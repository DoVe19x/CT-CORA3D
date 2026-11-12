"""
etape4_maillage.py — transforme chaque os segmenté en un maillage 3D étanche (STL), comme 3D Slicer.

Rôle    : pour chaque os nommé (ou groupe d'os : « tarse » = talus + calcanéus + autres os du tarse) :
          (1) remplissage : fermeture morphologique (pores de la corticale) puis remplissage des cavités (canal
              médullaire, os spongieux) ; un os coupé par le bord du champ du scanner reçoit d'abord un « couvercle »
              (sa section remplie) pour que son canal soit fermé ;
          (2) surface : léger flou du masque puis « marching cubes » (vtkFlyingEdges3D, isovaleur 0,5) ;
          (3) lissage « windowed sinc » (ne rétrécit pas le maillage), décimation si trop de triangles ;
          (4) passage aux coordonnées du scanner (LPS, mm) par la matrice de l'étape 1, normales vers l'extérieur ;
          (5) contrôle : étanchéité (chaque arête partagée par 2 triangles exactement), orientation cohérente,
              nombre d'Euler (2 par morceau sans trou), volume ; écriture du STL binaire.
          Écrit aussi segmentation.seg.nrrd : toutes les étiquettes, avec noms et couleurs, lisible par 3D Slicer.
Entrées : Segmentation nommée (étapes 2 et 3).
Sorties : resultats/<série>/<os>.stl, segmentation.seg.nrrd ; dictionnaire des mesures de chaque maillage.
"""
import gzip
from pathlib import Path

import numpy as np
import SimpleITK as sitk
import trimesh
import vtk_leger as vtk                  # seulement les classes utilisées (voir vtk_leger.py)
from scipy import ndimage as ndi
from vtkmodules.util import numpy_support as vns

import parametres as P
from etape2_segmentation import boite_englobante


# =============================================================================== noms et groupes
def base(nom):
    """« femur_gauche » -> « femur »."""
    return nom.split("_")[0] if nom else ""


def cote(nom):
    return nom.split("_", 1)[1] if nom and "_" in nom else ""


def libelle(nom):
    """Nom lisible : « fémur gauche », « os 12 »."""
    if not nom:
        return "os non identifié"
    return P.NOMS_OS.get(base(nom), base(nom)) + (f" {cote(nom)}" if cote(nom) else "")


def couleur(nom):
    return P.COULEURS.get(base(nom), P.COULEURS["autre"])


def exports(seg):
    """{fichier (sans .stl): [étiquettes]} : un fichier par os nommé, plus les groupes (tarse = tout le tarse)."""
    sortie = {}
    for e, n in seg.noms.items():
        if not n or base(n) in ("objet", "autre"):           # « autre » : non identifié (ou refusé par l'utilisateur)
            if P.EXPORTER_AUTRES and base(n) != "objet":
                sortie[f"autre_{e}"] = [e]
            continue
        sortie.setdefault(n, []).append(e)
    for groupe, membres in P.GROUPES_EXPORT.items():
        cotes = {cote(n) for n in seg.noms.values() if base(n) in membres}
        for c in cotes:
            etiq = [e for e, n in seg.noms.items() if base(n) in membres and cote(n) == c]
            nom = groupe + (f"_{c}" if c else "")
            sortie[nom] = sorted(etiq)                   # remplace l'export « tarse » seul par le groupe complet
    return sortie


