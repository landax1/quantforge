"""Generator, GA, optimizer, Monte Carlo and walk-forward behaviour."""

from __future__ import annotations

import numpy as np
import pytest

from botiquant.analysis.montecarlo import monte_carlo
from botiquant.analysis.walkforward import walk_forward
from botiquant.backtesting.engine import run_backtest
from botiquant.generator.generator import Genome, build_spec, generate_strategies
from botiquant.generator.templates import TEMPLATES, drivers, filters
from botiquant.genetic.evolution import evolve
from botiquant.optimizer.optimizer import apply_values, discover_dimensions, optimize
from botiquant.portfolio.portfolio import build_portfolio


def test_templates_build_valid_specs(df):
    for t in TEMPLATES.values():
        genome = Genome(driver=t.id) if t.kind == "driver" else \
            Genome(driver="ema_cross", filters=(t.id,))
        spec = build_spec(genome, direction="both")
        res = run_backtest(df.iloc[:2000], spec)
        assert res.metrics["trades"] >= 0   # must run without raising


def test_generator_ranks_and_filters(df):
    out = generate_strategies(df.iloc[:3000], allowed_drivers=["ema_cross", "rsi_reversal"],
                              allowed_filters=["adx_filter"], max_filters=1,
                              min_trades=5, top_n=10)
    assert out
    fitness = [r["fitness"] for r in out]
    assert fitness == sorted(fitness, reverse=True)
    assert all(r["metrics"]["trades"] >= 5 for r in out)


def test_evolution_deterministic(df):
    kw = dict(drivers=["ema_cross", "donchian_break"], filters=["adx_filter"],
              population=10, generations=3, min_trades=5, seed=123)
    a = evolve(df.iloc[:2500], **kw)
    b = evolve(df.iloc[:2500], **kw)
    assert a["history"] == b["history"]
    assert [h["fitness"] for h in a["hall_of_fame"]] == \
           [h["fitness"] for h in b["hall_of_fame"]]


def test_evolution_seed_changes_outcome(df):
    kw = dict(drivers=["ema_cross", "donchian_break"], filters=["adx_filter"],
              population=10, generations=3, min_trades=5)
    a = evolve(df.iloc[:2500], seed=1, **kw)
    b = evolve(df.iloc[:2500], seed=2, **kw)
    assert a["evaluations"] != b["evaluations"] or a["history"] != b["history"]


def test_optimizer_dimensions_and_apply(ema_spec):
    dims = discover_dimensions(ema_spec)
    keys = {d.key for d in dims}
    assert "entry_long[0].left.EMA.period" in keys
    assert "risk.stop_value" in keys
    tuned = apply_values(ema_spec, {"entry_long[0].left.EMA.period": 33.0,
                                    "risk.stop_value": 4.0})
    assert tuned.entry_long[0].left.params["period"] == 33.0
    assert tuned.risk.stop_value == 4.0
    # original untouched
    assert ema_spec.entry_long[0].left.params["period"] == 20


def test_optimizer_improves_or_matches_baseline(df, ema_spec):
    out = optimize(df.iloc[:3000], ema_spec, mode="quick", budget=20, min_trades=3, seed=7)
    assert out["tested"] <= 21  # baseline + budget cap
    assert out["evaluations"][0]["fitness"] >= out["evaluations"][-1]["fitness"]


def test_monte_carlo_deterministic_and_sane():
    rng = np.random.default_rng(0)
    pnls = rng.normal(10, 100, size=80).tolist()
    a = monte_carlo(pnls, simulations=300, seed=9)
    b = monte_carlo(pnls, simulations=300, seed=9)
    assert a["final_equity"] == b["final_equity"]
    assert a["final_equity"]["ci_90"][0] <= a["final_equity"]["median"] \
        <= a["final_equity"]["ci_90"][1]
    assert 0 <= a["risk_of_ruin_pct"] <= 100


def test_monte_carlo_needs_trades():
    with pytest.raises(ValueError):
        monte_carlo([1.0, 2.0], simulations=100)


def test_walk_forward_folds(df, ema_spec):
    out = walk_forward(df, ema_spec, folds=3, optimize_budget=5, min_trades=2)
    assert out["summary"]["folds"] == 3
    assert out["summary"]["verdict"] in ("robust", "acceptable", "overfitted")
    for fold in out["folds"]:
        assert fold["test_start"] > fold["train_start"]


def test_portfolio_math(df, ema_spec):
    resA = run_backtest(df, ema_spec)
    specB = build_spec(Genome(driver="rsi_reversal"), direction="both")
    resB = run_backtest(df, specB)
    port = build_portfolio([
        {"name": "A", "equity": resA.equity.tolist(), "timestamps": resA.timestamps,
         "initial_capital": 10_000},
        {"name": "B", "equity": resB.equity.tolist(), "timestamps": resB.timestamps,
         "initial_capital": 10_000},
    ], weights=[2.0, 1.0])
    assert port["weights"] == [round(2 / 3, 4), round(1 / 3, 4)]
    assert len(port["correlation"]) == 2
    assert abs(sum(port["risk_contribution_pct"]) - 100.0) < 1.0
    assert -1.0 <= port["metrics"]["avg_correlation"] <= 1.0
