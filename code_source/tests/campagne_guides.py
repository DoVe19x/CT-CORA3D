"""
campagne_guides.py — campagne de simulation des guides sur l'os fictif : construction et contrôles « de chirurgien ».

Pour chaque cas écrit par campagne_export.mjs : construit les guides (etape7_guide.generer, en parallèle), puis contrôle,
indépendamment de la construction :
  planification  angle vrai retrouvé, angles après correction = os sain, angle et translation résiduels, torsion après
                 dérotation = cible, broches parallèles après correction, ostéotomie possible ;
  guide          alertes de l'étape 7, jeu et interpénétration avec l'os, deux moitiés, retrait, appui de CHAQUE moitié
                 (surface et couverture angulaire autour de l'os) ;
  voisins        guide et guide de réduction contre la fibula (tibia), la rotule et les fabelles (fémur) ;
  articulations  guide posé sur le cartilage, broche dans le cartilage, trait de coupe dans le cartilage ;
  broches        broche qui traverse un os voisin, broche non bicorticale, entrée très oblique sur la corticale ;
  coupe          os voisin sur le trajet de la lame (côté guide : erreur ; derrière l'os d'une coupe complète : à protéger).
Les fentes trop proches d'un petit coin de fermeture (l'application propose alors le coin d'ouverture) et la torsion
laissée sous le seuil de dérotation (DEROTATION_MIN = 1°, en deçà de la précision de mesure) ne sont pas des erreurs.
Écrit <cas>/../resultats_campagne.jsonl et un rapport (rapport_campagne.md).

Usage (depuis code_source/) : ../../.venv/bin/python tests/campagne_guides.py <dossier des cas> [--processus 4] [--garder]
                              ../../.venv/bin/python tests/campagne_guides.py <dossier des cas> --rapport   (rapport seul)
"""
import argparse
import inspect
import json
import multiprocessing as mp
import shutil
import sys
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))

SEUILS = {"ecart_theta": 0.05, "post": 0.1, "residuel": 0.01, "decalage": 0.5, "torsion": 1.01, "paralleles": 0.01,
          "voisin_mm": 0.5, "cartilage_guide_mm": 1.0, "broche_voisin_mm": 0.5, "broche_cartilage_mm": 2.0,
          "coupe_cartilage_mm": 1.0, "appui_moitie_mm2": 100.0, "couverture_deg": 60.0, "entree_deg": 50.0,
          "bicortical_mm": 5.0, "reduction_voisin_mm": 0.5}


def lire_bin(f):
    b = Path(f).read_bytes()
    nv, nf = (int(x) for x in np.frombuffer(b, np.uint32, 2))
    return (np.frombuffer(b, np.float32, nv * 3, 8).reshape(-1, 3).astype(float),
            np.frombuffer(b, np.uint32, nf * 3, 8 + nv * 12).reshape(-1, 3).astype(np.int64))


