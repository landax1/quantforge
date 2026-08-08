"""Genetic evolution of strategies — deterministic, seeded, no AI.

Genome = (driver template, filter set, gene values). Standard GA loop:
tournament selection, uniform crossover, gaussian gene mutation, elitism.
The same seed always reproduces the same evolution.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from botiquant.backtesting.engine import run_backtest
from botiquant.backtesting.metrics import fitness
from botiquant.core.models import BacktestSettings, RiskConfig
from botiquant.generator.generator import (
    STOP_ATR_MAX, STOP_ATR_MIN, STOP_ATR_STEP,
    Genome, build_spec, random_genes, random_genome,
    random_max_bars, random_trail_mult,
)
from botiquant.generator.templates import TEMPLATES
from botiquant.indicators.base import IndicatorCache


def _mutate(g: Genome, drivers: list[str], filters: list[str],
            max_filters: int, rng: np.random.Generator, rate: float) -> Genome:
    genome = Genome(driver=g.driver, filters=tuple(g.filters),
                    genes={t: dict(v) for t, v in g.genes.items()},
                    stop_mult=g.stop_mult, trail_mult=g.trail_mult,
                    max_bars=g.max_bars)
    # el stop evoluciona como cualquier otro parámetro: se corre un paso o dos
    if genome.stop_mult is not None and rng.random() < rate:
        delta = STOP_ATR_STEP * int(rng.integers(-2, 3))
        genome.stop_mult = round(float(np.clip(genome.stop_mult + delta,
                                               STOP_ATR_MIN, STOP_ATR_MAX)), 4)
    # trailing y tiempo máximo saltan entre opciones discretas en vez de
    # moverse de a poco: entre "sin trailing" y "trailing" no hay gradiente
    if rng.random() < rate:
        genome.trail_mult = random_trail_mult(rng)
    if rng.random() < rate:
        genome.max_bars = random_max_bars(rng)
    # structural mutation: swap driver / add / remove / replace a filter
    roll = rng.random()
    if roll < 0.10:
        genome.driver = drivers[int(rng.integers(0, len(drivers)))]
        genome.genes.setdefault(genome.driver, random_genes(genome.driver, rng))
    elif roll < 0.20 and filters:
        fs = list(genome.filters)
        if fs and (len(fs) >= max_filters or rng.random() < 0.5):
            fs.pop(int(rng.integers(0, len(fs))))
        else:
            candidate = filters[int(rng.integers(0, len(filters)))]
            if candidate not in fs:
                fs.append(candidate)
                genome.genes.setdefault(candidate, random_genes(candidate, rng))
        genome.filters = tuple(sorted(fs))
    # parametric mutation: nudge genes by one or two steps
    for t_id in (genome.driver, *genome.filters):
        t = TEMPLATES[t_id]
        vals = genome.genes.setdefault(t_id, random_genes(t_id, rng))
        for gene in t.genes:
            if rng.random() < rate:
                delta = gene.step * int(rng.integers(-2, 3))
                vals[gene.name] = float(np.clip(vals.get(gene.name, gene.default) + delta,
                                                gene.min, gene.max))
    return genome


def _crossover(a: Genome, b: Genome, rng: np.random.Generator) -> Genome:
    driver = a.driver if rng.random() < 0.5 else b.driver
    pool = sorted(set(a.filters) | set(b.filters))
    fs = tuple(sorted(f for f in pool if rng.random() < 0.5)) or \
        (a.filters if rng.random() < 0.5 else b.filters)
    genes: dict[str, dict[str, float]] = {}
    for t_id in (driver, *fs):
        pa, pb = a.genes.get(t_id), b.genes.get(t_id)
        src = pa if (pb is None or (pa is not None and rng.random() < 0.5)) else pb
        genes[t_id] = dict(src) if src else random_genes(t_id, rng)
    # cada salida se hereda de un padre o del otro, por separado: así una cría
    # puede combinar el stop de uno con el trailing del otro
    return Genome(
        driver=driver, filters=fs, genes=genes,
        stop_mult=a.stop_mult if rng.random() < 0.5 else b.stop_mult,
        trail_mult=a.trail_mult if rng.random() < 0.5 else b.trail_mult,
        max_bars=a.max_bars if rng.random() < 0.5 else b.max_bars,
    )


def evolve(
    df: pd.DataFrame,
    drivers: list[str],
    filters: list[str],
    max_filters: int = 2,
    direction: str = "both",
    risk: RiskConfig | None = None,
    settings: BacktestSettings | None = None,
    population: int = 40,
    generations: int = 15,
    mutation_rate: float = 0.3,
    elite: int = 4,
    tournament: int = 3,
    fitness_mode: str = "composite",
    min_trades: int = 20,
    seed: int = 42,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Run the GA and return the hall of fame plus per-generation history."""
    rng = np.random.default_rng(seed)
    cache = IndicatorCache(df)
    settings = settings or BacktestSettings()
    eval_cache: dict[str, tuple[float, dict[str, float]]] = {}

    def evaluate(genome: Genome) -> tuple[float, dict[str, float]]:
        key = genome.key()
        hit = eval_cache.get(key)
        if hit is not None:
            return hit
        spec = build_spec(genome, direction=direction, risk=risk)
        res = run_backtest(df, spec, settings, cache=cache)
        m = res.metrics
        score = float(fitness(m, fitness_mode)) if m["trades"] >= min_trades else -1e9
        eval_cache[key] = (score, m)
        return score, m

    pop = [random_genome(drivers, filters, max_filters, rng) for _ in range(population)]
    history: list[dict[str, float]] = []
    total_evals = population * generations

    scored: list[tuple[float, dict[str, float], Genome]] = []
    for gen in range(generations):
        scored = []
        for i, genome in enumerate(pop):
            score, m = evaluate(genome)
            scored.append((score, m, genome))
            if progress:
                done = gen * population + i + 1
                progress(done / total_evals,
                         f"Generation {gen + 1}/{generations} — evaluating {i + 1}/{population}")
        scored.sort(key=lambda t: t[0], reverse=True)
        valid = [s for s, _, _ in scored if s > -1e8]
        history.append({
            "generation": gen + 1,
            "best": round(scored[0][0], 4) if valid else 0.0,
            "mean": round(float(np.mean(valid)), 4) if valid else 0.0,
            "valid": len(valid),
        })

        if gen == generations - 1:
            break

        next_pop: list[Genome] = [g for _, _, g in scored[:elite]]
        while len(next_pop) < population:
            def pick() -> Genome:
                idxs = rng.integers(0, len(scored), size=tournament)
                best = min(idxs, key=lambda j: -scored[j][0])
                return scored[best][2]
            child = _crossover(pick(), pick(), rng)
            child = _mutate(child, drivers, filters, max_filters, rng, mutation_rate)
            next_pop.append(child)
        pop = next_pop

    seen: set[str] = set()
    hall: list[dict[str, Any]] = []
    for score, m, genome in scored:
        if score <= -1e8:
            continue
        key = genome.key()
        if key in seen:
            continue
        seen.add(key)
        spec = build_spec(genome, direction=direction, risk=risk)
        hall.append({
            "spec": spec.to_dict(),
            "metrics": m,
            "fitness": round(score, 4),
            "genome": {"driver": genome.driver, "filters": list(genome.filters),
                       "genes": genome.genes},
        })
        if len(hall) >= 10:
            break

    return {"hall_of_fame": hall, "history": history,
            "evaluations": len(eval_cache), "seed": seed}
