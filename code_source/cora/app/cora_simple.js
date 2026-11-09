// =============================================================================
// cora_simple.js — cœur de calcul de CORA 3D (sans graphisme, utilisable sous Node)
// -----------------------------------------------------------------------------
// Cas : fémur ou tibia, composante FRONTALE (varus / valgus) éventuellement associée à une
// composante SAGITTALE (procurvatum / recurvatum). Le segment distal tourne d'un angle θ
// autour d'un axe OBLIQUE (perpendiculaire à l'os) passant par l'apex : c'est une déformité
// angulaire dans un plan oblique, comme sur la plupart des vrais patients.
//
// Méthode CORA (Paley 2002), faite en 3D puis montrée dans les deux vues radiographiques :
//   1. lignes d'orientation articulaire (JOL), dans le plan frontal ET dans le plan sagittal ;
//   2. axe de chaque segment construit depuis ses JOL avec l'orientation NORMALE (os sain) ;
//   3. CORA = milieu de la perpendiculaire commune aux deux axes, θ = angle 3D entre eux ;
//      projections : composante frontale F, composante sagittale S, tan²θ = tan²F + tan²S ;
//   4. plan de la déformité (orientation φ), bissectrice transverse, ACA ⊥ à ce plan (oblique) ;
//   5. règle 1 : ostéotomie au CORA, charnière sur la bissectrice -> correction sans translation ;
//   6. prescription pour le guide de coupe : plans de coupe, charnière, broches de réduction.
//
// Définitions des angles (IMAIOS vet-Anatomy ; Dismukes 2007 et 2008 ; Tomlinson 2007 ; Kara 2018).
// Repère de chaque os (membre DROIT) : X latéral, Y proximal, Z caudal (mm).
// Plan frontal = (X, Y), vecteur 2D [x, y] ; plan sagittal = (Z, Y), vecteur 2D [z, y].
// =============================================================================

export const DEG = 180 / Math.PI;
export const RAD = Math.PI / 180;
export const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
export const smoothstep = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };

// ----------------------------------------------------------------- vecteurs 3D --
export const V = {
  add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
  sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
  mul: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  neg: (a) => [-a[0], -a[1], -a[2]],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  len: (a) => Math.hypot(a[0], a[1], a[2]),
  dist: (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]),
  norm: (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; },
  mid: (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2],
  // angle non signé (°) entre deux directions
  angle: (a, b) => Math.acos(clamp(V.dot(a, b) / ((V.len(a) * V.len(b)) || 1), -1, 1)) * DEG,
  // composante de a perpendiculaire à la direction unitaire n
  perp: (a, n) => V.sub(a, V.mul(n, V.dot(a, n))),
  // distance du point x à la droite (p, d unitaire)
  distLine: (x, p, d) => V.len(V.perp(V.sub(x, p), d)),
};

// ----------------------------------------------------------------- vecteurs 2D --
export const P2 = {
  add: (a, b) => [a[0] + b[0], a[1] + b[1]],
  sub: (a, b) => [a[0] - b[0], a[1] - b[1]],
  mul: (a, s) => [a[0] * s, a[1] * s],
  neg: (a) => [-a[0], -a[1]],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1],
  len: (a) => Math.hypot(a[0], a[1]),
  dist: (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]),
  norm: (a) => { const l = Math.hypot(a[0], a[1]) || 1; return [a[0] / l, a[1] / l]; },
  mid: (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
  perp: (a) => [-a[1], a[0]],                                       // +90° (sens trigonométrique)
  rot: (a, ang) => { const c = Math.cos(ang), s = Math.sin(ang); return [c * a[0] - s * a[1], s * a[0] + c * a[1]]; },
  // angle signé (rad) pour aller de a à b, dans ]−π, π] ; positif = sens trigonométrique
  ang: (a, b) => Math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]),
  // angle non signé (°) entre deux directions, dans [0, 180]
  angU: (a, b) => Math.acos(clamp((a[0] * b[0] + a[1] * b[1]) / ((Math.hypot(a[0], a[1]) * Math.hypot(b[0], b[1])) || 1), -1, 1)) * DEG,
  // intersection des droites (p + s·d) et (q + t·e)
  intersect: (p, d, q, e) => { const den = d[0] * e[1] - d[1] * e[0]; if (Math.abs(den) < 1e-12) return null; const w = [q[0] - p[0], q[1] - p[1]]; const s = (w[0] * e[1] - w[1] * e[0]) / den; return [p[0] + s * d[0], p[1] + s * d[1]]; },
  // distance du point x à la droite (p, d unitaire)
  distLine: (x, p, d) => Math.abs((x[0] - p[0]) * d[1] - (x[1] - p[1]) * d[0]),
};

// Les deux vues radiographiques : projection orthogonale d'un point 3D sur le plan de la vue.
// F (frontale, crânio-caudale) : [x, y] ; S (sagittale, médio-latérale) : [z, y].
export const VUE = {
  F: { to2: (p) => [p[0], p[1]], nom: 'frontal', normale: [0, 0, 1] },
  S: { to2: (p) => [p[2], p[1]], nom: 'sagittal', normale: [1, 0, 0] },
};

// ------------------------------------------------- transformations rigides 3D --
// T = { R: mat3 (9 nombres, ligne par ligne), t: vec3 } :  p -> R p + t
export const M3 = {
  I: () => [1, 0, 0, 0, 1, 0, 0, 0, 1],
  mv: (A, v) => [A[0] * v[0] + A[1] * v[1] + A[2] * v[2], A[3] * v[0] + A[4] * v[1] + A[5] * v[2], A[6] * v[0] + A[7] * v[1] + A[8] * v[2]],
  mul: (A, B) => { const C = new Array(9); for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) C[3 * i + j] = A[3 * i] * B[j] + A[3 * i + 1] * B[3 + j] + A[3 * i + 2] * B[6 + j]; return C; },
  T: (A) => [A[0], A[3], A[6], A[1], A[4], A[7], A[2], A[5], A[8]],
  // rotation d'angle a (rad) autour de l'axe unitaire n (formule de Rodrigues)
  axisAngle: (n, a) => {
    const [x, y, z] = V.norm(n), c = Math.cos(a), s = Math.sin(a), k = 1 - c;
    return [c + x * x * k, x * y * k - z * s, x * z * k + y * s,
      y * x * k + z * s, c + y * y * k, y * z * k - x * s,
      z * x * k - y * s, z * y * k + x * s, c + z * z * k];
  },
};
export const RT = {
  I: () => ({ R: M3.I(), t: [0, 0, 0] }),
  apply: (T, p) => V.add(M3.mv(T.R, p), T.t),
  // rotation d'angle a (rad) autour de la droite (c, n)
  aboutAxis: (c, n, a) => { const R = M3.axisAngle(n, a); return { R, t: V.sub(c, M3.mv(R, c)) }; },
  compose: (A, B) => ({ R: M3.mul(A.R, B.R), t: V.add(M3.mv(A.R, B.t), A.t) }),   // A ∘ B
  inv: (T) => { const Rt = M3.T(T.R); return { R: Rt, t: V.neg(M3.mv(Rt, T.t)) }; },
  toMat4: (T) => { const R = T.R; return [R[0], R[3], R[6], 0, R[1], R[4], R[7], 0, R[2], R[5], R[8], 0, T.t[0], T.t[1], T.t[2], 1]; },
  toRows4: (T) => [[T.R[0], T.R[1], T.R[2], T.t[0]], [T.R[3], T.R[4], T.R[5], T.t[1]], [T.R[6], T.R[7], T.R[8], T.t[2]], [0, 0, 0, 1]],
};

// ------------------------------------------------------------------ les cas --
export const OS = ['femur', 'tibia'];
export const FRONTAL = ['varus', 'valgus'];
export const SAGITTAL = ['aucun', 'procurvatum', 'recurvatum'];
const NOM_OS = { femur: 'Fémur', tibia: 'Tibia' };
export function casDe(id) {
  const [bone, frontal, sagittal = 'aucun'] = id.split('-');
  const titre = `${NOM_OS[bone]} ${frontal}${sagittal === 'aucun' ? '' : ' + ' + sagittal}`;
  return { id: `${bone}-${frontal}-${sagittal}`, bone, frontal, sagittal, titre, pur: sagittal === 'aucun' };
}
export const CAS = OS.flatMap((b) => FRONTAL.flatMap((f) => SAGITTAL.map((s) => casDe(`${b}-${f}-${s}`))));

// thetaF / thetaS : amplitudes imposées (°) dans le plan frontal / sagittal (angles PROJETÉS, comme sur
// les radiographies) ; niveau : position de l'apex en fraction de la longueur depuis l'extrémité proximale ;
// largeur : zone de transition de la courbure (mm). Plages de niveau : l'apex doit rester à distance des
// repères utilisés par la méthode (sinon ils seraient eux-mêmes déformés).
export const REGLAGES = {
  femur: { thetaF: 15, thetaS: 10, niveau: 0.72, largeur: 14, niveaux: [0.62, 0.82], thetasF: [5, 30], thetasS: [3, 25] },
  tibia: { thetaF: 15, thetaS: 10, niveau: 0.60, largeur: 12, niveaux: [0.25, 0.85], thetasF: [5, 30], thetasS: [3, 25] },
};
// Préréglages cliniques (os fictif ; déformité de test d'un os segmenté) : déformités typiques du membre pelvien du chien,
// avec leur contexte et, quand il existe, le traitement publié. F, S : angles projetés (°) ; niveau : apex en fraction de la
// longueur depuis proximal ; torsion du segment distal (°, + externe).
export const PRESETS_DEFORMITE = [
  { id: 'tib-valgus-prox', os: 'tibia', titre: 'Tibia : valgus proximal (mMPTA élevé)', frontal: 'valgus', sagittal: 'aucun', thetaF: 12, thetaS: 0, niveau: 0.27, torsion: 0,
    contexte: 'Valgus proximal du tibia, souvent associé à la rupture du ligament croisé crânial. Traitement publié : TPLO + coin de fermeture médial (Vezzoni L 2020 : mMPTA 101° → 92,8°).', ref: 'vezzoni20' },
  { id: 'tib-varus-prox', os: 'tibia', titre: 'Tibia : varus proximal', frontal: 'varus', sagittal: 'aucun', thetaF: 10, thetaS: 0, niveau: 0.30, torsion: 0,
    contexte: 'Varus de la métaphyse proximale ; plateau tibial incliné vers médial.' },
  { id: 'tib-pes-varus', os: 'tibia', titre: 'Tibia : pes varus du teckel (varus distal + torsion interne)', frontal: 'varus', sagittal: 'aucun', thetaF: 22, thetaS: 0, niveau: 0.82, torsion: -15,
    contexte: 'Fermeture prématurée de la partie latérale de la physe distale : varus distal, souvent avec torsion interne. Traitement publié : coin d\'ouverture médial au CORA, corticale latérale conservée comme charnière (Petazzoni 2012) ; guides imprimés (Bright 2024).', ref: 'petazzoni' },
  { id: 'tib-valgus-dist', os: 'tibia', titre: 'Tibia : valgus distal', frontal: 'valgus', sagittal: 'aucun', thetaF: 14, thetaS: 0, niveau: 0.80, torsion: 0,
    contexte: 'Valgus du tibia distal (cal vicieux ou trouble de croissance).' },
  { id: 'tib-recurvatum', os: 'tibia', titre: 'Tibia : recurvatum diaphysaire (cal vicieux)', frontal: 'varus', sagittal: 'recurvatum', thetaF: 0, thetaS: 15, niveau: 0.50, torsion: 0,
    contexte: 'Angulation pure dans le plan sagittal (apex caudal) : la face du coin est crâniale ou caudale, hors des abords usuels ; le guide se pose sur la face médiale la plus proche (ostéotomie complète).' },
  { id: 'tib-procurvatum', os: 'tibia', titre: 'Tibia : procurvatum', frontal: 'varus', sagittal: 'procurvatum', thetaF: 0, thetaS: 12, niveau: 0.55, torsion: 0,
    contexte: 'Angulation pure dans le plan sagittal (apex crânial).' },
  { id: 'tib-varus-procurvatum', os: 'tibia', titre: 'Tibia : varus + procurvatum (plan oblique)', frontal: 'varus', sagittal: 'procurvatum', thetaF: 15, thetaS: 10, niveau: 0.60, torsion: 0,
    contexte: 'Une seule angulation dans un plan oblique : un seul coin oblique corrige les deux composantes.' },
  { id: 'tib-varus-recurvatum', os: 'tibia', titre: 'Tibia : varus + recurvatum (plan oblique)', frontal: 'varus', sagittal: 'recurvatum', thetaF: 15, thetaS: 10, niveau: 0.60, torsion: 0,
    contexte: 'Convexité caudo-latérale : le coin de fermeture devrait être retiré par la face caudo-latérale (fibula, hors abord) ; le coin d\'ouverture médial est réalisable.' },
  { id: 'tib-valgus-recurvatum', os: 'tibia', titre: 'Tibia : valgus + recurvatum', frontal: 'valgus', sagittal: 'recurvatum', thetaF: 12, thetaS: 12, niveau: 0.45, torsion: 0,
    contexte: 'Convexité caudo-médiale : coin de fermeture retiré par la face médiale.' },
  { id: 'tib-torsion-externe', os: 'tibia', titre: 'Tibia : valgus léger + torsion externe', frontal: 'valgus', sagittal: 'aucun', thetaF: 8, thetaS: 0, niveau: 0.50, torsion: 25,
    contexte: 'Torsion externe du segment distal : la correction ajoute une dérotation, l\'ostéotomie devient complète.' },
  { id: 'tib-grand-varus', os: 'tibia', titre: 'Tibia : grande déformité (varus 28° + recurvatum 15°)', frontal: 'varus', sagittal: 'recurvatum', thetaF: 28, thetaS: 15, niveau: 0.65, torsion: 0,
    contexte: 'Grande correction : l\'ouverture devient importante (greffe), la fermeture raccourcit nettement.' },
  { id: 'fem-varus-distal', os: 'femur', titre: 'Fémur : varus distal (luxation médiale de rotule)', frontal: 'varus', sagittal: 'aucun', thetaF: 14, thetaS: 0, niveau: 0.78, torsion: 0,
    contexte: 'Varus du fémur distal associé à la luxation médiale de la rotule. Traitement publié : coin de fermeture latéral (Brower 2017 : aLDFA 107,6° → 94,1°) ; guides imprimés (Hall 2019).', ref: 'brower' },
  { id: 'fem-valgus-distal', os: 'femur', titre: 'Fémur : valgus distal (luxation latérale de rotule)', frontal: 'valgus', sagittal: 'aucun', thetaF: 10, thetaS: 0, niveau: 0.78, torsion: 0,
    contexte: 'Valgus du fémur distal (grandes races), associé à la luxation latérale de la rotule ; coin de fermeture médial ou hémiépiphysiodèse chez le jeune (Vezzoni L 2022).', ref: 'vezzoni22' },
  { id: 'fem-varus-torsion', os: 'femur', titre: 'Fémur : varus distal + torsion externe', frontal: 'varus', sagittal: 'aucun', thetaF: 12, thetaS: 0, niveau: 0.75, torsion: 15,
    contexte: 'Varus distal avec torsion du segment distal : correction angulaire + dérotation (ostéotomie complète).' },
  { id: 'fem-procurvatum', os: 'femur', titre: 'Fémur : procurvatum distal', frontal: 'varus', sagittal: 'procurvatum', thetaF: 0, thetaS: 12, niveau: 0.72, torsion: 0,
    contexte: 'Angulation pure dans le plan sagittal : la face du coin est crâniale ou caudale (exclues : quadriceps, nerf sciatique).' },
  { id: 'fem-recurvatum', os: 'femur', titre: 'Fémur : recurvatum (cal vicieux)', frontal: 'varus', sagittal: 'recurvatum', thetaF: 0, thetaS: 15, niveau: 0.70, torsion: 0,
    contexte: 'Cal vicieux en recurvatum.' },
  { id: 'fem-varus-procurvatum', os: 'femur', titre: 'Fémur : varus + procurvatum (plan oblique)', frontal: 'varus', sagittal: 'procurvatum', thetaF: 12, thetaS: 10, niveau: 0.75, torsion: 0,
    contexte: 'Une seule angulation oblique au fémur distal.' },
];
export const CHARNIERE_RETRAIT = 2;     // mm : la charnière reste à 2 mm à l'intérieur de la corticale
// Instrumentation du guide : mêmes valeurs que la v2 (Planificateur_CORA_3Dv2/code_source/parametres.py)
export const INSTRUMENT = {
  lame: 0.6, jeuFente: 0.2,             // mm : épaisseur de lame (BP : 0,5–1 mm) et jeu de la fente
  broche: 1.6, jeuBroche: 0.2,          // mm : broche de Kirschner et jeu du manchon
  facteurBroches: 1.2,                  // distance broche–coupe préférée = 1,2 × largeur locale de l'os (si la place le permet)
  ecartBroches: 10,                     // mm entre les deux broches d'un même fragment (guide de réduction)
  ecartBrochesMin: 6.5,                 // mm : écart minimal (manchons Ø 5,8 mm accolés) pour un fragment court
  paroi: 2.0,                           // mm : parois des manchons et des tours de fente du guide (etape7_guide.py)
  jeuGuide: 0.3, coque: 3.0, guidage: 10.0,   // mm : jeu os-guide, épaisseur de coque, hauteur de guidage (parametres.py)
};
// rayon d'un manchon, demi-épaisseur d'une tour de fente : une broche reste à leur somme + 0,5 mm de chaque plan de coupe
export let RAYON_MANCHON = (INSTRUMENT.broche + INSTRUMENT.jeuBroche) / 2 + INSTRUMENT.paroi;
export let DEMI_TOUR = (INSTRUMENT.lame + INSTRUMENT.jeuFente) / 2 + INSTRUMENT.paroi;
// Guide GÉNÉRIQUE : ses dimensions de conception sont des paramètres (clés de prescription.parametres_guide, lues par
// etape7_guide.py ; mêmes valeurs par défaut que parametres.py). Ceux marqués « inst » servent aussi à la planification
// (placement des broches, tours de fente sur le trajet de la lame) ; ceux marqués « plan » ne servent qu'à elle.
// Les dimensions qui dépendent de l'os (longueur des fentes, hauteur des tours, position des broches, étendue de la
// coque…) en découlent pour chaque scanner.
export const PARAMS_GUIDE = [
  { cle: 'jeu_mm', sym: 'j', nom: 'Jeu entre l\'os et la coque', def: 0.3, min: 0.1, max: 1.0, pas: 0.05, unite: 'mm', groupe: 'Coque', inst: 'jeuGuide' },
  { cle: 'epaisseur_coque_mm', sym: 'e', nom: 'Épaisseur de la coque', def: 3.0, min: 1.5, max: 6, pas: 0.5, unite: 'mm', groupe: 'Coque', inst: 'coque' },
  { cle: 'secteur_deg', sym: 'α', nom: 'Demi-ouverture de la coque autour de la face d\'appui', def: 75, min: 30, max: 120, pas: 5, unite: '°', groupe: 'Coque' },
  { cle: 'marge_mm', sym: 'm', nom: 'Coque au-delà des broches extrêmes', def: 8, min: 3, max: 25, pas: 1, unite: 'mm', groupe: 'Coque' },
  { cle: 'depouille_deg', sym: 'δ', nom: 'Dépouille (pose et retrait sans contre-dépouille)', def: 5, min: 1, max: 15, pas: 1, unite: '°', groupe: 'Coque' },
  { cle: 'conge_mm', sym: 'r', nom: 'Rayon des congés', def: 0.8, min: 0, max: 2, pas: 0.1, unite: 'mm', groupe: 'Coque' },
  { cle: 'epaisseur_min_mm', sym: 'emin', nom: 'Épaisseur minimale imprimable', def: 1.2, min: 0.6, max: 3, pas: 0.1, unite: 'mm', groupe: 'Coque' },
  { cle: 'guidage_mm', sym: 'g', nom: 'Hauteur de guidage minimale au-dessus de la coque (tours, manchons)', def: 10, min: 4, max: 25, pas: 1, unite: 'mm', groupe: 'Fentes et manchons', inst: 'guidage' },
  { cle: 'paroi_mm', sym: 'p', nom: 'Paroi des tours et des manchons', def: 2, min: 1.2, max: 4, pas: 0.1, unite: 'mm', groupe: 'Fentes et manchons', inst: 'paroi' },
  { cle: 'lame_mm', sym: 's', nom: 'Épaisseur de la lame de scie', def: 0.6, min: 0.3, max: 1.5, pas: 0.05, unite: 'mm', groupe: 'Fentes et manchons', inst: 'lame' },
  { cle: 'jeu_fente_mm', sym: 'js', nom: 'Jeu de la fente', def: 0.2, min: 0.05, max: 0.6, pas: 0.05, unite: 'mm', groupe: 'Fentes et manchons', inst: 'jeuFente' },
  { cle: 'broche_mm', sym: 'Øb', nom: 'Diamètre des broches', def: 1.6, min: 1, max: 3.2, pas: 0.1, unite: 'mm', groupe: 'Fentes et manchons', inst: 'broche' },
  { cle: 'jeu_broche_mm', sym: 'jb', nom: 'Jeu du manchon', def: 0.2, min: 0.05, max: 0.6, pas: 0.05, unite: 'mm', groupe: 'Fentes et manchons', inst: 'jeuBroche' },
  { cle: 'pont_mm', sym: 'hp', nom: 'Hauteur des ponts sécables', def: 5, min: 2, max: 10, pas: 0.5, unite: 'mm', groupe: 'Fentes et manchons' },
  { cle: 'chanfrein_mm', sym: 'c', nom: 'Chanfreins d\'entrée (fentes, manchons)', def: 0.5, min: 0, max: 1.5, pas: 0.1, unite: 'mm', groupe: 'Fentes et manchons' },
  { cle: 'ecart_broches_mm', sym: 'eb', nom: 'Écart préféré entre deux broches d\'un fragment', def: 10, min: 6.5, max: 20, pas: 0.5, unite: 'mm', groupe: 'Broches (planification)', plan: true, inst: 'ecartBroches' },
  { cle: 'facteur_distance_broches', sym: 'kd', nom: 'Distance broche–coupe préférée (× largeur de l\'os)', def: 1.2, min: 0.5, max: 3, pas: 0.1, unite: '×', groupe: 'Broches (planification)', plan: true, inst: 'facteurBroches' },
  { cle: 'jeu_voisin_mm', sym: 'jv', nom: 'Distance minimale aux os voisins', def: 1, min: 0.5, max: 4, pas: 0.5, unite: 'mm', groupe: 'Voisins et cartilage' },
  { cle: 'marge_cartilage_mm', sym: 'mc', nom: 'Écart supplémentaire de la coque au cartilage', def: 1, min: 0.5, max: 5, pas: 0.5, unite: 'mm', groupe: 'Voisins et cartilage' },
  { cle: 'reduction_ecart_mm', sym: 'er', nom: 'Guide de réduction : distance de la barre à l\'os', def: 4, min: 2, max: 15, pas: 0.5, unite: 'mm', groupe: 'Guide de réduction' },
  { cle: 'reduction_manchon_mm', sym: 'lr', nom: 'Guide de réduction : longueur des manchons', def: 12, min: 6, max: 25, pas: 1, unite: 'mm', groupe: 'Guide de réduction' },
  { cle: 'reduction_barre_mm', sym: 'tb', nom: 'Guide de réduction : épaisseur de la barre', def: 6, min: 3, max: 12, pas: 0.5, unite: 'mm', groupe: 'Guide de réduction' },
];
const INSTRUMENT_DEFAUT = { ...INSTRUMENT };
// Applique (pour une planification) les dimensions choisies du guide générique qui comptent pour la planification ;
// les autres valeurs reviennent à leur défaut. Valeurs bornées comme dans etape7_guide.py.
export function appliquerInstrument(pg = {}) {
  Object.assign(INSTRUMENT, INSTRUMENT_DEFAUT);
  for (const p of PARAMS_GUIDE) {
    const x = pg ? pg[p.cle] : undefined;
    if (p.inst && Number.isFinite(x)) INSTRUMENT[p.inst] = clamp(x, p.min, p.max);
  }
  RAYON_MANCHON = (INSTRUMENT.broche + INSTRUMENT.jeuBroche) / 2 + INSTRUMENT.paroi;
  DEMI_TOUR = (INSTRUMENT.lame + INSTRUMENT.jeuFente) / 2 + INSTRUMENT.paroi;
}

