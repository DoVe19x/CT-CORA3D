"""
etape6_reperes.py — repères anatomiques automatiques sur le fémur et le tibia segmentés (lien CT → CORA 3D).

Rôle    : à partir du STL d'un fémur ou d'un tibia (coordonnées du scanner), construire le repère de l'os (X latéral,
          Y proximal, Z caudal, comme CORA 3D), reconnaître le côté (droit / gauche, d'après l'anatomie), vérifier que
          l'os est complet (une extrémité coupée par le champ du scanner rend la méthode CORA impossible), puis placer
          les repères utilisés par CORA 3D, avec les mêmes définitions :
            tibia : éminence intercondylaire, centres des plateaux médial et latéral, bords crânial et caudal du
                    plateau médial (pente), sillons médial et latéral de la cochlée, crête intermédiaire (centre
                    distal), bords crânial et caudal de la surface articulaire distale, points caudaux des condyles,
                    malléoles, tubérosité ; tête et malléole de la fibula si son STL existe ;
            fémur : centre de la tête (sphère), sommet du grand trochanter, centre du col, points distaux et caudaux
                    des condyles (tangentes communes), centres des condyles (sphères), épicondyles, sillon de la
                    trochlée (fond, aux niveaux proximal et distal).
Entrées : resultats/<série>/femur.stl, tibia.stl (et fibula.stl, reperes_auto.mrk.json s'ils existent).
Sorties : resultats/<série>/cora_<os>.json (repère, côté, complétude, repères dans le repère de l'os et dans celui du
          scanner, ligne centrale, contrôles) et cora_<os>.png (repères sur les trois vues).

Méthode (détails dans code_source/README.md) : axe long par analyse en composantes principales, puis repère
anatomique affiné en trois passes (tibia : axe mécanique éminence → centre distal ; fémur : axe anatomique, milieux de
la diaphyse à 1/3 et 1/2 ; X : axe caudal des condyles). Les repères sont des points de la surface : extrêmes dans une
direction, tangentes communes (enveloppe convexe 2D, comme la règle posée sur la radiographie), sphères ajustées
(moindres carrés robustes), régions articulaires obtenues par croissance de région sur le maillage (normales).

Usage :
    python etape6_reperes.py ../resultats/greyhound_hindlimb_hip_to_knee          # fémur et tibia complets du dossier
    python etape6_reperes.py ../resultats/<série> --os tibia
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import ConvexHull, cKDTree

import parametres as P

VERSION = "cora-reel-1"
NOMS = {
    "head_center": "centre de la tête fémorale", "gt_tip": "sommet du grand trochanter", "neck_base": "centre du col",
    "cond_med_dist": "point distal du condyle médial", "cond_lat_dist": "point distal du condyle latéral",
    "cond_med_caud": "point caudal du condyle médial", "cond_lat_caud": "point caudal du condyle latéral",
    "cond_med_center": "centre du condyle médial", "cond_lat_center": "centre du condyle latéral",
    "epi_med": "épicondyle médial", "epi_lat": "épicondyle latéral",
    "troch_prox": "fond de la trochlée (proximal)", "troch_dist": "fond de la trochlée (distal)",
    "eminence": "éminence intercondylaire", "plat_med": "centre du plateau médial", "plat_lat": "centre du plateau latéral",
    "plat_cran": "bord crânial du plateau médial", "plat_caud": "bord caudal du plateau médial",
    "caud_med": "point caudal du condyle tibial médial", "caud_lat": "point caudal du condyle tibial latéral",
    "tuberosity": "tubérosité tibiale", "groove_med": "sillon médial de la cochlée", "groove_lat": "sillon latéral de la cochlée",
    "distal_center": "crête intermédiaire (centre distal)", "dist_cran": "bord crânial de la surface distale",
    "dist_caud": "bord caudal de la surface distale", "mall_med": "malléole médiale", "mall_lat": "malléole latérale",
    "fib_head": "tête de la fibula",
    "lt_tip": "petit trochanter", "neck_base_lt": "base du col (niveau du petit trochanter)",
    "fem_axe_13": "axe anatomique (milieu à 1/3)", "fem_axe_12": "axe anatomique (milieu à 1/2)",
    "ant_med": "saillie crâniale distale médiale (axe antécochléaire)",
    "ant_lat": "saillie crâniale distale latérale (axe antécochléaire)",
    "tib_shaft_prox": "centre de la diaphyse (proximal)", "tib_shaft_dist": "centre de la diaphyse (distal)",
}
OBLIGATOIRES = {
    "femur": ["head_center", "gt_tip", "neck_base", "cond_med_dist", "cond_lat_dist", "cond_med_caud", "cond_lat_caud",
              "troch_dist", "epi_med", "epi_lat"],
    "tibia": ["eminence", "plat_med", "plat_lat", "plat_cran", "plat_caud", "groove_med", "groove_lat",
              "distal_center", "dist_cran", "dist_caud", "caud_med", "caud_lat", "mall_med", "mall_lat"],
}


def unitaire(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


# =============================================================================== outils géométriques
def ajuster_sphere(p):
    """Sphère des moindres carrés (algébrique) : centre, rayon, écart quadratique moyen (mm)."""
    A = np.column_stack([2 * p, np.ones(len(p))])
    b = (p ** 2).sum(1)
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = x[:3]
    r = float(np.sqrt(max(x[3] + c @ c, 1e-9)))
    return c, r, float(np.sqrt(np.mean((np.linalg.norm(p - c, axis=1) - r) ** 2)))


def sphere_robuste(p, n=None, rayons=(4.0, 30.0), essais=400, tol=0.6, graine=0):
    """Sphère par RANSAC (4 points), affinée sur les points à moins de `tol` mm de la surface. Si les normales sont
    données, seuls comptent les points dont la normale s'éloigne du centre (surface convexe vue de l'extérieur)."""
    rng = np.random.default_rng(graine)
    meilleur = (None, 0.0, np.inf, np.zeros(len(p), bool))
    if len(p) < 20:
        return meilleur
    for _ in range(essais):
        i = rng.choice(len(p), 4, replace=False)
        try:
            c, r, _ = ajuster_sphere(p[i])
        except np.linalg.LinAlgError:
            continue
        if not rayons[0] <= r <= rayons[1]:
            continue
        d = np.abs(np.linalg.norm(p - c, axis=1) - r)
        ok = d < tol
        if n is not None:
            ok &= ((p - c) * n).sum(1) > 0.5 * r
        if ok.sum() > meilleur[3].sum():
            meilleur = (c, r, 0.0, ok)
    c, r, _, ok = meilleur
    for _ in range(3):                                   # affinage sur les points proches
        if c is None or ok.sum() < 10:
            break
        c, r, rms = ajuster_sphere(p[ok])
        d = np.abs(np.linalg.norm(p - c, axis=1) - r)
        ok = d < tol
        if n is not None:
            ok &= ((p - c) * n).sum(1) > 0.5 * r
        meilleur = (c, r, rms, ok)
    return meilleur


def enveloppe_tangente(q, cote_med, cote_lat):
    """Tangente commune (règle posée sur deux bosses) : arête de l'enveloppe convexe 2D de q qui enjambe le creux
    entre les deux groupes de points (masques cote_med / cote_lat). q est orienté pour que la règle soit « en bas »
    (petits q[:, 1]). Renvoie les indices (i_med, i_lat) ou None."""
    if cote_med.sum() < 3 or cote_lat.sum() < 3:
        return None
    h = ConvexHull(q)
    meilleur = None
    for a, b in h.simplices:
        if cote_med[a] and cote_lat[b] or cote_med[b] and cote_lat[a]:
            e = q[b] - q[a]
            nrm = np.array([e[1], -e[0]])                # normale de l'arête ; on garde l'arête du bas
            ctr = q.mean(0)
            if nrm @ (q[a] - ctr) < 0:
                nrm = -nrm
            if nrm[1] < 0 and (meilleur is None or nrm[1] < meilleur[2]):
                meilleur = (a, b, nrm[1] / np.linalg.norm(nrm))
    if meilleur is None:
        return None
    a, b = meilleur[:2]
    return (a, b) if cote_med[a] else (b, a)


def region_connexe(voisins, depart, admis):
    """Croissance de région sur le maillage : sommets admis reliés au sommet de départ."""
    vu = np.zeros(len(admis), bool)
    if not admis[depart]:
        return vu
    pile = [int(depart)]
    vu[depart] = True
    while pile:
        i = pile.pop()
        for j in voisins[i]:
            if admis[j] and not vu[j]:
                vu[j] = True
                pile.append(j)
    return vu


def section(m, origine, normale):
    """Points d'intersection du maillage avec un plan (segments de la coupe, extrémités empilées)."""
    seg = trimesh.intersections.mesh_plane(m, normale, origine)
    return seg.reshape(-1, 3) if len(seg) else np.zeros((0, 3))


