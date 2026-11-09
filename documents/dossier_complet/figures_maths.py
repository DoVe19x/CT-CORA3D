"""
figures_maths.py — figures calculées du dossier complet (géométrie, principes mathématiques, résultats).

Usage : <python du projet> figures_maths.py            (écrit les PDF dans figures/)
        <python du projet> figures_maths.py angle_vrai   (une seule figure, par son nom)
Python du projet : ~/Library/Application Support/CTCORA3D/venv/bin/python (numpy, scipy, matplotlib, trimesh).

Les figures « réelles » relisent les os du lévrier dans ../../resultats/ (repère de l'os : X latéral, Y proximal,
Z caudal ; membre gauche mis en miroir) ; les autres sont des constructions géométriques exactes, avec les mêmes
formules que le programme (code_source/). Aucune donnée du patient n'est lue.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.patches import Arc, FancyArrowPatch, Polygon, Rectangle, Wedge, Circle  # noqa: E402
from scipy import ndimage  # noqa: E402
from scipy.spatial import ConvexHull  # noqa: E402
from scipy.stats import norm  # noqa: E402

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "figures"
PROJET = ICI.parent.parent
RES = PROJET / "resultats"

# ------------------------------------------------------------------------------------------- style commun
POLICES = Path.home() / "Library/TinyTeX/texmf-dist/fonts/opentype/public/libertinus-fonts"
for f in ("LibertinusSans-Regular.otf", "LibertinusSans-Bold.otf", "LibertinusSans-Italic.otf",
          "LibertinusSerif-Regular.otf", "LibertinusSerif-Italic.otf", "LibertinusSerif-Semibold.otf"):
    if (POLICES / f).exists():
        fm.fontManager.addfont(str(POLICES / f))
# textes en Avenir Next (la police des titres et des légendes du document, livrée avec macOS), sinon Libertinus Sans ;
# formules en Libertinus (comme le texte du document)
AVENIR = Path("/System/Library/Fonts/Avenir Next.ttc")
if AVENIR.exists():
    fm.fontManager.addfont(str(AVENIR))
plt.rcParams.update({
    "font.family": ["Avenir Next", "Libertinus Sans"], "font.size": 8.8, "axes.titlesize": 9.6,
    "axes.titleweight": "semibold", "axes.labelsize": 8.8, "legend.fontsize": 8.0, "xtick.labelsize": 8.0,
    "ytick.labelsize": 8.0, "axes.edgecolor": "#5b6b7a", "xtick.color": "#3a4652", "ytick.color": "#3a4652",
    "axes.labelcolor": "#2a333c", "text.color": "#1e2832",
    "mathtext.fontset": "custom", "mathtext.rm": "Libertinus Serif", "mathtext.it": "Libertinus Serif:italic",
    "mathtext.bf": "Libertinus Serif:bold", "axes.spines.top": False, "axes.spines.right": False,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.04, "pdf.fonttype": 42,
})
OS, OS_BORD = "#efe6d2", "#9c8a66"
BLEU, ORANGE, ROUGE, VERT, VIOLET, GRIS = "#1f5f8b", "#b8611a", "#c0392b", "#3a7d2c", "#6f4a99", "#7f8c8d"
VERT_CLAIR, BLEU_CLAIR, ORANGE_CLAIR = "#cfe8c6", "#cfe0f1", "#f8dcc0"
L_PAGE = 6.3                                   # pouces : largeur du texte (16 cm)


def sauver(fig, nom):
    SORTIE.mkdir(exist_ok=True)
    fig.savefig(SORTIE / f"{nom}.pdf")
    import os
    if os.environ.get("APERCU"):                      # aperçu PNG facultatif (vérification à l'écran)
        fig.savefig(Path(os.environ["APERCU"]) / f"{nom}.png", dpi=110)
    plt.close(fig)
    print("  ", nom)


def sans_axes(ax):
    ax.set_axis_off()
    ax.set_aspect("equal")


def fleche(ax, a, b, couleur="#333333", lw=1.4, style="-|>", ms=10, **kw):
    kw.setdefault("zorder", 5)
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=ms, color=couleur, lw=lw,
                                 shrinkA=0, shrinkB=0, **kw))


def rot2(v, a):
    c, s = np.cos(a), np.sin(a)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def arc_angle(ax, centre, d1, d2, r, couleur, texte=None, dt=1.25, taille=9.5, fond=False, **kw):
    """Arc de cercle entre les directions d1 et d2 (le plus petit), avec une étiquette."""
    a1, a2 = np.degrees(np.arctan2(d1[1], d1[0])), np.degrees(np.arctan2(d2[1], d2[0]))
    d = (a2 - a1 + 540) % 360 - 180
    t1, t2 = (a1, a1 + d) if d > 0 else (a1 + d, a1)
    ax.add_patch(Arc(centre, 2 * r, 2 * r, theta1=t1, theta2=t2, color=couleur, lw=1.4, zorder=6, **kw))
    if texte:
        am = np.radians(0.5 * (t1 + t2))
        ax.text(centre[0] + dt * r * np.cos(am), centre[1] + dt * r * np.sin(am), texte, color=couleur,
                ha="center", va="center", fontsize=taille, zorder=7,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85) if fond else None)


def lire_bin(chemin):
    b = Path(chemin).read_bytes()
    nv, nf = (int(x) for x in np.frombuffer(b, np.uint32, 2))
    v = np.frombuffer(b, np.float32, nv * 3, 8).reshape(-1, 3).astype(float)
    f = np.frombuffer(b, np.uint32, nf * 3, 8 + nv * 12).reshape(-1, 3).astype(np.int64)
    return v, f


def segments_coupe(v, f, axe, valeur):
    """Segments de l'intersection du maillage avec le plan {p[axe] = valeur} (même principe que trimesh)."""
    d = v[:, axe] - valeur
    out = []
    for tri in f:
        s = d[tri]
        pts = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            if (s[i] >= 0) != (s[j] >= 0):
                t = s[i] / (s[i] - s[j])
                pts.append(v[tri[i]] + t * (v[tri[j]] - v[tri[i]]))
        if len(pts) == 2:
            out.append(pts)
    return np.array(out)


def remplir_coupe(seg, i0, i1, lo, hi, pas):
    """Section remplie (règle pair-impair ligne par ligne, comme Os.section_remplie de etape6_reperes.py)."""
    nx, ny = int(np.ceil((hi[0] - lo[0]) / pas)), int(np.ceil((hi[1] - lo[1]) / pas))
    M = np.zeros((ny, nx), bool)
    a, b = seg[:, 0][:, [i0, i1]], seg[:, 1][:, [i0, i1]]
    for j in range(ny):
        yy = lo[1] + (j + 0.5) * pas
        c = (a[:, 1] > yy) != (b[:, 1] > yy)
        if not c.any():
            continue
        t = (yy - a[c, 1]) / (b[c, 1] - a[c, 1])
        x = np.sort(a[c, 0] + t * (b[c, 0] - a[c, 0]))
        for x0, x1 in zip(x[::2], x[1::2]):
            M[j, max(int((x0 - lo[0]) / pas), 0):max(int((x1 - lo[0]) / pas), 0)] = True
    return M


