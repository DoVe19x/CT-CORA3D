"""
figures.py : figures calculées du document « Segmentation osseuse et maillage 3D ».

Usage (depuis ce dossier) : ../../../.venv/bin/python figures.py
Écrit dans images/ :
  profil_bord.pdf      pourquoi un seuil bas place la surface trop à l'extérieur, et comment la demi-hauteur corrige ;
  critere_contact.pdf  le critère c* qui recolle les morceaux d'un même os ;
  sensibilite.pdf      écart des surfaces quand le seuil varie de 50 HU (relu dans ../../exemples/*/rapport.json).
Les deux premières reprennent celles du dossier complet (documents/dossier_complet/figures_maths.py), sans tirets.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from scipy.stats import norm  # noqa: E402

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "images"
EXEMPLES = ICI.parent.parent / "exemples"

AVENIR = Path("/System/Library/Fonts/Avenir Next.ttc")   # police de macOS ; sinon la police par défaut de matplotlib
if AVENIR.exists():
    fm.fontManager.addfont(str(AVENIR))
plt.rcParams.update({
    "font.family": ["Avenir Next", "DejaVu Sans"], "font.size": 8.8, "axes.labelsize": 8.8, "legend.fontsize": 8.0,
    "xtick.labelsize": 8.0, "ytick.labelsize": 8.0, "axes.edgecolor": "#5b6b7a", "axes.spines.top": False,
    "axes.spines.right": False, "savefig.bbox": "tight", "savefig.pad_inches": 0.04, "pdf.fonttype": 42,
})
OS, OS_BORD = "#efe6d2", "#9c8a66"
BLEU, ORANGE, ROUGE, VERT, GRIS = "#1f5f8b", "#b8611a", "#c0392b", "#3a7d2c", "#7f8c8d"
L_PAGE = 6.3                                    # pouces : largeur du texte (16 cm)


def virgule(x, n=2):
    return f"{x:.{n}f}".replace(".", ",")


def sauver(fig, nom):
    SORTIE.mkdir(exist_ok=True)
    fig.savefig(SORTIE / f"{nom}.pdf")
    plt.close(fig)
    print("  ", nom)


def profil_bord():
    """Bord flou d'un os : position de la surface au seuil 226 HU et à la demi-hauteur."""
    B, C = 40.0, 1300.0
    sigma = np.hypot(0.5, 0.35)                 # flou du scanner (fantôme) combiné au lissage du programme
    s = np.linspace(-3, 3, 600)
    I = B + (C - B) * norm.cdf(-s / sigma)
    T = 226.0
    sT = -sigma * norm.ppf((T - B) / (C - B))
    h = 0.5 * (B + C)
    fig, ax = plt.subplots(figsize=(L_PAGE, 2.6))
    ax.axvspan(-3, 0, color=OS, zorder=0)
    ax.text(-2.85, 1180, "dans l'os (corticale)", fontsize=9, color=OS_BORD)
    ax.text(0.15, 1180, "dehors (tissus mous)", fontsize=9, color=GRIS)
    ax.plot(s, I, color=BLEU, lw=2, label="intensité vue par le scanner (bord flou)")
    ax.axhline(T, color=ORANGE, lw=1.2, ls="--")
    ax.text(2.95, T + 25, "seuil 226 HU", color=ORANGE, ha="right", fontsize=9)
    ax.axhline(h, color=VERT, lw=1.2, ls="--")
    ax.text(2.95, h + 25, "demi-hauteur (pic + fond) / 2", color=VERT, ha="right", fontsize=9)
    ax.plot([sT], [T], "o", color=ORANGE, ms=6)
    ax.plot([0], [h], "o", color=VERT, ms=6)
    ax.axvline(0, color="#555555", lw=1)
    ax.annotate("", xy=(sT, 400), xytext=(0, 400), arrowprops=dict(arrowstyle="<->", color=ORANGE, lw=1.2))
    ax.text(sT + 0.08, 400, f"+{virgule(sT)} mm", color=ORANGE, ha="left", va="center", fontsize=9.5)
    ax.text(0.04, 60, "vrai bord", fontsize=9, color="#555555")
    ax.set_xlim(-3, 3)
    ax.set_ylim(0, 1400)
    ax.set_xlabel("position le long de la normale à la surface (mm)")
    ax.set_ylabel("intensité (HU)")
    ax.legend(loc="upper right", bbox_to_anchor=(1, 0.86), frameon=False)
    sauver(fig, "profil_bord")