# =============================================================================== complétude
def extremites_coupees(v, faces, normales_faces, aires, axe, longueur, bords=None):
    """Extrémités coupées par le champ du scanner. 1) Si l'étape 4 a noté les bords du volume touchés par l'os
    (rapport.json, « bords_volume ») : une extrémité est coupée si des sommets de son dixième extrême sont à moins de
    1,5 mm d'un de ces plans. 2) Sinon (STL seul) : une extrémité coupée porte un « couvercle », une face plane
    perpendiculaire à un axe du scanner (normales à 2° près, coplanaire à 0,3 mm près) de plus de
    P.CORA_COUVERCLE_MIN_MM2 ; aucune surface osseuse naturelle mesurée n'en a autant (≤ 47 mm² sur le lévrier)."""
    tv = (v - v.mean(0)) @ axe
    tf = (v[faces].mean(1) - v.mean(0)) @ axe
    out = {}
    for nom, mv, mf in (("haut", tv > tv.max() - 0.1 * longueur, tf > tf.max() - 0.1 * longueur),
                        ("bas", tv < tv.min() + 0.1 * longueur, tf < tf.min() + 0.1 * longueur)):
        if bords is not None:
            touche = [b for b in bords if (np.abs((v[mv] - np.array(b["point"])) @ np.array(b["normale"])) < 1.5).any()]
            out[nom] = {"coupe": bool(touche), "methode": "bords du volume (étape 4)",
                        "bords": [f"{b['axe']} {b['cote']}" for b in touche]}
            continue
        aire_max, direction = 0.0, None
        for k in range(3):
            for sgn in (1, -1):
                e = np.zeros(3)
                e[k] = sgn
                ok = mf & (normales_faces @ e > np.cos(np.radians(2)))
                if not ok.any():
                    continue
                pos = v[faces[ok]].mean(1) @ e
                a_ok = aires[ok]
                for p0 in np.unique(np.round(pos, 1)):
                    aire = float(a_ok[np.abs(pos - p0) < 0.3].sum())
                    if aire > aire_max:
                        aire_max, direction = aire, ("LR", "PA", "IS")[k]
        out[nom] = {"coupe": aire_max > P.CORA_COUVERCLE_MIN_MM2, "methode": "couvercle plan (STL seul)",
                    "aire_plane_mm2": round(aire_max, 1), "axe_scanner": direction}
    return out


# =============================================================================== repère de l'os
class Os:
    """Maillage d'un os exprimé dans un repère courant (R lignes = X, Y, Z ; origine o) : p_os = R (p − o)."""

    def __init__(self, m):
        self.m = m
        self.v0 = np.asarray(m.vertices, float)
        self.n0 = np.asarray(m.vertex_normals, float)
        self.voisins = [np.asarray(x) for x in m.vertex_neighbors]
        self.R, self.o = np.eye(3), self.v0.mean(0)
        self.maj()

    def maj(self):
        self.v = (self.v0 - self.o) @ self.R.T
        self.n = self.n0 @ self.R.T
        self.L = float(np.ptp(self.v[:, 1]))
        self.ytop, self.ybot = float(self.v[:, 1].max()), float(self.v[:, 1].min())

    def poser(self, x, y, o=None):
        """Nouveau repère : Y donné, X orthogonalisé, Z = X × Y (repère direct)."""
        y = unitaire(y)
        x = unitaire(x - (x @ y) * y)
        z = np.cross(x, y)
        self.R = np.vstack([x, y, z])
        if o is not None:
            self.o = np.asarray(o, float)
        self.maj()

    def vers_scanner(self, p):
        return np.asarray(p) @ self.R + self.o

    def depuis_scanner(self, p):
        return (np.asarray(p) - self.o) @ self.R.T

    def tranche(self, y0, y1):
        return (self.v[:, 1] >= y0) & (self.v[:, 1] <= y1)

    def milieu_diaphyse(self, y):
        """Milieu de la diaphyse à la hauteur y, comme diaphysisMidpoint() de CORA 3D : milieux des bords médial /
        latéral (x) et crânial / caudal (z) de la section."""
        s = section(self.m, self.vers_scanner([0, y, 0]), self.R[1])
        if len(s) < 6:
            return None
        q = self.depuis_scanner(s)
        return np.array([(q[:, 0].min() + q[:, 0].max()) / 2, y, (q[:, 2].min() + q[:, 2].max()) / 2])

    def section_remplie(self, y, pas=0.25):
        """Section transverse REMPLIE à la hauteur y, dans le plan (x, z) du repère courant : (masque 2D [z, x],
        coin (x0, z0), pas). Règle pair-impair ligne par ligne sur les segments de la coupe : une coupe du maillage
        n'a que son contour ; il faut le remplir pour voir les creux (échancrure) et les saillies (crête)."""
        seg = trimesh.intersections.mesh_plane(self.m, self.R[1], self.vers_scanner([0, y, 0]))
        if not len(seg):
            return None
        q = self.depuis_scanner(seg.reshape(-1, 3)).reshape(-1, 2, 3)[:, :, [0, 2]]
        lo = q.reshape(-1, 2).min(0) - 1
        n = np.ceil((q.reshape(-1, 2).max(0) + 1 - lo) / pas).astype(int)
        M = np.zeros((n[1], n[0]), bool)
        a, b = q[:, 0], q[:, 1]
        for j in range(n[1]):
            zz = lo[1] + (j + 0.5) * pas
            c = (a[:, 1] > zz) != (b[:, 1] > zz)
            if not c.any():
                continue
            t = (zz - a[c, 1]) / (b[c, 1] - a[c, 1])
            x = np.sort(a[c, 0] + t * (b[c, 0] - a[c, 0]))
            for x0, x1 in zip(x[::2], x[1::2]):
                M[j, max(int((x0 - lo[0]) / pas), 0):max(int((x1 - lo[0]) / pas), 0)] = True
        return M, lo, pas

    def ligne_centrale(self, pas=2.0):
        out = []
        for y in np.arange(self.ybot + 1.0, self.ytop - 1.0, pas):
            c = self.milieu_diaphyse(y)
            if c is not None:
                out.append([round(float(y), 3), round(float(c[0]), 3), round(float(c[2]), 3)])
        return out


def axe_long(v):
    c = v.mean(0)
    _, s, vt = np.linalg.svd(v - c, full_matrices=False)
    return c, vt


# =============================================================================== fémur
def tete_femorale(O, tete_scanner=None):
    """Centre de la tête : sphère robuste sur l'extrémité proximale ; si la segmentation l'a trouvée (repère
    tete_femorale), on part de son centre."""
    sel = O.tranche(O.ytop - 0.2 * O.L, O.ytop)
    p, n = O.v[sel], O.n[sel]
    if tete_scanner is not None:
        c0 = O.depuis_scanner(tete_scanner)
        proche = np.linalg.norm(p - c0, axis=1) < 0.12 * O.L
        p, n = p[proche], n[proche]
    c, r, rms, ok = sphere_robuste(p, n, rayons=(0.025 * O.L, 0.09 * O.L))
    return c, r, rms, int(ok.sum())


def condyles_femur(O, xc):
    """Sphères des condyles médial et latéral : surfaces distales et caudales de chaque côté de l'échancrure."""
    out = {}
    for cote, s in (("med", -1), ("lat", 1)):
        sel = O.tranche(O.ybot, O.ybot + 0.12 * O.L) & (s * (O.v[:, 0] - xc) > 1.0)
        sel &= (O.n[:, 1] < 0.3) & (O.n[:, 2] > -0.3)    # surfaces distales et caudales (pas la trochlée crâniale)
        c, r, rms, ok = sphere_robuste(O.v[sel], O.n[sel], rayons=(0.02 * O.L, 0.08 * O.L), tol=0.5)
        out[cote] = (c, r, rms)
    return out


