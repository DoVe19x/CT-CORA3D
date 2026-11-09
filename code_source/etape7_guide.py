"""
etape7_guide.py — guides imprimables à partir de la prescription CORA (format v2.2), sur l'os planifié (os segmenté sur
CT ou os fictif) : un guide de coupe et un guide de réduction.

Rôle    : 1. GUIDE DE COUPE patient-spécifique : coque moulée sur l'os, fente(s) de scie dans le(s) plan(s) prescrit(s),
             4 manchons de broches (2 par fragment). Il s'imprime d'une pièce, mais il est fait de deux moitiés
             (proximale, distale) reliées par 2 ponts sécables, aux extrémités de la 1re fente : après la coupe, on coupe
             les ponts et chaque moitié glisse le long de SES deux broches, parallèles entre elles (les broches distales ne
             sont pas parallèles aux proximales avant la correction). En fermeture, la 2e fente est une fente fermée de la
             moitié distale. Chaque fente est parallèle à la charnière : la profondeur de lame, du haut de la tour à la
             charnière (ou à la corticale opposée en coupe complète), est la même sur toute la fente ; elle est donnée
             dans le mode opératoire et sur le plan coté.
          2. GUIDE DE RÉDUCTION séparé : barre à 4 manchons parallèles. Après la correction, les 4 broches sont
             parallèles ; on enfile la barre sur les broches jusqu'au contact de l'os : elle tient les fragments dans la
             position planifiée (6 degrés de liberté) pendant la fixation.
          3. Finitions : arêtes des tours arrondies, entrées chanfreinées (fentes, manchons).
          (Version simplifiée du 06/11/2026 : la butée graduée, le verrou de réduction intégré « 2 en 1 », la pièce du
          coin séparée et les gravures de la v3 ont été retirés.)
Entrées : prescription.json (onglet CORA, étape 12) + maillage de l'os planifié (repère de l'os, .bin ou .stl).
Sorties : guide_coupe.stl (à imprimer d'une pièce, + repère du scanner), guide_reduction.stl, os_corrige.stl, guide.json
          (contrôles, mode opératoire), guide.png, plans 2D ; fichiers .bin (moitiés, ponts, guide de réduction, os
          corrigé) pour l'affichage dans l'application.

Méthode (modélisation implicite) :
  - distance signée d à l'os sur une grille de pas 0,3 mm : signe exact (voxelisation par rayons, VTK), valeur exacte
    près de l'os (distance au triangle le plus proche), approchée ailleurs (transformée de Maurer, SimpleITK) ;
  - guide = union lisse (congés de 0,8 mm) de primitives : coque J ≤ d ≤ J + e limitée à la zone d'appui, tours des
    fentes, manchons des broches ;
  - contraintes dures : d ≥ J partout (aucune interpénétration) et aucune contre-dépouille : pas de matière « sous »
    l'os vu depuis la direction de retrait (carte de hauteur de l'os + cône de dépouille de 5°). La moitié distale
    respecte deux directions : la pose du guide entier et son propre retrait le long des broches distales ;
  - isosurface (Flying Edges, VTK) -> solide exact (manifold3d) ; fentes, trous et séparation des moitiés par booléens
    exacts (plans et cylindres exacts, indépendants de la grille) ;
  - os voisins (fibula, rotule, fabelles) : jeu dur de GUIDE_JEU_VOISIN_MM et pas de contre-dépouille contre eux non plus
    (ils entrent dans les cartes de hauteur) ; l'espace entre l'os et un os voisin reste vide ; cartilage articulaire :
    la coque d'appui s'en tient à l'écart ;
  - guide de réduction : construit sur l'os corrigé (correction réelle : trait de scie compensé en fermeture), autour
    des broches dans leur position après la correction ;
  - contrôles indépendants de la construction : distance exacte guide-os, volume d'interpénétration, lancer de rayons
    dans la direction de retrait de chaque moitié, balayage exact contre l'autre moitié, étanchéité du STL relu, appui de
    chaque moitié, lame contre broches, guides et broches contre les os voisins et le cartilage.
"""
import argparse
import json
import os
import time
from pathlib import Path

import manifold3d as m3d
import numpy as np
import SimpleITK as sitk
import vtk_leger as vtk                  # seulement les classes utilisées (voir vtk_leger.py)
from scipy import ndimage
from scipy.spatial import cKDTree
from vtkmodules.util import numpy_support as ns

import parametres as P

# --------------------------------------------------------------------------- guide générique (paramètres)
# Le guide est un modèle PARAMÉTRIQUE : ses dimensions de conception sont des paramètres (valeurs par défaut dans
# parametres.py), que l'interface peut changer pour un cas (prescription.json > "parametres_guide"). Les dimensions
# qui dépendent de l'os (longueur des fentes, hauteur des tours, position des broches, étendue de la coque…) en
# découlent pour chaque scanner : elles sont recalculées à chaque construction (guide.json > "dimensions").
# clé de la prescription -> (attribut de parametres.py, minimum, maximum, symbole du plan, description)
PARAMETRES_GUIDE = {
    "jeu_mm": ("GUIDE_JEU_MM", 0.1, 1.0, "j", "jeu entre l'os et la surface d'appui"),
    "epaisseur_coque_mm": ("GUIDE_EPAISSEUR_MM", 1.5, 6.0, "e", "épaisseur de la coque"),
    "guidage_mm": ("GUIDE_GUIDAGE_MM", 4.0, 25.0, "g", "hauteur de guidage minimale des tours de fente et des manchons au-dessus de la coque"),
    "paroi_mm": ("GUIDE_PAROI_MM", 1.2, 4.0, "p", "épaisseur des parois des tours et des manchons"),
    "lame_mm": ("GUIDE_LAME_MM", 0.3, 1.5, "s", "épaisseur de la lame de scie"),
    "jeu_fente_mm": ("GUIDE_JEU_FENTE_MM", 0.05, 0.6, "js", "jeu ajouté à la lame dans la fente"),
    "broche_mm": ("GUIDE_BROCHE_MM", 1.0, 3.2, "Øb", "diamètre des broches de Kirschner"),
    "jeu_broche_mm": ("GUIDE_JEU_BROCHE_MM", 0.05, 0.6, "jb", "jeu ajouté au diamètre de la broche dans le manchon"),
    "marge_mm": ("GUIDE_MARGE_MM", 3.0, 25.0, "m", "dépassement de la coque au-delà des broches extrêmes"),
    "secteur_deg": ("GUIDE_SECTEUR_DEG", 30.0, 120.0, "α", "demi-ouverture de la coque autour de la face d'appui"),
    "pont_mm": ("GUIDE_PONT_MM", 2.0, 10.0, "hp", "hauteur des ponts sécables"),
    "chanfrein_mm": ("GUIDE_CHANFREIN_MM", 0.0, 1.5, "c", "chanfreins d'entrée (fentes, manchons)"),
    "depouille_deg": ("GUIDE_DEPOUILLE_DEG", 1.0, 15.0, "δ", "angle de dépouille (pose et retrait sans contre-dépouille)"),
    "conge_mm": ("GUIDE_CONGE_MM", 0.0, 2.0, "r", "rayon des congés"),
    "epaisseur_min_mm": ("GUIDE_EPAISSEUR_MIN_MM", 0.6, 3.0, "emin", "épaisseur minimale imprimable"),
    "jeu_voisin_mm": ("GUIDE_JEU_VOISIN_MM", 0.5, 4.0, "jv", "distance minimale aux os voisins"),
    "marge_cartilage_mm": ("GUIDE_MARGE_CARTILAGE_MM", 0.5, 5.0, "mc", "écart supplémentaire de la coque au cartilage"),
    "reduction_ecart_mm": ("REDUCTION_ECART_MM", 2.0, 15.0, "er", "guide de réduction : distance de la barre à l'os"),
    "reduction_manchon_mm": ("REDUCTION_MANCHON_MM", 6.0, 25.0, "lr", "guide de réduction : longueur des manchons"),
    "reduction_barre_mm": ("REDUCTION_BARRE_MM", 3.0, 12.0, "tb", "guide de réduction : épaisseur de la barre"),
}


class parametres_du_cas:
    """Applique les dimensions choisies pour un cas (prescription > parametres_guide) aux réglages de parametres.py, le
    temps d'une construction (bornées par PARAMETRES_GUIDE ; une valeur absente ou invalide garde sa valeur par défaut),
    puis rétablit les valeurs par défaut. Une construction à la fois par processus (serveur : fil de calcul unique)."""

    def __init__(self, pr):
        self.demandes = dict((pr or {}).get("parametres_guide") or {})
        self.anciens, self.appliques = {}, {}

    def __enter__(self):
        self.defauts = valeurs_parametres()            # valeurs de parametres.py avant les réglages du cas
        for cle, x in self.demandes.items():
            if cle not in PARAMETRES_GUIDE:
                continue
            attr, lo, hi = PARAMETRES_GUIDE[cle][:3]
            try:
                val = float(x)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(val):
                continue
            self.anciens[attr] = getattr(P, attr)
            setattr(P, attr, float(np.clip(val, lo, hi)))
            self.appliques[cle] = getattr(P, attr)
        return self

    def __exit__(self, *exc):
        for attr, val in self.anciens.items():
            setattr(P, attr, val)
        return False


def valeurs_parametres():
    """Valeurs courantes des paramètres du guide générique (clés de la prescription)."""
    return {cle: getattr(P, attr) for cle, (attr, *_r) in PARAMETRES_GUIDE.items()}


PARAMETRES_DEFAUT = valeurs_parametres()      # valeurs de parametres.py au chargement (avant tout réglage d'un cas)


VIDE = np.float32(-1e3)          # hauteur d'une colonne sans os (cartes de hauteur)
COMPENSATION_MM = 0.04           # l'isosurface interpole linéairement la distance entre les nœuds : sur un os convexe elle
                                 # passe jusqu'à ≈ 0,03 mm trop près ; le jeu visé est J + 0,04 mm pour garantir d ≥ J
FROTTEMENT_MM3 = 0.5             # deux pièces qui glissent l'une contre l'autre en s'interpénétrant de moins de 0,5 mm³
                                 # (parois de fente sur toute leur hauteur : quelques µm d'épaisseur) frottent sans bloquer
# recherches dans les arbres k-d (scipy) réparties sur tous les cœurs (5 fois plus rapide sur 10 cœurs) ; une limite
# fixée par OMP_NUM_THREADS (campagnes : plusieurs guides en parallèle) est respectée
FILS = int(os.environ.get("OMP_NUM_THREADS") or 0) or -1
TOL_OMBRE_MM = 0.5               # la contrainte « pas de contre-dépouille » est abaissée de 0,5 mm (verticalement) : sur
                                 # la face visible de l'os, c'est le jeu exact d ≥ J qui commande (la carte de hauteur,
                                 # discrétisée à 0,3 mm, surestime l'os sur les pentes) ; près de la silhouette, le cône de
                                 # dépouille est presque vertical : 0,5 mm vertical = 0,04 mm latéral pour 5°


# --------------------------------------------------------------------------- géométrie
def unitaire(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def perp(a, axe):
    """Composante de a perpendiculaire à axe (unitaire), normalisée."""
    a = np.asarray(a, float)
    return unitaire(a - (a @ axe) * axe)


def base(e0, e2):
    """Repère orthonormé direct (lignes e0, e1, e2) : e0 imposé, e2 ≈ e2 donné."""
    e0 = unitaire(e0)
    e2 = perp(e2, e0)
    return np.vstack([e0, np.cross(e2, e0), e2])


def smin(a, b, k):
    """Minimum lisse (union avec congé de rayon ≈ k) de deux champs."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def angle_deg(a, b):
    return float(np.degrees(np.arccos(np.clip(unitaire(a) @ unitaire(b), -1.0, 1.0))))


# --------------------------------------------------------------------------- maillages
def lire_maillage(chemin):
    """Maillage (sommets, triangles) : format .bin de l'application (nb sommets, nb triangles, float32, uint32) ou STL."""
    chemin = Path(chemin)
    if chemin.suffix.lower() == ".bin":
        b = chemin.read_bytes()
        nv, nf = (int(x) for x in np.frombuffer(b, np.uint32, 2))
        v = np.frombuffer(b, np.float32, nv * 3, 8).reshape(-1, 3).astype(float)
        f = np.frombuffer(b, np.uint32, nf * 3, 8 + nv * 12).reshape(-1, 3).astype(np.int64)
        return v, f
    import trimesh
    m = trimesh.load(chemin, force="mesh", process=True)
    return np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)


def ecrire_bin(chemin, v, f):
    Path(chemin).write_bytes(np.array([len(v), len(f)], np.uint32).tobytes() + np.asarray(v, np.float32).tobytes()
                             + np.asarray(f, np.uint32).tobytes())


def ecrire_stl(chemin, v, f, nom="CT-CORA3D"):
    """STL binaire (normales calculées)."""
    tri = np.asarray(v, np.float32)[np.asarray(f)]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    d = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    d["n"], d["v"] = n, tri
    Path(chemin).write_bytes(nom.encode()[:80].ljust(80, b" ") + np.uint32(len(tri)).tobytes() + d.tobytes())


def polydata(v, f):
    pts = vtk.vtkPoints()
    pts.SetData(ns.numpy_to_vtk(np.ascontiguousarray(v, float), deep=True))
    cel = vtk.vtkCellArray()
    cel.SetData(ns.numpy_to_vtkIdTypeArray(np.arange(0, 3 * len(f) + 1, 3, dtype=np.int64), deep=True),
                ns.numpy_to_vtkIdTypeArray(np.ascontiguousarray(f, np.int64).ravel(), deep=True))
    p = vtk.vtkPolyData()
    p.SetPoints(pts)
    p.SetPolys(cel)
    return p


def vers_manifold(v, f):
    mesh = m3d.Mesh(vert_properties=np.ascontiguousarray(v, np.float32), tri_verts=np.ascontiguousarray(f, np.uint32))
    man = m3d.Manifold(mesh)
    if man.status() != m3d.Error.NoError:
        mesh.merge()
        man = m3d.Manifold(mesh)
    if man.status() != m3d.Error.NoError:
        raise ValueError(f"maillage non manifold ({man.status()})")
    return man


def depuis_manifold(man):
    mesh = man.to_mesh()
    return np.asarray(mesh.vert_properties[:, :3], float), np.asarray(mesh.tri_verts, np.int64)


def boite_m(centre, axes, demi):
    """Pavé exact : centre, 3 axes orthonormés directs, demi-dimensions."""
    A = np.column_stack(axes)
    demi = np.asarray(demi, float)
    return m3d.Manifold.cube(tuple(2 * demi)).transform(np.column_stack([A, np.asarray(centre) - A @ demi]))


def cylindre_m(a, o, t0, t1, r, segments=48):
    """Cylindre exact d'axe (a, o) entre les abscisses t0 et t1."""
    return cone_m(a, o, t0, t1, r, r, segments)


def cone_m(a, o, t0, t1, r0, r1, segments=48):
    """Tronc de cône exact d'axe (a, o) : rayon r0 à l'abscisse t0, r1 à t1 (chanfreins d'entrée)."""
    o = unitaire(o)
    b1 = perp([1.0, 0, 0] if abs(o[0]) < 0.9 else [0, 1.0, 0], o)
    b2 = np.cross(o, b1)
    M = np.column_stack([b1, b2, o, np.asarray(a) + t0 * o])
    return m3d.Manifold.cylinder(float(t1 - t0), float(r0), float(r1), segments).transform(M)


def transformation_reelle(pr, plans):
    """Correction obtenue au bloc (repère de l'os, fragment proximal fixe). C'est T de la prescription, sauf pour un coin
    de fermeture : chaque trait de scie enlève l'épaisseur de la lame s, centrée sur son plan ; quand le chirurgien ferme
    le coin jusqu'au contact des surfaces osseuses, le fragment distal avance encore de s vers le proximal, le long de la
    normale au 1er plan. Sans cette compensation du trait de scie, un ajustement à 0,1 mm près ne s'emboîterait pas."""
    T = np.asarray(pr["correction"]["T_4x4"], float).copy()
    if pr["strategie"]["type_coin"] == "fermeture" and len(plans) == 2:
        T[:3, 3] -= P.GUIDE_LAME_MM * unitaire(plans[0][1])
    return T


def appliquer(T, x):
    """Transformation rigide 4 × 4 appliquée à des points (…, 3)."""
    T = np.asarray(T, float)
    return np.asarray(x, float) @ T[:3, :3].T + T[:3, 3]


def profondeurs_fentes(pr):
    """Profondeur de chaque fente : « charniere » (la lame s'arrête à la charnière) ou « complete » (jusqu'à la corticale
    opposée) ; celle de la prescription, sinon selon l'ostéotomie (complète si elle est prescrite ou s'il faut dérouter)."""
    st = pr["strategie"]
    derot = float(pr.get("correction", {}).get("derotation_deg", 0) or 0)
    complete = bool(st.get("osteotomie_complete", abs(derot) >= 1))
    return [x.get("profondeur") or ("complete" if complete else "charniere") for x in pr.get("plans_coupe", [])]


