"""Las marcas de tiempo del backtest son opcionales, y no cambian los números.

El minero corre miles de backtests y sólo mira métricas: convertir a texto
las 35.000 marcas de cada candidata —y la fecha de cada operación cerrada—
costaba más que el backtest entero. Sin marcas tiene que dar EXACTAMENTE lo
mismo, salvo las marcas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from botiquant.backtesting.engine import run_backtest
from botiquant.core.models import BacktestSettings, StrategySpec


def _df(n=3000, tz="UTC"):
    t = pd.date_range("2024-01-01", periods=n, freq="1h", tz=tz)
    x = np.arange(n)
    c = 100 + np.sin(x / 15) * 4 + x * 0.002
    return pd.DataFrame({"open": c, "high": c + 0.8, "low": c - 0.8, "close": c,
                         "volume": np.full(n, 10.0)}, index=t)


def _spec():
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return StrategySpec.from_dict({
        "name": "t", "direction": "both",
        "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
        "entry_short": [{"left": ema(5), "op": "cross_below", "right": ema(20)}],
        "risk": {"size_mode": "risk_pct", "size_value": 1.0, "stop_type": "atr",
                 "stop_value": 2.0, "target_type": "atr", "target_value": 3.0,
                 "atr_period": 14}})


def test_sin_marcas_da_los_mismos_numeros():
    df, spec, s = _df(), _spec(), BacktestSettings()
    con = run_backtest(df, spec, s)
    sin = run_backtest(df, spec, s, con_marcas=False)
    assert len(con.trades) > 20
    assert con.metrics == sin.metrics
    assert np.array_equal(con.equity, sin.equity)
    assert [t.pnl for t in con.trades] == [t.pnl for t in sin.trades]
    assert sin.timestamps == [] and all(t.entry_time == "" for t in sin.trades)


def test_con_marcas_el_texto_es_el_de_siempre():
    """El texto vectorizado tiene que ser el mismo que daba `str()` una por
    una: hay reportes y exportaciones que lo leen."""
    df, spec = _df(), _spec()
    con = run_backtest(df, spec, BacktestSettings())
    assert con.timestamps[0] == str(df.index[0])
    assert con.timestamps[-1] == str(df.index[-1])
    t0 = con.trades[0]
    assert t0.entry_time in con.timestamps and t0.exit_time in con.timestamps
    assert t0.entry_time == str(df.index[con.timestamps.index(t0.entry_time)])


def test_tambien_sin_zona_horaria():
    df = _df(tz=None)
    con = run_backtest(df, _spec(), BacktestSettings())
    assert con.timestamps[0] == str(df.index[0]) == "2024-01-01 00:00:00"
