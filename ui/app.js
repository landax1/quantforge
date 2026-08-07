/* QuantForge SPA — sin frameworks, sin build, 100% offline.
   v4: la corrida se define por OBJETIVO (cuántas estrategias tiene que juntar
   el databank), no por cuántas candidatas probar. Rediseño completo de la UI. */

"use strict";

/* ------------------------------------------------------------------ state */
const S = {
  meta: null,
  datasets: [],
  catalog: [],
  page: "data",
  sel: JSON.parse(localStorage.getItem("qf.sel") || "{}"),   // {dataset_id, timeframe}
  cfg: JSON.parse(localStorage.getItem("qf.cfg") || "null"), // config de mining
  mineJobId: null,
  mineLive: null,
  mineResult: null,
  mining: false,
  inspect: null,
  // cuaderno de laboratorio: cada corrida terminada con su configuración
  runs: JSON.parse(localStorage.getItem("qf.runs") || "[]"),
  // estrategias guardadas: viven en el servidor y sobreviven a cada corrida
  saved: [],
};

/* UN solo modelo de riesgo, dos perillas:
     · riesgo por operación (%) → define el tamaño de la posición
     · relación riesgo/beneficio → define el target como múltiplo del stop
   La distancia del stop NO se configura: se mide en volatilidad (ATR) y el
   minero busca el múltiplo que le sirve a cada estrategia. Esto elimina el
   problema que rompía todo — un stop en puntos es una distancia absoluta que
   no significa lo mismo en el S&P (7700) que en EURUSD (1.15).

   Esta es la perilla de rentabilidad, y su precio es el drawdown. */
const RR_PRESETS = [1, 1.5, 2, 3];
const RISK_PRESETS = [0.5, 1, 2, 3];
const LOT_PRESETS = [0.01, 0.1, 0.5, 1];

/* Qué cuesta una racha de pérdidas seguidas a este nivel de riesgo. Es
   aritmética del tamaño de posición, no un resultado medido: la app no sabe
   de antemano qué va a rendir una estrategia que todavía no encontró, y
   sugerirlo daría la impresión de que los resultados vienen prearmados. */
function lossStreakCost(pct, n = 10) {
  const r = Math.max(+pct || 0, 0) / 100;
  return (1 - Math.pow(1 - r, n)) * 100;
}

const DEFAULT_CFG = {
  spread: 0.36, slippage: 0.1, commission: 0, capital: 10000,
  minPf: 1.10, minSharpe: 0.30, maxDd: 25, minNet: 20, minWinRate: 50,
  maxFilters: 2, direction: "long", minTrades: 30,
  minCagr: 5, minExposure: 5,
  // ningún filtro opcional activo de arranque: primero mostrale que encuentra
  // estrategias, después que suba la vara con lo que le importa
  critOn: {},
  // el número que manda: cuántas estrategias APROBADAS tiene que juntar el
  // databank antes de parar. Cuántas candidatas hagan falta no se sabe de
  // antemano — depende de qué tan exigentes sean los criterios.
  goal: 25,
  // tope de seguridad: sin esto, criterios imposibles buscarían para siempre
  maxCandidates: 20000,
  // % final del período que la búsqueda no ve. Desactivada por defecto: la
  // decisión de partir el período es del usuario, no del programa.
  oosPct: 0,
  fitness: "composite",
  // Cómo se dimensiona la posición. "risk" ajusta el tamaño para que tocar el
  // stop cueste un % fijo; "lots" manda siempre el mismo volumen — hay brokers
  // de CFDs que no interpretan bien un volumen calculado en cada operación.
  sizing: "risk",
  riskPct: 1,      // % del capital arriesgado por operación
  lots: 0.1,       // volumen fijo cuando sizing === "lots"
  rr: 2,           // relación riesgo/beneficio: el target vale 2× el stop
  blocks: null, method: "random",
};
// merge con los defaults: una config vieja guardada en localStorage no tiene
// las claves nuevas, y un undefined en el objetivo rompería la corrida
const _saved = S.cfg;
S.cfg = { ...DEFAULT_CFG, ...(_saved || {}) };
S.cfg.critOn = { ...(S.cfg.critOn || {}) };
if (_saved && _saved.goal == null) {
  // config previa al modelo por objetivo: su "maxCandidates" era el total a
  // probar (a veces 120), inservible como tope de seguridad
  S.cfg.maxCandidates = DEFAULT_CFG.maxCandidates;
}

const GOAL_PRESETS = [10, 25, 50, 100];

/* Filtros de aceptación al databank. Todos opcionales salvo el mínimo de
   operaciones: exigir Sharpe/DD/exposición por defecto rechazaba el 90% de las
   candidatas y la búsqueda volvía vacía sin que se entendiera por qué. Se
   activan de a uno, y sólo cuentan los que estén tildados. */
const CRITERIA = [
  { key: "minPf",       label: "Profit factor ≥",       step: 0.05, min: 0, def: 1.10, unit: "" },
  { key: "minWinRate",  label: "Aciertos ≥",            step: 1,    min: 0, def: 50,   unit: "%" },
  { key: "minNet",      label: "Ganancia total ≥",      step: 5,    min: 0, def: 20,   unit: "%" },
  { key: "minCagr",     label: "Rendimiento anual ≥",   step: 1,    min: 0, def: 5,    unit: "%" },
  // el motor mide el drawdown sobre la curva real: pedir menos de 4% deja
  // fuera hasta a las estrategias buenas, así que ese es el piso del campo
  { key: "maxDd",       label: "Caída máxima ≤",        step: 1,    min: 4, def: 25,   unit: "%" },
  { key: "minSharpe",   label: "Sharpe ≥",              step: 0.1,  min: 0, def: 0.30, unit: "" },
  { key: "minExposure", label: "Tiempo en mercado ≥",   step: 1,    min: 0, def: 5,    unit: "%" },
];
const CRIT_BY_KEY = Object.fromEntries(CRITERIA.map(c => [c.key, c]));

// un valor guardado por debajo del piso del criterio (ej. max DD 1%) no dejaría
// pasar nada: vuelve al recomendado
for (const cr of CRITERIA) {
  if (!Number.isFinite(+S.cfg[cr.key]) || +S.cfg[cr.key] < cr.min) S.cfg[cr.key] = cr.def;
}

/* -------------------------------------------------------------------- api */
const api = {
  async req(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(url, opts);
    if (!r.ok) {
      let msg = `${r.status}`;
      try { msg = (await r.json()).detail || msg; } catch (e) { /* noop */ }
      throw new Error(msg);
    }
    return r.json();
  },
  get: (u) => api.req("GET", u),
  post: (u, b) => api.req("POST", u, b),
  del: (u) => api.req("DELETE", u),
};

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function runJob(url, payload, onTick, onJobId) {
  const { job_id } = await api.post(url, payload);
  if (onJobId) onJobId(job_id);
  for (;;) {
    const j = await api.get(`/api/jobs/${job_id}`);
    if (onTick) onTick(j);
    if (j.status === "done") return j.result;
    if (j.status === "error") throw new Error(j.error);
    await sleep(400);
  }
}

/* ------------------------------------------------------------------ utils */
const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => [...(root || document).querySelectorAll(sel)];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, kind = "") {
  const host = $("#toast-host");
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.textContent = msg;
  host.appendChild(t);
  setTimeout(() => t.remove(), 4600);
}

const fmtPct = (v) => `${v > 0 ? "+" : ""}${(+v).toFixed(2)}%`;
const fmtMoney = (v) => (v < 0 ? "-$" : "$") +
  Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
const fmtNum = (v, d = 2) => (+v).toFixed(d);
const fmtInt = (v) => (+v || 0).toLocaleString("es-AR");