def echantillons(v, f, pas, graine=0):
    """Points sur la surface (sommets + points tirés dans chaque triangle, ≈ 8 par pixel de côté `pas`)."""
    tri = v[f]
    aire = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    k = np.ceil(aire / (pas * pas / 8)).astype(np.int64)
    idx = np.repeat(np.arange(len(f)), k)
    r1, r2 = np.random.default_rng(graine).random((2, len(idx)))
    s = np.sqrt(r1)
    pts = (1 - s)[:, None] * tri[idx, 0] + (s * (1 - r2))[:, None] * tri[idx, 1] + (s * r2)[:, None] * tri[idx, 2]
    return np.vstack([v[np.unique(f)], pts])


def dist2_point_triangle(p, a, b, c, point=False):
    """Carré de la distance exacte de points p à des triangles (a, b, c), tableaux diffusables (…, 3) : point le plus
    proche par les régions de Voronoï du triangle (Ericson, Real-Time Collision Detection, § 5.1.5). point=True : renvoie
    aussi le point le plus proche."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = np.einsum("...i,...i", ab, ap), np.einsum("...i,...i", ac, ap)
    bp = p - b
    d3, d4 = np.einsum("...i,...i", ab, bp), np.einsum("...i,...i", ac, bp)
    cp = p - c
    d5, d6 = np.einsum("...i,...i", ab, cp), np.einsum("...i,...i", ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    sur = lambda x: np.where(x == 0, 1.0, x)
    den = 1.0 / sur(va + vb + vc)
    q = a + ab * (vb * den)[..., None] + ac * (vc * den)[..., None]            # intérieur de la face
    # du moins prioritaire au plus prioritaire (dans l'algorithme, les tests sont faits dans l'ordre inverse)
    m = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)                              # arête BC
    q = np.where(m[..., None], b + (c - b) * ((d4 - d3) / sur((d4 - d3) + (d5 - d6)))[..., None], q)
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)                                        # arête AC
    q = np.where(m[..., None], a + ac * (d2 / sur(d2 - d6))[..., None], q)
    q = np.where(((d6 >= 0) & (d5 <= d6))[..., None], c, q)                      # sommet C
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)                                        # arête AB
    q = np.where(m[..., None], a + ab * (d1 / sur(d1 - d3))[..., None], q)
    q = np.where(((d3 >= 0) & (d4 <= d3))[..., None], b, q)                      # sommet B
    q = np.where(((d1 <= 0) & (d2 <= 0))[..., None], a, q)                       # sommet A
    d2_ = np.einsum("...i,...i", p - q, p - q)
    return (d2_, q) if point else d2_


class DistanceSurface:
    """Distance exacte (non signée) de points à une surface triangulée. Triangles candidats : ceux des k échantillons
    de surface les plus proches (arbre k-d, échantillons denses qui connaissent leur triangle), puis distance exacte
    point-triangle. Remplace vtkImplicitPolyDataDistance, dont l'évaluation a planté par intermittence (VTK 9.7)."""

    def __init__(self, v, f, pas=0.3, zone=None):
        v, f = np.asarray(v, float), np.asarray(f, np.int64)
        if zone is not None:                                   # seulement les triangles qui touchent la zone utile
            lo, hi = zone                                      # (boîte englobante du triangle : un long triangle
            t = v[f]                                           # dont le centre est loin peut la traverser)
            f = f[np.all(t.max(1) > lo, axis=1) & np.all(t.min(1) < hi, axis=1)]
        self.v, self.f = v, f
        self.vide = len(f) == 0                                # aucun triangle dans la zone : distance infinie
        if self.vide:
            return
        tri = v[f]
        aire = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        n = np.maximum(1, np.ceil(aire / (pas * pas / 2)).astype(np.int64))        # ≥ 1 échantillon (centre) par triangle
        self.ti = np.repeat(np.arange(len(f)), n)
        r1, r2 = np.random.default_rng(1).random((2, len(self.ti)))
        r1[np.r_[0, np.cumsum(n)[:-1]]], r2[np.r_[0, np.cumsum(n)[:-1]]] = 4 / 9, 0.5   # premier échantillon = centre
        s_ = np.sqrt(r1)
        t = tri[self.ti]
        pts = (1 - s_)[:, None] * t[:, 0] + (s_ * (1 - r2))[:, None] * t[:, 1] + (s_ * r2)[:, None] * t[:, 2]
        self.arbre = cKDTree(pts)

    def __call__(self, q, k=6, bloc=150_000):
        q = np.asarray(q, float)
        if self.vide:
            return np.full(len(q), np.inf)
        k = min(k, self.arbre.n)
        out = np.empty(len(q))
        for i in range(0, len(q), bloc):
            qq = q[i:i + bloc]
            _, idx = self.arbre.query(qq, k=k, workers=FILS)
            idx = idx.reshape(len(qq), -1)
            T = self.f[self.ti[idx]]
            out[i:i + bloc] = np.sqrt(dist2_point_triangle(qq[:, None, :], self.v[T[..., 0]], self.v[T[..., 1]], self.v[T[..., 2]]).min(1))
        return out

    def plus_proche(self, q, k=6):
        """Distance exacte et point le plus proche de la surface, pour chaque point q."""
        q = np.asarray(q, float)
        _, idx = self.arbre.query(q, k=min(k, self.arbre.n), workers=FILS)
        idx = idx.reshape(len(q), -1)
        T = self.f[self.ti[idx]]
        d2, pts = dist2_point_triangle(q[:, None, :], self.v[T[..., 0]], self.v[T[..., 1]], self.v[T[..., 2]], point=True)
        j = d2.argmin(1)
        return np.sqrt(d2[np.arange(len(q)), j]), pts[np.arange(len(q)), j]


def distance_exacte(poly_ou_maillage, pts, marge=6.0):
    """Distance exacte non signée de points à une surface (maillage (v, f)), limitée aux triangles proches des points."""
    v, f = poly_ou_maillage
    pts = np.asarray(pts, float)
    zone = (pts.min(0) - marge, pts.max(0) + marge)
    return DistanceSurface(v, f, zone=zone)(pts)


# --------------------------------------------------------------------------- grille et champs
class Grille:
    """Grille régulière de pas h dans le repère (K, R) : q = R (p − K). Champs : tableaux (n0, n1, n2) float32."""

    def __init__(self, K, R, lo, hi, h):
        self.K, self.R, self.h = np.asarray(K, float), np.asarray(R, float), float(h)
        self.lo = np.asarray(lo, float)
        self.n = np.ceil((np.asarray(hi, float) - self.lo) / h).astype(int) + 1
        self.q = [(self.lo[i] + h * np.arange(self.n[i])).astype(np.float32) for i in range(3)]

    def vers(self, p):
        return (np.asarray(p, float) - self.K) @ self.R.T

    def vec(self, d):
        return np.asarray(d, float) @ self.R.T

    def depuis(self, q):
        return self.K + np.asarray(q, float) @ self.R

    def tranche(self, pts_q, marge):
        """Indices de la sous-grille qui contient les points (repère de la grille) à `marge` près."""
        lo, hi = np.min(pts_q, 0) - marge, np.max(pts_q, 0) + marge
        a = np.clip(np.floor((lo - self.lo) / self.h).astype(int), 0, self.n)
        b = np.clip(np.ceil((hi - self.lo) / self.h).astype(int) + 1, 0, self.n)
        return tuple(slice(int(x), int(y)) for x, y in zip(a, b))

    def sous_grille(self, sl):
        """Sous-grille alignée sur celle-ci (mêmes nœuds) pour les tranches d'indices sl."""
        g = Grille.__new__(Grille)
        g.K, g.R, g.h = self.K, self.R, self.h
        g.q = [self.q[i][sl[i]] for i in range(3)]
        g.lo = np.array([float(x[0]) for x in g.q])
        g.n = np.array([len(x) for x in g.q])
        return g

    def plan(self, p, n, sl=None):
        """Distance signée au plan (p, n), donnés dans le repère de la grille (n unitaire)."""
        sl = sl or (slice(None),) * 3
        c = [(self.q[i][sl[i]] - np.float32(p[i])) * np.float32(n[i]) for i in range(3)]
        return c[0][:, None, None] + c[1][None, :, None] + c[2][None, None, :]

    def dist2(self, a, sl=None):
        sl = sl or (slice(None),) * 3
        c = [(self.q[i][sl[i]] - np.float32(a[i])) ** 2 for i in range(3)]
        return c[0][:, None, None] + c[1][None, :, None] + c[2][None, None, :]


def champ_boite(gr, c, axes, demi, sl=None):
    F = None
    for ax, dm in zip(axes, demi):
        x = np.abs(gr.plan(c, ax, sl)) - np.float32(dm)
        F = x if F is None else np.maximum(F, x)
    return F


def champ_boite_arrondie(gr, c, axes, demi, r, sl=None):
    """Pavé aux arêtes arrondies de rayon r : distance signée exacte (moins d'arêtes vives : gants, tissus, impression)."""
    q = [np.abs(gr.plan(c, ax, sl)) - np.float32(dm - r) for ax, dm in zip(axes, demi)]
    dehors = np.sqrt(np.maximum(q[0], 0) ** 2 + np.maximum(q[1], 0) ** 2 + np.maximum(q[2], 0) ** 2)
    return dehors + np.minimum(np.maximum(np.maximum(q[0], q[1]), q[2]), 0) - np.float32(r)


def champ_cylindre(gr, a, o, r, t0, t1, sl=None):
    t = gr.plan(a, o, sl)
    rho = np.sqrt(np.maximum(gr.dist2(a, sl) - t * t, 0))
    return np.maximum(rho - np.float32(r), np.maximum(np.float32(t0) - t, t - np.float32(t1)))


def champ_capsule(gr, a, b, r, sl=None):
    """Capsule de rayon r autour du segment [a, b] (repère de la grille) : distance au segment moins r."""
    ab = np.asarray(b, float) - np.asarray(a, float)
    L = float(np.linalg.norm(ab))
    proj = gr.plan(a, ab / L, sl)                                  # (p − a)·ab / L
    t = np.clip(proj / np.float32(L), 0, 1)
    d2 = gr.dist2(a, sl) - 2 * t * proj * np.float32(L) + t * t * np.float32(L * L)
    return np.sqrt(np.maximum(d2, 0)) - np.float32(r)


def champ_secteur(gr, a, axe, c0, A):
    """Négatif dans le dièdre d'angle ± A autour de la direction c0, d'arête la droite (a, axe)."""
    s0 = np.cross(axe, c0)
    n1, n2 = np.sin(A) * c0 - np.cos(A) * s0, np.sin(A) * c0 + np.cos(A) * s0
    return np.maximum(-gr.plan(a, n1), -gr.plan(a, n2))


def distance_signee(gr, v, f, bande):
    """Distance signée à l'os aux nœuds (négative dedans) : signe exact par voxelisation (rayons), valeur exacte à
    moins de `bande` mm de la surface, approchée (Maurer) au-delà."""
    poly = polydata(gr.vers(v), f)
    n0, n1, n2 = (int(x) for x in gr.n)
    st = vtk.vtkPolyDataToImageStencil()
    st.SetInputData(poly)
    st.SetOutputOrigin(*gr.lo)
    st.SetOutputSpacing(gr.h, gr.h, gr.h)
    st.SetOutputWholeExtent(0, n0 - 1, 0, n1 - 1, 0, n2 - 1)
    im = vtk.vtkImageStencilToImage()
    im.SetInputConnection(st.GetOutputPort())
    im.SetInsideValue(1)
    im.SetOutsideValue(0)
    im.SetOutputScalarTypeToUnsignedChar()
    im.Update()
    masque = ns.vtk_to_numpy(im.GetOutput().GetPointData().GetScalars()).reshape(n2, n1, n0)
    img = sitk.GetImageFromArray(masque.astype(np.uint8))
    img.SetSpacing((gr.h,) * 3)
    dm = sitk.SignedMaurerDistanceMap(img, insideIsPositive=False, squaredDistance=False, useImageSpacing=True)
    d = sitk.GetArrayFromImage(dm).astype(np.float32).transpose(2, 1, 0).copy()
    dedans = masque.transpose(2, 1, 0).astype(bool)
    # valeur exacte seulement à l'extérieur de l'os, dans la bande où le guide peut exister (dedans : le signe suffit)
    sel = np.nonzero((d > -gr.h) & (d < bande + gr.h))
    pts = np.column_stack([gr.q[0][sel[0]], gr.q[1][sel[1]], gr.q[2][sel[2]]])
    if len(pts):                                   # (un os voisin peut toucher la boîte sans approcher des nœuds)
        ex = distance_exacte((gr.vers(v), f), pts).astype(np.float32)
        d[sel] = np.where(dedans[sel], -ex, ex)
    return d, int(len(pts))


def distance_voisin(gr, v, f, bande):
    """Distance signée à un os voisin, calculée seulement sur la sous-grille qui l'entoure (à bande + 2 mm près) :
    (tranches, distances), ou None s'il est hors de la grille. Économise la mémoire : la rotule ou une fabelle n'occupent
    qu'une petite partie de la grille du guide."""
    sl = gr.tranche(gr.vers(v), bande + 2.0)
    if any(x.stop - x.start < 3 for x in sl):
        return None
    return sl, distance_signee(gr.sous_grille(sl), v, f, bande)[0]


def carte_hauteur(ech, g, a1, a2, o, pas, forme):
    """Hauteur maximale de l'os le long de g, par pixel du plan (a1, a2) (origine o, pas) ; VIDE sans os."""
    i = np.rint((ech @ a1 - o[0]) / pas).astype(np.int64)
    j = np.rint((ech @ a2 - o[1]) / pas).astype(np.int64)
    ok = (i >= 0) & (i < forme[0]) & (j >= 0) & (j < forme[1])
    Hm = np.full(forme, VIDE, np.float32)
    np.maximum.at(Hm, (i[ok], j[ok]), (ech[ok] @ g).astype(np.float32))
    return ndimage.grey_closing(Hm, size=(3, 3))       # bouche les pixels isolés sans échantillon


def depouille(Hm, pas, J, alpha, rayon=2.0):
    """Hauteur interdite : enveloppe supérieure de l'os dilaté de J (calottes sphériques), prolongée vers le bas par un
    cône de demi-angle `alpha` (dépouille), puis abaissée de TOL_OMBRE_MM."""
    r = int(np.ceil(rayon / pas))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1] * pas
    dd = np.hypot(yy, xx)
    S = np.where(dd <= J, np.sqrt(np.maximum(J * J - dd * dd, 0)), -(dd - J) / np.tan(alpha)).astype(np.float32)
    return ndimage.grey_dilation(Hm, footprint=dd <= rayon, structure=S) - np.float32(TOL_OMBRE_MM)


def ombre(gr, ech_q, g, J, alpha):
    """Champ « sous l'os » vu depuis la direction g (repère de la grille) : > 0 là où de la matière accrocherait l'os
    (os dilaté de J, cône de dépouille) pendant un retrait le long de g."""
    g = unitaire(g)
    if abs(g[0]) > 1 - 1e-9:                          # direction de la grille : carte sur les colonnes (q1, q2)
        Hm = carte_hauteur(ech_q, g, np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), gr.lo[1:], gr.h, tuple(gr.n[1:]))
        return depouille(Hm, gr.h, J, alpha)[None, :, :] - gr.q[0][:, None, None] * np.float32(g[0])
    a1 = perp([0, 0, 1.0], g)
    a2 = np.cross(g, a1)
    coins = np.array([[gr.q[0][i], gr.q[1][j], gr.q[2][k]] for i in (0, -1) for j in (0, -1) for k in (0, -1)])
    c1, c2 = coins @ a1, coins @ a2
    o = (c1.min() - 3, c2.min() - 3)
    forme = (int(np.ceil((np.ptp(c1) + 6) / gr.h)) + 1, int(np.ceil((np.ptp(c2) + 6) / gr.h)) + 1)
    Hm = depouille(carte_hauteur(ech_q, g, a1, a2, o, gr.h, forme), gr.h, J, alpha)
    u1 = (gr.plan(np.zeros(3), a1) - np.float32(o[0])) / np.float32(gr.h)
    u2 = (gr.plan(np.zeros(3), a2) - np.float32(o[1])) / np.float32(gr.h)
    hv = ndimage.map_coordinates(Hm, [u1.ravel(), u2.ravel()], order=1, mode="constant", cval=float(VIDE))
    return hv.reshape(u1.shape).astype(np.float32) - gr.plan(np.zeros(3), g)


def sans_parties_fines(gr, F, epaisseur_min):
    """Supprime les parties du solide {F < 0} plus fines que `epaisseur_min` (lèvres en biseau en bord de coque, qui
    casseraient à l'impression) : ouverture morphologique par une boule, puis la matière n'est gardée qu'à moins d'un
    pas de grille du solide ouvert. Les surfaces exactes (appui à J, faces des tours) ne bougent pas."""
    r = max(1, int(round(epaisseur_min / 2 / gr.h)))
    zz, yy, xx = np.mgrid[-r:r + 1, -r:r + 1, -r:r + 1]
    boule = xx * xx + yy * yy + zz * zz <= r * r
    plein = F < 0
    ouvert = ndimage.binary_opening(plein, structure=boule)
    retire = int(plein.sum() - (plein & ouvert).sum())
    img = sitk.GetImageFromArray(ouvert.transpose(2, 1, 0).astype(np.uint8))
    img.SetSpacing((gr.h,) * 3)
    d = sitk.GetArrayFromImage(sitk.SignedMaurerDistanceMap(img, insideIsPositive=False, squaredDistance=False,
                                                            useImageSpacing=True)).transpose(2, 1, 0)
    return np.maximum(F, d.astype(np.float32) - np.float32(gr.h)), retire