# ------------------------------------------------------------------------------------------- 1. bord flou
def profil_bord():
    """Pourquoi un seuil bas place la surface trop à l'extérieur, et pourquoi la « demi-hauteur » corrige."""
    B, C = 40.0, 1300.0
    sigma = np.hypot(0.5, 0.35)                       # flou du scanner (fantôme) ⊕ lissage du programme
    s = np.linspace(-3, 3, 600)
    I = B + (C - B) * norm.cdf(-s / sigma)
    T = 226.0
    sT = -sigma * norm.ppf((T - B) / (C - B))
    fig, ax = plt.subplots(figsize=(L_PAGE, 2.6))
    ax.axvspan(-3, 0, color=OS, zorder=0)
    ax.text(-2.85, 1180, "dans l'os (corticale)", fontsize=9, color=OS_BORD)
    ax.text(0.15, 1180, "dehors (tissus mous)", fontsize=9, color=GRIS)
    ax.plot(s, I, color=BLEU, lw=2, label="intensité vue par le scanner (bord flou)")
    ax.axhline(T, color=ORANGE, lw=1.2, ls="--")
    ax.text(2.95, T + 25, "seuil 226 HU", color=ORANGE, ha="right", fontsize=9)
    h = 0.5 * (B + C)
    ax.axhline(h, color=VERT, lw=1.2, ls="--")
    ax.text(2.95, h + 25, "demi-hauteur (pic + fond) / 2", color=VERT, ha="right", fontsize=9)
    ax.plot([sT], [T], "o", color=ORANGE, ms=6)
    ax.plot([0], [h], "o", color=VERT, ms=6)
    ax.axvline(0, color="#555555", lw=1)
    ax.annotate("", xy=(sT, 400), xytext=(0, 400), arrowprops=dict(arrowstyle="<->", color=ORANGE, lw=1.2))
    ax.text(sT + 0.08, 400, f"+{sT:.2f} mm".replace(".", ","), color=ORANGE, ha="left", va="center", fontsize=9.5)
    ax.text(0.04, 60, "vrai bord", fontsize=9, color="#555555")
    ax.set_xlim(-3, 3)
    ax.set_ylim(0, 1400)
    ax.set_xlabel("position le long de la normale à la surface (mm)")
    ax.set_ylabel("intensité (HU)")
    ax.legend(loc="upper right", bbox_to_anchor=(1, 0.86), frameon=False)
    sauver(fig, "profil_bord")


# ------------------------------------------------------------------------------------------- 2. critère c*
def critere_contact():
    cas = [("fabelle collée au fémur", 0.5, VERT), ("hanche (tête du fémur – bassin)", 0.6, VERT),
           ("articulations du tarse", 2.1, VERT), ("même os coupé en deux\n(épiphyse – diaphyse)", 5.0, ROUGE)]
    fig, ax = plt.subplots(figsize=(L_PAGE, 2.1))
    y = np.arange(len(cas))[::-1]
    ax.barh(y, [c[1] for c in cas], color=[c[2] for c in cas], height=0.55, alpha=0.85)
    for yy, (n, val, _c) in zip(y, cas):
        ax.text(val + 0.08, yy, ("≈ " if val == 5.0 else "≤ " if val == 2.1 else "≈ ") + f"{val:.1f}".replace(".", ","),
                va="center", fontsize=9)
    ax.set_yticks(y, [c[0] for c in cas])
    ax.axvline(3, color="#333333", ls="--", lw=1.2)
    ax.text(3.05, 3.42, "seuil : recoller si $c^* \\geq 3$", fontsize=9)
    ax.set_xlim(0, 6)
    ax.set_xlabel("$c^* = A_{\\mathrm{contact}} \\,/\\, V_{\\min}^{2/3}$ (sans unité), mesuré sur le lévrier")
    sauver(fig, "critere_contact")


# ------------------------------------------------------------------------------------------- 3. RANSAC
def ransac_cercle():
    rng = np.random.default_rng(3)
    c0, r0 = np.array([0.0, 0.0]), 12.0
    t = rng.uniform(np.radians(20), np.radians(250), 140)
    arc = np.c_[c0[0] + r0 * np.cos(t), c0[1] + r0 * np.sin(t)] + rng.normal(0, 0.22, (140, 2))
    autres = np.r_[np.c_[rng.uniform(-22, 22, 40), rng.uniform(-22, 22, 40)],
                   np.c_[np.linspace(-20, 5, 30), -16 + 0.2 * np.linspace(-20, 5, 30) + rng.normal(0, 0.3, 30)]]
    P = np.r_[arc, autres]

    def cercle3(q):
        A = np.c_[2 * q, np.ones(3)]
        x = np.linalg.solve(A, (q ** 2).sum(1))
        c = x[:2]
        return c, np.sqrt(x[2] + c @ c)

    tol = 0.6
    meilleur = (0, None)
    essais = []
    for _ in range(600):
        q = P[rng.choice(len(P), 3, replace=False)]
        try:
            c, r = cercle3(q)
        except np.linalg.LinAlgError:
            continue
        if not 4 <= r <= 20:
            continue
        nb = int((np.abs(np.linalg.norm(P - c, axis=1) - r) < tol).sum())
        essais.append((nb, c, r, q))
        if nb > meilleur[0]:
            meilleur = (nb, (c, r))
    c, r = meilleur[1]
    for _ in range(3):
        inl = np.abs(np.linalg.norm(P - c, axis=1) - r) < tol
        q = P[inl]
        x = np.linalg.lstsq(np.c_[2 * q, np.ones(len(q))], (q ** 2).sum(1), rcond=None)[0]
        c, r = x[:2], np.sqrt(x[2] + x[:2] @ x[:2])
    inl = np.abs(np.linalg.norm(P - c, axis=1) - r) < tol
    mauvais = sorted(essais, key=lambda e: e[0])[len(essais) // 4]
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 3.0))
    for ax in axs:
        sans_axes(ax)
        ax.set_xlim(-24, 24)
        ax.set_ylim(-22, 22)
    ax = axs[0]
    ax.plot(P[:, 0], P[:, 1], ".", color=GRIS, ms=3.5)
    nb, cm, rm, q = mauvais
    ax.add_patch(Circle(cm, rm, fill=False, color=ORANGE, lw=1.4))
    ax.plot(q[:, 0], q[:, 1], "o", color=ORANGE, ms=6)
    ax.set_title(f"un essai au hasard :\n{nb} points le soutiennent", fontsize=9.5)
    ax = axs[1]
    th = np.linspace(0, 2 * np.pi, 300)
    for dr, a in ((tol, 0.18),):
        ax.fill(np.r_[(r + dr) * np.cos(th), (r - dr) * np.cos(th[::-1])] + c[0],
                np.r_[(r + dr) * np.sin(th), (r - dr) * np.sin(th[::-1])] + c[1], color=VERT, alpha=a, lw=0)
    ax.add_patch(Circle(c, r, fill=False, color=VERT, lw=1.4))
    ax.plot(P[~inl, 0], P[~inl, 1], ".", color=GRIS, ms=3.5)
    ax.plot(P[inl, 0], P[inl, 1], ".", color=VERT, ms=4.5)
    ax.plot(*c, "+", color=VERT, ms=10, mew=2)
    ax.set_title(f"le meilleur, affiné :\n{int(inl.sum())} points à ± 0,6 mm", fontsize=9.5)
    ax.text(c[0] + 1.2, c[1] - 1.6, f"centre ; r = {r:.1f} mm".replace(".", ","), color=VERT, fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    sauver(fig, "ransac_cercle")


# ------------------------------------------------------------------------------------------- os réels
def dossier_serie(serie, nom_os):
    """Dossier des résultats d'une série pour les figures. Si l'analyse de l'os manque dans la copie de travail (série
    re-segmentée dont l'analyse a échoué, par exemple), les fichiers sont pris dans le dernier commit git et copiés dans
    construction/resultats_git/ (ignoré par git) : les figures restent cohérentes et reproductibles."""
    d = RES / serie
    if (d / f"cora_{nom_os}.json").exists():
        return d
    import subprocess
    cache = ICI / "construction" / "resultats_git" / serie
    cache.mkdir(parents=True, exist_ok=True)
    for nom in (f"cora_{nom_os}.json", f"cora_{nom_os}.bin", f"cora_{nom_os}_fibula.bin", f"{nom_os}.stl"):
        r = subprocess.run(["git", "-C", str(PROJET), "show", f"HEAD:resultats/{serie}/{nom}"], capture_output=True)
        if r.returncode == 0:
            (cache / nom).write_bytes(r.stdout)
    print(f"   ({serie} : analyse du {nom_os} absente de la copie de travail ; version du dernier commit)")
    return cache


def os_reel(nom_serie, nom_os):
    d = dossier_serie(nom_serie, nom_os)
    js = json.loads((d / f"cora_{nom_os}.json").read_text(encoding="utf-8"))
    v, f = lire_bin(d / f"cora_{nom_os}.bin")
    fib = None
    if (d / f"cora_{nom_os}_fibula.bin").exists():
        fib = lire_bin(d / f"cora_{nom_os}_fibula.bin")
    R = {k: np.array(p) for k, p in js["reperes"].items()}
    return js, v, f, R, fib


def droite(ax, p, d, t0, t1, **kw):
    p, d = np.asarray(p), unit(d)
    ax.plot([p[0] + t0 * d[0], p[0] + t1 * d[0]], [p[1] + t0 * d[1], p[1] + t1 * d[1]], **kw)


def intersect2(p, d, q, e):
    den = d[0] * e[1] - d[1] * e[0]
    w = q - p
    s = (w[0] * e[1] - w[1] * e[0]) / den
    return p + s * d


def tangente_commune():
    js, v, f, R, _ = os_reel("greyhound_hindlimb_hip_to_knee", "femur")
    L = js["repere"]["y_haut"] - js["repere"]["y_bas"]
    yb = v[:, 1].min()
    dist = v[:, 1] < yb + 0.12 * L
    xc = 0.5 * (np.percentile(v[dist, 0], 2) + np.percentile(v[dist, 0], 98))
    q = v[dist][:, [0, 1]]
    h = ConvexHull(q)
    med, lat = R["cond_med_dist"], R["cond_lat_dist"]
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 2.9), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axs[0]
    sans_axes(ax)
    sel = v[:, 1] < yb + 0.2 * L
    ax.plot(v[sel, 0][::3], v[sel, 1][::3], ".", color="#c9c2b2", ms=1)
    for s_ in h.simplices:
        ax.plot(q[s_, 0], q[s_, 1], color=BLEU, lw=0.8, alpha=0.6)
    e = lat[:2] - med[:2]
    droite(ax, med[:2], e, -12, np.linalg.norm(e) + 12, color=ROUGE, lw=1.8)
    ax.plot([med[0], lat[0]], [med[1], lat[1]], "o", color=ROUGE, ms=5)
    ax.axvline(xc, color=GRIS, lw=0.8, ls=":")
    x0, x1 = v[sel, 0].min(), v[sel, 0].max()
    ax.annotate("point distal du\ncondyle médial", med[:2], (x0 - 4, med[1] - 9), fontsize=8, ha="center",
                color=ROUGE, arrowprops=dict(arrowstyle="-", color=ROUGE, lw=0.7))
    ax.annotate("point distal du\ncondyle latéral", lat[:2], (x1 + 4, lat[1] - 9), fontsize=8, ha="center",
                color=ROUGE, arrowprops=dict(arrowstyle="-", color=ROUGE, lw=0.7))
    ax.set_xlim(x0 - 14, x1 + 14)
    ax.set_ylim(med[1] - 15, yb + 0.2 * L + 2)
    ax.set_title("vue de face : la « règle » sous les condyles", fontsize=9.5)
    ax = axs[1]
    sans_axes(ax)
    t = np.linspace(-1, 1, 400)
    prof = 3 + 2.2 * np.cos(np.pi * t) ** 2 * (1 + 0.25 * t) - 0.6 * np.cos(3 * np.pi * t)
    xs = 14 * t
    ax.fill_between(xs, prof, 9, color=OS, lw=0)
    ax.plot(xs, prof, color=OS_BORD, lw=1.2)
    pts = np.c_[xs, prof]
    hh = ConvexHull(pts)
    bas = None
    for a_, b_ in hh.simplices:
        if (xs[a_] < -2 and xs[b_] > 2) or (xs[b_] < -2 and xs[a_] > 2):
            ymid = 0.5 * (prof[a_] + prof[b_])
            if bas is None or ymid < bas[2]:
                bas = (a_, b_, ymid)
    a_, b_ = bas[:2]
    ax.plot([xs[a_], xs[b_]], [prof[a_], prof[b_]], color=ROUGE, lw=1.8)
    ax.plot([xs[a_], xs[b_]], [prof[a_], prof[b_]], "o", color=ROUGE, ms=5)
    ax.text(0, -1.0, "la tangente commune touche\nles deux bosses, quelle que\nsoit la forme du creux",
            ha="center", va="top", fontsize=8.5, color=ROUGE)
    ax.set_ylim(-8, 10)
    ax.set_title("principe (profil schématique)", fontsize=9.5)
    sauver(fig, "tangente_commune")


