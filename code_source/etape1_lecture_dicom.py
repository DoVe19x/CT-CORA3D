"""
etape1_lecture_dicom.py — lit un dossier DICOM comme le module « DICOM » de 3D Slicer.

Rôle    : (1) inventaire : fouiller un dossier (sous-dossiers compris, extensions quelconques) et regrouper les
              fichiers par série (SeriesInstanceUID) ;
          (2) chargement : trier les coupes le long de la normale à leur plan, vérifier la géométrie (orientation
              identique, espacement régulier, épaisseur ≤ 1 mm), convertir les valeurs en unités Hounsfield, et
              calculer la matrice qui passe des indices de voxels aux coordonnées du scanner (LPS, mm).
Entrées : un dossier contenant des fichiers DICOM.
Sorties : objets Serie et Volume (en mémoire). Facultatif : volume.nrrd, lisible par 3D Slicer.

Rappels DICOM utilisés ici :
  * ImagePositionPatient (IPP) : position (mm) du centre du premier pixel de la coupe ;
  * ImageOrientationPatient (IOP) : cosinus directeurs des lignes (sens des colonnes croissantes) puis des colonnes ;
  * PixelSpacing = [écart entre lignes, écart entre colonnes] (mm) ;
  * HU = valeur stockée × RescaleSlope + RescaleIntercept.
Le repère du scanner est LPS : x vers la gauche du patient, y vers l'arrière, z vers la tête.
"""
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pydicom
from pydicom.misc import is_dicom

import parametres as P

ETIQUETTES = ["SeriesInstanceUID", "SeriesNumber", "SeriesDescription", "StudyDescription", "StudyDate", "Modality",
              "PatientName", "PatientID", "PatientPosition", "BodyPartExamined", "Manufacturer", "ManufacturerModelName",
              "ConvolutionKernel", "KVP", "XRayTubeCurrent", "SliceThickness", "PixelSpacing", "Rows", "Columns",
              "ImagePositionPatient", "ImageOrientationPatient", "InstanceNumber", "NumberOfFrames", "ImageType"]
EXTENSIONS_IGNOREES = {".png", ".jpg", ".jpeg", ".txt", ".json", ".stl", ".nrrd", ".py", ".md", ".pdf", ".csv",
                       ".zip", ".html", ".js", ".css", ".tex", ".log", ".app", ".bat", ".sh", ".ds_store"}


@dataclass
class Serie:
    uid: str
    nom: str                       # nom sûr, utilisé pour resultats/<nom>/
    dossier: Path                  # dossier qui contient les fichiers
    fichiers: list                 # [(chemin, IPP, IOP, numéro d'instance)]
    infos: dict = field(default_factory=dict)


@dataclass
class Volume:
    hu: np.ndarray                 # int16, axes (k, j, i) = (coupe, ligne, colonne)
    affine: np.ndarray             # 4 × 4 : [i, j, k, 1] -> [x, y, z, 1] en LPS (mm)
    infos: dict
    avertissements: list

    @property
    def espacement(self):
        """Taille des voxels (mm) dans l'ordre des axes numpy (k, j, i)."""
        return tuple(float(np.linalg.norm(self.affine[:3, a])) for a in (2, 1, 0))

    def vers_lps(self, kji):
        """Indices (k, j, i), éventuellement fractionnaires, -> coordonnées LPS (mm)."""
        kji = np.atleast_2d(np.asarray(kji, float))
        return kji[:, ::-1] @ self.affine[:3, :3].T + self.affine[:3, 3]

    def vers_indices(self, lps):
        """Coordonnées LPS (mm) -> indices fractionnaires (k, j, i)."""
        lps = np.atleast_2d(np.asarray(lps, float))
        return (np.linalg.solve(self.affine[:3, :3], (lps - self.affine[:3, 3]).T).T)[:, ::-1]


def texte(v):
    return "" if v is None else str(v).strip()


def nom_sur(texte_, defaut="serie"):
    """Nom de dossier sans risque : minuscules, chiffres, tiret et soulignement."""
    t = re.sub(r"[^a-z0-9_-]+", "_", texte_.lower()).strip("_")[:60]
    return t or defaut


# =============================================================================== inventaire
def fichiers_candidats(dossier):
    for racine, sous, noms in os.walk(dossier):
        sous[:] = sorted(s for s in sous if s not in P.IGNORES and not s.startswith(".") and not s.endswith(".app"))
        for n in sorted(noms):
            if n.startswith(".") or Path(n).suffix.lower() in EXTENSIONS_IGNOREES:
                continue
            yield Path(racine) / n


