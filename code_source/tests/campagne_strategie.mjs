// =============================================================================
// campagne_strategie.mjs — campagne de simulation de la STRATÉGIE (planification, os fictif)
// -----------------------------------------------------------------------------
// Beaucoup de déformités (les 17 préréglages cliniques avec toutes leurs variantes, puis des déformités tirées au
// hasard), en coin d'ouverture ET de fermeture, et vérification de règles précises pour CHAQUE coin calculé :
//   R1  le guide n'est jamais du côté de la charnière (angle face d'appui / charnière ≥ 90°) ;
//   R2  charnière conservée => guide sur la face du coin, règle 1, sans dérotation, pont ≤ 3 mm ;
//   R3  coin réalisable => face d'appui à ≤ 60° de la face du coin ; sinon abord non usuel, guide sur la face du coin ;
//   R4  le coin recommandé est réalisable dès qu'un des deux l'est ;
//   R5  broches : nombre de la configuration (4, 2 ou 3) ; en 1+2, les 2 distales côte à côte au même niveau ;
//   R6  broches parallèles après la correction ; R7 angle et translation résiduels nuls ;
//   R8  niveau du trait et profondeur de charnière demandés respectés ; R9 angles après correction = os sain.
// Écrit <sortie>/strategie.jsonl et <sortie>/rapport_strategie.md ; avec --exporter, prépare aussi un sous-ensemble de
// cas dans <sortie>/guides/<id>/ pour la construction et le contrôle des guides (tests/campagne_guides.py).
// Usage (depuis code_source/) : node tests/campagne_strategie.mjs <sortie> [nombre aléatoire] [graine] [--exporter]
// =============================================================================
import fs from 'fs';
import zlib from 'zlib';
import path from 'path';
import { fileURLToPath } from 'url';
import * as C from '../cora/app/cora_simple.js';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const EXPORTER = process.argv.includes('--exporter');
const [OUT, NB = '300', GRAINE = '2026'] = args;
if (!OUT) { console.error('usage : node tests/campagne_strategie.mjs <sortie> [nombre aléatoire] [graine] [--exporter]'); process.exit(1); }
fs.mkdirSync(OUT, { recursive: true });

// --- modèle fictif (os, cartilage, voisins)
const meta = JSON.parse(fs.readFileSync(path.join(ICI, '../cora/build/bones_pack.json'), 'utf8'));
const raw = zlib.gunzipSync(fs.readFileSync(path.join(ICI, '../cora/build/bones_pack.bin.gz')));
const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
const bones = {};
for (const [name, info] of Object.entries(meta.bones)) {
  const q = new Uint16Array(buf, info.pos[0], info.pos[1] / 2);
  const pos = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) pos[i] = info.lo[i % 3] + q[i] * info.scale[i % 3];
  const idx = info.index32 ? Uint32Array.from(new Uint32Array(buf, info.idx[0], info.idx[1] / 4)) : Uint32Array.from(new Uint16Array(buf, info.idx[0], info.idx[1] / 2));
  bones[name] = { pos, idx, cart: new Uint8Array(buf.slice(info.cart[0], info.cart[0] + info.cart[1])) };
}
const MODELE = { meta, bones: Object.fromEntries(['femur', 'tibia', 'fibula', 'patella', 'fabellae'].map((n) => [n, bones[n]])) };

