#!/usr/bin/env python3
"""
creer_icone.py — dessine l'icône de CT-CORA3D (coupe de scanner + fémur en 3D + axes et CORA) et l'écrit aux formats
utiles.

Sorties : icone.png (1024 px), icone.icns (macOS, via iconutil), icone.ico (Windows), ../interface/ct/icone.png (256 px).
Usage   : ../../../.venv/bin/python creer_icone.py   (depuis ce dossier)
"""
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon
from PIL import Image

ICI = Path(__file__).resolve().parent
FOND, COUPE, CORTICALE, OS, OMBRE, TRAIT = "#0e1b25", "#2b3a46", "#f2ead8", "#ead9b8", "#c9b48d", "#6db4e6"

fig = plt.figure(figsize=(10.24, 10.24), dpi=100)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")
fig.patch.set_alpha(0)
ax.add_patch(FancyBboxPatch((4, 4), 92, 92, boxstyle="round,pad=0,rounding_size=20", fc=FOND, ec="none"))

# coupe axiale de scanner : cuisse (tissus mous) avec la section du fémur (corticale claire, moelle sombre)
ax.add_patch(Ellipse((36, 38), 50, 42, angle=-12, fc=COUPE, ec="none"))
ax.add_patch(Circle((38, 40), 9.5, fc=CORTICALE, ec="none"))
ax.add_patch(Circle((38, 40), 5.2, fc="#5d6b74", ec="none"))
ax.plot([11, 61], [40, 40], color="#e2574c", lw=3, alpha=0.9)          # réticule (comme dans l'application)
ax.plot([38, 38], [17, 59], color="#e7b44a", lw=3, alpha=0.9)

# fémur en 3D (tête, col, diaphyse, condyles) qui sort de la coupe
ax.add_patch(Polygon([(55, 49), (63, 55), (78, 74), (72, 79)], closed=True, fc=OS, ec="none"))      # diaphyse
ax.add_patch(Circle((78, 80), 6.5, fc=OS, ec="none"))                                              # tête fémorale
ax.add_patch(Ellipse((58, 47), 15, 10, angle=40, fc=OS, ec="none"))                               # condyles
ax.add_patch(Polygon([(59, 54), (63, 55), (78, 74), (76, 75)], closed=True, fc=OMBRE, ec="none"))  # ombre
# maillage (STL) suggéré par quelques arêtes
for a, b in [((66, 62), (71, 68)), ((69, 60), (66, 62)), ((71, 68), (74, 66)), ((69, 60), (74, 66))]:
    ax.plot(*zip(a, b), color=TRAIT, lw=2.2, alpha=0.9)
# méthode CORA : axe du segment proximal, axe du segment distal, et leur intersection (le CORA)
PROX, DIST, CORA = "#9a86ff", "#35c690", "#ff5b61"
ax.plot([86, 70.5], [91, 64], color=PROX, lw=6.5, solid_capstyle="round")
ax.plot([70.5, 50], [64, 47], color=DIST, lw=6.5, solid_capstyle="round")
ax.plot([70.5, 58], [64, 42], color=PROX, lw=3.2, ls=(0, (2, 1.6)), alpha=0.9)
ax.add_patch(Circle((70.5, 64), 4.6, fc=CORA, ec=FOND, lw=2.5))

png = ICI / "icone.png"
fig.savefig(png, dpi=100, transparent=True)
plt.close(fig)

img = Image.open(png).convert("RGBA")
img.resize((256, 256), Image.LANCZOS).save(ICI.parent / "interface" / "ct" / "icone.png")
img.save(ICI / "icone.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
if sys.platform == "darwin":                     # .icns : jeu d'images puis iconutil (outil de macOS)
    jeu = ICI / "icone.iconset"
    jeu.mkdir(exist_ok=True)
    for t in (16, 32, 128, 256, 512):
        img.resize((t, t), Image.LANCZOS).save(jeu / f"icon_{t}x{t}.png")
        img.resize((2 * t, 2 * t), Image.LANCZOS).save(jeu / f"icon_{t}x{t}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(jeu), "-o", str(ICI / "icone.icns")], check=True)
    shutil.rmtree(jeu)
print("icônes écrites dans", ICI)