/* duración legible: 45s, 3m 20s, 1h 04m */
function fmtDur(seconds) {
  if (seconds == null || !isFinite(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60), r = s % 60;
  if (m < 60) return `${m}m ${String(r).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

/* encabezado de página con la pastilla de contexto a la derecha */
function pageHead(title, sub, extra = "") {
  return `<div class="page-head">
    <div class="ph-text"><h1>${esc(title)}</h1><p>${sub}</p></div>${extra}</div>`;
}

/* Límites del dataset, en el formato que entiende <input type="date">. */
function datasetBounds(ds) {
  if (!ds) return { lo: "", hi: "" };
  return { lo: String(ds.start).slice(0, 10), hi: String(ds.end).slice(0, 10) };
}

/* El rango efectivo. Los campos NUNCA quedan vacíos: arrancan con el historial
   completo, porque dos casilleros en blanco se leen como "esto hay que
   completarlo" cuando en realidad el default es usar todo. */
function effectiveRange(ds) {
  const b = datasetBounds(ds);
  return { from: S.sel.dateFrom || b.lo, to: S.sel.dateTo || b.hi };
}

function isFullRange(ds) {
  const b = datasetBounds(ds), r = effectiveRange(ds);
  return !b.lo || (r.from <= b.lo && r.to >= b.hi);
}

/* Al cambiar de instrumento el período elegido se conserva — comparar el mismo
   tramo entre mercados es media razón para tener el selector. Lo único que se
   ajusta son los bordes: BTCUSD arranca en 2017, así que un "desde 2013"
   heredado del S&P no existe ahí. Devuelve true si hubo que recortar. */
function clampRangeTo(ds) {
  const b = datasetBounds(ds);
  if (!b.lo || (!S.sel.dateFrom && !S.sel.dateTo)) return false;
  const from = S.sel.dateFrom || b.lo, to = S.sel.dateTo || b.hi;
  const newFrom = from < b.lo ? b.lo : from;
  const newTo = to > b.hi ? b.hi : to;
  // si el tramo pedido no se solapa con el historial nuevo, no hay nada
  // sensato que conservar: se vuelve al historial completo
  if (newFrom >= newTo) {
    S.sel.dateFrom = S.sel.dateTo = "";
    return true;
  }
  const changed = newFrom !== from || newTo !== to;
  S.sel.dateFrom = newFrom;
  S.sel.dateTo = newTo;
  return changed;
}

/* Las fechas sólo viajan cuando recortan algo: con el historial completo el
   backend recibe el payload de siempre y no hay recorte que pueda fallar. */
function rangePayload() {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  if (!ds || isFullRange(ds)) return {};
  const r = effectiveRange(ds);
  return { date_from: r.from, date_to: r.to };
}

/* qué instrumento y timeframe están cargados ahora mismo */
function ctxPill() {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  if (!ds) return "";
  const initials = (ds.name.match(/[A-Za-z0-9]+/g) || ["?"])[0].slice(0, 3).toUpperCase();
  return `<div class="ctx-pill">
    <span class="ctx-ic">${esc(initials)}</span>
    <div><b>${esc(ds.name)}</b><br>
      <span>${fmtInt(ds.rows)} velas · ${esc(String(ds.start).slice(0, 10))} → ${esc(String(ds.end).slice(0, 10))}</span>
    </div></div>`;
}

function saveCfg() {
  localStorage.setItem("qf.cfg", JSON.stringify(S.cfg));
  // El rango de fechas NO se guarda: al abrir la app siempre se arranca con
  // todo el historial. Persistirlo significaría abrir mañana y estar minando
  // un tramo recortado sin acordarse de haberlo elegido.
  const { dateFrom, dateTo, ...persist } = S.sel;
  localStorage.setItem("qf.sel", JSON.stringify(persist));
}

/* El RiskConfig que entiende el backend. El stop va en volatilidad y su
   múltiplo lo elige el minero por candidata; acá sólo viaja la relación R:B. */
function riskPayload() {
  const fixed = S.cfg.sizing === "lots";
  return {
    size_mode: fixed ? "fixed_units" : "risk_pct",
    size_value: fixed ? S.cfg.lots : S.cfg.riskPct,
    stop_type: "atr", stop_value: 2,
    target_type: "atr", target_value: 2 * S.cfg.rr,
    reward_ratio: S.cfg.rr, atr_period: 14,
  };
}

/* Sólo viajan los filtros tildados; el resto va en null y el minero los
   ignora por completo. */
const CRIT_FIELD = {
  minPf: "min_pf", minSharpe: "min_sharpe", maxDd: "max_dd_pct",
  minNet: "min_net_pct", minCagr: "min_cagr_pct", minExposure: "min_exposure_pct",
  minWinRate: "min_win_rate_pct",
};
function acceptPayload() {
  const out = {};
  for (const cr of CRITERIA) {
    const active = !!S.cfg.critOn[cr.key];
    let v = active ? +S.cfg[cr.key] : null;
    if (active && !Number.isFinite(v)) v = cr.def;
    if (active && v < cr.min) v = cr.min;      // el max DD no puede bajar de 4
    out[CRIT_FIELD[cr.key]] = v;
  }
  return out;
}

/* ============================================================ QF Score =====
   La mejor estrategia NO es la que más rindió. El score mide qué tan
   repetible parece: consistencia, ganancia contra caída, cantidad de
   evidencia, ventaja por operación, estabilidad mes a mes y qué tan repartida
   está la ganancia. Un +300% hecho en 22 operaciones puntúa peor que un +40%
   repartido en 500. */
const SCORE_TIERS = [
  { min: 70, label: "Sólida",     cls: "s-top" },
  { min: 50, label: "Prometedora", cls: "s-good" },
  { min: 30, label: "Dudosa",     cls: "s-mid" },
  { min: 0,  label: "Frágil",     cls: "s-low" },
];
const scoreTier = (v) => SCORE_TIERS.find(t => v >= t.min) || SCORE_TIERS[3];

function scoreBadge(v, size = "") {
  const t = scoreTier(+v || 0);
  return `<span class="score-badge ${t.cls} ${size}">
    <b>${fmtNum(v ?? 0, 0)}</b><em>${t.label}</em></span>`;
}

/* barras del desglose: se ve de dónde sale el puntaje y qué lo hunde */
function scoreBars(parts) {
  const defs = S.meta?.score_parts || [];
  if (!parts || !defs.length) return "";
  return `<div class="score-bars">${defs.map(d => {
    const v = +(parts[d.key] ?? 0);
    return `<div class="sb-row">
      <span class="sb-label">${esc(d.label)}</span>
      <span class="sb-track"><i style="width:${(v * 100).toFixed(0)}%"
        class="${v >= 0.66 ? "hi" : v >= 0.33 ? "mid" : "lo"}"></i></span>
      <span class="sb-val">${Math.round(v * d.weight)}<u>/${d.weight}</u></span>
    </div>`;
  }).join("")}</div>`;
}

/* ================================================ cuaderno de corridas =====
   Probar combinaciones se hace CORRIENDO la búsqueda de nuevo, no moviendo
   umbrales sobre resultados ya vistos. Para que eso sea llevadero, cada
   corrida queda anotada con su configuración: se comparan entre sí y se puede
   volver a cualquiera con un clic. Ojo con leer el historial como un ranking
   — dos corridas con la MISMA config dan estrategias distintas (semilla
   aleatoria), así que la diferencia entre dos filas parecidas es varianza,
   no necesariamente que una configuración sea mejor. */
const MAX_RUNS = 24;

function recordRun(result) {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  const bank = result.databank || [];
  const best = bank[0]?.metrics;
  S.runs.unshift({
    at: Date.now(),
    instrument: ds ? ds.name.replace(/ M1.*/, "") : "—",
    tf: S.sel.timeframe || "1h",
    dir: S.cfg.direction,
    risk: S.cfg.riskPct, rr: S.cfg.rr,
    minTrades: S.cfg.minTrades,
    crit: CRITERIA.filter(cr => S.cfg.critOn[cr.key])
      .map(cr => ({ k: cr.key, v: S.cfg[cr.key] })),
    method: S.cfg.method,
    goal: S.cfg.goal,
    seed: result.seed,
    tested: result.tested, kept: bank.length,
    elapsed: result.elapsed_s,
    ended: result.stopped ? "detenida" : result.reached_goal ? "completa" : "sin llegar",
    best: best ? {
      cagr: best.cagr_pct, pf: best.profit_factor,
      dd: best.max_drawdown_pct, trades: best.trades,
    } : null,
  });
  S.runs = S.runs.slice(0, MAX_RUNS);
  localStorage.setItem("qf.runs", JSON.stringify(S.runs));
}

function critLabel(list) {
  if (!list.length) return "sin filtros";
  return list.map(c => `${CRIT_BY_KEY[c.k].label} ${c.v}${CRIT_BY_KEY[c.k].unit}`).join(" · ");
}

function renderRunHistory() {
  const host = $("#m-runs");
  if (!host) return;
  if (!S.runs.length) { host.innerHTML = ""; return; }
  const bestCagr = Math.max(...S.runs.map(r => r.best?.cagr ?? -Infinity));

  host.innerHTML = `
  <div class="card">
    <h2>Cuaderno de corridas
      <span class="hint">${S.runs.length} experimento${S.runs.length === 1 ? "" : "s"} ·
        clic en “repetir” para volver a esa configuración</span>
      <button class="linkbtn" id="runs-clear" style="margin-left:auto">Borrar historial</button></h2>
    <div class="scroll-x"><table class="runs">
      <thead><tr><th>Cuándo</th><th>Mercado</th><th>Riesgo</th><th>Filtros</th>
        <th class="num">Probadas</th><th class="num">Encontradas</th>
        <th class="num">Mejor anual</th><th class="num">PF</th><th class="num">DD</th><th></th></tr></thead>
      <tbody>${S.runs.map((r, i) => `
        <tr class="${r.best && r.best.cagr === bestCagr ? "best-run" : ""}">
          <td class="muted">${new Date(r.at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}
            <div class="run-sub">${esc(r.ended)} · ${fmtDur(r.elapsed)}</div></td>
          <td><b>${esc(r.instrument)}</b><div class="run-sub">${esc(r.tf)} · ${
            r.dir === "long" ? "largos" : r.dir === "short" ? "cortos" : "ambos"} · semilla ${r.seed}</div></td>
          <td>${r.risk}% <span class="muted">1:${r.rr}</span>
            <div class="run-sub">${r.minTrades}+ trades</div></td>
          <td class="run-crit">${esc(critLabel(r.crit))}</td>
          <td class="num">${fmtInt(r.tested)}</td>
          <td class="num"><b>${r.kept}</b><span class="muted">/${r.goal}</span></td>
          <td class="num ${r.best && r.best.cagr >= 0 ? "pos" : "neg"}">
            <b>${r.best ? fmtPct(r.best.cagr) : "—"}</b></td>
          <td class="num">${r.best ? fmtNum(r.best.pf) : "—"}</td>
          <td class="num neg">${r.best ? fmtNum(r.best.dd, 0) + "%" : "—"}</td>
          <td class="num"><button class="btn ghost small" data-redo="${i}">Repetir</button></td>
        </tr>`).join("")}</tbody></table></div>
    <p class="stage-note">Dos corridas con la misma configuración dan estrategias distintas
      (la semilla es aleatoria): si dos filas parecidas dan resultados distintos, eso es varianza
      de la búsqueda, no una configuración mejor que la otra.</p>
  </div>`;

  $$("[data-redo]", host).forEach(b => b.onclick = () => {
    const r = S.runs[+b.dataset.redo];
    S.cfg.riskPct = r.risk; S.cfg.rr = r.rr;
    S.cfg.minTrades = r.minTrades; S.cfg.goal = r.goal;
    S.cfg.direction = r.dir; S.cfg.method = r.method;
    S.cfg.critOn = {};
    r.crit.forEach(c => { S.cfg.critOn[c.k] = true; S.cfg[c.k] = c.v; });
    S.sel.timeframe = r.tf;
    const ds = S.datasets.find(d => d.name.replace(/ M1.*/, "") === r.instrument);
    if (ds) S.sel.dataset_id = ds.id;
    saveCfg();
    navigate("mining").then(() => toast("Configuración cargada — dale a Iniciar", "ok"));
  });

  $("#runs-clear", host).onclick = () => {
    S.runs = [];
    localStorage.removeItem("qf.runs");
    renderRunHistory();
  };
}

/* Una vez que arrancó la búsqueda la configuración queda congelada: si se
   pudieran mover los filtros con los resultados a la vista, elegir el umbral
   pasaría a ser parte del ajuste (data snooping) y el databank mostraría lo
   que quedó lindo en ESTE histórico, no lo que tiene ventaja real. Para
   cambiar algo hay que detener y volver a minar — corrida nueva, criterios
   fijados de antemano. */
function lockSetup(on) {
  const setup = $(".setup");
  if (!setup) return;
  setup.classList.toggle("locked", on);
  $$(".setup-scroll input, .setup-scroll select, .setup-scroll button", setup)
    .forEach(el => { el.disabled = on; });
  $("#m-goal", setup).disabled = on;
  $$("#m-goal-presets button", setup).forEach(b => { b.disabled = on; });
  $("#lock-note")?.remove();
  if (on) {
    const note = document.createElement("div");
    note.id = "lock-note";
    note.className = "lock-note";
    note.innerHTML = `<span>🔒</span><div>Configuración congelada mientras busca.
      Cambiar los criterios viendo los resultados sería elegirlos a medida del histórico.
      <b>Detené</b> para ajustar y volver a minar.</div>`;
    $(".setup-run", setup)?.prepend(note);
  }
}

/* Los costos del broker salen del dataset elegido, nunca se heredan del
   anterior. (Las salidas ya no necesitan esto: van en volatilidad.) */
function adoptInstrumentDefaults() {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  if (!ds) return;
  if (ds.suggested_spread != null) S.cfg.spread = ds.suggested_spread;
  if (ds.suggested_slippage != null) S.cfg.slippage = ds.suggested_slippage;
  saveCfg();
}

/* ¿Los costos guardados tienen sentido en el instrumento actual? Un spread de
   0.36 (S&P) sobre EURUSD a 1.15 es 31% por operación: todas las candidatas
   dan -100% y parece que la app estuviera rota. Se corrige ANTES de dibujar. */
function fixInheritedScale() {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  if (!ds || !ds.last_close) return null;
  const costPct = (+S.cfg.spread + 2 * +S.cfg.slippage) / ds.last_close * 100;
  if (costPct <= 1.0) return null;
  adoptInstrumentDefaults();
  return { name: ds.name.replace(/ M1.*/, ""), badCost: true, costPct };
}

/* lee todos los inputs [data-cfg] hacia S.cfg */
function harvestCfg(root) {
  $$("[data-cfg]", root).forEach(el => {
    const k = el.dataset.cfg;
    if (el.type !== "number") { S.cfg[k] = el.value; return; }
    // un campo vacío daba 0, y el backend lo subía al mínimo (10 candidatas):
    // la búsqueda terminaba al instante sin que nadie entendiera por qué
    const n = parseFloat(el.value);
    if (!Number.isFinite(n)) { el.value = S.cfg[k] ?? DEFAULT_CFG[k] ?? 0; return; }
    // el mínimo de cada criterio manda (el max DD no admite menos de 4%)
    const cr = CRIT_BY_KEY[k];
    S.cfg[k] = cr ? Math.max(n, cr.min) : n;
  });
  saveCfg();
}

function progressHtml(id) {
  return `<div class="progress-wrap" id="${id}">
    <div class="progress-bar"><div></div></div>
    <span class="progress-msg"></span></div>`;
}
function setProgress(id, job) {
  const box = $(`#${id}`);
  if (!box) return;
  box.classList.add("show");
  // sin progreso todavía: barra indeterminada en vez de una barra vacía que
  // se lee como "no está pasando nada"
  const indet = !job.progress;
  $(".progress-bar", box).classList.toggle("indet", indet);
  $(".progress-bar > div", box).style.width = indet ? "38%" : `${(job.progress * 100).toFixed(1)}%`;
  $(".progress-msg", box).textContent = job.message || `${(job.progress * 100).toFixed(0)}%`;
}
function hideProgress(id) { $(`#${id}`)?.classList.remove("show"); }

function bindChips(root, sel) {
  $$(sel + " .chip", root).forEach(c => c.onclick = () => c.classList.toggle("on"));
}
function chipValues(root, sel) {
  return $$(sel + " .chip.on", root).map(c => c.dataset.tid);
}

/* ------------------------------------------------------------- navigation */
const PAGES = {};

async function refreshDatasets() {
  [S.datasets, S.catalog] = await Promise.all([
    api.get("/api/datasets"), api.get("/api/catalog"),
  ]);
  if (S.sel.dataset_id && !S.datasets.some(d => d.id === S.sel.dataset_id)) {
    S.sel.dataset_id = null;
  }
  if (!S.sel.dataset_id && S.datasets.length) S.sel.dataset_id = S.datasets[0].id;
}

async function navigate(page) {
  S.page = page;
  $$("#nav button").forEach(b => b.classList.toggle("active", b.dataset.page === page));
  const main = $("#main");
  main.innerHTML = "";
  await PAGES[page](main);
  main.scrollTop = 0;
}

/* ============================================================ página DATOS */
PAGES.data = async (main) => {
  await refreshDatasets();

  const cards = S.catalog.map(c => {
    const ready = !!c.dataset_id;
    return `<div class="inst-card ${ready ? "ready" : ""}">
      <div class="inst-top"><h3>${esc(c.label)}</h3>
        <span class="cat">${esc(c.category)}</span></div>
      <p>${esc(c.full_name)} · ${esc(c.note)}</p>
      ${ready
        ? `<div class="inst-meta">✓ ${c.rows.toLocaleString()} velas M1<br>
             ${esc(String(c.start).slice(0, 10))} → ${esc(String(c.end).slice(0, 10))}</div>
           <button class="btn ghost" data-mine="${c.dataset_id}" data-key="${c.key}">Minar este</button>`
        : `<div class="inst-meta">Historial M1 desde ${esc(c.from)}</div>
           <button class="btn" data-dl="${c.key}">↓ Descargar</button>`}
    </div>`;
  }).join("") + `
    <button class="inst-card add-card" id="inst-add">
      <span class="add-plus">+</span>
      <b>Agregar símbolo o data</b>
      <span>Importá cualquier CSV de MT4/MT5, TradingView, Dukascopy o Binance</span>
    </button>`;

  const rows = S.datasets.map(d => `
    <tr>
      <td><b>${esc(d.name)}</b></td>
      <td><span class="badge ${d.source === "sample" ? "yellow" : "green"}">${
        d.source === "sample" ? "sintético" : esc(d.source)}</span></td>
      <td class="num">${d.rows.toLocaleString()}</td>
      <td class="muted">${esc(String(d.start).slice(0, 16))}</td>
      <td class="muted">${esc(String(d.end).slice(0, 16))}</td>
      <td>${esc(d.timeframe)}</td>
      <td class="num"><button class="btn ghost small" data-del="${d.id}">Borrar</button></td>
    </tr>`).join("");

  main.innerHTML = `
  ${pageHead("Datos",
    "Los instrumentos más operados, listos para minar. Descargá con un clic o importá tu propio CSV.",
    ctxPill())}

  <div class="card">
    <h2>Biblioteca de instrumentos <span class="hint">M1 real de Dukascopy, en hora del servidor (NY+7)</span></h2>
    <div class="inst-grid">${cards}</div>
    ${progressHtml("dl-prog")}
  </div>

  <div class="card" id="imp-card">
    <h2>Importar tu propio CSV <span class="hint">MT4/MT5, TradingView, Dukascopy, Binance</span></h2>
    <div class="controls">
      <label class="fld" style="flex:1; min-width:320px"><span>Ruta del archivo en esta PC</span>
        <input id="imp-path" type="text" style="width:100%"
          placeholder="C:\\Users\\...\\Downloads\\SP500_M1.csv"></label>
      <label class="fld"><span>Nombre</span><input id="imp-name" type="text" placeholder="opcional"></label>
      <button class="btn" id="imp-go">Importar</button>
      <label class="fld"><span>…o subir archivo chico</span><input id="up-file" type="file" accept=".csv,.txt"></label>
    </div>
    ${progressHtml("imp-prog")}
  </div>

  <div class="card">
    <h2>Datasets en el workspace</h2>
    ${S.datasets.length ? `<div class="scroll-x"><table>
      <thead><tr><th>Nombre</th><th>Fuente</th><th class="num">Velas</th>
        <th>Desde</th><th>Hasta</th><th>TF</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>`
      : `<div class="empty-state"><div class="big">▤</div>
           <b>Todavía no hay datos</b>
           <p class="mt">Descargá un instrumento de la biblioteca de arriba, o importá tu propio CSV.</p>
         </div>`}
  </div>`;

  $("#inst-add", main).onclick = () => {
    const card = $("#imp-card", main);
    card.scrollIntoView({ block: "center", behavior: "smooth" });
    card.classList.add("flash");
    setTimeout(() => card.classList.remove("flash"), 900);
    $("#imp-path", main).focus();
  };

  $$("[data-dl]", main).forEach(b => b.onclick = async () => {
    const key = b.dataset.dl;
    $$("[data-dl]", main).forEach(x => x.disabled = true);
    b.innerHTML = `<span class="spinner"></span> Descargando…`;
    try {
      const meta = await runJob("/api/datasets/download", { key },
        j => setProgress("dl-prog", j));
      toast(`${meta.name}: ${meta.rows.toLocaleString()} velas listas`, "ok");
      navigate("data");
    } catch (e) {
      toast(`Descarga fallida: ${e.message}`, "err");
      hideProgress("dl-prog");
      $$("[data-dl]", main).forEach(x => x.disabled = false);
      b.textContent = "↓ Descargar";
    }
  });

  $$("[data-mine]", main).forEach(b => b.onclick = () => {
    S.sel.dataset_id = b.dataset.mine;
    const entry = S.catalog.find(c => c.key === b.dataset.key);
    if (entry) { S.cfg.spread = entry.spread; S.cfg.slippage = entry.slippage; }
    S.mineResult = S.mineLive = null;
    saveCfg();
    navigate("mining");
  });

  $("#imp-go").onclick = async () => {
    const path = $("#imp-path").value.trim();
    if (!path) { toast("Pegá la ruta del CSV", "err"); return; }
    $("#imp-go").disabled = true;
    try {
      const meta = await runJob("/api/datasets/import-path",
        { path, name: $("#imp-name").value.trim() || undefined },
        j => setProgress("imp-prog", j));
      toast(`Importado: ${meta.name} (${meta.rows.toLocaleString()} velas)`, "ok");
      navigate("data");
    } catch (e) { toast(e.message, "err"); hideProgress("imp-prog"); }
    const btn = $("#imp-go"); if (btn) btn.disabled = false;
  };

  $("#up-file").onchange = async () => {
    const f = $("#up-file").files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await fetch("/api/datasets/upload", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json()).detail || r.status);
      const meta = await r.json();
      toast(`Subido: ${meta.name} (${meta.rows.toLocaleString()} velas)`, "ok");
      navigate("data");
    } catch (e) { toast(e.message, "err"); }
  };

  $$("[data-del]", main).forEach(b => b.onclick = async () => {
    if (!confirm("¿Borrar este dataset?")) return;
    await api.del(`/api/datasets/${b.dataset.del}`);
    toast("Dataset borrado", "ok");
    navigate("data");
  });
};

