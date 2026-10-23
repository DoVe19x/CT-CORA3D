"""
test_guide.py — vérifie la construction des guides imprimables (etape7_guide.py).

1. Os coudé synthétique (deux cylindres de 8 mm de rayon, coudés de 15° en varus, épiphyses sphériques) avec des
   prescriptions écrites à la main, comme les produit l'onglet CORA (format v2.2) : coin de fermeture, puis coin
   d'ouverture avec une dérotation de 12°. On vérifie : aucune alerte ; STL étanche ; jeu ≥ 0,3 mm et aucune
   interpénétration ; 3 pièces après la coupe des ponts en fermeture (moitiés proximale et distale, pièce du coin), 2 en
   ouverture, chacune retirable sans heurter l'os ni l'autre ; fentes vides sur toute leur largeur (0,8 mm) et dans le
   bon plan, parois présentes de part et d'autre, entrée chanfreinée ; trous de broche vides et coaxiaux aux broches
   prescrites ; butée de profondeur : le haut de chaque tour (mesuré par lancer de rayon sur le STL) est à la même
   distance D (multiple de 5 mm) de la butée de sa fente ; marquages gravés ; verrou de réduction intégré, contrôlé sur
   les fichiers seuls (moitiés dans la position corrigée, axes des broches de verrouillage de guide.json) : la broche
   passe dans les deux oreilles de chaque côté, et un décalage de 0,3 mm la bloque.
   Puis le coin de fermeture avec un os voisin (cylindre de 4 mm de rayon à 1,5 mm de l'os, qui empiète sur le secteur
   de la coque) et une bande de cartilage sous l'extrémité distale de la coque : jeu ≥ 1 mm au voisin, aucune
   interpénétration, coque hors du cartilage, aucune alerte.
2. Os réels segmentés (facultatif : si node et resultats/*/cora_<os>.json existent) : prescriptions exportées par le
   cœur de calcul JavaScript (fémur, coin de fermeture + torsion de test ; tibia valgus, coin de fermeture conseillé),
   guides sans alerte ; tibia valgus, coin d'ouverture forcé (face latérale, fibula sur le trajet de la lame) : guide
   refusé (GuideImpossible : il occuperait l'espace entre le tibia et la fibula).

Usage (depuis code_source/) : ../../.venv/bin/python tests/test_guide.py [--rapide]   (--rapide : sans la partie 2)
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import manifold3d as m3d
import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
import etape7_guide as E7      # noqa: E402
import parametres as P         # noqa: E402

ECHECS = []


def verifier(cond, texte):
    print(("  ok   " if cond else "  ÉCHEC ") + texte)
    if not cond:
        ECHECS.append(texte)


def rotation(axe, angle_deg):
    """Matrice de rotation (Rodrigues) autour de l'axe unitaire, angle en degrés (règle de la main droite)."""
    k = E7.unitaire(axe)
    a = np.radians(angle_deg)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


def autour(point, axe, angle_deg):
    """Transformation 4 × 4 : rotation autour de la droite (point, axe)."""
    T = np.eye(4)
    T[:3, :3] = rotation(axe, angle_deg)
    T[:3, 3] = point - T[:3, :3] @ point
    return T


def appliquer(T, p):
    return T[:3, :3] @ p + T[:3, 3]


def os_coude(theta=15.0, R=8.0, L=90.0):
    """Os coudé de θ en varus (membre droit : X latéral, Y proximal, Z caudal), apex à l'origine."""
    u = np.array([0.0, -1.0, 0.0])                                       # axe proximal, vers distal
    v = np.array([-np.sin(np.radians(theta)), -np.cos(np.radians(theta)), 0.0])   # axe distal (varus : vers médial)
    parts = [E7.cylindre_m(np.zeros(3), -u, 0.0, L, R, 96), E7.cylindre_m(np.zeros(3), v, 0.0, L, R, 96),
             m3d.Manifold.sphere(R, 96), m3d.Manifold.sphere(11.0, 96).translate(tuple(-u * L)),
             m3d.Manifold.sphere(11.0, 96).translate(tuple(v * L))]
    man = m3d.Manifold.batch_boolean(parts, m3d.OpType.Add)
    return man, u, v


