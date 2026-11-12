"""Plans 2D du guide générique (modèle de base, sans os), dessinés dans CADCraft par son serveur de contrôle.

Deux dessins séparés, chacun sur sa feuille A3 :
  guide_coupe_generique.dwg      : guide de coupe (pièces 1 à 3), vue A, coupes B-B, C-C et D-D, échelle 2:1 ;
  guide_reduction_generique.dwg  : guide de réduction (pièce 4), coupe A-A, vue de dessus, coupe B-B, échelle 2:1.
Modèle : os cylindrique de largeur nominale l = 16 mm (non dessiné), coin de fermeture θ = 20°, paramètres par défaut
de CT-CORA3D. Cotes réelles grâce à DIMLFAC = 0,5. Aucun tiret dans les textes (préférence de Dorian).

Usage (depuis ce dossier script/) :
  1. ouvrir une fenêtre CADCraft pilotable, dans un terminal :
       CADCRAFT_CONFIG_DIR=/tmp/cadcraft_cfg /Applications/CADCraft.app/Contents/MacOS/CADCraft --control 47651
  2. dans un autre terminal : python3 plans_generiques.py
Les fichiers .dwg, .dxf et .pdf sont écrits dans le dossier parent (documents/plan_guide_generique/).
Modules Python nécessaires : shapely et pymupdf (pip install shapely pymupdf).
"""
import json, math, shutil
from pathlib import Path
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
import fitz
from cc import Client

SORTIE = Path(__file__).resolve().parent.parent                       # documents/plan_guide_generique
LOGO_SRC = SORTIE.parents[1] / "code_source" / "logo_ecam.png"        # logo du projet
shutil.copy(LOGO_SRC, SORTIE / "logo_ecam.png")

c = Client()
def X(cmd, p=None):
    return c("engine.execute", {"command": cmd, "params": p or {}})
def hd(r):
    return r.get("handle") or (r.get("handles") or [None])[0]

# ------------------------------------------------------------------ paramètres du modèle (défauts de CT-CORA3D)
l_os = 16.0; R = l_os / 2
j, e, alpha, g, p, s, js = 0.30, 3.0, 75.0, 10.0, 2.0, 0.60, 0.20
Ob, jb, hp, kd, er, lr, tb, m = 1.6, 0.20, 5.0, 1.2, 4.0, 12.0, 6.0, 8.0   # une broche par fragment
r_conge = 0.8
theta = 20.0
Ri, Ro = R + j, R + j + e                     # 8,3 et 11,3
w_f = s + js                                  # largeur de fente 0,8
L_f = l_os + 2                                # longueur de fente 18
t_t = w_f + 2 * p                             # épaisseur de tour 4,8
L_t = L_f + 2 * p                             # longueur de tour 22
z_top = R + j + e + g                         # 21,3 : haut des tours et des manchons
Om, Oh = Ob + jb + 2 * p, Ob + jb             # manchon 5,8 ; trou 1,8
d = kd * l_os                                 # 19,2
Hz = -(R - 2.0)                               # charnière à 2 mm de la corticale opposée
u_top = z_top - Hz                            # 27,3 : profondeur de lame (haut de tour à la charnière)
th = math.radians(theta)
t2 = (math.cos(th), -math.sin(th))            # direction de PC2 (z, y) depuis la charnière
n2 = (-math.sin(th), -math.cos(th))           # normale de PC2 vers le côté distal
nP = (-n2[0], -n2[1])                         # normale de PC2 vers le côté proximal
yP1 = d                                       # broche proximale
def pt(base, *pairs):
    z, y = base
    for k, v in pairs:
        z += k * v[0]; y += k * v[1]
    return (z, y)
H = (Hz, 0.0)
def base_distale(off):                        # pied de l'axe d'une broche distale sur la coque (z = Ro)
    u = (Ro - Hz - off * n2[0]) / t2[0]
    return u, pt(H, (off, n2), (u, t2))
uD1, BD1 = base_distale(d)
TD1 = pt(BD1, (g, t2))
y_top, y_bot = yP1 + m, round(BD1[1] - m, 1)
xc = Ro * math.sin(math.radians(alpha))       # demi-largeur de la coque vue de face (10,9)
a75 = math.radians(alpha)
K = 2.0                                       # échelle 2:1

# ------------------------------------------------------------------ outils de dessin
def couche(nom): X("layer.current", {"name": nom})
def ligne(pts, closed=False): return hd(X("line", {"points": pts, "closed": closed}))
def pline(vertices, closed=True): return hd(X("pline", {"vertices": vertices, "closed": closed}))
def rect(p1, p2): return pline([p1, [p2[0], p1[1]], p2, [p1[0], p2[1]]])
def cercle(cen, r): return hd(X("circle", {"center": cen, "radius": r}))
def texte(at, t, h=2.5, just="BL", rot=0.0): return hd(X("text", {"at": at, "text": t, "height": h, "justify": just, "rotation": rot}))
def mtexte(at, t, h=2.5, w=100.0): return hd(X("mtext", {"at": at, "text": t, "height": h, "width": w, "attach": 1}))
def hachure(h, sc=0.45): couche("HACHURES"); X("hatch", {"handles": [h], "pattern": "ANSI31", "scale": sc})
def dlin(p1, p2, at, t="<>", rot=None):
    prm = {"p1": p1, "p2": p2, "at": at, "text": t}
    if rot is not None: prm["rotation"] = rot
    return hd(X("dimlinear", prm))
def dali(p1, p2, at, t="<>"): return hd(X("dimaligned", {"p1": p1, "p2": p2, "at": at, "text": t}))
def surcharge(h, t): X("properties.set", {"handles": [h], "textOverride": t})
def horizontal(h): X("dimoverride", {"handles": [h], "DIMTIH": 1, "DIMTOH": 1})    # texte de cote horizontal
def deplacer(h, at): X("dimtedit", {"handles": [h], "at": at})                     # milieu du texte de cote en `at`
def fleche(tip, direction, L=3.5, w=1.3):
    dx, dy = direction; n = math.hypot(dx, dy); dx, dy = dx / n, dy / n
    b = [tip[0] - L * dx, tip[1] - L * dy]
    X("solid", {"points": [tip, [b[0] - w * dy, b[1] + w * dx], [b[0] + w * dy, b[1] - w * dx]]})
