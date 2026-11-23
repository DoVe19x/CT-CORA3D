"""
maillages.py : maillages volumiques d'un os (fichier STL étanche) et d'une poutre de validation.

Rôle    : (1) placer l'os dans ses axes principaux (x = axe de l'os, orienté vers l'extrémité la plus large) ;
          (2) tétraèdres : surface remaillée de façon uniforme (pyacvd, taille h), puis remplissage par TetGen
              (qualité : rapport rayon / arête ≤ 1,5, volume maximal celui d'un tétraèdre régulier d'arête h) ;
          (3) hexaèdres : « voxels » de côté h dont le centre est dans l'os (rastérisation du STL par VTK) ;
          (4) poutre droite maillée en hexaèdres, ou en tétraèdres (6 par hexaèdre), pour la validation.
Sorties : (X, conn) : coordonnées des nœuds (mm) et connectivité (indices à partir de 0, ordre d'Abaqus).
"""
import numpy as np
from scipy import ndimage as ndi

import ef


# =============================================================================== repère de l'os
def lire_os(chemin_stl):
    """Surface (pyvista) de l'os dans ses axes principaux : x le long de l'os, vers l'extrémité la plus large."""
    import pyvista as pv
    s = pv.read(str(chemin_stl)).triangulate().clean()
    p = np.asarray(s.points, float)
    c = p.mean(0)
    _, _, vt = np.linalg.svd(p - c, full_matrices=False)
    q = (p - c) @ vt.T
    t = q[:, 0]
    L = t.max() - t.min()
    largeur = lambda m: np.ptp(q[m, 1]) * np.ptp(q[m, 2])
    if largeur(t < t.min() + 0.1 * L) > largeur(t > t.max() - 0.1 * L):
        vt[0] *= -1                                          # x vers l'extrémité large (plateau tibial)
        vt[2] *= -1                                          # repère direct
        q = (p - c) @ vt.T
    s.points = q
    return s


# =============================================================================== tétraèdres
def tetraedres(surface, h):
    """Maillage C3D4 de l'os, taille d'arête visée h (mm)."""
    import pyacvd
    import tetgen
    n_points = int(2 * surface.area / (np.sqrt(3) * h ** 2))
    clus = pyacvd.Clustering(surface)
    if surface.n_points < 3 * n_points:
        clus.subdivide(2)
    clus.cluster(n_points)
    peau = clus.create_mesh().clean()
    tg = tetgen.TetGen(peau)
    X, conn, _, _ = tg.tetrahedralize(quality=True, minratio=1.5, mindihedral=10.0,
                                       maxvolume=h ** 3 / (6 * np.sqrt(2)), quiet=True)
    X, conn = np.asarray(X, float), np.asarray(conn, np.int64)
    return orienter_tetra(X, conn)


def orienter_tetra(X, conn):
    """Abaqus veut un volume positif : (x2 - x1) × (x3 - x1) · (x4 - x1) > 0 ; sinon on échange les nœuds 2 et 3."""
    a, b, c, d = (X[conn[:, k]] for k in range(4))
    neg = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) < 0
    conn = conn.copy()
    conn[neg, 1], conn[neg, 2] = conn[neg, 2].copy(), conn[neg, 1].copy()
    return X, conn


