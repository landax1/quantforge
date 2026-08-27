"""Export a mined strategy as a compilable MQL5 Expert Advisor.

The generated EA recomputes the same indicators through MT5's own handles and
applies the same entry rules, so what mined here is what runs there. Every
tunable value is emitted as an ``input`` so the strategy can be re-optimised in
the MetaTrader tester without touching code.
"""

from __future__ import annotations

from typing import Any

from botiquant.core.models import Condition, Operand, StrategySpec

# Botiquant indicator -> (MQL5 handle factory, buffer index by output name)
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
    "ClosePosition": {"call": None, "buf": {"value": 0}},              # emulated
    "DistATR": {"call": None, "buf": {"to_high": 0, "to_low": 1, "bar_range": 2}},
    "DayOfWeek": {"call": None, "buf": {"value": 0}},                  # emulated
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
        if name == "ClosePosition":
            self.emulated.add("ClosePosition")
            return f"ClosePositionPct({shift})"
        if name == "DayOfWeek":
            self.emulated.add("DayOfWeek")
            return f"BarDayOfWeek({shift})"
        if name == "DistATR":
            self.emulated.add("DistATR")
            p = params.get("period", "20")
            fn = {"to_high": "DistToHighATR", "to_low": "DistToLowATR",
                  "bar_range": "BarRangeATR"}.get(op.output or "to_high", "DistToHighATR")
            return f"{fn}((int){p}, {shift})"

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
        if op in ("==", "!="):
            # se comparan con tolerancia por lo mismo que en el backtest: son
            # enteros viajando como double
            signo = "<" if op == "==" else ">="
            return f"(MathAbs({left_now} - {right_now}) {signo} 1e-9)"
        mql_op = {">": ">", "<": "<", ">=": ">=", "<=": "<="}.get(op, ">")
        return f"({left_now} {mql_op} {right_now})"


def _fmt_num(v: Any) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


#: De dónde arranca la numeración. Un número alto y poco redondo para no
#: chocar con los que ponen otros programas: muchos EA comerciales usan 1, 100,
#: 12345 y cosas así, y dos EA con el mismo Magic Number en la misma cuenta se
#: pisan las posiciones sin que nada avise.
_MAGIC_BASE = 770_000_000


def magic_de(nombre: str) -> int:
    """Un Magic Number propio para cada estrategia, siempre el mismo.

    ES EL NÚMERO QUE SEPARA UN BOT DE OTRO. MetaTrader no tiene otra forma de
    saber de quién es una posición: cada EA marca sus órdenes con el suyo y
    después filtra por él. Dos EA con el mismo número en la misma cuenta creen
    cada uno que las posiciones del otro son suyas — uno cierra lo que el otro
    abrió, y ninguno de los dos da error.

    Hasta acá todos los EA exportados salían con 770001. O sea que poner dos
    bots de Botiquant en una cuenta no funcionaba, y la forma de enterarse era
    ver operaciones cerrándose solas.

    DETERMINISTA A PROPÓSITO: la misma estrategia da siempre el mismo número.
    Si cambiara al reexportar, el EA nuevo no reconocería la posición que dejó
    abierta el viejo y la trataría como ajena — quedaría huérfana, sin nadie
    que la gestione ni la cierre.
    """
    import hashlib
    h = hashlib.sha256(nombre.encode("utf-8")).digest()
    # 24 bits alcanzan para dieciséis millones de estrategias sin repetir y
    # dejan el número corto de leer, que importa cuando hay que reconocerlo
    # en la lista de operaciones de MetaTrader.
    return _MAGIC_BASE + int.from_bytes(h[:3], "big")


