"""
dessin_guide.py — plans 2D du guide de coupe (CT-CORA3D, étape 7).

Rôle    : 1. plan GÉNÉRIQUE (plan_generique.svg / .pdf / .png) : le guide en schéma (coupe dans le plan d'une fente, vue
             de la face d'appui, coupe d'un manchon), ses cotes en SYMBOLES (j, e, g, p, s, js, Øb, jb, m, hp, α, eb, kd)
             et le tableau des paramètres (valeur par défaut, valeur de ce cas), avec les formules des dimensions qui
             découlent de l'os : c'est le « modèle paramétrique » du guide, comme une pièce pilotée par une table.
          2. plan COTÉ du cas (plan_guide.svg / .pdf / .png) : le guide construit pour CET os, en projections
             orthogonales (A : depuis la face d'appui, B : de profil, C : axiale ; D : guide de réduction vu le long des
             broches), cotes principales, tableau des dimensions du cas et cartouche ; échelle 2:1, 1:1 ou 1:2 sur A3,
             avec une cote de contrôle de 50 mm pour vérifier l'échelle à l'impression.
Entrées : celles de etape7_guide.generer (prescription, guide.json, maillages manifold3d, repère du guide).
Méthode : projection orthogonale ; parties cachées par un tampon de profondeur (z-buffer en numpy : chaque pixel garde
          le triangle le plus proche ; faces arrière des solides fermés ignorées ; ≈ 180 points par pouce sur la
          feuille) ; traits = arêtes de silhouette et arêtes vives (> 35°) VISIBLES, en vecteurs ; aplats de couleur en
          image dans le fichier (fichiers vectoriels légers). matplotlib, moteur « Agg » (sans écran).
"""
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402
import numpy as np                                                 # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Arc, Circle, Polygon, Rectangle, Wedge  # noqa: E402

A3 = (420.0, 297.0)                    # mm, paysage
ENCRE = "#1d232a"
COTE = "#0b5cad"                       # couleur des cotes
GRIS = "#4a5560"
COULEURS = {"proximal": (0.80, 0.87, 0.95), "distal": (0.79, 0.93, 0.89), "ponts": (0.97, 0.80, 0.63),
            "reduction": (0.88, 0.82, 0.94), "os": (0.93, 0.90, 0.84), "coin": (0.98, 0.92, 0.66),
            "broches": (0.97, 0.72, 0.52)}
PLANIF_DEFAUT = {"ecart_broches_mm": 10.0, "facteur_distance_broches": 1.2}   # planification (cœur JavaScript)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "svg.fonttype": "none", "pdf.fonttype": 42})


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
    lignes 0 = bas. (Remplace deux rendus matplotlib de triangles subdivisés, 10 à 20 fois plus lents.)"""
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


def _dessiner_vue(ax, pieces, vue, lims, pas=0.07, lw=0.45):
    """pieces : [(sommets, triangles, couleur RGB, trait ?)] ; image des aplats + traits visibles. Les pièces « fort »
    sont des solides fermés (manifold3d) : leurs faces tournées vers l'arrière sont toujours cachées et ne sont pas
    rendues (moitié moins de travail). L'os de contexte (« fin ») est découpé autour du guide, donc ouvert : rendu en
    entier."""
    tris, cols = [], []
    for v, f, c, trait in pieces:
        t = _projeter(v, vue)[f]
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        if trait == "fort" and len(t):
            # sens des faces : signe du volume, calculé dans le repère de la vue (juste même si ce repère est inversé)
            signe = 1.0 if np.einsum("ij,ij->", np.cross(t[:, 0], t[:, 1]), t[:, 2]) >= 0 else -1.0
            devant = signe * n[:, 2] > 0
            t, n = t[devant], n[devant]
        nz = np.abs(n[:, 2]) / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
        tris.append(t)
        cols.append(np.clip(np.asarray(c)[None, :] * (0.78 + 0.22 * nz[:, None]), 0, 1))
    prof, img, info = _rendu(np.concatenate(tris), np.concatenate(cols), lims, pas)
    xa, ya, p_, nx, ny = info
    fond = np.all(img > 0.995, axis=2)
    rgba = np.dstack([img, np.where(fond, 0.0, 1.0)])
    ax.imshow(rgba, origin="lower", extent=(xa, xa + nx * p_, ya, ya + ny * p_), interpolation="bilinear", zorder=1,
              rasterized=True)
    for v, f, c, trait in pieces:
        if not trait:
            continue
        q = _projeter(v, vue)
        seg = _visibles(q[_aretes(f, q)], prof, info)
        if len(seg):
            ax.add_collection(LineCollection(seg, colors=ENCRE if trait == "fort" else "#8a8170",
                                             linewidths=lw if trait == "fort" else 0.25, zorder=3))
    ax.set_xlim(lims[0], lims[1])
    ax.set_ylim(lims[2], lims[3])
    return prof, info


# --------------------------------------------------------------------------- cotes
def _cote(ax, a, b, decal, texte, couleur=COTE, taille=6.3):
    """Cote entre a et b (mm de la vue), décalée du vecteur `decal` (mm), avec lignes d'attache."""
    a, b, dv = np.asarray(a, float), np.asarray(b, float), np.asarray(decal, float)
    a2, b2 = a + dv, b + dv
    e_ = _unitaire(dv) * 1.2 if np.linalg.norm(dv) > 0 else np.zeros(2)
    for p, p2 in ((a, a2), (b, b2)):
        ax.plot([p[0], p2[0] + e_[0]], [p[1], p2[1] + e_[1]], color=couleur, lw=0.3, zorder=9, clip_on=False)
    ax.annotate("", xy=b2, xytext=a2, annotation_clip=False,
                arrowprops=dict(arrowstyle="<|-|>", color=couleur, lw=0.5, shrinkA=0, shrinkB=0, mutation_scale=5), zorder=9)
    d = _unitaire(b2 - a2)
    ang = np.degrees(np.arctan2(d[1], d[0]))
    ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
    m = (a2 + b2) / 2 + _unitaire(dv) * 1.8 if np.linalg.norm(dv) > 0 else (a2 + b2) / 2
    ax.text(m[0], m[1], texte, color=couleur, fontsize=taille, ha="center", va="center", rotation=ang, zorder=10,
            clip_on=False, bbox=dict(boxstyle="square,pad=0.06", fc="white", ec="none", alpha=0.9))


