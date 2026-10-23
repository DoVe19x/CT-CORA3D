# Segmentation osseuse : greyhound_hindlimb_ankle_down

*Calcul du 2026-10-13 09:59:19 (durée 25.8 s).*

## Série DICOM

| Élément | Valeur |
|---|---|
| Patient / étude | greyhoundHL3 · 20130220 · PELVIS |
| Scanner | GE MEDICAL SYSTEMS LightSpeed Ultra, noyau BONEPLUS, 120 kV |
| Volume | 442 × 512 × 512 voxels (coupes × lignes × colonnes) |
| Voxel | 0.625 × 0.268 × 0.268 mm |
| Système des STL | LPS (mm, coordonnées du scanner) |

## Os exportés

| Fichier | Os | Volume (cm³) | Triangles | Étanche | Euler | Affinage (moy., mm) | Écart ±50 HU (moy. / P95, mm) |
|---|---|---|---|---|---|---|---|
| `calcaneus.stl` | calcanéus | 13.934 | 115632 | oui | 2 | -0.27 | 0.12 / 0.50 ; 0.06 / 0.17 |
| `metatarses.stl` | métatarses | 23.046 | 150000 | oui | 0 | -0.29 | n.d. |
| `phalanges.stl` | phalanges | 10.884 | 150000 | oui | -4 | -0.23 | n.d. |
| `talus.stl` | talus | 5.596 | 58964 | oui | 2 | -0.32 | 0.18 / 1.02 ; 0.04 / 0.15 |
| `tarse.stl` | tarse (autres os) | 24.033 | 150000 | oui | 0 | -0.28 | 0.14 / 0.60 ; 0.06 / 0.20 |
| `tibia.stl` | tibia | 21.944 | 143760 | oui | 2 | -0.24 | 0.08 / 0.22 ; 0.05 / 0.15 |

Euler = 2 pour un os d'un seul morceau sans trou (topologie d'une sphère) ; un groupe de n os sans trou donne 2n. Affinage : déplacement moyen des sommets vers le bord « demi-hauteur » (négatif = vers l'intérieur ; corrige le biais d'un seuil bas, voir code_source/README.md). Écart ± 50 HU : distance moyenne et 95e centile entre la surface au seuil de référence (226 HU) et la surface à 176 HU puis 276 HU (BP, hypothèse H2 : cible < 0.5 mm).

## Identification

| Segment | Nom | Volume (cm³) | Raison |
|---|---|---|---|
| 1 | objet non osseux | 40.5 | intérieur homogène (1290 HU, 0% de voxels < 600 HU) et sans cavité (+0%) : fantôme ou objet, pas un os |
| 2 | tibia | 19.39 | gros os au-dessus du tarse (le champ du scanner le coupe) |
| 3 | calcanéus | 14.39 | os du tarse le plus long (78 mm : tubérosité calcanéenne) |
| 4 | métatarses | 7.23 | os long fin, parallèle à 3 autres (rayons du pied) |
| 5 | métatarses | 6.49 | os long fin, parallèle à 3 autres (rayons du pied) |
| 6 | talus | 6.24 | os du tarse au plus grand contact avec le tibia (articulation tarso-crurale) |
| 7 | métatarses | 4.29 | os long fin, parallèle à 3 autres (rayons du pied) |
| 8 | métatarses | 4.24 | os long fin, parallèle à 3 autres (rayons du pied) |
| 9 | tarse (autres os) | 4.24 | os compact du tarse (entre tibia et métatarses) |
| 10 | phalanges | 3.07 | au-delà des métatarses (doigts) |
| 11 | phalanges | 3.0 | au-delà des métatarses (doigts) |
| 12 | phalanges | 2.89 | au-delà des métatarses (doigts) |
| 13 | phalanges | 2.48 | au-delà des métatarses (doigts) |

## Fichiers

* `*.stl` : un maillage étanche par os (coordonnées du scanner, mm) ; `tarse.stl` = tous les os du tarse ;
* `segmentation.seg.nrrd` : toutes les étiquettes avec leurs noms, à ouvrir dans 3D Slicer avec la série DICOM ;
* `apercu_3d.png`, `apercu_coupes.png` : contrôle visuel ;
* `graines.json` (s'il existe) : points nommés par l'utilisateur, réappliqués à chaque calcul ;
* `rapport.json` : toutes les valeurs de ce rapport.

## Repères pour CORA 3D

* **tibia** : pas d'analyse CORA (extrémité distale coupée par le champ du scanner : il faut les deux articulations pour la méthode CORA)
