"""
etape3_identification.py — nomme chaque os (fémur, tibia, fibula…) et applique les corrections anatomiques.

Rôle    : (1) décrire chaque segment : volume, longueur et allongement (analyse en composantes principales),
              densité, contacts avec ses voisins, contact avec le bord du volume (os coupé par le champ du scanner) ;
          (2) écarter les objets non osseux (fantôme de calibration : densité homogène, sans os spongieux) ;
          (3) reconnaître les os par leurs formes et leurs voisinages :
              fémur  = os long dont une extrémité porte une sphère (tête fémorale) au contact d'un gros os (bassin) ;
              tibia  = os long longé par un os long fin (fibula), ou en contact avec le fémur au genou ;
              patella, fabelles = petits os compacts au bout distal du fémur ;
              tarse  = os compacts au bout distal du tibia (talus : plus grand contact avec le tibia ;
                       calcanéus : le plus long) ; métatarses : os longs au-delà du tarse ; phalanges ensuite ;
          (4) corrections : sphère de la tête fémorale (la tête est rendue au fémur), séparation tibia / fibula,
              points nommés par l'utilisateur (renommer, ou séparer un segment qui contient deux os).
Entrées : Segmentation de l'étape 2 ; points nommés facultatifs (resultats/<série>/graines.json).
Sorties : seg.noms, seg.raisons, seg.reperes (tête fémorale : centre, rayon) complétés.
"""
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi

import etape2_segmentation as E2
import etape4_maillage as E4
import parametres as P


# =============================================================================== description des segments
def decrire(seg, etiquettes=None):
    """Descripteurs de forme et de densité de chaque segment (coordonnées LPS, mm)."""
    lab, I = seg.etiquettes, seg.image
    boites = ndi.find_objects(lab)
    vox = seg.volume_voxel
    bord_lo = np.array(seg.origine_kji)
    bord_hi = bord_lo + np.array(lab.shape)
    plein = np.array(seg.forme_volume)
    d = {}
    for e in (etiquettes or [x for x in range(1, len(boites) + 1) if boites[x - 1] is not None]):
        b = boites[e - 1]
        if b is None:
            continue
        m = lab[b] == e
        kji = np.argwhere(m) + [s.start for s in b]
        if len(kji) < 10:
            continue
        p = seg.vers_lps(kji)
        c = p.mean(0)
        _, _, vt = np.linalg.svd(p - c, full_matrices=False)
        proj = (p - c) @ vt.T
        lo, hi = np.percentile(proj, 1, axis=0), np.percentile(proj, 99, axis=0)
        L = hi - lo
        t = proj[:, 0]
        ext = [p[t <= lo[0] + 0.05 * L[0]].mean(0), p[t >= hi[0] - 0.05 * L[0]].mean(0)]
        valeurs = I[b][m].astype(float)
        coeur = ndi.binary_erosion(m, iterations=2)          # intérieur : sans les voxels de bord (flou)
        interieur = I[b][coeur].astype(float) if coeur.sum() >= 50 else valeurs
        touche = [bool((np.array([s.start for s in b]) + bord_lo == 0)[a] or (np.array([s.stop for s in b]) + bord_lo == plein)[a])
                  for a in range(3)]
        d[e] = {"volume_mm3": float(len(kji) * vox), "centre": c, "axes": vt, "longueurs": L,
                "allongement": float(L[0] / max(L[1], 1e-6)), "extremites": ext,
                "hu_moyen": float(valeurs.mean()), "cv": float(interieur.std() / max(interieur.mean(), 1.0)),
                "frac_spongieux": float((interieur < 600).mean()), "bord": touche,
                "tronque": any(touche), "boite": b}
    return d


def base_nom(n):
    return (n or "").split("_")[0]


def voisins(paires, e):
    """{voisin: surface de contact (mm²)} d'une étiquette."""
    return {(b if a == e else a): s for (a, b), s in paires.items() if e in (a, b)}


def afficher(d, paires, noms=None):
    noms = noms or {}
    for e in sorted(d, key=lambda x: -d[x]["volume_mm3"]):
        x = d[e]
        v = voisins(paires, e)
        vs = ", ".join(f"{k}:{s:.0f}" for k, s in sorted(v.items(), key=lambda t: -t[1])[:4])
        print(f"  {e:3d} {noms.get(e, ''):10s} {x['volume_mm3']/1000:7.2f} cm³  L={x['longueurs'][0]:6.1f} "
              f"e={x['allongement']:5.2f}  HU={x['hu_moyen']:5.0f} cv={x['cv']:.2f} sp={x['frac_spongieux']:.2f} "
              f"bord={'oui' if x['tronque'] else 'non'}  voisins(mm²) {vs}")


# =============================================================================== outils géométriques
def angle_axes(a, b):
    """Angle (degrés, 0 à 90) entre deux directions non orientées."""
    return float(np.degrees(np.arccos(np.clip(abs(float(np.dot(a, b))), 0.0, 1.0))))