def bulge(deg): return math.tan(math.radians(deg) / 4)
def croix(cen, r):
    couche("AXES"); ligne([[cen[0] - r, cen[1]], [cen[0] + r, cen[1]]]); ligne([[cen[0], cen[1] - r], [cen[0], cen[1] + r]])
def arcpt(r, phi): return (r * math.sin(phi), r * math.cos(phi))       # phi depuis +z, positif vers +x
def polys(geom):
    return list(geom.geoms) if hasattr(geom, "geoms") else [geom]
def coupe_trait(a, b, sens, lettre, cote_lettre):
    """Trait fort d'extrémité de plan de coupe de a vers b, flèche dans la direction `sens`, lettre à côté."""
    couche("COUPE"); ligne([a, b])
    tip = [b[0] + 7 * sens[0], b[1] + 7 * sens[1]]
    fleche(tip, sens); ligne([b, [b[0] + 4 * sens[0], b[1] + 4 * sens[1]]])
    couche("TEXTE"); texte([tip[0] + cote_lettre[0], tip[1] + cote_lettre[1]], lettre, 5, "MC")
def ballon(cible, centre, n):
    couche("TEXTE")
    dx, dy = cible[0] - centre[0], cible[1] - centre[1]; L = math.hypot(dx, dy)
    ligne([[centre[0] + 3.5 * dx / L, centre[1] + 3.5 * dy / L], cible]); cercle(centre, 3.5); cercle(cible, 0.45)
    texte(centre, str(n), 3.5, "MC")

# ------------------------------------------------------------------ éléments communs de la feuille
def nouveau_document():
    X("new", {"metric": True})
    X("linetype", {"load": "*"})
    X("units", {"lunits": 2, "luprec": 2, "aunits": 0, "auprec": 0, "insunits": 4})
    X("setvar", {"name": "LTSCALE", "value": 0.35})
    for nom, coul, lw, lt in [("CADRE", 7, 0.70, "Continuous"), ("CARTOUCHE", 7, 0.35, "Continuous"),
                              ("CONTOUR", 7, 0.50, "Continuous"), ("CACHE", 4, 0.25, "HIDDEN"),
                              ("AXES", 1, 0.25, "CENTER"), ("PLANS", 6, 0.25, "PHANTOM"),
                              ("HACHURES", 8, 0.18, "Continuous"), ("COTES", 3, 0.25, "Continuous"),
                              ("TEXTE", 7, 0.25, "Continuous"), ("COUPE", 7, 0.70, "Continuous"), ("LOGO", 7, 0.25, "Continuous")]:
        X("layer.new", {"name": nom, "color": coul, "lineweight": lw, "linetype": lt})
    X("style", {"name": "ISO", "font": "Arial", "widthFactor": 1.0, "current": True})
    commun = {"DIMTXSTY": "ISO", "DIMDSEP": ",", "DIMDEC": 1, "DIMZIN": 8, "DIMADEC": 0, "DIMASZ": 2.5, "DIMTXT": 2.5,
              "DIMEXO": 1.0, "DIMEXE": 1.5, "DIMGAP": 0.8, "DIMTAD": 1, "DIMTIH": 0, "DIMTOH": 0, "DIMTFILL": 1,
              "DIMCLRD": 256, "DIMCLRE": 256, "DIMCLRT": 256}
    X("dimstyle", {"name": "ISO_2_1", **commun, "DIMLFAC": 0.5, "current": True})

def cadre():
    couche("CARTOUCHE"); rect([0, 0], [420, 297])
    couche("CADRE"); rect([20, 10], [410, 287])
    for x0, y0, x1, y1 in [(210, 287, 210, 297), (210, 0, 210, 10), (0, 148.5, 20, 148.5), (410, 148.5, 420, 148.5)]:
        ligne([[x0, y0], [x1, y1]])
    couche("CARTOUCHE")
    for i in range(1, 8):
        x = 20 + i * 390 / 8
        ligne([[x, 287], [x, 290]]); ligne([[x, 7], [x, 10]])
    for i in range(1, 6):
        y = 287 - i * 277 / 6
        ligne([[15, y], [20, y]]); ligne([[410, y], [413, y]])
    couche("TEXTE")
    for i in range(8):
        x = 20 + (i + 0.5) * 390 / 8
        texte([x, 288.6], str(i + 1), 2.5, "MC"); texte([x, 8.4], str(i + 1), 2.5, "MC")
    for i, lettre in enumerate("ABCDEF"):
        y = 287 - (i + 0.5) * 277 / 6
        texte([16.5, y], lettre, 2.5, "MC"); texte([411.8, y], lettre, 2.5, "MC")
    for i in range(5):                                                  # barre de contrôle d'échelle (50 mm)
        if i % 2 == 0: X("solid", {"points": [[25 + 10 * i, 14], [35 + 10 * i, 14], [25 + 10 * i, 16], [35 + 10 * i, 16]]})
    couche("CARTOUCHE"); rect([25, 14], [75, 16])
    couche("TEXTE"); texte([78, 13.6], "cote de contrôle : 50 mm imprimés à l'échelle 1:1 (imprimer à 100 %)", 2.2)

