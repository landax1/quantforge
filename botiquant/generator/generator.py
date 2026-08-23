"""Combinatorial strategy generator.

Enumerates driver × filter combinations (the deterministic replacement for
"AI strategy generation"), backtests each candidate and ranks by fitness.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import Any, Callable

import pandas as pd

from botiquant.backtesting.engine import run_backtest
from botiquant.backtesting.metrics import fitness
from botiquant.core import sesiones
from botiquant.core.models import BacktestSettings, RiskConfig, StrategySpec, TimeFilter
from botiquant.generator.templates import TEMPLATES, RuleTemplate, drivers, filters
from botiquant.indicators.base import IndicatorCache


# La distancia del stop se mide en volatilidad (múltiplo de ATR) porque es la
# única unidad que vale igual en cualquier mercado: 2×ATR son ~14 puntos en el
# S&P y ~0.006 en EURUSD sin que nadie configure nada. El minero la busca como
# un gen más, así el usuario sólo elige riesgo por operación y relación R:B.
STOP_ATR_MIN, STOP_ATR_MAX, STOP_ATR_STEP = 1.0, 5.0, 0.25

# Salidas evolucionables. Hasta acá todas las candidatas salían igual —stop y
# target fijos— y eso dejaba afuera familias enteras: las que necesitan dejar
# correr la ganancia (trailing) y las que se mueren si aguantan demasiado
# (salida por tiempo). Ambas son genes, no configuración: cuál conviene depende
# de las entradas de cada estrategia, y eso el usuario no lo puede saber.
#
# El 0 es un valor válido en los dos y significa "sin trailing" / "sin límite",
# así que la búsqueda puede seguir encontrando la forma simple de siempre.
TRAIL_CHOICES: tuple[float, ...] = (0.0, 0.0, 0.0, 1.0, 1.5, 2.0, 3.0, 4.0)
MAX_BARS_CHOICES: tuple[int, ...] = (0, 0, 0, 0, 12, 24, 48, 96, 192)

# EL RIESGO:BENEFICIO, cuando se lo deja buscar.
#
# Era lo único de la salida que seguía siendo configuración fija y multiplicaba
# a todas las candidatas por igual. Medido sobre SP500 a una hora, 30
# estrategias por corrida: con 1:2 la mediana de aciertos es 39,8% y NINGUNA
# llega a 60%; con 0,5 la mediana es 59,5% y quince de treinta pasan el 60%.
#
# O sea que pedir win rate alto con el 1:2 de fábrica no devuelve nada nunca,
# por más candidatas que se prueben: el techo no lo pone la búsqueda, lo pone
# la aritmética de la relación. Con el R:B adentro del genoma, la misma
# búsqueda puede traer las dos familias.
#
# Se ofrece SÓLO si se pide una lista: sin ella cada candidata usa el valor
# configurado, que es exactamente lo que hacía antes.
RR_CHOICES: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)


def random_stop_mult(rng) -> float:
    steps = int(round((STOP_ATR_MAX - STOP_ATR_MIN) / STOP_ATR_STEP))
    return round(STOP_ATR_MIN + STOP_ATR_STEP * int(rng.integers(0, steps + 1)), 4)


def random_trail_mult(rng) -> float:
    return float(TRAIL_CHOICES[int(rng.integers(0, len(TRAIL_CHOICES)))])


def random_max_bars(rng) -> int:
    return int(MAX_BARS_CHOICES[int(rng.integers(0, len(MAX_BARS_CHOICES)))])


@dataclass(slots=True)
class Genome:
    """A strategy recipe: one driver, optional filters, gene values.

    ``stop_mult`` is the exit gene: how many ATRs away the stop sits. It is
    searched like any other parameter, so each candidate carries the exit
    distance that actually suits its entries.
    """

    driver: str
    filters: tuple[str, ...] = ()
    genes: dict[str, dict[str, float]] = field(default_factory=dict)
    stop_mult: float | None = None
    trail_mult: float = 0.0
    max_bars: int = 0
    # La relación riesgo:beneficio. `None` significa "la que configuró el
    # usuario", que es como funcionó siempre; con un número, esta candidata
    # lleva el suyo. Es un gen por la misma razón que la franja: cuál conviene
    # depende de las entradas, y el usuario no lo puede saber de antemano.
    rr_mult: float | None = None
    # En qué franja horaria opera. Es un gen y no configuración porque cuál
    # sirve depende de las entradas: una ruptura de rango vive de la apertura
    # de Londres y una reversión a la media de las horas quietas. Ver
    # botiquant/core/sesiones.py.
    session: str = sesiones.SIN_RESTRICCION

    def key(self) -> str:
        parts = [self.driver, *sorted(self.filters)]
        gene_sig = ";".join(
            f"{t}:{','.join(f'{k}={v:g}' for k, v in sorted(vals.items()))}"
            for t, vals in sorted(self.genes.items())
        )
        exit_sig = f"@sl={self.stop_mult:g}" if self.stop_mult is not None else ""
        if self.trail_mult:
            exit_sig += f"/tr={self.trail_mult:g}"
        if self.max_bars:
            exit_sig += f"/mb={self.max_bars:d}"
        # sin esto, dos candidatas idénticas salvo el horario cuentan como la
        # misma y la búsqueda descarta la segunda por duplicada
        if self.session and self.session != sesiones.SIN_RESTRICCION:
            exit_sig += f"/hs={self.session}"
        # sin esto, dos candidatas iguales salvo el R:B cuentan como la misma y
        # la búsqueda descarta la segunda por duplicada — que es justo la que
        # tiene el perfil de aciertos distinto
        if self.rr_mult is not None:
            exit_sig += f"/rb={self.rr_mult:g}"
        return "|".join(parts) + "#" + gene_sig + exit_sig


def exit_risk(risk: RiskConfig | None, genome: "Genome") -> RiskConfig | None:
    """El RiskConfig de una candidata: sus salidas evolucionadas + el R:B pedido."""
    if risk is None or genome.stop_mult is None:
        return risk
    # El R:B de esta candidata si lo trae, y si no el configurado. Se escribe
    # también en `reward_ratio` y no sólo en el objetivo: es lo que queda
    # guardado en la estrategia y lo que lee el exportador a MetaTrader, así
    # que si no se actualiza, el robot sale con una relación que no es la que
    # se midió.
    rb = genome.rr_mult if genome.rr_mult is not None else risk.reward_ratio
    return replace(
        risk,
        stop_type="atr", stop_value=genome.stop_mult,
        target_type="atr", target_value=round(genome.stop_mult * rb, 4),
        reward_ratio=rb,
        trail_atr=genome.trail_mult,
        max_bars_in_trade=genome.max_bars,
    )


def build_spec(
    genome: Genome,
    direction: str = "both",
    risk: RiskConfig | None = None,
    time_filter: TimeFilter | None = None,
    name: str | None = None,
) -> StrategySpec:
    """Materialise a genome into a runnable :class:`StrategySpec`."""
    risk = exit_risk(risk, genome)
    templates = [TEMPLATES[genome.driver]] + [TEMPLATES[f] for f in genome.filters]
    entry_long, entry_short = [], []
    labels = []
    for t in templates:
        g = t.resolved(genome.genes.get(t.id))
        lng, sht = t.build(g)
        entry_long.extend(lng)
        entry_short.extend(sht)
        labels.append(t.label)
    return StrategySpec(
        name=name or " + ".join(labels),
        direction=direction,
        entry_long=entry_long,
        entry_short=entry_short,
        risk=risk or RiskConfig(),
        # un time_filter explícito gana —lo usa quien re-evalúa una estrategia
        # ya construida—, y si no viene, manda la franja del genoma
        time_filter=time_filter or sesiones.filtro(genome.session),
    )


def default_genes(t: RuleTemplate) -> dict[str, float]:
    return {g.name: g.default for g in t.genes}


def random_genes(t_id: str, rng) -> dict[str, float]:
    """Uniform random gene values on each template's step grid."""
    t = TEMPLATES[t_id]
    out: dict[str, float] = {}
    for g in t.genes:
        steps = max(int(round((g.max - g.min) / g.step)), 1)
        out[g.name] = g.min + g.step * int(rng.integers(0, steps + 1))
    return out


