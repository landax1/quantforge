"""MQL5 export: valid structure, real indicator handles, honest warnings."""

from __future__ import annotations

from botiquant.core.models import Condition, Operand, RiskConfig, StrategySpec
from botiquant.reports.mql5 import export_mql5


def _spec(entry, direction="long", risk=None):
    return StrategySpec(name="t", direction=direction, entry_long=entry, entry_short=[],
                        risk=risk or RiskConfig())


def test_export_has_valid_ea_skeleton():
    ema = lambda p: Operand(type="indicator", name="EMA", params={"period": p})
    code = export_mql5(_spec([Condition(ema(20), "cross_above", ema(80))]), ea_name="BQ_T")
    for token in ("#include <Trade\\Trade.mqh>", "int OnInit()", "void OnTick()",
                  "void OnDeinit", "CTrade   trade;", "iMA(_Symbol, _Period, 20"):
        assert token in code, f"falta {token}"
    # balanced braces => the file at least parses structurally
    assert code.count("{") == code.count("}")
    # crossover must compare previous and current bar, never bar 0 (repainting)
    assert "iClose(_Symbol, _Period, 0)" not in code


def test_bollinger_and_volume_helpers_emitted():
    boll = Operand(type="indicator", name="Bollinger", output="lower",
                   params={"period": 20, "mult": 2.0})
    vol = Operand(type="price", field_name="volume")
    vsma = Operand(type="indicator", name="VolumeSMA", params={"period": 30})
    code = export_mql5(_spec([
        Condition(Operand(type="price", field_name="close"), "cross_below", boll),
        Condition(vol, ">", vsma),
    ]))
    assert "iBands(_Symbol, _Period, 20" in code
    assert "double VolumeAverage(" in code
    assert "VolumeAverage((int)30, 1)" in code


def test_volume_operand_survives_serialisation_round_trip():
    """A volume comparison must never silently degrade into a close price.

    The dataclass attribute is ``field_name`` but JSON carries ``field`` — the
    exact mismatch that would turn `volume > VolumeSMA` into `close > VolumeSMA`.
    """
    spec = _spec([Condition(Operand(type="price", field_name="volume"), ">",
                            Operand(type="indicator", name="VolumeSMA", params={"period": 30}))])
    round_tripped = StrategySpec.from_dict(spec.to_dict())
    code = export_mql5(round_tripped)
    assert "iVolume(_Symbol, _Period, 1)" in code
    assert "iClose(_Symbol, _Period, 1) > VolumeAverage" not in code

    # a hand-written spec using the python attribute name must work too
    legacy = StrategySpec.from_dict({
        "name": "legacy", "direction": "long",
        "entry_long": [{"left": {"type": "price", "field_name": "volume"}, "op": ">",
                        "right": {"type": "indicator", "name": "VolumeSMA",
                                  "params": {"period": 30}}}],
    })
    assert "iVolume" in export_mql5(legacy)


def test_donchian_is_emulated():
    up = Operand(type="indicator", name="Donchian", output="upper", params={"period": 40})
    code = export_mql5(_spec([Condition(Operand(type="price", field_name="close"), ">", up)]))
    assert "double DonchianUpper(" in code
    assert "iHighest(_Symbol, _Period, MODE_HIGH" in code


def test_unsupported_indicator_is_flagged_loudly():
    st = Operand(type="indicator", name="Supertrend", output="direction",
                 params={"period": 10, "mult": 3.0})
    code = export_mql5(_spec([Condition(st, "cross_above", Operand(type="const", value=0))]))
    assert "NO SOPORTADO" in code
    assert "¡ATENCIÓN!" in code, "el usuario debe ver la advertencia en la cabecera"


def test_short_only_disables_long_input():
    rsi = Operand(type="indicator", name="RSI", params={"period": 14})
    spec = StrategySpec(name="t", direction="short", entry_long=[],
                        entry_short=[Condition(rsi, "cross_below",
                                               Operand(type="const", value=70))])
    code = export_mql5(spec)
    assert "InpAllowLong   = false" in code
    assert "InpAllowShort  = true" in code
