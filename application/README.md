# application — CT-CORA3D (interface et serveur local)

Interface graphique du programme. Elle **ne fait aucun calcul de segmentation elle-même** : elle appelle les étapes de
`code_source/` (les mêmes que `lancer_tout.py`). La planification CORA, elle, tourne dans la page web de la fenêtre
(`code_source/cora/`, assemblé dans `interface/cora/index.html`) ; les guides imprimables (étape 7) sont construits par
le serveur à la demande de l'onglet CORA.

## Principe

```
fenêtre native (fenetre.py : pywebview — WebKit sur macOS, WebView2 sur Windows ; lanceur de développement : à défaut Chrome / Edge)
  interface/index.html ── page à deux onglets ──┬── interface/ct/    onglet 1 : segmentation CT (coupes, os 3D, corrections)
                                                └── interface/cora/  onglet 2 : planification CORA (os segmenté ou fictif)
        │  requêtes HTTP locales (127.0.0.1 uniquement : rien ne sort de l'ordinateur)
        ▼
serveur.py (Python) ──► code_source/etape1 … etape7 ──► CT-CORA3D/resultats/<série>/
```

* `serveur.py` démarre un petit serveur web **local**, choisit un port libre et lance `fenetre.py`, qui affiche
  l'interface dans une fenêtre du système : nom « CT-CORA3D » et icône dans le Dock / la barre des tâches, menus en
  français, boîtes « Enregistrer sous » pour les exports (STL, ZIP). Les liens `target=_blank` vers un fichier du serveur
  (aperçus, rapports) ouvrent une petite fenêtre de l'application, ceux vers internet (DOI) le navigateur habituel.
  Si la fenêtre native est impossible (`fenetre.py` sort avec le code 3 : pywebview absente ou inutilisable), le
  serveur ouvre comme avant une fenêtre Chrome / Edge sans barre d'adresse (sinon le navigateur par défaut).
* pywebview est installée par les lanceurs (`fenetre.py --installer`) dans un dossier propre à l'ordinateur et à la
  version de Python, hors OneDrive (`~/Library/Application Support/CTCORA3D/fenetre-py3XX`,
  `%LOCALAPPDATA%\CTCORA3D\fenetre-py3XX`) : l'environnement Python du projet n'est pas modifié. Elle n'est pas dans
  `requirements.txt` exprès : un échec de son installation ne doit pas empêcher l'application de démarrer.
