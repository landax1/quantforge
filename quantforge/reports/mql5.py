"""Export a mined strategy as a compilable MQL5 Expert Advisor.

The generated EA recomputes the same indicators through MT5's own handles and
applies the same entry rules, so what mined here is what runs there. Every
tunable value is emitted as an ``input`` so the strategy can be re-optimised in
the MetaTrader tester without touching code.
"""

from __future__ import annotations

from typing import Any

from quantforge.core.models import Condition, Operand, StrategySpec

# QuantForge indicator -> (MQL5 handle factory, buffer index by output name)
_HANDLES: dict[str, dict[str, Any]] = {
    "EMA": {"call": 'iMA(_Symbol, _Period, {period}, 0, MODE_EMA, PRICE_CLOSE)', "buf": {"value": 0}},
    "SMA": {"call": 'iMA(_Symbol, _Period, {period}, 0, MODE_SMA, PRICE_CLOSE)', "buf": {"value": 0}},
    "RSI": {"call": 'iRSI(_Symbol, _Period, {period}, PRICE_CLOSE)', "buf": {"value": 0}},
    "ATR": {"call": 'iATR(_Symbol, _Period, {period})', "buf": {"value": 0}},
    "ADX": {"call": 'iADX(_Symbol, _Period, {period})', "buf": {"adx": 0, "plus": 1, "minus": 2}},
    "CCI": {"call": 'iCCI(_Symbol, _Period, {period}, PRICE_TYPICAL)', "buf": {"value": 0}},
    "Momentum": {"call": 'iMomentum(_Symbol, _Period, {period}, PRICE_CLOSE)', "buf": {"value": 0}},
    "MACD": {"call": 'iMACD(_Symbol, _Period, {fast}, {slow}, {signal}, PRICE_CLOSE)',
             "buf": {"macd": 0, "signal": 1}},
    "Stochastic": {"call": 'iStochastic(_Symbol, _Period, {k_period}, {d_period}, 3, MODE_SMA, STO_LOWHIGH)',
                   "buf": {"k": 0, "d": 1}},
    "Bollinger": {"call": 'iBands(_Symbol, _Period, {period}, 0, {mult}, PRICE_CLOSE)',
                  "buf": {"middle": 0, "upper": 1, "lower": 2}},
    "Donchian": {"call": None, "buf": {"upper": 0, "lower": 1}},      # emulated
    "VolumeSMA": {"call": None, "buf": {"value": 0}},                  # emulated
    "Supertrend": {"call": None, "buf": {"direction": 0}},             # unsupported
    "Ichimoku": {"call": 'iIchimoku(_Symbol, _Period, {tenkan}, {kijun}, {senkou})',
                 "buf": {"tenkan": 0, "kijun": 1, "senkou_a": 2, "senkou_b": 3}},
    "VWAP": {"call": None, "buf": {"value": 0}},                       # unsupported
}

UNSUPPORTED = {"Supertrend", "VWAP"}

_UNIT_LABEL = {
    "atr": "multiplo de ATR",
    "percent": "% del precio",
    "points": "puntos de precio",
    "money": "dinero de la cuenta",
}