def critere_contact():
    """Valeurs de c* mesurées sur le lévrier : vraies articulations contre os coupé en deux."""
    cas = [("fabelle collée au fémur", 0.5, VERT, "≈ "), ("hanche (tête du fémur et bassin)", 0.6, VERT, "≈ "),
           ("articulations du tarse", 2.1, VERT, "≤ "), ("même os coupé en deux\n(épiphyse et diaphyse)", 5.0, ROUGE, "≈ ")]
    fig, ax = plt.subplots(figsize=(L_PAGE, 2.1))
    y = np.arange(len(cas))[::-1]
    ax.barh(y, [c[1] for c in cas], color=[c[2] for c in cas], height=0.55, alpha=0.85)
    for yy, (_n, val, _c, signe) in zip(y, cas):
        ax.text(val + 0.08, yy, signe + virgule(val, 1), va="center", fontsize=9)
    ax.set_yticks(y, [c[0] for c in cas])
    ax.axvline(3, color="#333333", ls="--", lw=1.2)
    ax.text(3.05, 3.42, "seuil : recoller si $c^* \\geq 3$", fontsize=9)
    ax.set_xlim(0, 6)
    ax.set_xlabel("$c^* = A_{\\mathrm{contact}} \\,/\\, V_{\\min}^{2/3}$ (sans unité), mesuré sur le lévrier")
    sauver(fig, "critere_contact")


def sensibilite():
    """Écart moyen et 95e centile entre la surface à 226 HU et les surfaces à 176 et 276 HU, os par os."""
    series = {"greyhound_hindlimb_hip_to_knee": "H", "greyhound_hindlimb_knee_to_ankle": "G",
              "greyhound_hindlimb_ankle_down": "P"}
    lignes = []
    for dossier, lettre in series.items():
        f = EXEMPLES / dossier / "rapport.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        for nom, m in r["os"].items():
            s = m.get("sensibilite_seuil")
            if s:
                lignes.append((f"{m['libelle']} ({lettre})", s["moins"]["ecart_absolu_moyen_mm"], s["moins"]["ecart_p95_mm"],
                               s["plus"]["ecart_absolu_moyen_mm"], s["plus"]["ecart_p95_mm"]))
    if not lignes:
        return
    lignes.sort(key=lambda x: -x[2])
    y = np.arange(len(lignes))[::-1]
    fig, ax = plt.subplots(figsize=(L_PAGE, 0.24 * len(lignes) + 0.9))
    ax.barh(y + 0.19, [x[2] for x in lignes], height=0.36, color=ORANGE, alpha=0.35, label="95e centile, 176 HU")
    ax.barh(y + 0.19, [x[1] for x in lignes], height=0.36, color=ORANGE, label="écart moyen, 176 HU")
    ax.barh(y - 0.19, [x[4] for x in lignes], height=0.36, color=BLEU, alpha=0.35, label="95e centile, 276 HU")
    ax.barh(y - 0.19, [x[3] for x in lignes], height=0.36, color=BLEU, label="écart moyen, 276 HU")
    ax.axvline(0.5, color=ROUGE, ls="--", lw=1.2)
    ax.text(0.52, y[0] + 0.45, "objectif 0,5 mm", color=ROUGE, fontsize=8.5)
    ax.set_yticks(y, [x[0] for x in lignes])
    ax.set_xlabel("distance entre la surface à 226 HU et la surface au seuil modifié (mm)")
    ax.legend(loc="lower right", frameon=False, ncol=2)
    sauver(fig, "sensibilite")


if __name__ == "__main__":
    profil_bord()
    critere_contact()
    sensibilite()
