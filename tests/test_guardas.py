"""Lo último que se pregunta antes de mandar una orden con plata.

Es el código de más riesgo del proyecto: acá abajo un `False` que tenía que ser
`True` cuesta una operación perdida, y un `True` que tenía que ser `False`
cuesta plata. Por eso cada guarda tiene su prueba y cada prueba dice qué pasa
en el mundo si falla.

Todo corre sin red y sin exchange: las guardas no hablan con nadie, se les pasa
lo que el exchange dijo y contestan.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from botiquant.vivo.guardas import Estado, anotar_resultado, revisar
from botiquant.vivo.nucleo import ABRIR_CORTO, ABRIR_LARGO, CERRAR, NADA, Decision

VELA = pd.Timestamp("2026-08-26 20:00", tz="UTC")
CONTRATO = {"decimales_cantidad": 4, "minimo": 0.0001,
            "minimo_nocional": 2.0}
PRECIO = 78_000.0


def _abrir(cantidad: float = 0.01, stop: float = 76_000.0) -> Decision:
    return Decision(ABRIR_LARGO, "señal de entrada", cantidad=cantidad,
                    stop=stop, objetivo=82_000.0, precio=PRECIO)


def _revisar(d: Decision, **kw):
    base = dict(estado=Estado(), posicion_lado=0, vela=VELA, contrato=CONTRATO,
                disponible=10_000.0, precio=PRECIO)
    base.update(kw)
    return revisar(d, **base)


# ------------------------------------------------------ la posición huérfana

def test_una_posicion_que_el_bot_no_abrio_lo_detiene():
    """La guarda más importante de todas.

    Si el exchange dice que hay algo abierto y este bot no lo abrió —otra
    sesión, otra estrategia, alguien operando a mano desde el teléfono— el bot
    no sabe a qué precio se abrió ni con qué stop. Seguir operando encima de
    eso es operar sobre una realidad que no entiende.
    """
    v = _revisar(_abrir(), posicion_lado=1, estado=Estado(posicion_propia=False))
    assert not v.permitido
    assert v.detener, "no alcanza con esperar: la vela que viene ve lo mismo"
    assert "no abrió" in v.motivo


def test_la_posicion_propia_no_detiene_nada():
    e = Estado(posicion_propia=True)
    v = _revisar(Decision(CERRAR, "salida", precio=PRECIO),
                 posicion_lado=1, estado=e)
    assert v.permitido


def test_nunca_adopta_la_posicion_huerfana():
    """Adoptarla sería lo cómodo y es lo que no hay que hacer.

    Un stop calculado sobre una entrada que no ocurrió es peor que no tener
    stop, porque parece que hay protección.
    """
    e = Estado(posicion_propia=False)
    _revisar(_abrir(), posicion_lado=-1, estado=e)
    assert not e.posicion_propia, "la guarda no puede adoptarla por su cuenta"


# ------------------------------------------------------------ los duplicados

def test_no_actua_dos_veces_sobre_la_misma_vela():
    """La defensa contra órdenes duplicadas.

    El bucle se puede despertar dos veces en la misma vela: porque el usuario
    apretó dos veces, porque el pedido anterior tardó, porque el reloj se
    corrió. La segunda no puede operar.
    """
    e = Estado(ultima_vela=VELA)
    v = _revisar(_abrir(), estado=e)
    assert not v.permitido
    assert "ya se actuó" in v.motivo


def test_una_vela_anterior_tampoco_pasa():
    """Llega tarde, no adelantada: operar sobre una vela vieja es operar sobre
    información que ya caducó."""
    e = Estado(ultima_vela=VELA)
    v = _revisar(_abrir(), estado=e, vela=VELA - pd.Timedelta("1h"))
    assert not v.permitido


def test_la_vela_siguiente_si_pasa():
    e = Estado(ultima_vela=VELA)
    v = _revisar(_abrir(), estado=e, vela=VELA + pd.Timedelta("1h"))
    assert v.permitido


# ---------------------------------------------------------- el tope diario

def test_el_tope_de_perdida_diaria_detiene_el_bot():
    e = Estado(dia=str(VELA.date()), perdida_del_dia=300.0)
    v = _revisar(_abrir(), estado=e, perdida_maxima_diaria=250.0)
    assert not v.permitido and v.detener
    assert "pérdida máxima" in v.motivo


def test_el_tope_se_reinicia_al_cambiar_el_dia():
    e = Estado(dia="2026-08-25", perdida_del_dia=999.0)
    v = _revisar(_abrir(), estado=e, perdida_maxima_diaria=250.0)
    assert v.permitido
    assert e.perdida_del_dia == 0.0


def test_solo_cuenta_la_perdida_REALIZADA():
    """Contar lo no realizado frenaría al bot por una posición que todavía
    puede darse vuelta — que es exactamente para lo que existe el stop."""
    e = Estado()
    anotar_resultado(e, abrio=True, cerro=False, ganancia=-500.0)
    assert e.perdida_del_dia == 0.0
    anotar_resultado(e, abrio=False, cerro=True, ganancia=-120.0)
    assert e.perdida_del_dia == 120.0


def test_una_ganancia_no_baja_el_contador_de_perdida():
    """El tope es de pérdida acumulada del día, no de resultado neto.

    Con el neto, una racha de +500 y −800 no llegaría al tope de 250 y el bot
    seguiría operando después de perder 800 seguidos.
    """
    e = Estado()
    anotar_resultado(e, abrio=False, cerro=True, ganancia=-200.0)
    anotar_resultado(e, abrio=False, cerro=True, ganancia=+500.0)
    assert e.perdida_del_dia == 200.0


# ------------------------------------------------------------- el tamaño

def test_la_cantidad_se_redondea_HACIA_ABAJO():
    """Hacia arriba se opera MÁS de lo dimensionado.

    El tamaño sale de un porcentaje de riesgo que alguien eligió; redondear
    para arriba lo cambia sin avisar.
    """
    v = _revisar(_abrir(cantidad=0.0123456789))
    assert v.cantidad == 0.0123


def test_por_debajo_del_minimo_no_se_opera():
    v = _revisar(_abrir(cantidad=0.00005))
    assert not v.permitido
    assert "mínimo" in v.motivo


def test_por_debajo_del_nocional_minimo_tampoco():
    """BTC-USDT pide 2 USDT: 0,0001 a 78.000 pasa, pero con un precio bajo no."""
    v = _revisar(_abrir(cantidad=0.0001), precio=10.0)
    assert not v.permitido
    assert "nocional" in v.motivo


# --------------------------------------------------------------- el saldo

def test_sin_saldo_suficiente_no_se_manda_la_orden():
    v = _revisar(_abrir(cantidad=1.0), disponible=1_000.0)
    assert not v.permitido
    assert "hace falta" in v.motivo


def test_pide_un_poco_de_margen_sobre_el_nocional():
    """Entre que se decide y se llena, el precio se mueve.

    Una orden rechazada por centavos es un error evitable: se exige 2% de más.
    0,1 BTC a 78.000 son 7.800; con 7.850 disponibles alcanzaría justo, pero
    con el margen no.
    """
    assert not _revisar(_abrir(cantidad=0.1), disponible=7_850.0).permitido
    assert _revisar(_abrir(cantidad=0.1), disponible=8_200.0).permitido


def test_saldo_en_cero_se_trata_como_no_leido():
    v = _revisar(_abrir(), disponible=0.0)
    assert not v.permitido


# ---------------------------------------------------------------- el stop

def test_nunca_abre_sin_stop():
    """Una posición sin stop es la forma más rápida de perder una cuenta."""
    v = _revisar(_abrir(stop=float("nan")))
    assert not v.permitido
    assert "sin protección" in v.motivo


# ------------------------------------------------------- abrir sobre abierto

def test_no_agranda_una_posicion_que_ya_existe():
    e = Estado(posicion_propia=True)
    v = _revisar(_abrir(), posicion_lado=1, estado=e)
    assert not v.permitido
    assert "ya hay una posición" in v.motivo


def test_no_da_vuelta_la_posicion_en_una_sola_orden():
    """Dar vuelta de una haría el doble de nocional en una sola operación.

    El motor cierra y abre por separado, y el bot tiene que hacer lo mismo o
    la posición que abre no es la que se midió.
    """
    e = Estado(posicion_propia=True)
    v = _revisar(_abrir(), posicion_lado=-1, estado=e)
    assert not v.permitido
    assert "primero se cierra" in v.motivo


def test_cerrar_lo_que_no_existe_no_manda_nada():
    v = _revisar(Decision(CERRAR, "salida", precio=PRECIO), posicion_lado=0)
    assert not v.permitido


# ------------------------------------------------------- el caso que sí pasa

def test_una_orden_normal_pasa_todas_las_guardas():
    """El control: si esto se pone rojo, alguna guarda quedó demasiado dura y
    el bot no opera nunca, que es una forma silenciosa de estar roto."""
    v = _revisar(_abrir(cantidad=0.01))
    assert v.permitido, v.motivo
    assert v.cantidad == 0.01
    assert not v.detener


# ------------------------------------------ las guardas dentro del bucle
#
# Lo de arriba prueba las guardas solas. Esto prueba que el bucle LAS USE: una
# guarda perfecta que nadie llama no protege de nada, y es un error fácil de
# cometer y difícil de ver.

from botiquant.vivo.runner import Bot, PRACTICA, SIMULACRO         # noqa: E402


class _ExchangeFalso:
    """Un exchange de mentira que anota qué órdenes le pidieron."""

    es_real = False

    def __init__(self, posicion_lado=0, saldo=10_000.0):
        self._pos = posicion_lado
        self.saldo = saldo
        self.ordenes: list[tuple] = []

    def velas(self, simbolo, intervalo, limite=500):
        n = 300
        t = pd.date_range("2026-08-01", periods=n, freq="1h", tz="UTC")
        import numpy as np
        x = np.arange(n)
        c = 78_000 + np.sin(x / 9) * 900 + x * 2.0
        return pd.DataFrame({"open": c, "high": c + 60, "low": c - 60,
                             "close": c, "volume": np.full(n, 10.0)}, index=t)

    def capital(self):
        return self.saldo

    def posicion(self, simbolo):
        from botiquant.vivo.adaptador import Posicion
        return Posicion(self._pos, 0.01 if self._pos else 0.0, 78_000.0)

    def contrato(self, simbolo):
        return dict(CONTRATO)

    def abrir(self, simbolo, lado, cantidad, stop, objetivo):
        self.ordenes.append(("abrir", lado, cantidad))
        self._pos = lado
        return {"ok": True}

    def cerrar(self, simbolo, posicion):
        self.ordenes.append(("cerrar", posicion.lado, posicion.cantidad))
        self._pos = 0
        return {"ok": True}


def _doc():
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return {
        "formato": "botiquant-bot", "version": 1, "nombre": "t",
        "ejecucion": {"simbolo": "BTC-USDT", "timeframe": "1h"},
        "estrategia": {
            "name": "t", "direction": "both",
            "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
            "entry_short": [{"left": ema(5), "op": "cross_below", "right": ema(20)}],
            "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                     "stop_type": "atr", "stop_value": 2.0,
                     "target_type": "atr", "target_value": 4.0, "atr_period": 14}},
    }


def test_el_bucle_se_detiene_ante_una_posicion_que_no_abrio():
    """La guarda existe; esto comprueba que el bucle la respete.

    Si el bot operara igual, la guarda sería decorativa — y la primera vez que
    alguien cierre la aplicación con una posición abierta, al reabrirla el bot
    empezaría a operar encima sin saber qué hay.
    """
    ex = _ExchangeFalso(posicion_lado=1)
    bot = Bot(doc=_doc(), adaptador=ex, modo=PRACTICA)
    fila = bot.paso()
    assert bot.detenido
    assert not ex.ordenes, "no puede haber mandado ninguna orden"
    assert "no abrió" in fila["bloqueado"]


def test_una_vez_detenido_no_vuelve_solo():
    """Reanudarlo es una decisión de una persona, no del reloj."""
    ex = _ExchangeFalso(posicion_lado=1)
    bot = Bot(doc=_doc(), adaptador=ex, modo=PRACTICA)
    bot.paso()
    for _ in range(3):
        fila = bot.paso()
        assert "detenido" in fila["motivo"]
    assert not ex.ordenes


def test_en_simulacro_las_guardas_no_piden_cuenta_ni_contrato():
    """El simulacro tiene que correr sin ninguna clave.

    Si el modo simulacro consultara el saldo, dejaría de servir para lo único
    que sirve: mirar qué haría el bot antes de tener credenciales.
    """
    class _SinCuenta(_ExchangeFalso):
        def capital(self):
            raise AssertionError("el simulacro no puede consultar el saldo")
        def contrato(self, simbolo):
            raise AssertionError("el simulacro no puede consultar el contrato")

    bot = Bot(doc=_doc(), adaptador=_SinCuenta(), modo=SIMULACRO)
    fila = bot.paso()
    assert fila["simulado"] is True
