"""Event-accurate backtest engine on top of vectorised signals.

Signals are computed vectorised (numpy) for the whole frame; the fill loop then
walks the bars once. Execution model:

* a signal on bar *i-1* fills at the **open of bar i** (no lookahead);
* stops/targets are checked intrabar against high/low — if both could fill in
  the same bar the stop is assumed to fill first (conservative);
* slippage moves fills against the trade, commission is charged per side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from botiquant.backtesting.metrics import compute_metrics
from botiquant.core.models import BacktestSettings, StrategySpec, Trade
from botiquant.indicators.base import IndicatorCache
from botiquant.strategies.rules import EvalContext, eval_conditions, time_filter_mask


@dataclass(slots=True)
class BacktestResult:
    """Everything a backtest produces, JSON-serialisable via ``to_dict``."""

    metrics: dict[str, float]
    trades: list[Trade]
    equity: np.ndarray
    timestamps: list[str]
    monthly_returns: list[dict[str, Any]]
    strategy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, max_points: int = 2000) -> dict[str, Any]:
        # downsample the equity curve for transport; metrics use the full curve
        n = len(self.equity)
        idx = np.linspace(0, n - 1, min(n, max_points)).astype(int) if n else np.array([], dtype=int)
        return {
            "metrics": self.metrics,
            "trades": [t.to_dict() for t in self.trades],
            "equity": [round(float(self.equity[i]), 2) for i in idx],
            "timestamps": [self.timestamps[i] for i in idx],
            "monthly_returns": self.monthly_returns,
            "strategy": self.strategy,
        }


def run_backtest(
    df: pd.DataFrame,
    spec: StrategySpec,
    settings: BacktestSettings | None = None,
    cache: IndicatorCache | None = None,
) -> BacktestResult:
    """Run one backtest of ``spec`` over ``df`` (UTC DatetimeIndex OHLCV)."""
    settings = settings or BacktestSettings()
    ctx = EvalContext(df, cache)
    n = ctx.n

    want_long = spec.direction in ("long", "both") and bool(spec.entry_long)
    want_short = spec.direction in ("short", "both") and bool(spec.entry_short)

    entry_long = eval_conditions(spec.entry_long, ctx) if want_long else np.zeros(n, bool)
    exit_long = eval_conditions(spec.exit_long, ctx) if spec.exit_long else np.zeros(n, bool)
    entry_short = eval_conditions(spec.entry_short, ctx) if want_short else np.zeros(n, bool)
    exit_short = eval_conditions(spec.exit_short, ctx) if spec.exit_short else np.zeros(n, bool)

    tmask = time_filter_mask(spec.time_filter, df.index)
    entry_long &= tmask
    entry_short &= tmask

    risk = spec.risk
    atr = None
    if risk.stop_type == "atr" or risk.target_type == "atr":
        atr = ctx.cache.get("ATR", {"period": float(risk.atr_period)})["value"]

    o = df["open"].to_numpy(dtype=np.float64)
    h = df["high"].to_numpy(dtype=np.float64)
    l = df["low"].to_numpy(dtype=np.float64)
    c = df["close"].to_numpy(dtype=np.float64)

    slip = settings.slippage_pct / 100.0
    comm = settings.commission_pct / 100.0
    # absolute costs in price units: half the spread plus slippage per side,
    # so a round trip pays the full spread exactly once
    abs_slip = settings.spread / 2.0 + settings.slippage

    equity = np.empty(n, dtype=np.float64)
    cash = settings.initial_capital
    pos = 0            # +1 long, -1 short, 0 flat
    units = 0.0
    entry_px = 0.0
    stop_px = np.nan
    target_px = np.nan
    entry_i = 0
    trail_dist = 0.0   # distancia del trailing, fijada al entrar
    best_px = 0.0      # extremo a favor alcanzado dentro de la operación
    trades: list[Trade] = []

    def _distance(kind: str, value: float, i: int, px: float) -> float:
        """Price distance for a stop/target level, or NaN when disabled."""
        if kind == "atr":
            a = atr[i] if atr is not None else np.nan
            return value * a if not np.isnan(a) else np.nan
        if kind == "percent":
            return px * value / 100.0
        if kind == "points":
            return value
        return np.nan          # "none", or "money" which needs the size first

    def _levels(i: int, direction: int, px: float) -> tuple[float, float]:
        d_sl = _distance(risk.stop_type, risk.stop_value, i, px)
        d_tp = _distance(risk.target_type, risk.target_value, i, px)
        sl = px - direction * d_sl if not np.isnan(d_sl) else np.nan
        tp = px + direction * d_tp if not np.isnan(d_tp) else np.nan
        return sl, tp

    def _money_levels(direction: int, px: float, sz: float) -> tuple[float, float]:
        """Money-denominated stop/target, resolvable only once size is known."""
        sl = tp = np.nan
        if sz > 1e-12:
            if risk.stop_type == "money":
                sl = px - direction * (risk.stop_value / sz)
            if risk.target_type == "money":
                tp = px + direction * (risk.target_value / sz)
        return sl, tp

    def _size(px: float, sl: float, eq: float) -> float:
        if risk.size_mode == "fixed_units":
            return max(risk.size_value, 0.0)
        if risk.size_mode == "risk_pct" and not np.isnan(sl) and abs(px - sl) > 1e-12:
            return (eq * risk.size_value / 100.0) / abs(px - sl)
        # percent_equity, or risk_pct without a stop to size against
        pct = risk.size_value if risk.size_mode == "percent_equity" else 100.0
        return (eq * pct / 100.0) / px

    def _close_trade(i: int, px: float, reason: str) -> None:
        nonlocal cash, pos, units
        fill = px * (1.0 - pos * slip) - pos * abs_slip
        pnl = pos * units * (fill - entry_px) - comm * units * fill
        cash += pnl
        trades.append(Trade(
            entry_time=str(df.index[entry_i]), exit_time=str(df.index[i]),
            direction="long" if pos > 0 else "short",
            entry_price=round(entry_px, 6), exit_price=round(fill, 6),
            units=round(units, 6), pnl=round(pnl, 2),
            pnl_pct=round(100.0 * pos * (fill - entry_px) / entry_px, 4),
            bars=i - entry_i, exit_reason=reason,
        ))
        pos, units = 0, 0.0

    for i in range(n):
        if pos != 0:
            # 1) intrabar stop/target (stop first if both touch)
            if pos > 0:
                if not np.isnan(stop_px) and l[i] <= stop_px:
                    _close_trade(i, min(stop_px, o[i]), "stop")
                elif not np.isnan(target_px) and h[i] >= target_px:
                    _close_trade(i, max(target_px, o[i]), "target")
            else:
                if not np.isnan(stop_px) and h[i] >= stop_px:
                    _close_trade(i, max(stop_px, o[i]), "stop")
                elif not np.isnan(target_px) and l[i] <= target_px:
                    _close_trade(i, min(target_px, o[i]), "target")
        if pos != 0 and i > 0:
            # 2) signal-based exit / reversal, filled at this bar's open
            sig_exit = (pos > 0 and (exit_long[i - 1] or entry_short[i - 1])) or \
                       (pos < 0 and (exit_short[i - 1] or entry_long[i - 1]))
            timed_out = risk.max_bars_in_trade > 0 and (i - entry_i) >= risk.max_bars_in_trade
            if sig_exit or timed_out:
                _close_trade(i, o[i], "signal" if sig_exit else "time")
        if pos == 0 and i > 0 and cash > 0:
            # 3) entries, filled at this bar's open
            direction = 1 if entry_long[i - 1] else (-1 if entry_short[i - 1] else 0)
            if direction != 0:
                fill = o[i] * (1.0 + direction * slip) + direction * abs_slip
                sl, tp = _levels(i, direction, fill)
                # Un stop pedido que todavía no se puede calcular —el ATR está
                # en su período de calentamiento— no puede terminar en una
                # entrada sin protección: quedaría dimensionada al 100% del
                # capital y, en una estrategia de un solo sentido, sin ninguna
                # condición que la cierre. Medido en EURUSD H1: se convertía en
                # una única operación de 134.259 velas. El EA exportado tampoco
                # entra en esa situación, así que además desincronizaba el
                # backtest con lo que después corre en MetaTrader.
                unhedged = risk.stop_type not in ("none", "money") and np.isnan(sl)
                sz = 0.0 if unhedged else _size(fill, sl, cash)
                if sz > 0:
                    m_sl, m_tp = _money_levels(direction, fill, sz)
                    if not np.isnan(m_sl):
                        sl = m_sl
                    if not np.isnan(m_tp):
                        tp = m_tp
                    pos, units, entry_px, entry_i = direction, sz, fill, i
                    stop_px, target_px = sl, tp
                    # el trailing se mide en la volatilidad del momento de
                    # entrar y no cambia durante la operación: así la salida es
                    # reproducible y el EA exportado puede calcular lo mismo
                    a = atr[i] if atr is not None else np.nan
                    trail_dist = (risk.trail_atr * a
                                  if risk.trail_atr > 0 and not np.isnan(a) else 0.0)
                    best_px = fill
                    cash -= comm * units * fill

        # 4) el trailing se actualiza al CIERRE de la barra, después de haber
        #    comprobado el stop con el nivel que regía al abrirla. Moverlo antes
        #    sería usar el máximo de esta misma vela para decidir si el stop de
        #    esta vela se tocó, es decir, mirar el futuro dentro de la barra.
        if pos != 0 and trail_dist > 0.0:
            if pos > 0:
                best_px = max(best_px, h[i])
                nuevo = best_px - trail_dist
                stop_px = nuevo if np.isnan(stop_px) else max(stop_px, nuevo)
            else:
                best_px = min(best_px, l[i])
                nuevo = best_px + trail_dist
                stop_px = nuevo if np.isnan(stop_px) else min(stop_px, nuevo)

        equity[i] = cash + (pos * units * (c[i] - entry_px) if pos != 0 else 0.0)

    if pos != 0:
        _close_trade(n - 1, c[n - 1], "end")
        equity[n - 1] = cash

    timestamps = [str(t) for t in df.index]
    eq_series = pd.Series(equity, index=df.index)
    metrics = compute_metrics(eq_series, trades, settings.initial_capital)
    monthly = _monthly_returns(eq_series, settings.initial_capital)
    return BacktestResult(
        metrics=metrics, trades=trades, equity=equity,
        timestamps=timestamps, monthly_returns=monthly,
        strategy=spec.to_dict(),
    )


def _monthly_returns(eq: pd.Series, initial: float) -> list[dict[str, Any]]:
    if eq.empty:
        return []
    monthly_last = eq.resample("ME").last()
    prev = monthly_last.shift(1)
    if len(prev) > 0:
        prev.iloc[0] = initial
    rets = (monthly_last / prev - 1.0) * 100.0
    return [
        {"year": int(ts.year), "month": int(ts.month), "return_pct": round(float(r), 2)}
        for ts, r in rets.items() if not np.isnan(r)
    ]