def _repere(ax, p, texte, dxy=(6, 6), couleur=COTE, taille=6.3, ha="left"):
    p = np.asarray(p, float)
    ax.annotate(texte, xy=p, xytext=p + np.asarray(dxy, float), color=couleur, fontsize=taille, zorder=10, ha=ha,
                annotation_clip=False,
                arrowprops=dict(arrowstyle="-|>", color=couleur, lw=0.45, mutation_scale=5, shrinkA=0, shrinkB=0),
                bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none", alpha=0.9))


def _trait_mixte(ax, a, b, couleur="#6b7480"):
    ax.plot([a[0], b[0]], [a[1], b[1]], color=couleur, lw=0.4, ls=(0, (7, 2, 1, 2)), zorder=8)


# --------------------------------------------------------------------------- mise en page
def _feuille(titre, sous_titre=""):
    fig = plt.figure(figsize=(A3[0] / 25.4, A3[1] / 25.4))
    fond = fig.add_axes([0, 0, 1, 1])
    fond.set_xlim(0, A3[0])
    fond.set_ylim(0, A3[1])
    fond.axis("off")
    fond.add_patch(Rectangle((10, 10), A3[0] - 20, A3[1] - 20, fill=False, lw=0.8, ec=ENCRE))
    fond.text(16, A3[1] - 18, titre, fontsize=12, fontweight="bold", color=ENCRE, va="center")
    if sous_titre:
        fond.text(16, A3[1] - 25, sous_titre, fontsize=7.2, color=GRIS, va="center")
    return fig, fond


def _axes_vue(fig, x0, y0, lims, echelle):
    """Axes placés pour qu'un millimètre de l'objet mesure `echelle` mm sur la feuille. lims = (xmin, xmax, ymin, ymax)."""
    xa, xb, ya, yb = lims
    w, h = (xb - xa) * echelle, (yb - ya) * echelle
    ax = fig.add_axes([x0 / A3[0], y0 / A3[1], w / A3[0], h / A3[1]])
    ax.set_xlim(xa, xb)
    ax.set_ylim(ya, yb)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax


def _echelle_txt(e):
    return {2.0: "2:1", 1.0: "1:1", 0.5: "1:2"}.get(e, f"{_fr(e, 2)}:1")


def _cartouche(fond, x0, y0, lignes, echelle, larg=190.0):
    haut = 4.0 + 5.0 * len(lignes)
    fond.add_patch(Rectangle((x0, y0), larg, haut, fill=False, lw=0.7, ec=ENCRE))
    for i, (cle, val) in enumerate(lignes):
        y = y0 + haut - 4.5 - 5.0 * i
        fond.text(x0 + 3, y, cle, fontsize=6.2, color=GRIS, va="center")
        fond.text(x0 + 30, y, val, fontsize=6.6, color=ENCRE, va="center")
        if i < len(lignes) - 1:
            fond.plot([x0, x0 + larg], [y - 2.5, y - 2.5], color="#c9cfd6", lw=0.3)
    L, yb = 50.0 * echelle, y0 + haut + 6
    fond.plot([x0 + 3, x0 + 3 + L], [yb, yb], color=ENCRE, lw=1.0)
    for x in (x0 + 3, x0 + 3 + L):
        fond.plot([x, x], [yb - 1.5, yb + 1.5], color=ENCRE, lw=0.8)
    fond.text(x0 + 6 + L, yb, f"cote de contrôle : 50 mm de l'objet ({_fr(L, 0)} mm imprimés, échelle {_echelle_txt(echelle)})",
              fontsize=6.0, va="center", color=ENCRE)


def _tableau(fond, x0, y0, titre, lignes, colonnes, larg_col, h_ligne=4.3, taille=6.0, largeur_max=None):
    """Tableau ; les cellules trop longues passent à la ligne. Renvoie l'ordonnée sous le tableau."""
    fond.text(x0, y0, titre, fontsize=7.5, fontweight="bold", color=ENCRE, va="bottom")
    y = y0 - 2
    xs = np.cumsum([0] + list(larg_col[:-1])) + x0
    for j, c in enumerate(colonnes):
        fond.text(xs[j], y - h_ligne / 2, c, fontsize=taille, fontweight="bold", color=GRIS, va="center")
    fond.plot([x0, x0 + sum(larg_col)], [y - h_ligne, y - h_ligne], color=ENCRE, lw=0.4)
    y -= h_ligne
    car = [max(4, int(w / (taille * 0.19))) for w in larg_col]          # caractères par ligne et par colonne (approx.)
    for ligne in lignes:
        morceaux = []
        for j, val in enumerate(ligne):
            mots, cour, out = str(val).split(" "), "", []
            for m_ in mots:
                if cour and len(cour) + 1 + len(m_) > car[j]:
                    out.append(cour)
                    cour = m_
                else:
                    cour = f"{cour} {m_}".strip()
            out.append(cour)
            morceaux.append(out)
        n = max(len(x) for x in morceaux)
        for j, out in enumerate(morceaux):
            for i, txt in enumerate(out):
                fond.text(xs[j], y - h_ligne * (i + 0.5), txt, fontsize=taille, color=ENCRE, va="center")
        y -= h_ligne * n
    return y


def _enregistrer(fig, base):
    sortis = []
    for ext, kw in ((".svg", {}), (".pdf", {}), (".png", {"dpi": 170})):
        chemin = Path(str(base) + ext)
        fig.savefig(chemin, **kw)
        sortis.append(chemin.name)
    plt.close(fig)
    return sortis


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
    ("pl", "profondeur_lame_mm", "profondeur de lame, haut de tour → butée (0 = auto, 5 mm)", "mm"),
    ("dl", "depassement_mm", "coupe complète : dépassement de la corticale", "mm"),
    ("c", "chanfrein_mm", "chanfreins d'entrée (fentes, manchons)", "mm"),
    ("V", "verrou", "verrou de réduction intégré (1) / guide séparé (0)", ""),
    ("jo", "jeu_verrou_mm", "verrou : écart entre les oreilles", "mm"),
    ("eo", "oreille_mm", "verrou : épaisseur d'une oreille", "mm"),
    ("eb", "ecart_broches_mm", "écart entre 2 broches d'un fragment (planif.)", "mm"),
    ("kd", "facteur_distance_broches", "distance broche–coupe / largeur de l'os (planif.)", "×"),
    ("jv", "jeu_voisin_mm", "distance minimale aux os voisins", "mm"),
    ("mc", "marge_cartilage_mm", "écart supplémentaire au cartilage", "mm"),
    ("er", "reduction_ecart_mm", "réduction : barre → os", "mm"),
    ("lr", "reduction_manchon_mm", "réduction : longueur des manchons", "mm"),
    ("tb", "reduction_barre_mm", "réduction : épaisseur de la barre", "mm"),
]


