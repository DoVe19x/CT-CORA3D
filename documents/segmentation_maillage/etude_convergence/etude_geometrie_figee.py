"""
etude_geometrie_figee.py : étude de convergence « classique », comme dans Abaqus : la géométrie est figée, seul le
maillage change.

La géométrie : un tibia simplifié, construit une fois pour toutes à partir de tibia.stl : 21 sections à 16 côtés
(une tous les 12 mm), reliées par des faces planes ou presque (c'est le maillage balayé de base, 640 hexaèdres,
861 nœuds, 75,2 cm³). On ne cherche plus à suivre l'os de plus en plus près : la « pièce » est celle-ci.

Le maillage : chaque hexaèdre de base est coupé en k × k × k hexaèdres (k = 1, 2, 3...), placés par
l'interpolation de l'élément de base : la forme reste exactement la même. Les tétraèdres sont tirés des mêmes
hexaèdres (12 par hexaèdre, maillage conforme). Les quatre éléments sont donc calculés sur la même géométrie, et le
résultat ne dépend plus que de la finesse du maillage : il monte (ou descend) puis atteint un plateau.

Même modèle que etude_convergence.py : E = 17 GPa, ν = 0,3, encastrement à la cheville, F = (-300, 30, 0) N côté
genou ; résultat : contrainte de von Mises maximale aux nœuds au milieu de la diaphyse (40 à 60 % de la longueur).
Contrôle de la force : la série C3D8 est refaite avec F / 2 et 2 F (élasticité linéaire : σ proportionnelle à F).

Usage :
  python etude_geometrie_figee.py              toutes les séries (≈ 15 min ; reprend où il s'était arrêté)
  python etude_geometrie_figee.py --inp        écrit aussi un .inp Abaqus par maillage (abaqus/tibia_figee_*.inp)
  python etude_geometrie_figee.py --figures    figures seules
Sorties : resultats/convergence_figee.csv, ../images/figee_*.pdf
"""
import argparse
import csv
import time
from pathlib import Path

import numpy as np

import ef
import etude_convergence as C
import maillages as M

ICI = Path(__file__).resolve().parent
CSV = ICI / "resultats" / "convergence_figee.csv"
IMAGES = ICI.parent / "images"
BASE = (4, 1, 20)               # grille en « O » : 4 × 4 au centre, 1 couronne de 16, 20 tranches
SERIES = [("C3D8", 1.0, range(1, 9)), ("C3D20", 1.0, range(1, 6)), ("C3D4", 1.0, range(1, 6)),
          ("C3D10", 1.0, range(1, 4)), ("C3D8", 0.5, range(1, 7)), ("C3D8", 2.0, range(1, 7))]
CHAMPS = ["element", "k", "facteur_force", "force_N", "noeuds", "elements", "ddl", "volume_cm3", "sigma_milieu_MPa",
          "sigma_max_MPa", "u_max_mm", "reaction_N", "temps_s", "solveur"]
_BASE = {}


def maillage_k(surface, nom, k):
    """Maillage de l'élément `nom` au niveau de raffinement k, sur la géométrie figée."""
    if "base" not in _BASE:
        _BASE["base"] = M.balaye(surface, divisions=BASE)
    X, conn = M.subdiviser_hexa(*_BASE["base"], k)
    if nom in ("C3D4", "C3D10"):
        X, conn = M.hexa_vers_tetra12(X, conn)
    if nom in ("C3D10", "C3D20"):
        X, conn = ef.quadratique(X, conn, nom)             # nœuds milieux au milieu des arêtes : géométrie inchangée
    return X, conn


