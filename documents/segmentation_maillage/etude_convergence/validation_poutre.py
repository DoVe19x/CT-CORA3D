"""
validation_poutre.py : vérifie le code d'éléments finis (ef.py) avant l'étude sur l'os.

(1) Fonctions de forme de chaque élément : somme égale à 1 partout, Ni = 1 au nœud i et 0 aux autres nœuds,
    dérivées égales aux différences finies.
(2) Poutre console 100 × 10 × 10 mm encastrée en x = 0, sous son poids (charge volumique uniforme, q = 1 N/mm) :
    contrainte σ11 en fibre supérieure à mi-longueur et flèche au bout, comparées à la théorie des poutres :
        σ = M c / I avec M = q (L/2)² / 2         -> 7,5 MPa
        f = q L⁴ / (8 E I) + q L² / (2 κ G A)      -> 0,891 mm (flexion + cisaillement, κ = 5/6)
Usage : python validation_poutre.py      (écrit resultats/validation_poutre.csv)
"""
import csv
from pathlib import Path

import numpy as np

import ef
import maillages as M

ICI = Path(__file__).resolve().parent
E, NU = 17000.0, 0.3
L, B, H, Q = 100.0, 10.0, 10.0, 1.0


def fonctions_de_forme():
    rng = np.random.default_rng(0)
    for nom, el in ef.ELEMENTS.items():
        N = el.N(el.noeuds_ref)
        xi = rng.uniform(0.05, 0.3, (20, 3)) if nom.startswith("C3D1") or nom == "C3D4" else rng.uniform(-0.9, 0.9, (20, 3))
        s = el.N(xi).sum(1)
        e = 1e-6
        fd = np.stack([(el.N(xi + e * np.eye(3)[k]) - el.N(xi - e * np.eye(3)[k])) / (2 * e) for k in range(3)], -1)
        ok = np.allclose(N, np.eye(el.nn), atol=1e-12) and np.allclose(s, 1) and np.allclose(fd, el.dN(xi), atol=1e-6)
        assert np.allclose(el.poids.sum(), 1 / 6 if nom in ("C3D4", "C3D10") else 8)
        print(f"  {nom:6s} fonctions de forme : {'OK' if ok else 'ERREUR'}")
        assert ok


def poutre():
    I = B * H ** 3 / 12
    G = E / (2 * (1 + NU))
    sigma_th = Q * (L / 2) ** 2 / 2 * (H / 2) / I
    fleche_th = Q * L ** 4 / (8 * E * I) + Q * L ** 2 / (2 * 5 / 6 * G * B * H)
    D = ef.elasticite(E, NU)
    lignes = []
    print(f"  théorie : σ11 = {sigma_th:.3f} MPa, flèche = {fleche_th:.4f} mm")
    for m in (1, 2, 3, 4, 6):
        X8, c8 = M.poutre_hexa(L, B, H, m)
        X4, c4 = M.hexa_vers_tetra(X8, c8)
        for nom, (X0, c0) in (("C3D4", (X4, c4)), ("C3D10", (X4, c4)), ("C3D8", (X8, c8)), ("C3D20", (X8, c8))):
            X, conn = M.maillage(nom, X0, c0)
            b = np.array([0, 0, -Q / (B * H)])
            K, f, vol = ef.assembler(X, conn, nom, D, b, np.arange(len(conn)))
            fixes = np.nonzero(np.isclose(X[:, 0], 0))[0]
            u, info = ef.resoudre(K, f, X, fixes)
            s = ef.contraintes_noeuds(X, conn, nom, D, u)
            p = np.argmin(np.linalg.norm(X - [L / 2, B / 2, H], axis=1))
            bout = np.isclose(X[:, 0], L)
            fl = -u[2::3][bout].mean()
            lignes.append({"element": nom, "elements_epaisseur": m, "noeuds": len(X), "sigma11_MPa": round(s[p, 0], 4),
                           "erreur_sigma_pct": round(100 * (s[p, 0] / sigma_th - 1), 2), "fleche_mm": round(fl, 5),
                           "erreur_fleche_pct": round(100 * (fl / fleche_th - 1), 2), "volume_mm3": round(vol.sum(), 3)})
            print(f"  m = {m}  {nom:6s} {len(X):6d} nœuds  σ11 = {s[p, 0]:7.3f} MPa ({lignes[-1]['erreur_sigma_pct']:+6.2f} %)"
                  f"  flèche = {fl:.4f} mm ({lignes[-1]['erreur_fleche_pct']:+6.2f} %)")
    (ICI / "resultats").mkdir(exist_ok=True)
    with open(ICI / "resultats" / "validation_poutre.csv", "w", newline="", encoding="utf-8") as fichier:
        w = csv.DictWriter(fichier, fieldnames=list(lignes[0]))
        w.writeheader()
        w.writerows(lignes)
    return lignes


if __name__ == "__main__":
    print("1. Fonctions de forme")
    fonctions_de_forme()
    print("2. Poutre console sous charge répartie")
    poutre()
