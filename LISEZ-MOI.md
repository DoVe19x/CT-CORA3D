# CT-CORA3D — du scanner au guide imprimable, dans une seule application (PMD2, ECAM)

CT-CORA3D réunit les deux applications du projet et les prolonge jusqu'aux pièces à imprimer :

* **Segmentation CT** (reprise de `../CT-scan/`) : DICOM → os segmentés → un STL étanche par os ;
* **CORA 3D** (reprise de `../CORA3D/`) : planification d'ostéotomie par la méthode CORA ;
* **nouveau** : repères automatiques de l'os détecté (étape 6), correction de la torsion par dérotation, et
  **guide imprimable** (étape 7) : guide de coupe moulé sur l'os, « 2 en 1 » (butée de profondeur et verrou de
  réduction intégré ; guide de réduction séparé en option).

```
dossier DICOM du chirurgien ─► segmentation (étapes 1-5) ─► os détecté : le fémur OU le tibia complet
                                                                   │  repères automatiques (étape 6)
     onglet 2 « Planification CORA » : os segmenté (CT)  ◄─────────┘        ou   os fictif (modèle)
          JOL, angles (comparés aux références), CORA, angle vrai θ, ACA, coupe, correction + dérotation, contrôle
                                                                   │
                                     étape 12 : guide de coupe « 2 en 1 » (étape 7) ─► STL à imprimer
```

Les dossiers `CT-scan/` et `CORA3D/` ne sont pas modifiés. Les séries DICOM (≈ 1 Go) restent dans `CT-scan/` et sont
lues de là ; les résultats de CT-CORA3D vont dans `CT-CORA3D/resultats/`.

## Lancer

| Système | Double-cliquer sur |
|---|---|
| macOS (conseillé) | **`~/Applications/CT-CORA3D.app`** : application autonome, Python et toutes les bibliothèques sont dedans |
| macOS (développement) | `CT-CORA3D.app` du dossier du projet : petit lanceur qui utilise l'environnement Python de l'ordinateur |
| Windows (conseillé) | **raccourci « CT-CORA3D »** (menu Démarrer, Bureau) : application autonome, construite une fois par `application\lanceurs\creer_app_windows.bat` |
| Windows (développement) | `Lancer sur Windows.bat` |

L'application s'ouvre dans **sa propre fenêtre** (comme une application de bureau : nom et icône dans le Dock ou la
barre des tâches, menus, boîtes « Enregistrer sous » pour les exports), avec deux onglets : **1 · Segmentation CT** et
**2 · Planification CORA**.

**Application autonome (macOS).** Construite par `application/lanceurs/creer_app_autonome.sh` (PyInstaller, ≈ 800 Mo,
installée dans `~/Applications`, hors OneDrive) : rien à installer, aucun navigateur, aucun environnement Python. Au
lancement, la fenêtre affiche « Démarrage des calculs… » le temps que le serveur de calcul charge ses bibliothèques
(quelques secondes), puis l'interface. Deux processus, un seul exécutable : la fenêtre (Cocoa) et les calculs (VTK)
exigent chacun le fil principal de macOS ; le processus de calcul n'a pas d'icône dans le Dock et s'arrête quand la
fenêtre se ferme (après le calcul en cours). Elle travaille dans le dossier du projet d'où elle a été construite
(mêmes séries DICOM dans `../CT-scan/`, mêmes `resultats/`) ; copiée sur un autre Mac (Apple Silicon), dans
`~/Documents/CT-CORA3D`. Au premier accès à OneDrive ou à Documents, macOS demande l'autorisation : accepter. Après une
modification du programme, relancer `bash application/lanceurs/creer_app_autonome.sh` (≈ 3 min).

