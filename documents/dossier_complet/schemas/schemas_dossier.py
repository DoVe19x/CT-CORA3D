"""
schemas_dossier.py — schémas draw.io du dossier complet (fichiers .drawio modifiables dans draw.io).

Usage : python3 schemas_dossier.py            (écrit les .drawio dans ce dossier)
Le script ../construire.sh les exporte ensuite en PDF (vectoriel) avec draw.io.
Pour retoucher un schéma : ouvrir le .drawio dans draw.io. Attention : relancer ce script écrase les retouches
(copier le fichier sous un autre nom avant de le retoucher, ou modifier ce script).

Les schémas choix_du_coin, utilisation et chaine_du_projet sont des copies de ../../figures/ (rapport du 19/10/2026).
"""
from pathlib import Path
from xml.sax.saxutils import escape

ICI = Path(__file__).resolve().parent

# couleurs (fond, bord) : une par grande partie du projet (les mêmes que documents/sources/figures_drawio.py)
COULEURS = {
    "scanner": ("#eef2f6", "#5b6b7a"),
    "segmentation": ("#e6f0fa", "#1f5f8b"),
    "planification": ("#fdf0e2", "#b8611a"),
    "guides": ("#e8f5e4", "#3a7d2c"),
    "bloc": ("#f1eaf7", "#6f4a99"),
    "neutre": ("#ffffff", "#666666"),
    "fond": ("#f7f7f7", "#bbbbbb"),
    "fait": ("#e8f5e4", "#3a7d2c"),
    "partiel": ("#fff6db", "#b38600"),
    "afaire": ("#fbe9e9", "#b03a3a"),
    "fichier": ("#fffdf5", "#8a7a55"),
}
FORMES = {
    "boite": "rounded=1;arcSize=10;",
    "carre": "rounded=0;",
    "fichier": "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=8;",
    "note": "shape=note;size=14;",
    "document": "shape=document;boundedLbl=1;size=0.15;",
}


POLICE = "Avenir Next"          # police des titres du document (macOS) ; draw.io prend une police voisine ailleurs

def _q(t):
    return escape(t, {'"': "&quot;"})


class Schema:
    def __init__(self):
        self.cellules, self.n = [], 1

    def boite(self, x, y, l, h, texte, couleur="neutre", forme="boite", taille=14, align="center", valign="middle",
              pointilles=False, epaisseur=1.5):
        fond, bord = COULEURS[couleur]
        self.n += 1
        style = (FORMES[forme] + f"whiteSpace=wrap;html=1;fillColor={fond};strokeColor={bord};strokeWidth={epaisseur};"
                 f"fontFamily={POLICE};fontSize={taille};align={align};verticalAlign={valign};spacing=8;"
                 + ("dashed=1;" if pointilles else ""))
        self.cellules.append(f'<mxCell id="c{self.n}" value="{_q(texte)}" style="{style}" vertex="1" parent="1">'
                             f'<mxGeometry x="{x}" y="{y}" width="{l}" height="{h}" as="geometry"/></mxCell>')
        return f"c{self.n}"

    def texte(self, x, y, l, h, texte, taille=13, align="center", couleur="#333333"):
        self.n += 1
        style = (f"text;html=1;whiteSpace=wrap;fontFamily={POLICE};fontSize={taille};align={align};"
                 f"verticalAlign=middle;fontColor={couleur};")
        self.cellules.append(f'<mxCell id="c{self.n}" value="{_q(texte)}" style="{style}" vertex="1" parent="1">'
                             f'<mxGeometry x="{x}" y="{y}" width="{l}" height="{h}" as="geometry"/></mxCell>')
        return f"c{self.n}"

    def fleche(self, a, b, texte="", sortie=None, entree=None, points=(), pointilles=False, double=False):
        self.n += 1
        style = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor=#444444;"
                 f"strokeWidth=1.8;fontFamily={POLICE};fontSize=12;labelBackgroundColor=#ffffff;"
                 + ("dashed=1;" if pointilles else "") + ("startArrow=block;startFill=1;" if double else ""))
        if sortie:
            style += f"exitX={sortie[0]};exitY={sortie[1]};exitDx=0;exitDy=0;"
        if entree:
            style += f"entryX={entree[0]};entryY={entree[1]};entryDx=0;entryDy=0;"
        pts = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
        tableau = '<Array as="points">' + pts + "</Array>" if pts else ""
        geo = '<mxGeometry relative="1" as="geometry">' + tableau + "</mxGeometry>"
        self.cellules.append(f'<mxCell id="c{self.n}" value="{_q(texte)}" style="{style}" edge="1" parent="1" '
                             f'source="{a}" target="{b}">{geo}</mxCell>')

    def ecrire(self, nom):
        xml = ('<mxfile host="CT-CORA3D"><diagram id="d" name="' + escape(nom) + '"><mxGraphModel grid="0" page="0">'
               '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cellules) +
               '</root></mxGraphModel></diagram></mxfile>')
        (ICI / f"{nom}.drawio").write_text(xml, encoding="utf-8")


