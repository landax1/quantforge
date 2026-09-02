"""Continuous random strategy mining with a live databank.

The SQX-style experience: sample random genomes (structure AND gene values),
backtest each one, and keep a ranked databank that the UI renders while the
search runs. The seed defaults to a fresh random value on every run — shown
and returned so any run can be reproduced exactly — instead of a fixed seed
that would make every run return identical results.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

import numpy as np
import pandas as pd

from botiquant.backtesting.engine import run_backtest
from botiquant.backtesting.metrics import fitness, bq_score, score_breakdown
from botiquant.core import sesiones
from botiquant.core.jobs import JobHandle
from botiquant.core.models import BacktestSettings, RiskConfig
from botiquant.genetic.evolution import _crossover, _mutate
from botiquant.generator.generator import Genome, build_spec, random_genome
from botiquant.generator.templates import TEMPLATES
from botiquant.indicators.base import IndicatorCache

_ROW_METRICS = ("net_profit_pct", "cagr_pct", "profit_factor", "max_drawdown_pct",
                "win_rate_pct", "sharpe", "trades", "expectancy_r",
                "exposure_pct", "cagr_exposed_pct", "years",
                "avg_win", "avg_loss", "avg_trade",
                "months_positive_pct", "months_total", "worst_month_pct",
                "top_trade_share_pct",
                # los dos que se pueden exigir como filtro tienen que viajar en
                # la fila: si no, el databank no puede mostrar ni ordenar por
                # aquello mismo que se le pidió a la búsqueda
                "recovery_factor", "trades_per_month", "trades_per_week")

# after this many consecutive duplicate genomes the space is considered mined out
_EXHAUSTED_AFTER = 300


def _gene_summary(genome: Genome) -> str:
    parts = []
    for t_id in (genome.driver, *genome.filters):
        vals = genome.genes.get(t_id) or {}
        if vals:
            parts.append(",".join(f"{k}={v:g}" for k, v in sorted(vals.items())))
    if genome.stop_mult is not None:
        parts.append(f"SL={genome.stop_mult:g}×ATR")
    if genome.trail_mult:
        parts.append(f"trail={genome.trail_mult:g}×ATR")
    if genome.max_bars:
        parts.append(f"máx {genome.max_bars} velas")
    if genome.session and genome.session != sesiones.SIN_RESTRICCION:
        horas = sesiones.horario(genome.session)
        parts.append(sesiones.etiqueta(genome.session) + (f" ({horas})" if horas else ""))
    return " · ".join(parts)


#: points kept for the inline equity sparkline shown on each databank row
_SPARK_POINTS = 48


def _spark(equity: np.ndarray) -> list[float]:
    """Heavily downsampled equity curve — enough to read its shape at a glance."""
    n = len(equity)
    if n == 0:
        return []
    idx = np.linspace(0, n - 1, min(n, _SPARK_POINTS)).astype(int)
    return [round(float(equity[i]), 2) for i in idx]


def _row(genome: Genome, spec, m: dict[str, float], score: float,
         serial: int, equity: np.ndarray | None = None) -> dict[str, Any]:
    return {
        "id": genome.key(),
        "name": f"S-{serial:03d}",
        "blocks": spec.name,
        "genes_label": _gene_summary(genome),
        "spark": _spark(equity) if equity is not None else [],
        "driver": genome.driver,
        "filters": list(genome.filters),
        "genes": genome.genes,
        "stop_mult": genome.stop_mult,
        "trail_mult": genome.trail_mult,
        "max_bars": genome.max_bars,
        # El R:B viaja en la fila desde que dejo de ser configuracion fija. Sin
        # esto, dos estrategias que solo se diferencian en la relacion se ven
        # IDENTICAS en el databank — y es el gen que mas les cambia el caracter:
        # a 0,5 el win rate mediano es 59,5% y a 2,0 es 39,8%.
        "rr_mult": genome.rr_mult,
        # la franja viaja como id y como etiquetas: el banco tiene que poder
        # mostrar y ordenar por horario sin volver a consultar el catálogo
        "session": genome.session,
        "session_label": sesiones.etiqueta(genome.session),
        "session_label_en": sesiones.etiqueta(genome.session, "en"),
        "session_hours": sesiones.horario(genome.session),
        "metrics": {k: m[k] for k in _ROW_METRICS},
        "fitness": round(float(score), 4),
        # el score y su desglose viajan siempre, aunque se esté ordenando por
        # otro criterio: es lo que el usuario mira para decidir
        "score": bq_score(m),
        "score_parts": {k: round(v, 3) for k, v in score_breakdown(m).items()},
        "spec": spec.to_dict(),
    }


#: acceptance criterion -> (metric, comparison, human label)
_CRITERIA: tuple[tuple[str, str, str, str], ...] = (
    ("min_pf", "profit_factor", "min", "profit factor"),
    ("min_win_rate_pct", "win_rate_pct", "min", "win rate"),
    ("min_sharpe", "sharpe", "min", "Sharpe"),
    ("max_dd_pct", "max_drawdown_pct", "max", "drawdown máximo"),
    # Retorno sobre drawdown: ganancia neta dividida por la peor caída. Es el
    # filtro de calidad que más se usa en esta clase de herramienta, porque
    # junta las dos mitades de la pregunta —cuánto ganó y cuánto hubo que
    # aguantar para ganarlo— en un solo número que no depende del riesgo por
    # operación: subir el riesgo agranda las dos partes por igual.
    ("min_ret_dd", "recovery_factor", "min", "retorno / drawdown"),
    ("min_trades_month", "trades_per_month", "min", "operaciones por mes"),
    # Por semana además de por mes: quien está pasando un desafío de fondeo
    # tiene fecha de vencimiento y necesita saber que va a operar seguido, no
    # que el promedio mensual cierre.
    ("min_trades_week", "trades_per_week", "min", "operaciones por semana"),
    ("min_cagr_pct", "cagr_pct", "min", "retorno anual"),
    ("min_exposure_pct", "exposure_pct", "min", "tiempo en mercado"),
    # Sigue aceptándose para no romper las corridas ya archivadas, pero la
    # pantalla no lo ofrece: el total depende de cuántos años tenga el
    # histórico, así que el mismo número exige cosas distintas según el
    # instrumento. Lo que se quiere pedir ahí es el retorno anual.
    ("min_net_pct", "net_profit_pct", "min", "ganancia total"),
)

_CRIT_BY_KEY = {k: (metric, kind, label) for k, metric, kind, label in _CRITERIA}


def _failed_criteria(m: dict[str, float], accept: dict[str, float | None]) -> list[str]:
    """Which acceptance criteria this candidate misses (empty = accepted)."""
    missed = []
    for key, metric, kind, _label in _CRITERIA:
        limit = accept.get(key)
        if limit is None:
            continue
        if kind == "min" and m[metric] < limit:
            missed.append(key)
        elif kind == "max" and m[metric] > limit:
            missed.append(key)
    return missed


def _failed_criteria_oos(oos: dict[str, Any],
                         accept: dict[str, float | None]) -> list[str]:
    """Las mismas varas, contra el tramo reservado.

    El tramo reservado NO trae todas las métricas del de búsqueda —no tiene
    Sharpe ni operaciones por mes, por ejemplo—. Las que faltan se saltean en
    vez de darlas por reprobadas: reprobar por un dato que no existe rechazaría
    todo y el usuario vería cero resultados sin ningún motivo a la vista.
    """
    missed = []
    for key, metric, kind, _label in _CRITERIA:
        limit = accept.get(key)
        if limit is None or metric not in oos:
            continue
        v = oos[metric]
        if v is None:
            continue
        if kind == "min" and v < limit:
            missed.append(key)
        elif kind == "max" and v > limit:
            missed.append(key)
    return missed


def _passes(m: dict[str, float], accept: dict[str, float | None]) -> bool:
    """Databank acceptance: None disables an individual criterion."""
    return not _failed_criteria(m, accept)


def mine(
    df: pd.DataFrame,
    drivers: list[str],
    filters: list[str],
    *,
    max_filters: int = 2,
    direction: str = "both",
    risk: RiskConfig | None = None,
    settings: BacktestSettings | None = None,
    fitness_mode: str = "composite",
    min_trades: int = 30,
    accept: dict[str, float | None] | None = None,
    max_candidates: int = 2000,
    target_keep: int | None = None,
    keep_top: int = 100,
    seed: int | None = None,
    method: str = "random",
    #: Buscar sólo estrategias que el bot pueda ENCENDER.
    #:
    #: El bot se niega a operar una con stop dinámico —el motor lo mueve cada
    #: vela y el bot deja una orden fija en el exchange, así que operaría algo
    #: distinto de lo que se midió— y ese rechazo está bien. Lo que está mal es
    #: encontrarla, guardarla y descubrirlo al apretar encender.
    #:
    #: PASO DE VERDAD: la estrategia más frecuente de una corrida entera
    #: resultó tener trailing y no se pudo usar. Con esto, quien mina para
    #: operar busca directamente entre las que va a poder encender.
    sin_trailing: bool = False,
    population: int = 40,
    oos_pct: float = 0.0,
    #: Si los filtros de aceptación tienen que cumplirse TAMBIEN en el tramo
    #: reservado, y no sólo en el de búsqueda.
    #:
    #: "También" y no "en vez de": el tramo reservado sólo se corre para las
    #: que ya pasaron adentro, así que exigirlo afuera es una segunda puerta,
    #: no otra puerta.
    #:
    #: SIN ESTO, EL FUERA DE MUESTRA REORDENA PERO NO RECHAZA. Una estrategia
    #: que se derrumba afuera entra igual al databank, sólo que con el score
    #: castigado — y el usuario que mira los primeros puestos no se entera de
    #: que las de abajo no sobrevivieron.
    #:
    #: No cuesta tiempo: ese backtest ya se corre para cada aceptada.
    exigir_oos: bool = False,
    sessions: list[str] | None = None,
    #: Los R:B entre los que puede elegir cada candidata. Vacío o None deja el
    #: comportamiento de siempre: todas usan el configurado. Con una lista, la
    #: relación pasa a ser un gen más — que es lo único que permite encontrar
    #: familias de win rate alto, imposibles con un 1:2 fijo.
    rr_choices: list[float] | None = None,
    handle: JobHandle | None = None,
) -> dict[str, Any]:
    """Mining loop over the strategy space.

    ``method="random"`` samples genomes independently — broad, unbiased, and
    the honest baseline. ``method="evolution"`` keeps a population and breeds
    the best performers each generation, which converges on strong regions of
    the space much faster but explores less widely.

    Two ways to say when to stop. With ``target_keep`` the search runs until
    that many strategies have been ACCEPTED into the databank — the natural
    request ("quiero 50 que cumplan"), since how many candidates that takes is
    unknowable up front. ``max_candidates`` then acts purely as a safety cap so
    an impossible set of criteria cannot search forever. Without
    ``target_keep`` the old behaviour stands: test exactly ``max_candidates``.
    """
    if not drivers:
        raise ValueError("At least one driver template is required")
    # Con una sola franja, todas las candidatas operan ahí y el horario deja de
    # ser un gen. Con varias, la búsqueda lo elige por candidata — que es más
    # potente y también más fácil de sobreajustar: cuantas más franjas se
    # habiliten, más probable es que alguna se vea bien por casualidad.
    sessions = sesiones.normalizar(sessions)

    # ---------------------------------------------------------- in / out of sample
    # Con oos_pct > 0 la búsqueda sólo ve el tramo inicial y el final queda
    # reservado. Cada candidata aceptada se vuelve a correr ahí, sobre datos que
    # no participaron de la selección. Es la única medida del databank que no
    # está contaminada por haber elegido la estrategia mirando esos mismos datos:
    # buscar sobre 51 millones de combinaciones siempre encuentra algo que se ve
    # bien en el pasado, y esta columna es la que lo delata.
    df_full = df
    df_oos = None
    if oos_pct and 0.0 < oos_pct < 90.0:
        cut = int(len(df) * (1.0 - oos_pct / 100.0))
        if cut > 200 and len(df) - cut > 200:
            df, df_oos = df_full.iloc[:cut], df_full.iloc[cut:]
    if target_keep is not None:
        target_keep = max(int(target_keep), 1)
        # the bank must be able to hold the goal, otherwise trimming to
        # keep_top would silently cap the search below what was asked for
        keep_top = max(keep_top, target_keep)
    if seed is None:
        seed = secrets.randbelow(2**31)
    rng = np.random.default_rng(seed)
    cache = IndicatorCache(df)
    # una sola caché para el tramo reservado: se reutiliza en cada validación
    cache_oos = IndicatorCache(df_oos) if df_oos is not None else None
    settings = settings or BacktestSettings()

    accept = accept or {}
    # UN FILTRO MAL ESCRITO NO PUEDE PASAR DESAPERCIBIDO.
    #
    # Las claves se leen con `accept.get(...)`, así que una que no exista
    # devuelve None y el criterio simplemente no se aplica: se mina creyendo
    # que se filtra, el databank se llena de perdedoras y NADA lo dice. Pasó
    # de verdad —`min_profit_factor` en vez de `min_pf`— y el resultado fue un
    # databank con profit factors de 0,62 que parecía normal.
    #
    # La pantalla siempre manda claves válidas; esto protege a quien llame a
    # `mine` desde código, que es como corre el ciclo cuando no hay nadie
    # mirando.
    desconocidas = sorted(set(accept) - set(_CRIT_BY_KEY))
    if desconocidas:
        raise ValueError(
            f"Criterio de aceptación desconocido: {', '.join(desconocidas)}. "
            f"Los que existen son {', '.join(sorted(_CRIT_BY_KEY))}.")

    # UN BLOQUE DE FUNDING SOBRE UN HISTORICO SIN FUNDING NO MINA: MIENTE.
    #
    # `FundingPct` devuelve NaN cuando falta la columna, así que la condición
    # es falsa en todas las velas y la estrategia no opera nunca. Eso llegaría
    # al usuario como "no se encontró nada", que manda a aflojar los filtros —
    # cuando lo que pasa es que el instrumento no tiene el dato.
    #
    # SE DESCARTAN Y SE DICE CUALES, en vez de cortar o de ignorarlos callado.
    # Cortar sería lo natural, pero está mal: pedir "todos los bloques" es
    # legítimo y no debería fallar por incluir dos que este instrumento no
    # puede usar. Ignorarlos sin decirlo es peor todavía, que es el error que
    # este archivo persigue en todos lados.
    #
    # Un CFD no cobra funding, y eso no es un problema a resolver sino una
    # propiedad del instrumento que hay que informar.
    from botiquant.generator.templates import TEMPLATES as _TPL

    def _es_funding(t: str) -> bool:
        return getattr(_TPL.get(t), "category", "") == "funding"

    sin_funding: list[str] = []
    if "funding" not in getattr(df, "columns", ()):
        sin_funding = sorted(t for t in (*drivers, *filters) if _es_funding(t))
        if sin_funding:
            drivers = [t for t in drivers if not _es_funding(t)]
            filters = [t for t in filters if not _es_funding(t)]

    seen: set[str] = set()
    bank: list[dict[str, Any]] = []
    best_history: list[float] = []
    tested = 0
    passed = 0
    dupes = 0
    too_few_trades = 0
    blocked_by: dict[str, int] = {}
    # best value reached per criterion, so an empty databank can explain itself
    best_seen: dict[str, float] = {}
    # Candidatas que fallaron EXACTAMENTE un criterio, y cuál. Es el dato que
    # de verdad sirve: dice qué filtro aflojar para que entren estrategias.
    near_miss: dict[str, int] = {}
    # Mejor valor alcanzado ENTRE LAS QUE FALLARON cada criterio. `best_seen`
    # mira todas las candidatas, así que puede superar el límite pedido cuando
    # la que lo superaba cayó por otro filtro — y entonces el mensaje decía
    # "pediste 65 y lo mejor fue 70.67", que se lee como una contradicción.
    fail_best: dict[str, float] = {}
    t0 = time.time()
    #: segundos acumulados en pausa, que no son tiempo de búsqueda
    pausa_total = 0.0

    # drawdown of the highest-CAGR candidate, to project what raising the risk
    # per trade would cost — CAGR and drawdown both scale ~linearly with it
    top_cagr: dict[str, float] = {}

    def _validate_oos(spec) -> dict[str, Any]:
        """Corre la estrategia aceptada sobre el tramo reservado.

        ``oos_ratio`` es lo que hay que mirar: profit factor de afuera dividido
        el de adentro. Cerca de 1 significa que la ventaja se sostuvo; cerca de
        0 que la estrategia describía el pasado y nada más. Se calcula sobre el
        profit factor y no sobre la ganancia porque no depende de cuántos años
        tenga cada tramo.
        """
        res_oos = run_backtest(df_oos, spec, settings, cache=cache_oos, con_marcas=False)
        mo = res_oos.metrics
        pf_is = None
        return {
            "oos": {
                "profit_factor": mo["profit_factor"],
                "net_profit_pct": mo["net_profit_pct"],
                "cagr_pct": mo["cagr_pct"],
                "max_drawdown_pct": mo["max_drawdown_pct"],
                "win_rate_pct": mo["win_rate_pct"],
                "trades": mo["trades"],
            },
        }

    def _oos_ratio(row: dict[str, Any]) -> float | None:
        """Cuánto sobrevive la ventaja fuera de muestra, de 0 a 1+."""
        oos = row.get("oos")
        if not oos or not oos["trades"]:
            return None
        pf_in = max(row["metrics"]["profit_factor"], 1e-9)
        return round(min(oos["profit_factor"] / pf_in, 9.99), 3)

    def _ponderar_por_oos(row: dict[str, Any]) -> None:
        """Baja el score de lo que no sobrevivio al tramo reservado.

        Sin esto, el score que ordena el databank y elige el campeon mira solo
        el tramo con el que se busco. La mitad que de verdad dice algo estaba
        calculada y no pesaba: una estrategia que rendia adentro y se caia
        afuera quedaba arriba de otra que sostenia en las dos.

        Se castiga en proporcion a lo que sobrevivio y no se premia por encima
        de 1: que el tramo reservado haya salido MEJOR que el de busqueda es
        casi siempre ruido de un tramo corto, no una virtud.
        """
        q = row.get("oos_ratio")
        row["score_is"] = row["score"]
        if q is None:
            # sin operaciones afuera no hay nada que medir, y no medir no es
            # aprobar: se castiga como una supervivencia a medias
            row["score"] = round(row["score"] * 0.5, 1)
            row["oos_penal"] = 0.5
            return
        factor = min(float(q), 1.0)
        row["score"] = round(row["score"] * factor, 1)
        row["oos_penal"] = round(factor, 3)

    def _note_best(m: dict[str, float]) -> None:
        for key, metric, kind, _label in _CRITERIA:
            v = m[metric]
            cur = best_seen.get(key)
            if cur is None:
                best_seen[key] = v
            elif kind == "min":
                best_seen[key] = max(cur, v)
            else:
                best_seen[key] = min(cur, v)
        if not top_cagr or m["cagr_pct"] > top_cagr["cagr_pct"]:
            top_cagr.update({"cagr_pct": m["cagr_pct"],
                             "max_drawdown_pct": m["max_drawdown_pct"]})

    def _note_fail(key: str, m: dict[str, float]) -> None:
        """Lo más cerca que estuvo de este criterio algo que efectivamente falló."""
        metric, kind, _label = _CRIT_BY_KEY[key]
        v, cur = m[metric], fail_best.get(key)
        if cur is None:
            fail_best[key] = v
        else:
            fail_best[key] = max(cur, v) if kind == "min" else min(cur, v)

    def _transcurrido() -> float:
        """Segundos de búsqueda REAL, sin contar lo que estuvo en pausa.

        Sin descontarlo, un café de diez minutos con la búsqueda pausada se
        lee como diez minutos sin aceptar nada: el ritmo se desploma y el
        tiempo restante estimado se dispara a un número absurdo."""
        return time.time() - t0 - pausa_total

    def _esperar_pausa() -> None:
        nonlocal pausa_total
        if handle is None or not handle.paused:
            return
        desde = time.time()
        handle.esperar()
        pausa_total += time.time() - desde

    def _eta_s() -> float | None:
        """Seconds left to fill the databank at the acceptance rate so far."""
        if target_keep is None or not bank:
            return None
        missing = target_keep - len(bank)
        if missing <= 0:
            return 0.0
        elapsed = max(_transcurrido(), 1e-6)
        per_second = len(bank) / elapsed
        return round(missing / per_second, 1) if per_second > 0 else None

    def _fraction() -> float:
        """Progress means "how full is the databank" when a goal was set."""
        if target_keep is not None:
            return min(len(bank) / target_keep, 1.0)
        return min(tested / max_candidates, 1.0)

    def snapshot(final: bool = False) -> dict[str, Any]:
        return {
            "seed": seed,
            "tested": tested,
            "target": max_candidates,          # safety cap on candidates tested
            "target_keep": target_keep,        # goal: strategies in the databank
            "passed": passed,
            "rejected": tested - passed,
            "kept": len(bank),
            "accept": accept,
            # Los bloques de funding que se descartaron porque este histórico
            # no los tiene. Vacío en un perpetuo; con dos nombres en un CFD.
            "sin_funding": sin_funding,
            # Por qué se cae lo que se cae, en cuentas. Mientras el databank
            # está vacío es lo único que distingue una búsqueda trabajando de
            # una colgada, y dice qué filtro aflojar: un rechazo por pocas
            # operaciones se arregla distinto que uno por profit factor.
            #
            # Van por CLAVE y no por etiqueta: la interfaz existe en dos
            # idiomas y el nombre de cada criterio lo pone ella. Mandar el
            # texto ya armado obligaría al servidor a saber en qué idioma está
            # mirando cada quien, que es justo lo que no puede saber.
            "rechazos": {
                **({"min_trades": too_few_trades} if too_few_trades else {}),
                **{k: n for k, n in blocked_by.items() if n},
            },
            # el mínimo de operaciones se pasa aparte de `accept`, pero para
            # quien mira los resultados es un filtro más: sin él, la pantalla no
            # puede decir la vara completa que se aplicó
            "min_trades": min_trades,
            # las franjas horarias que se habilitaron: es parte de la vara con
            # la que se buscó, y sin ella una corrida archivada no se puede
            # repetir ni interpretar
            "sessions": list(sessions),
            "best_fitness": bank[0]["fitness"] if bank else 0.0,
            "elapsed_s": round(_transcurrido(), 1),
            "pausado_s": round(pausa_total, 1),
            "eta_s": _eta_s(),
            "best_history": best_history,
            "databank": bank if final else bank[:50],
            # El tramo EXACTO sobre el que se midieron las métricas del
            # databank. Va con hora y no recortado a la fecha: al reabrir una
            # estrategia guardada hay que reproducir el mismo backtest, y
            # redondear al día mueve el corte unas velas y con él los números.
            "measured_range": {"from": str(df.index[0]), "to": str(df.index[-1])},
            "split": None if df_oos is None else {
                "is_from": str(df.index[0])[:10], "is_to": str(df.index[-1])[:10],
                "oos_from": str(df_oos.index[0])[:10], "oos_to": str(df_oos.index[-1])[:10],
                "is_bars": len(df), "oos_bars": len(df_oos),
            },
            "diagnosis": _diagnose(),
        }

    def _diagnose() -> dict[str, Any]:
        """Why the databank is empty, in the user's terms."""
        if bank or tested == 0:
            return {}
        if too_few_trades == tested:
            # Una franja horaria estrecha es la primera sospechosa: recorta las
            # oportunidades disponibles en la misma proporción en que recorta
            # las horas, y quien la acaba de activar no relaciona una cosa con
            # la otra. Sin nombrarla, el consejo manda a bajar el mínimo de
            # operaciones, que es exactamente lo que no hay que hacer.
            estrechas = [s for s in sessions if s != sesiones.SIN_RESTRICCION]
            return {"reason": "trades", "tested": tested, "min_trades": min_trades,
                    # las franjas activas van con el diagnóstico para que la
                    # pantalla pueda nombrarlas en el idioma del usuario
                    "sessions": estrechas if len(estrechas) == len(sessions) else []}
        # LAS QUE FRENO EL TRAMO RESERVADO SE CUENTAN APARTE.
        #
        # Sus claves van con prefijo `oos:` y NO están en la tabla de criterios,
        # así que el camino de abajo las buscaba ahí y reventaba con KeyError —
        # justo cuando el usuario más necesita entender por qué no salió nada.
        #
        # Y merecen otro mensaje: no es que la vara sea muy exigente, es que
        # esas candidatas SI la cumplían con los datos de la búsqueda y se
        # cayeron donde no miraron. Decir "aflojá el filtro" ahí sería el
        # consejo exactamente al revés.
        frenadas_afuera = sum(v for k, v in blocked_by.items()
                              if k.startswith("oos:"))
        adentro = {k: v for k, v in blocked_by.items() if not k.startswith("oos:")}

        worst = max(adentro.items(), key=lambda kv: kv[1], default=None)
        if worst is None:
            if frenadas_afuera:
                return {
                    "reason": "oos",
                    "rejected": frenadas_afuera,
                    "tested": tested,
                    "text": (
                        f"<b>{frenadas_afuera}</b> "
                        f"{'candidata cumplía' if frenadas_afuera == 1 else 'candidatas cumplían'}"
                        f" todos los filtros con los datos de la búsqueda y NO "
                        f"los cumplieron en el tramo reservado. Eso es lo que ese "
                        f"tramo viene a mostrar: aflojar los filtros no lo "
                        f"arregla. Probá con otro instrumento, otra "
                        f"temporalidad, o desactivá la exigencia de afuera para "
                        f"ver qué encontraba antes."),
                }
            return {}

        # Lo más accionable primero: si hubo candidatas que sólo tropezaron con
        # UN filtro, ese es el que hay que aflojar y se sabe exactamente cuántas
        # entrarían. Recién si no hay ninguna se informa el que más descarta.
        near = max(near_miss.items(), key=lambda kv: kv[1], default=None)
        if near is not None:
            key, count = near
            label = _CRIT_BY_KEY[key][2]
            limit, reached = accept.get(key), fail_best.get(key)
            txt = (f"<b>{count}</b> de las {tested} cumplían todo salvo "
                   f"<b>{label}</b>. Pediste {limit:g} y la mejor de ésas llegó a "
                   f"<b>{reached:.2f}</b>: aflojá ese filtro y entran.")
        else:
            key, count = worst
            label = _CRIT_BY_KEY[key][2]
            limit, reached = accept.get(key), fail_best.get(key)
            txt = (f"Ninguna candidata quedó cerca: todas fallan dos filtros o más "
                   f"a la vez. El que más descarta es <b>{label}</b> ({count} de "
                   f"{tested}); pediste {limit:g} y las que fallaron ahí no pasaron "
                   f"de <b>{reached:.2f}</b>.") if reached is not None else ""
        if frenadas_afuera:
            una = frenadas_afuera == 1
            txt += (f" Además, <b>{frenadas_afuera}</b> "
                    f"{'pasó' if una else 'pasaron'} los filtros con los datos "
                    f"de la búsqueda y se "
                    f"{'cayó' if una else 'cayeron'} en el tramo reservado.")
        out = {"reason": key, "criterion": label, "limit": limit,
               "best_reached": reached, "rejected": count, "text": txt,
               "frenadas_afuera": frenadas_afuera,
               "near_miss": near_miss}
        # la sugerencia de riesgo proyecta desde el MEJOR rendimiento alcanzado
        # por cualquier candidata, no desde el mejor de las que fallaron
        hint = _risk_suggestion(key, limit, best_seen.get(key))
        if hint:
            out["suggestion"] = hint
        return out

    def _risk_suggestion(key: str, limit: float | None,
                         reached: float | None) -> dict[str, Any] | None:
        """If the return target is out of reach at the current risk per trade,
        work out the risk that would get there — and what it costs in drawdown.

        Both CAGR and drawdown scale close to linearly with risk per trade
        (measured on SP500 H1: 1% risk -> 5.9% CAGR / 8.8% DD; 3% -> 17.3%/25.1%),
        so a single multiplier projects both honestly enough to decide with.
        """
        if key != "min_cagr_pct" or not limit or not reached or reached <= 0:
            return None
        if risk is None or risk.size_mode not in ("risk_pct", "percent_equity"):
            return None
        factor = limit / reached
        if factor <= 1.05:
            return None                                   # ya está al alcance
        current = risk.size_value
        dd_now = top_cagr.get("max_drawdown_pct", 0.0)
        unit = "riesgo por operación" if risk.size_mode == "risk_pct" else "capital nominal"

        # Un multiplicador enorme significa que el objetivo no está en este
        # mercado: subir el riesgo lo alcanzaría en el papel y reventaría la
        # cuenta en la práctica. Mejor proponer una meta que sí existe.
        SANE_FACTOR = 4.0
        if factor > SANE_FACTOR * 3:
            realistic = round(reached * SANE_FACTOR, 1)
            return {
                "current": current, "needed": None, "factor": round(factor, 2),
                "dd_now": round(dd_now, 1),
                "dd_projected": round(dd_now * SANE_FACTOR, 1),
                "size_mode": risk.size_mode, "unreachable": True,
                "realistic_target": realistic,
                "text": (f"Ni subiendo el riesgo se llega: harían falta "
                         f"<b>{factor:.0f}×</b> más ({round(current * factor, 1):g}% por "
                         f"operación), lo que reventaría la cuenta antes de lograrlo. "
                         f"Con este mercado y estas salidas, un objetivo realista es "
                         f"<b>~{realistic:g}% anual</b> subiendo el {unit} a "
                         f"{round(current * SANE_FACTOR, 1):g}%."),
                "warning": ("Si querés más rendimiento, conviene cambiar el mercado, el "
                            "timeframe o las salidas — no forzar el tamaño de posición."),
            }

        needed = round(current * factor, 2)
        dd_then = dd_now * factor
        return {
            "current": current, "needed": needed, "factor": round(factor, 2),
            "dd_now": round(dd_now, 1), "dd_projected": round(dd_then, 1),
            "size_mode": risk.size_mode, "unreachable": False,
            "text": (f"Con {unit} de <b>{current:g}%</b> el techo es ~{reached:.1f}% anual. "
                     f"Para llegar a {limit:g}% haría falta subirlo a <b>{needed:g}%</b> "
                     f"({factor:.1f}× más), y el drawdown pasaría de ~{dd_now:.0f}% a "
                     f"<b>~{dd_then:.0f}%</b>."),
            "warning": ("Un drawdown así vacía cuentas reales: es perder más de la mitad "
                        "del capital antes de recuperar." if dd_then >= 45 else ""),
        }

    def evaluate(genome: Genome, note: str = "") -> float:
        """Backtest one genome, update every counter, return its fitness."""
        nonlocal tested, passed, too_few_trades
        spec = build_spec(genome, direction=direction, risk=risk)
        res = run_backtest(df, spec, settings, cache=cache, con_marcas=False)
        m = res.metrics
        tested += 1
        score = -1e9

        if m["trades"] < min_trades:
            too_few_trades += 1
        else:
            _note_best(m)
            missed = _failed_criteria(m, accept)
            for k in missed:
                blocked_by[k] = blocked_by.get(k, 0) + 1
                _note_fail(k, m)
            if len(missed) == 1:
                near_miss[missed[0]] = near_miss.get(missed[0], 0) + 1
            score = float(fitness(m, fitness_mode))
            if not missed:
                passed += 1
                row = _row(genome, spec, m, score, passed, res.equity)
                entra = True
                if cache_oos is not None:
                    row.update(_validate_oos(spec))
                    row["oos_ratio"] = _oos_ratio(row)
                    _ponderar_por_oos(row)

                    # LA SEGUNDA PUERTA. Se comparan las MISMAS varas contra
                    # las métricas del tramo reservado, con el mismo
                    # comparador: un segundo camino de decisión acabaría
                    # divergiendo del primero sin que nada avise.
                    #
                    # Con una bandera y no con un `continue`: esto vive dentro
                    # de una función y no de un bucle, y lo que sigue —publicar
                    # el avance— tiene que correr igual. Salir antes dejaba la
                    # pantalla sin novedades durante toda la búsqueda.
                    if exigir_oos:
                        fuera = row.get("oos") or {}
                        faltan = _failed_criteria_oos(fuera, accept)
                        if faltan or not fuera.get("trades"):
                            for k in (faltan or ["sin_operaciones_afuera"]):
                                clave = f"oos:{k}"
                                blocked_by[clave] = blocked_by.get(clave, 0) + 1
                            passed -= 1
                            entra = False
                if entra:
                    bank.append(row)
                    bank.sort(key=lambda r: r["fitness"], reverse=True)
                    del bank[keep_top:]

        if tested % 5 == 0 or tested >= max_candidates:
            best_history.append(bank[0]["fitness"] if bank else 0.0)
        # las primeras candidatas se publican de a una: en un dataset grande
        # cada backtest tarda casi un segundo y esperar diez para el primer
        # snapshot hace que la app parezca colgada apenas se aprieta Iniciar
        if handle is not None and (tested <= 5 or tested % 10 == 0
                                   or tested >= max_candidates):
            if target_keep is not None:
                msg = (f"{len(bank)}/{target_keep} estrategias en el databank · "
                       f"{tested:,} probadas{note}")
            else:
                msg = (f"{tested}/{max_candidates} candidatas · "
                       f"{len(bank)} en el databank{note}")
            handle.progress(_fraction(), msg)
            handle.publish(snapshot())
        return score

    def keep_going() -> bool:
        """Stop on: cancel, goal reached, or the safety cap on candidates.

        Es también el punto de pausa. Corta entre candidata y candidata y no en
        medio de un backtest: así el estado que se congela es siempre coherente
        —población, genomas vistos, banco— y reanudar sigue exactamente donde
        estaba en vez de repetir o saltear una candidata.
        """
        if handle is not None and handle.paused:
            handle.progress(_fraction(), f"En pausa · {len(bank)} en el databank")
            handle.publish(snapshot())
            _esperar_pausa()
        if handle is not None and handle.cancelled:
            return False
        if tested >= max_candidates:
            return False
        if target_keep is not None:
            return len(bank) < target_keep
        return True

    def fresh_genome() -> Genome | None:
        """A genome not tried yet, or None once the space looks exhausted."""
        nonlocal dupes
        for _ in range(_EXHAUSTED_AFTER):
            g = random_genome(drivers, filters, max_filters, rng,
                              sessions=sessions, rr_choices=rr_choices,
                              sin_trailing=sin_trailing)
            if g.key() not in seen:
                seen.add(g.key())
                dupes = 0
                return g
            dupes += 1
        return None

    if method == "evolution":
        pop_size = max(int(population), 8)
        pop: list[tuple[float, Genome]] = []
        while len(pop) < pop_size and keep_going():
            g = fresh_genome()
            if g is None:
                break
            pop.append((evaluate(g, " · población inicial"), g))

        generation = 0
        while pop and keep_going():
            generation += 1
            pop.sort(key=lambda t: t[0], reverse=True)
            elite = pop[:max(2, pop_size // 5)]
            children: list[tuple[float, Genome]] = list(elite)

            def pick() -> Genome:
                idx = rng.integers(0, len(pop), size=3)
                return max((pop[i] for i in idx), key=lambda t: t[0])[1]

            while len(children) < pop_size and keep_going():
                child = _mutate(_crossover(pick(), pick(), rng),
                                drivers, filters, max_filters, rng, 0.3,
                                sessions=sessions)
                if child.key() in seen:
                    alt = fresh_genome()
                    if alt is None:
                        break
                    child = alt
                else:
                    seen.add(child.key())
                children.append((evaluate(child, f" · generación {generation}"), child))
            if len(children) <= len(elite):
                break
            pop = children
    else:
        while keep_going():
            genome = fresh_genome()
            if genome is None:
                break
            evaluate(genome)

    out = snapshot(final=True)
    out["stopped"] = bool(handle.cancelled) if handle is not None else False
    out["exhausted"] = dupes >= _EXHAUSTED_AFTER
    out["reached_goal"] = target_keep is not None and len(bank) >= target_keep
    # searched as far as it was allowed to and still came up short: the UI has
    # to say so instead of presenting a half-full databank as a finished run
    out["hit_cap"] = (target_keep is not None and not out["reached_goal"]
                      and not out["stopped"] and not out["exhausted"])
    out["method"] = method
    out["sessions"] = list(sessions)
    out["too_few_trades"] = too_few_trades
    out["blocked_by"] = blocked_by
    out["best_seen"] = {k: round(v, 3) for k, v in best_seen.items()}
    return out