**Application autonome (Windows).** Même principe : double-cliquer une fois sur `application\lanceurs\creer_app_windows.bat`
(Python 3.10+ et internet requis pour la construction seulement ; ≈ 10 min la première fois). Elle s'installe pour
l'utilisateur seul, sans droits administrateur, dans `%LOCALAPPDATA%\Programs\CT-CORA3D`, avec un raccourci dans le
menu Démarrer et sur le Bureau ; la fenêtre utilise WebView2 (le moteur d'Edge, présent sur Windows 10 et 11) ; journal
`%LOCALAPPDATA%\CTCORA3D\CTCORA3D.log`. *Recette écrite et relue le 22/10/2026, mais pas encore construite sur un PC
Windows (PyInstaller ne construit que pour le système sur lequel il tourne) : à essayer sur un PC de l'ECAM.*

**Fluidité (22/10/2026).** Mesures sur le Mac de développement, avant → après :

| | Avant | Après |
|---|---|---|
| Guide complet (cas du tibia, fermeture, verrou, plans 2D) | 86,5 s | **23,5 s** |
| dont plans 2D | 49,8 s | 6,2 s |
| Chargement des bibliothèques du serveur au démarrage | 2,1 s | 0,9 s |
| Vérification de l'environnement par les lanceurs | 1,5 à 2,6 s | 0,02 s |
| Vue 3D au repos (images calculées par seconde, par onglet) | 60 | **0** |

Comment : plans 2D dessinés par un tampon de profondeur en numpy au lieu de matplotlib (et plus justes : bords de fente
et contours qui manquaient) ; recherches de plus proches voisins sur tous les cœurs ; distances entre pièces cherchées
de près en loin (même résultat, jusqu'à 50 fois plus vite) ; seulement les modules de VTK utilisés ; vues 3D
redessinées seulement quand quelque chose change. Les résultats des guides sont identiques au bit près (`guide.json`
comparé avant / après). Pendant un calcul, l'application empêche la mise en veille par inactivité (macOS et Windows) :
un calcul ne reste plus figé si l'on s'éloigne de l'ordinateur.

**Lanceur de développement** (`CT-CORA3D.app` du projet, `Lancer sur Windows.bat`) :

* À chaque lancement, il vérifie seulement que les bibliothèques sont présentes, sans les charger (0,02 s) : le serveur
  les charge juste après. Sous Windows, il active le mode UTF-8 de Python (accents dans les chemins et les fichiers).

* La fenêtre utilise le moteur web du système (WebKit sur macOS, WebView2 sur Windows) via la bibliothèque `pywebview`,
  installée au premier lancement pour l'ordinateur (une minute, internet requis), hors OneDrive :
  `~/Library/Application Support/CTCORA3D/fenetre-py3XX` (macOS), `%LOCALAPPDATA%\CTCORA3D\fenetre-py3XX` (Windows).
  `PMD2/.venv` n'est pas modifié. Si elle ne peut pas être installée, l'application s'ouvre dans Chrome / Edge, comme avant.
* Les aperçus et rapports de l'onglet 1 (PNG, `.md`, `.json`) s'ouvrent dans une petite fenêtre de l'application ; les
  références bibliographiques (DOI) dans le navigateur habituel.
* Pour garder l'application dans le Dock : y glisser `CT-CORA3D.app` (pas l'icône qui apparaît pendant l'utilisation).

* Python est nécessaire. Le lanceur utilise d'abord l'environnement propre à l'ordinateur, hors OneDrive
  (`~/Library/Application Support/CTCORA3D/venv`, `%LOCALAPPDATA%\CTCORA3D\venv`), sinon `PMD2/.venv` : quand OneDrive
  met les fichiers de `PMD2/.venv` « en ligne uniquement », les relire prend plusieurs minutes à chaque lancement. Sur un
  ordinateur qui n'a ni l'un ni l'autre, le premier lancement installe les bibliothèques (Python 3.10 ou plus récent et
  internet requis, une seule fois, quelques minutes). Un environnement
  installé par une version précédente est complété automatiquement (bibliothèque `manifold3d`, pour les guides).
* Premier lancement sur macOS : si « impossible de vérifier le développeur » s'affiche, clic droit sur l'application →
  *Ouvrir* → *Ouvrir*. Sous Windows, si SmartScreen s'affiche : *Informations complémentaires* → *Exécuter quand même*.
* En haut à droite : thème clair / sombre (◐) et quitter (⏻). Fermer la fenêtre (ou Cmd+Q) suffit aussi : le serveur
  local s'arrête aussitôt, ou à la fin du calcul en cours.

## Onglet 1 — Segmentation CT

Comme l'application CT-scan (son `LISEZ-MOI.md` détaille la méthode) : choisir une série, « Segmenter la série »
(≈ 30 à 60 s), vérifier les os en coupes et en 3D, corriger si besoin (« Renommer », « Séparer… »).

Le chirurgien arrive avec **un dossier DICOM = un fémur ou un tibia**. La 6e étape de la segmentation détecte l'os
complet de la série et le présente dans la carte **« Os à planifier (CORA) »**, avec la raison du choix ; le bouton
**« Planifier CORA → »** l'ouvre dans l'onglet 2. Les os coupés par le champ du scanner portent « CORA ✗ » (survolez
pour la raison) : il faut les deux articulations pour la méthode CORA. Si un scanner contient deux fémurs (ou deux
tibias) complets, le plus éloigné des normes est choisi et l'autre sert de membre controlatéral.

## Onglet 2 — Planification CORA

En haut, deux sources : **Os segmenté (CT)** et **Os fictif (modèle)**. Les 13 étapes sont les mêmes pour les deux.

### Os segmenté (CT)

1. **Os détecté** : l'onglet prend automatiquement l'os de la série ouverte dans l'onglet 1 (il suit la série quand on
   revient sur l'onglet). Aucune liste d'os à choisir.
2. **Étape 1** : l'os, ses repères automatiques (étiquetés), son côté, le **dépistage** des angles articulaires
   (± 2 écarts-types) et le tableau **« Les angles normaux : travaux de Vezzoni et autres études »** (voir plus bas).
   Un membre gauche est analysé en miroir, comme un droit.
3. **Tel quel** : sur les os du lévrier du dossier, tous les angles sont dans les normes ; l'application l'indique
   (« pas de correction indiquée ») et explique pourquoi il n'y a pas d'ostéotomie au CORA quand les axes sont presque
   parallèles.
4. **Déformité de test** (case à cocher) : on impose à l'os réel une déformité connue — varus / valgus, procurvatum /
   recurvatum, amplitudes, niveau de l'apex et **torsion τ** du segment distal (« Régler la déformité de test »).
5. **Référence** : **Valeurs normales**, uniquement publiées (au choix : « Vezzoni » par défaut, « Littérature »,
   « Race » dont le lévrier) ou **Os avant déformité** (avec une déformité de test : l'os réel non déformé joue le rôle
   du membre controlatéral ; la méthode retrouve alors exactement la déformité imposée).
6. **Étapes 10 et 11** : correction animée et contrôle, **dérotation comprise** si la torsion sort de la normale.
7. **Étape 12** : prescription, puis **« Construire les guides 3D »** (≈ 10 à 30 s) : guide de coupe affiché sur l'os
   avant la coupe, puis ses moitiés verrouillées sur l'os corrigé ; contrôles, mode opératoire, téléchargement des STL. « Exporter la prescription (ZIP) »
   reste disponible : il contient aussi les os voisins et la carte du cartilage, et la commande qui reconstruit les mêmes
   guides hors de l'application.
8. **Étape 13** : torsion de l'os mesurée avec les définitions publiées, et le laboratoire τ / ρ (radiographie contre
   scanner).

### Os fictif (modèle)

Exactement l'application CORA 3D (fémur ou tibia, varus ou valgus, avec ou sans procurvatum / recurvatum, réglages F,
S et niveau), plus la torsion τ du segment distal et la construction des guides à l'étape 12.

## Les angles normaux : travaux de Vezzoni et autres études

Un angle normal est l'orientation habituelle d'une ligne articulaire par rapport à l'axe de son segment. Il sert à
construire l'axe d'un segment déformé (méthode de Paley) et à dépister une déformité : un angle est jugé **anormal à
plus de 2 écarts-types** de la référence. Les références viennent **uniquement de publications** :

| Angle | Travaux de l'équipe Vezzoni | Autres études | Lévrier du dossier* |
|---|---|---|---|
| aLDFA (fémur, face) | 94 ± 3,3° ; en dessous = valgus distal (Vezzoni L 2022 ; valeur du berger allemand de Tomlinson 2007) | 97 ± 3,2° Labrador ; 94 à 98° selon la race (Tomlinson 2007) | 96,6° : normal |
| mMPTA (tibia, face) | 93,3 ± 1,78° ; au-dessus = valgus proximal (Olsen, Vezzoni 2016) ; valgus opéré 101° → 92,8° (Vezzoni L 2020) | 93,3 ± 1,8° (Dismukes 2007) ; 92,2 ± 1,8° (Dismukes 2008b) | 89,9° : normal |
| Pente du plateau tibial (TPA) | 26,3° (20,4–30,8°) chez 40 Labradors sains ; ≈ 30–31° en cas de rupture du ligament croisé (Guénégo, Vezzoni 2021 et 2025) | 22,5° chez le lévrier, « à considérer comme normal » ; 28,0° Labrador (Wilke 2002) | 21,8° : normal |
| Angle AMA (tibia, profil) | 0,99° (0–3,39°) chez les Labradors sains (Guénégo, Vezzoni 2021) | > 1,87° associé à la rupture du ligament croisé (Guénégo 2017) | non mesuré |
| mMDTA (tibia, face) | pes varus : 62° avant, 82° après correction (Petazzoni, Vezzoni 2012) — valeurs pathologiques | 96,0 ± 2,7° (Dismukes 2007) ; 95,9 ± 2,2° (Dismukes 2008b) | 96,3° : normal |

