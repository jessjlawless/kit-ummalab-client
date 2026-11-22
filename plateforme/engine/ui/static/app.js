/* Content Engine, dashboard local (vanilla JS, aucune étape de build) */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ic = (n, cls = "") => `<i data-lucide="${n}"${cls ? ` class="${cls}"` : ""}></i>`;
const icons = () => window.lucide && window.lucide.createIcons();
const ACC = { personal: "Mon compte" };
const ACC_COLOR = { personal: "var(--pb)" };
const STATUS = { planned: ["Planifiée", "circle-dashed"], filmed: ["Filmée", "video"], published: ["Publiée", "send"] };
const FUNNEL = { tofu: ["Notoriété", "TOFU"], mofu: ["Confiance", "MOFU"], bofu: ["Conversion", "BOFU"] };
const PLAT = { instagram: "Instagram", tiktok: "TikTok", youtube: "YouTube" };
const DRIVER = { celebrity: "célébrité", celebrite: "célébrité", "célébrité": "célébrité", personality: "personnalité", trend: "tendance",
  trending_audio: "son tendance", humor: "humour", humour: "humour", luck: "chance", algorithm: "algorithme", news: "actualité",
  controversy: "controverse", production: "production", animal: "animal", cute: "mignonnerie", shock: "choc" };
const lsGet = (k, d) => { try { return localStorage.getItem(k) || d; } catch (_) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };
const ISL = () => !!state.overview?.islamic;  // règles islamiques (config/identity.yaml → islamic_rules)
const state = { view: "today", overview: null, weekStart: null, day: null, discFilter: "all", discValid: true, ctxFile: null, videos: {},
  jobs: [], regenBusy: {}, calMode: lsGet("ce-cal-mode", "week"), calDay: null, calAnim: false, discRows: [], broll: null, brollFilter: lsGet("ce-broll-filter", "todo"),
  hl: null, hlCreator: "all", hlCh: lsGet("ce-hl-ch", "all"), hlSort: lsGet("ce-hl-sort", "strength"), hlRepl: lsGet("ce-hl-repl", "0") === "1", hlRailX: 0 };

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (!r.ok) {
    let msg = await r.text();
    try { const d = JSON.parse(msg).detail; msg = typeof d === "string" ? d : d ? JSON.stringify(d) : msg; } catch (_) {}
    const err = new Error(r.status === 404 && /not found/i.test(msg)
      ? "Cette fonction arrive : le serveur est en cours de mise à jour. Réessaie dans quelques minutes." : String(msg).slice(0, 300));
    err.status = r.status;
    throw err;
  }
  return r.json();
}
/* lecture tolérante : renvoie `fallback` si l'endpoint n'existe pas encore ou échoue */
const soft = (path, fallback = null) => api(path).catch(() => fallback);
function toast(msg, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.setAttribute("role", err ? "alert" : "status");
  t.innerHTML = `<span class="t-ico">${ic(err ? "circle-alert" : "circle-check")}</span><span class="t-msg">${esc(msg)}</span>`;
  $("#toasts").appendChild(t);
  icons();
  setTimeout(() => t.classList.add("out"), 4200);
  setTimeout(() => t.remove(), 4600);
}
const fmtDate = (iso, long = false) => new Date(iso + "T12:00:00").toLocaleDateString("fr-FR",
  long ? { weekday: "long", day: "numeric", month: "long" } : { day: "2-digit", month: "2-digit" });
const wday = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "short" }).replace(".", "");
const dnum = (iso) => new Date(iso + "T12:00:00").getDate();
const monthLabel = (a, b) => {
  const f = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
  return f(a) === f(b) ? f(a) : `${f(a).split(" ")[0]}, ${f(b)}`;
};
const cap = (s) => String(s || "").charAt(0).toUpperCase() + String(s || "").slice(1);
const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
const num = (n) => (n == null ? "-" : Number(n).toLocaleString("fr-FR"));
const compact = (n) => (n == null ? "-" : Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 }).format(n));
const fills = (s) => esc(s).replace(/\[([^\]]{2,160})\]/g, '<span class="fill">[$1]</span>');
const ytId = (url) => (String(url || "").match(/(?:shorts\/|v=|youtu\.be\/)([\w-]{6,})/) || [])[1];
const thumb = (url) => (ytId(url) ? `https://i.ytimg.com/vi/${ytId(url)}/hqdefault.jpg` : "");
const platName = (p) => PLAT[String(p || "").toLowerCase()] || p || "";
const PLAT_ICON = { instagram: "instagram", tiktok: "music-2", youtube: "youtube" };
const phIcon = (p) => `<span class="ph-icon" aria-hidden="true">${ic(PLAT_ICON[String(p || "").toLowerCase()] || "film")}</span>`;
const setupShort = (s) => String(s || "").split("-")[0].trim();
const setupRest = (s) => String(s || "").split("-").slice(1).join("-").trim();
const funnelPill = (s) => (FUNNEL[s] ? `<span class="fpill ${s}" title="${FUNNEL[s][1]}"><span class="fdot ${s}"></span>${FUNNEL[s][0]}</span>` : "");
const score10 = (v) => (v == null || v === "" || isNaN(+v) ? null : `${Math.round(+v * 10) / 10}/10`);
const driverNote = (d) => (d && String(d).toLowerCase() !== "technique"
  ? `<p class="driver-note">${ic("info")}Succès lié à : ${esc(DRIVER[String(d).toLowerCase()] || String(d).replaceAll("_", " "))}</p>` : "");
const segVars = (i, n) => `style="--i:${Math.max(i, 0)};--n:${n}"`;
const todayIso = () => state.overview?.today || new Date().toISOString().slice(0, 10);
const daysBetween = (a, b) => Math.round((new Date(b + "T12:00:00") - new Date(a + "T12:00:00")) / 864e5);
const mondayOf = (iso) => { const d = new Date(iso + "T12:00:00"); return addDays(iso, -((d.getDay() + 6) % 7)); };
const plural = (n, w, p = w + "s") => `${n} ${n > 1 ? p : w}`;
/* vignette : toujours la miniature servie par le serveur quand on a un id vidéo */
const refThumb = (r) => (r ? r.thumb_url || (r.video_id ? `/api/thumb/${r.video_id}` : thumb(r.url)) : "");
const refMedia = (r) => (!r ? null : r.media_url !== undefined ? r.media_url : r.video_id ? `/api/media/${r.video_id}` : null);
const thumbImg = (src, alt = "") => (src ? `<img class="th-img" src="${esc(src)}" alt="${esc(alt)}" loading="lazy" decoding="async">` : "");
/* défi : normalise l'ancien et le nouveau format de /api/overview */
function challenge() {
  const o = state.overview || {}, c = o.challenge || {};
  const start = c.start_date !== undefined ? c.start_date : o.challenge_start || null;
  // « scheduled » = date choisie mais dans le futur : on le traite comme lancé (compte à rebours)
  const started = !!start && (c.started !== undefined ? !!(c.started || c.scheduled || start > todayIso()) : true);
  const len = c.length || o.challenge_length || 90;
  let day = c.day_number !== undefined ? c.day_number : o.day_number;
  if (started && start && day == null) day = daysBetween(start, todayIso()) + 1;
  return { started, start, len, day: started ? day : null, objectif: c.objectif || o.objectif || "", upcoming: started && start && todayIso() < start };
}
const dayNumberOf = (iso) => { const c = challenge(); if (!c.started || !c.start) return null; const n = daysBetween(c.start, iso) + 1; return n >= 1 && n <= c.len ? n : null; };
/* erreur d'image : on retombe proprement sur le placeholder */
document.addEventListener("error", (ev) => {
  const t = ev.target;
  if (t && t.tagName === "IMG" && t.classList.contains("th-img")) { t.closest(".thumb, .vt-ref, .pl-poster")?.classList.add("no-img"); t.remove(); }
}, true);

/* ------------------------------------------------------------ thème */
const THEME_KEY = "ce-theme-v2";
function setTheme(t, animate = false) {
  const root = document.documentElement;
  if (animate) { root.classList.add("theme-anim"); setTimeout(() => root.classList.remove("theme-anim"), 400); }
  root.dataset.theme = t;
  $('meta[name="theme-color"]')?.setAttribute("content", t === "dark" ? "#000000" : "#f5f5f7");
  try { localStorage.setItem(THEME_KEY, t); } catch (_) {}
  const b = $("#theme-toggle");
  if (b) { b.innerHTML = `${ic(t === "dark" ? "sun" : "moon")}<span>${t === "dark" ? "Mode clair" : "Mode sombre"}</span>`; icons(); }
}
try { setTheme(localStorage.getItem(THEME_KEY) || "light"); } catch (_) { setTheme("light"); }
$("#theme-toggle").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true);

/* ------------------------------------------------------------ tâches */
const watched = new Set();
function track(j, msg) {
  if (!j || !j.id) return;
  watched.add(j.id);
  if (j.kind?.startsWith("regen:")) state.regenBusy[j.kind.slice(6)] = j.id;
  toast(msg || `${j.label || "Tâche"} lancé`);
  pollJobs();
}
async function runJob(kind, payload = {}) {
  try { track(await api(`/api/run/${kind}`, { method: "POST", body: payload })); }
  catch (e) { toast(e.message, true); }
}
window.runJob = runJob;
const isRunning = (j) => j.status === "running";
function paintPill(running) {
  const pill = $("#jobs-pill");
  pill.classList.toggle("hidden", !running.length);
  const j = running[0];
  const html = j ? `<button class="jp-main" data-go="system" title="Voir les tâches"><span class="spin"></span><span class="jp-lbl">${esc(j.label)}</span>${running.length > 1 ? `<span class="jp-more">+${running.length - 1}</span>` : ""}</button>
    <button class="jp-stop" data-stop-job="${esc(j.id)}" aria-label="Arrêter « ${esc(j.label)} »" title="Arrêter « ${esc(j.label)} »">${ic("square")}<span>Stop</span></button>` : "";
  if (pill.dataset.html !== html) { pill.dataset.html = html; pill.innerHTML = html; icons(); }
}
let polling = false;
async function pollJobs() {
  if (polling) return;
  polling = true;
  try {
    while (true) {
      const jobs = await api("/api/jobs");
      state.jobs = jobs;
      const running = jobs.filter(isRunning);
      paintPill(running);
      // cartes en cours de régénération (y compris celles lancées avant un rechargement)
      const busy = {};
      running.filter((j) => String(j.kind).startsWith("regen:")).forEach((j) => (busy[j.kind.slice(6)] = j.id));
      const ended = Object.keys(state.regenBusy).filter((c) => !busy[c]);
      const added = Object.keys(busy).filter((c) => !state.regenBusy[c]);
      state.regenBusy = busy;
      ended.forEach((c) => onRegenerated(c));
      added.forEach((c) => state.videos[c] && replaceCard(c, state.videos[c]));
      let refresh = false;
      for (const j of jobs) {
        if (watched.has(j.id) && !isRunning(j)) {
          watched.delete(j.id);
          if (j.status === "stopped") toast(`${j.label}, arrêtée`);
          else toast(j.status === "done" ? `${j.label}, terminé` : `${j.label} : ${j.error || "erreur"}`, j.status !== "done");
          if (!String(j.kind).startsWith("regen:")) refresh = true;
        }
      }
      if (refresh) { await refreshOverview(); render(true); }
      if (!running.length && !watched.size) break;
      await new Promise((r) => setTimeout(r, 2000));
    }
  } catch (_) { /* serveur indisponible : on réessaiera au prochain tick */ }
  finally { polling = false; }
}
/* tick léger : détecte aussi les pipelines lancés depuis le terminal (external) */
setInterval(() => { if (!polling && document.visibilityState !== "hidden") pollJobs(); }, 15000);
async function stopJob(id) {
  const j = state.jobs.find((x) => x.id === id) || { id, label: "cette tâche", kind: "" };
  if (!String(j.kind).startsWith("regen:") && !confirm(`Arrêter « ${j.label} » ?${j.external ? "\n(Pipeline lancé depuis le terminal.)" : ""}`)) return;
  try {
    await api(`/api/jobs/${encodeURIComponent(id)}/stop`, { method: "POST" });
    if (!watched.has(id)) toast(`${j.label}, arrêtée`);
    $$(`[data-stop-job="${id}"]`).forEach((b) => (b.disabled = true));
    setTimeout(async () => { await pollJobs(); await refreshOverview(); render(true); }, 400);
  } catch (e) { toast(e.message, true); }
}
document.addEventListener("click", (ev) => {
  const s = ev.target.closest("[data-stop-job]");
  if (s) { ev.preventDefault(); ev.stopPropagation(); return stopJob(s.dataset.stopJob); }
  const g = ev.target.closest("[data-go]");
  if (g) { ev.preventDefault(); closeOverlays(); if (g.dataset.goDay) state.day = g.dataset.goDay; return go(g.dataset.go); }
  const c = ev.target.closest("[data-challenge]");
  if (c) { ev.preventDefault(); return c.dataset.challenge === "reset" ? resetChallenge() : openChallengeSheet(); }
}, true);
$$("[data-run]").forEach((b) => (b.onclick = () => runJob(b.dataset.run)));