def angles_reels():
    """Angles articulaires mesurés sur les os du lévrier : mêmes définitions que mesurer() (cora_simple.js)."""
    jf, vf, ff, Rf, _ = os_reel("greyhound_hindlimb_hip_to_knee", "femur")
    jt, vt, ft, Rt, fib = os_reel("greyhound_hindlimb_knee_to_ankle", "tibia")
    Af, At = jf["angles"], jt["angles"]
    fig, axs = plt.subplots(1, 4, figsize=(L_PAGE, 4.3))
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.03, top=0.94, wspace=0.08)
    F2 = lambda p: np.array([p[0], p[1]])
    S2 = lambda p: np.array([p[2], p[1]])
    fr = lambda x: f"{x:.1f}".replace(".", ",") + "°"
    # fémur, face
    ax = axs[0]
    sans_axes(ax)
    ax.plot(vf[::7, 0], vf[::7, 1], ".", color="#d5cdbb", ms=0.8)
    a13, a12 = F2(Rf["fem_axe_13"]), F2(Rf["fem_axe_12"])
    dax = unit(a12 - a13)                                    # vers distal
    droite(ax, a13, dax, -95, 165, color=BLEU, lw=1.3)
    hc, gt = F2(Rf["head_center"]), F2(Rf["gt_tip"])
    md, ld = F2(Rf["cond_med_dist"]), F2(Rf["cond_lat_dist"])
    droite(ax, hc, gt - hc, -6, np.linalg.norm(gt - hc) + 8, color=ORANGE, lw=1.3)
    droite(ax, md, ld - md, -8, np.linalg.norm(ld - md) + 8, color=ORANGE, lw=1.3)
    for p in (hc, gt, md, ld):
        ax.plot(*p, "o", color=ROUGE, ms=3)
    X1 = intersect2(hc, unit(gt - hc), a13, dax)
    arc_angle(ax, X1, unit(gt - hc), dax, 13, ROUGE, "aLPFA\n" + fr(Af["aLPFA"]), dt=2.2, taille=8, fond=True)
    X2 = intersect2(md, unit(ld - md), a13, dax)
    arc_angle(ax, X2, unit(ld - md), -dax, 13, ROUGE, "aLDFA\n" + fr(Af["aLDFA"]), dt=2.4, taille=8, fond=True)
    ax.set_title("fémur, face", fontsize=9.5)
    # fémur, profil
    ax = axs[1]
    sans_axes(ax)
    ax.plot(vf[::7, 2], vf[::7, 1], ".", color="#d5cdbb", ms=0.8)
    s13, s12 = S2(Rf["fem_axe_13"]), S2(Rf["fem_axe_12"])
    dsx = unit(s12 - s13)
    droite(ax, s13, dsx, -95, 165, color=BLEU, lw=1.3)
    tr = S2(Rf["troch_dist"])
    cm = 0.5 * (S2(Rf["cond_med_caud"]) + S2(Rf["cond_lat_caud"]))
    droite(ax, tr, cm - tr, -6, np.linalg.norm(cm - tr) + 6, color=ORANGE, lw=1.3)
    ax.plot(*tr, "o", color=ROUGE, ms=3)
    ax.plot(*cm, "o", color=ROUGE, ms=3)
    X3 = intersect2(tr, unit(cm - tr), s13, dsx)
    arc_angle(ax, X3, unit(cm - tr), -dsx, 11, ROUGE, "aCdDFA\n" + fr(Af["aCdDFA"]), dt=2.6, taille=8, fond=True)
    ax.set_title("fémur, profil", fontsize=9.5)
    # tibia, face
    ax = axs[2]
    sans_axes(ax)
    ax.plot(vt[::7, 0], vt[::7, 1], ".", color="#d5cdbb", ms=0.8)
    if fib is not None:
        ax.plot(fib[0][::7, 0], fib[0][::7, 1], ".", color="#e3d7c7", ms=0.8)
    em, dc = F2(Rt["eminence"]), F2(Rt["distal_center"])
    dmec = unit(dc - em)
    droite(ax, em, dmec, -8, np.linalg.norm(dc - em) + 8, color=BLEU, lw=1.3)
    pm, pl = F2(Rt["plat_med"]), F2(Rt["plat_lat"])
    gm, gl = F2(Rt["groove_med"]), F2(Rt["groove_lat"])
    droite(ax, pm, pl - pm, -8, np.linalg.norm(pl - pm) + 8, color=ORANGE, lw=1.3)
    droite(ax, gm, gl - gm, -8, np.linalg.norm(gl - gm) + 8, color=ORANGE, lw=1.3)
    for p in (em, dc, pm, pl, gm, gl):
        ax.plot(*p, "o", color=ROUGE, ms=3)
    X4 = intersect2(pm, unit(pl - pm), em, dmec)
    arc_angle(ax, X4, unit(pm - pl), dmec, 12, ROUGE, "mMPTA\n" + fr(At["mMPTA"]), dt=2.4, taille=8, fond=True)
    X5 = intersect2(gm, unit(gl - gm), em, dmec)
    arc_angle(ax, X5, unit(gm - gl), -dmec, 12, ROUGE, "mMDTA\n" + fr(At["mMDTA"]), dt=2.4, taille=8, fond=True)
    ax.set_title("tibia, face", fontsize=9.5)
    # tibia, profil
    ax = axs[3]
    sans_axes(ax)
    ax.plot(vt[::7, 2], vt[::7, 1], ".", color="#d5cdbb", ms=0.8)
    es, ds_ = S2(Rt["eminence"]), S2(Rt["distal_center"])
    dms = unit(ds_ - es)
    droite(ax, es, dms, -8, np.linalg.norm(ds_ - es) + 8, color=BLEU, lw=1.3)
    pc, pk = S2(Rt["plat_cran"]), S2(Rt["plat_caud"])
    dcr, dca = S2(Rt["dist_cran"]), S2(Rt["dist_caud"])
    droite(ax, pc, pk - pc, -6, np.linalg.norm(pk - pc) + 6, color=ORANGE, lw=1.3)
    droite(ax, dca, dcr - dca, -6, np.linalg.norm(dcr - dca) + 6, color=ORANGE, lw=1.3)
    for p in (es, ds_, pc, pk, dcr, dca):
        ax.plot(*p, "o", color=ROUGE, ms=3)
    X6 = intersect2(pc, unit(pk - pc), es, dms)
    arc_angle(ax, X6, unit(pk - pc), dms, 12, ROUGE, "mCaPTA\n" + fr(At["mCaPTA"]), dt=2.4, taille=8, fond=True)
    X7 = intersect2(dca, unit(dcr - dca), es, dms)
    arc_angle(ax, X7, unit(dcr - dca), -dms, 12, ROUGE, "mCrDTA\n" + fr(At["mCrDTA"]), dt=2.4, taille=8, fond=True)
    ax.set_title("tibia, profil", fontsize=9.5)
    fig.text(0.5, 0.0, "bleu : axe du segment (fémur : axe anatomique ; tibia : axe mécanique) ; orange : lignes "
             "articulaires ; rouge : repères trouvés automatiquement", ha="center", fontsize=8.5)
    sauver(fig, "angles_reels")


