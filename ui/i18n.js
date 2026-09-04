/* Idioma de la interfaz.
   ---------------------------------------------------------------------------
   El inglés es el idioma por defecto y no es una preferencia estética: los
   nombres de las métricas SON el vocabulario del oficio. Profit factor,
   drawdown, win rate, Sharpe, expectancy — así aparecen en MetaTrader, en
   TradingView y en cualquier informe que alguien vaya a leer después. Cada vez
   que se traducen, el término deja de ser reconocible: "caída máxima" es
   español correcto y aun así hay que explicarlo, mientras que "drawdown" ya lo
   sabe cualquiera que haya operado un mes.

   El español está completo, no es un resto. Se elige desde la barra lateral y
   queda guardado.

   Cada entrada lleva los dos idiomas en la misma línea, a propósito: con dos
   diccionarios separados, agregar un texto en uno y olvidarlo en el otro no se
   nota hasta que alguien cambia de idioma y ve la clave cruda en pantalla.

   Uso:
     t("nav.mining")                    -> "Mining"
     t("mining.goal", { n: 25 })        -> "25 strategies"
   Las variables se escriben {así} en el texto. */

"use strict";

const STR = {
  /* ------------------------------------------------------------- navegación */
  "nav.section": ["Workspace", "Trabajo"],
  "nav.data": ["Instruments", "Instrumentos"],
  "cat_bloque.vela": ["candle", "vela"],
  "cat_bloque.trend": ["trend", "tendencia"],
  "cat_bloque.momentum": ["momentum", "impulso"],
  "cat_bloque.channel": ["channel", "canal"],
  "cat_bloque.volatility": ["volatility", "volatilidad"],
  "cat_bloque.volume": ["volume", "volumen"],
  "cat_bloque.funding": ["funding", "funding"],
  "cat_bloque.other": ["other", "otros"],
  "gene.rb": ["R:R", "R:B"],
  "wf.ef_corto": ["eff.", "ef."],
  "nav.mining": ["Generation", "Generación"],
  "nav.operar_cfd": ["Take to MetaTrader", "Llevar a MetaTrader"],
  "nav.ajustes": ["Settings", "Ajustes"],
  /* "APROBADAS" CONTRADECÍA A SUS PROPIAS FILAS: adentro conviven las que
     aprobaron y las que aguantaron a medias, y tres usuarios de prueba
     leyeron "Aprobadas" con todas las filas en ámbar (2 de septiembre).
     "Las que aguantaron" es cierto para las dos. */
  "nav.aprobadas": ["Validated", "Validadas"],
  "nav.piloto_avanzado": ["Autopilot (advanced)", "Automático (avanzado)"],
  /* LAS BANDEJAS: cada una contiene sólo lo que necesita una decisión ahora. */
  "saved.sub_aprobadas": ["Robust on data they never saw. \"Partially robust\" means it made money in most windows but kept less of its edge out-of-sample: worth running in demo, not worth trusting blind. Deploy one, or combine several into a portfolio.",
                          "Robustas sobre datos que nunca vieron. \"Robustez parcial\" significa que ganó en la mayoría de las ventanas pero conservó menos ventaja fuera de muestra: conviene ejecutarla en demo, no confiarle a ciegas. Activar una, o combinar varias en un portafolio."],
  "saved.descartadas_t": ["Discarded", "Descartadas"],
  "saved.sub_descartadas": ["Did not pass validation, or retired with a reason. Kept so the same mistake is not repeated.",
                            "No superaron la validación, o fueron retiradas con motivo. Se guardan para no repetir el mismo error."],
  /* PROBAR COMO FLUJO: lo que trajimos, y a dónde fue cada una. Lo probado
     se queda a la vista, con su porqué, hasta que se limpia. */
  "flujo.trajimos": ["Brought from Generation", "Traídas de Generación"],
  /* NO "EN PRUEBA": desde que probar es un botón, la caja decía "10 being
     tested" con diez estrategias quietas esperando (el usuario, 3 de
     septiembre: "cuando vas a testing no se empezaron a testear"). */
  "flujo.trajimos_sub": ["{n} waiting for validation", "{n} en espera de validación"],
  "flujo.trajimos_probando": ["{n} left · validating one after another", "{n} restantes · validando una tras otra"],
  "flujo.chip_probando": ["Validating now", "En validación ahora"],
  "flujo.chip_en_otra_bandeja": ["It moved to another tray: open it from there.", "Se movió a otra bandeja: abrirla desde ahí."],
  "fp.encontradas": ["Candidates", "Candidatas"],
  "fp.probar": ["Validate", "Validar"],
  "fp.probar_elegidas": ["Validate the {n} selected", "Validar las {n} seleccionadas"],
  "fp.probar_todas": ["Validate all", "Validar todas"],
  "fp.anual": ["annual", "anual"],
  "fp.caida": ["drawdown", "drawdown"],
  "fp.tramos": ["{g} of {n} windows", "{g} de {n} ventanas"],
  "fp.afuera": ["out-of-sample", "fuera de muestra"],
  "fp.por_que": ["see why", "ver por qué"],
  "fp.encender_corto": ["Deploy", "Activar"],
  "fp.encender": ["Deploy to demo", "Activar en demo"],
  "fp.seguir": ["Resume: {n} left from the last batch", "Continuar: faltan {n} de la última tanda"],
  "fp.ver_todas": ["See all · {n} →", "Ver todas · {n} →"],
  "fp.por_ruina": ["p95 drawdown {dd}%", "drawdown p95 {dd}%"],
  "fp.limpiar": ["Clear", "Limpiar"],
  "fp.sub_ok": ["data they never saw", "datos que nunca vieron"],
  "fp.sub_no": ["they were describing the past", "describían el pasado"],
  "fp.vacia": ["All validated.", "Todo validado."],
  "fp.buscar_mas": ["Generate more →", "Generar más →"],
  "fp.vacia_ok": ["Nothing robust yet.", "Todavía no hay ninguna robusta."],
  "fp.vacia_no": ["Nothing failed yet.", "Todavía no falló ninguna."],
  "flujo.aprobadas": ["Validated", "Validadas"],
  "flujo.aprobadas_sub": ["{n} remained robust on data they never saw", "{n} conservaron la ventaja sobre datos que no vieron"],
  "flujo.no_pasaron": ["Overfitted", "Sobreajustadas"],
  "flujo.no_pasaron_sub": ["{n} were describing the past", "{n} describían el pasado"],
  "flujo.de_esta_tanda": [
    "This is the batch just validated. The totals for every strategy are in the trays below.",
    "Esta es la tanda recién validada. Los totales de todas las estrategias están en las solapas de abajo."],
  "flujo.limpiar": ["Clear what has been validated", "Limpiar lo ya validado"],
  "flujo.limpiar_sub": ["They stay in Validated and in Discarded; this only tidies up here.", "Quedan en Validadas y Descartadas; esto sólo ordena aquí."],
  "flujo.resultados": ["Validation results", "Resultados de la validación"],
  "col.prueba": ["Validation", "Validación"],
  "col.prueba_help": ["Winning windows / windows · how much of the edge survived · return on data it never saw · p95 drawdown over 1,000 resamples of the trades",
                      "Ventanas ganadoras / ventanas · cuánto de la ventaja sobrevivió · retorno sobre datos que nunca vio · drawdown p95 con 1000 remuestreos de las operaciones"],
  "saved.linea": ["{p} in validation · {a} validated · {o} trading · {d} discarded",
                  "{p} en validación · {a} validadas · {o} en operación · {d} descartadas"],
  "saved.vacio_probar": ["Nothing in validation", "Nada en validación"],
  "saved.vacio_probar_sub": ["Everything sent already has its verdict.", "Todo lo enviado ya tiene su veredicto."],
  "saved.vacio_probar_btn": ["See the validated ones", "Ver las validadas"],
  "saved.vacio_aprobadas": ["No validated strategy yet", "Todavía no hay validadas"],
  "saved.vacio_aprobadas_sub": ["Generate, send the candidates to validation, and the robust ones appear here.",
                                "Generar, enviar las candidatas a validación, y las robustas aparecen aquí."],
  "saved.vacio_aprobadas_btn": ["Go to Generation", "Ir a Generación"],
  "saved.vacio_descartadas": ["Nothing discarded", "Nada descartado"],
  "saved.armar": ["Build a portfolio with {n}", "Armar un portafolio con {n}"],
  "op.cuenta_t": ["Account", "Cuenta"],
  /* LA HISTORIA EN UNA FRASE: lo que la cuenta hizo, dicho como se cuenta. */
  "op.historia": ["So far: {n} closed trades, net {neto} USDT, {abiertas} open. {mejor}",
                  "Hasta ahora: {n} operaciones cerradas, neto {neto} USDT, {abiertas} abiertas. {mejor}"],
  "op.historia_mejor": ["Best symbol: {sim} ({pnl} USDT).", "Mejor símbolo: {sim} ({pnl} USDT)."],
  "op.historia_nada": ["Nothing traded yet: the robots are watching.", "Todavía no se operó nada: los robots están mirando."],
  "op.encendiendo": ["Deploying…", "Activando…"],
  "op.encendida_ok": ["Deployed", "Activa"],
  "bot.apagando": ["Stopping…", "Deteniendo…"],
  "ex.conectando": ["Connecting…", "Conectando…"],
  "ex.conectada_ok": ["Connected", "Conectada"],
  /* LOS PRIMEROS PASOS: tres tildes en la barra, hasta que estén los tres. */
  "pp.titulo": ["The first three steps", "Los primeros tres pasos"],
  "pp.buscaste": ["Run a generation", "Ejecutar una generación"],
  "pp.probaste": ["Validate a strategy", "Validar una estrategia"],
  "pp.encendiste": ["Deploy a robot", "Activar un robot"],
  "pp.exportaste": ["Take one to MetaTrader", "Llevar una a MetaTrader"],
  "mine.primera": ["The first generation is ready: market and recipe are already set. Press Start.",
                   "La primera generación ya está lista: mercado y receta están configurados. Presionar Empezar."],
  "op.saldo": ["Balance", "Saldo"],
  "op.neto": ["Net result", "Resultado neto"],
  "op.abiertas": ["Open positions", "Posiciones abiertas"],
  "op.detalle": ["See detail", "Ver detalle"],
  "op.encender_t": ["Deploy one", "Activar una"],
  "op.encender_sub": ["A validated strategy, on the demo account, with its share of the capital already assigned.", "Una estrategia validada, en la cuenta demo, con su porción del capital ya asignada."],
  "op.modo_una": ["One strategy", "Una estrategia"],
  "op.modo_conjunto": ["A set", "Un conjunto"],
  "op.modo_una_sub": ["One robot on one symbol, with the share of the capital the autopilot would assign it.", "Un robot sobre un símbolo, con la porción del capital que le asignaría el piloto."],
  "op.modo_conjunto_sub": ["Several at once, each on its own symbol, with the capital split between them.", "Varias a la vez, cada una sobre su símbolo, con el capital distribuido entre ellas."],
  "op.elegi_una": ["Select one strategy to deploy", "Seleccionar una estrategia para activar"],
  "op.elegi_varias": ["Select two or more: the capital is split between them", "Seleccionar dos o más. El capital se distribuye entre las seleccionadas."],
  "op.elegidas_n": ["{n} selected", "{n} seleccionadas"],
  "op.repetido": ["Two of these run on {sim}: that is a single bet under two names. The autopilot allows one robot per symbol.", "Dos de éstas operan sobre {sim}: es una sola apuesta con dos nombres. El piloto admite un robot por símbolo."],
  "op.encender_conjunto_n": ["Deploy the set of {n}", "Activar el conjunto de {n}"],
  "op.elegir_aprobada": ["Select a validated strategy…", "Seleccionar una estrategia validada…"],
  "op.encender_btn": ["Deploy to demo", "Activar en demo"],
  "op.sin_aprobadas": ["Nothing to deploy yet. Strategies get here by remaining robust in Validation.", "Todavía no hay validadas para activar. Provienen de Validación."],
  "op.corriendo_t": ["Running", "En ejecución"],
  "op.nada_corriendo": ["Nothing running. Deploy one above.", "Nada en ejecución. Activar una arriba."],
  "op.volver": ["← Trading", "← Operación"],
  "pf.encender_conjunto": ["Deploy the set to demo", "Activar el conjunto en demo"],
  "pf.encender_title": ["Run the whole set", "Ejecutar el conjunto entero"],
  "pf.encender_sub": ["{n} robots on the demo account, each with its share of the account already decided.",
                      "{n} robots en la cuenta demo, cada uno con su porción de la cuenta ya decidida."],
  "nav.mercados": ["Instruments", "Instrumentos"],
  "nav.cuenta_ok": ["Binance account · demo connected", "Cuenta Binance · demo conectada"],
  "nav.cuenta_no": ["Connect Binance account", "Conectar cuenta Binance"],
  "mine.avanzado": ["Fine-tune the generation", "Ajustar la generación"],
  "mine.avanzado_sub": ["blocks, risk, costs, filters — the recipe already set them", "bloques, riesgo, costos, filtros — la receta ya los dejó puestos"],
  "etapa.vigentes": ["Hide discarded", "Ocultar descartadas"],
  "op.tab_piloto": ["Autopilot", "Piloto automático"],
  "op.conectar_t": ["Connect the Binance demo account", "Conectar la cuenta demo de Binance"],
  "op.conectar_sub": ["The robots trade on it with simulated funds. It takes two minutes and is done once.", "Los robots operan con fondos simulados. Lleva dos minutos y se hace una sola vez."],
  "op.conectar_btn": ["Connect account", "Conectar cuenta"],
  "op.conectar_primero": ["Connect the Binance demo account first; it takes two minutes.", "Conectar primero la cuenta demo de Binance; lleva dos minutos."],
  "saved.encendida": ["{nombre} is deployed, in demo. Follow it under Trading.", "{nombre} quedó activa en demo. Se sigue en Operación."],
  "saved.en_cola": ["Validating in the background: {n} in the queue.", "Validando en segundo plano: {n} en cola."],
  "pil.oferta": ["BotiQuant can generate, validate and deploy robots on its own. The autopilot can be activated at any time.", "BotiQuant puede generar, validar y activar robots por su cuenta. El piloto automático se activa en cualquier momento."],
  "nav.paso": ["Step {n}", "Paso {n}"],
  // el numero de al lado cuenta TODO el Databank, no la ultima corrida:
  // pegado a la palabra "Minado" y solo, se leia como "91 minados"
  "nav.bank_count": ["{n} candidates in the repository", "{n} candidatas en el repositorio"],
  /* La solapa de arriba se llama "Encontradas" en castellano y este rótulo
     decía "Databank" en los dos idiomas: la misma cosa con dos nombres, y uno
     de ellos en inglés en una pantalla en castellano (3 de septiembre). */
  "nav.bank": ["Candidates", "Candidatas"],
  "nav.montecarlo": ["Resampling", "Remuestreo"],
  "nav.walkforward": ["Window validation", "Validación por ventanas"],
  "nav.portfolio": ["Portfolio", "Portafolio"],
  "nav.saved": ["Validation", "Validación"],
  "nav.offline": ["desktop · local", "escritorio · local"],
  /* Corto a proposito: la barra lateral tiene 200px utiles y la frase larga
     partia en dos renglones, que en una fila de menu se lee como un error. */
  "nav.active_run": ["Active run", "Ejecución activa"],
  "nav.support": ["Report a problem", "Reportar un problema"],
  "nav.theme": ["Switch theme", "Cambiar tema"],
  "nav.theme_dark": ["Switch to dark theme", "Cambiar a tema oscuro"],
  "nav.theme_light": ["Switch to light theme", "Cambiar a tema claro"],
  "nav.language": ["Language", "Idioma"],
  "nav.tagline": ["strategy generator", "generador de estrategias"],

  /* ---------------------------------------------------------------- métricas
     Los nombres de métrica NO se traducen. Ver la nota de arriba: son
     términos del oficio, y en español se usan igual. Lo que sí se traduce es
     la explicación de cada uno. */
  "m.cagr": ["Annual return (CAGR)", "Retorno anual (CAGR)"],
  "m.net": ["Total return", "Retorno total"],
  "m.pf": ["Profit factor", "Profit factor"],
  /* QUÉ ES NORMAL. Una usuaria de prueba que no sabe de trading recorrió la
     aplicación el 3 de septiembre de 2026 y dijo lo obvio: los números
     aparecen desnudos y nadie le dice con qué compararlos. "¿+7,59% anual es
     mucho?" no tiene respuesta en ningún lado. La ficha de robustez ya lo
     hacía bien —"1.0 es que sobrevivió entero; 0.5 es lo normal y sano"— y
     acá se hace lo mismo con las cifras de siempre. */
  "ref.cagr": [
    "How much the account grows per year, on average, over the measured period. Buying and holding the S&P 500 has averaged about 10% a year: below that, the strategy is not paying for its own complexity. Above 40% over a short period is usually luck, not edge.",
    "Cuánto crece la cuenta por año, en promedio, sobre el período medido. Comprar y mantener el S&P 500 promedió alrededor del 10% anual: por debajo de eso, la estrategia no compensa su propia complejidad. Arriba del 40% en un período corto suele ser suerte, no ventaja."],
  "ref.dd": [
    "The worst peak-to-bottom drawdown the account went through. It is the number that decides whether a strategy can be held: 10% is uncomfortable, 20% is where most people stop, above 30% almost nobody stays in. It has to be smaller than what the operator is willing to watch happen.",
    "El peor descenso de pico a fondo que atravesó la cuenta. Es el número que decide si una estrategia se puede sostener: 10% incomoda, 20% es donde la mayoría abandona, arriba de 30% casi nadie resiste. Tiene que ser más chico que lo que uno esté dispuesto a ver pasar."],
  "ref.pf": [
    "How much it won for every unit it lost. Below 1 it lost money; 1.2 is thin but real; 1.5 is good; above 2.5 on few trades is usually a fluke that will not repeat.",
    "Cuánto ganó por cada unidad que perdió. Abajo de 1 perdió dinero; 1,2 es flaco pero real; 1,5 está bien; arriba de 2,5 con pocas operaciones suele ser una casualidad que no se repite."],
  "ref.trades": [
    "How many round trips it made. Under 30 the numbers mean almost nothing — a couple of lucky trades move everything. From 100 up the average starts to be worth something.",
    "Cuántas operaciones completas hizo. Abajo de 30 los números no significan casi nada: dos operaciones con suerte mueven todo. De 100 para arriba el promedio empieza a valer."],
  "ref.sharpe": [
    "Return divided by how much the equity curve moved along the way. Below 0.5 the swings eat the gain; around 1 is solid; above 2 measured over a short period is almost always overfitting.",
    "El rendimiento dividido por la variabilidad del recorrido. Abajo de 0,5 los vaivenes se comen la ganancia; alrededor de 1 es sólido; arriba de 2 medido en un período corto es casi siempre sobreajuste."],
  "ref.winrate": [
    "Share of trades closed in profit. A high one is not better on its own: a strategy that wins 30% of the time and lets the winners run beats one that wins 70% and cuts them short. Read it together with the profit factor.",
    "Qué proporción de operaciones cerró en ganancia. Que sea alta no la hace mejor: una estrategia que acierta el 30% y deja correr las ganadoras le gana a una que acierta el 70% y las corta enseguida. Se lee junto con el profit factor."],
  "m.dd": ["Max drawdown", "Drawdown máximo"],
  "m.winrate": ["Win rate", "Win rate"],
  "m.sharpe": ["Sharpe", "Sharpe"],
  "m.trades": ["Trades", "Operaciones"],
  /* ───────────────────────────── las categorías de búsqueda ───────────────
     Cada tarjeta dice qué busca Y QUÉ CUESTA. Todas cuestan algo: acertar más
     seguido significa ganar menos por acierto, caer poco significa rendir
     menos. Callarlo sería vender lo que la portada dice no vender. */
  "rec.titulo": ["What is the objective?", "¿Cuál es el objetivo?"],
  "rec.sub": ["each one configures the whole generation, not just the filters",
              "cada una configura la generación entera, no sólo los filtros"],
  "rec.puesta": ["Set up for: {nombre}. Anything below can still be changed.",
                 "Configurado para: {nombre}. Todo lo de abajo se puede modificar."],
  "rec.congelada": ["The generation is running with its own settings. Stop it to select another recipe.",
                   "La generación se ejecuta con su propia configuración. Detenerla para seleccionar otra receta."],

  "rec.fondeo": ["Pass a funded-account challenge", "Pasar un desafío de fondeo"],
  /* Comparativa y no absoluta, a propósito por dos razones.

     Una: medido, la primera que trae opera una vez cada 4,8 días en el S&P y
     una cada 21 en Bitcoin. Prometer un número sería inventarlo.

     Dos: la primera versión decía «cuida la caída», y eso ya lo dice «Dormir
     tranquilo». Dos categorías con la misma promesa es una de sobra. Lo que
     distingue a ésta es el ORDEN: entran las que aguantan y arriba quedan las
     que más operan, que es lo que sirve con fecha de vencimiento. */
  "rec.fondeo_que": ["The most active of the robust ones",
                     "La más activa de las robustas"],
  "rec.fondeo_cuesta": ["Costs: it trades rarely — making money and trading often barely coexist",
                        "Costo: opera poco — ganar y operar seguido casi no conviven"],

  "rec.largo": ["Hold it for years", "Mantenerla durante años"],
  "rec.largo_que": ["Few trades, edge that keeps working",
                    "Pocas operaciones, ventaja que se sostiene"],
  "rec.largo_cuesta": ["Costs: weeks can go by without a single trade",
                       "Costo: pueden pasar semanas sin operar"],

  "rec.aciertos": ["Win more often than it loses", "Acertar más veces de las que falla"],
  "rec.aciertos_que": ["Most trades close in the green",
                       "La mayoría de las operaciones cierran en positivo"],
  "rec.aciertos_cuesta": ["Costs: each loss is bigger than each win",
                          "Costo: cada pérdida es más grande que cada ganancia"],

  "rec.agresiva": ["Go for more", "Ir por más"],
  "rec.agresiva_que": ["Three times the risk per trade, more return, deeper drawdowns",
                       "El triple de riesgo por operación, más retorno, drawdowns más profundos"],
  "rec.agresiva_cuesta": ["Costs: drawdowns of 25% or more are normal here",
                          "Costo: drawdowns del 25% o más son normales aquí"],
  "rec.scalping": ["Trade several times a day", "Operar varias veces por día"],
  "rec.scalping_que": ["Opens and closes often, to watch the robot execute",
                       "Abre y cierra seguido, para ver al robot ejecutar"],
  "rec.scalping_cuesta": ["Costs: fees eat most of the edge, and it needs 1-minute data from Instruments",
                          "Costo: las comisiones se comen casi toda la ventaja, y necesita velas de 1 minuto desde Instrumentos"],
  "rec.necesita_m1": ["{ds} only has 1-hour candles: the generation stays at 1h. Download the 1-minute version in Instruments to trade shorter.",
                      "{ds} sólo tiene velas de 1 hora: la generación queda en 1h. Descargar la versión de 1 minuto en Instrumentos para operar más corto."],
  "rec.tranquilo": ["Sleep at night", "Dormir tranquilo"],
  "rec.tranquilo_que": ["The worst drawdown stays small",
                        "El drawdown máximo se mantiene chico"],
  "rec.tranquilo_cuesta": ["Costs: it returns less per year",
                           "Costo: rinde menos por año"],

  "m.trades_month": ["Trades per month", "Operaciones por mes"],
  "m.trades_week": ["Trades per week", "Operaciones por semana"],
  /* Desempata por frecuencia entre las que ya pasaron la vara. No es un
     filtro: como filtro la frecuencia no devuelve casi nada. */
  "mine.sort_activity": ["Score, favouring the most active",
                         "Score, favoreciendo a las que más operan"],
  "m.retdd": ["Return / drawdown", "Retorno / drawdown"],
  "m.exposure": ["Time in market", "Tiempo en mercado"],
  "m.expectancy": ["Expectancy (R)", "Expectancy (R)"],
  "m.months": ["Months", "Meses"],
  "m.avg_trade": ["Average trade", "Operación promedio"],
  "m.worst_month": ["Worst month", "Peor mes"],
  "m.months_positive": ["Positive months", "Meses positivos"],
  "m.top_trade": ["Biggest trade's share", "Peso de la mejor operación"],
  /* El desglose del score. El backend arma estos rotulos en castellano
     (metrics.py no sabe de idiomas) y la pantalla los mostraba tal cual: con la
     app en ingles el titulo decia "Score - how repeatable it looks" y las barras
     de abajo "Consistencia (Sharpe)". Ahora la clave manda sobre el rotulo. */
  "score.consistencia": ["Consistency (Sharpe)", "Consistencia (Sharpe)"],
  "score.recuperacion": ["Profit vs. drawdown", "Ganancia vs. drawdown"],
  "score.evidencia":    ["Evidence (no. of trades)", "Evidencia (nº de operaciones)"],
  "score.ventaja":      ["Edge per trade", "Ventaja por operación"],
  "score.estabilidad":  ["Month-to-month stability", "Estabilidad mes a mes"],
  "score.reparto":      ["Profit spread out", "Ganancia repartida"],
  "m.score": ["Score", "Score"],
  "m.session": ["Session", "Horario"],
  "gene.trail": ["trail", "trailing"],
  "gene.max_bars": ["max {n} bars", "máx {n} velas"],
  "m.cagr_exposed": ["Annual while in market", "Anual s/ exposición"],
  "m.avg_win": ["Average win", "Ganancia promedio"],
  "m.avg_loss": ["Average loss", "Pérdida promedio"],
  "m.final_equity": ["Final equity", "Capital final"],
  "m.win_loss": ["Average win / loss", "Ganancia / pérdida media"],
  "m.payoff": ["Win per 1 lost", "Gana por cada 1 que pierde"],
  "insp.g_rinde": ["How much does it make?", "¿Cuánto rinde?"],
  "insp.g_duele": ["How much does it hurt?", "¿Cuánto duele?"],
  "insp.g_opera": ["How does it trade?", "¿Cómo opera?"],
  "insp.ya_guardada": ["In Validation", "En Validación"],
  /* COMPARTIR CON UN ENLACE: quien lo abre no necesita cuenta. */
  "comp.btn": ["Share", "Compartir"],
  "comp.titulo": ["Share this strategy", "Compartir esta estrategia"],
  "comp.sub": ["Anyone with the link can open it, no account needed. It never includes keys, account or robots.",
               "Cualquiera con el enlace la abre, sin cuenta. Nunca incluye las claves, la cuenta ni los robots."],
  "comp.nivel_usar": ["To use", "Para usar"],
  "comp.nivel_usar_sub": ["Results, verdict and rules, with buttons for TradingView and MetaTrader 5.", "Resultados, veredicto y reglas, con botones para TradingView y MetaTrader 5."],
  "comp.nivel_mirar": ["To look at", "Para mirar"],
  "comp.nivel_mirar_sub": ["Results and verdict only. The rules are not included.", "Sólo resultados y veredicto. Las reglas no se incluyen."],
  "comp.autor": ["Sign it (optional)", "Firmar (opcional)"],
  "comp.crear": ["Create the link", "Crear el enlace"],
  "comp.creando": ["Publishing…", "Publicando…"],
  "comp.listo": ["Link ready", "Enlace listo"],
  "comp.copiar": ["Copy", "Copiar"],
  "comp.copiado": ["Copied", "Copiado"],
  "comp.abrir": ["Open", "Abrir"],
  "comp.otro": ["Create another link", "Crear otro enlace"],
  "comp.nota": ["It can be turned off at any time from Documentation → My links.", "Se puede desactivar en cualquier momento desde Documentación → Mis enlaces."],
  "comp.mis_enlaces": ["My links", "Mis enlaces"],
  "comp.mis_enlaces_sub": ["The strategies shared so far. Turning one off makes its link stop opening at once.", "Las estrategias compartidas hasta ahora. Desactivar una hace que su enlace deje de abrir en el acto."],
  "comp.sin_enlaces": ["Nothing shared yet. Every strategy has a Share button.", "Todavía no se compartió ninguna. Cada estrategia tiene un botón Compartir."],
  "comp.apagar": ["Turn off", "Desactivar"],
  "comp.apagado": ["Link turned off.", "Enlace desactivado."],
  "insp.save": ["Send to validation", "Enviar a validación"],
  "bot.solo_demo": ["demo account", "cuenta demo"],
  "m.years": ["Years", "Años"],

  /* ------------------------------------------- qué le baja el puntaje */
  "why.lowers": ["What drags its score down most is <b>{parte}</b>: {motivo}.",
                 "Lo que más le baja el puntaje es <b>{parte}</b>: {motivo}."],
  "why.consistency": ["its Sharpe is {sharpe} — the curve moves a lot for what it returns",
                      "su Sharpe es {sharpe}: la curva se mueve mucho para lo que rinde"],
  "why.recovery": ["it makes {cagr}% a year but falls as much as {dd}%",
                   "gana {cagr}% al año pero llega a caer {dd}%"],
  "why.evidence": ["{n} trades is too small a sample to trust the result",
                   "{n} operaciones son poca muestra para confiar en el resultado"],
  "why.edge": ["its expectancy is {r}R per trade, a thin margin",
               "su expectativa es {r}R por operación, un margen fino"],
  "why.stability": ["only {pct}% of months closed positive",
                    "sólo {pct}% de los meses cerraron en positivo"],
  "why.spread": ["the single best trade accounts for {pct}% of the profit",
                 "la mejor operación aporta el {pct}% de la ganancia"],
  "risk.no_stop": ["no stop or target, exits on signal", "sin stop ni target, sale por señal"],
  "risk.atr": [
    "Risks {pct}% of capital per trade · stop at {mult}× volatility (ATR {atr}) · 1:{rr}",
    "Arriesga {pct}% del capital por operación · stop a {mult}× la volatilidad (ATR {atr}) · relación 1:{rr}"],
  "risk.points": ["points", "puntos"],
  "risk.pct_price": ["% of price", "% del precio"],
  "note.range_clamped": ["{mercado} does not cover that whole period — the dates were fitted to its history",
                         "{mercado} no cubre todo ese período — las fechas se ajustaron a su historial"],
  "note.typical_diff": ["Currently set to <b>{actual}</b>. The typical one for <b>{mercado}</b> is <b>{tipico}</b>.",
                        "Configurado en <b>{actual}</b>. El típico de <b>{mercado}</b> es <b>{tipico}</b>."],
  "note.use_typical": ["Use the typical one", "Usar el típico"],

  /* ---------------------------------------------------------------- puntaje */
  "tier.solid": ["Solid", "Sólida"],
  "tier.promising": ["Promising", "Prometedora"],
  "tier.doubtful": ["Doubtful", "Dudosa"],
  "tier.fragile": ["Fragile", "Frágil"],

  /* ------------------------------------------------------------------ errores */
  "err.page": ["This page could not load", "No se pudo cargar esta página"],
  "err.no_response": ["The server did not respond.", "El servidor no respondió."],
  "auth.expired": ["The session ended", "La sesión se cerró"],
  "auth.expired_sub": ["Sign in again and everything continues where it was.",
                       "Ingresar de nuevo y todo continúa donde estaba."],
  /* La licencia, en el escritorio.

     El texto no promete nada que no cumpla. La aplicacion funciona completa
     sin licencia y eso se dice con esas palabras: la alternativa —"activá tu
     licencia"— hace creer que algo se desbloquea y despues no pasa nada. Lo
     que se ofrece es lo que de verdad da. */
  "lic.title": ["Licence", "Licencia"],
  "lic.sub": ["Checked locally on this machine, without asking any server.",
              "Se comprueba aquí, en esta máquina, sin consultar a ningún servidor."],
  "lic.poner": ["Activate licence", "Activar licencia"],
  "lic.ver": ["View", "Ver"],
  "lic.plan": ["Plan", "Plan"],
  "lic.plan_free": ["Free", "Gratis"],
  "lic.plan_pago": ["Full", "Completo"],
  "lic.fundador": ["founding member", "socio fundador"],
  "lic.de": ["Issued to", "A nombre de"],
  "lic.desde": ["With us since", "Con nosotros desde"],
  "lic.vence": ["Expires in", "Vence en"],
  "lic.dias": ["{n} days", "{n} días"],
  "lic.explica": [
    "Botiquant works in full without a licence — nothing here is locked. Adding one lets the app know who is using it and since when, and leaves this copy recognised for the day there are paid features. It is available from the account at <b>botiquant.com</b>.",
    "Botiquant funciona completo sin licencia — aquí no hay nada bloqueado. Cargar la licencia hace que la aplicación registre quién la usa y desde cuándo, y deja esta copia reconocida para el día que haya funciones de pago. Se obtiene desde la cuenta en <b>botiquant.com</b>."],
  "lic.pegar": ["Paste the licence", "Pegar la licencia"],
  "lic.reemplazar": ["Replace it with another one", "Reemplazarla por otra"],
  "lic.placeholder": ["Paste the whole text, in one line",
                      "Pegar el texto entero, en una sola línea"],
  "lic.guardar": ["Save licence", "Guardar licencia"],
  "lic.sacar": ["Remove it", "Quitarla"],
  "lic.vacio": ["Nothing has been pasted in there yet.", "Todavía no se pegó nada ahí."],
  "lic.puesta_ok": ["Licence saved", "Licencia guardada"],
  "lic.sacada": ["Licence removed from this machine",
                 "Licencia quitada de esta máquina"],
  "lic.confirmar_sacar": [
    "Remove the licence from this machine? The app keeps working exactly the same.",
    "¿Quitar la licencia de esta máquina? La aplicación sigue funcionando exactamente igual."],
  "auth.sign_in": ["Sign in with Google", "Entrar con Google"],
  "auth.sign_out": ["Sign out", "Salir"],
  "auth.signed_out": ["Signed out", "Sesión cerrada"],
  "auth.gate_body": [
    "Sign in again to carry on. Nothing saved is lost: the strategies in the repository and the instruments are still where they were.",
    "Ingresar de nuevo para continuar. Nada de lo guardado se pierde: las estrategias del repositorio y los instrumentos siguen donde estaban."],
  "auth.gate_fine": [
    "Google provides the name, the email and the picture. Nothing else: no access is requested to mail or files, and no password is typed here.",
    "Google entrega el nombre, el correo y la foto. Nada más: no se pide permiso sobre el correo ni los archivos, y aquí no se escribe ninguna contraseña."],

  /* --------------------------------------------------------------- pantalla DATOS */
  "data.sub": [
    "The most traded instruments, ready to generate on. Download with one click or import a CSV.",
    "Los instrumentos más operados, listos para generar. Descargar con un clic o importar un CSV propio."],
  "data.library": ["Instrument library", "Biblioteca de instrumentos"],
  "data.library_hint": ["real 1-minute data from Dukascopy, in server time (NY+7)",
                        "M1 real de Dukascopy, en hora del servidor (NY+7)"],
  "data.library_hint_cripto": ["1-hour candles from Binance with their funding, in UTC",
                               "velas de 1 hora de Binance con su funding, en UTC"],
  "data.search_this": ["Generate on this", "Generar sobre este"],
  "data.history_since": ["1-minute history since {fecha}", "Historial M1 desde {fecha}"],
  "data.unavailable": ["Not available for this instrument", "No disponible en este instrumento"],
  "data.download": ["Download", "Descargar"],
  "data.downloading": ["Downloading…", "Descargando…"],
  "data.add": ["Add a symbol or data", "Agregar símbolo o datos"],
  "data.add_sub": ["Import any CSV from MT4/MT5, TradingView, Dukascopy or Binance",
                   "Importar cualquier CSV de MT4/MT5, TradingView, Dukascopy o Binance"],
  "data.seccion": ["Section…", "Sección…"],
  "data.seccion_help": [
    "This file was imported before the app noted its section. Select where it belongs.",
    "Este archivo se importó antes de que la aplicación anotara su sección. Seleccionar a cuál pertenece."],
  "data.seccion_puesta": ["Section saved. Its strategies now show only there.",
                          "Sección guardada. Sus estrategias se ven sólo ahí."],
  "data.synthetic": ["synthetic", "sintético"],
  "data.shared": ["shared", "compartido"],
  "data.shared_help": ["Shared instrument: every user has it",
                       "Instrumento compartido: lo usan todos los usuarios"],
  "data.import": ["Import a CSV", "Importar un CSV propio"],
  "data.pick_file": ["Pick the file", "Seleccionar el archivo"],
  "data.pick_file_hint": ["CSV from MT4, MT5, TradingView, Dukascopy or Binance",
                          "CSV de MT4, MT5, TradingView, Dukascopy o Binance"],
  "data.name": ["Name", "Nombre"],
  "data.source": ["Source", "Fuente"],
  "data.optional": ["optional", "opcional"],
  "data.big_file": ["The file is over 100 MB", "El archivo pesa más de 100 MB"],
  "data.paste_path": ["Paste its full path", "Pegar la ruta completa"],
  "data.paste_path_hint": [
    "years of 1-minute history will not go through the browser file picker",
    "un histórico M1 de años no entra por el selector del navegador"],
  "data.import_path": ["Import by path", "Importar por ruta"],
  "data.need_path": ["Paste the path to the CSV", "Pegar la ruta del CSV"],
  "data.imported": ["Imported: {nombre} ({n} bars)", "Importado: {nombre} ({n} velas)"],
  "csv.descartadas": [
    "{total} of the {leidas} rows were left out: {detalle}. The rest was imported.",
    "Se descartaron {total} de las {leidas} filas: {detalle}. El resto se importó."],
  "csv.sin_precio": ["{n} with no price", "{n} sin precio"],
  "csv.precio_invalido": ["{n} with a zero or negative price", "{n} con un precio cero o negativo"],
  "csv.vela_incoherente": ["{n} that close outside their own range", "{n} que cierran fuera de su propio rango"],
  "csv.repetida": ["{n} repeating a timestamp", "{n} que repiten una marca de tiempo"],
  "data.uploaded": ["Uploaded: {nombre} ({n} bars)", "Subido: {nombre} ({n} velas)"],
  "data.in_workspace": ["Datasets in the workspace", "Datasets en el workspace"],
  "data.none": ["No data yet", "Todavía no hay datos"],
  "data.none_help": ["Download an instrument from the library above, or import a CSV.",
                     "Descargar un instrumento de la biblioteca de arriba, o importar un CSV propio."],
  /* "¿Borrar este dataset?" no decía ni qué se pierde ni si vuelve. Los cuatro
     que trae la aplicación se pueden volver a bajar; uno propio, importado de
     un CSV, no. Son dos situaciones distintas y hay que decir cuál es. */
  "data.confirm_delete": [
    "Delete {nombre}?\n\nStrategies already generated stay in place. If it is one of the four that ship with Botiquant it can be downloaded again from Instruments; if it was imported, the original file will be needed.",
    "¿Borrar {nombre}?\n\nLas estrategias ya generadas no se tocan. Si es uno de los cuatro que trae Botiquant se puede volver a descargar desde Instrumentos; si fue importado, hará falta el archivo original."],
  "data.deleted": ["Dataset deleted", "Dataset borrado"],

  /* ------------------------------------------------- ayudas de configuración */
  "help.risk": [
    "Each trade puts <b>{pct}%</b> ≈ <b>${plata}</b> of the ${capital} on the line; the position size is worked out so that hitting the stop costs exactly that. <br>It multiplies the return AND the drawdown of any generated strategy in the same proportion: <b>10 losses in a row</b> take <b>{racha}%</b> of the account.",
    "Cada operación pone en juego <b>{pct}%</b> ≈ <b>${plata}</b> de los ${capital}; el tamaño de la posición se calcula solo para que tocar el stop cueste exactamente eso. <br>Multiplica en la misma proporción la ganancia Y el drawdown de cualquier estrategia generada: <b>10 pérdidas seguidas</b> se llevan el <b>{racha}%</b> de la cuenta."],
  "help.no_crit_title": ["No quality filter is active.", "No hay ningún filtro de calidad activo."],
  "help.no_crit": [
    "With only <b>{n}+ trades</b> required, almost any candidate gets in: the repository fills up in seconds with candidates with negative returns. The numbers below do not apply until their box is active.",
    "Con sólo <b>{n}+ operaciones</b> exigidas entra casi cualquier candidata: el repositorio se llena en segundos de candidatas con retorno negativo. Los números de abajo no se aplican hasta que se active su casilla."],
  "help.wr_impossible_title": ["A {pct}% win rate is not enough to make money",
                               "{pct}% de aciertos no alcanza para ganar dinero"],
  "help.wr_impossible": [
    "at 1:{rr}: break-even sits at <b>{be}%</b>. Below that, winning more often still loses money.",
    "con relación 1:{rr}: el punto de equilibrio está en <b>{be}%</b>. Por debajo de ahí, acertar más veces sigue dando pérdida."],
  "help.wr_ok": [
    "At 1:{rr}, break-even sits at <b>{be}%</b>, so the requirement is <b>{ventaja} points</b> of edge.",
    "Con relación 1:{rr} el equilibrio está en <b>{be}%</b>, así que se exigen <b>{ventaja} puntos</b> de ventaja."],
  "help.wr_high": ["That is a very high threshold: lowering it helps if nothing shows up.",
                   "Es un umbral muy alto: conviene bajarlo si no aparece nada."],
  "help.lots": [
    "Always <b>{lots}</b> lot(s), no matter what. The risk per trade stops being fixed: it depends on the volatility of the moment, because the stop moves with the ATR. In exchange, the volume is a round number that any broker accepts without recalculating anything — which is where some CFDs get stuck.",
    "Siempre <b>{lots}</b> lote(s), pase lo que pase. El riesgo por operación deja de ser fijo: depende de la volatilidad del momento, porque el stop se mueve con el ATR. A cambio, el volumen es un número redondo que cualquier broker acepta sin recalcular nada — que es donde algunos CFDs se traban."],
  "help.rr": [
    "The target is worth <b>{rr}×</b> the risk taken: <b>${gana}</b> on a win and <b>${pierde}</b> on a loss. Being right <b>{be}%</b> of the time is enough to break even. <br>The further the target, the less often it is reached: the generation has to find entries that clear that threshold.",
    "El objetivo vale <b>{rr}×</b> lo que se arriesga: gana <b>${gana}</b> al acertar y pierde <b>${pierde}</b> al fallar. Alcanza con acertar <b>{be}%</b> de las veces para empatar. <br>Cuanto más lejos el objetivo, menos veces se acierta: la generación tiene que encontrar entradas que superen ese umbral."],
  "note.full_history": [
    "Generating over <b>the whole</b> history: {desde} → {hasta} ({anios} years) · last price <b>{precio}</b>",
    "Generando sobre <b>todo</b> el historial: {desde} → {hasta} ({anios} años) · último precio <b>{precio}</b>"],
  "note.range": ["Generating over <b>{desde} → {hasta}</b> ({anios} years out of {lo} → {hi})",
                 "Generando sobre <b>{desde} → {hasta}</b> ({anios} años de {lo} → {hi})"],
  "note.split": [
    "Of that period, the generation sees the first <b>{mina}%</b> and the final <b>{valida}%</b> is reserved for validation.",
    "De ese período, la generación ve el <b>{mina}%</b> inicial y el <b>{valida}%</b> final queda reservado para validar."],
  "note.round_trip": ["Round trip costs <b>{abs}</b> in price units", "Ida y vuelta: <b>{abs}</b> de precio"],
  "note.match_broker": ["It must match the broker.", "Debe coincidir con el bróker."],
  "note.impossible_cost": ["Impossible cost: {pct}% per trade.", "Costo imposible: {pct}% por operación."],
  "note.impossible_cost_sub": [
    "That looks like another instrument's spread — with this, no strategy can win.",
    "Parece el spread de otro instrumento — con esto ninguna estrategia puede ganar."],
  "note.use_defaults": ["Use {mercado}'s", "Usar los de {mercado}"],
  "note.typical_ok": [
    "That is the typical spread on {mercado}: {spread}. Change it if the broker charges a different one.",
    "Es el spread típico de <b>{mercado}</b>: {spread}. Conviene cambiarlo si el bróker cobra otro."],
  "mine.sub_empty": ["Generate strategies over real data.", "Generar estrategias sobre datos reales."],
  "mine.no_data": ["Nothing to generate on yet", "Todavía no hay datos para generar"],
  "mine.no_data_help": ["Go to <b>Instruments</b> and download one — one click and it is ready.",
                        "Ir a <b>Instrumentos</b> y descargar uno — con un clic queda listo."],
  "mine.go_data": ["Go to Instruments", "Ir a Instrumentos"],
  /* La sección elegida no tiene ni un instrumento. Se dice cuál es la que
     falta, porque "no hay con qué minar" al lado de un SP500 cargado en la
     otra sección se lee como un error de la aplicación. */
  "mine.no_data_cripto": ["No perpetuals loaded yet", "Todavía no hay ningún perpetuo cargado"],
  "mine.no_data_cripto_help": [
    "The CFDs are still here — switching back to <b>CFDs</b> shows them again. To generate on crypto, go to <b>Instruments</b> and download a perpetual from Binance: one click and it is ready.",
    "Los CFDs siguen ahí — volver a <b>CFDs</b> para verlos. Para generar en cripto, ir a <b>Instrumentos</b> y descargar un perpetuo de Binance: con un clic queda listo."],
  "mine.no_data_cfd": ["No CFD instruments loaded yet", "Todavía no hay ningún CFD cargado"],
  "mine.no_data_cfd_help": [
    "The perpetuals are still here — switching back to <b>Crypto</b> shows them again. To generate on CFDs, go to <b>Instruments</b> and download an index, a pair or a metal: one click and it is ready.",
    "Los perpetuos siguen ahí — volver a <b>Cripto</b> para verlos. Para generar en CFDs, ir a <b>Instrumentos</b> y descargar un índice, un par o un metal: con un clic queda listo."],

  /* ------------------------------------------------------------ pantalla MINADO */
  "mine.sub": ["The generation continues until it has gathered the requested number of strategies.",
               "La generación continúa hasta reunir la cantidad de estrategias solicitada."],
  "mine.market": ["Market", "Mercado"],
  "mine.instrument": ["Instrument", "Instrumento"],
  "mine.timeframe": ["Timeframe", "Timeframe"],
  "mine.timeframe_hint": ["1-minute bars get grouped into this", "las velas M1 se agrupan a este TF"],
  "mine.direction": ["Direction", "Dirección"],
  "dir.long": ["Long only", "Largos"],
  "dir.short": ["Short only", "Cortos"],
  "dir.both": ["Both", "Ambos"],
  "mine.period": ["Period to generate on", "Período a generar"],
  "mine.from": ["From", "Desde"],
  "mine.to": ["To", "Hasta"],
  "mine.window": [
    "Starts on the <b>last {n} years</b> so the first generation does not take too long. This instrument has {total} years.",
    "Arranca en los <b>últimos {n} años</b> para que la primera generación no demore demasiado. Este instrumento tiene {total} años."],
  "mine.use_all": ["Use all {total} years", "Usar los {total} años"],
  "mine.oos": ["Keep a period for later", "Reservar un período para después"],
  "mine.oos_off": ["Off", "Desactivada"],
  // Vive adentro del paso de la data, pegado a las fechas: reservar un tramo
  // es partir en dos el periodo que se acaba de elegir, no un paso aparte al
  // final. Apagado de fabrica: reservar significa minar sobre
  // menos historia, y eso hace salir menos estrategias. La decision es del
  // usuario y por eso la explicacion vive adentro del paso, no en un tooltip.
  "oos.off": ["Off", "Desactivada"],
  "oos.on": ["On", "Activada"],
  "oos.sum_on": ["last {pct}% kept for later", "último {pct}% guardado para después"],
  "oos.how_much": ["How much to keep for later", "Cuánto reservar para después"],
  "oos.b_busca": ["generates here · {pct}%", "genera aquí · {pct}%"],
  "oos.b_guarda": ["never looks · {pct}%", "no mira · {pct}%"],
  "oos.what": [
    "The last <b>{pct}%</b> of the period is <b>reserved</b>: the generation never looks at it. Each strategy that passes is then run out-of-sample on that portion. If it also makes money there, it was not just describing the past.",
    "El último <b>{pct}%</b> del período queda <b>reservado</b>: la generación no lo mira nunca. Cada estrategia que pasa se ejecuta después sobre esa porción, fuera de muestra. Si gana también ahí, no estaba describiendo el pasado."],
  "oos.informa": [
    "It reports, it does not discard: nothing is thrown out for failing there. Note that the generation is left with less history, so fewer strategies come out.",
    "Informa, no descarta: nada se descarta por fallar ahí. Conviene tener en cuenta que la generación queda con menos historia, así que salen menos estrategias."],
  "mine.oos_split": ["Generate {mina}% · validate {valida}%", "Generar {mina}% · validar {valida}%"],
  "mine.oos_help": [
    "Splits the period in two: the generation only sees the first part, and every accepted strategy is re-run on the end, on data it <b>never saw</b>. The repository gains a column saying how much of the edge survives there — the best available reference for what to expect from the strategy going forward.",
    "Parte el período en dos: la generación usa sólo la parte inicial y cada estrategia aceptada se vuelve a ejecutar sobre el final, con datos que <b>nunca vio</b>. El repositorio suma una columna que dice cuánto de la ventaja se sostiene ahí — que es la mejor referencia disponible de qué esperar de la estrategia hacia adelante."],
  "mine.blocks": ["Building blocks", "Bloques"],
  "mine.triggers": ["Entry triggers", "Disparadores de entrada"],
  "mine.filters": ["Context filters", "Filtros de contexto"],
  "mine.complexity": ["Rule complexity", "Complejidad de las reglas"],
  "mine.complexity_hint": ["how many context filters a strategy may stack at once",
                           "cuántos filtros de contexto puede exigir una estrategia al mismo tiempo"],
  "mine.risk": ["Risk and exits", "Riesgo y salidas"],
  "mine.size_risk": ["% of capital at risk", "Riesgo % del capital"],
  "mine.size_lots": ["Fixed lots", "Lotes fijos"],
  "mine.risk_per_trade": ["Risk per trade", "Riesgo por operación"],
  "mine.volume": ["Volume per trade", "Volumen por operación"],
  "mine.lots": ["lots", "lotes"],
  "mine.rr": ["Risk / reward", "Relación riesgo / beneficio"],
  "mine.stop_note": [
    "The stop <b>distance</b> is not configured by hand: it is measured in volatility (ATR) and the generation finds each strategy the multiple that suits it, between 1× and 5×. That is why it works the same on any instrument.",
    "La <b>distancia</b> del stop no se configura: se mide en volatilidad (ATR) y la generación le busca a cada estrategia el múltiplo que le sirve, entre 1× y 5×. Por eso funciona igual en cualquier instrumento."],
  "mine.costs": ["Broker costs", "Costos del broker"],
  "mine.costs_cripto": ["Exchange costs", "Costos del exchange"],
  "run.ocupado": ["The server is busy (validating or generating). It will try again in 30 seconds.", "El servidor está ocupado (validando o generando). Vuelve a intentar en 30 segundos."],
  "run.ocupado_largo": ["The server runs one heavy job at a time and it is busy right now, validating or generating. The generation will start by itself in 30 seconds; the app stays usable meanwhile.", "El servidor ejecuta un trabajo pesado por vez y ahora está ocupado, validando o generando. La generación arranca sola en 30 segundos; la aplicación se puede seguir usando mientras tanto."],
  "wf.avance": ["window {k} of {n} · candidate {i} of {m}", "ventana {k} de {n} · candidata {i} de {m}"],
  "wf.avance_baraja": ["resampling the trades", "remuestreando las operaciones"],
  "wf.avance_prepara": ["preparing", "preparando"],
  "mine.spread": ["Spread", "Spread"],
  "mine.slippage": ["Slippage", "Slippage"],
  "mine.commission": ["Commission % per side", "Comisión % lado"],
  "mine.swap": ["Overnight cost % per year", "Costo de mantener % anual"],
  "mine.swap_help": ["What the broker charges per year for holding a position open (swap or overnight financing). It is on the symbol spec sheet. Leave it at 0 if it is unknown — the results will be slightly optimistic. Perpetual futures ignore it: they use their own funding series.", "Lo que cobra el bróker por año por dejar una posición abierta (swap o financiación). Está en la ficha del símbolo. Dejarlo en 0 si se desconoce — los resultados quedan un poco optimistas. Los perpetuos lo ignoran: usan su propia serie de funding."],
  /* ---------------------------------------- el chequeo del capital inicial
     Cambiar el capital no mueve ninguna metrica: el riesgo porcentual escala
     todo por igual. Lo que si cambia es el TAMANO de la posicion, y ahi esta
     lo que importa: por debajo del minimo del broker, el minimo manda. */
  "mine.min_lot": ["Broker minimum (lots)", "Mínimo del bróker (lotes)"],
  "cap.fits": ["Position size", "Tamaño de la posición"],
  "cap.too_small": ["Position size", "Tamaño de la posición"],
  "cap.detail": [
    "The risk is {plata} per trade, which on {mercado} is a position of about <b>{lotes} lots</b>.",
    "El riesgo es de {plata} por operación, que en {mercado} equivale a una posición de unos <b>{lotes} lotes</b>."],
  "cap.forced": [
    "If the broker does not go below {minimo} lots on this instrument, each trade will risk more than the {pedido}% requested. Worth checking before deploying it.",
    "Si el bróker no baja de {minimo} lotes en este instrumento, cada operación va a arriesgar más del {pedido}% solicitado. Conviene comprobarlo antes de ponerla a operar."],
  "cap.check_broker": [
    "The minimum and the contract size are references: check them against the actual broker.",
    "El mínimo y el tamaño de contrato son referencias: conviene comprobarlos contra el propio bróker."],

  "mine.capital": ["Capital", "Capital"],
  "mine.accept": ["Acceptance filters", "Filtros de aceptación"],
  "mine.accept_help": [
    "A candidate enters the repository only if it meets EVERY filter selected. Enable only the relevant ones: each additional filter slows the generation down.",
    "Una candidata entra al repositorio sólo si cumple TODOS los filtros seleccionados. Conviene activar únicamente los relevantes: cada filtro adicional vuelve más lenta la generación."],
  "mine.method": ["Generation method", "Método de generación"],
  "mine.method_random": ["Random (explores widely)", "Aleatorio (explora amplio)"],
  "mine.method_evolution": ["Evolutionary (improves over generations)",
                            "Evolutivo (mejora por generaciones)"],
  "mine.sort_by": ["Sort the repository by", "Ordenar el repositorio por"],
  "mine.sort_score": ["Score (robustness)", "Score (robustez)"],
  "mine.cap": ["Safety cap", "Tope de seguridad"],
  "mine.cap_hint": ["most candidates before stopping", "candidatas máximas antes de detenerse"],
  "mine.want": ["Generate", "Generar"],
  "mine.want_sub": ["strategies that meet<br>the filters", "estrategias que<br>cumplan los filtros"],
  "mine.start": ["Start generating", "Iniciar generación"],
  "mine.pause": ["Pause", "Pausar"],
  "mine.resume": ["Resume", "Continuar"],
  "mine.stop": ["Stop", "Detener"],

  /* -------------------------------------------- corrida en curso y resultado */
  "run.in_bank": ["in the repository", "en el repositorio"],
  "run.tested": ["Evaluated", "Evaluadas"],
  "run.pie": ["{n} evaluated", "{n} evaluadas"],
  "run.progreso": ["{k}/{meta} in the repository · {n} evaluated", "{k}/{meta} en el repositorio · {n} evaluadas"],
  "run.done": ["Generation finished", "Generación terminada"],
  "run.searching": ["Generating strategies", "Generando estrategias"],
  "run.pausada": ["Paused — press Resume to continue", "En pausa — presionar Continuar para reanudar"],
  "run.trying": ["evaluating candidate #{n}", "evaluando candidata #{n}"],
  "run.preparing": ["preparing indicators…", "preparando indicadores…"],
  "run.until": ["It does not stop until <b>{goal}</b> clear the threshold — <b>{faltan}</b> to go.",
                "No se detiene hasta reunir <b>{goal}</b> que superen el umbral — faltan <b>{faltan}</b>."],
  "run.until_cap": ["Evaluating candidates up to <b>{n}</b>.", "Evaluando candidatas hasta llegar a <b>{n}</b>."],
  "run.seed": ["seed <b>{seed}</b> reproduces this run", "semilla <b>{seed}</b> reproduce esta ejecución"],
  "run.profitable": ["Profitable", "Con ganancia"],
  "run.hit_rate": ["Hit rate", "Tasa de éxito"],
  "run.duration": ["Duration", "Duración"],
  "run.elapsed": ["Elapsed", "Transcurrido"],
  "run.eta": ["Approx. left", "Falta aprox."],
  "run.rate": ["Pace", "Ritmo"],
  "run.per_sec": ["accepted/s", "acept./s"],
  "run.por_seg": [" accepted/s", " acept./s"],
  "run.cada": [" every {s}", " cada {s}"],
  "run.best": ["Best score", "Mejor score"],
  "run.best_so_far": ["Best so far", "Mejor hasta ahora"],
  "run.preparando": ["Preparing candles and indicators…", "Preparando velas e indicadores…"],
  "run.listo": ["{n} strategies generated.", "{n} estrategias generadas."],
  "wf.quedo": ["{nombre} is now in {donde}.", "{nombre} quedó en {donde}."],
  "wf.ir_a_ver": ["Go and see it", "Ir a verla"],
  "run.open_full": ["Open the full analysis", "Ver análisis completo"],
  "run.history": ["How the best score improved", "Evolución del mejor score"],
  "run.history_hint": ["how the generation improved over time", "cómo fue mejorando la generación"],
  "bank.guardar_todas": ["Send all {n} to validation", "Enviar las {n} a validación"],
  "bank.guardadas_n": ["{n} sent to validation. They are validated on demand: nothing runs on its own.", "{n} enviadas a validación. Se validan a pedido: nada se ejecuta automáticamente."],
  "run.bank_hint": [
    "{n} strategies ranked by score (robustness, not profit) · click any of them for the full analysis",
    "{n} estrategias ordenadas por score (robustez, no rentabilidad) · clic en cualquiera para analizarla a fondo"],
  "run.stopped": [
    "<b>The generation was stopped.</b> The {n} strategies already in the repository are below, ready to inspect or export.",
    "<b>Generación detenida.</b> Las {n} estrategias que ya habían entrado al repositorio siguen aquí abajo, listas para inspeccionar o exportar."],
  "run.exhausted": [
    "<b>The possible combinations ran out</b> with the blocks selected. Select more blocks in section 2 or raise the rule complexity to widen the space.",
    "<b>Se agotaron las combinaciones posibles</b> con los bloques seleccionados. Seleccionar más bloques en la sección 2 o subir la complejidad para ampliar el espacio."],
  "run.hit_cap": [
    "<b>The {tope}-candidate safety cap was reached</b> with {n} of {goal} strategies. The filters are very demanding for this market: disable one in section 5, change the exits in section 3, or raise the cap under Advanced to keep generating for longer.",
    "<b>Se llegó al tope de seguridad de {tope} candidatas</b> con {n} de {goal} estrategias. Los filtros son muy exigentes para este mercado: conviene desactivar alguno en la sección 5, cambiar las salidas en la 3, o subir el tope en Avanzado para que la generación siga más tiempo."],
  "run.reached": [
    "<b>Goal reached.</b> {goal} strategies that clear every filter, obtained by evaluating {probadas} candidates in {tiempo}.",
    "<b>Objetivo cumplido.</b> {goal} estrategias que cumplen todos los filtros, obtenidas evaluando {probadas} candidatas en {tiempo}."],
  "run.split_note": [
    "<b>Checked out-of-sample.</b> The generation used {desde} → {hasta} ({velas} bars) and every strategy was re-run on {odesde} → {ohasta} ({ovelas} bars) that it never saw. The <b>{columna}</b> column is the one that says whether the edge was real.",
    "<b>Validado fuera de muestra.</b> La generación usó {desde} → {hasta} ({velas} velas) y cada estrategia se volvió a ejecutar sobre {odesde} → {ohasta} ({ovelas} velas) que nunca vio. La columna <b>{columna}</b> es la que indica si la ventaja era real."],

  "run.paused_toast": ["Paused — the current progress is kept, nothing is lost",
                       "En pausa — se conserva el punto alcanzado, no se pierde nada"],
  "run.resumed_toast": ["The generation continues", "Continúa la generación"],
  "run.few_passed": ["{n} were evaluated and only {kept} cleared the filters",
                     "Se evaluaron {n} y sólo {kept} superaron los filtros"],
  "mine.need_trigger": ["Select at least one entry trigger", "Seleccionar al menos un disparador de entrada"],
  "err.dataset_gone": ["The instrument it was generated on is no longer in the workspace",
                       "El instrumento con el que se generó ya no está en el workspace"],
  "err.no_backend": ["Could not reach the backend", "No se pudo conectar con el backend"],
  "export.installed": ["Robot installed in {terminal} — open it and compile with F7",
                       "Robot instalado en {terminal} — abrirlo y compilar con F7"],
  "export.bot_saved": ["Bot file saved", "Archivo del bot guardado"],
  "insp.bingx_btn": ["Trade it on Binance", "Operarla en Binance"],
  /* LA GUIA DE "OPERARLA SOLA" EMPIEZA POR BOTIQUANT Y BINANCE. Antes era
     una guía de TradingView→BingX; hoy el camino principal es el bot de la
     aplicación contra la demo de Binance (Operar → Claves → Encender), y el
     webhook queda como alternativa para quien no puede dejar la computadora
     prendida. Binance no recibe alertas de TradingView directamente, y eso
     se dice, no se esconde. */
  "bx.title": ["Run this strategy automatically", "Operar esta estrategia de forma automática"],
  "bx.intro": [
    "The simplest path is to let Botiquant run it against the Binance demo account. TradingView with a webhook is the alternative for when the computer cannot stay on.",
    "Lo más simple es dejar que Botiquant la ejecute contra la cuenta demo de Binance. TradingView con webhook es la alternativa para cuando la computadora no puede quedar encendida."],
  "bx.app_t": ["In Botiquant, on the Binance demo account", "En Botiquant, con la cuenta demo de Binance"],
  "bx.a1_t": ["Save it to My strategies", "Guardarla en Mis estrategias"],
  "bx.a1_d": [
    "Only saved strategies can be deployed: the bot needs the instrument, the timeframe and the costs it was measured with.",
    "Sólo se activan las guardadas: el bot necesita el instrumento, la temporalidad y los costos con los que se midió."],
  "bx.a2_t": ["Paste the Binance demo keys under Trading → Exchange keys", "Pegar las claves demo de Binance en Operación → Claves de exchange"],
  "bx.a2_d": [
    "They are created on demo.binance.com, never on binance.com. Botiquant stores them encrypted on this computer and only accepts Binance in demo.",
    "Se crean en demo.binance.com, nunca en binance.com. Botiquant las guarda cifradas en esta computadora y sólo acepta Binance en demo."],
  "bx.a3_t": ["Deploy it under Trading → Bot", "Activarla en Operación → Bot"],
  "bx.a3_d": [
    "Botiquant checks every closed candle and sends the orders, with the stop and the take profit placed on the exchange. The computer has to stay on.",
    "Botiquant revisa cada vela cerrada y envía las órdenes, con el stop y el take profit puestos en el exchange. La computadora tiene que quedar encendida."],
  "bx.ir_operar": ["Go to Trading", "Ir a Operación"],
  "bx.alt_t": ["Alternative: TradingView with a webhook", "Alternativa: TradingView con webhook"],
  "bx.alt_sub": [
    "For when the computer cannot stay on. Binance does not receive TradingView alerts directly: this path needs an exchange with signal trading, such as BingX or Bybit, or a webhook bridge.",
    "Para cuando la computadora no puede quedar encendida. Binance no recibe alertas de TradingView directamente: este camino necesita un exchange con trading de señales, como BingX o Bybit, o un puente de webhooks."],
  "bx.p1_t": ["Get a TradingView plan with alerts", "Conseguir un plan de TradingView con alertas"],
  "bx.p1_d": ["Webhooks are not in the free plan: Essential or higher is required. This is the only cost of the whole setup, and it is worth knowing before starting.", "Los webhooks no están en el plan gratuito: hace falta Essential o superior. Es el único costo de todo esto, y conviene saberlo antes de empezar."],
  "bx.p2_t": ["Paste the strategy into the Pine Editor", "Pegar la estrategia en el Pine Editor"],
  "bx.p2_d": ["Open the chart for the symbol, paste the exported script and add it to the chart. Compare the Strategy Tester against the numbers Botiquant measured before going any further.", "Abrir el gráfico del símbolo, pegar el script exportado y agregarlo al gráfico. Comparar el Strategy Tester contra los números que midió Botiquant antes de seguir."],
  "bx.p3_t": ["Copy the webhook URL and message from the exchange", "Copiar la URL y el mensaje del exchange"],
  "bx.p3_d": ["In the exchange's signal trading screen, on the USD-M perpetual chart, the exchange provides a URL and a message that belong to that account alone. That URL must never be shared.", "En la pantalla de trading de señales del exchange, sobre el gráfico de perpetuos USD-M, el exchange entrega una URL y un mensaje que pertenecen sólo a esa cuenta. Esa URL nunca se comparte."],
  "bx.p4_t": ["Paste the exchange's messages into the strategy settings", "Pegar los mensajes del exchange en la estrategia"],
  "bx.p4_d": ["The script has three boxes: open long, open short and close. The exchange's message goes into each one. Botiquant does not invent that format on purpose: a made-up message produces orders the exchange discards silently.", "El script tiene tres casillas: abrir largo, abrir corto y cerrar. En cada una va el mensaje del exchange. Botiquant no inventa ese formato a propósito: un mensaje inventado produce órdenes que el exchange descarta en silencio."],
  "bx.p5_t": ["Create the alert with the webhook", "Crear la alerta con el webhook"],
  "bx.p5_d": ["New alert on the strategy, condition \"Order fills only\", message {{strategy.order.alert_message}}, and the URL under Notifications. From then on it trades automatically.", "Alerta nueva sobre la estrategia, condición \"Order fills only\", mensaje {{strategy.order.alert_message}}, y la URL en Notificaciones. Desde ahí opera de forma automática."],
  "bx.demo_t": ["Demo first, always", "Primero en demo, siempre"],
  "bx.demo_d": [
    "Botiquant only trades Binance in demo, on purpose. Running it there for a few weeks is what shows whether it does live what it did in the backtest, and it costs nothing to find out.",
    "Botiquant sólo opera Binance en demo, a propósito. Ejecutarla ahí unas semanas es lo que muestra si hace en vivo lo mismo que hizo en el backtest, y no cuesta nada averiguarlo."],
  "bx.compara": ["One warning worth repeating: the Pine script is a translation of the strategy into another language. Compare TradingView's Strategy Tester against Botiquant's numbers over the same dates. If they differ a lot, do not deploy it.", "Un aviso que vale repetir: el script de Pine es una traducción de la estrategia a otro lenguaje. Comparar el Strategy Tester de TradingView contra los números de Botiquant en las mismas fechas. Si difieren mucho, no activarla."],
  "insp.bingx_hint": ["How to leave it running on the Binance demo account", "Cómo dejarla operando en la cuenta demo de Binance"],
  "insp.bingx_solo_cripto": ["Only for perpetual futures: a crypto exchange does not trade indices or metals", "Sólo para perpetuos: un exchange de cripto no opera índices ni metales"],
  "export.mq5_saved": ["Expert Advisor saved — copy it to MQL5/Experts and compile",
                       "Expert Advisor guardado — copiarlo a MQL5/Experts y compilar"],
  "export.pine_saved": ["Pine saved — or use Copy and paste it into TradingView",
                        "Pine guardado — o usar Copiar y pegarlo en TradingView"],
  "export.pick_terminal": ["There are {n} MetaTraders installed. Send it to:",
                           "Hay {n} MetaTrader instalados. Enviarlo a:"],
  "export.copy_failed": ["The system would not allow copying, so it was saved as a file",
                         "El sistema no permitió copiar, así que se guardó como archivo"],
  "insp.no_range": [
    "<b>This strategy was saved without recording its period.</b> What is shown here was calculated over the <b>whole history</b> of the instrument, so it may not match the metrics in the list, which came from the window it was generated on. Generate it again and save it anew so the two are tied together.",
    "<b>Esta estrategia se guardó sin registrar el período.</b> Lo que se ve aquí se calculó sobre <b>toda la historia</b> del instrumento, así que puede no coincidir con las métricas de la lista, que salieron de la ventana en la que se generó. Conviene volver a generarla y guardarla de nuevo para que queden vinculadas."],

  "run.locked": [
    "Settings are frozen while it generates. Changing the criteria while looking at the results would be choosing them to fit this particular history. <b>Stop</b> to adjust and generate again.",
    "Configuración congelada durante la generación. Cambiar los criterios viendo los resultados sería elegirlos a medida del histórico. <b>Detener</b> para ajustar y generar de nuevo."],
  /* Cuando el histórico no tiene funding. Se dice el número y no los nombres:
     lo que importa es que la corrida usó menos bloques de los pedidos. */
  "vara.sin_funding": [
    "{n} funding block(s) were left out: this instrument has no funding — perpetuals charge it, a CFD does not.",
    "Quedaron fuera {n} bloque(s) de funding: este instrumento no lo tiene — lo cobran los perpetuos, un CFD no."],
  "vara.required": ["Required", "Se exigió"],
  "vara.min_trades": ["at least <b>{n}</b> trades", "mínimo <b>{n}</b> operaciones"],
  "vara.none": [
    "<b>No quality filters.</b> The only requirement was {unico}, so almost any candidate gets in — including the ones with negative returns. Select what matters under <b>Acceptance filters</b> and generate again.",
    "<b>Sin filtros de calidad.</b> Lo único que se exigió fue {unico}, así que entra casi cualquier candidata — incluidas las de retorno negativo. Conviene seleccionar lo relevante en <b>Filtros de aceptación</b> y generar de nuevo."],
  "busca.tested": ["candidates evaluated", "candidatas evaluadas"],
  "busca.accepted": ["accepted", "aceptadas"],
  "busca.why": ["Why they get rejected", "Por qué se descartan"],
  "busca.too_few_trades": ["too few trades", "pocas operaciones"],
  "busca.foot": [
    "The ones that clear the threshold show up here. The generation can be left running.",
    "Las que superan el umbral van apareciendo aquí. La generación puede quedar en ejecución."],

  /* ------------------------------------------------------------- Monte Carlo */
  "mc.sub": ["How much of the result was the strategy, and how much was the order the trades came in.",
             "Cuánto del resultado fue la estrategia, y cuánto fue el orden en que salieron las operaciones."],
  "mc.head": [
    "A strategy that won may have won because of the order its trades came in. Here they are resampled a thousand times to see which one remains robust.",
    "Una estrategia que ganó pudo ganar por el orden en que le salieron las operaciones. Aquí se remuestrean mil veces para ver cuál conserva la ventaja."],
  "mc.empty": ["Nothing to simulate yet", "Todavía no hay nada que simular"],
  "mc.empty_help": [
    "When a generation finishes, its strategies show up here to be put under pressure and see which one withstands a bad run best.",
    "Cuando termina una generación, sus estrategias aparecen aquí para someterlas a presión y ver cuál resiste mejor una racha en contra."],
  "mc.pick": ["Which strategies to compare", "Qué estrategias comparar"],
  "mc.pick_hint": [
    "{n} available · from the saved ones and the repository · select several to see which one remains most robust",
    "{n} disponibles · de las guardadas y del repositorio · seleccionar varias para ver cuál resiste mejor"],
  "mc.title": ["How stable is this result?", "¿Qué tan estable es este resultado?"],
  "mc.title_hint": ["the same trades, in a different order, a thousand times each",
                    "las mismas operaciones, en otro orden, mil veces cada una"],
  "mc.what": [
    "<b>What this is.</b> The <i>order</i> the trades arrive in changes the path: three losses in a row at the start leave the account somewhere very different than the same three at the end. This takes the strategy's real trades and resamples them a thousand times, to show the range of outcomes it lands in and how deep the drawdown can get along the way.",
    "<b>Qué es esto.</b> El <i>orden</i> en que llegan las operaciones cambia el recorrido: tres pérdidas seguidas al principio dejan la cuenta en un lugar muy distinto que las mismas tres al final. Esto toma las operaciones reales de la estrategia y las remuestrea mil veces, para mostrar en qué rango de resultados cae y qué tan profundo puede ser el drawdown en el camino."],
  "mc.what_not": [
    "<b>What this does NOT answer.</b> The trades are resampled over the same period the strategy was generated on, so this measures how much depends on the order — not whether the edge will exist next year. That is what the out-of-sample check is for, under Advanced in the generation: it reserves a final window and never lets the generation look at it.",
    "<b>Qué NO contesta esto.</b> Las operaciones se remuestrean sobre el mismo período donde se generó la estrategia, así que esto mide cuánto depende del orden — no si la ventaja va a existir el año que viene. Para eso está la validación fuera de muestra, en la sección Avanzado de la generación: reserva una ventana final y no la deja mirar durante la generación."],
  "mc.start_above": [
    "<b>Start at the top:</b> select the strategies to compare. Several can be selected at once and all of them are simulated.",
    "<b>Comenzar por arriba:</b> seleccionar las estrategias a comparar. Se pueden elegir varias y se simulan todas."],
  "mc.simulate": ["Simulate {n} strategies", "Simular {n} estrategias"],
  "mc.simulating": ["Simulating…", "Simulando…"],
  "mc.champion": ["The most robust one", "La que mejor resiste"],
  "mc.wins_in": [
    "It wins in <b>{n} out of every 100</b> ways its trades could have come out.",
    "Gana en <b>{n} de cada 100</b> formas en que le podrían haber salido las operaciones."],
  "mc.cost": [
    "And what has to be tolerated to obtain it: a drawdown of up to <b>{dd}%</b>, and some window where the account is at {peor} having started with {inicial}. That is not what will happen — it is the lower edge of normal.",
    "Y lo que hay que estar dispuesto a tolerar para conseguirlo: un drawdown de hasta <b>{dd}%</b>, y alguna ventana en que la cuenta quede en {peor} habiendo empezado con {inicial}. No es lo que va a pasar — es el borde inferior de lo normal."],
  "mc.see_full": ["See the full simulation", "Ver la simulación completa"],
  "mc.side_by_side": ["All of them, side by side", "Todas, una al lado de la otra"],
  "mc.side_hint": ["{n} simulations of each · click any of them for its full simulation",
                   "{n} simulaciones de cada una · clic en cualquiera para ver su simulación completa"],
  "mc.c_wins": ["Wins in", "Gana en"],
  "mc.c_wins_help": [
    "In how many of the thousand possible resamples it ended up making money. It is the criterion they are sorted by.",
    "En cuántos de los mil remuestreos posibles terminó ganando dinero. Es el criterio por el que están ordenadas."],
  "mc.c_typical": ["Typical equity", "Capital típico"],
  "mc.c_endure": ["Tolerance required", "Tolerancia requerida"],
  "mc.c_endure_help": [
    "The drawdown in the worst 5% of simulations. It is not what will happen: it is what has to be tolerated.",
    "El drawdown del 5% de simulaciones peores. No es lo que va a pasar: es lo que hay que estar dispuesto a tolerar."],
  "mc.c_bad": ["Bad case", "Mal escenario"],
  "mc.c_bad_help": [
    "In the bad case, what is left. It is the lower edge of normal, not an expected loss.",
    "En el mal escenario, con cuánto queda la cuenta. Es el borde inferior de lo normal, no una pérdida esperada."],
  "mc.c_ruin": ["Ruin risk", "Riesgo de ruina"],
  "mc.c_ruin_help": [
    "Chance of losing 30% of the capital at some point. This one is a genuine warning.",
    "Probabilidad de llegar a perder el 30% del capital en algún momento. Esto sí es una alerta."],
  "mc.v_risky": ["Risky", "Riesgosa"],
  "mc.v_risky_sub": [
    "It remains robust in general, but in {pct}% of scenarios it ends up losing a lot. That is what to look at before anything else.",
    "Resiste bien en general, pero en {pct}% de los escenarios llega a perder mucho. Eso es lo primero que hay que mirar."],
  "mc.v_solid": ["Solid", "Sólida"],
  "mc.v_solid_sub": [
    "It wins in the vast majority of possible resamples: the result holds whatever order the trades arrive in.",
    "Gana en la enorme mayoría de los remuestreos posibles: el resultado se sostiene venga en el orden que venga."],
  "mc.v_holds": ["Remains robust", "Resiste"],
  "mc.v_holds_sub": [
    "It wins in most resamples. It depends somewhat on the order the trades come in, but it stands.",
    "Gana en la mayoría de los remuestreos. Depende algo del orden en que salgan las operaciones, pero se sostiene."],
  "mc.v_edge": ["On the edge", "Al filo"],
  "mc.v_edge_sub": [
    "It wins about as often as it loses: with this one the order the trades arrive in weighs heavily on the outcome.",
    "Gana casi tantas veces como pierde: con ésta el orden en que lleguen las operaciones pesa mucho en el resultado."],
  "mc.v_fragile": ["Fragile", "Frágil"],
  "mc.v_fragile_sub": [
    "It loses in more than half of the possible resamples: the backtest landed on one of its better orders.",
    "Pierde en más de la mitad de los remuestreos posibles: el backtest cayó en uno de sus órdenes más favorables."],
  "mc.simulation": ["Simulation", "Simulación"],
  "mc.sims_of": ["{sims} simulations of {ops} trades", "{sims} simulaciones de {ops} operaciones"],
  "mc.ci90": [
    "Out of every 100 times this system ran, in 90 the final equity would land between <b>{bajo}</b> and <b>{alto}</b>. That range is the honest answer to “how much can it make”: the single number in the backtest was just one of the ones inside it.",
    "De cada 100 veces que se ejecutara este sistema, en 90 el capital final caería entre <b>{bajo}</b> y <b>{alto}</b>. Ese rango es la respuesta honesta a “cuánto puede rendir”: el número único del backtest era sólo uno de los que había adentro."],
  "mc.band": [
    "The band shows where the equity lands in 90% of the simulations. The middle line is the typical path.",
    "La banda muestra dónde cae el capital en el 90% de las simulaciones. La línea del medio es el recorrido típico."],
  "mc.finals": ["How the final outcomes spread", "Cómo se distribuyen los resultados finales"],
  "mc.drawdowns": ["And the maximum drawdowns", "Y los drawdowns máximos"],

  /* ---------------------------------------------------------------- databank */
  "bank.sub": ["Everything generated, run by run.", "Todo lo generado, ejecución por ejecución."],
  "bank.empty": ["The repository is empty", "El repositorio está vacío"],
  "bank.empty_help": [
    "Every generation that finishes leaves its strategies here with the instrument, the timeframe and the filters they were found under. They accumulate: generating again no longer wipes what came before.",
    "Cada generación que termina deja aquí sus estrategias con el instrumento, la temporalidad y los filtros con los que se encontraron. Se acumulan: generar de nuevo ya no borra lo anterior."],
  "bank.count": ["{n} strategies from {corridas} runs.", "{n} estrategias de {corridas} ejecuciones."],
  "bank.count_run": ["{n} strategies in this run · {total} in the whole repository.",
    "{n} estrategias en esta ejecución · {total} en todo el repositorio."],
  "bank.almost_full": ["almost full", "casi lleno"],
  "bank.capacity": ["capacity", "capacidad"],
  "bank.runs": ["Runs", "Ejecuciones"],
  "bank.runs_hint": [
    "each generation kept the settings that produced it · click to see only its own",
    "cada generación quedó con la configuración que la produjo · clic para ver sólo la suya"],
  "bank.all": ["All", "Todas"],
  "bank.all_strategies": ["Every strategy", "Todas las estrategias"],
  "bank.in_view": ["{n} in view · click a row to analyse it", "{n} a la vista · clic en una fila para analizarla"],
  "bank.in_view_of": ["{n} of {hay} in view · click a row to analyse it",
    "{n} de {hay} a la vista · clic en una fila para analizarla"],
  "bank.load_more": ["Show more", "Ver más"],
  /* Las busquedas que no encontraron nada se conservan como registro —dicen que
     con esa vara ese mercado no da— pero agrupadas: con quince, la pantalla se
     llenaba de burbujas iguales y parecia que algo estaba roto. */
  "bank.viejas": ["{n} older runs", "{n} ejecuciones anteriores"],
  "bank.vacias": ["{n} with no results", "{n} sin resultados"],
  "bank.buscar": ["Filter by name or block\u2026", "Filtrar por nombre o bloque\u2026"],
  "bank.filtradas": ["{n} of {total} shown", "{n} de {total} a la vista"],
  "bank.sin_coincidencias": ["Nothing matches \u201c{q}\u201d", "Nada coincide con \u201c{q}\u201d"],
  /* Exportar en masa. Reemplaza abrir cada ficha, esperar el recalculo del
     backtest y exportar, una por una. */
  "bank.export_all": ["Export to MetaTrader", "Exportar a MetaTrader"],
  "bank.exporting": ["Exporting {i} of {n}\u2026", "Exportando {i} de {n}\u2026"],
  "bank.exported": ["{n} robots saved in {carpeta}", "{n} robots guardados en {carpeta}"],
  "bank.exported_mt5": ["{n} robots installed in {terminal}",
                        "{n} robots instalados en {terminal}"],
  "bank.export_failed": ["Could not export: {nombres}", "No se pudieron exportar: {nombres}"],
  "bank.risk": ["risk", "riesgo"],
  "bank.no_results": ["no results", "sin resultados"],
  "bank.no_filters": ["no filters", "sin filtros"],
  "bank.searched": ["Evaluated", "Evaluó"],
  "bank.found": ["Found", "Encontró"],
  "bank.remaining": ["{n} left", "quedan {n}"],
  "bank.took": ["Took", "Tardó"],
  "bank.ended": ["Ended", "Terminó"],
  "bank.seed": ["Seed", "Semilla"],
  "bank.bar": ["Threshold", "Umbral"],
  "bank.run": ["Run", "Ejecución"],
  "bank.rank_help": ["The rank the generation gave it, by score",
                     "El orden que le dio la generación, por score"],
  "ended.completa": ["complete", "completa"],
  "ended.detenida": ["stopped", "detenida"],
  "ended.sin llegar": ["fell short", "sin llegar"],
  "bank.repeat": ["Repeat these settings", "Repetir esta configuración"],
  "bank.delete_run": ["Delete the whole run", "Borrar la ejecución entera"],
  "bank.repeat_note": [
    "Repeating does not give the same strategies: the seed is random and each generation explores different combinations. Two identical runs that perform differently are generation variance, not one configuration being better than the other.",
    "Repetir no da las mismas estrategias: la semilla es aleatoria y cada generación explora otras combinaciones. Dos ejecuciones iguales que rinden distinto son varianza de la generación, no una configuración mejor que la otra."],
  "bank.confirm_delete_run": [
    "Delete the run {nombre} and its {n} strategies?\n\nThe ones already copied to My strategies are untouched.",
    "¿Borrar la ejecución {nombre} y sus {n} estrategias?\n\nLas que ya se copiaron a Mis estrategias no se tocan."],
  "bank.run_deleted": ["Run deleted", "Ejecución borrada"],
  "bank.confirm_remove": ["Remove {n} strategies from the repository?",
                          "¿Quitar {n} estrategias del repositorio?"],
  "bank.sin_instrumento": ["deleted instrument", "instrumento borrado"],
  "bank.copied": ["Sent to validation: {n} — they also stay here", "Enviadas a validación: {n} — siguen también aquí"],
  "bank.ya_en_probar": ["in validation", "en validación"],
  "bank.ya_de_esas": ["{m} already in validation", "{m} ya en validación"],
  "bank.mandar_n": ["Send {n} to validation", "Enviar {n} a validación"],
  "bank.ya_estaban": [" · {m} were already there", " · {m} ya estaban"],
  "bank.ya_estaban_todas": ["All {m} were already in validation", "Las {m} ya estaban en validación"],
  /* --------------------------------------- las reglas, en palabras
     El operador de una condicion se lee como parte de una frase —"EMA(20)
     cruza arriba de EMA(60)"— asi que se traduce. El indicador y sus
     parametros NO: EMA(20) se llama igual en las dos lenguas y en MetaTrader. */
  "rule.cross_above": ["crosses above", "cruza arriba de"],
  "rule.cross_below": ["crosses below", "cruza abajo de"],
  "rule.rising": ["rising", "sube"],
  "rule.falling": ["falling", "baja"],

  /* La hora es lo que distingue una corrida de otra cuando el instrumento y
     la temporalidad se repiten, que es casi siempre. */
  "time.today": ["today {hora}", "hoy {hora}"],
  "time.yesterday": ["yesterday {hora}", "ayer {hora}"],

  /* Con nada tildado la barra dice para qué sirve, en vez de mostrar cuatro
     botones apagados. Un control deshabilitado no enseña nada; una frase sí. */
  /* ------------------------------------- las cuatro etapas de una candidata
     Los nombres importan más de lo que parece: son el vocabulario con el que
     alguien entiende qué hizo el programa. "Descartadas" y no "fallidas" —no
     fallaron, no llegaron a la vara que puso el usuario—, y "en el Databank"
     y no "aceptadas", porque lo que el usuario ve es dónde están. */
  "data.download_failed": ["Download failed: {motivo}", "Descarga fallida: {motivo}"],
  "run.stopping": ["Stopping…", "Deteniendo…"],
  "idle.last_run": ["The last generation", "La última generación"],
  "idle.see_last": ["See what it found", "Ver lo que encontró"],
  "insp.no_trades": ["No trades in this window.", "Ninguna operación en esta ventana."],
  "ms.midiendo": ["measuring the three periods…", "midiendo los tres períodos…"],
  /* El pie ya no repite las métricas: están en la tabla, al lado de las otras
     dos. Sólo queda de qué fechas a qué fechas es la curva que se está viendo. */
  "ms.periodo": ["Curve from {desde} to {hasta}.", "Curva de {desde} a {hasta}."],
  "state.built": ["built and evaluated", "construidas y evaluadas"],
  "state.discarded": ["discarded", "descartadas"],
  "state.kept": ["in the repository", "en el repositorio"],
  "state.saved": ["saved", "guardadas"],
  "state.removed": ["{n} removed", "{n} quitadas"],
  "state.rate": ["{n} of {total} cleared the threshold — {tasa}%",
                 "{n} de {total} superaron el umbral — {tasa}%"],

  "bank.sel_hint": ["Select rows to save or export several at once",
                    "Seleccionar filas para guardar o exportar varias a la vez"],
  "bank.removed": ["{n} out of the repository", "{n} fuera del repositorio"],
  /* De que corrida salio la fila que se esta mirando. Dice "del banco" y no
     "guardada" a proposito: todavia no lo esta, y confundirlas hace creer que
     ya se rescato algo que no. */
  "bank.from_bank": ["from the repository · {corrida} · risk {riesgo}",
                     "del repositorio · {corrida} · riesgo {riesgo}"],

  "run.stopped_kept": ["Stopped — {n} strategies, kept in the repository",
                       "Detenido — {n} estrategias, guardadas en el repositorio"],
  "run.kept": ["{n} strategies in {tiempo} — they went to the repository",
               "{n} estrategias en {tiempo} — quedaron en el repositorio"],

  "data.costs_fixed": [
    "Costs and exits adjusted to {mercado}: the previous spread was {pct}% of the price",
    "Costos y salidas ajustados a {mercado}: el spread anterior era {pct}% del precio"],
  "data.exits_fixed": ["Exits adjusted to the scale of {mercado}",
                       "Salidas ajustadas a la escala de {mercado}"],

  "saved.added": ["{nombre} saved to My strategies",
                  "{nombre} guardada en Mis estrategias"],

  "bank.pruned": ["The repository was full: the {n} oldest runs were dropped",
                  "El repositorio estaba lleno: se descartaron las {n} ejecuciones más antiguas"],
  "bank.cfg_loaded": ["Settings loaded — press Start", "Configuración cargada — presionar Iniciar"],
  "bank.cfg_loaded_missing": [
    "Settings loaded, but {mercado} is no longer in the workspace",
    "Configuración cargada, pero {mercado} ya no está en el workspace"],
  "bank.remove": ["Remove from repository", "Quitar del repositorio"],
  "bank.mixed_risk": [
    "<b>These runs have different risk settings.</b> <b>{anual}</b> and <b>{dd}</b> scale with the risk per trade, so across runs they sort by that dial and not by the strategy. <b>PF</b>, <b>{score}</b> and <b>{meses}</b> are ratios: those do compare.",
    "<b>Estas ejecuciones tienen riesgos distintos.</b> <b>{anual}</b> y <b>{dd}</b> escalan con el riesgo por operación, así que entre ejecuciones ordenan por esa perilla y no por la estrategia. <b>PF</b>, <b>{score}</b> y <b>{meses}</b> son proporciones: ésas sí comparan."],
  "bank.nothing_left": ["Nothing left in the repository.", "No queda nada en el repositorio."],
  "bank.saved_untouched": ["Whatever was saved is still in My strategies.",
                           "Las que se hayan guardado siguen en Mis estrategias."],
  "bank.run_found_none": ["This generation found none.", "Esta generación no encontró ninguna."],
  "bank.run_found_none_help": [
    "It evaluated {n} candidates on {mercado} and none cleared the threshold: <b>{vara}</b>.",
    "Evaluó {n} candidatas sobre {mercado} y ninguna superó el umbral: <b>{vara}</b>."],
  "bank.run_found_none_note": [
    "It stays on record anyway — this is the experiment worth not repeating by accident. Repeat the settings and loosen the filter that rejects the most.",
    "Queda registrada igual — es el experimento que conviene no repetir por olvido. Repetir la configuración y aflojar el filtro que más descarta."],
  "bank.you_removed": ["The {n} it had found were removed.", "Se le quitaron las {n} que había encontrado."],
  "bank.cagr_help": [
    "Annualised return. It scales with the risk per trade: it does not compare across runs with different risk.",
    "Rendimiento anualizado. Escala con el riesgo por operación: no se compara entre ejecuciones de distinto riesgo."],
  "bank.pf_help": [
    "Profit factor: dollars made per dollar lost. It does not depend on position size, so it compares well across runs.",
    "Profit factor: cuántos dólares ganó por cada dólar que perdió. No depende del tamaño de posición, así que compara bien entre ejecuciones."],
  /* El color de esta columna es información, así que la ayuda dice cuándo
     cambia. Un umbral que nadie puede leer es lo mismo que un umbral inventado. */
  "bank.dd_help": [
    "Largest drawdown from a peak. It scales with the risk per trade, same as the return — "
    + "so the colour is read against that risk: amber past 15% at 1% per trade, red past 25%.",
    "Drawdown máximo desde un pico. Escala con el riesgo por operación igual que el rendimiento — "
    + "por eso el color se lee contra ese riesgo: ámbar pasando 15% al 1% por operación, rojo pasando 25%."],

  /* ------------------------------------------------------- mis estrategias */
  /* PROBAR: la bajada dice qué se hace acá y qué es la prueba, en una
     frase. Las palabras del motor (walk-forward, Monte Carlo) no aparecen. */
  "saved.sub_probar": [
    "The retained candidates. Nothing runs on its own: select some and run the validation, or validate the ones that are missing. Each one comes back with a verdict: robust, partially robust or overfitted.",
    "Las candidatas retenidas. Ninguna se valida automáticamente: seleccionar algunas y ejecutar la validación, o validar las que faltan. Cada una vuelve con un veredicto: robusta, robustez parcial o sobreajustada."],
  "saved.que_es_t": ["What the validation does", "Qué hace la validación"],
  "saved.que_es": [
    "Two questions, and both are answered by numbers the strategy never had a chance to fit. <b>Does it still work where it never looked?</b> The history is cut into four windows; in each one the strategy re-tunes itself on the first part and is judged on the last part, blind. <b>How rough can the path get?</b> Its trades are resampled in a different order 1,000 times to see how deep the drawdown could have been. A robust verdict means it made money in most windows and kept most of its edge out-of-sample.",
    "Dos preguntas, y las dos se contestan con números que la estrategia nunca pudo acomodar. <b>¿Sigue funcionando donde no miró?</b> La historia se corta en cuatro ventanas; en cada una la estrategia se reajusta sobre la primera parte y se la juzga sobre la última, a ciegas. <b>¿Qué tan adverso puede ser el recorrido?</b> Sus operaciones se remuestrean en otro orden 1000 veces para ver qué tan profundo pudo ser el drawdown. Un veredicto robusto significa ganar en la mayoría de las ventanas y conservar la mayor parte de la ventaja fuera de muestra."],
  "saved.acc_encender": ["Deploy", "Activar"],
  "saved.acc_ver_robot": ["See robot", "Ver robot"],
  "saved.acc_retirar": ["Retire", "Retirar"],
  "saved.acc_exportar": ["To MetaTrader", "A MetaTrader"],
  "saved.retirar_motivo": ["Why retire \"{nombre}\"? One line, so it is not deployed again in six months.", "¿Por qué se retira \"{nombre}\"? Una línea, para no volver a activarla en seis meses."],
  "saved.retirada": ["Retired with its reason.", "Retirada con su motivo."],
  "saved.sub": ["{n} saved. They survive any new generation.",
                "{n} guardadas. Sobreviven a cualquier generación nueva."],
  "saved.sub_retiradas": ["{n} in play · {r} retired. They survive any new generation.",
                          "{n} en juego · {r} retiradas. Sobreviven a cualquier generación nueva."],
  /* La única pista de que el portafolio existe. Aparece recién con dos
     guardadas: con una sería vender algo que todavía no se puede hacer. */
  "saved.combinar": [
    "Select two or more to see how they behave together: whether they add up or they are the same bet twice.",
    "Seleccionar dos o más para ver cómo se comportan juntas: si se suman o son la misma apuesta repetida."],
  "saved.title": ["Saved", "Guardadas"],
  "saved.hint": ["click a row to analyse it again", "clic en una fila para volver a analizarla"],
  "saved.when": ["Saved", "Guardada"],
  "saved.confirm_delete": ['Delete "{nombre}"? This cannot be undone.',
                           '¿Borrar "{nombre}"? No se puede deshacer.'],
  "saved.deleted": ["Strategy deleted", "Estrategia borrada"],
  "saved.none": ["Nothing saved yet", "Todavía no hay ninguna guardada"],
  "saved.empty_sub": [
    "Saved strategies stay here, even after generating again with different filters.",
    "Las estrategias guardadas quedan aquí, aunque se genere de nuevo con otros filtros."],
  "saved.none_help": [
    "When the generation finds a useful one, open it and press <b>Save to My strategies</b>. It gets saved with its instrument, its timeframe and its costs, so it can be exported again months later without generating all over.",
    "Cuando la generación encuentre una que sirva, abrirla y usar <b>Guardar en Mis estrategias</b>. Se guarda con su instrumento, su timeframe y sus costos, así se puede volver a exportar meses después sin tener que generar de nuevo."],

  /* ------------------------------------------------------------- inspector */
  "insp.score_sub": ["how repeatable it looks, not how much it returned",
                     "qué tan repetible parece, no cuánto rindió"],
  "insp.metrics": ["Full metrics", "Métricas completas"],
  /* -------------------------------------- las tres vistas de la curva
     Aparecen solo cuando la corrida reservo un tramo. Antes la ficha abria
     mostrando el tramo de busqueda y no lo decia: una curva impecable que era
     la mitad que la estrategia ya conocia. */
  /* Los nombres del oficio, no la paráfrasis.

     Decían "Searched on / Never seen / Both together": lenguaje llano, elegido
     para que se entendiera sin jerga. El problema es que el paso que activa
     esto ya se llama "Out-of-sample check", y quien lo usa lo nombra así — con
     la app en castellano también. Dos nombres para lo mismo, en la misma
     pantalla, es peor que la jerga.

     Es la misma regla que rige para profit factor y drawdown: los términos del
     oficio no se traducen, se reconocen. La explicación en llano no se pierde,
     pasa al globito de cada pestaña. */
  "ms.is": ["In sample", "In sample"],
  "ms.oos": ["Out of sample", "Out of sample"],
  "ms.todo": ["Full period", "Período completo"],
  "ms.is_help": ["The window the generation looked at",
                 "La ventana que miró la generación"],
  "ms.oos_help": ["Reserved on purpose: the generation never saw it",
                  "Reservada a propósito: la generación nunca la vio"],
  "ms.todo_help": ["Both windows, end to end",
                   "Las dos ventanas, de punta a punta"],
  "ms.marca": ["from here on, never seen", "de aquí en adelante, nunca visto"],
  "ms.muy_corto": [
    "The reserved window is too short to re-run on its own — the indicators need more history than it has. Use 'Full period', or reserve a larger share next time.",
    "La ventana reservada es muy corta para ejecutarla sola: los indicadores necesitan más historia de la que tiene. Conviene usar 'Período completo', o reservar una porción más grande la próxima vez."],
  "ms.sin_curva": ["No curve for this window", "Sin curva para esta ventana"],
  "ms.resumen": [
    "{desde} → {hasta} · {cagr} a year · {dd}% drawdown · PF {pf} · {n} trades",
    "{desde} → {hasta} · {cagr} anual · {dd}% de drawdown · PF {pf} · {n} operaciones"],
  "ms.corte": [
    "The dashed line is where the generation stopped looking.",
    "La línea punteada es donde la generación dejó de mirar."],

  /* --------------------------------------------- las salidas, en palabras
     La cabecera mostraba "SL=3x ATR - trail=1.5x ATR - max 12 velas", que es
     la notacion interna del minero. Los valores crudos siguen enteros en
     "Reglas de la estrategia". */
  "sal.stop": ["Stop at {n} ATR", "Stop a {n} ATR"],
  "sal.rr": ["Target {n}:1", "Objetivo {n}:1"],
  "sal.trail": ["Trailing at {n} ATR", "Trailing a {n} ATR"],
  "sal.max_bars": ["Closes after {n} bars", "Cierra a las {n} velas"],
  "sal.ninguna": ["Exits on the opposite signal", "Sale con la se\u00f1al contraria"],

  "insp.equity": ["Equity curve and drawdowns", "Curva de capital y drawdowns"],
  "insp.monthly": ["Monthly returns", "Retornos mensuales"],
  "insp.rules": ["Strategy rules", "Reglas de la estrategia"],
  "insp.long_entry": ["Long entry", "Entrada larga"],
  "insp.short_entry": ["Short entry", "Entrada corta"],
  "insp.last_n": ["(last {n} of {total})", "(últimas {n} de {total})"],
  "insp.copy_pine": ["Copy Pine", "Copiar Pine"],
  "insp.export_note": [
    "The <b>.mq5</b> compiles in MetaEditor (F7) and runs in the Strategy Tester. The <b>.pine</b> goes into TradingView's Pine Editor and onto the chart. In both cases, use the same spread used here.",
    "El <b>.mq5</b> se compila en MetaEditor (F7) y se ejecuta en el Strategy Tester. El <b>.pine</b> se pega en el Pine Editor de TradingView y se agrega al gráfico. En los dos casos, usar el mismo spread que se usó aquí."],
  /* Lo que hay que saber antes de llevar el bot a MetaTrader.

     Las tres lineas salieron de correr el EA exportado en el Strategy Tester y
     comparar con el backtest propio: 147 operaciones contra 145, profit factor
     1.13 contra 1.14, aciertos 38.1% contra 40.7% — pero solo el 5% de las
     entradas en la misma hora, porque los dos historicos difieren 18 puntos en
     promedio sobre el S&P. */
  "mt5.title": ["Before taking it to MetaTrader", "Antes de llevarlo a MetaTrader"],
  "mt5.symbol": [
    "This market is called {nuestro} here. The broker may list it as {otros}. Attach the bot to that chart — on the wrong one it will not place a single trade.",
    "Aquí este mercado se llama {nuestro}. El bróker puede tenerlo como {otros}. El bot se engancha a ese gráfico — en el equivocado no opera ni una vez."],
  "mt5.feed": [
    "The broker's price history is not the same data this was generated on, so the bot <b>will not repeat these trades one by one</b>. What carries over is the behaviour: how often it trades, how often it is right, and how much it gives back on the way.",
    "El histórico de precios del bróker no es el mismo dato con el que se generó, así que el bot <b>no va a repetir estas operaciones una por una</b>. Lo que se conserva es el comportamiento: cada cuánto opera, con qué proporción de aciertos, y cuánto devuelve en el camino."],
  /* DEL .MQ5 AL PROBADOR: el siguiente paso que faltaba después de "ya
     aparece en el Navegador". */
  "mt5.pasos_t": ["From the .mq5 to the Strategy Tester", "Del .mq5 al Probador"],
  "mt5.paso1": ["In MetaEditor press F7 to compile: it has to say 0 errors.", "En MetaEditor, F7 para compilar: tiene que decir 0 errores."],
  "mt5.paso2": ["In MetaTrader open View → Strategy Tester, choose the robot, the broker's symbol for this market, the same timeframe, and \"Every tick based on real ticks\".", "En MetaTrader, abrir Ver → Probador de estrategias, elegir el robot, el símbolo del bróker para este mercado, la misma temporalidad y \"Cada tick basado en ticks reales\"."],
  "mt5.paso3": ["Compare the tester's trades, profit factor and drawdown with this card over the same dates. If they differ a lot, do not deploy it.", "Comparar operaciones, profit factor y drawdown del probador con esta ficha en las mismas fechas. Si difieren mucho, no activarlo."],
  "mt5.paso4": ["Then drag it onto the chart of a demo account. The robot warns if the symbol or the timeframe are not the ones it was measured on.", "Después, arrastrarlo al gráfico de una cuenta demo. El robot avisa si el símbolo o la temporalidad no son los que se midieron."],
  "mt5.test_first": [
    "Run it in MetaTrader's Strategy Tester over the same period before committing capital. That is the number the broker will actually give.",
    "Ejecutarlo en el Strategy Tester de MetaTrader sobre el mismo período antes de asignarle capital. Ese es el número que va a dar el bróker en la realidad."],
  "insp.recalculating": ["Recalculating the full backtest…", "Recalculando el backtest completo…"],
  "insp.failed": ["Could not recalculate", "No se pudo recalcular"],
  "tr.in": ["Entry", "Entrada"],
  "tr.out": ["Exit", "Salida"],
  "tr.dir": ["Dir", "Dir"],
  "tr.price_in": ["Entry price", "Precio ent."],
  "tr.price_out": ["Exit price", "Precio sal."],
  "tr.result": ["Result", "Resultado"],
  "tr.bars": ["Bars", "Barras"],
  "tr.reason": ["Reason", "Motivo"],
  "sal_r.stop": ["stop hit", "tocó el stop"],
  "sal_r.target": ["target hit", "llegó al objetivo"],
  "sal_r.signal": ["exit signal", "señal de salida"],
  "sal_r.time": ["time limit", "límite de tiempo"],
  "sal_r.end": ["end of data", "fin de los datos"],

  /* ------------------------- por qué no entra ninguna candidata */
  "diag.trades": [
    "None of the {n} reached {min} trades. Lower the minimum, or use a smaller timeframe.",
    "Ninguna de las {n} llegó a {min} operaciones. Conviene bajar el mínimo de operaciones o usar un timeframe más chico."],
  "diag.trades_session": [
    "The generation is restricted to {franjas}, which leaves far fewer opportunities per year. Add <b>Around the clock</b> to the sessions, or lengthen the period.",
    "La generación está restringida a {franjas}: eso deja mucha menos oportunidad por año. Conviene sumar <b>Todo el día</b> a las franjas o alargar el período."],
  "diag.near": [
    "<b>{n}</b> of them met everything except <b>{criterio}</b>. The requirement was {pedido} and the best of those reached <b>{llego}</b>: loosen that filter and they get in.",
    "<b>{n}</b> de ellas cumplían todo salvo <b>{criterio}</b>. Se pidió {pedido} y la mejor de ésas llegó a <b>{llego}</b>: aflojar ese filtro y entran."],
  "diag.far": [
    "No candidate came close: they all fail two filters or more at once. The one rejecting the most is <b>{criterio}</b> ({n} of them); the requirement was {pedido} and the ones that failed there did not get past <b>{llego}</b>.",
    "Ninguna candidata quedó cerca: todas fallan dos filtros o más a la vez. El que más descarta es <b>{criterio}</b> ({n} de ellas); se pidió {pedido} y las que fallaron ahí no pasaron de <b>{llego}</b>."],

  "empty.none_passed": ["{n} evaluated, none cleared the filters.",
                        "{n} evaluadas, ninguna superó los filtros."],
  /* El arreglo de un clic cuando la busqueda no encontro nada.

     El diagnostico ya dice que filtro bloquea, que se pidio y hasta donde se
     llego. Sin esto habia que subir, abrir la seccion 5, encontrar ese filtro
     entre nueve, cambiar el numero y volver a minar: cinco pasos para aplicar
     una conclusion que la aplicacion ya saco.

     El boton dice QUE va a cambiar. Nadie aprieta uno que diga "arreglar". */
  "fix.bajar": ["Lower {criterio} to {valor} and generate again",
                "Bajar {criterio} a {valor} y generar de nuevo"],
  "fix.apagar": ["Disable {criterio} and generate again",
                 "Desactivar {criterio} y generar de nuevo"],
  "fix.aplicado": ["Filter adjusted \u2014 generating again",
                   "Filtro ajustado \u2014 generando de nuevo"],
  "empty.also": [
    "Filters can also be disabled in section 5, or the exits changed in section 3 — that completely changes which strategies work.",
    "También se pueden desactivar filtros en la sección 5, o cambiar las salidas en la 3 — eso cambia por completo qué estrategias funcionan."],
  "sug.title": ["How to reach that target", "Cómo llegar a ese objetivo"],
  "sug.per_trade": ["risk per trade", "riesgo por operación"],
  "sug.notional": ["notional capital", "capital nominal"],
  "sug.reachable": [
    "At a {unidad} of <b>{actual}%</b> the ceiling is the one shown. To reach the target it would have to go up to <b>{necesario}%</b> ({factor}× more), and the drawdown would go from ~{ddahora}% to <b>~{ddluego}%</b>.",
    "Con un {unidad} de <b>{actual}%</b> el techo es el que se ve. Para llegar al objetivo habría que subirlo a <b>{necesario}%</b> ({factor}× más), y el drawdown pasaría de ~{ddahora}% a <b>~{ddluego}%</b>."],
  "sug.unreachable": [
    "Raising the risk will not reach it either: it would take <b>{factor}×</b> more ({haria}% per trade), which would blow up the account before getting there. In this market and with these exits, a realistic target is <b>~{realista}% a year</b> by raising the {unidad} to {subir}%.",
    "Ni subiendo el riesgo se llega: harían falta <b>{factor}×</b> más ({haria}% por operación), lo que reventaría la cuenta antes de lograrlo. Con este mercado y estas salidas, un objetivo realista es <b>~{realista}% anual</b> subiendo el {unidad} a {subir}%."],
  "sug.warn_dd": [
    "A drawdown like that empties real accounts: it means losing more than half the capital before recovering.",
    "Un drawdown así vacía cuentas reales: es perder más de la mitad del capital antes de recuperar."],
  "sug.warn_market": [
    "For more return, the thing to change is the market, the timeframe or the exits — not the position size.",
    "Para obtener más rendimiento, conviene cambiar el mercado, el timeframe o las salidas — no forzar el tamaño de posición."],
  "sug.apply_target": ["Set the target to {n}% a year and generate again",
                       "Fijar objetivo en {n}% anual y generar de nuevo"],
  "sug.apply_risk": ["Raise it to {n}% and generate again", "Subir a {n}% y volver a generar"],

  /* --------------------------------------------- columnas de las tablas */
  "col.strategy": ["Strategy", "Estrategia"],
  "col.equity": ["Equity", "Capital"],
  "col.annual": ["Annual", "Anual"],
  "col.maxdd": ["Max drawdown", "Drawdown máx."],
  "col.ops": ["Trades", "Ops."],
  "col.months_plus": ["Positive months", "Meses positivos"],
  "col.oos": ["Reserved<br>window", "Ventana<br>reservada"],
  "col.oos_full": ["Reserved window", "Ventana reservada"],
  "col.score_help": [
    "The app's own robustness score: how repeatable the strategy looks, not how much it returned.",
    "Puntaje propio de robustez: qué tan repetible parece la estrategia, no cuánto rindió."],
  "col.ops_help": [
    "Number of trades. Few trades make any metric unreliable.",
    "Cantidad de operaciones. Pocas operaciones hacen que cualquier métrica sea poco confiable."],
  "col.months_help": [
    "Share of months closed in profit. High means it wins steadily, not in a single stroke.",
    "Porcentaje de meses cerrados en ganancia. Alto significa que gana de forma sostenida, no de un solo golpe."],
  "col.oos_help": [
    "How much of the edge survived on the window the generation never looked at (profit factor there divided by the profit factor of the window it generated on). Near 1 the edge remained whole; near 0 the strategy was only describing the past.",
    "Cuánto de la ventaja sobrevivió en la ventana que la generación no miró (profit factor ahí dividido por el de la ventana donde se generó). Cerca de 1 la ventaja se conservó entera; cerca de 0 la estrategia sólo describía el pasado."],
  "col.click_sort": ["click to sort", "clic para ordenar"],
  "col.oos_holds": ["holds", "se sostiene"],
  "col.oos_weakens": ["weakens", "se debilita"],
  "col.oos_falls": ["falls apart", "se cae"],
  "col.oos_nodata": ["no data", "sin datos"],
  "col.oos_nodata_help": ["It did not trade in the reserved window: there is nothing to check.",
                          "No operó en la ventana reservada: no hay nada que validar."],

  /* ------------------------------------- antes de la primera búsqueda */
  "idle.title": ["Ready to generate", "Lista para generar"],
  "idle.plan": [
    "Generation of <b>{goal} strategies</b> on <b>{mercado}</b>, in <b>{tf}</b> candles, {tamano} and a <b>{rr}</b> risk/reward. Only the ones that traded <b>{trades} times or more</b> are kept",
    "Se generan <b>{goal} estrategias</b> sobre <b>{mercado}</b>, en velas de <b>{tf}</b>, {tamano} y relación <b>{rr}</b>. Se conservan sólo las que operaron <b>{trades} veces o más</b>"],
  /* Cuando una receta busca varias relaciones riesgo:beneficio, decir "1:2"
     sería mentir: esa corrida no va a usar ninguna relación fija. */
  /* ─────────────────────── buscar la relación en vez de fijarla ───────────
     Es la perilla que más cambia lo que la búsqueda puede encontrar, y hasta
     ahora sólo se podía tocar eligiendo una categoría. */
  "rr.fija": ["Fixed", "Fija"],
  "rr.buscar": ["Explored", "Explorada"],
  "rr.fija_ayuda": [
    "Every candidate uses the ratio above. It caps the win rate: risking 1 to "
    + "make 2 needs about a third of trades to win, and that is the result.",
    "Todas las candidatas usan la relación de arriba. Es lo que le pone techo al "
    + "win rate: arriesgar 1 para ganar 2 exige acertar un tercio, y eso es lo "
    + "que se acierta."],
  "rr.buscar_ayuda": [
    "Each candidate gets its own ratio, from 1:{desde} to 1:{hasta} ({n} values). "
    + "Widens what the generation can find: measured, the win rate range nearly doubles.",
    "Cada candidata lleva la suya, de 1:{desde} a 1:{hasta} ({n} valores). Ensancha "
    + "lo que la generación puede encontrar: medido, el abanico de win rate casi se "
    + "duplica."],
  /* Va DENTRO de "a <b>{rr}</b> risk/reward", así que tiene que leerse como
     un sustantivo: "anywhere from 1:0.5 to 1:0.75" dejaba la frase en "a
     anywhere from…". El rango ya dice solo que la búsqueda los prueba todos,
     y el tooltip de al lado lo explica (3 de septiembre de 2026). */
  "rr.varias": ["1:{desde} to 1:{hasta}",
                "de 1:{desde} a 1:{hasta} (se explora)"],
  "idle.and_meet": ["and, on top of that: {lista}.", "y además: {lista}."],
  /* CADA FILTRO EN CASTELLANO: la métrica exacta queda al pasar el mouse. */
  "llano.minPf": ["earned more than they lost ({v}×)", "ganaron más de lo que perdieron ({v}×)"],
  "llano.minRetDd": ["earned {v} times what they fell", "ganaron {v} veces lo que cayeron"],
  "llano.maxDd": ["never fell more than {v}", "nunca cayeron más de {v}"],
  "llano.minWinRate": ["closed at least {v} of trades in profit", "cerraron en ganancia al menos el {v} de las operaciones"],
  "llano.minTradesMonth": ["traded {v} times a month or more", "operaron {v} veces por mes o más"],
  "llano.minTradesWeek": ["traded {v} times a week or more", "operaron {v} veces por semana o más"],
  "llano.minCagr": ["returned {v} a year or more", "rindieron {v} al año o más"],
  "llano.minSharpe": ["gained steadily (Sharpe {v})", "ganaron parejo (Sharpe {v})"],
  "llano.minExposure": ["were in the market at least {v} of the time", "estuvieron en el mercado al menos el {v} del tiempo"],
  "idle.session_one": ["Only during {nombre} ({horas}).", "Sólo durante {nombre} ({horas})."],
  "idle.session_many": [
    "The generation picks the best of {n} trading sessions for each strategy.",
    "La generación elige la mejor de {n} franjas horarias para cada estrategia."],
  "idle.no_filters": [
    "With no filters on, anything gets in — including strategies that lose capital. Enabling <b>Profit factor ≥ 1</b> in section 5 keeps only the winners.",
    "Sin filtros activos entra cualquier estrategia, incluso las que pierden dinero. Activar <b>Profit factor ≥ 1</b> en la sección 5 deja sólo las ganadoras."],
  "idle.s1": ["A candidate gets built", "Se arma una candidata"],
  "idle.s1_sub": [
    "It randomly combines an entry trigger, context filters, a trading session and each indicator's parameters.",
    "Combina al azar un disparador de entrada, filtros de contexto, una franja horaria y los parámetros de cada indicador."],
  "idle.s2": ["It gets fully backtested", "Se backtestea entera"],
  "idle.s2_sub": ["Over every year of real data, with the configured costs and risk model.",
                  "Sobre todos los años de datos reales, con los costos y el modelo de riesgo configurados."],
  "idle.s3": ["It passes or it is discarded", "Pasa o se descarta"],
  "idle.s3_sub": [
    "If it meets the filters it enters the repository ranked by score; if not, it is discarded and another one is generated.",
    "Si cumple los filtros entra al repositorio ordenada por score; si no, se descarta y se genera otra."],
  "idle.s4": ["It repeats without stopping", "Se repite sin parar"],
  "idle.s4_sub": [
    "Until the {goal} requested are gathered. Each one can be inspected and exported to MetaTrader.",
    "Hasta reunir las {goal} solicitadas. Cada una se puede inspeccionar y exportar a MetaTrader."],

  /* --------------------- resúmenes de las secciones plegadas del minado */
  "sum.sessions": ["{n} sessions", "{n} franjas"],
  "sum.oos_short": ["checks {pct}%", "valida {pct}%"],
  /* Resumenes de fila plegada: valores, no frases. La version larga de
     cada uno vive dentro de la seccion, que es donde hace falta explicar. */
  "sum.vol_stop_short": ["ATR stop", "stop ATR"],
  "sum.swap": ["holding {pct}%/yr", "mantener {pct}%/año"],
  "sum.costs": ["spread {spread} · slip {slip} · ${cap}",
                "spread {spread} · slip {slip} · ${cap}"],
  "sum.method_rnd_short": ["Random", "Aleatorio"],
  "sum.method_evo_short": ["Evolution", "Evolución"],
  "sum.cap_short": ["cap {n}", "tope {n}"],

  "sug.risk_again": ["Risk {pct}% — generating again", "Riesgo {pct}% — generando de nuevo"],
  "sug.target_again": ["Target {pct}% a year — generating again",
                       "Objetivo {pct}% anual — generando de nuevo"],
  "sum.blocks": ["{drv} triggers · {flt} filters",
                 "{drv} disparadores · {flt} filtros"],
  "sum.no_filters": ["With no filters selected, every strategy is just its entry trigger.",
                     "Sin filtros seleccionados, cada estrategia es sólo su disparador de entrada."],
  "sum.minimal_ignores": [
    "At <b>{nombre}</b> the selected filters are not used: each strategy enters on its trigger alone.",
    "En <b>{nombre}</b>, los filtros seleccionados no se usan: cada estrategia entra sólo con su disparador."],
  "sum.filters_note": [
    "There are <b>{flt} filters</b> selected. Each candidate picks <b>between 0 and {n}</b> of them at random and requires them all at once. More filters per strategy means more specific rules: they trade less often and depend more on the market repeating those same conditions.",
    "Hay <b>{flt} filtros</b> seleccionados. Cada candidata elige al azar <b>entre 0 y {n}</b> de ellos y los exige a la vez. Más filtros por estrategia hace reglas más específicas: operan con menos frecuencia y dependen más de que el mercado repita esas mismas condiciones."],
  "sum.lots": ["{lots} fixed lots", "{lots} lotes fijos"],
  "sum.risk": ["{pct}% per trade", "{pct}% por operación"],
  "sum.only_trades": ["only {n}+ trades — nothing else filtered",
                      "sólo {n}+ operaciones — el resto sin filtrar"],

  /* --------------------------------------- qué significa cada métrica
     Los nombres no se traducen; esto sí. Van en el título de cada fila para
     que se pueda preguntar qué es un profit factor sin salir de la pantalla. */
  "crit.minPf": [
    "How many dollars it made for every dollar it lost. At 1 it broke even; below that the strategy loses capital. It ships enabled at 1 precisely so the repository does not fill up with losers.",
    "Cuántos dólares ganó por cada dólar que perdió. En 1 quedó igual; por debajo, la estrategia pierde dinero. Viene activado en 1 justamente para que el repositorio no se llene de perdedoras."],
  "crit.minRetDd": [
    "Net profit divided by the worst fall. It joins the two halves of the question — how much it made and how much had to be endured — and it does not move when the risk per trade changes. At 1 it made exactly what it fell; 2 is demanding and 3 is passed by one in ten in a good market.",
    "Ganancia neta dividida por la peor caída. Junta las dos mitades de la pregunta —cuánto ganó y cuánto hubo que soportar— y no se mueve si cambia el riesgo por operación. En 1 ganó justo lo que llegó a caer; 2 ya es exigente y 3 lo pasa una de cada diez en un mercado bueno."],
  "crit.maxDd": [
    "The worst the account ever fell from a peak to a bottom. It is what has to be endured without closing everything.",
    "Lo peor que llegó a bajar la cuenta desde un pico hasta el fondo. Es lo que hay que poder soportar sin cerrar todo."],
  "crit.minWinRate": [
    "Share of winning trades. Note: at a 1:2 risk/reward, 40% is already profitable — a high win rate is not the same as making more capital.",
    "Porcentaje de operaciones ganadoras. Atención: con una relación riesgo/beneficio de 1:2, un 40% ya es rentable — un win rate alto no es lo mismo que ganar más."],
  "crit.minTradesMonth": [
    "How often it trades per month. It is the trade count made comparable: 200 is a lot over two years and very few over twenty.",
    "Cuántas veces opera al mes. Es el total de operaciones pero comparable: 200 son muchas en dos años y pocas en veinte."],
  /* La ayuda dice la equivalencia porque es la pregunta que sigue: alguien
     que quiere operar todos los días necesita saber que eso son cinco. */
  "crit.minTradesWeek": [
    "How often it trades per week. Five is roughly one per trading day — the usual "
    + "requirement for a funded-account challenge, which has a deadline.",
    "Cuántas veces opera por semana. Cinco es aproximadamente una por día hábil — "
    + "lo que suele pedir un desafío de cuenta fondeada, que tiene fecha de vencimiento."],
  "crit.minCagr": [
    "What it returned per year, compounded. It scales with the risk per trade.",
    "Cuánto rindió por año, en promedio compuesto. Escala con el riesgo por operación."],
  "crit.minSharpe": [
    "Return per unit of volatility. It rewards a smooth curve and punishes one that jumps around.",
    "Retorno por unidad de volatilidad. Premia la curva pareja y castiga la que da saltos."],
  "crit.minExposure": [
    "What share of the time it held an open position. Very low means it barely trades and the sample is worth little.",
    "Qué porcentaje del tiempo estuvo con una posición abierta. Muy bajo significa que opera muy poco y la muestra vale poco."],
  "crit.minTrades": ["Minimum trades", "Mínimo de operaciones"],

  /* ------------------------------------------------- complejidad de las reglas */
  "cx.0": ["Minimal", "Mínima"],
  "cx.0_sub": ["trigger only", "sólo el disparador"],
  "cx.0_help": [
    "The entry trigger and nothing else. It is the hardest to overfit and the most honest place to start: if nothing appears here, the filters are not the problem.",
    "Sólo el disparador de entrada. Es lo más difícil de sobreajustar y lo más honesto como punto de partida: si aquí no aparece nada, el problema no son los filtros."],
  "cx.1": ["Low", "Baja"],
  "cx.1_sub": ["1 condition", "1 condición"],
  "cx.1_help": ["The trigger plus one context condition.",
                "El disparador más una condición de contexto."],
  "cx.2": ["Medium", "Media"],
  "cx.2_sub": ["up to 2", "hasta 2"],
  "cx.2_help": [
    "Up to two conditions at once. It is the recommended balance between finding something and inventing it.",
    "Hasta dos condiciones a la vez. Es el equilibrio recomendado entre encontrar algo y no inventarlo."],
  "cx.3": ["High", "Alta"],
  "cx.3_sub": ["up to 3", "hasta 3"],
  "cx.3_help": [
    "Up to three. It finds much prettier backtests and considerably less repeatable ones: validate them out-of-sample before believing them.",
    "Hasta tres. Encuentra backtests mucho más vistosos y bastante menos repetibles: conviene validar fuera de muestra antes de creerles."],

  /* ------------------------------------------------- franjas horarias (motor)
     Los ids los define el servidor en botiquant/core/sesiones.py; acá sólo
     viven sus nombres. */
  "s.todo": ["Around the clock", "Todo el día"],
  "s.asia": ["Asian session", "Sesión asiática"],
  "s.londres": ["London session", "Sesión de Londres"],
  "s.apertura_londres": ["London open", "Apertura de Londres"],
  "s.nueva_york": ["New York session", "Sesión de Nueva York"],
  "s.apertura_ny": ["New York open", "Apertura de Nueva York"],
  "s.solape": ["London–New York overlap", "Solape Londres–Nueva York"],
  "s.rueda_eeuu": ["US cash hours", "Rueda de acciones de EE.UU."],
  "s.sin_lunes_viernes": ["Tuesday to Thursday", "De martes a jueves"],

  "session.title": ["Trading hours", "Horario de negociación"],
  "session.sub": ["When the strategy is allowed to open trades",
                  "Cuándo puede abrir operaciones la estrategia"],
  "session.help": [
    "Every hour of the day trades differently. A rule that works between the New York open and the close can lose capital running overnight, when the same instrument moves on a tenth of the volume and a much wider spread. Select the one that fits the instrument. Enabling several lets the generation choose per strategy, which explores more but also overfits more.",
    "Cada hora del día se opera distinto. Una regla que funciona entre la apertura de Nueva York y el cierre puede perder dinero de madrugada, cuando el mismo instrumento se mueve con una décima parte del volumen y un spread mucho más ancho. Seleccionar la que le corresponda al instrumento. Activar varias deja que la generación elija por estrategia, que explora más pero también sobreajusta más."],
  "session.searched": [
    "The generation picks the best of the {n} windows selected — <b>for each candidate</b>. That is {n} chances to fit noise, and it shows: measured over twelve years, enabling all nine windows drops the average annual return from <b>2.49% to 1.85%</b> on the S&P 500 and from 3.80% to 2.22% on gold. Selecting <b>one</b> window on purpose is the version that helps.",
    "La generación elige la mejor de las {n} franjas seleccionadas — <b>para cada candidata</b>. Eso son {n} oportunidades de ajustarse al ruido, y se nota: medido sobre doce años, habilitar las nueve baja el rendimiento medio de <b>2,49% a 1,85%</b> anual en el S&P 500 y de 3,80% a 2,22% en oro. Seleccionar <b>una sola</b> a propósito es la versión que sí ayuda."],
  "session.fixed": ["Every strategy trades only in this window.",
                    "Todas las estrategias operan sólo en esta franja."],
  "session.utc": ["Hours are UTC, the timezone of the price data.",
                  "Las horas son UTC, la zona horaria de los datos de precio."],
  "session.none": ["No hour restriction", "Sin restricción de horario"],
  "session.all_day": ["all day", "todo el día"],
  /* ---------------------------------------------- los tres pasos y su estado
     Nada de esto se traduce "a ojo": los nombres de las pruebas se dejan como
     los usa el oficio (walk-forward, Monte Carlo) y lo que se traduce es la
     explicación. Un "análisis de avance progresivo" no lo busca nadie en
     Google ni lo dice nadie en una mesa. */

  /* ------------------------------------------------------------- consejos
     Los números salen de mediciones hechas sobre estos mismos instrumentos
     durante el desarrollo. Si alguno cambia, hay que volver a medirlo antes
     de tocar el texto: un consejo con un número inventado es peor que no
     tener la sección. */
  /* --------------------------------------- rótulos de los dibujos de Consejos
     Cortos a propósito: van dentro del SVG, al lado de su barra, y un rótulo
     largo empuja la barra hasta dejarla sin espacio para crecer. */
  "g.short_window": ["Short window", "Ventana corta"],
  "g.long_window": ["Whole history", "Todo el hist\u00f3rico"],
  "g.higher_returns": ["Higher returns", "Retornos m\u00e1s altos"],
  "g.more_behind": ["More behind each one", "M\u00e1s respaldo detr\u00e1s"],

  "g.day_shape": ["How busy the day is, hour by hour",
                  "Qu\u00e9 tan movido est\u00e1 el d\u00eda, hora por hora"],
  "g.day_note": [
    "Highlighted: the New York session. The same rule meets a different market outside it.",
    "Resaltada: la sesi\u00f3n de Nueva York. Fuera de ah\u00ed, la misma regla se encuentra otro mercado."],

  "g.funnel": ["Candidates that clear the threshold", "Candidatas que pasan el umbral"],
  "g.bar_low": ["Low threshold", "Umbral bajo"],
  "g.bar_high": ["High threshold", "Umbral alto"],
  "g.funnel_note": [
    "How far it can be raised depends on the instrument and the period. Raise it until the repository starts to thin out.",
    "Hasta d\u00f3nde se puede subir depende del instrumento y del per\u00edodo. Conviene subirlo hasta que el repositorio empiece a ralear."],

  "g.same_shape": ["Triple the risk, triple both halves",
                   "El triple de riesgo, el triple de las dos mitades"],
  "g.risk_base": ["Base risk", "Riesgo base"],
  "g.risk_triple": ["Triple risk", "Triple de riesgo"],
  "g.legend_return": ["Return", "Retorno"],
  "g.legend_dd": ["Drawdown", "Ca\u00edda"],
  "g.scale_note": [
    "The shape of the equity curve does not change \u2014 only its scale.",
    "La forma de la curva de capital no cambia \u2014 s\u00f3lo su escala."],

  "g.btc_cost": ["Round-trip cost on BTCUSD, in price units",
                 "Costo de ida y vuelta en BTCUSD, en unidades de precio"],
  "g.real_spread": ["BTCUSD spread", "Spread de BTCUSD"],
  "g.inherited_spread": ["EURUSD spread left behind", "Spread de EURUSD heredado"],
  "g.spread_note": [
    "A hundred thousand times cheaper, and nothing warns about it.",
    "Cien mil veces más barato, y nada lo advierte."],
  "g.utc_mined": ["UTC — where it was generated", "UTC — donde se generó"],
  "g.server_utc3": ["Broker on UTC+3", "Bróker en UTC+3"],
  "g.offset_note": [
    "Same window, three hours later on the server clock.",
    "La misma franja, tres horas más tarde en el reloj del servidor."],

  "nav.exchanges": ["Exchanges", "Exchanges"],
  // El menú se está renombrando a "Operar" en otra sesión. Este texto va acá
  // para que la sección no se dibuje en crudo mientras tanto; la vieja se
  // deja hasta que ese cambio esté terminado y se pueda sacar de una.
  /* Bajar el conjunto, que es lo que lo convierte en un portafolio y no en
     varios archivos sueltos. El texto dice la diferencia porque no es obvia:
     exportando de a uno, cada EA se cree dueño de toda la cuenta. */
  "pf.export_title": ["Take the whole set to MetaTrader",
                      "Llevar el conjunto a MetaTrader"],
  "pf.export_sub": [
    "{n} robots, each one already carrying its share of the account. Exported one by one, each would size as if it owned the whole account.",
    "{n} robots, cada uno con su parte de la cuenta ya adentro. Exportados de a uno, cada uno se dimensiona como si fuera dueño de toda la cuenta."],
  "pf.export_btn": ["Download the set", "Bajar el conjunto"],
  "pf.export_ok": ["{n} robots saved in {carpeta}",
                   "{n} robots guardados en {carpeta}"],

  /* En qué reloj están las velas. La FUENTE no se muestra a propósito: de
     dónde las bajamos es asunto nuestro y el usuario pidió un instrumento, no
     un proveedor. El reloj sí, porque es lo que tiene que coincidir con el
     horario de su bróker. */
  "data.en_reloj": ["clock {reloj}", "reloj {reloj}"],

  /* Dónde se tienen que cumplir los filtros de aceptación.

     "También afuera" y no "en vez de adentro": el tramo reservado sólo se
     corre para las que ya pasaron adentro, así que es una segunda puerta y no
     otra puerta. Decirlo mal haría esperar que aparezcan estrategias que
     adentro no llegan. */
  "acc.solo_dentro": ["In sample", "En muestra"],
  "acc.tambien_fuera": ["Also out-of-sample", "También fuera de muestra"],
  "acc.solo_dentro_ayuda": [
    "The filters apply to the window the generation looked at. The reserved window still lowers the score of whatever did not remain robust there, but does not reject it.",
    "Los filtros se aplican a la ventana que miró la generación. La ventana reservada igual le baja el score a lo que no conservó la ventaja ahí, pero no lo descarta."],
  /* Dice que TARDA MAS además de que salen menos: medido sobre EURUSD, con
     esto la tasa de aceptación cayó a 0,6% y juntar diez llevó unos diez
     minutos. Sin avisarlo, alguien lo prende y cree que la búsqueda se colgó. */
  "acc.tambien_fuera_ayuda": [
    "The same thresholds have to hold on the reserved window too, and one that never traded there does not pass: not measuring is not passing. Fewer candidates come out and the generation takes longer — but every one of them remained robust where the generation never looked.",
    "Los mismos umbrales tienen que cumplirse también en la ventana reservada, y una que no operó ahí no pasa: no medir no es aprobar. Salen menos candidatas y la generación tarda más, pero cada una conservó la ventaja donde la generación no miró."],
  "acc.necesita_reserva": [
    "Enable the reserved window in step 1 to be able to demand it out-of-sample.",
    "Activar la ventana reservada en el paso 1 para poder exigirla fuera de muestra."],

  /* Las dos secciones. El rótulo dice QUE se opera, no dónde: un trader sabe
     si opera CFD o cripto, y de ahí se deduce todo lo demás —dónde se ejecuta,
     cómo se paga y cómo se exporta—. */
  "mundo.rotulo": ["What is traded", "Qué se opera"],
  "mundo.cfds": ["MetaTrader 5", "MetaTrader 5"],
  "mundo.cfds_sub": [
    "Indices, forex and metals through MetaTrader. The spread is paid and they are taken as Expert Advisors.",
    "Índices, forex y metales por MetaTrader. Se paga el spread y se llevan como Expert Advisor."],
  "mundo.cripto": ["Crypto", "Cripto"],
  "mundo.cripto_sub": [
    "Perpetual futures on an exchange. Commission and funding are paid, and they connect to the exchange.",
    "Futuros perpetuos en un exchange. Se paga comisión y funding, y se conectan al exchange."],

  "nav.operar": ["Trading", "Operación"],

  /* LA ESCALERA: hasta dónde puede llegar una estrategia.
     simulacro → práctica → real, y cada escalón pide más que el anterior.
     Los textos existen desde acá; el código que los pide ya estaba y pedía
     claves que nadie había escrito, así que las pestañas y la escalera se
     dibujaban con el nombre interno de la clave. */
  "esc.title": ["How far this one can go", "Hasta dónde puede llegar"],
  "esc.sub": [
    "Each rung asks for more than the one before, and the last one asks for it out of the sample the generation looked at.",
    "Cada escalón pide más que el anterior, y el último lo pide además fuera de la muestra que miró la generación."],
  "esc.simulacro": ["Simulation", "Simulacro"],
  "esc.practica": ["Practice", "Práctica"],
  "esc.real": ["Real capital", "Dinero real"],
  "esc.ninguno": ["Not yet", "Todavía no"],
  "esc.hasta": ["up to {destino}", "hasta {destino}"],
  "esc.libre": ["always available — no capital at risk",
                "siempre disponible — no hay dinero en juego"],
  "esc.habilitada": ["clear", "habilitada"],
  "esc.falta": ["For {destino}: {motivo}", "Para {destino}: {motivo}"],
  /* Cuando la cantera dice que no y no explica: pasa con las guardadas viejas,
     que no tienen las métricas que la vara mira. */
  "esc.falta_sin_motivo": ["not enough measured yet", "todavía falta medirla"],
  "esc.pie": [
    "Getting past a rung is permission, not advice: it says the numbers remain robust, not that it will work.",
    "Pasar un escalón es un permiso, no un consejo: dice que los números se sostienen, no que vaya a funcionar."],

  /* Las dos pestañas de Operar y lo que las acompaña. */
  "op.tab_bot": ["Robots", "Robots"],
  "op.tab_claves": ["Exchange keys", "Claves"],
  "op.sin_claves": ["No key loaded yet", "Todavía no hay ninguna clave cargada"],
  /* Decía "un bot por vez sobre una cuenta", que fue cierto hasta que el
     piloto aprendió a sostener varios. La regla real es POR SIMBOLO. */
  "op.sub_bot": [
    "One bot per symbol: several can run at once, each sized on its own share of the account.",
    "Un bot por símbolo: pueden correr varios a la vez, cada uno dimensionado sobre su porción de la cuenta."],
  "op.cfd_nota": ["CFDs trade through MetaTrader: export the strategy as a robot from My strategies and attach it to a chart. The bots below are for crypto.",
                 "Los CFD se operan en MetaTrader: exportar la estrategia como robot desde Mis estrategias y colocarla en un gráfico. Los bots de abajo son de cripto."],
  "op.ir_claves": ["Load a key", "Cargar una clave"],
  /* Binance va SOLO en demo, y el rotulo lo dice en el titulo y no en una
     nota al pie: si estuviera abajo, alguien carga la clave, ve "configurada"
     y da por hecho que puede operar en real. */
  /* El exchange se ELIGE. Ver el comentario del select en app.js. */
  /* EL TABLERO. El resultado va PARTIDO por concepto: un numero solo esconde
     si la estrategia no sirve o si sirve y los costos se la comen. */
  "op.tab_tablero": ["The account", "La cuenta"],
  "tab.titulo": ["What the account actually did", "Lo que la cuenta hizo de verdad"],
  "tab.sub": [
    "Straight from Binance demo, not from what the bots remember: the bot's log is lost when the app closes and knows nothing about fees.",
    "Directo de Binance demo, no de lo que los bots recuerdan: el registro del bot se pierde al cerrar la app y no sabe de comisiones."],
  "tab.sin_clave": ["No demo key loaded", "No hay clave demo cargada"],
  "tab.sin_clave_sub": [
    "Loading the Binance demo key in the Exchange keys tab fills this in on its own.",
    "Al cargar la clave demo de Binance en la pestaña de Claves, esto se completa solo."],
  "tab.cargando": ["Asking the exchange…", "Preguntándole al exchange…"],
  "tab.saldo": ["Balance", "Saldo"],
  "tab.neto": ["Net result", "Resultado neto"],
  "tab.cerradas": ["Closed trades", "Operaciones cerradas"],
  "tab.wr": ["Trades closed in profit", "Operaciones cerradas en ganancia"],
  "tab.pnl": ["Trading P&L", "P&L de las operaciones"],
  "tab.comision": ["Fees", "Comisiones"],
  "tab.funding": ["Funding", "Funding"],
  "tab.parte_nota": [
    "Split on purpose: P&L can be positive and the account still down because fees ate it. One single number would say \"losing\" and point to changing the strategy, when what to change is how often it trades.",
    "Partido a propósito: el P&L puede estar en positivo y la cuenta en negativo porque las comisiones se lo consumieron. Un número solo diría \"pierde\" y llevaría a cambiar la estrategia, cuando lo que hay que cambiar es cuánto opera."],
  "tab.abiertas": ["Open positions", "Posiciones abiertas"],
  "tab.sin_abiertas": ["Nothing open right now.", "Ahora mismo no hay nada abierto."],
  "tab.largo": ["long", "largo"],
  "tab.corto": ["short", "corto"],
  "tab.desde_precio": ["in at {p}", "entró a {p}"],
  "tab.marca": ["mark {p}", "marca {p}"],
  "tab.ejecuciones": ["Fills", "Ejecuciones"],
  "tab.ejecuciones_nota": [
    "One trade can be several fills: a market order fills against several levels of the book and the exchange reports one row each.",
    "Una operación puede ser varias ejecuciones: una orden a mercado se llena contra varios niveles del libro y el exchange devuelve una fila por llenado."],
  "tab.sin_ejecuciones": ["Nothing traded yet.", "Todavía no se operó nada."],
  "tab.compra": ["buy", "compra"],
  "tab.venta": ["sell", "venta"],
  "tab.com_corta": ["fee", "com."],

  /* EL CONJUNTO. Las expectativas se rotulan como lo que son: lo que esas
     estrategias hicieron en SU backtest, agregado. Nunca una promesa. */
  "conj.titulo": ["Run a set", "Armar un conjunto"],
  "conj.sub": [
    "Selecting several shows the plan -shares, expectations, warnings- before starting them together.",
    "Seleccionar varias muestra el plan —porciones, expectativas, avisos— antes de activarlas juntas."],
  "conj.armar": ["Preview the plan", "Armar el plan"],
  "conj.encender": ["Start the set (demo)", "Activar el conjunto (demo)"],
  "conj.elegi": ["Select at least two strategies", "Seleccionar al menos dos estrategias"],
  "conj.retorno": ["Expected yearly return", "Retorno anual esperado"],
  "conj.ops": ["Trades per month", "Operaciones por mes"],
  "conj.wr": ["Expected win rate", "Win rate esperado"],
  "conj.dd": ["Worst individual drawdown", "Peor drawdown individual"],
  "conj.fuente": [
    "From each strategy's backtest, aggregated. An expectation, not a promise: the traffic light reports if it stops being true.",
    "Del backtest de cada una, agregado. Una expectativa, no una promesa: el semáforo avisa si deja de cumplirse."],
  "conj.ops_cortas": ["{n} ops/mo", "{n} ops/mes"],
  "conj.parcial": ["{n} deployed, {f} could not: {motivo}", "{n} activadas, {f} no se pudieron: {motivo}"],
  "conj.encendido": ["{n} bots running", "{n} bots activos"],
  "conj.fallo": [
    "Started {n} and then one failed: {err}. The ones already running stay on.",
    "Se activaron {n} y uno falló: {err}. Los que ya arrancaron siguen activos."],
  "bot.esperado_mes": ["≈{n} trades a month, going by its backtest", "≈{n} ops/mes según su backtest"],
  "bot.proxima": ["next candle ~{h}", "próxima vela ~{h}"],
  /* LO QUE HACE FALTA PARA DEJARLO CORRIENDO TRANQUILO, en una línea. */
  "bot.riesgo": ["Risks {pct}% of its share per trade ≈ {usdt} USDT · stop on the exchange · daily cap: {tope}",
                 "Arriesga {pct}% de su porción por operación ≈ {usdt} USDT · stop en el exchange · tope diario: {tope}"],
  "bot.sin_tope": ["none", "sin tope"],
  "bot.trailing_no": ["Its stop moves with price every candle, and a robot leaves one order on the exchange: it cannot be run as measured.",
                      "Su stop se mueve con el precio en cada vela, y un robot deja una sola orden puesta en el exchange: no se puede correr como se midió."],
  "bot.trailing_corto": ["not runnable (trailing)", "no se puede activar (trailing)"],

  /* ---- la franja de agentes en Operar: qué está haciendo cada uno ---- */
  "ag.titulo": ["Autopilot", "Piloto automático"],
  /* YA NO DICE QUE LAS PRUEBA. El ciclo dejó de mandar a probar por su
     cuenta: probar es la decisión de una persona y además cada prueba es un
     walk-forward completo que dejaba el servidor ocupado sin parar
     (3 de septiembre de 2026). */
  "pil.reglas": [
    "Its rules: every {h} h it generates new strategies and deploys the ones already validated that remained robust, up to {n} robots, one per symbol, on the demo account. Sending strategies to validation stays a manual decision.",
    "Sus reglas: cada {h} h genera estrategias nuevas y activa las ya validadas que resultaron robustas, hasta {n} robots, uno por símbolo, en la cuenta demo. Enviar estrategias a validación es una decisión manual."],
  "pil.ultimas": ["What it did last", "Lo último que hizo"],
  /* LA EXPLICACIÓN ANIMADA: un recorrido de pasos con un punto que avanza.
     Los textos cortos van en el nodo; los largos, en el panel de abajo. */
  "expl.ver": ["See how it works", "Ver cómo funciona"],
  /* EL PILOTO SE CONFIGURA SOBRE SU DIBUJO: un campo por parámetro, en el
     nodo que le corresponde. */
  "pil.f_minar_cada_horas": ["Generates every (hours)", "Genera cada (horas)"],
  "pil.f_candidatas_por_vuelta": ["Candidates per round", "Candidatas por vuelta"],
  "pil.f_reservar_pct": ["Reserved window (%)", "Ventana reservada (%)"],
  "pil.f_instrumentos": ["On which perpetuals", "Sobre qué perpetuos"],
  "pil.f_instrumentos_nota": ["None selected means all the downloaded ones. It always picks the one with the fewest strategies.",
                              "Sin ninguno seleccionado, todos los descargados. Siempre elige el que menos estrategias tiene."],
  "pil.f_validar_por_vuelta": ["Validations per round", "Validaciones por vuelta"],
  "pil.f_validar_nota": ["Few on purpose: each one is a full backtest across four windows plus 1,000 resamples.",
                         "Pocas a propósito: cada una es un backtest completo en cuatro ventanas más 1000 remuestreos."],
  "pil.f_max_en_practica": ["Robots at most", "Robots como máximo"],
  "pil.f_max_por_instrumento": ["Per symbol", "Por símbolo"],
  "pil.f_practica_nota": ["Always on the demo account. It never moves anything to real capital by itself.",
                          "Siempre en la cuenta demo. Nunca pasa nada a dinero real por su cuenta."],
  "pil.f_vueltas_en_naranja": ["Rounds in orange before acting", "Vueltas en naranja antes de actuar"],
  "pil.f_vigila_nota": ["An orange light can go back to green. Acting at once would make it eat its own strategies in a bad streak.",
                        "Un naranja puede volver a verde. Actuar de inmediato haría que se coma sus propias estrategias en una racha mala."],
  "pil.f_retirar_solo": ["Retire by itself (otherwise it only reports)", "Retirar solo (si no, sólo avisa)"],
  "pil.f_retirar_nota": ["Off by default: the light should be seen changing colour a few times before it is trusted.",
                         "Desactivado por omisión: conviene ver el semáforo cambiar de color varias veces antes de confiar en él."],
  "pil.guardar": ["Save changes", "Guardar cambios"],
  "pil.guardado": ["Autopilot updated.", "Piloto actualizado."],
  "expl.reproducir": ["Play", "Reproducir"],
  "expl.pausar": ["Pause", "Pausar"],
  "expl.pil1": ["Generates", "Genera"],
  "expl.pil1_t": ["Every 12 hours it generates <b>1,500 candidates</b> on the perpetuals it does not have a robot on yet, with the same filters used by hand.",
                  "Cada 12 horas genera <b>1500 candidatas</b> sobre los perpetuos que todavía no tienen robot, con los mismos filtros que se usarían a mano."],
  "expl.pil2": ["Validates", "Valida"],
  "expl.pil2_t": ["What comes out goes through the same validation as the button: four windows it never saw and 1,000 resamples. Only what remains robust moves on.",
                  "Lo que sale pasa por la misma validación que el botón: cuatro ventanas que nunca vio y 1000 remuestreos. Sólo sigue lo que resiste."],
  "expl.pil3": ["Deploys", "Activa"],
  "expl.pil3_t": ["The robust ones get a robot on the <b>demo account</b>: up to 8, one per symbol, each with its share. Never real capital by itself.",
                  "Las robustas reciben un robot en la <b>cuenta demo</b>: hasta 8, uno por símbolo, cada uno con su porción. Nunca dinero real por su cuenta."],
  "expl.pil4": ["Watches", "Vigila"],
  "expl.pil4_t": ["Each robot is checked against its own backtest: does it trade as often as it said, does it still earn? A traffic light says so.",
                  "A cada robot se lo compara con su propio backtest: ¿opera tan seguido como decía, sigue rindiendo? Un semáforo lo dice."],
  "expl.pil5": ["Retires", "Retira"],
  "expl.pil5_t": ["When the edge fades, the robot is stopped and the strategy retired <b>with the reason</b>, so it is not deployed again in six months. Then it generates again.",
                  "Cuando la ventaja se apaga, el robot se detiene y la estrategia se retira <b>con el motivo</b>, para no volver a activarla en seis meses. Y vuelve a generar."],
  "expl.ent2": ["Validation", "Validación"],
  "expl.pr1": ["Cuts", "Corta"],
  "expl.pr1_t": ["The history is cut into <b>four windows</b>, one after another. Each one is a small exam with its own study period.",
                 "La historia se corta en <b>cuatro ventanas</b>, una tras otra. Cada una es un examen breve con su propio período de estudio."],
  "expl.pr2": ["Re-fits", "Reajusta"],
  "expl.pr2_t": ["On the first 70% of each window the strategy re-tunes its parameters, the way it would have if it had been running back then.",
                 "Sobre el primer 70% de cada ventana la estrategia reajusta sus parámetros, como lo habría hecho si hubiera estado operando en ese momento."],
  "expl.pr3": ["Judges", "Juzga"],
  "expl.pr3_t": ["Then it trades the remaining 30% <b>without having seen it</b>. Making money there is the only thing that counts: it is the closest thing to the future.",
                 "Después opera el 30% restante <b>sin haberlo visto</b>. Ganar ahí es lo único que cuenta: es lo más parecido al futuro."],
  "expl.pr4": ["Resamples", "Remuestrea"],
  "expl.pr4_t": ["Its trades are resampled in a different order <b>1,000 times</b>. The total is always the same; what changes is how deep the hole gets along the way.",
                 "Sus operaciones se remuestrean en otro orden <b>1000 veces</b>. El total es siempre el mismo; lo que cambia es qué tan hondo es el pozo en el camino."],
  "expl.pr5": ["Verdict", "Veredicto"],
  "expl.pr5_t": ["In how many windows it won, and how much of the edge survived out-of-sample: <b>robust</b>, <b>partially robust</b> or <b>overfitted</b>. In words, before any number.",
                 "En cuántas ventanas ganó y cuánto de la ventaja sobrevivió fuera de muestra: <b>robusta</b>, <b>robustez parcial</b> o <b>sobreajustada</b>. En palabras, antes que cualquier número."],
  "expl.ent1_t": ["A market and a number of strategies are selected. The generation builds candidates, backtests each one over years of real data and keeps only those that pass the configured filters.",
                  "Se selecciona un mercado y una cantidad de estrategias. La generación arma candidatas, hace el backtest de cada una sobre años de datos reales y conserva sólo las que pasan los filtros configurados."],
  "expl.ent2_t": ["Before trusting one, it is validated on windows it never saw. Robust, partially robust or overfitted: the verdict comes in words.",
                  "Antes de confiar en una, se la valida sobre ventanas que nunca vio. Robusta, robustez parcial o sobreajustada: el veredicto se da en palabras."],
  "expl.ent3_t": ["The ones worth keeping go to My strategies, with their instrument, timeframe and costs. They survive any new generation.",
                  "Las que valen la pena van a Mis estrategias, con su instrumento, su temporalidad y sus costos. Sobreviven a cualquier generación nueva."],
  "expl.ent4_t": ["On CFDs it exports as a robot for MetaTrader 5. On crypto a robot runs it here, on the Binance demo account, and the autopilot can do the whole loop by itself.",
                  "En CFDs se exporta como robot para MetaTrader 5. En cripto un robot la ejecuta aquí, en la cuenta demo de Binance, y el piloto automático puede hacer el ciclo entero solo."],
  "pil.nada": ["It has not done anything yet.", "Todavía no hizo nada."],
  "rob.titulo": ["Robots", "Robots"],
  "rob.mirando": ["Watching", "Mirando"],
  "rob.en_posicion": ["In position · {lado}", "En posición · {lado}"],
  "rob.largo": ["long", "largo"],
  "rob.corto": ["short", "corto"],
  "rob.detenido": ["Stopped", "Detenido"],
  "ag.sub": ["What each one is doing right now. Refreshes every 30 seconds.",
             "Qué está haciendo cada uno ahora mismo. Se actualiza cada 30 segundos."],
  "ag.ciclo": ["The cycle", "El ciclo"],
  "ag.ciclo_sub": ["Generates and deploys by itself the ones already validated that remained robust, on the demo account.",
                   "Genera y activa por su cuenta las ya validadas que resultaron robustas, en la cuenta demo."],
  "ag.ciclo_on": ["Start the cycle", "Activar el ciclo"],
  "ag.ciclo_off": ["Stop the cycle", "Detener el ciclo"],
  "ag.corriendo": ["running", "en ejecución"],
  "ag.apagado": ["stopped", "detenido"],
  "ag.ahora": ["now", "ahora"],
  "ag.ciclo_encendido": ["Cycle running. It decides once a minute.", "Ciclo activo. Decide una vez por minuto."],
  "ag.ciclo_apagado": ["Cycle stopped. Nothing runs by itself.", "Ciclo detenido. Nada se ejecuta solo."],
  "ag.acc_validar": ["validated", "validó"],
  "ag.acc_promover": ["promoted and deployed", "promovió y activó"],
  "ag.acc_minar": ["started generating", "comenzó a generar"],
  "ag.acc_retirar": ["retired", "retiró"],
  "ag.acc_nada": ["waited", "esperó"],
  "ag.bots": ["Bots", "Bots"],
  "ag.sin_bots": ["No bot is running. One can be deployed below, or the cycle can do it.",
                  "Ningún bot en ejecución. Se puede activar uno abajo, o dejar que lo haga el ciclo."],
  "ag.mirando": ["watching {sim} · next candle ~{h}", "mirando {sim} · próxima vela ~{h}"],
  "ag.detenido": ["stopped", "detenido"],
  "ag.apagada": ["promoted, no bot running", "promovida, sin bot en ejecución"],
  "ag.apagadas_sub": ["They stopped when the app closed, and nothing restarts them on its own. Reactivate them after reviewing them.",
                     "Se detuvieron al cerrar la aplicación y nada las reactiva sola: reactivarlas después de revisarlas."],
  "ag.reencender": ["Reactivate {n}", "Reactivar {n}"],
  "ag.reencendidas": ["Reactivated.", "Reactivadas."],
  "ag.reencender_fallo": ["{n} did not start: {motivo}", "{n} no arrancaron: {motivo}"],

  /* VARIOS BOTS. El rótulo dice CUANTOS y no "encendido": con cinco
     corriendo, "encendido" no dice si están los cinco o quedó uno. */
  "bot.n_operando": ["{n} operating", "{n} operando"],
  "bot.maneja": ["Handles {pct}% of the account", "Maneja el {pct}% de la cuenta"],
  "bot.reparto": [
    "{usado}% of the account is committed, {libre}% free.",
    "El {usado}% de la cuenta está comprometido, queda {libre}% libre."],
  "bot.apagar_todos": ["Stop them all", "Detenerlos a todos"],
  "bot.porcion": ["Share of the account (%)", "Porción de la cuenta (%)"],
  "bot.porcion_nota": [
    "Each bot sizes its risk on ITS share, not on the whole balance. Fixed when it starts: deploying a new bot must not resize one that already has a position open.",
    "Cada bot calcula su riesgo sobre SU porción, no sobre el saldo entero. Se fija al activarlo: activar uno nuevo no puede cambiarle el tamaño a otro que ya tiene una posición abierta."],
  "bot.sin_lugar": ["No room for another one", "No hay lugar para otro"],
  "bot.sin_lugar_sub": [
    "Either every slot is taken or the account is fully committed. Stopping one frees up its share.",
    "O están todos los lugares ocupados, o la cuenta está comprometida entera. Detener uno libera su porción."],

  "bot.casa": ["Exchange", "Exchange"],
  "bot.casa_bingx": ["BingX", "BingX"],
  "bot.casa_binance": ["Binance (demo only)", "Binance (sólo demo)"],
  "bot.casa_binance_nota": [
    "On Binance the app only trades the demo environment, with simulated funds. There is no way to send it a real order.",
    "En Binance la aplicación sólo opera el entorno demo, con fondos simulados. No tiene forma de enviarle una orden real."],

  "ex.bn_t": ["Binance (demo only)", "Binance (sólo demo)"],
  "ex.bn_sub": [
    "Simulated funds on Binance's demo environment. The app has no way to send a real order to Binance.",
    "Fondos simulados en el entorno demo de Binance. La aplicación no tiene forma de enviarle una orden real."],
  "ex.bn_crear": ["Create the demo key", "Crear la clave demo"],
  "ex.bn_ver": ["Watch it execute", "Ver cómo ejecuta"],
  "ex.bn_nota": [
    "The demo key is created on demo.binance.com, not on binance.com: that one belongs to the real account. The second link opens the screen where the order can be watched landing.",
    "La clave demo se crea en demo.binance.com, no en binance.com: esa corresponde a la cuenta real. El segundo enlace abre la pantalla donde se ve aparecer la orden."],

  "ex.sub": ["Connect an exchange so a strategy can trade on its own",
             "Conectar un exchange para que una estrategia opere sola"],
  "ex.regla1_t": ["The keys stay on this computer",
                  "Las claves se quedan en esta computadora"],
  "ex.regla1": ["They are encrypted with the Windows account and never reach our servers. Nobody else on this machine can read them.",
                "Se cifran con la cuenta de Windows y no llegan nunca a nuestros servidores. Nadie más en esta máquina puede leerlas."],
  "ex.regla2_t": ["Create the key WITHOUT withdrawal permission",
                  "Crear la clave SIN permiso de retiro"],
  "ex.regla2": ["Reading and trading is all it needs. With withdrawal disabled, even a stolen key cannot take the funds out.",
                "Con lectura y trading alcanza. Sin retiro, ni siquiera una clave robada puede sacar los fondos."],
  "ex.regla3_t": ["Start on the practice account",
                  "Empezar en la cuenta de práctica"],
  "ex.regla3": ["Binance has a demo environment with simulated funds and the same API, and Botiquant only accepts Binance in demo. Running it there for a few weeks comes before risking anything anywhere.",
                "Binance tiene un entorno demo con fondos simulados y la misma API, y Botiquant sólo acepta Binance en demo. Conviene operar ahí unas semanas antes de arriesgar nada en ningún lado."],
  "ex.practica": ["Practice account", "Cuenta de práctica"],
  "ex.practica_sub": ["Simulated funds, real market data", "Fondos simulados, mercado real"],
  "ex.real": ["Live account", "Cuenta real"],
  "ex.real_sub": ["Real capital. Only after the practice account has proven it.",
                  "Dinero real. Sólo después de que la práctica lo haya demostrado."],
  "ex.api_key": ["API Key", "API Key"],
  "ex.secret": ["Secret Key", "Secret Key"],
  "ex.vacia": ["not set", "sin cargar"],
  "ex.cargada": ["set · ends in {cola}", "cargada · termina en {cola}"],
  "ex.ilegible": ["saved on another machine", "guardada en otra máquina"],
  "ex.guardar": ["Save", "Guardar"],
  "ex.probar": ["Check connection", "Comprobar conexión"],
  "ex.borrar": ["Remove", "Quitar"],
  "ex.guardada": ["Key saved and encrypted", "Clave guardada y cifrada"],
  "ex.borrada": ["Key removed from this computer", "Clave borrada de esta computadora"],
  "ex.faltan": ["Both fields are needed", "Hacen falta los dos campos"],
  "ex.borrar_seguro": ["Remove this key from the computer?",
                       "¿Quitar esta clave de la computadora?"],
  "ex.paso_responde": ["The exchange responds", "El exchange responde"],
  "ex.paso_clave": ["The key is loaded", "La clave está cargada"],
  "ex.paso_saldo": ["Key and signature work", "La clave y la firma funcionan"],
  "ex.paso_modo": ["Position mode", "Modo de posición"],
  "ex.modo_una_via": ["one-way", "una vía"],
  "ex.modo_cobertura": ["hedge (two-way)", "cobertura (dos vías)"],
  "ex.det_velas": ["{n} candles", "{n} velas"],
  "ex.det_disponible": ["{n} available", "{n} disponible"],
  "ex.det_ninguna": ["none open", "ninguna abierta"],
  "ex.det_una": ["one open", "hay una abierta"],
  "ex.det_abiertas": ["{n} open", "{n} abiertas"],
  "ex.paso_posiciones": ["Open positions", "Posiciones abiertas"],
  "bot.sin_cripto": ["No crypto strategy saved yet",
                     "Todavía no hay ninguna estrategia de cripto guardada"],
  /* NO ENUMERA LOS PARES. Decía "BTCUSDT o ETHUSDT" cuando eran los dos
     únicos, y con trece quedó mintiendo: mandaba a minar sobre dos de trece.
     Un texto que lista opciones envejece cada vez que se agrega una. */
  "bot.sin_cripto_sub": ["A crypto exchange cannot trade indices or metals. Generate on one of the perpetuals and save the strategy, and it will appear here.",
                         "Un exchange de cripto no opera índices ni metales. Generar sobre alguno de los perpetuos y guardar la estrategia: entonces aparece aquí."],
  "bot.acc_nada": ["waited", "esperó"],
  /* LAS FRASES DEL MOTOR, EN EL IDIOMA DE LA PANTALLA. El motor escribe en
     español; acá se reconocen y se dicen en el idioma elegido. */
  "mot.sin_senal": ["no signal", "sin señal"],
  "mot.posicion_sin_salida": ["position open, no exit signal", "posición abierta, sin señal de salida"],
  "mot.pocas_velas": ["not enough candles yet", "todavía no hay suficientes velas"],
  "mot.sin_velas": ["no closed candles yet", "todavía no hay velas cerradas"],
  "mot.sin_capital": ["no capital available", "sin capital disponible"],
  "mot.adopto": ["took over an open {lado} position it did not open ({cant}); it closes it with the strategy's rules", "adoptó una posición {lado} abierta que no abrió ({cant}); la cierra con las reglas de la estrategia"],
  "ciclo.sin_probar": ["{n} not validated yet", "{n} sin validar"],
  "ciclo.hay_lugar": ["{h} free slot(s) and {n} validated waiting", "hay {h} lugar(es) libre(s) y {n} validada(s) esperando"],
  "ciclo.al_tope": ["{n} instrument(s) already at their cap", "{n} instrumento(s) ya al tope"],
  "ciclo.inoperables": ["{n} the robot cannot run", "{n} que el robot no puede activar"],
  "ciclo.toca_minar": ["{h} hours since the last generation", "pasaron {h} horas de la última generación"],
  "ciclo.proximo": ["next generation in {h} hours", "la próxima generación en {h} horas"],
  "ciclo.nada": ["nothing to do", "nada que hacer"],
  "mot.detenido": ["stopped: {resto}", "detenido: {resto}"],
  "mot.apagado_exchange": ["stopped by the exchange", "apagado por el exchange"],
  "mot.firma_invalida": [
    "Binance rejects the signature (-1022): the secret does not match this key. Remove the key and paste key and secret again, fresh from Binance. If that was just done, check that Windows sets the time automatically.",
    "Binance rechaza la firma (-1022): el secreto no corresponde a esta clave. Quitar la clave y volver a pegar clave y secreto recién copiados de Binance. Si ya se hizo, revisar que Windows ponga la hora automáticamente."],
  "mot.clave_invalida": [
    "Binance does not accept this key (-2015): it does not exist, it is not a demo key, or it lacks Futures permission.",
    "Binance no acepta esta clave (-2015): no existe, no es de la cuenta demo, o no tiene permiso de Futuros."],
  "mot.hora_corrida": [
    "Binance reports this computer's clock is off (-1021). Enable automatic time in Windows and retry.",
    "Binance informa que el reloj de esta computadora está desfasado (-1021). Activar la hora automática en Windows y reintentar."],
  "mot.largo": ["long", "larga"],
  "mot.corto": ["short", "corta"],
  "bot.acc_largo": ["opened long", "abrió largo"],
  "bot.acc_corto": ["opened short", "abrió corto"],
  "bot.acc_cerrar": ["closed", "cerró"],
  "bot.acc_panico": ["panic stop", "pánico"],
  "bot.tope": ["Daily loss limit", "Tope de pérdida diaria"],
  "bot.no_ofrecidas": [
    "{n} more are not offered here: {t} use a trailing stop (the robot cannot run it yet) and {c} do not pass the practice gate.",
    "{n} más no se ofrecen aquí: {t} usan trailing (el robot todavía no lo ejecuta) y {c} no pasan la puerta de práctica."],
  "bot.tope_nota": ["In account currency. When the day's REALISED losses reach it, the bot stops until tomorrow. 0 means no limit. Floating losses do not count: that is what the stop is for.",
                    "En la moneda de la cuenta. Cuando las pérdidas REALIZADAS del día llegan ahí, el bot se detiene hasta mañana. 0 es sin tope. Las pérdidas flotantes no cuentan: para eso está el stop."],
  "bot.no_habilitado": ["not qualified yet", "todavía no habilitada"],
  "bot.falta_clave_larga": ["The API key for that account must be loaded above.",
                            "Hace falta cargar arriba la clave de esa cuenta."],
  "bot.vig_titulo": ["Not trading as measured:", "No opera como se midió:"],
  "bot.title": ["Run a strategy", "Operar una estrategia"],
  "bot.sub": ["It trades while this app is open. Closing the app stops it.",
              "Opera mientras esta aplicación esté abierta. Al cerrarla, para."],
  "bot.on": ["running", "activo"],
  "bot.off": ["stopped", "detenido"],
  "bot.detenido": ["stopped itself", "se detuvo solo"],
  "bot.estrategia": ["Strategy", "Estrategia"],
  "bot.modo": ["Mode", "Modo"],
  "bot.elegir": ["Choose…", "Seleccionar…"],
  "bot.sin_clave": ["no key loaded", "sin clave cargada"],
  "bot.modo_simulacro": ["Dry run — decides but never orders",
                         "Simulacro — decide pero no envía órdenes"],
  "bot.modo_practica": ["Practice account", "Cuenta de práctica"],
  "bot.modo_real": ["Live account — real capital", "Cuenta real — dinero real"],
  "bot.encender": ["Deploy", "Activar"],
  "bot.apagar": ["Stop", "Detener"],
  "bot.panico": ["Stop and close position", "Detener y cerrar posición"],
  "bot.apagar_nota": ["Stopping leaves any open position alone, with its stop still on the exchange. Use the other button to close it too.",
                      "Detener deja la posición abierta como está, con su stop puesto en el exchange. Para cerrarla también, usar el otro botón."],
  "bot.encendido": ["Bot deployed", "Bot activado"],
  "bot.apagado": ["Bot stopped", "Bot detenido"],
  "bot.panico_hecho": ["Stopped and position closed", "Detenido y posición cerrada"],
  "bot.falta_elegir": ["Select a strategy and a mode", "Seleccionar una estrategia y un modo"],
  "bot.no_esta": ["That strategy is no longer saved", "Esa estrategia ya no está guardada"],
  "bot.real_seguro": ["This will trade with REAL capital. Did the practice account justify it first?",
                      "Esto opera con dinero REAL. ¿La cuenta de práctica lo justificó antes?"],
  "bot.panico_seguro": ["Stop the bot and close the open position at market?",
                        "¿Detener el bot y cerrar la posición abierta a mercado?"],
  "nav.tips": ["Documentation", "Documentación"],
  "tips.sub": [
    "What we learned by measuring, not what everyone repeats.",
    "Lo que aprendimos midiendo, no lo que se repite por ahí."],
  "tips.foot": [
    "Every figure here was measured on the instruments the app ships with. Individual numbers will differ; the direction will not.",
    "Todas las cifras de aquí se midieron sobre los instrumentos que trae la aplicación. Los números propios serán otros; la dirección no."],

  "tip.historia": ["Choose the window with intent", "Elegir la ventana a conciencia"],
  "tip.historia_cuerpo": [
    "The period used for generation sets what the generation can find. A short window produces higher returns, because the strategy only has to work through the conditions of those few years. The whole history forces it to survive rallies, crashes and flat windows: fewer make it through, and the ones that do carry more behind them.\n\nNeither is the right answer. Generate over a short period to see what an instrument can give; generate over a long one when choosing something to actually run.",
    "El período sobre el que se genera define lo que la generación puede encontrar. Una ventana corta da retornos más altos, porque la estrategia sólo tiene que funcionar en las condiciones de esos pocos años. Todo el histórico obliga a sobrevivir subidas, derrumbes y ventanas planas: pasan menos, y las que pasan llevan más detrás.\n\nNinguna de las dos es la respuesta correcta. Generar sobre un período corto para ver qué puede dar un instrumento; generar sobre uno largo al elegir algo para poner a operar."],

  "tip.horario": ["The hour changes everything", "El horario cambia todo"],
  "tip.horario_cuerpo": [
    "An index at three in the morning trades with a fraction of the volume and a much wider spread than at the New York open. They are different markets wearing the same name, and a rule built for one has no reason to work in the other.\n\nRestricting the hours narrows what the generation can look at, so it finds fewer strategies — and the ones it finds only have to work in conditions that resemble each other.",
    "Un índice a las tres de la mañana cotiza con una fracción del volumen y un spread mucho más ancho que en la apertura de Nueva York. Son mercados distintos con el mismo nombre, y una regla armada para uno no tiene por qué funcionar en el otro.\n\nRestringir el horario achica lo que la generación puede mirar, así que encuentra menos estrategias — y las que encuentra sólo tienen que funcionar en condiciones que se parecen entre sí."],

  "tip.spread": ["Set the spread for each instrument", "El spread va por instrumento"],
  "tip.spread_cuerpo": [
    "Costs are expressed in the instrument's own price units, and those units are not comparable across markets: what counts as a normal spread on a currency pair is a rounding error on an index, and the other way round.\n\nSwitching instruments without updating the cost raises no error. The generation simply runs against a cost that is not the one actually paid. The app suggests one per instrument — accept it, and check it against the broker.",
    "Los costos se expresan en las unidades de precio del propio instrumento, y esas unidades no son comparables entre mercados: lo que es un spread normal en un par de divisas es un error de redondeo en un índice, y al revés.\n\nCambiar de instrumento sin actualizar el costo no da ningún error. La generación simplemente corre contra un costo que no es el que se paga en realidad. La aplicación sugiere uno por instrumento: conviene aceptarlo, y comprobarlo contra el bróker."],

  "tip.vara": ["Raise the threshold gradually", "Subir el umbral de a poco"],
  "tip.vara_cuerpo": [
    "Return over drawdown is the filter worth demanding: it joins both halves of the question — how much it made and how much drawdown it required — into one number that does not move when risk per trade changes.\n\nHow high the threshold can go depends entirely on the instrument and the period. Start low, watch how many candidates get through, and raise it from there. While the generation runs it reports which filter is holding everything back, so there is no need to guess.",
    "Retorno sobre drawdown es el filtro que conviene exigir: junta las dos mitades de la pregunta —cuánto ganó y cuánto drawdown exigió— en un solo número que no se mueve al cambiar el riesgo por operación.\n\nHasta dónde se puede subir el umbral depende por completo del instrumento y del período. Conviene arrancar bajo, observar cuántas candidatas entran, y subirlo desde ahí. Mientras la generación corre, informa cuál es el filtro que está frenando todo, así que no hace falta adivinar."],

  "tip.riesgo": ["Risk scales both halves", "El riesgo escala las dos mitades"],
  "tip.riesgo_cuerpo": [
    "Raising risk per trade does not find a better strategy: it runs the same one bigger. Return and drawdown grow together, near enough in step, so the shape of the equity curve stays exactly as it was — only the scale changes.\n\nWhich means risk is not the knob to turn when the results disappoint. Change the instrument, the timeframe or the exits.",
    "Subir el riesgo por operación no encuentra una estrategia mejor: corre la misma más grande. Rendimiento y drawdown crecen juntos, casi al mismo ritmo, así que la forma de la curva de capital queda igual que estaba — lo único que cambia es la escala.\n\nO sea que el riesgo no es la perilla que hay que mover cuando el resultado decepciona. Conviene cambiar el instrumento, la temporalidad o las salidas."],

  "tip.zona": ["The broker's clock is not UTC", "El reloj del bróker no está en UTC"],
  "tip.zona_cuerpo": [
    "This matters only for strategies with a trading-hours restriction. The price data here is UTC; MetaTrader stamps its bars in the <b>broker's server time</b>, and most brokers run on UTC+2 or UTC+3. The local timezone is irrelevant — two people in different countries with the same broker get identical backtests.",
    "Esto importa sólo en estrategias con restricción de horario. Los datos de precio de aquí están en UTC; MetaTrader fecha sus velas con la <b>hora del servidor del bróker</b>, y la mayoría corre en UTC+2 o UTC+3. La zona horaria propia no influye: dos personas en países distintos con el mismo bróker obtienen backtests idénticos."],

  /* ------------------------------------------------- las dos mitades de Minado */
  /* --------------------------------------- instrumentos que trae la aplicación
     El nombre y la descripción de cada instrumento viven acá y no en el
     catálogo del servidor. Estaban del otro lado, en español fijo, y en la
     versión en inglés la pantalla de Datos mostraba "ÍNDICES" y "spread típico
     0.36 puntos" en medio de una interfaz en inglés.

     El servidor conserva lo que de verdad le importa —símbolo, fechas, spread,
     distancias— y la categoría como CLAVE, no como rótulo. */
  "cat.otros": ["Other", "Otros"],
  "famsub.indices": ["stock index CFDs, for MetaTrader",
                     "CFDs de índices bursátiles, para MetaTrader"],
  "famsub.forex": ["currency pairs, for MetaTrader",
                   "pares de divisas, para MetaTrader"],
  "famsub.bonos": ["government bond CFDs, for MetaTrader",
                   "CFD de bonos de gobierno, para MetaTrader"],
  "famsub.energia": ["energy CFDs, for MetaTrader",
                     "CFD de energía, para MetaTrader"],
  "famsub.metals": ["gold and silver CFDs, for MetaTrader",
                    "CFDs de metales, para MetaTrader"],
  "famsub.crypto": ["crypto CFDs, for MetaTrader — spread, no funding",
                    "CFDs de cripto, para MetaTrader — spread, sin funding"],
  "famsub.perpetuos": ["perpetual futures, for an exchange — commission and funding",
                       "futuros perpetuos, para un exchange — comisión y funding"],
  "cat.indices": ["Indices", "Índices"],
  "cat.forex": ["Forex", "Forex"],
  "cat.metals": ["Metals", "Metales"],
  "cat.crypto": ["Crypto CFD", "Cripto CFD"],
  "cat.bonos": ["Bonds", "Bonos"],
  "cat.energia": ["Energy", "Energía"],

  /* El distintivo del instrumento que más estrategias produce. El texto tiene
     que ser cierto: sale de medir los cuatro con la misma vara sobre los datos
     que trae la aplicación. */
  "inst.mejor": ["Best yield", "Más estrategias"],
  "inst.mejor_ayuda": [
    "Of the four instruments included, this one produces the most profitable strategies under the same filters.",
    "De los cuatro instrumentos incluidos, es el que más estrategias rentables produce con los mismos filtros."],

  "inst.sp500": [
    "S&P 500 index CFD — typical spread 0.36 points",
    "CFD del índice S&P 500 — spread típico 0.36 puntos"],
  "inst.eurusd": [
    "Euro / US Dollar — the most traded pair, typical spread 1.2 pips",
    "Euro / dólar — el par más operado, spread típico 1.2 pips"],
  "inst.xauusd": [
    "Gold / US Dollar — spot gold, typical spread 25 cents",
    "Oro / dólar — oro spot, spread típico 25 centavos"],
  "inst.btcusd": [
    "Bitcoin / US Dollar — wide spread, careful with scalping",
    "Bitcoin / dólar — spread ancho, cuidado con el scalping"],

  /* Los tres que se agregaron para que el portafolio DIVERSIFIQUE. La
     descripción dice lo que los hace distintos de los otros cuatro, que es el
     único motivo por el que están: no son más instrumentos, son otras
     apuestas. Los números salen de medir la correlación de retornos diarios
     2021-2025 contra los cuatro originales. */
  "inst.gas": [
    "Natural gas — the least correlated of all: weather and storage move it, and they move nothing else",
    "Gas natural — el menos correlacionado de todos: lo mueven el clima y el almacenamiento, que no mueven nada más"],
  "inst.bund": [
    "German 10-year bond — fixed income, the one asset class the catalogue was missing",
    "Bono alemán a 10 años — renta fija, la única familia que faltaba en el catálogo"],
  "inst.wti": [
    "WTI crude oil — moves with the world, not with US stocks",
    "Petróleo WTI — se mueve con el mundo, no con la bolsa estadounidense"],

  /* Los perpetuos de exchange. La descripción dice lo que los distingue de un
     CFD y no una obviedad: que cobran o pagan por MANTENER la posición, y que
     esa tasa históricamente le paga al lado corto. Medido sobre siete años de
     BTCUSDT: media +11,61% anual cobrada por los vendedores. */
  "inst.btcusdt": [
    "Bitcoin perpetual — 24/7, and funding pays the short side (+11.6% a year on average)",
    "Bitcoin perpetuo — 24/7, y el funding le paga al lado corto (+11,6% anual de media)"],
  "inst.ethusdt": [
    "Ethereum perpetual — same funding mechanics as Bitcoin, more movement",
    "Ethereum perpetuo — mismo funding que Bitcoin, más movimiento"],
  /* LOS ONCE QUE SE SUMARON EL 1/9/2026. Cada descripción dice el funding
     MEDIDO de esa moneda y no una obviedad, porque es el dato que cambia si
     una familia de estrategias es rentable o no — y NO va en la misma
     dirección en todas: en Monero le paga al corto un 16,6% anual y en Zcash
     se lo cobra un 2,2%. Medido sobre los últimos 1000 cobros de cada una. */
  "inst.solusdt": [
    "Solana perpetual — funding is roughly neutral (-0.3% a year), unusual among these",
    "Solana perpetuo — el funding es casi neutro (-0,3% anual), raro entre estos"],
  "inst.zecusdt": [
    "Zcash perpetual — funding CHARGES the short side (-2.2% a year): a short starts behind",
    "Zcash perpetuo — el funding le COBRA al lado corto (-2,2% anual): un corto arranca en contra"],
  "inst.xrpusdt": [
    "XRP perpetual — funding barely tilts either way (+0.2% a year)",
    "XRP perpetuo — el funding casi no se inclina para ningún lado (+0,2% anual)"],
  "inst.dogeusdt": [
    "Dogecoin perpetual — funding pays the short side (+3.8% a year)",
    "Dogecoin perpetuo — el funding le paga al lado corto (+3,8% anual)"],
  "inst.arbusdt": [
    "Arbitrum perpetual — the shortest history here: listed in 2023",
    "Arbitrum perpetuo — la historia más corta de todos: cotiza desde 2023"],
  "inst.uniusdt": [
    "Uniswap perpetual — funding pays the short side (+4.4% a year)",
    "Uniswap perpetuo — el funding le paga al lado corto (+4,4% anual)"],
  "inst.bnbusdt": [
    "BNB perpetual — the exchange's own token, funding pays the short side (+3.4% a year)",
    "BNB perpetuo — el token del propio exchange, y el funding le paga al lado corto (+3,4% anual)"],
  "inst.suiusdt": [
    "Sui perpetual — listed in 2023, funding pays the short side (+2.8% a year)",
    "Sui perpetuo — cotiza desde 2023, y el funding le paga al lado corto (+2,8% anual)"],
  "inst.xmrusdt": [
    "Monero perpetual — the most extreme funding here: +16.6% a year to the short side",
    "Monero perpetuo — el funding más extremo de todos: +16,6% anual al lado corto"],
  "inst.adausdt": [
    "Cardano perpetual — funding pays the short side (+1.0% a year)",
    "Cardano perpetuo — el funding le paga al lado corto (+1,0% anual)"],
  "inst.linkusdt": [
    "Chainlink perpetual — funding pays the short side (+4.8% a year)",
    "Chainlink perpetuo — el funding le paga al lado corto (+4,8% anual)"],

  "cat.perpetuos": ["Crypto perpetuals", "Perpetuos de cripto"],

  "data.ready": ["{nombre}: {n} bars ready", "{nombre}: {n} velas listas"],
  "ui.n_bars": ["{n} bars", "{n} velas"],
  "data.bars_of": ["{n} {tf} bars", "{n} velas de {tf}"],
  "tf.1m": ["1-minute", "1 minuto"],
  "tf.5m": ["5-minute", "5 minutos"],
  "tf.15m": ["15-minute", "15 minutos"],
  "tf.30m": ["30-minute", "30 minutos"],
  "tf.1h": ["1-hour", "1 hora"],
  "tf.4h": ["4-hour", "4 horas"],
  "tf.1d": ["daily", "1 día"],
  "tf.native": ["native", "nativo"],

  "data.broker": ["The broker's clock", "El reloj del bróker"],
  "data.broker_hint": ["set once, used by every exported robot",
                       "se pone una vez y la usan todos los robots exportados"],
  "data.broker_help": [
    "The price data here is UTC. MetaTrader stamps its bars in the <b>broker's server time</b>, and most brokers run two or three hours ahead. The local timezone plays no part: two people in different countries with the same broker get identical backtests.",
    "Los datos de precio de aquí están en UTC. MetaTrader fecha sus velas con la <b>hora del servidor del bróker</b>, y la mayoría va dos o tres horas adelantada. La zona horaria propia no interviene: dos personas en países distintos con el mismo bróker obtienen backtests idénticos."],
  "data.broker_offset": ["Broker server", "Servidor del bróker"],
  "data.broker_now": ["Right now it would be", "Ahora mismo serían las"],
  "data.broker_note": [
    "Compare that time with the clock in MetaTrader's Market Watch. When they match, the setting is right — and it only matters for strategies with a trading-hours restriction.",
    "Comparar esa hora con el reloj de Observación de Mercado en MetaTrader. Cuando coinciden, el valor es el correcto — y sólo importa en estrategias con restricción de horario."],
  "data.broker_saved": ["Saved. Robots exported from now on carry it.",
                        "Guardado. Los robots exportados de ahora en más lo llevan."],
  "mine.tab_search": ["Generation", "Generación"],
  "mine.tab_results": ["Candidates", "Candidatas"],
  "exp.pine_copied": ["Pine copied — paste it into TradingView's Pine Editor",
                      "Pine copiado — pegar en el Pine Editor de TradingView"],
  "saved.mined_on": ["Generated on {fecha}", "Generada el {fecha}"],
  /* El aviso de que el robot ya está puesto. Es el momento más importante de
     la aplicación —la persona acaba de conseguir lo que vino a buscar— y estas
     cuatro frases estaban escritas a mano en castellano, al lado de
     "Open in MetaEditor", que sí se traducía. */
  "exp.in_terminal": ["{terminal} Experts folder · it already shows in the Navigator",
                      "Robots de {terminal} · ya aparece en el Navegador"],
  "exp.change": ["change", "cambiar"],
  "exp.downloads": ["Downloads", "Descargas"],
  "exp.open_folder": ["Open the folder", "Ver la carpeta"],
  /* La misma frase que `bank.from_bank` pero para una corrida recién
     terminada: no salió del banco todavía, así que decir "del banco" sería
     falso. */
  "bank.from_run": ["{corrida} · risk {riesgo}", "{corrida} · riesgo {riesgo}"],

  "exp.open_editor": ["Open in MetaEditor", "Abrir en MetaEditor"],
  "exp.open_file": ["Open file", "Abrir archivo"],
  "exp.saved_in": ["{archivo} saved in {carpeta}", "{archivo} guardado en {carpeta}"],
  "col.status": ["Status", "Estado"],
  /* DONDE ESTA en el camino, que es otra cosa que cómo le fue en la prueba.
     Sin esto una retirada se veía igual que una viva. */
  "camino.validada": ["Validated", "Validada"],
  "camino.practica": ["Running on demo", "Operando en demo"],
  "camino.produccion": ["Running live", "Operando en real"],
  "camino.retirada": ["Retired", "Retirada"],

  "est.sin_probar": ["Not validated", "Sin validar"],
  "est.aprobada": ["Robust", "Robusta"],
  "est.aceptable": ["Partially robust", "Robustez parcial"],
  "est.no_paso": ["Overfitted", "Sobreajustada"],
  "est.help": [
    "Whether the strategy still worked on data it had never seen.",
    "Si la estrategia siguió funcionando sobre datos que nunca había visto."],

  "wf.frase_ruina": [
    "It made money in {g} of {n} windows, but resampling its own trades a plausible bad run consumes {dd}% of the account. Not worth deploying as is.",
    "Ganó en {g} de {n} ventanas, pero al remuestrear sus propias operaciones una racha mala plausible se come el {dd}% de la cuenta. No conviene operarla así."],
  "wf.frase_aprobada": [
    "It made money in {g} of {n} windows it had never seen, and kept most of what it was earning.",
    "Ganó en {g} de {n} ventanas que nunca había visto, y conservó la mayor parte de lo que rendía."],
  "wf.frase_aceptable_ef": [
    "It made money in all {n} windows, but earned considerably less out-of-sample than in-sample. Worth keeping; not worth trusting blindly.",
    "Ganó en las {n} ventanas, pero fuera de muestra rindió bastante menos que dentro. Vale conservarla; no para asignarle capital a ciegas."],
  "wf.frase_aceptable_tramos": [
    "It made money in {g} of {n} windows. Worth keeping; not worth trusting blindly.",
    "Ganó en {g} de {n} ventanas. Vale conservarla; no para asignarle capital a ciegas."],
  "wf.frase_no_paso_tramos": [
    "It only made money in {g} of {n} windows: it was describing the past.",
    "Sólo ganó en {g} de {n} ventanas: estaba describiendo el pasado."],
  "wf.frase_no_paso_ef": [
    "It made money in {g} of {n} windows, but almost none of its edge survived outside the data it was found on.",
    "Ganó en {g} de {n} ventanas, pero casi nada de su ventaja sobrevivió fuera de los datos donde se la encontró."],

  /* LOS DIBUJOS DE LA PRUEBA. Las palabras van con su definición al pasar
     el mouse: "tramo" y "fuera de muestra" no se explican solas. */
  "wf.tramo": ["Window {n}", "Ventana {n}"],
  "wf.tramo_tip": [
    "Re-fitted there: {adentro}. Judged on data it never saw: {afuera} over {ops} trades, worst drawdown {caida}%.",
    "Reajustada ahí: {adentro}. Juzgada sobre datos que nunca vio: {afuera} en {ops} operaciones, peor drawdown {caida}%."],
  "wf.d_tramos": ["The four windows", "Las cuatro ventanas"],
  "wf.d_tramos_help": [
    "The history is cut in four. In each window the strategy is re-fitted on the grey part and then judged on the coloured part, which it had never seen. Green: it made money there. Red: it did not.",
    "La historia se corta en cuatro. En cada ventana la estrategia se reajusta sobre la parte gris y después se la juzga sobre la parte de color, que nunca había visto. Verde: ganó ahí. Rojo: no."],
  "wf.d_afuera": ["Equity on data it never saw", "Capital sobre datos que nunca vio"],
  "wf.d_afuera_help": [
    "The four judged windows stitched together, one after another. This is the closest thing to how it would have done live.",
    "Las cuatro ventanas de juicio cosidas una tras otra. Es lo más parecido a cómo le habría ido en vivo."],
  "wf.d_mc": ["Same trades, resampled 1,000 times", "Las mismas operaciones, remuestreadas 1000 veces"],
  "wf.d_mc_help": [
    "The total profit is identical every time; what changes is the path. The band shows how deep the hole could have been before it paid off.",
    "Las mismas operaciones, en otro orden y con repetición; lo que se mira es el camino. La banda muestra qué tan hondo pudo ser el pozo antes de que pagara."],
  "wf.test_it": ["Validate", "Validar"],
  "wf.retest": ["Revalidate", "Revalidar"],
  "wf.testing": ["Validating", "Validando"],
  "wf.done": ["{nombre} validated", "{nombre} validada"],
  "wf.untested": ["This one has not been validated yet", "Esta todavía no se validó"],
  "wf.untested_sub": [
    "The generation chose it by looking at this whole period, so its numbers here are flattering by construction. Validation refits it window by window and judges it on data it never saw.",
    "La generación la eligió mirando todo este período, así que sus números aquí son favorables por construcción. La validación la reajusta por ventanas y la juzga sobre datos que nunca vio."],

  "wf.m_efficiency": ["Efficiency", "Eficiencia"],
  "wf.m_efficiency_help": [
    "How much of the in-sample performance survived out-of-sample. 1.0 means it survived whole; 0.5 is normal and healthy; near 0 means the strategy was describing the past.",
    "Cuánto del rendimiento sobrevivió fuera de muestra. 1.0 es que sobrevivió entero; 0.5 es lo normal y sano; cerca de 0 es que la estrategia describía el pasado."],
  "wf.m_consistency": ["Winning windows", "Ventanas ganadoras"],
  "wf.m_oos_return": ["Return in the robustness validation", "Retorno en la validación de robustez"],
  "wf.m_oos_return_help": [
    "Stitched from the newer part of each fold of this validation, over its own window — which is not the window the generation kept for later. Two honest numbers over two different periods.",
    "Cosido con la parte nueva de cada fold de esta validación, sobre su propia ventana — que no es la ventana que se guardó la generación. Dos números honestos sobre dos períodos distintos."],
  "wf.m_tramo_guardado": ["Window the generation kept", "Ventana que se guardó la generación"],
  "wf.tramo_ventana": ["Measured over {desde} → {hasta}.", "Medido sobre {desde} → {hasta}."],
  "wf.m_bad_run": ["p95 drawdown", "Drawdown p95"],
  "wf.dd_malo_corto": ["p95 drawdown", "drawdown p95"],
  "wf.m_bad_run_help": [
    "From 1,000 resamples: the same trades dealt in a different order a thousand times. The total profit comes out identical every time — what changes is the path, so this is how deep the hole could have been before it paid off.",
    "De 1000 remuestreos: las mismas operaciones repartidas en otro orden mil veces. Las mismas operaciones en otro orden y con repetición — lo que se mira es el camino, así que esto es qué tan hondo pudo haber sido el pozo antes de que empezara a pagar."],
  "wf.tested_on": [
    "Validated over {desde} → {hasta}, on {cuando}.",
    "Validada sobre {desde} → {hasta}, el {cuando}."],
  "wf.que_mide": [
    "In each window the validation re-tunes the numbers on the older data and grades them on the newer. So what it measures is whether this KIND of rule survives out-of-sample, not these exact numbers: two strategies built on the same rule can get the same verdict. The annual return above is from these numbers.",
    "En cada ventana la validación vuelve a ajustar los números sobre los datos viejos y los califica sobre los nuevos. Lo que mide, entonces, es si esta CLASE de regla sobrevive fuera de muestra, no estos números exactos: dos estrategias armadas sobre la misma regla pueden sacar el mismo veredicto. El retorno anual de arriba sí es de estos números."],
  "wf.ruin_warn": [
    "In <b>{pct}%</b> of the resamples the account lost a third of its capital before recovering. That is a real account somebody closes.",
    "En el <b>{pct}%</b> de los remuestreos la cuenta perdió un tercio del capital antes de recuperarse. Eso es una cuenta real que alguien cierra."],

  /* LAS CUATRO ETAPAS DEL CAMINO, que también son los filtros de la lista. */
  "etapa.por_probar": ["Pending", "Pendientes"],
  "etapa.por_probar_sub": ["newly generated · awaiting validation", "recién generadas · esperan validación"],
  "etapa.aprobadas": ["Validated", "Validadas"],
  "etapa.aprobadas_sub": ["{n} partially robust", "{n} con robustez parcial"],
  "etapa.aprobadas_sub0": ["the edge survived out-of-sample", "la ventaja sobrevivió fuera de muestra"],
  "etapa.operando": ["Live", "En operación"],
  "etapa.operando_sub": ["with a bot on the account", "con un robot en la cuenta"],
  "etapa.descartadas": ["Discarded", "Descartadas"],
  "etapa.descartadas_sub": ["{n} retired with a reason", "{n} retiradas con motivo"],
  "etapa.descartadas_sub0": ["did not pass validation", "no superaron la validación"],
  "etapa.todas": ["Show all {n}", "Ver todas · {n}"],
  "etapa.todas_corto": ["all", "todas"],
  "sel.rapida": ["Select:", "Seleccionar:"],
  "etapa.vacia": ["Nothing in this stage yet.", "Todavía no hay nada en esta etapa."],
  "saved.probar_faltan": ["Validate the {n} missing", "Validar las {n} que faltan"],
  "saved.probando_faltan": ["Validating the {n}, one after another…", "Validando las {n}, una tras otra…"],
  "sel.probar": ["Validate {n}", "Validar {n}"],
  "sel.borrar": ["Delete {n}", "Borrar {n}"],
  "sel.borradas": ["{n} deleted", "{n} borradas"],
  "sel.confirm_delete": ["Delete {n} strategies? This cannot be undone.", "¿Borrar {n} estrategias? No se puede deshacer."],
  "sel.en_cola": ["Validating {n} one after another. The app remains usable.", "Validando {n} una tras otra. La aplicación sigue disponible."],
  "sel.resumen": ["{a} robust · {m} partially robust · {f} overfitted", "{a} robustas · {m} con robustez parcial · {f} sobreajustadas"],
  "sel.errores": ["{n} could not be validated", "{n} no se pudieron validar"],
  "sel.esperando": ["Waiting for the server to free up…", "Esperando que el servidor se libere…"],
  "sel.en_cola_chip": ["in the queue", "en cola"],
  "sel.en_cola_pos": ["queued · {n} ahead", "en cola · {n} antes"],
  "saved.pending": [
    "Not validated yet: {n}.",
    "{n} de éstas todavía no se validaron."],

  "pf.pick_one": ["Include {nombre} in the portfolio", "Incluir {nombre} en el portafolio"],
  "pf.building": ["Combining the curves", "Combinando las curvas"],
  "ui.go_bank": ["See what the generation found", "Ver lo que encontró la generación"],

  /* ------------------------------------------------------------- bienvenida */
  "wel.title": ["Three steps", "Tres pasos"],
  /* NO NOMBRA A METATRADER, y eso importa: se lee ANTES de elegir mundo, y
     prometer un destino que el usuario todavía no eligió deja a quien viene
     por cripto pensando que se equivocó de programa. */
  "wel.sub": [
    "Botiquant generates trading strategies on local data, the ones worth keeping are retained, and they are exported to wherever the trading happens. Everything runs on this machine.",
    "Botiquant genera estrategias sobre datos propios, se conservan las que valen la pena, y se llevan al lugar donde se opera. Todo corre en esta máquina."],
  "wel.s1": ["Generation", "Generación"],
  "wel.s1_sub": [
    "Select an instrument and the number of strategies required. The generation does not stop until it has them.",
    "Seleccionar un instrumento y la cantidad de estrategias requerida. La generación no se detiene hasta reunirlas."],
  "wel.s2": ["Validation", "Validación"],
  "wel.s2_sub": [
    "What is kept goes to Validation and is judged on data it never saw. It comes back with a verdict: robust, partially robust or overfitted.",
    "Lo que se guarda pasa a Validación y se juzga sobre datos que nunca vio. Vuelve con un veredicto: robusta, robustez parcial o sobreajustada."],
  "wel.s3": ["Trading", "Operación"],
  /* Los DOS destinos, porque este texto se lee antes de elegir. Decir sólo
     MetaTrader deja a quien viene por cripto pensando que se equivocó. */
  "wel.s3_sub": [
    "On MetaTrader 5 it exports as a robot for the terminal; on crypto a robot runs it here, on the Binance demo account. Either way, demo first.",
    "En MetaTrader 5 se exporta como robot para la terminal; en cripto un robot la ejecuta aquí, en la cuenta demo de Binance. En los dos casos, primero demo."],
  /* La bienvenida ya no es "empezar" sino ELEGIR QUE SE OPERA: son dos
     productos distintos y el que elige mal mina sobre datos que no va a poder
     operar. `wel.start` queda para no romper una traducción a medio camino. */
  "wel.elegir": ["Start here", "Empezar aquí"],
  "wel.cambiar": [
    "The choice can be changed at any time from the top left. Nothing saved is lost.",
    "Se puede cambiar en cualquier momento desde arriba a la izquierda. No se pierde nada de lo guardado."],
  "wel.start": ["Start generating", "Empezar a generar"],
  "wel.again": [
    "This screen does not appear again. Everything is in the menu on the left.",
    "Esto no vuelve a aparecer. Todo está en el menú de la izquierda."],

  "session.no_limit": ["no restriction", "sin restricción"],
  "session.exported": [
    "The exported robot carries this window. If the broker's server is not on UTC, set InpServerUTCOffset to the hours it runs ahead.",
    "El robot exportado lleva esta franja. Si el servidor del bróker no está en UTC, indicar en InpServerUTCOffset las horas que adelanta."],

  /* --------------------------------------------------- comprar y mantener */

  /* ------------------------------------------------------------ walk-forward */
  "wf.title": ["Window validation", "Validación por ventanas"],
  "wf.sub": ["Does the edge survive outside the data it was found on?",
             "¿La ventaja sobrevive fuera de los datos donde se la encontró?"],
  "wf.explain": [
    "The hardest validation there is. The history gets cut into consecutive windows; the strategy is re-tuned on each one and then judged on the window that comes next, which it has never seen. A strategy that only described the past falls apart here — and that is the point.",
    "La validación más dura que hay. El histórico se corta en ventanas consecutivas; la estrategia se reajusta en cada una y después se la juzga sobre la ventana siguiente, que nunca vio. Una estrategia que sólo describía el pasado se cae aquí — y de eso se trata."],
  "wf.run": ["Run the validation", "Ejecutar la validación"],
  "wf.running": ["Validating…", "Validando…"],
  "wf.no_se_pudo": ["Could not validate it", "No se pudo validar"],
  "wf.no_se_pudo_de": ["{nombre}: {motivo}", "{nombre}: {motivo}"],
  "wf.folds": ["Windows", "Ventanas"],
  "wf.folds_help": [
    "How many times to repeat the tune-then-validate cycle. More windows is a harder validation and takes longer.",
    "Cuántas veces repetir el ciclo de ajustar y validar. Más ventanas es una validación más dura y tarda más."],
  "wf.train": ["Share used for tuning", "Parte usada para ajustar"],
  "wf.train_help": [
    "How much of each window goes into tuning the strategy. The rest is what it gets judged on.",
    "Cuánto de cada ventana se usa para ajustar la estrategia. El resto es sobre lo que se la juzga."],
  "wf.efficiency": ["Validation efficiency", "Eficiencia de la validación"],
  "wf.efficiency_help": [
    "What fraction of the tuned performance survived on data the strategy had not seen. Above 0.5 is good; below 0.3 means the tuning was describing noise.",
    "Qué fracción del rendimiento ajustado sobrevivió sobre datos que la estrategia no había visto. Por encima de 0,5 está bien; por debajo de 0,3 el ajuste estaba describiendo ruido."],
  "wf.consistency": ["Profitable windows", "Ventanas en ganancia"],
  "wf.verdict.robust": ["Robust", "Robusta"],
  "wf.verdict.robust_sub": [
    "The edge survived on data the strategy had never seen, and it did so in most windows. This is as good as backtesting evidence gets.",
    "La ventaja sobrevivió sobre datos que la estrategia nunca vio, y lo hizo en la mayoría de las ventanas. Es lo mejor que puede dar la evidencia de un backtest."],
  "wf.verdict.acceptable": ["Partially robust", "Robustez parcial"],
  "wf.verdict.acceptable_sub": [
    "Some of the edge survived, but not in every window. Worth watching on a demo account before risking capital.",
    "Algo de la ventaja sobrevivió, pero no en todas las ventanas. Conviene observarla en una cuenta demo antes de arriesgar capital."],
  "wf.verdict.overfitted": ["Overfitted", "Sobreajustada"],
  "wf.verdict.overfitted_sub": [
    "It looked good on the data it was tuned on and fell apart on the next window. That is the signature of a strategy that memorised the past instead of finding something in it.",
    "Se veía bien sobre los datos con los que se la ajustó y se cayó en la ventana siguiente. Es la firma de una estrategia que memorizó el pasado en vez de encontrar algo en él."],
  "wf.fold": ["Window", "Ventana"],
  "wf.tuned_on": ["Tuned on", "Ajustada sobre"],
  "wf.judged_on": ["Judged on", "Juzgada sobre"],
  "wf.in_sample": ["While tuning", "Al ajustar"],
  "wf.out_sample": ["On unseen data", "Sobre datos nuevos"],
  "wf.stitched": ["Equity on unseen data only", "Capital sólo sobre datos nuevos"],
  "wf.pick": ["Which strategy to validate", "Qué estrategia validar"],
  "wf.pick_one": ["Select one strategy above to validate.",
                  "Seleccionar arriba una estrategia para validar."],
  "wf.nothing": ["Nothing to validate yet", "Todavía no hay nada que validar"],
  "wf.nothing_sub": [
    "Once a generation finishes, its strategies show up here for the hardest validation the app has.",
    "Cuando termina una generación, sus estrategias aparecen aquí para pasar por la validación más dura que tiene la aplicación."],
  "wf.by_fold": ["Window by window", "Ventana por ventana"],
  "wf.need_data": [
    "Not enough history for that many windows. Use fewer windows or a longer period.",
    "No hay suficiente histórico para tantas ventanas. Usar menos ventanas o un período más largo."],

  /* -------------------------------------------------------------- portafolio */
  "pf.title": ["Portfolio", "Portafolio"],
  "pf.sub": ["Do these work together, or are they the same bet in disguise?",
             "¿Funcionan juntas, o son la misma apuesta disfrazada?"],
  "pf.explain": [
    "Ten strategies that all make money at the same time and lose at the same time are one strategy with ten names. This puts their equity curves together and shows how much each one actually adds.",
    "Diez estrategias que ganan al mismo tiempo y pierden al mismo tiempo son una sola estrategia con diez nombres. Esto junta sus curvas de capital y muestra cuánto suma de verdad cada una."],
  "pf.build": ["Combine selected", "Combinar las seleccionadas"],
  "pf.combined": ["Combined", "Combinada"],
  "pf.correlation": ["How alike they are", "Qué tan parecidas son"],
  "pf.ventana": [
    "Measured over the days when all of them have data: {desde} → {hasta}. Each strategy on its own covers more, so its number there is not this one.",
    "Medido sobre los días en que todas tienen datos: {desde} → {hasta}. Cada estrategia por separado abarca más, así que su cifra allá no es esta."],
  "pf.correlation_help": [
    "1.0 means the two curves move together exactly — holding both adds nothing. Below 0.3 is a real diversification.",
    "1,0 significa que las dos curvas se mueven exactamente igual: tener las dos no aporta nada. Por debajo de 0,3 es una diversificación de verdad."],
  "pf.contribution": ["Share of the risk", "Parte del riesgo"],
  "pf.best_pair": ["Least alike pair", "El par menos parecido"],
  "pf.worst_pair": ["Most alike pair", "El par más parecido"],
  "pf.need_two": ["Select at least two strategies to combine.",
                  "Seleccionar al menos dos estrategias para combinar."],
  "pf.pick": ["Which strategies to combine", "Qué estrategias combinar"],
  "pf.equal_weight": ["capital split evenly", "capital repartido en partes iguales"],
  "pf.corr_high": ["These are almost the same bet", "Éstas son casi la misma apuesta"],
  "pf.corr_mid": ["Partly independent", "Parcialmente independientes"],
  "pf.corr_low": ["Genuinely different bets", "Apuestas de verdad distintas"],
  "pf.corr_unknown": ["Not enough shared history to tell",
                      "No hay suficiente historia compartida para saberlo"],
  "pf.no_overlap_cell": ["No shared movement to compare", "Sin movimiento compartido que comparar"],
  "pf.no_overlap": [
    "<b>{lista}</b> did not trade between {desde} and {hasta}, which is the only window all of these share. Its numbers are not part of the combination — combine strategies generated over similar periods, or this comparison says nothing.",
    "<b>{lista}</b> no operó entre {desde} y {hasta}, que es la única ventana que comparten todas. Sus números no entran en la combinación — conviene combinar estrategias generadas sobre períodos parecidos, o esta comparación no dice nada."],
  "pf.conviene": [
    "Worth combining: the drawdown goes from {dd}% with {nombre} alone to {ddjunto}% together, and the return goes from {parte}% to {junto}%.",
    "Conviene combinarlas: el drawdown baja de {dd}% con {nombre} sola a {ddjunto}% juntas, y el rendimiento va de {parte}% a {junto}%."],
  "pf.no_conviene": [
    "Not worth combining here: the drawdown goes from {dd}% with {nombre} alone to {ddjunto}% together, and the return goes from {parte}% to {junto}%.",
    "Aquí no conviene combinarlas: el drawdown pasa de {dd}% con {nombre} sola a {ddjunto}% juntas, y el rendimiento va de {parte}% a {junto}%."],
  "pf.vs_best": [
    "The best single one, {nombre}, returned {parte}% a year with a {dd}% drawdown. Together they return {junto}% with a {ddjunto}% drawdown — combining is worth it when the drawdown falls by more than the return does.",
    "La mejor sola, {nombre}, rindió {parte}% anual con un drawdown del {dd}%. Juntas rinden {junto}% con un drawdown del {ddjunto}% — combinar conviene cuando el drawdown baja más de lo que baja el rendimiento."],

  /* ------------------------------------------------------ comparar dos a dos */
  "cmp.title": ["Side by side", "Una al lado de la otra"],
  "cmp.sub": ["Two strategies, the same axes", "Dos estrategias, los mismos ejes"],
  "cmp.pick_two": ["Select exactly two strategies to compare.",
                   "Seleccionar exactamente dos estrategias para comparar."],
  "cmp.better": ["better", "mejor"],
  "cmp.tie": ["tied", "empate"],

  /* --------------------------------------------------- prueba en otro mercado */

  /* ------------------------------------------------------------------ notas */
  "note.title": ["Why it was kept", "Por qué se guardó"],
  "note.placeholder": [
    "In two weeks there will be twenty of these and no way to remember which one stood out.",
    "En dos semanas habrá veinte de éstas y ninguna manera de recordar cuál se destacó."],
  "note.save": ["Save note", "Guardar nota"],
  "note.saved": ["Note saved", "Nota guardada"],
  "note.empty": ["No note yet", "Sin nota todavía"],

  /* ---------------------------------------------------------------- gráficos */
  "chart.drawdown_from_peak": ["DRAWDOWN FROM PEAK", "DRAWDOWN DESDE MÁXIMO"],
  "chart.below_peak": ["{pct}% below peak", "{pct}% bajo el máximo"],
  //: doce abreviaturas separadas por coma; el orden es enero → diciembre
  "chart.months": ["Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec",
                   "Ene,Feb,Mar,Abr,May,Jun,Jul,Ago,Sep,Oct,Nov,Dic"],
  "chart.year": ["Year", "Año"],

  /* ------------------------------------------------------------- genéricos */
  "ui.cancel": ["Cancel", "Cancelar"],
  "ui.close": ["Close", "Cerrar"],
  "ui.back": ["Back", "Volver"],
  "ui.save": ["Save", "Guardar"],
  "ui.delete": ["Delete", "Borrar"],
  "ui.select_all": ["Select all", "Seleccionar todas"],
  "ui.select_one": ["Select {n}", "Seleccionar {n}"],
  "ui.clear": ["Clear selection", "Limpiar selección"],
  "ui.loading": ["Loading…", "Cargando…"],
  "ui.none": ["Nothing to show", "Nada para mostrar"],
  "ui.all": ["All", "Todos"],
  "ui.none_btn": ["None", "Ninguno"],
  "ui.retry": ["Try again", "Reintentar"],
  "ui.bars": ["bars", "velas"],
  "ui.error": ["Something went wrong", "Algo salió mal"],
  "ui.of": ["of", "de"],
  "ui.selected": ["{n} selected", "{n} seleccionadas"],
  "ui.strategy": ["strategy", "estrategia"],
  "ui.strategies": ["strategies", "estrategias"],
  "ui.recommended": ["recommended", "recomendado"],
  "ui.advanced": ["Advanced", "Avanzado"],
  "ui.and": ["and", "y"],
  "ui.saved_tag": ["saved", "guardada"],
  "ui.go_mining": ["Go to Generation", "Ir a Generación"],
};

