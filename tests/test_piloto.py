"""Encender, apagar, y el botón de pánico.

Lo que se defiende acá es lo que pasa en los bordes: apagar mientras opera,
encender dos veces, un error adentro del bucle. Son los momentos donde un bot
mal hecho manda cien órdenes en un minuto o se queda sordo al botón de apagar.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from botiquant.vivo.adaptador import Posicion
from botiquant.vivo.piloto import Piloto
from botiquant.vivo.runner import PRACTICA, SIMULACRO, Bot


class _Exchange:
    es_real = False

    def __init__(self, posicion_lado=0):
        self._pos = posicion_lado
        self.ordenes: list[tuple] = []
        self.vueltas = 0

    def velas(self, simbolo, intervalo, limite=500):
        self.vueltas += 1
        n = 300
        t = pd.date_range("2026-08-01", periods=n, freq="1h", tz="UTC")
        x = np.arange(n)
        c = 78_000 + np.sin(x / 9) * 900 + x * 2.0
        return pd.DataFrame({"open": c, "high": c + 60, "low": c - 60,
                             "close": c, "volume": np.full(n, 10.0)}, index=t)

    def capital(self):
        return 10_000.0

    def posicion(self, simbolo):
        return Posicion(self._pos, 0.01 if self._pos else 0.0, 78_000.0)

    def contrato(self, simbolo):
        return {"quantityPrecision": 4, "tradeMinQuantity": 0.0001,
                "tradeMinUSDT": 2.0}

    def abrir(self, simbolo, lado, cantidad, stop, objetivo):
        self.ordenes.append(("abrir", lado, cantidad))
        self._pos = lado
        return {"ok": True}

    def cerrar(self, simbolo, posicion):
        self.ordenes.append(("cerrar", posicion.lado, posicion.cantidad))
        self._pos = 0
        return {"ok": True}


def _doc(timeframe="1h"):
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return {
        "formato": "botiquant-bot", "version": 1, "nombre": "S-042",
        "ejecucion": {"simbolo": "BTC-USDT", "timeframe": timeframe},
        "estrategia": {
            "name": "S-042", "direction": "both",
            "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
            "entry_short": [{"left": ema(5), "op": "cross_below", "right": ema(20)}],
            "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                     "stop_type": "atr", "stop_value": 2.0,
                     "target_type": "atr", "target_value": 4.0, "atr_period": 14}},
    }


def _bot(ex=None, modo=SIMULACRO, posicion_propia=False):
    """Un bot listo para correr.

    `posicion_propia` importa mas de lo que parece: sin eso, un exchange con
    una posicion abierta dispara la guarda de posicion huerfana y el bot se
    detiene SOLO en la primera vuelta. Las pruebas del panico pasaban por eso
    y no porque el panico funcionara — verificado rompiendolo a proposito.
    """
    b = Bot(doc=_doc(), adaptador=ex or _Exchange(), modo=modo)
    if posicion_propia:
        b.estado.posicion_propia = True
    return b


@pytest.fixture
def piloto():
    p = Piloto()
    yield p
    p.apagar(espera=3.0)


# ------------------------------------------------------------ encender

def test_apagado_de_entrada(piloto):
    """Nada arranca solo. Encender el bot es siempre una decisión de alguien."""
    assert piloto.encendido is False
    assert piloto.estado() == {"encendido": False, "hay_bot": False}


def test_encender_lo_pone_a_correr(piloto):
    piloto.encender(_bot())
    assert piloto.encendido is True
    e = piloto.estado()
    assert e["nombre"] == "S-042" and e["simbolo"] == "BTC-USDT"


def test_no_se_pueden_encender_dos(piloto):
    """Dos bots sobre la misma cuenta se pelean por la misma posición.

    Uno abre, el otro ve una posición que él no abrió, se detiene, y el primero
    sigue creyendo que está solo.
    """
    piloto.encender(_bot())
    with pytest.raises(RuntimeError, match="Ya hay un bot"):
        piloto.encender(_bot())


def test_da_al_menos_una_vuelta_apenas_arranca(piloto):
    """No espera al primer cierre de vela para hacer algo.

    Arrancar y no mirar el mercado hasta dentro de una hora se ve igual que
    estar roto, y nadie lo deja prendido lo suficiente para descubrir que
    andaba.
    """
    ex = _Exchange()
    piloto.encender(_bot(ex))
    # Se espera al REGISTRO y no al contador de velas: el contador sube al
    # empezar la vuelta y la anotación pasa al terminarla, así que mirar el
    # contador corta en el medio y la prueba falla por carrera, no por bug.
    for _ in range(60):
        if piloto.estado()["registro"]:
            break
        time.sleep(0.05)
    assert ex.vueltas >= 1
    assert piloto.estado()["registro"], "la vuelta tendría que quedar anotada"


# --------------------------------------------------------------- apagar

def test_apagar_es_inmediato_y_no_espera_a_la_vela(piloto):
    """El bucle espera sobre un evento y no sobre un `sleep`.

    Con `sleep(3600)`, el botón de apagar tardaría hasta una hora en hacer
    efecto — justo en el momento en que a alguien le urge.
    """
    piloto.encender(_bot())
    time.sleep(0.2)
    arranque = time.time()
    piloto.apagar(espera=5.0)
    assert time.time() - arranque < 3.0, "tardó demasiado en apagarse"
    assert piloto.encendido is False


def test_apagar_NO_cierra_la_posicion(piloto):
    """Apagar y cerrar son dos decisiones distintas.

    Quien apaga porque se va a dormir quiere que el stop del exchange siga
    cuidando la posición, no que se cierre a mercado en el peor momento.
    """
    ex = _Exchange(posicion_lado=1)
    piloto.encender(_bot(ex))
    time.sleep(0.2)
    piloto.apagar()
    assert not any(o[0] == "cerrar" for o in ex.ordenes)


def test_apagar_lo_que_no_esta_encendido_no_revienta(piloto):
    assert piloto.apagar()["encendido"] is False


def test_despues_de_apagar_se_puede_encender_de_nuevo(piloto):
    piloto.encender(_bot())
    piloto.apagar()
    piloto.encender(_bot())
    assert piloto.encendido is True


# --------------------------------------------------------------- pánico

def test_panico_apaga_y_cierra(piloto):
    ex = _Exchange(posicion_lado=1)
    piloto.encender(_bot(ex, modo=PRACTICA, posicion_propia=True))
    time.sleep(0.2)
    assert piloto.encendido, "el bot tiene que estar VIVO o el panico no prueba nada"
    e = piloto.panico()
    assert piloto.encendido is False
    assert any(o[0] == "cerrar" for o in ex.ordenes)
    assert e["cerrado"]


def test_panico_apaga_ANTES_de_cerrar(piloto):
    """Al reves, el bucle puede despertarse entre las dos cosas, ver la
    posicion cerrada y abrir otra — lo contrario de lo que se pidio.

    Se comprueba DETERMINISTICAMENTE: el exchange falso anota si el bucle ya
    estaba parado en el instante exacto en que le pidieron cerrar. La version
    anterior de esta prueba miraba si aparecia una orden en los 300ms
    siguientes, y pasaba en verde con el orden invertido porque el bucle
    espera un segundo como minimo. Verificado rompiendo el codigo.
    """
    ex = _Exchange(posicion_lado=1)
    visto = {}
    original = ex.cerrar

    def _cerrar(simbolo, posicion):
        visto["parado"] = piloto._parar.is_set()
        return original(simbolo, posicion)

    ex.cerrar = _cerrar
    piloto.encender(_bot(ex, modo=PRACTICA, posicion_propia=True))
    time.sleep(0.2)
    piloto.panico()
    assert visto.get("parado") is True, (
        "cerro la posicion sin haber parado el bucle primero")


def test_panico_sin_posicion_no_manda_ninguna_orden(piloto):
    ex = _Exchange(posicion_lado=0)
    piloto.encender(_bot(ex, modo=PRACTICA))
    time.sleep(0.2)
    e = piloto.panico()
    assert not any(o[0] == "cerrar" for o in ex.ordenes)
    assert "no había posición" in str(e["cerrado"])


def test_panico_queda_anotado_en_el_registro(piloto):
    ex = _Exchange(posicion_lado=1)
    piloto.encender(_bot(ex, modo=PRACTICA, posicion_propia=True))
    time.sleep(0.2)
    piloto.panico()
    assert any(f.get("accion") == "panico" for f in piloto.estado()["registro"])


def test_si_el_cierre_falla_el_panico_igual_apaga(piloto):
    """Lo primero que tiene que garantizar el pánico es que deje de operar.

    Si el cierre falla y encima el bot sigue encendido, el botón no sirvió
    para nada en el momento en que más importaba.
    """
    ex = _Exchange(posicion_lado=1)
    ex.cerrar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin red"))
    piloto.encender(_bot(ex, modo=PRACTICA, posicion_propia=True))
    time.sleep(0.2)
    e = piloto.panico()
    assert piloto.encendido is False
    assert "no se pudo cerrar" in str(e["cerrado"])


# ------------------------------------------------------- cuando algo falla

def test_un_error_inesperado_apaga_el_bot(piloto):
    """No reintenta en bucle.

    Reintentar a ciegas contra un exchange que rechaza algo es la forma de
    mandar cien órdenes malas en un minuto.
    """
    ex = _Exchange()
    ex.velas = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("se cayó"))
    piloto.encender(_bot(ex))
    for _ in range(50):
        if not piloto.encendido:
            break
        time.sleep(0.05)
    assert piloto.encendido is False
    assert "se cayó" in piloto.estado()["error"]


def test_una_guarda_que_detiene_saca_al_bot_del_bucle(piloto):
    """Hace falta una persona: seguir dando vueltas sólo llena el registro."""
    ex = _Exchange(posicion_lado=1)          # posición que el bot no abrió
    piloto.encender(_bot(ex, modo=PRACTICA))
    for _ in range(50):
        if not piloto.encendido:
            break
        time.sleep(0.05)
    assert piloto.encendido is False
    assert piloto.estado()["detenido"] is True


# ------------------------------------------------------------- el estado

def test_el_estado_nunca_trae_una_credencial(piloto):
    """Va a la pantalla en cada refresco. Si filtra, filtra a la vista."""
    from botiquant.vivo.adaptador import BingX
    bot = Bot(doc=_doc(), adaptador=BingX("CLAVE_PUBLICA", "SECRETO_DEL_BOT"),
              modo=SIMULACRO)
    piloto.bot = bot
    texto = str(piloto.estado())
    assert "SECRETO_DEL_BOT" not in texto
    assert "CLAVE_PUBLICA" not in texto


def test_el_registro_viene_de_lo_mas_nuevo_a_lo_mas_viejo(piloto):
    """Es como se lee un registro cuando uno quiere saber qué acaba de pasar."""
    bot = _bot()
    bot.registro = [{"cuando": f"t{i}"} for i in range(5)]
    piloto.bot = bot
    assert [f["cuando"] for f in piloto.estado()["registro"]] == \
        ["t4", "t3", "t2", "t1", "t0"]