def est_objet(x):
    """Objet non osseux (fantôme de calibration, tige…) : densité homogène, pas d'os spongieux."""
    return x["frac_spongieux"] < P.FRACTION_SPONGIEUX_MAX_OBJET and x["cv"] < P.CV_MAX_OBJET


def est_os_long(x):
    """Os long : assez long et allongé ; un os coupé par le bord du volume peut paraître trapu."""
    e_min = P.ALLONGEMENT_OS_LONG if not x["tronque"] else 2.0
    return x["longueurs"][0] >= P.LONGUEUR_OS_LONG_MM and x["allongement"] >= e_min


def recouvrement(a, b):
    """Fraction de la longueur de b (projetée sur l'axe de a) qui recouvre la longueur de a : ≈ 1 pour une fibula
    le long du tibia, ≈ 0 pour deux os bout à bout."""
    u = a["axes"][0]
    ia = sorted(((e - a["centre"]) @ u) for e in a["extremites"])
    ib = sorted(((e - a["centre"]) @ u) for e in b["extremites"])
    return max(0.0, min(ia[1], ib[1]) - max(ia[0], ib[0])) / max(ib[1] - ib[0], 1e-6)


def est_compact(x):
    return x["allongement"] < P.ALLONGEMENT_COMPACT


def extremite_proche(x, point):
    """Indice (0 ou 1) de l'extrémité d'un os la plus proche d'un point."""
    return int(np.argmin([np.linalg.norm(e - point) for e in x["extremites"]]))