# =============================================================================== remplissage
def remplir(seg, etiquettes=None, masque=None, boite=None):
    """Masque plein d'un os : fermeture (RAYON_FERMETURE_MM) + couvercles aux bords du volume + remplissage 3D.
    L'os est donné par ses étiquettes, ou par un masque booléen de la zone recadrée. Renvoie (masque, coin) :
    masque booléen d'une boîte englobante agrandie (ou de la boîte imposée), et coin de cette boîte."""
    esp = np.array(seg.espacement)
    m = np.isin(seg.etiquettes, etiquettes) if masque is None else masque
    b = boite_englobante(m)
    debut, fin = np.array([s.start for s in b]), np.array([s.stop for s in b])
    r = np.ceil(P.RAYON_FERMETURE_MM / esp).astype(int)
    lo, hi = (debut - r - 2, fin + r + 2) if boite is None else (np.array(boite[0]), np.array(boite[1]))
    # bords du volume COMPLET (le champ du scanner) touchés par l'os : l'os y est coupé
    coupe_bas = np.array(seg.origine_kji) + debut == 0
    coupe_haut = np.array(seg.origine_kji) + fin == np.array(seg.forme_volume)
    bloc = np.zeros(hi - lo, bool)
    src_lo, src_hi = np.maximum(lo, 0), np.minimum(hi, m.shape)
    bloc[tuple(slice(a - l, c - l) for a, c, l in zip(src_lo, src_hi, lo))] = m[tuple(slice(a, c) for a, c in zip(src_lo, src_hi))]
    img = sitk.GetImageFromArray(bloc.astype(np.uint8))
    img.SetSpacing(tuple(float(s) for s in esp[::-1]))
    ferme = sitk.GetArrayFromImage(sitk.BinaryMorphologicalClosing(img, [int(x) for x in r[::-1]], sitk.sitkBall)).astype(bool)
    ferme |= bloc
    # couvercles : là où l'os sort du champ, la tranche au bord est fermée par sa section remplie (2D)
    for axe in range(3):
        for cote_, touche in (("bas", coupe_bas[axe]), ("haut", coupe_haut[axe])):
            if not touche:
                continue
            idx = int(debut[axe] - lo[axe]) if cote_ == "bas" else int(fin[axe] - 1 - lo[axe])
            tranche = np.take(ferme, idx, axis=axe)
            plein = ndi.binary_fill_holes(tranche)
            sl = [slice(None)] * 3
            sl[axe] = slice(0, idx + 1) if cote_ == "bas" else slice(idx, None)
            ferme[tuple(sl)] = False
            sl[axe] = idx
            ferme[tuple(sl)] = plein
    plein = sitk.GetArrayFromImage(sitk.BinaryFillhole(sitk.GetImageFromArray(ferme.astype(np.uint8)), fullyConnected=False)).astype(bool)
    return plein, lo


# =============================================================================== maillage
def affiner_demi_hauteur(seg, pts_lps, faces):
    """Affinage sous-voxel de la surface (« demi-hauteur » locale) : chaque sommet est déplacé le long de sa
    normale jusqu'au point où l'intensité vaut la moitié entre le pic de la corticale (à l'intérieur) et le fond
    (à l'extérieur). Pour un bord flou symétrique, ce point est le vrai bord, quel que soit le seuil : on supprime
    ainsi le biais d'un seuil bas (surface trop à l'extérieur d'environ un écart-type du flou). Déplacement
    limité à ±DEPLACEMENT_MAX_MM, ignoré si le contraste est trop faible, puis lissé sur le maillage.
    Renvoie (nouveaux sommets, déplacements en mm)."""
    tm = trimesh.Trimesh(pts_lps, faces, process=False)
    n = np.asarray(tm.vertex_normals)                      # normales sortantes (volume > 0 vérifié avant)
    pas = 0.1
    s = np.arange(-P.PROFIL_INTERIEUR_MM, P.PROFIL_EXTERIEUR_MM + 1e-9, pas)
    echant = pts_lps[:, None, :] + s[None, :, None] * n[:, None, :]
    kji = seg.vers_indices(echant.reshape(-1, 3))
    prof = ndi.map_coordinates(seg.image.astype(np.float32), kji.T, order=1, mode="nearest").reshape(len(pts_lps), len(s))
    interieur = s <= 0.5
    i_pic = np.argmax(np.where(interieur[None, :], prof, -1e9), axis=1)
    pic = prof[np.arange(len(prof)), i_pic]
    apres = np.arange(len(s))[None, :] >= i_pic[:, None]
    fond = np.min(np.where(apres, prof, 1e9), axis=1)
    h = (pic + fond) / 2
    sous = apres & (prof < h[:, None])
    i_x = np.argmax(sous, axis=1)                          # premier échantillon sous la demi-hauteur après le pic
    trouve = sous[np.arange(len(prof)), i_x]
    i0 = np.maximum(i_x - 1, 0)
    p0, p1 = prof[np.arange(len(prof)), i0], prof[np.arange(len(prof)), i_x]
    t = np.clip((p0 - h) / np.maximum(p0 - p1, 1e-6), 0, 1)
    d = s[i0] + t * pas
    valide = trouve & (pic - fond >= P.CONTRASTE_MIN_HU) & (np.abs(d) <= P.DEPLACEMENT_MAX_MM)
    d = np.where(valide, d, 0.0)
    # lissage du champ de déplacement (moyenne avec les voisins, quelques passes) : pas de bruit voxel par voxel
    voisins = tm.vertex_neighbors
    lignes = np.repeat(np.arange(len(voisins)), [len(v) for v in voisins])
    cols = np.concatenate([np.asarray(v, int) for v in voisins]) if len(lignes) else np.zeros(0, int)
    deg = np.bincount(lignes, minlength=len(d)).astype(float)
    for _ in range(P.LISSAGE_DEPLACEMENT):
        moy = np.bincount(lignes, weights=d[cols], minlength=len(d)) / np.maximum(deg, 1)
        d = 0.5 * d + 0.5 * moy
    return pts_lps + d[:, None] * n, d, float(valide.mean())


