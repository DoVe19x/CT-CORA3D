# Segmentation osseuse : greyhound_hindlimb_knee_to_ankle

*Calcul du 2026-11-11 16:14:19 (durée 25.7 s).*

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
| `calcaneus.stl` | calcanéus | 13.957 | 44124 | oui | 2 | -0.28 | 0.16 / 0.79 ; 0.07 / 0.41 |
| `fabelles.stl` | fabelles | 0.427 | 3028 | oui | 2 | -0.28 | n.d. |
| `femur.stl` | fémur | 53.389 | 87796 | oui | 2 | -0.21 | 0.12 / 0.51 ; 0.09 / 0.41 |
| `fibula.stl` | fibula | 3.79 | 38700 | oui | 2 | -0.26 | 0.17 / 0.84 ; 0.07 / 0.40 |
| `metatarses.stl` | métatarses | 26.094 | 85472 | oui | 0 | -0.26 | n.d. |
| `patella.stl` | patella | 2.23 | 8556 | oui | 2 | -0.24 | 0.20 / 0.80 ; 0.10 / 0.46 |
| `phalanges.stl` | phalanges | 4.388 | 27592 | oui | 4 | -0.25 | n.d. |
| `talus.stl` | talus | 5.618 | 21308 | oui | 2 | -0.31 | 0.21 / 1.12 ; 0.05 / 0.39 |
| `tarse.stl` | tarse (autres os) | 24.221 | 68892 | oui | 0 | -0.27 | 0.14 / 0.65 ; 0.11 / 0.44 |
| `tibia.stl` | tibia | 82.215 | 150000 | oui | 2 | -0.24 | 0.11 / 0.48 ; 0.07 / 0.40 |

Euler = 2 pour un os d'un seul morceau sans trou (topologie d'une sphère) ; un groupe de n os sans trou donne 2n. Affinage : déplacement moyen des sommets vers le bord « demi-hauteur » (négatif = vers l'intérieur ; corrige le biais d'un seuil bas, voir code_source/README.md). Écart ± 50 HU : distance moyenne et 95e centile entre la surface au seuil de référence (226 HU) et la surface à 176 HU puis 276 HU (BP, hypothèse H2 : cible < 0.5 mm).

## Identification

| Segment | Nom | Volume (cm³) | Raison |
|---|---|---|---|
| 1 | tibia | 71.92 | os long dont on a séparé la fibula (petite tache parallèle sur les coupes) |
| 2 | objet non osseux | 44.54 | intérieur homogène (1286 HU, 0% de voxels < 600 HU) et sans cavité (+0%) : fantôme ou objet, pas un os |
| 3 | fémur | 43.63 | gros os au contact du plateau tibial (genou, segment 1) |
| 4 | métatarses | 7.65 | os long fin, parallèle à 2 autres (rayons du pied) |
| 5 | calcanéus | 14.49 | os du tarse le plus long (78 mm : tubérosité calcanéenne) |
| 6 | métatarses | 11.96 | os long fin, parallèle à 2 autres (rayons du pied) |
| 7 | métatarses | 4.43 | os long fin, parallèle à 2 autres (rayons du pied) |
| 8 | patella | 2.46 | petit os compact au contact du fémur (le plus gros) |
| 9 | phalanges | 2.37 | au-delà des métatarses (doigts) |
| 12 | phalanges | 1.44 | au-delà des métatarses (doigts) |
| 14 | phalanges | 0.92 | au-delà des métatarses (doigts) |
| 24 | fibula | 4.88 | petite tache parallèle au tibia sur les coupes, prolongée par croissance de région |
| 25 | talus | 6.28 | os du tarse au plus grand contact avec le tibia (articulation tarso-crurale) |
| 26 | tarse (autres os) | 4.12 | os compact du tarse (entre tibia et métatarses) |
| 27 | fabelles | 0.52 | petit os compact accolé au fémur (contact 30 mm², c* = 0.47) : sésamoïde du gastrocnémien |
| … | 12 segment(s) non identifié(s) | 9.2 | vertèbres, petits os, débris : visibles dans segmentation.seg.nrrd |

## Fichiers

* `*.stl` : un maillage étanche par os (coordonnées du scanner, mm) ; `tarse.stl` = tous les os du tarse ;
* `segmentation.seg.nrrd` : toutes les étiquettes avec leurs noms, à ouvrir dans 3D Slicer avec la série DICOM ;
* `apercu_3d.png`, `apercu_coupes.png` : contrôle visuel ;
* `graines.json` (s'il existe) : points nommés par l'utilisateur, réappliqués à chaque calcul ;
* `rapport.json` : toutes les valeurs de ce rapport.

## Repères pour CORA 3D

* **femur** : pas d'analyse CORA (extrémité proximale coupée par le champ du scanner : il faut les deux articulations pour la méthode CORA)
* **tibia** : complet, membre gauche (analysé comme un membre droit, par symétrie), 20 repères → `cora_tibia.json`, `cora_tibia.png`. Angles : mMPTA 91.2° (normal 94.6 ± 1.8), mMDTA 96.5° (normal 96.1 ± 2.7), valgusTib 7.7° (normal 13.2 ± 3.1), mCaPTA 77.7° (normal 73.2 ± 2.6), mCrDTA 84.5° (normal 86.7 ± 3.2).
