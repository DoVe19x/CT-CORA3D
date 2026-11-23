"""
ef.py : petit code d'éléments finis 3D (élasticité linéaire) avec les éléments d'Abaqus C3D4, C3D10, C3D8, C3D20.

Rôle    : fonctions de forme et points de Gauss de chaque élément (même ordre des nœuds et même intégration que
          les éléments d'Abaqus du même nom), assemblage de la matrice de rigidité, charge volumique, résolution,
          contraintes aux nœuds (moyennées entre éléments, comme l'affichage par défaut d'Abaqus) et écriture d'un
          fichier .inp lisible par Abaqus.
Unités  : mm, N, MPa.

Les éléments :
  C3D4   tétraèdre linéaire, 4 nœuds, 1 point de Gauss ;
  C3D10  tétraèdre quadratique, 10 nœuds, 4 points ;
  C3D8   hexaèdre linéaire, 8 nœuds, 2 × 2 × 2 points (intégration complète) ;
  C3D20  hexaèdre quadratique « serendipity », 20 nœuds, 3 × 3 × 3 points (intégration complète).
"""
import time
import unicodedata
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


# =============================================================================== éléments
@dataclass
class Element:
    nom: str
    nn: int                     # nombre de nœuds
    noeuds_ref: np.ndarray      # coordonnées naturelles des nœuds (nn × 3), ordre d'Abaqus
    points: np.ndarray          # points de Gauss (G × 3)
    poids: np.ndarray           # poids (G)
    aretes: tuple = ()          # éléments quadratiques : paires de sommets dont le milieu est un nœud

    def N(self, xi):
        return FORMES[self.nom][0](np.atleast_2d(xi))

    def dN(self, xi):
        return FORMES[self.nom][1](np.atleast_2d(xi))


# ----- tétraèdres : coordonnées barycentriques L1 = 1 - ξ - η - ζ, L2 = ξ, L3 = η, L4 = ζ
_dL = np.array([[-1, -1, -1], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)        # dLi/dξ


def _L(xi):
    return np.c_[1 - xi.sum(1), xi]


def _tet4_N(xi):
    return _L(xi)


def _tet4_dN(xi):
    return np.repeat(_dL[None], len(xi), 0)


_T10 = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))      # nœuds 5 à 10 d'Abaqus


def _tet10_N(xi):
    L = _L(xi)
    sommets = L * (2 * L - 1)
    milieux = np.stack([4 * L[:, a] * L[:, b] for a, b in _T10], 1)
    return np.c_[sommets, milieux]


def _tet10_dN(xi):
    L = _L(xi)
    d = np.zeros((len(xi), 10, 3))
    for i in range(4):
        d[:, i, :] = (4 * L[:, i] - 1)[:, None] * _dL[i]
    for k, (a, b) in enumerate(_T10):
        d[:, 4 + k, :] = 4 * (L[:, a][:, None] * _dL[b] + L[:, b][:, None] * _dL[a])
    return d


# ----- hexaèdres
_H8 = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float)
_H20 = np.vstack([_H8, [[0, -1, -1], [1, 0, -1], [0, 1, -1], [-1, 0, -1],
                        [0, -1, 1], [1, 0, 1], [0, 1, 1], [-1, 0, 1],
                        [-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]]])
_A20 = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))


def _hex8_N(xi):
    return np.prod(1 + xi[:, None, :] * _H8[None], axis=2) / 8


def _hex8_dN(xi):
    f = 1 + xi[:, None, :] * _H8[None]                       # (G, 8, 3)
    d = np.empty_like(f)
    for k in range(3):
        autres = [m for m in range(3) if m != k]
        d[:, :, k] = _H8[None, :, k] * f[:, :, autres[0]] * f[:, :, autres[1]] / 8
    return d


def _hex20_facteurs(xi):
    """Pour chaque nœud et chaque direction : facteur (1 + a x) si a = ±1, (1 - x²) si a = 0, et sa dérivée."""
    a = _H20[None]                                           # (1, 20, 3)
    x = xi[:, None, :]                                       # (G, 1, 3)
    f = np.where(a == 0, 1 - x ** 2, 1 + a * x)
    df = np.where(a == 0, -2 * x, a + 0 * x)
    return f, df


def _hex20_N(xi):
    f, _ = _hex20_facteurs(xi)
    p = np.prod(f, axis=2)
    coin = np.all(_H20 != 0, axis=1)
    g = (xi @ _H20.T) - 2                                    # aξ + bη + cζ - 2 (sommets)
    return np.where(coin[None], p * g / 8, p / 4)