// Valeurs publiées (affichées pour comparaison ; la méthode utilise les valeurs de l'os sain du modèle,
// qui joue le rôle du membre controlatéral sain). sd : écart-type.
export const LITTERATURE = {
  tibia: {
    mMPTA: { m: 93.3, sd: 1.8, src: 'Dismukes et al. 2007, radiographie' },
    mMDTA: { m: 96.0, sd: 2.7, src: 'Dismukes et al. 2007, radiographie' },
    valgusTib: { m: 11.8, sd: 3.1, src: 'Newman & Voss 2017, CT, Staffordshire bull terrier (cité par IMAIOS)' },
    mCaPTA: { m: 63.6, sd: 3.9, src: 'Dismukes et al. 2008, radiographie sagittale' },
    mCrDTA: { m: 81.6, sd: 3.2, src: 'Dismukes et al. 2008, radiographie sagittale' },
  },
  femur: {
    aLPFA: { m: 103, sd: 6.4, src: 'Tomlinson et al. 2007, Labrador' },
    aLDFA: { m: 97, sd: 3.2, src: 'Tomlinson et al. 2007, Labrador' },
    varusFem: { m: 9.4, sd: 2.3, src: 'IMAIOS, races moyennes à grandes, radiographie' },
    // Kara 2018 : IC 95 % de la moyenne 89,1–91,9° sur 75 fémurs (3D-CT) ; écart-type déduit : 1,43·√75/1,96 ≈ 6,3°
    aCdDFA: { m: 90.5, sd: 6.3, src: 'Kara et al. 2018, 3D-CT (« CDFA », définition non identique)' },
  },
};
export const CLES = {
  tibia: { F: ['mMPTA', 'mMDTA', 'valgusTib'], S: ['mCaPTA', 'mCrDTA'] },
  femur: { F: ['aLPFA', 'aLDFA', 'varusFem'], S: ['aCdDFA'] },
};

// ------------------------------------------------------- modèle osseux (accès) --
// model = { meta (bones_pack.json), bones: { femur|tibia|fibula: { pos: Float32Array, idx: Uint32Array } } }
export function axisInfo(meta, bone) {
  const cl = meta.centerline[bone].filter((r, i, a) => i === 0 || r[0] > a[i - 1][0]);
  const centerAt = (y) => {
    if (y <= cl[0][0]) return [cl[0][1], y, cl[0][2]];
    for (let i = 1; i < cl.length; i++) if (y <= cl[i][0]) {
      const t = (y - cl[i - 1][0]) / (cl[i][0] - cl[i - 1][0]);
      return [cl[i - 1][1] + t * (cl[i][1] - cl[i - 1][1]), y, cl[i - 1][2] + t * (cl[i][2] - cl[i - 1][2])];
    }
    const l = cl[cl.length - 1]; return [l[1], y, l[2]];
  };
  return { ...meta.axis[bone], centerAt };
}
export function landmarks(meta, bone) {
  const L = {};
  for (const [k, v] of Object.entries(meta.landmarks[bone])) L[k] = [...v];
  if (bone === 'tibia') for (const [k, v] of Object.entries(meta.landmarks.fibula)) L[k] = [...v];
  // fémur : milieu des points caudaux des condyles (extrémité caudale de la JOL sagittale distale)
  if (bone === 'femur') L.caud_mid = V.mid(L.cond_med_caud, L.cond_lat_caud);
  return L;
}
export const BONE_MESHES = { femur: ['femur'], tibia: ['tibia', 'fibula'] };
// maillages réellement présents (un os segmenté peut ne pas avoir de fibula)
export const meshesOf = (model, bone) => BONE_MESHES[bone].filter((n) => model.bones[n]);

// ------------------------------------------- os segmenté (CT) -> même forme que le modèle --
// json : cora_<os>.json écrit par etape6_reperes.py (repère X latéral, Y proximal, Z caudal ; membre gauche mis en
// miroir) ; maillages : { tibia|femur|fibula: { pos: Float32Array, idx: Uint32Array } } dans ce même repère.
// Le résultat a la forme du modèle synthétique (meta + bones) : toute la planification fonctionne telle quelle.
export function modeleReel(json, maillages) {
  const bone = json.os;
  const L = Object.fromEntries(Object.entries(json.reperes).map(([k, p]) => [k, [...p]]));
  const meta = {
    axis: { [bone]: { y_top: json.repere.y_haut, y_bot: json.repere.y_bas } },
    centerline: { [bone]: json.ligne_centrale },
    landmarks: { [bone]: L, fibula: {} },
  };
  return { meta, bones: maillages, reel: json };
}

// ------------------------------------------------ déformité synthétique (3D) --
// Le segment distal tourne de θ autour de l'axe n (⊥ à l'os) passant par l'apex A.
// Direction distale imposée : v = norm(−sF·tan F, −1, sS·tan S), avec sF = +1 en varus (distal vers médial,
// −X) et sS = +1 en procurvatum (distal vers caudal, +Z). Ainsi les angles PROJETÉS sur les vues frontale et
// sagittale valent exactement F et S, et l'angle vrai vérifie tan²θ = tan²F + tan²S.
// Dans la zone de transition (largeur w), l'angle passe progressivement de 0 à θ.
// torsion (°, facultatif) : rotation du segment distal autour de l'axe long au même apex ; + = externe (sa face crâniale
// tourne vers latéral), c'est-à-dire une rotation négative autour de +Y pour un membre droit.
// axeTorsion (facultatif) : axe { p, d } du segment sain (d vers distal) autour duquel tourne la torsion ; par défaut la
// verticale passant par l'apex. Tourner autour de l'axe du segment n'ajoute pas de translation à la déformité.
export function makeDeformity({ frontal, sagittal, thetaF, thetaS, niveau, largeur, torsion = 0, axeTorsion = null }, ax) {
  const yA = ax.y_top - niveau * (ax.y_top - ax.y_bot);
  const A = ax.centerAt(yA);
  const sF = frontal === 'varus' ? 1 : -1;
  const sS = sagittal === 'procurvatum' ? 1 : sagittal === 'recurvatum' ? -1 : 0;
  const S = sS ? thetaS : 0;
  const u0 = [0, -1, 0];
  const v0 = V.norm([-sF * Math.tan(thetaF * RAD), -1, sS * Math.tan(S * RAD)]);
  const theta = Math.acos(clamp(V.dot(u0, v0), -1, 1));
  const n = V.norm(V.cross(u0, v0));
  // torsion d'abord (autour de l'axe long), puis angulation (autour de n) : le segment distal garde sa direction
  const tor = axeTorsion
    ? { p: V.add(axeTorsion.p, V.mul(axeTorsion.d, (yA - axeTorsion.p[1]) / axeTorsion.d[1])), d: V.neg(V.norm(axeTorsion.d)) }
    : { p: A, d: [0, 1, 0] };
  return {
    A, yA, w: Math.max(1, largeur), theta, n, F: thetaF, S, sF, sS, tau: torsion, tor,
    phi: Math.atan2(Math.abs(Math.tan(S * RAD)), Math.abs(Math.tan(thetaF * RAD))) * DEG,
    T: RT.compose(RT.aboutAxis(A, n, theta), RT.aboutAxis(tor.p, tor.d, -torsion * RAD)),
  };
}
export function deformWeight(D, y) { return smoothstep(D.yA + D.w / 2, D.yA - D.w / 2, y); }
export function deformPoint(D, p) {
  const b = deformWeight(D, p[1]);
  if (b <= 0) return [...p];
  if (b >= 1) return RT.apply(D.T, p);
  const Tb = D.tau ? RT.compose(RT.aboutAxis(D.A, D.n, D.theta * b), RT.aboutAxis(D.tor.p, D.tor.d, -D.tau * b * RAD)) : RT.aboutAxis(D.A, D.n, D.theta * b);
  return RT.apply(Tb, p);
}
export function deformArray(D, src, dst) {
  for (let i = 0; i < src.length; i += 3) {
    const q = deformPoint(D, [src[i], src[i + 1], src[i + 2]]);
    dst[i] = q[0]; dst[i + 1] = q[1]; dst[i + 2] = q[2];
  }
}

// -------------------------------------------------------- sections de maillage --
// Points d'intersection du maillage avec le plan (p0, n)
export function sectionPoints(pos, idx, p0, n) {
  n = V.norm(n);
  const nv = pos.length / 3, d = new Float64Array(nv);
  for (let i = 0; i < nv; i++) d[i] = (pos[3 * i] - p0[0]) * n[0] + (pos[3 * i + 1] - p0[1]) * n[1] + (pos[3 * i + 2] - p0[2]) * n[2];
  const out = [];
  const pt = (i, j) => { const t = d[i] / (d[i] - d[j]); return [0, 1, 2].map((c) => pos[3 * i + c] + (pos[3 * j + c] - pos[3 * i + c]) * t); };
  for (let f = 0; f < idx.length; f += 3) {
    const a = idx[f], b = idx[f + 1], c = idx[f + 2];
    if ((d[a] >= 0) !== (d[b] >= 0)) out.push(pt(a, b));
    if ((d[b] >= 0) !== (d[c] >= 0)) out.push(pt(b, c));
    if ((d[c] >= 0) !== (d[a] >= 0)) out.push(pt(c, a));
  }
  return out;
}
// Milieu de la diaphyse à la hauteur y, comme sur les radiographies : bords médial / latéral de la
// silhouette crânio-caudale (x min / x max) et bords crânial / caudal de la silhouette de profil (z min / z max).
export function diaphysisMidpoint(pos, idx, y) {
  const pts = sectionPoints(pos, idx, [0, y, 0], [0, 1, 0]);
  let xmin = Infinity, xmax = -Infinity, zmin = Infinity, zmax = -Infinity;
  for (const p of pts) { xmin = Math.min(xmin, p[0]); xmax = Math.max(xmax, p[0]); zmin = Math.min(zmin, p[2]); zmax = Math.max(zmax, p[2]); }
  const xm = (xmin + xmax) / 2, zm = (zmin + zmax) / 2;
  return { y, xmin, xmax, zmin, zmax, mid3: [xm, y, zm], F: { a: [xmin, y], b: [xmax, y], mid: [xm, y] }, S: { a: [zmin, y], b: [zmax, y], mid: [zm, y] } };
}

// ------------------------------------------------------- repères articulaires --
// Repère orthonormé lié à une articulation, construit avec ses deux JOL : la JOL frontale donne e1
// (médial -> latéral), la JOL sagittale orthogonalisée donne e3 (crânial -> caudal), e2 = e3 × e1 (≈ proximal).
export function cadre(jf, js, origine) {
  const e1 = V.norm(V.sub(jf[1], jf[0]));
  const e3 = V.norm(V.perp(V.sub(js[1], js[0]), e1));
  return { o: origine, e1, e2: V.cross(e3, e1), e3 };
}
const versLocalDir = (F, d) => [V.dot(d, F.e1), V.dot(d, F.e2), V.dot(d, F.e3)];
const versLocal = (F, p) => versLocalDir(F, V.sub(p, F.o));
const depuisLocalDir = (F, l) => V.add(V.add(V.mul(F.e1, l[0]), V.mul(F.e2, l[1])), V.mul(F.e3, l[2]));
const depuisLocal = (F, l) => V.add(F.o, depuisLocalDir(F, l));

// JOL de chaque os dans les deux plans (paires de repères anatomiques, de médial à latéral et de crânial à caudal)
export const JOL = {
  tibia: { F: { prox: ['plat_med', 'plat_lat'], dist: ['groove_med', 'groove_lat'] }, S: { prox: ['plat_cran', 'plat_caud'], dist: ['dist_cran', 'dist_caud'] } },
  femur: { F: { prox: ['head_center', 'gt_tip'], dist: ['cond_med_dist', 'cond_lat_dist'] }, S: { prox: null, dist: ['troch_dist', 'caud_mid'] } },
};
const paire = (L, k) => (k ? [L[k[0]], L[k[1]]] : null);
function cadresArticulaires(bone, L) {
  const J = JOL[bone];
  if (bone === 'tibia') return { prox: cadre(paire(L, J.F.prox), paire(L, J.S.prox), L.eminence), dist: cadre(paire(L, J.F.dist), paire(L, J.S.dist), L.distal_center) };
  return { dist: cadre(paire(L, J.F.dist), paire(L, J.S.dist), V.mid(L.cond_med_dist, L.cond_lat_dist)) };
}

// --------------------------------------------------------------- mesures ------
// Angles articulaires mesurés en PROJECTION dans chaque vue, comme sur une radiographie.
// axe : axe anatomique du fémur { p, d } (3D, d vers distal) ; ignoré pour le tibia (axe mécanique).
function mesurer(bone, L, axe) {
  const F = (k) => VUE.F.to2(L[k]), S = (k) => VUE.S.to2(L[k]);
  if (bone === 'tibia') {
    const down3 = V.sub(L.distal_center, L.eminence);
    const dF = VUE.F.to2(down3), dS = VUE.S.to2(down3);
    return {
      mMPTA: P2.angU(P2.sub(F('plat_med'), F('plat_lat')), dF),
      mMDTA: P2.angU(P2.sub(F('groove_med'), F('groove_lat')), P2.neg(dF)),
      valgusTib: P2.ang(P2.sub(F('plat_lat'), F('plat_med')), P2.sub(F('groove_lat'), F('groove_med'))) * DEG,
      mCaPTA: P2.angU(P2.sub(S('plat_caud'), S('plat_cran')), dS),
      mCrDTA: P2.angU(P2.sub(S('dist_cran'), S('dist_caud')), P2.neg(dS)),
      longueur: V.len(down3),
    };
  }
  const dF = VUE.F.to2(axe.d), dS = VUE.S.to2(axe.d);
  const aLDFA = P2.angU(P2.sub(F('cond_lat_dist'), F('cond_med_dist')), P2.neg(dF));
  return {
    aLPFA: P2.angU(P2.sub(F('gt_tip'), F('head_center')), dF),
    aLDFA,
    varusFem: aLDFA - 90,
    aCdDFA: P2.angU(P2.sub(S('caud_mid'), S('troch_dist')), P2.neg(dS)),
    longueur: V.dist(L.head_center, V.mid(L.cond_med_dist, L.cond_lat_dist)),
  };
}

