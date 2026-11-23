"""
schemas.py : schémas draw.io du document « Segmentation osseuse et maillage 3D ».

Usage : python3 schemas.py      (écrit les .drawio dans ce dossier ; ../construire.sh les exporte en PDF dans ../images/)
Pour retoucher un schéma, ouvrir le .drawio dans draw.io. Attention : relancer ce script écrase les retouches
(copier le fichier sous un autre nom avant de le retoucher, ou modifier ce script).
Même style que documents/dossier_complet/schemas/schemas_dossier.py.
"""
from pathlib import Path
from xml.sax.saxutils import escape

ICI = Path(__file__).resolve().parent
POLICE = "Helvetica"
COULEURS = {
    "scanner": ("#eef2f6", "#5b6b7a"),
    "segmentation": ("#e6f0fa", "#1f5f8b"),
    "maillage": ("#e8f5e4", "#3a7d2c"),
    "controle": ("#fdf0e2", "#b8611a"),
    "fichier": ("#fffdf5", "#8a7a55"),
    "neutre": ("#ffffff", "#666666"),
}
FORMES = {
    "boite": "rounded=1;arcSize=10;",
    "fichier": "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=8;",
    "document": "shape=document;boundedLbl=1;size=0.15;",
}


def _q(t):
    return escape(t, {'"': "&quot;"})


class Schema:
    def __init__(self):
        self.cellules, self.n = [], 1

    def boite(self, x, y, l, h, texte, couleur="neutre", forme="boite", taille=14, pointilles=False):
        fond, bord = COULEURS[couleur]
        self.n += 1
        style = (FORMES[forme] + f"whiteSpace=wrap;html=1;fillColor={fond};strokeColor={bord};strokeWidth=1.5;"
                 f"fontFamily={POLICE};fontSize={taille};align=center;verticalAlign=middle;spacing=6;"
                 + ("dashed=1;" if pointilles else ""))
        self.cellules.append(f'<mxCell id="c{self.n}" value="{_q(texte)}" style="{style}" vertex="1" parent="1">'
                             f'<mxGeometry x="{x}" y="{y}" width="{l}" height="{h}" as="geometry"/></mxCell>')
        return f"c{self.n}"

    def texte(self, x, y, l, h, texte, taille=13, couleur="#333333"):
        self.n += 1
        style = (f"text;html=1;whiteSpace=wrap;fontFamily={POLICE};fontSize={taille};align=center;"
                 f"verticalAlign=middle;fontColor={couleur};")
        self.cellules.append(f'<mxCell id="c{self.n}" value="{_q(texte)}" style="{style}" vertex="1" parent="1">'
                             f'<mxGeometry x="{x}" y="{y}" width="{l}" height="{h}" as="geometry"/></mxCell>')
        return f"c{self.n}"

    def fleche(self, a, b, texte="", sortie=None, entree=None, pointilles=False):
        self.n += 1
        style = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor=#444444;"
                 f"strokeWidth=1.8;fontFamily={POLICE};fontSize=12;labelBackgroundColor=#ffffff;"
                 + ("dashed=1;" if pointilles else ""))
        if sortie:
            style += f"exitX={sortie[0]};exitY={sortie[1]};exitDx=0;exitDy=0;"
        if entree:
            style += f"entryX={entree[0]};entryY={entree[1]};entryDx=0;entryDy=0;"
        self.cellules.append(f'<mxCell id="c{self.n}" value="{_q(texte)}" style="{style}" edge="1" parent="1" '
                             f'source="{a}" target="{b}"><mxGeometry relative="1" as="geometry"/></mxCell>')

    def ecrire(self, nom):
        xml = ('<mxfile host="CT-CORA3D"><diagram id="d" name="' + escape(nom) + '"><mxGraphModel grid="0" page="0">'
               '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cellules) +
               '</root></mxGraphModel></diagram></mxfile>')
        (ICI / f"{nom}.drawio").write_text(xml, encoding="utf-8")
        print("  ", nom + ".drawio")


def T(titre, detail="", taille_detail=12):
    """Texte d'une boîte : titre en gras, détail plus petit en dessous."""
    return f"<b>{titre}</b>" + (f"<br><font style='font-size:{taille_detail}px'>{detail}</font>" if detail else "")


def F(texte):
    """Nom de fichier en police à chasse fixe."""
    return f"<font face='Courier New' style='font-size:11px'>{texte}</font>"


def serpent(s, etapes, L=250, H=96, dx=290, dy=136, x0=20, y0=20, cols=3):
    """Boîtes en serpentin (ligne 1 de gauche à droite, ligne 2 de droite à gauche...), reliées par des flèches."""
    ids = []
    for i, (t, d, c) in enumerate(etapes):
        r, k = divmod(i, cols)
        col = k if r % 2 == 0 else cols - 1 - k
        ids.append(s.boite(x0 + col * dx, y0 + r * dy, L, H, T(t, d), c, taille=15))
    for i in range(len(ids) - 1):
        r1, r2 = i // cols, (i + 1) // cols
        if r1 == r2:
            vers_droite = r1 % 2 == 0
            s.fleche(ids[i], ids[i + 1], sortie=(1, 0.5) if vers_droite else (0, 0.5),
                     entree=(0, 0.5) if vers_droite else (1, 0.5))
        else:
            s.fleche(ids[i], ids[i + 1], sortie=(0.5, 1), entree=(0.5, 0))
    return ids


