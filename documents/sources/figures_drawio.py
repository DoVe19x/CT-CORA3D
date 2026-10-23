"""
figures_drawio.py — les schémas du projet au format draw.io (fichiers .drawio, modifiables dans draw.io).

Usage : python3 figures_drawio.py <dossier figures>
Le script construire.sh les exporte ensuite en PNG avec draw.io.
Pour modifier un schéma : ouvrir le .drawio dans draw.io (attention, relancer ce script écrase les retouches).
"""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# couleurs (fond, bord) : une par grande partie du projet
COULEURS = {
    "scanner": ("#eef2f6", "#5b6b7a"),
    "segmentation": ("#e6f0fa", "#1f5f8b"),
    "planification": ("#fdf0e2", "#b8611a"),
    "guides": ("#e8f5e4", "#3a7d2c"),
    "bloc": ("#f1eaf7", "#6f4a99"),
    "neutre": ("#ffffff", "#666666"),
    "fait": ("#e8f5e4", "#3a7d2c"),
    "partiel": ("#fff6db", "#b38600"),
    "afaire": ("#fbe9e9", "#b03a3a"),
}
FORMES = {
    "boite": "rounded=1;arcSize=10;",
    "losange": "rhombus;",
    "fichier": "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=8;",
    "note": "shape=note;size=14;",
}


class Schema:
    def __init__(self):
        self.cellules, self.n = [], 1

    def boite(self, x, y, l, h, texte, couleur="neutre", forme="boite", taille=14, align="center"):
        fond, bord = COULEURS[couleur]
        self.n += 1
        style = (FORMES[forme] + f"whiteSpace=wrap;html=1;fillColor={fond};strokeColor={bord};strokeWidth=1.5;"
                 f"fontFamily=Helvetica;fontSize={taille};align={align};spacing=8;")
        self.cellules.append(f'<mxCell id="c{self.n}" value="{escape(texte, {chr(34): "&quot;"})}" style="{style}" '
                             f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{l}" height="{h}" as="geometry"/>'
                             '</mxCell>')
        return f"c{self.n}"

    def texte(self, x, y, l, h, texte, taille=13, align="center", couleur="#333333"):
        self.n += 1
        style = f"text;html=1;whiteSpace=wrap;fontFamily=Helvetica;fontSize={taille};align={align};fontColor={couleur};"
        self.cellules.append(f'<mxCell id="c{self.n}" value="{escape(texte, {chr(34): "&quot;"})}" style="{style}" '
                             f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{l}" height="{h}" as="geometry"/>'
                             '</mxCell>')

    def fleche(self, a, b, texte="", sortie=None, entree=None, points=()):
        self.n += 1
        style = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor=#444444;"
                 "strokeWidth=1.8;fontFamily=Helvetica;fontSize=12;labelBackgroundColor=#ffffff;")
        if sortie:
            style += f"exitX={sortie[0]};exitY={sortie[1]};exitDx=0;exitDy=0;"
        if entree:
            style += f"entryX={entree[0]};entryY={entree[1]};entryDx=0;entryDy=0;"
        pts = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
        tableau = '<Array as="points">' + pts + "</Array>" if pts else ""
        geo = '<mxGeometry relative="1" as="geometry">' + tableau + "</mxGeometry>"
        self.cellules.append(f'<mxCell id="c{self.n}" value="{escape(texte, {chr(34): "&quot;"})}" style="{style}" '
                             f'edge="1" parent="1" source="{a}" target="{b}">{geo}</mxCell>')

    def ecrire(self, fichier, nom):
        xml = ('<mxfile host="CT-CORA3D"><diagram id="d" name="' + escape(nom) + '"><mxGraphModel grid="0" page="0">'
               '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cellules) +
               '</root></mxGraphModel></diagram></mxfile>')
        Path(fichier).write_text(xml, encoding="utf-8")


def T(titre, detail=""):
    """Texte d'une boîte : titre en gras, détail plus petit en dessous."""
    return f"<b>{titre}</b>" + (f"<br><font style='font-size:12px'>{detail}</font>" if detail else "")


