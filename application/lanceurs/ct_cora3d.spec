# -*- mode: python ; coding: utf-8 -*-
# ct_cora3d.spec — recette PyInstaller de l'application autonome CT-CORA3D, pour macOS (« CT-CORA3D.app ») et pour
# Windows (dossier « CT-CORA3D » avec CT-CORA3D.exe). PyInstaller construit pour le système sur lequel il tourne :
# lancée par creer_app_autonome.sh (macOS) ou creer_app_windows.bat (Windows), qui fixent CTCORA3D_CONSTRUCTION
# (dossier de travail, hors OneDrive).
# Contenu : Python, les bibliothèques (numpy, scipy, SimpleITK, VTK, pyvista, trimesh, manifold3d, matplotlib, pydicom,
# pywebview), le programme (application/ et code_source/) et ses données (interface, icône, calibration des repères).
# Rien n'est écrit dans l'application à l'usage : voir parametres.py pour les dossiers.
import json
import os
import sys
import time
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

MAC, WINDOWS = sys.platform == "darwin", sys.platform == "win32"
LANCEURS = Path(SPECPATH)
APPLI = LANCEURS.parent
PROJET = APPLI.parent
CODE = PROJET / "code_source"
TRAVAIL = Path(os.environ["CTCORA3D_CONSTRUCTION"])
TRAVAIL.mkdir(parents=True, exist_ok=True)
VERSION = time.strftime("%Y.%m.%d")

# dossier du projet d'origine : l'application y range ses résultats tant qu'il existe (parametres.py)
(TRAVAIL / "construction.json").write_text(json.dumps({"projet": str(PROJET), "version": VERSION}), encoding="utf-8")

donnees = [
    (str(APPLI / "interface"), "application/interface"),
    (str(APPLI / "icone"), "application/icone"),
    (str(CODE / "calibration_reperes.json"), "."),
    (str(TRAVAIL / "construction.json"), "."),
]
donnees += collect_data_files("trimesh") + collect_data_files("pyvista")

modules = ["serveur", "fenetre", "etape1_lecture_dicom", "etape2_segmentation", "etape3_identification",
           "etape4_maillage", "etape5_controle", "etape6_reperes", "etape7_guide", "dessin_guide", "lancer_tout",
           "parametres", "vtk_leger", "vtkmodules.util.numpy_support",
           # exports chargés par matplotlib au moment d'enregistrer (plans 2D du guide en PDF et SVG)
           "matplotlib.backends.backend_agg", "matplotlib.backends.backend_pdf", "matplotlib.backends.backend_svg"]
# moteur de la fenêtre : WebKit (Cocoa) sur macOS ; WebView2 (Edge, via pythonnet et WinForms) sur Windows
modules += ["webview.platforms.cocoa"] if MAC else ["webview.platforms.winforms", "webview.platforms.edgechromium", "clr"]
modules += collect_submodules("pydicom") + collect_submodules("pyvista")

a = Analysis(
    [str(APPLI / "ct_cora3d_app.py")],
    pathex=[str(APPLI), str(CODE)],
    datas=donnees,
    hiddenimports=modules,
    excludes=["tkinter", "_tkinter", "IPython", "jupyter", "notebook", "pytest", "PyQt5", "PyQt6", "PySide2",
              "PySide6", "wx", "PyObjCTest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CT-CORA3D", console=False, argv_emulation=False,
          icon=str(APPLI / "icone" / ("icone.icns" if MAC else "icone.ico")))
coll = COLLECT(exe, a.binaries, a.datas, name="CT-CORA3D")
if MAC:                            # paquet .app (Windows : le dossier CT-CORA3D, avec CT-CORA3D.exe, suffit)
    app = BUNDLE(
        coll,
        name="CT-CORA3D.app",
        icon=str(APPLI / "icone" / "icone.icns"),
        bundle_identifier="be.ecam.pmd2.ctcora3d",
        version=VERSION,
        info_plist={
            "CFBundleName": "CT-CORA3D",
            "CFBundleDisplayName": "CT-CORA3D",
            "CFBundleShortVersionString": VERSION,
            "LSApplicationCategoryType": "public.app-category.medical",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            # textes des demandes d'accès de macOS (premier accès à chacun de ces dossiers)
            "NSDocumentsFolderUsageDescription": "CT-CORA3D lit les séries DICOM et enregistre ses résultats (segmentation, guides) dans le dossier choisi.",
            "NSDesktopFolderUsageDescription": "CT-CORA3D lit les séries DICOM du dossier choisi.",
            "NSDownloadsFolderUsageDescription": "CT-CORA3D lit les séries DICOM du dossier choisi.",
            "NSRemovableVolumesUsageDescription": "CT-CORA3D lit les séries DICOM d'un disque externe ou d'une clé USB.",
            "NSNetworkVolumesUsageDescription": "CT-CORA3D lit les séries DICOM d'un dossier réseau.",
            "NSFileProviderDomainUsageDescription": "CT-CORA3D lit les séries DICOM et enregistre ses résultats dans le dossier du projet (OneDrive).",
        },
    )
