"""
etape2_segmentation.py — seuillage + croissance de région : sépare chaque os du volume CT.

Rôle    : (1) recadrer le volume autour des os et le lisser légèrement (bruit) ;
          (2) seuiller l'os (≥ SEUIL_OS_HU) : c'est le « masque osseux » ;
          (3) trouver une GRAINE par os : on monte le seuil palier par palier (500 → 1500 HU) ; quand un bloc dense
              se coupe en morceaux qui persistent, chaque morceau devient une graine (les interlignes articulaires,
              moins denses, cèdent avant l'os) ;
          (4) CROISSANCE DE RÉGION compétitive : toutes les graines grandissent en même temps dans le masque
              osseux, chacune par ses voxels les plus denses d'abord (ligne de partage des eaux de SimpleITK sur
              l'intensité inversée) ; deux os se rencontrent dans la zone la moins dense, l'interligne ;
          (5) FUSION des sur-découpages (un même os coupé en deux, reconnu à son contact sur toute la section).
          Outils pour l'étape 3 : nouvelle croissance dans une zone avec des graines imposées (sphère de la tête
          fémorale, fibula, points de l'utilisateur).
Entrées : Volume de l'étape 1.
Sorties : objet Segmentation (en mémoire) : une étiquette entière par os dans la zone recadrée.
"""
import time
from dataclasses import dataclass, field

import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi

import parametres as P

S26 = np.ones((3, 3, 3), bool)                   # voisinage 3D complet (26 voisins)


def boite_englobante(m):
    """Boîte englobante (tuple de 3 tranches) d'un masque booléen 3D non vide : le même résultat que
    ndi.find_objects(m.astype(np.uint8))[0], ≈ 50 fois plus vite (mesuré : 2 ms au lieu de 120 ms sur 72 M voxels),
    car sans copie du volume : une projection np.any sur le premier axe, puis une seconde sur la seule boîte (j, i)."""
    p = m.any(axis=0)
    j, i = np.flatnonzero(p.any(axis=1)), np.flatnonzero(p.any(axis=0))
    k = np.flatnonzero(m[:, j[0]:j[-1] + 1, i[0]:i[-1] + 1].any(axis=(1, 2)))
    return slice(int(k[0]), int(k[-1]) + 1), slice(int(j[0]), int(j[-1]) + 1), slice(int(i[0]), int(i[-1]) + 1)


@dataclass
class Segmentation:
    etiquettes: np.ndarray                       # uint16 (k, j, i), 0 = pas d'os ; zone recadrée
    image: np.ndarray                            # int16 : HU lissés, même zone
    origine_kji: tuple                           # coin de la zone recadrée dans le volume complet
    forme_volume: tuple                          # taille du volume complet
    espacement: tuple                            # (dk, dj, di) en mm
    affine: np.ndarray                           # 4 × 4 de la zone recadrée : [i, j, k, 1] -> LPS (mm)
    noms: dict = field(default_factory=dict)     # étiquette -> nom d'os ("" : pas nommé)
    raisons: dict = field(default_factory=dict)  # étiquette -> justification du nom
    reperes: dict = field(default_factory=dict)  # repères obtenus en chemin (tête fémorale…)
    avertissements: list = field(default_factory=list)
    duree_s: dict = field(default_factory=dict)

    @property
    def volume_voxel(self):
        return float(np.prod(self.espacement))

    def vers_lps(self, kji):
        kji = np.atleast_2d(np.asarray(kji, float))
        return kji[:, ::-1] @ self.affine[:3, :3].T + self.affine[:3, 3]

    def vers_indices(self, lps):
        lps = np.atleast_2d(np.asarray(lps, float))
        return (np.linalg.solve(self.affine[:3, :3], (lps - self.affine[:3, 3]).T).T)[:, ::-1]

    def nouvelle_etiquette(self):
        return int(self.etiquettes.max()) + 1


