"""STL du guide générique (modèle de base, sans os), pour l'impression 3D.

Même modèle et mêmes paramètres que les plans CTC3D-GEN-01 et CTC3D-GEN-02 (plans_generiques.py) :
  guide_coupe_generique.stl      : guide de coupe d'une pièce (moitiés 1 et 2 reliées par les 2 ponts sécables 3) ;
  guide_reduction_generique.stl  : guide de réduction (pièce 4).
Os cylindrique de largeur l = 16 mm (non fourni), coin de fermeture θ = 20°, paramètres par défaut de CT-CORA3D.
Repère des plans : axe de l'os = axe y (y > 0 côté proximal), z vers la face d'appui (haut des tours), x latéral.
Unité : mm. Géométrie exacte (booléens de manifold3d, comme l'étape 7) ; chanfreins c à l'entrée des fentes et des
manchons du guide de coupe, congés r aux raccords barre / manchons du guide de réduction (comme sur les plans).

Usage (depuis ce dossier script/) : python3 -B stl_generiques.py
Modules Python nécessaires : numpy, manifold3d et trimesh.
"""
import math
from pathlib import Path

import manifold3d as m3d
import numpy as np
import trimesh

SORTIE = Path(__file__).resolve().parent.parent                       # documents/plan_guide_generique

# ------------------------------------------------------------------ paramètres du modèle (ceux des plans)
l_os = 16.0; R = l_os / 2
j, e, alpha, g, p, s, js = 0.30, 3.0, 75.0, 10.0, 2.0, 0.60, 0.20
Ob, jb, hp, kd, er, lr, tb, m = 1.6, 0.20, 5.0, 1.2, 4.0, 12.0, 6.0, 8.0
c_ch, r_conge, theta = 0.50, 0.80, 20.0
Ri, Ro = R + j, R + j + e                     # 8,3 et 11,3
w_f = s + js                                  # largeur de fente 0,8
L_f = l_os + 2                                # longueur de fente 18
t_t = w_f + 2 * p                             # épaisseur de tour 4,8
L_t = L_f + 2 * p                             # longueur de tour 22
z_top = Ri + e + g                            # 21,3 : haut de la tour 1 et du manchon proximal
Rs, rh = (Ob + jb) / 2 + p, (Ob + jb) / 2     # manchon 5,8 ; trou 1,8
d = kd * l_os                                 # 19,2
Hz = -(R - 2.0)                               # charnière à 2 mm de la corticale opposée
u_top = z_top - Hz                            # 27,3 : profondeur de lame
a75 = math.radians(alpha)
zb = Ro * math.cos(a75)                       # hauteur des bords de la coque (2,9)
th = math.radians(theta)

# directions 3D (x, y, z)
EX, EY, EZ = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
H = np.array([0.0, 0.0, Hz])                  # charnière (sur l'axe x)
t2 = np.array([0.0, -math.sin(th), math.cos(th)])   # le long de PC2, de la charnière vers la face d'appui
nP = np.array([0.0, math.cos(th), math.sin(th)])    # normale de PC2 vers le côté proximal
n2 = -nP                                            # normale de PC2 vers le côté distal
axe_D1 = H + d * n2                                 # axe de la broche distale (parallèle à PC2, à d de la coupe)
u_b = (Ro - axe_D1[2]) / t2[2]                      # abscisse où cet axe traverse la coque (z = Ro)
B_D1 = axe_D1 + u_b * t2
y_top, y_bot = d + m, round(B_D1[1] - m, 1)        # extrémités de la coque : 27,2 et -34,7 (longueur 61,9)

SEG_GRAND, SEG_MANCHON, SEG_TROU = 256, 96, 64      # facettes des cercles (écart à l'arc inférieur à 0,002 mm)


# ------------------------------------------------------------------ primitives exactes
def unitaire(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def boite(centre, axes, demi):
    """Pavé : centre, 3 axes orthonormés, demi-dimensions (repère remis en sens direct si besoin)."""
    A = np.column_stack([unitaire(a) for a in axes])
    if np.linalg.det(A) < 0:
        A[:, 2] *= -1
    demi = np.asarray(demi, float)
    return m3d.Manifold.cube(tuple(2 * demi)).transform(np.column_stack([A, np.asarray(centre, float) - A @ demi]))


def cone(a, o, t0, t1, r0, r1, segments=SEG_MANCHON):
    """Tronc de cône (ou cylindre si r0 = r1) d'axe (a, o) : rayon r0 à l'abscisse t0, r1 à t1."""
    o = unitaire(o)
    b1 = unitaire(np.cross(o, EX if abs(o[0]) < 0.9 else EY))
    b2 = np.cross(o, b1)
    M = np.column_stack([b1, b2, o, np.asarray(a, float) + t0 * o])
    return m3d.Manifold.cylinder(float(t1 - t0), float(r0), float(r1), segments).transform(M)


def prisme_y(section, y0, y1):
    """Extrusion le long de l'axe de l'os d'un profil dessiné dans le plan (x, z) : X du profil = x, Y du profil = z."""
    M = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, y1], [0, 1.0, 0, 0]])    # rotation (déterminant + 1)
    return m3d.Manifold.extrude(section, y1 - y0).transform(M)


