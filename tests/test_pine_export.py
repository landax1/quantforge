"""El script de TradingView tiene que reflejar la MISMA estrategia minada."""

from __future__ import annotations

from quantforge.core.models import Condition, Operand, RiskConfig, StrategySpec
from quantforge.reports.pine import export_pine


def _spec(**risk_kw) -> StrategySpec:
    risk = RiskConfig(stop_type="atr", stop_value=2.5, target_type="atr",
                      target_value=5.0, **risk_kw)
    return StrategySpec(
        name="EMA cross",
        direction="long",
        entry_long=[Condition(
            left=Operand(type="indicator", name="EMA", params={"period": 12}),
            op="cross_above",
            right=Operand(type="indicator", name="EMA", params={"period": 26}))],
        entry_short=[],
        risk=risk,
    )


def test_pine_has_version_and_strategy_call():
    code = export_pine(_spec(), name="QF S-001")
    assert "//@version=5" in code
    assert 'strategy("QF S-001"' in code
    # sin repintado: process_orders_on_close y velas cerradas
    assert "process_orders_on_close=true" in code
    assert "calc_on_every_tick=false" in code


def test_pine_translates_the_crossover_on_closed_bars():
    code = export_pine(_spec())
    # cruce = comparación en [2] y en [1], nunca la vela en curso
    assert "ta.ema(close, 12))[1]" in code
    assert "ta.ema(close, 26))[2]" in code
    assert "[0]" not in code, "no puede leer la vela en curso"


def test_pine_exit_uses_the_evolved_atr_multiples():
    code = export_pine(_spec())
    assert 'InpStopMult   = input.float(2.5' in code
    assert 'InpTargetMult = input.float(5' in code
    assert "close - InpStopMult * atrRisk" in code
    assert "close + InpTargetMult * atrRisk" in code


def test_pine_fixed_lots_and_risk_pct_size_differently():
    fixed = export_pine(_spec(size_mode="fixed_units", size_value=0.1))
    assert "InpContracts" in fixed
    assert "qty = InpContracts" in fixed
    assert "InpRiskPct" not in fixed

    pct = export_pine(_spec(size_mode="risk_pct", size_value=1.0))
    assert "InpRiskPct" in pct
    assert "strategy.equity * InpRiskPct / 100.0" in pct


def test_pine_flags_indicators_it_cannot_translate():
    spec = _spec()
    spec.entry_long = [Condition(
        left=Operand(type="indicator", name="NoExiste", params={"period": 5}),
        op=">", right=Operand(type="const", value=1))]
    code = export_pine(spec)
    assert "NO SOPORTADO" in code
    assert "¡ATENCIÓN!" in code


def test_pine_short_only_disables_longs():
    spec = _spec()
    spec.direction = "short"
    spec.entry_short = list(spec.entry_long)
    spec.entry_long = []
    code = export_pine(spec)
    assert 'InpAllowLong  = input.bool(false' in code
    assert 'InpAllowShort = input.bool(true' in code
