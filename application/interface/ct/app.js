/* CT-CORA3D, onglet 1 « Segmentation CT » — interface.
   Le serveur local (serveur.py) fait tous les calculs ; cette page affiche le scanner en coupes, les os en 3D,
   et envoie les demandes (ouvrir une série, segmenter, renommer, séparer). Coordonnées : indices (k, j, i) du
   volume (coupe, ligne, colonne) et LPS (mm) du scanner, comme dans les fichiers produits. */
"use strict";
const { THREE, OrbitControls, RoomEnvironment } = window.__THREE__;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// intégrée dans la page à deux onglets de CT-CORA3D : thème et bouton « Quitter » sont ceux de la page
const INTEGRE = window.parent !== window;
const parentMsg = (m) => { if (INTEGRE) window.parent.postMessage(m, "*"); };
// fémur ou tibia exporté en STL : il peut passer à la planification CORA (onglet 2)
const osCora = (nom) => /^(femur|tibia|radius)(_gauche|_droit)?$/.test(nom || "");

const E = {
  config: null, serie: null, version: -1, ouverte: null, travail: null, enCours: false,
  point: [0, 0, 0],                      // réticule (k, j, i)
  ww: 2000, wl: 500, couleurs: true,
  selection: 0,
  separation: null,                      // { etiquette, points: [{ nom, kji }] }
  cache: new Map(),
  cachees: new Set(),                    // étiquettes masquées en 3D
};

// ================================================================== serveur
async function lire(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).erreur || r.statusText);
  return r.json();
}
async function envoyer(url, donnees = {}) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(donnees) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.erreur || r.statusText);
  return j;
}
async function action(nom, donnees = {}) {
  try {
    await envoyer("/api/action", { action: nom, ...donnees });
    E.enCours = true;
    suivre();
  } catch (e) { message(e.message, true); }
}
let minuterieMessage;
function message(texte, erreur = false) {
  const t = $("#toast");
  t.textContent = texte;
  t.classList.toggle("erreur", erreur);
  t.classList.add("visible");
  clearTimeout(minuterieMessage);
  minuterieMessage = setTimeout(() => t.classList.remove("visible"), erreur ? 6000 : 3200);
}
const fmt = (x, n = 1) => (x === null || x === undefined || Number.isNaN(x)) ? "n.d." : Number(x).toFixed(n).replace(".", ",");
const libelle = (nom) => {
  if (!nom) return "os non identifié";
  const [b, ...c] = nom.split("_");
  return (E.config?.libelles?.[b] || b) + (c.length ? " " + c.join(" ") : "");
};
const base = (nom) => (nom || "").split("_")[0];
const rgb = (c) => `rgb(${c.map((x) => Math.round(x * 255)).join(",")})`;

// ================================================================== suivi des calculs et des séries
let minuterieSuivi;
async function suivre() {
  clearTimeout(minuterieSuivi);
  try {
    const e = await lire("/api/etat");
    afficherSeries(e);
    afficherProgression(e.travail);
    const fini = E.enCours && e.travail.etat !== "en_cours";
    E.enCours = e.travail.etat === "en_cours";
    if (fini) {
      if (e.travail.etat === "erreur") message("Erreur : " + e.travail.erreur, true);
      else {
        message(`${e.travail.action} : terminé${e.travail.duree ? ` en ${fmt(e.travail.duree, 0)} s` : ""}`);
        // l'onglet CORA relit la liste des os segmentés (sauf après la construction des guides, lancée par lui)
        if (!e.travail.action.startsWith("Construction des guides")) parentMsg({ type: "segmentation-terminee" });
      }
    }
    if (e.ouverte !== E.ouverte || (e.ouverte && e.travail.version !== E.version && !E.enCours)) {
      E.ouverte = e.ouverte;
      E.version = e.travail.version;
      if (e.ouverte) await chargerSerie();
    }
  } catch (err) { /* serveur occupé ou arrêté : on réessaie */ }
  minuterieSuivi = setTimeout(suivre, E.enCours ? 600 : 2500);
}

function afficherSeries(e) {
  $("#dossierDicom").textContent = e.dossier;
  const liste = $("#listeSeries");
  const cle = JSON.stringify([e.series, e.ouverte]);
  if (liste.dataset.cle === cle) return;
  liste.dataset.cle = cle;
  liste.innerHTML = "";
  if (!e.series.length) {
    liste.innerHTML = `<p class="aide">Aucune série DICOM trouvée dans ce dossier.</p>`;
    return;
  }
  for (const s of e.series) {
    const b = document.createElement("button");
    b.className = "serie";
    b.setAttribute("role", "option");
    b.setAttribute("aria-selected", String(s.nom === e.ouverte));
    b.innerHTML = `<span class="nom"></span><span class="meta"></span><span class="meta"></span>${s.resultats ? '<span class="ok">✓ résultats enregistrés</span>' : ""}`;
    b.children[0].textContent = s.nom;
    b.children[1].textContent = `${s.coupes} coupes ${s.modalite} · ${s.description || "sans description"}`;
    b.children[2].textContent = `${s.patient} · ${s.date} · pixel ${fmt(s.pixel_mm?.[0], 3)} mm · coupe ${fmt(s.epaisseur_mm, 3)} mm`;
    b.addEventListener("click", () => {
      if (E.enCours) return message("Un calcul est en cours.", true);
      action("ouvrir", { nom: s.nom });
    });
    liste.append(b);
  }
}

