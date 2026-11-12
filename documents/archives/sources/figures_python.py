"""
figures_python.py — schémas et graphes du projet tracés avec matplotlib (PNG, 300 ppp).

  methode_cora               principe de la méthode CORA (os stylisé, géométrie calculée)
  coins_fermeture_ouverture  coin de fermeture et coin d'ouverture, avant et après
  segmentation_principe      la segmentation sur une vraie coupe CT du genou du lévrier
  precision                  précision mesurée, objectif du projet et résultats publiés
  campagne_guides            erreurs trouvées puis corrigées pendant la première campagne de guides

Usage : python figures_python.py <dossier CT-CORA3D> <dossier figures>
        (Python du projet : numpy, scipy, matplotlib, trimesh ; la segmentation relit une série DICOM)
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Polygon, Rectangle  # noqa: E402

PROJET = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../..")
FIG = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("../figures")
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "Arial", "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
                     "savefig.dpi": 300, "axes.spines.top": False, "axes.spines.right": False})
OS, BORD, BLEU, ORANGE, ROUGE, VERT, GRIS, OCRE = "#efe4cf", "#9c8b6e", "#1f5f8b", "#b8611a", "#c0392b", "#3a7d2c", "#777777", "#c08a00"
LARGEUR = 6.7          # pouces : largeur du texte d'une page A4


def sauver(fig, nom):
    fig.savefig(FIG / f"{nom}.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(nom)


# ------------------------------------------------------------------------------------------------ géométrie 2D
def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def rot(a):
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


def tourner(P, centre, angle):
    return (np.asarray(P) - centre) @ rot(angle).T + centre


def couper(poly, p0, n, garder_positif=True):
    """Partie d'un polygone du côté (x − p0)·n ≥ 0 (ou ≤ 0) : découpe exacte par un demi-plan."""
    s = 1.0 if garder_positif else -1.0
    out, P = [], list(map(np.asarray, poly))
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        da, db = s * (a - p0) @ n, s * (b - p0) @ n
        if da >= 0:
            out.append(a)
        if (da >= 0) != (db >= 0):
            out.append(a + da / (da - db) * (b - a))
    return np.array(out)


def os_coude(theta_deg, L=100.0, w=16.0, n=50):
    """Os stylisé vu de face : segment du haut vertical, segment du bas tourné de θ autour de l'apex (origine)."""
    th = np.radians(theta_deg)
    u = np.array([0.0, -1.0])                       # direction du segment du haut, vers le bas
    v = rot(th) @ u                                 # direction du segment du bas
    def demi_largeur(s):                            # extrémités plus larges (épiphyses)
        return w / 2 * (1 + 0.7 * np.exp(-(s / 22) ** 2) + 0.55 * np.exp(-((2 * L - s) / 20) ** 2))
    g, d = [], []
    n1 = np.array([-1.0, 0.0])
    n2 = unit(rot(np.pi / 2) @ v)
    n2 = n2 if n2 @ n1 > 0 else -n2
    for k in range(n + 1):
        s = L * k / n
        c = -u * L + u * s
        nr = n1 if k < n else unit(n1 + n2) / np.cos(th / 2)
        g.append(c + nr * demi_largeur(s))
        d.append(c - nr * demi_largeur(s))
    for k in range(1, n + 1):
        c = v * (L * k / n)
        g.append(c + n2 * demi_largeur(L + L * k / n))
        d.append(c - n2 * demi_largeur(L + L * k / n))
    return np.array(g + d[::-1]), u, v, th


def poly(ax, P, **kw):
    ax.add_patch(Polygon(P, closed=True, fc=kw.pop("fc", OS), ec=kw.pop("ec", BORD), lw=kw.pop("lw", 1.0), **kw))


def cadre(ax, xlim, ylim):
    ax.set_aspect("equal")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")


