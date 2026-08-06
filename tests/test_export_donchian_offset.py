"""El canal de Donchian exportado tiene que excluir la vela evaluada.

Bug real (QF_S_001/002, agosto 2026): el EA emulaba el canal incluyendo la
vela que estaba evaluando, así que la ruptura "close[1] > máximo(high[1..n])"
era imposible por definición — el high de una vela siempre es >= su close.
Los EA compilaban, no daban ningún error y no abrían una sola operación.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantforge.core.models import Condition, Operand, RiskConfig, StrategySpec
from quantforge.indicators.library import Donchian
from quantforge.reports.mql5 import export_mql5
from quantforge.reports.pine import export_pine


def _breakout_spec() -> StrategySpec:
    return StrategySpec(
        name="Donchian breakout", direction="long",
        entry_long=[Condition(
            left=Operand(type="price", field_name="close"),
            op=">",
            right=Operand(type="indicator", name="Donchian",
                          params={"period": 20}, output="upper"))],
        entry_short=[],
        risk=RiskConfig(stop_type="atr", stop_value=2.0,
                        target_type="atr", target_value=4.0))


def test_python_channel_excludes_the_current_bar():
    """La referencia: el backtest compara contra las velas ANTERIORES."""
    n = 60
    df = pd.DataFrame({
        "open": np.linspace(100, 160, n), "high": np.linspace(101, 161, n),
        "low": np.linspace(99, 159, n), "close": np.linspace(100, 160, n),
        "volume": np.ones(n),
    }, index=pd.date_range("2024-01-01", periods=n, freq="h"))
    upper = Donchian.compute(df, period=5)["upper"]
    # en una serie que sólo sube, el canal de la vela i es el high de i-1
    assert upper[10] == df["high"].iloc[9]
    assert upper[10] < df["close"].iloc[10], "la ruptura tiene que ser posible"


def test_mql5_donchian_starts_one_bar_back():
    code = export_mql5(_breakout_spec())
    assert "iHighest(_Symbol, _Period, MODE_HIGH, period, shift + 1)" in code
    assert "iLowest(_Symbol, _Period, MODE_LOW, period, shift + 1)" in code
    # y nunca la versión que incluye la vela evaluada
    assert "MODE_HIGH, period, shift)" not in code


def test_pine_donchian_starts_one_bar_back():
    code = export_pine(_breakout_spec())
    assert "ta.highest(high[1], 20)" in code
    assert "ta.highest(high, 20)" not in code


def test_exported_breakout_is_not_impossible_by_construction():
    """Comparar el close contra un canal que lo contiene nunca se cumple."""
    for code in (export_mql5(_breakout_spec()), export_pine(_breakout_spec())):
        assert "Donchian" in code or "highest" in code
        # el canal se lee una vela más atrás que el precio que se compara
        assert "shift + 1" in code or "high[1]" in code