# =============================================================================== briques
def recadrage(hu, espacement):
    """Boîte englobant les os denses (≥ SEUIL_GRAINE_DEPART_HU), calculée sur un volume 2 × plus petit : la
    table du scanner et les tissus mous en sont exclus, et la mémoire nécessaire est divisée par ~5."""
    petit = hu[::2, ::2, ::2] >= P.SEUIL_GRAINE_DEPART_HU
    lab, n = ndi.label(petit, S26)
    taille = np.bincount(lab.ravel())
    taille[0] = 0
    v8 = 8 * float(np.prod(espacement))
    garde = np.nonzero(taille * v8 >= P.VOLUME_MIN_GRAINE_MM3)[0]
    if len(garde) == 0:
        raise ValueError(f"aucun os trouvé : aucune zone ≥ {P.SEUIL_GRAINE_DEPART_HU} HU (est-ce bien un scanner ?)")
    boites = ndi.find_objects(lab)
    lo = np.min([[boites[g - 1][a].start for a in range(3)] for g in garde], axis=0) * 2
    hi = np.max([[boites[g - 1][a].stop for a in range(3)] for g in garde], axis=0) * 2
    marge = np.ceil(P.MARGE_RECADRAGE_MM / np.array(espacement)).astype(int)
    lo = np.maximum(lo - marge, 0)
    hi = np.minimum(hi + marge, hu.shape)
    return tuple(int(x) for x in lo), tuple(int(x) for x in hi)


def lisser(hu, espacement, sigma_mm=None):
    """Flou gaussien (sigma en mm, donc identique dans les 3 directions malgré des voxels non cubiques)."""
    img = sitk.GetImageFromArray(hu.astype(np.float32))
    img.SetSpacing(tuple(float(s) for s in espacement[::-1]))
    out = sitk.GetArrayFromImage(sitk.SmoothingRecursiveGaussian(img, sigma_mm or P.SIGMA_LISSAGE_MM))
    return np.clip(np.rint(out), -32768, 32767).astype(np.int16)


def graines_automatiques(I, espacement, volume_morceau_mm3=None, persistance_hu=None):
    """Une graine par os : composantes connexes d'un seuil qui monte palier par palier (arbre des seuils).
    Un bloc est coupé quand, à un palier, il donne au moins deux morceaux assez gros (VOLUME_MIN_MORCEAU_MM3)
    qui existent encore PERSISTANCE_HU plus haut ; chaque morceau est ensuite examiné aux paliers suivants.
    Les deux réglages peuvent être assouplis pour raffiner un segment (étape 3)."""
    vox = float(np.prod(espacement))
    persistance = persistance_hu or P.PERSISTANCE_HU
    paliers = list(range(P.SEUIL_GRAINE_DEPART_HU + P.PAS_SEUIL_HU, P.SEUIL_GRAINE_MAX_HU + 1, P.PAS_SEUIL_HU))
    v_morceau = (volume_morceau_mm3 or P.VOLUME_MIN_MORCEAU_MM3) / vox
    v_persist, v_graine = P.VOLUME_PERSISTANCE_MM3 / vox, P.VOLUME_MIN_GRAINE_MM3 / vox

    def couper(region, boite, seuil):
        s = I[boite]
        for palier in paliers:
            if palier <= seuil:
                continue
            lab, n = ndi.label((s >= palier) & region, S26)
            if n < 2:
                continue
            taille = np.bincount(lab.ravel())
            taille[0] = 0
            candidats = np.nonzero(taille >= v_morceau)[0]
            if len(candidats) < 2:
                continue
            haut = s >= palier + persistance
            retenus = [c for c in candidats if np.count_nonzero(haut[lab == c]) >= v_persist]
            if len(retenus) >= 2:
                morceaux, boites = [], ndi.find_objects(lab)
                for c in retenus:
                    b = boites[c - 1]
                    globale = tuple(slice(boite[a].start + b[a].start, boite[a].start + b[a].stop) for a in range(3))
                    morceaux += couper(lab[b] == c, globale, palier)
                return morceaux
        return [(region, boite)]

    lab0, _ = ndi.label(I >= P.SEUIL_GRAINE_DEPART_HU, S26)
    taille = np.bincount(lab0.ravel())
    taille[0] = 0
    boites = ndi.find_objects(lab0)
    graines = np.zeros(I.shape, np.uint16)
    n = 0
    for c in np.nonzero(taille >= v_graine)[0]:
        b = boites[c - 1]
        for region, boite in couper(lab0[b] == c, b, P.SEUIL_GRAINE_DEPART_HU):
            n += 1
            graines[boite][region] = n
    return graines, n


