"""Exportar un conjunto de EA que van a convivir en una cuenta de MetaTrader.

La diferencia con exportar cinco veces de a uno no es comodidad: es que un
portafolio tiene propiedades que ningún archivo suelto tiene. El reparto del
capital, la concentración por instrumento y el riesgo combinado sólo existen
mirando el conjunto, y exportando de a uno nadie los mira nunca.

DOS COSAS QUE SOLO SE PUEDEN HACER ACA:

  * repartir el capital. Cada EA se dimensiona sobre SU porción, y las
    porciones tienen que sumar la cuenta. Con cinco archivos exportados por
    separado, cada uno se cree dueño del 100% y entre todos arriesgan cinco
    veces lo que se pidió.
  * decir la verdad sobre la concentración. Tres EA de Bitcoin no son tres
    apuestas: medido, dos estrategias del mismo instrumento correlacionan
    +0,64 a +0,71 y entre instrumentos distintos van de -0,18 a +0,11.

EL REPARTO ES IGUALITARIO Y ESO NO ES PEREZA. Existen métodos que reparten
según el riesgo de cada una, y son mejores en teoría. Pero necesitan estimar
correlaciones y volatilidades a futuro a partir del pasado, y esa estimación
es ruidosa: con muestras cortas, los métodos sofisticados reparten peor que
partir por igual porque amplifican el error de estimación.

Con cinco estrategias y meses de historia en vivo, partir por igual es lo
honesto. Cuando haya años de datos propios se puede revisar — y ahí conviene
mirar la literatura en vez de inventar la fórmula.

LO QUE NO HACE: apagar nada. Si el conjunto está concentrado, lo dice y
exporta igual. Es el usuario el que arma su cartera, no nosotros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Desde cuántas del mismo instrumento avisamos. Ver el encabezado: con dos
#: todavía se puede argumentar que son distintas; con tres es concentración.
CONCENTRADO_DESDE = 3


@dataclass
class Aviso:
    """Algo que conviene saber antes de encender el conjunto."""

    clave: str
    texto: str


@dataclass
class Reparto:
    """Cómo queda el capital repartido, y qué conviene mirar."""

    porciones: dict[str, float] = field(default_factory=dict)
    avisos: list[Aviso] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(self.porciones.values()), 4)


def repartir(estrategias: list[dict[str, Any]], *,
             usar_pct: float = 100.0) -> Reparto:
    """Reparte la cuenta entre las estrategias y avisa lo que haga falta.

    `usar_pct` es cuánto de la cuenta se pone a trabajar. Menos de 100 deja
    un colchón: el informe del que salió esto opera al 89% y guarda el resto
    como margen libre, porque una cuenta al 100% no aguanta que dos posiciones
    se muevan en contra a la vez.
    """
    n = len(estrategias)
    if n == 0:
        return Reparto()

    usar_pct = max(1.0, min(float(usar_pct), 100.0))
    cada = round(usar_pct / n, 4)
    porciones = {str(e.get("id") or e.get("name")): cada for e in estrategias}

    avisos: list[Aviso] = []

    # ---------------------------------------------------- la concentración
    por_inst: dict[str, list[str]] = {}
    for e in estrategias:
        inst = str((e.get("meta") or {}).get("dataset_name")
                   or (e.get("meta") or {}).get("dataset_id") or "")
        if inst:
            por_inst.setdefault(inst, []).append(str(e.get("name") or e.get("id")))

    for inst, cuales in sorted(por_inst.items()):
        if len(cuales) >= CONCENTRADO_DESDE:
            avisos.append(Aviso(
                "concentracion",
                f"{len(cuales)} de {n} operan {inst}. Medido, dos estrategias "
                f"del mismo instrumento se mueven casi juntas: eso no es "
                f"diversificar, es la misma apuesta con varios nombres."))

    if len(por_inst) == 1 and n > 1:
        avisos.append(Aviso(
            "un_solo_mercado",
            "Todas operan el mismo mercado. Si ese mercado se da vuelta, se "
            "dan vuelta todas a la vez."))

    # ------------------------------------------------------- el colchón
    if usar_pct >= 100.0 and n > 1:
        avisos.append(Aviso(
            "sin_colchon",
            "La cuenta queda al 100%. Conviene dejar un margen libre: dos "
            "posiciones moviéndose en contra a la vez necesitan aire."))

    # ------------------------------------------------- porciones diminutas
    if cada < 2.0:
        avisos.append(Aviso(
            "porciones_chicas",
            f"Cada bot maneja {cada}% de la cuenta. Con porciones tan chicas "
            f"el lote mínimo del bróker puede quedar por encima de lo que la "
            f"estrategia quiere arriesgar, y va a operar más grande de lo "
            f"pedido o no operar."))

    return Reparto(porciones, avisos)


def resumen(estrategias: list[dict[str, Any]], reparto: Reparto) -> dict[str, Any]:
    """Lo que se muestra antes de bajar el conjunto.

    Se arma acá y no en la pantalla para que el número que se ve y el que va
    adentro de cada EA salgan del mismo cálculo.
    """
    return {
        "cuantas": len(estrategias),
        "porciones": reparto.porciones,
        "usado_pct": reparto.total,
        "libre_pct": round(100.0 - reparto.total, 4),
        "avisos": [{"clave": a.clave, "texto": a.texto} for a in reparto.avisos],
    }
