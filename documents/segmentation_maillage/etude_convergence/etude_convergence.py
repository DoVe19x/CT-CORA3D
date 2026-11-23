"""
etude_convergence.py : étude de convergence du maillage éléments finis du tibia du lévrier, « comme dans Abaqus ».

Le modèle :
  géométrie   tibia.stl de la série genou et cheville (étape 4 du projet), placé dans ses axes principaux :
              x le long de l'os, vers le genou ; longueur 247 mm ;
  matériau    élastique linéaire, homogène et isotrope : E = 17 GPa, ν = 0,3 (os cortical). Le STL est rempli
              (canal médullaire compris) : les contraintes servent à comparer les maillages, pas à juger l'os ;
  appuis      encastrement de tous les nœuds à moins de 10 mm de l'extrémité distale (cheville) ;
  charge      F = (-300, 30, 0) N, soit 300 N de compression le long de l'os et 30 N de flexion, répartis comme une
              charge volumique uniforme dans les 15 derniers millimètres du côté du genou ;
  résultat    contrainte de von Mises aux nœuds (moyennée entre éléments, comme l'affichage d'Abaqus) :
              maximum au milieu de la diaphyse (40 à 60 % de la longueur), et maximum sur tout l'os.

Les maillages (famille) :
  tetgen          C3D4, C3D10 : tétraèdres (surface remaillée puis TetGen), taille h ;
  balaye          C3D8, C3D20 : hexaèdres balayés le long de l'os (grille en « O » qui suit le contour de chaque
                  section, comme un maillage « sweep » d'Abaqus), taille h ;
                  pour C3D10 et C3D20, les nœuds milieux des arêtes de surface sont sur la surface courbe de l'os,
                  comme Abaqus les place sur la géométrie ;
  *_droites       les mêmes avec des nœuds milieux au milieu d'arêtes droites (comparaison) ;
  voxels          C3D8, C3D20 : hexaèdres « voxels » de côté h (surface en escalier) : contre-exemple.
Usage :
  python etude_convergence.py               tous les maillages (≈ 30 à 60 min ; reprend où il s'était arrêté)
  python etude_convergence.py --inp         écrit aussi un fichier Abaqus .inp par maillage (dossier abaqus/)
  python etude_convergence.py --figures     refait seulement les figures depuis resultats/convergence.csv
Sorties : resultats/convergence.csv, ../images/libre_*.pdf (étude avec maillages libres ; l'étude principale,
          à géométrie figée, est etude_geometrie_figee.py)
"""
import argparse
import csv
import time
from pathlib import Path

import numpy as np

import ef
import maillages as M

ICI = Path(__file__).resolve().parent
STL = ICI.parent.parent.parent / "exemples" / "greyhound_hindlimb_knee_to_ankle" / "tibia.stl"
CSV = ICI / "resultats" / "convergence.csv"
IMAGES = ICI.parent / "images"

E, NU = 17000.0, 0.3
FORCE = np.array([-300.0, 30.0, 0.0])           # N
ENCASTREMENT_MM, CHARGE_MM = 10.0, 15.0
TRANCHE = (0.40, 0.60)                           # milieu de la diaphyse (fraction de la longueur, depuis la cheville)
SERIES = [                                       # (élément, famille de maillage, tailles h en mm)
    ("C3D4", "tetgen", [6, 4, 3, 2.5, 2, 1.6, 1.3, 1.1, 0.95, 0.8]),
    ("C3D10", "tetgen", [6, 4, 3, 2.5, 2, 1.6, 1.4, 1.25]),
    ("C3D8", "balaye", [4, 3, 2.5, 2, 1.6, 1.3, 1.1, 0.9, 0.75]),
    ("C3D20", "balaye", [4, 3, 2.5, 2, 1.6, 1.4, 1.25]),
    ("C3D10", "tetgen_droites", [6, 4, 3, 2.5, 2, 1.6, 1.4, 1.25]),
    ("C3D20", "balaye_droites", [4, 3, 2.5, 2, 1.6, 1.4, 1.25]),
    ("C3D8", "voxels", [4, 3, 2.5, 2, 1.6, 1.3, 1.1, 0.95, 0.8, 0.7]),
    ("C3D20", "voxels", [4, 3, 2.5, 2, 1.6, 1.3, 1.15, 1.05]),
]
CHAMPS = ["element", "maillage", "h_mm", "noeuds", "elements", "ddl", "volume_cm3", "sigma_milieu_MPa", "sigma_max_MPa",
          "u_max_mm", "reaction_N", "temps_s", "solveur"]