def export_mql5(spec: StrategySpec, *, ea_name: str = "BQ_Strategy",
                symbol_hint: str = "", timeframe_hint: str = "",
                metrics: dict[str, float] | None = None,
                server_utc_offset: int = 0) -> str:
    """Render a full .mq5 Expert Advisor source for ``spec``.

    ``server_utc_offset`` son las horas que el servidor del bróker adelanta
    respecto de UTC. Sale de la configuración del usuario y viene ya puesto en
    el EA porque dejarlo en cero es un error silencioso: la estrategia opera en
    la franja equivocada y los resultados no se parecen a los del backtest, sin
    que nada falle. Sólo tiene efecto en estrategias con restricción horaria.
    """
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
        perf = (f"//|  Backtest Botiquant: Net {metrics.get('net_profit_pct', 0):+.1f}% · "
                f"CAGR {metrics.get('cagr_pct', 0):.2f}% · PF {metrics.get('profit_factor', 0):.2f} ·\n"
                f"//|  MaxDD {metrics.get('max_drawdown_pct', 0):.1f}% · "
                f"{int(metrics.get('trades', 0))} trades · "
                f"exposición {metrics.get('exposure_pct', 0):.1f}% del tiempo\n")

    warn = ""
    if b.unsupported:
        warn = ("//|  ¡ATENCIÓN! Indicadores sin equivalente nativo en MT5: "
                + ", ".join(sorted(b.unsupported)) + ".\n"
                "//|  El EA NO reproduce esa lógica — revisá el código marcado NO SOPORTADO.\n")

    # ------------------------------------------------------------- horario
    # Si la estrategia se minó restringida a una franja y el EA no la
    # respetara, en MetaTrader operaría las veinticuatro horas: no sería la
    # misma estrategia, y la diferencia aparecería recién con dinero real.
    tf = spec.time_filter
    usa_horario = bool(tf and tf.enabled)
    dias = sorted(tf.days) if usa_horario else [0, 1, 2, 3, 4]
    # MQL5 numera el domingo como 0 y el backtest numera el lunes como 0
    dias_mql = ",".join(str((d + 1) % 7) for d in dias)

    helpers = _HELPERS_BASE
    if "Donchian" in b.emulated:
        helpers += _HELPER_DONCHIAN
    if "VolumeSMA" in b.emulated:
        helpers += _HELPER_VOLUME
    if "ClosePosition" in b.emulated:
        helpers += _HELPER_CLOSE_POS
    if "DayOfWeek" in b.emulated:
        helpers += _HELPER_DOW
    if "DistATR" in b.emulated:
        helpers += _HELPER_DIST_ATR
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

    # El número que separa este bot de los demás en la misma cuenta. Sale del
    # NOMBRE y no del contenido: dos exportaciones de la misma estrategia con
    # ajustes distintos son el mismo bot para MetaTrader, y tienen que poder
    # reconocer las posiciones que dejó la anterior.
    magic = magic_de(ea_name)

    return f"""//+------------------------------------------------------------------+
//| {ea_name}.mq5
//| Generado por Botiquant — estrategia minada{f" sobre {symbol_hint} {timeframe_hint}" if symbol_hint else ""}
{perf}{warn}//|
//| Las reglas de entrada se evalúan en el cierre de la vela anterior,
//| igual que en el backtest (sin repintado, sin mirar el futuro).
//+------------------------------------------------------------------+
#property copyright "Botiquant"
#property version   "1.00"
#property strict

#include <Trade\\Trade.mqh>

input double InpLots        = {_fmt_num(risk.size_value) if risk.size_mode == 'fixed_units' else '0.10'};    // Lotes fijos{'' if risk.size_mode == 'fixed_units' else ' (sólo si InpRiskPct = 0)'}
input double InpRiskPct     = {_fmt_num(risk.size_value) if risk.size_mode == 'risk_pct' else '0'};     // % del balance a arriesgar (0 = usar lotes fijos)
input double InpStopValue   = {_fmt_num(risk.stop_value)};  // Stop loss ({_UNIT_LABEL.get(risk.stop_type, 'desactivado')})
input double InpTargetValue = {_fmt_num(risk.target_value)};  // Take profit ({_UNIT_LABEL.get(risk.target_type, 'desactivado')})
input double InpTrailATR    = {_fmt_num(risk.trail_atr)};  // Trailing (multiplo de ATR, 0 = sin trailing)
input int    InpMaxBars     = {int(risk.max_bars_in_trade)};     // Cerrar tras N velas (0 = sin limite)
input int    InpATRPeriod   = {int(risk.atr_period)};     // Periodo del ATR de riesgo
input long   InpMagic       = {magic};  // Magic number (propio de esta estrategia)
input int    InpSlippage    = 30;      // Desviacion maxima (points)
input bool   InpVerbose     = true;    // Explicar en el log por que no opera
input bool   InpAllowLong   = {'true' if want_long else 'false'};    // Permitir largos
input bool   InpAllowShort  = {'true' if want_short else 'false'};   // Permitir cortos
input bool   InpUseSession  = {'true' if usa_horario else 'false'};   // Operar solo en la franja horaria minada
input int    InpStartHourUTC = {int(tf.start_hour) if usa_horario else 0};      // Franja: hora de inicio (UTC, incluida)
input int    InpEndHourUTC   = {int(tf.end_hour) if usa_horario else 24};      // Franja: hora de fin (UTC, excluida)
input string InpDaysCSV      = "{dias_mql}";  // Dias permitidos (0=domingo ... 5=viernes)
input int    InpServerUTCOffset = {int(server_utc_offset)};    // Horas que adelanta el servidor del broker respecto de UTC

CTrade   trade;
datetime g_lastBar = 0;
double   g_trailDist = 0.0;   // distancia del trailing, fijada al entrar
double   g_bestPx    = 0.0;   // extremo a favor alcanzado en la operacion
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
      // La franja se declara al arrancar con la hora UTC que el EA cree que
      // es. Si no coincide con la hora real, InpServerUTCOffset esta mal y se
      // ve aca, antes de la primera operacion.
      if(InpUseSession)
        {{
         MqlDateTime ahora;
         TimeToStruct(TimeCurrent() - (long)InpServerUTCOffset * 3600, ahora);
         PrintFormat("[QF] Franja horaria activa: %02d:00-%02d:00 UTC, dias %s | "
                     "para el EA ahora son las %02d:%02d UTC (offset del servidor: %d h)",
                     InpStartHourUTC, InpEndHourUTC, InpDaysCSV,
                     ahora.hour, ahora.min, InpServerUTCOffset);
        }}
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

   if(ManageOpenPosition()) return;   // trailing y salida por tiempo

   // El horario filtra ENTRADAS, no salidas: una posicion abierta dentro de la
   // franja se sigue gestionando cuando la franja termina, igual que en el
   // backtest. Cerrarla al sonar la campana seria otra estrategia.
   if(!InSession())
     {{
      if(InpVerbose) Print("[QF] Fuera de la franja horaria minada");
      return;
     }}

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
      if(trade.Buy(vol, _Symbol, 0.0, Norm(sl), Norm(tp), "{ea_name}"))
        {{
         // la distancia del trailing queda fijada con el ATR de esta vela
         g_trailDist = (InpTrailATR > 0.0) ? InpTrailATR * atr : 0.0;
         g_bestPx = ask;
        }}
      else ReportFailure("BUY", vol, ask, sl, tp);
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
      if(trade.Sell(vol, _Symbol, 0.0, Norm(sl), Norm(tp), "{ea_name}"))
        {{
         g_trailDist = (InpTrailATR > 0.0) ? InpTrailATR * atr : 0.0;
         g_bestPx = bid;
        }}
      else ReportFailure("SELL", vol, bid, sl, tp);
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
//| % del balance (igual que el backtest de Botiquant). Con 0 manda  |
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
//| Gestion de la posicion abierta: trailing y salida por tiempo.      |
//| Devuelve true si hay una posicion (haya que gestionarla o no), asi |
//| OnTick no busca una entrada nueva mientras haya uno abierto.       |
//|                                                                   |
//| El trailing usa el ATR de la vela de ENTRADA, no el actual: es lo  |
//| que hace el backtest, y recalcularlo en cada vela daria una salida |
//| distinta a la que se minó.                                         |
//+------------------------------------------------------------------+
bool ManageOpenPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol ||
         PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;

      // --- salida por tiempo
      if(InpMaxBars > 0)
        {
         datetime abierta = (datetime)PositionGetInteger(POSITION_TIME);
         int velas = Bars(_Symbol, _Period, abierta, TimeCurrent()) - 1;
         if(velas >= InpMaxBars)
           {
            if(InpVerbose) PrintFormat("[QF] Cierre por tiempo: %d velas", velas);
            trade.PositionClose(ticket);
            return true;
           }
        }

      // --- trailing: el stop persigue al precio y nunca retrocede
      if(InpTrailATR > 0.0 && g_trailDist > 0.0)
        {
         long   tipo = PositionGetInteger(POSITION_TYPE);
         double sl   = PositionGetDouble(POSITION_SL);
         double tp   = PositionGetDouble(POSITION_TP);
         double nuevo;
         if(tipo == POSITION_TYPE_BUY)
           {
            g_bestPx = MathMax(g_bestPx, iHigh(_Symbol, _Period, 1));
            nuevo = g_bestPx - g_trailDist;
            if(nuevo > sl) trade.PositionModify(ticket, Norm(nuevo), tp);
           }
         else
           {
            g_bestPx = (g_bestPx <= 0.0) ? iLow(_Symbol, _Period, 1)
                                         : MathMin(g_bestPx, iLow(_Symbol, _Period, 1));
            nuevo = g_bestPx + g_trailDist;
            if(sl <= 0.0 || nuevo < sl) trade.PositionModify(ticket, Norm(nuevo), tp);
           }
        }
      return true;
     }
   g_trailDist = 0.0;
   g_bestPx = 0.0;
   return false;
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
//| Franja horaria: los datos con los que se mino estan en UTC, y el  |
//| servidor del broker casi nunca lo esta. InpServerUTCOffset son    |
//| las horas que el servidor adelanta respecto de UTC (un broker en  |
//| UTC+3 lleva 3). Si queda mal puesto, la estrategia opera en la    |
//| franja equivocada y los numeros no se parecen a los del backtest: |
//| por eso el log lo dice en la primera vela y en cada rechazo.      |
//|                                                                   |
//| Con InpUseSession en false no filtra nada, que es como corre una  |
//| estrategia minada sin restriccion de horario.                     |
//+------------------------------------------------------------------+
bool InSession()
  {
   if(!InpUseSession) return true;

   MqlDateTime t;
   TimeToStruct(TimeCurrent() - (long)InpServerUTCOffset * 3600, t);

   if(StringFind("," + InpDaysCSV + ",", "," + IntegerToString(t.day_of_week) + ",") < 0)
      return false;

   int desde = InpStartHourUTC, hasta = InpEndHourUTC;
   if(desde == hasta) return true;              // franja vacia = sin filtro
   if(desde < hasta)  return (t.hour >= desde && t.hour < hasta);
   // franja que cruza la medianoche, por ejemplo 22:00 a 05:00
   return (t.hour >= desde || t.hour < hasta);
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

_HELPER_CLOSE_POS = """//+------------------------------------------------------------------+
//| Donde cerro la vela dentro de su propio rango, de 0 a 100.        |
//| Una vela sin rango vale 50: ni compradores ni vendedores.          |
//+------------------------------------------------------------------+
double ClosePositionPct(const int shift)
  {
   double hi = iHigh(_Symbol, _Period, shift);
   double lo = iLow(_Symbol, _Period, shift);
   double rango = hi - lo;
   if(rango <= 0.0) return 50.0;
   return (iClose(_Symbol, _Period, shift) - lo) / rango * 100.0;
  }