def reperes_femur(O, tete, col=True, r_tete=None):
    v, n = O.v, O.n
    L, yb = O.L, O.ybot
    R = {"head_center": tete}
    # grand trochanter : point le plus proximal du côté latéral (x > axe)
    haut = O.tranche(O.ytop - 0.15 * L, O.ytop)
    xa = O.milieu_diaphyse(O.ytop - L / 3)[0]
    lat = haut & (v[:, 0] > xa + 0.02 * L)
    R["gt_tip"] = v[lat][np.argmax(v[lat, 1])]
    # échancrure intercondylaire : milieu en x de la partie distale
    dist = O.tranche(yb, yb + 0.12 * L)
    xc = (np.percentile(v[dist, 0], 2) + np.percentile(v[dist, 0], 98)) / 2
    Wc = np.percentile(v[dist, 0], 98) - np.percentile(v[dist, 0], 2)          # largeur des condyles
    cond = condyles_femur(O, xc)
    for cote in ("med", "lat"):
        if cond[cote][0] is not None:
            R[f"cond_{cote}_center"] = cond[cote][0]
    # points distaux : tangente commune sous les condyles (vue de face), sur tous les points distaux de chaque côté de
    # l'échancrure (une fabelle, toujours plus proximale, ne peut pas toucher cette règle)
    med, lat = dist & (v[:, 0] < xc), dist & (v[:, 0] > xc)
    idx = np.flatnonzero(med | lat)
    t = enveloppe_tangente(v[idx][:, [0, 1]], med[idx], lat[idx])
    R["cond_med_dist"], R["cond_lat_dist"] = v[idx[t[0]]], v[idx[t[1]]]
    # points caudaux : tangente commune derrière les condyles (vue axiale), sous le niveau des centres des condyles
    # + un demi-rayon : une fabelle restée accolée (caudo-proximale) ou un ostéophyte est ainsi exclu
    centres = [cond[c] for c in ("med", "lat") if cond[c][0] is not None]
    y_lim = (np.mean([c[0][1] for c in centres]) + 0.5 * np.mean([c[1] for c in centres])) if centres else yb + 0.1 * L
    bas = v[:, 1] < y_lim
    idx = np.flatnonzero((med | lat) & bas)
    t = enveloppe_tangente(np.column_stack([v[idx, 0], -v[idx, 2]]), med[idx], lat[idx])
    R["cond_med_caud"], R["cond_lat_caud"] = v[idx[t[0]]], v[idx[t[1]]]
    # épicondyles : points extrêmes en x au niveau des centres des condyles
    yc = np.mean([cond[c][0][1] for c in ("med", "lat") if cond[c][0] is not None]) if any(cond[c][0] is not None for c in cond) else yb + 0.06 * L
    bande = O.tranche(yc - 0.04 * L, yc + 0.04 * L)
    R["epi_med"] = v[bande][np.argmin(v[bande, 0])]
    R["epi_lat"] = v[bande][np.argmax(v[bande, 0])]
    # trochlée : fond du sillon. À chaque niveau, profil crânial z_min(x) : deux crêtes (z petits) et, entre elles,
    # le sillon. On garde le point dont la « profondeur » (descente jusqu'à la crête la plus basse de chaque côté,
    # dans un rayon de 12 mm) est la plus grande.
    fonds = []
    for y in np.arange(yc - 2.0, yc + 0.2 * L, 1.0):
        sl = O.tranche(y - 0.6, y + 0.6)
        s_ = sl & (v[:, 2] < np.median(v[sl, 2])) if sl.sum() > 30 else sl
        if s_.sum() < 30:
            continue
        x, z = v[s_, 0], v[s_, 2]
        bins = np.arange(x.min(), x.max() + 0.75, 0.75)
        k = np.digitize(x, bins)
        prof = np.array([z[k == i].min() if (k == i).any() else np.nan for i in range(1, len(bins))])
        xm = (bins[:-1] + bins[1:]) / 2
        ok = ~np.isnan(prof)
        if ok.sum() < 10:
            continue
        xm, prof = xm[ok], np.convolve(prof[ok], np.ones(3) / 3, mode="same")
        # seulement la face crâniale de la trochlée (à moins de 8 mm de son point le plus crânial) et près du milieu
        # des condyles : sinon un bord médial ou latéral de l'os, plus caudal, passerait pour un « sillon »
        face = prof < prof.min() + 8.0
        meilleur = (0.0, None)
        for i in range(2, len(xm) - 2):
            if not face[i] or abs(xm[i] - xc) > 0.3 * Wc:
                continue
            g = (xm < xm[i]) & (xm > xm[i] - 12) & face
            d_ = (xm > xm[i]) & (xm < xm[i] + 12) & face
            if not g.any() or not d_.any():
                continue
            prof_ = min(prof[i] - prof[g].min(), prof[i] - prof[d_].min())
            if prof_ > meilleur[0]:
                meilleur = (prof_, i)
        if meilleur[1] is not None:
            i = meilleur[1]
            fonds.append((y, xm[i], prof[i], meilleur[0]))
    fonds = np.array(fonds)
    nets = fonds[fonds[:, 3] > 1.0] if len(fonds) else fonds
    if len(nets):
        # suivi : on part du niveau des condyles et on monte tant que le sillon reste net et continu (≤ 3 mm par mm)
        j0 = int(np.argmin(np.abs(nets[:, 0] - yc)))
        garde = [j0]
        for j in range(j0 + 1, len(nets)):
            if nets[j, 0] - nets[garde[-1], 0] > 2.5 or abs(nets[j, 1] - nets[garde[-1], 1]) > 3.0:
                break
            garde.append(j)
        nets = nets[min(garde):max(garde) + 1] if len(garde) > 1 else nets[[j0]]
        # fond distal : au niveau des centres des condyles ; fond proximal : dernier niveau où le sillon est net
        j = 0
        R["troch_dist"] = point_surface(O, nets[j, 1], nets[j, 0], nets[j, 2])
        R["troch_prox"] = point_surface(O, nets[-1, 1], nets[-1, 0], nets[-1, 2])
        R["_sillon"] = nets
    # col : centre de la section la plus étroite entre la tête et la diaphyse
    if col:
        rt = r_tete or 0.05 * L
        R["neck_base"] = centre_col(O, tete, rt)
        lt = petit_trochanter(O, tete, rt)
        if lt is not None:
            R["lt_tip"], R["neck_base_lt"] = lt
    m13, m12 = O.milieu_diaphyse(O.ytop - L / 3), O.milieu_diaphyse(O.ytop - L / 2)
    if m13 is not None and m12 is not None:
        R["fem_axe_13"], R["fem_axe_12"] = m13, m12
    return R, cond


def petit_trochanter(O, tete, r_tete):
    """Petit trochanter = saillie caudo-médiale maximale sous la tête (entre 1,4 rayon de tête et 18 % de la longueur
    plus bas) ; base du col (Al Aiyan 2021) = milieu de la section transverse à ce niveau (bords médial / latéral et
    crânial / caudal, comme sur une coupe CT). Renvoie (sommet du petit trochanter, base du col) ou None."""
    v, best = O.v, None
    for y in np.arange(tete[1] - 1.4 * r_tete - 0.18 * O.L, tete[1] - 1.4 * r_tete, 1.0):
        c = O.milieu_diaphyse(y)
        b = O.tranche(y - 0.5, y + 0.5)
        if c is None or not b.any():
            continue
        p = (v[b][:, [0, 2]] - c[[0, 2]]) @ np.array([-1.0, 1.0]) / np.sqrt(2)      # direction caudo-médiale
        if best is None or p.max() > best[0]:
            best = (p.max(), y, v[b][int(np.argmax(p))])
    if best is None:
        return None
    base = O.milieu_diaphyse(best[1])
    return (best[2], base) if base is not None else None


def point_surface(O, x, y, z):
    """Sommet du maillage le plus proche du point (x, y, z)."""
    return O.v[cKDTree(O.v).query([x, y, z])[1]]


def centre_col(O, tete, r_tete):
    """Axe du col (Dudley 2006 : centre de la tête → centre du col). Le col part de la tête comme un cylindre : dans
    une coquille de 1,1 à 1,6 rayon de tête autour du centre, la surface hors de la sphère de la tête est celle du col,
    et son barycentre est sur l'axe du col. « neck_base » est placé sur cet axe à 1,5 rayon du centre.
    Validation sur le fémur du modèle : axe à 2° de l'axe vrai, antéversion 27,1° pour 29,7°."""
    d = np.linalg.norm(O.v - tete, axis=1)
    coque = (d > 1.1 * r_tete) & (d < 1.6 * r_tete) & (np.abs(d - r_tete) > 1.0)
    if coque.sum() < 20:
        return None
    axe = unitaire(O.v[coque].mean(0) - tete)
    return tete + 1.5 * r_tete * axe


def cotes_femur(O, tete):
    """Médial = côté de la tête ; caudal = côté de l'échancrure intercondylaire : sur les sections remplies juste
    au-dessus de l'extrémité distale, c'est le plus grand creux entre la section et son enveloppe convexe (entre les
    deux condyles)."""
    from scipy import ndimage as ndi
    dirs = []
    for f in (0.04, 0.06, 0.08):
        r = O.section_remplie(O.ybot + f * O.L)
        if r is None:
            continue
        M, lo, pas = r
        jj, ii = np.nonzero(M)
        pts = np.column_stack([ii, jj]).astype(float)
        h = ConvexHull(pts)
        J, I = np.mgrid[0:M.shape[0], 0:M.shape[1]]
        g = np.column_stack([I.ravel(), J.ravel()]).astype(float)
        dans = np.all(h.equations[:, :2] @ g.T + h.equations[:, 2:3] <= 1e-9, axis=0).reshape(M.shape)
        creux, nb = ndi.label(dans & ~M)
        if not nb:
            continue
        tailles = ndi.sum(np.ones_like(creux), creux, range(1, nb + 1))
        k = int(np.argmax(tailles)) + 1
        cj, ci = ndi.center_of_mass(creux == k)
        dirs.append(unitaire(np.array([ci - pts[:, 0].mean(), cj - pts[:, 1].mean()])))
    caudal2 = unitaire(np.sum(dirs, axis=0)) if dirs else np.array([0.0, 1.0])
    axe_c = O.milieu_diaphyse(tete[1] - 0.15 * O.L)
    medial2 = unitaire(np.array([tete[0], tete[2]]) - np.array([axe_c[0], axe_c[2]]))
    return medial2, caudal2


# =============================================================================== tibia
def plan_plateau(O):
    s = O.tranche(O.ytop - 0.08 * O.L, O.ytop) & (O.n[:, 1] > 0.6)
    c = O.v[s].mean(0)
    _, _, vt = np.linalg.svd(O.v[s] - c)
    nrm = vt[2] * np.sign(vt[2][1])
    return c, nrm