def croissance(I, marqueurs, masque, avec_fond=True):
    """Croissance de région compétitive : ligne de partage des eaux à partir de marqueurs (SimpleITK) sur
    l'intensité inversée, limitée au masque. Chaque marqueur avance d'abord dans les voxels les plus denses ;
    deux os se rencontrent là où la densité est la plus faible, c'est-à-dire dans l'interligne.
    avec_fond=True : le fond (hors masque, peu dense) est un marqueur concurrent (segmentation complète).
    avec_fond=False : hors du masque, le relief est maximal et personne n'y part ; les seuls concurrents sont
    les marqueurs donnés (re-croissance d'une zone entourée d'autres os, denses, qui ne doivent pas l'envahir)."""
    relief = np.clip(3000 - I.astype(np.int32), 0, 4500).astype(np.uint16)
    m = marqueurs.astype(np.uint16, copy=True)
    fond = int(m.max()) + 1
    if avec_fond:
        m[(~masque) & (m == 0)] = fond                   # le « fond » (hors os) est aussi un marqueur
    else:
        relief[~masque] = np.iinfo(np.uint16).max
    ws = sitk.MorphologicalWatershedFromMarkers(sitk.GetImageFromArray(relief), sitk.GetImageFromArray(m),
                                                markWatershedLine=False, fullyConnected=True)
    lab = sitk.GetArrayFromImage(ws).astype(np.uint16)
    lab[~masque] = 0
    lab[lab == fond] = 0
    return lab


def contacts(etiquettes, espacement):
    """Surface de contact (mm²) entre chaque paire d'étiquettes voisines (faces de voxels partagées)."""
    dk, dj, di = espacement
    paires = {}
    for axe, aire in zip(range(3), (dj * di, dk * di, dk * dj)):
        a = np.moveaxis(etiquettes, axe, 0)
        e1, e2 = a[:-1], a[1:]
        m = (e1 != e2) & (e1 > 0) & (e2 > 0)
        if not m.any():
            continue
        cles = np.stack([np.minimum(e1[m], e2[m]), np.maximum(e1[m], e2[m])], 1)
        uniques, nb = np.unique(cles, axis=0, return_counts=True)
        for (x, y), c in zip(uniques, nb):
            paires[(int(x), int(y))] = paires.get((int(x), int(y)), 0.0) + float(c) * aire
    return paires