/* ==================================================== página MIS ESTRATEGIAS
   Lo que sobrevive a la corrida. Cada minado empieza de cero con una semilla
   nueva, así que sin este cajón una estrategia buena se pierde para siempre
   apenas volvés a minar con otros filtros. */
async function refreshSavedCount() {
  try {
    S.saved = await api.get("/api/strategies");
    const el = $("#saved-count");
    if (el) el.textContent = S.saved.length || "";
  } catch (e) { /* si el backend no responde ya hay un aviso arriba */ }
}

PAGES.saved = async (main) => {
  await refreshDatasets();
  await refreshSavedCount();
  const items = S.saved || [];

  if (!items.length) {
    main.innerHTML = pageHead("Mis estrategias",
      "Las estrategias que guardes quedan acá, aunque vuelvas a minar con otros filtros.") +
      `<div class="card"><div class="empty-state">
        <div class="big">◫</div>
        <b>Todavía no guardaste ninguna</b>
        <p class="mt">Cuando el minado encuentre una que te sirva, abrila y tocá
          <b>Guardar estrategia</b>. Se guarda con su instrumento, su timeframe y sus costos,
          así la podés volver a exportar meses después sin tener que minar de nuevo.</p>
        <button class="btn mt" id="go-mine">Ir a Mining</button>
      </div></div>`;
    $("#go-mine", main).onclick = () => navigate("mining");
    return;
  }

  const fila = (s) => {
    const t = s.meta || {}, m = t.metrics || {};
    const q = t.oos_ratio;
    return `<tr class="clickable" data-sid="${esc(s.id)}">
      <td><span class="strat-name">${esc(s.name)}</span>
          <div class="strat-blocks">${esc(t.blocks || "")}</div>
          <div class="strat-genes">${esc(t.genes_label || "")}</div></td>
      <td>${esc((t.dataset_name || "—").replace(/ M1.*/, ""))}
          <div class="muted" style="font-size:11px">${esc(t.timeframe || "")}
            ${t.direction === "short" ? "· cortos" : t.direction === "both" ? "· ambos" : "· largos"}</div></td>
      <td class="num ${(m.cagr_pct ?? 0) >= 0 ? "pos" : "neg"}"><b>${m.cagr_pct != null ? fmtPct(m.cagr_pct) : "—"}</b></td>
      <td class="num">${m.profit_factor != null ? fmtNum(m.profit_factor) : "—"}</td>
      <td class="num neg">${m.max_drawdown_pct != null ? fmtNum(m.max_drawdown_pct, 1) + "%" : "—"}</td>
      <td class="num">${q != null
        ? `<span class="oos-tag ${q >= 0.8 ? "good" : q >= 0.5 ? "mid" : "bad"}"><b>${fmtNum(q, 2)}×</b></span>`
        : `<span class="muted">—</span>`}</td>
      <td class="num">${m.trades ?? "—"}</td>
      <td class="muted" style="white-space:nowrap">${esc(String(s.updated).slice(0, 10))}</td>
      <td class="num" style="white-space:nowrap">
        <button class="btn ghost small" data-export="${esc(s.id)}">⬇ MQL5</button>
        <button class="btn ghost small" data-del-strat="${esc(s.id)}" title="Borrar">✕</button>
      </td>
    </tr>`;
  };

  main.innerHTML = pageHead("Mis estrategias",
    `${items.length} guardada${items.length === 1 ? "" : "s"}. Sobreviven a cualquier corrida nueva.`) +
    `<div class="card">
      <h2>Guardadas <span class="hint">clic en una fila para volver a analizarla</span></h2>
      <div class="scroll-x"><table>
        <thead><tr><th>Estrategia</th><th>Mercado</th><th class="num">Anual</th>
          <th class="num">PF</th><th class="num">Max DD</th>
          <th class="num" title="Profit factor fuera de muestra sobre el de adentro">Fuera de muestra</th>
          <th class="num">Trades</th><th>Guardada</th><th></th></tr></thead>
        <tbody>${items.map(fila).join("")}</tbody>
      </table></div>
    </div>`;

  $$("[data-sid]", main).forEach(tr => tr.onclick = (ev) => {
    if (ev.target.closest("button")) return;      // los botones tienen lo suyo
    const s = items.find(x => x.id === tr.dataset.sid);
    openSaved(s);
  });

  $$("[data-export]", main).forEach(b => b.onclick = async () => {
    const s = items.find(x => x.id === b.dataset.export);
    b.disabled = true;
    try {
      const safe = `QF_${s.name.replace(/[^\w]/g, "_")}`;
      const r = await fetch("/api/export/mql5", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec: s.spec, name: safe,
          dataset_id: (s.meta || {}).dataset_id,
          timeframe: (s.meta || {}).timeframe, metrics: (s.meta || {}).metrics }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || r.status);
      const url = URL.createObjectURL(new Blob([await r.text()], { type: "text/plain" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${safe}.mq5`; a.click();
      URL.revokeObjectURL(url);
      toast("EA descargado", "ok");
    } catch (e) { toast(e.message, "err"); }
    b.disabled = false;
  });

  $$("[data-del-strat]", main).forEach(b => b.onclick = async () => {
    const s = items.find(x => x.id === b.dataset.delStrat);
    if (!confirm(`¿Borrar "${s.name}"? No se puede deshacer.`)) return;
    try {
      await api.del(`/api/strategies/${s.id}`);
      toast("Estrategia borrada", "ok");
      navigate("saved");
    } catch (e) { toast(e.message, "err"); }
  });
};

/* Re-analiza una guardada sobre su propio instrumento y sus propios costos,
   no sobre lo que esté configurado ahora en la página de Mining. */
async function openSaved(s) {
  const t = s.meta || {};
  if (!t.dataset_id || !S.datasets.some(d => d.id === t.dataset_id)) {
    toast("El dataset con el que se minó ya no está en el workspace", "err");
    return;
  }
  const row = {
    name: s.name, blocks: t.blocks || "", genes_label: t.genes_label || "",
    spec: s.spec, metrics: t.metrics || {}, score: t.score,
    stop_mult: t.stop_mult, oos: t.oos, oos_ratio: t.oos_ratio,
    fitness: 0, spark: [],
  };
  openInspector(row, {
    dataset_id: t.dataset_id, timeframe: t.timeframe || "1h",
    settings: { spread: t.spread, slippage: t.slippage,
                commission_pct: t.commission, initial_capital: t.capital },
  });
}

/* =========================================================== página MINING */
PAGES.mining = async (main) => {
  await refreshDatasets();
  if (!S.datasets.length) {
    main.innerHTML = pageHead("Mining", "Buscá estrategias sobre datos reales.") +
      `<div class="card"><div class="empty-state"><div class="big">⛏</div>
        <b>No hay con qué minar todavía</b>
        <p class="mt">Andá a <b>Datos</b> y descargá un instrumento — con un clic queda listo.</p>
        <button class="btn mt" id="go-data">Ir a Datos</button>
      </div></div>`;
    $("#go-data", main).onclick = () => navigate("data");
    return;
  }

  // se corrige antes de dibujar: los inputs nacen con los valores del mercado
  // elegido en vez de arrastrar los del instrumento anterior
  const fixed = fixInheritedScale();

  const c = S.cfg;
  const dsOpts = S.datasets.map(d =>
    `<option value="${d.id}" ${d.id === S.sel.dataset_id ? "selected" : ""}>
       ${esc(d.name)} · ${d.rows.toLocaleString()} velas</option>`).join("");
  if (!S.sel.timeframe) S.sel.timeframe = "1h";
  const tfOpts = (S.meta?.timeframes || ["1h"]).map(t =>
    `<option ${t === S.sel.timeframe ? "selected" : ""}>${t}</option>`).join("");
  // arranque curado: los bloques mas usados y entendibles, no todos
  const DEFAULT_ON = new Set(["ema_cross", "price_ema", "rsi_reversal", "macd_cross",
                              "bollinger_revert", "donchian_break",
                              "ema_trend_filter", "adx_filter"]);
  const picked = S.cfg.blocks && S.cfg.blocks.length ? new Set(S.cfg.blocks) : DEFAULT_ON;
  const blockList = (kind) => `<div class="blocklist" data-kind="${kind}">` +
    (S.meta?.templates || []).filter(t => t.kind === kind).map(t => `
      <label class="blockitem ${picked.has(t.id) ? "on" : ""}">
        <input type="checkbox" data-tid="${t.id}" ${picked.has(t.id) ? "checked" : ""}>
        <span>${esc(t.label)}</span>
        <span class="cat-tag">${esc(t.category)}</span>
      </label>`).join("") + `</div>`;
  const opt = (val, cur, label) => `<option value="${val}" ${val === cur ? "selected" : ""}>${label || val}</option>`;

  const curDs = S.datasets.find(d => d.id === S.sel.dataset_id);
  const bounds = datasetBounds(curDs);
  const range = effectiveRange(curDs);

  const critRow = (cr) => {
    const on = !!S.cfg.critOn[cr.key];
    return `<div class="critrow ${on ? "on" : ""}" data-crit="${cr.key}">
      <label class="crit-check"><input type="checkbox" data-crit-on="${cr.key}" ${on ? "checked" : ""}>
        <span class="crit-label">${esc(cr.label)}</span></label>
      <input class="crit-val" type="number" data-cfg="${cr.key}" value="${S.cfg[cr.key] ?? cr.def}"
        min="${cr.min}" step="${cr.step}" ${on ? "" : "disabled"}>
      <span class="crit-unit">${cr.unit || ""}</span>
    </div>`;
  };

  main.innerHTML = `
  ${pageHead("Mining",
    "Elegís cuántas estrategias querés y la búsqueda no para hasta juntarlas.", ctxPill())}

  <div class="workbench">
    <aside class="setup">
      <div class="setup-scroll">
        <details class="sect">
          <summary><span class="sect-num n-indigo">1</span>
            <span class="sect-t"><b>Mercado</b><em id="sum-market">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="fld-stack">
              <label class="fld"><span>Instrumento</span><select id="sel-dataset">${dsOpts}</select></label>
              <label class="fld"><span>Timeframe <span class="hint">las velas M1 se agrupan a este TF</span></span>
                <select id="sel-timeframe">${tfOpts}</select></label>
              <label class="fld"><span>Dirección</span><select data-cfg="direction">
                ${opt("long", c.direction, "Solo largos")}${opt("both", c.direction, "Largos y cortos")}${opt("short", c.direction, "Solo cortos")}</select></label>
            </div>

            <div class="stage-sub">Período a minar</div>
            <div class="fld-pair">
              <label class="fld"><span>Desde</span>
                <input type="date" class="datefld" id="m-date-from"
                  min="${esc(bounds.lo)}" max="${esc(bounds.hi)}" value="${esc(range.from)}"></label>
              <label class="fld"><span>Hasta</span>
                <input type="date" class="datefld" id="m-date-to"
                  min="${esc(bounds.lo)}" max="${esc(bounds.hi)}" value="${esc(range.to)}"></label>
            </div>
            <p class="stage-note" id="m-dsnote"></p>

            <details class="adv" id="m-adv-oos">
              <summary><span class="adv-chev">›</span>Avanzado<em id="sum-oos"></em></summary>
              <div class="adv-body">
                <label class="fld"><span>Validación fuera de muestra</span>
                  <select data-cfg="oosPct">
                    ${opt(0, +c.oosPct, "Desactivada")}
                    ${opt(30, +c.oosPct, "Minar 70% · validar 30% (sugerido)")}
                    ${opt(20, +c.oosPct, "Minar 80% · validar 20%")}
                    ${opt(40, +c.oosPct, "Minar 60% · validar 40%")}
                  </select></label>
                <p class="help-note">Parte el período en dos: la búsqueda usa sólo el tramo
                  inicial y cada estrategia aceptada se vuelve a correr sobre el final, con
                  datos que <b>nunca vio</b>. El databank suma una columna que dice si la
                  ventaja se sostiene o se cae — que es lo que separa una estrategia real de
                  una casualidad bien ajustada al pasado.</p>
              </div>
            </details>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num n-teal">2</span>
            <span class="sect-t"><b>Bloques</b><em id="sum-blocks">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="stage-sub">Disparadores de entrada</div>
            <div class="blocklist-actions" data-for="m-drivers">
              <button data-all="1">Todos</button><button data-all="0">Ninguno</button></div>
            <div id="m-drivers">${blockList("driver")}</div>
            <div class="stage-sub">Filtros de contexto</div>
            <div class="blocklist-actions" data-for="m-filters">
              <button data-all="1">Todos</button><button data-all="0">Ninguno</button></div>
            <div id="m-filters">${blockList("filter")}</div>
            <label class="fld mt"><span>Máx. filtros por estrategia</span>
              <input type="number" data-cfg="maxFilters" value="${c.maxFilters}" min="0" max="4"></label>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num n-pink">3</span>
            <span class="sect-t"><b>Riesgo y salidas</b><em id="sum-risk">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="seg full" id="rk-sizing">
              <button data-v="risk" class="${c.sizing !== "lots" ? "on" : ""}">Riesgo % del capital</button>
              <button data-v="lots" class="${c.sizing === "lots" ? "on" : ""}">Lotes fijos</button>
            </div>

            <div class="knob mt" id="rk-risk-box" ${c.sizing === "lots" ? "hidden" : ""}>
              <div class="knob-head"><b>Riesgo por operación</b>
                <span class="knob-val"><input type="number" id="rk-risk" step="0.1" min="0.1" max="10"
                  value="${c.riskPct}"><em>%</em></span></div>
              <div class="goal-presets" id="rk-risk-presets">
                ${RISK_PRESETS.map(p => `<button data-v="${p}" class="${+c.riskPct === p ? "on" : ""}">${p}%</button>`).join("")}
              </div>
              <p class="help-note" id="m-riskhelp"></p>
            </div>

            <div class="knob mt" id="rk-lots-box" ${c.sizing === "lots" ? "" : "hidden"}>
              <div class="knob-head"><b>Volumen por operación</b>
                <span class="knob-val"><input type="number" id="rk-lots" step="0.01" min="0.01" max="100"
                  value="${c.lots}"><em>lotes</em></span></div>
              <div class="goal-presets" id="rk-lots-presets">
                ${LOT_PRESETS.map(p => `<button data-v="${p}" class="${+c.lots === p ? "on" : ""}">${p}</button>`).join("")}
              </div>
              <p class="help-note" id="m-lotshelp"></p>
            </div>

            <div class="knob mt">
              <div class="knob-head"><b>Relación riesgo / beneficio</b>
                <span class="knob-val"><em>1 :</em><input type="number" id="rk-rr" step="0.25" min="0.25" max="10"
                  value="${c.rr}"></span></div>
              <div class="goal-presets" id="rk-rr-presets">
                ${RR_PRESETS.map(p => `<button data-v="${p}" class="${+c.rr === p ? "on" : ""}">1:${p}</button>`).join("")}
              </div>
              <p class="help-note" id="m-rrhelp"></p>
            </div>

            <p class="stage-note mt">La <b>distancia</b> del stop no se configura: se mide en
              volatilidad (ATR) y el minero le busca a cada estrategia el múltiplo que le sirve,
              entre 1× y 5×. Por eso funciona igual en cualquier instrumento.</p>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num n-blue">4</span>
            <span class="sect-t"><b>Costos del broker</b><em id="sum-cost">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="fld-pair">
              <label class="fld"><span>Spread</span><input type="number" step="0.00001" data-cfg="spread" value="${c.spread}"></label>
              <label class="fld"><span>Slippage</span><input type="number" step="0.00001" data-cfg="slippage" value="${c.slippage}"></label>
            </div>
            <div class="fld-pair mt">
              <label class="fld"><span>Comisión % lado</span><input type="number" step="0.001" data-cfg="commission" value="${c.commission}"></label>
              <label class="fld"><span>Capital</span><input type="number" step="1000" data-cfg="capital" value="${c.capital}"></label>
            </div>
            <p class="stage-note" id="m-costnote"></p>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num n-amber">5</span>
            <span class="sect-t"><b>Filtros de aceptación</b><em id="sum-crit">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <p class="help-note">Una estrategia entra al databank si cumple TODO lo que esté tildado.
              Activá sólo lo que te importe: cada filtro extra hace la búsqueda más lenta.</p>
            <div class="critlist mt">
              <div class="critrow on always">
                <label class="crit-check"><input type="checkbox" checked disabled>
                  <span class="crit-label">Mínimo de operaciones</span></label>
                <input class="crit-val" type="number" data-cfg="minTrades" value="${c.minTrades}" min="1" step="5">
                <span class="crit-unit"></span>
              </div>
              ${CRITERIA.map(critRow).join("")}
            </div>
            <p class="help-note" id="m-crithelp"></p>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num n-violet">6</span>
            <span class="sect-t"><b>Avanzado</b><em id="sum-adv">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="fld-stack">
              <label class="fld"><span>Método de búsqueda</span><select data-cfg="method">
                ${opt("random", c.method, "Aleatorio (explora amplio)")}
                ${opt("evolution", c.method, "Evolutivo (mejora por generaciones)")}</select></label>
              <label class="fld"><span>Ordenar el databank por</span><select data-cfg="fitness">
                ${opt("composite", c.fitness, "QF Score (robustez) — recomendado")}${opt("net_profit", c.fitness, "Ganancia neta")}
                ${opt("profit_factor", c.fitness, "Profit factor")}${opt("sharpe", c.fitness, "Sharpe")}</select></label>
              <label class="fld"><span>Tope de seguridad
                  <span class="hint">candidatas máximas antes de rendirse</span></span>
                <input type="number" data-cfg="maxCandidates" value="${c.maxCandidates}" min="100" step="1000"></label>
            </div>
          </div>
        </details>
      </div>

      <div class="setup-run" id="m-runbar">
        <div class="goal-field">
          <span>Quiero encontrar</span>
          <div class="goal-input">
            <input type="number" id="m-goal" value="${c.goal}" min="1" max="1000" step="1">
            <em>estrategias que<br>cumplan los filtros</em>
          </div>
          <div class="goal-presets" id="m-goal-presets">
            ${GOAL_PRESETS.map(g => `<button data-goal="${g}" class="${+c.goal === g ? "on" : ""}">${g}</button>`).join("")}
          </div>
        </div>
        <button class="btn big" id="m-run">⛏ Iniciar mining</button>
        <button class="btn ghost big" id="m-stop" style="display:none">■ Detener</button>
        ${progressHtml("m-prog")}
      </div>
    </aside>

    <section class="results">
      <div id="m-live"></div>
      <div id="m-bank"></div>
      <div id="m-runs"></div>
    </section>
  </div>`;

  /* filtros de aceptación: el número sólo se puede tocar si el filtro está
     activado, y un filtro apagado no viaja al backend */
  $$("[data-crit-on]", main).forEach(cb => cb.onchange = () => {
    const key = cb.dataset.critOn;
    S.cfg.critOn[key] = cb.checked;
    const row = cb.closest(".critrow");
    row.classList.toggle("on", cb.checked);
    const val = $(".crit-val", row);
    val.disabled = !cb.checked;
    if (cb.checked) val.focus();
    saveCfg();
    updateNotes();
  });

  // checklist: marcar/desmarcar y atajos de todos/ninguno
  $$(".blockitem input", main).forEach(cb => cb.onchange = () => {
    cb.closest(".blockitem").classList.toggle("on", cb.checked);
    S.cfg.blocks = $$(".blockitem input", main).filter(x => x.checked).map(x => x.dataset.tid);
    saveCfg();
    updateNotes();
  });
  $$(".blocklist-actions button", main).forEach(b => b.onclick = () => {
    const on = b.dataset.all === "1";
    $$(`#${b.parentElement.dataset.for} .blockitem input`, main).forEach(cb => {
      cb.checked = on;
      cb.closest(".blockitem").classList.toggle("on", on);
    });
    S.cfg.blocks = $$(".blockitem input", main).filter(x => x.checked).map(x => x.dataset.tid);
    saveCfg();
    updateNotes();
  });

  /* las dos perillas del riesgo: campo + atajos, siempre sincronizados */
  function bindKnob(inputId, presetsId, key, min, max) {
    const input = $(`#${inputId}`, main);
    const sync = (v, syncInput) => {
      const n = Math.min(Math.max(+v || min, min), max);
      S.cfg[key] = n;
      if (syncInput) input.value = n;
      $$(`#${presetsId} button`, main).forEach(b => b.classList.toggle("on", +b.dataset.v === n));
      saveCfg();
      updateNotes();
    };
    input.oninput = () => { if (input.value !== "") sync(input.value, false); };
    input.onblur = () => sync(S.cfg[key], true);
    $$(`#${presetsId} button`, main).forEach(b => b.onclick = () => sync(b.dataset.v, true));
  }
  bindKnob("rk-risk", "rk-risk-presets", "riskPct", 0.1, 10);
  bindKnob("rk-lots", "rk-lots-presets", "lots", 0.01, 100);

  /* riesgo % vs lotes fijos: sólo se muestra el campo del modo elegido */
  $$("#rk-sizing button", main).forEach(b => b.onclick = () => {
    S.cfg.sizing = b.dataset.v;
    $$("#rk-sizing button", main).forEach(x => x.classList.toggle("on", x === b));
    $("#rk-risk-box", main).hidden = S.cfg.sizing === "lots";
    $("#rk-lots-box", main).hidden = S.cfg.sizing !== "lots";
    saveCfg();
    updateNotes();
  });
  bindKnob("rk-rr", "rk-rr-presets", "rr", 0.25, 10);

  const dsSel = $("#sel-dataset"), tfSel = $("#sel-timeframe");
  dsSel.onchange = () => {
    S.sel.dataset_id = dsSel.value;
    const ds = S.datasets.find(d => d.id === dsSel.value);
    const clamped = clampRangeTo(ds);   // el período elegido se conserva
    adoptInstrumentDefaults();          // costos del broker del mercado nuevo
    navigate("mining").then(() => {     // refresca la pastilla de contexto
      if (clamped) {
        toast(`${ds.name.replace(/ M1.*/, "")} no cubre todo ese período — ` +
              `las fechas se ajustaron a su historial`, "ok");
      }
    });
  };

  /* período a minar: campos libres + atajos para el split in/out-of-sample */
  const dFrom = $("#m-date-from", main), dTo = $("#m-date-to", main);
  const onDate = () => {
    S.sel.dateFrom = dFrom.value;
    S.sel.dateTo = dTo.value;
    saveCfg();
    updateNotes();
  };
  dFrom.onchange = onDate;
  dTo.onchange = onDate;
  // el calendario se abre tocando el campo entero, no sólo el iconito
  [dFrom, dTo].forEach(el => el.onmousedown = (ev) => {
    if (typeof el.showPicker !== "function") return;
    ev.preventDefault();
    el.focus();
    try { el.showPicker(); } catch (e) { /* el navegador lo abre solo */ }
  });

  tfSel.onchange = () => { S.sel.timeframe = tfSel.value; saveCfg(); updateNotes(); };
  $$("[data-cfg]", main).forEach(el => el.oninput = () => { harvestCfg(main); updateNotes(); });

  function updateNotes() {
    const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
    const dsNote = $("#m-dsnote");
    if (ds && dsNote) {
      const r = effectiveRange(ds);
      const full = isFullRange(ds);
      const years = (new Date(r.to) - new Date(r.from)) / (365.25 * 24 * 3600 * 1000);
      const oos = +S.cfg.oosPct;
      const base = full
        ? `Minando <b>todo</b> el historial: ${esc(r.from)} → ${esc(r.to)}
           (${years.toFixed(1)} años) · último precio <b>${ds.last_close}</b>`
        : `Minando <b>${esc(r.from)} → ${esc(r.to)}</b> (${years.toFixed(1)} años de
           ${esc(datasetBounds(ds).lo)} → ${esc(datasetBounds(ds).hi)})`;
      // si la validación está activa, el corte se calcula sobre ESE rango
      const corte = oos
        ? `<br>De ese tramo, la búsqueda ve el <b>${100 - oos}%</b> inicial y el
           <b>${oos}%</b> final queda reservado para validar.`
        : "";
      dsNote.innerHTML = base + corte;
    }
    updateSummaries(ds);
    const note = $("#m-costnote");
    if (note) {
      const abs = +S.cfg.spread + 2 * +S.cfg.slippage;
      const pct = ds && ds.last_close ? abs / ds.last_close * 100 + 2 * +S.cfg.commission : null;
      let txt = `Ida y vuelta: <b>${abs.toLocaleString(undefined, { maximumFractionDigits: 5 })}</b> de precio`;
      if (pct != null) txt += ` ≈ <b>${pct.toFixed(3)}%</b>`;
      txt += ". Debe coincidir con tu broker.";
      // un costo así se come cualquier estrategia: todas dan -100%
      const bad = pct != null && pct > 1;
      if (bad) {
        txt = `<b class="neg">⚠ Costo imposible: ${pct.toFixed(1)}% por operación.</b>
          Parece el spread de otro instrumento — con esto ninguna estrategia puede ganar.
          <button class="linkbtn" id="fix-cost">Usar los de ${esc(ds.name.replace(/ M1.*/, ""))}</button>`;
      }
      note.classList.toggle("danger", bad);
      note.innerHTML = txt;
      const fixC = $("#fix-cost", note);
      if (fixC) fixC.onclick = () => { adoptInstrumentDefaults(); navigate("mining"); };
    }

    // la perilla de riesgo traducida a plata, y a lo que implica en el año
    const riskHelp = $("#m-riskhelp");
    if (riskHelp) {
      const cap = +S.cfg.capital, v = +S.cfg.riskPct;
      const streak = lossStreakCost(v, 10);
      riskHelp.innerHTML =
        `Cada operación pone en juego <b>${v}%</b> ≈ <b>$${(cap * v / 100).toFixed(0)}</b> de tus
         $${fmtInt(cap)}; el tamaño de la posición se calcula solo para que tocar el stop cueste
         exactamente eso. <br>Multiplica en la misma proporción la ganancia y la caída de
         cualquier estrategia que encuentres: <b>10 pérdidas seguidas</b> se llevan el
         <b>${streak.toFixed(0)}%</b> de la cuenta.`;
      riskHelp.classList.toggle("danger-note", streak >= 25);
    }

    /* El porcentaje de aciertos no se puede leer solo: con relación 1:3 hasta
       un 30% es rentable, y pedir 60% ahí es casi imposible por construcción. */
    const critHelp = $("#m-crithelp");
    if (critHelp) {
      if (!S.cfg.critOn.minWinRate) {
        critHelp.innerHTML = "";
      } else {
        const rr = +S.cfg.rr, be = 100 / (1 + rr), pedido = +S.cfg.minWinRate;
        critHelp.innerHTML = pedido <= be
          ? `<b class="neg">⚠ ${pedido}% de aciertos no alcanza para ganar plata</b> con
             relación 1:${rr}: el punto de equilibrio está en <b>${be.toFixed(0)}%</b>.
             Por debajo de ahí, acertar más veces sigue dando pérdida.`
          : `Con relación 1:${rr} el equilibrio está en <b>${be.toFixed(0)}%</b>, así que
             pedís <b>${(pedido - be).toFixed(0)} puntos</b> de ventaja.${
               pedido - be > 15 ? " Es una vara muy alta: probá bajarla si no aparece nada."
                                : ""}`;
      }
    }

    const lotsHelp = $("#m-lotshelp");
    if (lotsHelp) {
      lotsHelp.innerHTML =
        `Siempre <b>${S.cfg.lots}</b> lote(s), pase lo que pase. Lo que arriesgás por operación
         deja de ser fijo: depende de la volatilidad del momento, porque el stop se mueve con
         el ATR. A cambio, el volumen es un número redondo que cualquier broker acepta sin
         recalcular nada — que es donde algunos CFDs se traban.`;
    }

    const rrHelp = $("#m-rrhelp");
    if (rrHelp) {
      const rr = +S.cfg.rr;
      // el break-even sale de la relación: con 1:2 alcanza con acertar 1 de 3
      const be = 100 / (1 + rr);
      rrHelp.innerHTML =
        `El objetivo vale <b>${rr}×</b> lo que arriesgás: ganás <b>$${(+S.cfg.capital * +S.cfg.riskPct / 100 * rr).toFixed(0)}</b>
         cuando acertás y perdés <b>$${(+S.cfg.capital * +S.cfg.riskPct / 100).toFixed(0)}</b> cuando no.
         Te alcanza con acertar <b>${be.toFixed(0)}%</b> de las veces para empatar.
         <br>Cuanto más lejos el objetivo, menos veces se acierta: el minero tiene que
         encontrar entradas que superen esa vara.`;
    }
  }

  /* resumen de una línea en cada sección plegada: se ve la configuración
     entera sin tener que abrirlas una por una */
  function updateSummaries(ds) {
    const set = (id, txt) => { const el = $(`#${id}`, main); if (el) el.textContent = txt; };
    const dirLbl = { long: "solo largos", short: "solo cortos", both: "largos y cortos" };
    set("sum-market", (ds ? `${ds.name.replace(/ M1.*/, "")} · ${S.sel.timeframe} · ${dirLbl[S.cfg.direction]}` : "—") +
      (+S.cfg.oosPct ? ` · valida ${S.cfg.oosPct}%` : ""));
    // el resumen del desplegable: se ve sin abrirlo
    set("sum-oos", +S.cfg.oosPct
      ? `mina ${100 - +S.cfg.oosPct}% · valida ${S.cfg.oosPct}%` : "");

    const drv = $$("#m-drivers .blockitem input", main).filter(x => x.checked).length;
    const flt = $$("#m-filters .blockitem input", main).filter(x => x.checked).length;
    set("sum-blocks", `${drv} disparadores · ${flt} filtros · hasta ${S.cfg.maxFilters} por estrategia`);

    set("sum-risk", `${S.cfg.sizing === "lots" ? `${S.cfg.lots} lotes fijos` : `${S.cfg.riskPct}% por operación`}` +
      ` · relación 1:${S.cfg.rr} · stop por volatilidad`);

    set("sum-cost", `spread ${S.cfg.spread} · slippage ${S.cfg.slippage} · capital $${fmtInt(S.cfg.capital)}`);

    const on = CRITERIA.filter(cr => S.cfg.critOn[cr.key]);
    set("sum-crit", on.length
      ? `${S.cfg.minTrades}+ trades · ${on.map(cr => cr.label.replace(/ [≥≤]$/, "")).join(" · ")}`
      : `sólo ${S.cfg.minTrades}+ operaciones — el resto sin filtrar`);

    set("sum-adv", `${S.cfg.method === "evolution" ? "evolutivo" : "aleatorio"} · ` +
      `tope ${fmtInt(S.cfg.maxCandidates)} candidatas`);
  }
  /* objetivo: input y atajos, siempre en sincronía */
  const goalInput = $("#m-goal", main);
  function setGoal(v, syncInput) {
    const n = Math.max(1, Math.min(Math.round(+v) || 1, 1000));
    S.cfg.goal = n;
    if (syncInput) goalInput.value = n;
    $$("#m-goal-presets button", main).forEach(b => b.classList.toggle("on", +b.dataset.goal === n));
    saveCfg();
  }
  goalInput.oninput = () => { if (goalInput.value !== "") setGoal(goalInput.value, false); };
  goalInput.onblur = () => setGoal(S.cfg.goal, true);   // un campo vacío vuelve al valor real
  $$("#m-goal-presets button", main).forEach(b => b.onclick = () => setGoal(b.dataset.goal, true));

  updateNotes();
  if (fixed) {
    toast(fixed.badCost
      ? `Costos y salidas ajustados a ${fixed.name}: el spread anterior era ${fixed.costPct.toFixed(1)}% del precio`
      : `Salidas ajustadas a la escala de ${fixed.name}`, "ok");
  }
  if (S.mineResult || S.mineLive) renderMining(S.mineResult || S.mineLive, !!S.mineResult);
  else renderIdle();
  renderRunHistory();

  $("#m-stop").onclick = async () => {
    if (S.mineJobId) {
      try { await api.post(`/api/jobs/${S.mineJobId}/stop`); toast("Deteniendo…"); }
      catch (e) { toast(e.message, "err"); }
    }
  };

  $("#m-run").onclick = async () => {
    harvestCfg(main);
    const checked = (sel) => $$(`${sel} .blockitem input`, main)
      .filter(cb => cb.checked).map(cb => cb.dataset.tid);
    const drivers = checked("#m-drivers");
    if (!drivers.length) { toast("Elegí al menos un disparador de entrada", "err"); return; }
    S.mining = true; S.mineResult = null; S.mineLive = null;
    $("#m-run").disabled = true;
    $("#m-stop").style.display = "";
    $("#m-runbar")?.classList.add("running");
    lockSetup(true);
    // pintar el estado "buscando" YA: el primer snapshot del backend tarda
    // varios segundos en un dataset grande y sin esto la app parece colgada
    renderMining({ seed: "—", tested: 0, passed: 0, rejected: 0, kept: 0,
                   target: S.cfg.maxCandidates, target_keep: S.cfg.goal,
                   elapsed_s: 0, databank: [], best_history: [], diagnosis: {} }, false);
    setProgress("m-prog", { progress: 0, message: "Preparando velas e indicadores…" });
    const cfg = S.cfg;
    try {
      const result = await runJob("/api/mine", {
        dataset_id: S.sel.dataset_id, timeframe: S.sel.timeframe || "1h",
        ...rangePayload(),
        drivers, filters: checked("#m-filters"),
        // el objetivo manda; max_candidates es solo el tope de seguridad
        target_keep: cfg.goal, keep_top: Math.max(cfg.goal, 100),
        oos_pct: +cfg.oosPct || 0,
        max_candidates: cfg.maxCandidates, max_filters: cfg.maxFilters,
        method: cfg.method, population: 40,
        direction: cfg.direction, min_trades: cfg.minTrades, fitness: cfg.fitness,
        // un filtro sin tildar viaja como null: el backend lo ignora
        ...acceptPayload(),
        risk: riskPayload(),
        settings: {
          spread: cfg.spread, slippage: cfg.slippage,
          commission_pct: cfg.commission, initial_capital: cfg.capital,
        },
      }, j => {
        setProgress("m-prog", j);
        if (j.partial) { S.mineLive = j.partial; renderMining(j.partial, false); }
      }, id => { S.mineJobId = id; });
      S.mineResult = result;
      hideProgress("m-prog");
      recordRun(result);
      renderMining(result, true);
      renderRunHistory();
      const kept = result.databank.length;
      if (result.stopped) toast(`Detenido — ${kept} estrategias en el databank`, "ok");
      else if (result.reached_goal)
        toast(`Databank lleno: ${kept} estrategias en ${fmtDur(result.elapsed_s)}`, "ok");
      else toast(`Se probaron ${fmtInt(result.tested)} y sólo ${kept} pasaron los filtros`, "err");
    } catch (e) { toast(e.message, "err"); hideProgress("m-prog"); }
    S.mining = false; S.mineJobId = null;
    const run = $("#m-run"), stop = $("#m-stop");
    if (run) run.disabled = false;
    if (stop) stop.style.display = "none";
    $("#m-runbar")?.classList.remove("running");
    lockSetup(false);
  };
};

/* La columna de resultados antes de la primera corrida: explica el flujo y
   confirma qué se va a buscar, en vez de mostrar un hueco vacío. */
function renderIdle() {
  const live = $("#m-live"), bankBox = $("#m-bank");
  if (!live) return;
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  const on = CRITERIA.filter(cr => S.cfg.critOn[cr.key]);
  live.innerHTML = `
  <div class="idle-card">
    <div class="idle-ready">
      <span class="idle-ic">⛏</span>
      <div>
        <h2>Listo para minar</h2>
        <p>Vas a buscar <b>${S.cfg.goal} estrategias</b> sobre
          <b>${esc(ds ? ds.name.replace(/ M1.*/, "") : "—")}</b> en velas de
          <b>${esc(S.sel.timeframe || "1h")}</b>, ${S.cfg.sizing === "lots"
            ? `con <b>${S.cfg.lots} lotes fijos</b>` : `arriesgando <b>${S.cfg.riskPct}%</b> por operación`}
          y relación <b>1:${S.cfg.rr}</b>.
          Entran al databank las que hagan <b>${S.cfg.minTrades}+ operaciones</b>${
            on.length ? ` y cumplan: ${on.map(cr => `<b>${esc(cr.label)} ${S.cfg[cr.key]}${cr.unit}</b>`).join(", ")}` : ""}.</p>
        ${on.length ? "" : `<p class="idle-warn">Sin filtros activos entra cualquier estrategia,
          incluso las que pierden plata. Tildá <b>Profit factor ≥ 1</b> en la sección 5 para
          quedarte sólo con las ganadoras.</p>`}
      </div>
    </div>
    <div class="guide-steps">
      <div class="gstep"><span class="gnum g-indigo">1</span><b>Se arma una candidata</b>
        <p>Combina al azar un disparador de entrada, filtros de contexto y los parámetros de cada indicador.</p></div>
      <div class="gstep"><span class="gnum g-teal">2</span><b>Se backtestea entera</b>
        <p>Sobre todos los años de datos reales, con tus costos y tu modelo de riesgo.</p></div>
      <div class="gstep"><span class="gnum g-pink">3</span><b>Pasa o se descarta</b>
        <p>Si cumple los filtros entra al databank ordenada por fitness; si no, se tira y se prueba otra.</p></div>
      <div class="gstep"><span class="gnum g-amber">4</span><b>Se repite sin parar</b>
        <p>Hasta juntar las ${S.cfg.goal} que pediste. Cada una se puede inspeccionar y exportar a MetaTrader.</p></div>
    </div>
  </div>`;
  if (bankBox) bankBox.innerHTML = "";
}

/* Cuánto sobrevivió la ventaja fuera de muestra. Es la única columna del
   databank que no está contaminada por haber elegido la estrategia mirando
   esos mismos datos, así que se muestra con su propio semáforo. */
function oosCell(r) {
  const oos = r.oos;
  if (!oos) return `<span class="muted">—</span>`;
  if (!oos.trades) {
    return `<span class="oos-tag none" title="No operó en el tramo reservado: no hay nada que validar">sin datos</span>`;
  }
  const q = r.oos_ratio;
  const cls = q >= 0.8 ? "good" : q >= 0.5 ? "mid" : "bad";
  const etiqueta = q >= 0.8 ? "se sostiene" : q >= 0.5 ? "se debilita" : "se cae";
  return `<span class="oos-tag ${cls}"
    title="Profit factor ${fmtNum(oos.profit_factor)} fuera de muestra contra ${fmtNum(r.metrics.profit_factor)} adentro · ${oos.trades} operaciones · ${fmtPct(oos.net_profit_pct)}">
    <b>${fmtNum(q, 2)}×</b><em>${etiqueta}</em></span>`;
}

/* ------------------------------------------------------- render resultados */
function renderMining(snap, finished) {
  const live = $("#m-live"), bankBox = $("#m-bank");
  if (!live || !snap) return;
  const bank = snap.databank || [];
  const champ = bank[0];

  const goal = snap.target_keep || null;
  const kept = goal ? Math.min(bank.length, goal) : bank.length;
  const frac = goal ? kept / goal : (snap.tested / (snap.target || 1));
  const rate = snap.tested && snap.elapsed_s > 0 ? snap.passed / snap.elapsed_s : 0;
  // sin filtros activos el databank también junta perdedoras: decirlo de frente
  const winners = bank.filter(r => r.metrics.net_profit_pct > 0).length;

  // por qué terminó: el usuario no tiene que deducirlo de los números
  let banner = "";
  if (finished && snap.stopped) {
    banner = `<div class="banner info"><span class="b-ic">■</span><div>
      <b>Búsqueda detenida por vos.</b> ${bank.length === 1
        ? "La estrategia que ya había entrado al databank sigue"
        : `Las ${bank.length} estrategias que ya habían entrado al databank siguen`}
      acá abajo, lista${bank.length === 1 ? "" : "s"} para inspeccionar o exportar.</div></div>`;
  } else if (finished && snap.exhausted) {
    banner = `<div class="banner"><span class="b-ic">◍</span><div>
      <b>Se agotaron las combinaciones posibles</b> con los bloques que marcaste.
      Marcá más bloques en la sección 2 o subí el máximo de filtros para ampliar el espacio.</div></div>`;
  } else if (finished && snap.hit_cap) {
    banner = `<div class="banner"><span class="b-ic">⚠</span><div>
      <b>Se llegó al tope de seguridad de ${fmtInt(snap.target)} candidatas</b> con
      ${bank.length} de ${goal} estrategias. Tus filtros son muy exigentes para este mercado:
      destildá alguno en la sección 5, cambiá las salidas en la 3, o subí el tope en Avanzado
      si querés que siga buscando más tiempo.</div></div>`;
  } else if (!finished && !bank.length && snap.tested >= 20 && snap.diagnosis?.text) {
    // no esperar al final para explicar por qué no entra ninguna: el usuario
    // puede aflojar el filtro ahora mismo en vez de mirar un cero por minutos
    banner = `<div class="banner"><span class="b-ic">◎</span><div>${snap.diagnosis.text}</div></div>`;
  } else if (finished && goal && snap.reached_goal) {
    banner = `<div class="banner ok"><span class="b-ic">✓</span><div>
      <b>Objetivo cumplido.</b> ${goal} estrategias que cumplen todos los filtros, encontradas
      probando ${fmtInt(snap.tested)} candidatas en ${fmtDur(snap.elapsed_s)}.</div></div>`;
  }

  const goalCard = `
  <div class="goalcard ${finished ? "" : "running"}">
    <div class="ring">${Charts.ringSvg(frac)}
      <div class="ring-label">
        <b>${goal ? `${kept}/${goal}` : fmtInt(snap.tested)}</b>
        <span>${goal ? "en el databank" : "probadas"}</span>
      </div>
    </div>
    <div class="goal-side">
      <div class="goal-title">
        <h2>${finished ? "Búsqueda terminada" : "Buscando estrategias"}</h2>
        ${finished ? "" : `<span class="mining-live">
          <span class="scanner"><i></i><i></i><i></i><i></i><i></i></span>
          ${snap.tested ? `probando candidata #${fmtInt(snap.tested + 1)}` : "preparando indicadores…"}
        </span>`}
      </div>
      <div class="goal-sub">${goal
        ? `No se detiene hasta juntar <b>${goal}</b> que cumplan los filtros — faltan <b>${Math.max(goal - kept, 0)}</b>.`
        : `Probando candidatas hasta llegar a <b>${fmtInt(snap.target)}</b>.`}
        · semilla <b>${snap.seed}</b> para reproducir esta corrida</div>
      <div class="statgrid">
        <div class="stat"><span>Probadas</span><b>${fmtInt(snap.tested)}</b></div>
        <div class="stat"><span>Con ganancia</span><b class="${winners ? "pos" : "neg"}">${winners}<u>de ${bank.length}</u></b></div>
        <div class="stat"><span>Tasa de éxito</span><b>${snap.tested ? (snap.passed / snap.tested * 100).toFixed(1) : "0.0"}<u>%</u></b></div>
        <div class="stat"><span>${finished ? "Duración" : "Transcurrido"}</span><b>${fmtDur(snap.elapsed_s)}</b></div>
        ${!finished && goal ? `<div class="stat"><span>Falta aprox.</span><b>${
          snap.eta_s != null ? fmtDur(snap.eta_s) : "—"}</b></div>` : ""}
        <div class="stat"><span>Ritmo</span><b>${rate ? rate.toFixed(2) : "—"}<u>acept./s</u></b></div>
      </div>
      ${banner}
    </div>
  </div>`;

  const champCardHtml = champ ? `<div class="champ" id="champ-card">
    <div>
      <div class="champ-tag">${finished ? "★ Mejor QF Score" : "★ Mejor hasta ahora"}</div>
      <h2>${esc(champ.name)} ${scoreBadge(champ.score, "big")}</h2>
      <div class="champ-blocks">${esc(champ.blocks || "")}</div>
      <div class="champ-genes">${esc(champ.genes_label)}</div>
      <div class="champ-spark">${Charts.sparkSvg(champ.spark, { width: 240, height: 54 })}</div>
      ${scoreBars(champ.score_parts)}
      <div class="champ-cta">Ver análisis completo →</div>
    </div>
    <div class="champ-metrics">
      <div><span>Anual (CAGR)</span><b class="${champ.metrics.cagr_pct >= 0 ? "pos" : "neg"}">${fmtPct(champ.metrics.cagr_pct)}</b></div>
      <div><span>Total ${champ.metrics.years ? `${fmtNum(champ.metrics.years, 1)} años` : ""}</span><b class="${champ.metrics.net_profit_pct >= 0 ? "pos" : "neg"}">${fmtPct(champ.metrics.net_profit_pct)}</b></div>
      <div><span>Profit factor</span><b>${fmtNum(champ.metrics.profit_factor)}</b></div>
      <div><span>Sharpe</span><b>${fmtNum(champ.metrics.sharpe)}</b></div>
      <div><span>Max DD</span><b class="neg">${fmtNum(champ.metrics.max_drawdown_pct, 1)}%</b></div>
      <div><span>En mercado</span><b>${fmtNum(champ.metrics.exposure_pct ?? 0, 1)}%</b></div>
      <div><span>Trades</span><b>${champ.metrics.trades}</b></div>
    </div>
  </div>` : "";

  // mientras corre manda el progreso; al terminar, manda el ganador
  live.innerHTML = (finished ? champCardHtml + goalCard : goalCard + champCardHtml) +
    (snap.best_history?.length > 1 ? `<div class="card">
       <h2>Evolución del mejor fitness <span class="hint">cómo fue mejorando la búsqueda</span></h2>
       <div class="chart-box short" id="m-hist"></div></div>` : "");

  if (snap.best_history?.length > 1) {
    Charts.line($("#m-hist"), { series: [{ values: snap.best_history, fill: true }], height: 170 });
  }
  const champCard = $("#champ-card");
  if (champCard) champCard.onclick = () => openInspector(champ);

  const splitNote = snap.split ? `
    <div class="banner info mt" style="margin-bottom:14px">
      <span class="b-ic">◫</span><div>
        <b>Validado fuera de muestra.</b> La búsqueda usó
        ${esc(snap.split.is_from)} → ${esc(snap.split.is_to)}
        (${fmtInt(snap.split.is_bars)} velas) y cada estrategia se volvió a correr sobre
        ${esc(snap.split.oos_from)} → ${esc(snap.split.oos_to)}
        (${fmtInt(snap.split.oos_bars)} velas) que nunca vio.
        La columna <b>Fuera de muestra</b> es la que dice si la ventaja era real.</div>
    </div>` : "";

  bankBox.innerHTML = `
  <div class="card">
    ${splitNote}
    <h2>Databank <span class="hint">${bank.length} estrategias ordenadas por QF Score
      (robustez, no rentabilidad) · clic en cualquiera para analizarla a fondo</span></h2>
    ${bank.length ? `<div class="databank-wrap"><table>
      <thead><tr><th>#</th><th class="num">Score</th><th>Estrategia</th><th>Curva</th>
        ${snap.split ? `<th class="num" title="Profit factor fuera de muestra dividido por el de adentro. Cerca de 1 la ventaja se sostuvo; cerca de 0 la estrategia sólo describía el pasado.">Fuera<br>de muestra</th>` : ""}
        <th class="num">Stop</th><th class="num">Anual</th><th class="num">Total</th>
        <th class="num">PF</th><th class="num">Sharpe</th><th class="num">Max DD</th>
        <th class="num">Meses +</th><th class="num">Mejor op.</th>
        <th class="num">Expo.</th><th class="num">Win %</th>
        <th class="num">Trades</th></tr></thead>
      <tbody>${bank.map((r, i) => {
        const m = r.metrics;
        return `<tr class="clickable" data-row="${i}" style="animation-delay:${Math.min(i, 12) * 22}ms">
          <td><span class="rank">${i + 1}</span></td>
          <td class="num">${scoreBadge(r.score)}</td>
          <td><span class="strat-name">${esc(r.name)}</span>
              <div class="strat-blocks">${esc(r.blocks || "")}</div>
              <div class="strat-genes">${esc(r.genes_label)}</div></td>
          <td class="spark-cell">${Charts.sparkSvg(r.spark)}</td>
          ${snap.split ? `<td class="num">${oosCell(r)}</td>` : ""}
          <td class="num muted">${r.stop_mult != null ? `${fmtNum(r.stop_mult, 2)}×` : "—"}</td>
          <td class="num ${m.cagr_pct >= 0 ? "pos" : "neg"}"><b>${fmtPct(m.cagr_pct)}</b></td>
          <td class="num ${m.net_profit_pct >= 0 ? "pos" : "neg"}">${fmtPct(m.net_profit_pct)}</td>
          <td class="num">${fmtNum(m.profit_factor)}</td>
          <td class="num">${fmtNum(m.sharpe)}</td>
          <td class="num neg">${fmtNum(m.max_drawdown_pct, 1)}%</td>
          <td class="num">${fmtNum(m.months_positive_pct ?? 0, 0)}%</td>
          <td class="num ${(m.top_trade_share_pct ?? 0) > 35 ? "neg" : "muted"}">${fmtNum(m.top_trade_share_pct ?? 0, 0)}%</td>
          <td class="num muted">${fmtNum(m.exposure_pct ?? 0, 1)}%</td>
          <td class="num">${fmtNum(m.win_rate_pct, 1)}%</td>
          <td class="num">${m.trades}</td>
        </tr>`;
      }).join("")}</tbody></table></div>`
      : `<div class="empty-state">
           <div class="big">ðŸ”</div>
           <b>${fmtInt(snap.tested)} probadas, ninguna pasó los filtros.</b>
           ${snap.diagnosis?.text ? `<p class="mt">${snap.diagnosis.text}</p>` : ""}
           ${snap.diagnosis?.suggestion ? `
             <div class="suggestion mt">
               <div class="sug-title">💡 Cómo llegar a ese objetivo</div>
               <p>${snap.diagnosis.suggestion.text}</p>
               ${snap.diagnosis.suggestion.warning
                 ? `<p class="sug-warn">⚠ ${esc(snap.diagnosis.suggestion.warning)}</p>` : ""}
               ${snap.diagnosis.suggestion.unreachable
                 ? `<button class="btn small mt" id="apply-target"
                      data-target="${snap.diagnosis.suggestion.realistic_target}">
                      Fijar objetivo en ${snap.diagnosis.suggestion.realistic_target}% anual</button>`
                 : `<button class="btn small mt" id="apply-risk"
                      data-needed="${snap.diagnosis.suggestion.needed}">
                      Subir a ${snap.diagnosis.suggestion.needed}% y volver a minar</button>`}
             </div>` : ""}
           <p class="mt muted">También podés destildar filtros en la sección 5, o cambiar las
             salidas en la 3 — eso cambia por completo qué estrategias funcionan.</p>
         </div>`}
  </div>`;

  $$("[data-row]", bankBox).forEach(tr => tr.onclick = () => openInspector(bank[+tr.dataset.row]));

  const applyRisk = $("#apply-risk", bankBox);
  if (applyRisk) applyRisk.onclick = () => {
    S.cfg.riskPct = +applyRisk.dataset.needed;
    saveCfg();
    navigate("mining").then(() => {
      toast(`Riesgo ajustado a ${S.cfg.riskPct}% — dale a Iniciar mining`, "ok");
      $("#m-run")?.scrollIntoView({ block: "center" });
    });
  };

  const applyTarget = $("#apply-target", bankBox);
  if (applyTarget) applyTarget.onclick = () => {
    const sug = snap.diagnosis.suggestion;
    S.cfg.minCagr = +applyTarget.dataset.target;
    S.cfg.critOn.minCagr = true;
    S.cfg.riskPct = Math.round(sug.current * 4 * 10) / 10;
    saveCfg();
    navigate("mining").then(() => {
      toast(`Objetivo ${S.cfg.minCagr}% con riesgo ${S.cfg.riskPct}% — dale a Iniciar mining`, "ok");
      $("#m-run")?.scrollIntoView({ block: "center" });
    });
  };
}

/* ------------------------------------------------------------- inspector */
/* ``ctx`` permite abrir una estrategia GUARDADA sobre el instrumento y los
   costos con los que se minó, en vez de los que estén configurados ahora en
   Mining — que pueden ser de otro mercado por completo. */
async function openInspector(row, ctx) {
  if (!row) return;
  const host = document.createElement("div");
  host.className = "overlay";
  host.innerHTML = `<div class="sheet">
    <div class="sheet-head">
      <div><h2>${esc(row.name)} ${ctx
        ? `<span class="badge">guardada</span>`
        : `<span class="badge">fitness ${fmtNum(row.fitness, 3)}</span>`}</h2>
        <p>${esc(row.blocks || "")} · <span style="font-family:ui-monospace">${esc(row.genes_label)}</span></p></div>
      <button class="sheet-close">✕</button>
    </div>
    <div id="insp-body"><div class="empty-state"><span class="spinner"></span>
      Recalculando el backtest completo…</div></div>
  </div>`;
  document.body.appendChild(host);
  const close = () => host.remove();
  $(".sheet-close", host).onclick = close;
  host.onclick = (e) => { if (e.target === host) close(); };
  document.addEventListener("keydown", function esckey(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", esckey); }
  });

  try {
    const cfg = S.cfg;
    // sin bloque risk: el spec ya trae el stop que el minero encontró para
    // ESTA estrategia — mandar el genérico daría métricas distintas a las
    // que muestra el databank
    const { result } = ctx ? await api.post("/api/backtest", {
      dataset_id: ctx.dataset_id, timeframe: ctx.timeframe,
      spec: row.spec, settings: ctx.settings,
    }) : await api.post("/api/backtest", {
      dataset_id: S.sel.dataset_id, timeframe: S.sel.timeframe || "1h",
      // el mismo tramo que se minó: si no, la curva del inspector no
      // coincidiría con la fila del databank que el usuario acaba de clickear
      ...rangePayload(),
      spec: row.spec,
      settings: {
        spread: cfg.spread, slippage: cfg.slippage,
        commission_pct: cfg.commission, initial_capital: cfg.capital,
      },
    });
    renderInspector($("#insp-body", host), row, result);
  } catch (e) {
    $("#insp-body", host).innerHTML =
      `<div class="empty-state neg">No se pudo recalcular: ${esc(e.message)}</div>`;
  }
}

const INSPECT_METRICS = [
  ["cagr_pct", "Rendimiento anual", "pct"], ["net_profit_pct", "Rendimiento total", "pct"],
  ["exposure_pct", "Tiempo en mercado", "raw"], ["cagr_exposed_pct", "Anual s/ exposición", "raw"],
  ["profit_factor", "Profit factor", "n"], ["sharpe", "Sharpe", "n"],
  ["sortino", "Sortino", "n"], ["max_drawdown_pct", "Max drawdown", "dd"],
  ["recovery_factor", "Recovery", "n"], ["win_rate_pct", "Win rate", "raw"],
  ["trades", "Trades", "int"], ["avg_trade", "Trade promedio", "money"],
  ["avg_win", "Ganancia promedio", "money"], ["avg_loss", "Pérdida promedio", "loss"],
  ["expectancy_r", "Expectancy (R)", "n"], ["final_equity", "Capital final", "money"],
];

function renderInspector(box, row, res) {
  const m = res.metrics;
  const metricCards = INSPECT_METRICS.map(([k, label, kind]) => {
    const v = m[k];
    let txt = fmtNum(v), cls = "";
    if (kind === "pct") { txt = fmtPct(v); cls = v >= 0 ? "pos" : "neg"; }
    else if (kind === "dd") { txt = `${fmtNum(v, 1)}%`; cls = "neg"; }
    else if (kind === "raw") txt = `${fmtNum(v, 1)}%`;
    else if (kind === "int") txt = (+v).toLocaleString();
    else if (kind === "money") { txt = fmtMoney(v); cls = v >= 0 ? "pos" : ""; }
    else if (kind === "loss") { txt = `-${fmtMoney(Math.abs(v))}`; cls = "neg"; }
    return `<div class="metric"><span>${label}</span><b class="${cls}">${txt}</b></div>`;
  }).join("");

  const rules = (list, side) => (list || []).length
    ? `<div><b style="font-size:12px">${side}:</b> ` +
      list.map(c => `<span class="rule-pill">${esc(condLabel(c))}</span>`).join("") + `</div>`
    : "";

  const trades = (res.trades || []).slice(-120).reverse();
  const monthly = res.monthly_returns || [];

  box.innerHTML = `
  <section>
    <h3>QF Score <span style="text-transform:none;font-weight:400">— qué tan repetible parece,
      no cuánto rindió</span></h3>
    <div class="score-panel">
      <div class="score-big">${scoreBadge(res.score, "huge")}</div>
      <div class="score-detail">
        ${scoreBars(res.score_parts)}
        <p class="help-note">${scoreVerdict(res)}</p>
      </div>
    </div>
  </section>

  <section>
    <h3>Métricas completas</h3>
    <div class="metrics-grid">${metricCards}</div>
  </section>

  <section>
    <h3>Curva de capital y caídas</h3>
    <div class="chart-box tall" id="insp-eq"></div>
  </section>

  ${monthly.length ? `<section>
    <h3>Retornos mensuales</h3>
    <div class="scroll-x" id="insp-monthly"></div>
  </section>` : ""}

  <section>
    <h3>Reglas de la estrategia</h3>
    ${rules(row.spec.entry_long, "Entrada larga")}
    ${rules(row.spec.entry_short, "Entrada corta")}
    <div class="stage-note">${esc(riskSummary(row.spec.risk))}</div>
  </section>

  <section>
    <h3>Operaciones <span style="text-transform:none;font-weight:400">(últimas ${trades.length} de ${res.trades.length})</span></h3>
    <div class="table-scroll"><table>
      <thead><tr><th>Entrada</th><th>Salida</th><th>Dir</th>
        <th class="num">Precio ent.</th><th class="num">Precio sal.</th>
        <th class="num">Resultado</th><th class="num">%</th><th class="num">Barras</th><th>Motivo</th></tr></thead>
      <tbody>${trades.map(t => `<tr>
        <td class="muted">${esc(t.entry_time.slice(0, 16))}</td>
        <td class="muted">${esc(t.exit_time.slice(0, 16))}</td>
        <td><span class="badge ${t.direction === "long" ? "green" : "red"}">${t.direction === "long" ? "L" : "S"}</span></td>
        <td class="num">${fmtNum(t.entry_price, 2)}</td>
        <td class="num">${fmtNum(t.exit_price, 2)}</td>
        <td class="num ${t.pnl >= 0 ? "pos" : "neg"}">${fmtMoney(t.pnl)}</td>
        <td class="num ${t.pnl_pct >= 0 ? "pos" : "neg"}">${fmtNum(t.pnl_pct, 2)}%</td>
        <td class="num">${t.bars}</td>
        <td class="muted">${esc(t.exit_reason)}</td></tr>`).join("")}
      </tbody></table></div>
  </section>

  <div class="controls">
    <button class="btn" id="insp-mql5">⬇ MetaTrader 5 (.mq5)</button>
    <button class="btn ghost" id="insp-pine">⬇ TradingView (Pine)</button>
    <button class="btn ghost" id="insp-save">Guardar estrategia</button>
  </div>
  <p class="stage-note">El <b>.mq5</b> se compila en MetaEditor (F7) y se prueba en el Strategy Tester.
    El <b>.pine</b> se pega en el Pine Editor de TradingView y se agrega al gráfico.
    En los dos casos, poné el mismo spread que usaste acá.</p>`;

  Charts.equity($("#insp-eq", box), {
    values: res.equity,
    labels: res.timestamps.map(t => String(t).slice(0, 10)),
    initial: res.equity[0], height: 320,
  });

  if (monthly.length) Charts.monthlyGrid($("#insp-monthly", box), monthly);

  $("#insp-save", box).onclick = async () => {
    const btn = $("#insp-save", box);
    btn.disabled = true;
    try {
      // se guarda con todo su contexto: sin el instrumento, el timeframe y los
      // costos, dentro de un mes la estrategia no se puede volver a exportar
      const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
      await api.post("/api/strategies", {
        spec: row.spec, name: row.name,
        dataset_id: S.sel.dataset_id,
        notes: `Minada el ${new Date().toLocaleDateString("es-AR")}`,
        meta: {
          dataset_name: ds ? ds.name : "",
          timeframe: S.sel.timeframe || "1h",
          direction: S.cfg.direction,
          spread: S.cfg.spread, slippage: S.cfg.slippage,
          commission: S.cfg.commission, capital: S.cfg.capital,
          sizing: S.cfg.sizing, riskPct: S.cfg.riskPct, lots: S.cfg.lots, rr: S.cfg.rr,
          stop_mult: row.stop_mult ?? null,
          blocks: row.blocks || "", genes_label: row.genes_label || "",
          score: row.score ?? null,
          oos: row.oos || null, oos_ratio: row.oos_ratio ?? null,
          metrics: m,
          saved_at: new Date().toISOString(),
        },
      });
      toast(`${row.name} guardada en Mis estrategias`, "ok");
      refreshSavedCount();
    } catch (e) { toast(e.message, "err"); }
    btn.disabled = false;
  };

  /* MQL5 y Pine comparten todo salvo el endpoint, la extensión y el aviso */
  async function exportAs(btnId, endpoint, ext, done) {
    const btn = $(`#${btnId}`, box);
    btn.disabled = true;
    const safe = `QF_${row.name.replace("-", "_")}`;
    try {
      const r = await fetch(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spec: row.spec, name: safe,
          dataset_id: S.sel.dataset_id, timeframe: S.sel.timeframe || "1h",
          metrics: m,
        }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || r.status);
      const code = await r.text();
      const url = URL.createObjectURL(new Blob([code], { type: "text/plain" }));
      const a = document.createElement("a");
      a.href = url; a.download = `${safe}.${ext}`;
      a.click(); URL.revokeObjectURL(url);
      toast(done, "ok");
    } catch (e) { toast(e.message, "err"); }
    btn.disabled = false;
  }

  $("#insp-mql5", box).onclick = () => exportAs(
    "insp-mql5", "/api/export/mql5", "mq5",
    "EA descargado — copialo a MQL5/Experts y compilá");
  $("#insp-pine", box).onclick = () => exportAs(
    "insp-pine", "/api/export/pine", "pine",
    "Pine descargado — pegalo en el Pine Editor de TradingView");
}

