"""
rendus_3d.py — rendus 3D soignés des guides pour le dossier complet (couverture, chapitre 11).

Usage : <python du projet> rendus_3d.py        (écrit figures/rendu_*.png, fond transparent)
Données : exemples/_os_fictif/guide_tibia_ouverture/ et guide_tibia_fermeture/ (os fictif, aucune donnée de patient) :
os planifié, fibula, moitiés du guide de coupe, ponts, os corrigé et guide de réduction ; position des broches (avant et
après la correction) lue dans guide.json. Repère de l'os : X latéral, Y proximal, Z caudal (mm).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pyvista as pv

pv.OFF_SCREEN = True
ICI = Path(__file__).resolve().parent
BASE = ICI.parent.parent / "exemples" / "_os_fictif"
CAS = BASE / "guide_tibia_ouverture"
SORTIE = ICI / "figures"

OS = "#efe4cc"
FIBULA = "#e6dcc6"
PROX = "#2f6db5"
DIST = "#2e9a7e"
PONT = "#e08a3c"
METAL = "#a9b1b9"
REDUCTION = "#8a5cc2"


def lire_bin(nom, cas=None):
    b = ((cas or CAS) / nom).read_bytes()
    nv, nf = (int(x) for x in np.frombuffer(b, np.uint32, 2))
    v = np.frombuffer(b, np.float32, nv * 3, 8).reshape(-1, 3).astype(float)
    f = np.frombuffer(b, np.uint32, nf * 3, 8 + nv * 12).reshape(-1, 3).astype(np.int64)
    faces = np.hstack([np.full((len(f), 1), 3), f]).ravel()
    return pv.PolyData(v, faces).clean()


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def broches(g, apres=False):
    """Cylindres des broches (de 4 mm au-delà de la sortie à 22 mm au-dessus du manchon) ; apres : les distales suivent
    le fragment distal (correction réelle de guide.json)."""
    out = []
    T = np.asarray(g["correction_reelle"]["T_4x4"], float)
    for b in g["guide_coupe"]["broches"]:
        e, s, h = (np.asarray(b[k], float) for k in ("entree_os", "sortie_os", "haut_manchon"))
        o = unit(h - e)
        a, z = s - 4 * o, h + 22 * o
        if apres and b["fragment"] == "distal":
            a, z = T[:3, :3] @ a + T[:3, 3], T[:3, :3] @ z + T[:3, 3]
        if apres:                                        # au-dessus du guide de réduction
            z = z + 14 * o if b["fragment"] == "proximal" else z + 14 * unit(T[:3, :3] @ o)
        out.append(pv.Cylinder(center=(a + z) / 2, direction=z - a, radius=0.8, height=float(np.linalg.norm(z - a)),
                               resolution=40))
    return out


def scene(taille, fond=None):
    pl = pv.Plotter(off_screen=True, window_size=taille, lighting="none")
    if fond:
        pl.set_background(fond)
    pl.add_light(pv.Light(position=(1, 1, 1), focal_point=(0, 0, 0), intensity=0.55, light_type="camera light"))
    pl.add_light(pv.Light(position=(-1, 0.5, 0.6), focal_point=(0, 0, 0), intensity=0.35, light_type="camera light"))
    pl.add_light(pv.Light(position=(0, -1, 0.3), focal_point=(0, 0, 0), intensity=0.18, light_type="camera light"))
    pl.add_light(pv.Light(light_type="headlight", intensity=0.25))
    return pl


def ajouter(pl, m, couleur, brillant=0.25, opacite=1.0):
    pl.add_mesh(m, color=couleur, smooth_shading=True, specular=brillant, specular_power=25, ambient=0.18,
                diffuse=0.85, opacity=opacite)


def camera(pl, focal, direction, distance, haut=(0, 1, 0), angle=20):
    pl.camera.focal_point = tuple(focal)
    pl.camera.position = tuple(np.asarray(focal) + distance * unit(direction))
    pl.camera.up = haut
    pl.camera.view_angle = angle


def finir(chemin, fondu=0.12, marge=24):
    """Recadre l'image sur l'os et le guide (marge en pixels) et estompe le haut et le bas, où l'os est coupé par le
    cadre : l'os s'efface doucement au lieu de s'arrêter net."""
    from PIL import Image
    im = np.asarray(Image.open(chemin)).astype(float)
    cols = np.where(im[:, :, 3].max(0) > 8)[0]
    im = im[:, max(cols.min() - marge, 0):min(cols.max() + marge + 1, im.shape[1])]
    h = im.shape[0]
    n = int(fondu * h)
    t = np.linspace(0.0, 1.0, n)
    rampe = np.ones(h)
    rampe[:n] = t * t * (3 - 2 * t)
    rampe[h - n:] = rampe[:n][::-1]
    im[:, :, 3] *= rampe[:, None]
    Image.fromarray(im.round().astype(np.uint8)).save(chemin)