def fusionner_surdecoupages(etiquettes, espacement, proteges=None, journal=print):
    """Recolle les morceaux d'un même os : contact / V_min^(2/3) ≥ RAPPORT_CONTACT_FUSION. Calcul fait sur le
    tableau des contacts (quand A et B fusionnent, contact(A∪B, C) = contact(A, C) + contact(B, C) exactement).
    Deux étiquettes « protégées » de noms différents ne sont jamais fusionnées."""
    proteges = dict(proteges or {})
    vox = float(np.prod(espacement))
    vol = np.bincount(etiquettes.ravel()).astype(float) * vox
    paires = contacts(etiquettes, espacement)
    parent = {}

    def racine(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    fusions = []
    while True:
        meilleur = None
        for (a, b), aire in paires.items():
            if proteges.get(a) and proteges.get(b) and proteges[a] != proteges[b]:
                continue
            c = aire / min(vol[a], vol[b]) ** (2 / 3)
            if c >= P.RAPPORT_CONTACT_FUSION and (meilleur is None or c > meilleur[0]):
                meilleur = (c, a, b)
        if meilleur is None:
            break
        c, a, b = meilleur
        if bool(proteges.get(a)) != bool(proteges.get(b)):       # on garde l'étiquette qui porte un nom imposé
            garde, enleve = (a, b) if proteges.get(a) else (b, a)
        else:                                                    # sinon la plus volumineuse
            garde, enleve = (a, b) if vol[a] >= vol[b] else (b, a)
        parent[enleve] = garde
        vol[garde] += vol[enleve]
        if enleve in proteges and garde not in proteges:
            proteges[garde] = proteges[enleve]
        nouvelles = {}
        for (x, y), aire in paires.items():
            x2, y2 = (garde if x == enleve else x), (garde if y == enleve else y)
            if x2 != y2:
                cle = (min(x2, y2), max(x2, y2))
                nouvelles[cle] = nouvelles.get(cle, 0.0) + aire
        paires = nouvelles
        fusions.append((enleve, garde, round(c, 2)))
    if fusions:
        table = np.arange(int(etiquettes.max()) + 1, dtype=np.uint16)
        for x in range(len(table)):
            table[x] = racine(x)
        etiquettes = table[etiquettes]
        journal(f"  {len(fusions)} os recollé(s) (même os coupé en deux, c* ≥ {P.RAPPORT_CONTACT_FUSION}) : "
                + ", ".join(f"{a}→{b} (c*={c})" for a, b, c in fusions))
    return etiquettes


def nettoyer(etiquettes, espacement):
    """Segments trop petits : rattachés au voisin de plus grand contact, ou supprimés s'ils sont isolés ;
    puis renumérotation 1, 2, 3… par volume décroissant."""
    vox = float(np.prod(espacement))
    taille = np.bincount(etiquettes.ravel())
    petits = [e for e in np.nonzero(taille)[0] if e and taille[e] * vox < P.VOLUME_MIN_SEGMENT_MM3]
    if petits:
        paires = contacts(etiquettes, espacement)
        table = np.arange(len(taille), dtype=np.uint16)
        for e in petits:
            voisins = [(aire, b if a == e else a) for (a, b), aire in paires.items() if e in (a, b) and (b if a == e else a) not in petits]
            table[e] = max(voisins)[1] if voisins else 0
        etiquettes = table[etiquettes]
        taille = np.bincount(etiquettes.ravel(), minlength=len(taille))
    ordre = [e for e in np.argsort(taille)[::-1] if e and taille[e] > 0]
    table = np.zeros(len(taille), np.uint16)
    for n, e in enumerate(ordre, 1):
        table[e] = n
    return table[etiquettes]


def boule(centre_kji, rayon_mm, espacement, forme, rayon_min_mm=None):
    """Indices (N × 3 : k, j, i) des voxels d'une boule (ou d'une coquille si rayon_min_mm), dans la grille."""
    c = np.asarray(centre_kji, float)
    r = np.ceil(rayon_mm / np.asarray(espacement)).astype(int) + 1
    lo = np.maximum(np.floor(c).astype(int) - r, 0)
    hi = np.minimum(np.floor(c).astype(int) + r + 1, forme)
    if np.any(hi <= lo):
        return np.zeros((0, 3), int)
    k, j, i = (np.arange(lo[a], hi[a]) - c[a] for a in range(3))
    d2 = ((k[:, None, None] * espacement[0]) ** 2 + (j[None, :, None] * espacement[1]) ** 2
          + (i[None, None, :] * espacement[2]) ** 2)
    m = d2 <= rayon_mm ** 2
    if rayon_min_mm is not None:
        m &= d2 >= rayon_min_mm ** 2
    return np.argwhere(m) + lo


def recroissance(seg, etiquettes_zone, marqueurs, marge=3):
    """Nouvelle croissance de région limitée à une zone (union des étiquettes données), à partir de graines
    imposées : {étiquette finale: indices (N × 3) des voxels de sa graine}. La zone est entièrement redistribuée."""
    zone = np.isin(seg.etiquettes, list(etiquettes_zone))
    b = boite_englobante(zone)
    b = tuple(slice(max(s.start - marge, 0), min(s.stop + marge, n)) for s, n in zip(b, zone.shape))
    z = zone[b]
    m = np.zeros(z.shape, np.uint16)
    finales = sorted(marqueurs)
    origine = np.array([s.start for s in b])
    for n, e in enumerate(finales, 1):
        q = np.asarray(marqueurs[e], int).reshape(-1, 3) - origine
        q = q[np.all((q >= 0) & (q < z.shape), axis=1)]
        q = q[z[tuple(q.T)]]
        m[tuple(q.T)] = n
    lab = croissance(seg.image[b], m, z, avec_fond=False)
    sortie = seg.etiquettes[b].copy()
    sortie[z] = 0
    for n, e in enumerate(finales, 1):
        sortie[lab == n] = e
    seg.etiquettes[b] = sortie


def raffiner(seg, e, journal=print, finesse=2):
    """Re-découpe un segment qui contient sans doute plusieurs os (ex. talus soudé à un métatarse, fabelle collée
    au fémur) : graines plus fines (taille minimale et persistance divisées par `finesse`) cherchées dans ce seul
    segment, croissance de région, puis recollage des sur-découpages. Renvoie les étiquettes (la première est e)."""
    m = seg.etiquettes == e
    b = boite_englobante(m)
    I = np.where(m[b], seg.image[b], np.int16(-1000))
    graines, n = graines_automatiques(I, seg.espacement, P.VOLUME_MIN_MORCEAU_MM3 / finesse, P.PERSISTANCE_HU // finesse)
    if n < 2:
        return [e]
    lab = croissance(I, graines, m[b])
    lab = nettoyer(fusionner_surdecoupages(lab, seg.espacement, journal=lambda *a: None), seg.espacement)
    restants = [int(x) for x in np.unique(lab) if x]
    if len(restants) < 2:
        return [e]
    base = seg.nouvelle_etiquette()
    sortie = seg.etiquettes[b].copy()
    nouvelles = [e] + [base + k for k in range(len(restants) - 1)]
    taille = {x: int((lab == x).sum()) for x in restants}
    for x, nv in zip(sorted(restants, key=lambda z: -taille[z]), nouvelles):
        sortie[lab == x] = nv
    sortie[m[b] & (lab == 0)] = e
    seg.etiquettes[b] = sortie
    journal(f"    segment {e} raffiné en {len(nouvelles)} os : " + ", ".join(
        f"{(seg.etiquettes == x).sum() * seg.volume_voxel / 1000:.1f} cm³" for x in nouvelles))
    return nouvelles


def depuis_fichier(volume, etiquettes, origine_lps, noms):
    """Reconstruit une Segmentation à partir d'un fichier relu (segmentation.seg.nrrd) : permet de corriger un
    résultat dans l'application sans relancer la segmentation."""
    coin = np.rint(volume.vers_indices(origine_lps)[0]).astype(int)
    if np.any(coin < 0) or np.any(coin + etiquettes.shape > np.array(volume.hu.shape)):
        raise ValueError("la segmentation enregistrée ne correspond pas à ce volume")
    boite = tuple(slice(int(a), int(a) + n) for a, n in zip(coin, etiquettes.shape))
    affine = volume.affine.copy()
    affine[:3, 3] = volume.affine[:3, :3] @ np.array(coin[::-1], float) + volume.affine[:3, 3]
    seg = Segmentation(etiquettes=etiquettes.copy(), image=lisser(volume.hu[boite], volume.espacement),
                       origine_kji=tuple(int(x) for x in coin), forme_volume=volume.hu.shape,
                       espacement=volume.espacement, affine=affine)
    seg.noms = {int(e): noms.get(int(e), "") for e in np.unique(etiquettes) if e}
    return seg


# =============================================================================== chaîne complète
def segmenter(volume, journal=print):
    """Étapes (1) à (5) : du volume en HU à un os par étiquette (sans les noms : étape 3)."""
    t = {"debut": time.time()}
    esp = volume.espacement
    lo, hi = recadrage(volume.hu, esp)
    boite = tuple(slice(a, b) for a, b in zip(lo, hi))
    journal(f"  zone utile : {hi[0]-lo[0]} × {hi[1]-lo[1]} × {hi[2]-lo[2]} voxels "
            f"({np.prod(np.subtract(hi, lo)) / np.prod(volume.hu.shape) * 100:.0f} % du volume)")
    I = lisser(volume.hu[boite], esp)
    t["lissage"] = time.time()
    masque = I >= P.SEUIL_OS_HU
    graines, n = graines_automatiques(I, esp)
    t["graines"] = time.time()
    journal(f"  {n} graines automatiques (noyaux denses, seuils {P.SEUIL_GRAINE_DEPART_HU} à {P.SEUIL_GRAINE_MAX_HU} HU)")
    etiquettes = croissance(I, graines, masque)
    del graines
    t["croissance"] = time.time()
    etiquettes = fusionner_surdecoupages(etiquettes, esp, journal=journal)
    etiquettes = nettoyer(etiquettes, esp)
    t["fusion"] = time.time()
    affine = volume.affine.copy()
    affine[:3, 3] = volume.affine[:3, :3] @ np.array(lo[::-1], float) + volume.affine[:3, 3]
    seg = Segmentation(etiquettes=etiquettes, image=I, origine_kji=lo, forme_volume=volume.hu.shape, espacement=esp,
                       affine=affine)
    seg.noms = {int(e): "" for e in np.unique(etiquettes) if e}
    cles = ["debut", "lissage", "graines", "croissance", "fusion"]
    seg.duree_s = {k: round(t[k] - t[p], 1) for p, k in zip(cles, cles[1:])}
    journal(f"  {len(seg.noms)} segments osseux (os ou groupes d'os) en {t['fusion'] - t['debut']:.0f} s")
    return seg
