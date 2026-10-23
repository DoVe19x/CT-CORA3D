# code_source — du scanner DICOM aux os en STL, puis à la planification CORA (CT-CORA3D, PMD2)

Ce dossier contient le programme. L'application (`../application/`) appelle exactement ces fonctions ; la ligne de
commande `lancer_tout.py` aussi.

* **Python** (étapes 1 à 7) : Python 3.10 ou plus récent ; numpy, scipy, pydicom, SimpleITK, VTK, trimesh, pyvista,
  matplotlib, manifold3d (liste : `../application/requirements.txt`). Étapes 1 à 5 reprises de `../../CT-scan/` ;
  étapes 6 (repères) et 7 (guides imprimables) nouvelles.
* **JavaScript** (`cora/`) : la planification CORA (onglet 2), reprise de `../../CORA3D/` et étendue aux os segmentés.
  Aucune dépendance (Three.js est embarqué) ; tests sous Node ≥ 22.

## Commandes

```bash
cd code_source
../../.venv/bin/python lancer_tout.py --liste                 # inventaire des séries DICOM (défaut : ../../CT-scan)
../../.venv/bin/python lancer_tout.py                         # toutes les séries, étapes 1 à 6 (≈ 115 s pour les 3)
../../.venv/bin/python lancer_tout.py --serie hip_to_knee     # une série (un morceau de nom unique suffit)
../../.venv/bin/python lancer_tout.py --dossier "D:/CT chien 12" --sortie "D:/resultats" --seuil 250 --ras
../../.venv/bin/python tests/test_chaine.py                   # test automatique sur un fantôme synthétique (≈ 3 s)

../../.venv/bin/python etape6_reperes.py                      # étape 6 seule, sur tous les dossiers de ../resultats
../../.venv/bin/python etape6_reperes.py ../resultats/greyhound_hindlimb_knee_to_ankle --os tibia
../../.venv/bin/python tests/test_reperes.py                  # détection des repères : modèle + os réels (≈ 12 s)

../../.venv/bin/python etape7_guide.py --prescription P.json --os os.bin --sortie dossier \
      [--voisin fibula=fibula.bin] [--cartilage cartilage.u8]                               # guides (≈ 15 à 40 s)
../../.venv/bin/python tests/test_guide.py                    # guides : os synthétique + os réels (≈ 90 s ; --rapide)

node tests/campagne_strategie.mjs <dossier> [n] [graine] [--exporter]  # stratégie : 17 préréglages + n cas au hasard,
                                                              # règles R1 à R9 (≈ 30 s pour n = 300) ; --exporter :
                                                              # sous-ensemble de cas dans <dossier>/guides/
node tests/campagne_export.mjs <dossier> [coins|aleatoire|tout] [n] [graine]    # campagne : cas planifiés (os fictif)
../../.venv/bin/python tests/campagne_guides.py <dossier> --processus 4       # guides + contrôles « de chirurgien »
#   --filtre <texte>, --reprendre (cas absents du .jsonl), --rapport (rapport seul, depuis resultats_campagne.jsonl)

cd cora
python3 build_app.py                                          # reconstruit ../../application/interface/cora/index.html
node tests/test_cas.mjs                                       # os fictif : 12 cas + 252 variantes + torsion
node tests/test_reel.mjs                                      # os segmentés : tels quels + 6 déformités de test chacun
```

Options : `--sans-controle` (sans la sensibilité au seuil), `--sans-images` (sans aperçus PNG), `--ras` (STL en RAS).
Tous les réglages sont dans `parametres.py`, chacun avec son origine (document Best_Position, littérature, ou mesure
sur les scanners du dossier).

## La chaîne, étape par étape

| Fichier | Rôle |
|---|---|
| `parametres.py` | tous les réglages |
| `etape1_lecture_dicom.py` | inventaire des séries, construction du volume en HU et de sa géométrie |
| `etape2_segmentation.py` | seuillage, graines automatiques, croissance de région, recollage des sur-découpages |
| `etape3_identification.py` | noms des os, tête fémorale (sphère), fibula, fabelles, tarse, points de l'utilisateur |
| `etape4_maillage.py` | remplissage, maillage étanche, affinage « demi-hauteur », STL, `segmentation.seg.nrrd` |
| `etape5_controle.py` | sensibilité au seuil ± 50 HU (H2), aperçus, `rapport.md`, `rapport.json`, repères Slicer |
| `etape6_reperes.py` | **nouveau** : repère, côté, complétude et repères anatomiques du fémur et du tibia pour CORA |
| `etape7_guide.py` | **nouveau** : guide de coupe « 2 en 1 » (moitiés et ponts sécables, butée de profondeur, verrou de réduction intégré ; guide de réduction séparé en option), avec contrôles |
| `calibration_reperes.json` | cache de l'étape 6 : écarts de définition mesurés sur l'os du modèle (recalculé si besoin) |
| `lancer_tout.py` | enchaîne les six étapes (ligne de commande) |
| `tests/test_chaine.py` | fantôme synthétique écrit en DICOM, géométrie connue : contrôle de bout en bout |
| `tests/test_reperes.py` | étape 6 : os du modèle dans des poses aléatoires (repères exacts connus) et os réels |
| `tests/test_guide.py` | étape 7 : os coudé synthétique (prescriptions écrites à la main) et os réels |
| `tests/modele_cora.py` | lit le modèle osseux de CORA 3D (`cora/build/bones_pack.*`) depuis Python |
| `vtk_leger.py` | les seules classes VTK utilisées (`import vtk_leger as vtk`) : `import vtk` chargeait toute la bibliothèque (2,2 s au démarrage, 0,5 s désormais) |
| `cora/` | planification CORA en JavaScript (voir la section « cora/ » plus bas) |

Temps de calcul de la chaîne (étapes 1 à 6) sur la série du lévrier « genou → cheville » (748 coupes) : ≈ 60 s. La
boîte englobante d'un os se calcule par projections `np.any` (`etape2_segmentation.boite_englobante`, sans copie du
volume) au lieu de `find_objects(m.astype(np.uint8))` : 2 ms au lieu de 120 ms, à chaque os et à chaque étape. Tous les
fichiers texte (JSON, rapports, STL ASCII) sont lus et écrits en UTF-8 explicite : sous Windows, l'encodage par défaut
(cp1252) ne connaît ni « ≥ » ni « → » et faisait échouer l'écriture de `guide.json`.

### Étape 1 — lecture DICOM (comme le module DICOM de 3D Slicer)

1. **Inventaire** : tous les fichiers du dossier (sous-dossiers compris, extension quelconque) dont l'en-tête est
   DICOM sont regroupés par série (`SeriesInstanceUID`). Seules les images en coupe sont gardées.
