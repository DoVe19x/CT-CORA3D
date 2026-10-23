#!/usr/bin/env python3
"""
serveur.py — application « CT-CORA3D » : un serveur local et une interface dans une fenêtre native.

Rôle      : sert l'interface (dossier interface/ : page d'accueil à deux onglets, ct/ = segmentation, cora/ =
            planification CORA 3D), l'affiche dans une fenêtre d'application (fenetre.py ; à défaut Chrome / Edge)
            et exécute à la demande le programme de code_source/ : lecture DICOM,
            segmentation, identification, maillages, contrôle, puis repères du fémur et du tibia pour CORA (étape 6).
            L'onglet « Segmentation CT » montre le scanner en coupes avec les os en couleur, et les os en 3D ; on peut y
            corriger le résultat (renommer un os, séparer un segment par des points), comme dans 3D Slicer. L'onglet
            « Planification CORA » lit les os segmentés (/api/cora/…) ou garde l'os fictif du modèle.
Lancement : double-clic sur « CT-CORA3D.app » (macOS) ou « Lancer sur Windows.bat », ou
            ../../.venv/bin/python serveur.py [--port N] [--sans-fenetre] [--dossier CHEMIN]
Résultats : CT-CORA3D/resultats/<série>/ (les mêmes fichiers que lancer_tout.py).
Arrêt     : automatique à la fermeture de la fenêtre (après le calcul en cours), ou bouton « Quitter ».

Les calculs tournent dans le fil principal (VTK l'exige sur macOS) ; le serveur HTTP tourne à côté et ne fait que
lire : coupes (numpy + PNG), maillages, fichiers.
"""
import argparse
import base64
import contextlib
import io
import json
import os
import queue
import re
import socket
import socketserver
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np

if getattr(sys, "frozen", False):      # application autonome (PyInstaller) : interface et données dans le paquet
    ICI = Path(sys._MEIPASS) / "application"
    RACINE = Path(sys._MEIPASS)
else:
    ICI = Path(__file__).resolve().parent
    RACINE = ICI.parent
sys.path.insert(0, str(RACINE / "code_source"))

import etape1_lecture_dicom as E1      # noqa: E402
import etape2_segmentation as E2       # noqa: E402
import etape3_identification as E3     # noqa: E402
import etape4_maillage as E4           # noqa: E402
import etape5_controle as E5           # noqa: E402
import etape6_reperes as E6            # noqa: E402
import lancer_tout as LT               # noqa: E402
import parametres as P                 # noqa: E402

INTERFACE = ICI / "interface"
ETAPES = ["lecture DICOM", "seuillage et croissance de région", "identification des os", "maillages STL",
          "contrôle et rapport", "repères pour CORA (fémur, tibia)"]
# réglages modifiables depuis l'interface, avec leurs bornes (garde-fous contre une saisie absurde)
BORNES = {"SEUIL_OS_HU": (100, 700), "SIGMA_LISSAGE_MM": (0.0, 1.0), "VARIATION_SEUIL_HU": (10, 150),
          "TRIANGLES_MAX": (10_000, 1_000_000), "RAYON_FERMETURE_MM": (0.0, 3.0)}
CHOIX = {"SYSTEME_COORDONNEES": ("LPS", "RAS")}
NOMS_PROPOSES = ["femur", "tibia", "fibula", "patella", "fabelles", "talus", "calcaneus", "tarse", "metatarses",
                 "phalanges", "bassin", "objet", "autre"]

FILE = queue.Queue()                    # demandes de calcul, traitées une à une dans le fil principal
VERROU = threading.Lock()
TRAVAIL = {"etat": "libre", "action": "", "etape": -1, "etapes": [], "journal": [], "erreur": None, "debut": None,
           "duree": None, "version": 0, "resultat": None}
ETAT = {"dossier": str(P.DOSSIER_DICOM), "series": [], "courant": None}
COURANT = {}                            # série ouverte : serie, volume, seg, bilan, rapport, dossier, version
CACHE = {}                              # maillages déjà convertis
VIE = {"dernier_signe": time.time() + 120.0}
FENETRE = {"native": False, "fermee": False}  # fenêtre native (fenetre.py) : arrêt dès qu'elle est fermée


# =============================================================================== utilitaires
class Journal(io.TextIOBase):
    """Recueille les messages des étapes (print) pour l'interface, et les recopie à la console."""
    def write(self, s):
        with VERROU:
            for ligne in s.splitlines():
                if ligne.strip():
                    TRAVAIL["journal"].append(ligne)
        if sys.__stdout__ is not None:
            with contextlib.suppress(Exception):
                sys.__stdout__.write(s)
        return len(s)


def etat(**k):
    with VERROU:
        TRAVAIL.update(k)


@contextlib.contextmanager
def sans_mise_en_veille():
    """Pendant un calcul (segmentation, guides : jusqu'à quelques minutes), l'ordinateur ne se met pas en veille par
    inactivité : sinon le calcul s'arrête avec lui et reprend au réveil (mesuré : 55 s de calcul étalées sur une heure).
    macOS : caffeinate -i (assertion système, levée à la fin du calcul) ; Windows : SetThreadExecutionState sur le fil
    du calcul. Sans effet si c'est impossible ; la veille demandée par l'utilisateur (capot fermé) reste possible."""
    garde = None
    try:
        if sys.platform == "darwin":
            garde = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # CONTINUOUS | SYSTEM_REQUIRED
    except (OSError, AttributeError):
        garde = None
    try:
        yield
    finally:
        if garde is not None:
            garde.terminate()
        elif os.name == "nt":
            with contextlib.suppress(OSError, AttributeError):
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)            # CONTINUOUS : retour à la normale


def journal(texte):
    print(texte, flush=True)


def borne(nom, x):
    lo, hi = BORNES[nom]
    v = min(max(float(x), lo), hi)
    return int(v) if isinstance(getattr(P, nom), int) else v


def serie_par_nom(nom):
    for s in ETAT["series"]:
        if s.nom == nom:
            return s
    raise ValueError(f"série inconnue : {nom}")