/* el componente más flojo, dicho en criollo: qué habría que arreglar */
function scoreVerdict(res) {
  const parts = res.score_parts || {};
  const defs = S.meta?.score_parts || [];
  if (!defs.length) return "";
  const m = res.metrics;
  const worst = defs.reduce((a, b) => ((parts[a.key] ?? 0) <= (parts[b.key] ?? 0) ? a : b));
  const why = {
    consistencia: `su Sharpe es ${fmtNum(m.sharpe)}: la curva se mueve mucho para lo que rinde`,
    recuperacion: `gana ${fmtNum(m.cagr_pct, 1)}% al año pero llega a caer ${fmtNum(m.max_drawdown_pct, 0)}%`,
    evidencia: `${m.trades} operaciones son poca muestra para confiar en el resultado`,
    ventaja: `su expectativa es ${fmtNum(m.expectancy_r)}R por operación, un margen fino`,
    estabilidad: `sólo ${fmtNum(m.months_positive_pct ?? 0, 0)}% de los meses cerraron en verde`,
    reparto: `la mejor operación aporta el ${fmtNum(m.top_trade_share_pct ?? 0, 0)}% de la ganancia`,
  }[worst.key] || "";
  const tier = scoreTier(res.score || 0);
  return `<b>${tier.label}.</b> Lo que más le baja el puntaje es
    <b>${esc(worst.label.toLowerCase())}</b>: ${why}.`;
}