# =============================================================================== hexaèdres
def voxels(surface, h):
    """Maillage C3D8 « voxel » de l'os : cubes de côté h dont le centre est dans l'os (plus grand morceau relié par
    des faces). Grille alignée sur les axes de l'os."""
    import vtk
    lo, hi = np.array(surface.bounds[::2]), np.array(surface.bounds[1::2])
    n = np.ceil((hi - lo) / h).astype(int) + 2
    origine = lo - h * 0.5
    image = vtk.vtkImageData()
    image.SetSpacing(h, h, h)
    image.SetOrigin(*(origine + h / 2))                      # points de l'image = centres des cubes
    image.SetDimensions(*n)
    image.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
    image.GetPointData().GetScalars().Fill(1)
    pol = vtk.vtkPolyDataToImageStencil()
    pol.SetInputData(surface)
    pol.SetOutputOrigin(image.GetOrigin())
    pol.SetOutputSpacing(image.GetSpacing())
    pol.SetOutputWholeExtent(image.GetExtent())
    pol.Update()
    st = vtk.vtkImageStencil()
    st.SetInputData(image)
    st.SetStencilConnection(pol.GetOutputPort())
    st.ReverseStencilOff()
    st.SetBackgroundValue(0)
    st.Update()
    from vtkmodules.util import numpy_support as vns
    plein = vns.vtk_to_numpy(st.GetOutput().GetPointData().GetScalars()).reshape(n[2], n[1], n[0]) > 0
    lab, k = ndi.label(plein)                                # connexité par les faces
    if k > 1:
        plein = lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1)
    kk, jj, ii = np.nonzero(plein)
    coins = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]])
    gi = ii[:, None] + coins[None, :, 0]
    gj = jj[:, None] + coins[None, :, 1]
    gk = kk[:, None] + coins[None, :, 2]
    cle = (gk * (n[1] + 1) + gj) * (n[0] + 1) + gi
    uniques, conn = np.unique(cle, return_inverse=True)
    conn = conn.reshape(-1, 8)
    i = uniques % (n[0] + 1)
    j = (uniques // (n[0] + 1)) % (n[1] + 1)
    k_ = uniques // ((n[0] + 1) * (n[1] + 1))
    X = origine + h * np.c_[i, j, k_]
    return X.astype(float), conn.astype(np.int64)


FACES_HEXA = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
ARETES_HEXA = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))


def grille_o(n, m, s=0.35):
    """Grille en « O » du disque unité : un carré central [-s, s]² de n × n quadrangles, entouré de m couronnes de 4n
    quadrangles qui vont du bord du carré au cercle. Renvoie (points 2D, quadrangles parcourus dans le sens direct)."""
    g = np.linspace(-s, s, n + 1)
    P = [np.array([(a, b) for b in g for a in g])]            # carré : indice i + (n + 1) j
    carre = lambda i, j: i + (n + 1) * j
    quads = [[carre(i, j), carre(i + 1, j), carre(i + 1, j + 1), carre(i, j + 1)] for j in range(n) for i in range(n)]
    tour = ([carre(i, 0) for i in range(n)] + [carre(n, j) for j in range(n)]
            + [carre(n - i, n) for i in range(n)] + [carre(0, n - j) for j in range(n)])   # 4n nœuds, sens direct
    bord = P[0][tour]
    cercle = bord / np.linalg.norm(bord, axis=1)[:, None]
    couches = [np.array(tour)]
    debut = len(P[0])
    for l in range(1, m + 1):
        t = l / m
        P.append((1 - t) * bord + t * cercle)
        couches.append(debut + np.arange(4 * n))
        debut += 4 * n
    for l in range(m):
        a, b = couches[l], couches[l + 1]
        for p in range(4 * n):
            q = (p + 1) % (4 * n)
            quads.append([a[p], a[q], b[q], b[p]])
    P = np.vstack(P)
    quads = np.array(quads)
    v1, v2 = P[quads[:, 1]] - P[quads[:, 0]], P[quads[:, 3]] - P[quads[:, 0]]
    neg = v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0] < 0
    quads[neg] = quads[neg][:, ::-1]
    return P, quads


def _rayons(coupe, centre, angles):
    """Distance du centre au contour de la section, le long de chaque rayon (intersection la plus lointaine)."""
    pts = np.asarray(coupe.points)[:, 1:]
    lignes = coupe.lines.reshape(-1, 3)[:, 1:] if coupe.n_lines else np.zeros((0, 2), int)
    a, b = pts[lignes[:, 0]] - centre, pts[lignes[:, 1]] - centre
    u = np.c_[np.cos(angles), np.sin(angles)]
    e = b - a
    croix = lambda p, q: p[..., 0] * q[..., 1] - p[..., 1] * q[..., 0]
    den = croix(u[:, None, :], e[None])                       # (rayons, segments)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = croix(a[None], e[None]) / den                     # distance le long du rayon
        s = croix(a[None], u[:, None, :]) / den               # position sur le segment
    ok = (np.abs(den) > 1e-12) & (t > 0) & (s >= 0) & (s <= 1)
    return np.where(ok, t, 0).max(1)