def _hex20_dN(xi):
    f, df = _hex20_facteurs(xi)
    coin = np.all(_H20 != 0, axis=1)
    g = (xi @ _H20.T) - 2
    p = np.prod(f, axis=2)
    d = np.empty(f.shape)
    for k in range(3):
        autres = [m for m in range(3) if m != k]
        dp = df[:, :, k] * f[:, :, autres[0]] * f[:, :, autres[1]]
        d[:, :, k] = np.where(coin[None], (dp * g + p * _H20[None, :, k]) / 8, dp / 4)
    return d


FORMES = {"C3D4": (_tet4_N, _tet4_dN), "C3D10": (_tet10_N, _tet10_dN),
          "C3D8": (_hex8_N, _hex8_dN), "C3D20": (_hex20_N, _hex20_dN)}


def _gauss_hex(n):
    x, w = np.polynomial.legendre.leggauss(n)
    P = np.array(np.meshgrid(x, x, x, indexing="ij")).reshape(3, -1).T
    W = np.prod(np.array(np.meshgrid(w, w, w, indexing="ij")).reshape(3, -1).T, axis=1)
    return P, W


_a, _b = 0.5854101966249685, 0.1381966011250105
ELEMENTS = {
    "C3D4": Element("C3D4", 4, np.r_[[[0, 0, 0]], np.eye(3)], np.array([[0.25, 0.25, 0.25]]), np.array([1 / 6])),
    "C3D10": Element("C3D10", 10,
                     np.vstack([np.r_[[[0, 0, 0]], np.eye(3)],
                                [(np.r_[[[0, 0, 0]], np.eye(3)][a] + np.r_[[[0, 0, 0]], np.eye(3)][b]) / 2 for a, b in _T10]]),
                     np.array([[_b, _b, _b], [_a, _b, _b], [_b, _a, _b], [_b, _b, _a]]), np.full(4, 1 / 24), _T10),
    "C3D8": Element("C3D8", 8, _H8, *_gauss_hex(2)),
    "C3D20": Element("C3D20", 20, _H20, *_gauss_hex(3), _A20),
}
LINEAIRE = {"C3D10": "C3D4", "C3D20": "C3D8"}


def quadratique(X, conn, nom):
    """Ajoute un nœud au milieu de chaque arête (arêtes droites) : C3D4 -> C3D10, C3D8 -> C3D20.
    Les nœuds partagés entre éléments voisins sont créés une seule fois."""
    el = ELEMENTS[nom]
    paires = np.array(el.aretes)
    a, b = conn[:, paires[:, 0]], conn[:, paires[:, 1]]
    cle = np.stack([np.minimum(a, b), np.maximum(a, b)], -1).reshape(-1, 2)
    uniques, inv = np.unique(cle, axis=0, return_inverse=True)
    milieux = 0.5 * (X[uniques[:, 0]] + X[uniques[:, 1]])
    ids = len(X) + inv.reshape(len(conn), len(paires))
    return np.vstack([X, milieux]), np.hstack([conn, ids])


# =============================================================================== matériau
def elasticite(E, nu):
    """Matrice de Hooke 6 × 6, ordre d'Abaqus : 11, 22, 33, 12, 13, 23 ; cisaillements en déformation de l'ingénieur."""
    lam, mu = E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[np.arange(3), np.arange(3)] += 2 * mu
    D[3, 3] = D[4, 4] = D[5, 5] = mu
    return D


def matrice_B(dNdx):
    """(e, nn, 3) -> B (e, 6, 3 nn)."""
    e, nn, _ = dNdx.shape
    B = np.zeros((e, 6, 3 * nn))
    x, y, z = dNdx[:, :, 0], dNdx[:, :, 1], dNdx[:, :, 2]
    B[:, 0, 0::3], B[:, 1, 1::3], B[:, 2, 2::3] = x, y, z
    B[:, 3, 0::3], B[:, 3, 1::3] = y, x                     # γ12
    B[:, 4, 0::3], B[:, 4, 2::3] = z, x                     # γ13
    B[:, 5, 1::3], B[:, 5, 2::3] = z, y                     # γ23
    return B


def _jacobien(Xe, dN):
    """Xe (e, nn, 3), dN (nn, 3) -> det J (e), dN/dx (e, nn, 3)."""
    J = np.einsum("enj,nk->ejk", Xe, dN)                     # J[j, k] = dx_j / dξ_k
    det = np.linalg.det(J)
    Jinv = np.linalg.inv(J)                                  # Jinv[k, j] = dξ_k / dx_j
    return det, np.einsum("nk,ekj->enj", dN, Jinv)