def inventaire(dossier=P.DOSSIER_DICOM, progression=None):
    """Toutes les séries d'images (scanner, IRM…) du dossier, comme la base DICOM de 3D Slicer."""
    groupes = {}
    candidats = list(fichiers_candidats(dossier))
    for n, f in enumerate(candidats):
        if progression and n % 200 == 0:
            progression(n, len(candidats))
        try:
            if not is_dicom(f):
                continue
            ds = pydicom.dcmread(f, stop_before_pixels=True, specific_tags=ETIQUETTES)
        except Exception:
            continue                                     # fichier illisible ou non DICOM : ignoré
        if "ImagePositionPatient" not in ds or "ImageOrientationPatient" not in ds or "SeriesInstanceUID" not in ds:
            continue                                     # pas une image en coupe (rapport, DICOMDIR…)
        g = groupes.setdefault(ds.SeriesInstanceUID, {"fichiers": [], "entete": ds})
        g["fichiers"].append((f, np.array(ds.ImagePositionPatient, float), np.array(ds.ImageOrientationPatient, float),
                              int(ds.get("InstanceNumber") or 0)))
    series = []
    for uid, g in groupes.items():
        ds = g["entete"]
        dossier_commun = Path(os.path.commonpath([str(f[0].parent) for f in g["fichiers"]]))
        epaisseur = ds.get("SliceThickness")
        series.append(Serie(uid=uid, nom="", dossier=dossier_commun, fichiers=g["fichiers"], infos={
            "description": texte(ds.get("SeriesDescription")), "etude": texte(ds.get("StudyDescription")),
            "date": texte(ds.get("StudyDate")), "modalite": texte(ds.get("Modality")),
            "patient": texte(ds.get("PatientName")), "id_patient": texte(ds.get("PatientID")),
            "position_patient": texte(ds.get("PatientPosition")), "numero_serie": texte(ds.get("SeriesNumber")),
            "fabricant": " ".join(x for x in (texte(ds.get("Manufacturer")), texte(ds.get("ManufacturerModelName"))) if x),
            "noyau": texte(ds.get("ConvolutionKernel")), "kv": texte(ds.get("KVP")), "ma": texte(ds.get("XRayTubeCurrent")),
            "epaisseur_mm": float(epaisseur) if epaisseur not in (None, "") else None,
            "pixel_mm": [float(x) for x in ds.get("PixelSpacing", [0, 0])],
            "taille_image": [int(ds.get("Rows") or 0), int(ds.get("Columns") or 0)],
            "nb_fichiers": len(g["fichiers"]), "dossier": str(dossier_commun),
        }))
    # noms lisibles : le nom du dossier, complété du numéro de série si le dossier en contient plusieurs. Le dossier
    # apporté par le chirurgien est souvent le dossier de la série lui-même : on garde alors aussi son nom (la
    # description DICOM, par exemple « PELVIS », est la même pour toutes les séries d'un examen).
    par_dossier = Counter(s.dossier for s in series)
    for s in series:
        base = s.dossier.name or s.infos["description"] or "serie"
        s.nom = nom_sur(base if par_dossier[s.dossier] == 1 else f"{base}_s{s.infos['numero_serie'] or s.uid[-6:]}")
    noms = Counter(s.nom for s in series)
    for s in series:                                     # deux séries de même nom : suffixe unique
        if noms[s.nom] > 1:
            s.nom = f"{s.nom}_{s.uid[-6:].replace('.', '')}"
    return sorted(series, key=lambda s: s.nom)


def decrire(serie):
    i = serie.infos
    return (f"{serie.nom} : {i['nb_fichiers']} coupes {i['modalite']}, {i['description'] or 'sans description'}, "
            f"patient « {i['patient']} », {i['date'][6:8]}/{i['date'][4:6]}/{i['date'][:4]}, "
            f"pixel {i['pixel_mm'][0]:.3f} mm, épaisseur {i['epaisseur_mm']} mm")


# =============================================================================== chargement
def lire_pixels(chemin):
    """Valeurs en HU d'une coupe (float). pydicom d'abord ; SimpleITK (GDCM) si l'image est compressée
    dans un format que pydicom ne sait pas décoder sans greffon."""
    ds = pydicom.dcmread(chemin)
    pente, origine = float(ds.get("RescaleSlope", 1) or 1), float(ds.get("RescaleIntercept", 0) or 0)
    try:
        brut = ds.pixel_array
    except Exception:
        import SimpleITK as sitk
        brut = sitk.GetArrayFromImage(sitk.ReadImage(str(chemin)))[0]
        return brut.astype(np.float32)                   # SimpleITK applique déjà pente et ordonnée
    return brut.astype(np.float32) * pente + origine


