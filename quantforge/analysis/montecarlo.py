"""Monte Carlo robustness simulation.

Bootstraps the realised trade P&L sequence (sampling with replacement) to
answer: how sensitive is the equity curve to trade ordering and selection?
Deterministic under a fixed seed.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def monte_carlo(
    trade_pnls: list[float],
    initial_capital: float = 10_000.0,
    simulations: int = 1000,
    ruin_threshold_pct: float = 30.0,
    seed: int = 42,
) -> dict[str, Any]:
    """Run the simulation and summarise distributions.

    Returns percentile equity bands, final-equity / max-drawdown distributions,
    confidence intervals and the risk of ruin (probability of losing
    ``ruin_threshold_pct`` % of starting capital at any point).
    """
    pnls = np.asarray(trade_pnls, dtype=np.float64)
    n = len(pnls)
    if n < 5:
        raise ValueError(f"Need at least 5 trades for Monte Carlo (got {n})")
    simulations = int(np.clip(simulations, 100, 20_000))
    rng = np.random.default_rng(seed)

    # bootstrap: simulations × n resampled trade sequences
    samples = pnls[rng.integers(0, n, size=(simulations, n))]
    equity = initial_capital + np.cumsum(samples, axis=1)
    equity = np.hstack([np.full((simulations, 1), initial_capital), equity])

    peaks = np.maximum.accumulate(equity, axis=1)
    dd = peaks - equity
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_pct = np.where(peaks > 0, dd / peaks * 100.0, 0.0)
    max_dd_pct = dd_pct.max(axis=1)
    final = equity[:, -1]
    ruin_level = initial_capital * (1.0 - ruin_threshold_pct / 100.0)
    ruined = (equity.min(axis=1) <= ruin_level).mean()

    def pct(a: np.ndarray, q: float) -> float:
        return round(float(np.percentile(a, q)), 2)

    # per-step percentile bands for the fan chart (downsample steps for transport)
    steps = equity.shape[1]
    idx = np.linspace(0, steps - 1, min(steps, 300)).astype(int)
    bands = {
        "p5": [pct(equity[:, i], 5) for i in idx],
        "p25": [pct(equity[:, i], 25) for i in idx],
        "p50": [pct(equity[:, i], 50) for i in idx],
        "p75": [pct(equity[:, i], 75) for i in idx],
        "p95": [pct(equity[:, i], 95) for i in idx],
        "steps": idx.tolist(),
    }

    hist_counts, hist_edges = np.histogram(final, bins=40)
    dd_counts, dd_edges = np.histogram(max_dd_pct, bins=30)

    return {
        "simulations": simulations,
        "trades_per_sim": n,
        "initial_capital": initial_capital,
        "bands": bands,
        "final_equity": {
            "mean": round(float(final.mean()), 2),
            "median": pct(final, 50),
            "ci_90": [pct(final, 5), pct(final, 95)],
            "ci_50": [pct(final, 25), pct(final, 75)],
            "worst": round(float(final.min()), 2),
            "best": round(float(final.max()), 2),
            "prob_loss": round(float((final < initial_capital).mean() * 100.0), 2),
            "histogram": {"counts": hist_counts.tolist(),
                          "edges": np.round(hist_edges, 2).tolist()},
        },
        "max_drawdown_pct": {
            "median": pct(max_dd_pct, 50),
            "p95": pct(max_dd_pct, 95),
            "worst": round(float(max_dd_pct.max()), 2),
            "histogram": {"counts": dd_counts.tolist(),
                          "edges": np.round(dd_edges, 2).tolist()},
        },
        "risk_of_ruin_pct": round(float(ruined * 100.0), 2),
        "ruin_threshold_pct": ruin_threshold_pct,
        "seed": seed,
    }