2. **Tri des coupes le long de la normale** `n = ligne × colonne` (produit vectoriel des cosinus directeurs
   `ImageOrientationPatient`), par la position `ImagePositionPatient · n`. Le numéro d'image n'est pas fiable et
   n'est pas utilisé ; le test le vérifie en mélangeant les noms de fichiers.
3. **Contrôles** : une seule orientation (les images de repérage sont écartées), coupes en double écartées,
   espacement régulier (sinon rééchantillonnage linéaire et avertissement), épaisseur ≤ 1 mm (BP §3.1, sinon
   avertissement), inclinaison du statif détectée.
4. **Unités Hounsfield** : `HU = valeur × RescaleSlope + RescaleIntercept`, stockées en entiers 16 bits.
5. **Géométrie** : matrice 4 × 4 qui envoie l'indice de voxel `(i, j, k)` (colonne, ligne, coupe) vers les
   coordonnées du scanner LPS en mm. Ses colonnes : direction des lignes × écart entre colonnes, direction des
   colonnes × écart entre lignes, pas réel d'une coupe à la suivante (donc exact même avec un statif incliné),
   position du premier voxel. Tout ce qui est produit (STL, repères) est exprimé dans ce repère.

### Étape 2 — seuillage et croissance de région

Le principe du schéma du projet : « seuillage + croissance de région ».

1. **Recadrage** sur les os denses (calculé sur un volume 2 fois plus petit : économie de mémoire) et **lissage**
   gaussien de 0,35 mm (bruit mesuré dans les tissus mous ≈ 49 HU avec le noyau BONEPLUS).
2. **Masque osseux** : voxels ≥ 226 HU (BP : 200 à 300 HU ; 226 HU est le seuil « Bone (CT) » de Mimics).
3. **Une graine par os.** À 226 HU tout le membre forme un seul bloc : aux articulations, quelques voxels de
   volume partiel font des ponts. On monte donc le seuil palier par palier (500 → 1500 HU, pas de 100 HU) : les
   interlignes, moins denses que l'os, cèdent avant lui. Quand un bloc se coupe en morceaux d'au moins 0,3 cm³
   qui existent encore 200 HU plus haut (un vrai os a une corticale dense, un fragment d'os spongieux disparaît),
   chaque morceau devient une graine et est examiné aux paliers suivants. Mesuré sur le lévrier : le genou se
   sépare dès 600 HU, la hanche vers 900 HU, le tarse vers 1200 à 1400 HU.
4. **Croissance de région compétitive** : toutes les graines grandissent en même temps dans le masque osseux,
   chacune par ses voxels les plus denses d'abord (ligne de partage des eaux de SimpleITK sur l'intensité
   inversée). Deux os se rencontrent dans la zone la moins dense entre eux : l'interligne.
5. **Recollage des sur-découpages.** À haut seuil, une épiphyse se détache parfois de la diaphyse (corticale de
   la métaphyse trop fine). Les deux morceaux se touchent alors sur toute la section de l'os. Critère sans
   dimension `c* = surface de contact / V_min^(2/3)`. Mesuré : coupure à travers un même os, c* ≈ 5 ; vraies
   articulations, c* ≤ 2,1 (hanche 0,6 ; tarse ≤ 2,1). Les morceaux sont recollés si c* ≥ 3.

### Étape 3 — identification et corrections anatomiques

Descripteurs de chaque segment : volume, longueur et allongement (analyse en composantes principales), densité à
l'intérieur, contacts avec les voisins, contact avec le bord du champ (os coupé). Puis, de la règle la plus sûre
à la moins sûre :

| Ordre | Os | Règle |
|---|---|---|
| 1 | objet non osseux | intérieur homogène et dense (fantôme de calibration : 1300 HU, 2 % de voxels < 600 HU) **et** aucune cavité à remplir (un os en a toujours) |
| 2 | tibia, fibula | un os long fin, parallèle et qui recouvre au moins la moitié de la longueur, touche un gros os long |
| 3 | fémur, bassin | une **sphère** (tête fémorale) est trouvée au contact d'un gros voisin (voir ci-dessous) |
| 4 | genou | le gros os au contact du plateau tibial (extrémité la plus large) est le fémur, et inversement |
| 5 | fibula collée | sur des tranches perpendiculaires au tibia, une petite tache (aire < 20 % de celle du tibia) est vue séparée sur au moins 15 % de la longueur, en se déplaçant de moins de 3 mm d'une tranche à l'autre ; elle sert de graine « fibula » |
| 5 bis | raffinement | un segment allongé qui touche la jambe n'est pas un métatarse pur : il est re-découpé avec des graines plus fines (ex. talus soudé à un rayon du pied) |
| 6 | métatarses | au moins 3 os longs fins, parallèles et voisins |
| 7 | tibia (pied seul) | gros os au-dessus du tarse quand aucune autre règle ne l'a trouvé |
| 8 | talus, calcanéus, tarse | os compacts reliés au bout distal du tibia : talus = plus grand contact avec le tibia ; calcanéus = le plus long |
| 9 | phalanges | au-delà des métatarses |
| 10 | patella, fabelles | petits os compacts au contact du fémur ; les fabelles collées au fémur en sont détachées par un raffinement si elles sont petites, compactes et peu en contact (c* < 1,5) |
| 11 | bassin | gros os reliés à l'acétabulum par de larges contacts |
| 12 | points de l'utilisateur | renommer un segment, ou le séparer quand il contient des points de plusieurs noms |
| 13 | côtés | s'il y a deux fémurs ou deux tibias : `_gauche` / `_droit` d'après x (LPS), à vérifier |

**Tête fémorale.** La hanche est l'articulation la plus serrée : sur ce cadavre, la tête touche l'acétabulum
jusqu'à 1100 HU alors qu'elle se détache du col dès 900 HU. Aucun seuil ne la rend au fémur. Mais l'interligne
reste visible comme une ligne sombre de 1 à 2 voxels. Un « chapeau haut-de-forme noir » (fermeture morphologique
en niveaux de gris − image, rayon 1 mm) révèle ces vallées. Une sphère y est ajustée par RANSAC (rayon 4 à 20 mm,
tolérance 0,6 mm), validée si au moins 150 points la soutiennent et si elle couvre au moins 40 % des directions.
La zone fémur + bassin est alors redistribuée : graine « fémur » à l'intérieur de la sphère (rayon − 1 mm), graine
« bassin » au-delà (rayon + 1 mm), et la croissance de région place la frontière sur l'interligne. Le centre et le
rayon sont écrits dans `reperes_auto.mrk.json` (format Markups de 3D Slicer, nom `tete_femorale`), lisible
directement par `Planificateur_CORA_3Dv2`.

### Étape 4 — maillages étanches