// Axe anatomique du fémur (Tomlinson 2007) : milieux de la diaphyse à 1/3 et 1/2 de la longueur, dans les
// deux vues (on obtient ainsi une droite 3D).
function axeAnatomique(pos, idx, ax) {
  const Lg = ax.y_top - ax.y_bot;
  const m1 = diaphysisMidpoint(pos, idx, ax.y_top - Lg / 3), m2 = diaphysisMidpoint(pos, idx, ax.y_top - Lg / 2);
  return { milieux: [m1, m2], p: m1.mid3, d: V.norm(V.sub(m2.mid3, m1.mid3)) };
}

// ------------------------------------------- référence : l'os sain du modèle --
// On mesure sur l'os sain les angles qui serviront de « valeurs normales », et on mémorise l'axe de chaque
// segment dans le repère de ses articulations : c'est l'équivalent 3D de « JOL + angle articulaire normal ».
export function reference(model, bone) {
  model._ref = model._ref || {};
  if (model._ref[bone]) return model._ref[bone];
  const { meta } = model;
  const L0 = landmarks(meta, bone);
  const ax = axisInfo(meta, bone);
  const ref = { L0, ax };
  const C = cadresArticulaires(bone, L0);
  if (bone === 'tibia') {
    const d0 = V.norm(V.sub(L0.distal_center, L0.eminence));      // axe mécanique sain (vers distal)
    ref.axeSain = { p: L0.eminence, d: d0 };
    ref.prox = { pt: versLocal(C.prox, L0.eminence), dir: versLocalDir(C.prox, d0) };
    ref.dist = { pt: versLocal(C.dist, L0.distal_center), dir: versLocalDir(C.dist, d0) };
    ref.normal = mesurer(bone, L0);
  } else {
    const b = model.bones.femur;
    const a = axeAnatomique(b.pos, b.idx, ax);
    ref.axeSain = { p: a.p, d: a.d };
    // point de l'axe sain le plus proche de l'origine du repère distal (milieu des condyles)
    const pt = V.add(a.p, V.mul(a.d, V.dot(V.sub(C.dist.o, a.p), a.d)));
    ref.dist = { pt: versLocal(C.dist, pt), dir: versLocalDir(C.dist, a.d) };
    ref.normal = mesurer(bone, L0, a);
  }
  return ref;
}

// ------------------------------------- référence « valeurs normales » (méthode de Paley) --
// Sans os sain de référence (membre controlatéral), l'axe d'un segment se construit depuis ses JOL et les angles
// articulaires NORMAUX, dans chaque vue : direction 2D qui fait l'angle normal avec la JOL et qui pointe vers distal
// (sens = +1) ou vers proximal (sens = −1) ; les deux directions 2D (face, profil) donnent la direction 3D.
function dir2DNormale(jol, angle, sens) {
  const a = P2.norm(jol);
  const c1 = P2.rot(a, angle * RAD), c2 = P2.rot(a, -angle * RAD);
  const ok = (c) => (sens > 0 ? c[1] < 0 : c[1] > 0);
  const c = ok(c1) && ok(c2) ? (Math.abs(c1[0]) < Math.abs(c2[0]) ? c1 : c2) : ok(c1) ? c1 : c2;
  return sens > 0 ? c : P2.neg(c);                        // toujours vers distal
}
// direction 3D (vers distal) dont les projections de face (x, y) et de profil (z, y) sont dF et dS
const dir3D = (dF, dS) => V.norm([dF[0] / Math.abs(dF[1]), -1, dS[0] / Math.abs(dS[1])]);
// Définitions identiques à mesurer() : JOL et sens de l'axe pour chaque angle.
const SPEC_NORMALES = {
  tibia: {
    prox: { F: ['mMPTA', 'plat_lat', 'plat_med', 1], S: ['mCaPTA', 'plat_cran', 'plat_caud', 1] },
    dist: { F: ['mMDTA', 'groove_lat', 'groove_med', -1], S: ['mCrDTA', 'dist_caud', 'dist_cran', -1] },
  },
  femur: { dist: { F: ['aLDFA', 'cond_med_dist', 'cond_lat_dist', -1], S: ['aCdDFA', 'troch_dist', 'caud_mid', -1] } },
};
function dirNormale(bone, seg, L, normales) {
  const sp = SPEC_NORMALES[bone][seg];
  const d = {};
  for (const k of ['F', 'S']) {
    const [cle, a, b, sens] = sp[k];
    d[k] = dir2DNormale(P2.sub(VUE[k].to2(L[b]), VUE[k].to2(L[a])), normales[cle], sens);
  }
  return dir3D(d.F, d.S);
}
// Gabarit du fémur (os sain du modèle synthétique) : où l'axe anatomique sain coupe la JOL distale, en fraction de
// la JOL depuis son premier repère, de face (fF) et de profil (fS). Sert à placer l'axe distal du fémur.
export function gabaritFemur(model) {
  const ref = reference(model, 'femur'), L = ref.L0, a = ref.axeSain;
  const frac = (k, A, B) => {
    const to2 = VUE[k].to2, p = to2(a.p), d = P2.norm(to2(a.d)), q = to2(L[A]), e = P2.sub(to2(L[B]), q);
    const X = P2.intersect(p, d, q, e);
    return X ? P2.dot(P2.sub(X, q), e) / P2.dot(e, e) : 0.5;
  };
  return { fF: frac('F', 'cond_med_dist', 'cond_lat_dist'), fS: frac('S', 'troch_dist', 'caud_mid') };
}
// Axes des segments depuis les valeurs normales.
//   tibia : axes mécaniques, par l'éminence (proximal) et par le centre distal (distal) ;
//   fémur : axe proximal = axe anatomique mesuré ; axe distal : direction depuis les JOL distales ; position : de face,
//   il coupe la JOL distale comme l'axe sain du gabarit ; de profil, il croise l'axe proximal au niveau du CORA de face
//   (une seule angulation : mêmes niveaux de CORA dans les deux vues, Paley). Le fémur du chien est arqué vers crânial :
//   un gabarit de profil serait faux d'un os à l'autre (lévrier : 33 mm), d'où cette règle.
function axesNormales(bone, L, axeProxFemur, normales, gabarit) {
  if (bone === 'tibia') {
    return {
      prox: { p: L.eminence, d: dirNormale('tibia', 'prox', L, normales), depuis: 'JOL proximales + angles normaux (mMPTA, mCaPTA)' },
      dist: { p: L.distal_center, d: dirNormale('tibia', 'dist', L, normales), depuis: 'JOL distales + angles normaux (mMDTA, mCrDTA)' },
    };
  }
  const d = dirNormale('femur', 'dist', L, normales);
  const ap = axeProxFemur;
  const g = gabarit || { fF: 0.5, fS: 0.5 };
  // point de face : sur la JOL distale de face, à la fraction fF
  const qF = P2.add(VUE.F.to2(L.cond_med_dist), P2.mul(P2.sub(VUE.F.to2(L.cond_lat_dist), VUE.F.to2(L.cond_med_dist)), g.fF));
  const dF = P2.norm(VUE.F.to2(d)), pF = VUE.F.to2(ap.p), uF = P2.norm(VUE.F.to2(ap.d));
  const croise = Math.abs(P2.ang(uF, dF)) * DEG >= 1 ? P2.intersect(pF, uF, qF, dF) : null;
  let z0, y0;
  if (croise) {                                          // niveau du CORA de face -> même niveau de profil
    y0 = croise[1];
    z0 = ap.p[2] + ap.d[2] * (y0 - ap.p[1]) / ap.d[1];
  } else {                                               // pas de composante frontale : gabarit de profil
    const qS = P2.add(VUE.S.to2(L.troch_dist), P2.mul(P2.sub(VUE.S.to2(L.caud_mid), VUE.S.to2(L.troch_dist)), g.fS));
    y0 = qF[1]; z0 = qS[0] + (d[2] / d[1]) * (y0 - qS[1]);
  }
  const x0 = qF[0] + (dF[0] / dF[1]) * (y0 - qF[1]);
  return {
    prox: { ...ap },
    dist: { p: [x0, y0, z0], d, depuis: 'JOL distales + angles normaux (aLDFA, aCdDFA) ; niveau : CORA de face' },
  };
}

// CORA 3D (Best_Position, éq. 4–5) : perpendiculaire commune aux droites (p, u) et (q, v)
export function coraPerpCommune(p, u, q, v) {
  const w0 = V.sub(p, q);
  const a = V.dot(u, u), b = V.dot(u, v), c = V.dot(v, v), d = V.dot(u, w0), e = V.dot(v, w0);
  const den = a * c - b * b;
  if (Math.abs(den) < 1e-12) return null;
  const s = (b * e - c * d) / den, t = (a * e - b * d) / den;
  const Pp = V.add(p, V.mul(u, s)), Pd = V.add(q, V.mul(v, t));
  return { C: V.mid(Pp, Pd), Pp, Pd, delta: V.dist(Pp, Pd) };
}

// Angle signé projeté de la direction a vers b dans une vue ('F' ou 'S'), en degrés.
// Frontal : < 0 = varus (distal vers médial). Sagittal : > 0 = procurvatum (distal vers caudal).
export function angleProjete(vue, a, b) { return P2.ang(VUE[vue].to2(a), VUE[vue].to2(b)) * DEG; }

// ------------------------------------------------------------- planification --
// cas : élément de CAS (ou casDe(id)) ; opts : { thetaF, thetaS, niveau } (facultatif) et, pour un os segmenté :
//   sansDeformite : true -> l'os est analysé tel quel (pas de déformité imposée, pas de vérité terrain) ;
//   reference : 'sain' (défaut : os sain du modèle = membre controlatéral idéal) ou
//               { type: 'normales', valeurs: { mMPTA: …, … }, sd: { … }, gabarit } (méthode de Paley, valeurs normales).
// Retourne tout ce qu'il faut pour afficher la planification étape par étape.
export const THETA_MIN = 0.5;                      // en dessous : axes considérés parallèles (pas de CORA)
// en dessous : pas de dérotation. Une angulation pure fait varier de quelques dixièmes de degré la torsion mesurée
// avec l'axe mécanique (la fermeture raccourcit l'os de 2 mm et incline cet axe) : ce n'est pas une torsion.
export const DEROTATION_MIN = 1.0;

// --------------------------------------------- articulations, os voisins, broches --
// Zones articulaires (cartilage) : carte du cartilage du modèle fictif si elle existe ; sinon (os segmenté sur CT)
// approximation géométrique calibrée sur ce modèle, en fraction de la longueur : fémur, trochlée jusqu'à 22,9 % du bout
// distal côté crânial, condyles 14,1 % côté caudal, tête 10,4 % du bout proximal côté médial ; tibia, plateau 6,1 %,
// cochlée 5,8 %.
export const ZONE_ARTICULAIRE = { femur: { distCran: 0.229, distCaud: 0.141, prox: 0.104 }, tibia: { prox: 0.061, dist: 0.058 } };
export const MARGE_COUPE_CARTILAGE = 5;     // mm entre un trait de coupe et le cartilage (sinon : règle 2)
export const MARGE_BROCHE_CARTILAGE = 3;    // mm entre l'axe d'une broche et le cartilage
export const MARGE_BROCHE_VOISIN = 2.0;     // mm entre l'axe d'une broche et les sommets d'un os voisin (rayon 0,8 +
                                            // 0,7 de jeu + 0,5 : la surface peut passer plus près que ses sommets)
export const RETRAIT_DERIVE_MAX = 0.03;    // dérive (sinus) tolérée vers l'autre moitié quand une moitié du guide sort
export const ANGLE_ENTREE_MAX = 50;         // ° entre une broche et la normale à la corticale d'entrée (au-delà, la
                                            // mèche glisse sur l'os et la broche tient mal)