def reperes_tibia(O, fib=None):
    v, n, L, yt, yb = O.v, O.n, O.L, O.ytop, O.ybot
    R = {}
    prox = O.tranche(yt - 0.12 * L, yt)
    # centre du plateau (milieu en x de l'extrémité proximale)
    hautes = O.tranche(yt - 0.06 * L, yt)
    xc = (np.percentile(v[hautes, 0], 2) + np.percentile(v[hautes, 0], 98)) / 2
    W = np.percentile(v[hautes, 0], 98) - np.percentile(v[hautes, 0], 2)
    zc = (np.percentile(v[hautes, 2], 5) + np.percentile(v[hautes, 2], 95)) / 2
    # éminence : milieu des sommets des tubercules intercondylaires médial et latéral
    bande = hautes & (np.abs(v[:, 0] - xc) < 0.2 * W) & (np.abs(v[:, 2] - zc) < 0.25 * W)
    pts = v[bande]
    med = pts[pts[:, 0] <= xc]
    lat = pts[pts[:, 0] > xc]
    tm = med[np.argmax(med[:, 1])] if len(med) else pts[np.argmax(pts[:, 1])]
    tl = lat[np.argmax(lat[:, 1])] if len(lat) else tm
    R["eminence"] = (tm + tl) / 2
    R["eminence"][1] = max(tm[1], tl[1])
    # plateaux : régions articulaires (normales proches de celle du plateau) reliées au centre de chaque condyle
    cpl, npl = plan_plateau(O)
    admis = prox & (n @ npl > np.cos(np.radians(40))) & (np.abs(v[:, 0] - xc) > 0.1 * W)
    arbre = cKDTree(v)
    for cote, s in (("med", -1), ("lat", 1)):
        cible = np.array([xc + s * 0.27 * W, yt, zc])
        cand = np.flatnonzero(admis & (s * (v[:, 0] - xc) > 0))
        if not len(cand):
            continue
        dep = cand[np.argmin(np.linalg.norm(v[cand][:, [0, 2]] - cible[[0, 2]], axis=1) - 0.2 * v[cand, 1])]
        reg = region_connexe(O.voisins, dep, admis & (s * (v[:, 0] - xc) > 0))
        p = v[reg]
        ctr = p.mean(0)
        R[f"plat_{cote}"] = v[np.flatnonzero(reg)[np.argmin(np.linalg.norm(p[:, [0, 2]] - ctr[[0, 2]], axis=1))]]
        if cote == "med":
            # bords crânial et caudal du plateau médial, dans une bande centrale en x (vue de profil)
            xm = R["plat_med"][0]
            b = reg & (np.abs(v[:, 0] - xm) < 0.06 * W)
            if b.sum() < 4:
                b = reg
            q = v[b]
            R["plat_cran"], R["plat_caud"] = q[np.argmin(q[:, 2])], q[np.argmax(q[:, 2])]
    # points caudaux des condyles tibiaux : tangente commune derrière l'extrémité proximale (échancrure poplitée) ;
    # si le bord caudal est convexe (pas d'échancrure), point le plus caudal autour de chaque condyle
    sel = prox & (v[:, 2] > zc)
    idx = np.flatnonzero(sel)
    q = np.column_stack([v[idx, 0], -v[idx, 2]])
    t = enveloppe_tangente(q, v[idx, 0] < xc - 0.1 * W, v[idx, 0] > xc + 0.1 * W)
    if t:
        R["caud_med"], R["caud_lat"] = v[idx[t[0]]], v[idx[t[1]]]
    else:
        for cote in ("med", "lat"):
            xx = R.get(f"plat_{cote}", [xc + (0.27 if cote == "lat" else -0.27) * W])[0]
            b = prox & (np.abs(v[:, 0] - xx) < 0.08 * W)
            if b.any():
                R[f"caud_{cote}"] = v[b][np.argmax(v[b, 2])]
    # tubérosité : point le plus crânial de l'extrémité proximale
    R["tuberosity"] = v[prox][np.argmin(v[prox, 2])]
    # surface articulaire distale (cochlée). Elle est concave d'avant en arrière : sur une radiographie de face, le
    # faisceau est tangent à sa partie la plus profonde. Le trait visible est donc l'enveloppe HAUTE (y max par x) de
    # la surface tournée vers distal : deux sillons (pics vers proximal) séparés par la crête intermédiaire (creux).
    dist = O.tranche(yb, yb + 0.1 * L)
    basses = O.tranche(yb, yb + 0.05 * L)
    Wd = np.percentile(v[basses, 0], 98) - np.percentile(v[basses, 0], 2)
    art0 = dist & (n[:, 1] < -0.5)
    # départ : point le plus profond (le plus proximal) de la surface tournée vers distal, dans la moitié centrale
    xd0 = (np.percentile(v[basses, 0], 2) + np.percentile(v[basses, 0], 98)) / 2
    cen = art0 & (np.abs(v[:, 0] - xd0) < 0.3 * Wd)
    dep = np.flatnonzero(cen)[np.argmax(v[cen, 1])]
    reg_art = region_connexe(O.voisins, dep, art0)
    x_dep = v[dep, 0]

    def profil(sel):
        x, y = v[sel, 0], v[sel, 1]
        bins = np.arange(x.min(), x.max() + 0.75, 0.75)
        k = np.digitize(x, bins)
        xm = (bins[:-1] + bins[1:]) / 2
        p = np.array([y[k == i].max() if (k == i).any() else np.nan for i in range(1, len(bins))])
        ok = ~np.isnan(p)
        return xm[ok], np.convolve(p[ok], np.ones(3) / 3, mode="same")

    def sillons(xm, p):
        """Deux pics (sillons) séparés par un creux (crête) d'au moins 0,5 mm, écartés de 25 à 85 % de la largeur ;
        on garde la paire la plus haute. Sinon : maximum de chaque côté du point de départ, sans crête nette."""
        pics = [i for i in range(1, len(p) - 1) if p[i] >= p[i - 1] and p[i] >= p[i + 1] and abs(xm[i] - x_dep) < 0.55 * Wd]
        best = None
        for ia in pics:
            for ib in pics:
                if xm[ib] - xm[ia] < 0.25 * Wd or xm[ib] - xm[ia] > 0.85 * Wd:
                    continue
                ic = ia + 1 + int(np.argmin(p[ia + 1:ib]))
                if p[ic] > min(p[ia], p[ib]) - 0.5:
                    continue
                score = p[ia] + p[ib]
                if best is None or score > best[0]:
                    best = (score, ia, ib, ic)
        if best:
            return best[1], best[2], best[3], True
        g, d_ = xm < x_dep, xm >= x_dep
        if g.sum() < 1 or d_.sum() < 1:
            return None
        ia, ib = np.flatnonzero(g)[np.argmax(p[g])], np.flatnonzero(d_)[np.argmax(p[d_])]
        return ia, ib, None, False

    zmid, prof_cc, trouve = None, None, None
    for passe in range(2):
        sel = reg_art if zmid is None else reg_art & (np.abs(v[:, 2] - zmid) < max(2.0, 0.2 * prof_cc))
        if sel.sum() < 10:
            break
        xm, p = profil(sel)
        r_ = sillons(xm, p)
        if r_ is None:
            break
        ia, ib, ic, creux = r_
        x_cen = xm[ic] if creux else (xm[ia] + xm[ib]) / 2       # crête nette (IMAIOS) ou milieu des sillons
        bande = reg_art & (np.abs(v[:, 0] - x_cen) < 0.08 * Wd)
        q = v[bande] if bande.sum() > 3 else v[reg_art]
        cran, caud = q[np.argmin(q[:, 2])], q[np.argmax(q[:, 2])]
        zmid, prof_cc = (cran[2] + caud[2]) / 2, caud[2] - cran[2]
        trouve = (xm[ia], xm[ib], x_cen, creux, cran, caud)
    if trouve:
        xa, xb, x_cen, creux, cran, caud = trouve

        def pt_haut(xx):
            b_ = reg_art & (np.abs(v[:, 0] - xx) < 0.6) & (np.abs(v[:, 2] - zmid) < max(2.0, 0.2 * prof_cc))
            if not b_.any():
                b_ = reg_art & (np.abs(v[:, 0] - xx) < 0.6)
            q_ = v[b_]
            return q_[np.argmax(q_[:, 1])] if len(q_) else None
        R["groove_med"], R["groove_lat"] = pt_haut(xa), pt_haut(xb)
        R["dist_cran"], R["dist_caud"] = cran, caud
        R["distal_center"] = pt_haut(x_cen)
        R["_cochlee"] = {"crete_nette": bool(creux)}
    # axe antécochléaire (Brühschwein 2023, torsion tibiale en 3D) : tangente commune aux deux saillies osseuses
    # crâniales, médiale et latérale, situées juste au-dessus de la cochlée (proximales à l'interligne)
    if "dist_cran" in R:
        y0 = R["dist_cran"][1]
        zone = O.tranche(y0, y0 + 0.07 * L)
        xc_d = R.get("distal_center", R["dist_cran"])[0]
        idx = np.flatnonzero(zone)
        if len(idx) > 20:
            g_ = (v[idx, 0] < xc_d - 0.15 * Wd) & (v[idx, 0] > xc_d - 0.45 * Wd)
            d_ = (v[idx, 0] > xc_d + 0.15 * Wd) & (v[idx, 0] < xc_d + 0.45 * Wd)
            t_ = enveloppe_tangente(v[idx][:, [0, 2]], g_, d_)
            if t_:
                R["ant_med"], R["ant_lat"] = v[idx[t_[0]]], v[idx[t_[1]]]
            elif g_.any() and d_.any():                  # bord crânial convexe (pas de creux) : point le plus crânial
                R["ant_med"] = v[idx[g_]][int(np.argmin(v[idx[g_], 2]))]      # de chaque tiers, médial et latéral
                R["ant_lat"] = v[idx[d_]][int(np.argmin(v[idx[d_], 2]))]
    # centres de la diaphyse à 25 % et 75 % de la longueur : axe long de la torsion tibiale (Brühschwein 2023)
    for nom_, f_ in (("tib_shaft_prox", 0.25), ("tib_shaft_dist", 0.75)):
        c_ = O.milieu_diaphyse(yt - f_ * L)
        if c_ is not None:
            R[nom_] = c_
    # malléoles : points extrêmes en x de l'extrémité distale (la latérale appartient à la fibula)
    R["mall_med"] = v[basses][np.argmin(v[basses, 0])]
    R["mall_lat"] = v[basses][np.argmax(v[basses, 0])]
    if fib is not None:
        fb = fib[fib[:, 1] < yb + 0.05 * L]
        if len(fb):
            R["mall_lat"] = fb[np.argmax(fb[:, 0])]
        R["fib_head"] = fib[np.argmax(fib[:, 1])]
    return R


