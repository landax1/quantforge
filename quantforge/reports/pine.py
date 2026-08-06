"""Export a mined strategy as a TradingView Pine Script v5 strategy.

Same contract as the MQL5 exporter: the script recomputes the indicators with
TradingView's own built-ins and applies the same entry rules, evaluated on the
previous closed bar so the chart cannot repaint. Every tunable value becomes an
``input`` so the strategy can be re-tuned in TradingView without editing code.
"""

from __future__ import annotations

from typing import Any

from quantforge.core.models import Condition, Operand, StrategySpec

# QuantForge indicator -> Pine expression template, by output name.
# ``{shift}`` is applied afterwards as a history reference: expr[shift].
_PINE: dict[str, dict[str, str]] = {
    "EMA": {"value": "ta.ema(close, {period})"},
    "SMA": {"value": "ta.sma(close, {period})"},
    "RSI": {"value": "ta.rsi(close, {period})"},
    "ATR": {"value": "ta.atr({period})"},
    "CCI": {"value": "ta.cci(hlc3, {period})"},
    "Momentum": {"value": "(close / close[{period}] * 100)"},
    "ADX": {"adx": "_adx({period})", "plus": "_diPlus({period})", "minus": "_diMinus({period})"},
    "MACD": {"macd": "_macdLine({fast}, {slow})", "signal": "_macdSignal({fast}, {slow}, {signal})"},
    "Stochastic": {"k": "ta.stoch(close, high, low, {k_period})",
                   "d": "ta.sma(ta.stoch(close, high, low, {k_period}), {d_period})"},
    "Bollinger": {"middle": "ta.sma(close, {period})",
                  "upper": "(ta.sma(close, {period}) + {mult} * ta.stdev(close, {period}))",
                  "lower": "(ta.sma(close, {period}) - {mult} * ta.stdev(close, {period}))"},
    # high[1]/low[1] como fuente = el canal excluye la vela evaluada, igual que
    # el shift(1) del backtest. Sin eso "close > maximo(high)" incluiria la
    # propia vela y jamas se cumpliria: cero operaciones.
    "Donchian": {"upper": "ta.highest(high[1], {period})",
                 "lower": "ta.lowest(low[1], {period})"},
    "VolumeSMA": {"value": "ta.sma(volume, {period})"},
    "VWAP": {"value": "ta.vwap(hlc3)"},
    "Ichimoku": {"tenkan": "_donchMid({tenkan})", "kijun": "_donchMid({kijun})",
                 "senkou_a": "((_donchMid({tenkan}) + _donchMid({kijun})) / 2)",
                 "senkou_b": "_donchMid({senkou})"},
    "Supertrend": {"direction": "_supertrendDir({period}, {mult})"},
}

_PRICE = {"close": "close", "open": "open", "high": "high",
          "low": "low", "volume": "volume"}


def _fmt_num(v: Any) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


class _Builder:
    """Turns conditions into Pine expressions, collecting needed helpers."""

    def __init__(self) -> None:
        self.helpers: set[str] = set()
        self.unsupported: set[str] = set()

    def value(self, op: Operand, shift: int = 1) -> str:
        if op.type == "const":
            return _fmt_num(op.value)
        if op.type == "price":
            field = (op.field_name or "close").lower()
            return f"{_PRICE.get(field, 'close')}[{shift}]"

        spec = _PINE.get(op.name)
        if spec is None:
            self.unsupported.add(op.name)
            return f"na // NO SOPORTADO: {op.name}"
        tpl = spec.get(op.output or "value") or next(iter(spec.values()))
        params = {k: _fmt_num(v) for k, v in (op.params or {}).items()}
        try:
            expr = tpl.format(**params)
        except KeyError:                      # falta un parámetro: no inventamos
            self.unsupported.add(op.name)
            return f"na // NO SOPORTADO: {op.name}"
        for helper in ("_adx", "_diPlus", "_diMinus", "_macdLine", "_macdSignal",
                       "_donchMid", "_supertrendDir"):
            if helper in expr:
                self.helpers.add(helper)
        return f"({expr})[{shift}]"

    def condition(self, c: Condition) -> str:
        op = c.op
        left_now, left_prev = self.value(c.left, 1), self.value(c.left, 2)
        if op in ("rising", "falling"):
            return f"({left_now} {'>' if op == 'rising' else '<'} {left_prev})"
        right_now, right_prev = self.value(c.right, 1), self.value(c.right, 2)
        if op == "cross_above":
            return f"({left_prev} <= {right_prev} and {left_now} > {right_now})"
        if op == "cross_below":
            return f"({left_prev} >= {right_prev} and {left_now} < {right_now})"
        pine_op = {">": ">", "<": "<", ">=": ">=", "<=": "<="}.get(op, ">")
        return f"({left_now} {pine_op} {right_now})"


_HELPER_SRC = {
    "_adx": """_adx(int len) =>
    [_p, _m, _a] = ta.dmi(len, len)
    _a""",
    "_diPlus": """_diPlus(int len) =>
    [_p, _m, _a] = ta.dmi(len, len)
    _p""",
    "_diMinus": """_diMinus(int len) =>
    [_p, _m, _a] = ta.dmi(len, len)
    _m""",
    "_macdLine": """_macdLine(int f, int s) =>
    ta.ema(close, f) - ta.ema(close, s)""",
    "_macdSignal": """_macdSignal(int f, int s, int sig) =>
    ta.ema(ta.ema(close, f) - ta.ema(close, s), sig)""",
    "_donchMid": """_donchMid(int len) =>
    (ta.highest(high, len) + ta.lowest(low, len)) / 2""",
    "_supertrendDir": """_supertrendDir(int len, float mult) =>
    [_st, _dir] = ta.supertrend(mult, len)
    _dir""",
}