function afficherProgression(t) {
  E.travail = t;
  const bloc = $("#blocProgression");
  const actif = t.etat === "en_cours" || ((t.etat === "termine" || t.etat === "erreur") && t.journal.length);
  bloc.hidden = !actif;
  $("#btnSegmenter").disabled = !E.serie || t.etat === "en_cours";
  $("#btnSegmenter").textContent = t.etat === "en_cours" && t.action === "Segmentation" ? "Segmentation en cours…" : "Segmenter la série";
  if (!actif) return;
  $("#titreProgression").textContent = t.etat === "en_cours" ? `${t.action}…` : t.etat === "erreur" ? `${t.action} : erreur` : `${t.action} : terminé`;
  const ol = $("#listeEtapes");
  ol.innerHTML = "";
  (t.etapes || []).forEach((nom, n) => {
    const li = document.createElement("li");
    li.textContent = nom;
    if (t.etat !== "en_cours" && t.etat !== "erreur") li.className = "fait";
    else if (n < t.etape) li.className = "fait";
    else if (n === t.etape) li.className = t.etat === "en_cours" ? "encours" : "";
    ol.append(li);
  });
  const j = $("#journal");
  const bas = j.scrollTop + j.clientHeight >= j.scrollHeight - 4;
  j.textContent = (t.journal || []).join("\n") + (t.erreur ? `\n⚠ ${t.erreur}` : "");
  if (bas) j.scrollTop = j.scrollHeight;
}

// ================================================================== série ouverte
async function chargerSerie() {
  const d = await lire("/api/serie");
  const nouvelle = !E.serie || E.serie.nom !== d.nom;
  E.serie = d;
  if (nouvelle) {
    E.point = d.dimensions.map((n) => Math.floor(n / 2));
    E.selection = 0;
    E.cachees.clear();
    for (const v of Object.values(vues)) v.reinitialiser();
    if (d.segments.length) {                        // réticule sur l'os principal
      const p = d.segments.find((s) => ["femur", "tibia", "radius"].includes(base(s.nom))) || d.segments[0];
      if (p.centre_kji) E.point = p.centre_kji.map(Math.round);
    }
  }
  const i = d.infos;
  $("#serieCourante").innerHTML = `<b></b> · <span></span>`;
  $("#serieCourante b").textContent = d.nom;
  $("#serieCourante span").textContent = `${i.dimensions_kji.join(" × ")} voxels · ${i.espacement_kji_mm.map((x) => fmt(x, 3)).join(" × ")} mm`;
  const g = d.graines?.length || 0;
  $("#aideGraines").textContent = g ? `${g} point(s) nommé(s) enregistré(s) (graines.json) seront réappliqués.` :
    "Calcul entièrement automatique (aucun point nommé enregistré).";
  afficherOs();
  afficherFichiers();
  afficherReperes();
  if (E.separation && !d.segments.some((s) => s.etiquette === E.separation.etiquette)) finSeparation();
  selectionner(d.segments.some((s) => s.etiquette === E.selection) ? E.selection : 0, false);
  for (const v of Object.values(vues)) v.orienter();
  rafraichirCoupes();
  await scene.charger(d);
  infoPoint();
}

function afficherOs() {
  afficherCas();
  const d = E.serie, liste = $("#listeOs");
  liste.innerHTML = "";
  if (!d.segments.length) {
    liste.innerHTML = `<p class="aide">Pas encore de segmentation : cliquez « Segmenter la série ».</p>`;
    return;
  }
  // une ligne par nom d'os (le bassin, les métatarses… regroupent plusieurs segments) ; non identifiés à part
  const groupes = new Map();
  for (const s of d.segments) {
    const cle = s.nom && !["autre", "objet"].includes(base(s.nom)) ? s.nom : `#${s.etiquette}`;
    if (!groupes.has(cle)) groupes.set(cle, []);
    groupes.get(cle).push(s);
  }
  const ligne = (segs, parent) => {
    const s = segs[0], vol = segs.reduce((a, x) => a + x.volume_cm3, 0);
    const el = document.createElement("div");
    el.className = "os" + (s.nom && !["autre", "objet"].includes(base(s.nom)) ? "" : " autre");
    el.dataset.e = segs.map((x) => x.etiquette).join(",");
    el.setAttribute("aria-selected", String(segs.some((x) => x.etiquette === E.selection)));
    el.title = s.raison || "";
    const etat = s.fichier ? (s.etanche ? `<span class="etat ok" title="maillage étanche, Euler ${s.euler}">✓</span>` :
      `<span class="etat critique" title="maillage non étanche">!</span>`) : `<span class="etat"></span>`;
    el.innerHTML = `<span class="pastille-os"></span><span class="lib"></span><span class="vol"></span>${etat}`;
    el.children[0].style.background = rgb(s.couleur);
    el.children[1].textContent = s.libelle + (segs.length > 1 ? ` ×${segs.length}` : "");
    el.children[2].textContent = `${fmt(vol, 1)} cm³`;
    const etatCora = d.cora?.[s.fichier];
    const candidat = !d.cas || d.cas.cible === s.fichier || d.cas.candidats?.some((x) => x.complet && x.nom === s.fichier);
    if (INTEGRE && s.fichier && osCora(s.fichier) && etatCora?.complet !== false && candidat) {   // raccourci vers la planification CORA
      const b = document.createElement("button");
      b.className = "mini cora";
      b.textContent = "CORA →";
      b.title = `Planifier une ostéotomie (méthode CORA) sur ${s.fichier}.stl`;
      b.addEventListener("click", (ev) => { ev.stopPropagation(); ouvrirCora(s.fichier); });
      el.children[1].after(b);
    } else if (INTEGRE && etatCora?.complet === false) {                              // os coupé : pas planifiable
      const t = document.createElement("span");
      t.className = "mini cora off";
      t.textContent = "CORA ✗";
      t.title = `Pas de planification CORA : ${etatCora.raison}`;
      el.children[1].after(t);
    }
    el.addEventListener("click", () => { selectionner(s.etiquette); viser(s); });
    parent.append(el);
  };
  const autres = [];
  for (const [cle, segs] of groupes) (cle.startsWith("#") ? autres.push(segs) : ligne(segs, liste));
  if (autres.length) {
    const det = document.createElement("details");
    det.open = autres.length <= 5 || autres.some((g) => g[0].etiquette === E.selection);
    det.innerHTML = `<summary class="separateur-os">Non identifiés / objets (${autres.length})</summary>`;
    autres.forEach((g) => ligne(g, det));
    liste.append(det);
  }
}

