// =============================================================================
// 20 — scène : rendu, caméra orthographique (comme une radiographie), matériaux,
//      et outil de dessin des tracés (lignes, points, arcs d'angle, plans, étiquettes)
// =============================================================================
const canvas = $('#gl');
const viewportEl = $('#viewport');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.6;

// Caméra orthographique : pas de perspective, les angles vus de face sont les vrais angles du plan frontal.
const camera = new THREE.OrthographicCamera(-100, 100, 100, -100, -5000, 5000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.09;
controls.rotateSpeed = 0.75;
controls.zoomSpeed = 1.1;
controls.screenSpacePanning = true;
controls.minZoom = 0.4;
controls.maxZoom = 12;

const labelRenderer = new CSS2DRenderer({ element: $('#labels') });

const hemi = new THREE.HemisphereLight(0xe9f1ff, 0x3b3328, 0.4);
const keyLight = new THREE.DirectionalLight(0xfff3e2, 2.2);
const fillLight = new THREE.DirectionalLight(0xdbe7ff, 0.8);
const rimLight = new THREE.DirectionalLight(0xffffff, 1.0);
scene.add(hemi, keyLight, fillLight, rimLight);
// les lumières suivent la caméra (l'os reste bien éclairé quel que soit l'angle de vue)
function placeLights() {
  const q = camera.quaternion;
  keyLight.position.set(-0.5, 0.8, 1).applyQuaternion(q).multiplyScalar(500).add(controls.target);
  fillLight.position.set(0.9, 0.1, 0.6).applyQuaternion(q).multiplyScalar(500).add(controls.target);
  rimLight.position.set(0.2, 0.4, -1).applyQuaternion(q).multiplyScalar(500).add(controls.target);
  keyLight.target.position.copy(controls.target); fillLight.target.position.copy(controls.target); rimLight.target.position.copy(controls.target);
  keyLight.target.updateMatrixWorld(); fillLight.target.updateMatrixWorld(); rimLight.target.updateMatrixWorld();
}

// ------------------------------------------------------------------ matériaux --
const GLSL_NOISE = `
float hash3(vec3 p){ p = fract(p*0.3183099 + .1); p *= 17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
float vnoise(vec3 x){ vec3 i = floor(x); vec3 f = fract(x); f = f*f*(3.0-2.0*f);
  return mix(mix(mix(hash3(i), hash3(i+vec3(1,0,0)), f.x), mix(hash3(i+vec3(0,1,0)), hash3(i+vec3(1,1,0)), f.x), f.y),
             mix(mix(hash3(i+vec3(0,0,1)), hash3(i+vec3(1,0,1)), f.x), mix(hash3(i+vec3(0,1,1)), hash3(i+vec3(1,1,1)), f.x), f.y), f.z); }`;

// os : couleur ivoire, cartilage articulaire bleuté, occlusion ambiante pré-calculée
function boneMaterial() {
  const m = new THREE.MeshPhysicalMaterial({ color: 0xeadcc2, roughness: 0.6, metalness: 0, clearcoat: 0.5, clearcoatRoughness: 0.25, sheen: 0.2, sheenRoughness: 0.85, sheenColor: new THREE.Color(0xfff0d6), transparent: true });
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nattribute float aAO; attribute float aCart; attribute float aMed;\nvarying float vAO; varying float vCart; varying float vMed; varying vec3 vLocal;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvAO = aAO; vCart = aCart; vMed = aMed; vLocal = position;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying float vAO; varying float vCart; varying float vMed; varying vec3 vLocal;\n${GLSL_NOISE}`)
      .replace('#include <color_fragment>', `#include <color_fragment>
float cart = clamp(vCart, 0.0, 1.0);
float n1 = vnoise(vLocal*0.21)*0.62 + vnoise(vLocal*0.83)*0.38;
diffuseColor.rgb *= 0.92 + 0.13*n1;
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.85, 0.91, 0.95)*(0.96+0.06*n1), cart*0.85);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.49, 0.18, 0.15)*(0.8+0.4*vnoise(vLocal*1.3)), step(0.75, vMed));`)
      .replace('#include <aomap_fragment>', `#include <aomap_fragment>
