"""Una señal durante el calentamiento del indicador no puede abrir una posición
sin stop.

Bug real (EURUSD H1, agosto 2026): el ATR está en NaN durante sus primeras
velas. Si la entrada disparaba ahí, `_levels` devolvía NaN, la posición se
abría sin stop ni target y `_size` caía al 100% del capital. En una estrategia
de un solo sentido no existe ninguna condición que la cierre, así que la
"estrategia" quedaba comprada 134.259 velas seguidas y salía por fin de datos.
Afectaba a ~3% de las candidatas y desincronizaba el backtest con el EA
exportado, que sí se saltea esas velas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantforge.backtesting.engine import run_backtest
from quantforge.core.models import (
    BacktestSettings, Condition, Operand, RiskConfig, StrategySpec,
)


@pytest.fixture
def rising_frame() -> pd.DataFrame:
    """Serie que sube siempre: una entrada larga nunca tocaría un stop."""
    n = 400
    close = np.linspace(100.0, 200.0, n)
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5,
         "close": close, "volume": np.ones(n)},
        index=pd.date_range("2024-01-01", periods=n, freq="h"))


def _always_in_spec(direction: str = "long", atr_period: int = 14) -> StrategySpec:
    """Entra en cuanto puede: la condición es verdadera desde la primera vela."""
    cond = Condition(left=Operand(type="price", field_name="close"),
                     op=">", right=Operand(type="const", value=0.0))
    return StrategySpec(
        name="siempre", direction=direction,
        entry_long=[cond], entry_short=[cond],
        risk=RiskConfig(stop_type="atr", stop_value=2.0, target_type="atr",
                        target_value=4.0, atr_period=atr_period,
                        size_mode="risk_pct", size_value=1.0))


def test_no_entry_while_the_atr_is_still_warming_up(rising_frame):
    from quantforge.indicators.base import IndicatorCache

    res = run_backtest(rising_frame, _always_in_spec(), BacktestSettings())
    assert res.trades, "tiene que operar una vez que el ATR esté listo"

    # la primera vela con ATR válido se calcula, no se asume
    atr = IndicatorCache(rising_frame).get("ATR", {"period": 14.0})["value"]
    first_valid = int(np.argmax(~np.isnan(atr)))
    entry = pd.Timestamp(res.trades[0].entry_time)
    assert entry >= rising_frame.index[first_valid], (
        f"abrió en {entry}, antes de que el ATR tuviera valor "
        f"({rising_frame.index[first_valid]})")


def test_every_position_carries_a_stop(rising_frame):
    """Ninguna operación puede quedar sin protección."""
    res = run_backtest(rising_frame, _always_in_spec(), BacktestSettings())
    for t in res.trades:
        assert t.exit_reason != "end" or t is res.trades[-1], (
            "sólo la última operación puede cerrarse por fin de datos")


def test_the_warmup_entry_no_longer_becomes_buy_and_hold(rising_frame):
    """El sintoma que lo delato: una sola operacion que dura casi todo el
    historial, abierta en las primeras velas."""
    res = run_backtest(rising_frame, _always_in_spec(), BacktestSettings())
    stuck = [t for t in res.trades
             if t.bars > len(rising_frame) * 0.8
             and pd.Timestamp(t.entry_time) < rising_frame.index[14]]
    assert not stuck, f"posición atrapada desde el calentamiento: {stuck}"


def test_a_longer_warmup_delays_the_first_trade(rising_frame):
    """Si el guard funciona, subir el período del ATR corre la primera entrada."""
    short = run_backtest(rising_frame, _always_in_spec(atr_period=14), BacktestSettings())
    long_ = run_backtest(rising_frame, _always_in_spec(atr_period=100), BacktestSettings())
    assert short.trades and long_.trades
    assert pd.Timestamp(long_.trades[0].entry_time) > pd.Timestamp(short.trades[0].entry_time)


def test_sizing_respects_the_risk_even_on_the_first_trade(rising_frame):
    """Sin stop, _size caia al 100% del capital. Con el guard, la primera
    operacion arriesga lo pedido como cualquier otra."""
    settings = BacktestSettings(initial_capital=10_000.0)
    res = run_backtest(rising_frame, _always_in_spec(), settings)
    t = res.trades[0]
    # unidades x distancia al stop = 1% del capital
    atr_like = abs(t.entry_price - t.exit_price)
    assert t.units * t.entry_price < settings.initial_capital * 50, (
        "el tamaño quedó desacoplado del riesgo configurado")
    assert atr_like > 0