def resume_serie(s):
    i = s.infos
    d = i.get("date", "")
    return {"nom": s.nom, "description": i.get("description", ""), "patient": i.get("patient", ""),
            "date": f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else d, "coupes": i.get("nb_fichiers"),
            "pixel_mm": i.get("pixel_mm"), "epaisseur_mm": i.get("epaisseur_mm"), "modalite": i.get("modalite"),
            "dossier": i.get("dossier"), "resultats": (P.RESULTATS / s.nom / "rapport.json").exists()}


def lire_graines(dossier):
    return LT.lire_graines(dossier)


def ecrire_graines(dossier, points):
    Path(dossier).mkdir(parents=True, exist_ok=True)
    (Path(dossier) / "graines.json").write_text(json.dumps(
        {"explication": "points nommés par l'utilisateur (coordonnées du scanner, mm) : réappliqués à chaque calcul",
         "points": points}, ensure_ascii=False, indent=1), encoding="utf-8")


# =============================================================================== calculs (fil principal)
def inventorier(d):
    dossier = Path(d.get("chemin") or ETAT["dossier"]).expanduser()
    if not dossier.is_dir():
        raise ValueError(f"dossier introuvable : {dossier}")
    journal(f"Inventaire DICOM de {dossier} …")
    series = E1.inventaire(dossier)
    for s in series:
        journal("  " + E1.decrire(s))
    if not series:
        journal("  aucune série DICOM trouvée dans ce dossier")
    with VERROU:
        ETAT["dossier"], ETAT["series"] = str(dossier), series


def ouvrir(d):
    """Charge le volume d'une série (et sa segmentation déjà enregistrée, s'il y en a une)."""
    serie = serie_par_nom(d["nom"])
    etat(etape=0)
    journal(f"Ouverture de {serie.nom}")
    volume = E1.charger(serie, journal)
    dossier = P.RESULTATS / serie.nom
    seg = bilan = rapport = None
    f = dossier / "segmentation.seg.nrrd"
    if f.exists() and (dossier / "rapport.json").exists():
        try:
            journal("  relecture de la segmentation enregistrée…")
            lab, origine, _, noms = E4.lire_seg_nrrd(f)
            seg = E2.depuis_fichier(volume, lab, origine, noms)
            rapport = json.loads((dossier / "rapport.json").read_text(encoding="utf-8"))
            seg.raisons = {s["etiquette"]: s.get("raison", "") for s in rapport.get("segments", [])}
            seg.reperes = rapport.get("reperes", {})
            bilan = rapport.get("os", {})
        except Exception as exc:
            journal(f"  ⚠ segmentation enregistrée illisible ({exc}) : relancez « Segmenter »")
            seg = bilan = rapport = None
    with VERROU:
        COURANT.clear()
        COURANT.update({"serie": serie, "volume": volume, "seg": seg, "bilan": bilan, "rapport": rapport,
                        "dossier": dossier, "version": TRAVAIL["version"] + 1})
        TRAVAIL["version"] += 1
        CACHE.clear()


def segmenter(d):
    """Toute la chaîne (étapes 1 à 5) sur la série ouverte, avec les réglages de l'interface."""
    if not COURANT:
        raise ValueError("ouvrez d'abord une série")
    anciens = {k: getattr(P, k) for k in list(BORNES) + list(CHOIX) + ["IMAGES_CONTROLE"]}
    try:
        for k, v in (d.get("reglages") or {}).items():
            if k in BORNES:
                setattr(P, k, borne(k, v))
            elif k in CHOIX and v in CHOIX[k]:
                setattr(P, k, v)
        P.IMAGES_CONTROLE = bool(d.get("images", True))
        rapport, volume, seg, bilan = LT.traiter(COURANT["serie"], avec_sensibilite=bool(d.get("controle", True)),
                                                 journal=journal, etape=lambda n: etat(etape=n - 1),
                                                 volume=COURANT["volume"])
        rapport["parametres_application"] = {k: getattr(P, k) for k in anciens}
    finally:
        for k, v in anciens.items():
            setattr(P, k, v)
    with VERROU:
        COURANT.update({"seg": seg, "bilan": bilan, "rapport": rapport})
        TRAVAIL["version"] += 1
        CACHE.clear()


def point_dans(seg, e, kji=None):
    """Un voxel de l'étiquette e : le point cliqué s'il y est, sinon le voxel le plus proche du centre."""
    if kji is not None:
        q = np.clip(np.rint(np.array(kji, float) - seg.origine_kji).astype(int), 0, np.array(seg.etiquettes.shape) - 1)
        if seg.etiquettes[tuple(q)] == e:
            return q
    pts = np.argwhere(seg.etiquettes == e)
    c = pts.mean(0)
    return pts[np.argmin(((pts - c) ** 2).sum(1))]


def apres_modification(seg, avant, journal_=journal):
    """Remaille seulement les fichiers touchés par une correction, puis met à jour contrôle et rapport."""
    apres = E4.exports(seg)
    touches = {n for n in set(avant) | set(apres) if avant.get(n) != apres.get(n)}
    dossier = COURANT["dossier"]
    journal_(f"  fichiers à refaire : {', '.join(sorted(touches)) or 'aucun'}")
    bilan = E4.exporter(seg, dossier, journal_, seulement=touches, precedent=COURANT.get("bilan") or {})
    rapport = E5.controler(seg, COURANT["volume"], bilan, dossier, time.time(), avec_sensibilite=True,
                           avec_images=True, journal=journal_, seulement=touches)
    # fémur ou tibia modifié (ou fibula, qui sert au tibia) : repères CORA refaits
    refaire = {n for n in touches if E4.base(n) in P.CORA_OS}
    refaire |= {"tibia" + n[len("fibula"):] for n in touches if E4.base(n) == "fibula"}
    if refaire:
        journal_("  repères CORA refaits (étape 6)")
        for f in dossier.glob("cora_*"):
            if any(f.name.startswith(f"cora_{n}.") or f.name.startswith(f"cora_{n}_fibula") for n in refaire):
                f.unlink()
        cora = {n: E6.traiter_os(dossier, n, journal_) for n in sorted(refaire) if (dossier / f"{n}.stl").exists()}
        E6.ajouter_au_rapport(dossier, cora)
        cas = E6.choisir_cible(dossier)
        journal_(f"  os à planifier : {cas['cible'] or 'aucun'} ({cas['raison']})")
    with VERROU:
        COURANT.update({"bilan": bilan, "rapport": rapport})
        TRAVAIL["version"] += 1
        CACHE.clear()