def normales_sommets(v, f):
    n = np.zeros_like(v)
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for i in range(3):
        np.add.at(n, f[:, i], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def corrige(E7, man, plans, T, coupe=True):
    """Voisin après la correction : coupé par les plans comme l'os (fibula) ou déplacé en bloc s'il est distal (rotule)."""
    if coupe:
        return E7.os_corrige(man, plans, T)
    v, _ = E7.depuis_manifold(man)
    p, n = plans[-1]
    return man.transform(np.asarray(T)[:3, :]) if float(np.mean((v - p) @ n)) > 0 else man


def cote_guide(E7, gv, spr, nom="guide"):
    """Contrôle indépendant de la construction : près du trait, la matière du guide est-elle du côté OPPOSÉ à la
    charnière ? (centre de la matière à moins de 8 mm du 1er plan de coupe, comparé à la direction centre de la section
    -> charnière, dans le plan transverse). Renvoie (angle en degrés entre la matière et la charnière, message d'erreur)."""
    p0, n0 = np.array(spr["plans_coupe"][0]["point"]), E7.unitaire(spr["plans_coupe"][0]["normale"])
    K, H = np.array(spr["guide"]["centre_section"]), np.array(spr["charniere"]["point"])
    u = E7.unitaire(spr["guide"]["axe_os"])
    pres = gv[np.abs((gv - p0) @ n0) < 8.0]
    hd = (H - K) - ((H - K) @ u) * u
    if len(pres) < 20 or np.linalg.norm(hd) < 1.0:
        return None, None
    g = pres.mean(0) - K
    g = g - (g @ u) * u
    ang = float(np.degrees(np.arccos(np.clip(E7.unitaire(g) @ E7.unitaire(hd), -1, 1))))
    return ang, (f"côté : {nom} du côté de la charnière ({ang:.0f}° entre la matière du guide et la charnière)" if ang < 90 else None)


# Coin forcé alors que la planification le déclare non réalisable par un abord usuel (elle recommande l'autre type de
# coin) : un os voisin sur le trajet de la lame, et une tour de fente amputée par cet os voisin, en sont la conséquence
# attendue (ils confirment l'avertissement), pas un défaut de construction du guide.
ATTENDUS_ABORD_NON_USUEL = ("sur le trajet de la lame (côté de la face d'appui)", "détachée(s) du guide",
                            "guide de coupe non construit")   # 22/10/2026 : refus motivé de l'étape 7
# appui insuffisant : attendu seulement si l'os voisin est bien sur la face d'appui (il masque la coque), 21/10/2026
ATTENDUS_SI_VOISIN_SUR_LA_FACE = ("sans appui sur l'os", "sans contact avec l'os", "posé sur")


def classer_attendus(res, pr):
    """Range dans res["attendus"] les erreurs attendues d'un coin en abord non usuel (pr : prescription du cas)."""
    if not (pr.get("strategie") or {}).get("abord_non_usuel"):
        return res
    voisin_face = any(ATTENDUS_ABORD_NON_USUEL[0] in e for e in res["erreurs"] + res.get("attendus", []))
    att = [e for e in res["erreurs"] if any(t in e for t in ATTENDUS_ABORD_NON_USUEL)
           or (voisin_face and any(t in e for t in ATTENDUS_SI_VOISIN_SUR_LA_FACE))]
    if att:
        res["attendus"] = res.get("attendus", []) + att
        res["erreurs"] = [e for e in res["erreurs"] if e not in att]
    return res


def controler(dossier, garder=False):
    import etape7_guide as E7
    import parametres as P
    d = Path(dossier)
    plan = json.loads((d / "planification.json").read_text(encoding="utf-8"))
    res = {"id": plan["id"], "cas": {k: plan[k] for k in ("bone", "frontal", "sagittal", "F", "S", "niveau", "torsion", "kind", "serie")},
           "erreurs": [], "avertissements": [], "mesures": {}}
    E, A, M = res["erreurs"], res["avertissements"], res["mesures"]

    # ---------------------------------------------------------------- planification
    if not plan["osteoPossible"]:
        E.append("planification : pas d'ostéotomie au CORA")
        return res
    o = plan["osteo"]
    M.update(theta=plan["theta"], ecart_theta=plan["ecartTheta"], post=o["postMax"], residuel=o["residuel"], decalage=o["decalage"],
             torsion_ecart=abs(o["torsionApres"] - o["torsionCible"]), derotation=o["derotation"], paralleles=o["brochesParalleles"],
             base=o["base"], dlongueur=o["dLongueur"])
    for cle, val, txt in (("ecart_theta", abs(plan["ecartTheta"]), "angle vrai mal retrouvé"), ("post", o["postMax"], "angles après correction ≠ os sain"),
                          ("residuel", o["residuel"], "angle résiduel"), ("decalage", o["decalage"], "translation résiduelle"),
                          ("torsion", M["torsion_ecart"], "torsion après correction ≠ cible"), ("paralleles", o["brochesParalleles"], "broches non parallèles après correction")):
        if val is None or val > SEUILS[cle]:
            E.append(f"planification : {txt} ({val})")

    # ---------------------------------------------------------------- guides
    pr = json.loads((d / "prescription.json").read_text(encoding="utf-8"))
    v, f = lire_bin(d / "os.bin")
    voisins = {p_.stem[len("voisin_"):]: lire_bin(p_) for p_ in sorted(d.glob("voisin_*.bin"))}
    cart = {p_.stem[len("cartilage_"):]: np.frombuffer(p_.read_bytes(), np.uint8) for p_ in d.glob("cartilage_*.u8")}
    sortie = Path(tempfile.mkdtemp(prefix="guide_"))
    kw = {}
    sig = inspect.signature(E7.generer).parameters
    if "voisins" in sig:
        kw["voisins"] = [(n_, vv, ff) for n_, (vv, ff) in voisins.items()]
    if "articulaire" in sig:
        kw["articulaire"] = cart.get(plan["bone"])
    t0 = time.time()
    try:
        info = E7.generer(pr, (v, f), sortie, journal=lambda *_: None, image=False, **kw)
    except Exception as exc:
        if type(exc).__name__ == "GuideImpossible":     # refus motivé (os voisin sur la face du coin) : pas un plantage
            E.append(f"étape 7 : {exc}")
            shutil.rmtree(sortie, ignore_errors=True)
            return classer_attendus(res, pr)
        E.append(f"guide : exception {type(exc).__name__} : {exc}")
        res["trace"] = traceback.format_exc()[-1500:]
        shutil.rmtree(sortie, ignore_errors=True)
        return res
    M["duree_s"] = round(time.time() - t0, 1)
    C, R = info["guide_coupe"], info["guide_reduction"]
    # avertissements : limites de conception avec un repli valide (fentes très proches : coin d'ouverture conseillé) ;
    # tout le reste est une erreur
    LIMITES = ("fentes très proches",)
    for a in info["alertes"]:
        (A if a.startswith(LIMITES) else E).append(f"étape 7 : {a}")
    for a in plan["osteo"].get("alertes") or []:
        A.append(f"planification : {a.split(' (')[0].split(' : ')[0]}")
    M.update(regle=plan["osteo"].get("regle"), complete=int(bool(pr["strategie"].get("osteotomie_complete"))))
    M.update(jeu=C["jeu_minimal_mesure_mm"], appui=C["surface_appui_mm2"], interpenetration=C["volume_interpenetration_mm3"],
             bras=len(C.get("bras_ajoutes") or []), repousses=C.get("sommets_repousses_au_jeu", 0))
    if C.get("ilots_coque_ecartes_mm3"):
        A.append(f"guide : îlot(s) de coque isolé(s) par le cartilage ou un os voisin, écarté(s) ({', '.join(f'{x:.0f}' for x in C['ilots_coque_ecartes_mm3'])} mm³)")
    if C["surface_appui_mm2"] < 300:
        E.append(f"appui : guide entier posé sur {C['surface_appui_mm2']:.0f} mm² seulement")

    gv, gf = E7.lire_maillage(sortie / "guide_coupe.bin")
    g_man = E7.vers_manifold(gv, gf)
    # côté du guide (contrôle indépendant sur le maillage construit)
    ang_cote, err_cote = cote_guide(E7, gv, pr)
    if ang_cote is not None:
        M["cote_guide_deg"] = round(ang_cote, 1)
    if err_cote:
        E.append(err_cote)
    st_ = pr.get("strategie", {})
    if st_.get("abord_non_usuel"):
        A.append("planification : coin non réalisable par un abord usuel (guide sur la face du coin)")
    M["broches_n"] = len(C["broches"])
    J = P.GUIDE_JEU_MM
    dist_os = E7.DistanceSurface(v, f)
    p_sep, n_sep = np.array(pr["plans_coupe"][0]["point"]), E7.unitaire(pr["plans_coupe"][0]["normale"])
    face = E7.unitaire(pr["guide"]["face_appui"])

    # appui de chaque moitié : surface au contact et couverture angulaire autour de l'os
    for nom in ("proximal", "distal"):
        fb = sortie / f"guide_coupe_{nom}.bin"
        if not fb.exists():
            E.append(f"guide : moitié {nom} absente")
            continue
        hv, hf = lire_bin(fb)
        tri = hv[hf]
        aires = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        cen = tri.mean(1)
        contact = dist_os(cen) < J + 0.15
        aire = float(aires[contact].sum())
        axe = E7.unitaire(pr["guide"]["axe_os" if nom == "proximal" else "axe_distal"])
        c0 = E7.perp(face, axe)
        s0 = np.cross(axe, c0)
        q = cen[contact] - np.array(pr["guide"]["centre_section"])
        ang = np.degrees(np.arctan2(q @ s0, q @ c0)) if len(q) else np.array([0.0])
        couverture = float(np.percentile(ang, 98) - np.percentile(ang, 2)) if len(q) > 10 else 0.0
        M[f"appui_{nom}"] = round(aire, 1)
        M[f"couverture_{nom}"] = round(couverture, 1)
        # après la coupe des ponts, chaque moitié est tenue par ses 2 broches parallèles : un faible appui propre n'est
        # qu'un avertissement ; aucune surface au contact de l'os est une erreur
        if aire < 30:
            E.append(f"appui : moitié {nom} sans contact avec l'os ({aire:.0f} mm²)")
        elif aire < SEUILS["appui_moitie_mm2"]:
            A.append(f"appui : moitié {nom} posée sur {aire:.0f} mm² seulement")
        if couverture < SEUILS["couverture_deg"]:
            A.append(f"appui : moitié {nom} n'embrasse que {couverture:.0f}° de l'os (rotation possible)")

    # voisins (fibula, rotule, fabelles) : guide de coupe
    plans = [(np.array(p_["point"]), E7.unitaire(p_["normale"])) for p_ in pr["plans_coupe"]]
    T = np.asarray(pr["correction"]["T_4x4"])
    for nom, (vv, ff) in voisins.items():
        dmin = float(E7.DistanceSurface(vv, ff, zone=(gv.min(0) - 6, gv.max(0) + 6))(gv).min()) if len(ff) else 99
        try:
            vol = float((g_man ^ E7.vers_manifold(vv, ff)).volume())
        except ValueError:
            vol = None
        M[f"guide_{nom}_mm"] = round(dmin, 2)
        if (vol or 0) > 0.01 or dmin < SEUILS["voisin_mm"]:
            E.append(f"voisin : le guide de coupe {'traverse' if (vol or 0) > 0.01 else 'touche'} {nom} (jeu {dmin:.2f} mm, {vol or 0:.1f} mm³)")

    # cartilage : guide posé sur le cartilage
    for nom, c_ in cart.items():
        pts = (v if nom == plan["bone"] else voisins.get(nom, (np.zeros((0, 3)), None))[0])
        if pts is None or not len(pts):
            continue
        pc = pts[c_[:len(pts)] >= 128]
        if not len(pc):
            continue
        dc = float(E7.DistanceSurface(gv, gf, zone=(pc.min(0) - 6, pc.max(0) + 6))(pc).min())
        M[f"cartilage_{nom}_mm"] = round(dc, 2)
        if dc < SEUILS["cartilage_guide_mm"]:
            E.append(f"articulation : le guide de coupe est à {dc:.2f} mm du cartilage de {nom}")

    # broches
    rp = P.GUIDE_BROCHE_MM / 2
    cart_os = v[cart[plan["bone"]][:len(v)] >= 128] if plan["bone"] in cart else np.zeros((0, 3))
    nrm = normales_sommets(v, f)
    from scipy.spatial import cKDTree
    arbre_v = cKDTree(v)
    for b in C["broches"]:
        e_, s_, top = np.array(b["entree_os"]), np.array(b["sortie_os"]), np.array(b["haut_manchon"])
        dvec = E7.unitaire(s_ - e_)
        bout = s_ + 5.0 * dvec                                     # la broche dépasse la corticale opposée de ≈ 5 mm
        ts = np.linspace(0, 1, 200)[:, None]
        trajet = top + ts * (bout - top)
        long_os = float(np.linalg.norm(s_ - e_))
        if long_os < SEUILS["bicortical_mm"]:
            E.append(f"broche {b['nom']} : {long_os:.1f} mm d'os seulement (non bicorticale)")
        for nom, (vv, ff) in voisins.items():
            dv = float(E7.DistanceSurface(vv, ff, zone=(trajet.min(0) - 6, trajet.max(0) + 6))(trajet).min()) if len(ff) else 99
            M.setdefault("broche_voisin_mm", 99)
            M["broche_voisin_mm"] = round(min(M["broche_voisin_mm"], dv), 2)
            if dv < rp + SEUILS["broche_voisin_mm"]:
                E.append(f"broche {b['nom']} : traverse ou frôle {nom} (axe à {dv:.2f} mm)")
        if len(cart_os):
            dcb = float(cKDTree(cart_os).query(np.vstack([e_ + t_ * (bout - e_) for t_ in np.linspace(0, 1, 120)]))[0].min())
            M.setdefault("broche_cartilage_mm", 99)
            M["broche_cartilage_mm"] = round(min(M["broche_cartilage_mm"], dcb), 2)
            if dcb < SEUILS["broche_cartilage_mm"]:
                E.append(f"broche {b['nom']} : à {dcb:.1f} mm du cartilage (dans l'articulation)")
        _, i_ = arbre_v.query(e_)
        angle_entree = float(np.degrees(np.arccos(np.clip(abs(nrm[i_] @ dvec), 0, 1))))
        M.setdefault("entree_max_deg", 0)
        M["entree_max_deg"] = round(max(M["entree_max_deg"], angle_entree), 1)
        if angle_entree > SEUILS["entree_deg"]:
            A.append(f"broche {b['nom']} : entrée à {angle_entree:.0f}° de la normale à la corticale (la mèche peut glisser)")

    # traits de coupe : cartilage et voisins sur le trajet de la lame (fente : de la face d'appui jusqu'à la charnière, ou
    # jusqu'à 3 mm au-delà de la corticale opposée pour une coupe complète), sur la longueur de la fente
    K = np.array(pr["guide"]["centre_section"])
    larg = plan["section"]["largeur"] or 20
    H = np.array(pr["charniere"]["point"])
    complete = bool(pr["strategie"].get("osteotomie_complete"))
    for i, (p_, n_) in enumerate(plans):
        if len(cart_os):
            pres = (np.abs((cart_os - p_) @ n_) < SEUILS["coupe_cartilage_mm"]) & (np.linalg.norm(cart_os - K, axis=1) < 1.5 * larg)
            if pres.any():
                E.append(f"coupe {i + 1} : le trait passe dans le cartilage articulaire ({int(pres.sum())} sommets)")
        hh = E7.perp(face, n_)
        ll = np.cross(n_, hh)
        sec = v[(np.abs((v - p_) @ n_) < 0.6) & (np.linalg.norm(v - K, axis=1) < 1.5 * larg)]
        if not len(sec):
            continue
        l_os, h_os = (sec - H) @ ll, (sec - H) @ hh
        for nom, (vv, ff) in voisins.items():
            pres = (np.abs((vv - p_) @ n_) < 0.5) & (np.linalg.norm(vv - K, axis=1) < 2 * larg)
            if not pres.any():
                continue
            l_, h_ = (vv[pres] - H) @ ll, (vv[pres] - H) @ hh
            dans_l = (l_ > l_os.min() - 1) & (l_ < l_os.max() + 1)
            if nom == "fibula":
                A.append(f"coupe {i + 1} : la fibula croise le plan de coupe (ostéotomie de la fibula à prévoir)")
            if (dans_l & (h_ > 0) & (h_ < h_os.max() + 14)).any():
                E.append(f"coupe {i + 1} : {nom} sur le trajet de la lame (côté de la face d'appui)")
            elif complete and (dans_l & (h_ <= 0) & (h_ > h_os.min() - 3)).any():
                A.append(f"coupe {i + 1} : {nom} derrière l'os sur le trajet d'une coupe complète (à protéger)")

    # guide de réduction contre les voisins après correction
    if R and (sortie / "guide_reduction.bin").exists():
        rv, rf = lire_bin(sortie / "guide_reduction.bin")
        r_man = E7.vers_manifold(rv, rf)
        for nom, (vv, ff) in voisins.items():
            try:
                vc_man = corrige(E7, E7.vers_manifold(vv, ff), plans, T, coupe=(nom == "fibula"))
                vcv, vcf = E7.depuis_manifold(vc_man)
                dr = float(E7.DistanceSurface(vcv, vcf, zone=(rv.min(0) - 6, rv.max(0) + 6))(rv).min())
                vol = float((r_man ^ vc_man).volume())
            except ValueError:
                continue
            M[f"reduction_{nom}_mm"] = round(dr, 2)
            if vol > 0.01 or dr < SEUILS["reduction_voisin_mm"]:
                E.append(f"voisin : le guide de réduction {'traverse' if vol > 0.01 else 'touche'} {nom} (jeu {dr:.2f} mm)")

    classer_attendus(res, pr)
    E = res["erreurs"]
    if garder or E:
        dest = d / "guide"
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(sortie, dest)
    shutil.rmtree(sortie, ignore_errors=True)
    return res


def _travail(args):
    dossier, garder = args
    try:
        return controler(dossier, garder)
    except Exception as exc:
        return {"id": Path(dossier).name, "cas": {}, "erreurs": [f"campagne : exception {type(exc).__name__} : {exc}"],
                "avertissements": [], "mesures": {}, "trace": traceback.format_exc()[-1500:]}


def planification(dossier):
    """Section « planification » du rapport : stratégie retenue par le cœur pour chaque cas (planification.json)."""
    import re
    rows = [json.loads(p_.read_text(encoding="utf-8")) for p_ in sorted(Path(dossier).glob("*/planification.json"))]
    o = [r_.get("osteo") or {} for r_ in rows]
    if not rows:
        return []
    pb = [x.get("placementBroches") or {} for x in o]
    tors = [int(m.group(1)) for r_ in rows if (m := re.search(r"_t(-?\d+)_", r_["id"]))]
    abords = Counter()
    autres = Counter()
    for x in o:
        for a in x.get("alertes") or []:
            if a.startswith("face du coin"):
                abords[a.split("(")[1].split(")")[0]] += 1
            elif "décalées" in a:
                autres["paire de broches décalée de la ligne centrale"] += 1
            elif "tournées" in a:
                autres["broches tournées autour de l'os"] += 1
            elif "côte à côte" in a:
                autres["broches côte à côte (fragment court)"] += 1
            elif "raccourcis" in a:
                autres["manchons distaux raccourcis"] += 1
            elif "trop fin" in a:
                autres["coin de fermeture trop fin pour deux fentes (ouverture conseillée)"] += 1
            elif "contact osseux" in a:
                autres["translation de la règle 2 > 50 % de la largeur"] += 1
            elif "ne peuvent pas sortir" in a:
                autres["retrait des moitiés non garanti"] += 1
    n = len(rows)
    lignes = ["## Planification (cœur de calcul)", "",
              f"{n} cas : fémur {sum(r_['bone'] == 'femur' for r_ in rows)}, tibia {sum(r_['bone'] == 'tibia' for r_ in rows)} ; "
              f"F {min(r_['F'] for r_ in rows)}–{max(r_['F'] for r_ in rows)}°, S {min(r_['S'] for r_ in rows)}–{max(r_['S'] for r_ in rows)}°, "
              + (f"torsion {min(tors)}–{max(tors)}°, " if tors else "")
              + f"apex à {min(r_['niveau'] for r_ in rows):.2f}–{max(r_['niveau'] for r_ in rows):.2f} de la longueur.", "",
              "| Contrôle | Résultat |", "|---|---|",
              f"| Broches placées (toutes les règles respectées) | {sum(bool(x.get('ok')) for x in pb)} / {n} |",
              f"| Retrait des deux moitiés garanti | {sum(bool(x.get('retraitLibre', True)) for x in pb)} / {n} |",
              f"| Règle 2 de Paley (coupe hors du cartilage) | {sum(x.get('regle') == 2 for x in o)} |",
              f"| Angle vrai retrouvé (écart max) | {max(abs(r_.get('ecartTheta') or 0) for r_ in rows):.4f}° |",
              f"| Angles articulaires après correction (écart max à l'os sain) | {max(x.get('postMax') or 0 for x in o):.4f}° |",
              f"| Angle résiduel entre les axes (max) | {max(x.get('residuel') or 0 for x in o):.6f}° |",
              f"| Translation résiduelle entre les axes (max) | {max(x.get('decalage') or 0 for x in o):.3f} mm |",
              f"| Broches parallèles après correction (écart max) | {max(x.get('brochesParalleles') or 0 for x in o):.6f}° |"]
    if any(x.get("regle") == 2 for x in o):
        lignes.append(f"| Translation à l'ostéotomie, règle 2 (max) | {max(x.get('translationOsteo') or 0 for x in o if x.get('regle') == 2):.1f} mm |")
    lignes += ["", "Abord changé (guide par l'abord usuel, ostéotomie complète) :", ""]
    lignes += [f"* {k} : {v}" for k, v in abords.most_common()] or ["* aucun"]
    lignes += ["", "Adaptations du placement des broches et alertes de planification :", ""]
    lignes += [f"* {k} : {v}" for k, v in autres.most_common()] or ["* aucune"]
    return lignes + [""]


def rapport(resultats, chemin):
    cat = Counter()
    par_param = defaultdict(Counter)
    for r in resultats:
        for e in r["erreurs"]:
            c = e.split(" : ")[0] + " : " + e.split(" : ")[1].split(" (")[0] if " : " in e else e
            cat[c] += 1
            for k in ("bone", "kind", "frontal", "sagittal"):
                par_param[k][f"{r['cas'].get(k)}"] += 1
    n = len(resultats)
    ok = sum(1 for r in resultats if not r["erreurs"])
    n_att = sum(1 for r in resultats if r.get("attendus") and not r["erreurs"])
    lignes = [f"# Campagne de simulation des guides — {time.strftime('%Y-%m-%d %H:%M')}", "",
              f"{n} cas, **{ok} sans erreur** ({100 * ok / max(n, 1):.0f} %"
              + (f", dont {n_att} coins forcés en abord non usuel : conséquences attendues, voir plus bas" if n_att else "")
              + f"), {n - ok} avec au moins une erreur.", ""]
    lignes += planification(Path(chemin).parent)
    lignes += ["## Erreurs par type", "", "| Type | Cas |", "|---|---|"]
    lignes += [f"| {k} | {v} |" for k, v in cat.most_common()]
    av = Counter()
    for r in resultats:
        for a in r["avertissements"]:
            av[a.split(" : ")[0] + " : " + a.split(" : ")[1].split(" (")[0].split(" à ")[0]] += 1
    lignes += ["", "## Avertissements", "", "| Type | Cas |", "|---|---|"] + [f"| {k} | {v} |" for k, v in av.most_common()]
    att = Counter()
    for r in resultats:
        for e in r.get("attendus", []):
            att[e.split(" : ")[0] + " : " + e.split(" : ")[1].split(" (")[0] if " : " in e else e] += 1
    if att:
        lignes += ["", "## Conséquences attendues d'un abord non usuel", "",
                   "Coins forcés alors que la planification les déclare non réalisables par un abord usuel (elle recommande "
                   "l'autre type de coin) : l'os voisin sur le trajet de la lame confirme l'avertissement.", "",
                   "| Type | Cas |", "|---|---|"] + [f"| {k} | {v} |" for k, v in att.most_common()]
        lignes += [""] + [f"* `{r['id']}` : " + " ; ".join(r["attendus"][:3]) for r in resultats if r.get("attendus")]
    lignes += ["", "## Erreurs selon les paramètres", ""]
    for k, c in par_param.items():
        lignes.append(f"* {k} : " + ", ".join(f"{a} {b}" for a, b in c.most_common()))
    mes = defaultdict(list)
    for r in resultats:
        for k, x in r["mesures"].items():
            if isinstance(x, (int, float)):
                mes[k].append(x)
    lignes += ["", "## Mesures (min / médiane / max)", "", "| Mesure | min | médiane | max |", "|---|---|---|---|"]
    lignes += [f"| {k} | {min(x):.3g} | {np.median(x):.3g} | {max(x):.3g} |" for k, x in sorted(mes.items())]
    lignes += ["", "## Exemples de cas en erreur", ""]
    for r in [r for r in resultats if r["erreurs"]][:40]:
        lignes.append(f"* `{r['id']}` : " + " ; ".join(r["erreurs"][:4]))
    Path(chemin).write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return ok, n, cat


def main():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    a.add_argument("cas")
    a.add_argument("--processus", type=int, default=5)
    a.add_argument("--garder", action="store_true")
    a.add_argument("--filtre", default="")
    a.add_argument("--rapport", action="store_true", help="réécrire seulement le rapport à partir de resultats_campagne.jsonl")
    a.add_argument("--reprendre", action="store_true", help="ne calculer que les cas absents de resultats_campagne.jsonl")
    x = a.parse_args()
    if x.rapport:
        res = [json.loads(l_) for l_ in open(Path(x.cas) / "resultats_campagne.jsonl", encoding="utf-8")]
        for r_ in res:
            f_ = Path(x.cas) / r_["id"] / "prescription.json"
            if f_.exists():
                classer_attendus(r_, json.loads(f_.read_text(encoding="utf-8")))
        ok, n, _ = rapport(res, Path(x.cas) / "rapport_campagne.md")
        print(f"{ok}/{n} cas sans erreur ; rapport : {Path(x.cas) / 'rapport_campagne.md'}")
        return
    dossiers = sorted(p for p in Path(x.cas).iterdir() if p.is_dir() and (p / "planification.json").exists() and x.filtre in p.name)
    t0 = time.time()
    sortie = Path(x.cas) / "resultats_campagne.jsonl"
    resultats = []
    if x.reprendre and sortie.exists():                 # reprise après une interruption : cas déjà faits gardés
        resultats = [json.loads(l_) for l_ in open(sortie, encoding="utf-8") if l_.strip()]
        faits = {r_["id"] for r_ in resultats}
        dossiers = [p_ for p_ in dossiers if p_.name not in faits]
        print(f"reprise : {len(faits)} cas déjà faits, {len(dossiers)} à calculer", flush=True)
    with mp.get_context("spawn").Pool(x.processus) as pool, open(sortie, "a" if x.reprendre else "w", encoding="utf-8") as fh:
        for i, r in enumerate(pool.imap_unordered(_travail, [(str(p), x.garder) for p in dossiers]), 1):
            resultats.append(r)
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 10 == 0 or r["erreurs"]:
                print(f"[{i}/{len(dossiers)} {time.time() - t0:.0f} s] {r['id']} : {len(r['erreurs'])} erreur(s)"
                      + (f" — {r['erreurs'][0]}" if r["erreurs"] else ""), flush=True)
    ok, n, cat = rapport(resultats, Path(x.cas) / "rapport_campagne.md")
    print(f"\n{ok}/{n} cas sans erreur en {time.time() - t0:.0f} s ; rapport : {Path(x.cas) / 'rapport_campagne.md'}")
    for k, v in cat.most_common(25):
        print(f"  {v:4d}  {k}")


if __name__ == "__main__":
    main()
