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
  "nav.data": ["Data", "Datos"],
  "nav.mining": ["Mining", "Minado"],
  // el numero de al lado cuenta TODO el Databank, no la ultima corrida:
  // pegado a la palabra "Minado" y solo, se leia como "91 minados"
  "nav.bank_count": ["{n} strategies in the Databank",
    "{n} estrategias en el Databank"],
  "nav.bank": ["Databank", "Databank"],
  "nav.montecarlo": ["Monte Carlo", "Monte Carlo"],
  "nav.walkforward": ["Walk-forward", "Walk-forward"],
  "nav.portfolio": ["Portfolio", "Portafolio"],
  "nav.saved": ["My strategies", "Mis estrategias"],
  "nav.offline": ["offline · local", "sin conexión · local"],
  /* Corto a proposito: la barra lateral tiene 200px utiles y la frase larga
     partia en dos renglones, que en una fila de menu se lee como un error. */
  "nav.active_run": ["Active run", "Corrida activa"],
  "nav.support": ["Report a problem", "Reportar un problema"],
  "nav.theme": ["Switch theme", "Cambiar tema"],
  "nav.theme_dark": ["Switch to dark theme", "Cambiar a tema oscuro"],
  "nav.theme_light": ["Switch to light theme", "Cambiar a tema claro"],
  "nav.language": ["Language", "Idioma"],
  "nav.tagline": ["strategy miner", "buscador de estrategias"],

  /* ---------------------------------------------------------------- métricas
     Los nombres de métrica NO se traducen. Ver la nota de arriba: son
     términos del oficio, y en español se usan igual. Lo que sí se traduce es
     la explicación de cada uno. */
  "m.cagr": ["Annual return (CAGR)", "Retorno anual (CAGR)"],
  "m.net": ["Total return", "Retorno total"],
  "m.pf": ["Profit factor", "Profit factor"],
  "m.dd": ["Max drawdown", "Drawdown máximo"],
  "m.winrate": ["Win rate", "Win rate"],
  "m.sharpe": ["Sharpe", "Sharpe"],
  "m.trades": ["Trades", "Operaciones"],
  /* ───────────────────────────── las categorías de búsqueda ───────────────
     Cada tarjeta dice qué busca Y QUÉ CUESTA. Todas cuestan algo: acertar más
     seguido significa ganar menos por acierto, caer poco significa rendir
     menos. Callarlo sería vender lo que la portada dice no vender. */
  "rec.titulo": ["What are you looking for?", "¿Qué estás buscando?"],
  "rec.sub": ["each one sets the whole search, not just the filters",
              "cada una configura la búsqueda entera, no sólo los filtros"],
  "rec.puesta": ["Set up for: {nombre}. You can still change anything below.",
                 "Configurado para: {nombre}. Podés cambiar lo que quieras abajo."],

  "rec.fondeo": ["Pass a funded-account challenge", "Pasar un desafío de fondeo"],
  /* Comparativa y no absoluta, a propósito por dos razones.

     Una: medido, la primera que trae opera una vez cada 4,8 días en el S&P y
     una cada 21 en Bitcoin. Prometer un número sería inventarlo.

     Dos: la primera versión decía «cuida la caída», y eso ya lo dice «Dormir
     tranquilo». Dos categorías con la misma promesa es una de sobra. Lo que
     distingue a ésta es el ORDEN: entran las que aguantan y arriba quedan las
     que más operan, que es lo que sirve con fecha de vencimiento. */
  "rec.fondeo_que": ["The most active of the ones that hold up",
                     "La más activa de las que no se hunden"],
  "rec.fondeo_cuesta": ["Costs: it trades rarely — making money and trading often barely coexist",
                        "Cuesta: opera poco — ganar y operar seguido casi no conviven"],

  "rec.largo": ["Hold it for years", "Aguantarla años"],
  "rec.largo_que": ["Few trades, edge that keeps working",
                    "Pocas operaciones, ventaja que se sostiene"],
  "rec.largo_cuesta": ["Costs: weeks can go by without a single trade",
                       "Cuesta: pueden pasar semanas sin operar"],

  "rec.aciertos": ["Win more often than you lose", "Acertar más veces de las que fallás"],
  "rec.aciertos_que": ["Most trades close in the green",
                       "La mayoría de las operaciones cierran en verde"],
  "rec.aciertos_cuesta": ["Costs: each loss is bigger than each win",
                          "Cuesta: cada pérdida es más grande que cada ganancia"],

  "rec.tranquilo": ["Sleep at night", "Dormir tranquilo"],
  "rec.tranquilo_que": ["The worst fall stays small",
                        "La peor caída se mantiene chica"],
  "rec.tranquilo_cuesta": ["Costs: it returns less per year",
                           "Cuesta: rinde menos por año"],

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
  "m.months_positive": ["Winning months", "Meses en ganancia"],
  "m.top_trade": ["Biggest trade's share", "Peso de la mejor operación"],
  /* El desglose del score. El backend arma estos rotulos en castellano
     (metrics.py no sabe de idiomas) y la pantalla los mostraba tal cual: con la
     app en ingles el titulo decia "Score - how repeatable it looks" y las barras
     de abajo "Consistencia (Sharpe)". Ahora la clave manda sobre el rotulo. */
  "score.consistencia": ["Consistency (Sharpe)", "Consistencia (Sharpe)"],
  "score.recuperacion": ["Profit vs. drawdown", "Ganancia vs. caída"],
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
  "why.stability": ["only {pct}% of months closed in the green",
                    "sólo {pct}% de los meses cerraron en verde"],
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
  "note.typical_diff": ["You are using <b>{actual}</b>. The typical one for <b>{mercado}</b> is <b>{tipico}</b>.",
                        "Estás usando <b>{actual}</b>. El típico de <b>{mercado}</b> es <b>{tipico}</b>."],
  "note.use_typical": ["Use the typical one", "Usar el típico"],

  /* ---------------------------------------------------------------- puntaje */
  "tier.solid": ["Solid", "Sólida"],
  "tier.promising": ["Promising", "Prometedora"],
  "tier.doubtful": ["Doubtful", "Dudosa"],
  "tier.fragile": ["Fragile", "Frágil"],

  /* ------------------------------------------------------------------ errores */
  "err.page": ["This page could not load", "No se pudo cargar esta página"],
  "err.no_response": ["The server did not respond.", "El servidor no respondió."],
  "auth.expired": ["Your session ended", "Se cerró tu sesión"],
  "auth.expired_sub": ["Sign in again and we pick up where you were.",
                       "Volvé a entrar y seguimos donde estabas."],
  /* La licencia, en el escritorio.

     El texto no promete nada que no cumpla. La aplicacion funciona completa
     sin licencia y eso se dice con esas palabras: la alternativa —"activá tu
     licencia"— hace creer que algo se desbloquea y despues no pasa nada. Lo
     que se ofrece es lo que de verdad da. */
  "lic.title": ["Your licence", "Tu licencia"],
  "lic.sub": ["Checked here on your machine, without asking any server.",
              "Se comprueba acá en tu máquina, sin preguntarle a ningún servidor."],
  "lic.poner": ["Add your licence", "Poné tu licencia"],
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
    "Botiquant works in full without a licence — nothing here is locked. Bringing yours lets the app know who you are and since when, and leaves this copy recognised for the day there are paid features. You get it from your account at <b>botiquant.com</b>.",
    "Botiquant funciona completo sin licencia — acá no hay nada bloqueado. Traer la tuya hace que la aplicación sepa quién sos y desde cuándo, y deja esta copia reconocida para el día que haya funciones de pago. La sacás de tu cuenta en <b>botiquant.com</b>."],
  "lic.pegar": ["Paste your licence", "Pegá tu licencia"],
  "lic.reemplazar": ["Replace it with another one", "Reemplazarla por otra"],
  "lic.placeholder": ["Paste the whole text, in one line",
                      "Pegá el texto entero, en una sola línea"],
  "lic.guardar": ["Save licence", "Guardar licencia"],
  "lic.sacar": ["Remove it", "Sacarla"],
  "lic.vacio": ["There is nothing pasted in there yet.", "Todavía no pegaste nada ahí."],
  "lic.puesta_ok": ["Licence saved", "Licencia guardada"],
  "lic.sacada": ["Licence removed from this machine",
                 "Licencia sacada de esta máquina"],
  "lic.confirmar_sacar": [
    "Remove the licence from this machine? The app keeps working exactly the same.",
    "¿Sacar la licencia de esta máquina? La aplicación sigue funcionando exactamente igual."],
  "auth.sign_in": ["Sign in with Google", "Entrar con Google"],
  "auth.sign_out": ["Sign out", "Salir"],
  "auth.signed_out": ["Signed out", "Sesión cerrada"],
  "auth.gate_body": [
    "Sign in again to carry on. Nothing you saved is lost: the databank strategies and the instruments are still where they were.",
    "Volvé a entrar para seguir. Lo que tengas guardado no se pierde: las estrategias del databank y los instrumentos siguen donde estaban."],
  "auth.gate_fine": [
    "Google gives us your name, your email and your picture. Nothing else: we ask for no access to your mail or your files, and you will not type any password here.",
    "Google nos da tu nombre, tu correo y tu foto. Nada más: no pedimos permiso sobre tu correo ni tus archivos, y no vas a escribir ninguna contraseña acá."],

  /* --------------------------------------------------------------- pantalla DATOS */
  "data.sub": [
    "The most traded instruments, ready to search. Download with one click or import your own CSV.",
    "Los instrumentos más operados, listos para minar. Descargá con un clic o importá tu propio CSV."],
  "data.library": ["Instrument library", "Biblioteca de instrumentos"],
  "data.library_hint": ["real 1-minute data from Dukascopy, in server time (NY+7)",
                        "M1 real de Dukascopy, en hora del servidor (NY+7)"],
  "data.search_this": ["Search this one", "Minar este"],
  "data.history_since": ["1-minute history since {fecha}", "Historial M1 desde {fecha}"],
  "data.unavailable": ["Not available for this instrument", "No disponible en este instrumento"],
  "data.download": ["Download", "Descargar"],
  "data.downloading": ["Downloading…", "Descargando…"],
  "data.add": ["Add a symbol or data", "Agregar símbolo o data"],
  "data.add_sub": ["Import any CSV from MT4/MT5, TradingView, Dukascopy or Binance",
                   "Importá cualquier CSV de MT4/MT5, TradingView, Dukascopy o Binance"],
  "data.synthetic": ["synthetic", "sintético"],
  "data.shared": ["shared", "compartido"],
  "data.shared_help": ["Shared instrument: every user has it",
                       "Instrumento compartido: lo usan todos los usuarios"],
  "data.import": ["Import your own CSV", "Importar tu propio CSV"],
  "data.pick_file": ["Pick the file", "Elegí el archivo"],
  "data.pick_file_hint": ["CSV from MT4, MT5, TradingView, Dukascopy or Binance",
                          "CSV de MT4, MT5, TradingView, Dukascopy o Binance"],
  "data.name": ["Name", "Nombre"],
  "data.source": ["Source", "Fuente"],
  "data.optional": ["optional", "opcional"],
  "data.big_file": ["The file is over 100 MB", "El archivo pesa más de 100 MB"],
  "data.paste_path": ["Paste its full path", "Pegá su ruta completa"],
  "data.paste_path_hint": [
    "years of 1-minute history will not go through the browser file picker",
    "un histórico M1 de años no entra por el selector del navegador"],
  "data.import_path": ["Import by path", "Importar por ruta"],
  "data.need_path": ["Paste the path to the CSV", "Pegá la ruta del CSV"],
  "data.imported": ["Imported: {nombre} ({n} bars)", "Importado: {nombre} ({n} velas)"],
  "data.uploaded": ["Uploaded: {nombre} ({n} bars)", "Subido: {nombre} ({n} velas)"],
  "data.in_workspace": ["Datasets in the workspace", "Datasets en el workspace"],
  "data.none": ["No data yet", "Todavía no hay datos"],
  "data.none_help": ["Download an instrument from the library above, or import your own CSV.",
                     "Descargá un instrumento de la biblioteca de arriba, o importá tu propio CSV."],
  /* "¿Borrar este dataset?" no decía ni qué se pierde ni si vuelve. Los cuatro
     que trae la aplicación se pueden volver a bajar; uno propio, importado de
     un CSV, no. Son dos situaciones distintas y hay que decir cuál es. */
  "data.confirm_delete": [
    "Delete {nombre}?\n\nStrategies already found stay in place. If it is one of the four that ship with Botiquant you can download it again from Data; if you imported it yourself, you will need the original file.",
    "¿Borrar {nombre}?\n\nLas estrategias que ya encontraste no se tocan. Si es uno de los cuatro que trae Botiquant lo podés volver a bajar desde Datos; si lo importaste vos, vas a necesitar el archivo original."],
  "data.deleted": ["Dataset deleted", "Dataset borrado"],

  /* ------------------------------------------------- ayudas de configuración */
  "help.risk": [
    "Each trade puts <b>{pct}%</b> ≈ <b>${plata}</b> of your ${capital} on the line; the position size is worked out so that hitting the stop costs exactly that. <br>It multiplies the return AND the drawdown of any strategy you find in the same proportion: <b>10 losses in a row</b> take <b>{racha}%</b> of the account.",
    "Cada operación pone en juego <b>{pct}%</b> ≈ <b>${plata}</b> de tus ${capital}; el tamaño de la posición se calcula solo para que tocar el stop cueste exactamente eso. <br>Multiplica en la misma proporción la ganancia Y la caída de cualquier estrategia que encuentres: <b>10 pérdidas seguidas</b> se llevan el <b>{racha}%</b> de la cuenta."],
  "help.no_crit_title": ["No quality filter is ticked.", "No hay ningún filtro de calidad tildado."],
  "help.no_crit": [
    "With only <b>{n}+ trades</b> required, almost any candidate gets in: the databank fills up in seconds with strategies that lose money. The numbers below do not apply until you tick their box.",
    "Con sólo <b>{n}+ operaciones</b> entra casi cualquier candidata: el databank se llena en segundos con estrategias que pierden plata. Los números de abajo no se aplican hasta que tildes su casilla."],
  "help.wr_impossible_title": ["A {pct}% win rate is not enough to make money",
                               "{pct}% de aciertos no alcanza para ganar plata"],
  "help.wr_impossible": [
    "at 1:{rr}: break-even sits at <b>{be}%</b>. Below that, winning more often still loses money.",
    "con relación 1:{rr}: el punto de equilibrio está en <b>{be}%</b>. Por debajo de ahí, acertar más veces sigue dando pérdida."],
  "help.wr_ok": [
    "At 1:{rr}, break-even sits at <b>{be}%</b>, so you are asking for <b>{ventaja} points</b> of edge.",
    "Con relación 1:{rr} el equilibrio está en <b>{be}%</b>, así que pedís <b>{ventaja} puntos</b> de ventaja."],
  "help.wr_high": ["That is a very high bar: try lowering it if nothing shows up.",
                   "Es una vara muy alta: probá bajarla si no aparece nada."],
  "help.lots": [
    "Always <b>{lots}</b> lot(s), no matter what. What you risk per trade stops being fixed: it depends on the volatility of the moment, because the stop moves with the ATR. In exchange, the volume is a round number that any broker accepts without recalculating anything — which is where some CFDs get stuck.",
    "Siempre <b>{lots}</b> lote(s), pase lo que pase. Lo que arriesgás por operación deja de ser fijo: depende de la volatilidad del momento, porque el stop se mueve con el ATR. A cambio, el volumen es un número redondo que cualquier broker acepta sin recalcular nada — que es donde algunos CFDs se traban."],
  "help.rr": [
    "The target is worth <b>{rr}×</b> what you risk: you make <b>${gana}</b> when you are right and lose <b>${pierde}</b> when you are not. Being right <b>{be}%</b> of the time is enough to break even. <br>The further the target, the less often you hit it: the search has to find entries that clear that bar.",
    "El objetivo vale <b>{rr}×</b> lo que arriesgás: ganás <b>${gana}</b> cuando acertás y perdés <b>${pierde}</b> cuando no. Te alcanza con acertar <b>{be}%</b> de las veces para empatar. <br>Cuanto más lejos el objetivo, menos veces se acierta: el minero tiene que encontrar entradas que superen esa vara."],
  "note.full_history": [
    "Searching <b>the whole</b> history: {desde} → {hasta} ({anios} years) · last price <b>{precio}</b>",
    "Minando <b>todo</b> el historial: {desde} → {hasta} ({anios} años) · último precio <b>{precio}</b>"],
  "note.range": ["Searching <b>{desde} → {hasta}</b> ({anios} years out of {lo} → {hi})",
                 "Minando <b>{desde} → {hasta}</b> ({anios} años de {lo} → {hi})"],
  "note.split": [
    "Of that stretch, the search sees the first <b>{mina}%</b> and the final <b>{valida}%</b> is reserved for checking.",
    "De ese tramo, la búsqueda ve el <b>{mina}%</b> inicial y el <b>{valida}%</b> final queda reservado para validar."],
  "note.round_trip": ["Round trip: <b>{abs}</b> of price", "Ida y vuelta: <b>{abs}</b> de precio"],
  "note.match_broker": ["It must match your broker.", "Debe coincidir con tu broker."],
  "note.impossible_cost": ["Impossible cost: {pct}% per trade.", "Costo imposible: {pct}% por operación."],
  "note.impossible_cost_sub": [
    "That looks like another instrument's spread — with this, no strategy can win.",
    "Parece el spread de otro instrumento — con esto ninguna estrategia puede ganar."],
  "note.use_defaults": ["Use {mercado}'s", "Usar los de {mercado}"],
  "note.typical_ok": [
    "That is {mercado}'s typical spread: {spread}. Change it if your broker charges another.",
    "Es el spread típico de <b>{mercado}</b>: {spread}. Cambialo si tu broker te cobra otro."],
  "mine.sub_empty": ["Search for strategies over real data.", "Buscá estrategias sobre datos reales."],
  "mine.no_data": ["Nothing to search on yet", "No hay con qué minar todavía"],
  "mine.no_data_help": ["Go to <b>Data</b> and download an instrument — one click and it is ready.",
                        "Andá a <b>Datos</b> y descargá un instrumento — con un clic queda listo."],
  "mine.go_data": ["Go to Data", "Ir a Datos"],

  /* ------------------------------------------------------------ pantalla MINADO */
  "mine.sub": ["You choose how many strategies you want; the search does not stop until it has them.",
               "Elegís cuántas estrategias querés y la búsqueda no para hasta juntarlas."],
  "mine.market": ["Market", "Mercado"],
  "mine.instrument": ["Instrument", "Instrumento"],
  "mine.timeframe": ["Timeframe", "Timeframe"],
  "mine.timeframe_hint": ["1-minute bars get grouped into this", "las velas M1 se agrupan a este TF"],
  "mine.direction": ["Direction", "Dirección"],
  "dir.long": ["Long only", "Largos"],
  "dir.short": ["Short only", "Cortos"],
  "dir.both": ["Both", "Ambos"],
  "mine.period": ["Period to search", "Período a minar"],
  "mine.from": ["From", "Desde"],
  "mine.to": ["To", "Hasta"],
  "mine.window": [
    "Starts on the <b>last {n} years</b> so the first search does not take forever. This instrument has {total} years.",
    "Arranca en los <b>últimos {n} años</b> para que la primera búsqueda no tarde una eternidad. Este instrumento tiene {total} años."],
  "mine.use_all": ["Use all {total} years", "Usar los {total} años"],
  "mine.oos": ["Out-of-sample check", "Validación fuera de muestra"],
  "mine.oos_off": ["Off", "Desactivada"],
  // Vive adentro del paso de la data, pegado a las fechas: reservar un tramo
  // es partir en dos el periodo que se acaba de elegir, no un paso aparte al
  // final. Apagado de fabrica: reservar significa minar sobre
  // menos historia, y eso hace salir menos estrategias. La decision es del
  // usuario y por eso la explicacion vive adentro del paso, no en un tooltip.
  "oos.off": ["Off", "Desactivada"],
  "oos.on": ["On", "Activada"],
  "oos.sum_on": ["last {pct}% reserved", "último {pct}% reservado"],
  "oos.how_much": ["How much to set aside", "Cuánto reservar"],
  "oos.what": [
    "With this on, the last <b>{pct}%</b> of the period above is <b>set aside</b>: the search never sees it. Every strategy that passes is then re-run on that final stretch, and the results table gains a column saying whether the edge held there.",
    "Activándolo, el último <b>{pct}%</b> del período de arriba queda <b>reservado</b>: la búsqueda no lo ve nunca. Después, cada estrategia que pasa se vuelve a correr sobre ese tramo final, y la tabla de resultados suma una columna que dice si la ventaja se sostuvo ahí."],
  "oos.informa": [
    "It reports, it does not discard: nothing is thrown out for failing there. Bear in mind the search is left with less history, so fewer strategies come out.",
    "Informa, no descarta: nada se tira por fallar ahí. Tené en cuenta que la búsqueda queda con menos historia, así que salen menos estrategias."],
  "mine.oos_split": ["Search {mina}% · check {valida}%", "Minar {mina}% · validar {valida}%"],
  "mine.oos_help": [
    "Splits the period in two: the search only sees the first stretch, and every accepted strategy is re-run on the end, on data it <b>never saw</b>. The databank gains a column saying how much of the edge holds there — the best reference you have for what to expect from the strategy going forward.",
    "Parte el período en dos: la búsqueda usa sólo el tramo inicial y cada estrategia aceptada se vuelve a correr sobre el final, con datos que <b>nunca vio</b>. El databank suma una columna que dice cuánto de la ventaja se sostiene ahí — que es la mejor referencia de qué esperar de la estrategia hacia adelante."],
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
    "The stop <b>distance</b> is not something you set: it is measured in volatility (ATR) and the search finds each strategy the multiple that suits it, between 1× and 5×. That is why it works the same on any instrument.",
    "La <b>distancia</b> del stop no se configura: se mide en volatilidad (ATR) y el minero le busca a cada estrategia el múltiplo que le sirve, entre 1× y 5×. Por eso funciona igual en cualquier instrumento."],
  "mine.costs": ["Broker costs", "Costos del broker"],
  "mine.spread": ["Spread", "Spread"],
  "mine.slippage": ["Slippage", "Slippage"],
  "mine.commission": ["Commission % per side", "Comisión % lado"],
  "mine.swap": ["Overnight cost % per year", "Costo de mantener % anual"],
  "mine.swap_help": ["What your broker charges per year for holding a position open (swap or overnight financing). It is on the symbol spec sheet. Leave it at 0 if you do not know it — your results will be slightly optimistic. Perpetual futures ignore it: they use their own funding series.", "Lo que te cobra tu bróker por año por dejar una posición abierta (swap o financiación). Está en la ficha del símbolo. Dejálo en 0 si no lo sabés — los resultados van a quedar un poco optimistas. Los perpetuos lo ignoran: usan su propia serie de funding."],
  /* ---------------------------------------- el chequeo del capital inicial
     Cambiar el capital no mueve ninguna metrica: el riesgo porcentual escala
     todo por igual. Lo que si cambia es el TAMANO de la posicion, y ahi esta
     lo que importa: por debajo del minimo del broker, el minimo manda. */
  "mine.min_lot": ["Broker minimum (lots)", "Mínimo del bróker (lotes)"],
  "cap.fits": ["Position size", "Tamaño de la posición"],
  "cap.too_small": ["Position size", "Tamaño de la posición"],
  "cap.detail": [
    "You risk {plata} per trade, which on {mercado} is a position of about <b>{lotes} lots</b>.",
    "Arriesgás {plata} por operación, que en {mercado} es una posición de unos <b>{lotes} lotes</b>."],
  "cap.forced": [
    "If your broker does not go below {minimo} lots on this instrument, each trade will risk more than the {pedido}% you asked for. Worth checking before you run it.",
    "Si tu bróker no baja de {minimo} lotes en este instrumento, cada operación va a arriesgar más del {pedido}% que pediste. Conviene comprobarlo antes de ponerla a operar."],
  "cap.check_broker": [
    "The minimum and the contract size are references: check them against your own broker.",
    "El mínimo y el tamaño de contrato son referencias: comprobalos contra tu propio bróker."],

  "mine.capital": ["Capital", "Capital"],
  "mine.accept": ["Acceptance filters", "Filtros de aceptación"],
  "mine.accept_help": [
    "A strategy enters the databank if it meets EVERY box you tick. Turn on only what matters to you: each extra filter makes the search slower.",
    "Una estrategia entra al databank si cumple TODO lo que esté tildado. Activá sólo lo que te importe: cada filtro extra hace la búsqueda más lenta."],
  "mine.method": ["Search method", "Método de búsqueda"],
  "mine.method_random": ["Random (explores widely)", "Aleatorio (explora amplio)"],
  "mine.method_evolution": ["Evolutionary (improves over generations)",
                            "Evolutivo (mejora por generaciones)"],
  "mine.sort_by": ["Sort the databank by", "Ordenar el databank por"],
  "mine.sort_score": ["Score (robustness)", "Score (robustez)"],
  "mine.cap": ["Safety cap", "Tope de seguridad"],
  "mine.cap_hint": ["most candidates before giving up", "candidatas máximas antes de rendirse"],
  "mine.want": ["I want to find", "Quiero encontrar"],
  "mine.want_sub": ["strategies that meet<br>the filters", "estrategias que<br>cumplan los filtros"],
  "mine.start": ["Start mining", "Iniciar minado"],
  "mine.pause": ["Pause", "Pausar"],
  "mine.resume": ["Resume", "Seguir"],
  "mine.stop": ["Stop", "Detener"],

  /* -------------------------------------------- corrida en curso y resultado */
  "run.in_bank": ["in the databank", "en el databank"],
  "run.tested": ["Tested", "Probadas"],
  "run.done": ["Search finished", "Búsqueda terminada"],
  "run.searching": ["Searching for strategies", "Buscando estrategias"],
  "run.trying": ["trying candidate #{n}", "probando candidata #{n}"],
  "run.preparing": ["preparing indicators…", "preparando indicadores…"],
  "run.until": ["It will not stop until it has <b>{goal}</b> that clear the bar — <b>{faltan}</b> to go.",
                "No se detiene hasta juntar <b>{goal}</b> que cumplan la vara — faltan <b>{faltan}</b>."],
  "run.until_cap": ["Testing candidates up to <b>{n}</b>.", "Probando candidatas hasta llegar a <b>{n}</b>."],
  "run.seed": ["seed <b>{seed}</b> reproduces this run", "semilla <b>{seed}</b> para reproducir esta corrida"],
  "run.profitable": ["Profitable", "Con ganancia"],
  "run.hit_rate": ["Hit rate", "Tasa de éxito"],
  "run.duration": ["Duration", "Duración"],
  "run.elapsed": ["Elapsed", "Transcurrido"],
  "run.eta": ["Approx. left", "Falta aprox."],
  "run.rate": ["Pace", "Ritmo"],
  "run.per_sec": ["accepted/s", "acept./s"],
  "run.best": ["Best score", "Mejor score"],
  "run.best_so_far": ["Best so far", "Mejor hasta ahora"],
  "run.open_full": ["Open the full analysis", "Ver análisis completo"],
  "run.history": ["How the best score improved", "Evolución del mejor score"],
  "run.history_hint": ["how the search got better over time", "cómo fue mejorando la búsqueda"],
  "run.bank_hint": [
    "{n} strategies ranked by score (robustness, not profit) · click any of them for the full analysis",
    "{n} estrategias ordenadas por score (robustez, no rentabilidad) · clic en cualquiera para analizarla a fondo"],
  "run.stopped": [
    "<b>You stopped the search.</b> The {n} strategies already in the databank are below, ready to inspect or export.",
    "<b>Búsqueda detenida por vos.</b> Las {n} estrategias que ya habían entrado al databank siguen acá abajo, listas para inspeccionar o exportar."],
  "run.exhausted": [
    "<b>The possible combinations ran out</b> with the blocks you ticked. Tick more blocks in section 2 or raise the rule complexity to widen the space.",
    "<b>Se agotaron las combinaciones posibles</b> con los bloques que marcaste. Marcá más bloques en la sección 2 o subí la complejidad para ampliar el espacio."],
  "run.hit_cap": [
    "<b>The {tope}-candidate safety cap was reached</b> with {n} of {goal} strategies. Your filters are very demanding for this market: untick one in section 5, change the exits in section 3, or raise the cap under Advanced to keep searching longer.",
    "<b>Se llegó al tope de seguridad de {tope} candidatas</b> con {n} de {goal} estrategias. Tus filtros son muy exigentes para este mercado: destildá alguno en la sección 5, cambiá las salidas en la 3, o subí el tope en Avanzado si querés que siga buscando más tiempo."],
  "run.reached": [
    "<b>Goal reached.</b> {goal} strategies that clear every filter, found by testing {probadas} candidates in {tiempo}.",
    "<b>Objetivo cumplido.</b> {goal} estrategias que cumplen todos los filtros, encontradas probando {probadas} candidatas en {tiempo}."],
  "run.split_note": [
    "<b>Checked out of sample.</b> The search used {desde} → {hasta} ({velas} bars) and every strategy was re-run on {odesde} → {ohasta} ({ovelas} bars) that it never saw. The <b>{columna}</b> column is the one that says whether the edge was real.",
    "<b>Validado fuera de muestra.</b> La búsqueda usó {desde} → {hasta} ({velas} velas) y cada estrategia se volvió a correr sobre {odesde} → {ohasta} ({ovelas} velas) que nunca vio. La columna <b>{columna}</b> es la que dice si la ventaja era real."],

  "run.paused_toast": ["Paused — where it was is kept, nothing is lost",
                       "En pausa — se guarda dónde iba, no se pierde nada"],
  "run.resumed_toast": ["The search continues", "Sigue la búsqueda"],
  "run.few_passed": ["{n} were tested and only {kept} cleared the filters",
                     "Se probaron {n} y sólo {kept} pasaron los filtros"],
  "mine.need_trigger": ["Tick at least one entry trigger", "Elegí al menos un disparador de entrada"],
  "err.dataset_gone": ["The instrument it was found on is no longer in the workspace",
                       "El instrumento con el que se minó ya no está en el workspace"],
  "err.no_backend": ["Could not reach the backend", "No se pudo conectar con el backend"],
  "export.installed": ["Robot installed in {terminal} — open it and compile with F7",
                       "Robot instalado en {terminal} — abrilo y compilá con F7"],
  "export.bot_saved": ["Bot file saved", "Archivo del bot guardado"],
  "insp.bingx_btn": ["Connect it to an exchange", "Conectarla a un exchange"],
  "bx.title": ["Run this strategy automatically", "Operar esta estrategia sola"],
  "bx.intro": ["TradingView evaluates the rules on its own servers and notifies the exchange when they trigger. Your computer does not need to stay on, and Botiquant never handles your exchange keys.", "TradingView evalúa las reglas en sus propios servidores y le avisa al exchange cuando se cumplen. Tu computadora no tiene que quedar prendida, y Botiquant no toca nunca las claves de tu exchange."],
  "bx.p1_t": ["Get a TradingView plan with alerts", "Conseguir un plan de TradingView con alertas"],
  "bx.p1_d": ["Webhooks are not in the free plan: you need Essential or higher. This is the only cost of the whole setup, and it is worth knowing before you start.", "Los webhooks no están en el plan gratis: hace falta Essential o superior. Es el único costo de todo esto, y conviene saberlo antes de empezar."],
  "bx.p2_t": ["Paste the strategy into the Pine Editor", "Pegar la estrategia en el Pine Editor"],
  "bx.p2_d": ["Open the chart for your symbol, paste the script you just exported and add it to the chart. Check the Strategy Tester against the numbers Botiquant measured before going any further.", "Abrí el gráfico de tu símbolo, pegá el script que acabás de exportar y agregalo al gráfico. Compará el Strategy Tester contra los números que midió Botiquant antes de seguir."],
  "bx.p3_t": ["Copy the webhook URL and message from your exchange", "Copiar la URL y el mensaje de tu exchange"],
  "bx.p3_d": ["On BingX: open the USD-M perpetual chart and click the signal trading icon. It gives you a URL and a message that are yours alone. Bybit has the same thing under Webhook Signal Trading. Never share that URL.", "En BingX: abrí el gráfico de perpetuos USD-M y tocá el ícono de trading de señales. Te da una URL y un mensaje que son sólo tuyos. Bybit tiene lo mismo en Webhook Signal Trading. Esa URL no se comparte con nadie."],
  "bx.p4_t": ["Paste the exchange's messages into the strategy settings", "Pegar los mensajes del exchange en la estrategia"],
  "bx.p4_d": ["The script has three boxes: open long, open short and close. Paste the exchange's message in each. Botiquant does not invent that format on purpose: a made-up message produces orders the exchange discards silently.", "El script tiene tres casillas: abrir largo, abrir corto y cerrar. Pegá en cada una el mensaje del exchange. Botiquant no inventa ese formato a propósito: un mensaje inventado produce órdenes que el exchange descarta en silencio."],
  "bx.p5_t": ["Create the alert with the webhook", "Crear la alerta con el webhook"],
  "bx.p5_d": ["New alert on the strategy, condition \"Order fills only\", message {{strategy.order.alert_message}}, and paste the URL under Notifications. From then on it trades on its own.", "Alerta nueva sobre la estrategia, condición \"Order fills only\", mensaje {{strategy.order.alert_message}}, y pegá la URL en Notificaciones. Desde ahí opera sola."],
  "bx.demo_t": ["Start on a demo account", "Empezá en una cuenta de práctica"],
  "bx.demo_d": ["BingX has a demo environment and so do most exchanges. Run it there for a few weeks first: that is what tells you whether it does live what it did in the backtest, and it costs nothing to find out.", "BingX tiene entorno de práctica, y la mayoría de los exchanges también. Corrila ahí unas semanas primero: eso es lo que te dice si hace en vivo lo mismo que hizo en el backtest, y averiguarlo no cuesta nada."],
  "bx.compara": ["One warning worth repeating: the Pine script is a translation of the strategy into another language. Compare TradingView's Strategy Tester against Botiquant's numbers over the same dates. If they differ a lot, do not turn it on.", "Un aviso que vale repetir: el script de Pine es una traducción de la estrategia a otro lenguaje. Compará el Strategy Tester de TradingView contra los números de Botiquant sobre las mismas fechas. Si difieren mucho, no la enciendas."],
  "insp.bingx_hint": ["Save the link file for the BingX runner", "Guarda el archivo de enlace para el runner de BingX"],
  "insp.bingx_solo_cripto": ["Only for perpetual futures: a crypto exchange does not trade indices or metals", "Sólo para perpetuos: un exchange de cripto no opera índices ni metales"],
  "export.mq5_saved": ["Expert Advisor saved — copy it to MQL5/Experts and compile",
                       "Expert Advisor guardado — copialo a MQL5/Experts y compilá"],
  "export.pine_saved": ["Pine saved — or use Copy and paste it into TradingView",
                        "Pine guardado — o usá Copiar y pegalo en TradingView"],
  "export.pick_terminal": ["You have {n} MetaTraders installed. Send it to:",
                           "Tenés {n} MetaTrader instalados. Mandarlo a:"],
  "export.copy_failed": ["The system would not let me copy, so I saved it as a file",
                         "El sistema no dejó copiar, así que lo guardé como archivo"],
  "insp.no_range": [
    "<b>This strategy was saved without recording its period.</b> What you see here was calculated over the <b>whole history</b> of the instrument, so it may not match the metrics in the list, which came from the stretch you searched. Search for it again and save it anew so the two are tied together.",
    "<b>Esta estrategia se guardó sin registrar el período.</b> Lo que ves acá se calculó sobre <b>toda la historia</b> del instrumento, así que puede no coincidir con las métricas de la lista, que salieron del tramo que minaste. Volvé a minarla y guardala de nuevo para que queden atadas."],

  "run.locked": [
    "Settings are frozen while it searches. Changing the criteria while looking at the results would be choosing them to fit this particular history. <b>Stop</b> to adjust and search again.",
    "Configuración congelada mientras busca. Cambiar los criterios viendo los resultados sería elegirlos a medida del histórico. <b>Detené</b> para ajustar y volver a minar."],
  /* Cuando el histórico no tiene funding. Se dice el número y no los nombres:
     lo que importa es que la corrida usó menos bloques de los pedidos. */
  "vara.sin_funding": [
    "{n} funding block(s) were left out: this instrument has no funding — perpetuals charge it, a CFD does not.",
    "Quedaron afuera {n} bloque(s) de funding: este instrumento no lo tiene — lo cobran los perpetuos, un CFD no."],
  "vara.required": ["Required", "Se exigió"],
  "vara.min_trades": ["at least <b>{n}</b> trades", "mínimo <b>{n}</b> operaciones"],
  "vara.none": [
    "<b>No quality filters.</b> The only requirement was {unico}, so almost any candidate gets in — including the ones that lose money. Tick what matters to you under <b>Acceptance filters</b> and search again.",
    "<b>Sin filtros de calidad.</b> Lo único que se exigió fue {unico}, así que entra casi cualquier candidata — incluidas las que pierden plata. Tildá lo que te importe en <b>Filtros de aceptación</b> y volvé a minar."],
  "busca.tested": ["candidates tested", "candidatas probadas"],
  "busca.accepted": ["accepted", "aceptadas"],
  "busca.why": ["Why they get rejected", "Por qué se caen"],
  "busca.too_few_trades": ["too few trades", "pocas operaciones"],
  "busca.foot": [
    "The ones that clear the bar show up here. You can leave it running and come back.",
    "Las que pasen la vara van apareciendo acá. Podés dejarlo corriendo y volver."],

  /* ------------------------------------------------------------- Monte Carlo */
  "mc.sub": ["How much of what you see was the strategy, and how much was the order the trades came in.",
             "Cuánto de lo que ves fue la estrategia, y cuánto fue el orden en que salieron las operaciones."],
  "mc.head": [
    "A strategy that won may have won because of the order its trades came in. Here they get reshuffled a thousand times to see which one really holds up.",
    "Una estrategia que ganó pudo ganar por el orden en que le salieron las operaciones. Acá se rebarajan mil veces para ver cuál aguanta de verdad."],
  "mc.empty": ["Nothing to simulate yet", "Todavía no hay nada que simular"],
  "mc.empty_help": [
    "When a search finishes, its strategies show up here so you can put them under pressure and see which one takes a bad run best.",
    "Cuando termines una búsqueda, sus estrategias aparecen acá para ponerlas a prueba y ver cuál aguanta mejor una racha en contra."],
  "mc.pick": ["Which strategies to compare", "Qué estrategias comparar"],
  "mc.pick_hint": [
    "{n} available · from your saved ones and the databank · pick several to see which holds up best",
    "{n} disponibles · de tus guardadas y del databank · elegí varias para ver cuál aguanta mejor"],
  "mc.title": ["How steady is this result?", "¿Qué tan parejo es este resultado?"],
  "mc.title_hint": ["the same trades, in a different order, a thousand times each",
                    "las mismas operaciones, en otro orden, mil veces cada una"],
  "mc.what": [
    "<b>What this is.</b> The <i>order</i> the trades arrive in changes the ride: three losses in a row at the start leave the account somewhere very different than the same three at the end. This takes the strategy's real trades and deals them out again a thousand times, to show the range of outcomes it lands in and how deep the dip can get along the way.",
    "<b>Qué es esto.</b> El <i>orden</i> en que llegan las operaciones cambia el recorrido: tres pérdidas seguidas al principio dejan la cuenta en un lugar muy distinto que las mismas tres al final. Esto agarra las operaciones reales de la estrategia y las vuelve a repartir mil veces, para mostrar en qué rango de resultados cae y qué tan hondo puede ser el pozo en el camino."],
  "mc.what_not": [
    "<b>What this does NOT answer.</b> The trades get reshuffled over the same period the strategy was found on, so this measures how much depends on the order — not whether the edge will exist next year. That is what the out-of-sample check is for, under Advanced in the search: it reserves a final stretch and never lets the search look at it.",
    "<b>Qué NO contesta esto.</b> Las operaciones se rebarajan sobre el mismo período donde se encontró la estrategia, así que esto mide cuánto depende del orden — no si la ventaja va a existir el año que viene. Para eso está la validación fuera de muestra, en la sección Avanzado del minado: reserva un tramo final y no lo deja mirar durante la búsqueda."],
  "mc.start_above": [
    "<b>Start at the top:</b> tick the strategies you want to compare. You can pick several and it simulates them all.",
    "<b>Empezá por arriba:</b> tildá las estrategias que quieras comparar. Podés elegir varias y las simula a todas."],
  "mc.simulate": ["Simulate {n} strategies", "Simular {n} estrategias"],
  "mc.simulating": ["Simulating…", "Simulando…"],
  "mc.champion": ["The one that holds up best", "La que mejor aguanta"],
  "mc.wins_in": [
    "It wins in <b>{n} out of every 100</b> ways its trades could have come out.",
    "Gana en <b>{n} de cada 100</b> formas en que le podrían haber salido las operaciones."],
  "mc.cost": [
    "And what you have to be willing to sit through to get it: a fall of up to <b>{dd}%</b>, and some stretch where the account is at {peor} having started with {inicial}. That is not what will happen — it is the lower edge of normal.",
    "Y lo que hay que estar dispuesto a aguantar para conseguirlo: una caída de hasta <b>{dd}%</b>, y algún tramo en que la cuenta quede en {peor} habiendo empezado con {inicial}. No es lo que va a pasar — es el borde de abajo de lo normal."],
  "mc.see_full": ["See the full simulation", "Ver la simulación completa"],
  "mc.side_by_side": ["All of them, side by side", "Todas, una al lado de la otra"],
  "mc.side_hint": ["{n} simulations of each · click any of them for its full simulation",
                   "{n} simulaciones de cada una · clic en cualquiera para ver su simulación completa"],
  "mc.c_wins": ["Wins in", "Gana en"],
  "mc.c_wins_help": [
    "In how many of the thousand possible deals it ended up making money. It is the criterion they are sorted by.",
    "En cuántos de los mil repartos posibles terminó ganando plata. Es el criterio por el que están ordenadas."],
  "mc.c_typical": ["Typical equity", "Capital típico"],
  "mc.c_endure": ["You have to sit through", "Hay que aguantar"],
  "mc.c_endure_help": [
    "The fall in the worst 5% of simulations. It is not what will happen: it is what you have to be willing to take.",
    "La caída del 5% de simulaciones peores. No es lo que va a pasar: es lo que hay que estar dispuesto a bancar."],
  "mc.c_bad": ["Bad case", "Mal escenario"],
  "mc.c_bad_help": [
    "In the bad case, what you are left with. It is the lower edge of normal, not an expected loss.",
    "En el mal escenario, con cuánto quedás. Es el borde de abajo de lo normal, no una pérdida esperada."],
  "mc.c_ruin": ["Risk of ruin", "Riesgo de ruina"],
  "mc.c_ruin_help": [
    "Chance of losing 30% of the capital at some point. This one is a genuine warning.",
    "Probabilidad de llegar a perder el 30% del capital en algún momento. Esto sí es una alerta."],
  "mc.v_risky": ["Risky", "Riesgosa"],
  "mc.v_risky_sub": [
    "It holds up well in general, but in {pct}% of scenarios it ends up losing a lot. That is what to look at before anything else.",
    "Aguanta bien en general, pero en {pct}% de los escenarios llega a perder mucho. Eso es lo que hay que mirar antes que nada."],
  "mc.v_solid": ["Solid", "Sólida"],
  "mc.v_solid_sub": [
    "It wins in the vast majority of possible deals: the result holds up whatever order the trades arrive in.",
    "Gana en la enorme mayoría de los repartos posibles: el resultado se sostiene venga en el orden que venga."],
  "mc.v_holds": ["Holds up", "Aguanta"],
  "mc.v_holds_sub": [
    "It wins in most deals. It depends somewhat on the order the trades come in, but it stands.",
    "Gana en la mayoría de los repartos. Depende algo del orden en que salgan las operaciones, pero se sostiene."],
  "mc.v_edge": ["On the edge", "Al filo"],
  "mc.v_edge_sub": [
    "It wins about as often as it loses: with this one the order the trades arrive in weighs heavily on the outcome.",
    "Gana casi tantas veces como pierde: con ésta el orden en que lleguen las operaciones pesa mucho en el resultado."],
  "mc.v_fragile": ["Fragile", "Frágil"],
  "mc.v_fragile_sub": [
    "It loses in more than half of the possible deals: the backtest landed on one of its better orders.",
    "Pierde en más de la mitad de los repartos posibles: el backtest cayó en uno de sus órdenes más favorables."],
  "mc.simulation": ["Simulation", "Simulación"],
  "mc.sims_of": ["{sims} simulations of {ops} trades", "{sims} simulaciones de {ops} operaciones"],
  "mc.ci90": [
    "Out of every 100 times you ran this system, in 90 the final equity would land between <b>{bajo}</b> and <b>{alto}</b>. That range is the honest answer to “how much can it make”: the single number in the backtest was just one of the ones inside it.",
    "De cada 100 veces que corriera este sistema, en 90 el capital final caería entre <b>{bajo}</b> y <b>{alto}</b>. Ese rango es la respuesta honesta a “cuánto puede rendir”: el número único del backtest era sólo uno de los que había adentro."],
  "mc.band": [
    "The band shows where the equity lands in 90% of the simulations. The middle line is the typical path.",
    "La banda muestra dónde cae el capital en el 90% de las simulaciones. La línea del medio es el recorrido típico."],
  "mc.finals": ["How the final outcomes spread", "Cómo se reparten los finales"],
  "mc.drawdowns": ["And the biggest falls", "Y las caídas máximas"],

  /* ---------------------------------------------------------------- databank */
  "bank.sub": ["Everything you find, run by run.", "Todo lo que encontrás, corrida por corrida."],
  "bank.empty": ["The databank is empty", "El banco está vacío"],
  "bank.empty_help": [
    "Every search that finishes leaves its strategies here with the instrument, the timeframe and the filters they were found under. They accumulate: searching again no longer wipes what came before.",
    "Cada búsqueda que termina deja acá sus estrategias con el instrumento, la temporalidad y los filtros con los que se encontraron. Se acumulan: minar de nuevo ya no borra lo anterior."],
  "bank.count": ["{n} strategies from {corridas} runs.", "{n} estrategias de {corridas} corridas."],
  "bank.count_run": ["{n} strategies in this run · {total} in the whole Databank.",
    "{n} estrategias en esta corrida · {total} en todo el Databank."],
  "bank.almost_full": ["almost full", "casi lleno"],
  "bank.capacity": ["capacity", "capacidad"],
  "bank.runs": ["Runs", "Corridas"],
  "bank.runs_hint": [
    "each search kept the settings that produced it · click to see only its own",
    "cada búsqueda quedó con la configuración que la produjo · clic para ver sólo la suya"],
  "bank.all": ["All", "Todas"],
  "bank.all_strategies": ["Every strategy", "Todas las estrategias"],
  "bank.in_view": ["{n} in view · click a row to analyse it", "{n} a la vista · clic en una fila para analizarla"],
  "bank.in_view_of": ["{n} of {hay} in view · click a row to analyse it",
    "{n} de {hay} a la vista · clic en una fila para analizarla"],
  "bank.load_more": ["Show more", "Ver más"],
  /* Las busquedas que no encontraron nada se conservan como registro —dicen que
     con esa vara ese mercado no da— pero agrupadas: con quince, la pantalla se
     llenaba de burbujas iguales y parecia que algo estaba roto. */
  "bank.vacias": ["{n} searches that found nothing",
                  "{n} b\u00fasquedas que no encontraron nada"],
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
  "bank.searched": ["Tested", "Buscó"],
  "bank.found": ["Found", "Encontró"],
  "bank.remaining": ["{n} left", "quedan {n}"],
  "bank.took": ["Took", "Tardó"],
  "bank.ended": ["Ended", "Terminó"],
  "bank.seed": ["Seed", "Semilla"],
  "bank.bar": ["Bar", "Vara"],
  "bank.run": ["Run", "Corrida"],
  "bank.rank_help": ["The rank the search gave it, by score",
                     "El orden que le dio el minero, por score"],
  "ended.completa": ["complete", "completa"],
  "ended.detenida": ["stopped", "detenida"],
  "ended.sin llegar": ["fell short", "sin llegar"],
  "bank.repeat": ["Repeat these settings", "Repetir esta configuración"],
  "bank.delete_run": ["Delete the whole run", "Borrar la corrida entera"],
  "bank.repeat_note": [
    "Repeating does not give the same strategies: the seed is random and each search explores different combinations. Two identical runs that perform differently are search variance, not one configuration being better than the other.",
    "Repetir no da las mismas estrategias: la semilla es aleatoria y cada búsqueda explora otras combinaciones. Dos corridas iguales que rinden distinto son varianza de la búsqueda, no una configuración mejor que la otra."],
  "bank.confirm_delete_run": [
    "Delete the run {nombre} and its {n} strategies?\n\nThe ones you already copied to My strategies are untouched.",
    "¿Borrar la corrida {nombre} y sus {n} estrategias?\n\nLas que ya copiaste a Mis estrategias no se tocan."],
  "bank.run_deleted": ["Run deleted", "Corrida borrada"],
  "bank.confirm_remove": ["Remove {n} strategies from the databank?",
                          "¿Quitar {n} estrategias del banco?"],
  "bank.copied": ["{n} strategies in My strategies — they also stay in the databank",
                  "{n} estrategias en Mis estrategias — siguen también en el banco"],
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
  "idle.last_run": ["Your last search", "Tu última búsqueda"],
  "idle.see_last": ["See what it found", "Ver lo que encontró"],
  "insp.no_trades": ["No trades in this period.", "Ninguna operación en este tramo."],
  "ms.midiendo": ["measuring the three periods…", "midiendo los tres tramos…"],
  /* El pie ya no repite las métricas: están en la tabla, al lado de las otras
     dos. Sólo queda de qué fechas a qué fechas es la curva que se está viendo. */
  "ms.periodo": ["Curve from {desde} to {hasta}.", "Curva de {desde} a {hasta}."],
  "state.built": ["built and tested", "construidas y probadas"],
  "state.discarded": ["discarded", "descartadas"],
  "state.kept": ["in the Databank", "en el Databank"],
  "state.saved": ["saved", "guardadas"],
  "state.removed": ["{n} you removed", "{n} que borraste"],
  "state.rate": ["{n} of {total} cleared the bar — {tasa}%",
                 "{n} de {total} pasaron la vara — {tasa}%"],

  "bank.sel_hint": ["Tick rows to save or export several at once",
                    "Tildá filas para guardar o exportar varias de una vez"],
  "bank.removed": ["{n} out of the databank", "{n} fuera del banco"],
  /* De que corrida salio la fila que se esta mirando. Dice "del banco" y no
     "guardada" a proposito: todavia no lo esta, y confundirlas hace creer que
     ya se rescato algo que no. */
  "bank.from_bank": ["from the databank · {corrida} · risk {riesgo}",
                     "del banco · {corrida} · riesgo {riesgo}"],

  "run.stopped_kept": ["Stopped — {n} strategies, kept in the Databank",
                       "Detenido — {n} estrategias, guardadas en el Databank"],
  "run.kept": ["{n} strategies in {tiempo} — they went to the Databank",
               "{n} estrategias en {tiempo} — quedaron en el Databank"],

  "data.costs_fixed": [
    "Costs and exits adjusted to {mercado}: the previous spread was {pct}% of the price",
    "Costos y salidas ajustados a {mercado}: el spread anterior era {pct}% del precio"],
  "data.exits_fixed": ["Exits adjusted to the scale of {mercado}",
                       "Salidas ajustadas a la escala de {mercado}"],

  "saved.added": ["{nombre} saved to My strategies",
                  "{nombre} guardada en Mis estrategias"],

  "bank.pruned": ["The databank was full: the {n} oldest runs were dropped",
                  "El banco estaba lleno: se soltaron las {n} corridas más viejas"],
  "bank.cfg_loaded": ["Settings loaded — press Start", "Configuración cargada — dale a Iniciar"],
  "bank.cfg_loaded_missing": [
    "Settings loaded, but {mercado} is no longer in the workspace",
    "Configuración cargada, pero {mercado} ya no está en el workspace"],
  "bank.remove": ["Remove from databank", "Quitar del banco"],
  "bank.mixed_risk": [
    "<b>You are looking at runs with different risk settings.</b> <b>{anual}</b> and <b>{dd}</b> scale with the risk per trade, so across runs they sort by that dial and not by the strategy. <b>PF</b>, <b>{score}</b> and <b>{meses}</b> are ratios: those do compare.",
    "<b>Estás viendo corridas con riesgos distintos.</b> <b>{anual}</b> y <b>{dd}</b> escalan con el riesgo por operación, así que entre corridas ordenan por esa perilla y no por la estrategia. <b>PF</b>, <b>{score}</b> y <b>{meses}</b> son proporciones: ésas sí comparan."],
  "bank.nothing_left": ["Nothing left in the databank.", "No queda nada en el banco."],
  "bank.saved_untouched": ["Whatever you saved is still in My strategies.",
                           "Las que hayas guardado siguen en Mis estrategias."],
  "bank.run_found_none": ["This search found none.", "Esta búsqueda no encontró ninguna."],
  "bank.run_found_none_help": [
    "It tested {n} candidates on {mercado} and none cleared the bar: <b>{vara}</b>.",
    "Probó {n} candidatas sobre {mercado} y ninguna pasó la vara: <b>{vara}</b>."],
  "bank.run_found_none_note": [
    "It stays on record anyway — this is the experiment worth not repeating by accident. Repeat the settings and loosen the filter that rejects the most.",
    "Queda anotada igual — es el experimento que conviene no repetir por olvido. Repetí la configuración y aflojá el filtro que más descarta."],
  "bank.you_removed": ["You removed the {n} it had found.", "Le sacaste las {n} que había encontrado."],
  "bank.cagr_help": [
    "Annualised return. It scales with the risk per trade: it does not compare across runs with different risk.",
    "Rendimiento anualizado. Escala con el riesgo por operación: no se compara entre corridas de distinto riesgo."],
  "bank.pf_help": [
    "Profit factor: dollars made per dollar lost. It does not depend on position size, so it compares well across runs.",
    "Profit factor: cuántos dólares ganó por cada dólar que perdió. No depende del tamaño de posición, así que compara bien entre corridas."],
  /* El color de esta columna es información, así que la ayuda dice cuándo
     cambia. Un umbral que nadie puede leer es lo mismo que un umbral inventado. */
  "bank.dd_help": [
    "Largest fall from a peak. It scales with the risk per trade, same as the return — "
    + "so the colour is read against that risk: amber past 15% at 1% per trade, red past 25%.",
    "Máxima caída desde un pico. Escala con el riesgo por operación igual que el rendimiento — "
    + "por eso el color se lee contra ese riesgo: ámbar pasando 15% al 1% por operación, rojo pasando 25%."],

  /* ------------------------------------------------------- mis estrategias */
  "saved.sub": ["{n} saved. They survive any new search.",
                "{n} guardadas. Sobreviven a cualquier corrida nueva."],
  /* La única pista de que el portafolio existe. Aparece recién con dos
     guardadas: con una sería vender algo que todavía no se puede hacer. */
  "saved.combinar": [
    "Tick two or more to see how they behave together: whether they add up or they are the same bet twice.",
    "Tildá dos o más para ver cómo se comportan juntas: si se suman o son la misma apuesta repetida."],
  "saved.title": ["Saved", "Guardadas"],
  "saved.hint": ["click a row to analyse it again", "clic en una fila para volver a analizarla"],
  "saved.when": ["Saved", "Guardada"],
  "saved.confirm_delete": ['Delete "{nombre}"? This cannot be undone.',
                           '¿Borrar "{nombre}"? No se puede deshacer.'],
  "saved.deleted": ["Strategy deleted", "Estrategia borrada"],
  "saved.none": ["You have not saved any yet", "Todavía no guardaste ninguna"],
  "saved.empty_sub": [
    "Strategies you save stay here, even if you search again with different filters.",
    "Las estrategias que guardes quedan acá, aunque vuelvas a minar con otros filtros."],
  "saved.none_help": [
    "When the search finds one you like, open it and press <b>Save to My strategies</b>. It gets saved with its instrument, its timeframe and its costs, so you can export it again months later without searching all over.",
    "Cuando el minado encuentre una que te sirva, abrila y tocá <b>Guardar en Mis estrategias</b>. Se guarda con su instrumento, su timeframe y sus costos, así la podés volver a exportar meses después sin tener que minar de nuevo."],

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
  "ms.is_help": ["The stretch the search looked at",
                 "El tramo que miró la búsqueda"],
  "ms.oos_help": ["Reserved on purpose: the search never saw it",
                  "Reservado a propósito: la búsqueda nunca lo vio"],
  "ms.todo_help": ["Both stretches, end to end",
                   "Los dos tramos, de punta a punta"],
  "ms.marca": ["from here on, never seen", "de acá en adelante, nunca visto"],
  "ms.muy_corto": [
    "The reserved stretch is too short to re-run on its own — the indicators need more history than it has. Use 'Both together', or reserve a larger share next time.",
    "El tramo reservado es muy corto para correrlo solo: los indicadores necesitan más historia de la que tiene. Mirá 'Las dos juntas', o reservá una porción más grande la próxima vez."],
  "ms.sin_curva": ["No curve for this stretch", "Sin curva para este tramo"],
  "ms.resumen": [
    "{desde} → {hasta} · {cagr} a year · {dd}% drawdown · PF {pf} · {n} trades",
    "{desde} → {hasta} · {cagr} anual · {dd}% de caída · PF {pf} · {n} operaciones"],
  "ms.corte": [
    "The dashed line is where the search stopped looking.",
    "La línea punteada es donde la búsqueda dejó de mirar."],

  /* --------------------------------------------- las salidas, en palabras
     La cabecera mostraba "SL=3x ATR - trail=1.5x ATR - max 12 velas", que es
     la notacion interna del minero. Los valores crudos siguen enteros en
     "Reglas de la estrategia". */
  "sal.stop": ["Stop at {n} ATR", "Stop a {n} ATR"],
  "sal.rr": ["Target {n}:1", "Objetivo {n}:1"],
  "sal.trail": ["Trailing at {n} ATR", "Trailing a {n} ATR"],
  "sal.max_bars": ["Closes after {n} bars", "Cierra a las {n} velas"],
  "sal.ninguna": ["Exits on the opposite signal", "Sale con la se\u00f1al contraria"],

  "insp.equity": ["Equity curve and drawdowns", "Curva de capital y caídas"],
  "insp.monthly": ["Monthly returns", "Retornos mensuales"],
  "insp.rules": ["Strategy rules", "Reglas de la estrategia"],
  "insp.long_entry": ["Long entry", "Entrada larga"],
  "insp.short_entry": ["Short entry", "Entrada corta"],
  "insp.last_n": ["(last {n} of {total})", "(últimas {n} de {total})"],
  "insp.copy_pine": ["Copy Pine", "Copiar Pine"],
  "insp.save": ["Save to My strategies", "Guardar en Mis estrategias"],
  "insp.export_note": [
    "The <b>.mq5</b> compiles in MetaEditor (F7) and runs in the Strategy Tester. The <b>.pine</b> goes into TradingView's Pine Editor and onto the chart. In both cases, use the same spread you used here.",
    "El <b>.mq5</b> se compila en MetaEditor (F7) y se prueba en el Strategy Tester. El <b>.pine</b> se pega en el Pine Editor de TradingView y se agrega al gráfico. En los dos casos, poné el mismo spread que usaste acá."],
  /* Lo que hay que saber antes de llevar el bot a MetaTrader.

     Las tres lineas salieron de correr el EA exportado en el Strategy Tester y
     comparar con el backtest propio: 147 operaciones contra 145, profit factor
     1.13 contra 1.14, aciertos 38.1% contra 40.7% — pero solo el 5% de las
     entradas en la misma hora, porque los dos historicos difieren 18 puntos en
     promedio sobre el S&P. */
  "mt5.title": ["Before you take it to MetaTrader", "Antes de llevarlo a MetaTrader"],
  "mt5.symbol": [
    "We call this market {nuestro}. Your broker may list it as {otros}. Attach the bot to that chart — on the wrong one it will not place a single trade.",
    "Acá este mercado se llama {nuestro}. Tu bróker puede tenerlo como {otros}. Enganchá el bot a ese gráfico — en el equivocado no va a operar ni una vez."],
  "mt5.feed": [
    "Your broker's price history is not the same data this was mined on, so the bot <b>will not repeat these trades one by one</b>. What carries over is the behaviour: how often it trades, how often it is right, and how much it gives back on the way.",
    "El histórico de precios de tu bróker no es el mismo dato con el que se minó, así que el bot <b>no va a repetir estas operaciones una por una</b>. Lo que se conserva es el comportamiento: cada cuánto opera, con qué proporción de aciertos, y cuánto devuelve en el camino."],
  "mt5.test_first": [
    "Run it in MetaTrader's Strategy Tester over the same period before putting money on it. That is the number your broker will actually give you.",
    "Correlo en el Strategy Tester de MetaTrader sobre el mismo período antes de ponerle plata. Ese es el número que te va a dar tu bróker de verdad."],
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

  /* ------------------------- por qué no entra ninguna candidata */
  "diag.trades": [
    "None of the {n} reached {min} trades. Lower the minimum, or try a smaller timeframe.",
    "Ninguna de las {n} llegó a {min} operaciones. Bajá el mínimo de trades o probá un timeframe más chico."],
  "diag.trades_session": [
    "You are searching only inside {franjas}, which leaves far fewer opportunities per year. Add <b>Around the clock</b> to the sessions, or lengthen the period.",
    "Estás buscando sólo dentro de {franjas}: eso deja mucha menos oportunidad por año. Sumá <b>Todo el día</b> a las franjas o alargá el período."],
  "diag.near": [
    "<b>{n}</b> of them met everything except <b>{criterio}</b>. You asked for {pedido} and the best of those reached <b>{llego}</b>: loosen that filter and they get in.",
    "<b>{n}</b> de ellas cumplían todo salvo <b>{criterio}</b>. Pediste {pedido} y la mejor de ésas llegó a <b>{llego}</b>: aflojá ese filtro y entran."],
  "diag.far": [
    "No candidate came close: they all fail two filters or more at once. The one rejecting the most is <b>{criterio}</b> ({n} of them); you asked for {pedido} and the ones that failed there did not get past <b>{llego}</b>.",
    "Ninguna candidata quedó cerca: todas fallan dos filtros o más a la vez. El que más descarta es <b>{criterio}</b> ({n} de ellas); pediste {pedido} y las que fallaron ahí no pasaron de <b>{llego}</b>."],

  "empty.none_passed": ["{n} tested, none cleared the filters.",
                        "{n} probadas, ninguna pasó los filtros."],
  /* El arreglo de un clic cuando la busqueda no encontro nada.

     El diagnostico ya dice que filtro bloquea, que se pidio y hasta donde se
     llego. Sin esto habia que subir, abrir la seccion 5, encontrar ese filtro
     entre nueve, cambiar el numero y volver a minar: cinco pasos para aplicar
     una conclusion que la aplicacion ya saco.

     El boton dice QUE va a cambiar. Nadie aprieta uno que diga "arreglar". */
  "fix.bajar": ["Lower {criterio} to {valor} and search again",
                "Bajar {criterio} a {valor} y buscar de nuevo"],
  "fix.apagar": ["Turn off {criterio} and search again",
                 "Apagar {criterio} y buscar de nuevo"],
  "fix.aplicado": ["Filter adjusted \u2014 searching again",
                   "Filtro ajustado \u2014 buscando de nuevo"],
  "empty.also": [
    "You can also untick filters in section 5, or change the exits in section 3 — that completely changes which strategies work.",
    "También podés destildar filtros en la sección 5, o cambiar las salidas en la 3 — eso cambia por completo qué estrategias funcionan."],
  "sug.title": ["How to reach that target", "Cómo llegar a ese objetivo"],
  "sug.per_trade": ["risk per trade", "riesgo por operación"],
  "sug.notional": ["notional capital", "capital nominal"],
  "sug.reachable": [
    "At a {unidad} of <b>{actual}%</b> the ceiling is what you saw. To reach your target it would have to go up to <b>{necesario}%</b> ({factor}× more), and the drawdown would go from ~{ddahora}% to <b>~{ddluego}%</b>.",
    "Con un {unidad} de <b>{actual}%</b> el techo es el que viste. Para llegar a tu objetivo habría que subirlo a <b>{necesario}%</b> ({factor}× más), y el drawdown pasaría de ~{ddahora}% a <b>~{ddluego}%</b>."],
  "sug.unreachable": [
    "Raising the risk will not get you there either: it would take <b>{factor}×</b> more ({haria}% per trade), which would blow up the account before reaching it. In this market and with these exits, a realistic target is <b>~{realista}% a year</b> by raising the {unidad} to {subir}%.",
    "Ni subiendo el riesgo se llega: harían falta <b>{factor}×</b> más ({haria}% por operación), lo que reventaría la cuenta antes de lograrlo. Con este mercado y estas salidas, un objetivo realista es <b>~{realista}% anual</b> subiendo el {unidad} a {subir}%."],
  "sug.warn_dd": [
    "A drawdown like that empties real accounts: it means losing more than half the capital before recovering.",
    "Un drawdown así vacía cuentas reales: es perder más de la mitad del capital antes de recuperar."],
  "sug.warn_market": [
    "If you want more return, the thing to change is the market, the timeframe or the exits — not the position size.",
    "Si querés más rendimiento, conviene cambiar el mercado, el timeframe o las salidas — no forzar el tamaño de posición."],
  "sug.apply_target": ["Set the target to {n}% a year and search again",
                       "Fijar objetivo en {n}% anual y volver a minar"],
  "sug.apply_risk": ["Raise it to {n}% and search again", "Subir a {n}% y volver a minar"],

  /* --------------------------------------------- columnas de las tablas */
  "col.strategy": ["Strategy", "Estrategia"],
  "col.equity": ["Equity", "Capital"],
  "col.annual": ["Annual", "Anual"],
  "col.maxdd": ["Max DD", "Máx. DD"],
  "col.ops": ["Trades", "Ops."],
  "col.months_plus": ["Months +", "Meses +"],
  "col.oos": ["Out of<br>sample", "Fuera<br>de muestra"],
  "col.oos_full": ["Out of sample", "Fuera de muestra"],
  "col.score_help": [
    "The app's own robustness score: how repeatable the strategy looks, not how much it returned.",
    "Puntaje propio de robustez: qué tan repetible parece la estrategia, no cuánto rindió."],
  "col.ops_help": [
    "Number of trades. Few trades make any metric unreliable.",
    "Cantidad de operaciones. Pocas operaciones hacen que cualquier métrica sea poco confiable."],
  "col.months_help": [
    "Share of months closed in profit. High means it wins steadily, not in a single stroke.",
    "Porcentaje de meses cerrados en ganancia. Alto significa que gana seguido, no de un solo golpe."],
  "col.oos_help": [
    "Out-of-sample profit factor divided by the in-sample one. Near 1 the edge held; near 0 the strategy was only describing the past.",
    "Profit factor fuera de muestra dividido por el de adentro. Cerca de 1 la ventaja se sostuvo; cerca de 0 la estrategia sólo describía el pasado."],
  "col.click_sort": ["click to sort", "clic para ordenar"],
  "col.oos_holds": ["holds", "se sostiene"],
  "col.oos_weakens": ["weakens", "se debilita"],
  "col.oos_falls": ["falls apart", "se cae"],
  "col.oos_nodata": ["no data", "sin datos"],
  "col.oos_nodata_help": ["It did not trade in the reserved stretch: there is nothing to check.",
                          "No operó en el tramo reservado: no hay nada que validar."],

  /* ------------------------------------- antes de la primera búsqueda */
  "idle.title": ["Ready to search", "Listo para minar"],
  "idle.plan": [
    "You are going to look for <b>{goal} strategies</b> on <b>{mercado}</b> in <b>{tf}</b> bars, {tamano} at <b>{rr}</b> risk/reward. Anything with <b>{trades}+ trades</b> enters the databank",
    "Vas a buscar <b>{goal} estrategias</b> sobre <b>{mercado}</b> en velas de <b>{tf}</b>, {tamano} y relación <b>{rr}</b>. Entran al databank las que hagan <b>{trades}+ operaciones</b>"],
  /* Cuando una receta busca varias relaciones riesgo:beneficio, decir "1:2"
     sería mentir: esa corrida no va a usar ninguna relación fija. */
  /* ─────────────────────── buscar la relación en vez de fijarla ───────────
     Es la perilla que más cambia lo que la búsqueda puede encontrar, y hasta
     ahora sólo se podía tocar eligiendo una categoría. */
  "rr.fija": ["Fixed", "Fija"],
  "rr.buscar": ["Search it", "Buscarla"],
  "rr.fija_ayuda": [
    "Every candidate uses the ratio above. It caps the win rate: risking 1 to "
    + "make 2 needs about a third of trades to win, and that is what you get.",
    "Todas las candidatas usan la relación de arriba. Es lo que le pone techo al "
    + "win rate: arriesgar 1 para ganar 2 necesita acertar un tercio, y eso es lo "
    + "que se acierta."],
  "rr.buscar_ayuda": [
    "Each candidate gets its own ratio, from 1:{desde} to 1:{hasta} ({n} values). "
    + "Widens what the search can find: measured, the win rate range nearly doubles.",
    "Cada candidata lleva la suya, de 1:{desde} a 1:{hasta} ({n} valores). Ensancha "
    + "lo que la búsqueda puede encontrar: medido, el abanico de win rate casi se "
    + "duplica."],
  "rr.varias": ["1:{desde} to 1:{hasta} (searched)",
                "de 1:{desde} a 1:{hasta} (se busca)"],
  "idle.and_meet": ["and also meets: {lista}.", "y cumplan: {lista}."],
  "idle.session_one": ["Only during {nombre} ({horas}).", "Sólo durante {nombre} ({horas})."],
  "idle.session_many": [
    "The search will pick the best of {n} trading sessions for each strategy.",
    "La búsqueda va a elegir la mejor de {n} franjas horarias para cada estrategia."],
  "idle.no_filters": [
    "With no filters on, anything gets in — including strategies that lose money. Tick <b>Profit factor ≥ 1</b> in section 5 to keep only the winners.",
    "Sin filtros activos entra cualquier estrategia, incluso las que pierden plata. Tildá <b>Profit factor ≥ 1</b> en la sección 5 para quedarte sólo con las ganadoras."],
  "idle.s1": ["A candidate gets built", "Se arma una candidata"],
  "idle.s1_sub": [
    "It randomly combines an entry trigger, context filters, a trading session and each indicator's parameters.",
    "Combina al azar un disparador de entrada, filtros de contexto, una franja horaria y los parámetros de cada indicador."],
  "idle.s2": ["It gets fully backtested", "Se backtestea entera"],
  "idle.s2_sub": ["Over every year of real data, with your costs and your risk model.",
                  "Sobre todos los años de datos reales, con tus costos y tu modelo de riesgo."],
  "idle.s3": ["It passes or it is discarded", "Pasa o se descarta"],
  "idle.s3_sub": [
    "If it meets the filters it enters the databank ranked by score; if not, it is thrown away and another is tried.",
    "Si cumple los filtros entra al databank ordenada por score; si no, se tira y se prueba otra."],
  "idle.s4": ["It repeats without stopping", "Se repite sin parar"],
  "idle.s4_sub": [
    "Until it has the {goal} you asked for. Each one can be inspected and exported to MetaTrader.",
    "Hasta juntar las {goal} que pediste. Cada una se puede inspeccionar y exportar a MetaTrader."],

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

  "sug.risk_again": ["Risk {pct}% — searching again", "Riesgo {pct}% — buscando de nuevo"],
  "sug.target_again": ["Target {pct}% a year — searching again",
                       "Objetivo {pct}% anual — buscando de nuevo"],
  "sum.blocks": ["{drv} triggers · {flt} filters",
                 "{drv} disparadores · {flt} filtros"],
  "sum.no_filters": ["With no filters ticked, every strategy is just its entry trigger.",
                     "Sin filtros marcados, cada estrategia es sólo su disparador de entrada."],
  "sum.minimal_ignores": [
    "At <b>{nombre}</b> the ticked filters are not used: each strategy enters on its trigger alone.",
    "En <b>{nombre}</b>, los filtros marcados no se usan: cada estrategia entra sólo con su disparador."],
  "sum.filters_note": [
    "You ticked <b>{flt} filters</b>. Each candidate picks <b>between 0 and {n}</b> of them at random and requires them all at once. More filters per strategy means more specific rules: they trade less often and depend more on the market repeating those same conditions.",
    "Marcaste <b>{flt} filtros</b>. Cada candidata elige al azar <b>entre 0 y {n}</b> de ellos y los exige a la vez. Más filtros por estrategia hace reglas más específicas: operan menos seguido y dependen más de que el mercado repita esas mismas condiciones."],
  "sum.lots": ["{lots} fixed lots", "{lots} lotes fijos"],
  "sum.risk": ["{pct}% per trade", "{pct}% por operación"],
  "sum.only_trades": ["only {n}+ trades — nothing else filtered",
                      "sólo {n}+ operaciones — el resto sin filtrar"],

  /* --------------------------------------- qué significa cada métrica
     Los nombres no se traducen; esto sí. Van en el título de cada fila para
     que se pueda preguntar qué es un profit factor sin salir de la pantalla. */
  "crit.minPf": [
    "How many dollars it made for every dollar it lost. At 1 it broke even; below that the strategy loses money. It ships ticked at 1 precisely so the databank does not fill up with losers.",
    "Cuántos dólares ganó por cada dólar que perdió. En 1 quedó igual; por debajo, la estrategia pierde plata. Viene tildado en 1 justamente para que el databank no se llene de perdedoras."],
  "crit.minRetDd": [
    "Net profit divided by the worst fall. It joins the two halves of the question — how much it made and how much you had to sit through — and it does not move when you change the risk per trade. At 1 it made exactly what it fell; 2 is demanding and 3 is passed by one in ten in a good market.",
    "Ganancia neta dividida por la peor caída. Junta las dos mitades de la pregunta —cuánto ganó y cuánto hubo que aguantar— y no se mueve si cambiás el riesgo por operación. En 1 ganó justo lo que llegó a caer; 2 ya es exigente y 3 lo pasa una de cada diez en un mercado bueno."],
  "crit.maxDd": [
    "The worst the account ever fell from a peak to a bottom. It is what you have to be able to sit through without closing everything.",
    "Lo peor que llegó a bajar la cuenta desde un pico hasta el fondo. Es lo que hay que poder aguantar sin cerrar todo."],
  "crit.minWinRate": [
    "Share of winning trades. Careful: at a 1:2 risk/reward, 40% is already profitable — a high win rate is not the same as making more money.",
    "Porcentaje de operaciones ganadoras. Ojo: con una relación riesgo/beneficio de 1:2, un 40% ya es rentable — un win rate alto no es lo mismo que ganar más."],
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
    "Qué porcentaje del tiempo estuvo con una posición abierta. Muy bajo significa que opera poquísimo y la muestra vale poco."],
  "crit.minTrades": ["Minimum trades", "Mínimo de operaciones"],

  /* ------------------------------------------------- complejidad de las reglas */
  "cx.0": ["Minimal", "Mínima"],
  "cx.0_sub": ["trigger only", "sólo el disparador"],
  "cx.0_help": [
    "The entry trigger and nothing else. It is the hardest to overfit and the most honest place to start: if you find nothing here, the filters are not the problem.",
    "Sólo el disparador de entrada. Es lo más difícil de sobreajustar y lo más honesto como punto de partida: si acá no encontrás nada, el problema no son los filtros."],
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
    "Up to three. It finds much prettier backtests and considerably less repeatable ones: check them out of sample before believing them.",
    "Hasta tres. Encuentra backtests mucho más lindos y bastante menos repetibles: validá fuera de muestra antes de creerles."],

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
    "Every hour of the day trades differently. A rule that works between the New York open and the close can lose money running overnight, when the same instrument moves on a tenth of the volume and a much wider spread. Pick the one that fits the instrument. Ticking several lets the search choose per strategy, which explores more but also overfits more.",
    "Cada hora del día se opera distinto. Una regla que funciona entre la apertura de Nueva York y el cierre puede perder plata de madrugada, cuando el mismo instrumento se mueve con una décima parte del volumen y un spread mucho más ancho. Elegí la que le corresponda al instrumento. Tildar varias deja que la búsqueda elija por estrategia, que explora más pero también sobreajusta más."],
  "session.searched": [
    "The search picks the best of the {n} windows you ticked — <b>for each candidate</b>. That is {n} chances to fit noise, and it shows: measured over twelve years, enabling all nine windows drops the average annual return from <b>2.49% to 1.85%</b> on the S&P 500 and from 3.80% to 2.22% on gold. Picking <b>one</b> window on purpose is the version that helps.",
    "La búsqueda elige la mejor de las {n} franjas que tildaste — <b>para cada candidata</b>. Eso son {n} oportunidades de pegarle al ruido, y se nota: medido sobre doce años, habilitar las nueve baja el rendimiento medio de <b>2,49% a 1,85%</b> anual en el S&P 500 y de 3,80% a 2,22% en oro. Elegir <b>una sola</b> a propósito es la versión que sí ayuda."],
  "session.fixed": ["Every strategy will trade only in this window.",
                    "Todas las estrategias van a operar sólo en esta franja."],
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
    "Lit up: the New York session. The same rule meets a different market outside it.",
    "Encendida: la sesi\u00f3n de Nueva York. Fuera de ah\u00ed, la misma regla se encuentra otro mercado."],

  "g.funnel": ["Candidates that clear the bar", "Candidatas que pasan la vara"],
  "g.bar_low": ["Low bar", "Vara baja"],
  "g.bar_high": ["High bar", "Vara alta"],
  "g.funnel_note": [
    "How far you can raise it depends on the instrument and the period. Raise it until the databank starts to thin out.",
    "Hasta d\u00f3nde se puede subir depende del instrumento y del per\u00edodo. Subila hasta que el databank empiece a ralear."],

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
    "A hundred thousand times cheaper, and nothing warns you.",
    "Cien mil veces más barato, y nada te avisa."],
  "g.utc_mined": ["UTC — where it was mined", "UTC — donde se minó"],
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
  "acc.tambien_fuera": ["Also out of sample", "También fuera de muestra"],
  "acc.solo_dentro_ayuda": [
    "The filters apply to the stretch the search looked at. The reserved stretch still lowers the score of whatever did not hold up there, but does not reject it.",
    "Los filtros se aplican al tramo que miró la búsqueda. El tramo reservado igual le baja el score a lo que no aguantó ahí, pero no lo descarta."],
  /* Dice que TARDA MAS además de que salen menos: medido sobre EURUSD, con
     esto la tasa de aceptación cayó a 0,6% y juntar diez llevó unos diez
     minutos. Sin avisarlo, alguien lo prende y cree que la búsqueda se colgó. */
  "acc.tambien_fuera_ayuda": [
    "The same thresholds have to hold on the reserved stretch too, and one that never traded there does not pass: not measuring is not passing. Fewer will come out and the search takes longer — but every one of them held up where the search never looked.",
    "Los mismos umbrales tienen que cumplirse también en el tramo reservado, y una que no operó ahí no pasa: no medir no es aprobar. Van a salir menos y la búsqueda tarda más, pero cada una aguantó donde la búsqueda no miró."],
  "acc.necesita_reserva": [
    "Turn on the reserved stretch in step 1 to be able to demand it out of sample.",
    "Prendé el tramo reservado en el paso 1 para poder exigirlo fuera de muestra."],

  /* Las dos secciones. El rótulo dice QUE se opera, no dónde: un trader sabe
     si opera CFD o cripto, y de ahí se deduce todo lo demás —dónde se ejecuta,
     cómo se paga y cómo se exporta—. */
  "mundo.rotulo": ["What you trade", "Qué operás"],
  "mundo.cfds": ["CFDs", "CFDs"],
  "mundo.cfds_sub": [
    "Indices, forex and metals through MetaTrader. You pay the spread and take them as Expert Advisors.",
    "Índices, forex y metales por MetaTrader. Se paga el spread y se llevan como Expert Advisor."],
  "mundo.cripto": ["Crypto", "Cripto"],
  "mundo.cripto_sub": [
    "Perpetual futures on an exchange. You pay commission and funding, and they connect to the exchange.",
    "Futuros perpetuos en un exchange. Se paga comisión y funding, y se conectan al exchange."],

  "nav.operar": ["Trade", "Operar"],

  /* LA ESCALERA: hasta dónde puede llegar una estrategia.
     simulacro → práctica → real, y cada escalón pide más que el anterior.
     Los textos existen desde acá; el código que los pide ya estaba y pedía
     claves que nadie había escrito, así que las pestañas y la escalera se
     dibujaban con el nombre interno de la clave. */
  "esc.title": ["How far this one can go", "Hasta dónde puede llegar"],
  "esc.sub": [
    "Each rung asks for more than the one before, and the last one asks for it outside the sample the search looked at.",
    "Cada escalón pide más que el anterior, y el último lo pide además afuera de la muestra que miró la búsqueda."],
  "esc.simulacro": ["Simulation", "Simulacro"],
  "esc.practica": ["Practice", "Práctica"],
  "esc.real": ["Real money", "Plata real"],
  "esc.ninguno": ["Not yet", "Todavía no"],
  "esc.hasta": ["up to {destino}", "hasta {destino}"],
  "esc.libre": ["always available — no money at risk",
                "siempre disponible — no hay plata en juego"],
  "esc.habilitada": ["clear", "habilitada"],
  "esc.falta": ["For {destino}: {motivo}", "Para {destino}: {motivo}"],
  /* Cuando la cantera dice que no y no explica: pasa con las guardadas viejas,
     que no tienen las métricas que la vara mira. */
  "esc.falta_sin_motivo": ["not enough measured yet", "todavía falta medirla"],
  "esc.pie": [
    "Getting past a rung is permission, not advice: it says the numbers hold up, not that it will work.",
    "Pasar un escalón es un permiso, no un consejo: dice que los números aguantan, no que vaya a funcionar."],

  /* Las dos pestañas de Operar y lo que las acompaña. */
  "op.tab_bot": ["Bot", "Bot"],
  "op.tab_claves": ["Exchange keys", "Claves"],
  "op.sin_claves": ["No key loaded yet", "Todavía no cargaste ninguna clave"],
  /* Decía "un bot por vez sobre una cuenta", que fue cierto hasta que el
     piloto aprendió a sostener varios. La regla real es POR SIMBOLO. */
  "op.sub_bot": [
    "One bot per symbol: several can run at once, each sized on its own share of the account.",
    "Un bot por símbolo: pueden correr varios a la vez, cada uno dimensionado sobre su porción de la cuenta."],
  "op.ir_claves": ["Load a key", "Cargar una clave"],
  /* Binance va SOLO en demo, y el rotulo lo dice en el titulo y no en una
     nota al pie: si estuviera abajo, alguien carga la clave, ve "configurada"
     y da por hecho que puede operar en real. */
  /* El exchange se ELIGE. Ver el comentario del select en app.js. */
  /* EL TABLERO. El resultado va PARTIDO por concepto: un numero solo esconde
     si la estrategia no sirve o si sirve y los costos se la comen. */
  "op.tab_tablero": ["Performance", "Rendimiento"],
  "tab.titulo": ["What the account actually did", "Lo que la cuenta hizo de verdad"],
  "tab.sub": [
    "Straight from Binance demo, not from what the bots remember: the bot's log is lost when the app closes and knows nothing about fees.",
    "Directo de Binance demo, no de lo que los bots recuerdan: el registro del bot se pierde al cerrar la app y no sabe de comisiones."],
  "tab.sin_clave": ["No demo key loaded", "No hay clave demo cargada"],
  "tab.sin_clave_sub": [
    "Load the Binance demo key in the Exchange keys tab and this fills in on its own.",
    "Cargá la clave demo de Binance en la pestaña de Claves y esto se llena solo."],
  "tab.cargando": ["Asking the exchange…", "Preguntándole al exchange…"],
  "tab.saldo": ["Balance", "Saldo"],
  "tab.neto": ["Net result", "Resultado neto"],
  "tab.cerradas": ["Closed trades", "Operaciones cerradas"],
  "tab.wr": ["Win rate", "Win rate"],
  "tab.pnl": ["Trading P&L", "P&L de las operaciones"],
  "tab.comision": ["Fees", "Comisiones"],
  "tab.funding": ["Funding", "Funding"],
  "tab.parte_nota": [
    "Split on purpose: P&L can be positive and the account still down because fees ate it. One single number would say \"losing\" and send you to change the strategy, when what to change is how often it trades.",
    "Partido a propósito: el P&L puede estar en positivo y la cuenta en negativo porque las comisiones se lo comieron. Un número solo diría \"pierde\" y mandaría a cambiar la estrategia, cuando lo que hay que cambiar es cuánto opera."],
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
    "Pick several, see the plan -shares, expectations, warnings- and only then start them together.",
    "Elegí varias, mirá el plan —porciones, expectativas, avisos— y recién ahí encendelas juntas."],
  "conj.armar": ["Preview the plan", "Armar el plan"],
  "conj.encender": ["Start the set (demo)", "Encender el conjunto (demo)"],
  "conj.elegi": ["Pick at least two strategies", "Elegí al menos dos estrategias"],
  "conj.retorno": ["Expected yearly return", "Retorno anual esperado"],
  "conj.ops": ["Trades per month", "Operaciones por mes"],
  "conj.wr": ["Expected win rate", "Win rate esperado"],
  "conj.dd": ["Worst individual drawdown", "Peor caída individual"],
  "conj.fuente": [
    "From each strategy's backtest, aggregated. An expectation, not a promise: the traffic light will say if it stops being true.",
    "Del backtest de cada una, agregado. Una expectativa, no una promesa: el semáforo va a avisar si deja de cumplirse."],
  "conj.ops_cortas": ["{n} ops/mo", "{n} ops/mes"],
  "conj.encendido": ["{n} bots running", "{n} bots encendidos"],
  "conj.fallo": [
    "Started {n} and then one failed: {err}. The ones already running stay on.",
    "Encendió {n} y uno falló: {err}. Los que ya arrancaron siguen encendidos."],
  "bot.esperado_mes": ["≈{n} trades/mo per its backtest", "≈{n} ops/mes según su backtest"],
  "bot.proxima": ["next candle ~{h}", "próxima vela ~{h}"],

  /* VARIOS BOTS. El rótulo dice CUANTOS y no "encendido": con cinco
     corriendo, "encendido" no dice si están los cinco o quedó uno. */
  "bot.n_operando": ["{n} operating", "{n} operando"],
  "bot.maneja": ["Handles {pct}% of the account", "Maneja el {pct}% de la cuenta"],
  "bot.reparto": [
    "{usado}% of the account is committed, {libre}% free.",
    "El {usado}% de la cuenta está comprometido, queda {libre}% libre."],
  "bot.apagar_todos": ["Stop them all", "Apagarlos a todos"],
  "bot.porcion": ["Share of the account (%)", "Porción de la cuenta (%)"],
  "bot.porcion_nota": [
    "Each bot sizes its risk on ITS share, not on the whole balance. Fixed when it starts: turning on a new bot must not resize one that already has a position open.",
    "Cada bot calcula su riesgo sobre SU porción, no sobre el saldo entero. Se fija al encender: prender uno nuevo no puede cambiarle el tamaño a otro que ya tiene una posición abierta."],
  "bot.sin_lugar": ["No room for another one", "No hay lugar para otro"],
  "bot.sin_lugar_sub": [
    "Either every slot is taken or the account is fully committed. Stop one to free up its share.",
    "O están todos los lugares ocupados, o la cuenta está comprometida entera. Apagá uno para liberar su porción."],

  "bot.casa": ["Exchange", "Exchange"],
  "bot.casa_bingx": ["BingX", "BingX"],
  "bot.casa_binance": ["Binance (demo only)", "Binance (sólo demo)"],
  "bot.casa_binance_nota": [
    "On Binance the app only trades the demo environment, with fake money. There is no way to send it a real order.",
    "En Binance la aplicación sólo opera el entorno demo, con plata de juguete. No tiene forma de mandarle una orden real."],

  "ex.bn_t": ["Binance (demo only)", "Binance (sólo demo)"],
  "ex.bn_sub": [
    "Fake money on Binance's demo environment. The app has no way to send a real order to Binance.",
    "Plata de juguete en el entorno demo de Binance. La aplicación no tiene forma de mandarle una orden real."],
  "ex.bn_crear": ["Create the demo key", "Crear la clave demo"],
  "ex.bn_ver": ["Watch it execute", "Ver cómo ejecuta"],
  "ex.bn_nota": [
    "The demo key is created on demo.binance.com, not on binance.com: that one belongs to your real account. The second link opens the screen where you can watch the order land.",
    "La clave demo se crea en demo.binance.com, no en binance.com: esa es la de tu cuenta real. El segundo enlace abre la pantalla donde ves la orden aparecer."],

  "ex.sub": ["Connect an exchange so a strategy can trade on its own",
             "Conectá un exchange para que una estrategia opere sola"],
  "ex.regla1_t": ["Your keys stay on this computer",
                  "Tus claves se quedan en esta computadora"],
  "ex.regla1": ["They are encrypted with your Windows account and never reach our servers. Nobody else on this machine can read them.",
                "Se cifran con tu cuenta de Windows y no llegan nunca a nuestros servidores. Nadie más en esta máquina puede leerlas."],
  "ex.regla2_t": ["Create the key WITHOUT withdrawal permission",
                  "Creá la clave SIN permiso de retiro"],
  "ex.regla2": ["Reading and trading is all it needs. With withdrawal disabled, even a stolen key cannot take your funds out.",
                "Con lectura y trading alcanza. Sin retiro, ni siquiera una clave robada puede sacarte los fondos."],
  "ex.regla3_t": ["Start on the practice account",
                  "Empezá en la cuenta de práctica"],
  "ex.regla3": ["BingX has a demo environment with play money and the same API. Run it there for a few weeks before risking anything.",
                "BingX tiene un entorno demo con plata de juguete y la misma API. Corrila ahí unas semanas antes de arriesgar nada."],
  "ex.practica": ["Practice account", "Cuenta de práctica"],
  "ex.practica_sub": ["Play money, real market data", "Plata de juguete, mercado real"],
  "ex.real": ["Live account", "Cuenta real"],
  "ex.real_sub": ["Real money. Only after practice convinced you.",
                  "Plata de verdad. Sólo después de que la práctica te haya convencido."],
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
  "ex.paso_posiciones": ["Open positions", "Posiciones abiertas"],
  "bot.sin_cripto": ["No crypto strategy saved yet",
                     "Todavía no hay ninguna estrategia de cripto guardada"],
  /* NO ENUMERA LOS PARES. Decía "BTCUSDT o ETHUSDT" cuando eran los dos
     únicos, y con trece quedó mintiendo: mandaba a minar sobre dos de trece.
     Un texto que lista opciones envejece cada vez que se agrega una. */
  "bot.sin_cripto_sub": ["A crypto exchange cannot trade indices or metals. Mine on one of the perpetuals and save it, and it will show up here.",
                         "Un exchange de cripto no opera índices ni metales. Miná sobre alguno de los perpetuos y guardala, y va a aparecer acá."],
  "bot.acc_nada": ["waited", "esperó"],
  "bot.acc_largo": ["opened long", "abrió largo"],
  "bot.acc_corto": ["opened short", "abrió corto"],
  "bot.acc_cerrar": ["closed", "cerró"],
  "bot.acc_panico": ["panic stop", "pánico"],
  "bot.tope": ["Daily loss limit", "Tope de pérdida diaria"],
  "bot.tope_nota": ["In account currency. When the day's REALISED losses reach it, the bot stops until tomorrow. 0 means no limit. Floating losses do not count: that is what the stop is for.",
                    "En la moneda de la cuenta. Cuando las pérdidas REALIZADAS del día llegan ahí, el bot se detiene hasta mañana. 0 es sin tope. Las pérdidas flotantes no cuentan: para eso está el stop."],
  "bot.no_habilitado": ["not qualified yet", "todavía no habilitada"],
  "bot.falta_clave_larga": ["You need to load the API key for that account above.",
                            "Hace falta cargar arriba la clave de esa cuenta."],
  "bot.vig_titulo": ["Not trading as measured:", "No opera como se midió:"],
  "bot.title": ["Run a strategy", "Operar una estrategia"],
  "bot.sub": ["It trades while this app is open. Closing the app stops it.",
              "Opera mientras esta aplicación esté abierta. Al cerrarla, para."],
  "bot.on": ["running", "encendido"],
  "bot.off": ["stopped", "apagado"],
  "bot.detenido": ["stopped itself", "se detuvo solo"],
  "bot.estrategia": ["Strategy", "Estrategia"],
  "bot.modo": ["Mode", "Modo"],
  "bot.elegir": ["Choose…", "Elegí…"],
  "bot.sin_clave": ["no key loaded", "sin clave cargada"],
  "bot.modo_simulacro": ["Dry run — decides but never orders",
                         "Simulacro — decide pero no manda órdenes"],
  "bot.modo_practica": ["Practice account", "Cuenta de práctica"],
  "bot.modo_real": ["Live account — real money", "Cuenta real — plata de verdad"],
  "bot.encender": ["Start", "Encender"],
  "bot.apagar": ["Stop", "Apagar"],
  "bot.panico": ["Stop and close position", "Apagar y cerrar posición"],
  "bot.apagar_nota": ["Stopping leaves any open position alone, with its stop still on the exchange. Use the other button to close it too.",
                      "Apagar deja la posición abierta como está, con su stop puesto en el exchange. Para cerrarla también, usá el otro botón."],
  "bot.encendido": ["Bot started", "Bot encendido"],
  "bot.apagado": ["Bot stopped", "Bot apagado"],
  "bot.panico_hecho": ["Stopped and position closed", "Apagado y posición cerrada"],
  "bot.falta_elegir": ["Pick a strategy and a mode", "Elegí una estrategia y un modo"],
  "bot.no_esta": ["That strategy is no longer saved", "Esa estrategia ya no está guardada"],
  "bot.real_seguro": ["This will trade with REAL money. Did the practice account convince you first?",
                      "Esto va a operar con plata DE VERDAD. ¿La cuenta de práctica te convenció antes?"],
  "bot.panico_seguro": ["Stop the bot and close the open position at market?",
                        "¿Apagar el bot y cerrar la posición abierta a mercado?"],
  "nav.tips": ["Tips", "Consejos"],
  "tips.sub": [
    "What we learned measuring, not what gets repeated around.",
    "Lo que aprendimos midiendo, no lo que se repite por ahí."],
  "tips.foot": [
    "Every figure here was measured on the instruments the app ships with. Your own numbers will differ; the direction will not.",
    "Todas las cifras de acá se midieron sobre los instrumentos que trae la aplicación. Tus números van a ser otros; la dirección no."],

  "tip.historia": ["Choose the window with intent", "Elegí la ventana a conciencia"],
  "tip.historia_cuerpo": [
    "The period you search over sets what the search can find. Ask for a short window and returns come out higher, because the strategy only has to work through the conditions of those few years. Ask for the whole history and it has to survive rallies, crashes and flat stretches: fewer make it through, and the ones that do carry more behind them.\n\nNeither is the right answer. Search short when you want to see what an instrument can give; search long when you are choosing something to actually run.",
    "El período sobre el que buscas define lo que la búsqueda puede encontrar. Pedí una ventana corta y los retornos salen más altos, porque la estrategia sólo tiene que funcionar en las condiciones de esos pocos años. Pedí todo el histórico y tiene que sobrevivir subidas, derrumbes y tramos planos: pasan menos, y las que pasan llevan más detrás.\n\nNinguna de las dos es la respuesta correcta. Buscá corto cuando querés ver qué puede dar un instrumento; buscá largo cuando estás eligiendo algo para poner a operar."],

  "tip.horario": ["The hour changes everything", "El horario cambia todo"],
  "tip.horario_cuerpo": [
    "An index at three in the morning trades with a fraction of the volume and a much wider spread than at the New York open. They are different markets wearing the same name, and a rule built for one has no reason to work in the other.\n\nRestricting the hours narrows what the search can look at, so it finds fewer strategies — and the ones it finds only have to work in conditions that resemble each other.",
    "Un índice a las tres de la mañana cotiza con una fracción del volumen y un spread mucho más ancho que en la apertura de Nueva York. Son mercados distintos con el mismo nombre, y una regla armada para uno no tiene por qué funcionar en el otro.\n\nRestringir el horario achica lo que la búsqueda puede mirar, así que encuentra menos estrategias — y las que encuentra sólo tienen que funcionar en condiciones que se parecen entre sí."],

  "tip.spread": ["Set the spread for each instrument", "El spread va por instrumento"],
  "tip.spread_cuerpo": [
    "Costs are expressed in the instrument's own price units, and those units are not comparable across markets: what counts as a normal spread on a currency pair is a rounding error on an index, and the other way round.\n\nSwitching instruments without updating the cost raises no error. The search simply runs against a cost that is not the one you will pay. The app suggests one per instrument — take it, and check it against your broker.",
    "Los costos se expresan en las unidades de precio del propio instrumento, y esas unidades no son comparables entre mercados: lo que es un spread normal en un par de divisas es un error de redondeo en un índice, y al revés.\n\nCambiar de instrumento sin actualizar el costo no da ningún error. La búsqueda simplemente corre contra un costo que no es el que vas a pagar. La aplicación sugiere uno por instrumento: aceptalo, y comprobalo contra tu bróker."],

  "tip.vara": ["Raise the bar gradually", "Subí la vara de a poco"],
  "tip.vara_cuerpo": [
    "Return over drawdown is the filter worth demanding: it joins both halves of the question — how much it made and how much you had to sit through — into one number that does not move when you change risk per trade.\n\nHow high you can set it depends entirely on the instrument and the period. Start low, watch how many candidates get through, and raise it from there. While the search runs it tells you which filter is holding everything back, so you never have to guess.",
    "Retorno sobre drawdown es el filtro que conviene exigir: junta las dos mitades de la pregunta —cuánto ganó y cuánto hubo que aguantar— en un solo número que no se mueve al cambiar el riesgo por operación.\n\nHasta dónde podés subirlo depende por completo del instrumento y del período. Arrancá bajo, mirá cuántas candidatas entran, y subilo desde ahí. Mientras la búsqueda corre te va diciendo cuál es el filtro que está frenando todo, así que nunca tenés que adivinar."],

  "tip.riesgo": ["Risk scales both halves", "El riesgo escala las dos mitades"],
  "tip.riesgo_cuerpo": [
    "Raising risk per trade does not find a better strategy: it runs the same one bigger. Return and drawdown grow together, near enough in step, so the shape of the equity curve stays exactly as it was — only the scale changes.\n\nWhich means risk is not the knob to turn when the results disappoint. Change the instrument, the timeframe or the exits.",
    "Subir el riesgo por operación no encuentra una estrategia mejor: corre la misma más grande. Rendimiento y caída crecen juntos, casi al mismo ritmo, así que la forma de la curva de capital queda igual que estaba — lo único que cambia es la escala.\n\nO sea que el riesgo no es la perilla que hay que mover cuando el resultado decepciona. Cambiá el instrumento, el timeframe o las salidas."],

  "tip.zona": ["Your broker's clock is not UTC", "El reloj de tu bróker no está en UTC"],
  "tip.zona_cuerpo": [
    "This matters only for strategies with a trading-hours restriction. The price data here is UTC; MetaTrader stamps its bars in the <b>broker's server time</b>, and most brokers run on UTC+2 or UTC+3. Your own country's timezone is irrelevant — two people in different countries with the same broker get identical backtests.",
    "Esto importa sólo en estrategias con restricción de horario. Los datos de precio de acá están en UTC; MetaTrader fecha sus velas con la <b>hora del servidor del bróker</b>, y la mayoría corre en UTC+2 o UTC+3. Tu zona horaria no influye: dos personas en países distintos con el mismo bróker obtienen backtests idénticos."],

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

  "data.broker": ["Your broker's clock", "El reloj de tu bróker"],
  "data.broker_hint": ["set once, used by every exported robot",
                       "se pone una vez y la usan todos los robots exportados"],
  "data.broker_help": [
    "The price data here is UTC. MetaTrader stamps its bars in the <b>broker's server time</b>, and most brokers run two or three hours ahead. Your own country's timezone plays no part: two people in different countries with the same broker get identical backtests.",
    "Los datos de precio de acá están en UTC. MetaTrader fecha sus velas con la <b>hora del servidor del bróker</b>, y la mayoría va dos o tres horas adelantada. Tu zona horaria no interviene: dos personas en países distintos con el mismo bróker obtienen backtests idénticos."],
  "data.broker_offset": ["Broker server", "Servidor del bróker"],
  "data.broker_now": ["Right now it would be", "Ahora mismo serían las"],
  "data.broker_note": [
    "Compare that time with the clock in MetaTrader's Market Watch. When they match, the setting is right — and it only matters for strategies with a trading-hours restriction.",
    "Compará esa hora con el reloj de Observación de Mercado en MetaTrader. Cuando coinciden, el valor es el correcto — y sólo importa en estrategias con restricción de horario."],
  "data.broker_saved": ["Saved. Robots exported from now on carry it.",
                        "Guardado. Los robots que exportes de ahora en más la llevan."],
  "mine.tab_search": ["Search", "Buscar"],
  "mine.tab_results": ["Results", "Resultados"],
  "exp.pine_copied": ["Pine copied — paste it into TradingView's Pine Editor",
                      "Pine copiado — pegalo en el Pine Editor de TradingView"],
  "saved.mined_on": ["Mined on {fecha}", "Minada el {fecha}"],
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

  "est.sin_probar": ["Not tested", "Sin probar"],
  "est.aprobada": ["Passed", "Aprobada"],
  "est.aceptable": ["Partly held", "Aguantó a medias"],
  "est.no_paso": ["Did not hold", "No pasó"],
  "est.help": [
    "Whether the strategy still worked on data it had never seen.",
    "Si la estrategia siguió funcionando sobre datos que nunca había visto."],

  "wf.frase_aprobada": [
    "It made money in {g} of {n} stretches it had never seen, and kept most of what it was earning.",
    "Ganó en {g} de {n} tramos que nunca había visto, y conservó la mayor parte de lo que rendía."],
  "wf.frase_aceptable_ef": [
    "It made money in all {n} stretches, but earned considerably less outside than inside. Worth keeping; not worth trusting blind.",
    "Ganó en los {n} tramos, pero afuera rindió bastante menos que adentro. Vale conservarla; no para confiarle plata a ciegas."],
  "wf.frase_aceptable_tramos": [
    "It made money in {g} of {n} stretches. Worth keeping; not worth trusting blind.",
    "Ganó en {g} de {n} tramos. Vale conservarla; no para confiarle plata a ciegas."],
  "wf.frase_no_paso_tramos": [
    "It only made money in {g} of {n} stretches: it was describing the past.",
    "Sólo ganó en {g} de {n} tramos: estaba describiendo el pasado."],
  "wf.frase_no_paso_ef": [
    "It made money in {g} of {n} stretches, but almost none of its edge survived outside the data it was found on.",
    "Ganó en {g} de {n} tramos, pero casi nada de su ventaja sobrevivió fuera de los datos donde se la encontró."],

  "wf.test_it": ["Put it to the test", "Poner a prueba"],
  "wf.retest": ["Test again", "Volver a probar"],
  "wf.testing": ["Testing", "Probando"],
  "wf.done": ["{nombre} tested", "{nombre} probada"],
  "wf.untested": ["This one has not been tested yet", "Esta todavía no se probó"],
  "wf.untested_sub": [
    "The search chose it by looking at this whole period, so its numbers here are flattering by construction. The test refits it in stretches and judges it on data it never saw.",
    "La búsqueda la eligió mirando todo este período, así que sus números acá son favorables por construcción. La prueba la reajusta por tramos y la juzga sobre datos que nunca vio."],

  "wf.m_efficiency": ["Efficiency", "Eficiencia"],
  "wf.m_efficiency_help": [
    "How much of the in-sample performance survived outside it. 1.0 means it survived whole; 0.5 is normal and healthy; near 0 means the strategy was describing the past.",
    "Cuánto del rendimiento sobrevivió afuera. 1.0 es que sobrevivió entero; 0.5 es lo normal y sano; cerca de 0 es que la estrategia describía el pasado."],
  "wf.m_consistency": ["Winning stretches", "Tramos ganadores"],
  "wf.m_oos_return": ["Return out of sample", "Retorno fuera de muestra"],
  "wf.m_bad_run": ["Worst plausible drawdown", "Peor caída plausible"],
  "wf.m_bad_run_help": [
    "From Monte Carlo: the same trades dealt in a different order a thousand times. The total profit comes out identical every time — what changes is the path, so this is how deep the hole could have been before it paid off.",
    "De Monte Carlo: las mismas operaciones repartidas en otro orden mil veces. La ganancia total sale idéntica siempre — lo que cambia es el camino, así que esto es qué tan hondo pudo haber sido el pozo antes de que empezara a pagar."],
  "wf.tested_on": [
    "Tested over {desde} → {hasta}, on {cuando}.",
    "Probada sobre {desde} → {hasta}, el {cuando}."],
  "wf.ruin_warn": [
    "In <b>{pct}%</b> of the reshuffles the account lost a third of its capital before recovering. That is a real account somebody closes.",
    "En el <b>{pct}%</b> de los repartos la cuenta perdió un tercio del capital antes de recuperarse. Eso es una cuenta real que alguien cierra."],

  "saved.pending": [
    "{n} of these have not been tested yet.",
    "{n} de éstas todavía no se probaron."],

  "pf.pick_one": ["Include {nombre} in the portfolio", "Incluir {nombre} en el portafolio"],
  "pf.building": ["Combining the curves", "Combinando las curvas"],
  "ui.go_bank": ["See what the search found", "Ver lo que encontró la búsqueda"],

  /* ------------------------------------------------------------- bienvenida */
  "wel.title": ["Three steps", "Tres pasos"],
  /* NO NOMBRA A METATRADER, y eso importa: se lee ANTES de elegir mundo, y
     prometer un destino que el usuario todavía no eligió deja a quien viene
     por cripto pensando que se equivocó de programa. */
  "wel.sub": [
    "Botiquant searches for trading strategies on your own data, you keep the ones worth keeping, and you take them to where you trade. Everything runs on this machine.",
    "Botiquant busca estrategias sobre tus propios datos, vos te quedás con las que valgan la pena, y te las llevás a donde operes. Todo corre en esta máquina."],
  "wel.s1": ["Search", "Buscar"],
  "wel.s1_sub": [
    "Pick a market and how many strategies you want. The search does not stop until it has them.",
    "Elegís un mercado y cuántas estrategias querés. La búsqueda no se detiene hasta tenerlas."],
  "wel.s2": ["Keep", "Guardar"],
  "wel.s2_sub": [
    "Look at what it found and save the ones worth a second look. The rest you can throw away without thinking twice.",
    "Mirás lo que encontró y guardás las que merezcan una segunda mirada. El resto se tira sin pensarlo."],
  "wel.s3": ["Take it away", "Llevarla"],
  /* Los DOS destinos, porque este texto se lee antes de elegir. Decir sólo
     MetaTrader deja a quien viene por cripto pensando que se equivocó. */
  "wel.s3_sub": [
    "On CFDs it exports as a robot for MetaTrader 5; on crypto it connects straight to the exchange. Either way, run it on a demo account before putting real money on it.",
    "En CFDs se exporta como robot para MetaTrader 5; en cripto se conecta directo al exchange. En los dos casos, correla en una cuenta demo antes de ponerle plata."],
  /* La bienvenida ya no es "empezar" sino ELEGIR QUE SE OPERA: son dos
     productos distintos y el que elige mal mina sobre datos que no va a poder
     operar. `wel.start` queda para no romper una traducción a medio camino. */
  "wel.elegir": ["Start here", "Empezar por acá"],
  "wel.cambiar": [
    "You can switch at any time from the top left. Nothing you save is lost.",
    "Podés cambiar cuando quieras desde arriba a la izquierda. No se pierde nada de lo guardado."],
  "wel.start": ["Start searching", "Empezar a buscar"],
  "wel.again": [
    "You will not see this again. Everything is in the menu on the left.",
    "Esto no vuelve a aparecer. Todo está en el menú de la izquierda."],

  "session.no_limit": ["no restriction", "sin restricción"],
  "session.exported": [
    "The exported robot carries this window. If your broker's server is not on UTC, set InpServerUTCOffset to the hours it runs ahead.",
    "El robot exportado lleva esta franja. Si el servidor de tu bróker no está en UTC, poné en InpServerUTCOffset las horas que adelanta."],

  /* --------------------------------------------------- comprar y mantener */

  /* ------------------------------------------------------------ walk-forward */
  "wf.title": ["Walk-forward", "Walk-forward"],
  "wf.sub": ["Does the edge survive outside the data it was found on?",
             "¿La ventaja sobrevive fuera de los datos donde se la encontró?"],
  "wf.explain": [
    "The hardest test there is. The history gets cut into consecutive stretches; the strategy is re-tuned on each one and then judged on the stretch that comes next, which it has never seen. A strategy that only described the past falls apart here — and that is the point.",
    "La prueba más dura que hay. El histórico se corta en tramos consecutivos; la estrategia se reajusta en cada uno y después se la juzga sobre el tramo siguiente, que nunca vio. Una estrategia que sólo describía el pasado se cae acá — y de eso se trata."],
  "wf.run": ["Run walk-forward", "Correr walk-forward"],
  "wf.running": ["Testing…", "Probando…"],
  "wf.folds": ["Stretches", "Tramos"],
  "wf.folds_help": [
    "How many times to repeat the tune-then-test cycle. More stretches is a harder test and takes longer.",
    "Cuántas veces repetir el ciclo de ajustar y probar. Más tramos es una prueba más dura y tarda más."],
  "wf.train": ["Share used for tuning", "Parte usada para ajustar"],
  "wf.train_help": [
    "How much of each stretch goes into tuning the strategy. The rest is what it gets judged on.",
    "Cuánto de cada tramo se usa para ajustar la estrategia. El resto es sobre lo que se la juzga."],
  "wf.efficiency": ["Walk-forward efficiency", "Eficiencia walk-forward"],
  "wf.efficiency_help": [
    "What fraction of the tuned performance survived on data the strategy had not seen. Above 0.5 is good; below 0.3 means the tuning was describing noise.",
    "Qué fracción del rendimiento ajustado sobrevivió sobre datos que la estrategia no había visto. Por encima de 0,5 está bien; por debajo de 0,3 el ajuste estaba describiendo ruido."],
  "wf.consistency": ["Profitable stretches", "Tramos en ganancia"],
  "wf.verdict.robust": ["Holds up", "Aguanta"],
  "wf.verdict.robust_sub": [
    "The edge survived on data the strategy had never seen, and it did so in most stretches. This is as good as backtesting evidence gets.",
    "La ventaja sobrevivió sobre datos que la estrategia nunca vio, y lo hizo en la mayoría de los tramos. Es lo mejor que puede dar la evidencia de un backtest."],
  "wf.verdict.acceptable": ["Partly holds up", "Aguanta a medias"],
  "wf.verdict.acceptable_sub": [
    "Some of the edge survived, but not in every stretch. Worth watching on a demo account before risking money.",
    "Algo de la ventaja sobrevivió, pero no en todos los tramos. Conviene mirarla en una cuenta demo antes de arriesgar plata."],
  "wf.verdict.overfitted": ["Does not hold up", "No aguanta"],
  "wf.verdict.overfitted_sub": [
    "It looked good on the data it was tuned on and fell apart on the next stretch. That is the signature of a strategy that memorised the past instead of finding something in it.",
    "Se veía bien sobre los datos con los que se la ajustó y se cayó en el tramo siguiente. Es la firma de una estrategia que memorizó el pasado en vez de encontrar algo en él."],
  "wf.fold": ["Stretch", "Tramo"],
  "wf.tuned_on": ["Tuned on", "Ajustada sobre"],
  "wf.judged_on": ["Judged on", "Juzgada sobre"],
  "wf.in_sample": ["While tuning", "Al ajustar"],
  "wf.out_sample": ["On unseen data", "Sobre datos nuevos"],
  "wf.stitched": ["Equity on unseen data only", "Capital sólo sobre datos nuevos"],
  "wf.pick": ["Which strategy to put through it", "Qué estrategia poner a prueba"],
  "wf.pick_one": ["Pick one strategy above to test.",
                  "Elegí arriba una estrategia para probar."],
  "wf.nothing": ["Nothing to test yet", "Todavía no hay nada que probar"],
  "wf.nothing_sub": [
    "Once a search finishes, its strategies show up here to be put through the hardest test the app has.",
    "Cuando termine una búsqueda, sus estrategias aparecen acá para pasarlas por la prueba más dura que tiene la aplicación."],
  "wf.by_fold": ["Stretch by stretch", "Tramo por tramo"],
  "wf.need_data": [
    "Not enough history for that many stretches. Use fewer stretches or a longer period.",
    "No hay suficiente histórico para tantos tramos. Usá menos tramos o un período más largo."],

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
  "pf.correlation_help": [
    "1.0 means the two curves move together exactly — holding both buys you nothing. Below 0.3 is a real diversification.",
    "1,0 significa que las dos curvas se mueven exactamente igual: tener las dos no aporta nada. Por debajo de 0,3 es una diversificación de verdad."],
  "pf.contribution": ["Share of the risk", "Parte del riesgo"],
  "pf.best_pair": ["Least alike pair", "El par menos parecido"],
  "pf.worst_pair": ["Most alike pair", "El par más parecido"],
  "pf.need_two": ["Pick at least two strategies to combine.",
                  "Elegí al menos dos estrategias para combinar."],
  "pf.pick": ["Which strategies to combine", "Qué estrategias combinar"],
  "pf.equal_weight": ["capital split evenly", "capital repartido en partes iguales"],
  "pf.corr_high": ["These are almost the same bet", "Éstas son casi la misma apuesta"],
  "pf.corr_mid": ["Partly independent", "Parcialmente independientes"],
  "pf.corr_low": ["Genuinely different bets", "Apuestas de verdad distintas"],
  "pf.corr_unknown": ["Not enough shared history to tell",
                      "No hay suficiente historia compartida para saberlo"],
  "pf.no_overlap_cell": ["No shared movement to compare", "Sin movimiento compartido que comparar"],
  "pf.no_overlap": [
    "<b>{lista}</b> did not trade between {desde} and {hasta}, which is the only window all of these share. Its numbers are not part of the combination — combine strategies found over similar periods, or this comparison says nothing.",
    "<b>{lista}</b> no operó entre {desde} y {hasta}, que es la única ventana que comparten todas. Sus números no entran en la combinación — combiná estrategias encontradas sobre períodos parecidos, o esta comparación no dice nada."],
  "pf.vs_best": [
    "The best single one, {nombre}, returned {parte}% a year with a {dd}% drawdown. Together they return {junto}% with a {ddjunto}% drawdown — combining is worth it when the drawdown falls by more than the return does.",
    "La mejor sola, {nombre}, rindió {parte}% anual con una caída del {dd}%. Juntas rinden {junto}% con una caída del {ddjunto}% — combinar conviene cuando la caída baja más de lo que baja el rendimiento."],

  /* ------------------------------------------------------ comparar dos a dos */
  "cmp.title": ["Side by side", "Una al lado de la otra"],
  "cmp.sub": ["Two strategies, the same axes", "Dos estrategias, los mismos ejes"],
  "cmp.pick_two": ["Select exactly two strategies to compare.",
                   "Seleccioná exactamente dos estrategias para comparar."],
  "cmp.better": ["better", "mejor"],
  "cmp.tie": ["tied", "empate"],

  /* --------------------------------------------------- prueba en otro mercado */

  /* ------------------------------------------------------------------ notas */
  "note.title": ["Why you kept it", "Por qué la guardaste"],
  "note.placeholder": [
    "In two weeks you will have twenty of these and you will not remember which one you liked.",
    "En dos semanas vas a tener veinte de éstas y no vas a acordarte cuál te había gustado."],
  "note.save": ["Save note", "Guardar nota"],
  "note.saved": ["Note saved", "Nota guardada"],
  "note.empty": ["No note yet", "Sin nota todavía"],

  /* ---------------------------------------------------------------- gráficos */
  "chart.drawdown_from_peak": ["DRAWDOWN FROM PEAK", "CAÍDA DESDE MÁXIMO"],
  "chart.below_peak": ["{pct}% below peak", "{pct}% bajo el máximo"],
  //: doce abreviaturas separadas por coma; el orden es enero → diciembre
  "chart.months": ["Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec",
                   "Ene,Feb,Mar,Abr,May,Jun,Jul,Ago,Sep,Oct,Nov,Dic"],

  /* ------------------------------------------------------------- genéricos */
  "ui.cancel": ["Cancel", "Cancelar"],
  "ui.close": ["Close", "Cerrar"],
  "ui.back": ["Back", "Volver"],
  "ui.save": ["Save", "Guardar"],
  "ui.delete": ["Delete", "Borrar"],
  "ui.select_all": ["Select all", "Seleccionar todas"],
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
  "ui.go_mining": ["Go to Mining", "Ir a Minado"],
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