# ------------------------------------------------------------------------------------------------ méthode CORA
def methode_cora():
    TH = 22.0
    P, u, v, th = os_coude(TH)
    c = unit(u - v)                                  # côté convexe
    fig, axs = plt.subplots(1, 2, figsize=(LARGEUR, 3.9))
    ax = axs[0]
    poly(ax, P)
    ax.plot([0, 0], [100, -70], color=BLEU, lw=1.8)
    fin = v * 100
    debut = -v * 70
    ax.plot([debut[0], fin[0]], [debut[1], fin[1]], color=ORANGE, lw=1.8)
    ax.add_patch(Arc((0, 0), 46, 46, theta1=-90, theta2=-90 + TH, color=ROUGE, lw=1.5))
    ax.text(*(unit(u + v) * 31 + np.array([2, -2])), "θ", color=ROUGE, fontsize=13, fontweight="bold")
    ax.add_patch(Circle((0, 0), 2.6, color=ROUGE, zorder=5))
    ax.annotate("CORA : les deux axes\nse croisent ici", xy=(0, 0), xytext=(24, 20), fontsize=8.5, color=ROUGE,
                arrowprops=dict(arrowstyle="-", color=ROUGE, lw=0.7))
    ax.text(24, 80, "axe du\nsegment du haut", color=BLEU, fontsize=8.5, va="center")
    ax.text(40, -58, "axe du\nsegment du bas", color=ORANGE, fontsize=8.5, va="center")
    ax.text(-62, -116, "θ : angle de la déformité", color=ROUGE, fontsize=8.5)
    cadre(ax, (-65, 85), (-128, 108))
    ax.set_title("a) L'os déformé", loc="left")

    ax = axs[1]
    H = -c * 6.0                                     # charnière : côté concave, au niveau du CORA
    haut = couper(P, H, u, garder_positif=False)
    bas = couper(P, H, v, garder_positif=True)
    ax.add_patch(Polygon(P, closed=True, fill=False, ec="#c9bfa9", lw=0.9, ls="--"))
    poly(ax, haut)
    poly(ax, tourner(bas, H, -th))
    ax.plot([0, 0], [100, -100], color=BLEU, lw=1.6)
    ax.add_patch(Circle(H, 2.2, color=ROUGE, zorder=5))
    ax.annotate("on coupe au CORA\net on redresse autour\nde ce point (charnière)", xy=H, xytext=(14, 18), fontsize=8.5,
                color=ROUGE, arrowprops=dict(arrowstyle="-", color=ROUGE, lw=0.7))
    ax.text(-62, -112, "les deux axes sont de nouveau alignés ;\npointillés : l'os avant la correction", fontsize=8.5,
            va="top")
    cadre(ax, (-65, 85), (-128, 108))
    ax.set_title("b) Après la correction", loc="left")
    fig.tight_layout()
    sauver(fig, "methode_cora")


# ------------------------------------------------------------------------------------------------ coins
def coins_fermeture_ouverture():
    TH = 20.0
    P, u, v, th = os_coude(TH, L=70, w=20)
    c = unit(u - v)
    b = unit(u + v)
    fig, axs = plt.subplots(2, 2, figsize=(5.4, 6.6))

    def guide(ax, x, y, gauche):
        ax.add_patch(Rectangle((x, y), 6, 30, fc="#2e6db4", ec="none", alpha=0.85))
        ax.text(x - 3 if gauche else x + 9, y + 34, "guide", color="#2e6db4", fontsize=8.5, ha="right" if gauche else "left")

    def scie(ax, depart, arrivee, gauche):
        ax.add_patch(FancyArrowPatch(depart, arrivee, arrowstyle="-|>", mutation_scale=10, color=ROUGE, lw=1.6))
        ax.text(depart[0], depart[1] + 4, "scie", color=ROUGE, fontsize=8.5, ha="left" if gauche else "right")

    # fermeture : charnière côté concave, le coin est retiré côté convexe
    H = -c * 8.0
    haut, bas = couper(P, H, u, False), couper(P, H, v, True)
    coin = couper(couper(P, H, u, True), H, v, False)
    ax = axs[0, 0]
    poly(ax, haut)
    poly(ax, bas)
    poly(ax, coin, fc="#f4b6b6", ec=ROUGE, hatch="///")
    ax.add_patch(Circle(H, 2.0, color=ROUGE, zorder=5))
    ax.annotate("charnière", xy=H, xytext=(10, 10), fontsize=8.5, color=ROUGE,
                arrowprops=dict(arrowstyle="-", color=ROUGE, lw=0.7))
    ax.annotate("coin d'os\nretiré", xy=coin.mean(axis=0), xytext=(-58, -40), fontsize=8.5, color=ROUGE,
                arrowprops=dict(arrowstyle="-", color=ROUGE, lw=0.7))
    guide(ax, -27, -15, True)
    scie(ax, (-56, 2), (-17, 2), True)
    cadre(ax, (-60, 60), (-95, 75))
    ax.set_title("Fermeture : avant", loc="left")
    ax = axs[1, 0]
    poly(ax, haut)
    poly(ax, tourner(bas, H, -th))
    ax.text(-58, -80, "deux traits de scie ; l'os est\ndroit et un peu plus court", fontsize=8.5, va="top")
    cadre(ax, (-60, 60), (-95, 75))
    ax.set_title("Fermeture : après", loc="left")

    # ouverture : charnière côté convexe, un seul trait, l'os s'ouvre côté concave
    H = c * 8.0
    haut, bas = couper(P, H, b, False), couper(P, H, b, True)
    ax = axs[0, 1]
    poly(ax, haut)
    poly(ax, bas)
    ax.add_patch(Circle(H, 2.0, color=ROUGE, zorder=5))
    ax.annotate("charnière", xy=H, xytext=(-46, 14), fontsize=8.5, color=ROUGE,
                arrowprops=dict(arrowstyle="-", color=ROUGE, lw=0.7))
    guide(ax, 21, -13, False)
    scie(ax, (56, 4), (17, 4), False)
    cadre(ax, (-60, 60), (-95, 75))
    ax.set_title("Ouverture : avant", loc="left")
    ax = axs[1, 1]
    poly(ax, haut)
    poly(ax, tourner(bas, H, -th))
    ax.text(-58, -80, "un seul trait ; l'os s'ouvre,\nil est droit et un peu plus long", fontsize=8.5, va="top")
    cadre(ax, (-60, 60), (-95, 75))
    ax.set_title("Ouverture : après", loc="left")
    fig.suptitle("La scie entre toujours du côté opposé à la charnière,\nc'est là que se pose le guide", fontsize=10,
                 fontweight="bold")
    fig.tight_layout()
    sauver(fig, "coins_fermeture_ouverture")