def calculer(surface, nom, k, facteur=1.0, ecrire_inp=False):
    t0 = time.time()
    X, conn = maillage_k(surface, nom, k)
    x0, x1 = surface.bounds[0], surface.bounds[1]
    L = x1 - x0
    sommets = conn[:, :4] if nom in ("C3D4", "C3D10") else conn[:, :8]
    centre = X[sommets].mean(1)
    fixes = np.nonzero(X[:, 0] < x0 + C.ENCASTREMENT_MM)[0]
    charge = np.nonzero(centre[:, 0] > x1 - C.CHARGE_MM)[0]
    D = ef.elasticite(C.E, C.NU)
    F = facteur * C.FORCE
    _, _, vol = ef.assembler(X, conn[charge], nom, D)
    b = F / vol.sum()
    K, f, vol_tout = ef.assembler(X, conn, nom, D, b, charge)
    u, info = ef.resoudre(K, f, X, fixes)
    reaction = (K @ u - f).reshape(-1, 3)[fixes].sum(0)
    vm = ef.von_mises(ef.contraintes_noeuds(X, conn, nom, D, u))
    t = (X[:, 0] - x0) / L
    milieu = (t >= C.TRANCHE[0]) & (t <= C.TRANCHE[1])
    if ecrire_inp and facteur == 1.0:
        (ICI / "abaqus").mkdir(exist_ok=True)
        tc = (centre[:, 0] - x0) / L
        ef.ecrire_inp(ICI / "abaqus" / f"tibia_figee_{nom}_k{k}.inp", X, conn, nom, C.E, C.NU, fixes, charge, b,
                      np.nonzero((tc >= C.TRANCHE[0]) & (tc <= C.TRANCHE[1]))[0],
                      f"Tibia du levrier, geometrie figee, {nom}, k = {k}, {len(X)} noeuds (CT-CORA3D)")
    return {"element": nom, "k": k, "facteur_force": facteur, "force_N": round(float(np.linalg.norm(F)), 2),
            "noeuds": len(X), "elements": len(conn), "ddl": info["ddl"], "volume_cm3": round(vol_tout.sum() / 1000, 3),
            "sigma_milieu_MPa": round(float(vm[milieu].max()), 4), "sigma_max_MPa": round(float(vm.max()), 3),
            "u_max_mm": round(float(np.abs(u).max()), 5), "reaction_N": round(float(np.linalg.norm(reaction)), 3),
            "temps_s": round(time.time() - t0, 1), "solveur": info["solveur"]}