def prescription(u, v, theta, kind, R=8.0, derotation=0.0):
    """Prescription v2.2 « à la main » (mêmes conventions que prescription() du cœur JavaScript)."""
    A = np.zeros(3)                                                      # CORA = centre de la section
    c = E7.unitaire(u - v)                                               # côté convexe
    b = E7.unitaire(u + v)                                               # normale du plan bissecteur
    k = E7.unitaire(np.cross(v, u))                                      # axe de correction : fait tourner v vers u
    H = A - c * (R - 2) if kind == "fermeture" else A + c * (R - 2)      # charnière à 2 mm dans la corticale
    plans = [(H, u), (H, v)] if kind == "fermeture" else [(H, b)]
    face = c if kind == "fermeture" else -c
    Tang = autour(H, k, theta)
    if derotation:                                                       # ouverture : autour de l'axe réaligné, après
        T = autour(A, -u, derotation) @ Tang
    else:
        T = Tang
    Ti = np.linalg.inv(T)
    e = 1.2 * 2 * R
    prox = [(A - u * e, -face), (A - u * (e + 10), -face)]
    dist = [(appliquer(Ti, A + u * e), Ti[:3, :3] @ -face), (appliquer(Ti, A + u * (e + 10)), Ti[:3, :3] @ -face)]
    r = lambda x: [round(float(y), 6) for y in x]
    br = [{"fragment": "proximal", "point_axe": r(p), "direction": r(d), "diametre_mm": 1.6} for p, d in prox] + \
         [{"fragment": "distal", "point_axe": r(p), "direction": r(d), "diametre_mm": 1.6} for p, d in dist]
    apres = [{"fragment": x["fragment"], "point_axe": r(appliquer(T, np.array(x["point_axe"])) if x["fragment"] == "distal" else x["point_axe"]),
              "direction": r(T[:3, :3] @ np.array(x["direction"]) if x["fragment"] == "distal" else x["direction"])} for x in br]
    return {
        "schema_version": "v2.2", "os": "tibia", "cote": "droit", "unites": "mm",
        "repere": "X latéral, Y proximal, Z caudal",
        "deformite": {"theta_deg": theta, "cora": r(A)},
        "strategie": {"type_coin": kind, "regle_paley": 1},
        "charniere": {"point": r(H), "direction": r(k), "marge_mm": 2},
        "plans_coupe": [{"point": r(p), "normale": r(n)} for p, n in plans],
        "correction": {"axe": r(k), "angle_deg": theta, "point": r(H), "derotation_deg": derotation,
                       "T_4x4": [r(l) for l in T]},
        "broches_reduction": br, "broches": [br[0], br[2]],
        "guide_reduction": {"broches_apres_correction": apres},
        "guide": {"face_appui": r(face), "axe_os": r(u), "axe_distal": r(v), "centre_section": r(A)},
    }


def volume_dans(guide, outil):
    return float((guide ^ outil).volume())