def _centre_interieur(coupe, pas=0.2):
    """Point de la section le plus éloigné de son contour (carte de distance sur une grille de 0,2 mm) : il est
    toujours à l'intérieur de l'os, même pour une section creusée ou faite de deux morceaux."""
    from matplotlib.path import Path as Chemin
    pts = np.asarray(coupe.points)[:, 1:]
    lo, hi = pts.min(0) - 2 * pas, pts.max(0) + 2 * pas
    gy, gz = np.arange(lo[0], hi[0], pas), np.arange(lo[1], hi[1], pas)
    G = np.array(np.meshgrid(gy, gz, indexing="ij")).reshape(2, -1).T
    dedans = np.zeros(len(G), bool)
    for boucle in _boucles(coupe):
        dedans ^= Chemin(pts[boucle]).contains_points(G)       # règle pair / impair (trous éventuels)
    d = ndi.distance_transform_edt(dedans.reshape(len(gy), len(gz)))
    i, j = np.unravel_index(np.argmax(d), d.shape)
    return np.array([gy[i], gz[j]])


def _boucles(coupe):
    """Contours fermés de la section (listes d'indices de points)."""
    bandes = coupe.strip(join=True)
    lignes, k, out = bandes.lines, 0, []
    while k < len(lignes):
        n = lignes[k]
        out.append(lignes[k + 1:k + 1 + n])
        k += n + 1
    pts_b = np.asarray(bandes.points)
    # indices de « bandes » -> indices de « coupe » (mêmes points, ordre éventuellement différent)
    from scipy.spatial import cKDTree
    _, idx = cKDTree(np.asarray(coupe.points)).query(pts_b)
    return [idx[b] for b in out]


_PROFILS = {}


def profil(surface, marge=1.0, pas=0.5, n_angles=360):
    """Description de l'os par tranches, calculée une fois et partagée par tous les maillages balayés (la géométrie
    est donc la même quel que soit h) : tous les 0,5 mm, le centre de la section c(x) et la distance r(x, θ) du centre
    au contour. Le trajet des centres est lissé (médiane glissante sur 5 mm puis gaussienne σ = 3 mm), et r est lissé
    autour de la section (σ = 4°) et le long de l'os (σ = 1 mm) : pas de saut d'une tranche à l'autre."""
    cle = (id(surface), marge, pas, n_angles)
    if cle in _PROFILS:
        return _PROFILS[cle]
    x0, x1 = surface.bounds[0] + marge, surface.bounds[1] - marge
    xs = np.linspace(x0, x1, int(round((x1 - x0) / pas)) + 1)
    angles = np.linspace(-np.pi, np.pi, n_angles + 1)[:-1]
    coupes = [surface.slice(normal="x", origin=(x, 0, 0)) for x in xs]
    c = np.array([_centre_interieur(k) for k in coupes])
    c = ndi.median_filter(c, size=(11, 1), mode="nearest")
    c = ndi.gaussian_filter1d(c, 3.0 / pas, axis=0, mode="nearest")
    R = np.zeros((len(xs), n_angles))
    for k, coupe in enumerate(coupes):
        r = _rayons(coupe, c[k], angles)
        if np.any(r <= 0):                                     # centre lissé hors de la section : rayons manquants
            ok = r > 0
            r = np.interp(angles, angles[ok], r[ok], period=2 * np.pi) if ok.sum() > 3 else R[k - 1]
        R[k] = r
    R = ndi.gaussian_filter1d(R, 4.0 * n_angles / 360, axis=1, mode="wrap")
    R = ndi.gaussian_filter1d(R, 1.0 / pas, axis=0, mode="nearest")
    _PROFILS[cle] = (xs, angles, c, R)
    return _PROFILS[cle]