def tableau_parametres(params, titre, x0=300.0, x1=405.0, ytab=282.0, hrow=4.6, htitre=5.8):
    cols = [x0, x0 + 10, x0 + 79, x0 + 94, x1]
    bas = ytab - htitre - hrow * (len(params) + 1)
    couche("CARTOUCHE"); rect([x0, bas], [x1, ytab])
    couche("TEXTE"); texte([x0 + 2, ytab - htitre + 1.6], titre, 2.8)
    y = ytab - htitre
    couche("CARTOUCHE"); ligne([[x0, y], [x1, y]])
    couche("TEXTE")
    for xc_, t in zip(cols, ["sym.", "description", "défaut", "unité"]):
        texte([xc_ + 1.5, y - hrow + 1.3], t, 2.2)
    for i, (sym, desc, val, un) in enumerate(params):
        yl = y - hrow * (i + 1)
        couche("CARTOUCHE"); ligne([[x0, yl], [x1, yl]])
        couche("TEXTE")
        texte([cols[0] + 1.5, yl - hrow + 1.3], sym, 2.2); texte([cols[1] + 1.5, yl - hrow + 1.3], desc, 2.2)
        texte([cols[3] - 1.5, yl - hrow + 1.3], val, 2.2, "BR"); texte([cols[3] + 1.5, yl - hrow + 1.3], un, 2.2)
    couche("CARTOUCHE")
    for xc_ in cols[1:-1]:
        ligne([[xc_, y], [xc_, bas]])
    return bas

def nomenclature(lignes_):
    cx = [230.0, 242.0, 254.0, 324.0, 350.0, 410.0]
    yb, hn = 60.0, 5.0
    couche("CARTOUCHE")
    rect([cx[0], yb], [cx[-1], yb + hn * (len(lignes_) + 1)])
    for i in range(1, len(lignes_) + 1):
        ligne([[cx[0], yb + hn * i], [cx[-1], yb + hn * i]])
    for x in cx[1:-1]:
        ligne([[x, yb], [x, yb + hn * (len(lignes_) + 1)]])
    couche("TEXTE")
    for x, t in zip(cx, ["Rep.", "Qté", "Désignation", "Matière", "Observations"]):
        texte([x + 1.5, yb + 1.5], t, 2.2)
    for i, row in enumerate(lignes_):
        for x, t in zip(cx, row):
            texte([x + 1.5, yb + hn * (len(lignes_) - i) + 1.5], t, 2.2)

def cartouche(titre, designation, numero, echelle="2:1"):
    couche("CARTOUCHE")
    rect([230, 10], [410, 60])
    ligne([[275, 10], [275, 60]])
    for y in (47, 38, 29, 20):
        ligne([[275, y], [410, y]])
    for x, y0, y1 in ((350, 29, 38), (350, 20, 29), (335, 10, 20), (355, 10, 20), (370, 10, 20), (385, 10, 20)):
        ligne([[x, y0], [x, y1]])
    couche("TEXTE")
    lab = lambda at, t: texte(at, t, 1.6)                              # intitulé : ligne de base 3 mm sous le trait
    lab([276.5, 57.0], "Titre"); texte([276.5, 49.5], titre, 4)
    lab([276.5, 44.0], "Désignation"); texte([276.5, 39.6], designation, 2.4)
    lab([276.5, 35.0], "Matière"); texte([276.5, 30.6], "PA12 (frittage laser) ou résine stérilisable", 2.3)
    lab([351.5, 35.0], "Tolérances générales"); texte([351.5, 30.6], "± 0,1 (impression 3D)", 2.3)
    lab([276.5, 26.0], "Dessiné par"); texte([276.5, 21.6], "D. Verstappen, I. Bikass, M.-A. Ahmidouch", 2.3)
    lab([351.5, 26.0], "Date"); texte([351.5, 21.6], "12/11/2026", 2.3)
    lab([276.5, 17.0], "N° de plan"); texte([276.5, 11.8], numero, 3)
    lab([336.5, 17.0], "Échelle"); texte([336.5, 11.8], echelle, 3)
    lab([356.5, 17.0], "Format"); texte([356.5, 11.8], "A3", 3)
    lab([371.5, 17.0], "Rév."); texte([371.5, 11.8], "B", 3)
    lab([386.5, 17.0], "Projection")
    couche("CARTOUCHE")                                                 # symbole de la projection européenne
    pline([[389, 11.2], [389, 15.2], [397, 14.3], [397, 12.1]])
    cercle([403.5, 13.2], 2.0); cercle([403.5, 13.2], 1.1)
    couche("AXES"); ligne([[387.5, 13.2], [407.5, 13.2]])
    couche("TEXTE")
    texte([252.5, 23.6], "Master en ingénierie biomédicale", 1.9, "MC")
    texte([252.5, 20.2], "Projet PMD2 CT-CORA3D", 1.9, "MC")
    texte([252.5, 15.6], "Prototype de recherche,", 1.6, "MC")
    texte([252.5, 12.8], "non validé cliniquement", 1.6, "MC")

def exporter(nom):
    X("zoom", {"mode": "extents"})
    dwg = SORTIE / f"{nom}.dwg"
    X("saveas", {"path": str(dwg), "version": 2018})
    couche("LOGO")
    X("imageattach", {"path": "logo_ecam.png", "at": [233.0, 27.5], "width": 39.0})
    X("saveas", {"path": str(dwg), "version": 2018})
    X("export", {"path": str(SORTIE / f"{nom}.dxf"), "format": "dxf"})
    couleurs = {"CACHE": 4, "AXES": 1, "PLANS": 6, "HACHURES": 8, "COTES": 3}
    for n_ in couleurs:                                                 # PDF en noir : couches en couleur 7 le temps de l'export
        X("layer.set", {"name": n_, "color": 7})
    pdf = SORTIE / f"{nom}.pdf"
    X("layer.set", {"name": "LOGO", "plot": False})                     # sinon le PDF garde le cadre vide de l'image
    X("exportpdf", {"path": str(pdf), "paper": "A3", "landscape": True, "scale": 1, "fit": False,
                    "plotArea": "window", "window": [[0, 0], [420, 297]], "lineweights": True, "center": True})
    X("layer.set", {"name": "LOGO", "plot": True})
    for n_, coul in couleurs.items():
        X("layer.set", {"name": n_, "color": coul})
    X("saveas", {"path": str(dwg), "version": 2018})
    doc = fitz.open(str(pdf)); page = doc[0]; mmpt = 72 / 25.4      # le PDF de CADCraft n'emporte pas les images
    haut = 39.0 * 684 / 900
    page.insert_image(fitz.Rect(233.0 * mmpt, (297 - 27.5 - haut) * mmpt, 272.0 * mmpt, (297 - 27.5) * mmpt),
                      filename=str(SORTIE / "logo_ecam.png"))
    doc.save(str(pdf) + ".tmp", deflate=True, garbage=3); doc.close()   # compressé : environ 20 fois plus léger
    Path(str(pdf) + ".tmp").replace(pdf)
    for bak in SORTIE.glob("*.bak"):
        bak.unlink()
    print(nom, "OK", json.dumps(c("drawing.inspect")["counts"], ensure_ascii=False))


