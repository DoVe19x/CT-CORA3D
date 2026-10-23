// =============================================================================
// 30 — os dans la scène : os déformé, os sain (fantôme), fragments d'ostéotomie,
//      broches de réduction, os tordu de l'étape « torsion »
// =============================================================================
let DATA = null;                     // { meta, bones } : os affichés (modèle synthétique ou os segmenté)
let MODEL = {};                      // modèle passé au cœur de calcul (meta + maillages sains)
let PLAN_ID = 0;                     // change à chaque nouvelle planification (caches des fragments)
let MODEL_ID = 0;                    // change quand on passe d'un os à un autre (cache de l'os tordu)
const G = {};                        // groupes de la scène
const OV = {};                       // calques de tracés : base (immobile) et dist (suit le fragment distal)

function initGroups() {
  for (const k of ['bone', 'ghost', 'prox', 'dist', 'wedge', 'gap', 'pins', 'torsion', 'guide', 'guideRed']) { G[k] = new THREE.Group(); scene.add(G[k]); }
  G.distFrag = new THREE.Group(); G.dist.add(G.distFrag);      // fragments distaux (le calque OV.dist est à côté)
  G.pinsDist = new THREE.Group(); G.dist.add(G.pinsDist);      // broche distale : suit le fragment distal
  G.dist.matrixAutoUpdate = false;
  G.wedge.matrixAutoUpdate = false;
  OV.base = new Overlay(scene);
  OV.dist = new Overlay(G.dist);
}
function setMatrix(g, T) { g.matrix.fromArray(RT.toMat4(T)); g.matrixWorldNeedsUpdate = true; }

function clearGroup(g) {
  const partages = [...Object.values(MAT), ...Object.values(MAT_GUIDE)];
  g.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material && !partages.includes(o.material) && o.material.dispose) o.material.dispose(); });
  g.clear();
}

// géométrie Three.js d'un os (positions éventuellement déformées) avec ses attributs de rendu
function boneGeometry(name, pos) {
  const b = DATA.bones[name];
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('aAO', new THREE.BufferAttribute(b.ao, 1));
  g.setAttribute('aCart', new THREE.BufferAttribute(b.cart, 1));
  g.setAttribute('aMed', new THREE.BufferAttribute(b.med, 1));
  g.setIndex(new THREE.BufferAttribute(b.idx, 1));
  g.computeVertexNormals();
  g.computeBoundingBox();
  return g;
}

// os déformé intact + os sain en transparence ; os voisins (rotule et fabelles du fémur), que le guide et les broches
// évitent, tels que planifiés
function buildBones(P) {
  clearGroup(G.bone); clearGroup(G.ghost);
  const voisins = Object.entries(P.voisins || {}).filter(([n]) => DATA.bones[n]);
  for (const [n, pos] of [...P.meshes.map((n) => [n, P.pos[n]]), ...voisins]) {
    G.bone.add(new THREE.Mesh(boneGeometry(n, pos), boneMaterial()));
    const gh = new THREE.Mesh(boneGeometry(n, DATA.bones[n].pos), MAT.ghost);
    gh.renderOrder = 4;
    G.ghost.add(gh);
  }
}

// ------------------------------------------------------------ fragments --
const triangulate2D = (contour, holes) => THREE.ShapeUtils.triangulateShape(
  contour.map((p) => new THREE.Vector2(p[0], p[1])), holes.map((hh) => hh.map((p) => new THREE.Vector2(p[0], p[1]))));