// carte « Os à planifier » : l'os complet détecté dans cette série (cora_cas.json, étape 6) et la raison du choix
function afficherCas() {
  const el = $("#carteCora"), d = E.serie, cas = d?.cas;
  if (!INTEGRE || !cas || !d.segments?.length) { el.hidden = true; return; }
  el.hidden = false;
  el.replaceChildren();
  const titre = document.createElement("div");
  titre.className = "cc-titre";
  titre.innerHTML = `<span class="cc-lbl">Os à planifier (CORA)</span><b></b>`;
  const p = document.createElement("p");
  p.className = "aide";
  p.textContent = cas.raison || "";
  el.classList.toggle("vide", !cas.cible);
  if (cas.cible) {
    const c = cas.candidats.find((x) => x.nom === cas.cible) || {};
    const nom = libelle(cas.cible);
    titre.querySelector("b").textContent = `${nom.charAt(0).toUpperCase()}${nom.slice(1)}${c.cote && !cas.cible.includes("_") ? " " + c.cote : ""}${c.longueur_mm ? ` · ${fmt(c.longueur_mm, 0)} mm` : ""}`;
    const b = document.createElement("button");
    b.className = "btn principal";
    b.textContent = "Planifier CORA →";
    b.title = "Ouvrir cet os dans l'onglet « Planification CORA »";
    b.addEventListener("click", () => ouvrirCora(cas.cible));
    el.append(titre, p);
    // patte avant : mesures de chaque radius complet (l'autre se choisit dans l'onglet CORA)
    const rad = (cas.candidats || []).filter((x) => x.os === "radius" && x.complet && x.mesures);
    if (rad.length) el.append(listeRadius(rad));
    el.append(b);
  } else {
    // radius analysé mais pas planifiable (cas qui ne devrait plus arriver : le radius se planifie dans l'onglet CORA)
    const radius = (cas.candidats || []).filter((x) => x.os === "radius" && x.complet);
    if (radius.length) {
      el.classList.remove("vide");
      titre.querySelector(".cc-lbl").textContent = "Patte avant (analyse du radius)";
      titre.querySelector("b").textContent = radius.map((x) => libelle(x.nom)).join(" et ");
      const note = document.createElement("p");
      note.className = "aide";
      note.textContent = "Repères et angles dans cora_radius_*.json et cora_radius_*.png (dossier des résultats).";
      el.append(titre, listeRadius(radius), note);
      return;
    }
    titre.querySelector("b").textContent = "aucun";
    el.append(titre, p);
  }
}

// mesures de chaque radius (étape 6) : courbure, procurvatum, valgus, torsion propre (tête radiale → surface carpienne)
function listeRadius(radius) {
  const deg = (v) => (v === null || v === undefined ? "?" : `${fmt(Math.abs(v), 0)}°`);
  const ul = document.createElement("ul");
  ul.className = "aide";
  for (const x of radius) {
    const m = x.mesures || {};
    const li = document.createElement("li");
    const t = m.torsion_deg;
    li.textContent = `${libelle(x.nom)} (${fmt(x.longueur_mm, 0)} mm) : courbure ${deg(m.courbure_3d_deg)} (procurvatum `
      + `${deg(m.procurvatum_deg)}, valgus ${deg(m.angulation_frontale_deg)}) ; torsion ${deg(t)} `
      + `${t === null || t === undefined ? "" : t >= 0 ? "externe" : "interne"} (normale : 3,6°)`;
    ul.append(li);
  }
  return ul;
}

function ouvrirCora(fichier) {
  parentMsg({ type: "cora-ouvrir", serie: E.serie.nom, os: fichier });
}

function viser(s) {
  if (!s?.centre_kji) return;
  E.point = s.centre_kji.map(Math.round);
  rafraichirCoupes();
  scene.reticule();
  infoPoint();
}

function selectionner(e, rafraichir = true) {
  E.selection = e;
  $$("#listeOs .os").forEach((el) => el.setAttribute("aria-selected", String(el.dataset.e.split(",").map(Number).includes(e))));
  const s = E.serie?.segments.find((x) => x.etiquette === e);
  $("#blocSelection").hidden = !s;
  if (s) {
    $("#selTitre").textContent = s.libelle;
    $("#selCouleur").style.background = rgb(s.couleur);
    const freres = s.nom ? E.serie.segments.filter((x) => x.nom === s.nom) : [s];
    $("#selRaison").textContent = (s.raison ? `Pourquoi : ${s.raison}.` : "") + (freres.length > 1 ?
      ` Ce segment fait partie de « ${s.libelle} » (${freres.length} segments, ${fmt(freres.reduce((a, x) => a + x.volume_cm3, 0), 1)} cm³ au total).` : "");
    const m = s.fichier ? E.serie.os?.[s.fichier] : null;
    const sens = m?.sensibilite_seuil;
    $("#selMesures").innerHTML = [
      `<span>Segment n° <span class="chiffre">${s.etiquette}</span> · volume <span class="chiffre">${fmt(s.volume_cm3, 2)} cm³</span> (voxels ≥ seuil)</span>`,
      m ? `<span>Fichier <b>${s.fichier}.stl</b> : <span class="chiffre">${fmt(m.volume_cm3, 2)} cm³</span> plein, ${m.triangles} triangles</span>` : "",
      m ? `<span>${m.etanche && m.orientation_coherente ? '<span class="ok">étanche</span>' : '<span class="critique">non étanche</span>'} · ${m.morceaux} morceau(x) · Euler ${m.euler}</span>` : "",
      sens ? `<span>Seuil ± 50 HU : écart moyen <span class="chiffre">${fmt(sens.moins.ecart_absolu_moyen_mm, 2)} / ${fmt(sens.plus.ecart_absolu_moyen_mm, 2)} mm</span>, P95 <span class="chiffre">${fmt(sens.moins.ecart_p95_mm, 2)} / ${fmt(sens.plus.ecart_p95_mm, 2)} mm</span></span>` : "",
      !s.fichier && s.nom && !["autre", "objet"].includes(base(s.nom)) ? `<span>Exporté dans le groupe <b>${base(s.nom) === "tarse" ? "tarse.stl" : "n.d."}</b></span>` : "",
      !s.nom ? `<span class="attention">Non exporté : donnez-lui un nom s'il vous est utile.</span>` : "",
    ].filter(Boolean).join("");
    const [b, cote] = (s.nom || "autre").split("_");
    $("#selNom").value = E.config.noms.includes(b) ? b : "autre";
    $("#selCote").value = cote || "";
    const bc = $("#btnCora");
    bc.hidden = !(INTEGRE && s.fichier && osCora(s.fichier) && E.serie.cora?.[s.fichier]?.complet !== false);
    bc.onclick = () => ouvrirCora(s.fichier);
  }
  if (rafraichir) { rafraichirCoupes(); scene.surligner(); }
}