class _Builder:
    """Turns conditions into MQL5 expressions, collecting handles as it goes."""

    def __init__(self) -> None:
        self.handles: dict[str, tuple[str, str]] = {}   # var -> (call, comment)
        self.emulated: set[str] = set()
        self.unsupported: set[str] = set()

    def _handle_var(self, op: Operand) -> str:
        spec = _HANDLES.get(op.name)
        params = {k: _fmt_num(v) for k, v in (op.params or {}).items()}
        key = f"h_{op.name.lower()}_" + "_".join(str(v).replace(".", "p") for v in params.values())
        if spec and spec["call"]:
            self.handles[key] = (spec["call"].format(**params),
                                 f"{op.name}({', '.join(f'{k}={v}' for k, v in params.items())})")
        return key

    def value(self, op: Operand, shift: int = 1) -> str:
        """MQL5 expression for an operand's value at ``shift`` bars back."""
        if op.type == "const":
            return _fmt_num(op.value)
        if op.type == "price":
            field = (op.field_name or "close").lower()
            return {"close": f"iClose(_Symbol, _Period, {shift})",
                    "open": f"iOpen(_Symbol, _Period, {shift})",
                    "high": f"iHigh(_Symbol, _Period, {shift})",
                    "low": f"iLow(_Symbol, _Period, {shift})",
                    "volume": f"(double)iVolume(_Symbol, _Period, {shift})"}.get(
                        field, f"iClose(_Symbol, _Period, {shift})")

        name = op.name
        if name in UNSUPPORTED:
            self.unsupported.add(name)
            return "0.0 /* NO SOPORTADO: " + name + " */"

        params = {k: _fmt_num(v) for k, v in (op.params or {}).items()}
        if name == "Donchian":
            self.emulated.add("Donchian")
            p = params.get("period", "20")
            fn = "DonchianUpper" if op.output == "upper" else "DonchianLower"
            return f"{fn}((int){p}, {shift})"
        if name == "VolumeSMA":
            self.emulated.add("VolumeSMA")
            return f"VolumeAverage((int){params.get('period', '20')}, {shift})"

        var = self._handle_var(op)
        buf = _HANDLES[name]["buf"].get(op.output or "value", 0)
        return f"Buf({var}, {buf}, {shift})"

    def condition(self, c: Condition) -> str:
        op = c.op
        left_now, left_prev = self.value(c.left, 1), self.value(c.left, 2)
        if op in ("rising", "falling"):
            sign = ">" if op == "rising" else "<"
            return f"({left_now} {sign} {left_prev})"
        right_now, right_prev = self.value(c.right, 1), self.value(c.right, 2)
        if op == "cross_above":
            return f"({left_prev} <= {right_prev} && {left_now} > {right_now})"
        if op == "cross_below":
            return f"({left_prev} >= {right_prev} && {left_now} < {right_now})"
        mql_op = {">": ">", "<": "<", ">=": ">=", "<=": "<="}.get(op, ">")
        return f"({left_now} {mql_op} {right_now})"