def isosurface(gr, F):
    """Surface F = 0 (Flying Edges) -> solide manifold dans le repère de l'os."""
    F = F.copy()
    F[[0, -1], :, :] = 1.0
    F[:, [0, -1], :] = 1.0
    F[:, :, [0, -1]] = 1.0
    F[F == 0] = np.float32(1e-6)
    img = vtk.vtkImageData()
    img.SetDimensions(*(int(x) for x in gr.n))
    img.SetSpacing(gr.h, gr.h, gr.h)
    img.SetOrigin(*gr.lo)
    img.GetPointData().SetScalars(ns.numpy_to_vtk(np.ascontiguousarray(F.transpose(2, 1, 0)).ravel(), deep=True))
    fe = vtk.vtkFlyingEdges3D()
    fe.SetInputData(img)
    fe.SetValue(0, 0.0)
    fe.ComputeNormalsOff()
    fe.ComputeGradientsOff()
    fe.ComputeScalarsOff()
    fe.Update()
    out = fe.GetOutput()
    if out.GetNumberOfPoints() == 0:
        raise ValueError("isosurface vide")
    q = ns.vtk_to_numpy(out.GetPoints().GetData()).astype(float)
    t = ns.vtk_to_numpy(out.GetPolys().GetConnectivityArray()).reshape(-1, 3).astype(np.int64)
    v = gr.depuis(q)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    if np.einsum("ij,ij->i", a, np.cross(b, c)).sum() < 0:      # volume signé négatif : triangles retournés
        t = t[:, ::-1]
    return vers_manifold(v, t)


def section_os(poly, p, n, hh, ll, K):
    """Contour de l'os dans le plan (p, n) autour de K : étendues le long de ll (longueur de la fente) et de hh
    (vers la face d'appui), coordonnées relatives à p. Le contour retenu est le plus grand de ceux qui entourent K
    (le canal médullaire éventuel est ignoré), sinon le plus proche de K."""
    pl = vtk.vtkPlane()
    pl.SetOrigin(*p)
    pl.SetNormal(*n)
    cut = vtk.vtkCutter()
    cut.SetInputData(poly)
    cut.SetCutFunction(pl)
    con = vtk.vtkPolyDataConnectivityFilter()
    con.SetInputConnection(cut.GetOutputPort())
    con.SetExtractionModeToAllRegions()
    con.ColorRegionsOn()
    con.Update()
    out = con.GetOutput()
    if out.GetNumberOfPoints() == 0:
        raise ValueError("le plan de coupe ne coupe pas l'os")
    pts = ns.vtk_to_numpy(out.GetPoints().GetData()).astype(float)
    reg = ns.vtk_to_numpy(out.GetPointData().GetArray("RegionId"))
    kh, kl = (K - p) @ hh, (K - p) @ ll
    meilleur, entoure = None, []
    for r in np.unique(reg):
        q = pts[reg == r] - p
        h_, l_ = q @ hh, q @ ll
        info = dict(lmin=l_.min(), lmax=l_.max(), hmin=h_.min(), hmax=h_.max(), hc=float(np.mean(h_)), n=len(q),
                    dist=float(np.min(np.hypot(h_ - kh, l_ - kl))))
        if info["lmin"] < kl < info["lmax"] and info["hmin"] < kh < info["hmax"]:
            entoure.append(info)
        if meilleur is None or info["dist"] < meilleur["dist"]:
            meilleur = info
    if entoure:
        meilleur = max(entoure, key=lambda x: (x["lmax"] - x["lmin"]) * (x["hmax"] - x["hmin"]))
    return {k: float(x) for k, x in meilleur.items()}


def dans_secteur(pts, a, axe, c0, A):
    q = pts - a
    q = q - np.outer(q @ axe, axe)
    s0 = np.cross(axe, c0)
    return np.abs(np.arctan2(q @ s0, q @ c0)) <= A


def lire_broches(pr):
    """Broches de la prescription (v2.2 : 4 broches de réduction ; v2.1 : 2 broches), triées et nommées
    P1, P2 (proximales, de la plus proche de l'ostéotomie à la plus éloignée), D1, D2 (distales)."""
    src = pr.get("broches_reduction") or pr.get("broches") or []
    K = np.array(pr["guide"]["centre_section"], float)
    out = []
    for b in src:
        a, d = np.array(b["point_axe"], float), unitaire(b["direction"])
        out.append({"fragment": b["fragment"], "a": a, "d": d, "dist_K": float(np.linalg.norm(a - K)),
                    "hauteur_manchon": b.get("hauteur_manchon_mm")})
    res = []
    for frag, lettre in (("proximal", "P"), ("distal", "D")):
        g = sorted([x for x in out if x["fragment"] == frag], key=lambda x: x["dist_K"])
        for i, x in enumerate(g):
            x["nom"] = f"{lettre}{i + 1}"
            res.append(x)
    return res


def volume_pieces(man):
    return sorted(man.decompose(), key=lambda m: m.volume(), reverse=True)


def cote_plan(man, p, n):
    """Distance signée moyenne des sommets d'une pièce au plan (p, n)."""
    v, _ = depuis_manifold(man)
    return float(np.mean((v - p) @ n))


def retrait_libre(poly_os, pts, r, longueur=50.0, n_max=4000):
    """Lancer de rayons : nombre de points de la pièce dont le trajet de retrait (direction r, 50 mm) rencontre l'os.
    Seuls les impacts effectifs comptent (la valeur renvoyée par vtkOBBTree n'est pas fiable sans impact)."""
    loc = vtk.vtkStaticCellLocator()
    loc.SetDataSet(poly_os)
    loc.BuildLocator()
    if len(pts) > n_max:
        pts = pts[np.random.default_rng(0).choice(len(pts), n_max, replace=False)]
    P_, ids = vtk.vtkPoints(), vtk.vtkIdList()
    touches = 0
    for x in pts:
        ids.Reset()
        loc.IntersectWithLine(x + 0.01 * r, x + longueur * r, P_, ids)
        touches += ids.GetNumberOfIds() > 0
    return int(touches), int(len(pts))


def dedans(poly, pts):
    """Points à l'intérieur de la surface fermée (test par rayons, VTK)."""
    pp = vtk.vtkPolyData()
    P_ = vtk.vtkPoints()
    P_.SetData(ns.numpy_to_vtk(np.ascontiguousarray(pts, float), deep=True))
    pp.SetPoints(P_)
    sel = vtk.vtkSelectEnclosedPoints()
    sel.SetInputData(pp)
    sel.SetSurfaceData(poly)
    sel.Update()
    return ns.vtk_to_numpy(sel.GetOutput().GetPointData().GetArray("SelectedPoints")).astype(bool)


def jeu_controle(maillage, pts, interpenetration=None):
    """Jeu (distance à l'os) de chaque point, négatif s'il est dans l'os. La valeur vient de la distance exacte au
    triangle le plus proche. Le signe : si le volume d'interpénétration exact (booléen manifold3d) est nul, aucun point
    n'est dans l'os ; sinon (ou si l'os n'est pas un solide valide), test d'inclusion par rayons près de l'os (le signe
    « par les normales » de VTK se trompe parfois loin de l'os, et le test par rayons de VTK donne de rares faux positifs)."""
    a = distance_exacte(maillage, pts)
    if interpenetration is not None and interpenetration < 1e-3:
        return a
    pres = np.nonzero(a < 3.0)[0]
    if len(pres):
        a[pres[dedans(polydata(*maillage), pts[pres])]] *= -1
    return a


def mesures_piece(man, nom):
    v, f = depuis_manifold(man)
    return {"piece": nom, "volume_cm3": round(man.volume() / 1000, 3),
            "masse_g": round(man.volume() / 1000 * P.DENSITE_IMPRESSION_G_CM3, 2),
            "dimensions_mm": [round(float(x), 1) for x in np.ptp(v, axis=0)], "triangles": int(len(f))}


def assurer_jeu(man, v_os, f_os, J, depl_max=0.15):
    """Garantit le jeu J aux sommets du guide : l'isosurface interpole la distance linéairement entre les nœuds et peut
    passer un peu trop près de l'os là où la distance n'est pas lisse (raccord concave, arête). Chaque sommet à moins de
    J est repoussé le long de la normale à l'os jusqu'à J + 0,005 mm (au plus depl_max, topologie inchangée)."""
    gv, gf = depuis_manifold(man)
    ds = DistanceSurface(v_os, f_os, zone=(gv.min(0) - 2, gv.max(0) + 2))
    if ds.vide:
        return man, 0
    d0 = ds(gv)
    i = np.nonzero(d0 < J)[0]
    if not len(i):
        return man, 0
    d, q = ds.plus_proche(gv[i])
    i_ok = (J + 0.005 - d <= depl_max) & (d > 1e-6)
    gv = gv.copy()
    gv[i[i_ok]] = q[i_ok] + (gv[i[i_ok]] - q[i_ok]) * ((J + 0.005) / d[i_ok])[:, None]
    try:
        return vers_manifold(gv, gf), int(i_ok.sum())
    except ValueError:
        return man, 0


def etanche_stl(chemin):
    """Relit le STL comme un logiciel d'impression (sommets fusionnés) : étanche ?"""
    import trimesh
    m = trimesh.load(chemin, force="mesh", process=True)
    return bool(m.is_watertight), bool(m.is_winding_consistent)


def decoller_pincements(v, f, eps=2e-3):
    """Pincements : sommets distincts du solide (topologiquement) à la même position, là où deux nappes de la surface
    se touchent. Un STL n'a pas d'indices : relu, ces sommets fusionnent et l'arête voisine devient commune à 4 faces
    (non étanche). Chaque sommet confondu est écarté de eps (2 µm) vers le centre de ses propres triangles."""
    q = np.round(np.asarray(v, np.float32).astype(np.float64) * 1e5).astype(np.int64)
    _, inv, cnt = np.unique(q, axis=0, return_inverse=True, return_counts=True)
    dup = cnt[inv.ravel()] > 1
    if not dup.any():
        return v, 0
    acc, n = np.zeros_like(v), np.zeros(len(v))
    cen = v[f].mean(1)
    for k in range(3):
        np.add.at(acc, f[:, k], cen)
        np.add.at(n, f[:, k], 1.0)
    vers = acc / np.maximum(n, 1.0)[:, None] - v
    v = v.copy()
    v[dup] += eps * vers[dup] / np.maximum(np.linalg.norm(vers[dup], axis=1, keepdims=True), 1e-12)
    return v, int(dup.sum())


def exporter(man, chemin, nom):
    """Écrit le STL et le relit comme un logiciel d'impression. Les booléens laissent parfois des triangles d'aire
    nulle une fois les sommets arrondis en float32 (format STL) : le solide est reconstruit à partir des sommets
    arrondis (fusion), puis simplifié avec une tolérance croissante (≤ 0,001 mm) tant que le STL relu n'est pas étanche ;
    en dernier recours, les pincements (sommets distincts confondus) sont décollés de 2 µm."""
    v, f = depuis_manifold(man)
    try:
        base_ = vers_manifold(v.astype(np.float32).astype(float), f)
    except ValueError:
        base_ = man
    n_pinc = 0
    for tol in (0.0, 1e-4, 1e-3, "pincements"):
        if tol == "pincements":
            v, n_pinc = decoller_pincements(*depuis_manifold(m_))
            if not n_pinc:
                break
            try:
                m_ = vers_manifold(v.astype(np.float32).astype(float), f)
            except ValueError:
                break
        else:
            m_ = base_.simplify(tol) if tol else base_
        v, f = depuis_manifold(m_)
        ecrire_stl(chemin, v, f, nom)
        etanche, coherent = etanche_stl(chemin)
        if etanche:
            break
    return m_, v, f, {"etanche_stl": etanche, "orientation_coherente": coherent,
                      "tolerance_simplification_mm": tol if tol != "pincements" else 1e-3, "pincements_decolles": n_pinc}


def enveloppe_2d(pts):
    """Enveloppe convexe de points 2D (chaîne monotone d'Andrew), sens trigonométrique ; points alignés : 2 extrémités."""
    p = sorted({(round(float(x), 9), round(float(y), 9)) for x, y in pts})
    if len(p) <= 2:
        return np.array(p, float)
    croix = lambda o, a, b_: (a[0] - o[0]) * (b_[1] - o[1]) - (a[1] - o[1]) * (b_[0] - o[0])
    bas, haut = [], []
    for q in p:
        while len(bas) >= 2 and croix(bas[-2], bas[-1], q) <= 1e-9:
            bas.pop()
        bas.append(q)
    for q in reversed(p):
        while len(haut) >= 2 and croix(haut[-2], haut[-1], q) <= 1e-9:
            haut.pop()
        haut.append(q)
    return np.array(bas[:-1] + haut[:-1], float)


def dist_polygone(y, poly):
    """Distance de points 2D au polygone convexe `poly` (0 à l'intérieur) ; 1 ou 2 sommets : point ou segment."""
    y = np.asarray(y, float)
    if len(poly) == 1:
        return np.linalg.norm(y - poly[0], axis=1)
    plein = len(poly) > 2
    d = np.full(len(y), np.inf)
    dedans = np.full(len(y), plein)
    for i in range(len(poly) if plein else 1):
        p0, p1 = poly[i], poly[(i + 1) % len(poly)]
        w = p1 - p0
        t = np.clip(((y - p0) @ w) / (w @ w), 0, 1)
        d = np.minimum(d, np.linalg.norm(y - (p0 + np.outer(t, w)), axis=1))
        if plein:
            dedans &= (w[0] * (y[:, 1] - p0[1]) - w[1] * (y[:, 0] - p0[0])) >= 0
    d[dedans] = 0.0
    return d


def dist_boite(pts, c, axes, demi):
    """Distance de points à un pavé plein (0 dedans)."""
    r = np.asarray(pts, float) - c
    e = np.stack([np.maximum(np.abs(r @ a) - dm, 0.0) for a, dm in zip(axes, demi)], 1)
    return np.linalg.norm(e, axis=1)


def boite_grille(gr):
    """Boîte englobante de la grille dans le repère de l'os."""
    coins = np.array([[gr.q[0][i], gr.q[1][j], gr.q[2][k]] for i in (0, -1) for j in (0, -1) for k in (0, -1)])
    c = gr.depuis(coins)
    return c.min(0), c.max(0)


class EntreOs:
    """Espace ENTRE l'os et ses os voisins (fibula, rotule, fabelles), interdit au guide : le chirurgien ne peut ni y
    glisser une pièce (membrane interosseuse, muscles, articulation), ni y forer, ni y faire sortir la lame. Tranche par
    tranche le long de l'os (couches de la grille, dont le 3e axe suit l'os), c'est ce que l'enveloppe convexe de l'os
    ET du voisin ajoute à l'enveloppe convexe de l'os seul (la coque garde ainsi les creux de l'os lui-même).
    Champ (mm, repère de la grille) : > 0 dans cet espace (vers l'intérieur), ≤ 0 ailleurs.
    ech_os_q, voisins_q : échantillons de surface de l'os et de chaque voisin, en coordonnées de la grille."""

    def __init__(self, gr, ech_os_q, voisins_q, epaisseur=0.75):
        from scipy.spatial import ConvexHull, QhullError
        self.gr, self.couches = gr, {}                      # k -> [(équations de l'enveloppe commune, de l'os seul)]
        for vq in voisins_q:
            if len(vq) < 3:
                continue
            k0 = max(int(np.floor((vq[:, 2].min() - epaisseur - gr.lo[2]) / gr.h)), 0)
            k1 = min(int(np.ceil((vq[:, 2].max() + epaisseur - gr.lo[2]) / gr.h)), int(gr.n[2]) - 1)
            for k in range(k0, k1 + 1):
                z = float(gr.q[2][k])
                b = ech_os_q[np.abs(ech_os_q[:, 2] - z) <= epaisseur, :2]
                n = vq[np.abs(vq[:, 2] - z) <= epaisseur, :2]
                if len(b) < 3 or len(n) < 1:
                    continue
                try:
                    eq_u, eq_b = ConvexHull(np.vstack([b, n])).equations, ConvexHull(b).equations
                except QhullError:                           # section dégénérée (quelques points alignés)
                    continue
                self.couches.setdefault(k, []).append((eq_u, eq_b))

    @staticmethod
    def _champ(p2, eq_u, eq_b):
        # distance signée (minorée) aux deux enveloppes : < 0 dedans ; dans l'espace entre les os : dedans la commune et
        # dehors celle de l'os
        return np.minimum(-(p2 @ eq_u[:, :2].T + eq_u[:, 2]).max(1), (p2 @ eq_b[:, :2].T + eq_b[:, 2]).max(1))

    def champs(self):
        """(k, champ 2D de la couche k sur les nœuds (q0, q1)) pour les couches où un voisin est présent."""
        X0, X1 = np.meshgrid(self.gr.q[0], self.gr.q[1], indexing="ij")
        p2 = np.column_stack([X0.ravel(), X1.ravel()]).astype(np.float64)
        for k, liste in self.couches.items():
            yield k, np.max([self._champ(p2, eu, eb) for eu, eb in liste], axis=0).reshape(X0.shape)