export const VOISINS = { femur: ['patella', 'fabellae'], tibia: [] };
// Abords chirurgicaux usuels (repère de l'os : X latéral, Y proximal, Z caudal ; membre gauche mis en miroir) et
// demi-ouverture du secteur où le guide peut être posé. Fémur : abord latéral (diaphyse et fémur distal), abord médial
// pour l'ostéotomie distale ; le crânial (quadriceps, rotule, trochlée) et le caudal (nerf sciatique, vaisseaux) sont
// exclus. Tibia : face médiale sous-cutanée ; abord latéral plus étroit (muscles crâniaux, fibula).
export const ABORDS = {
  femur: [{ nom: 'latéral', dir: [1, 0, 0], demi: 60 }, { nom: 'médial', dir: [-1, 0, 0], demi: 45 }],
  tibia: [{ nom: 'médial', dir: [-1, 0, 0], demi: 60 }, { nom: 'latéral', dir: [1, 0, 0], demi: 30 }],
};
// nom d'une direction transverse (repère de l'os)
export function nomDirection(f) {
  const a = Math.atan2(f[2], f[0]) * DEG;                 // 0 latéral, 90 caudal, ±180 médial, −90 crânial
  const noms = ['latérale', 'caudo-latérale', 'caudale', 'caudo-médiale', 'médiale', 'crânio-médiale', 'crâniale', 'crânio-latérale'];
  return noms[((Math.round(a / 45) % 8) + 8) % 8];
}
// La lame entre toujours du côté OPPOSÉ à la charnière : par la face du coin (corticale convexe pour un coin de
// fermeture, concave pour un coin d'ouverture). Le guide de coupe se pose sur cette face d'entrée. Si elle n'est pas
// dans un abord usuel (ou si un os voisin est sur le trajet de la lame), le guide se pose sur la face accessible la plus
// proche, à condition qu'elle reste à moins de ANGLE_ENTREE_COIN_MAX de la face du coin : au-delà, la lame entrerait
// du côté de la charnière (les deux traits d'un coin de fermeture se croiseraient sous le guide, le coin ne pourrait pas
// sortir). Ce type de coin n'est alors pas réalisable par un abord usuel : on le signale et on recommande l'autre.
export const ANGLE_ENTREE_COIN_MAX = 60;   // ° entre la face d'entrée de la lame et la face du coin (choix du projet)
export const PONT_MAX = 3;                 // mm : charnière corticale au-delà de laquelle le pont d'os ne plie plus
export const CHARNIERE_OUVERTURE_MAX = 3;  // mm : coin d'ouverture, au-delà le côté convexe devrait se chevaucher
// Face du guide pour un coin dont la face d'entrée idéale est `faceCoin` (transverse) ; `libre(d)` : aucun os voisin
// dans les tours de fente posées sur la face d (trajet de la lame). Recherche, dans chaque secteur d'abord, de la
// direction libre la plus proche de la face du coin (pas de 5°, du bord le plus proche vers l'autre bord).
function choisirAbord(bone, faceCoin, axe, libre) {
  const liste = ABORDS[bone] || [];
  const f0 = V.norm(V.perp(faceCoin, axe));
  if (!liste.length) {
    const ok = libre(faceCoin);
    return { face: faceCoin, abord: null, ecart: 0, faisable: ok, charniere: ok, nonUsuel: false };
  }
  let best = null;
  for (const a of liste) {
    const d0 = V.norm(V.perp(a.dir, axe));
    const ang = V.angle(f0, d0);
    const s = Math.sign(V.dot(V.cross(d0, f0), axe)) || 1;     // sens de rotation autour de l'os : de d0 vers f0
    for (let t = Math.min(ang, a.demi); t >= -a.demi - 1e-9; t -= 5) {
      const d = V.norm(M3.mv(M3.axisAngle(axe, s * t * RAD), d0));
      const ecart = V.angle(d, f0);
      if (best && ecart >= best.ecart - 1e-9) break;          // déjà plus loin que la meilleure direction trouvée
      if (libre(d)) { best = { face: ecart < 0.01 ? faceCoin : d, abord: a.nom, ecart: ecart < 0.01 ? 0 : ecart }; break; }
    }
  }
  if (best && best.ecart === 0) return { ...best, faisable: true, charniere: true, nonUsuel: false };
  if (best && best.ecart <= ANGLE_ENTREE_COIN_MAX) return { ...best, faisable: true, charniere: false, nonUsuel: false };
  // aucun abord usuel ne permet d'entrer du bon côté : le guide reste sur la face du coin (abord non usuel)
  const ok = libre(faceCoin);
  return { face: faceCoin, abord: null, ecart: 0, faisable: false, charniere: ok, nonUsuel: true, voisinSurLame: !ok, abordProche: best };
}   // os voisins (la fibula est un maillage du tibia)
export function masqueArticulaire(model, bone) {
  const b = model.bones[bone];
  if (!b) return null;
  const nv = b.pos.length / 3, m = new Uint8Array(nv);
  if (b.cart) {
    const seuil = b.cart instanceof Uint8Array ? 128 : 0.5;
    for (let i = 0; i < nv; i++) m[i] = b.cart[i] >= seuil ? 1 : 0;
    return m;
  }
  const ax = axisInfo(model.meta, bone), Lg = ax.y_top - ax.y_bot, Z = ZONE_ARTICULAIRE[bone];
  for (let i = 0; i < nv; i++) {
    const x = b.pos[3 * i], y = b.pos[3 * i + 1], z = b.pos[3 * i + 2], ctr = ax.centerAt(y);
    const dd = y - ax.y_bot, dp = ax.y_top - y;
    m[i] = bone === 'femur'
      ? ((dd < (z < ctr[2] ? Z.distCran : Z.distCaud) * Lg) || (dp < Z.prox * Lg && x < ctr[0]) ? 1 : 0)
      : (dp < Z.prox * Lg || dd < Z.dist * Lg ? 1 : 0);
  }
  return m;
}
// points (Float32Array xyz) d'un maillage retenus par un masque
function pointsMasques(pos, m) {
  let n = 0;
  for (let i = 0; i < m.length; i++) n += m[i];
  const out = new Float32Array(3 * n);
  for (let i = 0, j = 0; i < m.length; i++) if (m[i]) { out[j++] = pos[3 * i]; out[j++] = pos[3 * i + 1]; out[j++] = pos[3 * i + 2]; }
  return out;
}
// Index spatial des nuages de points. La recherche des broches (placerBroches) évalue des milliers de positions ;
// chacune parcourait tous les sommets de l'os, du cartilage et des os voisins (≈ 40 s sur un fémur segmenté). Les points
// sont rangés une fois dans une grille de cellules de CELLULE mm ; une requête n'examine que les cellules qui peuvent
// contenir un point retenu, avec la même formule point par point que le parcours complet : résultats identiques.
const CELLULE = 1.5;                         // mm
const PETIT_NUAGE = 256;                     // en dessous : parcours complet (la grille ne ferait rien gagner)
const GRILLES = new WeakMap();               // nuage (Float32Array) -> grille, construite à la première requête
function grille(pts) {
  let g = GRILLES.get(pts);
  if (g) return g;
  const n = pts.length / 3, lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < pts.length; i += 3) for (let c = 0; c < 3; c++) { lo[c] = Math.min(lo[c], pts[i + c]); hi[c] = Math.max(hi[c], pts[i + c]); }
  let h = CELLULE, nd;
  for (;;) { nd = lo.map((l, c) => Math.floor((hi[c] - l) / h) + 1); if (nd[0] * nd[1] * nd[2] <= 4e6) break; h *= 2; }
  const [nx, ny, nz] = nd, nc = nx * ny * nz, cellule = new Uint32Array(n), debut = new Uint32Array(nc + 1);
  for (let p = 0; p < n; p++) {
    const k = (Math.floor((pts[3 * p + 2] - lo[2]) / h) * ny + Math.floor((pts[3 * p + 1] - lo[1]) / h)) * nx + Math.floor((pts[3 * p] - lo[0]) / h);
    cellule[p] = k; debut[k + 1]++;
  }
  for (let k = 0; k < nc; k++) debut[k + 1] += debut[k];
  const ordre = new Uint32Array(n), suivant = debut.slice(0, nc);
  for (let p = 0; p < n; p++) ordre[suivant[cellule[p]]++] = p;
  g = { lo, hi, h, nx, ny, nz, debut, ordre, vu: new Uint32Array(nc), passage: 0 };
  GRILLES.set(pts, g);
  return g;
}
// Cellules qui touchent l'une des boîtes de demi-côté r + h / 2 centrées sur les points a + s·d, s de s0 à s1 par pas
// ≤ h (extrémités comprises) : elles contiennent tous les points à moins de r de cette portion de droite. Appelle
// f(indice du point) pour chacun de leurs points, chaque cellule une seule fois ; f renvoie true pour arrêter.
function parcourirLeLong(g, a, d, s0, s1, r, f) {
  const { lo, h, nx, ny, nz, debut, ordre, vu } = g;
  if (++g.passage === 0xffffffff) { vu.fill(0); g.passage = 1; }
  const marque = g.passage, demi = r + h / 2 + 0.05;          // 0,05 mm : marge (direction pas tout à fait unitaire)
  const longueur = Math.abs(s1 - s0) * Math.hypot(d[0], d[1], d[2]);
  const m = Math.max(1, Math.ceil(longueur / h));
  for (let k = 0; k <= m; k++) {
    const s = s0 + (s1 - s0) * k / m, c = [a[0] + s * d[0], a[1] + s * d[1], a[2] + s * d[2]];
    const i0 = Math.max(0, Math.floor((c[0] - demi - lo[0]) / h)), i1 = Math.min(nx - 1, Math.floor((c[0] + demi - lo[0]) / h));
    const j0 = Math.max(0, Math.floor((c[1] - demi - lo[1]) / h)), j1 = Math.min(ny - 1, Math.floor((c[1] + demi - lo[1]) / h));
    const l0 = Math.max(0, Math.floor((c[2] - demi - lo[2]) / h)), l1 = Math.min(nz - 1, Math.floor((c[2] + demi - lo[2]) / h));
    for (let l = l0; l <= l1; l++) for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
      const cel = (l * ny + j) * nx + i;
      if (vu[cel] === marque) continue;
      vu[cel] = marque;
      for (let q = debut[cel]; q < debut[cel + 1]; q++) if (f(ordre[q])) return true;
    }
  }
  return false;
}
// distance entre le nuage de points (Float32Array xyz) et le segment [a, b] inférieure à seuil ?
// (même résultat que « distance minimale < seuil » calculée sur tous les points)
function nuageProche(pts, a, b, seuil) {
  const ab = V.sub(b, a), L2 = V.dot(ab, ab) || 1;
  const pres = (i) => {
    const px = pts[i] - a[0], py = pts[i + 1] - a[1], pz = pts[i + 2] - a[2];
    const t = Math.min(1, Math.max(0, (px * ab[0] + py * ab[1] + pz * ab[2]) / L2));
    const dx = px - t * ab[0], dy = py - t * ab[1], dz = pz - t * ab[2];
    return Math.sqrt(dx * dx + dy * dy + dz * dz) < seuil;
  };
  if (pts.length / 3 <= PETIT_NUAGE) {
    for (let i = 0; i < pts.length; i += 3) if (pres(i)) return true;
    return false;
  }
  return parcourirLeLong(grille(pts), a, ab, 0, 1, seuil, (p) => pres(3 * p));
}
// étendue de l'os le long d'une droite (point a, direction unitaire d) : sommets à moins de r de la droite
function etendueLeLong(pos, a, d, r = 1.2) {
  let tmin = Infinity, tmax = -Infinity, iMax = -1;
  const examiner = (i) => {
    const px = pos[i] - a[0], py = pos[i + 1] - a[1], pz = pos[i + 2] - a[2];
    const t = px * d[0] + py * d[1] + pz * d[2];
    const qx = px - t * d[0], qy = py - t * d[1], qz = pz - t * d[2];
    // à t égal, le premier sommet dans l'ordre du maillage (comme le parcours complet)
    if (qx * qx + qy * qy + qz * qz < r * r) { if (t < tmin) tmin = t; if (t > tmax || (t === tmax && i < iMax)) { tmax = t; iMax = i; } }
  };
  if (pos.length / 3 <= PETIT_NUAGE) {
    for (let i = 0; i < pos.length; i += 3) examiner(i);
  } else {
    // portion de la droite dans la boîte des sommets élargie de r (méthode des tranches)
    const g = grille(pos), e = r + 0.05;
    let s0 = -Infinity, s1 = Infinity;
    for (let c = 0; c < 3; c++) {
      if (Math.abs(d[c]) < 1e-12) { if (a[c] < g.lo[c] - e || a[c] > g.hi[c] + e) return null; continue; }
      const u = (g.lo[c] - e - a[c]) / d[c], w = (g.hi[c] + e - a[c]) / d[c];
      s0 = Math.max(s0, Math.min(u, w)); s1 = Math.min(s1, Math.max(u, w));
    }
    if (s0 > s1) return null;
    parcourirLeLong(g, a, d, s0, s1, r, (p) => { examiner(3 * p); return false; });
  }
  return Number.isFinite(tmin) ? { tmin, tmax, iMax } : null;
}
// normales aux sommets d'un maillage (moyenne des normales des triangles, pondérée par leur aire)
function normalesSommets(pos, idx) {
  const n = new Float32Array(pos.length);
  for (let f = 0; f < idx.length; f += 3) {
    const a = 3 * idx[f], b = 3 * idx[f + 1], c = 3 * idx[f + 2];
    const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
    const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const k of [a, b, c]) { n[k] += nx; n[k + 1] += ny; n[k + 2] += nz; }
  }
  for (let i = 0; i < n.length; i += 3) { const l = Math.hypot(n[i], n[i + 1], n[i + 2]) || 1; n[i] /= l; n[i + 1] /= l; n[i + 2] /= l; }
  return n;
}
// Tours de fente du guide (même construction que etape7_guide.py) : pavé centré sur chaque plan de coupe, de la
// largeur de l'os (+ 1 mm + paroi de chaque côté) dans la direction de la fente, du milieu de la section jusqu'à
// jeu + coque + guidage au-dessus de l'os, côté face d'appui.
function toursFente(plans, face, osPos, osIdx, largeur, sections = null) {
  return plans.map((pl, ip) => {
    const n = V.norm(pl.n), hh = V.norm(V.perp(face, n)), ll = V.cross(n, hh);
    let lmin = Infinity, lmax = -Infinity, hmax = -Infinity, hs = 0, nb = 0;
    for (const q of sections ? sections[ip] : sectionPoints(osPos, osIdx, pl.p, n)) {
      const r = V.sub(q, pl.p);
      if (V.len(r) > 1.5 * largeur + 10) continue;
      const l = V.dot(r, ll), h = V.dot(r, hh);
      lmin = Math.min(lmin, l); lmax = Math.max(lmax, l); hmax = Math.max(hmax, h); hs += h; nb++;
    }
    if (!nb) return null;
    const hc = hs / nb;
    return { p: pl.p, n, hh, ll, l0: lmin - 1 - INSTRUMENT.paroi, l1: lmax + 1 + INSTRUMENT.paroi,
      h0: hc + 0.5 * (hmax - hc), h1: hmax + INSTRUMENT.jeuGuide + INSTRUMENT.coque + INSTRUMENT.guidage };
  }).filter(Boolean);
}
// distance d'un point à une tour de fente (pavé dans le repère n, hh, ll du plan)
function distTour(q, t) {
  const r = V.sub(q, t.p);
  const x = Math.max(Math.abs(V.dot(r, t.n)) - DEMI_TOUR, 0);
  const l = V.dot(r, t.ll), h = V.dot(r, t.hh);
  const y = Math.max(t.l0 - l, l - t.l1, 0), z = Math.max(t.h0 - h, h - t.h1, 0);
  return Math.hypot(x, y, z);
}
// Une broche (point a de son axe dans l'os, direction d vers l'os) est-elle acceptable ? Contrôles :
//   - de l'os à traverser (bicorticale), mesuré le long de la broche ;
//   - à distance des plans de coupe : 2 mm de pont osseux dans l'os, du bon côté ;
//   - à distance du cartilage et des os voisins, de la pointe (5 mm au-delà de la corticale opposée) jusqu'à 15 mm
//     au-dessus de la corticale d'entrée.
// Le manchon contre la tour de fente (qui dépend de la hauteur du manchon) est contrôlé à part (manchonLibre).
function evaluerBroche(a, d, ctx) {
  const o = V.neg(d), cote = ctx.distal ? 1 : -1;
  // 1. rejet rapide sur le point a lui-même (toujours dans l'os, sur la ligne centrale du fragment)
  for (const pl of ctx.plans) if (V.dot(V.sub(a, pl.p), V.norm(pl.n)) * cote < 2) return { ok: false, raison: 'trop près du trait de coupe' };
  if (ctx.art && ctx.art.length && nuageProche(ctx.art, a, a, MARGE_BROCHE_CARTILAGE)) return { ok: false, raison: 'dans le cartilage' };
  // 2. contrôles exacts le long de la broche
  const et = etendueLeLong(ctx.osPos, a, o);
  if (!et || et.tmax - et.tmin < 5) return { ok: false, raison: 'hors de l\'os' };
  if (ctx.osNrm) {                                         // entrée sur la corticale : pas trop oblique
    const i = et.iMax, c = Math.abs(ctx.osNrm[i] * o[0] + ctx.osNrm[i + 1] * o[1] + ctx.osNrm[i + 2] * o[2]);
    if (Math.acos(Math.min(1, c)) * DEG > ANGLE_ENTREE_MAX) return { ok: false, raison: 'entrée trop oblique sur la corticale' };
  }
  const pointe = V.add(a, V.mul(o, et.tmin - 5)), entree = V.add(a, V.mul(o, et.tmax)), haut = V.add(a, V.mul(o, et.tmax + 15));
  for (const pl of ctx.plans) {
    const n = V.norm(pl.n), sa = V.dot(V.sub(pointe, pl.p), n), se = V.dot(V.sub(entree, pl.p), n);
    if (Math.min(sa * cote, se * cote) < 2) return { ok: false, raison: 'trop près du trait de coupe' };
  }
  // les autres traits (coin de fermeture) : derrière la charnière, les deux plans se croisent ; la pointe d'une broche
  // qui dépasse la corticale opposée ne doit pas entrer dans le trajet de la lame de l'autre trait (coupe complète)
  for (const pl of ctx.autresPlans || []) {
    const n = V.norm(pl.n), sa = V.dot(V.sub(pointe, pl.p), n), sh = V.dot(V.sub(haut, pl.p), n);
    if (sa * sh <= 0 || Math.min(Math.abs(sa), Math.abs(sh)) < 1.6) return { ok: false, raison: 'pointe sur le trajet de la lame de l\'autre trait' };
  }
  // broche (pointe -> entrée) puis manchon du guide (entrée -> 15 mm au-dessus, rayon RAYON_MANCHON) : le manchon ne doit
  // ni reposer sur le cartilage ni toucher un os voisin (1 mm de tissus mous)
  if (ctx.art && ctx.art.length && (nuageProche(ctx.art, pointe, entree, MARGE_BROCHE_CARTILAGE)
    || nuageProche(ctx.art, entree, haut, RAYON_MANCHON + 0.5))) return { ok: false, raison: 'dans le cartilage' };
  // os voisins : la broche est contrôlée jusqu'à 8 mm au-delà de la corticale opposée (5 mm prévus + 3 mm d'erreur de
  // profondeur de forage) : une broche qui vise la fibula ne doit pas pouvoir l'embrocher si on fore un peu trop loin
  const pointeSecu = V.add(a, V.mul(o, et.tmin - 8));
  for (const vp of ctx.voisins) {
    if (nuageProche(vp, pointeSecu, entree, MARGE_BROCHE_VOISIN) || nuageProche(vp, entree, haut, RAYON_MANCHON + 1)) return { ok: false, raison: 'dans un os voisin' };
  }
  return { ok: true, entree, sortie: V.add(a, V.mul(o, et.tmin)), longueurOs: et.tmax - et.tmin };
}
// manchon (de l'entrée dans l'os jusqu'à sa hauteur) assez loin des tours de fente du guide
function manchonLibre(ev, d, tours, hauteur) {
  const o = V.neg(d);
  for (const t of tours || []) {
    for (let s1 = 0; s1 <= hauteur; s1 += 1.5) if (distTour(V.add(ev.entree, V.mul(o, s1)), t) < RAYON_MANCHON + 0.5) return false;
  }
  return true;
}
// Configurations de broches de réduction : nombre de broches par fragment et disposition imposée.
//   2+2 : 2 par fragment (le guide de réduction bloque les 6 degrés de liberté de chaque fragment) ;
//   1+1 : 1 par fragment (un fragment peut tourner autour de sa propre broche : seuls les manchons du guide de
//         réduction, au contact de l'os, s'y opposent) ;
//   1+2 : 1 proximale (fragment long, tenu par le membre) + 2 distales côte à côte, au même niveau (« horizontales »).
export const CONFIG_BROCHES = {
  '2+2': { prox: 2, dist: 2, nom: '2 par fragment (4 broches)' },
  '1+1': { prox: 1, dist: 1, nom: '1 par fragment (2 broches)' },
  '1+2': { prox: 1, dist: 2, dispDist: 'transversale', nom: '1 proximale + 2 distales côte à côte (3 broches)' },
};
// Place les broches de réduction : 1 ou 2 par fragment (CONFIG_BROCHES), à une distance e de la coupe le long de l'os
// (préférée : 1,2 × largeur, sinon plus près, jamais contre la tour de fente). Deux broches d'un même fragment : l'une
// derrière l'autre (écart 10, 8 puis 6,5 mm) ou, si le fragment est court (ou si la configuration l'impose), côte à côte
// au même niveau (écart 6,5 à 9 mm) ; le groupe est centré sur la ligne centrale du fragment, ou décalé de 2 à 4 mm (au
// plus 20 % de la largeur) en dernier recours, par exemple pour s'écarter de la trochlée sur un fragment distal court.
// Direction : vers la face d'appui, tournée autour de l'os de β (0, ±5°… ±45°) pour éviter le cartilage et les os
// voisins. Les broches distales sont forées avec l'inverse de la correction : toutes sont parallèles après la
// correction. Chaque position est évaluée une seule fois (cache).
function placerBroches(g) {
  const { u, face, Tinv, largeur } = g;
  const cfg = g.config || CONFIG_BROCHES['2+2'];
  // direction des broches proximales : vers l'os depuis la face d'appui, tournée de β autour de l'os, puis inclinée de γ
  // le long de l'os (γ > 0 : pointe vers distal), seulement si le retrait du guide l'exige
  const dirProx = (beta, gamma = 0) => {
    const d0 = M3.mv(RT.aboutAxis([0, 0, 0], u, beta * RAD).R, V.neg(face));
    return gamma ? V.norm(V.add(V.mul(d0, Math.cos(gamma * RAD)), V.mul(u, Math.sin(gamma * RAD)))) : d0;
  };
  const ePref = Math.min(Math.max(INSTRUMENT.facteurBroches * largeur, RAYON_MANCHON + DEMI_TOUR + 3), 40);
  const es = [];
  for (let e = ePref; e >= 3; e -= 1) es.push(e);
  for (let e = ePref + 2; e <= ePref + 20; e += 2) es.push(e);
  // dispositions essayées pour n broches dans un fragment ; « imposee » : seulement côte à côte (configuration 1+2)
  const dispositionsPour = (n, imposee) => {
    if (n === 1) return [{ type: 'unique', ecart: 0 }];
    const axiales = [INSTRUMENT.ecartBroches, 8, INSTRUMENT.ecartBrochesMin].map((ecart) => ({ type: 'axiale', ecart }));
    const transversales = [INSTRUMENT.ecartBrochesMin, 7.5, 9].map((ecart) => ({ type: 'transversale', ecart, imposee: imposee === 'transversale' }));
    return imposee === 'transversale' ? transversales : imposee === 'axiale' ? axiales : [...axiales, ...transversales];
  };
  const decalages = [0, 2, -2, 4, -4].filter((x) => Math.abs(x) <= 0.2 * largeur);
  const cache = new Map();
  const candidat = (frag, orient, dd, t, e, x) => {
    const cle = `${frag}|${orient}|${e}|${x.toFixed(2)}`;
    let r = cache.get(cle);
    if (!r) {
      const pt = V.add(g.centre(frag, e), V.mul(t, x));
      const propres = frag === 'proximal' ? g.plansProx : g.plansDist;
      r = { pt, ev: evaluerBroche(pt, dd, { ...g.ctx, plans: propres, autresPlans: (g.tousPlans || []).filter((x) => !propres.includes(x)), distal: frag === 'distal' }) };
      cache.set(cle, r);
    }
    return r;
  };
  const paire = (frag, orient, d, hauteurManchon) => {
    let meilleur = null;
    const n = frag === 'proximal' ? cfg.prox : cfg.dist;
    const dispositions = dispositionsPour(n, frag === 'proximal' ? cfg.dispProx : cfg.dispDist);
    const dd = frag === 'proximal' ? d : M3.mv(Tinv.R, d);
    const t = V.norm(V.cross(dd, frag === 'proximal' ? u : g.v));         // ⊥ à la broche et à l'os
    for (const [iDisp, disp] of dispositions.entries()) {
      // côte à côte plus large que 60 % de l'os : seulement si la configuration l'impose (et alors l'écart le plus petit)
      if (disp.type === 'transversale' && disp.ecart > 0.6 * largeur && !(disp.imposee && iDisp === 0)) continue;
      for (const x of decalages) {
        for (const e of es) {
          const cs = disp.type === 'unique' ? [candidat(frag, orient, dd, t, e, x)]
            : disp.type === 'axiale' ? [candidat(frag, orient, dd, t, e, x), candidat(frag, orient, dd, t, e + disp.ecart, x)]
              : [candidat(frag, orient, dd, t, e, x + disp.ecart / 2), candidat(frag, orient, dd, t, e, x - disp.ecart / 2)];
          const ev = cs.map((c) => (c.ev.ok && !manchonLibre(c.ev, dd, g.tours, hauteurManchon) ? { ok: false, raison: 'manchon contre la tour de fente' } : c.ev));
          const nOk = ev.filter((y) => y.ok).length;
          const r = { ok: nOk === n, n, pts: cs.map((c) => c.pt), dir: dd, ev, e, ecart: disp.ecart, disposition: disp.type, decalage: x, nOk, hauteurManchon };
          if (r.ok) return r;
          if (!meilleur || nOk > meilleur.nOk) meilleur = r;
        }
      }
    }
    return meilleur || { ok: false, n, pts: [], dir: dd, ev: [], e: 0, ecart: 0, disposition: dispositions[0].type, decalage: 0, nOk: 0, hauteurManchon };
  };
  // manchons de 15 mm (guidage ≈ 0,9°) ; si un manchon heurte la tour de fente (broches très inclinées d'un grand coin),
  // ils sont raccourcis à 10 puis 8 mm (≈ 1,4°). La paire proximale garde 15 mm : calculée une fois par orientation.
  // Retrait du guide de coupe : après la coupe des ponts, chaque moitié sort le long de ses broches. Il faut qu'au moins
  // une moitié s'éloigne de l'autre en sortant (sinon elles se heurtent dans la fente de séparation, 0,8 mm de jeu sur
  // 15 à 20 mm de course) : dérive vers l'autre moitié ≤ RETRAIT_DERIVE_MAX (≈ 2°) pour l'une des deux.
  const nSep = V.norm(g.plansProx[0].n);
  const retirable = (d) => Math.max(V.dot(d, nSep), -V.dot(M3.mv(Tinv.R, d), nSep)) >= -RETRAIT_DERIVE_MAX;
  // Si aucune rotation β ne permet le retrait (grand coin d'ouverture posé par un autre abord, par exemple), les broches
  // sont inclinées de γ = ± 10 puis ± 20° le long de l'os : la moitié correspondante recule alors en sortant.
  const BETAS = [0, 5, -5, 10, -10, 15, -15, 20, -20, 25, -25, 30, -30, 35, -35, 40, -40, 45, -45];
  const GAMMAS = [0, 10, -10, 20, -20];
  const prox = new Map();
  let choix = null;
  for (const exigerRetrait of [true, false]) {
    for (const gamma of exigerRetrait ? GAMMAS : [0]) {
      for (const hauteur of [15, 10, 8]) {
        for (const beta of BETAS) {
          const d = dirProx(beta, gamma), orient = `${beta}|${gamma}`;
          if (exigerRetrait && !retirable(d)) continue;
          if (!prox.has(orient)) prox.set(orient, paire('proximal', orient, d, 15));
          const pp = prox.get(orient);
          if (!pp.ok && choix && choix.pp.ok) continue;                  // une orientation meilleure existe déjà
          const pd = paire('distal', orient, d, hauteur);
          const score = (pp.ok ? 10 : pp.nOk || 0) + (pd.ok ? 10 : pd.nOk || 0);
          if (!choix || score > choix.score) choix = { beta, gamma, pp, pd, score, retrait: retirable(d) };
          if (pp.ok && pd.ok) return choix;
        }
      }
    }
  }
  return choix;
}