/* descripción legible de las salidas de una estrategia */
function riskSummary(risk) {
  if (!risk) return "";
  if (risk.stop_type === "none") return "sin stop ni target, sale por señal";
  const rr = risk.stop_value ? risk.target_value / risk.stop_value : 0;
  if (risk.stop_type === "atr") {
    return `Arriesga ${risk.size_value}% del capital por operación · stop a ` +
           `${(+risk.stop_value).toFixed(2)}× la volatilidad (ATR ${risk.atr_period}) · ` +
           `relación 1:${rr.toFixed(2).replace(/\.?0+$/, "")}`;
  }
  const unit = { points: "puntos", percent: "% del precio", money: "$" };
  const u = unit[risk.stop_type] || risk.stop_type;
  return `stop ${risk.stop_value} ${u} · target ${risk.target_value} ` +
         `${unit[risk.target_type] || risk.target_type}`;
}

/* etiqueta legible de una condición */
function condLabel(c) {
  const opLbl = { cross_above: "cruza arriba de", cross_below: "cruza abajo de",
                  rising: "sube", falling: "baja", ">": ">", "<": "<" }[c.op] || c.op;
  const side = o => {
    if (!o) return "";
    if (o.type === "const") return (+o.value).toLocaleString();
    if (o.type === "price") return (o.field || o.field_name || "close");
    const p = Object.values(o.params || {}).map(v => +v).join(",");
    return `${o.name}(${p})${o.output && o.output !== "value" ? "." + o.output : ""}`;
  };
  if (c.op === "rising" || c.op === "falling") return `${side(c.left)} ${opLbl}`;
  return `${side(c.left)} ${opLbl} ${side(c.right)}`;
}