# --------------------------------------------------------------------------------------------- les schémas
def chaine_du_projet():
    s = Schema()
    L, H = 210, 76
    etapes = [
        (20, 30, "1. Scanner (CT)", "images DICOM du membre", "scanner"),
        (265, 30, "2. Segmentation", "les os en 3D (STL)", "segmentation"),
        (510, 30, "3. Repères anatomiques", "trouvés automatiquement", "segmentation"),
        (510, 170, "4. Planification CORA", "angle, niveau de coupe, coin", "planification"),
        (265, 170, "5. Guides imprimables", "guide de coupe et de réduction", "guides"),
        (20, 170, "6. Impression, chirurgie", "en dehors du logiciel", "bloc"),
    ]
    ids = [s.boite(x, y, L, H, T(t, d), c) for x, y, t, d, c in etapes]
    for a, b in zip(ids, ids[1:]):
        if a == ids[2]:
            s.fleche(a, b, sortie=(0.5, 1), entree=(0.5, 0))
        else:
            s.fleche(a, b)
    s.texte(20, 270, 700, 30, "<font color='#1f5f8b'>■</font> onglet 1 de l'application &nbsp;&nbsp; "
            "<font color='#b8611a'>■</font> onglet 2 &nbsp;&nbsp; <font color='#3a7d2c'>■</font> construit par l'application "
            "&nbsp;&nbsp; <font color='#6f4a99'>■</font> fait à la main", 12, "left")
    return s


def organisation_du_logiciel():
    s = Schema()
    f = s.boite(20, 20, 480, 96, T("Fenêtre de l'application (interface)",
                                   "onglet 1 « Segmentation CT » &nbsp;·&nbsp; onglet 2 « Planification CORA »<br>"
                                   "la planification est calculée dans la page (JavaScript)"), "planification")
    c = s.boite(20, 186, 480, 96, T("Programme de calcul (Python)",
                                    "lecture DICOM, segmentation, repères, construction des guides"), "segmentation")
    d = s.boite(20, 352, 480, 76, T("Fichiers sur l'ordinateur",
                                    "séries DICOM (lues) &nbsp;·&nbsp; dossier resultats/ (écrit)"), "neutre", "fichier")
    s.fleche(f, c, "demandes de calcul", sortie=(0.3, 1), entree=(0.3, 0))
    s.fleche(c, f, "résultats", sortie=(0.7, 0), entree=(0.7, 1))
    s.fleche(c, d, sortie=(0.5, 1), entree=(0.5, 0))
    s.boite(530, 20, 190, 300, "<b>Tout reste sur l'ordinateur</b><br><br>Les deux parties se parlent par "
            "l'adresse locale 127.0.0.1.<br><br>Aucune connexion Internet.<br><br>Une seule application à "
            "double-cliquer (macOS).", "neutre", "note", 13, "left")
    return s


def choix_du_coin():
    s = Schema()
    a = s.boite(150, 10, 420, 60, T("Pour chaque coin : fermeture et ouverture", "la scie entre à l'opposé de la charnière"),
                "planification")
    q = s.boite(210, 100, 300, 120, "<b>La scie peut-elle entrer<br>par un abord chirurgical<br>habituel ?</b>", "neutre",
                "losange", 13)
    oui = s.boite(10, 250, 230, 64, T("Oui", "le coin est possible"), "fait")
    non = s.boite(480, 250, 230, 64, T("Non", "ce coin est écarté (ou le guide est décalé)"), "afaire")
    s.fleche(a, q)
    s.fleche(q, oui, sortie=(0, 0.5), entree=(0.5, 0))
    s.fleche(q, non, sortie=(1, 0.5), entree=(0.5, 0))
    r = s.boite(10, 350, 700, 156, "<b>Si les deux coins sont possibles, on choisit avec, dans l'ordre :</b><br>"
                "1. la charnière d'os qui peut rester intacte (plus stable)<br>"
                "2. la coupe au CORA (pas de décalage de l'os)<br>"
                "3. un coin assez épais pour deux traits de scie<br>"
                "4. une ouverture pas trop grande (moins de 40 % de la largeur de l'os)<br>"
                "5. la longueur du membre (fermer raccourcit, ouvrir allonge)<br>"
                "6. sinon la fermeture : les deux morceaux d'os restent en contact", "planification", "boite", 13, "left")
    s.fleche(oui, r, sortie=(0.5, 1), entree=(0.1643, 0))
    return s