def repere_os():
    """Analyse en composantes principales d'un tibia réel : repère du scanner -> repère de l'os."""
    import trimesh
    d = dossier_serie("greyhound_hindlimb_knee_to_ankle", "tibia")
    m = trimesh.load(d / "tibia.stl", process=False)
    v = np.asarray(m.vertices)[::25]
    c = v.mean(0)
    _, s, vt = np.linalg.svd(v - c, full_matrices=False)
    proj = (v - c) @ vt.T
    Ls = np.percentile(proj, 99, axis=0) - np.percentile(proj, 1, axis=0)
    js = json.loads((d / "cora_tibia.json").read_text(encoding="utf-8"))
    vb, _ = lire_bin(d / "cora_tibia.bin")
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 3.6))
    ax = axs[0]
    sans_axes(ax)
    ax.plot(v[:, 0], v[:, 2], ".", color="#d5cdbb", ms=1)
    for k, (col, nom, lon) in enumerate(((ROUGE, "1er axe (le long de l'os)", 0.40), (BLEU, "2e axe", 0.25))):
        e = vt[k][[0, 2]]
        e = e / np.linalg.norm(e)
        if k == 0 and e[1] < 0:
            e = -e
        fleche(ax, c[[0, 2]], c[[0, 2]] + lon * Ls[0] * e if k == 0 else c[[0, 2]] + 30 * e, col, lw=1.8)
        bout = c[[0, 2]] + (lon * Ls[0] + 6) * e if k == 0 else c[[0, 2]] + 36 * e
        ax.text(*bout, nom, color=col, fontsize=8.5, ha="center")
    xs, zs = v[:, 0], v[:, 2]
    ax.set_xlim(xs.min() - 30, xs.max() + 30)
    ax.set_ylim(zs.min() - 12, zs.max() + 30)
    ax.set_title("(a) repère du scanner (vue x, z)", fontsize=9.5)
    ax.text(xs.min() - 28, zs.min() - 10, f"allongement $L_1 / L_2$ = {Ls[0] / Ls[1]:.1f}".replace(".", ","),
            fontsize=8, color=GRIS)
    ax = axs[1]
    sans_axes(ax)
    ax.plot(vb[::25, 0], vb[::25, 1], ".", color="#d5cdbb", ms=1)
    o = np.array([-42.0, 6.0])
    fleche(ax, o, o + np.array([22, 0]), ROUGE, lw=1.6)
    fleche(ax, o, o + np.array([0, 36]), VERT, lw=1.6)
    ax.plot(*o, "o", color="#333333", ms=4)
    ax.text(o[0] + 24, o[1], "X latéral", color=ROUGE, fontsize=8.5, va="center")
    ax.text(o[0], o[1] + 39, "Y proximal", color=VERT, fontsize=8.5, ha="center")
    ax.text(o[0] - 2, o[1] - 9, "Z caudal :\nvers le lecteur", fontsize=8, color=GRIS, ha="left", va="top")
    ax.set_xlim(-70, 40)
    ax.set_title(f"(b) repère de l'os (membre {js['cote']} → miroir)", fontsize=9.5)
    sauver(fig, "repere_os")


# ------------------------------------------------------------------------------------------- 4. CORA 3D

def cav(p, k=0.55, phi=np.radians(35)):
    """Perspective cavalière : x vers la droite, y vers le haut, z fuit à φ avec un facteur k."""
    p = np.atleast_2d(np.asarray(p, float))
    return np.c_[p[:, 0] + k * p[:, 2] * np.cos(phi), p[:, 1] + k * p[:, 2] * np.sin(phi)]


def ligne3(ax, a, b, **kw):
    q = cav([a, b])
    ax.plot(q[:, 0], q[:, 1], **kw)

def perpendiculaire_commune():
    u = np.array([0.0, -1.0, 0.0])
    v = unit([0.30, -1.0, -0.60])
    n = unit(np.cross(u, v))
    Pp = np.array([0.0, 30.0, 0.0])
    delta = 15.0
    Pd = Pp + delta * n
    C = 0.5 * (Pp + Pd)
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 3.2), gridspec_kw={"width_ratios": [1, 1.15]})
    ax = axs[0]
    sans_axes(ax)
    ligne3(ax, Pp - 42 * u, Pp + 62 * u, color=BLEU, lw=2)
    ligne3(ax, Pd - 40 * v, Pd + 62 * v, color=ORANGE, lw=2)
    ligne3(ax, Pp, Pd, color=ROUGE, lw=2)
    for p_, col in ((Pp, BLEU), (Pd, ORANGE), (C, ROUGE)):
        q = cav(p_)[0]
        ax.plot(*q, "o", color=col, ms=5 if col != ROUGE else 6, zorder=5)
    qp, qd, qc = cav(Pp)[0], cav(Pd)[0], cav(C)[0]
    ax.text(qp[0] - 2, qp[1] + 1, "$P_p$", color=BLEU, ha="right", fontsize=10)
    ax.text(qd[0] + 2, qd[1] - 1, "$P_d$", color=ORANGE, ha="left", fontsize=10)
    ax.text(qc[0], qc[1] - 4, "CORA", color=ROUGE, fontsize=9, ha="center", va="top")
    a = cav(Pp + 58 * u)[0]
    ax.text(a[0] - 2, a[1], "axe proximal\n$(\\mathbf{p}, \\mathbf{u})$", color=BLEU, fontsize=8.5, ha="right",
            va="center")
    b = cav(Pd + 60 * v)[0]
    ax.text(b[0] + 2, b[1], "axe distal\n$(\\mathbf{q}, \\mathbf{v})$", color=ORANGE, fontsize=8.5, ha="left",
            va="center")
    ax.set_title("deux axes qui ne se coupent pas", fontsize=9.5)
    ax2 = axs[1]
    sans_axes(ax2)
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, 10)
    txt = ("On cherche $s$ et $t$ qui rendent\n$\\|\\mathbf{p} + s\\,\\mathbf{u} - \\mathbf{q} - t\\,\\mathbf{v}\\|$ "
           "minimale.\n\nLe segment $[P_p\\,P_d]$ est alors perpendiculaire\naux deux axes : c'est la "
           "perpendiculaire\ncommune (en rouge).\n\nCORA = milieu de $[P_p\\,P_d]$ ;\n"
           "$\\delta = \\|P_p - P_d\\|$ dit de combien les axes\n« se ratent » (exagéré ici : 15 mm).")
    ax2.text(0.1, 5, txt, fontsize=9.3, va="center")
    sauver(fig, "perpendiculaire_commune")