def _fmt_num(v: Any) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def export_mql5(spec: StrategySpec, *, ea_name: str = "QF_Strategy",
                symbol_hint: str = "", timeframe_hint: str = "",
                metrics: dict[str, float] | None = None) -> str:
    """Render a full .mq5 Expert Advisor source for ``spec``."""
    b = _Builder()
    long_conds = [b.condition(c) for c in (spec.entry_long or [])]
    short_conds = [b.condition(c) for c in (spec.entry_short or [])]
    want_long = spec.direction in ("long", "both") and long_conds
    want_short = spec.direction in ("short", "both") and short_conds

    handle_decls = "\n".join(f"int {v} = INVALID_HANDLE;" for v in b.handles)
    handle_init = "\n".join(
        f'   {v} = {call};\n'
        f'   if({v} == INVALID_HANDLE) {{ Print("No se pudo crear {cmt}"); return INIT_FAILED; }}'
        for v, (call, cmt) in b.handles.items())
    handle_free = "\n".join(f"   IndicatorRelease({v});" for v in b.handles)

    risk = spec.risk
    perf = ""
    if metrics:
        perf = (f"//|  Backtest QuantForge: Net {metrics.get('net_profit_pct', 0):+.1f}% · "
                f"CAGR {metrics.get('cagr_pct', 0):.2f}% · PF {metrics.get('profit_factor', 0):.2f} ·\n"
                f"//|  MaxDD {metrics.get('max_drawdown_pct', 0):.1f}% · "
                f"{int(metrics.get('trades', 0))} trades · "
                f"exposición {metrics.get('exposure_pct', 0):.1f}% del tiempo\n")

    warn = ""
    if b.unsupported:
        warn = ("//|  ¡ATENCIÓN! Indicadores sin equivalente nativo en MT5: "
                + ", ".join(sorted(b.unsupported)) + ".\n"
                "//|  El EA NO reproduce esa lógica — revisá el código marcado NO SOPORTADO.\n")

    helpers = _HELPERS_BASE
    if "Donchian" in b.emulated:
        helpers += _HELPER_DONCHIAN
    if "VolumeSMA" in b.emulated:
        helpers += _HELPER_VOLUME
    if "money" in (risk.stop_type, risk.target_type):
        helpers += _HELPER_MONEY

    def join(conds: list[str]) -> str:
        if not conds:
            return "false"
        return "\n          && ".join(conds)

    sl_line = _stop_expr(risk.stop_type, risk.stop_value, "long")
    sl_short = _stop_expr(risk.stop_type, risk.stop_value, "short")
    tp_line = _target_expr(risk.target_type, risk.target_value, "long")
    tp_short = _target_expr(risk.target_type, risk.target_value, "short")
    needs_atr = risk.stop_type == "atr" or risk.target_type == "atr"

    return f"""//+------------------------------------------------------------------+
//| {ea_name}.mq5
//| Generado por QuantForge — estrategia minada{f" sobre {symbol_hint} {timeframe_hint}" if symbol_hint else ""}
{perf}{warn}//|
//| Las reglas de entrada se evalúan en el cierre de la vela anterior,
//| igual que en el backtest (sin repintado, sin mirar el futuro).
//+------------------------------------------------------------------+
#property copyright "QuantForge"
#property version   "1.00"
#property strict

#include <Trade\\Trade.mqh>

input double InpLots        = {_fmt_num(risk.size_value) if risk.size_mode == 'fixed_units' else '0.10'};    // Lotes fijos{'' if risk.size_mode == 'fixed_units' else ' (sólo si InpRiskPct = 0)'}
input double InpRiskPct     = {_fmt_num(risk.size_value) if risk.size_mode == 'risk_pct' else '0'};     // % del balance a arriesgar (0 = usar lotes fijos)
input double InpStopValue   = {_fmt_num(risk.stop_value)};  // Stop loss ({_UNIT_LABEL.get(risk.stop_type, 'desactivado')})
input double InpTargetValue = {_fmt_num(risk.target_value)};  // Take profit ({_UNIT_LABEL.get(risk.target_type, 'desactivado')})
input int    InpATRPeriod   = {int(risk.atr_period)};     // Periodo del ATR de riesgo
input long   InpMagic       = 770001;  // Magic number
input int    InpSlippage    = 30;      // Desviacion maxima (points)
input bool   InpVerbose     = true;    // Explicar en el log por que no opera
input bool   InpAllowLong   = {'true' if want_long else 'false'};    // Permitir largos
input bool   InpAllowShort  = {'true' if want_short else 'false'};   // Permitir cortos

CTrade   trade;
datetime g_lastBar = 0;
{handle_decls}
{'int h_atr_risk = INVALID_HANDLE;' if needs_atr else ''}

{helpers}
//+------------------------------------------------------------------+
int OnInit()
  {{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);
{handle_init}
{'   h_atr_risk = iATR(_Symbol, _Period, InpATRPeriod);' if needs_atr else ''}
   if(InpVerbose)
     {{
      // lo que el broker declara para ESTE simbolo: si algo no cierra, esta aca
      PrintFormat("[QF] %s %s | volumen min=%.2f max=%.2f step=%.2f | "
                  "stops_level=%d points | tick_value=%.5f tick_size=%.5f | digits=%d",
                  _Symbol, EnumToString((ENUM_TIMEFRAMES)_Period),
                  SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
                  SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX),
                  SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP),
                  (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL),
                  SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE),
                  SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE),
                  (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
     }}
   return INIT_SUCCEEDED;
  }}
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {{
{handle_free}
{'   IndicatorRelease(h_atr_risk);' if needs_atr else ''}
  }}
//+------------------------------------------------------------------+
bool HasPosition()
  {{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {{
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
     }}
   return false;
  }}
//+------------------------------------------------------------------+
void OnTick()
  {{
   // una sola evaluacion por vela cerrada
   datetime bar = iTime(_Symbol, _Period, 0);
   if(bar == g_lastBar) return;
   g_lastBar = bar;

   if(HasPosition()) return;

   bool goLong  = InpAllowLong && ({join(long_conds) if want_long else 'false'});
   bool goShort = InpAllowShort && ({join(short_conds) if want_short else 'false'});
   if(!goLong && !goShort) return;

{'   double atr = Buf(h_atr_risk, 0, 1);' if needs_atr else '   double atr = 0.0;'}
{'''   if(atr <= 0.0)
     {
      // sin ATR no hay distancia de stop: pasa en las primeras velas del
      // historial, cuando el indicador todavia no tiene datos suficientes
      if(InpVerbose) Print("[QF] Sin senal de ATR todavia (historial insuficiente)");
      return;
     }''' if needs_atr else ''}
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(goLong)
     {{
      double sl = {sl_line};
      double tp = {tp_line};
      if(!ValidStops(true, ask, sl, tp)) return;
      double vol = LotsFor(true, ask, sl);
      if(vol <= 0.0)
        {{
         if(InpVerbose) Print("[QF] Volumen calculado en 0 — revisa volumen minimo del simbolo");
         return;
        }}
      ReportSize("BUY", true, vol, ask, sl);
      if(!trade.Buy(vol, _Symbol, 0.0, Norm(sl), Norm(tp), "{ea_name}"))
         ReportFailure("BUY", vol, ask, sl, tp);
     }}
   else if(goShort)
     {{
      double sl = {sl_short};
      double tp = {tp_short};
      if(!ValidStops(false, bid, sl, tp)) return;
      double vol = LotsFor(false, bid, sl);
      if(vol <= 0.0)
        {{
         if(InpVerbose) Print("[QF] Volumen calculado en 0 — revisa volumen minimo del simbolo");
         return;
        }}
      ReportSize("SELL", false, vol, bid, sl);
      if(!trade.Sell(vol, _Symbol, 0.0, Norm(sl), Norm(tp), "{ea_name}"))
         ReportFailure("SELL", vol, bid, sl, tp);
     }}
  }}
//+------------------------------------------------------------------+
"""


