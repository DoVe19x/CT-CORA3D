// =============================================================================
// test_reel.mjs — planification CORA sur les os segmentés (fémur, tibia du CT)
// -----------------------------------------------------------------------------
// Lit resultats/<série>/cora_<os>.json et cora_<os>.bin (écrits par etape6_reperes.py) et vérifie :
//   1. l'os tel quel, référence « valeurs normales » : planification sans erreur, angles comparés aux normes ;
//   2. déformités de test sur l'os réel (6 cas : varus / valgus × aucun / procurvatum / recurvatum), référence =
//      l'os avant déformité (membre controlatéral idéal) : θ, F, S retrouvés, angles post-opératoires = normaux,
//      angle et translation résiduels nuls, broches parallèles après correction, prescription complète ;
//   3. mêmes déformités, référence « valeurs normales » : θ retrouvé à l'écart naturel de l'os près ; fémur : CORA
//      au niveau de l'apex (règle « une seule angulation ») ;
//   4. matrice os -> scanner de la prescription : redonne les repères dans le repère du scanner.
//
// Usage : node tests/test_reel.mjs [dossier resultats]   (défaut : ../../resultats)
// =============================================================================
import fs from 'fs';
import zlib from 'zlib';
import path from 'path';
import { fileURLToPath } from 'url';
import * as C from '../app/cora_simple.js';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const RES = path.resolve(process.argv[2] || path.join(ROOT, '..', '..', 'resultats'));
let echecs = 0;
const V3n = (a) => { const l = Math.hypot(...a); return a.map((x) => x / l); };
const angDeg = (a, b) => Math.acos(Math.min(1, Math.max(-1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))) * 180 / Math.PI;
const ok = (cond, txt) => { console.log(`${cond ? '  ok    ' : '  ÉCHEC  '}${txt}`); if (!cond) echecs++; };

function lireBin(f) {
  const b = fs.readFileSync(f);
  const ab = b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
  const [nv, nf] = new Uint32Array(ab, 0, 2);
  return { pos: new Float32Array(ab, 8, nv * 3).slice(), idx: new Uint32Array(ab, 8 + nv * 12, nf * 3).slice() };
}
// gabarit du fémur : os sain du modèle synthétique
function modeleFictif() {
  const meta = JSON.parse(fs.readFileSync(path.join(ROOT, 'build/bones_pack.json'), 'utf8'));
  const raw = zlib.gunzipSync(fs.readFileSync(path.join(ROOT, 'build/bones_pack.bin.gz')));
  const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
  const bones = {};
  for (const name of ['femur', 'tibia', 'fibula']) {
    const info = meta.bones[name];
    const q = new Uint16Array(buf, info.pos[0], info.pos[1] / 2);
    const pos = new Float32Array(q.length);
    for (let i = 0; i < q.length; i++) pos[i] = info.lo[i % 3] + q[i] * info.scale[i % 3];
    const idx = info.index32 ? Uint32Array.from(new Uint32Array(buf, info.idx[0], info.idx[1] / 4)) : Uint32Array.from(new Uint16Array(buf, info.idx[0], info.idx[1] / 2));
    bones[name] = { pos, idx };
  }
  return { meta, bones };
}
const GABARIT = C.gabaritFemur(modeleFictif());
console.log(`Gabarit du fémur (modèle sain) : l'axe anatomique coupe la JOL distale à ${(GABARIT.fF * 100).toFixed(1)} % (face), ${(GABARIT.fS * 100).toFixed(1)} % (profil)`);

