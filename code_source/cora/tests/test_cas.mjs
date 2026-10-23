// =============================================================================
// test_cas.mjs — vérifie la planification CORA 3D sur le modèle synthétique
// -----------------------------------------------------------------------------
// 12 cas (fémur / tibia × varus / valgus × aucun / procurvatum / recurvatum), aux réglages par défaut
// puis sur une grille d'amplitudes F, S et de niveaux d'apex. Pour chaque cas :
//   · θ 3D mesuré = θ imposé ; composantes projetées F et S = valeurs imposées ; types corrects ;
//     formule tan²θ = tan²F + tan²S ; orientation φ ;
//   · axes quasi sécants (δ) ; apex imposé sur le plan bissecteur ; CORA frontal et sagittal au même niveau ;
//   · après correction (fermeture et ouverture) : angles articulaires = valeurs normales dans les deux
//     plans, angle et translation résiduels nuls, raccourcissement / allongement ;
//   · le coin de fermeture contient de l'os, du côté convexe ;
//   · broches de réduction : placées hors du cartilage et des os voisins, angle ≤ θ avant correction, parallèles après ;
//   · prescription pour le guide (format v2.2 = v2.1 + système de réduction) complète et cohérente.
// Torsion : la mesure 3D retrouve τ et ignore la rotation de positionnement ρ ; la largeur projetée
// dépend de τ + ρ seulement.
//
// Usage : node tests/test_cas.mjs        (Node ≥ 22, aucune dépendance)
//         node tests/test_cas.mjs --export <dossier>   écrit aussi prescription.json + STL d'un cas
// =============================================================================
import fs from 'fs';
import zlib from 'zlib';
import path from 'path';
import { fileURLToPath } from 'url';
import * as C from '../app/cora_simple.js';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const meta = JSON.parse(fs.readFileSync(path.join(ROOT, 'build/bones_pack.json'), 'utf8'));
const raw = zlib.gunzipSync(fs.readFileSync(path.join(ROOT, 'build/bones_pack.bin.gz')));
const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
const bones = {};
// même modèle que l'application : fémur, tibia, fibula, rotule, fabelles, avec la carte du cartilage
for (const name of ['femur', 'tibia', 'fibula', 'patella', 'fabellae']) {
  const info = meta.bones[name];
  const q = new Uint16Array(buf, info.pos[0], info.pos[1] / 2);
  const pos = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) pos[i] = info.lo[i % 3] + q[i] * info.scale[i % 3];
  const idx = info.index32 ? Uint32Array.from(new Uint32Array(buf, info.idx[0], info.idx[1] / 4)) : Uint32Array.from(new Uint16Array(buf, info.idx[0], info.idx[1] / 2));
  bones[name] = { pos, idx, cart: new Uint8Array(buf.slice(info.cart[0], info.cart[0] + info.cart[1])) };
}
const model = { meta, bones };

const f = (x, d = 2) => (Number.isFinite(x) ? x.toFixed(d) : String(x));
let echecs = 0;
const verifie = (cond, msg) => { if (!cond) { echecs++; console.log('   ÉCHEC : ' + msg); } };
const pire = {};                                        // plus grands écarts rencontrés (résumé final)
const note = (k, x) => { pire[k] = Math.max(pire[k] ?? 0, Math.abs(x)); };

// ------------------------------------------------------------ valeurs normales du modèle
for (const bone of C.OS) {
  const n = C.reference(model, bone).normal, lit = C.LITTERATURE[bone];
  console.log(`Os sain (${bone}) : ` + Object.keys(lit).map((k) => `${k} ${f(n[k], 1)}° (litt. ${lit[k].m} ± ${lit[k].sd})`).join(' · '));
}