// --- les cas
let s_ = +GRAINE >>> 0;
const rng = () => { s_ = (s_ * 1664525 + 1013904223) >>> 0; return s_ / 4294967296; };
const tire = (a, b) => a + rng() * (b - a);
const choisis = (l) => l[Math.floor(rng() * l.length)];
const cas = [];
const VARIANTES = [
  { nom: 'défaut' }, { nom: 'charnière 0,5 mm', charniere: 0.5 }, { nom: 'charnière 6 mm', charniere: 6 },
  { nom: 'trait −15 mm', decalageCoupe: -15 }, { nom: 'trait +15 mm', decalageCoupe: 15 }, { nom: 'chien en croissance', croissance: true },
];
for (const p of C.PRESETS_DEFORMITE) {
  for (const broches of ['2+2', '1+1', '1+2']) {
    for (const v of VARIANTES) {
      cas.push({ serie: 'préréglages', preset: p.id, bone: p.os, frontal: p.frontal, sagittal: p.sagittal, thetaF: p.thetaF, thetaS: p.thetaS,
        niveau: p.niveau, torsion: p.torsion || 0, broches, variante: v.nom,
        opts: { charniere: v.charniere, decalageCoupe: v.decalageCoupe, croissance: v.croissance } });
    }
  }
}
for (let i = 0; i < +NB; i++) {
  const bone = choisis(C.OS), R = C.REGLAGES[bone];
  const sagittal = choisis(C.SAGITTAL);
  let F = Math.round(tire(0, 30)), S = sagittal === 'aucun' ? 0 : Math.round(tire(3, 25));
  if (F < 5 && S < 5) F = 5 + Math.round(tire(0, 20));
  const c = { serie: 'aléatoire', bone, frontal: choisis(C.FRONTAL), sagittal, thetaF: F, thetaS: S || 10,
    torsion: Math.round(tire(-30, 30)), broches: choisis(['2+2', '1+1', '1+2']), variante: 'aléatoire', opts: {} };
  c.niveau = +tire(R.niveaux[0], R.niveaux[1]).toFixed(3);
  c.opts = { charniere: rng() < 0.3 ? +tire(0.5, 8).toFixed(1) : undefined, decalageCoupe: rng() < 0.25 ? Math.round(tire(-20, 20)) : undefined, croissance: rng() < 0.15 };
  cas.push(c);
}

