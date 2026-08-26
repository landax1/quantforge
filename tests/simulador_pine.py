"""Reproduce en Python lo que hace el script de Pine que exportamos.

NO es el motor de Botiquant ni lo llama: es una relectura línea por línea del
texto que sale del exportador, con las reglas de TradingView. Existe para poder
contestar sin TradingView la única pregunta que decide si el camino de webhook
sirve — ¿el script opera lo mismo que el backtest?

Las reglas de TradingView que hay que respetar, y que son las que producen las
diferencias cuando no se respetan:

  * `process_orders_on_close=true` hace que una orden pedida en la barra `i` se
    llene al CIERRE de la barra `i`, no en la apertura de la siguiente.
  * `strategy.exit` con stop y limit se evalúa DENTRO de las barras siguientes,
    contra el máximo y el mínimo, nunca en la barra de la entrada.
  * `strategy.position_avg_price` es el precio de llenado real.
  * la comisión se cobra por lado, en porcentaje del nocional.

Es un modelo, no TradingView. Sirve para detectar divergencias sistemáticas
—que son las que importan— y no para predecir el centavo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from botiquant.core.models import StrategySpec
from botiquant.strategies.rules import EvalContext, eval_conditions, time_filter_mask


@dataclass
class OperacionPine:
    entrada_i: int
    salida_i: int
    lado: int
    precio_entrada: float
    precio_salida: float
    unidades: float
    motivo: str

    @property
    def pnl(self) -> float:
        return self.lado * self.unidades * (self.precio_salida - self.precio_entrada)


def correr_pine(df: pd.DataFrame, spec: StrategySpec, *,
                capital: float = 10_000.0, comision_pct: float = 0.0,
                minimo: float = 0.0) -> dict:
    """Corre la lógica del Pine exportado y devuelve sus operaciones."""
    ctx = EvalContext(df)
    n = ctx.n
    risk = spec.risk

    quiere_largo = spec.direction in ("long", "both") and bool(spec.entry_long)
    quiere_corto = spec.direction in ("short", "both") and bool(spec.entry_short)
    e_largo = eval_conditions(spec.entry_long, ctx) if quiere_largo else np.zeros(n, bool)
    e_corto = eval_conditions(spec.entry_short, ctx) if quiere_corto else np.zeros(n, bool)
    tmask = time_filter_mask(spec.time_filter, df.index)
    e_largo, e_corto = e_largo & tmask, e_corto & tmask

    atr = ctx.cache.get("ATR", {"period": float(risk.atr_period)})["value"]
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)

    comm = comision_pct / 100.0
    equity = capital
    pos = 0
    unidades = 0.0
    entrada_px = 0.0
    entrada_i = 0
    atr_entrada = np.nan
    ops: list[OperacionPine] = []

    def cerrar(i: int, px: float, motivo: str) -> None:
        nonlocal pos, unidades, equity
        bruto = pos * unidades * (px - entrada_px)
        equity += bruto - comm * unidades * px
        ops.append(OperacionPine(entrada_i, i, pos, entrada_px, px,
                                 unidades, motivo))
        pos, unidades = 0, 0.0

    for i in range(n):
        # 1) las salidas se comprueban DENTRO de la barra, y nunca en la de
        #    entrada: strategy.exit recién rige desde la barra siguiente
        if pos != 0 and i > entrada_i and not np.isnan(atr_entrada):
            stop = entrada_px - pos * risk.stop_value * atr_entrada
            obj = entrada_px + pos * risk.target_value * atr_entrada
            # OJO: cerrar y seguir, sin `continue`. Con `continue` la barra
            # del stop no evaluaba la entrada, y una estrategia que se frena y
            # cruza en la misma vela perdia esa operacion. TradingView SI
            # entra: la posicion ya quedo plana cuando el script corre al
            # cierre. Costo dos entradas de quince en la primera medicion.
            if pos > 0:
                if l[i] <= stop:
                    cerrar(i, min(stop, o[i]), "stop")
                elif h[i] >= obj:
                    cerrar(i, max(obj, o[i]), "objetivo")
            else:
                if h[i] >= stop:
                    cerrar(i, max(stop, o[i]), "stop")
                elif l[i] <= obj:
                    cerrar(i, min(obj, o[i]), "objetivo")

        # 2) salida por tiempo
        if (pos != 0 and risk.max_bars_in_trade > 0
                and (i - entrada_i) >= risk.max_bars_in_trade):
            cerrar(i, c[i], "tiempo")

        # 3) entradas y REVERSIONES: se llenan en el CIERRE de esta misma
        #    barra. El guardia es `pos <= 0` para largos y `pos >= 0` para
        #    cortos, igual que el script: da vuelta la posicion pero no
        #    piramida cuando ya se esta del lado correcto.
        if not np.isnan(atr[i]):
            direccion = 1 if e_largo[i] else (-1 if e_corto[i] else 0)
            if direccion != 0 and pos * direccion <= 0:
                if pos != 0:
                    cerrar(i, c[i], "reversion")
                px = c[i]
                dist = risk.stop_value * atr[i]
                if dist <= 0:
                    continue
                if risk.size_mode == "fixed_units":
                    qty = max(risk.size_value, minimo)
                else:
                    qty = max((equity * risk.size_value / 100.0) / dist, minimo)
                if qty <= 0:
                    continue
                pos, unidades = direccion, qty
                entrada_px, entrada_i = px, i
                atr_entrada = atr[i]
                equity -= comm * qty * px

    if pos != 0:
        cerrar(n - 1, c[n - 1], "fin")

    ganadoras = [x for x in ops if x.pnl > 0]
    bruto_pos = sum(x.pnl for x in ganadoras)
    bruto_neg = -sum(x.pnl for x in ops if x.pnl <= 0)
    return {
        "operaciones": len(ops),
        "equity_final": equity,
        "ganancia_neta": equity - capital,
        "aciertos_pct": 100.0 * len(ganadoras) / len(ops) if ops else 0.0,
        "profit_factor": (bruto_pos / bruto_neg) if bruto_neg > 0 else float("inf"),
        "ops": ops,
    }