def T(titre, detail="", taille_detail=12):
    """Texte d'une boîte : titre en gras, détail plus petit en dessous."""
    return f"<b>{titre}</b>" + (f"<br><font style='font-size:{taille_detail}px'>{detail}</font>" if detail else "")


def F(texte):
    """Nom de fichier en police à chasse fixe."""
    return f"<font face='Menlo' style='font-size:11px'>{texte}</font>"


# --------------------------------------------------------------------------------------------- les schémas
def serpent(s, etapes, L=250, H=104, dx=290, dy=146, x0=20, y0=20, cols=3, taille=16):
    """Boîtes en serpentin (ligne 1 de gauche à droite, ligne 2 de droite à gauche…), reliées par des flèches."""
    ids = []
    for i, (t, d, c) in enumerate(etapes):
        r, k = divmod(i, cols)
        col = k if r % 2 == 0 else cols - 1 - k
        ids.append(s.boite(x0 + col * dx, y0 + r * dy, L, H, T(t, d, 13), c, taille=taille))
    for i in range(len(ids) - 1):
        r1, r2 = i // cols, (i + 1) // cols
        if r1 == r2:
            gauche_droite = r1 % 2 == 0
            s.fleche(ids[i], ids[i + 1], sortie=(1, 0.5) if gauche_droite else (0, 0.5),
                     entree=(0, 0.5) if gauche_droite else (1, 0.5))
        else:
            s.fleche(ids[i], ids[i + 1], sortie=(0.5, 1), entree=(0.5, 0))
    return ids


def chaine_complete():
    """Toute la chaîne : étapes, programme qui les fait, fichiers produits."""
    s = Schema()
    s.boite(8, 8, 874, 292, "", "fond", forme="carre", epaisseur=1)
    s.texte(16, 10, 860, 24, "<b>Onglet 1 · Segmentation CT</b> — Python (code_source/etape1 à etape6)", 14, "left",
            "#1f5f8b")
    s.boite(8, 300, 874, 296, "", "fond", forme="carre", epaisseur=1)
    s.texte(16, 302, 860, 24, "<b>Onglet 2 · Planification CORA</b> — JavaScript, puis l'étape 7 en Python", 14, "left",
            "#b8611a")
    etapes = [
        ("Série DICOM", "les coupes du scanner<br>" + F("CT-scan/&lt;série&gt;/"), "scanner"),
        ("1 · Lecture", "volume en HU<br>et matrice voxel → mm", "segmentation"),
        ("2 · Segmentation", "une étiquette par os", "segmentation"),
        ("3 · Identification", "un nom par os<br>(fémur, tibia…)", "segmentation"),
        ("4 · Maillage", F("femur.stl, tibia.stl…") + "<br>" + F("segmentation.seg.nrrd"), "segmentation"),
        ("5 · Contrôle", F("rapport.md / .json") + "<br>aperçus PNG", "segmentation"),
        ("6 · Repères", F("cora_&lt;os&gt;.json") + "<br>repère, côté, angles", "segmentation"),
        ("Planification CORA", "13 étapes à l'écran :<br>CORA, coin, broches", "planification"),
        ("Prescription", F("prescription.json") + "<br>plans, charnière, T", "planification"),
        ("7 · Guides", F("guide_coupe.stl") + "<br>" + F("guide.json") + ", plans 2D", "guides"),
        ("Contrôle humain", "le chirurgien vérifie<br>et décide", "bloc"),
        ("Impression, bloc", "en dehors du logiciel", "bloc"),
    ]
    serpent(s, etapes, y0=44)
    s.ecrire("chaine_complete")


