#!/bin/bash
# construire.sh : refait le PDF du document « Segmentation osseuse et maillage 3D ».
#
#   bash construire.sh            compile main.tex (trois passes, pour la table des matières et les renvois)
#   bash construire.sh figures    refait d'abord les figures (figures.py) et les schémas (schemas/*.drawio)
#
# Il faut : TinyTeX ou MacTeX (pdflatex) ; pour « figures » : le Python du projet (../../../.venv) et draw.io
# (/Applications/draw.io.app, fermé pendant l'export). Le zip pour Overleaf est refait à chaque fois.
set -e
cd "$(dirname "$0")"
PYTHON="../../../.venv/bin/python"
DRAWIO="/Applications/draw.io.app/Contents/MacOS/draw.io"

if [ "$1" = "figures" ]; then
  echo "Figures calculées"
  "$PYTHON" figures.py
  echo "Schémas draw.io"
  python3 schemas/schemas.py
  for f in schemas/*.drawio; do
    n="$(basename "${f%.drawio}")"
    "$DRAWIO" --export --format pdf --crop --output "images/schema_$n.pdf" "$f" > /dev/null 2>&1 \
      || echo "   export impossible : $f (draw.io est-il déjà ouvert ? le fermer et relancer)"
  done
fi

echo "Compilation LaTeX"
TMP="$(mktemp -d)"
for passe in 1 2 3; do
  pdflatex -interaction=nonstopmode -halt-on-error -output-directory "$TMP" main.tex > "$TMP/console.txt" \
    || { tail -30 "$TMP/console.txt"; exit 1; }
done
cp "$TMP/main.pdf" main.pdf
grep -E "Warning|Overfull" "$TMP/main.log" | grep -v "Font shape" | head -20 || true
rm -rf "$TMP"

echo "Zip pour Overleaf"
rm -f ../segmentation_maillage_overleaf.zip
zip -qr ../segmentation_maillage_overleaf.zip main.tex images
echo "Fait : main.pdf et ../segmentation_maillage_overleaf.zip"