/* ------------------------------------------------------------------ tema
   El oscuro es el default y vive en :root; el claro se activa poniendo
   data-theme="light" en <html>. Los gráficos leen sus colores del CSS con
   getComputedStyle, así que al cambiar de tema hay que volver a dibujarlos:
   el SVG ya generado conserva los colores viejos. */
function applyTheme(theme, redraw) {
  const light = theme === "light";
  const root = document.documentElement;
  // se cortan las transiciones mientras dura el cambio: si no, todas las
  // propiedades de color se animan a la vez y alguna queda a mitad de camino
  root.classList.add("theme-switching");
  root.setAttribute("data-theme", light ? "light" : "dark");
  try { localStorage.setItem("qf.theme", light ? "light" : "dark"); } catch (e) { /* noop */ }
  const btn = $("#theme-btn");
  if (btn) btn.title = light ? "Cambiar a tema oscuro" : "Cambiar a tema claro";
  if (redraw) navigate(S.page);
  // dos cuadros: uno para aplicar los colores nuevos, otro para devolver las
  // transiciones sin que el navegador las vea como un cambio animable
  requestAnimationFrame(() => requestAnimationFrame(
    () => root.classList.remove("theme-switching")));
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("qf.theme"); } catch (e) { /* noop */ }
  applyTheme(saved === "light" ? "light" : "dark", false);
  const btn = $("#theme-btn");
  if (btn) btn.onclick = () => {
    const now = document.documentElement.getAttribute("data-theme");
    applyTheme(now === "light" ? "dark" : "light", true);
  };
}

/* -------------------------------------------------------------------- boot */
(async function boot() {
  try {
    S.meta = await api.get("/api/meta");
    $("#version").textContent = `v${S.meta.version}`;
    await refreshDatasets();
  } catch (e) { toast(`No se pudo conectar con el backend: ${e.message}`, "err"); }
  initTheme();
  refreshSavedCount();
  $$("#nav button").forEach(b => b.onclick = () => navigate(b.dataset.page));
  navigate(S.datasets.length ? "mining" : "data");
})();