def angle_vrai():
    F, S = 15.0, 10.0
    tF, tS = np.tan(np.radians(F)), np.tan(np.radians(S))
    th = np.degrees(np.arctan(np.hypot(tF, tS)))
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 3.3), gridspec_kw={"width_ratios": [1, 1.15]})
    ax = axs[0]
    sans_axes(ax)
    Lb = 60.0
    tFd, tSd = np.tan(np.radians(32)), np.tan(np.radians(26))      # angles agrandis pour la lisibilité
    O = np.array([0.0, 0.0, 0.0])
    Ub = np.array([0.0, -Lb, 0.0])
    Vb = np.array([-Lb * tFd, -Lb, Lb * tSd])
    VF = np.array([Vb[0], -Lb, 0.0])                 # projection sur le plan frontal (x, y)
    VS = np.array([0.0, -Lb, Vb[2]])                 # projection sur le plan sagittal (z, y)
    for a_, b_ in ((Ub, VF), (VF, Vb), (Vb, VS), (VS, Ub)):
        ligne3(ax, a_, b_, color="#b5b5b5", lw=0.8)
    for a_, b_ in ((Vb, VF), (Vb, VS)):
        ligne3(ax, a_, b_, color="#b5b5b5", lw=0.8, ls=":")
    ligne3(ax, O, 1.12 * Ub, color=BLEU, lw=2)
    ligne3(ax, O, Vb, color=ORANGE, lw=2.2)
    ligne3(ax, O, VF, color=ORANGE, lw=1.2, ls="--")
    ligne3(ax, O, VS, color=ORANGE, lw=1.2, ls=(0, (1, 1.5)))
    q = lambda p_: cav(p_)[0]
    ax.text(*(q(1.12 * Ub) + [-2, -1]), "$\\mathbf{u}$ (axe proximal)", color=BLEU, fontsize=8.5, va="top", ha="right")
    ax.text(*(q(Vb) + [-2, -3]), "$\\mathbf{v}$", color=ORANGE, fontsize=10, ha="right")
    o2 = q(O)
    dir2 = lambda p_: unit(q(p_) - o2)
    arc_angle(ax, o2, dir2(Ub), dir2(VF), 17, ORANGE, "$F$", dt=1.3, taille=10)
    arc_angle(ax, o2, dir2(Ub), dir2(VS), 26, ORANGE, "$S$", dt=1.18, taille=10)
    arc_angle(ax, o2, dir2(Ub), dir2(Vb), 36, ROUGE, "$\\theta$", dt=1.12, taille=11)
    ax.text(*(q(VF) + [-2, 1]), "vue de face\n(plan x, y)", fontsize=7.8, color=GRIS, ha="right", va="center")
    ax.text(*(q(VS) + [0, -3]), "vue de profil\n(plan z, y)", fontsize=7.8, color=GRIS, ha="center", va="top")
    ax.set_title("$F$, $S$ : projections ; $\\theta$ : angle vrai", fontsize=9.5)
    ax.text(0.5, -0.02, "(angles agrandis pour la lisibilité)", transform=ax.transAxes, ha="center", va="top",
            fontsize=7.8, color=GRIS)
    ax2 = axs[1]
    Fs = np.linspace(0, 30, 200)
    for Sv, col in ((0, GRIS), (5, "#7fa8cc"), (10, BLEU), (20, VIOLET)):
        tht = np.degrees(np.arctan(np.hypot(np.tan(np.radians(Fs)), np.tan(np.radians(Sv)))))
        ax2.plot(Fs, tht, color=col, lw=1.6, label=f"$S$ = {Sv}°")
        ax2.plot(Fs, Fs + Sv, color=col, lw=0.8, ls="--")
    ax2.plot([F], [th], "o", color=ROUGE, ms=5)
    ax2.annotate(f"$F$ = 15°, $S$ = 10°\n$\\theta$ = {th:.1f}° (et non 25°)".replace(".", ","), (F, th), (16.5, 5.5),
                 fontsize=8.5, color=ROUGE, arrowprops=dict(arrowstyle="->", color=ROUGE, lw=0.8))
    ax2.set_xlabel("composante frontale $F$ (°)")
    ax2.set_ylabel("angle vrai $\\theta$ (°)")
    ax2.legend(frameon=False, loc="upper left", fontsize=8)
    ax2.set_xlim(0, 30)
    ax2.set_ylim(0, 50)
    sauver(fig, "angle_vrai")


# ------------------------------------------------------------------------------------------- 5. ostéotomie
W = 8.0                                     # demi-largeur de l'os du schéma (mm)
THETA = np.radians(20)
U = np.array([0.0, -1.0])                   # axe proximal, vers distal
V = rot2(U, THETA)                          # axe distal (vers distal), tourné de θ


def os_coude(theta=THETA, long_p=70, long_d=70, w=W):
    """Contour d'un os coudé au CORA (origine) : segment proximal vertical, distal selon V."""
    v = rot2(U, theta)
    nv = np.array([-v[1], v[0]])
    off = nv if nv[0] < 0 else -nv                 # normale de v tournée vers la gauche (x < 0)

    def inter(a1, d1, a2, d2):
        return intersect2(np.asarray(a1, float), d1, np.asarray(a2, float), d2)
    # côtés gauche (x < 0) et droit (x > 0) : intersection des bords des deux segments
    gauche = inter([-w, 0], U, w * off, v)
    droite_ = inter([w, 0], U, -w * off, v)
    bas_g, bas_d = w * off + long_d * v, -w * off + long_d * v
    return np.array([[-w, long_p], gauche, bas_g, bas_d, droite_, [w, long_p]])


def couper(poly, p0, n, garder_positif=True):
    """Polygone ∩ demi-plan {(x − p0)·n ≥ 0} (Sutherland–Hodgman)."""
    s = (poly - p0) @ n * (1 if garder_positif else -1)
    out = []
    for i in range(len(poly)):
        a, b, sa, sb = poly[i], poly[(i + 1) % len(poly)], s[i], s[(i + 1) % len(poly)]
        if sa >= 0:
            out.append(a)
        if (sa >= 0) != (sb >= 0):
            out.append(a + sa / (sa - sb) * (b - a))
    return np.array(out)


def rot_autour(p, Q, a):
    return np.array([rot2(x - Q, a) + Q for x in np.atleast_2d(p)])


def dessiner_os(ax, poly, **kw):
    kw.setdefault("fc", OS)
    kw.setdefault("ec", OS_BORD)
    kw.setdefault("lw", 1.1)
    ax.add_patch(Polygon(poly, closed=True, **kw))