def verifier_fentes_et_trous(pr, guide_stl, os_man):
    """Fentes : un pavé de 0,76 mm d'épaisseur centré sur chaque plan (au-dessus de l'os, au milieu de la fente) ne
    contient aucune matière ; le même pavé décalé de 1,4 mm dans la paroi en contient. Trous : un cylindre de rayon
    0,87 mm sur l'axe de chaque broche (dans le manchon) est vide ; une couronne de 1,2 à 2,5 mm autour est pleine."""
    g = E7.vers_manifold(*E7.lire_maillage(guide_stl))
    ws = P.GUIDE_LAME_MM + P.GUIDE_JEU_FENTE_MM
    face = np.array(pr["guide"]["face_appui"])
    poly = E7.polydata(*E7.depuis_manifold(os_man))
    K = np.array(pr["guide"]["centre_section"])
    for i, pl in enumerate(pr["plans_coupe"]):
        p, n = np.array(pl["point"]), E7.unitaire(pl["normale"])
        hh = E7.perp(face, n)
        ll = np.cross(n, hh)
        sec = E7.section_os(poly, p, n, hh, ll, K)
        larg = sec["lmax"] - sec["lmin"]
        h0, h1 = sec["hmax"] + 1.0, sec["hmax"] + P.GUIDE_EPAISSEUR_MM + P.GUIDE_GUIDAGE_MM - 1.0
        centre = p + 0.5 * (h0 + h1) * hh + 0.5 * (sec["lmin"] + sec["lmax"]) * ll
        demi = (ws / 2 - 0.02, 0.5 * (h1 - h0), 0.35 * larg)
        vide = volume_dans(g, E7.boite_m(centre, (n, hh, ll), demi))
        paroi = volume_dans(g, E7.boite_m(centre + n * (ws / 2 + 1.0), (n, hh, ll), (0.4, demi[1], demi[2])))
        verifier(vide < 1e-3 and paroi > 0.5 * 0.8 * 2 * demi[1] * 2 * demi[2],
                 f"fente {i + 1} : vide dans le plan prescrit ({vide:.4f} mm³ de matière), paroi pleine à côté ({paroi:.1f} mm³)")
    rh = (P.GUIDE_BROCHE_MM + P.GUIDE_JEU_BROCHE_MM) / 2
    pires = []
    for b in pr["broches_reduction"]:
        a, o = np.array(b["point_axe"]), -E7.unitaire(b["direction"])
        # hauteur du haut de l'os le long de la broche (manchon au-dessus)
        t_os = max(float((q - a) @ o) for q in E7.echantillons(*E7.depuis_manifold(os_man), 1.0)
                   if np.linalg.norm((q - a) - ((q - a) @ o) * o) < 1.0)
        t0, t1 = t_os + P.GUIDE_EPAISSEUR_MM, t_os + P.GUIDE_EPAISSEUR_MM + P.GUIDE_GUIDAGE_MM - 1.0
        trou = volume_dans(g, E7.cylindre_m(a, o, t0, t1, rh - 0.03, 64))
        mur = volume_dans(g, E7.cylindre_m(a, o, t0, t1, rh + 1.6, 64) - E7.cylindre_m(a, o, t0 - 1, t1 + 1, rh + 0.3, 64))
        pires.append((trou, mur))
    verifier(all(t < 1e-3 for t, _ in pires) and all(m > 10 for _, m in pires),
             f"trous de broche vides et coaxiaux (matière dans les trous ≤ {max(t for t, _ in pires):.4f} mm³), manchons pleins "
             f"(≥ {min(m for _, m in pires):.0f} mm³)")