const series = fs.existsSync(RES) ? fs.readdirSync(RES).filter((d) => fs.statSync(path.join(RES, d)).isDirectory()) : [];
let nbOs = 0;
for (const serie of series) {
  for (const bone of ['femur', 'tibia']) {
    const fj = path.join(RES, serie, `cora_${bone}.json`);
    if (!fs.existsSync(fj)) continue;
    const json = JSON.parse(fs.readFileSync(fj, 'utf8'));
    if (!json.complet) { console.log(`\n${serie} / ${bone} : non analysé (${json.raison})`); continue; }
    nbOs++;
    const meshes = {};
    for (const [n, f] of Object.entries(json.maillages)) meshes[n] = lireBin(path.join(RES, serie, f));
    const model = C.modeleReel(json, meshes);
    const normales = { type: 'normales', valeurs: Object.fromEntries(Object.entries(json.normales).map(([k, x]) => [k, x.valeur])),
      sd: Object.fromEntries(Object.entries(json.normales).map(([k, x]) => [k, x.sd])), gabarit: GABARIT };
    console.log(`\n${serie} / ${bone} (membre ${json.cote}${json.miroir ? ', mis en miroir' : ''}, ${json.longueur_mm} mm, maillage ${meshes[bone].idx.length / 3} triangles)`);

    // 1. os tel quel
    const t0 = Date.now();
    const P0 = C.planifier(model, C.casDe(`${bone}-varus-aucun`), { sansDeformite: true, reference: normales });
    const cles = [...C.CLES[bone].F, ...C.CLES[bone].S];
    console.log(`   tel quel (${Date.now() - t0} ms) : ` + cles.map((k) => `${k} ${P0.mesures.pre[k].toFixed(1)}° (normal ${P0.mesures.normal[k].toFixed(1)})`).join(', '));
    ok(cles.every((k) => Number.isFinite(P0.mesures.pre[k])), 'angles mesurés finis');
    ok(P0.anomalies.length === 0, `angles dans les normes (± 2 écarts-types)${P0.anomalies.length ? ' — hors normes : ' + P0.anomalies.join(', ') : ''}`);
    console.log(`   θ entre les axes ${P0.theta.toFixed(2)}° (F ${P0.Fm.toFixed(2)}°, S ${P0.Sm.toFixed(2)}°), CORA ${P0.coraDansOs ? 'dans l\'os' : 'hors de l\'os'}, ostéotomie ${P0.osteoPossible ? 'calculable' : 'non calculée'}`);
    ok(Number.isFinite(P0.theta) && Number.isFinite(P0.coraC[0]) && Number.isFinite(P0.section.largeur), 'planification sans valeur non définie');

    // 4. matrice os -> scanner
    if (P0.osteoPossible) {
      const pr = C.prescription(P0, 'fermeture');
      const M = pr.os_segmente.repere_scanner.os_vers_scanner;
      let e = 0;
      for (const [k, p] of Object.entries(json.reperes)) {
        const q = [0, 1, 2].map((i) => M[i][0] * p[0] + M[i][1] * p[1] + M[i][2] * p[2] + M[i][3]);
        e = Math.max(e, Math.hypot(...q.map((x, i) => x - json.reperes_scanner[k][i])));
      }
      ok(e < 0.01, `matrice os → scanner de la prescription (écart max ${e.toFixed(4)} mm, déterminant ${pr.os_segmente.repere_scanner.determinant})`);
    }

    // 2. et 3. déformités de test
    let pireTheta = 0, pirePost = 0, pireRes = 0, pireTrans = 0, pireBroches = 0, pireNorm = 0, pireNiveau = 0;
    for (const frontal of C.FRONTAL) for (const sagittal of C.SAGITTAL) {
      const cas = C.casDe(`${bone}-${frontal}-${sagittal}`);
      const P = C.planifier(model, cas, { reference: 'sain' });
      const v = P.validation;
      pireTheta = Math.max(pireTheta, Math.abs(v.ecartTheta));
      ok(P.osteoPossible && P.typeF === frontal && P.typeS === sagittal && Math.abs(P.Fm) > 0 && Math.abs(v.ecartTheta) < 0.05,
        `${cas.titre} (réf. os avant déformité) : θ ${P.theta.toFixed(2)}° pour ${v.thetaVrai.toFixed(2)}°, F ${Math.abs(P.Fm).toFixed(2)}° (vrai ${Math.abs(v.FProjVrai).toFixed(2)}), S ${Math.abs(P.Sm).toFixed(2)}° (vrai ${Math.abs(v.SProjVrai).toFixed(2)})`);
      for (const kind of ['fermeture', 'ouverture']) {
        const O = P.osteo[kind];
        pirePost = Math.max(pirePost, ...cles.map((k) => Math.abs(O.post[k] - P.mesures.normal[k])));
        pireRes = Math.max(pireRes, O.residuel); pireTrans = Math.max(pireTrans, O.decalage);
        const dirsApres = O.brochesApres.map((bb) => V3n(bb.dir));
        pireBroches = Math.max(pireBroches, ...dirsApres.map((dd) => angDeg(dd, dirsApres[0])));
        const pr = C.prescription(P, kind);
        if (!(pr.plans_coupe.length === (kind === 'fermeture' ? 2 : 1) && pr.broches.length === 2 && pr.os_segmente && pr.verite_terrain)) ok(false, `prescription ${kind} incomplète`);
      }
      const Pn = C.planifier(model, cas, { reference: normales });
      pireNorm = Math.max(pireNorm, Math.abs(Pn.validation.ecartTheta));
      if (bone === 'femur' && Pn.coraDansOs) pireNiveau = Math.max(pireNiveau, Math.abs(Pn.validation.niveauCORA - Pn.validation.niveauApex));
    }
    ok(pireTheta < 0.05, `θ retrouvé (réf. os avant déformité) : écart max ${pireTheta.toFixed(4)}°`);
    ok(pirePost < 0.1, `angles après correction = angles avant déformité : écart max ${pirePost.toFixed(4)}°`);
    ok(pireRes < 0.01 && pireTrans < 0.5, `angle résiduel max ${pireRes.toFixed(4)}°, translation résiduelle max ${pireTrans.toFixed(3)} mm`);
    ok(pireBroches < 0.01, `broches : les 4 parallèles après correction (écart max ${pireBroches.toFixed(4)}°)`);
    console.log(`   réf. valeurs normales : écart max à θ vrai ${pireNorm.toFixed(2)}° (écart naturel de cet os aux normes)` +
      (bone === 'femur' ? ` ; niveau du CORA − niveau de l'apex : max ${pireNiveau.toFixed(1)} mm` : ''));
    ok(pireNorm < 10, `réf. valeurs normales : θ retrouvé à moins de 10°`);

    // 5. torsion de test (15° externe) + varus + procurvatum : la dérotation ramène la torsion de l'os sain, sans angle
    //    ni translation résiduels ; les 4 broches de réduction sont parallèles après correction (et pas avant)
    for (const kind of ['fermeture', 'ouverture']) {
      const Pt = C.planifier(model, C.casDe(`${bone}-varus-procurvatum`), { reference: 'sain', torsion: 15 });
      const O = Pt.osteo[kind];
      const dirs = O.brochesApres.map((bb) => V3n(bb.dir));
      const parall = Math.max(...dirs.map((d) => angDeg(d, dirs[0])));
      const avant = O.brochesReduction.map((bb) => V3n(bb.dir));
      ok(Math.abs(O.torsionApres - Pt.torsion.sain) < 0.1 && O.residuel < 0.01 && O.decalage < 0.5 && parall < 1e-6 && angDeg(avant[0], avant[2]) > 5,
        `${kind}, torsion de test 15° : torsion ${Pt.torsion.avant.toFixed(1)}° → ${O.torsionApres.toFixed(2)}° (os sain ${Pt.torsion.sain.toFixed(2)}°), dérotation ${O.derotation.toFixed(2)}°, résiduel ${O.residuel.toFixed(4)}°, broches parallèles à ${parall.toExponential(1)}°`);
      const pr = C.prescription(Pt, kind);
      if (!(pr.broches_reduction.length === 4 && pr.guide_reduction.broches_apres_correction.length === 4 && Math.abs(pr.correction.derotation_deg - O.derotation) < 0.01)) ok(false, 'prescription : système de réduction incomplet');
    }
  }
}
if (!nbOs) console.log(`Aucun os complet analysé dans ${RES} : lancer d'abord etape6_reperes.py`);
console.log(`\n${echecs ? `${echecs} ÉCHEC(S)` : 'Tous les contrôles sont passés.'}`);
process.exit(echecs ? 1 : 0);