def balaye(surface, h=None, s=0.35, quadratique=False, divisions=None):
    """Maillage C3D8 balayé (« sweep » d'Abaqus) : l'os est coupé en tranches perpendiculaires à son axe (pas ≈ h) ;
    chaque section est maillée par la même grille en « O » (n × n quadrangles au centre, m couronnes de 4n autour),
    déformée pour suivre le contour r(θ) de la section ; les quadrangles de deux tranches voisines forment des
    hexaèdres. Les extrémités de l'os sont coupées à 1 mm. Hypothèse : sections étoilées depuis leur centre (vrai
    pour la diaphyse ; dans les épiphyses, les creux du contour sont comblés).
    quadratique=True : C3D20 dont les nœuds milieux sont placés par la même transformation que les sommets (milieu
    pris dans la grille de référence) : ils sont sur la surface courbe de l'os, comme Abaqus les place sur la
    géométrie."""
    xs_p, angles, cp, Rp = profil(surface)
    r_moy = float(np.mean(Rp))
    if divisions is None:                                      # taille h : nombres de divisions déduits
        divisions = (max(2, int(round(2 * np.pi * r_moy / (4 * h)))), max(1, int(round((1 - s) * r_moy / h))),
                     max(2, int(np.ceil((xs_p[-1] - xs_p[0]) / h))))
    n, m, nk = divisions
    xs = np.linspace(xs_p[0], xs_p[-1], nk + 1)
    centres = np.c_[np.interp(xs, xs_p, cp[:, 0]), np.interp(xs, xs_p, cp[:, 1])]
    P, quads = grille_o(n, m, s)
    rho, phi = np.linalg.norm(P, axis=1), np.arctan2(P[:, 1], P[:, 0])
    npl = len(P)
    conn = np.vstack([np.hstack([quads + k * npl, quads + (k + 1) * npl]) for k in range(nk)]).astype(np.int64)
    R = Rp.copy()
    for essai in range(12):
        rayons = np.array([np.interp(xs, xs_p, R[:, j]) for j in range(len(angles))]).T
        X = np.vstack([np.c_[np.full(npl, x), c + (rho * np.interp(phi, angles, r, period=2 * np.pi))[:, None]
                             * np.c_[np.cos(phi), np.sin(phi)]] for x, c, r in zip(xs, centres, rayons)])
        mauvais = qualite_hexa(X, conn) <= 0.02
        if not mauvais.any():
            break
        # éléments retournés (épiphyses aux contours tourmentés) : contour lissé plus fort autour de ces tranches
        xb = np.unique(X[conn[mauvais]].mean(1)[:, 0])
        w = np.exp(-((xs_p[:, None] - xb[None]) ** 2) / (2 * 3.0 ** 2)).max(1)[:, None]
        fort = ndi.gaussian_filter1d(ndi.gaussian_filter1d(R, 12.0 * len(angles) / 360, axis=1, mode="wrap"),
                                     2.0 / (xs_p[1] - xs_p[0]), axis=0, mode="nearest")
        R = (1 - w) * R + w * fort
    else:
        raise ValueError(f"maillage balayé {divisions} : {int(mauvais.sum())} élément(s) retourné(s)")
    if not quadratique:
        return X, conn
    # C3D20 : seuls les nœuds milieux des arêtes de la surface (les deux sommets sur le contour, ρ = 1 dans la grille de
    # référence) sont placés sur la surface courbe : image du milieu de l'arête par la même transformation que les
    # sommets. Les autres restent au milieu d'arêtes droites (comme Abaqus, qui ne courbe que les arêtes sur la géométrie).
    X2, conn2 = ef.quadratique(X, conn, "C3D20")
    Xd = X2.copy()
    xr, Pr = X[:, 0], P[np.arange(len(X)) % npl]
    rho_r = np.linalg.norm(Pr, axis=1)
    a_, b_ = np.array(ef._A20).T
    milieux = conn2[:, 8:].ravel()
    ia, ib = conn2[:, a_].ravel(), conn2[:, b_].ravel()
    peau = (rho_r[ia] > 0.999) & (rho_r[ib] > 0.999)
    milieux, ia, ib = milieux[peau], ia[peau], ib[peau]
    xm, Pm = 0.5 * (xr[ia] + xr[ib]), 0.5 * (Pr[ia] + Pr[ib])
    phi_m = np.arctan2(Pm[:, 1], Pm[:, 0])
    from scipy.interpolate import RegularGridInterpolator
    ang = np.r_[angles, angles[0] + 2 * np.pi]
    interp = RegularGridInterpolator((xs_p, ang), np.c_[R, R[:, :1]])
    r_m = interp(np.c_[xm, np.mod(phi_m - ang[0], 2 * np.pi) + ang[0]])
    cm = np.c_[np.interp(xm, xs_p, cp[:, 0]), np.interp(xm, xs_p, cp[:, 1])]
    X2[milieux] = np.c_[xm, cm + r_m[:, None] * np.c_[np.cos(phi_m), np.sin(phi_m)]]   # ρ = 1 : sur le contour
    # qualité : rapport min / max du jacobien (27 points de Gauss + 20 nœuds) au moins 0,3, sinon arêtes droites
    el = ef.ELEMENTS["C3D20"]
    points = np.vstack([el.points, el.noeuds_ref])
    for _ in range(10):
        dets = np.stack([np.linalg.det(np.einsum("enj,nk->ejk", X2[conn2], el.dN(xi)[0])) for xi in points], 1)
        courbes = np.any(X2[conn2[:, 8:]] != Xd[conn2[:, 8:]], axis=(1, 2))
        mauvais = courbes & ((dets.min(1) <= 0) | (dets.min(1) < 0.3 * dets.max(1)))
        if not mauvais.any():
            break
        n = np.unique(conn2[mauvais][:, 8:])
        X2[n] = Xd[n]
    return X2, conn2


