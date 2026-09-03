# Auditoría para el rediseño de la interfaz (3 de septiembre de 2026)

Documento de trabajo, temporal. Compara cada elemento de las imágenes de
referencia con lo que el repositorio realmente implementa. Regla: el código es
la fuente de verdad de la funcionalidad; las imágenes, de la dirección visual.

Clases: **A** existe y se muestra directo · **B** existe, la pantalla lo
representa distinto · **C** existe en parte, se muestra sólo lo que hay ·
**D** no existe; no se construye en este rediseño.

## 1. Mapa del producto actual

**Arquitectura.** FastAPI en `botiquant/api/app.py` (una sola `create_app`,
~4.500 líneas, ~90 endpoints), SPA sin dependencias en `ui/` (`app.js` 10.200
líneas, `styles.css` 3.960, `i18n.js` 2.500 con pares EN/ES, `charts.js` 440
de SVG a mano), SQLite en `botiquant/database/db.py`, empaquetado PyInstaller.

**Dos mundos.** `S.mundo` ∈ {`metatrader`, `exchange`}; el conmutador vive en
la barra lateral (`#mundo-sw`). Cada sección ve sólo sus históricos
(`mundoDeDataset`, `_es_del_mundo`), sus recetas (`RECETAS()` filtra por
mundo), sus costos (spread/slippage/swap vs. comisión %/funding), sus
exportaciones (MQL5 sólo CFD; BingX/Pine y robots sólo cripto) y su
operación (robots Binance demo sólo en cripto; MetaTrader por EA en CFD).

**Páginas reales** (`data-page`): `mining` (Buscar), `saved` con vistas
`por_probar` / `aprobadas` / `descartadas` (Probar, Las que aguantaron,
Descartadas), `operar` con vistas `bot` / `tablero` / `resultados` / `claves` /
`piloto` (Operar, cuenta, claves, Automático avanzado), `data` (Mercados y
datos), `consejos`. Página de bienvenida al primer arranque. Landing pública en
`/`, app en `/app`. Barra lateral con pasos numerados 1→4 y bloque "Ajustes".

**Motores.**
- Minería: `botiquant/mining/miner.py` + `generator/` (candidatas al azar por
  bloques, backtest completo, filtros de vara). Un histórico y un timeframe
  por corrida. Recetas (5 objetivos) que configuran la búsqueda entera.
  Progreso por job (`/api/jobs/{id}`, pausa/parada). Corridas archivadas
  (`/api/corridas`, `/api/banco`).
- Genético (`genetic/evolution.py`, `/api/evolve`) y optimizador
  (`optimizer/optimizer.py`, `/api/optimize`, `/api/optimize/dimensions`):
  **existen en el backend y hoy la interfaz no los expone**.
- Backtest (`backtesting/`), `/api/backtest`: usado por las fichas.
- Validación: `/api/probar` = walk-forward (4 tramos, reoptimización por
  tramo, `analysis/walkforward.py`) + Monte Carlo (`analysis/montecarlo.py`,
  bootstrap de rendimientos compuestos, 1.000 sims) + puerta de ruina
  (p95 de caída ≥ 60 % ⇒ "ruina"). Veredicto: `robust` / `acceptable` /
  `overfitted` (+ `ruina`). `/api/walkforward`, `/api/montecarlo` y
  `/api/validar` existen sueltos pero la interfaz sólo usa `/api/probar`.
- `/api/robustez`: **es Monte Carlo sobre varias estrategias para
  compararlas**, no sensibilidad de parámetros.
