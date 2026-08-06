"""Salidas evolucionables: trailing y salida por tiempo como genes.

Hasta acá todas las candidatas salían igual —stop y target fijos— y eso dejaba
afuera familias enteras de estrategias: las que necesitan dejar correr la
ganancia y las que se mueren si aguantan demasiado. Cuál conviene depende de
las entradas de cada estrategia, así que es un gen y no configuración.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantforge.backtesting.engine import run_backtest
from quantforge.core.models import (
    BacktestSettings, Condition, Operand, RiskConfig, StrategySpec,
)
from quantforge.generator.generator import Genome, build_spec, random_genome
from quantforge.reports.mql5 import export_mql5
from quantforge.reports.pine import export_pine

DRV = ["ema_cross", "price_ema", "donchian_break"]
FLT = ["ema_trend_filter"]


@pytest.fixture
def subida_y_caida() -> pd.DataFrame:
    """Sube fuerte y después se desploma: el trailing tiene que salvar la
    ganancia que un target lejano dejaría escapar."""
    sube = np.linspace(100.0, 160.0, 160)
    baja = np.linspace(160.0, 95.0, 140)
    close = np.concatenate([sube, baja])
    return pd.DataFrame(
        {"open": close, "high": close + 0.4, "low": close - 0.4,
         "close": close, "volume": np.ones(len(close))},
        index=pd.date_range("2024-01-01", periods=len(close), freq="h"))


def _spec(**risk_kw) -> StrategySpec:
    cond = Condition(left=Operand(type="price", field_name="close"),
                     op=">", right=Operand(type="const", value=0.0))
    risk = RiskConfig(stop_type="atr", stop_value=3.0, target_type="atr",
                      target_value=30.0, atr_period=14,
                      size_mode="fixed_units", size_value=1.0, **risk_kw)
    return StrategySpec(name="siempre", direction="long", entry_long=[cond],
                        entry_short=[], risk=risk)


def test_trailing_protects_a_gain_that_a_far_target_would_lose(subida_y_caida):
    sin = run_backtest(subida_y_caida, _spec(), BacktestSettings())
    con = run_backtest(subida_y_caida, _spec(trail_atr=1.5), BacktestSettings())
    assert con.metrics["net_profit"] > sin.metrics["net_profit"], (
        "el trailing tiene que cerrar cerca del máximo en vez de devolverlo todo")


def test_the_trailing_stop_never_moves_backwards(subida_y_caida):
    res = run_backtest(subida_y_caida, _spec(trail_atr=1.0), BacktestSettings())
    salidas = [t for t in res.trades if t.exit_reason == "stop"]
    assert salidas, "con trailing tiene que haber salidas por stop"
    for t in salidas:
        # nunca peor que el stop inicial: el trailing sólo aprieta
        assert t.exit_price > t.entry_price - 3.0 * 5.0


def test_the_time_exit_closes_the_trade(subida_y_caida):
    res = run_backtest(subida_y_caida, _spec(max_bars_in_trade=10), BacktestSettings())
    porTiempo = [t for t in res.trades if t.exit_reason == "time"]
    assert porTiempo, "tiene que haber cierres por tiempo"
    for t in porTiempo:
        assert t.bars <= 10


def test_trailing_does_not_peek_inside_the_bar(subida_y_caida):
    """El trailing se actualiza al CIERRE de la vela. Si se moviera antes de
    comprobar el stop, usaría el máximo de la misma vela para decidir si el
    stop de esa vela se tocó — mirar el futuro dentro de la barra."""
    res = run_backtest(subida_y_caida, _spec(trail_atr=1.0), BacktestSettings())
    for t in res.trades:
        if t.exit_reason == "end":
            continue          # cierre forzado por fin de datos, puede durar 0
        assert t.bars >= 1, "ninguna operación puede abrir y cerrar en la misma vela"


def test_the_genome_carries_the_new_exits():
    g = random_genome(DRV, FLT, 1, np.random.default_rng(7))
    assert hasattr(g, "trail_mult") and hasattr(g, "max_bars")
    # dos genomas que sólo difieren en el trailing son candidatas distintas
    a = Genome("ema_cross", (), {}, stop_mult=2.0, trail_mult=0.0, max_bars=0)
    b = Genome("ema_cross", (), {}, stop_mult=2.0, trail_mult=2.0, max_bars=0)
    c = Genome("ema_cross", (), {}, stop_mult=2.0, trail_mult=0.0, max_bars=24)
    assert len({a.key(), b.key(), c.key()}) == 3


def test_the_spec_receives_the_evolved_exits():
    g = Genome("ema_cross", (), {"ema_cross": {"fast": 12, "slow": 26}},
               stop_mult=2.5, trail_mult=1.5, max_bars=48)
    spec = build_spec(g, direction="long", risk=RiskConfig(reward_ratio=2.0))
    assert spec.risk.stop_value == 2.5
    assert spec.risk.target_value == 5.0
    assert spec.risk.trail_atr == 1.5
    assert spec.risk.max_bars_in_trade == 48


def test_both_exporters_carry_the_evolved_exits():
    spec = _spec(trail_atr=1.5, max_bars_in_trade=48)

    mql = export_mql5(spec)
    assert "InpTrailATR    = 1.5" in mql
    assert "InpMaxBars     = 48" in mql
    assert "ManageOpenPosition" in mql
    # el trailing usa el ATR de la entrada, como el backtest
    assert "g_trailDist = (InpTrailATR > 0.0) ? InpTrailATR * atr : 0.0;" in mql

    pine = export_pine(spec)
    assert 'InpTrailATR   = input.float(1.5' in pine
    assert 'InpMaxBars    = input.int(48' in pine
    assert "trailDist := InpTrailATR > 0 ? InpTrailATR * atrRisk : na" in pine
    assert "strategy.close_all" in pine


def test_exits_stay_off_when_the_genome_says_so():
    """El 0 es un valor válido: la búsqueda puede seguir encontrando la forma
    simple de siempre, sin trailing ni límite de tiempo."""
    g = Genome("ema_cross", (), {}, stop_mult=2.0, trail_mult=0.0, max_bars=0)
    spec = build_spec(g, direction="long", risk=RiskConfig())
    assert spec.risk.trail_atr == 0.0
    assert spec.risk.max_bars_in_trade == 0