// ------------------------------------- contraintes chirurgicales (biologiques) au niveau de la coupe --
// Ce qui peut empêcher de couper à un niveau donné : cartilage et capsule articulaire, insertions (ligament patellaire
// sur la tubérosité tibiale, ligaments collatéraux aux épicondyles), physes d'un chien en croissance, place pour la
// fixation de chaque fragment, qualité de consolidation (métaphyse / diaphyse), structures à protéger selon l'abord.
// niveau : 'bloquant' (ne pas couper ici), 'attention', 'info', 'ok'.
export const FRAGMENT_MIN_MM = 25;          // longueur minimale d'un fragment : plaque avec ≥ 3 vis bicorticales et ses
                                            // broches (choix raisonné du projet, à adapter à l'implant)
export const MARGE_TUBEROSITE_MM = 8;       // tubérosité tibiale (insertion du ligament patellaire)
export const MARGE_EPICONDYLE_MM = 6;       // épicondyles fémoraux (origine des ligaments collatéraux)
// physes d'un chien en croissance : zones approchées en fraction de la longueur depuis chaque extrémité (non segmentées :
// à vérifier sur le scanner, les physes ouvertes y sont visibles)
export const ZONE_PHYSE = { femur: { prox: 0.10, dist: 0.17 }, tibia: { prox: 0.10, dist: 0.07 } };
export const STRUCTURES_ABORD = {
  tibia: {
    'médial': 'veine et artère saphènes médiales et nerf saphène, qui croisent la face médiale ; derrière l\'os, artères poplitée puis tibiale crâniale (protéger la corticale opposée avec un écarteur de Hohmann)',
    'latéral': 'muscles tibial crânial et extenseurs ; artère tibiale crâniale et nerf fibulaire (péronier) entre le tibia et la fibula',
  },
  femur: {
    'latéral': 'nerf sciatique en arrière du fémur (protéger la corticale caudale) ; vaste latéral et biceps fémoral à écarter',
    'médial': 'artère et veine fémorales et nerf saphène ; au fémur distal, artère génienne descendante',
  },
};
export function contraintesCoupe(x) {
  const { bone, L, ax, cp } = x;
  const out = [];
  const Lg = ax.y_top - ax.y_bot, y = cp.Pc[1];
  const f1 = (v_) => v_.toFixed(1).replace('.', ',');
  // 1. cartilage articulaire (et capsule) : le trait doit en rester à MARGE_COUPE_CARTILAGE
  if (Number.isFinite(cp.dCart)) {
    out.push(cp.dCart < MARGE_COUPE_CARTILAGE || cp.dansCoin
      ? { niveau: 'bloquant', id: 'cartilage', texte: `cartilage articulaire à ${f1(cp.dCart)} mm du trait (minimum ${MARGE_COUPE_CARTILAGE} mm)${cp.dansCoin ? ', et dans le coin à retirer' : ''} : fracture articulaire, arthrose ; déplacer la coupe vers la diaphyse` }
      : { niveau: 'ok', id: 'cartilage', texte: `cartilage articulaire à ${f1(cp.dCart)} mm du trait (≥ ${MARGE_COUPE_CARTILAGE} mm)` });
  }
  // 2. place pour la fixation : chaque fragment doit recevoir la plaque (≥ 3 vis) et ses broches
  for (const [nom, l] of [['proximal', ax.y_top - y], ['distal', y - ax.y_bot]]) {
    if (l < FRAGMENT_MIN_MM) out.push({ niveau: 'attention', id: `fragment_${nom}`, texte: `fragment ${nom} de ${f1(l)} mm seulement : peu de place pour la plaque (≥ 3 vis) et les broches` });
  }
  // 3. insertions tendineuses et ligamentaires
  if (bone === 'tibia' && L.tuberosity) {
    const d = Math.min(...cp.plans.map((pl) => Math.abs(V.dot(V.sub(L.tuberosity, pl.p), V.norm(pl.n)))));
    if (d < MARGE_TUBEROSITE_MM) out.push({ niveau: 'bloquant', id: 'tuberosite', texte: `trait à ${f1(d)} mm de la tubérosité tibiale : insertion du ligament patellaire (appareil extenseur) fragilisée ou détachée` });
  }
  if (bone === 'femur' && L.epi_med && L.epi_lat) {
    const d = Math.min(...[L.epi_med, L.epi_lat].flatMap((p) => cp.plans.map((pl) => Math.abs(V.dot(V.sub(p, pl.p), V.norm(pl.n))))));
    if (d < MARGE_EPICONDYLE_MM) out.push({ niveau: 'attention', id: 'epicondyles', texte: `trait à ${f1(d)} mm d'un épicondyle : origine des ligaments collatéraux du grasset` });
  }
  // 4. physes (chien en croissance) : une coupe à travers la physe arrête la croissance (déformité secondaire)
  const zp = ZONE_PHYSE[bone];
  if (x.croissance && zp) {
    if (ax.y_top - y < zp.prox * Lg + 3) out.push({ niveau: 'bloquant', id: 'physe_proximale', texte: `zone de la physe proximale (chien en croissance, zone approchée à ${Math.round(zp.prox * 100)} % de la longueur) : arrêt de croissance` });
    if (y - ax.y_bot < zp.dist * Lg + 3) out.push({ niveau: 'bloquant', id: 'physe_distale', texte: `zone de la physe distale (chien en croissance, zone approchée à ${Math.round(zp.dist * 100)} % de la longueur) : arrêt de croissance` });
  }
  // 5. consolidation : métaphyse (os spongieux bien vascularisé) ou diaphyse (os cortical, plus lent)
  const fr = (ax.y_top - y) / Lg;
  const meta = fr < 0.2 || fr > 0.8;
  out.push({ niveau: 'info', id: 'consolidation', texte: meta ? 'métaphyse : os spongieux bien vascularisé, large surface de contact : consolidation rapide' : 'diaphyse : os cortical, consolidation plus lente (contact osseux et stabilité de la fixation importants)' });
  if (bone === 'tibia' && fr > 0.66 && fr <= 0.8) out.push({ niveau: 'attention', id: 'tiers_distal', texte: 'tiers distal du tibia : peu de muscles autour de l\'os, vascularisation périostée pauvre : consolidation plus lente' });
  // 6. translation de la règle 2 : contact osseux
  if (x.regle === 2) {
    const r = x.translation / x.largeur;
    out.push({ niveau: r > 0.5 ? 'bloquant' : r > 0.25 ? 'attention' : 'info', id: 'translation', texte: `translation de ${f1(x.translation)} mm à l'ostéotomie (${Math.round(100 * r)} % de la largeur de l'os)${r > 0.5 ? ' : contact osseux insuffisant' : ''}` });
  }
  // 7. structures à protéger pendant l'abord et la coupe
  const s_ = x.abord && STRUCTURES_ABORD[bone]?.[x.abord];
  if (s_) out.push({ niveau: 'info', id: 'abord', texte: `abord ${x.abord} : ${s_}` });
  if (x.nonUsuel) out.push({ niveau: 'attention', id: 'abord', texte: 'abord non usuel pour ce type de coin : dissection plus large, structures du côté opposé à protéger' });
  return out;
}

// ------------------------------------------------------------- ouverture ou fermeture ? --
// Choix du type de coin, critère par critère ; le premier qui départage décide (les suivants restent affichés) :
//   1. accès : la lame doit entrer par un abord usuel, du côté opposé à la charnière (faisable) ;
//   2. charnière corticale conservée (stabilité, pas de translation) ;
//   3. règle 1 (coupe au CORA) plutôt que règle 2 (translation à l'ostéotomie) ;
//   4. coin de fermeture assez épais pour deux fentes de scie (≥ 1,5 mm de matière entre elles) ;
//   5. ouverture raisonnable (≤ OUVERTURE_MAX_FRAC de la largeur) : au-delà, greffe et consolidation plus longue ;
//   6. longueur : si le membre opéré est plus court (ou plus long) que le membre opposé, le coin qui compense le mieux ;
//   7. à défaut : fermeture (surfaces d'os en contact, stabilité primaire, pas de greffe).
export const OUVERTURE_MAX_FRAC = 0.40;    // choix raisonné du projet (à valider avec un chirurgien) : 40 % de la largeur,
                                           // soit ≈ 6 mm pour un tibia de 15 mm (les coins d'ouverture du pes varus approchent 30 %)
export function recommanderCoin(osteo, opts = {}) {
  const F = osteo.fermeture, O = osteo.ouverture;
  if (!F && !O) return null;
  if (!F || !O) return { kind: F ? 'fermeture' : 'ouverture', decisif: 'seul', criteres: [] };
  const pref = (bF, bO) => (bF === bO ? null : bF ? 'fermeture' : 'ouverture');
  const fente = INSTRUMENT.lame + INSTRUMENT.jeuFente;
  const ineg = Number.isFinite(opts.inegaliteLongueur) ? opts.inegaliteLongueur : 0;   // mm, + = membre opéré plus court
  let prefL = null;
  if (Math.abs(ineg) >= 3) {
    const eF = Math.abs(F.deltaOperation - ineg), eO = Math.abs(O.deltaOperation - ineg);
    if (Math.abs(eF - eO) >= 1) prefL = eF < eO ? 'fermeture' : 'ouverture';
  }
  const criteres = [
    { id: 'abord', nom: 'Accès : la lame entre par un abord usuel, du côté opposé à la charnière', fermeture: F.faisable, ouverture: O.faisable, prefere: pref(F.faisable, O.faisable) },
    { id: 'charniere', nom: 'Charnière corticale conservée (stabilité, pas de translation)', fermeture: F.charniereConservee, ouverture: O.charniereConservee, prefere: pref(F.charniereConservee, O.charniereConservee) },
    { id: 'regle', nom: 'Règle 1 : coupe au CORA, sans translation', fermeture: F.regle === 1, ouverture: O.regle === 1, prefere: pref(F.regle === 1, O.regle === 1) },
    { id: 'coinFin', nom: 'Coin de fermeture assez épais pour deux fentes (≥ 1,5 mm de matière)', fermeture: F.base - fente >= 1.5, ouverture: true, prefere: F.base - fente < 1.5 ? 'ouverture' : null },
    { id: 'ouverture', nom: `Ouverture ≤ ${Math.round(OUVERTURE_MAX_FRAC * 100)} % de la largeur de l'os (sinon greffe, consolidation longue)`, fermeture: true, ouverture: O.base <= OUVERTURE_MAX_FRAC * O.sectionCoupe.largeur, prefere: O.base > OUVERTURE_MAX_FRAC * O.sectionCoupe.largeur ? 'fermeture' : null },
    { id: 'longueur', nom: Math.abs(ineg) >= 3 ? `Longueur : membre opéré ${ineg > 0 ? 'plus court' : 'plus long'} de ${Math.abs(ineg)} mm` : 'Longueur : pas d\'inégalité de longueur indiquée', fermeture: F.deltaOperation, ouverture: O.deltaOperation, prefere: prefL },
    { id: 'stabilite', nom: 'À défaut : surfaces en contact, stabilité primaire, pas de greffe', fermeture: true, ouverture: false, prefere: 'fermeture' },
  ];
  const d = criteres.find((x) => x.prefere);
  return { kind: d.prefere, decisif: d.id, criteres };
}