function controle(cas, opts, bavard) {
  const P = C.planifier(model, cas, opts);
  const v = P.validation, n = P.mesures.normal;
  const tag = `${cas.id} F=${P.thetaF}° S=${P.thetaS}° niveau=${P.niveau}`;
  const cles = [...C.CLES[cas.bone].F, ...C.CLES[cas.bone].S];
  if (bavard) {
    console.log(`\n${tag}`);
    console.log(`   θ ${f(v.thetaMesure, 3)}° (imposé ${f(v.thetaVrai, 3)}°, formule 2D ${f(v.theta2D, 3)}°) · F ${f(v.FMesure)}° ${v.typeF} · S ${f(v.SMesure)}° ${v.typeS} · φ ${f(v.phi, 1)}° (imposé ${f(v.phiVrai, 1)}°) · ψ ${f(P.psi, 1)}°`);
    console.log(`   CORA : niveau ${f(v.niveauCORA, 1)} mm (apex ${f(v.niveauApex, 1)} mm ; frontal ${f(v.niveauF, 1)}, sagittal ${v.typeS === 'aucun' ? '—' : f(v.niveauS, 1)}), δ ${f(v.delta, 3)} mm, apex → plan bissecteur ${f(v.apexBissectrice, 3)} mm`);
  }
  // déformité retrouvée
  verifie(Math.abs(v.ecartTheta) < 0.05, `${tag} : écart θ ${f(v.ecartTheta, 3)}°`); note('θ (°)', v.ecartTheta);
  // θ : angle entre les axes construits = angle entre l'axe sain et l'axe sain tourné (exact)
  verifie(Math.abs(v.thetaMesure - v.thetaAxesVrai) < 1e-3, `${tag} : θ ${f(v.thetaMesure, 4)}° ≠ ${f(v.thetaAxesVrai, 4)}°`); note('θ − θ axes (°)', v.thetaMesure - v.thetaAxesVrai);
  // F et S mesurés = vraies valeurs projetées (exact) ; écart aux valeurs nominales (effet de projection) noté
  verifie(Math.abs(P.Fm - v.FProjVrai) < 1e-3 && Math.abs(P.Sm - v.SProjVrai) < 1e-3, `${tag} : F ${f(P.Fm, 4)} / ${f(v.FProjVrai, 4)}, S ${f(P.Sm, 4)} / ${f(v.SProjVrai, 4)}`);
  note('F − F projeté vrai (°)', P.Fm - v.FProjVrai); note('S − S projeté vrai (°)', P.Sm - v.SProjVrai);
  note('F − F nominal (°) [projection]', v.FMesure - P.thetaF); note('S − S nominal (°) [projection]', v.SMesure - P.thetaS);
  verifie(Math.abs(v.FMesure - P.thetaF) < 0.5 && Math.abs(v.SMesure - P.thetaS) < 0.5, `${tag} : F ${f(v.FMesure, 3)}°, S ${f(v.SMesure, 3)}° loin des valeurs imposées`);
  verifie(v.typeF === cas.frontal && v.typeS === cas.sagittal, `${tag} : types ${v.typeF} / ${v.typeS}`);
  verifie(Math.abs(v.theta2D - v.thetaMesure) < 0.5, `${tag} : formule 2D ${f(v.theta2D, 3)}° ≠ θ 3D`); note('formule 2D − θ 3D (°) [projection]', v.theta2D - v.thetaMesure);
  verifie(Math.abs(v.phi - v.phiVrai) < 1, `${tag} : φ ${f(v.phi, 2)}° au lieu de ${f(v.phiVrai, 2)}°`); note('φ (°) [projection]', v.phi - v.phiVrai);
  verifie(v.delta < 0.1, `${tag} : axes gauches, δ = ${f(v.delta, 3)} mm`); note('δ (mm)', v.delta);
  verifie(v.apexBissectrice < 0.2, `${tag} : apex à ${f(v.apexBissectrice, 3)} mm du plan bissecteur`); note('apex → bissecteur (mm)', v.apexBissectrice);
  if (cas.sagittal !== 'aucun') { verifie(Math.abs(v.niveauF - v.niveauS) < 1, `${tag} : CORA frontal ${f(v.niveauF, 1)} / sagittal ${f(v.niveauS, 1)}`); note('niveaux F / S (mm)', v.niveauF - v.niveauS); }
  // ostéotomies
  for (const kind of ['fermeture', 'ouverture']) {
    const O = P.osteo[kind];
    const ecarts = cles.map((k) => Math.abs(O.post[k] - n[k]));
    if (bavard) console.log(`   ${kind.padEnd(10)} : charnière d = ${f(O.d, 1)} mm, ${kind === 'fermeture' ? 'base' : 'ouverture'} ${f(O.base)} mm, broches ${f(O.angleBroches, 3)}°, ` +
      `après correction ${cles.map((k) => `${k} ${f(O.post[k])}°`).join(' · ')}, résiduel ${f(O.residuel, 4)}°, translation ${f(O.decalage, 3)} mm, Δ longueur ${f(O.dLongueur)} mm`);
    verifie(Math.max(...ecarts) < 0.05, `${tag} ${kind} : angles post-op ≠ normaux (${ecarts.map((e) => f(e, 3)).join(', ')})`); note('angles post-op (°)', Math.max(...ecarts));
    verifie(O.residuel < 0.01 && O.decalage < 0.1, `${tag} ${kind} : résiduel ${f(O.residuel, 3)}°, translation ${f(O.decalage, 3)} mm`); note('translation résiduelle (mm)', O.decalage);
    // faces de l'ostéotomie en contact après la correction angulaire : faces confondues (fermeture), arête de charnière
    // sur la face proximale (ouverture) ; règle 2 : le fragment glisse le long de la coupe (translation planifiée)
    const glisse = C.V.sub(C.RT.apply(O.Tang, O.charniere), O.charniere);
    const contact = Math.abs(C.V.dot(glisse, kind === 'fermeture' ? P.axeProx.d : P.bis.b));
    verifie(contact < 1e-6, `${tag} ${kind} : faces de l'ostéotomie écartées de ${f(contact, 6)} mm après correction`); note('faces : écart après correction (mm)', contact);
    // règle 1 : la fermeture raccourcit, l'ouverture allonge (règle 2 : la translation peut inverser un faible écart)
    if (O.regle === 1) verifie(kind === 'fermeture' ? O.dLongueur < 0 : O.dLongueur > 0, `${tag} ${kind} : Δ longueur ${f(O.dLongueur)} mm de signe inattendu`);
    else verifie(Math.abs(C.V.dot(glisse, P.axeProx.d)) < 1e-6 || kind === 'ouverture', `${tag} ${kind} : règle 2, translation hors du plan de coupe`);
    // broches : θ entre elles, parallèles après correction
    const dDistCorr = C.M3.mv(O.T.R, O.broches[1].dir);
    // (tolérance 1e-4° : acos n'est précis qu'à ≈ 1e-6° près de 0)
    // broches tournées autour de l'os pour éviter la fibula ou le cartilage : l'angle entre les paires vaut alors au plus θ ;
    // l'invariant clinique est le parallélisme après correction
    verifie(O.angleBroches <= P.theta + 1e-4 && C.V.angle(O.broches[0].dir, dDistCorr) < 1e-4 && O.placementBroches.ok, `${tag} ${kind} : broches ${f(O.angleBroches, 4)}° (placement ${O.placementBroches.ok ? 'ok' : 'impossible'})`);
    if (kind === 'fermeture') verifie(Math.abs(O.angleCoupes - P.theta) < 1e-4, `${tag} : angle entre les traits ${f(O.angleCoupes, 4)}° ≠ θ`);
    // prescription
    const pr = C.prescription(P, kind);
    verifie(pr.schema_version === 'v2.2' && pr.plans_coupe.length === (kind === 'fermeture' ? 2 : 1) && pr.broches.length === 2
      && Math.abs(pr.coin.angle_deg - P.theta) < 1e-3 && pr.guide && pr.guide.centre_section.length === 3, `${tag} ${kind} : prescription incomplète`);
  }
  // le coin de fermeture : sommets entre les deux plans, du côté convexe de la charnière
  const Of = P.osteo.fermeture, [p1, p2] = Of.plans, pos = P.pos[cas.bone];
  let nIn = 0, sCvx = 0;
  for (let i = 0; i < pos.length; i += 3) {
    const x = [pos[i], pos[i + 1], pos[i + 2]];
    if (C.V.dot(C.V.sub(x, p1.p), p1.n) > 0 && C.V.dot(C.V.sub(x, p2.p), p2.n) < 0) { nIn++; sCvx += C.V.dot(C.V.sub(x, Of.charniere), P.bis.c); }
  }
  verifie(nIn > 20 && sCvx > 0, `${tag} : coin de fermeture vide ou du mauvais côté (${nIn} sommets)`);
  return P;
}