def vers_numpy(pd):
    pts = vns.vtk_to_numpy(pd.GetPoints().GetData()).astype(np.float64)
    faces = vns.vtk_to_numpy(pd.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    return pts, faces


def vers_vtk(pts, faces):
    pd = vtk.vtkPolyData()
    p = vtk.vtkPoints()
    p.SetData(vns.numpy_to_vtk(np.ascontiguousarray(pts, dtype=np.float64), deep=True))
    pd.SetPoints(p)
    cells = vtk.vtkCellArray()
    off = np.arange(0, 3 * len(faces) + 1, 3, dtype=np.int64)
    cells.SetData(vns.numpy_to_vtkIdTypeArray(off, deep=True), vns.numpy_to_vtkIdTypeArray(faces.astype(np.int64).ravel(), deep=True))
    pd.SetPolys(cells)
    return pd


def controle(pts, faces):
    tm = trimesh.Trimesh(pts, faces, process=False)
    return {"etanche": bool(tm.is_watertight), "orientation_coherente": bool(tm.is_winding_consistent),
            "euler": int(tm.euler_number), "morceaux": int(tm.body_count),
            "volume_cm3": round(float(tm.volume) / 1000, 3) if tm.is_watertight else None,
            "surface_cm2": round(float(tm.area) / 100, 2), "triangles": int(len(faces)), "sommets": int(len(pts))}


def mailler(seg, etiquettes, systeme=None):
    """Maillage étanche d'un os (ou d'un groupe) : (sommets en mm, triangles, mesures)."""
    systeme = systeme or P.SYSTEME_COORDONNEES
    esp = np.array(seg.espacement)
    plein, lo = remplir(seg, etiquettes)
    volume_voxels = float(plein.sum()) * seg.volume_voxel
    f = np.pad(plein, 2).astype(np.float32)
    sigma = P.SIGMA_MAILLAGE_MM / esp
    g = ndi.gaussian_filter(f, sigma=sigma)
    im = vtk.vtkImageData()
    im.SetDimensions(g.shape[2], g.shape[1], g.shape[0])
    im.GetPointData().SetScalars(vns.numpy_to_vtk(g.ravel(), deep=True))
    fe = vtk.vtkFlyingEdges3D()
    fe.SetInputData(im)
    fe.SetValue(0, 0.5)
    fe.ComputeNormalsOff()
    fe.ComputeGradientsOff()
    fe.Update()
    pts, faces = vers_numpy(fe.GetOutput())
    if len(faces) == 0:
        raise ValueError("maillage vide")
    # indices (i, j, k) du bloc rembourré -> indices de la zone recadrée -> LPS
    ijk = pts + (lo[::-1] - 2)
    pts = ijk @ seg.affine[:3, :3].T + seg.affine[:3, 3]
    pd = vers_vtk(pts, faces)
    # morceaux : un os seul garde ses morceaux significatifs ; un groupe (bassin, métatarses…) les garde tous
    cf = vtk.vtkPolyDataConnectivityFilter()
    cf.SetInputData(pd)
    cf.SetExtractionModeToAllRegions()
    cf.ColorRegionsOn()
    cf.Update()
    aires = vns.vtk_to_numpy(cf.GetRegionSizes()).astype(float)
    if len(aires) > 1:
        garde = np.nonzero(aires >= 0.02 * aires.max())[0]
        cf2 = vtk.vtkPolyDataConnectivityFilter()
        cf2.SetInputData(pd)
        cf2.SetExtractionModeToSpecifiedRegions()
        for r in garde:
            cf2.AddSpecifiedRegion(int(r))
        cf2.Update()
        nettoie = vtk.vtkCleanPolyData()
        nettoie.SetInputConnection(cf2.GetOutputPort())
        nettoie.Update()
        pd = nettoie.GetOutput()
    lisse = vtk.vtkWindowedSincPolyDataFilter()
    lisse.SetInputData(pd)
    lisse.SetNumberOfIterations(P.ITERATIONS_LISSAGE)
    lisse.SetPassBand(P.BANDE_PASSANTE_LISSAGE)
    lisse.BoundarySmoothingOff()
    lisse.FeatureEdgeSmoothingOff()
    lisse.NonManifoldSmoothingOn()
    lisse.NormalizeCoordinatesOn()
    lisse.Update()
    pd = lisse.GetOutput()
    pts_l, faces_l = vers_numpy(pd)
    if len(faces_l) > P.TRIANGLES_MAX:
        dec = vtk.vtkQuadricDecimation()
        dec.SetInputData(pd)
        dec.SetTargetReduction(min(P.REDUCTION_MAX, 1.0 - P.TRIANGLES_MAX / len(faces_l)))
        dec.VolumePreservationOn()
        dec.Update()
        pts_d, faces_d = vers_numpy(dec.GetOutput())
        if controle(pts_d, faces_d)["etanche"]:          # la décimation ne doit jamais ouvrir le maillage
            pts_l, faces_l = pts_d, faces_d
    tm = trimesh.Trimesh(pts_l, faces_l, process=True)
    if tm.is_watertight and tm.volume < 0:
        tm.invert()                                      # normales vers l'extérieur
    pts_l, faces_l = np.asarray(tm.vertices), np.asarray(tm.faces)
    deplacement = None
    if P.AFFINAGE_DEMI_HAUTEUR and tm.is_watertight:
        nouveaux, d, part = affiner_demi_hauteur(seg, pts_l, faces_l)
        if controle(nouveaux, faces_l)["etanche"]:
            pts_l = nouveaux
            deplacement = {"moyen_mm": round(float(d.mean()), 3), "p95_mm": round(float(np.percentile(np.abs(d), 95)), 3),
                           "sommets_affines_pct": round(100 * part, 1)}
    bords = bords_touches(seg, etiquettes)
    if systeme.upper() == "RAS":
        pts_l = pts_l * [-1.0, -1.0, 1.0]               # rotation de 180° autour de z : orientation conservée
        for b in bords:
            b["point"], b["normale"] = [round(float(x), 3) for x in np.array(b["point"]) * [-1, -1, 1]], \
                [round(float(x), 6) for x in np.array(b["normale"]) * [-1, -1, 1]]
    mesures = controle(pts_l, faces_l)
    mesures["affinage_demi_hauteur"] = deplacement
    mesures["volume_voxels_cm3"] = round(volume_voxels / 1000, 3)
    mesures["systeme"] = systeme.upper()
    mesures["bords_volume"] = bords
    return pts_l, faces_l, mesures


def bords_touches(seg, etiquettes):
    """Bords du volume COMPLET (champ du scanner) touchés par l'os : là, l'os est coupé et fermé par un couvercle.
    Chaque bord est un plan (point, normale sortante) en LPS ; l'étape 6 s'en sert pour savoir si une extrémité
    articulaire manque (méthode CORA impossible)."""
    m = np.isin(seg.etiquettes, etiquettes)
    b = boite_englobante(m)
    debut, fin = np.array([s.start for s in b]), np.array([s.stop for s in b])
    o, forme = np.array(seg.origine_kji), np.array(seg.forme_volume)
    out = []
    for axe in range(3):                                 # axes (k, j, i) ; colonne de l'affine : i = 0, j = 1, k = 2
        col = seg.affine[:3, 2 - axe]
        for cote_, touche, indice in (("bas", o[axe] + debut[axe] == 0, -o[axe]),
                                      ("haut", o[axe] + fin[axe] == forme[axe], forme[axe] - 1 - o[axe])):
            if not touche:
                continue
            ijk = np.zeros(3)
            ijk[2 - axe] = indice
            point = seg.affine[:3, :3] @ ijk + seg.affine[:3, 3]
            normale = (col if cote_ == "haut" else -col) / np.linalg.norm(col)
            out.append({"axe": "kji"[axe], "cote": cote_, "point": [round(float(x), 3) for x in point],
                        "normale": [round(float(x), 6) for x in normale]})
    return out


def ecrire_stl(chemin, pts, faces, titre=""):
    """STL binaire (80 octets d'en-tête : programme, version et titre ; nombre de triangles ; puis normale + 3 sommets
    par triangle). Sert aussi à l'étape 7 (guides) et au serveur."""
    v = np.asarray(pts, np.float32)[np.asarray(faces)]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    donnees = np.zeros(len(faces), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    donnees["n"], donnees["v"] = n, v
    with open(chemin, "wb") as f:
        f.write(f"{P.PROGRAMME} {titre}".strip().encode("ascii", "replace")[:80].ljust(80, b" "))
        f.write(np.uint32(len(faces)).tobytes())
        f.write(donnees.tobytes())


# =============================================================================== segmentation pour 3D Slicer
def ecrire_seg_nrrd(seg, chemin):
    """Toutes les étiquettes dans un fichier .seg.nrrd (format « Segmentation » de 3D Slicer) : chaque segment a
    son nom et sa couleur ; la géométrie (origine, directions) place la zone recadrée au bon endroit."""
    lab = seg.etiquettes
    ids = [int(e) for e in np.unique(lab) if e]
    type_ = "unsigned char" if max(ids, default=0) < 256 else "unsigned short"
    data = lab.astype(np.uint8 if type_ == "unsigned char" else np.uint16)
    A = seg.affine
    vec = lambda v: "(" + ",".join(f"{x:.10g}" for x in v) + ")"
    lignes = ["NRRD0004", f"# fichier écrit par {P.PROGRAMME}", f"type: {type_}", "dimension: 3",
              "space: left-posterior-superior", f"sizes: {lab.shape[2]} {lab.shape[1]} {lab.shape[0]}",
              f"space directions: {vec(A[:3, 0])} {vec(A[:3, 1])} {vec(A[:3, 2])}", "kinds: domain domain domain",
              "encoding: gzip", f"space origin: {vec(A[:3, 3])}",
              "Segmentation_MasterRepresentation:=Binary labelmap",
              "Segmentation_ContainedRepresentationNames:=Binary labelmap|",
              "Segmentation_ReferenceImageExtentOffset:=0 0 0"]
    boites = ndi.find_objects(lab)
    for n, e in enumerate(ids):
        nom = seg.noms.get(e) or f"os_{e}"
        b = boites[e - 1]
        r, g, bl = couleur(seg.noms.get(e, ""))
        lignes += [f"Segment{n}_ID:=Segment_{e}", f"Segment{n}_Name:={nom}", f"Segment{n}_Color:={r} {g} {bl}",
                   f"Segment{n}_LabelValue:={e}", f"Segment{n}_Layer:=0",
                   f"Segment{n}_Extent:={b[2].start} {b[2].stop - 1} {b[1].start} {b[1].stop - 1} {b[0].start} {b[0].stop - 1}",
                   f"Segment{n}_Tags:=Segmentation.Status:completed|"]
    with open(chemin, "wb") as f:
        f.write(("\n".join(lignes) + "\n\n").encode("utf-8"))
        f.write(gzip.compress(np.ascontiguousarray(data).tobytes(), compresslevel=6))


def lire_seg_nrrd(chemin):
    """Relit un .seg.nrrd écrit par ecrire_seg_nrrd (ou par 3D Slicer, en étiquettes sur une couche) : renvoie
    (étiquettes (k, j, i), origine LPS, directions (colonnes i, j, k), {étiquette: nom})."""
    brut = Path(chemin).read_bytes()
    fin = brut.index(b"\n\n")
    entete = brut[:fin].decode("utf-8", "replace").splitlines()
    champs, segments = {}, {}
    for ligne in entete[1:]:
        if ligne.startswith("#"):
            continue
        if ":=" in ligne:
            k, v = ligne.split(":=", 1)
            if k.startswith("Segment") and "_" in k:
                n, cle = k[len("Segment"):].split("_", 1)
                segments.setdefault(n, {})[cle] = v
            continue
        if ":" in ligne:
            k, v = ligne.split(":", 1)
            champs[k.strip()] = v.strip()
    tailles = [int(x) for x in champs["sizes"].split()]
    vecteurs = [[float(c) for c in v.strip("()").split(",")] for v in champs["space directions"].replace(") (", ")|(").split("|")]
    origine = np.array([float(c) for c in champs["space origin"].strip("()").split(",")])
    types = {"unsigned char": np.uint8, "uchar": np.uint8, "unsigned short": np.uint16, "ushort": np.uint16,
             "short": np.int16, "int": np.int32, "unsigned int": np.uint32}
    donnees = brut[fin + 2:]
    if champs.get("encoding", "raw") in ("gzip", "gz"):
        donnees = gzip.decompress(donnees)
    lab = np.frombuffer(donnees, dtype=types[champs["type"]]).reshape(tailles[::-1]).astype(np.uint16)
    noms = {}
    for v in segments.values():
        if "LabelValue" in v:
            n = v.get("Name", "")
            noms[int(v["LabelValue"])] = "" if n.startswith("os_") else n
    return lab, origine, np.array(vecteurs).T, noms


def exporter(seg, dossier, journal=print, seulement=None, precedent=None):
    """STL de la série + segmentation pour Slicer. Renvoie {fichier: mesures}. Avec `seulement` (noms de fichiers),
    seuls ces os sont remaillés (correction dans l'application) ; les autres gardent leurs mesures `precedent`."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    a_faire = exports(seg)
    for ancien in dossier.glob("*.stl"):                 # STL d'os qui n'existent plus, ou à refaire
        if seulement is None or ancien.stem in seulement or ancien.stem not in a_faire:
            ancien.unlink()
    bilan = {}
    for nom, etiq in sorted(a_faire.items()):
        if seulement is not None and nom not in seulement and precedent and nom in precedent \
                and (dossier / f"{nom}.stl").exists():
            bilan[nom] = dict(precedent[nom], etiquettes=[int(e) for e in etiq])
            continue
        try:
            pts, faces, mesures = mailler(seg, etiq)
        except Exception as exc:                         # un os raté ne bloque pas les autres
            journal(f"  ⚠ {nom} : maillage impossible ({exc})")
            continue
        chemin = dossier / f"{nom}.stl"
        ecrire_stl(chemin, pts, faces, f"{nom} ({mesures['systeme']}, mm)")
        mesures.update({"fichier": chemin.name, "etiquettes": [int(e) for e in etiq], "libelle": libelle(nom)})
        bilan[nom] = mesures
        etat = "étanche" if mesures["etanche"] and mesures["orientation_coherente"] else "⚠ NON ÉTANCHE"
        journal(f"  {nom + '.stl':22s} {mesures['volume_cm3'] or mesures['volume_voxels_cm3']:7.2f} cm³  "
                f"{mesures['triangles']:7d} triangles  {mesures['morceaux']} morceau(x)  Euler {mesures['euler']:3d}  {etat}")
    ecrire_seg_nrrd(seg, dossier / "segmentation.seg.nrrd")
    return bilan