export function planifier(model, cas, opts = {}) {
  appliquerInstrument(opts.parametresGuide);       // dimensions du guide générique choisies pour ce cas
  const { bone, frontal, sagittal } = cas;
  const R0 = REGLAGES[bone];
  const sansDef = !!opts.sansDeformite;
  const thetaF = sansDef ? 0 : (opts.thetaF ?? R0.thetaF), niveau = opts.niveau ?? R0.niveau;
  const thetaS = sansDef || sagittal === 'aucun' ? 0 : (opts.thetaS ?? R0.thetaS);
  const refN = opts.reference && opts.reference.type === 'normales' ? opts.reference : null;
  const ref = reference(model, bone);
  const ax = ref.ax;
  const noms = meshesOf(model, bone);

  // 1) os à planifier : os déformé (vérité terrain connue) ou os segmenté tel quel
  const tauTest = sansDef ? 0 : (opts.torsion ?? 0);
  const p1 = { frontal, sagittal, thetaF, thetaS, niveau, largeur: R0.largeur, torsion: tauTest, axeTorsion: ref.axeSain };
  const D = sansDef ? null : makeDeformity(p1, ax);
  const pos = {};
  for (const n of noms) {
    if (!D) { pos[n] = model.bones[n].pos; continue; }
    pos[n] = new Float32Array(model.bones[n].pos.length);
    deformArray(D, model.bones[n].pos, pos[n]);
  }
  const L = {};
  for (const [k, v] of Object.entries(ref.L0)) L[k] = D ? deformPoint(D, v) : [...v];
  const main = { pos: pos[bone], idx: model.bones[bone].idx };

  // 2) lignes articulaires (3D) dans les deux plans, centres articulaires
  const J = JOL[bone];
  const jol = { F: { prox: paire(L, J.F.prox), dist: paire(L, J.F.dist) }, S: { prox: paire(L, J.S.prox), dist: paire(L, J.S.dist) } };
  const centres = bone === 'tibia'
    ? { prox: L.eminence, dist: L.distal_center }
    : { prox: L.head_center, dist: V.mid(L.cond_med_dist, L.cond_lat_dist) };

  // 3) axes des segments (3D)
  let axeProx, axeDist, milieux = null;
  const anat = bone === 'femur' ? axeAnatomique(main.pos, main.idx, ax) : null;
  if (anat) milieux = anat.milieux;
  if (refN) {
    const ap = anat ? { p: anat.p, d: anat.d, depuis: 'milieux de la diaphyse à 1/3 et 1/2 (deux vues)' } : null;
    const A = axesNormales(bone, L, ap, refN.valeurs, refN.gabarit);
    axeProx = A.prox; axeDist = A.dist;
  } else {
    // depuis les repères articulaires et l'orientation normale de l'os sain (membre controlatéral)
    const C3 = cadresArticulaires(bone, L);
    if (bone === 'tibia') {
      axeProx = { p: depuisLocal(C3.prox, ref.prox.pt), d: V.norm(depuisLocalDir(C3.prox, ref.prox.dir)), depuis: 'JOL proximales + orientation normale (mMPTA, mCaPTA)' };
      axeDist = { p: depuisLocal(C3.dist, ref.dist.pt), d: V.norm(depuisLocalDir(C3.dist, ref.dist.dir)), depuis: 'JOL distales + orientation normale (mMDTA, mCrDTA)' };
    } else {
      axeProx = { p: anat.p, d: anat.d, depuis: 'milieux de la diaphyse à 1/3 et 1/2 (deux vues)' };
      axeDist = { p: depuisLocal(C3.dist, ref.dist.pt), d: V.norm(depuisLocalDir(C3.dist, ref.dist.dir)), depuis: 'JOL distales + orientation normale (aLDFA, aCdDFA)' };
    }
  }
  const pre = mesurer(bone, L, axeProx);
  // valeurs « normales » affichées : os sain (mesuré) ou valeurs de référence choisies
  const normal = refN ? { ...ref.normal, ...refN.valeurs, longueur: pre.longueur } : ref.normal;
  const sdRef = refN && refN.sd ? refN.sd : Object.fromEntries(Object.entries(LITTERATURE[bone]).map(([k, x]) => [k, x.sd]));
  const anomalies = [...CLES[bone].F, ...CLES[bone].S].filter((k) => Math.abs(pre[k] - normal[k]) > 2 * sdRef[k]);

  // 4) CORA 3D, angle vrai, projections dans les deux vues
  const u = axeProx.d, v = axeDist.d;
  const theta = V.angle(u, v);
  let cc = theta >= THETA_MIN ? coraPerpCommune(axeProx.p, u, axeDist.p, v) : null;
  const yMilieu = (ax.y_top + ax.y_bot) / 2;
  const coraDansOs = !!cc && cc.C[1] < ax.y_top - 0.04 * (ax.y_top - ax.y_bot) && cc.C[1] > ax.y_bot + 0.04 * (ax.y_top - ax.y_bot);
  const coraVrai = cc ? cc.C : null;                     // intersection réelle des axes (peut être loin de l'os)
  if (!coraDansOs) {                                     // axes parallèles ou CORA hors de l'os : point de tracé au milieu de l'os
    const P0 = V.add(axeProx.p, V.mul(u, (yMilieu - axeProx.p[1]) / u[1]));
    cc = { C: P0, Pp: P0, Pd: V.add(axeDist.p, V.mul(v, (yMilieu - axeDist.p[1]) / v[1])), delta: cc ? cc.delta : V.distLine(axeDist.p, axeProx.p, u) };
  }
  const C = cc.C;
  const proj = {};
  for (const k of ['F', 'S']) {
    const W = VUE[k];
    const up = P2.norm(W.to2(u)), vp = P2.norm(W.to2(v));
    const angle = P2.ang(up, vp) * DEG;
    const cora = P2.intersect(W.to2(axeProx.p), up, W.to2(axeDist.p), vp);
    proj[k] = { up, vp, angle, cora, niveau: cora ? ax.y_top - cora[1] : null };
  }
  const Fm = proj.F.angle, Sm = proj.S.angle;
  const typeF = Math.abs(Fm) < 0.5 ? 'aucun' : Fm < 0 ? 'varus' : 'valgus';
  const typeS = Math.abs(Sm) < 0.5 ? 'aucun' : Sm > 0 ? 'procurvatum' : 'recurvatum';
  const theta2D = Math.atan(Math.hypot(Math.tan(Fm * RAD), Math.tan(Sm * RAD))) * DEG;
  const phi = Math.atan2(Math.abs(Math.tan(Sm * RAD)), Math.abs(Math.tan(Fm * RAD))) * DEG;

  // 5) plan de la déformité, bissectrice, ACA ; c = côté convexe (vers l'apex)
  const nx = V.cross(u, v);
  const nACA = V.len(nx) > 1e-9 ? V.norm(nx) : V.norm(V.cross(u, [0, 0, 1]));   // axes parallèles : ACA crânio-caudal
  const b = V.norm(V.add(u, v));                      // normale du plan bissecteur transverse
  const c = V.len(V.sub(u, v)) > 1e-9 ? V.norm(V.sub(u, v)) : V.norm(V.cross(nACA, b));   // bissectrice transverse
  // section de l'os par le plan bissecteur : largeur le long de c, profondeur le long de l'ACA
  let sec = sectionPoints(main.pos, main.idx, C, b);
  const secOK = sec.length >= 6;
  if (!secOK) sec = sectionPoints(main.pos, main.idx, V.add(axeProx.p, V.mul(u, (yMilieu - axeProx.p[1]) / u[1])), b);
  let sMax = -Infinity, sMin = Infinity, wMin = Infinity, wMax = -Infinity;
  for (const p of sec) {
    const r = V.sub(p, C), s = V.dot(r, c), w = V.dot(r, nACA);
    sMax = Math.max(sMax, s); sMin = Math.min(sMin, s); wMin = Math.min(wMin, w); wMax = Math.max(wMax, w);
  }
  const section = { cvx: sMax, ccv: -sMin, largeur: sMax - sMin, profondeur: wMax - wMin, wMid: (wMin + wMax) / 2 };
  const Cc = V.add(C, V.mul(nACA, section.wMid));     // CORA ramené au milieu de l'os le long de l'ACA (même droite)
  // orientation de la charnière dans le plan transverse : 0° = crânio-caudale (frontal pur), 90° = médio-latérale
  const psi = Math.atan2(Math.abs(nACA[0]), Math.abs(nACA[2])) * DEG;
  // ostéotomie au CORA possible ? (axes non parallèles, CORA dans l'os, section valable)
  const osteoPossible = theta >= THETA_MIN && coraDansOs && secOK && section.cvx > CHARNIERE_RETRAIT && section.ccv > CHARNIERE_RETRAIT;

  // 6) torsion : mesure avant correction, cible et dérotation à ajouter à la correction angulaire.
  //    Référence « os sain » : la torsion de l'os sain (ou de l'os avant la déformité de test). Référence « valeurs
  //    normales » : on ne dérote que si la torsion sort des seuils publiés, jusqu'à la valeur normale moyenne.
  //    La décision se prend sur la torsion APRÈS la seule correction angulaire : une angulation pure incline les axes
  //    transverses (quelques dixièmes de degré de « fausse torsion » avant correction), que la correction annule.
  const TN = TORSION_NORMALE[bone];
  const torPre = mesuresTorsion(bone, L), torSain = mesuresTorsion(bone, ref.L0);
  const statutTorsion = (t) => (t < TN.seuils[0] ? (bone === 'femur' ? 'externe' : 'interne') : t > TN.seuils[1] ? (bone === 'femur' ? 'interne' : 'externe') : 'normale');
  const cibleTorsion = (tApresAngle) => (opts.derotation === false ? tApresAngle
    : refN ? (statutTorsion(tApresAngle) === 'normale' ? tApresAngle : TN.m) : torSain.torsion3D);
  const torsion = { avant: torPre.torsion3D, sain: torSain.torsion3D, publiee: torPre.publiee, axes: torPre.axes, normale: TN, statut: statutTorsion(torPre.torsion3D) };

  // 7) ostéotomies : fermeture et ouverture, dérotation éventuelle, broches de réduction du guide.
  //    Par défaut, règle 1 de Paley : coupe au CORA, charnière sur la bissectrice transverse (corticale concave en
  //    fermeture, convexe en ouverture), à opts.charniere mm de cette corticale (profondeur ; défaut 2 mm). Le niveau de
  //    la coupe peut être déplacé le long de l'os (opts.decalageCoupe, mm, + vers distal) : règle 2, l'ACA reste sur la
  //    bissectrice du CORA (axes réalignés) et le fragment glisse le long de la coupe (translation à l'ostéotomie).
  //    Sans décalage imposé, si un trait passe à moins de MARGE_COUPE_CARTILAGE du cartilage (CORA dans ou contre
  //    l'articulation, par exemple la trochlée du fémur), la coupe remonte vers la diaphyse (pas de 1 mm, au plus 35 % de
  //    la longueur) : règle 2 automatique.
  const k = V.norm(V.cross(v, u));                    // axe de correction : fait tourner v vers u
  const masque = masqueArticulaire(model, bone);
  const nrmOs = normalesSommets(main.pos, main.idx);
  const art = masque ? pointsMasques(pos[bone], masque) : new Float32Array(0);
  const voisinsPos = {};
  for (const n of VOISINS[bone] || []) {
    const b0 = model.bones[n];
    if (!b0) continue;
    if (D) { voisinsPos[n] = new Float32Array(b0.pos.length); deformArray(D, b0.pos, voisinsPos[n]); } else voisinsPos[n] = b0.pos;
  }
  const obstacles = [...noms.filter((n) => n !== bone).map((n) => ({ nom: n, pos: pos[n] })), ...Object.entries(voisinsPos).map(([n, p_]) => ({ nom: n, pos: p_ }))];
  const Lgr = ax.y_top - ax.y_bot;
  const versProx = C[1] < yMilieu;                    // CORA dans la moitié distale : la coupe remonte (règle 2)
  const zImpose = Number.isFinite(opts.decalageCoupe) ? opts.decalageCoupe : null;
  const hDemande = (kind) => { const x = typeof opts.charniere === 'number' ? opts.charniere : opts.charniere?.[kind]; return Number.isFinite(x) ? x : CHARNIERE_RETRAIT; };
  const cfgBroches = CONFIG_BROCHES[opts.broches] ? opts.broches : '2+2';
  // trait de coupe à z mm du CORA le long de l'os : + vers distal (sur l'axe distal), − vers proximal (sur l'axe proximal)
  const pointCoupe = (z) => (z === 0 ? C : z > 0 ? V.add(C, V.mul(v, z)) : V.add(C, V.mul(u, z)));
  const coupeAu = (z, kind) => {
    const P0 = pointCoupe(z);
    const sp = sectionPoints(main.pos, main.idx, P0, b);
    if (sp.length < 6) return null;
    let sMx = -Infinity, sMn = Infinity, wMn = Infinity, wMx = -Infinity;
    for (const q of sp) { const r = V.sub(q, P0), s1 = V.dot(r, c), w = V.dot(r, nACA); sMx = Math.max(sMx, s1); sMn = Math.min(sMn, s1); wMn = Math.min(wMn, w); wMx = Math.max(wMx, w); }
    const sec2 = { cvx: sMx, ccv: -sMn, largeur: sMx - sMn, profondeur: wMx - wMn, wMid: (wMn + wMx) / 2 };
    if (sec2.cvx <= CHARNIERE_RETRAIT || sec2.ccv <= CHARNIERE_RETRAIT) return null;
    const Pc = V.add(P0, V.mul(nACA, sec2.wMid));
    const cote = kind === 'fermeture' ? V.neg(c) : c;              // du centre de la section vers la corticale de la charnière
    const loin = kind === 'fermeture' ? sec2.ccv : sec2.cvx;
    // profondeur de la charnière = distance à la corticale de la charnière, le long de la bissectrice. Fermeture : de
    // 0,3 mm jusqu'au centre de la section (coin neutre) ; ouverture : au plus CHARNIERE_OUVERTURE_MAX (au-delà, la partie
    // convexe derrière la charnière devrait se chevaucher : il faudrait y retirer un coin, hors d'atteinte de cet abord).
    const hMax = kind === 'fermeture' ? loin : Math.max(0.3, Math.min(CHARNIERE_OUVERTURE_MAX, loin - 0.5));
    const h = clamp(hDemande(kind), 0.3, hMax);
    const H = V.add(Pc, V.mul(cote, loin - h));
    const plans = kind === 'fermeture' ? [{ p: H, n: u }, { p: H, n: v }] : [{ p: H, n: b }];
    // distance du cartilage aux traits (dans le disque de la coupe) ; sûr si elle atteint la marge et si le coin de
    // fermeture ne contient pas de cartilage (entre les deux traits : le coin retiré en emporterait)
    let dCart = Infinity, dansCoin = false;
    for (let i = 0; i < art.length; i += 3) {
      const q = [art[i], art[i + 1], art[i + 2]];
      for (const pl of plans) {
        const dq = V.sub(q, pl.p), hq = V.dot(dq, pl.n);
        if (V.len(V.sub(dq, V.mul(pl.n, hq))) < 1.3 * sec2.largeur) dCart = Math.min(dCart, Math.abs(hq));
      }
      if (!dansCoin && plans.length === 2) {
        const dq = V.sub(q, H);
        if (V.dot(dq, plans[0].n) > -MARGE_COUPE_CARTILAGE && V.dot(dq, plans[1].n) < MARGE_COUPE_CARTILAGE && V.len(dq) < 1.5 * sec2.largeur) dansCoin = true;
      }
    }
    return { z, P0, Pc, H, h, hMax, plans, sec2, sur: dCart >= MARGE_COUPE_CARTILAGE && !dansCoin, dCart, dansCoin };
  };
  const osteo = {};
  const alertes = [];
  for (const kind of ['fermeture', 'ouverture']) {
    if (!osteoPossible) { osteo[kind] = null; continue; }
    let cp;
    if (zImpose !== null) {
      cp = coupeAu(zImpose, kind);
      if (!cp) alertes.push(`${kind} : à ${zImpose.toFixed(0)} mm du CORA, le trait sort de l'os ou la bissectrice ne traverse plus la section`);
    } else {
      cp = coupeAu(0, kind);
      if (cp && !cp.sur) {
        let trouve = null;
        for (let s = 1; s <= 0.35 * Lgr && !trouve; s += 1) { const c2 = coupeAu(versProx ? -s : s, kind); if (c2 && c2.sur) trouve = c2; }
        if (trouve) cp = trouve;
        else alertes.push(`${kind} : le trait de coupe reste à moins de ${MARGE_COUPE_CARTILAGE} mm du cartilage`);
      }
    }
    if (!cp) { osteo[kind] = null; continue; }
    const regle = cp.z === 0 ? 1 : 2;
    const { H, plans } = cp, secK = cp.sec2;
    const nDist = plans[plans.length - 1].n;
    const estDistal = (p) => V.dot(V.sub(p, H), nDist) > 0;
    // règle 1 : rotation autour de la charnière, sur la bissectrice transverse du CORA. Règle 2 : l'ACA reste sur cette
    // bissectrice (droite Cc + λ·c : les axes sont réalignés sans translation quel que soit λ), à la seule position qui
    // garde les faces de l'ostéotomie en contact : faces confondues (fermeture), arête de charnière posée sur la face
    // proximale (ouverture). Le fragment distal glisse alors le long de la coupe : c'est la translation de la règle 2.
    let Q = H;
    if (regle === 2) {
      const Rk = RT.aboutAxis([0, 0, 0], k, theta * RAD).R;
      const moinsI = (x) => V.sub(M3.mv(Rk, x), x);                       // (R − I)·x
      const nF = kind === 'fermeture' ? u : b;
      const den = V.dot(moinsI(c), nF);
      Q = V.add(Cc, V.mul(c, Math.abs(den) > 1e-12 ? V.dot(moinsI(V.sub(H, Cc)), nF) / den : 0));
    }
    const Tang = RT.aboutAxis(Q, k, theta * RAD);
    // dérotation, autour d'un axe que la correction garde aligné (aucun angle ni translation résiduels) :
    //   fermeture : autour de l'axe distal, AVANT la fermeture (la face distale, ⊥ à cet axe, tourne dans son plan) ;
    //   ouverture : autour de l'axe réaligné (axe proximal), APRÈS l'ouverture (l'espace d'ouverture est comblé).
    // L'angle est ajusté (méthode de la sécante) pour que la torsion mesurée après correction égale la cible.
    const surAxe = (A_, p) => V.add(A_.p, V.mul(A_.d, V.dot(V.sub(p, A_.p), A_.d)));
    const axeDer = kind === 'fermeture' ? { p: surAxe(axeDist, Cc), d: V.neg(v) } : { p: surAxe(axeProx, Cc), d: V.neg(u) };
    const corrigeAvec = (alpha) => {
      const Rd = RT.aboutAxis(axeDer.p, axeDer.d, alpha * RAD);
      const Ttot = kind === 'fermeture' ? RT.compose(Tang, Rd) : RT.compose(Rd, Tang);
      const Lx = {};
      for (const [key, p] of Object.entries(L)) Lx[key] = estDistal(p) ? RT.apply(Ttot, p) : [...p];
      return { Ttot, Lx, tor: mesuresTorsion(bone, Lx).torsion3D };
    };
    let alpha = 0, sol = corrigeAvec(0);
    const torApresAngle = sol.tor, torCible = cibleTorsion(torApresAngle);
    if (Math.abs(torCible - torApresAngle) > DEROTATION_MIN) {
      let a0 = 0, f0 = sol.tor - torCible, a1 = -f0, s1 = corrigeAvec(a1), f1 = s1.tor - torCible;
      for (let it = 0; it < 6 && Math.abs(f1) > 1e-3 && Math.abs(f1 - f0) > 1e-9; it++) {
        const a2 = a1 - f1 * (a1 - a0) / (f1 - f0);
        a0 = a1; f0 = f1; a1 = a2; s1 = corrigeAvec(a1); f1 = s1.tor - torCible;
      }
      alpha = a1; sol = s1;
    }
    const T = sol.Ttot, Lc = sol.Lx;
    const post = mesurer(bone, Lc, axeProx);
    const vC = M3.mv(T.R, v);
    const Dl = secK.largeur - cp.h;                                          // charnière -> corticale d'entrée de la lame
    // os, cartilage et voisins limités à la région de la coupe (calcul rapide)
    const rayon = 3 * secK.largeur + 60;
    const dansRegion = (pts, i) => Math.abs(pts[i] - H[0]) < rayon && Math.abs(pts[i + 1] - H[1]) < rayon && Math.abs(pts[i + 2] - H[2]) < rayon;
    const proche = (pts, ref = pts) => {                     // (ref : tableau dont la position décide, même indexation)
      const out = [];
      for (let i = 0; i < pts.length; i += 3) if (dansRegion(ref, i)) out.push(pts[i], pts[i + 1], pts[i + 2]);
      return Float32Array.from(out);
    };
    const voisinsProches = obstacles.map((o_) => ({ nom: o_.nom, pts: proche(o_.pos) })).filter((x) => x.pts.length);
    // face du guide = côté d'entrée de la lame, toujours opposé à la charnière : la face du coin (convexe en fermeture,
    // concave en ouverture) si un abord usuel y donne accès et si aucun os voisin n'est sur le trajet de la lame ; sinon la
    // face accessible la plus proche, à moins de ANGLE_ENTREE_COIN_MAX (ostéotomie complète) ; sinon le coin n'est pas
    // réalisable par un abord usuel et le guide reste sur la face du coin (signalé, l'autre type de coin est recommandé)
    const faceCoin = kind === 'fermeture' ? c : V.neg(c);
    const f0Coin = V.norm(V.perp(faceCoin, u));
    const NOMS_OS = { fibula: 'la fibula', patella: 'la rotule', fabellae: 'une fabelle' };
    const sections = plans.map((pl_) => sectionPoints(main.pos, main.idx, pl_.p, V.norm(pl_.n)));
    let bloqueePar = null;
    const lameLibre = (f) => {
      const ts = toursFente(plans, f, main.pos, main.idx, secK.largeur, sections);
      for (const vp of voisinsProches) for (let i = 0; i < vp.pts.length; i += 3) {
        const q = [vp.pts[i], vp.pts[i + 1], vp.pts[i + 2]];
        for (const t of ts) if (distTour(q, t) < 0.5) { if (V.angle(V.norm(V.perp(f, u)), f0Coin) < 1) bloqueePar = NOMS_OS[vp.nom] || vp.nom; return false; }
      }
      return true;
    };
    const ab = choisirAbord(bone, faceCoin, u, lameLibre);
    const face = ab.face;
    const Tinv = RT.inv(T);
    // ligne centrale de chaque fragment (configuration planifiée), à la distance e du trait mesurée le long de l'os :
    // sur l'axe du segment où tombe le point (règle 2 : le fragment qui contient le CORA change d'axe au CORA)
    const pieds = { prox: surAxe(axeProx, H), dist: surAxe(axeDist, H) };           // pied du trait sur chaque axe
    const coraProx = surAxe(axeProx, Cc), coraDist = surAxe(axeDist, Cc);
    const zc = cp.z, sD = Math.abs(zc);
    const centre = (frag, e) => {
      if (frag === 'proximal') {
        if (zc <= 0) return V.sub(pieds.prox, V.mul(u, e));                      // trait au CORA ou dans le segment proximal
        return e <= sD ? V.sub(pieds.dist, V.mul(v, e)) : V.sub(coraProx, V.mul(u, e - sD));
      }
      if (zc >= 0) return V.add(pieds.dist, V.mul(v, e));                        // trait au CORA ou dans le segment distal
      return e <= sD ? V.add(pieds.prox, V.mul(u, e)) : V.add(coraDist, V.mul(v, e - sD));
    };
    const cfgB = CONFIG_BROCHES[cfgBroches];
    const pl = placerBroches({
      u, v, face, Tinv, largeur: secK.largeur, centre, config: cfgB, tours: toursFente(plans, face, main.pos, main.idx, secK.largeur, sections),
      plansProx: [plans[0]], plansDist: [plans[plans.length - 1]], tousPlans: plans,
      ctx: { osPos: proche(main.pos), osNrm: proche(nrmOs, main.pos), art: proche(art), voisins: voisinsProches.map((x) => x.pts), demiLargeur: secK.largeur / 2 },
    });
    const mk = (frag, pt, dir, h) => ({ fragment: frag, point: pt, dir, hauteurManchon: h });
    const brochesReduction = [
      ...pl.pp.pts.map((pt) => mk('proximal', pt, pl.pp.dir, 15)),
      ...pl.pd.pts.map((pt) => mk('distal', pt, pl.pd.dir, pl.pd.hauteurManchon)),
    ];
    // une broche par fragment (format v2.1 de la prescription : P1, D1)
    const broches = ['proximal', 'distal'].map((fr_) => brochesReduction.find((x) => x.fragment === fr_)).filter(Boolean);
    const brochesApres = brochesReduction.map((bb) => (bb.fragment === 'distal' ? { ...bb, point: RT.apply(T, bb.point), dir: M3.mv(T.R, bb.dir) } : { ...bb }));
    const alertesK = [];
    for (const [frag, pr_] of [['proximal', pl.pp], ['distal', pl.pd]]) {
      pr_.ev.forEach((ev, i) => { if (!ev.ok) alertesK.push(`broche ${frag === 'proximal' ? 'P' : 'D'}${i + 1} : ${ev.raison}`); });
      if (!pr_.pts.length) alertesK.push(`fragment ${frag} : aucune position de broche possible`);
    }
    if (Math.abs(pl.beta) > 0) alertesK.push(`broches tournées de ${pl.beta}° autour de l'os (cartilage ou os voisin évités)`);
    if (pl.gamma) alertesK.push(`broches inclinées de ${Math.abs(pl.gamma)}° le long de l'os (vers ${pl.gamma > 0 ? 'distal' : 'proximal'}) pour que le guide de coupe se retire en deux moitiés`);
    if (pl.retrait === false) alertesK.push('orientation des broches imposée par le cartilage ou les os voisins : les deux moitiés du guide de coupe ne peuvent pas sortir l\'une sans heurter l\'autre');
    if (pl.pd.ok && pl.pd.hauteurManchon < 15) alertesK.push(`manchons distaux raccourcis à ${pl.pd.hauteurManchon} mm (broches très inclinées : guidage moins précis)`);
    for (const [nomF, pr_] of [['proximal', pl.pp], ['distal', pl.pd]]) {
      const impose = (nomF === 'proximal' ? cfgB.dispProx : cfgB.dispDist) === 'transversale';
      if (pr_.ok && pr_.disposition === 'transversale' && !impose) alertesK.push(`fragment ${nomF} court : ses 2 broches sont côte à côte (écart ${pr_.ecart} mm)`);
      if (pr_.ok && pr_.decalage) alertesK.push(`broches du fragment ${nomF} décalées de ${Math.abs(pr_.decalage)} mm de la ligne centrale de l'os (cartilage ou os voisin évités)`);
    }
    const charniereConservee = ab.charniere && regle === 1 && Math.abs(alpha) < DEROTATION_MIN && cp.h <= PONT_MAX + 1e-9;
    const coinMixte = kind === 'fermeture' && cp.h > PONT_MAX + 1e-9;
    const pourquoi = ab.charniere && !ab.nonUsuel ? null : bloqueePar ? `${bloqueePar} est sur le trajet de la lame` : 'hors des abords chirurgicaux usuels';
    if (ab.nonUsuel) {
      // os voisin sur le trajet de la lame : un guide sur cette face occuperait l'espace entre l'os et ce voisin (on ne
      // pourrait ni l'y glisser, ni le fixer, ni couper) : pas de guide de coupe (étape 7 : GuideImpossible)
      alertesK.push(`coin non réalisable par un abord usuel : la lame doit entrer par la face ${nomDirection(faceCoin)} (${pourquoi}) ; ${ab.voisinSurLame && bloqueePar ? `pas de guide de coupe : il occuperait l'espace entre l'os et ${bloqueePar}` : 'guide posé sur cette face (abord non usuel)'}${ab.abordProche ? ` ; l'abord ${ab.abordProche.abord} n'y entre qu'à ${Math.round(ab.abordProche.ecart)}° de la face du coin, du côté de la charnière` : ''}`);
    } else if (!ab.charniere) {
      alertesK.push(`face du coin ${nomDirection(faceCoin)} (${pourquoi}) : guide posé par l'abord ${ab.abord}, face ${nomDirection(face)} à ${Math.round(ab.ecart)}° de la face du coin, ostéotomie complète (charnière non conservée)`);
    }
    if (coinMixte) alertesK.push(`charnière à ${cp.h.toFixed(1)} mm de la corticale concave (> ${PONT_MAX} mm) : coin mixte, ostéotomie complète ; le côté concave s'ouvre de ${(2 * cp.h * Math.sin(theta * RAD / 2)).toFixed(1)} mm`);
    else if (cp.h > PONT_MAX + 1e-9) alertesK.push(`charnière à ${cp.h.toFixed(1)} mm de la corticale : pont d'os épais, il risque de casser`);
    // profondeur de coupe par fente : jusqu'à la charnière, ou complète (corticale opposée). Fermeture avec ostéotomie
    // complète et lame par la face du coin : la 1re fente traverse l'os, la 2e s'arrête à la charnière (sinon un éclat
    // d'os se détacherait entre les deux traits, côté concave)
    plans.forEach((pl_, i) => { pl_.profondeur = charniereConservee ? 'charniere' : (kind === 'fermeture' && i === 1 && ab.ecart === 0 && !ab.nonUsuel) ? 'charniere' : 'complete'; });
    const largeurFente = INSTRUMENT.lame + INSTRUMENT.jeuFente;
    if (kind === 'fermeture' && 2 * Dl * Math.tan(theta * RAD / 2) - largeurFente < 1.5) {
      alertesK.push(`coin de fermeture trop fin (base ≈ ${(2 * Dl * Math.tan(theta * RAD / 2)).toFixed(1)} mm) : les deux fentes du guide se touchent presque ; préférer le coin d'ouverture`);
    }
    const trans = V.dist(RT.apply(Tang, H), H);
    if (regle === 2) alertesK.push(`règle 2 de Paley : coupe à ${Math.abs(cp.z).toFixed(0)} mm ${cp.z < 0 ? 'au-dessus' : 'au-dessous'} du CORA${zImpose === null ? ' (hors du cartilage)' : ' (niveau choisi)'}, translation de ${trans.toFixed(1)} mm à l'ostéotomie`);
    if (trans > 0.5 * secK.largeur) alertesK.push(`translation à l'ostéotomie de ${trans.toFixed(1)} mm (${Math.round(100 * trans / secK.largeur)} % de la largeur de l'os) : contact osseux insuffisant`);
    if (zImpose !== null && !cp.sur) alertesK.push(`trait de coupe à ${Number.isFinite(cp.dCart) ? cp.dCart.toFixed(1) : '?'} mm du cartilage (minimum ${MARGE_COUPE_CARTILAGE} mm)${cp.dansCoin ? ' ; le coin retiré emporterait du cartilage' : ''}`);
    const contraintes = contraintesCoupe({ bone, L, ax, kind, cp, regle, translation: trans, largeur: secK.largeur, croissance: !!opts.croissance, abord: ab.abord, nonUsuel: ab.nonUsuel });
    osteo[kind] = {
      kind, regle, decalageCoupe: Math.abs(cp.z), z: cp.z, translationOsteo: trans, aca: Q, centreCoupe: cp.Pc,
      abord: ab.abord, charniereConservee, faceCoin, raisonAbord: pourquoi,
      faisable: ab.faisable, abordNonUsuel: !!ab.nonUsuel, ecartFace: ab.ecart, voisinSurLame: bloqueePar,
      angleFaceCharniere: V.angle(V.norm(V.perp(face, u)), V.norm(V.perp(V.neg(faceCoin), u))),
      h: cp.h, hMax: cp.hMax, coinMixte, ouvertureCharniere: !charniereConservee && kind === 'fermeture' ? 2 * cp.h * Math.sin(theta * RAD / 2) : 0,
      dCart: cp.dCart, contraintes, configBroches: cfgBroches,
      charniere: H, plans, T, Tang, k, corr: theta, face, broches, brochesReduction, brochesApres,
      placementBroches: { beta: pl.beta, eProx: pl.pp.e, eDist: pl.pd.e, ecartProx: pl.pp.ecart, ecartDist: pl.pd.ecart,
        dispositionProx: pl.pp.disposition, dispositionDist: pl.pd.disposition, decalageProx: pl.pp.decalage, decalageDist: pl.pd.decalage,
        retraitLibre: pl.retrait !== false, gamma: pl.gamma || 0, nProx: pl.pp.pts.length, nDist: pl.pd.pts.length,
        ok: !!(pl.pp.ok && pl.pd.ok) },
      alertes: alertesK, sectionCoupe: secK,
      derotation: alpha, axeDerotation: axeDer, torsionApres: mesuresTorsion(bone, Lc).torsion3D, torsionApresAngle: torApresAngle, torsionCible: torCible,
      angleBroches: V.angle(broches[0].dir, broches[broches.length - 1].dir),
      d: V.dot(V.sub(H, C), c),                                          // charnière -> CORA, + vers le convexe
      D: Dl,
      base: kind === 'fermeture' ? 2 * Dl * Math.tan(theta * RAD / 2) : 2 * Dl * Math.sin(theta * RAD / 2),
      angleCoupes: plans.length === 2 ? V.angle(plans[0].n, plans[1].n) : 0,
      inclinaisonCoupes: plans.map((pl_) => V.angle(pl_.n, u)),            // par rapport à la perpendiculaire à l'axe proximal
      post, Lc,
      residuel: V.angle(u, vC),                                           // angle restant entre les axes
      decalage: V.distLine(RT.apply(T, axeDist.p), axeProx.p, u),         // translation restante (mm)
      dLongueur: post.longueur - normal.longueur,                         // + allongement, − raccourcissement (/ référence)
      deltaOperation: post.longueur - pre.longueur,                       // changement de longueur dû à l'ostéotomie
      distanceApex: D && D.A ? V.dot(V.sub(H, D.A), c) : null,
    };
  }
  const recommandation = recommanderCoin(osteo, opts);

  // 7) validation : comparaison à la vérité terrain (seulement si une déformité connue a été imposée). F et S « vrais »
  // = angles projetés entre l'axe sain et ce même axe tourné par la déformité (si l'axe n'est pas exactement vertical,
  // ils diffèrent un peu des valeurs nominales imposées : c'est un effet de projection, pas une erreur de la méthode).
  let validation = {
    thetaMesure: theta, FMesure: Math.abs(Fm), SMesure: Math.abs(Sm), typeF, typeS, theta2D, phi,
    delta: cc.delta, niveauCORA: ax.y_top - (coraVrai || C)[1], longueurOs: ax.y_top - ax.y_bot, niveauF: proj.F.niveau, niveauS: proj.S.niveau,
  };
  if (D) {
    const dSain = ref.axeSain.d, dTourne = M3.mv(D.T.R, dSain);
    validation = {
      ...validation, FProjVrai: angleProjete('F', dSain, dTourne), SProjVrai: angleProjete('S', dSain, dTourne),
      thetaAxesVrai: V.angle(dSain, dTourne), thetaVrai: D.theta * DEG, FVrai: thetaF, SVrai: D.S, typeVraiF: frontal,
      typeVraiS: sagittal, phiVrai: D.phi, ecartTheta: theta - D.theta * DEG, tauVrai: D.tau,
      apexBissectrice: Math.abs(V.dot(V.sub(D.A, C), b)),                 // distance de l'apex au plan bissecteur
      apexCORA: V.dist(D.A, C), niveauApex: ax.y_top - D.yA,
    };
  }

  return {
    bone, cas, frontal, sagittal, thetaF, thetaS, niveau, ref, D, pos, L, main, section, meshes: noms,
    reel: model.reel || null, reference: refN ? 'normales' : 'sain', sdRef, anomalies, torsion, tauTest,
    jol, centres, axeProx, axeDist, milieux, proj,
    mesures: { pre, normal, litt: LITTERATURE[bone] },
    cora: C, coraC: Cc, cc, coraDansOs, theta, Fm, Sm, typeF, typeS, theta2D, phi, psi,
    bis: { b, c, ccv: V.neg(c), n: nACA },
    osteo, osteoPossible, validation, recommandation,
    optionsStrategie: { decalageCoupe: zImpose, charniere: opts.charniere ?? null, broches: cfgBroches, croissance: !!opts.croissance, inegaliteLongueur: opts.inegaliteLongueur ?? null },
    voisins: voisinsPos, articulaire: masque, alertesPlanif: alertes,
  };
}

// --------------------------------------------- prescription pour le guide de coupe --
// Même format que la v2 (Planificateur_CORA_3Dv2, schema v2.1) : le script etape4_guide.py de la v2 peut
// construire le guide imprimable à partir de ce fichier et du STL de l'os (déformé ou segmenté).
// Coordonnées : repère du maillage exporté (X latéral, Y proximal, Z caudal ; un membre gauche y est mis en miroir
// pour être traité comme un droit), en mm. Os segmenté : « repere_scanner » donne la matrice pour revenir aux
// coordonnées du scanner. Signes v2 : frontal + = varus, sagittal + = procurvatum.
export const nomFichierOs = (P) => (P.reel ? `${P.bone}_${P.D ? 'deforme_test' : 'segmente'}.stl` : `${P.bone}_deforme.stl`);
// Os segmenté : série, côté, miroir et matrice os -> scanner (inverse de scanner_vers_os) : p_scanner = M · [p_os, 1]
function blocOsSegmente(R) {
  const r = (x, d = 4) => +x.toFixed(d);
  const M = R.repere.scanner_vers_os, A = [M[0].slice(0, 3), M[1].slice(0, 3), M[2].slice(0, 3)], t = [M[0][3], M[1][3], M[2][3]];
  const det = A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1]) - A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0]) + A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0]);
  const At = [[A[0][0], A[1][0], A[2][0]], [A[0][1], A[1][1], A[2][1]], [A[0][2], A[1][2], A[2][2]]];   // orthogonale : inverse = transposée
  const ti = At.map((row) => -(row[0] * t[0] + row[1] * t[1] + row[2] * t[2]));
  return {
    serie: R.serie, fichier_stl_scanner: R.fichier_stl, systeme_scanner: R.systeme, cote_anatomique: R.cote,
    miroir: !!R.miroir, reperes_detectes: 'etape6_reperes.py (repères automatiques)',
    repere_scanner: { os_vers_scanner: [...At.map((row, i) => [...row.map((x) => r(x, 6)), r(ti[i], 4)]), [0, 0, 0, 1]], determinant: r(det, 3) },
  };
}
// extra.parametresGuide : dimensions du guide générique choisies dans l'interface (etape7_guide.py les lit dans
// « parametres_guide » ; une dimension absente garde sa valeur par défaut de parametres.py).
export function prescription(P, kind, extra = {}) {
  const O = P.osteo[kind];
  if (!O) throw new Error('pas d\'ostéotomie au CORA possible pour ce cas');
  const r = (x, d = 4) => +x.toFixed(d);
  const p3 = (p) => p.map((x) => r(x));
  const R = P.reel;
  const out = {
    schema_version: 'v2.2',
    generateur: R ? 'CT-CORA3D (PMD2, ECAM), os segmenté sur CT' + (P.D ? ', déformité de test simulée' : '') : 'CORA 3D (PMD2, ECAM), modèle synthétique',
    os: P.bone, cote: 'droit', unites: 'mm',
    fichier_maillage: nomFichierOs(P),
    repere: R && R.miroir ? 'X latéral, Y proximal, Z caudal (repère du maillage ; membre gauche mis en miroir)' : 'X latéral, Y proximal, Z caudal (repère du maillage)',
    deformite: {
      theta_deg: r(P.theta), frontal_deg: r(-P.Fm), sagittal_deg: r(P.Sm), phi_deg: r(P.phi),
      torsion_mesuree_deg: R && R.torsion_deg != null ? r(R.torsion_deg, 2) : 0, ecart_axes_mm: r(P.cc.delta), cora: p3(P.cora),
    },
    reference: P.reference === 'normales' ? { type: 'valeurs normales (méthode de Paley)', valeurs: Object.fromEntries(Object.entries(P.mesures.normal).filter(([k]) => k !== 'longueur').map(([k, x]) => [k, r(x, 2)])) }
      : { type: R ? 'os avant la déformité de test (membre controlatéral idéal)' : 'os sain du modèle (membre controlatéral)' },
    strategie: { type_coin: kind, regle_paley: O.regle, torsion: Math.abs(O.derotation) >= DEROTATION_MIN ? `corrigée : dérotation de ${r(O.derotation, 1)}°` : 'non corrigée',
      decalage_coupe_mm: O.decalageCoupe, decalage_coupe_signe_mm: r(O.z ?? 0, 2), translation_osteotomie_mm: r(O.translationOsteo, 2),
      abord: O.abord, face_du_coin: p3(O.faceCoin || O.face),
      abord_non_usuel: !!O.abordNonUsuel, faisable_abord_usuel: O.faisable !== false, ecart_face_coin_deg: r(O.ecartFace || 0, 1),
      // os voisin sur le trajet de la lame par la face du coin (« la fibula »…) : l'étape 7 ne construit alors pas de guide
      voisin_sur_lame: O.abordNonUsuel ? (O.voisinSurLame || null) : null,
      charniere_profondeur_mm: r(O.h ?? CHARNIERE_RETRAIT, 2), coin_mixte: !!O.coinMixte,
      configuration_broches: O.configBroches || '2+2',
      recommandation: P.recommandation ? { type_coin: P.recommandation.kind, critere_decisif: P.recommandation.decisif } : null,
      osteotomie_complete: O.charniereConservee === undefined ? O.regle === 2 || Math.abs(O.derotation) >= DEROTATION_MIN : !O.charniereConservee },
    charniere: { point: p3(O.charniere), direction: p3(P.bis.n), d_mm: r(O.d), marge_mm: r(O.h ?? CHARNIERE_RETRAIT, 2),
      axe_correction_point: p3(O.aca || O.charniere) },                  // règle 2 : ACA sur la bissectrice du CORA
    // profondeur de chaque fente : 'charniere' (la lame s'arrête à la charnière) ou 'complete' (jusqu'à la corticale opposée)
    plans_coupe: O.plans.map((pl) => ({ point: p3(pl.p), normale: p3(V.norm(pl.n)), profondeur: pl.profondeur || (O.charniereConservee ? 'charniere' : 'complete') })),
    coin: {
      angle_deg: r(P.theta), largeur_base_mm: r(O.base), profondeur_coupe_mm: r(O.D), delta_L_mm: r(O.dLongueur),
      r_convexe_mm: r(P.section.cvx), r_concave_mm: r(P.section.ccv), angle_entre_coupes_deg: r(O.angleCoupes),
      orientation_charniere_deg: r(P.psi),
    },
    correction: { axe: p3(O.k), angle_deg: r(P.theta), point: p3(O.charniere), derotation_deg: r(O.derotation, 2),
      axe_derotation: { point: p3(O.axeDerotation.p), direction: p3(O.axeDerotation.d) },
      T_4x4: RT.toRows4(O.T).map((l) => l.map((x) => r(x, 6))), T_angulaire_4x4: RT.toRows4(O.Tang).map((l) => l.map((x) => r(x, 6))) },
    broches: O.broches.map((bb) => ({ fragment: bb.fragment, point_axe: p3(bb.point), direction: p3(V.norm(bb.dir)), diametre_mm: INSTRUMENT.broche })),
    angle_entre_broches_deg: r(O.angleBroches),
    // système de réduction (CT-CORA3D) : 4 broches (2 par fragment) forées à travers le guide de coupe ; après la
    // correction planifiée, elles sont toutes parallèles et le guide de réduction s'enfile dessus (6 degrés de liberté)
    broches_reduction: O.brochesReduction.map((bb) => ({ fragment: bb.fragment, point_axe: p3(bb.point), direction: p3(V.norm(bb.dir)), diametre_mm: INSTRUMENT.broche,
      hauteur_manchon_mm: bb.hauteurManchon || 15 })),
    placement_broches: { rotation_deg: O.placementBroches.beta, inclinaison_deg: O.placementBroches.gamma || 0, distance_coupe_mm: [r(O.placementBroches.eProx, 1), r(O.placementBroches.eDist, 1)],
      disposition: [O.placementBroches.dispositionProx, O.placementBroches.dispositionDist], ecart_mm: [O.placementBroches.ecartProx, O.placementBroches.ecartDist],
      contraintes_respectees: O.placementBroches.ok },
    guide_reduction: { broches_apres_correction: O.brochesApres.map((bb) => ({ fragment: bb.fragment, point_axe: p3(bb.point), direction: p3(V.norm(bb.dir)) })) },
    torsion: {
      definition: P.torsion.publiee ? 'publiée (Al Aiyan 2021 / Brühschwein 2023)' : 'CORA 3D (modèle synthétique)',
      avant_deg: r(P.torsion.avant, 2), apres_correction_angulaire_deg: r(O.torsionApresAngle, 2), cible_deg: r(O.torsionCible, 2),
      apres_deg: r(O.torsionApres, 2), derotation_deg: r(O.derotation, 2), normale: { moyenne_deg: P.torsion.normale.m, seuils_deg: P.torsion.normale.seuils, source: P.torsion.normale.src },
      convention: P.bone === 'femur' ? 'antéversion : + = col vers crânial' : '− = interne, + = externe (Longo 2022)',
    },
    guide: { face_appui: p3(O.face), axe_os: p3(P.axeProx.d), axe_distal: p3(P.axeDist.d), centre_section: p3(O.centreCoupe || P.coraC) },
    contraintes_coupe: (O.contraintes || []).map((x) => ({ niveau: x.niveau, id: x.id, texte: x.texte })),
    prevision: { angle_residuel_deg: r(O.residuel, 6), translation_residuelle_mm: r(O.decalage, 6) },
    alertes: [...(P.anomalies.length ? [] : (R && !P.D ? ['angles articulaires dans les normes : correction non indiquée (démonstration de la méthode)'] : [])), ...(O.alertes || []), ...(P.alertesPlanif || [])],
  };
  if (R) out.os_segmente = blocOsSegmente(R);
  if (P.D) {
    out.verite_terrain = {
      synthetique: !R, apex: p3(P.D.A), theta_deg: r(P.D.theta * DEG), torsion_deg: P.D.tau || 0,
      frontal_deg: (P.frontal === 'varus' ? 1 : -1) * P.thetaF, sagittal_deg: P.D.sS * P.D.S,
    };
  }
  if (extra.parametresGuide && Object.keys(extra.parametresGuide).length) out.parametres_guide = { ...extra.parametresGuide };
  return out;
}