function afficherFichiers() {
  const d = E.serie, ul = $("#listeFichiers");
  $("#blocFichiers").hidden = !d.fichiers.length;
  ul.innerHTML = "";
  const ordre = (f) => (f.endsWith(".stl") ? 0 : f.endsWith(".nrrd") ? 1 : f.endsWith(".md") ? 2 : f.endsWith(".png") ? 3 : 4);
  for (const f of [...d.fichiers].sort((a, b) => ordre(a) - ordre(b) || a.localeCompare(b))) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = `/res/${encodeURIComponent(f)}` + (/\.(png|md|json)$/.test(f) ? "" : "?telecharger=1");
    a.target = /\.(png|md|json)$/.test(f) ? "_blank" : "";
    a.textContent = f;
    const m = d.os?.[f.replace(/\.stl$/, "")];
    const t = document.createElement("span");
    t.className = "taille";
    t.textContent = m ? `${fmt(m.volume_cm3, 1)} cm³` : "";
    li.append(a, t);
    ul.append(li);
  }
  const g = d.graines || [];
  $("#nbGraines").textContent = g.length ? `(${g.length})` : "(aucun)";
  const lg = $("#listeGraines");
  lg.innerHTML = "";
  for (const p of g) {
    const li = document.createElement("li");
    li.textContent = `${libelle(p.nom)} : (${p.position.map((x) => fmt(x, 1)).join(" ; ")}) mm ${p.systeme || "LPS"}`;
    lg.append(li);
  }
  $("#btnOublier").disabled = !g.length;
}

function afficherReperes() {
  const r = E.serie.reperes || {};
  const cles = Object.keys(r);
  $("#blocReperes").hidden = !cles.length;
  $("#listeReperes").innerHTML = cles.map((k) => {
    const c = r[k].centre_lps;
    const nom = k.replace(/^tete_femorale/, "tête fémorale").replace(/_/g, " ");
    return `<span><b>${nom}</b> : centre (<span class="chiffre">${c.map((x) => fmt(x, 1)).join(" ; ")}</span>) mm, rayon <span class="chiffre">${fmt(r[k].rayon_mm, 1)} mm</span></span>
      <span class="aide">sphère ajustée sur l'interligne (${r[k].points} points, couverture ${fmt(100 * r[k].couverture, 0)} %) → reperes_auto.mrk.json</span>`;
  }).join("");
}

// ================================================================== vues en coupe
const LETTRES = (v) => {
  const a = v.map(Math.abs), m = a.indexOf(Math.max(...a));
  return [["G", "D"], ["P", "A"], ["S", "I"]][m][v[m] > 0 ? 0 : 1];
};

