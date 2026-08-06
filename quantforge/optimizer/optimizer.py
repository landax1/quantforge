"""Parameter optimizer for an existing strategy.

Discovers every tunable number inside a spec (indicator parameters in the
rules, optionally stop/target multiples), then searches:

* **quick** — seeded random search, small budget;
* **balanced** — random search + hill-climb refinement around the best point;
* **exhaustive** — full grid, automatically coarsened to stay under budget.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from quantforge.backtesting.engine import run_backtest
from quantforge.backtesting.metrics import fitness
from quantforge.core.models import BacktestSettings, Condition, Operand, StrategySpec
from quantforge.indicators.base import REGISTRY, IndicatorCache


@dataclass(slots=True)
class Dimension:
    """One tunable number found inside the spec."""

    key: str            # e.g. "entry_long[0].left.EMA.period" or "risk.stop_value"
    label: str
    current: float
    min: float
    max: float
    step: float

    def values(self) -> np.ndarray:
        n = int(round((self.max - self.min) / self.step)) + 1
        return np.round(self.min + self.step * np.arange(n), 10)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "current": self.current,
                "min": self.min, "max": self.max, "step": self.step}


def _iter_operands(spec: StrategySpec):
    for group in ("entry_long", "exit_long", "entry_short", "exit_short"):
        conds: list[Condition] = getattr(spec, group)
        for ci, cond in enumerate(conds):
            for side in ("left", "right"):
                op: Operand = getattr(cond, side)
                if op.type == "indicator":
                    yield group, ci, side, op


def discover_dimensions(spec: StrategySpec, include_risk: bool = True) -> list[Dimension]:
    """Find every optimizable number in the spec, deduplicated by key."""
    dims: dict[str, Dimension] = {}
    for group, ci, side, op in _iter_operands(spec):
        cls = REGISTRY.get(op.name)
        if cls is None:
            continue
        for p in cls.params:
            key = f"{group}[{ci}].{side}.{op.name}.{p.name}"
            cur = float(op.params.get(p.name, p.default))
            dims[key] = Dimension(key=key, label=f"{op.name} {p.name}",
                                  current=cur, min=p.min, max=p.max, step=p.step)
    if include_risk:
        r = spec.risk
        if r.stop_type != "none":
            hi = 8.0 if r.stop_type == "atr" else 10.0
            dims["risk.stop_value"] = Dimension(
                "risk.stop_value", f"Stop ({r.stop_type})", r.stop_value, 0.5, hi, 0.5)
        if r.target_type != "none":
            hi = 12.0 if r.target_type == "atr" else 20.0
            dims["risk.target_value"] = Dimension(
                "risk.target_value", f"Target ({r.target_type})", r.target_value, 0.5, hi, 0.5)
    return list(dims.values())


def apply_values(spec: StrategySpec, values: dict[str, float]) -> StrategySpec:
    """Return a copy of ``spec`` with dimension values substituted in."""
    out = StrategySpec.from_dict(spec.to_dict())
    for group, ci, side, op in _iter_operands(out):
        for pname in list(op.params) or [p.name for p in REGISTRY[op.name].params]:
            key = f"{group}[{ci}].{side}.{op.name}.{pname}"
            if key in values:
                op.params[pname] = float(values[key])
        # params may be empty if defaults were implied — fill from any matching key
        if op.name in REGISTRY:
            for p in REGISTRY[op.name].params:
                key = f"{group}[{ci}].{side}.{op.name}.{p.name}"
                if key in values:
                    op.params[p.name] = float(values[key])
    if "risk.stop_value" in values:
        out.risk.stop_value = float(values["risk.stop_value"])
    if "risk.target_value" in values:
        out.risk.target_value = float(values["risk.target_value"])
    return out


def _snap(dim: Dimension, v: float) -> float:
    stepped = round((v - dim.min) / dim.step) * dim.step + dim.min
    return float(np.clip(stepped, dim.min, dim.max))


def optimize(
    df: pd.DataFrame,
    spec: StrategySpec,
    mode: str = "quick",
    dims: list[Dimension] | None = None,
    settings: BacktestSettings | None = None,
    fitness_mode: str = "composite",
    min_trades: int = 10,
    seed: int = 42,
    budget: int | None = None,
    progress: Callable[[float, str], None] | None = None,
    top_n: int = 25,
) -> dict[str, Any]:
    """Search the parameter space; returns ranked evaluations and the best spec."""
    dims = dims if dims is not None else discover_dimensions(spec)
    settings = settings or BacktestSettings()
    cache = IndicatorCache(df)
    rng = np.random.default_rng(seed)
    budgets = {"quick": 60, "balanced": 150, "exhaustive": 1200}
    max_evals = budget or budgets.get(mode, 60)

    seen: dict[tuple, tuple[float, dict[str, float]]] = {}

    def evaluate(values: dict[str, float]) -> tuple[float, dict[str, float]]:
        key = tuple(sorted(values.items()))
        hit = seen.get(key)
        if hit is not None:
            return hit
        candidate = apply_values(spec, values)
        m = run_backtest(df, candidate, settings, cache=cache).metrics
        score = float(fitness(m, fitness_mode)) if m["trades"] >= min_trades else -1e9
        seen[key] = (score, m)
        if progress:
            progress(min(len(seen) / max_evals, 1.0), f"Evaluated {len(seen)}/{max_evals}")
        return score, m

    if not dims:
        score, m = evaluate({})
        return {"evaluations": [{"values": {}, "fitness": score, "metrics": m}],
                "best_spec": spec.to_dict(), "dimensions": [], "tested": 1}

    baseline = {d.key: d.current for d in dims}
    evaluate(baseline)

    if mode == "exhaustive":
        grids = [d.values() for d in dims]
        combo_count = int(np.prod([len(g) for g in grids]))
        # coarsen axes until the grid fits the budget
        while combo_count > max_evals:
            longest = int(np.argmax([len(g) for g in grids]))
            if len(grids[longest]) <= 2:
                break
            grids[longest] = grids[longest][::2]
            combo_count = int(np.prod([len(g) for g in grids]))
        for combo in itertools.islice(itertools.product(*grids), max_evals):
            evaluate({d.key: float(v) for d, v in zip(dims, combo)})
    else:
        random_budget = max_evals if mode == "quick" else int(max_evals * 0.7)
        while len(seen) < random_budget:
            values = {d.key: _snap(d, rng.uniform(d.min, d.max)) for d in dims}
            evaluate(values)
        if mode == "balanced":
            best_key = max(seen, key=lambda k: seen[k][0])
            current = dict(best_key)
            improved = True
            while improved and len(seen) < max_evals:
                improved = False
                for d in dims:
                    for delta in (-d.step, d.step):
                        if len(seen) >= max_evals:
                            break
                        trial = dict(current)
                        trial[d.key] = _snap(d, trial[d.key] + delta)
                        s, _ = evaluate(trial)
                        if s > seen[tuple(sorted(current.items()))][0]:
                            current = trial
                            improved = True

    ranked = sorted(seen.items(), key=lambda kv: kv[1][0], reverse=True)
    evaluations = [
        {"values": dict(k), "fitness": round(s, 4), "metrics": m}
        for k, (s, m) in ranked[:top_n] if s > -1e8
    ]
    best_values = dict(ranked[0][0]) if ranked and ranked[0][1][0] > -1e8 else baseline
    best_spec = apply_values(spec, best_values)
    return {
        "evaluations": evaluations,
        "best_spec": best_spec.to_dict(),
        "best_values": best_values,
        "dimensions": [d.to_dict() for d in dims],
        "tested": len(seen),
    }