// ------------------------------------------------------------ la torsion --
// « Laboratoire » : on tord l'os SAIN de τ autour de son axe long (segment distal tourné, transition
// progressive au milieu de la diaphyse), puis on pose tout l'os de travers de ρ sur la table (rotation de
// positionnement). On compare ce que voit une radiographie crânio-caudale (projection sur X, Y) et ce que
// mesure le scanner (angle entre deux axes transverses, en 3D).
// Convention (membre droit) : τ > 0 = torsion EXTERNE du segment distal (sa face crâniale tourne vers latéral),
// c'est-à-dire une rotation négative autour de +Y.
export const TORSION = { niveau: 0.5, largeur: 40, plage: [-45, 45] };
export function makeTorsion(ax, tau, rho = 0) {
  const yA = ax.y_top - TORSION.niveau * (ax.y_top - ax.y_bot);
  const A = ax.centerAt(yA);
  return { A, yA, w: TORSION.largeur, tau, rho, Tr: RT.aboutAxis(A, [0, 1, 0], -rho * RAD) };
}
export function torsionPoint(Tz, p) {
  const b = smoothstep(Tz.yA + Tz.w / 2, Tz.yA - Tz.w / 2, p[1]);
  const q = b > 0 ? RT.apply(RT.aboutAxis(Tz.A, [0, 1, 0], -Tz.tau * b * RAD), p) : [...p];
  return RT.apply(Tz.Tr, q);
}
export function torsionArray(Tz, src, dst) {
  for (let i = 0; i < src.length; i += 3) {
    const q = torsionPoint(Tz, [src[i], src[i + 1], src[i + 2]]);
    dst[i] = q[0]; dst[i + 1] = q[1]; dst[i + 2] = q[2];
  }
}
// Axes transverses utilisés pour mesurer la torsion (paires de repères, de médial à latéral).
// CORA 3D (modèle synthétique) : axe du col au ras de la tête, axe bimalléolaire.
export const AXES_TORSION = {
  femur: { prox: ['head_center', 'neck_base'], dist: ['cond_med_caud', 'cond_lat_caud'], nomProx: 'axe du col fémoral', nomDist: 'axe condylaire caudal' },
  tibia: { prox: ['caud_med', 'caud_lat'], dist: ['mall_med', 'mall_lat'], nomProx: 'axe condylaire caudal du tibia', nomDist: 'axe bimalléolaire' },
};
// Définitions publiées (scanner), utilisées dès que les repères existent (os segmenté) :
//   fémur : Al Aiyan 2021 — axe de la diaphyse, axe du col = centre de la tête → base du col au niveau du petit
//           trochanter, ligne condylaire caudale ; + = antéversion (col dirigé vers crânial) ;
//   tibia : Brühschwein 2023 — axe long par les centres de la diaphyse, ligne condylaire caudale et axe antécochléaire ;
//           − = interne, + = externe (Méthodes de Longo 2022 ; le résumé de cet article inverse les deux mots).
export const AXES_TORSION_PUBLIES = {
  femur: { prox: ['head_center', 'neck_base_lt'], dist: ['cond_med_caud', 'cond_lat_caud'], long: ['fem_axe_13', 'fem_axe_12'], nomProx: 'axe du col (base au petit trochanter)', nomDist: 'ligne condylaire caudale' },
  tibia: { prox: ['caud_med', 'caud_lat'], dist: ['ant_med', 'ant_lat'], long: ['tib_shaft_prox', 'tib_shaft_dist'], nomProx: 'ligne condylaire caudale', nomDist: 'axe antécochléaire' },
};
export const TORSION_NORMALE = {
  femur: { m: 31, sd: 5, seuils: [20, 35], nom: 'antéversion fémorale', src: 'Al Aiyan et al. 2021 (CT) ; seuils de Longo et al. 2022' },
  tibia: { m: -4, sd: null, seuils: [-10, 2], nom: 'torsion tibiale', src: 'Brühschwein et al. 2023 (3D-CT) ; seuils de Longo et al. 2022 (Méthodes)' },
};
export const axesTorsion = (bone, L) => (AXES_TORSION_PUBLIES[bone][bone === 'femur' ? 'prox' : 'dist'].every((k) => L[k]) && AXES_TORSION_PUBLIES[bone].long.every((k) => L[k])
  ? { ...AXES_TORSION_PUBLIES[bone], publiee: true } : { ...AXES_TORSION[bone], publiee: false });