def calculer(surface, nom, famille, h, ecrire_inp=False):
    t0 = time.time()
    base = "C3D4" if nom in ("C3D4", "C3D10") else "C3D8"
    if famille == "balaye":
        X, conn = M.balaye(surface, h, quadratique=(nom == "C3D20"))      # nœuds milieux sur la surface courbe
    elif famille == "tetgen" and nom == "C3D10":
        X, conn = M.tetra10_courbes(surface, *M.tetraedres(surface, h))   # idem (projetés sur le STL)
    else:                                                                 # sommets seuls, ou arêtes droites
        f = {"tetgen": M.tetraedres, "balaye": M.balaye, "voxels": M.voxels}[famille.replace("_droites", "")]
        X, conn = M.maillage(nom, *f(surface, h))
    x0, x1 = surface.bounds[0], surface.bounds[1]
    L = x1 - x0
    sommets = conn[:, :4] if base == "C3D4" else conn[:, :8]
    centre = X[sommets].mean(1)
    fixes = np.nonzero(X[:, 0] < x0 + ENCASTREMENT_MM)[0]
    charge = np.nonzero(centre[:, 0] > x1 - CHARGE_MM)[0]
    D = ef.elasticite(E, NU)
    _, _, vol = ef.assembler(X, conn[charge], nom, D)                 # volume de la zone chargée
    b = FORCE / vol.sum()                                              # N/mm³ : la résultante vaut F
    K, f, vol_tout = ef.assembler(X, conn, nom, D, b, charge)
    u, info = ef.resoudre(K, f, X, fixes)
    reaction = (K @ u - f).reshape(-1, 3)[fixes].sum(0)
    vm = ef.von_mises(ef.contraintes_noeuds(X, conn, nom, D, u))
    t = (X[:, 0] - x0) / L
    milieu = (t >= TRANCHE[0]) & (t <= TRANCHE[1])
    if ecrire_inp:
        (ICI / "abaqus").mkdir(exist_ok=True)
        el_milieu = np.nonzero(((centre[:, 0] - x0) / L >= TRANCHE[0]) & ((centre[:, 0] - x0) / L <= TRANCHE[1]))[0]
        ef.ecrire_inp(ICI / "abaqus" / f"tibia_{nom}_{famille}_h{str(h).replace('.', 'p')}.inp",
                      X, conn, nom, E, NU, fixes, charge, b, el_milieu,
                      f"Tibia du levrier, {nom} ({famille}), h = {h} mm, {len(X)} noeuds (CT-CORA3D, etude de convergence)")
    return {"element": nom, "maillage": famille, "h_mm": h, "noeuds": len(X), "elements": len(conn), "ddl": info["ddl"],
            "volume_cm3": round(vol_tout.sum() / 1000, 3), "sigma_milieu_MPa": round(float(vm[milieu].max()), 4),
            "sigma_max_MPa": round(float(vm.max()), 3), "u_max_mm": round(float(np.abs(u).reshape(-1, 3).max(0).max()), 5),
            "reaction_N": round(float(np.linalg.norm(reaction)), 3), "temps_s": round(time.time() - t0, 1),
            "solveur": info["solveur"]}


