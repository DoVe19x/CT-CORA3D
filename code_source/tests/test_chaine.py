"""
test_chaine.py — test automatique de toute la chaîne sur un scanner SYNTHÉTIQUE dont la géométrie est connue.

Fantôme (coordonnées LPS, mm) : deux « os » en forme de capsule (cylindre de rayon 7 mm à bouts hémisphériques),
bout à bout, séparés par un interligne de 1,5 mm, inclinés de 15° ; corticale de 1,5 mm à 1300 HU, moelle à 40 HU ;
tissus mous à 40 HU dans un cylindre de 30 mm de rayon ; table de scanner (300 HU) ; cylindre de calibration
homogène (1300 HU). Flou du scanner : gaussien, sigma = 0,5 mm ; bruit : 40 HU. Le tout est écrit en DICOM (une coupe
par fichier, noms de fichiers mélangés), puis relu par le programme exactement comme un vrai scanner.

Vérifications :
  1. lecture DICOM : une série, dimensions, espacement, position LPS d'un voxel connu ;
  2. segmentation : deux os ; le cylindre est reconnu « objet non osseux » ; la table est ignorée ;
  3. points nommés : les deux os reçoivent les noms donnés (fémur, tibia) ;
  4. maillages : étanches, un morceau, nombre d'Euler 2 ;
  5. exactitude : distance des sommets à la surface vraie. Un seuil bas placerait la surface ≈ 0,6 mm à l'extérieur
     du bord réel (flou du scanner, valeur prévue par la théorie et vérifiée sans affinage) ; l'affinage
     « demi-hauteur » doit ramener l'écart moyen sous 0,25 mm.
Usage : ../../../.venv/bin/python tests/test_chaine.py   (depuis code_source/ ; ≈ 30 s)
"""
import random
import sys
import tempfile
import time
from math import sqrt
from pathlib import Path

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
from scipy import ndimage as ndi
from scipy.special import erfinv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etape1_lecture_dicom as E1      # noqa: E402
import etape2_segmentation as E2       # noqa: E402
import etape3_identification as E3     # noqa: E402
import etape4_maillage as E4           # noqa: E402
import parametres as P                 # noqa: E402

# ------------------------------------------------------------------------------- fantôme
DK, DJ, DI = 0.625, 0.5, 0.5                    # voxel (mm) : coupe, ligne, colonne
NK, NJ, NI = 240, 170, 170
ORIGINE = np.array([-42.25, -42.25, -75.0])     # IPP de la première coupe (LPS)
R_OS, EP_CORTICALE, GAP = 7.0, 1.5, 1.5
SIGMA_PSF, BRUIT = 0.5, 40.0
INCLINAISON = np.radians(15)
ROT = np.array([[1, 0, 0], [0, np.cos(INCLINAISON), -np.sin(INCLINAISON)], [0, np.sin(INCLINAISON), np.cos(INCLINAISON)]])
# axes des deux capsules (avant inclinaison, le long de z) ; bouts hémisphériques séparés de GAP
OS = {"femur": (np.array([0, 0, -55.0]), np.array([0, 0, -R_OS - GAP / 2])),
      "tibia": (np.array([0, 0, R_OS + GAP / 2]), np.array([0, 0, 55.0]))}


def distance_capsule(p, a, b):
    """Distance de points à l'axe [a, b] d'une capsule (avant inclinaison)."""
    ab = b - a
    t = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def fabriquer_volume(rng):
    k, j, i = np.meshgrid(np.arange(NK), np.arange(NJ), np.arange(NI), indexing="ij")
    p = np.stack([ORIGINE[0] + i * DI, ORIGINE[1] + j * DJ, ORIGINE[2] + k * DK], axis=-1).reshape(-1, 3)
    hu = np.full(len(p), -1000.0)
    hu[np.hypot(p[:, 0], p[:, 1]) < 30] = 40.0                                   # tissus mous
    hu[(p[:, 1] > 35) & (p[:, 1] < 37)] = 300.0                                  # table (en arrière)
    cal = (np.hypot(p[:, 0] - 36, p[:, 1] + 10) < 5) & (np.abs(p[:, 2]) < 25)
    hu[cal] = 1300.0                                                             # cylindre de calibration
    q = p @ ROT                                                                  # repère des os (inclinaison)
    for a, b in OS.values():
        d = distance_capsule(q, a, b)
        hu[d < R_OS] = 1300.0
        hu[d < R_OS - EP_CORTICALE] = 40.0                                       # moelle
    hu = hu.reshape(NK, NJ, NI)
    hu = ndi.gaussian_filter(hu, sigma=(SIGMA_PSF / DK, SIGMA_PSF / DJ, SIGMA_PSF / DI))
    return hu + rng.normal(0, BRUIT, hu.shape)


def ecrire_dicom(hu, dossier, rng):
    etude, serie, repere = generate_uid(), generate_uid(), generate_uid()
    ordre = list(range(NK))
    rng.shuffle(ordre)                                                           # noms sans rapport avec la position
    for n, k in enumerate(ordre):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = etude, serie, repere
        ds.Modality, ds.PatientName, ds.PatientID = "CT", "FANTOME^TEST", "0000"
        ds.StudyDate, ds.SeriesDescription, ds.SeriesNumber, ds.InstanceNumber = "20261012", "Fantome synthetique", 1, k + 1
        ds.ImagePositionPatient = [f"{ORIGINE[0]:.4f}", f"{ORIGINE[1]:.4f}", f"{ORIGINE[2] + k * DK:.4f}"]
        ds.ImageOrientationPatient = ["1", "0", "0", "0", "1", "0"]
        ds.PixelSpacing, ds.SliceThickness = [f"{DJ}", f"{DI}"], f"{DK}"
        ds.Rows, ds.Columns = NJ, NI
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.RescaleIntercept, ds.RescaleSlope = "-1024", "1"
        ds.PixelData = np.clip(np.rint(hu[k] + 1024), -32768, 32767).astype("<i2").tobytes()
        ds.save_as(Path(dossier) / f"IM{n:04d}", enforce_file_format=True)


