"""Walk-forward analysis.

Rolls train/test windows across the data; each fold re-optimizes the strategy
on its training slice and evaluates the tuned parameters out-of-sample. The
stitched OOS equity and walk-forward efficiency show whether an edge survives
outside the data it was fitted on.
"""

from __future__ import annotations

from dataclasses import replace
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
        # LOS MISMOS COSTOS QUE ADENTRO. El tramo de fuera se corría con un
        # objeto nuevo que sólo copiaba las dos comisiones porcentuales: se
        # perdían el spread, el deslizamiento en unidades de precio y el
        # funding del perpetuo. O sea que la prueba medía el tramo de fuera
        # más barato que el de dentro, y la eficiencia salía inflada por
        # construcción (encontrado el 3 de septiembre de 2026). Lo único que
        # cambia entre tramos es el capital, que se compone.
        fold_settings = replace(settings, initial_capital=capital)
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

    # La eficiencia se calcula sobre la MEDIANA y no sobre el promedio.
    #
    # Con ventanas ancladas, el primer tramo de entrenamiento puede ser mucho
    # más largo que los siguientes, y sobre un mercado alcista devuelve un
    # rendimiento in-sample enorme (+70% contra +13% de los otros tres). El
    # promedio se lo lleva puesto: la eficiencia caía a 0.24 y la estrategia se
    # declaraba sobreajustada aunque hubiera ganado plata en los CUATRO tramos
    # fuera de muestra. La mediana describe el tramo típico, que es lo que la
    # pregunta quiere saber.
    is_avg = float(np.median([f["is_net_profit_pct"] for f in fold_rows]))
    oos_avg = float(np.median([f["oos_net_profit_pct"] for f in fold_rows]))
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
    """Las dos preguntas, y cuál manda cuando se contradicen.

    ``consistency`` es en cuántos tramos fuera de muestra ganó plata;
    ``efficiency``, cuánto del rendimiento ajustado sobrevivió fuera.

    Cuando se contradicen manda la consistencia, y no es una preferencia: una
    estrategia que ganó en TODOS los tramos que nunca vio aguantó, punto — que
    haya ganado menos de lo que prometía el ajuste es lo normal, porque el
    ajuste siempre es optimista por construcción. Llamar "sobreajustada" a algo
    que ganó cuatro veces de cuatro sobre datos nuevos es decirle al usuario
    que tire lo único que le funcionó.

    Al revés no vale: una eficiencia alta con consistencia baja significa que
    un tramo afortunado tapó a los demás, y eso sí es una advertencia.
    """
    # PISO DE EFICIENCIA, gane donde gane. Una estrategia ganó en los cuatro
    # tramos con eficiencia 0,03 —conservó el TRES por ciento de lo que hacía
    # adentro— y salía "aguantó a medias". Ganar por un pelo en cada tramo
    # perdiendo el 97 % de la ventaja no es aguantar: es que el ajuste
    # describía el pasado y afuera quedó casi nada (3 de septiembre de 2026).
    if efficiency < 0.1:
        return "overfitted"
    if consistency >= 0.99:
        # ganó en todos: como mínimo aguanta, y aguanta bien si además
        # conservó buena parte de lo que prometía
        return "robust" if efficiency >= 0.4 else "acceptable"
    if efficiency >= 0.5 and consistency >= 0.75:
        return "robust"
    if efficiency >= 0.3 and consistency >= 0.5:
        return "acceptable"
    # Ganar en tres de cuatro con eficiencia 0,29 salía "no pasó" mientras
    # dos de cuatro con 0,30 salía "a medias": la consistencia alta compensa
    # una eficiencia algo menor (3 de septiembre de 2026).
    if efficiency >= 0.2 and consistency >= 0.75:
        return "acceptable"
    return "overfitted"