def verifier_butee_et_chanfreins(pr, info, guide_stl, os_man):
    """Butée de profondeur et entrée des fentes, sur le STL seul. Haut de chaque tour : lancer de rayon vertical (le long
    de hh) sur la bande plate de part et d'autre de la fente, au milieu de sa longueur ; butée : la charnière, ou la
    corticale opposée moins le dépassement (coupe complète). Entrée : au ras du haut, la fente est ouverte sur ws + 2c."""
    g = E7.vers_manifold(*E7.lire_maillage(guide_stl))
    ws, ch = P.GUIDE_LAME_MM + P.GUIDE_JEU_FENTE_MM, P.GUIDE_CHANFREIN_MM
    face, K = np.array(pr["guide"]["face_appui"]), np.array(pr["guide"]["centre_section"])
    H, kdir = np.array(pr["charniere"]["point"]), E7.unitaire(pr["charniere"]["direction"])
    poly = E7.polydata(*E7.depuis_manifold(os_man))
    D = info["butee"]["profondeur_lame_mm"]
    ecarts, ouvert, plein = [], [], []
    for i, pl in enumerate(pr["plans_coupe"]):
        p, n = np.array(pl["point"]), E7.unitaire(pl["normale"])
        ll = E7.unitaire(kdir - (kdir @ n) * n)                  # fente parallèle à la charnière
        hh = np.cross(ll, n)
        hh = hh if hh @ face > 0 else -hh
        ll = np.cross(n, hh)
        sec = E7.section_os(poly, p, n, hh, ll, K)
        prof = info["guide_coupe"]["fentes"][i]["profondeur"]
        h_stop = sec["hmin"] - P.GUIDE_DEPASSEMENT_MM if prof == "complete" else float((H - p) @ hh)
        lc = 0.5 * (sec["lmin"] + sec["lmax"])
        for cote in (-1, 1):
            q = p + cote * (ws / 2 + ch + 0.45) * n + lc * ll
            hits = g.ray_cast(tuple(q + 80 * hh), tuple(q - 10 * hh))
            if hits:
                ecarts.append(abs(float((np.array(hits[0].position) - p) @ hh) - h_stop - D))
        h_top = h_stop + D
        L = 0.5 * (sec["lmax"] - sec["lmin"])
        ouvert.append(float((g ^ E7.boite_m(p + (h_top - 0.06) * hh + lc * ll, (n, hh, ll), (ws / 2 + ch - 0.15, 0.05, L))).volume()))
        plein.append(float((g ^ E7.boite_m(p + (h_top - 0.3) * hh + lc * ll + (ws / 2 + ch + 0.5) * n, (n, hh, ll), (0.2, 0.2, L))).volume()))
    verifier(info["butee"]["mode"] == "automatique" and abs(D / P.GUIDE_PAS_PROFONDEUR_MM - round(D / P.GUIDE_PAS_PROFONDEUR_MM)) < 1e-6
             and len({f["profondeur_lame_mm"] for f in info["guide_coupe"]["fentes"]}) == 1,
             f"butée : profondeur de lame {D:g} mm, multiple de {P.GUIDE_PAS_PROFONDEUR_MM:g} mm, la même pour toutes les fentes")
    verifier(len(ecarts) == 2 * len(pr["plans_coupe"]) and max(ecarts) < 0.1,
             f"haut des tours à D de la butée (lancer de rayon sur le STL : écart ≤ {max(ecarts or [99]):.3f} mm)")
    verifier(max(ouvert) < 1e-3 and min(plein) > 0.05,
             f"entrée des fentes chanfreinée : ouverte sur {ws + 2 * ch:.1f} mm au ras du haut ({max(ouvert):.4f} mm³ de matière), "
             "paroi pleine juste à côté")


def verifier_verrou(info, dossier, decale=0.3):
    """Verrou de réduction, sur les fichiers seuls : moitiés dans la position corrigée (verrou_*.bin) et axes des broches
    de verrouillage (guide.json). La broche (Ø des broches, du fond du trou borgne à 20 mm au-dessus) ne touche aucune
    matière ; décalée de 0,3 mm perpendiculairement à son axe (2 directions), elle bute sur une oreille."""
    V = info["verrou_reduction"]
    verifier(V["construit"] and len(V["cotes"]) == 2, f"verrou de réduction des deux côtés ({', '.join(V.get('cotes') or [])})"
             + ("" if V["construit"] else f" — {V.get('raison')}"))
    if not V["construit"]:
        return
    moities = E7.vers_manifold(*E7.lire_maillage(dossier / "verrou_proximal.bin")) + \
        E7.vers_manifold(*E7.lire_maillage(dossier / "verrou_distal.bin"))
    rp = P.GUIDE_BROCHE_MM / 2
    passe, bloque = [], []
    for pt in V["points"]:
        a, o = np.array(pt["axe_point"]), E7.unitaire(pt["direction"])
        passe.append(float((moities ^ E7.cylindre_m(a, o, 0.05, 25.0, rp - 0.01, 64)).volume()))
        e1 = E7.perp([1.0, 0, 0] if abs(o[0]) < 0.9 else [0, 1.0, 0], o)
        for e in (e1, np.cross(o, e1)):
            bloque.append(float((moities ^ E7.cylindre_m(a + decale * e, o, 0.05, 25.0, rp - 0.01, 64)).volume()))
    verifier(max(passe) < 1e-3 and min(bloque) > 1e-3,
             f"broche de verrouillage : passe dans les oreilles ({max(passe):.4f} mm³ de matière), bloquée par un décalage de "
             f"{decale} mm (≥ {min(bloque):.3f} mm³)")
    sens = V["sensibilite"]
    rot = [k for k in sens if k.startswith("rotation")]
    tol = V["tolerances"]["rotations_detectees_deg"]
    verifier(all(sens[k] for k in rot) and all(v_ for k, v_ in sens.items() if "le long des broches" not in k)
             and max(tol.values()) <= E7.MARGE_VERROU * E7.TOL_VERROU_DEG,
             "sensibilité : 1° de rotation (3 axes) et 0,3 mm de translation perpendiculaire aux broches bloquent la broche "
             f"(test booléen, broche enfoncée jusqu'au fond) ; rotations détectées dès {', '.join(f'{v_}° ({k_})' for k_, v_ in tol.items())}")
    # (laisser les moitiés sur leurs broches pendant la correction est une option du mode opératoire, proposée seulement
    # si ce trajet est libre : il est rapporté, pas exigé)
    verifier(V["remise_en_place_libre"] and V["ecart_moities_apres_mm"] >= 0.1 and (V["interpenetration_os_corrige_mm3"] or 0) <= 0.05,
             f"moitiés remises en place sans se toucher (écart {V['ecart_moities_apres_mm']} mm), os corrigé respecté "
             f"({V['interpenetration_os_corrige_mm3']} mm³) ; trajet de la correction moitiés en place : "
             f"{'libre' if V['trajet_libre'] else 'non (les retirer avant)'}")


