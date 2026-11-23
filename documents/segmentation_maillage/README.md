# Segmentation osseuse et maillage 3D

Ce dossier documente la partie « traitement d'images » de CT-CORA3D : du scanner (fichiers DICOM) aux os en 3D
(fichiers STL), puis une étude de convergence du maillage éléments finis d'un os. Il peut servir seul, par exemple
pour un autre cours : il ne parle pas de la chirurgie.

## Contenu

| Fichier ou dossier | Contenu |
|---|---|
| `main.pdf` | le document complet (lecture DICOM, segmentation, identification des os, maillage, contrôle, étude de convergence) |
| `main.tex` | sa source LaTeX (compilateur pdfLaTeX, comme sur Overleaf) |
| `images/` | les figures du document |
| `schemas/` | les schémas modifiables (`.drawio`, à ouvrir avec draw.io) et le script qui les crée |
| `figures.py` | refait les graphiques calculés (bord flou, critère c*, sensibilité au seuil) |
| `construire.sh` | refait le PDF (`bash construire.sh`) ou tout (`bash construire.sh figures`) et le zip pour Overleaf |
| `etude_convergence/` | l'étude de convergence éléments finis : code, résultats, fichiers Abaqus (voir son README) |
| `../segmentation_maillage_overleaf.zip` | le projet prêt à importer dans Overleaf (New Project, Upload Project) |

## Où est le code de la segmentation et du maillage

Dans `code_source/` à la racine du dépôt :

| Étape | Fichier |
|---|---|
| 1. Lecture DICOM | `etape1_lecture_dicom.py` |
| 2. Segmentation | `etape2_segmentation.py` |
| 3. Identification des os | `etape3_identification.py` |
| 4. Maillage (STL) | `etape4_maillage.py` |
| 5. Contrôle | `etape5_controle.py` |
| Réglages | `parametres.py` |
| Test sur un faux scanner | `tests/test_chaine.py` |

Lancer les étapes 1 à 5 sur une série : voir la section « Utiliser le module » du document.

## Refaire le document

```bash
bash construire.sh            # PDF seul (pdflatex, deux passes)
bash construire.sh figures    # figures (Python du projet), schémas (draw.io fermé), puis PDF
```
