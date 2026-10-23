// =============================================================================
// 50 — programme principal : état, interface, caméra, animation, événements
//      Deux sources : l'os segmenté sur le CT (onglet 1 de CT-CORA3D) ou l'os fictif du modèle synthétique.
// =============================================================================
const S = {
  source: 'fictif',           // 'reel' (os segmenté, servi par le serveur local) | 'fictif' (modèle synthétique)
  cas: 'tibia-varus-procurvatum',
  reglages: Object.fromEntries(OS.map((b) => [b, { thetaF: REGLAGES[b].thetaF, thetaS: REGLAGES[b].thetaS, niveau: REGLAGES[b].niveau, torsion: 0 }])),
  step: 0,
  kind: 'fermeture',          // type de coin : fermeture | ouverture
  progress: 0,                // avancement de la correction (étape « Correction »)
  playing: false,
  ghost: true,
  tor: { tau: 20, rho: 0 },   // étape « torsion » : torsion anatomique et rotation sur la table (°)
  reel: {
    serveur: false,           // serveur local joignable (sinon : os fictif seulement)
    cas: null,                // os détecté dans la série en cours (onglet 1) : /api/cora/cas (cora_cas.json)
    choix: null,              // { serie, os } chargé
    json: null,               // cora_<os>.json de l'os chargé
    chargement: false, erreur: null,
    test: { on: false, frontal: 'varus', sagittal: 'aucun', thetaF: 15, thetaS: 10, niveau: null, torsion: 0 },
    reference: 'normales',    // 'normales' (valeurs de référence converties) | 'sain' (os avant la déformité de test)
    preset: 'vezzoni',        // référence de normalité (publications seulement) : vezzoni | litterature | race
    race: 'levrier',          // race si preset = race (Tomlinson 2007 pour le fémur, Wilke 2002 pour la pente tibiale)
    normales: {},             // valeurs normales utilisées (définition des repères automatiques)
    sd: {},                   // écarts-types utilisés pour le dépistage (± 2 écarts-types)
    sources: {},              // publication d'où vient chaque valeur
    normOuvert: false,
  },
  // guides imprimables (étape 7, construits par le serveur)
  guide: { etat: 'aucun', cle: null, dossier: null, info: null, vue: 'coupe', journal: [], erreur: null },
  // stratégie chirurgicale (panneau « 2 · Stratégie et guide ») : type de coin (auto = recommandation), niveau du trait
  // (z, mm du CORA le long de l'os, + vers distal ; null = règle 1, ou règle 2 automatique si le CORA touche le cartilage),
  // profondeur de la charnière (y, mm de la corticale de la charnière, par type de coin), broches, chien en croissance,
  // inégalité de longueur (mm, + = membre opéré plus court que le membre opposé)
  strat: { auto: true, decalage: null, charniere: { fermeture: CHARNIERE_RETRAIT, ouverture: CHARNIERE_RETRAIT }, broches: '2+2', croissance: false, inegalite: 0 },
  guideParams: {},            // dimensions du guide générique changées pour ce cas (clé -> valeur) ; vide = valeurs par défaut
  preset: '',                 // préréglage clinique choisi
};
let PLAN = null, TORS = null;
let DATA_F = null, MODEL_F = {}, GABARIT = null;          // os fictif (toujours chargé) et gabarit du fémur
let DATA_R = null, MODEL_R = null;                        // os segmenté chargé
const casCourant = () => casDe(S.cas);
const ctx = {
  get kind() { return S.kind; },
  // choix manuel du type de coin (la recommandation automatique est suspendue) ; setKindAuto : revenir à la recommandation
  setKind(k) { S.kind = k; S.strat.auto = false; S.progress = 0; refresh(); },
  setKindAuto() { S.strat.auto = true; if (PLAN?.recommandation) S.kind = PLAN.recommandation.kind; S.progress = 0; refresh(); },
  get strat() { return S.strat; },
  get guideParams() { return S.guideParams; },
  get torsion() { return TORS; },
  // tau / rho : nouvelles valeurs (null = inchangée) ; complet : reconstruire tout le panneau (boutons)
  setTorsion(tau, rho, complet = false) {
    if (tau !== null) S.tor.tau = tau;
    if (rho !== null) S.tor.rho = rho;
    majTorsion(complet);
  },
  // guides imprimables (étape 12)
  get guide() { return S.guide; },
  get guidePret() { return guidePret(); },
  get serveur() { return S.reel.serveur; },
  construireGuide() { construireGuide(); },
  vueGuide(v) { S.guide.vue = v; refresh(); },
  get reference() { return { preset: S.reel.preset, race: S.reel.race }; },
};
const INTEGRE = window.parent !== window;

// ------------------------------------------------------------ mise à jour --
// cas et options de planification de la source courante
const optsStrategie = () => ({ decalageCoupe: S.strat.decalage, charniere: { ...S.strat.charniere }, broches: S.strat.broches,
  croissance: S.strat.croissance, inegaliteLongueur: S.strat.inegalite, parametresGuide: { ...S.guideParams } });
function casEtOptions() {
  if (S.source === 'fictif') { const c = casCourant(); return { cas: c, opts: { ...S.reglages[c.bone], ...optsStrategie() } }; }
  const R = S.reel, bone = R.json.os, T = R.test;
  const cas = casDe(`${bone}-${T.frontal}-${T.sagittal}`);
  const refN = { type: 'normales', valeurs: { ...R.normales }, sd: Object.fromEntries(Object.entries(R.json.normales).map(([k, x]) => [k, R.sd[k] ?? x.sd])), gabarit: GABARIT };
  const reference = T.on && R.reference === 'sain' ? 'sain' : refN;
  const opts = T.on ? { thetaF: T.thetaF, thetaS: T.thetaS, niveau: T.niveau ?? REGLAGES[bone].niveau, torsion: T.torsion, reference } : { sansDeformite: true, reference };
  return { cas, opts: { ...opts, ...optsStrategie() } };
}
function replan() {
  PLAN_ID++;
  if (S.guide.etat === 'pret') { S.guide.etat = 'aucun'; viderGuides(); }
  if (S.source === 'reel' && !MODEL_R) { PLAN = null; TORS = null; clearFragments(); clearGroup(G.bone); clearGroup(G.ghost); return; }
  const { cas, opts } = casEtOptions();
  PLAN = planifier(MODEL, cas, opts);
  if (S.strat.auto && PLAN.recommandation) S.kind = PLAN.recommandation.kind;     // coin recommandé (critères : étape 9)
  if (!PLAN.osteo[S.kind]) { const autre = S.kind === 'fermeture' ? 'ouverture' : 'fermeture'; if (PLAN.osteo[autre]) S.kind = autre; }
  buildBones(PLAN);
  clearFragments();
  const pos = PLAN.pos[PLAN.bone];
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < pos.length; i += 3) for (let c = 0; c < 3; c++) { lo[c] = Math.min(lo[c], pos[i + c]); hi[c] = Math.max(hi[c], pos[i + c]); }
  PLAN.box = { lo, hi };
  TORS = null;
}
function calculTorsion() {
  TORS = { ...planTorsion(MODEL, PLAN.bone, S.tor.tau, S.tor.rho), tau: S.tor.tau, rho: S.tor.rho };
  updateTorsionBone(PLAN.bone, S.tor.tau, S.tor.rho);
}
// l'os sain (transparence) n'a de sens que s'il diffère de l'os planifié
const fantomeDispo = () => !!PLAN && !!PLAN.D;

function dessiner(st) {
  OV.base.clear(); OV.dist.clear();
  if (!PLAN) return;
  const plan = st.plan2D === 'S' ? 'S' : 'F';
  OV.base.plane = OV.dist.plane = plan;
  OV.base.z = OV.dist.z = plan === 'S' ? PLAN.coraC[0] : PLAN.coraC[2];
  st.dessin(PLAN, ctx);
}
function refresh() {
  demanderImage();                              // (l'image est calculée après ce rafraîchissement)
  const st = ETAPES[S.step];
  $('#vide-reel').hidden = !!PLAN;
  if (!PLAN) {
    for (const k of ['bone', 'ghost', 'prox', 'distFrag', 'wedge', 'gap', 'pins', 'pinsDist', 'torsion', 'guide', 'guideRed']) G[k].visible = false;
    dessiner(st);
    renderSteps(); renderExplain(); renderNav(); renderLegend(); renderContext(); renderTimeline(); renderStrategie();
    return;
  }
  if (st.torsion) calculTorsion();
  const coupe = !!st.coupe && PLAN.osteoPossible && !!PLAN.osteo[S.kind];
  // os intact, fragments ou os tordu
  if (coupe) buildFragments(PLAN, S.kind);
  G.torsion.visible = !!st.torsion;
  G.bone.visible = !coupe && !st.torsion;
  G.prox.visible = G.distFrag.visible = coupe;
  G.wedge.visible = coupe && S.kind === 'fermeture';
  G.gap.visible = coupe && S.kind === 'ouverture';
  G.pins.visible = G.pinsDist.visible = coupe && !!st.broches;
  // guides imprimables (étape 12) : guide de coupe sur l'os intact, ou guide de réduction sur l'os corrigé
  const gp = st.id === 'guide' && coupe && guidePret();
  const reduction = gp && S.guide.vue === 'reduction';
  G.guide.visible = gp && !reduction;
  G.guideRed.visible = reduction;
  if (reduction) { G.wedge.visible = false; G.gap.visible = S.kind === 'ouverture'; }
  opaciteOs(gp ? 1 : st.transparence ?? 1);
  if (coupe) applyCorrection(PLAN, S.kind, st.fin || reduction ? 1 : st.anime ? S.progress : 0);
  else setMatrix(G.dist, RT.I());
  G.ghost.visible = S.ghost && fantomeDispo();
  $('#v-ghost').setAttribute('aria-pressed', String(S.ghost && fantomeDispo()));
  $('#v-ghost').disabled = !fantomeDispo();
  dessiner(st);
  renderSteps(); renderExplain(); renderNav(); renderLegend(); renderContext(); renderTimeline();
  if (!glisseStrat) renderStrategie();
}
// os translucide dans les étapes 3D (constructions et broches visibles à travers l'os)
function opaciteOs(o) {
  for (const g of [G.bone, G.prox, G.distFrag]) g.traverse((m) => {
    if (!m.isMesh || m.material === MAT.wedge) return;
    m.material.opacity = o; m.material.depthWrite = o >= 1;
  });
}
// étape « torsion » : mise à jour légère pendant le glissement d'un curseur (le panneau n'est pas reconstruit)
function majTorsion(complet) {
  if (complet) { refresh(); return; }
  calculTorsion();
  dessiner(ETAPES[S.step]);
  const m = TORS.m;
  const set = (id, txt) => { const el = $('#' + id); if (el) el.textContent = txt; };
  set('tor-3d', deg(m.torsion3D)); set('tor-w', mm(m.radio.epicondyles, 2)); set('tor-c', mm(m.radio.condyles, 2));
  const ch = $('#tor-chart'); if (ch) ch.innerHTML = courbeTorsionSVG(PLAN, TORS);
  renderContext();
}