"""

_HELPER_DOW = """//+------------------------------------------------------------------+
//| Dia de la semana de la vela: 1 = lunes ... 5 = viernes.           |
//| Se convierte desde la numeracion de MQL5 (0 = domingo) a la misma |
//| que usa el backtest, o el filtro saltearia el dia equivocado.     |
//+------------------------------------------------------------------+
double BarDayOfWeek(const int shift)
  {
   MqlDateTime t;
   TimeToStruct(iTime(_Symbol, _Period, shift), t);
   return (double)((t.day_of_week + 6) % 7 + 1);
  }
"""

_HELPER_DIST_ATR = """//+------------------------------------------------------------------+
//| Distancias medidas en ATR. El maximo y el minimo del rango        |
//| EXCLUYEN la vela evaluada (se arranca en shift+1), igual que el   |
//| canal de Donchian: incluirla haria que "el cierre esta a menos de |
//| X del maximo" fuera casi siempre cierto y el filtro no filtraria. |
//|                                                                   |
//| El handle del ATR se crea una sola vez por periodo pedido: uno    |
//| nuevo en cada vela agota los handles del terminal en una tarde.   |
//+------------------------------------------------------------------+
int    g_distAtrPeriod = 0;
int    g_distAtrHandle = INVALID_HANDLE;