for (const cas of C.CAS) controle(cas, {}, true);

// grille : amplitudes F × S × niveaux
let nGrille = 0;
for (const cas of C.CAS) {
  const R = C.REGLAGES[cas.bone];
  for (const thetaF of [5, 15, 30]) for (const thetaS of cas.sagittal === 'aucun' ? [0] : [3, 12, 25]) for (let k = 0; k <= 2; k++) {
    controle(cas, { thetaF, thetaS, niveau: +(R.niveaux[0] + (R.niveaux[1] - R.niveaux[0]) * k / 2).toFixed(3) }, false);
    nGrille++;
  }
}
console.log(`\nGrille : ${nGrille} variantes supplémentaires contrôlées.`);

// ------------------------------------------------------------ torsion
console.log('\nTorsion (os sain tordu de τ, posé de travers de ρ) :');
for (const bone of C.OS) {
  const T0 = C.planTorsion(model, bone, 0, 0);
  for (const [tau, rho] of [[20, 0], [0, 20], [20, -20], [-15, 10], [35, 0]]) {
    const T = C.planTorsion(model, bone, tau, rho);
    const ref = C.planTorsion(model, bone, tau + rho, 0);          // même rotation de l'extrémité distale
    console.log(`   ${bone} τ ${String(tau).padStart(3)}° ρ ${String(rho).padStart(3)}° : torsion 3D ${f(T.m.torsion3D, 1)}° (Δ ${f(T.dTorsion, 2)}°), largeur projetée ${f(T.m.radio.epicondyles)} mm (sain ${f(T0.m.radio.epicondyles)} mm)`);
    // fémur : une torsion externe diminue l'antéversion ; tibia : externe = positif (Méthodes de Longo 2022)
    const sg = bone === 'femur' ? -1 : 1;
    verifie(Math.abs(sg * T.dTorsion - tau) < 0.5, `${bone} τ=${tau} ρ=${rho} : torsion 3D Δ ${f(T.dTorsion, 2)}°`); note('torsion 3D (°)', sg * T.dTorsion - tau);
    verifie(Math.abs(T.m.radio.epicondyles - ref.m.radio.epicondyles) < 1e-6, `${bone} τ=${tau} ρ=${rho} : la largeur projetée ne dépend pas que de τ + ρ`);
  }
  const W = Math.max(...T0.courbe.map((p) => p.largeur));
  console.log(`   ${bone} : largeur max ${f(W)} mm ; rotation pour perdre 0,5 mm : ${f(Math.acos(1 - 0.5 / W) * C.DEG, 1)}° ; pour perdre 5 % : ${f(Math.acos(0.95) * C.DEG, 1)}°`);
}

console.log('\nPlus grands écarts : ' + Object.entries(pire).map(([k, x]) => `${k} ${f(x, 4)}`).join(' · '));

// ------------------------------------------------------------ export (facultatif)
const iExp = process.argv.indexOf('--export');
if (iExp > 0) {
  const dir = process.argv[iExp + 1];
  fs.mkdirSync(dir, { recursive: true });
  const cas = C.casDe(process.argv[iExp + 2] || 'tibia-varus-procurvatum'), kind = process.argv[iExp + 3] || 'fermeture';
  const P = C.planifier(model, cas, {});
  fs.writeFileSync(path.join(dir, 'prescription.json'), JSON.stringify(C.prescription(P, kind), null, 2));
  fs.writeFileSync(path.join(dir, `${cas.bone}_deforme.stl`), C.stlBinary([{ pos: P.pos[cas.bone], idx: bones[cas.bone].idx }], `${cas.bone} deforme`));
  console.log(`\nExport : ${cas.id}, ${kind} -> ${dir}`);
}

console.log(echecs ? `\n${echecs} échec(s).` : '\nTous les contrôles sont passés.');
process.exit(echecs ? 1 : 0);
