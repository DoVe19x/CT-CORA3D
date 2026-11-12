"""
refaire_exemples.py — reconstruit les guides de démonstration livrés avec le projet (dossier exemples/).

Rôle    : planifie quelques cas avec le cœur de calcul JavaScript (cora/app/cora_simple.js, comme l'onglet CORA), puis
          construit leurs guides avec l'étape 7, exactement comme l'application :
            os fictif   : fémur varus + procurvatum (coin de fermeture), tibia valgus (fermeture, face médiale),
                          tibia varus + procurvatum (ouverture, face médiale) ;
            lévrier     : fémur varus + procurvatum (hip_to_knee) et tibia valgus (knee_to_ankle), coin de fermeture.
          Un tibia varus se corrige par un coin d'ouverture médial : son coin de fermeture passerait par la face latérale,
          derrière la fibula, et l'étape 7 le refuse (aucun guide entre l'os et la fibula).
Entrées : exemples/<série>/cora_<os>.json et .bin (étape 6) ; modèle de l'os fictif (cora/build/bones_pack.*).
Sorties : exemples/<série>/guide_<os>_<coin>/ et exemples/_os_fictif/guide_<os>_<coin>/ (fichiers de l'étape 7).
Usage   : python refaire_exemples.py        (depuis code_source/ ; il faut node)
À relancer après une modification des guides (étape 7) ou de la planification (cora_simple.js).
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

import etape7_guide as E7
import parametres as P

CAS = [  # (série ou None pour l'os fictif, os, cas de déformation, coin, torsion de test en degrés, réglages)
    (None, "femur", "femur-varus-procurvatum", "fermeture", 0, {"thetaF": 16, "thetaS": 15, "niveau": 0.75}),
    (None, "tibia", "tibia-valgus-aucun", "fermeture", 0, {"thetaF": 12, "niveau": 0.6}),
    (None, "tibia", "tibia-varus-procurvatum", "ouverture", 0, {"thetaF": 15, "thetaS": 10, "niveau": 0.6}),
    ("greyhound_hindlimb_hip_to_knee", "femur", "femur-varus-procurvatum", "fermeture", 15, {}),
    ("greyhound_hindlimb_knee_to_ankle", "tibia", "tibia-valgus-aucun", "fermeture", 0, {}),
]

EXPORT_JS = r"""
import fs from 'fs'; import path from 'path'; import zlib from 'zlib';
const [CODE, OUT, CAS] = process.argv.slice(2);
const C = await import(path.join(CODE, 'cora/app/cora_simple.js'));
const lireBin = (f) => { const b = fs.readFileSync(f), ab = b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
  const [nv, nf] = new Uint32Array(ab, 0, 2); return { pos: new Float32Array(ab, 8, nv * 3).slice(), idx: new Uint32Array(ab, 8 + nv * 12, nf * 3).slice() }; };
const ecrireBin = (f, pos, idx) => fs.writeFileSync(f, Buffer.concat([Buffer.from(new Uint32Array([pos.length / 3, idx.length / 3]).buffer),
  Buffer.from(Float32Array.from(pos).buffer), Buffer.from(Uint32Array.from(idx).buffer)]));