// ------------------------------------------------------------ source : os segmenté / os fictif --
function renderSource() {
  for (const b of $$('#source button')) {
    b.setAttribute('aria-pressed', String(b.dataset.source === S.source));
    if (b.dataset.source === 'reel') b.title = S.reel.serveur ? 'Os segmenté dans l\'onglet « Segmentation CT »' : 'Indisponible : ouvrez CT-CORA3D (serveur local) pour les os segmentés';
  }
  $('#h-cas').textContent = S.source === 'reel' ? '1 · Os détecté (scanner)' : '1 · Choisir le cas';
  $('#adjust-wrap').hidden = S.source === 'reel' && !(MODEL_R && S.reel.test.on);
  $('#adjust-titre').textContent = S.source === 'reel' ? 'Régler la déformité de test' : 'Ajuster les amplitudes et le niveau';
}
async function choisirSource(src, cadrer = true) {
  if (src === S.source && (src === 'fictif' || MODEL_R)) return;
  S.source = src; S.step = Math.min(S.step, ETAPES.length - 1); S.progress = 0; S.playing = false;
  try { localStorage.setItem('ct-cora3d-source', src); } catch (e) { /* stockage indisponible */ }
  if (src === 'fictif') { MODEL = MODEL_F; DATA = DATA_F; MODEL_ID++; }
  else if (MODEL_R) { MODEL = MODEL_R; DATA = DATA_R; MODEL_ID++; actualiserCas(true); }   // suit la série de l'onglet 1
  else await actualiserCas(true);
  replan();
  renderSource(); renderCases(); renderAdjust(); refresh();
  if (cadrer && PLAN) setView(ETAPES[S.step].vue);
}

// Os détecté dans la série en cours de l'onglet 1 (un dossier DICOM = un fémur OU un tibia) : /api/cora/cas.
// auto : charger cet os s'il n'est pas déjà chargé (seulement si l'on travaille sur l'os segmenté).
// serie : le cas d'une série précise (celle de l'os que l'on vient d'ouvrir) plutôt que celle de l'onglet 1.
async function actualiserCas(auto = false, serie = null) {
  const R = S.reel;
  try {
    R.cas = await lireJSON(`/api/cora/cas${serie ? `?serie=${encodeURIComponent(serie)}` : ''}`);
    R.serveur = true;
  } catch (e) {
    R.serveur = false; R.cas = null;
  }
  const c = R.cas;
  const deja = !!(c && MODEL_R && R.choix && R.choix.serie === c.serie && c.candidats.some((x) => x.complet && x.nom === R.choix.os));
  if (auto && c?.cible && !deja && S.source === 'reel') { await ouvrirOs(c.serie, c.cible, true); return; }
  if (S.source === 'reel') renderCases();
  renderSource();
}

async function ouvrirOs(serie, os, cadrer = true) {
  S.source = 'reel';
  S.reel.chargement = true; S.reel.erreur = null; S.reel.choix = { serie, os };
  renderSource(); renderCases();
  try {
    const { json, bones } = await chargerReel(serie, os);
    DATA_R = { meta: null, bones };
    MODEL_R = modeleReel(json, Object.fromEntries(Object.entries(bones).map(([k, b]) => [k, { pos: b.pos, idx: b.idx }])));
    DATA_R.meta = MODEL_R.meta;
    S.reel.json = json;
    S.reel.normales = Object.fromEntries(Object.entries(json.normales).map(([k, x]) => [k, x.valeur]));
    S.reel.sd = Object.fromEntries(Object.entries(json.normales).map(([k, x]) => [k, x.sd]));
    appliquerReference();
    if (!S.reel.test.on) S.reel.reference = 'normales';
    MODEL = MODEL_R; DATA = DATA_R; MODEL_ID++;
  } catch (e) {
    console.error(e);
    S.reel.erreur = `${os} (${serie}) : ${e.message}`;
    MODEL_R = DATA_R = null; S.reel.json = null;
  }
  S.reel.chargement = false;
  await actualiserCas(false, serie);
  S.progress = 0; S.playing = false;
  replan();
  renderSource(); renderCases(); renderAdjust(); refresh();
  if (cadrer && PLAN) setView(ETAPES[S.step].vue);
}

// ------------------------------------------------------------ références de normalité (os segmenté) --
// Uniquement des valeurs publiées (définition « radiographique » des articles) ; la valeur utilisée leur ajoute l'écart
// de définition des repères automatiques (json.normales[k].ecart_definition, mesuré une fois sur l'os sain du modèle).
// 1. Travaux de l'équipe Vezzoni (vérifiés sur PubMed et dans le texte intégral en accès libre) :
//    aLDFA 94 ± 3,3° : borne de normalité de Vezzoni L et al. 2022 (valgus distal du fémur en dessous), qui cite Tomlinson ;
//    mMPTA 93,3 ± 1,78° : Olsen, Vezzoni L, Vezzoni A et al. 2016 (valgus proximal du tibia au-dessus), qui cite Dismukes ;
//    pente tibiale : témoins de Guénégo, Vezzoni et Vezzoni 2021 (40 Labradors sains de plus de 11 ans), TPA 26,3°
//    (20,4 à 30,8°) → mCaPTA = 90° − TPA = 63,7°, écart-type estimé = étendue / 4 = 2,6°.
// Pour les angles que ces travaux ne donnent pas : littérature (LITTERATURE du cœur de calcul).
const VEZZONI_PUBLIE = {
  femur: { aLDFA: { m: 94, sd: 3.3, src: 'Vezzoni L et al. 2022 : borne de normalité 94 ± 3,3° (= Tomlinson 2007, berger allemand)' } },
  tibia: {
    mMPTA: { m: 93.3, sd: 1.78, src: 'Olsen, Vezzoni L, Vezzoni A et al. 2016 : borne de normalité 93,3 ± 1,78° (= Dismukes 2007)' },
    mCaPTA: { m: 63.7, sd: 2.6, src: 'Guénégo, Vezzoni et Vezzoni 2021 : Labradors sains, TPA 26,3° (20,4 à 30,8°) ; mCaPTA = 90° − TPA, écart-type ≈ étendue / 4' },
  },
};
// 2. Par race : Tomlinson et al. 2007 (résumé PubMed 17686134 : moyennes, sans écart-type) pour le fémur ; Wilke et al.
//    2002 (résumé PubMed 12458611 : TPA « traditionnel » moyen) pour la pente tibiale (mCaPTA = 90° − TPA). Les
//    écarts-types manquants sont ceux de la littérature (Labrador de Tomlinson ; Dismukes 2008 pour mCaPTA).
const RACES = {
  levrier: { nom: 'Lévrier', tibia: { mCaPTA: { m: 67.5, src: 'Wilke et al. 2002 : lévriers sains, TPA 22,5° (« à considérer comme normal »)' } } },
  labrador: { nom: 'Labrador', femur: { aLDFA: { m: 97 }, aLPFA: { m: 103 } }, tibia: { mCaPTA: { m: 62.0, src: 'Wilke et al. 2002 : Labradors sains, TPA 28,0°' } } },
  golden: { nom: 'Golden retriever', femur: { aLDFA: { m: 97 }, aLPFA: { m: 98 } } },
  berger: { nom: 'Berger allemand', femur: { aLDFA: { m: 94 }, aLPFA: { m: 101 } } },
  rottweiler: { nom: 'Rottweiler', femur: { aLDFA: { m: 98 }, aLPFA: { m: 96 } } },
};
const PRESETS = [['vezzoni', 'Vezzoni'], ['litterature', 'Littérature'], ['race', 'Race']];
const NOM_PRESET = {
  vezzoni: 'travaux de l\'équipe Vezzoni, complétés par la littérature',
  litterature: 'littérature (Tomlinson 2007, Labrador ; Dismukes 2007-2008)',
  race: 'valeurs publiées pour la race',
};
const nomPreset = () => (S.reel.preset === 'race' ? `race : ${RACES[S.reel.race].nom.toLowerCase()} (Tomlinson 2007, Wilke 2002)` : NOM_PRESET[S.reel.preset]);
// valeur publiée { m, sd, src } de l'angle k pour une référence ; null = pas de valeur publiée (on garde la littérature)
function valeurReference(preset, bone, k, race = S.reel.race) {
  const lit = LITTERATURE[bone][k];
  if (!lit) return null;
  if (preset === 'vezzoni') return VEZZONI_PUBLIE[bone]?.[k] || null;
  if (preset === 'race') {
    const r = RACES[race]?.[bone]?.[k];
    return r ? { m: r.m, sd: lit.sd, src: r.src || `Tomlinson et al. 2007, ${RACES[race].nom} (écart-type : ${lit.src})` } : null;
  }
  return { m: lit.m, sd: lit.sd, src: lit.src };
}
function appliquerReference() {
  const R = S.reel, J = R.json;
  if (!J) return;
  for (const [k, n] of Object.entries(J.normales)) {
    // aCdDFA : pas de valeur publiée de même définition (os sain du modèle mesuré par le programme)
    const v = k === 'aCdDFA' ? null : valeurReference(R.preset, J.os, k) || valeurReference('litterature', J.os, k);
    R.normales[k] = v ? v.m + (n.ecart_definition || 0) : n.valeur;
    R.sd[k] = v ? v.sd : n.sd;
    R.sources[k] = v ? v.src : (n.note || n.source);
  }
}

