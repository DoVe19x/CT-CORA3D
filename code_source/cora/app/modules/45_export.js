// =============================================================================
// 45 — export pour le guide de coupe : ZIP = prescription.json (format v2.2) + STL + mode d'emploi
// =============================================================================
// ZIP sans compression (méthode « stockage »), repris de la v1 : aucune bibliothèque nécessaire.
const CRC_TABLE = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(u8) { let c = 0xffffffff; for (let i = 0; i < u8.length; i++) c = CRC_TABLE[(c ^ u8[i]) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }
function zipStore(files) {
  const enc = new TextEncoder();
  const chunks = [], central = [];
  let offset = 0;
  for (const f of files) {
    const name = enc.encode(f.name);
    const data = typeof f.data === 'string' ? enc.encode(f.data) : f.data;
    const crc = crc32(data);
    const lh = new DataView(new ArrayBuffer(30));
    lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true); lh.setUint16(8, 0, true);
    lh.setUint16(10, 0, true); lh.setUint16(12, 0x21, true); lh.setUint32(14, crc, true);
    lh.setUint32(18, data.length, true); lh.setUint32(22, data.length, true); lh.setUint16(26, name.length, true); lh.setUint16(28, 0, true);
    chunks.push(new Uint8Array(lh.buffer), name, data);
    const ch = new DataView(new ArrayBuffer(46));
    ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true); ch.setUint16(8, 0x0800, true); ch.setUint16(10, 0, true);
    ch.setUint16(12, 0, true); ch.setUint16(14, 0x21, true); ch.setUint32(16, crc, true); ch.setUint32(20, data.length, true); ch.setUint32(24, data.length, true);
    ch.setUint16(28, name.length, true); ch.setUint16(30, 0, true); ch.setUint16(32, 0, true); ch.setUint16(34, 0, true); ch.setUint16(36, 0, true);
    ch.setUint32(38, 0, true); ch.setUint32(42, offset, true);
    central.push(new Uint8Array(ch.buffer), name);
    offset += 30 + name.length + data.length;
  }
  const cdSize = central.reduce((s, c) => s + c.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
  end.setUint32(12, cdSize, true); end.setUint32(16, offset, true);
  return new Blob([...chunks, ...central, new Uint8Array(end.buffer)], { type: 'application/zip' });
}
// maillage au format .bin de l'application (nb sommets, nb triangles, float32, uint32) : garde l'ordre des sommets
// (la carte du cartilage, une valeur par sommet, s'y réfère ; un STL relu fusionne et réordonne les sommets)
function binMaillage(pos, idx) {
  const nv = pos.length / 3, nf = idx.length / 3;
  const out = new Uint8Array(8 + 12 * nv + 12 * nf);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, nv, true); dv.setUint32(4, nf, true);
  new Float32Array(out.buffer, 8, 3 * nv).set(pos);
  new Uint32Array(out.buffer, 8 + 12 * nv, 3 * nf).set(idx);
  return out;
}
function telecharger(nom, blob) {
  const url = URL.createObjectURL(blob);
  const a = h('a', { href: url, download: nom });
  document.body.append(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 2000);
}