# ================================================================== PLAN 1 : GUIDE DE COUPE
def plan_coupe():
    nouveau_document(); cadre()
    OA, OB, OC, OD = (95.0, 155.0), (150.0, 155.0), (262.0, 204.0), (262.0, 100.0)
    VA = lambda x, y: [OA[0] + K * x, OA[1] + K * y]
    VB = lambda q: [OB[0] + K * q[0], OB[1] + K * q[1]]
    VC = lambda x, z: [OC[0] + K * x, OC[1] + K * z]
    VD = lambda x, z: [OD[0] + K * x, OD[1] + K * z]

    # ---------------- VUE A (face d'appui)
    couche("CONTOUR")
    rect(VA(-xc, y_bot), VA(xc, y_top))
    rect(VA(-L_t / 2, -t_t / 2), VA(L_t / 2, t_t / 2))
    rect(VA(-L_f / 2, -w_f / 2), VA(L_f / 2, w_f / 2))
    yt2a, yt2b = pt(H, (u_top, t2), (t_t / 2, n2))[1], pt(H, (u_top, t2), (t_t / 2, nP))[1]
    rect(VA(-L_t / 2, yt2a), VA(L_t / 2, yt2b))
    yf2a, yf2b = pt(H, (u_top, t2), (w_f / 2, n2))[1], pt(H, (u_top, t2), (w_f / 2, nP))[1]
    rect(VA(-L_f / 2, yf2a), VA(L_f / 2, yf2b))
    u_pied = (Ro - Hz - (t_t / 2) * nP[0]) / t2[0]
    y_pied = pt(H, (u_pied, t2), (t_t / 2, nP))[1]
    ligne([VA(-xc, y_pied), VA(xc, y_pied)])
    ligne([VA(-L_t / 2, yt2b), VA(-xc, y_pied)]); ligne([VA(L_t / 2, yt2b), VA(xc, y_pied)])
    for yP in (yP1,):
        cercle(VA(0, yP), K * Om / 2); cercle(VA(0, yP), K * Oh / 2); croix(VA(0, yP), K * Om / 2 + 3); couche("CONTOUR")
    for B, T in ((BD1, TD1),):
        couche("CONTOUR")
        X("ellipse", {"center": VA(0, T[1]), "major": [K * Om / 2, 0], "ratio": math.cos(th)})
        X("ellipse", {"center": VA(0, T[1]), "major": [K * Oh / 2, 0], "ratio": math.cos(th)})
        ligne([VA(-Om / 2, T[1]), VA(-Om / 2, B[1])]); ligne([VA(Om / 2, T[1]), VA(Om / 2, B[1])])
        X("ellipse", {"center": VA(0, B[1]), "major": [K * Om / 2, 0], "ratio": math.cos(th), "start": 0, "end": 180})
        croix(VA(0, T[1]), K * Om / 2 + 3)
    couche("CACHE")
    for sgn in (-1, 1):
        ligne([VA(sgn * L_f / 2, w_f / 2), VA(sgn * xc, w_f / 2)]); ligne([VA(sgn * L_f / 2, -w_f / 2), VA(sgn * xc, -w_f / 2)])
    couche("AXES")
    ligne([VA(0, y_top + 4), VA(0, y_bot - 4)])
    ligne([VA(-xc - 3, yP1), VA(xc + 3, yP1)])
    ligne([VA(-xc - 3, 0), VA(xc + 3, 0)])
    coupe_trait(VA(0, y_top + 4), VA(0, y_top + 9), (1, 0), "B", (4, 0))      # plan B-B (x = 0), vue vers +x
    coupe_trait(VA(0, y_bot - 8), VA(0, y_bot - 12), (1, 0), "B", (4, 0))
    for sgn in (-1, 1):
        coupe_trait(VA(sgn * (xc + 3), yP1), VA(sgn * (xc + 8), yP1), (0, 1), "C", (0, 4.5))  # plan C-C, vue vers +y
        coupe_trait(VA(sgn * (xc + 3), 0), VA(sgn * (xc + 8), 0), (0, 1), "D", (0, 4.5))      # plan D-D (fente 1)
    couche("TEXTE")
    texte(VA(-xc - 17, y_top + 15), "VUE A", 5); texte(VA(-xc - 17, y_top + 11.5), "face d'appui, échelle 2:1", 3)
    texte(VA(-xc - 17, y_top + 8.5), "os non représenté (l = 16 mm)", 2.5)
    couche("COTES")
    dlin(VA(-L_t / 2, 6), VA(L_t / 2, 6), VA(0, 6), "<>")
    dlin(VA(-L_f / 2, 11), VA(L_f / 2, 11), VA(0, 11), "<> (l + 2)")
    dlin(VA(-xc, y_bot), VA(xc, y_bot), VA(0, y_bot - 4), "<>")
    dlin(VA(0, 0), VA(0, yP1), VA(-xc - 14, yP1 / 2), "<> (d)", 90)
    dlin(VA(0, yP1), VA(-xc, y_top), VA(-xc - 14, (yP1 + y_top) / 2), "<> (m)", 90)
    dlin(VA(-xc, y_bot), VA(-xc, y_top), VA(-xc - 20.5, 0), "<>", 90)

    # ---------------- COUPE B-B (plan x = 0)
    def rect_local(origine, tdir, ndir, u0, u1, v0, v1):
        return Polygon([pt(origine, (u0, tdir), (v0, ndir)), pt(origine, (u1, tdir), (v0, ndir)),
                        pt(origine, (u1, tdir), (v1, ndir)), pt(origine, (u0, tdir), (v1, ndir))])
    matiere = [box(Ri, y_bot, Ro, y_top), box(Ri, -t_t / 2, z_top, t_t / 2), rect_local(H, t2, nP, 12.0, u_top, -t_t / 2, t_t / 2)]
    vides = [box(-20, -w_f / 2, 40, w_f / 2), rect_local(H, t2, nP, 0.0, 45.0, -w_f / 2, w_f / 2)]
    for yP in (yP1,):
        matiere.append(box(Ri, yP - Om / 2, z_top, yP + Om / 2)); vides.append(box(-20, yP - Oh / 2, 40, yP + Oh / 2))
    for off, u_b in ((d, uD1),):
        axe0 = pt(H, (off, n2))
        matiere.append(rect_local(axe0, t2, n2, u_b - 6.0, u_b + g, -Om / 2, Om / 2))
        vides.append(rect_local(axe0, t2, n2, u_b - 9.0, u_b + g + 1.0, -Oh / 2, Oh / 2))
    section = unary_union(matiere).difference(unary_union(vides)).intersection(box(Ri, -80, 60, 80))
    for poly in polys(section):
        couche("CONTOUR"); h = pline([VB(q) for q in list(poly.simplify(1e-6).exterior.coords)[:-1]]); hachure(h)
    couche("PLANS")
    ligne([VB(H), VB(pt(H, (u_top + 6, (1, 0))))]); ligne([VB(H), VB(pt(H, (u_top + 6, t2)))])
    couche("AXES")
    ligne([VB((0, y_top + 4)), VB((0, y_bot - 4))])
    for yP in (yP1,):
        ligne([VB((Ri - 3, yP)), VB((z_top + 3, yP))])
    for off, u_b in ((d, uD1),):
        axe0 = pt(H, (off, n2)); ligne([VB(pt(axe0, (6.0, t2))), VB(pt(axe0, (u_b + g + 3, t2)))])
    couche("CONTOUR"); X("circle", {"center": VB(H), "radius": 0.8})
    couche("TEXTE")
    texte([VB(H)[0] - 2, VB(H)[1] - 6], "charnière", 2.5, "TR")
    texte([VB(pt(H, (u_top + 6, (1, 0))))[0] + 1, VB(H)[1] + 1], "PC1", 2.5)
    q = VB(pt(H, (u_top + 6, t2))); texte([q[0] + 1, q[1] - 3], "PC2", 2.5)
    texte([VB((0, y_top + 4))[0] + 1, VB((0, y_top + 4))[1] - 4], "axe de l'os", 2.2)
    texte([VB((Ri, y_top))[0] - 18, VB((0, y_top))[1] + 30], "COUPE B-B", 5)
    texte([VB((Ri, y_top))[0] - 18, VB((0, y_top))[1] + 23], "échelle 2:1", 3)
    couche("COTES")
    he = dlin(VB((Ri, 8)), VB((Ro, 8)), VB((Ro + 4, 8 + 1.5)), "<> (e)", 0)
    deplacer(he, [VB((Ro + 5.2, 9.5))[0], VB((0, 9.5))[1] + 2.05])
    dlin(VB((Ro, y_top)), VB((z_top, yP1 + Om / 2)), VB(((Ro + z_top) / 2, y_top + 4)), "<> (g)", 0)
    dlin(VB((z_top, -t_t / 2)), VB((z_top, t_t / 2)), VB((z_top + 4, 0)), "<>", 90)
    dlin(VB((z_top, -w_f / 2)), VB((z_top, w_f / 2)), VB((z_top + 13, 0)), "<>", 90)
    dlin(VB((z_top, yP1 - Om / 2)), VB((z_top, yP1 + Om / 2)), VB((z_top + 4, yP1)), "Ø<>", 90)
    dlin(VB((z_top, yP1 - Oh / 2)), VB((z_top, yP1 + Oh / 2)), VB((z_top + 13, yP1)), "Ø<>", 90)
    Q = pt(H, (7.0, t2))
    dali(VB(Q), VB(pt(Q, (d, n2))), VB(pt(Q, (d / 2, n2), (-4, t2))), "<> (d)")
    hl = dlin(VB((Hz, 0)), VB((z_top, 0)), VB(((Hz + z_top) / 2, 12)), "<> (profondeur de lame)", 0)
    deplacer(hl, [VB((Hz, 12))[0] + 6.0, VB((0, 12))[1] + 2.05])
    ha = hd(X("dimangular", {"vertex": VB(H), "p1": VB(pt(H, (24, (1, 0)))), "p2": VB(pt(H, (24, t2))),
                             "at": VB(pt(H, (13.5, (math.cos(th / 2), -math.sin(th / 2)))))}))
    surcharge(ha, "<> (θ)"); horizontal(ha)
    deplacer(ha, [VB(H)[0] + 19.2, VB(H)[1] - 2.3])                     # entre l'axe de l'os et l'arc de cote

    # ---------------- COUPE C-C (plan y = d, manchon P1)
    x_h, x_m = Oh / 2, Om / 2
    phi_h_in, phi_m_out = math.asin(x_h / Ri), math.asin(x_m / Ro)
    for sgn in (-1, 1):
        v = [{"p": VC(sgn * x_h, math.sqrt(Ri ** 2 - x_h ** 2))}, {"p": VC(sgn * x_h, z_top)}, {"p": VC(sgn * x_m, z_top)}]
        zo = math.sqrt(Ro ** 2 - x_m ** 2)
        v.append({"p": VC(sgn * x_m, zo), "bulge": -sgn * bulge(math.degrees(a75 - phi_m_out))})
        v.append({"p": VC(*arcpt(Ro, sgn * a75))})
        v.append({"p": VC(*arcpt(Ri, sgn * a75)), "bulge": sgn * bulge(math.degrees(a75 - phi_h_in))})
        couche("CONTOUR"); h = pline(v); hachure(h)
    couche("AXES")
    ligne([VC(0, -3), VC(0, z_top + 4)]); ligne([VC(-4, 0), VC(4, 0)])
    ligne([VC(0, 0), VC(*arcpt(Ro + 5, -a75))])
    couche("TEXTE")
    texte(VC(-Ro - 6, z_top + 13.3), "COUPE C-C", 5); texte(VC(-Ro - 6, z_top + 10.8), "échelle 2:1", 3)
    couche("COTES")
    dlin(VC(-x_m, z_top), VC(x_m, z_top), VC(0, z_top + 3), "Ø<>", 0)
    dlin(VC(-x_h, z_top), VC(x_h, z_top), VC(0, z_top + 7.5), "Ø<>", 0)
    dlin(VC(x_m, z_top), VC(0, Ro), VC(x_m + 5, (Ro + z_top) / 2), "<> (g)", 90)
    f50 = math.radians(50)                                              # du côté libre (à droite de l'axe)
    hri = hd(X("dimradius", {"center": VC(0, 0), "point": VC(*arcpt(Ri, f50))}))
    deplacer(hri, [OC[0] + 9.6 * math.sin(f50) - 2.05 * math.cos(f50), OC[1] + 9.6 * math.cos(f50) + 2.05 * math.sin(f50)])
    hg = hd(X("dimangular", {"vertex": VC(0, 0), "p1": VC(0, 5), "p2": VC(*arcpt(5, -a75)),
                             "at": VC(*arcpt(5.2, -math.radians(22)))}))
    surcharge(hg, "<> (α)")

    # ---------------- COUPE D-D (plan de la fente 1 : les ponts sécables), vue vers le côté proximal
    zb = Ro * math.cos(a75)                                             # hauteur des bords de la coque (2,9)
    couche("CONTOUR")
    pline([{"p": VD(*arcpt(Ri, -a75))}, {"p": VD(*arcpt(Ro, -a75))}, {"p": VD(-L_t / 2, zb)}, {"p": VD(-L_t / 2, z_top)},
           {"p": VD(L_t / 2, z_top)}, {"p": VD(L_t / 2, zb)}, {"p": VD(*arcpt(Ro, a75))},
           {"p": VD(*arcpt(Ri, a75)), "bulge": bulge(2 * alpha)}])
    for sgn in (-1, 1):                                                 # ponts sécables, dans le plan de coupe
        couche("CONTOUR"); h = rect(VD(sgn * L_f / 2, z_top - hp), VD(sgn * L_t / 2, z_top)); hachure(h, 0.35)
    couche("AXES")
    ligne([VD(0, -3), VD(0, z_top + 3)]); ligne([VD(-4, 0), VD(4, 0)])
    couche("TEXTE")
    texte(VD(-L_t / 2, z_top + 21), "COUPE D-D", 5)
    texte(VD(-L_t / 2, z_top + 18), "plan de la fente 1 (PC1), échelle 2:1", 2.5)
    couche("COTES")
    dlin(VD(-L_t / 2, z_top), VD(-L_f / 2, z_top), VD(-L_t / 2 - 3, z_top + 3), "<> (p)", 0)
    dlin(VD(L_t / 2, z_top - hp), VD(L_t / 2, z_top), VD(L_t / 2 + 4, z_top - hp / 2), "<> (hp)", 90)
    dlin(VD(-L_f / 2, z_top), VD(L_f / 2, z_top), VD(0, z_top + 7), "<> (l + 2)", 0)
    dlin(VD(-L_t / 2, z_top), VD(L_t / 2, z_top), VD(0, z_top + 11.5), "<>", 0)
    dlin(VD(0, 0), VD(-L_t / 2, z_top), VD(-L_t / 2 - 5, z_top / 2), "<>", 90)

    # ---------------- repères, tableau, notes, nomenclature, cartouche
    ballon(VA(6, yP1 + 4), [128.0, 226.0], 1)
    ballon(VA(6, y_bot + 6), [128.0, 76.0], 2)
    ballon(VA(L_t / 2 - 1, 0.0), [124.0, 172.0], 3)
    ballon(VD(L_t / 2 - 1, z_top - 1), [OD[0] + 28.0, OD[1] + 14.0], 3)
    PARAMS = [("j", "jeu entre l'os et la coque", "0,30", "mm"), ("e", "épaisseur de la coque", "3,0", "mm"),
              ("α", "demi-ouverture de la coque", "75", "°"), ("δ", "dépouille de la coque", "5", "°"),
              ("m", "coque au-delà des broches extrêmes", "8,0", "mm"), ("r", "rayon des congés", "0,80", "mm"),
              ("g", "hauteur de guidage au-dessus de la coque", "10,0", "mm"), ("p", "paroi des tours et des manchons", "2,0", "mm"),
              ("s", "épaisseur de la lame de scie", "0,60", "mm"), ("js", "jeu de la fente", "0,20", "mm"),
              ("Øb", "diamètre des broches", "1,6", "mm"), ("jb", "jeu du manchon", "0,20", "mm"),
              ("hp", "hauteur des ponts sécables", "5,0", "mm"), ("c", "chanfrein d'entrée (fentes, manchons)", "0,50", "mm"),
              ("kd", "distance à la coupe / largeur de l'os", "1,2", "×"),
              ("jv", "distance minimale aux os voisins", "1,00", "mm"), ("mc", "écart supplémentaire au cartilage", "1,0", "mm")]
    bas = tableau_parametres(PARAMS, "Paramètres du guide de coupe (valeurs par défaut)")
    NOTES = ("Notes\\P"
             "1. Modèle générique du guide de coupe (pièces 1 à 3), dessiné pour un os cylindrique de largeur l = 16 mm "
             "(non représenté) et un coin de fermeture θ = 20°. Pour chaque chien, les faces au contact de l'os sont "
             "moulées sur l'os segmenté et les cotes qui en dépendent sont recalculées.\\P"
             "2. Cotes en mm : dimension réelle suivie du paramètre entre parenthèses. Rayon intérieur de la coque : "
             "R os + j ; haut des tours et des manchons à R os + j + e + g de l'axe de l'os.\\P"
             "3. Fente : largeur s + js, longueur l + 2. Tour : épaisseur s + js + 2p, hauteur g au-dessus de la coque.\\P"
             "4. Manchon : diamètre extérieur Øb + jb + 2p, trou Øb + jb. Une broche par fragment, à d = kd × l de la coupe ; la "
             "coque dépasse de m chaque broche. Broche distale parallèle à PC2.\\P"
             "5. Moitiés 1 et 2 séparées par la fente 1 (PC1) et reliées par deux ponts sécables p × hp (pièce 3), "
             "coupés à la pince après la coupe de l'os (coupe D-D).\\P"
             "6. Tolérances générales ± 0,1. Congés r, chanfreins c à l'entrée des fentes et des manchons, dépouille δ.\\P"
             "7. Repères communs aux deux plans : la pièce 4 (guide de réduction) figure sur le plan CTC3D-GEN-02.")
    couche("TEXTE"); mtexte([300.0, bas - 4], NOTES, 2.1, 105.0)
    nomenclature([("5", "2", "Broche de Kirschner Ø1,6", "Inox", "du commerce (non fournie)"),
                  ("3", "2", "Pont sécable", "PA12", "venu de matière, à couper"),
                  ("2", "1", "Guide de coupe : moitié distale", "PA12", "guide_coupe.stl"),
                  ("1", "1", "Guide de coupe : moitié proximale", "PA12", "guide_coupe.stl (pièces 1 à 3)")])
    cartouche("GUIDE DE COUPE GÉNÉRIQUE", "Guide de coupe (pièces 1 à 3), sans os, paramètres par défaut", "CTC3D-GEN-01")
    exporter("guide_coupe_generique")