* Les calculs de segmentation tournent dans le fil principal de Python (VTK l'exige sur macOS), un à la fois ;
  l'interface suit leur progression (6 étapes, la dernière = repères pour CORA). Pendant un calcul, le serveur empêche
  la mise en veille par inactivité (`sans_mise_en_veille` : `caffeinate -i` sur macOS, `SetThreadExecutionState` sur
  Windows) : sans cela, un calcul lancé avant de s'éloigner de l'ordinateur restait figé jusqu'au réveil.
* Les deux vues 3D (onglets CT et CORA) sont redessinées **à la demande** : seulement quand la caméra bouge (inertie
  comprise), qu'une vue s'anime ou que la scène change, au lieu de 60 images par seconde en permanence (vérifié dans
  Chrome : 0 image par seconde au repos) ; densité de pixels plafonnée à 2 (écrans 4K sous Windows).
* Les deux onglets sont deux pages indépendantes (chacune dans son cadre) : la page d'accueil leur transmet le thème
  (clair / sombre) et relie le bouton « CORA → » de l'onglet 1 à l'onglet 2 (messages `postMessage`).
* Arrêt : bouton ⏻ (la fenêtre native se ferme alors d'elle-même), ou fermeture de la fenêtre : le serveur s'arrête
  dès que le calcul en cours est fini. Fenêtre Chrome / Edge : une minute sans signe de vie (`/api/ping`).

## Application autonome (macOS et Windows)

`lanceurs/creer_app_autonome.sh` construit `~/Applications/CT-CORA3D.app` avec PyInstaller (recette
`lanceurs/ct_cora3d.spec`) : Python, toutes les bibliothèques (y compris pywebview), le programme et ses données
(interface, icône, calibration des repères) sont dans le paquet (≈ 800 Mo). Construction hors OneDrive, dans
`~/Library/Caches/CTCORA3D/` (environnement de construction et fichiers intermédiaires) ; ≈ 3 min.

Windows : `lanceurs\creer_app_windows.bat` (double-clic) construit, avec la même recette, le dossier
`%LOCALAPPDATA%\Programs\CT-CORA3D` (CT-CORA3D.exe et ses bibliothèques) et crée les raccourcis du menu Démarrer et du
Bureau ; construction dans `%LOCALAPPDATA%\CTCORA3D\construction-app`. La recette choisit le moteur de la fenêtre
selon le système (WebKit / Cocoa sur macOS ; WebView2 via pythonnet et WinForms sur Windows), l'icône (`.icns` /
`.ico`) et ne fait le paquet `.app` que sur macOS. Pas encore construite sur un PC Windows au 22/10/2026 (PyInstaller
ne construit que pour le système sur lequel il tourne).

```
CT-CORA3D.app/Contents/MacOS/CT-CORA3D            (ct_cora3d_app.py)
  ├─ sans argument : processus FENÊTRE (fenetre.py) ── affiche « Démarrage des calculs… », puis l'interface dès que
  │                  le serveur répond ; fermer la fenêtre arrête le serveur
  └─ --serveur … : processus de CALCUL (serveur.py --sans-fenetre --suivre-parent), lancé par la fenêtre, sans icône
                   dans le Dock (politique d'activation « Prohibited »), entrée standard reliée à la fenêtre par un tube
```

* Deux processus parce que la fenêtre (Cocoa) et les calculs (VTK) exigent chacun le fil principal sur macOS.
* `--suivre-parent` : le serveur s'arrête (après le calcul en cours) quand le tube de son entrée standard se ferme,
  c'est-à-dire quand la fenêtre se termine, quelle qu'en soit la cause. Le bouton ⏻ arrête le serveur, et la fenêtre
  se ferme d'elle-même.
* Le serveur HTTP (`Serveur`) ne fait pas la résolution inverse du nom de la machine (`socket.getfqdn`) que fait
  `HTTPServer` : pour une application que macOS ne connaît pas encore, elle passe par mDNS et bloquait le démarrage
  ≈ 30 s (démarrage mesuré ensuite : 5,8 s).
* Dossiers : voir `code_source/parametres.py` (dossier du projet d'où l'application a été construite, noté dans
  `construction.json` du paquet, sinon `~/Documents/CT-CORA3D`). Rien n'est écrit dans le paquet.
* Essai sans construire : `python ct_cora3d_app.py` avec un Python qui a les bibliothèques et pywebview.

## Lancer

| Système | Double-cliquer sur (dossier `CT-CORA3D/`) |
|---|---|
| macOS | `~/Applications/CT-CORA3D.app` (application autonome) ou `CT-CORA3D.app` (lanceur de développement) |
| Windows | raccourci « CT-CORA3D » (application autonome, `creer_app_windows.bat`) ou `Lancer sur Windows.bat` (développement) |
| Ligne de commande | `python serveur.py` (options `--port`, `--sans-fenetre`, `--dossier`, `--resultats`, `--sans-veille`, `--suivre-parent`) |

Windows : le serveur tourne avec `pythonw.exe` (pas de console) ; journal `%LOCALAPPDATA%\CTCORA3D\CTCORA3D.log`.

**Python.** Le lanceur utilise d'abord l'environnement propre à l'ordinateur, hors OneDrive, s'il contient les
bibliothèques ; sinon `PMD2/.venv` ; sinon, au premier lancement, il crée l'environnement propre à l'ordinateur et y
installe `requirements.txt` (Python 3.10 ou plus récent et une connexion internet, une seule fois). Emplacements :
macOS `~/Library/Application Support/CTCORA3D/venv` (journal `~/Library/Logs/CTCORA3D.log`), Windows
`%LOCALAPPDATA%\CTCORA3D\venv`. Pourquoi cet ordre : OneDrive (« fichiers à la demande ») met une partie des fichiers
de `PMD2/.venv` « en ligne uniquement » ; les importer les retélécharge, ce qui a bloqué un lancement plus de deux
minutes (15/10/2026 : 1 435 fichiers sur 11 163 en ligne uniquement).

## API du serveur (utilisée par les deux onglets)

| Requête | Rôle |
|---|---|
| `GET /api/etat`, `/api/config`, `/api/serie`, `/api/coupe`, `/api/point`, `/api/maillage` | onglet 1 ; `/api/serie` donne aussi l'état CORA de chaque fémur / tibia |
| `POST /api/action` | `inventaire`, `ouvrir`, `segmenter`, `nommer`, `separer`, `oublier` (calculs dans le fil principal) |
| `POST /api/action` (`guide`) | onglet CORA, étape 12 : `{prescription, sommets, triangles, voisins?, articulaire?, serie?, nom_os?}` (os planifié en base64 : float32, uint32 ; `voisins` = `[{nom, sommets, triangles}]` fibula, rotule, fabelles tels que planifiés ; `articulaire` = 1 octet par sommet, ≥ 128 = cartilage) → `etape7_guide.py` dans le fil de calcul ; résultat dans `resultats/<série>/guide_<os>_<coin>/` (os fictif : `resultats/_os_fictif/…`), dossier renvoyé par `/api/etat` (`travail.resultat`) |
| `GET /api/cora/cas` | l'os à planifier : os complet détecté dans la série ouverte dans l'onglet 1 (sinon la dernière segmentée), raison du choix, autres os et pourquoi ils sont ignorés (`cora_cas.json`) |
| `GET /api/cora/guide?dossier=…` | `guide.json` d'un dossier de guides (contrôles, mode opératoire) et liste des fichiers |
| `GET /api/cora/guide/fichier?dossier=…&f=…` | un fichier de ce dossier (`.stl`, `.bin`, `.json`, `.png` ; `&telecharger=1` pour l'enregistrer) |
| `GET /api/cora/liste` | tous les fémurs et tibias segmentés de `resultats/` : prêt, incomplet (coupé), à analyser |
| `GET /api/cora/os?serie=…&os=…` | `cora_<os>.json` (calculé à la demande, en ≈ 1,3 s, si absent ou plus ancien que le STL) |
| `GET /api/cora/maillage?serie=…&quoi=…` | maillage dans le repère de l'os (`cora_<quoi>.bin`) |
| `POST /api/montrer`, `/api/choisir_dossier`, `/api/quitter`, `/api/ping` | dossier des résultats (ou d'un guide : `{dossier_guide}`), choix du dossier DICOM, arrêt, signe de vie |

Après une correction dans l'onglet 1 (renommer, séparer) qui touche le fémur, le tibia ou la fibula, l'étape 6 est
refaite pour ces os.

## Contenu

| Fichier | Rôle |
|---|---|
| `serveur.py` | serveur local, calculs, API |
| `ct_cora3d_app.py` | point d'entrée de l'application autonome : fenêtre, ou serveur de calcul avec `--serveur` |
| `fenetre.py` | fenêtre native de l'application (pywebview) ; page d'attente quand le serveur démarre en même temps ; `--verifier`, `--installer` pour les lanceurs |
| `interface/index.html` | page d'accueil à deux onglets (thème, quitter, liaison des onglets) |
| `interface/ct/` | onglet 1 : `index.html`, `app.js`, `style.css`, icône |
| `interface/cora/index.html` | onglet 2 : **fichier produit** par `code_source/cora/build_app.py` (ne pas modifier à la main) |
| `interface/vendor/` | Three.js r170 (licence MIT) pour l'onglet 1 |
| `lancer_mac.sh`, `lanceurs/` | lanceur macOS de développement (`creer_app_mac.sh` reconstruit `CT-CORA3D.app` du projet) ; application autonome (`creer_app_autonome.sh`, recette PyInstaller `ct_cora3d.spec`) |
| `icone/` | icône (`creer_icone.py`) aux formats PNG, ICNS, ICO |
| `requirements.txt` | bibliothèques Python (dont manifold3d pour l'étape 7, importée seulement quand on construit un guide) |

## Essai sans fenêtre

```bash
python serveur.py --sans-fenetre --sans-veille --port 8765
# puis http://127.0.0.1:8765/ dans un navigateur
```