function lisezMoiExport(P, kind, presc, voisins = [], cartilage = false) {
  const O = P.osteo[kind], R = P.reel, fos = nomFichierOs(P);
  const cas = R
    ? `${NOM_OS[P.bone]} segmenté (série ${R.serie}, membre ${R.cote}${R.miroir ? ', mis en miroir pour être traité comme un droit' : ''})` +
      (P.D ? `, déformité de test : ${P.cas.titre.toLowerCase()} (F ${fr(P.thetaF, 0)}°, S ${fr(P.thetaS, 0)}°)` : ', analysé tel quel')
    : `${P.cas.titre} (modèle synthétique)`;
  const lignes = [
    `${R ? 'CT-CORA3D' : 'CORA 3D'} : export pour le guide de coupe (PMD2, ECAM)`,
    '',
    `Cas        : ${cas}, ${kindNom[kind]}`,
    `Référence  : ${nomRef(P)}`,
    `Déformité  : F = ${fr(Math.abs(P.Fm), 2)}° (${P.typeF}), S = ${fr(Math.abs(P.Sm), 2)}° (${P.typeS}), angle vrai θ = ${fr(P.theta, 2)}°, plan à φ = ${fr(P.phi, 1)}° du plan frontal`,
    `Charnière  : corticale ${sens3(kind === 'fermeture' ? P.bis.ccv : P.bis.c, true)}, orientation ψ = ${fr(P.psi, 1)}° (0° = crânio-caudale)`,
    `Coupe      : ${O.plans.length} fente(s), profondeur ${fr(O.D, 1)} mm, ${kind === 'fermeture' ? 'base du coin' : 'ouverture'} ${fr(O.base, 2)} mm`,
    `Torsion    : ${Math.abs(O.derotation) >= DEROTATION_MIN ? `dérotation de ${fr(O.derotation, 1)}° (${fr(P.torsion.avant, 1)}° -> ${fr(O.torsionApres, 1)}°)` : `non corrigée (${fr(P.torsion.avant, 1)}°)`}`,
    `Broches    : ${(O.brochesReduction || O.broches).length} × Ø ${fr(INSTRUMENT.broche)} mm (${(CONFIG_BROCHES[O.configBroches] || CONFIG_BROCHES['2+2']).nom}), ${fr(O.angleBroches, 2)}° entre les fragments (toutes parallèles après correction)`,
    `Stratégie  : face d'appui ${nomDirection(O.face)}${O.abordNonUsuel ? ' (abord non usuel)' : ` (abord ${O.abord})`}, charnière à ${fr(O.h, 1)} mm, trait ${Math.abs(O.z) < 0.5 ? 'au CORA (règle 1)' : `à ${fr(O.z, 0)} mm du CORA (règle 2)`}`,
  ];
  if (R && !P.D && !P.anomalies.length) lignes.push('', 'ATTENTION : les angles articulaires de cet os sont dans les normes ; aucune correction n\'est indiquée. Cet export illustre la méthode, sans indication chirurgicale.');
  lignes.push('',
    'Fichiers',
    `  prescription.json        contrat partie 1 -> partie 2 (format v2.2 : dérotation et 4 broches de réduction)`,
    `  ${fos.padEnd(24)} os planifié (mm ; X latéral, Y proximal, Z caudal${R && R.miroir ? ' ; membre gauche mis en miroir' : ''})`,
    `  ${(P.bone + '_planifie.bin').padEnd(24)} même os, format de l'application (ordre des sommets conservé) : entrée de etape7_guide.py`,
    `  ${P.bone}_corrige_prevu.stl   os après la correction simulée (contrôle visuel)`);
  for (const n of voisins) lignes.push(`  ${('voisin_' + n + '.stl').padEnd(24)} os voisin tel que planifié (${{ fibula: 'fibula', ulna: 'ulna', patella: 'rotule', fabellae: 'fabelles' }[n] || n}) : le guide et les broches l'évitent`);
  if (cartilage) lignes.push(`  ${('cartilage_' + P.bone + '.u8').padEnd(24)} cartilage articulaire : 1 octet par sommet de ${P.bone}_planifie.bin (255 = cartilage)`);
  if (R) lignes.push(`  cora_${R.nom || P.bone}.json${' '.repeat(Math.max(1, 13 - (R.nom || P.bone).length))}repères automatiques (étape 6), dans le repère de l'os et dans celui du scanner`);
  lignes.push('',
    'Construire les guides imprimables : bouton « Construire les guides 3D » de l\'étape 12 dans CT-CORA3D, ou en ligne de',
    'commande (depuis le dossier PMD2, après avoir dézippé dans <dossier>) :',
    `  macOS   : .venv/bin/python CT-CORA3D/code_source/etape7_guide.py --prescription <dossier>/prescription.json --os <dossier>/${P.bone}_planifie.bin${voisins.map((n) => ` --voisin ${n}=<dossier>/voisin_${n}.stl`).join('')}${cartilage ? ` --cartilage <dossier>/cartilage_${P.bone}.u8` : ''} --sortie <dossier>`,
    `  Windows : .venv\\Scripts\\python CT-CORA3D\\code_source\\etape7_guide.py --prescription <dossier>\\prescription.json --os <dossier>\\${P.bone}_planifie.bin${voisins.map((n) => ` --voisin ${n}=<dossier>\\voisin_${n}.stl`).join('')}${cartilage ? ` --cartilage <dossier>\\cartilage_${P.bone}.u8` : ''} --sortie <dossier>`,
    '(sans les options --voisin et --cartilage, le guide ignorerait les os voisins et le cartilage).',
    'Résultat : guide_coupe.stl (à imprimer d\'une pièce : deux moitiés reliées par des ponts sécables), guide_reduction.stl,',
    'os_corrige.stl, guide.json (contrôles et mode opératoire), guide.png, plans 2D.');
  if (R) {
    lignes.push('',
      'Revenir aux coordonnées du scanner (pour superposer le guide au CT, par exemple dans 3D Slicer) :',
      '  prescription.json > os_segmente > repere_scanner > os_vers_scanner est la matrice 4 × 4 : p_scanner = M · (x, y, z, 1).',
      R.miroir ? '  Son déterminant vaut −1 (membre gauche mis en miroir) : après transformation, inverser l\'ordre des sommets de chaque triangle.' : '  Son déterminant vaut +1 : une simple rotation + translation.',
      '  Exemple (Python, trimesh) : m = trimesh.load("guide.stl"); m.apply_transform(M); m.export("guide_scanner.stl")',
      '  (trimesh corrige lui-même l\'orientation des triangles quand le déterminant est négatif).');
  }
  lignes.push('', `Généré le ${new Date().toLocaleString('fr-BE')}, schéma ${presc.schema_version}.`, '');
  return lignes.join('\r\n');
}