function fragmentObject(M, surfaceMat) {
  const grp = new THREE.Group();
  const surf = [], spongy = [], compact = [];
  for (let f = 0; f < M.tri.length / 3; f++) {
    const t = M.tag[f], tri = [M.tri[3 * f], M.tri[3 * f + 1], M.tri[3 * f + 2]];
    if (t === 0) surf.push(...tri); else if (t >= 100) compact.push(...tri); else spongy.push(...tri);
  }
  if (surf.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(M.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(M.nrm, 3));
    g.setAttribute('aAO', new THREE.Float32BufferAttribute(M.attr.ao, 1));
    g.setAttribute('aCart', new THREE.Float32BufferAttribute(M.attr.cart, 1));
    g.setAttribute('aMed', new THREE.Float32BufferAttribute(M.attr.med, 1));
    g.setIndex(surf);
    grp.add(new THREE.Mesh(g, surfaceMat || boneMaterial()));
  }
  for (const [list, mat] of [[compact, MAT.capCompact], [spongy, MAT.capSpongy]]) {
    if (!list.length) continue;
    const pos = new Float32Array(list.length * 3);
    for (let i = 0; i < list.length; i++) for (let c = 0; c < 3; c++) pos[3 * i + c] = M.pos[3 * list[i] + c];
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.computeVertexNormals();
    grp.add(new THREE.Mesh(g, surfaceMat || mat));
  }
  return grp;
}

const FRAG = { key: null, gapLoops: null, raw: null };
const cleFragments = (P, kind) => `${PLAN_ID}|${kind}`;
// Découpe réelle du maillage déformé par les plans de l'ostéotomie choisie.
function buildFragments(P, kind) {
  const key = cleFragments(P, kind);
  if (FRAG.key === key) return;
  clearFragments();
  FRAG.key = key;
  const O = P.osteo[kind];
  const [P1, P2b] = O.plans;
  for (const n of P.meshes) {
    const geo = G.bone.children.find((m) => m.geometry.attributes.position.array === P.pos[n])?.geometry || boneGeometry(n, P.pos[n]);
    const b = DATA.bones[n];
    const M = meshFromArrays(P.pos[n], b.idx, geo.attributes.normal.array, { ao: b.ao, cart: b.cart, med: b.med });
    let prox, dist, wedge = null;
    if (kind === 'fermeture') {
      prox = clipMesh(M, P1.p, P1.n, -1, 1, triangulate2D);                  // au-dessus du trait proximal
      const below = clipMesh(M, P1.p, P1.n, +1, 1, triangulate2D);
      dist = clipMesh(below, P2b.p, P2b.n, +1, 2, triangulate2D);            // au-dessous du trait distal
      wedge = clipMesh(below, P2b.p, P2b.n, -1, 2, triangulate2D);           // entre les deux : coin retiré
    } else {
      prox = clipMesh(M, P1.p, P1.n, -1, 1, triangulate2D);
      dist = clipMesh(M, P1.p, P1.n, +1, 1, triangulate2D);
      if (n === P.bone) FRAG.gapLoops = prox.loops;                          // contour de la coupe (espace d'ouverture)
    }
    if (n === P.bone) FRAG.raw = { prox, dist, kind };                       // pour l'export de l'os corrigé prévu
    G.prox.add(fragmentObject(prox));
    G.distFrag.add(fragmentObject(dist));
    if (wedge && wedge.tri.length) G.wedge.add(fragmentObject(wedge, MAT.wedge));
  }
  // os voisins entiers : du côté distal de la coupe, ils suivent le fragment distal (rotule, fabelles)
  const Pl = O.plans[O.plans.length - 1];
  for (const [n, pos] of Object.entries(P.voisins || {})) {
    if (!DATA.bones[n]) continue;
    let s = 0;
    for (let i = 0; i < pos.length; i += 3) s += (pos[i] - Pl.p[0]) * Pl.n[0] + (pos[i + 1] - Pl.p[1]) * Pl.n[1] + (pos[i + 2] - Pl.p[2]) * Pl.n[2];
    (s > 0 ? G.distFrag : G.prox).add(new THREE.Mesh(boneGeometry(n, pos), boneMaterial()));
  }
  if (kind === 'ouverture' && FRAG.gapLoops) buildGap(P, O);
  buildPins(P, O);
}
function clearFragments() {
  for (const k of ['prox', 'distFrag', 'wedge', 'gap', 'pins', 'pinsDist']) if (G[k]) clearGroup(G[k]);
  FRAG.key = null; FRAG.gapLoops = null; FRAG.gap = null; FRAG.raw = null;
}

