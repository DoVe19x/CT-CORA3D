# Campagne de simulation des guides — 2026-10-19 09:03

102 cas, **102 sans erreur** (100 %, dont 7 coins forcés en abord non usuel : conséquences attendues, voir plus bas), 0 avec au moins une erreur.

## Planification (cœur de calcul)

102 cas : fémur 36, tibia 66 ; F 0–28°, S 0–15°, apex à 0.27–0.82 de la longueur.

| Contrôle | Résultat |
|---|---|
| Broches placées (toutes les règles respectées) | 102 / 102 |
| Retrait des deux moitiés garanti | 102 / 102 |
| Règle 2 de Paley (coupe hors du cartilage) | 33 |
| Angle vrai retrouvé (écart max) | 0.0026° |
| Angles articulaires après correction (écart max à l'os sain) | 0.0049° |
| Angle résiduel entre les axes (max) | 0.000001° |
| Translation résiduelle entre les axes (max) | 0.019 mm |
| Broches parallèles après correction (écart max) | 0.000001° |
| Translation à l'ostéotomie, règle 2 (max) | 8.0 mm |

Abord changé (guide par l'abord usuel, ostéotomie complète) :

* hors des abords chirurgicaux usuels : 24
* la rotule est sur le trajet de la lame : 1

Adaptations du placement des broches et alertes de planification :

* paire de broches décalée de la ligne centrale : 40
* broches tournées autour de l'os : 22
* coin de fermeture trop fin pour deux fentes (ouverture conseillée) : 7
* broches côte à côte (fragment court) : 3
* translation de la règle 2 > 50 % de la largeur : 1

## Erreurs par type

| Type | Cas |
|---|---|

## Avertissements

| Type | Cas |
|---|---|
| coupe 1 : la fibula croise le plan de coupe | 66 |
| coupe 2 : la fibula croise le plan de coupe | 33 |
| planification : règle 2 de Paley | 33 |
| planification : broches du fragment distal décalées de 2 mm de la ligne centrale de l'os | 33 |
| planification : coin non réalisable par un abord usuel | 18 |
| planification : face du coin caudale | 13 |
| planification : face du coin crâniale | 11 |
| étape 7 : fentes très proches | 10 |
| planification : broches tournées de -10° autour de l'os | 9 |
| planification : charnière | 8 |
| guide : îlot(s) de coque isolé(s) par le cartilage ou un os voisin, écarté(s) | 8 |
| planification : coin de fermeture trop fin | 7 |
| planification : broches du fragment distal décalées de 4 mm de la ligne centrale de l'os | 4 |
| planification : broches tournées de -20° autour de l'os | 3 |
| planification : broches inclinées de 10° le long de l'os | 3 |
| planification : broches du fragment proximal décalées de 2 mm de la ligne centrale de l'os | 3 |
| planification : fragment distal court | 3 |
| planification : broches tournées de 5° autour de l'os | 2 |
| planification : broches tournées de 45° autour de l'os | 2 |
| planification : broches tournées de 10° autour de l'os | 2 |
| planification : broches tournées de -45° autour de l'os | 2 |
| appui : moitié distal n'embrasse que 51° de l'os | 1 |
| planification : broches tournées de 25° autour de l'os | 1 |
| planification : broches tournées de -5° autour de l'os | 1 |
| planification : translation | 1 |
| planification : face du coin crânio-latérale | 1 |

## Conséquences attendues d'un abord non usuel

Coins forcés alors que la planification les déclare non réalisables par un abord usuel (elle recommande l'autre type de coin) : l'os voisin sur le trajet de la lame confirme l'avertissement.

| Type | Cas |
|---|---|
| coupe 1 : fibula sur le trajet de la lame | 7 |
| coupe 2 : fibula sur le trajet de la lame | 4 |
| étape 7 : partie(s) de tour de fente ou de manchon détachée(s) du guide | 2 |

* `0001_tibia_tib-valgus-prox_2+2_défaut_ouverture` : étape 7 : partie(s) de tour de fente ou de manchon détachée(s) du guide : 10 mm³ ; coupe 1 : fibula sur le trajet de la lame (côté de la face d'appui)
* `0019_tibia_tib-varus-prox_2+2_défaut_fermeture` : étape 7 : partie(s) de tour de fente ou de manchon détachée(s) du guide : 26 mm³ ; coupe 1 : fibula sur le trajet de la lame (côté de la face d'appui) ; coupe 2 : fibula sur le trajet de la lame (côté de la face d'appui)
* `0037_tibia_tib-pes-varus_2+2_défaut_fermeture` : coupe 1 : fibula sur le trajet de la lame (côté de la face d'appui) ; coupe 2 : fibula sur le trajet de la lame (côté de la face d'appui)
* `0055_tibia_tib-valgus-dist_2+2_défaut_ouverture` : coupe 1 : fibula sur le trajet de la lame (côté de la face d'appui)
* `0127_tibia_tib-varus-recurvatum_2+2_défaut_fermeture` : coupe 1 : fibula sur le trajet de la lame (côté de la face d'appui) ; coupe 2 : fibula sur le trajet de la lame (côté de la face d'appui)
* `0163_tibia_tib-torsion-externe_2+2_défaut_ouverture` : coupe 1 : fibula sur le trajet de la lame (côté de la face d'appui)
* `0181_tibia_tib-grand-varus_2+2_défaut_fermeture` : coupe 1 : fibula sur le trajet de la lame (côté de la face d'appui) ; coupe 2 : fibula sur le trajet de la lame (côté de la face d'appui)

## Erreurs selon les paramètres


## Mesures (min / médiane / max)

| Mesure | min | médiane | max |
|---|---|---|---|
| appui | 566 | 1.21e+03 | 1.97e+03 |
| appui_distal | 210 | 570 | 888 |
| appui_proximal | 272 | 634 | 1.11e+03 |
| base | 1.07 | 3.28 | 6.33 |
| bras | 0 | 0 | 0 |
| broche_cartilage_mm | 3.05 | 20.5 | 72.4 |
| broche_voisin_mm | 1.59 | 4.12 | 99 |
| broches_n | 2 | 4 | 4 |
| cartilage_femur_mm | 1.52 | 3.06 | 7.96 |
| cartilage_patella_mm | 1.27 | 3.89 | inf |
| cartilage_tibia_mm | 3.12 | 43 | 65 |
| complete | 0 | 1 | 1 |
| cote_guide_deg | 125 | 178 | 180 |
| couverture_distal | 50.8 | 129 | 260 |
| couverture_proximal | 64.6 | 136 | 145 |
| decalage | 9e-06 | 0.00104 | 0.0193 |
| derotation | -14.9 | 0 | 25 |
| dlongueur | -2.42 | -0.852 | 2.62 |
| duree_s | 9.1 | 18.5 | 30.1 |
| ecart_theta | -0.00262 | -0.000189 | -5e-06 |
| entree_max_deg | 7.4 | 19.8 | 49.4 |
| guide_fabellae_mm | 1.03 | 2.39 | inf |
| guide_fibula_mm | 1 | 11.2 | inf |
| guide_patella_mm | 1.04 | 3.88 | inf |
| interpenetration | 0 | 0 | 0 |
| jeu | 0.3 | 0.305 | 0.321 |
| paralleles | 0 | 0 | 1e-06 |
| post | 9e-06 | 0.000356 | 0.00491 |
| reduction_fabellae_mm | 1.04 | inf | inf |
| reduction_fibula_mm | 1.04 | inf | inf |
| reduction_patella_mm | 1.37 | inf | inf |
| regle | 1 | 1 | 2 |
| repousses | 0 | 0 | 5 |
| residuel | 0 | 0 | 1e-06 |
| theta | 8 | 14 | 30.8 |
| torsion_ecart | 0 | 0.0691 | 0.308 |

## Exemples de cas en erreur