# --------------------------------------------------------------------------------------------- les schémas
def chaine():
    """Les cinq étapes du module, ce que chacune reçoit et ce qu'elle produit."""
    s = Schema()
    L, H, dx, y = 170, 104, 205, 20
    entree = s.boite(20, y + 6, 150, 92, T("Dossier DICOM", "une coupe par fichier,<br>une ou plusieurs séries"),
                     "scanner", "fichier", taille=14)
    etapes = [("1. Lecture", "trier les coupes,<br>valeurs en HU", "scanner", "etape1_lecture_dicom.py"),
              ("2. Segmentation", "un numéro<br>par os", "segmentation", "etape2_segmentation.py"),
              ("3. Identification", "un nom par os,<br>corrections", "segmentation", "etape3_identification.py"),
              ("4. Maillage", "une surface<br>fermée par os", "maillage", "etape4_maillage.py"),
              ("5. Contrôle", "sensibilité au seuil,<br>rapports", "controle", "etape5_controle.py")]
    produits = [("Volume", "HU (int16) + matrice A<br>voxel vers mm (LPS)"),
                ("Étiquettes", "tableau 3D :<br>0 = pas d'os, 1, 2, 3..."),
                ("Noms et repères", "fémur, tibia, fibula...<br>tête fémorale"),
                ("Fichiers", F("femur.stl") + "<br>" + F("segmentation.seg.nrrd")),
                ("Rapports", F("rapport.md") + ", " + F(".json") + "<br>aperçus PNG")]
    ids, prev = [], entree
    for k, ((titre, detail, coul, fichier), (pt, pd)) in enumerate(zip(etapes, produits)):
        x = 210 + k * dx
        b = s.boite(x, y, L, H, T(titre, detail) + "<br>" + F(fichier), coul, taille=15)
        s.fleche(prev, b, sortie=(1, 0.5), entree=(0, 0.5))
        p = s.boite(x, y + H + 50, L, 78, T(pt, pd, 11), "fichier", "document", taille=13)
        s.fleche(b, p, sortie=(0.5, 1), entree=(0.5, 0), pointilles=True)
        ids.append(b)
        prev = b
    s.texte(210, y + H + 140, 5 * dx - 35, 30, "Étapes 6 et 7 de CT-CORA3D (repères, guides de coupe) : elles lisent les "
            "STL produits ici", taille=12, couleur="#666666")
    s.ecrire("chaine")


def segmentation():
    """Algorithme de l'étape 2 : deux seuils, croissance de région compétitive, recollage."""
    s = Schema()
    L, H = 300, 74
    xc = 200
    a = s.boite(xc, 20, L, H, T("Volume en HU", "zone recadrée autour des os denses (≥ 500 HU, marge 6 mm)"), "scanner")
    b = s.boite(xc, 130, L, H, T("Lissage gaussien", "σ = 0,35 mm : le bruit est divisé par deux"), "segmentation")
    m = s.boite(20, 250, 300, 92, T("Masque osseux", "seuil BAS : I ≥ 226 HU<br>l'os entier, mais les os se touchent"),
                "segmentation")
    g = s.boite(380, 250, 300, 92, T("Graines", "seuil HAUT qui monte de 500 à 1500 HU<br>un noyau dense par os "
                                              "(arbre des seuils)"), "segmentation")
    c = s.boite(xc, 390, L, 92, T("Croissance de région compétitive", "ligne de partage des eaux sur le relief "
                                                                      "3000 - I<br>les os se rencontrent dans l'interligne"),
                "segmentation")
    r = s.boite(xc, 520, L, H, T("Recollage", "deux morceaux d'un même os : c* ≥ 3"), "segmentation")
    n = s.boite(xc, 630, L, H, T("Nettoyage", "segments < 50 mm³ rattachés au voisin<br>numéros par volume décroissant"),
                "segmentation")
    e = s.boite(xc + 40, 740, L - 80, 70, T("Étiquettes", "0 = pas d'os ; 1, 2, 3... = un os"), "fichier", "document")
    s.fleche(a, b)
    s.fleche(b, m, sortie=(0.25, 1), entree=(0.5, 0))
    s.fleche(b, g, sortie=(0.75, 1), entree=(0.5, 0))
    s.fleche(m, c, sortie=(0.5, 1), entree=(0.25, 0), texte="où grandir")
    s.fleche(g, c, sortie=(0.5, 1), entree=(0.75, 0), texte="d'où partir")
    s.fleche(c, r)
    s.fleche(r, n)
    s.fleche(n, e)
    s.ecrire("segmentation")


def maillage():
    """Étape 4 : du masque d'un os au fichier STL."""
    s = Schema()
    etapes = [("Masque de l'os", "étiquettes de l'os (ou du groupe)", "segmentation"),
              ("Remplissage", "fermeture de 1 mm, couvercles<br>aux bords du champ, trous", "maillage"),
              ("Léger flou", "σ = 0,3 mm : plus d'escaliers", "maillage"),
              ("Marching cubes", "Flying Edges de VTK<br>isovaleur 0,5", "maillage"),
              ("Morceaux", "on garde ceux qui font<br>au moins 2 % du plus grand", "maillage"),
              ("Lissage sans rétrécir", "windowed sinc<br>20 itérations", "maillage"),
              ("Décimation", "si plus de 150 000 triangles<br>(seulement si reste étanche)", "maillage"),
              ("Normales", "vers l'extérieur<br>(volume signé > 0)", "maillage"),
              ("Affinage à demi-hauteur", "chaque sommet glisse<br>vers le vrai bord", "maillage"),
              ("Contrôle", "étanche, orientation,<br>nombre d'Euler, volume", "controle"),
              ("STL binaire", "un fichier par os,<br>coordonnées du scanner (LPS, mm)", "fichier")]
    serpent(s, etapes, L=250, H=96, dx=290, dy=136, cols=3)
    s.ecrire("maillage")


if __name__ == "__main__":
    chaine()
    segmentation()
    maillage()