// Broches de réduction (Kirschner) : deux par fragment (système de réduction de CT-CORA3D ; une par fragment dans
// les prescriptions plus anciennes). Les distales sont forées avec l'inverse de la correction : toutes deviennent
// parallèles quand la correction (angle + dérotation) est faite : les moitiés du guide de coupe, remises dessus, se
// verrouillent alors l'une à l'autre (ou le guide de réduction s'enfile sur les 4).
function buildPins(P, O) {
  const r = INSTRUMENT.broche / 2, longueur = P.section.largeur + 26;
  for (const bb of O.brochesReduction || O.broches) {
    const g = new THREE.CylinderGeometry(r, r, longueur, 16);
    const m = new THREE.Mesh(g, MAT.pin);
    const d = new THREE.Vector3(...bb.dir).normalize();
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d);
    // la broche entre par la face d'appui (côté −dir) et traverse l'os
    m.position.set(...V.add(bb.point, V.mul(bb.dir, 4 - longueur / 2 + P.section.largeur / 2)));
    (bb.fragment === 'proximal' ? G.pins : G.pinsDist).add(m);
  }
}

// Espace d'ouverture : volume balayé par le contour de la coupe quand le fragment distal tourne
// autour de la charnière. K anneaux entre l'angle 0 et l'angle courant ; mis à jour à chaque image.
const GAP_K = 10;
function buildGap(P, O) {
  const loops = FRAG.gapLoops.filter((l) => l.length >= 3);
  let nv = 0; const idx = [];
  for (const loop of loops) {
    const N = loop.length;
    for (let k = 0; k < GAP_K; k++) for (let i = 0; i < N; i++) {
      const a = nv + k * N + i, b = nv + k * N + (i + 1) % N, c = a + N, d = b + N;
      idx.push(a, b, d, a, d, c);
    }
    nv += N * (GAP_K + 1);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(nv * 3), 3));
  g.setIndex(idx);
  const m = new THREE.Mesh(g, MAT.gap);
  m.renderOrder = 6;
  G.gap.add(m);
  FRAG.gap = { mesh: m, loops, H: O.charniere, k: O.k };
}
function updateGap(angle) {
  const gp = FRAG.gap;
  if (!gp) return;
  const arr = gp.mesh.geometry.attributes.position.array;
  let o = 0;
  for (const loop of gp.loops) for (let k = 0; k <= GAP_K; k++) {
    const T = RT.aboutAxis(gp.H, gp.k, angle * k / GAP_K);
    for (const p of loop) { const q = RT.apply(T, p); arr[o++] = q[0]; arr[o++] = q[1]; arr[o++] = q[2]; }
  }
  gp.mesh.geometry.attributes.position.needsUpdate = true;
  gp.mesh.geometry.computeVertexNormals();
  gp.mesh.geometry.computeBoundingSphere();
  gp.mesh.visible = Math.abs(angle) > 1e-4;
}

// Avancement de la correction p ∈ [0, 1] -> transformations des fragments
//   fermeture : 0–0,25 le coin est retiré (glisse vers le côté convexe), 0,25–1 rotation
//   ouverture : 0–1 rotation, l'espace d'ouverture apparaît
//   la dérotation éventuelle se fait en même temps : autour de l'axe distal pour un coin de fermeture (avant la
//   fermeture dans la composition), autour de l'axe réaligné pour un coin d'ouverture (après l'ouverture)
function transformCorrection(O, kind, e) {
  const Ta = RT.aboutAxis(O.charniere, O.k, O.corr * RAD * e);
  if (!O.derotation || !O.axeDerotation) return Ta;
  const Rd = RT.aboutAxis(O.axeDerotation.p, O.axeDerotation.d, O.derotation * RAD * e);
  return kind === 'fermeture' ? RT.compose(Ta, Rd) : RT.compose(Rd, Ta);
}
function applyCorrection(P, kind, p) {
  const O = P.osteo[kind];
  const s = kind === 'fermeture' ? clamp((p - 0.25) / 0.75, 0, 1) : clamp(p, 0, 1);
  const e = s * s * (3 - 2 * s);
  setMatrix(G.dist, transformCorrection(O, kind, e));
  if (kind === 'fermeture') {
    const w = clamp(p / 0.25, 0, 1);
    const off = V.add(V.mul(P.bis.c, 30 * w), V.mul(P.bis.n, 14 * w));
    setMatrix(G.wedge, { R: M3.I(), t: off });
    MAT.wedge.opacity = 0.7 * (1 - w);
    G.wedge.visible = w < 1;
  } else {
    updateGap(O.corr * RAD * e);
  }
  return e;
}

