# Campagne de simulation de la stratégie (planification) — 11/11/2026 16:23:34

222 cas (120 aléatoire, 102 préréglages), en 3 s : **221 sans erreur** (99.5 %).

Pour chaque cas, les deux coins (fermeture et ouverture) sont planifiés et contrôlés.

| Règle | Contrôle | Erreurs |
|---|---|---|
| R1 | guide jamais du côté de la charnière | 0 |
| R2 | charnière conservée cohérente | 0 |
| R3 | face d'appui à ≤ 60° de la face du coin, sinon abord non usuel signalé | 0 |
| R4 | coin recommandé réalisable | 0 |
| R5 | une broche proximale et une broche distale | 0 |
| R6 | broches parallèles après correction | 0 |
| R7 | angle et translation résiduels nuls | 0 |
| R8 | niveau du trait et profondeur de charnière respectés | 0 |
| R9 | angles après correction = os sain | 1 |

## Le coin recommandé

| Déformité → coin recommandé (critère décisif) | Cas |
|---|---|
| tibia valgus → fermeture (abord) | 27 |
| tibia varus → ouverture (abord) | 25 |
| femur varus → fermeture (stabilite) | 19 |
| tibia varus + procurvatum → ouverture (abord) | 17 |
| tibia varus + recurvatum → ouverture (abord) | 16 |
| femur valgus → fermeture (stabilite) | 14 |
| femur varus + procurvatum → fermeture (stabilite) | 11 |
| femur varus + recurvatum → fermeture (stabilite) | 10 |
| tibia varus + procurvatum → fermeture (stabilite) | 9 |
| tibia valgus + recurvatum → fermeture (abord) | 9 |
| tibia valgus + procurvatum → fermeture (abord) | 9 |
| tibia varus + recurvatum → fermeture (stabilite) | 7 |
| femur varus + procurvatum → fermeture (ouverture) | 7 |
| femur valgus + recurvatum → fermeture (stabilite) | 5 |
| femur valgus + procurvatum → fermeture (stabilite) | 5 |
| femur varus + procurvatum → ouverture (charniere) | 4 |
| femur varus + recurvatum → fermeture (ouverture) | 3 |
| femur valgus + procurvatum → fermeture (ouverture) | 3 |
| femur varus + procurvatum → ouverture (coinFin) | 2 |
| femur valgus + recurvatum → fermeture (ouverture) | 2 |
| femur varus → ouverture (coinFin) | 2 |
| femur valgus → ouverture (coinFin) | 2 |
| tibia varus + recurvatum → ouverture (coinFin) | 1 |
| tibia varus + procurvatum → ouverture (coinFin) | 1 |
| femur varus + procurvatum → ouverture (abord) | 1 |
| femur varus + recurvatum → fermeture (abord) | 1 |
| femur valgus → ouverture (abord) | 1 |
| tibia valgus + procurvatum → ouverture (coinFin) | 1 |
| tibia varus + procurvatum → fermeture (ouverture) | 1 |
| femur varus → fermeture (ouverture) | 1 |
| femur valgus + recurvatum → fermeture (abord) | 1 |
| femur valgus + procurvatum → ouverture (abord) | 1 |
| tibia varus → fermeture (stabilite) | 1 |
| tibia valgus + procurvatum → fermeture (stabilite) | 1 |
| tibia valgus + recurvatum → fermeture (stabilite) | 1 |
| femur varus + procurvatum → ouverture (regle) | 1 |

## Faces d'appui du guide

| Coin | Face d'appui | Cas |
|---|---|---|
| fermeture | latérale | 58 |
| fermeture | médiale | 52 |
| fermeture | crânio-latérale | 37 |
| fermeture | caudo-latérale | 29 |
| fermeture | caudo-médiale | 24 |
| fermeture | crânio-médiale | 21 |
| fermeture | crâniale | 1 |
| ouverture | médiale | 59 |
| ouverture | latérale | 52 |
| ouverture | caudo-médiale | 41 |
| ouverture | crânio-médiale | 31 |
| ouverture | crânio-latérale | 20 |
| ouverture | caudo-latérale | 17 |
| ouverture | crâniale | 2 |

Coin réalisable par un abord usuel : fermeture oui 157, non 65 ; ouverture oui 171, non 51.
Charnière conservée : fermeture non 213, oui 9 ; ouverture non 198, oui 24.

## Avertissements (non bloquants)

| Avertissement | Cas |
|---|---|
| contrainte fermeture : cartilage | 11 |
| contrainte ouverture : cartilage | 10 |
| contrainte fermeture : translation | 3 |
| contrainte ouverture : translation | 3 |
| broches ouverture : placement incomplet | 1 |
| broches fermeture : placement incomplet | 1 |

## Cas en erreur

* `0115_femur_aléatoire_aléatoire` : R9 fermeture : angles après correction à 3.836° de l'os sain
