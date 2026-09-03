/* Botiquant SPA — sin frameworks, sin build, 100% offline.
   v4: la corrida se define por OBJETIVO (cuántas estrategias tiene que juntar
   el databank), no por cuántas candidatas probar. Rediseño completo de la UI. */

"use strict";

/* ------------------------------------------------------------------ state */
const S = {
  meta: null,
  auth: null,           // {configurado, usuario} — ver refreshAuth()
  // La licencia de esta máquina, comprobada sin red. null en un servidor
  // web, donde las licencias se emiten en vez de guardarse.
  licencia: null,       // {situacion, plan, email, alta, fundador} — ver refreshLicencia()
  datasets: [],
  catalog: [],
  /* QUE SE ESTA OPERANDO: "metatrader" (CFD) o "exchange" (perpetuos).

     No es un filtro ni una preferencia: es de qué producto se está hablando.
     Un CFD paga spread, se opera por MetaTrader y se exporta como Expert
     Advisor; un perpetuo paga comisión y funding, se opera en un exchange y se
     exporta como enlace. No hay cuenta donde convivan.

     Mezclados, la aplicación deja armar cosas que no se pueden operar: antes
     de esto, un portafolio con el S&P y BTCUSDT exportaba los dos como EA de
     MetaTrader sin un solo aviso. */
  mundo: localStorage.getItem("qf.mundo") || "metatrader",
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
  /* Qué vista se está mirando en cada sección que tiene dos. Una memoria
     por sección y no una sola compartida: son listas de vistas distintas
     —"buscar" no existe en Operar— y con una variable única entrar a una
     sección devolvía la otra a su primera vista. */
  vista: "buscar",          // Minado: "buscar" | "resultados"
  vistaOperar: "bot",       // Operar: "bot" | "claves"
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
/* Las relaciones entre las que puede elegir la búsqueda cuando se la deja.
   Son las mismas que conoce el minero (RR_CHOICES en generator.py); si las dos
   listas se separan, la pantalla ofrece algo que el servidor no va a probar. */
const RR_BUSCABLES = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0];

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
  spread: 0.36, slippage: 0.1, commission: 0, swap: 0, capital: 10000,
  /* El volumen minimo que acepta tu broker para el instrumento. Es una
     referencia como el spread: se sugiere el del catalogo y se comprueba
     contra el broker propio. */
  minLot: 0.01,
  /* Horas que adelanta el servidor del bróker respecto de UTC. Cero es un
     default honesto —hay brókers en UTC— pero equivocado para la mayoría,
     que corre en UTC+2 o UTC+3. Se pregunta en Datos y viaja en cada robot
     exportado; sólo importa si la estrategia tiene franja horaria. */
  brokerUtc: 0,
  exigirOos: false,
  minPf: 1.0, minSharpe: 0.30, maxDd: 25, minNet: 20, minWinRate: 50,
  maxFilters: 2, direction: "long", minTrades: 30,
  /* 3 y no 5, y prendido de fábrica. Medido sobre S&P y oro, doce años:

                             sólo PF>=1      + anual>=3%
         S&P 500  media           2.49%           4.99%
                  sobre 5%            2               9
         Oro      media           3.80%           5.84%
                  sobre 5%           10              13

     Duplica la calidad de lo primero que ve cualquiera. Cuesta pasar de 18 a
     74 segundos en el S&P — con la pantalla mostrando cuánto falta, se banca.

     Con 5 en vez de 3 la búsqueda se va a 518 segundos, que ya es demasiado
     para lo primero que alguien prueba. */
  minCagr: 3, minExposure: 5, minRetDd: 1.5, minTradesMonth: 4, minTradesWeek: 2,
  /* Dos varas prendidas de fábrica: que la estrategia haya ganado plata, y
     que haya ganado algo que valga la pena mirar.

     Antes no venía ninguna, con el argumento de mostrar primero que la
     búsqueda encuentra cosas. Medido, eso significaba llenar el databank en
     catorce segundos con monedas al aire: en EURUSD, 21 de las 25 que
     mostraba PERDÍAN plata. Encontrar veinticinco estrategias en catorce
     segundos no es una buena primera impresión si la mitad no sirve — es una
     promesa que el producto no cumple.

     Profit factor 1 y no 1.10 a propósito: 1 es la línea que significa algo
     —ganó contra perdió— y es la más barata de satisfacer.

     Pero PF>=1 solo devolvía 2.49% anual de media en el S&P: honesto y
     aburrido. Nadie se entusiasma con eso, y el entusiasmo de la primera
     corrida es lo que decide si alguien vuelve. Con anual>=3% la media sube a
     4.99% y las que pasan el 5% van de dos a nueve. El resto de las varas las
     sube el usuario. */
  critOn: { minPf: true, minCagr: true },
  // el número que manda: cuántas estrategias APROBADAS tiene que juntar el
  // databank antes de parar. Cuántas candidatas hagan falta no se sabe de
  // antemano — depende de qué tan exigentes sean los criterios.
  goal: 25,
  // tope de seguridad: sin esto, criterios imposibles buscarían para siempre
  maxCandidates: 20000,
  // % final del período que la búsqueda no ve. Desactivada por defecto: la
  // decisión de partir el período es del usuario, no del programa.
  oosPct: 0,
  // cuánto había elegido la última vez que estuvo prendida, para que apagarla
  // y volver a prenderla no lo mande siempre al 30
  oosUltimo: 30,
  /* Los R:B entre los que puede elegir cada candidata. `null` deja el
     comportamiento de siempre: todas usan el configurado en el paso de riesgo.

     Existe porque el R:B resultó ser lo que gobierna el win rate, y estaba
     fijo. Medido sobre SP500 a una hora, treinta estrategias por corrida: con
     1:2 la mediana de aciertos es 39,8% y NINGUNA llega a 60%; con 0,5 la
     mediana es 59,5% y quince de treinta lo pasan. Buscar aciertos altos con
     el 1:2 de fábrica no devuelve nada nunca, por más candidatas que se
     prueben — el techo no lo pone la búsqueda, lo pone la aritmética. */
  rrBuscado: null,
  fitness: "composite",
  // Cómo se dimensiona la posición. "risk" ajusta el tamaño para que tocar el
  // stop cueste un % fijo; "lots" manda siempre el mismo volumen — hay brokers
  // de CFDs que no interpretan bien un volumen calculado en cada operación.
  sizing: "risk",
  // spread y slippage que el usuario corrigió a mano, por instrumento. Vacío
  // significa "usar el sugerido de cada mercado" — ver costosDe().
  costos: {},
  /* Franjas horarias habilitadas. Con una, todas las estrategias operan ahí;
     con varias, la búsqueda elige la mejor por candidata.

     Arranca sin restricción a propósito. Activar una franja recorta las
     oportunidades disponibles en la misma proporción en que recorta las horas,
     y una configuración de fábrica que devuelve menos estrategias se siente
     rota aunque sea más correcta. La franja es una decisión del usuario, y la
     pantalla explica qué se gana con ella. */
  sessions: ["todo"],
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
// una config vieja no tiene franjas; y una lista vacía dejaría al minero sin
// ninguna opción de la que elegir, que es una búsqueda que no puede construir
// ni una candidata
if (!Array.isArray(S.cfg.sessions) || !S.cfg.sessions.length) {
  S.cfg.sessions = [...DEFAULT_CFG.sessions];
}
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
const COMPLEJIDAD = () => [0, 1, 2, 3].map(n => ({
  n, nombre: t(`cx.${n}`), ayuda: t(`cx.${n}_help`), pie: t(`cx.${n}_sub`),
}));

/* Símbolo por familia de mercado. Con cuatro tarjetas idénticas salvo el
   texto, el icono es lo que permite encontrar la que buscás de un vistazo.
   Van dibujados a mano y no con logos de marca: un CFD de Bitcoin no es
   Bitcoin, y poner el logo real sugeriría una relación que no existe. */
const INST_FAMILIA = {
  indices: { icono:
    '<path d="M3 20h18"/><rect x="5" y="11" width="3.2" height="6" rx="1"/>' +
    '<rect x="10.4" y="7" width="3.2" height="10" rx="1"/>' +
    '<rect x="15.8" y="4" width="3.2" height="13" rx="1"/>' },
  forex: { icono:
    '<path d="M4 9h13"/><path d="M14 6l3 3-3 3"/>' +
    '<path d="M20 15H7"/><path d="M10 12l-3 3 3 3"/>' },
  metals: { icono:
    '<path d="M12 3l3.2 4.4L12 21 8.8 7.4 12 3Z"/><path d="M8.8 7.4h6.4"/>' },
  crypto: { icono:
    '<circle cx="12" cy="12" r="8.5"/>' +
    '<path d="M9.6 8.4h4a1.9 1.9 0 0 1 0 3.8H9.6h4.6a1.9 1.9 0 0 1 0 3.8H9.6"/>' +
    '<path d="M11.2 6.6v1.8M11.2 16v1.8"/>' },
  bonos: { icono:
    // un cupon: rectangulo con el borde dentado de un titulo
    '<rect x="3.5" y="6.5" width="17" height="11" rx="1.5"/>' +
    '<path d="M7 10.5h10M7 13.5h6"/>' },
  energia: { icono:
    // una gota, que sirve para el crudo y para el gas
    '<path d="M12 3.5c3.4 4 5.2 6.6 5.2 9.1a5.2 5.2 0 0 1-10.4 0c0-2.5 1.8-5.1 5.2-9.1Z"/>' },
  perpetuos: { icono:
    '<circle cx="12" cy="12" r="8.5"/>' +
    '<path d="M9.6 8.4h4a1.9 1.9 0 0 1 0 3.8H9.6h4.6a1.9 1.9 0 0 1 0 3.8H9.6"/>' +
    '<path d="M11.2 6.6v1.8M11.2 16v1.8"/>' },
  _otro: { icono:
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
/* Los NOMBRES de las métricas viven en i18n.js y son los mismos en los dos
   idiomas: profit factor, drawdown, win rate, Sharpe se dicen así en la mesa,
   en MetaTrader y en TradingView. Lo que se traduce es la explicación. */
/* ═══════════════════════ QUÉ ESTÁS BUSCANDO ═══════════════════════════════
   Cada receta fija TEMPORALIDAD, R:B, COMPLEJIDAD y FILTROS. No sólo los
   filtros, y ésa es toda la diferencia entre una categoría que funciona y una
   que decora: pedir win rate ≥ 60% con el R:B 1:2 de fábrica no devuelve nada
   nunca —medido, cero de treinta— por más que el filtro esté bien puesto.

   Los números no son de gusto. Salen de barrer el espacio y mirar qué hay:
   qué win rate aparece con cada relación, cuánta caída es alcanzable, con qué
   frecuencia se opera en cada temporalidad. Una receta que pide algo que no
   existe es peor que no tener recetas, porque manda a esperar veinte minutos
   para que no salga nada.

   Y cada una fija su TOPE DE CANDIDATAS, que no es un detalle. Medido: una
   candidata cuesta 8,3 microsegundos por vela, así que a 30 minutos son 1,04
   segundos y a 15 son 2,08. Con el tope de fábrica —veinte mil— una receta a
   30 minutos correría casi SEIS HORAS antes de rendirse, y a 15 minutos once.
   Los topes de acá abajo están puestos para que ninguna pase de unos diez
   minutos en el peor caso, que es cuando no encuentra lo que busca.

   Cada tarjeta dice qué busca Y QUÉ CUESTA. Todas cuestan algo: acertar más
   seguido significa ganar menos por acierto, y caer poco significa rendir
   menos. Callar la contrapartida sería vender lo que la portada dice no
   vender.

   Y CADA UNA TRAE SU FORMA DE PORTAFOLIO —cuántos bots y cuánto de la cuenta
   se pone a trabajar—, que es la parte que faltaba. Una receta decía dónde
   buscar y se callaba qué hacer con lo encontrado, así que el usuario que
   menos sabe terminaba encendiendo una sola estrategia al 100% de la cuenta:
   la configuración más riesgosa posible, elegida por omisión.

   LA RECETA TRAE CRITERIOS Y NO ESTRATEGIAS, y esa diferencia decide si esto
   sirve o miente. Un paquete de estrategias ya elegidas sería una promesa
   sobre resultados —lo que este proyecto ya sacó de la pantalla una vez— y
   además se agotaría solo: si todos corren las mismas cinco, deja de haber
   ventaja. MEDIDO acá: tres corridas con semillas distintas dieron 101
   estrategias y CERO repetidas. Dos personas con la misma receta obtienen
   portafolios disjuntos, y eso es lo que hace que la receta se pueda
   repartir. */
/* A qué mundo pertenece un histórico, por su nombre. Se clasifica contra el
   catálogo; los que no se pueden clasificar —un CSV propio— pertenecen a los
   dos, porque adivinarles un mundo sería peor que dejarlos a la vista. */
function mundoDeDataset(nombre) {
  const token = String(nombre || "").trim().split(/\s+/)[0].toLowerCase();
  const enCat = (S.catalog || []).find(c => c.label.toLowerCase() === token);
  return enCat ? (enCat.mundo || "metatrader") : null;
}

/* Los históricos que se ven en el mundo elegido, EN EL ORDEN DEL CATÁLOGO.

   No en el orden en que se cargaron: el servidor los manda del más nuevo al
   más viejo, y con eso el desplegable de Minar —y el elegido por defecto—
   arrancaba en el último perpetuo que se sembró, LINK o ADA, antes que
   Bitcoin. El catálogo va del más conocido al menos; lo que no está en el
   catálogo (un CSV propio) va al final, en su orden de carga. */
function datasetsDelMundo() {
  const puesto = (d) => {
    const token = String(d.name || "").trim().split(/\s+/)[0].toLowerCase();
    const i = (S.catalog || []).findIndex(c => c.label.toLowerCase() === token);
    return i < 0 ? 1e6 : i;
  };
  return (S.datasets || [])
    .filter(d => { const m = mundoDeDataset(d.name); return m === null || m === S.mundo; })
    .map((d, i) => [puesto(d), i, d])
    .sort((a, b) => a[0] - b[0] || a[1] - b[1])
    .map(x => x[2]);
}

const RECETAS = () => [
  {
    /* SÓLO EN CFD. Un desafío de fondeo es cosa de las firmas que fondean
       cuentas de MetaTrader; en un exchange de cripto no existe, y la
       tarjeta ahí no significaba nada (2 de septiembre). */
    id: "fondeo", ico: "diana", mundo: "metatrader",
    /* La más difícil de las cuatro, y los números explican por qué.

       Un desafío tiene fecha de vencimiento, así que no alcanza con que la
       estrategia sea buena: tiene que OPERAR dentro del plazo. El problema es
       que las dos cosas se pelean. Medido sobre SP500 a 30 minutos, cuatro
       años, 1400 candidatas, aflojando de a una exigencia:

           rentable + caída ≤8% + 3 por semana ....... nada
           rentable + 3 por semana (sin caída) ....... nada
           rentable + caída ≤8% (sin frecuencia) .... 5, con 0,62 por semana
           lo mismo pidiendo 2 por semana ........... 1
           lo mismo pidiendo 1 por semana ........... 2, con 2,03 de mediana
           rentable + 3 por semana + caída ≤15% ..... nada

       La que ahoga es la frecuencia, no la caída: aflojar el drawdown al 15%
       sigue sin dar nada. Y bajar a 15 minutos EMPEORA —ahí no sale nada ni
       siquiera sin pedir frecuencia— porque se paga el spread tres veces más
       seguido y se come la ventaja.

       Ser rentable es ser selectivo, y ser selectivo es operar poco. Por eso
       la frecuencia no filtra: ORDENA. Entran las que pasaron la vara y arriba
       quedan las que más operan, así que siempre hay tabla.

       Lo que trae, medido con esta misma configuración:

           SP500    la primera opera 1,46 por semana — una cada 4,8 días
                    con 8,89% anual y 6,3% de caída
           BTCUSD   la primera opera 0,33 por semana — una cada 21 días

       Por eso la tarjeta NO promete una frecuencia: varía demasiado entre
       mercados y poner un número sería inventarlo. Promete lo que sí cumple en
       los dos, que es la caída chica — y que además es la regla que de verdad
       elimina gente en un desafío. */
    /* CINCO BOTS Y 80% DE LA CUENTA. Un desafío se pierde por la caída
       diaria, así que lo que hay que comprar es que no caigan todos a la vez:
       cinco instrumentos distintos y un colchón del 20% para que dos
       posiciones en contra no toquen el límite. */
    cartera: { bots: 5, usarPct: 80 },
    /* CUATRO BOTS Y 70%. La que menos tolera un susto: pocas operaciones
       grandes significa que cada una pesa, y el colchón más ancho de las
       cuatro es lo que evita que una mala racha obligue a cerrar en el peor
       momento. */
    cartera: { bots: 4, usarPct: 70 },
    /* SEIS BOTS Y 90%. Acertar seguido significa ganar poco por acierto,
       así que el resultado sale de la cantidad: con pocos bots la ventaja por
       operación no alcanza a moverse del ruido. */
    cartera: { bots: 6, usarPct: 90 },
    /* CINCO BOTS Y 75%. La caída del conjunto no es la suma de las
       individuales —eso supondría que caen todas juntas— pero tampoco el
       promedio. Repartir en cinco instrumentos es lo que de verdad la baja, y
       por eso ésta es la receta donde más importa no concentrar. */
    cartera: { bots: 5, usarPct: 75 },
    cfg: {
      /* TREINTA MINUTOS SOLO EN CFD: en cripto, `aplicarReceta` la sube a
         una hora. En un perpetuo de Binance el costo por operación (0,04%
         por lado más deslizamiento) pesa entre el 98% y el 146% del rango de
         una vela de 30 minutos, medido sobre trece pares: ninguna candidata
         pasa la vara. A una hora sí salen. */
      timeframe: "30m", direction: "both", maxFilters: 1,
      anios: 4, maxCandidates: 1400,
      rrBuscado: [0.75, 1.0, 1.25, 1.5],
      minTrades: 60,
      // La frecuencia ORDENA, no filtra. Como filtro devolvía cero.
      fitness: "activity",
      critOn: { minPf: true, maxDd: true },
      minPf: 1.15, maxDd: 8,
    },
  },
  {
    id: "largo", ico: "pico",
    /* Lo contrario: acá no importa operar seguido sino que la ventaja se
       sostenga. Temporalidad alta, pocas operaciones grandes, y se le exige
       retorno sobre caída, que es lo que dice si valió la pena aguantarla. */
    cfg: {
      timeframe: "4h", direction: "both", maxFilters: 2,
      maxCandidates: 5000,
      rrBuscado: [1.5, 2.0, 2.5, 3.0],
      minTrades: 40,
      critOn: { minPf: true, minRetDd: true, minCagr: true },
      minPf: 1.25, minRetDd: 2.5, minCagrFactor: 1.6,
    },
  },
  {
    id: "aciertos", ico: "estrella",
    /* La que era imposible hasta ahora. El R:B bajo es TODO el truco: con 0,5
       la mediana de aciertos es 59,5% y quince de treinta pasan el 60%; con
       1:2 no lo pasa ninguna. Sin tocar la relación, este filtro no devuelve
       nada por más candidatas que se prueben. */
    cfg: {
      timeframe: "1h", direction: "both", maxFilters: 1,
      maxCandidates: 1200,
      rrBuscado: [0.5, 0.6, 0.75],
      minTrades: 40,
      critOn: { minPf: true, minWinRate: true },
      minPf: 1.1, minWinRate: 58,
    },
  },
  {
    id: "tranquilo", ico: "baja",
    /* Caída baja. Medido: el mínimo alcanzable ronda 2,5% en cualquier
       relación, y entre siete y diez de cada treinta quedan por debajo de 10%,
       así que pedir 10 es exigente pero no imposible. Se le suma retorno sobre
       caída para que no entren estrategias que caen poco porque no hacen nada. */
    cfg: {
      timeframe: "1h", direction: "both", maxFilters: 2,
      maxCandidates: 1200,
      rrBuscado: [0.75, 1.0, 1.5, 2.0],
      minTrades: 40,
      critOn: { minPf: true, maxDd: true, minRetDd: true },
      minPf: 1.15, maxDd: 10, minRetDd: 2,
    },
  },
  {
    id: "agresiva", ico: "sube",
    /* Para quien quiere más: se arriesga el triple por operación y se le
       exige más retorno anual, a cambio de aceptar caídas hondas. No se pide
       drawdown a propósito: pedirlo es pedir lo contrario. Tres robots y el
       90% de la cuenta, porque el que elige esto no quiere colchón. */
    cartera: { bots: 3, usarPct: 90 },
    cfg: {
      timeframe: "1h", direction: "both", maxFilters: 1,
      // 1400 y no 2000: el techo de espera son doce minutos y a una hora
      // cada candidata cuesta lo suyo (la prueba lo mide)
      maxCandidates: 1400,
      rrBuscado: [1.5, 2.0, 2.5, 3.0],
      minTrades: 40,
      riskPct: 3,
      critOn: { minPf: true, minCagr: true },
      minPf: 1.2, minCagrFactor: 2.5,
    },
  },
  {
    /* SÓLO EN CRIPTO, y con los ojos abiertos: en un perpetuo el costo por
       operación pesa casi lo mismo que el rango de una vela corta, así que
       la ventaja que sobrevive es chica. La receta existe para VER OPERAR
       al robot varias veces por día, no para ganar plata con ella, y la
       tarjeta lo dice. Necesita velas de un minuto: los perpetuos de fábrica
       vienen en una hora, y de una hora no salen velas de quince. */
    id: "scalping", ico: "seguir", mundo: "exchange", permiteCorto: true,
    /* DOS ROBOTS Y EL 30% DE LA CUENTA. Opera muchas veces por día y su
       ventaja es fina: se le da poco capital a propósito, y dos como máximo
       para no llenar la cuenta de operaciones correlacionadas. */
    cartera: { bots: 2, usarPct: 50 },
    cfg: {
      timeframe: "15m", direction: "both", maxFilters: 1,
      // 1800 y no 3000: a quince minutos cada candidata recorre muchas velas
      // y el techo de espera son doce minutos (la prueba lo mide)
      anios: 2, maxCandidates: 1600,
      rrBuscado: [0.75, 1.0],
      minTrades: 150,
      riskPct: 0.5,
      fitness: "activity",
      critOn: { minPf: true, minTradesMonth: true },
      minPf: 1.05, minTradesMonth: 40,
    },
  },
];

/* ═══════════════════════════════ COMPARTIR CON UN ENLACE ═════════════════
   La estrategia viaja congelada a botiquant.com y vuelve un código. Lo que
   se publica es lo que se ve en la ficha, y nada más: el documento se arma
   acá campo por campo. El secreto que vuelve es lo único que permite apagar
   el enlace, y se guarda en esta máquina. */
function enlacesGuardados() {
  try { return JSON.parse(localStorage.getItem("qf.enlaces") || "[]"); } catch (e) { return []; }
}
function guardarEnlace(e) {
  const lista = enlacesGuardados().filter(x => x.codigo !== e.codigo);
  lista.unshift(e);
  try { localStorage.setItem("qf.enlaces", JSON.stringify(lista.slice(0, 100))); } catch (err) { /* nada */ }
  /* Y EN EL ESPACIO DE TRABAJO, que es lo que sobrevive. El secreto es lo
     único que permite bajar una página ya publicada: guardarlo sólo en el
     navegador significaba que vaciarlo dejaba en internet una estrategia que
     su autor no podía retirar nunca más (3 de septiembre de 2026). */
  api.post("/api/enlaces", { codigo: e.codigo, secreto: e.secreto, url: e.url,
                             nombre: e.nombre, nivel: e.nivel || "" })
    .catch(() => { /* en el sitio público no existe; el navegador alcanza */ });
}

/* La lista completa: la del espacio de trabajo manda, y la del navegador
   suma los que se hayan compartido desde otra máquina contra este servidor. */
async function enlacesDeAmbos() {
  const local = enlacesGuardados();
  let delDisco = [];
  try { delDisco = await api.get("/api/enlaces"); } catch (e) { /* sólo escritorio */ }
  const porCodigo = new Map();
  for (const e of local) porCodigo.set(e.codigo, e);
  for (const e of delDisco) {
    const previo = porCodigo.get(e.codigo) || {};
    porCodigo.set(e.codigo, { ...previo, ...e, apagado: !!(e.apagado || previo.apagado) });
  }
  return [...porCodigo.values()].sort((a, b) => String(b.creado || "").localeCompare(String(a.creado || "")));
}

function documentoCompartible(row, ctx, res, nivel, autor) {
  const m = (res && res.metrics) || row.metrics || {};
  const g = (ctx && ctx.guardar) || {};
  const ds = S.datasets.find(d => d.id === (ctx ? ctx.dataset_id : S.sel.dataset_id));
  const muestra = (xs, n) => {
    xs = xs || [];
    if (xs.length <= n) return xs;
    const paso = (xs.length - 1) / (n - 1);
    return Array.from({ length: n }, (_, i) => xs[Math.round(i * paso)]);
  };
  const reglas = [...(row.spec.entry_long || []).map(c => `${t("insp.long_entry")}: ${condLabel(c)}`),
                  ...(row.spec.entry_short || []).map(c => `${t("insp.short_entry")}: ${condLabel(c)}`)];
  const v = (ctx && ctx.validacion) || null;
  return {
    nivel, autor: autor || "",
    nombre: row.name, instrumento: (ds ? ds.name : (ctx && ctx.dataset_name) || "").replace(/ M1.*/, ""),
    timeframe: (ctx ? ctx.timeframe : S.sel.timeframe) || "1h",
    direccion: (g.direction || ctx?.direction || S.cfg.direction || ""),
    bloques: row.blocks || "", reglas, salidas: salidasEnCastellano(row).replace(/&[a-z#0-9]+;/g, " "),
    /* Los costos de LA ESTRATEGIA, no del mercado elegido ahora. Con `||`
       un spread de 0 real se perdía y salía el del mercado en pantalla. */
    /* LOS COSTOS SON LOS DE LA ESTRATEGIA. Primero los del contexto con que
       se abrió (una guardada trae los suyos en `settings`), después los de la
       corrida, y recién al final los de la pantalla: una estrategia de
       perpetuos viajaba con el spread de MetaTrader (2 de septiembre). */
    costos: (() => {
      const st = (ctx && ctx.settings) || {};
      const elegir = (a, b, c) => +(a ?? b ?? c ?? 0);
      return { spread: elegir(st.spread, g.spread, S.cfg.spread),
               slippage: elegir(st.slippage, g.slippage, S.cfg.slippage),
               commission_pct: elegir(st.commission_pct, g.commission, S.cfg.commission),
               initial_capital: elegir(st.initial_capital, g.capital, S.cfg.capital) };
    })(),
    metricas: m,
    curva: muestra(res && res.equity, 240),
    fechas: muestra(res && res.timestamps, 240).map(x => String(x).slice(0, 10)),
    /* Con el PERÍODO y la CAÍDA PLAUSIBLE. Sin el primero, el "+7,9% anual"
       de la página no estaba fechado; sin la segunda, viajaba la caída que
       efectivamente pasó (7,8%) y no la que puede pasar (16,6%), que es la
       que la aplicación muestra al lado (3 de septiembre de 2026). */
    validacion: v && v.estado ? { estado: v.estado, tramos: v.tramos, tramos_ganadores: v.tramos_ganadores,
                                  eficiencia: v.eficiencia, retorno_fuera_pct: v.retorno_fuera_pct,
                                  periodo: v.periodo || null,
                                  detalle: v.detalle
                                    ? { tramos: v.detalle.tramos, mc: v.detalle.mc || v.mc || null }
                                    : (v.mc ? { mc: v.mc } : null) } : null,
    mundo: S.mundo, spec: row.spec,
    utc_offset: ds && ds.utc_offset != null ? ds.utc_offset : (S.cfg.brokerUtc || 0),
  };
}

/* ESCAPE CIERRA LA VENTANA DE ARRIBA, nunca la de atrás.

   Cada diálogo ataba su propio `keydown` y cerraba sin mirar: con la ficha de
   una estrategia abajo y Compartir arriba, Escape cerraba la ficha y dejaba
   Compartir flotando sobre otra pantalla, sin nadie escuchando. La regla vive
   acá una sola vez para que no se pierda en el próximo diálogo que se agregue
   (3 de septiembre de 2026). */
function cerrarConEscape(host, close) {
  document.addEventListener("keydown", function esckey(e) {
    if (e.key !== "Escape") return;
    if (!host.isConnected) { document.removeEventListener("keydown", esckey); return; }
    const capas = $$(".overlay");
    if (capas[capas.length - 1] !== host) return;   // hay algo más arriba
    close();
    document.removeEventListener("keydown", esckey);
  });
}

function abrirCompartirPortafolio(elegidas, r) {
  const m = r.metrics || {};
  const partes = (r.componentes || []).map((c, i) => ({
    nombre: c.name,
    cagr_pct: (c.metrics || {}).cagr_pct,
    riesgo_pct: (r.risk_contribution_pct || [])[i],
  }));
  const doc = {
    nivel: "mirar", tipo: "portafolio",
    nombre: elegidas.map(x => x.name).join(" + "),
    tipo_rotulo: "portafolio",
    instrumento: [...new Set(elegidas.map(x => String((x.meta || {}).dataset_name || "").split(" ")[0]))].join(" + "),
    timeframe: "", direccion: "", bloques: "", reglas: [], salidas: "",
    costos: {}, metricas: m,
    curva: (r.combined_equity || []).slice(0, 240),
    fechas: (r.timestamps || []).slice(0, 240).map(x => String(x).slice(0, 10)),
    validacion: null, mundo: S.mundo,
    portafolio: {
      nombres: elegidas.map(x => x.name),
      correlacion: m.avg_correlation,
      ventana: r.ventana || {},
      partes,
    },
  };
  abrirCompartir({ name: doc.nombre, spec: {}, blocks: "" }, null, null, doc);
}

function abrirCompartir(row, ctx, res, docFijo) {
  const host = document.createElement("div");
  host.className = "overlay";
  host.innerHTML = `<div class="sheet sheet-chica">
    <div class="sheet-head">
      <div><h2>${esc(t("comp.titulo"))}</h2><p>${esc(row.name)}</p></div>
      <button class="sheet-close" aria-label="${esc(t("ui.close"))}">${icono("cerrar")}</button>
    </div>
    <div class="comp-cuerpo">
      <p class="help-note">${esc(t("comp.sub"))}</p>
      <div class="comp-niveles" ${docFijo ? "hidden" : ""}>
        <label class="comp-nivel on"><input type="radio" name="comp-nivel" value="usar" checked>
          <b>${esc(t("comp.nivel_usar"))}</b><span>${esc(t("comp.nivel_usar_sub"))}</span></label>
        <label class="comp-nivel"><input type="radio" name="comp-nivel" value="mirar">
          <b>${esc(t("comp.nivel_mirar"))}</b><span>${esc(t("comp.nivel_mirar_sub"))}</span></label>
      </div>
      <label class="fld mt"><span>${esc(t("comp.autor"))}</span><input type="text" id="comp-autor" maxlength="40" placeholder="—"></label>
      <div class="controls mt"><button class="btn" id="comp-crear">${icono("seguir")} ${esc(t("comp.crear"))}</button></div>
      <div class="comp-listo" id="comp-listo" hidden>
        <b>${icono("tilde", "ico-sm")} ${esc(t("comp.listo"))}</b>
        <div class="comp-url"><input type="text" id="comp-url" readonly>
          <button class="btn small" id="comp-copiar">${esc(t("comp.copiar"))}</button>
          <a class="btn ghost small" id="comp-abrir" target="_blank" rel="noopener">${esc(t("comp.abrir"))}</a></div>
        <p class="help-note">${esc(t("comp.nota"))}</p>
      </div>
    </div>
  </div>`;
  document.body.appendChild(host);
  const close = () => host.remove();
  $(".sheet-close", host).onclick = close;
  host.onclick = (e) => { if (e.target === host) close(); };
  cerrarConEscape(host, close);
  $$(".comp-nivel input", host).forEach(r => r.onchange = () =>
    $$(".comp-nivel", host).forEach(l => l.classList.toggle("on", $("input", l).checked)));
  const crear = $("#comp-crear", host);
  crear.onclick = async () => {
    crear.disabled = true;
    crear.innerHTML = `<span class="spinner"></span>${esc(t("comp.creando"))}`;
    try {
      const nivel = ($(".comp-nivel input:checked", host) || {}).value || "usar";
      const doc = docFijo
        ? { ...docFijo, autor: $("#comp-autor", host).value.trim() }
        : documentoCompartible(row, ctx, res, nivel, $("#comp-autor", host).value.trim());
      const r = await api.post("/api/compartir/remoto", doc);
      guardarEnlace({ codigo: r.codigo, secreto: r.secreto, url: r.url, nombre: row.name,
                      nivel, creado: new Date().toISOString() });
      $("#comp-url", host).value = r.url;
      $("#comp-abrir", host).href = r.url;
      $("#comp-listo", host).hidden = false;
      /* SE PUEDE CREAR OTRO SIN CERRAR: quien comparte "para usar" suele
         querer también uno "para mirar", y había que cerrar y reabrir. */
      crear.disabled = false;
      crear.innerHTML = `${icono("seguir")} ${esc(t("comp.otro"))}`;
      $("#comp-copiar", host).onclick = async () => {
        try { await navigator.clipboard.writeText(r.url); } catch (e) { $("#comp-url", host).select(); document.execCommand("copy"); }
        $("#comp-copiar", host).textContent = t("comp.copiado");
      };
    } catch (e) {
      toast(e.message, "err");
      crear.disabled = false;
      crear.innerHTML = `${icono("seguir")} ${esc(t("comp.crear"))}`;
    }
  };
}

/* Lo último que devolvió la fusión navegador + espacio de trabajo. Se dibuja
   primero con lo que hay en el navegador —instantáneo— y se rellena cuando
   llega el disco, que puede tener enlaces que este navegador no vio. */
let ENLACES = null;

function misEnlacesHTML() {
  const lista = ENLACES || enlacesGuardados();
  return `<section class="card mt" id="mis-enlaces">
    <h2>${esc(t("comp.mis_enlaces"))} <span class="hint">${esc(t("comp.mis_enlaces_sub"))}</span></h2>
    ${lista.length ? `<div class="enlaces">${lista.map(e => `
      <div class="enlace ${e.apagado ? "apagado" : ""}" data-codigo="${esc(e.codigo)}">
        <div><b>${esc(e.nombre)}</b> <span class="tag-nivel">${esc(t(e.nivel === "mirar" ? "comp.nivel_mirar" : "comp.nivel_usar"))}</span>
          <span class="muted">${esc(e.url)} · ${esc(String(e.creado).slice(0, 10))}</span></div>
        <div class="controls">
          ${e.apagado ? `<span class="muted">${esc(t("comp.apagado"))}</span>` : `
          <button class="btn ghost small" data-enlace-copiar="${esc(e.url)}">${esc(t("comp.copiar"))}</button>
          <button class="btn ghost small" data-enlace-apagar="${esc(e.codigo)}">${esc(t("comp.apagar"))}</button>`}
        </div>
      </div>`).join("")}</div>` : `<p class="help-note">${esc(t("comp.sin_enlaces"))}</p>`}
  </section>`;
}
function atarMisEnlaces(main) {
  /* Y se vuelve a dibujar con lo que guarda el equipo: un enlace compartido
     desde otro navegador, o desde este mismo antes de vaciarlo, sigue estando
     y todavía se puede apagar. */
  enlacesDeAmbos().then(lista => {
    const iguales = JSON.stringify(lista) === JSON.stringify(ENLACES);
    ENLACES = lista;
    const caja = $("#mis-enlaces", main);
    if (caja && !iguales && caja.isConnected) {
      caja.outerHTML = misEnlacesHTML();
      atarMisEnlaces(main);
    }
  });

  $$("[data-enlace-copiar]", main).forEach(b => b.onclick = async () => {
    try { await navigator.clipboard.writeText(b.dataset.enlaceCopiar); } catch (e) { /* nada */ }
    b.textContent = t("comp.copiado");
  });
  $$("[data-enlace-apagar]", main).forEach(b => b.onclick = async () => {
    const e = (ENLACES || enlacesGuardados()).find(x => x.codigo === b.dataset.enlaceApagar);
    if (!e) return;
    b.disabled = true;
    try {
      await api.post("/api/compartir/apagar", { codigo: e.codigo, secreto: e.secreto });
      guardarEnlace({ ...e, apagado: true });
      api.post(`/api/enlaces/${e.codigo}/apagado`, {}).catch(() => { /* sólo escritorio */ });
      ENLACES = null;
      toast(t("comp.apagado"), "ok");
      navigate("consejos");
    } catch (err) { toast(err.message, "err"); b.disabled = false; }
  });
}

/* ═══════════════════════════════ NÚMEROS QUE CUENTAN ═════════════════════
   Las cifras grandes suben desde cero en 400 ms al aparecer. Cada una lleva
   su valor final y su formato en atributos, así la animación produce el
   mismo texto que produciría sin animación. Con "reducir movimiento" se
   escribe el final directo. */
const FORMATOS_CIFRA = {
  pct: v => fmtPct(v), dd: v => `${fmtNum(v, 1)}%`, n: v => fmtNum(v),
  int: v => fmtInt(Math.round(v)), usdt: v => `${fmtNum(v, 2)} USDT`,
  usdt_signo: v => `${v > 0 ? "+" : ""}${fmtNum(v, 2)} USDT`,
};
function animarCifras(root) {
  const reducido = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  $$("[data-cifra]", root).forEach(el => {
    if (el.dataset.animada) return;
    el.dataset.animada = "1";
    const fin = parseFloat(el.dataset.cifra);
    const fmt = FORMATOS_CIFRA[el.dataset.formato] || (v => String(v));
    if (!isFinite(fin) || reducido) { el.textContent = fmt(fin); return; }
    /* EL NÚMERO BUENO PRIMERO, LA ANIMACIÓN DESPUÉS. `requestAnimationFrame`
       no corre en una pestaña oculta ni en una ventana en segundo plano, así
       que la cifra se quedaba en el "0" del marcador para siempre: "Saldo 0 ·
       Resultado neto 0 · Posiciones abiertas 0" con la frase de abajo diciendo
       los valores reales, y "Arriesga ≈ 0.00 USDT" en la tarjeta de cada
       robot. Escribiéndolo antes, lo peor que puede pasar es que no se anime
       (3 de septiembre de 2026). */
    el.textContent = fmt(fin);
    const t0 = performance.now(), dur = 420;
    const paso = (ahora) => {
      const k = Math.min(1, (ahora - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3);                // sale rápido, frena al final
      el.textContent = fmt(fin * e);
      if (k < 1) requestAnimationFrame(paso); else el.textContent = fmt(fin);
    };
    requestAnimationFrame(paso);
  });
}

/* ═══════════════════════════════ LOS PRIMEROS TRES PASOS ═════════════════
   Tres tildes en la barra lateral —buscaste, probaste, encendiste— que se
   van marcando solas y desaparecen cuando están los tres. La primera vez
   decide si el usuario vuelve, y esto le dice qué sigue sin explicarle nada. */
const PRIMEROS = ["buscaste", "probaste", "encendiste"];
const PP_ROTULO = () => ({ buscaste: t("pp.buscaste"), probaste: t("pp.probaste"),
                           encendiste: t(S.mundo === "metatrader" ? "pp.exportaste" : "pp.encendiste") });
function primerPaso(cual) {
  try { localStorage.setItem("qf.pp." + cual, "1"); } catch (e) { /* nada */ }
  marcarPrimerosPasos();
}
function marcarPrimerosPasos() {
  const caja = $("#primeros-pasos");
  if (!caja) return;
  let hechos = {};
  try { PRIMEROS.forEach(p => { hechos[p] = localStorage.getItem("qf.pp." + p) === "1"; }); } catch (e) { hechos = {}; }
  const todos = PRIMEROS.every(p => hechos[p]);
  caja.hidden = todos || S.mundo === "metatrader" && false;
  if (todos) return;
  caja.innerHTML = `<b>${esc(t("pp.titulo"))}</b>
    ${PRIMEROS.map(p => `<span class="pp ${hechos[p] ? "hecho" : ""}">${icono(hechos[p] ? "tilde" : "info", "ico-sm")} ${esc(PP_ROTULO()[p])}</span>`).join("")}`;
}

/* ═══════════════════════════════ UNA EXPLICACIÓN QUE SE VE PASAR ══════════
   Un recorrido de pasos con un punto que viaja de uno al siguiente, y un
   texto que cambia con cada paso. Se aprieta "ver cómo funciona" y la
   aplicación se explica sola: para el piloto automático y para la entrada.

   Un diagrama quieto se lee a medias; el mismo diagrama con un punto que
   avanza se sigue entero, porque la vista va a donde está pasando algo. Con
   "reducir movimiento" el punto no se mueve y los pasos se muestran todos
   a la vez, como una lista. */
const EXPLICACIONES = {};          // estado por id: paso actual, andando

function explicacionHTML(id, pasos, opciones = {}) {
  const st = EXPLICACIONES[id] || (EXPLICACIONES[id] = { paso: 0, andando: false, abierta: !!opciones.abierta });
  const ciclico = !!opciones.ciclico;
  return `
  <div class="expl ${st.abierta ? "abierta" : ""} ${ciclico ? "ciclica" : ""}" id="expl-${esc(id)}" data-expl="${esc(id)}">
    ${opciones.fija ? "" : `<button class="linkbtn expl-abrir" data-expl-abrir>${icono("seguir", "ico-sm")} ${esc(t("expl.ver"))}</button>`}
    <div class="expl-cuerpo">
      <div class="expl-flujo">
        ${pasos.map((p, i) => `
        <button class="expl-nodo ${i === st.paso ? "on" : ""} ${i < st.paso ? "hecho" : ""}" data-expl-ir="${i}">
          <span class="expl-ico">${icono(p.ico, "ico-sm")}</span>
          <b>${esc(t(p.titulo))}</b>
        </button>${i < pasos.length - 1 || ciclico ? `<i class="expl-lin ${i < st.paso ? "hecho" : ""}"></i>` : ""}`).join("")}
        <span class="expl-punto" aria-hidden="true"></span>
      </div>
      <div class="expl-texto" aria-live="polite">
        <b>${esc(t(pasos[st.paso].titulo))}</b>
        <p>${t(pasos[st.paso].texto, pasos[st.paso].params || {})}</p>
      </div>
      ${opciones.panel ? `<div class="expl-panel">${opciones.panel(st.paso)}</div>` : ""}
      <div class="expl-pie">
        <button class="btn small" data-expl-play>${st.andando ? esc(t("expl.pausar")) : esc(t("expl.reproducir"))}</button>
        <span class="expl-prog">${st.paso + 1} / ${pasos.length}</span>
      </div>
    </div>
  </div>`;
}

function atarExplicacion(root, id, pasos, opciones = {}) {
  const caja = $(`#expl-${id}`, root);
  if (!caja) return;
  const st = EXPLICACIONES[id];
  const sinMovimiento = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const punto = $(".expl-punto", caja);

  const moverPunto = () => {
    const nodo = $$(".expl-nodo", caja)[st.paso];
    if (!nodo || !punto) return;
    const flujo = $(".expl-flujo", caja);
    const r = nodo.getBoundingClientRect(), f = flujo.getBoundingClientRect();
    punto.style.transform = `translate(${r.left - f.left + r.width / 2 - 6}px, ${r.top - f.top - 8}px)`;
  };
  const pintar = () => {
    $$(".expl-nodo", caja).forEach((n, i) => {
      n.classList.toggle("on", i === st.paso);
      n.classList.toggle("hecho", i < st.paso);
    });
    $$(".expl-lin", caja).forEach((l, i) => l.classList.toggle("hecho", i < st.paso));
    const texto = $(".expl-texto", caja);
    texto.classList.remove("cambia"); void texto.offsetWidth; texto.classList.add("cambia");
    $("b", texto).textContent = t(pasos[st.paso].titulo);
    $("p", texto).innerHTML = t(pasos[st.paso].texto, pasos[st.paso].params || {});
    $(".expl-prog", caja).textContent = `${st.paso + 1} / ${pasos.length}`;
    $("[data-expl-play]", caja).textContent = st.andando ? t("expl.pausar") : t("expl.reproducir");
    /* EL PANEL DEL PASO: donde el recorrido también se configura. Se
       redibuja con cada paso y quien lo dibuja vuelve a atar sus campos. */
    const panel = $(".expl-panel", caja);
    if (panel && opciones.panel) { panel.innerHTML = opciones.panel(st.paso); if (opciones.alPintar) opciones.alPintar(caja, st.paso); }
    moverPunto();
  };
  const parar = () => { st.andando = false; if (st.timer) clearInterval(st.timer); st.timer = null; pintar(); };
  const andar = () => {
    st.andando = true;
    if (st.timer) clearInterval(st.timer);
    st.timer = setInterval(() => {
      if (!document.body.contains(caja)) { clearInterval(st.timer); st.timer = null; st.andando = false; return; }
      const ultimo = st.paso >= pasos.length - 1;
      if (ultimo && !opciones.ciclico) { parar(); return; }
      st.paso = ultimo ? 0 : st.paso + 1;
      pintar();
    }, sinMovimiento ? 4000 : 2600);
    pintar();
  };

  const abrir = $("[data-expl-abrir]", caja);
  if (abrir) abrir.onclick = () => {
    st.abierta = !st.abierta;
    caja.classList.toggle("abierta", st.abierta);
    if (st.abierta) { st.paso = 0; andar(); } else parar();
  };
  $("[data-expl-play]", caja).onclick = () => (st.andando ? parar() : andar());
  $$("[data-expl-ir]", caja).forEach(n => n.onclick = () => { st.paso = +n.dataset.explIr; parar(); });
  if (st.abierta) { requestAnimationFrame(moverPunto); if (st.andando) andar(); }
  if (opciones.alPintar) opciones.alPintar(caja, st.paso);
}

/* ═══════════════════ EL PILOTO SE CONFIGURA SOBRE SU PROPIO DIBUJO ════════
   Cada nodo del recorrido abre sus parámetros: cada cuántas horas busca,
   cuántas candidatas, sobre qué perpetuos, cuántas prueba, cuántos robots,
   cuándo retira. Es el mismo diagrama que lo explica, así que quien lo
   entiende ya sabe dónde tocar. Es el "workflow" de la aplicación: un solo
   recorrido fijo, editable nodo por nodo, sin lienzo de nodos libres. */
let PILOTO_PARAMS = null;   // copia editable de c.params, hasta guardar

/* Claves ENTERAS, por el examen de textos: no se arman pegando el prefijo. */
const PIL_ROTULO = () => ({
  minar_cada_horas: t("pil.f_minar_cada_horas"), candidatas_por_vuelta: t("pil.f_candidatas_por_vuelta"),
  reservar_pct: t("pil.f_reservar_pct"), validar_por_vuelta: t("pil.f_validar_por_vuelta"),
  max_en_practica: t("pil.f_max_en_practica"), max_por_instrumento: t("pil.f_max_por_instrumento"),
  vueltas_en_naranja: t("pil.f_vueltas_en_naranja"),
});

function panelPiloto(i) {
  const p = PILOTO_PARAMS || {};
  const num = (clave, min, max, paso = 1) => `
    <label class="fld"><span>${esc(PIL_ROTULO()[clave])}</span>
      <input type="number" data-pil="${clave}" value="${esc(String(p[clave] ?? ""))}" min="${min}" max="${max}" step="${paso}"></label>`;
  const perps = (S.datasets || []).filter(d => mundoDeDataset(d.name) === "exchange");
  const elegidos = new Set(p.instrumentos || []);
  const paneles = [
    `<div class="pil-campos">${num("minar_cada_horas", 1, 168)}${num("candidatas_por_vuelta", 100, 50000, 100)}${num("reservar_pct", 0, 60)}</div>
     <div class="pil-instr"><span class="fld-rot">${esc(t("pil.f_instrumentos"))}</span>
       <div class="pil-chips">${perps.map(d => `<label class="pil-chip ${elegidos.has(d.id) ? "on" : ""}">
         <input type="checkbox" data-pil-instr="${esc(d.id)}" ${elegidos.has(d.id) ? "checked" : ""}>${esc(d.name.replace(/ (H1|M1).*/, ""))}</label>`).join("")}</div>
       <p class="help-note">${esc(t("pil.f_instrumentos_nota"))}</p></div>`,
    `<div class="pil-campos">${num("validar_por_vuelta", 1, 50)}</div>
     <p class="help-note">${esc(t("pil.f_validar_nota"))}</p>`,
    `<div class="pil-campos">${num("max_en_practica", 1, 20)}${num("max_por_instrumento", 1, 10)}</div>
     <p class="help-note">${esc(t("pil.f_practica_nota"))}</p>`,
    `<div class="pil-campos">${num("vueltas_en_naranja", 1, 50)}</div>
     <p class="help-note">${esc(t("pil.f_vigila_nota"))}</p>`,
    `<label class="pil-check"><input type="checkbox" data-pil="retirar_solo" ${p.retirar_solo ? "checked" : ""}> ${esc(t("pil.f_retirar_solo"))}</label>
     <p class="help-note">${esc(t("pil.f_retirar_nota"))}</p>`,
  ];
  return `<div class="pil-panel">${paneles[i] || ""}
    <div class="controls mt"><button class="btn small" data-pil-guardar>${esc(t("pil.guardar"))}</button>
      <span class="help-note" data-pil-estado></span></div></div>`;
}

function atarPanelPiloto(caja) {
  const p = PILOTO_PARAMS;
  if (!p) return;
  $$("[data-pil]", caja).forEach(el => el.onchange = () => {
    if (el.type === "checkbox") p[el.dataset.pil] = el.checked;
    else p[el.dataset.pil] = +el.value;
  });
  $$("[data-pil-instr]", caja).forEach(cb => cb.onchange = () => {
    const set = new Set(p.instrumentos || []);
    if (cb.checked) set.add(cb.dataset.pilInstr); else set.delete(cb.dataset.pilInstr);
    p.instrumentos = [...set];
    cb.closest(".pil-chip").classList.toggle("on", cb.checked);
  });
  const g = $("[data-pil-guardar]", caja);
  if (g) g.onclick = async () => {
    g.disabled = true;
    try {
      /* Manda el juego ENTERO: el servidor reemplaza todos los parámetros,
         y mandar uno solo devolvería los demás a sus valores por defecto. */
      const r = await api.post("/api/ciclo/params", p);
      PILOTO_PARAMS = { ...(r.params || p) };
      toast(t("pil.guardado"), "ok");
      const est = $("[data-pil-estado]", caja); if (est) est.textContent = t("pil.guardado");
    } catch (e) {
       toast(e.message, "err"); }
    g.disabled = false;
  };
}

/* Los pasos del piloto automático: lo que hace, en el orden en que lo hace. */
const PASOS_PILOTO = () => [
  { ico: "pico",   titulo: "expl.pil1",  texto: "expl.pil1_t" },
  { ico: "tilde",  titulo: "expl.pil2",  texto: "expl.pil2_t" },
  { ico: "seguir", titulo: "expl.pil3",  texto: "expl.pil3_t" },
  { ico: "sube",   titulo: "expl.pil4",  texto: "expl.pil4_t" },
  { ico: "baja",   titulo: "expl.pil5",  texto: "expl.pil5_t" },
];

/* Los pasos de una búsqueda: lo que le pasa a cada candidata. Reusa los
   textos que ya explicaban esto en cuatro columnas quietas. */
const PASOS_MINAR = () => [
  { ico: "idea",   titulo: "idle.s1", texto: "idle.s1_sub" },
  { ico: "pico",   titulo: "idle.s2", texto: "idle.s2_sub" },
  { ico: "tilde",  titulo: "idle.s3", texto: "idle.s3_sub" },
  { ico: "seguir", titulo: "idle.s4", texto: "idle.s4_sub", params: { goal: S.cfg.goal } },
];

/* Los pasos de la prueba: cómo se corta la historia y qué se le pregunta. */
const PASOS_PRUEBA = () => [
  { ico: "base",   titulo: "expl.pr1", texto: "expl.pr1_t" },
  { ico: "idea",   titulo: "expl.pr2", texto: "expl.pr2_t" },
  { ico: "tilde",  titulo: "expl.pr3", texto: "expl.pr3_t" },
  { ico: "baja",   titulo: "expl.pr4", texto: "expl.pr4_t" },
  { ico: "estrella", titulo: "expl.pr5", texto: "expl.pr5_t" },
];

/* Los pasos de la entrada: el camino entero de una estrategia. */
const PASOS_ENTRADA = () => [
  { ico: "diana",    titulo: "wel.s1",   texto: "expl.ent1_t" },
  { ico: "tilde",    titulo: "expl.ent2", texto: "expl.ent2_t" },
  { ico: "marcador", titulo: "wel.s2",   texto: "expl.ent3_t" },
  { ico: "seguir",   titulo: "wel.s3",   texto: "expl.ent4_t" },
];

/* Los minutos de cada temporalidad, para saber qué histórico puede darla:
   de velas de una hora no salen velas de quince. */
const MINUTOS_DE_TF = { "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440 };

/* Acorta el período a los últimos N años.

   Es la quinta cosa que una receta configura, y hace falta por dos motivos que
   apuntan al mismo lado. Uno es de sentido: un desafío de cuenta fondeada se
   juega con el comportamiento reciente, no con lo que el mercado hacía hace
   diez años. El otro es aritmético: la mitad de velas es la mitad de costo por
   candidata, así que en el mismo tiempo de espera entran el doble de
   candidatas — y en una búsqueda que encuentra poco, eso es la diferencia
   entre traer algo y no traer nada. */
function acortarVentana(anios) {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  const b = datasetBounds(ds);
  if (!b.hi) return;
  const fin = new Date(b.hi + "T00:00:00Z");
  const desde = new Date(Date.UTC(fin.getUTCFullYear() - anios,
                                  fin.getUTCMonth(), fin.getUTCDate()))
    .toISOString().slice(0, 10);
  S.sel.dateFrom = desde > b.lo ? desde : b.lo;
  S.sel.dateTo = b.hi;
  // elegido por la receta: que la ventana automática no lo pise después
  S.sel.rangoPropio = true;
}

/* Aplica una receta y deja al usuario en la pantalla de búsqueda.

   Apaga TODOS los criterios antes de prender los suyos. Si no, los que había
   tildados de antes se suman a los de la receta y la búsqueda termina pidiendo
   una mezcla que nadie eligió — que es la forma más rápida de que una
   categoría no devuelva nada y parezca rota. */
function aplicarReceta(r) {
  const c = S.cfg;
  c.critOn = {};
  for (const [k, v] of Object.entries(r.cfg)) {
    if (k === "timeframe") {
      /* EN CRIPTO NADA POR DEBAJO DE UNA HORA. Medido sobre trece perpetuos
         de Binance: a 30 minutos el costo por operación pesa entre el 98% y
         el 146% del rango de la vela y ninguna candidata pasa la vara. Una
         receta que ahí pidiera 30 minutos prometería una búsqueda vacía. */
      const cripto = S.mundo === "exchange";
      const corta = ["30m", "15m", "5m", "1m"].includes(v);
      let tf = (cripto && corta && !r.permiteCorto) ? "1h" : v;
      /* Y EL HISTÓRICO TIENE QUE PODER DARLA. Los perpetuos de fábrica son
         de una hora: pedirles quince minutos dejaba la búsqueda pidiendo lo
         imposible. Se queda en lo que el histórico da y se dice qué bajar. */
      const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
      const minsDs = MINUTOS_DE_TF[ds?.timeframe] || 1;
      if ((MINUTOS_DE_TF[tf] || 60) < minsDs) {
        tf = ds.timeframe;
        setTimeout(() => toast(t("rec.necesita_m1", { ds: ds.name }), "err"), 600);
      }
      S.sel.timeframe = tf;
      continue;
    }
    if (k === "critOn") { c.critOn = { ...v }; continue; }
    if (k === "anios") { acortarVentana(v); continue; }
    /* El rendimiento anual pedido, como MÚLTIPLO del piso del instrumento y no
       como número fijo.

       Encontrado verificando las categorías en los cuatro mercados: "Aguantarla
       años" pedía 5% anual y en EURUSD devolvía cero de cinco mil candidatas.
       No es que buscara mal — el techo medido de EURUSD es 4,05% anual, así que
       le estaba pidiendo por encima de lo que ese mercado da. En oro y Bitcoin,
       donde el techo pasa el 20%, las mismas cinco unidades son un pedido
       cómodo y salieron diez de diez.

       Un número fijo no puede significar lo mismo en mercados cuyos techos van
       de 4% a 22%. El piso por instrumento ya vive en el catálogo por esta
       misma razón, así que la receta se apoya en él. */
    if (k === "minCagrFactor") {
      const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
      c.minCagr = Math.round((ds?.min_cagr ?? 3) * v * 10) / 10;
      continue;
    }
    c[k] = v;
  }
  S.recetaPuesta = r.id;
  saveCfg();
  navigate("mining", "buscar").then(() =>
    toast(t("rec.puesta", { nombre: t(`rec.${r.id}`) }), "ok"));
}

const CRIT_DEF = [
  { key: "minPf",          metrica: "m.pf",           cmp: "≥", step: 0.05, min: 0, def: 1.0,  unit: "" },
  { key: "minRetDd",       metrica: "m.retdd",        cmp: "≥", step: 0.5,  min: 0, def: 1.5,  unit: "" },
  { key: "maxDd",          metrica: "m.dd",           cmp: "≤", step: 1,    min: 4, def: 25,   unit: "%" },
  { key: "minWinRate",     metrica: "m.winrate",      cmp: "≥", step: 1,    min: 0, def: 50,   unit: "%" },
  { key: "minTradesMonth", metrica: "m.trades_month", cmp: "≥", step: 1,    min: 0, def: 4,    unit: "" },
  /* Por semana además de por mes. Quien está pasando un desafío de fondeo
     tiene fecha de vencimiento: "cuatro por mes" puede ser cuatro días
     seguidos y después nada, y eso no le sirve. Por semana es la unidad en
     la que esa persona piensa el problema. */
  { key: "minTradesWeek",  metrica: "m.trades_week",  cmp: "≥", step: 0.5,  min: 0, def: 2,    unit: "" },
  { key: "minCagr",        metrica: "m.cagr",         cmp: "≥", step: 1,    min: 0, def: 5,    unit: "%" },
  { key: "minSharpe",      metrica: "m.sharpe",       cmp: "≥", step: 0.1,  min: 0, def: 0.30, unit: "" },
  { key: "minExposure",    metrica: "m.exposure",     cmp: "≥", step: 1,    min: 0, def: 5,    unit: "%" },
];
const CRITERIA = () => CRIT_DEF.map(c => ({
  ...c, label: `${t(c.metrica)} ${c.cmp}`, ayuda: t(`crit.${c.key}`),
}));
const CRIT_BY_KEY = () => Object.fromEntries(CRITERIA().map(c => [c.key, c]));

/* Lo que cada filtro quiere decir, en castellano. Las claves van enteras
   para que el examen de textos pueda seguirlas. */
const LLANO = () => ({
  minPf: t("llano.minPf"), minRetDd: t("llano.minRetDd"), maxDd: t("llano.maxDd"),
  minWinRate: t("llano.minWinRate"), minTradesMonth: t("llano.minTradesMonth"),
  minTradesWeek: t("llano.minTradesWeek"), minCagr: t("llano.minCagr"),
  minSharpe: t("llano.minSharpe"), minExposure: t("llano.minExposure"),
});

// un valor guardado por debajo del piso del criterio (ej. max DD 1%) no dejaría
// pasar nada: vuelve al recomendado
for (const cr of CRITERIA()) {
  if (!Number.isFinite(+S.cfg[cr.key]) || +S.cfg[cr.key] < cr.min) S.cfg[cr.key] = cr.def;
}

/* -------------------------------------------------------------------- api */
const api = {
  async req(method, url, body) {
    // El idioma viaja en cada pedido para que los errores del servidor
    // vuelvan en el mismo idioma que la pantalla. Sin esto, la aplicación en
    // inglés mostraba mensajes en español apenas algo fallaba.
    const opts = { method, headers: { "X-Idioma": idioma() } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(url, opts);
    if (!r.ok) {
      let msg = `${r.status}`;
      try {
        const d = (await r.json()).detail;
        /* El detalle puede ser un objeto (las compuertas del bot mandan
           {mensaje, puertas}); mostrarlo crudo daba "[object Object]". */
        msg = (d && typeof d === "object") ? (d.mensaje || d.detail || JSON.stringify(d)) : (d || msg);
      } catch (e) {
       /* noop */ }
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

async function runJob(url, payload, onTick, onJobId, reanudar = null) {
  /* `reanudar` es el id de un trabajo que ya corre en el servidor: no se
     manda nada, sólo se lo vuelve a seguir. Es lo que permite que recargar
     la página no pierda de vista una búsqueda en curso. */
  const job_id = reanudar || (await api.post(url, payload)).job_id;
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
/* El formateo sigue al IDIOMA de la aplicación, no al del navegador. Con
   `undefined` la misma pantalla mezclaba criterios: los enteros salían
   "35.500" y el dinero "35,500" según dónde estuviera cada usuario. Atarlo al
   idioma elegido mantiene la coherencia y además hace lo correcto en los dos:
   en inglés 35,500 con coma, en español 35.500 con punto.

   Sin abreviar a "k" ni a "M": son cifras de dinero y redondear $35.500 a
   "$35k" esconde justo el detalle que se está mirando. */
const fmtMoney = (v) => (v < 0 ? "-$" : "$") +
  Math.abs(+v || 0).toLocaleString(localeNum(), { maximumFractionDigits: 0 });
const fmtNum = (v, d = 2) => (+v).toFixed(d);
const fmtInt = (v) => (+v || 0).toLocaleString(localeNum());

/* Las filas que el cargador tuvo que tirar, en castellano y con el motivo.
   Se muestra aparte del "listo" para que no se lea como parte del éxito. */
function avisarDescartes(meta) {
  const d = (meta || {}).descartadas;
  if (!d) return;
  /* Las claves se nombran enteras a propósito: armarlas con "csv." + motivo
     las vuelve invisibles para la prueba que verifica que ninguna falte, y
     una clave que falta se dibuja cruda en la pantalla. */
  const COMO = {
    sin_precio: () => t("csv.sin_precio", { n: d.sin_precio }),
    precio_invalido: () => t("csv.precio_invalido", { n: d.precio_invalido }),
    vela_incoherente: () => t("csv.vela_incoherente", { n: d.vela_incoherente }),
    repetida: () => t("csv.repetida", { n: d.repetida }),
  };
  const partes = Object.keys(d).filter(k => COMO[k]).map(k => COMO[k]());
  toast(t("csv.descartadas", { total: Object.values(d).reduce((a, b) => a + b, 0),
                               leidas: fmtInt(meta.filas_leidas || 0),
                               detalle: partes.join(", ") }), "err");
}

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
/* EL LOGO DE CADA CRIPTO. Íconos del set abierto cryptocurrency-icons
   (licencia CC0, dominio público) en ui/iconos/cripto; SUI y ARB no están
   en el set y son marcas simples dibujadas acá. Se busca por la moneda del
   par: "BTCUSDT H1" → btc. Lo que no tiene logo sigue con sus iniciales. */
const LOGOS_CRIPTO = new Set(["btc", "eth", "bnb", "sol", "xrp", "doge", "ada",
                              "link", "sui", "arb", "uni", "xmr", "zec"]);
/* Y LOS DE METATRADER 5: banderas (flag-icons, licencia MIT) para índices,
   pares y bonos; marcas propias para oro, petróleo y gas. */
const LOGOS_CFD = { sp500: "us", eurusd: "eu", xauusd: "xau", bund: "de", wti: "wti", gas: "gas", btcusd: "btc" };
function logoCripto(nombre, cls = "logo-cripto") {
  const token = String(nombre || "").trim().split(/\s+/)[0].toLowerCase();
  const cfd = LOGOS_CFD[token];
  if (cfd) {
    const carpeta = cfd === "btc" ? "cripto" : "cfd";
    return `<img class="${cls}" src="/static/iconos/${carpeta}/${cfd}.svg" alt="" width="32" height="32">`;
  }
  const m = token.match(/^([a-z]+?)(usdt|usd|busd|usdc)$/);
  const moneda = m ? m[1] : token;
  if (!LOGOS_CRIPTO.has(moneda)) return "";
  return `<img class="${cls}" src="/static/iconos/cripto/${moneda}.svg" alt="" width="32" height="32">`;
}

function ctxPill() {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  if (!ds) return "";
  const initials = (ds.name.match(/[A-Za-z0-9]+/g) || ["?"])[0].slice(0, 3).toUpperCase();
  const logo = logoCripto(ds.name, "ctx-logo");
  return `<div class="ctx-pill">
    <span class="ctx-ic ${logo ? "con-logo" : ""}">${logo || esc(initials)}</span>
    <div><b>${esc(ds.name)}</b><br>
      <span>${fmtInt(ds.rows)} ${esc(t("ui.bars"))} · ${esc(String(ds.start).slice(0, 10))} → ${esc(String(ds.end).slice(0, 10))}</span>
    </div></div>`;
}

function saveCfg() {
  localStorage.setItem("qf.cfg", JSON.stringify(S.cfg));
  /* Y UNA COPIA POR MERCADO. Alguien que ajusta a mano bloques, riesgo y
     filtros para ETHUSDT y después mira otro mercado perdía diez minutos de
     trabajo al volver (2 de septiembre). Cada mercado recuerda lo suyo y se
     restituye al elegirlo; quien nunca lo tocó no nota nada. */
  try {
    if (S.sel.dataset_id) {
      const porMercado = JSON.parse(localStorage.getItem("qf.cfg_mercado") || "{}");
      /* NO PISAR LA RECETA CON NADA. Al recargar, el lector de campos guarda
         antes de que se restituya qué receta estaba puesta, y escribía
         `receta: null` encima de "dormir tranquilo": la marca se perdía en la
         primera recarga y nadie sabía por qué la búsqueda pedía lo que pedía
         (3 de septiembre de 2026). Sin receta en memoria, se conserva la que
         este mercado ya tenía. */
      const previa = (porMercado[S.sel.dataset_id] || {}).receta || null;
      porMercado[S.sel.dataset_id] = { cfg: S.cfg, timeframe: S.sel.timeframe,
                                       receta: S.recetaPuesta || previa };
      localStorage.setItem("qf.cfg_mercado", JSON.stringify(porMercado));
    }
  } catch (e) { /* modo privado */ }
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
  minTradesMonth: "min_trades_month", minTradesWeek: "min_trades_week",
  //: "Ganancia total" ya no se ofrece —el total depende de cuántos años tenga
  //: el histórico, así que el mismo número exige cosas distintas según el
  //: instrumento— pero la clave queda para leer las corridas ya archivadas.
  minNet: "min_net_pct",
};

/* El camino inverso: de la clave que manda el minero al nombre que ve el
   usuario, en su idioma. El servidor manda claves justamente porque no puede
   saber en qué idioma está mirando cada quien. */
const CRIT_POR_CAMPO = Object.fromEntries(
  Object.entries(CRIT_FIELD).map(([k, campo]) => [campo, k]));

function nombreDeRechazo(clave) {
  if (clave === "min_trades") return t("busca.too_few_trades");
  const k = CRIT_POR_CAMPO[clave];
  const cr = k ? CRIT_BY_KEY()[k] : null;
  // una clave desconocida —una corrida archivada por una versión anterior—
  // se muestra tal cual en vez de desaparecer de la lista de rechazos
  return cr ? cr.label.replace(/ [≥≤]$/, "") : clave;
}
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
  const partes = [t("vara.min_trades", { n: fmtInt(snap.min_trades ?? 0) })];
  for (const cr of CRITERIA()) {
    const v = a[CRIT_FIELD[cr.key]];
    if (v == null) continue;
    partes.push(`${esc(cr.label.replace(/ [≥≤]$/, ""))} ${cr.label.slice(-1)}
                 <b>${fmtNum(v, cr.step < 1 ? 2 : 0)}${cr.unit}</b>`);
  }
  /* LOS BLOQUES QUE NO SE PUDIERON USAR, dichos acá y no callados.

     El funding lo cobran los perpetuos; un CFD no lo tiene. Pedirlo igual es
     legítimo —"todos los bloques" es una elección razonable— pero si se
     descartan sin avisar, la corrida sale con menos herramientas de las que
     uno cree que pidió y no hay forma de notarlo. */
  const fuera = snap.sin_funding || [];
  const nota = fuera.length
    ? `<div class="vara floja">${esc(t("vara.sin_funding", { n: fuera.length }))}</div>`
    : "";

  if (partes.length > 1) {
    return `<div class="vara">${t("vara.required")}: ${partes.join(" · ")}</div>${nota}`;
  }
  return `<div class="vara floja">${t("vara.none", { unico: partes[0] })}</div>${nota}`;
}

function acceptPayload() {
  const out = {};
  for (const cr of CRITERIA()) {
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

const SCORE_TIERS = () => [
  { min: 70, label: t("tier.solid"),      cls: "s-top" },
  { min: 50, label: t("tier.promising"),  cls: "s-good" },
  { min: 30, label: t("tier.doubtful"),   cls: "s-mid" },
  { min: 0,  label: t("tier.fragile"),    cls: "s-low" },
];
const scoreTier = (v) => {
  const t2 = SCORE_TIERS();
  return t2.find(x => v >= x.min) || t2[3];
};

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

/* Barras del desglose: se ve de dónde sale el puntaje y qué lo hunde.

   El rótulo sale del DICCIONARIO y no del que manda el servidor. El backend
   define las partes en metrics.py con textos fijos en castellano —no sabe de
   idiomas— y la pantalla los dibujaba tal cual, así que con la aplicación en
   inglés, que es el idioma por omisión, el título decía "Score — how repeatable
   it looks" y las barras de abajo "Consistencia (Sharpe)".

   Hay una prueba que comprueba que cada parte del backend tenga su texto acá. */
function scoreBars(parts) {
  const defs = S.meta?.score_parts || [];
  if (!parts || !defs.length) return "";
  return `<div class="score-bars">${defs.map(d => {
    const v = +(parts[d.key] ?? 0);
    return `<div class="sb-row">
      <span class="sb-label">${esc(t("score." + d.key))}</span>
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
/* El estado visible de los controles de minado, en un solo lugar.

   Estaba repartido en el manejador del boton — cuatro lineas al arrancar y
   cuatro al terminar — y por eso al volver a la pantalla no se restauraba
   nada: el marcado se redibuja de cero y esas lineas no vuelven a correr.

   Con esto, dibujar la pantalla y arrancar una busqueda pasan por la misma
   funcion, asi que no pueden discrepar. */
function pintarEstadoMinado(corriendo) {
  const run = $("#m-run");
  if (run) run.disabled = !!corriendo;
  const acciones = $("#m-acciones");
  if (acciones) acciones.style.display = corriendo ? "" : "none";
  $("#m-runbar")?.classList.toggle("running", !!corriendo);
  // el punto de la barra lateral late mientras haya corrida: es la unica
  // senal de que algo pasa si el usuario se fue a otra pantalla
  $("#nav [data-page='mining']")?.classList.toggle("minando", !!corriendo);
  lockSetup(!!corriendo);
}

function lockSetup(on) {
  /* OJO: ESTA FUNCION ES DUENIA DE `disabled` EN TODO EL PANEL.
     Con `on=false` habilita TODOS los controles, así que un control que quiera
     estar apagado por su cuenta no puede usar la propiedad `disabled`: se la
     borra este barrido, que corre al dibujar la página.
     Se perdió un rato buscando por qué un botón no quedaba deshabilitado ni
     poniéndolo en la plantilla ni asignándolo después. Para apagar UNO, usar
     una clase y guardar el clic por la condición. Ver `pintarExigir`. */
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
    note.innerHTML = `<span>${icono("candado")}</span><div>${t("run.locked")}</div>`;
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
  /* Y la comisión, que es donde cobra un exchange.
     Va con `?? 0` a propósito: al pasar de un perpetuo a un CFD hay que
     APAGARLA, y dejar la anterior puesta cobraría 0,04% sobre un índice que no
     la cobra. Heredar un costo entre instrumentos es el mismo error que
     heredar el spread, y ese ya nos costó una corrida entera de -100%. */
  S.cfg.commission = ds?.suggested_commission ?? 0;
  // Un perpetuo no paga swap: paga funding, y ese sale de la serie real.
  // Arrastrar el swap del S&P a Bitcoin cobraria el costo de mantener dos
  // veces, asi que cambiar de instrumento lo apaga.
  S.cfg.swap = 0;
  /* La dirección también es propia del instrumento. Medido en EURUSD: buscando
     sólo largos el techo es 1.76% anual; permitiendo cortos, 4.52% — y con MÁS
     estrategias rentables, sin aflojar ninguna vara. Un par de divisas no sube:
     limitarlo a largos tira medio espacio de búsqueda. Un índice sí sube, y ahí
     "sólo largos" es una hipótesis con fundamento. */
  if (ds && ds.suggested_direction) S.cfg.direction = ds.suggested_direction;
  // el volumen mínimo también es propio del instrumento: 0.1 en un índice y
  // 0.01 en divisas, y heredar el del anterior da un chequeo que no sirve
  if (ds && ds.min_lot) S.cfg.minLot = ds.min_lot;
  /* Y el rendimiento que tiene sentido pedirle. Los techos medidos no se
     parecen: 14,95% anual en el S&P, 20,20% en oro, 21,84% en Bitcoin y 4,05%
     en EURUSD. Pedirle 3% a los cuatro trata como iguales a mercados que no lo
     son — en EURUSD equivale a exigir casi el máximo posible, y la búsqueda se
     va a decenas de minutos buscando lo que casi no existe. */
  if (ds && ds.min_cagr != null) S.cfg.minCagr = ds.min_cagr;
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
    const cr = CRIT_BY_KEY()[k];
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
    /* Y EL TOPE QUE DECLARA EL PROPIO CAMPO. Sólo se hacía valer el de los
       criterios, así que el `min="100"` del capital inicial era decorativo:
       con capital 0 la búsqueda arrancaba, no abría ni una operación, y el
       diagnóstico culpaba al mínimo de operaciones. El usuario aflojaba
       filtros persiguiendo un fantasma (3 de septiembre de 2026). */
    if (normalizar) {
      const piso = parseFloat(el.min), techo = parseFloat(el.max);
      if (Number.isFinite(piso) && n < piso) { el.value = piso; S.cfg[k] = piso; return; }
      if (Number.isFinite(techo) && n > techo) { el.value = techo; S.cfg[k] = techo; return; }
    }
    S.cfg[k] = n;
  });
  saveCfg();
}

/* --------------------------------------------------------- franjas horarias */

/** Las franjas elegidas, saneadas contra el catálogo que declara el servidor.
 *  Nunca devuelve vacío: sin ninguna, el minero no podría construir ni una
 *  candidata. */
function sesionesElegidas() {
  /* Con las franjas apagadas, siempre "todo el día".

     No alcanza con no dibujar los botones: la elección vive en localStorage,
     así que alguien que la semana pasada eligió Londres seguiría minando
     restringido a Londres sin ningún control en pantalla que lo diga ni con
     qué apagarlo. Una restricción invisible es peor que la perilla. */
  if (!SESIONES) return ["todo"];
  const validas = new Set((S.meta?.sessions || []).map(s => s.id));
  const elegidas = (S.cfg.sessions || []).filter(x => !validas.size || validas.has(x));
  return elegidas.length ? elegidas : ["todo"];
}

function nombreSesion(id) {
  return id ? t("s." + id) : "";
}

/** Qué franja conocida describe un time_filter suelto.
 *
 *  Las estrategias guardadas llevan su `time_filter` pero no el id de la
 *  franja: se guardaron antes de que las franjas existieran, o se editaron a
 *  mano. Reconocerlo permite mostrar "Sesión de Nueva York" en vez de un par
 *  de horas sueltas que nadie va a interpretar. */
function sesionDeFiltro(tf) {
  if (!tf || !tf.enabled) return "";
  const dias = [...(tf.days || [])].sort().join(",");
  const s = (S.meta?.sessions || []).find(x =>
    x.restringe && x.start_hour === tf.start_hour && x.end_hour === tf.end_hour
    && [...x.days].sort().join(",") === dias);
  return s ? s.id : "";
}

function horasSesion(id) {
  const s = (S.meta?.sessions || []).find(x => x.id === id);
  return (s && s.horario) || "";
}

/** El resumen de una sola línea que va debajo de las pastillas. */
function notaSesiones() {
  const el = sesionesElegidas();
  if (el.length === 1) {
    return el[0] === "todo"
      ? t("session.none")
      : `${t("session.fixed")} ${t("session.utc")}`;
  }
  return `${t("session.searched", { n: el.length })} ${t("session.utc")}`;
}

function cablearSesiones(root) {
  const host = $("#m-sessions", root);
  if (!host) return;
  $$("button", host).forEach(b => b.onclick = () => {
    const id = b.dataset.ses;
    const act = new Set(sesionesElegidas());
    if (act.has(id)) act.delete(id); else act.add(id);
    // Quitar la última dejaría al minero sin franjas. En vez de bloquear el
    // clic —que se siente como un botón roto— se vuelve a "todo el día", que
    // es lo que la persona quiso decir al apagar la única que quedaba.
    S.cfg.sessions = act.size ? [...act] : ["todo"];
    // "Todo el día" no se combina con nada: es la ausencia de restricción, y
    // tildarla junto a Londres significaría "Londres o cualquier hora", que es
    // lo mismo que no filtrar. Elegirla apaga el resto y viceversa.
    if (id === "todo" && act.has("todo")) S.cfg.sessions = ["todo"];
    else if (id !== "todo") S.cfg.sessions = S.cfg.sessions.filter(x => x !== "todo");
    if (!S.cfg.sessions.length) S.cfg.sessions = ["todo"];
    const vigentes = sesionesElegidas();
    $$("button", host).forEach(x => x.classList.toggle("on", vigentes.includes(x.dataset.ses)));
    const nota = $("#m-sesnote", root);
    // innerHTML y no textContent: el aviso lleva negritas sobre lo que importa
    // ("para CADA candidata"), y con textContent se veian las etiquetas crudas
    if (nota) nota.innerHTML = notaSesiones();
    saveCfg();
  });
  const nota = $("#m-sesnote", root);
  if (nota) nota.innerHTML = notaSesiones();
}

/* Cuánto espacio hay arriba del panel de configuración, publicado como
   variable CSS para que el panel pueda limitarse a lo que queda.

   Se mide en vez de asumirse. El CSS restaba sesenta píxeles fijos y el panel
   arranca a ciento ochenta y seis —arriba tiene el título de la pantalla y la
   pastilla de contexto—, así que a 1366x768 el botón de arrancar quedaba en
   y=765 con la ventana en 768. Y no se alcanzaba scrolleando: el panel es
   pegajoso, se detiene, y el botón se queda donde está.

   Se recalcula al cambiar el tamaño de la ventana, así que no puede volver a
   quedar viejo cuando cambie el encabezado. */
/* Cuánto hay que descontarle a la ventana para que el panel entre entero.

   Arriba del panel está el título de la pantalla, así que no arranca pegado
   al borde. Sin descontar ese hueco el botón de arrancar quedaba fuera de la
   ventana y no se alcanzaba ni scrolleando —medido a 1366x768, caía en
   y=765— porque el panel es pegajoso y se detiene.

   LA MEDICIÓN TIENE QUE SER INDEPENDIENTE DEL SCROLL, y la anterior no lo
   era: sumaba `getBoundingClientRect().top` —que ya viene con el scroll
   descontado— MÁS el `scrollTop` del contenedor, contándolo dos veces. Y como
   el panel es pegajoso, al pegarse su borde superior se clava en cero, así
   que la suma pasaba a ser el scroll entero y crecía cuanto más se bajaba.

   Medido: con el contenedor bajado 700px el hueco daba 752px y el panel se
   encogía de 578 a 148, con doce píxeles de caja usable adentro. Es el estado
   en el que alguien mina veinticinco estrategias, baja a mirarlas, y se
   encuentra con que la configuración es una ranura.

   El arreglo no puede salir de medir el panel: `offsetTop` TAMPOCO sirve en un
   elemento pegajoso —Chrome devuelve la posición desplazada, no la de
   maquetado: 192 sin scroll y 730 con el contenedor bajado 698—. Ni el
   rectángulo ni el offset son estables mientras el elemento esté pegado.

   Lo estable es el ancestro que NO es pegajoso, que se queda donde lo puso el
   maquetado. Se sube hasta el primero que cumpla eso y se mide ése, contra el
   contenedor con scroll.

   Y el tope es la red de seguridad, que es lo que faltaba. Da igual qué mida
   mal mañana: al panel no se le puede dejar menos de la mitad de la ventana,
   porque por debajo de eso deja de ser usable. Un error de medición tiene que
   degradar el ajuste, no romper la pantalla — de hecho ya salvó al segundo
   intento de este mismo arreglo. */
/* Cómo se dice la relación riesgo:beneficio de una búsqueda.

   Con una receta que la busca, decir "1:2" es mentir: esa corrida va a probar
   candidatas con varias relaciones y ninguna va a ser la configurada. El
   panel de "listo para buscar" es la promesa de lo que la aplicación está por
   hacer, así que tiene que describir lo que va a hacer de verdad.

   Se resuelve en una sola función porque lo decían dos lugares —el resumen
   del paso de riesgo y el panel de arranque— y dos textos que dicen lo mismo
   por caminos distintos terminan diciendo cosas distintas. */
function comoSeDiceElRR() {
  const lista = S.cfg.rrBuscado;
  if (!lista || !lista.length) return `1:${S.cfg.rr}`;
  if (lista.length === 1) return `1:${lista[0]}`;
  return t("rr.varias", { desde: Math.min(...lista), hasta: Math.max(...lista) });
}

function medirHuecoDelPanel() {
  const panel = document.querySelector(".setup");
  if (!panel) return;
  const AIRE = 24;                 // el respiro de abajo, igual que el de arriba
  const cont = panel.closest("main") || document.body;

  let marco = panel;
  while (marco.parentElement && marco !== cont
         && getComputedStyle(marco).position === "sticky") {
    marco = marco.parentElement;
  }
  const arriba = marco.getBoundingClientRect().top
               - cont.getBoundingClientRect().top + cont.scrollTop;

  const TOPE = Math.round(window.innerHeight * 0.5);
  const hueco = Math.min(Math.max(60, Math.round(arriba + AIRE)), TOPE);
  document.documentElement.style.setProperty("--setup-hueco", hueco + "px");
}

let _huecoPendiente = null;
window.addEventListener("resize", () => {
  clearTimeout(_huecoPendiente);
  _huecoPendiente = setTimeout(medirHuecoDelPanel, 120);
});

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

/* LA DIRECCIÓN DICE DÓNDE ESTÁS.

   La aplicación no tocaba la URL nunca: el botón Atrás del navegador te sacaba
   de la aplicación entera, Adelante volvía recargando, y recargar desde
   cualquier sección te devolvía a Buscar. Con el fragmento —#/saved/aprobadas—
   Atrás y Adelante recorren las pantallas y una recarga te deja donde estabas.

   En la ventana de escritorio no hay barra de direcciones, así que el
   fragmento no se ve; los atajos del navegador sí funcionan igual. */
//: Las únicas pantallas partidas en bandejas. Las demás no llevan segunda
//: parte: sin esta lista, Aprender heredaba la bandeja de la pantalla
//: anterior y la dirección quedaba en "#/consejos/aprobadas".
const CON_BANDEJA = new Set(["mining", "saved", "operar"]);

function rutaDe(page, vista) {
  const segunda = CON_BANDEJA.has(page) ? vista : null;
  return "#/" + [page, segunda].filter(Boolean).join("/");
}

/** Lee la dirección. Devuelve null si no nombra una pantalla que exista: una
 *  URL vieja o escrita a mano no puede dejar la aplicación en blanco. */
function rutaActual() {
  const partes = (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
  if (!partes.length || !PAGES[partes[0]]) return null;
  return { page: partes[0], vista: partes[1] };
}

//: Mientras se navega por el historial no se vuelve a apilar, o cada Atrás
//: crearía una entrada nueva y el botón dejaría de avanzar.
let VOLVIENDO = false;

window.addEventListener("popstate", () => {
  const r = rutaActual();
  if (!r) return;
  VOLVIENDO = true;
  navigate(r.page, r.vista).finally(() => { VOLVIENDO = false; });
});

async function refreshDatasets() {
  [S.datasets, S.catalog] = await Promise.all([
    api.get("/api/datasets"), api.get("/api/catalog"),
  ]);
  if (S.sel.dataset_id && !S.datasets.some(d => d.id === S.sel.dataset_id)) {
    S.sel.dataset_id = null;
  }
  if (!S.sel.dataset_id && S.datasets.length) {
    /* La aplicación elige el instrumento sola cuando no hay ninguno: al abrir,
       o cuando el que estaba se borró. Sin adoptar sus costos acá, ese caso
       arrancaba con el spread del instrumento ANTERIOR y nadie lo eligió.

       Y no elige el primero de la lista sino el que MÁS estrategias produce,
       medido sobre los mismos datos que trae la aplicación. La primera búsqueda
       de alguien que recién llega decide si vuelve: arrancarla en el
       instrumento más difícil es empezar perdiendo. */
    const delMundo = datasetsDelMundo();
    const recomendado = (S.catalog || []).find(
      c => c.mejor_rendimiento && c.dataset_id
        && delMundo.some(d => d.id === c.dataset_id));
    S.sel.dataset_id = (recomendado && recomendado.dataset_id)
      || (delMundo[0] || S.datasets[0]).id;
    adoptInstrumentDefaults();
  }
}

async function navigate(page, vista) {
  S.page = page;
  if (!VOLVIENDO) {
    const ruta = rutaDe(page, vista || (page === "operar" ? S.vistaOperar : S.vista));
    // reemplazar en vez de apilar cuando es la misma pantalla: si no, quedarse
    // quieto llenaba el historial de entradas iguales
    if (location.hash === ruta) history.replaceState(null, "", ruta);
    else history.pushState(null, "", ruta);
  }
  // la vista pedida va a la memoria de SU sección, ver S.vista / S.vistaOperar
  if (vista) { if (page === "operar") S.vistaOperar = vista; else S.vista = vista; }
  /* ACTIVO POR PÁGINA Y VISTA: Probar y Aprobadas son la misma página con
     otra bandeja, y Operar tiene atajos abajo (cuenta, automático). */
  const vistaAct = page === "operar" ? (S.vistaOperar || "bot") : (S.vista || "");
  $$("#nav button").forEach(b => b.classList.toggle("active",
    b.dataset.page === page && (!b.dataset.vista || b.dataset.vista === vistaAct
      || (page === "saved" && b.dataset.vista === "por_probar" && !["aprobadas"].includes(vistaAct)))));
  const main = $("#main");
  main.innerHTML = "";
  try {
    await PAGES[page](main);
    /* LA PANTALLA NUEVA ENTRA, no aparece: 200 ms desde 8 px abajo. Se
       reinicia la clase para que corra aunque sea la misma página. */
    main.classList.remove("entra"); void main.offsetWidth; main.classList.add("entra");
    animarCifras(main);
    marcarPrimerosPasos();
  } catch (e) {
    // Sin esto, cualquier fallo dejaba el <main> vacío para siempre: la página
    // ya se había limpiado y nadie volvía a escribir nada. Se veía igual que
    // una carga eterna, sin ningún mensaje ni forma de salir.
    if (e && e.status === 401) { pedirCuenta(401); }
    main.innerHTML = pageHead(TITULOS()[page] || "Botiquant", "") + `
      <div class="card"><div class="empty-state">
        <div class="big">${icono("alerta","ico-xl")}</div>
        <b>${esc(e && e.status === 401 ? t("auth.expired") : t("err.page"))}</b>
        <p class="mt">${esc(e && e.status === 401
          ? t("auth.expired_sub")
          : (e && e.message) || t("err.no_response"))}</p>
        <button class="btn mt" id="reintentar">${esc(t("ui.retry"))}</button>
      </div></div>`;
    const b = $("#reintentar", main);
    if (b) b.onclick = () => navigate(page);
    return;
  }
  main.scrollTop = 0;
}

const TITULOS = () => ({
  bienvenida: t("wel.title"), data: t("nav.data"), mining: t("nav.mining"),
  saved: t(S.vista === "aprobadas" ? "nav.aprobadas" : S.vista === "descartadas" ? "saved.descartadas_t" : "nav.saved"),
  consejos: t("nav.tips"),
  operar: t(S.mundo === "metatrader" ? "nav.operar_cfd" : "nav.operar"),
});

/* Todo lo que vive fuera del <main> y por lo tanto no se repinta al navegar:
   la barra lateral, el pie, el selector de idioma. Se llama al arrancar y cada
   vez que cambia el idioma. */
/* Las dos secciones. No son dos filtros de lo mismo: son dos productos que
   comparten el buscador y no comparten nada más. */
const MUNDOS = () => [
  { id: "metatrader", rotulo: t("mundo.cfds"), sub: t("mundo.cfds_sub") },
  { id: "exchange", rotulo: t("mundo.cripto"), sub: t("mundo.cripto_sub") },
];

function pintarMundo() {
  const caja = $("#mundo-sw");
  if (!caja) return;
  caja.innerHTML = `<span class="mundo-rot">${esc(t("mundo.rotulo"))}</span>
    <div class="mundo-btns">${MUNDOS().map(m => `
      <button data-mundo="${m.id}" class="${S.mundo === m.id ? "on" : ""}"
        title="${esc(m.sub)}">${esc(m.rotulo)}</button>`).join("")}</div>`;
  /* EL MENÚ SIGUE A LA SECCIÓN: en CFDs no hay tercer paso ni cuenta que
     conectar. Se hace acá, que es lo que se llama cada vez que cambia. */
  const cfd = S.mundo === "metatrader";
  const navOp = $("#nav-operar"); if (navOp) navOp.hidden = cfd;
  const navCu = $("#nav-cuenta"); if (navCu) navCu.hidden = cfd;
  const navPi = $("#nav-piloto"); if (navPi) navPi.hidden = cfd;
  $$("[data-mundo]", caja).forEach(b => b.onclick = () => {
    if (b.dataset.mundo === S.mundo) return;
    S.mundo = b.dataset.mundo;
    recordarEleccionDeMundo();
    // en CFDs no existe Operar: quien estaba ahí vuelve a Probar
    if (S.mundo === "metatrader" && S.page === "operar") S.page = "saved";
    /* CAMBIAR DE SECCION OLVIDA EL INSTRUMENTO ELEGIDO. Si no, se queda
       apuntando a uno que en la sección nueva no existe, y la pantalla de
       minado abre mostrando un instrumento que no está en su propia lista. */
    S.sel.dataset_id = null;
    /* Y OLVIDA LA CORRIDA ELEGIDA: es de la otra sección, y filtrar por ella
       acá dejaría la tabla vacía sin decir por qué. */
    S.banco.corrida = "";
    S.banco.sel.clear();
    /* Y LA BÚSQUEDA DE LA OTRA SECCIÓN: el progreso y el resultado de un
       perpetuo se veían bajo la pastilla del S&P (2 de septiembre). */
    S.mineResult = null; S.mineLive = null; S.primeraBusqueda = false;
    saveCfg();
    pintarMundo();
    /* Los números del menú son de la sección: 236 al lado de "Minado" en
       cripto, con cero perpetuos minados, prometía lo que no había. */
    /* Un fundido corto al cambiar de sección: cambió TODO lo de la
       pantalla, y sin movimiento parecía que no había pasado nada. */
    const main = $("#main");
    if (main) { main.classList.remove("cruza"); void main.offsetWidth; main.classList.add("cruza"); }
    Promise.allSettled([refreshSavedCount(), refreshBancoCount(), refreshRobots()])
      .then(() => navigate(S.page));
  });
}

function pintarChrome() {
  document.documentElement.setAttribute("lang", idioma());
  $$("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  /* EL CUARTO VERBO CAMBIA CON LA SECCIÓN: en CFDs no se opera desde la
     aplicación, se exporta un robot a MetaTrader. Decir "Operar" ahí era
     prometer algo que la pantalla no hace. */
  const op = $("#nav-operar [data-i18n]");
  if (op) op.textContent = t("nav.operar");
  // la licencia se pinta una sola vez y quedaba en el idioma anterior
  refreshLicencia();
  /* EN CFDs NO HAY TERCER PASO: se exporta el robot desde Probar. Operar y
     la cuenta del exchange desaparecen del menú en esa sección. */
  pintarCuenta();
  pintarMundo();
  const rot = $("#nav-rotulo");
  if (rot) rot.textContent = t("nav.section");
  const rotIdioma = $("#lang-rotulo");
  if (rotIdioma) rotIdioma.textContent = t("nav.language");
  /* El enlace de soporte. En el escritorio apunta al sitio y no a un archivo
     local: la página se puede corregir sin que nadie vuelva a descargar nada,
     y el número de WhatsApp puede cambiar sin dejar tirada a la gente que
     tiene una versión vieja instalada. */
  const sop = $("#soporte-link");
  if (sop) {
    sop.textContent = t("nav.support");
    sop.href = ORIGEN_SITIO + "/soporte";
  }
  const conn = $("#conn-text");
  if (conn) conn.textContent = t("nav.offline");
  const btn = $("#theme-btn");
  if (btn) {
    btn.setAttribute("aria-label", t("nav.theme"));
    btn.title = document.documentElement.getAttribute("data-theme") === "light"
      ? t("nav.theme_dark") : t("nav.theme_light");
  }
  pintarIdiomas();
}

function pintarIdiomas() {
  const host = $("#lang-sw");
  if (!host) return;
  host.replaceChildren();
  host.setAttribute("role", "group");
  host.setAttribute("aria-label", t("nav.language"));
  for (const lg of IDIOMAS) {
    const b = document.createElement("button");
    b.type = "button";
    // el nombre entero y en su propio idioma: "ES" no le dice nada a quien
    // abrió la aplicación en inglés justamente porque no lee inglés
    b.textContent = lg.nombre;
    b.className = lg.id === idioma() ? "on" : "";
    b.setAttribute("aria-pressed", String(lg.id === idioma()));
    // Se repinta TODO, no sólo el marco: las pantallas arman su HTML con
    // llamadas a t() en el momento de dibujarse, así que cambiar el idioma
    // sin volver a dibujar dejaría el contenido en el anterior.
    b.onclick = () => setIdioma(lg.id, () => { pintarChrome(); navigate(S.page); });
    host.appendChild(b);
  }
}

/* ================================== CONECTAR LA ESTRATEGIA A BINGX ===
   El camino de producción para cripto, y la razón de que no haya un programa
   nuestro corriendo en la máquina de nadie.

   TradingView evalúa las reglas en SUS servidores y, cuando se cumplen, le
   manda un aviso HTTP directo a BingX, que ejecuta. Eso resuelve de una vez
   las tres cosas que un bot propio no podía resolver bien: la computadora no
   tiene que quedar prendida, nosotros no tocamos nunca la clave de API, y no
   hay que instalar ni firmar ningún ejecutable aparte.

   El costo es que TradingView cobra por los webhooks. Se dice en el paso 1 y
   no al final: enterarse después de hacer cinco pasos es peor.

   Lo que NO hacemos acá es inventar el mensaje que espera BingX. La
   plataforma le genera a cada usuario el suyo, con su identificador de bot
   adentro; adivinar el formato produciría órdenes que el exchange descarta en
   silencio, que es el peor resultado posible porque parece que está
   operando. */
/* HOY EL CAMINO PRINCIPAL ES EL BOT DE LA APLICACION contra la demo de
   Binance (Operar → Claves → Encender): se mide en vivo con stop y take
   profit en el exchange, y es lo que ya operó de verdad. El webhook de
   TradingView queda como alternativa, plegada, para quien no puede dejar la
   computadora prendida — y se dice que Binance no lo recibe directo. */
function abrirGuiaBingx(nombreEstrategia, simbolo) {
  const host = document.createElement("div");
  host.className = "overlay";
  const lista = (pasos) => `<ol class="guia-pasos">
        ${pasos.map(([tt, dd]) => `<li><b>${esc(tt)}</b><span>${esc(dd)}</span></li>`).join("")}
      </ol>`;
  const enApp = [
    [t("bx.a1_t"), t("bx.a1_d")],
    [t("bx.a2_t"), t("bx.a2_d")],
    [t("bx.a3_t"), t("bx.a3_d")],
  ];
  const conWebhook = [
    [t("bx.p1_t"), t("bx.p1_d")],
    [t("bx.p2_t"), t("bx.p2_d")],
    [t("bx.p3_t"), t("bx.p3_d")],
    [t("bx.p4_t"), t("bx.p4_d")],
    [t("bx.p5_t"), t("bx.p5_d")],
  ];
  host.innerHTML = `<div class="sheet">
    <div class="sheet-head">
      <div><h2>${esc(t("bx.title"))}</h2>
        <p>${esc(nombreEstrategia)}${simbolo ? " · " + esc(simbolo) : ""}</p></div>
      <button class="sheet-close">${icono("cerrar")}</button>
    </div>
    <div class="guia-bx">
      <p class="help-note">${esc(t("bx.intro"))}</p>
      <h3 class="guia-tit">${esc(t("bx.app_t"))}</h3>
      ${lista(enApp)}
      <div class="controls mt"><button class="btn" id="guia-operar">${icono("seguir")} ${esc(t("bx.ir_operar"))}</button></div>
      <div class="guia-aviso">
        <b>${esc(t("bx.demo_t"))}</b>
        <span>${esc(t("bx.demo_d"))}</span>
      </div>
      <details class="guia-alt">
        <summary><b>${esc(t("bx.alt_t"))}</b><span>${esc(t("bx.alt_sub"))}</span></summary>
        ${lista(conWebhook)}
        <p class="help-note">${esc(t("bx.compara"))}</p>
      </details>
    </div>
  </div>`;
  document.body.appendChild(host);
  const close = () => host.remove();
  $(".sheet-close", host).onclick = close;
  /* CIERRA TODO LO QUE HAY ENCIMA, no sólo la guía: abajo suele estar la
     ficha de la estrategia, y con ella abierta "Ir a Operar" parecía volver
     a la pantalla anterior en vez de ir a Operar (2 de septiembre). */
  $("#guia-operar", host).onclick = () => {
    $$(".overlay").forEach(o => o.remove());
    navigate("operar", "claves");
  };
  host.onclick = (e) => { if (e.target === host) close(); };
  cerrarConEscape(host, close);
}


/* ============================================== PORTAFOLIO COMO UNA HOJA ===
   Era una de las siete secciones del menú, con su propio selector de
   estrategias — el tercero idéntico. Pero "¿funcionan juntas?" no es un lugar
   al que ir: es algo que se pregunta sobre estrategias que YA se eligieron.

   Así que ahora se tildan dos o más en Mis estrategias y esto se abre encima,
   sin salir del paso 3 ni perder la selección. */
async function abrirPortafolio(elegidas) {
  const host = document.createElement("div");
  host.className = "overlay";
  host.innerHTML = `<div class="sheet">
    <div class="sheet-head">
      <div><h2>${esc(t("pf.title"))}</h2>
        <p>${esc(elegidas.map(x => x.name).join(" · "))}</p></div>
      <button class="sheet-close">${icono("cerrar")}</button>
    </div>
    <div id="pf-body"><div class="empty-state"><span class="spinner"></span>
      ${esc(t("pf.building"))}</div></div>
  </div>`;
  document.body.appendChild(host);
  const close = () => host.remove();
  $(".sheet-close", host).onclick = close;
  host.onclick = (e) => { if (e.target === host) close(); };
  cerrarConEscape(host, close);

  const body = $("#pf-body", host);
  try {
    const r = await api.post("/api/portfolio", {
      estrategias: elegidas.map(x => ({ origen: "guardada", id: x.id })),
      initial_capital: S.cfg.capital,
    });
    body.innerHTML = resultadoPF(r) + `
      <div class="pf-bajar">
        <div>
          <b>${esc(t(S.mundo === "exchange" ? "pf.encender_title" : "pf.export_title"))}</b>
          <p class="help-note">${esc(t(S.mundo === "exchange" ? "pf.encender_sub" : "pf.export_sub", { n: elegidas.length }))}</p>
        </div>
        <button class="btn ghost" id="pf-compartir">${icono("seguir")} ${esc(t("comp.btn"))}</button>
        ${S.mundo === "exchange"
          ? `<button class="btn" id="pf-encender">${icono("seguir")} ${esc(t("pf.encender_conjunto"))}</button>`
          : `<button class="btn" id="pf-mql5">${icono("bajar")} ${esc(t("pf.export_btn"))}</button>`}
      </div>`;
    /* ENCENDER EL CONJUNTO: el mismo plan que reparte la cuenta entre los
       robots, y cada uno pasa por las mismas puertas que uno solo. */
    /* COMPARTIR EL CONJUNTO: la otra mitad del producto. Se publica lo que
       se ve —qué lo compone, qué tan parecidas son y sobre qué ventana— sin
       las reglas de cada estrategia. */
    const compPf = $("#pf-compartir", body);
    if (compPf) compPf.onclick = () => abrirCompartirPortafolio(elegidas, r);

    const encConj = $("#pf-encender", body);
    if (encConj) encConj.onclick = async () => {
      encConj.disabled = true;
      let prendidos = 0;
      try {
        const ex = await api.get("/api/exchanges");
        if (!ex.some(x => x.exchange === "binance" && x.entorno === "practica" && x.configurada)) {
          toast(t("op.conectar_primero"), "err"); close(); navigate("operar", "claves"); return;
        }
        const plan = await api.post("/api/bot/plan-conjunto", { ids: elegidas.map(x => x.id), usar_pct: 90 });
        /* UNA QUE NO PUEDE NO FRENA A LAS DEMÁS: cortaba en la primera y
           dejaba el conjunto a medias sin intentar el resto. */
        const fallos = [];
        for (const d of plan.detalle) {
          const fila = elegidas.find(x => x.id === d.id);
          try {
            const archivo = await api.post("/api/export/bingx/objeto", {
              spec: fila.spec, name: fila.name, dataset_id: (fila.meta || {}).dataset_id,
              timeframe: (fila.meta || {}).timeframe, settings: { commission_pct: (fila.meta || {}).commission },
              metrics: (fila.meta || {}).metrics, oos: (fila.meta || {}).oos,
            });
            await api.post("/api/bot/encender", { bot: archivo, modo: "practica", exchange: "binance",
                                                  estrategia_id: d.id, porcion: (plan.porciones[d.id] || 0) / 100 });
            prendidos += 1;
          } catch (err) { fallos.push(`${fila.name}: ${err.message}`); }
        }
        toast(fallos.length
          ? t("conj.parcial", { n: prendidos, f: fallos.length, motivo: fallos[0] })
          : t("conj.encendido", { n: prendidos }), fallos.length ? "err" : "ok");
        close(); SEL_PF.clear(); navigate("operar", "bot");
      } catch (e) {
        toast(t("conj.fallo", { n: prendidos, err: e.message }), "err");
        encConj.disabled = false;
      }
    };
    const caja = $("#pf-eq", body);
    if (caja) Charts.equity(caja, {
      values: r.combined_equity, labels: r.timestamps,
      initial: r.combined_equity[0], height: 300,
    });

    /* EL BOTÓN QUE FALTABA, y era el único eslabón que no estaba.
       El panel medía el conjunto —correlación, curva combinada, reparto del
       riesgo— y después no había forma de bajarlo: sólo un botón de cerrar.
       Quien quería el portafolio tenía que exportar de a uno desde la tabla,
       y ahí CADA EA se cree dueño del 100% de la cuenta: tres exportados por
       separado arriesgan tres veces lo pedido, y el aviso de riesgo de cada
       uno dice que está bien porque contra su propio número lo está. */
    const bajar = $("#pf-mql5", body);
    if (bajar) bajar.onclick = async () => {
      bajar.disabled = true;
      try {
        const d = await api.post("/api/export/portafolio", {
          ids: elegidas.map(x => x.id),
          usar_pct: 90,
          server_utc_offset: S.cfg.brokerUtc,
        });
        (d.avisos || []).forEach(a => toast(a.texto, "warn"));
        toast(t("pf.export_ok", { n: (d.archivos || []).length,
                                  carpeta: d.carpeta }), "ok");
      } catch (e) {
       if (!pedirCuenta(e.status)) toast(e.message, "err"); }
      bajar.disabled = false;
    };
  } catch (e) {
    body.innerHTML = `<div class="empty-state neg">${esc(e.message)}</div>`;
  }
}

/** Qué tan parecidas son dos estrategias, en palabras.
 *
 *  `null` no es cero: significa que no se pudo medir porque los períodos no
 *  se solapan lo suficiente. Pintarlo como 0.00 decía "diversificación
 *  perfecta" justo cuando no había con qué afirmarlo. */
function juicioCorrelacion(c) {
  if (c == null) return { cls: "medio", txt: t("pf.corr_unknown") };
  if (c >= 0.7) return { cls: "mal", txt: t("pf.corr_high") };
  if (c >= 0.3) return { cls: "medio", txt: t("pf.corr_mid") };
  return { cls: "bien", txt: t("pf.corr_low") };
}

function resultadoPF(r) {
  const m = r.metrics || {};
  const n = r.names.length;
  const comps = r.componentes || [];
  const prom = m.avg_correlation;
  const j = juicioCorrelacion(prom);
  const mudas = r.sin_datos || [];

  // El extremo del triángulo superior: el par que más se parece es el que
  // decide si el conjunto está diversificado o no, y con seis estrategias
  // nadie va a leer una matriz de 36 celdas buscándolo.
  let peor = null;
  for (let i = 0; i < n; i++) {
    for (let k = i + 1; k < n; k++) {
      const c = r.correlation[i][k];
      if (c == null) continue;
      if (!peor || c > peor.c) peor = { c, a: r.names[i], b: r.names[k] };
    }
  }

  const celda = (v, diagonal) => {
    if (diagonal) return `<td class="pf-diag">—</td>`;
    if (v == null) return `<td class="pf-diag" title="${esc(t("pf.no_overlap_cell"))}">·</td>`;
    const cl = v >= 0.7 ? "mal" : v >= 0.3 ? "medio" : "bien";
    return `<td class="pf-corr ${cl}">${fmtNum(v, 2)}</td>`;
  };

  // Comparar el portafolio contra la MEJOR de sus partes es lo único que
  // contesta "¿me convino combinarlas?". Contra el promedio siempre gana.
  const mejorParte = comps.reduce((best, c) =>
    (!best || (c.metrics.cagr_pct ?? -1e9) > (best.metrics.cagr_pct ?? -1e9)) ? c : best, null);

  return `
  <div class="card" id="pf-resultado">
    <h2>${esc(t("pf.combined"))}
      <span class="hint">${n} ${esc(t("ui.strategies"))} · ${esc(t("pf.equal_weight"))}</span></h2>
    <div class="statgrid mt">
      <div class="stat"><span>${rotuloMetrica("m.cagr")}</span>
        <b class="${m.cagr_pct >= 0 ? "pos" : "neg"}">${fmtPct(m.cagr_pct)}</b></div>
      <div class="stat"><span>${rotuloMetrica("m.dd")}</span>
        <b class="${nivelDD(m.max_drawdown_pct, riesgoActual())}">${
          fmtNum(m.max_drawdown_pct, 1)}<u>%</u></b></div>
      <div class="stat"><span>${rotuloMetrica("m.sharpe")}</span><b>${fmtNum(m.sharpe)}</b></div>
      <div class="stat"><span>${esc(t("pf.correlation"))}</span>
        <b class="pf-${j.cls}">${prom == null ? "—" : fmtNum(prom, 2)}</b></div>
    </div>
    ${/* DE DÓNDE SALEN ESTAS CIFRAS. La misma estrategia mostraba tres
          números distintos —en la lista, acá y en el enlace— y no había
          manera de saber por qué. El conjunto se mide sobre los días en
          que TODAS tienen datos, así que es más corto que cada una. */ ""}
    ${r.ventana?.from ? `<p class="help-note nota-ventana">${esc(t("pf.ventana", {
        desde: r.ventana.from, hasta: r.ventana.to }))}</p>` : ""}
    ${mudas.length ? `<div class="banner warn mt"><span class="b-ic">${icono("alerta")}</span>
      <div>${t("pf.no_overlap", { lista: mudas.map(esc).join(", "),
        desde: esc(r.ventana?.from || ""), hasta: esc(r.ventana?.to || "") })}</div></div>` : ""}
    <div class="pf-juicio ${j.cls}">
      <b>${esc(j.txt)}</b>
      <p>${esc(t("pf.correlation_help"))}</p>
      ${peor ? `<p class="help-note">${esc(t("pf.worst_pair"))}:
        <b>${esc(peor.a)}</b> ${esc(t("ui.and"))} <b>${esc(peor.b)}</b> — ${fmtNum(peor.c, 2)}</p>` : ""}
    </div>
    <div class="chart-box tall mt" id="pf-eq"></div>
    ${/* EL VEREDICTO, NO LA REGLA: decía "combinar conviene cuando la caída
          baja más de lo que baja el rendimiento" y dejaba la cuenta al
          lector. Ahora se hace la cuenta y se dice si conviene. */ ""}
    ${mejorParte ? `<p class="pf-veredicto ${
      (m.max_drawdown_pct ?? 0) < (mejorParte.metrics.max_drawdown_pct ?? 0) ? "bien" : "medio"}">${
      esc(t((m.max_drawdown_pct ?? 0) < (mejorParte.metrics.max_drawdown_pct ?? 0) ? "pf.conviene" : "pf.no_conviene", {
        nombre: mejorParte.name,
        parte: fmtNum(mejorParte.metrics.cagr_pct ?? 0, 1),
        dd: fmtNum(mejorParte.metrics.max_drawdown_pct ?? 0, 1),
        junto: fmtNum(m.cagr_pct, 1),
        ddjunto: fmtNum(m.max_drawdown_pct, 1) }))}</p>` : ""}
    ${mejorParte ? `<p class="help-note">${esc(t("pf.vs_best", {
      nombre: mejorParte.name,
      parte: fmtNum(mejorParte.metrics.cagr_pct ?? 0, 1),
      dd: fmtNum(mejorParte.metrics.max_drawdown_pct ?? 0, 1),
      junto: fmtNum(m.cagr_pct, 1),
      ddjunto: fmtNum(m.max_drawdown_pct, 1),
    }))}</p>` : ""}
  </div>

  <div class="card">
    <h2>${esc(t("pf.correlation"))}</h2>
    <div class="table-scroll"><table class="pf-matriz">
      <thead><tr><th></th>${r.names.map((x, i) =>
        `<th class="num" title="${esc(x)}">${i + 1}</th>`).join("")}
        <th class="num">${esc(t("pf.contribution"))}</th></tr></thead>
      <tbody>${r.names.map((name, i) => `
        <tr>
          <th class="pf-nombre"><span class="pf-idx">${i + 1}</span>${esc(name)}</th>
          ${r.correlation[i].map((v, k) => celda(v, i === k)).join("")}
          <td class="num"><b>${fmtNum(r.risk_contribution_pct[i], 1)}%</b></td>
        </tr>`).join("")}
      </tbody>
    </table></div>
  </div>`;
}

/* ========================================================= BIENVENIDA ======
   Se ve una sola vez, y existe por una razón concreta: alguien que abre esto
   por primera vez veía siete secciones sin ningún orden y tenía que deducir
   solo que Monte Carlo va DESPUÉS de minar. El camino ahora está en el menú,
   numerado, pero el menú se lee cuando ya sabés que hay un camino.

   Tres tarjetas y un botón. No es un tutorial ni un asistente que no te deja
   salir: es el mapa, una vez, y después nunca más. */
const VISTA_BIENVENIDA = "bq.bienvenida";

const PASOS_BIENVENIDA = () => [
  { n: 1, ico: "diana", clave: "wel.s1" },
  { n: 2, ico: "banco", clave: "wel.s2" },
  { n: 3, ico: "bajar", clave: "wel.s3" },
];

PAGES.bienvenida = async (main) => {
  main.innerHTML = `<div class="wel">
    <div class="wel-cab">
      <span class="logo-mark grande" aria-hidden="true"><i class="pulpo"></i></span>
      <h1>${esc(t("wel.title"))}</h1>
      <p>${esc(t("wel.sub"))}</p>
    </div>
    <!-- LA PRIMERA DECISION ES QUE SE OPERA, y va acá y no escondida en un
         interruptor de la barra lateral. No son dos filtros de lo mismo: son
         dos productos que comparten el buscador y no comparten nada más —otro
         mercado, otro costo, otro lugar donde termina corriendo el robot—.
         Elegir mal significa minar sobre datos que no se van a poder operar,
         y descubrirlo recién al querer encender.

         Se elige y no se adivina: nadie puede deducir de un instrumento si el
         usuario tiene cuenta de MetaTrader o de un exchange. -->
    <div class="wel-mundos">
      ${MUNDOS().map(m => `
        <button class="wel-mundo" data-elegir="${esc(m.id)}">
          <span class="wel-mundo-ico">${icono(m.id === "metatrader" ? "pico" : "banco", "ico-lg")}</span>
          <b>${esc(m.rotulo)}</b>
          <p>${esc(m.sub)}</p>
          <span class="wel-mundo-ir">${esc(t("wel.elegir"))}</span>
        </button>`).join("")}
    </div>
    <p class="wel-fina">${esc(t("wel.cambiar"))}</p>
    <ol class="wel-pasos">
      ${PASOS_BIENVENIDA().map(p => `
        <li>
          <span class="wel-num">${p.n}</span>
          <span class="wel-ico">${icono(p.ico, "ico-lg")}</span>
          <b>${esc(t(p.clave))}</b>
          <p>${esc(t(p.clave + "_sub"))}</p>
        </li>`).join("")}
    </ol>
    <div class="wel-expl">${explicacionHTML("entrada", PASOS_ENTRADA())}</div>
  </div>`;
  atarExplicacion(main, "entrada", PASOS_ENTRADA());

  $$("[data-elegir]", main).forEach(b => b.onclick = () => {
    S.mundo = b.dataset.elegir;
    recordarEleccionDeMundo();
    /* El instrumento elegido se olvida al cambiar de mundo, por el mismo
       motivo que en el interruptor de la barra: quedaría apuntando a uno que
       en la sección nueva no existe. */
    S.sel.dataset_id = null;
    saveCfg();
    pintarMundo();
    /* AL MINADO Y NO A DATOS: con la semilla adentro, las dos secciones abren
       con instrumentos listos. Mandar a Datos era correcto cuando la
       aplicación abría vacía y ahora sería un rodeo. Los contadores del
       menú se piden de nuevo porque son de la sección recién elegida. */
    Promise.allSettled([refreshSavedCount(), refreshBancoCount(), refreshRobots()])
      .then(() => navigate(S.datasets.length ? "mining" : "data"));
  });
};

/* Se muestra mientras nadie haya ELEGIDO qué opera.

   Antes se saltaba si ya había algo hecho —estrategias guardadas, un banco—
   y por eso quien venía de la versión con sólo CFDs abría directo en la
   sección que hubiera quedado guardada, sin haberla elegido nunca (2 de
   septiembre: "ni siquiera elegí el panel"). Tener trabajo hecho no
   reemplaza la decisión: son dos productos distintos y la elección es del
   usuario, no de un valor que quedó en el almacenamiento. */
const MUNDO_ELEGIDO = "qf.mundo_elegido";

function tocaBienvenida() {
  try { return localStorage.getItem(MUNDO_ELEGIDO) !== "1"; } catch (e) { return true; }
}

function recordarEleccionDeMundo() {
  try {
    localStorage.setItem("qf.mundo", S.mundo);
    localStorage.setItem(MUNDO_ELEGIDO, "1");
    localStorage.setItem(VISTA_BIENVENIDA, "1");
  } catch (e) { /* modo privado */ }
}

/* ══════════════════════════════════════════════════════ CONSEJOS ══════════
   Lo que aprendimos midiendo, no lo que se dice por ahí.

   Cada consejo lleva su número medido y sobre qué instrumento se midió. Es la
   diferencia entre "usá más historia" —que suena a consejo de manual— y "con
   todo el histórico el S&P rinde 3.5% anual y sobrevive el 94% de las veces;
   con los últimos dos años rinde 21.4% y sobrevive el 65%", que le permite a
   alguien decidir con qué se queda.

   Es texto y nada más. Sin gráficos, sin interactividad: se entra, se lee y se
   vuelve a minar. Una sección de ayuda que hay que aprender a usar no es ayuda.

   El orden importa: primero el que más cambia los resultados de alguien que
   recién empieza, último el que sólo importa cuando ya está exportando. */
/* ══════════════════════════════════════ LOS DIBUJOS DE LOS CONSEJOS ═══════
   Un gráfico por consejo, y cada uno dibuja EL dato de ese consejo. Ninguno es
   decorativo: si un consejo no tuviera una cifra que mostrar, no llevaría
   dibujo.

   SVG escrito a mano y no una librería. Son seis diagramas fijos —los números
   salen de mediciones ya hechas y no cambian— así que traer un motor de
   gráficos sería cargar un camión para llevar una caja. Y en SVG inline los
   colores salen de las variables del tema, así que los seis funcionan en claro
   y en oscuro sin una línea extra.

   Regla de composición: el número va SIEMPRE pegado a su barra. Una leyenda
   aparte obliga a ir y volver con la vista, y eso es más trabajo que leer la
   frase que el dibujo venía a resumir. */

const G_ANCHO = 620, G_BARRA = 22, G_HUECO = 9;

function lienzo(alto, cuerpo, titulo) {
  return `<svg class="g-svg" viewBox="0 0 ${G_ANCHO} ${alto}" role="img"
    aria-label="${esc(titulo)}" preserveAspectRatio="xMidYMid meet">${cuerpo}</svg>`;
}

const gT = (x, y, txt, cls = "") =>
  `<text x="${x}" y="${y}" class="g-t ${cls}">${esc(String(txt))}</text>`;

const gB = (x, y, w, alto, cls) =>
  `<rect x="${x}" y="${y}" width="${Math.max(w, 2)}" height="${alto}" rx="4" class="${cls}"/>`;

/* 1 · Elegí la ventana a conciencia.
   Dos curvas que se cruzan sobre el mismo eje: lo que sube al acortar la
   ventana y lo que baja. Sin escala y sin cifras a proposito — el dibujo
   afirma la FORMA del intercambio, que es cierta siempre, y no un resultado,
   que depende del instrumento, del periodo y de la configuracion de cada uno.
   Los numeros de una corrida nuestra dibujados aca harian creer que la
   aplicacion reparte estrategias ya calculadas. */
function gHistoria() {
  const x0 = 46, x1 = G_ANCHO - 46, y0 = 26, y1 = 96;
  const curva = (subiendo) => {
    const pasos = 24, pts = [];
    for (let i = 0; i <= pasos; i++) {
      const t = i / pasos;
      // una S suave: el intercambio no es una recta, se acelera en el medio
      const e = t * t * (3 - 2 * t);
      pts.push(`${x0 + (x1 - x0) * t},${subiendo ? y1 - (y1 - y0) * e : y0 + (y1 - y0) * e}`);
    }
    return pts.join(" ");
  };
  let out = `<polyline points="${curva(false)}" class="g-curva g-c-ret"/>`;
  out += `<polyline points="${curva(true)}" class="g-curva g-c-ev"/>`;
  out += `<line x1="${x0}" y1="${y1 + 12}" x2="${x1}" y2="${y1 + 12}" class="g-eje"/>`;
  out += gT(x0, y1 + 30, t("g.short_window"), "g-rot");
  out += `<text x="${x1}" y="${y1 + 30}" class="g-t g-rot" text-anchor="end">${
    esc(t("g.long_window"))}</text>`;
  out += gT(x0, y0 - 8, t("g.higher_returns"), "g-cab g-c-ret-t");
  out += `<text x="${x1}" y="${y0 - 8}" class="g-t g-cab g-c-ev-t" text-anchor="end">${
    esc(t("g.more_behind"))}</text>`;
  return lienzo(140, out, t("tip.historia"));
}

/* 2 · El horario cambia todo.
   Arriba la silueta de actividad del dia; abajo las 24 horas con la sesion
   encendida. Sin eje vertical: lo que hay que ver es que el dia no es parejo,
   no cuanto vale cada hora. */
function gHorario() {
  const w = G_ANCHO / 24;
  // perfil tipico de un dia: quieto de madrugada, pico en el solape
  const perfil = [.10,.08,.07,.07,.08,.10,.14,.30,.48,.55,.52,.48,
                  .55,.82,1,.95,.78,.62,.50,.40,.30,.22,.16,.12];
  const base = 74;
  let pts = `${0},${base}`;
  perfil.forEach((v, h) => { pts += ` ${h * w + w / 2},${base - v * 56}`; });
  pts += ` ${G_ANCHO},${base}`;
  let out = gT(0, 14, t("g.day_shape"), "g-cab");
  out += `<polygon points="${pts}" class="g-area"/>`;
  for (let h = 0; h < 24; h++) {
    const dentro = h >= 13 && h < 21;
    out += `<rect x="${h * w}" y="82" width="${w - 2.5}" height="22" rx="3"
      class="g-cel ${dentro ? "on" : ""}"/>`;
    if (h % 6 === 0) out += gT(h * w, 122, `${String(h).padStart(2, "0")}h`, "g-rot");
  }
  out += gT(0, 144, t("g.day_note"), "g-pie");
  return lienzo(154, out, t("tip.horario"));
}

/* 3 · El spread va por instrumento.
   La barra heredada es un hilo de dos píxeles, y ESO es lo que hay que ver: el
   error no se nota porque no se nota. No da ningún aviso, sólo hace que todas
   las estrategias parezcan rentables. A escala real dice más que el párrafo. */
function gSpread() {
  const rot = 200, pista = G_ANCHO - rot - 92;
  let out = gT(0, 14, t("g.btc_cost"), "g-cab");
  out += gT(0, 48, t("g.real_spread"), "g-rot");
  out += gB(rot, 32, pista, G_BARRA, "g-b g-bien");
  out += gT(rot + pista + 8, 48, "12.00", "g-val");
  out += gT(0, 88, t("g.inherited_spread"), "g-rot");
  out += gB(rot, 72, 2, G_BARRA, "g-b g-mal");
  out += gT(rot + 12, 88, "0.00012", "g-val g-mal-t");
  out += gT(0, 118, t("g.spread_note"), "g-pie");
  return lienzo(128, out, t("tip.spread"));
}

/* 4 · Subi la vara de a poco.
   Un embudo: cuanto mas alta la vara, menos candidatas la pasan. Cuantas
   exactamente depende del instrumento y del periodo, asi que el dibujo no
   pone ningun numero — muestra la direccion, que es lo unico que vale
   para cualquiera. */
function gVara() {
  const cols = 9, x0 = 30, paso = (G_ANCHO - 90) / (cols - 1);
  let out = gT(0, 14, t("g.funnel"), "g-cab");
  for (let c = 0; c < cols; c++) {
    const cuantos = Math.max(1, Math.round(9 * (1 - c / (cols - 1)) ** 1.5));
    for (let i = 0; i < cuantos; i++) {
      out += `<circle cx="${x0 + c * paso}" cy="${92 - i * 9}" r="3.2"
        class="g-pt on" opacity="${(1 - c / cols * .55).toFixed(2)}"/>`;
    }
  }
  out += `<line x1="${x0 - 14}" y1="104" x2="${G_ANCHO - 46}" y2="104" class="g-eje"/>`;
  out += gT(x0 - 14, 122, t("g.bar_low"), "g-rot");
  out += `<text x="${G_ANCHO - 46}" y="122" class="g-t g-rot" text-anchor="end">${
    esc(t("g.bar_high"))}</text>`;
  out += gT(0, 144, t("g.funnel_note"), "g-pie");
  return lienzo(154, out, t("tip.vara"));
}

/* 5 · El riesgo escala las dos mitades.
   Dos pares de barras: al triplicar el riesgo, las dos crecen igual. No lleva
   cifras porque la proporcion es una propiedad del tamano de posicion —
   vale para cualquier estrategia —, mientras que los valores concretos
   son de una corrida y no de otra. */
function gRiesgo() {
  const grupo = (x, rot, esc_) => {
    const base = 104, alto = 68 * esc_;
    let out = `<rect x="${x}" y="${base - alto}" width="46" height="${alto}" rx="4"
      class="g-b g-acento"/>`;
    out += `<rect x="${x + 56}" y="${base - alto}" width="46" height="${alto}" rx="4"
      class="g-b g-mal"/>`;
    out += `<text x="${x + 51}" y="126" class="g-t g-rot" text-anchor="middle">${
      esc(rot)}</text>`;
    return out;
  };
  let out = gT(0, 14, t("g.same_shape"), "g-cab");
  out += grupo(70, t("g.risk_base"), 0.34);
  out += grupo(330, t("g.risk_triple"), 1);
  out += `<line x1="40" y1="104" x2="${G_ANCHO - 40}" y2="104" class="g-eje"/>`;
  // la leyenda va una sola vez, arriba a la derecha
  out += `<rect x="${G_ANCHO - 172}" y="26" width="10" height="10" rx="2" class="g-b g-acento"/>`;
  out += gT(G_ANCHO - 157, 35, t("g.legend_return"), "g-rot");
  out += `<rect x="${G_ANCHO - 84}" y="26" width="10" height="10" rx="2" class="g-b g-mal"/>`;
  out += gT(G_ANCHO - 69, 35, t("g.legend_dd"), "g-rot");
  out += gT(0, 146, t("g.scale_note"), "g-pie");
  return lienzo(156, out, t("tip.riesgo"));
}

/* 6 · El reloj de tu broker.
   Dos tiras del mismo dia con el mismo bloque corrido tres horas. Explicar el
   desfase con palabras cuesta un parrafo; verlo corrido se entiende antes de
   leer nada. */
function gZona() {
  const w = G_ANCHO / 24;
  const tira = (y, rot, desde, hasta, alt) => {
    let out = gT(0, y, rot, "g-rot");
    for (let h = 0; h < 24; h++) {
      const dentro = h >= desde && h < hasta;
      out += `<rect x="${h * w}" y="${y + 6}" width="${w - 2.5}" height="24" rx="3"
        class="g-cel ${dentro ? (alt ? "on alt" : "on") : ""}"/>`;
    }
    return out;
  };
  let out = tira(12, t("g.utc_mined"), 13, 16, false);
  out += tira(74, t("g.server_utc3"), 16, 19, true);
  // la flecha va del centro del bloque de arriba al del de abajo
  out += `<path d="M${14.5 * w} 44 L${17.5 * w} 78" class="g-flecha"/>`;
  for (let h = 0; h < 24; h += 6) {
    out += gT(h * w, 122, `${String(h).padStart(2, "0")}h`, "g-rot");
  }
  out += gT(0, 146, t("g.offset_note"), "g-pie");
  return lienzo(158, out, t("tip.zona"));
}

const GRAFICOS = { historia: gHistoria, horario: gHorario, spread: gSpread,
                   vara: gVara, riesgo: gRiesgo, zona: gZona };

const CONSEJOS = () => [
  { id: "historia", ico: "pico", clave: "tip.historia" },
  /* El de las franjas horarias sólo si las franjas están: un consejo sobre
     una perilla que no existe en la pantalla es peor que no tenerlo — manda a
     buscar algo que no se va a encontrar. */
  ...(SESIONES ? [{ id: "horario", ico: "diana", clave: "tip.horario" }] : []),
  /* DOS CONSEJOS SON DE CFD Y NADA MÁS: el del spread por instrumento y el
     del reloj del bróker. En cripto el costo es comisión y funding, y
     Binance habla en UTC; un consejo sobre una perilla que en este mundo no
     existe manda a buscar algo que no se va a encontrar. */
  { id: "spread",   ico: "alerta", clave: "tip.spread", mundo: "metatrader" },
  { id: "vara",     ico: "estrella", clave: "tip.vara" },
  { id: "riesgo",   ico: "baja", clave: "tip.riesgo" },
  { id: "zona",     ico: "info", clave: "tip.zona", mundo: "metatrader" },
];

/* ============================================================ LA ESCALERA ===
   Simulacro -> practica -> real. Los tres destinos de una estrategia, en el
   orden en que se suben, y que le falta para subir al siguiente.

   EL CALCULO NO ESTA ACA. Lo hace `botiquant/cantera.py` y viaja con cada fila
   de /api/strategies bajo la clave `cantera`. Repetir los umbrales en la
   pantalla haria que lo que se ve y lo que el servidor permite puedan
   divergir, que es exactamente el agujero que la cantera vino a tapar.

   POR QUE SE DIBUJA. Hasta ahora la escalera existia unicamente como opciones
   deshabilitadas en un desplegable: habia que elegir una estrategia, abrir el
   menu de modos y leer un renglon en gris para enterarse de que ese destino
   estaba cerrado. Un escalon que solo se ve cuando uno intenta pisarlo no es
   una guia, es un tropiezo — y ademas obliga a entrar a Operar para saber algo
   que es de la estrategia y no del exchange.

   Los rotulos se piden ENTEROS y no armando la clave con el nombre del
   destino: armados asi, el examen de textos ve el prefijo suelto y una clave
   que falte se dibuja en crudo en la pantalla sin que nada avise. */
const PELDANIOS = ["simulacro", "practica", "real"];

function rotuloDestino(d) {
  if (d === "real") return t("esc.real");
  if (d === "practica") return t("esc.practica");
  return t("esc.simulacro");
}

/* Hasta donde llega una estrategia, y cual es el escalon siguiente.

   El tope es el ultimo peldanio CONSECUTIVO que pasa y no el mas alto que
   pasa. Las varas de real son mas duras que las de practica en todas las
   metricas, asi que en la practica no puede haber huecos; pero si alguna vez
   los umbrales se tocan y aparece uno, decir "llega a real" con practica
   cerrada seria contar una escalera a la que le falta un escalon en el medio.

   Simulacro no pide nada —ver el encabezado de cantera.py— asi que lo normal
   es que siempre haya al menos uno. */
function escaleraDe(fila) {
  const c = (fila || {}).cantera || {};
  const pasos = PELDANIOS.map(d => ({
    destino: d,
    /* Sin veredicto —una estrategia guardada por una version anterior, o un
       servidor que no lo manda— NO se da por pasado. Es la misma regla que la
       cantera le aplica a una metrica que nadie midio: la ausencia de
       evidencia no es evidencia. */
    pasa: (c[d] || {}).pasa === true,
    /* `por_que_no` lo escribe el motor y es una frase libre en espaniol,
       igual que los `motivo` del registro del bot. Se muestra igual: es lo
       unico que explica el rechazo, y una frase en el idioma equivocado sigue
       siendo mejor que ninguna. */
    por_que_no: (c[d] || {}).por_que_no || "",
  }));
  let tope = -1;
  for (let i = 0; i < pasos.length && pasos[i].pasa; i++) tope = i;
  return { pasos, tope, siguiente: pasos[tope + 1] || null };
}

/* La escalera en una celda de la tabla: tres barritas y el nombre del ultimo
   escalon alcanzado.

   Las barritas son para barrer la columna con la vista —"cuales de mis
   estrategias podrian ir a real" es una pregunta que se hace mirando la lista
   entera, no una ficha— y el nombre esta al lado para no obligar a nadie a
   descifrar las barritas. Debajo, en chico, lo que falta para el escalon
   siguiente: sin eso la columna dice que no y no dice que hacer. */
function escaleraChip(fila) {
  const e = escaleraDe(fila);
  const nivel = e.tope < 0 ? "none" : PELDANIOS[e.tope];
  return `<div class="esc esc-${nivel}">
    <div class="esc-linea">
      <span class="esc-barras" aria-hidden="true">${
        PELDANIOS.map((d, i) => `<i class="${i <= e.tope ? "on" : ""}"></i>`).join("")}</span>
      <span class="esc-rot">${esc(e.tope < 0 ? t("esc.ninguno")
                                             : rotuloDestino(PELDANIOS[e.tope]))}</span>
    </div>
    ${e.siguiente ? `<div class="esc-falta">${esc(t("esc.falta", {
        destino: rotuloDestino(e.siguiente.destino),
        motivo: e.siguiente.por_que_no || t("esc.falta_sin_motivo"),
      }))}</div>` : ""}
  </div>`;
}

/* La escalera entera, adentro de una estrategia.

   Aca van los TRES escalones con su veredicto y no solo el que falta, porque
   la ficha es donde alguien viene a entender por que su estrategia no puede
   operar todavia. Ver los tres juntos ensenia que las varas suben: lo que
   practica pide con 30 operaciones, real lo pide con 100 y ademas afuera de
   la muestra que la busqueda miro. */
function panelEscalera(ctx) {
  // una fila del banco no tiene destino: todavia no es una estrategia guardada
  if (!ctx || !ctx.strategy_id) return "";
  const e = escaleraDe(ctx);
  const nivel = e.tope < 0 ? "none" : PELDANIOS[e.tope];
  return `<section class="escalera esc-${nivel}">
    <div class="esc-cabeza">
      <div>
        <b>${esc(t("esc.title"))}</b>
        <p class="help-note">${esc(t("esc.sub"))}</p>
      </div>
      <span class="esc-tope">${esc(e.tope < 0 ? t("esc.ninguno")
        : t("esc.hasta", { destino: rotuloDestino(PELDANIOS[e.tope]) }))}</span>
    </div>
    <ol class="esc-pasos">
      ${e.pasos.map((p, i) => `
        <li class="esc-paso ${p.pasa ? "ok" : "mal"}${i === e.tope ? " aqui" : ""}">
          <span class="esc-ic">${icono(p.pasa ? "tilde" : "candado")}</span>
          <b>${esc(rotuloDestino(p.destino))}</b>
          <span>${esc(p.pasa
            ? (p.destino === "simulacro" ? t("esc.libre") : t("esc.habilitada"))
            : (p.por_que_no || t("esc.falta_sin_motivo")))}</span>
        </li>`).join("")}
    </ol>
    <p class="esc-pie">${esc(t("esc.pie"))}</p>
  </section>`;
}


/* ------------------------------------------------------- las piezas de OPERAR

   Los rotulos y la tarjeta del bot. La seccion que los usa esta mas abajo,
   partida en sus dos vistas.

   Las claves de texto se escriben ENTERAS. Armadas pegando el prefijo con el
   modo, el examen de textos ve el prefijo suelto y una que falte se dibuja en
   crudo en la pantalla sin que nada avise. */
/* Las acciones son un conjunto CERRADO —cuatro— y se traducen. Los `motivo`
   no: los escribe el motor y son frases libres en español. Se muestran igual
   porque son lo único que explica por qué el bot hizo lo que hizo, y una
   frase en el idioma equivocado sigue siendo mejor que ninguna. */
/* Lo que escribe el motor, dicho en el idioma de la pantalla. Lo que no se
   reconoce se muestra tal cual: mejor una frase en español que nada. */
/* Por qué se cerró cada operación. El motor escribe "stop", "target",
   "signal", "time" y "end"; en pantalla se dice qué pasó. */
const SALIDAS = () => ({
  stop: t("sal_r.stop"), target: t("sal_r.target"), signal: t("sal_r.signal"),
  time: t("sal_r.time"), end: t("sal_r.end"),
});
function motivoSalida(r) {
  return SALIDAS()[String(r || "")] || r || "";
}

function traducirMotivo(m) {
  const x = String(m || "");
  if (!x) return "";
  if (/^sin señal$/i.test(x)) return t("mot.sin_senal");
  if (/^posición abierta, sin señal de salida/i.test(x)) return t("mot.posicion_sin_salida");
  if (/todavía no hay suficientes velas/i.test(x)) return t("mot.pocas_velas");
  if (/todavía no hay velas cerradas/i.test(x)) return t("mot.sin_velas");
  if (/^sin capital disponible/i.test(x)) return t("mot.sin_capital");
  if (/apagado por el exchange/i.test(x)) return t("mot.apagado_exchange");
  const ad = x.match(/adoptó la posición abierta en \S+ \((larga|corta), ([\d.]+)\)/i);
  if (ad) return t("mot.adopto", { lado: t(ad[1] === "corta" ? "mot.corto" : "mot.largo"), cant: ad[2] });
  const det = x.match(/^detenido: (.*)$/i);
  if (det) return t("mot.detenido", { resto: traducirMotivo(det[1]) });

  /* LO QUE DICE EL PILOTO. El ciclo arma sus motivos como frases sueltas en
     castellano —no hay claves de texto detrás— y en inglés salían crudos:
     "now: 5 sin probar". Se traducen acá, del lado de la pantalla, que es
     donde ya se traduce todo lo demás que dice el motor. Un motivo que no
     coincida con ninguna forma se muestra tal cual, que es lo que pasaba
     antes y no rompe nada. */
  const partes = x.split("; ").map(p => {
    let m = p.match(/^(\d+) sin probar$/i);
    if (m) return t("ciclo.sin_probar", { n: m[1] });
    m = p.match(/^hay (\d+) lugar\(es\) libre\(s\) y (\d+) validada\(s\) esperando$/i);
    if (m) return t("ciclo.hay_lugar", { h: m[1], n: m[2] });
    m = p.match(/^(\d+) instrumento\(s\) ya al tope$/i);
    if (m) return t("ciclo.al_tope", { n: m[1] });
    m = p.match(/^(\d+) que el bot no puede encender$/i);
    if (m) return t("ciclo.inoperables", { n: m[1] });
    m = p.match(/^pasaron (\d+) horas del último minado$/i);
    if (m) return t("ciclo.toca_minar", { h: m[1] });
    m = p.match(/^el próximo minado en (\d+) horas$/i);
    if (m) return t("ciclo.proximo", { h: m[1] });
    if (/^nada que hacer$/i.test(p)) return t("ciclo.nada");
    return p;
  });
  return partes.join("; ");
}

/* UNA CIFRA CON SU REFERENCIA. La ficha de robustez ya ponía un "?" al lado
   de cada número con la frase que dice qué es normal —"1.0 es que sobrevivió
   entero; 0.5 es lo normal y sano"— y era la única pantalla que lo hacía. El
   resto mostraba CAGR, caída, profit factor y Sharpe desnudos: una usuaria de
   prueba que no sabe de trading preguntó "¿+7,59% anual es mucho?" y la
   aplicación no lo decía en ninguna parte (3 de septiembre de 2026). */
function rotuloMetrica(clave) {
  const REF = { "m.cagr": "ref.cagr", "m.dd": "ref.dd", "m.pf": "ref.pf",
                "m.trades": "ref.trades", "m.sharpe": "ref.sharpe",
                "m.winrate": "ref.winrate" };
  const ref = REF[clave];
  return esc(t(clave)) + (ref ? ` <em class="ref" title="${esc(t(ref))}">?</em>` : "");
}

function rotuloAccion(a) {
  if (a === "abrir_largo") return t("bot.acc_largo");
  if (a === "abrir_corto") return t("bot.acc_corto");
  if (a === "cerrar") return t("bot.acc_cerrar");
  if (a === "panico") return t("bot.acc_panico");
  if (a === "nada") return t("bot.acc_nada");
  return a || "—";
}

function rotuloModo(modo) {
  if (modo === "real") return t("bot.modo_real");
  if (modo === "practica") return t("bot.modo_practica");
  return t("bot.modo_simulacro");
}


/* UN BOT EN EL AIRE. Cada uno con su estado y sus botones: apagar "el bot"
   cuando hay cinco no significa nada, y un botón que apaga algo distinto de lo
   que uno está mirando es peor que no tenerlo. */
/* EL ESTADO DE UN ROBOT EN UNA PALABRA: Mirando, En posición o Detenido.
   El servidor dice si la posición es suya; el lado sale de la última acción
   anotada (abrió largo / abrió corto), que es lo único que el registro sabe. */
function estadoRobot(v) {
  if (v.detenido || v.error) return { cls: "parado", txt: t("rob.detenido") };
  if (!v.encendido) return { cls: "parado", txt: t("bot.off") };
  const ultimaAbre = (v.registro || []).find(f => ["abrir_largo", "abrir_corto", "cerrar", "panico"].includes(f.accion));
  /* Una posición ADOPTADA no tiene "abrió" en el registro: el lado se lee
     de la frase de adopción ("larga" / "corta"), que es lo único que hay. */
  const adopcion = (v.registro || []).find(f => /adopt/i.test(String(f.motivo || "")));
  const enPos = v.en_posicion || (ultimaAbre && ultimaAbre.accion.startsWith("abrir")) || !!adopcion;
  if (enPos) {
    const corto = ultimaAbre ? ultimaAbre.accion === "abrir_corto"
      : /cort/i.test(String((adopcion || {}).motivo || ""));
    return { cls: "en-pos", txt: t("rob.en_posicion", { lado: corto ? t("rob.corto") : t("rob.largo") }) };
  }
  return { cls: "mirando", txt: t("rob.mirando") };
}

/* Un porcentaje que se puede sumar: entero si lo es, con un decimal si no. */
function pctExacto(x) {
  const r = Math.round(x * 10) / 10;
  return Number.isInteger(r) ? String(r) : fmtNum(r, 1);
}

function tarjetaVuelo(v) {
  const detenido = v.detenido || v.error;
  const est = estadoRobot(v);
  return `
  <div class="bot-vuelo robot ${est.cls}${v.encendido ? " vivo" : ""}">
    <div class="bot-linea">
      <span><b>${esc(v.nombre || "—")}</b> · ${esc(v.simbolo || "")} ${esc(v.timeframe || "")}</span>
      <span class="robot-estado ${est.cls}">${esc(est.txt)}</span>
    </div>
    <div class="robot-modo">${esc(rotuloModo(v.modo))}</div>
    ${v.riesgo_pct != null ? `<p class="help-note bot-riesgo">${esc(t("bot.riesgo", {
        pct: fmtNum(v.riesgo_pct, 1),
        usdt: fmtNum((S.cuentaSaldo || 0) * (v.porcion || 1) * (v.riesgo_pct / 100), 2),
        tope: v.tope_diario > 0 ? fmtNum(v.tope_diario, 2) + " USDT" : t("bot.sin_tope") }))}</p>` : ""}
    ${/* Con un decimal cuando lo necesita: ocho robots al 10,6% redondeados a
          11 sumaban 88% contra el 85% del pie, y no había forma de saber cuál
          de los dos mentía (3 de septiembre). */ ""}
    <p class="help-note">${esc(t("bot.maneja", { pct: pctExacto((v.porcion || 1) * 100) }))}${
      v.esperado_mes ? " · " + esc(t("bot.esperado_mes", { n: v.esperado_mes })) : ""}${
      v.encendido && v.timeframe ? " · " + esc(t("bot.proxima", { h: proximaVela(v.timeframe) })) : ""}</p>

    ${(v.vigilante || {}).estado === "amarillo" ? `<div class="bot-alerta mt">
      <span class="g-ic">${icono("alerta")}</span>
      <span><b>${esc(t("bot.vig_titulo"))}</b> ${esc(v.vigilante.razon)}</span>
    </div>` : ""}

    ${detenido ? `<div class="bot-alerta mt">
      <span class="g-ic">${icono("alerta")}</span>
      <span>${esc(v.motivo_detencion || v.error || "")}</span>
    </div>` : ""}

    ${(v.registro || []).length ? `
    <div class="bot-registro mt">
      ${/* SÓLO LO QUE PASÓ, y la última vuelta: el robot mira cada cinco
            minutos y anotaba "esperó · sin señal" cinco veces seguidas; se ve
            la última espera y todas las acciones. Hora local, como la vela. */
        [...v.registro.filter(f => f.accion && f.accion !== "nada").slice(0, 4),
         ...(v.registro[0] && v.registro[0].accion === "nada" ? [v.registro[0]] : [])]
        .sort((a, b) => String(b.cuando).localeCompare(String(a.cuando))).map(f => `
        <div class="bot-fila">
          <span class="bot-hora">${esc(horaLocal(f.cuando))}</span>
          <span class="bot-que">${esc(rotuloAccion(f.accion))}</span>
          <span class="bot-det">${esc(traducirMotivo(f.bloqueado || f.error || f.motivo || ""))}</span>
        </div>`).join("")}
    </div>` : ""}

    ${v.encendido ? `
    <div class="controls mt">
      <button class="btn ghost" data-apagar="${esc(v.simbolo)}">${esc(t("bot.apagar"))}</button>
      <button class="btn danger" data-panico="${esc(v.simbolo)}">${esc(t("bot.panico"))}</button>
    </div>` : ""}
  </div>`;
}

/* Cuándo cierra la próxima vela de ese timeframe, en hora local. Es lo que
   convierte "hace rato que no hace nada" de una duda en un dato: el bot
   decide UNA vez por vela, y acá dice cuándo es la próxima. */
function proximaVela(tf) {
  const seg = { "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                "1h": 3600, "4h": 14400, "1d": 86400 }[tf] || 3600;
  const ahora = Date.now() / 1000;
  const prox = new Date((Math.floor(ahora / seg) + 1) * seg * 1000);
  return prox.toLocaleTimeString(localeNum(), HORA());
}

/* La hora, atada al idioma y no al navegador: en español se lee "20:00" y
   en inglés "08:00 PM". El locale solo no alcanza —Chrome pone "p. m."
   también en es-AR— así que el ciclo de horas se pide explícito. */
function HORA(mas) {
  return Object.assign({ hour: "2-digit", minute: "2-digit",
                         hour12: idioma() !== "es" }, mas || {});
}

/* LA ZONA DE VUELOS, SEPARADA DEL RESTO DEL PANEL. Es lo unico que cambia
   mientras el bot opera, asi que es lo unico que el refresco redibuja: el
   formulario de abajo —con lo que el usuario haya elegido a medio armar— no
   se toca nunca. */
function zonaVuelos(e) {
  const vuelos = e.vuelos || [];
  const libre = typeof e.porcion_libre === "number" ? e.porcion_libre : 1;
  /* LAS PROMOVIDAS QUE QUEDARON SIN ROBOT van acá, en ámbar, entre los
     robots: son robots que faltan, no una nota al pie. Pasa cada vez que la
     aplicación se cierra —mueren con el proceso— y se reencienden con un
     clic, uno para todas. */
  const apagadas = e.apagadas || [];
  const tarjetasApagadas = apagadas.map(a => `
    <div class="bot-vuelo robot apagada">
      <div class="bot-linea">
        <span><b>${esc(a.name || "—")}</b> · ${esc(a.simbolo || "")}</span>
        <span class="robot-estado apagada">${esc(t("ag.apagada"))}</span>
      </div>
      <p class="help-note">${esc(t("ag.apagadas_sub"))}</p>
    </div>`).join("");
  return `
    ${vuelos.length || apagadas.length ? `<div class="robots">${vuelos.map(tarjetaVuelo).join("")}${tarjetasApagadas}</div>` : ""}
    ${apagadas.length ? `<div class="controls mt">
      <button class="btn" id="ag-reencender">${esc(t("ag.reencender", { n: apagadas.length }))}</button>
    </div>` : ""}
    ${vuelos.length ? `
    <p class="help-note mt">${esc(t("bot.reparto", {
      usado: Math.round((e.porcion_usada || 0) * 100),
      libre: Math.round(libre * 100) }))}</p>
    ${e.cuantos > 1 ? `<div class="controls mt">
      <button class="btn ghost" id="bot-apagar-todos">${esc(t("bot.apagar_todos"))}</button>
    </div>` : ""}
    <p class="help-note mt">${esc(t("bot.apagar_nota"))}</p>` : ""}`;
}

function atarVuelos(main) {
  $$("[data-apagar]", main).forEach(b => {
    b.onclick = async () => {
      b.disabled = true;
      b.innerHTML = `<span class="spinner"></span>${esc(t("bot.apagando"))}`;
      try {
        await api.post("/api/bot/apagar", { simbolo: b.dataset.apagar });
        toast(t("bot.apagado"), "ok");
        await navigate("operar");
      } catch (e) {
       toast(e.message, "err"); }
      b.disabled = false;
    };
  });
  $$("[data-panico]", main).forEach(b => {
    b.onclick = async () => {
      if (!confirm(t("bot.panico_seguro"))) return;
      b.disabled = true;
      try {
        const r = await api.post("/api/bot/panico", { simbolo: b.dataset.panico });
        toast(t("bot.panico_hecho"), "ok");
        await navigate("operar");
        if (r && r.cerrado) console.info("[bot] pánico:", r.cerrado);
      } catch (e) {
       toast(e.message, "err"); }
      b.disabled = false;
    };
  });
  const todos = $("#bot-apagar-todos", main);
  if (todos) todos.onclick = async () => {
    todos.disabled = true;
    try {
      await api.post("/api/bot/apagar", {});
      toast(t("bot.apagado"), "ok");
      await navigate("operar");
    } catch (e) {
       toast(e.message, "err"); }
    todos.disabled = false;
  };
}

/* ---- la franja de agentes: qué está haciendo cada uno AHORA ----

   Es lo primero que se ve al entrar a Operar, y responde "¿está haciendo
   algo?" antes de que haya que leer un registro: una fila por agente —el
   ciclo primero, después cada bot— con un punto que late mientras trabaja y
   la última decisión de cada uno en una línea.

   EL CICLO NO TENÍA PANTALLA. Minaba, validaba y encendía bots por su cuenta
   y la única forma de saberlo era la API: alguien podía ver aparecer un bot
   que no encendió y no tener dónde mirar por qué. Acá se ve, y se apaga. */
function rotuloCiclo(a) {
  if (a === "validar") return t("ag.acc_validar");
  if (a === "promover") return t("ag.acc_promover");
  if (a === "minar") return t("ag.acc_minar");
  if (a === "retirar") return t("ag.acc_retirar");
  return t("ag.acc_nada");
}

function horaLocal(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString(localeNum(), HORA());
}

function zonaAgentes(e, c) {
  return zonaPiloto(c);
}


function atarReencender(main) {
  const b = $("#ag-reencender", main);
  if (!b) return;
  b.onclick = async () => {
    b.disabled = true;
    try {
      const r = await api.post("/api/bot/reencender", {});
      if ((r.fallos || []).length) {
        toast(t("ag.reencender_fallo", { n: r.fallos.length,
                                          motivo: r.fallos[0].motivo || "" }), "err");
      } else {
        toast(t("ag.reencendidas"), "ok");
      }
      await navigate("operar");
    } catch (err) { toast(err.message, "err"); }
    b.disabled = false;
  };
}

/* EL PILOTO AUTOMÁTICO, con nombre de usuario. Antes era "el ciclo" dentro
   de una franja de "agentes" donde robots y ciclo eran renglones iguales; no
   se entendía qué hacía ni qué había hecho. Ahora es una tarjeta sola: un
   interruptor, qué está por hacer, sus reglas en castellano y una línea de
   tiempo con lo último que hizo. Los robots viven abajo, en su grilla. */
function panelAgentes(e, c) {
  if (!c) return "";
  return `
  <div class="card piloto" id="ag-zona">${zonaAgentes(e, c)}</div>`;
}

function zonaPiloto(c) {
  const p = (c && c.params) || {};
  const cicloOn = !!(c && c.corriendo && p.encendido);
  const prox = (c && c.proxima) || {};
  const ultimas = ((c && c.registro) || []).slice(0, 5);
  const reglas = t("pil.reglas", { h: p.minar_cada_horas ?? 12, n: p.max_en_practica ?? 8 });
  // la copia editable nace de lo que dice el servidor, una sola vez
  if (!PILOTO_PARAMS && Object.keys(p).length) PILOTO_PARAMS = { ...p };
  return `
    <div class="ex-head">
      <div>
        <b>${esc(t("ag.titulo"))}</b>
        <p class="help-note">${esc(t("ag.ciclo_sub"))}</p>
      </div>
      <span class="ex-estado ${cicloOn ? "on" : ""}">${esc(cicloOn ? t("ag.corriendo") : t("ag.apagado"))}</span>
    </div>
    <div class="piloto-cuerpo">
      <div class="piloto-ahora">
        <span class="ag-punto${cicloOn ? " vivo" : ""}${c.error ? " alerta" : ""}"></span>
        <div>
          <div class="ag-quien">${esc(c.error ? c.error
            : cicloOn ? t("ag.ahora") + ": " + traducirMotivo(prox.motivo || "")
            : t("ag.ciclo_apagado"))}</div>
          <div class="ag-que">${esc(reglas)}</div>
        </div>
        <div class="ag-lado">
          <button class="btn ${cicloOn ? "ghost" : ""}" id="ag-ciclo" data-encender="${cicloOn ? "0" : "1"}">${
            esc(cicloOn ? t("ag.ciclo_off") : t("ag.ciclo_on"))}</button>
        </div>
      </div>
      ${explicacionHTML("piloto", PASOS_PILOTO(), { ciclico: true, panel: panelPiloto })}
      <div class="piloto-linea">
        <b>${esc(t("pil.ultimas"))}</b>
        ${ultimas.length ? `<ol>${ultimas.map(u => `<li>
          <span class="ag-hora">${esc(horaLocal(u.cuando))}</span>
          <span class="pil-acc pil-${esc(u.accion || "nada")}">${esc(rotuloCiclo(u.accion))}</span>
          <span class="ag-que">${esc(traducirMotivo(u.motivo || ""))}</span></li>`).join("")}</ol>`
        : `<p class="help-note">${esc(t("pil.nada"))}</p>`}
      </div>
    </div>`;
}

/* El interruptor del ciclo se vuelve a atar en cada refresco, porque la zona
   se redibuja entera. Manda TODOS los parámetros y no sólo el interruptor:
   el servidor reemplaza el juego completo, y mandar uno solo devolvería los
   demás a sus valores por defecto sin que nadie lo pidiera. */
function atarCiclo(main, c) {
  // los parámetros que muestra el servidor son la base; lo editado y no
  // guardado se conserva entre refrescos porque vive en PILOTO_PARAMS
  if (!PILOTO_PARAMS && c && c.params) PILOTO_PARAMS = { ...c.params };
  atarExplicacion(main, "piloto", PASOS_PILOTO(), { ciclico: true, panel: panelPiloto, alPintar: atarPanelPiloto });
  const b = $("#ag-ciclo", main);
  if (!b) return;
  b.onclick = async () => {
    const encender = b.dataset.encender === "1";
    b.disabled = true;
    try {
      await api.post("/api/ciclo/params",
                     Object.assign({}, (c && c.params) || {}, PILOTO_PARAMS || {}, { encendido: encender }));
      toast(t(encender ? "ag.ciclo_encendido" : "ag.ciclo_apagado"), "ok");
      await navigate("operar");
    } catch (err) { toast(err.message, "err"); }
    b.disabled = false;
  };
}

function panelBot(e, hayClave) {
  const on = e.encendido;
  const hc = hayClave || {};
  /* BINANCE ES EL EXCHANGE POR DEFECTO: es el único que la aplicación opera
     hoy (en demo). BingX sólo se preselecciona si es el único con clave. */
  const casaInicial = (((hc.bingx || {}).practica || (hc.bingx || {}).real)
                       && !(hc.binance || {}).practica)
    ? "bingx" : "binance";
  /* SOLO las estrategias minadas sobre un perpetuo. Un exchange de cripto no
     opera el S&P ni el oro: encender una de esas mandaria un simbolo que
     BingX no conoce, y el error llegaria recien al intentar operar. Se filtra
     por la FUENTE del dataset y no por el nombre, que alguien puede cambiar. */
  const cripto = new Set((S.datasets || [])
    .filter(d => d.source === "binance").map(d => d.id));
  /* Y TAMPOCO SE OFRECEN LAS QUE EL BOT SE NIEGA A OPERAR.
     Una estrategia con stop dinamico (trailing) se rechaza al encender: el
     motor mueve el stop cada vela y el bot deja UNA orden puesta en el
     exchange, asi que operaria algo distinto de lo que se midio. El rechazo
     esta bien; ofrecerla no. Suelta se veia como un error al apretar Start, y
     adentro de un conjunto era peor: encendia dos, fallaba en la tercera y
     dejaba el conjunto a medias. */
  const operables = (S.saved || []).filter(
    x => cripto.has((x.meta || {}).dataset_id)
      && !(((x.spec || {}).risk || {}).trail_atr > 0)
      /* Y NO LAS RETIRADAS. El cementerio existe para no volver a encender lo
         que ya se sabe que no sirve, y retirar EXIGE un motivo justamente por
         eso — ofrecerlas de nuevo en el desplegable tiraba ese trabajo a la
         basura. Hoy no aparecían de casualidad: las retiradas que hay son de
         históricos borrados, así que el filtro del instrumento las tapaba. */
      && !estaRetirada(x));
  const vuelos = e.vuelos || [];
  const libre = typeof e.porcion_libre === "number" ? e.porcion_libre : 1;
  /* HAY LUGAR SI SOBRA CUPO Y SOBRA CUENTA. Ofrecer el formulario sin una de
     las dos cosas es dejar que alguien arme un bot entero para que el servidor
     lo rechace al final. */
  const hayLugar = vuelos.filter(v => v.encendido).length < (e.maximo || 8)
                   && libre > 0.001;
  return `
  <div class="card bot-card${on ? " bot-on" : ""}">
    <div class="ex-head">
      <div>
        <b>${esc(t("rob.titulo"))}</b>
        <p class="help-note">${esc(t("bot.sub"))}</p>
      </div>
      <span class="ex-estado ${on ? "on" : ""}">${
        esc(on ? t("bot.n_operando", { n: e.cuantos }) : t("bot.off"))}</span>
    </div>

    <div id="bot-zona-vuelos">${zonaVuelos(e)}</div>

    ${!hayLugar ? `
    <div class="empty-state mt">
      <b>${esc(t("bot.sin_lugar"))}</b>
      <p class="mt">${esc(t("bot.sin_lugar_sub"))}</p>
    </div>` : `
    ${!operables.length ? `
    <div class="empty-state mt">
      <b>${esc(t("bot.sin_cripto"))}</b>
      <p class="mt">${esc(t("bot.sin_cripto_sub"))}</p>
    </div>` : `
    <div class="fld-pair mt">
      <label class="fld"><span>${esc(t("bot.estrategia"))}</span>
        <select id="bot-cual">
          <option value="">${esc(t("bot.elegir"))}</option>
          ${operables.map(x =>
            `<option value="${esc(x.id)}" ${PREELEGIDA === x.id ? "selected" : ""}>${esc(x.name)} · ${
              esc(String((x.meta || {}).dataset_name || "").split(" ")[0])}</option>`).join("")}
        </select></label>
      <label class="fld"><span>${esc(t("bot.tope"))}</span>
        <input type="number" id="bot-tope" min="0" step="1" value="0"
               placeholder="0"></label>
    </div>
    <p class="help-note">${esc(t("bot.tope_nota"))}</p>
    <div class="fld-pair mt">
      <!-- QUE PORCION DE LA CUENTA. Se ofrece lo que queda libre, no el 100%:
           el default tiene que ser algo que entre. -->
      <label class="fld"><span>${esc(t("bot.porcion"))}</span>
        <input type="number" id="bot-porcion" min="1" max="100" step="1"
               value="${Math.round(libre * 100)}"></label>
    </div>
    <p class="help-note">${esc(t("bot.porcion_nota"))}</p>
    <div class="fld-pair mt">
      <!-- EN QUE CASA. Se elige y no se deduce del simbolo: BingX pide
           BTC-USDT y Binance BTCUSDT, y adivinar por el guion convertiria un
           error de tipeo en una orden al exchange equivocado. -->
      <label class="fld"><span>${esc(t("bot.casa"))}</span>
        ${/* ARRANCA EN LA CASA QUE TIENE CLAVE. Con la única clave cargada
              en Binance, el desplegable abría en BingX y el modo decía "sin
              clave": el usuario tenía que adivinar que había que cambiar de
              casa antes de elegir el modo. Si hay clave en las dos, o en
              ninguna, queda BingX como antes. */ ""}
        ${/* Un solo exchange operable: se muestra como dato, no como
              elección. El <select> queda oculto porque el resto del panel
              lee su valor. */ ""}
        <select id="bot-casa" hidden>
          <option value="binance" selected>${esc(t("bot.casa_binance"))}</option>
        </select>
        <span class="fld-fijo">${esc(t("bot.casa_binance"))} · ${esc(t("bot.solo_demo"))}</span></label>
      <label class="fld"><span>${esc(t("bot.modo"))}</span>
        <select id="bot-modo">
          <option value="">${esc(t("bot.elegir"))}</option>
          <option value="simulacro">${esc(t("bot.modo_simulacro"))}</option>
          <option value="practica">${esc(t("bot.modo_practica"))}</option>
          <option value="real">${esc(t("bot.modo_real"))}</option>
        </select></label>
    </div>
    <p class="help-note" id="bot-casa-nota" hidden></p>
    <p class="bot-porque" id="bot-porque" hidden></p>
    <!-- Lo esconde y lo muestra revisarDestinos: sale SOLO cuando lo que
         falta es la clave. El motivo de arriba puede venir de la cantera, y
         para eso el atajo no sirve de nada. -->
    <button class="linkbtn" id="bot-ir-claves" hidden>${
      esc(t("op.ir_claves"))}</button>
    <div class="controls mt">
      <button class="btn" id="bot-encender">${esc(t("bot.encender"))}</button>
    </div>`}`}

    ${operables.length >= 2 && hayLugar ? `
    <!-- EL CONJUNTO. Elegir varias, ver el PLAN antes de tocar nada -mismo
         principio que el ciclo: decidir separado de hacer- y recien ahi
         encender. Las expectativas salen del backtest de cada una y la
         pantalla lo dice: son una expectativa, no una promesa. -->
    <div class="conj mt" id="conjunto">
      <div class="ex-head">
        <div>
          <b>${esc(t("conj.titulo"))}</b>
          <p class="help-note">${esc(t("conj.sub"))}</p>
        </div>
      </div>
      <div class="conj-lista mt">
        ${operables.map(x => {
          const m = ((x.meta || {}).metrics) || {};
          return `<label class="conj-item">
            <input type="checkbox" data-conj="${esc(x.id)}">
            <span class="conj-nom"><b>${esc(x.name)}</b> · ${
              esc(String((x.meta || {}).dataset_name || "").split(" ")[0])} ${
              esc((x.meta || {}).timeframe || "")}</span>
            <span class="conj-met">${m.trades_per_month
              ? esc(t("conj.ops_cortas", { n: fmtNum(m.trades_per_month, 1) })) : ""}${
              (x.meta || {}).score != null ? " · score " + Math.round(x.meta.score) : ""}</span>
          </label>`;
        }).join("")}
      </div>
      <!-- SU PROPIO EXCHANGE Y NO EL DEL FORMULARIO DE ARRIBA. Heredarlo
           parecia ahorrar un control y era un error: ese selector arranca en
           BingX, asi que un conjunto armado sin tocarlo se mandaba a un
           exchange sin clave y fallaba tres veces seguidas con un 400 que la
           pantalla no explicaba. Se elige acá, como todo lo demás. -->
      <div class="fld-pair mt">
        <label class="fld"><span>${esc(t("bot.casa"))}</span>
          <select id="conj-casa" hidden>
            <option value="binance">${esc(t("bot.casa_binance"))}</option>
          </select>
          <span class="fld-fijo">${esc(t("bot.casa_binance"))} · ${esc(t("bot.solo_demo"))}</span></label>
      </div>
      <div class="controls mt">
        <button class="btn ghost" id="conj-armar">${esc(t("conj.armar"))}</button>
      </div>
      <div id="conj-plan" hidden></div>
    </div>` : ""}
  </div>`;
}

/* El plan dibujado: las cuatro expectativas como fichas, el detalle por bot,
   y los avisos del reparto. */
function planConjuntoHTML(plan) {
  const e = plan.esperado || {};
  const ficha = (rot, valor) => `<div class="conj-stat">
    <span>${esc(rot)}</span><b>${valor}</b></div>`;
  return `
    <div class="conj-stats mt">
      ${ficha(t("conj.retorno"), (e.retorno_anual_pct >= 0 ? "+" : "")
              + fmtNum(e.retorno_anual_pct, 1) + "%")}
      ${ficha(t("conj.ops"), fmtNum(e.ops_mes, 1))}
      ${e.win_rate_pct != null ? ficha(t("conj.wr"), fmtNum(e.win_rate_pct, 1) + "%") : ""}
      ${e.peor_dd ? ficha(t("conj.dd"), fmtNum(e.peor_dd.dd_pct, 0) + "% · " + esc(e.peor_dd.nombre)) : ""}
    </div>
    <p class="help-note">${esc(t("conj.fuente"))}</p>
    <div class="conj-detalle mt">
      ${(plan.detalle || []).map(d => `
        <div class="bot-fila">
          <span class="bot-que"><b>${esc(d.nombre)}</b> · ${esc(d.instrumento.split(" ")[0])}</span>
          <span>${Math.round(d.porcion_pct)}%</span>
          <span class="bot-det">PF ${fmtNum(d.pf, 2)} · ${fmtNum(d.ops_mes, 1)} ops/mes · DD ${fmtNum(d.dd_pct, 0)}%</span>
        </div>`).join("")}
    </div>
    ${(plan.avisos || []).map(a => `<div class="bot-alerta mt">
      <span class="g-ic">${icono("alerta")}</span><span>${esc(a.texto)}</span>
    </div>`).join("")}
    <div class="controls mt">
      <button class="btn" id="conj-encender">${esc(t("conj.encender"))}</button>
    </div>`;
}


/* ------------------------------------------------------------------ OPERAR

   El ultimo paso del flujo, y la seccion donde se hacen DOS cosas de
   frecuencia muy distinta. Estaban una debajo de la otra en la misma pagina:

     * cargar la clave de API se hace UNA vez, y ojala nunca mas;
     * encender y apagar el bot se hace seguido, y es lo que alguien abre
       cuando quiere saber si hay algo operando.

   Poner lo de una sola vez arriba de lo de todos los dias obliga a pasar por
   un formulario de claves —el momento de mas confianza de toda la aplicacion,
   con dos campos de contrasenia— cada vez que uno quiere mirar el bot. Y al
   reves tambien es cierto: quien viene a cargar una clave no tiene por que
   pasar por un boton de encender.

   Se separan en dos vistas de la MISMA seccion, igual que el databank adentro
   de Minado. No es una entrada nueva del menu: son las dos mitades de la misma
   tarea, y el menu no puede crecer cada vez que una pantalla tiene dos cosas
   adentro.

   El bot es la vista de arranque porque es la que se abre seguido. */
PAGES.operar = async (main) => {
  const vista = ["claves", "tablero", "piloto"].includes(S.vistaOperar)
    ? S.vistaOperar : "bot";
  const estado = await api.get("/api/exchanges");
  /* POR EXCHANGE Y ENTORNO, no sólo por entorno. Indexado por entorno solo,
     la fila de Binance práctica PISABA a la de BingX práctica: la tarjeta de
     BingX mostraba la clave del otro como propia, y el selector de modo creía
     que había clave donde no la había. Con un solo exchange el atajo era
     inocuo; con dos era una mentira en pantalla. */
  const por = {};
  estado.forEach(x => { por[`${x.exchange}-${x.entorno}`] = x; });
  const hayClave = {
    bingx: { practica: !!(por["bingx-practica"] || {}).configurada,
             real: !!(por["bingx-real"] || {}).configurada },
    binance: { practica: !!(por["binance-practica"] || {}).configurada,
               real: false },     // Binance no tiene real: sólo demo
  };
  /* Un punto en la pestania cuando no hay NINGUNA clave cargada. Sin eso,
     alguien que entra por primera vez cae en la vista del bot, no puede
     encender nada mas alla del simulacro y no tiene por que adivinar que lo
     que le falta vive en la otra pestania. */
  const sinClaves = !Object.values(hayClave)
    .some(x => x.practica || x.real);

  /* TRES PESTAÑAS CON UNA SOLA PREGUNTA: qué está corriendo y cómo le va.
     La cuenta se conecta desde el menú (abajo, "Cuenta Binance") y se
     muestra acá sólo cuando se llega a ella. */
  /* SIN PESTAÑAS. Operar es una sola pantalla; la cuenta, el detalle y el
     automático son vistas secundarias con un "← Operar" para volver. */
  main.innerHTML = `${vista !== "bot" && vista !== "piloto" ? `<div class="vistas volver"><button class="linkbtn" data-vista="bot">${esc(t("op.volver"))}</button></div>` : ""}
    <div id="vista-host"></div>`;

  $$("[data-vista]", main).forEach(b => b.onclick = () => {
    S.vistaOperar = b.dataset.vista;
    navigate("operar");
  });

  const host = $("#vista-host", main);
  await (vista === "claves" ? vistaClaves(host, por)
         : vista === "tablero" ? vistaTablero(host, hayClave)
         : vista === "piloto" ? vistaPiloto(host)
         : vistaBot(host, hayClave));
  acomodarVistas(main, host);
};


/* ---- vista 1: el bot. Encenderlo, mirarlo y apagarlo ----

   EL MODO SE ELIGE CADA VEZ y no se recuerda. Recordar "real" y que alcance
   con apretar encender es exactamente el clic de mas que este proyecto viene
   evitando en todas las pantallas. */
const vistaBot = async (main, hayClave) => {
  /* UNA SOLA PANTALLA, TRES BLOQUES, DE ARRIBA A ABAJO: tu cuenta, encender
     una, corriendo. Sin pestañas, sin modo, sin porción, sin tope: demo
     siempre y la porción repartida. Quien quiera afinar lo hace desde la
     tarjeta del robot. El Piloto vive aparte, en Ajustes. */
  const [bot, ciclo] = await Promise.all([
    api.get("/api/bot"), api.get("/api/ciclo").catch(() => null)]);
  await refreshSavedCount();
  if (!(S.datasets || []).length) await refreshDatasets();

  if (S.mundo === "metatrader") {
    main.innerHTML = pageHead(t("nav.operar"), esc(t("op.sub_bot")))
      + `<div class="card ex-aviso"><p class="help-note">${esc(t("op.cfd_nota"))}</p></div>`;
    return;
  }
  if (!hayClave.binance.practica) {
    main.innerHTML = pageHead(t("nav.operar"), esc(t("op.sub_bot"))) + `
      <div class="card conectar">
        <div class="empty-state">
          <div class="big">${icono("candado", "ico-xl")}</div>
          <b>${esc(t("op.conectar_t"))}</b>
          <p class="mt">${esc(t("op.conectar_sub"))}</p>
          <button class="btn mt" id="ir-conectar">${esc(t("op.conectar_btn"))}</button>
        </div>
      </div>`;
    $("#ir-conectar", main).onclick = () => navigate("operar", "claves");
    return;
  }

  const cripto = new Set((S.datasets || []).filter(d => d.source === "binance").map(d => d.id));
  const aprobadas = (S.saved || []).filter(x => etapaDe(x) === "aprobadas"
    && cripto.has((x.meta || {}).dataset_id)
    && !(((x.spec || {}).risk || {}).trail_atr > 0));
  const operando = (bot.vuelos || []).length + (bot.apagadas || []).length;

  main.innerHTML = pageHead(t("nav.operar"), esc(t("op.sub_bot"))) + `
    <div class="card cuenta-linea" id="op-cuenta">
      <div class="ex-head"><div><b>${esc(t("op.cuenta_t"))}</b>
        <p class="help-note"><i class="esq esq-linea" aria-label="${esc(t("tab.cargando"))}"></i></p>
        <p class="historia"></p></div>
        <button class="linkbtn" id="op-detalle">${esc(t("op.detalle"))}</button></div>
    </div>

    <div class="card mt" id="op-encender">
      <div class="ex-head"><div><b>${esc(t("op.encender_t"))}</b>
        <p class="help-note">${esc(t("op.encender_sub"))}</p></div></div>
      ${aprobadas.length ? `<div class="fld-pair mt">
        <label class="fld"><span>${esc(t("bot.estrategia"))}</span>
          <select id="bot-cual">
            <option value="">${esc(t("op.elegir_aprobada"))}</option>
            ${aprobadas.map(x => `<option value="${esc(x.id)}" ${PREELEGIDA === x.id ? "selected" : ""}>${
              esc(x.name)} · ${esc(String((x.meta || {}).dataset_name || "").split(" ")[0])}</option>`).join("")}
          </select></label>
        <div class="fld"><span>&nbsp;</span><button class="btn" id="bot-encender">${icono("seguir")} ${esc(t("op.encender_btn"))}</button></div>
      </div>` : `<p class="help-note mt">${esc(t("op.sin_aprobadas"))} <button class="linkbtn" id="op-ir-probar">${esc(t("nav.saved"))}</button></p>`}
    </div>

    <div class="card mt">
      <div class="ex-head"><div><b>${esc(t("op.corriendo_t"))}</b>
        <p class="help-note">${esc(t("bot.sub"))}</p></div>
        <span class="ex-estado ${operando ? "on" : ""}">${esc(operando ? t("bot.n_operando", { n: bot.cuantos }) : t("bot.off"))}</span></div>
      <div id="bot-zona-vuelos">${operando ? zonaVuelos(bot) : `<p class="help-note">${esc(t("op.nada_corriendo"))}</p>`}</div>
    </div>`;

  $("#op-detalle", main).onclick = () => navigate("operar", "tablero");
  const irP = $("#op-ir-probar", main); if (irP) irP.onclick = () => navigate("saved", "aprobadas");
  const btnEnc = $("#bot-encender", main);
  if (btnEnc) btnEnc.onclick = () => {
    const id = ($("#bot-cual", main) || {}).value;
    if (!id) return toast(t("bot.falta_elegir"), "err");
    PREELEGIDA = null;
    encenderDirecto(aprobadas.find(x => x.id === id), btnEnc);
  };
  atarVuelos(main);
  atarReencender(main);

  // la cuenta, en una línea: saldo, resultado neto y posiciones abiertas
  (async () => {
    const caja = $("#op-cuenta", main);
    if (!caja) return;
    try {
      const d = await api.get("/api/cuenta/rendimiento");
      /* EL SALDO LLEGA DESPUÉS QUE LAS TARJETAS: sin repintar, la línea de
         riesgo decía "≈ 0.00 USDT". Se vuelven a dibujar con el saldo ya
         sabido, una sola vez. */
      S.cuentaSaldo = +d.saldo || 0;
      const r = d.resultado || {};
      const signo = n => (n > 0 ? "pos" : n < 0 ? "neg" : "");
      $(".help-note", caja).innerHTML = `<span class="cuenta-dato">${esc(t("op.saldo"))} <b data-cifra="${+d.saldo || 0}" data-formato="usdt">0</b></span>
        <span class="cuenta-dato">${esc(t("op.neto"))} <b class="${signo(r.neto)}" data-cifra="${+r.neto || 0}" data-formato="usdt_signo">0</b></span>
        <span class="cuenta-dato">${esc(t("op.abiertas"))} <b data-cifra="${(d.posiciones || []).length}" data-formato="int">0</b></span>`;
      animarCifras(caja);
      /* Y RECIÉN AHORA los robots. Este pedido va al exchange y tarda; hacerlo
         antes dejaba saldo, resultado y posiciones en cero durante siete
         segundos, con la frase de abajo ya diciendo los valores de verdad. */
      const zonaR = $("#bot-zona-vuelos", main);
      if (zonaR && (bot.vuelos || []).length) {
        const fresco = await api.get("/api/bot");
        zonaR.innerHTML = zonaVuelos(fresco); atarVuelos(main); atarReencender(main);
      }
      /* LA HISTORIA EN UNA FRASE. Un tablero quieto no dice qué pasó; una
         frase con los mismos números sí. El mejor símbolo sale de las
         operaciones cerradas, si hay. */
      const cerradas = d.cerradas || [];
      const porSim = {};
      cerradas.forEach(c => { porSim[c.simbolo] = (porSim[c.simbolo] || 0) + (+c.pnl || 0); });
      const mejor = Object.entries(porSim).sort((a, b) => b[1] - a[1])[0];
      $(".historia", caja).textContent = d.cuantas_cerradas
        ? t("op.historia", { n: fmtInt(d.cuantas_cerradas), neto: (r.neto > 0 ? "+" : "") + fmtNum(r.neto, 2),
                              abiertas: fmtInt((d.posiciones || []).length),
                              mejor: mejor ? t("op.historia_mejor", { sim: mejor[0], pnl: (mejor[1] > 0 ? "+" : "") + fmtNum(mejor[1], 2) }) : "" })
        : t("op.historia_nada");
    } catch (e) {
       $(".help-note", caja).textContent = e.message; }
  })();

  /* Lo que corre se redibuja solo cada treinta segundos: el robot decide una
     vez por vela, más seguido es tráfico sin información. */
  const refresco = setInterval(async () => {
    const zona = $("#bot-zona-vuelos", main);
    if (!zona || !document.body.contains(zona)) { clearInterval(refresco); return; }
    try {
      const e = await api.get("/api/bot");
      if (!(e.vuelos || []).length && !(e.apagadas || []).length) return;
      zona.innerHTML = zonaVuelos(e);
      atarVuelos(main);
      atarReencender(main);
      /* Y NO EN METATRADER. Los robots son de Binance: en el mundo de
       MetaTrader 5 el menú prometía "Operar 8" en una pantalla donde no se
       enciende nada, y esos ocho eran de la otra sección (3 de septiembre). */
    const rc = $("#robots-count");
    if (rc) rc.textContent = S.mundo === "metatrader" ? "" : (e.cuantos || "");
    } catch (err) { /* la próxima vuelta lo reintenta */ }
  }, 30000);
};

/* ---- vista: el piloto automático, en su propia pestaña ---- */
const vistaPiloto = async (main) => {
  const [bot, ciclo] = await Promise.all([
    api.get("/api/bot"), api.get("/api/ciclo").catch(() => null)]);
  if (!(S.datasets || []).length) await refreshDatasets();
  const apagado = !(ciclo && ciclo.corriendo && (ciclo.params || {}).encendido);
  main.innerHTML = pageHead(t("op.tab_piloto"), esc(t("ag.ciclo_sub")))
    + (apagado ? `<div class="pista mb">${icono("idea", "ico-sm")}<div>${esc(t("pil.oferta"))}</div></div>` : "")
    + panelAgentes(bot, ciclo);
  atarCiclo(main, ciclo);
  const refresco = setInterval(async () => {
    const ag = $("#ag-zona", main);
    if (!ag || !document.body.contains(ag)) { clearInterval(refresco); return; }
    try {
      const [e, c] = await Promise.all([api.get("/api/bot"), api.get("/api/ciclo").catch(() => null)]);
      if (c) { ag.innerHTML = zonaAgentes(e, c); atarCiclo(main, c); }
    } catch (err) { /* la próxima vuelta lo reintenta */ }
  }, 30000);
};

/* ---- vista: el tablero ----

   LO QUE LA CUENTA HIZO, NO LO QUE LOS BOTS RECUERDAN. Es la misma regla que
   la posicion: el registro del bot se pierde al cerrar la aplicacion, no sabe
   de comisiones, y no incluye lo que alguien haya hecho a mano desde Binance.

   EL RESULTADO VA PARTIDO y no como un solo numero. Un numero solo esconde la
   unica pregunta que importa -si la estrategia no sirve, o si sirve y los
   costos se la comen- y manda a cambiar lo que no habia que cambiar. */
const vistaTablero = async (main, hayClave) => {
  main.innerHTML = pageHead(t("tab.titulo"), esc(t("tab.sub")));
  if (!hayClave.binance.practica) {
    main.innerHTML += `<div class="card"><div class="empty-state">
      <b>${esc(t("tab.sin_clave"))}</b>
      <p class="mt">${esc(t("tab.sin_clave_sub"))}</p></div></div>`;
    return;
  }

  const caja = document.createElement("div");
  caja.id = "tab-caja";
  caja.innerHTML = `<div class="card"><p class="help-note">${esc(t("tab.cargando"))}</p></div>`;
  main.appendChild(caja);

  const pintar = async () => {
    let d;
    try {
      d = await api.get("/api/cuenta/rendimiento");
    } catch (e) {
      caja.innerHTML = `<div class="card"><div class="bot-alerta">
        <span class="g-ic">${icono("alerta")}</span>
        <span>${esc(e.message)}</span></div></div>`;
      return;
    }
    const r = d.resultado || {};
    const signo = n => (n > 0 ? "pos" : n < 0 ? "neg" : "");
    const dinero = n => (n > 0 ? "+" : "") + fmtNum(n, 4) + " USDT";
    const ficha = (rot, val, cls) => `<div class="conj-stat">
      <span>${esc(rot)}</span><b class="${cls || ""}">${val}</b></div>`;

    caja.innerHTML = `
    <div class="card">
      <div class="conj-stats">
        ${ficha(t("tab.saldo"), fmtNum(d.saldo, 2) + " USDT")}
        ${ficha(t("tab.neto"), dinero(r.neto), signo(r.neto))}
        ${d.cuantas_cerradas ? ficha(t("tab.cerradas"), fmtInt(d.cuantas_cerradas)) : ""}
        ${d.win_rate_pct != null ? ficha(t("tab.wr"), fmtNum(d.win_rate_pct, 1) + "%") : ""}
      </div>

      <!-- LAS TRES PARTES. Es lo que hace util al tablero: el PNL puede estar
           en positivo y la cuenta en negativo porque la comision se lo comio,
           y eso con un solo numero no se ve. -->
      <div class="conj-stats mt">
        ${ficha(t("tab.pnl"), dinero(r.pnl), signo(r.pnl))}
        ${ficha(t("tab.comision"), dinero(r.comision), signo(r.comision))}
        ${ficha(t("tab.funding"), dinero(r.funding), signo(r.funding))}
      </div>
      <p class="help-note">${esc(t("tab.parte_nota"))}</p>
    </div>

    <div class="card mt">
      <b>${esc(t("tab.abiertas"))}</b>
      ${(d.posiciones || []).length ? `
      <div class="conj-detalle mt">
        ${d.posiciones.map(p => `<div class="bot-fila">
          <span class="bot-que"><b>${esc(p.simbolo)}</b> ${
            esc(p.lado > 0 ? t("tab.largo") : t("tab.corto"))} ${fmtNum(p.cantidad, 4)}</span>
          <span class="bot-det">${esc(t("tab.desde_precio", {
            p: fmtNum(p.precio_entrada, 2) }))} · ${esc(t("tab.marca", {
            p: fmtNum(p.precio_marca, 2) }))}</span>
          <span class="${signo(p.pnl_abierto)}">${dinero(p.pnl_abierto)}</span>
        </div>`).join("")}
      </div>` : `<p class="help-note mt">${esc(t("tab.sin_abiertas"))}</p>`}
    </div>

    <div class="card mt">
      <b>${esc(t("tab.ejecuciones"))}</b>
      <p class="help-note">${esc(t("tab.ejecuciones_nota"))}</p>
      ${(d.cerradas || []).length ? `
      <div class="conj-detalle mt">
        ${d.cerradas.slice(0, 20).map(c => `<div class="bot-fila">
          <span class="bot-hora">${esc(new Date(c.cuando).toLocaleString(localeNum(),
            HORA({ month: "2-digit", day: "2-digit" })))}</span>
          <!-- La clave se escribe ENTERA y no se arma concatenando: armada,
               el examen de textos no puede saber cuáles se piden, y una que
               falte se dibuja en crudo en la pantalla sin que nada avise. -->
          <span class="bot-que"><b>${esc(c.simbolo)}</b> ${
            esc(c.lado === "compra" ? t("tab.compra") : t("tab.venta"))} ${
            fmtNum(c.cantidad, 4)} @ ${fmtNum(c.precio, 2)}</span>
          <span class="bot-det ${signo(c.pnl)}">${c.pnl ? dinero(c.pnl) : "—"}</span>
          <span class="bot-det">${esc(t("tab.com_corta"))} ${fmtNum(-c.comision, 4)}</span>
        </div>`).join("")}
      </div>` : `<p class="help-note mt">${esc(t("tab.sin_ejecuciones"))}</p>`}
    </div>`;
  };

  await pintar();
  /* Se refresca solo mientras la pestania este abierta: un tablero que hay
     que recargar a mano deja de ser un tablero. */
  const tic = setInterval(() => {
    if (!document.body.contains(caja)) { clearInterval(tic); return; }
    pintar();
  }, 30000);
};


/* ---- vista 2: las claves ----

   Se hace una vez y se vuelve a mirar cuando algo falla, asi que vive en una
   pestania y no arriba del bot. Lo que NO cambia por mudarse: las tres reglas
   siguen yendo ARRIBA de los campos —es el momento de mas confianza que le
   pedimos a nadie en toda la aplicacion— y practica y real siguen siendo dos
   tarjetas separadas y no un interruptor, para que operar con plata de verdad
   pida cargar otra clave a proposito. */
const vistaClaves = async (main, por) => {
  /* `casa` es el exchange. Mientras hubo uno solo estaba escrito a mano en
     cada URL; con dos, olvidarse de cambiarlo en una sola de las tres
     llamadas —guardar, probar, borrar— manda la clave de Binance al archivo
     de BingX sin que nada avise. */
  const tarjeta = (entorno, casa = "binance", cabecera = null, extra = "") => {
    const e = por[`${casa}-${entorno}`] || { configurada: false };
    const real = entorno === "real";
    return `
    <div class="card ex-card${real ? " ex-real" : ""}">
      <div class="ex-head">
        <div>
          <b>${esc(cabecera ? t(cabecera + "_t") : t(real ? "ex.real" : "ex.practica"))}</b>
          <p class="help-note">${esc(cabecera ? t(cabecera + "_sub") : t(real ? "ex.real_sub" : "ex.practica_sub"))}</p>
        </div>
        <span class="ex-estado ${e.configurada ? "on" : ""}">${
          esc(e.configurada
              ? (e.ilegible ? t("ex.ilegible") : t("ex.cargada", { cola: e.termina_en || "" }))
              : t("ex.vacia"))}</span>
      </div>
      ${extra}
      <div class="fld-pair mt">
        <label class="fld"><span>${esc(t("ex.api_key"))}</span>
          <input type="text" autocomplete="off" spellcheck="false"
                 data-ex="key" data-casa="${casa}" data-entorno="${entorno}"
                 placeholder="${e.configurada ? "········" + esc(e.termina_en || "") : ""}"></label>
        <label class="fld"><span>${esc(t("ex.secret"))}</span>
          <input type="password" autocomplete="off" spellcheck="false"
                 data-ex="secret" data-casa="${casa}" data-entorno="${entorno}"
                 placeholder="${e.configurada ? "········" : ""}"></label>
      </div>
      <div class="controls mt">
        <button class="btn" data-ex-guardar="${entorno}" data-casa="${casa}">${esc(t("ex.guardar"))}</button>
        <button class="btn ghost" data-ex-probar="${entorno}" data-casa="${casa}" ${e.configurada ? "" : "disabled"}
          >${esc(t("ex.probar"))}</button>
        <button class="linkbtn" data-ex-borrar="${entorno}" data-casa="${casa}" ${e.configurada ? "" : "hidden"}
          >${esc(t("ex.borrar"))}</button>
      </div>
      <div class="ex-pasos" id="ex-pasos-${casa}-${entorno}" hidden></div>
    </div>`;
  };

  /* LOS DOS ENLACES DE BINANCE. Van por el servidor y no como <a href>: el
     escritorio es una sola ventana sin barra de direcciones, asi que navegar
     adentro dejaria al usuario en Binance sin forma de volver. */
  const enlacesBinance = `
    <div class="controls mt">
      <button class="btn ghost" data-enlace="binance_clave"
        >${esc(t("ex.bn_crear"))}</button>
      <button class="btn ghost" data-enlace="binance_demo"
        >${esc(t("ex.bn_ver"))}</button>
    </div>
    <p class="help-note">${esc(t("ex.bn_nota"))}</p>`;

  main.innerHTML = pageHead(t("op.tab_claves"), esc(t("ex.sub"))) + `
    <div class="card ex-aviso">
      <ul class="ex-reglas">
        <li><b>${esc(t("ex.regla1_t"))}</b><span>${esc(t("ex.regla1"))}</span></li>
        <li><b>${esc(t("ex.regla2_t"))}</b><span>${esc(t("ex.regla2"))}</span></li>
        <li><b>${esc(t("ex.regla3_t"))}</b><span>${esc(t("ex.regla3"))}</span></li>
      </ul>
    </div>
    ${/* BINANCE PRIMERO. Es el único exchange con demo que el bot sabe
          encender y donde todo esto se prueba; alguien que eligió "cripto"
          llegaba acá y lo primero que veía eran dos tarjetas de BingX, con
          la de Binance debajo del pliegue. */ ""}
    ${/* SÓLO BINANCE, Y SÓLO DEMO. Es el único exchange que la aplicación
          opera hoy; las tarjetas de BingX (práctica y real) se retiran de la
          vista hasta que haya un segundo exchange operable de verdad. El
          código de BingX y sus pruebas quedan. */ ""}
    ${tarjeta("practica", "binance", "ex.bn", enlacesBinance)}`;

  const campo = (casa, entorno, cual) =>
    $(`[data-ex="${cual}"][data-casa="${casa}"][data-entorno="${entorno}"]`, main);

  /* Los nombres de los pasos se escriben ENTEROS y no se arman concatenando
     el prefijo con el nombre del paso. Armados así, el examen de textos no
     puede saber qué claves se piden —ve el prefijo suelto— y una clave que
     falte se dibuja en crudo en la pantalla sin que nada avise.

     (El examen lee el archivo como texto, así que ni siquiera se puede
     ESCRIBIR la versión mala en un comentario: la cuenta igual.) */
  const NOMBRE_PASO = () => ({
    responde: t("ex.paso_responde"), clave: t("ex.paso_clave"),
    saldo: t("ex.paso_saldo"), modo: t("ex.paso_modo"),
    posiciones: t("ex.paso_posiciones"),
  });

  const pintarPasos = (casa, entorno, r) => {
    const caja = $(`#ex-pasos-${casa}-${entorno}`, main);
    const nombres = NOMBRE_PASO();
    caja.hidden = false;
    caja.innerHTML = r.pasos.map(p => `
      <div class="ex-paso ${p.ok ? "ok" : "mal"}">
        <span class="ex-ic">${icono(p.ok ? "tilde" : "alerta")}</span>
        <b>${esc(nombres[p.paso] || p.paso)}</b>
        <span>${esc(detallePaso(p))}</span>
      </div>`).join("");
  };

  /* El modo de posición llega como lo nombra el servidor ("una_via",
     "cobertura") y se mostraba tal cual, con guion bajo y en español, en la
     interfaz en inglés. Es un valor cerrado: se traduce como los demás. */
  function detallePaso(p) {
    const d = String(p.detalle ?? "");
    if (p.paso === "modo") {
      if (d === "una_via") return t("ex.modo_una_via");
      if (d === "cobertura") return t("ex.modo_cobertura");
      return d;
    }
    /* Los detalles de los otros pasos también los escribe el servidor en
       español ("2 velas", "4.991,94 disponible", "ninguna abierta"): son
       formas cerradas, así que se reconocen y se dicen en el idioma de la
       pantalla. Lo que no se reconoce —un mensaje de error del exchange— se
       muestra tal cual. */
    let m;
    if (p.paso === "responde" && (m = d.match(/^([\d.,]+) velas$/)))
      return t("ex.det_velas", { n: m[1] });
    if (p.paso === "saldo" && (m = d.match(/^([\d.,]+) disponible$/)))
      return t("ex.det_disponible", { n: m[1] });
    if (p.paso === "posiciones") {
      if (d === "ninguna abierta") return t("ex.det_ninguna");
      if (d === "hay una abierta") return t("ex.det_una");
      if ((m = d.match(/^(\d+) abiertas?$/))) return t("ex.det_abiertas", { n: m[1] });
    }
    return d;
  }

  $$("[data-ex-guardar]", main).forEach(b => {
    b.onclick = async () => {
      const entorno = b.dataset.exGuardar;
      const casa = b.dataset.casa;
      const key = campo(casa, entorno, "key").value.trim();
      const secret = campo(casa, entorno, "secret").value.trim();
      if (!key || !secret) return toast(t("ex.faltan"), "err");
      b.disabled = true;
      const original = b.innerHTML;
      b.innerHTML = `<span class="spinner"></span>${esc(t("ex.conectando"))}`;
      try {
        await api.post(`/api/exchanges/${casa}/${entorno}`,
                       { api_key: key, secret });
        b.innerHTML = `${icono("tilde", "ico-sm")} ${esc(t("ex.conectada_ok"))}`;
        b.classList.add("hecho");
        await sleep(450);
        /* Los campos se vacian apenas se guardo. Una clave que queda a la
           vista en un input se ve en una captura de pantalla, en un video de
           YouTube y en cualquiera que pase por atras. */
        campo(casa, entorno, "key").value = "";
        campo(casa, entorno, "secret").value = "";
        toast(t("ex.guardada"), "ok");
        await refreshCuenta();
        /* Recién conectada la cuenta es el momento de ofrecer el Piloto: es
           la función más fuerte del producto, y escondida no existe. Si
           venía de "Encender" en Probar, vuelve ahí con la elegida. */
        await navigate("operar", PREELEGIDA ? "bot" : "piloto");
      } catch (e) {
       toast(e.message, "err"); b.innerHTML = original; }
      b.disabled = false;
    };
  });

  $$("[data-ex-probar]", main).forEach(b => {
    b.onclick = async () => {
      const entorno = b.dataset.exProbar;
      const casa = b.dataset.casa;
      b.disabled = true;
      try {
        pintarPasos(casa, entorno,
                    await api.post(`/api/exchanges/${casa}/${entorno}/comprobar`, {}));
      } catch (e) {
       toast(e.message, "err"); }
      b.disabled = false;
    };
  });

  $$("[data-enlace]", main).forEach(b => {
    b.onclick = async () => {
      try { await api.post("/api/abrir-enlace", { nombre: b.dataset.enlace }); }
      catch (e) { toast(e.message, "err"); }
    };
  });

  $$("[data-ex-borrar]", main).forEach(b => {
    b.onclick = async () => {
      const entorno = b.dataset.exBorrar;
      const casa = b.dataset.casa;
      if (!confirm(t("ex.borrar_seguro"))) return;
      try {
        await api.del(`/api/exchanges/${casa}/${entorno}`);
        toast(t("ex.borrada"), "ok");
        await navigate("operar");
      } catch (e) {
       toast(e.message, "err"); }
    };
  });
};


PAGES.consejos = async (main) => {
  main.innerHTML = pageHead(t("nav.tips"), esc(t("tips.sub"))) + `
    <div class="consejos">
      ${CONSEJOS().filter(c => !c.mundo || c.mundo === S.mundo).map(c => `
        <article class="consejo">
          <span class="c-ico">${icono(c.ico, "ico-lg")}</span>
          <div class="c-cuerpo">
            <h2>${esc(t(c.clave))}</h2>
            ${t(c.clave + "_cuerpo").split("\n\n").map(x => `<p>${x}</p>`).join("")}
            ${GRAFICOS[c.id] ? `<figure class="c-fig">${GRAFICOS[c.id]()}</figure>` : ""}
          </div>
        </article>`).join("")}
    </div>
    <p class="stage-note tips-pie">${esc(t("tips.foot"))}</p>` + misEnlacesHTML();
  atarMisEnlaces(main);
};

/* Las familias de instrumentos, en el orden en que se muestran.

   El orden NO es alfabético: va de lo que la mayoría ya conoce a lo más
   nuevo. Alfabético pondría los perpetuos primero por casualidad.

   Los rótulos se piden ENTEROS y no armando la clave con el nombre de la
   categoría: armados así, el examen de textos ve el prefijo suelto y una
   clave que falte se dibuja en crudo sin que nada avise. */
const FAMILIAS = () => [
  { cat: "indices", rotulo: t("cat.indices"), sub: t("famsub.indices") },
  { cat: "forex", rotulo: t("cat.forex"), sub: t("famsub.forex") },
  { cat: "metals", rotulo: t("cat.metals"), sub: t("famsub.metals") },
  { cat: "crypto", rotulo: t("cat.crypto"), sub: t("famsub.crypto") },
  /* Energía y bonos van DESPUÉS de lo conocido y ANTES de los perpetuos,
     siguiendo el mismo criterio del resto: de lo que la mayoría reconoce a lo
     más raro. Son los que hacen que un portafolio diversifique, pero nadie
     empieza por el gas natural. */
  { cat: "energia", rotulo: t("cat.energia"), sub: t("famsub.energia") },
  { cat: "bonos", rotulo: t("cat.bonos"), sub: t("famsub.bonos") },
  { cat: "perpetuos", rotulo: t("cat.perpetuos"), sub: t("famsub.perpetuos") },
];

/* ============================================================ página DATOS */
PAGES.data = async (main) => {
  await refreshDatasets();

  const tarjeta = (c) => {
    const ready = !!c.dataset_id;
    const fam = INST_FAMILIA[c.category] || INST_FAMILIA._otro;
    return `<div class="inst-card ${ready ? "ready" : ""}">
      ${c.mejor_rendimiento ? `<span class="inst-sello"
        title="${esc(t("inst.mejor_ayuda"))}">${icono("estrella")} ${
        esc(t("inst.mejor"))}</span>` : ""}
      <div class="inst-top">
        ${logoCripto(c.label, "inst-logo") || `<span class="inst-ic"><svg viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
          stroke-linejoin="round">${fam.icono}</svg></span>`}
        <span class="inst-id"><h3>${esc(c.label)}</h3>
          <span class="cat">${esc(t("cat." + c.category))}</span></span>
      </div>
      <p>${esc(t("inst." + c.key))}</p>
      ${ready
        ? `<div class="inst-meta">${icono("tilde")} ${esc(t("data.bars_of", {
             n: c.rows.toLocaleString(localeNum()),
             tf: t("tf." + (c.timeframe || "1h")) }))}<br>
             ${esc(String(c.start).slice(0, 10))} → ${esc(String(c.end).slice(0, 10))}
             ${/* EL RELOJ SI, LA FUENTE NO.
                   De dónde bajamos las velas es asunto nuestro: el usuario
                   pidió un instrumento, no un proveedor, y ver "de Dukascopy"
                   o "de MetaTrader" en la tarjeta sólo abre una pregunta que
                   no tiene que hacerse.
                   El reloj es lo contrario: le dice en qué horario están las
                   velas, que es lo que tiene que coincidir con su bróker. */
               c.utc_offset != null
                 ? `<br><span class="inst-fuente">${esc(t("data.en_reloj", {
                     reloj: "UTC" + (c.utc_offset >= 0 ? "+" : "") + c.utc_offset }))
                   }</span>` : ""}</div>
           <button class="btn ghost" data-mine="${c.dataset_id}" data-key="${c.key}">${esc(t("data.search_this"))}</button>`
        : `<div class="inst-meta">${esc(t("data.history_since", { fecha: c.from }))}</div>
           ${S.meta?.multiuser
             ? `<span class="muted" style="font-size:11.5px">${esc(t("data.unavailable"))}</span>`
             : `<button class="btn" data-dl="${c.key}">${icono("bajar")} ${esc(t("data.download"))}</button>`}`}
    </div>`;
  };

  /* AGRUPADAS POR FAMILIA, y el orden se fija acá.

     Con cuatro instrumentos daba igual; con dos familias de cripto no. Un
     CFD de bitcoin y un perpetuo de bitcoin se ven casi iguales en una grilla
     plana —el nombre difiere en una letra— y son cosas distintas: uno se
     opera por MetaTrader y paga spread, el otro en un exchange y paga
     comisión y funding.

     El orden NO es alfabético: va de lo que la mayoría ya conoce a lo más
     nuevo. Alfabético pondría los perpetuos primero por casualidad. */
  /* LOS OCULTOS NO SE MUESTRAN, SALVO QUE YA TENGAS SUS DATOS.
     El catálogo los sigue trayendo —de ahí salen sus costos— pero la vitrina
     no los ofrece: hoy el producto apunta a MetaTrader, y un CFD de Bitcoin
     al lado de un perpetuo de Bitcoin se lee como el mismo instrumento dos
     veces. Quien YA lo bajó lo sigue viendo: esconderle un instrumento que
     tiene cargado y con estrategias encima sería hacerlo desaparecer. */
  /* SOLO LOS DE ESTA SECCION. No es un filtro con aviso: en la sección de CFD
     un perpetuo no existe, igual que en la de cripto no existe el S&P. Eran
     dos listas mezcladas que obligaban a entender la diferencia entre spread y
     funding antes de poder elegir nada. */
  const visible = (c) => (c.mundo || "metatrader") === S.mundo
    && (!c.oculto || c.dataset_id);
  const catalogo = S.catalog.filter(visible);

  const familias = FAMILIAS()
    .map(f => ({ ...f, xs: catalogo.filter(c => c.category === f.cat) }))
    .filter(f => f.xs.length);
  // por si algún día se agrega una categoría y nadie se acuerda de esa lista
  const conocidas = new Set(FAMILIAS().map(f => f.cat));
  const sueltas = catalogo.filter(c => !conocidas.has(c.category));
  if (sueltas.length) {
    familias.push({ cat: "_otro", rotulo: t("cat.otros"), sub: "", xs: sueltas });
  }

  /* LAS FAMILIAS DE UN SOLO INSTRUMENTO VAN JUNTAS. En CFDs hay un índice,
     un par, un metal y una cripto: cuatro familias de una tarjeta, cada una
     con su título y su fila, y la pantalla quedaba como una columna apilada
     con todo el ancho vacío a la derecha (2 de septiembre). La familia sigue
     escrita en la tarjeta —el chip "INDICES"—, así que juntarlas no pierde
     nada; separarlas sólo servía cuando había varias por familia. */
  const chicas = familias.filter(f => f.xs.length < 2);
  const secciones = chicas.length >= 2
    ? [...familias.filter(f => f.xs.length >= 2), {
        cat: "_juntas",
        rotulo: t(S.mundo === "exchange" ? "mundo.cripto" : "mundo.cfds"),
        sub: chicas.map(f => f.rotulo).join(" · "),
        xs: chicas.flatMap(f => f.xs),
      }]
    : familias;

  const agregar = `
        <button class="inst-card add-card" id="inst-add">
          <span class="add-plus">+</span>
          <b>${esc(t("data.add"))}</b>
          <span>${esc(t("data.add_sub"))}</span>
        </button>`;
  /* La tarjeta de "agregar CSV" cierra la última grilla en vez de abrir una
     sección propia: sola en su fila era una tarjeta más apilada. */
  const cards = secciones.length
    ? secciones.map((f, i) => `
    <section class="inst-fam">
      <h3 class="fam-tit">
        <span>${esc(f.rotulo)}</span>
        <span class="fam-sub">${esc(f.sub)}</span>
        <span class="fam-n">${f.xs.filter(c => c.dataset_id).length}/${f.xs.length}</span>
      </h3>
      <div class="inst-grid">${f.xs.map(tarjeta).join("")}${
        i === secciones.length - 1 ? agregar : ""}</div>
    </section>`).join("")
    : `<section class="inst-fam"><div class="inst-grid">${agregar}</div></section>`;

  /* La tabla del espacio de trabajo también es de la sección: en MetaTrader
     5 listaba los trece perpetuos. */
  const rows = datasetsDelMundo().map(d => `
    <tr>
      <td><b>${esc(d.name)}</b></td>
      <td><span class="badge ${d.source === "sample" ? "yellow" : "green"}">${
        d.source === "sample" ? esc(t("data.synthetic")) : esc(d.source)}</span></td>
      <td class="num">${d.rows.toLocaleString(localeNum())}</td>
      <td class="muted">${esc(String(d.start).slice(0, 16))}</td>
      <td class="muted">${esc(String(d.end).slice(0, 16))}</td>
      <td>${esc(d.timeframe)}</td>
      <td class="num">${puedeBorrar(d)
        ? `<button class="btn ghost small" data-del="${d.id}">${esc(t("ui.delete"))}</button>`
        : `<span class="muted" title="${esc(t("data.shared_help"))}">${esc(t("data.shared"))}</span>`}</td>
    </tr>`).join("");

  main.innerHTML = `
  ${pageHead(t("nav.data"), esc(t("data.sub")), ctxPill())}

  <!-- Sin caja alrededor: adentro ya hay cinco tarjetas con su propio borde,
       y encerrarlas en otra dibuja un borde que no agrupa nada que el título
       no agrupara ya. Es el caso mas claro de tarjeta dentro de tarjeta que
       tenia la aplicacion. -->
  <div class="card llana">
    <h2>${esc(t("data.library"))} <span class="hint">${esc(t(S.mundo === "exchange" ? "data.library_hint_cripto" : "data.library_hint"))}</span></h2>
    ${cards}
    ${progressHtml("dl-prog")}
  </div>

  <!-- El reloj del bróker. Va en Datos y no en Minado porque es una propiedad
       de la máquina y de la cuenta, no de una búsqueda: se pone una vez y
       vale para todos los robots que se exporten después. -->
  ${/* SOLO EN CFD. El reloj del bróker es una propiedad de MetaTrader; en
        cripto Binance habla en UTC, el bot no lo usa, y la tarjeta hacía
        creer que faltaba configurar algo. */ ""}
  <div class="card"${S.mundo === "exchange" ? " hidden" : ""}>
    <h2>${esc(t("data.broker"))} <span class="hint">${esc(t("data.broker_hint"))}</span></h2>
    <p class="help-note">${t("data.broker_help")}</p>
    <div class="reloj">
      <label class="fld">
        <span>${esc(t("data.broker_offset"))}</span>
        <select data-cfg="brokerUtc">
          ${[-5,-4,-3,-2,-1,0,1,2,3,4,5].map(h => `<option value="${h}" ${
            +S.cfg.brokerUtc === h ? "selected" : ""}>UTC${h >= 0 ? "+" : ""}${h}${
            h === 0 ? "" : " h"}</option>`).join("")}
        </select>
      </label>
      <div class="reloj-ahora">
        <span>${esc(t("data.broker_now"))}</span>
        <b id="reloj-b">—</b>
      </div>
    </div>
    <p class="stage-note">${esc(t("data.broker_note"))}</p>
  </div>

  <div class="card" id="imp-card">
    <h2>${esc(t("data.import"))} <span class="hint">MT4/MT5, TradingView, Dukascopy, Binance</span></h2>
    <div class="controls">
      <!-- El selector de archivo primero, que es lo que la gente sabe usar.
           Antes el campo grande pedía "Ruta del archivo en esta PC" —algo que
           nadie tiene de memoria— y el selector normal aparecía último y en
           chico, con el rótulo "…o subir archivo chico", que se lee como si
           fuera la opción mala. La ruta sigue existiendo porque un histórico
           M1 de años no entra por el selector del navegador, pero eso es el
           caso raro y ahora está donde va: guardado. -->
      <label class="fld" style="flex:1; min-width:280px"><span>${esc(t("data.pick_file"))}
          <span class="hint">${esc(t("data.pick_file_hint"))}</span></span>
        <input id="up-file" type="file" accept=".csv,.txt"></label>
      <label class="fld"><span>${esc(t("data.name"))}</span>
        <input id="imp-name" type="text" placeholder="${esc(t("data.optional"))}"></label>
      <details class="adv" style="flex-basis:100%">
        <summary><span class="adv-chev">›</span>${esc(t("data.big_file"))}</summary>
        <div class="fld-pair mt">
          <label class="fld" style="flex:1; min-width:300px"><span>${esc(t("data.paste_path"))}
              <span class="hint">${esc(t("data.paste_path_hint"))}</span></span>
            <input id="imp-path" type="text" style="width:100%"
              placeholder="C:\Users\...\Downloads\SP500_M1.csv"></label>
          <button class="btn" id="imp-go">${esc(t("data.import_path"))}</button>
        </div>
      </details>
    </div>
    ${progressHtml("imp-prog")}
  </div>

  <div class="card">
    <h2>${esc(t("data.in_workspace"))}</h2>
    ${S.datasets.length ? `<div class="scroll-x"><table>
      <thead><tr><th>${esc(t("data.name"))}</th><th>${esc(t("data.source"))}</th>
        <th class="num">${esc(t("ui.bars"))}</th>
        <th>${esc(t("mine.from"))}</th><th>${esc(t("mine.to"))}</th><th>TF</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>`
      : `<div class="empty-state"><div class="big">${icono("base","ico-xl")}</div>
           <b>${esc(t("data.none"))}</b>
           <p class="mt">${esc(t("data.none_help"))}</p>
         </div>`}
  </div>`;

  $("#inst-add", main).onclick = () => {
    // Con guarda porque el manejador puede sobrevivir a su propio DOM: si la
    // pantalla se redibuja mientras algo asincrónico está en vuelo, `main`
    // queda apuntando a un árbol desmontado y todo lo de adentro es null.
    const card = $("#imp-card", main);
    if (!card) return;
    card.scrollIntoView({ block: "center", behavior: "smooth" });
    card.classList.add("flash");
    setTimeout(() => card.classList.remove("flash"), 900);
    $("#imp-path", main)?.focus();
  };

  $$("[data-dl]", main).forEach(b => b.onclick = async () => {
    const key = b.dataset.dl;
    $$("[data-dl]", main).forEach(x => x.disabled = true);
    b.innerHTML = `<span class="spinner"></span> ${esc(t("data.downloading"))}`;
    try {
      const meta = await runJob("/api/datasets/download", { key },
        j => setProgress("dl-prog", j));
      toast(t("data.ready", { nombre: meta.name,
                             n: meta.rows.toLocaleString(localeNum()) }), "ok");
      navigate("data");
    } catch (e) {
      toast(t("data.download_failed", { motivo: e.message }), "err");
      hideProgress("dl-prog");
      $$("[data-dl]", main).forEach(x => x.disabled = false);
      b.textContent = "↓ Descargar";
    }
  });

  /* El reloj del bróker. Se muestra la hora que sería AHORA con el desfase
     elegido, para que se pueda comparar de un vistazo con el reloj de
     Observación de Mercado en MetaTrader. Sin esa comparación, elegir "UTC+3"
     es adivinar. */
  const relojSel = $('[data-cfg="brokerUtc"]', main);
  const relojB = $("#reloj-b", main);
  if (relojSel && relojB) {
    const pintarReloj = () => {
      const h = parseInt(relojSel.value, 10) || 0;
      const ahora = new Date(Date.now() + h * 3600e3);
      relojB.textContent = String(ahora.getUTCHours()).padStart(2, "0") + ":" +
        String(ahora.getUTCMinutes()).padStart(2, "0");
    };
    relojSel.onchange = () => {
      S.cfg.brokerUtc = parseInt(relojSel.value, 10) || 0;
      saveCfg();
      pintarReloj();
      toast(t("data.broker_saved"), "ok");
    };
    pintarReloj();
    // el minuto corre mientras la pantalla está abierta; se corta al salir
    const tic = setInterval(() => {
      if (!document.body.contains(relojB)) { clearInterval(tic); return; }
      pintarReloj();
    }, 20000);
  }

  $$("[data-mine]", main).forEach(b => b.onclick = () => {
    S.sel.dataset_id = b.dataset.mine;
    const entry = S.catalog.find(c => c.key === b.dataset.key);
    if (entry) { S.cfg.spread = entry.spread; S.cfg.slippage = entry.slippage; }
    S.mineResult = S.mineLive = null;
    saveCfg();
    navigate("mining");
  });

  $("#imp-go").onclick = async () => {
    const campo = $("#imp-path");
    if (!campo) return;                    // pantalla ya redibujada
    const path = campo.value.trim();
    if (!path) { toast(t("data.need_path"), "err"); return; }
    $("#imp-go").disabled = true;
    try {
      const meta = await runJob("/api/datasets/import-path",
        { path, name: $("#imp-name")?.value.trim() || undefined },
        j => setProgress("imp-prog", j));
      toast(t("data.imported", { nombre: meta.name, n: fmtInt(meta.rows) }), "ok");
      navigate("data");
    } catch (e) {
       toast(e.message, "err"); hideProgress("imp-prog"); }
    const btn = $("#imp-go"); if (btn) btn.disabled = false;
  };

  $("#up-file").onchange = async () => {
    const f = $("#up-file").files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await fetch("/api/datasets/upload",
        { method: "POST", body: fd, headers: { "X-Idioma": idioma() } });
      if (!r.ok) throw new Error((await r.json()).detail || r.status);
      const meta = await r.json();
      toast(t("data.uploaded", { nombre: meta.name, n: fmtInt(meta.rows) }), "ok");
      avisarDescartes(meta);
      navigate("data");
    } catch (e) {
       toast(e.message, "err"); }
  };

  /* LO QUE EL ARCHIVO TRAÍA MAL. El alta no falla —tirar tres filas de
     novecientas es lo correcto— pero se dice: antes un CSV con un precio
     negativo y una marca repetida entraba con el tilde verde y nada más, y
     quien lo subió minaba sobre datos rotos creyendo que estaban enteros. */
  $$("[data-del]", main).forEach(b => b.onclick = async () => {
    // con el nombre adentro: "¿Borrar este dataset?" no dice CUAL, y la
    // pantalla tiene cuatro botones iguales uno debajo del otro
    const ds = (S.datasets || []).find(d => d.id === b.dataset.del);
    if (!confirm(t("data.confirm_delete", { nombre: ds ? ds.name : "" }))) return;
    await api.del(`/api/datasets/${b.dataset.del}`);
    toast(t("data.deleted"), "ok");
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
    S.saved = await api.get("/api/strategies?" + new URLSearchParams({ mundo: S.mundo || "" }));
    const el = $("#saved-count");
    /* NO CUENTA LAS RETIRADAS. El menú decía 14 y había 7 vivas: el
       cementerio existe para separar lo vivo de lo muerto y el contador los
       volvía a mezclar, así que el número prometía el doble de lo que hay. */
    if (el) {
      const enPrueba = S.saved.filter(x => etapaDe(x) === "por_probar").length;
      const aprob = S.saved.filter(x => etapaDe(x) === "aprobadas").length;
      const antes = +el.textContent || 0;
      el.textContent = enPrueba || "";
      if (enPrueba > antes && antes) {
        el.classList.remove("sube"); void el.offsetWidth; el.classList.add("sube");
      }
      const ea = $("#aprobadas-count"); if (ea) ea.textContent = aprob || "";
    }
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

/* LA CUENTA, ABAJO EN EL MENÚ: conectada o por conectar. Se pregunta al
   servidor porque es la única verdad; el menú no adivina. */
let CUENTA_OK = null;
async function refreshRobots() {
  try {
    const e = await api.get("/api/bot");
    const prendidos = (e.vuelos || []).filter(v => v.encendido);
    ROBOTS_LLENOS = prendidos.length >= (e.maximo || 8);
    /* QUIÉNES ESTÁN DE VERDAD EN EL AIRE. El menú contaba robots (8) y la
       lista contaba estrategias promovidas (9): la que se apagó seguía
       diciendo "Operando" y los dos números no cerraban (3 de septiembre). */
    const ids = prendidos.map(v => v.estrategia_id).filter(Boolean);
    /* Un robot encendido antes de que existiera este campo no dice de qué
       estrategia salió. Si NINGUNO lo dice, no se sabe nada y se cree lo que
       dice la estrategia: demotarlas todas sería peor que el desajuste. */
    ROBOTS_VIVOS = prendidos.length && !ids.length ? null : new Set(ids);
    const rc = $("#robots-count"); if (rc) rc.textContent = e.cuantos || "";
  } catch (err) { /* sin bots no hay número */ }
}
async function refreshCuenta() {
  try {
    const ex = await api.get("/api/exchanges");
    CUENTA_OK = ex.some(x => x.exchange === "binance" && x.entorno === "practica" && x.configurada);
  } catch (e) { CUENTA_OK = null; }
  pintarCuenta();
}
function pintarCuenta() {
  const el = $("#nav-cuenta-txt");
  if (!el) return;
  el.textContent = t(CUENTA_OK ? "nav.cuenta_ok" : "nav.cuenta_no");
  const b = $("#nav-cuenta"); if (b) b.classList.toggle("conectada", !!CUENTA_OK);
}

async function refreshBancoCount() {
  try {
    const r = await api.get("/api/corridas?" + new URLSearchParams({ mundo: S.mundo || "" }));
    S.banco.corridas = r.corridas;
    S.banco.total = r.total;
    S.banco.tope = r.tope;
    pintarNavBanco(r.total);
  } catch (e) { /* ídem */ }
}

/* El numero pegado a "Minado" en la barra lateral.

   Es el total del Databank sumando TODAS las corridas, no lo que encontro la
   ultima. Pegado a la palabra "Minado" y sin nada mas se lee como "91
   minados", que no es lo que dice: por eso ahora lleva el rotulo entero
   encima y para el lector de pantalla. */
function pintarNavBanco(total) {
  const el = $("#banco-count");
  if (!el) return;
  el.textContent = total || "";
  const rotulo = t("nav.bank_count", { n: fmtInt(total || 0) });
  el.title = rotulo;
  el.setAttribute("aria-label", rotulo);
}

/* ================================================ ESTADO DE UNA ESTRATEGIA ==
   El dato que le da un objetivo a la aplicación.

   Antes de esto se podía correr el walk-forward y el Monte Carlo desde dos
   secciones distintas del menú, salía un veredicto, y al cambiar de pantalla
   se perdía. La lista de estrategias no podía decir cuáles estaban probadas,
   así que la aplicación era un montón de pantallas sin ningún objetivo: nunca
   había un "listo".

   Ahora cada guardada tiene un estado que sobrevive a cerrar el programa, y el
   trabajo consiste en llevarlas a verde.

   Cuatro estados y no dos. "A medias" es un resultado real y frecuente —
   sobrevivió en la mitad de los tramos — y meterlo en "no pasó" sería mentir
   tanto como meterlo en "aprobada". */
/* ══════════════════════════════════════════════ FUNCIONES AVANZADAS ═══════
   Walk-forward, Monte Carlo y portafolio están construidos, probados y
   funcionando — y apagados a propósito para la primera versión.

   El motivo no es técnico. Alguien que abre esto por primera vez tiene que
   poder minar una estrategia y llevársela a MetaTrader sin que nadie le
   explique qué es la eficiencia de un walk-forward. Cada pantalla de más es
   una razón de más para cerrar la aplicación y no volver.

   Nada se borró: el código está entero, los endpoints responden y sus tests
   siguen corriendo en cada cambio. Poner esto en `true` los devuelve a la
   pantalla. Se eligió un interruptor y no comentar bloques porque el código
   comentado se pudre en tres semanas, y el código con tests no.

   Lo que se apaga:
     · el veredicto y el botón "Poner a prueba" dentro de una estrategia
     · la columna Estado en Mis estrategias
     · el portafolio al tildar dos o más
*/
/* De dónde cuelga el sitio público. En el escritorio la aplicación se sirve
   desde 127.0.0.1, así que un enlace relativo a /soporte abriría la copia
   local — que existe, pero queda dentro de la ventana y sin poder corregirse.
   Apuntando al sitio, la página de ayuda se arregla una vez para todos. */
const ORIGEN_SITIO = location.hostname === "127.0.0.1" || location.hostname === "localhost"
  ? "https://botiquant.com" : "";

/* LAS PRUEBAS DE ROBUSTEZ: walk-forward y Monte Carlo.

   Se llamaba `AVANZADO` y escondía tres cosas distintas. El portafolio ya
   salió de acá —es un objetivo del producto, no una herramienta— y lo que
   quedó es una sola función con un solo nombre: poner una estrategia a
   prueba. Un interruptor que esconde una cosa se puede razonar; uno que
   esconde tres se vuelve un cajón.

   AHORA VA ENCENDIDO. El motivo de apagarlo era bueno —cada pantalla de más
   es una razón de más para cerrar la aplicación y no volver— pero se cumplía
   igual sin apagarlo, porque esto NO agrega una pantalla: vive adentro de una
   estrategia ya guardada y respeta el orden que ya existe —encontrar, guardar,
   PROBAR, operar—. Quien no guarda nada no lo ve nunca.

   Y lo que muestra está escrito para que se entienda sin vocabulario: el
   veredicto va primero y en palabras —"aguanta a medias"— y los números
   quedan debajo. Ver `panelPrueba`. */
const PRUEBAS = true;

/* EL PORTAFOLIO VA APARTE DE LAS PRUEBAS, y la separación es la decisión.

   Estaba adentro, apagado junto con el walk-forward y la columna Estado. El
   motivo de aquello sigue siendo bueno —cada pantalla de más es una razón de
   más para cerrar la aplicación y no volver— pero metía en la misma bolsa dos
   cosas distintas:

     · el walk-forward es una HERRAMIENTA para el que ya sabe qué mirar;
     · el portafolio es uno de los dos OBJETIVOS del producto. Alguien puede
       venir a buscar una estrategia sola, o a armar un conjunto de EA para
       una cuenta. Los dos caminos son igual de válidos y el segundo no es
       una versión avanzada del primero.

   Escondido, el conjunto sólo se podía armar exportando de a uno — y ahí cada
   EA se cree dueño del 100% de la cuenta, así que tres exportados por separado
   arriesgan tres veces lo pedido.

   Se enciende solo: aparece al tildar dos o más, y quien no tilde nada no ve
   nada de esto. */
const PORTAFOLIO = true;

/* LAS FRANJAS HORARIAS, APAGADAS.

   Medido: restringir la búsqueda a una franja sube mucho UNA estrategia fija
   —una Donchian del S&P pasó de 0,89% a 5,38% anual limitándola a Nueva York—
   pero cuando la BÚSQUEDA elige entre nueve franjas, el promedio baja: S&P de
   2,49% a 1,85%, oro de 3,80% a 2,22%. Las dos cosas son ciertas y la segunda
   es la que importa acá, porque es lo que hace la aplicación.

   Por qué baja: cada franja recorta la muestra, así que hay menos operaciones
   por candidata y más chance de que una racha buena pase la vara por azar. Se
   gana un grado de libertad y se pierde evidencia.

   Ocupaba nueve botones, más de un tercio del primer paso, para una perilla
   que en promedio empeora el resultado y que hay que entender para usar bien.

   Se apaga y no se borra, igual que se hacía con las pruebas: el código queda entero, sus
   tests siguen corriendo y las estrategias ya minadas con una franja la siguen
   mostrando —son un registro de lo que se hizo—. Poner esto en `true` la
   devuelve a la pantalla. */
const SESIONES = false;

const ESTADO_UI = {
  aprobada:  { cls: "ok",  ico: "tilde" },
  aceptable: { cls: "mid", ico: "info" },
  no_paso:   { cls: "bad", ico: "alerta" },
};

const estadoDe = (s) => (s.validacion && s.validacion.estado) || "sin_probar";

/* EN QUÉ ETAPA DEL CAMINO ESTÁ, dicho de una sola vez.

   La fila mostraba dos chips que se leían como una contradicción:
   "Validada" (dónde está) y "No pasó" (cómo le fue). Para quien mira la
   lista son la misma pregunta —¿qué hago con ésta?— y la respuesta es una
   sola: probarla, encenderla, ya está operando, o descartarla. Las cuatro
   etapas son también los filtros de la cabecera. */
const ETAPAS = ["por_probar", "aprobadas", "operando", "descartadas"];

function etapaDe(s) {
  if (estaRetirada(s)) return "descartadas";
  const e = s.estado || "";
  // Promovida Y con el robot prendido. Apagada vuelve a Las que aguantaron,
  // que es donde se la puede volver a encender.
  if ((e === "practica" || e === "produccion")
      && (ROBOTS_VIVOS === null || ROBOTS_VIVOS.has(s.id))) return "operando";
  const v = estadoDe(s);
  if (v === "sin_probar") return "por_probar";
  if (v === "no_paso") return "descartadas";
  return "aprobadas";                      // aprobada, o aguantó a medias
}

/* El chip único de la fila: la etapa, y dentro de ella el matiz que importa
   (a medias va en ámbar dentro de Aprobadas; retirada en gris dentro de
   Descartadas, con el motivo al pasar el mouse). */
function chipEtapa(s) {
  const et = etapaDe(s);
  if (et === "operando") return caminoChip(s);
  if (et === "por_probar") return `<span class="est est-none">${esc(t("est.sin_probar"))}</span>`;
  if (et === "descartadas") {
    if (estaRetirada(s)) return caminoChip(s);
    return `<span class="est est-bad">${icono("alerta", "ico-sm")}${esc(t("est.no_paso"))}</span>`;
  }
  const v = estadoDe(s);
  return v === "aceptable"
    ? `<span class="est est-mid">${icono("info", "ico-sm")}${esc(t("est.aceptable"))}</span>`
    : `<span class="est est-ok">${icono("tilde", "ico-sm")}${esc(t("est.aprobada"))}</span>`;
}

/* El filtro elegido en Probar. Vive fuera de la página porque la
   pantalla se repinta después de cada prueba y no puede perderlo. */
let FILTRO_ETAPA = "vigentes";

/* La estrategia que Probar manda a encender: Operar la preelige. */
let PREELEGIDA = null;
/* Si ya están todos los robots puestos, Aprobadas no ofrece encender. */
let ROBOTS_LLENOS = false;
/* Las estrategias con un robot encendido. `null` mientras no se sabe: hasta
   que llegue la respuesta se cree lo que dice la estrategia, o la lista
   parpadearía entera al cargar. */
let ROBOTS_VIVOS = null;

/* LO PROBADO SE QUEDA EN PROBAR HASTA QUE SE LIMPIA. Antes desaparecía al
   segundo de terminar y el usuario no veía por qué pasó o no pasó. Ahora
   sigue a la vista con su porqué; "Limpiar" lo saca de acá (ya está en su
   bandeja). Lo limpiado se recuerda en esta máquina. */
function limpiadas() {
  try { return new Set(JSON.parse(localStorage.getItem("qf.limpiadas") || "[]")); } catch (e) { return new Set(); }
}
function limpiar(ids) {
  const set = limpiadas(); ids.forEach(id => set.add(id));
  try { localStorage.setItem("qf.limpiadas", JSON.stringify([...set].slice(-500))); } catch (e) { /* nada */ }
}

/* El resumen de la prueba, en una celda: tramos, eficiencia, afuera, caída. */
function pruebaResumen(s) {
  const v = s.validacion || {};
  if (!v.estado) return `<span class="muted">—</span>`;
  const partes = [];
  if (v.tramos) partes.push(`${v.tramos_ganadores ?? "?"}/${v.tramos}`);
  if (v.eficiencia != null) partes.push(`${t("wf.ef_corto")} ${fmtNum(v.eficiencia, 2)}`);
  if (v.retorno_fuera_pct != null) partes.push(`<b class="${v.retorno_fuera_pct >= 0 ? "pos" : "neg"}">${fmtPct(v.retorno_fuera_pct)}</b>`);
  /* NO ES LA MISMA CAÍDA que la columna "Caída máxima" de al lado: aquélla es
     la que efectivamente pasó, ésta es la peor plausible rebarajando las
     operaciones, y suele ser el doble. Las dos decían "dd" en la misma fila
     (3 de septiembre de 2026). */
  if (v.mc && v.mc.dd_malo_pct != null) {
    partes.push(`<span class="muted" title="${esc(t("wf.m_bad_run_help"))}">${
      esc(t("wf.dd_malo_corto"))} ${fmtNum(v.mc.dd_malo_pct, 1)}%</span>`);
  }
  return `<span class="prueba-res">${partes.join(" · ")}</span>`;
}
let REINTENTO_OCUPADO = null;

/* ENCENDER ES UN CLIC. La porción sale de la misma regla del Piloto —la
   cuenta repartida entre los robots que puede haber— y el modo es demo,
   siempre. Sin cuenta conectada, manda a conectarla y guarda la elegida. */
async function encenderDirecto(s, boton) {
  if (!s) return;
  const original = boton.innerHTML;
  boton.disabled = true;
  boton.innerHTML = `<span class="spinner"></span>${esc(t("op.encendiendo"))}`;
  try {
    const ex = await api.get("/api/exchanges");
    const hay = ex.some(x => x.exchange === "binance" && x.entorno === "practica" && x.configurada);
    if (!hay) { PREELEGIDA = s.id; toast(t("op.conectar_primero"), "err"); navigate("operar", "claves"); return; }
    const m = s.meta || {};
    const obj = await api.post("/api/export/bingx/objeto", {
      spec: s.spec, name: s.name, dataset_id: m.dataset_id, timeframe: m.timeframe,
      settings: { commission_pct: m.commission }, metrics: m.metrics, oos: m.oos,
    });
    const [e, c] = await Promise.all([api.get("/api/bot"), api.get("/api/ciclo").catch(() => null)]);
    if ((e.vuelos || []).filter(v => v.encendido).length >= (e.maximo || 8)) {
      throw Object.assign(new Error(t("bot.sin_lugar") + ". " + t("bot.sin_lugar_sub")), { status: 409 });
    }
    const libre = typeof e.porcion_libre === "number" ? e.porcion_libre : 1;
    const max = (c && c.params && c.params.max_en_practica) || e.maximo || 8;
    const porcion = Math.max(0.01, Math.min(libre, Math.round(100 / max) / 100));
    await api.post("/api/bot/encender", { bot: obj, modo: "practica", exchange: "binance",
                                          estrategia_id: s.id, porcion, perdida_maxima: 0 });
    boton.innerHTML = `${icono("tilde", "ico-sm")} ${esc(t("op.encendida_ok"))}`;
    boton.classList.add("hecho");
    primerPaso("encendiste");
    toast(t("saved.encendida", { nombre: s.name }), "ok");
    await refreshSavedCount();
    await sleep(450);
    navigate("operar", "bot");
  } catch (err) {
    if (!pedirCuenta(err.status)) toast(err.message, "err");
    boton.disabled = false;
    boton.innerHTML = original;
  }
}

/* ¿ESTÁ ESPERANDO SU PRUEBA? Salir de Probar y volver mostraba las filas
   como "sin probar" con la cola corriendo, y volver a apretar las encolaba
   de nuevo (2 de septiembre). */
function enCola(id) {
  if (!COLA_PRUEBAS) return false;
  return (COLA_PRUEBAS.ids || []).includes(id) || COLA_PENDIENTE.some(x => x.id === id);
}

/* Dónde quedó la que se acaba de probar, con un atajo. Se busca en la
   lista ya refrescada; si todavía no llegó, no se dice nada. */
async function avisarVeredicto(id) {
  await refreshSavedCount();
  const s = (S.saved || []).find(x => x.id === id);
  if (!s || !(s.validacion || {}).estado) return;
  const et = etapaDe(s);
  if (S.page === "saved" && S.vista === et) return;      // ya lo está viendo
  toastAccion(t("wf.quedo", { nombre: s.name, donde: t(et === "aprobadas" ? "nav.aprobadas" : "saved.descartadas_t") }),
              t("wf.ir_a_ver"), () => navigate("saved", et));
}

/* Un aviso con un botón. El toast común se va solo y no lleva a ningún lado;
   éste ofrece el paso siguiente sin obligar a nada. */
function toastAccion(mensaje, rotulo, alApretar) {
  const host = $("#toast-host");
  if (!host) return;
  const el = document.createElement("div");
  el.className = "toast ok toast-accion";
  el.innerHTML = `<span>${esc(mensaje)}</span>`;
  const b = document.createElement("button");
  b.className = "linkbtn"; b.textContent = rotulo;
  b.onclick = () => { el.remove(); alApretar(); };
  el.appendChild(b);
  host.appendChild(el);
  setTimeout(() => el.remove(), 12000);
}

function accionEtapa(s) {
  const et = etapaDe(s);
  const cripto = mundoDeDataset((s.meta || {}).dataset_name || "") !== "metatrader";
  if (et === "por_probar") {
    if (enCola(s.id)) return `<span class="help-note">${esc(t("sel.en_cola_chip"))}</span>`;
    return `<button class="btn small" data-probar="${esc(s.id)}">${esc(t("wf.test_it"))}</button>`;
  }
  if (et === "aprobadas") {
    /* NI TRAILING NI RETIRADAS: el trailing mueve el stop cada vela y el bot
       deja UNA orden puesta en el exchange, así que Operar las filtra. Ofrecer
       "Encender" acá y no encontrarlas allá era una promesa rota. */
    const operable = cripto && !(((s.spec || {}).risk || {}).trail_atr > 0);
    /* SIN LUGAR NO SE OFRECE: el botón estaba habilitado con los ocho robots
       puestos y el motivo aparecía recién después del clic. */
    const sinLugar = ROBOTS_LLENOS;
    return `${operable ? `<button class="btn small" ${sinLugar ? `disabled title="${esc(t("bot.sin_lugar_sub"))}"` : ""} data-encender="${esc(s.id)}">${icono("seguir", "ico-sm")} ${esc(t("saved.acc_encender"))}</button>` : ""}
      <button class="btn ghost small" data-probar="${esc(s.id)}">${esc(t("wf.retest"))}</button>
      ${cripto && !operable ? `<span class="muted" title="${esc(t("bot.trailing_no"))}">${esc(t("bot.trailing_corto"))}</span>` : ""}`;
  }
  if (et === "operando") {
    return `<button class="btn ghost small" data-ver-robot="${esc(s.id)}">${esc(t("saved.acc_ver_robot"))}</button>`;
  }
  if (estaRetirada(s)) return "";
  return `<button class="btn ghost small" data-retirar="${esc(s.id)}">${esc(t("saved.acc_retirar"))}</button>
    <button class="btn ghost small" data-probar="${esc(s.id)}">${esc(t("wf.retest"))}</button>`;
}

/* Las claves ENTERAS, como en CAMINO_ROTULO: el examen de textos no puede
   seguir una clave armada pegando el prefijo con el nombre de la etapa. */
const ETAPA_ROTULO = () => ({
  por_probar: t("etapa.por_probar"), aprobadas: t("etapa.aprobadas"),
  operando: t("etapa.operando"), descartadas: t("etapa.descartadas"),
});

/* DONDE ESTA en el camino, que es OTRA COSA que cómo le fue en la prueba.

   La columna se llamaba "Estado" y mostraba el veredicto del walk-forward, así
   que una estrategia RETIRADA se veía idéntica a una viva: decía "Sin probar"
   y ofrecía el botón de probarla. Peor todavía cuando el motivo del retiro es
   que se borró su histórico — la acción que ofrecía no podía funcionar.

   `estados.py` guarda el motivo y lo exige para retirar, justamente para no
   volver a encender lo mismo. Ese trabajo no servía de nada si la pantalla no
   lo mostraba. */
const RETIRADA = "retirada";
const estaRetirada = (s) => (s.estado || "") === RETIRADA;

/* Las claves ENTERAS y no armadas pegando el prefijo con el nombre del
   estado: así el examen de textos no puede saber cuáles se piden —ve el
   prefijo suelto— y una que falte se dibuja en crudo sin que nada avise.

   (Y el examen lee el archivo como TEXTO, así que la versión mala tampoco se
   puede escribir acá como ejemplo: la contaría igual. Ya pasó.) */
const CAMINO_ROTULO = () => ({
  validada: t("camino.validada"),
  practica: t("camino.practica"),
  produccion: t("camino.produccion"),
  retirada: t("camino.retirada"),
});

function caminoChip(s) {
  const e = s.estado || "";
  const rotulo = CAMINO_ROTULO()[e];
  if (!rotulo) return "";
  const motivo = (s.retiro || {}).motivo || "";
  return `<span class="est est-camino est-${esc(e)}"
    title="${esc(motivo)}">${esc(rotulo)}</span>`;
}

function estadoChip(s) {
  const e = estadoDe(s);
  const ui = ESTADO_UI[e];
  if (!ui) {
    return `<span class="est est-none">${esc(t("est.sin_probar"))}</span>`;
  }
  return `<span class="est est-${ui.cls}">${icono(ui.ico, "ico-sm")}${esc(t("est." + e))}</span>`;
}

/* La frase que resume la prueba. Es lo primero que se lee, y va antes que
   cualquier número: "aguantó en 3 de 4 tramos" se entiende sin saber qué es un
   tramo, y "eficiencia 0.62" no se entiende sin que te lo expliquen.

   La frase tiene que nombrar QUÉ la limitó, y hay dos cosas distintas que
   pueden limitarla. Una estrategia puede ganar en los cuatro tramos y aun así
   quedar en "a medias" porque afuera rindió un tercio de lo que rendía adentro
   — que es el caso más común de todos. Con una sola frase por estado, la
   pantalla decía "aguantó a medias: ganó en 4 de 4 tramos", que se lee como una
   contradicción y le hace perder la confianza al usuario justo cuando le
   estamos pidiendo que confíe en el veredicto. */
function fraseVeredicto(v) {
  if (!v || !v.estado) return "";
  const g = v.tramos_ganadores, n = v.tramos;
  const todos = n > 0 && g >= n;
  if (v.estado === "aprobada") return t("wf.frase_aprobada", { g, n });
  if (v.estado === "aceptable") {
    return todos ? t("wf.frase_aceptable_ef", { n })
                 : t("wf.frase_aceptable_tramos", { g, n });
  }
  // no pasó: o perdió en la mitad de los tramos, o ganó pero sin ventaja real
  return g * 2 <= n ? t("wf.frase_no_paso_tramos", { g, n })
                    : t("wf.frase_no_paso_ef", { g, n });
}

/* Corre las dos pruebas. Una sola acción: son dos preguntas sobre la misma
   estrategia y ninguna se entiende sola, así que pedirle al usuario que elija
   entre "walk-forward" y "Monte Carlo" es pedirle la respuesta antes de la
   pregunta. */
async function probarEstrategia(sid, onTick) {
  return runJob("/api/probar", { strategy_id: sid }, onTick);
}

/* Selección para el portafolio. Vive fuera de la función porque la pantalla
   se repinta al probar una estrategia y no se puede perder lo tildado. */
const SEL_PF = new Set();

/* LO QUE ACABA DE PASAR SE VE PASAR. Una fila recién guardada llega a la
   lista como llega al banco; un chip que acaba de cambiar de etapa lo
   marca. Es la misma familia de movimiento que el minado, y por el mismo
   motivo: responde a algo que el usuario hizo hace un segundo. */
const RECIEN_GUARDADAS = new Set();
const RECIEN_PROBADAS = new Set();

PAGES.saved = async (main) => {
  await refreshDatasets();
  await refreshSavedCount();
  /* LAS RETIRADAS AL FINAL. Llegan primero por ser las más nuevas —el
     ciclo retira lo que acaba de encontrar sobre un histórico borrado— y
     entonces la lista abría con el cementerio: la primera fila era una
     estrategia que ya no juega. Adentro de cada grupo se conserva el orden. */
  const items = [...(S.saved || [])].sort(
    (x, y) => (estaRetirada(x) ? 1 : 0) - (estaRetirada(y) ? 1 : 0));
  /* LA BANDEJA: cada una contiene sólo lo que necesita una decisión ahora,
     y lo que pasa de etapa se va sola a la siguiente. */
  const BANDEJA = ["por_probar", "aprobadas", "descartadas"].includes(S.vista) ? S.vista : "por_probar";
  FILTRO_ETAPA = BANDEJA;

  if (!items.length) {
    main.innerHTML = pageHead(t("nav.saved"), esc(t("saved.empty_sub"))) +
      `<div class="card"><div class="empty-state">
        <div class="big">${icono("marcador","ico-xl")}</div>
        <b>${esc(t("saved.none"))}</b>
        <p class="mt">${t("saved.none_help")}</p>
        <button class="btn mt" id="go-bank">${esc(t("ui.go_bank"))}</button>
      </div></div>`;
    $("#go-bank", main).onclick = () => navigate("mining", "resultados");
    return;
  }

  // las que ya no existen no pueden seguir tildadas. La poda por bandeja va
  // más abajo, apenas se sabe qué filas están a la vista.
  const vivas = new Set(items.map(x => x.id));
  [...SEL_PF].forEach(k => { if (!vivas.has(k)) SEL_PF.delete(k); });

  /* La tabla bajó de nueve columnas a seis. Las que se fueron —profit factor,
     fuera de muestra del minado, cantidad de operaciones, fecha— no
     desaparecieron: están en la ficha de cada estrategia, a un clic. Una tabla
     es una superficie de DECISIÓN y no un volcado de datos; con nueve columnas
     de números nadie decide nada, y "fuera de muestra" al lado de "estado"
     eran dos validaciones parecidas pero distintas, que es exactamente la
     confusión que se vino a sacar. */
  const fila = (s) => {
    const ctx = s.meta || {}, m = ctx.metrics || {};
    const llega = (RECIEN_GUARDADAS.delete(s.id) || RECIEN_PROBADAS.has(s.id)) ? " llegando" : "";
    return `<tr class="clickable ${SEL_PF.has(s.id) ? "elegida" : ""}${llega}" data-sid="${esc(s.id)}">
      ${PORTAFOLIO ? `<td class="tick"><input type="checkbox" data-pf="${esc(s.id)}"
            ${SEL_PF.has(s.id) ? "checked" : ""}
            aria-label="${esc(t("pf.pick_one", { nombre: s.name }))}"></td>` : ""}
      <td><span class="strat-name">${esc(s.name)}</span>${sesionTag(s.spec?.time_filter
            ? { session: sesionDeFiltro(s.spec.time_filter) } : {})}
          ${ctx.saved_at ? `<div class="strat-nota">${esc(t("saved.mined_on", {
              /* Con el mes escrito: sin opciones, en inglés salía "9/3/2026" al lado
                 de fechas ISO en otras pantallas, y 9/3 es marzo o septiembre según
                 de dónde seas (3 de septiembre de 2026). */
              fecha: new Date(ctx.saved_at).toLocaleDateString(localeNum(),
                { day: "numeric", month: "short", year: "numeric" }) }))}</div>` : ""}
          ${s.notes ? `<div class="strat-nota">${esc(s.notes)}</div>` : ""}
          <div class="strat-blocks">${esc(ctx.blocks || "")}</div></td>
      <td>${esc((ctx.dataset_name || "—").replace(/ M1.*/, ""))}
          <div class="muted" style="font-size:11px">${esc(ctx.timeframe || "")}
            · ${esc(t("dir." + (ctx.direction || "long")).toLowerCase())}</div></td>
      <td class="num ${(m.cagr_pct ?? 0) >= 0 ? "pos" : "neg"}"><b>${
        m.cagr_pct != null ? fmtPct(m.cagr_pct) : "—"}</b></td>
      <td class="num ${nivelDD(m.max_drawdown_pct, riesgoDeCtx(ctx))}">${
        m.max_drawdown_pct != null ? fmtNum(m.max_drawdown_pct, 1) + "%" : "—"}</td>
      ${PRUEBAS ? `<td class="celda-estado ${RECIEN_PROBADAS.delete(s.id) ? "chip-cambia" : ""}">${
        enCola(s.id) ? `<span class="est est-none">${esc(t("sel.en_cola_chip"))}</span>` : chipEtapa(s)}</td>
      <td class="celda-prueba">${pruebaResumen(s)}</td>` : ""}
      <td class="num" style="white-space:nowrap">
        ${/* LA ACCIÓN DICE EL PASO SIGUIENTE, según la etapa: probar las
              nuevas, encender las aprobadas, ver el robot de las que operan,
              retirar las que no pasaron. Volver a probar queda como acción
              secundaria en todas las probadas. */
          PRUEBAS ? accionEtapa(s) : ""}
        ${/* Exportar a MetaTrader sólo donde se opera con MetaTrader: en
              cripto el camino es encender un robot, y el botón confundía. */
          S.mundo === "metatrader"
            ? `<button class="btn ghost small" data-export="${esc(s.id)}">${icono("bajar")} ${esc(t("saved.acc_exportar"))}</button>` : ""}
        <button class="btn ghost small" data-del-strat="${esc(s.id)}"
          title="${esc(t("ui.delete"))}">${icono("cerrar")}</button>
      </td>
    </tr>`;
  };

  // Sin las retiradas: "24 de estas sin probar" contaba las que ya no juegan.
  const sinProbar = items.filter(x => !estaRetirada(x) && estadoDe(x) === "sin_probar" && !enCola(x.id)).length;

  /* LA CIFRA DE LA CABECERA ES LA MISMA QUE LA DEL MENÚ. El menú cuenta las
     que están en juego (sin las retiradas) y acá se decía "25 guardadas"
     con 16 en el menú: dos números para lo mismo, a un clic de distancia.
     Las retiradas se nombran aparte, que es lo que son. */
  const retiradas = items.filter(x => estaRetirada(x)).length;
  const enJuego = items.length - retiradas;
  /* EL CAMINO, ARRIBA Y CON CUENTAS. Cuatro etapas que también filtran la
     lista: quien entra ve de un vistazo cuántas hay por probar y cuántas ya
     operan, y con un clic se queda con las que le importan. "Todas" sigue
     existiendo, pero deja de ser la única vista. */
  const porEtapa = Object.fromEntries(ETAPAS.map(e => [e, items.filter(x => etapaDe(x) === e)]));
  /* CADA CUENTA ES LA DE SUS FILAS. La solapa decía "Probar · 0" y la tabla
     dibujaba 91: la cuenta salía de `porEtapa.por_probar` y la lista sumaba
     además las recién probadas, que se quedan a la vista hasta que uno las
     limpia. `cuentas.p` se completa más abajo, cuando ya se sabe cuáles son
     (3 de septiembre de 2026). */
  const cuentas = { p: porEtapa.por_probar.length, a: porEtapa.aprobadas.length,
                    o: porEtapa.operando.length, d: porEtapa.descartadas.length };
  const aMedias = porEtapa.aprobadas.filter(x => estadoDe(x) === "aceptable").length;
  const subEtapa = {
    por_probar: t("etapa.por_probar_sub"),
    aprobadas: aMedias ? t("etapa.aprobadas_sub", { n: aMedias }) : t("etapa.aprobadas_sub0"),
    operando: t("etapa.operando_sub"),
    descartadas: retiradas ? t("etapa.descartadas_sub", { n: retiradas }) : t("etapa.descartadas_sub0"),
  };
  /* LAS DESCARTADAS NO SE VEN POR DEFECTO: la lista que se mira es la de
     las que valen. Están a un clic, en su etapa o en "ver todas". */
  const yaLimpias = limpiadas();
  const recienProbadas = items.filter(x => !estaRetirada(x) && etapaDe(x) !== "operando"
    && ["aprobadas", "descartadas"].includes(etapaDe(x)) && !yaLimpias.has(x.id));
  const enProbar = [...porEtapa.por_probar, ...recienProbadas];
  cuentas.p = enProbar.length;

  /* EN METATRADER NADIE ESTÁ OPERANDO: ahí no se enciende ningún robot y la
     solapa no se dibuja, así que una estrategia que quedó en práctica no caía
     en ninguna bandeja y no se podía alcanzar desde ningún lado —31 guardadas,
     30 visibles—. Se muestran con las que aguantaron, que es de donde salieron
     y donde tiene sentido volver a mirarlas. */
  if (S.mundo === "metatrader" && porEtapa.operando.length) {
    porEtapa.aprobadas = [...porEtapa.aprobadas, ...porEtapa.operando];
    cuentas.a = porEtapa.aprobadas.length;
    cuentas.o = 0;
  }

  const visibles = BANDEJA === "por_probar" ? enProbar : porEtapa[BANDEJA];

  /* LA SELECCIÓN ES DE ESTA BANDEJA. Sobrevivía al cambio de bandeja: se
     tildaban las 25 de Probar, se pasaba a Las que aguantaron —cuatro filas a
     la vista— y la barra seguía diciendo "25 seleccionadas" con el botón en
     "Borrar 25". Veintiuna estrategias que el usuario no tenía delante, y
     borrarlas de verdad, porque el borrado recorría TODAS las guardadas y no
     las de la pantalla. Encontradas ya se limpiaba así; esto lo empareja
     (3 de septiembre de 2026). */
  const aLaVista = new Set(visibles.map(x => x.id));
  [...SEL_PF].forEach(k => { if (!aLaVista.has(k)) SEL_PF.delete(k); });
  /* Una línea con lo que hay en las otras bandejas, con enlaces: para saber
     cuánto hay sin verlo todo junto. */
  const enlace = (v, txt) => `<button class="linkbtn ${BANDEJA === v ? "on" : ""}" data-bandeja="${v}">${esc(txt)}</button>`;
  /* EL FLUJO, EN PROBAR: una caja con lo que trajimos y dos con a dónde
     fue cada una, con las cuentas de esta tanda. */
  const flujo = BANDEJA !== "por_probar" ? "" : (() => {
    const ok = recienProbadas.filter(x => etapaDe(x) === "aprobadas").length;
    const mal = recienProbadas.filter(x => etapaDe(x) === "descartadas").length;
    /* DE QUÉ HABLA ESTE DIAGRAMA. Sus números son los de esta tanda —lo
       recién probado y todavía sin limpiar— y las solapas de abajo son los
       totales: "No pasaron 68" acá y "Descartadas 72" ahí abajo se leían
       como dos respuestas a la misma pregunta (3 de septiembre de 2026). */
    return `<p class="help-note">${esc(t("flujo.de_esta_tanda"))}</p>
    <div class="flujo">
      <div class="flujo-caja ${porEtapa.por_probar.length ? "on" : ""}">
        <b>${esc(t("flujo.trajimos"))}</b><span class="flujo-n">${porEtapa.por_probar.length}</span>
        <span class="flujo-sub">${esc(t("flujo.trajimos_sub", { n: porEtapa.por_probar.length }))}</span></div>
      <i class="flujo-flecha" aria-hidden="true"></i>
      <div class="flujo-ramas">
        <div class="flujo-caja ok ${ok ? "on" : ""}"><b>${esc(t("flujo.aprobadas"))}</b><span class="flujo-n">${ok}</span>
          <span class="flujo-sub">${esc(t("flujo.aprobadas_sub", { n: ok }))}</span></div>
        <div class="flujo-caja mal ${mal ? "on" : ""}"><b>${esc(t("flujo.no_pasaron"))}</b><span class="flujo-n">${mal}</span>
          <span class="flujo-sub">${esc(t("flujo.no_pasaron_sub", { n: mal }))}</span></div>
      </div>
      ${recienProbadas.length ? `<div class="flujo-limpiar">
        <button class="btn ghost small" id="flujo-limpiar">${icono("basura", "ico-sm")} ${esc(t("flujo.limpiar"))}</button>
        <span class="help-note">${esc(t("flujo.limpiar_sub"))}</span></div>` : ""}
    </div>`;
  })();
  const camino = flujo + `<div class="bandejas-linea">
      ${enlace("por_probar", t("nav.saved") + " · " + cuentas.p)}
      ${enlace("aprobadas", t("nav.aprobadas") + " · " + cuentas.a)}
      ${S.mundo === "metatrader" ? "" : `<button class="linkbtn" data-ir-operar>${esc(t("etapa.operando") + " · " + cuentas.o)}</button>`}
      ${enlace("descartadas", t("saved.descartadas_t") + " · " + cuentas.d)}
    </div>`;

  const subtitulo = BANDEJA === "aprobadas" ? t("saved.sub_aprobadas")
    : BANDEJA === "descartadas" ? t("saved.sub_descartadas") : t("saved.sub_probar");
  const vacia = !visibles.length ? `<div class="card"><div class="empty-state">
      <div class="big">${icono(BANDEJA === "aprobadas" ? "estrella" : BANDEJA === "descartadas" ? "basura" : "tilde", "ico-xl")}</div>
      <b>${esc(t(BANDEJA === "aprobadas" ? "saved.vacio_aprobadas" : BANDEJA === "descartadas" ? "saved.vacio_descartadas" : "saved.vacio_probar"))}</b>
      ${BANDEJA === "descartadas" ? "" : `<p class="mt">${esc(t(BANDEJA === "aprobadas" ? "saved.vacio_aprobadas_sub" : "saved.vacio_probar_sub"))}</p>
      <button class="btn mt" id="bandeja-ir">${esc(t(BANDEJA === "aprobadas" ? "saved.vacio_aprobadas_btn" : "saved.vacio_probar_btn"))}</button>`}
    </div></div>` : "";
  main.innerHTML = pageHead(TITULOS().saved, esc(subtitulo)) + camino +
    `${/* QUÉ HACE LA PRUEBA, sólo en la bandeja de Probar: dos preguntas y
          sin jerga, abierta la primera vez, con el recorrido animado. */
      BANDEJA === "por_probar" ? `
    <details class="que-es" ${localStorage.getItem("qf.vio_prueba") === "1" ? "" : "open"}>
      <summary>${icono("idea", "ico-sm")} ${esc(t("saved.que_es_t"))}</summary>
      <p>${t("saved.que_es")}</p>
      ${explicacionHTML("prueba-pagina", PASOS_PRUEBA())}
    </details>` : ""}` + vacia +
    `${PRUEBAS && sinProbar && BANDEJA === "por_probar" && !COLA_PRUEBAS ? `<div class="pista mb pista-accion">${icono("idea", "ico-sm")}
       <div>${esc(t("saved.pending", { n: sinProbar }))}</div>
       <button class="btn small" id="probar-faltan">${esc(t("saved.probar_faltan", { n: sinProbar }))}</button></div>` : ""}
    ${/* QUE EL PORTAFOLIO SE SEPA QUE EXISTE, sin ponerse en el camino.

           El conjunto ya se arma tildando dos o más, y esa casilla no se ve
           hasta que uno la busca. Quien viene por una estrategia sola no tiene
           por qué enterarse de nada — por eso la línea aparece SOLO cuando ya
           hay dos guardadas, que es cuando la pregunta "¿y si las combino?"
           se puede contestar.

           Con una sola guardada no dice nada: sería vender algo que todavía
           no se puede hacer. */
      PORTAFOLIO && BANDEJA === "aprobadas" && visibles.length >= 2
        ? `<div class="pista mb">${icono("idea", "ico-sm")}
             <div>${esc(t("saved.combinar", { n: visibles.length }))}</div>
           </div>`
        : ""}
    <div class="card" ${visibles.length ? "" : "hidden"}>
      <h2>${esc(TITULOS().saved)} <span class="hint">${esc(t("saved.hint"))}</span></h2>
      ${PORTAFOLIO && visibles.length ? `<div class="sel-rapida"><span>${esc(t("sel.rapida"))}</span>
        <button class="linkbtn" data-sel-est="todas">${esc(t("etapa.todas_corto"))}</button>
        <button class="linkbtn" data-sel-est="aprobada">${esc(t("est.aprobada"))}</button>
        <button class="linkbtn" data-sel-est="aceptable">${esc(t("est.aceptable"))}</button>
        <button class="linkbtn" data-sel-est="no_paso">${esc(t("est.no_paso"))}</button>
        <button class="linkbtn" data-sel-est="sin_probar">${esc(t("est.sin_probar"))}</button>
        <button class="linkbtn" data-sel-est="ninguna">${esc(t("ui.clear"))}</button></div>` : ""}
      <div class="scroll-x"><table class="guardadas">
        <thead><tr>${PORTAFOLIO ? `<th class="tick"><input type="checkbox" id="sel-todas-guardadas"
            ${visibles.length && visibles.every(x => SEL_PF.has(x.id)) ? "checked" : ""}
            aria-label="${esc(t("ui.select_all"))}" title="${esc(t("ui.select_all"))}"></th>` : ""}
          <th>${esc(t("col.strategy"))}</th><th>${esc(t("mine.market"))}</th>
          <th class="num">${esc(t("col.annual"))}</th>
          <th class="num">${esc(t("col.maxdd"))}</th>
          ${PRUEBAS ? `<th title="${esc(t("est.help"))}">${esc(t("col.status"))}</th>
          <th title="${esc(t("col.prueba_help"))}">${esc(t("col.prueba"))}</th>` : ""}
          <th></th></tr></thead>
        <tbody>${visibles.length ? visibles.map(fila).join("")
          : `<tr><td colspan="7"><div class="empty-state" style="padding:24px">${
              esc(t("etapa.vacia"))}</div></td></tr>`}</tbody>
      </table></div>
    </div>
    <div class="barra-sel" id="barra-pf" hidden></div>`;

  $$("[data-bandeja]", main).forEach(b => b.onclick = () => navigate("saved", b.dataset.bandeja));
  const irOp = $("[data-ir-operar]", main); if (irOp) irOp.onclick = () => navigate("operar", "bot");
  const limpiarBtn = $("#flujo-limpiar", main);
  if (limpiarBtn) limpiarBtn.onclick = () => { limpiar(recienProbadas.map(x => x.id)); navigate("saved", "por_probar"); };
  const irB = $("#bandeja-ir", main);
  if (irB) irB.onclick = () => (BANDEJA === "aprobadas" ? navigate("mining", "buscar") : navigate("saved", "aprobadas"));
  if (BANDEJA === "por_probar") atarExplicacion(main, "prueba-pagina", PASOS_PRUEBA());
  /* LA SALA DE ESPERA SE VACÍA SOLA. El Piloto prueba por su cuenta y la
     pantalla no se enteraba hasta recargar: cada 20 s se pregunta, y si
     cambió lo que hay en la bandeja se repinta (nunca mientras corre una
     prueba desde acá, para no pisar sus barras). */
  const huella = () => (S.saved || []).map(x => x.id + ":" + etapaDe(x) + ":" + ((x.validacion || {}).estado || "")).sort().join("|");
  const antes = huella();
  const vigia = setInterval(async () => {
    if (!document.body.contains(main) || S.page !== "saved") { clearInterval(vigia); return; }
    if (COLA_PRUEBAS) return;
    await refreshSavedCount();
    if (huella() !== antes) { clearInterval(vigia); navigate("saved", S.vista); }
  }, 20000);
  /* ABIERTA LA PRIMERA VEZ, PLEGADA DESPUÉS: la primera vez es la única en
     que hace falta leerla; después molesta. */
  try { localStorage.setItem("qf.vio_prueba", "1"); } catch (e) { /* nada */ }
  const faltan = $("#probar-faltan", main);
  /* SI LA COLA YA ESTÁ CORRIENDO, el cartel no ofrece empezar de nuevo:
     apretarlo otra vez duplicaba pruebas (2 de septiembre). */
  if (faltan && COLA_PRUEBAS) {
    faltan.replaceWith(Object.assign(document.createElement("span"),
      { className: "help-note", textContent: t("saved.probando_faltan", { n: COLA_PRUEBAS.total }) }));
  } else if (faltan) faltan.onclick = () => {
    /* EL CARTEL SE APAGA AL APRETARLO: seguía ofreciendo "probar las 5" con
       las cinco ya en cola, y parecía que había que volver a apretar. */
    const n = faltan.textContent.match(/\d+/)?.[0] || "";
    faltan.disabled = true;
    faltan.replaceWith(Object.assign(document.createElement("span"),
      { className: "help-note", textContent: t("saved.probando_faltan", { n }) }));
    probarVarias(items.filter(x => !estaRetirada(x) && estadoDe(x) === "sin_probar"), main);
  };

  /* LA BARRA DE SELECCIÓN SIRVE DESDE UNA. Antes aparecía recién con dos y
     sólo para combinar; ahora con una o más ofrece probar, combinar (dos o
     más) y borrar, que es lo que se quiere hacer con varias a la vez. */
  const pintarBarra = () => {
    const barra = $("#barra-pf", main);
    const n = SEL_PF.size;
    barra.hidden = n < 1;
    if (n < 1) return;
    // de las visibles: el conjunto ya está podado, y esto lo deja explícito
    // para el que lo lea después
    const elegidas = visibles.filter(x => SEL_PF.has(x.id));
    const probables = elegidas.filter(x => !estaRetirada(x));
    barra.innerHTML = `<span>${esc(t("ui.selected", { n }))}</span>
      <button class="linkbtn" id="pf-nada">${esc(t("ui.clear"))}</button>
      <span class="barra-acciones">
        <button class="btn ghost" id="sel-borrar">${icono("cerrar")} ${esc(t("sel.borrar", { n }))}</button>
        ${PORTAFOLIO && n >= 2 ? `<button class="btn ${BANDEJA === "aprobadas" ? "" : "ghost"}" id="pf-ver">${esc(t("saved.armar", { n }))}</button>` : ""}
        ${PRUEBAS && probables.length ? `<button class="btn" id="sel-probar">${
          esc(t("sel.probar", { n: probables.length }))}</button>` : ""}
      </span>`;
    $("#pf-nada", barra).onclick = () => {
      SEL_PF.clear();
      $$("[data-pf]", main).forEach(cb => { cb.checked = false; });
      $$("tr[data-sid]", main).forEach(tr => tr.classList.remove("elegida"));
      pintarBarra();
    };
    const ver = $("#pf-ver", barra);
    if (ver) ver.onclick = () => abrirPortafolio(elegidas);
    const probar = $("#sel-probar", barra);
    if (probar) probar.onclick = () => probarVarias(probables, main);
    $("#sel-borrar", barra).onclick = async () => {
      if (!confirm(t("sel.confirm_delete", { n }))) return;
      try {
        for (const s of elegidas) await api.del(`/api/strategies/${s.id}`);
        SEL_PF.clear();
        toast(t("sel.borradas", { n }), "ok");
        navigate("saved");
      } catch (e) {
       toast(e.message, "err"); }
    };
  };
  pintarBarra();

  $$("[data-pf]", main).forEach(cb => cb.onchange = (ev) => {
    ev.stopPropagation();
    const sid = cb.dataset.pf;
    if (cb.checked) SEL_PF.add(sid); else SEL_PF.delete(sid);
    cb.closest("tr").classList.toggle("elegida", cb.checked);
    pintarBarra();
  });
  /* TODAS LAS VISIBLES DE UNA VEZ: con el filtro en "Por probar", tildar
     todas y apretar "Probar N" es probar todo lo que falta en dos clics. */
  const aplicarSel = () => {
    $$("[data-pf]", main).forEach(cb => {
      cb.checked = SEL_PF.has(cb.dataset.pf);
      cb.closest("tr").classList.toggle("elegida", cb.checked);
    });
    const th = $("#sel-todas-guardadas", main);
    if (th) th.checked = visibles.length > 0 && visibles.every(x => SEL_PF.has(x.id));
    pintarBarra();
  };
  $$("[data-sel-est]", main).forEach(bt => bt.onclick = () => {
    const que = bt.dataset.selEst;
    SEL_PF.clear();
    if (que === "todas") visibles.forEach(x => SEL_PF.add(x.id));
    else if (que !== "ninguna") visibles.filter(x => !estaRetirada(x) && estadoDe(x) === que).forEach(x => SEL_PF.add(x.id));
    aplicarSel();
  });
  const todasG = $("#sel-todas-guardadas", main);
  if (todasG) todasG.onchange = () => {
    visibles.forEach(x => { if (todasG.checked) SEL_PF.add(x.id); else SEL_PF.delete(x.id); });
    $$("[data-pf]", main).forEach(cb => {
      cb.checked = SEL_PF.has(cb.dataset.pf);
      cb.closest("tr").classList.toggle("elegida", cb.checked);
    });
    pintarBarra();
  };

  $$("[data-sid]", main).forEach(tr => tr.onclick = (ev) => {
    if (ev.target.closest("button") || ev.target.closest(".tick")) return;
    openSaved(items.find(x => x.id === tr.dataset.sid));
  });

  $$("[data-export]", main).forEach(b => b.onclick = async () => {
    const s = items.find(x => x.id === b.dataset.export);
    b.disabled = true;
    try {
      // lo escribe el servidor, que corre en esta misma máquina: la ventana
      // nativa cancela las descargas del navegador y el botón no hacía nada
      /* AL MISMO LUGAR QUE DESDE LA FICHA: la fila mandaba a Descargas y la
         ficha al terminal elegido, así que el mismo robot terminaba en dos
         carpetas distintas (2 de septiembre). */
      const cuerpoFila = {
        spec: s.spec, name: `BQ_${s.name.replace(/[^\w]/g, "_")}`,
        dataset_id: (s.meta || {}).dataset_id,
        timeframe: (s.meta || {}).timeframe, metrics: (s.meta || {}).metrics,
        server_utc_offset: S.cfg.brokerUtc,
      };
      if (S.mt5.elegido) cuerpoFila.terminal = S.mt5.elegido;
      const r = await api.post("/api/export/mql5/archivo", cuerpoFila);
      toast(t("exp.saved_in", { archivo: r.archivo, carpeta: r.carpeta }), "ok");
      if (S.mundo === "metatrader") primerPaso("encendiste");
    } catch (e) {
       if (!pedirCuenta(e.status)) toast(e.message, "err"); }
    b.disabled = false;
  });

  $$("[data-probar]", main).forEach(b => b.onclick = async () => {
    const s = items.find(x => x.id === b.dataset.probar);
    await correrPrueba(s, b);
  });
  $$("[data-encender]", main).forEach(b => b.onclick = () => encenderDirecto(
    items.find(x => x.id === b.dataset.encender), b));
  $$("[data-ver-robot]", main).forEach(b => b.onclick = () => navigate("operar", "bot"));
  $$("[data-retirar]", main).forEach(b => b.onclick = async () => {
    const s = items.find(x => x.id === b.dataset.retirar);
    const motivo = prompt(t("saved.retirar_motivo", { nombre: s.name }));
    if (motivo == null || !motivo.trim()) return;
    try {
      await api.post(`/api/strategies/${s.id}/estado`, { estado: "retirada", motivo: motivo.trim() });
      toast(t("saved.retirada"), "ok");
      navigate("saved");
    } catch (e) {
       toast(e.message, "err"); }
  });

  $$("[data-del-strat]", main).forEach(b => b.onclick = async () => {
    const s = items.find(x => x.id === b.dataset.delStrat);
    if (!confirm(t("saved.confirm_delete", { nombre: s.name }))) return;
    try {
      await api.del(`/api/strategies/${s.id}`);
      toast(t("saved.deleted"), "ok");
      navigate("saved");
    } catch (e) {
       toast(e.message, "err"); }
  });
};

/* VARIAS EN COLA, UNA POR VEZ. El servidor corre una prueba por usuario a
   la vez, así que en paralelo no ganaría nada; en cola cada fila muestra su
   avance y al final un resumen dice cuántas pasaron. Se puede seguir usando
   el resto de la aplicación mientras tanto: la cola vive fuera de la
   pantalla, y si la pantalla se repinta, la cola sigue. */
let COLA_PRUEBAS = null;
const COLA_PENDIENTE = [];

/* GUARDAR NO ES PROBAR. Acá decía lo contrario: "nadie guarda una estrategia
   para no probarla", y lo que se mandaba a Probar entraba solo en la cola de
   walk-forward. Con una búsqueda que deja veinticinco, eran veinticinco
   pruebas de cuatro tramos cada una arrancando sin que nadie las pidiera, y el
   servidor quedaba ocupado hasta que la aplicación se arrastraba: abrir una
   ficha tardaba más de 45 segundos. El usuario lo dijo con todas las letras
   el 3 de septiembre de 2026: "eso lo debería hacer manualmente el usuario".

   Ahora mandar a Probar las deja en la bandeja Probar, contadas y a la vista.
   Probar es un botón: "Probar N" con las elegidas, o "Probar las N que
   faltan" arriba de la lista. La cola sigue existiendo para eso. */
function encolarPruebas(ids) {
  const n = (ids || []).filter(Boolean).length;
  if (n) refreshSavedCount();
}

async function probarVarias(lista, main) {
  if (!lista.length || COLA_PRUEBAS) { COLA_PENDIENTE.push(...lista); return; }
  COLA_PRUEBAS = { total: lista.length, hechas: 0, ids: lista.map(x => x.id) };
  const cuenta = { aprobada: 0, aceptable: 0, no_paso: 0, error: 0 };
  toast(t("sel.en_cola", { n: lista.length }), "ok");
  for (let i = 0; i < lista.length; i++) {
    const s = lista[i];
    if (!s.name) { const f = (S.saved || []).find(x => x.id === s.id); if (f) Object.assign(s, f); }
    const boton = $(`[data-probar="${s.id}"]`, document);
    let avance = () => {};
    if (boton) {
      boton.disabled = true;
      boton.innerHTML = `${i + 1}/${lista.length}`;
      avance = barraPrueba(boton.closest("tr")?.querySelector(".celda-estado") || null, boton);
    }
    try {
      /* EL SERVIDOR PRUEBA DE A UNA. Si está ocupado —minando, o el Piloto
         probando lo suyo— contesta 429; antes eso se contaba como error en
         silencio. Ahora se espera lugar y se vuelve a intentar, diciéndolo. */
      let r = null;
      for (let intento = 0; ; intento++) {
        try { r = await probarEstrategia(s.id, avance); break; }
        catch (e) {
          if (e.status !== 429 || intento >= 40) throw e;
          avance({ progress: 0, message: t("sel.esperando") });
          await sleep(15000);
        }
      }
      // el trabajo devuelve el veredicto arriba o bajo `validacion`, según
      // el camino; se acepta cualquiera de los dos
      const v = (r && (r.validacion || r)) || {};
      cuenta[v.estado in cuenta ? v.estado : "error"] += 1;
      RECIEN_PROBADAS.add(s.id);
      primerPaso("probaste");
      avisarVeredicto(s.id);
      if (S.page === "saved" && S.vista !== "aprobadas") await navigate("saved", S.vista);
    } catch (e) {
      cuenta.error += 1;
      if (pedirCuenta(e.status)) break;
    }
    COLA_PRUEBAS.hechas = i + 1;
    // lo que se agregó mientras corría, al final de esta misma cola
    if (COLA_PENDIENTE.length) {
      lista.push(...COLA_PENDIENTE.splice(0));
      COLA_PRUEBAS.total = lista.length;
      COLA_PRUEBAS.ids = lista.map(x => x.id);
    }
  }
  COLA_PRUEBAS = null;
  /* EL VEREDICTO SE AVISA AUNQUE NO ESTÉS MIRANDO: la usuaria de prueba
     cambió de pantalla y no supo nunca que su estrategia había aprobado. */
  toast(t("sel.resumen", { a: cuenta.aprobada, m: cuenta.aceptable, f: cuenta.no_paso })
        + (cuenta.error ? ` · ${t("sel.errores", { n: cuenta.error })}` : ""), "ok");
  SEL_PF.clear();
  if (S.page === "saved") await navigate("saved", S.vista);
  else await refreshSavedCount();
}

/* Corre la prueba desde un botón cualquiera y deja el botón contando.
   El walk-forward reajusta la estrategia en cada tramo, así que tarda: sin
   avisar del progreso se ve igual que un botón roto. */
/* LA PRUEBA SE VE AVANZAR: una barra que se llena y "Probando…" con los
   puntos moviéndose, en lugar de un circulito que gira igual al segundo
   que al minuto tres. Va en la celda de estado de la fila —donde después
   aparece el veredicto— o al lado del botón, en la ficha. */
function barraPrueba(anfitrion, boton) {
  const barra = document.createElement("div");
  barra.className = "prueba-progreso";
  barra.innerHTML = `<span class="pp-txt">${esc(t("wf.testing"))}<i class="puntos" aria-hidden="true"></i></span>
    <div class="pp-bar"><i></i></div><span class="pp-det"></span>`;
  if (anfitrion) { anfitrion.innerHTML = ""; anfitrion.appendChild(barra); }
  else boton.insertAdjacentElement("afterend", barra);
  return (j) => {
    const pct = Math.max(2, Math.round((j.progress || 0) * 100));
    $(".pp-bar i", barra).style.transform = `scaleX(${pct / 100})`;
    const m = String(j.message || "").match(/^Fold (\d+)\/(\d+): Evaluated (\d+)\/(\d+)/);
    const que = m ? t("wf.avance", { k: m[1], n: m[2], i: m[3], m: m[4] })
      : /rebaraj/i.test(j.message || "") ? t("wf.avance_baraja")
      : /prepar/i.test(j.message || "") ? t("wf.avance_prepara") : (j.message || "");
    $(".pp-det", barra).textContent = `${pct}%` + (que ? ` · ${que}` : "");
  };
}

async function correrPrueba(s, boton) {
  const original = boton.innerHTML;
  boton.disabled = true;
  boton.innerHTML = esc(t("wf.testing"));
  const celda = boton.closest("tr")?.querySelector(".celda-estado") || null;
  const chipOriginal = celda ? celda.innerHTML : "";
  const avance = barraPrueba(celda, boton);
  try {
    await probarEstrategia(s.id, avance);
    toast(t("wf.done", { nombre: s.name }), "ok");
    RECIEN_PROBADAS.add(s.id);
    primerPaso("probaste");
    // y el aviso dice dónde quedó, con un atajo para ir a verla
    avisarVeredicto(s.id);
    /* LA FILA SE VA: lo probado deja Probar y aparece en su bandeja nueva.
       Se la ve salir antes de repintar, para que el movimiento cuente la
       regla de las bandejas. */
    if (S.page === "saved") await navigate("saved", S.vista); else await refreshSavedCount();
  } catch (e) {
    if (!pedirCuenta(e.status)) toast(e.message, "err");
    boton.disabled = false;
    boton.innerHTML = original;
    if (celda) celda.innerHTML = chipOriginal;
    else $(".prueba-progreso", boton.parentElement)?.remove();
  }
}

/* Re-analiza una guardada sobre su propio instrumento y sus propios costos,
   no sobre lo que esté configurado ahora en la página de Mining. */
async function openSaved(s) {
  const meta = s.meta || {};
  if (!meta.dataset_id || !S.datasets.some(d => d.id === meta.dataset_id)) {
    toast(t("err.dataset_gone"), "err");
    return;
  }
  const row = {
    name: s.name, blocks: meta.blocks || "", genes_label: meta.genes_label || "",
    spec: s.spec, metrics: meta.metrics || {}, score: meta.score,
    stop_mult: meta.stop_mult, oos: meta.oos, oos_ratio: meta.oos_ratio,
    fitness: 0, spark: [],
  };
  /* El tramo tiene que ser el mismo con el que se midió, o el backtest corre
     sobre toda la historia y devuelve otra estrategia distinta con el mismo
     nombre. Las guardadas antes de que esto se registrara no lo tienen: se
     avisa en vez de mostrar números que no coinciden con la fila. */
  const r = meta.measured_range;
  openInspector(row, {
    dataset_id: meta.dataset_id, timeframe: meta.timeframe || "1h",
    date_from: r ? r.from : undefined,
    date_to: r ? r.to : undefined,
    sinRango: !r,
    // el id y la nota van al contexto para que el inspector pueda ofrecer
    // escribir por qué se guardó esta estrategia
    strategy_id: s.id, notes: s.notes || "",
    // el veredicto guardado: sin esto la ficha no puede mostrar el estado ni
    // saber si ofrecer "poner a prueba" o "volver a probar"
    validacion: s.validacion || {},
    /* El corte con el que se mino, para las tres vistas de la curva. Las
       guardadas antes de que esto se registrara no lo tienen y las pestanias
       simplemente no aparecen, como antes: no hay forma de reconstruirlo. */
    split: meta.split || null,
    settings: { spread: meta.spread, slippage: meta.slippage,
                commission_pct: meta.commission, swap_anual: meta.swap, initial_capital: meta.capital },
  });
}

/* ══════════════════════════════════════════════ LA CAÍDA, GRADUADA ════════
   El drawdown estaba SIEMPRE en rojo, en los siete lugares donde se dibuja.
   Una caída del 4,6% y una del 33,8% salían idénticas, así que el color no
   distinguía nada: pintar todo de rojo es lo mismo que no pintar nada, salvo
   que además gasta la señal para cuando de verdad hace falta.

   Las bandas salen de medir el banco, no de una intuición. Sobre las 150
   estrategias que había: la mediana cae 12,3%, tres de cada cuatro se quedan
   por debajo de 18,7% y la décima parte más brava pasa de 25%. Con los cortes
   en 15 y 25, el ámbar marca "mirala antes de confiar" y el rojo marca ese
   último décimo — que es lo que un color de alarma tiene que hacer.

   Y escalan con el riesgo por operación, porque la caída escala con él igual
   que el rendimiento —está dicho en COLS_CON_RIESGO y es la razón de que esas
   dos columnas no se puedan comparar entre corridas—. Al 3% por operación
   todo se multiplica por tres: una banda fija llamaría grave a una estrategia
   que arriesga el triple y cae exactamente lo mismo.

   Con lotes fijos no hay perilla que leer, así que se usa la banda base y se
   dice acá que es una aproximación, en vez de inventar una normalización. */
const DD_ATENCION = 15, DD_GRAVE = 25;        /* al 1% por operación */

function nivelDD(dd, riesgo) {
  if (dd == null || !isFinite(dd)) return "";
  /* El tope evita que un riesgo absurdo —0,05% o 20%— convierta la escala en
     otra cosa. Fuera de ese rango la normalización deja de tener sentido
     físico y es más honesto quedarse cerca de la banda base. */
  const k = Math.max(0.25, Math.min(4, +riesgo || 1));
  const rel = Math.abs(dd) / k;
  if (rel >= DD_GRAVE) return "dd-grave";
  if (rel >= DD_ATENCION) return "dd-atencion";
  return "dd-calma";
}

/* El riesgo por operación de un contexto guardado, en por ciento.

   Devuelve null con lotes fijos: ahí el tamaño no se expresa como fracción
   del capital y no hay con qué normalizar. */
function riesgoDeCtx(ctx) {
  if (!ctx) return null;
  const modo = ctx.sizing ?? ctx.size_mode;
  if (modo === "lots" || modo === "fixed_units") return null;
  return ctx.riskPct ?? ctx.size_value ?? null;
}

/* El riesgo de la configuración que está en pantalla ahora mismo. */
function riesgoActual() {
  return S.cfg.sizing === "lots" ? null : S.cfg.riskPct;
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
const VARA = () => [
  ...CRITERIA().map(cr => [CRIT_FIELD[cr.key], cr.label, cr.unit]),
  // ya no se ofrece como filtro, pero las corridas archivadas lo tienen
  ["min_net_pct", `${t("m.net")} ≥`, "%"],
];

/* Las columnas que dependen del tamaño de posición. Un riesgo del 3% por
   operación da más o menos el triple de rendimiento Y el triple de caída que
   el 1%: ordenar una lista mezclada por estas columnas ordena por la perilla
   de riesgo, no por la calidad de la estrategia. Las otras —profit factor,
   score, aciertos, meses positivos— son proporciones y no se mueven con el
   tamaño, así que sí comparan de verdad. */
const COLS_CON_RIESGO = new Set(["cagr", "dd"]);

/* `hayOos` decide si vale la pena gastar una columna.

   Salía siempre, y cuando ninguna corrida a la vista reservó un tramo son
   ciento cincuenta guiones debajo de un encabezado que además parte en dos
   líneas. Una columna entera vacía no es información: es ancho que le falta
   a las que sí tienen algo que decir. */
const BANCO_COLS = (hayOos = true) => [
  ["score", t("m.score"), t("col.score_help")],
  ["cagr", t("col.annual"), t("bank.cagr_help")],
  ["pf", "PF", t("bank.pf_help")],
  ["dd", t("col.maxdd"), t("bank.dd_help")],
  ["trades", t("col.ops"), t("col.ops_help")],
  ["months", t("col.months_plus"), t("col.months_help")],
  ...(hayOos ? [["oos", t("col.oos"), t("col.oos_help")]] : []),
];

/* El instrumento sin la temporalidad ni la fuente: "SP500 M1 (Dukascopy)" es
   el nombre del archivo, "SP500" es el mercado.

   Recortaba solo " M1...", y los datos que VIENEN CON LA APLICACION se llaman
   "SP500 H1 (Dukascopy)". O sea que funcionaba en nuestra maquina —que tiene
   los M1 descargados— y no funcionaba en ninguna instalacion nueva: ahi el
   nombre salia entero en las burbujas de corrida, en la columna de origen del
   Databank y en la pastilla de cada estrategia.

   Pide letra Y numero pegados al final para no comerse un CSV propio que se
   llame "Mis datos 2020": ahi el ultimo trozo no lleva letra adelante. */
/* Una corrida cuyo histórico se borró desde Datos quedaba como "—": una
   burbuja sin nombre entre las demás, sin decir qué era. Se dice. */
const nombreCorto = (s) =>
  String(s || t("bank.sin_instrumento")).replace(/\s+(?:M|H|D|W|MN)\d+\s*(?:\(.*)?$/i, "");

/* Cuándo corrió, dicho como se acuerda uno.

   Ocho búsquedas sobre el mismo instrumento y la misma temporalidad daban
   ocho burbujas idénticas —"SP500 · 1h" arriba, "25 · riesgo 1%" abajo, en
   todas— y elegir una era una lotería. La hora es lo que las separa porque es
   lo que uno recuerda: "la de recién", "la de ayer".

   La `Z` del final no es adorno. El servidor guarda en UTC (`db.py`) y sin
   ella el navegador lo lee como hora local: en Buenos Aires una corrida de
   hace un minuto aparecía tres horas en el futuro. */
function cuando(iso) {
  if (!iso) return "";
  const s = String(iso).trim().replace(" ", "T");
  const d = new Date(/[Z+]|-\d\d:\d\d$/.test(s) ? s : s + "Z");
  if (isNaN(d.getTime())) return "";
  const hoy = new Date();
  const ayer = new Date(hoy); ayer.setDate(hoy.getDate() - 1);
  const dia = x => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`;
  const hora = d.toLocaleTimeString(localeNum(), HORA());
  if (dia(d) === dia(hoy)) return t("time.today", { hora });
  if (dia(d) === dia(ayer)) return t("time.yesterday", { hora });
  return d.toLocaleDateString(localeNum(), d.getFullYear() === hoy.getFullYear()
    ? { day: "numeric", month: "short" }
    : { day: "numeric", month: "short", year: "2-digit" });
}

function etiquetaCorrida(c) {
  return `${nombreCorto(c.dataset_name)} · ${c.timeframe || "1h"}`;
}

/** El riesgo por operación de una corrida, que es lo que hace comparables (o
 *  no) sus números con los de otra. */
function riesgoDe(c) {
  const r = (c.contexto || {}).risk || {};
  return r.size_mode === "fixed_units" ? `${r.size_value} ${t("mine.lots")}` : `${r.size_value ?? "—"}%`;
}

function varaDe(c) {
  const acc = (c.contexto || {}).accept || {};
  const puestos = VARA().filter(([k]) => acc[k] != null)
    .map(([k, lab, u]) => `${lab} ${acc[k]}${u}`);
  const min = (c.contexto || {}).min_trades;
  if (min) puestos.unshift(`${min}+ ${t("m.trades").toLowerCase()}`);
  return puestos.length ? puestos.join(" · ") : t("bank.no_filters");
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

async function cargarBanco({ corridas = true, mas = false } = {}) {
  if (corridas) {
    const r = await api.get("/api/corridas?" + new URLSearchParams({ mundo: S.mundo || "" }));
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
  /* El servidor manda de a doscientas y acepta `desde` para seguir. Esto no
     lo usaba: pedia la primera pagina y dibujaba eso, asi que con el banco
     por encima de doscientas filas el resto quedaba invisible — y el
     encabezado seguia diciendo el total, que era justamente el numero que no
     coincidia con nada. */
  const desde = mas ? S.banco.filas.length : 0;
  const pagina = await api.get("/api/banco?" + new URLSearchParams({
    corrida: S.banco.corrida, orden: s.key, dir: s.dir === 1 ? "asc" : "desc",
    desde: String(desde), mundo: S.mundo || "",
  }));
  S.banco.filas = mas ? S.banco.filas.concat(pagina) : pagina;
  // lo tildado que ya no está (borrado, podado, o de otra corrida) se suelta:
  // si no, el contador diría "5 seleccionadas" con tres filas a la vista
  const vivos = new Set(S.banco.filas.map(f => f.banco_id));
  [...S.banco.sel].forEach(id => { if (!vivos.has(id)) S.banco.sel.delete(id); });
}

/* Cuantas filas hay de verdad para la vista actual.

   No es `filas.length`: eso es lo que llego en las paginas pedidas hasta
   ahora. Y no es siempre el total del banco: con una corrida elegida, la
   poblacion es la de esa corrida. Sin esta distincion no hay forma de saber
   si falta traer mas ni de rotular honestamente el encabezado. */
/* Lo escrito en el buscador del Databank. Vive fuera de S.banco porque no es
   parte de lo que trae el servidor: es una vista sobre lo que ya llego. */
let FILTRO_BANCO = "";

/* Las filas que pasan el filtro. Busca en el nombre, en los bloques que la
   componen y en el instrumento de su corrida — que son las tres formas en que
   uno se acuerda de una estrategia. */
function filasVisibles() {
  const b = S.banco;
  const q = FILTRO_BANCO.trim().toLowerCase();
  if (!q) return b.filas;
  const porId = Object.fromEntries(b.corridas.map(c => [c.id, c]));
  return b.filas.filter(f => {
    const c = porId[f.corrida_id] || {};
    /* `blocks` es lo que se busca de verdad: "Donchian breakout + EMA trend
       filter". `etiquetaGenes` devuelve los PARAMETROS —fast=10, SL=1.75×ATR—
       que nadie recuerda. Se incluyen los dos, mas el instrumento y la franja,
       que son las otras formas en que uno se acuerda de una estrategia. */
    return [f.name, f.blocks, etiquetaGenes(f), f.session_label,
            f.session_label_en, c.dataset_name, c.timeframe]
      .filter(Boolean).join(" ").toLowerCase().includes(q);
  });
}

function poblacionBanco() {
  const b = S.banco;
  if (!b.corrida) return b.total;
  const c = b.corridas.find(x => x.id === b.corrida);
  return c ? c.n : b.filas.length;
}

const vistaResultados = async (main) => {
  await Promise.all([refreshDatasets(), cargarBanco()]);
  const b = S.banco;

  if (!b.corridas.length) {
    main.innerHTML = pageHead(t("mine.tab_results"), esc(t("bank.sub"))) +
      `<div class="card"><div class="empty-state">
        <div class="big">${icono("banco", "ico-xl")}</div>
        <b>${esc(t("bank.empty"))}</b>
        <p class="mt">${esc(t("bank.empty_help"))}</p>
        <button class="btn mt" id="ir-a-minar">${esc(t("ui.go_mining"))}</button>
      </div></div>`;
    $("#ir-a-minar", main).onclick = () => navigate("mining", "buscar");
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
  /* El subtitulo tiene que hablar de la misma poblacion que la tabla de
     abajo. Decia siempre el total del banco, asi que al elegir una corrida el
     encabezado decia noventa y uno con ocho filas debajo. */
  const activa = b.corridas.find(c => c.id === b.corrida);
  host.innerHTML = pageHead(t("mine.tab_results"),
    esc(activa
      ? t("bank.count_run", { n: fmtInt(activa.n), total: fmtInt(b.total) })
      : t("bank.count", { n: fmtInt(b.total), corridas: b.corridas.length })),
    `<div class="ph-pill ${lleno > 0.85 ? "alerta" : ""}">
       <b>${fmtInt(b.total)}</b><u>/${fmtInt(b.tope)}</u>
       <em>${esc(lleno > 0.85 ? t("bank.almost_full") : t("bank.capacity"))}</em></div>`);
  // y el de la barra lateral, que es el mismo dato en otro lado
  pintarNavBanco(b.total);
}

/* Las corridas como una lista, no como pestañas: son hasta cuarenta y cada
   una necesita decir su instrumento, su temporalidad, su riesgo y su vara.
   Eso no entra en una pestaña. */
/* Las cuatro etapas por las que pasa una candidata, con sus números.

   Los datos ya estaban todos en la corrida; lo que faltaba era decir que son
   etapas de una misma cosa y no seis números técnicos sueltos. Puestos en
   fila se lee el recorrido: se construyeron tantas, se tiraron tantas, quedan
   tantas en el banco y tantas están guardadas.

   La proporción es el dato que más se perdía. De tres mil candidatas pasan
   veinticinco: ese 0,8% es lo que uno compra cuando deja la máquina buscando,
   y no estaba escrito en ningún lado.

   Las guardadas se cuentan por `meta.corrida_id`, que es lo que graba el
   servidor al copiar del banco. Las guardadas de antes de ese campo no suman
   — es preferible quedarse corto que inventar una atribución. */
function embudoCorrida(c) {
  if (!c) return "";
  const construidas = c.tested ?? 0;
  const pasaron = c.encontradas ?? c.n ?? 0;
  const tiradas = Math.max(0, construidas - pasaron);
  const enBanco = c.n ?? 0;
  const guardadas = (S.saved || []).filter(s => (s.meta || {}).corrida_id === c.id).length;
  const tasa = construidas ? (pasaron / construidas) * 100 : 0;

  const paso = (n, clave, cls = "", nota = "") => `
    <div class="et ${cls}"><b>${fmtInt(n)}</b><span>${esc(t(clave))}${
      nota ? `<u class="et-nota">${esc(nota)}</u>` : ""}</span></div>`;

  /* Que queden menos de las que pasaron significa que el usuario borró
     algunas, y eso no es lo mismo que no haberlas encontrado nunca. Dicho al
     lado del número, la etapa deja de contradecir a la de su izquierda. */
  const borradas = Math.max(0, pasaron - enBanco);

  return `<div class="embudo">
    ${paso(construidas, "state.built")}
    ${paso(tiradas, "state.discarded", "et-tirada")}
    ${paso(enBanco, "state.kept", "et-banco",
           borradas ? t("state.removed", { n: fmtInt(borradas) }) : "")}
    ${paso(guardadas, "state.saved", "et-guardada")}
  </div>
  <p class="embudo-tasa">${esc(t("state.rate", {
    tasa: tasa >= 10 ? fmtNum(tasa, 0) : fmtNum(tasa, 1),
    n: fmtInt(pasaron), total: fmtInt(construidas) }))}</p>`;
}

function pintarCorridas() {
  const host = $("#banco-corridas");
  if (!host) return;
  const b = S.banco;
  const activa = b.corridas.find(c => c.id === b.corrida);

  /* Las que no tienen ninguna estrategia van aparte.

     No se borran: una búsqueda que no encontró nada es el experimento que más
     conviene tener anotado —dice que con esa vara, sobre ese mercado, no pasó
     ninguna de novecientas— y sin ese registro se vuelve a intentar lo mismo
     dentro de un mes.

     Pero tampoco pueden ocupar el mismo lugar que las que sí encontraron algo:
     con quince búsquedas fallidas la pantalla se llena de burbujas que dicen
     "sin resultados" y parece que la aplicación está rota. Van agrupadas
     detrás de una línea que se abre si hacen falta. */
  const conAlgo = b.corridas.filter(c => c.n);
  const vacias = b.corridas.filter(c => !c.n);
  /* Y LAS VIEJAS TAMPOCO PESAN LO MISMO QUE LAS DE HOY. Con cuarenta
     búsquedas la pantalla era una pared de burbujas iguales —"SP500 · 1h ·
     30 · 23 ago" ocho veces— y la corrida recién terminada se perdía entre
     ellas. Quedan a la vista las doce últimas; las demás, detrás de una
     línea que se abre, y abierta de entrada si la elegida está ahí. */
  const RECIENTES = 12;
  const recientes = conAlgo.slice(0, RECIENTES);
  const viejas = conAlgo.slice(RECIENTES);
  const viejaElegida = viejas.some(c => c.id === b.corrida);

  host.innerHTML = `<div class="card">
    <h2>${esc(t("bank.runs"))} <span class="hint">${esc(t("bank.runs_hint"))}</span></h2>
    <div class="corridas-lista">
      <button class="corrida-chip ${b.corrida ? "" : "on"}" data-corrida="">
        <b>${esc(t("bank.all"))}</b><span>${fmtInt(b.total)} ${esc(t("ui.strategies"))}</span></button>
      ${recientes.map(c => `
        <button class="corrida-chip ${b.corrida === c.id ? "on" : ""}"
          data-corrida="${esc(c.id)}" title="${esc(varaDe(c))}">
          <b>${esc(etiquetaCorrida(c))}<i class="chip-n">${fmtInt(c.n)}</i></b>
          <span>${esc(cuando(c.created))} · ${esc(t("bank.risk"))} ${esc(riesgoDe(c))}</span>
        </button>`).join("")}
    </div>
      ${viejas.length ? `<details class="corridas-vacias"${viejaElegida ? " open" : ""}>
        <summary>${esc(t("bank.viejas", { n: viejas.length }))}</summary>
        <div class="corridas-lista">
          ${viejas.map(c => `
            <button class="corrida-chip ${b.corrida === c.id ? "on" : ""}"
              data-corrida="${esc(c.id)}" title="${esc(varaDe(c))}">
              <b>${esc(etiquetaCorrida(c))}<i class="chip-n">${fmtInt(c.n)}</i></b>
              <span>${esc(cuando(c.created))} · ${esc(t("bank.risk"))} ${esc(riesgoDe(c))}</span>
            </button>`).join("")}
        </div>
      </details>` : ""}
      ${vacias.length ? `<details class="corridas-vacias">
        <summary>${esc(t("bank.vacias", { n: vacias.length }))}</summary>
        <div class="corridas-lista">
          ${vacias.map(c => `
            <button class="corrida-chip vacia ${b.corrida === c.id ? "on" : ""}"
              data-corrida="${esc(c.id)}" title="${esc(varaDe(c))}">
              <b>${esc(etiquetaCorrida(c))}</b>
              <span>${esc(cuando(c.created))} · ${esc(t("bank.no_results"))}</span>
            </button>`).join("")}
        </div>
      </details>` : ""}
    ${activa ? `
      <div class="corrida-ficha">
        <!-- Primero el recorrido —qué le pasó a cada candidata— y recién
             después los datos técnicos de la corrida. Estaban todos mezclados
             en una grilla de seis, así que las etapas no se leían como
             etapas: la semilla pesaba lo mismo que cuántas sobrevivieron. -->
        ${embudoCorrida(activa)}
        <div class="cf-datos">
          <div><span>${esc(t("bank.took"))}</span><b>${fmtDur(activa.elapsed)}</b></div>
          <div><span>${esc(t("bank.ended"))}</span><b>${esc(t("ended." + activa.ended))}</b></div>
          <div><span>${esc(t("bank.seed"))}</span><b>${activa.seed ?? "—"}</b></div>
          <div><span>${esc(t("mine.direction"))}</span><b>${
            esc(t("dir." + ((activa.contexto || {}).direction || "long")).toLowerCase())}</b></div>
        </div>
        <p class="cf-vara"><span>${esc(t("bank.bar"))}</span> ${esc(varaDe(activa))}</p>
        <div class="cf-acciones">
          <button class="btn ghost small" id="repetir-corrida">${esc(t("bank.repeat"))}</button>
          <button class="linkbtn peligro" id="borrar-corrida">${icono("basura","ico-sm")} ${esc(t("bank.delete_run"))}</button>
        </div>
        <p class="stage-note">${esc(t("bank.repeat_note"))}</p>
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
    /* La cabecera tambien. Sin esto seguia diciendo el total del banco entero
       con la tabla filtrada debajo: "38 estrategias de 4 corridas" arriba de
       ocho filas. Es el numero que no coincidia con nada. */
    pintarCabecera();
    pintarCorridas();
    pintarBanco();
  });

  const repetir = $("#repetir-corrida", host);
  if (repetir) repetir.onclick = () => repetirCorrida(activa);

  const borrar = $("#borrar-corrida", host);
  if (borrar) borrar.onclick = async () => {
    if (!confirm(t("bank.confirm_delete_run", {
      nombre: etiquetaCorrida(activa), n: activa.n }))) return;
    try {
      await api.del(`/api/corridas/${activa.id}`);
      S.banco.corrida = "";
      S.banco.sel.clear();
      await cargarBanco();
      pintarCabecera();
      pintarCorridas();
      pintarBanco();
      toast(t("bank.run_deleted"), "ok");
    } catch (e) {
       toast(e.message, "err"); }
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
  // lo que se dibuja es lo que pasa el buscador; `b.filas` sigue siendo todo
  // lo que llego, que es lo que hace falta para contar y para el "ver mas"
  const filas = filasVisibles();
  const filtrando = FILTRO_BANCO.trim().length > 0;

  const riesgos = new Set(filas.map(f => riesgoDe(porId[f.corrida_id] || {})));
  const mezcla = todas && riesgos.size > 1;
  // cuantas hay de verdad, contra cuantas llegaron en las paginas pedidas
  const hay = poblacionBanco();

  const th = (key, label, ayuda) => {
    const activa = s.key === key;
    const flecha = activa ? (s.dir === -1 ? icono("baja","ico-sm") : icono("sube","ico-sm")) : "";
    const ojo = mezcla && COLS_CON_RIESGO.has(key) ? " mixta" : "";
    return `<th class="num orden ${activa ? "activa" : ""}${ojo}" data-sort="${key}"
      title="${esc(ayuda)}${activa ? "" : ` · ${esc(t("col.click_sort"))}`}">${label}<i>${flecha}</i></th>`;
  };

  const todosTildados = filas.length && filas.every(f => b.sel.has(f.banco_id));
  /* ¿Alguna de las que se ven reservó un tramo fuera de muestra? Si ninguna,
     la columna es ciento cincuenta guiones y se saca. Se mira lo que está a
     la vista y no el banco entero: la columna acompaña a la tabla. */
  const hayOos = filas.some(f => f.oos);

  host.innerHTML = `<div class="card">
    <h2>${todas ? esc(t("bank.all_strategies")) : etiquetaCorrida(porId[b.corrida] || {})}
      <span class="hint">${esc(filtrando
        ? t("bank.filtradas", { n: filas.length, total: b.filas.length })
        : hay > b.filas.length
          ? t("bank.in_view_of", { n: b.filas.length, hay: fmtInt(hay) })
          : t("bank.in_view", { n: b.filas.length }))}</span>
      <input type="search" class="banco-buscar" id="banco-buscar"
        placeholder="${esc(t("bank.buscar"))}" value="${esc(FILTRO_BANCO)}"
        aria-label="${esc(t("bank.buscar"))}"></h2>
    ${/* SELECCIÓN RÁPIDA POR RESULTADO: todas las que están a la vista, o
          sólo las que en el tramo guardado se sostuvieron, se debilitaron o
          se cayeron. Es la pregunta que uno se hace antes de guardar. */
      filas.length ? `<div class="sel-rapida"><span>${esc(t("sel.rapida"))}</span>
        <button class="linkbtn" data-sel-oos="todas">${esc(t("etapa.todas_corto"))}</button>
        ${hayOos ? `<button class="linkbtn" data-sel-oos="good">${esc(t("col.oos_holds"))}</button>
        <button class="linkbtn" data-sel-oos="mid">${esc(t("col.oos_weakens"))}</button>
        <button class="linkbtn" data-sel-oos="bad">${esc(t("col.oos_falls"))}</button>` : ""}
        <button class="linkbtn" data-sel-oos="ninguna">${esc(t("ui.clear"))}</button></div>` : ""}

    ${mezcla ? `<div class="banner info mt" style="margin-bottom:14px">
      <span class="b-ic">${icono("info")}</span><div>${t("bank.mixed_risk", {
        anual: t("col.annual"), dd: t("col.maxdd"),
        score: t("m.score"), meses: t("col.months_plus") })}</div>
    </div>` : ""}

    <!-- Con nada tildado, una línea que dice cómo se usa. Los cuatro botones
         estaban siempre puestos: apagados de verdad, pero a simple vista los
         dos llenos de acento seguían leyéndose como disponibles y ocupaban
         una fila entera para no hacer nada. -->
    <div class="seleccion ${b.sel.size ? "activa" : ""}">
      <span class="sel-n">${esc(b.sel.size
        ? t("ui.selected", { n: b.sel.size }) : t("bank.sel_hint"))}</span>
      ${b.sel.size ? `
        <button class="btn small" id="sel-guardar">${icono("marcador","ico-sm")} ${esc(t("insp.save"))}</button>
        <button class="btn small" id="sel-exportar">${icono("bajar","ico-sm")} ${esc(t("bank.export_all"))}</button>
        <button class="btn ghost small" id="sel-borrar">${icono("basura","ico-sm")} ${esc(t("bank.remove"))}</button>
        <button class="linkbtn" id="sel-limpiar">${esc(t("ui.clear"))}</button>` : ""}
    </div>

    ${filas.length ? `<div class="databank-wrap"><table class="banco">
      <thead><tr>
        <th class="tick"><input type="checkbox" id="sel-todas" ${todosTildados ? "checked" : ""}
          aria-label="${esc(t("ui.select_all"))}"></th>
        <th>${esc(t("col.strategy"))}</th>
        ${todas ? `<th>${esc(t("bank.run"))}</th>` : `<th class="num orden ${s.key === "puesto" ? "activa" : ""}"
          data-sort="puesto" title="${esc(t("bank.rank_help"))}">#<i>${
            s.key === "puesto" ? icono("sube","ico-sm") : ""}</i></th>`}
        ${BANCO_COLS(hayOos).map(([k, l, a]) => th(k, l, a)).join("")}
      </tr></thead>
      <tbody>${filas.map(f => {
        const m = f.metrics || {}, c = porId[f.corrida_id] || {};
        return `<tr class="clickable ${b.sel.has(f.banco_id) ? "tildada" : ""}" data-fila="${esc(f.banco_id)}">
          <td class="tick"><input type="checkbox" data-tick="${esc(f.banco_id)}"
            ${b.sel.has(f.banco_id) ? "checked" : ""} aria-label="${esc(t("ui.select_one", { n: f.name }))}"></td>
          <td><span class="strat-name">${esc(f.name)}</span>${sesionTag(f)}
              <div class="strat-genes">${esc(etiquetaGenes(f))}</div></td>
          ${todas
            ? `<td class="origen"><b>${esc(nombreCorto(c.dataset_name))}</b>
                 <div class="run-sub">${esc(c.timeframe || "")} · ${esc(t("bank.risk"))} ${esc(riesgoDe(c))}</div></td>`
            : `<td class="rank-cell"><span class="rank">${String(f.puesto + 1).padStart(2, "0")}</span></td>`}
          <td class="num">${scoreCell(f.score)}</td>
          <td class="num ${(m.cagr_pct ?? 0) >= 0 ? "pos" : "neg"}"><b>${
            m.cagr_pct != null ? fmtPct(m.cagr_pct) : "—"}</b></td>
          <td class="num">${m.profit_factor != null ? fmtNum(m.profit_factor) : "—"}</td>
          <td class="num ${nivelDD(m.max_drawdown_pct, riesgoDeCtx((c.contexto || {}).risk))}">${
            m.max_drawdown_pct != null ? fmtNum(m.max_drawdown_pct, 1) + "%" : "—"}</td>
          <td class="num">${fmtInt(m.trades ?? 0)}</td>
          <td class="num">${fmtNum(m.months_positive_pct ?? 0, 0)}%</td>
          ${hayOos ? `<td class="num">${oosCell(f)}</td>` : ""}
        </tr>`;
      }).join("")}</tbody></table></div>
      ${hay > b.filas.length ? `<div class="banco-mas">
        <button class="btn ghost" id="banco-mas">${esc(t("bank.load_more"))}</button>
        <span class="muted">${esc(t("bank.in_view_of", {
          n: b.filas.length, hay: fmtInt(hay) }))}</span>
      </div>` : ""}`
      : filtrando
        ? `<div class="empty-state"><b>${esc(t("bank.sin_coincidencias",
             { q: FILTRO_BANCO }))}</b></div>`
        : bancoVacioHtml(porId[b.corrida])}
  </div>`;

  cablearBanco(host);

  /* Exportar todo lo tildado de una.

     Sin esto habia que abrir cada ficha, esperar a que recalcule el backtest
     —segundos por estrategia, para un archivo que no necesita ese calculo— y
     exportar. Diez estrategias eran diez vueltas de lo mismo. */
  /* Filtra mientras se escribe, sin ir al servidor. Se repinta solo la tabla
     y se devuelve el foco: sin eso, escribir la segunda letra es imposible
     porque el campo se acaba de redibujar. */
  const buscar = $("#banco-buscar", host);
  if (buscar) buscar.oninput = () => {
    const pos = buscar.selectionStart;
    FILTRO_BANCO = buscar.value;
    pintarBanco();
    const nuevo = $("#banco-buscar");
    if (nuevo) { nuevo.focus(); nuevo.setSelectionRange(pos, pos); }
  };

  const exportar = $("#sel-exportar", host);
  if (exportar) exportar.onclick = async () => {
    const elegidas = S.banco.filas.filter(f => S.banco.sel.has(f.banco_id));
    if (!elegidas.length) return;
    exportar.disabled = true;
    const original = exportar.innerHTML;

    let listas = 0;
    const fallaron = [];
    let carpeta = "", terminal = "";
    for (const [i, f] of elegidas.entries()) {
      exportar.innerHTML = `<span class="spinner"></span>${esc(
        t("bank.exporting", { i: i + 1, n: elegidas.length }))}`;
      // el contexto de SU corrida, no el de la pantalla: dos filas tildadas
      // pueden ser de instrumentos distintos
      const c = S.banco.corridas.find(x => x.id === f.corrida_id) || {};
      const cuerpo = {
        spec: f.spec, name: `BQ_${String(f.name).replace("-", "_")}`,
        dataset_id: c.dataset_id, timeframe: c.timeframe || "1h",
        metrics: f.metrics, server_utc_offset: S.cfg.brokerUtc,
      };
      if (S.mt5.elegido) cuerpo.terminal = S.mt5.elegido;
      try {
        const r = await api.post("/api/export/mql5/archivo", cuerpo);
        listas++; carpeta = r.carpeta; terminal = r.terminal || "";
      } catch (e) {
        if (pedirCuenta(e.status)) break;
        fallaron.push(f.name);
      }
    }

    exportar.innerHTML = original;
    exportar.disabled = false;
    if (listas) {
      toast(terminal
        ? t("bank.exported_mt5", { n: listas, terminal })
        : t("bank.exported", { n: listas, carpeta }), "ok");
    }
    // los que fallaron se nombran: "3 de 5" sin decir cuales dos obliga a
    // revisar las cinco
    if (fallaron.length) {
      toast(t("bank.export_failed", { nombres: fallaron.join(", ") }), "err");
    }
  };

  const mas = $("#banco-mas", host);
  if (mas) mas.onclick = async () => {
    mas.disabled = true;
    mas.textContent = t("ui.loading");
    try {
      await cargarBanco({ corridas: false, mas: true });
      pintarBanco();
    } catch (e) {
      toast(e.message, "err");
      mas.disabled = false;
      mas.textContent = t("bank.load_more");
    }
  };
}

/* Una corrida sin filas puede serlo por dos motivos opuestos, y confundirlos
   manda a hacer cosas distintas: si la búsqueda no encontró nada hay que
   aflojar la vara, y si las borraste no hay nada que arreglar. */
function bancoVacioHtml(c) {
  if (!c) {
    return `<div class="empty-state"><b>${esc(t("bank.nothing_left"))}</b>
      <p class="mt">${esc(t("bank.saved_untouched"))}</p></div>`;
  }
  if (!c.encontradas) {
    return `<div class="empty-state">
      <div class="big">${icono("diana","ico-xl")}</div>
      <b>${esc(t("bank.run_found_none"))}</b>
      <p class="mt">${t("bank.run_found_none_help", {
        n: fmtInt(c.tested), mercado: esc(nombreCorto(c.dataset_name)),
        vara: esc(varaDe(c)) })}</p>
      <p class="mt muted">${esc(t("bank.run_found_none_note"))}</p>
    </div>`;
  }
  return `<div class="empty-state"><b>${esc(t("bank.you_removed", { n: c.encontradas }))}</b>
    <p class="mt">${esc(t("bank.saved_untouched"))}</p></div>`;
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
  $$("[data-sel-oos]", host).forEach(bt => bt.onclick = () => {
    const que = bt.dataset.selOos;
    const visibles = filasVisibles();
    const clase = (f) => {
      if (!f.oos || !f.oos.trades) return "none";
      const q = f.oos_ratio; return q >= 0.8 ? "good" : q >= 0.5 ? "mid" : "bad";
    };
    b.sel.clear();
    if (que === "todas") visibles.forEach(f => b.sel.add(f.banco_id));
    else if (que !== "ninguna") visibles.filter(f => clase(f) === que).forEach(f => b.sel.add(f.banco_id));
    refrescar();
  });

  $$("[data-fila]", host).forEach(tr => tr.onclick = (ev) => {
    if (ev.target.closest(".tick")) return;
    abrirDelBanco(b.filas.find(f => f.banco_id === tr.dataset.fila));
  });

  /* Los botones sólo existen con algo tildado, así que los enganches
     tienen que tolerar que no estén. */
  const conBoton = (id, fn) => { const el = $(id, host); if (el) fn(el); };

  conBoton("#sel-limpiar", el => el.onclick = () => { b.sel.clear(); refrescar(); });

  conBoton("#sel-guardar", el => el.onclick = async () => {
    const ids = [...b.sel];
    if (!ids.length) return;
    const btn = $("#sel-guardar", host);
    btn.disabled = true;
    try {
      const r = await api.post("/api/banco/guardar", { ids });
      await refreshSavedCount();
      encolarPruebas((r.guardadas || []).map(g => g.id));
      const n = r.guardadas.length;
      // guardar es COPIAR: la fila sigue en el banco. Si además la sacara,
      // revisar una corrida la iría vaciando a medida que uno la mira.
      b.sel.clear();
      refrescar();
      await refreshSavedCount();
      toast(t("bank.copied", { n }), "ok");
    } catch (e) {
       toast(e.message, "err"); }
    btn.disabled = false;
  });

  conBoton("#sel-borrar", el => el.onclick = async () => {
    const ids = [...b.sel];
    if (!ids.length) return;
    if (!confirm(t("bank.confirm_remove", { n: ids.length }) + "\n\n"
                 + t("bank.saved_untouched"))) return;
    try {
      await api.post("/api/banco/borrar", { ids });
      b.sel.clear();
      await cargarBanco();
      pintarCabecera();
      pintarCorridas();
      pintarBanco();
      toast(t("bank.removed", { n: ids.length }), "ok");
    } catch (e) {
       toast(e.message, "err"); }
  });
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
  if (ajustes.swap_anual != null) S.cfg.swap = ajustes.swap_anual;
  if (ajustes.initial_capital != null) S.cfg.capital = ajustes.initial_capital;

  S.sel.timeframe = c.timeframe || "1h";
  const hay = S.datasets.some(d => d.id === c.dataset_id);
  if (hay) S.sel.dataset_id = c.dataset_id;
  saveCfg();
  navigate("mining", "buscar").then(() => toast(hay
    ? t("bank.cfg_loaded")
    : t("bank.cfg_loaded_missing", { mercado: nombreCorto(c.dataset_name) }),
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
    toast(t("err.dataset_gone"), "err");
    return;
  }
  openInspector(f, {
    dataset_id: c.dataset_id, timeframe: c.timeframe || "1h",
    date_from: rango ? rango.from : undefined,
    date_to: rango ? rango.to : undefined,
    sinRango: !rango,
    // el corte, para poder mirar cada mitad por separado y las dos juntas
    split: ctx.split || null,
    settings: ctx.settings || {},
    /* Con que guardarla si sale de aca. Tiene que salir de la corrida y no de
       la pantalla: esta fila puede ser de otro instrumento, de otra
       temporalidad y de otro riesgo que lo que este configurado ahora. */
    guardar: {
      dataset_id: c.dataset_id, dataset_name: c.dataset_name || "",
      timeframe: c.timeframe || "1h", direction: ctx.direction || "both",
      spread: (ctx.settings || {}).spread,
      slippage: (ctx.settings || {}).slippage,
      commission: (ctx.settings || {}).commission_pct,
      swap: (ctx.settings || {}).swap_anual,
      capital: (ctx.settings || {}).initial_capital,
      sizing: (ctx.risk || {}).size_mode === "fixed_units" ? "lots" : "risk",
      riskPct: (ctx.risk || {}).size_value,
      lots: (ctx.risk || {}).size_value,
      rr: (ctx.risk || {}).reward_ratio,
      measured_range: rango || null, split: ctx.split || null,
    },
    // decir de qué corrida salió, no "guardada": todavía no lo está, y
    // confundir las dos cosas hace creer que ya se rescató algo que no
    etiqueta: t("bank.from_bank", { corrida: etiquetaCorrida(c), riesgo: riesgoDe(c) }),
  });
}

/* =========================================================== página MINING */
/* ═══════════════════════════════════════ MINADO: BUSCAR Y RESULTADOS ══════
   El databank era una sección aparte del menú. Es información valiosa —lo que
   encontró cada corrida, y de dónde se guardan las estrategias— pero no es un
   destino: es la otra mitad de minar. Uno busca y después mira lo que salió.

   Puestas como dos vistas de la misma sección, el menú baja una entrada y el
   recorrido se lee solo: Buscar → Resultados → Guardar.

   Se mantienen como dos funciones separadas y no como una pantalla enorme
   porque no comparten nada: una configura una búsqueda, la otra lee una tabla
   de corridas archivadas. */
PAGES.mining = async (main) => {
  const vista = S.vista === "resultados" ? "resultados" : "buscar";
  const n = S.banco?.total || 0;
  main.innerHTML = `<div class="vistas" role="tablist">
      <button role="tab" data-vista="buscar" aria-selected="${vista === "buscar"}"
        class="${vista === "buscar" ? "on" : ""}">${esc(t("mine.tab_search"))}</button>
      <button role="tab" data-vista="resultados" aria-selected="${vista === "resultados"}"
        class="${vista === "resultados" ? "on" : ""}">${esc(t("mine.tab_results"))}
        ${n ? `<em>${fmtInt(n)}</em>` : ""}</button>
    </div>
    <div id="vista-host"></div>`;

  $$("[data-vista]", main).forEach(b => b.onclick = () => {
    S.vista = b.dataset.vista;
    navigate("mining");
  });

  const host = $("#vista-host", main);
  await (vista === "resultados" ? vistaResultados(host) : vistaBuscar(host));
  acomodarVistas(main, host);
};

/* Las pestañas se dibujan arriba y se MUEVEN debajo del título.

   Se emiten acá porque son de la sección y no de cada vista —una sola lista,
   un solo cableado— pero el título lo escribe la vista, así que al dibujarse
   quedaban por encima de él: lo primero que se leía era "Buscar | Resultados"
   y recién después "Minado". Las pestañas son las dos mitades de una sección
   y no pueden presentarse antes que la sección.

   Se mueven en vez de emitirse en su lugar por una razón concreta: en
   Resultados el encabezado se reescribe solo cada vez que cambia la cuenta
   —`pintarCabecera`— y unas pestañas metidas adentro se las llevaría ese
   repintado. Por eso el ancla es el hijo directo del host que CONTIENE el
   título, no el título: ese nodo sobrevive. */
function acomodarVistas(main, host) {
  const tabs = $(".vistas", main);
  const head = $(".page-head", host);
  if (!tabs || !head) return;
  let ancla = head;
  while (ancla.parentElement && ancla.parentElement !== host) ancla = ancla.parentElement;
  if (ancla.parentElement === host) ancla.after(tabs);
}

const vistaBuscar = async (main) => {
  await refreshDatasets();
  /* LA PRIMERA BÚSQUEDA YA ESTÁ LISTA. Sin ninguna corrida hecha y sin
     receta puesta, se deja "dormir tranquilo" puesta: es la más fácil de
     que devuelva algo, y el usuario sólo tiene que apretar. */
  if (!(S.banco && S.banco.total) && !S.recetaPuesta && (S.datasets || []).length) {
    const r = RECETAS().find(x => x.id === "tranquilo");
    if (r) { const c = S.cfg; c.critOn = {}; Object.entries(r.cfg).forEach(([k, v]) => {
      if (k === "critOn") c.critOn = { ...v };
      else if (!["timeframe", "anios", "minCagrFactor"].includes(k)) c[k] = v; });
      S.recetaPuesta = r.id; saveCfg(); S.primeraBusqueda = true; }
  }
  if (!S.datasets.length) {
    main.innerHTML = pageHead(t("nav.mining"), esc(t("mine.sub_empty"))) +
      `<div class="card"><div class="empty-state"><div class="big">${icono("pico","ico-xl")}</div>
        <b>${esc(t("mine.no_data"))}</b>
        <p class="mt">${t("mine.no_data_help")}</p>
        <button class="btn mt" id="go-data">${esc(t("mine.go_data"))}</button>
      </div></div>`;
    $("#go-data", main).onclick = () => navigate("data");
    return;
  }
  /* LA SECCION ELEGIDA PUEDE ESTAR VACIA AUNQUE LA OTRA NO. Sin esto, en
     "Cripto" sin perpetuos el selector caía en el primer histórico que
     hubiera —SP500— y cambiar de sección parecía no hacer nada: un parpadeo
     y la misma pantalla. Pasó el 2 de septiembre con un espacio de trabajo
     que venía de la versión con sólo CFDs. */
  if (!datasetsDelMundo().length) {
    const cripto = S.mundo === "exchange";
    main.innerHTML = pageHead(t("nav.mining"), esc(t("mine.sub_empty"))) +
      `<div class="card"><div class="empty-state"><div class="big">${icono("pico","ico-xl")}</div>
        <b>${esc(t(cripto ? "mine.no_data_cripto" : "mine.no_data_cfd"))}</b>
        <p class="mt">${t(cripto ? "mine.no_data_cripto_help" : "mine.no_data_cfd_help")}</p>
        <button class="btn mt" id="go-data">${esc(t("mine.go_data"))}</button>
      </div></div>`;
    $("#go-data", main).onclick = () => navigate("data");
    return;
  }

  // se corrige antes de dibujar: los inputs nacen con los valores del mercado
  // elegido en vez de arrastrar los del instrumento anterior
  const fixed = fixInheritedScale();

  const c = S.cfg;
  /* EL SELECTOR LISTA DATASETS, NO CATALOGO, y por ahí se colaba el otro
     mundo: los perpetuos seguían apareciendo acá aunque no estuvieran en la
     vitrina de instrumentos. Se clasifica cada histórico por su nombre; los
     que no se pueden clasificar —un CSV propio— se muestran siempre, porque
     adivinarles un mundo sería peor que dejarlos a la vista. */
  /* SI EL ELEGIDO NO ES DE ESTE MUNDO, SE ELIGE UNO QUE SÍ. Cambiar de
     sección olvida el instrumento, pero quien lo vuelve a elegir por defecto
     no miraba el mundo: en "cripto" el desplegable mostraba ADAUSDT y la
     búsqueda iba a SP500. Pasó, y la búsqueda arrancaba en el instrumento
     equivocado sin que nada lo dijera. */
  const delMundo = datasetsDelMundo();
  if (delMundo.length && !delMundo.some(d => d.id === S.sel.dataset_id)) {
    S.sel.dataset_id = delMundo[0].id;
    adoptInstrumentDefaults();
    saveCfg();
  }
  const dsOpts = delMundo.map(d =>
    `<option value="${d.id}" ${d.id === S.sel.dataset_id ? "selected" : ""}>
       ${esc(d.name)} · ${esc(t("ui.n_bars", {
         n: d.rows.toLocaleString(localeNum()) }))}</option>`).join("");
  if (!S.sel.timeframe) S.sel.timeframe = "1h";

  /* SOLO LAS TEMPORALIDADES QUE ESTE HISTORICO PUEDE DAR.

     De velas de una hora no salen velas de quince minutos: agrupar hacia
     arriba se puede, hacia abajo no. La lista era fija y ofrecía las seis
     siempre, así que con un histórico horario uno elegía 15m y recién al
     iniciar la búsqueda le decían que no — correctamente, pero después de
     configurar todo lo demás.

     Desde que hay dos fuentes esto dejó de ser teórico: Dukascopy trae velas
     de un minuto y MetaTrader de una hora, y el mismo instrumento puede estar
     en cualquiera de las dos. */
  const dsElegido = S.datasets.find(d => d.id === S.sel.dataset_id);
  const MINUTOS_TF = { "1m": 1, "5m": 5, "15m": 15, "30m": 30,
                       "1h": 60, "4h": 240, "1d": 1440 };
  const minsDs = MINUTOS_TF[dsElegido?.timeframe] || 1;
  const tfPosibles = (S.meta?.timeframes || ["1h"]).filter(
    x => x === "native" || (MINUTOS_TF[x] || 0) >= minsDs);
  // si la que estaba elegida ya no se puede, se pasa a la más chica que sí:
  // dejarla elegida mostraría un valor que el servidor va a rechazar
  if (!tfPosibles.includes(S.sel.timeframe)) {
    S.sel.timeframe = tfPosibles.find(x => x !== "native") || "native";
  }
  const tfOpts = tfPosibles.map(x =>
    `<option ${x === S.sel.timeframe ? "selected" : ""}>${x}</option>`).join("");
  // arranque curado: los bloques mas usados y entendibles, no todos
  const DEFAULT_ON = new Set(["ema_cross", "price_ema", "rsi_reversal", "macd_cross",
                              "bollinger_revert", "donchian_break",
                              "ema_trend_filter", "adx_filter"]);
  const picked = S.cfg.blocks && S.cfg.blocks.length ? new Set(S.cfg.blocks) : DEFAULT_ON;
  /* La categoría viene del motor en castellano ("vela", "volatility"…) y
     se pintaba cruda: en inglés se leía "VELA" cuatro veces. Si aparece una
     categoría nueva se muestra como viene, que es mejor que nada. */
  const tCat = (c) => {
    const k = "cat_bloque." + String(c || "");
    const txt = t(k);
    return txt === k ? String(c || "") : txt;
  };
  const blockList = (kind) => `<div class="blocklist" data-kind="${kind}">` +
    (S.meta?.templates || []).filter(t => t.kind === kind).map(t => `
      <label class="blockitem ${picked.has(t.id) ? "on" : ""}">
        <input type="checkbox" data-tid="${t.id}" ${picked.has(t.id) ? "checked" : ""}>
        <span>${esc(t.label)}</span>
        <span class="cat-tag">${esc(tCat(t.category))}</span>
      </label>`).join("") + `</div>`;
  const opt = (val, cur, label) => `<option value="${val}" ${val === cur ? "selected" : ""}>${label || val}</option>`;

  const curDs = S.datasets.find(d => d.id === S.sel.dataset_id);

  /* QUÉ RECETA ESTÁ PUESTA, DESPUÉS DE RECARGAR. Los valores de la receta se
     guardan y vuelven —siguen gobernando la búsqueda— pero la marca de cuál
     era sólo se restituía al CAMBIAR de mercado en el desplegable. Recargar
     dejaba el plan con los números de "dormir tranquilo" y ninguna tarjeta
     encendida: la pantalla no decía por qué buscaba lo que buscaba
     (3 de septiembre de 2026). */
  if (S.recetaPuesta == null && S.sel.dataset_id) {
    try {
      const g = JSON.parse(localStorage.getItem("qf.cfg_mercado") || "{}")[S.sel.dataset_id];
      if (g && g.receta) S.recetaPuesta = g.receta;
    } catch (e) { /* modo privado */ }
  }

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
  ${pageHead(t("nav.mining"), esc(t("mine.sub")), ctxPill())}

  <section class="recetas">
    <h2>${esc(t("rec.titulo"))}
      <span class="hint">${esc(t("rec.sub"))}</span></h2>
    <div class="recetas-lista">
      ${RECETAS().filter(r => !r.mundo || r.mundo === S.mundo).map(r => `
        <button class="receta ${S.recetaPuesta === r.id ? "on" : ""}" data-receta="${r.id}">
          <span class="r-ico">${icono(r.ico)}</span>
          <b>${esc(t(`rec.${r.id}`))}</b>
          <span class="r-que">${esc(t(`rec.${r.id}_que`))}</span>
          <em class="r-cuesta">${esc(t(`rec.${r.id}_cuesta`))}</em>
        </button>`).join("")}
    </div>
  </section>

  <div class="workbench">
    <aside class="setup">
      <div class="setup-scroll">
        <details class="sect">
          <summary><span class="sect-num">1</span>
            <span class="sect-t"><b>${esc(t("mine.market"))}</b><em id="sum-market">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="fld-stack">
              <label class="fld"><span>${esc(t("mine.instrument"))}</span>
                <select id="sel-dataset">${dsOpts}</select></label>
              <label class="fld"><span>${esc(t("mine.timeframe"))}
                  <span class="hint">${esc(t("mine.timeframe_hint"))}</span></span>
                <select id="sel-timeframe">${tfOpts}</select></label>
              <div class="fld"><span>${esc(t("mine.direction"))}</span>
                <div class="seg full" id="m-dir">
                  ${["long", "short", "both"].map(v =>
                    `<button data-dir="${v}" class="${c.direction === v ? "on" : ""}"
                      >${esc(t("dir." + v))}</button>`).join("")}
                </div>
              </div>
            </div>

            <div class="stage-sub">${esc(t("mine.period"))}</div>
            <div class="fld-pair">
              <label class="fld"><span>${esc(t("mine.from"))}</span>
                <input type="date" class="datefld" id="m-date-from"
                  min="${esc(bounds.lo)}" max="${esc(bounds.hi)}" value="${esc(range.from)}"></label>
              <label class="fld"><span>${esc(t("mine.to"))}</span>
                <input type="date" class="datefld" id="m-date-to"
                  min="${esc(bounds.lo)}" max="${esc(bounds.hi)}" value="${esc(range.to)}"></label>
            </div>
            ${acotado && aniosTotales > VENTANA_ANIOS ? `
              <div class="ventana">
                <div>${t("mine.window", { n: VENTANA_ANIOS, total: aniosTotales.toFixed(0) })}</div>
                <button class="btn ghost small" id="m-todo-historial">${
                  esc(t("mine.use_all", { total: aniosTotales.toFixed(0) }))}</button>
              </div>` : ""}
            <p class="stage-note" id="m-dsnote"></p>

            ${SESIONES ? `
            <div class="stage-sub">${esc(t("session.title"))}
              <span class="hint">${esc(t("session.sub"))}</span></div>
            <p class="help-note">${esc(t("session.help"))}</p>
            <div class="franjas" id="m-sessions">
              ${(S.meta?.sessions || []).map(s => `
                <button data-ses="${esc(s.id)}"
                  class="${sesionesElegidas().includes(s.id) ? "on" : ""}">
                  <b>${esc(t("s." + s.id))}</b>
                  <em>${esc(s.horario
                    || (s.restringe ? t("session.all_day") : t("session.no_limit")))}</em>
                </button>`).join("")}
            </div>
            <p class="help-note" id="m-sesnote"></p>` : ""}

            <!-- RESERVAR UN TRAMO va acá y no en un paso al final.

                 Estaba de sexto, casi al final: uno terminaba de armar el
                 robot y recién ahí le aparecía la opción de guardarse un
                 pedazo de historia sin mirar. No es un paso final — es una
                 decisión sobre LA DATA: partir en dos el período que se acaba
                 de elegir, tres líneas más arriba. -->
            <!-- Sin bajada al lado del rótulo: en 300px de ancho entran los
                 dos en versalitas y se parten en dos renglones cada uno, y
                 además diría lo mismo que el párrafo de acá abajo. -->
            <div class="stage-sub">${esc(t("mine.oos"))}</div>
            <div class="seg full" id="m-oos-sw">
              <button data-oos="0" class="${+c.oosPct ? "" : "on"}"
                >${esc(t("oos.off"))}</button>
              <button data-oos="30" class="${+c.oosPct ? "on" : ""}"
                >${esc(t("oos.on"))}</button>
            </div>
            <p class="help-note mt">${t("oos.what", { pct: 30 })}</p>
            ${/* EL REPARTO, DIBUJADO. "Reservar el 30 %" es un número; una
                  barra partida en dos se entiende sin leer. */ ""}
            <div class="oos-barra" id="m-oos-barra" ${+c.oosPct ? "" : "hidden"}>
              <i class="oos-busca" style="flex:${100 - (+c.oosPct || 30)}"><span>${esc(t("oos.b_busca", { pct: 100 - (+c.oosPct || 30) }))}</span></i>
              <i class="oos-guarda" style="flex:${+c.oosPct || 30}"><span>${esc(t("oos.b_guarda", { pct: +c.oosPct || 30 }))}</span></i>
            </div>

            <div id="m-oos-detalle" ${+c.oosPct ? "" : "hidden"}>
              <div class="stage-sub">${esc(t("oos.how_much"))}</div>
              <!-- Solo el porcentaje en el boton. Con la frase entera
                   ("Minar 70% · validar 30% (recomendado)") las tres opciones
                   no entran a lo ancho de la columna y se rompen en cuatro
                   renglones cada una: ilegible. Lo que significa el numero lo
                   dice la linea de abajo, que ademas cambia con la eleccion. -->
              <div class="seg full" id="m-oos-pct">
                ${[20, 30, 40].map(v => `<button data-pct="${v}"
                  class="${+c.oosPct === v ? "on" : ""}">${v}%</button>`).join("")}
              </div>
              <p class="stage-note" id="m-oos-nota"></p>
              <p class="help-note mt">${t("mine.oos_help")}</p>
              <p class="stage-note">${esc(t("oos.informa"))}</p>
            </div>

          </div>
        </details>

        ${/* MODO SIMPLE POR DEFECTO: mercado, receta y buscar. Los otros
              cinco pasos —bloques, riesgo, costos, filtros, avanzado— quedan
              plegados bajo "Ajustar la búsqueda": la receta ya los dejó
              puestos, y quien quiera tocarlos los abre. Se recuerda si se
              abrió, para no volver a plegárselo a quien ya los usa. */ ""}
        <details class="sect avanzado" id="m-avanzado" ${localStorage.getItem("qf.avanzado") === "1" ? "open" : ""}>
          <summary><span class="sect-num">+</span>
            <span class="sect-t"><b>${esc(t("mine.avanzado"))}</b><em>${esc(t("mine.avanzado_sub"))}</em></span>
            <span class="chev">›</span></summary>
        <details class="sect">
          <summary><span class="sect-num">2</span>
            <span class="sect-t"><b>${esc(t("mine.blocks"))}</b><em id="sum-blocks">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="stage-sub">${esc(t("mine.triggers"))}</div>
            <div class="blocklist-actions" data-for="m-drivers">
              <button data-all="1">${esc(t("ui.all"))}</button>
              <button data-all="0">${esc(t("ui.none_btn"))}</button></div>
            <div id="m-drivers">${blockList("driver")}</div>
            <div class="stage-sub">${esc(t("mine.filters"))}</div>
            <div class="blocklist-actions" data-for="m-filters">
              <button data-all="1">${esc(t("ui.all"))}</button>
              <button data-all="0">${esc(t("ui.none_btn"))}</button></div>
            <div id="m-filters">${blockList("filter")}</div>
            <!-- Este número pasó por dos nombres malos: "Máx. filtros por
                 estrategia" describía el código, y "cuántos de estos puede
                 combinar" no decía de qué estaba hablando ni por qué importa.

                 Lo que gradúa es la COMPLEJIDAD de las reglas, que es la
                 palanca más grande que hay sobre el sobreajuste: cuantas más
                 condiciones puede apilar una estrategia, más fácil le resulta
                 describir el pasado exacto y menos le queda para el futuro.
                 Como eso es una decisión y no un número, va con nombres. -->
            <div class="fld mt"><span>${esc(t("mine.complexity"))}
                <span class="hint">${esc(t("mine.complexity_hint"))}</span></span></div>
            <div class="complejidad" id="m-complejidad">
              ${COMPLEJIDAD().map(c2 => `<button data-filtros="${c2.n}"
                class="${+c.maxFilters === c2.n ? "on" : ""}" title="${esc(c2.ayuda)}">
                <b>${esc(c2.nombre)}</b><em>${esc(c2.pie)}</em></button>`).join("")}
            </div>
            <p class="help-note" id="m-filtnote"></p>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num">3</span>
            <span class="sect-t"><b>${esc(t("mine.risk"))}</b><em id="sum-risk">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="seg full" id="rk-sizing">
              <button data-v="risk" class="${c.sizing !== "lots" ? "on" : ""}">${esc(t("mine.size_risk"))}</button>
              <button data-v="lots" class="${c.sizing === "lots" ? "on" : ""}">${esc(t("mine.size_lots"))}</button>
            </div>

            <div class="knob mt" id="rk-risk-box" ${c.sizing === "lots" ? "hidden" : ""}>
              <div class="knob-head"><b>${esc(t("mine.risk_per_trade"))}</b>
                <span class="knob-val"><input type="number" id="rk-risk" step="0.1" min="0.1" max="10"
                  value="${c.riskPct}"><em>%</em></span></div>
              <div class="goal-presets" id="rk-risk-presets">
                ${RISK_PRESETS.map(p => `<button data-v="${p}" class="${+c.riskPct === p ? "on" : ""}">${p}%</button>`).join("")}
              </div>
              <p class="help-note" id="m-riskhelp"></p>
            </div>

            <div class="knob mt" id="rk-lots-box" ${c.sizing === "lots" ? "" : "hidden"}>
              <div class="knob-head"><b>${esc(t("mine.volume"))}</b>
                <span class="knob-val"><input type="number" id="rk-lots" step="0.01" min="0.01" max="100"
                  value="${c.lots}"><em>${esc(t("mine.lots"))}</em></span></div>
              <div class="goal-presets" id="rk-lots-presets">
                ${LOT_PRESETS.map(p => `<button data-v="${p}" class="${+c.lots === p ? "on" : ""}">${p}</button>`).join("")}
              </div>
              <p class="help-note" id="m-lotshelp"></p>
            </div>

            <div class="knob mt">
              <div class="knob-head"><b>${esc(t("mine.rr"))}</b>
                <span class="knob-val"><em>1 :</em><input type="number" id="rk-rr" step="0.25" min="0.25" max="10"
                  value="${c.rr}"></span></div>
              <div class="goal-presets" id="rk-rr-presets">
                ${RR_PRESETS.map(p => `<button data-v="${p}" class="${+c.rr === p ? "on" : ""}">1:${p}</button>`).join("")}
              </div>
              <p class="help-note" id="m-rrhelp"></p>

              <!-- BUSCAR LA RELACIÓN, en vez de fijarla.

                   Hasta ahora esto sólo se podía pedir eligiendo una categoría,
                   y es la perilla que más cambia lo que la búsqueda puede
                   encontrar: con 1:2 fija, ninguna de treinta estrategias llega
                   a 60% de aciertos; dejándola buscar, el abanico de win rate
                   casi se duplica. Esconder eso adentro de una receta es
                   esconder la mitad de la aplicación. -->
              <div class="seg full mt" id="rk-rr-modo">
                <button data-rrmodo="fija" class="${c.rrBuscado?.length ? "" : "on"}"
                  >${esc(t("rr.fija"))}</button>
                <button data-rrmodo="buscar" class="${c.rrBuscado?.length ? "on" : ""}"
                  >${esc(t("rr.buscar"))}</button>
              </div>
              <p class="help-note mt">${c.rrBuscado?.length
                ? t("rr.buscar_ayuda", { n: c.rrBuscado.length,
                    desde: Math.min(...c.rrBuscado), hasta: Math.max(...c.rrBuscado) })
                : t("rr.fija_ayuda")}</p>
            </div>

            <label class="fld mt"><span>${esc(t("mine.capital"))}</span>
              <input type="number" step="1000" min="100" data-cfg="capital" value="${c.capital}"></label>

            <!-- La comprobacion que el capital nunca hacia: con esta plata y
                 este riesgo, la posicion que sale, ¿el broker la acepta? -->
            <div class="realidad" id="m-realidad"></div>

            <p class="stage-note mt">${t("mine.stop_note")}</p>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num">4</span>
            <span class="sect-t"><b>${esc(t(S.mundo === "exchange" ? "mine.costs_cripto" : "mine.costs"))}</b><em id="sum-cost">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="fld-pair">
              <label class="fld"><span>${esc(t("mine.spread"))}</span><input type="number" step="0.00001" data-cfg="spread" value="${c.spread}"></label>
              <label class="fld"><span>${esc(t("mine.slippage"))}</span><input type="number" step="0.00001" data-cfg="slippage" value="${c.slippage}"></label>
            </div>
            <div class="fld-pair mt">
              <label class="fld"><span>${esc(t("mine.commission"))}</span><input type="number" step="0.001" data-cfg="commission" value="${c.commission}"></label>
              <label class="fld"><span>${esc(t("mine.min_lot"))}</span><input type="number" step="0.01" min="0.001" data-cfg="minLot" value="${c.minLot}"></label>
            </div>
            <div class="fld-pair mt">
              <label class="fld"><span>${esc(t("mine.swap"))}</span><input type="number" step="0.1" min="0" data-cfg="swap" value="${c.swap}"></label>
            </div>
            <p class="help-note">${esc(t("mine.swap_help"))}</p>
            <div class="sugerido" id="m-sugerido" hidden></div>
            <p class="stage-note" id="m-costnote"></p>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num">5</span>
            <span class="sect-t"><b>${esc(t("mine.accept"))}</b><em id="sum-crit">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <p class="help-note">${esc(t("mine.accept_help"))}</p>

            <!-- DONDE SE TIENEN QUE CUMPLIR ESTAS VARAS.
                 Sin tramo reservado la segunda opción no existe: no hay
                 "afuera" contra el cual medir, así que se muestra apagada y
                 dice dónde prenderla en vez de dejar un botón muerto. -->
            <div class="seg full mb" id="m-oos-exig">
              <button data-exig="0" class="${c.exigirOos ? "" : "on"}"
                >${esc(t("acc.solo_dentro"))}</button>
              <!-- El estado deshabilitado lo pone el pintor y NO esta
                   plantilla. Estaban los dos: la plantilla escribía el
                   atributo al dibujar y el pintor lo recalculaba una línea
                   después, con lo cual el botón quedaba en un estado que no
                   correspondía a ninguno y no había forma de saber cuál
                   mandaba. Una sola fuente.
                   (Y ojo con las comillas invertidas en un comentario de
                   adentro de una plantilla: cortan la plantilla y rompen el
                   archivo entero. Pasó acá.) -->
              <button data-exig="1" class="${c.exigirOos ? "on" : ""}"
                >${esc(t("acc.tambien_fuera"))}</button>
            </div>
            <p class="help-note" id="m-exig-nota"></p>

            <p class="help-note" id="m-critaviso"></p>
            <div class="critlist mt">
              <div class="critrow on always">
                <label class="crit-check"><input type="checkbox" checked disabled>
                  <span class="crit-label">${esc(t("crit.minTrades"))}</span></label>
                <input class="crit-val" type="number" data-cfg="minTrades" value="${c.minTrades}" min="1" step="5">
                <span class="crit-unit"></span>
              </div>
              ${CRITERIA().map(critRow).join("")}
            </div>
            <p class="help-note" id="m-crithelp"></p>
          </div>
        </details>

        <details class="sect">
          <summary><span class="sect-num">6</span>
            <span class="sect-t"><b>${esc(t("ui.advanced"))}</b><em id="sum-adv">—</em></span>
            <span class="chev">›</span></summary>
          <div class="sect-body">
            <div class="fld-stack">
              <label class="fld"><span>${esc(t("mine.method"))}</span><select data-cfg="method">
                ${opt("random", c.method, esc(t("mine.method_random")))}
                ${opt("evolution", c.method, esc(t("mine.method_evolution")))}</select></label>
              <label class="fld"><span>${esc(t("mine.sort_by"))}</span><select data-cfg="fitness">
                ${opt("composite", c.fitness, `${esc(t("mine.sort_score"))} — ${esc(t("ui.recommended"))}`)}
                ${opt("net_profit", c.fitness, esc(t("m.net")))}
                ${opt("profit_factor", c.fitness, esc(t("m.pf")))}
                ${opt("sharpe", c.fitness, esc(t("m.sharpe")))}
                ${opt("activity", c.fitness, esc(t("mine.sort_activity")))}</select></label>
              <label class="fld"><span>${esc(t("mine.cap"))}
                  <span class="hint">${esc(t("mine.cap_hint"))}</span></span>
                <input type="number" data-cfg="maxCandidates" value="${c.maxCandidates}" min="100" step="1000"></label>
            </div>
          </div>
        </details>
        </details>
      </div>

      <div class="setup-run" id="m-runbar">
        <div class="goal-field">
          <span>${esc(t("mine.want"))}</span>
          <div class="goal-input">
            <input type="number" id="m-goal" value="${c.goal}" min="1" max="1000" step="1">
            <em>${t("mine.want_sub")}</em>
          </div>
          <div class="goal-presets" id="m-goal-presets">
            ${GOAL_PRESETS.map(g => `<button data-goal="${g}" class="${+c.goal === g ? "on" : ""}">${g}</button>`).join("")}
          </div>
        </div>
        <button class="btn big" id="m-run">${icono("pico")} ${esc(t("mine.start"))}</button>
        <div class="run-acciones" id="m-acciones" style="display:none">
          <button class="btn ghost big" id="m-pause">${icono("pausa")} ${esc(t("mine.pause"))}</button>
          <button class="btn ghost big" id="m-stop">${icono("detener")} ${esc(t("mine.stop"))}</button>
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
  /* El paso de validacion fuera de muestra.

     Dos controles y no uno: prender/apagar es la decision, y cuanto reservar
     es un ajuste que solo tiene sentido una vez prendido. Ponerlos juntos en
     un desplegable de cuatro opciones —que es como estaba— mezclaba las dos
     cosas y dejaba "Desactivada" como si fuera un porcentaje mas. */
  const pintarOos = () => {
    const on = +S.cfg.oosPct > 0;
    $$("#m-oos-sw button", main).forEach(b =>
      b.classList.toggle("on", (b.dataset.oos !== "0") === on));
    $$("#m-oos-pct button", main).forEach(b =>
      b.classList.toggle("on", +b.dataset.pct === +S.cfg.oosPct));
    const det = $("#m-oos-detalle", main);
    if (det) det.hidden = !on;
    const nota = $("#m-oos-nota", main);
    if (nota) {
      const v = +S.cfg.oosPct;
      nota.textContent = t("mine.oos_split", { mina: 100 - v, valida: v })
        + (v === 30 ? ` · ${t("ui.recommended")}` : "");
    }
    // la barra del reparto sigue al porcentaje elegido
    const barra = $("#m-oos-barra", main);
    if (barra) {
      const v = +S.cfg.oosPct || 30;
      barra.hidden = !on;
      const busca = $(".oos-busca", barra), guarda = $(".oos-guarda", barra);
      busca.style.flex = String(100 - v); guarda.style.flex = String(v);
      $("span", busca).textContent = t("oos.b_busca", { pct: 100 - v });
      $("span", guarda).textContent = t("oos.b_guarda", { pct: v });
    }
    updateNotes();
  };
  $$("#m-oos-sw button", main).forEach(b => b.onclick = () => {
    // apagar no olvida cuanto habia elegido: volver a prender restituye ese
    // valor en vez de mandarlo siempre al 30
    if (b.dataset.oos === "0") { S.cfg.oosUltimo = +S.cfg.oosPct || 30; S.cfg.oosPct = 0; }
    else S.cfg.oosPct = +S.cfg.oosUltimo || 30;
    saveCfg();
    pintarOos();
    // apagar la reserva tiene que apagar también la exigencia de afuera: si
    // no, queda pedida sobre un tramo que ya no existe
    pintarExigir();
  });
  $$("#m-oos-pct button", main).forEach(b => b.onclick = () => {
    S.cfg.oosPct = +b.dataset.pct;
    saveCfg();
    pintarOos();
    pintarExigir();
  });

  /* Las varas también afuera. Se repinta junto con el tramo reservado porque
     depende de él: apagar la reserva tiene que apagar esto, y no dejarlo
     tildado pidiendo algo que ya no se puede medir. */
  const pintarExigir = () => {
    const hayReserva = +S.cfg.oosPct > 0;
    if (!hayReserva) S.cfg.exigirOos = false;
    $$("#m-oos-exig button", main).forEach(b => {
      const es = b.dataset.exig === "1";
      b.classList.toggle("on", es === !!S.cfg.exigirOos);
      if (es) {
        /* SE APAGA CON UNA CLASE Y NO CON `disabled`. `lockSetup` habilita
           todos los controles del panel cada vez que dibuja, así que la
           propiedad no sobrevive: el botón se veía disponible, se apretaba, y
           no pasaba nada. Lo que impide el clic es la condición del
           manejador; esto es lo que lo hace ver. */
        b.classList.toggle("apagado", !hayReserva);
        b.title = hayReserva ? "" : t("acc.necesita_reserva");
      }
    });
    const n = $("#m-exig-nota", main);
    if (n) {
      n.textContent = !hayReserva ? t("acc.necesita_reserva")
        : S.cfg.exigirOos ? t("acc.tambien_fuera_ayuda")
                          : t("acc.solo_dentro_ayuda");
    }
    updateNotes();
  };
  $$("#m-oos-exig button", main).forEach(b => b.onclick = () => {
    // SE GUARDA POR LA CONDICION Y NO POR EL ESTADO DEL BOTON. Si el atributo
    // `disabled` no llegara a pegarse —pasó— el clic entraría igual y pediría
    // que las varas se cumplan en un tramo que no existe.
    if (b.dataset.exig === "1" && !(+S.cfg.oosPct > 0)) return;
    S.cfg.exigirOos = b.dataset.exig === "1";
    saveCfg();
    pintarExigir();
  });
  pintarExigir();
  // y una vez al dibujar: la linea que explica el porcentaje se arma aca, asi
  // que sin esta llamada el paso abre en blanco justo debajo de los botones
  pintarOos();

  // el panel ya está en su lugar: recién ahora se puede medir cuánto espacio
  // le queda, y sin eso el botón de arrancar se sale de la ventana
  medirHuecoDelPanel();

  $$("#rk-sizing button", main).forEach(b => b.onclick = () => {
    S.cfg.sizing = b.dataset.v;
    $$("#rk-sizing button", main).forEach(x => x.classList.toggle("on", x === b));
    $("#rk-risk-box", main).hidden = S.cfg.sizing === "lots";
    $("#rk-lots-box", main).hidden = S.cfg.sizing !== "lots";
    saveCfg();
    updateNotes();
  });
  bindKnob("rk-rr", "rk-rr-presets", "rr", 0.25, 10);

  /* Prender "buscar" carga la lista entera de relaciones; apagarlo la borra y
     vuelve a mandar la del control de arriba. Se guarda la lista y no un
     booleano porque las recetas ya fijan sus propias listas acotadas —la de
     aciertos busca sólo entre 0,5 y 0,75— y un booleano no podría expresarlas. */
  $$("[data-rrmodo]").forEach(b => b.onclick = () => {
    S.cfg.rrBuscado = b.dataset.rrmodo === "buscar" ? [...RR_BUSCABLES] : null;
    saveCfg();
    navigate("mining", "buscar");
  });

  const dsSel = $("#sel-dataset"), tfSel = $("#sel-timeframe");
  dsSel.onchange = () => {
    /* LO QUE ESTE MERCADO TENÍA: su temporalidad, sus filtros y su receta.
       Sin esto, cambiar de mercado y volver borraba el ajuste a mano. */
    try {
      const guardado = JSON.parse(localStorage.getItem("qf.cfg_mercado") || "{}")[dsSel.value];
      if (guardado && guardado.cfg) {
        S.cfg = { ...S.cfg, ...guardado.cfg };
        if (guardado.timeframe) S.sel.timeframe = guardado.timeframe;
        S.recetaPuesta = guardado.receta || null;
      }
    } catch (e) { /* modo privado */ }
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
        toast(t("note.range_clamped", { mercado: ds.name.replace(/ M1.*/, "") }), "ok");
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
  const avz = $("#m-avanzado", main);
  if (avz) avz.ontoggle = () => { try { localStorage.setItem("qf.avanzado", avz.open ? "1" : "0"); } catch (e) { /* nada */ } };

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
    // el resumen del panel de espera sigue a lo elegido
    const idlePlan = $("#idle-plan");
    if (idlePlan && !S.mining) idlePlan.innerHTML = textoPlanIdle();
    const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
    const dsNote = $("#m-dsnote");
    if (ds && dsNote) {
      const r = effectiveRange(ds);
      const full = isFullRange(ds);
      const years = (new Date(r.to) - new Date(r.from)) / (365.25 * 24 * 3600 * 1000);
      const oos = +S.cfg.oosPct;
      const base = full
        ? t("note.full_history", { desde: esc(r.from), hasta: esc(r.to),
                                   anios: years.toFixed(1), precio: ds.last_close })
        : t("note.range", { desde: esc(r.from), hasta: esc(r.to), anios: years.toFixed(1),
                            lo: esc(datasetBounds(ds).lo), hi: esc(datasetBounds(ds).hi) });
      // si la validación está activa, el corte se calcula sobre ESE rango
      const corte = oos ? "<br>" + t("note.split", { mina: 100 - oos, valida: oos }) : "";
      dsNote.innerHTML = base + corte;
    }
    updateSummaries(ds);
    /* ¿La posicion que sale de este capital y este riesgo la acepta un broker?

       Es lo unico que el capital inicial deberia contestar y no contestaba.
       Cambiarlo de 500 a 100.000 dolares no movia ni una metrica — el riesgo
       porcentual escala todo por igual — asi que el campo parecia decorativo.
       Lo que si cambia es el TAMANO de la posicion, y por debajo del minimo del
       broker el minimo manda: pediste 1% y vas a arriesgar lo que el minimo
       imponga.

       Medido sobre S&P 500 con la configuracion por defecto: 10.000 dolares al
       1% dan 0.025 lotes contra un minimo de 0.1. El minimo fuerza 4%. */
    const chequeo = $("#m-realidad");
    if (chequeo) {
      const espec = ds || {};
      const stop = espec.suggested_stop;
      if (!ds || !stop || S.cfg.sizing === "lots") {
        chequeo.hidden = true;
      } else {
        chequeo.hidden = false;
        const plata = +S.cfg.capital * +S.cfg.riskPct / 100;
        const unidades = plata / stop;
        const contrato = +(espec.contract_size || 1);
        const lotes = unidades / contrato;
        const minimo = +S.cfg.minLot || +(espec.min_lot || 0.01);
        const entra = lotes >= minimo;
        // lo que el minimo del broker te obliga a arriesgar de verdad
        const forzado = minimo * contrato * stop;
        const pctForzado = forzado / +S.cfg.capital * 100;
        const capitalMinimo = forzado / (+S.cfg.riskPct / 100);
        chequeo.className = "realidad " + (entra ? "ok" : "mal");
        chequeo.innerHTML = `
          <div class="r-linea">${icono("info", "ico-sm")}
            <b>${esc(t("cap.fits"))}</b></div>
          <p>${t("cap.detail", {
            plata: fmtMoney(plata), lotes: lotes.toFixed(3),
            mercado: nombreCorto(ds.name) })}</p>
          ${entra ? "" : `<p class="r-aviso">${t("cap.forced", {
            pct: pctForzado.toFixed(1), pedido: S.cfg.riskPct,
            minimo, capital: fmtMoney(capitalMinimo) })}</p>`}
          <p class="help-note">${esc(t("cap.check_broker"))}</p>`;
      }
    }

    const note = $("#m-costnote");
    if (note) {
      const abs = +S.cfg.spread + 2 * +S.cfg.slippage;
      const pct = ds && ds.last_close ? abs / ds.last_close * 100 + 2 * +S.cfg.commission : null;
      let txt = t("note.round_trip", {
        abs: abs.toLocaleString(localeNum(), { maximumFractionDigits: 5 }) });
      if (pct != null) txt += ` ≈ <b>${pct.toFixed(3)}%</b>`;
      txt += ". " + t("note.match_broker");
      // un costo así se come cualquier estrategia: todas dan -100%
      const bad = pct != null && pct > 1;
      if (bad) {
        txt = `<b class="neg">${icono("alerta")} ${esc(t("note.impossible_cost", { pct: pct.toFixed(1) }))}</b>
          ${esc(t("note.impossible_cost_sub"))}
          <button class="linkbtn" id="fix-cost">${esc(t("note.use_defaults",
            { mercado: ds.name.replace(/ M1.*/, "") }))}</button>`;
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
        const num = (v) => (+v).toLocaleString(localeNum(), { maximumFractionDigits: 5 });
        const igual = Math.abs(+S.cfg.spread - refSpread) < 1e-9;
        sug.innerHTML = igual
          ? `<span class="sg-ok">${icono("tilde","ico-sm")}</span>
             <div>${t("note.typical_ok", { mercado, spread: num(refSpread) })}</div>`
          : `<span class="sg-ojo">${icono("info","ico-sm")}</span>
             <div>${t("note.typical_diff", { actual: num(S.cfg.spread),
               mercado, tipico: num(refSpread) })}
               <button class="linkbtn" id="usar-sugerido">${esc(t("note.use_typical"))}</button></div>`;
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
      riskHelp.innerHTML = t("help.risk", {
        pct: v, plata: (cap * v / 100).toFixed(0), capital: fmtInt(cap),
        racha: streak.toFixed(0),
      });
      riskHelp.classList.toggle("danger-note", streak >= 25);
    }

    /* El porcentaje de aciertos no se puede leer solo: con relación 1:3 hasta
       un 30% es rentable, y pedir 60% ahí es casi imposible por construcción. */
    // Destildado no es "sin configurar": es "no se exige". Con la casilla en
    // blanco el número de al lado igual se ve, y eso hace creer que la vara
    // está puesta.
    const critAviso = $("#m-critaviso");
    if (critAviso) {
      const activos = CRITERIA().filter(cr => S.cfg.critOn[cr.key]).length;
      critAviso.innerHTML = activos ? ""
        : `<b class="neg">${icono("alerta")} ${esc(t("help.no_crit_title"))}</b> ${
            t("help.no_crit", { n: S.cfg.minTrades })}`;
    }

    const critHelp = $("#m-crithelp");
    if (critHelp) {
      if (!S.cfg.critOn.minWinRate) {
        critHelp.innerHTML = "";
      } else {
        const rr = +S.cfg.rr, be = 100 / (1 + rr), pedido = +S.cfg.minWinRate;
        critHelp.innerHTML = pedido <= be
          ? `<b class="neg">${icono("alerta")} ${esc(t("help.wr_impossible_title", { pct: pedido }))}</b> ${
              t("help.wr_impossible", { rr, be: be.toFixed(0) })}`
          : t("help.wr_ok", { rr, be: be.toFixed(0), ventaja: (pedido - be).toFixed(0) })
            + (pedido - be > 15 ? " " + t("help.wr_high") : "");
      }
    }

    const lotsHelp = $("#m-lotshelp");
    if (lotsHelp) {
      lotsHelp.innerHTML = t("help.lots", { lots: S.cfg.lots });
    }

    const rrHelp = $("#m-rrhelp");
    if (rrHelp) {
      const rr = +S.cfg.rr;
      // el break-even sale de la relación: con 1:2 alcanza con acertar 1 de 3
      const be = 100 / (1 + rr);
      rrHelp.innerHTML = t("help.rr", {
        rr, be: be.toFixed(0),
        gana: (+S.cfg.capital * +S.cfg.riskPct / 100 * rr).toFixed(0),
        pierde: (+S.cfg.capital * +S.cfg.riskPct / 100).toFixed(0),
      });
    }
  }

  /* resumen de una línea en cada sección plegada: se ve la configuración
     entera sin tener que abrirlas una por una */
  function updateSummaries(ds) {
    const set = (id, txt) => { const el = $(`#${id}`, main); if (el) el.textContent = txt; };
    const ses = sesionesElegidas();
    set("sum-market", (ds ? `${ds.name.replace(/ M1.*/, "")} · ${S.sel.timeframe} · ${
      t("dir." + S.cfg.direction).toLowerCase()}` : "—")
      // la franja va en el resumen del desplegable cerrado porque cambia por
      // completo lo que la búsqueda puede encontrar, y no se ve sin abrirlo
      + (ses.length === 1 && ses[0] !== "todo" ? ` · ${nombreSesion(ses[0])}`
         : ses.length > 1 ? ` · ${t("sum.sessions", { n: ses.length })}` : "")
      /* Y el tramo reservado, por lo mismo: ahora vive adentro de este paso,
         y con el paso plegado no habría forma de saber que la búsqueda se
         está guardando un pedazo de la historia sin mirar. Sólo cuando está
         prendido — decir "apagado" en el resumen de un paso que tiene cinco
         cosas más es gastar la línea en la que no pasa nada. */
      + (+S.cfg.oosPct ? ` · ${t("oos.sum_on", { pct: S.cfg.oosPct })}` : "")
      );

    const drv = $$("#m-drivers .blockitem input", main).filter(x => x.checked).length;
    const flt = $$("#m-filters .blockitem input", main).filter(x => x.checked).length;
    const compl = COMPLEJIDAD().find(c => c.n === +S.cfg.maxFilters);
    set("sum-blocks", t("sum.blocks", {
      drv, flt, compl: (compl ? compl.nombre : S.cfg.maxFilters).toString().toLowerCase() }));

    // qué significa el número, con los valores que el usuario tiene puestos
    const fn = $("#m-filtnote");
    if (fn) {
      const n = +S.cfg.maxFilters;
      fn.innerHTML = !flt ? t("sum.no_filters")
        : n === 0 ? t("sum.minimal_ignores", { nombre: COMPLEJIDAD()[0].nombre.toLowerCase() })
        : t("sum.filters_note", { flt, n });
    }

    set("sum-risk", (S.cfg.sizing === "lots"
      ? t("sum.lots", { lots: S.cfg.lots }) : t("sum.risk", { pct: S.cfg.riskPct }))
      + ` · ${comoSeDiceElRR()} · ${t("sum.vol_stop_short")}`);

    /* El costo de mantener se muestra sólo cuando está puesto. Es el único
       costo que puede quedar activo sin que se vea —la sección va plegada— y
       un 5% anual encendido de más explicaría resultados malos sin motivo
       aparente. Los otros dos van siempre porque siempre valen algo. */
    set("sum-cost", t("sum.costs", {
      spread: S.cfg.spread, slip: S.cfg.slippage, cap: fmtInt(S.cfg.capital) })
      + (+S.cfg.swap > 0 ? ` · ${t("sum.swap", { pct: S.cfg.swap })}` : ""));

    /* Con el valor y no sólo el nombre del filtro. Decía "Profit factor" a
       secas, que al lado de "30+ operaciones" se lee como una frase cortada —
       y encima es el único de los seis resúmenes que no mostraba su número. */
    const on = CRITERIA().filter(cr => S.cfg.critOn[cr.key]);
    /* Y SI ADEMAS SE EXIGEN AFUERA. Es lo que más cambia el resultado de todo
       este paso —midiendo una corrida, de 9 estrategias a 7— y sin esto queda
       invisible con la sección plegada, que es como se ve casi siempre. */
    const tambienFuera = S.cfg.exigirOos && +S.cfg.oosPct > 0
      ? ` · ${t("acc.tambien_fuera").toLowerCase()}` : "";
    set("sum-crit", (on.length
      ? `${S.cfg.minTrades}+ ${t("m.trades").toLowerCase()} · ${
          on.map(cr => `${cr.label} ${S.cfg[cr.key]}${cr.unit || ""}`).join(" · ")}`
      : t("sum.only_trades", { n: S.cfg.minTrades })) + tambienFuera);

    set("sum-adv", `${S.cfg.method === "evolution"
      ? t("sum.method_evo_short") : t("sum.method_rnd_short")} · ${
      t("sum.cap_short", { n: fmtInt(S.cfg.maxCandidates) })}`);
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

  $$("[data-receta]", main).forEach(b => b.onclick = () => {
    /* CON UNA BÚSQUEDA CORRIENDO, LA RECETA NO SE CAMBIA. El panel dice que
       la configuración está congelada mientras busca, pero las tarjetas de
       arriba seguían aplicándose: la receta nueva se pintaba como elegida
       mientras la búsqueda seguía con la anterior, y el resumen de al lado
       decía una cosa y el progreso otra. Se dice, y no se hace. */
    if (S.mining) { toast(t("rec.congelada"), "err"); return; }
    const r = RECETAS().find(x => x.id === b.dataset.receta);
    if (r) aplicarReceta(r);
  });

  cablearSesiones(main);
  updateNotes();
  if (fixed) {
    toast(fixed.badCost
      ? t("data.costs_fixed", { mercado: fixed.name, pct: fixed.costPct.toFixed(1) })
      : t("data.exits_fixed", { mercado: fixed.name }), "ok");
  }
  if (S.mineResult || S.mineLive) renderMining(S.mineResult || S.mineLive, !!S.mineResult);
  else renderIdle();

  /* Si hay una busqueda corriendo, la pantalla recien dibujada tiene que
     mostrarla. Sin esto el boton volvia a decir "Iniciar minado" con la
     busqueda en curso: no habia como detenerla, y apretarlo lanzaba una
     SEGUNDA encima de la primera. */
  pintarEstadoMinado(S.mining);
  if (S.mining) pintarPausa(S.minePaused);

  $("#m-stop").onclick = async () => {
    if (S.mineJobId) {
      try { await api.post(`/api/jobs/${S.mineJobId}/stop`); toast(t("run.stopping")); }
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
      toast(r.paused ? t("run.paused_toast") : t("run.resumed_toast"));
    } catch (e) {
       toast(e.message, "err"); }
    btn.disabled = false;
  };

  /* LA BÚSQUEDA SOBREVIVE A UNA RECARGA. El trabajo corre en el servidor;
     lo que se perdía era el hilo desde la pantalla: al recargar, "lista
     para buscar" con la búsqueda viva detrás y sin forma de pausarla ni
     detenerla. El id del trabajo se guarda al arrancar y, al abrir Minado,
     si ese trabajo sigue corriendo se lo vuelve a seguir con la misma
     pantalla que si nunca se hubiera ido. */
  const correrMinado = async (reanudar = null) => {
    // se normaliza acá también: si alguien toca "Minar" con el cursor todavía
    // dentro de un campo, el `change` nunca llegó a saltar y la corrida saldría
    // con un valor a medio escribir o por debajo del piso
    if (!reanudar) harvestCfg(main, { normalizar: true });
    const checked = (sel) => $$(`${sel} .blockitem input`, main)
      .filter(cb => cb.checked).map(cb => cb.dataset.tid);
    const drivers = checked("#m-drivers");
    if (!reanudar && !drivers.length) { toast(t("mine.need_trigger"), "err"); return; }
    S.mining = true; S.mineResult = null; S.mineLive = null;
    pintarEstadoMinado(true);
    pintarPausa(false);
    // pintar el estado "buscando" YA: el primer snapshot del backend tarda
    // varios segundos en un dataset grande y sin esto la app parece colgada
    renderMining({ seed: "—", tested: 0, passed: 0, rejected: 0, kept: 0,
                   target: S.cfg.maxCandidates, target_keep: S.cfg.goal,
                   elapsed_s: 0, databank: [], best_history: [], diagnosis: {} }, false);
    setProgress("m-prog", { progress: 0, message: t("run.preparando") });
    const cfg = S.cfg;
    try {
      const result = await runJob("/api/mine", {
        dataset_id: S.sel.dataset_id, timeframe: S.sel.timeframe || "1h",
        ...rangePayload(),
        drivers, filters: checked("#m-filters"),
        // el objetivo manda; max_candidates es solo el tope de seguridad
        target_keep: cfg.goal, keep_top: Math.max(cfg.goal, 100),
        oos_pct: +cfg.oosPct || 0,
        // sin tramo reservado no hay nada afuera que exigir, y mandarlo en
        // true igual haría que el servidor rechazara todo
        exigir_oos: !!(cfg.exigirOos && +cfg.oosPct > 0),
        // sólo viaja si alguien lo pidió: sin la lista el servidor deja que
        // cada candidata use el R:B configurado, como siempre
        ...(cfg.rrBuscado?.length ? { rr_choices: cfg.rrBuscado } : {}),
        // sólo cuando se viene del botón de arreglo: repetir las mismas
        // candidatas es justo lo que hace que el arreglo funcione
        ...(SEMILLA_REINTENTO ? { seed: +SEMILLA_REINTENTO } : {}),
        max_candidates: cfg.maxCandidates, max_filters: cfg.maxFilters,
        sessions: sesionesElegidas(),
        method: cfg.method, population: 40,
        direction: cfg.direction, min_trades: cfg.minTrades, fitness: cfg.fitness,
        // un filtro sin tildar viaja como null: el backend lo ignora
        ...acceptPayload(),
        risk: riskPayload(),
        settings: {
          spread: cfg.spread, slippage: cfg.slippage,
          commission_pct: cfg.commission, swap_anual: cfg.swap, initial_capital: cfg.capital,
        },
      }, j => {
        /* La semilla se consume acá, en la primera vuelta del sondeo: ya viajó
           en el pedido. Si quedara puesta, TODAS las corridas siguientes
           repetirían las mismas candidatas y la aplicación dejaría de
           encontrar cosas nuevas — con la misma configuración devolvería
           siempre lo mismo, que es lo contrario de lo que hace. */
        SEMILLA_REINTENTO = null;
        /* LA LÍNEA DE PROGRESO SE ESCRIBE ACÁ, NO EN EL SERVIDOR. El mensaje
           del trabajo viene en español ("3/25 estrategias en el databank ·
           130 probadas") y se mostraba tal cual con la interfaz en inglés.
           Los números vienen aparte, así que el texto se arma en el idioma
           de la pantalla; sin números todavía, queda el mensaje del servidor. */
        setProgress("m-prog", j.partial ? { progress: j.progress, message: t("run.progreso", {
          k: Math.min((j.partial.databank || []).length, j.partial.kept ?? Infinity),
          meta: j.partial.target_keep ?? cfg.goal, n: fmtInt(j.partial.tested || 0) }) } : j);
        // el botón se sincroniza con el servidor y no con el clic: si el pedido
        // de pausa se perdió, la pantalla no puede seguir diciendo que pausó
        pintarPausa(!!j.paused);
        if (j.partial) { S.mineLive = j.partial; renderMining(j.partial, false); }
      }, id => {
        S.mineJobId = id;
        try { localStorage.setItem("qf.mineJob", id); } catch (e) { /* modo privado */ }
      }, reanudar);
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
      if (result.stopped) toast(t("run.stopped_kept", { n: kept }), "ok");
      else if (result.reached_goal)
        toast(t("run.kept", { n: kept, tiempo: fmtDur(result.elapsed_s) }), "ok");
      else toast(t("run.few_passed", { n: fmtInt(result.tested), kept }), "err");
      if (result.podadas) {
        toast(t("bank.pruned", { n: result.podadas }));
      }
    } catch (e) {
      /* SI NO ARRANCÓ, LA PANTALLA VUELVE A "LISTA PARA BUSCAR". Antes
         quedaba el panel de "buscando" con cero probadas y la tarjeta de
         corrida activa en la barra lateral, sin ninguna búsqueda detrás: el
         siguiente clic en una receta la redibujaba a medias y la pausa no
         apuntaba a nada. Pasó con un 500 del servidor en la primera
         búsqueda de un usuario nuevo. */
      /* SERVIDOR OCUPADO (429): la búsqueda no espera en cola —es pausable y
         se mira mientras corre—, así que se avisa en el panel y se reintenta
         sola a los 30 segundos. El botón es #m-run: con otro id el reintento
         no ocurría nunca (encontrado el 2 de septiembre). */
      if (e && e.status === 429) {
        // el texto del servidor viene en español y en una sola voz; el que
        // se muestra es el de la pantalla, en el idioma elegido
        S.avisoOcupado = true;
        clearTimeout(REINTENTO_OCUPADO);
        REINTENTO_OCUPADO = setTimeout(() => {
          const b = $("#m-run");
          if (b && !S.mining) b.click();
        }, 30000);
        toast(t("run.ocupado"), "err");
      } else {
        toast(e.message, "err");
      }
      hideProgress("m-prog");
      S.mineLive = null;
      pintarCorrida(null, true);
      renderIdle();
      if (S.avisoOcupado) {
        const live = $("#m-live");
        if (live) live.insertAdjacentHTML("afterbegin", `<div class="pista mb">${icono("alerta", "ico-sm")}<div>${esc(t("run.ocupado_largo"))}</div></div>`);
        S.avisoOcupado = false;
      }
    }
    S.mining = false; S.mineJobId = null; S.minePaused = false;
    try { localStorage.removeItem("qf.mineJob"); } catch (e) { /* modo privado */ }
    pintarEstadoMinado(false);
  };
  $("#m-run").onclick = () => correrMinado(null);

  // Si quedó una búsqueda corriendo de antes de recargar, se la sigue.
  let pendiente = null;
  try { pendiente = localStorage.getItem("qf.mineJob"); } catch (e) { /* modo privado */ }
  if (pendiente && !S.mining) {
    api.get(`/api/jobs/${pendiente}`).then(j => {
      if (j && j.status === "running") correrMinado(pendiente);
      else { try { localStorage.removeItem("qf.mineJob"); } catch (e) { /* nada */ } }
    }).catch(() => { try { localStorage.removeItem("qf.mineJob"); } catch (e) { /* nada */ } });
  }
};

/* El botón de pausa dice qué va a pasar si lo apretás, no en qué estado está:
   "Seguir" cuando está pausado, "Pausar" cuando está buscando. Un control que
   se rotula con su estado hace dudar en el momento de tocarlo. */
function pintarPausa(on) {
  S.minePaused = !!on;
  const btn = $("#m-pause");
  if (!btn) return;
  btn.innerHTML = on ? `${icono("seguir")} ${esc(t("mine.resume"))}`
                     : `${icono("pausa")} ${esc(t("mine.pause"))}`;
  btn.classList.toggle("pausado", !!on);
  $("#m-runbar")?.classList.toggle("pausado", !!on);
  $("#nav [data-page='mining']")?.classList.toggle("pausado", !!on);
  /* Y el título del panel, acá mismo: mientras está en pausa el trabajo no
     informa, así que nadie lo vuelve a dibujar y quedaba en "Buscando
     estrategias" con el contador quieto. */
  const h = $("#m-live h2");
  if (h && !h.dataset.fin) h.textContent = on ? t("run.pausada") : t("run.searching");
}

/* La columna de resultados antes de la primera corrida: explica el flujo y
   confirma qué se va a buscar, en vez de mostrar un hueco vacío. */
/* EL RESUMEN DE LO QUE SE VA A BUSCAR, en una función aparte porque se
   vuelve a escribir con cada cambio. Antes se escribía una sola vez al
   dibujar el panel: se cambiaba la temporalidad a 1d y el texto seguía
   diciendo "en velas de 1h" (2 de septiembre). Un resumen que no dice lo
   que está elegido es peor que ninguno. */
function textoPlanIdle() {
  const ds = S.datasets.find(d => d.id === S.sel.dataset_id);
  const on = CRITERIA().filter(cr => S.cfg.critOn[cr.key]);
  const ses = sesionesElegidas();
  return `${S.primeraBusqueda ? `<p class="pista-primera">${icono("idea", "ico-sm")} ${esc(t("mine.primera"))}</p>` : ""}
  <h2>${esc(t("idle.title"))}</h2>
        <p>${t("idle.plan", {
          goal: S.cfg.goal,
          mercado: esc(ds ? ds.name.replace(/ M1.*/, "") : "—"),
          tf: esc(S.sel.timeframe || "1h"),
          tamano: S.cfg.sizing === "lots"
            ? t("sum.lots", { lots: S.cfg.lots }) : t("sum.risk", { pct: S.cfg.riskPct }),
          rr: comoSeDiceElRR(),
          trades: S.cfg.minTrades,
        })}${on.length
          ? " " + t("idle.and_meet", {
              /* CADA FILTRO, DICHO: "Profit factor ≥ 1.15" es la métrica; lo
                 que significa es "ganaron más de lo que perdieron". Se dice lo
                 segundo y la métrica queda al pasar el mouse. */
              lista: on.map(cr => `<b title="${esc(cr.label)} ${S.cfg[cr.key]}${cr.unit}">${
                esc((LLANO()[cr.key] || cr.label).replace("{v}", S.cfg[cr.key] + cr.unit))}</b>`).join(", ") })
          : ""}</p>
        ${ses.length === 1 && ses[0] !== "todo"
          ? `<p class="idle-ses">${icono("info","ico-sm")} ${esc(t("idle.session_one",
              { nombre: nombreSesion(ses[0]), horas: horasSesion(ses[0]) }))}</p>`
          : ses.length > 1
            ? `<p class="idle-ses">${icono("info","ico-sm")} ${esc(t("idle.session_many", { n: ses.length }))}</p>`
            : ""}
        ${/* Sólo si NO hay ningún criterio tildado. Durante la preparación
              la pantalla se dibuja antes de que la receta termine de
              aplicarse y el aviso salía en falso. */ ""}
        ${on.length || S.mining ? "" : `<p class="idle-warn">${t("idle.no_filters")}</p>`}
`;
}

function renderIdle() {
  const live = $("#m-live"), bankBox = $("#m-bank");
  if (!live) return;
  /* La marca de "ya está partido en dos" se borra: si no, después de un
     arranque fallido la pantalla quedaba en "Lista para buscar" con la
     búsqueda corriendo por detrás. */
  delete live.dataset.partido;
  live.innerHTML = `
  <div class="idle-card">
    <div class="idle-ready">
      <span class="idle-ic">${icono("pico","ico-xl")}</span>
      <div id="idle-plan">${textoPlanIdle()}</div>
    </div>
    ${/* LAS CUATRO COLUMNAS QUIETAS PASAN A SER UN RECORRIDO. Un diagrama
          que se lee a medias, con un punto que avanza se sigue entero: la
          vista va a donde está pasando algo. Nace abierto, se reproduce
          al apretar, y da la vuelta porque la búsqueda también la da. */ ""}
    ${explicacionHTML("minar", PASOS_MINAR(), { abierta: true, fija: true, ciclico: true })}
  </div>${panelUltima()}`;
  atarExplicacion(live, "minar", PASOS_MINAR(), { ciclico: true });
  if (bankBox) bankBox.innerHTML = "";
  // arranca una busqueda nueva: lo que se vio en la anterior no cuenta
  S.vistasBanco = null;

  const irUltima = $("#idle-ver-ultima", live);
  if (irUltima) irUltima.onclick = () => {
    S.banco.corrida = irUltima.dataset.corrida;
    S.bancoSort = ORDEN_NATURAL(false);
    S.banco.sel.clear();
    navigate("mining", "resultados");
  };
}

/* Qué pasó la vez anterior, debajo de "Listo para buscar".

   La columna derecha terminaba a media pantalla y abajo quedaban unos 400px
   vacíos. El hueco no se llena por llenarlo: ahí falta justamente lo que uno
   quiere saber antes de apretar Iniciar de nuevo — cómo salió la búsqueda
   pasada—, y sin eso hay que irse a Resultados, mirar, y volver.

   El recorrido lo dibuja `embudoCorrida`, la misma función que usa Resultados.
   Dos formas de contar lo mismo terminan diciendo cosas distintas del mismo
   número en cuanto alguien toca una. */
function panelUltima() {
  const c = (S.banco?.corridas || [])[0];
  if (!c) return "";                      // todavía no buscó nunca
  return `
  <div class="card ultima">
    <h2>${esc(t("idle.last_run"))}
      <span class="hint">${esc(etiquetaCorrida(c))} · ${esc(cuando(c.created))}</span></h2>
    ${embudoCorrida(c)}
    <div class="ultima-pie">
      <button class="btn ghost small" id="idle-ver-ultima"
        data-corrida="${esc(c.id)}">${esc(t("idle.see_last"))}</button>
      <span class="muted">${esc(varaDe(c))}</span>
    </div>
  </div>`;
}

/* Cuánto sobrevivió la ventaja fuera de muestra. Es la única columna del
   databank que no está contaminada por haber elegido la estrategia mirando
   esos mismos datos, así que se muestra con su propio semáforo. */
function oosCell(r) {
  const oos = r.oos;
  if (!oos) return `<span class="muted">—</span>`;
  if (!oos.trades) {
    return `<span class="oos-tag none" title="${esc(t("col.oos_nodata_help"))}"
      >${esc(t("col.oos_nodata"))}</span>`;
  }
  const q = r.oos_ratio;
  const cls = q >= 0.8 ? "good" : q >= 0.5 ? "mid" : "bad";
  const etiqueta = q >= 0.8 ? t("col.oos_holds") : q >= 0.5 ? t("col.oos_weakens") : t("col.oos_falls");
  return `<span class="oos-tag ${cls}"
    title="PF ${fmtNum(oos.profit_factor)} / ${fmtNum(r.metrics.profit_factor)} · ${oos.trades} ${esc(t("m.trades").toLowerCase())} · ${fmtPct(oos.net_profit_pct)}">
    <b>${fmtNum(q, 2)}×</b><em>${esc(etiqueta)}</em></span>`;
}

/* Los parámetros de una estrategia, en una línea.

   Se arma acá y no se usa el `genes_label` que guardó el minero porque ese
   texto quedó congelado en el idioma que había cuando se minó. Los datos
   crudos —los genes, el stop, el trailing— viajan igual en la fila, así que
   la etiqueta se puede volver a escribir en el idioma que corresponda.

   Las estrategias guardadas antes de esto no traen los genes sueltos: para
   ésas se usa el texto viejo, que es mejor que no mostrar nada. */
function etiquetaGenes(r) {
  if (!r) return "";
  if (!r.genes) return r.genes_label || "";
  const partes = [];
  for (const id of [r.driver, ...(r.filters || [])]) {
    const vals = r.genes[id];
    if (!vals) continue;
    const kv = Object.keys(vals).sort().map(k => `${k}=${(+vals[k])}`).join(",");
    if (kv) partes.push(kv);
  }
  if (r.stop_mult != null) partes.push(`SL=${r.stop_mult}×ATR`);
  if (r.trail_mult) partes.push(`${t("gene.trail")}=${r.trail_mult}×ATR`);
  if (r.max_bars) partes.push(t("gene.max_bars", { n: r.max_bars }));
  /* La relación, sólo cuando la búsqueda la eligió. Con el R:B fijo por
     configuración es el mismo para todas y repetirlo en cada fila es ruido;
     cuando se busca, es lo que distingue una fila de otra — y la que más les
     cambia el carácter, porque gobierna el win rate. */
  if (r.rr_mult != null) partes.push(`${t("gene.rb")} 1:${r.rr_mult}`);
  // la franja NO va acá: ya tiene su propia etiqueta al lado del nombre, y
  // repetirla hace la línea más larga sin decir nada nuevo
  return partes.join(" · ");
}

/* La franja horaria de una fila, como etiqueta al lado del nombre.

   Va ahí y no en una columna propia porque la tabla tiene ocho a propósito
   (ver el comentario de la tabla) y agregar una novena la mandaría de vuelta
   al scroll horizontal. Sólo aparece cuando la estrategia está restringida:
   "todo el día" es la ausencia de horario y no vale una etiqueta. */
function sesionTag(r) {
  const id = r && r.session;
  if (!id || id === "todo") return "";
  const horas = r.session_hours || horasSesion(id);
  return `<span class="ses-tag" title="${esc(t("m.session"))}: ${esc(nombreSesion(id))}${
    horas ? ` · ${esc(horas)}` : ""}">${esc(nombreSesion(id))}</span>`;
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
        <span>${esc(t("busca.tested"))}${snap.passed
          ? ` · <b class="pos">${fmtInt(snap.passed)}</b> ${esc(t("busca.accepted"))}` : ""}</span>
      </div>
    </div>
    ${barras.length ? `
      <div class="buscando-motivos">
        <span class="bm-tit">${esc(t("busca.why"))}</span>
        ${barras.map(([clave, n]) => `
          <div class="bm-fila">
            <span class="bm-lab">${esc(nombreDeRechazo(clave))}</span>
            <span class="bm-track"><i style="width:${(n / tope * 100).toFixed(0)}%"></i></span>
            <span class="bm-n">${fmtInt(n)}</span>
          </div>`).join("")}
      </div>`
      : `<p class="bm-tit" style="margin-top:16px">${esc(t("run.preparing"))}</p>`}
    ${consejo(snap)}
    <p class="buscando-pie">${esc(t("busca.foot"))}</p>
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
/* Por qué el databank está vacío, y qué aflojar.

   El texto se arma acá y no en el servidor aunque el servidor ya lo mande
   hecho: viene en español, y esta pantalla existe en dos idiomas. El servidor
   manda los datos —qué criterio, cuánto se pidió, hasta dónde llegó, cuántas
   se cayeron sólo por ése— y la frase la escribe quien sabe en qué idioma
   está mirando el usuario. */
function textoDiagnostico(d) {
  if (!d || !d.reason) return "";
  if (d.reason === "trades") {
    const ses = d.sessions || [];
    return t("diag.trades", { n: d.tested, min: d.min_trades })
      + (ses.length
         ? " " + t("diag.trades_session", { franjas: ses.map(nombreSesion).join(", ") })
         : "");
  }
  const nombre = nombreDeRechazo(d.reason);
  const cerca = (d.near_miss || {})[d.reason];
  if (cerca) {
    return t("diag.near", {
      n: cerca, criterio: nombre,
      pedido: fmtNum(d.limit, 2), llego: fmtNum(d.best_reached, 2),
    });
  }
  if (d.best_reached == null) return "";
  return t("diag.far", {
    criterio: nombre, n: d.rejected,
    pedido: fmtNum(d.limit, 2), llego: fmtNum(d.best_reached, 2),
  });
}

/* La semilla que hay que reusar en el próximo minado, si lo pidió el botón de
   arreglo. Se consume una vez: la corrida siguiente vuelve a sortear sola. */
let SEMILLA_REINTENTO = null;

/* Aplicar el arreglo y volver a buscar.

   Por delegación en el documento y no atado al nodo: la pantalla del minado se
   redibuja en cada vuelta del sondeo, así que cualquier manejador colgado de un
   botón concreto se pierde en el redibujo siguiente. Con esto no hay nodo que
   perder. */
document.addEventListener("click", (ev) => {
  const b = ev.target.closest?.("#m-arreglar");
  if (!b) return;
  const clave = b.dataset.clave;
  const valor = b.dataset.valor;
  if (valor === "") S.cfg.critOn[clave] = false;
  else { S.cfg[clave] = +valor; S.cfg.critOn[clave] = true; }
  /* Si la búsqueda se cortó por el tope y no por falta de candidatas buenas,
     bajar la vara sin levantar el tope la deja parando en el mismo lugar por
     el mismo motivo. */
  if (b.dataset.tope) {
    S.cfg.maxCandidates = Math.min(20000, (+S.cfg.maxCandidates || 2000) * 5);
  }
  saveCfg();
  // la semilla de la corrida fallida: regenera las mismas candidatas, así que
  // las que estaban cerca entran seguro en vez de depender del azar
  SEMILLA_REINTENTO = b.dataset.semilla || null;
  // se redibuja la pantalla para que la sección 5 MUESTRE lo que se tocó —el
  // usuario tiene que poder ver qué cambió— y desde ahí arranca sola
  navigate("mining", "buscar").then(() => {
    toast(t("fix.aplicado"), "ok");
    $("#m-run")?.click();
  });
});

/* El botón. Dice exactamente qué va a cambiar antes de cambiarlo: nadie
   aprieta un botón que dice "arreglar" sin saber qué toca. */
function botonArreglo(d, snap) {
  const a = arregloSugerido(d);
  if (!a) return "";
  /* La semilla de ESTA corrida viaja con el botón. Al volver a buscar con
     ella se regeneran exactamente las mismas candidatas, así que las que
     estaban cerca entran con seguridad. Sin esto el arreglo es una apuesta:
     medido, bajar la vara y volver a sortear encontró cero. */
  return `<button class="btn mt" id="m-arreglar"
    data-semilla="${esc(String(snap?.seed ?? ""))}"
    data-tope="${snap?.hit_cap ? "1" : ""}"
    data-clave="${esc(a.clave)}" data-valor="${a.apagar ? "" : a.valor}">${
    esc(a.apagar
      ? t("fix.apagar", { criterio: a.nombre })
      : t("fix.bajar", { criterio: a.nombre, valor: a.valor }))}</button>`;
}

/* El arreglo que la aplicación ya dedujo, listo para aplicar de un clic.

   El diagnóstico dice qué criterio bloquea, qué se pidió y hasta dónde se
   llegó — y después manda al usuario a cambiarlo a mano: subir, abrir la
   sección 5, encontrar ese filtro entre nueve, cambiar el número, y volver a
   minar. Cinco pasos para aplicar una conclusión que ya está sacada.

   Devuelve null cuando no hay nada sensato que ofrecer. */
function arregloSugerido(d) {
  if (!d || !d.reason || d.best_reached == null) return null;
  const clave = CRIT_POR_CAMPO[d.reason];
  if (!clave) return null;                       // min_trades y desconocidos
  const cr = CRIT_BY_KEY()[clave];
  if (!cr) return null;

  const esMaximo = clave === "maxDd";            // el único donde menos es más
  // un pelín más flojo que el techo alcanzado: pedir exactamente el máximo
  // dejaría pasar una sola candidata, que no es una búsqueda
  const holgura = esMaximo ? 1.05 : 0.95;
  let valor = +(d.best_reached * holgura);
  valor = +valor.toFixed(valor < 10 ? 2 : 0);

  // Si ni aflojando llega al mínimo que el criterio admite, bajarlo es fingir
  // que el mercado da algo que no da. Ahí lo honesto es apagarlo.
  if (!esMaximo && cr.min != null && valor < cr.min) {
    return { clave, apagar: true, nombre: nombreDeRechazo(d.reason) };
  }
  return { clave, valor, apagar: false, nombre: nombreDeRechazo(d.reason) };
}

/* "Pediste 20% anual y el techo de este mercado es 5%": qué haría falta y qué
   costaría. Los números los calcula el minero —CAGR y drawdown escalan casi
   lineal con el riesgo por operación, medido— y la frase se arma acá, en el
   idioma que corresponda. */
function sugerenciaRiesgo(sug) {
  if (!sug) return "";
  const unidad = sug.size_mode === "risk_pct" ? t("sug.per_trade") : t("sug.notional");
  const cuerpo = sug.unreachable
    ? t("sug.unreachable", {
        factor: fmtNum(sug.factor, 0),
        haria: fmtNum(sug.current * sug.factor, 1),
        realista: sug.realistic_target,
        unidad, subir: fmtNum(sug.current * 4, 1),
      })
    : t("sug.reachable", {
        unidad, actual: sug.current, necesario: sug.needed,
        factor: fmtNum(sug.factor, 1),
        ddahora: fmtNum(sug.dd_now, 0), ddluego: fmtNum(sug.dd_projected, 0),
      });
  const aviso = sug.unreachable ? t("sug.warn_market")
    : sug.dd_projected >= 45 ? t("sug.warn_dd") : "";
  return `<div class="suggestion mt">
    <div class="sug-title">${icono("idea")} ${esc(t("sug.title"))}</div>
    <p>${cuerpo}</p>
    ${aviso ? `<p class="sug-warn">${icono("alerta")} ${esc(aviso)}</p>` : ""}
    ${sug.unreachable
      ? `<button class="btn small mt" id="apply-target" data-target="${sug.realistic_target}">${
          esc(t("sug.apply_target", { n: sug.realistic_target }))}</button>`
      : `<button class="btn small mt" id="apply-risk" data-needed="${sug.needed}">${
          esc(t("sug.apply_risk", { n: sug.needed }))}</button>`}
  </div>`;
}

function consejo(snap) {
  const d = snap.diagnosis || {};
  const txt = textoDiagnostico(d);
  if (!txt || (snap.tested || 0) < 60) return "";
  return `<div class="consejo"><span class="c-ic">${icono("idea")}</span><div>${txt}</div></div>`;
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
    <div class="corrida-rot">${esc(t("nav.active_run"))}</div>
    <div class="corrida-cifra">${meta ? `${hechas}<u>/${meta}</u>` : fmtInt(snap.tested || 0)}</div>
    <div class="corrida-pie">${meta ? esc(t("run.in_bank")) + " · " : ""}${
      esc(t("run.pie", { n: fmtInt(snap.tested || 0) }))}</div>
    ${meta ? `<div class="corrida-barra"><i style="width:${(frac * 100).toFixed(1)}%"></i></div>` : ""}`;
}

/* ------------------------------------------------------- render resultados */
function renderMining(snap, finished) {
  const live = $("#m-live"), bankBox = $("#m-bank");
  if (!live || !snap) return;
  const bank = ordenarBank(snap.databank || []);
  pintarCorrida(snap, finished);
  /* EL CAMPEÓN ES EL DE MEJOR SCORE, y se elige mirando: la lista viene
     ordenada por el fitness de la búsqueda, así que "Mejor hasta ahora"
     mostraba una de 31 con otras de 72 en la tabla (visto el 2 de
     septiembre). Reordenar la tabla sigue sin cambiarlo. */
  const champ = [...(snap.databank || [])].sort(
    (a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity))[0];

  const s = S.bankSort || {};
  const th = (key, label, ayuda) => {
    const activa = s.key === key;
    const flecha = activa ? (s.dir === -1 ? icono("baja","ico-sm") : icono("sube","ico-sm")) : "";
    return `<th class="num orden ${activa ? "activa" : ""}" data-sort="${key}"
      title="${esc(ayuda)}${activa ? "" : ` · ${esc(t("col.click_sort"))}`}">${label}<i>${flecha}</i></th>`;
  };

  const goal = snap.target_keep || null;
  const kept = goal ? Math.min(bank.length, goal) : bank.length;
  const frac = goal ? kept / goal : (snap.tested / (snap.target || 1));
  const rate = snap.tested && snap.elapsed_s > 0 ? snap.passed / snap.elapsed_s : 0;
  // sin filtros activos el databank también junta perdedoras: decirlo de frente
  const winners = bank.filter(r => r.metrics.net_profit_pct > 0).length;

  // por qué terminó: el usuario no tiene que deducirlo de los números
  let banner = "";
  if (finished) primerPaso("buscaste");
  if (finished && snap.stopped) {
    banner = `<div class="banner info"><span class="b-ic">${icono("detener")}</span><div>
      ${t("run.stopped", { n: bank.length })}</div></div>`;
  } else if (finished && snap.exhausted) {
    banner = `<div class="banner"><span class="b-ic">${icono("info")}</span><div>
      ${t("run.exhausted")}</div></div>`;
  } else if (finished && snap.hit_cap) {
    banner = `<div class="banner"><span class="b-ic">${icono("alerta")}</span><div>
      ${t("run.hit_cap", { tope: fmtInt(snap.target), n: bank.length, goal })}</div></div>`;
  } else if (!finished && !bank.length && snap.tested >= 20 && textoDiagnostico(snap.diagnosis)) {
    // no esperar al final para explicar por qué no entra ninguna: el usuario
    // puede aflojar el filtro ahora mismo en vez de mirar un cero por minutos
    banner = `<div class="banner"><span class="b-ic">${icono("diana")}</span><div>${
      textoDiagnostico(snap.diagnosis)}</div></div>`;
  } else if (finished && goal && snap.reached_goal) {
    banner = `<div class="banner ok"><span class="b-ic">${icono("tilde")}</span><div>
      ${t("run.reached", { goal, probadas: fmtInt(snap.tested), tiempo: fmtDur(snap.elapsed_s) })}</div></div>`;
  }

  /* Todo lo que cambia en cada vuelta va acá y se repinta siempre. El anillo
     queda fuera a propósito: rehacer su SVG lo dejaría sin punto de partida
     para animar y se vería saltar de un valor al siguiente en vez de avanzar.

     Estuvieron juntos, y como `ringUpdate` devuelve `true` siempre que el
     anillo existe, la tarjeta no se repintaba nunca: a los 55 segundos de
     minar decía "Tested 0 · Elapsed 0s" con 70 candidatas probadas de verdad,
     y arrastraba un cartel rojo diciendo que la búsqueda no tenía filtros
     cuando sí los tenía. */
  const goalLado = `
      <div class="goal-title">
        ${/* EN PAUSA LO DICE. El botón cambiaba a "Seguir" pero el panel
              seguía titulando "Buscando estrategias" con el contador
              congelado: la pantalla decía una cosa y hacía otra
              (3 de septiembre de 2026). */ ""}
        <h2${finished ? ' data-fin="1"' : ""}>${esc(finished ? t("run.done") : S.minePaused ? t("run.pausada") : t("run.searching"))}</h2>
        ${finished ? "" : `<span class="mining-live">
          <span class="scanner"><i></i><i></i><i></i><i></i><i></i></span>
          ${esc(snap.tested ? t("run.trying", { n: fmtInt(snap.tested + 1) })
                            : t("run.preparing"))}
        </span>`}
      </div>
      <div class="goal-sub">${goal
        ? t("run.until", { goal, faltan: Math.max(goal - kept, 0) })
        : t("run.until_cap", { n: fmtInt(snap.target) })}
        · ${t("run.seed", { seed: snap.seed })}</div>
      ${varaAplicada(snap)}
      <div class="statgrid">
        <div class="stat"><span>${esc(t("run.tested"))}</span><b>${fmtInt(snap.tested)}</b></div>
        <div class="stat"><span>${esc(t("run.profitable"))}</span><b class="${winners ? "pos" : "neg"}">${winners}<u>${esc(t("ui.of"))} ${bank.length}</u></b></div>
        <div class="stat"><span>${esc(t("run.hit_rate"))}</span><b>${snap.tested ? (snap.passed / snap.tested * 100).toFixed(1) : "0.0"}<u>%</u></b></div>
        <div class="stat"><span>${esc(finished ? t("run.duration") : t("run.elapsed"))}</span><b>${fmtDur(snap.elapsed_s)}</b></div>
        ${!finished && goal ? `<div class="stat"><span>${esc(t("run.eta"))}</span><b>${
          snap.eta_s != null ? fmtDur(snap.eta_s) : "—"}</b></div>` : ""}
        ${/* EL RITMO, EN PALABRAS: "0.03 acept./s" no le dice nada a nadie;
              "1 cada 33 s" sí (2 de septiembre). */ ""}
        <div class="stat"><span>${esc(t("run.rate"))}</span><b>${
          rate ? (rate >= 1 ? `${rate.toFixed(1)}<u>${esc(t("run.por_seg"))}</u>`
                            : `1<u>${esc(t("run.cada", { s: fmtDur(Math.round(1 / rate)) }))}</u>`)
               : "—"}</b></div>
      </div>
      ${banner}`;

  const goalCard = `
  <div class="goalcard ${finished ? "" : "running"}">
    <div class="ring">${Charts.ringSvg(frac)}
      <div class="ring-label">
        <b>${goal ? `${kept}/${goal}` : fmtInt(snap.tested)}</b>
        <span>${goal ? esc(t("run.in_bank")) : esc(t("run.tested"))}</span>
      </div>
    </div>
    <div class="goal-side" id="m-goal-lado">${goalLado}</div>
  </div>`;

  const champCardHtml = champ ? `<div class="champ" id="champ-card">
    <div>
      <div class="champ-tag">${icono("estrella")} ${esc(finished ? t("run.best") : t("run.best_so_far"))}</div>
      <h2>${esc(champ.name)} ${scoreBadge(champ.score, "big")}${sesionTag(champ)}</h2>
      <div class="champ-blocks">${esc(champ.blocks || "")}</div>
      <div class="champ-genes">${esc(etiquetaGenes(champ))}</div>
      <div class="champ-spark">${Charts.sparkSvg(champ.spark, { width: 240, height: 54 })}</div>
      ${scoreBars(champ.score_parts)}
      <div class="champ-cta">${esc(t("run.open_full"))} →</div>
    </div>
    <div class="champ-metrics">
      <div><span>${rotuloMetrica("m.cagr")}</span><b class="${champ.metrics.cagr_pct >= 0 ? "pos" : "neg"}">${fmtPct(champ.metrics.cagr_pct)}</b></div>
      <div><span>${esc(t("m.net"))} ${champ.metrics.years ? `${fmtNum(champ.metrics.years, 1)} ${esc(t("m.years").toLowerCase())}` : ""}</span><b class="${champ.metrics.net_profit_pct >= 0 ? "pos" : "neg"}">${fmtPct(champ.metrics.net_profit_pct)}</b></div>
      <div><span>${rotuloMetrica("m.pf")}</span><b>${fmtNum(champ.metrics.profit_factor)}</b></div>
      <div><span>${rotuloMetrica("m.sharpe")}</span><b>${fmtNum(champ.metrics.sharpe)}</b></div>
      <div><span>${rotuloMetrica("m.dd")}</span><b class="${
        nivelDD(champ.metrics.max_drawdown_pct, riesgoActual())}">${
        fmtNum(champ.metrics.max_drawdown_pct, 1)}%</b></div>
      <div><span>${esc(t("m.exposure"))}</span><b>${fmtNum(champ.metrics.exposure_pct ?? 0, 1)}%</b></div>
      <div><span>${rotuloMetrica("m.trades")}</span><b>${champ.metrics.trades}</b></div>
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
       <h2>${esc(t("run.history"))} <span class="hint">${esc(t("run.history_hint"))}</span></h2>
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
  /* La tarjeta del objetivo se reescribe entera sólo cuando cambió algo que
     no sea el anillo. Si se reescribiera siempre, el SVG del anillo seria un
     nodo nuevo en cada vuelta y su transicion no tendria desde donde animar:
     se veria saltar de un valor al siguiente. Moviendo el anillo por separado,
     avanza. */
  const anillo = $("#m-goal .ring", live);
  const movido = anillo && !finished && Charts.ringUpdate(anillo, frac);
  /* El lado se repinta SIEMPRE. Esto se saltaba cuando el anillo se había
     movido —y se mueve en todas las vueltas—, así que después del primer
     dibujo los contadores no volvían a cambiar. */
  pintar("#m-goal-lado", goalLado);
  if (!movido) pintar("#m-goal", goalCard);
  else {
    // el numero de al lado sigue al anillo, sin rehacer la tarjeta
    const cifra = $("#m-goal .ring-label b", live);
    const texto = goal ? `${kept}/${goal}` : fmtInt(snap.tested);
    if (cifra && cifra.textContent !== texto) {
      cifra.textContent = texto;
      cifra.classList.remove("sube");
      void cifra.offsetWidth;          // reinicia la animacion
      cifra.classList.add("sube");
    }
    $("#m-goal", live).dataset.h = goalCard;   // que el proximo cambio real entre
  }
  pintar("#m-champ", champCardHtml);
  pintar("#m-histbox", histHtml);

  // el gráfico se redibuja siempre que haya datos nuevos, pero el contenedor
  // sólo se recrea cuando cambió: así el canvas no se pierde en cada vuelta
  if (snap.best_history?.length > 1) {
    const caja = $("#m-hist");
    if (caja) Charts.line(caja, { series: [{ values: snap.best_history, fill: true }], height: 170 });
  }
  const champCard = $("#champ-card");
  if (champCard) champCard.onclick = () => openInspector(champ, ctxDeLaCorrida(snap));

  const splitNote = snap.split ? `
    <div class="banner info mt" style="margin-bottom:14px">
      <span class="b-ic">${icono("marcador")}</span><div>${t("run.split_note", {
        desde: esc(snap.split.is_from), hasta: esc(snap.split.is_to),
        velas: fmtInt(snap.split.is_bars),
        odesde: esc(snap.split.oos_from), ohasta: esc(snap.split.oos_to),
        ovelas: fmtInt(snap.split.oos_bars),
        columna: t("col.oos_full"),
      })}</div>
    </div>` : "";

  const bankHtml = `
  <div class="card">
    ${splitNote}
    <h2>${esc(t("nav.bank"))} <span class="hint">${esc(t("run.bank_hint", { n: bank.length }))}</span>
      ${/* TODAS A MIS ESTRATEGIAS EN UN CLIC, cuando la búsqueda terminó y ya
            está archivada: es lo que uno quiere hacer con lo recién encontrado
            antes de probarlas juntas. */
        finished && snap.corrida_id && bank.length
          ? `<button class="btn small" id="guardar-todas" style="margin-left:auto">${
              icono("marcador", "ico-sm")} ${esc(t("bank.guardar_todas", { n: bank.length }))}</button>` : ""}</h2>
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
        <th>${esc(t("col.strategy"))}</th>
        <th>${esc(t("col.equity"))}</th>
        ${th("score", esc(t("m.score")), t("col.score_help"))}
        ${th("cagr", esc(t("col.annual")), t("crit.minCagr"))}
        ${th("pf", "PF", t("crit.minPf"))}
        ${th("dd", esc(t("col.maxdd")), t("crit.maxDd"))}
        ${th("trades", esc(t("col.ops")), t("col.ops_help"))}
        ${th("months", esc(t("col.months_plus")), t("col.months_help"))}
        ${snap.split ? th("oos", t("col.oos"), t("col.oos_help")) : ""}
      </tr></thead>
      <tbody>${bank.map((r, i) => {
        const m = r.metrics;
        // la clave del genoma, para poder distinguir una fila nueva de una
        // que ya estaba: el indice no sirve, cambia al reordenarse el banco
        return `<tr class="clickable" data-row="${i}" data-key="${esc(r.id || "")}">
          <td class="rank-cell"><span class="rank">${String(i + 1).padStart(2, "0")}</span></td>
          <td><span class="strat-name">${esc(r.name)}</span>${sesionTag(r)}</td>
          <td class="spark-cell">${Charts.sparkSvg(r.spark)}</td>
          <td class="num">${scoreCell(r.score)}</td>
          <td class="num ${m.cagr_pct >= 0 ? "pos" : "neg"}"><b>${fmtPct(m.cagr_pct)}</b></td>
          <td class="num">${fmtNum(m.profit_factor)}</td>
          <td class="num ${nivelDD(m.max_drawdown_pct, riesgoActual())}">${
            fmtNum(m.max_drawdown_pct, 1)}%</td>
          <td class="num">${fmtInt(m.trades)}</td>
          <td class="num">${fmtNum(m.months_positive_pct ?? 0, 0)}%</td>
          ${snap.split ? `<td class="num">${oosCell(r)}</td>` : ""}
        </tr>`;
      }).join("")}</tbody></table></div>`
      : !finished ? buscandoHtml(snap)
      : `<div class="empty-state">
           <div class="big">${icono("diana", "ico-xl")}</div>
           <b>${esc(t("empty.none_passed", { n: fmtInt(snap.tested) }))}</b>
           ${textoDiagnostico(snap.diagnosis)
             ? `<p class="mt">${textoDiagnostico(snap.diagnosis)}</p>` : ""}
           ${sugerenciaRiesgo(snap.diagnosis?.suggestion)}
           ${botonArreglo(snap.diagnosis, snap)}
           <p class="mt muted">${esc(t("empty.also"))}</p>
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
    /* LA ACCIÓN NO SE PIERDE DE VISTA. El botón quedaba a 1.400 px del tope y
     el panel lo redibujaba: la usuaria de prueba tardó minuto y medio en
     encontrar lo que acababa de buscar. Cuando la búsqueda terminó y hay
     algo, la acción también vive en una barra fija abajo. */
  const barraFin = $("#barra-fin");
  if (barraFin) {
    const hay = finished && snap.corrida_id && bank.length;
    barraFin.hidden = !hay;
    if (hay && !barraFin.dataset.n) {
      barraFin.dataset.n = String(bank.length);
      barraFin.innerHTML = `<span>${esc(t("run.listo", { n: bank.length }))}</span>
        <button class="btn" id="fin-a-probar">${icono("marcador")} ${esc(t("bank.guardar_todas", { n: bank.length }))}</button>`;
      $("#fin-a-probar", barraFin).onclick = () => { const b = $("#guardar-todas", bankBox); if (b) b.click(); };
    }
  }
  const todasAlBanco = $("#guardar-todas", bankBox);
    if (todasAlBanco) todasAlBanco.onclick = async () => {
      todasAlBanco.disabled = true;
      try {
        const filas = await api.get("/api/banco?" + new URLSearchParams({ corrida: snap.corrida_id, limite: "200" }));
        const r = await api.post("/api/banco/guardar", { ids: filas.map(f => f.banco_id) });
        (r.guardadas || []).forEach(g => RECIEN_GUARDADAS.add(g.id));
        toast(t("bank.guardadas_n", { n: (r.guardadas || []).length }), "ok");
        await refreshSavedCount();
        encolarPruebas((r.guardadas || []).map(g => g.id));
        const bf = $("#barra-fin"); if (bf) { bf.hidden = true; delete bf.dataset.n; }
        todasAlBanco.replaceWith(Object.assign(document.createElement("span"),
          { className: "insp-guardada recien", innerHTML: `${icono("tilde", "ico-sm")} ${esc(t("bank.guardadas_n", { n: (r.guardadas || []).length }))}` }));
      } catch (e) {
       toast(e.message, "err"); todasAlBanco.disabled = false; }
    };

    const nuevo = $(".databank-wrap", bankBox);
    if (nuevo && (x || y)) { nuevo.scrollLeft = x; nuevo.scrollTop = y; }

    // con el contexto de ESTA corrida: sin el no salian las tres vistas de la
    // curva, que es lo que se acaba de pedir al reservar un tramo de validacion
    $$("[data-row]", bankBox).forEach(tr =>
      tr.onclick = () => openInspector(bank[+tr.dataset.row], ctxDeLaCorrida(snap)));

    cablearOrden(bankBox);

    /* Las estrategias que llegaron en esta vuelta entran con un desliz.

       Va aca y no antes: la tabla se pinta unas lineas mas arriba, y correrlo
       antes marcaba las filas de la vuelta ANTERIOR — una animacion que
       llegaba tarde y sobre la estrategia equivocada.

       No es decoracion. Durante una busqueda larga la tabla se redibuja cada
       pocos segundos y una fila nueva aparecia sin mas, indistinguible de las
       que ya estaban. El desliz contesta lo unico que uno mira mientras espera
       — ¿encontro algo? — sin tener que acordarse de lo que habia hace
       tres segundos. */
    if (!finished) {
      const primera = !S.vistasBanco;
      S.vistasBanco = S.vistasBanco || new Set();
      $$("tr[data-key]", bankBox).forEach(fila => {
        const k = fila.dataset.key;
        if (!k || S.vistasBanco.has(k)) return;
        S.vistasBanco.add(k);
        // en la primera pintada ya hay filas: marcarlas todas seria una
        // cascada sin sentido
        if (primera) return;
        fila.classList.add("llegando");
        setTimeout(() => fila.classList.remove("llegando"), 700);
      });
    }
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
    t("sug.risk_again", { pct: +applyRisk.dataset.needed }));

  const applyTarget = $("#apply-target", bankBox);
  if (applyTarget) applyTarget.onclick = () => {
    const sug = snap.diagnosis.suggestion;
    aplicarSugerencia(() => {
      S.cfg.minCagr = +applyTarget.dataset.target;
      S.cfg.critOn.minCagr = true;
      S.cfg.riskPct = Math.round(sug.current * 4 * 10) / 10;
    }, t("sug.target_again", { pct: +applyTarget.dataset.target }));
  };
}

/* El contexto de la corrida que se acaba de terminar.

   Los resultados recien minados abrian el inspector sin contexto, y entonces
   se caia al respaldo: leer la pantalla. Funcionaba de casualidad —la
   pantalla todavia tiene la configuracion con la que se mino— pero no traia
   el corte in/out, asi que las tres vistas de la curva no aparecian justo
   donde el usuario acababa de pedir la validacion. */
function ctxDeLaCorrida(snap) {
  const cfg = S.cfg;
  const r = (snap && snap.measured_range) || null;
  return {
    dataset_id: S.sel.dataset_id, timeframe: S.sel.timeframe || "1h",
    date_from: r ? r.from : undefined,
    date_to: r ? r.to : undefined,
    split: (snap && snap.split) || null,
    /* De dónde sale, con las mismas palabras que usa el Databank. Sin esto la
       ficha de una estrategia recién minada no decía sobre qué mercado ni con
       qué riesgo se midió — justo la que ve todo usuario nuevo. */
    etiqueta: t("bank.from_run", {
      corrida: `${nombreCorto((S.datasets.find(d => d.id === S.sel.dataset_id) || {}).name)} · ${S.sel.timeframe || "1h"}`,
      riesgo: cfg.sizing === "lots" ? `${cfg.lots} ${t("mine.lots")}` : `${cfg.riskPct}%`,
    }),
    settings: { spread: cfg.spread, slippage: cfg.slippage,
                commission_pct: cfg.commission, swap_anual: cfg.swap, initial_capital: cfg.capital },
    // con que datos guardarla si el usuario aprieta Guardar desde la ficha
    guardar: {
      dataset_id: S.sel.dataset_id,
      dataset_name: (S.datasets.find(d => d.id === S.sel.dataset_id) || {}).name || "",
      timeframe: S.sel.timeframe || "1h", direction: cfg.direction,
      spread: cfg.spread, slippage: cfg.slippage,
      commission: cfg.commission, swap: cfg.swap, capital: cfg.capital,
      sizing: cfg.sizing, riskPct: cfg.riskPct, lots: cfg.lots, rr: cfg.rr,
      measured_range: r, split: (snap && snap.split) || null,
    },
  };
}

/* Lo que hay que saber antes de llevarlo a MetaTrader.

   Tres cosas, y las tres salieron de correr el EA de verdad en el tester y
   comparar: el nombre del simbolo cambia de broker en broker, el historico del
   broker no es el mismo dato, y por eso conviene correr el tester antes de
   operar. Ninguna se sabia mirando el codigo. */
function avisoExportacion(ctx) {
  const dsId = (ctx && (ctx.dataset_id || (ctx.guardar || {}).dataset_id))
    || S.sel.dataset_id;
  const ds = S.datasets.find(d => d.id === dsId);
  const alias = (ds && ds.aliases) || [];
  // solo si hay mas de un nombre posible: en EURUSD la linea sobraria
  const otros = alias.slice(1);
  return `<section class="listo-mt5">
    <h3>${icono("info", "ico-sm")} ${esc(t("mt5.title"))}</h3>
    <ul>
      ${otros.length ? `<li>${t("mt5.symbol", {
        nuestro: `<b>${esc(alias[0])}</b>`,
        otros: otros.map(a => `<b>${esc(a)}</b>`).join(", ") })}</li>` : ""}
      <li>${t("mt5.feed")}</li>
      <li>${t("mt5.test_first")}</li>
    </ul>
    <h3 class="mt">${icono("seguir", "ico-sm")} ${esc(t("mt5.pasos_t"))}</h3>
    <ol class="mt5-pasos">
      <li>${esc(t("mt5.paso1"))}</li>
      <li>${esc(t("mt5.paso2"))}</li>
      <li>${esc(t("mt5.paso3"))}</li>
      <li>${esc(t("mt5.paso4"))}</li>
    </ol>
  </section>`;
}

function panelNota(ctx) {
  if (!ctx || !ctx.strategy_id) return "";
  return `<section id="insp-nota">
    <h3>${esc(t("note.title"))}</h3>
    <textarea id="nota-txt" class="nota-campo" rows="3"
      placeholder="${esc(t("note.placeholder"))}">${esc(ctx.notes || "")}</textarea>
    <div class="nota-pie">
      <button class="btn ghost small" id="nota-guardar">${esc(t("note.save"))}</button>
      <span class="nota-estado" id="nota-estado"></span>
    </div>
  </section>`;
}

/* Las tres vistas de la curva, cuando la corrida reservo un tramo.

   No se calcula nada nuevo: el inspector ya sabe re-correr un backtest sobre
   un rango, y la corrida ya guardo las fechas del corte. Lo unico que faltaba
   era ofrecerlo. */
function cablearMuestras(box, row, ctx, mostrarResultado) {
  const host = $("#insp-muestras", box);
  if (!host) return;
  const sp = ctx && ctx.split;
  if (!sp || !sp.oos_from) { host.hidden = true; return; }
  host.hidden = false;

  const VISTAS = [
    { id: "is",    desde: sp.is_from,  hasta: sp.is_to },
    { id: "oos",   desde: sp.oos_from, hasta: sp.oos_to },
    { id: "todo",  desde: sp.is_from,  hasta: sp.oos_to },
  ];
  /* Abre en el período completo.

     Abría en "donde buscó" por una razón que ya no existe: el bloque de
     métricas de arriba estaba clavado en el tramo de adentro, así que abrir
     en "las dos juntas" ponía 204 operaciones en el pie de la curva y 148 en
     las cifras, a diez centímetros una de otra. Ahora las cifras siguen a la
     pestaña, así que no hay nada que se contradiga.

     Sin esa restricción, lo natural es lo que hace cualquiera al abrir una
     estrategia: mirar primero cuánto dio en total, y recién después
     desglosar en qué parte lo dio. El desglose está a un clic y además ya
     está entero en la tabla de comparación de arriba. */
  const INICIAL = 2;
  host.innerHTML = `<div class="muestras" role="tablist">
      ${VISTAS.map((v, i) => `<button role="tab" data-m="${v.id}"
        class="${i === INICIAL ? "on" : ""}" aria-selected="${i === INICIAL}"
        title="${esc(t("ms." + v.id + "_help"))}">
        ${esc(t("ms." + v.id))}</button>`).join("")}
    </div>
    <div class="ms-comparar" id="ms-comparar">
      <span class="ms-cargando">${esc(t("ms.midiendo"))}</span>
    </div>`;

  /* Los tres tramos se piden JUNTOS y se guardan.

     Antes se pedía el de la pestaña abierta y nada más, así que comparar era
     hacer clic, memorizar cuatro números, hacer clic de nuevo y acordarse.
     Eso no es comparar: es tomar apuntes. Con los tres a la vista, "afuera
     rinde un tercio" se ve en vez de deducirse.

     No cuesta más de lo que costaba: pedir los tres es exactamente lo que
     pasaba en cuanto alguien tocaba las otras dos pestañas, que es lo que uno
     hace justamente cuando quiere comparar. Y ahora cambiar de pestaña no
     vuelve a pedir nada. */
  const medido = new Map();

  const traer = (v) => api.post("/api/backtest", {
    dataset_id: ctx.dataset_id, timeframe: ctx.timeframe,
    date_from: v.desde, date_to: v.hasta,
    spec: row.spec, settings: ctx.settings,
  }).then(r => ({ v, res: r.result })).catch(e => ({ v, err: e }));

  /* El tramo reservado puede quedar demasiado corto para volver a correrlo:
     con validación al 20% sobre un histórico diario son unos pocos cientos de
     velas, y los indicadores necesitan 500 para tener historia. No es un
     fallo, es una consecuencia de la configuración — así que se dice en esos
     términos y no con el error del servidor. */
  const esCorto = (e) => /velas|bars/i.test((e && e.message) || "");

  const pintarTabla = () => {
    const tabla = $("#ms-comparar", host);
    if (!tabla) return;
    const FILAS = [
      ["cagr_pct", rotuloMetrica("m.cagr"), "pct"],
      ["max_drawdown_pct", rotuloMetrica("m.dd"), "dd"],
      ["profit_factor", rotuloMetrica("m.pf"), "n"],
      ["trades", rotuloMetrica("m.trades"), "int"],
    ];
    const riesgo = riesgoDeCtx(ctx && ctx.guardar) ?? riesgoActual();
    const celda = (id, k, kind) => {
      const d = medido.get(id);
      if (!d) return `<td class="num muted">…</td>`;
      if (d.err) return `<td class="num muted" title="${esc(d.err.message || "")}">—</td>`;
      const val = d.res.metrics[k];
      if (val == null) return `<td class="num muted">—</td>`;
      if (kind === "pct") return `<td class="num ${val >= 0 ? "pos" : "neg"}">${fmtPct(val)}</td>`;
      if (kind === "dd") return `<td class="num ${nivelDD(val, riesgo)}">${fmtNum(val, 1)}%</td>`;
      if (kind === "int") return `<td class="num">${fmtInt(val)}</td>`;
      return `<td class="num">${fmtNum(val, 2)}</td>`;
    };
    tabla.innerHTML = `<table>
      <thead><tr><th></th>${VISTAS.map(v => `<th class="num">${esc(t("ms." + v.id))}</th>`).join("")}</tr>
        <tr class="ms-rango"><td></td>${VISTAS.map(v =>
          `<td class="num">${esc(String(v.desde).slice(0, 10))} → ${esc(String(v.hasta).slice(0, 10))}</td>`).join("")}</tr>
      </thead>
      <tbody>${FILAS.map(([k, lab, kind]) => `<tr>
        <th scope="row">${lab}</th>
        ${VISTAS.map(v => celda(v.id, k, kind)).join("")}
      </tr>`).join("")}</tbody></table>
      ${[...medido.values()].some(d => d.err && esCorto(d.err))
        ? `<p class="ms-corto">${icono("info","ico-sm")} ${esc(t("ms.muy_corto"))}</p>` : ""}`;
  };

  const pintar = (id) => {
    const v = VISTAS.find(x => x.id === id);
    $$("[data-m]", host).forEach(b => {
      const on = b.dataset.m === id;
      b.classList.toggle("on", on); b.setAttribute("aria-selected", String(on));
    });
    const lienzo = $("#insp-eq", box);
    const d = medido.get(id);
    if (!d) return;                       // todavía no llegó; lo pinta al llegar
    if (d.err) {
      $("#ms-pie", box).innerHTML = esCorto(d.err)
        ? `<span class="ms-corto">${icono("info","ico-sm")} ${esc(t("ms.muy_corto"))}</span>`
        : esc(d.err.message);
      // sin datos nuevos, el gráfico anterior seguiría en pantalla como si
      // fuera el de esta vista
      lienzo.innerHTML = `<div class="empty-state">${esc(t("ms.sin_curva"))}</div>`;
      return;
    }
    /* Repinta la ficha ENTERA, no sólo la curva: cifras, mapa mensual y
       operaciones son de este período igual que la curva. Mientras esto
       dibujaba nada más el gráfico, la pestaña "out of sample" convivía con
       las cifras de in sample justo arriba. */
    mostrarResultado(d.res);
    /* La marca del corte sólo tiene sentido en la vista completa, así que se
       vuelve a dibujar la curva con ella encima de la que ya puso el
       repintado general. */
    if (id === "todo") {
      Charts.equity(lienzo, {
        values: d.res.equity,
        labels: d.res.timestamps.map(x => String(x).slice(0, 10)),
        initial: d.res.equity[0], height: 320,
        marca: String(sp.oos_from).slice(0, 10),
        marcaTexto: t("ms.marca"),
      });
    }
    // el rótulo de las métricas dice de qué tramo son las que se están viendo
    const rot = $("#insp-h3-metricas", box);
    if (rot) {
      rot.innerHTML = `${esc(t("insp.metrics"))} <span class="h3-nota">— ${
        esc(t("ms." + id))}</span>`;
    }
    $("#ms-pie", box).innerHTML = t("ms.periodo", {
      desde: esc(String(v.desde).slice(0, 10)), hasta: esc(String(v.hasta).slice(0, 10)),
    }) + (id === "todo" ? " " + t("ms.corte") : "");
  };

  $$("[data-m]", host).forEach(b => b.onclick = () => pintar(b.dataset.m));

  (async () => {
    const lienzo = $("#insp-eq", box);
    if (lienzo) lienzo.style.opacity = ".45";
    const salidas = await Promise.all(VISTAS.map(traer));
    // el inspector puede haberse cerrado mientras tanto
    if (!host.isConnected) return;
    salidas.forEach(s => medido.set(s.v.id, s));
    pintarTabla();
    // la misma vista que quedo marcada arriba, o el marcado y la curva
    // arrancarian discrepando
    pintar(VISTAS[INICIAL].id);
    if (lienzo) lienzo.style.opacity = "1";
  })();
}

function cablearNota(box, ctx) {
  const btn = $("#nota-guardar", box);
  if (!btn || !ctx || !ctx.strategy_id) return;
  const campo = $("#nota-txt", box);
  const estado = $("#nota-estado", box);
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      const r = await api.post(`/api/strategies/${ctx.strategy_id}/nota`,
                               { notes: campo.value });
      // el contexto se actualiza para que reabrir el inspector sin recargar
      // la lista no muestre la nota vieja
      ctx.notes = r.notes;
      estado.textContent = t("note.saved");
      toast(t("note.saved"), "ok");
    } catch (e) {
       toast(e.message, "err"); }
    btn.disabled = false;
  };
}

/* ==================================================== EL VEREDICTO ARRIBA ===
   Lo primero que se lee dentro de una estrategia, antes que cualquier número.

   "Aguantó fuera de muestra en 3 de 4 tramos" se entiende sin saber qué es un
   tramo. "Eficiencia 0.62" no se entiende sin que te lo expliquen, y era lo
   único que la pantalla anterior mostraba grande.

   Cuando todavía no se probó, este mismo lugar es la invitación a hacerlo: un
   botón y una frase de por qué conviene. Es lo que convierte una lista de
   estrategias en algo que tiene un siguiente paso. */
function panelPrueba(ctx, row) {
  if (!PRUEBAS) return "";
  if (!ctx || !ctx.strategy_id) return "";       // una fila del banco no se prueba
  const v = ctx.validacion || {};
  if (!v.estado) {
    return `<section class="prueba-invita">
      <div>
        <h3>${esc(t("wf.untested"))}</h3>
        <p class="help-note">${esc(t("wf.untested_sub"))}</p>
      </div>
      <button class="btn" id="insp-probar">${esc(t("wf.test_it"))}</button>
      ${explicacionHTML("prueba", PASOS_PRUEBA())}
    </section>`;
  }

  const ui = ESTADO_UI[v.estado] || ESTADO_UI.no_paso;
  const mc = v.mc;
  return `<section class="veredicto v-${ui.cls}">
    <div class="v-cabeza">
      <span class="v-ic">${icono(ui.ico, "ico-lg")}</span>
      <div>
        <b>${esc(t("est." + v.estado))}</b>
        <p>${esc(fraseVeredicto(v))}</p>
      </div>
      <button class="btn ghost small" id="insp-probar">${esc(t("wf.retest"))}</button>
    </div>

    <div class="v-datos">
      <div class="metric"><span>${esc(t("wf.m_efficiency"))}
          <em title="${esc(t("wf.m_efficiency_help"))}">?</em></span>
        <b>${fmtNum(v.eficiencia, 2)}</b></div>
      <div class="metric"><span>${esc(t("wf.m_consistency"))}</span>
        <b>${v.tramos_ganadores}/${v.tramos}</b></div>
      ${/* DOS "FUERA DE MUESTRA" QUE NO ERAN EL MISMO. El banco muestra el
            tramo que la búsqueda se guardó (0,94× sobre 2024-07 → 2026-08) y
            acá salía el de la prueba de robustez (+21,43% sobre 2021-06 →
            2024-07). Los dos se llamaban igual y medían ventanas distintas,
            así que ninguno de los dos se podía creer (3 de septiembre). */ ""}
      <div class="metric"><span>${esc(t("wf.m_oos_return"))}
          <em title="${esc(t("wf.m_oos_return_help"))}">?</em></span>
        <b class="${(v.retorno_fuera_pct ?? 0) >= 0 ? "pos" : "neg"}">${
          fmtPct(v.retorno_fuera_pct)}</b></div>
      ${(() => {
        const q = (row || {}).oos_ratio;
        if (q == null) return "";
        /* Y SOBRE QUÉ DÍAS. Se mostraba el número sin ventana en ningún
           lado —105 de 121 estrategias— justo al lado del otro "fuera de
           muestra", que cubre otro período (3 de septiembre de 2026). */
        const sp = ctx.split || {};
        const cuando = sp.oos_from
          ? " " + t("wf.tramo_ventana", { desde: sp.oos_from, hasta: sp.oos_to })
          : "";
        return `<div class="metric"><span>${esc(t("wf.m_tramo_guardado"))}
          <em title="${esc(t("col.oos_help") + cuando)}">?</em></span>
        <b class="${q >= 0.8 ? "pos" : q >= 0.5 ? "" : "neg"}">${fmtNum(q, 2)}×</b>
        ${sp.oos_from ? `<small class="muted">${esc(sp.oos_from)} → ${esc(sp.oos_to)}</small>` : ""}</div>`;
      })()}
      ${mc ? `<div class="metric"><span>${esc(t("wf.m_bad_run"))}
          <em title="${esc(t("wf.m_bad_run_help"))}">?</em></span>
        <b class="${nivelDD(mc.dd_malo_pct, riesgoActual())}">${
          fmtNum(mc.dd_malo_pct, 1)}%</b></div>` : ""}
    </div>

    ${dibujosPrueba(v)}
    ${explicacionHTML("prueba", PASOS_PRUEBA())}

    ${/* QUÉ MIDE ESTA PRUEBA, dicho al lado del número. Tres estrategias con
          parámetros distintos daban tramos idénticos y el mismo +21,43%: es
          lo que corresponde —la prueba reoptimiza en cada tramo—, pero la
          ficha lo mostraba como el resultado de ESA estrategia, pegado a un
          retorno anual que sí es de sus parámetros (3 de septiembre). */ ""}
    <p class="help-note nota-que-mide">${esc(t("wf.que_mide"))}</p>
    <p class="v-pie">${t("wf.tested_on", {
      desde: esc(v.periodo?.from || "—"), hasta: esc(v.periodo?.to || "—"),
      cuando: esc(String(v.probada || "").slice(0, 10)) })}</p>
    ${mc && mc.ruina_pct > 10 ? `<div class="banner warn">
      <span class="b-ic">${icono("alerta")}</span>
      <div>${t("wf.ruin_warn", { pct: fmtNum(mc.ruina_pct, 1) })}</div></div>` : ""}
  </section>`;
}

/* LA PRUEBA, DIBUJADA. Tres números y una frase no alcanzaban: "cuatro
   tramos" no se entiende sin verlos. Con el detalle guardado se muestran
   los tramos (gris donde se reajustó, color donde se la juzgó sin haberla
   visto), la curva cosida de esos tramos de juicio y el abanico de Monte
   Carlo. Las guardadas antes de esto no tienen detalle y muestran lo de
   siempre hasta que se las vuelva a probar. */
function dibujosPrueba(v) {
  const d = v && v.detalle;
  if (!d || !(d.tramos || []).length) return "";
  const tramos = d.tramos.map(tr => {
    const gana = tr.afuera_pct > 0;
    return `<div class="tramo ${gana ? "gana" : "pierde"}"
      title="${esc(t("wf.tramo_tip", { adentro: fmtPct(tr.adentro_pct), afuera: fmtPct(tr.afuera_pct),
                                       ops: fmtInt(tr.operaciones), caida: fmtNum(tr.caida_pct, 1) }))}">
      <span class="tramo-n">${esc(t("wf.tramo", { n: tr.n }))}</span>
      <div class="tramo-bar"><i class="tr-in"></i><i class="tr-out"></i></div>
      <small><span>${esc(tr.juzga[0])} → ${esc(tr.juzga[1])}</span>
        <b>${fmtPct(tr.afuera_pct)}</b></small>
    </div>`;
  }).join("");
  return `<div class="v-dibujos">
    <div>
      <h4>${esc(t("wf.d_tramos"))} <em class="ayuda" title="${esc(t("wf.d_tramos_help"))}">?</em></h4>
      <div class="tramos">${tramos}</div>
    </div>
    <div class="v-graficos">
      ${d.afuera && (d.afuera.curva || []).length > 1 ? `<div>
        <h4>${esc(t("wf.d_afuera"))} <em class="ayuda" title="${esc(t("wf.d_afuera_help"))}">?</em></h4>
        <div class="chart-box" id="v-afuera"></div></div>` : ""}
      ${d.mc ? `<div>
        <h4>${esc(t("wf.d_mc"))} <em class="ayuda" title="${esc(t("wf.d_mc_help"))}">?</em></h4>
        <div class="chart-box" id="v-mc"></div></div>` : ""}
    </div>
  </div>`;
}

function dibujarPrueba(box, v) {
  const d = v && v.detalle;
  if (!d) return;
  const a = $("#v-afuera", box);
  if (a && d.afuera) {
    Charts.line(a, { height: 200, baseline: d.afuera.curva[0], labels: d.afuera.fechas,
                     series: [{ values: d.afuera.curva, fill: true }] });
  }
  const m = $("#v-mc", box);
  if (m && d.mc) Charts.fan(m, d.mc.bandas, d.mc.capital);
}

/* Abre la ficha de una estrategia: el backtest se recalcula entero en el
   momento, no se guarda. La fila del databank trae metricas resumidas; aca
   hacen falta la curva, el mes a mes y las operaciones. */
/* Las salidas de la estrategia, dichas como se dicen.

   La cabecera mostraba el genoma tal cual sale del minero:

       RSI reversal \u00b7 level=45,period=23 \u00b7 SL=3\u00d7ATR \u00b7 trail=1.5\u00d7ATR \u00b7 m\u00e1x 12 velas

   Eso es la notacion interna de la busqueda. En la primera linea de la ficha,
   para alguien que abrio la aplicacion esta semana, no dice nada \u2014 y es lo
   primero que ve cada vez que entra a una estrategia.

   Los valores crudos no se pierden: siguen enteros en "Reglas de la
   estrategia", que es la seccion donde alguien los va a buscar a proposito. */
function salidasEnCastellano(row) {
  const p = [];
  // del spec y no de la fila: una guardada no arrastra stop_mult ni max_bars
  // en su meta, pero su risk siempre está — es lo que se va a exportar
  const rk = (row.spec && row.spec.risk) || {};
  const stop = row.stop_mult != null ? row.stop_mult
    : (rk.stop_type === "atr" ? rk.stop_value : null);
  const trail = row.trail_mult || rk.trail_atr || 0;
  const velas = row.max_bars || rk.max_bars_in_trade || 0;
  if (stop != null) p.push(t("sal.stop", { n: fmtNum(stop, 2) }));
  if (rk.reward_ratio) p.push(t("sal.rr", { n: fmtNum(rk.reward_ratio, 2) }));
  if (trail) p.push(t("sal.trail", { n: fmtNum(trail, 2) }));
  if (velas) p.push(t("sal.max_bars", { n: fmtInt(velas) }));
  if (row.session && row.session !== "todo") {
    const h = row.session_hours;
    p.push(idioma() === "en" && row.session_label_en
      ? row.session_label_en + (h ? ` (${h})` : "")
      : (row.session_label || "") + (h ? ` (${h})` : ""));
  }
  return p.length ? esc(p.join(" \u00b7 ")) : esc(t("sal.ninguna"));
}

async function openInspector(row, ctx) {
  if (!row) return;
  const host = document.createElement("div");
  host.className = "overlay";
  host.innerHTML = `<div class="sheet">
    <div class="sheet-head">
      <!-- La pastilla dice DE DÓNDE sale la estrategia. Decía "fitness
           22.350" cuando se abría una recién minada: el número con el que el
           minero la ordenó internamente, que no significa nada para quien lo
           lee y encima ocupaba el lugar del dato que sí sirve. -->
      <div><h2>${esc(row.name)} ${ctx && ctx.etiqueta
        ? `<span class="badge">${esc(ctx.etiqueta)}</span>`
        : ctx && ctx.strategy_id
          ? `<span class="badge">${esc(t("nav.saved"))}</span>`
          : ""}</h2>
        <p>${esc(row.blocks || "")}</p>
        <p class="sh-salidas">${salidasEnCastellano(row)}</p></div>
      <button class="sheet-close" aria-label="${esc(t("ui.close"))}">${icono("cerrar")}</button>
    </div>
    <div id="insp-body"><div class="esqueleto" aria-busy="true" aria-label="${esc(t("insp.recalculating"))}">
      <i class="esq esq-ancha"></i><i class="esq esq-linea"></i>
      <div class="esq-fila"><i class="esq esq-caja"></i><i class="esq esq-caja"></i><i class="esq esq-caja"></i><i class="esq esq-caja"></i></div>
      <i class="esq esq-grafico"></i></div></div>
  </div>`;
  document.body.appendChild(host);
  const close = () => host.remove();
  $(".sheet-close", host).onclick = close;
  host.onclick = (e) => { if (e.target === host) close(); };
  cerrarConEscape(host, close);

  try {
    const cfg = S.cfg;
    // sin bloque risk: el spec ya trae el stop que el minero encontro para
    // ESTA estrategia — mandar el generico daria metricas distintas a las
    // que muestra el databank
    const { result } = ctx ? await api.post("/api/backtest", {
      dataset_id: ctx.dataset_id, timeframe: ctx.timeframe,
      // el mismo tramo que se midio al guardarla; sin esto corria sobre toda
      // la historia y devolvia otra estrategia con el mismo nombre
      ...(ctx.date_from ? { date_from: ctx.date_from, date_to: ctx.date_to } : {}),
      spec: row.spec, settings: ctx.settings,
    }) : await api.post("/api/backtest", {
      dataset_id: S.sel.dataset_id, timeframe: S.sel.timeframe || "1h",
      // el mismo tramo que se mino: si no, la curva del inspector no
      // coincidiria con la fila del databank que se acaba de clickear
      ...rangePayload(),
      spec: row.spec,
      settings: {
        spread: cfg.spread, slippage: cfg.slippage,
        commission_pct: cfg.commission, swap_anual: cfg.swap, initial_capital: cfg.capital,
      },
    });
    renderInspector($("#insp-body", host), row, result, ctx);
  } catch (e) {
    $("#insp-body", host).innerHTML =
      `<div class="empty-state neg">${esc(t("insp.failed"))}: ${esc(e.message)}</div>`;
  }
}

/* Las metricas de la ficha, en el orden en que se miran: primero cuanto
   rindio, despues a costa de que, y al final el detalle de las operaciones.
   Es una funcion y no una constante porque los rotulos salen del diccionario,
   que cambia al cambiar de idioma. */
/* Las cuatro que deciden.

   No son un gusto: son exactamente las mismas contra las que se pone la vara
   al minar —operaciones mínimas, profit factor, rendimiento anual, caída
   máxima—. O sea que el usuario ya eligió que son las importantes cuando
   configuró la búsqueda; la ficha no hace más que respetarlo.

   El resto son doce datos de consulta. Se leen cuando se los busca, no de un
   vistazo, y por eso van como lista y no como fichas: doce cajas con borde
   para eso era media pantalla gastada en dibujar bordes. */
const INSPECT_CABEZA = ["cagr_pct", "max_drawdown_pct", "profit_factor", "trades"];

/* Las seis de siempre llevan su "?" con la referencia de qué es normal: eran
   las que una usuaria de prueba miró sin saber si un +7,59% anual era mucho o
   poco (3 de septiembre de 2026). */
const INSPECT_METRICS = () => [
  ["cagr_pct", rotuloMetrica("m.cagr"), "pct"],
  ["net_profit_pct", t("m.net"), "pct"],
  ["exposure_pct", t("m.exposure"), "raw"],
  ["cagr_exposed_pct", t("m.cagr_exposed"), "raw"],
  ["months_positive_pct", t("m.months_positive"), "raw"],
  ["profit_factor", rotuloMetrica("m.pf"), "n"],
  ["sharpe", rotuloMetrica("m.sharpe"), "n"],
  ["recovery_factor", t("m.retdd"), "n"],
  ["max_drawdown_pct", rotuloMetrica("m.dd"), "dd"],
  ["win_rate_pct", rotuloMetrica("m.winrate"), "raw"],
  ["trades", rotuloMetrica("m.trades"), "int"],
  ["trades_per_month", t("m.trades_month"), "n"],
  ["avg_trade", t("m.avg_trade"), "money"],
  ["_win_loss", t("m.win_loss"), "win_loss"],
  ["expectancy_r", t("m.expectancy"), "n"],
  ["final_equity", t("m.final_equity"), "money"],
];

/* LAS SECUNDARIAS SE AGRUPAN POR PREGUNTA, no por orden de lista. En tres
   columnas rellenadas por filas, "ganancia promedio" cerraba una fila a la
   derecha y "pérdida promedio" abría la siguiente a la izquierda: dos mitades
   del mismo dato en esquinas opuestas (2 de septiembre). Cada columna
   contesta una pregunta y las parejas van en la misma línea. */
const INSPECT_GRUPOS = () => [
  ["insp.g_rinde", ["net_profit_pct", "cagr_exposed_pct", "exposure_pct",
                    "months_positive_pct", "final_equity"]],
  ["insp.g_duele", ["sharpe", "recovery_factor"]],
  ["insp.g_opera", ["trades_per_month", "win_rate_pct", "avg_trade", "_win_loss",
                    "expectancy_r"]],
];

function renderInspector(box, row, res, ctx) {
  const m = res.metrics;
  /* Las guardadas antes de que se registrara el tramo no se pueden reproducir:
     el backtest corre sobre toda la historia y da otros números que los de la
     fila. Decirlo es lo único honesto — callarlo deja al usuario comparando
     dos cosas distintas sin saberlo. */
  const avisoRango = ctx && ctx.sinRango ? `
    <div class="banner warn" style="margin-bottom:16px"><span class="b-ic">${icono("alerta")}</span><div>
      ${t("insp.no_range")}</div></div>` : "";
  const riesgoInsp = riesgoDeCtx(ctx && ctx.guardar) ?? riesgoActual();
  /* Toma el resultado como argumento en vez de leer el de apertura.

     Antes cerraba sobre `m`, las métricas del tramo donde buscó, así que la
     ficha no tenía forma de mostrar otro período aunque lo tuviera medido. */
  const pintarMetrica = (m) => ([k, label, kind]) => {
    const v = m[k];
    let txt = fmtNum(v), cls = "";
    if (kind === "pct") { txt = fmtPct(v); cls = v >= 0 ? "pos" : "neg"; }
    else if (kind === "dd") { txt = `${fmtNum(v, 1)}%`; cls = nivelDD(v, riesgoInsp); }
    else if (kind === "raw") txt = `${fmtNum(v, 1)}%`;
    else if (kind === "int") txt = (+v).toLocaleString(localeNum());
    else if (kind === "money") { txt = fmtMoney(v); cls = v >= 0 ? "pos" : ""; }
    else if (kind === "loss") { txt = `-${fmtMoney(Math.abs(v))}`; cls = "neg"; }
    // la cifra cruda y su formato, para que las grandes cuenten al aparecer
    const formato = { pct: "pct", dd: "dd", n: "n", int: "int" }[kind];
    if (formato && isFinite(+v)) return { label, txt, cls, cifra: +v, formato };
    else if (kind === "win_loss") {
      /* Las dos mitades juntas, y la relación entre ellas, que es lo que
         uno quiere saber: cuánto gana cada acierto contra cuánto cuesta cada
         error. */
      const g = +m.avg_win || 0, p = Math.abs(+m.avg_loss || 0);
      const razon = p > 1e-9 ? `${fmtNum(g / p, 1)} : 1` : "";
      txt = `<span class="pos">${fmtMoney(g)}</span> · <span class="neg">-${fmtMoney(p)}</span>${
        razon ? ` · <span class="muted">${razon}</span>` : ""}`;
      cls = "par";
    }
    return { label, txt, cls };
  };

  const todas = INSPECT_METRICS();
  /* El orden de arriba lo fija INSPECT_CABEZA y no el orden en que aparecen
     en la lista larga: los cuatro tienen que salir siempre en la misma
     posición, porque se los busca por dónde están. */
  const fichaMetricas = (mm) => {
    const cabeza = INSPECT_CABEZA
      .map(k => todas.find(([kk]) => kk === k)).filter(Boolean)
      .map(pintarMetrica(mm))
      .map(d => `<div class="m-grande"><span>${d.label}</span><b class="${d.cls}" ${d.cifra != null ? `data-cifra="${d.cifra}" data-formato="${d.formato}"` : ""}>${d.txt}</b></div>`)
      .join("");
    const fila = (d) => `<div class="m-fila"><span>${d.label}</span><b class="${d.cls}">${d.txt}</b></div>`;
    const grupos = INSPECT_GRUPOS().map(([clave, keys]) => `
      <div class="m-grupo"><b class="m-tit">${esc(t(clave))}</b>${
        keys.map(k => todas.find(([kk]) => kk === k)).filter(Boolean)
          .map(pintarMetrica(mm)).map(fila).join("")}</div>`).join("");
    return `<div class="m-cabeza">${cabeza}</div><div class="m-resto">${grupos}</div>`;
  };

  const rules = (list, side) => (list || []).length
    ? `<div><b style="font-size:12px">${side}:</b> ` +
      list.map(c => `<span class="rule-pill">${esc(condLabel(c))}</span>`).join("") + `</div>`
    : "";

  /* La tabla de operaciones también depende del período elegido: dejarla
     fija mostraría las 545 del tramo de búsqueda debajo de un encabezado que
     dice "out of sample", donde hubo 241. */
  const tablaTrades = (r) => {
    const ops = (r.trades || []).slice(-120).reverse();
    if (!ops.length) return `<p class="help-note">${esc(t("insp.no_trades"))}</p>`;
    return `<div class="table-scroll"><table>
      <thead><tr><th>${esc(t("tr.in"))}</th><th>${esc(t("tr.out"))}</th><th>${esc(t("tr.dir"))}</th>
        <th class="num">${esc(t("tr.price_in"))}</th><th class="num">${esc(t("tr.price_out"))}</th>
        <th class="num">${esc(t("tr.result"))}</th><th class="num">%</th>
        <th class="num">${esc(t("tr.bars"))}</th><th>${esc(t("tr.reason"))}</th></tr></thead>
      <tbody>${ops.map(t => `<tr>
        <td class="muted">${esc(t.entry_time.slice(0, 16))}</td>
        <td class="muted">${esc(t.exit_time.slice(0, 16))}</td>
        <td><span class="badge ${t.direction === "long" ? "green" : "red"}">${t.direction === "long" ? "L" : "S"}</span></td>
        <td class="num">${fmtNum(t.entry_price, 2)}</td>
        <td class="num">${fmtNum(t.exit_price, 2)}</td>
        <td class="num ${t.pnl >= 0 ? "pos" : "neg"}">${fmtMoney(t.pnl)}</td>
        <td class="num ${t.pnl_pct >= 0 ? "pos" : "neg"}">${fmtNum(t.pnl_pct, 2)}%</td>
        <td class="num">${t.bars}</td>
        <td class="muted">${esc(motivoSalida(t.exit_reason))}</td></tr>`).join("")}
      </tbody></table></div>`;
  };
  const rotuloTrades = (r) => {
    const ops = (r.trades || []).slice(-120);
    return esc(t("insp.last_n", { n: ops.length, total: (r.trades || []).length }));
  };
  const monthly = res.monthly_returns || [];

  /* El panel del score, que también es del tramo elegido.

     El inspector no muestra el score guardado de la corrida: muestra el que
     `/api/backtest` recalcula sobre el tramo que le pidió. O sea que con la
     pestaña en "out of sample" ese 84 seguía siendo de in sample. */
  const panelScore = (r) => `
    <div class="score-big">${scoreBadge(r.score, "huge")}</div>
    <div class="score-detail">
      ${scoreBars(r.score_parts)}
      <p class="help-note">${scoreVerdict(r)}</p>
    </div>`;

  /* El boton de BingX solo tiene sentido en un perpetuo: un exchange de
     cripto no opera el S&P ni el oro. Se deja VISIBLE pero apagado en los
     demas instrumentos en vez de esconderlo, porque esconderlo hace que nadie
     se entere de que existe — y enterarse es medio producto. */
  const dsBot = S.datasets.find(
    d => d.id === (ctx ? ctx.dataset_id : S.sel.dataset_id));
  const esCripto = (dsBot || {}).source === "binance";

  box.innerHTML = avisoRango + panelPrueba(ctx, row) + `
  <!-- Las tres vistas, sólo si la corrida reservó un tramo. Van ACÁ arriba de
       todo porque mandan sobre todo lo que sigue: el score, las cifras, la
       curva, el mapa mensual y las operaciones. Un control tiene que ir antes
       de lo que gobierna — mientras estuvo abajo, dentro de la sección de la
       curva, tocarlo cambiaba sólo el gráfico y dejaba las cifras del otro
       tramo: decía "out of sample" arriba de un +13,88% que era de in sample. -->
  <div id="insp-muestras" hidden></div>

  <section>
    <h3>${esc(t("m.score"))} <span class="h3-nota">— ${
      esc(t("insp.score_sub"))}</span></h3>
    <div class="score-panel" id="insp-score">${panelScore(res)}</div>
  </section>

  <section>
    <h3 id="insp-h3-metricas">${esc(t("insp.metrics"))}</h3>
    <div id="insp-metricas">${fichaMetricas(m)}</div>
  </section>

  <section>
    <h3>${esc(t("insp.equity"))}</h3>
    <div class="chart-box tall" id="insp-eq"></div>
    <!-- De qué fecha a qué fecha es la curva. Vive acá y no arriba con las
         pestañas: describe el gráfico, y arriba quedaba a media pantalla de
         distancia de lo que describía. -->
    <p class="ms-pie" id="ms-pie"></p>
  </section>

  ${monthly.length ? `<section id="insp-sec-mensual">
    <h3>${esc(t("insp.monthly"))}</h3>
    <div class="scroll-x" id="insp-monthly"></div>
  </section>` : ""}

  <section>
    <h3>${esc(t("insp.rules"))}</h3>
    ${rules(row.spec.entry_long, t("insp.long_entry"))}
    ${rules(row.spec.entry_short, t("insp.short_entry"))}
    <div class="stage-note">${esc(riskSummary(row.spec.risk))}</div>
  </section>

  <section>
    <h3>${esc(t("m.trades"))} <span class="h3-nota" id="insp-h3-trades">${
      rotuloTrades(res)}</span></h3>
    <div id="insp-trades">${tablaTrades(res)}</div>
  </section>


  ${panelNota(ctx)}

  ${avisoExportacion(ctx)}

  <p class="stage-note">${t("insp.export_note")}</p>

  <!-- El pie se pega abajo mientras se lee el resto: es la acción principal
       de la pantalla y estaba a dos pantallas y media de scroll. -->
  <div class="insp-pie">
    <div class="controls">
      <button class="btn ${esCripto ? "ghost" : ""}" id="insp-mql5">${icono("bajar")} MetaTrader 5 (.mq5)</button>
      <button class="btn ${esCripto ? "" : "ghost"}" id="insp-bingx" ${esCripto ? "" : "hidden"}
        title="${esc(esCripto ? t("insp.bingx_hint") : t("insp.bingx_solo_cripto"))}"
        >${icono("seguir")} ${esc(t("insp.bingx_btn"))}</button>
      <button class="btn ghost" id="insp-pine">${icono("bajar")} TradingView (.pine)</button>
      <button class="btn ghost" id="insp-copiar">${icono("copiar")} ${esc(t("insp.copy_pine"))}</button>
      <button class="btn ghost" id="insp-compartir">${icono("seguir")} ${esc(t("comp.btn"))}</button>
      ${/* YA GUARDADA NO SE VUELVE A GUARDAR. Abierta desde Mis estrategias,
            el botón ofrecía guardar lo que ya estaba guardado; el chip de la
            cabecera lo dice y el pie lo contradecía. */
        ctx && ctx.strategy_id
          ? `<span class="insp-guardada">${icono("tilde", "ico-sm")} ${esc(t("insp.ya_guardada"))}</span>`
          : `<button class="btn ghost" id="insp-save">${icono("marcador")} ${esc(t("insp.save"))}</button>`}
    </div>
    <div class="guardado" id="insp-guardado" hidden></div>
  </div>`;

  const btnProbar = $("#insp-probar", box);
  if (btnProbar) btnProbar.onclick = async () => {
    // se recarga la ficha entera al terminar: el veredicto es lo primero que
    // se lee, y dejarla abierta con el estado viejo sería mentir en pantalla
    await correrPrueba({ id: ctx.strategy_id, name: row.name }, btnProbar);
    box.closest(".overlay")?.remove();
  };

  /* Todo lo que depende del período, en una sola función.

     La usa la apertura y la usan las pestañas, así que no hay forma de que
     una dibuje algo distinto de la otra. Mientras fueron dos caminos, las
     pestañas repintaban la curva y se olvidaban de las cifras. */
  const mostrarResultado = (r) => {
    const cajaS = $("#insp-score", box);
    if (cajaS) cajaS.innerHTML = panelScore(r);
    const cajaM = $("#insp-metricas", box);
    if (cajaM) { cajaM.innerHTML = fichaMetricas(r.metrics); animarCifras(cajaM); }
    const cajaT = $("#insp-trades", box);
    if (cajaT) cajaT.innerHTML = tablaTrades(r);
    const rotT = $("#insp-h3-trades", box);
    if (rotT) rotT.innerHTML = rotuloTrades(r);
    const secM = $("#insp-sec-mensual", box);
    if (secM) {
      const meses = r.monthly_returns || [];
      secM.hidden = !meses.length;
      if (meses.length) Charts.monthlyGrid($("#insp-monthly", box), meses);
    }
    Charts.equity($("#insp-eq", box), {
      values: r.equity,
      labels: r.timestamps.map(x => String(x).slice(0, 10)),
      initial: r.equity[0], height: 320,
    });
  };

  mostrarResultado(res);
  dibujarPrueba(box, ctx && ctx.validacion);
  atarExplicacion(box, "prueba", PASOS_PRUEBA());
  $("#insp-compartir", box).onclick = () => abrirCompartir(row, ctx, res);
  cablearMuestras(box, row, ctx, mostrarResultado);

  cablearNota(box, ctx);

  // sin botón cuando ya está guardada: no hay nada que atar
  if ($("#insp-save", box)) $("#insp-save", box).onclick = async () => {
    const btn = $("#insp-save", box);
    btn.disabled = true;
    try {
      /* Se guarda con el contexto de la CORRIDA de la que salio la fila, no
         con lo que este en pantalla.

         Salia de `S.sel` y `S.cfg`. Mientras la unica forma de abrir una
         estrategia fuera la corrida recien terminada eso coincidia, pero
         desde el Databank se abre una fila de hace tres semanas sobre otro
         instrumento — y se guardaba como el instrumento de ahora, con los
         costos de ahora y el tramo de ahora. La tabla de Mis estrategias
         muestra justamente esos campos, asi que quedaba una fila que mentia
         sobre su propio origen y que al reabrirse daba otros numeros. */
      const g = (ctx && ctx.guardar) || null;
      const dsId = g ? g.dataset_id : S.sel.dataset_id;
      const ds = S.datasets.find(d => d.id === dsId);
      const guardada = await api.post("/api/strategies", {
        spec: row.spec, name: row.name,
        dataset_id: dsId,
        /* El campo de notas es del usuario. Antes salía de fábrica con
           "Minada el {fecha}" ya traducida, que se congelaba en el idioma de
           ese día y encima le pisaba el lugar a lo que quisiera escribir él.
           La fecha vive en `meta.saved_at` y se dibuja en el momento. */
        notes: "",
        meta: {
          dataset_name: ds ? ds.name : (g ? g.dataset_name : ""),
          timeframe: g ? g.timeframe : (S.sel.timeframe || "1h"),
          direction: g ? g.direction : S.cfg.direction,
          spread: g ? g.spread : S.cfg.spread,
          slippage: g ? g.slippage : S.cfg.slippage,
          commission: g ? g.commission : S.cfg.commission,
          swap: g ? g.swap : S.cfg.swap,
          capital: g ? g.capital : S.cfg.capital,
          sizing: g ? g.sizing : S.cfg.sizing,
          riskPct: g ? g.riskPct : S.cfg.riskPct,
          lots: g ? g.lots : S.cfg.lots,
          rr: g ? g.rr : S.cfg.rr,
          // el corte, para que al reabrirla desde Mis estrategias vuelvan a
          // aparecer las tres vistas de la curva
          split: g ? g.split : ((S.mineResult || S.mineLive || {}).split || null),
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
          measured_range: g ? g.measured_range
            : ((S.mineResult || S.mineLive || {}).measured_range || null),
          saved_at: new Date().toISOString(),
        },
      });
      toast(t("saved.added", { nombre: row.name }), "ok");
      if (guardada && guardada.id) RECIEN_GUARDADAS.add(guardada.id);
      await refreshSavedCount();
      if (guardada && guardada.id) encolarPruebas([guardada.id]);
      /* EL BOTÓN SE CONVIERTE EN "GUARDADA". Un aviso abajo a la derecha se
         va; el botón pintado se queda, y es lo que dice de un vistazo que
         esta estrategia ya está en Mis estrategias. */
      const chip = document.createElement("span");
      chip.className = "insp-guardada recien";
      chip.innerHTML = `${icono("tilde", "ico-sm")} ${esc(t("insp.ya_guardada"))}`;
      btn.replaceWith(chip);
      return;
    } catch (e) {
       toast(e.message, "err"); }
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
    // sin esto el robot sale con el offset en cero y, si la estrategia tiene
    // franja horaria, opera en el horario equivocado sin que nada falle
    server_utc_offset: S.cfg.brokerUtc,
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
        ? t("export.installed", { terminal: r.terminal })
        : aviso);
    } catch (e) {
       if (!pedirCuenta(e.status)) toast(e.message, "err"); }
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
          ? t("exp.in_terminal", { terminal: `<b>${esc(r.terminal)}</b>` })
            + (opciones ? ` · <a href="#" id="insp-cambiar">${esc(t("exp.change"))}</a>` : "")
          : esc(r.carpeta)}</span>
        ${opciones ? `<div class="g-destino" hidden>
          <span>${esc(t("export.pick_terminal", { n: S.mt5.terminales.length }))}</span>
          <select id="insp-destino">
            ${S.mt5.terminales.map(t => `<option value="${esc(t.id)}"
              ${t.id === S.mt5.elegido ? "selected" : ""}>${esc(t.nombre)}</option>`).join("")}
            <option value="" ${S.mt5.elegido ? "" : "selected"}>${esc(t("exp.downloads"))}</option>
          </select></div>` : ""}
      </div>
      <div class="g-acciones">
        <button class="btn small" id="insp-abrir-archivo">${
          esc(t(esRobot ? "exp.open_editor" : "exp.open_file"))}</button>
        <button class="linkbtn" id="insp-abrir">${esc(t("exp.open_folder"))}</button>
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
    "insp-mql5", "mql5", t("export.mq5_saved"));

  /* El boton de BingX abre la GUIA y no exporta un archivo.
     Exportaba un .bqbot que describe la estrategia para un programa que
     ejecute — y ese programa dejo de ser el camino: TradingView evalua en la
     nube y le avisa a BingX directo. Un boton que entrega un archivo que nada
     puede ejecutar es peor que no tener boton. El exportador sigue en el
     codigo y con sus pruebas, por si algun dia se quiere la opcion sin
     suscripcion a TradingView. */
  const btnBingx = $("#insp-bingx", box);
  if (btnBingx && esCripto) btnBingx.onclick = () => abrirGuiaBingx(
    row.name, dsBot ? dsBot.name.replace(/ M1.*/, "") : "");
  /* En cripto, exportar a TradingView ABRE LA GUIA ademas de guardar.
     El .pine no es el final del camino sino el principio: pegarlo en
     TradingView y no enterarse de que hace falta una alerta con webhook deja
     a la persona con un grafico lindo que no opera nada. El panel aparece
     justo cuando acaba de conseguir el archivo, que es el momento en que la
     pregunta "y ahora que hago con esto" existe de verdad. */
  $("#insp-pine", box).onclick = async () => {
    await exportAs("insp-pine", "pine", t("export.pine_saved"));
    if (esCripto) abrirGuiaBingx(row.name, dsBot ? dsBot.name.replace(/ M1.*/, "") : "");
  };

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
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Idioma": idioma() },
        body: JSON.stringify(cuerpoExport()),
      });
      if (!r.ok) {
        const detalle = await r.json().then(j => j.detail).catch(() => r.status);
        throw Object.assign(new Error(detalle), { status: r.status });
      }
      const codigo = await r.text();
      if (await copiar(codigo)) {
        toast(t("exp.pine_copied"), "ok");
      } else {
        const g = await api.post("/api/export/pine/archivo", cuerpoExport());
        mostrarGuardado(g, t("export.copy_failed"));
      }
    } catch (e) {
       if (!pedirCuenta(e.status)) toast(e.message, "err"); }
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
    consistencia: t("why.consistency", { sharpe: fmtNum(m.sharpe) }),
    recuperacion: t("why.recovery", { cagr: fmtNum(m.cagr_pct, 1), dd: fmtNum(m.max_drawdown_pct, 0) }),
    evidencia: t("why.evidence", { n: m.trades }),
    ventaja: t("why.edge", { r: fmtNum(m.expectancy_r) }),
    estabilidad: t("why.stability", { pct: fmtNum(m.months_positive_pct ?? 0, 0) }),
    reparto: t("why.spread", { pct: fmtNum(m.top_trade_share_pct ?? 0, 0) }),
  }[worst.key] || "";
  const tier = scoreTier(res.score || 0);
  // el nombre de la parte sale del diccionario, no del rótulo que manda el
  // servidor: si no, la frase queda "What drags its score down most is ventaja
  // por operación" — inglés con un pedazo en castellano en el medio
  return `<b>${tier.label}.</b> ${t("why.lowers", {
    parte: esc(t("score." + worst.key).toLowerCase()), motivo: why })}`;
}

/* descripción legible de las salidas de una estrategia */
function riskSummary(risk) {
  if (!risk) return "";
  if (risk.stop_type === "none") return t("risk.no_stop");
  const rr = risk.stop_value ? risk.target_value / risk.stop_value : 0;
  if (risk.stop_type === "atr") {
    return t("risk.atr", {
      pct: risk.size_value, mult: (+risk.stop_value).toFixed(2),
      atr: risk.atr_period, rr: rr.toFixed(2).replace(/\.?0+$/, ""),
    });
  }
  const unit = { points: t("risk.points"), percent: t("risk.pct_price"), money: "$" };
  const u = unit[risk.stop_type] || risk.stop_type;
  return `stop ${risk.stop_value} ${u} · target ${risk.target_value} ` +
         `${unit[risk.target_type] || risk.target_type}`;
}

/* etiqueta legible de una condición */
function condLabel(c) {
  const opLbl = { cross_above: t("rule.cross_above"), cross_below: t("rule.cross_below"),
                  rising: t("rule.rising"), falling: t("rule.falling"),
                  ">": ">", "<": "<" }[c.op] || c.op;
  const side = o => {
    if (!o) return "";
    if (o.type === "const") return (+o.value).toLocaleString(localeNum());
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
  if (btn) btn.title = light ? t("nav.theme_dark") : t("nav.theme_light");
  if (redraw) navigate(S.page);
  // Dos cuadros: uno para aplicar los colores nuevos, otro para devolver las
  // transiciones sin que el navegador las vea como un cambio animable.
  //
  // Con red de seguridad por tiempo: requestAnimationFrame NO corre mientras
  // la ventana está oculta, así que arrancar minimizado dejaba esta clase
  // pegada — y con ella toda la aplicación sin una sola transición, hasta
  // recargar. Se siente como que el programa está trabado y no hay nada en
  // pantalla que lo explique.
  const soltar = () => root.classList.remove("theme-switching");
  requestAnimationFrame(() => requestAnimationFrame(soltar));
  setTimeout(soltar, 260);
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

/* ═══════════════════════════════════════════════════ LA LICENCIA ══════
   En el escritorio no hay login: la identidad la da un archivo firmado que el
   usuario baja de su cuenta y trae a la maquina. Se comprueba aca adentro, sin
   red — por eso la aplicacion sigue andando con el wifi cortado o el dia que
   el servidor se caiga.

   HOY NO HABILITA NI BLOQUEA NADA. La aplicacion funciona igual con licencia y
   sin ella, y el texto lo dice con esas palabras. Esta puesto desde el
   principio porque una version publicada que no mira la licencia la va a
   ignorar para siempre: no hay forma de agregarle el control despues a las
   copias que ya estan instaladas. */
async function refreshLicencia() {
  try { S.licencia = await api.get("/api/licencia/local"); }
  catch (e) { S.licencia = null; }      // servidor web: no existe el endpoint
  renderLicencia();
}

function renderLicencia() {
  const caja = $("#acct");
  // Si hay login configurado manda la cuenta: es un servidor web y ahi la
  // licencia se emite, no se guarda.
  if (!caja || !S.licencia || (S.auth && S.auth.configurado)) return;
  caja.hidden = false;
  const l = S.licencia;
  const puesta = l.situacion === "valida";

  caja.innerHTML = puesta
    ? `<div class="acct-chip lic">
         <div class="acct-txt">
           <b>${esc(l.email)}</b>
           <span>${esc(l.plan === "free" ? t("lic.plan_free") : t("lic.plan_pago"))}${
             l.fundador ? ` · ${esc(t("lic.fundador"))}` : ""}</span>
         </div>
         <button class="acct-out" id="lic-abrir">${esc(t("lic.ver"))}</button>
       </div>`
    : `<button class="acct-in" id="lic-abrir">
         ${icono("marcador", "ico-sm")}<span>${esc(t("lic.poner"))}</span>
       </button>`;
  $("#lic-abrir", caja).onclick = abrirLicencia;
}

function abrirLicencia() {
  const l = S.licencia || { situacion: "sin_licencia", plan: "free" };
  const puesta = l.situacion === "valida";
  const host = document.createElement("div");
  host.className = "overlay";
  host.innerHTML = `<div class="sheet estrecha">
    <div class="sheet-head">
      <div><h2>${esc(t("lic.title"))}</h2>
        <p>${esc(t("lic.sub"))}</p></div>
      <button class="sheet-close" aria-label="${esc(t("ui.close"))}">${icono("cerrar")}</button>
    </div>
    <div class="sheet-body">
      ${puesta ? `<div class="lic-puesta">
          <div class="lic-fila"><span>${esc(t("lic.de"))}</span><b>${esc(l.email)}</b></div>
          <div class="lic-fila"><span>${esc(t("lic.plan"))}</span><b>${
            /* la clave entera y no armada por concatenación: así se puede
               buscar con grep y el test que detecta claves faltantes no lee
               "lic.plan_" suelto como si fuera una clave */
            esc(l.plan === "free" ? t("lic.plan_free") : t("lic.plan_pago"))}${
            /* la marca de fundador va también acá: la barra lateral la muestra
               y esta es la vista detallada — que diga menos que el resumen
               hace dudar de las dos */
            l.fundador ? ` · ${esc(t("lic.fundador"))}` : ""}</b></div>
          ${l.alta ? `<div class="lic-fila"><span>${esc(t("lic.desde"))}</span><b>${
            esc(new Date(l.alta * 1000).toLocaleDateString(localeNum(),
                { year: "numeric", month: "long" }))}</b></div>` : ""}
          ${l.dias_restantes != null ? `<div class="lic-fila"><span>${
            esc(t("lic.vence"))}</span><b>${esc(t("lic.dias", { n: l.dias_restantes }))}</b></div>` : ""}
        </div>` : ""}

      <p class="help-note">${t("lic.explica")}</p>

      <div class="stage-sub">${esc(t(puesta ? "lic.reemplazar" : "lic.pegar"))}</div>
      <textarea id="lic-txt" class="nota-campo" rows="4"
        placeholder="${esc(t("lic.placeholder"))}" spellcheck="false"></textarea>
      <div class="controls">
        <button class="btn" id="lic-guardar">${esc(t("lic.guardar"))}</button>
        ${puesta ? `<button class="btn ghost" id="lic-sacar">${esc(t("lic.sacar"))}</button>` : ""}
      </div>
      <p class="stage-note" id="lic-estado"></p>
    </div>
  </div>`;
  document.body.appendChild(host);
  const cerrar = () => host.remove();
  $(".sheet-close", host).onclick = cerrar;
  host.onclick = (e) => { if (e.target === host) cerrar(); };

  $("#lic-guardar", host).onclick = async () => {
    const texto = $("#lic-txt", host).value.trim();
    if (!texto) { $("#lic-estado", host).textContent = t("lic.vacio"); return; }
    const btn = $("#lic-guardar", host);
    btn.disabled = true;
    try {
      S.licencia = await api.post("/api/licencia/local", { texto });
      renderLicencia();
      toast(t("lic.puesta_ok"), "ok");
      cerrar();
    } catch (e) {
      // el servidor ya explica por que no sirve, en castellano
      $("#lic-estado", host).innerHTML = `<span class="neg">${esc(e.message)}</span>`;
      btn.disabled = false;
    }
  };

  const sacar = $("#lic-sacar", host);
  if (sacar) sacar.onclick = async () => {
    if (!confirm(t("lic.confirmar_sacar"))) return;
    try {
      S.licencia = await api.del("/api/licencia/local");
      renderLicencia();
      toast(t("lic.sacada"), "ok");
      cerrar();
    } catch (e) {
       toast(e.message, "err"); }
  };
}

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
  if (!S.auth || !S.auth.configurado) {
    // Sin login es el escritorio: el hueco lo ocupa la licencia.
    caja.hidden = true;
    renderLicencia();
    return;
  }
  caja.hidden = false;
  caja.replaceChildren();

  const u = S.auth.usuario;
  if (!u) {
    const b = document.createElement("a");
    b.className = "acct-in";
    b.href = "/api/auth/google/start?next=/app";
    b.append(googleMark(), Object.assign(document.createElement("span"),
                                         { textContent: t("auth.sign_in") }));
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
  out.className = "acct-out"; out.title = t("auth.sign_out"); out.textContent = t("auth.sign_out");
  out.onclick = async () => {
    try { await api.post("/api/auth/logout", {}); } catch (err) { /* igual salimos */ }
    S.auth.usuario = null; renderAuth(); toast(t("auth.signed_out"), "ok");
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
      <h3 id="gate-t">${esc(t("auth.expired"))}</h3>
      <p>${esc(t("auth.gate_body"))}</p>
      <p class="gate-fine">${esc(t("auth.gate_fine"))}</p>
      <div class="gate-row">
        <button class="btn ghost" data-x>${esc(t("ui.close"))}</button>
        <a class="btn" href="/api/auth/google/start?next=/app"></a>
      </div>
    </div>`;
  const entrar = $("a", fondo);
  entrar.append(googleMark(), Object.assign(document.createElement("span"),
                                            { textContent: t("auth.sign_in") }));
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
  } catch (e) { toast(`${t("err.no_backend")}: ${e.message}`, "err"); }
  pintarChrome();
  refreshAuth();
  // en el escritorio ocupa el hueco de la cuenta; en la web no existe el
  // endpoint y queda en null sin molestar
  refreshLicencia();
  initTheme();
  refreshSavedCount();
  refreshBancoCount();
  refreshMt5();
  refreshCuenta();
  refreshRobots();
  $$("#nav button").forEach(b => b.onclick = () => navigate(b.dataset.page, b.dataset.vista || undefined));
  // los contadores ya se pidieron arriba, pero sin esperarlos: la bienvenida
  // necesita saber si hay algo hecho ANTES de decidir si aparece
  await Promise.allSettled([refreshSavedCount(), refreshBancoCount(), refreshRobots()]);
  /* La dirección manda sobre el arranque por omisión, salvo que toque la
     bienvenida: alguien que abre por primera vez tiene que ver la bienvenida
     aunque haya quedado un fragmento viejo pegado. */
  const guardada = rutaActual();
  if (tocaBienvenida()) navigate("bienvenida");
  else if (guardada) navigate(guardada.page, guardada.vista);
  else navigate(S.datasets.length ? "mining" : "data");
})();