def cotes_tibia(O, fib=None):
    """Crânial = côté de la crête tibiale : sur les sections remplies du quart proximal (sous les condyles), point le
    plus éloigné du centre. Latéral = perpendiculaire, du côté de la fibula (caudo-latérale chez le chien) ; sans
    fibula, à l'opposé de la malléole médiale (saillie distale médiale)."""
    yt, L = O.ytop, O.L
    dirs = []
    for f in (0.14, 0.18, 0.22):
        r = O.section_remplie(yt - f * L)
        if r is None:
            continue
        M, lo, pas = r
        jj, ii = np.nonzero(M)
        p = np.column_stack([ii, jj]).astype(float)
        d = p - p.mean(0)
        loin = d[np.linalg.norm(d, axis=1) > np.percentile(np.linalg.norm(d, axis=1), 97)]
        dirs.append(unitaire(loin.mean(0)))
    cranial2 = unitaire(np.sum(dirs, axis=0))
    perp = np.array([-cranial2[1], cranial2[0]])
    axe = O.milieu_diaphyse(yt - 0.5 * L)
    if fib is not None and len(fib):
        f = fib.mean(0)
        sgn = np.sign(perp @ np.array([f[0] - axe[0], f[2] - axe[2]]))
        raison_lat = "côté de la fibula"
    else:
        basses = O.tranche(O.ybot, O.ybot + 0.03 * L)
        p = O.v[basses][np.argmin(O.v[basses, 1])]
        c = O.milieu_diaphyse(O.ybot + 0.08 * L)
        sgn = -np.sign(perp @ np.array([p[0] - c[0], p[2] - c[2]]))
        raison_lat = "à l'opposé de la malléole médiale (pas de fibula : à vérifier)"
    return sgn * perp, -cranial2, raison_lat


# =============================================================================== analyse complète
MIROIR = np.diag([-1.0, 1.0, 1.0])


def miroir_maillage(m):
    """Symétrie x -> -x (scanner) ; l'ordre des sommets est inversé pour garder des normales sortantes."""
    return trimesh.Trimesh(np.asarray(m.vertices) @ MIROIR, np.asarray(m.faces)[:, ::-1], process=False)


def orienter(m, type_os, fibula=None, tete_scanner=None):
    """Premier repère (axe long, sens proximal) et sens anatomiques latéral / caudal dans le repère du scanner.
    Renvoie (O, lateral, caudal, droit, raisons)."""
    O = Os(m)
    c, vt = axe_long(O.v0)
    y = vt[0]
    t = (O.v0 - c) @ y
    if type_os == "femur":
        if tete_scanner is not None:
            raison_prox = "côté de la tête fémorale trouvée par la segmentation"
            if (np.asarray(tete_scanner) - c) @ y < 0:
                y = -y
        else:
            raison_prox = "extrémité qui porte la meilleure sphère (tête fémorale)"
            O.poser(vt[1], y, c)
            nb = []
            for sel in (O.tranche(O.ytop - 0.2 * O.L, O.ytop), O.tranche(O.ybot, O.ybot + 0.2 * O.L)):
                nb.append(sphere_robuste(O.v[sel], O.n[sel], rayons=(0.025 * O.L, 0.09 * O.L))[3].sum())
            if nb[1] > nb[0]:
                y = -y
    else:
        raison_prox = "extrémité la plus large (plateau tibial)"
        largeur = lambda sel: np.ptp((O.v0[sel] - c) @ vt[1:].T, axis=0).max() if sel.any() else 0
        if largeur(t < t.min() + 0.08 * np.ptp(t)) > largeur(t > t.max() - 0.08 * np.ptp(t)):
            y = -y
    O.poser(vt[1], y, c)
    if type_os == "femur":
        tete = tete_femorale(O, tete_scanner)[0]
        med2, cau2 = cotes_femur(O, tete)
        lat2 = -med2
        raisons = {"proximal": raison_prox, "lateral": "à l'opposé de la tête fémorale (la tête est médiale)",
                   "caudal": "côté de l'échancrure intercondylaire"}
    else:
        fib = O.depuis_scanner(np.asarray(fibula.vertices, float)) if fibula is not None else None
        lat2, cau2, raison_lat = cotes_tibia(O, fib)
        raisons = {"proximal": raison_prox, "lateral": raison_lat,
                   "caudal": "à l'opposé de la crête tibiale (crâniale)"}
    lateral = O.R[0] * lat2[0] + O.R[2] * lat2[1]
    caudal = O.R[0] * cau2[0] + O.R[2] * cau2[1]
    droit = bool(np.cross(lateral, O.R[1]) @ caudal > 0)
    return O, lateral, caudal, droit, raisons


