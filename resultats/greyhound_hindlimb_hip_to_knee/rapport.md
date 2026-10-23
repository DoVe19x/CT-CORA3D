# Segmentation osseuse : greyhound_hindlimb_hip_to_knee

*Calcul du 2026-10-14 09:14:35 (durée 120.3 s).*

## Série DICOM

| Élément | Valeur |
|---|---|
| Patient / étude | Greyhound HL1 · 20130207 · PELVIS |
| Scanner | GE MEDICAL SYSTEMS LightSpeed Ultra, noyau BONEPLUS, 120 kV |
| Volume | 728 × 512 × 512 voxels (coupes × lignes × colonnes) |
| Voxel | 0.625 × 0.543 × 0.543 mm |
| Système des STL | LPS (mm, coordonnées du scanner) |

## Os exportés

| Fichier | Os | Volume (cm³) | Triangles | Étanche | Euler | Affinage (moy., mm) | Écart ±50 HU (moy. / P95, mm) |
|---|---|---|---|---|---|---|---|
| `bassin.stl` | bassin | 200.059 | 176802 | oui | -58 | -0.13 | n.d. |
| `fabelles.stl` | fabelles | 0.427 | 3148 | oui | 2 | -0.27 | n.d. |
| `femur.stl` | fémur | 100.286 | 150000 | oui | 2 | -0.23 | 0.10 / 0.42 ; 0.07 / 0.38 |
| `fibula.stl` | fibula | 1.113 | 14940 | oui | 2 | -0.26 | 0.21 / 1.21 ; 0.07 / 0.38 |
| `patella.stl` | patella | 2.242 | 8844 | oui | 2 | -0.22 | 0.20 / 0.84 ; 0.11 / 0.43 |
| `tibia.stl` | tibia | 46.527 | 103296 | oui | 2 | -0.25 | 0.11 / 0.42 ; 0.08 / 0.38 |

Euler = 2 pour un os d'un seul morceau sans trou (topologie d'une sphère) ; un groupe de n os sans trou donne 2n. Affinage : déplacement moyen des sommets vers le bord « demi-hauteur » (négatif = vers l'intérieur ; corrige le biais d'un seuil bas, voir code_source/README.md). Écart ± 50 HU : distance moyenne et 95e centile entre la surface au seuil de référence (226 HU) et la surface à 176 HU puis 276 HU (BP, hypothèse H2 : cible < 0.5 mm).

## Identification

| Segment | Nom | Volume (cm³) | Raison |
|---|---|---|---|
| 1 | fémur | 82.9 | os long avec une tête sphérique (rayon 12.62 mm) au contact du bassin |
| 2 | bassin | 60.36 | gros os au contact de la tête fémorale (acétabulum) |
| 3 | bassin | 57.1 | relié au bassin par un large contact (os coxal, sacrum, vertèbre) |
| 4 | tibia | 42.57 | os long longé par un os long fin et parallèle (fibula, segment 18) |
| 5 | bassin | 23.01 | relié au bassin par un large contact (os coxal, sacrum, vertèbre) |
| 6 | bassin | 22.86 | relié au bassin par un large contact (os coxal, sacrum, vertèbre) |
| 7 | bassin | 19.48 | relié au bassin par un large contact (os coxal, sacrum, vertèbre) |
| 8 | bassin | 6.47 | relié au bassin par un large contact (os coxal, sacrum, vertèbre) |
| 9 | bassin | 6.18 | relié au bassin par un large contact (os coxal, sacrum, vertèbre) |
| 10 | patella | 2.44 | petit os compact au contact du fémur (le plus gros) |
| 16 | bassin | 1.78 | relié au bassin par un large contact (os coxal, sacrum, vertèbre) |
| 18 | fibula | 1.5 | os long fin parallèle au tibia (allongement 8.7) |
| 26 | fabelles | 0.52 | petit os compact accolé au fémur (contact 33 mm², c* = 0.51) : sésamoïde du gastrocnémien |
| … | 13 segment(s) non identifié(s) | 17.5 | vertèbres, petits os, débris : visibles dans segmentation.seg.nrrd |

## Repères trouvés

* **tete_femorale** : centre (18.0, -41.0, -186.6) mm LPS, rayon 12.62 mm (2055 points de l'interligne, couverture 68%) → `reperes_auto.mrk.json`

## Fichiers

* `*.stl` : un maillage étanche par os (coordonnées du scanner, mm) ; `tarse.stl` = tous les os du tarse ;
* `segmentation.seg.nrrd` : toutes les étiquettes avec leurs noms, à ouvrir dans 3D Slicer avec la série DICOM ;
* `apercu_3d.png`, `apercu_coupes.png` : contrôle visuel ;
* `graines.json` (s'il existe) : points nommés par l'utilisateur, réappliqués à chaque calcul ;
* `rapport.json` : toutes les valeurs de ce rapport.

## Repères pour CORA 3D

* **femur** : complet, membre gauche (analysé comme un membre droit, par symétrie), 17 repères → `cora_femur.json`, `cora_femur.png`. Angles : aLPFA 114.2° (normal 103.2 ± 6.4), aLDFA 96.3° (normal 94.0 ± 3.3), varusFem 6.3° (normal 9.4 ± 2.3), aCdDFA 88.7° (normal 88.1 ± 6.3).
* **tibia** : pas d'analyse CORA (extrémité distale coupée par le champ du scanner : il faut les deux articulations pour la méthode CORA)