def profil_sections(seg, e, x, n=20):
    """Aire moyenne des sections (mm²) dans le premier et le dernier cinquième de l'os, le long de son axe :
    l'extrémité la plus large d'un tibia est son plateau (proximal)."""
    b = x["boite"]
    kji = np.argwhere(seg.etiquettes[b] == e) + [s.start for s in b]
    t = (seg.vers_lps(kji) - x["centre"]) @ x["axes"][0]
    lo, hi = np.percentile(t, 1), np.percentile(t, 99)
    pas = (hi - lo) / n
    vols = np.histogram(t, bins=n, range=(lo, hi))[0] * seg.volume_voxel / pas
    return float(vols[: n // 5].mean()), float(vols[-(n // 5):].mean())


# =============================================================================== tête fémorale (sphère)
def ajuster_sphere(points, rng, iterations=4000):
    """RANSAC : sphère passant au mieux par des points (mm) ; rayon borné ; puis moindres carrés sur les inliers."""
    meilleur = (0, None)
    rmin, rmax = P.RAYON_TETE_MM
    n = len(points)
    if n < 20:
        return None
    for _ in range(iterations):
        q = points[rng.choice(n, 4, replace=False)]
        A = np.c_[2 * q, np.ones(4)]
        try:
            s = np.linalg.solve(A, (q ** 2).sum(1))
        except np.linalg.LinAlgError:
            continue
        c = s[:3]
        r2 = s[3] + c @ c
        if r2 <= 0 or not (rmin <= np.sqrt(r2) <= rmax):
            continue
        nb = int((np.abs(np.linalg.norm(points - c, axis=1) - np.sqrt(r2)) < P.TOLERANCE_SPHERE_MM).sum())
        if nb > meilleur[0]:
            meilleur = (nb, (c, float(np.sqrt(r2))))
    if meilleur[1] is None:
        return None
    c, r = meilleur[1]
    for _ in range(3):                                   # raffinement par moindres carrés sur les inliers
        inl = np.abs(np.linalg.norm(points - c, axis=1) - r) < P.TOLERANCE_SPHERE_MM
        q = points[inl]
        s = np.linalg.lstsq(np.c_[2 * q, np.ones(len(q))], (q ** 2).sum(1), rcond=None)[0]
        c, r = s[:3], float(np.sqrt(s[3] + s[:3] @ s[:3]))
    inl = np.abs(np.linalg.norm(points - c, axis=1) - r) < P.TOLERANCE_SPHERE_MM
    # couverture : fraction de 200 directions régulières qui ont un point de la sphère à moins de 25°
    u = (points[inl] - c) / np.linalg.norm(points[inl] - c, axis=1)[:, None]
    g = np.arange(200) + 0.5
    phi, th = np.arccos(1 - 2 * g / 200), np.pi * (1 + 5 ** 0.5) * g
    F = np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]
    couverture = float(((F @ u.T) > np.cos(np.radians(25))).any(1).mean())
    return {"centre_mm": c, "rayon_mm": r, "inliers": int(inl.sum()), "candidats": n, "couverture": couverture}


def tete_femorale(seg, femur, voisin, journal=print):
    """Cherche la tête fémorale au contact fémur / gros voisin (bassin) : l'interligne, ligne sombre entre la tête
    et l'acétabulum, est révélé par un « chapeau haut-de-forme noir » (fermeture en niveaux de gris - image),
    puis une sphère y est ajustée. Si elle est valide, la zone fémur + bassin est redistribuée : graine « fémur »
    = intérieur de la sphère (rayon - marge) + diaphyse, graine « bassin » = au-delà de la sphère (rayon + marge).
    Renvoie le centre (LPS) et le rayon, ou None."""
    esp = np.array(seg.espacement)
    lab = seg.etiquettes
    F, N = lab == femur, lab == voisin
    contact = ndi.binary_dilation(F, E2.S26) & N
    if not contact.any():
        return None
    c0 = np.argwhere(contact).mean(0)
    r = np.ceil(P.RAYON_RECHERCHE_TETE_MM / esp).astype(int)
    lo = np.maximum(np.floor(c0).astype(int) - r, 0)
    hi = np.minimum(np.floor(c0).astype(int) + r + 1, lab.shape)
    b = tuple(slice(a, z) for a, z in zip(lo, hi))
    img = sitk.GetImageFromArray(seg.image[b].astype(np.float32))
    img.SetSpacing(tuple(float(s) for s in esp[::-1]))
    rayon_vox = [max(1, int(round(P.RAYON_VALLEE_MM / s))) for s in esp[::-1]]
    vallee = sitk.GetArrayFromImage(sitk.GrayscaleMorphologicalClosing(img, rayon_vox, sitk.sitkBall)) - seg.image[b]
    pres = ndi.binary_dilation(F[b] | N[b], iterations=int(np.ceil(3.0 / esp.min())))
    cand = (vallee > P.PROFONDEUR_VALLEE_HU) & (seg.image[b] > P.HU_MIN_VALLEE) & pres
    pts = (np.argwhere(cand) + lo) * esp
    pts = pts[np.linalg.norm(pts - c0 * esp, axis=1) < P.RAYON_RECHERCHE_TETE_MM]
    s = ajuster_sphere(pts, np.random.default_rng(0))
    if s is None or s["couverture"] < P.COUVERTURE_MIN_SPHERE or s["inliers"] < P.INLIERS_MIN_SPHERE:
        if s is not None:
            journal(f"    sphère rejetée (rayon {s['rayon_mm']:.1f} mm, {s['inliers']} points, couverture {s['couverture']:.2f})")
        return None
    c_vox, R = s["centre_mm"] / esp, s["rayon_mm"]
    if np.linalg.norm(s["centre_mm"] - c0 * esp) > R + 15:
        journal("    sphère trop loin du contact fémur / bassin : rejetée")
        return None
    # redistribution de la zone fémur + voisin à partir de graines séparées par la sphère
    zone = np.argwhere(F | N)
    d = np.linalg.norm((zone - c_vox) * esp, axis=1)
    est_f = F[tuple(zone.T)]
    graine_f = zone[(d <= R - P.MARGE_SPHERE_MM) | (est_f & (d > R + 3.0))]
    graine_n = zone[(~est_f) & (d >= R + P.MARGE_SPHERE_MM)]
    avant = int(F.sum())
    E2.recroissance(seg, {femur, voisin}, {femur: graine_f, voisin: graine_n})
    apres = int((seg.etiquettes == femur).sum())
    centre_lps = seg.vers_lps(c_vox)[0]
    journal(f"    tête fémorale : sphère de rayon {R:.1f} mm ({s['inliers']} points, couverture {s['couverture']:.0%}), "
            f"centre LPS ({centre_lps[0]:.1f}, {centre_lps[1]:.1f}, {centre_lps[2]:.1f}) ; "
            f"fémur {avant * seg.volume_voxel / 1000:.1f} → {apres * seg.volume_voxel / 1000:.1f} cm³")
    return {"centre_lps": [float(v) for v in centre_lps], "rayon_mm": round(R, 2), "points": s["inliers"],
            "couverture": round(s["couverture"], 3)}


# =============================================================================== fibula collée au tibia
def separer_fibula(seg, tibia, x, journal=print):
    """Si la fibula fait partie du segment « tibia » : sur des tranches perpendiculaires à l'os, elle apparaît au
    milieu de la jambe comme une petite tache séparée. Ces taches servent de graine « fibula », les grandes de
    graine « tibia », puis une croissance de région redistribue le segment. Renvoie l'étiquette de la fibula."""
    esp = np.array(seg.espacement)
    b = x["boite"]
    kji = np.argwhere(seg.etiquettes[b] == tibia) + [s.start for s in b]
    p = kji * esp
    c = p.mean(0)
    _, _, vt = np.linalg.svd(p - c, full_matrices=False)
    t, u, v = ((p - c) @ vt[0]), ((p - c) @ vt[1]), ((p - c) @ vt[2])
    px = float(esp.min())
    ui = np.round((u - u.min()) / px).astype(int)
    vi = np.round((v - v.min()) / px).astype(int)
    tmin, tmax = np.percentile(t, 0.5), np.percentile(t, 99.5)
    L = tmax - tmin
    tranches = []
    for tc in np.arange(tmin + 0.05 * L, tmin + 0.95 * L, P.PAS_TRANCHES_MM):
        sel = np.nonzero(np.abs(t - tc) < P.PAS_TRANCHES_MM / 2)[0]
        img = np.zeros((ui.max() + 1, vi.max() + 1), bool)
        img[ui[sel], vi[sel]] = True
        lab2, n = ndi.label(ndi.binary_fill_holes(img), np.ones((3, 3), bool))
        a = np.bincount(lab2.ravel()) * px * px
        a[0] = 0
        o = np.argsort(a)[::-1]
        ok = n >= 2 and a[o[1]] >= P.AIRE_MIN_FIBULA_MM2 and a[o[1]] / a[o[0]] < P.RAPPORT_AIRE_FIBULA_MAX
        lv = lab2[ui[sel], vi[sel]]
        centre = np.c_[u[sel], v[sel]][lv == o[1]].mean(0) if ok else None      # position de la petite tache
        tranches.append((sel, lv, o[0], o[1] if n >= 2 else -1, ok, centre))
    # plus longue série continue : la petite tache existe et se déplace de moins de SAUT_MAX_FIBULA_MM par tranche
    meilleure, debut = (0, 0, -1), None
    for n_, tr in enumerate(tranches):
        suite = tr[4] and debut is not None and np.linalg.norm(tr[5] - tranches[n_ - 1][5]) < P.SAUT_MAX_FIBULA_MM
        debut = (debut if suite else n_) if tr[4] else None
        if debut is not None and n_ - debut + 1 > meilleure[0]:
            meilleure = (n_ - debut + 1, debut, n_)
    longueur = meilleure[0] * P.PAS_TRANCHES_MM
    if longueur < P.SERIE_MIN_FIBULA * L:
        return None
    gf, gt = [], []
    for sel, lv, grand, petit, _, _ in tranches[meilleure[1]:meilleure[2] + 1]:
        gf.append(kji[sel][lv == petit])
        gt.append(kji[sel][lv == grand])
    fibula = seg.nouvelle_etiquette()
    E2.recroissance(seg, {tibia}, {tibia: np.concatenate(gt), fibula: np.concatenate(gf)})
    qf = np.argwhere(seg.etiquettes[b] == fibula) + [s.start for s in b]
    vf, vt_ = len(qf), int((seg.etiquettes == tibia).sum())
    tf = (qf * esp - c) @ vt[0] if len(qf) else np.zeros(1)
    etendue = float(np.percentile(tf, 99.5) - np.percentile(tf, 0.5))
    if not (0.02 <= vf / max(vt_, 1) <= 0.25) or etendue < 0.4 * L:
        seg.etiquettes[seg.etiquettes == fibula] = tibia      # résultat invraisemblable : on annule
        journal(f"    fibula : séparation annulée (volume {vf / max(vt_, 1):.0%} du tibia, longueur {etendue:.0f} mm)")
        return None
    journal(f"    fibula séparée du tibia (vue séparée sur {longueur:.0f} mm, {longueur / L:.0%} de la longueur) : "
            f"{vf * seg.volume_voxel / 1000:.1f} cm³")
    return fibula


# =============================================================================== points nommés par l'utilisateur
def points_par_etiquette(seg, points, journal=print):
    """{étiquette: {nom: [indices k, j, i des points]}} ; un point hors os est rattaché à l'os le plus proche
    (à moins de 3 mm), sinon ignoré."""
    groupes = {}
    esp = np.array(seg.espacement)
    for pt in points or []:
        lps = np.array(pt["position"], float)
        if str(pt.get("systeme", "LPS")).upper() == "RAS":
            lps = lps * [-1, -1, 1]
        kji = np.rint(seg.vers_indices(lps)[0]).astype(int)
        r = np.ceil(3.0 / esp).astype(int)
        lo, hi = np.maximum(kji - r, 0), np.minimum(kji + r + 1, seg.etiquettes.shape)
        if np.any(hi <= lo):
            journal(f"  ⚠ point « {pt['nom']} » hors de la zone osseuse : ignoré")
            continue
        bloc = seg.etiquettes[tuple(slice(a, b) for a, b in zip(lo, hi))]
        if not bloc.any():
            journal(f"  ⚠ point « {pt['nom']} » à plus de 3 mm de tout os : ignoré")
            continue
        q = np.argwhere(bloc > 0)
        proche = q[np.argmin(np.linalg.norm((q + lo - kji) * esp, axis=1))] + lo   # le point lui-même s'il est dans un os
        groupes.setdefault(int(seg.etiquettes[tuple(proche)]), {}).setdefault(pt["nom"], []).append(proche)
    return groupes


def separer_par_points(seg, e, par_nom, journal=print):
    """Un segment contient des points de plusieurs noms : nouvelle croissance de région à partir de boules
    (RAYON_GRAINE_MM) centrées sur les points ; une étiquette par nom. Renvoie {étiquette: nom}."""
    esp = np.array(seg.espacement)
    noms = sorted(par_nom)
    base = seg.nouvelle_etiquette()
    etiq = {n: (e if k == 0 else base + k - 1) for k, n in enumerate(noms)}
    marqueurs = {}
    for n in noms:
        q = [E2.boule(p, P.RAYON_GRAINE_MM, esp, seg.etiquettes.shape) for p in par_nom[n]]
        marqueurs[etiq[n]] = np.concatenate(q)
    E2.recroissance(seg, {e}, marqueurs)
    journal(f"  segment {e} séparé par les points de l'utilisateur : " + ", ".join(
        f"{n} ({(seg.etiquettes == etiq[n]).sum() * seg.volume_voxel / 1000:.1f} cm³)" for n in noms))
    return {v: k for k, v in etiq.items()}


# =============================================================================== identification
def identifier(seg, points=None, journal=print):
    """Nomme les segments (seg.noms) et applique les corrections anatomiques. Ordre : objets, tibia (fibula),
    fémur (sphère de la tête), genou, fibula interne, métatarses, tibia par défaut (pied seul), tarse,
    phalanges, patella et fabelles, bassin, points de l'utilisateur, côtés (deux membres)."""
    noms, raisons = seg.noms, seg.raisons

    def nommer(e, nom, raison):
        noms[e], raisons[e] = nom, raison

    def libre(e):
        return not noms.get(e)

    d = decrire(seg)
    paires = E2.contacts(seg.etiquettes, seg.espacement)
    groupes = points_par_etiquette(seg, points, journal)
    for e, par_nom in groupes.items():                    # noms imposés (un seul nom dans le segment)
        if len(par_nom) == 1:
            nommer(e, next(iter(par_nom)), "nommé par l'utilisateur")

    def jambe_():
        return [e for e in d if noms.get(e) in ("tibia", "fibula")]

    def rafraichir(*etiq):
        nonlocal paires
        presents = set(np.unique(seg.etiquettes).tolist())
        for x in etiq:
            if x and x not in presents:
                d.pop(x, None)
        d.update(decrire(seg, [x for x in etiq if x and x in presents]))
        paires = E2.contacts(seg.etiquettes, seg.espacement)

    # 1) objets non osseux : intérieur homogène et dense, et pas de cavité à remplir
    for e, x in d.items():
        if libre(e) and est_objet(x):
            plein, _ = E4.remplir(seg, [e])
            cavite = plein.sum() / max((seg.etiquettes == e).sum(), 1) - 1
            if cavite < P.CAVITE_MAX_OBJET:
                nommer(e, "objet", f"intérieur homogène ({x['hu_moyen']:.0f} HU, {x['frac_spongieux']:.0%} de voxels "
                                   f"< 600 HU) et sans cavité ({cavite:+.0%}) : fantôme ou objet, pas un os")
    os_ = [e for e in d if noms.get(e) != "objet"]
    longs = [e for e in os_ if est_os_long(d[e])]
    v_max = max([d[e]["volume_mm3"] for e in longs], default=0.0)
    v_os_max = max([d[e]["volume_mm3"] for e in os_], default=0.0)
    grands = sorted([e for e in longs if d[e]["volume_mm3"] >= 0.25 * v_max], key=lambda e: -d[e]["volume_mm3"])
    tibias, femurs = [], []

    # 2) tibia : un os long fin et parallèle (fibula) le touche
    for e in grands:
        if noms.get(e) not in ("", "tibia"):
            continue
        for f, s in voisins(paires, e).items():
            y = d.get(f)
            if (y and libre(f) and s >= 10 and y["allongement"] >= 6 and y["volume_mm3"] < 0.25 * d[e]["volume_mm3"]
                    and angle_axes(y["axes"][0], d[e]["axes"][0]) < 20 and recouvrement(d[e], y) >= 0.5):
                nommer(e, "tibia", f"os long longé par un os long fin et parallèle (fibula, segment {f})")
                nommer(f, "fibula", f"os long fin parallèle au tibia (allongement {y['allongement']:.1f})")
                tibias.append(e)
                break

    # 3) fémur : une sphère (tête fémorale) au contact d'un gros voisin (bassin)
    for e in grands:
        if noms.get(e) not in ("", "femur"):
            continue
        cand = sorted(((s, f) for f, s in voisins(paires, e).items() if f in d and noms.get(f) not in ("objet", "tibia", "fibula")
                       and s >= 100 and d[f]["volume_mm3"] >= max(0.5 * d[e]["volume_mm3"], 0.25 * v_os_max)
                       and not est_os_long(d[f])), reverse=True)
        for s, f in cand[:2]:
            journal(f"  recherche de la tête fémorale entre les segments {e} et {f} (contact {s:.0f} mm²)…")
            tete = tete_femorale(seg, e, f, journal)
            if tete:
                nommer(e, "femur", f"os long avec une tête sphérique (rayon {tete['rayon_mm']} mm) au contact du bassin")
                if libre(f):
                    nommer(f, "bassin", "gros os au contact de la tête fémorale (acétabulum)")
                seg.reperes[f"tete_femorale#{e}"] = tete
                femurs.append(e)
                rafraichir(e, f)
                break

    # 4) genou : le gros os au contact de l'extrémité large du tibia est le fémur, et inversement
    def apparier():
        for t in tibias:
            if any(noms.get(f) == "femur" for f in voisins(paires, t)):
                continue
            a, b = profil_sections(seg, t, d[t])
            large = d[t]["extremites"][int(b > a)]
            for f, s in sorted(voisins(paires, t).items(), key=lambda z: -z[1]):
                y = d.get(f)
                if (y and libre(f) and y["volume_mm3"] >= 0.3 * d[t]["volume_mm3"] and
                        np.linalg.norm(y["centre"] - large) < np.linalg.norm(y["centre"] - d[t]["extremites"][int(b <= a)])):
                    nommer(f, "femur", f"gros os au contact du plateau tibial (genou, segment {t})")
                    femurs.append(f)
                    break
        for fe in femurs:
            if any(noms.get(t) == "tibia" for t in voisins(paires, fe)):
                continue
            for t, s in sorted(voisins(paires, fe).items(), key=lambda z: -z[1]):
                if t in grands and libre(t):
                    nommer(t, "tibia", f"os long au contact du fémur au genou (segment {fe})")
                    tibias.append(t)
                    break
    apparier()

    # 5) fibula collée au tibia (détectée sur des tranches)
    candidats = tibias or [e for e in grands[:1] if libre(e)]      # sans tibia reconnu : le plus gros os long seulement
    for e in candidats:
        if any(noms.get(f) == "fibula" for f in voisins(paires, e)):
            continue
        fib = separer_fibula(seg, e, d[e], journal)
        if fib:
            if libre(e):
                nommer(e, "tibia", "os long dont on a séparé la fibula (petite tache parallèle sur les coupes)")
                tibias.append(e)
            nommer(fib, "fibula", "petite tache parallèle au tibia sur les coupes, prolongée par croissance de région")
            rafraichir(e, fib)
            break
    apparier()

    # 5 bis) un segment allongé qui touche la jambe n'est pas un métatarse pur (un métatarse ne touche jamais le
    #        tibia) : c'est sans doute un talus soudé à un rayon du pied -> re-découpage plus fin
    for e in [f for t in jambe_() for f, s in voisins(paires, t).items() if s >= 50]:
        if e in d and libre(e) and d[e]["allongement"] >= P.ALLONGEMENT_COMPACT and not est_objet(d[e]):
            morceaux = E2.raffiner(seg, e, journal)
            if len(morceaux) > 1:
                rafraichir(*morceaux)
                os_ += [x for x in morceaux if x not in os_]

    # 6) métatarses : au moins 3 os longs, fins, parallèles et voisins
    mt = [e for e in os_ if libre(e) and d[e]["allongement"] >= 4.5 and d[e]["longueurs"][0] >= 40
          and d[e]["volume_mm3"] >= P.VOLUME_MIN_NOMME_MM3]
    groupe = []
    for e in mt:
        g = [f for f in mt if angle_axes(d[f]["axes"][0], d[e]["axes"][0]) < 25
             and np.linalg.norm(d[f]["centre"] - d[e]["centre"]) < 0.8 * d[e]["longueurs"][0]]
        if len(g) > len(groupe):
            groupe = g
    if len(groupe) >= 3:
        for e in groupe:
            nommer(e, "metatarses", f"os long fin, parallèle à {len(groupe) - 1} autres (rayons du pied)")

    # 7) pied seul : le tibia est le gros os au-dessus du tarse (à 2 contacts au plus des métatarses)
    if not tibias and groupe:
        v_mt = np.mean([d[e]["volume_mm3"] for e in groupe])
        proches = {f for e in groupe for f in voisins(paires, e) if libre(f) and est_compact(d[f])}
        for e in sorted(os_, key=lambda z: -d[z]["volume_mm3"]):
            if libre(e) and d[e]["volume_mm3"] >= 2 * v_mt and not set(voisins(paires, e)) & set(groupe):
                if any(f in proches or set(voisins(paires, f)) & proches for f in voisins(paires, e)):
                    nommer(e, "tibia", "gros os au-dessus du tarse (le champ du scanner le coupe)")
                    tibias.append(e)
                    break

    # 8) tarse : os compacts reliés au bout distal du tibia (ou de la fibula), jusqu'aux métatarses
    jambe = [e for e in d if noms.get(e) in ("tibia", "fibula")]
    tarse, a_voir = [], [f for e in jambe for f, s in voisins(paires, e).items() if s >= 20]
    while a_voir:
        f = a_voir.pop()
        if f in tarse or f not in d or not libre(f) or not est_compact(d[f]) or d[f]["volume_mm3"] < P.VOLUME_MIN_NOMME_MM3:
            continue
        if any(noms.get(g) == "femur" for g in voisins(paires, f)):
            continue                                          # au contact du fémur : patella ou fabelle
        tarse.append(f)
        a_voir += [g for g, s in voisins(paires, f).items() if s >= 20]
    if tarse:
        contact_tibia = {f: sum(s for g, s in voisins(paires, f).items() if noms.get(g) == "tibia") for f in tarse}
        talus = max(tarse, key=lambda f: contact_tibia[f])
        if contact_tibia[talus] > 0:
            nommer(talus, "talus", "os du tarse au plus grand contact avec le tibia (articulation tarso-crurale)")
        reste = [f for f in tarse if libre(f)]
        if len(reste) >= 1:
            L = {f: d[f]["longueurs"][0] for f in reste}
            calc = max(reste, key=lambda f: L[f])
            if L[calc] >= 1.4 * np.median([d[f]["longueurs"][0] for f in tarse]):
                nommer(calc, "calcaneus", f"os du tarse le plus long ({L[calc]:.0f} mm : tubérosité calcanéenne)")
        for f in tarse:
            if libre(f):
                nommer(f, "tarse", "os compact du tarse (entre tibia et métatarses)")

    # 9) phalanges : au-delà des métatarses
    a_voir = [f for e in groupe for f in voisins(paires, e)]
    while a_voir:
        f = a_voir.pop()
        if f in d and libre(f) and d[f]["volume_mm3"] >= P.VOLUME_MIN_NOMME_MM3:
            nommer(f, "phalanges", "au-delà des métatarses (doigts)")
            a_voir += list(voisins(paires, f))

    # 10) patella et fabelles : petits os compacts au contact du fémur (hors tibia, fibula, bassin)
    for fe in [e for e in d if noms.get(e) == "femur"]:
        petits = sorted([f for f, s in voisins(paires, fe).items() if f in d and libre(f) and s >= 5
                         and d[f]["allongement"] < 2.5 and 0.005 <= d[f]["volume_mm3"] / d[fe]["volume_mm3"] <= 0.1],
                        key=lambda f: -d[f]["volume_mm3"])
        if petits:
            nommer(petits[0], "patella", "petit os compact au contact du fémur (le plus gros)")
            for f in petits[1:]:
                nommer(f, "fabelles", "petit os compact au contact du fémur")

    # 10 bis) fabelles collées au fémur : raffinement du fémur ; seuls les petits morceaux compacts et peu en contact
    #         (c* < CSTAR_MAX_SESAMOIDE) deviennent des fabelles, tout autre morceau est rendu au fémur
    for fe in [e for e in d if base_nom(noms.get(e)) == "femur"]:
        v_fe = float((seg.etiquettes == fe).sum()) * seg.volume_voxel
        morceaux = E2.raffiner(seg, fe, lambda *a: None, finesse=3)
        if len(morceaux) < 2:
            continue
        paires_f = E2.contacts(seg.etiquettes, seg.espacement)
        dd = decrire(seg, morceaux[1:])
        for m in morceaux[1:]:
            x = dd.get(m)
            c = voisins(paires_f, m).get(fe, 0.0)
            if (x and x["volume_mm3"] < P.FRACTION_MAX_SESAMOIDE * v_fe and x["allongement"] < 2.5
                    and c / x["volume_mm3"] ** (2 / 3) < P.CSTAR_MAX_SESAMOIDE):
                nommer(m, "fabelles", f"petit os compact accolé au fémur (contact {c:.0f} mm², c* = "
                                      f"{c / x['volume_mm3'] ** (2 / 3):.2f}) : sésamoïde du gastrocnémien")
                journal(f"    fabelle détachée du fémur : {x['volume_mm3'] / 1000:.2f} cm³")
            else:
                seg.etiquettes[seg.etiquettes == m] = fe
        rafraichir(fe, *morceaux[1:])

    # 11) bassin : gros os reliés à l'acétabulum par de larges contacts
    a_voir = [e for e in d if noms.get(e) == "bassin"]
    while a_voir:
        e = a_voir.pop()
        for f, s in voisins(paires, e).items():
            if f in d and libre(f) and s >= 100 and not est_os_long(d[f]):
                nommer(f, "bassin", "relié au bassin par un large contact (os coxal, sacrum, vertèbre)")
                a_voir.append(f)

    # 12) points de l'utilisateur dans un segment qui contient plusieurs noms : séparation
    for e, par_nom in points_par_etiquette(seg, points, lambda *a: None).items():
        if len(par_nom) >= 2:
            for f, n in separer_par_points(seg, e, par_nom, journal).items():
                nommer(f, n, "séparé et nommé par l'utilisateur")

    # 12 bis) morceaux détachés d'un os nommé : rendus à l'os dont ils ont été découpés (c* ≥ 3), sinon segment à part
    nettoyer_morceaux(seg, journal)

    # 13) deux membres : suffixe de côté (LPS : x croissant = gauche du patient)
    nommer_cotes(seg, journal)
    for k in [k for k in seg.reperes if k.startswith("tete_femorale#")]:
        n = seg.noms.get(int(k.split("#")[1]), "femur")
        seg.reperes["tete_femorale" + (n[len("femur"):] if n.startswith("femur") else "")] = seg.reperes.pop(k)
    for e in list(noms):
        if not (seg.etiquettes == e).any():
            del noms[e]
            raisons.pop(e, None)
    for e in d:
        noms.setdefault(e, "")
    resume = {}
    for e, n in noms.items():
        resume[n or "autre"] = resume.get(n or "autre", 0) + 1
    journal("  os reconnus : " + ", ".join(f"{P.NOMS_OS.get(n.split('_')[0], n)}{'' if '_' not in n else ' ' + n.split('_', 1)[1]}"
                                         f"{f' ×{c}' if c > 1 else ''}" for n, c in sorted(resume.items()) if n != "autre")
            + (f" ; {resume['autre']} autre(s) segment(s) non nommé(s)" if "autre" in resume else ""))
    return seg


def nettoyer_morceaux(seg, journal=print):
    """Un os nommé (hors groupes : bassin, métatarses, phalanges) doit être d'un seul tenant. Chaque morceau
    détaché (composante 26-connexe autre que la plus grosse) est rendu au voisin dont il a été découpé s'il le
    touche sur toute une section (c* ≥ RAPPORT_CONTACT_FUSION) ; sinon il devient un segment non nommé (un
    sésamoïde, par exemple) ; un morceau minuscule va au voisin de plus grand contact."""
    groupes = {"bassin", "metatarses", "phalanges", "tarse", "objet", "autre", ""}
    vox = seg.volume_voxel
    for e, n in list(seg.noms.items()):
        if base_nom(n) in groupes:
            continue
        m = seg.etiquettes == e
        if not m.any():
            continue
        b = E2.boite_englobante(m)
        b = tuple(slice(max(s.start - 2, 0), s.stop + 2) for s in b)
        lab, k = ndi.label(m[b], np.ones((3, 3, 3), bool))
        if k < 2:
            continue
        taille = np.bincount(lab.ravel())
        taille[0] = 0
        principal = int(np.argmax(taille))
        bloc = seg.etiquettes[b]
        for c in range(1, k + 1):
            if c == principal:
                continue
            morceau = lab == c
            autour = ndi.binary_dilation(morceau, np.ones((3, 3, 3), bool)) & ~morceau
            voisins_ = {int(x): int(nb) for x, nb in zip(*np.unique(bloc[autour], return_counts=True)) if x and x != e}
            v = float(taille[c]) * vox
            aire = {x: nb * float(np.mean(seg.espacement[1:]) * seg.espacement[0]) for x, nb in voisins_.items()}
            cible = max(aire, key=aire.get) if aire else None
            if v < P.VOLUME_MIN_SEGMENT_MM3:
                if cible:
                    bloc[morceau] = cible
            elif cible and aire[cible] / v ** (2 / 3) >= P.RAPPORT_CONTACT_FUSION:
                bloc[morceau] = cible
                journal(f"    {v / 1000:.2f} cm³ détachés de « {n} » rendus à « {seg.noms.get(cible) or cible} » (c* = "
                        f"{aire[cible] / v ** (2 / 3):.1f})")
            else:
                nouvelle = seg.nouvelle_etiquette()
                bloc[morceau] = nouvelle
                seg.noms[nouvelle] = ""
                seg.raisons[nouvelle] = f"morceau détaché de « {n} » (sésamoïde ?)"
                journal(f"    {v / 1000:.2f} cm³ détachés de « {n} » : segment séparé ({nouvelle})")
        seg.etiquettes[b] = bloc


def nommer_cotes(seg, journal=print):
    """S'il y a deux fémurs ou deux tibias (CT des deux membres), chaque os du membre reçoit _gauche ou _droit
    selon sa position (repère LPS du scanner : +x = gauche du patient ; à vérifier si l'animal n'était pas
    enregistré dans la bonne position sur la console)."""
    d = {e: n for e, n in seg.noms.items() if n}
    ancres = [e for e, n in d.items() if n in ("femur", "tibia")]
    par_nom = {}
    for e in ancres:
        par_nom.setdefault(d[e], []).append(e)
    if not any(len(v) == 2 for v in par_nom.values()):
        return
    centres = {e: seg.vers_lps(np.argwhere(seg.etiquettes == e).mean(0))[0] for e in d}
    x_milieu = np.mean([centres[e][0] for e in ancres])
    membre = ("femur", "tibia", "fibula", "patella", "fabelles", "talus", "calcaneus", "tarse", "metatarses", "phalanges")
    for e, n in d.items():
        if n in membre:
            seg.noms[e] = f"{n}_{'gauche' if centres[e][0] > x_milieu else 'droit'}"
    journal("  deux membres détectés : côtés attribués d'après la coordonnée x (LPS), à vérifier")