def random_rr(opciones: list[float] | None, rng) -> float | None:
    """Un R:B de los permitidos. Sin lista, `None` = usar el configurado."""
    if not opciones:
        return None
    limpias = [float(x) for x in opciones if float(x) > 0]
    if not limpias:
        return None
    if len(limpias) == 1:
        return limpias[0]
    return limpias[int(rng.integers(0, len(limpias)))]


def random_session(sessions: list[str] | None, rng) -> str:
    """Una franja horaria de las permitidas. Con una sola, siempre esa."""
    opciones = sesiones.normalizar(sessions)
    if len(opciones) == 1:
        return opciones[0]
    return opciones[int(rng.integers(0, len(opciones)))]


def random_genome(drivers: list[str], filters: list[str],
                  max_filters: int, rng, evolve_exits: bool = True,
                  sessions: list[str] | None = None,
                  rr_choices: list[float] | None = None) -> Genome:
    """One random strategy recipe: driver + filter subset + random genes."""
    drv = drivers[int(rng.integers(0, len(drivers)))]
    k = int(rng.integers(0, max_filters + 1)) if filters else 0
    fs = tuple(sorted(rng.choice(filters, size=min(k, len(filters)),
                                 replace=False).tolist())) if k else ()
    genes = {t: random_genes(t, rng) for t in (drv, *fs)}
    return Genome(driver=drv, filters=fs, genes=genes,
                  stop_mult=random_stop_mult(rng) if evolve_exits else None,
                  trail_mult=random_trail_mult(rng) if evolve_exits else 0.0,
                  max_bars=random_max_bars(rng) if evolve_exits else 0,
                  rr_mult=random_rr(rr_choices, rng),
                  session=random_session(sessions, rng))