1. **Remplissage** : fermeture morphologique de 1 mm (pores de la corticale), puis remplissage des cavités en 3D
   (canal médullaire, os spongieux). Si l'os sort du champ du scanner, sa section au bord est d'abord fermée par
   un « couvercle » : sinon le canal serait ouvert et ne se remplirait pas.
2. **Surface** : flou de 0,3 mm du masque, puis « marching cubes » (`vtkFlyingEdges3D`, isovaleur 0,5).
3. **Lissage** « windowed sinc » (20 itérations), qui ne rétrécit pas le maillage (comme 3D Slicer), puis
   décimation au-delà de 150 000 triangles (seulement si le maillage reste étanche).
4. **Affinage « demi-hauteur »** : chaque sommet est déplacé le long de sa normale jusqu'au point où l'intensité
   vaut la moitié entre le pic de la corticale et le fond. Raison : un seuil bas place la surface environ un
   écart-type du flou du scanner trop à l'extérieur. Sur le fantôme du test, le biais est mesuré à +0,60 mm (la
   théorie prévoit +0,64 mm) ; l'affinage le ramène à +0,16 mm. Le résidu vient de la corticale fine du fantôme
   (1,5 mm), dont le pic est atténué. Déplacement limité à ± 1,5 mm, ignoré si le contraste est < 300 HU, lissé
   sur le maillage.
5. **Contrôles** : étanchéité (chaque arête partagée par exactement deux triangles), orientation cohérente,
   nombre d'Euler (2 pour un os d'un seul morceau sans trou), volume ; normales vers l'extérieur. STL binaire
   en LPS (mm), comme l'export par défaut de 3D Slicer.
6. `segmentation.seg.nrrd` : toutes les étiquettes avec leurs noms et couleurs, au format « Segmentation » de
   3D Slicer (s'ouvre par-dessus la série DICOM pour vérifier ou retoucher).
7. **Bords du volume** (ajout de CT-CORA3D) : pour chaque os, les plans du bord du volume qu'il touche (là où il est
   coupé par le champ du scanner) sont notés dans `rapport.json` (`os.<nom>.bords_volume` : point et normale
   sortante, dans le système des STL). L'étape 6 s'en sert pour savoir si une extrémité articulaire manque.

### Étape 5 — contrôle et rapport

* **Hypothèse H2 du document Best_Position** (« contrôle : variation du seuil ± 50 HU ») : chaque os principal
  est re-segmenté à 176 et 276 HU dans la même zone. On mesure la distance de chaque sommet de la nouvelle
  surface à la surface de référence, avec une précision inférieure au voxel : `d ≈ (0,5 − g) / |∇g|`, où `g`
  est le masque de référence flouté, le même que pour le STL.
* `rapport.md` (lisible), `rapport.json` (tout), `apercu_3d.png`, `apercu_coupes.png`,
  `reperes_auto.mrk.json`.

### Étape 6 — repères anatomiques pour CORA (`etape6_reperes.py`)

Pour chaque `femur*.stl` et `tibia*.stl` du dossier (et `fibula*.stl` pour le tibia, `reperes_auto.mrk.json` pour
la tête fémorale), en ≈ 1,3 s par os :

1. **Orientation** : axe long par analyse en composantes principales ; extrémité proximale = côté de la tête fémorale
   (ou de la meilleure sphère) / extrémité la plus large du tibia (plateau). Sens anatomiques : fémur, médial = côté
   de la tête et caudal = côté de l'échancrure intercondylaire (plus grand creux de la section *remplie* entre les
   condyles) ; tibia, crânial = crête tibiale (saillie la plus éloignée du centre des sections du quart proximal) et
   latéral = côté de la fibula. Le **côté** (droit / gauche) découle du trièdre (latéral, proximal, caudal) ; il est
   comparé au côté lu dans le repère du scanner (avertissement si différent : la position déclarée du patient peut
   être fausse, ici un membre isolé).
2. **Complétude** : une extrémité qui touche le bord du volume (étape 4) est coupée → os refusé (il faut les deux
   articulations). STL seul, sans rapport : on cherche un « couvercle » plan ⊥ à un axe du scanner (> 80 mm² ;
   couvercles mesurés 122 et 146 mm², surfaces naturelles ≤ 47 mm²).
3. **Membre gauche** → image miroir (x → −x, ordre des sommets inversé) : tout est ensuite traité comme un membre droit,
   comme dans CORA 3D et la v2. La matrice scanner → os (4 × 4, déterminant −1 dans ce cas) est enregistrée.
4. **Repère de l'os en trois passes** (repères ⇄ repère) : X latéral, Y proximal, Z caudal. Tibia : Y = axe mécanique
   (éminence → centre distal) ; fémur : Y = axe anatomique (milieux de la diaphyse à 1/3 et 1/2, Tomlinson 2007) ;
   X = axe caudal des condyles (tangente commune). Origine : centre articulaire distal, au niveau de l'extrémité distale.
5. **Repères** (mêmes noms et définitions que CORA 3D) :
   * fémur : centre de la tête (sphère RANSAC puis moindres carrés) ; sommet du grand trochanter ; centre du col
     (barycentre de la surface du col dans une coquille de 1,1 à 1,6 rayon de tête : axe du col) ; points distaux et
     caudaux des condyles (tangentes communes = règle posée sur la radiographie ; points caudaux pris sous le centre des
     condyles + ½ rayon pour exclure une fabelle restée accolée) ; épicondyles ; fond de la trochlée (sillon suivi
     niveau par niveau sur la face crâniale ; point distal au niveau des centres des condyles) ;
   * tibia : éminence (milieu des sommets des tubercules intercondylaires) ; centres des plateaux médial et latéral et
     bords crânial / caudal du plateau médial (régions articulaires par croissance de région sur le maillage, normales à
     moins de 40° de celle du plateau) ; points caudaux des condyles (tangente commune derrière l'échancrure poplitée) ;
     tubérosité ; cochlée : sillons médial et latéral et crête intermédiaire sur l'**enveloppe haute** de la surface
     articulaire distale (elle est concave d'avant en arrière : le faisceau d'une radiographie de face est tangent à sa
     partie la plus profonde), centre distal = crête (ou milieu des sillons) en x et milieu des bords crânial et caudal
     en z ; malléoles (points les plus saillants ; la latérale sur la fibula).
6. **Angles** (mêmes formules que `mesurer()` de CORA 3D) et **torsion 3D**, enregistrés dans `cora_<os>.json`.
7. **Valeurs normales dans la définition du programme** : valeur publiée (travaux de l'équipe Vezzoni si elle existe,
   sinon littérature) + écart de définition, cet écart étant mesuré
   une fois pour toutes sur l'os sain du modèle CORA 3D (angle avec les repères détectés − angle avec les repères du
   modèle ; même os, donc seul le choix des repères diffère). aCdDFA n'a pas d'équivalent publié de même définition :
   sa référence est l'os sain du modèle mesuré par le détecteur.

