#!/usr/bin/env python3
"""
ct_cora3d_app.py — point d'entrée de l'application autonome CT-CORA3D (macOS : « CT-CORA3D.app », construite par
                   lanceurs/creer_app_autonome.sh ; Windows : CT-CORA3D.exe, construite par
                   lanceurs/creer_app_windows.bat ; PyInstaller : Python et toutes les bibliothèques sont dans
                   l'application, rien à installer, aucun navigateur).

Rôle      : le même exécutable joue deux rôles.
            Sans argument (double-clic) : processus de la FENÊTRE (fenetre.py, pywebview, moteur WebKit du système).
              Il lance le serveur de calcul (ce même exécutable avec --serveur), ouvre aussitôt la fenêtre sur
              « Démarrage des calculs… », puis affiche l'interface dès que le serveur répond.
              Fermer la fenêtre arrête le serveur (après le calcul en cours).
            --serveur [options de serveur.py] : processus de CALCUL (serveur.py), sans fenêtre ni icône dans le Dock.
Pourquoi deux processus : sur macOS, la fenêtre (Cocoa) et les calculs (VTK) exigent tous deux le fil principal.
Dossiers  : voir parametres.py (dossier du projet d'où l'application a été construite, sinon ~/Documents/CT-CORA3D).
Journal   : ~/Library/Logs/CTCORA3D.log (macOS), %LOCALAPPDATA%\\CTCORA3D\\CTCORA3D.log (Windows)
Essai sans construire : python ct_cora3d_app.py (avec l'environnement Python du projet et pywebview).
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "darwin":
    JOURNAL = Path.home() / "Library" / "Logs" / "CTCORA3D.log"
elif os.name == "nt":                  # même journal que le lanceur « Lancer sur Windows.bat »
    JOURNAL = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "CTCORA3D" / "CTCORA3D.log"
else:
    JOURNAL = Path.home() / ".local" / "state" / "ctcora3d" / "CTCORA3D.log"


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serveur(argv):
    """Processus de calcul : serveur.py, sans icône dans le Dock (VTK touche à l'application Cocoa pour ses rendus)."""
    os.environ.setdefault("MPLBACKEND", "Agg")              # matplotlib : jamais de fenêtre
    if sys.platform == "darwin":
        try:
            import AppKit
            AppKit.NSApplication.sharedApplication().setActivationPolicy_(AppKit.NSApplicationActivationPolicyProhibited)
        except Exception as exc:                            # pyobjc absente (essai hors paquet) : sans conséquence
            print(f"serveur : politique d'activation inchangée ({exc!r})", flush=True)
    import serveur as S
    S.main(argv)
    return 0


def fenetre():
    """Processus de la fenêtre : lance le serveur, puis la fenêtre native ; le serveur suit ce processus."""
    import fenetre as F
    port = port_libre()
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    journal = open(JOURNAL, "a", buffering=1, encoding="utf-8")
    journal.write(f"=== {time.ctime()} — application autonome ({sys.executable}) ===\n")
    soi = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")   # 2e instance indépendante de l'exécutable
    # entrée standard en tube : elle se ferme quand ce processus se termine, le serveur s'arrête alors (--suivre-parent)
    srv = subprocess.Popen(soi + ["--serveur", "--port", str(port), "--sans-fenetre", "--suivre-parent"],
                           stdin=subprocess.PIPE, stdout=journal, stderr=subprocess.STDOUT, env=env)
    code = F.ouvrir(f"http://127.0.0.1:{port}/", serveur=srv)
    if code == F.INDISPONIBLE:
        journal.write("fenêtre native impossible : arrêt du serveur\n")
        srv.terminate()
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--serveur":
        return serveur(sys.argv[2:])
    return fenetre()


if __name__ == "__main__":
    sys.exit(main())