def analyser(m, type_os, fibula=None, tete_scanner=None, nom_serie="", systeme="LPS", fichier="", bords=None,
             calibrer=True):
    """Repère, côté, complétude et repères d'un fémur ou d'un tibia. m : trimesh (coordonnées du scanner).
    Renvoie (résultat JSON, objet Os dans le repère final ou None)."""
    O, lateral, caudal, droit, raisons = orienter(m, type_os, fibula, tete_scanner)
    longueur = O.L
    coupes = extremites_coupees(O.v0, np.asarray(m.faces), np.asarray(m.face_normals, float),
                                np.asarray(m.area_faces), O.R[1], longueur, bords)
    tronque = {"proximal": coupes["haut"]["coupe"], "distal": coupes["bas"]["coupe"]}
    res = {"schema": VERSION, "os": type_os, "serie": nom_serie, "fichier_stl": fichier, "systeme": systeme,
           "date": datetime.now().isoformat(timespec="seconds"), "longueur_mm": round(longueur, 1),
           "cote": "droit" if droit else "gauche", "raisons": raisons, "tronque": tronque, "couvercles": coupes,
           "avertissements": []}
    # côté vu par le scanner (LPS : +x = gauche du patient ; un membre droit a son côté latéral vers −x)
    lat_x = lateral[0] if systeme == "LPS" else -lateral[0]
    res["cote_scanner"] = "droit" if lat_x < 0 else "gauche"
    if res["cote_scanner"] != res["cote"]:
        res["avertissements"].append(f"côté anatomique ({res['cote']}) différent du côté lu dans le repère du scanner "
                                     f"({res['cote_scanner']}) : vérifier la position déclarée du patient")
    if tronque["proximal"] or tronque["distal"]:
        bouts = [k for k, x in tronque.items() if x]
        res.update(complet=False, raison=f"extrémité {' et '.join(b + "e" for b in bouts)} coupée par le champ du scanner : il faut "
                   "les deux articulations pour la méthode CORA")
        return res, None
    # membre gauche : on travaille sur son image miroir (un membre droit), comme la v2 et CORA 3D
    S = np.eye(3) if droit else MIROIR
    if not droit:
        m = miroir_maillage(m)
        fibula = miroir_maillage(fibula) if fibula is not None else None
        tete_scanner = np.asarray(tete_scanner) @ MIROIR if tete_scanner is not None else None
        lateral, caudal = lateral @ MIROIR, caudal @ MIROIR
    O = Os(m)
    c, vt = axe_long(O.v0)
    # repère de départ : X latéral, Z caudal (trouvés par orienter()), donc Y = Z × X (proximal, repère direct)
    O.poser(lateral, np.cross(caudal, lateral), c)
    fib = None
    for passe in range(3):
        if type_os == "femur":
            tete, r_tete, rms_tete, n_tete = tete_femorale(O, tete_scanner)
            if tete is None:
                res.update(complet=False, raison="tête fémorale introuvable (aucune sphère à l'extrémité proximale)")
                return res, None
            Rp, cond = reperes_femur(O, tete, col=False)
            if "cond_lat_caud" not in Rp:
                break
            m1, m2 = O.milieu_diaphyse(O.ytop - O.L / 3), O.milieu_diaphyse(O.ytop - O.L / 2)
            y_new = O.vers_scanner(m1) - O.vers_scanner(m2)
            x_new = O.vers_scanner(Rp["cond_lat_caud"]) - O.vers_scanner(Rp["cond_med_caud"])
        else:
            fib = O.depuis_scanner(np.asarray(fibula.vertices, float)) if fibula is not None else None
            Rp = reperes_tibia(O, fib)
            y_new = O.vers_scanner(Rp["eminence"]) - O.vers_scanner(Rp["distal_center"])
            x_new = O.vers_scanner(Rp["caud_lat"]) - O.vers_scanner(Rp["caud_med"]) if "caud_lat" in Rp else O.R[0]
        x_new = x_new if x_new @ O.R[0] > 0 else -x_new
        O.poser(x_new, y_new, O.o)
    # dernière détection dans le repère final ; origine : centre articulaire distal, au niveau de l'extrémité distale
    if type_os == "femur":
        tete, r_tete, rms_tete, n_tete = tete_femorale(O, tete_scanner)
        Rp, cond = reperes_femur(O, tete, r_tete=r_tete)
        dc = (Rp["cond_med_dist"] + Rp["cond_lat_dist"]) / 2
        res["qualite"] = {"tete_rayon_mm": round(r_tete, 2), "tete_rms_mm": round(rms_tete, 3), "tete_points": n_tete}
        for cote in ("med", "lat"):
            cc, rr, rms = cond[cote]
            if cc is not None:
                res["qualite"][f"condyle_{cote}_rayon_mm"] = round(rr, 2)
                res["qualite"][f"condyle_{cote}_rms_mm"] = round(rms, 3)
    else:
        fib = O.depuis_scanner(np.asarray(fibula.vertices, float)) if fibula is not None else None
        Rp = reperes_tibia(O, fib)
        dc = Rp["distal_center"]
        res["qualite"] = {"fibula": fibula is not None}
    # nouvelle origine = simple translation : les repères sont décalés, pas recalculés
    decalage = np.array([dc[0], O.ybot, dc[2]])
    O.o = O.vers_scanner(decalage)
    O.maj()
    Rp = {k: (p - decalage if isinstance(p, np.ndarray) and p.shape == (3,) else p) for k, p in Rp.items()}
    if "_cochlee" in Rp:
        res["qualite"]["cochlee"] = Rp.pop("_cochlee")
    sillon = Rp.pop("_sillon", None)
    if sillon is not None:
        res["qualite"]["sillon_trochleen"] = {"niveaux": len(sillon), "profondeur_max_mm": round(float(sillon[:, 3].max()), 2)}
    manquants = [k for k in OBLIGATOIRES[type_os] if k not in Rp or Rp[k] is None]
    if manquants:
        res.update(complet=False, raison="repères introuvables : " + ", ".join(NOMS.get(k, k) for k in manquants))
        return res, O
    # matrice scanner -> os (4 × 4) : p_os = R (S p − o) ; det = −1 si le membre a été mis en miroir
    M = np.eye(4)
    M[:3, :3] = O.R @ S
    M[:3, 3] = -O.R @ O.o
    res.update(complet=True, raison="", miroir=not droit,
               repere={"description": "X latéral, Y proximal, Z caudal (mm) ; membre gauche ramené à un droit par "
                                      "symétrie" if not droit else "X latéral, Y proximal, Z caudal (mm)",
                       "scanner_vers_os": np.round(M, 6).tolist(),
                       "y_haut": round(O.ytop, 3), "y_bas": round(O.ybot, 3)},
               reperes={k: [round(float(x), 3) for x in p] for k, p in Rp.items() if p is not None},
               noms={k: NOMS.get(k, k) for k in Rp},
               ligne_centrale=O.ligne_centrale())
    axe_d = axe_anatomique(O)[1] if type_os == "femur" else None
    res["angles"] = {k: round(x, 2) for k, x in angles_articulaires(type_os, Rp, axe_d).items()}
    t_ = torsion(type_os, Rp)
    res["torsion_deg"] = round(t_, 2) if t_ is not None else None
    tn = TORSION_NORMALE[type_os]
    statut = None
    if t_ is not None:
        statut = "interne" if (t_ > tn["seuils"][1] if type_os == "femur" else t_ < tn["seuils"][0]) else \
            "externe" if (t_ < tn["seuils"][0] if type_os == "femur" else t_ > tn["seuils"][1]) else "normale"
    t_c = torsion(type_os, Rp, "cora3d")
    res["torsion"] = {"valeur_deg": res["torsion_deg"], "statut": statut, "nom": tn["nom"], "definition": tn["definition"],
                      "normale": {"m": tn["m"], "sd": tn["sd"], "seuils": tn["seuils"], "source": tn["source"]},
                      "definition_cora3d_deg": round(t_c, 2) if t_c is not None else None}
    if calibrer:
        res["normales"] = normales(type_os)
    Minv = np.linalg.inv(M)
    res["reperes_scanner"] = {k: [round(float(x), 3) for x in (Minv[:3, :3] @ np.asarray(p) + Minv[:3, 3])]
                              for k, p in Rp.items() if p is not None}
    return res, O


def _sauver_png(O, R, chemin, titre):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    v = O.v
    fig, ax = plt.subplots(1, 3, figsize=(14, 8))
    for a, (i, j, t) in zip(ax, [(0, 1, "vue de face (X latéral →, Y proximal ↑)"), (2, 1, "vue de profil (Z caudal →)"),
                                 (0, 2, "vue axiale (X latéral →, Z caudal ↑)")]):
        a.scatter(v[::5, i], v[::5, j], s=0.2, c="0.6")
        for k, p in R.items():
            a.plot(p[i], p[j], "o", ms=4, color="crimson")
            a.annotate(k, (p[i], p[j]), fontsize=6, color="crimson", xytext=(3, 2), textcoords="offset points")
        a.set_aspect("equal")
        a.set_title(t, fontsize=9)
        a.grid(alpha=0.25)
    fig.suptitle(titre)
    fig.tight_layout()
    fig.savefig(chemin, dpi=110)
    plt.close(fig)


# =============================================================================== angles et valeurs normales
# Valeurs publiées : les mêmes que LITTERATURE dans cora/app/cora_simple.js (moyenne m, écart-type sd).
LITTERATURE = {
    "tibia": {"mMPTA": (93.3, 1.8, "Dismukes et al. 2007"), "mMDTA": (96.0, 2.7, "Dismukes et al. 2007"),
              "valgusTib": (11.8, 3.1, "Newman & Voss 2017"), "mCaPTA": (63.6, 3.9, "Dismukes et al. 2008"),
              "mCrDTA": (81.6, 3.2, "Dismukes et al. 2008")},
    "femur": {"aLPFA": (103.0, 6.4, "Tomlinson et al. 2007"), "aLDFA": (97.0, 3.2, "Tomlinson et al. 2007"),
              "varusFem": (9.4, 2.3, "IMAIOS"), "aCdDFA": (90.5, 6.3, "Kara et al. 2018 (définition voisine)")},
}
# Bornes de normalité des travaux de l'équipe Vezzoni : utilisées en priorité (comme le préréglage par défaut de
# l'onglet CORA) ; les angles qu'ils ne donnent pas gardent LITTERATURE. mCaPTA = 90° − TPA des Labradors sains de
# Guénégo, Vezzoni et Vezzoni 2021 (26,3°, étendue 20,4–30,8° ; écart-type estimé = étendue / 4).
VEZZONI = {
    "femur": {"aLDFA": (94.0, 3.3, "Vezzoni L et al. 2022 (= Tomlinson 2007, berger allemand)")},
    "tibia": {"mMPTA": (93.3, 1.78, "Olsen, Vezzoni L, Vezzoni A et al. 2016 (= Dismukes 2007)"),
              "mCaPTA": (63.7, 2.6, "Guénégo, Vezzoni et Vezzoni 2021 (Labradors sains : TPA 26,3°, 20,4 à 30,8°)")},
}


def _p2(p, vue):
    return np.array([p[0], p[1]]) if vue == "F" else np.array([p[2], p[1]])


def _angU(a, b):
    return float(np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1))))


def _ang(a, b):
    return float(np.degrees(np.arctan2(a[0] * b[1] - a[1] * b[0], a @ b)))


def axe_anatomique(O):
    """Axe anatomique du fémur (Tomlinson 2007), comme axeAnatomique() de CORA 3D : milieux de la diaphyse à 1/3 et 1/2
    de la longueur depuis l'extrémité proximale. Renvoie (point, direction vers distal)."""
    m1, m2 = O.milieu_diaphyse(O.ytop - O.L / 3), O.milieu_diaphyse(O.ytop - O.L / 2)
    return m1, unitaire(m2 - m1)