def nommer(d):
    """Renomme un segment (nom vide = « autre » : ni exporté, ni renommé automatiquement au prochain calcul)."""
    seg = COURANT.get("seg")
    if seg is None:
        raise ValueError("pas de segmentation : lancez d'abord « Segmenter »")
    e, nom = int(d["etiquette"]), (d.get("nom") or "autre")
    if nom not in NOMS_PROPOSES:
        raise ValueError(f"nom inconnu : {nom}")
    cote = d.get("cote") if d.get("cote") in ("gauche", "droit") else ""
    complet = nom + (f"_{cote}" if cote and nom not in ("objet", "autre", "bassin") else "")
    avant = E4.exports(seg)
    q = point_dans(seg, e, d.get("kji"))
    lps = [round(float(x), 3) for x in seg.vers_lps(q)[0]]
    seg.noms[e] = complet
    seg.raisons[e] = "nommé par l'utilisateur"
    # graines.json : le point remplace ceux qui tombaient dans le même segment
    points = [p for p in lire_graines(COURANT["dossier"]) if etiquette_de(seg, p) != e]
    points.append({"nom": complet, "position": lps, "systeme": "LPS"})
    ecrire_graines(COURANT["dossier"], points)
    journal(f"Segment {e} renommé « {E4.libelle(complet)} » (point enregistré dans graines.json)")
    apres_modification(seg, avant)


def etiquette_de(seg, point):
    lps = np.array(point["position"], float)
    if str(point.get("systeme", "LPS")).upper() == "RAS":
        lps = lps * [-1, -1, 1]
    q = np.rint(seg.vers_indices(lps)[0]).astype(int)
    if np.any(q < 0) or np.any(q >= seg.etiquettes.shape):
        return 0
    return int(seg.etiquettes[tuple(q)])


def separer(d):
    """Sépare un segment avec des points nommés (au moins deux noms différents)."""
    seg = COURANT.get("seg")
    if seg is None:
        raise ValueError("pas de segmentation : lancez d'abord « Segmenter »")
    e = int(d["etiquette"])
    par_nom = {}
    for p in d.get("points") or []:
        if p.get("nom") not in NOMS_PROPOSES:
            raise ValueError(f"nom inconnu : {p.get('nom')}")
        q = np.rint(np.array(p["kji"], float) - seg.origine_kji).astype(int)
        if np.any(q < 0) or np.any(q >= seg.etiquettes.shape) or seg.etiquettes[tuple(q)] != e:
            raise ValueError("chaque point doit être placé dans le segment sélectionné")
        par_nom.setdefault(p["nom"], []).append(q)
    if len(par_nom) < 2:
        raise ValueError("il faut au moins deux points de noms différents")
    avant = E4.exports(seg)
    nouveaux = E3.separer_par_points(seg, e, par_nom, journal)
    for f, n in nouveaux.items():
        seg.noms[f] = n
        seg.raisons[f] = "séparé et nommé par l'utilisateur"
    points = [p for p in lire_graines(COURANT["dossier"]) if etiquette_de(seg, p) not in nouveaux]
    for n, qs in par_nom.items():
        for q in qs:
            points.append({"nom": n, "position": [round(float(x), 3) for x in seg.vers_lps(q)[0]], "systeme": "LPS"})
    ecrire_graines(COURANT["dossier"], points)
    apres_modification(seg, avant)


def oublier_graines(d):
    """Supprime graines.json : le prochain calcul sera entièrement automatique."""
    if COURANT:
        f = COURANT["dossier"] / "graines.json"
        if f.exists():
            f.unlink()
        journal("graines.json supprimé : le prochain « Segmenter » sera entièrement automatique")


def dossier_guide(d):
    """Dossier des guides : resultats/<série>/guide_<os>_<coin> (os segmenté), resultats/_os_fictif/… (os fictif)."""
    pr = d["prescription"]
    kind, os_ = pr["strategie"]["type_coin"], pr.get("os")
    if kind not in ("fermeture", "ouverture") or os_ not in ("femur", "tibia"):
        raise ValueError("prescription invalide (os ou type de coin)")
    if d.get("serie"):
        return dossier_serie(d["serie"]) / f"guide_{nom_os_valide(d.get('nom_os') or os_)}_{kind}"
    return P.RESULTATS / "_os_fictif" / f"guide_{os_}_{kind}"


def guide(d):
    """Étape 7 (onglet CORA) : guide de coupe et guide de réduction pour l'os planifié envoyé par l'interface."""
    pr = d["prescription"]
    v = np.frombuffer(base64.b64decode(d["sommets"]), np.float32).reshape(-1, 3).astype(float)
    f = np.frombuffer(base64.b64decode(d["triangles"]), np.uint32).reshape(-1, 3).astype(np.int64)
    if not len(v) or not len(f) or f.max() >= len(v):
        raise ValueError("maillage de l'os invalide")
    try:                                         # importé ici : l'application démarre même sans manifold3d
        import etape7_guide as E7
    except ImportError as exc:
        raise RuntimeError(f"bibliothèque manquante pour les guides ({exc.name}) : relancer l'installation "
                           "(requirements.txt), par exemple en supprimant l'environnement local de CT-CORA3D") from exc
    dossier = dossier_guide(d)
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "prescription.json").write_text(json.dumps(pr, ensure_ascii=False, indent=2), encoding="utf-8")
    E7.ecrire_stl(dossier / "os_planifie.stl", v, f, "CT-CORA3D os planifie")
    E7.ecrire_bin(dossier / "os_planifie.bin", v, f)
    # os voisins à éviter (fibula ; rotule et fabelles du fémur), dans le repère de l'os planifié, et cartilage articulaire
    # (1 octet par sommet de l'os) : envoyés par l'interface quand ils sont connus (os fictif, fibula segmentée…)
    voisins = []
    for x in d.get("voisins") or []:
        vv = np.frombuffer(base64.b64decode(x["sommets"]), np.float32).reshape(-1, 3).astype(float)
        ff = np.frombuffer(base64.b64decode(x["triangles"]), np.uint32).reshape(-1, 3).astype(np.int64)
        if len(vv) and len(ff) and ff.max() < len(vv):
            voisins.append((str(x.get("nom", "voisin")), vv, ff))
            E7.ecrire_bin(dossier / f"voisin_{x.get('nom', 'voisin')}.bin", vv, ff)
    art = np.frombuffer(base64.b64decode(d["articulaire"]), np.uint8) if d.get("articulaire") else None
    if art is not None and len(art) != len(v):
        art = None
    journal(f"Guides pour {pr.get('os')} ({pr['strategie']['type_coin']}) -> {dossier}"
            + (f" ; os voisins : {', '.join(n for n, _, _ in voisins)}" if voisins else "")
            + (" ; cartilage articulaire connu" if art is not None else ""))
    info = E7.generer(pr, (v, f), dossier, journal=journal, voisins=voisins, articulaire=art)
    etat(resultat={"dossier": dossier.relative_to(P.RESULTATS).as_posix(), "alertes": info["alertes"]})