def architecture_application():
    s = Schema()
    W = 820
    s.boite(10, 10, W, 196, "", "fond", forme="carre", epaisseur=1)
    s.texte(20, 14, W - 20, 26, "<b>Fenêtre native</b> — " + F("application/fenetre.py") + " (pywebview)", 15, "left")
    o1 = s.boite(30, 50, 370, 136, T("Onglet 1 · Segmentation CT", F("interface/ct/") + "<br>liste des séries, coupes,<br>"
                                     "os en 3D, renommer, séparer", 13), "segmentation", taille=16)
    o2 = s.boite(440, 50, 370, 136, T("Onglet 2 · Planification CORA", F("interface/cora/index.html") + "<br>"
                                      "cœur " + F("cora_simple.js") + ", 3D Three.js<br>13 étapes", 13), "planification",
                 taille=16)
    srv = s.boite(10, 262, W, 112, T("Serveur local — " + F("application/serveur.py"),
                                     "adresse 127.0.0.1 seulement · un calcul à la fois<br>" + F("/api/action") +
                                     " lance un calcul · " + F("/api/etat") + " donne l'avancement", 13), "neutre",
                  taille=16)
    s.boite(10, 432, W, 160, "", "fond", forme="carre", epaisseur=1)
    s.texte(20, 436, W - 20, 26, "<b>Le programme</b> — " + F("code_source/") + " (Python)", 15, "left")
    noms = ["etape1<br>lecture", "etape2<br>segmen-<br>tation", "etape3<br>identifi-<br>cation", "etape4<br>maillage",
            "etape5<br>contrôle", "etape6<br>repères", "etape7<br>guides"]
    cs = [s.boite(22 + i * 114, 474, 104, 100, n, "guides" if i == 6 else "segmentation", taille=13)
          for i, n in enumerate(noms)]
    s.fleche(o1, srv, "requêtes", sortie=(0.5, 1), entree=(0.25, 0), double=True)
    s.fleche(o2, srv, "requêtes", sortie=(0.5, 1), entree=(0.75, 0), double=True)
    s.fleche(srv, cs[3], "appels de fonctions", sortie=(0.5, 1), entree=(0.5, 0))
    fic = s.boite(10, 640, 380, 104, T("Fichiers", "séries DICOM (lues)<br>" + F("resultats/") + " (écrits)", 13),
                  "fichier", forme="fichier", taille=16)
    s.fleche(cs[0], fic, sortie=(0.5, 1), entree=(0.3, 0))
    s.boite(430, 640, 400, 104, T("Lancement", "développement : le Python de l'ordinateur<br>autonome : PyInstaller "
                                  "copie Python, les<br>bibliothèques et le code (≈ 800 Mo)", 13), "bloc", forme="note",
            taille=16)
    s.ecrire("architecture_application")


def parcours_requete():
    """D'un clic à l'écran jusqu'au code et retour (exemple : « Segmenter la série »)."""
    s = Schema()
    lignes = [
        ("1 · Clic sur « Segmenter la série »", F("app.js") + " envoie /api/action, action « segmenter »", "segmentation"),
        ("2 · Le serveur reçoit la demande", F("serveur.py") + " met la tâche en file et répond tout de suite", "neutre"),
        ("3 · Le fil principal exécute", F("segmenter()") + " → " + F("lancer_tout.traiter()") + " → étapes 1 à 6",
         "guides"),
        ("4 · L'interface suit l'avancement", "elle interroge " + F("/api/etat") + " plusieurs fois par seconde",
         "segmentation"),
        ("5 · Le résultat s'affiche", "coupes colorées, os en 3D, carte « Os à planifier »", "segmentation"),
    ]
    ids = [s.boite(20, 20 + i * 92, 600, 68, T(t, d, 13), c, taille=16) for i, (t, d, c) in enumerate(lignes)]
    for a, b in zip(ids, ids[1:]):
        s.fleche(a, b)
    s.ecrire("parcours_requete")