def _paquets(n_elem, ndl):
    taille = max(200, int(1.5e7 / ndl ** 2))
    return [slice(i, min(i + taille, n_elem)) for i in range(0, n_elem, taille)]


# =============================================================================== assemblage
def assembler(X, conn, nom, D, b=None, elems_b=None):
    """Matrice de rigidité K (CSR, 3 ddl par nœud, rangés nœud par nœud) et vecteur des forces dues à une charge
    volumique b (N/mm³, vecteur) appliquée aux éléments elems_b. Renvoie aussi le volume de chaque élément."""
    el = ELEMENTS[nom]
    nn, ndl = el.nn, 3 * el.nn
    dN = el.dN(el.points)
    Nf = el.N(el.points)
    ddl = (3 * conn[:, :, None] + np.arange(3)).reshape(len(conn), ndl)
    K = sp.csr_matrix((3 * len(X), 3 * len(X)))
    volume = np.zeros(len(conn))
    f = np.zeros(3 * len(X))
    charge = np.zeros(len(conn), bool)
    if elems_b is not None:
        charge[elems_b] = True
    for s in _paquets(len(conn), ndl):
        Xe = X[conn[s]]
        Ke = np.zeros((Xe.shape[0], ndl, ndl))
        for g in range(len(el.poids)):
            det, dNdx = _jacobien(Xe, dN[g])
            if np.any(det <= 0):
                raise ValueError(f"{nom} : {int((det <= 0).sum())} élément(s) retourné(s) ou dégénéré(s)")
            B = matrice_B(dNdx)
            Ke += (el.poids[g] * det)[:, None, None] * np.matmul(B.transpose(0, 2, 1), D @ B)
            volume[s] += el.poids[g] * det
            if b is not None:
                c = charge[s]
                if c.any():
                    fe = (el.poids[g] * det[c])[:, None, None] * Nf[g][None, :, None] * np.asarray(b)[None, None, :]
                    np.add.at(f, ddl[s][c].reshape(-1), fe.reshape(-1))
        lignes = np.repeat(ddl[s], ndl, axis=1).ravel()
        colonnes = np.tile(ddl[s], (1, ndl)).ravel()
        K = K + sp.csr_matrix((Ke.ravel(), (lignes, colonnes)), shape=K.shape)
    return K, f, volume


# =============================================================================== résolution
def modes_rigides(X):
    """6 déplacements de corps rigide (3 translations, 3 rotations) aux nœuds X : aident le solveur multigrille."""
    c = X - X.mean(0)
    B = np.zeros((3 * len(X), 6))
    for k in range(3):
        B[k::3, k] = 1
    x, y, z = c.T
    B[1::3, 3], B[2::3, 3] = -z, y
    B[0::3, 4], B[2::3, 4] = z, -x
    B[0::3, 5], B[1::3, 5] = -y, x
    return B


def resoudre(K, f, X, fixes, tol=1e-10):
    """Déplacements u (nul aux nœuds fixés). Direct (SuperLU) pour les petits systèmes, gradient conjugué préconditionné
    par multigrille algébrique (pyamg, agrégation lissée) au-delà."""
    libres_n = np.setdiff1d(np.arange(len(X)), fixes)
    libres = (3 * libres_n[:, None] + np.arange(3)).ravel()
    Kf = K[libres][:, libres].tocsr()
    u = np.zeros(3 * len(X))
    info = {"ddl": int(len(libres))}
    t = time.time()
    if len(libres) <= 60_000:
        u[libres] = spla.spsolve(Kf.tocsc(), f[libres])
        info["solveur"] = "direct"
    else:
        import pyamg
        Kf.sum_duplicates()
        Kb = Kf.tobsr(blocksize=(3, 3))
        # pyamg sert seulement de préconditionneur ; le gradient conjugué est celui de scipy (celui de pyamg stagnait
        # puis divergeait sur la poutre en C3D10 de 61 000 ddl ; scipy : 32 itérations, résidu réel 2e-9)
        ml = pyamg.smoothed_aggregation_solver(Kb, B=modes_rigides(X[libres_n]), symmetry="symmetric",
                                               smooth="energy", max_coarse=1000)
        n_it = [0]
        u[libres], _ = spla.cg(Kf, f[libres], M=ml.aspreconditioner(cycle="V"), rtol=tol, maxiter=3000,
                               callback=lambda x: n_it.__setitem__(0, n_it[0] + 1))
        vrai = np.linalg.norm(f[libres] - Kf @ u[libres]) / np.linalg.norm(f[libres])
        info["solveur"] = f"AMG + CG, {n_it[0]} itérations, résidu relatif {vrai:.1e}"
        if vrai > 1e-6:
            raise RuntimeError(f"le solveur itératif n'a pas convergé (résidu relatif {vrai:.1e})")
    info["temps_s"] = round(time.time() - t, 1)
    return u, info