def angles_articulaires(type_os, R, axe_d=None):
    """Angles projetés sur les vues de face (x, y) et de profil (z, y) : mêmes formules que mesurer() de CORA 3D."""
    L = {k: np.asarray(p, float) for k, p in R.items()}
    F = lambda k: _p2(L[k], "F")
    S = lambda k: _p2(L[k], "S")
    if type_os == "tibia":
        d = L["distal_center"] - L["eminence"]
        dF, dS = _p2(d, "F"), _p2(d, "S")
        return {"mMPTA": _angU(F("plat_med") - F("plat_lat"), dF), "mMDTA": _angU(F("groove_med") - F("groove_lat"), -dF),
                "valgusTib": _ang(F("plat_lat") - F("plat_med"), F("groove_lat") - F("groove_med")),
                "mCaPTA": _angU(S("plat_caud") - S("plat_cran"), dS), "mCrDTA": _angU(S("dist_cran") - S("dist_caud"), -dS),
                "longueur": float(np.linalg.norm(d))}
    dF, dS = _p2(axe_d, "F"), _p2(axe_d, "S")
    cm = (L["cond_med_caud"] + L["cond_lat_caud"]) / 2
    aLDFA = _angU(F("cond_lat_dist") - F("cond_med_dist"), -dF)
    return {"aLPFA": _angU(F("gt_tip") - F("head_center"), dF), "aLDFA": aLDFA, "varusFem": aLDFA - 90,
            "aCdDFA": _angU(_p2(cm, "S") - S("troch_dist"), -dS),
            "longueur": float(np.linalg.norm(L["head_center"] - (L["cond_med_dist"] + L["cond_lat_dist"]) / 2))}


def _angle_autour(a, b, axe):
    """Angle signé (°) de a vers b autour de axe (règle de la main droite), après projection sur le plan ⊥ axe."""
    axe = unitaire(axe)
    pa, pb = a - (a @ axe) * axe, b - (b @ axe) * axe
    return float(np.degrees(np.arctan2(np.cross(pa, pb) @ axe, pa @ pb)))


# Définitions publiées de la torsion et valeurs normales (scanner)
TORSION_NORMALE = {
    "femur": {"nom": "antéversion fémorale", "m": 31.0, "sd": 5.0, "seuils": (20.0, 35.0),
              "source": "Al Aiyan et al. 2021 (CT, 58 chiens) ; seuils < 20° (rétroversion = torsion externe) et > 35° "
                        "(antéversion excessive = torsion interne) : Longo et al. 2022",
              "definition": "axe de la diaphyse ; axe du col = centre de la tête → base du col au niveau du petit "
                            "trochanter ; ligne condylaire caudale ; + = col dirigé vers crânial"},
    "tibia": {"nom": "torsion tibiale", "m": -4.0, "sd": None, "seuils": (-10.0, 2.0),
              "source": "Brühschwein et al. 2023 (3D-CT, tibias normaux ≈ 176°, soit 4° de torsion interne) ; "
                        "physiologique −3 à −6°, anormal < −10° (interne) ou > +2° (externe) : Longo et al. 2022",
              "definition": "axe long = centres de la diaphyse ; ligne condylaire caudale (proximale) ; axe "
                            "antécochléaire (distal) ; − = interne, + = externe"},
}


def torsion(type_os, R, definition="publiee"):
    """Angle de torsion 3D.
    publiee (défaut) — fémur : antéversion d'Al Aiyan 2021 (axe de la diaphyse, centre de la tête → base du col au
    niveau du petit trochanter, ligne condylaire caudale ; + = antéversion) ; tibia : Brühschwein 2023 (axe long par
    les centres de la diaphyse, ligne condylaire caudale / axe antécochléaire ; − = interne, + = externe, comme les
    Méthodes de Longo 2022).
    cora3d — définitions de CORA 3D (axe mécanique ; axe du col au ras de la tête ; tibia : axe bimalléolaire)."""
    L = {k: np.asarray(p, float) for k, p in R.items()}
    if type_os == "femur":
        if definition == "publiee" and all(k in L for k in ("neck_base_lt", "fem_axe_13", "fem_axe_12")):
            axe = L["fem_axe_13"] - L["fem_axe_12"]                     # vers proximal
            col = L["head_center"] - L["neck_base_lt"]
            return -_angle_autour(L["cond_med_caud"] - L["cond_lat_caud"], col, axe)
        if "neck_base" not in L:
            return None
        lon = L["head_center"] - (L["cond_med_dist"] + L["cond_lat_dist"]) / 2
        return -_angle_autour(L["cond_med_caud"] - L["cond_lat_caud"], L["head_center"] - L["neck_base"], lon)
    if definition == "publiee" and all(k in L for k in ("ant_med", "ant_lat", "tib_shaft_prox", "tib_shaft_dist")):
        axe = L["tib_shaft_prox"] - L["tib_shaft_dist"]                 # vers proximal
        return -_angle_autour(L["caud_lat"] - L["caud_med"], L["ant_lat"] - L["ant_med"], axe)
    lon = L["eminence"] - L["distal_center"]
    return -_angle_autour(L["caud_lat"] - L["caud_med"], L["mall_lat"] - L["mall_med"], lon)


FICHIER_CALIBRATION = Path(__file__).resolve().parent / "calibration_reperes.json"


def calibration():
    """Écart de définition entre ce détecteur et les repères du modèle de CORA 3D (os sain calibré sur les valeurs
    publiées) : pour chaque angle, (angle avec les repères détectés) − (angle avec les repères du modèle). Les deux
    sont mesurés sur le même os sain ; l'écart ne vient donc que des définitions des repères. Résultat mis en cache
    (calibration_reperes.json), recalculé si ce fichier source change."""
    import hashlib
    try:
        cle = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:12]
    except OSError:                    # application autonome : source dans l'archive, calibration livrée avec elle
        cle = None
    if FICHIER_CALIBRATION.exists():
        try:
            d = json.loads(FICHIER_CALIBRATION.read_text(encoding="utf-8"))
            if cle is None or d.get("cle") == cle:
                return d
        except ValueError:
            pass
    sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
    import modele_cora
    os_, rep, _ = modele_cora.charger()
    out = {"cle": cle, "explication": "écart = angle (repères détectés) − angle (repères du modèle), os sain du modèle "
                                      "CORA 3D ; valeur normale du programme = valeur publiée + écart", "os": {}}
    for type_os in ("femur", "tibia"):
        m = trimesh.Trimesh(*os_[type_os], process=True)
        fib = trimesh.Trimesh(*os_["fibula"], process=True) if type_os == "tibia" else None
        res, O = analyser(m, type_os, fib, None, calibrer=False)
        vrai = dict(rep[type_os], **(rep["fibula"] if type_os == "tibia" else {}))
        if type_os == "femur":
            O0 = Os(m)
            O0.R, O0.o = np.eye(3), np.zeros(3)
            O0.maj()
            a_vrai = angles_articulaires("femur", vrai, axe_anatomique(O0)[1])
            a_det = angles_articulaires("femur", res["reperes"], axe_anatomique(O)[1])
        else:
            a_vrai, a_det = angles_articulaires("tibia", vrai), angles_articulaires("tibia", res["reperes"])
        out["os"][type_os] = {k: {"modele": round(a_vrai[k], 2), "detecte": round(a_det[k], 2),
                                  "ecart": round(a_det[k] - a_vrai[k], 2)} for k in LITTERATURE[type_os]}
        # torsion : même définition des deux côtés (celle de CORA 3D : le modèle n'a pas les repères des définitions
        # publiées), plus la valeur publiée mesurée par le détecteur sur l'os sain du modèle
        out["os"][type_os]["torsion"] = {"modele": round(torsion(type_os, vrai, "cora3d"), 2),
                                         "detecte": round(torsion(type_os, res["reperes"], "cora3d"), 2),
                                         "publiee_detecte": round(torsion(type_os, res["reperes"]), 2)}
    try:
        FICHIER_CALIBRATION.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return out


def normales(type_os):
    """Valeurs normales dans la définition du programme : valeur publiée (travaux de l'équipe Vezzoni, sinon
    littérature) + écart de définition (modèle). aCdDFA n'a pas d'équivalent publié exact : sa référence est l'os sain
    du modèle mesuré par le détecteur."""
    cal = calibration()["os"][type_os]
    out = {}
    for k in LITTERATURE[type_os]:
        m, sd, src = VEZZONI[type_os].get(k, LITTERATURE[type_os][k])
        e = cal[k]["ecart"]
        if k == "aCdDFA":
            out[k] = {"publiee": m, "sd": sd, "source": src, "ecart_definition": e, "valeur": round(cal[k]["detecte"], 2),
                      "note": "pas de valeur publiée de même définition : os sain du modèle mesuré par le programme"}
        else:
            out[k] = {"publiee": m, "sd": sd, "source": src, "ecart_definition": e, "valeur": round(m + e, 2)}
    return out


# =============================================================================== série complète
def charger_tete(dossier):
    f = Path(dossier) / "reperes_auto.mrk.json"
    if not f.exists():
        return None
    try:
        for pt in json.loads(f.read_text(encoding="utf-8"))["markups"][0]["controlPoints"]:
            if pt["label"] == "tete_femorale":
                return np.array(pt["position"], float)
    except (KeyError, IndexError, ValueError):
        return None
    return None


def lire_rapport(dossier):
    f = Path(dossier) / "rapport.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def maillage_dans_repere(m, M):
    """Maillage exprimé dans le repère de l'os (matrice scanner -> os M, 4 × 4) ; si M contient le miroir (det < 0),
    l'ordre des sommets des triangles est inversé pour garder des normales sortantes."""
    v = np.asarray(m.vertices, float) @ M[:3, :3].T + M[:3, 3]
    f = np.asarray(m.faces)
    return v, (f[:, ::-1] if np.linalg.det(M[:3, :3]) < 0 else f)