def disque(r, centre=(0.0, 0.0), segments=SEG_GRAND):
    return m3d.CrossSection.circle(r, segments).translate(centre)


def union(pieces):
    return m3d.Manifold.batch_boolean(pieces, m3d.OpType.Add)


def chanfrein_fente(centre, axe_fente, sortie, longueur):
    """Entrée chanfreinée d'une fente (pente 45°) : prisme carré tourné de 45° autour de la fente, centré sur le haut de
    la tour ; il ouvre la fente à w_f + 2c au ras du haut (même construction que l'étape 7)."""
    n = np.cross(sortie, axe_fente)                     # normale de la fente
    a_ = math.sqrt(2.0) * (c_ch + w_f / 2)
    return boite(centre, (unitaire(n + sortie), unitaire(sortie - n), axe_fente), (a_ / 2, a_ / 2, longueur / 2))


# ================================================================== GUIDE DE COUPE (pièces 1 à 3)
def guide_coupe():
    # coque : secteur ± α du disque Ro, de y_bot à y_top ; sa face intérieure (Ri) est creusée plus bas par l'os
    # (un seul cylindre Ri : deux surfaces confondues laisseraient des arêtes à 4 faces dans le STL)
    secteur = m3d.CrossSection([[(0.0, 0.0)] + [(30 * math.sin(f), 30 * math.cos(f))
                                                 for f in np.linspace(a75, -a75, 31)]])     # sens trigonométrique
    coque = prisme_y(disque(Ro) ^ secteur, y_bot, y_top)

    # tour 1 (PC1, plan y = 0) : des bords de la coque (z = zb) au haut z_top
    tour1 = boite([0, 0, (zb + z_top) / 2], (EX, EY, EZ), (L_t / 2, t_t / 2, (z_top - zb) / 2))
    # tour 2 (PC2, coin de fermeture θ) : parallèle à PC2, haut perpendiculaire à PC2 à la profondeur de lame u_top,
    # descendue comme la tour 1 jusqu'au plan des bords de la coque
    tour2 = boite(H + (u_top / 2) * t2, (EX, nP, t2), (L_t / 2, t_t / 2, u_top / 2))
    tour2 = tour2 ^ boite([0, 0, zb + 25], (EX, EY, EZ), (40, 40, 25))

    # manchon proximal P1 (radial, y = d) et manchon distal D1 (parallèle à PC2), hauteur g au-dessus de la coque
    P1 = cone([0, d, 0], EZ, 0.0, z_top, Rs, Rs)
    D1 = cone(axe_D1, t2, u_b - 6.0, u_b + g, Rs, Rs)

    corps = union([coque, tour1, tour2, P1, D1])

    # os (cylindre Ri = R + j) : aucune matière à l'intérieur
    os_jeu = prisme_y(disque(Ri), -80.0, 80.0)
    # séparation des deux moitiés : dalle de la fente 1 (PC1) sur toute la largeur, sauf les 2 ponts sécables p × hp
    # aux extrémités de la fente, en haut de la tour 1 (les boîtes des ponts débordent vers le haut et vers l'extérieur)
    dalle = boite([0, 0, 10], (EX, EY, EZ), (40, w_f / 2, 40))
    ponts = union([boite([sg * (L_f / 2 + (L_t / 2 + 1 - L_f / 2) / 2), 0, z_top - hp + (hp + 1) / 2], (EX, EY, EZ),
                         ((L_t / 2 + 1 - L_f / 2) / 2, w_f / 2 + 1, (hp + 1) / 2)) for sg in (-1, 1)])
    # fente 2 (PC2) : fente fermée de la moitié distale, de la charnière au-dessus de la tour 2
    fente2 = boite(H + ((u_top + 3) / 2) * t2, (EX, nP, t2), (L_f / 2, w_f / 2, (u_top + 3) / 2))
    # trous des broches (Øb + jb), à travers la coque
    trous = [cone([0, d, -5], EZ, 0.0, z_top + 6, rh, rh, SEG_TROU),
             cone(axe_D1, t2, u_b - 9.0, u_b + g + 1.0, rh, rh, SEG_TROU)]
    # chanfreins d'entrée c : fentes (pente 45°) et manchons (cône de rh + c à rh)
    chanfreins = [chanfrein_fente([0, 0, z_top], EX, EZ, L_f + 0.6),
                  chanfrein_fente(H + u_top * t2, EX, t2, L_f + 0.6),
                  cone([0, d, 0], EZ, z_top - c_ch, z_top + 1.0, rh, rh + c_ch + 1.0, SEG_TROU),
                  cone(axe_D1, t2, u_b + g - c_ch, u_b + g + 1.0, rh, rh + c_ch + 1.0, SEG_TROU)]

    guide = corps - union([os_jeu, dalle - ponts, fente2] + trous + chanfreins)
    return guide