class VueCoupe {
  constructor(el) {
    this.el = el;
    this.plan = el.dataset.plan;
    this.canvas = $("canvas", el);
    this.ctx = this.canvas.getContext("2d");
    this.img = null;
    this.charge = null;       // requête en cours
    this.voulu = null;        // dernière image voulue
    this.zoom = 1; this.dx = 0; this.dy = 0;
    this.evenements();
    new ResizeObserver(() => this.dessiner()).observe(el);
  }
  reinitialiser() { this.zoom = 1; this.dx = 0; this.dy = 0; this.img = null; }
  // géométrie de l'image : largeur (colonnes), hauteur (lignes), taille d'un pixel (mm), nombre de coupes
  geo() {
    const [nk, nj, ni] = E.serie.dimensions, [dk, dj, di] = E.serie.espacement;
    if (this.plan === "a") return { w: ni, h: nj, sx: di, sy: dj, n: nk, idx: 0 };
    if (this.plan === "c") return { w: ni, h: nk, sx: di, sy: dk, n: nj, idx: 1 };
    return { w: nj, h: nk, sx: dj, sy: dk, n: ni, idx: 2 };
  }
  indice() { return E.point[this.geo().idx]; }
  // (colonne, ligne) de l'image <-> (k, j, i)
  versKji(col, ligne) {
    const nk = E.serie.dimensions[0], p = [...E.point];
    if (this.plan === "a") { p[1] = ligne; p[2] = col; }
    else if (this.plan === "c") { p[0] = nk - 1 - ligne; p[2] = col; }
    else { p[0] = nk - 1 - ligne; p[1] = col; }
    return p;
  }
  reticuleImage() {
    const [k, j, i] = E.point, nk = E.serie.dimensions[0];
    if (this.plan === "a") return [i, j];
    if (this.plan === "c") return [i, nk - 1 - k];
    return [j, nk - 1 - k];
  }
  cadre() {                   // position de l'image à l'écran (pixels CSS)
    const g = this.geo(), W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    const s = Math.min(W / (g.w * g.sx), (H - 20) / (g.h * g.sy)) * this.zoom;
    const w = g.w * g.sx * s, h = g.h * g.sy * s;
    return { x: (W - w) / 2 + this.dx, y: (H - h) / 2 + 10 + this.dy, w, h, g };
  }
  orienter() {
    const A = E.serie.affine, col = (n) => [A[0][n], A[1][n], A[2][n]], neg = (v) => v.map((x) => -x);
    let droite, bas;
    if (this.plan === "a") { droite = col(0); bas = col(1); }
    else if (this.plan === "c") { droite = col(0); bas = neg(col(2)); }
    else { droite = col(1); bas = neg(col(2)); }
    $(".lettre.d", this.el).textContent = LETTRES(droite);
    $(".lettre.g", this.el).textContent = LETTRES(neg(droite));
    $(".lettre.b", this.el).textContent = LETTRES(bas);
    $(".lettre.h", this.el).textContent = LETTRES(neg(bas));
  }
  demander() {
    if (!E.serie) return;
    const url = `/api/coupe?plan=${this.plan}&i=${this.indice()}&ww=${E.ww}&wl=${E.wl}&seg=${E.couleurs ? 1 : 0}&sel=${E.selection}&v=${E.version}`;
    this.voulu = url;
    if (this.charge) return;                      // une seule requête à la fois : la plus récente gagne
    this.charge = url;
    const img = new Image();
    img.onload = () => { this.img = img; this.charge = null; this.dessiner(); if (this.voulu !== url) this.demander(); };
    img.onerror = () => { this.charge = null; };
    img.src = url;
    $("[data-indice]", this.el).textContent = `${this.indice() + 1} / ${this.geo().n}`;
  }
  dessiner() {
    const c = this.canvas, dpr = window.devicePixelRatio || 1;
    const W = c.clientWidth, H = c.clientHeight;
    if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
    const x = this.ctx;
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.clearRect(0, 0, W, H);
    if (!E.serie || !this.img) return;
    const f = this.cadre();
    x.imageSmoothingEnabled = this.zoom < 2.5;
    x.drawImage(this.img, f.x, f.y, f.w, f.h);
    // réticule (lignes des deux autres plans)
    const [ci, li] = this.reticuleImage();
    const px = f.x + (ci + 0.5) / f.g.w * f.w, py = f.y + (li + 0.5) / f.g.h * f.h;
    const couleurs = { a: ["#46c25f", "#e7b44a"], c: ["#e2574c", "#e7b44a"], s: ["#e2574c", "#46c25f"] }[this.plan];
    x.lineWidth = 1;
    x.globalAlpha = 0.75;
    x.strokeStyle = this.plan === "a" ? couleurs[1] : couleurs[1];       // ligne verticale
    x.beginPath(); x.moveTo(px, f.y); x.lineTo(px, py - 10); x.moveTo(px, py + 10); x.lineTo(px, f.y + f.h); x.stroke();
    x.strokeStyle = this.plan === "a" ? couleurs[0] : couleurs[0];       // ligne horizontale
    x.beginPath(); x.moveTo(f.x, py); x.lineTo(px - 10, py); x.moveTo(px + 10, py); x.lineTo(f.x + f.w, py); x.stroke();
    x.globalAlpha = 1;
    // points de la séparation en cours (dans cette coupe)
    if (E.separation) {
      for (const p of E.separation.points) {
        const sauve = E.point; E.point = p.kji;
        const [c2, l2] = this.reticuleImage(); E.point = sauve;
        if (p.kji[this.geo().idx] !== this.indice()) continue;
        const qx = f.x + (c2 + 0.5) / f.g.w * f.w, qy = f.y + (l2 + 0.5) / f.g.h * f.h;
        x.fillStyle = rgb(E.config.couleurs[p.nom] || [1, 1, 1]);
        x.strokeStyle = "#000";
        x.beginPath(); x.arc(qx, qy, 6, 0, 2 * Math.PI); x.fill(); x.stroke();
        x.fillStyle = "#fff"; x.font = "600 11px system-ui"; x.fillText(libelle(p.nom), qx + 9, qy + 4);
      }
    }
  }
  pixelSous(ev) {
    const f = this.cadre(), r = this.canvas.getBoundingClientRect();
    const col = Math.floor((ev.clientX - r.left - f.x) / f.w * f.g.w), ligne = Math.floor((ev.clientY - r.top - f.y) / f.h * f.g.h);
    if (col < 0 || ligne < 0 || col >= f.g.w || ligne >= f.g.h) return null;
    return this.versKji(col, ligne);
  }
  evenements() {
    const c = this.canvas;
    c.addEventListener("wheel", (ev) => {
      if (!E.serie) return;
      ev.preventDefault();
      if (ev.ctrlKey || ev.metaKey) {             // zoom autour du curseur
        const r = c.getBoundingClientRect(), mx = ev.clientX - r.left - c.clientWidth / 2, my = ev.clientY - r.top - c.clientHeight / 2;
        const z = Math.min(Math.max(this.zoom * Math.exp(-ev.deltaY * 0.0025), 0.5), 25), k = z / this.zoom;
        this.dx = mx - (mx - this.dx) * k; this.dy = my - (my - this.dy) * k; this.zoom = z;
        this.dessiner();
        return;
      }
      const g = this.geo(), pas = (ev.deltaY > 0 ? -1 : 1) * (ev.shiftKey ? 5 : 1);
      E.point[g.idx] = Math.min(Math.max(E.point[g.idx] + pas, 0), g.n - 1);
      this.demander();
      for (const v of Object.values(vues)) if (v !== this) v.dessiner();
      scene.reticule();
      infoPointDiffere();
    }, { passive: false });
    let glisse = null;
    c.addEventListener("contextmenu", (ev) => ev.preventDefault());
    c.addEventListener("pointerdown", (ev) => {
      if (!E.serie) return;
      if (ev.button === 2 || ev.button === 1) { glisse = { x: ev.clientX, y: ev.clientY, dx: this.dx, dy: this.dy }; c.setPointerCapture(ev.pointerId); return; }
      const p = this.pixelSous(ev);
      if (!p) return;
      E.point = p;
      rafraichirCoupes();
      scene.reticule();
      cliquer(p);
    });
    c.addEventListener("pointermove", (ev) => {
      if (glisse) { this.dx = glisse.dx + ev.clientX - glisse.x; this.dy = glisse.dy + ev.clientY - glisse.y; this.dessiner(); return; }
      if (!E.serie) return;
      const p = this.pixelSous(ev);
      if (p) survol(p);
    });
    c.addEventListener("pointerup", () => { glisse = null; });
    c.addEventListener("dblclick", () => { this.reinitialiser(); this.demander(); });
  }
}

