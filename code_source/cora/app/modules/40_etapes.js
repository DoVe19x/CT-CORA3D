// =============================================================================
// 40 — les 13 étapes de la planification : tracés 3D, cadrage, légende, explication
// =============================================================================
const NOMS = {
  mMPTA: 'mMPTA (médial proximal)', mMDTA: 'mMDTA (médial distal)', valgusTib: 'Valgus tibial (JOL / JOL)',
  mCaPTA: 'mCaPTA (caudal proximal)', mCrDTA: 'mCrDTA (crânial distal)',
  aLPFA: 'aLPFA (latéral proximal)', aLDFA: 'aLDFA (latéral distal)', varusFem: 'Angle de varus fémoral',
  aCdDFA: 'aCdDFA (caudal distal)',
  MPRA: 'MPRA (médial proximal)', LDRA: 'LDRA (latéral distal)', CrPRA: 'CrPRA (crânial proximal)', CdDRA: 'CdDRA (caudal distal)',
  procurvatum: 'Procurvatum (axes 20-40 / 60-80 %, de profil)', angulation_frontale: 'Valgus (axes 20-40 / 60-80 %, de face)',
};
const LEG = {
  plan: ['--accent', 'Plan de la vue'], ghost: ['#8fb4d0', 'Os sain (transparence)'], reperes: ['--c-joint', 'Repères automatiques', 'dot'],
  joint: ['--c-joint', 'Lignes articulaires (JOL)'], mech: ['--c-mech', null, 'dash'],
  prox: ['--c-prox', 'Axe du segment proximal'], dist: ['--c-dist', 'Axe du segment distal'],
  cora: ['--c-cora', 'CORA', 'dot'], truth: ['--fg-2', 'Apex imposé (vérité terrain)', 'dot'],
  oblique: ['--c-plane', 'Plan de la déformité (oblique)'],
  bis: ['--c-bis', 'Plan bissecteur transverse'], aca: ['--c-cora', 'ACA (axe de correction)', 'dash'],
  hinge: ['--c-hinge', 'Charnière', 'dot'], cut: ['--c-cut', 'Traits de scie'],
  wedge: ['#ff5b61', 'Coin d\'os retiré'], gap: ['#ffa640', 'Espace d\'ouverture (à combler)'],
  pin: ['--c-pin', 'Broches de réduction'], face: ['--c-ok', 'Face d\'appui du guide'],
  trans: ['--c-trans', 'Axes transverses (torsion 3D)'], width: ['--c-cut', 'Largeur projetée (radiographie)'],
  gprox: ['#2f6db5', 'Guide de coupe : moitié proximale'], gdist: ['#23a08f', 'Guide de coupe : moitié distale'],
  gponts: ['#e8822b', 'Ponts sécables'], gred: ['#8e44ad', 'Guide de réduction (os corrigé)'],
};

// ------------------------------------------------------------ petits outils --
const para = (html) => h('p', { html });
const boite = (cls, titre, ...kids) => h('div', { class: 'box ' + cls }, titre ? h('h3', {}, titre) : null, ...kids);
const ext = (a, b, e) => { const d = P2.norm(P2.sub(b, a)); return [P2.sub(a, P2.mul(d, e)), P2.add(b, P2.mul(d, e))]; };
const tAtY = (p, d, y) => (y - p[1]) / d[1];          // paramètre de la droite (p, d) à la hauteur y
const leOs = (P) => ({ tibia: 'le tibia', radius: 'le radius' }[P.bone] || 'le fémur');
const LeOs = (P) => ({ tibia: 'Tibia', radius: 'Radius' }[P.bone] || 'Fémur');
// os segmenté (CT) ou modèle synthétique ; référence des « valeurs normales »
const nomRef = (P) => (P.reference === 'normales' ? `valeurs normales publiées (${P.reel ? nomPreset() : 'littérature'})${P.bone === 'radius' ? '' : ', converties dans la définition des repères automatiques'}`
  : P.reel ? 'os avant la déformité de test (rôle du membre controlatéral sain)' : 'os sain du modèle (rôle du membre controlatéral)');
const colRef = (P) => (P.reference === 'normales' ? 'Normale' : P.reel ? 'Avant déf.' : 'Os sain');
const ecartRef = (P, k, x = P.mesures.pre[k]) => x - P.mesures.normal[k];
const anormal = (P, k, x = P.mesures.pre[k]) => Math.abs(ecartRef(P, k, x)) > 2 * P.sdRef[k];
const tousNormaux = (P, cles) => cles.every((k) => !anormal(P, k));
// liste lisible des angles hors normes parmi `cles`, avec leur écart
const horsNormes = (P, cles) => cles.filter((k) => anormal(P, k)).map((k) => `${court(k)} ${degS(ecartRef(P, k))}`).join(', ');
const depuis = (P) => ({ tibia: 'du plateau tibial', radius: 'du sommet de la tête radiale' }[P.bone] || 'du sommet de la tête fémorale');
const kindNom = { fermeture: 'coin de fermeture', ouverture: 'coin d\'ouverture' };
// direction anatomique d'un vecteur ⊥ à l'os (membre droit : +X latéral, −Z crânial)
function sens3(v, fem = false) {
  const x = v[0], z = v[2], ax = Math.abs(x), az = Math.abs(z), e = fem ? 'e' : '';
  const ml = (x > 0 ? 'latéral' : 'médial') + e, cc = (z < 0 ? 'crânial' : 'caudal') + e;
  if (az < 0.3 * ax) return ml;
  if (ax < 0.3 * az) return cc;
  return (z < 0 ? 'crânio-' : 'caudo-') + ml;
}
const compF = (P) => `${deg(Math.abs(P.Fm))} de ${P.typeF}`;
const compS = (P) => (P.typeS === 'aucun' ? 'pas de composante sagittale' : `${deg(Math.abs(P.Sm))} de ${P.typeS}`);
function statut(P, k, x) {
  const n = P.mesures.normal[k], tol = 2 * P.sdRef[k];
  return Math.abs(x - n) <= tol ? h('span', { class: 'tag ok' }, 'normal') : h('span', { class: 'tag bad' }, 'anormal');
}
// tableau : mesure | ce cas | os sain (modèle) | littérature
function tableMesures(P, valeurs, titre, cles, colonne = 'Ce cas') {
  const L = P.mesures.litt, N = P.mesures.normal;
  return h('table', { class: 't' }, h('caption', {}, titre),
    h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Mesure'), h('th', { scope: 'col' }, colonne), h('th', { scope: 'col' }, colRef(P)), h('th', { scope: 'col' }, 'Littérature'))),
    h('tbody', {}, cles.map((k) => h('tr', {},
      h('td', {}, NOMS[k]),
      h('td', { class: 'hi' }, deg(valeurs[k]), statut(P, k, valeurs[k])),
      h('td', {}, deg(N[k])),
      h('td', {}, `${fr(L[k].m)} ± ${fr(L[k].sd)}°`)))));
}
const sources = (...keys) => h('p', { class: 'src' }, 'Sources : ', ...keys.flatMap((k, i) => [i ? ' · ' : '', srcLink(k)]));
// curseur avec sa valeur affichée (réglages du cas, étape torsion)
function curseur(id, label, min, max, step, val, affiche, onInput, gauche, droite, disabled = false) {
  const out = h('output', { for: id, id: id + '-v' }, affiche(val));
  const inp = h('input', { type: 'range', id, min, max, step, value: val, disabled });
  inp.addEventListener('input', () => { out.textContent = affiche(+inp.value); onInput(+inp.value); });
  return h('div', { class: 'row' + (disabled ? ' off' : '') }, h('label', { for: id }, label), out, inp, h('div', { class: 'sub' }, h('span', {}, gauche), h('span', {}, droite)));
}
const lignes = (rows) => h('table', { class: 't' }, h('tbody', {}, rows.map(([a, b]) => h('tr', {}, h('td', {}, a), h('td', { class: 'hi' }, b)))));

// Angles articulaires dessinés dans chaque vue : JOL (paire de repères), vecteur de mesure, sens de l'axe
// (+1 : axe vers distal, −1 : vers proximal). Mêmes définitions que mesurer() dans le cœur de calcul.
const SPEC = {
  tibia: {
    F: { prox: { cle: 'mMPTA', a: ['plat_lat', 'plat_med'], s: 1 }, dist: { cle: 'mMDTA', a: ['groove_lat', 'groove_med'], s: -1 } },
    S: { prox: { cle: 'mCaPTA', a: ['plat_cran', 'plat_caud'], s: 1 }, dist: { cle: 'mCrDTA', a: ['dist_caud', 'dist_cran'], s: -1 } },
  },
  femur: {
    F: { prox: { cle: 'aLPFA', a: ['head_center', 'gt_tip'], s: 1 }, dist: { cle: 'aLDFA', a: ['cond_med_dist', 'cond_lat_dist'], s: -1 } },
    S: { prox: null, dist: { cle: 'aCdDFA', a: ['troch_dist', 'caud_mid'], s: -1 } },
  },
  // radius (Fox 2006, Kwon 2022) : MPRA et LDRA de face avec l'axe 25 → 75 % ; CrPRA (axe 20 → 40 %) et CdDRA (axe
  // 60 → 80 %) de profil. Les repères portent les noms du tibia (alias, cora_simple.ALIAS_RADIUS).
  radius: {
    F: { prox: { cle: 'MPRA', a: ['plat_lat', 'plat_med'], s: 1 }, dist: { cle: 'LDRA', a: ['groove_med', 'groove_lat'], s: -1 } },
    S: { prox: { cle: 'CrPRA', a: ['plat_caud', 'plat_cran'], s: 1 }, dist: { cle: 'CdDRA', a: ['dist_cran', 'dist_caud'], s: -1 } },
  },
};
const court = (k) => NOMS[k].split(' ')[0];

// ------------------------------------------------------------ tracés --
function bornes(P) { const a = P.ref.ax; return { top: a.y_top + 8, bot: a.y_bot - 8 }; }
function dessinJOL(P, k, opacity = 1) {
  const c = COL.joint, to2 = VUE[k].to2;
  for (const [seg, calque] of [['prox', OV.base], ['dist', OV.dist]]) {
    const j = P.jol[k][seg];
    if (!j) continue;
    calque.line(ext(to2(j[0]), to2(j[1]), 10), c, 2.6, { opacity });
    if (opacity === 1) for (const p of j) calque.dot(to2(p), 1.3, c);
  }
}
function etiquettesJOL(P, k) {
  const to2 = VUE[k].to2;
  for (const [seg, calque, dy] of [['prox', OV.base, 6], ['dist', OV.dist, -6]]) {
    const j = P.jol[k][seg];
    if (!j) continue;
    const a = to2(j[0]), b = to2(j[1]), loin = a[0] > b[0] ? a : b;
    calque.label(`JOL ${seg === 'prox' ? 'proximale' : 'distale'}`, P2.add(loin, [24, dy]), 'joint');
  }
}
function dessinOrientation(P, k) {
  const b = P.ref.ax, pos = P.pos[P.bone], c = k === 'S' ? 2 : 0;
  let lo = Infinity, hi = -Infinity;
  for (let i = c; i < pos.length; i += 3) { lo = Math.min(lo, pos[i]); hi = Math.max(hi, pos[i]); }
  const ym = (b.y_top + b.y_bot) / 2;
  OV.base.label(k === 'S' ? 'caudal' : 'latéral', [hi + 18, ym], 'orient');
  OV.base.label(k === 'S' ? 'crânial' : 'médial', [lo - 18, ym], 'orient');
  OV.base.label('proximal', [(lo + hi) / 2, b.y_top + 16], 'orient');
  OV.base.label('distal', [(lo + hi) / 2, b.y_bot - 16], 'orient');
}
function planVue(P, k) {
  const b = P.ref.ax, c = P.coraC;
  const [u, w] = k === 'S' ? [[0, 0, 1], [0, 1, 0]] : [[1, 0, 0], [0, 1, 0]];
  const ctr = k === 'S' ? [c[0], (b.y_top + b.y_bot) / 2, c[2]] : [c[0], (b.y_top + b.y_bot) / 2, c[2]];
  OV.base.rect(ctr, u, w, 48, (b.y_top - b.y_bot) / 2 + 14, cssColor('--accent'), 0.07);
}
// axe d'un segment projeté dans la vue k ; jusqu'au CORA de la vue puis en pointillés (si coupe)
function dessinAxe(P, k, seg, coupe, opts = {}) {
  const axe = seg === 'prox' ? P.axeProx : P.axeDist, calque = seg === 'prox' ? OV.base : OV.dist, col = seg === 'prox' ? COL.prox : COL.dist;
  const to2 = VUE[k].to2, p = to2(axe.p), d = P2.norm(to2(axe.d)), B = bornes(P);
  const tTop = tAtY(p, d, B.top), tBot = tAtY(p, d, B.bot);
  const C2 = P.proj[k].cora;
  const ok = coupe && C2 && Math.abs(P.proj[k].angle) >= 0.5 && C2[1] < B.top && C2[1] > B.bot;
  if (!ok) return calque.ray(p, d, tTop, tBot, col, 3, opts);
  const tc = P2.dot(P2.sub(C2, p), d);
  const [plein, tiret] = seg === 'prox' ? [tTop, tBot] : [tBot, tTop];
  calque.ray(p, d, plein, tc, col, 3, opts);
  calque.ray(p, d, tc, tiret, col, 2, { dashed: true, dashSize: 5, gapSize: 4, opacity: 0.85 });
}
// arc d'un angle articulaire (vue k, segment prox / dist) entre la JOL et l'axe donné ; renvoie la valeur
function arcArticulaire(P, k, seg, axe, Lset, calque, couleur, suffixe = '', valeur = null) {
  const sp = SPEC[P.bone][k][seg];
  if (!sp) return null;
  const to2 = VUE[k].to2, J = JOL[P.bone][k][seg];
  const A = to2(Lset[J[0]]), B = to2(Lset[J[1]]);
  const p = to2(axe.p), d = P2.norm(to2(axe.d));
  const X = P2.intersect(p, d, A, P2.sub(B, A));
  if (!X) return null;
  const va = P2.sub(to2(Lset[sp.a[1]]), to2(Lset[sp.a[0]])), vb = P2.mul(d, sp.s);
  const v = valeur ?? P2.angU(va, vb);
  const cls = couleur === COL.joint ? 'joint' : couleur === COL.prox ? 'prox' : 'dist';
  calque.arc(X, va, vb, 13, couleur, 2, `${court(sp.cle)} ${deg(v)}${suffixe}`, cls);
  return v;
}
// axe « de diagnostic » de l'os entier : mécanique (tibia) ou anatomique (fémur, radius)
function dessinAxeGlobal(P, k) {
  const to2 = VUE[k].to2, B = bornes(P);
  if (P.bone === 'radius') {
    // milieux de la diaphyse (Kwon 2022) ; de face : un seul axe, 25 → 75 % (MPRA, LDRA) ; de profil : axes 20 → 40 %
    // (CrPRA) et 60 → 80 % (CdDRA). Les arcs affichent les valeurs mesurées (chaque articulation dans son repère propre).
    const L = P.L, axe = (a, b) => ({ p: L[a], d: V.norm(V.sub(L[b], L[a])) });
    for (const f of [20, 25, 40, 60, 75, 80]) if (L[`rad_shaft_${f}`]) OV.base.dot(to2(L[`rad_shaft_${f}`]), 1.4, COL.mech);
    const axes = k === 'F' ? [axe('rad_shaft_25', 'rad_shaft_75')] : [axe('rad_shaft_20', 'rad_shaft_40'), axe('rad_shaft_60', 'rad_shaft_80')];
    for (const a of axes) { const p = to2(a.p), d = P2.norm(to2(a.d)); OV.base.ray(p, d, tAtY(p, d, B.top), tAtY(p, d, B.bot), COL.mech, 1.8, { dashed: true, dashSize: 6, gapSize: 4 }); }
    ['prox', 'dist'].forEach((seg, i) => arcArticulaire(P, k, seg, axes[Math.min(i, axes.length - 1)], L, seg === 'prox' ? OV.base : OV.dist, COL.joint, '', P.mesures.pre[SPEC.radius[k][seg].cle]));
    return;
  }
  if (P.bone === 'tibia') {
    const a = to2(P.centres.prox), b = to2(P.centres.dist);
    OV.base.seg(a, b, COL.mech, 1.8, { dashed: true, dashSize: 6, gapSize: 4 });
    OV.base.dot(a, 1.8, COL.mech); OV.dist.dot(b, 1.8, COL.mech);
    OV.base.label('éminence', P2.add(a, [0, 9]), 'mech');
    OV.dist.label(k === 'F' ? 'crête intermédiaire' : 'centre distal', P2.add(b, [0, -9]), 'mech');
    const axe = { p: P.centres.prox, d: V.norm(V.sub(P.centres.dist, P.centres.prox)) };
    for (const seg of ['prox', 'dist']) arcArticulaire(P, k, seg, axe, P.L, seg === 'prox' ? OV.base : OV.dist, COL.joint, '', P.mesures.pre[SPEC.tibia[k][seg].cle]);
  } else {
    for (const [i, m] of P.milieux.entries()) {
      const M = m[k];
      OV.base.seg(P2.add(M.a, [-4, 0]), P2.add(M.b, [4, 0]), COL.mech, 1.4);
      OV.base.dot(M.mid, 1.6, COL.mech);
      OV.base.label(i ? '1/2' : '1/3', P2.add(M.b, [16, 0]), 'mech');
    }
    const p = to2(P.axeProx.p), d = P2.norm(to2(P.axeProx.d));
    OV.base.ray(p, d, tAtY(p, d, B.top), tAtY(p, d, B.bot), COL.mech, 1.8, { dashed: true, dashSize: 6, gapSize: 4 });
    for (const seg of ['prox', 'dist']) if (SPEC.femur[k][seg]) arcArticulaire(P, k, seg, P.axeProx, P.L, seg === 'prox' ? OV.base : OV.dist, COL.joint, '', P.mesures.pre[SPEC.femur[k][seg].cle]);
  }
}
function dessinCORA2D(P, k) {
  const pr = P.proj[k], C = pr.cora, B = bornes(P);
  if (!C || Math.abs(pr.angle) < 0.5 || C[1] > B.top || C[1] < B.bot) return false;
  OV.base.dot(C, 2.2, COL.cora);
  OV.base.ring(C, 4.4, COL.cora, 1.6, { opacity: 0.8 });
  OV.base.arc(C, pr.up, pr.vp, 24, COL.cora, 2);
  const mid = P2.norm(P2.add(pr.up, pr.vp)), lat = P2.perp(mid);
  OV.base.label(`${k === 'F' ? 'F' : 'S'} = ${deg(Math.abs(pr.angle))}`, P2.add(C, P2.add(P2.mul(mid, 34), P2.mul(lat, 6))), 'cora');
  OV.base.label(k === 'F' ? 'CORA frontal' : 'CORA sagittal', P2.add(C, P2.mul(lat, -26)), 'cora');
  return true;
}
function dessinVerite(P) {
  if (!P.D) return;
  OV.base.octa(P.D.A, 2.6, COL.truth);
  OV.base.label('apex imposé', V.add(P.D.A, V.mul(P.bis.c, P.section.cvx + 22)), '');
}
// repères anatomiques détectés automatiquement (os segmenté)
const COURTS = {
  head_center: 'tête', gt_tip: 'grand trochanter', neck_base: 'col', cond_med_dist: 'condyle méd. (distal)',
  cond_lat_dist: 'condyle lat. (distal)', cond_med_caud: 'condyle méd. (caudal)', cond_lat_caud: 'condyle lat. (caudal)',
  epi_med: 'épicondyle méd.', epi_lat: 'épicondyle lat.', troch_dist: 'trochlée', eminence: 'éminence',
  plat_med: 'plateau méd.', plat_lat: 'plateau lat.', plat_cran: 'plateau (crânial)', plat_caud: 'plateau (caudal)',
  caud_med: 'condyle méd. (caudal)', caud_lat: 'condyle lat. (caudal)', tuberosity: 'tubérosité',
  groove_med: 'sillon méd.', groove_lat: 'sillon lat.', distal_center: 'centre distal', dist_cran: 'distal (crânial)',
  dist_caud: 'distal (caudal)', mall_med: 'malléole méd.', mall_lat: 'malléole lat.', fib_head: 'tête de la fibula',
};
// radius : ses propres repères (les alias du tibia, aux mêmes positions, ne sont pas étiquetés une seconde fois)
const COURTS_RADIUS = {
  rad_prox_center: 'centre de la tête radiale', rad_head_med: 'tête (méd.)', rad_head_lat: 'tête (lat.)',
  rad_head_cran: 'tête (crânial)', rad_head_caud: 'tête (caudal)', rad_dist_center: 'centre distal',
  rad_dist_med: 'surface carpienne (méd.)', rad_dist_lat: 'surface carpienne (lat.)', rad_dist_cran: 'surface carpienne (crânial)',
  rad_dist_caud: 'surface carpienne (caudal)', rad_styloid: 'styloïde du radius', uln_styloid: 'styloïde de l\'ulna',
  uln_olecranon: 'olécrâne (ulna)',
};
function dessinReperes(P, etiquettes = true) {
  const pts = Object.entries(P.bone === 'radius' ? COURTS_RADIUS : COURTS).filter(([k]) => P.L[k]).map(([k, nom]) => ({ k, nom, p: P.L[k] }));
  for (const it of pts) OV.base.dot(it.p, 1.1, COL.joint);
  if (!etiquettes || !P.box) return;
  // légendes rangées de part et d'autre de l'os (côté du repère), espacées d'au moins 9 mm, reliées par un trait
  const { lo, hi } = P.box, xm = (lo[0] + hi[0]) / 2, zm = (lo[2] + hi[2]) / 2;
  for (const cote of [-1, 1]) {
    const groupe = pts.filter((it) => (it.p[0] >= xm ? 1 : -1) === cote).sort((a, b) => b.p[1] - a.p[1]);
    let yPrec = Infinity;
    const xl = cote > 0 ? hi[0] + 14 : lo[0] - 14;
    for (const it of groupe) {
      const y = Math.min(it.p[1], yPrec - 9);
      yPrec = y;
      OV.base.seg(it.p, [xl, y, zm], COL.joint, 1, { opacity: 0.55 });
      // vues de face et 3/4 : le côté latéral (+X) est à gauche de l'écran ; l'étiquette s'étend vers l'extérieur
      OV.base.label(it.nom, [xl, y, zm], 'joint', cote > 0 ? 1 : 0);
    }
  }
}
// pas d'ostéotomie au CORA : pourquoi (étapes 9 à 12)
function boiteSansOsteo(P) {
  const raison = P.theta < THETA_MIN
    ? `les axes proximal et distal sont parallèles (θ = ${deg(P.theta, 2)}) : il n'y a pas de déformité angulaire à corriger.`
    : !P.coraDansOs
      ? `les axes se croisent en dehors de l'os (CORA à ${mm(P.validation.niveauCORA, 0)} ${depuis(P)}, os de ${mm(P.validation.longueurOs, 0)}) : avec θ = ${deg(P.theta)}, c'est le signe d'axes presque parallèles et décalés, pas d'une angulation.`
      : `le CORA n'est pas à l'intérieur de la section de l'os : la règle 1 (charnière sur la bissectrice, dans l'os) ne s'applique pas.`;
  return boite('warn', 'Pas d\'ostéotomie au CORA pour cet os', para(`Pas de plan de coupe : ${raison}`),
    P.reel && !P.D ? para('Pour voir toute la planification sur cet os réel, activez une <b>déformité de test</b> dans le panneau de gauche : la méthode doit alors retrouver l\'angulation imposée.') : null);
}
// os segmenté sans déformité imposée et angles dans les normes : la planification est un exercice
function boiteExercice(P) {
  if (!P.reel || P.D || P.anomalies.length) return null;
  return boite('warn', 'Aucune correction indiquée', para(`Les angles articulaires de cet os sont <b>dans les normes</b> : aucune correction n'est indiquée. Les ${deg(P.theta)} entre les axes viennent de la variation naturelle de l'os par rapport aux valeurs normales ; la suite montre la méthode, pas une indication chirurgicale.`));
}