// os fictif : même modèle que l'application (fémur, tibia, fibula, rotule, fabelles, cartilage)
const meta = JSON.parse(fs.readFileSync(path.join(CODE, 'cora/build/bones_pack.json'), 'utf8'));
const raw = zlib.gunzipSync(fs.readFileSync(path.join(CODE, 'cora/build/bones_pack.bin.gz')));
const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
const fictif = {};
for (const name of ['femur', 'tibia', 'fibula', 'patella', 'fabellae']) {
  const info = meta.bones[name];
  const q = new Uint16Array(buf, info.pos[0], info.pos[1] / 2), pos = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) pos[i] = info.lo[i % 3] + q[i] * info.scale[i % 3];
  const idx = info.index32 ? Uint32Array.from(new Uint32Array(buf, info.idx[0], info.idx[1] / 4)) : Uint32Array.from(new Uint16Array(buf, info.idx[0], info.idx[1] / 2));
  fictif[name] = { pos, idx, cart: new Uint8Array(buf.slice(info.cart[0], info.cart[0] + info.cart[1])) };
}
for (const [i, [serie, bone, cas, kind, torsion, reglages]] of JSON.parse(CAS).entries()) {
  let model, idx;
  if (serie) {
    const dir = path.join(CODE, '..', 'exemples', serie);
    const json = JSON.parse(fs.readFileSync(path.join(dir, `cora_${bone}.json`)));
    const meshes = Object.fromEntries(Object.entries(json.maillages).map(([n, f]) => [n, lireBin(path.join(dir, f))]));
    model = C.modeleReel(json, meshes); idx = meshes;
  } else {
    model = { meta, bones: fictif }; idx = fictif;
  }
  const P = C.planifier(model, C.casDe(cas), { reference: 'sain', torsion, ...reglages });
  if (!P.osteo[kind]) throw new Error(`${cas} : pas de coin de ${kind}`);
  const d = path.join(OUT, String(i)); fs.mkdirSync(d, { recursive: true });
  fs.writeFileSync(path.join(d, 'prescription.json'), JSON.stringify(C.prescription(P, kind), null, 2));
  ecrireBin(path.join(d, 'os.bin'), P.pos[bone], idx[bone].idx);
  const voisins = { ...Object.fromEntries(P.meshes.filter((n) => n !== bone).map((n) => [n, P.pos[n]])), ...(P.voisins || {}) };
  for (const [nom, pos] of Object.entries(voisins)) if (idx[nom]) ecrireBin(path.join(d, `voisin_${nom}.bin`), pos, idx[nom].idx);
  if (P.articulaire) fs.writeFileSync(path.join(d, 'articulaire.u8'), Uint8Array.from(P.articulaire, (x) => (x ? 255 : 0)));
}
"""


def lire_bin(f):
    b = Path(f).read_bytes()
    nv, nf = np.frombuffer(b[:8], np.uint32)
    return (np.frombuffer(b[8:8 + 12 * nv], np.float32).reshape(-1, 3).astype(float),
            np.frombuffer(b[8 + 12 * nv:], np.uint32).reshape(-1, 3).astype(np.int64))


def main():
    node = shutil.which("node")
    if not node:
        sys.exit("node est introuvable : il faut Node.js pour planifier les cas (cœur de calcul JavaScript)")
    tmp = Path(tempfile.mkdtemp(prefix="exemples_"))
    (tmp / "export.mjs").write_text(EXPORT_JS, encoding="utf-8")
    r = subprocess.run([node, str(tmp / "export.mjs"), str(Path(__file__).resolve().parent), str(tmp), json.dumps(CAS)],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        sys.exit(f"planification impossible : {r.stderr.strip()[-600:]}")
    for i, (serie, os_, _cas, kind, _t, _r) in enumerate(CAS):
        src = tmp / str(i)
        dossier = P.EXEMPLES / (serie or "_os_fictif") / f"guide_{os_}_{kind}"
        shutil.rmtree(dossier, ignore_errors=True)
        dossier.mkdir(parents=True)
        v, f = lire_bin(src / "os.bin")
        shutil.copy(src / "prescription.json", dossier / "prescription.json")
        E7.ecrire_stl(dossier / "os_planifie.stl", v, f, "os planifie")
        E7.ecrire_bin(dossier / "os_planifie.bin", v, f)
        voisins = []
        for fv in sorted(src.glob("voisin_*.bin")):
            nom = fv.stem[len("voisin_"):]
            vv, ff = lire_bin(fv)
            voisins.append((nom, vv, ff))
            shutil.copy(fv, dossier / fv.name)
        art = np.frombuffer((src / "articulaire.u8").read_bytes(), np.uint8) if (src / "articulaire.u8").exists() else None
        info = E7.generer(src / "prescription.json", (v, f), dossier, journal=lambda *_: None, voisins=voisins,
                          articulaire=art)
        print(f"{dossier.relative_to(P.RACINE)} : {len(info['alertes'])} alerte(s)"
              + (f" ({'; '.join(info['alertes'])})" if info["alertes"] else ""))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