# =============================================================================== contraintes
def contraintes_noeuds(X, conn, nom, D, u):
    """Contraintes évaluées à chaque nœud de chaque élément (σ = D B u), puis moyennées entre les éléments qui
    partagent le nœud (comme l'affichage par défaut d'Abaqus). Renvoie σ (n, 6), ordre 11, 22, 33, 12, 13, 23."""
    el = ELEMENTS[nom]
    dN = el.dN(el.noeuds_ref)                                # (nn, nn, 3) : dérivées évaluées aux nœuds
    somme = np.zeros((len(X), 6))
    nombre = np.zeros(len(X))
    for s in _paquets(len(conn), 3 * el.nn):
        Xe = X[conn[s]]
        ue = u[(3 * conn[s][:, :, None] + np.arange(3)).reshape(Xe.shape[0], -1)]
        for a in range(el.nn):
            _, dNdx = _jacobien(Xe, dN[a])
            sig = np.einsum("ij,ejk,ek->ei", D, matrice_B(dNdx), ue)
            np.add.at(somme, conn[s][:, a], sig)
            np.add.at(nombre, conn[s][:, a], 1)
    return somme / np.maximum(nombre, 1)[:, None]


def von_mises(s):
    s11, s22, s33, s12, s13, s23 = s.T
    return np.sqrt(0.5 * ((s11 - s22) ** 2 + (s22 - s33) ** 2 + (s33 - s11) ** 2) + 3 * (s12 ** 2 + s13 ** 2 + s23 ** 2))


# =============================================================================== Abaqus
def _lignes(valeurs, n=16):
    """Données d'un mot-clé Abaqus : 16 valeurs au plus par ligne ; une ligne qui finit par une virgule continue."""
    out = []
    for i in range(0, len(valeurs), n):
        out.append(", ".join(str(v) for v in valeurs[i:i + n]) + ("," if i + n < len(valeurs) else ""))
    return out


def ecrire_inp(chemin, X, conn, nom, E, nu, fixes, elems_charge, b, elems_milieu, titre):
    """Fichier .inp Abaqus/Standard : nœuds, éléments, ensembles ENCASTREMENT (nœuds), CHARGE et MILIEU
    (éléments), matériau, charge volumique (*Dload BX, BY, BZ), un pas statique linéaire."""
    L = [f"*Heading\n {titre}", "** Fichier écrit par CT-CORA3D (etude_convergence). Unités : mm, N, MPa.",
         "** Repère : axes principaux du tibia, x = axe de l'os (vers le genou).", "*Node"]
    L += [f"{i + 1}, {x:.6f}, {y:.6f}, {z:.6f}" for i, (x, y, z) in enumerate(X)]
    L.append(f"*Element, type={nom}, elset=OS")
    for i, e in enumerate(conn):
        L += _lignes([i + 1] + [int(n) + 1 for n in e])
    L.append("*Nset, nset=ENCASTREMENT")
    L += _lignes([int(n) + 1 for n in fixes])
    L.append("*Elset, elset=CHARGE")
    L += _lignes([int(e) + 1 for e in elems_charge])
    L.append("*Elset, elset=MILIEU")
    L += _lignes([int(e) + 1 for e in elems_milieu])
    L += ["*Solid Section, elset=OS, material=OS_HOMOGENE", ",", "*Material, name=OS_HOMOGENE", "*Elastic",
          f"{E:.1f}, {nu}", "*Step, name=CHARGE, nlgeom=NO", "*Static", "*Boundary", "ENCASTREMENT, ENCASTRE",
          "*Dload"] + [f"CHARGE, B{c}, {v:.9e}" for c, v in zip("XYZ", b)] + [
          "*Output, field, variable=PRESELECT", "*Output, history, variable=PRESELECT", "*End Step"]
    texte = unicodedata.normalize("NFKD", "\n".join(L) + "\n").encode("ascii", "ignore").decode("ascii")
    with open(chemin, "w", encoding="ascii") as fichier:      # Abaqus : fichier en ASCII (accents retirés)
        fichier.write(texte)
