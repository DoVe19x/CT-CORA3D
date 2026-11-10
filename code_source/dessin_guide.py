"""
dessin_guide.py — plans 2D du guide (CT-CORA3D, étape 7), présentés comme des plans de pièce industrielle.

Rôle    : 1. plan GÉNÉRIQUE (plan_generique.svg / .pdf / .png) : le guide en schéma de principe (coupe dans le plan
             d'une fente, vue de la face d'appui, coupe d'un manchon), ses cotes en SYMBOLES (j, e, g, p, s, js, Øb, jb,
             m, hp, α, eb, kd) et le tableau des paramètres (valeur par défaut, valeur de ce cas) : c'est le « modèle
             paramétrique » du guide, comme une pièce pilotée par une table.
          2. plan COTÉ du cas (plan_guide.svg / .pdf / .png) : le guide construit pour CET os, en projections
             orthogonales (vue de face A depuis la face d'appui, vue de gauche B, vue de dessus C, coupe E-E par les
             manchons), le guide de réduction (vue D, le long des broches), une vue isométrique, les cotes, la
             nomenclature avec les repères des pièces, le tableau des cotes du cas et le mode opératoire.
Mise en page (normes ISO de dessin technique, comme un plan fait dans AutoCAD) :
          - format A3 paysage, cadre avec marge de reliure, repères de zones 1 à 8 et A à F, repères de centrage
            (ISO 5457) ; cartouche en bas à droite avec le logo de l'ECAM, le numéro du plan, l'échelle, le symbole de
            projection, « dessiné / vérifié / approuvé » (ISO 7200) ; nomenclature au-dessus du cartouche ;
          - projection européenne (ISO 128 / 5456-2) : la vue de gauche B est à DROITE de la vue de face A, la vue de
            dessus C est SOUS la vue A, et les vues sont alignées (mêmes cotes de hauteur et de largeur) ;
          - traits : forts 0,35 mm (arêtes vues), fins 0,18 mm (cotes, hachures), mixtes fins (axes des broches),
            mixtes à deux points (plans de coupe de l'os), ondulés (os interrompu) ; l'os, pièce voisine, est en gris ;
          - cotes ISO 129 : lignes d'attache, flèches pleines, valeur au-dessus de la ligne, lisible depuis le bas ou
            depuis la droite ; coupe hachurée à 45° (os hachuré en gris dans l'autre sens).
Entrées : celles de etape7_guide.generer (prescription, guide.json, maillages manifold3d, repère du guide).
Méthode : projection orthogonale ; parties cachées par un tampon de profondeur (z-buffer en numpy : chaque pixel garde
          le triangle le plus proche ; faces arrière des solides fermés ignorées ; ≈ 180 points par pouce sur la
          feuille) ; traits = arêtes de silhouette et arêtes vives (> 35°) VISIBLES, en vecteurs ; aplats en image dans
          le fichier (fichiers vectoriels légers). Coupe E-E : solides coupés exactement (manifold3d trim_by_plane et
          slice ; os : trimesh). matplotlib, moteur « Agg » (sans écran).
"""
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402
import numpy as np                                                 # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Arc, Circle, PathPatch, Polygon, Rectangle  # noqa: E402
from matplotlib.path import Path as CheminMPL  # noqa: E402

A3 = (420.0, 297.0)                    # mm, paysage
CADRE = (20.0, 10.0, 410.0, 287.0)     # cadre du dessin (x0, y0, x1, y1) : marge de reliure de 20 mm à gauche
PT = 72.0 / 25.4                       # points (unité de matplotlib) par millimètre
TRAIT_FORT, TRAIT_FIN, TRAIT_CADRE = 0.35 * PT, 0.18 * PT, 0.7 * PT
NOIR, GRIS, GRIS_OS = "#000000", "#5a5a5a", "#8c8c8c"
OS_FOND = (0.905, 0.905, 0.905)        # os (pièce voisine) : aplat gris clair
BLANC = (1.0, 1.0, 1.0)
FLECHE = 2.5                           # longueur des flèches de cote (mm de papier)
T_COTE = 7.5                           # taille des valeurs de cote (points)
AXE = (0, (8 * PT, 1.0 * PT, 0.5 * PT, 1.0 * PT))                           # trait mixte fin (axes)
PLAN = (0, (8 * PT, 1.0 * PT, 0.5 * PT, 1.0 * PT, 0.5 * PT, 1.0 * PT))      # trait mixte à deux points (plans de coupe)
CACHE = (0, (3 * PT, 1.2 * PT))                                             # trait interrompu fin
LOGO = Path(__file__).resolve().parent / "logo_ecam.png"
ECOLE = ("ECAM Brussels Engineering School", "Master en ingénierie biomédicale")
PROJET = "Projet PMD2 · CT-CORA3D"     # projet de groupe : pas de nom d'auteur sur les plans
PLANIF_DEFAUT = {"ecart_broches_mm": 10.0, "facteur_distance_broches": 1.2}   # planification (cœur JavaScript)
STYLE = {"font.family": "DejaVu Sans", "font.size": 7, "svg.fonttype": "none", "pdf.fonttype": 42,
         "lines.scale_dashes": False}


def _fr(x, d=1):
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