// --- contrôles
const r6 = (x) => (Number.isFinite(x) ? +x.toFixed(6) : x);
function verifierCoin(P, O, kind, c, E) {
  const tag = `${kind}`;
  if (O.angleFaceCharniere < 90 - 1e-6) E.push(`R1 ${tag} : guide du côté de la charnière (${O.angleFaceCharniere.toFixed(1)}°)`);
  if (O.charniereConservee && (O.ecartFace > 1e-6 || O.regle !== 1 || Math.abs(O.derotation) >= C.DEROTATION_MIN || O.h > C.PONT_MAX + 1e-9)) E.push(`R2 ${tag} : charnière conservée incohérente`);
  if (O.faisable && O.ecartFace > C.ANGLE_ENTREE_COIN_MAX + 1e-6) E.push(`R3 ${tag} : face d'appui à ${O.ecartFace.toFixed(0)}° de la face du coin`);
  if (!O.faisable && (!O.abordNonUsuel || C.V.angle(O.face, O.faceCoin) > 1e-3)) E.push(`R3 ${tag} : coin non réalisable mais guide hors de la face du coin`);
  const cfg = C.CONFIG_BROCHES[c.broches];
  const nP = O.brochesReduction.filter((b) => b.fragment === 'proximal').length, nD = O.brochesReduction.filter((b) => b.fragment === 'distal').length;
  if (nP !== cfg.prox || nD !== cfg.dist) E.push(`R5 ${tag} : ${nP}+${nD} broches au lieu de ${cfg.prox}+${cfg.dist}`);
  if (c.broches === '1+2' && nD === 2) {
    const [a, b] = O.brochesReduction.filter((x) => x.fragment === 'distal');
    const ecartAxial = Math.abs(C.V.dot(C.V.sub(a.point, b.point), P.axeDist.d));
    if (ecartAxial > 0.5) E.push(`R5 ${tag} : broches distales pas au même niveau (${ecartAxial.toFixed(2)} mm le long de l'os)`);
  }
  const dirs = O.brochesApres.map((b) => C.V.norm(b.dir));
  const par = Math.max(...dirs.map((x) => C.V.angle(x, dirs[0])));
  if (par > 0.01) E.push(`R6 ${tag} : broches non parallèles après correction (${par.toFixed(4)}°)`);
  if (O.residuel > 0.01) E.push(`R7 ${tag} : angle résiduel ${O.residuel.toFixed(4)}°`);
  if (O.decalage > 0.5) E.push(`R7 ${tag} : translation résiduelle ${O.decalage.toFixed(3)} mm`);
  if (Number.isFinite(c.opts.decalageCoupe) && Math.abs(O.z - c.opts.decalageCoupe) > 1e-6) E.push(`R8 ${tag} : trait à ${O.z} mm au lieu de ${c.opts.decalageCoupe}`);
  if (O.z !== 0 && O.regle !== 2) E.push(`R8 ${tag} : trait hors du CORA sans règle 2`);
  if (Number.isFinite(c.opts.charniere)) {
    const attendu = Math.min(Math.max(c.opts.charniere, 0.3), O.hMax);
    if (Math.abs(O.h - attendu) > 1e-6) E.push(`R8 ${tag} : charnière à ${O.h.toFixed(2)} mm au lieu de ${attendu.toFixed(2)}`);
  }
  const cles = [...C.CLES[P.bone].F, ...C.CLES[P.bone].S];
  const post = Math.max(...cles.map((k) => Math.abs(O.post[k] - P.mesures.normal[k])));
  if (post > 0.1) E.push(`R9 ${tag} : angles après correction à ${post.toFixed(3)}° de l'os sain`);
  return { post, par };
}
const lignes = [];
const t0 = Date.now();
const exportes = [];
cas.forEach((c, i) => {
  const id = `${String(i + 1).padStart(4, '0')}_${c.bone}_${c.preset || c.serie.replace(/[ ,]+/g, '-')}_${c.broches}_${c.variante.replace(/[ ,]+/g, '-')}`;
  const E = [], A = [], M = {};
  let P;
  try {
    P = C.planifier(MODELE, C.casDe(`${c.bone}-${c.frontal}-${c.sagittal}`), { thetaF: c.thetaF, thetaS: c.thetaS, niveau: c.niveau, torsion: c.torsion,
      reference: 'sain', broches: c.broches, ...Object.fromEntries(Object.entries(c.opts).filter(([, x]) => x !== undefined)) });
  } catch (e) {
    lignes.push({ id, cas: c, erreurs: [`exception : ${e.message}`], avertissements: [], mesures: {} });
    return;
  }
  if (!P.osteoPossible) E.push('planification : pas d\'ostéotomie au CORA');
  const kinds = ['fermeture', 'ouverture'].filter((k) => P.osteo[k]);
  for (const k of kinds) {
    const r = verifierCoin(P, P.osteo[k], k, c, E);
    M[`post_${k}`] = r6(r.post);
    M[`face_${k}`] = C.nomDirection(P.osteo[k].face);
    M[`faisable_${k}`] = P.osteo[k].faisable;
    M[`charniere_${k}`] = P.osteo[k].charniereConservee;
    if (!P.osteo[k].placementBroches.ok) A.push(`broches ${k} : placement incomplet`);
  }
  const R = P.recommandation;
  if (R) {
    M.recommande = R.kind; M.decisif = R.decisif;
    const fais = kinds.filter((k) => P.osteo[k].faisable);
    if (fais.length && !P.osteo[R.kind].faisable) E.push(`R4 : coin recommandé (${R.kind}) non réalisable alors que ${fais.join(', ')} l'est`);
    if (fais.length === 1 && R.kind !== fais[0]) E.push(`R4 : seul ${fais[0]} est réalisable mais ${R.kind} est recommandé`);
  }
  for (const k of kinds) for (const x of P.osteo[k].contraintes || []) if (x.niveau === 'bloquant') A.push(`contrainte ${k} : ${x.id}`);
  lignes.push({ id, cas: c, erreurs: E, avertissements: A, mesures: M });
  // sous-ensemble pour la construction des guides
  if (EXPORTER && (c.serie === 'préréglages' && (c.variante === 'défaut' || (c.broches === '2+2' && ['charnière 6 mm', 'trait −15 mm'].includes(c.variante))))) {
    const kinds = [P.recommandation.kind, ...(c.broches === '2+2' && c.variante === 'défaut' ? [P.recommandation.kind === 'fermeture' ? 'ouverture' : 'fermeture'] : [])];
    for (const kind of kinds) {
      if (!P.osteo[kind]) continue;
      const d = path.join(OUT, 'guides', `${id}_${kind}`);
      fs.mkdirSync(d, { recursive: true });
      const ecrireBin = (f, pos, idx) => fs.writeFileSync(f, Buffer.concat([Buffer.from(new Uint32Array([pos.length / 3, idx.length / 3]).buffer), Buffer.from(Float32Array.from(pos).buffer), Buffer.from(Uint32Array.from(idx).buffer)]));
      const pr = C.prescription(P, kind);
      fs.writeFileSync(path.join(d, 'prescription.json'), JSON.stringify(pr));
      ecrireBin(path.join(d, 'os.bin'), P.pos[c.bone], bones[c.bone].idx);
      fs.writeFileSync(path.join(d, `cartilage_${c.bone}.u8`), bones[c.bone].cart);
      const voisins = { ...Object.fromEntries(P.meshes.filter((n) => n !== c.bone).map((n) => [n, P.pos[n]])), ...P.voisins };
      for (const [nom, pos] of Object.entries(voisins)) { ecrireBin(path.join(d, `voisin_${nom}.bin`), pos, bones[nom].idx); fs.writeFileSync(path.join(d, `cartilage_${nom}.u8`), bones[nom].cart); }
      const O = P.osteo[kind], v = P.validation;
      const plan = { id: `${id}_${kind}`, bone: c.bone, frontal: c.frontal, sagittal: c.sagittal, F: c.thetaF, S: c.sagittal === 'aucun' ? 0 : c.thetaS, niveau: c.niveau,
        torsion: c.torsion, kind, serie: c.serie, preset: c.preset, broches: c.broches, variante: c.variante, recommande: P.recommandation.kind,
        osteoPossible: true, theta: r6(P.theta), thetaVrai: r6(v.thetaVrai), ecartTheta: r6(v.ecartTheta),
        section: { largeur: r6(P.section.largeur), cvx: r6(P.section.cvx), ccv: r6(P.section.ccv), profondeur: r6(P.section.profondeur) } };
      if (O) {
        const cles = [...C.CLES[c.bone].F, ...C.CLES[c.bone].S], dirs = O.brochesApres.map((b) => C.V.norm(b.dir));
        plan.osteo = { residuel: r6(O.residuel), decalage: r6(O.decalage), dLongueur: r6(O.dLongueur), base: r6(O.base), D: r6(O.D),
          postMax: r6(Math.max(...cles.map((k) => Math.abs(O.post[k] - P.mesures.normal[k])))), derotation: r6(O.derotation), torsionApres: r6(O.torsionApres),
          torsionCible: r6(O.torsionCible), brochesParalleles: r6(Math.max(...dirs.map((x) => C.V.angle(x, dirs[0])))), angleBroches: r6(O.angleBroches),
          regle: O.regle, decalageCoupe: O.decalageCoupe, translationOsteo: r6(O.translationOsteo), placementBroches: O.placementBroches, alertes: O.alertes,
          largeurCoupe: r6(O.sectionCoupe.largeur), faisable: O.faisable, abordNonUsuel: O.abordNonUsuel };
      }
      fs.writeFileSync(path.join(d, 'planification.json'), JSON.stringify(plan));
      exportes.push(plan.id);
    }
  }
});
const duree = (Date.now() - t0) / 1000;
fs.writeFileSync(path.join(OUT, 'strategie.jsonl'), lignes.map((l) => JSON.stringify(l)).join('\n') + '\n');