# ------------------------------------------------------------------------------------------------ segmentation
def segmentation_principe():
    """Les quatre temps de la segmentation, refaits en 2D sur une coupe sagittale du genou (le programme travaille en 3D)."""
    from scipy import ndimage as ndi
    from scipy.spatial import cKDTree
    import trimesh
    sys.path.insert(0, str(PROJET / "code_source"))
    import etape1_lecture_dicom as E1
    import parametres as Pm
    vol = E1.charger(E1.trouver(E1.inventaire(Pm.DOSSIER_DICOM, progression=None), "hip_to_knee"), journal=lambda *a: None)
    res = PROJET / "resultats" / "greyhound_hindlimb_hip_to_knee"
    fem, tib = trimesh.load(res / "femur.stl").vertices, trimesh.load(res / "tibia.stl").vertices
    dist, idx = cKDTree(tib).query(fem)
    genou = (fem[np.argmin(dist)] + tib[idx[np.argmin(dist)]]) / 2          # là où le fémur et le tibia se touchent
    k, _, i = [int(round(x)) for x in np.linalg.solve(vol.affine[:3, :3], genou - vol.affine[:3, 3])[::-1]]
    hu = vol.hu
    sl = hu[max(0, k - 105):k + 105, :, i].astype(float)
    lab, n = ndi.label(sl > 300)
    gros = np.isin(lab, [j + 1 for j, a in enumerate(ndi.sum(sl > 300, lab, range(1, n + 1))) if a > 400])
    r, cc = np.nonzero(gros)
    sl = ndi.gaussian_filter(sl[max(0, r.min() - 25):r.max() + 25, max(0, cc.min() - 35):cc.max() + 35], 0.7)
    masque = sl >= 226
    graines, ng = ndi.label(sl >= 650)
    tailles = ndi.sum(sl >= 650, graines, range(1, ng + 1))
    marques = np.zeros(sl.shape, np.int16)
    for m, j in enumerate([j + 1 for j, a in enumerate(tailles) if a > 60], 1):
        marques[graines == j] = m
    marques[~ndi.binary_dilation(masque, iterations=2)] = -1
    ws = ndi.watershed_ift(np.clip(2000 - sl, 0, 4000).astype(np.uint16), marques)
    ws[~masque] = 0
    asp = float(np.linalg.norm(vol.affine[:3, 2]) / np.linalg.norm(vol.affine[:3, 1]))
    h, w = sl.shape
    fig, axs = plt.subplots(1, 4, figsize=(LARGEUR, LARGEUR / 4 * h * asp / w + 0.8))
    couleurs = {1: (0.12, 0.47, 0.71), 2: (0.17, 0.63, 0.17), 3: (1.0, 0.5, 0.05), 4: (0.84, 0.15, 0.16)}
    for ax in axs:
        ax.imshow(np.clip(sl, -200, 1600)[::-1], cmap="gray", aspect=asp)
        ax.axis("off")
    axs[1].imshow(np.ma.masked_where(~masque[::-1], masque[::-1]), cmap="autumn", alpha=0.55, aspect=asp)
    for ax, etiq in ((axs[2], marques), (axs[3], ws)):
        rgb = np.zeros(sl.shape + (4,))
        for m, coul in couleurs.items():
            rgb[etiq == m] = (*coul, 0.75)
        ax.imshow(rgb[::-1], aspect=asp)
    for ax, t in zip(axs, ("1. Image du scanner", "2. Seuil à 226 HU :\nles os se touchent", "3. Seuil plus haut :\nun noyau par os",
                           "4. Chaque os grandit\njusqu'à l'articulation")):
        ax.set_title(t, fontsize=8.5)
    fig.tight_layout()
    sauver(fig, "segmentation_principe")


