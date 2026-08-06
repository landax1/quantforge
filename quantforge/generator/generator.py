"""Combinatorial strategy generator.

Enumerates driver × filter combinations (the deterministic replacement for
"AI strategy generation"), backtests each candidate and ranks by fitness.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import Any, Callable

import pandas as pd

from quantforge.backtesting.engine import run_backtest
from quantforge.backtesting.metrics import fitness
from quantforge.core.models import BacktestSettings, RiskConfig, StrategySpec, TimeFilter
from quantforge.generator.templates import TEMPLATES, RuleTemplate, drivers, filters
from quantforge.indicators.base import IndicatorCache


# La distancia del stop se mide en volatilidad (múltiplo de ATR) porque es la
# única unidad que vale igual en cualquier mercado: 2×ATR son ~14 puntos en el
# S&P y ~0.006 en EURUSD sin que nadie configure nada. El minero la busca como
# un gen más, así el usuario sólo elige riesgo por operación y relación R:B.
STOP_ATR_MIN, STOP_ATR_MAX, STOP_ATR_STEP = 1.0, 5.0, 0.25


def random_stop_mult(rng) -> float:
    steps = int(round((STOP_ATR_MAX - STOP_ATR_MIN) / STOP_ATR_STEP))
    return round(STOP_ATR_MIN + STOP_ATR_STEP * int(rng.integers(0, steps + 1)), 4)


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

    def key(self) -> str:
        parts = [self.driver, *sorted(self.filters)]
        gene_sig = ";".join(
            f"{t}:{','.join(f'{k}={v:g}' for k, v in sorted(vals.items()))}"
            for t, vals in sorted(self.genes.items())
        )
        exit_sig = f"@sl={self.stop_mult:g}" if self.stop_mult is not None else ""
        return "|".join(parts) + "#" + gene_sig + exit_sig


def exit_risk(risk: RiskConfig | None, stop_mult: float | None) -> RiskConfig | None:
    """El RiskConfig de una candidata: su stop evolucionado + el R:B pedido."""
    if risk is None or stop_mult is None:
        return risk
    return replace(risk, stop_type="atr", stop_value=stop_mult,
                   target_type="atr", target_value=round(stop_mult * risk.reward_ratio, 4))


def build_spec(
    genome: Genome,
    direction: str = "both",
    risk: RiskConfig | None = None,
    time_filter: TimeFilter | None = None,
    name: str | None = None,
) -> StrategySpec:
    """Materialise a genome into a runnable :class:`StrategySpec`."""
    risk = exit_risk(risk, genome.stop_mult)
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
        time_filter=time_filter or TimeFilter(),
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


def random_genome(drivers: list[str], filters: list[str],
                  max_filters: int, rng, evolve_exits: bool = True) -> Genome:
    """One random strategy recipe: driver + filter subset + random genes."""
    drv = drivers[int(rng.integers(0, len(drivers)))]
    k = int(rng.integers(0, max_filters + 1)) if filters else 0
    fs = tuple(sorted(rng.choice(filters, size=min(k, len(filters)),
                                 replace=False).tolist())) if k else ()
    genes = {t: random_genes(t, rng) for t in (drv, *fs)}
    return Genome(driver=drv, filters=fs, genes=genes,
                  stop_mult=random_stop_mult(rng) if evolve_exits else None)


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