# ------------------------------------------------------------------------------- vérifications
def verifier(condition, texte, details=""):
    print(f"  {'OK ' if condition else 'ÉCHEC'}  {texte}{('  — ' + details) if details else ''}")
    return bool(condition)


def main():
    debut = time.time()
    rng = np.random.default_rng(1)
    random.seed(1)
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        dicom, sortie = Path(tmp) / "dicom", Path(tmp) / "resultats"
        dicom.mkdir()
        print("Fabrication du fantôme et écriture DICOM…")
        ecrire_dicom(fabriquer_volume(rng), dicom, rng)

        print("1. Lecture DICOM")
        series = E1.inventaire(dicom)
        ok &= verifier(len(series) == 1, "une seule série trouvée", f"{len(series)}")
        v = E1.charger(series[0], journal=lambda *a: None)
        ok &= verifier(v.hu.shape == (NK, NJ, NI), "dimensions (coupes, lignes, colonnes)", str(v.hu.shape))
        ok &= verifier(np.allclose(v.espacement, (DK, DJ, DI)), "espacement", str(v.espacement))
        attendu = ORIGINE + [7 * DI, 5 * DJ, 3 * DK]
        ok &= verifier(np.allclose(v.vers_lps([3, 5, 7])[0], attendu, atol=1e-3), "position LPS du voxel (3, 5, 7)",
                       f"{v.vers_lps([3, 5, 7])[0].round(3)}")

        print("2-3. Segmentation et noms (points nommés)")
        seg = E2.segmenter(v, journal=lambda *a: None)
        centres = {n: ((a + b) / 2) @ ROT.T for n, (a, b) in OS.items()}      # centres des os (LPS)
        points = [{"nom": n, "position": c.tolist(), "systeme": "LPS"} for n, c in centres.items()]
        E3.identifier(seg, points, journal=lambda *a: None)
        noms = sorted(n for n in seg.noms.values() if n)
        ok &= verifier(noms == ["femur", "objet", "tibia"], "deux os nommés + le cylindre reconnu comme objet", str(noms))
        ok &= verifier(len(seg.noms) == 3, "aucun autre segment (la table est ignorée)", f"{len(seg.noms)} segments")

        print("4-5. Maillages et exactitude")
        P.AFFINAGE_DEMI_HAUTEUR = False                          # d'abord sans affinage : biais du seuil seul
        sans = E4.exporter(seg, sortie / "sans_affinage", journal=lambda *a: None)
        P.AFFINAGE_DEMI_HAUTEUR = True
        bilan = E4.exporter(seg, sortie, journal=lambda *a: None)
        # biais prévu : bord flou (PSF du scanner + lissage du programme) coupé au seuil de l'os
        sigma = sqrt(SIGMA_PSF ** 2 + P.SIGMA_LISSAGE_MM ** 2)
        frac = (P.SEUIL_OS_HU - 40) / (1300 - 40)
        prevu = sigma * sqrt(2) * erfinv(1 - 2 * frac)
        for nom, (a, b) in OS.items():
            m = bilan.get(nom)
            if not verifier(m is not None, f"{nom}.stl écrit"):
                ok = False
                continue
            ok &= verifier(m["etanche"] and m["orientation_coherente"] and m["morceaux"] == 1 and m["euler"] == 2,
                           f"{nom}.stl étanche, un morceau, Euler 2", f"Euler {m['euler']}, {m['triangles']} triangles")
            import trimesh
            vrai = (np.pi * R_OS ** 2 * np.linalg.norm(b - a) + 4 / 3 * np.pi * R_OS ** 3) / 1000
            t0 = trimesh.load(sortie / "sans_affinage" / f"{nom}.stl")
            d0 = distance_capsule(np.asarray(t0.vertices) @ ROT, a, b) - R_OS     # > 0 : à l'extérieur
            ok &= verifier(abs(d0.mean() - prevu) < 0.15, f"{nom}, seuil seul : surface à {d0.mean():+.2f} mm du bord vrai "
                           f"(théorie : {prevu:+.2f} mm)", f"volume {sans[nom]['volume_cm3']:.2f} cm³ pour {vrai:.2f} cm³ vrais")
            t = trimesh.load(sortie / f"{nom}.stl")
            d = distance_capsule(np.asarray(t.vertices) @ ROT, a, b) - R_OS
            ok &= verifier(abs(d.mean()) < 0.25 and np.percentile(np.abs(d), 95) < 0.3,
                           f"{nom}, avec affinage demi-hauteur : {d.mean():+.2f} mm en moyenne, P95 "
                           f"{np.percentile(np.abs(d), 95):.2f} mm", f"volume {m['volume_cm3']:.2f} cm³ pour {vrai:.2f} cm³ vrais")
    print(f"\n{'TOUT EST BON' if ok else 'AU MOINS UN ÉCHEC'} ({time.time() - debut:.0f} s)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