def voisins_proches(voisins, lo, hi, marge=2.0):
    """Os voisins dont au moins un triangle touche la boîte (lo, hi) : [(nom, v, f, masque des triangles proches)]."""
    out = []
    for nom, vv, ff in voisins:
        t = vv[ff]
        m = np.all(t.max(1) > lo - marge, axis=1) & np.all(t.min(1) < hi + marge, axis=1)
        if m.any():
            out.append((nom, vv, ff, m))
    return out


def masque_cartilage(articulaire, n):
    """Masque booléen des sommets de cartilage : uint8 (≥ 128), booléen ou réel (≥ 0,5) ; None si absent ou incohérent."""
    if articulaire is None:
        return None
    a = np.asarray(articulaire)
    if len(a) != n:
        return None
    m = a >= 128 if a.dtype == np.uint8 else (a.astype(bool) if a.dtype == bool else a >= 0.5)
    return m if m.any() else None


# --------------------------------------------------------------------------- finitions
def chanfrein_fente(t, ws, ch, debord=0.3):
    """Entrée chanfreinée de la fente de la tour t : prisme à section carrée tourné de 45° autour de la fente, centré sur
    le haut de la tour ; il ouvre la fente à ws + 2 ch au ras du haut (pente de 45°) et déborde de 0,3 mm dans les parois
    d'extrémité (pas de faces confondues avec celles de la fente)."""
    s_ = t["sec"]
    a_ = np.sqrt(2.0) * (ch + ws / 2)
    c = t["p"] + t["h_top"] * t["hh"] + 0.5 * (s_["lmin"] + s_["lmax"]) * t["ll"]
    L = s_["lmax"] - s_["lmin"] + 2.0 + 2 * debord
    return boite_m(c, (unitaire(t["n"] + t["hh"]), unitaire(t["hh"] - t["n"]), t["ll"]), (a_ / 2, a_ / 2, L / 2))