def bissectrice_coins():
    """Plan bissecteur, charnière, coins de fermeture et d'ouverture, et leurs bases 2D tan(θ/2) / 2D sin(θ/2)."""
    th = np.radians(25)
    v = rot2(U, th)
    c = unit(U - v)                          # vers le côté convexe
    b = unit(U + v)                          # normale du plan bissecteur
    poly = os_coude(theta=th)
    cvx = W / np.cos(th / 2)
    D = 2 * cvx - 2.0                        # charnière -> corticale d'entrée, le long de la bissectrice
    fig, axs = plt.subplots(1, 3, figsize=(L_PAGE, 3.5), gridspec_kw={"width_ratios": [0.85, 1.2, 1.2]})
    fig.subplots_adjust(wspace=0.04)
    for ax in axs:
        sans_axes(ax)
    # (a) géométrie
    ax = axs[0]
    ax.set_xlim(-25, 26)
    ax.set_ylim(-48, 40)
    dessiner_os(ax, poly)
    droite(ax, [0, 0], -U, -45, 38, color=BLEU, lw=1.3)
    droite(ax, [0, 0], v, -35, 48, color=ORANGE, lw=1.3)
    droite(ax, [0, 0], c, -22, 22, color=VIOLET, lw=1.2, ls="--")
    ax.plot(0, 0, "o", color=ROUGE, ms=5, zorder=5)
    arc_angle(ax, np.zeros(2), U, v, 14, ROUGE, r"$\theta$", dt=1.4)
    ax.text(-1.5, 33, "axe proximal $\\mathbf{u}$", color=BLEU, fontsize=8, ha="right")
    ax.text(13, -45, "axe distal $\\mathbf{v}$", color=ORANGE, fontsize=8)
    ax.text(-24.5, 8, "bissectrice\ntransverse $\\mathbf{c}$", color=VIOLET, fontsize=8)
    ax.text(-24.5, -14, "côté convexe", fontsize=8, color=GRIS)
    ax.text(11, 7, "côté\nconcave", fontsize=8, color=GRIS)
    ax.text(2, 1.5, "CORA", color=ROUGE, fontsize=8)
    ax.set_title("(a) plan de la déformité", fontsize=9.5)
    zoom = dict(xlim=(-19, 17), ylim=(-15, 13))
    # (b) fermeture : charnière sur la corticale concave, 2 plans ⊥ u et ⊥ v passant par elle
    ax = axs[1]
    ax.set(**zoom)
    H = -c * (cvx - 2.0)
    dessiner_os(ax, poly)
    coin_os = couper(couper(poly, H, U, True), H, v, False)
    ax.add_patch(Polygon(coin_os, closed=True, fc="#f5b7b1", ec=ROUGE, lw=1))
    for n_ in (U, v):
        droite(ax, H, np.array([-n_[1], n_[0]]), -30, 30, color=ROUGE, lw=1.1)
    ax.plot(*H, "o", color=ROUGE, ms=5, zorder=5)
    ax.text(H[0] + 0.8, H[1] + 2.2, "charnière $H$", fontsize=8, color=ROUGE)
    E = H + D * c
    nb_ = np.array([-c[1], c[0]])
    base = 2 * D * np.tan(th / 2)
    ax.annotate("", E + 0.5 * base * nb_, E - 0.5 * base * nb_, arrowprops=dict(arrowstyle="<->", lw=1, color="#333333"))
    ax.text(E[0] - 1.5, E[1] - 3.0, "base\n$2D\\tan(\\theta/2)$", fontsize=8.5, ha="right", va="top")
    ax.annotate("", H - 1.2 * nb_, E - 1.2 * nb_ + 0.0, arrowprops=dict(arrowstyle="<->", lw=0.8, color=GRIS))
    ax.text(*(0.5 * (H + E) - 3.2 * nb_), "$D$", fontsize=9, color=GRIS, ha="center", va="center")
    ax.set_title("(b) coin de fermeture", fontsize=9.5)
    ax.text(0.5, -0.02, "2 traits : plans $\\perp\\,\\mathbf{u}$ et $\\perp\\,\\mathbf{v}$ ;\nle coin rouge est retiré", fontsize=8,
            transform=ax.transAxes, ha="center", va="top")
    # (c) ouverture : charnière sur la corticale convexe, 1 plan ⊥ b
    ax = axs[2]
    ax.set(**zoom)
    H2 = c * (cvx - 2.0)
    distal = couper(poly, H2, b, True)
    prox = couper(poly, H2, b, False)
    dist_ouv = rot_autour(distal, H2, -th)
    dessiner_os(ax, distal, fc="none", ec=GRIS, ls="--", lw=0.9)
    dessiner_os(ax, dist_ouv)
    dessiner_os(ax, prox)
    droite(ax, H2, np.array([-b[1], b[0]]), -30, 30, color=ROUGE, lw=1.1)
    ax.plot(*H2, "o", color=ROUGE, ms=5, zorder=5)
    ax.text(H2[0] - 0.5, H2[1] + 2.2, "charnière $H$", fontsize=8, color=ROUGE, ha="right")
    E2 = H2 - D * c
    E2o = rot_autour(E2, H2, -th)[0]
    ax.annotate("", E2, E2o, arrowprops=dict(arrowstyle="<->", lw=1, color="#333333"))
    ax.text(E2[0] + 1.5, E2[1] - 3.0, "ouverture\n$2D\\sin(\\theta/2)$", fontsize=8.5, ha="left", va="top")
    ax.set_title("(c) coin d'ouverture", fontsize=9.5)
    ax.text(0.5, -0.02, "1 trait : plan $\\perp\\,\\mathbf{b}$ (bissecteur) ;\nl'os s'ouvre côté concave", fontsize=8,
            transform=ax.transAxes, ha="center", va="top")
    sauver(fig, "bissectrice_coins")


def regle2():
    """Règle 1 (coupe au CORA) et règle 2 (coupe déplacée : translation à l'ostéotomie), coin d'ouverture."""
    c = unit(U - V)
    b = unit(U + V)
    poly = os_coude(long_d=80)
    cvx = W / np.cos(THETA / 2)
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 3.9))
    for ax, z in zip(axs, (0.0, 22.0)):
        sans_axes(ax)
        ax.set_xlim(-30, 30)
        ax.set_ylim(-78, 40)
        P0 = z * V
        H = P0 + c * (cvx - 2.0)                         # charnière (ouverture : côté convexe)
        if z == 0:
            Q = H
        else:
            I_ = lambda x: rot2(x, -THETA) - x
            lam = (I_(H) @ b) / (I_(c) @ b)
            Q = lam * c
        distal = couper(poly, H, b, True)
        prox = couper(poly, H, b, False)
        apres = rot_autour(distal, Q, -THETA)
        dessiner_os(ax, distal, fc="none", ec=GRIS, ls="--", lw=0.9)
        dessiner_os(ax, prox)
        dessiner_os(ax, apres, fc=BLEU_CLAIR, ec=BLEU)
        droite(ax, [0, 0], -U, -76, 38, color=BLEU, lw=1.0)
        ax.plot(0, 0, "o", color=ROUGE, ms=4.5, zorder=5)
        ax.text(1.8, 2.5, "CORA", color=ROUGE, fontsize=8)
        droite(ax, H, np.array([-b[1], b[0]]), -16, 16, color=ROUGE, lw=1.1)
        droite(ax, [0, 0], c, -2, 26, color=VIOLET, lw=0.8, ls=":")
        ax.plot(*Q, "x", color=VIOLET, ms=7, mew=1.8, zorder=6)
        Hn = rot_autour(H, Q, -THETA)[0]
        tr = np.linalg.norm(Hn - H)
        if z == 0:
            ax.set_title("règle 1 : coupe au CORA", fontsize=9.5)
            pied = "rotation autour de la charnière, sur la\nbissectrice : axes réalignés, sans translation"
        else:
            ax.annotate("", Hn, H, arrowprops=dict(arrowstyle="->", color=VIOLET, lw=1.3))
            ax.set_title(f"règle 2 : coupe {z:.0f} mm plus bas", fontsize=9.5)
            pied = (f"rotation autour de l'ACA (×), toujours sur la\nbissectrice : axes réalignés, mais le fragment\n"
                    f"glisse de {tr:.1f} mm le long de la coupe").replace(".", ",")
            ax.text(Q[0] - 1, Q[1] + 2.5, "ACA", color=VIOLET, fontsize=8, ha="right")
        ax.text(-29, -80, pied, fontsize=8.3, va="top", clip_on=False)
    sauver(fig, "regle2")


