"""¿El bot está operando como decía que iba a operar?

No mira si gana o pierde: mira CUÁNTO OPERA. Es una pregunta distinta y se
puede contestar mucho antes, porque la frecuencia se estabiliza más rápido que
el resultado.

QUÉ DETECTA QUE NADIE MÁS DETECTA. Un bot que deberia abrir tres veces por
semana y lleva un mes sin abrir ninguna no está "teniendo un mal mes": está
roto. Y roto de las maneras que no dan error —el exchange rechazando por
tamaño mínimo, la clave sin permiso de trading, el símbolo mal escrito, una
guarda demasiado estricta— porque las que sí dan error ya las agarra el
piloto. Lo mismo al revés: uno que abre diez veces más de lo esperado está
operando otra cosa.

LA PARTE QUE MÁS IMPORTA ES CUÁNDO CALLARSE. Medido sobre las estrategias
guardadas al escribir esto: operan entre 0,13 y 0,70 veces por semana. Con
0,13 esperadas hay que esperar DOS MESES para ver una. Decir "no está
operando" a las dos semanas no es una alerta temprana, es ruido — y un
vigilante que grita cuando no sabe se apaga a la semana, que es peor que no
tenerlo.

Por eso no opina hasta que la cantidad ESPERADA alcance un mínimo. Si el bot
tendría que haber abierto tres veces y no abrió ninguna, la probabilidad de
que sea casualidad es del 5%; con una esperada, es del 37% y no hay nada que
decir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

#: Cuántas operaciones tiene que ESPERAR el bot antes de que valga la pena
#: opinar sobre su silencio. Con tres esperadas, no ver ninguna tiene 5% de
#: probabilidad de ser casualidad (e^-3); con una, 37%.
ESPERADAS_MINIMAS = 3.0

#: Cuánto puede desviarse la frecuencia observada antes de llamar la atención.
#: Amplio a propósito: la frecuencia de una estrategia varía sola con el
#: régimen del mercado, y estrechar esto convierte al vigilante en alguien que
#: avisa todo el tiempo.
BANDA = (0.4, 2.5)

VERDE = "verde"
AMARILLO = "amarillo"
CALLADO = "callado"       # todavía no hay con qué opinar


@dataclass
class Veredicto:
    estado: str
    esperadas: float
    observadas: int
    razon: str = ""

    @property
    def opina(self) -> bool:
        return self.estado != CALLADO


def por_semana(respaldo: dict[str, Any]) -> float | None:
    """Cuántas operaciones por semana decía el backtest. None si no se sabe."""
    ops = respaldo.get("trades")
    anios = respaldo.get("years")
    if not ops or not anios or anios <= 0:
        return None
    return float(ops) / (float(anios) * 52.0)


def revisar(respaldo: dict[str, Any], registro: list[dict[str, Any]],
            desde: str | pd.Timestamp | None = None,
            ahora: pd.Timestamp | None = None) -> Veredicto:
    """Compara lo que el bot abrió contra lo que el backtest decía.

    `registro` son las vueltas del bot; se cuentan las que abrieron posición.
    `desde` es cuándo se encendió: sin eso no hay ventana que medir.
    """
    ahora = ahora or pd.Timestamp.now(tz="UTC")
    tasa = por_semana(respaldo)
    if tasa is None:
        return Veredicto(CALLADO, 0.0, 0,
                         "el backtest no dice cuántas operaciones esperaba")
    if desde is None:
        return Veredicto(CALLADO, 0.0, 0, "todavía no arrancó")

    semanas = max((ahora - pd.Timestamp(desde)).total_seconds() / 604800.0, 0.0)
    esperadas = tasa * semanas
    observadas = sum(1 for f in registro
                     if str(f.get("accion", "")).startswith("abrir"))

    if esperadas < ESPERADAS_MINIMAS:
        # No es que esté bien: es que todavía no se puede saber, y decir que
        # está bien seria tan equivocado como decir que está mal.
        faltan = (ESPERADAS_MINIMAS - esperadas) / tasa if tasa > 0 else 0
        return Veredicto(
            CALLADO, esperadas, observadas,
            f"hacen falta {faltan:.0f} semanas más para poder decir algo "
            f"(esta estrategia opera {tasa:.2f} veces por semana)")

    if observadas == 0:
        return Veredicto(
            AMARILLO, esperadas, observadas,
            f"esperaba {esperadas:.1f} operaciones y no abrió ninguna. "
            f"Revisá que la clave tenga permiso de trading y que el tamaño "
            f"mínimo del exchange entre con este capital.")

    razon_de = observadas / esperadas
    if razon_de < BANDA[0]:
        return Veredicto(
            AMARILLO, esperadas, observadas,
            f"abrió {observadas} y esperaba {esperadas:.1f}. Opera menos de lo "
            f"medido: puede ser el mercado, o algo que le está bloqueando "
            f"entradas.")
    if razon_de > BANDA[1]:
        return Veredicto(
            AMARILLO, esperadas, observadas,
            f"abrió {observadas} y esperaba {esperadas:.1f}. Opera mucho más "
            f"de lo medido: eso no es la estrategia que se probó.")

    return Veredicto(VERDE, esperadas, observadas,
                     f"abrió {observadas}, esperaba {esperadas:.1f}")