def _level_expr(kind: str, input_name: str, side: str, is_stop: bool) -> str:
    px = "ask" if side == "long" else "bid"
    away = ("-" if is_stop else "+") if side == "long" else ("+" if is_stop else "-")
    if kind == "atr":
        return f"{px} {away} {input_name} * atr"
    if kind == "percent":
        return f"{px} * (1.0 {away} {input_name} / 100.0)"
    if kind == "points":
        return f"{px} {away} {input_name}"
    if kind == "money":
        # money / (lots * value of one price unit) => distance in price
        return f"{px} {away} MoneyDistance({input_name})"
    return "0.0"


def _stop_expr(kind: str, value: float, side: str) -> str:
    return _level_expr(kind, "InpStopValue", side, is_stop=True)


def _target_expr(kind: str, value: float, side: str) -> str:
    return _level_expr(kind, "InpTargetValue", side, is_stop=False)


_HELPERS_BASE = """//+------------------------------------------------------------------+
//| Lectura de un buffer de indicador en la vela `shift`              |
//+------------------------------------------------------------------+
double Buf(const int handle, const int buffer, const int shift)
  {
   if(handle == INVALID_HANDLE) return 0.0;
   double tmp[];
   if(CopyBuffer(handle, buffer, shift, 1, tmp) < 1) return 0.0;
   return tmp[0];
  }
//+------------------------------------------------------------------+
double Norm(const double price)
  {
   if(price <= 0.0) return 0.0;
   return NormalizeDouble(price, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
  }
//+------------------------------------------------------------------+
//| Volumen de la operacion.                                          |
//| Con InpRiskPct > 0 se calcula para que tocar el stop cueste ese   |
//| % del balance (igual que el backtest de QuantForge). Con 0 manda  |
//| InpLots: hay brokers de CFDs que no aceptan bien un volumen       |
//| recalculado en cada entrada.                                      |
//+------------------------------------------------------------------+
double LotsFor(const bool isLong, const double entry, const double stopPrice)
  {
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vol     = InpLots;
   ENUM_ORDER_TYPE dir = isLong ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   if(InpRiskPct > 0.0 && entry > 0.0 && stopPrice > 0.0)
     {
      // Cuanto pierde 1 lote desde la entrada hasta el stop, en la MONEDA DE
      // LA CUENTA, preguntandoselo al terminal. Calcularlo como
      // (distancia / tick_size) * tick_value asume que el tick vale lo mismo
      // que el punto: en los CFD de indices el contrato es de 100 unidades y
      // esa cuenta devuelve 100x MAS volumen del que corresponde. Medido en
      // US500: 12.2 lotes donde tocaban 0.12, y una sola perdida vacio la
      // cuenta entera arriesgando el 100% en vez del 1%.
      double lossPerLot = 0.0;
      if(OrderCalcProfit(dir, _Symbol, 1.0, entry, stopPrice, lossPerLot))
        {
         lossPerLot = MathAbs(lossPerLot);
         double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0;
         if(lossPerLot > 0.0) vol = riskMoney / lossPerLot;
        }
      else if(InpVerbose)
         PrintFormat("[QF] OrderCalcProfit fallo (error %d) — se usa el volumen fijo %.2f",
                     GetLastError(), InpLots);
     }

   // el margen manda: pedir mas de lo que la cuenta banca hace fallar la orden
   double price = isLong ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                         : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double margin = 0.0;
   if(OrderCalcMargin(dir, _Symbol, vol, price, margin) && margin > 0.0)
     {
      double usable = AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.90;
      if(margin > usable && usable > 0.0) vol = vol * usable / margin;
     }

   if(lotStep > 0.0) vol = MathFloor(vol / lotStep) * lotStep;
   // nunca por debajo del minimo del simbolo: redondear hacia abajo puede
   // dejar el volumen en cero y entonces el EA no abre nada, en silencio
   if(minLot > 0.0 && vol < minLot) vol = minLot;
   if(maxLot > 0.0 && vol > maxLot) vol = maxLot;
   if(vol <= 0.0) vol = (minLot > 0.0) ? minLot : 0.01;
   return NormalizeDouble(vol, 2);
  }
//+------------------------------------------------------------------+
//| Los stops tienen que respetar la distancia minima del broker.     |
//| Es la causa numero uno de ordenes rechazadas en CFDs.             |
//+------------------------------------------------------------------+
bool ValidStops(const bool isLong, const double price, double &sl, double &tp)
  {
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int    lvl   = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minDist = (lvl > 0 && point > 0.0) ? lvl * point : 0.0;

   if(sl <= 0.0 || tp <= 0.0 || price <= 0.0)
     {
      if(InpVerbose) PrintFormat("[QF] Niveles invalidos: precio=%.5f sl=%.5f tp=%.5f", price, sl, tp);
      return false;
     }
   if(minDist > 0.0)
     {
      // se empuja el nivel hasta la distancia minima en vez de descartar la
      // senal: mejor una operacion con stop algo mas ancho que ninguna
      if(isLong)
        {
         if(price - sl < minDist) sl = price - minDist;
         if(tp - price < minDist) tp = price + minDist;
        }
      else
        {
         if(sl - price < minDist) sl = price + minDist;
         if(price - tp < minDist) tp = price - minDist;
        }
     }
   return true;
  }
//+------------------------------------------------------------------+
//| Cuanto se arriesga DE VERDAD en esta operacion, en plata y en %   |
//| del balance. Si el numero no coincide con InpRiskPct, el problema |
//| es el dimensionamiento y se ve en la primera operacion, no        |
//| cuando la cuenta ya voló.                                         |
//+------------------------------------------------------------------+
void ReportSize(const string side, const bool isLong, const double vol,
                const double entry, const double stopPrice)
  {
   if(!InpVerbose) return;
   double loss = 0.0;
   ENUM_ORDER_TYPE dir = isLong ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!OrderCalcProfit(dir, _Symbol, vol, entry, stopPrice, loss)) return;
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double pct = (balance > 0.0) ? MathAbs(loss) / balance * 100.0 : 0.0;
   PrintFormat("[QF] %s vol=%.2f | si toca el stop pierde %.2f = %.2f%% del balance "
               "(pedido: %.2f%%)", side, vol, MathAbs(loss), pct, InpRiskPct);
  }
//+------------------------------------------------------------------+
//| Por que fallo la orden, con el codigo que devuelve el servidor    |
//+------------------------------------------------------------------+
void ReportFailure(const string side, const double vol, const double price,
                   const double sl, const double tp)
  {
   PrintFormat("[QF] %s RECHAZADA: retcode=%d (%s) | vol=%.2f precio=%.5f sl=%.5f tp=%.5f | "
               "margen_libre=%.2f",
               side, trade.ResultRetcode(), trade.ResultRetcodeDescription(),
               vol, price, sl, tp, AccountInfoDouble(ACCOUNT_MARGIN_FREE));
  }
"""

