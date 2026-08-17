/* Botiquant SPA — sin frameworks, sin build, 100% offline.
   v4: la corrida se define por OBJETIVO (cuántas estrategias tiene que juntar
   el databank), no por cuántas candidatas probar. Rediseño completo de la UI. */

"use strict";

/* ------------------------------------------------------------------ state */
const S = {
  meta: null,
  auth: null,           // {configurado, usuario} — ver refreshAuth()
  datasets: [],
  catalog: [],
  page: "data",
  sel: JSON.parse(localStorage.getItem("qf.sel") || "{}"),   // {dataset_id, timeframe}
  cfg: JSON.parse(localStorage.getItem("qf.cfg") || "null"), // config de mining
  mineJobId: null,
  //: orden elegido en el databank. null = el del minero (QF Score)
  bankSort: null,
  mineLive: null,
  mineResult: null,
  mining: false,
  minePaused: false,
  inspect: null,
  // los MetaTrader de esta máquina y a cuál mandamos los robots. "" es
  // Descargas, que es lo que queda cuando no hay ninguno instalado.
  mt5: { terminales: [], elegido: localStorage.getItem("qf.mt5") },
  // el banco: corridas archivadas, qué se está mirando y qué está tildado
  banco: { corridas: [], total: 0, tope: 0, filas: [], corrida: "", sel: new Set() },
  // arranca en la vista de todas, y ahí el puesto no ordena nada — ver ORDEN_NATURAL
  bancoSort: { key: "score", dir: -1 },
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
  minPf: 1.0, minSharpe: 0.30, maxDd: 25, minNet: 20, minWinRate: 50,
  maxFilters: 2, direction: "long", minTrades: 30,
  minCagr: 5, minExposure: 5, minRetDd: 1.5, minTradesMonth: 4,
  /* Una sola vara prendida de fábrica, y es la que nadie discute: que la
     estrategia haya ganado plata.

     Antes no venía ninguna, con el argumento de mostrar primero que la
     búsqueda encuentra cosas. Medido, eso significaba llenar el databank en
     catorce segundos con monedas al aire: en EURUSD, 21 de las 25 que
     mostraba PERDÍAN plata. Encontrar veinticinco estrategias en catorce
     segundos no es una buena primera impresión si la mitad no sirve — es una
     promesa que el producto no cumple.

     Profit factor 1 y no 1.10 a propósito: 1 es la línea que significa algo
     —ganó contra perdió— y es la más barata de satisfacer, así que es la que
     menos alarga la búsqueda. El resto de las varas las sube el usuario. */
  critOn: { minPf: true },
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
  // spread y slippage que el usuario corrigió a mano, por instrumento. Vacío
  // significa "usar el sugerido de cada mercado" — ver costosDe().
  costos: {},
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
S.cfg.costos = { ...(S.cfg.costos || {}) };
// El primer default de Retorno/Drawdown fue 3, puesto a ojo. Medido sobre
// datos reales lo pasa una de cada diez candidatas en un mercado bueno y
// NINGUNA en EURUSD, así que como sugerencia mandaba a una búsqueda vacía.
// Nadie eligió ese 3: era lo que venía puesto, y por eso se corrige solo.
if (_saved && _saved.minRetDd === 3) S.cfg.minRetDd = DEFAULT_CFG.minRetDd;
/* Config previa a que hubiera una vara de fábrica. Un `critOn` vacío no
   distingue "lo apagué a propósito" de "nunca lo toqué", pero de las dos la
   segunda es la única que existía: hasta ahora no venía ninguno prendido. Y
   como el 1.10 tampoco lo eligió nadie, se alinea con el nuevo. */
if (_saved && _saved.critOn && !Object.keys(_saved.critOn).length) {
  S.cfg.critOn = { ...DEFAULT_CFG.critOn };
  if (_saved.minPf === 1.10) S.cfg.minPf = DEFAULT_CFG.minPf;
}
if (_saved && _saved.goal == null) {
  // config previa al modelo por objetivo: su "maxCandidates" era el total a
  // probar (a veces 120), inservible como tope de seguridad
  S.cfg.maxCandidates = DEFAULT_CFG.maxCandidates;
}

const GOAL_PRESETS = [10, 25, 50, 100];

/* Cuántos filtros de contexto puede apilar una estrategia a la vez.

   Es la palanca más grande que hay sobre el sobreajuste, y por eso va con
   nombres y no como un número del 0 al 4. Cada condición que se agrega le
   permite a la búsqueda describir mejor el pasado exacto de este histórico:
   con cuatro condiciones encadenadas siempre aparece algo que se ve
   espectacular hacia atrás, porque hay tantas combinaciones que alguna tenía
   que dar. Lo que no aparece es que funcione después. */
const COMPLEJIDAD = [
  { n: 0, nombre: "Mínima",
    ayuda: "Sólo el disparador de entrada. Es lo más difícil de sobreajustar y lo más honesto como punto de partida: si acá no encontrás nada, el problema no son los filtros." },
  { n: 1, nombre: "Baja",
    ayuda: "El disparador más una condición de contexto." },
  { n: 2, nombre: "Media",
    ayuda: "Hasta dos condiciones a la vez. Es el equilibrio recomendado entre encontrar algo y no inventarlo." },
  { n: 3, nombre: "Alta",
    ayuda: "Hasta tres. Encuentra backtests mucho más lindos y bastante menos repetibles: validá fuera de muestra antes de creerles." },
];

/* Símbolo por familia de mercado. Con cuatro tarjetas idénticas salvo el
   texto, el icono es lo que permite encontrar la que buscás de un vistazo.
   Van dibujados a mano y no con logos de marca: un CFD de Bitcoin no es
   Bitcoin, y poner el logo real sugeriría una relación que no existe. */
const INST_FAMILIA = {
  "Índices": { tono: "indigo", icono:
    '<path d="M3 20h18"/><rect x="5" y="11" width="3.2" height="6" rx="1"/>' +
    '<rect x="10.4" y="7" width="3.2" height="10" rx="1"/>' +
    '<rect x="15.8" y="4" width="3.2" height="13" rx="1"/>' },
  "Forex": { tono: "teal", icono:
    '<path d="M4 9h13"/><path d="M14 6l3 3-3 3"/>' +
    '<path d="M20 15H7"/><path d="M10 12l-3 3 3 3"/>' },
  "Metales": { tono: "amber", icono:
    '<path d="M12 3l3.2 4.4L12 21 8.8 7.4 12 3Z"/><path d="M8.8 7.4h6.4"/>' },
  "Cripto": { tono: "blue", icono:
    '<circle cx="12" cy="12" r="8.5"/>' +
    '<path d="M9.6 8.4h4a1.9 1.9 0 0 1 0 3.8H9.6h4.6a1.9 1.9 0 0 1 0 3.8H9.6"/>' +
    '<path d="M11.2 6.6v1.8M11.2 16v1.8"/>' },
  _otro: { tono: "violet", icono:
    '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v9M9 10h6M9 14h6"/>' },
};

/* Filtros de aceptación al databank. Todos opcionales salvo el mínimo de
   operaciones: exigir Sharpe/DD/exposición por defecto rechazaba el 90% de las
   candidatas y la búsqueda volvía vacía sin que se entendiera por qué. Se
   activan de a uno, y sólo cuentan los que estén tildados. */
/* Los nombres son los que se usan en la mesa, no traducciones.
   "Aciertos" y "caída máxima" son español correcto y aun así hacen dudar: el
   que opera lee win rate y drawdown, los ve así en MetaTrader, en TradingView
   y en cualquier informe. Traducir un término técnico no lo aclara, lo vuelve
   irreconocible. */
const CRITERIA = [
  { key: "minPf",       label: "Profit factor ≥",       step: 0.05, min: 0, def: 1.0,  unit: "",
    ayuda: "Cuántos dólares ganó por cada dólar que perdió. En 1 quedó igual; por debajo, la estrategia pierde plata. Viene tildado en 1 justamente para que el databank no se llene de perdedoras." },
  { key: "minRetDd",    label: "Retorno / drawdown ≥",  step: 0.5,  min: 0, def: 1.5,  unit: "",
    ayuda: "Ganancia neta dividida por la peor caída. Junta las dos mitades de la pregunta —cuánto ganó y cuánto hubo que aguantar— y no se mueve si cambiás el riesgo por operación. En 1 ganó justo lo que llegó a caer; 2 ya es exigente y 3 lo pasa una de cada diez en un mercado bueno." },
  { key: "maxDd",       label: "Drawdown máximo ≤",     step: 1,    min: 4, def: 25,   unit: "%",
    ayuda: "Lo peor que llegó a bajar la cuenta desde un pico hasta el fondo. Es lo que hay que poder aguantar sin cerrar todo." },
  { key: "minWinRate",  label: "Win rate ≥",            step: 1,    min: 0, def: 50,   unit: "%",
    ayuda: "Porcentaje de operaciones ganadoras. Ojo: con una relación riesgo/beneficio de 1:2, un 40% ya es rentable — un win rate alto no es lo mismo que ganar más." },
  { key: "minTradesMonth", label: "Operaciones por mes ≥", step: 1, min: 0, def: 4,    unit: "",
    ayuda: "Cuántas veces opera al mes. Es el total de operaciones pero comparable: 200 son muchas en dos años y pocas en veinte." },
  { key: "minCagr",     label: "Retorno anual (CAGR) ≥", step: 1,   min: 0, def: 5,    unit: "%",
    ayuda: "Cuánto rindió por año, en promedio compuesto. Escala con el riesgo por operación." },
  { key: "minSharpe",   label: "Sharpe ≥",              step: 0.1,  min: 0, def: 0.30, unit: "",
    ayuda: "Retorno por unidad de volatilidad. Premia la curva pareja y castiga la que da saltos." },
  { key: "minExposure", label: "Tiempo en mercado ≥",   step: 1,    min: 0, def: 5,    unit: "%",
    ayuda: "Qué porcentaje del tiempo estuvo con una posición abierta. Muy bajo significa que opera poquísimo y la muestra vale poco." },
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
      // el código viaja con el error para que quien llama pueda distinguir
      // "falta cuenta" de un fallo cualquiera
      throw Object.assign(new Error(msg), { status: r.status });
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
/* Todo el formateo va en es-AR y no en el idioma del navegador. Con
   `undefined` la app mezclaba criterios: los enteros salían "35.500" y el
   dinero "35,500" en la misma pantalla según dónde estuviera cada usuario.
   La aplicación está en español; los números también.

   Sin abreviar a "k" ni a "M": son cifras de dinero y redondear $35.500 a
   "$35k" esconde justo el detalle que se está mirando. */
const fmtMoney = (v) => (v < 0 ? "-$" : "$") +
  Math.abs(+v || 0).toLocaleString("es-AR", { maximumFractionDigits: 0 });
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

/* ================================================ ventana por defecto =====
   El período con el que ARRANCA la pantalla: los últimos diez años.

   Es una regla de tiempo de búsqueda, no de calidad. EURUSD tiene 21 años de
   historia y su primer minado tardaba 405 segundos contra los 48 del S&P: en
   parte porque cada backtest recorre casi el doble de velas, y en parte
   porque es un mercado difícil y hay que probar muchas más candidatas. Siete
   minutos mirando una barra es lo primero que ve alguien que abre esto.

   Diez años y no tres a propósito. Es un límite pensado para que la búsqueda
   termine, y sigue cubriendo varios regímenes distintos —2018, el
   derrumbe de 2020, el bajista de 2022—, que es lo que hace que una
   estrategia signifique algo. Recortar más acelera todavía más y a la vez
   infla los resultados: con menos velas que satisfacer, cualquier regla se
   acomoda al ruido. Medido sobre el S&P, pasar de la historia completa a dos
   años sube el mejor CAGR de 3.5% a 21.4% y baja de 94% a 65% la proporción
   de estrategias cuya ventaja sobrevive fuera de muestra.

   Por eso son fechas VISIBLES en dos campos y no un recorte silencioso, y por
   eso hay un botón al lado para usar el historial entero. Un default que
   acelera se puede defender; uno que esconde sobre qué se midió, no. */
const VENTANA_ANIOS = 10;

function ventanaPorDefecto(ds) {
  const b = datasetBounds(ds);
  if (!b.lo || !b.hi) return "";
  const hi = new Date(b.hi + "T00:00:00Z");
  const corte = new Date(Date.UTC(hi.getUTCFullYear() - VENTANA_ANIOS,
                                  hi.getUTCMonth(), hi.getUTCDate()));
  const desde = corte.toISOString().slice(0, 10);
  // historia más corta que la ventana: se usa entera y no hay nada que recortar
  return desde > b.lo ? desde : "";
}

/** Pone la ventana de arranque, salvo que el usuario haya elegido su propio
 *  período — en ese caso manda el suyo y sólo se ajustan los bordes. */
function aplicarVentanaPorDefecto(ds) {
  if (S.sel.rangoPropio) { clampRangeTo(ds); return; }
  S.sel.dateFrom = ventanaPorDefecto(ds);
  S.sel.dateTo = "";
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

/* En una instalación compartida, los instrumentos del catálogo son de todos:
   un "Borrar" ahí dejaría al resto sin 4,6 millones de velas. Sólo lo que
   subió el propio usuario se puede borrar. */
function puedeBorrar(d) {
  return !S.meta?.multiuser || d.source === "upload";
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
  minCagr: "min_cagr_pct", minExposure: "min_exposure_pct",
  minWinRate: "min_win_rate_pct", minRetDd: "min_ret_dd",
  minTradesMonth: "min_trades_month",
  //: "Ganancia total" ya no se ofrece —el total depende de cuántos años tenga
  //: el histórico, así que el mismo número exige cosas distintas según el
  //: instrumento— pero la clave queda para leer las corridas ya archivadas.
  minNet: "min_net_pct",
};
/* Qué se exigió DE VERDAD en esta corrida.

   Los filtros son opcionales y arrancan destildados, pero sus casillas de
   número muestran igual un valor sugerido. Leído rápido eso parece una vara
   puesta, y no lo es: con sólo el mínimo de operaciones activo entra
   prácticamente cualquier cosa y el databank se llena en segundos con
   estrategias flojas. Sin decirlo acá, la aplicación parece estar ignorando
   filtros que en realidad nunca se le pidieron.

   Se lee de lo que devolvió el minero y no de la configuración actual de la
   pantalla: si no, cambiar un filtro después de correr reescribiría la
   historia de una corrida ya hecha. */
function varaAplicada(snap) {
  const a = snap.accept || {};
  const partes = [`mínimo <b>${fmtInt(snap.min_trades ?? 0)}</b> operaciones`];
  for (const cr of CRITERIA) {
    const v = a[CRIT_FIELD[cr.key]];
    if (v == null) continue;
    partes.push(`${esc(cr.label.replace(/ [≥≤]$/, ""))} ${cr.label.slice(-1)}
                 <b>${fmtNum(v, cr.step < 1 ? 2 : 0)}${cr.unit}</b>`);
  }
  if (partes.length > 1) {
    return `<div class="vara">Se exigió: ${partes.join(" · ")}</div>`;
  }
  return `<div class="vara floja"><b>Sin filtros de calidad.</b> Lo único que se
    exigió fue ${partes[0]}, así que entra casi cualquier candidata — incluidas
    las que pierden plata. Tildá lo que te importe en
    <b>Filtros de aceptación</b> y volvé a minar.</div>`;
}

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
/* ============================================================== iconos ==
   Un set dibujado, no emoji.

   Antes la interfaz usaba ⚠ ⛏ 💡 ✕ ★ y once glifos más. Un emoji no es un
   ícono: lo dibuja el sistema operativo, así que cambia de forma, de peso y
   hasta de color en cada máquina — en Windows salen a todo color, en otro lado
   son un trazo plano. Nada de eso responde al tema, y ninguno comparte grosor
   de línea con los demás. Es la diferencia más visible entre una interfaz
   armada y una que junta símbolos donde hace falta algo.

   Todos comparten caja de 24, trazo 1.7 y `currentColor`, así que heredan el
   color de donde estén y se ven como una familia. */
const TRAZO = 'fill="none" stroke="currentColor" stroke-width="1.7" ' +
              'stroke-linecap="round" stroke-linejoin="round"';

const ICONOS = {
  alerta:   `<path d="M10.3 3.9 1.8 18.5A2 2 0 0 0 3.5 21.5h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4.5"/><path d="M12 17.5h.01"/>`,
  bajar:    `<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M4 21h16"/>`,
  pico:     `<path d="M3 20.5 12.5 11"/><path d="M9 4.5c3-1.6 6.4-1.2 8.8 1.2s2.8 5.8 1.2 8.8l-4-4"/><path d="M9 4.5 15 10.5"/><path d="M19 14.5 13 8.5"/>`,
  tilde:    `<path d="m4 12.5 5.2 5.2L20 6.9"/>`,
  marcador: `<path d="M6 3.5h12a1 1 0 0 1 1 1v15.2a.6.6 0 0 1-.93.5L12 16.4l-6.07 3.8A.6.6 0 0 1 5 19.7V4.5a1 1 0 0 1 1-1Z"/>`,
  base:     `<ellipse cx="12" cy="5.5" rx="7.5" ry="3"/><path d="M4.5 5.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6"/><path d="M4.5 11.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6"/>`,
  cerrar:   `<path d="M6 6 18 18"/><path d="M18 6 6 18"/>`,
  detener:  `<rect x="6" y="6" width="12" height="12" rx="2"/>`,
  idea:     `<path d="M9 18h6"/><path d="M10 21.5h4"/><path d="M12 2.5a6.5 6.5 0 0 0-3.8 11.8c.5.4.8 1 .8 1.7h6c0-.7.3-1.3.8-1.7A6.5 6.5 0 0 0 12 2.5Z"/>`,
  estrella: `<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.2-5.4-2.9-5.4 2.9 1-6.2L3.2 9.5l6.1-.9L12 3Z"/>`,
  candado:  `<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>`,
  diana:    `<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3.5"/>`,
  info:     `<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5"/><path d="M12 7.6h.01"/>`,
  sube:     `<path d="m6 14.5 6-6 6 6"/>`,
  baja:     `<path d="m6 9.5 6 6 6-6"/>`,
  // pausa y seguir van en rectángulo y triángulo para que hagan juego con
  // `detener`, que ya era un rectángulo: los tres son el mismo control
  pausa:    `<rect x="7" y="5.5" width="3.6" height="13" rx="1.2"/><rect x="13.4" y="5.5" width="3.6" height="13" rx="1.2"/>`,
  seguir:   `<path d="M8 5.6v12.8a.6.6 0 0 0 .92.5l10-6.4a.6.6 0 0 0 0-1L8.92 5.1A.6.6 0 0 0 8 5.6Z"/>`,
  // el banco es una tabla, no un cilindro: el cilindro ya es `base` y son los
  // instrumentos. Dos cosas distintas no pueden compartir símbolo.
  banco:    `<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17"/><path d="M9.5 9.5v10"/>`,
  basura:   `<path d="M4.5 7h15"/><path d="M9.5 7V5.2a1.2 1.2 0 0 1 1.2-1.2h2.6a1.2 1.2 0 0 1 1.2 1.2V7"/><path d="m6.7 7 .87 12.1a1.5 1.5 0 0 0 1.5 1.4h5.86a1.5 1.5 0 0 0 1.5-1.4L17.3 7"/>`,
  copiar:   `<rect x="9" y="9" width="11" height="11.5" rx="2"/><path d="M15.5 9V5.5a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2V13a2 2 0 0 0 2 2h3.5"/>`,
};

/** Devuelve el SVG de un ícono. `cls` va al elemento para poder dimensionarlo
 *  desde el CSS en vez de fijar un tamaño acá. */
function icono(nombre, cls = "ico") {
  const d = ICONOS[nombre];
  if (!d) return "";
  return `<svg class="${cls}" viewBox="0 0 24 24" ${TRAZO} aria-hidden="true">${d}</svg>`;
}

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

/* En una tabla el badge con palabra no sirve: "Prometedora" mide el doble que
   "Sólida", cada píldora sale de otro ancho y en una columna alineada a la
   derecha ningún número queda a la par del de arriba. Además pesa mucho más
   que las otras trece columnas, que son números pelados.

   Acá va sólo el número, con ancho fijo para que la columna quede a plomo. El
   color ya dice de qué lado está y la palabra queda en el tooltip, que es
   donde no estorba. */
function scoreCell(v) {
  const t = scoreTier(+v || 0);
  return `<span class="score-cell ${t.cls}" title="${t.label}">${fmtNum(v ?? 0, 0)}</span>`;
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
    note.innerHTML = `<span>${icono("candado")}</span><div>Configuración congelada mientras busca.
      Cambiar los criterios viendo los resultados sería elegirlos a medida del histórico.
      <b>Detené</b> para ajustar y volver a minar.</div>`;
    $(".setup-run", setup)?.prepend(note);
  }
}

/* ================================================ costos por instrumento ===
   El spread no es una preferencia del usuario: es un dato del mercado. 0.36
   puntos es el spread del S&P y sobre EURUSD a 1.15 significa pagar 31% por
   operación — todas las candidatas dan -100% y la aplicación parece rota.

   Esa dirección ya estaba cubierta. La otra no, y es la peligrosa: si venís
   de EURUSD (0.00012) y pasás a Bitcoin (12), el costo queda en la
   cienmilésima parte del real. No dispara ninguna alarma porque el guardia
   vigila que no sea demasiado CARO, y el resultado no es un -100% evidente
   sino un backtest sin costos que se ve espectacular. Un error que se ve como
   un éxito es mucho peor que uno que se ve como un error.

   Por eso los costos siguen al instrumento siempre. Y lo que el usuario haya
   corregido a mano se guarda POR instrumento: su spread real de oro no tiene
   por qué perderse cuando pasa a mirar el S&P y vuelve. */
function costosDe(ds) {
  if (!ds) return null;
  const propio = (S.cfg.costos || {})[ds.id];
  if (propio) return { ...propio, mio: true };
  if (ds.suggested_spread == null) return null;
  return { spread: ds.suggested_spread, slippage: ds.suggested_slippage ?? 0, mio: false };
}

function adoptInstrumentDefaults() {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  const costos = costosDe(ds);
  if (!costos) return;
  S.cfg.spread = costos.spread;
  S.cfg.slippage = costos.slippage;
  saveCfg();
}

/** Lo que el usuario escribió a mano queda atado a SU instrumento. */
function recordarCostos() {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  if (!ds) return;
  S.cfg.costos = S.cfg.costos || {};
  S.cfg.costos[ds.id] = { spread: +S.cfg.spread, slippage: +S.cfg.slippage };
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

/* Lee todos los inputs [data-cfg] hacia S.cfg.

   `normalizar` separa dos momentos que antes estaban mezclados: mientras se
   escribe no se toca el campo, y recién al confirmarlo se acomoda.

   Corregirlo en cada tecla hacía imposible editarlo. Al borrar el último
   dígito el campo quedaba vacío y el código le devolvía el valor anterior en la
   misma pulsación, así que siempre sobraba un dígito imborrable. Y aplicar el
   piso tecla por tecla impedía escribir "10" en un criterio con mínimo 4: la
   "1" se convertía en 4 antes de llegar a tipear el "0". */
function harvestCfg(root, { normalizar = false } = {}) {
  $$("[data-cfg]", root).forEach(el => {
    const k = el.dataset.cfg;
    if (el.type !== "number") { S.cfg[k] = el.value; return; }
    const cr = CRIT_BY_KEY[k];
    const n = parseFloat(el.value);

    if (!Number.isFinite(n)) {
      // vacío a mitad de la edición: se deja en paz y S.cfg conserva lo último
      // válido, así nada corre con un campo en blanco
      if (!normalizar) return;
      // un campo vacío daba 0, y el backend lo subía al mínimo (10 candidatas):
      // la búsqueda terminaba al instante sin que nadie entendiera por qué
      el.value = S.cfg[k] ?? DEFAULT_CFG[k] ?? 0;
      S.cfg[k] = parseFloat(el.value);
      return;
    }
    // el mínimo de cada criterio manda (el max DD no admite menos de 4%), pero
    // sólo al confirmar
    if (cr && n < cr.min && normalizar) {
      el.value = cr.min;
      S.cfg[k] = cr.min;
      return;
    }
    S.cfg[k] = n;
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
  if (!S.sel.dataset_id && S.datasets.length) {
    // La aplicación elige el instrumento sola cuando no hay ninguno: al abrir,
    // o cuando el que estaba se borró. Sin adoptar sus costos acá, ese caso
    // arrancaba con el spread del instrumento ANTERIOR y nadie lo eligió.
    S.sel.dataset_id = S.datasets[0].id;
    adoptInstrumentDefaults();
  }
}

async function navigate(page) {
  S.page = page;
  $$("#nav button").forEach(b => b.classList.toggle("active", b.dataset.page === page));
  const main = $("#main");
  main.innerHTML = "";
  try {
    await PAGES[page](main);
  } catch (e) {
    // Sin esto, cualquier fallo dejaba el <main> vacío para siempre: la página
    // ya se había limpiado y nadie volvía a escribir nada. Se veía igual que
    // una carga eterna, sin ningún mensaje ni forma de salir.
    if (e && e.status === 401) { pedirCuenta(401); }
    main.innerHTML = pageHead(TITULOS[page] || "Botiquant", "") + `
      <div class="card"><div class="empty-state">
        <div class="big">${icono("alerta","ico-xl")}</div>
        <b>${e && e.status === 401 ? "Se cerró tu sesión" : "No se pudo cargar esta página"}</b>
        <p class="mt">${esc(e && e.status === 401
          ? "Volvé a entrar y seguimos donde estabas."
          : (e && e.message) || "El servidor no respondió.")}</p>
        <button class="btn mt" id="reintentar">Reintentar</button>
      </div></div>`;
    const b = $("#reintentar", main);
    if (b) b.onclick = () => navigate(page);
    return;
  }
  main.scrollTop = 0;
}

const TITULOS = {
  data: "Datos", mining: "Mining", banco: "Databank",
  validacion: "Validación", saved: "Mis estrategias", results: "Resultados",
};

/* ======================================================== página VALIDACIÓN
   Las dos preguntas que siguen a "encontré algo": ¿funciona fuera de donde lo
   busqué, y cuánto de lo que veo es suerte?

   Van juntas porque son la misma pregunta hecha de dos maneras. Fuera de
   muestra la contesta con datos que la búsqueda no vio; Monte Carlo la
   contesta sin datos nuevos, rebarajando las operaciones que ya hubo para ver
   qué tan distinto podría haber salido el mismo sistema por puro orden.

   Lo que decide si esta pantalla sirve o engaña es el SOLAPAMIENTO. Volver a
   correr una estrategia sobre las mismas velas con las que se la encontró
   devuelve los mismos números por construcción: no valida nada, y se ve
   exactamente igual que una validación exitosa. Por eso el solapamiento se
   mide siempre y se muestra antes que los resultados. */
const VAL = {
  sel: new Set(),          // "origen:id" de lo tildado
  tab: "oos",
  candidatas: [],          // banco + guardadas, forma común
  resultado: null,
  mc: null,
  detalle: null,
  corriendo: false,
};

/** Banco y guardadas en una sola lista con la misma forma. */
async function cargarCandidatas() {
  const [banco, guardadas] = await Promise.all([
    api.get("/api/banco?" + new URLSearchParams({ orden: "score", dir: "desc", limite: "80" })),
    api.get("/api/strategies"),
  ]);
  if (!S.banco.corridas.length) await refreshBancoCount();
  const porCorrida = Object.fromEntries(S.banco.corridas.map(c => [c.id, c]));

  const deBanco = banco.map(f => {
    const c = porCorrida[f.corrida_id] || {};
    return {
      clave: `banco:${f.banco_id}`, origen: "banco", id: f.banco_id, nombre: f.name,
      mercado: nombreCorto(c.dataset_name), tf: c.timeframe || "",
      dataset_id: c.dataset_id, medido: (c.contexto || {}).measured_range || null,
      metricas: f.metrics || {},
    };
  });
  const deGuardadas = guardadas.map(s => {
    const m = s.meta || {};
    return {
      clave: `guardada:${s.id}`, origen: "guardada", id: s.id, nombre: s.name,
      mercado: nombreCorto(m.dataset_name), tf: m.timeframe || "",
      dataset_id: m.dataset_id, medido: m.measured_range || null,
      metricas: m.metrics || {},
    };
  });
  VAL.candidatas = [...deGuardadas, ...deBanco];
  const vivas = new Set(VAL.candidatas.map(x => x.clave));
  [...VAL.sel].forEach(k => { if (!vivas.has(k)) VAL.sel.delete(k); });
}

/* El tramo que la búsqueda NUNCA vio, si es que quedó alguno.

   Sólo HACIA ADELANTE, y esto es una corrección de algo que estaba mal. Antes
   también ofrecía el tramo anterior al minado, y validar una estrategia contra
   años previos a los que se usó para encontrarla no responde la pregunta que
   uno se hace. Lo que se quiere saber es si va a seguir funcionando, no si
   habría funcionado en un mercado que ya pasó.

   Cuando no queda nada adelante —porque se minó hasta el final del
   histórico— no hay validación posible y hay que decirlo, en vez de ofrecer
   un tramo que devuelve números sin significado. */
function tramoLibre(cand) {
  const ds = S.datasets.find(d => d.id === cand.dataset_id);
  if (!ds || !cand.medido || !cand.medido.from) return null;
  const b = datasetBounds(ds);
  const hasta = String(cand.medido.to).slice(0, 10);
  const dias = (new Date(b.hi) - new Date(hasta)) / 86400000;
  // menos de cuatro meses no alcanza para que las métricas signifiquen algo
  if (dias < 120) return null;
  return { from: hasta, to: b.hi, dias, anios: Math.round(dias / 365 * 10) / 10 };
}

/* Volver a minar dejando el final sin tocar.

   Es la salida real cuando no quedó tramo limpio, y no hace falta nada nuevo:
   el minado ya sabe reservar un porcentaje final y validar ahí cada candidata
   que acepta. Lo único que pasaba es que venía apagado y escondido en
   Avanzado, así que nadie llegaba. */
function reminarReservando(cand, pct) {
  const ds = S.datasets.find(d => d.id === cand.dataset_id);
  if (ds) S.sel.dataset_id = ds.id;
  if (cand.tf) S.sel.timeframe = cand.tf;
  if (cand.medido && cand.medido.from) {
    S.sel.dateFrom = String(cand.medido.from).slice(0, 10);
    S.sel.dateTo = String(cand.medido.to).slice(0, 10);
    S.sel.rangoPropio = true;
  }
  S.cfg.oosPct = pct;
  saveCfg();
  navigate("mining").then(() => {
    toast(`Configurado para reservar el último ${pct}% — dale a Iniciar`, "ok");
    const run = $("#m-run");
    if (run) run.scrollIntoView({ block: "center" });
  });
}

PAGES.validacion = async (main) => {
  await refreshDatasets();
  await cargarCandidatas();

  if (!VAL.candidatas.length) {
    main.innerHTML = pageHead("Validación",
      "Comprobá si lo que encontraste es real o fue suerte.") +
      `<div class="card"><div class="empty-state">
        <div class="big">${icono("diana", "ico-xl")}</div>
        <b>Todavía no hay nada que validar</b>
        <p class="mt">Cuando termines una búsqueda, sus estrategias aparecen acá para
          probarlas sobre datos que no usaste y para simular qué tan repetibles son.</p>
        <button class="btn mt" id="val-ir">Ir a Mining</button>
      </div></div>`;
    $("#val-ir", main).onclick = () => navigate("mining");
    return;
  }

  main.innerHTML = pageHead("Validación",
    "Las dos preguntas que siguen a encontrar algo: ¿funciona fuera de donde lo buscaste, y cuánto de lo que ves es suerte?") +
    `<div id="val-elegir"></div>
     <div class="tabs" id="val-tabs">
       <button data-tab="oos" class="${VAL.tab === "oos" ? "on" : ""}">Fuera de muestra</button>
       <button data-tab="mc" class="${VAL.tab === "mc" ? "on" : ""}">Monte Carlo</button>
     </div>
     <div id="val-cuerpo"></div>`;

  $$("#val-tabs button", main).forEach(b => b.onclick = () => {
    VAL.tab = b.dataset.tab;
    $$("#val-tabs button", main).forEach(o => o.classList.toggle("on", o === b));
    pintarCuerpoVal();
  });

  pintarElegir();
  pintarCuerpoVal();
};

function pintarElegir() {
  const host = $("#val-elegir");
  if (!host) return;
  const n = VAL.sel.size;
  host.innerHTML = `<div class="card">
    <h2>Qué validar <span class="hint">${VAL.candidatas.length} disponibles ·
      de tus estrategias guardadas y del databank</span></h2>
    <div class="val-lista">
      ${VAL.candidatas.map(x => `
        <label class="val-item ${VAL.sel.has(x.clave) ? "on" : ""}">
          <input type="checkbox" data-cand="${esc(x.clave)}" ${VAL.sel.has(x.clave) ? "checked" : ""}>
          <span class="vi-nom">${esc(x.nombre)}
            ${x.origen === "guardada" ? `<em class="vi-tag">guardada</em>` : ""}</span>
          <span class="vi-ctx">${esc(x.mercado)} · ${esc(x.tf)}</span>
          <span class="vi-pf">PF ${x.metricas.profit_factor != null
            ? fmtNum(x.metricas.profit_factor) : "—"}</span>
        </label>`).join("")}
    </div>
    <div class="val-pie">
      <span><b>${n}</b> seleccionada${n === 1 ? "" : "s"}</span>
      <button class="linkbtn" id="val-todas">Todas</button>
      <button class="linkbtn" id="val-nada">Ninguna</button>
    </div>
  </div>`;

  $$("[data-cand]", host).forEach(cb => cb.onchange = () => {
    if (cb.checked) VAL.sel.add(cb.dataset.cand); else VAL.sel.delete(cb.dataset.cand);
    pintarElegir(); pintarCuerpoVal();
  });
  $("#val-todas", host).onclick = () => {
    VAL.candidatas.forEach(x => VAL.sel.add(x.clave)); pintarElegir(); pintarCuerpoVal();
  };
  $("#val-nada", host).onclick = () => { VAL.sel.clear(); pintarElegir(); pintarCuerpoVal(); };
}

const seleccionadas = () => VAL.candidatas.filter(x => VAL.sel.has(x.clave));

function pintarCuerpoVal() {
  const host = $("#val-cuerpo");
  if (!host) return;
  if (VAL.tab === "oos") pintarOOS(host); else pintarMC(host);
}

/* ------------------------------------------------------- fuera de muestra */
function pintarOOS(host) {
  const elegidas = seleccionadas();
  const una = elegidas[0];
  const libre = una ? tramoLibre(una) : null;
  if (libre && !VAL.desde) { VAL.desde = libre.from; VAL.hasta = libre.to; }
  const r = VAL.resultado;

  const explico = `<div class="explico">
    <b>Qué es esto.</b> Para encontrar tu estrategia, la búsqueda probó miles de
    combinaciones sobre un período. Entre tantas, siempre aparece alguna que se ve
    bien ahí — a veces por casualidad. La única forma de saber si la ventaja es real
    es correrla sobre velas <b>posteriores</b>, que la búsqueda nunca miró.
  </div>`;

  host.innerHTML = `<div class="card">
    <h2>Probarla en el futuro que no vio
      <span class="hint">las mismas reglas, sobre velas que la búsqueda nunca miró</span></h2>
    ${explico}

    ${!una ? `<div class="pista">${icono("info","ico-sm")}
        <div><b>Empezá por arriba:</b> tildá una o varias estrategias en la lista.</div></div>`
      : libre ? `<div class="pista ok">${icono("tilde","ico-sm")}
        <div><b>Se puede validar.</b> Esta búsqueda usó hasta ${esc(libre.from)}, así que
          quedan <b>${libre.anios} años</b> posteriores que nunca miró
          (${esc(libre.from)} → ${esc(libre.to)}). Ése es el tramo que sirve, y ya está
          puesto abajo.</div></div>`
      : `<div class="pista alerta">${icono("alerta","ico-sm")}
        <div><b>Acá no se puede validar, y conviene saber por qué.</b>
          La búsqueda usó el historial <i>hasta el final</i>, así que no queda ningún
          tramo posterior sin mirar. Elegir cualquier período de los que ya usó devuelve
          los mismos números por construcción: parece una confirmación y no lo es.
          <div class="pista-accion">
            La salida es volver a buscar dejando el final sin tocar, y la aplicación ya
            sabe hacerlo sola:
            <button class="btn small" data-reminar="20">Minar reservando el último 20%</button>
            <button class="btn ghost small" data-reminar="30">Reservar 30%</button>
          </div>
        </div></div>`}

    ${libre ? `
      <div class="fld-pair mt">
        <label class="fld"><span>Desde</span>
          <input type="date" class="datefld" id="val-desde" value="${esc(VAL.desde || "")}"></label>
        <label class="fld"><span>Hasta</span>
          <input type="date" class="datefld" id="val-hasta" value="${esc(VAL.hasta || "")}"></label>
      </div>
      <button class="btn mt" id="val-correr" ${VAL.corriendo ? "disabled" : ""}>
        ${VAL.corriendo ? "Corriendo…"
          : `Probar ${elegidas.length} estrategia${elegidas.length === 1 ? "" : "s"}`}
      </button>` : ""}
  </div>

  ${r ? tablaOOS(r) : ""}`;

  $$("[data-reminar]", host).forEach(b => b.onclick = () => reminarReservando(una, +b.dataset.reminar));

  const d = $("#val-desde", host), h = $("#val-hasta", host);
  if (d) d.onchange = () => { VAL.desde = d.value; };
  if (h) h.onchange = () => { VAL.hasta = h.value; };

  const btn = $("#val-correr", host);
  if (btn) btn.onclick = async () => {
    if (!VAL.desde || !VAL.hasta) { toast("Elegí el período a probar", "err"); return; }
    VAL.corriendo = true; pintarCuerpoVal();
    try {
      VAL.resultado = await api.post("/api/validar", {
        estrategias: elegidas.map(x => ({ origen: x.origen, id: x.id })),
        date_from: VAL.desde, date_to: VAL.hasta,
      });
    } catch (e) { toast(e.message, "err"); }
    VAL.corriendo = false; pintarCuerpoVal();
  };
}

/** Cómo leer el ratio: cuánto del profit factor sobrevivió al cambio de datos. */
function veredicto(x) {
  if (x.error) return `<span class="oos-tag none">${esc(x.error.slice(0, 40))}</span>`;
  if (x.ratio == null) return `<span class="muted">—</span>`;
  if (x.solapamiento_pct >= 50) {
    return `<span class="oos-tag none" title="Este período ya lo vio la búsqueda: el resultado no valida nada">no cuenta</span>`;
  }
  const q = x.ratio;
  const cls = q >= 0.8 ? "good" : q >= 0.5 ? "mid" : "bad";
  const et = q >= 0.8 ? "se sostiene" : q >= 0.5 ? "se debilita" : "se cae";
  return `<span class="oos-tag ${cls}"><b>${fmtNum(q, 2)}×</b><em>${et}</em></span>`;
}

function tablaOOS(r) {
  const filas = r.resultados;
  const solapadas = filas.filter(x => x.solapamiento_pct >= 50).length;
  const sanas = filas.filter(x => !x.error && x.ratio != null && x.solapamiento_pct < 50);
  const aguantan = sanas.filter(x => x.ratio >= 0.8).length;
  return `<div class="card">
    <h2>Resultado <span class="hint">${esc(r.periodo.from)} → ${esc(r.periodo.to)}</span></h2>

    ${sanas.length ? `<div class="veredicto ${aguantan ? "" : "flojo"}">
      <b>${aguantan} de ${sanas.length}</b> mantuvieron su ventaja en datos que nunca vieron.
      ${aguantan === 0
        ? "Ninguna sobrevivió: lo que encontró la búsqueda describía ese período y no se repitió después. Es el resultado más común, y saberlo ahora vale mucho más que descubrirlo con plata puesta."
        : aguantan < sanas.length
          ? "Las que se caen no son errores de la aplicación: es lo que pasa cuando una regla se ajustó al pasado. Quedate con las que aguantaron."
          : "Buena señal. Aun así, probalas en demo antes de poner plata."}
    </div>` : ""}

    ${solapadas ? `<div class="banner info mt" style="margin-bottom:14px">
      <span class="b-ic">${icono("alerta")}</span><div>
      <b>${solapadas} de ${filas.length} se corrieron sobre datos que la búsqueda ya había
      visto.</b> Esos números vuelven parecidos por construcción y no dicen nada nuevo —
      por eso figuran como “no cuenta”.</div></div>` : ""}
    <div class="databank-wrap"><table class="banco">
      <thead><tr>
        <th>Estrategia</th>
        <th class="num" title="Qué parte del período elegido ya la había visto la búsqueda">Ya visto</th>
        <th class="num">PF antes</th><th class="num">PF ahora</th>
        <th class="num">Anual</th><th class="num">Máx. DD</th><th class="num">Ops.</th>
        <th class="num">Sobrevive</th>
      </tr></thead>
      <tbody>${filas.map(x => {
        const a = x.antes || {}, d = x.despues || {};
        return `<tr>
          <td><span class="strat-name">${esc(x.nombre)}</span></td>
          <td class="num ${x.solapamiento_pct >= 50 ? "neg" : "muted"}">${fmtNum(x.solapamiento_pct, 0)}%</td>
          <td class="num">${a.profit_factor != null ? fmtNum(a.profit_factor) : "—"}</td>
          <td class="num"><b>${d.profit_factor != null ? fmtNum(d.profit_factor) : "—"}</b></td>
          <td class="num ${(d.cagr_pct ?? 0) >= 0 ? "pos" : "neg"}">${
            d.cagr_pct != null ? fmtPct(d.cagr_pct) : "—"}</td>
          <td class="num neg">${d.max_drawdown_pct != null ? fmtNum(d.max_drawdown_pct, 1) + "%" : "—"}</td>
          <td class="num">${d.trades != null ? fmtInt(d.trades) : "—"}</td>
          <td class="num">${veredicto(x)}</td>
        </tr>`;
      }).join("")}</tbody></table></div>
    <p class="stage-note">“Sobrevive” es el profit factor de este período dividido por el
      original. Cerca de 1 la ventaja se mantuvo; cerca de 0 la estrategia describía el
      tramo en que se la encontró y nada más.</p>
  </div>`;
}

/* ------------------------------------------------------------ Monte Carlo
   Corre sobre TODAS las seleccionadas y las pone una al lado de la otra.

   Antes simulaba sólo la primera, que es una elección arbitraria y encima
   silenciosa. Y de a una el número no sirve para decidir: un 12% de
   probabilidad de perder no es bueno ni malo hasta que se lo compara con el
   de las otras que uno encontró. */
function pintarMC(host) {
  const elegidas = seleccionadas();
  const r = VAL.mc;

  host.innerHTML = `<div class="card">
    <h2>¿Cuánto de esto fue suerte?
      <span class="hint">las mismas operaciones, en otro orden, mil veces cada una</span></h2>
    <div class="explico">
      <b>Qué es esto.</b> Una estrategia que ganó puede haber ganado por el <i>orden</i> en
      que le salieron las operaciones: si las tres pérdidas seguidas hubieran caído al
      principio en vez de al final, la historia era otra. Esto agarra sus operaciones
      reales y las vuelve a repartir mil veces, para ver en qué rango de resultados cae
      de verdad — y cuánto del backtest fue puntería.
    </div>

    ${!elegidas.length
      ? `<div class="pista">${icono("info","ico-sm")}
          <div><b>Empezá por arriba:</b> tildá las estrategias que quieras comparar.
          Podés elegir varias y las simula a todas.</div></div>`
      : `<button class="btn mt" id="mc-correr" ${VAL.corriendo ? "disabled" : ""}>
          ${VAL.corriendo ? "Simulando…"
            : `Simular ${elegidas.length} estrategia${elegidas.length === 1 ? "" : "s"}`}
        </button>`}
  </div>
  ${r ? tablaMC(r) : ""}
  ${r && VAL.detalle ? panelMC(VAL.detalle) : ""}`;

  const btn = $("#mc-correr", host);
  if (btn) btn.onclick = async () => {
    VAL.corriendo = true; pintarCuerpoVal();
    try {
      VAL.mc = await api.post("/api/robustez", {
        estrategias: elegidas.map(x => ({ origen: x.origen, id: x.id })),
        simulations: 1000, seed: 42,
      });
      // se abre la mejor: es la que el usuario va a querer mirar primero
      const mejor = VAL.mc.resultados.find(x => x.puesto === 1);
      VAL.detalle = mejor ? { ...mejor.mc, nombre: mejor.nombre } : null;
    } catch (e) { toast(e.message, "err"); }
    VAL.corriendo = false; pintarCuerpoVal();
  };

  $$("[data-ver]", host).forEach(b => b.onclick = () => {
    const x = VAL.mc.resultados.find(y => y.id === b.dataset.ver);
    VAL.detalle = x && x.mc ? { ...x.mc, nombre: x.nombre } : null;
    pintarCuerpoVal();
    $("#mc-detalle")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  if (VAL.detalle) dibujarMC(VAL.detalle);
}

function tablaMC(r) {
  const filas = [...r.resultados].sort((a, b) => (a.puesto || 99) - (b.puesto || 99));
  const mejor = filas.find(x => x.puesto === 1);
  return `<div class="card">
    <h2>Cuál aguanta mejor
      <span class="hint">${fmtInt(r.simulations)} simulaciones de cada una ·
        ordenadas por la que menos depende de la suerte</span></h2>

    ${mejor ? `<div class="veredicto">
      La más sólida es <b>${esc(mejor.nombre)}</b>: en ${fmtNum(100 - mejor.prob_perder, 0)}%
      de los repartos termina ganando, y su peor 5% cae ${fmtNum(mejor.dd_p95, 1)}%.
      ${mejor.ruina > 5
        ? `Ojo igual con el riesgo de ruina de ${fmtNum(mejor.ruina, 1)}%.`
        : `Su riesgo de ruina es ${fmtNum(mejor.ruina, 1)}%.`}
    </div>` : ""}

    <div class="databank-wrap"><table class="banco">
      <thead><tr>
        <th>#</th><th>Estrategia</th>
        <th class="num" title="En cuántos de los mil repartos terminó perdiendo plata">Pierde en</th>
        <th class="num" title="Probabilidad de llegar a perder el 30% del capital en algún momento">Ruina</th>
        <th class="num" title="La caída máxima del 5% de simulaciones peores. Es lo que hay que poder aguantar.">Peor caída</th>
        <th class="num">Capital típico</th><th class="num">Ops.</th><th></th>
      </tr></thead>
      <tbody>${filas.map(x => x.error ? `
        <tr><td class="rank-cell">—</td><td><span class="strat-name">${esc(x.nombre)}</span></td>
          <td colspan="6" class="muted">${esc(x.error)}</td></tr>` : `
        <tr class="${x.puesto === 1 ? "tildada" : ""}">
          <td class="rank-cell"><span class="rank">${String(x.puesto).padStart(2, "0")}</span></td>
          <td><span class="strat-name">${esc(x.nombre)}</span></td>
          <td class="num ${x.prob_perder > 30 ? "neg" : ""}"><b>${fmtNum(x.prob_perder, 1)}%</b></td>
          <td class="num ${x.ruina > 5 ? "neg" : ""}">${fmtNum(x.ruina, 1)}%</td>
          <td class="num neg">${fmtNum(x.dd_p95, 1)}%</td>
          <td class="num">${fmtMoney(x.final_mediana)}</td>
          <td class="num">${fmtInt(x.operaciones)}</td>
          <td class="num"><button class="btn ghost small" data-ver="${esc(x.id)}">Ver</button></td>
        </tr>`).join("")}</tbody></table></div>
    <p class="stage-note"><b>Pierde en</b> es de cada 100 repartos posibles, en cuántos
      terminaría en rojo. Cuanto más bajo, menos depende de que las operaciones salgan
      en buen orden.</p>
    <div class="explico">
      <b>Ojo con confundir las dos pestañas.</b> Esto mide si la estrategia depende del
      orden en que salieron sus operaciones — pero las rebaraja sobre <i>el mismo período
      donde se la encontró</i>. Una estrategia puede salir primera acá y aun así caerse
      en <b>Fuera de muestra</b>, que es la que pregunta si la ventaja existe fuera de
      ese período. Hacen falta las dos, y la que manda es la otra.
    </div>
  </div>`;
}

function panelMC(mc) {
  const fe = mc.final_equity, dd = mc.max_drawdown_pct;
  const ruina = mc.risk_of_ruin_pct;
  return `<div class="card" id="mc-detalle">
    <h2>${esc(mc.nombre || "Simulación")}
      <span class="hint">${fmtInt(mc.simulations)} simulaciones de
        ${fmtInt(mc.trades_per_sim)} operaciones</span></h2>

    <div class="metrics-grid">
      <div class="metric"><span>Probabilidad de perder plata</span>
        <b class="${fe.prob_loss > 30 ? "neg" : ""}">${fmtNum(fe.prob_loss, 1)}%</b></div>
      <div class="metric"><span>Riesgo de ruina (−${fmtNum(mc.ruin_threshold_pct, 0)}%)</span>
        <b class="${ruina > 5 ? "neg" : ""}">${fmtNum(ruina, 1)}%</b></div>
      <div class="metric"><span>Capital final típico</span>
        <b>${fmtMoney(fe.median)}</b></div>
      <div class="metric"><span>Caída en el 5% peor</span>
        <b class="neg">${fmtNum(dd.p95, 1)}%</b></div>
    </div>

    <p class="stage-note mt">De cada 100 veces que corriera este sistema, en 90 el capital
      final caería entre <b>${fmtMoney(fe.ci_90[0])}</b> y <b>${fmtMoney(fe.ci_90[1])}</b>.
      En el peor caso simulado terminó en ${fmtMoney(fe.worst)} y llegó a caer
      ${fmtNum(dd.worst, 1)}%. <b>Ese es el número que hay que poder aguantar</b>, no el
      del backtest.</p>

    <div class="chart-box" id="mc-fan"></div>
    <p class="stage-note">La banda muestra dónde cae el capital en el 90% de las
      simulaciones. La línea del medio es el recorrido típico.</p>

    <h2 class="mt">Cómo se reparten los finales</h2>
    <div class="chart-box short" id="mc-hist"></div>

    <h2 class="mt">Y las caídas máximas</h2>
    <div class="chart-box short" id="mc-dd"></div>
  </div>`;
}

function dibujarMC(mc) {
  const fan = $("#mc-fan");
  if (fan) Charts.fan(fan, mc.bands, mc.initial_capital);
  const h = $("#mc-hist");
  if (h) Charts.histogram(h, mc.final_equity.histogram, mc.initial_capital);
  const d = $("#mc-dd");
  if (d) Charts.histogram(d, mc.max_drawdown_pct.histogram, mc.max_drawdown_pct.median);
}


/* ============================================================ página DATOS */
PAGES.data = async (main) => {
  await refreshDatasets();

  const cards = S.catalog.map(c => {
    const ready = !!c.dataset_id;
    const fam = INST_FAMILIA[c.category] || INST_FAMILIA._otro;
    return `<div class="inst-card ${ready ? "ready" : ""}">
      <div class="inst-top">
        <span class="inst-ic f-${fam.tono}"><svg viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
          stroke-linejoin="round">${fam.icono}</svg></span>
        <span class="inst-id"><h3>${esc(c.label)}</h3>
          <span class="cat">${esc(c.category)}</span></span>
      </div>
      <p>${esc(c.full_name)} · ${esc(c.note)}</p>
      ${ready
        ? `<div class="inst-meta">${icono("tilde")} ${c.rows.toLocaleString()} velas M1<br>
             ${esc(String(c.start).slice(0, 10))} → ${esc(String(c.end).slice(0, 10))}</div>
           <button class="btn ghost" data-mine="${c.dataset_id}" data-key="${c.key}">Minar este</button>`
        : `<div class="inst-meta">Historial M1 desde ${esc(c.from)}</div>
           ${S.meta?.multiuser
             ? `<span class="muted" style="font-size:11.5px">No disponible en este instrumento</span>`
             : `<button class="btn" data-dl="${c.key}">${icono("bajar")} Descargar</button>`}`}
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
      <td class="num">${puedeBorrar(d)
        ? `<button class="btn ghost small" data-del="${d.id}">Borrar</button>`
        : `<span class="muted" title="Instrumento compartido: lo usan todos los usuarios">compartido</span>`}</td>
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
      : `<div class="empty-state"><div class="big">${icono("base","ico-xl")}</div>
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
   El estante elegido, y el último de los tres pasos: Mining busca, el Databank
   junta todo lo que encontró corrida por corrida, y acá quedan las pocas que
   uno decidió quedarse. La diferencia con el banco es el tope: el banco se
   poda solo cuando se llena, esto no se toca nunca. */
async function refreshSavedCount() {
  try {
    S.saved = await api.get("/api/strategies");
    const el = $("#saved-count");
    if (el) el.textContent = S.saved.length || "";
  } catch (e) { /* si el backend no responde ya hay un aviso arriba */ }
}

/* Los MetaTrader instalados. Se pregunta una vez al arrancar: instalar un
   terminal mientras la aplicación está abierta es raro, y preguntarlo en cada
   exportación recorrería el disco cada vez. */
async function refreshMt5() {
  try {
    const r = await api.get("/api/metatrader");
    S.mt5.terminales = r.terminales || [];
    const existe = S.mt5.terminales.some(t => t.id === S.mt5.elegido);
    // sin elección previa —o con una que apunta a un MetaTrader desinstalado—
    // manda el que se usó más recientemente, que viene primero
    if (S.mt5.elegido === null || (S.mt5.elegido && !existe)) {
      S.mt5.elegido = S.mt5.terminales.length ? S.mt5.terminales[0].id : "";
      localStorage.setItem("qf.mt5", S.mt5.elegido);
    }
  } catch (e) { S.mt5.terminales = []; }
}

async function refreshBancoCount() {
  try {
    const r = await api.get("/api/corridas");
    S.banco.corridas = r.corridas;
    S.banco.total = r.total;
    S.banco.tope = r.tope;
    const el = $("#banco-count");
    if (el) el.textContent = r.total || "";
  } catch (e) { /* ídem */ }
}

PAGES.saved = async (main) => {
  await refreshDatasets();
  await refreshSavedCount();
  const items = S.saved || [];

  if (!items.length) {
    main.innerHTML = pageHead("Mis estrategias",
      "Las estrategias que guardes quedan acá, aunque vuelvas a minar con otros filtros.") +
      `<div class="card"><div class="empty-state">
        <div class="big">${icono("marcador","ico-xl")}</div>
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
        <button class="btn ghost small" data-export="${esc(s.id)}">${icono("bajar")} MQL5</button>
        <button class="btn ghost small" data-del-strat="${esc(s.id)}" title="Borrar">${icono("cerrar")}</button>
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
      // lo escribe el servidor, que corre en esta misma máquina: la ventana
      // nativa cancela las descargas del navegador y el botón no hacía nada
      const r = await api.post("/api/export/mql5/archivo", {
        spec: s.spec, name: `BQ_${s.name.replace(/[^\w]/g, "_")}`,
        dataset_id: (s.meta || {}).dataset_id,
        timeframe: (s.meta || {}).timeframe, metrics: (s.meta || {}).metrics,
      });
      toast(`${r.archivo} guardado en ${r.carpeta}`, "ok");
    } catch (e) { if (!pedirCuenta(e.status)) toast(e.message, "err"); }
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
  /* El tramo tiene que ser el mismo con el que se midió, o el backtest corre
     sobre toda la historia y devuelve otra estrategia distinta con el mismo
     nombre. Las guardadas antes de que esto se registrara no lo tienen: se
     avisa en vez de mostrar números que no coinciden con la fila. */
  const r = t.measured_range;
  openInspector(row, {
    dataset_id: t.dataset_id, timeframe: t.timeframe || "1h",
    date_from: r ? r.from : undefined,
    date_to: r ? r.to : undefined,
    sinRango: !r,
    settings: { spread: t.spread, slippage: t.slippage,
                commission_pct: t.commission, initial_capital: t.capital },
  });
}

/* ========================================================= página DATABANK ==
   El banco es donde queda TODO lo minado, corrida por corrida.

   Antes esto no existía: el databank vivía en la memoria del trabajo en curso
   y apretar Iniciar otra vez lo borraba entero. Comparar dos configuraciones
   significaba anotar los números a mano antes de volver a minar, y una
   estrategia que se veía bien el martes no estaba el miércoles.

   La corrida no es una etiqueta decorativa, es la unidad de sentido. Dos filas
   de corridas distintas pueden tener el mismo "42% anual" y no querer decir lo
   mismo: el rendimiento y la caída escalan con el riesgo por operación, así
   que 42% al 1% y 42% al 3% son estrategias muy distintas. Por eso cada fila
   se muestra siempre con su origen, y por eso la vista de todas juntas avisa
   qué columnas se pueden comparar entre corridas y cuáles no. */

/* Qué exigió cada corrida, con el nombre que ve el usuario.

   Sale de la misma tabla que arma la pantalla de Mining y no de una copia: dos
   listas de los mismos filtros terminan diciendo cosas distintas del mismo
   número en cuanto se renombra uno. Al final va el que ya no se ofrece, para
   que las corridas viejas sigan pudiendo contar qué se les pidió. */
const VARA = [
  ...CRITERIA.map(cr => [CRIT_FIELD[cr.key], cr.label, cr.unit]),
  ["min_net_pct", "Ganancia total ≥", "%"],
];

/* Las columnas que dependen del tamaño de posición. Un riesgo del 3% por
   operación da más o menos el triple de rendimiento Y el triple de caída que
   el 1%: ordenar una lista mezclada por estas columnas ordena por la perilla
   de riesgo, no por la calidad de la estrategia. Las otras —profit factor,
   score, aciertos, meses positivos— son proporciones y no se mueven con el
   tamaño, así que sí comparan de verdad. */
const COLS_CON_RIESGO = new Set(["cagr", "dd"]);

const BANCO_COLS = [
  ["score", "Score", "Puntaje propio de robustez: qué tan repetible parece la estrategia, no cuánto rindió."],
  ["cagr", "Anual", "Rendimiento anualizado. Escala con el riesgo por operación: no se compara entre corridas de distinto riesgo."],
  ["pf", "PF", "Profit factor: cuántos dólares ganó por cada dólar que perdió. No depende del tamaño de posición, así que compara bien entre corridas."],
  ["dd", "Máx. DD", "Máxima caída desde un pico. Escala con el riesgo por operación igual que el rendimiento."],
  ["trades", "Ops.", "Cantidad de operaciones. Pocas operaciones hacen que cualquier métrica sea poco confiable."],
  ["months", "Meses +", "Porcentaje de meses cerrados en ganancia. Alto significa que gana seguido, no de un solo golpe."],
  ["oos", "Fuera<br>de muestra", "Profit factor fuera de muestra sobre el de adentro. Cerca de 1 la ventaja se sostuvo."],
];

const nombreCorto = (s) => String(s || "—").replace(/ M1.*/, "");

function etiquetaCorrida(c) {
  return `${nombreCorto(c.dataset_name)} · ${c.timeframe || "1h"}`;
}

/** El riesgo por operación de una corrida, que es lo que hace comparables (o
 *  no) sus números con los de otra. */
function riesgoDe(c) {
  const r = (c.contexto || {}).risk || {};
  return r.size_mode === "fixed_units" ? `${r.size_value} lotes` : `${r.size_value ?? "—"}%`;
}

function varaDe(c) {
  const acc = (c.contexto || {}).accept || {};
  const puestos = VARA.filter(([k]) => acc[k] != null)
    .map(([k, lab, u]) => `${lab} ${acc[k]}${u}`);
  const min = (c.contexto || {}).min_trades;
  if (min) puestos.unshift(`${min}+ operaciones`);
  return puestos.length ? puestos.join(" · ") : "sin filtros";
}

/* El orden con el que abre cada vista.

   Dentro de una corrida el puesto es el ranking que le dio el minero, que es
   su recomendación y por eso manda. Entre corridas ese mismo número no ordena
   nada: el puesto 1 de EURUSD y el puesto 1 de XAUUSD quedan pegados y la
   lista sale intercalada sin criterio. Ahí ordena el score, que es lo único
   comparable entre búsquedas porque no depende del riesgo de cada una. */
const ORDEN_NATURAL = (todas) => todas
  ? { key: "score", dir: -1 }
  : { key: "puesto", dir: 1 };

async function cargarBanco({ corridas = true } = {}) {
  if (corridas) {
    const r = await api.get("/api/corridas");
    S.banco.corridas = r.corridas;
    S.banco.total = r.total;
    S.banco.tope = r.tope;
    // una corrida podada o borrada no puede seguir siendo el filtro activo, o
    // la tabla queda vacía para siempre sin decir por qué
    if (S.banco.corrida && !r.corridas.some(c => c.id === S.banco.corrida)) {
      S.banco.corrida = "";
      S.banco.sel.clear();
    }
  }
  const s = S.bancoSort;
  S.banco.filas = await api.get("/api/banco?" + new URLSearchParams({
    corrida: S.banco.corrida, orden: s.key, dir: s.dir === 1 ? "asc" : "desc",
  }));
  // lo tildado que ya no está (borrado, podado, o de otra corrida) se suelta:
  // si no, el contador diría "5 seleccionadas" con tres filas a la vista
  const vivos = new Set(S.banco.filas.map(f => f.banco_id));
  [...S.banco.sel].forEach(id => { if (!vivos.has(id)) S.banco.sel.delete(id); });
}

PAGES.banco = async (main) => {
  await Promise.all([refreshDatasets(), cargarBanco()]);
  const b = S.banco;

  if (!b.corridas.length) {
    main.innerHTML = pageHead("Databank", "Todo lo que encontrás, corrida por corrida.") +
      `<div class="card"><div class="empty-state">
        <div class="big">${icono("banco", "ico-xl")}</div>
        <b>El banco está vacío</b>
        <p class="mt">Cada búsqueda que termina deja acá sus estrategias con el instrumento,
          la temporalidad y los filtros con los que se encontraron. Se acumulan: minar de
          nuevo ya no borra lo anterior.</p>
        <button class="btn mt" id="ir-a-minar">Ir a Mining</button>
      </div></div>`;
    $("#ir-a-minar", main).onclick = () => navigate("mining");
    return;
  }

  main.innerHTML = `<div id="banco-cabecera"></div>
    <div id="banco-corridas"></div><div id="banco-tabla"></div>`;

  pintarCabecera();
  pintarCorridas();
  pintarBanco();
};

/* La cuenta de arriba vive en su propio contenedor porque cambia.

   Estaba escrita de una sola vez al abrir la pantalla, así que borrar tres
   estrategias dejaba el título diciendo veinte con diecisiete en la tabla.
   Un número que se contradice con lo que está justo debajo hace dudar de los
   dos, y de paso del borrado que uno acaba de hacer. */
function pintarCabecera() {
  const host = $("#banco-cabecera");
  if (!host) return;
  const b = S.banco;
  const lleno = b.tope ? b.total / b.tope : 0;
  host.innerHTML = pageHead("Databank",
    `${fmtInt(b.total)} estrategia${b.total === 1 ? "" : "s"} de
     ${b.corridas.length} corrida${b.corridas.length === 1 ? "" : "s"}.`,
    `<div class="ph-pill ${lleno > 0.85 ? "alerta" : ""}">
       <b>${fmtInt(b.total)}</b><u>/${fmtInt(b.tope)}</u>
       <em>${lleno > 0.85 ? "casi lleno" : "capacidad"}</em></div>`);
  // y el de la barra lateral, que es el mismo dato en otro lado
  const nav = $("#banco-count");
  if (nav) nav.textContent = b.total || "";
}

/* Las corridas como una lista, no como pestañas: son hasta cuarenta y cada
   una necesita decir su instrumento, su temporalidad, su riesgo y su vara.
   Eso no entra en una pestaña. */
function pintarCorridas() {
  const host = $("#banco-corridas");
  if (!host) return;
  const b = S.banco;
  const activa = b.corridas.find(c => c.id === b.corrida);

  host.innerHTML = `<div class="card">
    <h2>Corridas <span class="hint">cada búsqueda quedó con la configuración
      que la produjo · clic para ver sólo la suya</span></h2>
    <div class="corridas-lista">
      <button class="corrida-chip ${b.corrida ? "" : "on"}" data-corrida="">
        <b>Todas</b><span>${fmtInt(b.total)} estrategias</span></button>
      ${b.corridas.map(c => `
        <button class="corrida-chip ${b.corrida === c.id ? "on" : ""} ${c.n ? "" : "vacia"}"
          data-corrida="${esc(c.id)}" title="${esc(varaDe(c))}">
          <b>${esc(etiquetaCorrida(c))}</b>
          <span>${c.n ? `${c.n} · riesgo ${esc(riesgoDe(c))}` : "sin resultados"}</span>
        </button>`).join("")}
    </div>
    ${activa ? `
      <div class="corrida-ficha">
        <div class="cf-datos">
          <div><span>Buscó</span><b>${fmtInt(activa.tested)} candidatas</b></div>
          <div><span>Encontró</span><b>${activa.encontradas ?? activa.n}${
            activa.n !== (activa.encontradas ?? activa.n)
              ? `<u class="cf-quedan"> · quedan ${activa.n}</u>` : ""}</b></div>
          <div><span>Tardó</span><b>${fmtDur(activa.elapsed)}</b></div>
          <div><span>Terminó</span><b>${esc(activa.ended)}</b></div>
          <div><span>Semilla</span><b>${activa.seed ?? "—"}</b></div>
          <div><span>Dirección</span><b>${
            (activa.contexto || {}).direction === "short" ? "cortos"
            : (activa.contexto || {}).direction === "both" ? "ambos" : "largos"}</b></div>
        </div>
        <p class="cf-vara"><span>Vara</span> ${esc(varaDe(activa))}</p>
        <div class="cf-acciones">
          <button class="btn ghost small" id="repetir-corrida">Repetir esta configuración</button>
          <button class="linkbtn peligro" id="borrar-corrida">${icono("basura","ico-sm")} Borrar la corrida entera</button>
        </div>
        <p class="stage-note">Repetir no da las mismas estrategias: la semilla es aleatoria y cada
          búsqueda explora otras combinaciones. Dos corridas iguales que rinden distinto son
          varianza de la búsqueda, no una configuración mejor que la otra.</p>
      </div>` : ""}
  </div>`;

  $$("[data-corrida]", host).forEach(btn => btn.onclick = async () => {
    if (S.banco.corrida === btn.dataset.corrida) return;
    S.banco.corrida = btn.dataset.corrida;
    // cambiar de corrida cambia la población: mantener lo tildado dejaría
    // acciones en masa apuntando a filas que ya no se ven
    S.banco.sel.clear();
    S.bancoSort = ORDEN_NATURAL(!S.banco.corrida);
    await cargarBanco({ corridas: false });
    pintarCorridas();
    pintarBanco();
  });

  const repetir = $("#repetir-corrida", host);
  if (repetir) repetir.onclick = () => repetirCorrida(activa);

  const borrar = $("#borrar-corrida", host);
  if (borrar) borrar.onclick = async () => {
    if (!confirm(`¿Borrar la corrida ${etiquetaCorrida(activa)} y sus ${activa.n} estrategias?\n\n` +
                 `Las que ya copiaste a Mis estrategias no se tocan.`)) return;
    try {
      await api.del(`/api/corridas/${activa.id}`);
      S.banco.corrida = "";
      S.banco.sel.clear();
      await cargarBanco();
      pintarCabecera();
      pintarCorridas();
      pintarBanco();
      toast("Corrida borrada", "ok");
    } catch (e) { toast(e.message, "err"); }
  };
}

function pintarBanco() {
  const host = $("#banco-tabla");
  if (!host) return;
  const b = S.banco, s = S.bancoSort;
  const todas = !b.corrida;
  const porId = Object.fromEntries(b.corridas.map(c => [c.id, c]));

  // ¿la vista mezcla corridas con distinto riesgo? Es lo que decide si las
  // columnas de rendimiento y caída significan lo mismo de una fila a otra.
  const riesgos = new Set(b.filas.map(f => riesgoDe(porId[f.corrida_id] || {})));
  const mezcla = todas && riesgos.size > 1;

  const th = (key, label, ayuda) => {
    const activa = s.key === key;
    const flecha = activa ? (s.dir === -1 ? icono("baja","ico-sm") : icono("sube","ico-sm")) : "";
    const ojo = mezcla && COLS_CON_RIESGO.has(key) ? " mixta" : "";
    return `<th class="num orden ${activa ? "activa" : ""}${ojo}" data-sort="${key}"
      title="${esc(ayuda)}${activa ? "" : " · clic para ordenar"}">${label}<i>${flecha}</i></th>`;
  };

  const todosTildados = b.filas.length && b.filas.every(f => b.sel.has(f.banco_id));

  host.innerHTML = `<div class="card">
    <h2>${todas ? "Todas las estrategias" : etiquetaCorrida(porId[b.corrida] || {})}
      <span class="hint">${b.filas.length} a la vista · clic en una fila para analizarla</span></h2>

    ${mezcla ? `<div class="banner info mt" style="margin-bottom:14px">
      <span class="b-ic">${icono("info")}</span><div>
      <b>Estás viendo corridas con riesgos distintos.</b>
      <b>Anual</b> y <b>Máx. DD</b> escalan con el riesgo por operación, así que entre
      corridas ordenan por esa perilla y no por la estrategia.
      <b>PF</b>, <b>Score</b> y <b>Meses +</b> son proporciones: ésas sí comparan.</div>
    </div>` : ""}

    <div class="seleccion ${b.sel.size ? "activa" : ""}">
      <span class="sel-n">${b.sel.size} seleccionada${b.sel.size === 1 ? "" : "s"}</span>
      <button class="btn small" id="sel-guardar">${icono("marcador","ico-sm")} Guardar en Mis estrategias</button>
      <button class="btn ghost small" id="sel-borrar">${icono("basura","ico-sm")} Quitar del banco</button>
      <button class="linkbtn" id="sel-limpiar">Limpiar</button>
    </div>

    ${b.filas.length ? `<div class="databank-wrap"><table class="banco">
      <thead><tr>
        <th class="tick"><input type="checkbox" id="sel-todas" ${todosTildados ? "checked" : ""}
          aria-label="Seleccionar todas las de la vista"></th>
        <th>Estrategia</th>
        ${todas ? `<th>Corrida</th>` : `<th class="num orden ${s.key === "puesto" ? "activa" : ""}"
          data-sort="puesto" title="El orden que le dio el minero, por QF Score">#<i>${
            s.key === "puesto" ? icono("sube","ico-sm") : ""}</i></th>`}
        ${BANCO_COLS.map(([k, l, a]) => th(k, l, a)).join("")}
      </tr></thead>
      <tbody>${b.filas.map(f => {
        const m = f.metrics || {}, c = porId[f.corrida_id] || {};
        return `<tr class="clickable ${b.sel.has(f.banco_id) ? "tildada" : ""}" data-fila="${esc(f.banco_id)}">
          <td class="tick"><input type="checkbox" data-tick="${esc(f.banco_id)}"
            ${b.sel.has(f.banco_id) ? "checked" : ""} aria-label="Seleccionar ${esc(f.name)}"></td>
          <td><span class="strat-name">${esc(f.name)}</span>
              <div class="strat-genes">${esc(f.genes_label || "")}</div></td>
          ${todas
            ? `<td class="origen"><b>${esc(nombreCorto(c.dataset_name))}</b>
                 <div class="run-sub">${esc(c.timeframe || "")} · riesgo ${esc(riesgoDe(c))}</div></td>`
            : `<td class="rank-cell"><span class="rank">${String(f.puesto + 1).padStart(2, "0")}</span></td>`}
          <td class="num">${scoreCell(f.score)}</td>
          <td class="num ${(m.cagr_pct ?? 0) >= 0 ? "pos" : "neg"}"><b>${
            m.cagr_pct != null ? fmtPct(m.cagr_pct) : "—"}</b></td>
          <td class="num">${m.profit_factor != null ? fmtNum(m.profit_factor) : "—"}</td>
          <td class="num neg">${m.max_drawdown_pct != null ? fmtNum(m.max_drawdown_pct, 1) + "%" : "—"}</td>
          <td class="num">${fmtInt(m.trades ?? 0)}</td>
          <td class="num">${fmtNum(m.months_positive_pct ?? 0, 0)}%</td>
          <td class="num">${oosCell(f)}</td>
        </tr>`;
      }).join("")}</tbody></table></div>`
      : bancoVacioHtml(porId[b.corrida])}
  </div>`;

  cablearBanco(host);
}

/* Una corrida sin filas puede serlo por dos motivos opuestos, y confundirlos
   manda a hacer cosas distintas: si la búsqueda no encontró nada hay que
   aflojar la vara, y si las borraste no hay nada que arreglar. */
function bancoVacioHtml(c) {
  if (!c) {
    return `<div class="empty-state"><b>No queda nada en el banco.</b>
      <p class="mt">Las que hayas guardado siguen en Mis estrategias.</p></div>`;
  }
  if (!c.encontradas) {
    return `<div class="empty-state">
      <div class="big">${icono("diana","ico-xl")}</div>
      <b>Esta búsqueda no encontró ninguna.</b>
      <p class="mt">Probó ${fmtInt(c.tested)} candidatas sobre
        ${esc(nombreCorto(c.dataset_name))} y ninguna pasó la vara:
        <b>${esc(varaDe(c))}</b>.</p>
      <p class="mt muted">Queda anotada igual — es el experimento que conviene no repetir
        por olvido. Repetí la configuración y aflojá el filtro que más descarta.</p>
    </div>`;
  }
  return `<div class="empty-state"><b>Le sacaste las ${c.encontradas} que había encontrado.</b>
    <p class="mt">Las que hayas guardado siguen en Mis estrategias.</p></div>`;
}

function cablearBanco(host) {
  const b = S.banco;

  $$("[data-sort]", host).forEach(th => th.onclick = async () => {
    const key = th.dataset.sort;
    const s = S.bancoSort;
    // menos es mejor en la caída: ahí el primer clic tiene que traer las mejores
    const natural = key === "dd" || key === "puesto" ? 1 : -1;
    S.bancoSort = s.key === key ? { key, dir: -s.dir } : { key, dir: natural };
    await cargarBanco({ corridas: false });
    pintarBanco();
  });

  const refrescar = () => pintarBanco();

  $$("[data-tick]", host).forEach(cb => cb.onclick = (ev) => {
    ev.stopPropagation();      // el clic en la casilla no abre el inspector
    const id = cb.dataset.tick;
    if (cb.checked) b.sel.add(id); else b.sel.delete(id);
    refrescar();
  });

  const todas = $("#sel-todas", host);
  if (todas) todas.onclick = (ev) => {
    ev.stopPropagation();
    if (todas.checked) b.filas.forEach(f => b.sel.add(f.banco_id));
    else b.sel.clear();
    refrescar();
  };

  $$("[data-fila]", host).forEach(tr => tr.onclick = (ev) => {
    if (ev.target.closest(".tick")) return;
    abrirDelBanco(b.filas.find(f => f.banco_id === tr.dataset.fila));
  });

  $("#sel-limpiar", host).onclick = () => { b.sel.clear(); refrescar(); };

  $("#sel-guardar", host).onclick = async () => {
    const ids = [...b.sel];
    if (!ids.length) return;
    const btn = $("#sel-guardar", host);
    btn.disabled = true;
    try {
      const r = await api.post("/api/banco/guardar", { ids });
      const n = r.guardadas.length;
      // guardar es COPIAR: la fila sigue en el banco. Si además la sacara,
      // revisar una corrida la iría vaciando a medida que uno la mira.
      b.sel.clear();
      refrescar();
      await refreshSavedCount();
      toast(`${n} estrategia${n === 1 ? "" : "s"} en Mis estrategias — siguen también en el banco`, "ok");
    } catch (e) { toast(e.message, "err"); }
    btn.disabled = false;
  };

  $("#sel-borrar", host).onclick = async () => {
    const ids = [...b.sel];
    if (!ids.length) return;
    if (!confirm(`¿Quitar ${ids.length} estrategia${ids.length === 1 ? "" : "s"} del banco?\n\n` +
                 `Las que hayas guardado en Mis estrategias no se tocan.`)) return;
    try {
      await api.post("/api/banco/borrar", { ids });
      b.sel.clear();
      await cargarBanco();
      pintarCabecera();
      pintarCorridas();
      pintarBanco();
      toast(`${ids.length} fuera del banco`, "ok");
    } catch (e) { toast(e.message, "err"); }
  };
}

/* Vuelve a Mining con la configuración exacta de una corrida vieja.

   Es lo que hace del banco un cuaderno de laboratorio y no un archivo muerto:
   se prueba una idea, se ve el resultado, se vuelve a la que había funcionado
   y se le cambia una sola cosa. Reconstruir eso a mano son quince campos. */
function repetirCorrida(c) {
  if (!c) return;
  const ctx = c.contexto || {};
  const acc = ctx.accept || {}, risk = ctx.risk || {}, ajustes = ctx.settings || {};

  S.cfg.critOn = {};
  for (const [ui, backend] of Object.entries(CRIT_FIELD)) {
    if (acc[backend] == null) continue;
    S.cfg.critOn[ui] = true;
    S.cfg[ui] = acc[backend];
  }
  S.cfg.direction = ctx.direction || "both";
  if (ctx.min_trades != null) S.cfg.minTrades = ctx.min_trades;
  if (ctx.target_keep != null) S.cfg.goal = ctx.target_keep;
  if (ctx.method) S.cfg.method = ctx.method;
  if (ctx.fitness) S.cfg.fitness = ctx.fitness;

  if (risk.size_mode === "fixed_units") {
    S.cfg.sizing = "lots";
    if (risk.size_value != null) S.cfg.lots = risk.size_value;
  } else {
    S.cfg.sizing = "risk";
    if (risk.size_value != null) S.cfg.riskPct = risk.size_value;
  }
  if (risk.reward_ratio != null) S.cfg.rr = risk.reward_ratio;

  // los costos van con la configuración: son del mercado que se minó, y son
  // justamente lo que no hay que arrastrar de otro instrumento
  if (ajustes.spread != null) S.cfg.spread = ajustes.spread;
  if (ajustes.slippage != null) S.cfg.slippage = ajustes.slippage;
  if (ajustes.commission_pct != null) S.cfg.commission = ajustes.commission_pct;
  if (ajustes.initial_capital != null) S.cfg.capital = ajustes.initial_capital;

  S.sel.timeframe = c.timeframe || "1h";
  const hay = S.datasets.some(d => d.id === c.dataset_id);
  if (hay) S.sel.dataset_id = c.dataset_id;
  saveCfg();
  navigate("mining").then(() => toast(hay
    ? "Configuración cargada — dale a Iniciar"
    : `Configuración cargada, pero ${nombreCorto(c.dataset_name)} ya no está en el workspace`,
    hay ? "ok" : "err"));
}

/* Una fila del banco se reabre con los datos de SU corrida, no con lo que esté
   cargado ahora en Mining: el instrumento, el tramo medido y los costos son los
   de aquella búsqueda. Con los de la pantalla, el backtest devolvería otra
   estrategia con el mismo nombre. */
function abrirDelBanco(f) {
  if (!f) return;
  const c = S.banco.corridas.find(x => x.id === f.corrida_id);
  const ctx = c ? (c.contexto || {}) : {};
  const rango = ctx.measured_range;
  if (!c || !S.datasets.some(d => d.id === c.dataset_id)) {
    toast("El instrumento con el que se minó ya no está en el workspace", "err");
    return;
  }
  openInspector(f, {
    dataset_id: c.dataset_id, timeframe: c.timeframe || "1h",
    date_from: rango ? rango.from : undefined,
    date_to: rango ? rango.to : undefined,
    sinRango: !rango,
    settings: ctx.settings || {},
    // decir de qué corrida salió, no "guardada": todavía no lo está, y
    // confundir las dos cosas hace creer que ya se rescató algo que no
    etiqueta: `del banco · ${etiquetaCorrida(c)} · riesgo ${riesgoDe(c)}`,
  });
}

/* =========================================================== página MINING */
PAGES.mining = async (main) => {
  await refreshDatasets();
  if (!S.datasets.length) {
    main.innerHTML = pageHead("Mining", "Buscá estrategias sobre datos reales.") +
      `<div class="card"><div class="empty-state"><div class="big">${icono("pico","ico-xl")}</div>
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
  // la ventana de arranque se resuelve antes de dibujar los campos, o el
  // primer render mostraría el historial entero y cambiaría solo después
  aplicarVentanaPorDefecto(curDs);
  const bounds = datasetBounds(curDs);
  const range = effectiveRange(curDs);
  const acotado = !isFullRange(curDs);
  const aniosTotales = bounds.lo && bounds.hi
    ? (new Date(bounds.hi) - new Date(bounds.lo)) / 31557600000 : 0;

  const critRow = (cr) => {
    const on = !!S.cfg.critOn[cr.key];
    // la explicación va en el título de la fila entera: son términos de mesa
    // —profit factor, drawdown, win rate— y quien recién empieza necesita
    // poder preguntar qué son sin salir de la pantalla
    return `<div class="critrow ${on ? "on" : ""}" data-crit="${cr.key}"
      title="${esc(cr.ayuda || "")}">
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
              <div class="fld"><span>Dirección</span>
                <div class="seg full" id="m-dir">
                  ${[["long", "Largos"], ["short", "Cortos"], ["both", "Ambos"]]
                    .map(([v, t]) => `<button data-dir="${v}" class="${c.direction === v ? "on" : ""}">${t}</button>`).join("")}
                </div>
              </div>
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
            ${acotado && aniosTotales > VENTANA_ANIOS ? `
              <div class="ventana">
                <div>Arranca en los <b>últimos ${VENTANA_ANIOS} años</b> para que la
                  primera búsqueda no tarde una eternidad. Este instrumento tiene
                  ${aniosTotales.toFixed(0)} años.</div>
                <button class="btn ghost small" id="m-todo-historial">Usar los ${
                  aniosTotales.toFixed(0)} años</button>
              </div>` : ""}
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
            <!-- Este número pasó por dos nombres malos: "Máx. filtros por
                 estrategia" describía el código, y "cuántos de estos puede
                 combinar" no decía de qué estaba hablando ni por qué importa.

                 Lo que gradúa es la COMPLEJIDAD de las reglas, que es la
                 palanca más grande que hay sobre el sobreajuste: cuantas más
                 condiciones puede apilar una estrategia, más fácil le resulta
                 describir el pasado exacto y menos le queda para el futuro.
                 Como eso es una decisión y no un número, va con nombres. -->
            <div class="fld mt"><span>Complejidad de las reglas
                <span class="hint">cuántos filtros de contexto puede exigir
                  una estrategia al mismo tiempo</span></span></div>
            <div class="complejidad" id="m-complejidad">
              ${COMPLEJIDAD.map(c2 => `<button data-filtros="${c2.n}"
                class="${+c.maxFilters === c2.n ? "on" : ""}" title="${esc(c2.ayuda)}">
                <b>${esc(c2.nombre)}</b><em>${c2.n === 0 ? "sólo el disparador"
                  : c2.n === 1 ? "1 condición" : `hasta ${c2.n}`}</em></button>`).join("")}
            </div>
            <p class="help-note" id="m-filtnote"></p>
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
            <div class="sugerido" id="m-sugerido" hidden></div>
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
            <p class="help-note" id="m-critaviso"></p>
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
        <button class="btn big" id="m-run">${icono("pico")} Iniciar mining</button>
        <div class="run-acciones" id="m-acciones" style="display:none">
          <button class="btn ghost big" id="m-pause">${icono("pausa")} Pausar</button>
          <button class="btn ghost big" id="m-stop">${icono("detener")} Detener</button>
        </div>
        ${progressHtml("m-prog")}
      </div>
    </aside>

    <section class="results">
      <div id="m-live"></div>
      <div id="m-bank"></div>
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
    // el período propio se conserva y sólo se le ajustan los bordes; el que
    // puso la aplicación se recalcula, porque doce años se cuentan desde el
    // final de CADA instrumento
    const clamped = S.sel.rangoPropio ? clampRangeTo(ds)
      : (aplicarVentanaPorDefecto(ds), false);
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
    // a partir de acá el período es una decisión suya: deja de reacomodarse
    // solo al cambiar de instrumento
    S.sel.rangoPropio = true;
    saveCfg();
    updateNotes();
  };
  dFrom.onchange = onDate;
  dTo.onchange = onDate;

  const todoHist = $("#m-todo-historial", main);
  if (todoHist) todoHist.onclick = () => {
    S.sel.dateFrom = S.sel.dateTo = "";
    S.sel.rangoPropio = true;      // elegido a mano: no se vuelve a acotar solo
    saveCfg();
    navigate("mining");
  };
  // el calendario se abre tocando el campo entero, no sólo el iconito
  [dFrom, dTo].forEach(el => el.onmousedown = (ev) => {
    if (typeof el.showPicker !== "function") return;
    ev.preventDefault();
    el.focus();
    try { el.showPicker(); } catch (e) { /* el navegador lo abre solo */ }
  });

  tfSel.onchange = () => { S.sel.timeframe = tfSel.value; saveCfg(); updateNotes(); };

  /* dirección: tres opciones excluyentes se eligen mejor viéndolas todas que
     abriendo un desplegable para descubrir cuáles hay */
  $$("#m-dir button", main).forEach(b => b.onclick = () => {
    S.cfg.direction = b.dataset.dir;
    $$("#m-dir button", main).forEach(x => x.classList.toggle("on", x === b));
    saveCfg();
    updateNotes();
  });
  // dos momentos: `input` sigue lo que se escribe sin corregirlo, `change`
  // —que salta al salir del campo o al confirmar— es donde se acomoda
  $$("[data-cfg]", main).forEach(el => {
    el.oninput = () => { harvestCfg(main); updateNotes(); };
    el.onchange = () => {
      harvestCfg(main, { normalizar: true });
      // el spread corregido a mano queda atado a SU instrumento: el de oro de
      // tu broker no tiene por qué perderse por ir a mirar el S&P y volver
      if (el.dataset.cfg === "spread" || el.dataset.cfg === "slippage") recordarCostos();
      updateNotes();
    };
  });

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
        txt = `<b class="neg">${icono("alerta")} Costo imposible: ${pct.toFixed(1)}% por operación.</b>
          Parece el spread de otro instrumento — con esto ninguna estrategia puede ganar.
          <button class="linkbtn" id="fix-cost">Usar los de ${esc(ds.name.replace(/ M1.*/, ""))}</button>`;
      }
      note.classList.toggle("danger", bad);
      note.innerHTML = txt;
      const fixC = $("#fix-cost", note);
      if (fixC) fixC.onclick = () => { adoptInstrumentDefaults(); navigate("mining"); };
    }

    /* El spread sugerido de ESTE mercado, siempre a la vista.

       Antes el número aparecía solo y no había forma de saber si correspondía
       al instrumento cargado: podía ser el que la aplicación puso, o el que
       quedó de otro mercado, y se ven exactamente igual. Decir cuál es el de
       referencia convierte un número a ciegas en uno que se puede comprobar
       contra el broker. */
    const sug = $("#m-sugerido");
    if (sug) {
      const cat = ds ? S.catalog.find(c => c.dataset_id === ds.id) : null;
      const refSpread = ds && ds.suggested_spread != null ? ds.suggested_spread
        : (cat ? cat.spread : null);
      if (refSpread == null) {
        // instrumento propio del usuario: no hay referencia que ofrecer
        sug.hidden = true;
      } else {
        sug.hidden = false;
        const mercado = esc(ds.name.replace(/ M1.*/, ""));
        const num = (v) => (+v).toLocaleString("es-AR", { maximumFractionDigits: 5 });
        const igual = Math.abs(+S.cfg.spread - refSpread) < 1e-9;
        sug.innerHTML = igual
          ? `<span class="sg-ok">${icono("tilde","ico-sm")}</span>
             <div>Es el spread típico de <b>${mercado}</b>: ${num(refSpread)}.
               Cambialo si tu broker te cobra otro.</div>`
          : `<span class="sg-ojo">${icono("info","ico-sm")}</span>
             <div>Estás usando <b>${num(S.cfg.spread)}</b>. El típico de
               <b>${mercado}</b> es <b>${num(refSpread)}</b>.
               <button class="linkbtn" id="usar-sugerido">Usar el típico</button></div>`;
        const usar = $("#usar-sugerido", sug);
        if (usar) usar.onclick = () => {
          // se borra el valor propio: pedir el sugerido es decir que el de uno
          // ya no vale, y si quedara guardado volvería en la próxima visita
          if (S.cfg.costos) delete S.cfg.costos[ds.id];
          adoptInstrumentDefaults();
          navigate("mining");
        };
      }
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
    // Destildado no es "sin configurar": es "no se exige". Con la casilla en
    // blanco el número de al lado igual se ve, y eso hace creer que la vara
    // está puesta.
    const critAviso = $("#m-critaviso");
    if (critAviso) {
      const activos = CRITERIA.filter(cr => S.cfg.critOn[cr.key]).length;
      critAviso.innerHTML = activos ? "" :
        `<b class="neg">${icono("alerta")} No hay ningún filtro de calidad tildado.</b> Con sólo
         <b>${S.cfg.minTrades}+ operaciones</b> entra casi cualquier candidata: el
         databank se llena en segundos con estrategias que pierden plata. Los
         números de abajo no se aplican hasta que tildes su casilla.`;
    }

    const critHelp = $("#m-crithelp");
    if (critHelp) {
      if (!S.cfg.critOn.minWinRate) {
        critHelp.innerHTML = "";
      } else {
        const rr = +S.cfg.rr, be = 100 / (1 + rr), pedido = +S.cfg.minWinRate;
        critHelp.innerHTML = pedido <= be
          ? `<b class="neg">${icono("alerta")} ${pedido}% de aciertos no alcanza para ganar plata</b> con
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
    const compl = COMPLEJIDAD.find(c => c.n === +S.cfg.maxFilters);
    set("sum-blocks", `${drv} disparadores · ${flt} filtros · complejidad ${
      (compl ? compl.nombre : S.cfg.maxFilters).toString().toLowerCase()}`);

    // qué significa el número, con los valores que el usuario tiene puestos
    const fn = $("#m-filtnote");
    if (fn) {
      const n = +S.cfg.maxFilters;
      fn.innerHTML = !flt
        ? `Sin filtros marcados, cada estrategia es sólo su disparador de entrada.`
        : n === 0
          ? `En <b>mínima</b>, los filtros marcados no se usan: cada estrategia entra
             sólo con su disparador.`
          : `Marcaste <b>${flt} filtros</b>. Cada candidata elige al azar
             <b>entre 0 y ${n}</b> de ellos y los exige a la vez. Más filtros por
             estrategia hace reglas más específicas —y más fáciles de ajustar al
             pasado sin que sirvan después.`;
    }

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

  $$("#m-complejidad button", main).forEach(b => b.onclick = () => {
    S.cfg.maxFilters = +b.dataset.filtros;
    $$("#m-complejidad button", main).forEach(o =>
      o.classList.toggle("on", +o.dataset.filtros === S.cfg.maxFilters));
    saveCfg();
    updateNotes();
  });

  updateNotes();
  if (fixed) {
    toast(fixed.badCost
      ? `Costos y salidas ajustados a ${fixed.name}: el spread anterior era ${fixed.costPct.toFixed(1)}% del precio`
      : `Salidas ajustadas a la escala de ${fixed.name}`, "ok");
  }
  if (S.mineResult || S.mineLive) renderMining(S.mineResult || S.mineLive, !!S.mineResult);
  else renderIdle();

  $("#m-stop").onclick = async () => {
    if (S.mineJobId) {
      try { await api.post(`/api/jobs/${S.mineJobId}/stop`); toast("Deteniendo…"); }
      catch (e) { toast(e.message, "err"); }
    }
  };

  /* Pausar no es detener a medias.
     Detener descarta la población, los genomas ya probados y el punto de la
     semilla: volver a arrancar re-explora lo mismo desde cero. Pausar congela
     el hilo con todo eso intacto, así que reanudar sigue en la candidata
     siguiente. Es lo que permite liberar el procesador un rato sin perder los
     minutos que ya se buscaron. */
  $("#m-pause").onclick = async () => {
    if (!S.mineJobId) return;
    const btn = $("#m-pause");
    btn.disabled = true;
    try {
      const r = await api.post(`/api/jobs/${S.mineJobId}/pause`, { paused: !S.minePaused });
      pintarPausa(r.paused);
      toast(r.paused
        ? "En pausa — se guarda dónde iba, no se pierde nada"
        : "Sigue la búsqueda");
    } catch (e) { toast(e.message, "err"); }
    btn.disabled = false;
  };

  $("#m-run").onclick = async () => {
    // se normaliza acá también: si alguien toca "Minar" con el cursor todavía
    // dentro de un campo, el `change` nunca llegó a saltar y la corrida saldría
    // con un valor a medio escribir o por debajo del piso
    harvestCfg(main, { normalizar: true });
    const checked = (sel) => $$(`${sel} .blockitem input`, main)
      .filter(cb => cb.checked).map(cb => cb.dataset.tid);
    const drivers = checked("#m-drivers");
    if (!drivers.length) { toast("Elegí al menos un disparador de entrada", "err"); return; }
    S.mining = true; S.mineResult = null; S.mineLive = null;
    // el punto de la barra lateral late mientras haya corrida: es la única
    // señal de que algo pasa si el usuario se fue a otra pantalla
    $("#nav [data-page='mining']")?.classList.add("minando");
    $("#m-run").disabled = true;
    $("#m-acciones").style.display = "";
    pintarPausa(false);
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
        // el botón se sincroniza con el servidor y no con el clic: si el pedido
        // de pausa se perdió, la pantalla no puede seguir diciendo que pausó
        pintarPausa(!!j.paused);
        if (j.partial) { S.mineLive = j.partial; renderMining(j.partial, false); }
      }, id => { S.mineJobId = id; });
      S.mineResult = result;
      hideProgress("m-prog");
      renderMining(result, true);
      // la corrida ya quedó archivada del lado del servidor: acá sólo se
      // actualiza el contador de la barra para que se note que entró
      refreshBancoCount().then(() => {
        const el = $("#banco-count");
        if (el) { el.classList.add("nuevo"); setTimeout(() => el.classList.remove("nuevo"), 2000); }
      });
      const kept = result.databank.length;
      if (result.stopped) toast(`Detenido — ${kept} estrategias, guardadas en el Databank`, "ok");
      else if (result.reached_goal)
        toast(`${kept} estrategias en ${fmtDur(result.elapsed_s)} — quedaron en el Databank`, "ok");
      else toast(`Se probaron ${fmtInt(result.tested)} y sólo ${kept} pasaron los filtros`, "err");
      if (result.podadas) {
        toast(`El banco estaba lleno: se soltaron las ${result.podadas} corridas más viejas`);
      }
    } catch (e) { toast(e.message, "err"); hideProgress("m-prog"); }
    S.mining = false; S.mineJobId = null; S.minePaused = false;
    $("#nav [data-page='mining']")?.classList.remove("minando");
    const run = $("#m-run"), acciones = $("#m-acciones");
    if (run) run.disabled = false;
    if (acciones) acciones.style.display = "none";
    $("#m-runbar")?.classList.remove("running");
    lockSetup(false);
  };
};

/* El botón de pausa dice qué va a pasar si lo apretás, no en qué estado está:
   "Seguir" cuando está pausado, "Pausar" cuando está buscando. Un control que
   se rotula con su estado hace dudar en el momento de tocarlo. */
function pintarPausa(on) {
  S.minePaused = !!on;
  const btn = $("#m-pause");
  if (!btn) return;
  btn.innerHTML = on ? `${icono("seguir")} Seguir` : `${icono("pausa")} Pausar`;
  btn.classList.toggle("pausado", !!on);
  $("#m-runbar")?.classList.toggle("pausado", !!on);
  $("#nav [data-page='mining']")?.classList.toggle("pausado", !!on);
}

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
      <span class="idle-ic">${icono("pico","ico-xl")}</span>
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

/* Columnas ordenables del databank.

   El minero entrega el databank ordenado por QF Score, que es su criterio de
   robustez. Pero mirar la misma lista por rendimiento, por caída máxima o por
   cantidad de operaciones responde preguntas distintas, y hasta ahora había que
   leer cien filas a ojo.

   El orden vive en S y no en el nodo: la tabla se rehace sola cada vez que
   entra una estrategia nueva, así que cualquier estado guardado en el DOM se
   perdería a los pocos segundos. */
const ORDENABLES = {
  score:  (r) => r.score,
  oos:    (r) => r.oos_ratio,
  stop:   (r) => r.stop_mult,
  cagr:   (r) => r.metrics.cagr_pct,
  net:    (r) => r.metrics.net_profit_pct,
  pf:     (r) => r.metrics.profit_factor,
  sharpe: (r) => r.metrics.sharpe,
  dd:     (r) => r.metrics.max_drawdown_pct,
  months: (r) => r.metrics.months_positive_pct,
  top:    (r) => r.metrics.top_trade_share_pct,
  expo:   (r) => r.metrics.exposure_pct,
  win:    (r) => r.metrics.win_rate_pct,
  trades: (r) => r.metrics.trades,
};
//: en estas, menos es mejor: el primer clic tiene que mostrar las mejores
const MENOS_ES_MEJOR = new Set(["dd", "top"]);

function ordenarBank(bank) {
  const s = S.bankSort;
  if (!s || !s.key || !ORDENABLES[s.key]) return bank;
  const leer = ORDENABLES[s.key];
  // copia: ordenar el array del snapshot alteraría el estado del minado
  return [...bank].sort((a, b) => {
    const va = leer(a), vb = leer(b);
    // los sin dato van siempre al fondo, se ordene como se ordene: si no,
    // pedir "las mejores por fuera de muestra" arrancaría con las que no tienen
    const na = va == null || Number.isNaN(va), nb = vb == null || Number.isNaN(vb);
    if (na || nb) return na && nb ? 0 : (na ? 1 : -1);
    return (va - vb) * s.dir;
  });
}

/* Qué se ve mientras el databank todavía está vacío y la búsqueda corre.

   Antes acá no había nada: la tabla salía vacía y lo único que se movía era un
   contador arriba. Una búsqueda que puede tardar minutos sin aceptar ninguna
   candidata parecía colgada, y la reacción natural es apretar Iniciar de nuevo.

   Lo que se muestra no es decoración: son las candidatas REALES que se están
   probando y por qué criterio se cayeron. Un rechazo por operaciones
   insuficientes se arregla distinto que uno por profit factor, y ver cuál
   domina es lo que dice qué filtro aflojar. */
function buscandoHtml(snap) {
  const probadas = snap.tested || 0;
  const fallos = snap.rechazos || {};
  const barras = Object.entries(fallos)
    .sort((a, b) => b[1] - a[1]).slice(0, 4);
  const tope = barras.length ? barras[0][1] : 1;

  return `<div class="buscando">
    <div class="buscando-top">
      <span class="pulso"><i></i><i></i><i></i></span>
      <div>
        <b class="contador" data-valor="${probadas}">${fmtInt(probadas)}</b>
        <span>candidatas probadas${snap.passed
          ? ` · <b class="pos">${fmtInt(snap.passed)}</b> aceptadas` : ""}</span>
      </div>
    </div>
    ${barras.length ? `
      <div class="buscando-motivos">
        <span class="bm-tit">Por qué se caen</span>
        ${barras.map(([etiqueta, n]) => `
          <div class="bm-fila">
            <span class="bm-lab">${esc(etiqueta)}</span>
            <span class="bm-track"><i style="width:${(n / tope * 100).toFixed(0)}%"></i></span>
            <span class="bm-n">${fmtInt(n)}</span>
          </div>`).join("")}
      </div>`
      : `<p class="bm-tit" style="margin-top:16px">Preparando indicadores…</p>`}
    ${consejo(snap)}
    <p class="buscando-pie">Las que pasen la vara van apareciendo acá. Podés
      dejarlo corriendo y volver.</p>
  </div>`;
}

/* Qué tocar para que empiece a entrar algo.

   El minero ya lo calcula: sabe cuántas candidatas fallaron por un solo filtro
   y hasta dónde llegó la mejor de ésas. Eso es una recomendación concreta —
   "aflojá esto hasta acá y entran doce"— y hasta ahora sólo aparecía cuando la
   búsqueda terminaba sin nada, que es tarde: el usuario ya esperó los minutos
   completos. Mostrarlo mientras corre le permite frenar y corregir.

   Se muestra recién con una muestra suficiente. Con veinte candidatas el filtro
   que más descarta todavía es ruido, y recomendar sobre ruido manda a aflojar
   el que no era. */
function consejo(snap) {
  const d = snap.diagnosis || {};
  if (!d.text || (snap.tested || 0) < 60) return "";
  return `<div class="consejo"><span class="c-ic">${icono("idea")}</span><div>${d.text}</div></div>`;
}

function cablearOrden(raiz) {
  $$("[data-sort]", raiz).forEach(th => th.onclick = () => {
    const key = th.dataset.sort;
    const s = S.bankSort || {};
    if (s.key === key) {
      // tercer clic: vuelve al orden del minero, que es el que él recomienda
      S.bankSort = s.dir === (MENOS_ES_MEJOR.has(key) ? 1 : -1)
        ? { key, dir: -s.dir } : { key: null, dir: -1 };
    } else {
      S.bankSort = { key, dir: MENOS_ES_MEJOR.has(key) ? 1 : -1 };
    }
    if (S.mineResult || S.mineLive) {
      renderMining(S.mineResult || S.mineLive, !!S.mineResult);
    }
  });
}

/* Lo que se ve de la corrida desde cualquier pantalla.

   Se dibuja en la barra lateral, que está siempre presente: si el usuario se
   fue a Datos mientras busca, esto es lo único que le dice que la búsqueda
   sigue viva y cuánto le falta. Sin esto tenía que volver a Minado para
   averiguarlo. */
function pintarCorrida(snap, finished) {
  const caja = $("#corrida");
  if (!caja) return;
  if (!snap || finished) { caja.hidden = true; caja.innerHTML = ""; return; }

  const meta = snap.target_keep || null;
  const hechas = Math.min((snap.databank || []).length, meta || Infinity);
  const frac = meta ? Math.min(hechas / meta, 1) : 0;
  caja.hidden = false;
  caja.innerHTML = `
    <div class="corrida-rot">Corrida activa</div>
    <div class="corrida-cifra">${meta ? `${hechas}<u>/${meta}</u>` : fmtInt(snap.tested || 0)}</div>
    <div class="corrida-pie">${meta ? "en el databank" : "probadas"} ·
      ${fmtInt(snap.tested || 0)} probadas</div>
    ${meta ? `<div class="corrida-barra"><i style="width:${(frac * 100).toFixed(1)}%"></i></div>` : ""}`;
}

/* ------------------------------------------------------- render resultados */
function renderMining(snap, finished) {
  const live = $("#m-live"), bankBox = $("#m-bank");
  if (!live || !snap) return;
  const bank = ordenarBank(snap.databank || []);
  pintarCorrida(snap, finished);
  // el campeón es el mejor por QF Score, no el primero de la vista: reordenar
  // la tabla no cambia cuál estrategia recomienda el minero
  const champ = (snap.databank || [])[0];

  const s = S.bankSort || {};
  const th = (key, label, ayuda) => {
    const activa = s.key === key;
    const flecha = activa ? (s.dir === -1 ? icono("baja","ico-sm") : icono("sube","ico-sm")) : "";
    return `<th class="num orden ${activa ? "activa" : ""}" data-sort="${key}"
      title="${esc(ayuda)}${activa ? "" : " · clic para ordenar"}">${label}<i>${flecha}</i></th>`;
  };

  const goal = snap.target_keep || null;
  const kept = goal ? Math.min(bank.length, goal) : bank.length;
  const frac = goal ? kept / goal : (snap.tested / (snap.target || 1));
  const rate = snap.tested && snap.elapsed_s > 0 ? snap.passed / snap.elapsed_s : 0;
  // sin filtros activos el databank también junta perdedoras: decirlo de frente
  const winners = bank.filter(r => r.metrics.net_profit_pct > 0).length;

  // por qué terminó: el usuario no tiene que deducirlo de los números
  let banner = "";
  if (finished && snap.stopped) {
    banner = `<div class="banner info"><span class="b-ic">${icono("detener")}</span><div>
      <b>Búsqueda detenida por vos.</b> ${bank.length === 1
        ? "La estrategia que ya había entrado al databank sigue"
        : `Las ${bank.length} estrategias que ya habían entrado al databank siguen`}
      acá abajo, lista${bank.length === 1 ? "" : "s"} para inspeccionar o exportar.</div></div>`;
  } else if (finished && snap.exhausted) {
    banner = `<div class="banner"><span class="b-ic">${icono("info")}</span><div>
      <b>Se agotaron las combinaciones posibles</b> con los bloques que marcaste.
      Marcá más bloques en la sección 2 o subí el máximo de filtros para ampliar el espacio.</div></div>`;
  } else if (finished && snap.hit_cap) {
    banner = `<div class="banner"><span class="b-ic">${icono("alerta")}</span><div>
      <b>Se llegó al tope de seguridad de ${fmtInt(snap.target)} candidatas</b> con
      ${bank.length} de ${goal} estrategias. Tus filtros son muy exigentes para este mercado:
      destildá alguno en la sección 5, cambiá las salidas en la 3, o subí el tope en Avanzado
      si querés que siga buscando más tiempo.</div></div>`;
  } else if (!finished && !bank.length && snap.tested >= 20 && snap.diagnosis?.text) {
    // no esperar al final para explicar por qué no entra ninguna: el usuario
    // puede aflojar el filtro ahora mismo en vez de mirar un cero por minutos
    banner = `<div class="banner"><span class="b-ic">${icono("diana")}</span><div>${snap.diagnosis.text}</div></div>`;
  } else if (finished && goal && snap.reached_goal) {
    banner = `<div class="banner ok"><span class="b-ic">${icono("tilde")}</span><div>
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
        ? `No se detiene hasta juntar <b>${goal}</b> que cumplan la vara — faltan <b>${Math.max(goal - kept, 0)}</b>.`
        : `Probando candidatas hasta llegar a <b>${fmtInt(snap.target)}</b>.`}
        · semilla <b>${snap.seed}</b> para reproducir esta corrida</div>
      ${varaAplicada(snap)}
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
      <div class="champ-tag">${finished ? `${icono("estrella")} Mejor QF Score` : `${icono("estrella")} Mejor hasta ahora`}</div>
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

  /* El minado refresca cada 400 ms. Rehacer todo el panel en cada vuelta hacía
     titilar la pantalla: se destruían y volvían a parsear la tabla entera, los
     SVG de las curvas y las barras del score, aunque no hubiera cambiado nada.

     Ahora cada pieza vive en su propio contenedor y sólo se reescribe la que
     de verdad cambió. El progreso cambia siempre —son segundos y contadores—
     pero es lo más chico; el campeón y el databank cambian sólo cuando entra
     una estrategia nueva, que es cada varios segundos.

     El orden entre progreso y campeón se invierte al terminar. Se hace con CSS
     y no moviendo nodos, porque mover un nodo lo repinta igual que recrearlo. */
  const histHtml = snap.best_history?.length > 1 ? `<div class="card">
       <h2>Evolución del mejor fitness <span class="hint">cómo fue mejorando la búsqueda</span></h2>
       <div class="chart-box short" id="m-hist"></div></div>` : "";

  if (!live.dataset.partido) {
    live.innerHTML = `<div id="m-goal"></div><div id="m-champ"></div><div id="m-histbox"></div>`;
    live.dataset.partido = "1";
  }
  live.classList.toggle("terminado", !!finished);
  const pintar = (sel, html) => {
    const el = $(sel, live);
    // comparar la cadena cuesta microsegundos; volver a parsear y maquetar el
    // HTML cuesta milisegundos y un parpadeo
    if (!el || el.dataset.h === html) return false;
    el.innerHTML = html;
    el.dataset.h = html;
    return true;
  };
  pintar("#m-goal", goalCard);
  pintar("#m-champ", champCardHtml);
  pintar("#m-histbox", histHtml);

  // el gráfico se redibuja siempre que haya datos nuevos, pero el contenedor
  // sólo se recrea cuando cambió: así el canvas no se pierde en cada vuelta
  if (snap.best_history?.length > 1) {
    const caja = $("#m-hist");
    if (caja) Charts.line(caja, { series: [{ values: snap.best_history, fill: true }], height: 170 });
  }
  const champCard = $("#champ-card");
  if (champCard) champCard.onclick = () => openInspector(champ);

  const splitNote = snap.split ? `
    <div class="banner info mt" style="margin-bottom:14px">
      <span class="b-ic">${icono("marcador")}</span><div>
        <b>Validado fuera de muestra.</b> La búsqueda usó
        ${esc(snap.split.is_from)} → ${esc(snap.split.is_to)}
        (${fmtInt(snap.split.is_bars)} velas) y cada estrategia se volvió a correr sobre
        ${esc(snap.split.oos_from)} → ${esc(snap.split.oos_to)}
        (${fmtInt(snap.split.oos_bars)} velas) que nunca vio.
        La columna <b>Fuera de muestra</b> es la que dice si la ventaja era real.</div>
    </div>` : "";

  const bankHtml = `
  <div class="card">
    ${splitNote}
    <h2>Databank <span class="hint">${bank.length} estrategias ordenadas por QF Score
      (robustez, no rentabilidad) · clic en cualquiera para analizarla a fondo</span></h2>
    ${bank.length ? `<div class="databank-wrap"><table>
      <!-- OCHO COLUMNAS, NO DIECISEIS.
           La tabla tenia dieciseis y por eso necesitaba scroll horizontal: para
           ver el drawdown habia que arrastrar, y comparar dos estrategias
           obligaba a ir y volver. Estas ocho son las que se miran para decidir
           si una candidata merece abrirse; las otras siguen enteras en el
           inspector, a un clic de distancia. Una tabla que entra en pantalla se
           compara de un vistazo; una que no, se lee de a pedazos. -->
      <thead><tr>
        <th>#</th>
        <th>Estrategia</th>
        <th>Capital</th>
        ${th("score", "Score", "Puntaje propio de robustez: qué tan repetible parece la estrategia, no cuánto rindió.")}
        ${th("cagr", "Anual", "Rendimiento ANUALIZADO: cuánto rindió por año, en promedio compuesto. Es el que sirve para comparar estrategias que corrieron distinta cantidad de tiempo.")}
        ${th("pf", "PF", "Profit factor: cuántos dólares ganó por cada dólar que perdió. Debajo de 1 la estrategia pierde plata.")}
        ${th("dd", "Máx. DD", "Máxima caída: lo peor que llegó a bajar la cuenta desde un pico hasta el fondo. Es lo que hay que poder aguantar sin cerrar todo.")}
        ${th("trades", "Ops.", "Cantidad de operaciones. Pocas operaciones hacen que cualquier métrica sea poco confiable.")}
        ${th("months", "Meses +", "Porcentaje de meses cerrados en ganancia. Alto significa que gana seguido, no de un solo golpe.")}
        ${snap.split ? th("oos", "Fuera<br>de muestra", "Profit factor fuera de muestra dividido por el de adentro. Cerca de 1 la ventaja se sostuvo; cerca de 0 la estrategia sólo describía el pasado.") : ""}
      </tr></thead>
      <tbody>${bank.map((r, i) => {
        const m = r.metrics;
        return `<tr class="clickable" data-row="${i}">
          <td class="rank-cell"><span class="rank">${String(i + 1).padStart(2, "0")}</span></td>
          <td><span class="strat-name">${esc(r.name)}</span></td>
          <td class="spark-cell">${Charts.sparkSvg(r.spark)}</td>
          <td class="num">${scoreCell(r.score)}</td>
          <td class="num ${m.cagr_pct >= 0 ? "pos" : "neg"}"><b>${fmtPct(m.cagr_pct)}</b></td>
          <td class="num">${fmtNum(m.profit_factor)}</td>
          <td class="num neg">${fmtNum(m.max_drawdown_pct, 1)}%</td>
          <td class="num">${fmtInt(m.trades)}</td>
          <td class="num">${fmtNum(m.months_positive_pct ?? 0, 0)}%</td>
          ${snap.split ? `<td class="num">${oosCell(r)}</td>` : ""}
        </tr>`;
      }).join("")}</tbody></table></div>`
      : !finished ? buscandoHtml(snap)
      : `<div class="empty-state">
           <div class="big">ðŸ”</div>
           <b>${fmtInt(snap.tested)} probadas, ninguna pasó los filtros.</b>
           ${snap.diagnosis?.text ? `<p class="mt">${snap.diagnosis.text}</p>` : ""}
           ${snap.diagnosis?.suggestion ? `
             <div class="suggestion mt">
               <div class="sug-title">${icono("idea")} Cómo llegar a ese objetivo</div>
               <p>${snap.diagnosis.suggestion.text}</p>
               ${snap.diagnosis.suggestion.warning
                 ? `<p class="sug-warn">${icono("alerta")} ${esc(snap.diagnosis.suggestion.warning)}</p>` : ""}
               ${snap.diagnosis.suggestion.unreachable
                 ? `<button class="btn small mt" id="apply-target"
                      data-target="${snap.diagnosis.suggestion.realistic_target}">
                      Fijar objetivo en ${snap.diagnosis.suggestion.realistic_target}% anual y volver a minar</button>`
                 : `<button class="btn small mt" id="apply-risk"
                      data-needed="${snap.diagnosis.suggestion.needed}">
                      Subir a ${snap.diagnosis.suggestion.needed}% y volver a minar</button>`}
             </div>` : ""}
           <p class="mt muted">También podés destildar filtros en la sección 5, o cambiar las
             salidas en la 3 — eso cambia por completo qué estrategias funcionan.</p>
         </div>`}
  </div>`;

  /* Es lo más caro de la pantalla: una tabla de hasta cien filas, cada una con
     su curva en SVG. Rehacerla cada 400 ms era el grueso del parpadeo, y encima
     perdía el scroll de la tabla y la fila sobre la que estuviera el mouse.
     Sólo cambia cuando entra una estrategia nueva. */
  const cambio = bankBox.dataset.h !== bankHtml;
  if (cambio) {
    /* Cada estrategia nueva rehace la tabla, y con ella se perdía el
       desplazamiento: si estabas mirando las columnas de la derecha, volvías
       al principio cada pocos segundos. Se guarda antes y se repone después,
       sobre el nodo NUEVO — el viejo ya no existe cuando termina el reemplazo. */
    const scroll = $(".databank-wrap", bankBox);
    const x = scroll ? scroll.scrollLeft : 0;
    const y = scroll ? scroll.scrollTop : 0;

    bankBox.innerHTML = bankHtml;
    bankBox.dataset.h = bankHtml;

    const nuevo = $(".databank-wrap", bankBox);
    if (nuevo && (x || y)) { nuevo.scrollLeft = x; nuevo.scrollTop = y; }

    $$("[data-row]", bankBox).forEach(tr => tr.onclick = () => openInspector(bank[+tr.dataset.row]));
    cablearOrden(bankBox);
  }

  /* Aplica una sugerencia y vuelve a minar.

     Antes sólo cambiaba el número y pedía apretar el botón. Dos cosas fallaban
     con eso. El cartel dice "y volver a minar", así que no minar es incumplir
     lo que promete el propio botón. Y como el resultado viejo seguía en S,
     al re-dibujar la página volvía a aparecer el mismo fracaso con el mismo
     cartel: se veía exactamente igual que antes de tocarlo, y parecía roto. */
  const aplicarSugerencia = (cambiar, mensaje) => {
    cambiar();
    saveCfg();
    // el resultado viejo tiene que irse antes de re-dibujar, o la pantalla
    // sigue mostrando la corrida que acabamos de dejar atrás
    S.mineResult = null;
    S.mineLive = null;
    navigate("mining").then(() => {
      toast(mensaje, "ok");
      const run = $("#m-run");
      if (run) { run.scrollIntoView({ block: "center" }); run.click(); }
    });
  };

  const applyRisk = $("#apply-risk", bankBox);
  // el mensaje sale del dato del botón y no de S.cfg: como es un argumento, se
  // evalúa ANTES de aplicar el cambio y mostraría el valor viejo
  if (applyRisk) applyRisk.onclick = () => aplicarSugerencia(
    () => { S.cfg.riskPct = +applyRisk.dataset.needed; },
    `Riesgo ${+applyRisk.dataset.needed}% — buscando de nuevo`);

  const applyTarget = $("#apply-target", bankBox);
  if (applyTarget) applyTarget.onclick = () => {
    const sug = snap.diagnosis.suggestion;
    aplicarSugerencia(() => {
      S.cfg.minCagr = +applyTarget.dataset.target;
      S.cfg.critOn.minCagr = true;
      S.cfg.riskPct = Math.round(sug.current * 4 * 10) / 10;
    }, `Objetivo ${+applyTarget.dataset.target}% anual — buscando de nuevo`);
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
        ? `<span class="badge">${esc(ctx.etiqueta || "guardada")}</span>`
        : `<span class="badge">fitness ${fmtNum(row.fitness, 3)}</span>`}</h2>
        <p>${esc(row.blocks || "")} · <span style="font-family:ui-monospace">${esc(row.genes_label)}</span></p></div>
      <button class="sheet-close">${icono("cerrar")}</button>
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
      // el mismo tramo que se midió al guardarla; sin esto corría sobre toda
      // la historia y devolvía otra estrategia con el mismo nombre
      ...(ctx.date_from ? { date_from: ctx.date_from, date_to: ctx.date_to } : {}),
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
    renderInspector($("#insp-body", host), row, result, ctx);
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

function renderInspector(box, row, res, ctx) {
  const m = res.metrics;
  /* Las guardadas antes de que se registrara el tramo no se pueden reproducir:
     el backtest corre sobre toda la historia y da otros números que los de la
     fila. Decirlo es lo único honesto — callarlo deja al usuario comparando
     dos cosas distintas sin saberlo. */
  const avisoRango = ctx && ctx.sinRango ? `
    <div class="banner warn" style="margin-bottom:16px"><span class="b-ic">${icono("alerta")}</span><div>
      <b>Esta estrategia se guardó sin registrar el período.</b> Lo que ves acá se
      calculó sobre <b>toda la historia</b> del instrumento, así que puede no coincidir
      con las métricas de la lista, que salieron del tramo que minaste.
      Volvé a minarla y guardala de nuevo para que queden atadas.</div></div>` : "";
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

  box.innerHTML = avisoRango + `
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
    <button class="btn" id="insp-mql5">${icono("bajar")} MetaTrader 5 (.mq5)</button>
    <button class="btn ghost" id="insp-pine">${icono("bajar")} TradingView (.pine)</button>
    <button class="btn ghost" id="insp-copiar">${icono("copiar")} Copiar Pine</button>
    <button class="btn ghost" id="insp-save">${icono("marcador")} Guardar en Mis estrategias</button>
  </div>
  <div class="guardado" id="insp-guardado" hidden></div>
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
          /* EL TRAMO MEDIDO. Sin esto, reabrir la estrategia corría el
             backtest sobre toda la historia en vez del período que se minó, y
             los números no se parecían en nada a los guardados: con riesgo
             agresivo sobre veinte años, hasta un -100%.

             Sale del propio minero y no de la pantalla: si el usuario cambia
             el calendario después de minar, lo que hay que reproducir sigue
             siendo el tramo de la corrida, no el que esté elegido ahora. Y
             cuando hubo división in/out, es el tramo de adentro — que es
             sobre el que se midieron estas métricas. */
          measured_range: (S.mineResult || S.mineLive || {}).measured_range || null,
          saved_at: new Date().toISOString(),
        },
      });
      toast(`${row.name} guardada en Mis estrategias`, "ok");
      refreshSavedCount();
    } catch (e) { toast(e.message, "err"); }
    btn.disabled = false;
  };

  /* El instrumento sale del contexto de la estrategia cuando lo tiene —una
     guardada, una del banco— y no de lo que esté elegido ahora en Mining. Si
     no, exportar una estrategia de EURUSD mientras mirás el S&P escribía el
     símbolo equivocado adentro del propio Expert Advisor. */
  const cuerpoExport = () => ({
    spec: row.spec, name: `BQ_${row.name.replace("-", "_")}`,
    dataset_id: ctx ? ctx.dataset_id : S.sel.dataset_id,
    timeframe: (ctx ? ctx.timeframe : S.sel.timeframe) || "1h",
    metrics: m,
  });

  /* MQL5 y Pine comparten todo salvo el formato. El .mq5 va a la carpeta de
     robots del MetaTrader elegido, si hay alguno instalado. */
  async function exportAs(btnId, formato, aviso) {
    const btn = $(`#${btnId}`, box);
    btn.disabled = true;
    try {
      const cuerpo = cuerpoExport();
      if (formato === "mql5" && S.mt5.elegido) cuerpo.terminal = S.mt5.elegido;
      const r = await api.post(`/api/export/${formato}/archivo`, cuerpo);
      mostrarGuardado(r, formato, r.terminal
        ? `Robot instalado en ${r.terminal} — abrilo y compilá con F7`
        : aviso);
    } catch (e) { if (!pedirCuenta(e.status)) toast(e.message, "err"); }
    btn.disabled = false;
  }

  /* Dónde quedó el archivo y qué hacer con él.

     Un aviso que se desvanece a los cuatro segundos no sirve para una ruta:
     es justo el dato que hay que leer despacio y volver a mirar. Y el botón
     que abre el archivo es el que cierra el círculo — un .mq5 abre MetaEditor
     listo para compilar, sin que haya que ir a buscarlo a ninguna carpeta. */
  function mostrarGuardado(r, formato, aviso) {
    toast(aviso, "ok");
    const caja = $("#insp-guardado", box);
    if (!caja) return;
    const esRobot = formato === "mql5";
    const opciones = esRobot && S.mt5.terminales.length > 1;
    caja.hidden = false;
    caja.innerHTML = `<span class="g-ic">${icono("tilde")}</span>
      <div class="g-txt">
        <b>${esc(r.archivo)}</b>
        <span class="g-ruta">${r.terminal
          ? `Robots de <b>${esc(r.terminal)}</b> · ya aparece en el Navegador${
              opciones ? ` · <a href="#" id="insp-cambiar">cambiar</a>` : ""}`
          : esc(r.carpeta)}</span>
        ${opciones ? `<div class="g-destino" hidden>
          <span>Tenés ${S.mt5.terminales.length} MetaTrader instalados. Mandarlo a:</span>
          <select id="insp-destino">
            ${S.mt5.terminales.map(t => `<option value="${esc(t.id)}"
              ${t.id === S.mt5.elegido ? "selected" : ""}>${esc(t.nombre)}</option>`).join("")}
            <option value="" ${S.mt5.elegido ? "" : "selected"}>Descargas</option>
          </select></div>` : ""}
      </div>
      <div class="g-acciones">
        <button class="btn small" id="insp-abrir-archivo">${
          esRobot ? "Abrir en MetaEditor" : "Abrir archivo"}</button>
        <button class="linkbtn" id="insp-abrir">Ver la carpeta</button>
      </div>`;

    $("#insp-abrir-archivo", caja).onclick = async () => {
      try { await api.post("/api/abrir-archivo", { ruta: r.ruta }); }
      catch (e) { toast(e.message, "err"); }
    };
    $("#insp-abrir", caja).onclick = async () => {
      try { await api.post("/api/abrir-carpeta", { ruta: r.carpeta }); }
      catch (e) { toast(e.message, "err"); }
    };
    /* La lista de MetaTrader arranca escondida. Mostrarla siempre convierte
       un aviso de "listo, quedó acá" en una pregunta con tres nombres casi
       iguales, y encima ya está resuelta: la aplicación eligió el terminal
       que se usó más recientemente. Sólo aparece si el usuario la pide. */
    const cambiar = $("#insp-cambiar", caja);
    if (cambiar) cambiar.onclick = (ev) => {
      ev.preventDefault();
      const panel = $(".g-destino", caja);
      if (panel) panel.hidden = false;
      cambiar.remove();
    };

    const destino = $("#insp-destino", caja);
    if (destino) destino.onchange = () => {
      S.mt5.elegido = destino.value;
      localStorage.setItem("qf.mt5", destino.value);
      // se vuelve a exportar en el acto: cambiar el destino sin mover el
      // archivo dejaría el cartel diciendo un lugar y el robot en otro
      exportAs("insp-mql5", "mql5", "Guardado");
    };
  }

  $("#insp-mql5", box).onclick = () => exportAs(
    "insp-mql5", "mql5", "Expert Advisor guardado — copialo a MQL5/Experts y compilá");
  $("#insp-pine", box).onclick = () => exportAs(
    "insp-pine", "pine", "Pine guardado — o usá Copiar y pegalo en TradingView");

  /* TradingView no se carga de un archivo: se pega en el Pine Editor. Bajar un
     .pine para después abrirlo y copiarlo a mano es dar una vuelta de más.

     Si el portapapeles se niega, este botón NO se queda sin hacer nada — que
     es exactamente el defecto que vinimos a arreglar. Guarda el archivo y lo
     dice. Peor que fallar es fallar en silencio. */
  $("#insp-copiar", box).onclick = async () => {
    const btn = $("#insp-copiar", box);
    btn.disabled = true;
    try {
      const r = await fetch("/api/export/pine", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpoExport()),
      });
      if (!r.ok) {
        const detalle = await r.json().then(j => j.detail).catch(() => r.status);
        throw Object.assign(new Error(detalle), { status: r.status });
      }
      const codigo = await r.text();
      if (await copiar(codigo)) {
        toast("Pine copiado — pegalo en el Pine Editor de TradingView", "ok");
      } else {
        const g = await api.post("/api/export/pine/archivo", cuerpoExport());
        mostrarGuardado(g, "El sistema no dejó copiar, así que lo guardé como archivo");
      }
    } catch (e) { if (!pedirCuenta(e.status)) toast(e.message, "err"); }
    btn.disabled = false;
  };
}

/* Copiar al portapapeles, con red de contención. Devuelve si se pudo.

   `navigator.clipboard` pide contexto seguro Y ventana con foco. 127.0.0.1 es
   contexto seguro, así que en la ventana nativa anda; pero abriendo la
   aplicación por la IP de la máquina en la red de casa deja de serlo. El
   camino viejo es feo y también pide foco, pero cubre casos que el nuevo no.

   No tira excepción: quien llama decide qué hacer, y lo que hace es guardar
   el archivo. */
async function copiar(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch (e) { /* seguimos por abajo */ }
  const ta = document.createElement("textarea");
  ta.value = texto;
  ta.style.cssText = "position:fixed;left:-9999px;top:0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  ta.remove();
  return ok;
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
  // Oscuro por defecto: es el mundo visual que define Botiquant Bordo, y una
  // herramienta que se mira durante horas seguidas cansa menos así.
  applyTheme(saved === "light" ? "light" : "dark", false);
  const btn = $("#theme-btn");
  if (btn) btn.onclick = () => {
    const now = document.documentElement.getAttribute("data-theme");
    applyTheme(now === "light" ? "dark" : "light", true);
  };
}

/* ---------------------------------------------------------------- cuenta
   Minar y ver resultados son libres; la cuenta hace falta sólo para bajarse
   el archivo. Así que acá no hay ningún muro: la sesión se consulta al
   arrancar y sólo se usa para dos cosas, mostrar quién sos y explicar el
   candado cuando lo tocás. */

async function refreshAuth() {
  try { S.auth = await api.get("/api/auth/me"); }
  catch (e) { S.auth = { configurado: false, usuario: null }; }
  renderAuth();
}

function renderAuth() {
  const caja = $("#acct");
  if (!caja) return;
  // Sin login configurado (instalación local) no se menciona el tema: ofrecer
  // una cuenta que no existe sólo confunde.
  if (!S.auth || !S.auth.configurado) { caja.hidden = true; return; }
  caja.hidden = false;
  caja.replaceChildren();

  const u = S.auth.usuario;
  if (!u) {
    const b = document.createElement("a");
    b.className = "acct-in";
    b.href = "/api/auth/google/start?next=/app";
    b.append(googleMark(), Object.assign(document.createElement("span"),
                                         { textContent: "Entrar con Google" }));
    caja.appendChild(b);
    return;
  }

  const chip = document.createElement("div");
  chip.className = "acct-chip";
  if (u.picture) {
    const img = document.createElement("img");
    img.src = u.picture; img.alt = ""; img.referrerPolicy = "no-referrer";
    chip.appendChild(img);
  }
  // textContent y no innerHTML: el nombre lo eligió el usuario en Google y
  // podría traer marcado.
  const txt = document.createElement("div");
  txt.className = "acct-txt";
  const n = document.createElement("b"); n.textContent = u.name || u.email;
  const e = document.createElement("span"); e.textContent = u.email;
  txt.append(n, e);
  const out = document.createElement("button");
  out.className = "acct-out"; out.title = "Cerrar sesión"; out.textContent = "Salir";
  out.onclick = async () => {
    try { await api.post("/api/auth/logout", {}); } catch (err) { /* igual salimos */ }
    S.auth.usuario = null; renderAuth(); toast("Sesión cerrada", "ok");
  };
  chip.append(txt, out);
  caja.appendChild(chip);
}

function googleMark() {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 48 48"); s.setAttribute("class", "g-mark");
  s.innerHTML =
    '<path fill="#4285F4" d="M45.1 24.5c0-1.6-.1-3.2-.4-4.7H24v8.9h11.8c-.5 2.7-2 5.1-4.4 6.7v5.5h7.1c4.2-3.8 6.6-9.5 6.6-16.4z"/>' +
    '<path fill="#34A853" d="M24 46c6 0 11-2 14.6-5.4l-7.1-5.5c-2 1.3-4.5 2.1-7.5 2.1-5.8 0-10.7-3.9-12.4-9.1H4.3v5.7C7.9 41.1 15.4 46 24 46z"/>' +
    '<path fill="#FBBC05" d="M11.6 28.1c-.4-1.3-.7-2.7-.7-4.1s.2-2.8.7-4.1v-5.7H4.3C2.8 17.1 2 20.4 2 24s.8 6.9 2.3 9.8l7.3-5.7z"/>' +
    '<path fill="#EA4335" d="M24 10.8c3.3 0 6.2 1.1 8.5 3.3l6.3-6.3C35 4.2 30 2 24 2 15.4 2 7.9 6.9 4.3 14.2l7.3 5.7c1.7-5.2 6.6-9.1 12.4-9.1z"/>';
  return s;
}

/* Un 401 acá dentro ya no es "te falta cuenta": a /app no se entra sin sesión,
   así que si el servidor la rechaza es porque venció o se cerró en otra
   pestaña. Se dice eso, que es lo que de verdad pasó, y se ofrece volver a
   entrar. Devuelve true si el error era de sesión. */
function pedirCuenta(status) {
  if (status !== 401) return false;
  const fondo = document.createElement("div");
  fondo.className = "gate-back";
  fondo.innerHTML = `
    <div class="gate" role="dialog" aria-modal="true" aria-labelledby="gate-t">
      <h3 id="gate-t">Se cerró tu sesión</h3>
      <p>Volvé a entrar para seguir. Lo que tengas guardado no se pierde: las
         estrategias del databank y los instrumentos siguen donde estaban.</p>
      <p class="gate-fine">Google nos da tu nombre, tu correo y tu foto. Nada más:
         no pedimos permiso sobre tu correo ni tus archivos, y no vas a escribir
         ninguna contraseña acá.</p>
      <div class="gate-row">
        <button class="btn ghost" data-x>Cerrar</button>
        <a class="btn" href="/api/auth/google/start?next=/app"></a>
      </div>
    </div>`;
  const entrar = $("a", fondo);
  entrar.append(googleMark(), Object.assign(document.createElement("span"),
                                            { textContent: "Entrar con Google" }));
  const cerrar = () => fondo.remove();
  $("[data-x]", fondo).onclick = cerrar;
  fondo.onclick = (ev) => { if (ev.target === fondo) cerrar(); };
  document.addEventListener("keydown", function esc(ev) {
    if (ev.key === "Escape") { cerrar(); document.removeEventListener("keydown", esc); }
  });
  document.body.appendChild(fondo);
  entrar.focus();
  return true;
}

/* -------------------------------------------------------------------- boot */
(async function boot() {
  try {
    S.meta = await api.get("/api/meta");
    $("#version").textContent = `v${S.meta.version}`;
    await refreshDatasets();
  } catch (e) { toast(`No se pudo conectar con el backend: ${e.message}`, "err"); }
  refreshAuth();
  initTheme();
  refreshSavedCount();
  refreshBancoCount();
  refreshMt5();
  $$("#nav button").forEach(b => b.onclick = () => navigate(b.dataset.page));
  navigate(S.datasets.length ? "mining" : "data");
})();