/* ------------------------------------------------------------ défi */
async function refreshOverview() {
  try { state.overview = await api("/api/overview"); paintChallenge(); } catch (_) {}
}
function paintChallenge() {
  const c = challenge(), el = $("#challenge");
  if (!el) return;
  const obj = c.objectif && !String(c.objectif).includes("À_REMPLIR") ? `<p>Objectif : ${esc(c.objectif)}.</p>` : "";
  if (!c.started) {
    el.innerHTML = `<div class="lbl">Défi ${c.len} jours</div><div class="big pre">Défi pas encore lancé</div>${obj}
      <button class="btn primary small ch-go" data-challenge="start">${ic("flag")}Lancer le défi</button>`;
  } else if (c.upcoming) {
    const n = daysBetween(todayIso(), c.start);
    el.innerHTML = `<div class="lbl">Défi ${c.len} jours</div><div class="big">J-${n}<small> avant le Jour 1</small></div>
      <div class="bar"><i style="width:2%"></i></div><p>Jour 1 : ${esc(fmtDate(c.start, true))}. Prépare tes B-rolls d'ici là.</p>`;
  } else {
    const d = Math.min(Math.max(c.day || 1, 1), c.len), pct = Math.round((d / c.len) * 100);
    el.innerHTML = `<div class="lbl">Défi ${c.len} jours</div><div class="big">Day ${d}<small> sur ${c.len}</small></div>
      <div class="bar"><i style="width:${Math.max(pct, 2)}%"></i></div>${obj}`;
  }
  icons();
}
function nextMonday(iso) { const d = new Date(iso + "T12:00:00"); const k = (8 - d.getDay()) % 7 || 7; return addDays(iso, k); }
function openChallengeSheet() {
  const c = challenge(), t = todayIso();
  const nm = nextMonday(t), dup = nm === addDays(t, 1);
  const chips = [["Aujourd'hui", t], ["Demain", addDays(t, 1)], dup ? ["Lundi suivant", addDays(nm, 7)] : ["Lundi prochain", nm]];
  let val = c.started && c.start ? c.start : t;
  $("#modal-card").innerHTML = `<div class="sheet-head"><span class="sheet-code">Défi ${c.len} jours</span>
      <button class="btn icon small" data-close aria-label="Fermer">${ic("x")}</button></div>
    <h2>${c.started ? "Changer la date du défi" : "Lancer le défi"}</h2>
    <p class="sub">Choisis ton Jour 1. Tu peux le changer plus tard.</p>
    <div class="date-chips" role="group" aria-label="Raccourcis">${chips.map(([l, d]) => `<button data-d="${d}"><b>${l}</b><small>${esc(cap(fmtDate(d, true)))}</small></button>`).join("")}</div>
    <label class="field-label" for="ch-date">Date du Jour 1</label>
    <div class="date-row"><span class="date-ico">${ic("calendar")}</span><input id="ch-date" type="date" value="${val}" min="${addDays(t, -60)}"></div>
    <div class="ch-preview" id="ch-preview"></div>
    <label class="verify ch-regen"><span>Régénérer le calendrier perso</span><input type="checkbox" class="switch" id="ch-regen" checked></label>
    <p class="hint">${ic("info")}Le calendrier perso sera régénéré à partir de cette date (Jour 1 = cette date). ~15 min avec Claude.</p>
    <div class="sheet-actions"><button class="btn ghost" data-close>Annuler</button>
      <button class="btn primary" id="ch-go">${ic("flag")}${c.started ? "Enregistrer" : "Lancer le défi"}</button></div>`;
  openModal("sheet-challenge");
  icons();
  const input = $("#ch-date");
  const paint = () => {
    val = input.value;
    $$(".date-chips button").forEach((b) => b.classList.toggle("on", b.dataset.d === val));
    $("#ch-preview").innerHTML = val ? `<span><b>Jour 1</b>${esc(cap(fmtDate(val, true)))}</span><span class="sep"></span>
      <span><b>Jour ${c.len}</b>${esc(cap(fmtDate(addDays(val, c.len - 1), true)))}</span>` : "";
  };
  input.oninput = paint;
  $$(".date-chips button").forEach((b) => (b.onclick = () => { input.value = b.dataset.d; paint(); }));
  paint();
  $("#ch-go").onclick = async () => {
    if (!val) return input.focus();
    const btn = $("#ch-go");
    btn.disabled = true;
    try {
      const j = await api("/api/challenge/start", { method: "POST", body: { date: val, regenerate: $("#ch-regen").checked } });
      closeOverlays();
      if (j && j.id) track(j, `Défi lancé : Jour 1 le ${fmtDate(val, true)}. Calendrier en cours…`);
      else toast(`Défi lancé : Jour 1 le ${fmtDate(val, true)}`);
      await refreshOverview();
      render(true);
    } catch (e) { btn.disabled = false; toast(e.message, true); }
  };
}
async function resetChallenge() {
  if (!confirm("Réinitialiser le défi ?\nIl repasse en « pas encore lancé ». Tes vidéos ne sont pas supprimées.")) return;
  try { await api("/api/challenge/reset", { method: "POST" }); toast("Défi réinitialisé"); await refreshOverview(); render(true); }
  catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------------ carte vidéo */
function refStats(r) {
  const parts = [score10(r.replicability) && `Réplicable ${score10(r.replicability)}`, score10(r.hook_strength) && `Hook ${score10(r.hook_strength)}`,
    r.platform && platName(r.platform)].filter(Boolean);
  return (parts.length || FUNNEL[r.funnel_stage] ? `<p class="ref-stats">${funnelPill(r.funnel_stage)}${parts.length ? `<span>${esc(parts.join(" · "))}</span>` : ""}</p>` : "")
    + driverNote(r.success_driver);
}
function refBlock(ref) {
  if (!ref) return `<div class="ref empty"><span class="ref-empty-ico">${ic("film")}</span><p>Pas encore de vidéo source : lance la veille.</p></div>`;
  const t = refThumb(ref);
  return `<div class="ref"><a class="thumb${t ? "" : " no-img"}" href="${esc(ref.url)}" target="_blank" rel="noopener" data-act="ref" aria-label="Voir la vidéo de référence : ${esc(ref.title || "")}">
      ${phIcon(ref.platform)}${thumbImg(t)}<span class="tag">${ic("flame")}A marché</span><span class="play">${ic("play")}</span>
      <span class="over"><b>${esc(ref.title || "Vidéo de référence")}</b>${ref.channel ? `<small>@${esc(ref.channel)}</small>` : ""}</span></a>
    ${refStats(ref)}${ref.why ? `<p class="why">${esc(ref.why)}</p>` : ""}</div>`;
}
function ideaBlock(e) {
  const i = e.big_idea;
  if (!i) return "";
  return `<div class="citation"><div class="head">${ic("lightbulb")}Grande idée reprise</div><q>${esc(i.idea)}</q>
    <div class="cit-links"><a href="${esc(i.url)}" target="_blank" rel="noopener">Vidéo longue : ${esc(i.title || "")}</a> · ${esc(i.channel || "")}${i.score ? ` · x${i.score}` : ""}</div></div>`;
}
function citationBlock(e) {
  const c = e.citation;
  if (!c) return "";
  if (c.status === "citation à ajouter")
    return `<div class="citation"><div class="head">${ic("book-open")}Rappel · citation à ajouter</div>
      <q>Aucune source vérifiée trouvée (idée : ${esc(c.idea)}). Ne cite rien de mémoire.</q></div>`;
  return `<div class="citation"><div class="head">${ic("book-open")}${esc(c.reference)}</div>
    ${c.arabic ? `<div class="ar" lang="ar">${esc(c.arabic)}</div>` : ""}<q>${esc(c.translation || c.french || c.text)}</q>
    <div class="cit-links"><a href="${esc(c.url)}" target="_blank" rel="noopener">Source</a>${c.source_url ? ` · <a href="${esc(c.source_url)}" target="_blank" rel="noopener">JSON</a>` : ""}</div>
    <label class="verify"><span>J'ai vérifié avec la source</span><input type="checkbox" class="switch" data-act="verify" ${e.citation_verified ? "checked" : ""}></label></div>`;
}
function videoCard(e, i = 0) {
  state.videos[e.code] = e;
  const done = new Set(e.shots_done || []);
  const shots = e.shots || [];
  const total = shots.length || 1;
  const h0 = e.hooks?.[0] || {};
  const warn = (e.ethics_flags || []).length;
  // 2-3 pastilles max : compte, entonnoir, puis le signal le plus important
  const flag = warn ? `<span class="badge warn">${ic("triangle-alert")}À relire</span>`
    : e.slot_type === "test" ? `<span class="badge test">${ic("flask-conical")}Format test</span>`
    : e.is_rappel ? `<span class="badge rappel">${ic("moon-star")}Rappel</span>`
    : e.campaign ? `<span class="badge campaign" title="${esc(e.campaign.title)}">${ic("megaphone")}${esc(CAMP_SHORT[e.campaign.type] || "Campagne")}</span>` : "";
  const meta = [
    e.campaign ? e.campaign.title : e.slot_type !== "test" ? "Format éprouvé" : warn ? "Format test" : "",
    e.is_rappel && (warn || e.slot_type === "test") ? "Rappel" : "",
    e.episode_label, e.format?.name || e.format?.id,
    e.format?.source_niche ? `emprunté à ${e.format.source_niche}` : "",
    setupShort(e.setup_label || e.setup),
  ].filter(Boolean);
  const stIdx = Object.keys(STATUS).indexOf(e.status);
  const row = (icon, label, val) => `<div class="row"><span class="row-l">${ic(icon)}${label}</span><span class="row-v">${esc(val || "-")}</span></div>`;
  const busyId = state.regenBusy[e.code];
  return `<article class="card ${e.account} is-${e.status}${busyId ? " busy" : ""}" data-code="${e.code}" style="animation-delay:${Math.min(i, 12) * 30}ms">
    ${busyId ? `<div class="busy-bar" role="status"><span class="spin"></span><span>Régénération avec Claude…</span>
      <button class="btn small danger" data-stop-job="${esc(busyId)}">${ic("square")}Arrêter</button></div>` : ""}
    <div class="main">
      <header class="card-head"><div class="badges"><span class="badge ${e.account}">${ACC[e.account] || e.account}</span>${funnelPill(e.funnel_stage)}${flag}</div>
        <span class="code">${esc(e.code)}</span></header>
      <h3 class="subject">${esc(e.subject)}</h3>
      <p class="meta-line">${meta.map(esc).join(" · ")}</p>
      <div class="hooks">${(e.hooks || []).map((h) => { const used = e.hook_used === h.variant;
        return `<div class="hook ${used ? "used" : ""}" data-act="hook" data-v="${h.variant}" tabindex="0" role="button" aria-pressed="${used}">
        <div class="h-top"><span class="v">${used ? ic("check") : ""}Hook ${h.variant}${used ? " · utilisé" : ""}</span>
        <button class="copy" data-act="copy" data-text="${esc(h.verbal)}" aria-label="Copier le hook ${h.variant}" title="Copier">${ic("copy")}</button></div>
        <p>${esc(h.verbal)}</p></div>`; }).join("")}</div>
      <div class="rows">${row("type", "Texte écran", h0.text_on_screen)}${row("scan-eye", "1re seconde", h0.visual)}${row("megaphone", "CTA", e.cta?.text)}</div>
      <div class="checklist">
        <div class="cl-head"><h4>Plans à filmer</h4><span class="cl-count">${done.size} sur ${shots.length}</span>
          <span class="progress-mini" aria-hidden="true"><i style="transform:scaleX(${done.size / total})"></i></span></div>
        <ul class="shots">${shots.map((s, k) => `<li class="${done.has(k) ? "on" : ""}" data-act="shot" data-i="${k}" role="checkbox" tabindex="0" aria-checked="${done.has(k)}">
          <span class="box" aria-hidden="true">${ic("check")}</span><span class="shot-t">${esc(s)}</span></li>`).join("")}</ul></div>
      ${e.campaign?.notes ? `<div class="camp-notes"><h4>${ic("clipboard-list")}À préparer</h4><p>${fills(e.campaign.notes)}</p></div>` : ""}
      <details class="script"><summary>${ic("scroll-text")}<span class="sum-t">Script</span><span class="wc">${e.word_count || 0} mots</span>${ic("chevron-right", "chev")}</summary>
        <div class="script-text">${h0.verbal ? `<p class="script-hook"><b>${esc(h0.verbal)}</b></p>` : ""}${fills(e.script)}</div>
        <div class="script-actions">${e.edited_by_owner ? `<span class="edited">${ic("pencil")}Ta version</span>` : ""}<button class="btn" data-act="edit-script">${ic("pencil")}Modifier le script</button></div></details>
    </div>
    <aside class="side">${refBlock(e.reference)}${ideaBlock(e)}${citationBlock(e)}</aside>
    <footer class="actions">
      <div class="seg" role="group" aria-label="Statut" ${segVars(stIdx, 3)}>${Object.entries(STATUS).map(([k, [v, ico]]) => `<button data-act="status" data-s="${k}" class="${e.status === k ? "on" : ""}" aria-pressed="${e.status === k}">${ic(ico)}${v}</button>`).join("")}</div>
      <span class="spacer"></span>
      <button class="btn small" data-act="prompter">${ic("monitor-play")}Prompteur</button>
      <button class="btn small" data-act="regen">${ic("sparkles")}Régénérer</button>
    </footer></article>`;
}
async function onCardClick(ev) {
  const el = ev.target.closest("[data-act]");
  const card = ev.target.closest("[data-code]");
  if (!el || !card) return;
  const code = card.dataset.code, e = state.videos[code], act = el.dataset.act;
  if (act === "ref") {
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return; // ⌘-clic : ouvrir l'original
    ev.preventDefault();
    return openPlayer(e?.reference || {});
  }
  if (act === "copy") {
    ev.stopPropagation();
    await navigator.clipboard.writeText(el.dataset.text);
    el.classList.add("copied"); setTimeout(() => el.classList.remove("copied"), 1200);
    return toast("Hook copié");
  }
  if (act === "hook") {
    const next = e.hook_used === el.dataset.v ? null : el.dataset.v;
    $$(".hook", card).forEach((h) => h.classList.toggle("used", h.dataset.v === next));
    e.hook_used = next;
    return save(code, { hook_used: next });
  }
  if (act === "shot") {
    const s = new Set(e.shots_done || []), i = +el.dataset.i;
    s.has(i) ? s.delete(i) : s.add(i);
    el.classList.toggle("on", s.has(i));
    el.setAttribute("aria-checked", s.has(i));
    e.shots_done = [...s].sort((a, b) => a - b);
    const cnt = $(".cl-count", card), bar = $(".progress-mini i", card);
    if (cnt) cnt.textContent = `${s.size} sur ${(e.shots || []).length}`;
    if (bar) bar.style.transform = `scaleX(${s.size / ((e.shots || []).length || 1)})`;
    return save(code, { shots_done: e.shots_done });
  }
  if (act === "verify") return save(code, { citation_verified: el.checked });
  if (act === "status") {
    const seg = el.closest(".seg"), btns = $$("button", seg);
    seg.style.setProperty("--i", btns.indexOf(el));
    btns.forEach((b) => { b.classList.toggle("on", b === el); b.setAttribute("aria-pressed", b === el); });
    return save(code, { status: el.dataset.s }, 320);
  }
  if (act === "prompter") return openPrompter(e);
  if (act === "chatcut") {
    const v = await api(`/api/video/${code}`);
    await navigator.clipboard.writeText(v.chatcut);
    return toast("Brief ChatCut copié, colle-le dans ChatCut");
  }
  if (act === "regen") return openRegen(e);
  if (act === "edit-script") {
    const box = el.closest("details.script");
    const cta = (e.cta && typeof e.cta === "object") ? (e.cta.text || "") : (e.cta || "");
    $(".script-text", box).outerHTML = `<form class="script-edit">
      <label>Hook (ce que tu dis en premier)<textarea name="hook" rows="2">${esc(e.hooks?.[0]?.verbal || "")}</textarea></label>
      <label>Script<textarea name="script" rows="14">${esc(e.script || "")}</textarea></label>
      <label>CTA<textarea name="cta" rows="2">${esc(cta)}</textarea></label>
      <p class="hint">Ta version sert d'exemple pour toutes les prochaines vidéos.</p></form>`;
    $(".script-actions", box).innerHTML = `<button class="btn" data-act="cancel-script">Annuler</button><button class="btn primary" data-act="save-script">${ic("check")}Enregistrer</button>`;
    icons();
    return $("textarea[name=script]", box).focus();
  }
  if (act === "cancel-script") return replaceCard(code, e);
  if (act === "save-script") {
    const f = $("form.script-edit", el.closest("details.script"));
    const body = { hook: f.hook.value, script: f.script.value, cta: f.cta.value };
    el.disabled = true;
    try {
      const out = await api(`/api/video/${code}/script`, { method: "POST", body });
      replaceCard(code, { ...e, ...out });
      return toast("Enregistré. Ta correction servira d'exemple pour les prochaines vidéos");
    } catch (err) { el.disabled = false; return toast(err.message, true); }
  }
}
document.addEventListener("click", onCardClick);
document.addEventListener("keydown", (ev) => {
  const t = ev.target;
  if ((ev.key === "Enter" || ev.key === " ") && t.matches && t.matches('[role="button"]:not(button), [role="checkbox"]:not(input)')) {
    if (!$("#prompter").classList.contains("hidden")) return;
    ev.preventDefault(); t.click();
  }
});
const pending = {};
async function save(code, patch, minMs = 0) {
  const t0 = performance.now();
  pending[code] = (pending[code] || 0) + 1;
  try {
    const e = await api(`/api/video/${code}`, { method: "POST", body: patch });
    const wait = minMs - (performance.now() - t0);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    e.status = patch.status || state.videos[code].status;
    pending[code]--;
    if (pending[code] > 0) { state.videos[code] = { ...state.videos[code], ...e, shots_done: state.videos[code].shots_done, hook_used: state.videos[code].hook_used }; return; }
    replaceCard(code, { ...state.videos[code], ...e });
    if (patch.status && (state.view === "today" || state.view === "week")) render(true);
  } catch (err) { pending[code] = Math.max(0, (pending[code] || 1) - 1); toast(err.message, true); }
}
function replaceCard(code, e) {
  $$(`.card[data-code="${code}"]`).forEach((old) => {
    const tmp = document.createElement("div");
    tmp.innerHTML = videoCard(e);
    const card = tmp.firstElementChild;
    card.style.animation = "none";
    const open = old.querySelector("details.script")?.open;
    if (open) card.querySelector("details.script").open = true;
    old.replaceWith(card);
  });
  state.videos[code] = e;
  icons();
}

/* ------------------------------------------------------------ régénération */
const IDEAS = ["Hook plus contrarian", "Plus personnel (mon histoire)", "Angle plus concret", "Plus court et punchy",
  "Autre sujet, même format", "Plus de preuves chiffrées", "Plus vulnérable"];
let lastFocus = null;
function openModal(cls = "") {
  const m = $("#modal");
  if (m.classList.contains("hidden")) lastFocus = document.activeElement;
  $("#modal-card").className = "modal-card" + (cls ? " " + cls : "");
  m.classList.remove("hidden", "closing");
}
function closeOverlays() {
  const m = $("#modal"), d = $("#drawer");
  $$("#modal video, #drawer video").forEach((v) => { try { v.pause(); } catch (_) {} });
  [m, d].forEach((x) => {
    if (x.classList.contains("hidden") || x.classList.contains("closing")) return;
    x.classList.add("closing");
    setTimeout(() => {
      x.classList.add("hidden"); x.classList.remove("closing");
      if (x === m) { $("#modal-card").innerHTML = ""; lastFocus?.focus?.({ preventScroll: true }); }
    }, 220);
  });
}
function openVideoDrawer(code) {
  const show = (e) => {
    state.videos[e.code] = e;
    $("#drawer-panel").innerHTML = `<div class="drawer-head"><span class="drawer-date">${cap(fmtDate(e.date, true))}</span>
      ${dayNumberOf(e.date) ? `<span class="drawer-day">Jour ${dayNumberOf(e.date)}</span>` : ""}<span class="spacer"></span>
      <button class="btn small" data-close>${ic("x")}Fermer</button></div>${videoCard(e)}`;
    $("#drawer").classList.remove("hidden", "closing");
    icons();
    $("#drawer-panel").focus?.();
  };
  if (state.videos[code]) return show(state.videos[code]);
  api(`/api/video/${encodeURIComponent(code)}`).then(show).catch((e) => toast(e.message, true));
}

/* ------------------------------------------------------------ lecteur vidéo */
function openPlayer(r) {
  const media = refMedia(r), t = refThumb(r), plat = platName(r.platform) || (/instagram/.test(r.url) ? "Instagram" : /tiktok/.test(r.url) ? "TikTok" : /youtu/.test(r.url) ? "YouTube" : "");
  const rep = score10(r.replicability), hk = score10(r.hook_strength);
  const handle = r.handle || r.channel;
  const why = r.why_it_works || r.why;
  const poster = `<div class="pl-poster${t ? "" : " no-img"}">${phIcon(r.platform)}${thumbImg(t)}
    <span class="pl-note">${ic("download")}Vidéo pas encore téléchargée</span></div>`;
  const stat = (lbl, v) => (v ? `<div class="pl-stat"><small>${lbl}</small><b>${v}</b></div>` : "");
  $("#modal-card").innerHTML = `<div class="pl-frame">${media ? `<video src="${esc(media)}" ${t ? `poster="${esc(t)}"` : ""} controls autoplay playsinline preload="metadata"></video>` : poster}</div>
    <div class="pl-info">
      <div class="sheet-head">${plat ? `<span class="pl-plat">${ic(PLAT_ICON[String(r.platform || plat).toLowerCase()] || "film")}${esc(plat)}</span>` : "<span></span>"}
        <button class="btn icon small" data-close aria-label="Fermer">${ic("x")}</button></div>
      <h2>${esc(r.title || r.caption || "Vidéo de référence")}</h2>
      ${handle ? `<p class="pl-handle">@${esc(handle)}${ACC[r.owner] ? ` · ${ACC[r.owner]}` : ""}</p>` : ""}
      <div class="pl-stats">${stat("Outlier", r.outlier_score ? `x${(+r.outlier_score).toFixed(1)}` : "")}${stat("Vues", r.views ? compact(r.views) : "")}
        ${stat("Réplicabilité", rep)}${stat("Hook", hk)}</div>
      ${FUNNEL[r.funnel_stage] ? `<p class="pl-funnel">${funnelPill(r.funnel_stage)}</p>` : ""}
      ${why ? `<div class="pl-why"><h4>Pourquoi ça marche</h4><p>${esc(why)}</p></div>` : ""}
      ${driverNote(r.success_driver)}
      ${r.url ? `<a class="btn primary pl-open" href="${esc(r.url)}" target="_blank" rel="noopener">${ic("external-link")}Ouvrir sur ${esc(plat || "la plateforme")}</a>` : ""}
    </div>`;
  openModal("sheet-player");
  icons();
  const v = $("#modal-card video");
  if (v) v.addEventListener("error", () => { const f = $("#modal-card .pl-frame"); if (f) { f.innerHTML = poster; icons(); } }, { once: true });
  $("#modal-card [data-close]")?.focus({ preventScroll: true });
}
function openRegen(e) {
  $("#modal-card").innerHTML = `<div class="sheet-head"><span class="sheet-code">${esc(e.code)}</span>
      <button class="btn icon small" data-close aria-label="Fermer">${ic("x")}</button></div>
    <h2>Régénérer cette vidéo</h2><p class="sub">${esc(e.subject)}</p>
    <div class="suggest">${IDEAS.map((i) => `<button data-idea="${esc(i)}">${esc(i)}</button>`).join("")}</div>
    <label class="field-label" for="regen-instr">Consigne (optionnel)</label>
    <textarea id="regen-instr" placeholder="ex. « parle de mon partiel de jeudi », « hook avec un chiffre réel »"></textarea>
    <p class="hint">Claude réécrit la vidéo via ton abonnement en gardant le slot, ton identité et les garde-fous. Environ 1 minute.</p>
    <div class="sheet-actions"><button class="btn ghost" data-close>Annuler</button>
    <button class="btn primary" id="regen-go">${ic("sparkles")}Régénérer</button></div>`;
  openModal();
  icons();
  $("#regen-instr").focus();
  $$("[data-idea]").forEach((b) => (b.onclick = () => { const t = $("#regen-instr"); t.value = (t.value ? t.value + " · " : "") + b.dataset.idea; b.classList.add("on"); }));
  $("#regen-go").onclick = async () => {
    const instruction = $("#regen-instr").value;
    closeOverlays();
    try {
      const j = await api(`/api/video/${e.code}/regenerate`, { method: "POST", body: { instruction } });
      state.regenBusy[e.code] = j.id;
      track(j, "Régénération en cours…");
      replaceCard(e.code, state.videos[e.code]);
      if (state.view === "week") render(true);
    } catch (err) { toast(err.message, true); }
  };
}
async function onRegenerated(code) {
  try {
    const e = await api(`/api/video/${code}`);
    replaceCard(code, e);
  } catch (_) { state.videos[code] && replaceCard(code, state.videos[code]); }
  if (state.view === "week") render(true);
}
document.addEventListener("click", (ev) => {
  if (ev.target.matches("[data-close]") || ev.target.closest("[data-close]") || ev.target.matches("[data-close-bg]")) closeOverlays();
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") { closeOverlays(); closePrompter(); }
});

/* ------------------------------------------------------------ prompteur */
let pTimer = null, pPlaying = false;
function setPlayBtn() {
  $("#prompter-play").innerHTML = `${ic(pPlaying ? "pause" : "play")}Espace`;
  icons();
}
function openPrompter(e) {
  const hook = e.hooks?.find((h) => h.variant === (e.hook_used || "A")) || e.hooks?.[0];
  $("#prompter-title").textContent = `${e.code}, ${e.subject}`;
  $("#prompter-text").innerHTML = `<div class="hookline">${esc(hook?.verbal || "")}</div>\n${fills(e.script)}\n\n\n\n`;
  $("#prompter-text").scrollTop = 0;
  $("#prompter").classList.remove("hidden");
  pPlaying = false;
  setPlayBtn();
}
function closePrompter() { $("#prompter").classList.add("hidden"); clearInterval(pTimer); pPlaying = false; }
function togglePrompter() {
  pPlaying = !pPlaying;
  clearInterval(pTimer);
  if (pPlaying) pTimer = setInterval(() => ($("#prompter-text").scrollTop += +$("#prompter-speed").value * 0.35), 16);
  setPlayBtn();
}
$("#prompter-play").onclick = togglePrompter;
$("#prompter-close").onclick = closePrompter;
$("#prompter-size").oninput = (ev) => ($("#prompter-text").style.fontSize = ev.target.value + "px");
document.addEventListener("keydown", (ev) => {
  if (!$("#prompter").classList.contains("hidden") && ev.code === "Space") { ev.preventDefault(); togglePrompter(); }
});

/* ------------------------------------------------------------ vues */
const pageHead = ({ kicker = "", title, sub = "", actions = "", cls = "" }) => `<header class="page-head ${cls}"><div class="ph-text">
    ${kicker ? `<p class="ph-kicker">${kicker}</p>` : ""}<h1>${title}</h1>${sub ? `<p class="sub">${sub}</p>` : ""}</div>
    ${actions ? `<div class="ph-actions">${actions}</div>` : ""}</header>`;
const emptyState = (icon, title, text, extra = "") => `<div class="empty"><div class="ico">${ic(icon)}</div><h3>${title}</h3><p>${text}</p>${extra}</div>`;

async function viewToday() {
  const o = state.overview, r = o.calendar_range || {};
  const day = state.day = state.day || (r.a && o.today < r.a ? r.a : o.today);
  const ch = challenge();
  const [d, br] = await Promise.all([api(`/api/day/${day}`), ch.started && !ch.upcoming ? null : soft("/api/broll")]);
  const all = d.setups.flatMap((s) => s.videos);
  const filmed = all.filter((v) => v.status !== "planned").length;
  $("#crumbs").innerHTML = `<b>${day === o.today ? "Aujourd'hui" : cap(fmtDate(day, true))}</b><span class="crumb-sub">Fiche de tournage</span>
    <span class="day-nav"><button class="btn icon small" id="d-prev" aria-label="Jour précédent">${ic("chevron-left")}</button>
    <button class="btn small" id="d-today">Aujourd'hui</button><button class="btn icon small" id="d-next" aria-label="Jour suivant">${ic("chevron-right")}</button></span>`;
  // écran « prépare tes B-rolls » seulement s'il n'y a rien à tourner ce jour-là : hors défi, la fiche reste normale
  const preMode = all.length ? null : !ch.started ? "off" : ch.start && day < ch.start ? "before" : null;
  if (preMode) {
    const items = (br?.groups || []).flatMap((g) => g.items || []);
    const bd = items.filter((x) => x.done).length;
    const n = preMode === "before" ? daysBetween(day, ch.start) : 0;
    const hero = pageHead({ kicker: cap(fmtDate(day, true)),
      title: preMode === "off" ? "Ta semaine n'est pas encore prête" : `Jour 1 dans ${plural(n, "jour")}`,
      sub: preMode === "off" ? "Clique sur Lancer la semaine : la plateforme fait la veille de ta niche, puis écrit tes hooks et tes scripts."
        : `Le défi démarre ${esc(fmtDate(ch.start, true))}. D'ici là, avance sur tes B-rolls.`, cls: "today-head" });
    const card = `<div class="prelaunch">
      <button class="pl-row" data-go="broll"><span class="pl-ico">${ic("aperture")}</span><span class="nu-text"><span class="nu-lbl">Liste des B-rolls</span>
        <b>${items.length ? `${bd} sur ${items.length} plans tournés` : "Génère ta liste de plans à tourner"}</b>
        <span class="nu-meta">Regroupés par lieu : fac, chambre, bureau, extérieur, écran…</span></span>
        ${items.length ? `<span class="pl-ring" style="--p:${bd / items.length}" aria-hidden="true"></span>` : ""}<span class="nu-go"><span>Ouvrir</span>${ic("chevron-right")}</span></button>
      </div>`;
    if (!all.length) return hero + card;
    return `${hero}${card}<h2 class="pre-title">Déjà planifié ce jour-là <span class="fmt">${plural(all.length, "vidéo")}</span></h2>
      ${d.setups.map((s, i) => `<section class="setup" id="setup-${i}"><header class="setup-head"><span class="setup-n">${i + 1}</span><div>
      <h2>${esc(setupShort(s.label))}</h2><p class="setup-sub">${esc(setupRest(s.label))}</p></div></header>
      <div class="cards">${s.videos.map(videoCard).join("")}</div></section>`).join("")}`;
  }
  if (!all.length) return pageHead({ kicker: cap(fmtDate(day, true)), title: "Rien de planifié" }) + emptyState("calendar-x", "Rien de planifié ce jour-là",
    "Génère 7 jours de contenu à partir de cette date.", `<p class="empty-cta"><button class="btn primary" onclick="runJob('calendar',{start:'${day}'})">${ic("sparkles")}Générer 7 jours</button></p>`);
  const next = all.find((v) => v.status === "planned");
  const setupDone = (s) => s.videos.every((v) => v.status !== "planned");
  const currentIdx = d.setups.findIndex((s) => !setupDone(s));
  const pct = all.length ? filmed / all.length : 0;
  const progress = `<div class="progress-card" role="img" aria-label="${filmed} vidéos filmées sur ${all.length}">
      <div class="pc-top"><span class="pc-num"><b>${filmed}</b> sur ${all.length}</span><span class="pc-lbl">filmées</span></div>
      <div class="pbar"><i style="--p:${pct}"></i></div>
      <div class="pc-stats"><span>${ic("clapperboard")}${all.length} vidéos</span><span>${ic("map-pin")}${d.setups.length} setups</span>
        <span>${ic("timer")}~${d.minutes} min</span>${ISL() ? `<span>${ic("volume-x")}Zéro musique</span>` : ""}</div></div>`;
  const dayN = d.day_number ?? dayNumberOf(day);
  return `${pageHead({ kicker: dayN ? cap(fmtDate(day, true)) : "Fiche de tournage",
      title: dayN ? `Day ${dayN}<span class="h1-dim"> sur ${ch.len}</span>` : esc(cap(fmtDate(day, true))),
      sub: "Tourne setup par setup, dans cet ordre. Les 2 hooks de chaque vidéo à la suite.", actions: progress, cls: "today-head" })}
    ${next ? `<button class="next-up" data-jump="${next.code}"><span class="nu-ico ${next.account}">${ic("video")}</span>
        <span class="nu-text"><span class="nu-lbl">À filmer maintenant</span><b>${esc(next.subject)}</b>
        <span class="nu-meta">${ACC[next.account]} · ${esc(setupShort(next.setup_label))}</span></span>
        <span class="nu-go"><span>Y aller</span>${ic("chevron-right")}</span></button>`
      : `<div class="next-up done"><span class="nu-ico">${ic("party-popper")}</span><span class="nu-text"><b>Tout est filmé pour aujourd'hui.</b>
        <span class="nu-meta">Passe au montage : ouvre Monter ma vidéo.</span></span></div>`}
    <nav class="steps" aria-label="Ordre des setups">${d.setups.map((s, i) => `<a class="step ${setupDone(s) ? "done" : i === currentIdx ? "current" : ""}" data-scroll="setup-${i}" role="button" tabindex="0">
      <span class="step-n">${setupDone(s) ? ic("check") : i + 1}</span><span class="step-t"><b>${esc(setupShort(s.label))}</b>
      <small>${s.videos.length} vidéo${s.videos.length > 1 ? "s" : ""} · ~${s.videos.length * 7 + 5} min</small></span></a>`).join("")}</nav>
    ${d.setups.map((s, i) => `<section class="setup" id="setup-${i}"><header class="setup-head"><span class="setup-n">${i + 1}</span><div>
      <h2>${esc(setupShort(s.label))}</h2>
      <p class="setup-sub">${esc(setupRest(s.label))}${s.gear ? `${setupRest(s.label) ? " · " : ""}${ic("backpack")}${esc(s.gear)}` : ""}</p></div></header>
      <div class="cards">${s.videos.map(videoCard).join("")}</div></section>`).join("")}`;
}
function afterToday() {
  const navd = (dd) => () => { state.day = dd; render(); };
  $("#d-prev") && ($("#d-prev").onclick = navd(addDays(state.day, -1)));
  $("#d-next") && ($("#d-next").onclick = navd(addDays(state.day, 1)));
  $("#d-today") && ($("#d-today").onclick = navd(state.overview.today));
  $$("[data-scroll]").forEach((a) => (a.onclick = () => $("#" + a.dataset.scroll).scrollIntoView({ behavior: "smooth" })));
  $$("[data-jump]").forEach((b) => (b.onclick = () => $(`.card[data-code="${b.dataset.jump}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" })));
}

/* ---- calendrier (Semaine / Jour / 90 jours) ---- */
const CAL_MODES = [["week", "Semaine", "columns-3"], ["day", "Jour", "rectangle-vertical"]];
const CAMP_SHORT = { presentation_motion: "Motion", presentation_face: "Présentation", temoignage: "Témoignage", objection: "Objection",
  fonctionnalite: "Fonction", rappel: "Rappel" };
const slotOf = (v) => (v.is_rappel ? ["rappel", "Rappel"] : v.campaign ? ["campaign", CAMP_SHORT[v.campaign.type] || "Campagne"]
  : v.slot_type === "test" ? ["test", "Test"] : ["proven", "Éprouvé"]);
const bySlot = (a, b) => (a.slot_index || 0) - (b.slot_index || 0);
const byAccSlot = (a, b) => Object.keys(ACC).indexOf(a.account) - Object.keys(ACC).indexOf(b.account) || bySlot(a, b);
const monthShort = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { month: "short" }).replace(".", "");
const NEXT_STATUS = { planned: "filmed", filmed: "published", published: "planned" };
function statusCircle(v) {
  const lbl = STATUS[v.status]?.[0] || "";
  return `<button class="scircle ${v.status}" data-qs="cycle" aria-label="Statut : ${lbl}. Passer à « ${STATUS[NEXT_STATUS[v.status]]?.[0] || ""} »"
    title="${lbl} · clic : ${STATUS[NEXT_STATUS[v.status]]?.[0] || ""}">${ic("check")}</button>`;
}
function vtile(v, i = 0) {
  const [sk, sl] = slotOf(v), t = refThumb(v.reference), busy = state.regenBusy[v.code];
  const f = FUNNEL[v.funnel_stage];
  return `<div class="vtile ${v.account} is-${v.status}${busy ? " busy" : ""}" data-open="${v.code}" tabindex="0" role="button"
      aria-label="${esc(v.subject)}, ${sl}, ${STATUS[v.status]?.[0] || ""}" style="animation-delay:${Math.min(i, 24) * 14}ms">
    <div class="vt-top"><span class="slot ${sk}">${sl}</span><span class="spacer"></span>${statusCircle(v)}</div>
    <p class="vt-subj">${esc(v.subject)}</p>
    <div class="vt-foot">${f ? `<span class="vt-funnel" title="${f[1]}"><span class="fdot ${v.funnel_stage}"></span>${f[0]}</span>` : "<span></span>"}
      ${t ? `<span class="vt-ref" aria-hidden="true">${thumbImg(t)}</span>` : ""}</div>
    ${busy ? `<div class="vt-busy"><span class="spin"></span><span>Régénération…</span><button class="vt-stop" data-stop-job="${esc(busy)}">${ic("square")}Arrêter</button></div>`
      : `<div class="vt-qa" role="group" aria-label="Actions rapides">
      <button data-qs="open" title="Ouvrir" aria-label="Ouvrir la fiche">${ic("maximize-2")}</button>
      <button data-qs="regen" title="Régénérer" aria-label="Régénérer avec Claude">${ic("sparkles")}</button>
      <button data-qs="filmed" class="qa-film${v.status !== "planned" ? " on" : ""}" title="${v.status === "planned" ? "Marquer filmée" : "Remettre en planifiée"}"
        aria-pressed="${v.status !== "planned"}">${ic("check")}<span>Filmée</span></button></div>`}
  </div>`;
}
function dayPill(d, vs, sel) {
  const t = todayIso(), n = dayNumberOf(d);
  const done = vs.filter((v) => v.status !== "planned").length;
  const dots = vs.length ? vs.slice(0, 8).map((v) => `<i class="${v.status}"></i>`).join("") : `<em>Libre</em>`;
  return `<button class="dpill${d === t ? " today" : ""}${sel ? " sel" : ""}${d < t ? " past" : ""}" data-day="${d}" role="tab" aria-selected="${sel}"
      aria-label="${esc(cap(fmtDate(d, true)))}${n ? `, Jour ${n}` : ""} : ${done} sur ${vs.length} filmées">
    <span class="dp-wd">${wday(d)}</span><span class="dp-dn">${dnum(d)}</span>
    <span class="dp-jr">${n ? `Jour ${n}` : "&nbsp;"}</span><span class="dp-dots" aria-hidden="true">${dots}</span></button>`;
}
function weekSummary(w) {
  const vs = w.videos, done = vs.filter((v) => v.status !== "planned").length, pub = vs.filter((v) => v.status === "published").length;
  const fc = { tofu: 0, mofu: 0, bofu: 0 };
  vs.forEach((v) => { if (v.funnel_stage in fc) fc[v.funnel_stage]++; });
  const fT = fc.tofu + fc.mofu + fc.bofu;
  const tests = Object.keys(ACC).map((a) => vs.find((v) => v.account === a && v.slot_type === "test")).filter(Boolean);
  const accs = Object.keys(ACC).map((a) => { const av = vs.filter((v) => v.account === a), ad = av.filter((v) => v.status !== "planned").length;
    return `<span class="ws-acc"><span class="ring ${a}" style="--p:${av.length ? ad / av.length : 0}" aria-hidden="true"></span><span><b>${ACC[a]}</b><small>${ad} sur ${av.length}</small></span></span>`; }).join("");
  return `<div class="wsum">
    <div class="ws-main"><p class="ws-line"><span><b>${vs.length}</b> vidéos</span><span class="dsep">·</span><span><b>${done}</b> filmée${done > 1 ? "s" : ""}</span>
      ${pub ? `<span class="dsep">·</span><span><b>${pub}</b> publiée${pub > 1 ? "s" : ""}</span>` : ""}
      ${fT ? Object.keys(fc).map((k) => `<span class="dsep">·</span><span class="ws-f" title="${FUNNEL[k][0]}"><span class="fdot ${k}"></span>${FUNNEL[k][1]} <b>${fc[k]}</b></span>`).join("") : ""}</p>
      ${fT ? `<div class="ws-bar" role="img" aria-label="Répartition du funnel">${Object.keys(fc).filter((k) => fc[k]).map((k) => `<i class="${k}" style="flex:${fc[k]}" title="${FUNNEL[k][0]} : ${fc[k]}"></i>`).join("")}</div>` : ""}
      ${tests.length ? `<p class="ws-tests">${ic("flask-conical")}${tests.map((t) => `<span><span class="acc-dot ${t.account}"></span>${esc(t.format?.name || "Format test")}</span>`).join("")}</p>` : ""}</div>
    <div class="ws-accs">${accs}</div></div>`;
}
function board(w) {
  const t = todayIso();
  return `<div class="board">${w.days.map((d) => {
    const n = dayNumberOf(d), dv = w.videos.filter((v) => v.date === d);
    return `<section class="bday${d === t ? " today" : ""}${d < t ? " past" : ""}" id="bday-${d}" aria-label="${esc(cap(fmtDate(d, true)))}">
      <header class="bday-head"><span class="bd-date"><b>${esc(cap(wday(d)))} ${dnum(d)}</b>${esc(new Date(d + "T12:00:00").toLocaleDateString("fr-FR", { month: "long" }))}</span>
        ${n ? `<span class="bd-jr">Jour ${n}</span>` : ""}<span class="bd-n">${dv.filter((v) => v.status !== "planned").length}/${dv.length}</span></header>
      ${Object.keys(ACC).map((a) => { const vs = dv.filter((v) => v.account === a).sort(bySlot);
        return `<div class="bacc ${a}"><div class="bacc-head"><span class="acc-dot ${a}"></span><span class="bacc-l">${ACC[a]}</span></div>
          ${vs.length ? vs.map(vtile).join("") : `<div class="vt-empty">Rien de prévu</div>`}</div>`; }).join("")}</section>`; }).join("")}</div>`;
}
function dayDetail(w, d) {
  const vs = w.videos.filter((v) => v.date === d).sort(byAccSlot), n = dayNumberOf(d);
  const done = vs.filter((v) => v.status !== "planned").length;
  const head = `<div class="dd-head"><div class="dd-t"><p class="ph-kicker">${esc(cap(fmtDate(d, true)))}</p><h2>${n ? `Jour ${n}<span class="h1-dim"> sur ${challenge().len}</span>` : esc(cap(fmtDate(d, true)))}</h2></div>
    ${vs.length ? `<span class="dd-prog"><span class="ring" style="--p:${done / vs.length}" aria-hidden="true"></span><b>${done}</b> sur ${vs.length} filmées</span>` : ""}
    <button class="btn" data-go="today" data-go-day="${d}">${ic("clapperboard")}Fiche de tournage</button></div>`;
  if (!vs.length) return head + emptyState("calendar-x", "Rien de planifié ce jour-là", "Génère 7 jours de contenu à partir de cette date.",
    `<p class="empty-cta"><button class="btn primary" onclick="runJob('calendar',{start:'${d}'})">${ic("sparkles")}Générer 7 jours</button></p>`);
  return head + Object.keys(ACC).map((a) => { const av = vs.filter((v) => v.account === a);
    return av.length ? `<section class="dd-acc"><h3 class="dd-acc-h"><span class="acc-dot ${a}"></span>${ACC[a]}<span class="fmt">${plural(av.length, "vidéo")}</span></h3>
      <div class="cards">${av.map(videoCard).join("")}</div></section>` : ""; }).join("");
}
async function mapView() {
  const ch = challenge();
  const m = ch.started ? await soft("/api/challenge-map") : null;
  if (!ch.started || !m || !m.start_date || !(m.days || []).length)
    return `<div class="map-empty">${emptyState("grid-3x3", ch.started ? "Carte indisponible pour l'instant" : "Lance le défi pour voir ta carte de 90 jours",
      ch.started ? "Le serveur prépare la carte du défi. Réessaie dans quelques minutes." : "Chaque case = un jour du défi : planifié, filmé, publié. C'est toi qui choisis le Jour 1.",
      ch.started ? "" : `<p class="empty-cta"><button class="btn primary" data-challenge="start">${ic("flag")}Lancer le défi</button></p>`)}</div>`;
  const t = todayIso(), start = m.start_date, days = m.days;
  const off = (new Date(start + "T12:00:00").getDay() + 6) % 7, cols = Math.ceil((off + days.length) / 7);
  const tot = (x) => (x.planned || 0) + (x.filmed || 0) + (x.published || 0);
  const lvl = (x) => { const n = tot(x); if (!n) return "none"; if (x.published >= n) return "pub"; if (x.published) return "pub-part";
    if (x.filmed + x.published >= n) return "film"; if (x.filmed) return "film-part"; return "plan"; };
  const cells = Array.from({ length: off }, () => `<span class="mc blank" aria-hidden="true"></span>`).concat(days.map((x) => {
    const n = tot(x), lbl = `Jour ${x.day_number} · ${cap(fmtDate(x.date, true))} · ${n ? `${n} prévue${n > 1 ? "s" : ""}, ${x.filmed || 0} filmée${x.filmed > 1 ? "s" : ""}, ${x.published || 0} publiée${x.published > 1 ? "s" : ""}` : "rien de planifié"}`;
    return `<button class="mc ${lvl(x)}${x.date === t ? " today" : ""}${x.date > t ? " future" : ""}" data-mapday="${x.date}" title="${esc(lbl)}" aria-label="${esc(lbl)}"
      style="animation-delay:${Math.min(x.day_number, 90) * 6}ms"></button>`; }));
  const months = Array.from({ length: cols }, (_, c) => {
    const first = addDays(start, c * 7 - off);
    let lab = c === 0 ? monthShort(start) : "";
    for (let k = 0; !lab && k < 7; k++) if (dnum(addDays(first, k)) === 1) lab = monthShort(addDays(first, k));
    return `<span>${esc(cap(lab))}</span>`; }).join("");
  const sum = days.reduce((a, x) => ({ p: a.p + tot(x), f: a.f + (x.filmed || 0) + (x.published || 0), pub: a.pub + (x.published || 0),
    full: a.full + (tot(x) && x.planned === 0 ? 1 : 0) }), { p: 0, f: 0, pub: 0, full: 0 });
  const cur = dayNumberOf(t);
  const stat = (b, s) => `<div class="ms"><b>${b}</b><small>${s}</small></div>`;
  return `<div class="map-card"><div class="map-stats">
      ${stat(cur ? `Jour ${cur}` : ch.upcoming ? `J-${daysBetween(t, start)}` : "-", cur ? `sur ${ch.len}` : ch.upcoming ? "avant le Jour 1" : "défi terminé")}
      ${stat(sum.f, `filmées sur ${sum.p}`)}${stat(sum.pub, "publiées")}${stat(sum.full, `jour${sum.full > 1 ? "s" : ""} bouclé${sum.full > 1 ? "s" : ""}`)}</div>
    <div class="map-scroll"><div class="map" style="--cols:${cols}">
      <div class="map-months" aria-hidden="true">${months}</div>
      <div class="map-wd" aria-hidden="true"><span>Lun</span><span></span><span>Mer</span><span></span><span>Ven</span><span></span><span>Dim</span></div>
      <div class="map-grid" role="grid" aria-label="Carte des ${ch.len} jours">${cells.join("")}</div></div></div>
    <div class="legend map-legend"><span><i class="mc-l none"></i>Rien</span><span><i class="mc-l plan"></i>Planifié</span><span><i class="mc-l film"></i>Filmé</span>
      <span><i class="mc-l pub"></i>Publié</span><span><i class="mc-l today"></i>Aujourd'hui</span><span class="fmt">Compte perso · clique un jour pour l'ouvrir</span></div></div>`;
}
async function viewWeek() {
  state.weekStart = state.weekStart || state.overview.week_start;
  const mode = CAL_MODES.some(([k]) => k === state.calMode) ? state.calMode : "week";
  const w = await api(`/api/week?start=${state.weekStart}`);
  w.videos.forEach((v) => (state.videos[v.code] = v));
  const t = todayIso();
  if (!state.calDay || !w.days.includes(state.calDay)) state.calDay = w.days.includes(t) ? t : w.days[0];
  $("#crumbs").innerHTML = `<b>Calendrier</b><span class="crumb-sub">${mode === "map" ? `Défi ${challenge().len} jours` : `${fmtDate(w.days[0])} → ${fmtDate(w.days[6])}`}</span>`;
  const mi = CAL_MODES.findIndex(([k]) => k === mode);
  const seg = `<div class="seg cal-seg" role="tablist" aria-label="Affichage" ${segVars(mi, 3)}>${CAL_MODES.map(([k, l, ico]) =>
    `<button data-cal="${k}" role="tab" class="${k === mode ? "on" : ""}" aria-selected="${k === mode}">${ic(ico)}${l}</button>`).join("")}</div>`;
  const navLbl = mode === "day" ? ["Jour précédent", "Jour suivant", "Aujourd'hui"] : ["Semaine précédente", "Semaine suivante", "Cette semaine"];
  const nav = mode === "map" ? "" : `<div class="btn-group"><button class="btn icon" id="wk-prev" aria-label="${navLbl[0]}">${ic("chevron-left")}</button>
    <button class="btn" id="wk-today">${navLbl[2]}</button><button class="btn icon" id="wk-next" aria-label="${navLbl[1]}">${ic("chevron-right")}</button></div>`;
  const actions = mode === "map" ? `<button class="btn" data-challenge="start">${ic("calendar-cog")}Date du défi</button>`
    : `<button class="btn" onclick="runJob('references',{start:'${state.weekStart}'})">${ic("link")}Références</button>
      <button class="btn primary" id="wk-regen">${ic("sparkles")}Régénérer la semaine</button>`;
  const title = mode === "map" ? "90 jours" : mode === "day" ? "Jour" : "Semaine";
  const kicker = mode === "map" ? (challenge().start ? `Depuis ${fmtDate(challenge().start, true)}` : "Défi") : cap(monthLabel(w.days[0], w.days[6]));
  const sub = mode === "map" ? "Ta progression jour par jour, comme une carte de contributions." : `${w.videos.filter((v) => v.status !== "planned").length} sur ${w.videos.length} vidéos filmées cette semaine.`;
  let body;
  if (mode === "map") body = await mapView();
  else {
    const strip = `<div class="dstrip" role="tablist" aria-label="Jours de la semaine">${w.days.map((d) => dayPill(d, w.videos.filter((v) => v.date === d).sort(byAccSlot), mode === "day" && d === state.calDay)).join("")}</div>`;
    body = mode === "day" ? `${strip}<div class="day-detail">${dayDetail(w, state.calDay)}</div>`
      : `${weekSummary(w)}<div class="calwrap">${strip}${board(w)}</div>
        <div class="legend"><span><i class="scircle-l planned"></i>Planifiée</span><span><i class="scircle-l filmed"></i>Filmée</span><span><i class="scircle-l published"></i>Publiée</span>
          <span><span class="slot test">Test</span>format emprunté à une autre niche</span>${ISL() ? `<span><span class="slot rappel">Rappel</span>rappel islamique business</span>` : ""}</div>`;
  }
  const anim = state.calAnim ? " anim" : "";
  state.calAnim = false;
  return `${pageHead({ kicker, title, sub, actions })}<div class="cal-toolbar">${seg}<span class="spacer"></span>${nav}</div>
    <div class="cal-body mode-${mode}${anim}">${body}</div>`;
}
function afterWeek() {
  const mode = state.calMode;
  const step = (n) => () => {
    if (mode === "day") { state.calDay = addDays(state.calDay, n); if (!state.calDay || state.calDay < state.weekStart || state.calDay > addDays(state.weekStart, 6)) state.weekStart = addDays(state.weekStart, 7 * Math.sign(n)); }
    else state.weekStart = addDays(state.weekStart, 7 * n);
    state.calAnim = true; render(true);
  };
  $("#wk-prev") && ($("#wk-prev").onclick = step(-1));
  $("#wk-next") && ($("#wk-next").onclick = step(1));
  $("#wk-today") && ($("#wk-today").onclick = () => {
    const t = todayIso();
    state.weekStart = mode === "day" && t < state.overview.week_start ? mondayOf(t) : state.overview.week_start;
    state.calDay = mode === "day" ? (t >= state.weekStart && t <= addDays(state.weekStart, 6) ? t : state.weekStart) : null;
    state.calAnim = true; render(true);
  });
  $("#wk-regen") && ($("#wk-regen").onclick = () => confirm("Régénérer avec Claude les vidéos encore « planifiées » de ces 7 jours ? (~15 min)") && runJob("calendar", { start: state.weekStart }));
  $$("[data-cal]").forEach((b, i) => (b.onclick = () => {
    if (state.calMode === b.dataset.cal) return;
    const seg = b.closest(".seg");
    seg.style.setProperty("--i", i);
    $$("button", seg).forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", x === b); });
    state.calMode = b.dataset.cal; lsSet("ce-cal-mode", state.calMode); state.calAnim = true;
    setTimeout(() => render(true), 160);
  }));
  // bande des jours : clic = focus du jour ; flèches gauche/droite pour naviguer
  const pills = $$(".dpill");
  pills.forEach((p, i) => {
    p.onclick = () => {
      if (mode === "day") { state.calDay = p.dataset.day; state.calAnim = true; return render(true); }
      const col = $("#bday-" + p.dataset.day);
      if (!col) return;
      col.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      col.classList.remove("flash"); void col.offsetWidth; col.classList.add("flash");
      $(".vtile", col)?.focus({ preventScroll: true });
    };
    p.onkeydown = (ev) => {
      const k = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
      if (!k) return;
      ev.preventDefault(); pills[(i + k + pills.length) % pills.length].focus();
    };
  });
  $$("[data-mapday]").forEach((c) => (c.onclick = () => {
    state.calDay = c.dataset.mapday; state.weekStart = mondayOf(c.dataset.mapday);
    state.calMode = "day"; lsSet("ce-cal-mode", "day"); state.calAnim = true; render(true);
  }));
  const wrap = $(".calwrap");
  if (wrap) wrap.onclick = (ev) => {
    const tile = ev.target.closest("[data-open]");
    if (!tile || ev.target.closest("[data-stop-job]")) return;
    const code = tile.dataset.open, e = state.videos[code], q = ev.target.closest("[data-qs]")?.dataset.qs;
    if (q) ev.stopPropagation();
    if (!q || q === "open") return openVideoDrawer(code);
    if (q === "regen") return openRegen(e);
    const next = q === "cycle" ? NEXT_STATUS[e.status] : e.status === "planned" ? "filmed" : "planned";
    tile.classList.remove("is-planned", "is-filmed", "is-published"); tile.classList.add("is-" + next, "pulse");
    const sc = $(".scircle", tile); if (sc) sc.className = "scircle " + next;
    e.status = next;
    toast(`${STATUS[next][0]} · ${e.subject.slice(0, 48)}${e.subject.length > 48 ? "…" : ""}`);
    save(code, { status: next }, 260);
  };
}

/* ---- stats ---- */
function smoothPath(pts) {
  if (pts.length < 2) return "";
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    const lo = Math.min(p1[1], p2[1]), hi = Math.max(p1[1], p2[1]);
    const c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = Math.min(hi, Math.max(lo, p1[1] + (p2[1] - p0[1]) / 6));
    const c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = Math.min(hi, Math.max(lo, p2[1] - (p3[1] - p1[1]) / 6));
    d += `C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}
function lineChart(points, color = "var(--pb)", id = "ar") {
  if (points.length < 2) return "";
  const W = 560, H = 200, PL = 40, PR = 16, PT = 16, PB = 28, max = Math.max(...points.map((p) => p.v)) * 1.15 || 1;
  const x = (i) => PL + (i * (W - PL - PR)) / (points.length - 1), y = (v) => H - PB - (v / max) * (H - PT - PB);
  const xy = points.map((p, i) => [x(i), y(p.v)]);
  const path = smoothPath(xy);
  const area = `${path}L${x(points.length - 1).toFixed(1)},${H - PB}L${x(0).toFixed(1)},${H - PB}Z`;
  const ticks = [0, .5, 1].map((t) => max * t / 1.15);
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Vues par vidéo dans le temps">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:${color};stop-opacity:.22"/><stop offset="1" style="stop-color:${color};stop-opacity:0"/></linearGradient></defs>
    <g class="grid">${ticks.map((t) => `<line x1="${PL}" x2="${W - PR}" y1="${y(t)}" y2="${y(t)}"/><text x="${PL - 8}" y="${y(t) + 4}" text-anchor="end">${compact(t)}</text>`).join("")}</g>
    <path d="${area}" fill="url(#${id})"/><path class="line" d="${path}" fill="none" style="stroke:${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
    ${points.map((p, i) => `<circle cx="${xy[i][0]}" cy="${xy[i][1]}" r="${i === points.length - 1 ? 4.5 : 3.5}" style="stroke:${color}" class="pt" stroke-width="2"><title>${esc(p.label)} : ${num(p.v)} vues</title></circle>`).join("")}
    ${points.map((p, i) => (i % Math.ceil(points.length / 6) === 0 ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(p.d)}</text>` : "")).join("")}</svg>`;
}
async function igPanel() {
  const st = await api("/api/ig/status");
  if (!st.app_id || !st.secret) return `<div class="panel ig-panel"><div class="panel-head"><span class="ph-ico">${ic("instagram")}</span><h2>Connexion Instagram (stats)</h2></div>
    <p class="sub">Ouvre <code>.env</code> à la racine du projet et remplis <code>IG_APP_ID</code> et <code>IG_APP_SECRET</code> (app Meta → Instagram → API setup with Instagram login),
    puis déclare <code>${esc(st.redirect || "https://localhost:8765/callback")}</code> dans « Business login settings → OAuth redirect URIs ». Recharge ensuite cette page.</p></div>`;
  const allOk = Object.values(st.accounts).every((a) => a.connected);
  const fb = st.flow === "facebook";
  return `<div class="panel ig-panel"><div class="panel-head"><span class="ph-ico">${ic("instagram")}</span><h2>Connexion Instagram</h2><span class="spacer"></span>
      <div class="seg" id="ig-flow" ${segVars(fb ? 1 : 0, 2)}><button data-flow="instagram" class="${!fb ? "on" : ""}">Instagram Login</button><button data-flow="facebook" class="${fb ? "on" : ""}">Facebook Login</button></div></div>
    <div class="group">${Object.keys(ACC).map((a) => `<div class="status-row"><span class="sr-l"><span class="acc-dot ${a}"></span><span><b>${ACC[a]}</b>${st.accounts[a].connected && st.accounts[a].expires ? `<small class="fmt">Token jusqu'au ${fmtDate(st.accounts[a].expires)} · rafraîchi auto</small>` : ""}</span></span>
      <span class="sr-r"><span class="${st.accounts[a].connected ? "pill-ok" : "pill-ko"}">${ic(st.accounts[a].connected ? "check" : "minus")}${st.accounts[a].connected ? "Connecté" : "Non connecté"}</span>
      <button class="btn small" data-ig="${a}">${st.accounts[a].connected ? "Reconnecter" : "Connecter"}</button></span></div>`).join("")}</div>
    <div id="ig-step" class="hidden ig-step">
      <p class="sub">1. Connecte-toi avec <b id="ig-acc"></b> dans l'onglet ouvert · 2. Page d'erreur <code>localhost</code> = normal · 3. Copie l'URL complète et colle-la :</p>
      <div class="ig-row"><input id="ig-url" aria-label="URL de retour" placeholder="https://localhost:8765/callback?code=…">
      <button class="btn primary" id="ig-go">Valider</button></div><div id="ig-choose"></div></div>
    ${allOk ? "" : `<p class="fmt ig-note">Les deux comptes doivent être connectés pour comparer tes formats.</p>`}</div>`;
}
function afterIg() {
  let flow = $("#ig-flow .on")?.dataset.flow || "instagram", stt = null;
  $$("#ig-flow button").forEach((b, i) => (b.onclick = () => {
    flow = b.dataset.flow;
    $("#ig-flow").style.setProperty("--i", i);
    $$("#ig-flow button").forEach((x) => x.classList.toggle("on", x === b));
  }));
  $$("[data-ig]").forEach((b) => (b.onclick = async () => {
    try {
      const r = await api("/api/ig/begin", { method: "POST", body: { account: b.dataset.ig, flow } });
      stt = r.state;
      window.open(r.url, "_blank");
      $("#ig-acc").textContent = "le compte " + ACC[b.dataset.ig];
      $("#ig-step").classList.remove("hidden");
      $("#ig-url").focus();
    } catch (e) { toast(e.message, true); }
  }));
  const finish = async (body) => {
    try {
      const r = await api("/api/ig/complete", { method: "POST", body });
      if (r.choose) {
        $("#ig-choose").innerHTML = `<p class="sub">Plusieurs comptes, lequel ?</p><div class="pick-row">${r.choose.map((u) => `<button class="btn small" data-pick="${esc(u)}">@${esc(u)}</button>`).join("")}</div>`;
        $$("[data-pick]").forEach((p) => (p.onclick = () => finish({ state: r.state, choice: p.dataset.pick })));
        return;
      }
      toast(`@${r.username} connecté`);
      render();
    } catch (e) { toast(e.message, true); }
  };
  $("#ig-go") && ($("#ig-go").onclick = () => finish({ url: $("#ig-url").value, state: stt }));
}
async function viewStats() {
  const [s, ig] = await Promise.all([api("/api/stats"), igPanel()]);
  $("#crumbs").innerHTML = `<b>Stats</b><span class="crumb-sub">Tes vidéos Instagram</span>`;
  const all = Object.values(s).flatMap((d) => d.videos);
  const views = all.map((v) => v.views || 0);
  const med = views.length ? [...views].sort((a, b) => a - b)[Math.floor(views.length / 2)] : null;
  const best = all.reduce((a, v) => (!a || (v.views || 0) > (a.views || 0) ? v : a), null);
  const watch = all.filter((v) => v.avg_watch_time_s).map((v) => v.avg_watch_time_s);
  const kpi = (cls, icon, label, val, small) => `<div class="kpi ${cls}"><div class="kpi-lbl">${ic(icon)}${label}</div><b>${val}</b><small>${small}</small></div>`;
  const kpis = `<div class="kpis">
    ${kpi("k-blue", "clapperboard", "Vidéos suivies", all.length, "30 derniers jours")}
    ${kpi("k-green", "eye", "Vues médianes", compact(med), "par vidéo")}
    ${kpi("k-indigo", "timer", "Visionnage moyen", watch.length ? (watch.reduce((a, b) => a + b, 0) / watch.length).toFixed(1) + "<span class=\"unit\"> s</span>" : "-", "par vue")}
    ${kpi("k-orange", "trophy", "Meilleure vidéo", compact(best?.views), esc((best?.subject || best?.caption || "-").slice(0, 34)))}</div>`;
  const panel = (acc) => {
    const d = s[acc], sm = d.summary;
    if (!sm.n_videos) return `<div class="panel"><div class="panel-head"><span class="acc-dot ${acc}"></span><h2>${ACC[acc]}</h2></div>
      ${emptyState("chart-no-axes-column", "Pas encore de stats", "Connecte le compte ci-dessus, puis « Actualiser ».")}</div>`;
    const fm = sm.by_format || [];
    const max = Math.max(...fm.map((f) => Math.abs(f.uplift_pct || 0)), 10);
    const pts = [...d.videos].filter((v) => v.posted_at).sort((a, b) => a.posted_at.localeCompare(b.posted_at))
      .map((v) => ({ v: v.views || 0, d: v.posted_at.slice(8, 10) + "/" + v.posted_at.slice(5, 7), label: (v.subject || v.caption || "").slice(0, 50) }));
    return `<div class="panel"><div class="panel-head"><span class="acc-dot ${acc}"></span><h2>${ACC[acc]}</h2><span class="spacer"></span>
      <span class="panel-meta">Médiane <b>${compact(sm.median_views)}</b> · <b>${sm.n_videos}</b> vidéos</span></div>
      ${lineChart(pts, ACC_COLOR[acc] || "var(--blue)", "ar-" + acc)}
      ${fm.length ? `<h3 class="sec-title">Formats vs ta médiane</h3>${fm.map((f) => { const u = f.uplift_pct || 0, w = (Math.abs(u) / max) * 50;
        return `<div class="barrow"><span>${esc(f.format_id === "inconnu" ? "non lié au calendrier" : f.format_id)} <span class="fmt">(${f.n})</span></span><div class="track"><i style="left:${u >= 0 ? 50 : 50 - w}%;width:${w}%;background:${u >= 0 ? ACC_COLOR[acc] : "var(--red)"}"></i></div><span class="num ${u >= 0 ? "up" : "down"}">${u > 0 ? "+" : ""}${u}%</span></div>`; }).join("")}` : ""}
      ${(sm.promotions || []).length ? `<h3 class="sec-title">Formats test → éprouvé <span class="fmt">${esc(sm.rule || "")}</span></h3><div class="group">${sm.promotions.map((p) => `<div class="status-row"><span>${esc(p.format_id)}</span><span class="${p.status.startsWith("promu") ? "pill-ok" : "pill-ko"}">${p.n_above}/${p.required} · ${esc(p.status)}</span></div>`).join("")}</div>` : ""}
      <h3 class="sec-title">Dernières vidéos</h3>
      <div class="table-wrap"><table><thead><tr><th>Date</th><th>Vidéo</th><th class="num">Vues</th><th class="num">Partages</th><th class="num">Enreg.</th><th class="num">Visionnage</th></tr></thead><tbody>
      ${d.videos.slice(0, 15).map((v) => `<tr><td class="num date">${esc((v.posted_at || "").slice(8, 10))}/${esc((v.posted_at || "").slice(5, 7))}</td>
        <td><a href="${esc(v.url)}" target="_blank" rel="noopener">${esc((v.subject || v.caption || "(sans légende)").slice(0, 60))}</a><br><span class="fmt">${esc(v.format_name || "non lié au calendrier")}</span></td>
        <td class="num">${num(v.views)}</td><td class="num">${num(v.shares)}</td><td class="num">${num(v.saves)}</td><td class="num">${v.avg_watch_time_s ? v.avg_watch_time_s.toFixed(1) + " s" : "-"}</td></tr>`).join("")}</tbody></table></div></div>`;
  };
  return `${pageHead({ title: "Stats", sub: "Ce qui marche chez toi est réinjecté dans la synthèse et le calendrier.",
      actions: `<button class="btn primary" onclick="runJob('stats')">${ic("refresh-cw")}Actualiser</button>` })}
    ${ig}${all.length ? kpis : ""}<div class="panels">${Object.keys(ACC).map(panel).join("")}</div>`;
}

async function viewDiscover() {
  const rows = await api("/api/discoveries");
  $("#crumbs").innerHTML = `<b>Découvertes</b><span class="crumb-sub">Vidéos qui surperforment</span>`;
  const hasElig = rows.some((r) => "eligible" in r);
  const validOn = hasElig && state.discValid;
  const base = validOn ? rows.filter((r) => r.eligible === true) : rows;
  const f = state.discFilter;
  const list = base.filter((r) => f === "all" || (f === "scout" ? r.category === "discovery" : r.owner === f));
  const filt = [["all", "Tout", base.length], ["scout", "Trouvées par le scout", base.filter((r) => r.category === "discovery").length]];
  state.discRows = list;
  const card = (r, i) => {
    const t = refThumb(r);
    const rep = score10(r.replicability), hk = score10(r.hook_strength);
    const stats = [rep && `Réplicable ${rep}`, hk && `Hook ${hk}`].filter(Boolean).join(" · ");
    const why = r.why_it_works || r.why;
    return `<div class="dcard" data-play="${i}" style="animation-delay:${Math.min(i, 20) * 30}ms"><a class="thumb${t ? "" : " no-img"}" href="${esc(r.url)}" target="_blank" rel="noopener" data-play-link aria-label="Lire la vidéo : ${esc(r.title || "")}">
        ${phIcon(r.platform)}${thumbImg(t)}<span class="score">${ic("flame")}x${(r.outlier_score || 0).toFixed(1)}</span><span class="plat">${esc(platName(r.platform))}</span>
        <span class="play">${ic("play")}</span><span class="views">${ic("eye")}${compact(r.views)}${r.media_url ? "" : `<span class="dl-off" title="Vidéo non téléchargée : miniature + lien">${ic("cloud-off")}</span>`}</span></a>
      <div class="body"><b>${esc(r.title || "(sans titre)")}</b><small>@${esc(r.handle)} · ${ACC[r.owner] || esc(r.owner)}${r.visual_format ? " · " + esc(r.visual_format.replaceAll("_", " ")) : ""}</small>
        ${FUNNEL[r.funnel_stage] || stats ? `<p class="disc-meta">${funnelPill(r.funnel_stage)}${stats ? `<span>${esc(stats)}</span>` : ""}</p>` : ""}
        ${why ? `<small class="why">${esc(why)}</small>` : ""}${driverNote(r.success_driver)}</div>
      <div class="foot">${r.known ? `<span class="pill-ko">${ic("check")}Suivi</span>` : `<button class="btn small" data-add='${esc(JSON.stringify({ owner: r.owner, platform: r.platform, handle: r.handle }))}'>${ic("user-plus")}Ajouter aux références</button>`}</div></div>`;
  };
  return `${pageHead({ title: "Découvertes", sub: "Vrais outliers : vues ÷ médiane du compte (ou ÷ abonnés pour le scout). Clique une carte pour la regarder ici.",
      actions: `<button class="btn primary" onclick="runJob('scout')">${ic("radar")}Lancer le scout</button>` })}
    <div class="filters" role="group" aria-label="Filtres">${hasElig ? `<button data-valid class="chip-toggle ${validOn ? "on" : ""}" aria-pressed="${validOn}">${ic(validOn ? "check" : "plus")}Références valides</button><span class="filters-sep"></span>` : ""}
      ${filt.map(([k, v, n]) => `<button data-f="${k}" class="${f === k ? "on" : ""}" aria-pressed="${f === k}">${v}<span class="n">${n}</span></button>`).join("")}</div>
    ${list.length ? `<div class="disc">${list.map(card).join("")}</div>`
      : emptyState("radar", "Rien ici pour l'instant", validOn && rows.length ? "Aucune référence valide pour ce filtre. Désactive « Références valides » pour tout voir." : "Lance le scout : il scrolle tes feeds et remonte ce qui cartonne.")}`;
}
function afterDiscover() {
  $$("[data-f]").forEach((b) => (b.onclick = () => { state.discFilter = b.dataset.f; render(true); }));
  $("[data-valid]") && ($("[data-valid]").onclick = () => { state.discValid = !state.discValid; render(true); });
  const disc = $(".disc");
  if (disc) disc.onclick = (ev) => {
    if (ev.target.closest("[data-add], .pill-ok, .pill-ko")) return;
    const c = ev.target.closest("[data-play]");
    if (!c) return;
    if (ev.target.closest("[data-play-link]") && (ev.metaKey || ev.ctrlKey || ev.shiftKey)) return;
    ev.preventDefault();
    openPlayer(state.discRows[+c.dataset.play] || {});
  };
  $$("[data-add]").forEach((b) => (b.onclick = async () => {
    try { await api("/api/accounts/add", { method: "POST", body: JSON.parse(b.dataset.add) }); toast("Ajouté à tes comptes de référence"); b.outerHTML = `<span class="pill-ok">Ajouté</span>`; }
    catch (e) { toast(e.message, true); }
  }));
}

/* ---- B-roll (façon Rappels) ---- */
const BR_SETUP = { fac: ["graduation-cap", "blue"], chambre: ["bed-double", "indigo"], bureau: ["laptop", "orange"], exterieur: ["trees", "green"],
  "extérieur": ["trees", "green"], ecran: ["monitor-smartphone", "teal"], "écran": ["monitor-smartphone", "teal"] };
const BR_COLORS = ["blue", "orange", "green", "indigo", "teal", "red"];
const BR_PRIO = { haute: ["!!!", "Priorité haute"], moyenne: ["!!", "Priorité moyenne"], basse: ["!", "Priorité basse"] };
const brSetup = (g, i) => { const k = String(g.setup || "").toLowerCase(); return BR_SETUP[k] || ["clapperboard", BR_COLORS[i % BR_COLORS.length]]; };
const fmtDur = (s) => (s == null || s === "" || isNaN(+s) ? "" : +s >= 60 ? `${Math.round(+s / 6) / 10} min` : `${Math.round(+s)} s`);
function brollItem(it, color) {
  const pr = BR_PRIO[it.priority], used = it.used_in || [];
  return `<li class="br-item${it.done ? " on" : ""}" data-br="${esc(it.id)}">
    <span class="br-check ${color}" role="checkbox" tabindex="0" aria-checked="${!!it.done}" aria-label="${esc(it.shot)}" data-br-toggle>${ic("check")}</span>
    <div class="br-body"><p class="br-shot">${pr ? `<span class="br-prio ${it.priority}" title="${pr[1]}" aria-label="${pr[1]}">${pr[0]}</span>` : ""}${esc(it.shot)}</p>
      ${it.tips ? `<p class="br-tips">${esc(it.tips)}</p>` : ""}
      <div class="br-meta">${fmtDur(it.duration_s) ? `<span class="br-chip">${ic("timer")}${fmtDur(it.duration_s)}</span>` : ""}
        ${used.length ? `<details class="br-used"><summary>${ic("film")}Utilisé dans ${plural(used.length, "vidéo")}${ic("chevron-right", "chev")}</summary>
          <div class="br-codes">${used.map((c) => `<button class="br-code" data-br-open="${esc(c)}">${esc(c)}</button>`).join("")}</div></details>` : ""}</div></div></li>`;
}
function brollCounts() {
  const items = (state.broll?.groups || []).flatMap((g) => g.items || []);
  const done = items.filter((x) => x.done).length;
  const left = items.filter((x) => !x.done).reduce((a, x) => a + (+x.duration_s || 0), 0);
  return { items, done, total: items.length, left };
}
function paintBrollProgress() {
  const c = brollCounts(), el = $(".br-progress");
  if (!el) return;
  $(".brp-num", el).innerHTML = `<b>${c.done}</b> / ${c.total}`;
  $(".brp-bar i", el).style.setProperty("--p", c.total ? c.done / c.total : 0);
  $(".brp-left", el).textContent = c.left ? `~${fmtDur(c.left)} de rushs restants` : c.total && c.done === c.total ? "Tout est tourné. Bravo." : "";
  (state.broll?.groups || []).forEach((g, i) => { const n = $(`[data-brg="${i}"] .brg-n`); if (n) n.textContent = (g.items || []).filter((x) => !x.done).length; });
}
async function viewBroll() {
  const b = (state.broll = await soft("/api/broll", null));
  $("#crumbs").innerHTML = `<b>B-roll</b><span class="crumb-sub">Plans d'illustration à tourner</span>`;
  const running = state.jobs.find((j) => isRunning(j) && j.kind === "broll");
  const regenBtn = running ? `<button class="btn danger-soft" data-stop-job="${esc(running.id)}">${ic("square")}Arrêter la génération</button>`
    : `<button class="btn" id="br-regen">${ic("sparkles")}Régénérer la liste</button>`;
  const groups = (b?.groups || []).filter((g) => (g.items || []).length);
  const head = (actions) => pageHead({ title: "B-roll", sub: "Les plans d'illustration de tes prochaines vidéos, regroupés par lieu. Coche au fur et à mesure.", actions });
  if (!groups.length) return head("") + emptyState("aperture", b ? "Pas encore de liste de B-rolls" : "La liste des B-rolls arrive",
    b ? "Claude parcourt ton calendrier et regroupe tous les plans d'illustration par lieu de tournage. ~2 min."
      : "Le serveur n'expose pas encore la liste. Tu peux déjà lancer la génération ; réessaie dans quelques minutes sinon.",
    `<p class="empty-cta">${running ? `<span class="pill-run"><span class="spin"></span>Génération en cours…</span>` : `<button class="btn primary" id="br-regen">${ic("sparkles")}Générer la liste</button>`}</p>`);
  const c = brollCounts(), f = state.brollFilter;
  const seg = `<div class="seg" id="br-filter" role="group" aria-label="Filtre" ${segVars(f === "all" ? 1 : 0, 2)}>
    <button data-brf="todo" class="${f !== "all" ? "on" : ""}" aria-pressed="${f !== "all"}">À tourner</button><button data-brf="all" class="${f === "all" ? "on" : ""}" aria-pressed="${f === "all"}">Tout</button></div>`;
  const gen = b.generated_at ? `Liste ${b.source === "heuristic" ? "extraite automatiquement" : "générée par Claude"} le ${esc(fmtDate(String(b.generated_at).slice(0, 10)))}` : "";
  const prog = `<div class="br-progress"><div class="brp-top"><span class="brp-num"><b>${c.done}</b> / ${c.total}</span><span class="brp-lbl">plans tournés</span>
      <span class="spacer"></span>${seg}</div>
    <div class="pbar brp-bar"><i style="--p:${c.total ? c.done / c.total : 0}"></i></div>
    <p class="brp-foot"><span class="brp-left">${c.left ? `~${fmtDur(c.left)} de rushs restants` : c.done === c.total ? "Tout est tourné. Bravo." : ""}</span><span class="spacer"></span><span class="fmt">${gen}</span></p></div>`;
  const lists = groups.map((g, i) => {
    const [icon, color] = brSetup(g, i);
    const items = (g.items || []).filter((x) => f === "all" || !x.done);
    const left = (g.items || []).filter((x) => !x.done).length;
    return `<section class="brg" data-brg="${i}" style="animation-delay:${i * 40}ms"><header class="brg-head"><span class="brg-ico ${color}">${ic(icon)}</span>
        <h2>${esc(setupShort(g.label || cap(g.setup)))}</h2><span class="brg-n ${color}">${left}</span></header>
      ${items.length ? `<ul class="br-list">${items.map((it) => brollItem(it, color)).join("")}</ul>`
        : `<p class="br-done">${ic("circle-check")}Tout est tourné ici</p>`}</section>`; }).join("");
  return `${head(regenBtn)}${prog}<div class="brgs">${lists}</div>`;
}
function afterBroll() {
  $$("#br-regen").forEach((b) => (b.onclick = () => (!state.broll?.groups?.length || confirm("Régénérer la liste des B-rolls avec Claude ? Les plans déjà cochés sont conservés quand ils correspondent.")) && runJob("broll")));
  $$("[data-brf]").forEach((b, i) => (b.onclick = () => {
    if (state.brollFilter === b.dataset.brf) return;
    $("#br-filter").style.setProperty("--i", i);
    $$("[data-brf]").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", x === b); });
    state.brollFilter = b.dataset.brf; lsSet("ce-broll-filter", state.brollFilter);
    setTimeout(() => render(true), 160);
  }));
  const root = $(".brgs");
  if (!root) return;
  root.onclick = async (ev) => {
    const op = ev.target.closest("[data-br-open]");
    if (op) return openVideoDrawer(op.dataset.brOpen);
    const tg = ev.target.closest("[data-br-toggle]");
    if (!tg) return;
    const li = tg.closest("[data-br]"), id = li.dataset.br;
    const it = (state.broll?.groups || []).flatMap((g) => g.items || []).find((x) => String(x.id) === id);
    if (!it) return;
    it.done = !it.done;
    li.classList.toggle("on", it.done);
    tg.setAttribute("aria-checked", it.done);
    paintBrollProgress();
    const leave = it.done && state.brollFilter !== "all";
    li.classList.toggle("leaving", leave);
    clearTimeout(brTimer);
    brPending++;
    try { await api(`/api/broll/${encodeURIComponent(id)}`, { method: "POST", body: { done: it.done } }); }
    catch (e) { it.done = !it.done; li.classList.toggle("on", it.done); li.classList.remove("leaving"); tg.setAttribute("aria-checked", it.done); paintBrollProgress(); toast(e.message, true); }
    brPending--;
    // en mode « À tourner », les plans cochés disparaissent après un court instant (comme Rappels)
    if (!brPending && $$(".br-item.leaving").length) brTimer = setTimeout(() => state.view === "broll" && render(true), 700);
  };
}
let brTimer = null, brPending = 0;

/* ---- Hook Lab : hooks des meilleurs créateurs, décortiqués sur 4 canaux ---- */
const HL_CH = {
  verbal: { label: "Verbal", short: "Verbal", icon: "mic" },
  textuel: { label: "Texte", short: "Texte", icon: "type" },
  visuel: { label: "Visuel", short: "Visuel", icon: "eye" },
  auditif: { label: "Auditif", short: "Audio", icon: "audio-lines" },
};
const HL_KEYS = Object.keys(HL_CH);
const HL_SORTS = [["strength", "Force du hook", "Les hooks les plus forts d'abord"], ["outlier", "Outlier", "Score outlier : vues ÷ médiane du créateur"],
  ["recent", "Récent", "Les plus récents d'abord"]];
const HL_AV = ["blue", "orange", "green", "indigo", "teal"];
const HL_PLATS = ["instagram", "tiktok", "youtube"];
const hlNum = (v) => v !== null && v !== undefined && v !== "" && !isNaN(+v);
const hlFr = (v, d = 1) => (+v).toLocaleString("fr-FR", { maximumFractionDigits: d });
const hlSec = (v) => (hlNum(v) ? `${hlFr(v, 2)} s` : "");
const hlCh = (s) => ({ verbal: "verbal", oral: "verbal", texte: "textuel", textuel: "textuel", text: "textuel", textual: "textuel", visuel: "visuel", visual: "visuel",
  auditif: "auditif", audio: "auditif", auditory: "auditif", sonore: "auditif" }[String(s || "").toLowerCase().trim()] || "");
const hlMusic = (it) => { const a = it.auditif || {}, m = String(a.music || "").toLowerCase().trim();
  return (!!m && !["aucune", "aucun", "none", "non", "no"].includes(m)) || String(a.first_sound || "").toLowerCase() === "musique"; };
const hlMusicLbl = (it) => (String(it.auditif?.music || "").toLowerCase() === "probable" ? "Musique probable" : "Musique");
const hlInitials = (name) => { const w = String(name || "?").trim().split(/\s+/).filter(Boolean);
  return ((w[0]?.[0] || "?") + (w.length > 1 ? w[w.length - 1][0] : w[0]?.[1] || "")).toUpperCase(); };
const hlColor = (name) => { let h = 0; for (const c of String(name || "")) h = (h * 31 + c.charCodeAt(0)) >>> 0; return HL_AV[h % HL_AV.length]; };
const hlAvatar = (name, cls = "") => `<span class="hl-av ${hlColor(name)}${cls ? " " + cls : ""}" aria-hidden="true">${esc(hlInitials(name))}</span>`;
const hlDate = (iso) => { if (!iso) return ""; const d = new Date(String(iso).slice(0, 10) + "T12:00:00");
  return isNaN(d) ? "" : d.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }); };
const hlRunning = () => state.jobs.find((j) => isRunning(j) && String(j.kind || "").startsWith("hooklab"));
function hlStatus(s) {
  const k = String(s || "ok").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  if (k.includes("introuv") || k.includes("not found")) return ["bad", "Introuvable", "circle-x"];
  if (k.includes("verif") || k.includes("check")) return ["warn", "À vérifier", "circle-alert"];
  return ["ok", "OK", "check"];
}
const hlProfile = (p, h) => { const u = encodeURIComponent(String(h || "").replace(/^@/, "")), k = String(p || "").toLowerCase();
  return !u ? "" : k === "instagram" ? `https://www.instagram.com/${u}/` : k === "tiktok" ? `https://www.tiktok.com/@${u}` : k === "youtube" ? `https://www.youtube.com/@${u}` : ""; };
const hlHandle = (v) => { let s = String(v || "").trim();
  const m = s.match(/(?:instagram\.com|tiktok\.com|youtube\.com)\/@?([^/?#\s]+)/i);
  if (m) s = m[1];
  return s.replace(/^@+/, "").replace(/\s+/g, ""); };
async function hlCopy(txt) {
  try { await navigator.clipboard.writeText(txt); return true; }
  catch (_) {
    const ta = document.createElement("textarea");
    ta.value = txt; ta.style.cssText = "position:fixed;opacity:0;min-height:0;height:0";
    document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand("copy"); } catch (_) {}
    ta.remove(); return ok;
  }
}
/* créateurs : ceux de l'API + ceux qui n'apparaissent que dans les items */
function hlCreators() {
  const d = state.hl || {}, items = d.items || [], map = new Map();
  (d.creators || []).forEach((c) => c && c.name && !map.has(c.name) && map.set(c.name, { ...c, accounts: c.accounts || [] }));
  items.forEach((it) => it.creator && !map.has(it.creator) && map.set(it.creator, { name: it.creator, accounts: [] }));
  return [...map.values()].map((c) => ({ ...c, n: items.filter((it) => it.creator === c.name).length,
    warn: (c.accounts || []).filter((a) => hlStatus(a.status)[0] !== "ok") }));
}
function hlList() {
  const n = (v) => (hlNum(v) ? +v : -1);
  const l = (state.hl?.items || []).filter((it) => (state.hlCreator === "all" || it.creator === state.hlCreator)
    && (state.hlCh === "all" || hlCh(it.strong_channel) === state.hlCh) && (!state.hlRepl || n(it.replicability) >= 7));
  if (state.hlSort === "outlier") l.sort((a, b) => n(b.outlier_score) - n(a.outlier_score) || n(b.hook_strength) - n(a.hook_strength));
  else if (state.hlSort === "recent") l.sort((a, b) => String(b.posted_at || "").localeCompare(String(a.posted_at || "")) || n(b.hook_strength) - n(a.hook_strength));
  else l.sort((a, b) => n(b.hook_strength) - n(a.hook_strength) || n(b.outlier_score) - n(a.outlier_score));
  return l;
}
/* texte principal d'un canal (carte + détail) */
function hlMain(it, k) {
  const c = it[k] || {};
  if (k === "verbal") return c.text ? { q: true, t: c.text } : null;
  if (k === "textuel") return !it.textuel ? null : c.text ? { q: true, t: c.text } : { t: "Pas de texte à l'écran", muted: true };
  if (k === "visuel") return c.first_frame ? { t: c.first_frame } : c.motion ? { t: c.motion } : null;
  const s = [c.first_sound && cap(c.first_sound), c.voice].filter(Boolean).join(" · ");
  return s ? { t: s } : null;
}
const hlQuote = (t) => (/^\s*["“«'‘]/.test(String(t)) ? esc(String(t).trim()) : `“${esc(String(t).trim())}”`);
const hlMainHtml = (m, empty = "-") => (m ? (m.q ? hlQuote(m.t) : esc(m.t)) : empty);
const hlMainCls = (m) => `${!m || m.muted ? " muted" : ""}${m?.q ? " q" : ""}`;
const hlMeter = (lbl, v, cls) => (hlNum(v) ? `<span class="hl-meter ${cls}" title="${lbl} : ${hlFr(v)}/10"><small>${lbl}</small>
  <span class="hm-bar" aria-hidden="true"><i style="--p:${Math.max(0, Math.min(1, +v / 10))}"></i></span><b>${hlFr(v)}</b></span>` : "");
function hlTags(it, detail = false) {
  const strong = hlCh(it.strong_channel), au = it.auditif || {};
  return [it.archetype ? `<span class="badge hl-arch" title="Archétype : ${esc(it.archetype)}">${ic("shapes")}<span class="bt">${esc(it.archetype)}</span></span>` : "",
    funnelPill(String(it.funnel_stage || "").toLowerCase()),
    detail && strong ? `<span class="badge hl-strong ch-${strong}">${ic(HL_CH[strong].icon)}Canal fort : ${HL_CH[strong].label}</span>` : "",
    hlMusic(it) && ISL() ? `<span class="badge hl-mchip" title="${esc(au.halal_adaptation ? `Version halal : ${au.halal_adaptation}` : "Musique dans le hook : à remplacer chez toi")}">${ic("music")}${hlMusicLbl(it)}</span>` : ""].join("");
}
const hlRef = (it) => ({ ...it, title: it.verbal?.text ? `“${it.verbal.text}”` : it.creator || "Vidéo", channel: it.handle });

function hlChRow(it, k, strong) {
  const m = hlMain(it, k), on = strong === k, ch = HL_CH[k], au = it.auditif || {};
  const halal = ISL() && k === "auditif" && hlMusic(it) && au.halal_adaptation;
  return `<div class="hc-ch ch-${k}${on ? " strong" : ""}"><span class="hc-ico">${ic(ch.icon)}</span><div class="hc-txt">
    <span class="hc-lbl">${ch.label}${on ? `<span class="hc-fort">${ic("zap")}Canal fort</span>` : ""}</span>
    <p class="${hlMainCls(m).trim()}">${hlMainHtml(m)}</p>
    ${halal ? `<div class="hc-halal">${ic("volume-x")}<span>Version halal : ${esc(au.halal_adaptation)}</span></div>` : ""}</div></div>`;
}
function hlCard(it, i) {
  const t = refThumb(it), strong = hlCh(it.strong_channel), p = String(it.platform || "").toLowerCase(), tags = hlTags(it);
  const lbl = `Hook de ${it.creator || "créateur"}${it.verbal?.text ? ` : ${it.verbal.text}` : ""}`;
  return `<article class="hcard" data-hl-open="${it._k}" role="button" tabindex="0" aria-label="${esc(lbl)}" style="animation-delay:${Math.min(i, 16) * 28}ms">
    <a class="thumb hl-thumb${t ? "" : " no-img"}" href="${esc(it.url || "#")}" target="_blank" rel="noopener" data-hl-thumb aria-label="Lire la vidéo ici (⌘-clic : ouvrir l'original)">
      ${phIcon(p)}${thumbImg(t)}${hlNum(it.outlier_score) ? `<span class="hl-out" title="Score outlier">${ic("flame")}x${(+it.outlier_score).toFixed(1)}</span>` : ""}
      ${PLAT[p] ? `<span class="hl-plat" title="${PLAT[p]}">${ic(PLAT_ICON[p])}</span>` : ""}<span class="play">${ic("play")}</span>
      <span class="hl-tfoot">${hlNum(it.views) ? `<span>${ic("eye")}${compact(it.views)}</span>` : "<span></span>"}${hlNum(it.duration_s) ? `<span>${fmtDur(it.duration_s)}</span>` : ""}</span></a>
    <div class="hc-head"><div class="hc-who">${hlAvatar(it.creator, "sm")}<span class="hc-name"><b>${esc(it.creator || "Créateur")}</b>${it.handle ? `<small>@${esc(it.handle)}</small>` : ""}</span></div>
      <div class="hc-meters">${hlMeter("Hook", it.hook_strength, "m-hook")}${hlMeter("Réplicable", it.replicability, "m-rep")}</div>
      ${tags ? `<div class="hc-tags">${tags}</div>` : ""}</div>
    <div class="hc-chs">${HL_KEYS.map((k) => hlChRow(it, k, strong)).join("")}</div></article>`;
}
function hlCreatorPanel(c) {
  const run = hlRunning();
  const accs = (c.accounts || []).map((a) => {
    const [k, l, i] = hlStatus(a.status), p = String(a.platform || "").toLowerCase(), u = hlProfile(p, a.handle);
    const inner = `${ic(PLAT_ICON[p] || "at-sign")}<span class="ha-h">@${esc(String(a.handle || "").replace(/^@/, ""))}</span>
      ${hlNum(a.videos) ? `<small>${plural(+a.videos, "vidéo")}</small>` : ""}<span class="ha-st ${k}">${ic(i)}${l}</span>`;
    return u ? `<a class="hl-acc ${k}" href="${esc(u)}" target="_blank" rel="noopener" title="Ouvrir le profil ${esc(PLAT[p] || p)}">${inner}</a>` : `<span class="hl-acc ${k}">${inner}</span>`;
  }).join("");
  return `<section class="hl-crd"><div class="hl-crd-top">${hlAvatar(c.name, "lg")}<div class="hl-crd-t"><h3>${esc(c.name)}</h3>
      <p>${c.why ? esc(c.why) : plural(c.n, "hook décortiqué", "hooks décortiqués")}</p></div>
    <div class="hl-crd-act"><button class="btn small" data-hl-add="${esc(c.name)}">${ic("plus")}Compte</button>
      <button class="btn small primary" data-hl-run data-creator="${esc(c.name)}"${run ? " disabled" : ""}>${ic("scan-search")}Décortiquer</button></div></div>
    ${accs ? `<div class="hl-accs">${accs}</div>` : `<p class="hl-noacc">Aucun compte renseigné pour ce créateur.</p>`}
    ${c.warn.length ? `<p class="hl-crd-warn">${ic("triangle-alert")}<span>${c.warn.length > 1 ? "Certains comptes sont" : "Un compte est"} à vérifier ou introuvable : ses vidéos ne seront pas récupérées tant que le handle n'est pas bon.</span></p>` : ""}</section>`;
}
function hlRail(crs) {
  const total = (state.hl?.items || []).length;
  const chip = (key, name, n, av, title, warn) => `<button class="hl-cr${state.hlCreator === key ? " on" : ""}" data-hl-cr="${esc(key)}" aria-pressed="${state.hlCreator === key}" title="${esc(title)}">
    <span class="cr-avw">${av}${warn ? `<span class="cr-warn"></span>` : ""}</span><span class="cr-name">${esc(name)}</span><span class="cr-n">${n}</span></button>`;
  return `<div class="hl-rail" role="group" aria-label="Créateurs">${chip("all", "Tous", total, `<span class="hl-av all" aria-hidden="true">${ic("users")}</span>`, `Tous les créateurs · ${plural(total, "hook")}`, false)}
    ${crs.map((c) => chip(c.name, c.name, c.n, hlAvatar(c.name), [`${c.name} · ${plural(c.n, "hook décortiqué", "hooks décortiqués")}`,
      ...c.warn.map((a) => `@${String(a.handle || "").replace(/^@/, "")} (${PLAT[String(a.platform || "").toLowerCase()] || a.platform || "?"}) : ${hlStatus(a.status)[1].toLowerCase()}`)].join("\n"), c.warn.length)).join("")}</div>`;
}
function hlToolbar() {
  const chs = ["all", ...HL_KEYS], ci = chs.indexOf(state.hlCh), si = HL_SORTS.findIndex(([k]) => k === state.hlSort);
  return `<div class="hl-toolbar">
    <div class="seg hl-seg" role="group" aria-label="Canal fort" ${segVars(ci, chs.length)}>${chs.map((k) => `<button data-hl-ch="${k}" class="${state.hlCh === k ? "on" : ""}" aria-pressed="${state.hlCh === k}"
      title="${k === "all" ? "Tous les canaux" : `Canal fort : ${HL_CH[k].label}`}">${k === "all" ? "Tous" : `${ic(HL_CH[k].icon)}<span>${HL_CH[k].short}</span>`}</button>`).join("")}</div>
    <button class="hl-toggle${state.hlRepl ? " on" : ""}" data-hl-repl aria-pressed="${state.hlRepl}" title="Réplicabilité ≥ 7/10">${ic(state.hlRepl ? "check" : "plus")}Réplicables seulement</button>
    <span class="spacer"></span>
    <div class="hl-sort"><span class="hl-sort-l">Trier</span><div class="seg" role="group" aria-label="Trier par" ${segVars(si, HL_SORTS.length)}>${HL_SORTS.map(([k, l, t]) =>
      `<button data-hl-sort="${k}" class="${state.hlSort === k ? "on" : ""}" aria-pressed="${state.hlSort === k}" title="${esc(t)}">${l}</button>`).join("")}</div></div></div>`;
}
function hlResults() {
  const items = state.hl?.items || [], l = hlList(), cr = hlCreators().find((c) => c.name === state.hlCreator);
  const panel = cr ? hlCreatorPanel(cr) : "";
  const run = hlRunning();
  if (!items.length && !cr) return emptyState("scan-search", "Aucun hook décortiqué pour l'instant",
    "Le Hook Lab prend les vidéos qui surperforment chez chaque créateur et décortique leurs 3 premières secondes : ce qui est dit, écrit, montré et entendu.",
    `<p class="empty-cta">${run ? `<span class="pill-run"><span class="spin"></span>Décorticage en cours…</span>` : `<button class="btn primary" data-hl-run>${ic("scan-search")}Décortiquer</button>`}
      ${hlCreators().length ? "" : `<button class="btn" data-hl-add="">${ic("plus")}Ajouter un créateur</button>`}</p>`);
  if (!l.length) {
    const filtered = state.hlCh !== "all" || state.hlRepl;
    const fewer = filtered && items.some((it) => !cr || it.creator === cr.name);
    return panel + (fewer ? emptyState("filter-x", "Aucun hook pour ces filtres", "Élargis le canal ou désactive « Réplicables seulement ».",
      `<p class="empty-cta"><button class="btn" data-hl-reset>${ic("rotate-ccw")}Réinitialiser les filtres</button></p>`)
      : emptyState("scan-search", `Pas encore de hook pour ${esc(cr?.name || "ce créateur")}`, "Lance le décorticage : ses vidéos outliers passeront au crible des 4 canaux."));
  }
  const sl = HL_SORTS.find(([k]) => k === state.hlSort)?.[1] || "";
  return `${panel}<p class="hl-count"><span><b>${l.length}</b> ${l.length > 1 ? "hooks" : "hook"}${cr ? ` de ${esc(cr.name)}` : ""}</span><span class="dsep">·</span><span>tri : ${esc(sl.toLowerCase())}</span></p>
    <div class="hl-grid">${l.map(hlCard).join("")}</div>`;
}
function hlPaint(crChanged = false) {
  const box = $("#hl-results");
  if (!box) return;
  box.innerHTML = hlResults();
  box.classList.remove("swap", "swap-cr");
  void box.offsetWidth;
  box.classList.add("swap");
  if (crChanged) box.classList.add("swap-cr");
  icons();
}
async function hlRun(payload = {}) {
  try {
    const j = await api("/api/run/hooklab", { method: "POST", body: payload });
    track(j, payload.creator ? `Décorticage de ${payload.creator} lancé` : "Décorticage lancé");
    if (j && j.id && !state.jobs.some((x) => x.id === j.id)) state.jobs = [{ status: "running", kind: "hooklab", ...j }, ...state.jobs];
    if (state.view === "hooklab") render(true);
  } catch (e) { toast(e.message, true); }
}

async function viewHooklab() {
  const [d, jobs] = await Promise.all([soft("/api/hooklab", null), soft("/api/jobs", null)]);
  if (Array.isArray(jobs)) state.jobs = jobs;
  $("#crumbs").innerHTML = `<b>Hook Lab</b><span class="crumb-sub">Hooks décortiqués sur 4 canaux</span>`;
  const run = hlRunning();
  const runBtn = run ? `<span class="pill-run hl-running"><span class="spin"></span>Décorticage en cours…</span>
      <button class="btn danger-soft" data-stop-job="${esc(run.id)}">${ic("square")}Arrêter</button>`
    : `<button class="btn primary" data-hl-run>${ic("scan-search")}Décortiquer</button>`;
  const head = (actions) => pageHead({ title: "Hook Lab", sub: "Les hooks des meilleurs créateurs, décortiqués sur 4 canaux : ce qui est dit, écrit, montré et entendu.", actions });
  if (!d) return `<div class="hl">${head(runBtn)}${emptyState("scan-search", "Le Hook Lab arrive",
    "Le serveur n'expose pas encore les données du Hook Lab. Réessaie dans quelques minutes.")}</div>`;
  const items = (Array.isArray(d.items) ? d.items : []).filter(Boolean).map((it, k) => ({ ...it, _k: k }));
  state.hl = { ...d, items };
  if (!["all", ...HL_KEYS].includes(state.hlCh)) state.hlCh = "all";
  if (!HL_SORTS.some(([k]) => k === state.hlSort)) state.hlSort = "strength";
  const crs = hlCreators();
  if (state.hlCreator !== "all" && !crs.some((c) => c.name === state.hlCreator)) state.hlCreator = "all";
  const st = d.stats || {};
  const sc = hlNum(st.creators) ? +st.creators : crs.length, sa = hlNum(st.analyzed) ? +st.analyzed : items.length;
  const sp = hlNum(st.pending) ? +st.pending : null, sv = hlNum(st.videos) ? +st.videos : null;
  const stats = `<div class="hl-stats">
    <span class="hl-stat">${ic("users")}<b>${num(sc)}</b>${sc > 1 ? "créateurs" : "créateur"}</span>
    <span class="hl-stat">${ic("scan-search")}<b>${num(sa)}</b>${sa > 1 ? "vidéos décortiquées" : "vidéo décortiquée"}</span>
    ${sp != null ? `<span class="hl-stat${sp ? " pending" : ""}">${ic("hourglass")}<b>${num(sp)}</b>en attente</span>` : ""}
    ${sv ? `<span class="hl-prog" role="img" aria-label="${sa} vidéos décortiquées sur ${sv}" title="${sa} sur ${sv} vidéos"><i style="--p:${Math.min(1, sa / sv)}"></i></span>` : ""}</div>`;
  const actions = `<button class="btn" data-hl-add="">${ic("plus")}Créateur</button>
    ${items.length ? `<a class="btn" href="/api/hooklab/export" download>${ic("file-spreadsheet")}Exporter<span class="lbl-x">(Excel)</span></a>` : ""}${runBtn}`;
  return `<div class="hl">${head(actions)}${stats}${crs.length ? hlRail(crs) : ""}${items.length ? hlToolbar() : ""}
    <div id="hl-results" class="hl-results">${hlResults()}</div></div>`;
}
function afterHooklab() {
  const root = $(".hl");
  if (!root) return;
  const rail = $(".hl-rail", root);
  if (rail) {
    const fade = () => { rail.classList.toggle("fl", rail.scrollLeft > 4); rail.classList.toggle("fr", rail.scrollLeft + rail.clientWidth < rail.scrollWidth - 4); };
    rail.scrollLeft = state.hlRailX || 0;
    rail.onscroll = () => { state.hlRailX = rail.scrollLeft; fade(); };
    fade();
  }
  const segPick = (b) => {
    const seg = b.closest(".seg"), btns = $$("button", seg);
    seg.style.setProperty("--i", btns.indexOf(b));
    btns.forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", x === b); });
  };
  root.onclick = (ev) => {
    const t = ev.target;
    const run = t.closest("[data-hl-run]");
    if (run) return hlRun(run.dataset.creator ? { creator: run.dataset.creator } : {});
    const add = t.closest("[data-hl-add]");
    if (add) return openHlAdd(add.dataset.hlAdd || "");
    const cr = t.closest("[data-hl-cr]");
    if (cr) {
      const key = cr.dataset.hlCr;
      state.hlCreator = state.hlCreator === key && key !== "all" ? "all" : key;
      $$(".hl-cr", root).forEach((b) => { const on = b.dataset.hlCr === state.hlCreator; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
      $(".hl-cr.on", root)?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
      return hlPaint(true);
    }
    const ch = t.closest("[data-hl-ch]");
    if (ch) { if (state.hlCh === ch.dataset.hlCh) return; segPick(ch); state.hlCh = ch.dataset.hlCh; lsSet("ce-hl-ch", state.hlCh); return hlPaint(); }
    const so = t.closest("[data-hl-sort]");
    if (so) { if (state.hlSort === so.dataset.hlSort) return; segPick(so); state.hlSort = so.dataset.hlSort; lsSet("ce-hl-sort", state.hlSort); return hlPaint(); }
    const rp = t.closest("[data-hl-repl]");
    if (rp) {
      state.hlRepl = !state.hlRepl; lsSet("ce-hl-repl", state.hlRepl ? "1" : "0");
      rp.classList.toggle("on", state.hlRepl); rp.setAttribute("aria-pressed", state.hlRepl);
      rp.innerHTML = `${ic(state.hlRepl ? "check" : "plus")}Réplicables seulement`;
      return hlPaint();
    }
    if (t.closest("[data-hl-reset]")) {
      state.hlCh = "all"; state.hlRepl = false; lsSet("ce-hl-ch", "all"); lsSet("ce-hl-repl", "0");
      const tb = $(".hl-toolbar", root);
      if (tb) tb.outerHTML = hlToolbar();
      return hlPaint();
    }
    if (t.closest(".hl-acc, a[download]")) return;
    const card = t.closest("[data-hl-open]");
    const it = card && state.hl?.items[+card.dataset.hlOpen];
    if (!it) return;
    if (t.closest("[data-hl-thumb]")) {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return; // ⌘-clic : ouvrir l'original
      ev.preventDefault();
      return openPlayer(hlRef(it));
    }
    openHook(it);
  };
}

/* ---- feuille détail d'un hook ---- */
function hlKV(rows) {
  const r = rows.filter(([, v]) => v !== "" && v != null && v !== false);
  return r.length ? `<div class="hl-kv">${r.map(([k, v]) => `<div><span>${k}</span><p>${v}</p></div>`).join("")}</div>` : "";
}
function hlChDetail(it, k, strong) {
  const c = it[k] || {}, ch = HL_CH[k], m = hlMain(it, k), on = strong === k, e = (v) => (v == null || v === "" ? "" : esc(v));
  let rows = [];
  if (k === "verbal") rows = [["Technique", e(c.technique)], ["Débit", hlNum(c.words_per_s) ? `${hlFr(c.words_per_s)} mots/s` : ""],
    ["Premier mot", hlNum(c.first_word_s) ? `à ${hlSec(c.first_word_s)}` : ""]];
  else if (k === "textuel") rows = [["Apparition", c.text && hlNum(c.appears_s) ? `à ${hlSec(c.appears_s)}` : ""], ["Position", e(c.position)], ["Style", e(c.style)],
    ["Relation au verbal", e(c.relation && cap(c.relation))]];
  else if (k === "visuel") rows = [["Mouvement", c.first_frame ? e(c.motion) : ""], ["Cadrage", e(c.framing)],
    ["Coupes (3 s)", hlNum(c.cuts_3s) ? (+c.cuts_3s ? plural(+c.cuts_3s, "coupe") : "Aucune coupe") : ""], ["Preuve", e(c.proof)], ["Pattern interrupt", e(c.pattern_interrupt)]];
  else {
    const mt = c.metrics || {};
    const sil = (mt.silences || []).filter((s) => Array.isArray(s) && hlNum(s[0]) && hlNum(s[1])).map(([a, b]) => `${hlFr(a, 2)}-${hlSec(b)}`).join(", ");
    rows = [["Sound design", e(c.sound_design)],
      ["Musique", c.music ? (hlMusic(it) ? `<span class="hl-mu">${ic("music")}${esc(cap(c.music))}</span>` : esc(cap(c.music))) : ""],
      ["Début de la parole", hlNum(mt.speech_start_s) ? `à ${hlSec(mt.speech_start_s)}` : ""], ["Loudness", hlNum(mt.loudness_lufs) ? `${hlFr(mt.loudness_lufs)} LUFS` : ""],
      ["Fond sonore", e(mt.background_audio && cap(mt.background_audio))], ["Silences", sil ? esc(sil) : ""]];
  }
  return `<div class="hl-chd ch-${k}${on ? " strong" : ""}"><div class="hl-chd-h"><span class="hc-ico">${ic(ch.icon)}</span><b>${ch.label}</b>
      ${on ? `<span class="hc-fort">${ic("zap")}Canal fort</span>` : ""}</div>
    <p class="hl-chd-main${hlMainCls(m)}"${m?.q ? ' lang="en"' : ""}>${hlMainHtml(m, "Pas de données pour ce canal.")}</p>${hlKV(rows)}</div>`;
}
function hlTimeline(it, hasMedia) {
  const tx = it.textuel || {}, mt = it.auditif?.metrics || {};
  const marks = [["verbal", it.verbal?.first_word_s, "1er mot"], ["auditif", mt.speech_start_s, "Début de la voix"], ["textuel", tx.text ? tx.appears_s : null, "Texte à l'écran"]]
    .filter(([, t]) => hlNum(t) && +t >= 0);
  const sil = (mt.silences || []).filter((s) => Array.isArray(s) && hlNum(s[0]) && hlNum(s[1]) && +s[1] > +s[0] && +s[0] < 3);
  const cuts = hlNum(it.visuel?.cuts_3s) ? +it.visuel.cuts_3s : 0;
  if (!marks.length && !sil.length && !hasMedia) return "";
  const pct = (t) => Math.max(0, Math.min(100, (+t / 3) * 100));
  return `<section class="hl-sec"><h4 class="hl-sec-t">Les 3 premières secondes</h4><div class="hl-tl">
    <div class="tl-track"${hasMedia ? ` data-seek title="Clique pour lire à partir d'ici"` : ""}>
      ${sil.map(([a, b]) => `<span class="tl-sil" style="left:${pct(a)}%;width:${pct(b) - pct(a)}%" title="Silence ${hlSec(a)} → ${hlSec(b)}"></span>`).join("")}
      ${marks.map(([k, tt, l]) => `<span class="tl-mk ch-${k} lane-${k}" style="left:clamp(7px,${pct(tt)}%,calc(100% - 7px))" title="${l} : ${hlSec(tt)}"></span>`).join("")}
      <span class="tl-ph" aria-hidden="true"></span></div>
    <div class="tl-ticks" aria-hidden="true"><span>0 s</span><span>1 s</span><span>2 s</span><span>3 s</span></div>
    ${marks.length || sil.length || cuts ? `<div class="tl-leg">${marks.map(([k, tt, l]) => `<span class="ch-${k}"><i></i>${l} · ${hlSec(tt)}</span>`).join("")}
      ${sil.length ? `<span class="sil"><i></i>${plural(sil.length, "silence")}</span>` : ""}${cuts ? `<span>${ic("scissors")}${plural(cuts, "coupe")} dans les 3 s</span>` : ""}</div>` : ""}
  </div></section>`;
}
const HL_NOTE = [["oral", "verbal"], ["texte", "textuel"], ["visuel", "visuel"], ["auditif", "auditif"]];
function hlNote(it) {
  const n = it.creator_note;
  if (!n || typeof n !== "object" || !HL_NOTE.some(([nk]) => n[nk])) return "";
  const extra = { verbal: it.verbal?.technique, textuel: it.textuel?.style, visuel: it.visuel?.first_frame ? it.visuel?.motion : "", auditif: it.auditif?.sound_design };
  const rows = HL_NOTE.filter(([nk, k]) => n[nk] || hlMain(it, k)).map(([nk, k]) => { const m = hlMain(it, k);
    return `<div class="hn-row ch-${k}"><span class="hn-ch"><span class="hc-ico">${ic(HL_CH[k].icon)}</span>${HL_CH[k].label}</span>
      <div class="hn-you${n[nk] ? "" : " muted"}"><small>Toi</small>${n[nk] ? esc(n[nk]) : "-"}</div>
      <div class="hn-eng${m ? "" : " muted"}"><small>Moteur</small>${hlMainHtml(m)}${extra[k] ? `<span class="hn-x">${esc(extra[k])}</span>` : ""}</div></div>`; }).join("");
  return `<section class="hl-sec"><h4 class="hl-sec-t">Ton annotation <span class="fmt">· comparée au moteur</span></h4>
    <div class="hl-note"><div class="hn-head" aria-hidden="true"><span></span><span>${ic("pen-line")}Toi</span><span>${ic("cpu")}Moteur</span></div>${rows}</div></section>`;
}
function openHook(it) {
  const media = refMedia(it), t = refThumb(it), p = String(it.platform || "").toLowerCase(), strong = hlCh(it.strong_channel), au = it.auditif || {};
  const poster = `<div class="pl-poster${t ? "" : " no-img"}">${phIcon(p)}${thumbImg(t)}<span class="pl-note">${ic("download")}Vidéo pas encore téléchargée</span></div>`;
  const stat = (lbl, v) => (v ? `<div class="pl-stat"><small>${lbl}</small><b>${v}</b></div>` : "");
  const s10 = (v) => (hlNum(v) ? `${hlFr(v)}<span class="pl-unit">/10</span>` : "");
  const meta = [it.handle && `@${it.handle}`, hlDate(it.posted_at), hlNum(it.duration_s) && fmtDur(it.duration_s)].filter(Boolean);
  const copyBtn = (txt, what) => `<button class="btn small hl-copy" data-hl-copy="${esc(txt)}" aria-label="Copier ${what}">${ic("copy")}<span>Copier</span></button>`;
  const ad = it.adaptations || {};
  const adapt = [["personal", "Mon compte", ad.personal]].filter(([, , v]) => v);
  const pids = Array.isArray(it.principles) ? it.principles : String(it.principles || "").split(/[,;\s]+/);
  const tags = hlTags(it, true);
  const music = hlMusic(it);
  const sec = (title, body) => `<section class="hl-sec"><h4 class="hl-sec-t">${title}</h4>${body}</section>`;
  $("#modal-card").innerHTML = `<div class="hl-d-media"><div class="pl-frame">${media ? `<video src="${esc(media)}" ${t ? `poster="${esc(t)}"` : ""} controls playsinline preload="metadata"></video>` : poster}
      <button class="hl-d-close" data-close aria-label="Fermer">${ic("x")}</button></div>
      ${media ? `<button class="btn small hl-replay" id="hl-replay">${ic("rotate-ccw")}Revoir le hook · 0-3 s</button>` : ""}</div>
    <div class="hl-d-info">
      <div class="sheet-head hl-d-head">${PLAT[p] ? `<span class="pl-plat">${ic(PLAT_ICON[p])}${PLAT[p]}</span>` : "<span></span>"}<span class="spacer"></span>
        ${it.url ? `<a class="btn small" href="${esc(it.url)}" target="_blank" rel="noopener">${ic("external-link")}Ouvrir l'original</a>` : ""}
        <button class="btn icon small" data-close aria-label="Fermer">${ic("x")}</button></div>
      <div class="hl-d-who">${hlAvatar(it.creator)}<div><b>${esc(it.creator || "Créateur")}</b>${meta.length ? `<small>${esc(meta.join(" · "))}</small>` : ""}</div></div>
      ${it.verbal?.text ? `<h2 class="hl-quote" lang="en">${hlQuote(it.verbal.text)}</h2>` : ""}
      <div class="pl-stats">${stat("Hook", s10(it.hook_strength))}${stat("Réplicabilité", s10(it.replicability))}
        ${stat("Outlier", hlNum(it.outlier_score) ? `x${(+it.outlier_score).toFixed(1)}` : "")}${stat("Vues", hlNum(it.views) ? compact(it.views) : "")}</div>
      ${tags ? `<div class="hl-tags">${tags}</div>` : ""}${driverNote(it.success_driver)}
      ${music && ISL() ? `<div class="hl-music" role="note"><span class="hm-ico">${ic("music")}</span><div>
        <b>${String(au.music || "").toLowerCase() === "probable" ? "Ce hook utilise probablement de la musique" : "Ce hook s'appuie sur de la musique"}<span class="hm-val">Musique : ${esc(cap(au.music || "oui"))}</span></b>
        <p>${au.halal_adaptation ? `<strong>Version halal :</strong> ${esc(au.halal_adaptation)}` : "Zéro musique chez toi : remplace-la par ta voix, un bruitage ou un vrai silence."}</p></div></div>` : ""}
      ${hlTimeline(it, !!media)}
      ${sec("Les 4 canaux", `<div class="hl-chds">${HL_KEYS.map((k) => hlChDetail(it, k, strong)).join("")}</div>`)}
      ${it.why_it_works ? sec("Pourquoi ça marche", `<p class="hl-prose">${esc(it.why_it_works)}</p>`) : ""}
      ${it.synergy ? sec("Synergie des 4 canaux", `<p class="hl-prose">${esc(it.synergy)}</p>`) : ""}
      ${it.template ? `<section class="hl-sec"><div class="hl-sec-h"><h4 class="hl-sec-t">Template réutilisable</h4>${copyBtn(it.template, "le template")}</div>
        <p class="hl-tpl" lang="en">${fills(it.template)}</p></section>` : ""}
      ${adapt.length ? sec("Adaptations pour tes comptes", `<div class="hl-adapts">${adapt.map(([a, l, v]) => `<div class="hl-adapt ${a}"><div class="hl-adapt-h"><span class="acc-dot ${a}"></span><b>${l}</b>
        <span class="spacer"></span>${copyBtn(v, `l'adaptation ${ACC[a]}`)}</div><p lang="en">${fills(v)}</p></div>`).join("")}</div>`) : ""}
      ${pids.filter(Boolean).length ? sec("Principes", `<div class="hl-pids">${pids.filter(Boolean).map((x) => `<span class="hl-pid">${esc(x)}</span>`).join("")}</div>`) : ""}
      ${hlNote(it)}
    </div>`;
  openModal("sheet-hook");
  icons();
  const card = $("#modal-card");
  $$("[data-hl-copy]", card).forEach((b) => (b.onclick = async () => {
    if (!(await hlCopy(b.dataset.hlCopy))) return toast("Copie impossible", true);
    b.classList.add("copied"); b.innerHTML = `${ic("check")}<span>Copié</span>`; icons();
    clearTimeout(b._t);
    b._t = setTimeout(() => { b.classList.remove("copied"); b.innerHTML = `${ic("copy")}<span>Copier</span>`; icons(); }, 1400);
  }));
  const v = $("video", card);
  if (v) {
    v.addEventListener("error", () => { const f = $(".pl-frame", card); if (f) { $("video", f)?.replaceWith(document.createRange().createContextualFragment(poster)); $("#hl-replay")?.remove(); icons(); } }, { once: true });
    const ph = $(".tl-ph", card);
    let stopAt = null;
    const tick = () => {
      if (!v.isConnected) return;
      const x = v.currentTime || 0;
      if (stopAt != null && x >= stopAt) { v.pause(); stopAt = null; }
      if (ph) { ph.style.setProperty("--x", Math.min(x / 3, 1)); ph.classList.toggle("on", x > 0.01 && x <= 3.25); }
      if (!v.paused) requestAnimationFrame(tick);
    };
    ["play", "seeked", "pause"].forEach((e) => v.addEventListener(e, () => requestAnimationFrame(tick)));
    const playFrom = (s) => { stopAt = 3; try { v.currentTime = s; } catch (_) {} v.play().catch(() => {}); };
    $("#hl-replay") && ($("#hl-replay").onclick = () => playFrom(0));
    const tr = $(".tl-track[data-seek]", card);
    if (tr) tr.onclick = (ev) => { const r = tr.getBoundingClientRect(); playFrom(Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) * 3); };
  }
  $(".hl-d-head [data-close]", card)?.focus({ preventScroll: true });
}

/* ---- feuille « + Créateur » ---- */
function openHlAdd(name = "") {
  let plat = "instagram";
  const names = hlCreators().map((c) => c.name);
  $("#modal-card").innerHTML = `<div class="sheet-head"><span class="sheet-code">Hook Lab</span>
      <button class="btn icon small" data-close aria-label="Fermer">${ic("x")}</button></div>
    <h2>${name ? `Ajouter un compte à ${esc(name)}` : "Ajouter un créateur"}</h2>
    <p class="sub">Ses meilleures vidéos (outliers vs sa médiane) seront décortiquées au prochain run.</p>
    <div class="hl-form">
      <label class="field-label" for="hl-name">Nom du créateur</label>
      <input id="hl-name" type="text" list="hl-names" placeholder="ex. Mino Lee" autocomplete="off" value="${esc(name)}">
      <datalist id="hl-names">${names.map((n) => `<option value="${esc(n)}"></option>`).join("")}</datalist>
      <span class="field-label" id="hl-plat-l">Plateforme</span>
      <div class="seg hl-pseg" role="radiogroup" aria-labelledby="hl-plat-l" ${segVars(0, HL_PLATS.length)}>${HL_PLATS.map((p, i) =>
        `<button type="button" data-p="${p}" class="${i === 0 ? "on" : ""}" role="radio" aria-checked="${i === 0}">${ic(PLAT_ICON[p])}${PLAT[p]}</button>`).join("")}</div>
      <label class="field-label" for="hl-handle">Compte</label>
      <div class="hl-at"><span aria-hidden="true">@</span><input id="hl-handle" type="text" placeholder="minolee" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
      <p class="hint">${ic("info")}Tu peux coller l'URL du profil : la plateforme est détectée toute seule.</p>
    </div>
    <div class="sheet-actions"><button class="btn ghost" data-close>Annuler</button>
      <button class="btn primary" id="hl-add-go">${ic("plus")}Ajouter</button></div>`;
  openModal("sheet-hl-add");
  icons();
  const setPlat = (p) => {
    plat = p;
    const btns = $$(".hl-pseg button");
    $(".hl-pseg").style.setProperty("--i", HL_PLATS.indexOf(p));
    btns.forEach((b) => { b.classList.toggle("on", b.dataset.p === p); b.setAttribute("aria-checked", b.dataset.p === p); });
  };
  $$(".hl-pseg button").forEach((b) => (b.onclick = () => setPlat(b.dataset.p)));
  const hIn = $("#hl-handle"), nIn = $("#hl-name"), go = $("#hl-add-go");
  hIn.oninput = () => { const s = hIn.value; const p = /instagram\.com/i.test(s) ? "instagram" : /tiktok\.com/i.test(s) ? "tiktok" : /youtu/i.test(s) ? "youtube" : null; if (p) setPlat(p); };
  const submit = async () => {
    const n = nIn.value.trim(), h = hlHandle(hIn.value);
    if (!n) return nIn.focus();
    if (!h) return hIn.focus();
    go.disabled = true;
    try {
      await api("/api/hooklab/creators", { method: "POST", body: { name: n, platform: plat, handle: h } });
      toast(`@${h} ajouté à ${n}`);
      closeOverlays();
      if (state.view === "hooklab") { state.hlCreator = n; render(true); }
    } catch (e) { go.disabled = false; toast(e.message, true); }
  };
  go.onclick = submit;
  [nIn, hIn].forEach((i) => (i.onkeydown = (ev) => { if (ev.key === "Enter") { ev.preventDefault(); submit(); } }));
  (name ? hIn : nIn).focus();
}

async function viewContext() {
  const files = await api("/api/context");
  state.ctxFile = state.ctxFile || files.find((f) => f.name !== "README.md")?.name || files[0]?.name;
  const cur = files.find((f) => f.name === state.ctxFile) || { content: "" };
  const todo = (c) => (c.match(/\[À COMPLÉTER/g) || []).length;
  $("#crumbs").innerHTML = `<b>Mon contexte</b><span class="crumb-sub">Injecté dans tous les prompts</span>`;
  return `${pageHead({ title: "Mon contexte", sub: `Plus c'est vrai et précis, plus les scripts sonnent comme toi. ${state.overview.context_chars} caractères utiles aujourd'hui.` })}
    <div class="ctx"><div class="ctx-list">${files.map((f) => `<button data-file="${esc(f.name)}" class="${f.name === state.ctxFile ? "on" : ""}">${ic(f.name === "README.md" ? "info" : "file-text")}
        <span class="ctx-name">${esc(f.name)}</span>${todo(f.content) ? `<span class="badge test" title="Lignes à compléter">${todo(f.content)}</span>` : ""}</button>`).join("")}
      <button data-new class="ctx-new">${ic("plus")}Nouveau fichier</button></div>
      <div class="ctx-edit"><textarea id="ctx-text" aria-label="Contenu du fichier" spellcheck="true">${esc(cur.content)}</textarea>
      <div class="ctx-foot"><span class="fmt">Les lignes « [À COMPLÉTER …] » sont ignorées tant que tu ne les remplaces pas.</span>
      <button class="btn primary" id="ctx-save">${ic("save")}Enregistrer</button></div></div></div>`;
}
function afterContext() {
  $$("[data-file]").forEach((b) => (b.onclick = () => { state.ctxFile = b.dataset.file; render(true); }));
  $("[data-new]").onclick = async () => {
    const n = prompt("Nom du fichier (ex. 05_histoires)");
    if (!n) return;
    const name = n.replace(/\.md$/, "").replace(/[^\w-]/g, "_") + ".md";
    await api(`/api/context/${name}`, { method: "POST", body: { content: `# ${n}\n\n` } });
    state.ctxFile = name; render();
  };
  $("#ctx-save").onclick = async () => {
    await api(`/api/context/${state.ctxFile}`, { method: "POST", body: { content: $("#ctx-text").value } });
    toast("Contexte enregistré");
    state.overview = await api("/api/overview");
  };
}

async function viewSystem() {
  const o = (state.overview = await api("/api/overview"));
  paintChallenge();
  const jobs = (state.jobs = await soft("/api/jobs", []));
  const ch = challenge();
  const pill = (ok, t1 = "OK", t0 = "-") => `<span class="${ok ? "pill-ok" : "pill-ko"}">${ic(ok ? "check" : "minus")}${ok ? t1 : t0}</span>`;
  $("#crumbs").innerHTML = `<b>Système</b>`;
  const jobPill = (j) => j.status === "running" ? '<span class="pill-run"><span class="spin"></span>En cours</span>'
    : j.status === "stopped" ? `<span class="pill-ko">${ic("square")}Arrêtée</span>` : pill(j.status === "done", "Terminé", "Erreur");
  const hm = (s) => esc(String(s || "").slice(11, 16));
  const running = jobs.filter(isRunning);
  const jobRow = (j) => `<div class="status-row job-row${isRunning(j) ? " is-running" : ""}"><span class="sr-l"><span><b>${esc(j.label)}</b>
      ${j.external ? `<span class="badge ext" title="Lancé depuis le terminal${j.pid ? ` · PID ${esc(j.pid)}` : ""}">${ic("terminal")}CLI</span>` : ""}
      <span class="fmt">${hm(j.started)}${j.finished ? " → " + hm(j.finished) : ""}</span></span></span>
    <span class="sr-r">${jobPill(j)}${isRunning(j) ? `<button class="btn small danger" data-stop-job="${esc(j.id)}">${ic("square")}Stop</button>` : ""}</span></div>
    ${j.error && j.status !== "stopped" ? `<div class="log err">${esc(j.error)}</div>` : ""}${(j.log || []).length ? `<div class="log">${esc(j.log.slice(-20).join("\n"))}</div>` : ""}`;
  const defi = `<div class="panel"><div class="panel-head"><span class="ph-ico">${ic("flag")}</span><h2>Défi ${ch.len} jours</h2></div>
    <div class="group">
      <div class="status-row"><span class="sr-l">${ic("circle-dot")}Statut</span>${ch.started ? (ch.upcoming ? `<span class="pill-run">${ic("hourglass")}Commence dans ${plural(daysBetween(todayIso(), ch.start), "jour")}</span>` : pill(true, `Lancé · Day ${ch.day ?? "-"}`)) : pill(false, "", "Pas encore lancé")}</div>
      <div class="status-row"><span class="sr-l">${ic("calendar")}Jour 1</span><span class="sr-v">${ch.start ? esc(cap(fmtDate(ch.start, true))) : "-"}</span></div>
      ${ch.start ? `<div class="status-row"><span class="sr-l">${ic("flag-triangle-right")}Jour ${ch.len}</span><span class="sr-v">${esc(cap(fmtDate(addDays(ch.start, ch.len - 1), true)))}</span></div>` : ""}
      ${ch.objectif ? `<div class="status-row"><span class="sr-l">${ic("target")}Objectif</span><span class="sr-v">${esc(ch.objectif)}</span></div>` : ""}</div>
    <div class="panel-actions">${ch.started ? `<button class="btn" data-challenge="start">${ic("calendar-cog")}Changer la date</button>
      <button class="btn ghost danger-text" data-challenge="reset">${ic("rotate-ccw")}Réinitialiser</button>` : `<button class="btn primary" data-challenge="start">${ic("flag")}Lancer le défi</button>`}</div></div>`;
  const plat = { instagram: "instagram", tiktok: "music-2", youtube: "youtube" };
  return `${pageHead({ title: "Système", sub: "Backend : le moteur Python + Claude Code (ton abonnement). Le serveur n'écoute que sur ta machine." })}
    <div class="sys">
      <div class="panel"><div class="panel-head"><span class="ph-ico">${ic("radar")}</span><h2>Comptes scout</h2></div>
        <p class="sub small">Tu te connectes toi-même dans la fenêtre Chrome ; elle se ferme seule une fois connecté. Comptes dédiés uniquement.</p>
        <div class="group">${["instagram", "tiktok", "youtube"].map((p) => `<div class="status-row"><span class="sr-l">${ic(plat[p])}<b>${PLAT[p]}</b></span>
          <span class="sr-r">${pill(o.sessions[p], "Connecté", "Non connecté")}<button class="btn small" onclick="runJob('login',{platform:'${p}'})">${o.sessions[p] ? "Reconnecter" : "Connecter"}</button></span></div>`).join("")}</div>
        <div class="panel-actions"><button class="btn" onclick="runJob('scout')">${ic("radar")}Lancer le scout des feeds</button></div></div>
      <div class="panel"><div class="panel-head"><span class="ph-ico">${ic("cpu")}</span><h2>Moteur</h2></div>
        <div class="group"><div class="status-row"><span class="sr-l">${ic("bot")}<span>Claude <code>${esc(o.llm.provider)}</code></span></span>${pill(o.llm.provider !== "none")}</div>
        ${Object.keys(ACC).map((a) => `<div class="status-row"><span class="sr-l">${ic("instagram")}Stats ${ACC[a]}</span>${pill(o.ig_stats[a], "Connecté", "Non connecté")}</div>`).join("")}
        <div class="status-row"><span class="sr-l">${ic("notebook-pen")}<span>Contexte perso <span class="fmt">${o.context_chars} car.</span></span></span>${pill(o.context_chars > 800, "OK", "À remplir")}</div>
        <div class="status-row"><span class="sr-l">${ic("database")}${num(o.videos.total)} vidéos · ${num(o.videos.outliers)} outliers</span>${pill(o.videos.mock === 0, "100 % réel", o.videos.mock + " mock")}</div></div>
        <div class="panel-actions"><button class="btn" onclick="runJob('weekly')">${ic("rocket")}Pipeline semaine</button>
        <button class="btn" onclick="runJob('daily')">${ic("sunrise")}Routine du jour</button><button class="btn" onclick="runJob('stats')">${ic("refresh-cw")}Stats</button></div></div>
      <div class="panel span-all"><div class="panel-head"><span class="ph-ico">${ic("list-checks")}</span><h2>Tâches</h2>
          ${running.length ? `<span class="panel-meta"><b>${running.length}</b> en cours</span>` : ""}<span class="spacer"></span>
          <button class="btn small" id="jobs-refresh">${ic("refresh-cw")}Actualiser</button></div>
        ${jobs.length ? `<div class="group">${[...running, ...jobs.filter((j) => !isRunning(j))].map(jobRow).join("")}</div>`
          : `<p class="sub">Aucune tâche lancée depuis l'ouverture du dashboard.</p>`}
        <h3 class="sec-title">Derniers runs</h3>
        <div class="log">${esc((o.last_runs || []).map((r) => `${r.at}  ${r.step}  ${r.status}  ${r.detail || ""}`).join("\n"))}</div></div>
    </div>`;
}
function afterSystem() {
  $("#jobs-refresh") && ($("#jobs-refresh").onclick = () => { pollJobs(); render(true); });
}

/* ------------------------------------------------------------ chat (Claude Code, ton abonnement) */
const CHAT_IDEAS = ["Qu'est-ce qui est prévu demain ?", "Régénère mercredi, plus axé objections", "Cette semaine je suis en déplacement : adapte le contenu",
  "Ajoute à mes connaissances ce que j'ai appris en formation : …"];
let chatTimer = null;
function md(s) {
  const blocks = String(s || "").split(/```/);
  return blocks.map((b, i) => {
    if (i % 2) return `<pre><code>${esc(b.replace(/^[\w-]*\n/, ""))}</code></pre>`;
    return b.split(/\n{2,}/).map((p) => {
      const inline = (t) => esc(t).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|\W)_([^_]+)_(?=\W|$)/g, "$1<i>$2</i>");
      const lines = p.trim().split("\n");
      if (!lines[0]) return "";
      if (lines.every((l) => /^\s*([-*]|\d+\.)\s/.test(l))) {
        const ol = /^\s*\d+\./.test(lines[0]);
        return `<${ol ? "ol" : "ul"}>${lines.map((l) => `<li>${inline(l.replace(/^\s*([-*]|\d+\.)\s/, ""))}</li>`).join("")}</${ol ? "ol" : "ul"}>`;
      }
      const h = lines[0].match(/^#{1,4}\s+(.*)/);
      if (h && lines.length === 1) return `<h4>${inline(h[1])}</h4>`;
      return `<p>${lines.map(inline).join("<br>")}</p>`;
    }).join("");
  }).join("");
}
const toolList = (tools) => (tools || []).length ? `<div class="cm-tools">${tools.map((t) => `<span class="cm-tool ${t.ok === false ? "ko" : t.ok ? "ok" : "run"}">
  ${t.ok == null ? '<span class="spin"></span>' : ic(t.ok ? "check" : "x")}<span>${esc(t.label)}</span></span>`).join("")}</div>` : "";
function chatMsgs(c) {
  if (!c.messages.length && !c.live) {
    return `<div class="chat-empty"><div class="ico">${ic("sparkles")}</div><h3>Nouvelle conversation</h3>
      <p>Même cerveau que Claude Code dans ce dossier : tes règles, ta skill, tes sources. Demande une régénération, donne le contexte de la semaine, ajoute ce que tu apprends.</p>
      <div class="chat-ideas">${CHAT_IDEAS.map((t) => `<button class="chip" data-idea="${esc(t)}">${esc(t)}</button>`).join("")}</div></div>`;
  }
  const msg = (m) => m.role === "user" ? `<div class="cm user"><div class="bubble">${esc(m.content).replace(/\n/g, "<br>")}</div></div>`
    : `<div class="cm bot${m.is_error ? " err" : ""}">${toolList(m.tools)}<div class="bubble md">${md(m.content)}</div></div>`;
  const live = c.live ? `<div class="cm bot live">${toolList(c.live.tools)}<div class="bubble md">${c.live.text ? md(c.live.text) : ""}
      <span class="typing" aria-label="Claude écrit"><i></i><i></i><i></i></span></div></div>` : "";
  return c.messages.map(msg).join("") + live;
}
const relTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso), days = daysBetween(iso.slice(0, 10), todayIso());
  return days === 0 ? d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : days === 1 ? "Hier" : d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
};
async function viewChat() {
  const convs = (state.chatList = await api("/api/chat"));
  if (!convs.find((c) => c.id === state.chatId)) state.chatId = convs.find((c) => c.id === lsGet("ce-chat", ""))?.id || convs[0]?.id || null;
  const c = (state.chat = state.chatId ? await api(`/api/chat/${state.chatId}`) : null);
  $("#crumbs").innerHTML = `<b>Chat</b><span class="crumb-sub">Claude Code · ton abonnement</span>`;
  const item = (x) => `<button data-conv="${esc(x.id)}" class="${x.id === state.chatId ? "on" : ""}">${x.running ? '<span class="spin"></span>' : ic("message-square")}
    <span class="ctx-name">${esc(x.title)}</span><span class="fmt">${esc(relTime(x.updated_at))}</span></button>`;
  const side = `<div class="ctx-list chat-list"><button data-new-conv class="ctx-new">${ic("square-pen")}Nouvelle conversation</button>${convs.map(item).join("")}</div>`;
  if (!c) {
    return `${pageHead({ title: "Chat", sub: "Parle au moteur comme à Claude Code : chaque conversation repart de zéro, avec tes règles et tes sources." })}
      <div class="chat">${side}<div class="chat-main">${emptyState("messages-square", "Aucune conversation", "Lance-en une : demande une régénération, donne le contexte de ta semaine ou ajoute ce que tu apprends.",
      `<button class="btn primary" data-new-conv>${ic("square-pen")}Nouvelle conversation</button>`)}</div></div>`;
  }
  return `<div class="chat">${side}
    <div class="chat-main"><div class="chat-head"><h2 id="chat-title" title="Renommer">${esc(c.title)}</h2><span class="spacer"></span>
        <button class="btn small ghost" id="chat-rename" aria-label="Renommer">${ic("pencil")}</button>
        <button class="btn small ghost danger-text" id="chat-delete" aria-label="Supprimer la conversation">${ic("trash-2")}</button></div>
      <div class="chat-msgs" id="chat-msgs" aria-live="polite">${chatMsgs(c)}</div>
      <form class="composer" id="chat-form"><textarea id="chat-input" rows="1" placeholder="Demande quelque chose…" title="Entrée pour envoyer · Maj+Entrée pour aller à la ligne" aria-label="Message"></textarea>
        ${c.live ? `<button type="button" class="btn danger" id="chat-stop">${ic("square")}Stop</button>` : `<button class="btn primary" id="chat-send" aria-label="Envoyer">${ic("arrow-up")}</button>`}</form></div></div>`;
}
function chatScroll(force = false) {
  const box = $("#chat-msgs");
  if (box && (force || box.scrollHeight - box.scrollTop - box.clientHeight < 160)) box.scrollTop = box.scrollHeight;
}
function chatPoll() {
  clearInterval(chatTimer);
  if (!state.chat?.live) return;
  const id = state.chat.id;
  chatTimer = setInterval(async () => {
    if (state.view !== "chat" || state.chatId !== id) { clearInterval(chatTimer); return; }
    const c = await soft(`/api/chat/${id}`);
    if (!c) return;
    state.chat = c;
    if (c.live) { $("#chat-msgs").innerHTML = chatMsgs(c); icons(); chatScroll(); return; }
    clearInterval(chatTimer);
    state.overview = await soft("/api/overview", state.overview);
    const draft = $("#chat-input")?.value || "";
    await render(true);
    if ($("#chat-input")) { $("#chat-input").value = draft; $("#chat-input").focus(); }
    chatScroll(true);
  }, 900);
}
async function newConversation() {
  const c = await api("/api/chat", { method: "POST", body: {} });
  state.chatId = c.id; lsSet("ce-chat", c.id);
  await render(true);
  $("#chat-input")?.focus();
}
async function chatSend(text) {
  text = String(text || "").trim();
  if (!text || state.chat?.live) return;
  const input = $("#chat-input");
  try {
    state.chat = await api(`/api/chat/${state.chatId}/message`, { method: "POST", body: { text } });
    if (input) input.value = "";
    await render(true);
    chatScroll(true);
    $("#chat-input")?.focus();
  } catch (e) { toast(e.message, true); }
}
function afterChat() {
  $$("[data-new-conv]").forEach((b) => (b.onclick = newConversation));
  $$("[data-conv]").forEach((b) => (b.onclick = async () => { state.chatId = b.dataset.conv; lsSet("ce-chat", state.chatId); await render(true); chatScroll(true); }));
  if (!state.chat) return;
  const input = $("#chat-input");
  const grow = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 220) + "px"; };
  input.oninput = grow;
  input.onkeydown = (ev) => { if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); chatSend(input.value); } };
  $("#chat-form").onsubmit = (ev) => { ev.preventDefault(); chatSend(input.value); };
  $$("[data-idea]").forEach((b) => (b.onclick = () => { input.value = b.dataset.idea; grow(); input.focus(); }));
  $("#chat-stop") && ($("#chat-stop").onclick = () => api(`/api/chat/${state.chatId}/stop`, { method: "POST" }));
  const rename = async () => {
    const t = prompt("Nom de la conversation", state.chat.title);
    if (!t) return;
    await api(`/api/chat/${state.chatId}/rename`, { method: "POST", body: { title: t } });
    render(true);
  };
  $("#chat-rename").onclick = rename;
  $("#chat-title").ondblclick = rename;
  $("#chat-delete").onclick = async () => {
    if (!confirm(`Supprimer « ${state.chat.title} » ?`)) return;
    await api(`/api/chat/${state.chatId}`, { method: "DELETE" });
    state.chatId = null; lsSet("ce-chat", "");
    render(true);
  };
  chatScroll(true);
  chatPoll();
}


/* ------------------------------------------------------------ Monter ma vidéo (Module 8) */
const MT_ICON = { soustitres: "captions", brolls: "film", viral: "flame", voixoff: "mic" };
async function viewMontage() {
  $("#crumbs").innerHTML = `<b>Monter ma vidéo</b><span class="crumb-sub">Ta rush brute devient un reel prêt à poster</span>`;
  const d = await api("/api/montages");
  state.mt = d;
  if (!state.mtStyle || !d.styles.some((s) => s.id === state.mtStyle)) state.mtStyle = d.styles[0].id;
  const fiches = d.fiches || [];
  const styles = d.styles.map((s) => `<button class="mt-style${s.id === state.mtStyle ? " on" : ""}" data-mt-style="${esc(s.id)}" aria-pressed="${s.id === state.mtStyle}">
      <span class="mt-ico">${ic(MT_ICON[s.id] || "clapperboard")}</span><b>${esc(s.label)}</b><small>${esc(s.desc || "")}</small></button>`).join("");
  const sel = `<label class="mt-field"><span>Fiche liée (facultatif)</span><select id="mt-code"><option value="">Aucune</option>
      ${fiches.map((e) => `<option value="${esc(e.code)}">${esc(fmtDate(e.date))} · ${esc(String(e.subject || "").slice(0, 80))}</option>`).join("")}</select></label>`;
  const jobs = d.jobs.length ? d.jobs.map(mtJob).join("") : emptyState("clapperboard", "Aucun montage pour l'instant", "Dépose ta première rush au-dessus.");
  return `<div class="mt">${pageHead({ title: "Monter ma vidéo", sub: "Dépose ta rush brute, choisis le style : le monteur coupe, sous-titre et vérifie. Compte 10 à 20 minutes par vidéo." })}
    <section class="mt-new">
      <label class="mt-drop" id="mt-drop" tabindex="0"><input type="file" id="mt-file" accept="video/*" hidden>
        ${ic("upload")}<b id="mt-fname">Glisse ta rush ici</b><small>ou clique pour la choisir (mp4, mov)</small></label>
      <div class="mt-styles" role="group" aria-label="Style de montage">${styles}</div>
      <div class="mt-row">${sel}<button class="btn primary" id="mt-go" disabled>${ic("scissors")}Monter</button></div>
      <div class="mt-bar hidden" id="mt-bar"><i></i></div>
    </section>
    <h2 class="mt-h2">Mes montages</h2><div class="mt-jobs">${jobs}</div></div>`;
}
function mtJob(j) {
  const run = j.status === "en cours", err = j.status === "erreur";
  const last = (j.progress || []).slice(-1)[0] || "";
  const steps = (j.progress || []).map((l) => `<li>${esc(l)}</li>`).join("");
  return `<article class="mt-job${err ? " err" : ""}" data-mt-id="${esc(j.id)}">
    <div class="mt-vid">${j.has_video ? `<video src="/api/montages/${esc(j.id)}/video" controls playsinline preload="metadata"></video>`
      : `<div class="mt-ph">${run ? '<span class="spin"></span>' : ic(err ? "circle-alert" : "film")}</div>`}</div>
    <div class="mt-info"><div class="mt-meta"><span class="badge">${esc(j.style_label || j.style)}</span>${j.code ? `<span class="badge">${esc(j.code)}</span>` : ""}
      <span class="mt-st ${run ? "run" : err ? "err" : "ok"}">${run ? "En cours" : err ? "Erreur" : "Fini"}</span></div>
      <b class="mt-src">${esc(j.source || j.id)}</b><small class="mt-date">${esc((j.started || "").replace("T", " · "))}</small>
      ${run ? `<p class="mt-last">${esc(last)}</p>` : ""}
      ${j.resume ? `<div class="mt-resume">${esc(j.resume).replace(/\n/g, "<br>")}</div>` : ""}
      <details><summary>Étapes (${(j.progress || []).length})</summary><ol>${steps}</ol></details>
      ${j.has_video ? `<a class="btn" href="/api/montages/${esc(j.id)}/video" download>${ic("download")}Télécharger</a>` : ""}</div></article>`;
}
function afterMontage() {
  const root = $(".mt");
  if (!root) return;
  let file = null;
  const go = $("#mt-go"), drop = $("#mt-drop"), input = $("#mt-file");
  const pick = (f) => { if (!f) return; file = f; $("#mt-fname").textContent = f.name; drop.classList.add("has"); go.disabled = false; };
  input.onchange = () => pick(input.files[0]);
  drop.onkeydown = (ev) => (ev.key === "Enter" || ev.key === " ") && input.click();
  drop.ondragover = (ev) => { ev.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (ev) => { ev.preventDefault(); drop.classList.remove("over"); pick(ev.dataTransfer.files[0]); };
  root.onclick = (ev) => {
    const b = ev.target.closest("[data-mt-style]");
    if (!b) return;
    state.mtStyle = b.dataset.mtStyle;
    $$(".mt-style", root).forEach((x) => { const on = x === b; x.classList.toggle("on", on); x.setAttribute("aria-pressed", on); });
  };
  go.onclick = () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file); fd.append("style", state.mtStyle); fd.append("code", $("#mt-code").value);
    const xhr = new XMLHttpRequest(), bar = $("#mt-bar");
    go.disabled = true; bar.classList.remove("hidden");
    xhr.upload.onprogress = (e) => e.lengthComputable && bar.firstElementChild.style.setProperty("--p", e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status >= 300) { toast("Envoi refusé : " + xhr.responseText.slice(0, 200), true); go.disabled = false; bar.classList.add("hidden"); return; }
      toast("Rush reçue, le montage démarre"); render(true);
    };
    xhr.onerror = () => { toast("Envoi impossible", true); go.disabled = false; };
    xhr.open("POST", "/api/montages"); xhr.send(fd);
  };
  clearTimeout(state.mtTimer);
  if ((state.mt?.jobs || []).some((j) => j.status === "en cours"))
    state.mtTimer = setTimeout(() => state.view === "montage" && !$("#mt-file")?.files.length && render(true), 8000);
}