_HELPER_DONCHIAN = """//+------------------------------------------------------------------+
//| Canal de Donchian emulado (MT5 no lo trae nativo).                |
//|                                                                   |
//| El canal EXCLUYE la vela evaluada: se arranca en shift+1. Si se   |
//| incluyera, "close[1] > maximo(high[1..n])" seria imposible por    |
//| definicion — el high de una vela siempre es >= su close — y el EA |
//| no abriria una sola operacion en toda la corrida.                 |
//+------------------------------------------------------------------+
double DonchianUpper(const int period, const int shift)
  {
   int idx = iHighest(_Symbol, _Period, MODE_HIGH, period, shift + 1);
   return (idx < 0) ? 0.0 : iHigh(_Symbol, _Period, idx);
  }
double DonchianLower(const int period, const int shift)
  {
   int idx = iLowest(_Symbol, _Period, MODE_LOW, period, shift + 1);
   return (idx < 0) ? 0.0 : iLow(_Symbol, _Period, idx);
  }
"""

_HELPER_MONEY = """//+------------------------------------------------------------------+
//| Convierte un importe en dinero a distancia de precio              |
//| usando el valor real del tick del simbolo                         |
//+------------------------------------------------------------------+
double MoneyDistance(const double money)
  {
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0.0 || tickSize <= 0.0 || InpLots <= 0.0) return 0.0;
   double moneyPerPriceUnit = (tickValue / tickSize) * InpLots;
   return (moneyPerPriceUnit > 0.0) ? money / moneyPerPriceUnit : 0.0;
  }
"""

_HELPER_VOLUME = """//+------------------------------------------------------------------+
//| Media simple del volumen de ticks                                 |
//+------------------------------------------------------------------+
double VolumeAverage(const int period, const int shift)
  {
   long total = 0;
   for(int i = shift; i < shift + period; i++)
      total += iVolume(_Symbol, _Period, i);
   return (period > 0) ? (double)total / period : 0.0;
  }
"""
