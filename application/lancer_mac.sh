#!/bin/bash
# lancer_mac.sh — démarre l'application « CT-CORA3D » sur macOS (appelé par « CT-CORA3D.app »).
#
# Python : 1) l'environnement propre à cet ordinateur, ~/Library/Application Support/CTCORA3D/venv, s'il existe et
#             contient les bibliothèques (hors OneDrive : rapide) ;
#          2) sinon l'environnement du projet PMD2/.venv s'il contient les bibliothèques (lent si OneDrive a mis ses
#             fichiers « en ligne uniquement » : ils sont retéléchargés à l'import, parfois plusieurs minutes) ;
#          3) sinon l'environnement propre à cet ordinateur est créé (premier lancement, quelques minutes).
# Fenêtre : native (fenetre.py, bibliothèque pywebview installée une fois dans ce même dossier, hors OneDrive) ;
#           si l'installation est impossible (pas d'internet), l'application s'ouvre dans Chrome comme avant.
# Journal : ~/Library/Logs/CTCORA3D.log
ICI="$(cd "$(dirname "$0")" && pwd)"
PMD2="$(cd "$ICI/../.." && pwd)"
LOCAL="$HOME/Library/Application Support/CTCORA3D/venv"
JOURNAL="$HOME/Library/Logs/CTCORA3D.log"
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"
# vérification rapide : bibliothèques présentes ? (sans les charger : 0,02 s au lieu de 2 s ; le serveur les importe
# juste après)
MODULES="import importlib.util as u, sys; sys.exit(any(u.find_spec(m) is None for m in 'numpy scipy pydicom SimpleITK vtk trimesh pyvista matplotlib PIL manifold3d'.split()))"

message() { osascript -e "display notification \"$1\" with title \"CT-CORA3D\"" >/dev/null 2>&1; }
alerte() { osascript -e "display alert \"CT-CORA3D\" message \"$1\" as critical" >/dev/null 2>&1; }

exec >>"$JOURNAL" 2>&1
echo "=== $(date) ==="

PY=""
if [ -x "$LOCAL/bin/python" ] && "$LOCAL/bin/python" -c "$MODULES" 2>/dev/null; then
  PY="$LOCAL/bin/python"
elif [ -x "$PMD2/.venv/bin/python" ] && "$PMD2/.venv/bin/python" -c "$MODULES" 2>/dev/null; then
  PY="$PMD2/.venv/bin/python"
else
  BASE="$(command -v python3)"
  if [ -z "$BASE" ] || ! "$BASE" -c "import sys; assert sys.version_info >= (3, 10)" 2>/dev/null; then
    alerte "Python 3.10 ou plus récent est introuvable. Installez-le depuis python.org, puis relancez l'application."
    exit 1
  fi
  message "Premier lancement : installation des bibliothèques Python (quelques minutes)…"
  mkdir -p "$(dirname "$LOCAL")"
  "$BASE" -m venv "$LOCAL" && "$LOCAL/bin/python" -m pip install --upgrade pip \
    && "$LOCAL/bin/python" -m pip install -r "$ICI/requirements.txt"
  if ! "$LOCAL/bin/python" -c "$MODULES" 2>/dev/null; then
    alerte "L'installation des bibliothèques a échoué (connexion internet ?). Détails : $JOURNAL"
    exit 1
  fi
  PY="$LOCAL/bin/python"
fi
echo "python : $PY"
if ! "$PY" "$ICI/fenetre.py" --verifier; then
  message "Premier lancement : installation de la fenêtre de l'application (une minute)…"
  "$PY" "$ICI/fenetre.py" --installer
fi
exec "$PY" "$ICI/serveur.py"