reflectedLight.indirectDiffuse *= vAO;
reflectedLight.indirectSpecular *= mix(1.0, vAO, 0.8);
reflectedLight.directDiffuse *= mix(1.0, vAO, 0.32);`);
  };
  m.customProgramCacheKey = () => 'bone-simple-v1';
  return m;
}
// faces de coupe : os compact (diaphyse, avec canal médullaire) ou spongieux (métaphyse)
function capMaterial(kind) {
  const m = new THREE.MeshStandardMaterial({ color: kind === 'compact' ? 0xe2d2b4 : 0xd8bf98, roughness: 0.82, metalness: 0, transparent: true });
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vLocal;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvLocal = position;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `#include <common>\nvarying vec3 vLocal;\n${GLSL_NOISE}`)
      .replace('#include <color_fragment>', kind === 'compact' ? `#include <color_fragment>
diffuseColor.rgb *= 0.9 + 0.14*(vnoise(vLocal*2.6)*0.5 + vnoise(vLocal*7.0)*0.5);` : `#include <color_fragment>
float pores = smoothstep(0.5, 0.62, vnoise(vLocal*1.6)*0.65 + vnoise(vLocal*4.2 + 3.1)*0.35);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.55, 0.22, 0.17), pores*0.75);`);
  };
  m.customProgramCacheKey = () => 'cap-simple-' + kind;
  return m;
}
const MAT = {
  capCompact: capMaterial('compact'),
  capSpongy: capMaterial('spongy'),
  ghost: new THREE.MeshStandardMaterial({ color: 0x8fb4d0, transparent: true, opacity: 0.2, depthWrite: false, roughness: 0.6 }),
  wedge: new THREE.MeshStandardMaterial({ color: 0xff5b61, transparent: true, opacity: 0.7, roughness: 0.5, depthWrite: false, side: THREE.DoubleSide }),
  gap: new THREE.MeshStandardMaterial({ color: 0xffa640, transparent: true, opacity: 0.55, roughness: 0.5, depthWrite: false, side: THREE.DoubleSide }),
  pin: new THREE.MeshStandardMaterial({ color: 0xb8c2cc, metalness: 0.85, roughness: 0.28 }),
};

// ------------------------------------------------------------------ tracés --
const lineMats = new Set();
function lineMaterial(color, width, opts = {}) {
  const m = new LineMaterial({ color, linewidth: width, transparent: true, opacity: opts.opacity ?? 1, depthTest: false,
    dashed: !!opts.dashed, dashSize: opts.dashSize ?? 4, gapSize: opts.gapSize ?? 3, worldUnits: false });
  m.resolution.set(viewportEl.clientWidth || 800, viewportEl.clientHeight || 600);
  lineMats.add(m);
  return m;
}
const v3 = (p) => new THREE.Vector3(p[0], p[1], p[2]);
const COL = {};
function readColors() {
  for (const k of ['prox', 'dist', 'cora', 'bis', 'hinge', 'cut', 'mech', 'joint', 'ok', 'pin', 'plane', 'trans']) COL[k] = cssColor('--c-' + k);
  COL.fg3 = cssColor('--fg-3');
  COL.truth = new THREE.Color(isLight() ? 0x111c24 : 0xffffff);
}