def lire_csv():
    if not CSV.exists():
        return []
    with open(CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def etude(types, ecrire_inp, max_ddl):
    surface = M.lire_os(STL)
    print(f"tibia : longueur {surface.bounds[1] - surface.bounds[0]:.1f} mm, volume {surface.volume / 1000:.1f} cm³")
    faits = {(r["element"], r["maillage"], float(r["h_mm"])) for r in lire_csv()}
    CSV.parent.mkdir(exist_ok=True)
    nouveau = not CSV.exists()
    with open(CSV, "a", newline="", encoding="utf-8") as fichier:
        w = csv.DictWriter(fichier, fieldnames=CHAMPS)
        if nouveau:
            w.writeheader()
        for nom, famille, tailles in SERIES:
            if nom not in types:
                continue
            for h in tailles:
                if (nom, famille, float(h)) in faits:
                    continue
                try:
                    r = calculer(surface, nom, famille, h, ecrire_inp)
                except Exception as exc:                  # un maillage raté n'arrête pas l'étude
                    print(f"  {nom} {famille} h = {h} : échec ({exc})", flush=True)
                    continue
                w.writerow(r)
                fichier.flush()
                print(f"  {nom:6s} {famille:7s} h = {h:5.2f} mm  {r['noeuds']:7d} nœuds  {r['ddl']:8d} ddl  "
                      f"σ milieu = {r['sigma_milieu_MPa']:7.3f} MPa  σ max = {r['sigma_max_MPa']:8.2f} MPa  "
                      f"réaction {r['reaction_N']:.1f} N  {r['temps_s']:6.1f} s  ({r['solveur']})", flush=True)
                if r["ddl"] > max_ddl:
                    break


# =============================================================================== figures
COULEURS = {"C3D4": "#c0392b", "C3D10": "#1f5f8b", "C3D8": "#b8611a", "C3D20": "#3a7d2c"}
LEGENDES = {"C3D4": "C3D4 : tétraèdre linéaire", "C3D10": "C3D10 : tétraèdre quadratique",
            "C3D8": "C3D8 : hexaèdre linéaire", "C3D20": "C3D20 : hexaèdre quadratique"}
PRINCIPALES = (("C3D4", "tetgen"), ("C3D10", "tetgen"), ("C3D8", "balaye"), ("C3D20", "balaye"))


def series_csv():
    """{(élément, famille): [(nœuds, σ milieu, σ max, h)]} triées par nombre de nœuds."""
    series = {}
    for r in lire_csv():
        series.setdefault((r["element"], r["maillage"]), []).append(
            (int(r["noeuds"]), float(r["sigma_milieu_MPa"]), float(r["sigma_max_MPa"]), float(r["h_mm"])))
    for v in series.values():
        v.sort()
    return series


def reference(series):
    """Valeur de référence : maillage le plus fin en C3D20 balayé (le plus précis de l'étude)."""
    return series[("C3D20", "balaye")][-1][1] if ("C3D20", "balaye") in series else None


def figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    avenir = Path("/System/Library/Fonts/Avenir Next.ttc")
    if avenir.exists():
        fm.fontManager.addfont(str(avenir))
    plt.rcParams.update({"font.family": ["Avenir Next", "DejaVu Sans"], "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.bbox": "tight", "pdf.fonttype": 42})
    series = series_csv()
    ref = reference(series)
    IMAGES.mkdir(exist_ok=True)
    virgule = lambda x, n=1: f"{x:.{n}f}".replace(".", ",")

    def finir(fig, ax, nom, ylabel, legende="lower right"):
        ax.set_xscale("log")
        ax.set_xlabel("nombre de nœuds")
        ax.set_ylabel(ylabel)
        ax.grid(True, which="both", color="#e5e5e5", lw=0.6)
        ax.legend(frameon=False, loc=legende, fontsize=8)
        fig.savefig(IMAGES / f"{nom}.pdf")
        fig.savefig(ICI / "resultats" / f"{nom}.png", dpi=150)
        plt.close(fig)
        print("  figure", nom)

    def bande(ax):
        if ref:
            ax.axhline(ref, color="#555555", ls=":", lw=1)
            ax.axhspan(ref * 0.98, ref * 1.02, color="#999999", alpha=0.15, lw=0)

    # 1. la courbe de convergence : contrainte au milieu de la diaphyse en fonction du nombre de nœuds
    fig, ax = plt.subplots(figsize=(6.3, 3.9))
    bande(ax)
    for el, fam in PRINCIPALES:
        if (el, fam) in series:
            v = series[(el, fam)]
            ax.plot([p[0] for p in v], [p[1] for p in v], "o-", color=COULEURS[el], label=LEGENDES[el], ms=4.5, lw=1.6)
    if ref:
        ax.text(0.60, 0.50, f"référence : {virgule(ref, 2)} MPa (C3D20 le plus fin)\nbande grise : ± 2 %",
                transform=ax.transAxes, fontsize=8, color="#555555", va="top")
    finir(fig, ax, "libre_milieu", "σ von Mises max au milieu de la diaphyse (MPa)")

    # 2. erreur relative par rapport à la référence
    if ref:
        fig, ax = plt.subplots(figsize=(6.3, 3.4))
        for el, fam in PRINCIPALES:
            if (el, fam) in series:
                v = series[(el, fam)][:-1] if (el, fam) == ("C3D20", "balaye") else series[(el, fam)]
                ax.plot([p[0] for p in v], [100 * abs(p[1] / ref - 1) for p in v], "o-", color=COULEURS[el],
                        label=LEGENDES[el], ms=4.5, lw=1.6)
        ax.axhline(2, color="#555555", ls="--", lw=1)
        ax.text(0.99, 2.15, "2 %", transform=ax.get_yaxis_transform(), ha="right", fontsize=8, color="#555555")
        ax.set_yscale("log")
        finir(fig, ax, "libre_erreur", "écart à la référence (%)", "lower left")

    # 3. maximum sur tout l'os : ne converge pas (singularité au bord de l'encastrement)
    fig, ax = plt.subplots(figsize=(6.3, 3.4))
    for el, fam in PRINCIPALES:
        if (el, fam) in series:
            v = series[(el, fam)]
            ax.plot([p[0] for p in v], [p[2] for p in v], "o-", color=COULEURS[el], label=LEGENDES[el], ms=4.5, lw=1.6)
    finir(fig, ax, "libre_max", "σ von Mises max sur tout l'os (MPa)", "upper left")

    # 4. hexaèdres : maillage balayé (épouse la surface) contre voxels (surface en escalier)
    fig, ax = plt.subplots(figsize=(6.3, 3.6))
    bande(ax)
    for el in ("C3D8", "C3D20"):
        for fam, style, txt in (("balaye", "o-", "balayé"), ("voxels", "s--", "voxels")):
            if (el, fam) in series:
                v = series[(el, fam)]
                ax.plot([p[0] for p in v], [p[1] for p in v], style, color=COULEURS[el], ms=4.2, lw=1.5,
                        label=f"{el} {txt}", alpha=1 if fam == "balaye" else 0.75)
    finir(fig, ax, "libre_voxels", "σ von Mises max au milieu de la diaphyse (MPa)", "upper right")

    # 5. éléments quadratiques : nœuds milieux sur la surface courbe (Abaqus) ou au milieu d'arêtes droites
    fig, ax = plt.subplots(figsize=(6.3, 3.6))
    bande(ax)
    for el, fam in (("C3D10", "tetgen"), ("C3D20", "balaye")):
        for f2, style, txt in ((fam, "o-", "nœuds milieux sur la surface"), (fam + "_droites", "s--", "arêtes droites")):
            if (el, f2) in series:
                v = series[(el, f2)]
                ax.plot([p[0] for p in v], [p[1] for p in v], style, color=COULEURS[el], ms=4.2, lw=1.5,
                        label=f"{el}, {txt}", alpha=1 if f2 == fam else 0.75)
    finir(fig, ax, "libre_courbes", "σ von Mises max au milieu de la diaphyse (MPa)", "upper right")


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    a.add_argument("--types", nargs="+", default=["C3D4", "C3D10", "C3D8", "C3D20"])
    a.add_argument("--inp", action="store_true", help="écrire les fichiers Abaqus (.inp)")
    a.add_argument("--max-ddl", type=int, default=1_000_000, help="arrêter une série au-delà de ce nombre de ddl")
    a.add_argument("--figures", action="store_true", help="refaire seulement les figures")
    x = a.parse_args()
    if not x.figures:
        etude(x.types, x.inp, x.max_ddl)
    figures()