# --------------------------------------------------------------------------- guide de coupe
def guide_coupe(pr, v, f, journal=print, voisins=(), cart=None):
    """Guide de coupe. voisins : [(nom, sommets, triangles)] os voisins à éviter (fibula, rotule, fabelles), dans le
    repère de l'os ; cart : points du cartilage articulaire de l'os (la coque d'appui ne s'y pose pas)."""
    J, E, Gd, W = P.GUIDE_JEU_MM, P.GUIDE_EPAISSEUR_MM, P.GUIDE_GUIDAGE_MM, P.GUIDE_PAROI_MM
    ws = P.GUIDE_LAME_MM + P.GUIDE_JEU_FENTE_MM          # largeur de fente
    rh = (P.GUIDE_BROCHE_MM + P.GUIDE_JEU_BROCHE_MM) / 2   # rayon des trous de broche
    Rs, Tt, k = rh + W, ws + 2 * W, P.GUIDE_CONGE_MM      # manchon, épaisseur de tour, congé
    alpha, A, MARGE = np.radians(P.GUIDE_DEPOUILLE_DEG), np.radians(P.GUIDE_SECTEUR_DEG), P.GUIDE_MARGE_MM
    JV = P.GUIDE_JEU_VOISIN_MM

    g = pr["guide"]
    K = np.array(g["centre_section"], float)
    u, vd = unitaire(g["axe_os"]), unitaire(g["axe_distal"])      # axes proximal et distal (vers distal)
    b = unitaire(u + vd)
    H = np.array(pr["charniere"]["point"], float)
    plans = [(np.array(p["point"], float), unitaire(p["normale"])) for p in pr["plans_coupe"]]
    broches = lire_broches(pr)
    prox = [x for x in broches if x["fragment"] == "proximal"]
    dist = [x for x in broches if x["fragment"] == "distal"]
    if not prox or not dist:
        raise ValueError("prescription sans broches proximales et distales")
    fp = unitaire(-np.mean([x["d"] for x in prox], 0))      # retrait de la moitié proximale (le long de ses broches)
    fd = unitaire(-np.mean([x["d"] for x in dist], 0))      # retrait de la moitié distale
    # pose du guide entier et direction des tours de fente : face d'appui prescrite (abord chirurgical, côté d'entrée de
    # la lame) ; les broches peuvent être tournées autour de l'os pour éviter le cartilage ou un os voisin
    face = unitaire(g["face_appui"]) if g.get("face_appui") is not None else fp
    Hs, nsep = plans[0]                                      # plan de séparation des moitiés : 1re coupe
    P_haut, P_bas = prox[-1]["a"], dist[-1]["a"]

    poly = polydata(v, f)
    cen = v[f].mean(1)
    s_b = (cen - K) @ b
    garde = (s_b > (P_haut - K) @ b - MARGE - 35) & (s_b < (P_bas - K) @ b + MARGE + 35)
    ech = echantillons(v, f[garde], P.GUIDE_PAS_MM)

    # broches : hauteur de l'os sous chaque manchon (côté face) et sortie de l'autre côté
    for x in broches:
        o = -x["d"]
        rel = ech - x["a"]
        t = rel @ o
        rho = np.linalg.norm(rel - np.outer(t, o), axis=1)
        pres = rho < Rs
        x["t_os"] = float(t[pres].max()) if pres.any() else 0.0
        x["t_sortie"] = float(t[rho < rh].min()) if (rho < rh).any() else -10.0
        # manchon : jeu + coque + guidage au-dessus de l'os, ou la hauteur prescrite si elle est plus courte (raccourci
        # par la planification pour ne pas heurter une tour de fente ; jamais moins de jeu + coque + 4 mm)
        hm = x.get("hauteur_manchon")
        x["t_haut"] = x["t_os"] + (J + E + Gd if hm is None else min(J + E + Gd, max(J + E + 4.0, float(hm))))

    # tours des fentes. Repère de chaque fente (n, hh, ll) : ll le long de la fente, hh vers la face d'appui (entrée de la
    # lame). Si la charnière est (presque) dans le plan, la fente lui est parallèle : la lame, enfoncée perpendiculairement
    # au haut de la tour, atteint la charnière à la même profondeur sur toute la longueur de la fente (profondeur donnée
    # dans le mode opératoire). Le haut de chaque tour est à la hauteur de guidage g au-dessus de la coque, au point le plus
    # haut de l'os dans la fente. La 1re fente sépare les deux moitiés ; en fermeture, la 2e est une fente fermée.
    profs = profondeurs_fentes(pr)
    kdir = (pr.get("charniere") or {}).get("direction")

    def charniere_dans(n):
        """Charnière projetée dans le plan de normale n, orientée comme la fente « face d'appui », et angle entre les deux."""
        ll0 = np.cross(n, perp(face, n))
        if kdir is None:
            return None, None
        k_ = np.asarray(kdir, float)
        k_ = k_ - (k_ @ n) * n
        if np.linalg.norm(k_) < 1e-6:
            return None, None
        k_ = unitaire(k_)
        k_ = k_ if k_ @ ll0 >= 0 else -k_
        return k_, angle_deg(k_, ll0)

    # une seule décision pour toutes les fentes (les tours d'un coin de fermeture restent parallèles) : si chaque fente
    # qui s'arrête à la charnière lui est presque parallèle (≤ 30°), toutes les fentes sont alignées sur la charnière
    # (elle est dans les deux plans d'un coin) ; sinon aucune (la profondeur donnée est alors celle du point le plus haut
    # de la charnière : la lame ne l'atteint pas ailleurs)
    proj = [charniere_dans(n) for _p, n in plans]
    a_ch = [a_ for (k_, a_), pf in zip(proj, profs) if pf == "charniere" and a_ is not None]
    aligner = bool(a_ch) and max(a_ch) <= 30.0
    tours = []
    for i, (p, n) in enumerate(plans):
        hh = perp(face, n)
        ll = np.cross(n, hh)
        k_, angle_ch = proj[i]
        alignee = False
        if aligner and k_ is not None:                  # fente parallèle à la charnière
            ll, hh, alignee = k_, np.cross(k_, n), True
        sec = section_os(poly, p, n, hh, ll, K)
        prof = profs[i] if i < len(profs) else "complete"
        if prof == "complete":                           # la lame traverse la corticale opposée
            h_stop = sec["hmin"]
        else:                                            # charnière : son point le plus haut sur la largeur de l'os
            h_stop = float((H - p) @ hh)
            if kdir is not None and not alignee and angle_ch is not None:
                kh, kl = float(k_ @ hh), float(k_ @ ll)
                if abs(kl) > 1e-6:
                    lH = float((H - p) @ ll)
                    h_stop = max(h_stop + (l_ - lH) * kh / kl for l_ in (sec["lmin"], sec["lmax"]))
        tours.append(dict(p=p, n=n, hh=hh, ll=ll, sec=sec, profondeur=prof, h_stop=h_stop, angle_charniere=angle_ch,
                          alignee_charniere=alignee, separation=(i == 0),
                          h_base=sec["hc"] + 0.5 * (sec["hmax"] - sec["hc"]), h_top=sec["hmax"] + J + E + Gd))

    def coins_boite(c, axes, demi):
        return np.array([c + sx * demi[0] * axes[0] + sy * demi[1] * axes[1] + sz * demi[2] * axes[2]
                         for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])

    for t in tours:
        s = t["sec"]
        t["axes"] = (t["n"], t["hh"], t["ll"])
        t["c"] = t["p"] + 0.5 * (t["h_base"] + t["h_top"]) * t["hh"] + 0.5 * (s["lmin"] + s["lmax"]) * t["ll"]
        t["demi"] = (Tt / 2, 0.5 * (t["h_top"] - t["h_base"]), 0.5 * (s["lmax"] - s["lmin"]) + 1 + W)
        # fente (trajet de la lame) : sous l'os jusqu'au-dessus de la tour, sur la longueur de la section + 1 mm
        bas = s["hmin"] - 5.0
        Lh = (t["h_top"] + 1.0) - bas
        t["fente"] = dict(largeur=ws, longueur=s["lmax"] - s["lmin"] + 2.0)
        t["boite_fente"] = (t["p"] + (bas + Lh / 2) * t["hh"] + 0.5 * (s["lmin"] + s["lmax"]) * t["ll"], t["axes"],
                            (ws / 2, Lh / 2, 0.5 * (s["lmax"] - s["lmin"]) + 1.0))
    # ponts : parois d'extrémité de la fente de séparation, en haut de la tour. Les boîtes débordent de la tour (vers
    # le haut et vers l'extérieur) : aucune de leurs faces ne coïncide avec une face de la tour (des faces presque
    # confondues laissent des facettes dégénérées qui rendent le STL non étanche une fois arrondi en float32)
    for t in tours:
        s_ = t["sec"]
        t["Hp"] = min(P.GUIDE_PONT_MM, t["h_top"] - t["h_base"])
        t["ponts"] = []
        for sg in (1.0, -1.0):
            l_c = (s_["lmax"] + 1.0 if sg > 0 else s_["lmin"] - 1.0) + sg * (W + 2.0) / 2
            t["ponts"].append((t["p"] + (t["h_top"] - t["Hp"] + (t["Hp"] + 3.0) / 2) * t["hh"] + l_c * t["ll"], t["axes"],
                               (Tt / 2 + 1.0, (t["Hp"] + 3.0) / 2, (W + 2.0) / 2)))
    t0_ = tours[0]
    s0 = t0_["sec"]
    Hp = t0_["Hp"]

    # zone d'appui (pour l'étendue de la grille) : échantillons entre les extrémités et dans le secteur
    a_p, a_d = np.mean([x["a"] for x in prox], 0), np.mean([x["a"] for x in dist], 0)
    c_p, c_d = perp(face, u), perp(face, vd)
    cote = (ech - Hs) @ nsep
    z_p = (cote < 1) & ((ech - P_haut) @ u > -MARGE - 1) & dans_secteur(ech, a_p, u, c_p, A + np.radians(10))
    z_d = (cote > -1) & ((ech - P_bas) @ vd < MARGE + 1) & dans_secteur(ech, a_d, vd, c_d, A + np.radians(10))
    R = base(face, b)
    pts_q = [(ech[z_p | z_d] - K) @ R.T]
    lo, hi = pts_q[0].min(0) - (J + E + 1.5), pts_q[0].max(0) + (J + E + 1.5)
    autres = [coins_boite(t["c"], t["axes"], t["demi"]) for t in tours]
    for x in broches:
        o = -x["d"]
        e1 = perp([1.0, 0, 0] if abs(o[0]) < 0.9 else [0, 1.0, 0], o)
        e2 = np.cross(o, e1)
        autres.append(np.array([x["a"] + tt * o + s1 * Rs * e1 + s2 * Rs * e2 for tt in (x["t_os"] - 4, x["t_haut"])
                                for s1 in (-1, 1) for s2 in (-1, 1)]))
    q_autres = (np.vstack(autres) - K) @ R.T
    lo = np.minimum(lo, q_autres.min(0)) - 2 * k
    hi = np.maximum(hi, q_autres.max(0)) + 2 * k
    h = P.GUIDE_PAS_MM
    nn = np.prod((hi - lo) / h + 1)
    if nn > P.GRILLE_MAX_NOEUDS:
        h *= (nn / P.GRILLE_MAX_NOEUDS) ** (1 / 3)
    gr = Grille(K, R, lo - 2 * h, hi + 2 * h, h)
    journal(f"[étape 7] guide de coupe : grille {gr.n[0]} × {gr.n[1]} × {gr.n[2]} ({np.prod(gr.n) / 1e6:.1f} M nœuds, "
            f"pas {h:.2f} mm), distance à l'os…")

    d, n_exact = distance_signee(gr, v, f, J + E + 1.0)
    # os voisins qui touchent la grille : distance signée (jeu dur JV) et échantillons ajoutés aux cartes de hauteur (le
    # guide ne passe sous un os voisin ni pendant la pose ni pendant le retrait des moitiés)
    lo_os, hi_os = boite_grille(gr)
    ech_ombre, d_voisins, vus = [ech], [], []
    for nom, vv, ff, m_ in voisins_proches(voisins, lo_os, hi_os):
        r_ = distance_voisin(gr, vv, ff, JV + 1.0)
        if r_ is None:
            continue
        d_voisins.append(r_)
        ech_ombre.append(echantillons(vv, ff[m_], P.GUIDE_PAS_MM))
        vus.append(nom)
    # espace entre l'os et chaque voisin : interdit au guide (voir EntreOs)
    entre = EntreOs(gr, gr.vers(ech), [gr.vers(e_) for e_ in ech_ombre[1:]])
    ech_q = gr.vers(np.vstack(ech_ombre))

    # coque : moitié proximale autour de l'axe proximal, moitié distale autour de l'axe distal (chevauchement 1 mm)
    s_sep = gr.plan(gr.vers(Hs), gr.vec(nsep))
    # extrémités de la coque : MARGE au-delà des broches extrêmes, mais jamais à moins de DISTANCE_MIN_ARTICULATION_MM
    # des extrémités (articulaires) de l'os, mesurées le long de l'axe proximal / distal
    s_haut = max(float((P_haut - K) @ u) - MARGE, float(((v - K) @ u).min()) + P.DISTANCE_MIN_ARTICULATION_MM)
    s_bas = max(float((P_bas - K) @ vd) + MARGE, 0.0)
    s_bas = min(s_bas, float(((v - K) @ vd).max()) - P.DISTANCE_MIN_ARTICULATION_MM)
    s_haut = min(s_haut, float((P_haut - K) @ u) - Rs - 1.0)          # la coque couvre toujours les manchons
    s_bas = max(s_bas, float((P_bas - K) @ vd) + Rs + 1.0)
    garde_art = {"proximal_mm": round(float((P_haut - K) @ u) - s_haut, 1), "distal_mm": round(s_bas - float((P_bas - K) @ vd), 1)}
    lim_p = np.maximum(np.float32(s_haut) - gr.plan(gr.vers(K), gr.vec(u)), s_sep - 0.5)
    lim_d = np.maximum(gr.plan(gr.vers(K), gr.vec(vd)) - np.float32(s_bas), -s_sep - 0.5)
    coque = d - np.float32(J + E)
    # cartilage articulaire : la coque s'arrête à J + E + GUIDE_MARGE_CARTILAGE_MM des sommets de cartilage
    n_art = 0
    cq = None
    if cart is not None and len(cart):
        cq = gr.vers(cart)
        cq = cq[np.all((cq > gr.lo - 8) & (cq < gr.lo + gr.h * (gr.n - 1) + 8), axis=1)]
        if len(cq):
            m_art = J + E + P.GUIDE_MARGE_CARTILAGE_MM
            sel = np.nonzero(coque < 0.5)
            dc, _ = cKDTree(cq).query(np.column_stack([gr.q[0][sel[0]], gr.q[1][sel[1]], gr.q[2][sel[2]]]),
                                      distance_upper_bound=m_art + 0.5, workers=FILS)
            dc = np.minimum(dc, 1e3).astype(np.float32)
            n_art = int(np.sum((dc < m_art) & (coque[sel] < 0)))
            coque[sel] = np.maximum(coque[sel], np.float32(m_art) - dc)
    F = np.minimum(np.maximum(np.maximum(coque, lim_p), champ_secteur(gr, gr.vers(a_p), gr.vec(u), gr.vec(c_p), A)),
                   np.maximum(np.maximum(coque, lim_d), champ_secteur(gr, gr.vers(a_d), gr.vec(vd), gr.vec(c_d), A)))
    del lim_p, lim_d, coque
    # tours (arêtes arrondies) et manchons, unis avec congés
    marge_sl = 2 * k + 2 * h
    r_tour = min(k, 0.6)
    for t in tours:
        sl = gr.tranche(gr.vers(coins_boite(t["c"], t["axes"], t["demi"])), marge_sl * 1.8)
        Ft = champ_boite_arrondie(gr, gr.vers(t["c"]), [gr.vec(a) for a in t["axes"]], t["demi"], r_tour, sl)
        F[sl] = smin(F[sl], Ft, k)
    for x, coins in zip(broches, autres[len(tours):]):
        sl = gr.tranche(gr.vers(coins), marge_sl * 1.8)
        Fm = champ_cylindre(gr, gr.vers(x["a"]), gr.vec(-x["d"]), Rs, x["t_os"] - 4, x["t_haut"], sl)
        F[sl] = smin(F[sl], Fm, k)
    # contraintes dures (champ G) : jeu J à l'os et JV aux os voisins partout ; pas de contre-dépouille pour la pose du
    # guide entier (face d'appui) ni pour le retrait de chaque moitié le long de ses broches
    G = np.float32(J + COMPENSATION_MM) - d
    del d
    for sl_v, d_v in d_voisins:
        G[sl_v] = np.maximum(G[sl_v], np.float32(JV + COMPENSATION_MM) - d_v)
    del d_voisins
    G = np.maximum(G, ombre(gr, ech_q, np.array([1.0, 0, 0]), J, alpha))
    distal = s_sep > 0
    if angle_deg(fp, face) > 0.5:
        G[~distal] = np.maximum(G[~distal], ombre(gr, ech_q, gr.vec(fp), J, alpha)[~distal])
    G[distal] = np.maximum(G[distal], ombre(gr, ech_q, gr.vec(fd), J, alpha)[distal])
    del distal
    # cartilage : aucune partie du guide (tours, pieds des manchons, bras compris) à moins de 1,5 mm de ses sommets (≈ 1 mm
    # de la surface articulaire, les sommets étant espacés de 1 à 2 mm)
    if cq is not None and len(cq):
        sel = np.nonzero((F < 1.0) & (G < 1.6))
        dc, _ = cKDTree(cq).query(np.column_stack([gr.q[0][sel[0]], gr.q[1][sel[1]], gr.q[2][sel[2]]]), distance_upper_bound=2.0, workers=FILS)
        G[sel] = np.maximum(G[sel], np.float32(1.5 + COMPENSATION_MM) - np.minimum(dc, 1e3).astype(np.float32))
    # espace entre l'os et un os voisin (fibula entre autres) : aucune matière (coque, tours, manchons, bras) ; le guide
    # reste sur la face accessible de l'os, l'espace du milieu reste libre pour le poser, le fixer et couper
    for k_, ch_ in entre.champs():
        G[:, :, k_] = np.maximum(G[:, :, k_], ch_.astype(np.float32))
    # manchons isolés du reste du guide (coque retirée au-dessus du cartilage ou d'un os voisin, par exemple sur un
    # fragment distal du fémur couvert par la trochlée) : un bras (capsule du rayon des manchons) relie le haut de chaque
    # manchon isolé au sommet de la tour de fente de sa moitié, au-dessus de l'os, puis les contraintes dures sont
    # réappliquées. Sans cela, la pièce isolée serait écartée et le guide n'aurait plus ces manchons.
    def isoles(Fx):
        plein = Fx < -0.5 * gr.h                           # col de moins d'un voxel : compté comme coupé
        for t in tours:                                    # fentes et dalle de séparation (moins les ponts) creusées
            c_, ax_, dm_ = t["boite_fente"]
            if t["separation"]:
                dm_ = (dm_[0], 400.0, 400.0)
            sl = gr.tranche(gr.vers(np.array([c_ + sx * dm_[0] * ax_[0] + sy * min(dm_[1], 200) * ax_[1] + sz * min(dm_[2], 200) * ax_[2]
                                              for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])), gr.h)
            vide = champ_boite(gr, gr.vers(c_), [gr.vec(a_) for a_ in ax_], dm_, sl) < gr.h / 2
            if t["separation"]:
                for cb, axb, dmb in t["ponts"]:
                    vide &= champ_boite(gr, gr.vers(cb), [gr.vec(a_) for a_ in axb], dmb, sl) > 0
            plein[sl] &= ~vide
        lab, _ = ndimage.label(plein)
        idx = lambda p_: tuple(int(np.clip(np.rint((q_ - lo_) / gr.h), 0, n_ - 1)) for q_, lo_, n_ in zip(gr.vers(p_), gr.lo, gr.n))
        # composante principale : celle des ponts (milieu de la paroi d'extrémité de la tour de séparation, dans la dalle)
        pont = lambda l_: t0_["p"] + (t0_["h_top"] - Hp / 2) * t0_["hh"] + l_ * t0_["ll"]
        principal = lab[idx(pont(s0["lmax"] + 1.0 + W / 2))] or lab[idx(pont(s0["lmin"] - 1.0 - W / 2))]
        relie = lambda p_: principal != 0 and lab[idx(p_)] == principal
        # 2e tour (coin de fermeture) : points de sa paroi distale à plusieurs hauteurs, hors de la dalle de séparation du
        # 1er plan ; coin si fin que les deux tours sont fusionnées (aucun point valable) : reliée de fait
        t2 = tours[-1]
        tour2 = True
        if len(tours) >= 2:
            p1_, n1_ = tours[0]["p"], tours[0]["n"]
            sondes = [t2["p"] + h_ * t2["hh"] + 0.5 * (t2["sec"]["lmin"] + t2["sec"]["lmax"]) * t2["ll"] + (ws / 2 + W / 2) * t2["n"]
                      for h_ in np.linspace(t2["sec"]["hmax"] + J + 1.0, t2["h_top"] - 1.0, 5)]
            sondes = [q_ for q_ in sondes if abs((q_ - p1_) @ n1_) > ws / 2 + 2 * gr.h]
            tour2 = not sondes or any(relie(q_) for q_ in sondes)
        return [x for x in broches if not relie(x["a"] - x["d"] * 0.5 * (x["t_os"] + J + E + x["t_haut"]))], tour2

    def ajouter_bras(p0, p1):
        sl = gr.tranche(gr.vers(np.array([p0, p1])), Rs + marge_sl * 1.8)
        F[sl] = smin(F[sl], champ_capsule(gr, gr.vers(p0), gr.vers(p1), Rs, sl), k)

    def bout_tour(t, l_, cote_n):
        """Point en haut de la tour t, à l'abscisse l_ (bornée à la tour), sur sa face du côté cote_n (± n)."""
        l_ = float(np.clip(l_, t["sec"]["lmin"] - 1.0 - W / 2, t["sec"]["lmax"] + 1.0 + W / 2))
        return t["p"] + (t["h_top"] - Rs) * t["hh"] + l_ * t["ll"] + cote_n * (Tt / 2) * t["n"]

    bras = []
    F_dur, n_fins = sans_parties_fines(gr, np.maximum(F, G), P.GUIDE_EPAISSEUR_MIN_MM)
    isol, tour2_ok = isoles(F_dur)
    if not tour2_ok:
        # coin de fermeture dont la coque entre les deux traits a disparu (2e tour isolée) : 2 bras par-dessus le coin, de
        # la face distale de la tour de séparation à la face proximale de la 2e tour, près des deux extrémités (hors du
        # trajet de la lame), 0,5 mm en deçà du bout des tours.
        t1, t2 = tours[0], tours[-1]
        for fin in ("lmax", "lmin"):
            sg = 1.0 if fin == "lmax" else -1.0
            ajouter_bras(bout_tour(t1, t1["sec"][fin] + sg * (0.5 + W - Rs), 1.0), bout_tour(t2, t2["sec"][fin] + sg * (0.5 + W - Rs), -1.0))
        bras.append("tour 2")
    for x in isol:
        i_b = 0 if x["fragment"] == "proximal" else len(tours) - 1
        t_b = tours[i_b]
        p0 = x["a"] - x["d"] * (x["t_haut"] - Rs)
        q_ = p0 - t_b["p"]
        cote_n = float(np.sign(q_ @ t_b["n"]) or 1.0)
        ajouter_bras(p0, bout_tour(t_b, q_ @ t_b["ll"], cote_n))
        bras.append(x["nom"])
    if bras:
        F_dur, n_fins = sans_parties_fines(gr, np.maximum(F, G), P.GUIDE_EPAISSEUR_MIN_MM)
    del G
    F = F_dur
    encore_isoles = []
    if bras:
        isol, tour2_ok = isoles(F)
        encore_isoles = [x["nom"] for x in isol] + ([] if tour2_ok else ["tour 2"])
    journal("[étape 7] isosurface et opérations booléennes exactes (fentes, trous, ponts, finitions)…")
    corps = isosurface(gr, F)
    del F

    # outils : trous de broches et chanfreins d'entrée (manchons, fentes)
    ch = float(P.GUIDE_CHANFREIN_MM)
    trous = [cylindre_m(x["a"], -x["d"], -60.0, x["t_haut"] + 2.0, rh) for x in broches]
    if ch > 0:
        trous += [cone_m(x["a"], -x["d"], x["t_haut"] - ch, x["t_haut"] + 1.0, rh, rh + ch + 1.0) for x in broches]
        trous += [chanfrein_fente(t, ws, ch) for t in tours]
    # pièces détachées : « fonctionnelles » si elles portent une partie GUIDANTE de tour de fente ou de manchon, c'est-à-
    # dire au-dessus de la coque (alerte) ; sinon îlots de coque isolés par le cartilage ou un os voisin, y compris au
    # pied d'une tour (patins d'appui sans fonction : simplement écartés)
    def tour_guidante(t):
        h0 = t["sec"]["hmax"] + J + E                     # haut de la coque au-dessus du point le plus haut de l'os
        if h0 >= t["h_top"] - 0.5:
            return boite_m(t["c"], t["axes"], t["demi"])
        return boite_m(t["p"] + 0.5 * (h0 + t["h_top"]) * t["hh"] + 0.5 * (t["sec"]["lmin"] + t["sec"]["lmax"]) * t["ll"],
                       t["axes"], (t["demi"][0], 0.5 * (t["h_top"] - h0), t["demi"][2]))
    tours_m = m3d.Manifold.batch_boolean([tour_guidante(t) for t in tours], m3d.OpType.Add)
    manchons_m = m3d.Manifold.batch_boolean([cylindre_m(x["a"], -x["d"], x["t_os"] + J + E, x["t_haut"], Rs) for x in broches],
                                            m3d.OpType.Add)

    # assemblage : la 1re fente coupe le guide en deux moitiés sur toute sa hauteur (dalle de l'épaisseur de la fente),
    # sauf aux 2 ponts ; la 2e fente d'un coin de fermeture est une fente fermée de la moitié distale
    t0_ = tours[0]
    coupes = [boite_m(*t["boite_fente"]) for t in tours if not t["separation"]]
    dalle = boite_m(t0_["p"] + (t0_["h_stop"] + 190.0) * t0_["hh"], t0_["axes"], (ws / 2, 200.0, 400.0))
    ponts_m = m3d.Manifold.batch_boolean([boite_m(*b_) for b_ in t0_["ponts"]], m3d.OpType.Add)
    outils = m3d.Manifold.batch_boolean(coupes + [dalle - ponts_m] + trous, m3d.OpType.Add)
    pieces = volume_pieces(corps - outils)
    guide = pieces[0]
    ecartees, ilots = [], []
    for p_ in pieces[1:]:
        vol = p_.volume()
        if vol < 1.0:
            continue
        utile = (p_ ^ tours_m).volume() > 5.0 or (p_ ^ manchons_m).volume() > 5.0
        (ecartees if utile else ilots).append(round(vol, 1))
    # les deux moitiés : ce qui reste du guide une fois les ponts coupés (sans facettes de volume nul)
    morceaux = [m_ for m_ in volume_pieces(guide - dalle) if m_.volume() > 1.0]
    m_p = min(morceaux, key=lambda m_: cote_plan(m_, Hs, nsep)) if morceaux else None
    m_d = max(morceaux, key=lambda m_: cote_plan(m_, Hs, nsep)) if morceaux else None
    # ordre de retrait : d'abord la moitié qui s'éloigne le plus vite de l'autre en glissant sur ses broches
    premiere = "distale" if float(fd @ nsep) >= -float(fp @ nsep) else "proximale"
    # correction réelle (trait de scie compensé en fermeture) : broches et os voisins après la correction, pour le guide
    # de réduction et l'os corrigé
    T_reel = transformation_reelle(pr, plans)
    broches_c = broches_apres(pr, broches, T_reel)
    voisins_c = [(n_, *voisin_corrige(n_, vv, ff, plans, T_reel)) for n_, vv, ff in voisins]
    geo = dict(K=K, u=u, vd=vd, b=b, H=H, fp=fp, fd=fd, face=face, nsep=nsep, Hs=Hs, plans=plans, broches=broches,
               tours=tours, ws=ws, rh=rh, Rs=Rs, Hp=Hp, J=J, E=E, gr=gr, n_exact=n_exact, ecartees=ecartees,
               poly=poly, etendue_coque=(float(s_haut), float(s_bas)), Tt=Tt,
               voxels_fins_retires=n_fins, garde_articulaire=garde_art, voisins_evites=vus, noeuds_coque_cartilage=n_art,
               bras=bras, manchons_isoles=encore_isoles, ilots=ilots,
               pieces=dict(proximal=m_p, distal=m_d if m_d is not m_p else None), n_morceaux=len(morceaux),
               premiere=premiere, r_tour=r_tour, chanfrein=ch, T=T_reel, broches_c=broches_c, voisins_c=voisins_c,
               T_prescrit=np.asarray(pr["correction"]["T_4x4"], float))
    return guide, [m_p, geo["pieces"]["distal"]], guide ^ dalle, geo


# --------------------------------------------------------------------------- os corrigé et guide de réduction
def os_corrige(man_os, plans, T):
    """Os après la correction : fragment proximal + fragment distal déplacé par T (coin retiré en fermeture, ouvert en
    ouverture). Chaque trait de scie enlève l'épaisseur de la lame, centrée sur son plan (T = transformation_reelle :
    en fermeture, les surfaces coupées se touchent)."""
    s2 = 0.5 * P.GUIDE_LAME_MM
    (p1, n1), (pl, nl) = plans[0], plans[-1]
    prox = man_os.trim_by_plane(tuple(-n1), float(-n1 @ p1) + s2)
    dist = man_os.trim_by_plane(tuple(nl), float(nl @ pl) + s2)
    return prox + dist.transform(np.asarray(T, float)[:3, :])


def voisin_corrige(nom, vv, ff, plans, T):
    """Os voisin après la correction planifiée : la fibula est ostéotomisée au niveau de la coupe et suit les deux
    fragments ; la rotule et les fabelles suivent le fragment distal (ou restent en place du côté proximal)."""
    T = np.asarray(T, float)
    p, n = plans[-1]
    if nom == "fibula":
        try:
            return depuis_manifold(os_corrige(vers_manifold(vv, ff), plans, T))
        except ValueError:
            pass
    if float(np.mean((vv - p) @ n)) > 0:
        return vv @ T[:3, :3].T + T[:3, 3], ff
    return vv, ff


def broches_apres(pr, broches, T=None):
    """Broches après la correction réelle T (transformation_reelle par défaut : trait de scie compensé en fermeture) :
    les distales suivent le fragment distal, les proximales ne bougent pas."""
    if T is None:
        T = transformation_reelle(pr, [(np.array(p_["point"], float), unitaire(p_["normale"])) for p_ in pr["plans_coupe"]])
    T = np.asarray(T, float)
    return [dict(x, a=appliquer(T, x["a"]), d=unitaire(T[:3, :3] @ x["d"])) if x["fragment"] == "distal" else dict(x)
            for x in broches]