// ------------------------------------------------------------ torsion --
// Os sain tordu de τ et posé de travers de ρ (étape « torsion ») : géométries réutilisées, positions mises à jour.
const TOR = { cle: null, meshes: [] };
function buildTorsionBone(bone) {
  if (TOR.cle === `${MODEL_ID}|${bone}`) return;
  clearGroup(G.torsion);
  TOR.cle = `${MODEL_ID}|${bone}`; TOR.meshes = [];
  for (const n of meshesOf(MODEL, bone)) {
    const pos = new Float32Array(DATA.bones[n].pos.length);
    pos.set(DATA.bones[n].pos);
    const m = new THREE.Mesh(boneGeometry(n, pos), boneMaterial());
    G.torsion.add(m);
    TOR.meshes.push({ n, m });
  }
}
function updateTorsionBone(bone, tau, rho) {
  buildTorsionBone(bone);
  const Tz = makeTorsion(reference(MODEL, bone).ax, tau, rho);
  for (const { n, m } of TOR.meshes) {
    const attr = m.geometry.attributes.position;
    torsionArray(Tz, DATA.bones[n].pos, attr.array);
    attr.needsUpdate = true;
    m.geometry.computeVertexNormals();
    m.geometry.computeBoundingBox();
    m.geometry.computeBoundingSphere();
  }
}

// ------------------------------------------------------------ guides imprimables (étape 7) --
// Maillages lus sur le serveur (repère de l'os) : moitiés du guide de coupe, pièce du coin, ponts sécables ; après la
// correction (fragment proximal fixe) : moitiés remises en place et broches de verrouillage (verrou intégré), ou guide de
// réduction séparé.
const MAT_GUIDE = {
  proximal: new THREE.MeshStandardMaterial({ color: 0x2f6db5, roughness: 0.55, metalness: 0.05 }),
  distal: new THREE.MeshStandardMaterial({ color: 0x23a08f, roughness: 0.55, metalness: 0.05 }),
  ponts: new THREE.MeshStandardMaterial({ color: 0xe8822b, roughness: 0.5, metalness: 0.05 }),
  reduction: new THREE.MeshStandardMaterial({ color: 0x8e44ad, roughness: 0.5, metalness: 0.05 }),
  coin: new THREE.MeshStandardMaterial({ color: 0xd9b43a, roughness: 0.55, metalness: 0.05 }),
  verrou_broches: new THREE.MeshStandardMaterial({ color: 0xc0392b, roughness: 0.4, metalness: 0.3 }),
};
// pièces montrées après la correction (vue « réduction ») et leur matériau
const APRES_CORRECTION = { reduction: 'reduction', verrou_proximal: 'proximal', verrou_distal: 'distal', verrou_broches: 'verrou_broches' };
function meshGuide(m, mat) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(m.pos, 3));
  g.setIndex(new THREE.BufferAttribute(m.idx, 1));
  g.computeVertexNormals();
  return new THREE.Mesh(g, mat);
}
function construireGuides(meshes) {
  clearGroup(G.guide); clearGroup(G.guideRed);
  // clés « proximal », « distal », « coin », « ponts » (guide de coupe) ; « reduction » ou « verrou_* » (après la correction)
  for (const [k, m] of Object.entries(meshes)) {
    if (APRES_CORRECTION[k]) G.guideRed.add(meshGuide(m, MAT_GUIDE[APRES_CORRECTION[k]]));
    else if (MAT_GUIDE[k]) G.guide.add(meshGuide(m, MAT_GUIDE[k]));
  }
}
function viderGuides() { clearGroup(G.guide); clearGroup(G.guideRed); }