// angle signé (°) de a vers b autour de l'axe (règle de la main droite), après projection sur le plan ⊥ axe
const angleAutour = (a, b, axe) => { const pa = V.perp(a, axe), pb = V.perp(b, axe); return Math.atan2(V.dot(V.cross(pa, pb), axe), V.dot(pa, pb)) * DEG; };
// Mesures sur un os (repères L) : torsion 3D (scanner) et grandeurs lues sur la radiographie crânio-caudale.
export function mesuresTorsion(bone, L) {
  const A = axesTorsion(bone, L);
  const long = A.long
    ? V.norm(V.sub(L[A.long[0]], L[A.long[1]]))
    : bone === 'femur' ? V.norm(V.sub(L.head_center, V.mid(L.cond_med_dist, L.cond_lat_dist))) : V.norm(V.sub(L.eminence, L.distal_center));
  const tp = V.perp(V.sub(L[A.prox[1]], L[A.prox[0]]), long), td = V.perp(V.sub(L[A.dist[1]], L[A.dist[0]]), long);
  // fémur : angle d'antéversion (≈ +31° sain ; < 20° = torsion externe) ; tibia : − interne, + externe (Longo 2022)
  const torsion3D = bone === 'femur' ? angleAutour(tp, td, long) : -angleAutour(tp, td, long);
  const lx = (a, b) => Math.abs(L[b][0] - L[a][0]);
  const radio = bone === 'femur'
    ? { condyles: lx('cond_med_dist', 'cond_lat_dist'), epicondyles: lx('epi_med', 'epi_lat'), col: P2.dist(VUE.F.to2(L.head_center), VUE.F.to2(L.neck_base)) }
    : { condyles: lx('caud_med', 'caud_lat'), epicondyles: lx('mall_med', 'mall_lat'), col: lx('plat_med', 'plat_lat') };
  // orientation de chaque axe transverse par rapport au détecteur (0° = parallèle au film), autour de Y
  const orient = (t) => Math.atan2(-t[2], t[0]) * DEG;
  return { torsion3D, radio, orientProx: orient(tp), orientDist: orient(td), publiee: A.publiee, axes: A };
}
export function planTorsion(model, bone, tau, rho = 0) {
  const ref = reference(model, bone);
  const Tz = makeTorsion(ref.ax, tau, rho);
  const L = {};
  for (const [k, v] of Object.entries(ref.L0)) L[k] = torsionPoint(Tz, v);
  const m = mesuresTorsion(bone, L), m0 = mesuresTorsion(bone, ref.L0);
  // largeur épicondylienne (ou bimalléolaire) projetée en fonction de la rotation de l'extrémité distale
  const courbe = [];
  for (let a = TORSION.plage[0]; a <= TORSION.plage[1]; a += 1) {
    const Ta = makeTorsion(ref.ax, 0, a);
    const La = {};
    for (const key of ['epi_med', 'epi_lat', 'cond_med_dist', 'cond_lat_dist', 'mall_med', 'mall_lat', 'caud_med', 'caud_lat']) if (ref.L0[key]) La[key] = torsionPoint(Ta, ref.L0[key]);
    const lx = (p, q) => Math.abs(La[q][0] - La[p][0]);
    courbe.push({ a, largeur: bone === 'femur' ? lx('epi_med', 'epi_lat') : lx('mall_med', 'mall_lat') });
  }
  return { bone, tau, rho, Tz, L, m, m0, courbe, dTorsion: m.torsion3D - m0.torsion3D };
}

// ---------------------------------------------------- découpe de maillages ----
// (reprise de la v1) Maillage : { pos, nrm, attr: {…}, tri, tag } ; tag 0 = surface, k > 0 = face de coupe.
export function meshFromArrays(pos, idx, nrm, attrs) {
  return {
    pos: Array.from(pos), nrm: nrm ? Array.from(nrm) : null,
    attr: Object.fromEntries(Object.entries(attrs || {}).map(([k, a]) => [k, Array.from(a)])),
    tri: Array.from(idx), tag: new Array(idx.length / 3).fill(0),
  };
}

// Coupe par le plan (p0, n), conserve le côté sign·(x−p0)·n ≥ 0 et bouche la coupe (tag = capTag).
// Un sommet d'intersection par arête, partagé par les triangles voisins => fragment étanche.
// triangulate(contour2D, trous2D) -> [[i, j, k], …] (ex. THREE.ShapeUtils.triangulateShape)
export function clipMesh(M, p0, n, sign, capTag, triangulate) {
  n = V.norm(n);
  const nv = M.pos.length / 3;
  const d = new Float64Array(nv);
  for (let i = 0; i < nv; i++) d[i] = sign * ((M.pos[3 * i] - p0[0]) * n[0] + (M.pos[3 * i + 1] - p0[1]) * n[1] + (M.pos[3 * i + 2] - p0[2]) * n[2]);
  const out = {
    pos: M.pos.slice(), nrm: M.nrm ? M.nrm.slice() : null,
    attr: Object.fromEntries(Object.entries(M.attr).map(([k, a]) => [k, a.slice()])), tri: [], tag: [],
  };
  const edgeMap = new Map();
  const segs = [];
  const inside = (i) => d[i] >= 0;
  const cut = (i, j) => {
    const key = i < j ? i * 4194304 + j : j * 4194304 + i;
    let k = edgeMap.get(key);
    if (k !== undefined) return k;
    const t = d[i] / (d[i] - d[j]);
    k = out.pos.length / 3;
    for (let c = 0; c < 3; c++) out.pos.push(M.pos[3 * i + c] + (M.pos[3 * j + c] - M.pos[3 * i + c]) * t);
    if (out.nrm) for (let c = 0; c < 3; c++) out.nrm.push(M.nrm[3 * i + c] + (M.nrm[3 * j + c] - M.nrm[3 * i + c]) * t);
    for (const a in out.attr) out.attr[a].push(M.attr[a][i] + (M.attr[a][j] - M.attr[a][i]) * t);
    edgeMap.set(key, k);
    return k;
  };
  const T = M.tri;
  for (let f = 0; f < T.length; f += 3) {
    const a = T[f], b = T[f + 1], c = T[f + 2], tg = M.tag[f / 3];
    const ia = inside(a), ib = inside(b), ic = inside(c);
    const cnt = ia + ib + ic;
    if (cnt === 3) { out.tri.push(a, b, c); out.tag.push(tg); continue; }
    if (cnt === 0) continue;
    let A = a, B = b, C = c;
    const lone = cnt === 1 ? (ia ? 0 : ib ? 1 : 2) : (!ia ? 0 : !ib ? 1 : 2);
    if (lone === 1) [A, B, C] = [b, c, a];
    else if (lone === 2) [A, B, C] = [c, a, b];
    const pAB = cut(A, B), pCA = cut(C, A);
    if (cnt === 1) { out.tri.push(A, pAB, pCA); out.tag.push(tg); segs.push([pAB, pCA]); }
    else { out.tri.push(pAB, B, C, pAB, C, pCA); out.tag.push(tg, tg); segs.push([pCA, pAB]); }
  }
  // bouchage : chaîner les segments en contours fermés, puis trianguler chaque contour (avec ses trous)
  const next = new Map();
  for (const [s, e] of segs) next.set(s, e);
  const visited = new Set();
  const loops = [];
  for (const [s] of segs) {
    if (visited.has(s)) continue;
    const loop = [];
    let cur = s, guard = 0;
    while (cur !== undefined && !visited.has(cur) && guard++ < 1e6) { visited.add(cur); loop.push(cur); cur = next.get(cur); }
    if (cur === s && loop.length >= 3) loops.push(loop);
  }
  const b1 = V.norm(Math.abs(n[0]) < 0.9 ? V.cross(n, [1, 0, 0]) : V.cross(n, [0, 1, 0]));
  const b2 = V.cross(n, b1);
  const P = (k) => [out.pos[3 * k], out.pos[3 * k + 1], out.pos[3 * k + 2]];
  const to2 = (k) => { const r = V.sub(P(k), p0); return [V.dot(r, b1), V.dot(r, b2)]; };
  const L2 = loops.map((lp) => lp.map(to2));
  const inPoly = (pt, pl) => {
    let ins = false;
    for (let i = 0, j = pl.length - 1; i < pl.length; j = i++) {
      const [xi, yi] = pl[i], [xj, yj] = pl[j];
      if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi) ins = !ins;
    }
    return ins;
  };
  const depth = L2.map((pl, i) => L2.reduce((acc, ql, j) => acc + (j !== i && inPoly(pl[0], ql) ? 1 : 0), 0));
  const capNormal = V.mul(n, -sign);
  for (let i = 0; i < loops.length; i++) {
    if (depth[i] % 2 === 1) continue;
    const holes = [];
    for (let j = 0; j < loops.length; j++) if (depth[j] % 2 === 1 && depth[j] === depth[i] + 1 && inPoly(L2[j][0], L2[i])) holes.push(j);
    let faces;
    try { faces = triangulate(L2[i], holes.map((j) => L2[j])); } catch (e) { faces = []; }
    const map = [...loops[i], ...holes.flatMap((j) => loops[j])];
    for (const [x, y, z] of faces) {
      const ia = map[x], ib = map[y], ic = map[z];
      const nf = V.cross(V.sub(P(ib), P(ia)), V.sub(P(ic), P(ia)));
      if (V.dot(nf, capNormal) >= 0) out.tri.push(ia, ib, ic); else out.tri.push(ia, ic, ib);
      out.tag.push(capTag + (holes.length ? 100 : 0));     // ≥ 100 : section avec canal médullaire (os compact)
    }
  }
  out.loops = loops.filter((_, i) => depth[i] % 2 === 0).map((lp) => lp.map(P));   // contours extérieurs (3D)
  return out;
}

// ------------------------------------------------------------- STL binaire --
// parts : [{ pos: Float32Array|number[], idx: Uint32Array|number[] }] -> Uint8Array (STL binaire, mm)
export function stlBinary(parts, name = 'cora3d') {
  let nTri = 0;
  for (const p of parts) nTri += p.idx.length / 3;
  const buf = new ArrayBuffer(84 + 50 * nTri);
  const dv = new DataView(buf);
  for (let i = 0; i < Math.min(79, name.length); i++) dv.setUint8(i, name.charCodeAt(i) & 0x7f);
  dv.setUint32(80, nTri, true);
  let o = 84;
  for (const p of parts) {
    const P = (i) => [p.pos[3 * i], p.pos[3 * i + 1], p.pos[3 * i + 2]];
    for (let f = 0; f < p.idx.length; f += 3) {
      const a = P(p.idx[f]), b = P(p.idx[f + 1]), c = P(p.idx[f + 2]);
      const n = V.norm(V.cross(V.sub(b, a), V.sub(c, a)));
      for (const x of [n, a, b, c]) { dv.setFloat32(o, x[0], true); dv.setFloat32(o + 4, x[1], true); dv.setFloat32(o + 8, x[2], true); o += 12; }
      dv.setUint16(o, 0, true); o += 2;
    }
  }
  return new Uint8Array(buf);
}

// accès de diagnostic (tests)
export const _interne = { evaluerBroche, manchonLibre, toursFente, distTour, placerBroches, normalesSommets, etendueLeLong };
