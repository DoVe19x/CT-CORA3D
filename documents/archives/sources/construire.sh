#!/bin/bash
# construire.sh — refait les documents (PDF et Word) à partir des fichiers .md de ce dossier.
#
#   bash construire.sh            les 3 documents, en PDF et en Word (environ 1 minute)
#   bash construire.sh figures    refait d'abord les figures (schémas draw.io et graphes), puis les documents
#
# Il faut : pandoc (celui de RStudio convient), XeLaTeX (TinyTeX), et pour les figures draw.io (application de
# bureau) et le Python du projet.
set -euo pipefail
cd "$(dirname "$0")"
DOCS=".."

PANDOC="$(command -v pandoc || true)"
for p in /Applications/RStudio.app/Contents/Resources/app/quarto/bin/tools/aarch64/pandoc \
         /Applications/RStudio.app/Contents/Resources/app/quarto/bin/tools/x86_64/pandoc; do
  [ -z "$PANDOC" ] && [ -x "$p" ] && PANDOC="$p"
done
[ -n "$PANDOC" ] || { echo "pandoc introuvable : installer RStudio, ou pandoc (https://pandoc.org)"; exit 1; }

if [ "${1:-}" = "figures" ]; then
  DRAWIO=/Applications/draw.io.app/Contents/MacOS/draw.io
  PY="$HOME/Library/Application Support/CTCORA3D/venv/bin/python"
  echo "1. Schémas draw.io"
  python3 figures_drawio.py "$DOCS/figures" > /dev/null
  for f in "$DOCS"/figures/*.drawio; do
    "$DRAWIO" --export --format png --scale 3 --border 16 --output "${f%.drawio}.png" "$f" > /dev/null 2>&1 \
      || echo "   export impossible : $f (draw.io est-il déjà ouvert ? le fermer et relancer)"
  done
  echo "2. Schémas et graphes Python (la figure de segmentation relit un scanner : 1 à 10 min)"
  "$PY" figures_python.py "$DOCS/.." "$DOCS/figures" > /dev/null
fi

echo "3. Documents"

for paire in cahier_des_charges:Cahier_des_charges rapport_de_projet:Rapport_de_projet \
             documentation_technique:Documentation_technique; do
  doc="${paire%%:*}"
  nom="CT-CORA3D_${paire##*:}"
  "$PANDOC" "$doc.md" -o "$DOCS/$nom.pdf" --pdf-engine=xelatex -H en-tete.tex --toc --number-sections \
    -V fontsize=11pt -V geometry:margin=2.4cm -V colorlinks=true
  "$PANDOC" "$doc.md" -o "$DOCS/$nom.docx" -t docx+native_numbering --toc --number-sections
  echo "   $nom : PDF et Word faits"
done