def divisions_balaye(surface, h, s=0.35):
    """(n, m, nk) du maillage balayé de taille h : n quadrangles par côté du carré central, m couronnes, nk tranches."""
    xs_p, _, _, Rp = profil(surface)
    r_moy = float(np.mean(Rp))
    return (max(2, int(round(2 * np.pi * r_moy / (4 * h)))), max(1, int(round((1 - s) * r_moy / h))),
            max(2, int(np.ceil((xs_p[-1] - xs_p[0]) / h))))


def subdiviser_tetra(surface, X, conn):
    """Raffinement uniforme emboîté : chaque tétraèdre est coupé en 8 (un nœud au milieu de chaque arête : 4 petits
    tétraèdres aux coins, l'octaèdre central coupé en 4 le long d'une diagonale). Les nouveaux nœuds des arêtes de
    surface sont posés sur le STL ; un élément qui se dégraderait trop (rapport des jacobiens des enfants) garde son
    nœud au milieu de l'arête droite. Le nouveau maillage contient tous les nœuds de l'ancien."""
    X2, c10 = ef.quadratique(X, conn, "C3D10")                # nœuds 4 à 9 : milieux de (0,1) (1,2) (2,0) (0,3) (1,3) (2,3)
    s0, s1, s2, s3, m01, m12, m02, m03, m13, m23 = c10.T
    enfants = np.vstack([np.c_[s0, m01, m02, m03], np.c_[m01, s1, m12, m13], np.c_[m02, m12, s2, m23],
                         np.c_[m03, m13, m23, s3],
                         np.c_[m01, m23, m02, m12], np.c_[m01, m23, m12, m13], np.c_[m01, m23, m13, m03],
                         np.c_[m01, m23, m03, m02]])
    Xd = X2                                                  # arêtes droites : enfants tous valides
    _, enfants = orienter_tetra(Xd, enfants)
    Y, _ = tetra10_courbes(surface, X, conn)                 # milieux des arêtes de surface posés sur le STL
    volume = lambda Z: np.einsum("ij,ij->i", np.cross(Z[enfants[:, 1]] - Z[enfants[:, 0]], Z[enfants[:, 2]] - Z[enfants[:, 0]]),
                                 Z[enfants[:, 3]] - Z[enfants[:, 0]])
    ref = volume(Xd)
    for _ in range(10):                                      # garde : aucun enfant retourné ni écrasé
        mauvais = volume(Y) < 0.2 * ref
        if not mauvais.any():
            break
        n = np.unique(enfants[mauvais])
        n = n[n >= len(X)]
        Y[n] = Xd[n]
    return Y, enfants