// --- rapport
const n = lignes.length, ok = lignes.filter((l) => !l.erreurs.length).length;
const compte = (f) => { const m = new Map(); for (const l of lignes) for (const x of f(l)) m.set(x, (m.get(x) || 0) + 1); return [...m.entries()].sort((a, b) => b[1] - a[1]); };
const regle = (e) => e.split(' : ')[0].split(' ')[0];
const par = (k) => { const m = new Map(); for (const l of lignes) { const v_ = l.mesures[k]; if (v_ !== undefined) m.set(String(v_), (m.get(String(v_)) || 0) + 1); } return [...m.entries()].sort((a, b) => b[1] - a[1]); };
const series = compte((l) => [l.cas.serie]);
const R = [];
R.push(`# Campagne de simulation de la stratégie (planification) — ${new Date().toLocaleString('fr-BE')}`, '');
R.push(`${n} cas (${series.map(([k, v]) => `${v} ${k}`).join(', ')}), en ${duree.toFixed(0)} s : **${ok} sans erreur** (${(100 * ok / n).toFixed(1)} %).`, '');
R.push('Pour chaque cas, les deux coins (fermeture et ouverture) sont planifiés et contrôlés.', '');
R.push('| Règle | Contrôle | Erreurs |', '|---|---|---|');
const TXT = { R1: 'guide jamais du côté de la charnière', R2: 'charnière conservée cohérente', R3: 'face d\'appui à ≤ 60° de la face du coin, sinon abord non usuel signalé',
  R4: 'coin recommandé réalisable', R5: 'nombre et disposition des broches (1+2 : distales au même niveau)', R6: 'broches parallèles après correction',
  R7: 'angle et translation résiduels nuls', R8: 'niveau du trait et profondeur de charnière respectés', R9: 'angles après correction = os sain' };
