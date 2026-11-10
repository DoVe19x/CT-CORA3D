import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
/*__CORE__*/
// =============================================================================
// 10 — base : utilitaires DOM, formatage, décodage du modèle osseux
// =============================================================================
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const isNum = (x) => typeof x === 'number' && isFinite(x);
// nombre à la française : virgule décimale, vrai signe moins
const fr = (x, d = 1) => (isNum(x) ? (Math.abs(x) < 0.5 * 10 ** -d ? 0 : x).toFixed(d).replace('-', '−').replace('.', ',') : 'n.d.');
const deg = (x, d = 1) => `${fr(x, d)}°`;
const degS = (x, d = 1) => `${isNum(x) && x >= 0.5 * 10 ** -d ? '+' : ''}${fr(x, d)}°`;     // écart signé : +15,0° / −6,0°
const mm = (x, d = 1) => `${fr(x, d)} mm`;
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const cssColor = (n) => new THREE.Color(cssVar(n) || '#ffffff');
const isLight = () => matchMedia('(prefers-color-scheme: light)').matches ? document.documentElement.dataset.theme !== 'dark' : document.documentElement.dataset.theme === 'light';

// ------------------------------------------------------------ modèle osseux --
// bones_pack : positions quantifiées sur 16 bits, indices, et trois attributs par sommet
// (occlusion ambiante, cartilage, médullaire) compressés en gzip puis encodés en base64.
async function loadBones(progress) {
  const meta = JSON.parse($('#bones-meta').textContent);
  progress(0.2, 'Décodage des maillages…');
  const b64 = $('#bones-data').textContent.trim();
  const raw = atob(b64);
  const bin = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bin[i] = raw.charCodeAt(i);
  progress(0.4, 'Décompression…');
  const stream = new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'));
  const buf = await new Response(stream).arrayBuffer();
  progress(0.6, 'Reconstruction des os…');
  const bones = {};
  for (const [name, info] of Object.entries(meta.bones)) {
    const q = new Uint16Array(buf, info.pos[0], info.pos[1] / 2);
    const pos = new Float32Array(q.length);
    for (let i = 0; i < q.length; i++) pos[i] = info.lo[i % 3] + q[i] * info.scale[i % 3];
    const idx = info.index32 ? Uint32Array.from(new Uint32Array(buf, info.idx[0], info.idx[1] / 4))
      : Uint32Array.from(new Uint16Array(buf, info.idx[0], info.idx[1] / 2));
    const u8 = (o) => Float32Array.from(new Uint8Array(buf, o[0], o[1]), (x) => x / 255);
    bones[name] = { pos, idx, ao: u8(info.ao), cart: u8(info.cart), med: u8(info.med) };
  }
  return { meta, bones };
}

// ------------------------------------------------------------ os segmenté (serveur local) --
// Le serveur de CT-CORA3D (application/serveur.py) fournit les os segmentés : liste, repères automatiques
// (cora_<os>.json, étape 6) et maillages dans le repère de l'os (cora_<os>.bin : nb sommets, nb triangles,
// sommets float32, triangles uint32). Hors serveur (fichier ouvert seul), seule la partie « os fictif » fonctionne.
async function lireJSON(url) {
  const r = await fetch(url);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.erreur || r.statusText);
  return j;
}
async function lireMaillage(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).erreur || r.statusText);
  const ab = await r.arrayBuffer();
  const [nv, nf] = new Uint32Array(ab, 0, 2);
  return { pos: new Float32Array(ab.slice(8, 8 + nv * 12)), idx: new Uint32Array(ab.slice(8 + nv * 12, 8 + nv * 12 + nf * 12)) };
}
async function chargerReel(serie, nom, progress) {
  const q = (o) => Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  progress?.(0.15, 'Repères anatomiques…');
  const json = await lireJSON(`/api/cora/os?${q({ serie, os: nom })}`);
  if (!json.complet) throw new Error(json.raison || 'os non analysable');
  const bones = {};
  let i = 0;
  for (const [n, f] of Object.entries(json.maillages)) {
    progress?.(0.3 + 0.5 * (i++ / Object.keys(json.maillages).length), `Maillage ${n}…`);
    const m = await lireMaillage(`/api/cora/maillage?${q({ serie, quoi: f.replace(/^cora_/, '').replace(/\.bin$/, '') })}`);
    // attributs de rendu du modèle synthétique : pas d'occlusion pré-calculée, pas de cartilage ni de canal visibles
    const nv = m.pos.length / 3;
    bones[n] = { ...m, ao: new Float32Array(nv).fill(1), cart: new Float32Array(nv), med: new Float32Array(nv) };
  }
  return { json, bones };
}