\* valeurs de l'os segmenté ramenées à la définition radiographique des articles (voir le piège 2D/3D ci-dessous).

* **Préréglages** (panneau de gauche, *Valeurs normales*) : **Vezzoni** (par défaut : bornes des travaux de l'équipe
  Vezzoni, et littérature pour les autres angles), **Littérature** (Tomlinson 2007 Labrador, Dismukes 2007-2008…),
  **Race** (fémur : Tomlinson 2007, quatre races ; pente tibiale : Wilke 2002, lévrier et Labrador). Les valeurs ne se
  modifient pas à la main ; survoler une ligne affiche sa source.
* **La race compte** : la borne Vezzoni de l'aLDFA est la valeur du berger allemand, la plus basse des races de
  Tomlinson. Sur le lévrier, l'aLDFA reste normal, mais la planification avec la référence « valeurs normales » voit un
  écart naturel un peu plus grand (θ retrouvé à 4,4° près au lieu de 1,1° avec la valeur du Labrador). Le meilleur
  témoin reste le membre opposé sain du même chien.
* **Piège 2D/3D** : les articles mesurent sur radiographie, l'application en 3D avec des repères automatiques. L'écart
  de définition, mesuré une fois sur l'os sain du modèle (par exemple +9,5° pour mCaPTA), est ajouté aux valeurs
  publiées. Contrôle : les os sains du lévrier tombent dans toutes les bornes (5 angles sur 5 pour le tibia, 4 sur 4
  pour le fémur, et la pente tibiale).

## Torsion : vérification et correction

* **Définitions publiées** (scanner) : fémur, antéversion entre l'axe du col (centre de la tête → base du col au niveau
  du petit trochanter) et la ligne condylaire caudale (Al Aiyan 2021 : 31 ± 5° ; Longo 2022 : < 20° torsion externe,
  > 35° interne) ; tibia, axe antécochléaire contre ligne condylaire caudale (Brühschwein 2023) ; − interne, + externe ;
  normale ≈ −4°, anormale < −10° ou > +2°.
* **Vérification sur le lévrier** : fémur 24,6° et tibia −7,9°, tous deux normaux. Les anciennes définitions de CORA 3D
  donnaient 15,6° (fémur, axe du col au ras de la tête) et +6,0° (tibia, axe bimalléolaire) : deux fausses « torsions
  externes ». La définition compte autant que la mesure ; l'antéversion reste indicative (centre de la tête et base du
  col estimés automatiquement).
* **Correction** : si la torsion sort de la normale (référence « valeurs normales ») ou diffère de l'os avant déformité,
  la correction ajoute une **dérotation** du fragment distal autour de son axe, réglée pour retrouver la torsion cible ;
  une dérotation impose une ostéotomie complète (la charnière corticale ne peut pas tourner).

## Stratégie chirurgicale (étapes 9 et 12)

La planification ne se contente pas de la géométrie : elle choisit la stratégie comme le ferait un chirurgien, et
l'explique dans la boîte « Stratégie chirurgicale ». Le panneau de gauche « 2 · Stratégie et guide » permet de tout
changer : préréglage clinique, type de coin, niveau du trait, profondeur de la charnière, broches, dimensions du guide.

* **Où se pose le guide de coupe.** La lame entre toujours du côté **opposé à la charnière** : par la face convexe pour
  un coin de fermeture (le coin est retiré du côté convexe), par la face concave pour un coin d'ouverture (l'os s'ouvre
  du côté concave). Le guide se pose sur cette face d'entrée. Si elle est hors des abords usuels, ou si un os voisin est
  sur le trajet de la lame, le guide passe par la face accessible la plus proche, à moins de 60° de la face du coin
  (l'ostéotomie devient complète) ; au-delà, la lame entrerait du côté de la charnière : ce type de coin est déclaré
  **non réalisable par un abord usuel** et l'autre est recommandé. Si, en plus, un os voisin (la fibula, en général :
  coin de fermeture d'un varus du tibia, ou d'ouverture d'un valgus) est sur le trajet de la lame par la face du coin,
  **aucun guide de coupe n'est construit** : il occuperait l'espace entre l'os et ce voisin, où l'on ne peut ni le
  glisser, ni le fixer, ni couper. L'application l'explique à l'étape 12 et renvoie au coin conseillé. (Jusqu'au
  22/10/2026, un guide était construit quand même sur cette face : il passait tous les contrôles géométriques, mais
  était physiquement impossible à poser.)
* **Abord chirurgical.** Fémur : abord latéral (± 60°), ou médial pour une ostéotomie distale (± 45°) ; jamais crânial
  (quadriceps, rotule, trochlée) ni caudal (nerf sciatique, vaisseaux). Tibia : face médiale (± 60°), latérale plus
  étroite (± 30°, muscles crâniaux et fibula). Les structures à protéger de l'abord retenu sont listées.