// --- tracés 3D
function pointAxe(axe, y) { return V.add(axe.p, V.mul(axe.d, (y - axe.p[1]) / axe.d[1])); }
function axe3D(P, seg, coupe, opts = {}) {
  const axe = seg === 'prox' ? P.axeProx : P.axeDist, calque = seg === 'prox' ? OV.base : OV.dist, col = seg === 'prox' ? COL.prox : COL.dist;
  const B = bornes(P), top = pointAxe(axe, B.top), bot = pointAxe(axe, B.bot);
  if (!coupe) return calque.seg(top, bot, col, 3, opts);
  const C = seg === 'prox' ? P.cc.Pp : P.cc.Pd;
  const [plein, tiret] = seg === 'prox' ? [top, bot] : [bot, top];
  calque.seg(plein, C, col, 3, opts);
  calque.seg(C, tiret, col, 2, { dashed: true, dashSize: 5, gapSize: 4, opacity: 0.85 });
}
function dessinCORA3D(P, avecTheta = true) {
  OV.base.dot(P.cora, avecTheta ? 2.2 : 1.2, COL.cora);
  if (avecTheta) OV.base.arc3(P.cora, P.axeProx.d, P.axeDist.d, 26, COL.cora, 2, `θ = ${deg(P.theta)}`, 'cora');
}
function dessinPlanOblique(P) {
  const S = P.section;
  OV.base.rect(P.coraC, P.bis.b, P.bis.c, 52, S.largeur / 2 + 16, COL.plane, 0.07);
  OV.base.label('plan de la déformité', V.add(P.coraC, V.add(V.mul(P.bis.b, 44), V.mul(P.bis.c, S.largeur / 2 + 16))), 'plane');
}
function dessinBissectrice3D(P, avecACA = true) {
  const C = P.coraC, S = P.section, c = P.bis.c, n = P.bis.n;
  OV.base.seg(V.add(C, V.mul(c, -(S.ccv + 14))), V.add(C, V.mul(c, S.cvx + 14)), COL.bis, 2.6);
  OV.base.rect(C, c, n, S.largeur / 2 + 10, S.profondeur / 2 + 10, COL.bis, 0.1, false);
  if (avecACA) {
    const a = V.add(C, V.mul(n, -(S.profondeur / 2 + 18))), b = V.add(C, V.mul(n, S.profondeur / 2 + 18));
    OV.base.seg(a, b, COL.cora, 2.6, { dashed: true, dashSize: 4, gapSize: 3 });
    OV.base.label('ACA', V.add(a, V.mul(n, -6)), 'cora');
  }
}
// orientation de l'ACA dans le plan transverse : angle ψ avec la direction crânio-caudale
function dessinPsi(P) {
  const C = P.coraC, n = P.bis.n, S = P.section;
  const nT = V.norm([n[0], 0, n[2]]), z = [0, 0, Math.sign(nT[2]) || 1];
  const r = S.profondeur / 2 + 14;
  OV.base.seg(V.add(C, V.mul(z, -r)), V.add(C, V.mul(z, r)), COL.fg3, 1.4, { dashed: true, dashSize: 3, gapSize: 3 });
  OV.base.label('direction crânio-caudale', V.add(C, V.mul(z, -(r + 8))), '');
  if (P.psi > 0.5) OV.base.arc3(C, z, nT, r - 4, COL.cora, 2, `ψ = ${deg(P.psi)}`, 'cora');
}
function dessinOsteo3D(P, kind, avecEtiquettes = true) {
  const O = P.osteo[kind], S = P.section, H = O.charniere, n = P.bis.n;
  OV.base.seg(V.add(H, V.mul(n, -(S.profondeur / 2 + 12))), V.add(H, V.mul(n, S.profondeur / 2 + 12)), COL.hinge, 3);
  OV.base.dot(H, avecEtiquettes ? 0.9 : 1.4, COL.hinge);
  const versOs = kind === 'fermeture' ? P.bis.c : V.neg(P.bis.c);       // de la charnière vers la corticale opposée
  if (avecEtiquettes) OV.base.label('charnière', V.add(H, V.mul(versOs, -16)), 'hinge');
  for (const pl of O.plans) {
    const w = V.norm(V.perp(versOs, V.norm(pl.n)));
    OV.base.rect(V.add(H, V.mul(w, O.D / 2)), w, n, O.D / 2 + 5, S.profondeur / 2 + 7, COL.cut, 0.16);
  }
  if (avecEtiquettes) {
    const loin = V.add(H, V.add(V.mul(versOs, O.D + 12), V.mul(P.bis.b, 7)));     // un peu vers distal
    OV.base.label(`${kind === 'fermeture' ? 'base du coin' : 'ouverture'} ${mm(O.base)}`, loin, 'cut');
    if (O.plans.length === 2) {                         // angle entre les deux traits = θ
      const [w1, w2] = O.plans.map((pl) => V.norm(V.perp(versOs, V.norm(pl.n))));
      OV.base.arc3(H, w1, w2, O.D * 0.62, COL.cut, 2);
      OV.base.label(`${deg(O.angleCoupes)} entre les traits`, V.add(H, V.add(V.mul(V.norm(V.add(w1, w2)), O.D * 0.5), V.mul(P.bis.b, -7))), 'cut');
    }
  }
}
function dessinBroches(P, kind) {
  const O = P.osteo[kind], liste = O.brochesReduction || O.broches;
  for (const frag of ['proximal', 'distal']) {
    const bb = liste.filter((x) => x.fragment === frag);
    if (!bb.length) continue;
    const m = V.mul(bb.reduce((a, x) => V.add(a, x.point), [0, 0, 0]), 1 / bb.length);
    const calque = frag === 'proximal' ? OV.base : OV.dist;
    calque.label(`broche${bb.length > 1 ? 's' : ''} ${frag}e${bb.length > 1 ? 's' : ''}`, V.add(m, V.mul(bb[0].dir, -(P.section.largeur / 2 + 24))), 'pin');
  }
}

// ------------------------------------------------------------ angles normaux --
// Rôle de chaque angle (vue, lignes qui le forment, sens d'un écart quand il est établi dans les publications citées)
const SENS_ANGLE = {
  aLPFA: 'hanche, vue de face : axe anatomique / ligne du centre de la tête au grand trochanter',
  aLDFA: 'genou, vue de face : axe anatomique / ligne des condyles ; trop bas = valgus distal, trop haut = varus distal',
  varusFem: 'vue de face : écart de la ligne des condyles à la perpendiculaire de l\'axe anatomique (aLDFA − 90°)',
  aCdDFA: 'genou, vue de profil : axe anatomique distal / ligne condylienne (procurvatum, recurvatum)',
  mMPTA: 'genou, vue de face : axe mécanique / ligne des plateaux ; trop haut = valgus proximal',
  mMDTA: 'jarret, vue de face : axe mécanique / ligne de la cochlée',
  valgusTib: 'vue de face : angle entre les deux lignes articulaires du tibia',
  mCaPTA: 'genou, vue de profil : axe mécanique / ligne des plateaux (pente tibiale)',
  mCrDTA: 'jarret, vue de profil : axe mécanique / ligne distale',
  MPRA: 'coude, vue de face : axe anatomique (25 → 75 %) / ligne de la tête radiale',
  LDRA: 'carpe, vue de face : axe anatomique (25 → 75 %) / ligne de la surface carpienne ; trop bas = valgus distal',
  CrPRA: 'coude, vue de profil : axe proximal (20 → 40 %) / ligne crânio-caudale de la tête radiale',
  CdDRA: 'carpe, vue de profil : axe distal (60 → 80 %) / ligne crânio-caudale de la surface carpienne',
  procurvatum: 'vue de profil : angle entre les axes 20 → 40 % et 60 → 80 % ; le radius normal est arqué vers crânial',
  angulation_frontale: 'vue de face : angle entre les mêmes axes ; + = valgus (partie distale vers latéral)',
};
// Les angles normaux et leurs références publiées : travaux de l'équipe Vezzoni et autres études ; valeur de cet os
// ramenée à la définition « radiographique » des articles.
// Radius : normes articulaires par race (Kwon 2022), courbure (Duncan 2022), torsion (Kroner 2017) ; valeurs de cet os
function boiteNormalesRadius(P) {
  const J = P.reel ? S.reel.json : null;
  const val = (k) => (J ? J.angles[k] : P.mesures.pre[k]);
  const cles = ['MPRA', 'LDRA', 'CrPRA', 'CdDRA'];
  const cellule = (k, m, sd) => {
    const z = (val(k) - m) / sd;
    return h('td', { title: `écart réduit de cet os z = ${fr(z, 1)}` }, h('span', { class: 'nw' }, `${fr(m)} ± ${fr(sd)}`), ' ', h('span', { class: `tag ${Math.abs(z) <= 2 ? 'ok' : 'bad'}` }, Math.abs(z) <= 2 ? 'dans' : 'hors'));
  };
  const utilisee = S.reel.raceRadius || J?.normales?.MPRA?.race || null;
  const lignesR = Object.entries(RACES_RADIUS).map(([race, N]) => h('tr', { class: race === utilisee ? 'decisif' : '' },
    h('td', {}, race + (race === utilisee ? ' ★' : '')), ...cles.map((k) => cellule(k, N[k][0], N[k][1]))));
  const table = h('table', { class: 't compact enveloppe' }, h('caption', {}, 'Angles articulaires normaux par race (Kwon 2022)'),
    h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Race'), ...cles.map((k) => h('th', { scope: 'col', title: SENS_ANGLE[k] }, k)))),
    h('tbody', {}, h('tr', {}, h('td', {}, h('b', {}, J ? 'Cet os' : 'Os')), ...cles.map((k) => h('td', { class: 'hi' }, deg(val(k))))), lignesR));
  const L = LITTERATURE.radius, tor = P.torsion;
  return boite('def', 'Les angles normaux du radius',
    para('Un <b>angle normal</b> est l\'orientation habituelle d\'une ligne articulaire par rapport à l\'axe de son segment. Pour le radius, il varie beaucoup d\'une race à l\'autre (LDRA de 77 à 90°) : la <b>race du chien</b> choisit la référence (panneau de gauche ; ★ = race utilisée).'),
    table,
    para(`<b>Courbure</b> : le radius normal est arqué vers crânial (procurvatum <b>${fr(L.procurvatum.m)} ± ${fr(L.procurvatum.sd)}°</b>) et un peu en valgus (<b>${fr(L.angulation_frontale.m)} ± ${fr(L.angulation_frontale.sd)}°</b>) chez les petits chiens non chondrodystrophiques (Duncan 2022) ; plages normales 8 à 35° de profil et 0 à 8° de face (Knapp 2016). Cet os : procurvatum ${deg(val('procurvatum'))}, valgus ${deg(val('angulation_frontale'))}. La planification ne corrige que l'<b>excès</b> de courbure.`),
    para(`<b>Torsion</b> : ${fr(tor.normale.m, 1)} ± ${fr(tor.normale.sd, 1)}° chez le chien sain (Kroner 2017) ; cet os : <b>${deg(tor.avant)}</b> (${tor.statut}).`),
    para('<b>Définitions</b> : les angles sont mesurés en 3D, chaque articulation dans son repère propre (coude : axe médio-latéral de la tête radiale ; carpe : grand axe de la surface carpienne), comme sur une radiographie centrée sur elle. La ligne proximale de Kwon va du bord latéral de la tête radiale au processus coronoïde médial de l\'ulna ; ici, d\'un bord à l\'autre de la tête radiale : le MPRA n\'est qu\'approximativement comparable.'),
    sources('kwon22', 'fox06', 'duncan22', 'knapp16', 'kroner17'));
}
function boiteNormales(P) {
  if (P.bone === 'radius') return boiteNormalesRadius(P);
  const bone = P.bone, cles = [...CLES[bone].F, ...CLES[bone].S];
  const J = P.reel ? S.reel.json : null;
  // os segmenté : angles de l'os tel que segmenté, moins l'écart de définition des repères automatiques ;
  // os fictif : os sain du modèle (repères exacts, mêmes définitions que les articles)
  const radio = (k) => (J ? J.angles[k] - (J.normales[k]?.ecart_definition ?? 0) : P.mesures.normal[k]);
  const ref = (r) => h('span', { class: 'nw' }, `${fr(r.m)} ± ${fr(r.sd)}`);
  const badge = (x, r) => {
    if (!r || !isNum(x)) return null;
    const z = (x - r.m) / r.sd;
    return h('span', { class: `tag ${Math.abs(z) <= 2 ? 'ok' : 'bad'}`, title: `écart réduit z = ${fr(z, 1)}` }, Math.abs(z) <= 2 ? 'dans' : 'hors');
  };
  const lit = (k) => LITTERATURE[bone][k], vez = (k) => VEZZONI_PUBLIE[bone]?.[k] || null;
  const lignes = cles.map((k) => h('tr', {},
    h('td', { title: SENS_ANGLE[k] }, k === 'varusFem' ? 'Varus fém.' : court(k)),
    h('td', { title: vez(k)?.src || 'pas de valeur dans ces travaux' }, vez(k) ? h('span', {}, ref(vez(k)), ' ', badge(radio(k), vez(k))) : 'n.d.'),
    h('td', { title: lit(k).src }, h('span', {}, ref(lit(k)), ' ', badge(radio(k), lit(k)))),
    h('td', { class: 'hi' }, deg(radio(k)))));
  if (bone === 'tibia') {                // pente du plateau tibial, la grandeur des travaux de l'équipe Vezzoni
    const tpa = 90 - radio('mCaPTA'), dans = tpa >= 20.4 && tpa <= 30.8;
    lignes.push(h('tr', {},
      h('td', { title: 'pente du plateau tibial (Slocum), vue de profil : TPA = 90° − mCaPTA' }, 'TPA'),
      h('td', { title: 'Guénégo, Vezzoni et Vezzoni 2021 : 40 Labradors sains (médiane et étendue)' }, h('span', {}, h('span', { class: 'nw' }, '26,3 (20,4 à 30,8)'), ' ', h('span', { class: `tag ${dans ? 'ok' : 'bad'}` }, dans ? 'dans' : 'hors'))),
      h('td', { title: 'Wilke et al. 2002 : lévriers sains 22,5°, Labradors sains 28,0° (moyennes)' }, h('span', { class: 'nw' }, '22,5 (lévrier)')),
      h('td', { class: 'hi' }, deg(tpa))));
  }
  const table = h('table', { class: 't compact enveloppe' }, h('caption', {}, 'Angles normaux : références publiées'),
    h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Angle'), h('th', { scope: 'col' }, 'Vezzoni'), h('th', { scope: 'col' }, 'Autres études'),
      h('th', { scope: 'col' }, J ? 'Cet os*' : 'Os sain*'))),
    h('tbody', {}, lignes));
  const nVez = cles.filter((k) => vez(k)).length;
  const dansVez = cles.filter((k) => vez(k) && Math.abs(radio(k) - vez(k).m) <= 2 * vez(k).sd).length;
  const dansLit = cles.filter((k) => isNum(radio(k)) && Math.abs(radio(k) - lit(k).m) <= 2 * lit(k).sd).length;
  return boite('def', 'Les angles normaux : travaux de Vezzoni et autres études',
    para('Un <b>angle normal</b> est l\'orientation habituelle d\'une ligne articulaire par rapport à l\'axe de son segment. Il sert deux fois dans la méthode de Paley : construire l\'axe d\'un segment déformé à partir de sa ligne articulaire, et dépister une déformité. Survolez une ligne pour la définition de l\'angle et la source de chaque valeur.'),
    table,
    h('p', { class: 'src' }, `* valeur ${J ? 'de cet os tel que segmenté' : 'de l\'os sain du modèle'} ramenée à la définition radiographique des articles${J ? ' (mesure 3D − écart de définition des repères automatiques)' : ''} ; « dans » = à moins de 2 écarts-types (TPA : dans l'étendue publiée).`),
    para('<b>Travaux de l\'équipe Vezzoni</b> (Clinica Veterinaria Vezzoni, Crémone) :'),
    h('ul', {},
      h('li', { html: '<b>aLDFA 94 ± 3,3°</b> : en dessous, valgus distal du fémur (critère d\'inclusion de l\'hémiépiphysiodèse, Vezzoni L 2022). C\'est la valeur du berger allemand chez Tomlinson 2007, la plus basse des quatre races étudiées.' }),
      h('li', { html: '<b>mMPTA 93,3 ± 1,78°</b> : au-dessus, valgus proximal du tibia (Olsen, Vezzoni 2016, d\'après Dismukes 2007). Dans leur série de TPLO avec coin de fermeture médial, les tibias en valgus avaient 101° (98 à 107°), ramenés à 92,8° (88 à 97°) (Vezzoni L 2020).' }),
      h('li', { html: '<b>Pente du plateau tibial</b> : chez 40 Labradors sains de plus de 11 ans, TPA 26,3° (20,4 à 30,8°) et angle AMA (axe anatomique distal du tibia / axe mécanique, de profil) 0,99° (0 à 3,39°) ; chez les chiens opérés pour rupture du ligament croisé crânial, TPA ≈ 30 à 31° et AMA ≈ 3° (Guénégo, Vezzoni 2021 et 2025). L\'angle AMA n\'est pas encore mesuré par l\'application.' }),
      h('li', { html: '<b>Pes varus du teckel</b> : mMDTA 62° (52 à 70°) avant correction et 82° (76 à 87°) après, sous-correction fréquente (Petazzoni, Vezzoni 2012) : ce sont des valeurs pathologiques, pas une norme.' })),
    para('<b>Autres études</b>, pour les angles que ces travaux ne donnent pas et pour comparer : Tomlinson 2007 (fémur, quatre races : aLDFA de 94 à 98°) ; Dismukes 2007 et 2008 (tibia, de face et de profil) et Dismukes 2008b (membre entier : mMPTA 92,2 ± 1,8°, mMDTA 95,9 ± 2,2°) ; Wilke 2002 (lévrier : TPA 22,5°, « à considérer comme normal ») ; Guénégo 2017 (angle AMA > 1,87° associé à la rupture du ligament croisé) ; Kara 2018 (aCdDFA au scanner) ; Brühschwein 2023 (scanner : valeurs propres à chaque race).'),
    para('<b>Normal ou anormal ?</b> Un angle est jugé anormal à plus de 2 écarts-types de la référence choisie dans le panneau de gauche : « Vezzoni » (par défaut ; les angles absents de ces travaux prennent la littérature), « Littérature » ou « Race » (dont le lévrier). La race compte : le meilleur témoin reste le membre opposé sain du même chien.'),
    para(`<b>Le piège 2D/3D</b> : les articles mesurent sur radiographie, l'application en 3D avec des repères automatiques. L'écart de définition, mesuré une fois sur l'os sain du modèle (par exemple +9,5° pour mCaPTA), est ajouté aux valeurs publiées. Contrôle sur ${J ? 'cet os sain' : 'l\'os sain du modèle'} : ${dansVez} angle${dansVez > 1 ? 's' : ''} sur ${nVez} dans les bornes Vezzoni, ${dansLit} sur ${cles.length} dans la littérature.`),
    sources('vezzoni22', 'olsen16', 'guenego21', 'guenego25', 'vezzoni20', 'petazzoni', 'tomlinson', 'dismukes', 'dismukes08', 'dismukes08b', 'wilke02', 'guenego17', 'kara', 'bruhRaces'));
}