def tetra10_courbes(surface, X, conn):
    """C3D10 dont les nœuds milieux des arêtes de surface sont ramenés sur le STL (point le plus proche), comme Abaqus
    les place sur la géométrie. Un élément qui se retournerait garde ses arêtes droites."""
    X2, conn2 = ef.quadratique(X, conn, "C3D10")
    faces = np.vstack([conn[:, list(f)] for f in ((0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3))])
    _, inv, nb = np.unique(np.sort(faces, 1), axis=0, return_inverse=True, return_counts=True)
    peau = faces[nb[inv.ravel()] == 1]
    aretes_peau = {tuple(sorted(e)) for f in peau for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0]))}
    paires = np.array(ef._T10)
    a_, b_ = conn2[:, paires[:, 0]].ravel(), conn2[:, paires[:, 1]].ravel()
    milieux = conn2[:, 4:].ravel()
    cle = np.c_[np.minimum(a_, b_), np.maximum(a_, b_)]
    sur_peau = np.array([tuple(c) in aretes_peau for c in map(tuple, cle)])
    cibles = np.unique(milieux[sur_peau])
    _, proche = surface.find_closest_cell(X2[cibles], return_closest_point=True)
    # un nœud milieu ne bouge pas de plus d'un quart de la longueur de son arête
    longueur = np.zeros(len(X2))
    longueur[milieux] = np.linalg.norm(X2[a_] - X2[b_], axis=1)
    ok = np.linalg.norm(proche - X2[cibles], axis=1) <= 0.25 * longueur[cibles]
    X3 = X2.copy()
    X3[cibles[ok]] = proche[ok]
    # qualité : rapport min / max du jacobien (4 points de Gauss + 10 nœuds) au moins 0,3, sinon arêtes droites
    el = ef.ELEMENTS["C3D10"]
    points = np.vstack([el.points, el.noeuds_ref])
    for _ in range(10):
        dets = np.stack([np.linalg.det(np.einsum("enj,nk->ejk", X3[conn2], el.dN(xi)[0])) for xi in points], 1)
        mauvais = (dets.min(1) <= 0) | (dets.min(1) < 0.3 * dets.max(1))
        courbes = np.any(X3[conn2[:, 4:]] != X2[conn2[:, 4:]], axis=(1, 2))
        mauvais &= courbes
        if not mauvais.any():
            break
        n = np.unique(conn2[mauvais][:, 4:])
        X3[n] = X2[n]
    return X3, conn2


def _fusionner(X, conn, tol=1e-6):
    """Fusionne les nœuds confondus (même position à tol près) : renvoie (X unique, connectivité renumérotée)."""
    cle = np.round(X / tol).astype(np.int64)
    _, premier, inverse = np.unique(cle, axis=0, return_index=True, return_inverse=True)
    return X[premier], inverse.ravel()[conn]


def subdiviser_hexa(X, conn, k):
    """Raffinement uniforme à géométrie figée : chaque C3D8 est coupé en k × k × k hexaèdres, placés par
    l'interpolation trilinéaire de l'élément de base. La forme du maillage ne change donc pas quand k augmente."""
    if k == 1:
        return X, conn
    el = ef.ELEMENTS["C3D8"]
    t = np.linspace(-1, 1, k + 1)
    R = np.array(np.meshgrid(t, t, t, indexing="ij")).reshape(3, -1).T          # (k+1)³ points de référence
    N = el.N(R)                                                                  # ((k+1)³, 8)
    P = np.einsum("pa,eaj->epj", N, X[conn]).reshape(-1, 3)                       # positions, élément par élément
    idx = np.arange((k + 1) ** 3).reshape(k + 1, k + 1, k + 1)
    I, J, K = (g.ravel() for g in np.meshgrid(np.arange(k), np.arange(k), np.arange(k), indexing="ij"))
    local = np.stack([idx[I, J, K], idx[I + 1, J, K], idx[I + 1, J + 1, K], idx[I, J + 1, K],
                      idx[I, J, K + 1], idx[I + 1, J, K + 1], idx[I + 1, J + 1, K + 1], idx[I, J + 1, K + 1]], 1)
    sous = (np.arange(len(conn))[:, None, None] * (k + 1) ** 3 + local[None]).reshape(-1, 8)
    return _fusionner(P, sous)