def generate_strategies(
    df: pd.DataFrame,
    allowed_drivers: list[str] | None = None,
    allowed_filters: list[str] | None = None,
    max_filters: int = 1,
    direction: str = "both",
    risk: RiskConfig | None = None,
    settings: BacktestSettings | None = None,
    fitness_mode: str = "composite",
    min_trades: int = 20,
    top_n: int = 20,
    progress: Callable[[float, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Enumerate, backtest and rank strategy candidates.

    Returns the top ``top_n`` results as dicts with the spec, metrics and
    fitness score, sorted best-first.
    """
    dset = [d.id for d in drivers()]
    fset = [f.id for f in filters()]
    use_drivers = [d for d in (allowed_drivers or dset) if d in dset]
    use_filters = [f for f in (allowed_filters or fset) if f in fset]

    combos: list[Genome] = []
    for drv in use_drivers:
        for k in range(0, max_filters + 1):
            for fs in combinations(use_filters, k):
                combos.append(Genome(driver=drv, filters=fs))

    cache = IndicatorCache(df)
    settings = settings or BacktestSettings()
    results: list[dict[str, Any]] = []
    total = len(combos)
    for i, genome in enumerate(combos):
        spec = build_spec(genome, direction=direction, risk=risk)
        res = run_backtest(df, spec, settings, cache=cache)
        m = res.metrics
        score = fitness(m, fitness_mode) if m["trades"] >= min_trades else -1e9
        results.append({
            "spec": spec.to_dict(),
            "metrics": m,
            "fitness": round(float(score), 4),
            "genome": {"driver": genome.driver, "filters": list(genome.filters)},
        })
        if progress and (i % 5 == 0 or i == total - 1):
            progress((i + 1) / total, f"Tested {i + 1}/{total} combinations")

    results.sort(key=lambda r: r["fitness"], reverse=True)
    kept = [r for r in results if r["fitness"] > -1e8][:top_n]
    return kept
