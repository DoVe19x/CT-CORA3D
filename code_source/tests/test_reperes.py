"""
test_reperes.py — vérifie la détection automatique des repères (etape6_reperes.py).

1. Os du modèle CORA 3D (repères exacts connus), posés n'importe comment dans le « scanner » : rotation et translation
   aléatoires, et en miroir (membre gauche). On vérifie : côté reconnu, repères robustes à moins de 1,5 mm des vrais,
   angles frontaux à moins de 1,5°, torsion à moins de 3°, et résultat identique quelle que soit la pose (le repère de
   l'os ne dépend que de l'os).
2. Os réels segmentés (s'ils existent : resultats/ de CT-CORA3D, sinon de CT-scan) : os coupés refusés, os complets
   analysés, angles dans les normes (lévrier sain), et invariance par déplacement / miroir.

Usage (depuis code_source/) : ../../.venv/bin/python tests/test_reperes.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
sys.path.insert(0, str(ICI))
import etape6_reperes as E      # noqa: E402
import modele_cora as MC        # noqa: E402

ROBUSTES = {"femur": ["head_center", "gt_tip", "cond_med_dist", "cond_lat_dist", "cond_med_caud", "cond_lat_caud",
                      "epi_med", "epi_lat"],
            "tibia": ["caud_med", "tuberosity", "dist_caud"]}
ECHECS = []


def verifier(cond, texte):
    print(("  ok   " if cond else "  ÉCHEC ") + texte)
    if not cond:
        ECHECS.append(texte)


def rotation_aleatoire(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def poser(m, R, t, miroir):
    S = np.diag([-1.0, 1, 1]) if miroir else np.eye(3)
    f = np.asarray(m.faces)
    return trimesh.Trimesh((np.asarray(m.vertices) @ S.T) @ R.T + t, f[:, ::-1] if miroir else f, process=True)


def test_modele():
    print("1. Os du modèle CORA 3D dans des poses aléatoires")
    os_, rep, _ = MC.charger()
    cal = E.calibration()["os"]
    rng = np.random.default_rng(7)
    for type_os in ("femur", "tibia"):
        m0 = trimesh.Trimesh(*os_[type_os], process=True)
        f0 = trimesh.Trimesh(*os_["fibula"], process=True) if type_os == "tibia" else None
        vrais = dict(rep[type_os], **(rep["fibula"] if type_os == "tibia" else {}))
        poses = []
        for k, miroir in enumerate((False, True, False, True)):
            R, t = rotation_aleatoire(rng), rng.normal(0, 150, 3)
            res, O = E.analyser(poser(m0, R, t, miroir), type_os, poser(f0, R, t, miroir) if f0 else None)
            verifier(res.get("complet"), f"{type_os} pose {k + 1} : analyse complète")
            if not res.get("complet"):
                continue
            verifier(res["cote"] == ("gauche" if miroir else "droit"), f"{type_os} pose {k + 1} : côté {res['cote']}")
            M = np.array(res["repere"]["scanner_vers_os"])
            S = np.diag([-1.0, 1, 1]) if miroir else np.eye(3)
            vrai = {n: M[:3, :3] @ (R @ (S @ np.array(p)) + t) + M[:3, 3] for n, p in vrais.items()}
            ecarts = {n: float(np.linalg.norm(np.array(res["reperes"][n]) - vrai[n])) for n in ROBUSTES[type_os]}
            pire = max(ecarts, key=ecarts.get)
            verifier(ecarts[pire] < 1.5, f"{type_os} pose {k + 1} : repères robustes à ≤ 1,5 mm des vrais "
                                        f"(pire : {pire} {ecarts[pire]:.2f} mm)")
            poses.append(res)
        # le résultat ne dépend pas de la pose : repères identiques dans le repère de l'os
        if len(poses) > 1:
            d = max(np.linalg.norm(np.array(p["reperes"][n]) - np.array(poses[0]["reperes"][n]))
                    for p in poses[1:] for n in poses[0]["reperes"])
            verifier(d < 0.5, f"{type_os} : mêmes repères dans les {len(poses)} poses (écart max {d:.3f} mm)")
        # angles : écart de définition (calibration) sur l'os sain du modèle
        c = cal[type_os]
        frontaux = ["aLPFA", "aLDFA"] if type_os == "femur" else ["mMPTA", "mMDTA"]
        e = max(abs(c[k]["ecart"]) for k in frontaux)
        verifier(e < 1.5, f"{type_os} : angles frontaux à ≤ 1,5° du modèle ({', '.join(f'{k} {c[k]['ecart']:+.2f}°' for k in frontaux)})")
        et = abs(c["torsion"]["detecte"] - c["torsion"]["modele"])
        verifier(et < 3.0, f"{type_os} : torsion {c['torsion']['detecte']:.1f}° pour {c['torsion']['modele']:.1f}° (écart {et:.1f}°)")
        sag = ["aCdDFA"] if type_os == "femur" else ["mCaPTA", "mCrDTA"]
        print("       écarts de définition sagittaux (pris en compte dans les valeurs normales) : "
              + ", ".join(f"{k} {c[k]['ecart']:+.1f}°" for k in sag))


def dossier_resultats():
    for d in (ICI.parent.parent / "resultats", ICI.parent.parent.parent / "CT-scan" / "resultats"):
        if (d / "greyhound_hindlimb_hip_to_knee" / "femur.stl").exists():
            return d
    return None


def test_reel():
    D = dossier_resultats()
    if D is None:
        print("2. Os réels : aucun résultat de segmentation trouvé (test sauté)")
        return
    print(f"2. Os réels segmentés ({D})")
    attendu = {("greyhound_hindlimb_hip_to_knee", "femur"): True, ("greyhound_hindlimb_knee_to_ankle", "tibia"): True,
               ("greyhound_hindlimb_knee_to_ankle", "femur"): False, ("greyhound_hindlimb_hip_to_knee", "tibia"): False}
    rng = np.random.default_rng(3)
    for (serie, type_os), complet in attendu.items():
        d = D / serie
        if not (d / f"{type_os}.stl").exists():
            continue
        m = trimesh.load(d / f"{type_os}.stl", process=True)
        fib = trimesh.load(d / "fibula.stl", process=True) if type_os == "tibia" and (d / "fibula.stl").exists() else None
        tete = E.charger_tete(d) if type_os == "femur" else None
        if tete is not None and np.min(np.linalg.norm(m.vertices - tete, axis=1)) > 30:
            tete = None
        t0 = time.time()
        res, O = E.analyser(m, type_os, fib, tete)
        nom = f"{serie.replace('greyhound_hindlimb_', '')} / {type_os}"
        verifier(bool(res.get("complet")) == complet,
                 f"{nom} : {'complet' if res.get('complet') else 'refusé (' + res.get('raison', '') + ')'} ({time.time() - t0:.1f} s)")
        if not res.get("complet"):
            continue
        N = res["normales"]
        hors = [f"{k} {res['angles'][k]:.1f}° (normal {N[k]['valeur']:.1f} ± {2 * N[k]['sd']:.1f})"
                for k in N if abs(res["angles"][k] - N[k]["valeur"]) > 2 * N[k]["sd"]]
        verifier(not hors, f"{nom} : angles dans les normes (lévrier sain)" + (" — hors normes : " + "; ".join(hors) if hors else
                 " : " + ", ".join(f"{k} {res['angles'][k]:.1f}°" for k in N)))
        # invariance : même os déplacé, puis en miroir (l'autre côté)
        for miroir in (False, True):
            R, t = rotation_aleatoire(rng), rng.normal(0, 100, 3)
            tete2 = None if tete is None else ((np.diag([-1.0, 1, 1]) if miroir else np.eye(3)) @ tete) @ R.T + t
            res2, _ = E.analyser(poser(m, R, t, miroir), type_os, poser(fib, R, t, miroir) if fib else None, tete2)
            d_ = max(np.linalg.norm(np.array(res2["reperes"][n]) - np.array(res["reperes"][n])) for n in res["reperes"])
            da = max(abs(res2["angles"][k] - res["angles"][k]) for k in res["angles"])
            cote_ok = (res2["cote"] != res["cote"]) if miroir else (res2["cote"] == res["cote"])
            verifier(d_ < 0.6 and da < 0.5 and cote_ok, f"{nom} {'en miroir' if miroir else 'déplacé'} : mêmes repères "
                     f"(écart max {d_:.2f} mm, angles {da:.2f}°), côté {res2['cote']}")


if __name__ == "__main__":
    t0 = time.time()
    test_modele()
    test_reel()
    print(f"\n{'TOUT EST BON' if not ECHECS else f'{len(ECHECS)} ÉCHEC(S)'} — {time.time() - t0:.0f} s")
    sys.exit(1 if ECHECS else 0)
