#!/usr/bin/env python3
"""
fenetre.py — fenêtre native de l'application « CT-CORA3D » (une application de bureau, pas un onglet de navigateur).

Rôle      : affiche l'interface servie par serveur.py dans une fenêtre du système, grâce à pywebview : moteur WebKit
            sur macOS (celui de Safari), WebView2 sur Windows (celui d'Edge). La fenêtre a son nom et son icône dans le
            Dock / la barre des tâches, ses menus en français et ses boîtes « Enregistrer sous » pour les exports.
            Les fichiers ouverts depuis l'interface (aperçus PNG, rapports) s'ouvrent dans une petite fenêtre de
            l'application ; les liens vers internet (références DOI) dans le navigateur habituel.
Lancement : par serveur.py (python fenetre.py URL) ; ne s'utilise pas seule.
            python fenetre.py --verifier   : code 0 si pywebview est disponible (lanceurs)
            python fenetre.py --installer  : installe pywebview pour cet ordinateur (lanceurs, premier lancement)
pywebview : installée hors OneDrive, dans un dossier propre à l'ordinateur et à la version de Python (macOS
            ~/Library/Application Support/CTCORA3D/fenetre-py3XX, Windows %LOCALAPPDATA%\\CTCORA3D\\fenetre-py3XX) :
            l'environnement Python du projet (PMD2/.venv) n'est pas modifié.
Sortie    : 0 = fenêtre fermée par l'utilisateur ou serveur arrêté ; 3 = fenêtre native impossible (pywebview absent
            ou inutilisable) : serveur.py ouvre alors une fenêtre Chrome / Edge, comme avant.
"""
import argparse
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import unquote, urlparse

NOM = "CT-CORA3D"
AUTONOME = getattr(sys, "frozen", False)  # application autonome (PyInstaller) : icônes dans le paquet
ICI = Path(sys._MEIPASS) / "application" if AUTONOME else Path(__file__).resolve().parent
INDISPONIBLE = 3
FOND = "#0a1015"                       # fond de l'interface (thème sombre) : pas d'éclair blanc à l'ouverture
TAILLE = (1680, 1020)                  # taille de la première ouverture (ensuite : la dernière taille utilisée)


def dossier_local():
    """Dossier propre à cet ordinateur, hors OneDrive (rien n'y est synchronisé)."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CTCORA3D"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "CTCORA3D"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "ctcora3d"


# pywebview est compilée pour une version de Python : un dossier par version. Ajouté en fin de chemin : si
# l'environnement Python contient déjà pywebview (requirements.txt), c'est cette version-là qui est utilisée.
BIBLIO = dossier_local() / f"fenetre-py{sys.version_info.major}{sys.version_info.minor}"
if not AUTONOME:                       # application autonome : pywebview est dans le paquet
    sys.path.append(str(BIBLIO))
REGLAGES = dossier_local() / "fenetre.json"

FRANCAIS = {
    "global.quitConfirmation": "Voulez-vous vraiment quitter ?", "global.ok": "OK", "global.quit": "Quitter",
    "global.cancel": "Annuler", "global.saveFile": "Enregistrer le fichier",
    "cocoa.menu.about": "À propos de", "cocoa.menu.services": "Services", "cocoa.menu.view": "Présentation",
    "cocoa.menu.edit": "Édition", "cocoa.menu.hide": "Masquer", "cocoa.menu.hideOthers": "Masquer les autres",
    "cocoa.menu.showAll": "Tout afficher", "cocoa.menu.quit": "Quitter",
    "cocoa.menu.fullscreen": "Passer en mode plein écran", "cocoa.menu.cut": "Couper", "cocoa.menu.copy": "Copier",
    "cocoa.menu.paste": "Coller", "cocoa.menu.selectAll": "Tout sélectionner",
    "windows.fileFilter.allFiles": "Tous les fichiers", "windows.fileFilter.otherFiles": "Autres types de fichiers",
}


# page affichée pendant que le serveur de l'application autonome charge ses bibliothèques (quelques secondes)
STYLE = ("html,body{margin:0;height:100%;background:#0a1015;color:#cfe3ee;font:15px -apple-system,system-ui,sans-serif}"
         "body{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:0 24px}"
         "h1{margin:0;font-size:22px;font-weight:600;letter-spacing:.06em}p{margin:0;color:#7f97a5;text-align:center}"
         ".r{width:26px;height:26px;border:3px solid #22384a;border-top-color:#4fb3d9;border-radius:50%;"
         "animation:t 1s linear infinite}@keyframes t{to{transform:rotate(360deg)}}")
ACCUEIL = (f'<!doctype html><html lang="fr"><meta charset="utf-8"><style>{STYLE}</style>'
           f'<h1>{NOM}</h1><div class="r"></div><p>Démarrage des calculs…</p></html>')


JOURNAL_LISIBLE = ("~/Library/Logs/CTCORA3D.log" if sys.platform == "darwin" else
                   r"%LOCALAPPDATA%\CTCORA3D\CTCORA3D.log" if os.name == "nt" else "~/.local/state/ctcora3d/CTCORA3D.log")


def page_erreur(message):
    return (f'<!doctype html><html lang="fr"><meta charset="utf-8"><style>{STYLE}</style><h1>{NOM}</h1>'
            f'<p>{message}</p><p>Détails : {JOURNAL_LISIBLE}</p></html>')


# =============================================================================== installation (lanceurs)
def presente():
    importlib.invalidate_caches()
    return importlib.util.find_spec("webview") is not None


def installer():
    """Installe pywebview dans BIBLIO (une fois par ordinateur et par version de Python ; internet nécessaire)."""
    if presente():
        return 0
    BIBLIO.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
           "--upgrade", "--target", str(BIBLIO), "pywebview>=5.0"]
    for _ in range(2):                 # proxy_tools (dépendance) est livrée en sources : 1er essai parfois en échec
        if subprocess.run(cmd).returncode == 0 and presente():
            print(f"pywebview installée dans {BIBLIO}", flush=True)
            return 0
    print("pywebview n'a pas pu être installée : l'application s'ouvrira dans Chrome / Edge.", flush=True)
    return 1


# =============================================================================== fenêtre
def identite_systeme():
    """Nom et icône de l'application pour le système, avant de créer la fenêtre (sinon : « Python »)."""
    if sys.platform == "darwin":
        import AppKit                  # pyobjc, installée avec pywebview
        # nom affiché dans la barre des menus, le Dock et Cmd+Tab (lu par macOS au démarrage de l'application)
        AppKit.NSBundle.mainBundle().infoDictionary()["CFBundleName"] = NOM
        # macOS ajoute de lui-même Dictée, Emoji et Plein écran à chaque installation des menus par pywebview :
        # doublons. Réglages en mémoire seulement (registerDefaults n'écrit rien sur le disque).
        AppKit.NSUserDefaults.standardUserDefaults().registerDefaults_({
            "NSDisabledDictationMenuItem": True, "NSDisabledCharacterPaletteMenuItem": True,
            "NSFullScreenMenuItemEverywhere": False})
        return str(ICI / "icone" / "icone.icns")
    if os.name == "nt":
        import ctypes
        # groupe propre dans la barre des tâches (avec l'icône de la fenêtre) au lieu de celui de python.exe
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("be.ecam.pmd2.ctcora3d")
        return str(ICI / "icone" / "icone.ico")
    return str(ICI / "icone" / "icone.png")