const IDIOMAS = [
  { id: "en", nombre: "English", corto: "EN" },
  { id: "es", nombre: "Español", corto: "ES" },
];

/* Inglés por defecto. Si el navegador está en español se arranca en español:
   es el único caso en que adivinar no molesta a nadie, porque quien tiene el
   sistema en español casi seguro prefiere leer en español. */
function _inicial() {
  try {
    const guardado = localStorage.getItem("bq.lang");
    if (guardado === "en" || guardado === "es") return guardado;
    return String(navigator.language || "").toLowerCase().startsWith("es") ? "es" : "en";
  } catch (e) {
    return "en";
  }
}

let LANG = _inicial();

const idioma = () => LANG;

function setIdioma(id, redibujar) {
  if (id !== "en" && id !== "es") return;
  LANG = id;
  try { localStorage.setItem("bq.lang", id); } catch (e) { /* sin localStorage no persiste */ }
  document.documentElement.setAttribute("lang", id);
  if (redibujar) redibujar();
}

/* Una clave que falta devuelve la clave misma y lo avisa por consola, no una
   cadena vacía: un hueco silencioso en la pantalla es mucho más difícil de
   encontrar que un "wf.titulo" escrito en el medio de una tarjeta. */
function t(clave, vars) {
  const fila = STR[clave];
  let texto;
  if (!fila) {
    if (!t._avisado) t._avisado = new Set();
    if (!t._avisado.has(clave)) {
      t._avisado.add(clave);
      console.warn("[i18n] falta la clave:", clave);
    }
    texto = clave;
  } else {
    texto = (LANG === "es" ? fila[1] : fila[0]) ?? fila[0];
  }
  if (!vars) return texto;
  return texto.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

/* Locale de formateo. Va atado al idioma y no al navegador: con `undefined`
   la misma pantalla mezclaba criterios —los enteros salían "35.500" y el
   dinero "35,500"— según dónde estuviera cada usuario. */
const localeNum = () => (LANG === "es" ? "es-AR" : "en-US");
