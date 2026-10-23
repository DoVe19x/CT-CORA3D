#!/usr/bin/env python3
"""
generate_bones.py
-----------------
Génération procédurale des os du membre pelvien canin (côté droit, chien type
Labrador ~30 kg) par fonctions de distance signée (SDF) + marching cubes.

Pourquoi des SDF ?
  * on assemble des primitives (sphères, ellipsoïdes, cônes arrondis, tubes à
    section elliptique...) par unions/soustractions LISSES -> formes organiques ;
  * le maillage obtenu est étanche (watertight) par construction ;
  * chaque repère anatomique est connu exactement (centre de la tête fémorale,
    condyles, plateau tibial...) : idéal pour la validation par déformités
    synthétiques (niveau 1 de la stratégie de validation du projet).

Le modèle sain est calibré sur les valeurs de référence publiées :
  fémur  : aLPFA 103°, aLDFA 97° (Tomlinson 2007, Labrador), antéversion ~31° (CT)
  tibia  : mMPTA 93.4°, mMDTA 96.3° (Dismukes 2007), mCaPTA 63.8°, mCrDTA 81.7°
           (Dismukes 2008)

Repère local de chaque os (côté droit) : X latéral, Y proximal, Z caudal (mm).

Usage :
  python generate_bones.py                 # génère build/bones_pack.*
  python generate_bones.py --preview femur # rendu PNG de contrôle
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import math
import time
from pathlib import Path

import numpy as np
import pyvista as pv
from scipy.interpolate import PchipInterpolator

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"


# =============================================================================
# 1. Primitives SDF vectorisées (p : tableau (..., 3))
# =============================================================================

def _dot(a, b):
    return np.einsum("...i,...i->...", a, b)


def _len(v):
    return np.sqrt(_dot(v, v))


def normalize(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def rot(axis, deg):
    """Matrice de rotation (formule de Rodrigues)."""
    a = normalize(axis)
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + s * K + (1 - c) * K @ K


def sphere(c, r):
    c = np.asarray(c, float)
    return lambda p: _len(p - c) - r


def ellipsoid(c, radii, R=None):
    """Distance approchée à un ellipsoïde (borne d'I. Quilez). R : colonnes = axes locaux."""
    c = np.asarray(c, float)
    r = np.asarray(radii, float)

    def f(p):
        q = p - c
        if R is not None:
            q = q @ R
        q = q + 1e-5
        k0 = _len(q / r)
        k1 = _len(q / (r * r))
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
    return f


def round_cone(a, b, ra, rb):
    """Cône arrondi exact entre a (rayon ra) et b (rayon rb) — I. Quilez."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ba = b - a
    l2 = float(ba @ ba)
    rr = ra - rb
    a2 = l2 - rr * rr
    il2 = 1.0 / l2

    def f(p):
        pa = p - a
        y = pa @ ba
        z = y - l2
        w = pa * l2 - y[..., None] * ba
        x2 = _dot(w, w)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        d1 = np.sqrt(x2 + z2) * il2 - rb
        d2 = np.sqrt(x2 + y2) * il2 - ra
        d3 = (np.sqrt(np.maximum(x2 * a2 * il2, 0.0)) + y * rr) * il2 - ra
        return np.where(np.sign(z) * a2 * z2 > k, d1, np.where(np.sign(y) * a2 * y2 < k, d2, d3))
    return f


def capsule(a, b, r):
    return round_cone(a, b, r, r)


def chain(points, radii):
    """Union de cônes arrondis le long d'une polyligne (rayons variables)."""
    parts = [round_cone(points[i], points[i + 1], radii[i], radii[i + 1]) for i in range(len(points) - 1)]

    def f(p):
        d = parts[0](p)
        for g in parts[1:]:
            d = np.minimum(d, g(p))
        return d
    return f


def rbox(c, half, R=None, r=0.0):
    """Boîte à arêtes arrondies (rayon r)."""
    c = np.asarray(c, float)
    h = np.asarray(half, float) - r

    def f(p):
        q = p - c
        if R is not None:
            q = q @ R
        q = np.abs(q) - h
        return _len(np.maximum(q, 0.0)) + np.minimum(np.max(q, axis=-1), 0.0) - r
    return f


def wheel(c, radius, halfw, rb, R=None):
    """Roue (cylindre arrondi) d'axe X local : condyles, trochlées."""
    c = np.asarray(c, float)

    def f(p):
        q = p - c
        if R is not None:
            q = q @ R
        dr = np.sqrt(q[..., 1] ** 2 + q[..., 2] ** 2) - (radius - rb)
        da = np.abs(q[..., 0]) - (halfw - rb)
        return (np.minimum(np.maximum(dr, da), 0.0)
                + np.sqrt(np.maximum(dr, 0.0) ** 2 + np.maximum(da, 0.0) ** 2) - rb)
    return f


def halfspace(point, normal):
    """Demi-espace : négatif du côté opposé à la normale."""
    point = np.asarray(point, float)
    n = normalize(normal)
    return lambda p: (p - point) @ n


def smin(a, b, k):
    """Union lisse (polynomiale)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


class Tube:
    """Cylindre généralisé d'axe ~Y : centre (cx, cz)(y), demi-axes (ax, az)(y).

    Sert pour les diaphyses (section elliptique variable, courbure physiologique)
    et pour le canal médullaire.
    """

    def __init__(self, ys, cx, cz, ax, az, y0, y1, end_k=0.0):
        self.ys = np.asarray(ys, float)
        self.fcx = PchipInterpolator(ys, cx)
        self.fcz = PchipInterpolator(ys, cz)
        self.fax = PchipInterpolator(ys, ax)
        self.faz = PchipInterpolator(ys, az)
        self.y0, self.y1, self.end_k = y0, y1, end_k

    def center(self, y):
        y = np.clip(y, self.ys[0], self.ys[-1])
        return np.stack([self.fcx(y), y, self.fcz(y)], axis=-1)

    def __call__(self, p):
        y = np.clip(p[..., 1], self.ys[0], self.ys[-1])
        dx = p[..., 0] - self.fcx(y) + 1e-5
        dz = p[..., 2] - self.fcz(y)
        ax = self.fax(y)
        az = self.faz(y)
        k0 = np.sqrt((dx / ax) ** 2 + (dz / az) ** 2)
        k1 = np.sqrt((dx / ax ** 2) ** 2 + (dz / az ** 2) ** 2)
        d = k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
        dend = np.maximum(self.y0 - p[..., 1], p[..., 1] - self.y1)
        if self.end_k > 0:
            return smax(d, dend, self.end_k)
        return np.maximum(d, dend)


class Noise:
    """Bruit lisse (somme de sinusoïdes 3D) : irrégularités sub-millimétriques
    de la surface osseuse, pour un rendu organique."""

    def __init__(self, seed, n=40, lam=(9.0, 42.0), amp=0.13):
        rng = np.random.default_rng(seed)
        d = rng.normal(size=(n, 3))
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        lams = rng.uniform(lam[0], lam[1], size=n)
        self.k = d * (2 * np.pi / lams)[:, None]
        self.ph = rng.uniform(0, 2 * np.pi, size=n)
        self.a = np.full(n, amp / math.sqrt(n / 2.0))

    def __call__(self, p):
        return np.sin(p @ self.k.T + self.ph) @ self.a


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# =============================================================================
# 2. Définition des os
# =============================================================================
# Chaque os : dict(sdf, bbox, h (voxel), tris (cible), cart (masque cartilage),
#                  canal (sdf du canal médullaire ou None), landmarks (fonction))

# ---------------------------------------------------------------- FÉMUR -----
FEMUR = {}


def build_femur():
    # Tête fémorale : inclinaison projetée ~134°, antéversion ~31°
    H = np.array([-14.0, 191.0, -5.0])
    AA = math.radians(31.0)
    incl_rise = math.tan(math.radians(134.0 - 90.0))
    d_neck = normalize([-math.cos(AA), incl_rise * math.cos(AA), -math.sin(AA)])
    N = H - 23.0 * d_neck                    # base du col

    bow = 3.0                                 # procurvatum physiologique (mm)
    ys = np.array([10, 18, 30, 45, 60, 80, 100, 125, 150, 165, 178, 188], float)
    cx = np.array([-3.5, -3.5, -3.4, -2.6, -1.5, -0.5, 0.0, 0.0, 0.0, 0.5, 1.5, 2.0])
    cz0 = np.array([3.0, 3.0, 2.6, 1.4, 0.6, 0.2, 0.0, 0.0, 0.0, 0.3, 1.0, 1.5])
    bowv = np.where((ys > 30) & (ys < 175), -bow * np.sin(np.pi * (ys - 30) / 145.0), 0.0)
    cz = cz0 + bowv
    ax = np.array([16.0, 15.5, 14.5, 11.5, 9.0, 7.9, 7.6, 7.5, 7.8, 9.3, 10.5, 9.5])
    az = np.array([12.5, 12.0, 11.5, 9.5, 8.0, 7.3, 7.0, 7.0, 7.2, 8.4, 9.0, 8.5])
    shaft = Tube(ys, cx, cz, ax, az, 8.0, 181.0, end_k=8.0)
    canal = Tube(ys, cx, cz, ax - 2.7, az - 2.7, 52.0, 162.0, end_k=12.0)

    head = sphere(H, 11.0)
    neck = round_cone(N, H, 7.8, 6.6)
    neck2 = round_cone(N + np.array([2.0, -7.0, 0.5]), N, 9.0, 7.8)
    gt_body = ellipsoid([11.0, 184.0, 4.0], [7.0, 12.0, 8.5])
    gt_tip = round_cone([8.5, 175.0, 3.5], [15.0, 192.6, 4.0], 7.5, 5.0)
    fossa = ellipsoid([5.5, 187.0, 10.0], [4.0, 7.0, 4.2])
    lt = ellipsoid([-7.0, 164.0, 6.8], [3.6, 6.5, 3.6])
    t3 = ellipsoid([8.6, 158.0, 0.8], [2.4, 7.0, 3.2])
    f_dir = normalize([-0.7, 0.45, 0.55])
    fovea = sphere(H + 11.6 * f_dir, 2.2)

    Cm = np.array([-14.5, 13.85, 6.5])       # condyle médial (plus haut)
    Cl = np.array([7.5, 11.15, 6.5])         # condyle latéral (plus bas) -> aLDFA 97°
    cond_m = ellipsoid(Cm, [7.2, 12.5, 12.8])
    cond_l = ellipsoid(Cl, [7.2, 12.5, 12.8])
    ridge_m = round_cone([-11.0, 45.0, -4.6], [-11.2, 15.0, -9.6], 1.6, 4.6)
    ridge_l = round_cone([4.0, 45.5, -4.6], [4.4, 15.0, -9.8], 1.8, 4.8)
    troch_fill = ellipsoid([-3.5, 28.0, -3.5], [11.0, 19.0, 7.5])
    groove = round_cone([-3.4, 52.0, -15.8], [-3.4, 12.0, -17.4], 5.6, 6.6)
    notch = ellipsoid([-3.5, 7.5, 13.5], [4.2, 11.0, 11.0])
    epi_m = ellipsoid([-19.0, 14.5, 4.0], [2.4, 5.5, 4.5])
    epi_l = ellipsoid([12.2, 13.0, 4.0], [2.4, 5.5, 4.5])
    sup_m = ellipsoid([-11.0, 27.0, 12.6], [2.4, 4.0, 2.2])
    sup_l = ellipsoid([4.5, 27.5, 13.0], [2.8, 4.4, 2.4])
    noise = Noise(11, amp=0.14)

    def outer(p):
        d = shaft(p)
        # --- extrémité proximale
        d = smin(d, neck2(p), 5.0)
        d = smin(d, neck(p), 3.0)
        d = smin(d, head(p), 2.6)
        d = smin(d, gt_body(p), 6.0)
        d = smin(d, gt_tip(p), 4.0)
        d = smax(d, -fossa(p), 3.5)
        d = smin(d, lt(p), 5.0)
        d = smin(d, t3(p), 3.0)
        d = smax(d, -fovea(p), 1.2)
        # --- extrémité distale
        d = smin(d, cond_m(p), 5.0)
        d = smin(d, cond_l(p), 5.0)
        d = smin(d, troch_fill(p), 5.0)
        d = smin(d, ridge_m(p), 6.0)
        d = smin(d, ridge_l(p), 6.0)
        d = smax(d, -groove(p), 2.0)
        d = smax(d, -notch(p), 1.5)
        d = smin(d, epi_m(p), 5.0)
        d = smin(d, epi_l(p), 5.0)
        d = smin(d, sup_m(p), 4.0)
        d = smin(d, sup_l(p), 4.0)
        return d + noise(p)

    def sdf(p):
        return np.maximum(outer(p), -canal(p))

    def cart(p):
        # tête fémorale
        m_head = (_len(p - H) < 11.9) & (((p - H) @ d_neck) > -3.0) & (_len(p - (H + 11.0 * f_dir)) > 3.0)
        # condyles : faces distale et caudale
        m_c = np.zeros(len(p), bool)
        for C in (Cm, Cl):
            dist = np.abs(ellipsoid(C, [7.2, 12.5, 12.8])(p))
            m_c |= (dist < 1.6) & ((p[:, 1] < C[1] + 3.0) | (p[:, 2] > C[2] + 2.0)) & (np.abs(p[:, 0] - C[0]) < 6.0)
        # trochlée (face craniale)
        m_t = (p[:, 2] < -6.5) & ((((p[:, 0] + 3.4) / 10.8) ** 2 + ((p[:, 1] - 25.0) / 20.5) ** 2) < 1.0)
        return (m_head | m_c | m_t).astype(float)

    def landmarks(v):
        L = {}
        L["head_center"] = H
        L["neck_base"] = N
        sel = (v[:, 0] > 8.0) & (v[:, 1] > 182.0)
        L["gt_tip"] = v[sel][np.argmax(v[sel][:, 1])]
        sel = (v[:, 1] > 154) & (v[:, 1] < 174) & (v[:, 0] < -3.0) & (v[:, 2] > 2.0)
        L["lt_tip"] = v[sel][np.argmax(-v[sel][:, 0] + v[sel][:, 2])]
        for side, C in (("med", Cm), ("lat", Cl)):
            sel = (np.abs(v[:, 0] - C[0]) < 4.0) & (v[:, 1] < 16.0)
            L[f"cond_{side}_dist"] = v[sel][np.argmin(v[sel][:, 1])]
            sel = (np.abs(v[:, 0] - C[0]) < 4.0) & (v[:, 1] < 26.0)
            L[f"cond_{side}_caud"] = v[sel][np.argmax(v[sel][:, 2])]
            L[f"cond_{side}_center"] = C
        sel = (v[:, 0] < -15.0) & (v[:, 1] < 30.0)       # épicondyle médial (et non la tête fémorale !)
        L["epi_med"] = v[sel][np.argmin(v[sel][:, 0])]
        sel = v[:, 0] > 10.0
        sel &= v[:, 1] < 30
        L["epi_lat"] = v[sel][np.argmax(v[sel][:, 0])]
        for name, yy in (("troch_prox", 42.0), ("troch_dist", 18.0)):
            sel = (np.abs(v[:, 0] + 3.5) < 1.5) & (np.abs(v[:, 1] - yy) < 1.5) & (v[:, 2] < -6.0)
            L[name] = v[sel][np.argmax(v[sel][:, 2])]
        L["knee_center"] = 0.5 * (L["cond_med_dist"] + L["cond_lat_dist"])
        return L

    FEMUR.update(dict(H=H, N=N, d_neck=d_neck, Cm=Cm, Cl=Cl, shaft=shaft))
    return dict(name="femur", sdf=sdf, outer=outer, canal=canal,
                bbox=([-30.0, 2.0 - 10.0, -28.0], [26.0, 207.0, 27.0]),
                h=0.42, tris=64000, cart=cart, landmarks=landmarks)


# ---------------------------------------------------------------- TIBIA -----
TIBIA = {}

FIB_HEAD = ([18.6, 182.5, 12.0], [4.2, 5.8, 3.8])
FIB_MALL = ([15.6, 0.0, 0.6], [3.6, 7.5, 5.5])


def build_tibia():
    # plateau : pente caudale TPA 26.2° (mCaPTA 63.8°), inclinaison frontale 3.4° (mMPTA 93.4°)
    Rp = rot([0, 0, 1], -1.8) @ rot([1, 0, 0], 26.2)
    Xp, Yp, Zp = Rp[:, 0], Rp[:, 1], Rp[:, 2]
    P0 = np.array([0.0, 199.0, -0.8])
    cm_c = P0 - 10.0 * Xp + 2.5 * Zp           # centre de la facette médiale
    cl_c = P0 + 10.0 * Xp + 3.5 * Zp           # centre de la facette latérale

    ys = np.array([8, 12, 22, 35, 55, 80, 110, 140, 160, 175, 186, 194], float)
    cx = np.array([0.4, 0.4, 0.6, 0.6, 0.5, 0.2, 0.0, 0.0, 0.0, 0.2, 0.4, 0.5])
    cz = np.array([-0.3, -0.3, -0.4, -0.6, -0.8, -0.6, -0.2, 0.5, 1.4, 2.2, 2.4, 2.4])
    ax = np.array([11.0, 10.6, 9.0, 7.6, 6.9, 6.7, 6.9, 7.4, 8.6, 11.0, 13.5, 14.0])
    az = np.array([9.0, 8.8, 7.8, 7.0, 6.5, 6.5, 6.8, 7.3, 8.3, 10.0, 11.0, 11.0])
    shaft = Tube(ys, cx, cz, ax, az, 6.0, 190.0, end_k=8.0)
    canal = Tube(ys, cx, cz, ax - 2.5, az - 2.5, 40.0, 160.0, end_k=12.0)

    cond_m = ellipsoid(P0 - 10.0 * Xp - 6.5 * Yp + 2.5 * Zp, [10.5, 7.0, 14.5], R=Rp)
    cond_l = ellipsoid(P0 + 10.0 * Xp - 6.5 * Yp + 3.5 * Zp, [10.0, 7.0, 13.0], R=Rp)
    inter = ellipsoid(P0 - 7.0 * Yp + 1.0 * Zp, [9.0, 6.5, 11.0], R=Rp)
    dish_m = sphere(cm_c + (30.0 - 1.0) * Yp + 0.5 * Yp, 30.0)
    dish_l = sphere(cl_c + (30.0 - 1.0) * Yp + 0.5 * Yp, 30.0)
    tub_m = ellipsoid(P0 - 2.4 * Xp + 1.4 * Yp + 0.5 * Zp, [1.6, 2.5, 3.6], R=Rp)
    tub_l = ellipsoid(P0 + 2.4 * Xp + 1.2 * Yp + 0.5 * Zp, [1.6, 2.3, 3.6], R=Rp)
    tuberosity = ellipsoid([0.5, 188.0, -18.0], [4.6, 9.0, 5.6], R=rot([1, 0, 0], -16))
    crest = chain([[0.5, 184.0, -18.0], [0.0, 160.0, -13.0], [-0.5, 128.0, -8.3]], [4.4, 2.9, 1.8])
    ext_groove = capsule([12.6, 198.5, -10.2], [13.4, 188.0, -14.2], 2.4)
    popliteal = ellipsoid([0.0, 194.5, 16.5], [4.5, 7.0, 5.0])

    # extrémité distale : cochlée inclinée (mMDTA 96.3°, mCrDTA 81.7°)
    Rd = rot([0, 0, 1], 6.3) @ rot([1, 0, 0], 8.3)
    epi = ellipsoid(Rd @ np.array([0.4, 6.0, 0.4]), [11.2, 7.5, 9.2], R=Rd)
    g_m = wheel(Rd @ np.array([-4.7, -9.0, 0.0]), 10.6, 2.9, 2.6, R=Rd)
    g_l = wheel(Rd @ np.array([4.9, -9.0, 0.0]), 10.6, 2.9, 2.6, R=Rd)
    mall_m = ellipsoid([-10.8, -2.4, 0.6], [3.0, 6.0, 5.2])

    fib_head = ellipsoid(*FIB_HEAD)
    fib_mall = ellipsoid(*FIB_MALL)
    noise = Noise(23, amp=0.14)

    def outer(p):
        d = shaft(p)
        d = smin(d, inter(p), 7.0)
        d = smin(d, cond_m(p), 5.0)
        d = smin(d, cond_l(p), 5.0)
        d = smax(d, -dish_m(p), 1.5)
        d = smax(d, -dish_l(p), 1.5)
        d = smin(d, tub_m(p), 2.0)
        d = smin(d, tub_l(p), 2.0)
        d = smin(d, tuberosity(p), 7.0)
        d = smin(d, crest(p), 6.0)
        d = smax(d, -ext_groove(p), 3.0)
        d = smax(d, -popliteal(p), 2.5)
        d = smin(d, epi(p), 6.0)
        d = smax(d, -g_m(p), 0.8)
        d = smax(d, -g_l(p), 0.8)
        d = smin(d, mall_m(p), 4.0)
        d = smax(d, -(fib_head(p) - 0.6), 1.2)
        d = smax(d, -(fib_mall(p) - 0.6), 1.2)
        return d + noise(p)

    def sdf(p):
        return np.maximum(outer(p), -canal(p))

    def cart(p):
        q = (p - P0) @ Rp
        top = q[:, 1] > -2.6
        fm = (((q[:, 0] + 10.0) / 9.2) ** 2 + ((q[:, 2] - 2.5) / 13.0) ** 2) < 1.0
        fl = (((q[:, 0] - 10.0) / 8.6) ** 2 + ((q[:, 2] - 3.5) / 11.5) ** 2) < 1.0
        loc = p @ Rd
        m_dist = (loc[:, 1] < 2.6) & (loc[:, 1] > -2.2) & (np.abs(loc[:, 0] - 0.1) < 8.6)
        m_mall = (p[:, 0] < -7.6) & (p[:, 0] > -10.4) & (p[:, 1] < 3.0)
        return ((top & (fm | fl)) | m_dist | m_mall).astype(float)

    def landmarks(v):
        L = {}
        loc = (v - P0) @ Rp
        for side, sx in (("med", -1.0), ("lat", 1.0)):
            sel = (np.abs(loc[:, 0] - sx * 2.6) < 1.2) & (np.abs(loc[:, 2] - 0.5) < 2.5)
            L[f"tub_{side}"] = v[sel][np.argmax(loc[sel][:, 1])]
            # même niveau crânio-caudal pour les deux condyles : sinon la pente
            # caudale du plateau (26°) se projette en fausse inclinaison frontale
            sel = (np.abs(loc[:, 0] - sx * 10.0) < 1.4) & (np.abs(loc[:, 2] - 3.0) < 1.0) & (loc[:, 1] > -4)
            L[f"plat_{side}"] = v[sel][np.argmin(loc[sel][:, 1])]      # fond de la concavité
        # ligne du plateau (sagittal, condyle médial) : bords crânial / caudal
        sel = (np.abs(loc[:, 0] + 10.0) < 1.5) & (loc[:, 1] > -3.0)
        L["plat_cran"] = v[sel][np.argmin(loc[sel][:, 2])]
        L["plat_caud"] = v[sel][np.argmax(loc[sel][:, 2])]
        L["eminence"] = 0.5 * (L["tub_med"] + L["tub_lat"])
        sel = (v[:, 1] > 178)
        for side, sx in (("med", -1.0), ("lat", 1.0)):
            s2 = sel & (sx * v[:, 0] > 5.0)
            L[f"caud_{side}"] = v[s2][np.argmax(v[s2][:, 2])]
        sel = (v[:, 1] > 172) & (v[:, 2] < -10)
        L["tuberosity"] = v[sel][np.argmin(v[sel][:, 2])]
        locd = v @ Rd
        for side, gx in (("med", -4.7), ("lat", 4.9)):
            sel = (np.abs(locd[:, 0] - gx) < 1.0) & (np.abs(locd[:, 2]) < 2.5) & (locd[:, 1] < 4)
            L[f"groove_{side}"] = v[sel][np.argmax(locd[sel][:, 1])]
        L["distal_center"] = 0.5 * (L["groove_med"] + L["groove_lat"])
        sel = (np.abs(locd[:, 0] - 0.1) < 3.0) & (locd[:, 1] < 4.5) & (locd[:, 1] > -4)
        L["dist_cran"] = v[sel][np.argmin(locd[sel][:, 2])]
        L["dist_caud"] = v[sel][np.argmax(locd[sel][:, 2])]
        sel = v[:, 0] < -7.0
        L["mall_med"] = v[sel][np.argmin(v[sel][:, 1])]
        return L

    TIBIA.update(dict(Rp=Rp, P0=P0, Rd=Rd, shaft=shaft))
    return dict(name="tibia", sdf=sdf, outer=outer, canal=canal,
                bbox=([-24.0, -14.0, -31.0], [27.0, 212.0, 33.0]),
                h=0.42, tris=64000, cart=cart, landmarks=landmarks)


def build_fibula():
    head = ellipsoid(*FIB_HEAD)
    shaft = chain([[18.0, 178.0, 11.0], [16.0, 160.0, 8.2], [14.6, 120.0, 5.0],
                   [13.6, 80.0, 3.0], [13.4, 42.0, 1.6], [14.6, 14.0, 0.8], [15.4, 5.0, 0.6]],
                  [2.9, 2.4, 2.1, 2.0, 2.2, 2.9, 3.4])
    mall = ellipsoid(*FIB_MALL)
    noise = Noise(31, amp=0.1)

    def sdf(p):
        d = smin(shaft(p), head(p), 3.0)
        d = smin(d, mall(p), 3.0)
        return d + noise(p)

    def landmarks(v):
        sel = v[:, 1] < 20
        return {"mall_lat": v[sel][np.argmin(v[sel][:, 1])],
                "fib_head": np.array(FIB_HEAD[0])}

    return dict(name="fibula", sdf=sdf, bbox=([8.0, -11.0, -7.0], [24.0, 192.0, 19.0]),
                h=0.35, tris=9000, cart=None, landmarks=landmarks)


def build_patella():
    body = ellipsoid([-3.5, 42.5, -19.8], [6.6, 10.5, 4.8])
    apex = round_cone([-3.5, 40.0, -19.8], [-3.5, 30.5, -19.3], 5.6, 2.2)
    ridge = capsule([-3.5, 48.0, -15.6], [-3.5, 35.0, -15.6], 1.5)
    noise = Noise(41, amp=0.1)

    def sdf(p):
        return smin(smin(body(p), apex(p), 3.0), ridge(p), 2.0) + noise(p)

    def cart(p):
        return (p[:, 2] > -16.5).astype(float)

    return dict(name="patella", sdf=sdf, bbox=([-12.0, 26.0, -27.0], [5.0, 55.0, -12.0]),
                h=0.25, tris=4000, cart=cart,
                landmarks=lambda v: {"center": np.array([-3.5, 41.5, -19.6])})


def build_fabellae():
    lat = ellipsoid([7.5, 29.5, 21.6], [3.8, 5.5, 3.6])
    med = ellipsoid([-14.5, 29.0, 20.6], [2.8, 4.0, 2.8])
    noise = Noise(43, amp=0.08)

    def sdf(p):
        return np.minimum(lat(p), med(p)) + noise(p)

    return dict(name="fabellae", sdf=sdf, bbox=([-19.0, 22.0, 15.0], [13.0, 37.0, 27.0]),
                h=0.25, tris=2400, cart=None, landmarks=lambda v: {})


# ---------------------------------------------------------------- TARSE -----
# Repère tarsien : origine au centre de la trochlée du talus (pivot du jarret)

def build_talus():
    r_m = wheel([-4.7, 0.0, 0.0], 9.9, 2.9, 2.6)
    r_l = wheel([4.9, 0.0, 0.0], 9.9, 2.9, 2.6)
    g = wheel([0.1, 0.0, 0.0], 7.0, 2.4, 1.6)
    body = rbox([0.0, -6.5, 0.8], [8.5, 6.0, 8.0], r=3.5)
    neck = round_cone([-1.5, -11.0, -1.5], [-4.0, -18.0, -4.0], 6.0, 6.3)
    head = ellipsoid([-4.5, -20.5, -4.5], [7.5, 5.0, 6.5])
    calc = calcaneus_sdf()
    noise = Noise(51, amp=0.12)

    def sdf(p):
        d = np.minimum(np.minimum(r_m(p), r_l(p)), g(p))
        d = smin(d, body(p), 3.0)
        d = smin(d, neck(p), 3.0)
        d = smin(d, head(p), 3.0)
        d = smax(d, -(calc(p) - 0.6), 1.0)
        return d + noise(p)

    def cart(p):
        top = (p[:, 1] > -3.0) & (np.abs(p[:, 0]) < 8.5)
        hd = (p[:, 1] < -22.0)
        return (top | hd).astype(float)

    return dict(name="talus", sdf=sdf, bbox=([-14.0, -28.0, -13.0], [11.0, 12.0, 12.0]),
                h=0.3, tris=9000, cart=cart,
                landmarks=lambda v: {"trochlea_center": np.zeros(3)})


def calcaneus_sdf():
    tuber = ellipsoid([4.5, 25.0, 22.5], [6.5, 8.5, 7.5])
    body = chain([[4.5, 22.0, 21.0], [6.0, 6.0, 15.5], [7.0, -10.0, 13.0], [7.5, -21.0, 9.5]],
                 [6.0, 5.2, 5.6, 5.8])
    dist = ellipsoid([7.5, -24.0, 8.5], [5.5, 4.5, 6.0])
    sust = ellipsoid([-3.5, -6.0, 11.0], [6.0, 3.0, 4.5])
    corac = ellipsoid([11.0, -8.0, 4.0], [2.2, 4.5, 3.6])

    def f(p):
        d = smin(tuber(p), body(p), 4.0)
        d = smin(d, dist(p), 3.0)
        d = smin(d, sust(p), 3.0)
        d = smin(d, corac(p), 4.5)
        return d
    return f


def build_calcaneus():
    base = calcaneus_sdf()
    noise = Noise(53, amp=0.15)

    def sdf(p):
        return base(p) + noise(p)

    def landmarks(v):
        return {"tuber": v[np.argmax(v[:, 1])]}

    return dict(name="calcaneus", sdf=sdf, bbox=([-11.0, -30.0, 0.0], [17.0, 35.0, 31.0]),
                h=0.32, tris=9000, cart=None, landmarks=landmarks)


def build_tarsals():
    parts = [
        rbox([-4.0, -29.8, -3.5], [6.4, 3.2, 6.8], r=2.95),   # os tarsien central
        rbox([7.6, -38.0, 6.0], [4.8, 8.0, 6.8], r=4.3),      # T4
        rbox([-1.6, -38.0, -4.0], [3.9, 3.2, 6.0], r=2.95),   # T3
        rbox([-8.4, -37.8, -2.5], [2.7, 3.2, 4.6], r=2.5),    # T2
        rbox([-12.1, -36.6, 3.5], [1.7, 4.0, 2.8], r=1.6),    # T1
    ]
    calc = calcaneus_sdf()
    noise = Noise(57, amp=0.1)

    def sdf(p):
        d = parts[0](p)
        for f in parts[1:]:
            d = np.minimum(d, f(p))
        d = smax(d, -(calc(p) - 0.5), 1.0)
        return d + noise(p)

    return dict(name="tarsals", sdf=sdf, bbox=([-16.0, -48.0, -12.0], [15.0, -24.0, 15.0]),
                h=0.3, tris=9000, cart=None, landmarks=lambda v: {})


MT = [  # base, extrémité distale de la diaphyse, centre de tête, rayons (base, distal), rayon de tête
    ([-9.6, -44.4, -2.0], [-11.4, -107.5, -4.2], [-11.6, -110.6, -4.0], 2.9, 2.3, 3.8),
    ([-2.9, -44.6, -3.5], [-3.8, -114.5, -5.0], [-3.9, -118.0, -4.8], 3.2, 2.6, 4.2),
    ([3.8, -49.3, -2.5], [3.9, -115.0, -4.6], [4.0, -118.4, -4.4], 3.2, 2.6, 4.2),
    ([10.6, -49.6, 0.5], [11.6, -108.0, -2.4], [11.8, -111.2, -2.2], 2.9, 2.3, 3.8),
]


def build_metatarsals():
    parts = []
    for i, (b, e, hc, rb_, re_, rh) in enumerate(MT):
        b = np.array(b)
        e = np.array(e)
        hc = np.array(hc)
        base = ellipsoid(b, [rb_ + 0.5, 3.3, 5.2])
        shaft = round_cone(b + [0, -1.0, 0], e, rb_, re_)
        head = sphere(hc, rh)
        ridge = ellipsoid(hc + [0.0, 0.0, 2.2], [1.2, 3.4, 2.6])
        parts.append((base, shaft, head, ridge))
    tub5 = ellipsoid([13.6, -50.0, 2.0], [2.0, 3.5, 3.0])
    noise = Noise(61, amp=0.08)

    def sdf(p):
        d = None
        for base, shaft, head, ridge in parts:
            di = smin(base(p), shaft(p), 3.0)
            di = smin(di, head(p), 2.5)
            di = smin(di, ridge(p), 1.5)
            d = di if d is None else np.minimum(d, di)
        d = np.minimum(d, smin(d, tub5(p), 2.0))
        return d + noise(p)

    def landmarks(v):
        return {f"mt{i + 2}_head": np.array(MT[i][2]) for i in range(4)}

    return dict(name="metatarsals", sdf=sdf, bbox=([-17.0, -124.0, -11.0], [17.0, -40.0, 9.0]),
                h=0.32, tris=16000, cart=None, landmarks=landmarks)


def build_phalanges():
    parts = []
    for i, (b, e, hc, rb_, re_, rh) in enumerate(MT):
        hc = np.array(hc)
        big = i in (1, 2)
        L1, L2 = (21.0, 12.5) if big else (18.0, 11.0)
        sx = np.sign(hc[0]) if abs(hc[0]) > 6 else 0.0
        dir1 = normalize([-0.04 * sx, -1.0, 0.0])
        p1a = hc + np.array([0.0, -rh - 1.3, 0.0])
        p1b = p1a + L1 * dir1
        p2a = p1b + 1.4 * dir1
        p2b = p2a + L2 * dir1
        p3a = p2b + 1.4 * dir1
        r1 = 3.2 if big else 2.9
        parts.append(chain([p1a, p1b], [r1, r1 - 0.6]))
        parts.append(ellipsoid(p1a + [0, -1.5, 0], [r1 + 0.4, 2.6, r1 + 0.3]))
        parts.append(chain([p2a, p2b], [r1 - 0.4, r1 - 0.9]))
        parts.append(ellipsoid(p2a + [0, -1.2, 0], [r1, 2.2, r1 - 0.2]))
        claw = chain([p3a, p3a + 5.5 * dir1 + np.array([0, 0, 0.6]),
                      p3a + 11.5 * dir1 + np.array([0, 0, 2.6]),
                      p3a + 15.0 * dir1 + np.array([0, 0, 4.8])],
                     [r1 - 0.7, r1 - 1.1, 1.0, 0.25])
        parts.append(claw)
    noise = Noise(67, amp=0.06)

    def sdf(p):
        # chaque phalange est une composante séparée ; les bulbes sont fusionnés à leur phalange
        d = None
        for k in range(0, len(parts), 5):
            a = smin(parts[k](p), parts[k + 1](p), 2.0)
            b = smin(parts[k + 2](p), parts[k + 3](p), 2.0)
            c = parts[k + 4](p)
            dk = np.minimum(np.minimum(a, b), c)
            d = dk if d is None else np.minimum(d, dk)
        return d + noise(p)

    return dict(name="phalanges", sdf=sdf, bbox=([-17.0, -175.0, -11.0], [17.0, -110.0, 12.0]),
                h=0.3, tris=14000, cart=None, landmarks=lambda v: {})


# --------------------------------------------------------------- BASSIN -----
# Repère du bassin : origine au centre de l'acétabulum (= centre de la tête
# fémorale), X latéral, Y crânial (corps), Z dorsal (position CT : décubitus
# dorsal, membres en extension -> ce repère coïncide avec celui du fémur).
PELVIS_MID = -45.0   # plan médian (symphyse), en x du repère bassin
PELVIS_CROP = (-50.0, 40.0)   # champ CT : de l'acétabulum (et alentours) au métatarse


def build_pelvis():
    d_neck = FEMUR["d_neck"]
    a0 = normalize([0.75, -0.25, -0.6])
    a_ac = normalize(-d_neck + a0)
    cup_out = ellipsoid([-2.0, 0.0, 1.5], [16.5, 18.0, 17.0])
    cup_in = sphere([0, 0, 0], 11.7)
    rim = halfspace(3.0 * a_ac, a_ac)
    # ilium : corps + aile (ellipsoïde aplati, surface glutéale dorsolatérale concave)
    il_body = round_cone([-3.5, 13.0, 7.0], [-11.0, 44.0, 19.0], 9.5, 7.5)
    Rw = rot([0, 1, 0], 28.0) @ rot([1, 0, 0], -8.0)
    wing_c = np.array([-14.0, 70.0, 25.0])
    il_wing = ellipsoid(wing_c, [4.2, 33.0, 21.0], R=Rw)
    il_crest = capsule([-10.5, 100.0, 11.0], [-17.0, 98.0, 40.0], 4.0)
    gluteal = sphere(wing_c + Rw @ np.array([62.0, 0.0, 0.0]), 59.5)
    # ischium : corps, table ischiatique, tubérosité
    is_body = round_cone([-2.0, -14.0, 5.0], [-7.5, -46.0, 9.0], 9.0, 7.0)
    is_tub = ellipsoid([-8.0, -61.0, 9.0], [8.0, 6.5, 6.5])
    is_table = ellipsoid([-25.0, -51.0, 6.0], [19.0, 11.0, 3.8])
    # pubis, plancher pelvien, foramen obturé
    pubis = chain([[-6.0, -6.0, -8.0], [-30.0, -12.0, -15.0], [-45.5, -15.0, -15.0]], [7.0, 5.0, 5.5])
    floor = ellipsoid([-38.0, -33.0, -10.0], [9.0, 21.0, 3.6], R=rot([1, 0, 0], -12))
    obturator = ellipsoid([-24.0, -30.0, -7.0], [10.5, 13.5, 10.0], R=rot([1, 0, 0], -15))
    mid_cut = halfspace([PELVIS_MID - 0.3, 0, 0], [-1, 0, 0])
    crop_cr = halfspace([0, PELVIS_CROP[1], 0], [0, 1, 0])
    crop_cd = halfspace([0, PELVIS_CROP[0], 0], [0, -1, 0])
    noise = Noise(71, amp=0.2)

    def sdf(p):
        d = cup_out(p)
        d = smin(d, il_body(p), 7.0)
        d = smin(d, il_wing(p), 9.0)
        d = smin(d, il_crest(p), 6.0)
        d = smax(d, -gluteal(p), 3.0)
        d = smin(d, is_body(p), 7.0)
        d = smin(d, is_tub(p), 6.0)
        d = smin(d, is_table(p), 7.0)
        d = smin(d, pubis(p), 6.0)
        d = smin(d, floor(p), 6.0)
        d = smax(d, -obturator(p), 3.0)
        d = smax(d, -cup_in(p), 1.0)
        d = smax(d, rim(p), 3.0)            # retire la matière au-delà du rebord
        d = d + noise(p)
        d = np.maximum(d, mid_cut(p))
        d = smax(d, crop_cr(p), 1.2)
        return smax(d, crop_cd(p), 1.2)

    def cart(p):
        r = _len(p)
        return ((r < 12.6) & ((p @ a_ac) > -9.0)).astype(float)

    def landmarks(v):
        return {"acetabulum_center": np.zeros(3),
                "rectus_origin": np.array([-1.0, 17.0, -9.0]),
                "iliac_crest": v[np.argmax(v[:, 1])]}

    return dict(name="pelvis", sdf=sdf, bbox=([-47.0, PELVIS_CROP[0] - 3, -30.0], [21.0, PELVIS_CROP[1] + 3, 52.0]),
                h=0.4, tris=22000, cart=cart, landmarks=landmarks, largest=True,
                crop_planes=[([0, PELVIS_CROP[1], 0], [0, 1, 0]), ([0, PELVIS_CROP[0], 0], [0, -1, 0])])


def build_sacrum():
    xm = PELVIS_MID
    body = chain([[xm, 94.0, 30.0], [xm, 62.0, 33.0], [xm, 36.0, 34.0]], [10.0, 7.0, 4.6])
    wings = ellipsoid([xm, 84.0, 30.0], [26.5, 11.0, 8.0])
    crest = capsule([xm, 90.0, 41.0], [xm, 42.0, 40.0], 2.4)
    noise = Noise(73, amp=0.15)

    def sdf(p):
        d = smin(body(p), wings(p), 6.0)
        d = smin(d, crest(p), 4.0)
        return d + noise(p)

    return dict(name="sacrum", sdf=sdf, bbox=([xm - 30, 28.0, 18.0], [xm + 30, 108.0, 47.0]),
                h=0.45, tris=8000, cart=None, landmarks=lambda v: {})


# =============================================================================
# 3. Maillage : grille -> marching cubes -> lissage -> décimation -> attributs
# =============================================================================

def eval_grid(sdf, bmin, bmax, h, chunk_pts=700_000):
    bmin = np.asarray(bmin, float)
    bmax = np.asarray(bmax, float)
    n = np.ceil((bmax - bmin) / h).astype(int) + 1
    xs = bmin[0] + h * np.arange(n[0])
    ys = bmin[1] + h * np.arange(n[1])
    zs = bmin[2] + h * np.arange(n[2])
    vals = np.empty((n[0], n[1], n[2]), np.float32)
    per = max(1, chunk_pts // (n[0] * n[2]))
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    for j0 in range(0, n[1], per):
        j1 = min(n[1], j0 + per)
        Y = ys[j0:j1]
        P = np.empty((n[0], j1 - j0, n[2], 3))
        P[..., 0] = X[:, None, :]
        P[..., 1] = Y[None, :, None]
        P[..., 2] = Z[:, None, :]
        vals[:, j0:j1, :] = sdf(P.reshape(-1, 3)).reshape(n[0], j1 - j0, n[2])
    # bord de grille strictement "extérieur" -> surface fermée
    vals[0, :, :] = vals[-1, :, :] = 1.0
    vals[:, 0, :] = vals[:, -1, :] = 1.0
    vals[:, :, 0] = vals[:, :, -1] = 1.0
    return vals, bmin, n


def mesh_bone(spec, verbose=True):
    t0 = time.time()
    vals, origin, n = eval_grid(spec["sdf"], *spec["bbox"], spec["h"])
    grid = pv.ImageData(dimensions=tuple(int(k) for k in n), spacing=(spec["h"],) * 3, origin=tuple(origin))
    grid.point_data["sdf"] = vals.ravel(order="F")
    surf = grid.contour([0.0], scalars="sdf", method="flying_edges")
    surf = surf.triangulate().clean()
    surf = surf.smooth_taubin(n_iter=25, pass_band=0.08)
    surf = pv.PolyData(surf.points, surf.faces).triangulate().clean()   # triangles uniquement
    surf = pv.PolyData(surf.points, surf.faces)
    if spec.get("largest"):
        surf = surf.connectivity(extraction_mode="largest").extract_surface()
        surf = pv.PolyData(surf.points, surf.faces).clean()
        surf = pv.PolyData(surf.points, surf.faces)
    n_tris = surf.n_cells
    if n_tris > spec["tris"]:
        surf = surf.decimate(1.0 - spec["tris"] / n_tris, volume_preservation=True)
    surf = surf.clean()
    surf = pv.PolyData(surf.points, surf.faces)
    v = np.asarray(surf.points, float)
    f = np.asarray(surf.faces).reshape(-1, 4)[:, 1:].astype(np.int64)
    # orientation : volume signé > 0 (normales sortantes)
    vol = np.sum(np.einsum("ij,ij->i", v[f[:, 0]], np.cross(v[f[:, 1]], v[f[:, 2]]))) / 6.0
    if vol < 0:
        f = f[:, [0, 2, 1]]
        vol = -vol
    if verbose:
        print(f"  {spec['name']:12s} grille {tuple(n)}  -> {len(v):6d} sommets {len(f):6d} triangles "
              f"vol {vol / 1000:7.1f} cm3  ({time.time() - t0:4.1f}s)")
    return v, f


def vertex_normals(v, f):
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    vn = np.zeros_like(v)
    for k in range(3):
        np.add.at(vn, f[:, k], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    return vn


def smooth_attr(a, f, n_vert, iters=2):
    """Lissage laplacien d'un attribut scalaire par sommet."""
    a = a.astype(float)
    for _ in range(iters):
        acc = np.zeros(n_vert)
        cnt = np.zeros(n_vert)
        for i, j in ((0, 1), (1, 2), (2, 0)):
            np.add.at(acc, f[:, i], a[f[:, j]])
            np.add.at(cnt, f[:, i], 1)
        a = 0.5 * a + 0.5 * acc / np.maximum(cnt, 1)
    return a


def bake_attributes(spec, v, f):
    vn = vertex_normals(v, f)
    sdf = spec.get("outer", spec["sdf"])
    # occlusion ambiante "SDF" : on regarde si la matière se rapproche le long de la normale
    occ = np.zeros(len(v))
    w = 1.0
    for hstep in (0.8, 1.7, 3.5, 7.0, 13.0):
        d = sdf(v + vn * hstep)
        occ += w * np.clip((hstep - d) / hstep, 0.0, 1.0)
        w *= 0.62
    ao = np.clip(1.0 - 0.55 * occ, 0.0, 1.0)
    ao = smooth_attr(ao, f, len(v), 2)
    cart = np.zeros(len(v))
    if spec.get("cart") is not None:
        cart = smooth_attr(spec["cart"](v), f, len(v), 3)
    med = np.zeros(len(v))
    if spec.get("canal") is not None:
        dc = np.abs(spec["canal"](v))
        do = np.abs(spec["outer"](v))
        med = (dc < do).astype(float)
        cart = np.where(med > 0.5, 0.0, cart)
        ao = np.where(med > 0.5, ao * 0.7, ao)
    for pt, nn in spec.get("crop_planes", []):
        nn = normalize(nn)
        on = (np.abs((v - np.asarray(pt, float)) @ nn) < 0.8) & ((vn @ nn) > 0.7)
        med = np.where(on, 0.5, med)
        cart = np.where(on, 0.0, cart)
        ao = np.where(on, np.maximum(ao, 0.85), ao)
    return ao, cart, med


# =============================================================================
# 4. Assemblage (position CT : membres en extension) et calibration
# =============================================================================

def proj_angle(a, b, n):
    """Angle signé (deg) entre a et b projetés dans le plan de normale n (éq. 3)."""
    n = normalize(n)
    pa = a - (a @ n) * n
    pb = b - (b @ n) * n
    return math.degrees(math.atan2(np.cross(pa, pb) @ n, pa @ pb))


def frame_from(x_axis, y_axis):
    x = normalize(x_axis)
    y = np.asarray(y_axis, float)
    y = normalize(y - (y @ x) * x)
    z = np.cross(x, y)
    return np.stack([x, y, z], axis=1)


def assemble(LM):
    """Transformations (4x4) des repères locaux vers le repère monde (= fémur)."""
    T = {}
    I4 = np.eye(4)
    T["femur"] = I4.copy()
    # Bassin : origine sur le centre de la tête fémorale
    Tp = np.eye(4)
    Tp[:3, 3] = FEMUR["H"]
    T["pelvis"] = Tp
    # Genou : lignes articulaires parallèles (frontal), axes mécaniques alignés
    # (sagittal), puis flexion de 10° autour de l'axe des condyles.
    f_m, f_l = LM["femur"]["cond_med_dist"], LM["femur"]["cond_lat_dist"]
    t_m, t_l = LM["tibia"]["plat_med"], LM["tibia"]["plat_lat"]
    m_f = normalize(FEMUR["H"] - LM["femur"]["knee_center"])        # axe mécanique fémoral
    m_t = normalize(LM["tibia"]["eminence"] - LM["tibia"]["distal_center"])
    A_f = frame_from(f_l - f_m, m_f)
    A_t = frame_from(t_l - t_m, m_t)
    R0 = A_f @ A_t.T
    gap = 2.2
    target = 0.5 * (f_m + f_l) - gap * A_f[:, 1]
    src = 0.5 * (t_m + t_l)
    Tk = np.eye(4)
    Tk[:3, :3] = R0
    Tk[:3, 3] = target - R0 @ src
    # flexion (6°) autour de l'axe condylien (passant par les centres des condyles)
    Cm, Cl = FEMUR["Cm"], FEMUR["Cl"]
    axis = normalize(Cl - Cm)
    piv = 0.5 * (Cm + Cl)
    Rf = rot(axis, -6.0)
    Tf = np.eye(4)
    Tf[:3, :3] = Rf
    Tf[:3, 3] = piv - Rf @ piv
    T["tibia"] = Tf @ Tk
    # Jarret : trochlée du talus dans la cochlée tibiale (quasi-extension)
    Rd = TIBIA["Rd"]
    T0 = Rd @ np.array([0.1, -9.0, 0.0])
    Th = np.eye(4)
    Rh = Rd @ rot([1, 0, 0], 2.0)
    Th[:3, :3] = Rh
    Th[:3, 3] = T0
    T["tarsus_in_tibia"] = Th
    T["tarsus"] = T["tibia"] @ Th
    return T


def calibration_report(LM, T):
    """Angles du modèle sain, mesurés comme dans l'application (contrôle)."""
    F, Tb = LM["femur"], LM["tibia"]
    out = {}
    # ---- fémur : axe anatomique = Y (par construction entre 1/3 et 1/2)
    sh = FEMUR["shaft"]
    L = F["head_center"][1] - 0.5 * (F["cond_med_dist"][1] + F["cond_lat_dist"][1]) + 11.0
    top = F["head_center"][1] + 11.0
    c13 = sh.center(top - L / 3.0)
    c12 = sh.center(top - L / 2.0)
    a_ax = normalize(c13 - c12)                 # axe anatomique (vers proximal)
    ey = np.array([0, 0, 1.0])                  # normale du plan frontal (Z caudal)
    lat = normalize(F["cond_lat_dist"] - F["cond_med_dist"])
    # aLDFA : angle latéral entre ligne articulaire distale (vers latéral) et axe (vers proximal)
    out["aLDFA"] = abs(proj_angle(lat, a_ax, ey))
    prox_line = normalize(F["gt_tip"] - F["head_center"])
    out["aLPFA"] = abs(proj_angle(prox_line, -a_ax, ey))
    m_ax = normalize(F["head_center"] - F["knee_center"])
    out["mLDFA"] = abs(proj_angle(lat, m_ax, ey))
    out["mLPFA"] = abs(proj_angle(prox_line, -m_ax, ey))
    tc = normalize(F["cond_lat_caud"] - F["cond_med_caud"])
    neck = normalize(F["head_center"] - F["neck_base"])
    out["anteversion"] = proj_angle(-tc, neck, a_ax)
    out["inclination_proj"] = 180.0 - abs(proj_angle(neck, a_ax, ey))
    out["femur_length"] = L
    # ---- tibia : axe mécanique
    m_t = normalize(Tb["eminence"] - Tb["distal_center"])
    ex = np.array([0, 0, 1.0])
    med_line = normalize(Tb["plat_med"] - Tb["plat_lat"])
    out["mMPTA"] = abs(proj_angle(med_line, -m_t, ex))
    dmed = normalize(Tb["groove_med"] - Tb["groove_lat"])
    out["mMDTA"] = abs(proj_angle(dmed, m_t, ex))
    sag_n = np.array([1.0, 0, 0])
    caud_line = normalize(Tb["plat_caud"] - Tb["plat_cran"])
    out["mCaPTA"] = abs(proj_angle(caud_line, -m_t, sag_n))
    out["TPA"] = 90.0 - out["mCaPTA"]
    cran_line = normalize(Tb["dist_cran"] - Tb["dist_caud"])
    out["mCrDTA"] = abs(proj_angle(cran_line, m_t, sag_n))
    out["tibia_length"] = float(np.linalg.norm(Tb["eminence"] - Tb["distal_center"]))
    # ---- membre : angle tibio-fémoral mécanique (frontal) dans le repère monde
    Rt = T["tibia"][:3, :3]
    m_t_w = Rt @ m_t
    out["tibiofemoral_varus"] = abs(proj_angle(m_ax, m_t_w, ey))
    return out


# =============================================================================
# 5. Pipeline complet + empaquetage
# =============================================================================

BUILDERS = [build_femur, build_tibia, build_fibula, build_patella, build_fabellae,
            build_talus, build_calcaneus, build_tarsals, build_metatarsals, build_phalanges,
            build_pelvis]

GROUP = {  # os -> segment rigide auquel il est attaché dans la chaîne cinématique
    "pelvis": "pelvis",
    "femur": "femur", "patella": "femur", "fabellae": "femur",
    "tibia": "tibia", "fibula": "tibia",
    "talus": "tarsus", "calcaneus": "tarsus", "tarsals": "tarsus",
    "metatarsals": "tarsus", "phalanges": "tarsus",
}


def run(only=None, preview=None):
    BUILD.mkdir(exist_ok=True)
    meshes, LM = {}, {}
    specs = []
    for b in BUILDERS:
        spec = b()
        specs.append(spec)
    for spec in specs:
        if only and spec["name"] not in only:
            continue
        v, f = mesh_bone(spec)
        ao, cart, med = bake_attributes(spec, v, f)
        LM[spec["name"]] = {k: np.asarray(x, float) for k, x in spec["landmarks"](v).items()}
        meshes[spec["name"]] = dict(v=v, f=f, ao=ao, cart=cart, med=med)
    if preview:
        render_preview(meshes, preview)
    if only:
        return meshes, LM
    T = assemble(LM)
    rep = calibration_report(LM, T)
    print("\nCalibration du modèle sain :")
    for k, x in rep.items():
        print(f"  {k:20s} {x:8.2f}")
    pack(meshes, LM, T, rep)
    return meshes, LM


def pack(meshes, LM, T, rep):
    """Binaire compact : positions int16 quantifiées, indices uint16/uint32,
    attributs uint8 ; puis gzip + base64 (embarqué dans le HTML)."""
    chunks = []
    offset = 0
    meta = {"version": 1, "units": "mm", "side": "right",
            "frame": "X latéral, Y proximal, Z caudal (repère local de chaque os)",
            "bones": {}, "landmarks": {}, "transforms": {}, "calibration": rep,
            "group": GROUP, "pelvis_mid_x": PELVIS_MID,
            "femur": {"head_center": FEMUR["H"].tolist(), "neck_dir": FEMUR["d_neck"].tolist(),
                      "cond_med_center": FEMUR["Cm"].tolist(), "cond_lat_center": FEMUR["Cl"].tolist()},
            "tibia": {"plateau_R": TIBIA["Rp"].tolist(), "distal_R": TIBIA["Rd"].tolist()}}

    def add(arr):
        nonlocal offset
        b = arr.tobytes()
        pad = (-len(b)) % 4
        chunks.append(b + b"\0" * pad)
        o = offset
        offset += len(b) + pad
        return o, len(b)

    for name, m in meshes.items():
        v, f = m["v"], m["f"]
        lo = v.min(0)
        hi = v.max(0)
        scale = (hi - lo) / 65535.0
        q = np.round((v - lo) / scale).astype(np.uint16)
        idx_t = np.uint16 if len(v) < 65536 else np.uint32
        info = {"nv": int(len(v)), "nf": int(len(f)), "lo": lo.tolist(), "scale": scale.tolist(),
                "index32": bool(idx_t == np.uint32)}
        info["pos"] = add(q.reshape(-1))
        info["idx"] = add(f.astype(idx_t).reshape(-1))
        info["ao"] = add(np.round(np.clip(m["ao"], 0, 1) * 255).astype(np.uint8))
        info["cart"] = add(np.round(np.clip(m["cart"], 0, 1) * 255).astype(np.uint8))
        info["med"] = add(np.round(np.clip(m["med"], 0, 1) * 255).astype(np.uint8))
        meta["bones"][name] = info
    for name, d in LM.items():
        meta["landmarks"][name] = {k: [round(float(c), 4) for c in x] for k, x in d.items()}
    # axe diaphysaire "vrai" (centre du tube) : sert à placer l'apex des déformités synthétiques
    meta["centerline"] = {}
    for name, sh in (("femur", FEMUR["shaft"]), ("tibia", TIBIA["shaft"])):
        ys = np.arange(4.0, 196.0, 2.0)
        c = sh.center(ys)
        meta["centerline"][name] = [[round(float(y), 2), round(float(x), 3), round(float(z), 3)] for x, y, z in c]
    Lf, Lt = LM["femur"], LM["tibia"]
    meta["axis"] = {
        "femur": {"y_top": float(Lf["head_center"][1] + 11.0),
                  "y_bot": float(min(Lf["cond_med_dist"][1], Lf["cond_lat_dist"][1]))},
        "tibia": {"y_top": float(Lt["eminence"][1]), "y_bot": float(Lt["distal_center"][1])},
    }
    for k, M in T.items():
        meta["transforms"][k] = [[round(float(c), 6) for c in row] for row in M]
    raw = b"".join(chunks)
    gz = gzip.compress(raw, 9)
    (BUILD / "bones_pack.bin.gz").write_bytes(gz)
    (BUILD / "bones_pack.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (BUILD / "bones_pack.b64").write_text(base64.b64encode(gz).decode("ascii"), encoding="ascii")
    print(f"\nPaquet : brut {len(raw) / 1e6:.2f} Mo, gzip {len(gz) / 1e6:.2f} Mo, "
          f"base64 {len(gz) * 4 / 3 / 1e6:.2f} Mo")


def render_preview(meshes, out_name):
    pv.OFF_SCREEN = True
    names = list(meshes.keys())
    views = [("craniocaudale", (0, 0, -1), (0, 1, 0)), ("latérale", (1, 0, 0), (0, 1, 0)),
             ("caudale", (0, 0, 1), (0, 1, 0)), ("médiale", (-1, 0, 0), (0, 1, 0)),
             ("3/4", (0.8, 0.35, -0.7), (0, 1, 0))]
    p = pv.Plotter(off_screen=True, shape=(1, len(views)), window_size=(360 * len(views), 900))
    for i, (title, d, up) in enumerate(views):
        p.subplot(0, i)
        p.set_background("#1b2228")
        for name in names:
            m = meshes[name]
            faces = np.hstack([np.full((len(m["f"]), 1), 3), m["f"]]).ravel()
            mesh = pv.PolyData(m["v"], faces)
            col = np.stack([0.91 * m["ao"], 0.87 * m["ao"], 0.78 * m["ao"]], 1)
            col = col * (1 - 0.35 * m["cart"][:, None]) + np.array([0.55, 0.75, 0.95]) * 0.35 * m["cart"][:, None]
            col = np.where(m["med"][:, None] > 0.5, np.array([0.55, 0.15, 0.12]), col)
            mesh.point_data["rgb"] = (np.clip(col, 0, 1) * 255).astype(np.uint8)
            p.add_mesh(mesh, scalars="rgb", rgb=True, smooth_shading=True, specular=0.25)
        p.add_text(title, font_size=10, color="white")
        c = np.mean(np.vstack([meshes[n]["v"] for n in names]), axis=0)
        p.camera.focal_point = c
        p.camera.position = c + 600 * np.asarray(d, float)
        p.camera.up = up
        p.reset_camera()
        p.camera.zoom(1.15)
    out = Path(out_name)
    p.screenshot(str(out))
    print("aperçu :", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="os à générer (aperçu rapide)")
    ap.add_argument("--preview", default=None, help="chemin PNG de l'aperçu")
    a = ap.parse_args()
    run(only=a.only, preview=a.preview)
