"""El bucle: mira el mercado, le pregunta al núcleo, y hace o anota.

Tres modos, y el orden importa porque es el orden en que conviene usarlos:

  * ``simulacro``  lee el mercado de verdad y NO manda ninguna orden. Anota lo
                   que habría hecho. No necesita clave de API: los datos de
                   mercado son públicos. Es el modo con el que se compara
                   contra el backtest antes de arriesgar nada.
  * ``practica``   opera contra el entorno VST de BingX, con plata de juguete.
  * ``real``       plata de verdad. Hay que escribirlo explícitamente.

`repetir()` es la pieza que hace todo esto comprobable: recorre un tramo de
historia barra por barra llamando al núcleo EXACTAMENTE como lo llamaría el
bucle en vivo —sin ver nunca una vela futura— y devuelve las operaciones que
habría hecho. Eso se puede comparar contra el backtest, y es la única forma de
saber que el camino en vivo hace lo mismo sin esperar semanas.

POR QUÉ EL BUCLE NO GUARDA LA POSICIÓN. Se la pregunta al adaptador en cada
vuelta. Si se corta la luz, si el stop se ejecutó del lado del exchange, si
alguien cerró a mano desde el teléfono — la verdad está siempre del otro lado, y
un bot que confía en su memoria opera sobre una realidad que ya no existe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from botiquant.core.models import StrategySpec
from botiquant.reports.bingx import leer_bingx
from botiquant.vivo.adaptador import Posicion
from botiquant.vivo.guardas import Estado, anotar_resultado, revisar
from botiquant.vivo.nucleo import (ABRIR_CORTO, ABRIR_LARGO, CERRAR, DURACION,
                                   Decision, decidir, solo_cerradas)

SIMULACRO = "simulacro"
PRACTICA = "practica"
REAL = "real"

#: Cuántas velas se piden. Tienen que alcanzar para el indicador más lento con
#: margen: una EMA de 200 necesita bastante más de 200 velas para estabilizarse,
#: y una que arranca corta da valores distintos de los del backtest sin fallar.
VELAS_MINIMAS = 500


@dataclass
class Bot:
    """Una estrategia enlazada a un mercado, con su modo de ejecución."""

    doc: dict[str, Any]
    adaptador: Any
    modo: str = SIMULACRO
    capital: float = 1000.0
    registro: list[dict[str, Any]] = field(default_factory=list)
    estado: Estado = field(default_factory=Estado)
    perdida_maxima_diaria: float = 0.0

    #: Cuando una guarda dice `detener`, el bot se apaga y no vuelve solo. Es
    #: para las situaciones donde esperar la vela que viene no arregla nada:
    #: una posición que no abrió él, el tope de pérdida del día. Reanudarlo es
    #: una decisión de una persona.
    detenido: bool = False
    motivo_detencion: str = ""

    @classmethod
    def desde_archivo(cls, ruta: str | Path, adaptador: Any,
                      modo: str = SIMULACRO, capital: float = 1000.0) -> "Bot":
        """Lee y VALIDA el archivo antes de tocar nada.

        Todo lo que puede fallar acá es gratis; lo que falle después ya cuesta.
        """
        doc = leer_bingx(Path(ruta).read_text(encoding="utf-8"))
        return cls(doc=doc, adaptador=adaptador, modo=modo, capital=capital)

    # ------------------------------------------------------------- lo básico
    @property
    def spec(self) -> StrategySpec:
        return StrategySpec.from_dict(self.doc["estrategia"])

    @property
    def simbolo(self) -> str:
        return self.doc["ejecucion"]["simbolo"]

    @property
    def timeframe(self) -> str:
        return self.doc["ejecucion"]["timeframe"]

    @property
    def manda_ordenes(self) -> bool:
        return self.modo != SIMULACRO

    def _anotar(self, d: Decision, extra: dict[str, Any] | None = None) -> dict:
        fila = {
            "cuando": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
            "modo": self.modo, "simbolo": self.simbolo,
            "accion": d.accion, "motivo": d.motivo,
            "cantidad": round(d.cantidad, 8), "precio": d.precio,
            "stop": d.stop, "objetivo": d.objetivo,
            **(extra or {}),
        }
        self.registro.append(fila)
        return fila

    # --------------------------------------------------------------- en vivo
    def paso(self, ahora: pd.Timestamp | None = None) -> dict[str, Any]:
        """Una vuelta del bucle. Devuelve lo que hizo, o por qué no hizo nada."""
        if self.detenido:
            return self._anotar(Decision(motivo=f"detenido: {self.motivo_detencion}"))
        df = self.adaptador.velas(self.simbolo, self.timeframe, VELAS_MINIMAS)
        df = solo_cerradas(df, self.timeframe, ahora)
        if len(df) < 2:
            return self._anotar(Decision(motivo="todavía no hay velas cerradas"))

        # LA POSICIÓN SE PREGUNTA, NO SE RECUERDA.
        pos: Posicion = self.adaptador.posicion(self.simbolo)
        capital = self.capital
        if self.manda_ordenes:
            try:
                capital = self.adaptador.capital()
            except Exception as exc:                      # noqa: BLE001
                return self._anotar(Decision(
                    motivo=f"no se pudo leer el saldo, no se opera: {exc}"))

        d = decidir(df, self.spec, posicion=pos.lado, capital=capital,
                    precio=float(df["close"].iloc[-1]))

        if not self.manda_ordenes:
            # En simulacro no hay cuenta ni contrato que consultar: se anota lo
            # que el nucleo decidio y listo. Meter las guardas aca haria que el
            # simulacro dependa de una clave, que es justo lo que no queremos.
            return self._anotar(d, {"simulado": True})

        # LAS GUARDAS, entre la decision y la orden.
        vela = df.index[-1]
        v = revisar(d, estado=self.estado, posicion_lado=pos.lado, vela=vela,
                    contrato=self.adaptador.contrato(self.simbolo),
                    disponible=capital, precio=float(df["close"].iloc[-1]),
                    perdida_maxima_diaria=self.perdida_maxima_diaria)
        if v.detener:
            self.detenido = True
            self.motivo_detencion = v.motivo
        if not v.permitido:
            return self._anotar(d, {"bloqueado": v.motivo, "detenido": v.detener})

        try:
            if d.accion == CERRAR:
                r = self.adaptador.cerrar(self.simbolo, pos)
                anotar_resultado(self.estado, abrio=False, cerro=True,
                                 ganancia=float(pos.no_realizado or 0.0),
                                 vela=vela)
            else:
                lado = 1 if d.accion == ABRIR_LARGO else -1
                r = self.adaptador.abrir(self.simbolo, lado, v.cantidad,
                                         d.stop, d.objetivo)
                anotar_resultado(self.estado, abrio=True, cerro=False, vela=vela)
            return self._anotar(d, {"respuesta": r, "cantidad_final": v.cantidad})
        except Exception as exc:                          # noqa: BLE001
            # Una orden que falla NO puede tumbar el bucle, pero TAMPOCO se
            # marca la vela como actuada: si el error fue de red y la orden
            # llego igual, marcarla ocultaria una posicion que si existe. La
            # vuelta siguiente pregunta la posicion y decide sobre eso.
            return self._anotar(d, {"error": str(exc)})


def repetir(df: pd.DataFrame, spec: StrategySpec, *, capital: float = 10_000.0,
            comision_pct: float = 0.0, minimo: float = 0.0,
            desde: int = 60) -> dict[str, Any]:
    """Recorre la historia como si el bot la hubiera vivido en vivo.

    En cada barra le pasa al núcleo SÓLO las velas hasta ahí —nunca una futura—
    y aplica su decisión. Es la prueba de que el camino en vivo hace lo mismo
    que el backtest, sin tener que esperar semanas para verlo.

    `desde` deja calentar los indicadores. Empezar en la vela cero no es más
    honesto: es comparar el arranque de una EMA de 200 contra la misma EMA ya
    estabilizada, y esa diferencia no tiene nada que ver con el bucle.

    Pero tampoco puede ser grande porque sí: con 200 se comía la primera
    operación de cada caso medido, y una operación de quince es 7% del
    resultado. Se deja en 60 y quien compare contra un backtest que empieza en
    la vela cero tiene que saber que las primeras señales no están.
    """
    comm = comision_pct / 100.0
    equity = capital
    pos, unidades, entrada_px, entrada_i = 0, 0.0, 0.0, 0
    stop_px = obj_px = float("nan")
    ops: list[dict[str, Any]] = []

    def cerrar(i: int, px: float, motivo: str) -> None:
        nonlocal pos, unidades, equity
        equity += pos * unidades * (px - entrada_px) - comm * unidades * px
        ops.append({"entrada": str(df.index[entrada_i]), "salida": str(df.index[i]),
                    "lado": "largo" if pos > 0 else "corto",
                    "precio_entrada": entrada_px, "precio_salida": px,
                    "unidades": unidades, "motivo": motivo})
        pos, unidades = 0, 0.0

    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)

    for i in range(desde, len(df)):
        # 1) el stop y el objetivo viven EN EL EXCHANGE: se disparan dentro de
        #    la vela, sin que el bot tenga que estar mirando
        if pos != 0 and i > entrada_i:
            if pos > 0 and l[i] <= stop_px:
                cerrar(i, stop_px, "stop")
            elif pos > 0 and h[i] >= obj_px:
                cerrar(i, obj_px, "objetivo")
            elif pos < 0 and h[i] >= stop_px:
                cerrar(i, stop_px, "stop")
            elif pos < 0 and l[i] <= obj_px:
                cerrar(i, obj_px, "objetivo")

        # 2) el bot despierta al cerrar la vela y ve SÓLO hasta acá
        ventana = df.iloc[: i + 1]
        d = decidir(ventana, spec, posicion=pos, capital=equity,
                    precio=float(c[i]), barras_en_posicion=i - entrada_i)

        # OJO CON EL CONTRATO DEL NUCLEO. `decidir` mira la posicion que se le
        # pasa: si hay una abierta y llega la senal contraria, devuelve CERRAR
        # y NADA MAS — no puede decir "cerra y abri del otro lado" en una sola
        # respuesta. Quien llama tiene que volver a preguntarle con la posicion
        # ya en cero.
        #
        # No hacerlo costaba 52% de diferencia contra el backtest: el bot
        # cerraba en la reversion y se quedaba afuera hasta la senal siguiente.
        # Es el mismo bug que tenia el Pine, en otro lugar y encontrado igual:
        # comparando los dos numeros.
        if d.accion == CERRAR and pos != 0:
            cerrar(i, float(c[i]), d.motivo)
            d = decidir(ventana, spec, posicion=0, capital=equity,
                        precio=float(c[i]))
        if d.accion in (ABRIR_LARGO, ABRIR_CORTO):
            lado = 1 if d.accion == ABRIR_LARGO else -1
            if pos != 0 and pos != lado:
                cerrar(i, float(c[i]), "reversión")
            if pos == 0:
                cant = max(d.cantidad, minimo)
                if cant > 0:
                    pos, unidades = lado, cant
                    entrada_px, entrada_i = float(c[i]), i
                    stop_px, obj_px = d.stop, d.objetivo
                    equity -= comm * cant * entrada_px

    if pos != 0:
        cerrar(len(df) - 1, float(c[-1]), "fin")

    ganadoras = [o for o in ops
                 if (1 if o["lado"] == "largo" else -1)
                 * (o["precio_salida"] - o["precio_entrada"]) > 0]
    return {"operaciones": len(ops), "equity_final": equity,
            "ganancia_neta": equity - capital,
            "aciertos_pct": 100.0 * len(ganadoras) / len(ops) if ops else 0.0,
            "ops": ops}
