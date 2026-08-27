"""En qué punto del camino está cada estrategia, y el cementerio.

Hasta ahora todo lo guardado vivía en la misma lista: la que acabás de
encontrar, la que corriste seis meses en demo y la que se fundió. Mezcladas no
se puede decidir nada — hay que abrir cada una para acordarse de qué era.

LA DIFERENCIA CON LA CANTERA, que es fácil de confundir:

    la cantera dice hasta dónde PODRÍA llegar   (se calcula de las métricas)
    el estado dice dónde ESTÁ                    (se guarda, lo movés vos)

Una estrategia puede estar habilitada para real y no haberse encendido nunca.
Son dos cosas distintas y por eso viven separadas: si el estado se dedujera de
las métricas, encender un bot no cambiaría nada en la pantalla.

EL CEMENTERIO NO ES UN TACHO. Es para no repetir el mismo error. Si una murió
porque el spread nocturno se comía la ventaja, la próxima con ese perfil va a
morir igual — y sin registro la volvés a encontrar en seis meses y la volvés a
encender. Por eso retirar EXIGE un motivo.

Y LA REGLA QUE MÁS CUESTA RESPETAR: una estrategia retirada no vuelve a donde
estaba. Vuelve al principio. Reactivarla en producción "porque venía teniendo
mala suerte" es exactamente el movimiento con el que se pierde plata, y es
justo el que uno quiere hacer a las once de la noche.
"""

from __future__ import annotations

from typing import Any

NUEVA = "nueva"
VALIDADA = "validada"
PRACTICA = "practica"
PRODUCCION = "produccion"
RETIRADA = "retirada"

#: El orden del camino. Sirve para ordenar la lista y para saber qué sigue.
ORDEN = [NUEVA, VALIDADA, PRACTICA, PRODUCCION]

TODOS = ORDEN + [RETIRADA]

#: Qué se puede hacer desde cada estado.
#:
#: No es burocracia: cada salto de más es un camino que alguien puede tomar sin
#: haber pasado por el anterior. Saltar de `nueva` a `produccion` es encender
#: con plata algo que nunca se probó, y es exactamente lo que la cantera y esto
#: existen para impedir.
TRANSICIONES: dict[str, set[str]] = {
    NUEVA: {VALIDADA, RETIRADA},
    VALIDADA: {PRACTICA, NUEVA, RETIRADA},
    PRACTICA: {PRODUCCION, VALIDADA, RETIRADA},
    # De producción se puede bajar a práctica: es lo que recomienda el semáforo
    # cuando la ventaja se deteriora, y tiene que ser un paso barato para que
    # alguien lo dé en vez de dejarlo corriendo.
    PRODUCCION: {PRACTICA, RETIRADA},
    # Y del cementerio SÓLO se vuelve al principio. Ver el encabezado.
    RETIRADA: {NUEVA},
}


class EstadoError(ValueError):
    """Un movimiento que no corresponde, con un texto que se puede mostrar."""


def normalizar(estado: Any) -> str:
    """El estado guardado, o `nueva` si viene vacío o desconocido.

    Las estrategias que ya existían no tienen ninguno: se guardaron antes de
    que esto existiera. Tratarlas como nuevas es lo correcto —nadie las validó
    ni las corrió— y evita tener que migrar nada.
    """
    e = str(estado or "").strip().lower()
    return e if e in TODOS else NUEVA


def puede(desde: str, hasta: str) -> bool:
    return normalizar(hasta) in TRANSICIONES[normalizar(desde)]


def mover(desde: str, hasta: str, *, motivo: str = "") -> dict[str, Any]:
    """Valida el movimiento y devuelve lo que hay que guardar.

    `motivo` es obligatorio para retirar. Un cementerio sin autopsias es una
    lista de nombres: no sirve para lo único que tiene que servir, que es no
    volver a encender lo mismo.
    """
    desde, hasta = normalizar(desde), normalizar(hasta)
    if desde == hasta:
        raise EstadoError(f"Ya está en {hasta}.")
    if not puede(desde, hasta):
        if desde == RETIRADA:
            raise EstadoError(
                "Una estrategia retirada vuelve al principio, no a donde "
                "estaba. Si querés volver a usarla, tiene que rehacer el "
                "camino: validarla, probarla en demo, y recién ahí operarla.")
        raise EstadoError(
            f"No se puede pasar de {desde} a {hasta} directamente. "
            f"Desde {desde} se puede ir a: {', '.join(sorted(TRANSICIONES[desde]))}.")
    if hasta == RETIRADA and not motivo.strip():
        raise EstadoError(
            "Para retirarla hace falta decir por qué. Sin eso el cementerio es "
            "una lista de nombres, y la próxima con el mismo problema se "
            "enciende igual.")

    cambio: dict[str, Any] = {"estado": hasta}
    if hasta == RETIRADA:
        cambio["retiro"] = {"motivo": motivo.strip(), "desde": desde}
    elif desde == RETIRADA:
        # Se limpia al salir: dejar la autopsia vieja pegada a una estrategia
        # que volvió a empezar hace creer que sigue retirada.
        cambio["retiro"] = None
    return cambio


def siguiente(estado: str) -> str | None:
    """El próximo paso del camino, o None si no hay."""
    e = normalizar(estado)
    if e == RETIRADA or e == PRODUCCION:
        return None
    return ORDEN[ORDEN.index(e) + 1]


def resumen(filas: list[dict[str, Any]]) -> dict[str, int]:
    """Cuántas hay en cada estado. Para el encabezado de la lista."""
    cuenta = {e: 0 for e in TODOS}
    for f in filas:
        cuenta[normalizar(f.get("estado"))] += 1
    return cuenta