* **Ouverture ou fermeture ?** Critère par critère ; le premier qui départage décide, les autres restent affichés :
  1. accès : la lame entre par un abord usuel, du côté opposé à la charnière ;
  2. charnière corticale conservée (stabilité, pas de translation) ;
  3. règle 1 (coupe au CORA) plutôt que règle 2 (translation à l'ostéotomie) ;
  4. coin de fermeture assez épais pour deux fentes de scie (≥ 1,5 mm de matière entre elles) ;
  5. ouverture raisonnable (≤ 40 % de la largeur de l'os) : au-delà, greffe et consolidation plus longue ;
  6. longueur : le coin qui compense le mieux une différence avec le membre opposé (la fermeture raccourcit,
     l'ouverture allonge) ;
  7. à défaut : fermeture (surfaces osseuses en contact, stabilité primaire, pas de greffe).

  Sur la campagne de 606 cas : tibia valgus → fermeture et tibia varus → ouverture (critère décisif : l'accès, la face
  médiale du tibia) ; fémur varus ou valgus → fermeture (stabilité). Le choix « Auto » suit la recommandation (★) ;
  « Fermeture » ou « Ouverture » l'impose.
* **Règle 1 de Paley par défaut, niveau du trait réglable (z).** La coupe passe au CORA. Si un trait passerait à moins
  de 5 mm du cartilage articulaire (ou si le coin emporterait du cartilage), la coupe se déplace vers la diaphyse
  (règle 2). Le curseur « Niveau du trait de coupe (z) » translate aussi le plan de coupe le long de l'os, à la demande.
  Hors du CORA, la correction tourne toujours autour de l'ACA placé sur la bissectrice du CORA, ce qui réaligne
  exactement les axes, et le fragment distal glisse le long de la coupe : c'est la translation de la règle 2, chiffrée,
  avec une alerte au-delà de 50 % de la largeur de l'os.
* **Charnière (y).** Par défaut sur la bissectrice transverse, au niveau du CORA, **à 2 mm à l'intérieur de la
  corticale opposée au coin** (concave en fermeture, convexe en ouverture). C'est le meilleur endroit : la charnière y
  est l'ACA de Paley (aucune translation) et il reste un pont d'os cortical (≤ 3 mm) qui plie sans casser et garde les
  fragments en contact. Le curseur « Profondeur de la charnière (y) » l'enfonce dans l'os : au-delà de 3 mm, le pont ne
  plie plus, l'ostéotomie est complète et le coin devient mixte (une part se ferme, l'autre s'ouvre ; la longueur change
  moins). Un coin d'ouverture ne garde sa charnière que jusqu'à 3 mm.
* **Contraintes chirurgicales (biologiques) au niveau du trait**, affichées par gravité (bloquant, attention, info) :
  cartilage et capsule articulaire (≥ 5 mm du trait) ; tubérosité tibiale, insertion du ligament patellaire (≥ 8 mm) ;
  épicondyles fémoraux, origine des ligaments collatéraux (≥ 6 mm) ; physes d'un chien en croissance (case « Chien en
  croissance ») ; place pour la plaque (≥ 3 vis) et les broches sur chaque fragment (≥ 25 mm) ; consolidation
  (métaphyse rapide ; diaphyse et tiers distal du tibia plus lents) ; translation de la règle 2 ; structures de l'abord
  (vaisseaux et nerf saphènes, nerf sciatique, nerf fibulaire…).
* **Broches.** Configuration au choix : **2 + 2** (défaut : rotation bloquée sur chaque fragment), **1 + 1** (une par
  fragment) ou **1 + 2** (une proximale, deux distales côte à côte au même niveau, horizontalement). Placement
  automatique : à ≥ 3 mm du cartilage (manchon compris), à ≥ 2 mm des os voisins (fibula, rotule, fabelles) jusqu'à
  8 mm au-delà de la corticale opposée (une broche forée un peu trop loin n'embroche pas la fibula), manchons hors des
  tours de fente, pointe hors du trajet de la lame de l'autre trait, entrée sur la corticale à moins de 50° de la
  normale, bicorticales. Si nécessaire : paire tournée autour de l'os (jusqu'à ± 45°), décalée de 2 à 4 mm, broches
  côte à côte sur un fragment court, manchons raccourcis. L'orientation garantit aussi qu'une moitié du guide de coupe
  peut sortir sans heurter l'autre (au besoin, broches inclinées de 10 à 20° le long de l'os).
* **Dérotation.** Si la torsion sort de la normale (ou diffère de l'os avant déformité), le fragment distal tourne en
  plus autour de son axe, d'un angle cherché par la méthode de la sécante pour que la torsion mesurée après correction
  soit la torsion cible. Elle impose une ostéotomie complète (la charnière corticale ne peut pas tourner). Les broches
  distales sont forées avec l'inverse de la correction complète, dérotation comprise : quand elles redeviennent
  parallèles aux proximales, l'angle ET la torsion sont corrigés.
* **Fibula.** Si elle croise le plan de coupe tibial, le mode opératoire prévoit son ostéotomie (intacte, elle
  empêcherait la correction). La rotule et les fabelles sont affichées et suivent le fragment distal.
* **Préréglages cliniques** : 17 déformités prêtes à l'emploi, chacune avec son contexte et sa référence : tibia
  (valgus proximal, varus proximal, pes varus du teckel, valgus distal, recurvatum, procurvatum, plans obliques, torsion
  externe, grande déformité), fémur (varus distal de la luxation médiale de rotule, valgus distal, varus + torsion,
  procurvatum, recurvatum, plan oblique).

## Et l'ostéotomie en dôme ?

**Quand l'utilise-t-on ?** Quand on ne peut pas couper au CORA (CORA tout près de l'articulation, ou dans une zone
interdite) et qu'on veut éviter la translation de la règle 2 : la coupe est un cylindre centré sur le CORA, les
fragments tournent l'un sur l'autre le long de cette coupe, sans translation et en gardant le contact osseux. Elle est
décrite au radius du chien, pour les déformités à un ou deux apex (Fox 2006).

**Pourquoi elle n'est pas proposée** : (1) il faut une lame courbe de rayon fixe et un guide qui fasse tourner la lame
autour d'un pivot, plus délicat à imprimer et à contrôler qu'une fente plane ; (2) un dôme cylindrique ne tourne
qu'autour de son axe : il corrige l'angulation, pas la torsion (une dérotation impose une coupe plane complète) ; (3) au
fémur distal et au tibia, le CORA est le plus souvent dans une zone où la règle 1 est possible.