def construction_guide():
    s = Schema()
    etapes = [
        ("Entrées", F("prescription.json") + "<br>os planifié, os voisins,<br>cartilage", "planification"),
        ("Grille de 0,3 mm", "distance signée d à l'os<br>(négative dans l'os)", "guides"),
        ("Primitives", "coque j ≤ d ≤ j + e, tours,<br>manchons (union lisse)", "guides"),
        ("Contraintes dures", "jeu à l'os et aux voisins, pas de<br>contre-dépouille, ni entre les os,<br>ni sur le cartilage",
         "guides"),
        ("Surface et solide", "matière trop fine retirée,<br>isosurface F = 0<br>→ solide exact", "guides"),
        ("Booléens exacts", "fentes, trous, chanfreins,<br>séparation des moitiés,<br>ponts (manifold3d)", "guides"),
        ("Guide de réduction", "barre et 2 manchons parallèles<br>sur l'os corrigé (trait<br>de scie compensé)", "guides"),
        ("Contrôles indépendants", "jeu mesuré, retrait, appui,<br>étanchéité, voisins…", "afaire"),
        ("Fichiers", F("guide_coupe.stl") + ", " + F("guide_reduction.stl") + "<br>" + F("guide.json") + ", plans 2D", "planification"),
    ]
    serpent(s, etapes, H=112, dy=150)
    s.ecrire("construction_guide")


def deroule_operation():
    s = Schema()
    etapes = [
        ("1 · Abord et pose", "le guide de coupe ne s'emboîte<br>que dans une seule position", "bloc"),
        ("2 · Forage des broches", "2 proximales, puis 2 distales,<br>à travers les manchons", "bloc"),
        ("3 · Coupe", "par chaque fente, jusqu'à la<br>profondeur de lame indiquée", "bloc"),
        ("4 · Séparer", "couper les 2 ponts ; retirer<br>les moitiés, puis le coin d'os", "bloc"),
        ("5 · Corriger", "fermer (ou ouvrir) et tourner<br>jusqu'à broches parallèles", "planification"),
        ("6 · Guide de réduction", "l'enfiler sur les broches<br>jusqu'au contact de l'os", "guides"),
        ("7 · Fixer", "plaque ; puis retirer le guide<br>de réduction et les broches", "bloc"),
    ]
    serpent(s, etapes, H=108, dy=150)
    s.ecrire("deroule_operation")


def niveaux_validation():
    s = Schema()
    L, H = 840, 112
    niveaux = [
        ("Niveau 1 — Cas simulés (fait)",
         "On déforme un os sain d'un angle connu, puis on vérifie que le programme le retrouve et sait le corriger. "
         "Erreur d'angle inférieure à 0,01° ; 606 stratégies et près de 1 800 guides sans erreur.", "fait"),
        ("Niveau 2 — Robustesse (en partie)",
         "Os posé au hasard, seuil ± 50 HU, faux scanner de forme connue, os du lévrier, lanceur Windows essayé. "
         "Reste à faire : d'autres scanners, d'autres races, des os malades.", "partiel"),
        ("Niveau 3 — Vrais cas et essais imprimés (à faire)",
         "Un premier cas clinique est arrivé, mais seulement son topogramme : le scanner complet est demandé. "
         "Il faut imprimer les guides, les essayer sur un os imprimé et comparer avec le chirurgien.", "afaire"),
    ]
    for i, (t, d, c) in enumerate(niveaux):
        s.boite(20, 20 + i * (H + 20), L, H, T(t, d, 14), c, align="left", taille=16)
    s.ecrire("niveaux_validation")


if __name__ == "__main__":
    for f in (chaine_complete, architecture_application, parcours_requete, construction_guide, deroule_operation,
              niveaux_validation):
        f()
    print("schémas écrits dans", ICI)