// ------------------------------------------------------------ guides imprimables (étape 7, serveur local) --
const cleGuide = () => `${PLAN_ID}|${S.kind}`;
const guidePret = () => S.guide.etat === 'pret' && S.guide.cle === cleGuide();
function enBase64(t) {
  const u8 = new Uint8Array(t.buffer, t.byteOffset, t.byteLength);
  let s = '';
  for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  return btoa(s);
}
const fichierGuide = (dossier, nom, telecharger = false) => `/api/cora/guide/fichier?dossier=${encodeURIComponent(dossier)}&f=${nom}${telecharger ? '&telecharger=1' : ''}`;
function majJournalGuide() {
  const el = $('#guide-journal');
  if (el) el.textContent = S.guide.journal.length ? S.guide.journal.join('\n') : 'Démarrage…';
}
// Envoie la prescription et l'os planifié au serveur, qui construit le guide de coupe (et son verrou de réduction, ou un
// guide de réduction séparé)
// (code_source/etape7_guide.py) dans le fil de calcul ; suit le calcul, puis charge les maillages pour la vue 3D.
async function construireGuide() {
  const Gd = S.guide;
  if (!PLAN?.osteo[S.kind] || Gd.etat === 'calcul') return;
  Object.assign(Gd, { etat: 'calcul', cle: cleGuide(), info: null, dossier: null, journal: [], erreur: null, vue: 'coupe' });
  viderGuides(); refresh();
  try {
    const corps = { action: 'guide', prescription: prescription(PLAN, S.kind, { parametresGuide: S.guideParams }),
      sommets: enBase64(Float32Array.from(PLAN.pos[PLAN.bone])), triangles: enBase64(Uint32Array.from(DATA.bones[PLAN.bone].idx)) };
    // os voisins tels que planifiés (fibula du tibia ; rotule et fabelles du fémur) et cartilage articulaire de l'os :
    // le guide et les broches doivent les éviter
    const voisins = { ...Object.fromEntries(PLAN.meshes.filter((n) => n !== PLAN.bone).map((n) => [n, PLAN.pos[n]])), ...(PLAN.voisins || {}) };
    corps.voisins = Object.entries(voisins).filter(([n]) => DATA.bones[n]).map(([nom, pos]) => ({
      nom, sommets: enBase64(Float32Array.from(pos)), triangles: enBase64(Uint32Array.from(DATA.bones[nom].idx)) }));
    if (PLAN.articulaire) corps.articulaire = enBase64(Uint8Array.from(PLAN.articulaire, (x) => (x ? 255 : 0)));
    if (PLAN.reel && S.reel.choix) { corps.serie = S.reel.choix.serie; corps.nom_os = S.reel.choix.os; }
    const r = await fetch('/api/action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).erreur || r.statusText);
    let t;
    for (;;) {
      await new Promise((res) => setTimeout(res, 700));
      t = (await lireJSON('/api/etat')).travail;
      Gd.journal = t.journal.filter((l) => l.startsWith('[étape 7]')).map((l) => l.replace('[étape 7] ', ''));
      majJournalGuide();
      if (t.etat !== 'en_cours') break;
    }
    if (t.etat === 'erreur') throw new Error(t.erreur || 'erreur pendant le calcul');
    const dossier = t.resultat?.dossier;
    if (!dossier) throw new Error('le serveur n\'a pas renvoyé de dossier de résultats');
    const info = await lireJSON(`/api/cora/guide?dossier=${encodeURIComponent(dossier)}`);
    const meshes = {};
    const liste = [['proximal', 'guide_coupe_proximal.bin'], ['distal', 'guide_coupe_distal.bin'], ['coin', 'guide_coupe_coin.bin'], ['ponts', 'guide_coupe_ponts.bin'],
      ['reduction', 'guide_reduction.bin'], ['verrou_proximal', 'verrou_proximal.bin'], ['verrou_distal', 'verrou_distal.bin'], ['verrou_broches', 'verrou_broches.bin']];
    for (const [k, n] of liste) {
      if (info.disponibles.includes(n)) meshes[k] = await lireMaillage(fichierGuide(dossier, n));
    }
    if (Gd.cle !== cleGuide()) { Gd.etat = 'aucun'; refresh(); return; }     // la planification a changé entre-temps
    construireGuides(meshes);
    Object.assign(Gd, { etat: 'pret', dossier, info });
  } catch (e) {
    console.error(e);
    Object.assign(Gd, { etat: 'erreur', erreur: e.message });
  }
  refresh();
  if (guidePret() && ETAPES[S.step].id === 'guide') setView(ETAPES[S.step].vue);
}
function montrerDossierGuide() {
  if (S.guide.dossier) fetch('/api/montrer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dossier_guide: S.guide.dossier }) });
}

// ------------------------------------------------------------ panneau gauche --
const ICONE = {
  varus: '<svg width="16" height="22" viewBox="0 0 16 22" aria-hidden="true"><path d="M6 1v9l-3 11" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  valgus: '<svg width="16" height="22" viewBox="0 0 16 22" aria-hidden="true"><path d="M10 1v9l3 11" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  aucun: '<svg width="16" height="22" viewBox="0 0 16 22" aria-hidden="true"><path d="M8 1v20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  procurvatum: '<svg width="16" height="22" viewBox="0 0 16 22" aria-hidden="true"><path d="M11 1 5 11l6 10" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  recurvatum: '<svg width="16" height="22" viewBox="0 0 16 22" aria-hidden="true"><path d="M5 1l6 10-6 10" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
const LIBELLE = { femur: 'Fémur', tibia: 'Tibia', varus: 'Varus', valgus: 'Valgus', aucun: 'Aucune', procurvatum: 'Procurv.', recurvatum: 'Recurv.' };
const groupeCas = (titre, valeurs, courant, choisir, icones = true) => h('div', { class: 'case-group' },
  h('span', { class: 'case-lbl' }, titre),
  h('div', { class: `case-row n${valeurs.length}`, role: 'group', 'aria-label': titre }, valeurs.map((v) => h('button', {
    type: 'button', class: 'case', 'aria-pressed': String(v === courant), title: v,
    onclick: () => choisir(v), html: `${icones ? ICONE[v] : ''}<span>${LIBELLE[v]}</span>`,
  }))));
function renderCases() {
  if (S.source === 'reel') { renderReel(); return; }
  const c = casCourant();
  $('#cases').replaceChildren(
    selectPresets(),
    groupeCas('Os', OS, c.bone, (v) => choisirCas(`${v}-${c.frontal}-${c.sagittal}`), false),
    groupeCas('Plan frontal (vue de face)', FRONTAL, c.frontal, (v) => choisirCas(`${c.bone}-${v}-${c.sagittal}`)),
    groupeCas('Plan sagittal (vue de profil)', SAGITTAL, c.sagittal, (v) => choisirCas(`${c.bone}-${c.frontal}-${v}`)),
    h('p', { class: 'src', id: 'case-sum' }, resumeCas()),
  );
}
function resumeCas() {
  if (!PLAN) return '';
  const v = PLAN.validation;
  if (!PLAN.D) return `θ entre les axes : ${deg(PLAN.theta)} (F ${deg(Math.abs(PLAN.Fm))}, S ${deg(Math.abs(PLAN.Sm))}).`;
  return PLAN.sagittal === 'aucun'
    ? `Déformité pure dans le plan frontal : θ = ${deg(v.thetaVrai)}.`
    : `Une seule angulation de θ = ${deg(v.thetaVrai)} dans un plan oblique à ${deg(v.phiVrai, 0)} du plan frontal.`;
}
const nomSerie = (s) => s.replace(/^greyhound_hindlimb_/, '').replace(/_/g, ' ');
const libOs = (nom) => `${nom.startsWith('femur') ? 'Fémur' : 'Tibia'}${nom.includes('_') ? ' ' + nom.split('_')[1] : ''}`;
function renderReel() {
  const R = S.reel, el = [];
  if (!R.serveur) {
    el.push(h('div', { class: 'box warn' }, h('h3', {}, 'Serveur local absent'),
      para('Les os segmentés sont fournis par l\'application CT-CORA3D (double-clic sur <b>CT-CORA3D.app</b> ou <b>Lancer sur Windows.bat</b>). Ouvert seul, ce fichier ne montre que l\'os fictif.'),
      h('button', { type: 'button', class: 'btn', onclick: () => choisirSource('fictif') }, 'Voir l\'os fictif')));
    $('#cases').replaceChildren(...el);
    return;
  }
  const cas = R.cas;
  const boutons = h('div', { class: 'ligne-btn' },
    h('button', { type: 'button', class: 'btn petit', onclick: () => actualiserCas(true) }, 'Actualiser'),
    INTEGRE ? h('button', { type: 'button', class: 'btn petit', onclick: () => window.parent.postMessage({ type: 'onglet', nom: 'ct' }, '*') }, '← Segmentation CT') : null);
  if (!cas || !cas.serie || !cas.cible) {
    el.push(h('div', { class: 'box warn' }, h('h3', {}, cas?.serie ? 'Aucun os planifiable dans cette série' : 'Aucun os détecté'),
      para(cas?.raison || 'Segmentez une série dans l\'onglet « Segmentation CT » : le fémur ou le tibia complet y est détecté automatiquement.'),
      ...(cas?.candidats || []).map((c) => h('p', { class: 'src' }, `${libOs(c.nom)} : ${c.complet ? 'complet' : c.raison}`))), boutons);
    $('#cases').replaceChildren(...el);
    return;
  }
  // l'os détecté (un dossier DICOM = un fémur OU un tibia) ; les autres os du scanner ne sont pas planifiables
  const actif = R.choix && R.choix.serie === cas.serie ? R.choix.os : cas.cible;
  const c = cas.candidats.find((x) => x.nom === actif) || cas.candidats.find((x) => x.nom === cas.cible);
  const complets = cas.candidats.filter((x) => x.complet), ignores = cas.candidats.filter((x) => !x.complet);
  const J = R.json && MODEL_R && R.choix?.serie === cas.serie && R.choix?.os === c.nom ? R.json : null;
  el.push(h('div', { class: 'os-detecte' },
    h('div', { class: 'od-tete' }, h('b', {}, `${libOs(c.nom)} ${c.cote || ''}`), h('span', { class: 'tag ok' }, 'détecté')),
    h('div', { class: 'od-meta' }, `Série ${nomSerie(cas.serie)}${c.longueur_mm ? ` · ${fr(c.longueur_mm, 0)} mm` : ''}${J ? ` · ${Object.keys(J.reperes).length} repères automatiques` : ''}`),
    h('p', { class: 'src' }, cas.raison + (cas.ouverte === false ? ' (la série ouverte dans l\'onglet 1 n\'est pas encore segmentée : dernière série segmentée)' : '')),
    J?.miroir ? h('p', { class: 'src' }, 'Membre gauche : analysé en miroir, comme un membre droit.') : null,
    complets.length > 1 ? h('div', { class: 'case-row n2', role: 'group', 'aria-label': 'Os complets' }, complets.map((x) => h('button', {
      type: 'button', class: 'case', 'aria-pressed': String(x.nom === c.nom), onclick: () => ouvrirOs(cas.serie, x.nom),
    }, h('span', {}, libOs(x.nom) + (x.nom === cas.controlateral ? ' (contro.)' : ''))))) : null,
    ignores.length ? h('p', { class: 'src' }, `Ignoré${ignores.length > 1 ? 's' : ''} : ${ignores.map((x) => `${libOs(x.nom).toLowerCase()} (${(x.raison || 'incomplet').split(' :')[0]})`).join(' ; ')}.`) : null));
  el.push(boutons);
  if (R.chargement) el.push(h('p', { class: 'src' }, `Chargement de l'os (${nomSerie(cas.serie)})…`));
  if (R.erreur) el.push(h('div', { class: 'box warn' }, para(R.erreur)));
  if (J) {
    // déformité de test
    const T = R.test;
    el.push(h('div', { class: 'case-group' },
      h('span', { class: 'case-lbl' }, 'Déformité de test (simulation)'),
      h('label', { class: 'bascule' }, h('input', { type: 'checkbox', checked: T.on, onchange: (e) => { T.on = e.target.checked; if (!T.on) R.reference = 'normales'; replanUI(); } }),
        h('span', {}, T.on ? 'Imposer une déformité connue à cet os réel' : 'Os analysé tel quel (pas de déformité imposée)'))));
    el.push(selectPresets(J.os));
    if (T.on) {
      el.push(groupeCas('Plan frontal', FRONTAL, T.frontal, (v) => { T.frontal = v; replanUI(); }));
      el.push(groupeCas('Plan sagittal', SAGITTAL, T.sagittal, (v) => { T.sagittal = v; replanUI(); }));
    }
    // référence
    el.push(h('div', { class: 'case-group' },
      h('span', { class: 'case-lbl' }, 'Référence'),
      h('div', { class: 'case-row n2', role: 'group', 'aria-label': 'Référence' },
        h('button', { type: 'button', class: 'case', 'aria-pressed': String(R.reference === 'normales' || !T.on), onclick: () => { R.reference = 'normales'; replanUI(); } }, h('span', {}, 'Valeurs normales')),
        h('button', { type: 'button', class: 'case', 'aria-pressed': String(R.reference === 'sain' && T.on), disabled: !T.on, title: T.on ? 'L\'os avant la déformité de test joue le rôle du membre controlatéral sain' : 'Disponible avec une déformité de test', onclick: () => { R.reference = 'sain'; replanUI(); } }, h('span', {}, 'Os avant déformité')))));
    if (R.reference === 'normales' || !T.on) el.push(tableNormales());
    el.push(h('p', { class: 'src', id: 'case-sum' }, resumeCas()));
  }
  $('#cases').replaceChildren(...el);
}
// valeurs normales de l'os segmenté : choix de la référence (publications seulement) et valeurs utilisées, avec leur source
function tableNormales() {
  const R = S.reel, J = R.json, bone = J.os;
  const nouveau = (f) => () => { f(); appliquerReference(); replanUI(); };
  const presets = h('div', { class: 'seg presets', role: 'group', 'aria-label': 'Référence de normalité' },
    PRESETS.map(([id, nom]) => h('button', { type: 'button', 'aria-pressed': String(R.preset === id), onclick: nouveau(() => { R.preset = id; }) }, nom)));
  const race = R.preset === 'race'
    ? h('select', { class: 'choix', 'aria-label': 'Race', onchange: (e) => { R.race = e.target.value; appliquerReference(); replanUI(); } },
      Object.entries(RACES).map(([k, r]) => h('option', { value: k, selected: k === R.race },
        `${r.nom} : ${[r.femur ? 'fémur' : null, r.tibia ? 'pente tibiale' : null].filter(Boolean).join(', ')}`)))
    : null;
  const ligne = (k) => h('tr', {}, h('td', {}, court(k)),
    h('td', { class: 'hi' }, deg(R.normales[k])),
    h('td', { class: 'src', title: `${R.sources[k] || ''} ; écart de définition ${degS(J.normales[k].ecart_definition)}` },
      k === 'aCdDFA' ? 'os du modèle' : `${fr(R.normales[k] - (J.normales[k].ecart_definition || 0))} ± ${fr(R.sd[k], 1)}`));
  const det = h('details', { class: 'adjust' },
    h('summary', {}, `Valeurs normales : ${nomPreset()}`),
    h('div', { class: 'adjust-body' }, presets, race,
      h('table', { class: 't compact' }, h('thead', {}, h('tr', {}, h('th', {}, 'Angle'), h('th', {}, 'Utilisée'), h('th', {}, 'Publiée'))),
        h('tbody', {}, Object.keys(J.normales).filter((k) => k !== 'varusFem').map(ligne))),
      h('p', { class: 'src' }, 'Valeurs tirées uniquement de publications (survolez une ligne pour sa source). « Utilisée » = valeur publiée + écart de définition des repères automatiques. Comparaison et explications : étape 1.')));
  det.open = R.normOuvert;
  det.addEventListener('toggle', () => { R.normOuvert = det.open; });
  return det;
}
// nouvelle planification après un changement de réglage (os segmenté)
function replanUI(reconstruire = true) {
  S.progress = 0; S.playing = false;
  replan();
  if (reconstruire) renderCases(); else { const s = $('#case-sum'); if (s) s.textContent = resumeCas(); }
  renderSource(); renderAdjust(); refresh();
}
function renderAdjust() {
  if (S.source === 'reel') {
    if (!MODEL_R || !S.reel.test.on) { $('#adjust').replaceChildren(); return; }
    const T = S.reel.test, bone = S.reel.json.os, R = REGLAGES[bone];
    if (T.niveau === null) T.niveau = R.niveau;
    $('#adjust').replaceChildren(
      curseur('r-thetaF', `Composante frontale F (${T.frontal})`, 0, R.thetasF[1], 1, T.thetaF, (x) => deg(x, 0), (x) => { T.thetaF = x; planifierBientot(); }, `${R.thetasF[0]}°`, `${R.thetasF[1]}°`),
      curseur('r-thetaS', `Composante sagittale S${T.sagittal === 'aucun' ? ' (aucune)' : ` (${T.sagittal})`}`, R.thetasS[0], R.thetasS[1], 1, T.thetaS, (x) => deg(x, 0), (x) => { T.thetaS = x; planifierBientot(); }, `${R.thetasS[0]}°`, `${R.thetasS[1]}°`, T.sagittal === 'aucun'),
      curseur('r-niveau', 'Niveau de l\'apex', R.niveaux[0], R.niveaux[1], 0.01, T.niveau, (x) => `${fr(x * 100, 0)} %`, (x) => { T.niveau = x; planifierBientot(); }, 'plus proximal', 'plus distal'),
      curseur('r-tau', 'Torsion de test τ (segment distal)', -30, 30, 1, T.torsion, (x) => `${x > 0 ? '+' : ''}${fr(x, 0)}°`, (x) => { T.torsion = x; planifierBientot(); }, 'interne', 'externe'),
      h('p', { class: 'src' }, `Déformité imposée à l'os réel (rotation du segment distal autour d'un axe oblique passant par l'apex, et torsion τ autour de son axe long). Niveau : fraction de la longueur ${depuis({ bone })}. Si la torsion sort de la normale, la correction ajoute une dérotation (étapes 10 à 12).`),
    );
    return;
  }
  const c = casCourant(), R = REGLAGES[c.bone], v = S.reglages[c.bone];
  $('#adjust').replaceChildren(
    curseur('r-thetaF', `Composante frontale F (${c.frontal})`, 0, R.thetasF[1], 1, v.thetaF, (x) => deg(x, 0), (x) => { v.thetaF = x; S.preset = ''; planifierBientot(); }, '0°', `${R.thetasF[1]}°`),
    curseur('r-thetaS', `Composante sagittale S${c.sagittal === 'aucun' ? ' (aucune)' : ` (${c.sagittal})`}`, R.thetasS[0], R.thetasS[1], 1, v.thetaS, (x) => deg(x, 0), (x) => { v.thetaS = x; planifierBientot(); }, `${R.thetasS[0]}°`, `${R.thetasS[1]}°`, c.sagittal === 'aucun'),
    curseur('r-niveau', 'Niveau de l\'apex', R.niveaux[0], R.niveaux[1], 0.01, v.niveau, (x) => `${fr(x * 100, 0)} %`, (x) => { v.niveau = x; planifierBientot(); }, 'plus proximal', 'plus distal'),
    curseur('r-tau', 'Torsion τ du segment distal', -30, 30, 1, v.torsion, (x) => `${x > 0 ? '+' : ''}${fr(x, 0)}°`, (x) => { v.torsion = x; planifierBientot(); }, 'interne', 'externe'),
    h('p', { class: 'src' }, `F et S sont les angles projetés (ce que montrent la vue de face et la vue de profil). Niveau : fraction de la longueur ${depuis(PLAN || { bone: c.bone })}, plage limitée pour que les repères utilisés restent hors de la zone déformée.`),
    h('button', { type: 'button', class: 'btn', onclick: () => { Object.assign(v, { thetaF: R.thetaF, thetaS: R.thetaS, niveau: R.niveau, torsion: 0 }); renderAdjust(); planifierBientot(); } }, 'Valeurs par défaut'),
  );
}
// ------------------------------------------------------------ préréglages cliniques --
// Liste déroulante : déformités typiques (PRESETS_DEFORMITE du cœur de calcul). Os fictif : choisit l'os et la déformité ;
// os segmenté : impose la déformité comme déformité de test (seulement les préréglages de cet os).
function selectPresets(bone = null) {
  const liste = PRESETS_DEFORMITE.filter((p) => !bone || p.os === bone);
  const groupes = [['Tibia', (p) => p.os === 'tibia'], ['Fémur', (p) => p.os === 'femur']];
  const sel = h('select', { class: 'choix', 'aria-label': 'Préréglage clinique', onchange: (e) => appliquerPreset(e.target.value) },
    h('option', { value: '', selected: !S.preset }, bone ? 'Déformité de test : préréglage clinique…' : 'Préréglage clinique…'),
    ...groupes.map(([nom, f]) => {
      const items = liste.filter(f);
      return items.length ? h('optgroup', { label: nom }, items.map((p) => h('option', { value: p.id, selected: S.preset === p.id }, p.titre))) : null;
    }));
  const p = PRESETS_DEFORMITE.find((x) => x.id === S.preset);
  return h('div', { class: 'case-group' }, sel, p ? h('p', { class: 'src' }, p.contexte) : null);
}
function appliquerPreset(id) {
  const p = PRESETS_DEFORMITE.find((x) => x.id === id);
  S.preset = p ? id : '';
  if (!p) { renderCases(); return; }
  if (S.source === 'fictif') {
    S.cas = casDe(`${p.os}-${p.frontal}-${p.sagittal}`).id;
    Object.assign(S.reglages[p.os], { thetaF: p.thetaF, thetaS: p.thetaS || REGLAGES[p.os].thetaS, niveau: p.niveau, torsion: p.torsion || 0 });
  } else if (S.reel.json && S.reel.json.os === p.os) {
    Object.assign(S.reel.test, { on: true, frontal: p.frontal, sagittal: p.sagittal, thetaF: p.thetaF, thetaS: p.thetaS || 10, niveau: p.niveau, torsion: p.torsion || 0 });
  }
  Object.assign(S.strat, { auto: true, decalage: null });
  S.progress = 0; S.playing = false;
  replan();
  renderCases(); renderAdjust(); refresh();
  if (PLAN) setView(ETAPES[S.step].vue);
}

// ------------------------------------------------------------ stratégie : coin, niveau de coupe, charnière, broches --
// Panneau de gauche (survit aux rafraîchissements) : pendant qu'on fait glisser un de ses curseurs, la planification est
// refaite en continu mais le panneau n'est reconstruit qu'au relâchement (sinon le curseur serait remplacé sous la souris).
let glisseStrat = false;
const RAISON_RECO = {
  abord: 'seul type de coin dont la face d\'entrée de la lame est accessible par un abord usuel',
  charniere: 'il garde la charnière corticale (stabilité, pas de translation)',
  regle: 'il permet de couper au CORA (règle 1, sans translation)',
  coinFin: 'le coin de fermeture serait trop fin pour deux fentes',
  ouverture: 'l\'ouverture serait trop grande (greffe, consolidation longue)',
  longueur: 'il compense le mieux l\'inégalité de longueur indiquée',
  stabilite: 'par défaut : surfaces d\'os en contact, stabilité primaire, pas de greffe',
  seul: 'seul type de coin possible',
};
function curseurStrat(...args) {
  const row = curseur(...args);
  const inp = $('input', row);
  inp.addEventListener('input', () => { glisseStrat = true; });
  inp.addEventListener('change', () => { glisseStrat = false; renderStrategie(); refresh(); });
  return row;
}
function replanStrat() { S.progress = 0; S.playing = false; planifierBientot(); }
function renderStrategie() {
  const el = $('#strat');
  if (!el) return;
  $('#sec-strat').hidden = !PLAN;
  if (!PLAN) { el.replaceChildren(); return; }
  const Sg = S.strat;
  if (!PLAN.osteoPossible) { el.replaceChildren(h('p', { class: 'strat-note' }, 'Pas d\'ostéotomie au CORA pour ce cas.')); return; }
  const O = PLAN.osteo[S.kind], rec = PLAN.recommandation;
  const nomK = { fermeture: 'fermeture', ouverture: 'ouverture' };
  const btnK = (k) => h('button', { type: 'button', 'aria-pressed': String(!Sg.auto && S.kind === k), disabled: !PLAN.osteo[k],
    title: PLAN.osteo[k]?.faisable === false ? 'pas réalisable par un abord usuel (voir l\'étape 9)' : '', onclick: () => ctx.setKind(k) },
  k === 'fermeture' ? 'Fermeture' : 'Ouverture', rec?.kind === k ? h('span', { class: 'etoile', title: 'recommandé' }, '★') : null);
  const coin = h('div', { class: 'case-group' }, h('span', { class: 'case-lbl' }, 'Type de coin'),
    h('div', { class: 'seg coin', role: 'group', 'aria-label': 'Type de coin' },
      h('button', { type: 'button', 'aria-pressed': String(Sg.auto), onclick: () => ctx.setKindAuto() }, `Auto (${rec ? nomK[rec.kind] : '—'})`),
      btnK('fermeture'), btnK('ouverture')),
    rec ? h('p', { class: 'strat-note' }, `★ ${nomK[rec.kind]} recommandée : ${RAISON_RECO[rec.decisif] || rec.decisif}.`) : null,
    O && O.faisable === false ? h('p', { class: 'strat-note', style: { color: 'var(--c-warn)' } }, O.voisinSurLame
      ? `Ce coin n'est pas réalisable par un abord usuel : par la face ${nomDirection(O.faceCoin)}, ${O.voisinSurLame} est sur le trajet de la lame ; un guide y occuperait l'espace entre l'os et ${O.voisinSurLame} : pas de guide de coupe.`
      : `Ce coin n'est pas réalisable par un abord usuel : le guide est posé sur la face ${nomDirection(O.faceCoin)} (abord non usuel).`) : null);
  if (!O) { el.replaceChildren(coin); return; }
  const Lg = PLAN.validation.longueurOs, zMax = Math.round(0.3 * Lg);
  const zVal = Sg.decalage ?? O.z;
  const niveau = curseurStrat('s-z', 'Niveau du trait de coupe (z)', -zMax, zMax, 1, zVal,
    (x) => (Math.abs(x) < 0.5 ? 'au CORA (règle 1)' : `${x > 0 ? '+' : '−'}${fr(Math.abs(x), 0)} mm (règle 2)`),
    (x) => { Sg.decalage = x; replanStrat(); }, '← proximal', 'distal →');
  const auto = Sg.decalage === null;
  const niveauBtns = h('div', { class: 'ligne-btn' },
    h('button', { type: 'button', class: 'btn petit', 'aria-pressed': String(Sg.decalage === 0), onclick: () => { Sg.decalage = 0; replanStrat(); renderStrategie(); } }, 'Au CORA (règle 1)'),
    h('button', { type: 'button', class: 'btn petit', 'aria-pressed': String(auto), onclick: () => { Sg.decalage = null; replanStrat(); renderStrategie(); } }, 'Automatique'));
  const noteZ = h('p', { class: 'strat-note' }, auto
    ? (O.regle === 2 ? `Automatique : le CORA touche le cartilage, la coupe est déplacée de ${fr(O.decalageCoupe, 0)} mm (règle 2).` : 'Automatique : règle 1 de Paley, coupe au CORA.')
    : 'Coupe déplacée le long de l\'os : l\'ACA reste au CORA (axes réalignés), le fragment glisse le long de la coupe (translation, règle 2). Contraintes au niveau choisi : étape 9.');
  const hMax = Math.max(0.6, O.hMax);
  const prof = curseurStrat('s-h', `Profondeur de la charnière (y) : depuis la corticale ${S.kind === 'fermeture' ? 'concave' : 'convexe'}`, 0.5, Math.round(hMax * 10) / 10, 0.1, O.h,
    (x) => `${fr(x, 1)} mm`, (x) => { Sg.charniere[S.kind] = x; replanStrat(); },
    'au ras de la corticale', S.kind === 'fermeture' ? 'centre (coin neutre)' : `${fr(hMax, 1)} mm (max.)`);
  const noteH = h('p', { class: 'strat-note' }, S.kind === 'fermeture'
    ? `≤ ${PONT_MAX} mm : pont d'os qui plie (charnière conservée). Au-delà : coin mixte, ostéotomie complète ; au centre, coin neutre (longueur conservée). Actuellement : ${O.coinMixte ? 'coin mixte' : O.charniereConservee ? 'charnière conservée' : 'ostéotomie complète'}, longueur ${O.deltaOperation >= 0 ? '+' : '−'}${fr(Math.abs(O.deltaOperation), 1)} mm.`
    : `Coin d'ouverture : la charnière reste au plus à ${CHARNIERE_OUVERTURE_MAX} mm de la corticale convexe (au-delà, la partie convexe devrait se chevaucher). Actuellement : ${O.charniereConservee ? 'charnière conservée' : 'ostéotomie complète'}, longueur +${fr(Math.abs(O.deltaOperation), 1)} mm.`);
  const broches = h('div', { class: 'case-group' }, h('span', { class: 'case-lbl' }, 'Broches de réduction'),
    h('div', { class: 'seg coin', role: 'group', 'aria-label': 'Broches' }, Object.entries(CONFIG_BROCHES).map(([k, c]) => h('button', {
      type: 'button', 'aria-pressed': String(Sg.broches === k), title: c.nom, onclick: () => { Sg.broches = k; replanStrat(); renderStrategie(); },
    }, k === '2+2' ? '2 + 2' : k === '1+1' ? '1 + 1' : '1 + 2'))),
    h('p', { class: 'strat-note' }, `${CONFIG_BROCHES[Sg.broches].nom}${O.placementBroches.ok ? '' : ' — placement incomplet, voir les alertes (étape 12)'}.`));
  const ineg = curseurStrat('s-ineg', 'Membre opéré plus court (+) ou plus long (−)', -20, 20, 1, Sg.inegalite,
    (x) => (x === 0 ? 'égal' : `${x > 0 ? '+' : '−'}${fr(Math.abs(x), 0)} mm`), (x) => { Sg.inegalite = x; replanStrat(); }, 'plus long', 'plus court');
  const croissance = h('label', { class: 'bascule' }, h('input', { type: 'checkbox', checked: Sg.croissance, onchange: (e) => { Sg.croissance = e.target.checked; replanStrat(); } }),
    h('span', {}, 'Chien en croissance (physes ouvertes : zones à ne pas couper)'));
  // inégalité de longueur : ne sert qu'au critère « longueur » du choix du coin (la fermeture raccourcit, l'ouverture allonge)
  const lg = (x) => (x ? `${x.deltaOperation >= 0 ? '+' : '−'}${fr(Math.abs(x.deltaOperation), 1)} mm` : '—');
  const noteL = h('p', { class: 'strat-note' }, `Écart de longueur avec le membre opposé, mesuré à l'examen ou sur une radiographie des deux membres. Il sert seulement à départager les deux coins (critère « longueur », à partir de 3 mm) : ici, fermeture ${lg(PLAN.osteo.fermeture)}, ouverture ${lg(PLAN.osteo.ouverture)}${rec?.decisif === 'longueur' ? ' ; c\'est ce critère qui décide' : ''}.`);
  el.replaceChildren(...[coin, niveau, niveauBtns, noteZ, prof, noteH, broches, ineg, noteL, croissance].filter(Boolean));
}

// ------------------------------------------------------------ guide générique : dimensions --
// Toutes les dimensions de conception du guide sont des paramètres (PARAMS_GUIDE) ; celles qui dépendent de l'os en
// découlent pour chaque scanner. Valeur changée -> nouvelle planification (broches, tours) et guide à reconstruire.
function renderGuideParams() {
  const el = $('#gparams');
  if (!el) return;
  const G_ = S.guideParams;
  const lignes = [];
  let groupe = null;
  for (const p of PARAMS_GUIDE) {
    if (p.groupe !== groupe) { groupe = p.groupe; lignes.push(h('tr', {}, h('td', { colspan: 3, class: 'gparams-groupe' }, groupe))); }
    const val = G_[p.cle] ?? p.def;
    const inp = h('input', { type: 'number', min: p.min, max: p.max, step: p.pas, value: val, 'aria-label': p.nom, class: G_[p.cle] !== undefined ? 'modifie' : '' });
    inp.addEventListener('change', () => {
      let x = +inp.value;
      if (!Number.isFinite(x)) x = p.def;
      x = clamp(x, p.min, p.max);
      if (Math.abs(x - p.def) < 1e-9) delete G_[p.cle]; else G_[p.cle] = x;
      renderGuideParams(); replanStrat();
    });
    lignes.push(h('tr', { title: `${p.nom} : défaut ${fr(p.def, p.pas < 0.1 ? 2 : 1)} ${p.unite}, de ${fr(p.min, p.pas < 0.1 ? 2 : 1)} à ${fr(p.max, p.pas < 0.1 ? 2 : 1)}` },
      h('td', {}, h('b', {}, p.sym), ` ${p.nom}`), h('td', {}, inp), h('td', {}, p.unite)));
  }
  const n = Object.keys(G_).length;
  el.replaceChildren(
    h('p', { class: 'strat-note' }, 'Le guide est un modèle paramétrique : ces dimensions de conception sont les mêmes pour tous les cas (sauf si vous les changez ici). Celles qui dépendent de l\'os (longueur des fentes, hauteur des tours, position des broches, longueur de la coque…) en découlent pour chaque scanner : plan 2D coté à l\'étape 12.'),
    h('table', { class: 't compact gp' }, h('tbody', {}, lignes)),
    h('div', { class: 'ligne-btn' }, h('button', { type: 'button', class: 'btn petit', disabled: !n, onclick: () => { S.guideParams = {}; renderGuideParams(); replanStrat(); } }, `Valeurs par défaut${n ? ` (${n} changée${n > 1 ? 's' : ''})` : ''}`)));
}

let planTimer = null;
function planifierBientot() {
  clearTimeout(planTimer);
  planTimer = setTimeout(() => { replan(); S.progress = 0; refresh(); const s = $('#case-sum'); if (s) s.textContent = resumeCas(); }, 60);
}
function renderSteps() {
  const ol = $('#steps');
  if (!ol.childElementCount) {
    ETAPES.forEach((st, i) => ol.append(h('li', {}, h('button', { type: 'button', class: 'step', 'data-i': i, onclick: () => allerA(i) },
      h('span', { class: 'n' }, String(i + 1)), h('span', { class: 't' }, st.court)))));
  }
  $$('.step', ol).forEach((b, i) => {
    if (i === S.step) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
    b.classList.toggle('done', i < S.step);
    b.disabled = !PLAN;
  });
}

// ------------------------------------------------------------ explication --
function renderExplain() {
  const st = ETAPES[S.step];
  if (!PLAN) {
    $('#explain').replaceChildren(h('h2', { class: 'title' }, 'Os segmenté'),
      para('Choisissez un fémur ou un tibia <b>complet</b> dans le panneau de gauche. Il vient de la segmentation du scanner (onglet 1) ; ses repères anatomiques sont placés automatiquement.'),
      para('Un os coupé par le champ du scanner n\'est pas planifiable : la méthode CORA a besoin des deux articulations.'),
      h('button', { type: 'button', class: 'btn', onclick: () => choisirSource('fictif') }, 'Voir plutôt l\'os fictif'));
    return;
  }
  $('#explain').replaceChildren(
    h('h2', { class: 'title' }, h('span', { class: 'n' }, `${S.step + 1}/${ETAPES.length}`), st.titre(PLAN)),
    ...st.texte(PLAN, ctx).filter(Boolean),
  );
}
function renderNav() {
  const st = ETAPES[S.step];
  $('#where-title').textContent = PLAN ? st.titre(PLAN) : 'Aucun os chargé';
  $('#where-n').textContent = `Étape ${S.step + 1} sur ${ETAPES.length} · ← → pour naviguer`;
  $('#prev').setAttribute('aria-disabled', String(S.step === 0 || !PLAN));
  const nx = $('#next');
  nx.setAttribute('aria-disabled', String(S.step === ETAPES.length - 1 || !PLAN));
  $('.t', nx).textContent = S.step === ETAPES.length - 1 ? 'Terminé' : 'Suivant';
}
function renderLegend() {
  const st = ETAPES[S.step], L = $('#legend');
  if (!PLAN) { L.hidden = true; return; }
  let keys = [...st.legende];
  if (S.kind === 'ouverture') keys = keys.map((k) => (k === 'wedge' ? 'gap' : k));
  if (st.id === 'corr') keys.push(S.kind === 'fermeture' ? 'wedge' : 'gap');
  if (S.ghost && fantomeDispo() && !keys.includes('ghost')) keys.push('ghost');
  if (!S.ghost || !fantomeDispo()) keys = keys.filter((k) => k !== 'ghost');
  if (!PLAN.D) keys = keys.filter((k) => k !== 'truth');
  if (st.id === 'cas' && PLAN.reel) keys.unshift('reperes');
  if (st.coupe && !PLAN.osteoPossible) keys = keys.filter((k) => !['hinge', 'cut', 'wedge', 'gap', 'pin', 'face', 'bis'].includes(k));
  if (st.id === 'guide' && guidePret()) {
    const I = S.guide.info || {}, verrou = !!I.verrou_reduction?.construit, coin = !!I.guide_coupe?.piece_du_coin;
    keys = S.guide.vue === 'reduction' ? (verrou ? ['gprox', 'gdist', 'gverrou', 'pin'] : ['gred', 'pin'])
      : ['gprox', 'gdist', ...(coin ? ['gcoin'] : []), 'gponts', 'pin', 'cut'];
  }
  L.replaceChildren(...keys.map((k) => {
    const [c, t, forme] = LEG[k];
    const txt = k === 'mech' ? (PLAN.bone === 'tibia' ? 'Axe mécanique (os entier)' : 'Axe anatomique (milieux de la diaphyse)') : k === 'plan' ? (st.plan2D === 'S' ? 'Plan sagittal' : 'Plan frontal') : k === 'ghost' && PLAN.reel ? 'Os avant déformité (transparence)' : t;
    const col = c.startsWith('--') ? `var(${c})` : c;
    return h('div', {}, h('i', { class: forme || '', style: { background: col, color: col } }), txt);
  }));
  L.hidden = !keys.length;
}
function renderContext() {
  if (!PLAN) { $('#ctx').replaceChildren(); return; }
  const v = PLAN.validation, st = ETAPES[S.step], nomOs = PLAN.bone === 'tibia' ? 'Tibia' : 'Fémur';
  let pills;
  if (PLAN.reel) {
    const R = PLAN.reel;
    pills = [
      h('span', { class: 'glass pill' }, `${nomOs} ${R.cote}${R.miroir ? ' (miroir)' : ''} · ${nomSerie(R.serie)}`),
      st.torsion ? h('span', { class: 'glass pill' }, `torsion τ ${deg(S.tor.tau, 0)} · rotation sur la table ρ ${deg(S.tor.rho, 0)}`)
        : h('span', { class: 'glass pill' }, PLAN.D ? `test : ${PLAN.frontal} ${deg(PLAN.thetaF, 0)}${PLAN.sagittal === 'aucun' ? '' : ` + ${PLAN.sagittal} ${deg(PLAN.thetaS, 0)}`} · θ vrai ${deg(v.thetaVrai)}` : `θ entre les axes ${deg(PLAN.theta)}`),
      st.torsion ? null : h('span', { class: `glass pill ${PLAN.anomalies.length ? 'bad' : 'ok'}` }, PLAN.anomalies.length ? `${PLAN.anomalies.length} angle(s) hors normes` : 'angles dans les normes'),
    ];
  } else {
    const comp = `${PLAN.frontal} ${deg(PLAN.thetaF, 0)}${PLAN.sagittal === 'aucun' ? '' : ` + ${PLAN.sagittal} ${deg(PLAN.thetaS, 0)}`}`;
    pills = [
      st.torsion
        ? h('span', { class: 'glass pill' }, `${nomOs} sain · torsion τ ${deg(S.tor.tau, 0)} · rotation sur la table ρ ${deg(S.tor.rho, 0)}`)
        : h('span', { class: 'glass pill' }, `${nomOs} droit · ${comp} · θ vrai ${deg(v.thetaVrai)}`),
      st.torsion ? null : h('span', { class: 'glass pill' }, `apex à ${fr(PLAN.niveau * 100, 0)} % (${mm(v.niveauApex, 0)})`),
    ];
  }
  $('#ctx').replaceChildren(...pills.filter(Boolean));
}
function renderTimeline() {
  const st = ETAPES[S.step];
  $('#timeline').hidden = !st.anime || !PLAN || !PLAN.osteoPossible;
  if ($('#timeline').hidden) return;
  $('#sim-progress').value = Math.round(S.progress * 1000);
  $('#sim-pct').textContent = `${Math.round(S.progress * 100)} %`;
  const lab = S.kind === 'fermeture' ? ['Coin retiré', 'Fermeture', 'Axes réalignés'] : ['Trait de scie', 'Ouverture', 'Axes réalignés'];
  $('#tl-steps').replaceChildren(...lab.map((t) => h('span', {}, t)));
  $('#ico-play').hidden = S.playing; $('#ico-pause').hidden = !S.playing;
  $('#sim-play').setAttribute('aria-label', S.playing ? 'Mettre en pause' : 'Lancer la correction');
}

// ------------------------------------------------------------ navigation --
function allerA(i, cadrer = true) {
  if (!PLAN) return;
  i = clamp(i, 0, ETAPES.length - 1);
  const change = i !== S.step;
  S.step = i;
  S.playing = false;
  if (change) S.ghost = !!ETAPES[i].fantome;
  if (ETAPES[i].anime && change) S.progress = 0;
  refresh();
  if (cadrer) setView(ETAPES[i].vue);
}
function choisirCas(id) {
  if (S.cas === id) return;
  const ancienOs = casCourant().bone;
  S.cas = casDe(id).id; S.progress = 0; S.playing = false;
  S.preset = '';                                          // choix manuel : plus de préréglage
  replan();
  renderCases();
  renderAdjust();
  refresh();
  if (casCourant().bone !== ancienOs || ETAPES[S.step].vue.dir === 'aca') setView(ETAPES[S.step].vue);
}

// ------------------------------------------------------------ caméra --
let orthoR = 120, tween = null, currentDir = 'iso';
// direction de la caméra (depuis la cible) et haut de l'écran
const DIRS = {
  cc: { d: [0, 0, -1] },                       // crânio-caudale : depuis crânial, médial à droite
  ml: { d: [1, 0, 0] },                        // médio-latérale : depuis latéral, crânial à droite
  iso: { d: [0.62, 0.26, -0.74] },             // 3/4 crânio-latéral
  haut: { d: [0.5, 0.62, -0.6] },              // 3/4 plongeant depuis proximal (plan transverse lisible)
  ax: { d: [0, 1, 0], up: [0, 0, -1] },        // axiale : depuis proximal, crânial en haut
};
function dirVue(dir) {
  if (dir === 'aca') {                         // le long de l'ACA, du côté crânial : on voit l'angle vrai θ
    const n = PLAN.bis.n;
    return { d: n[2] <= 0 ? n : V.neg(n) };
  }
  if (dir === 'face') {                        // trois quarts depuis la face d'appui du guide : guides vus de dessus
    const O = PLAN.osteo[S.kind];
    if (O) return { d: V.norm(V.add(V.mul(O.face, 0.8), V.mul(V.norm(V.cross([0, 1, 0], O.face)), 0.45))) };
    return DIRS.iso;
  }
  return DIRS[dir];
}
function setView(spec, animate = true) {
  if (!PLAN) return;
  if (spec.focus === 'cora' && !PLAN.coraDansOs) spec = { ...spec, focus: 'os' };   // pas de CORA dans l'os : on cadre l'os
  currentDir = spec.dir;
  for (const b of $$('[data-view]')) b.setAttribute('aria-pressed', String(b.dataset.view === spec.dir));
  const w = viewportEl.clientWidth || 1, hpx = viewportEl.clientHeight || 1, a = w / hpx;
  // place réellement libre : sous les pastilles du haut (≈ 56 px) et au-dessus de la navigation du bas
  const bas = ($('.ov-bc').offsetHeight || 60) + 24, haut = 56;
  const libre = Math.max(120, hpx - bas - haut);
  const D = dirVue(spec.dir);
  const d = new THREE.Vector3(...D.d).normalize();
  const up = new THREE.Vector3(...(D.up || [0, 1, 0]));
  const right = new THREE.Vector3().crossVectors(up, d).normalize(), upS = new THREE.Vector3().crossVectors(d, right).normalize();
  let center, halfH, halfW;
  if (spec.focus === 'cora') {
    center = new THREE.Vector3(...PLAN.coraC);
    // os segmenté : les distances sont à l'échelle de l'os (le modèle fait ≈ 200 mm)
    halfH = halfW = spec.r * (PLAN.reel ? PLAN.validation.longueurOs / 200 : 1);
  } else {
    const { lo, hi } = PLAN.box;
    center = new THREE.Vector3((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2);
    const size = new THREE.Vector3(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]);
    const ext = (ax) => 0.5 * (Math.abs(ax.x) * size.x + Math.abs(ax.y) * size.y + Math.abs(ax.z) * size.z);
    halfH = ext(upS) + 14; halfW = ext(right) + 40;     // marge pour les étiquettes latérales
    if (spec.dir === 'ax') { halfH = ext(upS) + 18; halfW = ext(right) + 18; }
  }
  const r = Math.max(halfH * hpx / libre, halfW / a);
  // décale la cible pour centrer l'os dans la zone libre
  const shift = ((bas - haut) / 2) * (2 * r / hpx);
  const target = center.clone().addScaledVector(upS, -shift);
  const to = { pos: target.clone().addScaledVector(d, 800), target, up: upS.clone(), r };
  demanderImage();
  if (!animate) { applyCam(to); return; }
  tween = { t0: performance.now(), dur: 750, from: { pos: camera.position.clone(), target: controls.target.clone(), up: camera.up.clone(), r: orthoR / camera.zoom }, to };
}
function applyCam(c) {
  camera.position.copy(c.pos); camera.up.copy(c.up); camera.lookAt(c.target);
  controls.target.copy(c.target);
  orthoR = c.r; camera.zoom = 1;
  updateOrtho();
}
function stepTween(now) {
  const k = clamp((now - tween.t0) / tween.dur, 0, 1);
  const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
  const { from, to } = tween;
  applyCam({ pos: from.pos.clone().lerp(to.pos, e), target: from.target.clone().lerp(to.target, e), up: from.up.clone().lerp(to.up, e).normalize(), r: from.r + (to.r - from.r) * e });
  if (k >= 1) tween = null;
}
function updateOrtho() {
  const w = viewportEl.clientWidth || 1, hpx = viewportEl.clientHeight || 1, a = w / hpx;
  Object.assign(camera, { left: -orthoR * a, right: orthoR * a, top: orthoR, bottom: -orthoR });
  camera.updateProjectionMatrix();
}
function resize() {
  const w = viewportEl.clientWidth, hpx = viewportEl.clientHeight;
  if (!w || !hpx) return;
  renderer.setSize(w, hpx, false);
  labelRenderer.setSize(w, hpx);
  updateOrtho();
  for (const m of lineMats) m.resolution.set(w, hpx);
  demanderImage();
}

// ------------------------------------------------------------ animation --
let lastT = performance.now(), lastUI = 0;
function majCorrection(force) {
  const e = applyCorrection(PLAN, S.kind, S.progress);
  const now = performance.now();
  if (force || now - lastUI > 90) {
    lastUI = now;
    renderTimeline();
    const live = $('#live-angle'), pins = $('#live-pins');
    if (live) live.textContent = deg(PLAN.theta * (1 - e), 1);
    if (pins && PLAN.osteo[S.kind]) pins.textContent = deg(PLAN.osteo[S.kind].angleBroches * (1 - e), 1);
  }
}
// Rendu À LA DEMANDE : une image seulement quand quelque chose change (caméra, transition de vue, animation de la
// correction, refresh(), interaction, message de la page d'accueil), au lieu de 60 images par seconde en permanence ;
// au repos, la 3D et ses étiquettes ne coûtent plus rien (processeur graphique, ventilateur, batterie).
let imageDemandee = false;
function demanderImage() {
  if (imageDemandee) return;
  imageDemandee = true;
  requestAnimationFrame(animate);
}
function animate(t) {
  imageDemandee = false;
  const dt = Math.min(0.05, (t - lastT) / 1000);
  lastT = t;
  if (tween) stepTween(t);
  controls.update();                            // déclenche « change » (donc une autre image) tant que la vue bouge
  if (S.playing && PLAN && PLAN.osteoPossible && ETAPES[S.step].anime) {
    S.progress = Math.min(1, S.progress + dt / 4.5);       // correction complète en 4,5 s
    if (S.progress >= 1) S.playing = false;
    majCorrection(!S.playing);
  }
  placeLights();
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
  if (tween || S.playing) demanderImage();
}
function togglePlay() {
  if (!PLAN || !PLAN.osteoPossible || !ETAPES[S.step].anime) return;
  if (S.progress >= 1) S.progress = 0;
  S.playing = !S.playing;
  renderTimeline();
  demanderImage();
}

// ------------------------------------------------------------ thème --
function appliquerTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme; else delete document.documentElement.dataset.theme;
  $('meta[name="color-scheme"]').content = theme || 'light dark';
  readColors(); refresh();
}
function toggleTheme() {
  const sysLight = matchMedia('(prefers-color-scheme: light)').matches;
  const next = isLight() ? 'dark' : 'light';
  const pinned = (next === 'light') === sysLight ? null : next;     // revenir au réglage système si identique
  try { if (pinned) localStorage.setItem('cora3d-simple-theme', pinned); else localStorage.removeItem('cora3d-simple-theme'); } catch (e) { /* stockage indisponible */ }
  appliquerTheme(pinned);
}

// ------------------------------------------------------------ aide --
function renderHelp() {
  const b = $('#help-body');
  if (b.childElementCount) return;
  const li = (html) => h('li', { html });
  b.append(
    h('h3', {}, 'Ce que fait l\'application'),
    h('p', {}, 'Deux sources, même méthode. « Os segmenté (CT) » : le fémur ou le tibia segmenté sur le scanner (onglet 1 de CT-CORA3D), avec ses repères anatomiques placés automatiquement ; on peut l\'analyser tel quel ou lui imposer une déformité de test. « Os fictif (modèle) » : un os synthétique (fémur ou tibia droit, modèle procédural calibré sur la littérature) auquel on impose une déformité connue (varus ou valgus, seul ou associé à un procurvatum ou un recurvatum).'),
    h('p', {}, 'On suit ensuite, étape par étape, la planification par la méthode CORA de Paley dans les deux vues puis en 3D, jusqu\'à la prescription du guide de coupe. Une dernière étape explique pourquoi la torsion se mesure en 3D.'),
    h('h3', {}, 'La méthode en bref'),
    h('ol', {},
      li('Vue de face puis vue de profil : lignes d\'orientation articulaire (JOL) et angles articulaires.'),
      li('Axe de chaque segment, construit depuis ses JOL avec l\'orientation <b>normale</b> : os sain (membre controlatéral) ou valeurs normales publiées.'),
      li('CORA de chaque vue : composantes F (frontale) et S (sagittale). Mêmes niveaux = une seule angulation oblique.'),
      li('En 3D : <b>angle vrai θ</b> (tan²θ = tan²F + tan²S), plan de la déformité (φ), plan bissecteur, <b>ACA oblique</b> (orientation ψ).'),
      li('<b>Règle 1</b> : ostéotomie au CORA, coin de fermeture (charnière concave, 2 traits ⊥ aux axes) ou d\'ouverture (charnière convexe, 1 trait bissecteur). Même angle θ dans les deux cas.'),
      li('Correction (avec dérotation si la torsion sort de la normale), contrôle dans les deux plans, puis prescription : fentes, charnière, broches de réduction (2 + 2, 1 + 1 ou 1 + 2), parallèles après correction.'),
      li('<b>Guides imprimables</b> (étape 12, application CT-CORA3D) : guide de coupe moulé sur l\'os (moitiés reliées par des ponts sécables, butée de profondeur, verrou de réduction intégré « 2 en 1 » ou guide de réduction séparé), construit et contrôlé par <code>etape7_guide.py</code> ; STL à télécharger.')),
    h('h3', {}, 'Stratégie chirurgicale (panneau « 2 · Stratégie et guide »)'),
    h('ul', {},
      li('<b>Préréglages cliniques</b> : 17 déformités prêtes à l\'emploi, avec leur contexte et leur référence.'),
      li('<b>Où se pose le guide</b> : la lame entre toujours du côté opposé à la charnière (face convexe en fermeture, concave en ouverture) ; le guide se pose sur cette face, dans un abord usuel. Si c\'est impossible à moins de 60°, ce coin est déclaré non réalisable par un abord usuel et l\'autre est recommandé.'),
      li('<b>Ouverture ou fermeture</b> : « Auto » suit la recommandation (★), décidée par le premier critère qui départage : accès, charnière conservée, règle 1, coin assez épais, ouverture ≤ 40 % de la largeur, longueur, puis stabilité.'),
      li('<b>Niveau du trait (z)</b> : règle 1 de Paley par défaut (coupe au CORA) ; le curseur translate le plan de coupe le long de l\'os (règle 2 : translation chiffrée). <b>Profondeur de la charnière (y)</b> : 2 mm dans la corticale par défaut (pont d\'os qui plie) ; plus profond, ostéotomie complète.'),
      li('<b>Contraintes biologiques</b> au niveau du trait : cartilage, tubérosité tibiale, épicondyles, physes (chien en croissance), place pour la fixation, consolidation, structures de l\'abord.'),
      li('<b>Guide générique</b> : 21 dimensions de conception modifiables (panneau « Guide générique : dimensions ») ; les autres découlent de l\'os. Étape 12 : guide 3D et <b>plans 2D</b> (générique et coté).')),
    h('h3', {}, 'Os segmenté : repères et références'),
    h('ul', {},
      li('Un dossier DICOM = un fémur <b>ou</b> un tibia : l\'onglet CORA prend l\'os complet détecté dans la série de l\'onglet 1 (les os coupés par le champ du scanner sont ignorés).'),
      li('Les repères (éminence, plateaux, cochlée, malléoles ; tête fémorale, condyles, trochlée…) sont placés par <code>etape6_reperes.py</code> : repère de l\'os, côté reconnu par l\'anatomie (un membre gauche est traité en miroir comme un droit).'),
      li('<b>Valeurs normales</b> : uniquement des valeurs publiées : travaux de l\'équipe Vezzoni (par défaut, complétés par la littérature), littérature, ou valeurs par race (Tomlinson 2007, Wilke 2002 pour le lévrier) ; toujours corrigées de l\'écart de définition des repères automatiques.'),
      li('<b>Os avant déformité</b> (avec une déformité de test) : l\'os réel non déformé joue le rôle du membre controlatéral ; la méthode doit retrouver exactement la déformité imposée.')),
    h('h3', {}, 'Conventions'),
    h('ul', {},
      li('Membre droit (un gauche est mis en miroir). Repère de l\'os : X latéral, Y proximal, Z caudal (mm).'),
      li('<b>Varus</b> : segment distal dévié vers médial. <b>Valgus</b> : vers latéral. <b>Procurvatum</b> : apex crânial (distal vers caudal). <b>Recurvatum</b> : apex caudal.'),
      li('Vue de face (CrCd) : depuis crânial, médial à droite. Vue de profil (ML) : depuis latéral, crânial à droite. Vue axiale (Ax) : depuis proximal.'),
      li('« Anormal » = écart à la référence de plus de 2 écarts-types publiés.')),
    h('h3', {}, 'Commandes'),
    h('ul', {},
      li('<b>← →</b> : étape précédente / suivante · <b>Espace</b> : lecture de la correction (étape 10).'),
      li('Clic-glisser : tourner · molette : zoomer · clic droit-glisser : déplacer · bouton de cadrage : revenir à la vue de l\'étape.')),
    h('h3', {}, 'Références'),
    h('ul', {}, Object.keys(REFS).map((k) => h('li', {}, srcLink(k)))),
    h('h3', {}, 'Limites'),
    h('p', {}, 'Os rigide, un seul apex (comme CORA 3D), tissus mous non modélisés ; pas d\'ostéotomie en dôme ; fémur : déformités distales seulement (apex entre 62 et 82 % de la longueur ; coxa vara ou valga et antéversion du col : autre méthode, hors champ). Os fictif : repères exacts. Os segmenté : repères automatiques (≈ 1 mm pour les repères robustes sur l\'os du modèle ; les angles sagittaux, mesurés sur des lignes articulaires de 20 à 30 mm, sont sensibles à quelques degrés près ; antéversion fémorale indicative). Guides : prototypes de recherche, non validés cliniquement (imprimer des coupons de réglage des jeux).'),
  );
}

// ------------------------------------------------------------ événements --
function wire() {
  $('#prev').addEventListener('click', () => allerA(S.step - 1));
  $('#next').addEventListener('click', () => allerA(S.step + 1));
  for (const b of $$('[data-view]')) b.addEventListener('click', () => setView({ ...ETAPES[S.step].vue, dir: b.dataset.view, focus: b.dataset.view === 'ax' ? 'os' : ETAPES[S.step].vue.focus }));
  $('#v-step').addEventListener('click', () => setView(ETAPES[S.step].vue));
  $('#v-ghost').addEventListener('click', () => { S.ghost = !S.ghost; refresh(); });
  $('#btn-theme').addEventListener('click', toggleTheme);
  $('#btn-help').addEventListener('click', () => { renderHelp(); $('#dlg-help').showModal(); });
  for (const b of $$('#source button')) b.addEventListener('click', () => choisirSource(b.dataset.source));
  const dlg = $('#dlg-help');
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  $('[data-close]', dlg).addEventListener('click', () => dlg.close());
  $('#sim-play').addEventListener('click', togglePlay);
  $('#sim-progress').addEventListener('input', (e) => { if (!PLAN?.osteoPossible) return; S.progress = +e.target.value / 1000; S.playing = false; majCorrection(true); });
  window.addEventListener('keydown', (e) => {
    if (e.target.closest('input, textarea, select, dialog') || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); allerA(S.step + 1); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); allerA(S.step - 1); }
    else if (e.key === ' ' && ETAPES[S.step].anime && !e.target.closest('button')) { e.preventDefault(); togglePlay(); }
  });
  new ResizeObserver(() => resize()).observe(viewportEl);
  controls.addEventListener('change', demanderImage);
  // filet de sécurité du rendu à la demande : toute interaction ou réponse peut changer la scène → une image
  for (const ev of ['pointerdown', 'pointerup', 'wheel', 'keydown', 'input', 'change', 'click']) document.addEventListener(ev, demanderImage, { capture: true, passive: true });
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { readColors(); refresh(); });
  // messages de la page à deux onglets (CT-CORA3D)
  window.addEventListener('message', (e) => {
    demanderImage();
    const m = e.data || {};
    if (m.type === 'theme') appliquerTheme(m.theme);
    else if (m.type === 'ouvrir-os' && m.serie && m.os) ouvrirOs(m.serie, m.os);
    else if (m.type === 'actualiser') actualiserCas(true);                     // une segmentation vient de finir
    else if (m.type === 'visible') {                                           // l'onglet CORA redevient visible
      resize(); if (PLAN) setView(ETAPES[S.step].vue, false);
      if (S.reel.serveur && S.guide.etat !== 'calcul') actualiserCas(true);     // suit la série de l'onglet 1
    }
  });
}

