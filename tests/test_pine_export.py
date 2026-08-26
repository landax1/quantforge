"""El script de TradingView tiene que reflejar la MISMA estrategia minada."""

from __future__ import annotations

from botiquant.core.models import Condition, Operand, RiskConfig, StrategySpec
from botiquant.reports.pine import export_pine


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
    # los niveles cuelgan del precio real de entrada, no del cierre de la vela
    # de señal: es lo que hace el motor y lo que ve el usuario en el inspector
    #
    # Y del ATR DE LA ENTRADA, no del de cada vela. Antes decía `atrRisk`, que
    # se recalcula barra a barra: el stop y el objetivo se movían solos con la
    # volatilidad mientras la operación estaba abierta, y el backtest los fija
    # al entrar. Medido, esa diferencia sola separaba los dos resultados.
    assert "strategy.position_avg_price - InpStopMult * atrEntrada" in code
    assert "strategy.position_avg_price + InpTargetMult * atrEntrada" in code
    assert "var float atrEntrada = na" in code, (
        "el ATR de entrada tiene que estar declarado como `var` para que "
        "sobreviva de una vela a la otra")


def test_pine_fixed_lots_and_risk_pct_size_differently():
    fixed = export_pine(_spec(size_mode="fixed_units", size_value=0.1))
    assert "InpContracts" in fixed
    assert "InpRiskPct" not in fixed

    pct = export_pine(_spec(size_mode="risk_pct", size_value=1.0))
    assert "InpRiskPct" in pct
    assert "strategy.equity * InpRiskPct / 100.0" in pct


def test_pine_never_orders_a_fractional_size_that_rounds_to_zero():
    """0.1 contratos se redondea a 0 en instrumentos sin fracciones y la
    estrategia no abre nada. El default tiene que ser % de capital."""
    code = export_pine(_spec(size_mode="fixed_units", size_value=0.1))
    assert "default_qty_type=strategy.percent_of_equity" in code
    assert "math.max(InpContracts, 1)" in code
    # el tamaño exacto queda como opción explícita, no como default
    assert 'InpUseFixedQty = input.bool(false' in code
    assert "qty      = InpUseFixedQty ? qtyFixed : na" in code


def test_pine_plots_the_signals_for_diagnosis():
    """Si no hay operaciones hay que poder ver si al menos hubo señal."""
    code = export_pine(_spec())
    assert "plotshape(goLong" in code
    assert "plotshape(goShort" in code


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
