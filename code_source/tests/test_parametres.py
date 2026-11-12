"""
test_parametres.py — vérifie que les paramètres du guide générique sont les mêmes partout.

Ils sont écrits à trois endroits : parametres.py (valeurs par défaut), etape7_guide.PARAMETRES_GUIDE (bornes) et
cora/app/cora_simple.js > PARAMS_GUIDE (panneau de l'interface). Ce test compare, pour chaque paramètre, la valeur par
défaut et les bornes. Les paramètres « plan » du JavaScript ne servent qu'à la planification et n'ont pas d'équivalent
dans l'étape 7.
Usage (depuis code_source/) : python tests/test_parametres.py      (il faut node)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
import etape7_guide as E7  # noqa: E402
import parametres as P  # noqa: E402

node = shutil.which("node")
if not node:
    sys.exit("node introuvable : test ignoré")
js = subprocess.run([node, "--input-type=module", "-e",
                     f"const C = await import({json.dumps((ICI.parent / 'cora/app/cora_simple.js').as_uri())});"
                     "console.log(JSON.stringify(C.PARAMS_GUIDE));"], capture_output=True, text=True, check=True)
erreurs = []
vus = set()
for p in json.loads(js.stdout):
    if p.get("plan"):
        continue
    cle = p["cle"]
    if cle not in E7.PARAMETRES_GUIDE:
        erreurs.append(f"{cle} : présent dans l'interface, absent de l'étape 7")
        continue
    vus.add(cle)
    attr, lo, hi = E7.PARAMETRES_GUIDE[cle][:3]
    defaut = getattr(P, attr)
    for nom, a, b in (("défaut", p["def"], defaut), ("minimum", p["min"], lo), ("maximum", p["max"], hi)):
        if abs(float(a) - float(b)) > 1e-9:
            erreurs.append(f"{cle} : {nom} {a} dans l'interface, {b} en Python")
for cle in sorted(set(E7.PARAMETRES_GUIDE) - vus):
    erreurs.append(f"{cle} : présent dans l'étape 7, absent de l'interface")
print("\n".join(f"  ÉCHEC  {e}" for e in erreurs) or f"  ok   {len(vus)} paramètres identiques (défaut et bornes)")
sys.exit(1 if erreurs else 0)