def broches():
    """Les broches distales sont forées avec l'inverse de la correction : après la correction, tout est parallèle."""
    c = unit(U - V)
    poly = os_coude()
    cvx = W / np.cos(THETA / 2)
    H = -c * (cvx - 2.0)                                     # fermeture : charnière côté concave
    prox = couper(poly, H, U, False)
    distal = couper(poly, H, V, True)
    d = np.array([-1.0, 0.0])                                # direction des broches proximales
    dd = rot2(d, THETA)                                      # T⁻¹ d : forée avec l'inverse de la correction
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 3.6))
    for k, ax in enumerate(axs):
        sans_axes(ax)
        ax.set_xlim(-30, 34)
        ax.set_ylim(-62, 42)
        corr = k == 1
        dessiner_os(ax, prox)
        dessiner_os(ax, rot_autour(distal, H, -THETA) if corr else distal)
        for y in (22, 34):
            a = np.array([0.0, y])
            ax.plot([a[0] - 14 * d[0], a[0] + 12 * d[0]], [a[1] - 14 * d[1], a[1] + 12 * d[1]], color="#555555",
                    lw=2.2, solid_capstyle="round")
        for e in (22, 34):
            a = e * V
            p1, p2 = a - 14 * dd, a + 12 * dd
            if corr:
                p1, p2 = rot_autour(np.array([p1, p2]), H, -THETA)
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=ORANGE, lw=2.2, solid_capstyle="round")
        ax.set_title("avant la correction" if not corr else "après la correction", fontsize=9.5)
    axs[0].text(-29, -64, "les broches distales (orange) sont forées\navec l'inverse de la correction : elles\n"
                "ne sont pas parallèles aux proximales", fontsize=8.3, va="top", clip_on=False)
    axs[1].text(-29, -64, "les quatre broches sont parallèles\nexactement quand la correction\nest la bonne",
                fontsize=8.3, va="top", clip_on=False)
    sauver(fig, "broches")


# ------------------------------------------------------------------------------------------- 6. guides
def champ_distance():
    """Coupe transverse d'un vrai tibia (et de sa fibula) : distance signée, coque, espace entre les os."""
    from matplotlib.path import Path as MPath
    js, v, f, R, fib = os_reel("greyhound_hindlimb_knee_to_ankle", "tibia")
    yb, yt = v[:, 1].min(), v[:, 1].max()
    y0 = yb + 0.62 * (yt - yb)
    seg = segments_coupe(v, f, 1, y0)
    segf = segments_coupe(fib[0], fib[1], 1, y0) if fib is not None else np.zeros((0, 2, 3))
    pas = 0.06
    allp = np.vstack([seg.reshape(-1, 3), segf.reshape(-1, 3)])
    lo = allp[:, [0, 2]].min(0) - 9
    hi = allp[:, [0, 2]].max(0) + 9
    Mt = remplir_coupe(seg, 0, 2, lo, hi, pas)
    Mf = remplir_coupe(segf, 0, 2, lo, hi, pas) if len(segf) else np.zeros_like(Mt)
    d = np.where(Mt, -ndimage.distance_transform_edt(Mt) * pas, ndimage.distance_transform_edt(~Mt) * pas)
    df = ndimage.distance_transform_edt(~Mf) * pas if Mf.any() else np.full_like(d, 1e3)
    ny, nx = Mt.shape
    X, Z = np.meshgrid(lo[0] + (np.arange(nx) + 0.5) * pas, lo[1] + (np.arange(ny) + 0.5) * pas)
    J, E, A = 0.3, 3.0, np.radians(75)
    ctr = np.array([X[Mt].mean(), Z[Mt].mean()])
    ext = [lo[0], hi[0], hi[1], lo[1]]

    def coque(face):
        ang = np.arctan2(Z - ctr[1], X - ctr[0]) - np.arctan2(face[1], face[0])
        ang = (ang + np.pi) % (2 * np.pi) - np.pi
        return (d >= J) & (d <= J + E) & (np.abs(ang) <= A) & (df >= 1.0)

    pts_t = np.c_[X[Mt], Z[Mt]]
    pts_u = np.r_[pts_t, np.c_[X[Mf], Z[Mf]]]
    ht, hu = ConvexHull(pts_t), ConvexHull(pts_u)
    grille = np.c_[X.ravel(), Z.ravel()]
    dans_t = MPath(pts_t[ht.vertices]).contains_points(grille).reshape(X.shape)
    dans_u = MPath(pts_u[hu.vertices]).contains_points(grille).reshape(X.shape)
    entre = dans_u & ~dans_t & ~Mf
    fig, axs = plt.subplots(1, 3, figsize=(L_PAGE, 2.9))
    for ax in axs:
        sans_axes(ax)
        ax.set_xlim(lo[0], hi[0])
        ax.set_ylim(hi[1], lo[1])                       # crânial (z petit) en haut, caudal en bas
    ax = axs[0]
    im = ax.imshow(np.clip(d, -10, 10), extent=ext, cmap="RdBu_r", vmin=-10, vmax=10, interpolation="bilinear")
    ax.contour(X, Z, d, [0], colors="k", linewidths=1)
    ax.contour(X, Z, d, [J, J + E], colors=[VERT, VERT], linewidths=[0.8, 0.8], linestyles=["-", "--"])
    ax.set_title("distance signée $d$ (mm)", fontsize=9)
    cax = ax.inset_axes([1.02, 0.15, 0.05, 0.7])
    cb = fig.colorbar(im, cax=cax)
    cb.ax.tick_params(labelsize=6.5)
    for ax, face, titre in ((axs[1], np.array([-1.0, 0.0]), "coque posée côté médial"),
                            (axs[2], np.array([1.0, -0.25]), "coque posée côté latéral")):
        ax.contourf(X, Z, Mt.astype(float), [0.5, 1.5], colors=[OS])
        ax.contour(X, Z, Mt.astype(float), [0.5], colors=[OS_BORD], linewidths=0.8)
        if Mf.any():
            ax.contourf(X, Z, Mf.astype(float), [0.5, 1.5], colors=["#e3d7c7"])
            ax.contour(X, Z, Mf.astype(float), [0.5], colors=[OS_BORD], linewidths=0.8)
            fz = np.array([X[Mf].mean(), Z[Mf].mean()])
            ax.text(fz[0], fz[1] + 3.2, "fibula", fontsize=7, ha="center", va="top", color=OS_BORD)
        k_ = coque(face)
        if titre.endswith("latéral"):
            ax.contourf(X, Z, entre.astype(float), [0.5, 1.5], colors=["none"], hatches=["////"])
            ax.contour(X, Z, entre.astype(float), [0.5], colors=[ROUGE], linewidths=0.7)
            k_ &= ~entre
        ax.contourf(X, Z, k_.astype(float), [0.5, 1.5], colors=[VERT_CLAIR])
        ax.contour(X, Z, k_.astype(float), [0.5], colors=[VERT], linewidths=0.8)
        ax.set_title(titre, fontsize=9)
        ax.text(ctr[0], ctr[1], "tibia", fontsize=7.5, ha="center", va="center", color=OS_BORD)
    axs[1].text(lo[0] + 0.5, lo[1] + 0.5, "crânial ↑   médial ←", fontsize=7, color=GRIS, va="top")
    axs[2].text(0.5, -0.03, "hachures : espace entre les os,\ninterdit au guide", fontsize=7.5, color=ROUGE,
                va="top", ha="center", transform=axs[2].transAxes)
    axs[1].text(0.5, -0.03, "jeu 0,3 mm, épaisseur 3 mm,\n± 75° autour de la face d'appui", fontsize=7.5,
                color=VERT, va="top", ha="center", transform=axs[1].transAxes)
    axs[0].text(0.5, -0.03, "noir : surface de l'os ($d$ = 0)\nvert : $d$ = 0,3 et $d$ = 3,3 mm", fontsize=7.5,
                va="top", ha="center", transform=axs[0].transAxes)
    sauver(fig, "champ_distance")


