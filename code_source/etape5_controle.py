"""
etape5_controle.py — vérifie et documente le résultat d'une série.

Rôle    : (1) sensibilité au seuil (BP, hypothèse H2) : chaque os principal est re-segmenté à SEUIL_OS_HU ± 50 HU
              dans la même zone, et l'écart entre les surfaces est mesuré en mm (moyen, 95e centile) ;
          (2) aperçus : rendu 3D des os exportés et coupes orthogonales avec les os en couleur ;
          (3) rapports : rapport.json (tout), rapport.md (lisible), reperes_auto.mrk.json (tête fémorale, format
              Markups de 3D Slicer, lisible par Planificateur_CORA_3Dv2).
Entrées : Volume (étape 1), Segmentation nommée (étapes 2-3), mesures des maillages (étape 4).
Sorties : dans resultats/<série>/ : rapport.json, rapport.md, apercu_3d.png, apercu_coupes.png, reperes_auto.mrk.json.
"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi

import etape4_maillage as E4
import parametres as P
from etape2_segmentation import boite_englobante

OS_CONTROLES = ("femur", "tibia", "fibula", "talus", "calcaneus", "tarse", "patella")


# =============================================================================== sensibilité au seuil (H2)
def surface(m):
    """Voxels de surface d'un masque (voxels de l'objet qui touchent le fond par une face)."""
    return m & ~ndi.binary_erosion(m, iterations=1, border_value=0)


def champ(plein, esp):
    """Masque plein légèrement flouté (comme avant le maillage) : la surface est l'isovaleur 0,5."""
    return ndi.gaussian_filter(plein.astype(np.float32), sigma=P.SIGMA_MAILLAGE_MM / np.asarray(esp))


def sommets_surface(g):
    """Sommets (indices k, j, i fractionnaires) de l'isosurface 0,5 d'un champ (marching cubes de VTK)."""
    import vtk_leger as vtk
    from vtkmodules.util import numpy_support as vns
    im = vtk.vtkImageData()
    im.SetDimensions(g.shape[2], g.shape[1], g.shape[0])
    im.GetPointData().SetScalars(vns.numpy_to_vtk(np.ascontiguousarray(g).ravel(), deep=True))
    fe = vtk.vtkFlyingEdges3D()
    fe.SetInputData(im)
    fe.SetValue(0, 0.5)
    fe.Update()
    return vns.vtk_to_numpy(fe.GetOutput().GetPoints().GetData())[:, ::-1].astype(float)


def sensibilite_seuil(seg, etiquettes, delta=None):
    """Re-segmente l'os à seuil ± delta (même zone : l'os dilaté de 3 mm, sans les autres os), le remplit de la
    même façon, puis mesure la distance de chaque sommet de la nouvelle surface à la surface de référence, avec
    une précision inférieure au voxel : d ≈ (0,5 - g) / |grad g|, g = masque de référence flouté (celui du STL)."""
    delta = delta or P.VARIATION_SEUIL_HU
    esp = np.array(seg.espacement)
    m = np.isin(seg.etiquettes, etiquettes)
    b = boite_englobante(m)
    r = np.ceil((3.0 + P.RAYON_FERMETURE_MM) / esp).astype(int) + 4
    lo = np.maximum(np.array([s.start for s in b]) - r, 0)
    hi = np.minimum(np.array([s.stop for s in b]) + r, m.shape)
    boite = tuple(slice(a, z) for a, z in zip(lo, hi))
    ref, _ = E4.remplir(seg, masque=m, boite=(lo, hi))
    g_ref = champ(ref, esp)
    grad = np.sqrt(sum(x ** 2 for x in np.gradient(g_ref, *esp)))
    img = sitk.GetImageFromArray(ref.astype(np.uint8))
    img.SetSpacing(tuple(float(x) for x in esp[::-1]))
    loin = sitk.GetArrayFromImage(sitk.SignedMaurerDistanceMap(img, insideIsPositive=False, squaredDistance=False,
                                                               useImageSpacing=True))   # secours loin de la surface
    autres = (seg.etiquettes[boite] > 0) & ~m[boite]
    zone = ndi.binary_dilation(m[boite], iterations=int(np.ceil(3.0 / esp.min()))) & ~autres
    resultat = {}
    for signe, cle in ((-1, "moins"), (1, "plus")):
        seuil = P.SEUIL_OS_HU + signe * delta
        variante = (seg.image[boite] >= seuil) & zone
        lab, _ = ndi.label(variante, np.ones((3, 3, 3), bool))
        garde = np.unique(lab[variante & m[boite]])
        mv = np.zeros(m.shape, bool)
        mv[boite] = np.isin(lab, garde[garde > 0])
        plein, _ = E4.remplir(seg, masque=mv, boite=(lo, hi))
        p = sommets_surface(champ(plein, esp))
        g = ndi.map_coordinates(g_ref, p.T, order=1)
        n = ndi.map_coordinates(grad, p.T, order=1)
        d = (0.5 - g) / np.maximum(n, 1e-6)                    # > 0 : la nouvelle surface est à l'extérieur
        hors = (g < 0.02) | (g > 0.98)                          # loin de la référence : distance au voxel près
        q = np.clip(np.rint(p[hors]).astype(int), 0, np.array(ref.shape) - 1)
        d[hors] = loin[tuple(q.T)]                              # distance signée (< 0 dedans), au voxel près
        resultat[cle] = {"seuil_hu": seuil, "ecart_moyen_mm": round(float(d.mean()), 3),
                         "ecart_absolu_moyen_mm": round(float(np.abs(d).mean()), 3),
                         "ecart_p95_mm": round(float(np.percentile(np.abs(d), 95)), 3),
                         "ecart_max_mm": round(float(np.abs(d).max()), 2),
                         "variation_volume_pct": round(float((plein.sum() - ref.sum()) / ref.sum() * 100), 2)}
    return resultat


