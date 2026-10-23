@echo off
rem ===========================================================================
rem  creer_app_windows.bat - construit l'application AUTONOME CT-CORA3D pour Windows (double-clic).
rem
rem  Comme creer_app_autonome.sh sur macOS : Python et toutes les bibliotheques sont copies DANS l'application
rem  (PyInstaller, environ 1 Go). Elle s'ouvre dans sa propre fenetre (moteur WebView2 d'Edge, present sur
rem  Windows 10 et 11), sans navigateur ni Python a installer, et peut etre copiee sur un autre PC Windows 64 bits.
rem  Installation pour l'utilisateur seul (aucun droit administrateur) : %LOCALAPPDATA%\Programs\CT-CORA3D,
rem  raccourcis dans le menu Demarrer et sur le Bureau. Resultats : dossier du projet tant qu'il existe, sinon
rem  Documents\CT-CORA3D. Journal : %LOCALAPPDATA%\CTCORA3D\CTCORA3D.log
rem
rem  Construction hors OneDrive (des milliers de fichiers) : %LOCALAPPDATA%\CTCORA3D\construction-app.
rem  Duree : environ 10 min la premiere fois (telechargement des bibliotheques), ensuite 3 a 5 min.
rem  A relancer apres chaque modification du programme (code_source\ ou application\).
rem  Prerequis : Python 3.10 ou plus recent (python.org, "Add python.exe to PATH") et une connexion internet.
rem ===========================================================================
setlocal
set "ICI=%~dp0"
for %%I in ("%ICI%..") do set "APPLI=%%~fI"
for %%I in ("%ICI%..\..") do set "PROJET=%%~fI"
set "CACHE=%LOCALAPPDATA%\CTCORA3D\construction-app"
set "VENV=%CACHE%\venv-construction"
set "CIBLE=%LOCALAPPDATA%\Programs\CT-CORA3D"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "BASE="
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul && set "BASE=py -3"
if not defined BASE python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul && set "BASE=python"
if defined BASE goto environnement
echo Python 3.10 ou plus recent est introuvable : installez-le depuis https://www.python.org/downloads/
echo en cochant "Add python.exe to PATH", puis relancez ce fichier.
pause
exit /b 1

:environnement
echo 1/4 environnement de construction (%VENV%)
if not exist "%VENV%\Scripts\python.exe" %BASE% -m venv "%VENV%"
set "PY=%VENV%\Scripts\python.exe"
"%PY%" -m pip install -q --disable-pip-version-check -r "%APPLI%\requirements.txt" "pywebview>=5.0" "pyinstaller>=6.16"
if errorlevel 1 goto echec

echo 2/4 interface CORA et calibration des reperes a jour (l'application ne peut pas les reecrire)
"%PY%" "%PROJET%\code_source\cora\build_app.py"
if errorlevel 1 goto echec
pushd "%PROJET%\code_source"
"%PY%" -c "import etape6_reperes as E; E.calibration()"
set "CODE_CALIB=%ERRORLEVEL%"
popd
if not "%CODE_CALIB%"=="0" goto echec

echo 3/4 PyInstaller (plusieurs minutes)
set "CTCORA3D_CONSTRUCTION=%CACHE%\construction"
"%PY%" -m PyInstaller --noconfirm --log-level WARN --distpath "%CACHE%\dist" --workpath "%CTCORA3D_CONSTRUCTION%" "%ICI%ct_cora3d.spec"
if errorlevel 1 goto echec

echo 4/4 installation dans %CIBLE%
rem robocopy : code 0 a 7 = succes (8 et plus = erreur)
robocopy "%CACHE%\dist\CT-CORA3D" "%CIBLE%" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto echec
powershell -NoProfile -Command "$w = New-Object -ComObject WScript.Shell; foreach ($d in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) { $s = $w.CreateShortcut((Join-Path $d 'CT-CORA3D.lnk')); $s.TargetPath = '%CIBLE%\CT-CORA3D.exe'; $s.WorkingDirectory = '%CIBLE%'; $s.IconLocation = '%CIBLE%\CT-CORA3D.exe,0'; $s.Description = 'CT-CORA3D : segmentation CT, planification CORA, guides'; $s.Save() }"
echo.
echo OK : %CIBLE%\CT-CORA3D.exe (raccourcis : menu Demarrer et Bureau)
pause
exit /b 0

:echec
echo.
echo La construction a echoue : voir les messages ci-dessus.
pause
exit /b 1