def ecrire_binaire(chemin, v, f):
    """Format compact lu par l'application : nb sommets, nb triangles (uint32), sommets (float32), triangles (uint32)."""
    Path(chemin).write_bytes(np.array([len(v), len(f)], np.uint32).tobytes() + np.asarray(v, np.float32).tobytes()
                             + np.asarray(f, np.uint32).tobytes())


def fichiers_cora(dossier):
    """Fémurs et tibias d'un dossier de résultats : noms de fichier sans extension (« femur », « tibia_gauche »…)."""
    out = []
    for type_os in P.CORA_OS:
        for suffixe in ("", "_gauche", "_droit"):
            if (Path(dossier) / f"{type_os}{suffixe}.stl").exists():
                out.append(type_os + suffixe)
    return out


def traiter_os(dossier, nom, journal=print, images=True):
    """Analyse d'un os d'un dossier de résultats (nom = « femur », « tibia_droit »…) ; écrit cora_<nom>.json, .bin et
    .png. Renvoie le résultat."""
    dossier = Path(dossier)
    type_os, suffixe = nom.split("_")[0], nom[len(nom.split("_")[0]):]
    f = dossier / f"{nom}.stl"
    if not f.exists():
        raise FileNotFoundError(f"{f.name} absent de {dossier.name}")
    m = trimesh.load(f, process=True)
    ffib = dossier / f"fibula{suffixe}.stl"
    fib = trimesh.load(ffib, process=True) if type_os == "tibia" and ffib.exists() else None
    tete = charger_tete(dossier) if type_os == "femur" else None
    if tete is not None and np.min(np.linalg.norm(np.asarray(m.vertices) - tete, axis=1)) > 30:
        tete = None                                        # tête d'un autre os (autre côté) : ignorée
    rapport = lire_rapport(dossier)
    bords = rapport.get("os", {}).get(nom, {}).get("bords_volume")         # absent des anciens rapports
    systeme = rapport.get("parametres", {}).get("SYSTEME_COORDONNEES", "LPS")
    res, O = analyser(m, type_os, fib, tete, dossier.name, systeme, f.name, bords)
    res["nom"] = nom
    res["stl_modifie"] = f.stat().st_mtime
    if res.get("complet"):
        # maillages dans le repère de l'os (ceux que l'application CORA affiche et découpe)
        M = np.array(res["repere"]["scanner_vers_os"])
        ecrire_binaire(dossier / f"cora_{nom}.bin", *maillage_dans_repere(m, M))
        res["maillages"] = {type_os: f"cora_{nom}.bin"}
        if fib is not None:
            ecrire_binaire(dossier / f"cora_{nom}_fibula.bin", *maillage_dans_repere(fib, M))
            res["maillages"]["fibula"] = f"cora_{nom}_fibula.bin"
    (dossier / f"cora_{nom}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if res.get("complet"):
        journal(f"  {nom} : complet, membre {res['cote']}, longueur {res['longueur_mm']:.0f} mm, "
                f"{len(res['reperes'])} repères → cora_{nom}.json")
        if images:
            _sauver_png(O, {k: np.array(p) for k, p in res["reperes"].items()}, dossier / f"cora_{nom}.png",
                        f"{dossier.name} · {nom} (membre {res['cote']}) : repères pour CORA 3D")
    else:
        journal(f"  {nom} : pas d'analyse CORA ({res['raison']})")
    return res


def traiter_serie(dossier, journal=print, images=True):
    """Tous les fémurs et tibias d'un dossier de résultats."""
    out = {}
    for nom in fichiers_cora(dossier):
        try:
            out[nom] = traiter_os(dossier, nom, journal, images)
        except Exception as exc:                           # un os inexploitable ne bloque pas les autres
            journal(f"  {nom} : échec de l'analyse ({exc})")
            out[nom] = {"complet": False, "raison": f"échec de l'analyse : {exc}"}
    return out


def ecart_aux_normes(r):
    """Somme des écarts aux valeurs normales, en écarts-types (0 = os parfaitement dans la moyenne)."""
    N, A = r.get("normales") or {}, r.get("angles") or {}
    return float(sum(abs(A[k] - N[k]["valeur"]) / N[k]["sd"] for k in N if k in A and N[k].get("sd")))


def choisir_cible(dossier, resultats=None):
    """L'os à planifier pour ce cas (un dossier DICOM = un fémur OU un tibia) : l'os complet du scanner. S'il y en a
    plusieurs : l'os le plus éloigné des normes ; si c'est le même os des deux côtés (scanner des deux membres), l'autre
    côté devient la référence (membre controlatéral). Écrit cora_cas.json et le renvoie."""
    dossier = Path(dossier)
    res = {}
    for nom in fichiers_cora(dossier):
        r = (resultats or {}).get(nom)
        if r is None and (dossier / f"cora_{nom}.json").exists():
            r = json.loads((dossier / f"cora_{nom}.json").read_text(encoding="utf-8"))
        if r is not None:
            res[nom] = r
    candidats = [{"nom": n, "os": n.split("_")[0], "complet": bool(r.get("complet")), "raison": r.get("raison", ""),
                  "cote": r.get("cote"), "longueur_mm": r.get("longueur_mm"),
                  "ecart_normes": round(ecart_aux_normes(r), 2) if r.get("complet") else None} for n, r in res.items()]
    complets = sorted((c for c in candidats if c["complet"]), key=lambda c: -c["ecart_normes"])
    cas = {"serie": dossier.name, "cible": None, "controlateral": None, "candidats": candidats, "raison": ""}
    if not complets:
        cas["raison"] = ("aucun fémur ni tibia complet dans ce scanner : "
                         + "; ".join(f"{c['nom']} : {c['raison']}" for c in candidats)) if candidats else \
            "aucun fémur ni tibia segmenté dans ce scanner"
    else:
        cas["cible"] = complets[0]["nom"]
        autres = [c for c in complets[1:] if c["os"] == complets[0]["os"]]
        if autres:
            cas["controlateral"] = autres[0]["nom"]
        if len(complets) == 1:
            cas["raison"] = f"seul os complet du scanner ({complets[0]['nom']})"
        elif autres:
            cas["raison"] = (f"les deux {complets[0]['os']}s sont complets : {complets[0]['nom']} est le plus éloigné des "
                             f"normes ; {autres[0]['nom']} sert de membre controlatéral")
        else:
            cas["raison"] = (f"plusieurs os complets ({', '.join(c['nom'] for c in complets)}) : {complets[0]['nom']} est "
                             "le plus éloigné des normes (choix modifiable)")
    (dossier / "cora_cas.json").write_text(json.dumps(cas, ensure_ascii=False, indent=1), encoding="utf-8")
    return cas


def ajouter_au_rapport(dossier, resultats):
    """Résumé de l'étape 6 dans rapport.json (clé « cora ») et rapport.md (section « Repères pour CORA 3D »)."""
    dossier = Path(dossier)
    resume = {}
    for type_os, r in resultats.items():
        resume[type_os] = {k: r.get(k) for k in ("complet", "raison", "cote", "longueur_mm", "angles", "torsion_deg")}
    fj = dossier / "rapport.json"
    if fj.exists():
        d = json.loads(fj.read_text(encoding="utf-8"))
        d["cora"] = resume
        fj.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    fm = dossier / "rapport.md"
    if fm.exists():
        texte = fm.read_text(encoding="utf-8").split("\n## Repères pour CORA 3D")[0].rstrip() + "\n\n## Repères pour CORA 3D\n\n"
        for type_os, r in resultats.items():
            if r.get("complet"):
                N = r.get("normales", {})
                ang = ", ".join(f"{k} {v:.1f}°" + (f" (normal {N[k]['valeur']:.1f} ± {N[k]['sd']:.1f})" if k in N else "")
                                for k, v in r["angles"].items() if k != "longueur")
                texte += (f"* **{type_os}** : complet, membre {r['cote']} (analysé comme un membre droit"
                          f"{', par symétrie' if r.get('miroir') else ''}), {len(r['reperes'])} repères → "
                          f"`cora_{type_os}.json`, `cora_{type_os}.png`. Angles : {ang}.\n")
            else:
                texte += f"* **{type_os}** : pas d'analyse CORA ({r.get('raison', '')})\n"
        fm.write_text(texte, encoding="utf-8")


def main():
    a = argparse.ArgumentParser(description="Repères anatomiques automatiques (fémur, tibia) pour CORA 3D")
    a.add_argument("dossiers", nargs="*", type=Path, help="dossiers resultats/<série> (défaut : tous)")
    a.add_argument("--os", help="un seul os (femur, tibia, tibia_gauche…)")
    a.add_argument("--sans-images", action="store_true")
    x = a.parse_args()
    dossiers = x.dossiers or sorted(d for d in P.RESULTATS.iterdir() if d.is_dir())
    for d in dossiers:
        print(f"── {d.name} ──")
        if x.os:
            traiter_os(d, x.os, images=not x.sans_images)
        else:
            r_ = traiter_serie(d, images=not x.sans_images)
            ajouter_au_rapport(d, r_)
            c_ = choisir_cible(d, r_)
            print(f"  os à planifier : {c_['cible'] or 'aucun'} ({c_['raison']})")


if __name__ == "__main__":
    sys.exit(main())
