# documents — les documents du projet CT-CORA3D

| Document | Pages | Pour qui | Contenu |
|---|---|---|---|
| `CT-CORA3D_Cahier_des_charges` | 7 | référent clinique, encadrement | ce que le logiciel doit faire, hypothèses, critères de réussite, organisation |
| `CT-CORA3D_Rapport_de_projet` | 24 | jury, encadrement | le projet expliqué étape par étape, les résultats, les limites |
| `CT-CORA3D_Documentation_technique` | 10 | service informatique | organisation du logiciel, installation, utilisation, tests, données |

Chaque document existe en **PDF** (pour lire ou rendre) et en **Word** (pour modifier).

## À compléter

Les champs à compléter sont écrits en gras entre crochets, par exemple **[à compléter]** : noms de l'équipe et de
l'encadrement (page de titre), dates du projet, licence du code.

## Les figures (`figures/`)

19 figures en PNG. Les 7 schémas (`chaine_du_projet`, `organisation_du_logiciel`, `choix_du_coin`, `les_deux_guides`,
`deroule_operation`, `validation`, `utilisation`) ont aussi un fichier `.drawio` qui s'ouvre et se modifie dans draw.io.

## Modifier un document

* **Dans Word** : ouvrir le `.docx`, modifier, puis « Enregistrer sous… PDF » si besoin.
* **Ou à la source** : modifier le fichier `.md` dans `sources/` (même syntaxe que R Markdown), puis lancer
  `bash sources/construire.sh` : les PDF et les Word sont refaits (environ 1 minute). Avec `bash sources/construire.sh
  figures`, les figures sont refaites aussi.

Il faut pandoc (celui de RStudio est utilisé automatiquement) et XeLaTeX (TinyTeX) ; pour les figures, draw.io et le
Python du projet.
