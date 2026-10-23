// =============================================================================
// campagne_export.mjs — campagne de simulation des guides sur l'os fictif : génération des cas
// -----------------------------------------------------------------------------
// Pour chaque cas (os × varus/valgus × procurvatum/recurvatum × amplitudes × niveau de l'apex × torsion × type de
// coin), planifie avec le cœur de calcul (référence « os sain ») et écrit dans <sortie>/<id>/ :
//   prescription.json, os.bin (os planifié), voisin_<nom>.bin (fibula ; rotule et fabelles pour le fémur, déformées
//   avec l'os : ceux que le cœur a évités), cartilage_<nom>.u8 (cartilage articulaire de chaque maillage, 0-255 par
//   sommet), planification.json (contrôles de la planification : angle vrai retrouvé, angles après correction, torsion,
//   règle de Paley, placement des broches, alertes…).
// Le modèle est celui de l'application : fémur, tibia, fibula, rotule, fabelles, avec la carte du cartilage.
// Usage : node tests/campagne_export.mjs <sortie> [coins|aleatoire|tout] [nombre aléatoire] [graine]
// =============================================================================
import fs from 'fs';
import zlib from 'zlib';
import path from 'path';
import { fileURLToPath } from 'url';
import * as C from '../cora/app/cora_simple.js';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const [OUT, MODE = 'tout', NB = '80', GRAINE = '7'] = process.argv.slice(2);
if (!OUT) { console.error('usage : node tests/campagne_export.mjs <sortie> [coins|aleatoire|tout] [nombre] [graine]'); process.exit(1); }
fs.mkdirSync(OUT, { recursive: true });

// modèle fictif avec la carte du cartilage
const meta = JSON.parse(fs.readFileSync(path.join(ICI, '../cora/build/bones_pack.json'), 'utf8'));
const raw = zlib.gunzipSync(fs.readFileSync(path.join(ICI, '../cora/build/bones_pack.bin.gz')));
const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
const bones = {}, cart = {};
for (const [name, info] of Object.entries(meta.bones)) {
  const q = new Uint16Array(buf, info.pos[0], info.pos[1] / 2);
  const pos = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) pos[i] = info.lo[i % 3] + q[i] * info.scale[i % 3];
  const idx = info.index32 ? Uint32Array.from(new Uint32Array(buf, info.idx[0], info.idx[1] / 4)) : Uint32Array.from(new Uint16Array(buf, info.idx[0], info.idx[1] / 2));
  cart[name] = new Uint8Array(buf.slice(info.cart[0], info.cart[0] + info.cart[1]));
  bones[name] = { pos, idx, cart: cart[name] };
}
const MODELE = { meta, bones: Object.fromEntries(['femur', 'tibia', 'fibula', 'patella', 'fabellae'].map((n) => [n, bones[n]])) };

const ecrireBin = (f, pos, idx) => fs.writeFileSync(f, Buffer.concat([Buffer.from(new Uint32Array([pos.length / 3, idx.length / 3]).buffer),
  Buffer.from(Float32Array.from(pos).buffer), Buffer.from(Uint32Array.from(idx).buffer)]));

// --- liste des cas
const cas = [];
let rng = (() => { let s = +GRAINE >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; })();
if (MODE === 'coins' || MODE === 'tout') {
  for (const bone of C.OS) {
    const R = C.REGLAGES[bone];
    for (const frontal of C.FRONTAL) for (const sagittal of C.SAGITTAL) {
      for (const F of [R.thetasF[0], R.thetasF[1]]) for (const S of sagittal === 'aucun' ? [0] : [R.thetasS[0], R.thetasS[1]]) {
        for (const niveau of [R.niveaux[0], R.niveaux[1]]) for (const torsion of [0, 20]) {
          cas.push({ bone, frontal, sagittal, F, S, niveau, torsion, serie: 'coins' });
        }
      }
    }
  }
}
if (MODE === 'aleatoire' || MODE === 'tout') {
  for (let i = 0; i < +NB; i++) {
    const bone = C.OS[Math.floor(rng() * 2)], R = C.REGLAGES[bone];
    const sagittal = C.SAGITTAL[Math.floor(rng() * 3)];
    cas.push({ bone, frontal: C.FRONTAL[Math.floor(rng() * 2)], sagittal,
      F: Math.round(R.thetasF[0] + rng() * (R.thetasF[1] - R.thetasF[0])),
      S: sagittal === 'aucun' ? 0 : Math.round(R.thetasS[0] + rng() * (R.thetasS[1] - R.thetasS[0])),
      niveau: +(R.niveaux[0] + rng() * (R.niveaux[1] - R.niveaux[0])).toFixed(3),
      torsion: Math.round(-30 + rng() * 60), serie: 'aleatoire' });
  }
}