def les_deux_guides():
    s = Schema()
    g = s.boite(10, 10, 340, 60, T("Guide de coupe", "posé sur l'os pendant l'opération"), "guides")
    r = s.boite(380, 10, 340, 60, T("Guide de réduction", "posé après la coupe"), "bloc")
    for x, base, items in ((10, g, ["moulé sur l'os : une seule position possible",
                                    "1 ou 2 fentes qui guident la scie",
                                    "4 trous qui guident les broches",
                                    "2 moitiés reliées par 2 petits ponts à couper"]),
                           (380, r, ["s'enfile sur les 4 broches",
                                     "n'entre que si l'os est bien corrigé",
                                     "tient l'os pendant la pose de la plaque"])):
        prec = base
        for k, t in enumerate(items):
            b = s.boite(x + 20, 100 + k * 76, 300, 56, t, "neutre", "boite", 13)
            s.fleche(prec, b, sortie=(0.5, 1), entree=(0.5, 0))
            prec = b
    return s


def deroule_operation():
    s = Schema()
    L, H = 210, 80
    etapes = [
        (20, 20, "1. Scanner et planification", "avec l'application"),
        (265, 20, "2. Impression des guides", "et vérification"),
        (510, 20, "3. Pose du guide de coupe", "puis forage des 4 broches"),
        (510, 160, "4. Coupe de l'os", "la scie suit les fentes"),
        (265, 160, "5. Correction", "jusqu'à ce que les broches soient parallèles"),
        (20, 160, "6. Guide de réduction", "puis plaque ; on retire le reste"),
    ]
    couleurs = ["planification", "bloc", "guides", "guides", "guides", "bloc"]
    ids = [s.boite(x, y, L, H, T(t, d), c) for (x, y, t, d), c in zip(etapes, couleurs)]
    for a, b in zip(ids, ids[1:]):
        if a == ids[2]:
            s.fleche(a, b, sortie=(0.5, 1), entree=(0.5, 0))
        else:
            s.fleche(a, b)
    return s


def validation():
    s = Schema()
    niveaux = [
        ("fait", "Niveau 1 — Cas simulés (fait)",
         "On déforme un os sain d'un angle connu, puis on vérifie que le programme retrouve cet angle.<br>"
         "Résultat : erreur inférieure à 0,01° ; 606 planifications et 742 guides sans erreur."),
        ("partiel", "Niveau 2 — Robustesse (en partie)",
         "Os tourné au hasard, seuil de segmentation modifié, faux scanner de taille connue.<br>"
         "Reste à faire : d'autres scanners, d'autres races."),
        ("afaire", "Niveau 3 — Vrais cas et essais imprimés (à faire)",
         "Scanners de chiens malades, comparaison avec le chirurgien,<br>impression des guides et essai sur un os imprimé."),
    ]
    for k, (c, titre, detail) in enumerate(niveaux):
        s.boite(10, 10 + k * 120, 700, 100, f"<b>{titre}</b><br><font style='font-size:13px'>{detail}</font>", c,
                "boite", 14, "left")
    return s


def utilisation():
    s = Schema()
    L, H = 210, 80
    etapes = [
        (20, 20, "1. Choisir la série", "onglet 1 : liste des scanners"),
        (265, 20, "2. Segmenter", "bouton « Segmenter » (1 à 2 min)"),
        (510, 20, "3. Vérifier les os", "en coupes et en 3D"),
        (510, 160, "4. Planifier", "onglet 2 : 13 étapes expliquées"),
        (265, 160, "5. Construire les guides", "étape 12 (environ 20 s)"),
        (20, 160, "6. Récupérer les fichiers", "STL à imprimer, plans 2D"),
    ]
    couleurs = ["segmentation", "segmentation", "segmentation", "planification", "guides", "guides"]
    ids = [s.boite(x, y, L, H, T(t, d), c) for (x, y, t, d), c in zip(etapes, couleurs)]
    for a, b in zip(ids, ids[1:]):
        if a == ids[2]:
            s.fleche(a, b, sortie=(0.5, 1), entree=(0.5, 0))
        else:
            s.fleche(a, b)
    return s


SCHEMAS = {
    "chaine_du_projet": chaine_du_projet,
    "organisation_du_logiciel": organisation_du_logiciel,
    "choix_du_coin": choix_du_coin,
    "les_deux_guides": les_deux_guides,
    "deroule_operation": deroule_operation,
    "validation": validation,
    "utilisation": utilisation,
}

if __name__ == "__main__":
    dossier = Path(sys.argv[1] if len(sys.argv) > 1 else "../figures")
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, f in SCHEMAS.items():
        f().ecrire(dossier / f"{nom}.drawio", nom)
        print(nom)