async function init() {
  const prog = (f, txt) => { $('#loading-bar').style.width = `${Math.round(f * 100)}%`; if (txt) $('#loading-text').textContent = txt; };
  try {
    if (INTEGRE) document.body.classList.add('integre');
    DATA_F = await loadBones(prog);
    // le cœur reçoit aussi la carte du cartilage (zones articulaires à éviter par les traits et les broches)
    MODEL_F = { meta: DATA_F.meta, bones: Object.fromEntries(Object.entries(DATA_F.bones).map(([k, b]) => [k, { pos: b.pos, idx: b.idx, cart: b.cart }])) };
    GABARIT = gabaritFemur(MODEL_F);
    MODEL = MODEL_F; DATA = DATA_F;
    prog(0.8, 'Construction de la scène…');
    await new Promise((r) => setTimeout(r, 0));
    readColors();
    initGroups();
    wire();
    resize();
    // source au démarrage : os segmenté si le serveur en propose un, sinon os fictif
    let pref = null;
    try { pref = localStorage.getItem('ct-cora3d-source'); } catch (e) { /* rien */ }
    await actualiserCas(false);
    const cas = S.reel.cas;
    if (S.reel.serveur && pref !== 'fictif' && cas?.cible) { prog(0.9, 'Chargement de l\'os détecté…'); await ouvrirOs(cas.serie, cas.cible, false); }
    else { S.source = 'fictif'; replan(); }
    renderSource();
    renderCases();
    renderAdjust();
    renderGuideParams();
    refresh();
    if (PLAN) setView(ETAPES[0].vue, false);
    $('#loading').classList.add('done');
    demanderImage();
  } catch (err) {
    console.error(err);
    $('#loading-text').textContent = `Impossible de démarrer la vue 3D : ${err.message}. Vérifiez que WebGL est activé et que le navigateur est à jour (Chrome, Edge, Safari ou Firefox récents).`;
  }
}
// poignée de diagnostic dans la console du navigateur
window.CORA3D = { S, get PLAN() { return PLAN; }, get TORS() { return TORS; }, allerA, choisirCas, choisirSource, ouvrirOs, setView, camera, controls, construireGuide, replanUI, appliquerPreset };
init();