def guide_reduction(pr, vc, fc, broches_c, journal=print, voisins_c=()):
    """Guide de réduction : barre (enveloppe convexe des 4 broches, vue le long des broches, épaissie du rayon des
    manchons) au-dessus de l'os corrigé et des os voisins corrigés, et 4 manchons parallèles avec butées sur l'os."""
    J, W, JV = P.GUIDE_JEU_MM, P.GUIDE_PAROI_MM, P.GUIDE_JEU_VOISIN_MM
    rh = (P.GUIDE_BROCHE_MM + P.GUIDE_JEU_BROCHE_MM) / 2
    Rs, k, alpha = rh + W, P.GUIDE_CONGE_MM, np.radians(P.GUIDE_DEPOUILLE_DEG)
    o = unitaire(-np.mean([x["d"] for x in broches_c], 0))
    u = unitaire(pr["guide"]["axe_os"])
    K = np.mean([x["a"] for x in broches_c], 0)
    R = base(o, u)
    aq = np.array([(x["a"] - K) @ R.T for x in broches_c])                 # broches dans le repère (o, e1, e2)
    poly2 = enveloppe_2d(aq[:, 1:])                                        # barre : enveloppe convexe des broches
    portee = float(np.max(np.linalg.norm(aq[:, 1:], axis=1))) + Rs + 20
    ech_os = echantillons(vc, fc[np.linalg.norm((vc[fc].mean(1) - K) @ R[1:].T, axis=1) < portee], P.GUIDE_PAS_MM)
    ech_l = [ech_os]
    for nom, vv, ff in voisins_c:
        m_ = np.linalg.norm((vv[ff].mean(1) - K) @ R[1:].T, axis=1) < portee
        if m_.any():
            ech_l.append(echantillons(vv, ff[m_], P.GUIDE_PAS_MM))
    ech = np.vstack(ech_l)
    q = (ech - K) @ R.T
    sous_barre = dist_polygone(q[:, 1:], poly2) < Rs + P.REDUCTION_ECART_MM   # os et voisins à portée de la barre
    t_barre = float(q[sous_barre, 0].max())
    for x in broches_c:
        rel = ech_os - x["a"]
        t = rel @ o
        rho = np.linalg.norm(rel - np.outer(t, o), axis=1)
        if not (rho < Rs).any():
            raise ValueError(f"broche {x.get('nom', '?')} hors de l'os après correction : guide de réduction impossible")
        x["t_os"] = float(((x["a"] - K) @ o) + t[rho < Rs].max())       # hauteur (repère K, o) de l'os sous le manchon
    t_b = t_barre + P.REDUCTION_ECART_MM
    t_hb = t_b + P.REDUCTION_BARRE_MM
    t_top = max(t_hb, max(x["t_os"] for x in broches_c) + P.REDUCTION_MANCHON_MM)
    lo = np.array([min(x["t_os"] for x in broches_c) - 6, aq[:, 1].min() - Rs - 2, aq[:, 2].min() - Rs - 2])
    hi = np.array([t_top + 1, aq[:, 1].max() + Rs + 2, aq[:, 2].max() + Rs + 2])
    h = P.GUIDE_PAS_MM
    gr = Grille(K, R, lo - 2 * h - k, hi + 2 * h + k, h)
    journal(f"[étape 7] guide de réduction : grille {gr.n[0]} × {gr.n[1]} × {gr.n[2]} ({np.prod(gr.n) / 1e6:.1f} M nœuds)…")
    d, _ = distance_signee(gr, vc, fc, J + 1.5)
    yq = np.stack(np.meshgrid(gr.q[1], gr.q[2], indexing="ij"), -1).reshape(-1, 2)
    ds = dist_polygone(yq, poly2).reshape(gr.n[1], gr.n[2]).astype(np.float32)
    t = gr.q[0][:, None, None]
    F = np.maximum(ds[None, :, :] - np.float32(Rs), np.maximum(np.float32(t_b) - t, t - np.float32(t_hb)))
    for x in broches_c:
        aq_ = gr.vers(x["a"])
        F = smin(F, champ_cylindre(gr, aq_, np.array([1.0, 0, 0]), Rs, x["t_os"] - 5 - aq_[0], t_top - aq_[0]), k)
    F = np.maximum(F, np.float32(J + COMPENSATION_MM) - d)
    del d
    lo_os, hi_os = boite_grille(gr)
    vus = []
    for nom, vv, ff, _m in voisins_proches(voisins_c, lo_os, hi_os):
        r_ = distance_voisin(gr, vv, ff, JV + 1.0)
        if r_ is not None:
            F[r_[0]] = np.maximum(F[r_[0]], np.float32(JV + COMPENSATION_MM) - r_[1])
            vus.append(nom)
    F = np.maximum(F, ombre(gr, gr.vers(ech), np.array([1.0, 0, 0]), J, alpha))
    corps = isosurface(gr, F)
    trous = m3d.Manifold.batch_boolean([cylindre_m(x["a"], o, -80.0, t_top - ((x["a"] - K) @ o) + 5, rh)
                                        for x in broches_c], m3d.OpType.Add)
    pieces = volume_pieces(corps - trous)
    geo = dict(o=o, K=K, t_b=t_b, t_hb=t_hb, t_top=t_top, t_barre=t_barre, Rs=Rs, rh=rh, gr=gr, voisins_evites=vus,
               barre_sommets=len(poly2), ecartees=[round(p_.volume(), 3) for p_ in pieces[1:]])
    return pieces[0], geo


# --------------------------------------------------------------------------- contrôles
def controles_coupe(pr, v, f, man_os, guide, moities, geo):
    J = geo["J"]
    gv, gf = depuis_manifold(guide)
    poly = geo["poly"]
    inter = float((guide ^ man_os).volume()) if man_os is not None else None
    dg = jeu_controle((v, f), gv, inter)
    tri = gv[gf]
    aires = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    appui = distance_exacte((v, f), tri.mean(1)) < J + 0.15
    # pièces après la coupe des ponts (moitiés proximale et distale) ; ordre et liberté de retrait : chaque moitié le
    # long de ses broches sans heurter l'os (lancer de rayons) ni l'autre moitié (balayage exact)
    m_prox, m_dist = geo["pieces"]["proximal"], geo["pieces"]["distal"]
    vit_p, vit_d = -float(geo["fp"] @ geo["nsep"]), float(geo["fd"] @ geo["nsep"])
    premiere = geo["premiere"]
    retrait, appui_m = {}, {}
    dist_os = DistanceSurface(v, f, zone=(gv.min(0) - 6, gv.max(0) + 6))
    for nom, m, r, axe in (("proximale", m_prox, geo["fp"], geo["u"]), ("distale", m_dist, geo["fd"], geo["vd"])):
        if m is None:
            continue
        mv, mf = depuis_manifold(m)
        touches, n = retrait_libre(poly, mv, r)
        autre = m_dist if nom == "proximale" else m_prox
        heurt = balayage(m, autre, r) if nom == premiere and autre is not None else 0.0
        retrait[nom] = {"direction": [round(float(x), 4) for x in r], "points_testes": n, "points_bloques": touches,
                        "heurte_autre_moitie_mm3": round(heurt, 3), "libre": touches == 0 and heurt < FROTTEMENT_MM3}
        # appui de la moitié seule (après la coupe des ponts, chaque moitié tient sur ses 2 broches) : surface au
        # contact de l'os et couverture angulaire autour de l'os (une moitié posée sur une crête bascule)
        t_ = mv[mf]
        a_ = 0.5 * np.linalg.norm(np.cross(t_[:, 1] - t_[:, 0], t_[:, 2] - t_[:, 0]), axis=1)
        c_ = t_.mean(1)
        contact = dist_os(c_) < J + 0.15
        c0 = perp(geo["face"], axe)
        q_ = c_[contact] - geo["K"]
        ang = np.degrees(np.arctan2(q_ @ np.cross(axe, c0), q_ @ c0))
        appui_m[nom] = {"surface_mm2": round(float(a_[contact].sum()), 1),
                        "couverture_deg": round(float(np.percentile(ang, 98) - np.percentile(ang, 2)), 1) if len(q_) > 10 else 0.0}
    # fentes : profondeur de lame (du haut de la tour à la charnière, ou à la corticale opposée en coupe complète),
    # guidage, épaisseur de matière entre deux fentes
    fentes = []
    for i, t in enumerate(geo["tours"]):
        kh = abs(unitaire(pr["charniere"]["direction"]) @ t["hh"])
        fentes.append({
            "plan": i + 1, "role": "séparation" if t["separation"] else "coupe",
            "largeur_mm": round(t["fente"]["largeur"], 3), "longueur_mm": round(t["fente"]["longueur"], 2),
            "guidage_mm": round(t["h_top"] - t["sec"]["hmax"] - J, 2),
            "inclinaison_max_lame_deg": round(float(np.degrees(np.arctan(P.GUIDE_JEU_FENTE_MM / (t["h_top"] - t["sec"]["hmax"] - J)))), 2),
            "profondeur": t["profondeur"],
            "arret_lame": "corticale opposée (traversée)" if t["profondeur"] == "complete" else "charnière",
            "profondeur_lame_mm": round(t["h_top"] - t["h_stop"], 1),       # du haut de la tour à l'arrêt de la lame
            "fente_parallele_charniere": bool(t["alignee_charniere"]),
            "charniere_parallele_a_la_fente_deg": round(float(np.degrees(np.arcsin(min(1.0, kh)))), 2),
            "chanfrein_entree_mm": round(geo["chanfrein"], 2),
        })
    epaisseur_coin = None
    if len(geo["plans"]) == 2:
        t1, t2 = geo["tours"]
        hmax = max(t1["sec"]["hmax"], t2["sec"]["hmax"])
        ang = np.radians(angle_deg(t1["n"], t2["n"]))
        epaisseur_coin = round(float(2 * hmax * np.tan(ang / 2) - geo["ws"]), 2)
    # broches : écart aux plans de coupe, aux extrémités de l'os, angle entre les paires
    br = []
    s_u = (v - geo["K"]) @ geo["u"]
    s_v = (v - geo["K"]) @ geo["vd"]
    for x in geo["broches"]:
        o = -x["d"]
        seg = [x["a"] + x["t_sortie"] * o, x["a"] + x["t_os"] * o]
        dmin = min(abs(float((q - p) @ n)) for p, n in geo["plans"] for q in seg)
        croise = any(np.sign((seg[0] - p) @ n) != np.sign((seg[1] - p) @ n) for p, n in geo["plans"])
        bout = float((x["a"] - geo["K"]) @ geo["u"] - s_u.min()) if x["fragment"] == "proximal" \
            else float(s_v.max() - (x["a"] - geo["K"]) @ geo["vd"])
        # manchon présent dans le guide final : matière dans la couronne du manchon, au-dessus de la coque
        t0_m, t1_m = x["t_os"] + geo["J"] + geo["E"], x["t_haut"] - 0.5
        couronne = cylindre_m(x["a"], o, t0_m, t1_m, geo["Rs"] - 0.3, 48) - cylindre_m(x["a"], o, t0_m - 1, t1_m + 1, geo["rh"] + 0.3, 48)
        plein_m = float((guide ^ couronne).volume()) / max(couronne.volume(), 1e-9) if t1_m > t0_m + 0.5 else 1.0
        # lame contre broche : la broche (de sa pointe au haut de son manchon) doit rester hors du trajet de la lame
        trajet = x["a"] + np.linspace(x["t_sortie"] - 5.0, x["t_haut"], 120)[:, None] * o
        d_fente = min(float(dist_boite(trajet, *t["boite_fente"]).min()) for t in geo["tours"]) - geo["rh"]
        br.append({"nom": x["nom"], "fragment": x["fragment"], "point_axe": [round(float(c), 3) for c in x["a"]],
                   "direction": [round(float(c), 5) for c in x["d"]],
                   "entree_os": [round(float(c), 3) for c in seg[1]], "sortie_os": [round(float(c), 3) for c in seg[0]],
                   "haut_manchon": [round(float(c), 3) for c in x["a"] + x["t_haut"] * o],
                   "distance_plan_coupe_mm": round(dmin - geo["rh"], 2), "traverse_un_plan": bool(croise),
                   "distance_extremite_os_mm": round(bout, 1),
                   "trop_pres_articulation": bout < P.DISTANCE_MIN_ARTICULATION_MM,
                   "distance_trajet_lame_mm": round(d_fente, 2), "manchon_plein": round(plein_m, 3),
                   "hauteur_manchon_mm": round(float(x["t_haut"] - x["t_os"]), 1)})
    dp = [x["d"] for x in geo["broches"] if x["fragment"] == "proximal"]
    dd = [x["d"] for x in geo["broches"] if x["fragment"] == "distal"]
    return {
        "jeu_demande_mm": J, "jeu_minimal_mesure_mm": round(float(dg.min()), 3),
        "sommets_trop_proches": int(np.sum(dg < J - 0.05)),
        "volume_interpenetration_mm3": round(inter, 4) if inter is not None else None,
        "surface_appui_mm2": round(float(aires[appui].sum()), 1),
        "pieces_ecartees_mm3": geo["ecartees"],
        "moities_apres_coupe_des_ponts": geo["n_morceaux"], "pieces_attendues": 2,
        "ordre_retrait": [premiere, "proximale" if premiere == "distale" else "distale"],
        "vitesse_separation": {"proximale": round(vit_p, 4), "distale": round(vit_d, 4)},
        "retrait": retrait, "appui_moities": appui_m, "fentes": fentes, "epaisseur_entre_fentes_mm": epaisseur_coin,
        "bras_ajoutes": geo["bras"], "manchons_isoles": geo["manchons_isoles"], "ilots_coque_ecartes_mm3": geo["ilots"],
        "broches": br,
        "angle_paires_broches_deg": round(angle_deg(np.mean(dp, 0), np.mean(dd, 0)), 3),
        "parallelisme_paire_proximale_deg": round(max(angle_deg(dp[0], x) for x in dp), 4),
        "parallelisme_paire_distale_deg": round(max(angle_deg(dd[0], x) for x in dd), 4),
        "inclinaison_max_broche_deg": round(float(np.degrees(np.arctan(P.GUIDE_JEU_BROCHE_MM / (P.GUIDE_EPAISSEUR_MM + P.GUIDE_GUIDAGE_MM)))), 2),
        "_moities": (m_prox, m_dist),
    }


def balayage(mobile, fixe, direction, longueur=30.0):
    """Volume (mm³) de la plus grande intersection de la pièce `mobile`, glissée le long de `direction` (0,25 à 30 mm),
    avec la pièce `fixe` : 0 si elle sort (ou entre) sans la heurter."""
    d_ = unitaire(direction)
    return max(float((mobile.translate(tuple(s * d_)) ^ fixe).volume()) for s in (0.25, 0.5, 1, 2, 4, 8, 16, longueur))


def controles_voisins(guide, geo, voisins, cart):
    """Guide de coupe et broches contre les os voisins et le cartilage, fibula à ostéotomiser."""
    gv, gf = depuis_manifold(guide)
    lo, hi = gv.min(0) - 10, gv.max(0) + 10
    rp, Rs = P.GUIDE_BROCHE_MM / 2, geo["Rs"]
    out = {"voisins": {}, "cartilage": None, "broches": {}, "fibula_a_osteotomiser": False}
    dist_v = {}
    for nom, vv, ff in voisins:
        ds = DistanceSurface(vv, ff, zone=(lo, hi))
        dist_v[nom] = ds
        dmin = float(ds(gv).min())
        vol = None
        if np.isfinite(dmin) and dmin < 3:
            try:
                vol = round(float((guide ^ vers_manifold(vv, ff)).volume()), 3)
            except ValueError:
                vol = None
        out["voisins"][nom] = {"distance_guide_mm": round(dmin, 2) if np.isfinite(dmin) else None, "interpenetration_mm3": vol}
    arbre_c = None
    if cart is not None and len(cart):
        cz = cart[np.all((cart > lo) & (cart < hi), axis=1)]
        dc = float(DistanceSurface(gv, gf, zone=(cz.min(0) - 6, cz.max(0) + 6))(cz).min()) if len(cz) else np.inf
        out["cartilage"] = {"distance_guide_mm": round(dc, 2) if np.isfinite(dc) else None}
        arbre_c = cKDTree(cart)
    for x in geo["broches"]:
        o = -x["d"]
        pointe, entree, haut = (x["a"] + t_ * o for t_ in (x["t_sortie"] - 5.0, x["t_os"], x["t_haut"]))
        seg_b = pointe + np.linspace(0, 1, 80)[:, None] * (entree - pointe)        # broche dans l'os (et sa pointe)
        seg_m = entree + np.linspace(0, 1, 40)[:, None] * (haut - entree)          # manchon du guide
        r = {}
        for nom, ds in dist_v.items():
            r[nom] = {"axe_broche_mm": round(float(ds(seg_b).min()), 2), "axe_manchon_mm": round(float(ds(seg_m).min()), 2)}
        if arbre_c is not None:
            r["cartilage"] = {"axe_broche_mm": round(float(arbre_c.query(seg_b)[0].min()), 2),
                              "axe_manchon_mm": round(float(arbre_c.query(seg_m)[0].min()), 2)}
        out["broches"][x["nom"]] = r
    # fibula coupée par un plan de coupe près de l'ostéotomie : à ostéotomiser (sinon elle bloque la correction)
    for nom, vv, ff in voisins:
        if nom != "fibula":
            continue
        pres = vv[np.linalg.norm(vv - geo["K"], axis=1) < 60]
        for p_, n_ in geo["plans"]:
            c_ = (pres - p_) @ n_
            if len(c_) and c_.min() < 0 < c_.max():
                out["fibula_a_osteotomiser"] = True
    out["limites"] = {"guide_voisin_mm": P.GUIDE_JEU_VOISIN_MM, "broche_voisin_axe_mm": round(rp + 0.7, 2),
                      "manchon_voisin_axe_mm": round(Rs + 0.5, 2), "broche_cartilage_axe_mm": 3.0,
                      "manchon_cartilage_axe_mm": round(Rs + 0.5, 2), "guide_cartilage_mm": 1.0}
    return out