def lire_csv():
    if not CSV.exists():
        return []
    with open(CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def etude(ecrire_inp, max_ddl):
    surface = M.lire_os(C.STL)
    faits = {(r["element"], float(r["facteur_force"]), int(r["k"])) for r in lire_csv()}
    CSV.parent.mkdir(exist_ok=True)
    nouveau = not CSV.exists()
    with open(CSV, "a", newline="", encoding="utf-8") as fichier:
        w = csv.DictWriter(fichier, fieldnames=CHAMPS)
        if nouveau:
            w.writeheader()
        for nom, facteur, niveaux in SERIES:
            for k in niveaux:
                if (nom, facteur, k) in faits:
                    continue
                r = calculer(surface, nom, k, facteur, ecrire_inp)
                w.writerow(r)
                fichier.flush()
                print(f"  {nom:6s} F x {facteur:3.1f}  k = {k}  {r['noeuds']:7d} nœuds  {r['elements']:8d} éléments  "
                      f"σ milieu = {r['sigma_milieu_MPa']:7.3f} MPa  réaction {r['reaction_N']:.1f} N  "
                      f"{r['temps_s']:6.1f} s  ({r['solveur']})", flush=True)
                if r["ddl"] > max_ddl:
                    break


# =============================================================================== figures
def series():
    out = {}
    for r in lire_csv():
        out.setdefault((r["element"], float(r["facteur_force"])), []).append(
            (int(r["noeuds"]), int(r["elements"]), float(r["sigma_milieu_MPa"]), int(r["k"])))
    for v in out.values():
        v.sort()
    return out


def figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    from matplotlib.ticker import FuncFormatter
    avenir = Path("/System/Library/Fonts/Avenir Next.ttc")
    if avenir.exists():
        fm.fontManager.addfont(str(avenir))
    plt.rcParams.update({"font.family": ["Avenir Next", "DejaVu Sans"], "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.bbox": "tight", "pdf.fonttype": 42})
    S = series()
    ref = S[("C3D20", 1.0)][-1][2]
    virgule = lambda x, n=2: f"{x:.{n}f}".replace(".", ",")
    milliers = FuncFormatter(lambda v, _: f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}")
    ordre = ("C3D4", "C3D10", "C3D8", "C3D20")

    def sauver(fig, nom):
        fig.savefig(IMAGES / f"{nom}.pdf")
        fig.savefig(ICI / "resultats" / f"{nom}.png", dpi=150)
        plt.close(fig)
        print("  figure", nom)

    # 1. la courbe de convergence, échelle linéaire comme dans Abaqus : en nœuds et en éléments
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.9), sharey=True)
    for ax, col, titre, xmax in ((axes[0], 0, "nombre de nœuds", 160_000), (axes[1], 1, "nombre d'éléments", 1_000_000)):
        ax.axhspan(ref * 0.99, ref * 1.01, color="#3a7d2c", alpha=0.10, lw=0)
        ax.axhline(ref, color="#555555", ls=":", lw=1)
        for el in ordre:
            if (el, 1.0) in S:
                v = S[(el, 1.0)]
                ax.plot([p[col] for p in v], [p[2] for p in v], "o-", color=C.COULEURS[el], label=C.LEGENDES[el],
                        ms=4.5, lw=1.7)
        ax.set_xlim(0, xmax)
        ax.xaxis.set_major_formatter(milliers)
        ax.set_xlabel(titre)
        ax.grid(True, color="#e5e5e5", lw=0.6)
        ax.text(0.97, (ref * 1.012 - ax.get_ylim()[0]) / np.ptp(ax.get_ylim()), "zone de convergence (< 1 % d'écart)",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#3a7d2c")
    axes[0].set_ylabel("σ von Mises max au milieu de la diaphyse (MPa)")
    axes[1].legend(frameon=False, loc="lower right", fontsize=8)
    fig.suptitle(f"Étude de convergence, géométrie figée (plateau : {virgule(ref)} MPa)", fontsize=10)
    sauver(fig, "figee_convergence")

    # 2. la même chose en échelle logarithmique (tout le domaine) et en écart à la référence
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.6))
    for el in ordre:
        if (el, 1.0) in S:
            v = S[(el, 1.0)]
            n = [p[0] for p in v]
            axes[0].plot(n, [p[2] for p in v], "o-", color=C.COULEURS[el], label=C.LEGENDES[el], ms=4.5, lw=1.7)
            w = v[:-1] if el == "C3D20" else v
            axes[1].plot([p[0] for p in w], [100 * abs(p[2] / ref - 1) for p in w], "o-", color=C.COULEURS[el], ms=4.5,
                         lw=1.7)
    axes[0].axhspan(ref * 0.99, ref * 1.01, color="#3a7d2c", alpha=0.10, lw=0)
    axes[0].set_ylabel("σ von Mises max (MPa)")
    axes[1].axhline(1, color="#3a7d2c", ls="--", lw=1)
    axes[1].text(0.99, 1.1, "1 %", transform=axes[1].get_yaxis_transform(), ha="right", fontsize=8, color="#3a7d2c")
    axes[1].set_yscale("log")
    axes[1].set_ylabel("écart au plateau (%)")
    for ax in axes:
        ax.set_xscale("log")
        ax.set_xlabel("nombre de nœuds")
        ax.grid(True, which="both", color="#e5e5e5", lw=0.6)
    axes[0].legend(frameon=False, loc="lower right", fontsize=8)
    sauver(fig, "figee_log")

    # 3. effet de la force : σ proportionnelle à F, plateau atteint au même nombre de nœuds
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.6))
    teintes = {0.5: "#e3a46a", 1.0: "#b8611a", 2.0: "#6e3a0f"}
    for fac in (0.5, 1.0, 2.0):
        if ("C3D8", fac) in S:
            v = S[("C3D8", fac)]
            n = [p[0] for p in v]
            Fn = fac * float(np.linalg.norm(C.FORCE))
            axes[0].plot(n, [p[2] for p in v], "o-", color=teintes[fac], ms=4.5, lw=1.7,
                         label=f"F = {virgule(Fn, 0)} N")
            axes[1].plot(n, [p[2] / fac for p in v], "o-" if fac == 1.0 else "x--", color=teintes[fac], ms=5, lw=1.4,
                         label=f"σ × {virgule(1 / fac, 1)}")
    axes[0].set_ylabel("σ von Mises max, C3D8 (MPa)")
    axes[1].set_ylabel("σ ramenée à F = 301,5 N (MPa)")
    for ax in axes:
        ax.set_xscale("log")
        ax.set_xlabel("nombre de nœuds")
        ax.grid(True, which="both", color="#e5e5e5", lw=0.6)
        ax.legend(frameon=False, loc="lower right", fontsize=8)
    sauver(fig, "figee_force")


if __name__ == "__main__":
    a = argparse.ArgumentParser(description="Étude de convergence à géométrie figée")
    a.add_argument("--inp", action="store_true", help="écrire les fichiers Abaqus (.inp)")
    a.add_argument("--max-ddl", type=int, default=1_400_000)
    a.add_argument("--figures", action="store_true")
    x = a.parse_args()
    if not x.figures:
        etude(x.inp, x.max_ddl)
    figures()