ACTIONS = {"inventaire": ("Recherche des séries DICOM", inventorier), "ouvrir": ("Ouverture de la série", ouvrir),
           "segmenter": ("Segmentation", segmenter), "nommer": ("Correction du nom", nommer),
           "separer": ("Séparation d'un segment", separer), "oublier": ("Effacement des points", oublier_graines),
           "guide": ("Construction des guides (étape 7)", guide)}


def executer(d):
    titre, f = ACTIONS[d["action"]]
    etat(etat="en_cours", action=titre, etape=-1 if d["action"] != "segmenter" else 0,
         etapes=ETAPES if d["action"] == "segmenter" else [], journal=[], erreur=None, debut=time.time(), duree=None,
         resultat=None)
    try:
        with sans_mise_en_veille(), contextlib.redirect_stdout(Journal()):
            f(d)
        etat(etat="termine", duree=round(time.time() - TRAVAIL["debut"], 1))
    except Exception as exc:                             # message lisible pour l'interface, détail au journal
        with VERROU:
            TRAVAIL["journal"].extend(traceback.format_exc().splitlines()[-6:])
        etat(etat="erreur", erreur=str(exc) or exc.__class__.__name__)


def boucle_calcul():
    while True:
        d = FILE.get()
        if d is None:
            return
        executer(d)


# =============================================================================== lecture (fils HTTP)
def couleur_etiquettes(seg, selection=None):
    """Table de couleurs (RGBA, 0-255) par étiquette : couleur de l'os nommé ; segments non nommés en tons neutres."""
    n = int(seg.etiquettes.max()) + 1
    t = np.zeros((n, 4), np.float32)
    for e, nom in seg.noms.items():
        if e >= n:
            continue
        if nom and E4.base(nom) not in ("autre",):
            t[e, :3] = E4.couleur(nom)
            t[e, 3] = 0.45 if E4.base(nom) != "objet" else 0.25
        else:
            h = (e * 0.618) % 1.0                        # tons neutres distincts pour les segments non nommés
            t[e, :3] = (0.55 + 0.25 * np.cos(2 * np.pi * h), 0.55 + 0.2 * np.cos(2 * np.pi * (h + 0.33)), 0.62)
            t[e, 3] = 0.30
    if selection and 0 < selection < n:
        t[selection, 3] = 0.75
    return t


def coupe_png(plan, index, ww, wl, avec_seg, selection):
    """Une coupe du volume (axiale a, coronale c, sagittale s) en PNG, os en couleur. Axes de l'image : axiale
    (lignes j, colonnes i) ; coronale (k vers le haut, i) ; sagittale (k vers le haut, j)."""
    from PIL import Image
    v, seg = COURANT["volume"], COURANT.get("seg")
    nk, nj, ni = v.hu.shape
    index = int(index)
    if plan == "a":
        index = min(max(index, 0), nk - 1)
        img = v.hu[index]
    elif plan == "c":
        index = min(max(index, 0), nj - 1)
        img = v.hu[:, index, :]
    else:
        index = min(max(index, 0), ni - 1)
        img = v.hu[:, :, index]
    g = np.clip((img.astype(np.float32) - (wl - ww / 2)) / max(ww, 1) * 255, 0, 255)
    rgb = np.repeat(g[..., None], 3, axis=2)
    if avec_seg and seg is not None:
        o, s = np.array(seg.origine_kji), seg.etiquettes.shape
        lab = np.zeros(img.shape, np.uint16)
        if plan == "a" and o[0] <= index < o[0] + s[0]:
            lab[o[1]:o[1] + s[1], o[2]:o[2] + s[2]] = seg.etiquettes[index - o[0]]
        elif plan == "c" and o[1] <= index < o[1] + s[1]:
            lab[o[0]:o[0] + s[0], o[2]:o[2] + s[2]] = seg.etiquettes[:, index - o[1], :]
        elif plan == "s" and o[2] <= index < o[2] + s[2]:
            lab[o[0]:o[0] + s[0], o[1]:o[1] + s[1]] = seg.etiquettes[:, :, index - o[2]]
        if lab.any():
            t = couleur_etiquettes(seg, selection)
            lab = np.minimum(lab, len(t) - 1)
            a = t[lab, 3:4]
            rgb = rgb * (1 - a) + t[lab, :3] * 255 * a
            bord = (lab != np.roll(lab, 1, 0)) | (lab != np.roll(lab, 1, 1))      # contour plus marqué
            bord &= lab > 0
            rgb[bord] = rgb[bord] * 0.3 + t[lab[bord], :3] * 255 * 0.7
    if plan in ("c", "s"):
        rgb = rgb[::-1]                                  # k croissant vers le haut de l'écran
    tampon = io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8)).save(tampon, "PNG", compress_level=1)
    return tampon.getvalue()