def test_synthetique():
    print("1. Os coudé synthétique (15° de varus), prescriptions écrites à la main")
    os_man, u, v = os_coude()
    vv, ff = E7.depuis_manifold(os_man)
    for kind, derot in (("fermeture", 0.0), ("ouverture", 12.0)):
        pr = prescription(u, v, 15.0, kind, derotation=derot)
        dossier = Path(tempfile.mkdtemp(prefix=f"guide_{kind}_"))
        t0 = time.time()
        info = E7.generer(pr, (vv, ff), dossier, journal=lambda *_: None, image=False)
        C = info["guide_coupe"]
        print(f" {kind}{f' + dérotation {derot:g}°' if derot else ''} ({time.time() - t0:.1f} s)")
        verifier(not info["alertes"], f"aucune alerte{' : ' + '; '.join(info['alertes']) if info['alertes'] else ''}")
        verifier(C["etanche_stl"], "STL du guide de coupe étanche")
        verifier(C["jeu_minimal_mesure_mm"] >= P.GUIDE_JEU_MM - 0.05 and (C["volume_interpenetration_mm3"] or 0) < 0.01,
                 f"jeu minimal {C['jeu_minimal_mesure_mm']} mm (demandé {P.GUIDE_JEU_MM}), interpénétration "
                 f"{C['volume_interpenetration_mm3']} mm³")
        n_att = 3 if kind == "fermeture" else 2
        verifier(C["moities_apres_coupe_des_ponts"] == n_att and all(x["libre"] for x in C["retrait"].values()),
                 f"{n_att} pièces après la coupe des ponts, retrait libre ({', '.join(f'{k} {x['points_bloques']}/{x['points_testes']} bloqués, '
                                                                                   f'{x['heurte_autre_moitie_mm3']} mm³' for k, x in C['retrait'].items())}), "
                 f"ordre : {' puis '.join(C['ordre_retrait'])}")
        attendu = "distale" if kind == "fermeture" else "proximale"
        verifier(C["ordre_retrait"][0] == attendu, f"la moitié {attendu} sort en premier (elle s'éloigne de l'autre)")
        verifier(abs(C["angle_paires_broches_deg"] - E7.angle_deg(-np.array(pr["guide"]["face_appui"]),
                                                                   pr["broches_reduction"][2]["direction"])) < 0.01,
                 f"angle entre les paires de broches = celui de la prescription ({C['angle_paires_broches_deg']}°)")
        verifier(len(C["marquages"]) == 2 and {m["texte"][0] for m in C["marquages"]} == {"P", "D"},
                 f"marquages gravés : {', '.join(m['texte'] for m in C['marquages'])}")
        verifier_fentes_et_trous(pr, dossier / "guide_coupe.stl", os_man)
        verifier_butee_et_chanfreins(pr, info, dossier / "guide_coupe.stl", os_man)
        verifier_verrou(info, dossier)
        shutil.rmtree(dossier, ignore_errors=True)