const errs = compte((l) => l.erreurs.map(regle));
for (const r of Object.keys(TXT)) R.push(`| ${r} | ${TXT[r]} | ${errs.find(([k]) => k === r)?.[1] || 0} |`);
const autres = errs.filter(([k]) => !TXT[k]);
for (const [k, v] of autres) R.push(`| — | ${k} | ${v} |`);
R.push('', '## Le coin recommandé', '');
const reco = compte((l) => (l.mesures.recommande ? [`${l.cas.bone} ${l.cas.frontal}${l.cas.sagittal === 'aucun' ? '' : ' + ' + l.cas.sagittal} → ${l.mesures.recommande} (${l.mesures.decisif})`] : []));
R.push('| Déformité → coin recommandé (critère décisif) | Cas |', '|---|---|', ...reco.map(([k, v]) => `| ${k} | ${v} |`));
R.push('', '## Faces d\'appui du guide', '');
R.push('| Coin | Face d\'appui | Cas |', '|---|---|---|');
for (const k of ['fermeture', 'ouverture']) for (const [f, v] of par(`face_${k}`)) R.push(`| ${k} | ${f} | ${v} |`);
R.push('', `Coin réalisable par un abord usuel : fermeture ${par('faisable_fermeture').map(([a, b]) => `${a === 'true' ? 'oui' : 'non'} ${b}`).join(', ')} ; ouverture ${par('faisable_ouverture').map(([a, b]) => `${a === 'true' ? 'oui' : 'non'} ${b}`).join(', ')}.`);
R.push(`Charnière conservée : fermeture ${par('charniere_fermeture').map(([a, b]) => `${a === 'true' ? 'oui' : 'non'} ${b}`).join(', ')} ; ouverture ${par('charniere_ouverture').map(([a, b]) => `${a === 'true' ? 'oui' : 'non'} ${b}`).join(', ')}.`);
R.push('', '## Avertissements (non bloquants)', '', '| Avertissement | Cas |', '|---|---|');
for (const [k, v] of compte((l) => l.avertissements.map((a) => a.split(' (')[0]))) R.push(`| ${k} | ${v} |`);
R.push('', '## Cas en erreur', '');
for (const l of lignes.filter((x) => x.erreurs.length).slice(0, 60)) R.push(`* \`${l.id}\` : ${l.erreurs.slice(0, 4).join(' ; ')}`);
if (!lignes.some((x) => x.erreurs.length)) R.push('aucun');
if (EXPORTER) R.push('', `${exportes.length} cas exportés pour la construction des guides : ${path.join(OUT, 'guides')}.`);
fs.writeFileSync(path.join(OUT, 'rapport_strategie.md'), R.join('\n') + '\n');
console.log(`${ok}/${n} cas sans erreur en ${duree.toFixed(0)} s ; rapport : ${path.join(OUT, 'rapport_strategie.md')}${EXPORTER ? ` ; ${exportes.length} cas exportés` : ''}`);
for (const [k, v] of errs) console.log(`  ${String(v).padStart(4)}  ${k}`);