def info_point(k=None, j=None, i=None, lps=None):
    """Densité et os sous un voxel (k, j, i), ou au plus près d'un point LPS (clic 3D : à moins de 3 mm)."""
    v, seg = COURANT["volume"], COURANT.get("seg")
    if lps is not None:
        q = np.clip(np.rint(v.vers_indices(lps)[0]).astype(int), 0, np.array(v.hu.shape) - 1)
    else:
        q = np.clip([int(k), int(j), int(i)], 0, np.array(v.hu.shape) - 1)
    e = 0
    if seg is not None:
        r = q - np.array(seg.origine_kji)
        esp = np.array(seg.espacement)
        rr = np.ceil(3.0 / esp).astype(int) if lps is not None else np.zeros(3, int)
        lo, hi = np.maximum(r - rr, 0), np.minimum(r + rr + 1, seg.etiquettes.shape)
        if np.all(hi > lo):
            bloc = seg.etiquettes[tuple(slice(a, b) for a, b in zip(lo, hi))]
            if bloc.any():
                pts = np.argwhere(bloc > 0)
                proche = pts[np.argmin((((pts + lo - r) * esp) ** 2).sum(1))] + lo
                e = int(seg.etiquettes[tuple(proche)])
    nom = seg.noms.get(e, "") if seg is not None and e else ""
    return {"kji": q.tolist(), "hu": int(v.hu[tuple(q)]), "lps": [round(float(x), 2) for x in v.vers_lps(q)[0]],
            "etiquette": e, "nom": nom, "libelle": E4.libelle(nom) if e else ""}


def maillage_binaire(sommets, faces):
    """Format compact pour l'interface : nb sommets, nb triangles (uint32), sommets (float32), triangles (uint32)."""
    return (np.array([len(sommets), len(faces)], np.uint32).tobytes() + np.asarray(sommets, np.float32).tobytes()
            + np.asarray(faces, np.uint32).tobytes())


def maillage_os(nom):
    """STL exporté d'un os (sommets fusionnés pour un ombrage lisse)."""
    import trimesh
    f = COURANT["dossier"] / f"{nom}.stl"
    if not f.is_file():
        raise FileNotFoundError(f"{nom}.stl absent")
    cle = ("stl", str(f), f.stat().st_mtime)
    if cle not in CACHE:
        m = trimesh.load(f, process=True)
        CACHE[cle] = maillage_binaire(m.vertices, m.faces)
    return CACHE[cle]


