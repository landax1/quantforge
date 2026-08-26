"""Lo último que se pregunta antes de mandar una orden con plata.

El núcleo decide qué convendría hacer mirando sólo el mercado. Esto decide si
se puede hacer de verdad, mirando la cuenta, el contrato y lo que ya pasó hoy.
Son dos preguntas distintas y por eso viven separadas: el núcleo tiene que
poder probarse con velas inventadas, y esto tiene que poder probarse sin velas.

EL ORDEN DE LAS GUARDAS NO ES CASUAL. Van de la que más barato es descubrir a
la que más caro, y la primera que dice que no corta. Comprobar el mínimo del
contrato antes de leer el saldo evita un pedido a la red; comprobar la posición
huérfana antes que todo lo demás evita operar sobre una realidad que no
entendemos.

LA GUARDA MÁS IMPORTANTE ES LA DE LA POSICIÓN HUÉRFANA. Si el exchange dice que
hay una posición abierta y este bot no la abrió —porque se cerró la aplicación,
porque se corto la luz, porque alguien operó a mano desde el teléfono— el bot NO
sigue. No la adopta, no la cierra, no la ignora: se detiene y avisa.

Adoptarla sería lo cómodo y es exactamente lo que no hay que hacer: el bot no
sabe a qué precio se abrió, con qué stop, ni si es de esta estrategia. Un stop
calculado sobre una entrada que no ocurrió es peor que no tener stop, porque
parece que hay protección.

NO HAY REANUDACIÓN AUTOMÁTICA, Y ES DELIBERADO. Esta versión opera mientras la
aplicación está abierta. Si se cierra o se cae, al volver muestra qué hay y
pregunta. La recuperación automática tras un reinicio es justo el lugar donde
nacen las órdenes duplicadas, y duplicar una orden con plata real cuesta el
doble de lo que cuesta no operar un rato.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from botiquant.vivo.nucleo import ABRIR_CORTO, ABRIR_LARGO, CERRAR, Decision


@dataclass
class Veredicto:
    """Si se puede operar, y con qué cantidad exacta."""

    permitido: bool
    motivo: str = ""
    cantidad: float = 0.0
    #: True cuando el bot tiene que dejar de operar hasta que una persona mire.
    #: Distinto de un "no" pasajero: acá no alcanza con esperar la vela que
    #: viene, porque la vela que viene va a encontrar exactamente lo mismo.
    detener: bool = False


@dataclass
class Estado:
    """Lo que el bot sabe de su propia sesión. Se pierde al cerrar, a propósito.

    Guardarlo en disco haría que al reabrir la aplicación creyera conocer una
    posición que en realidad no vio abrirse. Prefiero que al arrancar no sepa
    nada y lo diga.
    """

    #: La vela sobre la que ya se actuó. Es la defensa contra duplicados: si el
    #: bucle se despierta dos veces en la misma vela —porque el usuario apretó
    #: dos veces, porque el reloj se corrió, porque el pedido tardó— la segunda
    #: no hace nada.
    ultima_vela: pd.Timestamp | None = None

    #: Si ESTE bot abrió la posición que hay ahora.
    posicion_propia: bool = False

    #: Ganancia y pérdida realizada del día, para el tope diario.
    perdida_del_dia: float = 0.0
    dia: str = ""

    #: Todo lo que se decidió y por qué. Un bot sin registro no se puede
    #: auditar, y el día que haga algo raro no va a haber forma de saber qué
    #: vio cuando lo hizo.
    eventos: list[dict[str, Any]] = field(default_factory=list)


def _redondear_abajo(cantidad: float, decimales: int) -> float:
    """Hacia abajo, nunca al más cercano.

    Redondear hacia arriba opera MÁS de lo que se dimensionó, y el tamaño sale
    de un porcentaje de riesgo que alguien eligió a propósito.
    """
    paso = 10.0 ** -decimales
    return round(math.floor(abs(cantidad) / paso) * paso, decimales)


def revisar(d: Decision, *, estado: Estado, posicion_lado: int,
            vela: pd.Timestamp, contrato: dict[str, Any],
            disponible: float, precio: float,
            perdida_maxima_diaria: float = 0.0) -> Veredicto:
    """¿Se puede mandar esta orden? Devuelve el veredicto y la cantidad final."""

    # ------------------------------------------------- 1) la posición huérfana
    if posicion_lado != 0 and not estado.posicion_propia:
        return Veredicto(
            False, detener=True,
            motivo=("Hay una posición abierta en el exchange que este bot no "
                    "abrió. Puede ser de otra sesión, de otra estrategia o "
                    "abierta a mano. No se opera hasta que la revises: cerrala "
                    "o dejala, pero decidilo vos."))

    # ------------------------------------------------------ 2) el tope diario
    hoy = str(vela.date())
    if estado.dia != hoy:
        estado.dia, estado.perdida_del_dia = hoy, 0.0
    if (perdida_maxima_diaria > 0
            and estado.perdida_del_dia >= perdida_maxima_diaria):
        return Veredicto(
            False, detener=True,
            motivo=(f"Se alcanzó la pérdida máxima del día "
                    f"({estado.perdida_del_dia:,.2f} de {perdida_maxima_diaria:,.2f}). "
                    f"No se opera más hasta mañana."))

    # ------------------------------------------------- 3) la misma vela dos veces
    if estado.ultima_vela is not None and vela <= estado.ultima_vela:
        return Veredicto(
            False, motivo=f"ya se actuó sobre la vela {vela}; no se repite")

    if not d.opera:
        return Veredicto(False, motivo=d.motivo)

    # -------------------------------------------------------- 4) cerrar es fácil
    if d.accion == CERRAR:
        if posicion_lado == 0:
            return Veredicto(False, motivo="no hay nada que cerrar")
        return Veredicto(True, motivo="cerrar", cantidad=0.0)

    # --------------------------------------------------- 5) abrir sobre abierto
    if posicion_lado != 0:
        quiere = 1 if d.accion == ABRIR_LARGO else -1
        if quiere == posicion_lado:
            return Veredicto(False, motivo="ya hay una posición de ese lado")
        return Veredicto(
            False,
            motivo=("hay una posición del otro lado; primero se cierra y "
                    "recién en la vuelta siguiente se abre"))

    # ------------------------------------------------------------ 6) el stop
    if math.isnan(d.stop):
        return Veredicto(
            False,
            motivo="no se abre sin stop: sería una posición sin protección")

    # ------------------------------------------- 7) el tamaño que el exchange acepta
    decimales = int(contrato.get("quantityPrecision", 4))
    minimo = float(contrato.get("tradeMinQuantity") or 0.0)
    cant = _redondear_abajo(d.cantidad, decimales)

    if cant <= 0 or cant < minimo:
        return Veredicto(
            False,
            motivo=(f"la cantidad calculada ({d.cantidad:.8f}) no llega al "
                    f"mínimo de {minimo} que acepta el exchange. Con este "
                    f"capital y este stop, la operación no entra."))

    min_usdt = float(contrato.get("tradeMinUSDT") or 0.0)
    if min_usdt > 0 and cant * precio < min_usdt:
        return Veredicto(
            False,
            motivo=(f"el nocional ({cant * precio:,.2f}) queda por debajo del "
                    f"mínimo de {min_usdt} del exchange"))

    # --------------------------------------------------------- 8) el saldo
    #
    # Sin apalancamiento el nocional sale del bolsillo. Se pide 2% de margen
    # extra porque entre que se decide y se llena, el precio se mueve: una
    # orden rechazada por centavos es un error evitable.
    necesario = cant * precio * 1.02
    if disponible <= 0:
        return Veredicto(False, motivo="no se pudo leer el saldo o está en cero")
    if necesario > disponible:
        return Veredicto(
            False,
            motivo=(f"hace falta {necesario:,.2f} y hay {disponible:,.2f} "
                    f"disponible"))

    return Veredicto(True, motivo="todo en orden", cantidad=cant)


def anotar_resultado(estado: Estado, *, abrio: bool, cerro: bool,
                     ganancia: float = 0.0, vela: pd.Timestamp | None = None) -> None:
    """Actualiza lo que el bot sabe después de que una orden se ejecutó.

    `ganancia` sólo cuenta cuando se cerró: la pérdida del día se mide sobre lo
    REALIZADO. Contar lo no realizado haría que el bot se frene por una
    posición que todavía puede darse vuelta, que es justo cuando el stop existe
    para decidir eso.
    """
    if vela is not None:
        estado.ultima_vela = vela
    if abrio:
        estado.posicion_propia = True
    if cerro:
        estado.posicion_propia = False
        if ganancia < 0:
            estado.perdida_del_dia += abs(ganancia)