# =============================================================================== aperçus
def apercu_3d(dossier, bilan, chemin):
    """Rendu des STL exportés (deux vues), sans fenêtre."""
    import pyvista as pv
    pv.OFF_SCREEN = True
    noms = [n for n in bilan if not (n == "tarse" and any(k in bilan for k in ("talus", "calcaneus")))]
    if not noms:
        return
    pl = pv.Plotter(off_screen=True, window_size=(1600, 900), shape=(1, 2), border=False)
    for k in range(2):
        pl.subplot(0, k)
        pl.set_background("white")
        for n in noms:
            m = pv.read(str(Path(dossier) / bilan[n]["fichier"]))
            pl.add_mesh(m, color=E4.couleur(n), smooth_shading=True, specular=0.25)
        if k == 0:
            pl.view_xz()
        else:
            pl.view_yz()
        pl.camera.up = (0, 0, 1)
        pl.reset_camera()
        pl.add_text(["vue de face (x, z)", "vue de profil (y, z)"][k], font_size=10, color="black")
    pl.screenshot(str(chemin))
    pl.close()


def apercu_coupes(seg, volume, chemin):
    """Trois coupes orthogonales (axiale, coronale, sagittale) passant par le centre de l'os principal (fémur,
    sinon tibia, sinon le plus gros os nommé) ; contour et nom de chaque os en couleur."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lab = seg.etiquettes
    nommes = {e: n for e, n in seg.noms.items() if n and E4.base(n) != "objet"}
    if not nommes:
        return
    taille = np.bincount(lab.ravel())
    principal = next((e for b in ("femur", "tibia") for e, n in nommes.items() if E4.base(n) == b),
                     max(nommes, key=lambda e: taille[e]))
    c = np.median(np.argwhere(lab[::2, ::2, ::2] == principal) * 2, axis=0).astype(int)
    o = np.array(seg.origine_kji)
    esp = seg.espacement
    vues = [("axiale", (c[0], slice(None), slice(None)), 1.0, False),
            ("coronale", (slice(None), c[1], slice(None)), esp[0] / esp[2], True),
            ("sagittale", (slice(None), slice(None), c[2]), esp[0] / esp[1], True)]
    fig, ax = plt.subplots(1, 3, figsize=(18, 8))
    for a, (titre, sl, aspect, retourner) in zip(ax, vues):
        sl_vol = tuple(x + o[n] if isinstance(x, (int, np.integer)) else slice(o[n], o[n] + lab.shape[n]) for n, x in enumerate(sl))
        img, l = volume.hu[sl_vol], lab[sl]
        if retourner:                                    # coupe coronale ou sagittale : la tête (k croissant) en haut
            img, l = img[::-1], l[::-1]
        a.imshow(np.clip(img, -250, 1750), cmap="gray", aspect=aspect, interpolation="nearest")
        for e, n in nommes.items():
            mk = l == e
            if mk.sum() < 4:
                continue
            col = E4.couleur(n)
            a.contour(mk, [0.5], colors=[col], linewidths=1.2)
            a.imshow(np.dstack([np.broadcast_to(np.array(col), mk.shape + (3,)), mk * 0.25]), aspect=aspect)
            y, x = np.argwhere(mk).mean(0)
            a.text(x, y, E4.libelle(n), color=col, fontsize=9, ha="center", va="center", weight="bold")
        a.set_title(f"coupe {titre}")
        a.axis("off")
    fig.suptitle("Os segmentés sur le scanner (fenêtre osseuse), coupes par le centre de l'os principal")
    fig.tight_layout()
    fig.savefig(chemin, dpi=80)
    plt.close(fig)


# =============================================================================== rapports
def markups(reperes):
    """Repères au format Markups de 3D Slicer (lisible par Planificateur_CORA_3Dv2 : geometrie.charger_reperes)."""
    points = [{"id": str(n + 1), "label": nom, "position": [round(x, 4) for x in r["centre_lps"]],
               "description": f"sphère ajustée, rayon {r['rayon_mm']} mm"} for n, (nom, r) in enumerate(sorted(reperes.items()))]
    return {"@schema": "https://raw.githubusercontent.com/slicer/slicer/master/Modules/Loadable/Markups/Resources/Schema/markups-schema-v1.0.3.json#",
            "markups": [{"type": "Fiducial", "coordinateSystem": "LPS", "coordinateUnits": "mm", "controlPoints": points}]}


def rapport_md(r):
    i = r["serie"]
    lignes = [f"# Segmentation osseuse : {i['nom']}", "",
              f"*Calcul du {r['date']} (durée {r['duree_s']} s).*", "",
              "## Série DICOM", "",
              "| Élément | Valeur |", "|---|---|",
              f"| Patient / étude | {i.get('patient', '')} · {i.get('date', '')} · {i.get('description', '')} |",
              f"| Scanner | {i.get('fabricant', '')}, noyau {i.get('noyau', '')}, {i.get('kv', '')} kV |",
              f"| Volume | {' × '.join(map(str, i['dimensions_kji']))} voxels (coupes × lignes × colonnes) |",
              f"| Voxel | {i['espacement_kji_mm'][0]:.3f} × {i['espacement_kji_mm'][1]:.3f} × {i['espacement_kji_mm'][2]:.3f} mm |",
              f"| Système des STL | {r['parametres']['SYSTEME_COORDONNEES']} (mm, coordonnées du scanner) |", "",
              "## Os exportés", "",
              "| Fichier | Os | Volume (cm³) | Triangles | Étanche | Euler | Affinage (moy., mm) | Écart ±50 HU (moy. / P95, mm) |",
              "|---|---|---|---|---|---|---|---|"]
    for nom, m in r["os"].items():
        s = m.get("sensibilite_seuil")
        sens = (f"{s['moins']['ecart_absolu_moyen_mm']:.2f} / {s['moins']['ecart_p95_mm']:.2f} ; "
                f"{s['plus']['ecart_absolu_moyen_mm']:.2f} / {s['plus']['ecart_p95_mm']:.2f}") if s else "n.d."
        aff = m.get("affinage_demi_hauteur")
        aff_txt = f"{aff['moyen_mm']:+.2f}" if aff else "n.d."
        lignes.append(f"| `{m['fichier']}` | {m['libelle']} | {m['volume_cm3'] or m['volume_voxels_cm3']} | {m['triangles']} | "
                      f"{'oui' if m['etanche'] and m['orientation_coherente'] else '**non**'} | {m['euler']} | "
                      f"{aff_txt} | {sens} |")
    lignes += ["", "Euler = 2 pour un os d'un seul morceau sans trou (topologie d'une sphère) ; un groupe de n os sans trou "
                   "donne 2n. Affinage : déplacement moyen des sommets vers le bord « demi-hauteur » (négatif = vers "
                   "l'intérieur ; corrige le biais d'un seuil bas, voir code_source/README.md). "
                   "Écart ± 50 HU : distance moyenne et 95e centile entre la surface au seuil de référence "
                   f"({r['parametres']['SEUIL_OS_HU']} HU) et la surface à {r['parametres']['SEUIL_OS_HU'] - 50} HU puis "
                   f"{r['parametres']['SEUIL_OS_HU'] + 50} HU (BP, hypothèse H2 : cible < {P.ECART_SURFACE_CIBLE_MM} mm).", "",
               "## Identification", "", "| Segment | Nom | Volume (cm³) | Raison |", "|---|---|---|---|"]
    for s in r["segments"]:
        if s["nom"]:
            lignes.append(f"| {s['etiquette']} | {E4.libelle(s['nom'])} | {s['volume_cm3']} | {s['raison']} |")
    autres = [s for s in r["segments"] if not s["nom"]]
    if autres:
        lignes.append(f"| … | {len(autres)} segment(s) non identifié(s) | {sum(s['volume_cm3'] for s in autres):.1f} | "
                      "vertèbres, petits os, débris : visibles dans segmentation.seg.nrrd |")
    if r["reperes"]:
        lignes += ["", "## Repères trouvés", ""]
        for nom, x in r["reperes"].items():
            c = x["centre_lps"]
            lignes.append(f"* **{nom}** : centre ({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f}) mm LPS, rayon {x['rayon_mm']} mm "
                          f"({x['points']} points de l'interligne, couverture {x['couverture']:.0%}) → `reperes_auto.mrk.json`")
    if r["avertissements"]:
        lignes += ["", "## Avertissements", ""] + [f"* {a}" for a in r["avertissements"]]
    lignes += ["", "## Fichiers", "",
               "* `*.stl` : un maillage étanche par os (coordonnées du scanner, mm) ; `tarse.stl` = tous les os du tarse ;",
               "* `segmentation.seg.nrrd` : toutes les étiquettes avec leurs noms, à ouvrir dans 3D Slicer avec la série DICOM ;",
               "* `apercu_3d.png`, `apercu_coupes.png` : contrôle visuel ;",
               "* `graines.json` (s'il existe) : points nommés par l'utilisateur, réappliqués à chaque calcul ;",
               "* `rapport.json` : toutes les valeurs de ce rapport.", ""]
    return "\n".join(lignes)


def controler(seg, volume, bilan, dossier, debut, avec_sensibilite=True, avec_images=None, journal=print,
              seulement=None):
    """Sensibilité au seuil, aperçus et rapports d'une série (avec `seulement` : sensibilité de ces os seulement)."""
    dossier = Path(dossier)
    avec_images = P.IMAGES_CONTROLE if avec_images is None else avec_images
    if avec_sensibilite:
        for nom, m in bilan.items():
            if E4.base(nom) in OS_CONTROLES and (seulement is None or nom in seulement or "sensibilite_seuil" not in m):
                try:
                    m["sensibilite_seuil"] = s = sensibilite_seuil(seg, m["etiquettes"])
                    journal(f"  seuil ± {P.VARIATION_SEUIL_HU} HU, {nom} : écart moyen {s['moins']['ecart_absolu_moyen_mm']:.2f} / "
                            f"{s['plus']['ecart_absolu_moyen_mm']:.2f} mm, P95 {s['moins']['ecart_p95_mm']:.2f} / "
                            f"{s['plus']['ecart_p95_mm']:.2f} mm, volume {s['moins']['variation_volume_pct']:+.1f} / "
                            f"{s['plus']['variation_volume_pct']:+.1f} %")
                except Exception as exc:
                    journal(f"  ⚠ sensibilité au seuil impossible pour {nom} : {exc}")
    if avec_images:
        try:
            apercu_3d(dossier, bilan, dossier / "apercu_3d.png")
            apercu_coupes(seg, volume, dossier / "apercu_coupes.png")
        except Exception as exc:
            journal(f"  ⚠ aperçus non produits : {exc}")
    vox = seg.volume_voxel
    taille = np.bincount(seg.etiquettes.ravel())
    segments = [{"etiquette": int(e), "nom": n, "volume_cm3": round(float(taille[e]) * vox / 1000, 2),
                 "raison": seg.raisons.get(e, "")} for e, n in sorted(seg.noms.items()) if e < len(taille)]
    params = {k: getattr(P, k) for k in dir(P) if k.isupper() and isinstance(getattr(P, k), (int, float, str, tuple))}
    r = {"date": datetime.now().isoformat(" ", "seconds"), "duree_s": round(float(__import__("time").time() - debut), 1),
         "serie": volume.infos, "parametres": params, "durees_segmentation_s": seg.duree_s, "os": bilan,
         "segments": segments, "reperes": seg.reperes,
         "avertissements": list(volume.avertissements) + list(seg.avertissements)}
    (dossier / "rapport.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)), encoding="utf-8")
    (dossier / "rapport.md").write_text(rapport_md(r), encoding="utf-8")
    mrk = dossier / "reperes_auto.mrk.json"
    if seg.reperes:
        mrk.write_text(json.dumps(markups(seg.reperes), ensure_ascii=False, indent=1), encoding="utf-8")
    elif mrk.exists():
        mrk.unlink()
    return r