def maillage_segment(e):
    """Maillage rapide d'un segment (non nommé, ou pas encore exporté) : surface du segment, sans remplissage, sur
    une grille deux fois plus grossière ; uniquement pour l'affichage."""
    import vtk_leger as vtk
    from scipy import ndimage as ndi
    from vtkmodules.util import numpy_support as vns
    seg = COURANT["seg"]
    cle = ("seg", TRAVAIL["version"], int(e))
    if cle in CACHE:
        return CACHE[cle]
    m = seg.etiquettes == int(e)
    if not m.any():
        raise FileNotFoundError(f"segment {e} absent")
    b = E2.boite_englobante(m)
    lo = np.array([max(s.start - 2, 0) for s in b])
    sous = m[tuple(slice(int(a), s.stop + 2) for a, s in zip(lo, b))][::2, ::2, ::2]
    g = ndi.gaussian_filter(np.pad(sous, 1).astype(np.float32), 0.7)
    im = vtk.vtkImageData()
    im.SetDimensions(g.shape[2], g.shape[1], g.shape[0])
    im.GetPointData().SetScalars(vns.numpy_to_vtk(g.ravel(), deep=True))
    fe = vtk.vtkFlyingEdges3D()
    fe.SetInputData(im)
    fe.SetValue(0, 0.5)
    fe.Update()
    pd = fe.GetOutput()
    if pd.GetNumberOfPolys() > 40_000:
        dec = vtk.vtkQuadricDecimation()
        dec.SetInputData(pd)
        dec.SetTargetReduction(1 - 40_000 / pd.GetNumberOfPolys())
        dec.Update()
        pd = dec.GetOutput()
    p = vns.vtk_to_numpy(pd.GetPoints().GetData()).astype(np.float64)
    faces = vns.vtk_to_numpy(pd.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    ijk = (p - 1) * 2 + lo[::-1]                      # grille grossière rembourrée -> indices de la zone recadrée
    lps = ijk @ seg.affine[:3, :3].T + seg.affine[:3, 3]
    CACHE[cle] = maillage_binaire(lps, faces)
    return CACHE[cle]


def description():
    """Tout ce que l'interface affiche de la série ouverte."""
    if not COURANT:
        return None
    v, seg = COURANT["volume"], COURANT.get("seg")
    out = {"nom": COURANT["serie"].nom, "infos": v.infos, "dimensions": list(v.hu.shape),
           "espacement": [float(x) for x in v.espacement], "affine": v.affine.tolist(),
           "avertissements": v.avertissements, "segments": [], "reperes": {}, "fichiers": [], "version": TRAVAIL["version"],
           "graines": lire_graines(COURANT["dossier"])}
    if seg is not None:
        cle_t = ("tailles", TRAVAIL["version"])          # comptage des voxels : seulement si la segmentation a changé
        if cle_t not in CACHE:
            CACHE[cle_t] = np.bincount(seg.etiquettes.ravel())
        taille = CACHE[cle_t]
        bilan = COURANT.get("bilan") or {}
        cle = ("centres", TRAVAIL["version"])
        if cle not in CACHE:                             # centre de chaque segment (indices du volume complet)
            from scipy import ndimage as ndi
            ids = [e for e in range(1, len(taille)) if taille[e]]
            centres = ndi.center_of_mass(np.ones_like(seg.etiquettes, dtype=np.uint8), seg.etiquettes, ids) if ids else []
            CACHE[cle] = {e: [round(float(c) + o, 1) for c, o in zip(cc, seg.origine_kji)] for e, cc in zip(ids, centres)}
        centres = CACHE[cle]
        fichier_de = {e: nom for nom, m in bilan.items() for e in m.get("etiquettes", []) if E4.base(nom) != "tarse"
                      or "talus" not in bilan}
        for e, n in seg.noms.items():
            if e >= len(taille) or taille[e] == 0:
                continue
            fic = fichier_de.get(e) if n and E4.base(n) not in ("objet", "autre") else None
            m = bilan.get(fic, {}) if fic else {}
            out["segments"].append({
                "etiquette": int(e), "nom": n, "libelle": E4.libelle(n) if n else f"os non identifié {e}",
                "couleur": list(couleur_etiquettes(seg)[e, :3]), "volume_cm3": round(float(taille[e]) * seg.volume_voxel / 1000, 2),
                "raison": seg.raisons.get(e, ""), "fichier": fic, "etanche": m.get("etanche"), "euler": m.get("euler"),
                "centre_kji": centres.get(e)})
        ordre = {n: i for i, n in enumerate(NOMS_PROPOSES)}
        out["segments"].sort(key=lambda s: (ordre.get(E4.base(s["nom"]) or "zz", 99), -s["volume_cm3"]))
        out["reperes"] = seg.reperes
        out["os"] = bilan
        out["zone"] = {"origine": list(seg.origine_kji), "forme": list(seg.etiquettes.shape)}
    d = COURANT["dossier"]
    if d.exists():
        out["fichiers"] = sorted(p.name for p in d.iterdir() if p.is_file())
        # état de l'étape 6 pour chaque fémur / tibia : l'onglet 1 ne propose « CORA → » que pour un os complet
        out["cora"] = {}
        for nom in E6.fichiers_cora(d):
            r = cora_a_jour(d, nom)
            if r is not None:
                out["cora"][nom] = {"complet": bool(r.get("complet")), "raison": r.get("raison", ""), "cote": r.get("cote")}
        out["cas"] = cas_serie(d) if out["cora"] else None
    return out


# =============================================================================== API CORA
VERROU_CORA = threading.Lock()                  # une analyse de repères à la fois (calcul court, numpy seulement)


def dossier_serie(nom):
    """Dossier de résultats d'une série, à partir de son nom (pas de chemin : protège des « ../ »)."""
    if not nom or "/" in nom or "\\" in nom or nom.startswith("."):
        raise ValueError("nom de série invalide")
    d = P.RESULTATS / nom
    if not d.is_dir():
        raise FileNotFoundError(f"série inconnue : {nom}")
    return d


def cora_a_jour(d, nom):
    """cora_<nom>.json existe et correspond au STL actuel (même date de modification)."""
    f, stl = d / f"cora_{nom}.json", d / f"{nom}.stl"
    if not f.exists() or not stl.exists():
        return None
    try:
        r = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if abs(float(r.get("stl_modifie", 0)) - stl.stat().st_mtime) > 1e-3:
        return None
    if r.get("complet") and any(not (d / n).exists() for n in (r.get("maillages") or {}).values()):
        return None
    return r


def nom_os_valide(nom):
    if not re.fullmatch(r"(femur|tibia)(_gauche|_droit)?", nom or ""):
        raise ValueError("os inconnu (femur, tibia, femur_gauche…)")
    return nom


def cora_analyse(serie, nom, forcer=False):
    d = dossier_serie(serie)
    nom = nom_os_valide(nom)
    with VERROU_CORA:
        r = None if forcer else cora_a_jour(d, nom)
        if r is None:
            r = E6.traiter_os(d, nom, journal=lambda *_: None)
    return r


def cas_serie(d):
    """cora_cas.json à jour (refait si un cora_<os>.json est plus récent, ou s'il manque)."""
    f = d / "cora_cas.json"
    jsons = [d / f"cora_{n}.json" for n in E6.fichiers_cora(d)]
    if not f.exists() or any(j.exists() and j.stat().st_mtime > f.stat().st_mtime for j in jsons) \
            or any(not j.exists() for j in jsons):
        with VERROU_CORA:
            for n in E6.fichiers_cora(d):
                if cora_a_jour(d, n) is None:
                    E6.traiter_os(d, n, journal=lambda *_: None)
            return E6.choisir_cible(d)
    return json.loads(f.read_text(encoding="utf-8"))


def cas_courant(serie=None):
    """Le cas à planifier : la série demandée, sinon celle ouverte dans l'onglet 1, sinon la dernière segmentée."""
    if serie:
        d = dossier_serie(serie)
    elif COURANT and (COURANT["dossier"] / "rapport.json").exists():
        d = COURANT["dossier"]
    else:
        faites = [x for x in P.RESULTATS.iterdir() if (x / "rapport.json").exists()] if P.RESULTATS.is_dir() else []
        if not faites:
            return {"serie": None, "cible": None, "candidats": [], "raison": "aucune série segmentée : ouvrez un dossier "
                    "DICOM et lancez « Segmenter » dans l'onglet 1"}
        d = max(faites, key=lambda x: (x / "rapport.json").stat().st_mtime)
    cas = dict(cas_serie(d))
    # série demandée explicitement : la question « est-ce la série ouverte dans l'onglet 1 ? » ne se pose pas
    cas["ouverte"] = None if serie else (bool(COURANT) and COURANT["dossier"] == d)
    return cas


def dossier_guide_lu(rel):
    """Dossier de guides désigné par l'interface (« <série>/guide_<os>_<coin> ») : vérifié, sans « ../ »."""
    if not re.fullmatch(r"[A-Za-z0-9_][^/\\]*/guide_(femur|tibia)(_gauche|_droit)?_(fermeture|ouverture)", rel or ""):
        raise ValueError("dossier de guide invalide")
    d = (P.RESULTATS / rel).resolve()
    if not d.is_relative_to(P.RESULTATS.resolve()) or not d.is_dir():
        raise FileNotFoundError(f"guides absents : {rel}")
    return d


def cora_liste():
    """Tous les fémurs et tibias segmentés (un par série et par côté) avec leur état pour la planification."""
    out = []
    if not P.RESULTATS.is_dir():
        return out
    for d in sorted(x for x in P.RESULTATS.iterdir() if x.is_dir()):
        for nom in E6.fichiers_cora(d):
            r = cora_a_jour(d, nom)
            e = {"serie": d.name, "os": nom, "etat": "a_calculer"}
            if r is not None:
                e.update(etat="pret" if r.get("complet") else "incomplet", raison=r.get("raison", ""),
                         cote=r.get("cote"), longueur_mm=r.get("longueur_mm"))
            out.append(e)
    return out


# =============================================================================== serveur HTTP
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml", ".stl": "model/stl",
         ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".nrrd": "application/octet-stream",
         ".pdf": "application/pdf"}


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "CT-CORA3D"

    def log_message(self, *_):
        pass

    def envoyer(self, code, corps, type_="application/json; charset=utf-8", entetes=None):
        if isinstance(corps, (dict, list)) or corps is None:
            corps = json.dumps(corps, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)).encode("utf-8")
        elif isinstance(corps, str):
            corps = corps.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corps)

    def erreur(self, code, message):
        self.envoyer(code, {"erreur": message})

    def lire_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        VIE["dernier_signe"] = time.time()
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        chemin = unquote(url.path)
        try:
            if chemin == "/api/etat":
                with VERROU:
                    t = dict(TRAVAIL, journal=TRAVAIL["journal"][-60:])
                    series = [resume_serie(s) for s in ETAT["series"]]
                return self.envoyer(200, {"travail": t, "dossier": ETAT["dossier"], "series": series,
                                          "ouverte": COURANT["serie"].nom if COURANT else None})
            if chemin == "/api/config":
                return self.envoyer(200, {"reglages": {k: getattr(P, k) for k in list(BORNES) + list(CHOIX)},
                                          "bornes": BORNES, "choix": CHOIX, "noms": NOMS_PROPOSES,
                                          "libelles": {n: P.NOMS_OS.get(n, n) for n in NOMS_PROPOSES},
                                          "couleurs": P.COULEURS, "etapes": ETAPES})
            if chemin == "/api/serie":
                return self.envoyer(200, description())
            if chemin == "/api/coupe":
                if not COURANT:
                    return self.erreur(404, "aucune série ouverte")
                png = coupe_png(q.get("plan", "a"), q.get("i", 0), float(q.get("ww", 2000)), float(q.get("wl", 500)),
                                q.get("seg", "1") == "1", int(q.get("sel", 0)))
                return self.envoyer(200, png, "image/png")
            if chemin == "/api/point":
                if "x" in q:
                    return self.envoyer(200, info_point(lps=[float(q["x"]), float(q["y"]), float(q["z"])]))
                return self.envoyer(200, info_point(q["k"], q["j"], q["i"]))
            if chemin == "/api/maillage":
                if "os" in q:
                    return self.envoyer(200, maillage_os(re.sub(r"[^a-z_]", "", q["os"])), "application/octet-stream")
                return self.envoyer(200, maillage_segment(int(q["e"])), "application/octet-stream")
            if chemin == "/api/cora/cas":
                return self.envoyer(200, cas_courant(q.get("serie")))
            if chemin == "/api/cora/liste":
                return self.envoyer(200, {"os": cora_liste(), "resultats": str(P.RESULTATS)})
            if chemin == "/api/cora/os":
                return self.envoyer(200, cora_analyse(q.get("serie"), q.get("os"), q.get("forcer") == "1"))
            if chemin == "/api/cora/maillage":                   # maillage dans le repère de l'os (binaire)
                d = dossier_serie(q.get("serie"))
                quoi = re.sub(r"[^a-z_]", "", q.get("quoi", ""))
                f = d / f"cora_{quoi}.bin"
                if not f.is_file():
                    return self.erreur(404, f"maillage absent : {f.name}")
                return self.envoyer(200, f.read_bytes(), "application/octet-stream")
            if chemin == "/api/cora/guide":                      # guide.json d'un dossier de guides
                d = dossier_guide_lu(q.get("dossier"))
                f = d / "guide.json"
                if not f.is_file():
                    return self.erreur(404, "guide.json absent")
                r = json.loads(f.read_text(encoding="utf-8"))
                r["dossier"] = q.get("dossier")
                r["disponibles"] = sorted(x.name for x in d.iterdir() if x.suffix in (".stl", ".bin", ".json", ".png", ".svg", ".pdf"))
                return self.envoyer(200, r)
            if chemin == "/api/cora/guide/fichier":              # un fichier d'un dossier de guides (affichage, téléchargement)
                d = dossier_guide_lu(q.get("dossier"))
                nom = q.get("f", "")
                if not re.fullmatch(r"[a-z0-9_]+\.(stl|bin|json|png|svg|pdf)", nom) or not (d / nom).is_file():
                    return self.erreur(404, f"fichier absent : {nom}")
                ent = {"Content-Disposition": f'attachment; filename="{nom}"'} if q.get("telecharger") else None
                return self.envoyer(200, (d / nom).read_bytes(), TYPES.get((d / nom).suffix, "application/octet-stream"), ent)
            if chemin.startswith("/res/"):                       # fichiers de la série ouverte : /res/<fichier>
                fichier = chemin[len("/res/"):]
                if not COURANT or "/" in fichier or "\\" in fichier or fichier.startswith("."):
                    return self.erreur(400, "nom de fichier invalide")
                f = COURANT["dossier"] / fichier
                if not f.is_file():
                    return self.erreur(404, f"fichier absent : {fichier}")
                ent = {"Content-Disposition": f'attachment; filename="{f.name}"'} if q.get("telecharger") else None
                return self.envoyer(200, f.read_bytes(), TYPES.get(f.suffix.lower(), "application/octet-stream"), ent)
            f = (INTERFACE / (chemin.lstrip("/") or "index.html")).resolve()
            if f.is_dir():                                       # /ct/ -> /ct/index.html
                f = f / "index.html"
            if not f.is_relative_to(INTERFACE.resolve()) or not f.is_file():
                return self.erreur(404, "introuvable")
            return self.envoyer(200, f.read_bytes(), TYPES.get(f.suffix.lower(), "application/octet-stream"))
        except FileNotFoundError as exc:
            return self.erreur(404, str(exc))
        except Exception as exc:
            return self.erreur(500, str(exc))

    def do_POST(self):
        VIE["dernier_signe"] = time.time()
        chemin = urlparse(self.path).path
        try:
            if chemin == "/api/ping":
                return self.envoyer(200, {"ok": True})
            if chemin == "/api/action":
                d = self.lire_json()
                if d.get("action") not in ACTIONS:
                    return self.erreur(400, "action inconnue")
                with VERROU:
                    occupe = TRAVAIL["etat"] == "en_cours"
                if occupe:
                    return self.erreur(409, "un calcul est déjà en cours")
                etat(etat="en_cours", action=ACTIONS[d["action"]][0], journal=[], erreur=None)
                FILE.put(d)
                return self.envoyer(200, {"ok": True})
            if chemin == "/api/choisir_dossier":
                return self.envoyer(200, {"chemin": choisir_dossier()})
            if chemin == "/api/montrer":                       # ouvre le dossier des résultats dans le Finder / l'Explorateur
                corps = self.lire_json()
                serie = corps.get("serie")
                if corps.get("dossier_guide"):
                    d = dossier_guide_lu(corps["dossier_guide"])
                else:
                    d = dossier_serie(serie) if serie else (COURANT["dossier"] if COURANT else P.RESULTATS)
                d.mkdir(parents=True, exist_ok=True)
                montrer(d)
                return self.envoyer(200, {"ok": True})
            if chemin == "/api/quitter":
                self.envoyer(200, {"ok": True})
                threading.Thread(target=arreter, daemon=True).start()
                return None
            return self.erreur(404, "introuvable")
        except Exception as exc:
            return self.erreur(500, str(exc))