Sorties : `cora_<os>.json` (repère, côté, complétude, repères dans le repère de l'os et dans celui du scanner, angles,
torsion, valeurs normales, ligne centrale), `cora_<os>.bin` (maillage dans le repère de l'os : nb sommets, nb triangles,
sommets float32, triangles uint32 ; `cora_<os>_fibula.bin` pour la fibula du tibia), `cora_<os>.png` (repères sur les
trois vues) ; résumé dans `rapport.md` / `rapport.json` (clé `cora`).

**Validation (`tests/test_reperes.py`, 13/10/2026).**

| Contrôle | Résultat |
|---|---|
| Os du modèle posés au hasard (4 poses dont 2 en miroir) : côté | 8/8 corrects |
| Repères robustes, écart au repère exact du modèle | fémur ≤ 0,84 mm (tête, trochanter, condyles, épicondyles) ; tibia ≤ 0,98 mm |
| Même os dans 4 poses : repères dans le repère de l'os | identiques (0,000 mm) |
| Angles frontaux (détecteur − modèle) | aLPFA +0,15°, aLDFA +0,01°, mMPTA +1,30°, mMDTA +0,14° |
| Écarts de définition sagittaux (repris dans les valeurs normales) | aCdDFA −8,2°, mCaPTA +9,5°, mCrDTA +5,1° |
| Torsion (détecteur / modèle) | fémur 27,1° / 29,7° ; tibia 1,0° / 0,7° |
| Lévrier : os coupés par le champ | 3/3 refusés (fémur genou → cheville, tibia hanche → genou, tibia pied) |
| Lévrier : fémur (hanche → genou), membre gauche | aLPFA 114,2°, aLDFA 96,3°, aCdDFA 88,7° : dans les normes ; antéversion 24,6° (normale, définition publiée ; 15,6° avec l'ancienne définition de CORA 3D) |
| Lévrier : tibia (genou → cheville), membre gauche | mMPTA 91,2°, mMDTA 96,5°, valgus 7,7°, mCaPTA 77,7°, mCrDTA 84,5° : dans les normes ; torsion tibiale −7,9° (normale ; +6,0° avec l'axe bimalléolaire) |
| Lévrier : os déplacé, puis en miroir | mêmes repères (0,00 mm), côté inversé en miroir |

Les angles sagittaux reposent sur des lignes articulaires courtes (20 à 30 mm) : 1 mm sur un bord arrondi du plateau ou
de la cochlée change l'angle de 2 à 3°. C'est la raison des écarts de définition ci-dessus, et une limite de toute
méthode par repères (voir aussi la validation de la v2).

**Torsion (définitions publiées).** Fémur : antéversion = angle, autour de l'axe de la diaphyse, entre l'axe du col
(centre de la tête → base du col au niveau du petit trochanter) et la ligne condylaire caudale (Al Aiyan 2021 :
31 ± 5° ; Longo 2022 : < 20° torsion externe, > 35° interne). Tibia : axe long par les centres de la diaphyse, ligne
condylaire caudale et axe antécochléaire (Brühschwein 2023) ; − = interne, + = externe (Méthodes de Longo 2022 ; le
résumé de cet article inverse les deux mots) ; normale ≈ −4°, anormale < −10° ou > +2°. Les anciennes définitions de
CORA 3D (axe du col au ras de la tête, axe bimalléolaire) classaient à tort le lévrier sain en torsion externe.

### Étape 7 — guides imprimables (`etape7_guide.py`)

Entrées : `prescription.json` (format v2.2, étape 12 de l'onglet CORA) et maillage de l'os planifié (repère de l'os).
Sorties dans `resultats/<série>/guide_<os>_<coin>/` (os fictif : `resultats/_os_fictif/…`) : `guide_coupe.stl` (à
imprimer d'une pièce), `guide_coupe_scanner.stl` (même guide dans le repère du scanner), `os_corrige.stl`, `guide.json`
(contrôles et mode opératoire), `guide.png`, les plans 2D, `guide_reduction.stl` s'il n'y a pas de verrou, et des
`.bin` pour l'affichage dans l'application (moitiés, pièce du coin, ponts ; moitiés verrouillées et broches de
verrouillage dans la position corrigée).

| Pièce | Conception |
|---|---|
| Coque | moulée sur l'os, jeu 0,3 mm, épaisseur 3 mm, ± 75° autour de la face d'appui, 8 mm au-delà des broches extrêmes, jamais à moins de 10 mm des extrémités articulaires ni à moins de jeu + épaisseur + 1 mm du cartilage articulaire ; **sans contre-dépouille** : le guide se pose par la face d'appui et chaque moitié se retire le long de ses broches (dépouille de 5°) |
| Os voisins | fibula, rotule, fabelles (repère de l'os planifié) : jeu dur ≥ 1 mm (distance signée calculée sur une sous-grille autour de chaque os voisin) et pas de matière sous eux dans les directions de pose et de retrait (ils entrent dans les cartes de hauteur) |
| Bras | si le cartilage ou un os voisin coupe la coque, les manchons isolés (et la 2e tour d'un coin de fermeture) sont reliés au reste du guide par des capsules du rayon des manchons, par-dessus l'os et hors du trajet de la lame ; connexité vérifiée sur la grille avec les fentes creusées |
| Fentes | 1 (ouverture) ou 2 (fermeture) fentes de 0,8 mm (lame 0,6 + 0,2), exactement dans les plans prescrits, parallèles à la charnière ; longueur = largeur de l'os + 2 mm ; tours d'au moins 13 mm au-dessus de l'os (inclinaison de la lame ≤ 0,9°), arêtes arrondies, entrée chanfreinée (0,5 mm à 45°) |
| Butée de profondeur | le haut de chaque tour est à la même distance D de la butée de sa fente (charnière, ou corticale opposée − 1 mm en coupe complète) ; D = la plus petite valeur qui garde le guidage, arrondie aux 5 mm (graduation de la lame), ou la longueur utile de la lame si on la donne (la scie bute alors sur les tours) ; gravée « P D » / « D D » sur la face extérieure des tours |
| Manchons | broches Ø 1,6 mm (trous 1,8 mm), 1 ou 2 par fragment selon la configuration (2 + 2, 1 + 1, 1 + 2), guidage 13 mm (ou la hauteur prescrite par la planification si elle est plus courte, jamais moins de 7,3 mm) ; les distales sont forées avec l'inverse de la correction |
| Moitiés et ponts | séparées par la fente proximale (la seule pour un coin d'ouverture) ; en fermeture avec verrou, la 2e fente sépare aussi : **3 pièces** (moitié proximale, pièce du coin, moitié distale). Ponts sécables de 2 × 5 mm en haut des parois d'extrémité de chaque fente de séparation. Après la coupe, on coupe les ponts, la pièce du coin sort la première, et chaque moitié glisse le long de **ses** broches, parallèles entre elles ; la moitié qui s'éloigne de l'autre sort en premier (fermeture : distale ; ouverture : proximale) |
| Verrou de réduction (« 2 en 1 ») | une oreille par moitié de chaque côté du trait, au-delà du bout des tours, perpendiculaires à la direction finale des broches et superposées dans la position corrigée réelle (trait de scie compensé en fermeture : T − s·n₁) ; trou traversant dans l'oreille du haut (moitié qui sort la première), borgne dans celle du bas ; une broche de verrouillage les traverse. Oreilles adaptées côté par côté (écart vertical, décalage vers l'extérieur ≤ 10 mm) pour qu'avant la correction les moitiés restent séparées et qu'aucune, en glissant sur ses broches (retrait, remise en place), ne balaie l'oreille de l'autre ; côté abandonné s'il toucherait un os voisin, le cartilage ou une broche, l'autre côté recevant alors deux trous (deux broches de verrouillage à 2 Ro + 0,4 mm : rotation autour des broches bloquée). Chaque moitié évite aussi, dans la position où on la remet (après la correction), les os voisins déplacés (jeu jv) et le fragment osseux de l'autre moitié sur 12 mm de part et d'autre du trait (jeu j) : contraintes ajoutées au champ dur G, pour la moitié proximale dans la position corrigée, pour la distale par T⁻¹ |
| Guide de réduction séparé | sans verrou (paramètre V = 0, ou aucun côté possible) : barre (enveloppe convexe des broches vue le long des broches) à ≥ 4 mm de l'os corrigé et des os voisins corrigés, et manchons parallèles terminés par des **butées moulées sur l'os corrigé** (6 degrés de liberté) |

**Guide générique** (`PARAMETRES_GUIDE`, `parametres_du_cas`, `dimensions_guide`) : 25 dimensions de conception (jeu,
coque, guidage, paroi, lame, jeu de fente, broche, jeu du manchon, marge, secteur, ponts, dépouille, congés, épaisseur
minimale, jeux aux voisins et au cartilage, profondeur de lame, dépassement, chanfreins, verrou, écart et épaisseur des
oreilles, guide de réduction séparé), valeur par défaut dans `parametres.py`, valeur du cas
dans `prescription.parametres_guide` (bornes vérifiées) ; les autres dimensions découlent de l'os (largeur dans le plan
de coupe, position des broches, étendue de la coque…) et sont rendues dans `guide.json` (`dimensions_guide`).

**Plans 2D** (`dessin_guide.py`) : `plan_generique` (schéma coté en symboles, tableau des paramètres et formules) et
`plan_guide` (projections orthogonales A–D du guide construit, cotes, tableau, cartouche, échelle 2:1, 1:1 ou 1:2 sur A3)
en SVG, PDF et PNG ; parties cachées par un tampon de profondeur (z-buffer) écrit en numpy : chaque pixel garde le
triangle le plus proche (test au centre du pixel, triangles groupés par taille de boîte englobante, une seule passe,
maximum d'une clé « profondeur codée sur 31 bits | n° de triangle ») ; faces arrière des solides fermés ignorées ;
≈ 180 points par pouce sur la feuille. Il remplace deux rendus matplotlib de triangles subdivisés (algorithme du
peintre) : vue 15 à 24 fois plus rapide (0,3–0,4 s au lieu de 6,3 s), et plus juste (le liseré des triangles de
l'ancien rendu masquait les bords de l'ouverture des fentes et des morceaux de contour).

**Temps de calcul (22/10/2026)** : guide complet avec plans, cas du tibia en fermeture avec verrou : 86,5 s → 23,5 s,
résultats identiques au bit près (`guide.json` comparé). Outre les plans : recherches dans les arbres k-d sur tous les
cœurs (`workers=FILS`, 5 fois plus rapide ; `FILS` respecte OMP_NUM_THREADS des campagnes) ; distances entre pièces
par `ecart_min` (recherches de longueur croissante, 0,5 mm puis × 3 : le coût de `min_gap` croît comme le cube de la
longueur de recherche quand les pièces sont proches, 2,8 s à 5 mm contre 0,05 s) ; `vtk_leger.py` n'importe que les
classes VTK utilisées (0,5 s au lieu de 2,2 s au démarrage).

Méthode (modélisation implicite) : grille de 0,3 mm alignée sur la direction de pose ; distance signée à l'os (signe
par voxelisation VTK, valeur exacte point-triangle en numpy avec un arbre k-d) ; union lisse des primitives (congés de
0,8 mm) ; contraintes dures : jeu ≥ J + 0,04 mm partout, et pour chaque moitié aucune matière « sous » l'os vu depuis sa
direction de retrait (carte de hauteur de l'os et cône de dépouille) ; parties de moins de 1,2 mm supprimées (ouverture
morphologique) ; isosurface (Flying Edges) puis solide exact (manifold3d) ; fentes, trous et séparation des moitiés par
booléens exacts ; sommets à moins du jeu repoussés le long de la normale à l'os (≤ 0,15 mm : erreur d'interpolation
de l'isosurface là où la distance n'est pas lisse) ; STL relu comme par un logiciel d'impression (étanchéité vérifiée,
reconstruction et simplification ≤ 0,001 mm, puis décollement des pincements de 2 µm si besoin). Les ponts débordent de
la tour pour qu'aucune face ne soit presque confondue avec une face de la tour (source de pincements). Les oreilles du
verrou sont ajoutées par booléens exacts (hors de l'union lisse, qui boucherait leur écart) ; la dalle de séparation
les épargne ; leur placement est vérifié par distances exactes (`min_gap`) et par le volume balayé par chaque pièce
convexe d'une oreille glissée de 30 mm le long des broches (enveloppe convexe).

Contrôles indépendants de la construction (`guide.json`) : jeu minimal mesuré (distance exacte aux triangles de l'os),
volume d'interpénétration (booléen exact), surface d'appui du guide et de chaque moitié (et couverture angulaire), nombre
de pièces après la coupe des ponts, pièces détachées, présence de chaque manchon (matière dans sa couronne), retrait de
chaque pièce sans heurter l'os (lancer de rayons le long des broches, 4000 points par moitié) ni l'autre moitié
(balayage exact de 0,25 à 30 mm ; moins de 0,5 mm³ d'interpénétration = frottement de parois, pas un blocage ; pièce du
coin : première direction libre parmi la face d'appui et les axes des fentes), broches hors du trajet de la lame, distance des broches aux plans de coupe et aux
extrémités, guide et broches (manchons compris) contre les os voisins et le cartilage, fibula à ostéotomiser, butée
(profondeur de lame de chaque fente) ; verrou dans la position corrigée réelle : moitiés sans contact entre elles ni avec
l'os corrigé et les voisins corrigés, remise en place de la moitié du haut le long de ses broches, trajet de la
correction moitiés en place (3 poses intermédiaires, exp(s · log T)), broche de verrouillage qui passe, et
**sensibilité** : la pose distale perturbée de 1° (autour de l'axe de l'os, des fentes, des broches, passant par le
centre de la section) ou de 0,3 mm (le long de l'os, du trait) bloque la broche — chaque broche de verrouillage suit le
trou de l'oreille du haut et est enfoncée jusqu'au fond du trou borgne déplacé, pour qu'un fond qui monte le long de la
broche ne compte pas comme un blocage ; guide de réduction séparé s'il existe (barre, parallélisme, butées, os
voisins corrigés) ; étanchéité des STL relus.

Règles ajoutées après la campagne du 21/10/2026 :
* **sensibilité exigée dès la conception** (`tolerances_verrou`) : plus petite rotation détectée autour de chaque axe du
  verrou passant par K = jeu radial / bras de levier, le bras étant pris aux deux bouts de la partie cylindrique de
  chaque trou du bas (autour de l'axe de l'os ou des fentes : hauteur du trou au-dessus de K le long des broches). Un
  verrou dont le calcul dépasse 0,9° (`MARGE_VERROU` × `TOL_VERROU_DEG` = 0,9 × 1°) est refusé comme un côté impossible
  (à un côté : essai à deux broches, puis guide de réduction séparé). Le test booléen ci-dessus vérifie ce calcul à 1° ;
  la marge de 10 % vient de ce qu'il ne compte un blocage qu'au-delà de 0,001 mm³ d'interférence (≈ 0,01 mm de
  chevauchement en plus du jeu de 0,1 mm) : sans elle, 3 verrous à 0,91–0,94° passaient le calcul mais pas le test ;
* **appui insuffisant en abord non usuel** : l'alerte dit qu'un os voisin couvre la face d'appui et rappelle le type de
  coin conseillé par la planification (la campagne range ce cas parmi les conséquences attendues d'un coin forcé, si la
  fibula est aussi sur le trajet de la lame côté face d'appui) ;
* **oreilles rattachées** : chaque oreille doit appartenir à la pièce finale de sa moitié (un bout de tour isolé par un os
  voisin partirait avec ses oreilles parmi les pièces écartées) ;
* **pièce du coin d'un seul tenant** : en fermeture « 2 en 1 », les composantes du coin (entre les deux dalles) retenues
  par les ponts doivent être une seule ; sinon deux bras relient les faces côté coin des deux tours (`isoles`), en deçà
  du bout des tours.

Règles ajoutées le 22/10/2026, après la remarque de Dorian sur un tibia (coin de fermeture d'un varus, posé du côté de
la fibula : « comment le chirurgien enfile-t-il le guide ? ») :
* **espace entre l'os et un os voisin interdit** (`EntreOs`) : couche par couche de la grille (son 3e axe suit l'os),
  enveloppe convexe (scipy, Qhull) des échantillons de surface de l'os et du voisin à ± 0,75 mm, moins l'enveloppe de
  l'os seul ; champ ≈ distance signée (min de −d(enveloppe commune), +d(enveloppe de l'os)), ajouté au champ dur G : ni
  coque, ni tour, ni manchon, ni bras dans cet espace ; oreilles du verrou refusées (ou écartées) si un de leurs sommets
  y tombe. Les creux de l'os gardent leur coque (c'est l'enveloppe de l'os seul qui est retranchée) ; sur un abord usuel
  (face médiale du tibia), rien ne change ;
* **refus motivé** (`verifier_abord`, exception `GuideImpossible`) : abord non usuel ET os voisin sur le trajet de la
  lame par la face du coin (`strategie.voisin_sur_lame`, exporté par le cœur JavaScript) → pas de guide de coupe, message
  pour le chirurgien avec le coin conseillé ; l'onglet CORA l'explique à l'étape 12 au lieu du bouton « Construire ». La
  campagne range ce refus parmi les conséquences attendues d'un coin forcé ;
* **pièce détachée « fonctionnelle »** : seulement si elle porte une partie GUIDANTE de tour (au-dessus de la coque,
  h > hmax + j + e) ou de manchon (au-delà de t_os + j + e). Un îlot de coque au pied d'une tour, coupé par l'espace
  interdit près de la fibula (tibia proximal, abord latéral), est un îlot sans fonction, écarté avec un simple
  avertissement.

**Validation (`tests/test_guide.py`, guide v3, 21/10/2026).**

| Cas | Résultat |
|---|---|
| Os coudé synthétique (15° de varus), coin de fermeture | aucune alerte ; jeu 0,31 mm, interpénétration 0 ; 3 pièces retirables (coin, distale, proximale) ; fentes vides dans les plans prescrits (0,000 mm³), parois pleines, entrées chanfreinées ; trous coaxiaux aux broches ; butée D = 30 mm, haut des tours à D de la charnière (lancer de rayon : écart 0,000 mm) ; verrou des deux côtés : la broche passe, 0,3 mm de décalage la bloque, 1° (3 axes) et 0,3 mm (⊥ broches) bloquent ; rotations détectées dès 0,2 à 0,4° |
| Même os, coin d'ouverture + dérotation de 12° | idem avec 2 moitiés (proximale d'abord) ; D = 35 mm (coupe complète) ; angle entre les paires de broches 19,19° = prescription ; verrou des deux côtés (écart vertical adapté d'un côté) |
| Même os, fermeture + os voisin et cartilage | jeu 1,03 mm au voisin, coque hors du cartilage, appui ≥ 100 mm² par moitié, verrou des deux côtés |
| Fémur réel du lévrier, coin de fermeture, torsion de test 15° | aucune alerte ; jeu 0,33 mm ; 3 pièces ; D = 40 mm ; broches inclinées de 36° sur les tours : verrou des deux côtés, l'un écarté vers l'extérieur (balayage) ; 14 s |
| Tibia réel du lévrier, coin d'ouverture | aucune alerte ; jeu 0,31 mm ; D = 35 mm ; verrou des deux côtés ; 15 s |

Essais complémentaires (8 cas : fémur et tibia réels, os fictif, fermeture et ouverture, avec et sans torsion) : aucune
alerte, alors que la construction de la v2 laissait la tour de fente dans l'os sur les coins d'ouverture obliques réels.
Trois fonctions de VTK 9.7 ne sont plus utilisées : `vtkImplicitPolyDataDistance` (plantages intermittents),
`vtkOBBTree.IntersectWithLine` (renvoie parfois « impact » sans intersection) et `vtkSelectEnclosedPoints` (faux
positif) ; elles sont remplacées par la distance exacte en numpy, le comptage des seules intersections réelles et le
volume d'interpénétration exact.

**Campagne de simulation (14/10/2026, `tests/campagne_export.mjs` + `tests/campagne_guides.py`).** 640 cas sur l'os
fictif (fémur et tibia, varus / valgus × aucun / procurvatum / recurvatum, F 5–30°, S 3–25°, apex 25–85 %, torsion
−30 à +30°, fermeture et ouverture ; 320 cas tirés au hasard avec une graine jamais utilisée pendant le développement) :
**640 sans erreur** (avant les corrections : 46 sur 480, 10 %). Broches placées et retrait garanti 640/640, règle 2 dans
178 cas, angles après correction à 0,016° près, jeu guide–os 0,29 à 0,32 mm, guide à ≥ 1 mm des os voisins et à
≥ 1,5 mm du cartilage. Détails : `../resultats/_campagne_os_fictif/`.

## cora/ — la planification CORA (JavaScript)

Reprise de `../../CORA3D/code_source/` (originaux intacts) ; même structure (`app/cora_simple.js` = cœur de calcul,
`app/modules/*.js` = interface, `build_app.py` = assemblage en un seul fichier). Ajouts :

* **Os segmenté** : `modeleReel(json, maillages)` met l'os segmenté sous la forme du modèle synthétique (méta-données
  + maillages) : toute la planification (déformité, découpe, correction, broches, export, torsion) fonctionne telle
  quelle. `planifier(…, { sansDeformite: true })` analyse l'os tel quel (pas de vérité terrain).
* **Référence « valeurs normales »** (`axesNormales`) : sans os sain de référence, l'axe de chaque segment est construit
  depuis ses JOL et les angles normaux, dans chaque vue (méthode de Paley), puis combiné en 3D. Tibia : axes mécaniques
  par l'éminence et le centre distal. Fémur : axe proximal = axe anatomique ; axe distal : direction depuis les JOL
  distales, position de face comme l'axe sain du gabarit (`gabaritFemur`, os sain du modèle), de profil par la règle
  « une seule angulation » (même niveau de CORA que de face). Le fémur du chien est arqué vers crânial (lévrier : condyles
  33 mm en arrière de l'axe proximal) : un gabarit de profil serait faux d'un chien à l'autre.
* **Référence « os avant déformité »** (déformité de test) : l'os réel non déformé joue le rôle du membre
  controlatéral, comme l'os sain dans CORA 3D.
* **Robustesse** : axes parallèles (θ < 0,5°), CORA hors de l'os ou hors de la section → pas d'ostéotomie
  (`osteoPossible`), explication dans les étapes 9 à 12 ; angles hors normes (± 2 écarts-types) listés (`anomalies`).
* **Torsion et dérotation** : torsion mesurée avec les définitions publiées ; si elle sort de la normale (ou diffère
  de l'os avant déformité de test), la correction ajoute une dérotation autour d'un axe que la correction garde aligné
  (fermeture : axe distal, avant la fermeture ; ouverture : axe réaligné, après), ajustée par la méthode de la sécante.
  Seuil : 1°. Déformité de test : torsion τ réglable.
* **Système de réduction** : broches 2 + 2 (défaut), 1 + 1 ou 1 + 2 (deux distales côte à côte au même niveau)
  (`CONFIG_BROCHES`), les distales forées avec l'inverse de la correction ; toutes parallèles après correction ; guide
  de réduction construit à l'étape 7.
* **Stratégie chirurgicale** (`planifier`, section 7) :
  - zones articulaires : carte du cartilage du modèle (`cart`, ≥ 128) ou, sur un os segmenté, zones géométriques
    (`ZONE_ARTICULAIRE`) ; os voisins : fibula (maillage du tibia), rotule et fabelles (`VOISINS`, déformées avec l'os) ;
  - règle 2 de Paley : si un trait passe à moins de `MARGE_COUPE_CARTILAGE` (5 mm) du cartilage ou si le coin de
    fermeture contient du cartilage, la coupe remonte vers la diaphyse (pas de 1 mm, ≤ 35 % de la longueur) ; l'ACA reste
    sur la bissectrice du CORA (axes réalignés exactement) à la position λ qui garde les faces en contact :
    ((R − I)(H − Cc − λ c))·n = 0 avec n = u (fermeture : faces confondues) ou b (ouverture : arête de charnière sur la
    face proximale) ; le fragment glisse de |(R − I)(H − Q)| le long de la coupe ;
  - abord (`ABORDS`, `choisirAbord`) : la lame entre du côté opposé à la charnière, par la face du coin (convexe en
    fermeture, concave en ouverture). Face du coin dans un secteur d'abord et lame libre de tout os voisin (tours de
    fente de `toursFente`) → guide sur cette face, charnière conservée ; sinon face accessible la plus proche à
    ≤ `ANGLE_ENTREE_COIN_MAX` (60°) → ostéotomie complète ; au-delà → coin « non réalisable par un abord usuel »
    (`abordNonUsuel`), guide laissé sur la face du coin et l'autre coin recommandé ;
  - type de coin (`recommanderCoin`) : critères ordonnés accès, charnière conservée, règle 1, coin assez épais pour deux
    fentes, ouverture ≤ `OUVERTURE_MAX_FRAC` (40 %) de la largeur, longueur, stabilité ; le premier qui départage décide ;
  - niveau du trait z (mm depuis le CORA, règle 2 si z ≠ 0) et profondeur de charnière y (`CHARNIERE_RETRAIT` = 2 mm
    par défaut ; pont ≤ `PONT_MAX` = 3 mm, sinon ostéotomie complète et coin mixte), choisis dans l'interface ;
  - contraintes biologiques au niveau du trait (`contraintesCoupe`) : cartilage, tubérosité tibiale, épicondyles, physes
    (`ZONE_PHYSE`, chien en croissance), longueur des fragments (`FRAGMENT_MIN_MM`), consolidation, translation de la
    règle 2, structures de l'abord (`STRUCTURES_ABORD`) ;
  - broches (`placerBroches`, `evaluerBroche`, `manchonLibre`) : bicorticales, ≥ 2 mm des plans de leur fragment et
    pointe hors du trajet de la lame de l'autre trait (≥ 1,6 mm, sans le traverser), ≥ 3 mm du cartilage (manchon :
    rayon + 0,5 mm), ≥ 2 mm des sommets des os voisins jusqu'à 8 mm au-delà de la corticale opposée (5 mm prévus + 3 mm
    d'erreur de forage ; manchon : rayon + 1 mm), manchon hors des tours de fente, entrée ≤ 50° de la normale ; recherche : rotation β (0 à ± 45°), distance à la coupe, disposition (l'une
    derrière l'autre 10 / 8 / 6,5 mm, côte à côte 6,5 à 9 mm), décalage de la paire (0, ± 2, ± 4 mm), manchons distaux
    15 / 10 / 8 mm ; une moitié du guide doit pouvoir sortir sans heurter l'autre (dérive ≤ 0,03), au besoin en inclinant
    les broches de γ = ± 10 ou ± 20° le long de l'os ; évaluations en cache.
  - prescription : `strategie.regle_paley`, `abord`, `osteotomie_complete`, `translation_osteotomie_mm`,
    `charniere.axe_correction_point`, `broches_reduction[].hauteur_manchon_mm`, `placement_broches`, `alertes`.
* **Préréglages cliniques** (`PRESETS_DEFORMITE`) : 17 déformités avec contexte et référence.
* **Guide générique** (`PARAMS_GUIDE`, `appliquerInstrument`) : 21 dimensions modifiables dans l'interface (les 19 de
  l'étape 7 + écart et distance des broches, qui servent à la planification).
* **Prescription** (format v2.2 = v2.1 + `broches_reduction`, `guide_reduction`, bloc `torsion`, dérotation et
  `T_4x4` total) : pour un os segmenté, bloc `os_segmente` (série, côté, miroir, matrice `os_vers_scanner`). La v2 lit
  toujours ce fichier (elle ignore les ajouts).
* **Os détecté** : l'onglet CORA prend l'os complet détecté dans la série ouverte dans l'onglet 1 (`cora_cas.json`).
* **Références de normalité** (publications seulement) : « Vezzoni » par défaut (aLDFA 94 ± 3,3° de Vezzoni L 2022,
  mMPTA 93,3 ± 1,78° d'Olsen, Vezzoni 2016, mCaPTA = 90° − TPA des Labradors sains de Guénégo, Vezzoni 2021 :
  26,3°, étendue 20,4–30,8°, écart-type estimé = étendue / 4 ; les autres angles prennent la littérature),
  « Littérature » (Tomlinson 2007 Labrador, Dismukes 2007-2008…), « Race » (Tomlinson 2007 pour le fémur ; Wilke 2002
  pour la pente tibiale du lévrier et du Labrador) ; toujours + écart de définition des repères automatiques. Le
  tableau de l'étape 1 compare ces références et ajoute la TPA (= 90° − mCaPTA). `etape6_reperes.py` applique la même
  règle (dictionnaire `VEZZONI`, sinon `LITTERATURE`).

**Validation (`tests/test_reel.mjs`)** sur le fémur et le tibia du lévrier : avec la référence « os avant déformité »,
les 6 déformités de test (varus / valgus × aucun / procurvatum / recurvatum, 15° + 10°) sont retrouvées à moins de
0,001° ; angles après correction = angles avant déformité (≤ 0,002°) ; translation résiduelle ≤ 0,006 mm ; broches
parallèles après correction ; matrice os → scanner exacte. Avec la référence « valeurs normales » (préréglage
Vezzoni), θ est retrouvé à 4,4° près (fémur) et 5,2° près (tibia) : c'est l'écart naturel de ces os aux normes (la borne
Vezzoni de l'aLDFA est celle du berger allemand ; 1,1° près avec la valeur du Labrador). `tests/test_cas.mjs` (os fictif)
passe toujours sans changement.

**Campagne de la stratégie (`../tests/campagne_strategie.mjs`, 19/10/2026)** : 606 cas (17 préréglages avec leurs
variantes, 300 cas tirés au hasard), les deux coins de chaque cas : 606 sans erreur sur les règles R1 à R9 (guide jamais
du côté de la charnière, abords, coin recommandé réalisable, broches, parallélisme, résiduels nuls, niveau et charnière
demandés, angles après correction). Guides de 102 de ces cas : 102 sans erreur.
Rapports : `../resultats/_campagne_strategie/`.

## Points nommés (`resultats/<série>/graines.json`)

```json
{"points": [{"nom": "femur", "position": [18.0, -41.0, -186.6], "systeme": "LPS"}]}
```

Chaque point donne son nom au segment qui le contient, ou à défaut au segment le plus proche à moins de 3 mm. Si
un segment contient des points de plusieurs noms, il est séparé : une croissance de région part de boules de
2,5 mm autour des points, et la frontière se place dans la vallée la moins dense entre eux. Le nom `autre` veut
dire « ni exporté, ni renommé automatiquement ». L'application écrit ce fichier quand on corrige un résultat ;
la ligne de commande le relit à chaque calcul.

## Limites connues

* **Une série = un examen.** Les trois séries du dossier ont des repères (`FrameOfReferenceUID`) différents :
  elles ne sont pas recollées en un seul membre.
* **Articulations très serrées** (hanche, tarso-crurale) : traitées par la sphère (hanche) et par l'arbre des
  seuils ; sur un autre scanner, contrôler visuellement et corriger par des points si besoin.
* **Os du tarse** : séparés individuellement à 0,27 mm de pixel, partiellement à 0,56 mm ; `tarse.stl` les
  réunit tous de toute façon.
* **Côté gauche / droit** : déduit de x (LPS) quand il y a deux membres. C'est correct seulement si l'animal a
  été enregistré dans la bonne position sur la console du scanner.
* **Mémoire** : ≈ 2 Go pour une série de 750 coupes de 512 × 512.
* **Étape 6** : repères automatiques sans contrôle humain ; les vérifier sur `cora_<os>.png` ou à l'étape 1 de l'onglet
  CORA. Testée sur un seul chien (lévrier) et sur le modèle synthétique ; un os très déformé, un implant, un cal ou un
  petit chien peuvent tromper une heuristique (crête tibiale, échancrure, sillon trochléen). L'axe du col fémoral (donc
  l'antéversion) est indicatif.
* **Application autonome** (PyInstaller) : `parametres.py` y prend le dossier du projet noté à la construction
  (`construction.json`), sinon `~/Documents/CT-CORA3D` ; la calibration des repères (`calibration_reperes.json`) est
  livrée dans le paquet (sa clé, l'empreinte de `etape6_reperes.py`, n'y est pas recalculable).
* **Étape 7** : prototypes de recherche, non validés cliniquement. Imprimer d'abord des coupons de fente et de manchon
  pour régler les jeux (0,2 mm) selon l'imprimante et le matériau ; la plaque d'ostéosynthèse n'est pas modélisée (les
  broches peuvent la gêner) ; tissus mous non modélisés (étendue de l'abord à vérifier) ; avec une dérotation, la
  translation de la règle 2 ou un abord qui n'est pas la face du coin, la charnière corticale ne peut pas être conservée
  (ostéotomie complète). Secteurs d'abord et marges : choix raisonnés, à valider avec un chirurgien.
