#!/bin/bash
# creer_app_autonome.sh — construit l'application AUTONOME « CT-CORA3D.app » dans ~/Applications (macOS).
#
# Différence avec creer_app_mac.sh (petit lanceur dans le dossier du projet) : ici Python et toutes les bibliothèques
# sont copiés DANS l'application (PyInstaller, ≈ 1 Go). Elle s'ouvre dans sa propre fenêtre (moteur WebKit du
# système), sans navigateur, sans environnement Python à installer, et peut être copiée sur un autre Mac (Apple
# Silicon). Ses résultats vont dans le dossier du projet tant qu'il existe, sinon dans ~/Documents/CT-CORA3D.
#
# Construction hors OneDrive (des milliers de fichiers) : ~/Library/Caches/CTCORA3D/ (environnement de construction,
# fichiers intermédiaires). Durée : ≈ 5 min la première fois (téléchargement des bibliothèques), ensuite ≈ 2-3 min.
# À relancer après chaque modification du programme (code_source/ ou application/).
# Usage : bash creer_app_autonome.sh          (Python 3.10+ : PYTHON=/chemin/python3 pour en choisir un autre)
set -euo pipefail
ICI="$(cd "$(dirname "$0")" && pwd)"
APPLI="$(cd "$ICI/.." && pwd)"
PROJET="$(cd "$APPLI/.." && pwd)"
CACHE="$HOME/Library/Caches/CTCORA3D"
VENV="$CACHE/venv-construction"
CIBLE="$HOME/Applications"
export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
BASE="${PYTHON:-$(command -v python3)}"

echo "1/4 environnement de construction ($VENV)"
[ -x "$VENV/bin/python" ] || "$BASE" -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check -r "$APPLI/requirements.txt" "pywebview>=5.0" "pyinstaller>=6.16"

echo "2/4 interface CORA et calibration des repères à jour (l'application ne peut pas les réécrire)"
"$VENV/bin/python" "$PROJET/code_source/cora/build_app.py"
(cd "$PROJET/code_source" && "$VENV/bin/python" -c "import etape6_reperes as E; E.calibration()")

echo "3/4 PyInstaller"
export CTCORA3D_CONSTRUCTION="$CACHE/construction"
"$VENV/bin/python" -m PyInstaller --noconfirm --log-level WARN --distpath "$CACHE/dist" \
  --workpath "$CTCORA3D_CONSTRUCTION" "$ICI/ct_cora3d.spec"

echo "4/4 installation dans $CIBLE"
mkdir -p "$CIBLE"
rm -rf "$CIBLE/CT-CORA3D.app"
ditto "$CACHE/dist/CT-CORA3D.app" "$CIBLE/CT-CORA3D.app"
codesign --force --deep --sign - "$CIBLE/CT-CORA3D.app" 2>/dev/null || true    # signature locale (ad hoc)
touch "$CIBLE/CT-CORA3D.app"
echo "OK : $CIBLE/CT-CORA3D.app ($(du -sh "$CIBLE/CT-CORA3D.app" | cut -f1))"
