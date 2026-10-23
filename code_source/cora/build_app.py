#!/usr/bin/env python3
"""
build_app.py — assemble la partie « Planification CORA » de CT-CORA3D en un seul fichier HTML (hors ligne).

  app/index.src.html     : structure + styles (gabarit)
  app/cora_simple.js     : cœur de calcul (testable sous Node : tests/test_cas.mjs, tests/test_reel.mjs)
  app/modules/*.js       : modules de l'interface (concaténés dans l'ordre des noms)
  build/bones_pack.*     : modèle osseux généré par generate_bones.py (fémur, tibia, fibula, rotule et fabelles gardés)
  vendor/three_bundle.js : Three.js r170 + modules complémentaires (voir vendor/three_entry.js)
  vendor/fonts/          : polices Archivo et JetBrains Mono (woff2)
  vendor/icon.png        : icône

Sortie : ../../application/interface/cora/index.html — servi par le serveur local (onglet 2). Aucune dépendance
réseau : ouvert seul (double-clic), il fonctionne aussi, avec l'os fictif uniquement.

Usage : python3 build_app.py      (bibliothèque standard uniquement)
"""
import base64
import gzip
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / "app"
BUILD = HERE / "build"
VENDOR = HERE / "vendor"
OUT = HERE.parent.parent / "application" / "interface" / "cora" / "index.html"
OS_GARDES = ["femur", "tibia", "fibula", "patella", "fabellae"]   # rotule et fabelles : obstacles des broches et du guide


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


# --- modèle osseux réduit aux trois os utiles ------------------------------------------------
meta = json.loads((BUILD / "bones_pack.json").read_text(encoding="utf-8"))
raw = gzip.decompress((BUILD / "bones_pack.bin.gz").read_bytes())
blob, bones = bytearray(), {}
for name in OS_GARDES:
    info = dict(meta["bones"][name])
    for key in ("pos", "idx", "ao", "cart", "med"):
        off, size = info[key]
        while len(blob) % 4:                       # alignement pour les vues Uint16 / Uint32
            blob.append(0)
        info[key] = [len(blob), size]
        blob += raw[off:off + size]
    bones[name] = info
meta_small = {k: meta[k] for k in ("version", "units", "side", "frame", "axis", "centerline", "calibration")}
meta_small["bones"] = bones
meta_small["landmarks"] = {k: meta["landmarks"][k] for k in OS_GARDES}
meta_json = json.dumps(meta_small, separators=(",", ":"))
b64 = base64.b64encode(gzip.compress(bytes(blob), 9, mtime=0)).decode("ascii")

# --- JavaScript : cœur + modules, imports « three » remplacés par le paquet embarqué ---------
core = (APP / "cora_simple.js").read_text(encoding="utf-8")
core = re.sub(r"^export (const|let|function|class) ", r"\1 ", core, flags=re.M)
parts = sorted((APP / "modules").glob("*.js"))
js = "\n".join(p.read_text(encoding="utf-8") for p in parts)
js = js.replace("/*__CORE__*/", core)


def local_import(m: re.Match) -> str:
    what = m.group(1).strip()
    if what.startswith("* as "):                       # import * as THREE from 'three'
        return f"const {what[5:].strip()} = __THREE__.THREE;"
    return f"const {what} = __THREE__;"                 # import { A, B } from 'three/addons/…'


js, n_imports = re.subn(r"^import (.+?) from 'three(?:/addons/[\w/]+\.js)?';$", local_import, js, flags=re.M)
assert not re.search(r"^import ", js, flags=re.M), "import non résolu"
three = (VENDOR / "three_bundle.js").read_text(encoding="utf-8")

# --- polices : url(fichier.woff2) -> data URI ------------------------------------------------
fonts = (VENDOR / "fonts" / "fonts.css").read_text(encoding="utf-8")
fonts = re.sub(r"url\(([\w.-]+\.woff2)\)", lambda m: f"url({data_uri(VENDOR / 'fonts' / m.group(1), 'font/woff2')})", fonts)

# --- assemblage ------------------------------------------------------------------------------
html = (APP / "index.src.html").read_text(encoding="utf-8")
for name, chunk in (("meta", meta_json), ("three", three), ("app", js)):
    assert "</script" not in chunk.lower(), f"« </script » dans {name}"
html = (html.replace("/*__FONTS__*/", fonts)
            .replace("/*__ICON__*/", data_uri(VENDOR / "icon.png", "image/png"))
            .replace("/*__BONES_META__*/", meta_json)
            .replace("/*__BONES_B64__*/", b64)
            .replace("/*__THREE__*/", three)
            .replace("/*__APP_JS__*/", js))
assert "/*__" not in html, "emplacement non rempli"
assert "https://cdn" not in html and "fonts.googleapis" not in html

head, body = html.split("<!--__BODY__-->")       # titre, méta, styles -> <head> ; le reste -> <body>
doc = ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
       + head + '</head><body>' + body + "</body></html>")
OUT.write_text(doc, encoding="utf-8")
print(f"OK : {OUT.name}  {len(doc) / 1e6:.2f} Mo  ({len(parts)} modules, {n_imports} imports Three.js locaux, "
      f"cœur {len(core) / 1e3:.0f} ko, os {len(b64) / 1e6:.2f} Mo, Three.js {len(three) / 1e3:.0f} ko)")
