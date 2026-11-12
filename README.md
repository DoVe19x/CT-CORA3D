# CT-CORA3D

Du scanner d'une patte de chien au guide chirurgical imprimable en 3D.
Projet PMD2, Master en ingénierie biomédicale, ECAM Brussels Engineering School (2026-2027).
Groupe : Dorian Verstappen, Imane Bikass, Mohamed-Amine Ahmidouch.

CT-CORA3D est une application de bureau (macOS, Windows) qui :

1. lit un scanner (DICOM) et sépare les os de la patte arrière (fémur, tibia, fibula, rotule…) ;
2. place automatiquement les repères anatomiques et mesure la déformation ;
3. planifie l'ostéotomie de correction en 3D par la méthode du CORA (Paley) ;
4. construit deux guides imprimables : un **guide de coupe** (deux moitiés reliées par des ponts sécables) et un
   **guide de réduction**, avec **une broche de Kirschner par fragment**.

> Prototype de recherche : ce n'est pas un dispositif médical. Toute planification doit être validée par un vétérinaire.

## Lancer

| Système | Double-cliquer sur |
|---|---|
| macOS | `CT-CORA3D.app` |
| Windows | `Lancer sur Windows.bat` |

Il faut Python 3.10 ou plus récent. Au premier lancement, les bibliothèques (`application/requirements.txt`) sont
installées dans un dossier propre à l'ordinateur (quelques minutes, internet nécessaire).

Les scanners se placent dans `dicom/` (jamais envoyé sur GitHub : environ 17 Go). Sans scanner, l'application
s'ouvre sur les **exemples** livrés : trois séries du lévrier déjà segmentées et l'os fictif.

## Contenu

```
CT-CORA3D/
├── README.md              ce fichier
├── LICENSE                licence du code (MIT)
├── CT-CORA3D.app          lanceur macOS
├── Lancer sur Windows.bat lanceur Windows
├── application/           serveur local, fenêtre et interface (onglets Segmentation CT et Planification CORA)
├── code_source/           programme Python (étapes 1 à 7), cœur de planification JavaScript (cora/), tests
├── exemples/              séries du lévrier et guides de démonstration (copiés dans resultats/ au démarrage)
├── documents/             cahiers des charges, dossier complet, plans 2D du guide générique, justification du guide
├── dicom/                 vos scanners (ignoré par Git)
└── resultats/             tout ce que produit l'application (ignoré par Git)
```

## Documentation

* `documents/CT-CORA3D_Dossier_complet.pdf` : le projet de A à Z (méthodes, calculs, code, validation).
* `documents/cahier_des_charges/` et `documents/cahier_des_charges_it/` : cahiers des charges fonctionnel et
  informatique (LaTeX, à ouvrir dans Overleaf).
* `documents/justification_guide/` : pourquoi le guide générique est fait ainsi.
* `documents/plan_guide_generique/` : plans 2D du guide de coupe et du guide de réduction (DWG, DXF, PDF).
* `code_source/README.md` et `application/README.md` : organisation du code.

## Tests

Depuis `code_source/` :

```
node cora/tests/test_cas.mjs        # planification sur l'os fictif (déformations connues)
node cora/tests/test_reel.mjs       # planification sur les os du lévrier
python tests/test_chaine.py         # chaîne complète sur un scanner synthétique
python tests/test_reperes.py        # repères automatiques
python tests/test_guide.py          # construction et contrôles des guides
python tests/test_parametres.py     # mêmes paramètres du guide en Python et en JavaScript
```

Après une modification de l'étape 7 ou de la planification, `python refaire_exemples.py` reconstruit les guides de
démonstration, et `bash ../application/lanceurs/creer_app_autonome.sh` l'application autonome macOS.