def controles_reduction(red, vc, fc, broches_c, geo, man_c=None, voisins_c=()):
    rv, _ = depuis_manifold(red)
    inter = float((red ^ man_c).volume()) if man_c is not None else None
    dr = jeu_controle((vc, fc), rv, inter)
    loin = np.ones(len(rv), bool)
    for x in broches_c:
        rel = rv - x["a"]
        t = rel @ geo["o"]
        loin &= np.linalg.norm(rel - np.outer(t, geo["o"]), axis=1) > geo["Rs"] + 0.2
    dirs = [unitaire(x["d"]) for x in broches_c]
    lo, hi = rv.min(0) - 8, rv.max(0) + 8
    vois = {}
    for nom, vv, ff in voisins_c:
        dmin = float(DistanceSurface(vv, ff, zone=(lo, hi))(rv).min())
        vois[nom] = {"distance_guide_mm": round(dmin, 2) if np.isfinite(dmin) else None}
    return {
        "voisins": vois,
        "jeu_minimal_mesure_mm": round(float(dr.min()), 3),
        "volume_interpenetration_mm3": round(inter, 4) if inter is not None else None,
        "distance_barre_os_mm": round(float(dr[loin].min()), 2) if loin.any() else None,
        "ecart_demande_mm": P.REDUCTION_ECART_MM,
        "parallelisme_manchons_deg": round(max(angle_deg(dirs[0], x) for x in dirs), 5),
        "longueur_broche_hors_os_min_mm": round(float(geo["t_top"] - min(x["t_os"] for x in broches_c) + 5), 1),
        "pieces_ecartees_mm3": geo["ecartees"],
    }


# --------------------------------------------------------------------------- mode opératoire
def _fr(x, d=1):
    """Nombre à la française (virgule décimale) pour les textes destinés au chirurgien."""
    return f"{float(x):.{d}f}".replace(".", ",")


def protocole(pr, cc, cv=None, cr=None):
    """Mode opératoire du chirurgien. cc : contrôles du guide de coupe ; cv : os voisins ; cr : contrôles du guide de
    réduction (None s'il n'a pas pu être construit)."""
    st = pr["strategie"]
    kind = st["type_coin"]
    derot = float(pr.get("correction", {}).get("derotation_deg", 0) or 0)
    fentes = cc["fentes"]
    p1, p2 = cc["ordre_retrait"]
    abord = st.get("abord")
    noms = {fr_: [x["nom"] for x in cc["broches"] if x["fragment"] == fr_] for fr_ in ("proximal", "distal")}
    n_tot = len(cc["broches"])

    def groupe(fr_):
        n = len(noms[fr_])
        return f"les {n} broches {fr_}es ({', '.join(noms[fr_])})" if n > 1 else f"la broche {fr_}e ({noms[fr_][0]})"

    lignes = []
    if abord:
        lignes.append(f"Abord {abord} : exposer la face d'appui de l'os sur toute la longueur du guide de coupe.")
    elif st.get("abord_non_usuel"):
        lignes.append("Abord NON USUEL (face du coin hors des abords habituels) : exposer la face d'appui indiquée ; "
                      "écarter ou ostéotomiser l'os voisin éventuel, protéger les structures de ce côté.")
    else:
        lignes.append("Abord : exposer la face d'appui de l'os sur toute la longueur du guide de coupe.")
    lignes.append("Poser le guide de coupe : il ne s'emboîte que dans une seule position ; vérifier qu'il ne bascule pas. "
                  f"Forer {groupe('proximal')}, puis {groupe('distal')}, à travers les manchons.")
    for i, x in enumerate(fentes):
        nom_f = f"la fente {i + 1}" if len(fentes) > 1 else "la fente"
        D = _fr(x["profondeur_lame_mm"], 1)
        if x["profondeur"] == "complete":
            lignes.append(f"Couper par {nom_f} sur toute l'épaisseur de l'os (la lame traverse la corticale opposée à {D} mm "
                          "du haut de la tour) ; protéger les tissus mous de l'autre côté de l'os (écarteur de Hohmann).")
        else:
            lignes.append(f"Couper par {nom_f} jusqu'à la charnière, à {D} mm du haut de la tour (repérer cette profondeur "
                          "sur la lame) : la corticale opposée est conservée.")
    lignes.append(f"Couper les 2 ponts (aux deux bouts de {'la fente 1' if len(fentes) > 1 else 'la fente'}) au ras des "
                  "moitiés, à la pince coupe-broche.")
    lignes.append(f"Retirer la moitié {p1} en la faisant glisser le long de ses broches, puis la moitié {p2}"
                  + (" ; retirer le coin osseux." if kind == "fermeture" else "."))
    if cv and cv.get("fibula_a_osteotomiser"):
        lignes.append("Ostéotomiser la fibula au niveau de la coupe tibiale (ostéotome ou scie, par un court abord latéral) : "
                      "intacte, elle empêcherait la correction.")
    geste = "Fermer le coin jusqu'au contact des surfaces coupées" if kind == "fermeture" else "Ouvrir le coin"
    if abs(derot) >= 1:
        geste += f" et faire tourner le fragment distal de {_fr(derot)}° autour de son axe (dérotation)"
    if st.get("regle_paley") == 2:
        geste += (f", en laissant le fragment distal glisser de {_fr(st.get('translation_osteotomie_mm') or 0)} mm le long de "
                  "la coupe (règle 2 de Paley : coupe hors du CORA, cette translation réaligne les axes)")
    lignes.append(geste + f", jusqu'à ce que les {n_tot} broches soient parallèles.")
    if cr is not None:
        lignes.append(f"Enfiler le guide de réduction sur les {n_tot} broches jusqu'au contact de ses manchons avec l'os : il "
                      "tient les fragments dans la position planifiée (angle, torsion et translation).")
        if min(len(v_) for v_ in noms.values()) == 1:
            lignes.append("Un fragment ne porte qu'une broche : il peut encore tourner autour d'elle ; vérifier que les manchons "
                          "du guide de réduction touchent bien l'os de ce fragment avant de fixer.")
        lignes.append("Fixer (plaque) ; retirer le guide de réduction et les broches.")
    else:
        lignes.append("Fixer (plaque) en gardant les broches parallèles ; retirer les broches.")
    return lignes


# --------------------------------------------------------------------------- aperçu
def apercu(chemin, v, f, moities, ponts, vc, fc, red, broches, broches_c, geo, voisins=(), voisins_c=()):
    import pyvista as pv
    def pvm(vv, ff):
        return pv.PolyData(vv, np.column_stack([np.full(len(ff), 3), ff]).ravel())
    pl = pv.Plotter(off_screen=True, shape=(1, 3), window_size=(1800, 760), border=False)
    K, u, fp = geo["K"], geo["u"], geo["face"]
    side = np.cross(u, fp)
    def cadre(*mans):                           # boîte englobante des pièces (+ 6 mm) pour cadrer chaque vue
        vv = np.vstack([depuis_manifold(m_)[0] for m_ in mans if m_ is not None])
        lo, hi = vv.min(0) - 6, vv.max(0) + 6
        return [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]]
    bornes = [cadre(*moities), cadre(*moities), cadre(red) if red is not None else None]
    for col, (titre, cam) in enumerate((("Guide de coupe : vue de la face d'appui", fp),
                                        ("Guide de coupe : vue de profil", side + 0.25 * fp),
                                        ("Après correction : guide de réduction", fp + 0.6 * side))):
        pl.subplot(0, col)
        pl.add_text(titre, font_size=10)
        if col < 2:
            pl.add_mesh(pvm(v, f), color="#e8dcc4", smooth_shading=True)
            for _n, vv, ff in voisins:
                pl.add_mesh(pvm(vv, ff), color="#b9b4ac", opacity=0.6, smooth_shading=True)
            for m_, c_ in zip(moities, ("#2f6db5", "#2aa198")):
                if m_ is not None:
                    pl.add_mesh(pvm(*depuis_manifold(m_)), color=c_, smooth_shading=True)
            if ponts is not None and not ponts.is_empty():
                pl.add_mesh(pvm(*depuis_manifold(ponts)), color="#e8822b")
            for x in broches:
                o = -x["d"]
                pl.add_mesh(pv.Cylinder(center=x["a"] + o * (x["t_haut"] + x["t_sortie"] - 10) / 2, direction=o, radius=0.8,
                                        height=x["t_haut"] - x["t_sortie"] + 10), color="#9aa0a6")
        elif red is not None:
            pl.add_mesh(pvm(vc, fc), color="#e8dcc4", smooth_shading=True)
            for _n, vv, ff in voisins_c:
                pl.add_mesh(pvm(vv, ff), color="#b9b4ac", opacity=0.6, smooth_shading=True)
            pl.add_mesh(pvm(*depuis_manifold(red)), color="#8e44ad", smooth_shading=True)
            for x in broches_c:
                o = -x["d"]
                pl.add_mesh(pv.Cylinder(center=x["a"] + o * 15, direction=o, radius=0.8, height=60), color="#9aa0a6")
        pl.camera.focal_point = K
        pl.camera.position = K + 300 * unitaire(cam)
        pl.camera.up = -u
        if bornes[col] is not None:
            pl.reset_camera(bounds=bornes[col])
        pl.camera.zoom(1.15)
    pl.screenshot(str(chemin))
    pl.close()


# --------------------------------------------------------------------------- dimensions du guide générique
def dimensions_guide(pr, geo, cc, guide, red=None, gred=None, broches_c=()):
    """Dimensions du guide générique pour CE cas : les paramètres (les mêmes pour tous les cas, sauf choix contraire) et
    les dimensions qui découlent de l'os du scanner (fentes, tours, manchons, broches, coque, encombrement). Repère du
    guide : axe de l'os (vers distal), côté (axe × face d'appui), face d'appui (vers l'extérieur)."""
    u, face = geo["u"], unitaire(geo["face"])
    cote = unitaire(np.cross(u, face))

    def encombrement(man):
        vv, _ = depuis_manifold(man)
        q = (vv - geo["K"]) @ np.vstack([u, cote, face]).T
        return {"longueur_axe_os_mm": round(float(np.ptp(q[:, 0])), 1), "largeur_mm": round(float(np.ptp(q[:, 1])), 1),
                "hauteur_mm": round(float(np.ptp(q[:, 2])), 1)}

    fentes = []
    for i, t in enumerate(geo["tours"]):
        s_ = t["sec"]
        fentes.append({"fente": i + 1, "role": "séparation" if t["separation"] else "coupe",
                       "largeur_mm": round(geo["ws"], 2), "longueur_mm": round(t["fente"]["longueur"], 1),
                       "largeur_os_mm": round(s_["lmax"] - s_["lmin"], 1),
                       "hauteur_tour_mm": round(t["h_top"] - t["h_base"], 1),
                       "guidage_mm": round(t["h_top"] - s_["hmax"] - geo["J"], 1), "epaisseur_tour_mm": round(geo["Tt"], 2),
                       "arret_lame": "corticale opposée" if t["profondeur"] == "complete" else "charnière",
                       "profondeur_lame_mm": round(t["h_top"] - t["h_stop"], 1)})
    plans = geo["plans"]
    broches = []
    for x in geo["broches"]:
        broches.append({"nom": x["nom"], "fragment": x["fragment"],
                        "distance_coupe_mm": round(min(abs(float((x["a"] - p) @ n)) for p, n in plans), 1),
                        "hauteur_manchon_mm": round(float(x["t_haut"] - x["t_os"]), 1)})
    ecarts = {}
    for fr_ in ("proximal", "distal"):
        g_ = [x for x in geo["broches"] if x["fragment"] == fr_]
        if len(g_) >= 2:
            ecarts[fr_] = round(float(np.linalg.norm(g_[0]["a"] - g_[1]["a"])), 1)
    s_haut, s_bas = geo["etendue_coque"]
    d = {
        "parametres": valeurs_parametres(),
        "fentes": fentes,
        "angle_entre_fentes_deg": round(angle_deg(plans[0][1], plans[-1][1]), 2) if len(plans) == 2 else 0.0,
        "manchon_diametre_exterieur_mm": round(2 * geo["Rs"], 2), "trou_broche_mm": round(2 * geo["rh"], 2),
        "broches": broches, "ecart_broches_mm": ecarts,
        "coque": {"longueur_mm": round(s_bas - s_haut, 1), "epaisseur_mm": round(geo["E"], 2), "jeu_mm": round(geo["J"], 2),
                  "secteur_deg": round(float(P.GUIDE_SECTEUR_DEG), 1)},
        "ponts": {"nombre": 2, "section_mm": [round(float(P.GUIDE_PAROI_MM), 2), round(float(geo["Hp"]), 2)]},
        "guide_coupe": encombrement(guide),
        "formules": {
            "longueur de fente": "largeur de l'os dans le plan de coupe + 2 mm",
            "haut de tour": "os + j + e + g (au point le plus haut de l'os dans la fente)",
            "profondeur de lame": "du haut de la tour à la charnière, ou à la corticale opposée (coupe complète)",
            "épaisseur de tour": "s + js + 2 p",
            "diamètre du manchon": "Øb + jb + 2 p",
            "longueur de coque": "de la broche la plus proximale − m à la plus distale + m (≥ 10 mm des extrémités articulaires)",
            "ponts": "p × hp, en haut des parois d'extrémité de la 1re fente",
        },
    }
    if red is not None and gred is not None:
        d["guide_reduction"] = {**encombrement(red), "barre_epaisseur_mm": round(float(P.REDUCTION_BARRE_MM), 2),
                                "manchon_longueur_mm": round(float(P.REDUCTION_MANCHON_MM), 2),
                                "ecart_os_mm": round(float(P.REDUCTION_ECART_MM), 2), "nombre_manchons": len(broches_c)}
    return d


# --------------------------------------------------------------------------- programme principal
def generer(prescription, maillage_os, dossier, journal=print, image=True, voisins=None, articulaire=None):
    """Construit et contrôle les deux guides (coupe, réduction) ; écrit les fichiers dans `dossier`. Renvoie le dictionnaire guide.json.
    voisins : [(nom, sommets, triangles)] os voisins dans le repère de l'os planifié (fibula ; rotule et fabelles pour le
    fémur), à éviter par les guides ; articulaire : cartilage articulaire, une valeur par sommet de l'os (uint8 ≥ 128,
    booléen ou réel ≥ 0,5). Les dimensions du guide générique choisies pour ce cas (prescription > parametres_guide)
    s'appliquent le temps de la construction."""
    pr = json.loads(Path(prescription).read_text(encoding="utf-8")) if not isinstance(prescription, dict) else prescription
    with parametres_du_cas(pr) as pc:
        return _generer(pr, maillage_os, dossier, journal, image, voisins, articulaire, pc)


class GuideImpossible(ValueError):
    """Le guide de coupe ne peut pas être posé par la face prescrite (message pour le chirurgien)."""


def verifier_abord(pr):
    """Un coin dont la face d'entrée de la lame est derrière un os voisin (la fibula, en général : coin de fermeture d'un
    varus du tibia) n'est pas réalisable par un abord usuel : un guide posé sur cette face occuperait l'espace entre
    l'os et le voisin, où l'on ne peut ni le glisser, ni le fixer, ni couper. Pas de guide : GuideImpossible, avec le
    type de coin que la planification conseille."""
    st = pr.get("strategie") or {}
    voisin = st.get("voisin_sur_lame")
    if not (st.get("abord_non_usuel") and voisin):
        return
    reco = (st.get("recommandation") or {}).get("type_coin")
    conseil = ((f"choisir le coin d'{reco}" if reco == "ouverture" else f"choisir le coin de {reco}")
               + " (conseillé par la planification)") if reco and reco != st.get("type_coin") \
        else "changer de type de coin ou de niveau de coupe"
    coin = "de fermeture" if st.get("type_coin") == "fermeture" else "d'ouverture"
    raise GuideImpossible(
        f"guide de coupe non construit : pour ce coin {coin}, la lame doit entrer par une face où {voisin} est sur son "
        f"trajet, et le guide occuperait l'espace entre l'os et {voisin} : on ne pourrait ni l'y glisser, ni le fixer, ni "
        f"couper. Ce coin n'est pas réalisable par un abord usuel : {conseil}.")