def plan_generique(base, valeurs_cas, defauts, dims=None, titre_cas=""):
    """Schéma paramétrique du guide (non à l'échelle) et tableau des paramètres."""
    fig, fond = _feuille("Guide de coupe générique : modèle paramétrique (schéma, non à l'échelle)",
                         "Les cotes en symboles sont des PARAMÈTRES modifiables (onglet CORA, étape 12) ; les cotes « = … » "
                         "DÉCOULENT de l'os segmenté et sont recalculées pour chaque scanner." + (f"   Cas : {titre_cas}." if titre_cas else ""))
    # --- A. coupe dans le plan de la fente : os, coque (j, e, ±α), tour de fente (g, p, s + js)
    ax = fig.add_axes([16 / A3[0], 95 / A3[1], 96 / A3[0], 165 / A3[1]])
    ax.set_xlim(-30, 30)
    ax.set_ylim(-40, 63)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(-30, 61, "A · Coupe dans le plan d'une fente", fontsize=8, color=ENCRE, va="top")
    R, j, e, alpha = 13.0, 1.8, 4.0, 62.0
    ax.add_patch(Circle((0, 0), R, fc=COULEURS["os"], ec=ENCRE, lw=0.6))
    ax.add_patch(Circle((0, 0), R * 0.42, fc="white", ec="#b8b0a2", lw=0.4))
    ax.text(0, -R * 0.68, "os", ha="center", fontsize=6.5, color="#6b6458")
    ax.add_patch(Wedge((0, 0), R + j + e, 90 - alpha, 90 + alpha, width=e, fc=COULEURS["proximal"], ec=ENCRE, lw=0.6))
    tw, sw, y1t = 7.2, 1.4, R + j + e + 15.0
    ax.add_patch(Rectangle((-tw / 2, R + j + e - 0.8), tw, y1t - (R + j + e - 0.8), fc=COULEURS["proximal"], ec=ENCRE, lw=0.6))
    ax.add_patch(Rectangle((-sw / 2, -R - 3), sw, y1t + R + 4, fc="white", ec="#b03030", lw=0.5, ls="--", zorder=3))
    ax.text(sw / 2 + 0.7, -R - 2.6, "trajet de la lame", fontsize=5.6, color="#b03030", rotation=90, va="bottom")
    ang_j, ang_e = np.radians(145), np.radians(38)
    pj0, pj1 = R * np.array([np.cos(ang_j), np.sin(ang_j)]), (R + j) * np.array([np.cos(ang_j), np.sin(ang_j)])
    _repere(ax, (pj0 + pj1) / 2, "j", (-9, 4))
    pe0, pe1 = (R + j) * np.array([np.cos(ang_e), np.sin(ang_e)]), (R + j + e) * np.array([np.cos(ang_e), np.sin(ang_e)])
    _cote(ax, pe0, pe1, 3.5 * np.array([np.sin(ang_e), -np.cos(ang_e)]), "e")
    _cote(ax, (tw / 2, R + j + e), (tw / 2, y1t), (5, 0), "g")
    _cote(ax, (-tw / 2, y1t), (-sw / 2, y1t), (0, 3.5), "p")
    _cote(ax, (-sw / 2, y1t + 7), (sw / 2, y1t + 7), (0, 2.5), "s + js")
    ra = R + j + e + 5
    ax.add_patch(Arc((0, 0), 2 * ra, 2 * ra, theta1=90, theta2=90 + alpha, color=COTE, lw=0.5))
    ax.text(-ra * np.sin(np.radians(alpha / 2)) - 2.5, ra * np.cos(np.radians(alpha / 2)) + 1.5, "α", color=COTE, fontsize=8)
    ax.plot([0, 0], [0, ra + 2], color="#6b7480", lw=0.4, ls=(0, (6, 2, 1, 2)))
    ax.text(1.0, y1t + 13, "face d'appui ↑ (abord)", fontsize=6.2, color=GRIS)
    # butée de profondeur : du haut de la tour à la charnière (ou à la corticale opposée − dl), la même pour toutes les fentes
    y_ch = -R + 2.0
    ax.plot([-sw / 2 - 2.5, sw / 2 + 2.5], [y_ch, y_ch], color="#b03030", lw=0.6)
    ax.text(-sw / 2 - 3.0, y_ch, "charnière", fontsize=5.6, color="#b03030", ha="right", va="center")
    _cote(ax, (-tw / 2, y1t), (-tw / 2, y_ch), (-19, 0), "pl")
    _cote(ax, (-R, -R), (R, -R), (0, -6), "= largeur de l'os dans le plan de coupe", taille=5.8)
    _cote(ax, (-R - 1, -R), (R + 1, -R), (0, -14), "longueur de fente = largeur de l'os + 2", taille=5.8)
    # --- B. vue de la face d'appui : deux moitiés, fentes, ponts, manchons, broches
    ax = fig.add_axes([122 / A3[0], 30 / A3[1], 112 / A3[0], 232 / A3[1]])
    ax.set_xlim(-28, 28)
    ax.set_ylim(-60, 56)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(-28, 55, "B · Vue de la face d'appui (coin de fermeture, « 2 en 1 »)", fontsize=8, color=ENCRE, va="top")
    th, Wg = np.radians(14), 13.0
    yb = lambda x: -1.2 - np.tan(th) * (x + Wg)
    ax.add_patch(Polygon([(-Wg, 44), (Wg, 44), (Wg, 1.6), (-Wg, 1.6)], fc=COULEURS["proximal"], ec=ENCRE, lw=0.6))
    ax.add_patch(Polygon([(-Wg, yb(-Wg) - 0.4), (Wg, yb(Wg) - 0.4), (Wg, -50), (-Wg, -50)], fc=COULEURS["distal"], ec=ENCRE, lw=0.6))
    ax.add_patch(Polygon([(-Wg, 0.8), (Wg, 0.8), (Wg, yb(Wg) + 0.4), (-Wg, yb(-Wg) + 0.4)], fc=COULEURS["coin"], ec=ENCRE, lw=0.6))
    ax.text(Wg - 0.8, -4.9, "pièce du coin", fontsize=5.6, color="#7a6200", ha="right")
    for x in (-Wg - 1.6, Wg - 0.4):                      # ponts sécables : 2 par fente de séparation
        ax.add_patch(Rectangle((x, -0.2), 2.0, 2.0, fc=COULEURS["ponts"], ec=ENCRE, lw=0.5, zorder=4))
        ax.add_patch(Rectangle((x, yb(x + 1.0) - 1.0), 2.0, 2.0, fc=COULEURS["ponts"], ec=ENCRE, lw=0.5, zorder=4))
    _repere(ax, (Wg + 1.0, 0.8), "pont sécable\np × hp (2 par fente)", (5, 6))
    ax.plot([-Wg - 2.5, Wg + 2.5], [1.2, 1.2], color="#b03030", lw=0.6)
    ax.plot([-Wg - 2.5, Wg + 2.5], [yb(-Wg - 2.5), yb(Wg + 2.5)], color="#b03030", lw=0.6)
    ax.text(-Wg - 8.6, 2.6, "fente 1\n(séparation)", fontsize=5.6, color="#b03030", ha="right", va="center")
    ax.text(-Wg - 8.6, yb(-Wg) - 3.0, "fente 2\n(séparation)", fontsize=5.6, color="#b03030", ha="right", va="center")
    # oreilles du verrou, de part et d'autre du trait, au-delà du bout des tours : vues le long des broches, superposées
    # (oreille distale au-dessus, trou traversant ; oreille proximale dessous, trou borgne)
    for sg in (-1.0, 1.0):
        xo = sg * (Wg + 5.0)
        ax.add_patch(Rectangle((min(sg * Wg, sg * (Wg + 5.0)), 1.6), 5.0, 2.6, fc=COULEURS["proximal"], ec=ENCRE, lw=0.5, zorder=3))
        ax.add_patch(Rectangle((min(sg * Wg, sg * (Wg + 5.0)), -3.4), 5.0, 2.6, fc=COULEURS["distal"], ec=ENCRE, lw=0.5, zorder=3))
        ax.add_patch(Circle((xo, 0.3), 2.9, fc=COULEURS["distal"], ec=ENCRE, lw=0.6, zorder=5))
        ax.add_patch(Circle((xo, 0.3), 0.9, fc="white", ec=ENCRE, lw=0.5, zorder=6))
    _repere(ax, (Wg + 5.0, -2.6), "oreilles du verrou :\nP dessous, D dessus ;\nØ(Øb + jb + 2p) × eo,\nécart jo ; broche Øb", (-3.5, -14), taille=5.6)
    ax.add_patch(Arc((-Wg, 1.2), 24, 24, theta1=-np.degrees(th), theta2=0, color=COTE, lw=0.5))
    ax.text(-Wg + 12.8, -1.6, "θ", color=COTE, fontsize=7)
    rs, rh = 2.9, 0.9
    for (x, y) in ((0, 14), (0, 25), (0, -16), (0, -27)):
        ax.add_patch(Circle((x, y), rs, fc="white", ec=ENCRE, lw=0.6, zorder=4))
        ax.add_patch(Circle((x, y), rh, fc="#9aa0a6", ec=ENCRE, lw=0.4, zorder=5))
    _cote(ax, (-rs, 1.2), (-rs, 14), (-6, 0), "d = kd × largeur")
    _cote(ax, (-rs, 14), (-rs, 25), (-6, 0), "eb")
    _cote(ax, (-rs, 25), (-rs, 44), (-6, 0), "m")
    _cote(ax, (-rs, -27), (-rs, -50), (-6, 0), "m")
    _repere(ax, (rs * 0.7, 25 + rs * 0.7), "manchon Ø(Øb + jb + 2p)\ntrou Ø(Øb + jb)", (5, 9))
    ax.text(-Wg + 1, 40, "moitié proximale", fontsize=6.2, color="#1f4f80")
    ax.text(-Wg + 1, -47.5, "moitié distale", fontsize=6.2, color="#17675a")
    _cote(ax, (-Wg, -50), (Wg, -50), (0, -5), "= os + coque (± α)", taille=5.8)
    # --- C. manchon en coupe
    ax = fig.add_axes([243 / A3[0], 160 / A3[1], 48 / A3[0], 100 / A3[1]])
    ax.set_xlim(-12, 12)
    ax.set_ylim(-16, 34)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(-12, 33, "C · Manchon (coupe)", fontsize=8, color=ENCRE, va="top")
    ax.add_patch(Rectangle((-12, -16), 24, 10, fc=COULEURS["os"], ec=ENCRE, lw=0.5))
    ax.add_patch(Rectangle((-6, -5.6), 12, 4.0, fc=COULEURS["proximal"], ec=ENCRE, lw=0.5))
    ax.add_patch(Rectangle((-3.4, -1.6), 6.8, 22, fc=COULEURS["proximal"], ec=ENCRE, lw=0.5))
    ax.add_patch(Rectangle((-0.8, -16), 1.6, 44, fc="#9aa0a6", ec=ENCRE, lw=0.4))
    _cote(ax, (-0.8, 22), (0.8, 22), (0, 4), "Øb")
    _cote(ax, (-3.4, -5.6), (-3.4, 20.4), (-4, 0), "e + g")
    _cote(ax, (0.8, 10), (3.4, 10), (0, 0), "")
    ax.text(5.2, 10, "p", color=COTE, fontsize=6.5, va="center")
    ax.text(6, -12, "os", fontsize=6.2, color="#6b6458")
    # --- tableaux : paramètres, dimensions qui découlent de l'os
    lignes = []
    for sym, cle, desc, unite in SYMBOLES:
        d_ = defauts.get(cle, PLANIF_DEFAUT.get(cle))
        c_ = valeurs_cas.get(cle, d_)
        if d_ is None:
            continue
        dec = 2 if abs(float(d_)) < 1 or cle.startswith("jeu") or cle in ("lame_mm",) else 1
        modif = c_ is not None and abs(float(c_) - float(d_)) > 1e-9
        if cle == "verrou":                                       # interrupteur : 1 ou 0
            txt = lambda x: str(int(round(float(x))))
        elif cle == "profondeur_lame_mm":                         # 0 = automatique
            txt = lambda x: "auto" if float(x) <= 0 else _fr(float(x), 1)
        else:
            txt = lambda x: _fr(float(x), dec)
        lignes.append((sym, desc, txt(d_), txt(c_) + (" ◄" if modif else ""), unite))
    y = _tableau(fond, 300, 262, "Paramètres du guide générique", lignes, ["sym.", "description", "défaut", "ce cas", ""],
                 [10, 62, 13, 15, 6], h_ligne=4.1, taille=5.8)
    if dims:
        derives = [
            ("fente(s)", " ; ".join(f"{_fr(x['longueur_mm'])} × {_fr(x['largeur_mm'], 2)}" for x in dims.get("fentes", []))),
            ("tour (hauteur)", " ; ".join(_fr(x["hauteur_tour_mm"]) for x in dims.get("fentes", []))),
            ("profondeur de lame pl", f"{_fr(dims['butee']['profondeur_lame_mm'], 0)} (minimum {_fr(dims['butee']['minimale_mm'])}) ; butée : "
                                      + ", ".join(x.get("butee", "charnière") for x in dims.get("fentes", []))) if dims.get("butee") else None,
            ("manchon Ø ext. / trou", f"{_fr(dims['manchon_diametre_exterieur_mm'], 2)} / {_fr(dims['trou_broche_mm'], 2)}"),
            ("coque (longueur)", _fr(dims["coque"]["longueur_mm"])),
            ("angle entre fentes", f"{_fr(dims['angle_entre_fentes_deg'], 1)}°" if dims.get("angle_entre_fentes_deg") else "1 fente"),
            ("broches → coupe", " ; ".join(f"{b['nom']} {_fr(b['distance_coupe_mm'])}" for b in dims.get("broches", []))),
            ("encombrement", "{} × {} × {}".format(*(_fr(dims["guide_coupe"][k]) for k in ("longueur_axe_os_mm", "largeur_mm", "hauteur_mm")))),
        ]
        _tableau(fond, 300, y - 7, "Dimensions qui découlent de l'os (ce cas, mm)", [d for d in derives if d], ["dimension", "valeur"],
                 [30, 76], h_ligne=4.1, taille=5.8)
    fond.text(16, 31, "Formules : longueur de fente = largeur de l'os + 2 ; haut de tour = butée + pl, avec pl = os + j + e + g − butée "
              "arrondi aux 5 mm (le même pour toutes les fentes) ; butée = charnière, ou corticale opposée − dl ;", fontsize=6.2, color=GRIS)
    fond.text(16, 26, "épaisseur de tour = s + js + 2p ; manchon Ø = Øb + jb + 2p ; d = kd × largeur de l'os ; oreilles du verrou : Ø(Øb + jb + 2p) "
              "× eo, superposées à jo, au-delà des tours, trou commun après la correction ;", fontsize=6.2, color=GRIS)
    fond.text(16, 21, "coque = de (broche la plus proximale − m) à (la plus distale + m), à ≥ 10 mm des extrémités articulaires ; "
              "ponts = p × hp ;  ◄ : valeur changée pour ce cas.", fontsize=6.2, color=GRIS)
    fond.text(16, 15, f"CT-CORA3D, étape 7 (dessin_guide.py) — {time.strftime('%d/%m/%Y %H:%M')} — prototype de recherche, "
              "non validé cliniquement.", fontsize=6.0, color=GRIS)
    return _enregistrer(fig, base)


