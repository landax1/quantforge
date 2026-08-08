"""Walk-forward analysis.

Rolls train/test windows across the data; each fold re-optimizes the strategy
on its training slice and evaluates the tuned parameters out-of-sample. The
stitched OOS equity and walk-forward efficiency show whether an edge survives
outside the data it was fitted on.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from botiquant.backtesting.engine import run_backtest
from botiquant.core.models import BacktestSettings, StrategySpec
from botiquant.optimizer.optimizer import discover_dimensions, optimize, apply_values


def walk_forward(
    df: pd.DataFrame,
    spec: StrategySpec,
    folds: int = 4,
    train_pct: float = 70.0,
    optimize_budget: int = 40,
    settings: BacktestSettings | None = None,
    fitness_mode: str = "composite",
    min_trades: int = 5,
    seed: int = 42,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Run anchored-window walk-forward analysis and aggregate OOS results."""
    settings = settings or BacktestSettings()
    n = len(df)
    folds = int(np.clip(folds, 2, 10))
    train_frac = np.clip(train_pct, 50.0, 90.0) / 100.0

    # rolling windows: each window = train + test, windows advance by test size
    window = int(n / (1 + (folds - 1) * (1 - train_frac)))
    test_len = max(int(window * (1 - train_frac)), 50)
    train_len = window - test_len
    if train_len < 200:
        raise ValueError("Not enough data for this many folds — reduce folds or use more bars")

    dims = discover_dimensions(spec)
    fold_rows: list[dict[str, Any]] = []
    oos_equity: list[float] = []
    oos_stamps: list[str] = []
    capital = settings.initial_capital

    for k in range(folds):
        start = k * test_len
        train_df = df.iloc[start: start + train_len]
        test_df = df.iloc[start + train_len: start + train_len + test_len]
        if len(test_df) < 30:
            break

        def fold_progress(frac: float, msg: str) -> None:
            if progress:
                progress((k + frac * 0.9) / folds, f"Fold {k + 1}/{folds}: {msg}")

        opt = optimize(train_df, spec, mode="quick", dims=dims, settings=settings,
                       fitness_mode=fitness_mode, min_trades=min_trades,
                       seed=seed + k, budget=optimize_budget, progress=fold_progress)
        tuned = apply_values(spec, opt.get("best_values", {}))

        is_res = run_backtest(train_df, tuned, settings)
        fold_settings = BacktestSettings(initial_capital=capital,
                                         commission_pct=settings.commission_pct,
                                         slippage_pct=settings.slippage_pct)
        oos_res = run_backtest(test_df, tuned, fold_settings)

        # stitch OOS equity (compounding capital across folds)
        step = max(len(oos_res.equity) // 200, 1)
        oos_equity.extend(float(v) for v in oos_res.equity[::step])
        oos_stamps.extend(oos_res.timestamps[::step])
        capital = float(oos_res.equity[-1]) if len(oos_res.equity) else capital

        fold_rows.append({
            "fold": k + 1,
            "train_start": str(train_df.index[0]), "train_end": str(train_df.index[-1]),
            "test_start": str(test_df.index[0]), "test_end": str(test_df.index[-1]),
            "best_values": opt.get("best_values", {}),
            "is_net_profit_pct": is_res.metrics["net_profit_pct"],
            "oos_net_profit_pct": oos_res.metrics["net_profit_pct"],
            "oos_trades": oos_res.metrics["trades"],
            "oos_profit_factor": oos_res.metrics["profit_factor"],
            "oos_max_dd_pct": oos_res.metrics["max_drawdown_pct"],
        })
        if progress:
            progress((k + 1) / folds, f"Fold {k + 1}/{folds} complete")

    if not fold_rows:
        raise ValueError("No folds could be evaluated")

    is_avg = float(np.mean([f["is_net_profit_pct"] for f in fold_rows]))
    oos_avg = float(np.mean([f["oos_net_profit_pct"] for f in fold_rows]))
    efficiency = oos_avg / is_avg if abs(is_avg) > 1e-9 else 0.0
    profitable = sum(1 for f in fold_rows if f["oos_net_profit_pct"] > 0)

    total_oos_return = (capital / settings.initial_capital - 1.0) * 100.0
    return {
        "folds": fold_rows,
        "oos_equity": [round(v, 2) for v in oos_equity],
        "oos_timestamps": oos_stamps,
        "summary": {
            "folds": len(fold_rows),
            "profitable_folds": profitable,
            "consistency_pct": round(profitable / len(fold_rows) * 100.0, 1),
            "is_avg_return_pct": round(is_avg, 2),
            "oos_avg_return_pct": round(oos_avg, 2),
            "wf_efficiency": round(efficiency, 3),
            "total_oos_return_pct": round(total_oos_return, 2),
            "verdict": _verdict(efficiency, profitable / len(fold_rows)),
        },
    }


def _verdict(efficiency: float, consistency: float) -> str:
    if efficiency >= 0.5 and consistency >= 0.75:
        return "robust"
    if efficiency >= 0.3 and consistency >= 0.5:
        return "acceptable"
    return "overfitted"
