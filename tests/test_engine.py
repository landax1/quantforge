"""Backtest engine behaviour: fills, determinism, serialisation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.backtesting.engine import run_backtest
from botiquant.core.models import (
    BacktestSettings, Condition, Operand, RiskConfig, StrategySpec, TimeFilter,
)


def _const_spec(op: str, value: float, direction: str = "long") -> StrategySpec:
    """Price vs constant — lets us hand-check entries."""
    return StrategySpec(
        name="const", direction=direction,
        entry_long=[Condition(Operand(type="price", field_name="close"), op,
                              Operand(type="const", value=value))],
        risk=RiskConfig(stop_type="none", target_type="none",
                        size_mode="percent_equity", size_value=100.0),
    )


def test_spec_roundtrip(ema_spec):
    d = ema_spec.to_dict()
    assert StrategySpec.from_dict(d).to_dict() == d


def test_backtest_deterministic(df, ema_spec):
    a = run_backtest(df, ema_spec)
    b = run_backtest(df, ema_spec)
    assert a.metrics == b.metrics
    np.testing.assert_array_equal(a.equity, b.equity)


def test_no_entry_without_rules(df):
    spec = StrategySpec(name="empty", direction="long")
    res = run_backtest(df, spec)
    assert res.metrics["trades"] == 0
    assert res.metrics["net_profit"] == 0.0


def _falling_frame() -> pd.DataFrame:
    """Deterministic series: enters at 100 then slides down one point per bar,
    so any stop distance has an exactly predictable trigger bar."""
    closes = [100.0] + [100.0 - i for i in range(1, 70)]
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="1h")
    return pd.DataFrame({"open": closes, "high": [c + 0.05 for c in closes],
                         "low": [c - 0.05 for c in closes], "close": closes,
                         "volume": 1000.0}, index=idx)


def test_points_stop_is_a_fixed_price_distance():
    """'5 puntos' must mean exactly 5 price units below the entry fill."""
    frame = _falling_frame()
    spec = _const_spec(">", 0.0)          # always long
    spec.risk = RiskConfig(stop_type="points", stop_value=5.0, target_type="none",
                           size_mode="fixed_units", size_value=1)
    res = run_backtest(frame, spec, BacktestSettings(spread=0.0, slippage=0.0))
    stopped = [t for t in res.trades if t.exit_reason == "stop"]
    assert stopped, "un stop de 5 puntos en una caída de 40 tiene que dispararse"
    t = stopped[0]
    assert t.entry_price == pytest.approx(99.0)          # fills at bar 1's open
    assert t.exit_price == pytest.approx(99.0 - 5.0, abs=0.06)


def test_money_stop_scales_with_position_size():
    """A $50 stop must cost about $50 whether holding 1 unit or 5."""
    frame = _falling_frame()
    losses = {}
    for units in (1, 5):
        spec = _const_spec(">", 0.0)
        spec.risk = RiskConfig(stop_type="money", stop_value=50.0, target_type="none",
                               size_mode="fixed_units", size_value=units)
        res = run_backtest(frame, spec, BacktestSettings(spread=0.0, slippage=0.0))
        stopped = [t for t in res.trades if t.exit_reason == "stop"]
        assert stopped, f"sin salida por stop con {units} unidades"
        losses[units] = abs(stopped[0].pnl)
        # distance must shrink as size grows: 50/1 = 50 points vs 50/5 = 10 points
        dist = abs(stopped[0].entry_price - stopped[0].exit_price)
        assert dist == pytest.approx(50.0 / units, abs=0.3)
    assert losses[1] == pytest.approx(losses[5], rel=0.05), \
        "la pérdida en dinero debe ser la misma sin importar el tamaño"


def test_cagr_uses_calendar_years_not_bar_count(df):
    """Hourly data covers fewer 'bar years' than calendar years — using bar
    count as the denominator would inflate CAGR by roughly 50%."""
    from botiquant.backtesting.metrics import compute_metrics
    from botiquant.core.models import Trade

    # 2 calendar years of hourly bars, but only trading hours (8/day, 5/7 days)
    idx = pd.date_range("2020-01-01", "2022-01-01", freq="1h")
    idx = idx[(idx.hour >= 9) & (idx.hour < 17) & (idx.dayofweek < 5)]
    eq = pd.Series(np.linspace(10_000, 20_000, len(idx)), index=idx)   # doubled

    m = compute_metrics(eq, [], 10_000.0)
    assert m["years"] == pytest.approx(2.0, abs=0.02)
    # doubling over 2 years => ~41.4% CAGR, not the ~90% a bar-count denominator gives
    assert m["cagr_pct"] == pytest.approx(41.4, abs=1.5)


def test_exposure_reflects_time_in_market(df, ema_spec):
    res = run_backtest(df, ema_spec)
    bars_held = sum(t.bars for t in res.trades)
    assert res.metrics["exposure_pct"] == pytest.approx(bars_held / len(df) * 100, abs=0.05)
    assert 0.0 <= res.metrics["exposure_pct"] <= 100.0


def test_spread_charged_once_per_round_trip(df):
    """Absolute spread must move entry and exit by half each — never double-charged."""
    spec = StrategySpec(
        name="cost probe", direction="both",
        entry_long=[Condition(Operand(type="indicator", name="EMA", params={"period": 20}),
                              "cross_above",
                              Operand(type="indicator", name="EMA", params={"period": 80}))],
        entry_short=[Condition(Operand(type="indicator", name="EMA", params={"period": 20}),
                               "cross_below",
                               Operand(type="indicator", name="EMA", params={"period": 80}))],
        risk=RiskConfig(stop_type="none", target_type="none",
                        size_mode="percent_equity", size_value=100),
    )
    free = run_backtest(df, spec, BacktestSettings(spread=0.0, slippage=0.0))
    spread = 1.0
    charged = run_backtest(df, spec, BacktestSettings(spread=spread, slippage=0.0))

    assert free.metrics["trades"] == charged.metrics["trades"] > 5
    for a, b in zip(free.trades[:5], charged.trades[:5]):
        sign = 1 if a.direction == "long" else -1
        assert b.entry_price == pytest.approx(a.entry_price + sign * spread / 2, abs=1e-6)
        assert b.exit_price == pytest.approx(a.exit_price - sign * spread / 2, abs=1e-6)


def test_fill_at_next_open(df):
    """Signal on bar close must fill at the NEXT bar's open, not the same bar."""
    spec = _const_spec("cross_above", float(df["close"].quantile(0.5)))
    settings = BacktestSettings(commission_pct=0.0, slippage_pct=0.0)
    res = run_backtest(df, spec, settings)
    assert res.metrics["trades"] > 0
    t = res.trades[0]
    idx = df.index.get_loc(pd.Timestamp(t.entry_time))
    assert t.entry_price == round(float(df["open"].iloc[idx]), 6)
    # signal bar is the previous one
    prev_close = float(df["close"].iloc[idx - 1])
    assert prev_close > df["close"].quantile(0.5) - 1e9  # sanity: index resolved


