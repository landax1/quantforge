"""Portfolio builder: combine saved backtest results.

Aligns the equity curves of several strategies on a common daily grid, applies
capital weights, and reports combined equity, drawdown, correlation and each
strategy's contribution to portfolio risk.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from botiquant.backtesting.metrics import max_drawdown


def build_portfolio(
    components: list[dict[str, Any]],
    weights: list[float] | None = None,
    initial_capital: float = 10_000.0,
) -> dict[str, Any]:
    """Combine strategies into a portfolio.

    ``components``: list of ``{"name", "equity": [...], "timestamps": [...],
    "initial_capital": float}`` taken from saved backtest results.
    Weights are capital fractions and default to equal weight.
    """
    k = len(components)
    if k < 2:
        raise ValueError("Select at least two strategies")
    if weights is None or len(weights) != k:
        weights = [1.0 / k] * k
    wsum = float(sum(weights))
    if wsum <= 0:
        raise ValueError("Weights must sum to a positive number")
    w = np.asarray([x / wsum for x in weights], dtype=np.float64)

    # normalise each curve to growth-of-1, resample daily, align on the union
    curves: list[pd.Series] = []
    for comp in components:
        eq = np.asarray(comp["equity"], dtype=np.float64)
        ts = pd.DatetimeIndex(pd.to_datetime(comp["timestamps"]))
        # TODAS LAS CURVAS EN EL MISMO RELOJ. Un perpetuo trae marcas con zona
        # horaria y un CFD no, así que combinar ADA con el S&P 500 reventaba
        # con "Cannot join tz-naive with tz-aware DatetimeIndex" —crudo, en
        # pantalla— justo en el caso para el que existe el portafolio: mezclar
        # mercados distintos (3 de septiembre de 2026). Se pasa todo a UTC y
        # se le saca la zona, que es como se guardan las velas.
        if ts.tz is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        base = float(comp.get("initial_capital") or eq[0] or 1.0)
        s = pd.Series(eq / base, index=ts)
        s = s[~s.index.duplicated(keep="last")].resample("1D").last().ffill()
        curves.append(s)

    frame = pd.concat(curves, axis=1, sort=True,
                      keys=[c.get("name", f"S{i+1}") for i, c in enumerate(components)])
    frame = frame.ffill().dropna(how="any")
    if len(frame) < 10:
        raise ValueError("Strategies share too little overlapping history")

    growth = frame.to_numpy(dtype=np.float64)
    growth = growth / growth[0]                       # rebase to common start
    combined_growth = growth @ w
    combined_equity = initial_capital * combined_growth

    rets = pd.DataFrame(growth, index=frame.index).pct_change().dropna()
    corr = rets.corr().to_numpy()
    cov = rets.cov().to_numpy()

    # Componentes SIN movimiento en la ventana compartida.
    #
    # Cada estrategia se mide sobre el tramo en el que se la encontró, y esos
    # tramos no tienen por qué coincidir: una de EURUSD 2016-2020 junto a tres
    # del S&P 2018-2026 comparten poco o nada. En la intersección, la curva de
    # la que queda afuera es una línea recta —el ffill la extiende plana—, su
    # desviación es cero y su correlación con todo lo demás es NaN.
    #
    # Eso llegaba a la pantalla como `null`, se pintaba como 0.00 y se leía
    # como "diversificación perfecta": exactamente lo contrario de lo que
    # pasa. Ahora se detecta, se nombra y no se promedia.
    quietas = [i for i in range(k) if float(rets.iloc[:, i].std(ddof=1) or 0.0) <= 1e-12]

    port_var = float(w @ cov @ w)
    if port_var > 1e-18:
        contrib = w * (cov @ w) / port_var * 100.0    # % of portfolio variance
    else:
        contrib = w * 100.0

    # el promedio se toma sólo entre los pares que EXISTEN; con menos de dos
    # componentes vivos no hay correlación media que informar
    triu = corr[np.triu_indices(k, 1)]
    validos = triu[~np.isnan(triu)]
    corr_media = round(float(validos.mean()), 3) if len(validos) else None

    dd_abs, dd_pct = max_drawdown(combined_equity)
    days = (frame.index[-1] - frame.index[0]).days or 1
    total_ret = combined_growth[-1] - 1.0
    cagr = ((1.0 + total_ret) ** (365.25 / days) - 1.0) * 100.0
    daily = pd.Series(combined_growth, index=frame.index).pct_change().dropna()
    sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(365.25)) \
        if len(daily) > 2 and daily.std(ddof=1) > 1e-12 else 0.0

    names = [str(c) for c in frame.columns]
    step = max(len(frame) // 1000, 1)
    per_strategy_curves = {
        names[i]: [round(float(v), 4) for v in growth[::step, i]] for i in range(k)
    }

    # NaN no existe en JSON: viaja como null y la pantalla decide qué decir
    matriz = [[None if np.isnan(v) else round(float(v), 3) for v in fila] for fila in corr]

    return {
        "names": names,
        "weights": [round(float(x), 4) for x in w],
        "timestamps": [str(t.date()) for t in frame.index[::step]],
        "combined_equity": [round(float(v), 2) for v in combined_equity[::step]],
        "per_strategy_growth": per_strategy_curves,
        "correlation": matriz,
        "risk_contribution_pct": [round(float(x), 2) for x in contrib],
        # el tramo que las estrategias comparten de verdad, y cuáles no se
        # mueven dentro de él: sin esto, una combinación de períodos que no se
        # tocan se ve idéntica a una diversificación perfecta
        "ventana": {"from": str(frame.index[0].date()), "to": str(frame.index[-1].date()),
                    "days": days},
        "sin_datos": [names[i] for i in quietas],
        "metrics": {
            "total_return_pct": round(total_ret * 100.0, 2),
            "cagr_pct": round(cagr, 2),
            "sharpe": round(sharpe, 3),
            "max_drawdown_pct": round(dd_pct, 2),
            "max_drawdown": round(dd_abs, 2),
            "avg_correlation": corr_media,
            "days": days,
        },
    }