// ------------------------------------------------------------ les étapes --
const ETAPES = [
  {
    id: 'cas', court: 'Le cas', titre: (P) => (P.reel ? `${LeOs(P)} segmenté${P.D ? ' + déformité de test' : ''} : le cas à planifier` : `${P.cas.titre} : le cas à planifier`),
    // os segmenté tel quel : vue de face, où les légendes des repères se rangent proprement de part et d'autre de l'os
    get vue() { return PLAN && PLAN.reel && !PLAN.D ? { dir: 'cc', focus: 'os' } : { dir: 'iso', focus: 'os' }; },
    fantome: true, legende: ['ghost', 'truth'],
    dessin(P) { if (P.reel) dessinReperes(P, !P.D); dessinVerite(P); },
    texte(P) {
      if (P.reel) return texteCasReel(P);
      const v = P.validation;
      return [
        para(`${LeOs(P)} droit du <b>modèle synthétique</b> (os procédural calibré sur les angles publiés) porte une déformité angulaire imposée, dont l'apex est à <b>${fr(P.niveau * 100, 0)} %</b> de la longueur (${mm(v.niveauApex, 0)} ${depuis(P)}) :`),
        lignes([
          ['Plan frontal (vue de face)', `${deg(P.thetaF, 0)} de ${P.frontal}`],
          ['Plan sagittal (vue de profil)', P.sagittal === 'aucun' ? 'aucun' : `${deg(P.thetaS, 0)} de ${P.sagittal}`],
          ['Angle vrai θ (3D)', deg(v.thetaVrai)],
          ['Orientation du plan de la déformité φ', `${deg(v.phiVrai)} du plan frontal`],
        ]),
        boite('def', 'Vocabulaire',
          para('<b>Varus</b> : segment distal dévié vers <b>médial</b> (l\'angle pointe vers latéral). <b>Valgus</b> : dévié vers <b>latéral</b>.'),
          para('<b>Procurvatum</b> : l\'os est arqué vers <b>crânial</b> (apex crânial, segment distal dévié vers caudal). <b>Recurvatum</b> : l\'inverse (apex caudal).')),
        P.sagittal === 'aucun'
          ? para('Cette déformité est <b>pure</b> : elle est entièrement dans le plan frontal. C\'est un cas d\'école ; chez un vrai patient, une composante sagittale (et souvent une torsion) est presque toujours associée.')
          : para(`Comme chez la plupart des vrais patients, la déformité n'est <b>pas pure</b> : un ${P.frontal} et un ${P.sagittal} coexistent. Ce ne sont pas deux déformités : c'est <b>une seule</b> angulation de θ = ${deg(v.thetaVrai)} dans un <b>plan oblique</b>, que chaque radiographie ne voit qu'en partie.`),
        para('L\'os sain est affiché en transparence. Le petit octaèdre marque l\'apex imposé (vérité terrain) : la méthode ne s\'en sert pas, on vérifiera qu\'elle le retrouve.'),
        boiteNormales(P),
        boite('def', 'Ce que l\'on va faire',
          h('ol', {}, h('li', {}, 'Vue de face : lignes articulaires, angles, axes, CORA frontal (composante F).'),
            h('li', {}, 'Vue de profil : la même chose dans le plan sagittal (composante S).'),
            h('li', {}, 'En 3D : angle vrai θ, plan oblique, bissectrice et ACA.'),
            h('li', {}, 'Ostéotomie au CORA (règle 1 de Paley) : angle et traits de coupe, correction, contrôle.'),
            h('li', {}, 'Prescription du guide de coupe (plans, charnière, broches), puis analyse de la torsion.'))),
        sources('paley', 'shihtzu'),
      ];
    },
  },
  {
    id: 'F-jol', court: 'Frontal : lignes articulaires', titre: () => 'Vue de face : lignes d\'orientation articulaire', vue: { dir: 'cc', focus: 'os' }, plan2D: 'F', legende: ['plan', 'joint'],
    dessin(P) { planVue(P, 'F'); dessinOrientation(P, 'F'); dessinJOL(P, 'F'); etiquettesJOL(P, 'F'); },
    texte(P) {
      const M = P.mesures;
      const commun = [
        para('On commence par la <b>vue crânio-caudale</b> (de face), comme sur une radiographie ou une reconstruction CT dans le plan frontal. La caméra est orthographique : les angles vus à l\'écran sont les vrais angles <b>projetés</b> sur ce plan. Pour ce membre droit, <b>médial est à droite</b> de l\'écran.'),
      ];
      if (P.bone === 'radius') {
        return [...commun,
          para('<b>JOL proximale</b> : ligne qui relie les bords médial et latéral de la surface articulaire de la <b>tête radiale</b> (face à l\'humérus). <b>JOL distale</b> : ligne qui relie les bords médial et latéral de la <b>surface carpienne</b> du radius.'),
          para('Chaque surface articulaire est trouvée par <b>contact</b> avec l\'os voisin (humérus, carpe) puis résumée par son plan moyen ; ses bords sont pris le long de l\'axe médio-latéral <b>propre</b> de l\'articulation, comme sur une radiographie centrée sur le coude ou sur le carpe : la torsion de l\'avant-bras ne fausse pas les angles.'),
          sources('fox06', 'kwon22')];
      }
      if (P.bone === 'tibia') {
        const dv = M.pre.valgusTib - M.normal.valgusTib;
        const phraseV = anormal(P, 'valgusTib')
          ? `Il a ${dv < 0 ? 'diminué' : 'augmenté'} de <b>${deg(Math.abs(dv))}</b> : c'est la composante <b>frontale</b> de la déformité. Elle donne la taille de la déformité vue de face, pas son <b>emplacement</b>, ni ce qui se passe de profil.`
          : `Écart à la référence : ${degS(dv)}, dans les normes (± ${deg(2 * P.sdRef.valgusTib)}). Vue de face, pas de déformité frontale nette.`;
        return [...commun,
          para('<b>JOL proximale</b> : ligne qui relie les concavités sous-chondrales des plateaux tibiaux médial et latéral. <b>JOL distale</b> : ligne qui relie les sillons médial et latéral de la cochlée tibiale.'),
          boite('def', 'Valgus tibial (IMAIOS)', para('« Angle créé entre la ligne d\'orientation articulaire proximale du tibia et la ligne d\'orientation articulaire distale du tibia », mesuré sur une vue crânio-caudale.'), sources('imaiosValgus', 'newman')),
          tableMesures(P, M.pre, 'Angle entre les deux JOL', ['valgusTib']),
          para(phraseV),
          boite('def', 'Radiographie valide (IMAIOS)', para('Tibia perpendiculaire au faisceau ; corticales médiale et latérale du fémur passant au milieu des fabelles ; bord médial du calcanéus aligné avec la crête intermédiaire de la cochlée tibiale.'), sources('imaiosMDTA')),
        ];
      }
      return [...commun,
        para('<b>JOL proximale</b> : ligne qui relie le centre de la tête fémorale au sommet du grand trochanter. <b>JOL distale</b> : tangente aux points les plus distaux des condyles médial et latéral.'),
        para('Ces lignes servent de référence aux angles articulaires du fémur (aLPFA et aLDFA), mesurés à l\'étape suivante par rapport à l\'axe anatomique.'),
        boite('def', 'Radiographie valide (IMAIOS)', para('Vue ventro-dorsale, hanches en extension : bassin symétrique, corticales fémorales centrées sur les fabelles, patellas centrées dans les trochlées. Ces critères existent parce qu\'une rotation du membre sur la table modifie les angles mesurés (voir l\'étape « torsion »).'), sources('imaiosMecaF', 'tomlinson')),
      ];
    },
  },
  {
    id: 'F-ang', court: 'Frontal : angles articulaires', titre: (P) => (P.bone === 'tibia' ? 'Vue de face : axe mécanique et angles' : 'Vue de face : axe anatomique et angles'), vue: { dir: 'cc', focus: 'os' }, plan2D: 'F', legende: ['joint', 'mech'],
    dessin(P) { dessinJOL(P, 'F', 0.55); dessinAxeGlobal(P, 'F'); },
    texte(P) {
      const M = P.mesures, d = (k) => M.pre[k] - M.normal[k];
      if (P.bone === 'radius') {
        return [
          boite('def', 'Axes anatomiques du radius (Fox 2006, Kwon 2022)', para('On trace des perpendiculaires à la diaphyse à <b>20, 25, 40, 60, 75 et 80 %</b> de sa longueur et l\'on prend leurs milieux. De face, le radius est presque droit : un seul axe, des milieux à 25 et 75 %, sert aux angles <b>MPRA</b> (côté médial, avec la ligne de la tête radiale) et <b>LDRA</b> (côté latéral, avec la ligne de la surface carpienne). L\'angle entre les axes 20 → 40 % et 60 → 80 % (valgus) vaut normalement 4,8 ± 2,5° (Duncan 2022).'), sources('fox06', 'kwon22', 'duncan22')),
          tableMesures(P, M.pre, 'Mesures dans le plan frontal', CLES.radius.F),
          tousNormaux(P, CLES.radius.F)
            ? para(`Écarts à la référence : MPRA ${degS(d('MPRA'))}, LDRA ${degS(d('LDRA'))}, valgus ${degS(d('angulation_frontale'))} : dans les normes.`)
            : para(`${horsNormes(P, CLES.radius.F)}${anormal(P, 'LDRA') ? ` : la surface carpienne est inclinée (<b>${d('LDRA') < 0 ? 'valgus' : 'varus'} distal</b>, LDRA ${d('LDRA') < 0 ? 'diminué' : 'augmenté'})` : ''}. L'axe 25 → 75 % traverse la déformité : il ne dit pas <b>où</b> elle est ; on construit donc un axe par segment.`),
        ];
      }
      if (P.bone === 'tibia') {
        return [
          boite('def', 'Axe mécanique du tibia (IMAIOS)', para('Dans le plan frontal, il va du centre de l\'éminence intercondylaire au point le plus distal de la crête intermédiaire de la cochlée tibiale. mMPTA et mMDTA sont les angles, <b>côté médial</b>, entre cet axe et la JOL proximale ou distale.'), sources('imaiosMeca', 'imaiosMPTA', 'dismukes')),
          tableMesures(P, M.pre, 'Mesures dans le plan frontal', CLES.tibia.F),
          tousNormaux(P, ['mMPTA', 'mMDTA'])
            ? para(`Écarts à la référence : ${degS(d('mMPTA'))} et ${degS(d('mMDTA'))}, dans les normes. On construit tout de même un axe par segment : c'est ce qui dira si les deux segments sont alignés.`)
            : para(`Les angles s'écartent de la référence (${degS(d('mMPTA'))} et ${degS(d('mMDTA'))}) : la déformité est <b>entre les deux articulations</b>. Mais l'axe mécanique de l'os entier traverse la déformité : il ne dit pas <b>où</b> elle est. On construit donc un axe par segment.`),
        ];
      }
      return [
        boite('def', 'Axe anatomique du fémur', para('On trace deux lignes perpendiculaires à la diaphyse, à <b>1/3</b> et à <b>1/2</b> de la longueur du fémur, et on relie leurs milieux (bords médial et latéral de la silhouette).'), sources('tomlinson')),
        tableMesures(P, M.pre, 'Mesures dans le plan frontal', CLES.femur.F),
        anormal(P, 'aLDFA')
          ? para(`${anormal(P, 'aLPFA') ? `L'aLPFA s'écarte aussi (${degS(d('aLPFA'))}).` : 'L\'aLPFA est normal : le segment proximal est sain.'} L'aLDFA vaut ${deg(M.pre.aLDFA)} au lieu de ${deg(M.normal.aLDFA)} (${degS(d('aLDFA'))}) : la déformité est <b>distale</b>, et c'est un <b>${d('aLDFA') > 0 ? 'varus' : 'valgus'}</b> (aLDFA ${d('aLDFA') > 0 ? 'augmenté' : 'diminué'}).`)
          : para(`aLPFA ${degS(d('aLPFA'))} et aLDFA ${degS(d('aLDFA'))} par rapport à la référence : ${anormal(P, 'aLPFA') ? 'l\'aLPFA sort des normes (segment proximal)' : 'dans les normes'} ; pas de varus ni de valgus distal net.`),
        boite('def', 'Angle de varus fémoral (IMAIOS)', para(`Angle entre l'axe anatomique et la perpendiculaire à la JOL distale, soit aLDFA − 90°. Ici ${deg(M.pre.varusFem)} pour ${deg(M.normal.varusFem)} sur l'os sain.`), sources('imaiosVarusF')),
      ];
    },
  },
  {
    id: 'F-cora', court: 'Frontal : axes et CORA', titre: () => 'Vue de face : axes des segments et CORA frontal', vue: { dir: 'cc', focus: 'os' }, plan2D: 'F', legende: ['joint', 'prox', 'dist', 'cora'],
    dessin(P) {
      dessinJOL(P, 'F', 0.45);
      dessinAxe(P, 'F', 'prox', true); dessinAxe(P, 'F', 'dist', true);
      if (P.bone === 'tibia') arcArticulaire(P, 'F', 'prox', P.axeProx, P.L, OV.base, COL.prox, ' (normal)');
      else if (P.bone === 'radius') for (const f of [20, 40]) OV.base.dot(VUE.F.to2(P.L[`rad_shaft_${f}`]), 1.6, COL.prox);
      else for (const m of P.milieux) OV.base.dot(m.F.mid, 1.6, COL.prox);
      arcArticulaire(P, 'F', 'dist', P.axeDist, P.L, OV.dist, COL.dist, ' (normal)');
      dessinCORA2D(P, 'F');
    },
    texte(P) {
      const n = P.mesures.normal, pr = P.proj.F;
      const axes = P.bone === 'radius' ? paraAxesRadius(P) : P.bone === 'tibia'
        ? para(`<b>Axe proximal</b> : depuis l'éminence, droite qui fait avec la JOL proximale l'angle <b>mMPTA normal (${deg(n.mMPTA)})</b>. <b>Axe distal</b> : depuis la crête intermédiaire, droite qui fait avec la JOL distale l'angle <b>mMDTA normal (${deg(n.mMDTA)})</b>.`)
        : para(`<b>Axe proximal</b> : l'axe anatomique (le segment proximal est sain). <b>Axe distal</b> : le segment distal est trop court pour y prendre des milieux de diaphyse ; on part donc de la JOL distale avec l'<b>aLDFA normal (${deg(n.aLDFA)})</b>.`);
      return [
        axes,
        boite('def', 'Principe de Paley', para(`L'axe d'un segment se construit à partir de sa ligne articulaire et de l'angle articulaire <b>normal</b>. Référence utilisée ici : <b>${nomRef(P)}</b>. En clinique : membre opposé sain, ou valeurs publiées (travaux de l'équipe Vezzoni, autres études, valeurs par race).`),
          P.reference === 'normales' && P.bone === 'femur' ? para('Fémur : l\'axe distal part de la JOL distale de face comme sur l\'os sain du modèle ; de profil, il croise l\'axe proximal au niveau du CORA de face (une seule angulation : mêmes niveaux dans les deux vues). Le fémur du chien est naturellement arqué vers crânial : un gabarit de profil serait faux d\'un chien à l\'autre.') : null,
          sources('paley', 'dismukes', 'tomlinson')),
        P.typeF === 'aucun'
          ? para(`Vus de face, les deux axes sont presque parallèles (F = ${deg(Math.abs(pr.angle), 2)}) : <b>pas de composante frontale</b>.`)
          : para(`Le <b>CORA frontal</b> est l'intersection des deux axes vus de face. L'angle entre eux est la <b>composante frontale</b> : <b>F = ${deg(Math.abs(pr.angle))}</b> de ${P.typeF}${pr.niveau !== null ? `, à ${mm(pr.niveau, 0)} ${depuis(P)}` : ''}.`),
        P.typeS === 'aucun' ? null : boite('def', 'Ce que la vue de face ne voit pas',
          para(`Le segment distal est aussi incliné vers ${P.typeS === 'procurvatum' ? 'caudal' : 'crânial'}, c'est-à-dire <b>perpendiculairement à l'écran</b>. Vue de face, cette inclinaison est invisible : il faut la vue de profil.`),
          para(`Les arcs « (normal) » valent ${deg(arcValeur(P, 'F', 'dist'))} au lieu de ${deg(n[SPEC[P.bone].F.dist.cle])} pour le segment distal : quand un segment est incliné hors du plan, son angle <b>projeté</b> change un peu. C'est pourquoi le programme construit les axes en 3D (repère articulaire complet) et ne fait que les montrer ici en projection.`)),
      ];
    },
  },
  {
    id: 'S-ang', court: 'Sagittal : lignes et angles', titre: () => 'Vue de profil : lignes articulaires et angles', vue: { dir: 'ml', focus: 'os' }, plan2D: 'S', legende: ['plan', 'joint', 'mech'],
    dessin(P) { planVue(P, 'S'); dessinOrientation(P, 'S'); dessinJOL(P, 'S'); etiquettesJOL(P, 'S'); dessinAxeGlobal(P, 'S'); },
    texte(P) {
      const M = P.mesures, d = (k) => M.pre[k] - M.normal[k];
      const intro = para('On tourne l\'os de 90° : <b>vue médio-latérale</b> (de profil), crânial à droite de l\'écran. On refait exactement le même travail dans le <b>plan sagittal</b>.');
      if (P.bone === 'radius') {
        return [intro,
          boite('def', 'Angles sagittaux du radius (Fox 2006, Kwon 2022)', para('Le radius du chien est naturellement <b>arqué vers crânial</b> : de profil, on utilise <b>deux axes</b>, proximal (milieux à 20 et 40 %) et distal (milieux à 60 et 80 %). <b>CrPRA</b> : angle crânial entre l\'axe proximal et la ligne crânio-caudale de la tête radiale. <b>CdDRA</b> : angle caudal entre l\'axe distal et la ligne crânio-caudale de la surface carpienne. <b>Procurvatum</b> : angle entre les deux axes (16,8 ± 4,1° chez les petits chiens non chondrodystrophiques, Duncan 2022 ; 8 à 35° selon Knapp 2016).'), sources('fox06', 'kwon22', 'duncan22', 'knapp16')),
          tableMesures(P, M.pre, 'Mesures dans le plan sagittal', CLES.radius.S),
          tousNormaux(P, CLES.radius.S)
            ? para(`Dans les normes (CrPRA ${degS(d('CrPRA'))}, CdDRA ${degS(d('CdDRA'))}, procurvatum ${degS(d('procurvatum'))}) : la courbure du radius est normale, pas de composante sagittale nette.`)
            : para(`${horsNormes(P, CLES.radius.S)}${anormal(P, 'procurvatum') ? ` : le radius est <b>trop arqué</b> vers crânial` : ''}. C'est l'<b>excès</b> par rapport à la courbure normale qui se corrige, pas la courbure elle-même.`),
        ];
      }
      if (P.bone === 'tibia') {
        return [intro,
          boite('def', 'Angles sagittaux du tibia (Dismukes 2008)', para('<b>JOL proximale</b> : pente du plateau tibial médial (bords crânial et caudal). <b>JOL distale</b> : bords crânial et caudal de la surface articulaire distale. <b>mCaPTA</b> : angle caudal entre l\'axe mécanique et la JOL proximale (pente du plateau TPA = 90° − mCaPTA). <b>mCrDTA</b> : angle crânial entre l\'axe et la JOL distale.'), sources('dismukes08')),
          tableMesures(P, M.pre, 'Mesures dans le plan sagittal', CLES.tibia.S),
          tousNormaux(P, CLES.tibia.S)
            ? para(`Les deux angles sont dans les normes (${degS(d('mCaPTA'))}, ${degS(d('mCrDTA'))}) : <b>pas de composante sagittale</b> nette. Ce contrôle est indispensable : sans la vue de profil, on ne peut pas affirmer qu'une déformité est purement frontale.`)
            : para(`${horsNormes(P, CLES.tibia.S)} : ${anormal(P, 'mCaPTA') && !anormal(P, 'mCrDTA') ? 'c\'est le segment proximal (pente du plateau) qui est incliné' : !anormal(P, 'mCaPTA') ? 'la pente du plateau est normale, le segment distal est incliné' : 'les deux segments sont inclinés'} dans le plan sagittal${P.typeS !== 'aucun' ? ` (<b>${P.typeS}</b>)` : ''}.`),
        ];
      }
      return [intro,
        para('Le segment proximal reste repéré par l\'<b>axe anatomique</b> (milieux des bords crânial et caudal de la diaphyse à 1/3 et 1/2). Pour le segment distal, on trace une <b>JOL sagittale</b> du fond de la trochlée (extrémité distale) au milieu des points caudaux des condyles.'),
        boite('def', 'aCdDFA (angle caudal distal du fémur)', para(`Angle, côté caudal, entre l'axe anatomique et la JOL sagittale distale. Kara et al. (2018, 3D-CT, 75 fémurs) rapportent un angle de procurvatum distal « CDFA » de 89,1 à 91,9° (IC 95 %) avec une définition voisine mais pas identique : la référence utilisée ici est ${P.reference === 'normales' ? `l'os sain du modèle mesuré avec les repères automatiques (${deg(P.mesures.normal.aCdDFA)})` : P.reel ? 'l\'os avant la déformité de test' : 'la valeur de l\'os sain du modèle (96,4°)'}.`), sources('kara')),
        tableMesures(P, M.pre, 'Mesure dans le plan sagittal', CLES.femur.S),
        !anormal(P, 'aCdDFA')
          ? para(`L'angle est dans les normes (${degS(d('aCdDFA'))}) : <b>pas de composante sagittale</b> nette. Sans cette vue, on ne pourrait pas affirmer qu'une déformité est purement frontale.`)
          : para(`L'aCdDFA s'écarte de ${degS(d('aCdDFA'))} : le segment distal est incliné dans le plan sagittal${P.typeS !== 'aucun' ? ` (<b>${P.typeS}</b>)` : ''}. Attention : le fémur du chien est naturellement arqué vers crânial ; c'est l'écart à la référence qui compte, pas la courbure elle-même.`),
      ];
    },
  },
  {
    id: 'S-cora', court: 'Sagittal : axes et CORA', titre: () => 'Vue de profil : axes des segments et CORA sagittal', vue: { dir: 'ml', focus: 'os' }, plan2D: 'S', legende: ['joint', 'prox', 'dist', 'cora'],
    dessin(P) {
      dessinJOL(P, 'S', 0.45);
      dessinAxe(P, 'S', 'prox', true); dessinAxe(P, 'S', 'dist', true);
      if (P.bone === 'tibia') arcArticulaire(P, 'S', 'prox', P.axeProx, P.L, OV.base, COL.prox, ' (normal)');
      else if (P.bone === 'radius') for (const f of [20, 40]) OV.base.dot(VUE.S.to2(P.L[`rad_shaft_${f}`]), 1.6, COL.prox);
      else for (const m of P.milieux) OV.base.dot(m.S.mid, 1.6, COL.prox);
      arcArticulaire(P, 'S', 'dist', P.axeDist, P.L, OV.dist, COL.dist, ' (normal)');
      dessinCORA2D(P, 'S');
    },
    texte(P) {
      const pr = P.proj.S, v = P.validation;
      if (P.typeS === 'aucun') {
        return [
          para('Les axes proximal et distal, construits comme de face mais avec les angles sagittaux normaux, sont <b>parallèles</b> vus de profil : ils ne se croisent pas, il n\'y a <b>pas de CORA sagittal</b>.'),
          para(`Composante sagittale : S = ${deg(Math.abs(pr.angle), 2)}. La déformité est entièrement dans le plan frontal : l'angle vrai est F = ${deg(P.theta)} et l'axe de correction (ACA) sera crânio-caudal.`),
          boite('def', 'À retenir', para('Une déformité n\'est « pure » que si on l\'a vérifié dans <b>les deux vues</b>. Le même cas avec un procurvatum ou un recurvatum (panneau de gauche) le montre.')),
        ];
      }
      return [
        para(`Vu de profil, les axes se croisent au <b>CORA sagittal</b>. L'angle entre eux est la <b>composante sagittale</b> : <b>S = ${deg(Math.abs(pr.angle))}</b> de ${P.typeS}.`),
        lignes([
          ['Niveau du CORA frontal', mm(v.niveauF, 1)],
          ['Niveau du CORA sagittal', mm(v.niveauS, 1)],
          ['Écart entre les deux niveaux', mm(Math.abs(v.niveauF - v.niveauS), 1)],
        ]),
        v.niveauF !== null && v.niveauS !== null && Math.abs(v.niveauF - v.niveauS) < 10
          ? para('Les deux CORA sont au <b>même niveau</b> : c\'est la signature d\'une <b>seule</b> angulation dans un plan oblique (et non de deux déformités distinctes). Si les niveaux différaient nettement, ce serait le signe d\'une translation ou de deux apex (Paley).')
          : para('Les deux CORA ne sont <b>pas au même niveau</b> : c\'est le signe d\'une translation, de deux apex (le programme n\'en planifie qu\'un), ou d\'axes presque parallèles (petite angulation mal définie). Le CORA 3D (étape suivante) prend le milieu de la perpendiculaire commune aux deux axes.'),
        sources('paley', 'dismukes08'),
      ];
    },
  },
  {
    id: 'obl', court: 'Angle vrai (3D)', titre: () => 'En 3D : angle vrai et plan de la déformité', vue: { dir: 'aca', focus: 'cora', r: 72 }, transparence: 0.45, legende: ['prox', 'dist', 'cora', 'oblique', 'truth'],
    dessin(P) { dessinPlanOblique(P); axe3D(P, 'prox', true); axe3D(P, 'dist', true); dessinCORA3D(P); dessinVerite(P); },
    texte(P) {
      const v = P.validation;
      const vF = M3.mv(M3.axisAngle([0, 0, 1], -P.Fm * RAD), P.axeDist.d);
      const resteF = V.angle(P.axeProx.d, vF);
      return [
        para('La vue regarde <b>perpendiculairement au plan de la déformité</b> (le long de l\'ACA) : θ y apparaît en vraie grandeur. Tournez la vue (clic-glisser ou bouton 3D) pour voir que ce plan est oblique.'),
        para(`En 3D, les axes proximal et distal se croisent au <b>CORA</b> (milieu de leur perpendiculaire commune ; écart entre les axes ${mm(v.delta, 2)}). Ils définissent un plan : le <b>plan de la déformité</b> (en rose). L'angle entre eux, mesuré <b>dans ce plan</b>, est l'<b>angle vrai θ = ${deg(P.theta)}</b>.`),
        h('table', { class: 't' }, h('caption', {}, 'Des deux vues au plan oblique'),
          h('tbody', {},
            h('tr', {}, h('td', {}, 'Composante frontale F (vue de face)'), h('td', { class: 'hi' }, compF(P))),
            h('tr', {}, h('td', {}, 'Composante sagittale S (vue de profil)'), h('td', { class: 'hi' }, compS(P))),
            h('tr', {}, h('td', {}, 'θ par la formule tan²θ = tan²F + tan²S'), h('td', { class: 'hi' }, deg(P.theta2D, 2))),
            h('tr', {}, h('td', {}, 'θ mesuré directement en 3D'), h('td', { class: 'hi' }, deg(P.theta, 2))),
            P.D ? h('tr', {}, h('td', {}, 'θ imposé (vérité terrain)'), h('td', {}, deg(v.thetaVrai, 2))) : null,
            h('tr', {}, h('td', {}, 'Orientation φ = atan(tan S / tan F)'), h('td', { class: 'hi' }, `${deg(P.phi)} du plan frontal`)))),
        P.theta < THETA_MIN ? boiteSansOsteo(P) : para(`L'apex est du côté <b>${sens3(P.bis.c)}</b> : c'est la direction de la convexité. φ = 0° serait un ${P.Fm < 0 ? 'varus' : 'valgus'} pur, φ = 90° un ${P.Sm >= 0 ? 'procurvatum' : 'recurvatum'} pur.`),
        boiteExercice(P),
        P.typeS === 'aucun' || P.typeF === 'aucun' ? null : boite('def', 'Le piège de la planification « vue par vue »',
          para(`Si l'on ne corrige que ce que montre la vue de face (un coin de F = ${deg(Math.abs(P.Fm))} avec une charnière crânio-caudale), il reste <b>${deg(resteF)}</b> d'angulation, presque toute dans le plan sagittal.`),
          para(`Deux coins successifs (F puis S) enlèveraient ${deg(Math.abs(P.Fm) + Math.abs(P.Sm))} d'angle au total ; <b>un seul coin oblique de θ = ${deg(P.theta)}</b> suffit et corrige les deux composantes à la fois.`)),
        sources('paley', 'qatu', 'shihtzu'),
      ];
    },
  },
  {
    id: 'bis', court: 'Bissectrice et ACA', titre: () => 'Plan bissecteur et axe de correction (ACA)', vue: { dir: 'haut', focus: 'cora', r: 46 }, transparence: 0.4, legende: ['prox', 'dist', 'cora', 'bis', 'aca'],
    dessin(P) { axe3D(P, 'prox', true, { opacity: 0.8 }); axe3D(P, 'dist', true, { opacity: 0.8 }); dessinCORA3D(P, false); dessinBissectrice3D(P); dessinPsi(P); },
    texte(P) {
      return [
        para('Le <b>plan bissecteur transverse</b> passe par le CORA et partage l\'angle θ en deux. Il coupe l\'os d\'une corticale à l\'autre (trait jaune : la bissectrice transverse, dans le plan de la déformité).'),
        P.osteoPossible ? null : boiteSansOsteo(P),
        para(`L'<b>ACA</b> (axe de correction angulaire) est la droite autour de laquelle on tournera le segment distal : il est <b>perpendiculaire au plan de la déformité</b>. Pour un varus ou un valgus pur, il serait crânio-caudal ; ici il est tourné de <b>ψ = ${deg(P.psi)}</b> dans le plan transverse.`),
        boite('def', 'Règle de Paley', para('Tout point de la bissectrice transverse est un CORA équivalent : si la charnière (l\'ACA) y est placée, la rotation réaligne les axes <b>sans translation</b>. On peut donc choisir la charnière n\'importe où sur cette ligne : c\'est ce qui décide entre coin d\'ouverture, de fermeture ou neutre.'), sources('paley')),
        para(`Largeur de l'os le long de la bissectrice : <b>${mm(P.section.largeur)}</b> (${mm(P.section.cvx)} côté convexe ${sens3(P.bis.c)}, ${mm(P.section.ccv)} côté concave ${sens3(P.bis.ccv)}).`),
        P.psi > 0.5 ? boite('def', 'Pourquoi c\'est important pour le guide', para(`Une charnière mal orientée change aussi le plan voisin : en chirurgie humaine, un coin d'ouverture tibial dont la charnière n'est pas bien orientée modifie la pente du plateau (≈ 2° de pente par millimètre d'erreur d'ouverture crâniale). Le guide doit donc imposer l'orientation 3D de la charnière, ici ψ = ${deg(P.psi)}.`), sources('noyes', 'ducat')) : null,
      ];
    },
  },
  {
    id: 'osteo', court: 'Angle et traits de coupe', titre: () => 'Ostéotomie : angle et traits de coupe', vue: { dir: 'aca', focus: 'cora', r: 30 }, legende: ['prox', 'dist', 'bis', 'hinge', 'cut', 'wedge'],
    coupe: true,
    dessin(P, ctx) { axe3D(P, 'prox', true, { opacity: 0.8 }); axe3D(P, 'dist', true, { opacity: 0.8 }); OV.base.dot(P.cora, 0.8, COL.cora); if (!P.osteoPossible) return; dessinBissectrice3D(P, false); dessinOsteo3D(P, ctx.kind); },
    texte(P, ctx) {
      if (!P.osteoPossible) return [boiteSansOsteo(P)];
      const O = P.osteo[ctx.kind], ccv = sens3(P.bis.ccv, true), cvx = sens3(P.bis.c, true);
      if (!O) return [boiteSansOsteo(P)];
      const rec = P.recommandation;
      const choix = h('div', { class: 'seg', role: 'group', 'aria-label': 'Type de coin' },
        ...['fermeture', 'ouverture'].map((k) => h('button', { type: 'button', 'aria-pressed': String(k === ctx.kind), disabled: !P.osteo[k], onclick: () => ctx.setKind(k) },
          k === 'fermeture' ? 'Coin de fermeture' : 'Coin d\'ouverture', rec?.kind === k ? ' ★' : '')));
      const sommet = O.charniereConservee ? '<b>Charnière</b>' : '<b>Sommet du coin</b> (ostéotomie complète : repère de l\'angle, la corticale est coupée aussi)';
      const corps = ctx.kind === 'fermeture'
        ? [para(`${sommet} sur la corticale <b>concave (${ccv})</b>, à ${fr(O.h, 1)} mm à l'intérieur${O.charniereConservee ? ' pour garder un pont d\'os' : ''}.`),
          para(`<b>Deux traits de scie</b> partent de la charnière : l'un <b>perpendiculaire à l'axe proximal</b>, l'autre <b>perpendiculaire à l'axe distal</b>. L'angle entre les deux traits vaut donc <b>θ = ${deg(O.angleCoupes)}</b>. Le coin d'os entre eux (en rouge) est retiré <b>par la face convexe (${cvx})</b> : c'est par là que la lame entre, et là que se pose le guide.`),
          para(`Base du coin sur la corticale ${cvx} : <b>${mm(O.base)}</b> (= 2·D·tan(θ/2), D = ${mm(O.D)} de la charnière à la corticale d'entrée). L'os est <b>${O.deltaOperation < 0 ? 'raccourci' : 'allongé'}</b> de ${mm(Math.abs(O.deltaOperation))}${O.coinMixte ? ` (coin mixte : le côté concave s'ouvre de ${mm(O.ouvertureCharniere)})` : ''}.`)]
        : [para(O.charniereConservee
          ? `<b>Charnière</b> sur la corticale <b>convexe (${cvx})</b>, à ${fr(O.h, 1)} mm à l'intérieur. Cette corticale doit rester intacte : si elle casse, la correction est imprécise (souvent sous-corrigée).`
          : `${sommet} sur la corticale <b>convexe (${cvx})</b>, à ${fr(O.h, 1)} mm à l'intérieur.`),
          para(`<b>Un seul trait de scie</b>, dans le plan bissecteur transverse, entré par la <b>face concave (${ccv})</b> : c'est là que se pose le guide. On ouvre de <b>θ = ${deg(P.theta)}</b> côté concave : l'espace créé (en orange) devra être comblé (greffe) et stabilisé (plaque).`),
          para(`Ouverture sur la corticale ${ccv} : <b>${mm(O.base)}</b> (= 2·D·sin(θ/2), D = ${mm(O.D)}). L'os est <b>allongé</b> de ${mm(Math.abs(O.deltaOperation))}.`)];
      return [
        choix,
        boiteRecommandation(P, ctx),
        boiteExercice(P),
        para('La vue regarde <b>le long de l\'ACA</b> : on voit la déformité dans son propre plan, donc l\'angle vrai θ sans déformation de projection.'),
        ...corps,
        boiteCharniere(P, O, ctx.kind),
        boiteContraintes(P, O),
        boiteStrategie(P, O, ctx.kind),
        P.bone === 'tibia' && P.meshes.includes('fibula') ? para('La <b>fibula</b>, accolée au tibia, est coupée par les mêmes plans : sans cela, elle bloquerait la correction.') : null,
        P.bone === 'radius' && P.meshes.includes('ulna') ? para('L\'<b>ulna</b>, parallèle au radius, est coupée au même niveau (ostéotomie de l\'ulna, par un court abord caudo-latéral) : intacte, elle bloquerait la correction. Le guide ne se pose jamais entre le radius et l\'ulna.') : null,
        boite('def', 'Sur quoi se base l\'angle de coupe ?',
          h('ol', {},
            h('li', { html: `L'angle à corriger est l'<b>écart à l'orientation normale</b> : angle articulaire mesuré − valeur de référence (valeurs publiées${P.bone === 'radius' ? ' par race et courbure normale' : ' : travaux de l\'équipe Vezzoni et autres études, éventuellement par race'} ; ou membre controlatéral sain). Ici : ${nomRef(P)}.` }),
            h('li', { html: `Avec deux radiographies, on mesure F et S puis on combine : tan²θ = tan²F + tan²S, plan à φ = atan(tan S / tan F). En 3D, θ se mesure directement (ici ${deg(P.theta)}).` }),
            h('li', { html: '<b>Le même θ sert pour l\'ouverture et pour la fermeture</b> : seule la position de la charnière change (concave = fermeture, convexe = ouverture, milieu = neutre).' }),
            h('li', { html: 'Fermeture : un trait ⊥ à chaque axe, donc angle entre les traits = θ. Ouverture : un trait le long de la bissectrice, ouvert de θ.' }),
            h('li', { html: `Précision : 1° de correction ne vaut que ${mm(O.D * Math.PI / 180, 2)} à la corticale opposée (os de ${mm(O.D, 0)}) : c'est l'angle qu'il faut contrôler, pas les millimètres.` })),
          sources('paley', 'qatu')),
        P.bone === 'radius' ? boite('def', 'Exemples publiés pour l\'avant-bras',
          para('<b>Une seule ostéotomie oblique</b> pour une déformité angulaire et de torsion de l\'avant-bras : 23° de valgus et 23° de procurvatum forment une seule angulation de 32° dans un plan oblique à 45° (Kim 2017) ; c\'est le principe du coin oblique de θ calculé ici.'),
          para('<b>Guides imprimés en 3D</b> : guides de coupe seuls, un membre sur 7 réopéré pour une rotation mal corrigée (Worth 2019) ; avec des guides de repositionnement (réduction), plus de 90 % des paramètres planifiés sont obtenus à 5° et 5 mm près (De Armond 2022 ; Carwardine 2021). D\'où le guide de réduction, qui fixe aussi la dérotation.'),
          sources('shihtzu', 'worth19', 'dearmond22', 'carwardine21')) : null,
        P.bone === 'radius' ? null : boite('def', 'Les exemples de l\'équipe Vezzoni',
          para('<b>CCWO « AMA-based »</b> (coin crânial de fermeture du tibia proximal) : angle du coin = angle entre l\'axe anatomique et l\'axe mécanique (= 0,65 × TPA) ; trait distal ⊥ à l\'axe anatomique, trait proximal ⊥ à l\'axe de rotation ; sommet du coin (charnière) à l\'insertion caudale du ligament collatéral médial. C\'est exactement la règle ci-dessus : un trait ⊥ à chaque axe, charnière sur la corticale concave.'),
          para('<b>TPLO + coin de fermeture médial</b> pour un valgus tibial : mMPTA 101° → 92,8°. <b>Pes varus du teckel</b> : coin d\'ouverture médial au CORA, en préservant la corticale latérale (la charnière) pour éviter la sous-correction.'),
          sources('guenego21', 'guenego25', 'vezzoni20', 'petazzoni')),
        boiteDome(P, O),
      ];
    },
  },
  {
    id: 'corr', court: 'Correction', titre: () => 'Simuler la correction', vue: { dir: 'aca', focus: 'cora', r: 74 }, legende: ['prox', 'dist', 'hinge', 'pin'],
    coupe: true, anime: true, broches: true, transparence: 0.6,
    dessin(P, ctx) {
      const O = P.osteo[ctx.kind];
      axe3D(P, 'prox', false); axe3D(P, 'dist', false);
      if (!O) return;
      OV.base.dot(O.charniere, 1.8, COL.hinge);
      OV.base.label(O.charniereConservee ? 'charnière' : 'sommet du coin', V.add(O.charniere, V.mul(ctx.kind === 'fermeture' ? P.bis.ccv : P.bis.c, 14)), 'hinge');
      dessinBroches(P, ctx.kind);
    },
    texte(P, ctx) {
      const O = P.osteo[ctx.kind];
      if (!O) return [boiteSansOsteo(P)];
      return [
        boiteExercice(P),
        para(O.regle === 2
          ? `Le fragment distal tourne de <b>${deg(P.theta)}</b> autour de l'ACA placé sur la bissectrice du CORA (règle 2) : comme la coupe est ${mm(O.decalageCoupe, 0)} plus loin, il <b>glisse de ${mm(O.translationOsteo, 1)}</b> le long de la coupe. Lancez la lecture ou faites glisser le curseur sous la vue.`
          : `Le fragment distal tourne de <b>${deg(P.theta)}</b> autour de la charnière, c'est-à-dire autour de l'ACA oblique. Lancez la lecture ou faites glisser le curseur sous la vue.`),
        para(ctx.kind === 'fermeture' ? 'Le coin d\'os est d\'abord retiré, puis les deux faces de coupe se referment l\'une sur l\'autre.' : 'Les deux faces de coupe s\'écartent côté concave ; l\'espace qui s\'ouvre est en orange.'),
        para('Regardez l\'axe distal (vert) : il vient se superposer à l\'axe proximal (violet), dans les deux plans à la fois.'),
        Math.abs(O.derotation) >= DEROTATION_MIN
          ? boite('warn', 'Dérotation', para(`La torsion mesurée (${P.torsion.publiee ? 'définition publiée' : 'définition du modèle'}) passe de ${deg(P.torsion.avant)} avant correction à ${deg(O.torsionApresAngle)} après la seule correction angulaire, pour une cible de ${deg(O.torsionCible)} : le fragment distal tourne en plus de <b>${deg(O.derotation)}</b> autour de son axe long (${ctx.kind === 'fermeture' ? 'avant de refermer le coin' : 'après l\'ouverture'}). Torsion finale : ${deg(O.torsionApres)}.`),
            para(`Une dérotation impose une ostéotomie <b>complète</b> (la charnière corticale ne peut pas tourner) : c'est le <b>guide de réduction</b> qui fixe alors la position des fragments.`))
          : null,
        para(`Les <b>broches de réduction</b> (${(CONFIG_BROCHES[O.configBroches] || CONFIG_BROCHES['2+2']).nom}) ont été forées avec un angle de ${deg(O.angleBroches)} entre les fragments : à la fin de la correction, elles sont toutes <b>parallèles</b>, et le guide de réduction s'y enfile (étape 12).`),
        h('table', { class: 't' }, h('tbody', {},
          h('tr', {}, h('td', {}, 'Angle restant entre les axes'), h('td', { class: 'hi', id: 'live-angle' }, deg(P.theta))),
          h('tr', {}, h('td', {}, 'Angle entre les paires de broches'), h('td', { class: 'hi', id: 'live-pins' }, deg(O.angleBroches))),
          h('tr', {}, h('td', {}, 'Torsion (avant → après)'), h('td', { class: 'hi' }, `${deg(P.torsion.avant)} → ${deg(O.torsionApres)}`)))),
        boiteBroches(P, O),
        boiteDerotation(P, O, ctx.kind),
      ];
    },
  },
  {
    id: 'ctrl', court: 'Contrôle', titre: () => 'Contrôler le résultat dans les deux plans', vue: { dir: 'cc', focus: 'os' }, plan2D: 'F', fantome: true, legende: ['joint', 'prox', 'dist', 'ghost'],
    coupe: true, fin: true,
    dessin(P, ctx) {
      const O = P.osteo[ctx.kind];
      dessinJOL(P, 'F');
      dessinAxe(P, 'F', 'prox', false); dessinAxe(P, 'F', 'dist', false, { opacity: 0.9 });
      if (!O) return;
      arcArticulaire(P, 'F', 'prox', P.axeProx, P.L, OV.base, COL.joint, '', O.post[SPEC[P.bone].F.prox.cle]);
      arcArticulaire(P, 'F', 'dist', P.axeDist, P.L, OV.dist, COL.joint, '', O.post[SPEC[P.bone].F.dist.cle]);   // calque distal : suit le fragment corrigé
    },
    texte(P, ctx) {
      const O = P.osteo[ctx.kind], pre = P.mesures.pre, v = P.validation, N = P.mesures.normal;
      const cles = [...CLES[P.bone].F, ...CLES[P.bone].S];
      if (!O) return [boiteSansOsteo(P)];
      return [
        para(`Après le ${kindNom[ctx.kind]}, on remesure les angles sur l'os corrigé, <b>de face et de profil</b>${P.D || !P.reel ? ' (l\'os sain est en transparence ; utilisez le bouton ML pour la vue de profil)' : ' (bouton ML pour la vue de profil)'}.`),
        h('table', { class: 't' }, h('caption', {}, 'Avant / après correction'),
          h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Mesure'), h('th', { scope: 'col' }, 'Avant'), h('th', { scope: 'col' }, 'Après'), h('th', { scope: 'col' }, colRef(P)))),
          h('tbody', {},
            cles.map((k) => h('tr', {}, h('td', {}, NOMS[k]), h('td', {}, deg(pre[k])), h('td', { class: 'hi' }, deg(O.post[k]), statut(P, k, O.post[k])), h('td', {}, deg(N[k])))),
            h('tr', {}, h('td', {}, 'Angle vrai entre les axes'), h('td', {}, deg(v.thetaMesure)), h('td', { class: 'hi' }, deg(O.residuel, 2)), h('td', {}, deg(0))),
            h('tr', {}, h('td', {}, 'Translation entre les axes'), h('td', {}, 'n.d.'), h('td', { class: 'hi' }, mm(O.decalage, 2)), h('td', {}, mm(0))),
            h('tr', {}, h('td', {}, `Torsion (${P.torsion.publiee ? 'définition publiée' : 'définition du modèle'})`), h('td', {}, deg(P.torsion.avant)), h('td', { class: 'hi' }, deg(O.torsionApres)), h('td', {}, deg(O.torsionCible))),
            h('tr', {}, h('td', {}, 'Longueur (centres articulaires)'), h('td', {}, mm(pre.longueur)), h('td', { class: 'hi' }, mm(O.post.longueur)), h('td', {}, P.reference === 'normales' ? 'n.d.' : mm(N.longueur))))),
        boite('ok', 'Conclusion', para(`Les axes sont réalignés (${deg(O.residuel, 2)} d'écart) et sans translation (${mm(O.decalage, 2)}) : la <b>règle ${O.regle === 2 ? '2' : '1'}</b> est respectée${O.regle === 2 ? ` (translation de ${mm(O.translationOsteo, 1)} à l'ostéotomie, pas entre les axes)` : ''} et les angles articulaires sont revenus à leur valeur normale dans les deux plans, avec <b>une seule</b> ostéotomie. Seule la longueur change (${O.dLongueur > 0 ? '+' : '−'}${mm(Math.abs(O.dLongueur))}), comme prévu pour un ${kindNom[ctx.kind]}.`)),
        boite('def', 'Limites', para(P.reel
          ? 'Os réel mais rigide ; repères automatiques (étape 6 : ± 1 mm sur l\'os du modèle pour les repères robustes, quelques degrés pour les angles sagittaux, dont les lignes articulaires ne font que 20 à 30 mm) ; torsion corrigée par dérotation si elle sort de la normale ; tissus mous non modélisés. Vérifiez les repères à l\'étape 1. Cibles publiées pour toute la chaîne planification + guide + chirurgie : < 2° et < 1 mm (pes varus du teckel), ≤ 5° et ≤ 5 mm acceptables.'
          : 'Modèle idéal : os rigide, repères anatomiques exacts, torsion corrigée par dérotation si besoin, tissus mous non modélisés. Sur un vrai patient, la précision dépend surtout du pointage des repères. Cibles publiées pour toute la chaîne planification + guide + chirurgie : < 2° et < 1 mm (pes varus du teckel), ≤ 5° et ≤ 5 mm acceptables.')),
      ];
    },
  },
  {
    id: 'guide', court: 'Guides de coupe', titre: () => 'Guides de coupe et de réduction',
    get vue() { return guidePret() ? { dir: 'face', focus: 'cora', r: 70 } : { dir: 'iso', focus: 'cora', r: 44 }; },
    legende: ['hinge', 'cut', 'pin', 'face'],
    coupe: true, broches: true, transparence: 0.5,
    dessin(P, ctx) {
      const O = P.osteo[ctx.kind], Sec = P.section;
      if (!O) return;
      if (ctx.guidePret) {                       // les pièces imprimables remplacent la flèche de la face d'appui
        if (ctx.guide.vue === 'coupe') dessinOsteo3D(P, ctx.kind, false);
        dessinBroches(P, ctx.kind);
        return;
      }
      dessinOsteo3D(P, ctx.kind, false);
      dessinBroches(P, ctx.kind);
      const cg = O.centreCoupe || P.coraC, fg = O.face;                   // centre du trait (règle 2 : décalé), face du guide
      const a = V.add(cg, V.mul(fg, Sec.largeur / 2 + 4)), b = V.add(cg, V.mul(fg, Sec.largeur / 2 + 24));
      OV.base.seg(a, b, COL.ok, 3);
      OV.base.label('face d\'appui du guide', V.add(b, V.mul(fg, 6)), 'ok');
    },
    texte(P, ctx) {
      const O = P.osteo[ctx.kind];
      if (!O) return [boiteSansOsteo(P)];
      return [
        boiteExercice(P),
        para('Tout ce qui précède se résume en quelques nombres que le <b>guide de coupe</b> doit matérialiser. Il s\'emboîte sur la surface de l\'os (empreinte tirée du CT) et ne peut se poser qu\'à un seul endroit ; il porte les fentes de scie et les manchons des broches. Un second guide, le <b>guide de réduction</b>, impose ensuite la position finale des fragments.'),
        tablePrescription(P, O, ctx.kind),
        boiteStrategie(P, O, ctx.kind),
        ...boiteGuide3D(P, O, ctx),
        boiteBrochesTorsion(P, O),
        boite('def', 'Exporter la prescription',
          para(`ZIP : prescription (JSON v2.2${P.reel ? ', avec la matrice pour revenir aux coordonnées du scanner' : ''}), os planifié (STL et .bin) et os corrigé prévu, os voisins (fibula, rotule, fabelles) et carte du cartilage quand ils sont connus, mode d'emploi. Pour reconstruire les mêmes guides hors de l'application : <code>etape7_guide.py --prescription … --os … --voisin … --cartilage …</code> (commande complète dans le LISEZ-MOI du ZIP).`),
          h('button', { type: 'button', class: 'btn', onclick: () => exporterGuide(PLAN, ctx.kind) }, 'Exporter la prescription (ZIP)'),
          h('p', { class: 'src', id: 'export-msg' }, '')),
      ];
    },
  },
  {
    id: 'tors', court: 'Et la torsion ?', titre: () => 'La torsion : pourquoi la radiographie ne suffit pas', vue: { dir: 'cc', focus: 'os' }, plan2D: 'F', fantome: true, legende: ['trans', 'width', 'ghost'],
    torsion: true,
    dessin(P, ctx) { dessinTorsion(P, ctx); },
    texte(P, ctx) { return texteTorsion(P, ctx); },
  },
];
// Ouverture ou fermeture : les critères du programme (recommanderCoin), le premier qui départage décide
function boiteRecommandation(P, ctx) {
  const R = P.recommandation;
  if (!R || !R.criteres?.length) return null;
  const val = (c, k) => {
    const x = c[k];
    if (c.id === 'longueur') return `${x >= 0 ? '+' : '−'}${fr(Math.abs(x), 1)} mm`;
    return x === true ? 'oui' : x === false ? 'non' : String(x);
  };
  const cls = (c, k) => (typeof c[k] === 'boolean' ? (c[k] ? 'oui' : 'non') : '');
  const lignes = R.criteres.map((c) => h('tr', { class: c.id === R.decisif ? 'decisif' : '' },
    h('td', {}, c.nom), h('td', { class: cls(c, 'fermeture') }, val(c, 'fermeture')), h('td', { class: cls(c, 'ouverture') }, val(c, 'ouverture')),
    h('td', {}, c.prefere ? (c.prefere === 'fermeture' ? 'ferm.' : 'ouv.') : '—')));
  const nomR = R.kind === 'fermeture' ? 'de fermeture' : 'd\'ouverture';
  return boite(R.kind === ctx.kind ? 'ok' : 'warn', 'Ouverture ou fermeture : comment le programme choisit',
    para(`Les critères sont examinés dans l'ordre ; le <b>premier qui départage</b> décide (ligne surlignée) : <b>coin ${nomR} recommandé</b>${R.kind === ctx.kind ? '' : ` ; vous regardez l'autre coin (choix manuel, panneau de gauche « Auto » pour revenir à la recommandation)`}.`),
    h('table', { class: 't compact crit' }, h('thead', {}, h('tr', {}, h('th', {}, 'Critère'), h('th', {}, 'Ferm.'), h('th', {}, 'Ouv.'), h('th', {}, 'Préfère'))), h('tbody', {}, lignes)),
    para('Règle de base : <b>la lame entre toujours du côté opposé à la charnière</b>. Coin de fermeture : elle entre par la corticale <b>convexe</b>, où le coin est retiré ; coin d\'ouverture : par la corticale <b>concave</b>, qui s\'ouvre. Le guide se pose sur cette face d\'entrée. C\'est donc l\'abord chirurgical qui décide quel coin garde sa charnière : au tibia, abordé par sa face médiale sous-cutanée, un <b>varus</b> se corrige par un coin d\'<b>ouverture</b> médial (charnière latérale), un <b>valgus</b> par un coin de <b>fermeture</b> médial (charnière latérale). Au fémur, abordé par la face latérale ou médiale, les deux coins sont possibles : les critères suivants départagent.'),
    h('p', { class: 'src' }, `Seuils (choix raisonnés du projet, à valider avec un chirurgien) : face d'entrée à ≤ ${ANGLE_ENTREE_COIN_MAX}° de la face du coin ; coin de fermeture ≥ 1,5 mm de matière entre les deux fentes ; ouverture ≤ ${Math.round(OUVERTURE_MAX_FRAC * 100)} % de la largeur de l'os ; inégalité de longueur prise en compte à partir de 3 mm (panneau de gauche).`));
}
// La charnière : position par défaut, profondeur réglée, meilleur endroit
function boiteCharniere(P, O, kind) {
  const cort = kind === 'fermeture' ? `concave (${sens3(P.bis.ccv, true)})` : `convexe (${sens3(P.bis.c, true)})`;
  return boite('def', 'La charnière : où elle est, où la placer',
    para(`<b>Par défaut</b> : sur la bissectrice transverse du CORA, à <b>${fr(CHARNIERE_RETRAIT, 0)} mm</b> à l'intérieur de la corticale ${cort}. Toute rotation autour d'un point de cette bissectrice réaligne les axes sans translation (règle de Paley) ; la lame s'arrête à ce point et laisse un pont d'os qui plie.`),
    para(`<b>Ici</b> : charnière à <b>${fr(O.h, 1)} mm</b> de la corticale ${cort} (profondeur y, réglable dans le panneau de gauche) ; la lame coupe ${mm(O.D)} depuis la corticale d'entrée.${O.coinMixte ? ' Coin mixte : ostéotomie complète.' : ''}`),
    h('ul', {},
      h('li', { html: '<b>Meilleur endroit</b> pour un coin d\'ouverture ou de fermeture : la corticale <b>opposée à l\'abord</b>, avec un pont fin (1 à 3 mm). Il plie sans casser, tient les fragments en place, empêche toute translation et limite la sous-correction (corticale latérale préservée : Petazzoni 2012).' }),
      h('li', { html: `<b>Plus profond</b> (pont plus épais) : il ne plie plus et casse de façon imprévisible. Coin de fermeture au-delà de ${PONT_MAX} mm : ostéotomie complète et coin <b>mixte</b> (moins d'os retiré côté convexe, ouverture côté concave). Coin d'ouverture : au plus ${CHARNIERE_OUVERTURE_MAX} mm, sinon la partie convexe derrière la charnière devrait se chevaucher.` }),
      h('li', { html: '<b>Au centre</b> de l\'os : coin <b>neutre</b> (Paley), moitié fermeture, moitié ouverture, la <b>longueur est conservée</b> ; ostéotomie complète, la stabilité vient de la plaque et du guide de réduction.' }),
      h('li', { html: 'Hors de la bissectrice (règle 3), la rotation laisse une translation entre les axes : à éviter.' })),
    sources('paley', 'petazzoni'));
}
// Contraintes chirurgicales (biologiques) au niveau de la coupe
function boiteContraintes(P, O) {
  const C = O.contraintes || [];
  const bloq = C.some((x) => x.niveau === 'bloquant');
  return boite(bloq ? 'warn' : 'def', 'Peut-on couper à ce niveau ?',
    para(`Trait de coupe ${O.z === 0 ? '<b>au CORA</b> (règle 1)' : `à <b>${fr(Math.abs(O.z), 0)} mm ${O.z < 0 ? 'au-dessus' : 'au-dessous'}</b> du CORA (règle 2)`} ; niveau réglable dans le panneau de gauche (z).`),
    h('ul', { class: 'contraintes' }, C.map((x) => h('li', { class: x.niveau }, x.texte))),
    para('<b>Ce qui interdit de couper à un niveau</b> : le cartilage et la capsule articulaire (fracture articulaire, arthrose) ; une physe ouverte chez le jeune (arrêt de croissance, nouvelle déformité) ; une insertion tendineuse ou ligamentaire (tubérosité tibiale et ligament patellaire, épicondyles et ligaments collatéraux) ; un fragment trop court pour la plaque (≥ 3 vis) et les broches ; une translation de règle 2 qui laisse trop peu de contact osseux. <b>Ce qui le déconseille</b> : la diaphyse et le tiers distal du tibia, moins vascularisés que la métaphyse (consolidation plus lente). <b>Ce qui se protège</b> : vaisseaux et nerfs du côté opposé à la lame (écarteur).'),
    h('p', { class: 'src' }, 'Physes : zones approchées en fraction de la longueur (non segmentées, à vérifier sur le scanner). Marges : choix raisonnés du projet, à valider avec un chirurgien.'));
}
// L'ostéotomie en dôme : quand, pourquoi elle n'est pas proposée, hypothèse retenue
function boiteDome(P, O) {
  return boite('def', 'Et l\'ostéotomie en dôme ?',
    para('<b>Quand l\'utilise-t-on ?</b> Quand on ne peut pas couper au CORA (CORA tout près de l\'articulation, ou dans une zone interdite) et qu\'on veut éviter la translation de la règle 2 : la coupe est un <b>cylindre centré sur le CORA</b> ; les fragments tournent l\'un sur l\'autre le long de cette coupe, autour du CORA, sans translation et en gardant le contact osseux. Elle est décrite au radius du chien pour les déformités à un ou deux apex (Fox 2006).'),
    para('<b>Pourquoi le programme ne la propose pas</b> : (1) il faut une lame courbe de rayon fixe et un guide qui fasse tourner la lame autour d\'un pivot, plus délicat à imprimer et à contrôler qu\'une fente plane ; (2) un dôme cylindrique ne tourne qu\'autour de son axe : il corrige l\'angulation, pas la torsion (une dérotation impose une coupe plane complète) ; (3) au fémur distal et au tibia, le CORA est le plus souvent dans une zone où la règle 1 est possible.'),
    para(`<b>Hypothèse retenue</b> : coupes planes guidées par des fentes, règle 1 par défaut ; si le niveau doit changer, règle 2 avec translation chiffrée et alerte au-delà de 50 % de la largeur de l'os.${O.regle === 2 ? ` Ici, un dôme centré sur le CORA aurait un rayon d'environ ${mm(O.decalageCoupe, 0)}.` : ''}`),
    sources('fox06', 'paley'));
}
// À quoi servent les broches ? (étape 10)
function boiteBroches(P, O) {
  const cfg = CONFIG_BROCHES[O.configBroches] || CONFIG_BROCHES['2+2'];
  return boite('def', 'À quoi servent les broches ?',
    h('ol', {},
      h('li', { html: '<b>Fixer le guide de coupe</b> sur l\'os pendant la coupe : il ne peut ni glisser ni basculer.' }),
      h('li', { html: '<b>Mémoriser la correction</b> : les broches distales sont forées avec l\'inverse de la correction (angle + dérotation). Quand les fragments sont à la position planifiée, toutes les broches deviennent <b>parallèles</b> : un repère visible immédiatement.' }),
      h('li', { html: '<b>Manipuler les fragments</b> : elles servent de poignées pendant la réduction.' }),
      h('li', { html: '<b>Porter le guide de réduction</b> : il s\'enfile sur les broches parallèles jusqu\'au contact de l\'os et tient la position pendant la pose de la plaque.' }),
      h('li', { html: '<b>Retirer le guide de coupe</b> : après la coupe des ponts, chaque moitié glisse le long de ses broches.' })),
    para(`<b>Configuration choisie : ${cfg.nom}.</b> ${O.configBroches === '1+1'
      ? 'Une broche par fragment : un fragment peut encore tourner autour de sa propre broche sans que le parallélisme change ; seuls les manchons du guide de réduction, au contact de l\'os, s\'y opposent (moins sûr pour la torsion).'
      : O.configBroches === '1+2'
        ? 'Le fragment distal (plus court, plus mobile, celui qui porte la dérotation) est tenu par deux broches côte à côte au même niveau (« horizontales ») : ses 6 degrés de liberté sont bloqués ; le fragment proximal, tenu par le membre, n\'en a qu\'une.'
        : 'Deux broches par fragment : un fragment ne peut plus tourner autour d\'une broche ; le guide de réduction bloque les 6 degrés de liberté de chaque fragment.'} Choix dans le panneau de gauche.`));
}
// Comment fonctionne la dérotation ? (étape 10)
function boiteDerotation(P, O, kind) {
  const T = P.torsion, der = Math.abs(O.derotation) >= DEROTATION_MIN;
  return boite('def', 'Comment fonctionne la dérotation ?',
    h('ol', {},
      h('li', { html: `<b>Mesure</b> : la torsion est l'angle, autour de l'axe long de l'os, entre un axe transverse proximal et un axe transverse distal (${P.bone === 'femur' ? 'fémur : axe du col contre ligne condylaire caudale, Al Aiyan 2021' : P.bone === 'radius' ? 'radius : axe médio-latéral de la tête radiale (perpendiculaire à la direction radius → ulna) contre grand axe de la surface carpienne, normale de Kroner 2017' : 'tibia : ligne condylaire caudale contre axe antécochléaire, Brühschwein 2023'}). Ici : ${deg(T.avant)} avant correction.` }),
      h('li', { html: `<b>Décision</b> : référence « valeurs normales » : on ne dérote que si la torsion sort des seuils publiés (${fr(T.normale.seuils[0], 0)} à ${fr(T.normale.seuils[1], 0)}°), jusqu'à la valeur moyenne (${fr(T.normale.m, 0)}°) ; référence « os sain » : jusqu'à la torsion de l'os sain. Seuil : ${fr(DEROTATION_MIN, 0)}°.` }),
      h('li', { html: `<b>Axe</b> : le fragment distal tourne autour de son propre axe long, choisi pour ne pas défaire la correction angulaire : ${kind === 'fermeture' ? 'coin de fermeture : autour de l\'axe distal, avant de refermer (la face distale, perpendiculaire à cet axe, tourne dans son plan et reste en face de la face proximale)' : 'coin d\'ouverture : autour de l\'axe réaligné, après l\'ouverture'}.` }),
      h('li', { html: '<b>Angle</b> : calculé par itérations (méthode de la sécante) pour que la torsion mesurée <b>après</b> toute la correction égale la cible : l\'angulation elle-même change la torsion mesurée de quelques dixièmes de degré.' }),
      h('li', { html: '<b>Conséquences</b> : une charnière corticale ne peut pas se tordre, l\'ostéotomie devient complète ; les broches distales sont forées avec l\'inverse de la correction <b>dérotation comprise</b> : le guide de réduction contrôle la torsion sans qu\'on ait à la mesurer pendant la chirurgie.' })),
    para(der ? `<b>Ici</b> : dérotation de <b>${deg(O.derotation)}</b> ; torsion ${deg(T.avant)} → ${deg(O.torsionApres)} (cible ${deg(O.torsionCible)}).` : `<b>Ici</b> : pas de dérotation (torsion ${deg(T.avant)}, ${T.statut === 'normale' ? 'dans la normale' : 'cible atteinte par la seule correction angulaire'}).`),
    sources('alaiyan', 'bruhT', 'longo'));
}
// Stratégie chirurgicale retenue par la planification : règle de Paley, abord, charnière ou coupe complète, broches
function boiteStrategie(P, O, kind) {
  const li = [];
  const choisi = P.optionsStrategie && P.optionsStrategie.decalageCoupe !== null;
  li.push(O.regle === 2
    ? `<b>Règle 2 de Paley</b> : ${choisi ? `coupe placée à ${mm(O.decalageCoupe, 0)} ${O.z < 0 ? 'au-dessus' : 'au-dessous'} du CORA (niveau choisi)` : `le CORA touche le cartilage articulaire ; la coupe est déplacée de ${mm(O.decalageCoupe, 0)} vers la diaphyse`}. La correction tourne toujours autour de l'ACA placé sur la bissectrice du CORA, ce qui réaligne les axes, mais le fragment distal <b>glisse de ${mm(O.translationOsteo, 1)}</b> le long de la coupe (translation à l'ostéotomie, prévue). Alternative classique : ostéotomie en dôme centrée sur le CORA (rayon ≈ ${mm(O.decalageCoupe, 0)}).`
    : '<b>Règle 1 de Paley</b> : coupe au CORA, charnière sur la bissectrice transverse ; pas de translation à l\'ostéotomie.');
  const face = nomDirection(O.face), faceCoin = nomDirection(O.faceCoin || O.face);
  const raisons = [O.regle === 2 ? 'la translation de la règle 2' : null, Math.abs(O.derotation) >= DEROTATION_MIN ? 'la dérotation' : null,
    O.h > PONT_MAX + 1e-9 ? `la charnière à ${fr(O.h, 1)} mm (pont trop épais pour plier)` : null].filter(Boolean);
  li.push(O.abordNonUsuel
    ? (O.voisinSurLame
      ? `<b>Abord non usuel</b> : la lame doit entrer par la face du coin (${faceCoin}) ; ${O.raisonAbord}. Un guide posé sur cette face occuperait l'espace entre l'os et ${O.voisinSurLame} : <b>aucun guide de coupe n'est construit</b> ; choisir le coin recommandé.`
      : `<b>Abord non usuel</b> : la lame doit entrer par la face du coin (${faceCoin}) ; ${O.raisonAbord || 'hors des abords usuels'}. Le guide y est posé quand même (il n'est jamais du côté de la charnière) ; le coin recommandé est plus simple.`)
    : O.charniereConservee
      ? `<b>Abord ${O.abord}</b> (face ${face}) : la lame entre du côté ${faceCoin}, la corticale opposée sert de charnière et reste intacte.`
      : O.ecartFace > 0
        ? `<b>Abord ${O.abord}</b> : face du coin (${faceCoin}) ${O.raisonAbord || 'hors des abords usuels'} ; le guide se pose sur la face accessible la plus proche (${face}, à ${fr(O.ecartFace, 0)}° de la face du coin, du côté opposé à la charnière) et l'<b>ostéotomie est complète</b>. Le guide de réduction fixe la position des fragments.`
        : `<b>Abord ${O.abord}</b> (face ${face}) : <b>ostéotomie complète</b>${raisons.length ? ` (${raisons.join(', ')} interdit de garder une charnière)` : ''}. Le guide de réduction fixe la position des fragments.`);
  const pb = O.placementBroches || {};
  const disp = (n, d, e) => (n === 1 ? 'une seule' : d === 'transversale' ? `côte à côte (écart ${mm(e, 1)})` : `l'une derrière l'autre (écart ${mm(e, 1)})`);
  li.push(`<b>Broches</b> (${(CONFIG_BROCHES[O.configBroches] || CONFIG_BROCHES['2+2']).nom}) : proximales ${disp(pb.nProx, pb.dispositionProx, pb.ecartProx)}, distales ${disp(pb.nDist, pb.dispositionDist, pb.ecartDist)}${pb.beta ? ` ; tournées de ${fr(pb.beta, 0)}° autour de l'os` : ''}${pb.decalageProx || pb.decalageDist ? ' ; groupe décalé de la ligne centrale' : ''}, hors du cartilage (≥ 3 mm), à ≥ 2 mm des os voisins, manchons hors des tours de fente, entrée sur la corticale à moins de ${ANGLE_ENTREE_MAX}° de la normale.`);
  const autres = (O.alertes || []).filter((a) => /trop fin|contact osseux|impossible|dans le cartilage|os voisin|trop près|oblique|manchon|non réalisable|aucune position|du cartilage \(minimum|épais/.test(a));
  return boite(autres.length ? 'warn' : 'def', 'Stratégie chirurgicale', h('ul', {}, ...li.map((x) => h('li', { html: x }))),
    autres.length ? h('ul', {}, ...autres.map((a) => h('li', {}, a))) : null);
}
// ------------------------------------------------------------ étape 12 : prescription et guides --
function tablePrescription(P, O, kind) {
  const largeurFente = INSTRUMENT.lame + INSTRUMENT.jeuFente, nb = (O.brochesReduction || O.broches).length;
  return h('table', { class: 't enveloppe' }, h('caption', {}, `Prescription (${kindNom[kind]})`),
    h('tbody', {},
      h('tr', {}, h('td', {}, 'Angle de correction θ (angle entre les fentes ou ouverture)'), h('td', { class: 'hi' }, deg(P.theta))),
      h('tr', {}, h('td', {}, 'Dérotation (torsion)'), h('td', { class: 'hi' }, Math.abs(O.derotation) >= DEROTATION_MIN ? `${deg(O.derotation)} (${deg(P.torsion.avant)} → ${deg(O.torsionApres)})` : 'aucune')),
      h('tr', {}, h('td', {}, 'Fentes de scie (lame + jeu)'), h('td', { class: 'hi' }, `${O.plans.length} × ${mm(largeurFente)}`)),
      h('tr', {}, h('td', {}, 'Charnière : corticale'), h('td', { class: 'hi' }, sens3(kind === 'fermeture' ? P.bis.ccv : P.bis.c, true))),
      h('tr', {}, h('td', {}, 'Charnière : profondeur y (depuis cette corticale)'), h('td', { class: 'hi' }, `${mm(O.h)}${O.coinMixte ? ' (coin mixte)' : ''}`)),
      h('tr', {}, h('td', {}, 'Niveau du trait z (depuis le CORA)'), h('td', { class: 'hi' }, Math.abs(O.z) < 0.5 ? 'au CORA' : `${O.z > 0 ? '+' : '−'}${mm(Math.abs(O.z), 0)} (${O.z > 0 ? 'distal' : 'proximal'})`)),
      h('tr', {}, h('td', {}, 'Face d\'appui du guide (entrée de la lame)'), h('td', { class: 'hi' }, `${nomDirection(O.face)}${O.abordNonUsuel ? ' (abord non usuel)' : ''}`)),
      h('tr', {}, h('td', {}, 'Orientation de la charnière ψ (0° = crânio-caudale)'), h('td', { class: 'hi' }, deg(P.psi))),
      h('tr', {}, h('td', {}, 'Règle de Paley'), h('td', { class: 'hi' }, O.regle === 2 ? `2 : coupe à ${mm(O.decalageCoupe, 0)} du CORA, translation ${mm(O.translationOsteo, 1)}` : '1 : coupe au CORA')),
      h('tr', {}, h('td', {}, 'Abord / coupe'), h('td', { class: 'hi' }, `${O.abord || 'n.d.'} ; ${O.charniereConservee ? 'charnière conservée' : 'ostéotomie complète'}`)),
      h('tr', {}, h('td', {}, O.charniereConservee ? 'Profondeur de coupe (arrêt avant la charnière)' : 'Profondeur de coupe (charnière → corticale opposée)'), h('td', { class: 'hi' }, mm(O.D))),
      h('tr', {}, h('td', {}, kind === 'fermeture' ? 'Base du coin' : 'Ouverture'), h('td', { class: 'hi' }, mm(O.base))),
      h('tr', {}, h('td', {}, `Broches de réduction (Ø ${fr(INSTRUMENT.broche)} mm)`), h('td', { class: 'hi' }, `${nb} (${O.configBroches || '2+2'})`)),
      h('tr', {}, h('td', {}, 'Angle entre broches proximales et distales (avant correction)'), h('td', { class: 'hi' }, deg(O.angleBroches))),
      h('tr', {}, h('td', {}, 'Translation résiduelle prévue'), h('td', { class: 'hi' }, mm(O.decalage, 2)))));
}
// construction des guides par le serveur (étape 7), résultats et contrôles
function boiteGuide3D(P, O, ctx) {
  const Gd = ctx.guide;
  if (!ctx.serveur) {
    return [boite('warn', 'Guides imprimables (étape 7)', para('La construction des guides 3D se fait dans l\'application CT-CORA3D (serveur local). Ouvert seul, ce fichier prépare seulement la prescription : exportez le ZIP ci-dessous et lancez <code>etape7_guide.py</code>.'))];
  }
  if (Gd.etat === 'calcul') {
    return [boite('def', 'Construction des guides en cours',
      para(`Distance à l'os sur une grille de 0,3 mm, coque moulée sans contre-dépouille, fentes et trous exacts, guide de réduction, contrôles (≈ 30 s)…`),
      h('pre', { class: 'journal', id: 'guide-journal', 'aria-live': 'polite' }, Gd.journal.length ? Gd.journal.join('\n') : 'Démarrage…'))];
  }
  // face du coin derrière un os voisin (fibula…) : un guide y occuperait l'espace entre les deux os, où l'on ne peut ni
  // le glisser, ni le fixer, ni couper ; le serveur le refuse (etape7_guide.verifier_abord) : on l'explique ici
  if (!ctx.guidePret && O.abordNonUsuel && O.voisinSurLame) {
    const reco = P.recommandation?.kind;
    return [boite('warn', 'Guide de coupe impossible pour ce coin',
      para(`Pour ce ${kindNom[ctx.kind]}, la lame doit entrer par la face ${nomDirection(O.faceCoin)}, où <b>${O.voisinSurLame}</b> est sur son trajet. Un guide posé sur cette face occuperait <b>l'espace entre l'os et ${O.voisinSurLame}</b> : le chirurgien ne pourrait ni l'y glisser, ni le fixer avec ses broches, ni couper. Le programme ne construit donc pas ce guide.`),
      para(reco && reco !== ctx.kind ? `Choisissez le <b>${kindNom[reco]}</b> (conseillé) dans « Type de coin », à gauche : sa face d'entrée est accessible et l'espace entre les deux os reste libre.` : 'Changez de type de coin ou de niveau de coupe.'))];
  }
  if (!ctx.guidePret) {
    return [boite('ok', 'Construire les guides imprimables',
      para(`Pour <b>cet os</b> et ce ${kindNom[ctx.kind]}, le programme construit :`),
      h('ul', {},
        h('li', { html: `le <b>guide de coupe</b> : coque moulée sur l'os (jeu ${fr(ctx.guideParams.jeu_mm ?? 0.3, 2)} mm, épaisseur ${fr(ctx.guideParams.epaisseur_coque_mm ?? 3, 1)} mm, sans contre-dépouille), ${O.plans.length === 2 ? 'deux fentes' : 'une fente'} de scie dans les plans prescrits, ${(O.brochesReduction || O.broches).length} manchons de broches ; deux moitiés reliées par <b>2 ponts sécables</b>, pour que chaque moitié sorte le long de ses broches ; la profondeur de lame de chaque fente est donnée dans le mode opératoire ; entrées chanfreinées, arêtes arrondies ;` }),
        h('li', { html: `le <b>guide de réduction</b> : ${(O.brochesReduction || O.broches).length} manchons parallèles qui s'enfilent sur les broches après la correction et s'appuient sur l'os corrigé ;` }),
        h('li', { html: 'les <b>plans 2D</b> : plan générique (cotes en symboles, tableau des paramètres) et plan coté de ce guide (vues orthogonales, échelle sur A3) ;' }),
        h('li', {}, 'des contrôles indépendants : jeu mesuré, interpénétration, retrait de chaque moitié (lancer de rayons et balayage), étanchéité des STL.')),
      Gd.etat === 'erreur' ? boite('warn', 'Échec', para(Gd.erreur || 'erreur inconnue')) : null,
      h('button', { type: 'button', class: 'btn primary', onclick: () => ctx.construireGuide() }, Gd.etat === 'erreur' ? 'Réessayer' : 'Construire les guides 3D'))];
  }
  const I = Gd.info, C = I.guide_coupe, R = I.guide_reduction;
  const NOMS_VOISINS = { fibula: 'fibula', ulna: 'ulna', patella: 'rotule', fabellae: 'fabelles' };
  const tag = (ok, oui = 'oui', non = 'non') => h('span', { class: `tag ${ok ? 'ok' : 'bad'}` }, ok ? oui : non);
  const ligne = (a, b) => h('tr', {}, h('td', {}, a), h('td', { class: 'hi' }, ...[b].flat()));
  const piece = C.pieces[0];
  const fichier = (n, txt) => (I.disponibles.includes(n) ? h('a', { class: 'btn petit', href: fichierGuide(Gd.dossier, n, true), download: n }, txt) : null);
  const vue = h('div', { class: 'seg', role: 'group', 'aria-label': 'Pièce affichée' },
    h('button', { type: 'button', 'aria-pressed': String(Gd.vue === 'coupe'), onclick: () => ctx.vueGuide('coupe') }, 'Guide de coupe'),
    h('button', { type: 'button', 'aria-pressed': String(Gd.vue === 'reduction'), onclick: () => ctx.vueGuide('reduction') }, 'Guide de réduction'));
  const out = [
    boite('ok', 'Guides imprimables construits', vue,
      para(Gd.vue === 'coupe'
        ? 'Guide de coupe sur l\'os, avant la coupe : moitié proximale en bleu, moitié distale en vert, ponts sécables en orange.'
        : 'Os corrigé (angle et dérotation) : les broches sont parallèles et le guide de réduction (violet) s\'y enfile jusqu\'au contact de l\'os.'),
      h('table', { class: 't compact enveloppe' }, h('caption', {}, 'Contrôles du guide de coupe'), h('tbody', {},
        ligne('Jeu minimal entre guide et os (mesuré)', [mm(C.jeu_minimal_mesure_mm, 2), ' ', tag(C.jeu_minimal_mesure_mm >= C.jeu_demande_mm - 0.05, `≥ ${fr(C.jeu_demande_mm)}`, 'trop proche')]),
        ligne('Interpénétration avec l\'os', `${fr(C.volume_interpenetration_mm3 ?? 0, 2)} mm³`),
        ligne('Surface d\'appui (jeu ≤ 0,45 mm)', `${fr(C.surface_appui_mm2, 0)} mm²`),
        ligne('STL étanche (relu)', tag(C.etanche_stl)),
        ligne('Pièces après coupe des ponts', [String(C.moities_apres_coupe_des_ponts), ' ', tag(C.moities_apres_coupe_des_ponts === (C.pieces_attendues ?? 2), 'deux moitiés')]),
        ligne('Retrait sans heurter l\'os ni l\'autre moitié', Object.entries(C.retrait).map(([k, r]) => h('span', {}, `${k} `, tag(r.libre), ' '))),
        ligne('Ordre de retrait', `moitié ${C.ordre_retrait[0]}, puis ${C.ordre_retrait[1]}`),
        C.appui_moities ? ligne('Appui de chaque moitié (seule sur ses broches)', Object.entries(C.appui_moities).map(([k, a]) => h('span', {}, `${k} ${fr(a.surface_mm2, 0)} mm² sur ${fr(a.couverture_deg, 0)}° `, tag(a.surface_mm2 >= 100), ' '))) : null,
        ...Object.entries(I.voisins_et_cartilage?.voisins || {}).map(([n, r]) => ligne(`Jeu entre guide et ${NOMS_VOISINS[n] || n}`, [r.distance_guide_mm === null ? 'loin' : mm(r.distance_guide_mm, 1), ' ', tag(r.distance_guide_mm === null || r.distance_guide_mm >= (I.parametres.jeu_voisin_mm ?? 1) - 0.1, `≥ ${fr(I.parametres.jeu_voisin_mm ?? 1)}`, 'trop proche')])),
        I.voisins_et_cartilage?.cartilage ? ligne('Distance entre guide et cartilage articulaire', I.voisins_et_cartilage.cartilage.distance_guide_mm === null
          ? ['loin (aucun cartilage près du guide) ', tag(true, 'hors du cartilage')]
          : [mm(I.voisins_et_cartilage.cartilage.distance_guide_mm, 1), ' ', tag(I.voisins_et_cartilage.cartilage.distance_guide_mm >= 1, 'hors du cartilage', 'sur le cartilage')]) : null,
        ligne('Distance entre broches et trajet de la lame', [mm(Math.min(...C.broches.map((b) => b.distance_trajet_lame_mm ?? 99)), 1), ' ', tag(C.broches.every((b) => (b.distance_trajet_lame_mm ?? 99) >= 0.3), 'libre', 'la lame touche une broche')]),
        ...C.fentes.map((f) => ligne(`Fente ${f.plan}${f.role.startsWith('séparation') ? ' (séparation)' : ''}`, `${mm(f.largeur_mm)} × ${mm(f.longueur_mm, 0)} ; guidage ${mm(f.guidage_mm, 0)} (lame ± ${deg(f.inclinaison_max_lame_deg)}) ; lame enfoncée de ${mm(f.profondeur_lame_mm, 1)} depuis le haut de la tour (jusqu'à la ${f.arret_lame ?? (O.charniereConservee ? 'charnière' : 'corticale opposée')})${f.chanfrein_entree_mm ? ` ; entrée chanfreinée ${mm(f.chanfrein_entree_mm, 1)}` : ''}`)),
        C.epaisseur_entre_fentes_mm !== null && C.epaisseur_entre_fentes_mm !== undefined ? ligne('Matière entre les deux fentes', mm(C.epaisseur_entre_fentes_mm)) : null,
        ligne('Broches : angle entre les paires', `${deg(C.angle_paires_broches_deg)} (parallélisme dans chaque paire : ${deg(Math.max(C.parallelisme_paire_proximale_deg, C.parallelisme_paire_distale_deg), 2)})`),
        ligne('Pièce (PA12)', `${fr(piece.masse_g, 1)} g · ${piece.dimensions_mm.map((x) => fr(x, 0)).join(' × ')} mm`))),
      R ? h('table', { class: 't compact enveloppe' }, h('caption', {}, 'Contrôles du guide de réduction'), h('tbody', {},
        ligne('Distance entre barre et os corrigé', [mm(R.distance_barre_os_mm), ' ', tag(R.distance_barre_os_mm >= R.ecart_demande_mm - 0.5, `≥ ${fr(R.ecart_demande_mm, 0)}`, 'trop proche')]),
        ligne('Jeu minimal avec l\'os corrigé', mm(R.jeu_minimal_mesure_mm, 2)),
        ligne('Manchons parallèles', deg(R.parallelisme_manchons_deg, 3)),
        ligne('Broches à laisser dépasser de l\'os', `≥ ${mm(R.longueur_broche_hors_os_min_mm, 0)}`),
        ligne('STL étanche (relu)', tag(R.etanche_stl)))) : null),
  ];
  out.push(I.alertes.length
    ? boite('warn', 'Alertes', h('ul', {}, I.alertes.map((a) => h('li', {}, a))))
    : boite('ok', 'Aucune alerte', para(`Jeu respecté partout, pas d'interpénétration, retrait libre de chaque moitié, STL étanches.`)));
  if (I.disponibles.includes('plan_guide.png')) {
    out.push(boite('def', 'Plans 2D du guide',
      para('<b>Plan coté</b> de ce guide (vues orthogonales, cotes en mm, échelle indiquée sur A3) et <b>plan générique</b> (le modèle paramétrique : cotes en symboles, tableau des paramètres, formules des dimensions qui découlent de l\'os). Cliquez sur l\'image pour l\'agrandir.'),
      h('a', { href: fichierGuide(Gd.dossier, 'plan_guide.png'), target: '_blank', rel: 'noopener' }, h('img', { class: 'plan2d', src: fichierGuide(Gd.dossier, 'plan_guide.png'), alt: 'Plan coté du guide de coupe' })),
      h('div', { class: 'ligne-btn' },
        fichier('plan_guide.pdf', 'Plan coté (PDF)'), fichier('plan_guide.svg', 'Plan coté (SVG)'),
        fichier('plan_generique.pdf', 'Plan générique (PDF)'), fichier('plan_generique.svg', 'Plan générique (SVG)'), fichier('plan_generique.png', 'Plan générique (PNG)')),
      Object.keys(I.parametres_modifies || {}).length ? h('p', { class: 'src' }, `Dimensions changées pour ce cas : ${Object.entries(I.parametres_modifies).map(([k, v]) => `${k} = ${fr(v, 2)}`).join(', ')}.`) : null));
  }
  out.push(boite('def', 'Mode opératoire', h('ol', {}, I.protocole.map((l) => h('li', {}, l)))));
  out.push(boite('def', 'Fichiers', h('div', { class: 'ligne-btn' },
    fichier('guide_coupe.stl', 'Guide de coupe (STL)'), fichier('guide_reduction.stl', 'Guide de réduction (STL)'),
    fichier('guide_coupe_scanner.stl', 'Guide de coupe, repère du scanner'), fichier('os_corrige.stl', 'Os corrigé (STL)'),
    fichier('guide.json', 'Contrôles (JSON)'), fichier('guide.png', 'Aperçu (PNG)')),
    h('div', { class: 'ligne-btn' },
      h('button', { type: 'button', class: 'btn petit', onclick: montrerDossierGuide }, 'Ouvrir le dossier'),
      h('button', { type: 'button', class: 'btn petit', onclick: () => ctx.construireGuide() }, 'Reconstruire')),
    h('p', { class: 'src' }, `Dossier : resultats/${Gd.dossier}. Impression conseillée : PA12 (frittage laser) ou résine stérilisable ; imprimer d'abord des coupons de fente et de manchon pour régler les jeux (0,2 mm). Prototype de recherche, non validé cliniquement.`)));
  return out;
}
// contrôle de la torsion : broches, guide de réduction ou autres moyens
function boiteBrochesTorsion(P, O) {
  const der = Math.abs(O.derotation) >= DEROTATION_MIN;
  return boite('def', 'Contrôle de la torsion',
    para('Le contrôle de la torsion exige un moyen de bloquer la rotation des fragments, pas nécessairement des broches. Deux broches seules le font mal :'),
    h('ul', {},
      h('li', { html: 'avec <b>une broche par fragment</b>, on juge le parallélisme à l\'œil (quelques degrés de précision), et une rotation du fragment <b>autour de sa propre broche</b> ne change rien au parallélisme ;' }),
      h('li', { html: 'avec un <b>guide de coupe seul</b>, la rotation est l\'erreur qui reste : 1 membre sur 7 réopéré pour une rotation mal corrigée (Worth 2019).' })),
    para(`<b>Ici</b> : ${(CONFIG_BROCHES[O.configBroches] || CONFIG_BROCHES['2+2']).nom}, forées à travers le guide de coupe ; les distales avec l'inverse de la correction${der ? ` (angle θ + dérotation de ${deg(O.derotation)})` : ''}. Après la correction, les ${(O.brochesReduction || O.broches).length} broches sont parallèles et le <b>guide de réduction</b> s'enfile jusqu'au contact de l'os : il n'y parvient que si les 6 degrés de liberté sont bons${O.configBroches === '1+1' ? ' (avec une broche par fragment, la rotation autour de chaque broche n\'est tenue que par les appuis sur l\'os)' : ''}. La torsion est <b>contrôlée sans être mesurée</b>.`),
    para('Avec des guides de réduction, les publications rapportent une torsion à 1,7 ± 2,1° de la cible (fémur, Hall 2019), 2,6 ± 1,3° dans le plan transverse (tibia, Jeon 2023), moins de 2° et 1 mm dans tous les plans (pes varus, Bright 2024), plus de 90 % des paramètres à ≤ 5° (De Armond 2022).'),
    para('<b>Sans broches</b> : une <b>plaque sur mesure</b> (imprimée en titane : Carwardine 2021) dont les trous de vis sont percés à travers le guide de coupe avant l\'ostéotomie impose la position une fois vissée ; des <b>repères de rotation</b> tracés de part et d\'autre du trait (décalés de la valeur prévue après dérotation) ; un contrôle peropératoire (fluoroscopie, scanner) ou la navigation. La plaque sur mesure n\'est pas proposée par l\'application ; le guide de réduction reste le plus simple à vérifier.'),
    sources('worth19', 'hall19', 'jeon23', 'bright24', 'dearmond22', 'carwardine21'));
}

// étape 1, os segmenté : provenance, côté, repères, dépistage des angles, indication
function texteCasReel(P) {
  const R = P.reel, cles = [...CLES[P.bone].F, ...CLES[P.bone].S], v = P.validation;
  const lignesOs = [
    ['Série CT', nomSerie(R.serie)],
    ['Os', `${LeOs(P)} ${R.cote === 'gauche' ? 'gauche' : 'droit'}${R.miroir ? ' (miroir)' : ''}`],
    ['Longueur', mm(R.longueur_mm, 0)],
    ['Repères automatiques', `${Object.keys(R.reperes).length} (étape 6)`],
  ];
  const out = [
    para(`Os analysé : ${leOs(P)} <b>segmenté sur le scanner</b> (onglet 1). Ses repères anatomiques ont été placés <b>automatiquement</b> (étape 6) : ce sont eux, et non l'os fictif, que la méthode CORA utilise ici.`),
    lignes(lignesOs),
    R.miroir ? para('Membre gauche : il est analysé en <b>miroir</b>, comme un membre droit (mêmes conventions que l\'os fictif) ; la prescription exportée garde la matrice pour revenir au scanner.') : null,
  ];
  if (R.avertissements?.length) out.push(boite('warn', 'À vérifier', ...R.avertissements.map((a) => para(a))));
  if (P.D) {
    out.push(boite('def', 'Déformité de test (simulation)',
      para(`On a imposé à cet os réel une déformité connue : <b>${deg(P.thetaF, 0)} de ${P.frontal}</b>${P.sagittal === 'aucun' ? '' : ` + <b>${deg(P.thetaS, 0)} de ${P.sagittal}</b>`}, apex à ${fr(P.niveau * 100, 0)} % de la longueur (θ vrai = ${deg(v.thetaVrai)}). L'octaèdre marque l'apex imposé ; l'os avant déformité est en transparence.`),
      para(`Référence : <b>${nomRef(P)}</b>. ${P.reference === 'sain' ? 'La méthode doit retrouver exactement la déformité imposée.' : 'L\'écart à la déformité imposée montrera l\'effet de la variation naturelle de cet os par rapport aux normes.'}`)));
  }
  out.push(tableMesures(P, P.mesures.pre, 'Dépistage : angles articulaires de cet os', cles, 'Cet os'));
  out.push(P.anomalies.length
    ? boite('warn', 'Angles hors normes', para(`${horsNormes(P, cles)} : écart de plus de 2 écarts-types à la référence. La suite cherche la déformité (CORA, angle vrai, plan).`))
    : boite('ok', 'Angles dans les normes', para(`Tous les angles sont à moins de 2 écarts-types de la référence (${nomRef(P)}) : <b>pas de déformité significative</b>.${P.D ? '' : ' Pour suivre toute la planification sur cet os, activez une déformité de test (panneau de gauche).'}`)));
  out.push(boiteNormales(P));
  out.push(para(`Les points ${P.D ? 'marquent' : 'montrent'} les repères détectés ; tournez la vue pour les vérifier.`));
  out.push(P.bone === 'radius' ? sources('paley', 'fox06', 'kwon22', 'duncan22', 'kroner17') : sources('paley', 'dismukes', 'dismukes08', 'tomlinson'));
  return out;
}
// Radius : comment sont construits les axes des deux segments (étape « Frontal : axes et CORA »)
function paraAxesRadius(P) {
  const n = P.mesures.normal;
  return P.axeDist.depuis.startsWith('ligne articulaire')
    ? para(`<b>Axe proximal</b> : l'axe anatomique du segment proximal (milieux de la diaphyse à 20 et 40 %), sain chez ce chien. <b>Axe distal</b> : le segment distal est court et déformé ; on part donc de la <b>surface carpienne</b> avec les angles <b>normaux</b> LDRA (${deg(n.LDRA)}) et CdDRA (${deg(n.CdDRA)}), comme Fox (2006), puis on retire la courbure normale du radius (procurvatum ${deg(n.procurvatum)}, moitié du valgus normal) : un radius normal donnerait deux axes parallèles. De profil, l'axe distal croise l'axe proximal au niveau du CORA de face (une seule angulation).`)
    : para('<b>Axe proximal</b> : milieux de la diaphyse à 20 et 40 %. <b>Axe distal</b> : milieux à 60 et 80 %, moins la courbure normale du radius (pas de normes articulaires pour ce cas).');
}

// valeur de l'angle projeté de l'axe construit (vue k, segment) — utilisée dans le texte de l'étape 4
function arcValeur(P, k, seg) {
  const sp = SPEC[P.bone][k][seg], to2 = VUE[k].to2, axe = seg === 'prox' ? P.axeProx : P.axeDist;
  return P2.angU(P2.sub(to2(P.L[sp.a[1]]), to2(P.L[sp.a[0]])), P2.mul(P2.norm(to2(axe.d)), sp.s));
}

// ------------------------------------------------------------ étape torsion --
function dessinTorsion(P, ctx) {
  const T = ctx.torsion, L = T.L, A = T.m?.axes || axesTorsion(P.bone, L), b = P.ref.ax;     // définition utilisée (publiée si possible)
  // axes transverses en 3D (scanner)
  for (const [k, nom] of [['prox', A.nomProx], ['dist', A.nomDist]]) {
    const [a, c] = A[k].map((key) => L[key]);
    const d = V.norm(V.sub(c, a));
    OV.base.seg(V.sub(a, V.mul(d, 8)), V.add(c, V.mul(d, 8)), COL.trans, 3);
    OV.base.label(nom, V.add(c, V.mul(d, 14)), 'trans');
  }
  // largeur projetée sur la radiographie crânio-caudale (épicondyles ou malléoles)
  const [k1, k2] = P.bone === 'femur' ? ['epi_med', 'epi_lat'] : ['mall_med', 'mall_lat'];
  const y = (L[k1][1] + L[k2][1]) / 2, z = P.coraC[2];
  const xs = [L[k1][0], L[k2][0]];
  OV.base.seg([xs[0], y, z], [xs[1], y, z], COL.cut, 2.6);
  for (const x of xs) OV.base.seg([x, y - 5, z], [x, y + 5, z], COL.cut, 2);
  OV.base.label(`largeur projetée ${mm(T.m.radio.epicondyles)}`, [Math.max(...xs) + 34, y, z], 'cut');
  // les deux axes transverses ramenés dans un même plan transverse, sous l'os (lisible en vue axiale)
  const yc = b.y_bot + 10;
  const proj = (key) => { const p = L[key]; return [p[0], yc, p[2]]; };
  const tp = V.norm(V.sub(proj(A.prox[1]), proj(A.prox[0]))), td = V.norm(V.sub(proj(A.dist[1]), proj(A.dist[0])));
  const c0 = V.mid(proj(A.dist[0]), proj(A.dist[1]));
  OV.base.seg(V.sub(c0, V.mul(td, 22)), V.add(c0, V.mul(td, 22)), COL.trans, 1.6, { opacity: 0.6 });
  OV.base.seg(V.sub(c0, V.mul(tp, 22)), V.add(c0, V.mul(tp, 22)), COL.trans, 1.6, { dashed: true, dashSize: 3, gapSize: 3, opacity: 0.8 });
}
function courbeTorsionSVG(P, T) {
  const W = 340, H = 150, m = { l: 38, r: 10, t: 12, b: 28 };
  const pts = T.courbe, xs = pts.map((p) => p.a), ys = pts.map((p) => p.largeur);
  const x0 = xs[0], x1 = xs[xs.length - 1], yMax = Math.max(...ys), y0 = Math.floor(Math.min(...ys) - 1), y1 = Math.ceil(yMax + 1);
  const X = (a) => m.l + (a - x0) / (x1 - x0) * (W - m.l - m.r), Y = (v) => m.t + (y1 - v) / (y1 - y0) * (H - m.t - m.b);
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.a).toFixed(1)},${Y(p.largeur).toFixed(1)}`).join('');
  const prec = 0.5;                                    // précision de mesure sur la radiographie (mm)
  const aCur = T.tau + T.rho, wCur = T.m.radio.epicondyles;          // rotation totale de l'extrémité distale
  const ticksX = [-40, -20, 0, 20, 40].map((a) => `<line x1="${X(a)}" x2="${X(a)}" y1="${H - m.b}" y2="${H - m.b + 4}" stroke="var(--fg-3)"/><text x="${X(a)}" y="${H - m.b + 15}" text-anchor="middle">${a}°</text>`).join('');
  const ticksY = [y0, Math.round((y0 + y1) / 2), y1].map((v) => `<text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`).join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Largeur projetée en fonction de la rotation de l'extrémité distale">
    <rect x="${m.l}" y="${Y(yMax)}" width="${W - m.l - m.r}" height="${Y(yMax - prec) - Y(yMax)}" fill="var(--c-cut)" opacity=".14"/>
    <line x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${H - m.b}" stroke="var(--line)"/><line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}" stroke="var(--line)"/>
    ${ticksX}${ticksY}
    <path d="${path}" fill="none" stroke="var(--c-cut)" stroke-width="2"/>
    <circle cx="${X(clamp(aCur, x0, x1))}" cy="${Y(wCur)}" r="4.5" fill="var(--c-cora)"/>
    <text x="${W - m.r}" y="${Y(yMax) - 3}" text-anchor="end" fill="var(--fg-3)">bande ±${fr(prec)} mm : rotation indétectable</text>
    <text x="${(W + m.l) / 2}" y="${H - 1}" text-anchor="middle">rotation de l'extrémité distale par rapport au film</text>
  </svg>`;
}
function texteTorsion(P, ctx) {
  const T = ctx.torsion, m = T.m, m0 = T.m0, A = m?.axes || axesTorsion(P.bone, T.L);
  const W0 = Math.max(...T.courbe.map((p) => p.largeur));
  const aPrec = Math.acos(1 - 0.5 / W0) * DEG, aMag = Math.acos(0.95) * DEG;
  const rad = P.bone === 'radius';
  const nomAngle = P.bone === 'femur' ? 'angle de torsion fémorale (antéversion)' : rad ? 'angle de torsion radiale' : 'angle de torsion tibiale';
  const [bProx, bDist] = P.bone === 'femur' ? ['la hanche', 'du genou'] : rad ? ['le coude', 'du carpe'] : ['le genou', 'du jarret'];
  const bDistNu = P.bone === 'femur' ? 'le genou' : rad ? 'le carpe' : 'le jarret';
  const seuil = P.bone === 'femur' ? 'antéversion < 20° : torsion externe ; > 35° : torsion interne'
    : rad ? 'torsion radiale du chien sain 3,6 ± 6,4° (Kroner 2017) : au-delà de +16,4°, torsion externe ; en deçà de −9,2°, torsion interne (± 2 écarts-types)'
      : 'torsion tibiale < −10° : torsion interne ; > +2° : torsion externe (− interne, + externe)';
  const largeurNom = P.bone === 'femur' ? 'épicondylienne' : rad ? 'bistyloïdienne (styloïdes du radius et de l\'ulna)' : 'bimalléolaire';
  const curseurs = h('div', { class: 'sliders' },
    curseur('t-tau', 'Torsion de l\'os τ (anatomique)', -40, 40, 1, T.tau, (x) => `${x > 0 ? '+' : ''}${fr(x, 0)}°`, (x) => ctx.setTorsion(x, null), 'interne', 'externe'),
    curseur('t-rho', 'Rotation sur la table ρ (positionnement)', -40, 40, 1, T.rho, (x) => `${x > 0 ? '+' : ''}${fr(x, 0)}°`, (x) => ctx.setTorsion(null, x), 'vers médial', 'vers latéral'),
    h('div', { class: 'seg', role: 'group', 'aria-label': 'Exemples' },
      h('button', { type: 'button', onclick: () => ctx.setTorsion(20, 0, true) }, 'τ = 20°'),
      h('button', { type: 'button', onclick: () => ctx.setTorsion(0, 20, true) }, 'ρ = 20°'),
      h('button', { type: 'button', onclick: () => ctx.setTorsion(20, -20, true) }, 'τ = 20°, ρ = −20°'),
      h('button', { type: 'button', onclick: () => ctx.setTorsion(0, 0, true) }, '0')));
  const JT = P.reel ? S.reel.json?.torsion : null;
  const nomStatut = { normale: 'dans la normale', externe: 'torsion externe', interne: 'torsion interne' };
  const statutDe = (t) => { const sl = TORSION_NORMALE[P.bone].seuils; return t < sl[0] ? (P.bone === 'femur' ? 'externe' : 'interne') : t > sl[1] ? (P.bone === 'femur' ? 'interne' : 'externe') : 'normale'; };
  const mesureReel = JT ? boite(JT.statut === 'normale' ? 'ok' : 'warn', 'Mesure sur cet os (scanner)',
    para(`${P.bone === 'femur' ? 'Antéversion fémorale' : rad ? 'Torsion radiale' : 'Torsion tibiale'} de l'os segmenté : <b>${deg(JT.valeur_deg)}</b>, ${nomStatut[JT.statut] || JT.statut} (normale ${fr(JT.normale.m, 0)}°${JT.normale.sd ? ` ± ${fr(JT.normale.sd, 0)}°` : ''} ; ${seuil}).`),
    para(`Définition publiée : ${JT.definition}.`),
    rad && isNum(S.reel.json?.torsion_coude_deg) ? para(`Par rapport au <b>coude</b> (axe des condyles de l'humérus), le carpe est tourné de ${deg(S.reel.json.torsion_coude_deg)} : cette valeur inclut la position de l'avant-bras sur la table (pronation, supination), pas seulement la torsion de l'os ; elle n'est qu'indicative.`) : null,
    !rad && isNum(JT.definition_cora3d_deg) ? para(`Avec l'autre définition courante (${P.bone === 'femur' ? 'axe du col au ras de la tête' : 'axe bimalléolaire'}), ce même os donnerait ${deg(JT.definition_cora3d_deg)}, soit « ${nomStatut[statutDe(JT.definition_cora3d_deg)]} » : la définition compte autant que la mesure. ${P.bone === 'femur' ? 'Le centre de la tête et la base du col restent estimés automatiquement : à confirmer par un pointage.' : ''}`) : null,
    rad ? sources('kroner17', 'kwon22') : sources(P.bone === 'femur' ? 'alaiyan' : 'bruhT', 'longo')) : null;
  return [
    para(`La <b>torsion</b> est une rotation d'un bout de l'os par rapport à l'autre, <b>autour de l'axe long</b>. Ici on tord l'os ${P.reel ? 'segmenté' : '<b>sain</b>'} de τ et on peut aussi le poser de travers sur la table (ρ). Bouton <b>Ax</b> : vue axiale, le long de l'os.`),
    mesureReel,
    curseurs,
    h('table', { class: 't' }, h('caption', {}, 'Scanner (3D) / radiographie de face (2D)'),
      h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Mesure'), h('th', { scope: 'col' }, 'Ici'), h('th', { scope: 'col' }, P.reel ? 'Os tel quel' : 'Os sain'))),
      h('tbody', {},
        h('tr', {}, h('td', {}, `3D : ${nomAngle}`), h('td', { class: 'hi', id: 'tor-3d' }, deg(m.torsion3D)), h('td', {}, deg(m0.torsion3D))),
        h('tr', {}, h('td', {}, `2D : largeur ${largeurNom} projetée`), h('td', { class: 'hi', id: 'tor-w' }, mm(m.radio.epicondyles, 2)), h('td', {}, mm(m0.radio.epicondyles, 2))),
        h('tr', {}, h('td', {}, `2D : distance entre ${P.bone === 'femur' ? 'les condyles (points distaux)' : rad ? 'les bords de la tête radiale' : 'les condyles caudaux'}`), h('td', { class: 'hi', id: 'tor-c' }, mm(m.radio.condyles, 2)), h('td', {}, mm(m0.radio.condyles, 2))))),
    h('div', { id: 'tor-chart', html: courbeTorsionSVG(P, T) }),
    boite('def', 'Largeur projetée et torsion : limites de la radiographie de face',
      para(`En géométrie, la largeur projetée d'une extrémité vaut W·cos α, où α est sa rotation <b>par rapport au film</b> (ici largeur ${largeurNom}, W = ${mm(W0)} ; le même calcul vaut pour la distance entre les condyles). Cette mesure a quatre limites :`),
      h('ol', {},
        h('li', { html: `<b>cos α est plat près de 0</b> : il faut tourner de ${deg(aPrec, 0)} pour perdre 0,5 mm (la précision d'une mesure sur radiographie), et de ${deg(aMag, 0)} pour perdre 5 %, l'incertitude habituelle sur le grossissement.` }),
        h('li', { html: '<b>Pas de signe</b> : une rotation interne et une externe de même valeur donnent la même largeur.' }),
        h('li', { html: `<b>Rotation sur la table ou torsion ?</b> La largeur dépend de τ + ρ seulement. Les exemples « ρ = 20° » et « τ = 20° » donnent la même radiographie ${bDist}, mais seul le second est une torsion. Avec « τ = 20°, ρ = −20° », ${bDistNu} paraît parfait et la torsion « passe » vers ${bProx}.` }),
        h('li', { html: 'La torsion est une <b>différence</b> entre deux extrémités : il faut l\'orientation des deux bouts dans le même repère, ce qu\'une seule vue de face ne donne pas.' })),
      para('Le principe sert pourtant en clinique, sous une forme plus robuste : on fait tourner le faisceau (amplificateur de brillance) jusqu\'à obtenir le profil « standard » du genou puis celui du col ; la différence des deux angles de rotation est l\'antéversion (méthode de Tornetta). Erreur rapportée : 4 à 9°. Chez l\'homme, les signes de « différence de diamètre » et de « marche corticale » (Krettek) exploitent la même idée, avec une sensibilité correcte seulement au-delà de ≈ 15°.'),
      sources('tornetta', 'ivanov', 'krettek', 'fang')),
    boite('def', 'Repérer la torsion en 3D (scanner)',
      para(`On choisit un axe transverse à chaque bout (${A.nomProx} ; ${A.nomDist}), on les projette sur le plan perpendiculaire à l'axe long et on mesure l'angle entre eux. La rotation de l'os sur la table n'a <b>aucun effet</b> (curseur ρ) : c'est l'intérêt du repère lié à l'os.`),
      para(`Repères publiés (Longo et al. 2022, chien) : ${seuil}.`),
      sources('aper', 'dudley', 'bruhF', 'longo')),
    boite('def', 'Chez le chien : radiographie contre scanner',
      h('ul', {},
        h('li', {}, 'Tibia : la radiographie standard ne distingue pas une torsion d\'une rotation du membre pendant le cliché ; un tibia normal peut paraître tordu et inversement (Apelt 2005).'),
        h('li', {}, 'Fémur : une vue axiale bien positionnée peut suffire sur des chiens normaux (Dudley 2006), mais les méthodes radiographiques ne corrèlent pas avec le scanner chez des Labradors et seul le scanner localise la torsion (Mostafa 2014).'),
        h('li', {}, 'Une rotation de plus de ±5° du fémur fait varier l\'aLDFA de façon imprévisible (Miles 2016) : la torsion fausse aussi les angles frontaux.'),
        h('li', {}, 'Radius : au-delà de 15° de torsion, les angles mesurés de face sur une radiographie sont faussés de plus de 5° (Kwon 2022) ; ici, chaque articulation se mesure dans son propre repère, et la torsion se mesure au scanner (Kroner 2017).'),
        h('li', {}, 'Deux radiographies orthogonales ne suffisent qu\'avec un modèle 3D de l\'os (système EOS chez l\'homme ≈ scanner) : c\'est une reconstruction 3D, pas une lecture 2D.')),
      sources('apelt', 'dudley', 'mostafa', 'miles', 'folinais')),
  ];
}