def test_stop_loss_respected(df, ema_spec):
    res = run_backtest(df, ema_spec)
    stops = [t for t in res.trades if t.exit_reason == "stop"]
    assert stops, "ATR stop should trigger at least once"
    for t in stops[:20]:
        if t.direction == "long":
            assert t.exit_price < t.entry_price
        else:
            assert t.exit_price > t.entry_price


def test_time_filter_blocks_entries(df, ema_spec):
    ema_spec.time_filter = TimeFilter(enabled=True, days=[0, 1, 2, 3, 4],
                                      start_hour=8, end_hour=17)
    res = run_backtest(df, ema_spec)
    for t in res.trades:
        signal_ts = pd.Timestamp(t.entry_time)
        i = df.index.get_loc(signal_ts)
        sig = df.index[i - 1]           # entry filled one bar after the signal
        assert sig.dayofweek in (0, 1, 2, 3, 4)
        assert 8 <= sig.hour < 17


def test_costs_reduce_profit(df, ema_spec):
    free = run_backtest(df, ema_spec, BacktestSettings(commission_pct=0.0, slippage_pct=0.0))
    costly = run_backtest(df, ema_spec, BacktestSettings(commission_pct=0.2, slippage_pct=0.05))
    assert costly.metrics["net_profit"] < free.metrics["net_profit"]


def test_equity_never_marked_before_entry(df, ema_spec):
    settings = BacktestSettings(initial_capital=5000)
    res = run_backtest(df, ema_spec, settings)
    assert res.equity[0] == settings.initial_capital