function exporterGuide(P, kind) {
  const msg = $('#export-msg');
  try {
    const presc = prescription(P, kind, { parametresGuide: S.guideParams });
    const fos = nomFichierOs(P);
    const files = [{ name: 'prescription.json', data: JSON.stringify(presc, null, 2) }];
    const parts = P.meshes.map((n) => ({ pos: P.pos[n], idx: MODEL.bones[n].idx }));
    files.push({ name: fos, data: stlBinary(parts.slice(0, 1), `${P.bone} ${P.reel ? 'CT-CORA3D' : 'CORA3D'}`) });
    buildFragments(P, kind);
    if (FRAG.raw) {
      const T = P.osteo[kind].T, d = FRAG.raw.dist;
      const posD = new Float32Array(d.pos.length);
      for (let i = 0; i < d.pos.length; i += 3) { const q = RT.apply(T, [d.pos[i], d.pos[i + 1], d.pos[i + 2]]); posD[i] = q[0]; posD[i + 1] = q[1]; posD[i + 2] = q[2]; }
      files.push({ name: `${P.bone}_corrige_prevu.stl`, data: stlBinary([{ pos: FRAG.raw.prox.pos, idx: FRAG.raw.prox.tri }, { pos: posD, idx: d.tri }], `${P.bone} corrige`) });
    }
    if (P.reel) files.push({ name: `cora_${P.reel.nom || P.bone}.json`, data: JSON.stringify(P.reel, null, 1) });
    // os planifié au format .bin, os voisins et cartilage : etape7_guide.py en ligne de commande construit alors le même
    // guide que l'application (il évite la fibula, la rotule et les fabelles et ne repose pas sur le cartilage)
    files.push({ name: `${P.bone}_planifie.bin`, data: binMaillage(P.pos[P.bone], MODEL.bones[P.bone].idx) });
    const voisins = { ...Object.fromEntries(P.meshes.filter((n) => n !== P.bone).map((n) => [n, P.pos[n]])), ...(P.voisins || {}) };
    const nomsVoisins = Object.keys(voisins).filter((n) => MODEL.bones[n]);
    for (const n of nomsVoisins) files.push({ name: `voisin_${n}.stl`, data: stlBinary([{ pos: voisins[n], idx: MODEL.bones[n].idx }], `${n} (voisin)`) });
    if (P.articulaire) files.push({ name: `cartilage_${P.bone}.u8`, data: Uint8Array.from(P.articulaire, (x) => (x ? 255 : 0)) });
    files.push({ name: 'LISEZ-MOI.txt', data: lisezMoiExport(P, kind, presc, nomsVoisins, !!P.articulaire) });
    const nom = P.reel
      ? `CT-CORA3D_${P.reel.serie}_${P.reel.nom || P.bone}${P.D ? '_test-' + P.cas.id.split('-').slice(1).join('-') : ''}_${kind}.zip`
      : `CORA3D_${P.cas.id}_${kind}.zip`;
    telecharger(nom, zipStore(files));
    if (msg) msg.textContent = `Fichier « ${nom} » enregistré dans le dossier des téléchargements.`;
  } catch (err) {
    console.error(err);
    if (msg) msg.textContent = `Export impossible : ${err.message}`;
  }
}