const vues = {};
function rafraichirCoupes() { for (const v of Object.values(vues)) v.demander(); }

let minuterieInfo, dernierSurvol = "";
function survol(p) {
  const cle = p.join(",");
  if (cle === dernierSurvol) return;
  dernierSurvol = cle;
  clearTimeout(minuterieInfo);
  minuterieInfo = setTimeout(async () => {
    try { afficherInfo(await lire(`/api/point?k=${p[0]}&j=${p[1]}&i=${p[2]}`)); } catch (e) { /* rien */ }
  }, 60);
}
function infoPointDiffere() { clearTimeout(minuterieInfo); minuterieInfo = setTimeout(infoPoint, 120); }
async function infoPoint() {
  if (!E.serie) return;
  try { afficherInfo(await lire(`/api/point?k=${E.point[0]}&j=${E.point[1]}&i=${E.point[2]}`)); } catch (e) { /* rien */ }
}
function afficherInfo(r) {
  $("#stPosition").textContent = `Position : (${r.lps.map((x) => fmt(x, 1)).join(" ; ")}) mm LPS · voxel (${r.kji.join(", ")})`;
  $("#stHU").textContent = `HU : ${r.hu}`;
  $("#stOs").textContent = `Os : ${r.etiquette ? `${r.libelle} (n° ${r.etiquette})` : "n.d."}`;
}

async function cliquer(p) {
  let r;
  try { r = await lire(`/api/point?k=${p[0]}&j=${p[1]}&i=${p[2]}`); } catch (e) { return; }
  afficherInfo(r);
  if (E.separation) {
    if (r.etiquette !== E.separation.etiquette) return message("Placez le point à l'intérieur du segment à séparer (en surbrillance).", true);
    E.separation.points.push({ nom: $("#sepNom").value, kji: p });
    afficherSeparation();
    for (const v of Object.values(vues)) v.dessiner();
    return;
  }
  if (r.etiquette) selectionner(r.etiquette);
}