# ------------------------------------------------------------------------------------------------ résultats
def precision():
    # mesures du projet : tests du 19/10/2026 ; objectif : document de cadrage (5/10/2026) ;
    # publiés : Jeon et al. 2023 (tibia, plan frontal), De Armond et al. 2022 (seuil d'acceptation)
    lignes = [
        ("Notre calcul de la déformité\n(cas simulés)", 0.0065, VERT, "0,007°  (trop petit pour se voir)"),
        ("Repères trouvés automatiquement\n(os modèle, angles de face)", 1.3, VERT, "1,3°"),
        ("Objectif fixé pour le projet", 2.0, OCRE, "2°"),
        ("Publié avec des guides imprimés\n(tibia, Jeon 2023)", 2.3, GRIS, "2,3°"),
        ("Limite jugée acceptable\n(De Armond 2022)", 5.0, GRIS, "5°"),
    ]
    fig, ax = plt.subplots(figsize=(LARGEUR, 2.9))
    y = np.arange(len(lignes))
    ax.barh(y, [l[1] for l in lignes], color=[l[2] for l in lignes], height=0.6)
    for k, l in enumerate(lignes):
        ax.text(l[1] + 0.08, k, l[3], va="center", fontsize=8.5)
    ax.set_yticks(y, [l[0] for l in lignes])
    ax.invert_yaxis()
    ax.set_xlim(0, 6.5)
    ax.set_xlabel("erreur d'angle (degrés)")
    ax.set_title("L'erreur du calcul est négligeable devant celle d'une opération réelle", loc="left")
    fig.tight_layout()
    sauver(fig, "precision")


def campagne_guides():
    # première campagne de simulation des guides (14/10/2026) : cas en erreur par type, avant les corrections
    lignes = [("guide, broche ou trait de scie\ndans le cartilage", 329), ("guide de coupe contre\nun autre os (fibula…)", 287),
              ("os voisin ou broche\nsur le trajet de la scie", 259), ("guide de réduction mal placé", 129),
              ("broche trop près du bout de l'os", 121)]
    fig, ax = plt.subplots(figsize=(LARGEUR, 2.8))
    y = np.arange(len(lignes))
    ax.barh(y, [l[1] for l in lignes], color=ROUGE, alpha=0.8, height=0.6, label="avant les corrections")
    for k, l in enumerate(lignes):
        ax.text(l[1] + 5, k, f"{l[1]} cas  →  0 après", va="center", fontsize=8.5)
    ax.set_yticks(y, [l[0] for l in lignes])
    ax.invert_yaxis()
    ax.set_xlim(0, 450)
    ax.set_xlabel("nombre de cas en erreur (sur 480 cas simulés)")
    ax.set_title("Première campagne : 46 cas sur 480 sans erreur avant, 640 sur 640 après", loc="left")
    fig.tight_layout()
    sauver(fig, "campagne_guides")


if __name__ == "__main__":
    quoi = sys.argv[3:] or ["methode_cora", "coins_fermeture_ouverture", "segmentation_principe", "precision",
                            "campagne_guides"]
    for q in quoi:
        globals()[q]()