double DistATRValue(const int period, const int shift)
  {
   if(g_distAtrHandle == INVALID_HANDLE || g_distAtrPeriod != period)
     {
      if(g_distAtrHandle != INVALID_HANDLE) IndicatorRelease(g_distAtrHandle);
      g_distAtrHandle = iATR(_Symbol, _Period, period);
      g_distAtrPeriod = period;
     }
   return Buf(g_distAtrHandle, 0, shift);
  }
double DistToHighATR(const int period, const int shift)
  {
   double atr = DistATRValue(period, shift);
   if(atr <= 0.0) return 0.0;
   int idx = iHighest(_Symbol, _Period, MODE_HIGH, period, shift + 1);
   if(idx < 0) return 0.0;
   return (iHigh(_Symbol, _Period, idx) - iClose(_Symbol, _Period, shift)) / atr;
  }
double DistToLowATR(const int period, const int shift)
  {
   double atr = DistATRValue(period, shift);
   if(atr <= 0.0) return 0.0;
   int idx = iLowest(_Symbol, _Period, MODE_LOW, period, shift + 1);
   if(idx < 0) return 0.0;
   return (iClose(_Symbol, _Period, shift) - iLow(_Symbol, _Period, idx)) / atr;
  }
double BarRangeATR(const int period, const int shift)
  {
   double atr = DistATRValue(period, shift);
   if(atr <= 0.0) return 0.0;
   return (iHigh(_Symbol, _Period, shift) - iLow(_Symbol, _Period, shift)) / atr;
  }
"""