# ================================================================== GUIDE DE RÉDUCTION (pièce 4)
def guide_reduction():
    z0 = R                                                              # haut de l'os (contact des manchons)
    yR = (-d, d)                                                        # 2 broches parallèles après correction
    z_b0, z_b1 = z0 + er, z0 + er + tb                                  # faces de la barre : 12 et 18
    # barre : contour des 2 broches vu le long des broches, élargi du rayon des manchons (oblong de largeur 2 Rs) ;
    # 0,01 mm plus étroite que les manchons, pour que leurs surfaces ne soient pas confondues (invisible à l'impression)
    Rb = Rs - 0.01
    oblong = (disque(Rb, (0.0, yR[0]), SEG_MANCHON) + disque(Rb, (0.0, yR[1]), SEG_MANCHON)).hull()
    barre = m3d.Manifold.extrude(oblong, tb).translate((0, 0, z_b0))
    manchons = [cone([0, y, z0 - 2.0], EZ, 0.0, lr + 2.0, Rs, Rs) for y in yR]

    # congés r entre les faces de la barre et les manchons (côté intérieur, comme la coupe A-A du plan) : anneaux de
    # révolution autour de chaque manchon, limités à l'emprise de la barre entre les 2 manchons. Le profil déborde de
    # 0,05 mm dans le manchon et dans la barre, et l'arc a 49 côtés (aucun sommet aux points de tangence) : pas de
    # surfaces confondues
    def conge(z_face, vers_bas):
        k, eps = r_conge, 0.05
        z_c = z_face - k if vers_bas else z_face + k
        carre = m3d.CrossSection.square((k + eps, k + eps)).translate((Rs - eps, z_c if vers_bas else z_face - eps))
        profil = carre - m3d.CrossSection.circle(k, 49).translate((Rs + k, z_c))
        return m3d.Manifold.revolve(profil, SEG_MANCHON)
    # emprise 0,02 mm en retrait des faces latérales de la barre (faces non confondues)
    emprise = boite([0, 0, (z_b0 + z_b1) / 2], (EX, EY, EZ), (Rb - 0.02, d, tb / 2 + 2))
    conges = [conge(zf, bas).translate((0, y, 0)) ^ emprise for y in yR for zf, bas in ((z_b0, True), (z_b1, False))]

    corps = union([barre] + manchons + conges)
    os_ = prisme_y(disque(R), -60.0, 60.0)                              # extrémités des manchons moulées sur l'os
    trous = [cone([0, y, 0], EZ, 0.0, z0 + lr + 2, rh, rh, SEG_TROU) for y in yR]
    return corps - union([os_] + trous)


# ================================================================== export et contrôles
def exporter(man, nom):
    """Écrit le STL (binaire, mm) et le relit comme un logiciel d'impression. Là où un cylindre coupe une face plane,
    les booléens laissent de minuscules triangles qui s'écrasent une fois les sommets arrondis en float32 (format
    STL) : le solide est simplifié avec une tolérance croissante (au plus 0,005 mm) jusqu'à ce que le STL relu soit
    étanche (même méthode que l'étape 7)."""
    if man.status() != m3d.Error.NoError:
        raise RuntimeError(f"{nom} : solide invalide ({man.status()})")
    chemin = SORTIE / f"{nom}.stl"
    for tol in (0.0, 1e-4, 1e-3, 5e-3):
        m_ = man.simplify(tol) if tol else man
        mesh = m_.to_mesh()
        tm = trimesh.Trimesh(np.asarray(mesh.vert_properties[:, :3], float), np.asarray(mesh.tri_verts), process=False)
        tm.export(chemin)
        relu = trimesh.load(chemin, force="mesh", process=True)
        if relu.is_watertight and relu.is_winding_consistent:
            break
    lo, hi = relu.bounds
    print(f"{nom}.stl : {len(relu.faces)} triangles, étanche {relu.is_watertight}, orientation cohérente "
          f"{relu.is_winding_consistent}, tolérance {tol} mm, {len(m_.decompose())} pièce(s), volume "
          f"{m_.volume():.0f} mm³ (avant simplification {man.volume():.0f}), "
          f"encombrement {hi[0] - lo[0]:.1f} × {hi[1] - lo[1]:.1f} × {hi[2] - lo[2]:.1f} mm")
    return relu


if __name__ == "__main__":
    exporter(guide_coupe(), "guide_coupe_generique")
    exporter(guide_reduction(), "guide_reduction_generique")