def choisir_dossier():
    """Fenêtre de choix de dossier du système (le serveur tourne sur l'ordinateur de l'utilisateur)."""
    if sys.platform == "darwin":
        r = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "Dossier contenant les DICOM")'],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.stdout.strip() or None
    if os.name == "nt":
        # sortie en UTF-8 (chemins accentués : « Scanner été ») ; boîte posée sur une fenêtre invisible « au premier
        # plan » : lancée par un serveur sans fenêtre, elle s'ouvrirait sinon derrière l'application
        script = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; "
                  "$p = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; ShowInTaskbar = $false}; "
                  "$d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = 'Dossier contenant les DICOM'; "
                  "if ($d.ShowDialog($p) -eq 'OK') { $d.SelectedPath }; $p.Dispose()")
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script], capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW)   # serveur sans console : pas de fenêtre noire
        return r.stdout.strip() or None
    return None


def montrer(dossier):
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(dossier)])
    elif os.name == "nt":
        os.startfile(str(dossier))                       # noqa: S606 (dossier local de l'utilisateur)
    else:
        subprocess.Popen(["xdg-open", str(dossier)])


SERVEUR = {}


class Serveur(ThreadingHTTPServer):
    """Serveur HTTP local, sans la résolution inverse du nom (socket.getfqdn) que HTTPServer fait au démarrage : sur
    macOS, elle passe par mDNS ; pour une application que le système ne connaît pas encore (réseau local), elle reste
    bloquée ≈ 30 s. Le nom ne sert à rien ici (127.0.0.1)."""
    daemon_threads = True

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