def test_voisin_cartilage():
    print(" fermeture + os voisin + cartilage")
    os_man, u, v = os_coude()
    os_man = os_man.refine_to_length(1.0)              # sommets tous les ≈ 1 mm (comme un os réel) : carte du cartilage
    vv, ff = E7.depuis_manifold(os_man)
    pr = prescription(u, v, 15.0, "fermeture")
    # os voisin : cylindre parallèle au segment proximal, côté caudo-latéral (60° de la face d'appui latérale), à 1,5 mm
    # de la surface de l'os : la coque (± 75° autour de la face) le recouvrirait
    a = np.array([13.5 * np.cos(np.radians(60)), 2.0, 13.5 * np.sin(np.radians(60))])
    vois_v, vois_f = E7.depuis_manifold(E7.cylindre_m(a, u, 0.0, 62.0, 4.0, 64))
    # cartilage : bande du segment distal entre 36 et 48 mm de l'apex (sous la fin de la coque distale)
    s_v = vv @ v
    art = ((s_v > 36) & (s_v < 48)).astype(np.uint8) * 255
    dossier = Path(tempfile.mkdtemp(prefix="guide_voisin_"))
    t0 = time.time()
    info = E7.generer(pr, (vv, ff), dossier, journal=lambda *_: None, image=False,
                      voisins=[("fibula", vois_v, vois_f)], articulaire=art)
    vc = info["voisins_et_cartilage"]
    print(f"  ({time.time() - t0:.1f} s)")
    verifier(not info["alertes"], f"aucune alerte{' : ' + '; '.join(info['alertes']) if info['alertes'] else ''}")
    r = vc["voisins"]["fibula"]
    verifier(r["distance_guide_mm"] >= P.GUIDE_JEU_VOISIN_MM - 0.1 and (r["interpenetration_mm3"] or 0) < 0.01
             and "fibula" in vc["voisins_evites_guide_coupe"],
             f"guide de coupe à {r['distance_guide_mm']} mm de l'os voisin (demandé {P.GUIDE_JEU_VOISIN_MM}), "
             f"interpénétration {r['interpenetration_mm3']} mm³")
    verifier(vc["cartilage"]["distance_guide_mm"] >= 1.0 and vc["noeuds_coque_retires_cartilage"] > 0,
             f"coque hors du cartilage ({vc['cartilage']['distance_guide_mm']} mm ; "
             f"{vc['noeuds_coque_retires_cartilage']} nœuds de coque retirés)")
    C = info["guide_coupe"]
    verifier(C["etanche_stl"] and all(x["libre"] for x in C["retrait"].values())
             and min(a_["surface_mm2"] for a_ in C["appui_moities"].values()) >= 100,
             "STL étanche, retrait libre, appui de chaque moitié ≥ 100 mm² ("
             + ", ".join(f"{k} {a_['surface_mm2']:.0f} mm²" for k, a_ in C["appui_moities"].items()) + ")")
    verifier_verrou(info, dossier)
    shutil.rmtree(dossier, ignore_errors=True)


EXPORT_JS = r"""
import fs from 'fs'; import path from 'path';
const [ROOT, OUT] = process.argv.slice(2);
const C = await import(path.join(ROOT, 'code_source/cora/app/cora_simple.js'));
const RES = path.join(ROOT, 'resultats');
const lire = (f) => { const b = fs.readFileSync(f), ab = b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); const [nv, nf] = new Uint32Array(ab, 0, 2); return { pos: new Float32Array(ab, 8, nv * 3).slice(), idx: new Uint32Array(ab, 8 + nv * 12, nf * 3).slice() }; };
const faits = [];
// tibia valgus : fermeture (face médiale, conseillée) ; ouverture forcée : face latérale, fibula sur le trajet de la lame
for (const [bone, cas, kind, tau] of [['femur', 'femur-varus-procurvatum', 'fermeture', 15], ['tibia', 'tibia-valgus-aucun', 'fermeture', 0], ['tibia', 'tibia-valgus-aucun', 'ouverture', 0]]) {
  const serie = fs.readdirSync(RES).find((s) => { try { return JSON.parse(fs.readFileSync(path.join(RES, s, `cora_${bone}.json`))).complet; } catch (e) { return false; } });
  if (!serie) continue;
  const json = JSON.parse(fs.readFileSync(path.join(RES, serie, `cora_${bone}.json`)));
  const meshes = Object.fromEntries(Object.entries(json.maillages).map(([n, f]) => [n, lire(path.join(RES, serie, f))]));
  const P = C.planifier(C.modeleReel(json, meshes), C.casDe(cas), { reference: 'sain', torsion: tau });
  const d = path.join(OUT, `${bone}_${kind}`); fs.mkdirSync(d, { recursive: true });
  fs.writeFileSync(path.join(d, 'prescription.json'), JSON.stringify(C.prescription(P, kind)));
  const pos = Float32Array.from(P.pos[bone]), idx = Uint32Array.from(meshes[bone].idx);
  fs.writeFileSync(path.join(d, 'os.bin'), Buffer.concat([Buffer.from(new Uint32Array([pos.length / 3, idx.length / 3]).buffer), Buffer.from(pos.buffer), Buffer.from(idx.buffer)]));
  faits.push(`${bone}_${kind} (${serie})`);
}
console.log(faits.join(', '));
"""


