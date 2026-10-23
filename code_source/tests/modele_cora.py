"""
modele_cora.py — lit le modèle osseux procédural de CORA 3D (code_source/cora/build/bones_pack.*) depuis Python.

Rôle    : fournir aux tests des os dont les repères anatomiques sont connus exactement (fémur, tibia, fibula du
          modèle synthétique, membre droit, repère X latéral, Y proximal, Z caudal), pour vérifier la détection
          automatique des repères (etape6_reperes.py).
Entrées : cora/build/bones_pack.json et bones_pack.bin.gz (même décodage que loadBones() de l'application).
Sorties : dictionnaire {os: (sommets float64 (n, 3), triangles int (m, 3))} et repères {os: {nom: [x, y, z]}}.
"""
import gzip
import json
from pathlib import Path

import numpy as np

DOSSIER = Path(__file__).resolve().parent.parent / "cora" / "build"


def charger(noms=("femur", "tibia", "fibula")):
    meta = json.loads((DOSSIER / "bones_pack.json").read_text(encoding="utf-8"))
    brut = gzip.decompress((DOSSIER / "bones_pack.bin.gz").read_bytes())
    os_ = {}
    for nom in noms:
        info = meta["bones"][nom]
        off, taille = info["pos"]
        q = np.frombuffer(brut, np.uint16, taille // 2, off).astype(np.float64).reshape(-1, 3)
        sommets = np.asarray(info["lo"]) + q * np.asarray(info["scale"])
        off, taille = info["idx"]
        typ = np.uint32 if info["index32"] else np.uint16
        faces = np.frombuffer(brut, typ, taille // np.dtype(typ).itemsize, off).astype(np.int64).reshape(-1, 3)
        os_[nom] = (sommets, faces)
    reperes = {k: {n: list(map(float, p)) for n, p in meta["landmarks"][k].items()} for k in noms}
    return os_, reperes, meta