def menus_sans_doublons():
    """macOS : l'entrée « Passer en mode plein écran » apparaît deux fois dans le menu Présentation de pywebview 6
    (doublon ajouté par AppKit) ; on retire les entrées répétées (même titre, même action). Fil principal."""
    import AppKit
    for m in AppKit.NSApp.mainMenu().itemArray():
        sous_menu, vues = m.submenu(), set()
        for item in list(sous_menu.itemArray()) if sous_menu else []:
            cle = (str(item.title()), str(item.action()))
            if item.isSeparatorItem():
                continue
            if cle in vues:
                sous_menu.removeItem_(item)
            vues.add(cle)


def lire_taille(ecran):
    """Dernière taille de la fenêtre (fenetre.json), limitée à l'écran."""
    l, h = TAILLE
    try:
        r = json.loads(REGLAGES.read_text(encoding="utf-8"))
        l, h = int(r["largeur"]), int(r["hauteur"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if ecran:
        l, h = min(l, ecran.width - 40), min(h, ecran.height - 60)
    return max(l, 1000), max(h, 650)


def ecrire_taille(fenetre):
    try:
        REGLAGES.parent.mkdir(parents=True, exist_ok=True)
        REGLAGES.write_text(json.dumps({"largeur": fenetre.width, "hauteur": fenetre.height}), encoding="utf-8")
    except (OSError, TypeError):
        pass


def attendre_serveur(fenetre, origine, serveur, direct):
    """Application autonome : l'interface s'affiche dès que le serveur répond ; s'il s'arrête avant, un message."""
    while not fenetre.events.closed.is_set():
        if serveur.poll() is not None:
            fenetre.load_html(page_erreur(f"Le serveur de calcul s'est arrêté au démarrage (code {serveur.returncode})."))
            return False
        try:
            direct.open(urllib.request.Request(origine + "/api/ping", data=b"", method="POST"), timeout=2).read()
        except OSError:                # pas encore à l'écoute (refus), ou délai dépassé pendant le chargement
            time.sleep(0.25)
            continue
        fenetre.load_url(origine + "/")
        return True
    return False


def surveiller(fenetre, origine, serveur=None):
    """Ferme la fenêtre quand le serveur s'est arrêté (bouton ⏻ Quitter de l'interface, ou arrêt imprévu).
    Un serveur occupé répond lentement (délai dépassé) : on n'en tient pas compte ; seul un refus de connexion compte.
    serveur : processus du serveur (application autonome, qui l'a lancé), sinon None."""
    if sys.platform == "darwin" and fenetre.events.shown.wait(15):
        from PyObjCTools import AppHelper
        AppHelper.callAfter(menus_sans_doublons)
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 127.0.0.1 : jamais par un proxy
    if serveur is not None and not attendre_serveur(fenetre, origine, serveur, direct):
        fenetre.events.closed.wait()   # message d'erreur affiché jusqu'à ce que l'utilisateur ferme la fenêtre
        return
    refus = 0
    # pywebview lance cette fonction dans un fil ordinaire : Python attend sa fin pour quitter. Elle s'arrête donc dès
    # que la fenêtre est fermée (sinon le processus resterait ouvert et le serveur ne s'arrêterait jamais).
    while not fenetre.events.closed.wait(3):
        try:
            direct.open(urllib.request.Request(origine + "/api/ping", data=b"", method="POST"), timeout=10).read()
            refus = 0
        except urllib.error.URLError as exc:
            refus = refus + 1 if isinstance(exc.reason, ConnectionError) else 0
        except ConnectionError:
            refus += 1
        except OSError:                # délai dépassé : serveur occupé
            refus = 0
        if refus >= 2 or (serveur is not None and serveur.poll() is not None):
            print("fenêtre : serveur arrêté, fermeture", flush=True)
            fenetre.destroy()
            return


def ouvrir(url, serveur=None):
    """Fenêtre de l'application sur url. serveur : processus du serveur lancé en même temps (application autonome) :
    la fenêtre s'ouvre tout de suite sur une page d'attente et affiche l'interface dès que le serveur répond."""
    if not presente():
        print(f"fenêtre native indisponible : pywebview absente (ni dans Python, ni dans {BIBLIO})", flush=True)
        return INDISPONIBLE
    try:
        icone = identite_systeme()
        import webview
    except Exception as exc:           # bibliothèque incomplète, système non pris en charge…
        print(f"fenêtre native indisponible : {exc!r}", flush=True)
        return INDISPONIBLE

    u = urlparse(url)
    origine = f"{u.scheme}://{u.netloc}"
    webview.settings["ALLOW_DOWNLOADS"] = True                   # exports STL / ZIP : boîte « Enregistrer sous »
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True    # liens target=_blank : voir ouvrir_lien

    ecran = webview.screens[0] if webview.screens else None
    largeur, hauteur = lire_taille(ecran)
    principale = webview.create_window(NOM, None if serveur else url, html=ACCUEIL if serveur else None, width=largeur,
                                       height=hauteur, min_size=(1000, 650), background_color=FOND, text_select=True)

    # pywebview confie les liens « nouvelle fenêtre » (target=_blank) à webbrowser.open. Un fichier de l'application
    # (aperçu PNG, rapport .md / .json de l'onglet CT) s'ouvre dans une petite fenêtre de l'application ; un lien vers
    # internet (référence DOI de l'onglet CORA) dans le navigateur habituel, comme dans les autres applications.
    navigateur = webbrowser.open

    def ouvrir_lien(adresse, *args, **kwargs):
        if not str(adresse).startswith(origine + "/"):
            return navigateur(adresse, *args, **kwargs)
        titre = f"{unquote(urlparse(adresse).path.rsplit('/', 1)[-1])} · {NOM}"
        threading.Thread(target=webview.create_window, args=(titre, adresse),
                         kwargs={"width": min(1100, largeur), "height": min(820, hauteur), "text_select": True},
                         daemon=True).start()
        return True

    webbrowser.open = ouvrir_lien

    def a_la_fermeture():
        ecrire_taille(principale)

    def apres_fermeture():             # fermer la fenêtre principale ferme aussi les aperçus : l'application s'arrête
        for w in list(webview.windows):
            if w is not principale:
                w.destroy()

    principale.events.closing += a_la_fermeture
    principale.events.closed += apres_fermeture
    gui = {"darwin": "cocoa", "win32": "edgechromium"}.get(sys.platform)    # Windows : jamais l'ancien moteur IE
    try:
        webview.start(surveiller, (principale, origine, serveur), gui=gui, private_mode=False,
                      storage_path=str(dossier_local() / "webview"), localization=FRANCAIS, icon=icone)
    except Exception as exc:
        print(f"fenêtre native : {exc!r}", flush=True)
        return 0 if principale.events.shown.is_set() else INDISPONIBLE
    return 0


def main():
    a = argparse.ArgumentParser(description=f"{NOM} : fenêtre native de l'application (lancée par serveur.py)")
    a.add_argument("url", nargs="?", help="adresse du serveur local, ex. http://127.0.0.1:8765/")
    a.add_argument("--verifier", action="store_true", help="code 0 si pywebview est disponible")
    a.add_argument("--installer", action="store_true", help="installer pywebview pour cet ordinateur si besoin")
    x = a.parse_args()
    if x.verifier:
        return 0 if presente() else 1
    if x.installer:
        return installer()
    if not x.url:
        a.error("adresse du serveur manquante")
    return ouvrir(x.url)


if __name__ == "__main__":
    sys.exit(main())