def test_reel():
    print("\n2. Os réels segmentés (prescriptions exportées par le cœur de calcul JavaScript)")
    node = shutil.which("node")
    if not node or not list(P.RESULTATS.glob("*/cora_*.json")):
        print("  (ignoré : node ou résultats de l'étape 6 absents)")
        return
    tmp = Path(tempfile.mkdtemp(prefix="guides_reels_"))
    script = tmp / "export.mjs"
    script.write_text(EXPORT_JS, encoding="utf-8")
    r = subprocess.run([node, str(script), str(P.RACINE), str(tmp)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        verifier(False, f"export des prescriptions : {r.stderr.strip()[-300:]}")
        return
    print(f"  cas exportés : {r.stdout.strip() or 'aucun'}")
    for d in sorted(x for x in tmp.iterdir() if x.is_dir()):
        t0 = time.time()
        st = json.loads((d / "prescription.json").read_text(encoding="utf-8"))["strategie"]
        if st.get("abord_non_usuel") and st.get("voisin_sur_lame"):
            # face du coin derrière la fibula : le guide occuperait l'espace entre les deux os ; refus motivé attendu
            try:
                E7.generer(d / "prescription.json", d / "os.bin", d / "sortie", journal=lambda *_: None, image=False)
                verifier(False, f"{d.name} : guide construit alors que {st['voisin_sur_lame']} est sur le trajet de la lame")
            except E7.GuideImpossible as exc:
                verifier("fibula" in str(exc) and "conseillé" in str(exc),
                         f"{d.name} : guide refusé ({st['voisin_sur_lame']} sur le trajet de la lame) : « {str(exc)[:110]}… »")
            continue
        info = E7.generer(d / "prescription.json", d / "os.bin", d / "sortie", journal=lambda *_: None, image=False)
        C, V = info["guide_coupe"], info["verrou_reduction"]
        verifier(not info["alertes"] and C["etanche_stl"] and C["moities_apres_coupe_des_ponts"] == C["pieces_attendues"]
                 and V["construit"],
                 f"{d.name} ({time.time() - t0:.0f} s) : jeu {C['jeu_minimal_mesure_mm']} mm, appui {C['surface_appui_mm2']:.0f} mm², "
                 f"{C['moities_apres_coupe_des_ponts']} pièces, profondeur de lame {info['butee']['profondeur_lame_mm']:g} mm, "
                 f"verrou {', '.join(V.get('cotes') or []) or 'non construit'}"
                 + (f" — alertes : {'; '.join(info['alertes'])}" if info["alertes"] else ""))
        if V["construit"]:
            verifier_verrou(info, d / "sortie")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    t = time.time()
    test_synthetique()
    test_voisin_cartilage()
    if "--rapide" not in sys.argv:
        test_reel()
    print(f"\n{len(ECHECS)} échec(s) en {time.time() - t:.0f} s" if ECHECS else f"\nTous les contrôles sont passés ({time.time() - t:.0f} s).")
    sys.exit(1 if ECHECS else 0)