// Les tracés 2D d'une vue sont posés dans un plan qui passe au milieu de l'os et dessinés par-dessus l'os
// (depthTest désactivé), comme un calque sur une radiographie.
//   plane = 'F' (frontal) : point 2D [x, y] -> [x, y, z]   avec z = profondeur
//   plane = 'S' (sagittal) : point 2D [z, y] -> [z0, y, z] avec z0 = profondeur (abscisse X du plan)
// Un point 3D est utilisé tel quel (tracés 3D : plan oblique, ACA, broches…).
class Overlay {
  constructor(parent) { this.g = new THREE.Group(); parent.add(this.g); this.z = 0; this.plane = 'F'; }
  clear() {
    const kill = [];
    this.g.traverse((o) => { if (o !== this.g) kill.push(o); });
    for (const o of kill) {
      if (o.geometry) o.geometry.dispose();
      if (o.material) { lineMats.delete(o.material); o.material.dispose(); }
      if (o.isCSS2DObject && o.element && o.element.parentNode) o.element.parentNode.removeChild(o.element);
    }
    this.g.clear();
  }
  P(p) { if (p.length === 3) return p; return this.plane === 'S' ? [this.z, p[1], p[0]] : [p[0], p[1], this.z]; }
  line(points, color, width = 2.5, opts = {}) {
    const geo = new LineGeometry();
    geo.setPositions(points.flatMap((p) => this.P(p)));
    const l = new Line2(geo, lineMaterial(color, width, opts));
    if (opts.dashed) l.computeLineDistances();
    l.renderOrder = opts.renderOrder ?? 20;
    this.g.add(l);
    return l;
  }
  seg(a, b, color, width, opts) { return this.line([a, b], color, width, opts); }
  // droite (p, d) entre les paramètres t0 et t1
  ray(p, d, t0, t1, color, width, opts) { return this.line([P2.add(p, P2.mul(d, t0)), P2.add(p, P2.mul(d, t1))], color, width, opts); }
  dot(p, r, color, opts = {}) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(r, 20, 14), new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true, opacity: opts.opacity ?? 1 }));
    m.position.copy(v3(this.P(p))); m.renderOrder = 30; this.g.add(m); return m;
  }
  ring(p, r, color, width = 1.5, opts = {}) {
    const pts = [];
    for (let i = 0; i <= 48; i++) { const a = i / 48 * Math.PI * 2; pts.push([p[0] + r * Math.cos(a), p[1] + r * Math.sin(a)]); }
    return this.line(pts, color, width, opts);
  }
  octa(p, r, color) {
    const m = new THREE.Mesh(new THREE.OctahedronGeometry(r), new THREE.MeshBasicMaterial({ color, wireframe: true, depthTest: false, transparent: true }));
    m.position.copy(v3(this.P(p))); m.renderOrder = 31; this.g.add(m); return m;
  }
  // arc d'angle de centre c, de la direction a à la direction b (le plus petit angle), rayon r
  arc(c, a, b, r, color, width = 2, label = null, cls = '') {
    a = P2.norm(a); b = P2.norm(b);
    const ang = P2.ang(a, b);
    const pts = [];
    for (let i = 0; i <= 40; i++) pts.push(P2.add(c, P2.mul(P2.rot(a, ang * i / 40), r)));
    this.line(pts, color, width);
    if (label) this.label(label, P2.add(c, P2.mul(P2.rot(a, ang / 2), r + 9)), cls);
  }
  // arc d'angle 3D de centre c, de la direction a à la direction b (dans le plan qu'elles définissent)
  arc3(c, a, b, r, color, width = 2, label = null, cls = '') {
    a = V.norm(a); b = V.norm(b);
    const n = V.cross(a, b), s = V.len(n);
    if (s < 1e-9) return;
    const ang = Math.atan2(s, V.dot(a, b));
    const pts = [];
    for (let i = 0; i <= 40; i++) pts.push(V.add(c, V.mul(M3.mv(M3.axisAngle(n, ang * i / 40), a), r)));
    this.line(pts, color, width);
    if (label) this.label(label, V.add(c, V.mul(M3.mv(M3.axisAngle(n, ang / 2), a), r + 11)), cls);
  }
  // rectangle dans le plan (centre c 3D, axes unitaires u et w 3D, demi-dimensions)
  rect(c, u, w, hu, hw, color, opacity = 0.14, outline = true) {
    const geo = new THREE.PlaneGeometry(2 * hu, 2 * hw);
    const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false }));
    const n = new THREE.Vector3().crossVectors(v3(u), v3(w)).normalize();
    m.matrixAutoUpdate = false;
    m.matrix.makeBasis(v3(u), v3(w), n).setPosition(v3(c));
    m.renderOrder = 8; this.g.add(m);
    if (outline) {
      const k = (s, t) => V.add(c, V.add(V.mul(u, s * hu), V.mul(w, t * hw)));
      this.line([k(-1, -1), k(1, -1), k(1, 1), k(-1, 1), k(-1, -1)], color, 1.4, { opacity: 0.9 });
    }
    return m;
  }
  // ancre : 0.5 = centrée sur le point ; 0 = le point est au bord gauche de l'étiquette ; 1 = au bord droit
  label(text, p, cls = '', ancre = 0.5) {
    const o = new CSS2DObject(h('div', { class: 'lbl ' + cls }, text));
    o.position.copy(v3(this.P(p))); o.center.set(ancre, 0.5);
    this.g.add(o);
    return o;
  }
}