/* ------------------------------------------------------------ routeur */
const VIEWS = { today: [viewToday, afterToday], week: [viewWeek, afterWeek], broll: [viewBroll, afterBroll], stats: [viewStats, afterIg],
  discover: [viewDiscover, afterDiscover], hooklab: [viewHooklab, afterHooklab], montage: [viewMontage, afterMontage], context: [viewContext, afterContext], chat: [viewChat, afterChat], system: [viewSystem, afterSystem] };
function skeleton() {
  return `<div class="sk-head"><div class="sk" style="width:180px;height:16px;border-radius:8px"></div><div class="sk" style="width:min(340px,70%);height:40px;border-radius:12px;margin-top:12px"></div>
    <div class="sk" style="width:min(460px,90%);height:16px;border-radius:8px;margin-top:14px"></div></div>
    <div class="sk" style="height:84px;margin-bottom:24px"></div><div class="sk" style="height:420px;margin-bottom:20px"></div><div class="sk" style="height:420px"></div>`;
}
let renderSeq = 0;
async function render(quiet = false) {
  const [fn, after] = VIEWS[state.view];
  const v = $("#view"), y = window.scrollY, seq = ++renderSeq;
  v.classList.toggle("quiet", quiet);
  if (!quiet) { v.classList.remove("enter"); v.innerHTML = skeleton(); }
  try {
    const html = await fn();
    if (seq !== renderSeq) return;
    v.innerHTML = html;
    if (!quiet) { void v.offsetWidth; v.classList.add("enter"); }
    after && after();
    icons();
    if (quiet) window.scrollTo(0, y);
  } catch (e) {
    if (seq !== renderSeq) return;
    v.innerHTML = emptyState("circle-alert", "Erreur", esc(e.message));
    icons();
  }
}
function go(view) {
  state.view = view;
  document.body.dataset.view = view;
  $$("#nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.view === view);
    a.setAttribute("aria-current", a.dataset.view === view ? "page" : "false");
  });
  history.replaceState(null, "", "#" + view);
  window.scrollTo(0, 0);
  render().then(() => $("#view").focus({ preventScroll: true }));
}
$$("#nav a").forEach((a) => { a.tabIndex = 0; a.onclick = () => go(a.dataset.view); a.onkeydown = (ev) => ev.key === "Enter" && go(a.dataset.view); });
window.addEventListener("scroll", () => document.body.classList.toggle("scrolled", window.scrollY > 4), { passive: true });

(async function init() {
  icons();
  try { state.overview = await api("/api/overview"); }
  catch (e) {
    $("#view").innerHTML = emptyState("wifi-off", "Serveur injoignable", `Le moteur ne répond pas (${esc(e.message)}). Relance-le puis recharge la page.`);
    icons();
    return;
  }
  paintChallenge();
  const v = location.hash.slice(1);
  go(VIEWS[v] ? v : "today");
  pollJobs();
})();