// ------------------------------------------------------------ références --
// Métadonnées vérifiées sur PubMed (eutils) les 12 et 13/10/2026.
const doi = (d) => `https://doi.org/${d}`;
const REFS = {
  paley: { t: 'Paley D. Principles of Deformity Correction. Springer, 2002 (CORA, bissectrice, ACA, plan oblique, règles d\'ostéotomie 1 à 3, coins d\'ouverture / fermeture / neutre).', url: doi('10.1007/978-3-642-59373-4') },
  dismukes: { t: 'Dismukes DI, Tomlinson JL, Fox DB, Cook JL, Song KJ. Radiographic measurement of the proximal and distal mechanical joint angles in the canine tibia. Vet Surg 2007;36:699-704.', url: doi('10.1111/j.1532-950X.2007.00323.x') },
  dismukes08: { t: 'Dismukes DI, Fox DB, Tomlinson JL, Essman SC. Radiographic measurement of canine tibial angles in the sagittal plane. Vet Surg 2008;37:300-305.', url: doi('10.1111/j.1532-950X.2008.00381.x') },
  tomlinson: { t: 'Tomlinson J, Fox D, Cook JL, Keller GG. Measurement of femoral angles in four dog breeds. Vet Surg 2007;36:593-598.', url: doi('10.1111/j.1532-950X.2007.00309.x') },
  kara: { t: 'Kara ME, Sevil-Kilimci F, Dilek ÖG, Onar V. Proximal and distal alignment of normal canine femurs: a morphometric analysis. Ann Anat 2018;217:125-128 (CDFA, angle de procurvatum distal, 3D-CT).', url: doi('10.1016/j.aanat.2018.02.006') },
  newman: { t: 'Newman M, Voss K. Computed tomographic evaluation of femoral and tibial conformation in English Staffordshire Bull Terriers. Vet Comp Orthop Traumatol 2017;30(3):191-199.', url: null },
  shihtzu: { t: 'Kim SY, Snowdon KA, DeCamp CE. Single oblique osteotomy for correction of antebrachial angular and torsional deformities in a dog. J Am Vet Med Assoc 2017;251(3):333-339 (23° valgus + 23° procurvatum = 32° dans un plan oblique à 45°).', url: doi('10.2460/javma.251.3.333') },
  qatu: { t: 'Qatu M, Al-Jamal M, Mouzaihem H. Rigorous mathematical derivation of inclination angle for single cut rotational osteotomy for tibia deformity correction. Orthop Rev 2024;16:120302 (passage des vues face / profil au plan oblique).', url: doi('10.52965/001c.120302') },
  guenego21: { t: 'Guénégo L, Vezzoni A, Vezzoni L. Comparison of tibial anatomical-mechanical axis angles and patellar positions between TPLO and AMA-based CCWO… and clinically normal Labrador retrievers. BMC Vet Res 2021;17:368 (témoins sains : TPA 26,3°, AMA 0,99° ; angle du coin = 0,65 × TPA).', url: doi('10.1186/s12917-021-03094-3') },
  guenego25: { t: 'Guénégo L, Vezzoni A, Vezzoni L. Modified cranial closing wedge osteotomy (AMA-based CCWO) … in 204 dogs over 50 kg. Vet Comp Orthop Traumatol 2025;38(3):111-118.', url: doi('10.1055/s-0044-1790511') },
  vezzoni20: { t: 'Vezzoni L, Bazzo S, Boiocchi S, Vezzoni A. Modified TPLO with double cut and medial crescentic closing wedge osteotomy to treat dogs with CCL rupture and tibial valgus deformity. Vet Comp Orthop Traumatol 2020;33(1):59-65.', url: doi('10.1055/s-0039-1700565') },
  petazzoni: { t: 'Petazzoni M, Nicetto T, Vezzoni A, Piras A, Palmer R. Treatment of pes varus using locking plate fixation in seven Dachshund dogs. Vet Comp Orthop Traumatol 2012;25(3):231-238 (coin d\'ouverture médial au CORA ; préserver la corticale latérale).', url: doi('10.3415/VCOT-11-03-0035') },
  brower: { t: 'Brower BE, Kowaleski MP, Peruski AM, et al. Distal femoral lateral closing wedge osteotomy … medial patellar luxation and distal femoral varus in dogs. Vet Comp Orthop Traumatol 2017;30(1):20-27 (aLDFA 107,6° -> 94,1°).', url: doi('10.3415/VCOT-16-07-0103') },
  noyes: { t: 'Noyes FR, Goebel SX, West J. Opening wedge tibial osteotomy: the 3-triangle method to correct axial alignment and tibial slope. Am J Sports Med 2005;33(3):378-387 (1 mm d\'erreur d\'ouverture crâniale ≈ 2° de pente).', url: doi('10.1177/0363546504269034') },
  ducat: { t: 'Ducat A, Sariali E, Lebel B, et al. Posterior tibial slope changes after opening- and closing-wedge high tibial osteotomy. Orthop Traumatol Surg Res 2012;98(1):68-74.', url: doi('10.1016/j.otsr.2011.08.013') },
  dudley: { t: 'Dudley RM, Kowaleski MP, Drost WT, Dyce J. Radiographic and computed tomographic determination of femoral varus and torsion in the dog. Vet Radiol Ultrasound 2006;47(6):546-552.', url: doi('10.1111/j.1740-8261.2006.00184.x') },
  apelt: { t: 'Apelt D, Kowaleski MP, Dyce J. Comparison of computed tomographic and standard radiographic determination of tibial torsion in the dog. Vet Surg 2005;34(5):457-462 (la radiographie ne distingue pas torsion et rotation de positionnement).', url: doi('10.1111/j.1551-2916.2005.00069.x') },
  aper: { t: 'Aper R, Kowaleski MP, Apelt D, Drost WT, Dyce J. Computed tomographic determination of tibial torsion in the dog. Vet Radiol Ultrasound 2005;46(3):187-191.', url: doi('10.1111/j.1740-8261.2005.00048.x') },
  mostafa: { t: 'Mostafa AA, Griffon DJ, Thomas MW, Constable PD. Radiographic evaluation of femoral torsion and correlation with computed tomographic techniques in Labrador Retrievers… Vet Surg 2014;43(5):534-541.', url: doi('10.1111/j.1532-950X.2014.12096.x') },
  miles: { t: 'Miles JE. Femoral rotation unpredictably affects radiographic anatomical lateral distal femoral angle measurements. Vet Comp Orthop Traumatol 2016;29(2):156-159.', url: doi('10.3415/VCOT-15-06-0107') },
  longo: { t: 'Longo F, Nicetto T, Knell SC, Evans RB, Isola M, Pozzi A. Three-dimensional volume rendering planning … femoral and tibial detorsional osteotomies in dogs. Vet Surg 2022;51(7):1126-1141 (FTA < 20° : torsion fémorale externe ; TTA < −10° : torsion tibiale externe).', url: doi('10.1111/vsu.13882') },
  bruhF: { t: 'Brühschwein A, Schmitz B, Zöllner M, Reese S, Meyer-Lindenberg A. CT angular measurements using a bone-centered 3D coordinate system are accurate in a femoral torsional deformity model… Front Vet Sci 2023;10:1019216.', url: doi('10.3389/fvets.2023.1019216') },
  krettek: { t: 'Krettek C, Miclau T, Grün O, Schandelmaier P, Tscherne H. Intraoperative control of axes, rotation and length in femoral and tibial fractures. Injury 1998;29 Suppl 3:C29-39 (signe de la différence de diamètre, signe de la marche corticale).', url: doi('10.1016/s0020-1383(98)95006-9') },
  fang: { t: 'Fang C, Gibson W, Lau TW, et al. Important tips and numbers on using the cortical step and diameter difference sign in assessing femoral rotation: should we abandon the technique? Injury 2015;46(7):1393-1399.', url: doi('10.1016/j.injury.2015.04.009') },
  tornetta: { t: 'Tornetta P 3rd, Ritz G, Kantor A. Femoral torsion after interlocked nailing of unstable femoral fractures. J Trauma 1995;38(2):213-219 (antéversion mesurée à l\'amplificateur de brillance).', url: doi('10.1097/00005373-199502000-00011') },
  ivanov: { t: 'Ivanov DV, Welby JP, Khanna A, et al. Evaluation of intraoperative fluoroscopic techniques to estimate femoral rotation: a cadaveric study. J Orthop Trauma 2024;38(5):279-284 (erreur moyenne 4 à 9°).', url: doi('10.1097/BOT.0000000000002790') },
  folinais: { t: 'Folinais D, Thelen P, Delin C, et al. Measuring femoral and rotational alignment: EOS system versus computed tomography. Orthop Traumatol Surg Res 2013;99(5):509-516 (deux radiographies + modèle 3D ≈ CT).', url: doi('10.1016/j.otsr.2012.12.023') },
  // normalité : bornes citées par l'équipe Vezzoni, valeurs 3D-CT (vérifiées sur PubMed le 13/10/2026)
  vezzoni22: { t: 'Vezzoni L, Forzisi I, Ferretti A, Vezzoni A. Hemiepiphysiodesis for the correction of distal femoral valgus in growing dogs. Vet Comp Orthop Traumatol 2022;35(2):112-118 (borne de normalité aLDFA « 94 ± 3,3° »).', url: doi('10.1055/s-0041-1736381') },
  olsen16: { t: 'Olsen AM, Vezzoni L, Ferretti A, Palmer RH, Vezzoni A, Duerr F. Hemiepiphysiodesis for the correction of proximal tibial valgus in growing dogs. Vet Comp Orthop Traumatol 2016;29(4):330-337 (borne de normalité mMPTA « 93,3 ± 1,78° »).', url: doi('10.3415/VCOT-15-12-0204') },
  dismukes08b: { t: 'Dismukes DI, Fox DB, Tomlinson JL, Cook JL, Essman SC. Determination of pelvic limb alignment in the large-breed dog: a cadaveric radiographic study in the frontal plane. Vet Surg 2008;37(7):674-682 (mMPTA 92,2 ± 1,8°, mMDTA 95,9 ± 2,2°).', url: doi('10.1111/j.1532-950X.2008.00434.x') },
  wilke02: { t: 'Wilke VL, Conzemius MG, Besancon MF, Evans RB, Ritter M. Comparison of tibial plateau angle between clinically normal Greyhounds and Labrador Retrievers with and without rupture of the cranial cruciate ligament. J Am Vet Med Assoc 2002;221(10):1426-1429 (lévriers : TPA 22,5°).', url: doi('10.2460/javma.2002.221.1426') },
  guenego17: { t: 'Guénégo L, Payot M, Charru P, Verwaerde P. Comparison of tibial anatomical-mechanical axis angle between predisposed dogs and dogs at low risk for cranial cruciate ligament rupture. Vet J 2017;225:35-41 (AMA > 1,87° : rupture du LCCr).', url: doi('10.1016/j.tvjl.2017.04.011') },
  alaiyan: { t: 'Al Aiyan A, Richardson K, Manchi G, Ginja M, Brunnberg L. Measurement of the femoral anteversion angle in medium and large dog breeds using computed tomography. Front Vet Sci 2021;8:540406 (antéversion 31,3 ± 5,5° et 31,0 ± 5,0°).', url: doi('10.3389/fvets.2021.540406') },
  bruhT: { t: 'Brühschwein A, Schmitz B, Zöllner M, Reese S, Meyer-Lindenberg A. Three-dimensional computed tomographic angular measurements of the canine tibia using a bone-centered coordinate system. Front Vet Sci 2023;10:1154144.', url: doi('10.3389/fvets.2023.1154144') },
  bruhRaces: { t: 'Brühschwein A, Burg-Personnaz J, Zöllner M, Reese S, Meyer-Lindenberg A. Comparison of CT-measured angles of pelvic limbs without patellar luxation of six canine breeds. Front Vet Sci 2023;10:1194167 (valeurs propres à chaque race).', url: doi('10.3389/fvets.2023.1194167') },
  // ostéotomie en dôme (vérifié le 16/10/2026)
  fox06: { t: 'Fox DB, Tomlinson JL, Cook JL, Breshears LM. Principles of uniapical and biapical radial deformity correction using dome osteotomies and the center of rotation of angulation methodology in dogs. Vet Surg 2006;35(1):67-77.', url: doi('10.1111/j.1532-950X.2005.00114.x') },
  // radius (patte avant, 09-10/11/2026)
  kwon22: { t: 'Kwon et al. Front Vet Sci 2022;8:774993 : angles articulaires du radius (MPRA, LDRA, CrPRA, CdDRA, méthode de Fox 2006) de chiens sains de six races (Welsh Corgi, Teckel, Pékinois, Bichon maltais, Caniche, Beagle) ; au-delà de 15° de torsion, erreurs de plus de 5° de face.', url: doi('10.3389/fvets.2021.774993') },
  duncan22: { t: 'Duncan et al. 2022 : courbure normale du radius de petits chiens non chondrodystrophiques, radiographies orthogonales (procurvatum 16,8 ± 4,1°, angle frontal 4,8 ± 2,5°) ; résumé PubMed 36054008.', url: 'https://pubmed.ncbi.nlm.nih.gov/36054008/' },
  knapp16: { t: 'Knapp JL, Tomlinson JL, Fox DB. Vet Surg 2016 : classification des déformations angulaires du radius et de l\'ulna par la méthode du CORA (plages normales : 0 à 8° de face, 8 à 35° de profil).', url: null },
  kroner17: { t: 'Kroner K et al. Vet Surg 2017 : torsion du radius mesurée au scanner chez des chiens avec et sans déformation de l\'avant-bras (chiens sains moyens à grands : 3,6 ± 6,4°).', url: null },
  // guides de coupe et de réduction (vérifiés sur PubMed le 13/10/2026)
  worth19: { t: 'Worth AJ, Crosse KR, Kersley A. Computer-assisted surgery using 3D printed saw guides for acute correction of antebrachial angular limb deformities in dogs. Vet Comp Orthop Traumatol 2019;32(3):241-249 (guides de coupe seuls : 1 membre sur 7 réopéré pour une rotation mal corrigée).', url: doi('10.1055/s-0039-1678701') },
  hall19: { t: 'Hall EL, Baines S, Bilmont A, Oxley B. Accuracy of patient-specific three-dimensional-printed osteotomy and reduction guides for distal femoral osteotomy in dogs with medial patella luxation. Vet Surg 2019;48(4):584-591 (torsion à 1,67 ± 2,08° de la cible in vivo).', url: doi('10.1111/vsu.13126') },
  carwardine21: { t: 'Carwardine DR, Gosling MJ, Burton NJ, O\'Malley FL, Parsons KJ. Three-dimensional-printed patient-specific osteotomy guides, repositioning guides and titanium plates for acute correction of antebrachial limb deformities in dogs. Vet Comp Orthop Traumatol 2021;34(1):43-52.', url: doi('10.1055/s-0040-1709702') },
  dearmond22: { t: 'De Armond CC, Lewis DD, Kim SE, Biedrzycki AH. Accuracy of virtual surgical planning and custom three-dimensionally printed osteotomy and reduction guides for acute uni- and biapical correction of antebrachial deformities in dogs. J Am Vet Med Assoc 2022;260(13):1-9 (> 90 % des paramètres à ≤ 5° et ≤ 5 mm).', url: doi('10.2460/javma.21.09.0419') },
  jeon23: { t: 'Jeon JW, Kang KW, Kim WK, Jung C, Kang BJ. Three-dimensional-printed patient-specific guides for tibial deformity correction in small-breed dogs. Am J Vet Res 2023;84(12) (erreurs 1,8 ± 1,4° sagittal, 2,3 ± 2,1° frontal, 2,6 ± 1,3° transverse).', url: doi('10.2460/ajvr.23.06.0146') },
  bright24: { t: 'Bright S, Schofield I, Oxley B. Surgical correction of pes varus deformity in dachshunds using three-dimensional-printed patient-specific guide system: nine tibiae in seven cases (2018-2022). J Small Anim Pract 2024;65(12):894-905 (erreur < 2° et < 1 mm dans tous les plans).', url: doi('10.1111/jsap.13789') },
  imaiosValgus: { t: 'IMAIOS vet-Anatomy : Valgus tibial.', url: 'https://www.imaios.com/fr/vet-anatomy/structures-anatomiques/valgus-tibial-11111648004' },
  imaiosMeca: { t: 'IMAIOS vet-Anatomy : Axe mécanique du tibia.', url: 'https://www.imaios.com/fr/vet-anatomy/structures-anatomiques/axe-mecanique-du-tibia-11111648144' },
  imaiosMPTA: { t: 'IMAIOS vet-Anatomy : Angle mécanique médial proximal du tibia.', url: 'https://www.imaios.com/fr/vet-anatomy/structures-anatomiques/angle-mecanique-medial-proximal-du-tibia-11111647884' },
  imaiosMDTA: { t: 'IMAIOS vet-Anatomy : Angle mécanique médial distal du tibia.', url: 'https://www.imaios.com/fr/vet-anatomy/structures-anatomiques/angle-mecanique-medial-distal-du-tibia-11111647916' },
  imaiosVarusF: { t: 'IMAIOS vet-Anatomy : Angle de varus fémoral.', url: 'https://www.imaios.com/fr/vet-anatomy/structures-anatomiques/angle-de-varus-femoral-11111648016' },
  imaiosMecaF: { t: 'IMAIOS vet-Anatomy : Axe mécanique du fémur.', url: 'https://www.imaios.com/fr/vet-anatomy/structures-anatomiques/axe-mecanique-du-femur-11111648032' },
};
const srcLink = (k) => { const r = REFS[k]; return r.url ? h('a', { href: r.url, target: '_blank', rel: 'noopener' }, r.t) : r.t; };