// ================================================================== séparation d'un segment
function debutSeparation() {
  if (!E.selection) return;
  E.separation = { etiquette: E.selection, points: [] };
  $("#zoneSeparer").hidden = false;
  $("#zoneRenommer").hidden = true;
  afficherSeparation();
  message("Choisissez un nom, puis cliquez dans l'os correspondant (dans une coupe).");
}
function finSeparation() {
  E.separation = null;
  $("#zoneSeparer").hidden = true;
  $("#zoneRenommer").hidden = false;
  for (const v of Object.values(vues)) v.dessiner();
}
function afficherSeparation() {
  const ul = $("#sepPoints");
  ul.innerHTML = "";
  E.separation.points.forEach((p, n) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="pastille-os"></span><span></span><button class="mini x" title="Retirer ce point">✕</button>`;
    li.children[0].style.background = rgb(E.config.couleurs[p.nom] || [1, 1, 1]);
    li.children[1].textContent = `${libelle(p.nom)} : voxel (${p.kji.join(", ")})`;
    li.children[2].addEventListener("click", () => { E.separation.points.splice(n, 1); afficherSeparation(); for (const v of Object.values(vues)) v.dessiner(); });
    ul.append(li);
  });
  $("#btnSepValider").disabled = new Set(E.separation.points.map((p) => p.nom)).size < 2;
}

// ================================================================== scène 3D
const scene = (() => {
  const canvas = $("#scene3d");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  // densité de pixels plafonnée à 2 : un écran 4K à 250 % (Windows) calculerait sinon 6 fois plus de pixels qu'à 100 %
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 0.9;
  const sc = new THREE.Scene();
  sc.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
  sc.environmentIntensity = 0.55;                          // os moins délavés (couleurs lisibles)
  const camera = new THREE.PerspectiveCamera(30, 1, 1, 20000);
  camera.up.set(0, 0, 1);                                   // z du scanner (S) vers le haut
  const lampe = new THREE.DirectionalLight(0xffffff, 1.1);
  camera.add(lampe); lampe.position.set(0.3, 0.6, 1);
  sc.add(camera);
  sc.add(new THREE.HemisphereLight(0xffffff, 0x3a4652, 0.35));
  const controles = new OrbitControls(camera, canvas);
  controles.enableDamping = true;
  const groupe = new THREE.Group(); sc.add(groupe);
  const plans = new THREE.Group(); sc.add(plans);
  const marque = new THREE.Mesh(new THREE.SphereGeometry(1.6, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  sc.add(marque);
  const objets = new Map();                                  // clé -> { mesh, etiquettes }
  let charge = "";

  // rendu À LA DEMANDE : une image seulement quand quelque chose change (souris, chargement, sélection, taille…), au
  // lieu de 60 images par seconde en permanence (processeur graphique, ventilateur et batterie au repos). Pendant
  // l'inertie de la rotation, update() signale que la caméra bouge encore : une image de plus, jusqu'à l'arrêt.
  let imageDemandee = false;
  function rendre() {
    if (imageDemandee) return;
    imageDemandee = true;
    requestAnimationFrame(() => {
      imageDemandee = false;
      controles.update();                       // déclenche « change » (donc une autre image) tant que la vue bouge
      renderer.render(sc, camera);
    });
  }
  controles.addEventListener("change", rendre);
  function taille() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    rendre();
  }
  new ResizeObserver(taille).observe(canvas);

  function lps(kji) {
    const A = E.serie.affine, [k, j, i] = kji;
    return new THREE.Vector3(A[0][0] * i + A[0][1] * j + A[0][2] * k + A[0][3], A[1][0] * i + A[1][1] * j + A[1][2] * k + A[1][3],
      A[2][0] * i + A[2][1] * j + A[2][2] * k + A[2][3]);
  }
  function geometrie(buf) {
    const h = new Uint32Array(buf, 0, 2), nv = h[0], nf = h[1];
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buf, 8, nv * 3), 3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, 8 + nv * 12, nf * 3), 1));
    g.computeVertexNormals();
    return g;
  }
  async function maillage(url) {
    if (!E.cache.has(url)) {
      const r = await fetch(url);
      if (!r.ok) throw new Error("maillage absent");
      E.cache.set(url, await r.arrayBuffer());
    }
    return geometrie(E.cache.get(url));
  }
  function vider() {
    for (const o of objets.values()) { groupe.remove(o.mesh); o.mesh.geometry.dispose(); o.mesh.material.dispose(); }
    objets.clear();
    for (const o of [...groupe.children]) groupe.remove(o);
    rendre();
  }
  async function charger(d) {
    const voirAutres = $("#voirAutres").checked;
    const cle = JSON.stringify([d.nom, d.version, voirAutres, d.segments.map((s) => [s.etiquette, s.nom, s.fichier])]);
    if (cle === charge) { surligner(); reticule(); return; }
    const premiere = !charge.startsWith(JSON.stringify([d.nom]).slice(0, -1));
    charge = cle;
    vider();
    $("#vide3d").hidden = d.segments.length > 0;
    // un objet par fichier STL (os nommés) ; les os du tarse « autres » et les non identifiés : maillage rapide
    const parFichier = new Map();
    for (const s of d.segments) {
      const b = base(s.nom);
      if (s.fichier && b !== "tarse") {
        if (!parFichier.has(s.fichier)) parFichier.set(s.fichier, { url: `/api/maillage?os=${s.fichier}&v=${d.version}`, segs: [] });
        parFichier.get(s.fichier).segs.push(s);
      } else if ((s.nom && !["autre", "objet"].includes(b)) || voirAutres) {
        parFichier.set(`e${s.etiquette}`, { url: `/api/maillage?e=${s.etiquette}&v=${d.version}`, segs: [s], rapide: true });
      }
    }
    await Promise.all([...parFichier.entries()].map(async ([k, o]) => {
      try {
        const g = await maillage(o.url);
        if (charge !== cle) return;
        const s = o.segs[0], estAutre = !s.nom || ["autre", "objet"].includes(base(s.nom));
        const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(...s.couleur), roughness: 0.62, metalness: 0,
          transparent: estAutre, opacity: estAutre ? 0.55 : 1 });
        const mesh = new THREE.Mesh(g, mat);
        mesh.userData = { etiquettes: o.segs.map((x) => x.etiquette) };
        objets.set(k, { mesh, etiquettes: mesh.userData.etiquettes });
        groupe.add(mesh);
      } catch (e) { /* maillage indisponible : ignoré */ }
    }));
    if (charge !== cle) return;
    for (const [nom, r] of Object.entries(d.reperes || {})) {     // tête fémorale : sphère ajustée
      const sp = new THREE.Mesh(new THREE.SphereGeometry(r.rayon_mm, 28, 18),
        new THREE.MeshBasicMaterial({ color: 0xff5b61, wireframe: true, transparent: true, opacity: 0.35 }));
      sp.position.set(...r.centre_lps);
      sp.userData = { etiquettes: [], repere: nom };
      groupe.add(sp);
    }
    if (premiere) recentrer();
    surligner();
    reticule();
  }
  function recentrer() {
    const boite = new THREE.Box3().setFromObject(groupe);
    if (boite.isEmpty()) {
      if (!E.serie) return;
      const [nk, nj, ni] = E.serie.dimensions;
      boite.setFromPoints([lps([0, 0, 0]), lps([nk - 1, nj - 1, ni - 1])]);
    }
    const c = boite.getCenter(new THREE.Vector3()), r = boite.getSize(new THREE.Vector3()).length() / 2;
    controles.target.copy(c);
    camera.position.copy(c).add(new THREE.Vector3(0, -1, 0.15).normalize().multiplyScalar(r / Math.tan(THREE.MathUtils.degToRad(15)) * 1.05));
    camera.near = r / 100; camera.far = r * 50; camera.updateProjectionMatrix();
    rendre();
  }
  function surligner() {
    for (const o of objets.values()) {
      const sel = o.etiquettes.includes(E.selection);
      o.mesh.material.emissive = new THREE.Color(sel ? 0x2a4a66 : 0x000000);
      o.mesh.visible = !o.etiquettes.every((e) => E.cachees.has(e));
    }
    rendre();
  }
  function reticule() {
    if (!E.serie) return;
    marque.position.copy(lps(E.point));
    for (const o of [...plans.children]) { plans.remove(o); o.geometry.dispose(); }
    plans.visible = $("#voirPlans").checked;
    const [nk, nj, ni] = E.serie.dimensions, [k, j, i] = E.point;
    const cadres = [[[k, 0, 0], [k, 0, ni - 1], [k, nj - 1, ni - 1], [k, nj - 1, 0], 0xe2574c],
      [[0, j, 0], [0, j, ni - 1], [nk - 1, j, ni - 1], [nk - 1, j, 0], 0x46c25f],
      [[0, 0, i], [0, nj - 1, i], [nk - 1, nj - 1, i], [nk - 1, 0, i], 0xe7b44a]];
    for (const [a, b, c, dd, couleur] of cadres) {
      const g = new THREE.BufferGeometry().setFromPoints([a, b, c, dd, a].map(lps));
      plans.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: couleur, transparent: true, opacity: 0.8 })));
    }
    rendre();
  }
  // clic dans la scène : sélection de l'os touché (sans déplacer la vue)
  const ray = new THREE.Raycaster();
  let appui = null;
  canvas.addEventListener("pointerdown", (ev) => { appui = [ev.clientX, ev.clientY]; });
  canvas.addEventListener("pointerup", async (ev) => {
    if (!appui || Math.hypot(ev.clientX - appui[0], ev.clientY - appui[1]) > 4 || !E.serie) return;
    const r = canvas.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2((ev.clientX - r.left) / r.width * 2 - 1, -(ev.clientY - r.top) / r.height * 2 + 1), camera);
    const touche = ray.intersectObjects(groupe.children.filter((m) => m.visible && m.userData.etiquettes?.length), false)[0];
    if (!touche) return;
    const p = touche.point;
    try {
      const info = await lire(`/api/point?x=${p.x}&y=${p.y}&z=${p.z}`);
      afficherInfo(info);
      if (info.etiquette) {
        selectionner(info.etiquette);
        E.point = info.kji;
        rafraichirCoupes(); reticule();
      }
    } catch (e) { /* rien */ }
  });
  return { charger, recentrer, surligner, reticule, vider, theme: rendre };
})();

// ================================================================== démarrage
async function demarrer() {
  E.config = await lire("/api/config");
  const r = E.config.reglages;
  $("#rSeuil").value = r.SEUIL_OS_HU; $("#rSigma").value = r.SIGMA_LISSAGE_MM; $("#rFermeture").value = r.RAYON_FERMETURE_MM;
  $("#rTriangles").value = r.TRIANGLES_MAX; $("#rSysteme").value = r.SYSTEME_COORDONNEES;
  for (const sel of [$("#selNom"), $("#sepNom")]) {
    sel.innerHTML = E.config.noms.map((n) => `<option value="${n}">${n === "autre" ? "autre (non exporté)" : n === "objet" ? "objet non osseux" : E.config.libelles[n]}</option>`).join("");
  }
  $("#sepNom").value = "talus";
  for (const el of $$(".vue[data-plan]")) if (el.dataset.plan !== "3d") vues[el.dataset.plan] = new VueCoupe(el);

  $("#btnSegmenter").addEventListener("click", () => action("segmenter", {
    reglages: { SEUIL_OS_HU: +$("#rSeuil").value, SIGMA_LISSAGE_MM: +$("#rSigma").value, RAYON_FERMETURE_MM: +$("#rFermeture").value,
      TRIANGLES_MAX: +$("#rTriangles").value, SYSTEME_COORDONNEES: $("#rSysteme").value },
    controle: $("#rControle").checked, images: $("#rImages").checked }));
  $("#btnChoisir").addEventListener("click", async () => {
    try {
      const r = await envoyer("/api/choisir_dossier");
      if (r.chemin) action("inventaire", { chemin: r.chemin });
    } catch (e) { message(e.message, true); }
  });
  $("#btnRelire").addEventListener("click", () => action("inventaire", { chemin: $("#dossierDicom").textContent }));
  $("#btnDossierResultats").addEventListener("click", () => envoyer("/api/montrer").catch((e) => message(e.message, true)));
  $("#btnRenommer").addEventListener("click", () => {
    if (!E.selection) return;
    const sous = E.point;
    action("nommer", { etiquette: E.selection, nom: $("#selNom").value, cote: $("#selCote").value, kji: sous });
  });
  $("#btnSeparer").addEventListener("click", debutSeparation);
  $("#btnSepAnnuler").addEventListener("click", finSeparation);
  $("#btnSepValider").addEventListener("click", () => {
    const s = E.separation;
    finSeparation();
    action("separer", { etiquette: s.etiquette, points: s.points });
  });
  $("#btnOublier").addEventListener("click", () => { if (confirm("Effacer tous les points nommés de cette série ?")) action("oublier"); });
  $$("#segFenetre button").forEach((b) => b.addEventListener("click", () => {
    $$("#segFenetre button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    E.ww = +b.dataset.ww; E.wl = +b.dataset.wl;
    rafraichirCoupes();
  }));
  $("#voirCouleurs").addEventListener("change", (ev) => { E.couleurs = ev.target.checked; rafraichirCoupes(); });
  $("#voirAutres").addEventListener("change", () => E.serie && scene.charger(E.serie));
  $("#voirPlans").addEventListener("change", () => scene.reticule());
  $("#btnRecentrer").addEventListener("click", () => scene.recentrer());
  $$("[data-agrandir]").forEach((b) => b.addEventListener("click", () => {
    const vue = b.closest(".vue"), deja = vue.classList.contains("grande");
    $$(".vue").forEach((v) => v.classList.remove("grande"));
    $("#vues").classList.toggle("agrandie", !deja);
    if (!deja) vue.classList.add("grande");
  }));
  $("#btnAide").addEventListener("click", () => $("#aide").showModal());
  $("#btnTheme").addEventListener("click", () => {
    const clair = document.documentElement.dataset.theme !== "light";
    document.documentElement.dataset.theme = clair ? "light" : "dark";
    try { localStorage.setItem("theme-ct", clair ? "light" : "dark"); } catch (e) { /* stockage indisponible */ }
  });
  try { if (localStorage.getItem("theme-ct") === "light") document.documentElement.dataset.theme = "light"; } catch (e) { /* rien */ }
  if (INTEGRE) {
    document.body.classList.add("integre");
    window.addEventListener("message", (ev) => {
      const m = ev.data || {};
      if (m.type === "theme") { document.documentElement.dataset.theme = m.theme; scene.theme(); rafraichirCoupes(); }
      else if (m.type === "visible") { window.dispatchEvent(new Event("resize")); }
    });
  }
  $("#btnQuitter").addEventListener("click", async () => {
    if (E.enCours && !confirm("Un calcul est en cours. Quitter quand même ?")) return;
    await envoyer("/api/quitter").catch(() => {});
    document.body.innerHTML = `<div class="vide" style="position:fixed">Application arrêtée. Vous pouvez fermer cette fenêtre.</div>`;
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && E.separation) finSeparation();
  });
  setInterval(() => envoyer("/api/ping").catch(() => {}), 15000);
  suivre();
}
demarrer().catch((e) => message("Démarrage impossible : " + e.message, true));