- Portafolio: `portfolio/portfolio.py` → equity combinada, matriz de
  correlación de retornos diarios, drawdown, contribución de riesgo por
  estrategia, pesos, Sharpe, CAGR (`/api/portfolio`, usado en "Armar un
  conjunto"). Plan de conjunto para robots (`/api/bot/plan-conjunto`).
- Operación en vivo (`vivo/`): robots sobre Binance **demo** (el adaptador no
  acepta base real; `claves` rechaza claves reales), semáforo, vigilante,
  tope diario, porción de cuenta, pánico. Cuenta: saldo, posiciones, cerradas,
  P&L (`/api/cuenta/rendimiento`).
- Ciclo automático (`ciclo.py`, `orquestador.py`): minar cada N horas,
  candidatas por vuelta, instrumentos, reservar %, validar por vuelta (hoy
  no valida solo: el usuario manda a Probar), máx. en práctica, máx. por
  instrumento, promover hasta, retirar sólo, vueltas en naranja. Registro de
  vueltas.
- Informes: por resultado `report.html`, `report.xlsx`, `trades.csv`,
  `metrics.csv`; exportaciones MQL5, BingX (objeto y archivo), Pine,
  portafolio; enlaces compartidos (`/api/compartir`, `/s/{codigo}`), registro
  de enlaces propios.
- Datos: CSV genérico, MetaTrader, TradingView, Binance klines, descarga de
  catálogo, resampleo, funding en archivo hermano, mundo por origen
  (`upload@exchange`).
- Auth y licencia: Google OAuth sólo con `BQ_MULTIUSER=1` (`auth/`);
  licencia local firmada (`licencia/`, `/api/licencia*`).
- Tema: ya hay claro y oscuro con tokens (`:root` oscuro por defecto,
  `:root[data-theme="light"]`), persistido en `localStorage["qf.theme"]`, con
  acento verde azulado `#0B6E72` en claro. Gráficos leen colores del CSS.
- Estados de estrategia (`estados.py`): `nueva → validada → practica →
  produccion`, más `retirada`; y el veredicto de la prueba: `sin_probar`,
  `aprobada`, `aceptable`, `no_paso`.

**Métricas reales por estrategia** (`meta.metrics`): net_profit_pct, cagr_pct,
cagr_exposed_pct, max_drawdown_pct, profit_factor, sharpe, win_rate_pct,
trades, trades_per_month/week, expectancy_r, avg_win/avg_loss/avg_trade,
exposure_pct, recovery_factor, months_positive_pct, worst_month_pct,
top_trade_share_pct, years; más `score`, `fitness`, `oos`, `oos_ratio`,
`spark` (mini-equity) en el banco; y `validacion` (tramos, tramos_ganadores,
eficiencia, consistencia_pct, retorno_fuera_pct, veredicto, mc.dd_malo_pct,
mc.ruina_pct, detalle.tramos, bandas de MC).

## 2. Matriz de compatibilidad por pantalla de referencia

### Dashboard
| Elemento | Clase | Con qué se hace |
|---|---|---|
| Contadores por estado (minadas, en test, validadas, en portafolio, descartadas) | B | `/api/estrategias/resumen` + `/api/strategies` (veredictos) + `/api/corridas` (construidas/descartadas) |
| "+10,6 % vs. período anterior" | D | no hay historial de contadores |
| Evolución del capital "todas las estrategias" | B | curva de la cuenta demo (`/api/cuenta/rendimiento`, cerradas) o equity combinada de `/api/portfolio` sobre las que operan |
| Distribución por estado (dona) | A | los mismos contadores |
| Actividad reciente | C | registro del ciclo (`/api/ciclo.registro`), fechas de corridas y de pruebas (`validacion.probada`); no hay bitácora general |
| Top estrategias por retorno | A | `/api/strategies` ordenadas por `net_profit_pct` |
| Selector de rango de fechas del dashboard | D | los contadores no tienen fecha |

### Minería
| Elemento | Clase | Con qué se hace |
|---|---|---|
| Pasos ordenados (activo → timeframe → configuración → riesgo → datos → criterios → buscar → resultados) | B | ya existe como Mercado → Receta → Ajustar (bloques, riesgo, costos, filtros) → cuántas → Empezar; se reorganiza en pasos visibles |
| Varios activos y varios timeframes en una corrida | D | una corrida = un histórico + un timeframe. El ciclo automático sí rota instrumentos |
| Reglas / Indicadores / Parámetros como pasos editables | C | los bloques se eligen (Ajustar); indicadores y rangos los decide el generador. Se muestra lo elegible, no rangos por parámetro |
| Combinaciones estimadas, tiempo estimado, hilos, CPU/RAM/disco | D | no se calcula |
| Barra de progreso, construidas/descartadas, pausar, tiempo transcurrido | A | job de minería |
| Plantillas / cargar configuración | B | las recetas son las plantillas; no hay configuraciones guardadas por el usuario |
| Capital, spread/comisión, apalancamiento | A/C | capital, costos por mundo y riesgo existen; "apalancamiento 1:100" no existe como parámetro (CFD dimensiona por lotes/riesgo %) |

### Estrategias (banco)
| Elemento | Clase | Con qué se hace |
|---|---|---|
| Tabla densa: ID, nombre, activo, TF, retorno, DD, PF, Sharpe, win rate, trades, score, estado | A | banco y guardadas |
| CAGR, expectancy, exposición, meses positivos, peor mes | A | `meta.metrics` (columnas opcionales) |
| KPIs arriba (total, rentables, en test, en portafolio, descartadas) | B | estados reales |
| Estrella / favoritas | D | no hay marca; hay notas por estrategia |
| Buscar, filtros por activo/TF/estado, columnas, orden | A/B | existen filtros y orden; "columnas" se agrega en la vista |
| Selección múltiple: enviar a Test, a Portafolio/Trade, descartar, comparar | A/B/C | mandar a Probar y borrar existen; "a Portafolio" = armar conjunto / Operar; comparar = `/api/robustez` (backend sin UI, ver §4) |
| Inspector lateral: equity, distribución ganadoras/perdedoras, resumen, notas | A/B | `spark`, backtest bajo demanda, win_rate × trades, notas |
| Importar estrategia | C | `POST /api/strategies` acepta un spec; no hay importador de archivos |
| Gráficos inferiores (activos, por timeframe, distribución de scores, estados) | A | se calculan en el cliente sobre las filas reales del mundo |
| Paginación "1 … 210" | B | hoy la lista es completa con filtro; se pagina en el cliente si hace falta |

### Test — Hub de validación
| Elemento | Clase | Con qué se hace |
|---|---|---|
| Cola: en cola, en ejecución, completadas, fallidas | A | `COLA_PRUEBAS`, veredictos (ahora con reanudación tras recarga) |
| Cinco tests con score 0-100 cada uno y radar | D | hay dos motores (walk-forward, Monte Carlo) y una puerta de ruina. No hay score unificado ni test de "distribución", "sobrecarga" ni "robustez de parámetros" |
| Métodos de prueba (tarjetas) | B | dos tarjetas reales: Walk Forward y Monte Carlo; "sobreajuste" es el veredicto del walk-forward, no un test aparte |
| Tasa de éxito, tiempo promedio | C | tasa = aprobadas / probadas; no se mide duración |
| Historial de pruebas | C | se conserva sólo la última prueba por estrategia |
| Repetir test, ver resultados | A | volver a probar, ficha |

### Test — Robustez (sensibilidad de parámetros)
| Elemento | Clase |
|---|---|
| Score de robustez 78/100, entropía, estabilidad, R² | D |
| Heatmap PF por SL/TP, superficie 3D, sensibilidad por parámetro, ranking de variaciones | D en este rediseño. Nota: `/api/optimize` (búsqueda de parámetros) podría alimentar algo así más adelante; hoy no tiene interfaz ni se pide construirla |
| "Comparar con Monte Carlo" | B | `/api/robustez` compara varias estrategias por Monte Carlo |

Se sustituye por **Comparar** (Monte Carlo de varias estrategias lado a lado)
usando `/api/robustez`, que ya existe, o se omite la pantalla.

### Test — Monte Carlo
| Elemento | Clase | Con qué se hace |
|---|---|---|
| Abanico de equity simulada vs. original | A | `bands` + equity original |
| Distribución de retornos finales (histograma, media, prob. de pérdida, IC 90/50) | A | `final_equity.histogram`, `mean`, `median`, `ci_90`, `ci_50`, `prob_loss` |
| Distribución de drawdown (mediana, p95, peor) | A | `max_drawdown_pct` |
| Riesgo de ruina, umbral | A | `ruina_pct`, umbral 30 % / puerta 60 % |
| Simulaciones, retorno medio, VaR 95 % | A/C | sims y media existen; "VaR" se muestra como el percentil 5 del retorno final, con ese nombre |

### Test — Walk Forward
| Elemento | Clase | Con qué se hace |
|---|---|---|
| Equity con ventanas IS/OOS sombreadas | A | `folds` con train/test fechas y `oos_equity` |
| Ventanas, retorno IS/OOS promedio, eficiencia, consistencia | A | `summary` |
| Score WF 75/100 | D | se muestra el veredicto real (robust / acceptable / overfitted / ruina) |
| Degradación | B | 1 − eficiencia, con su nombre real |
| Mejor/peor ventana | A | por tramo |

### Portfolio / Trade
| Elemento | Clase | Con qué se hace |
|---|---|---|
| Robots activos, capital asignado, P&L, ejecución demo, encender/apagar | A | `/api/bot` (vuelos con porción, riesgo, semáforo, tope), `/api/cuenta/rendimiento` |
| Conmutador Demo / Real | B | real está bloqueado por diseño: se muestra "Demo" y "Real" deshabilitado con el motivo |
| Equity combinada, correlación, contribución de riesgo, drawdown | A | `/api/portfolio` (hoy en "Armar un conjunto") |
| Capital asignado en dinero por estrategia | B | porción % de la cuenta × saldo |
| Agregar estrategia al portafolio | A | Encender (cripto) / plan de conjunto |
| Vista CFD | B | en MetaTrader no hay robots: se muestra exportación EA y estado de la terminal (`/api/metatrader`) |

### Cripto
Es el mundo `exchange`, no una página. Se mantiene el conmutador de mundo,
más visible y con rótulo permanente de contexto en cada pantalla.

### Reportes
| Elemento | Clase | Con qué se hace |
|---|---|---|
| Informe HTML, Excel, CSV por resultado | A | `/api/results/{rid}/…` |
| Enlaces compartidos, exportaciones (MQL5, BingX, Pine, portafolio) | A | existentes |
| Rendimiento agregado del portafolio con rango de fechas | C | `/api/cuenta/rendimiento` (demo) y `/api/portfolio`; sin selector de fechas arbitrario |
| Exportar PDF | B | imprimir el HTML desde el navegador |

### Configuración
Existente: Mercados y datos, Cuenta y claves de exchange (demo), carpeta de
MetaTrader, Automático avanzado (ciclo), idioma, tema, licencia, enlaces
propios. "Recursos del sistema" (CPU/RAM/disco): **D**.

### Barra lateral
Usuario y plan: **B** — nombre de cuenta sólo en multiusuario (Google);
en escritorio, estado de licencia. "Ayuda" = Consejos + soporte.

## 3. Arquitectura de información propuesta (sin tocar la lógica)

Barra lateral oscura (también en claro), en este orden:

1. **Inicio** (nuevo, sólo composición de datos existentes)
2. **Minería** (`mining`)
3. **Estrategias** (`saved` — banco de corridas + guardadas, con filtros por estado)
4. **Test** (`saved/por_probar` + `aprobadas` + `descartadas` como solapas; la cola en cabecera)
5. **Portafolio / Trade** (`operar/bot` + `tablero` + `resultados`; conjunto y correlación de `/api/portfolio`)
6. **Reportes** (resultados, exportaciones, enlaces)
7. **Datos** (`data`)
8. **Configuración** (claves, MetaTrader, Automático avanzado, idioma, tema, licencia)

Arriba de todo, el conmutador de mundo (MetaTrader / Cripto) con rótulo
permanente; cada página muestra el mundo activo en la cabecera (context pill).

## 4. Posibles mejoras futuras — NO implementadas
- Sensibilidad de parámetros (heatmap, superficie, ranking) sobre `/api/optimize`.
- Interfaz para el genético (`/api/evolve`) y el optimizador.
- Historial de pruebas por estrategia (hoy sólo la última).
- Favoritas.
- Corridas multi-activo / multi-timeframe.
- Historial de contadores (variaciones "vs. período anterior").
- Estimación de tiempo y combinaciones de minería.
- Score unificado de robustez.

## 5. Plan de implementación
Fase 3: tokens y tema — claro por defecto, oscuro preservado (`ui/styles.css`,
`ui/index.html`, `applyTheme` en `ui/app.js`).
Fase 4: barra lateral y cabeceras (`ui/index.html`, `nav` en `app.js`,
`i18n.js`).
Fase 5: componentes compartidos (KPI, tabla densa, badges, pestañas,
inspector, estado vacío) en `styles.css` + helpers en `app.js`.
Fases 6-15: una pantalla por vez, siempre sobre los endpoints de arriba.
Fase 16: QA visual a 1440×900 contra las imágenes, y la suite completa.