def arreter():
    time.sleep(0.3)
    FILE.put(None)
    if "httpd" in SERVEUR:
        SERVEUR["httpd"].shutdown()


def veille():
    """Arrêt automatique quand la fenêtre est fermée et qu'aucun calcul ne tourne. Fenêtre native : dès que son
    processus se termine ; fenêtre de navigateur : plus aucun signe de vie (ping) depuis une minute."""
    while True:
        time.sleep(2)
        with VERROU:
            occupe = TRAVAIL["etat"] == "en_cours"
        fermee = FENETRE["fermee"] if FENETRE["native"] else time.time() - VIE["dernier_signe"] > 60
        if not occupe and fermee:
            arreter()
            return


def ouvrir_fenetre(url):
    """Fenêtre native de l'application (fenetre.py, pywebview) ; si elle est impossible sur cet ordinateur
    (code 3 : pywebview absente), fenêtre de navigateur comme avant."""
    try:
        p = subprocess.Popen([sys.executable, str(ICI / "fenetre.py"), url])
    except OSError:
        return ouvrir_navigateur(url)
    FENETRE["native"] = True

    def suivre():
        if p.wait() == 3:
            print("fenêtre native indisponible : ouverture dans le navigateur", flush=True)
            VIE["dernier_signe"] = time.time() + 120.0
            FENETRE["native"] = False
            ouvrir_navigateur(url)
        else:
            FENETRE["fermee"] = True

    threading.Thread(target=suivre, daemon=True).start()


def suivre_parent():
    """Application autonome : la fenêtre est le processus parent ; elle garde ouverte l'entrée standard de ce serveur
    (tube), qui se ferme quand elle se termine, quelle qu'en soit la cause. Arrêt après le calcul en cours (veille)."""
    FENETRE["native"] = True

    def lire():
        try:
            while os.read(0, 4096):
                pass
        except OSError:
            pass
        FENETRE["fermee"] = True

    threading.Thread(target=lire, daemon=True).start()


def ouvrir_navigateur(url):
    """Secours : fenêtre d'application Chrome / Edge (sans barre d'adresse) ; sinon le navigateur par défaut."""
    taille = "--window-size=1680,1020"
    if sys.platform == "darwin":
        for nav in ("Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium"):
            if subprocess.run(["open", "-na", nav, "--args", f"--app={url}", taille],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return
    elif os.name == "nt":
        pf, pf86, local = (os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"))
        for exe in (rf"{pf86}\Microsoft\Edge\Application\msedge.exe", rf"{pf}\Microsoft\Edge\Application\msedge.exe",
                    rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Google\Chrome\Application\chrome.exe",
                    rf"{local}\Google\Chrome\Application\chrome.exe"):
            if os.path.isfile(exe):
                subprocess.Popen([exe, f"--app={url}", taille])
                return
    webbrowser.open(url)


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv=None):
    a = argparse.ArgumentParser(description="CT-CORA3D : segmentation CT et planification CORA, application locale")
    a.add_argument("--port", type=int, default=0)
    a.add_argument("--sans-fenetre", action="store_true", help="ne pas ouvrir la fenêtre de l'application")
    a.add_argument("--dossier", default=str(P.DOSSIER_DICOM), help="dossier DICOM fouillé au démarrage")
    a.add_argument("--sans-veille", action="store_true", help="ne pas s'arrêter seul (essais, ligne de commande)")
    a.add_argument("--resultats", help=f"dossier des résultats (défaut : {P.RESULTATS})")
    a.add_argument("--suivre-parent", action="store_true",
                   help="application autonome : s'arrêter quand la fenêtre (processus parent) se termine")
    x = a.parse_args(argv)
    if x.resultats:
        P.RESULTATS = Path(x.resultats).expanduser().resolve()
    if x.suivre_parent:
        suivre_parent()
    port = x.port or port_libre()
    httpd = Serveur(("127.0.0.1", port), Gestionnaire)
    SERVEUR["httpd"] = httpd
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if not x.sans_veille:
        threading.Thread(target=veille, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"CT-CORA3D : {url}  (fermer la fenêtre de l'application pour quitter)", flush=True)
    FILE.put({"action": "inventaire", "chemin": x.dossier})
    if not x.sans_fenetre:
        ouvrir_fenetre(url)
    boucle_calcul()                              # fil principal : les calculs
    httpd.server_close()


if __name__ == "__main__":
    main()