def _generer(pr, maillage_os, dossier, journal, image, voisins, articulaire, pc):
    appliques = pc.appliques
    t_debut = time.time()
    verifier_abord(pr)
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    # résultats d'une construction précédente dans ce dossier (y compris les pièces des anciennes versions : pièce du
    # coin, moitiés verrouillées…) : supprimés, pour que l'application n'affiche que ceux de cette construction. La
    # prescription, l'os et les voisins écrits par le serveur ne sont pas touchés.
    for motif in ("guide_coupe*.stl", "guide_coupe*.bin", "guide_reduction.stl", "guide_reduction.bin", "verrou_*.bin",
                  "os_corrige.stl", "os_corrige.bin", "guide.json", "guide.png", "plan_guide.*", "plan_generique.*"):
        for ancien in dossier.glob(motif):
            ancien.unlink(missing_ok=True)
    v, f = lire_maillage(maillage_os) if not isinstance(maillage_os, tuple) else maillage_os
    try:
        man_os = vers_manifold(v, f)
    except ValueError as e:
        journal(f"[étape 7] os : {e} (contrôles booléens limités)")
        man_os = None

    voisins = [(str(n_), np.asarray(vv, float), np.asarray(ff, np.int64)) for n_, vv, ff in (voisins or []) if len(ff)]
    m_cart = masque_cartilage(articulaire, len(v))
    cart = v[m_cart] if m_cart is not None else None
    guide, moities, ponts, geo = guide_coupe(pr, v, f, journal, voisins, cart)
    guide, n_jeu = assurer_jeu(guide, v, f, geo["J"])
    guide, gv, gf, etat = exporter(guide, dossier / "guide_coupe.stl", "CT-CORA3D guide de coupe")
    etat["sommets_repousses_au_jeu"] = n_jeu
    journal("[étape 7] contrôles du guide de coupe…")
    cc = controles_coupe(pr, v, f, man_os, guide, moities, geo)
    cc.update(etat)
    m_prox, m_dist = cc.pop("_moities")
    cv = controles_voisins(guide, geo, voisins, cart)
    ecrire_bin(dossier / "guide_coupe.bin", gv, gf)
    for nom, m_ in (("guide_coupe_proximal", m_prox), ("guide_coupe_distal", m_dist), ("guide_coupe_ponts", ponts)):
        if m_ is not None and not m_.is_empty():
            ecrire_bin(dossier / f"{nom}.bin", *depuis_manifold(m_))
    fichiers = ["guide_coupe.stl"]
    rs = (pr.get("os_segmente") or {}).get("repere_scanner")
    if rs:                                     # même guide dans le repère du scanner (superposable au STL de l'os)
        M = np.asarray(rs["os_vers_scanner"], float)
        sv = gv @ M[:3, :3].T + M[:3, 3]
        ecrire_stl(dossier / "guide_coupe_scanner.stl", sv, gf[:, ::-1] if np.linalg.det(M[:3, :3]) < 0 else gf,
                   "CT-CORA3D guide de coupe (repere scanner)")
        fichiers.append("guide_coupe_scanner.stl")

    # os corrigé (correction réelle : trait de scie compensé en fermeture), puis guide de réduction séparé
    T = geo["T"]
    red = vc = fc = man_c = gred = None
    cr = None
    broches_c, voisins_c = geo["broches_c"], geo["voisins_c"]
    raison_reduction = "il faut au moins 1 broche par fragment et un os manifold"
    nb_fr = {fr: sum(x["fragment"] == fr for x in geo["broches"]) for fr in ("proximal", "distal")}
    if man_os is not None:
        man_c = os_corrige(man_os, geo["plans"], T)
        vc, fc = depuis_manifold(man_c)
        ecrire_stl(dossier / "os_corrige.stl", vc, fc, "CT-CORA3D os corrige (prevision)")
        ecrire_bin(dossier / "os_corrige.bin", vc, fc)
        fichiers.append("os_corrige.stl")
    if man_c is not None and min(nb_fr.values()) >= 1:
        try:
            red, gred = guide_reduction(pr, vc, fc, broches_c, journal, voisins_c)
        except ValueError as exc:
            red = None
            journal(f"[étape 7] {exc}")
            raison_reduction = str(exc)
        if red is not None:
            red, n_jeu_r = assurer_jeu(red, vc, fc, P.GUIDE_JEU_MM)
            red, rv, rf, etat = exporter(red, dossier / "guide_reduction.stl", "CT-CORA3D guide de reduction")
            etat["sommets_repousses_au_jeu"] = n_jeu_r
            cr = controles_reduction(red, vc, fc, broches_c, gred, man_c, voisins_c)
            cr.update(etat)
            ecrire_bin(dossier / "guide_reduction.bin", rv, rf)
            cr["broches_apres_correction"] = [{"nom": x["nom"], "point_axe": [round(float(c), 3) for c in x["a"]],
                                               "direction": [round(float(c), 5) for c in x["d"]]} for x in broches_c]
            fichiers.append("guide_reduction.stl")
    tours = geo["tours"]

    alertes = []
    if cc["jeu_minimal_mesure_mm"] < geo["J"] - 0.05 or (cc["volume_interpenetration_mm3"] or 0) > 0.01:
        alertes.append("le guide de coupe touche l'os (jeu inférieur au jeu demandé) : NE PAS IMPRIMER")
    if not cc["etanche_stl"]:
        alertes.append("STL du guide de coupe non étanche")
    if cc["moities_apres_coupe_des_ponts"] != cc["pieces_attendues"]:
        alertes.append(f"après la coupe des ponts : {cc['moities_apres_coupe_des_ponts']} pièce(s) au lieu de {cc['pieces_attendues']}")
    for nom, r in cc["retrait"].items():
        if r["points_bloques"]:
            alertes.append(f"moitié {nom} : retrait bloqué par l'os en {r['points_bloques']} point(s) sur {r['points_testes']}")
        if r.get("heurte_autre_moitie_mm3", 0) >= FROTTEMENT_MM3:
            alertes.append(f"moitié {nom} : en sortant, elle heurte l'autre moitié ({r['heurte_autre_moitie_mm3']} mm³)")
    for i, t in enumerate(tours):
        if t["profondeur"] != "complete" and not t["alignee_charniere"] and t["angle_charniere"] is not None:
            alertes.append(f"fente {i + 1} oblique à la charnière ({_fr(t['angle_charniere'], 0)}°) : la profondeur de lame donnée "
                           "protège la charnière à son point le plus haut ; finir la coupe à l'ostéotome ailleurs")
    if cc["epaisseur_entre_fentes_mm"] is not None and cc["epaisseur_entre_fentes_mm"] < 1.5:
        alertes.append(f"fentes très proches ({cc['epaisseur_entre_fentes_mm']} mm de matière entre elles) : coin de "
                       "fermeture trop fin pour deux fentes ; envisager un coin d'ouverture")
    if cc["pieces_ecartees_mm3"]:                                   # (tour de fente ou manchon : les îlots de coque à part)
        alertes.append(f"partie(s) de tour de fente ou de manchon détachée(s) du guide : {', '.join(f'{x:.0f} mm³' for x in cc['pieces_ecartees_mm3'])}")
    if "tour 2" in cc["manchons_isoles"]:
        alertes.append("la 2e tour de fente n'est pas reliée au reste du guide : NE PAS IMPRIMER")
    # appui insuffisant : en abord non usuel, c'est en général l'os voisin qui couvre la face d'appui (la coque ne passe
    # ni à travers ni dessous) ; le dire, avec le coin que la planification conseille
    st_ = pr.get("strategie") or {}
    reco = (st_.get("recommandation") or {}).get("type_coin")
    pourquoi = ((" (abord non usuel : un os voisin couvre la face d'appui ; la planification conseille un coin "
                 + (f"d'{reco})" if reco == "ouverture" else f"de {reco})")) if reco else
                " (abord non usuel : un os voisin couvre la face d'appui)") if st_.get("abord_non_usuel") else ""
    if cc["surface_appui_mm2"] < 300:
        alertes.append(f"guide posé sur {cc['surface_appui_mm2']:.0f} mm² seulement : position mal définie{pourquoi}")
    for nom, a_ in cc["appui_moities"].items():
        if a_["surface_mm2"] < 30:
            alertes.append(f"moitié {nom} sans appui sur l'os ({a_['surface_mm2']:.0f} mm²){pourquoi}")
    for x in cc["broches"]:
        if x["traverse_un_plan"] or x["distance_plan_coupe_mm"] < 1.0:
            alertes.append(f"broche {x['nom']} trop proche d'un plan de coupe ({x['distance_plan_coupe_mm']} mm)")
        if x["distance_trajet_lame_mm"] < 0.3:
            alertes.append(f"broche {x['nom']} sur le trajet de la lame (la scie la toucherait)")
        if x["manchon_plein"] < 0.6:
            alertes.append(f"manchon de la broche {x['nom']} absent ou incomplet ({100 * x['manchon_plein']:.0f} % de matière) : NE PAS IMPRIMER")
        if x["trop_pres_articulation"]:
            alertes.append(f"broche {x['nom']} à {x['distance_extremite_os_mm']} mm de l'extrémité de l'os")
    lim = cv["limites"]
    for nom, r_ in cv["voisins"].items():
        dg, vol = r_["distance_guide_mm"], r_["interpenetration_mm3"] or 0
        if vol > 0.01 or (dg is not None and dg < lim["guide_voisin_mm"] - 0.1):
            alertes.append(f"le guide de coupe {'traverse' if vol > 0.01 else 'touche'} {nom} (jeu {dg} mm)")
    if cv["cartilage"] and cv["cartilage"]["distance_guide_mm"] is not None and cv["cartilage"]["distance_guide_mm"] < lim["guide_cartilage_mm"]:
        alertes.append(f"le guide de coupe repose sur le cartilage articulaire ({cv['cartilage']['distance_guide_mm']} mm)")
    for nb, r_ in cv["broches"].items():
        for nom, dd_ in r_.items():
            if nom == "cartilage":
                if dd_["axe_broche_mm"] < lim["broche_cartilage_axe_mm"] - 0.1 or dd_["axe_manchon_mm"] < lim["manchon_cartilage_axe_mm"] - 0.1:
                    alertes.append(f"broche {nb} ou son manchon trop près du cartilage ({min(dd_.values())} mm de l'axe)")
            elif dd_["axe_broche_mm"] < lim["broche_voisin_axe_mm"] - 0.1 or dd_["axe_manchon_mm"] < lim["manchon_voisin_axe_mm"] - 0.1:
                alertes.append(f"broche {nb} ou son manchon contre {nom} ({min(dd_.values())} mm de l'axe)")
    if cr is None:
        alertes.append(f"guide de réduction non construit ({raison_reduction})")
    else:
        if not cr["etanche_stl"]:
            alertes.append("STL du guide de réduction non étanche")
        if cr["distance_barre_os_mm"] is not None and cr["distance_barre_os_mm"] < P.REDUCTION_ECART_MM - 0.5:
            alertes.append(f"barre du guide de réduction à {cr['distance_barre_os_mm']} mm de l'os")
        for nom, r_ in cr["voisins"].items():
            if r_["distance_guide_mm"] is not None and r_["distance_guide_mm"] < P.GUIDE_JEU_VOISIN_MM - 0.1:
                alertes.append(f"le guide de réduction touche {nom} après la correction (jeu {r_['distance_guide_mm']} mm)")

    info = {
        "generateur": "CT-CORA3D étape 7 (etape7_guide.py)",
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "os": pr.get("os"), "type_coin": pr["strategie"]["type_coin"],
        "prescription": {"schema_version": pr.get("schema_version"), "theta_deg": pr["deformite"]["theta_deg"],
                         "derotation_deg": pr.get("correction", {}).get("derotation_deg", 0)},
        "repere": pr.get("repere"),
        "parametres": {"jeu_mm": P.GUIDE_JEU_MM, "epaisseur_coque_mm": P.GUIDE_EPAISSEUR_MM,
                       "guidage_mm": P.GUIDE_GUIDAGE_MM, "paroi_mm": P.GUIDE_PAROI_MM,
                       "lame_mm": P.GUIDE_LAME_MM, "jeu_fente_mm": P.GUIDE_JEU_FENTE_MM,
                       "broche_mm": P.GUIDE_BROCHE_MM, "jeu_broche_mm": P.GUIDE_JEU_BROCHE_MM,
                       "marge_mm": P.GUIDE_MARGE_MM, "secteur_deg": P.GUIDE_SECTEUR_DEG,
                       "depouille_deg": P.GUIDE_DEPOUILLE_DEG, "conge_mm": P.GUIDE_CONGE_MM,
                       "pont_mm": [P.GUIDE_PAROI_MM, round(geo["Hp"], 2)], "pas_grille_mm": round(geo["gr"].h, 3),
                       "reduction_ecart_mm": P.REDUCTION_ECART_MM, "reduction_manchon_mm": P.REDUCTION_MANCHON_MM,
                       "jeu_voisin_mm": P.GUIDE_JEU_VOISIN_MM, "marge_cartilage_mm": P.GUIDE_MARGE_CARTILAGE_MM,
                       "chanfrein_mm": P.GUIDE_CHANFREIN_MM},
        "parametres_modifies": appliques,
        "parametres_defaut": pc.defauts,
        "strategie": {k_: pr["strategie"].get(k_) for k_ in ("type_coin", "regle_paley", "abord", "osteotomie_complete",
                                                              "translation_osteotomie_mm", "charniere_profondeur_mm",
                                                              "decalage_coupe_signe_mm", "configuration_broches",
                                                              "abord_non_usuel", "coin_mixte")},
        "correction_reelle": {"T_4x4": [[round(float(x), 6) for x in l_] for l_ in np.asarray(T, float)],
                              "compensation_trait_scie_mm": round(float(np.linalg.norm(np.asarray(T, float)[:3, 3]
                                                                                       - geo["T_prescrit"][:3, 3])), 3)},
        "voisins_et_cartilage": dict(cv, voisins_evites_guide_coupe=geo["voisins_evites"],
                                     cartilage_connu=cart is not None,
                                     noeuds_coque_retires_cartilage=geo["noeuds_coque_cartilage"]),
        "guide_coupe": dict(cc, pieces=[mesures_piece(guide, "guide de coupe")]),
        "guide_reduction": dict(cr, pieces=[mesures_piece(red, "guide de réduction")]) if cr else None,
        "protocole": protocole(pr, cc, cv, cr),
        "alertes": alertes,
        "fichiers": fichiers,
        "duree_s": None,
    }
    info["dimensions"] = dimensions_guide(pr, geo, cc, guide, red, gred if red is not None else None, broches_c)
    if image:
        try:
            apercu(dossier / "guide.png", v, f, (m_prox, m_dist), ponts, vc, fc, red, geo["broches"], broches_c, geo,
                   voisins, voisins_c)
            info["fichiers"].append("guide.png")
        except Exception as e:                       # l'aperçu est facultatif (affichage hors écran indisponible)
            journal(f"[étape 7] aperçu non créé : {e}")
        try:                                         # plans 2D : générique (symboles) et coté (ce cas)
            import dessin_guide
            journal("[étape 7] plans 2D du guide (générique et coté)…")
            info["fichiers"] += dessin_guide.dessiner(dossier, pr, info, v, f, guide, (m_prox, m_dist), ponts, red, geo,
                                                      broches_c, vc, fc)
        except Exception as e:                       # le plan est facultatif : le guide reste valable
            journal(f"[étape 7] plan 2D non créé : {type(e).__name__} : {e}")
    info["duree_s"] = round(time.time() - t_debut, 1)
    (dossier / "guide.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    g = info["guide_coupe"]
    journal(f"[étape 7] guide de coupe : jeu min {g['jeu_minimal_mesure_mm']} mm, appui {g['surface_appui_mm2']} mm², "
            f"{g['moities_apres_coupe_des_ponts']} moitiés après les ponts, étanche {g['etanche_stl']}, profondeur de lame "
            + " et ".join(f"{_fr(x['profondeur_lame_mm'], 1)} mm" for x in g["fentes"]) + " ; "
            + (f"guide de réduction : barre à {cr['distance_barre_os_mm']} mm de l'os ; " if cr else "")
            + f"{len(alertes)} alerte(s), {info['duree_s']} s")
    return info


def main():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    a.add_argument("--prescription", required=True, help="prescription.json (onglet CORA, étape 12)")
    a.add_argument("--os", required=True, help="maillage de l'os planifié (.bin de l'application ou .stl)")
    a.add_argument("--sortie", required=True, help="dossier de sortie")
    a.add_argument("--voisin", action="append", default=[], metavar="NOM=FICHIER",
                   help="os voisin à éviter (.bin ou .stl, repère de l'os), par exemple fibula=fibula.bin ; répétable")
    a.add_argument("--cartilage", help="cartilage articulaire de l'os : fichier binaire, 1 octet par sommet (≥ 128)")
    a.add_argument("--sans-image", action="store_true")
    x = a.parse_args()
    voisins = []
    for item in x.voisin:
        nom, _, chemin = item.partition("=")
        voisins.append((nom, *lire_maillage(chemin)))
    art = np.frombuffer(Path(x.cartilage).read_bytes(), np.uint8) if x.cartilage else None
    info = generer(x.prescription, x.os, x.sortie, image=not x.sans_image, voisins=voisins, articulaire=art)
    for al in info["alertes"]:
        print("  ALERTE :", al)


if __name__ == "__main__":
    main()