def union_lisse():
    x = np.linspace(-14, 14, 700)
    X, Y = np.meshgrid(x, x * 0.75)
    a = np.hypot(X + 4, Y) - 6.5                                            # disque
    qx, qy = np.abs(X - 5) - 5, np.abs(Y + 1) - 2.2                          # pavé
    b = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0)

    def smin(a, b, k):
        h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
        return b + (a - b) * h - k * h * (1 - h)
    fig, axs = plt.subplots(1, 3, figsize=(L_PAGE, 2.1))
    for ax, F, t in ((axs[0], np.minimum(a, b), "union nette : $\\min(a, b)$"),
                     (axs[1], smin(a, b, 2.0), "union lisse : $\\mathrm{smin}(a, b, k)$")):
        sans_axes(ax)
        ax.contourf(X, Y, F, [-100, 0], colors=[VERT_CLAIR])
        ax.contour(X, Y, F, [0], colors=[VERT], linewidths=1.2)
        ax.contour(X, Y, a, [0], colors=[GRIS], linewidths=0.6, linestyles=":")
        ax.contour(X, Y, b, [0], colors=[GRIS], linewidths=0.6, linestyles=":")
        ax.set_title(t, fontsize=9)
    ax = axs[2]
    t = np.linspace(-4, 4, 300)
    ax.plot(t, np.minimum(t, 0 * t), color=GRIS, lw=1.2, label="$\\min(a, 0)$")
    ax.plot(t, smin(t, 0 * t, 2.0), color=VERT, lw=1.6, label="$\\mathrm{smin}(a, 0, k = 2)$")
    ax.axvspan(-2, 2, color=VERT, alpha=0.08)
    ax.set_xlabel("$a$ (avec $b = 0$)", fontsize=8.5)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax.set_title("le raccord se fait sur $|a - b| < k$", fontsize=9)
    sauver(fig, "union_lisse")


def depouille():
    """Contre-dépouille : un guide qui embrasse l'os au-delà de sa silhouette ne peut pas être posé."""
    R0, J, E = 10.0, 0.6, 3.0
    alpha = np.radians(8)
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 3.0))
    for k, ax in enumerate(axs):
        sans_axes(ax)
        ax.set_xlim(-20, 20)
        ax.set_ylim(-15, 19)
        ax.add_patch(Circle((0, 0), R0, fc=OS, ec=OS_BORD, lw=1.1))
        fleche(ax, (16.5, 9), (16.5, 17), "#333333", lw=1.3)
        ax.text(15.8, 13, "pose\n(et retrait)", ha="right", fontsize=8)
        demi = np.radians(115)
        a = np.linspace(np.pi / 2 - demi, np.pi / 2 + demi, 300)
        if k == 1:
            a = a[np.sin(a) >= 0]
        r1, r2 = R0 + J, R0 + J + E
        xs = np.r_[r1 * np.cos(a), r2 * np.cos(a[::-1])]
        ys = np.r_[r1 * np.sin(a), r2 * np.sin(a[::-1])]
        ax.add_patch(Polygon(np.c_[xs, ys], closed=True, fc=VERT_CLAIR if k else "#f5b7b1",
                             ec=VERT if k else ROUGE, lw=1))
        if k == 0:
            ax.annotate("", (-11.6, -4.6), (-16.0, -11.5), arrowprops=dict(arrowstyle="->", color=ROUGE, lw=1.1))
            ax.annotate("", (11.6, -4.6), (16.0, -11.5), arrowprops=dict(arrowstyle="->", color=ROUGE, lw=1.1))
            ax.text(-19.5, -15.5, "ces parties passent sous l'os : le guide\naccroche, on ne peut ni le poser ni le retirer",
                    fontsize=8, color=ROUGE, va="top", clip_on=False)
            ax.set_title("(a) avec contre-dépouille", fontsize=9.5)
        else:
            for s_ in (-1, 1):
                x0 = s_ * (R0 + J)
                ax.plot([x0, x0 + s_ * 12 * np.tan(alpha)], [0, -12], color=GRIS, lw=0.9, ls="--")
            ax.plot([-(R0 + J) - 2, R0 + J + 2], [0, 0], color=GRIS, lw=0.6, ls=":")
            ax.text(-19.5, -15.5, "la matière reste au-dessus de la silhouette de l'os\n(+ le jeu), prolongée par un "
                    "cône de dépouille\n(tirets) : pose et retrait libres", fontsize=8, color=VERT, va="top",
                    clip_on=False)
            ax.set_title("(b) sans contre-dépouille", fontsize=9.5)
    sauver(fig, "depouille")


def profondeur_lame():
    """Profondeur de lame : du haut de la tour (os + j + e + g) à l'arrêt de la lame (charnière, ou corticale opposée)."""
    fig, axs = plt.subplots(1, 2, figsize=(L_PAGE, 3.4))
    for k, ax in enumerate(axs):
        sans_axes(ax)
        ax.set_xlim(-17, 17)
        ax.set_ylim(-14, 30)
        ax.add_patch(matplotlib.patches.Ellipse((0, 0), 22, 18, fc=OS, ec=OS_BORD, lw=1.1))
        ax.add_patch(matplotlib.patches.Ellipse((0, 0), 12, 9, fc="#f8f3e8", ec=OS_BORD, lw=0.6))
        hmax, J, E, G = 9.0, 0.3, 3.0, 10.0
        ax.add_patch(Rectangle((-11, hmax + J), 22, E, fc=VERT_CLAIR, ec=VERT, lw=0.9))
        stop = -9.0 + 2.0 if k == 0 else -9.0
        top = hmax + J + E + G
        D = top - stop
        ax.add_patch(Rectangle((-3.4, hmax + J + E - 0.01), 6.8, top - (hmax + J + E), fc=VERT_CLAIR, ec=VERT, lw=0.9))
        ax.add_patch(Rectangle((-0.4, stop), 0.8, top - stop + 2, fc="#555555", ec="none", alpha=0.85))
        ax.plot([-6, 6], [top, top], color=VERT, lw=1)
        ax.plot(0, stop, "o", color=ROUGE, ms=5, zorder=5)
        ax.annotate("", (8.5, top), (8.5, stop), arrowprops=dict(arrowstyle="<->", color="#333333", lw=1))
        ax.text(9.2, 0.5 * (top + stop), f"$D$ = {D:.1f} mm".replace(".", ","), fontsize=9, va="center")
        ax.annotate("", (-7.5, top), (-7.5, hmax + J + E), arrowprops=dict(arrowstyle="<->", color=GRIS, lw=0.8))
        ax.text(-8.2, 0.5 * (top + hmax + J + E), "guidage\ng", fontsize=8, va="center", ha="right", color=GRIS)
        ax.text(1.2, top + 1.3, "haut de la tour : os + j + e + g", fontsize=7.8)
        if k == 0:
            ax.text(1.0, stop - 3.0, "arrêt : la charnière", fontsize=8, color=ROUGE)
            ax.set_title("(a) la lame s'arrête à la charnière", fontsize=9.5)
        else:
            ax.text(1.0, stop - 2.4, "arrêt : la corticale opposée\n(la lame la traverse)", fontsize=8, color=ROUGE,
                    va="top")
            ax.set_title("(b) coupe complète", fontsize=9.5)
    sauver(fig, "profondeur_lame")


def torsion():
    fig, ax = plt.subplots(figsize=(3.2, 2.6))
    sans_axes(ax)
    ax.set_xlim(-11, 11)
    ax.set_ylim(-8, 9)
    a = np.radians(12)
    b = np.radians(12 + 31)
    for ang, col, nom in ((a, BLEU, "axe transverse distal\n(ligne condylaire caudale)"),
                          (b, ORANGE, "axe transverse proximal\n(axe du col)")):
        d = np.array([np.cos(ang), np.sin(ang)])
        ax.plot([-9 * d[0], 9 * d[0]], [-9 * d[1], 9 * d[1]], color=col, lw=1.8)
        ax.text(9.3 * d[0], 9.3 * d[1] - (0.2 if col == BLEU else -0.5), nom, color=col, fontsize=7.5,
                ha="left" if d[0] > 0 else "right", va="center")
    arc_angle(ax, np.zeros(2), np.array([np.cos(a), np.sin(a)]), np.array([np.cos(b), np.sin(b)]), 5, ROUGE,
              r"$\tau$", dt=1.3)
    ax.plot(0, 0, "o", color="#333333", ms=4)
    ax.text(0.4, -1.1, "axe long (vers le lecteur)", fontsize=7.5)
    sauver(fig, "torsion")


FIGURES = {f.__name__: f for f in (profil_bord, critere_contact, ransac_cercle, tangente_commune, angles_reels,
                                   repere_os, perpendiculaire_commune, angle_vrai, bissectrice_coins, regle2, broches,
                                   champ_distance, union_lisse, depouille, profondeur_lame, torsion)}

if __name__ == "__main__":
    noms = sys.argv[1:] or list(FIGURES)
    print("figures :")
    for n in noms:
        FIGURES[n]()