def export_pine(spec: StrategySpec, *, name: str = "QF Strategy",
                symbol_hint: str = "", timeframe_hint: str = "",
                metrics: dict[str, float] | None = None) -> str:
    """Render a complete Pine Script v5 strategy for ``spec``."""
    b = _Builder()
    long_conds = [b.condition(c) for c in (spec.entry_long or [])]
    short_conds = [b.condition(c) for c in (spec.entry_short or [])]
    want_long = spec.direction in ("long", "both") and long_conds
    want_short = spec.direction in ("short", "both") and short_conds

    risk = spec.risk
    header = [f"// {name} — generado por QuantForge"]
    if symbol_hint:
        header.append(f"// Minada sobre {symbol_hint} {timeframe_hint}".rstrip())
    if metrics:
        header.append(
            f"// Backtest QuantForge: Net {metrics.get('net_profit_pct', 0):+.1f}% · "
            f"CAGR {metrics.get('cagr_pct', 0):.2f}% · PF {metrics.get('profit_factor', 0):.2f} · "
            f"MaxDD {metrics.get('max_drawdown_pct', 0):.1f}% · "
            f"{int(metrics.get('trades', 0))} trades")
    if b.unsupported:
        header.append("// ¡ATENCIÓN! Sin equivalente directo en Pine: "
                      + ", ".join(sorted(b.unsupported))
                      + " — revisá las líneas marcadas NO SOPORTADO.")
    header.append("// Las reglas se evalúan sobre velas ya cerradas: el script no repinta.")

    helpers = "\n".join(_HELPER_SRC[h] for h in sorted(b.helpers))
    fixed_lots = risk.size_mode == "fixed_units"

    # Ojo con el tamaño en TradingView: un qty fraccionario (0.1 lotes de MT5)
    # se redondea hacia abajo a 0 en los instrumentos que no admiten fracciones,
    # y la estrategia no abre NADA sin decir por qué. Por eso el default es
    # porcentaje de capital — que TradingView siempre resuelve a una posición
    # válida — y el volumen fijo queda como opción explícita, nunca por debajo
    # de 1 contrato.
    qty_block = (
        """qtyFixed = math.max(InpContracts, 1)
qty      = InpUseFixedQty ? qtyFixed : na"""
        if fixed_lots else
        """riskMoney = strategy.equity * InpRiskPct / 100.0
stopDist  = InpStopMult * atrRisk
qtyRisk   = stopDist > 0 ? riskMoney / stopDist : 0
qty       = InpUseFixedQty ? math.max(qtyRisk, 1) : na"""
    )

    def join(conds: list[str]) -> str:
        return "\n     and ".join(conds) if conds else "false"

    return f"""{chr(10).join(header)}
//@version=5
strategy("{name}", overlay=true, initial_capital=10000,
     default_qty_type=strategy.percent_of_equity, default_qty_value=10,
     commission_type=strategy.commission.percent, commission_value=0,
     calc_on_every_tick=false, process_orders_on_close=true)

// ---------------------------------------------------------------- entradas
{'InpContracts = input.float(' + _fmt_num(risk.size_value) + ', "Contratos por operación", minval=0.01)' if fixed_lots else 'InpRiskPct   = input.float(' + _fmt_num(risk.size_value) + ', "% del capital por operación", minval=0.01, maxval=100)'}
InpUseFixedQty = input.bool(false, "Usar ese tamaño exacto (si no, % del capital)")
InpStopMult   = input.float({_fmt_num(risk.stop_value)}, "Stop: múltiplo de ATR", minval=0.1)
InpTargetMult = input.float({_fmt_num(risk.target_value)}, "Target: múltiplo de ATR", minval=0.1)
InpATRPeriod  = input.int({int(risk.atr_period)}, "Período del ATR de riesgo", minval=1)
InpAllowLong  = input.bool({str(bool(want_long)).lower()}, "Permitir largos")
InpAllowShort = input.bool({str(bool(want_short)).lower()}, "Permitir cortos")

{helpers}

atrRisk = ta.atr(InpATRPeriod)

// ------------------------------------------------------------------ reglas
goLong  = InpAllowLong and ({join(long_conds) if want_long else 'false'})
goShort = InpAllowShort and ({join(short_conds) if want_short else 'false'})

// ----------------------------------------------------------------- tamaño
{qty_block}

// ------------------------------------------------------------------ órdenes
if goLong and strategy.position_size == 0 and not na(atrRisk)
    strategy.entry("L", strategy.long, qty=qty)
    strategy.exit("L exit", "L", stop=close - InpStopMult * atrRisk,
         limit=close + InpTargetMult * atrRisk)

if goShort and strategy.position_size == 0 and not na(atrRisk)
    strategy.entry("S", strategy.short, qty=qty)
    strategy.exit("S exit", "S", stop=close + InpStopMult * atrRisk,
         limit=close - InpTargetMult * atrRisk)

// ------------------------------------------------------- diagnóstico visual
// Si no ves operaciones, esto muestra en qué velas hubo señal: si no aparece
// ninguna flecha, el problema son las reglas de entrada (símbolo o timeframe
// distintos a los que se minaron), no el tamaño de la posición.
plotshape(goLong,  title="Señal larga", style=shape.triangleup,
     location=location.belowbar, color=color.new(color.teal, 0), size=size.tiny)
plotshape(goShort, title="Señal corta", style=shape.triangledown,
     location=location.abovebar, color=color.new(color.red, 0), size=size.tiny)
"""