# ================================================================== PLAN 2 : GUIDE DE RÉDUCTION
def plan_reduction():
    nouveau_document(); cadre()
    z0 = R                                                              # extrémité des manchons (contact avec l'os)
    yR = [-d, d]                                                        # 2 broches parallèles après correction
    Rs = Om / 2
    L_b = yR[-1] + Rs                                                   # demi-longueur de la barre (22,1)
    OA2, OT, OBB = (125.0, 172.0), (125.0, 117.0), (262.0, 172.0)
    FA = lambda y, z: [OA2[0] + K * y, OA2[1] + K * (z - z0)]          # coupe A-A : y vers la droite, z vers le haut
    FT = lambda y, x: [OT[0] + K * y, OT[1] + K * x]                   # vue de dessus : y vers la droite, x vers le haut
    FB = lambda x, z: [OBB[0] + K * x, OBB[1] + K * (z - z0)]          # coupe B-B : x vers la droite, z vers le haut

    # ---------------- COUPE A-A (plan x = 0, par les axes des 2 broches)
    corps = unary_union([box(-L_b, z0 + er, L_b, z0 + er + tb)] + [box(y - Rs, z0, y + Rs, z0 + lr) for y in yR])
    corps = corps.buffer(r_conge, join_style=1).buffer(-r_conge, join_style=1)      # congés r aux raccords barre / manchons
    corps = corps.difference(unary_union([box(y - Oh / 2, z0 - 1, y + Oh / 2, z0 + lr + 1) for y in yR]))
    for poly in polys(corps):
        couche("CONTOUR"); h = pline([FA(*q) for q in list(poly.simplify(0.01).exterior.coords)[:-1]]); hachure(h)
    couche("AXES")
    for y in yR:
        ligne([FA(y, z0 - 3), FA(y, z0 + lr + 3)])
    couche("TEXTE")
    texte([FA(-L_b, 0)[0], FA(0, z0 + lr)[1] + 29], "COUPE A-A", 5)
    texte([FA(-L_b, 0)[0], FA(0, z0 + lr)[1] + 23], "par les axes des 2 broches, après correction, échelle 2:1", 3)
    couche("COTES")
    dlin(FA(-L_b, z0), FA(-L_b, z0 + lr), FA(-L_b - 5, z0 + lr / 2), "<> (lr)", 90)
    dlin(FA(yR[0], z0 + lr), FA(yR[1], z0 + lr), FA(0, z0 + lr + 4), "<> (2d)", 0)

    # ---------------- VUE DE DESSUS (le long des broches)
    couche("CONTOUR")
    pline([{"p": FT(yR[0], -Rs)}, {"p": FT(yR[-1], -Rs), "bulge": 1.0}, {"p": FT(yR[-1], Rs)},
           {"p": FT(yR[0], Rs), "bulge": 1.0}])
    for y in yR:
        cercle(FT(y, 0), K * Rs); cercle(FT(y, 0), K * Oh / 2); croix(FT(y, 0), K * Rs + 3); couche("CONTOUR")
    couche("AXES"); ligne([FT(-L_b - 3, 0), FT(L_b + 3, 0)])
    coupe_trait(FT(-L_b - 3, 0), FT(-L_b - 8, 0), (0, 1), "A", (0, 4.5))  # plan A-A, vue vers le haut de la feuille
    coupe_trait(FT(L_b + 3, 0), FT(L_b + 8, 0), (0, 1), "A", (0, 4.5))
    couche("AXES"); ligne([FT(0, -Rs - 4), FT(0, Rs + 4)])
    coupe_trait(FT(0, Rs + 4), FT(0, Rs + 9), (1, 0), "B", (4, 0))        # plan B-B (milieu de la barre), vue vers +y
    coupe_trait(FT(0, -Rs - 4), FT(0, -Rs - 9), (1, 0), "B", (4, 0))
    couche("TEXTE")
    texte([FT(-L_b, 0)[0], FT(0, Rs)[1] + 30], "VUE DE DESSUS", 5)
    texte([FT(-L_b, 0)[0], FT(0, Rs)[1] + 24], "le long des broches, échelle 2:1", 3)
    couche("COTES")
    dlin(FT(-L_b, -Rs), FT(L_b, -Rs), FT(0, -Rs - 16), "<>", 0)
    hm = hd(X("dimdiameter", {"center": FT(yR[0], 0), "point": FT(yR[0] + Rs * math.cos(math.radians(60)), Rs * math.sin(math.radians(60)))}))
    hh = hd(X("dimdiameter", {"center": FT(yR[1], 0), "point": FT(yR[1] + Oh / 2 * math.cos(math.radians(55)), Oh / 2 * math.sin(math.radians(55)))}))
    horizontal(hm); horizontal(hh)

    # ---------------- COUPE B-B (milieu de la barre, y = 0), vue vers le manchon P1
    couche("CONTOUR"); h = rect(FB(-Rs, z0 + er), FB(Rs, z0 + er + tb)); hachure(h)
    z_bout = math.sqrt(R ** 2 - Rs ** 2)                               # extrémité du manchon moulée sur l'os
    couche("CONTOUR")
    ligne([FB(-Rs, z_bout), FB(-Rs, z0 + er)]); ligne([FB(Rs, z_bout), FB(Rs, z0 + er)])
    ligne([FB(-Rs, z0 + er + tb), FB(-Rs, z0 + lr)]); ligne([FB(Rs, z0 + er + tb), FB(Rs, z0 + lr)])
    ligne([FB(-Rs, z0 + lr), FB(Rs, z0 + lr)])
    phi_b = math.asin(Rs / R)
    pline([{"p": FB(-Rs, z_bout), "bulge": -bulge(2 * math.degrees(phi_b))}, {"p": FB(Rs, z_bout)}], closed=False)
    couche("CACHE")
    for sgn in (-1, 1):
        ligne([FB(sgn * Oh / 2, math.sqrt(R ** 2 - (Oh / 2) ** 2)), FB(sgn * Oh / 2, z0 + lr)])
    couche("AXES"); ligne([FB(0, z0 - 2), FB(0, z0 + lr + 3)]); croix(FB(0, 0), 3.0)
    couche("TEXTE"); texte([FB(0, 0)[0] + 4.5, FB(0, 0)[1]], "axe de l'os", 2.2, "ML")
    couche("TEXTE")
    texte([FB(-Rs, 0)[0] - 8, FB(0, z0 + lr)[1] + 29], "COUPE B-B", 5)
    texte([FB(-Rs, 0)[0] - 8, FB(0, z0 + lr)[1] + 23], "échelle 2:1", 3)
    couche("COTES")
    dlin(FB(-Rs, z0 + lr), FB(Rs, z0 + lr), FB(0, z0 + lr + 4), "<>", 0)
    dlin(FB(Rs, z0 + er), FB(Rs, z0 + er + tb), FB(Rs + 5, z0 + er + tb / 2), "<> (tb)", 90)
    dlin(FB(0, z0), FB(-Rs, z0 + er), FB(-Rs - 5, z0 + er / 2), "<> (er)", 90)
    dlin(FB(0, z0), FB(-Rs, z0 + lr), FB(-Rs - 12, z0 + lr / 2), "<> (lr)", 90)
    hr = hd(X("dimradius", {"center": FB(0, 0), "point": FB(*arcpt(R, -math.radians(14)))}))
    surcharge(hr, "<> (R os)"); horizontal(hr)
    deplacer(hr, [FB(0, 0)[0] + 6.5, FB(0, 0)[1] + 5.0])

    # ---------------- repères, tableau, notes, nomenclature, cartouche
    ballon(FA(d / 2 - 4, z0 + er), [OA2[0] + 25.0, OA2[1] - 13.0], 4)
    PARAMS = [("Øb", "diamètre des broches", "1,6", "mm"), ("jb", "jeu du manchon", "0,20", "mm"),
              ("p", "paroi des manchons", "2,0", "mm"), ("j", "jeu entre l'os et les manchons", "0,30", "mm"),
              ("r", "rayon des congés", "0,80", "mm"), ("δ", "dépouille", "5", "°"),
              ("kd", "distance à la coupe / largeur de l'os", "1,2", "×"),
              ("jv", "distance minimale aux os voisins", "1,00", "mm"), ("er", "distance de la barre à l'os", "4,0", "mm"),
              ("lr", "longueur des manchons", "12,0", "mm"), ("tb", "épaisseur de la barre", "6,0", "mm")]
    bas = tableau_parametres(PARAMS, "Paramètres du guide de réduction (valeurs par défaut)")
    NOTES = ("Notes\\P"
             "1. Modèle générique du guide de réduction (pièce 4), dessiné pour les 2 broches parallèles après la "
             "correction : une broche par fragment, à d = kd × l de la coupe (os de largeur l = 16 mm, non "
             "représenté ; d = 19,2 mm).\\P"
             "2. Cotes en mm : dimension réelle suivie du paramètre entre parenthèses.\\P"
             "3. Manchons parallèles de longueur lr, trou Øb + jb, paroi p. Le guide s'enfile sur les broches jusqu'au "
             "contact des manchons avec l'os corrigé ; leurs extrémités sont moulées sur l'os, au jeu j près.\\P"
             "4. Barre d'épaisseur tb, à er de l'os : contour des broches vu le long des broches, élargi du rayon des "
             "manchons. Elle fixe la position des fragments (angle, torsion et translation) pendant la pose de la plaque.\\P"
             "5. Tolérances générales ± 0,1 (impression 3D). Congés r aux raccords de la barre et des manchons.\\P"
             "6. Repères communs aux deux plans : les pièces 1 à 3 (guide de coupe) figurent sur le plan CTC3D-GEN-01.")
    couche("TEXTE"); mtexte([300.0, bas - 4], NOTES, 2.1, 105.0)
    nomenclature([("5", "2", "Broche de Kirschner Ø1,6", "Inox", "du commerce (non fournie)"),
                  ("4", "1", "Guide de réduction", "PA12", "guide_reduction.stl")])
    cartouche("GUIDE DE RÉDUCTION GÉNÉRIQUE", "Guide de réduction (pièce 4), sans os, paramètres par défaut", "CTC3D-GEN-02")
    exporter("guide_reduction_generique")


if __name__ == "__main__":
    plan_coupe()
    plan_reduction()
