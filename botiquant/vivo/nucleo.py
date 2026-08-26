"""Qué hacer ahora mismo, decidido con el mismo motor que corrió el backtest.

No sabe qué exchange existe, no toca la red y no guarda estado. Se le dan las
velas y la posición que el exchange dice tener, y devuelve una decisión. Todo
lo que puede salir mal acá sale mal en una prueba, gratis.

LA REGLA DE ORO: LA SEÑAL ES DE LA VELA CERRADA, LA EJECUCIÓN ES LA SIGUIENTE.
El motor evalúa las condiciones en la barra `i-1` y llena la orden en la
apertura de la barra `i`. En vivo eso significa: cuando una vela CIERRA, se
mira su señal y se opera de inmediato, al precio de ese momento —que es
exactamente la apertura de la vela nueva.

Hacerlo distinto rompe la correspondencia con el backtest de las dos formas
posibles: mirar la vela en formación adelanta la señal (y da una ventaja que no
existe), y esperar a la vela siguiente la atrasa una barra entera.

POR QUÉ HAY QUE TIRAR LA ÚLTIMA VELA. Medido contra la API de BingX: la lista
incluye la vela EN CURSO, la que todavía se está formando. Un cierre que
todavía no ocurrió hace que las señales aparezcan y desaparezcan dentro de la
misma hora, y el bot entraría y saldría siguiendo un número provisorio.

UNA DIFERENCIA HONESTA CON EL BACKTEST. Para el stop por ATR, el motor usa el
ATR de la barra en la que entra. En vivo esa barra recién empieza y su ATR no
existe todavía, así que se usa el de la última cerrada. Es una barra de
diferencia y no hay forma de evitarlo sin mirar el futuro. Queda anotado acá
porque explica por qué el simulacro y el backtest no van a dar idénticos al
centavo, y conviene saberlo de antemano en vez de descubrirlo y asustarse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from botiquant.core.models import StrategySpec
from botiquant.strategies.rules import EvalContext, eval_conditions, time_filter_mask

#: Cuánto dura una vela de cada temporalidad, en segundos.
DURACION = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "1d": 86400}

#: Las acciones posibles. Son pocas a propósito: el runner tiene que poder
#: manejarlas todas y cada una nueva es un camino más que puede fallar con
#: plata puesta.
NADA = "nada"
ABRIR_LARGO = "abrir_largo"
ABRIR_CORTO = "abrir_corto"
CERRAR = "cerrar"


@dataclass
class Decision:
    """Lo que habría que hacer, y por qué.

    `motivo` no es decorativo: es lo que se escribe en el registro y lo único
    que después permite entender por qué el bot hizo lo que hizo. Un registro
    que dice "abrió" y no dice por qué no sirve para nada.
    """

    accion: str = NADA
    motivo: str = ""
    cantidad: float = 0.0
    stop: float = float("nan")
    objetivo: float = float("nan")
    #: El precio con el que se calculó todo. El exchange va a llenar a otro
    #: precio y está bien: sirve para medir cuánto se deslizó.
    precio: float = float("nan")
    #: Datos sueltos para el registro; nunca para decidir.
    detalle: dict[str, Any] = field(default_factory=dict)

    @property
    def opera(self) -> bool:
        return self.accion != NADA


def solo_cerradas(df: pd.DataFrame, intervalo: str,
                  ahora: pd.Timestamp | None = None) -> pd.DataFrame:
    """Saca la vela que todavía se está formando.

    Se compara contra el reloj y no se tira la última a ciegas: si el exchange
    ya no la mandó —pasa cuando se pide justo después de un cierre— tirarla
    igual perdería una vela buena y atrasaría todas las señales una barra.
    """
    if df.empty:
        return df
    dur = DURACION.get(intervalo)
    if not dur:
        raise ValueError(f"Temporalidad desconocida: {intervalo}")
    ahora = ahora or pd.Timestamp.now(tz="UTC")
    cierra = df.index[-1] + pd.Timedelta(seconds=dur)
    return df.iloc[:-1] if cierra > ahora else df


def _atr(ctx: EvalContext, periodo: int) -> float:
    a = ctx.cache.get("ATR", {"period": float(periodo)})["value"]
    return float(a[-1]) if len(a) else float("nan")


def _distancia(kind: str, valor: float, precio: float, atr: float) -> float:
    """La misma cuenta que hace el motor para un stop o un objetivo."""
    if kind == "atr":
        return valor * atr if not np.isnan(atr) else float("nan")
    if kind == "percent":
        return precio * valor / 100.0
    if kind == "points":
        return valor
    return float("nan")           # "none", o "money" que necesita el tamaño


def _tamanio(risk: Any, precio: float, stop: float, capital: float) -> float:
    """El mismo dimensionamiento que el motor.

    Está duplicado del motor a propósito y con una prueba que compara los dos
    contra el mismo caso: el del motor es una función anidada que necesita todo
    el estado del backtest alrededor, y arrastrarlo hasta acá para reusar diez
    líneas ataría el bot en vivo a la maquinaria del backtest entera.
    """
    if risk.size_mode == "fixed_units":
        return max(risk.size_value, 0.0)
    if (risk.size_mode == "risk_pct" and not np.isnan(stop)
            and abs(precio - stop) > 1e-12):
        return (capital * risk.size_value / 100.0) / abs(precio - stop)
    pct = risk.size_value if risk.size_mode == "percent_equity" else 100.0
    return (capital * pct / 100.0) / precio


def decidir(df: pd.DataFrame, spec: StrategySpec, *,
            posicion: int = 0, capital: float = 0.0,
            precio: float | None = None, barras_en_posicion: int = 0) -> Decision:
    """Qué hacer al cerrar la última vela de `df`.

    `df` tiene que traer SÓLO velas cerradas: pasarle la que se está formando
    adelanta las señales. Usá `solo_cerradas()` antes.

    `posicion` es +1, -1 o 0, y sale de preguntarle al EXCHANGE, no de lo que
    el bot crea recordar. Si se cortó la luz a mitad de una operación, la
    verdad está del lado del exchange.
    """
    if len(df) < 2:
        return Decision(motivo="todavía no hay suficientes velas")

    ctx = EvalContext(df)
    n = ctx.n
    risk = spec.risk

    quiere_largo = spec.direction in ("long", "both") and bool(spec.entry_long)
    quiere_corto = spec.direction in ("short", "both") and bool(spec.entry_short)

    e_largo = eval_conditions(spec.entry_long, ctx) if quiere_largo else np.zeros(n, bool)
    e_corto = eval_conditions(spec.entry_short, ctx) if quiere_corto else np.zeros(n, bool)
    s_largo = eval_conditions(spec.exit_long, ctx) if spec.exit_long else np.zeros(n, bool)
    s_corto = eval_conditions(spec.exit_short, ctx) if spec.exit_short else np.zeros(n, bool)

    # La franja horaria filtra las ENTRADAS y no las salidas, igual que en el
    # motor: una estrategia que sólo opera de mañana igual tiene que poder
    # cerrar a la tarde lo que abrió.
    tmask = time_filter_mask(spec.time_filter, df.index)
    e_largo = e_largo & tmask
    e_corto = e_corto & tmask

    precio = float(precio if precio is not None else df["close"].iloc[-1])

    # ---------------------------------------------------------------- salidas
    if posicion != 0:
        if posicion > 0 and (s_largo[-1] or e_corto[-1]):
            return Decision(CERRAR, "señal de salida en largo", precio=precio)
        if posicion < 0 and (s_corto[-1] or e_largo[-1]):
            return Decision(CERRAR, "señal de salida en corto", precio=precio)
        if (risk.max_bars_in_trade > 0
                and barras_en_posicion >= risk.max_bars_in_trade):
            return Decision(
                CERRAR, f"cumplió el máximo de {risk.max_bars_in_trade} velas",
                precio=precio)
        return Decision(motivo="posición abierta, sin señal de salida")

    # ---------------------------------------------------------------- entradas
    direccion = 1 if e_largo[-1] else (-1 if e_corto[-1] else 0)
    if direccion == 0:
        return Decision(motivo="sin señal")
    if capital <= 0:
        return Decision(motivo="sin capital disponible")

    atr = _atr(ctx, risk.atr_period) if "atr" in (risk.stop_type, risk.target_type) else float("nan")
    d_stop = _distancia(risk.stop_type, risk.stop_value, precio, atr)
    d_obj = _distancia(risk.target_type, risk.target_value, precio, atr)
    stop = precio - direccion * d_stop if not np.isnan(d_stop) else float("nan")
    objetivo = precio + direccion * d_obj if not np.isnan(d_obj) else float("nan")

    # Un stop pedido que no se puede calcular —el ATR sigue calentando— NO
    # puede terminar en una entrada sin protección. En el backtest eso produjo
    # una única operación de 134.259 velas dimensionada al 100% del capital;
    # en vivo sería una posición sin stop, que es la forma más rápida de
    # perderlo todo.
    if risk.stop_type not in ("none", "money") and np.isnan(stop):
        return Decision(motivo="hay señal pero el stop todavía no se puede calcular")

    cantidad = _tamanio(risk, precio, stop, capital)

    # Stop u objetivo en plata: recién ahora se puede, con el tamaño resuelto.
    if risk.stop_type == "money" and cantidad > 1e-12:
        stop = precio - direccion * (risk.stop_value / cantidad)
    if risk.target_type == "money" and cantidad > 1e-12:
        objetivo = precio + direccion * (risk.target_value / cantidad)

    if not (cantidad > 0):
        return Decision(motivo="hay señal pero el tamaño calculado es cero")

    return Decision(
        ABRIR_LARGO if direccion > 0 else ABRIR_CORTO,
        "señal de entrada", cantidad=cantidad, stop=stop, objetivo=objetivo,
        precio=precio,
        detalle={"atr": atr, "vela": str(df.index[-1]), "capital": capital})