def _unitaire(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


# --------------------------------------------------------------------------- projection, parties cachées
def _projeter(v, vue):
    """Coordonnées dans le plan de la vue : (horizontal, vertical, profondeur vers l'observateur)."""
    return (np.asarray(v, float) - vue["o"]) @ np.vstack([vue["x"], vue["y"], vue["z"]]).T


def _rendu(tris, couleurs, lims, pas, bloc=3_000_000):
    """Tampon de profondeur (z-buffer) en numpy : chaque pixel prend le triangle le plus proche de l'observateur (z le
    plus grand), testé au centre du pixel. Une seule passe : pour chaque triangle, les pixels de sa boîte englobante
    (triangles regroupés par taille de boîte, calcul vectorisé par blocs de `bloc` pixels candidats) ; le plus proche
    est gardé par un maximum sur une clé (profondeur codée sur 31 bits, puis numéro du triangle).
    Renvoie l'image de profondeur (mm, −inf = fond), l'image couleur (RGB 0-1, fond blanc) et (xa, ya, pas, nx, ny) ;
    lignes 0 = bas."""
    xa, xb, ya, yb = lims
    nx, ny = int(np.ceil((xb - xa) / pas)), int(np.ceil((yb - ya) / pas))
    if not len(tris):
        return np.full((ny, nx), -np.inf), np.ones((ny, nx, 3)), (xa, ya, pas, nx, ny)
    X = (tris[:, :, 0] - xa) / pas - 0.5                         # le centre du pixel (i, j) est au point (i, j)
    Y = (tris[:, :, 1] - ya) / pas - 0.5
    Z = tris[:, :, 2]
    i0 = np.maximum(np.ceil(X.min(1)), 0).astype(np.int64)
    i1 = np.minimum(np.floor(X.max(1)), nx - 1).astype(np.int64)
    j0 = np.maximum(np.ceil(Y.min(1)), 0).astype(np.int64)
    j1 = np.minimum(np.floor(Y.max(1)), ny - 1).astype(np.int64)
    aire = (X[:, 1] - X[:, 0]) * (Y[:, 2] - Y[:, 0]) - (X[:, 2] - X[:, 0]) * (Y[:, 1] - Y[:, 0])   # 2 × aire signée
    w, h = i1 - i0 + 1, j1 - j0 + 1
    garde = np.nonzero((w > 0) & (h > 0) & (np.abs(aire) > 1e-12))[0]   # (vus par la tranche : invisibles)
    zmin, zmax = (float(Z.min()), float(Z.max())) if len(Z) else (0.0, 1.0)
    kz = (2 ** 31 - 2) / max(zmax - zmin, 1e-9)
    tampon = np.zeros(nx * ny, np.int64)                         # (profondeur codée << 32) | triangle ; 0 = fond
    taille = w[garde] * (ny + 1) + h[garde]
    ordre = np.argsort(taille, kind="stable")
    garde, taille = garde[ordre], taille[ordre]
    debuts = np.r_[0, np.nonzero(np.diff(taille))[0] + 1, len(garde)]
    for a, b in zip(debuts[:-1], debuts[1:]):
        if a == b:
            continue
        W, H = int(w[garde[a]]), int(h[garde[a]])
        dx, dy = np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64)
        for c in range(a, b, max(1, bloc // (W * H))):
            t = garde[c:min(b, c + max(1, bloc // (W * H)))]
            px = i0[t][:, None, None] + dx[None, None, :]
            py = j0[t][:, None, None] + dy[None, :, None]
            x0, x1, x2 = (X[t, k][:, None, None] for k in range(3))
            y0, y1, y2 = (Y[t, k][:, None, None] for k in range(3))
            e0 = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)       # fonctions d'arête : poids barycentriques × 2 aire
            e1 = (x0 - x2) * (py - y2) - (y0 - y2) * (px - x2)
            e2 = (x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)
            s = np.sign(aire[t])[:, None, None]
            tol = -1e-9 * np.abs(aire[t])[:, None, None]            # un centre de pixel sur une arête commune : pris
            n_, jj, ii = np.nonzero((s * e0 >= tol) & (s * e1 >= tol) & (s * e2 >= tol))
            if not len(n_):
                continue
            z = (e0[n_, jj, ii] * Z[t[n_], 0] + e1[n_, jj, ii] * Z[t[n_], 1] + e2[n_, jj, ii] * Z[t[n_], 2]) / aire[t[n_]]
            code = np.clip(np.rint((z - zmin) * kz), 0, 2 ** 31 - 2).astype(np.int64) + 1
            np.maximum.at(tampon, (j0[t[n_]] + jj) * nx + i0[t[n_]] + ii, (code << 32) | t[n_])
    code, tri = tampon >> 32, tampon & 0xFFFFFFFF
    fond = code == 0
    prof = np.where(fond, -np.inf, zmin + (code - 1) / kz).reshape(ny, nx)
    img = np.where(fond[:, None], 1.0, couleurs[tri]).reshape(ny, nx, 3)
    return prof, img, (xa, ya, pas, nx, ny)


def _aretes(f, q, angle_vif=35.0):
    """Arêtes de silhouette (une face vers l'observateur, l'autre non), arêtes vives et bords d'un maillage projeté q."""
    t = q[f]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    devant = n[:, 2] > 0
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    fi = np.tile(np.arange(len(f)), 3)
    uniq, inv, cnt = np.unique(np.sort(e, axis=1), axis=0, return_inverse=True, return_counts=True)
    ordre = np.argsort(inv.ravel(), kind="stable")
    debut = np.r_[0, np.cumsum(cnt)[:-1]]
    deux = cnt == 2
    fa, fb = fi[ordre][debut[deux]], fi[ordre][debut[deux] + 1]
    vive = np.einsum("ij,ij->i", n[fa], n[fb]) < np.cos(np.radians(angle_vif))
    garde = (devant[fa] != devant[fb]) | (vive & (devant[fa] | devant[fb]))
    return np.vstack([uniq[deux][garde], uniq[~deux]])


def _visibles(seg3, prof, info, tol=0.35, pas_seg=0.8):
    """Morceaux visibles de segments 3D (repère de vue) d'après l'image de profondeur."""
    xa, ya, pas, nx, ny = info
    a, b = seg3[:, 0], seg3[:, 1]
    L = np.linalg.norm(b[:, :2] - a[:, :2], axis=1)
    k = np.maximum(1, np.ceil(L / pas_seg)).astype(int)
    idx = np.repeat(np.arange(len(seg3)), k)
    j = np.concatenate([np.arange(x) for x in k])
    t0, t1 = j / k[idx], (j + 1) / k[idx]
    p0 = a[idx] + (b[idx] - a[idx]) * t0[:, None]
    p1 = a[idx] + (b[idx] - a[idx]) * t1[:, None]
    m = (p0 + p1) / 2
    ix = np.clip(((m[:, 0] - xa) / pas).astype(int), 0, nx - 1)
    iy = np.clip(((m[:, 1] - ya) / pas).astype(int), 0, ny - 1)
    # profondeur la plus proche dans un voisinage de 1 pixel (le trait est au bord de sa face)
    zb = prof[iy, ix]
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        zb = np.minimum(zb, prof[np.clip(iy + dy, 0, ny - 1), np.clip(ix + dx, 0, nx - 1)])
    vis = m[:, 2] >= zb - tol
    return np.stack([p0[vis, :2], p1[vis, :2]], 1)


def _dessiner_vue(ax, pieces, vue, lims, pas, ombre=False, lw_fort=TRAIT_FORT, decoupe=None, angle_vif=35.0):
    """pieces : [(sommets, triangles, couleur RGB, trait)], trait = « fort » (pièce : solide fermé, arêtes en trait
    fort noir), « fin » (os : arêtes en trait fin gris) ou None. ombre=False : aplats unis (dessin au trait) ; True :
    ombrage selon l'orientation des faces (vue isométrique). Les faces arrière des solides fermés sont ignorées (moitié
    moins de travail) ; l'os, découpé autour du guide, est ouvert : rendu en entier. decoupe : rectangle (x0, x1, y0,
    y1) hors duquel l'os n'est pas dessiné (os interrompu, voir _os_interrompu)."""
    tris, cols = [], []
    for v, f, c, trait in pieces:
        t = _projeter(v, vue)[f]
        if not len(t):
            continue
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        if trait == "fort":
            # sens des faces : signe du volume, calculé dans le repère de la vue (juste même si ce repère est inversé)
            signe = 1.0 if np.einsum("ij,ij->", np.cross(t[:, 0], t[:, 1]), t[:, 2]) >= 0 else -1.0
            devant = signe * n[:, 2] > 0
            t, n = t[devant], n[devant]
        nz = np.abs(n[:, 2]) / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
        fac = (0.62 + 0.38 * nz[:, None]) if ombre else np.ones((len(t), 1))
        tris.append(t)
        cols.append(np.clip(np.asarray(c, float)[None, :] * fac, 0, 1))
    prof, img, info = _rendu(np.concatenate(tris), np.concatenate(cols), lims, pas)
    xa, ya, p_, nx, ny = info
    if decoupe is not None:                       # os interrompu : rien hors du rectangle (le guide y est tout entier)
        xs = xa + (np.arange(nx) + 0.5) * p_
        ys = ya + (np.arange(ny) + 0.5) * p_
        hors = (ys[:, None] < decoupe[2]) | (ys[:, None] > decoupe[3]) | (xs[None, :] < decoupe[0]) \
            | (xs[None, :] > decoupe[1])
        prof = np.where(hors, -np.inf, prof)
    rgba = np.dstack([img, np.where(np.isfinite(prof), 1.0, 0.0)])
    ax.imshow(rgba, origin="lower", extent=(xa, xa + nx * p_, ya, ya + ny * p_), interpolation="bilinear", zorder=1,
              rasterized=True, aspect="auto")
    for v, f, c, trait in pieces:
        if not trait or not len(f):
            continue
        q = _projeter(v, vue)
        seg = _visibles(q[_aretes(f, q, angle_vif)], prof, info)
        if decoupe is not None and trait == "fin" and len(seg):
            m_ = seg.mean(1)
            seg = seg[(m_[:, 0] >= decoupe[0]) & (m_[:, 0] <= decoupe[1]) & (m_[:, 1] >= decoupe[2])
                      & (m_[:, 1] <= decoupe[3])]
        if len(seg):
            ax.add_collection(LineCollection(seg, colors=NOIR if trait == "fort" else GRIS_OS,
                                             linewidths=lw_fort if trait == "fort" else TRAIT_FIN * 0.8, zorder=3,
                                             capstyle="round"), autolim=False)
    ax.set_xlim(lims[0], lims[1])
    ax.set_ylim(lims[2], lims[3])
    return prof, info


def _os_interrompu(ax, prof, info, y):
    """Trait ondulé fin (ISO 128 : limite d'une vue partielle) à travers l'os, à l'ordonnée y de la vue."""
    xa, ya, p_, nx, ny = info
    j = int(np.clip((y - ya) / p_, 0, ny - 1))
    lignes = [np.isfinite(prof[min(max(j + d, 0), ny - 1)]) for d in (-3, 0, 3)]
    pleins = np.nonzero(np.any(lignes, axis=0))[0]
    if not len(pleins):
        return
    k = 1.0 / _mm(ax)
    x0, x1 = xa + pleins.min() * p_ - 0.8 * k, xa + (pleins.max() + 1) * p_ + 0.8 * k
    xs = np.linspace(x0, x1, 80)
    ax.plot(xs, y + 0.9 * k * np.sin(2 * np.pi * (xs - x0) / (7.0 * k)), color=GRIS_OS, lw=TRAIT_FIN, zorder=3)


def _section(v, f, R, o):
    """Contours de la section d'un maillage FERMÉ par le plan z = 0 du repère (lignes de R : x, y, z ; origine o),
    en coordonnées (x, y) de ce repère ; liste vide si le maillage n'est pas un solide valide."""
    try:
        import manifold3d as m3d
        man = m3d.Manifold(m3d.Mesh(vert_properties=np.ascontiguousarray(v, np.float32),
                                    tri_verts=np.ascontiguousarray(f, np.uint32)))
        if man.status() != m3d.Error.NoError:
            return []
        R = np.asarray(R, float)
        return [np.asarray(p_, float) for p_ in man.transform(np.column_stack([R, -R @ o])).slice(0.0).to_polygons()]
    except Exception:
        return []


def _point_visible(v, vue, prof, info, tol=0.3):
    """Un point visible de la pièce (sommet visible le plus proche du centre de ses sommets visibles)."""
    q = _projeter(v, vue)
    xa, ya, p_, nx, ny = info
    ix = np.clip(((q[:, 0] - xa) / p_).astype(int), 0, nx - 1)
    iy = np.clip(((q[:, 1] - ya) / p_).astype(int), 0, ny - 1)
    vis = q[:, 2] >= prof[iy, ix] - tol
    qv = q[vis, :2] if vis.any() else q[:, :2]
    c = np.median(qv, 0)
    return qv[np.argmin(((qv - c) ** 2).sum(1))]


# --------------------------------------------------------------------------- habillage ISO : cotes, repères, hachures
def _mm(ax):
    """Millimètres de papier par unité de données de l'axe (même échelle en x et en y)."""
    x0, x1 = ax.get_xlim()
    return ax.get_position().width * A3[0] / (x1 - x0)


def _fleche(ax, pointe, d, k, couleur=NOIR):
    """Flèche pleine (ISO 129) dont la pointe est en `pointe` et qui va dans la direction d ; k = données par mm."""
    d = _unitaire(d)
    p = np.array([-d[1], d[0]])
    base = np.asarray(pointe, float) - d * FLECHE * k
    ax.add_patch(Polygon([pointe, base + p * 0.48 * k, base - p * 0.48 * k], closed=True, fc=couleur, ec="none",
                         zorder=10, clip_on=False))


def _cote(ax, a, b, decal, texte, taille=T_COTE, couleur=NOIR, fond_blanc=False):
    """Cote ISO 129 entre les points a et b (données de la vue). La ligne de cote est décalée du vecteur `decal`, en
    mm de PAPIER ; lignes d'attache à 1 mm de la pièce et 2 mm au-delà de la ligne de cote ; flèches pleines (dehors
    si la cote est trop courte) ; valeur au-dessus de la ligne, lisible depuis le bas ou depuis la droite."""
    k = 1.0 / _mm(ax)
    a, b, dv = np.asarray(a, float), np.asarray(b, float), np.asarray(decal, float)
    n = _unitaire(dv) if np.linalg.norm(dv) > 0 else np.zeros(2)
    a2, b2 = a + dv * k, b + dv * k
    kw = dict(color=couleur, lw=TRAIT_FIN, zorder=9, clip_on=False, solid_capstyle="butt")
    if np.linalg.norm(dv) > 1.5:
        for p in (a, b):
            ax.plot([p[0] + n[0] * k, p[0] + dv[0] * k + n[0] * 2 * k],
                    [p[1] + n[1] * k, p[1] + dv[1] * k + n[1] * 2 * k], **kw)
    d = _unitaire(b2 - a2)
    if np.linalg.norm(b2 - a2) / k >= 2 * FLECHE + 1.5:
        ax.plot(*np.c_[a2, b2], **kw)
        _fleche(ax, a2, -d, k, couleur)
        _fleche(ax, b2, d, k, couleur)
    else:
        e = (FLECHE + 2.5) * k
        ax.plot(*np.c_[a2 - d * e, b2 + d * e], **kw)
        _fleche(ax, a2, d, k, couleur)
        _fleche(ax, b2, -d, k, couleur)
    ang = float(np.degrees(np.arctan2(d[1], d[0])))
    if ang > 90.01:
        ang -= 180
    elif ang <= -89.99:
        ang += 180
    haut = np.array([-np.sin(np.radians(ang)), np.cos(np.radians(ang))])
    m = (a2 + b2) / 2 + haut * 0.7 * k
    ax.text(m[0], m[1], texte, fontsize=taille, ha="center", va="bottom", rotation=ang, rotation_mode="anchor",
            color=couleur, zorder=10, clip_on=False,
            bbox=dict(boxstyle="square,pad=0.12", fc="white", ec="none") if fond_blanc else None)


def _note(ax, p, texte, dxy, taille=7.0, point=True):
    """Ligne de repère (ISO 128 : point sur une surface) vers une indication écrite ; dxy en mm de papier."""
    k = 1.0 / _mm(ax)
    p = np.asarray(p, float)
    q = p + np.asarray(dxy, float) * k
    s = 1.0 if dxy[0] >= 0 else -1.0
    r = q + np.array([s * 2.5 * k, 0.0])
    ax.plot([p[0], q[0], r[0]], [p[1], q[1], r[1]], color=NOIR, lw=TRAIT_FIN, zorder=12, clip_on=False)
    if point:
        ax.add_patch(Circle(p, 0.42 * k, color=NOIR, zorder=12, clip_on=False))
    ax.text(r[0] + s * 0.8 * k, r[1], texte, ha="left" if s > 0 else "right", va="center", fontsize=taille,
            zorder=12, clip_on=False, linespacing=1.15)


def _ballon(ax, p, q, numero):
    """Repère de pièce : cercle numéroté en q relié par une ligne de repère au point p de la pièce."""
    k = 1.0 / _mm(ax)
    p, q = np.asarray(p, float), np.asarray(q, float)
    r = 3.4 * k
    a = q + _unitaire(p - q) * r
    ax.plot([a[0], p[0]], [a[1], p[1]], color=NOIR, lw=TRAIT_FIN, zorder=12, clip_on=False)
    ax.add_patch(Circle(p, 0.42 * k, color=NOIR, zorder=12, clip_on=False))
    ax.add_patch(Circle(q, r, fc="white", ec=NOIR, lw=TRAIT_FORT * 0.8, zorder=12, clip_on=False))
    ax.text(q[0], q[1], str(numero), ha="center", va="center", fontsize=9, fontweight="bold", zorder=13,
            clip_on=False)


def _ligne(ax, a, b, style=AXE, lw=TRAIT_FIN, couleur=NOIR, zorder=8, dans_vue=False):
    ax.plot([a[0], b[0]], [a[1], b[1]], color=couleur, lw=lw, ls=style, zorder=zorder, clip_on=dans_vue,
            solid_capstyle="butt", dash_capstyle="butt")


def _trait_coupe(ax, a, b, vers, lettre):
    """Plan de coupe d'une coupe (ISO 128) : trait mixte fin renforcé aux extrémités, flèches du sens d'observation
    et lettres."""
    k = 1.0 / _mm(ax)
    a, b, vers = np.asarray(a, float), np.asarray(b, float), _unitaire(vers)
    d = _unitaire(b - a)
    _ligne(ax, a, b, AXE, zorder=11)
    for p, s in ((a, 1.0), (b, -1.0)):
        _ligne(ax, p, p + s * d * 5 * k, "-", TRAIT_FORT * 1.6, zorder=11)
        t = p + vers * 7 * k
        _ligne(ax, p, t - vers * FLECHE * k, "-", TRAIT_FIN, zorder=11)
        _fleche(ax, t, vers, k)
        c = t + vers * 2.6 * k
        ax.text(c[0], c[1], lettre, ha="center", va="center", fontsize=10, fontweight="bold", zorder=12,
                clip_on=False)


def _dans_boite(c, d, lo, hi):
    """Segment de la droite c + t·d contenu dans la boîte [lo, hi] (None si elle ne la traverse pas)."""
    t0, t1 = -np.inf, np.inf
    for i in range(2):
        if abs(d[i]) < 1e-12:
            if not lo[i] <= c[i] <= hi[i]:
                return None
            continue
        ta, tb = sorted(((lo[i] - c[i]) / d[i], (hi[i] - c[i]) / d[i]))
        t0, t1 = max(t0, ta), min(t1, tb)
    return None if t0 >= t1 else (c + t0 * d, c + t1 * d)


def _demi_plan(poly, n, c):
    """Sutherland–Hodgman : la partie du polygone où n·p ≥ c (None si elle est vide)."""
    P = np.asarray(poly, float)
    out = []
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        da, db = a @ n - c, b @ n - c
        if da >= 0:
            out.append(a)
        if (da >= 0) != (db >= 0):
            out.append(a + da / (da - db) * (b - a))
    return np.array(out) if len(out) >= 3 else None


def _orienter(anneaux):
    """Contours dans le sens direct, trous dans le sens indirect (d'après leur imbrication) : remplissage juste."""
    res = []
    for i, r in enumerate(anneaux):
        dedans = sum(CheminMPL(o).contains_point(r[0]) for j, o in enumerate(anneaux) if j != i)
        aire = 0.5 * np.sum(r[:, 0] * np.roll(r[:, 1], -1) - np.roll(r[:, 0], -1) * r[:, 1])
        res.append(r if (aire > 0) == (dedans % 2 == 0) else r[::-1])
    return res


def _hachures(ax, anneaux, angle=45.0, pas_mm=1.3, couleur=NOIR, contour=NOIR, zorder=5):
    """Surface coupée (ISO 128-50) : polygones (trous compris) remplis de blanc, hachures fines à `angle`° espacées de
    `pas_mm` mm de papier, contour en trait fort."""
    anneaux = [np.asarray(r, float) for r in anneaux if r is not None and len(r) >= 3]
    if not anneaux:
        return
    anneaux = _orienter(anneaux)
    sommets, codes = [], []
    for r in anneaux:
        sommets += [*r, r[0]]
        codes += [CheminMPL.MOVETO] + [CheminMPL.LINETO] * (len(r) - 1) + [CheminMPL.CLOSEPOLY]
    patch = PathPatch(CheminMPL(np.array(sommets), codes), fc="white", ec=contour or "none", lw=TRAIT_FORT,
                      zorder=zorder)
    ax.add_patch(patch)
    k = 1.0 / _mm(ax)
    pas = pas_mm * k
    pts = np.vstack(anneaux)
    lo, hi = pts.min(0), pts.max(0)
    a = np.radians(angle)
    u = np.array([np.cos(a), np.sin(a)])
    nrm = np.array([-u[1], u[0]])
    c = (lo + hi) / 2
    R = np.linalg.norm(hi - lo) / 2 + pas
    decal = np.arange(np.floor((c @ nrm - R) / pas), np.ceil((c @ nrm + R) / pas) + 1) * pas
    segs = [np.array([nrm * o + u * (c @ u - R), nrm * o + u * (c @ u + R)]) for o in decal]
    lc = LineCollection(segs, colors=couleur, linewidths=TRAIT_FIN, zorder=zorder + 0.1)
    ax.add_collection(lc, autolim=False)
    lc.set_clip_path(patch)


# --------------------------------------------------------------------------- feuille, cartouche, tableaux
def _feuille():
    """Feuille A3 : cadre (marge de reliure à gauche), repères de zones 1-8 / A-F et repères de centrage (ISO 5457)."""
    fig = plt.figure(figsize=(A3[0] / 25.4, A3[1] / 25.4))
    fond = fig.add_axes([0, 0, 1, 1])
    fond.set_xlim(0, A3[0])
    fond.set_ylim(0, A3[1])
    fond.axis("off")
    x0, y0, x1, y1 = CADRE
    e = 5.0
    fond.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=TRAIT_CADRE, ec=NOIR, zorder=20))
    fond.add_patch(Rectangle((x0 - e, y0 - e), x1 - x0 + 2 * e, y1 - y0 + 2 * e, fill=False, lw=TRAIT_FIN, ec=NOIR))
    nc, nl = 8, 6
    for i in range(nc + 1):
        x = x0 + (x1 - x0) * i / nc
        if 0 < i < nc:
            fond.plot([x, x], [y1, y1 + e], color=NOIR, lw=TRAIT_FIN)
            fond.plot([x, x], [y0 - e, y0], color=NOIR, lw=TRAIT_FIN)
        if i < nc:
            xm = x0 + (x1 - x0) * (i + 0.5) / nc
            for y in (y1 + e / 2, y0 - e / 2):
                fond.text(xm, y, str(i + 1), ha="center", va="center", fontsize=6.5, color=NOIR)
    for j in range(nl + 1):
        y = y1 - (y1 - y0) * j / nl
        if 0 < j < nl:
            fond.plot([x0 - e, x0], [y, y], color=NOIR, lw=TRAIT_FIN)
            fond.plot([x1, x1 + e], [y, y], color=NOIR, lw=TRAIT_FIN)
        if j < nl:
            ym = y1 - (y1 - y0) * (j + 0.5) / nl
            for x in (x0 - e / 2, x1 + e / 2):
                fond.text(x, ym, "ABCDEF"[j], ha="center", va="center", fontsize=6.5, color=NOIR)
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2                 # repères de centrage
    for a, b in (((xm, A3[1] - 1), (xm, y1 - 5)), ((xm, 1), (xm, y0 + 5)), ((x0 - e - 3, ym), (x0 + 5, ym)),
                 ((A3[0] - 1, ym), (x1 - 5, ym))):
        fond.plot([a[0], b[0]], [a[1], b[1]], color=NOIR, lw=TRAIT_CADRE, zorder=21)
    return fig, fond


def _symbole_projection(fond, cx, cy):
    """Symbole de la projection européenne (ISO 5456-2) : tronc de cône vu de face, et vu de gauche placé à droite."""
    lw = TRAIT_FIN * 1.3
    fond.add_patch(Polygon([(cx - 6.6, cy - 1.4), (cx - 1.4, cy - 2.8), (cx - 1.4, cy + 2.8), (cx - 6.6, cy + 1.4)],
                           closed=True, fill=False, ec=NOIR, lw=lw, zorder=24))
    for r in (2.8, 1.4):
        fond.add_patch(Circle((cx + 3.6, cy), r, fill=False, ec=NOIR, lw=lw, zorder=24))
    mixte = (0, (3 * PT, 0.6 * PT, 0.4 * PT, 0.6 * PT))
    _ligne(fond, (cx - 7.6, cy), (cx + 7.4, cy), mixte, TRAIT_FIN * 0.7, zorder=24)
    _ligne(fond, (cx + 3.6, cy - 3.8), (cx + 3.6, cy + 3.8), mixte, TRAIT_FIN * 0.7, zorder=24)


def _case(fond, x, y, l, h, etiquette, valeur, taille=7.5, gras=False, centre=False):
    fond.add_patch(Rectangle((x, y), l, h, fill=False, lw=TRAIT_FIN, ec=NOIR, zorder=22))
    if etiquette:
        fond.text(x + 1.0, y + h - 0.9, etiquette, fontsize=4.8, color=GRIS, va="top", ha="left", zorder=23)
    if valeur:
        fond.text(x + (l / 2 if centre else 1.5), y + (h - 2.0) / 2, valeur, fontsize=taille, color=NOIR,
                  va="center", ha="center" if centre else "left", fontweight="bold" if gras else "normal", zorder=23)


def _cartouche(fond, titre, designation, numero, echelle, matiere, tolerances, feuille="1 / 1", revision="A"):
    """Cartouche (ISO 7200) de 180 × 52 mm dans le coin inférieur droit du cadre, avec le logo de l'ECAM."""
    X0, Y0 = CADRE[2] - 180.0, CADRE[1]
    L, H, LL = 180.0, 52.0, 48.0          # largeur, hauteur, largeur de la case du logo
    fond.add_patch(Rectangle((X0, Y0), L, H, fc="white", ec=NOIR, lw=TRAIT_CADRE, zorder=21))
    fond.add_patch(Rectangle((X0, Y0), LL, H, fill=False, ec=NOIR, lw=TRAIT_FIN, zorder=22))
    if LOGO.exists():
        img = plt.imread(str(LOGO))
        lw_ = 40.0
        hw_ = lw_ * img.shape[0] / img.shape[1]
        fond.imshow(img, extent=(X0 + (LL - lw_) / 2, X0 + (LL + lw_) / 2, Y0 + H - 2.5 - hw_, Y0 + H - 2.5),
                    aspect="auto", zorder=23, interpolation="lanczos")
    else:
        fond.text(X0 + LL / 2, Y0 + 36, "ECAM", fontsize=20, fontweight="bold", color="#25407f", ha="center",
                  va="center", zorder=23)
    for i, t in enumerate((ECOLE[1], PROJET)):
        fond.text(X0 + LL / 2, Y0 + 11.0 - 4.2 * i, t, fontsize=5.0, color=NOIR, ha="center", va="center", zorder=23)
    fond.text(X0 + LL / 2, Y0 + 2.6, "Prototype de recherche, non validé cliniquement", fontsize=4.4, color=GRIS,
              ha="center", va="center", zorder=23, style="italic")
    x = X0 + LL
    W = L - LL
    _case(fond, x, Y0 + 40, W, 12, "Titre", titre, taille=10.0, gras=True)
    _case(fond, x, Y0 + 32, W, 8, "Désignation", designation, taille=7.0)
    _case(fond, x, Y0 + 24, W * 0.56, 8, "Matière", matiere, taille=6.2)
    _case(fond, x + W * 0.56, Y0 + 24, W * 0.44, 8, "Tolérances générales", tolerances, taille=6.2)
    w4 = W / 4
    _case(fond, x, Y0 + 16, w4, 8, "Dessiné par", "CT-CORA3D (auto)", taille=6.0)
    _case(fond, x + w4, Y0 + 16, w4, 8, "Vérifié par", "", taille=6.0)
    _case(fond, x + 2 * w4, Y0 + 16, w4, 8, "Approuvé par (chirurgien)", "", taille=6.0)
    _case(fond, x + 3 * w4, Y0 + 16, w4, 8, "Date", time.strftime("%d/%m/%Y"), taille=6.5)
    largeurs = [(f"N° de plan", numero, 56, 7.4, True), ("Échelle", echelle, 18, 9, True), ("Format", "A3", 14, 8, False),
                ("Rév.", revision, 10, 8, False), ("Feuille", feuille, 18, 7.5, False)]
    xc = x
    for et, val, l_, t_, g_ in largeurs:
        _case(fond, xc, Y0, l_, 16, et, val, taille=t_, gras=g_, centre=True)
        xc += l_
    _case(fond, xc, Y0, x + W - xc, 16, "Projection", "", taille=6)
    _symbole_projection(fond, xc + (x + W - xc) / 2, Y0 + 6.6)
    return Y0 + H


def _couper(texte, largeur_mm, taille):
    """Découpe un texte en lignes d'au plus `largeur_mm` (largeur moyenne d'un caractère DejaVu Sans ≈ 0,56 em)."""
    n = max(4, int(largeur_mm / (taille / PT * 0.56)))
    lignes, cour = [], ""
    for mot in str(texte).split(" "):
        if cour and len(cour) + 1 + len(mot) > n:
            lignes.append(cour)
            cour = mot
        else:
            cour = f"{cour} {mot}".strip()
    lignes.append(cour)
    return lignes


def _tableau(fond, x0, y0, titre, colonnes, lignes, larg_col, taille=6.2, h_ligne=3.5, entete=True):
    """Tableau encadré (comme une table AutoCAD) : bandeau de titre, ligne d'en-tête grisée, lignes séparées ; les
    cellules trop longues passent à la ligne. Renvoie l'ordonnée sous le tableau."""
    L = sum(larg_col)
    xs = np.cumsum([0] + list(larg_col[:-1])) + x0
    y = y0
    kw = dict(color=NOIR, lw=TRAIT_FIN, zorder=22)
    if titre:
        fond.add_patch(Rectangle((x0, y - 5.0), L, 5.0, fc="#e6e6e6", ec=NOIR, lw=TRAIT_FIN, zorder=21))
        fond.text(x0 + 1.5, y - 2.5, titre, fontsize=7.2, fontweight="bold", va="center", zorder=23)
        y -= 5.0
    if entete and any(colonnes):
        fond.add_patch(Rectangle((x0, y - 4.2), L, 4.2, fc="#f3f3f3", ec=NOIR, lw=TRAIT_FIN, zorder=21))
        for j, c in enumerate(colonnes):
            fond.text(xs[j] + 1.2, y - 2.1, c, fontsize=taille - 0.4, fontweight="bold", color=GRIS, va="center",
                      zorder=23)
        y -= 4.2
    haut = y
    for ligne in lignes:
        morceaux = [_couper(val, larg_col[j] - 2.2, taille) for j, val in enumerate(ligne)]
        n = max(len(m_) for m_ in morceaux)
        h = h_ligne * n + 1.0
        for j, m_ in enumerate(morceaux):
            for i, t in enumerate(m_):
                fond.text(xs[j] + 1.2, y - 0.5 - h_ligne * (i + 0.5), t, fontsize=taille, color=NOIR, va="center",
                          zorder=23)
        y -= h
        fond.plot([x0, x0 + L], [y, y], **kw)
    fond.plot([x0, x0, x0 + L, x0 + L], [haut, y, y, haut], **kw)
    for x in xs[1:]:
        fond.plot([x, x], [haut, y], **kw)
    return y


def _hauteur_tableau(lignes, larg_col, taille, h_ligne, titre=True, entete=True):
    h = (5.0 if titre else 0) + (4.2 if entete else 0)
    for ligne in lignes:
        h += h_ligne * max(len(_couper(v, larg_col[j] - 2.2, taille)) for j, v in enumerate(ligne)) + 1.0
    return h


def _nomenclature(fond, lignes, y0):
    """Nomenclature (liste des pièces) posée sur le cartouche : en-tête en bas, pièces numérotées vers le haut."""
    X0 = CADRE[2] - 180.0
    larg = [11, 11, 72, 30, 56]
    xs = np.cumsum([0] + larg[:-1]) + X0
    h = 5.2
    rangs = [("Rep.", "Qté", "Désignation", "Matière", "Observations")] + lignes
    for i, r in enumerate(rangs):
        y = y0 + i * h
        fond.add_patch(Rectangle((X0, y), 180, h, fc="#eeeeee" if i == 0 else "white", ec=NOIR,
                                 lw=TRAIT_FIN if i else TRAIT_FORT, zorder=21))
        for j, v in enumerate(r):
            fond.text(xs[j] + (larg[j] / 2 if j < 2 else 1.3), y + h / 2, str(v), fontsize=6.3 if i else 6.0,
                      ha="center" if j < 2 else "left", va="center", fontweight="bold" if i == 0 else "normal",
                      zorder=23)
    for x in xs[1:]:
        fond.plot([x, x], [y0, y0 + h * len(rangs)], color=NOIR, lw=TRAIT_FIN, zorder=22)
    return y0 + h * len(rangs)


def _titre_vue(fond, x, y, lettre, texte):
    """Titre d'une vue, au-dessus d'elle : lettre en gras, puis une courte explication."""
    t = fond.text(x, y, lettre, fontsize=8.5, fontweight="bold", va="bottom", ha="left")
    if texte:
        fig = fond.figure
        r = fig.canvas.get_renderer()
        bb = t.get_window_extent(renderer=r)
        dx = bb.width / fig.dpi * 25.4 + 1.6
        fond.text(x + dx, y + 0.15, texte, fontsize=6.6, color=GRIS, va="bottom", ha="left")


def _axes_vue(fig, x0, y0, lims, echelle):
    """Axes placés pour qu'un millimètre de l'objet mesure `echelle` mm sur la feuille. lims = (xmin, xmax, ymin, ymax)."""
    xa, xb, ya, yb = lims
    w, h = (xb - xa) * echelle, (yb - ya) * echelle
    ax = fig.add_axes([x0 / A3[0], y0 / A3[1], w / A3[0], h / A3[1]])
    ax.set_xlim(xa, xb)
    ax.set_ylim(ya, yb)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.patch.set_visible(False)
    return ax


def _echelle_txt(e):
    return {5.0: "5:1", 2.0: "2:1", 1.0: "1:1", 0.5: "1:2"}.get(e, f"{_fr(e, 2)}:1")


def _enregistrer(fig, base):
    sortis = []
    for ext, kw in ((".svg", {}), (".pdf", {}), (".png", {"dpi": 170})):
        chemin = Path(str(base) + ext)
        fig.savefig(chemin, **kw)
        sortis.append(chemin.name)
    plt.close(fig)
    return sortis


def _controle_echelle(fond, ech, x0=CADRE[0] + 5, y0=CADRE[1] + 3.2):
    """Cote de contrôle : 50 mm de l'objet, pour vérifier l'échelle à l'impression (imprimer à 100 %)."""
    L = 50.0 * ech
    for i in range(5):                                       # barre alternée noir / blanc, tous les 10 mm d'objet
        fond.add_patch(Rectangle((x0 + i * L / 5, y0 - 0.6), L / 5, 1.2, fc=NOIR if i % 2 == 0 else "white",
                                 ec=NOIR, lw=TRAIT_FIN))
    fond.text(x0 + L + 2.5, y0, f"cote de contrôle : 50 mm de l'objet = {_fr(L, 0)} mm imprimés à l'échelle "
              f"{_echelle_txt(ech)} (imprimer à 100 %)", fontsize=6.0, va="center", color=NOIR)


def _numero_plan(pr, suffixe):
    os_ = {"tibia": "TIB", "femur": "FEM", "radius": "RAD"}.get(pr.get("os", ""), "OS")
    coin = {"fermeture": "FER", "ouverture": "OUV"}.get((pr.get("strategie") or {}).get("type_coin", ""), "COIN")
    return f"CTC3D-{os_}-{coin}-{time.strftime('%y%m%d')}-{suffixe}"


# --------------------------------------------------------------------------- plan générique (symboles)
SYMBOLES = [   # (symbole, clé, description courte, unité)
    ("j", "jeu_mm", "jeu entre l'os et la coque", "mm"),
    ("e", "epaisseur_coque_mm", "épaisseur de la coque", "mm"),
    ("α", "secteur_deg", "demi-ouverture de la coque autour de la face d'appui", "°"),
    ("δ", "depouille_deg", "dépouille (pose et retrait sans contre-dépouille)", "°"),
    ("m", "marge_mm", "coque au-delà des broches extrêmes", "mm"),
    ("r", "conge_mm", "rayon des congés", "mm"),
    ("g", "guidage_mm", "hauteur de guidage au-dessus de la coque", "mm"),
    ("p", "paroi_mm", "paroi des tours et des manchons", "mm"),
    ("s", "lame_mm", "épaisseur de la lame de scie", "mm"),
    ("js", "jeu_fente_mm", "jeu de la fente", "mm"),
    ("Øb", "broche_mm", "diamètre des broches", "mm"),
    ("jb", "jeu_broche_mm", "jeu du manchon", "mm"),
    ("hp", "pont_mm", "hauteur des ponts sécables", "mm"),
    ("c", "chanfrein_mm", "chanfreins d'entrée (fentes, manchons)", "mm"),
    ("eb", "ecart_broches_mm", "écart entre 2 broches d'un fragment (planif.)", "mm"),
    ("kd", "facteur_distance_broches", "distance broche–coupe / largeur de l'os (planif.)", "×"),
    ("jv", "jeu_voisin_mm", "distance minimale aux os voisins", "mm"),
    ("mc", "marge_cartilage_mm", "écart supplémentaire au cartilage", "mm"),
    ("er", "reduction_ecart_mm", "réduction : barre → os", "mm"),
    ("lr", "reduction_manchon_mm", "réduction : longueur des manchons", "mm"),
    ("tb", "reduction_barre_mm", "réduction : épaisseur de la barre", "mm"),
]


def _axes_schema(fig, x0, y0, l, h, lims):
    ax = fig.add_axes([x0 / A3[0], y0 / A3[1], l / A3[0], h / A3[1]])
    ax.set_xlim(lims[0], lims[1])
    ax.set_ylim(lims[2], lims[3])
    ax.set_aspect("equal")
    ax.axis("off")
    ax.patch.set_visible(False)
    return ax


def _arc(c, r, a0, a1, n=60):
    t = np.radians(np.linspace(a0, a1, n))
    return np.c_[c[0] + r * np.cos(t), c[1] + r * np.sin(t)]


def plan_generique(base, valeurs_cas, defauts, dims=None, titre_cas="", pr=None):
    """Schéma paramétrique du guide (sans échelle), tableau des paramètres et dimensions qui découlent de l'os."""
    fig, fond = _feuille()
    # --- A. coupe de principe dans le plan d'une fente : os, coque (j, e, ±α), tour fendue (g, p, s + js)
    ax = _axes_schema(fig, 27, 92, 96, 165, (-30, 30, -40, 63))
    _titre_vue(fond, 27, 262, "COUPE A-A", "de principe, dans le plan d'une fente")
    R, j, e, alpha = 13.0, 1.8, 4.0, 62.0
    Ri, Ro = R + j, R + j + e
    tw, sw, y1t = 7.2, 1.4, R + j + e + 15.0
    # os (pièce voisine) : hachures grises dans l'autre sens ; canal médullaire vide
    _hachures(ax, [_arc((0, 0), R, 0, 360), _arc((0, 0), R * 0.42, 0, 360)], angle=-45, pas_mm=2.2, couleur=GRIS_OS,
              contour=GRIS_OS, zorder=2)
    # coque + tour, d'un seul tenant, fendues par la fente (deux moitiés de part et d'autre du trajet de la lame)
    yt = np.sqrt(Ro ** 2 - (tw / 2) ** 2)
    ar = np.degrees(np.arctan2(yt, tw / 2))
    profil = np.vstack([_arc((0, 0), Ro, 90 - alpha, ar), [(tw / 2, y1t), (-tw / 2, y1t)],
                        _arc((0, 0), Ro, 180 - ar, 90 + alpha), _arc((0, 0), Ri, 90 + alpha, 90 - alpha)])
    for s_ in (1, -1):
        _hachures(ax, [_demi_plan(profil, np.array([s_, 0.0]), sw / 2)], angle=45, pas_mm=1.2, zorder=4)
    _ligne(ax, (-sw / 2, -R - 3), (-sw / 2, y1t + 2), CACHE, zorder=6)
    _ligne(ax, (sw / 2, -R - 3), (sw / 2, y1t + 2), CACHE, zorder=6)
    _note(ax, (sw / 2, -R + 3.5), "trajet de la lame", (9, -6), taille=6.2)
    _ligne(ax, (0, -R - 5), (0, y1t + 9), AXE, zorder=6)
    pj = np.array([np.cos(np.radians(145)), np.sin(np.radians(145))])
    _note(ax, (R + j / 2) * pj, "j", (-7, 5), taille=8)
    ang_e = np.radians(30)
    pe = np.array([np.cos(ang_e), np.sin(ang_e)])
    _cote(ax, Ri * pe, Ro * pe, 6 * np.array([np.sin(ang_e), -np.cos(ang_e)]), "e")
    _cote(ax, (tw / 2, Ro), (tw / 2, y1t), (8, 0), "g")
    _cote(ax, (-tw / 2, y1t), (-sw / 2, y1t), (0, 5), "p")
    _cote(ax, (-sw / 2, y1t), (sw / 2, y1t), (0, 11), "s + js")
    ra = Ro + 6
    ax.add_patch(Arc((0, 0), 2 * ra, 2 * ra, theta1=90, theta2=90 + alpha, color=NOIR, lw=TRAIT_FIN))
    pa = ra * np.array([np.cos(np.radians(90 + alpha)), np.sin(np.radians(90 + alpha))])
    _fleche(ax, pa, (np.sin(np.radians(90 + alpha)), -np.cos(np.radians(90 + alpha))), 1 / _mm(ax))
    ax.text(-ra * np.sin(np.radians(alpha / 2)) - 2.0, ra * np.cos(np.radians(alpha / 2)) + 1.0, "α", fontsize=9)
    ax.text(0, y1t + 13.5, "face d'appui (abord)", fontsize=6.2, color=GRIS, ha="center")
    y_ch = -R + 2.0
    _ligne(ax, (-sw / 2 - 3, y_ch), (sw / 2 + 3, y_ch), "-", TRAIT_FORT, zorder=7)
    ax.text(-sw / 2 - 3.5, y_ch, "charnière", fontsize=6.0, ha="right", va="center")
    _cote(ax, (-tw / 2, y1t), (-tw / 2, y_ch), (-40, 0), "= profondeur de lame")
    _cote(ax, (-R, -R), (R, -R), (0, -10), "= largeur de l'os", taille=6.6)
    _cote(ax, (-R - 1, -R), (R + 1, -R), (0, -21), "longueur de fente = largeur de l'os + 2", taille=6.6)
    # --- B. vue de la face d'appui : deux moitiés, fentes, ponts, manchons, broches
    ax = _axes_schema(fig, 132, 26, 112, 232, (-28, 28, -60, 56))
    _titre_vue(fond, 132, 262, "VUE B", "depuis la face d'appui (coin de fermeture)")
    th, Wg = np.radians(14), 13.0
    yb = lambda x: -1.2 - np.tan(th) * (x + Wg)
    kw = dict(fc="white", ec=NOIR, lw=TRAIT_FORT, zorder=3)
    ax.add_patch(Polygon([(-Wg, 44), (Wg, 44), (Wg, 1.6), (-Wg, 1.6)], **kw))
    ax.add_patch(Polygon([(-Wg, 0.8), (Wg, 0.8), (Wg, -50), (-Wg, -50)], **kw))
    ax.add_patch(Polygon([(-Wg + 1.2, yb(-Wg + 1.2) + 0.4), (Wg - 1.2, yb(Wg - 1.2) + 0.4),
                          (Wg - 1.2, yb(Wg - 1.2) - 0.4), (-Wg + 1.2, yb(-Wg + 1.2) - 0.4)],
                         fc="white", ec=NOIR, lw=TRAIT_FORT * 0.8, zorder=4))     # fente 2 : fente fermée (distale)
    for x in (-Wg - 1.6, Wg - 0.4):                      # ponts sécables : aux deux bouts de la fente 1 (séparation)
        ax.add_patch(Rectangle((x, -0.2), 2.0, 2.0, fc="white", ec=NOIR, lw=TRAIT_FORT * 0.8, zorder=5))
    _note(ax, (Wg + 1.2, 1.4), "pont sécable\np × hp (×2)", (5, 9), taille=6.4)
    _ligne(ax, (-Wg - 4, 1.2), (Wg + 4, 1.2), PLAN, zorder=6)
    _ligne(ax, (-Wg - 4, yb(-Wg - 4)), (Wg + 4, yb(Wg + 4)), PLAN, zorder=6)
    ax.text(-Wg - 4.6, 3.5, "PC1\n(séparation)", fontsize=6.0, ha="right", va="center")
    ax.text(-Wg - 4.6, yb(-Wg - 4) - 4.5, "PC2\n(fente fermée)", fontsize=6.0, ha="right", va="center")
    ax.add_patch(Arc((-Wg, 1.2), 26, 26, theta1=-np.degrees(th), theta2=0, color=NOIR, lw=TRAIT_FIN))
    ax.text(-Wg + 14.0, -1.9, "θ", fontsize=8.5)
    rs, rh = 2.9, 0.9
    for (x, y) in ((0, 14), (0, 25), (0, -16), (0, -27)):
        ax.add_patch(Circle((x, y), rs, fc="white", ec=NOIR, lw=TRAIT_FORT, zorder=4))
        ax.add_patch(Circle((x, y), rh, fc="white", ec=NOIR, lw=TRAIT_FORT, zorder=5))
        _ligne(ax, (x - rs - 1.5, y), (x + rs + 1.5, y), AXE, zorder=6)
    _ligne(ax, (0, -53), (0, 47), AXE, zorder=6)
    _cote(ax, (-rs, 1.2), (-rs, 14), (-14, 0), "d = kd × larg.", fond_blanc=True)
    _cote(ax, (-rs, 14), (-rs, 25), (-14, 0), "eb", fond_blanc=True)
    _cote(ax, (-rs, 25), (-rs, 44), (-14, 0), "m", fond_blanc=True)
    _cote(ax, (-rs, -27), (-rs, -50), (-14, 0), "m", fond_blanc=True)
    _note(ax, (rs * 0.7, 25 + rs * 0.7), "manchon Ø(Øb + jb + 2p)\ntrou Ø(Øb + jb)", (6, 9), taille=6.4)
    ax.text(-Wg + 1.2, 40, "moitié proximale (1)", fontsize=6.4, zorder=6)
    ax.text(-Wg + 1.2, -47.5, "moitié distale (2)", fontsize=6.4, zorder=6)
    _cote(ax, (-Wg, -50), (Wg, -50), (0, -8), "= os + coque (± α)", taille=6.6)
    # --- C. manchon en coupe (la broche, pièce pleine, n'est pas hachurée : ISO 128-50)
    ax = _axes_schema(fig, 252, 150, 46, 98, (-12, 12, -16, 35))
    _titre_vue(fond, 252, 262, "COUPE C-C", "manchon")
    _hachures(ax, [np.array([(-12, -16), (12, -16), (12, -6), (-12, -6)])], angle=-45, pas_mm=2.2, couleur=GRIS_OS,
              contour=GRIS_OS, zorder=2)
    profil = np.array([(-6, -5.6), (6, -5.6), (6, -1.6), (3.4, -1.6), (3.4, 20.4), (-3.4, 20.4), (-3.4, -1.6),
                       (-6, -1.6)])
    for s_ in (1, -1):
        _hachures(ax, [_demi_plan(profil, np.array([s_, 0.0]), 0.9)], angle=45, pas_mm=1.2, zorder=4)
    ax.add_patch(Rectangle((-0.8, -16), 1.6, 46, fc="white", ec=NOIR, lw=TRAIT_FORT, zorder=6))
    _ligne(ax, (0, -18), (0, 33), AXE, zorder=7)
    _cote(ax, (-0.8, 28), (0.8, 28), (0, 3), "Øb", fond_blanc=True)
    _cote(ax, (-3.4, -5.6), (-3.4, 20.4), (-7, 0), "e + g")
    _cote(ax, (0.9, 14), (3.4, 14), (0, 0), "p", fond_blanc=True)
    ax.text(6.5, -12, "os", fontsize=6.4, color=GRIS)
    ax.text(1.4, 25, "broche", fontsize=6.0, color=GRIS)
    # --- tableaux à droite : paramètres, dimensions qui découlent de l'os, notes
    lignes = []
    for sym, cle, desc, unite in SYMBOLES:
        d_ = defauts.get(cle, PLANIF_DEFAUT.get(cle))
        c_ = valeurs_cas.get(cle, d_)
        if d_ is None:
            continue
        dec = 2 if abs(float(d_)) < 1 or cle.startswith("jeu") or cle in ("lame_mm",) else 1
        modif = c_ is not None and abs(float(c_) - float(d_)) > 1e-9
        txt = lambda x: _fr(float(x), dec)
        lignes.append((sym, desc, txt(d_), txt(c_) + (" ◄" if modif else ""), unite))
    x_t = 303.0
    y = _tableau(fond, x_t, 280, "Paramètres du guide", ["sym.", "description", "défaut", "ce cas", ""], lignes,
                 [10, 59, 13, 15, 8], taille=5.7, h_ligne=2.95)
    if dims:
        derives = [
            ("fente(s) L × l", " ; ".join(f"{_fr(x['longueur_mm'])} × {_fr(x['largeur_mm'], 2)}" for x in dims.get("fentes", []))),
            ("haut. de tour", " ; ".join(_fr(x["hauteur_tour_mm"]) for x in dims.get("fentes", []))),
            ("prof. de lame", " ; ".join(f"{_fr(x['profondeur_lame_mm'])} ({x.get('arret_lame', 'charnière')})"
                                         for x in dims.get("fentes", []))),
            ("manchon Ø ext. / trou", f"{_fr(dims['manchon_diametre_exterieur_mm'], 2)} / {_fr(dims['trou_broche_mm'], 2)}"),
            ("coque (longueur)", _fr(dims["coque"]["longueur_mm"])),
            ("angle entre fentes", f"{_fr(dims['angle_entre_fentes_deg'], 1)}°" if dims.get("angle_entre_fentes_deg") else "1 fente"),
            ("broches → coupe", " ; ".join(f"{b['nom']} {_fr(b['distance_coupe_mm'])}" for b in dims.get("broches", []))),
            ("encombrement", "{} × {} × {}".format(*(_fr(dims["guide_coupe"][k]) for k in ("longueur_axe_os_mm", "largeur_mm", "hauteur_mm")))),
        ]
        y = _tableau(fond, x_t, y - 4, f"Dimensions qui découlent de l'os (mm)", ["dimension", "ce cas"],
                     [d for d in derives if d], [30, 75], taille=5.7, h_ligne=2.95)
    notes = [("1.", "Schéma de principe, sans échelle. Les cotes en symboles sont des PARAMÈTRES modifiables (onglet "
                    "CORA, étape 12) ; les cotes « = … » découlent de l'os segmenté et sont recalculées pour chaque "
                    "scanner."),
             ("2.", "Longueur de fente = largeur de l'os + 2 ; haut de tour = os + j + e + g (point le plus haut de "
                    "l'os dans la fente) ; profondeur de lame = du haut de la tour à la charnière (ou à la corticale "
                    "opposée)."),
             ("3.", "Épaisseur de tour = s + js + 2p ; manchon Ø = Øb + jb + 2p ; d = kd × largeur de l'os ; ponts = "
                    "p × hp."),
             ("4.", "Coque : de (broche la plus proximale − m) à (la plus distale + m), à au moins 10 mm des "
                    "extrémités articulaires."),
             ("5.", "Guide de réduction : manchons parallèles de longueur lr, barre d'épaisseur tb à er de l'os."),
             ("6.", "◄ : valeur changée pour ce cas. Os hachuré en gris (pièce voisine) ; PC = plan de coupe de "
                    "l'os.")]
    _tableau(fond, x_t, y - 4, "Notes", ["", ""], notes, [6, 99], taille=5.7, h_ligne=2.95, entete=False)
    os_ = (pr or {}).get("os", "")
    _cartouche(fond, "GUIDE DE COUPE — MODÈLE PARAMÉTRIQUE",
               f"Schéma de principe et table des paramètres" + (f" · cas : {titre_cas}" if titre_cas else ""),
               _numero_plan(pr or {}, "00") if pr else "CTC3D-GEN-00", "—", "PA12 (frittage laser) ou résine stérilisable",
               "± 0,1 (impression 3D)")
    return _enregistrer(fig, base)


# --------------------------------------------------------------------------- plan coté du cas
def plan_cote(base, pr, info, v_os, f_os, moities, ponts, red, geo, broches_c, vc, fc, depuis_manifold):
    """Projections orthogonales (projection européenne) du guide de coupe, coupe E-E, guide de réduction, vue
    isométrique, cotes, nomenclature, tableau des cotes, mode opératoire et cartouche."""
    import trimesh

    u = _unitaire(geo["u"])
    face = _unitaire(geo["face"])
    face = _unitaire(face - (face @ u) * u)
    cote_ = _unitaire(np.cross(u, face))
    K = np.asarray(geo["K"], float)
    d_ = info.get("dimensions") or {}
    st = pr.get("strategie", {})
    kind = st.get("type_coin", "")
    theta = float(pr["deformite"]["theta_deg"])
    allege = lambda m_: m_.simplify(0.02)      # 0,02 mm, invisible à l'échelle du plan : 5 fois moins de triangles
    pieces = []                                # (nom, manifold, sommets, triangles)
    for nom, m_ in (("proximal", moities[0]), ("distal", moities[1]), ("ponts", ponts)):
        if m_ is not None and not m_.is_empty():
            m2 = allege(m_)
            pieces.append((nom, m2, *depuis_manifold(m2)))
    tous = np.vstack([p[2] for p in pieces])
    # vues, repères directs (x × y = z, z vers l'observateur) : projection européenne
    vues = {
        "A": {"o": K, "x": -cote_, "y": -u, "z": face},       # vue de face, depuis la face d'appui
        "B": {"o": K, "x": face, "y": -u, "z": cote_},        # vue de gauche (observateur à gauche de A), à droite de A
        "C": {"o": K, "x": -cote_, "y": -face, "z": -u},      # vue de dessus (depuis proximal), sous A
    }
    # coupe E-E : plan parallèle à la vue B, passant par les manchons (position latérale moyenne des broches)
    hauts = np.array([x["a"] + x["t_haut"] * (-_unitaire(x["d"])) for x in geo["broches"]])
    s_E = float(np.mean((hauts - K) @ cote_)) if len(hauts) else 0.0
    oE = K + s_E * cote_
    vues["E"] = {"o": oE, "x": face, "y": -u, "z": cote_}
    # isométrique : depuis l'avant, la droite et le haut de la vue A
    zi = _unitaire(vues["A"]["x"] + vues["A"]["y"] + vues["A"]["z"])
    yi = _unitaire(vues["A"]["y"] - (vues["A"]["y"] @ zi) * zi)
    vues["ISO"] = {"o": K, "x": np.cross(yi, zi), "y": yi, "z": zi}
    ext = {k_: (lambda q: (q[:, :2].min(0), q[:, :2].max(0)))(_projeter(tous, vues[k_])) for k_ in vues}
    # guide de réduction, après la correction, vu le long des broches (parallèles)
    vueD, rv, rf = None, None, None
    if red is not None and broches_c:
        rv, rf = depuis_manifold(red)
        o = _unitaire(-np.mean([_unitaire(x["d"]) for x in broches_c], 0))
        ud = _unitaire(u - (u @ o) * o)
        vueD = {"o": np.mean([x["a"] for x in broches_c], 0), "x": _unitaire(np.cross(-ud, o)), "y": -ud, "z": o}
        q = _projeter(rv, vueD)
        ext["D"] = (q[:, :2].min(0), q[:, :2].max(0))
    taille = {k_: ext[k_][1] - ext[k_][0] for k_ in ext}
    # marges autour de chaque vue (mm de papier) : place des cotes, des repères et des indications
    M = {"A": (16, 29, 17, 6), "B": (14, 15, 17, 6), "E": (13, 36, 17, 6), "C": (16, 29, 16, 5),
         "D": (18, 16, 16, 14)}                               # (gauche, droite, bas, haut)
    X_MIN, X_MAX, Y_HAUT = CADRE[0] + 4, 297.0, CADRE[3] - 9
    X_CART, Y_NOMEN = CADRE[2] - 180 - 4, 104.0               # sous Y_NOMEN, rien à droite de X_CART
    for ech in (5.0, 2.0, 1.0, 0.5):
        L_ = {k_: taille[k_][0] * ech + M[k_][0] + M[k_][1] for k_ in ("A", "B", "E", "C", "D") if k_ in taille}
        H_ = {k_: taille[k_][1] * ech + M[k_][2] + M[k_][3] for k_ in L_}
        L_["C"] = L_["A"]                                     # C sous A, mêmes abscisses
        x_ = {"A": X_MIN}
        x_["B"] = x_["A"] + L_["A"]
        x_["E"] = x_["B"] + L_["B"]
        h1 = max(H_["A"], H_["B"], H_["E"])
        y1 = Y_HAUT - h1                                      # bas de la rangée 1
        y2 = y1 - 9                                           # haut de la rangée 2
        ok = x_["E"] + L_["E"] <= X_MAX and y2 - H_["C"] >= CADRE[1] + 6
        x_["C"] = x_["A"]
        if "D" in L_:
            x_["D"] = x_["B"]
            basD = y2 - H_["D"]
            ok = ok and basD >= (CADRE[1] + 6 if x_["D"] + L_["D"] <= X_CART else Y_NOMEN)
        if ok:
            break
    k_ech = ech
    lims = {}
    for k_ in ("A", "B", "E", "C", "D"):
        if k_ not in taille:
            continue
        lo, hi = ext[k_]
        g, d, b, h = M[k_]
        lims[k_] = [lo[0] - g / ech, hi[0] + d / ech, lo[1] - b / ech, hi[1] + h / ech]
    lims["C"][0], lims["C"][1] = lims["A"][0], lims["A"][1]   # C alignée sur A (même axe horizontal)
    for k_ in ("B", "E"):                                     # A, B et E alignées (même axe vertical)
        lims[k_][2], lims[k_][3] = lims["A"][2], lims["A"][3]
    fig, fond = _feuille()
    pas = 25.4 / (180.0 * ech)          # aplats à ≈ 180 points par pouce sur la feuille, quelle que soit l'échelle
    axes = {}
    for k_ in ("A", "B", "E"):
        axes[k_] = _axes_vue(fig, x_[k_], y1, lims[k_], ech)
    axes["C"] = _axes_vue(fig, x_["C"], y2 - (lims["C"][3] - lims["C"][2]) * ech, lims["C"], ech)
    if "D" in lims:
        axes["D"] = _axes_vue(fig, x_["D"], y2 - (lims["D"][3] - lims["D"][2]) * ech, lims["D"], ech)
    # os (pièce voisine) autour du guide : interrompu un peu au-delà du guide (trait ondulé)
    s_u = (tous - K) @ u
    u0, u1 = float(s_u.min()), float(s_u.max())
    cen = v_os[f_os].mean(1)
    cu = (cen - K) @ u
    eu = 7.0 / ech + 3.0
    f_os_l = f_os[(cu > u0 - eu) & (cu < u1 + eu)]
    fort = [(p[2], p[3], BLANC, "fort") for p in pieces]
    rendus = {}
    for k_ in ("A", "B", "C"):
        lo, hi = ext[k_]
        if k_ == "C":
            rendus[k_] = _dessiner_vue(axes[k_], fort, vues[k_], lims[k_], pas)
            vC = vues["C"]
            oC = K + (u0 + 1.0) * u
            for b_ in _section(v_os, f_os, np.vstack([vC["x"], vC["y"], vC["z"]]), oC):
                b_ = np.vstack([b_, b_[:1]]) + (_projeter(np.array([oC]), vC)[0, :2])
                axes[k_].plot(b_[:, 0], b_[:, 1], color=GRIS_OS, lw=TRAIT_FIN, ls=PLAN, zorder=6)
            continue
        dec = (-1e9, 1e9, lo[1] - 6.0 / ech, hi[1] + 6.0 / ech)
        rendus[k_] = _dessiner_vue(axes[k_], [(v_os, f_os_l, OS_FOND, "fin")] + fort, vues[k_], lims[k_], pas,
                                   decoupe=dec)
        for y_ in dec[2:]:
            _os_interrompu(axes[k_], *rendus[k_], y_)
    # coupe E-E : on garde ce qui est derrière le plan (côté −cote_), coupé exactement
    nE = -cote_
    off = float(nE @ oE)
    coupes, morceaux_E = [], []
    RE = np.vstack([vues["E"]["x"], vues["E"]["y"], vues["E"]["z"]])
    ME = np.column_stack([RE, -RE @ oE])
    for nom, m2, _, _ in pieces:
        t_ = m2.trim_by_plane(tuple(nE), off)
        if not t_.is_empty():
            morceaux_E.append((*depuis_manifold(t_), BLANC, "fort"))
        coupes += [np.asarray(p_, float) for p_ in m2.transform(ME).slice(0.0).to_polygons()]
    os_m = trimesh.Trimesh(v_os, f_os_l, process=False)
    try:
        os_E = trimesh.intersections.slice_mesh_plane(os_m, plane_normal=nE, plane_origin=oE)
        os_E = [(np.asarray(os_E.vertices), np.asarray(os_E.faces), OS_FOND, "fin")]
    except Exception:
        os_E = []
    loE, hiE = ext["E"]
    decE = (-1e9, 1e9, loE[1] - 6.0 / ech, hiE[1] + 6.0 / ech)
    rendus["E"] = _dessiner_vue(axes["E"], os_E + morceaux_E, vues["E"], lims["E"], pas, decoupe=decE)
    for y_ in decE[2:]:
        _os_interrompu(axes["E"], *rendus["E"], y_)
    boucles = _section(v_os, f_os, RE, oE)       # section de l'os (os entier : contours fermés)
    bandes = []
    for b_ in boucles:
        b_ = _demi_plan(b_, np.array([0.0, 1.0]), decE[2])
        b_ = None if b_ is None else _demi_plan(b_, np.array([0.0, -1.0]), -decE[3])
        if b_ is not None:
            bandes.append(b_)
    _hachures(axes["E"], bandes, angle=-45, pas_mm=2.2, couleur=GRIS_OS, contour=GRIS_OS, zorder=4)
    _hachures(axes["E"], coupes, angle=45, pas_mm=1.2, zorder=5)
    # guide de réduction (pièce 4)
    if "D" in axes:
        cen_c = vc[fc].mean(1)
        cd = (cen_c - vueD["o"]) @ vueD["y"]
        loD, hiD = ext["D"]
        fc_l = fc[(cd > loD[1] - 7.0 / ech - 3) & (cd < hiD[1] + 7.0 / ech + 3)]
        decD = (-1e9, 1e9, loD[1] - 6.0 / ech, hiD[1] + 6.0 / ech)
        rendus["D"] = _dessiner_vue(axes["D"], [(vc, fc_l, OS_FOND, "fin"), (rv, rf, BLANC, "fort")], vueD,
                                    lims["D"], pas, decoupe=decD)
        for y_ in decD[2:]:
            _os_interrompu(axes["D"], *rendus["D"], y_)
    # titres des vues
    titres = {"A": ("A", "vue de face, depuis la face d'appui"), "B": ("B", "vue de gauche"),
              "E": ("E-E", "coupe par les manchons"), "C": ("C", "vue de dessus, depuis proximal"),
              "D": ("D", "pièce 4 après correction, le long des broches")}
    for k_, ax_ in axes.items():
        p0 = ax_.get_position()
        _titre_vue(fond, p0.x0 * A3[0] + 2, p0.y1 * A3[1] + 1.0, *titres[k_])
    # axes des broches (traits mixtes fins)
    for x in geo["broches"]:
        o = -_unitaire(x["d"])
        a0, a1 = x["a"] + (x["t_sortie"] - 4) * o, x["a"] + (x["t_haut"] + 4) * o
        for k_ in ("A", "B", "C", "E"):
            p0, p1 = _projeter(np.array([a0, a1]), vues[k_])[:, :2]
            if np.linalg.norm(p1 - p0) < 1.0:                # broche vue en bout : croix d'axes
                c = (p0 + p1) / 2
                r = 4.5 / ech
                _ligne(axes[k_], c - (r, 0), c + (r, 0), dans_vue=True)
                _ligne(axes[k_], c - (0, r), c + (0, r), dans_vue=True)
            else:
                _ligne(axes[k_], p0, p1, dans_vue=True)
    # plans de coupe de l'os (traits mixtes à deux points) dans A, B et E
    kA = 1.0 / ech
    for i, (p, n) in enumerate(geo["plans"]):
        n = _unitaire(n)
        for k_, cote_txt in (("A", "droite"), ("B", "gauche"), ("E", "gauche")):
            vue = vues[k_]
            dd = np.cross(n, vue["z"])
            if np.linalg.norm(dd) < 1e-6:
                continue
            d2 = _unitaire(np.array([dd @ vue["x"], dd @ vue["y"]]))
            c0 = _projeter(np.array([p]), vue)[0, :2]
            lo, hi = ext[k_]
            seg = _dans_boite(c0, d2, lo - 3 * kA, hi + 3 * kA)
            if seg is None:
                continue
            a_, b_ = sorted(seg, key=lambda z: z[0])
            _ligne(axes[k_], a_, b_, PLAN, zorder=7)
            bout = b_ if cote_txt == "droite" else a_
            axes[k_].text(bout[0] + (1.0 if cote_txt == "droite" else -1.0) * kA, bout[1] + (1.2 - 2.6 * i) * kA,
                          f"PC{i + 1}", fontsize=7, ha="left" if cote_txt == "droite" else "right", va="center",
                          zorder=11)
    # trait de la coupe E-E sur la vue A (l'observateur de la coupe regarde vers −cote_, soit +x de la vue A)
    loA, hiA = ext["A"]
    xs_ = float(_projeter(np.array([oE]), vues["A"])[0, 0])
    _trait_coupe(axes["A"], (xs_, loA[1] - 3.5 * kA), (xs_, hiA[1] + 3.5 * kA), (1.0, 0.0), "E")
    # cotes hors tout
    _cote(axes["A"], (loA[0], loA[1]), (loA[0], hiA[1]), (-9, 0), _fr(hiA[1] - loA[1]))
    _cote(axes["A"], (loA[0], loA[1]), (hiA[0], loA[1]), (0, -11), _fr(hiA[0] - loA[0]))
    loB, hiB = ext["B"]
    _cote(axes["B"], (hiB[0], loB[1]), (hiB[0], hiB[1]), (9, 0), _fr(hiB[1] - loB[1]))
    _cote(axes["B"], (loB[0], loB[1]), (hiB[0], loB[1]), (0, -11), _fr(hiB[0] - loB[0]))
    loC, hiC = ext["C"]
    _cote(axes["C"], (loC[0], loC[1]), (hiC[0], loC[1]), (0, -9), _fr(hiC[0] - loC[0]))
    _cote(axes["C"], (hiC[0], loC[1]), (hiC[0], hiC[1]), (9, 0), _fr(hiC[1] - loC[1]))
    # coupe E-E : profondeur de lame de chaque fente (du haut de la tour à l'arrêt de la lame), trous et fentes
    axE = axes["E"]
    fentes = d_.get("fentes", [])
    for i, t_ in enumerate(geo.get("tours", [])):
        hh = _unitaire(t_["hh"])
        haut_ = _projeter(np.array([t_["p"] + t_["h_top"] * hh]), vues["E"])[0, :2]
        arret = _projeter(np.array([t_["p"] + t_["h_stop"] * hh]), vues["E"])[0, :2]
        dl = _unitaire(arret - haut_)
        nrm = np.array([-dl[1], dl[0]])
        if (nrm[1] < 0) == (i == 0):
            nrm = -nrm                                        # fente 1 : cote du côté proximal ; fente 2 : distal
        val = fentes[i]["profondeur_lame_mm"] if i < len(fentes) else np.linalg.norm(arret - haut_)
        _cote(axE, haut_, arret, nrm * (6.0 + 5.0 * i), f"lame {_fr(val)}", taille=6.8, fond_blanc=True)
    loE, hiE = ext["E"]
    if geo["broches"]:
        x = geo["broches"][0]
        o = -_unitaire(x["d"])
        ph = _projeter(np.array([x["a"] + (x["t_haut"] - 1.5) * o]), vues["E"])[0, :2]
        n_b = len(geo["broches"])
        _note(axE, ph, f"{n_b}× Ø{_fr(d_.get('trou_broche_mm', 0), 2)} traversant\nmanchon Ø"
                       f"{_fr(d_.get('manchon_diametre_exterieur_mm', 0), 2)}",
              ((hiE[0] - ph[0]) * ech + 7, 7), taille=6.6)
    if geo.get("tours"):
        t_ = geo["tours"][0]
        hh = _unitaire(t_["hh"])
        pf = _projeter(np.array([t_["p"] + (t_["h_top"] - 1.0) * hh]), vues["E"])[0, :2]
        lf = fentes[0] if fentes else {}
        _note(axE, pf, f"fente {_fr(lf.get('largeur_mm', 0), 2)} × {_fr(lf.get('longueur_mm', 0))}\n"
                       f"(lame {_fr(d_.get('parametres', {}).get('lame_mm', 0.6), 2)})",
              ((hiE[0] - pf[0]) * ech + 7, -9), taille=6.6, point=False)
    # repères des pièces sur la vue A
    axA = axes["A"]
    profA, infoA = rendus["A"]
    cibles = []
    for num, nom in ((1, "proximal"), (2, "distal"), (3, "ponts")):
        for p_ in pieces:
            if p_[0] == nom:
                cibles.append((num, _point_visible(p_[2], vues["A"], profA, infoA)))
    cibles.sort(key=lambda z: -z[1][1])
    yb_ = None
    for num, p_ in cibles:
        y_ = p_[1] if yb_ is None else min(p_[1], yb_ - 9.0 * kA)
        _ballon(axA, p_, (hiA[0] + 21 * kA, y_), num)
        yb_ = y_
    # guide de réduction : cotes, entraxes des broches, repères 4 et 5
    if "D" in axes:
        axD = axes["D"]
        loD, hiD = ext["D"]
        _cote(axD, (loD[0], loD[1]), (hiD[0], loD[1]), (0, -9), _fr(hiD[0] - loD[0]))
        _cote(axD, (hiD[0], loD[1]), (hiD[0], hiD[1]), (9, 0), _fr(hiD[1] - loD[1]))
        cb = sorted((_projeter(np.array([x["a"]]), vueD)[0, :2] for x in broches_c), key=lambda z: z[1])
        for a_, b_ in zip(cb, cb[1:]):
            if b_[1] - a_[1] > 0.5:
                _cote(axD, (loD[0], a_[1]), (loD[0], b_[1]), (-9, 0), _fr(b_[1] - a_[1]))
        for c_ in cb:
            _ligne(axD, (loD[0] - 1 * kA, c_[1]), (c_[0] + 4.5 * kA, c_[1]))
            _ligne(axD, (c_[0], c_[1] - 4.5 * kA), (c_[0], c_[1] + 4.5 * kA))
        profD, infoD = rendus["D"]
        pD = _point_visible(rv, vueD, profD, infoD)
        _ballon(axD, pD, (hiD[0] + 12 * kA, pD[1] + 6 * kA), 4)
        _ballon(axD, cb[-1], (cb[-1][0] + 14 * kA, hiD[1] + 8 * kA), 5)
        _note(axD, cb[-1] + np.array([-0.9, 0.9]) * d_.get("trou_broche_mm", 1.8) / 2,
              f"{len(cb)}× Ø{_fr(d_.get('trou_broche_mm', 0), 2)} traversant", (-8, 9), taille=6.6, point=False)
    # vue isométrique (sans échelle), dans la plus grande place libre
    places = []
    droite2 = max(axes[k_].get_position().x1 * A3[0] for k_ in ("C", "D") if k_ in axes)
    places.append((droite2 + 8, CADRE[1] + 8, X_CART - 2, y2 - 8))
    places.append((droite2 + 8, Y_NOMEN + 4, X_MAX, y2 - 8))
    loI, hiI = ext["ISO"]
    tI = hiI - loI
    meilleure = None
    for (xa_, ya_, xb_, yb2) in places:
        if xb_ - xa_ < 30 or yb2 - ya_ < 30:
            continue
        s = min((xb_ - xa_ - 6) / tI[0], (yb2 - ya_ - 6) / tI[1], max(1.25 * ech, 1.6))
        if meilleure is None or s > meilleure[0]:
            meilleure = (s, xa_, ya_, xb_, yb2)
    if meilleure and meilleure[0] >= 0.35:
        s, xa_, ya_, xb_, yb2 = meilleure
        w_, h_ = tI * s + 6
        x0_, y0_ = xa_ + (xb_ - xa_ - w_) / 2, yb2 - h_
        limI = (loI[0] - 3 / s, hiI[0] + 3 / s, loI[1] - 3 / s, hiI[1] + 3 / s)
        axI = _axes_vue(fig, x0_, y0_, limI, s)
        f_iso = f_os[(cu > u0 - 4) & (cu < u1 + 4)]
        gris = [(p[2], p[3], (0.93, 0.93, 0.93), "fort") for p in pieces]
        _dessiner_vue(axI, [(v_os, f_iso, (0.84, 0.82, 0.78), None)] + gris, vues["ISO"], limI, 25.4 / (180 * s),
                      ombre=True, lw_fort=TRAIT_FIN * 1.1, angle_vif=60.0)
        _titre_vue(fond, x0_ + 2, y0_ + h_ + 1.0, "VUE ISOMÉTRIQUE", "sans échelle")
    # colonne de droite : cotes du cas, notes et mode opératoire
    lignes = []
    for x in d_.get("fentes", []):
        lignes.append((f"fente {x['fente']} (PC{x['fente']})", f"{_fr(x['longueur_mm'])} × {_fr(x['largeur_mm'], 2)} ; "
                       f"tour {_fr(x['hauteur_tour_mm'])} ; lame {_fr(x['profondeur_lame_mm'])} du haut de la tour à la "
                       f"{x.get('arret_lame', 'charnière')}"))
    if d_:
        lignes += [
            ("angle PC1 / PC2", f"{_fr(d_['angle_entre_fentes_deg'], 1)}°" if d_.get("angle_entre_fentes_deg") else "1 fente"),
            ("manchons", f"Ø ext. {_fr(d_['manchon_diametre_exterieur_mm'], 2)} ; trou Ø {_fr(d_['trou_broche_mm'], 2)}"),
            ("broches", " ; ".join(f"{b['nom']} à {_fr(b['distance_coupe_mm'])} de la coupe (manchon {_fr(b['hauteur_manchon_mm'])})"
                                   for b in d_.get("broches", []))),
            ("coque", f"longueur {_fr(d_['coque']['longueur_mm'])} ; e = {_fr(d_['coque']['epaisseur_mm'], 1)} ; j = "
                      f"{_fr(d_['coque']['jeu_mm'], 2)} ; ± {_fr(d_['coque']['secteur_deg'], 0)}°"),
            ("ponts (3)", f"{d_['ponts'].get('nombre', 2)} × {_fr(d_['ponts']['section_mm'][0], 1)} × "
                          f"{_fr(d_['ponts']['section_mm'][1], 1)}"),
            ("encombrement 1+2+3", "{} × {} × {}".format(*(_fr(d_["guide_coupe"][k]) for k in ("longueur_axe_os_mm", "largeur_mm", "hauteur_mm")))),
        ]
        if d_.get("guide_reduction"):
            gr_ = d_["guide_reduction"]
            lignes.append(("pièce 4", "{} × {} × {} ; {} manchons de {} ; barre à {} de l'os".format(
                *(_fr(gr_[k]) for k in ("longueur_axe_os_mm", "largeur_mm", "hauteur_mm")), gr_["nombre_manchons"],
                _fr(gr_["manchon_longueur_mm"]), _fr(gr_["ecart_os_mm"]))))
    generales = [
        "Cotes en mm ; tolérances générales ± 0,1 (impression 3D). Projection européenne ; vue isométrique sans échelle.",
        "Traits mixtes fins : axes des broches. Traits mixtes à deux points : plans de coupe de l'os (PC1, PC2).",
        "Os en gris : pièce voisine, montrée pour le repérage (interrompue par un trait ondulé ; hachuré en gris "
        "dans la coupe E-E ; contour en trait mixte gris dans la vue C).",
        "Pièces 1, 2 et 3 imprimées d'un seul tenant (guide_coupe.stl) ; distances des broches comptées depuis le "
        "plan de coupe de leur fragment.",
    ]
    proto = info.get("protocole") or []
    x_t, larg_t = 300.0, [27, 78]
    y_bas = Y_NOMEN + 2
    for t_ in (6.2, 5.9, 5.6, 5.3, 5.0, 4.7):
        hl = t_ * 0.5
        n1 = [(f"{i + 1}.", l_) for i, l_ in enumerate(generales)]
        n2 = [(f"{i + 1}.", l_) for i, l_ in enumerate(proto)]
        h_tot = (_hauteur_tableau(lignes, larg_t, t_, hl) + _hauteur_tableau(n1, [6, 99], t_, hl, entete=False)
                 + (_hauteur_tableau(n2, [6, 99], t_, hl, entete=False) if n2 else 0) + 8)
        if Y_HAUT + 6 - h_tot >= y_bas:
            break
    y = _tableau(fond, x_t, Y_HAUT + 6, "Cotes de ce guide (mm)", ["élément", "valeur"], lignes, larg_t, taille=t_,
                 h_ligne=hl)
    y = _tableau(fond, x_t, y - 4, "Notes", ["", ""], n1, [6, 99], taille=t_, h_ligne=hl, entete=False)
    if n2:
        _tableau(fond, x_t, y - 4, "Mode opératoire", ["", ""], n2, [6, 99], taille=t_, h_ligne=hl, entete=False)
    # nomenclature et cartouche
    n_b = len(geo["broches"])
    ob = _fr(float((d_.get("parametres") or {}).get("broche_mm", 1.6)), 1)
    nomen = [("1", "1", "Guide de coupe : moitié proximale", "PA12", "guide_coupe.stl (pièces 1 à 3)"),
             ("2", "1", "Guide de coupe : moitié distale", "PA12", "guide_coupe.stl"),
             ("3", str(d_.get("ponts", {}).get("nombre", 2)), "Pont sécable", "PA12", "venu de matière ; à couper")]
    if red is not None:
        nomen.append(("4", "1", "Guide de réduction", "PA12", "guide_reduction.stl"))
    nomen.append(("5", str(n_b), f"Broche de Kirschner Ø{ob}", "Inox", "du commerce (non fournie)"))
    y_n = _nomenclature(fond, nomen, CADRE[1] + 52)
    serie = (pr.get("os_segmente") or {}).get("serie")
    derot = float((pr.get("correction") or {}).get("derotation_deg") or 0)
    os_nom = {"tibia": "Tibia", "femur": "Fémur", "radius": "Radius"}.get(pr.get("os"), pr.get("os", ""))
    designation = (f"{os_nom} {pr.get('cote', '')} · {'coin de fermeture' if kind == 'fermeture' else 'coin d’ouverture'}"
                   f" θ = {_fr(theta, 1)}°" + (f", dérotation {_fr(derot, 1)}°" if abs(derot) >= 1 else "")
                   + f" · {serie or 'os fictif (modèle)'}")
    _controle_echelle(fond, k_ech)
    _cartouche(fond, "GUIDE DE COUPE ET DE RÉDUCTION", designation, _numero_plan(pr, "01"), _echelle_txt(k_ech),
               "PA12 (frittage laser) ou résine stérilisable", "± 0,1 ; jeux réglés sur coupons")
    return _enregistrer(fig, base)


# --------------------------------------------------------------------------- point d'entrée (etape7_guide.generer)
def dessiner(dossier, pr, info, v_os, f_os, guide, moities, ponts, red, geo, broches_c, vc, fc):
    """Écrit les deux plans dans `dossier` ; renvoie la liste des fichiers créés."""
    import etape7_guide as E7
    dossier = Path(dossier)
    # valeurs de ce cas (pendant la construction, parametres.py porte les valeurs choisies pour le cas), valeurs de la
    # planification (prescription), valeurs par défaut (relevées au chargement de etape7_guide)
    valeurs = {**PLANIF_DEFAUT, **E7.valeurs_parametres()}
    for k in PLANIF_DEFAUT:
        if k in (pr.get("parametres_guide") or {}):
            valeurs[k] = float(pr["parametres_guide"][k])
    st = pr.get("strategie", {})
    titre = f"{pr.get('os', '')}, {st.get('type_coin', '')}, θ = {_fr(float(pr['deformite']['theta_deg']), 1)}°"
    defauts = {**PLANIF_DEFAUT, **(info.get("parametres_defaut") or E7.PARAMETRES_DEFAUT)}
    with plt.rc_context(STYLE):
        sortis = plan_generique(dossier / "plan_generique", valeurs, defauts, info.get("dimensions"), titre, pr)
        sortis += plan_cote(dossier / "plan_guide", pr, info, v_os, f_os, moities, ponts, red, geo, broches_c, vc,
                            fc, E7.depuis_manifold)
    return sortis