def charger(serie, journal=print):
    """Construit le Volume (HU, géométrie) d'une série, avec les mêmes contrôles que 3D Slicer."""
    avert = []
    f = serie.fichiers
    # 1) une seule orientation (les images de repérage « scout » ont une autre orientation : écartées)
    iops = Counter(tuple(np.round(x[2], 3)) for x in f)
    iop_ref = np.array(iops.most_common(1)[0][0])
    garde = [x for x in f if np.abs(x[2] - iop_ref).max() <= P.TOLERANCE_ORIENTATION + 1e-3]
    if len(garde) < len(f):
        avert.append(f"{len(f) - len(garde)} fichier(s) d'orientation différente écarté(s) (images de repérage ?)")
    ligne, colonne = iop_ref[:3], iop_ref[3:]
    normale = np.cross(ligne, colonne)
    # 2) tri le long de la normale (et non par numéro d'image, qui n'est pas fiable)
    garde.sort(key=lambda x: float(x[1] @ normale))
    d = np.array([float(x[1] @ normale) for x in garde])
    doublons = np.nonzero(np.diff(d) < 1e-3)[0]
    if len(doublons):
        avert.append(f"{len(doublons)} coupe(s) en double (même position) écartée(s)")
        en_double = set(doublons + 1)                    # la seconde coupe de chaque paire est écartée
        garde = [x for n, x in enumerate(garde) if n not in en_double]
        d = np.array([float(x[1] @ normale) for x in garde])
    if len(garde) < 2:
        raise ValueError("la série contient moins de deux coupes : pas de volume 3D possible")
    ecarts = np.diff(d)
    pas = float(np.median(ecarts))
    irregulier = np.abs(ecarts - pas).max() > P.TOLERANCE_ESPACEMENT * pas
    # 3) lecture des pixels
    journal(f"  lecture de {len(garde)} coupes…")
    coupes = [lire_pixels(x[0]) for x in garde]
    formes = Counter(c.shape for c in coupes)
    if len(formes) > 1:
        raise ValueError(f"les coupes n'ont pas toutes la même taille : {dict(formes)}")
    vol = np.stack(coupes)
    # 4) espacement irrégulier (coupe manquante) : rééchantillonnage linéaire sur une grille régulière
    if irregulier:
        avert.append(f"espacement des coupes irrégulier ({ecarts.min():.3f} à {ecarts.max():.3f} mm) : volume "
                     f"rééchantillonné au pas de {pas:.3f} mm (coupes manquantes ?)")
        cible = np.arange(d[0], d[-1] + 1e-6, pas)
        k = np.clip(np.searchsorted(d, cible) - 1, 0, len(d) - 2)
        w = ((cible - d[k]) / (d[k + 1] - d[k]))[:, None, None]
        vol = vol[k] * (1 - w) + vol[k + 1] * w
        n = len(cible)
        pas_vec = normale * pas if n < 2 else (garde[-1][1] - garde[0][1]) / (d[-1] - d[0]) * pas
    else:
        n = len(garde)
        pas_vec = (garde[-1][1] - garde[0][1]) / (n - 1)
    hu = np.clip(np.rint(vol), -32768, 32767).astype(np.int16)
    del vol, coupes
    # 5) inclinaison du statif (gantry tilt) : le pas entre coupes n'est pas parallèle à la normale
    inclinaison = float(np.degrees(np.arccos(np.clip(abs(pas_vec @ normale) / np.linalg.norm(pas_vec), 0, 1))))
    if inclinaison > 0.5:
        avert.append(f"statif incliné de {inclinaison:.1f}° : la matrice de passage en tient compte exactement")
    # 6) matrice voxel -> LPS
    ds = pydicom.dcmread(garde[0][0], stop_before_pixels=True)
    dl, dc = (float(x) for x in ds.PixelSpacing)       # écart entre lignes, écart entre colonnes
    A = np.eye(4)
    A[:3, 0] = ligne * dc                              # i : le long d'une ligne (colonnes croissantes)
    A[:3, 1] = colonne * dl                            # j : le long d'une colonne (lignes croissantes)
    A[:3, 2] = pas_vec                                 # k : d'une coupe à la suivante
    A[:3, 3] = garde[0][1]
    epaisseur = serie.infos.get("epaisseur_mm") or pas
    if max(epaisseur, abs(pas)) > P.EPAISSEUR_MAX_MM + 1e-6:
        avert.append(f"coupes de {max(epaisseur, abs(pas)):.2f} mm : plus épaisses que les {P.EPAISSEUR_MAX_MM} mm "
                     f"demandés (BP §3.1) ; la précision des surfaces en souffre")
    infos = dict(serie.infos)
    infos.update({"nom": serie.nom, "dimensions_kji": list(hu.shape), "espacement_kji_mm": [abs(pas), dl, dc],
                  "etendue_mm": [round(abs(pas) * (hu.shape[0] - 1), 1), round(dl * hu.shape[1], 1), round(dc * hu.shape[2], 1)],
                  "hu_min": int(hu.min()), "hu_max": int(hu.max()), "inclinaison_statif_deg": round(inclinaison, 2),
                  "systeme": "LPS"})
    for a in avert:
        journal(f"  ⚠ {a}")
    return Volume(hu=hu, affine=A, infos=infos, avertissements=avert)


def trouver(series, nom):
    """Série par son nom exact, ou par un morceau de nom s'il est unique."""
    exact = [s for s in series if s.nom == nom]
    if exact:
        return exact[0]
    partiel = [s for s in series if nom.lower() in s.nom]
    if len(partiel) == 1:
        return partiel[0]
    raise ValueError(f"série « {nom} » introuvable ou ambiguë ; séries : {[s.nom for s in series]}")


if __name__ == "__main__":
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else P.DOSSIER_DICOM
    for s in inventaire(dossier):
        print(decrire(s))
