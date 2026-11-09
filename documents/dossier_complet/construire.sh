#!/bin/bash
# construire.sh — refait le dossier complet CT-CORA3D (PDF) à partir des sources LaTeX de ce dossier.
#
#   bash construire.sh            le PDF seulement (trois passes de XeLaTeX, environ 1 minute)
#   bash construire.sh figures    refait d'abord les schémas draw.io et les figures calculées, puis le PDF
#
# Il faut : XeLaTeX (TinyTeX convient, avec le paquet hyphen-french pour la césure), les polices Libertinus et
# Inconsolata (livrées avec TeX Live) ; pour les figures : draw.io (application de bureau) et le Python du projet.
# Le PDF est copié dans documents/CT-CORA3D_Dossier_complet.pdf.
set -euo pipefail
cd "$(dirname "$0")"
NOM="CT-CORA3D_Dossier_complet"

if [ "${1:-}" = "figures" ]; then
  DRAWIO=/Applications/draw.io.app/Contents/MacOS/draw.io
  PY="$HOME/Library/Application Support/CTCORA3D/venv/bin/python"
  echo "1. Schémas draw.io"
  (cd schemas && python3 schemas_dossier.py > /dev/null)
  for f in schemas/*.drawio; do
    n="$(basename "${f%.drawio}")"
    "$DRAWIO" --export --format pdf --crop --output "figures/$n.pdf" "$f" > /dev/null 2>&1 \
      || echo "   export impossible : $f (draw.io est-il déjà ouvert ? le fermer et relancer)"
  done
  echo "2. Figures calculées (matplotlib)"
  "$PY" figures_maths.py > /dev/null
fi

echo "3. Document (XeLaTeX, trois passes)"
mkdir -p construction
for passe in 1 2 3; do
  xelatex -interaction=nonstopmode -halt-on-error -output-directory=construction "$NOM.tex" > construction/console.txt 2>&1 \
    || { echo "   échec à la passe $passe : voir construction/$NOM.log"; tail -30 construction/console.txt; exit 1; }
done
cp "construction/$NOM.pdf" "../$NOM.pdf"
echo "   fait : documents/$NOM.pdf ($(grep -c 'Warning' "construction/$NOM.log" || true) avertissements LaTeX)"