**Hypothèse retenue** : coupes planes guidées par des fentes, règle 1 par défaut ; si le niveau doit changer, règle 2
avec translation chiffrée (et le rayon qu'aurait un dôme centré sur le CORA, pour comparaison).

## Les guides imprimables (étape 7)

**Guide de coupe** — coque moulée sur l'os (jeu 0,3 mm, épaisseur 3 mm, sans contre-dépouille), une fente de scie
(coin d'ouverture) ou deux (coin de fermeture) dans les plans prescrits, 4 manchons de broches (2 par fragment). Les
broches distales sont forées avec l'inverse de la correction, donc non parallèles aux proximales : le guide est fait de
**deux moitiés reliées par des ponts sécables** (et, en fermeture, d'une **pièce du coin** entre les deux fentes : 3
pièces, 4 ponts). Après la coupe, on coupe les ponts, on retire la pièce du coin, et chaque moitié glisse le long de
ses deux broches. Le guide se pose par la face d'appui (l'abord) ; chaque pièce sort sans contre-dépouille.

**Butée de profondeur** — chaque fente est parallèle à la charnière, et le haut de chaque tour est à la **même
distance D** de la butée de sa fente : la charnière, ou 1 mm au-delà de la corticale opposée pour une coupe complète.
D est la plus petite valeur qui garde 10 mm de guidage, arrondie aux 5 mm supérieurs (une graduation de la lame) ; elle
est **gravée sur les tours** (« P 30 », « D 30 ») : un seul repère sur la lame pour toutes les fentes, au lieu d'une
profondeur différente par fente à mesurer. Si l'on entre la longueur utile de la lame (paramètre pl), la scie bute
d'elle-même sur le haut des tours.

**Finitions** — arêtes des tours arrondies, entrées chanfreinées (fentes, manchons, trous de verrouillage : la lame
et les broches entrent sans accrocher), marquages gravés P / D.

**Guide générique, dimensions modifiables.** Le guide est un modèle paramétrique, comme une pièce de CAO pilotée par
une table : 27 dimensions de conception se règlent dans le panneau « Guide générique : dimensions » (coque : jeu
os-guide, épaisseur, secteur couvert, marge au-delà des broches, dépouille, congés, épaisseur minimale imprimable ; fentes
et manchons : hauteur de guidage, paroi, lame, jeu de fente, diamètre de broche, jeu du manchon, hauteur des ponts,
chanfreins ; butée : profondeur de lame, dépassement ; broches : écart, distance à la coupe ; voisins et cartilage ;
verrou : activé ou non, écart et épaisseur des oreilles ; guide de réduction séparé : distance, manchons, barre).
Valeurs par défaut dans `parametres.py`, bornes de sécurité, valeurs changées signalées. Toutes les autres dimensions
**découlent de l'os** de chaque scanner : longueur des fentes (largeur de l'os dans le plan de coupe + 1 mm + paroi de
chaque côté), hauteur des tours, étendue de la coque, position des broches (1,2 × largeur locale de l'os), position des
oreilles du verrou… Un nouveau DICOM segmenté donne donc un nouveau guide, construit avec les mêmes règles.

**Plans 2D** (dans le dossier du guide, en SVG, PDF et PNG) : `plan_generique` : le guide en schéma, ses cotes en
symboles (j, e, g, p, s, Øb, pl…) et le tableau des paramètres (défaut et valeur du cas) avec les formules des
dimensions qui découlent de l'os ; `plan_guide` : le guide construit pour cet os en projections orthogonales (A : face
d'appui, B : profil, C : vue axiale, D : après la correction, moitiés verrouillées le long des broches), cotes
principales, tableau des dimensions, cartouche, échelle 2:1, 1:1 ou 1:2 sur A3 et cote de contrôle de 50 mm pour
vérifier l'échelle à l'impression.

**Os voisins et cartilage** — le guide reste à ≥ 1 mm de la fibula, de la rotule et des fabelles (tissus mous), et ne
passe sous aucun d'eux pendant la pose ou le retrait. Surtout, il n'occupe jamais **l'espace entre l'os et un os
voisin** (entre le tibia et la fibula : membrane interosseuse, muscles) : tranche par tranche le long de l'os, la zone
que l'enveloppe convexe de l'os et du voisin ajoute à celle de l'os seul est interdite à toute matière du guide
(coque, tours, manchons, bras, oreilles du verrou). L'espace du milieu reste libre pour poser et fixer le guide et
pour couper ; les creux de l'os lui-même restent couverts par la coque. La coque ne repose jamais sur le cartilage articulaire (elle s'en
écarte de plus de 4 mm ; tout le guide, tours et manchons compris, reste à ≥ 1,5 mm de ses sommets). Quand le cartilage
ou un os voisin coupe la coque (fragment distal du fémur couvert par la trochlée, par exemple), des **bras** relient les
manchons isolés, ou la 2e tour d'un coin de fermeture, au reste du guide, par-dessus l'os et hors du trajet de la lame.
De même, si la pièce du coin sortirait en deux morceaux (le cartilage ou un os voisin entaille la paroi d'une tour),
deux bras relient les parois des deux tours par-dessus le coin, en deçà du bout des tours (au-delà se trouvent les
oreilles du verrou).

**Verrou de réduction (« 2 en 1 »)** — les deux moitiés du guide de coupe servent aussi de guide de réduction. Chacune
porte une **oreille** de chaque côté du trait, au-delà du bout des tours. Après la correction (angle + dérotation), les
broches sont parallèles : on remet les moitiés sur leurs broches, et leurs oreilles se superposent ; leurs trous ne
sont alignés que si les fragments sont à la position planifiée. Une **broche de verrouillage** (Ø des broches) passe
alors dans les deux oreilles de chaque côté ; une erreur de 1° ou de 0,3 mm la bloque (contrôlé à chaque construction,
axe par axe). Les moitiés, leurs broches et les broches de verrouillage forment ensuite un fixateur provisoire.
Quelques points de conception :
* **trait de scie compensé** : en fermeture, chaque trait enlève l'épaisseur de la lame ; en fermant jusqu'au contact
  des surfaces coupées, le fragment distal avance de 0,6 mm de plus que prévu, et le verrou en tient compte ;
* **oreilles adaptées côté par côté** : avant la correction, l'oreille distale (ramenée avec son fragment) ne doit
  toucher ni l'oreille proximale ni l'autre moitié, et aucune moitié, en glissant sur ses broches, ne doit balayer
  l'oreille de l'autre. Quand une dérotation fait monter l'oreille distale, l'écart entre les oreilles grandit ; quand
  les broches sont très inclinées sur les tours (jusqu'à 35° au fémur), le verrou s'écarte vers l'extérieur (≤ 10 mm) ;
* **remise en place après la correction** : chaque moitié évite aussi les os voisins dans leur position après la
  correction (la rotule suit le fragment distal, la fibula est coupée) et le fragment osseux de l'autre moitié près du
  trait (une dérotation fait tourner les sections l'une sur l'autre) ;
* si un côté reste impossible (os voisin, cartilage, broche — au fémur distal, la rotule bloque souvent le côté
  crânial), il est abandonné et l'autre côté reçoit des oreilles allongées à **deux broches de verrouillage** (à 6 mm
  l'une de l'autre : le pivotement autour du verrou reste bloqué, à 2° près au lieu de 0,3°, et l'appui des surfaces
  osseuses le limite) ; sans aucun côté
  possible, ou avec le paramètre V = 0, le programme construit à la place le **guide de réduction séparé** : barre
  (enveloppe convexe des broches) et manchons parallèles terminés par des butées moulées sur l'os corrigé ;
* **sensibilité exigée** : le verrou n'est gardé que s'il détecte une rotation de 1° autour de chacun de ses trois axes
  (axe de l'os, axe des fentes, axe des broches, passant par le centre de l'os) ; le calcul exige même 0,9° (marge de
  10 %), pour qu'à 1° la broche soit franchement bloquée. Pour une rotation autour de l'axe de
  l'os ou des fentes, le bras de levier est la **hauteur du trou du bas au-dessus du centre de l'os, mesurée le long
  des broches** : avec 0,1 mm de jeu entre la broche et son trou, il faut au moins 5,7 mm. Quand les broches sont très
  inclinées sur les tours (44° dans un cas du tibia) ou qu'une grosse dérotation fait descendre l'oreille du bas au
  niveau de l'os, le verrou ne verrait pas une erreur de 1,5 à 3,7° : il est alors refusé et remplacé par le guide de
  réduction séparé, dont les broches très écartées tiennent la correction à ≈ 0,1° près ;
* chaque oreille doit appartenir à la pièce de sa moitié : si un os voisin isole le bout d'une tour, ses oreilles
  partiraient avec lui à l'impression, et ce côté est refusé.

**Mode opératoire** (donné aussi dans l'application et dans `guide.json`) : abord ; poser le guide de coupe (une seule
position possible) ; forer les 2 broches proximales puis les 2 distales ; couper par chaque fente jusqu'à ce que la
graduation D de la lame affleure le haut de la tour (charnière, ou corticale opposée) ; couper les ponts ; retirer la
pièce du coin (fermeture), puis la moitié indiquée en premier et l'autre ; retirer le coin osseux (fermeture) ;
ostéotomiser la fibula si nécessaire ; corriger (et, en règle 2, laisser glisser le fragment de la translation
indiquée) jusqu'à ce que les broches soient parallèles ; remettre les moitiés (la moitié du bas d'abord) et enfoncer les
broches de verrouillage ; fixer ; retirer broches de verrouillage, moitiés et broches.