// --- planification et export
const r6 = (x) => (Number.isFinite(x) ? +x.toFixed(6) : null);
let n = 0;
for (const c of cas) {
  const P = C.planifier(MODELE, C.casDe(`${c.bone}-${c.frontal}-${c.sagittal}`), { thetaF: c.F, thetaS: c.S || 3, niveau: c.niveau, torsion: c.torsion, reference: 'sain' });
  for (const kind of ['fermeture', 'ouverture']) {
    const id = `${String(++n).padStart(4, '0')}_${c.bone}_${c.frontal}_${c.sagittal}_F${c.F}_S${c.S}_n${Math.round(c.niveau * 100)}_t${c.torsion}_${kind}`;
    const d = path.join(OUT, id);
    fs.mkdirSync(d, { recursive: true });
    const O = P.osteo[kind], v = P.validation;
    const plan = {
      id, ...c, kind, osteoPossible: !!P.osteoPossible, theta: r6(P.theta), thetaVrai: r6(v.thetaVrai), ecartTheta: r6(v.ecartTheta),
      typeF: P.typeF, typeS: P.typeS, coraDansOs: !!P.coraDansOs, niveauCORA: r6(v.niveauCORA), niveauApex: r6(v.niveauApex),
      section: { largeur: r6(P.section.largeur), cvx: r6(P.section.cvx), ccv: r6(P.section.ccv), profondeur: r6(P.section.profondeur) },
      torsion: { avant: r6(P.torsion.avant), sain: r6(P.torsion.sain), statut: P.torsion.statut },
    };
    if (O) {
      const cles = [...C.CLES[c.bone].F, ...C.CLES[c.bone].S];
      const dirs = O.brochesApres.map((b) => C.V.norm(b.dir));
      plan.osteo = {
        residuel: r6(O.residuel), decalage: r6(O.decalage), dLongueur: r6(O.dLongueur), base: r6(O.base), D: r6(O.D),
        postMax: r6(Math.max(...cles.map((k) => Math.abs(O.post[k] - P.mesures.normal[k])))),
        derotation: r6(O.derotation), torsionApres: r6(O.torsionApres), torsionCible: r6(O.torsionCible),
        brochesParalleles: r6(Math.max(...dirs.map((x) => C.V.angle(x, dirs[0])))), angleBroches: r6(O.angleBroches),
        charniere: O.charniere.map(r6), distanceApex: r6(O.distanceApex),
        regle: O.regle, decalageCoupe: O.decalageCoupe, translationOsteo: r6(O.translationOsteo),
        placementBroches: O.placementBroches, alertes: O.alertes, largeurCoupe: r6(O.sectionCoupe.largeur),
      };
      plan.alertesPlanif = P.alertesPlanif;
      fs.writeFileSync(path.join(d, 'prescription.json'), JSON.stringify(C.prescription(P, kind)));
      ecrireBin(path.join(d, 'os.bin'), P.pos[c.bone], bones[c.bone].idx);
      fs.writeFileSync(path.join(d, `cartilage_${c.bone}.u8`), cart[c.bone]);
      // voisins tels que le cœur les a vus : fibula (maillage du tibia), rotule et fabelles (déformées avec le fémur)
      const voisins = { ...Object.fromEntries(P.meshes.filter((n) => n !== c.bone).map((n) => [n, P.pos[n]])), ...P.voisins };
      for (const [nom, pos] of Object.entries(voisins)) {
        ecrireBin(path.join(d, `voisin_${nom}.bin`), pos, bones[nom].idx);
        fs.writeFileSync(path.join(d, `cartilage_${nom}.u8`), cart[nom]);
      }
    }
    fs.writeFileSync(path.join(d, 'planification.json'), JSON.stringify(plan));
  }
}
console.log(`${n} cas écrits dans ${OUT} (${cas.length} déformités × 2 types de coin)`);
