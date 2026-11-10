"""
lancer_tout.py — du dossier DICOM aux os en STL, puis aux repères pour CORA 3D, en une commande (PMD2).

Rôle    : pour chaque série DICOM trouvée : lecture (étape 1), segmentation par seuillage et croissance de région
          (étape 2), identification des os et corrections anatomiques (étape 3), maillages étanches (étape 4),
          contrôle et rapport (étape 5), repères anatomiques du fémur et du tibia complets pour la planification
          CORA (étape 6).
Entrées : un dossier DICOM (par défaut : le dossier CT-scan lui-même) ; facultatif : resultats/<série>/graines.json
          (points nommés par l'utilisateur, par exemple avec l'application).
Sorties : resultats/<série>/ : <os>.stl, segmentation.seg.nrrd, rapport.md, rapport.json, aperçus PNG,
          reperes_auto.mrk.json (tête fémorale), cora_femur.json / cora_tibia.json (+ .bin, .png) : repères pour CORA.

Exemples :
    python lancer_tout.py                         # toutes les séries du dossier CT-scan
    python lancer_tout.py --liste                 # inventaire seulement
    python lancer_tout.py --serie hip_to_knee     # une série (un morceau de son nom suffit s'il est unique)
    python lancer_tout.py --dossier "D:/CT chien 12" --sortie "D:/resultats" --seuil 250 --ras
"""
import argparse
import json
import sys
import time
from pathlib import Path

import etape1_lecture_dicom as E1
import etape2_segmentation as E2
import etape3_identification as E3
import etape4_maillage as E4
import etape5_controle as E5
import etape6_reperes as E6
import parametres as P


def lire_graines(dossier):
    """Points nommés {"points": [{"nom": "femur", "position": [x, y, z], "systeme": "LPS"}, …]}."""
    f = Path(dossier) / "graines.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8")).get("points", [])


def traiter(serie, sortie=None, points=None, avec_sensibilite=True, avec_images=None, journal=print, etape=None,
            volume=None):
    """Toute la chaîne pour une série. `etape(n)` est appelée au début de chaque étape (suivi dans l'application) ;
    `volume` : volume déjà chargé (l'application l'a en mémoire). Renvoie (rapport, volume, segmentation, bilan)."""
    debut = time.time()
    dossier = Path(sortie or P.RESULTATS) / serie.nom
    dossier.mkdir(parents=True, exist_ok=True)
    points = lire_graines(dossier) if points is None else points
    journal(f"── {serie.nom} ──")
    (etape or (lambda n: None))(1)
    journal("Étape 1 : lecture DICOM")
    volume = volume or E1.charger(serie, journal)
    i = volume.infos
    journal(f"  {i['dimensions_kji'][0]} coupes de {i['dimensions_kji'][1]} × {i['dimensions_kji'][2]} pixels, voxel "
            f"{i['espacement_kji_mm'][2]:.3f} × {i['espacement_kji_mm'][1]:.3f} × {i['espacement_kji_mm'][0]:.3f} mm")
    (etape or (lambda n: None))(2)
    journal(f"Étape 2 : seuillage ({P.SEUIL_OS_HU} HU) et croissance de région")
    seg = E2.segmenter(volume, journal)
    (etape or (lambda n: None))(3)
    journal("Étape 3 : identification des os" + (f" ({len(points)} point(s) nommé(s) par l'utilisateur)" if points else ""))
    E3.identifier(seg, points, journal)
    (etape or (lambda n: None))(4)
    journal(f"Étape 4 : maillages étanches (STL, {P.SYSTEME_COORDONNEES}, mm) → {dossier}")
    bilan = E4.exporter(seg, dossier, journal)
    (etape or (lambda n: None))(5)
    journal("Étape 5 : contrôle (seuil ± 50 HU), aperçus et rapport")
    rapport = E5.controler(seg, volume, bilan, dossier, debut, avec_sensibilite, avec_images, journal)
    (etape or (lambda n: None))(6)
    journal("Étape 6 : repères anatomiques pour CORA 3D (fémur, tibia et radius complets)")
    for ancien in dossier.glob("cora_*"):                # repères d'un calcul précédent : refaits
        ancien.unlink()
    cora = E6.traiter_serie(dossier, journal, images=P.IMAGES_CONTROLE if avec_images is None else avec_images)
    E6.ajouter_au_rapport(dossier, cora)
    cas = E6.choisir_cible(dossier, cora)
    journal(f"  os à planifier : {cas['cible'] or 'aucun'} ({cas['raison']})")
    rapport["cora"] = {k: {"complet": r.get("complet"), "raison": r.get("raison")} for k, r in cora.items()}
    journal(f"  terminé en {time.time() - debut:.0f} s, rapport : {dossier / 'rapport.md'}")
    return rapport, volume, seg, bilan


def main():
    a = argparse.ArgumentParser(description="CT DICOM → segmentation osseuse → STL étanches (PMD2, partie 1)")
    a.add_argument("--dossier", type=Path, default=P.DOSSIER_DICOM, help="dossier contenant les DICOM")
    a.add_argument("--sortie", type=Path, default=P.RESULTATS, help="dossier des résultats")
    a.add_argument("--serie", action="append", help="nom (ou morceau de nom) d'une série ; répétable")
    a.add_argument("--liste", action="store_true", help="afficher les séries trouvées et s'arrêter")
    a.add_argument("--seuil", type=float, help=f"seuil de l'os en HU (défaut {P.SEUIL_OS_HU})")
    a.add_argument("--ras", action="store_true", help="STL en RAS au lieu de LPS")
    a.add_argument("--sans-controle", action="store_true", help="sans la sensibilité au seuil (± 50 HU)")
    a.add_argument("--sans-images", action="store_true", help="sans les aperçus PNG")
    x = a.parse_args()
    if x.seuil:
        P.SEUIL_OS_HU = int(x.seuil)
    if x.ras:
        P.SYSTEME_COORDONNEES = "RAS"
    print(f"Inventaire DICOM de {x.dossier} …")
    series = E1.inventaire(x.dossier)
    if not series:
        sys.exit("Aucune série DICOM trouvée.")
    for s in series:
        print("  " + E1.decrire(s))
    if x.liste:
        return
    choix = [E1.trouver(series, n) for n in x.serie] if x.serie else series
    debut = time.time()
    for s in choix:
        traiter(s, x.sortie, avec_sensibilite=not x.sans_controle, avec_images=not x.sans_images)
    print(f"\n{len(choix)} série(s) traitée(s) en {time.time() - debut:.0f} s. Résultats : {x.sortie}")


if __name__ == "__main__":
    main()