def rendu(nom, pieces, focal, direction, distance, taille=(1400, 2000), angle=20, fondu=True):
    pl = scene(taille)
    for m, c, s in pieces:
        ajouter(pl, m, c, s)
    camera(pl, focal, direction, distance, angle=angle)
    try:
        pl.enable_ssao(radius=6.0, bias=0.4, kernel_size=128, blur=True)     # relief des creux
    except Exception:
        pass
    pl.enable_anti_aliasing("ssaa")
    SORTIE.mkdir(exist_ok=True)
    pl.screenshot(str(SORTIE / f"{nom}.png"), transparent_background=True)
    pl.close()
    if fondu:
        finir(SORTIE / f"{nom}.png")
    print("  ", nom)


def main():
    # coin d'ouverture posé par la face médiale (cas de démonstration de l'application) : couverture et chapitre 11
    g = json.loads((CAS / "guide.json").read_text(encoding="utf-8"))
    pr = json.loads((CAS / "prescription.json").read_text(encoding="utf-8"))
    face = unit(pr["guide"]["face_appui"])
    lateral = unit(np.cross([0, 1, 0], face))
    os_, fib = lire_bin("os_planifie.bin"), lire_bin("voisin_fibula.bin")
    prox, dist, ponts = (lire_bin(f"guide_coupe_{n}.bin") for n in ("proximal", "distal", "ponts"))
    avant = [(os_, OS, 0.12), (fib, FIBULA, 0.1), (prox, PROX, 0.35), (dist, DIST, 0.35), (ponts, PONT, 0.35)] + \
            [(b, METAL, 0.8) for b in broches(g)]
    centre = 0.5 * (np.asarray(prox.center) + np.asarray(dist.center))
    rendu("rendu_couverture", avant, centre + [0, -4, 0], face - 0.55 * lateral + [0, 0.28, 0], 420, (1500, 2200), 19,
          fondu=False)                                   # la couverture : l'os sort par le haut et le bas de la page
    rendu("rendu_face", avant, centre, face + [0, 0.06, 0], 330, (900, 1500), 21)
    rendu("rendu_profil", avant, centre, -lateral + 0.25 * face, 330, (900, 1500), 21)
    # après la correction : os corrigé, broches parallèles, guide de réduction enfilé dessus
    corr, red = lire_bin("os_corrige.bin"), lire_bin("guide_reduction.bin")
    apres = [(corr, OS, 0.12), (red, REDUCTION, 0.35)] + [(b, METAL, 0.8) for b in broches(g, apres=True)]
    rendu("rendu_reduction", apres, np.asarray(red.center), face - 0.4 * lateral + [0, 0.1, 0], 330, (900, 1500), 21)
    # coin de fermeture (deux moitiés ; la partie au-dessus du coin osseux appartient à la moitié distale) ; la fibula,
    # devant le guide dans cette vue, n'est pas dessinée (la légende de la figure le dit)
    cas_f = BASE / "guide_tibia_fermeture"
    g2 = json.loads((cas_f / "guide.json").read_text(encoding="utf-8"))
    pr2 = json.loads((cas_f / "prescription.json").read_text(encoding="utf-8"))
    face2 = unit(pr2["guide"]["face_appui"])
    lat2 = unit(np.cross([0, 1, 0], face2))
    pieces = [(lire_bin("os_planifie.bin", cas_f), OS, 0.12)] + \
             [(lire_bin(f"guide_coupe_{n}.bin", cas_f), c, 0.35)
              for n, c in (("proximal", PROX), ("distal", DIST), ("ponts", PONT))] + \
             [(b, METAL, 0.8) for b in broches(g2)]
    c3 = np.asarray(lire_bin("guide_coupe_ponts.bin", cas_f).center)
    rendu("rendu_fermeture", pieces, c3, face2 + 0.3 * lat2 + [0, 0.1, 0], 330, (900, 1500), 21)


if __name__ == "__main__":
    sys.exit(main())
