# Campagne de simulation des guides sur l'os fictif

Dossier écrit par la campagne de validation du 14/10/2026 (CT-CORA3D, étape 7).

* `rapport_campagne.md` : rapport final (planification, erreurs, avertissements, mesures, exemples).
* `rapport_avant_corrections.md` : la même campagne avec le cœur et l'étape 7 d'avant les corrections (480 cas).
* `resultats_campagne.jsonl` : un cas par ligne (paramètres, erreurs, avertissements, mesures).

Les dossiers des cas (os, voisins, prescription, guides) ne sont pas gardés : ils se régénèrent en ≈ 15 s.

```bash
cd code_source
node tests/campagne_export.mjs ../campagne tout 160 23                    # 640 cas (même graine)
../../.venv/bin/python tests/campagne_guides.py ../campagne --processus 4  # ≈ 1 h ; --rapport : rapport seul
```

## Résumé

Chaque cas = une déformité (fémur ou tibia ; varus ou valgus ; sans composante sagittale, procurvatum ou recurvatum ;
F 5 à 30°, S 3 à 25°, apex de 25 à 85 % de la longueur, torsion de −30 à +30°) × un type de coin. Le cœur de calcul
planifie, l'étape 7 construit les deux guides avec les os voisins et le cartilage, puis `tests/campagne_guides.py`
contrôle tout indépendamment, « avec l'œil du chirurgien » : planification (angle vrai, angles après correction,
torsion, broches parallèles), guide (jeu, interpénétration, appui de chaque moitié, retrait, étanchéité, manchons),
os voisins (fibula, rotule, fabelles) contre le guide, les broches et le trait de coupe, cartilage, broches
(bicorticales, entrée sur la corticale), guide de réduction contre les voisins corrigés.

| | Avant les corrections | Après |
|---|---|---|
| Cas simulés | 480 | 640, dont 320 sur des déformités tirées au hasard (graine jamais utilisée pendant le développement) |
| **Cas sans erreur** | **46 (10 %)** | **640 (100 %)** |
| guide, broche ou trait de coupe dans le cartilage | 329 | 0 |
| guide de coupe contre un os voisin | 287 | 0 |
| os voisin ou broche sur le trajet de la lame | 259 | 0 |
| guide de réduction (voisin, construction) | 129 | 0 |
| broche trop près de l'extrémité de l'os | 121 | 0 |
| broche contre un os voisin | 87 | 0 |
| torsion résiduelle < 1° — seuil de la campagne ramené au seuil clinique de 1° | 52 | 0 |
| fentes très proches (coin de fermeture trop fin) — devenu un avertissement, coin d'ouverture conseillé | 46 | 0 |
| STL non étanche | 21 | 0 |
| broche non bicorticale (< 5 mm d'os) | 7 | 0 |

Mesures après corrections (min / médiane / max) : jeu guide–os 0.29 / 0.30 / 0.32 mm ; appui du guide 960 / 1470 / 2534 mm² ; jeu guide–fibula 3.5 / 13.1 / 16.6 mm, –rotule 1.1 / 4.0 / 12.8 mm, –fabelles 1.0 / 1.6 / 25.7 mm ; guide–cartilage 1.5 / 3.9 / 6.7 mm (fémur), 1.5 / 4.3 / 57.7 mm (tibia) ; axe des broches–os voisin 1.9 / 7.6 / 99.0 mm ; entrée des broches 5 / 24 / 67° de la normale ; durée 11 / 22 / 90 s par cas.

Écart résiduel connu : le cœur limite l'entrée des broches à 50° de la normale lissée de la surface ; mesuré sur la
facette exacte du maillage (intersection de l'axe et de la surface), l'angle dépasse 50° dans 24 cas sur 640 (au
plus 56°, tibia ; médiane 24°). Le manchon guide la broche jusqu'à 0,3 mm de l'os, ce qui limite le glissement.

Avertissements (non bloquants, expliqués à l'utilisateur) :

* coupe 1 : la fibula croise le plan de coupe : 304
* planification : broches du fragment distal décalées de 2 mm de la ligne centrale de l'os : 196
* planification : règle 2 de Paley : 178
* coupe 2 : la fibula croise le plan de coupe : 152
* étape 7 : fentes très proches : 114
* planification : broches tournées de -10° autour de l'os : 73
* planification : face du coin latérale : 66
* planification : coin de fermeture trop fin : 64

Rapports complets : `resultats/_campagne_os_fictif/` (`rapport_campagne.md`, `rapport_avant_corrections.md`,
`resultats_campagne.jsonl`). Relancer : commandes de la section « Ligne de commande ».