**Contrôles** (dans l'application et `guide.json`) : jeu minimal mesuré (les rares sommets trop proches sont repoussés au
jeu), interpénétration, surface d'appui du guide et de chaque moitié, nombre de pièces après la coupe des ponts, aucune
pièce détachée, chaque manchon présent, retrait de chaque pièce sans heurter l'os (lancer de rayons) ni l'autre moitié
(balayage exact), broches hors du trajet de la lame, guide et broches contre les os voisins et le cartilage, butée
(même D pour toutes les fentes), verrou dans la position corrigée (broche qui passe ; sensibilité à 1° et 0,3 mm, la
broche de verrouillage étant enfoncée jusqu'au fond de son trou : seul un écart latéral entre les deux trous la bloque ;
plus petite rotation détectée autour de chaque axe ; remise en place ; moitiés contre l'os et les voisins corrigés),
étanchéité du STL (pincements de surface décollés de 2 µm si besoin).

**Validation** (`code_source/tests/test_guide.py`) : sur un os coudé synthétique (fermeture, puis ouverture avec 12° de
dérotation), fentes vides exactement dans les plans prescrits et chanfreinées, trous coaxiaux aux broches, haut des tours
à D de la butée (lancer de rayon sur le STL), jeu ≥ 0,29 mm, aucune interpénétration, pièces retirables ; verrou contrôlé
sur les fichiers seuls (la broche passe, un décalage de 0,3 mm la bloque) ; avec un os voisin qui empiète sur la coque
et une bande de cartilage, jeu de 1,03 mm au voisin et coque hors du cartilage ; sur le fémur et le tibia réels du
lévrier, guides sans alerte, verrou des deux côtés. Campagne de simulation sur l'os fictif : voir ci-dessous.

### Campagne de simulation (os fictif)

**Guides v3, 22/10/2026** (`tests/campagne_export.mjs` + `tests/campagne_guides.py`, code définitif) : 320 cas
« coins » (chaque paramètre à ses extrêmes : fémur et tibia, varus et valgus, sans composante sagittale, procurvatum ou
recurvatum, F, S, niveau de l'apex, torsion 0 ou 20°, fermeture et ouverture) et 200 cas tirés au hasard (100
déformités, torsion de −30 à +30°, × 2 types de coin) : **520 sur 520 sans erreur**.

| | Coins (320) | Hasard (200) |
|---|---|---|
| Verrou « 2 en 1 » des deux côtés | 226 | 148 |
| Verrou d'un seul côté, à deux broches | 26 | 10 |
| Guide de réduction séparé (aucun côté possible / verrou trop peu sensible) | 11 / 3 | 2 / 3 |
| Pas de guide de coupe : coin forcé, fibula sur le trajet de la lame (conséquence attendue) | 54 | 37 |
| Plus petite rotation détectée par le verrou (min / médiane / max) | 0,21 / 0,34 / 0,87° | 0,21 / 0,30 / 0,79° |
| Jeu guide–os mesuré | 0,296 à 0,327 mm | 0,297 à 0,324 mm |
| Durée par guide (min / médiane / max) | 11 / 18 / 31 s | 11 / 18 / 27 s |

Les coins « forcés » sont ceux que la planification déclare non réalisables par un abord usuel (elle conseille
l'autre type de coin) : la campagne les construit quand même pour éprouver le programme. Quand la fibula est sur la face
du coin, le programme refuse désormais le guide, ce qui est le comportement voulu.

**Stratégie, 19/10/2026** (`tests/campagne_strategie.mjs`) : 606 cas, soit les 17 préréglages avec leurs variantes
(broches 2 + 2, 1 + 1 et 1 + 2 ; trait déplacé de ± 15 mm ; charnière à 0,5 et 6 mm ; chien en croissance) et 300
déformités tirées au hasard. Pour chaque cas, les deux coins sont planifiés et contrôlés par 9 règles :

| Règle | Contrôle | Erreurs |
|---|---|---|
| R1 | guide jamais du côté de la charnière | 0 |
| R2 | charnière conservée cohérente (guide sur la face du coin, règle 1, sans dérotation, pont ≤ 3 mm) | 0 |
| R3 | face d'appui à ≤ 60° de la face du coin, sinon abord non usuel signalé | 0 |
| R4 | coin recommandé réalisable dès qu'un des deux l'est | 0 |
| R5 | nombre et disposition des broches (1 + 2 : distales côte à côte au même niveau) | 0 |
| R6 | broches parallèles après correction | 0 |
| R7 | angle et translation résiduels nuls | 0 |
| R8 | niveau du trait et profondeur de charnière demandés respectés | 0 |
| R9 | angles après correction = os sain | 0 |

**606 cas sur 606 sans erreur.**

**Guides, 19/10/2026** (`tests/campagne_guides.py`) : 102 de ces cas (les préréglages, les trois configurations de
broches, trait déplacé de 15 mm, charnière à 6 mm), guides construits puis contrôlés : **102 sur 102 sans erreur** ;
chaque guide est du côté opposé à la charnière (125 à 180° ; 180° = exactement à l'opposé, 90° = limite). 7 de ces cas
sont des coins forcés alors que la planification les déclare non réalisables par un abord usuel (abord latéral du
tibia, fibula sur le trajet de la lame) : cette conséquence attendue est rangée à part dans le rapport.

Rapports : `resultats/_campagne_strategie/`.

**Première campagne (guides, 640 cas).** Chaque cas = une déformité (fémur ou tibia ; varus ou valgus ; sans composante sagittale, procurvatum ou recurvatum ;
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

## À quoi servent les broches ?

1. **Fixer le guide de coupe** pendant la coupe : forées à travers les manchons, elles l'immobilisent sur l'os ; la lame
   reste dans le plan prescrit.
2. **Porter la correction** : les broches distales sont forées avec l'inverse de la correction planifiée (angle et
   dérotation) ; en corrigeant, elles redeviennent parallèles aux proximales exactement à la position planifiée.
3. **Tenir la réduction** : les moitiés du guide de coupe, remises sur les broches parallèles, se verrouillent l'une à
   l'autre (ou le guide de réduction séparé s'enfile sur toutes les broches) et maintiennent les fragments pendant la
   pose de la plaque.
4. **Bloquer la rotation** : deux broches par fragment empêchent le fragment de tourner autour d'une broche (torsion).

Configurations (panneau « Coin, niveau de coupe, charnière, broches ») : **2 + 2** (défaut : rotation bloquée sur
chaque fragment) ; **1 + 1** (deux trous de moins, mais chaque fragment peut encore tourner autour de sa broche :
vérifier que les moitiés, ou les butées du guide de réduction, touchent l'os) ; **1 + 2** (une proximale, deux distales côte à côte au
même niveau, horizontalement : utile pour un fragment distal court).

## Faut-il des broches pour contrôler la torsion ?

**Non, pas obligatoirement — mais il faut bloquer la rotation, et deux broches seules le font mal** : avec une broche par
fragment, on juge le parallélisme à l'œil (quelques degrés) et une rotation autour de la broche elle-même passe
inaperçue ; avec un guide de coupe seul, la rotation est l'erreur qui reste (Worth 2019 : 1 membre sur 7 réopéré).

Ce que fait CT-CORA3D : **2 broches par fragment + verrou de réduction intégré au guide de coupe** (ou guide de
réduction séparé) ; la torsion est contrôlée sans être mesurée (1° d'erreur bloque la broche de verrouillage).
Publications avec des guides de réduction : torsion à 1,7 ± 2,1° de la cible (Hall 2019, fémur), 2,6 ± 1,3° dans le
plan transverse (Jeon 2023, tibia), < 2° et < 1 mm (Bright 2024), > 90 % des paramètres à ≤ 5° (De Armond 2022).

Sans broches : **plaque sur mesure** (imprimée en titane, Carwardine 2021) dont les trous de vis sont percés à travers le
guide de coupe avant l'ostéotomie ; repères de rotation tracés de part et d'autre du trait ; contrôle peropératoire
(fluoroscopie, scanner) ou navigation. La plaque sur mesure serait la suite logique du projet.

## Ce que fait l'étape 6 (repères automatiques)

Pour chaque fémur et tibia segmentés, en ≈ 1,3 s : repère de l'os (X latéral, Y proximal, Z caudal) et côté reconnus
par l'anatomie ; os coupé par le champ du scanner refusé ; repères de CORA 3D (tête fémorale, grand et petit trochanter,
col, condyles, épicondyles, trochlée ; éminence, plateaux et leur pente, condyles caudaux, tubérosité, cochlée et axe
antécochléaire, centre distal, malléoles, tête de la fibula) ; angles, torsion, valeurs normales ; choix de l'os à
planifier (`cora_cas.json`).

**Validation** (détails : `code_source/README.md`) : sur l'os du modèle posé au hasard, côté toujours reconnu, repères
robustes à moins de 1 mm, angles frontaux à moins de 1,3° ; sur le lévrier, les 3 os coupés sont refusés et les angles
du fémur et du tibia complets sont dans les normes ; planification sur les os réels avec déformités de test : déformité
retrouvée à moins de 0,001°, dérotation exacte (torsion revenue à 0,01° près), broches parallèles après correction.

## Ligne de commande (sans interface)

```bash
cd code_source
../../.venv/bin/python lancer_tout.py                 # toutes les séries, étapes 1 à 6 (≈ 2 min pour les 3)
../../.venv/bin/python etape6_reperes.py              # étape 6 seule sur les résultats existants
../../.venv/bin/python etape7_guide.py --prescription prescription.json --os os.stl --sortie dossier   # guides
../../.venv/bin/python tests/test_chaine.py           # tests : fantôme CT (≈ 3 s)
../../.venv/bin/python tests/test_reperes.py          #         repères (≈ 13 s)
../../.venv/bin/python tests/test_guide.py            #         guides (≈ 90 s)
cd cora && node tests/test_cas.mjs && node tests/test_reel.mjs   # planification : os fictif, os segmentés
# campagne de la stratégie (606 cas, règles R1 à R9, ≈ 30 s), avec export d'un sous-ensemble de cas pour les guides
node tests/campagne_strategie.mjs ../campagne_strategie 300 --exporter
../../.venv/bin/python tests/campagne_guides.py ../campagne_strategie/guides --processus 4   # guides + contrôles
#   options : --filtre <texte> (cas dont le nom le contient), --reprendre, --rapport (rapport seul)
# première campagne (os fictif) : cas planifiés, puis guides + contrôles « de chirurgien » (≈ 8 s par cas)
node tests/campagne_export.mjs ../campagne tout 160 11
../../.venv/bin/python tests/campagne_guides.py ../campagne --processus 4     # rapport : ../campagne/rapport_campagne.md
# application autonome macOS (≈ 3 min ; à relancer après une modification du programme)
bash ../application/lanceurs/creer_app_autonome.sh
```

## Ce que contient `resultats/<série>/`

Les fichiers de CT-scan (`<os>.stl`, `segmentation.seg.nrrd`, `rapport.md`, `rapport.json`, aperçus,
`reperes_auto.mrk.json`), plus :

| Fichier | Contenu |
|---|---|
| `cora_cas.json` | l'os à planifier dans cette série, la raison du choix, les autres os et pourquoi ils sont ignorés |
| `cora_femur.json`, `cora_tibia.json` | repère, côté, complétude, repères (repère de l'os et du scanner), angles, torsion, valeurs normales |
| `cora_femur.png`, `cora_tibia.png` | repères sur les trois vues, pour vérifier |
| `cora_*.bin` | maillages dans le repère de l'os (lus par l'onglet 2) |
| `guide_<os>_<coin>/` | guides construits à l'étape 12 : `guide_coupe.stl` (à imprimer), `guide_coupe_scanner.stl` (repère du scanner), `guide_reduction.stl`, `os_corrige.stl`, `os_planifie.stl`, `prescription.json`, `guide.json`, `guide.png`, plans 2D `plan_generique.*` et `plan_guide.*` (SVG, PDF, PNG) |

Les guides de l'os fictif vont dans `resultats/_os_fictif/`.

## Limites

* **Repères automatiques** : à vérifier (étape 1 de l'onglet 2, ou `cora_<os>.png`). Méthode testée sur un seul chien
  (lévrier) et sur le modèle synthétique ; un os très déformé, un implant ou un petit chien peuvent la tromper.
* **Angles sagittaux** : lignes articulaires courtes (20 à 30 mm) → sensibles à quelques degrés.
* **Valeurs normales** : publiées surtout pour le Labrador, le berger allemand, le Golden et le Rottweiler ; pour le
  lévrier, seule la pente tibiale a une référence propre (Wilke 2002). L'angle AMA de l'équipe Vezzoni n'est pas encore
  mesuré.
* **Antéversion fémorale** : indicative (axe du col estimé automatiquement).
* **Guides** : prototypes de recherche, non validés cliniquement ni sur os imprimé. Imprimer d'abord des coupons de fente
  et de manchon pour régler les jeux (0,2 mm) ; matériau conseillé : PA12 (frittage laser) ou résine stérilisable. La
  plaque d'ostéosynthèse et les tissus mous ne sont pas modélisés (les broches peuvent gêner la plaque ; l'abord doit
  dégager toute la zone d'appui).
* **Abords et marges** : les secteurs d'abord (fémur latéral ± 60° ou médial ± 45°, tibia médial ± 60° ou latéral ± 30°)
  et les marges (cartilage 3 à 5 mm, os voisins 1 à 2 mm, entrée de broche ≤ 50°) sont des choix raisonnés de ce
  projet, à valider avec un chirurgien. Le cartilage est connu sur l'os fictif ; sur un os segmenté, la planification
  utilise des zones articulaires géométriques (fractions de la longueur de l'os), et les os voisins seulement s'ils ont
  été segmentés (fibula).
* **Règle 2** : la translation à l'ostéotomie peut réduire le contact osseux (alerte au-delà de 50 % de la largeur) ;
  l'alternative classique, l'ostéotomie en dôme centrée sur le CORA, n'est pas proposée (voir « Et l'ostéotomie en
  dôme ? »).
* **Fémur : déformités distales seulement** (hypothèse du projet). Les 6 préréglages du fémur ont leur apex entre 70 et
  78 % de la longueur et le curseur « Niveau de l'apex » est limité à 62–82 % : c'est là que se trouvent les déformités
  fémorales usuelles du chien (varus ou valgus distal des luxations de rotule), corrigées par ostéotomie fémorale
  distale. Les déformités proximales (coxa vara ou valga, antéversion du col) sont dans le col et se corrigent par une
  ostéotomie intertrochantérienne ou du col, autre méthode, hors du champ de l'application ; un cal vicieux de la
  diaphyse proximale n'est pas proposé. Au tibia, l'apex peut être proximal (25 à 85 %).
* **Un seul apex** (comme CORA 3D) : les déformités à deux apex ne sont pas prises en charge. Elles sont fréquentes à
  l'avant-bras (70 membres sur 106 dans le plan frontal, Knapp 2016) ; au fémur et au tibia, les déformités habituelles
  (varus distal du fémur, valgus proximal du tibia, pes varus) sont décrites à un apex.
* **Contraintes biologiques** : physes et zones articulaires approchées en fractions de la longueur de l'os (non
  segmentées) ; marges (tubérosité 8 mm, épicondyles 6 mm, fragment ≥ 25 mm) à valider avec un chirurgien.
* **Application autonome** : macOS sur Apple Silicon (≈ 800 Mo) ; à reconstruire après chaque modification du programme.
* Les trois séries du dossier sont trois examens distincts : un fémur et un tibia complets, mais pas du même examen.
* Os rigide (les tissus mous et la plaque ne sont pas modélisés).

## Contenu du dossier

```
CT-CORA3D/
├── CT-CORA3D.app             application macOS (lanceur de développement ; l'application autonome est dans ~/Applications)
├── Lancer sur Windows.bat    application Windows
├── LISEZ-MOI.md              ce fichier
├── application/              serveur local, fenêtre native et interface (voir application/README.md)
├── code_source/              programme Python (étapes 1 à 7), tests, et cora/ (planification, JavaScript)
├── documents/                cahier des charges, rapport de projet et documentation technique (PDF et Word), figures
│                             (schémas draw.io modifiables) et sources en Markdown (voir documents/LISEZ-MOI.md)
└── resultats/                sorties de la segmentation, des repères et des guides (<série>/), guides de l'os fictif
                              (_os_fictif/), rapports des campagnes (_campagne_os_fictif/, _campagne_strategie/)
```
