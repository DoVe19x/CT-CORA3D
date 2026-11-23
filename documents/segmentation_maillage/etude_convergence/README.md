# Étude de convergence du maillage éléments finis (tibia du lévrier)

**Étude principale : `etude_geometrie_figee.py`.** Comme dans Abaqus, la géométrie est figée (un tibia simplifié à
sections de 16 côtés, 640 hexaèdres, 861 nœuds, 75,2 cm³, tiré du STL) et seul le maillage change : chaque hexaèdre
est coupé en k × k × k (k = 1, 2, 3...), les tétraèdres sont tirés des mêmes hexaèdres (12 par hexaèdre). Les courbes
montent (ou descendent) puis atteignent un plateau de 9,62 MPa. Contrôle : avec F / 2 et 2 F, les contraintes sont
exactement divisées ou multipliées par 2 et le plateau est atteint au même nombre de nœuds (élasticité linéaire).
Résultats : `resultats/convergence_figee.csv`, figures `../images/figee_*.pdf`.

`etude_convergence.py` est la première étude, avec des maillages libres qui suivent le STL (TetGen, balayé, voxels) :
moins propre (la géométrie change avec la taille des éléments), mais elle montre trois pièges (nœuds milieux,
voxels, singularité). Figures `../images/libre_*.pdf`.

Étude « comme dans Abaqus » : on calcule le même problème avec des maillages de plus en plus fins et quatre types
d'éléments, et on trace la contrainte (MPa) en fonction du nombre de nœuds. Le calcul est fait par un petit code
d'éléments finis en Python (`ef.py`) qui reprend exactement les éléments d'Abaqus (même ordre des nœuds, même
intégration). Chaque maillage est aussi écrit en fichier `.inp`, pour refaire l'étude dans Abaqus.

## Le problème

| | |
|---|---|
| Géométrie | `exemples/greyhound_hindlimb_knee_to_ankle/tibia.stl` (247 mm, 82,2 cm³), dans ses axes principaux : x le long de l'os, vers le genou |
| Matériau | élastique linéaire isotrope homogène, E = 17 000 MPa, ν = 0,3 (os cortical) ; le STL est plein (canal compris) |
| Appuis | encastrement des nœuds à moins de 10 mm de l'extrémité distale |
| Charge | F = (−300 ; 30 ; 0) N : compression et flexion, en charge volumique uniforme dans les 15 mm du côté du genou |
| Résultat suivi | contrainte de von Mises maximale aux nœuds (moyennée entre éléments, comme Abaqus) entre 40 et 60 % de la longueur |

## Les éléments et les maillages

| Élément | Abaqus | Maillage |
|---|---|---|
| tétraèdre linéaire | C3D4 | surface remaillée uniformément (pyacvd), puis TetGen |
| tétraèdre quadratique | C3D10 | le même, avec un nœud au milieu de chaque arête |
| hexaèdre linéaire | C3D8 | maillage balayé le long de l'os (« sweep ») : grille en « O » qui suit le contour de chaque section |
| hexaèdre quadratique | C3D20 | le même, avec un nœud au milieu de chaque arête |
| comparaison | C3D10, C3D20 | les mêmes avec les nœuds milieux au milieu d'arêtes droites (familles `*_droites`) |
| contre-exemple | C3D8, C3D20 | hexaèdres « voxels » (cubes de côté h, surface en escalier) |

Pour C3D10 et C3D20, les nœuds milieux des arêtes de surface sont placés sur la surface courbe de l'os, comme Abaqus
les place sur la géométrie : projection sur le STL (tétraèdres) ou même transformation que les sommets (balayé).

## Fichiers

| Fichier | Rôle |
|---|---|
| `ef.py` | fonctions de forme, assemblage, résolution (direct ou gradient conjugué + multigrille), contraintes aux nœuds, écriture `.inp` |
| `maillages.py` | maillages de l'os (TetGen, balayé, voxels) et de la poutre de validation |
| `validation_poutre.py` | vérification du code : fonctions de forme, poutre console comparée à la théorie des poutres |
| `etude_geometrie_figee.py` | l'étude principale (géométrie figée) ; écrit `resultats/convergence_figee.csv` et `../images/figee_*.pdf` |
| `etude_convergence.py` | l'étude avec maillages libres ; écrit `resultats/convergence.csv` et `../images/libre_*.pdf` |
| `images_maillages.py` | images des maillages (`../images/maillages_tibia.png`, `section_o.pdf`, `figee_maillages.png`) |
| `resultats/` | `convergence.csv`, `validation_poutre.csv` et les figures en PNG |
| `abaqus/` | un fichier `.inp` par maillage de l'étude principale, `tibia_figee_<élément>_k<k>.inp` (21 fichiers, ≈ 240 Mo, non suivi par Git, refait par `--inp`) |

## Lancer

```bash
python -m venv .venv_ef
.venv_ef/bin/pip install -r requirements.txt
.venv_ef/bin/python validation_poutre.py              # ≈ 1 min
.venv_ef/bin/python etude_geometrie_figee.py --inp    # étude principale, ≈ 15 min ; reprend là où il s'était arrêté
.venv_ef/bin/python etude_convergence.py --inp        # maillages libres, ≈ 40 min
.venv_ef/bin/python etude_geometrie_figee.py --figures    # figures seules, depuis le CSV
.venv_ef/bin/python images_maillages.py
```

## Refaire l'étude dans Abaqus

Chaque fichier `abaqus/tibia_figee_<élément>_k<k>.inp` est complet : nœuds, éléments, matériau
`OS_HOMOGENE`, ensembles `ENCASTREMENT` (nœuds), `CHARGE` et `MILIEU` (éléments), charge volumique `*Dload BX, BY, BZ`
et un pas statique. Dans Abaqus/CAE : File, Import, Model, puis Job, Submit ; ou en ligne de commande :
`abaqus job=tibia_figee_C3D8_k3 interactive`. Dans le Visualization, afficher S, Mises (valeurs aux nœuds moyennées,
réglage par défaut) et lire le maximum sur l'ensemble `MILIEU`. Petite différence attendue : Abaqus extrapole les
contraintes depuis les points de Gauss, `ef.py` les évalue directement aux nœuds ; les deux convergent vers la même
valeur. Pour l'élément hexaédrique par défaut d'Abaqus, remplacer `type=C3D8` par `type=C3D8R` dans la ligne
`*Element` (intégration réduite avec contrôle du hourglass, non programmée dans `ef.py`). Le `.inp` n'a pas pu être testé dans Abaqus (pas de
licence sur la machine où il a été écrit) : le format suit le manuel d'Abaqus, et le même maillage, avec les mêmes
conditions, est résolu par `ef.py`.