def hexa_vers_tetra12(X, conn):
    """Chaque hexaèdre coupé en 12 tétraèdres : chaque face est coupée en 2 triangles par la diagonale qui part de son
    nœud de plus petit numéro (règle globale : les deux hexaèdres voisins choisissent la même diagonale, le maillage
    est conforme), puis chaque triangle est relié à un nœud ajouté au centre de l'hexaèdre."""
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ic = len(X) + np.arange(len(conn))
    Xt = np.vstack([X, X[conn].mean(1)])
    tets = []
    for f in faces:
        a, b, c, d = (conn[:, i] for i in f)
        diag_ac = np.minimum(a, c) < np.minimum(b, d)            # le plus petit numéro est sur la diagonale a-c
        t1 = np.where(diag_ac[:, None], np.c_[a, b, c], np.c_[b, c, d])
        t2 = np.where(diag_ac[:, None], np.c_[a, c, d], np.c_[b, d, a])
        tets += [np.c_[t1, ic], np.c_[t2, ic]]
    return orienter_tetra(Xt, np.vstack(tets))


def qualite_hexa(X, conn):
    """Jacobien relatif minimal de chaque C3D8 (aux 8 coins) : 1 pour un cube parfait, ≤ 0 pour un élément retourné."""
    el = ef.ELEMENTS["C3D8"]
    q = np.full(len(conn), np.inf)
    for a in range(8):
        dN = el.dN(el.noeuds_ref[a])[0]
        J = np.einsum("enj,nk->ejk", X[conn], dN)
        det = np.linalg.det(J)
        norme = np.prod(np.linalg.norm(J, axis=1), axis=1)
        q = np.minimum(q, det / norme)
    return q


# =============================================================================== poutre de validation
def poutre_hexa(L, b, h, m):
    """Poutre [0, L] × [0, b] × [0, h] en hexaèdres : m éléments dans l'épaisseur, autant que nécessaire ailleurs."""
    d = h / m
    nx, ny, nz = int(round(L / d)), int(round(b / d)), m
    x, y, z = np.linspace(0, L, nx + 1), np.linspace(0, b, ny + 1), np.linspace(0, h, nz + 1)
    X = np.array(np.meshgrid(x, y, z, indexing="ij")).reshape(3, -1).T
    idx = np.arange(len(X)).reshape(nx + 1, ny + 1, nz + 1)
    I, J, K = np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij")
    I, J, K = I.ravel(), J.ravel(), K.ravel()
    conn = np.stack([idx[I, J, K], idx[I + 1, J, K], idx[I + 1, J + 1, K], idx[I, J + 1, K],
                     idx[I, J, K + 1], idx[I + 1, J, K + 1], idx[I + 1, J + 1, K + 1], idx[I, J + 1, K + 1]], 1)
    return X, conn


def hexa_vers_tetra(X, conn):
    """Chaque hexaèdre coupé en 6 tétraèdres autour de sa diagonale 1-7 (découpage de Kuhn, conforme)."""
    t = [(0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6)]
    tet = np.vstack([conn[:, list(q)] for q in t])
    return orienter_tetra(X, tet)


def maillage(type_, X8_ou_4, conn):
    """Passe au quadratique si besoin : type_ dans C3D4, C3D10, C3D8, C3D20."""
    if type_ in ef.LINEAIRE:
        return ef.quadratique(X8_ou_4, conn, type_)
    return X8_ou_4, conn
