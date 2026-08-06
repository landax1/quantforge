"""Un EA que no opera tiene que decir por qué: fallar en silencio es el peor
modo de falla posible cuando el usuario está mirando el Strategy Tester."""

from __future__ import annotations

from quantforge.core.models import Condition, Operand, RiskConfig, StrategySpec
from quantforge.reports.mql5 import export_mql5


def _spec(**risk_kw) -> StrategySpec:
    risk = RiskConfig(stop_type="atr", stop_value=2.0, target_type="atr",
                      target_value=4.0, **risk_kw)
    return StrategySpec(
        name="EMA cross", direction="long",
        entry_long=[Condition(
            left=Operand(type="indicator", name="EMA", params={"period": 12}),
            op="cross_above",
            right=Operand(type="indicator", name="EMA", params={"period": 26}))],
        entry_short=[], risk=risk)


def test_ea_reports_symbol_specs_on_init():
    code = export_mql5(_spec())
    assert "SYMBOL_VOLUME_MIN" in code
    assert "SYMBOL_TRADE_STOPS_LEVEL" in code
    assert "InpVerbose" in code


def test_ea_reports_why_an_order_was_rejected():
    code = export_mql5(_spec())
    assert "ReportFailure" in code
    assert "trade.ResultRetcode()" in code
    assert "ACCOUNT_MARGIN_FREE" in code
    # la orden se comprueba: no se dispara y se olvida
    assert "if(trade.Buy(" in code
    assert 'else ReportFailure("BUY"' in code


def test_ea_respects_the_brokers_minimum_stop_distance():
    code = export_mql5(_spec())
    assert "ValidStops" in code
    assert "SYMBOL_TRADE_STOPS_LEVEL" in code


def test_ea_never_sends_a_zero_volume():
    code = export_mql5(_spec(size_mode="risk_pct", size_value=1.0))
    assert "if(vol <= 0.0) vol = (minLot > 0.0) ? minLot : 0.01;" in code


def test_risk_sizing_asks_the_terminal_what_a_lot_is_worth():
    """Bug real (US500, agosto 2026): calcular el valor del punto como
    tick_value/tick_size asume que el tick vale lo mismo que el punto. En un
    CFD de índice el contrato es de 100 unidades, así que el EA operó 100x
    más grande — 12.2 lotes donde tocaban 0.12 — y una sola pérdida se llevó
    la cuenta entera arriesgando el 100% en vez del 1%."""
    code = export_mql5(_spec(size_mode="risk_pct", size_value=1.0))
    assert "OrderCalcProfit(dir, _Symbol, 1.0, entry, stopPrice, lossPerLot)" in code
    # y nunca más la aproximación que se equivocaba por el tamaño del contrato
    assert "(stopDistance / tickSize) * tickValue" not in code


def test_ea_caps_the_volume_by_available_margin():
    code = export_mql5(_spec(size_mode="risk_pct", size_value=1.0))
    assert "OrderCalcMargin" in code
    assert "ACCOUNT_MARGIN_FREE" in code


def test_ea_logs_the_real_risk_of_every_order():
    code = export_mql5(_spec(size_mode="risk_pct", size_value=1.0))
    assert "ReportSize" in code
    assert "% del balance" in code
    assert 'ReportSize("BUY", true, vol, ask, sl);' in code


def test_ea_skips_bars_without_atr_instead_of_sending_broken_stops():
    code = export_mql5(_spec())
    assert "if(atr <= 0.0)" in code
