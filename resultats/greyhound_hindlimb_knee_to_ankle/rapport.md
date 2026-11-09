# Segmentation osseuse : greyhound_hindlimb_knee_to_ankle

*Calcul du 2026-11-06 18:14:11 (durée 23.9 s).*

## Série DICOM

| Élément | Valeur |
|---|---|
| Patient / étude | Greyhound HL1B · 20130208 · PELVIS |
| Scanner | GE MEDICAL SYSTEMS LightSpeed Ultra, noyau BONEPLUS, 120 kV |
| Volume | 748 × 512 × 512 voxels (coupes × lignes × colonnes) |
| Voxel | 0.625 × 0.561 × 0.561 mm |
| Système des STL | LPS (mm, coordonnées du scanner) |

## Os exportés

| Fichier | Os | Volume (cm³) | Triangles | Étanche | Euler | Affinage (moy., mm) | Écart ±50 HU (moy. / P95, mm) |
|---|---|---|---|---|---|---|---|
| `calcaneus.stl` | calcanéus | 15.081 | 49564 | oui | 2 | -0.39 | 1.15 / 2.86 ; 0.20 / 0.82 |
| `fabelles.stl` | fabelles | 0.469 | 3536 | oui | 2 | -0.44 | n.d. |
| `femur.stl` | fémur | 54.385 | 92424 | oui | 0 | -0.36 | 0.64 / 2.24 ; 0.16 / 0.61 |
| `fibula.stl` | fibula | 4.561 | 44864 | oui | -2 | -0.36 | 0.80 / 2.37 ; 0.16 / 0.64 |
| `metatarses.stl` | métatarses | 28.478 | 90496 | oui | -6 | -0.32 | n.d. |
| `patella.stl` | patella | 2.383 | 10068 | oui | 0 | -0.38 | 0.76 / 2.31 ; 0.18 / 0.61 |
| `phalanges.stl` | phalanges | 5.06 | 31172 | oui | 4 | -0.33 | n.d. |
| `talus.stl` | talus | 5.872 | 22584 | oui | 2 | -0.41 | 0.92 / 2.80 ; 0.11 / 0.56 |
| `tarse.stl` | tarse (autres os) | 26.089 | 73940 | oui | 0 | -0.37 | 0.99 / 2.80 ; 0.20 / 0.84 |
| `tibia.stl` | tibia | 83.982 | 150000 | oui | 2 | -0.37 | 0.86 / 2.58 ; 0.14 / 0.57 |

Euler = 2 pour un os d'un seul morceau sans trou (topologie d'une sphère) ; un groupe de n os sans trou donne 2n. Affinage : déplacement moyen des sommets vers le bord « demi-hauteur » (négatif = vers l'intérieur ; corrige le biais d'un seuil bas, voir code_source/README.md). Écart ± 50 HU : distance moyenne et 95e centile entre la surface au seuil de référence (100 HU) et la surface à 50 HU puis 150 HU (BP, hypothèse H2 : cible < 0.5 mm).

## Identification

| Segment | Nom | Volume (cm³) | Raison |
|---|---|---|---|
| 1 | tibia | 80.11 | os long dont on a séparé la fibula (petite tache parallèle sur les coupes) |
| 2 | fémur | 53.86 | gros os au contact du plateau tibial (genou, segment 1) |
| 3 | objet non osseux | 44.89 | intérieur homogène (1278 HU, 0% de voxels < 600 HU) et sans cavité (+0%) : fantôme ou objet, pas un os |
| 4 | métatarses | 8.66 | os long fin, parallèle à 2 autres (rayons du pied) |
| 5 | calcanéus | 16.26 | os du tarse le plus long (79 mm : tubérosité calcanéenne) |
| 6 | métatarses | 13.41 | os long fin, parallèle à 2 autres (rayons du pied) |
| 7 | métatarses | 4.89 | os long fin, parallèle à 2 autres (rayons du pied) |
| 8 | patella | 2.76 | petit os compact au contact du fémur (le plus gros) |
| 9 | phalanges | 2.75 | au-delà des métatarses (doigts) |
| 11 | phalanges | 1.69 | au-delà des métatarses (doigts) |
| 15 | phalanges | 1.03 | au-delà des métatarses (doigts) |
| 24 | fibula | 5.91 | petite tache parallèle au tibia sur les coupes, prolongée par croissance de région |
| 25 | talus | 6.7 | os du tarse au plus grand contact avec le tibia (articulation tarso-crurale) |
| 26 | tarse (autres os) | 4.51 | os compact du tarse (entre tibia et métatarses) |
| 27 | fabelles | 0.61 | petit os compact accolé au fémur (contact 54 mm², c* = 0.75) : sésamoïde du gastrocnémien |
| … | 12 segment(s) non identifié(s) | 11.0 | vertèbres, petits os, débris : visibles dans segmentation.seg.nrrd |

## Fichiers

* `*.stl` : un maillage étanche par os (coordonnées du scanner, mm) ; `tarse.stl` = tous les os du tarse ;
* `segmentation.seg.nrrd` : toutes les étiquettes avec leurs noms, à ouvrir dans 3D Slicer avec la série DICOM ;
* `apercu_3d.png`, `apercu_coupes.png` : contrôle visuel ;
* `graines.json` (s'il existe) : points nommés par l'utilisateur, réappliqués à chaque calcul ;
* `rapport.json` : toutes les valeurs de ce rapport.

## Repères pour CORA 3D

* **femur** : pas d'analyse CORA (extrémité proximale coupée par le champ du scanner : il faut les deux articulations pour la méthode CORA)
* **tibia** : pas d'analyse CORA (échec de l'analyse : 'distal_center')