# --------------------------------------------------------------------------- plan coté du cas
def plan_cote(base, pr, info, v_os, f_os, moities, ponts, red, geo, broches_c, vc, fc, depuis_manifold, titre="Guide de coupe : plan coté du cas"):
    """Projections orthogonales du guide de coupe (et du guide de réduction) de ce cas, cotes, tableau, cartouche."""
    u = _unitaire(geo["u"])
    face = _unitaire(geo["face"])
    face = _unitaire(face - (face @ u) * u)
    cote_ = _unitaire(np.cross(u, face))
    K = np.asarray(geo["K"], float)
    pieces = []
    coin = (geo.get("pieces") or {}).get("coin")
    allege = lambda m_: m_.simplify(0.02)      # 0,02 mm, invisible à l'échelle du plan : 5 fois moins de triangles
    for nom, m_ in (("proximal", moities[0]), ("distal", moities[1]), ("coin", coin), ("ponts", ponts)):
        if m_ is not None and not m_.is_empty():
            vv, ff = depuis_manifold(allege(m_))
            pieces.append((nom, vv, ff))
    tous = np.vstack([p[1] for p in pieces])
    vues = {
        "A": {"o": K, "x": cote_, "y": -u, "z": face, "titre": "A · depuis la face d'appui"},
        "B": {"o": K, "x": face, "y": -u, "z": -cote_, "titre": "B · de profil"},
        "C": {"o": K, "x": cote_, "y": face, "z": -u, "titre": "C · axiale (depuis proximal)"},
    }
    marge = 9.0
    lims = {}
    for k_, vue in vues.items():
        q = _projeter(tous, vue)
        lo, hi = q[:, :2].min(0), q[:, :2].max(0)
        lims[k_] = (lo[0] - marge, hi[0] + marge, lo[1] - marge, hi[1] + marge)
    # après la correction, vu le long des broches (parallèles) : guide de réduction séparé, ou moitiés remises en place
    # avec leurs broches de verrouillage (verrou intégré)
    vueD = None
    V = geo.get("verrou") or {}
    apres = []
    if red is not None:
        apres = [("reduction", *depuis_manifold(red))]
    elif V.get("oreilles") and moities[0] is not None and moities[1] is not None:
        import etape7_guide as E7
        Tm = np.asarray(V["T"], float)
        tiges = E7.m3d.Manifold.batch_boolean([E7.tige_verrou(o_, E7.P.GUIDE_BROCHE_MM / 2, 12.0) for o_ in V["oreilles"]],
                                              E7.m3d.OpType.Add)
        apres = [("proximal", *depuis_manifold(allege(moities[0]))), ("distal", *depuis_manifold(allege(moities[1]).transform(Tm[:3, :]))),
                 ("broches", *depuis_manifold(tiges))]
    if apres and broches_c:
        o = _unitaire(-np.mean([_unitaire(x["d"]) for x in broches_c], 0))
        ud = _unitaire(u - (u @ o) * o)
        vueD = {"o": np.mean([x["a"] for x in broches_c], 0), "x": _unitaire(np.cross(-ud, o)), "y": -ud, "z": o,
                "titre": "D · guide de réduction, le long des broches" if red is not None else
                "D · après correction : moitiés verrouillées, le long des broches"}
        rv = np.vstack([p_[1] for p_ in apres])
        qd = _projeter(rv, vueD)
        lims["D"] = (qd[:, 0].min() - marge, qd[:, 0].max() + marge, qd[:, 1].min() - marge, qd[:, 1].max() + marge)
    larg = lambda k_: lims[k_][1] - lims[k_][0]
    haut = lambda k_: lims[k_][3] - lims[k_][2]
    # échelle : la plus grande (2:1, 1:1, 1:2) qui fait tenir A, B (et D) côte à côte, C sous A, à gauche du tableau
    zone_l, zone_h = 272.0, 247.0
    for ech in (2.0, 1.0, 0.5):
        rangee1 = (larg("A") + larg("B")) * ech + 6
        rangee2 = (larg("C") + (larg("D") if "D" in lims else 0)) * ech + 6
        if max(rangee1, rangee2) <= zone_l and (haut("A") + haut("C")) * ech + 10 <= zone_h \
                and (haut("B") + (haut("D") if "D" in lims else 0)) * ech + 10 <= zone_h + 60:
            break
    st = pr.get("strategie", {})
    kind = st.get("type_coin", "")
    theta = float(pr["deformite"]["theta_deg"])
    fig, fond = _feuille(titre,
                         f"{'Tibia' if pr.get('os') == 'tibia' else 'Fémur'} · {'coin de fermeture' if kind == 'fermeture' else 'coin d’ouverture'}"
                         f" · θ = {_fr(theta, 1)}° · cotes en mm · échelle {_echelle_txt(ech)} sur A3 · traits mixtes = axes des broches, "
                         "tirets rouges = plans de coupe")
    d_ = info.get("dimensions") or {}
    x0, ytop = 16.0, A3[1] - 34.0
    axA = _axes_vue(fig, x0, ytop - haut("A") * ech, lims["A"], ech)
    axB = _axes_vue(fig, x0 + larg("A") * ech + 6, ytop - haut("B") * ech, lims["B"], ech)
    axC = _axes_vue(fig, x0, ytop - haut("A") * ech - 10 - haut("C") * ech, lims["C"], ech)
    axD = None
    if "D" in lims:
        xD = x0 + larg("C") * ech + 6
        yD = ytop - haut("B") * ech - 10 - haut("D") * ech
        yD = min(yD, ytop - haut("A") * ech - 10 - haut("D") * ech)
        axD = _axes_vue(fig, max(xD, x0 + larg("A") * ech + 6), max(yD, 18.0), lims["D"], ech)
    # os autour du guide (contexte) et pièces
    cen = v_os[f_os].mean(1)
    lo_g, hi_g = tous.min(0) - 12, tous.max(0) + 12
    f_pres = f_os[np.all((cen > lo_g) & (cen < hi_g), axis=1)]
    pcs = [(v_os, f_pres, COULEURS["os"], "fin")] + [(vv, ff, COULEURS[nom], "fort") for nom, vv, ff in pieces]
    pas = 25.4 / (180.0 * ech)          # aplats à ≈ 180 points par pouce sur la feuille, quelle que soit l'échelle
    for ax_, k_ in ((axA, "A"), (axB, "B"), (axC, "C")):
        _dessiner_vue(ax_, pcs, vues[k_], lims[k_], pas=pas)
        ax_.text(lims[k_][0], lims[k_][3], vues[k_]["titre"], fontsize=7.5, color=ENCRE, va="bottom", clip_on=False)
    if axD is not None:
        cen_c = vc[fc].mean(1)
        rv_lo, rv_hi = rv.min(0) - 12, rv.max(0) + 12
        fc_pres = fc[np.all((cen_c > rv_lo) & (cen_c < rv_hi), axis=1)]
        _dessiner_vue(axD, [(vc, fc_pres, COULEURS["os"], "fin")] + [(pv_, pf_, COULEURS[nom], "fort") for nom, pv_, pf_ in apres],
                      vueD, lims["D"], pas=pas)
        axD.text(lims["D"][0], lims["D"][3], vueD["titre"], fontsize=7.5, color=ENCRE, va="bottom", clip_on=False)
    # axes des broches (traits mixtes) et noms
    for x in geo["broches"]:
        o = -_unitaire(x["d"])
        a0, a1 = x["a"] + (x["t_sortie"] - 5) * o, x["a"] + (x["t_haut"] + 5) * o
        for ax_, k_ in ((axA, "A"), (axB, "B"), (axC, "C")):
            p0, p1 = _projeter(np.array([a0, a1]), vues[k_])[:, :2]
            _trait_mixte(ax_, p0, p1)
        pA = _projeter(np.array([x["a"] + x["t_haut"] * o]), vues["A"])[0, :2]
        p_f, n_f = geo["plans"][0] if x["fragment"] == "proximal" else geo["plans"][-1]
        dist = abs(float((x["a"] - p_f) @ _unitaire(n_f)))
        axA.text(pA[0] + 2.4, pA[1] + 2.4, f"{x['nom']} · {_fr(dist)}", fontsize=6.0, color=ENCRE, zorder=11,
                 bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.8))
    # plans de coupe (tirets rouges) dans A et B
    for i, (p, n) in enumerate(geo["plans"]):
        n = _unitaire(n)
        for ax_, k_ in ((axA, "A"), (axB, "B")):
            vue = vues[k_]
            dd = np.cross(n, vue["z"])
            if np.linalg.norm(dd) < 1e-6:
                continue
            dd = _unitaire(dd)
            c0 = _projeter(np.array([p]), vue)[0, :2]
            d2 = _unitaire(np.array([dd @ vue["x"], dd @ vue["y"]]))
            Lr = max(larg(k_), haut(k_))
            ax_.plot([c0[0] - Lr * d2[0], c0[0] + Lr * d2[0]], [c0[1] - Lr * d2[1], c0[1] + Lr * d2[1]], color="#b03030",
                     lw=0.45, ls=(0, (4, 2)), zorder=6)
            ax_.set_xlim(lims[k_][0], lims[k_][1])
            ax_.set_ylim(lims[k_][2], lims[k_][3])
        cA = _projeter(np.array([p]), vues["A"])[0, :2]
        axA.text(lims["A"][1] - 1, cA[1] + 1.0 - 3.0 * i, f"fente {i + 1}", fontsize=6.0, color="#b03030", ha="right", zorder=11,
                 bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.8))
    # cotes A : longueur et largeur hors tout, broches -> fente de séparation
    qA = _projeter(tous, vues["A"])[:, :2]
    loA, hiA = qA.min(0), qA.max(0)
    _cote(axA, (loA[0], loA[1]), (loA[0], hiA[1]), (-5, 0), _fr(hiA[1] - loA[1]))
    _cote(axA, (loA[0], loA[1]), (hiA[0], loA[1]), (0, -5), _fr(hiA[0] - loA[0]))
    # cotes B : hauteur et longueur, angle entre les fentes
    qB = _projeter(tous, vues["B"])[:, :2]
    loB, hiB = qB.min(0), qB.max(0)
    _cote(axB, (loB[0], loB[1]), (hiB[0], loB[1]), (0, -5), _fr(hiB[0] - loB[0]))
    _cote(axB, (hiB[0], loB[1]), (hiB[0], hiB[1]), (5, 0), _fr(hiB[1] - loB[1]))
    if len(geo["plans"]) == 2:
        cH = _projeter(np.array([geo["H"]]), vues["B"])[0, :2]
        axB.text(lims["B"][1] - 1, lims["B"][2] + 1, f"θ entre fentes {_fr(d_.get('angle_entre_fentes_deg') or 0, 1)}°", fontsize=6.0,
                 color="#b03030", zorder=11, ha="right", va="bottom",
                 bbox=dict(boxstyle="square,pad=0.06", fc="white", ec="none", alpha=0.85))
    # cotes C : largeur et hauteur
    qC = _projeter(tous, vues["C"])[:, :2]
    loC, hiC = qC.min(0), qC.max(0)
    _cote(axC, (loC[0], loC[1]), (hiC[0], loC[1]), (0, -5), _fr(hiC[0] - loC[0]))
    _cote(axC, (hiC[0], loC[1]), (hiC[0], hiC[1]), (5, 0), _fr(hiC[1] - loC[1]))
    if axD is not None:
        qD = _projeter(rv, vueD)[:, :2]
        loD, hiD = qD.min(0), qD.max(0)
        _cote(axD, (loD[0], loD[1]), (hiD[0], loD[1]), (0, -5), _fr(hiD[0] - loD[0]))
        _cote(axD, (hiD[0], loD[1]), (hiD[0], hiD[1]), (5, 0), _fr(hiD[1] - loD[1]))
    # tableau des dimensions (à droite)
    lignes = []
    for x in d_.get("fentes", []):
        lignes.append((f"fente {x['fente']}", f"{_fr(x['longueur_mm'])} × {_fr(x['largeur_mm'], 2)} ; tour {_fr(x['hauteur_tour_mm'])} ; "
                       f"lame {_fr(x['profondeur_lame_mm'])} jusqu'à la butée ({x.get('butee', 'charnière')})"))
    if d_:
        n_ponts = d_["ponts"].get("nombre", 2)
        lignes += [
            ("butée", f"profondeur de lame {_fr(d_['butee']['profondeur_lame_mm'], 0)} (gravée ; la même graduation pour toutes "
                      f"les fentes ; minimum {_fr(d_['butee']['minimale_mm'])})") if d_.get("butee") else None,
            ("manchons", f"Ø ext. {_fr(d_['manchon_diametre_exterieur_mm'], 2)}, trou Ø {_fr(d_['trou_broche_mm'], 2)}"),
            ("broches", " ; ".join(f"{b['nom']} à {_fr(b['distance_coupe_mm'])} de la coupe (manchon {_fr(b['hauteur_manchon_mm'])})"
                                   for b in d_.get("broches", []))),
            ("écart broches", " ; ".join(f"{k} {_fr(v)}" for k, v in (d_.get("ecart_broches_mm") or {}).items()) or "1 broche par fragment"),
            ("coque", f"longueur {_fr(d_['coque']['longueur_mm'])} ; e = {_fr(d_['coque']['epaisseur_mm'], 1)} ; j = "
                      f"{_fr(d_['coque']['jeu_mm'], 2)} ; ± {_fr(d_['coque']['secteur_deg'], 0)}°"),
            ("ponts", f"{n_ponts} × {_fr(d_['ponts']['section_mm'][0], 1)} × {_fr(d_['ponts']['section_mm'][1], 1)}"),
            ("guide de coupe", "{} × {} × {} (axe de l'os × largeur × hauteur)".format(
                *(_fr(d_["guide_coupe"][k]) for k in ("longueur_axe_os_mm", "largeur_mm", "hauteur_mm")))),
        ]
        if d_.get("verrou"):
            vr = d_["verrou"]
            lignes.append(("verrou", f"oreilles {', '.join(vr['cotes'])} : Ø {_fr(vr['oreille_diametre_mm'])} × {_fr(vr['oreille_epaisseur_mm'])}, "
                                     f"écart ≤ {_fr(vr['jeu_vertical_mm'])}"
                                     + (f", écartées de ≤ {_fr(vr['decalage_exterieur_mm'])} vers l'extérieur" if vr.get("decalage_exterieur_mm") else "")
                                     + f" ; trou Ø {_fr(vr['trou_mm'], 2)} ; broche guidée sur ≥ {_fr(vr['engagement_mm'])} "
                                     f"(oreille {vr['moitie_haute']} au-dessus)"
                                     + (f" ; détecte une rotation de {_fr(vr['rotation_detectee_deg'], 2)}°" if vr.get("rotation_detectee_deg") else "")))
        lignes = [l_ for l_ in lignes if l_]
        if d_.get("guide_reduction"):
            gr_ = d_["guide_reduction"]
            lignes.append(("guide de réduction", "{} × {} × {} ; {} manchons de {} ; barre à {} de l'os".format(
                *(_fr(gr_[k]) for k in ("longueur_axe_os_mm", "largeur_mm", "hauteur_mm")), gr_["nombre_manchons"],
                _fr(gr_["manchon_longueur_mm"]), _fr(gr_["ecart_os_mm"]))))
    y_t = _tableau(fond, 300, A3[1] - 34, "Dimensions de ce guide (mm)", lignes, ["élément", "valeur"], [24, 82], h_ligne=4.0, taille=5.8)
    notes = [("·", "Distances des broches : depuis le plan de coupe de leur fragment (P : fente 1 ; D : dernière fente).")]
    notes += [(f"{i + 1}.", l_) for i, l_ in enumerate(info.get("protocole") or [])]
    _tableau(fond, 300, y_t - 8, "Notes : mode opératoire", notes, ["", ""], [5, 101], h_ligne=3.7, taille=5.5)
    serie = (pr.get("os_segmente") or {}).get("serie")
    derot = float((pr.get("correction") or {}).get("derotation_deg") or 0)
    vr_ = info.get("verrou_reduction") or {}
    if vr_.get("construit"):
        n_p = (info.get("guide_coupe") or {}).get("pieces_attendues", 2)
        piece = (f"Guide de coupe « 2 en 1 » patient-spécifique ({'3 pièces : P, coin, D' if n_p == 3 else '2 moitiés'}, "
                 f"{2 * (n_p - 1)} ponts sécables) avec verrou de réduction intégré")
    else:
        piece = "Guide de coupe patient-spécifique (2 moitiés, 2 ponts sécables) + guide de réduction"
    profs = [x.get("profondeur") for x in (info.get("guide_coupe") or {}).get("fentes", [])]
    complete = all(p_ == "complete" for p_ in profs) if profs else bool(st.get("osteotomie_complete"))
    lignes_cart = [
        ("Pièce", piece),
        ("Cas", f"{pr.get('os', '')} {pr.get('cote', '')} · {serie or 'os fictif (modèle)'}"),
        ("Correction", f"{'fermeture' if kind == 'fermeture' else 'ouverture'} θ = {_fr(theta, 1)}°"
                       + (f", dérotation {_fr(derot, 1)}°" if abs(derot) >= 1 else "") + f", règle {st.get('regle_paley', 1)} de Paley"),
        ("Stratégie", f"abord {st.get('abord') or ('non usuel' if st.get('abord_non_usuel') else 'n.d.')} ; "
                      f"{'ostéotomie complète' if complete else 'charnière conservée'} ; charnière à "
                      f"{_fr(float(st.get('charniere_profondeur_mm') or 2), 1)} mm ; broches {st.get('configuration_broches', '2+2')}"),
        ("Matériau", "PA12 (frittage laser) ou résine stérilisable ; régler les jeux sur coupons imprimés"),
        ("Échelle", f"{_echelle_txt(ech)} sur A3 · cotes en mm · tolérance d'impression ± 0,1"),
        ("Généré", f"CT-CORA3D étape 7 (dessin_guide.py) · {time.strftime('%d/%m/%Y %H:%M')} · prototype de recherche"),
    ]
    _cartouche(fond, A3[0] - 12 - 190, 16, lignes_cart, ech)
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
    sortis = plan_generique(dossier / "plan_generique", valeurs, defauts, info.get("dimensions"), titre)
    sortis += plan_cote(dossier / "plan_guide", pr, info, v_os, f_os, moities, ponts, red, geo, broches_c, vc, fc,
                        E7.depuis_manifold)
    return sortis
