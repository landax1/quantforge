"""Las puertas que una estrategia tiene que pasar antes de tocar plata.

Hoy se puede encender en modo real una estrategia de nueve operaciones. Esto
es lo que lo impide, y es la pieza que convierte a la aplicación en un proceso
en vez de una colección de herramientas: no informa, DECIDE.

TRES DESTINOS Y TRES VARAS, no una sola. Es lo que hace que sirva:

  * simulacro  no pide nada. Es gratis, no manda órdenes, y su único propósito
               es que alguien mire qué haría el bot. Poner una vara acá es
               impedirle a la gente mirar.
  * práctica   pide lo mínimo para que valga la pena mirar: una muestra que no
               sea ruido y algo de ventaja. Con plata de juguete, el costo de
               equivocarse es el tiempo.
  * real       pide todo, y en particular pide EVIDENCIA FUERA DE MUESTRA. Es
               la única puerta donde equivocarse cuesta plata.

LA REGLA MÁS IMPORTANTE ES LA DEL TAMAÑO DE MUESTRA, y es la que más se
resiste. Un profit factor de 32 sobre nueve operaciones no es una estrategia
excepcional: son nueve tiradas de moneda que salieron bien. Rechazarla se
siente como dejar plata en la mesa y es exactamente al revés.

LO QUE FALTA NO PASA. Si una métrica no está —porque la estrategia se guardó
con una versión vieja, porque no se reservó tramo fuera de muestra— la puerta
NO se da por cumplida. La ausencia de evidencia no es evidencia: dar por buena
una métrica que nadie midió es la forma más silenciosa de saltarse el filtro
entero.

LOS UMBRALES SON DISCUTIBLES Y ESTÁN A LA VISTA. Los de `real` salen de la
práctica del rubro; medidos contra las cuatro estrategias que había guardadas
al escribir esto, NINGUNA los pasa —el Sharpe > 2 es el que más pega—. Eso no
es un error del filtro: es lo que el filtro tiene para decir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SIMULACRO = "simulacro"
PRACTICA = "practica"
REAL = "real"


@dataclass(frozen=True)
class Vara:
    """Un umbral, con el nombre de la métrica y de qué lado hay que estar."""

    metrica: str
    minimo: float | None = None
    maximo: float | None = None
    #: Dónde buscar el valor: en las métricas de todo el período, o en las del
    #: tramo que la búsqueda NO vio. La diferencia es la razón de ser de todo.
    fuera_de_muestra: bool = False

    def mide(self, metricas: dict[str, Any], oos: dict[str, Any] | None) -> Any:
        origen = oos if self.fuera_de_muestra else metricas
        return (origen or {}).get(self.metrica)


#: Las varas de cada destino. Están acá arriba, juntas y legibles, a propósito:
#: son la política del producto y tienen que poder discutirse sin leer código.
VARAS: dict[str, list[Vara]] = {
    SIMULACRO: [],
    PRACTICA: [
        Vara("trades", minimo=30),
        Vara("profit_factor", minimo=1.1),
        Vara("max_drawdown_pct", maximo=40.0),
    ],
    REAL: [
        Vara("trades", minimo=100),
        Vara("profit_factor", minimo=1.3),
        Vara("expectancy_r", minimo=0.15),
        Vara("max_drawdown_pct", maximo=20.0),
        # Y la mitad que importa: que haya aguantado donde la búsqueda no miró.
        Vara("trades", minimo=50, fuera_de_muestra=True),
        Vara("profit_factor", minimo=1.0, fuera_de_muestra=True),
    ],
}


@dataclass
class Resultado:
    """Si pasa, y el detalle de cada vara para poder mostrarlo."""

    destino: str
    pasa: bool
    puertas: list[dict[str, Any]] = field(default_factory=list)

    @property
    def faltan(self) -> list[dict[str, Any]]:
        return [p for p in self.puertas if not p["pasa"]]


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"
    return str(v)


def revisar(meta: dict[str, Any], destino: str) -> Resultado:
    """¿Puede esta estrategia ir a ese destino?

    `meta` es lo que se guarda con una estrategia: trae `metrics` y, cuando la
    búsqueda reservó un tramo, `oos`.
    """
    if destino not in VARAS:
        raise ValueError(f"Destino desconocido: {destino}")

    metricas = meta.get("metrics") or {}
    oos = meta.get("oos")
    puertas: list[dict[str, Any]] = []

    for v in VARAS[destino]:
        valor = v.mide(metricas, oos)
        if valor is None:
            # No se da por cumplida. Ver el encabezado: la ausencia de
            # evidencia no es evidencia.
            pasa, motivo = False, "sin medir"
        elif v.minimo is not None and float(valor) < v.minimo:
            pasa, motivo = False, f"{_fmt(valor)} < {_fmt(v.minimo)}"
        elif v.maximo is not None and float(valor) > v.maximo:
            pasa, motivo = False, f"{_fmt(valor)} > {_fmt(v.maximo)}"
        else:
            pasa, motivo = True, _fmt(valor)
        puertas.append({
            "metrica": v.metrica, "fuera_de_muestra": v.fuera_de_muestra,
            "minimo": v.minimo, "maximo": v.maximo,
            "valor": valor, "pasa": pasa, "detalle": motivo,
        })

    return Resultado(destino, all(p["pasa"] for p in puertas), puertas)


def por_que_no(res: Resultado) -> str:
    """Una frase que explique el rechazo, para mostrar sin hacer clic.

    Se nombra la vara que más lejos está y no todas: una lista de seis
    incumplimientos no se lee, y la primera ya alcanza para saber qué hacer.
    """
    faltan = res.faltan
    if not faltan:
        return ""
    sin_medir = [p for p in faltan if p["detalle"] == "sin medir"]
    if sin_medir:
        p = sin_medir[0]
        donde = " fuera de muestra" if p["fuera_de_muestra"] else ""
        return (f"falta medir {p['metrica']}{donde}. Volvé a buscarla "
                f"reservando un tramo de validación.")
    p = faltan[0]
    donde = " fuera de muestra" if p["fuera_de_muestra"] else ""
    return f"{p['metrica']}{donde}: {p['detalle']}"
