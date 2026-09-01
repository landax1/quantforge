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
        return {"decimales_cantidad": 4, "minimo": 0.0001,
                "minimo_nocional": 2.0}

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


def _bot(ex=None, modo=SIMULACRO, posicion_propia=False, porcion=1.0):
    """Un bot listo para correr.

    `posicion_propia` importa mas de lo que parece: sin eso, un exchange con
    una posicion abierta dispara la guarda de posicion huerfana y el bot se
    detiene SOLO en la primera vuelta. Las pruebas del panico pasaban por eso
    y no porque el panico funcionara — verificado rompiendolo a proposito.
    """
    b = Bot(doc=_doc(), adaptador=ex or _Exchange(), modo=modo,
            porcion=porcion)
    if posicion_propia:
        b.estado.posicion_propia = True
    return b


def _montar(p, bot):
    """Mete un bot en el piloto SIN arrancar el hilo: hay pruebas que
    sólo quieren leer el estado y no necesitan que nada opere."""
    from botiquant.vivo.piloto import Vuelo
    p.vuelos[bot.simbolo] = Vuelo(bot=bot)


def _uno(p):
    """El estado del único vuelo. El piloto ahora sostiene varios, así que lo
    de cada bot vive en `vuelos` y arriba queda sólo lo del conjunto."""
    vuelos = p.estado()["vuelos"]
    assert vuelos, "no hay ningún vuelo"
    return vuelos[0]


@pytest.fixture
def piloto():
    p = Piloto()
    yield p
    p.apagar(espera=3.0)


# ------------------------------------------------------------ encender

def test_apagado_de_entrada(piloto):
    """Nada arranca solo. Encender el bot es siempre una decisión de alguien."""
    assert piloto.encendido is False
    e = piloto.estado()
    assert e["encendido"] is False and e["hay_bot"] is False
    assert e["vuelos"] == [] and e["porcion_libre"] == 1.0


def test_encender_lo_pone_a_correr(piloto):
    piloto.encender(_bot())
    assert piloto.encendido is True
    v = _uno(piloto)
    assert v["nombre"] == "S-042" and v["simbolo"] == "BTC-USDT"


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
        if _uno(piloto)["registro"]:
            break
        time.sleep(0.05)
    assert ex.vueltas >= 1
    assert _uno(piloto)["registro"], "la vuelta tendría que quedar anotada"


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
        visto["parado"] = piloto.vuelos["BTC-USDT"].parar.is_set()
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
    assert any(f.get("accion") == "panico" for f in _uno(piloto)["registro"])


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
    assert "se cayó" in _uno(piloto)["error"]


def test_una_guarda_que_detiene_saca_al_bot_del_bucle(piloto):
    """Hace falta una persona: seguir dando vueltas sólo llena el registro."""
    ex = _Exchange(posicion_lado=1)          # posición que el bot no abrió
    piloto.encender(_bot(ex, modo=PRACTICA))
    for _ in range(50):
        if not piloto.encendido:
            break
        time.sleep(0.05)
    assert piloto.encendido is False
    assert _uno(piloto)["detenido"] is True


# ------------------------------------------------------------- el estado

def test_el_estado_nunca_trae_una_credencial(piloto):
    """Va a la pantalla en cada refresco. Si filtra, filtra a la vista."""
    from botiquant.vivo.adaptador import BingX
    bot = Bot(doc=_doc(), adaptador=BingX("CLAVE_PUBLICA", "SECRETO_DEL_BOT"),
              modo=SIMULACRO)
    _montar(piloto, bot)
    texto = str(piloto.estado())
    assert "SECRETO_DEL_BOT" not in texto
    assert "CLAVE_PUBLICA" not in texto


def test_el_registro_viene_de_lo_mas_nuevo_a_lo_mas_viejo(piloto):
    """Es como se lee un registro cuando uno quiere saber qué acaba de pasar."""
    bot = _bot()
    bot.registro = [{"cuando": f"t{i}"} for i in range(5)]
    _montar(piloto, bot)
    assert [f["cuando"] for f in _uno(piloto)["registro"]] == \
        ["t4", "t3", "t2", "t1", "t0"]


# ------------------------------------------- lo que el bot NO sabe reproducir

def test_se_niega_a_operar_una_estrategia_con_trailing():
    """El motor mueve el stop cada vela; el bot deja UNA orden en el exchange.

    Operar igual seria operar algo distinto de lo que se midio, y sin ningun
    error a la vista: la estrategia entra, sale y cierra — solo que por
    niveles que no son los del backtest. Encontrado comparando una estrategia
    minada de verdad contra su backtest.
    """
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    doc = {"formato": "botiquant-bot", "version": 1, "nombre": "t",
           "ejecucion": {"simbolo": "BTC-USDT", "timeframe": "1h"},
           "estrategia": {"name": "t", "direction": "both",
                          "entry_long": [{"left": ema(5), "op": "cross_above",
                                          "right": ema(20)}],
                          "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                                   "stop_type": "atr", "stop_value": 2.0,
                                   "target_type": "atr", "target_value": 4.0,
                                   "atr_period": 14, "trail_atr": 1.5}}}
    with pytest.raises(ValueError, match="trailing"):
        Bot(doc=doc, adaptador=_Exchange(), modo=SIMULACRO)

    doc["estrategia"]["risk"]["trail_atr"] = 0
    Bot(doc=doc, adaptador=_Exchange(), modo=SIMULACRO)   # sin trailing, arranca


def test_un_rechazo_del_exchange_se_lee_como_un_mensaje_y_no_como_un_traceback(piloto):
    """Es el fallo MAS PROBABLE de todos y salia como tripas de Python.

    La clave mal, vencida, o creada sin permiso de trading: las tres terminan
    en un rechazo del exchange. Quien lo lea tiene que poder arreglarlo, y
    para eso necesita el mensaje del exchange —que ademas trae el codigo con
    el que se busca— y no el archivo y la linea donde reventó.

    Encontrado mandando una orden de verdad a BingX con una clave inventada.
    """
    from botiquant.data.bingx import BingXError

    ex = _Exchange()
    ex.velas = lambda *a, **k: (_ for _ in ()).throw(
        BingXError("BingX rechazó el pedido (100413): Incorrect apiKey",
                   codigo=100413, mensaje="Incorrect apiKey"))
    piloto.encender(_bot(ex, modo=PRACTICA))
    for _ in range(50):
        if not piloto.encendido:
            break
        time.sleep(0.05)

    assert piloto.estado()["encendido"] is False
    v = _uno(piloto)
    assert v["error"] == "[100413] Incorrect apiKey"
    assert "Traceback" not in v["error"]
    assert v["registro"][0]["accion"] == "apagado por el exchange"


def test_un_error_que_no_previmos_si_guarda_el_traceback(piloto):
    """La contracara: si llegó hasta ahí es algo que no anticipamos, y
    recortarlo tira justo lo que hace falta para entenderlo."""
    ex = _Exchange()
    ex.velas = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("algo raro"))
    piloto.encender(_bot(ex, modo=PRACTICA))
    for _ in range(50):
        if not piloto.encendido:
            break
        time.sleep(0.05)
    assert "Traceback" in _uno(piloto)["error"]
    assert "algo raro" in _uno(piloto)["error"]


# ================================ cada bot sobre SU porcion de la cuenta

def test_el_bot_dimensiona_sobre_SU_PORCION(monkeypatch):
    """SIN ESTO, CINCO BOTS ARRIESGAN CINCO VECES LO PEDIDO.

    `adaptador.capital()` devuelve el saldo de la CUENTA y el riesgo por
    operación se calcula sobre lo que devuelva. Con un bot da igual; con cinco,
    cada uno se cree dueño del 100%. Es el mismo error que el exportador de
    portafolio ya evitaba para los EA de MetaTrader y que acá faltaba.
    """
    from botiquant.vivo.runner import Bot

    vistos = []

    class _Nucleo:
        @staticmethod
        def espiar(df, spec, *, posicion, capital, precio):
            vistos.append(capital)
            from botiquant.vivo.nucleo import Decision
            return Decision(motivo="sin señal")

    bot = _bot(porcion=0.25)
    monkeypatch.setattr("botiquant.vivo.runner.decidir", _Nucleo.espiar)
    bot.paso()
    assert vistos and vistos[0] == pytest.approx(1000.0 * 0.25), (
        f"dimensionó sobre {vistos} en vez de sobre su cuarta parte")


def test_una_porcion_imposible_se_RECHAZA(monkeypatch):
    """Un cero apagaría el bot sin decirlo: dimensionaría sobre cero, no
    abriría nunca, y parecería que la estrategia no da señales."""
    for mala in (0.0, -0.5, 1.5):
        with pytest.raises(ValueError, match="porción"):
            _bot(porcion=mala)


def test_sin_porcion_es_la_cuenta_entera(monkeypatch):
    """Compatibilidad: un bot de antes no puede achicarse por actualizar."""
    from botiquant.vivo.runner import Bot
    assert Bot.__dataclass_fields__["porcion"].default == 1.0


# ================================ varios bots, pero uno por simbolo

def _bot_de(simbolo, ex=None, porcion=1.0, modo=SIMULACRO,
            posicion_propia=False):
    """Un bot sobre otro símbolo. Es lo único que cambia entre vuelos.

    `posicion_propia` importa igual que en `_bot`: sin eso, un exchange con una
    posición abierta dispara la guarda de posición huérfana y el bot se detiene
    SOLO en la primera vuelta.
    """
    doc = _doc()
    doc["ejecucion"] = dict(doc["ejecucion"], simbolo=simbolo)
    b = Bot(doc=doc, adaptador=ex or _Exchange(), modo=modo, porcion=porcion)
    if posicion_propia:
        b.estado.posicion_propia = True
    return b


def test_dos_bots_en_SIMBOLOS_DISTINTOS_conviven(piloto):
    """EL CHOQUE ES POR SIMBOLO Y NO POR CUENTA.

    En una cuenta de futuros hay una posición neta por símbolo, así que dos
    bots en símbolos distintos no se pelean por nada: sólo comparten margen, y
    de eso se ocupa la porción.

    Es lo que hace posible un portafolio, que era la razón entera de operar por
    API en vez de por una alerta de TradingView.
    """
    piloto.encender(_bot_de("BTC-USDT", porcion=0.5))
    piloto.encender(_bot_de("ETH-USDT", porcion=0.5))

    e = piloto.estado()
    assert e["cuantos"] == 2
    assert {v["simbolo"] for v in e["vuelos"]} == {"BTC-USDT", "ETH-USDT"}


def test_dos_bots_en_el_MISMO_simbolo_se_rechazan(piloto):
    """Ahí sí chocan de raíz: el cierre de uno es la apertura del otro.

    Uno abre, el otro ve una posición que él no abrió, se detiene, y el primero
    sigue creyendo que está solo.
    """
    piloto.encender(_bot_de("BTC-USDT", porcion=0.5))
    with pytest.raises(RuntimeError, match="mismo símbolo"):
        piloto.encender(_bot_de("BTC-USDT", porcion=0.5))
    assert piloto.cuantos == 1


def test_las_porciones_NO_PUEDEN_SUMAR_MAS_QUE_LA_CUENTA(piloto):
    """Es el único lugar que las ve a todas: cada bot solo no puede saberlo.

    Sin este control, tres bots al 50% arriesgan el 150% de la cuenta y nada lo
    dice hasta que el exchange rechaza una orden por margen — o peor, la acepta.
    """
    piloto.encender(_bot_de("BTC-USDT", porcion=0.6))
    with pytest.raises(RuntimeError, match="no entran en la cuenta"):
        piloto.encender(_bot_de("ETH-USDT", porcion=0.5))
    assert piloto.cuantos == 1
    assert piloto.porcion_usada == 0.6


def test_el_estado_dice_cuanto_queda_libre(piloto):
    """Para que la pantalla pueda ofrecer un número que entre, en vez de dejar
    que alguien pida uno que va a ser rechazado."""
    piloto.encender(_bot_de("BTC-USDT", porcion=0.25))
    e = piloto.estado()
    assert e["porcion_usada"] == 0.25 and e["porcion_libre"] == 0.75


def test_apagar_SIN_simbolo_los_apaga_a_TODOS(piloto):
    """Es el botón de "me voy", y que exista uno solo para todo evita el caso
    peor: apagar cuatro de cinco creyendo que se apagaron los cinco."""
    piloto.encender(_bot_de("BTC-USDT", porcion=0.3))
    piloto.encender(_bot_de("ETH-USDT", porcion=0.3))
    piloto.apagar()
    assert piloto.encendido is False and piloto.cuantos == 0


def test_apagar_UNO_deja_al_otro_volando(piloto):
    piloto.encender(_bot_de("BTC-USDT", porcion=0.3))
    piloto.encender(_bot_de("ETH-USDT", porcion=0.3))
    piloto.apagar("BTC-USDT")
    vivos = [v["simbolo"] for v in piloto.estado()["vuelos"] if v["encendido"]]
    assert vivos == ["ETH-USDT"]


def test_el_panico_FRENA_A_TODOS_antes_de_cerrar_a_ninguno(piloto):
    """Cerrar el primero mientras el quinto sigue vivo le da a ese quinto una
    vuelta entera para abrir algo nuevo mientras uno cree que está vaciando la
    cuenta."""
    frenados = []
    # con posición abierta: sin eso el pánico no tiene nada que cerrar y el
    # test pasaría por no llamar a `cerrar` nunca
    ex1, ex2 = _Exchange(posicion_lado=1), _Exchange(posicion_lado=1)

    def _espiar(ex):
        original = ex.cerrar

        def _cerrar(simbolo, posicion):
            # cuando se cierra el primero, TODOS tienen que estar frenados
            frenados.append(all(v.bot.detenido for v in piloto.vuelos.values()))
            return original(simbolo, posicion)
        ex.cerrar = _cerrar

    _espiar(ex1); _espiar(ex2)
    piloto.encender(_bot_de("BTC-USDT", ex1, porcion=0.3, modo=PRACTICA,
                            posicion_propia=True))
    piloto.encender(_bot_de("ETH-USDT", ex2, porcion=0.3, modo=PRACTICA,
                            posicion_propia=True))
    time.sleep(0.2)
    piloto.panico()
    assert frenados and all(frenados), (
        "cerró uno mientras otro seguía sin frenar")


def test_un_vuelo_que_termino_sin_error_no_ensucia_la_lista(piloto):
    """Pero el que murió POR UN ERROR se queda: ese estado es justamente lo que
    alguien va a querer leer cuando pregunte por qué se apagó."""
    piloto.encender(_bot_de("BTC-USDT", porcion=0.3))
    piloto.apagar()
    piloto.encender(_bot_de("ETH-USDT", porcion=0.3))
    assert [v["simbolo"] for v in piloto.estado()["vuelos"]] == ["ETH-USDT"]


def test_se_niega_a_encender_con_un_indicador_QUE_NO_CONOCE():
    """SIN ESTO EL BOT NO SE NIEGA: ARRANCA Y SE MUERE EN LA PRIMERA VUELTA.

    PASO DE VERDAD: una estrategia minada con un indicador nuevo se encendió
    contra un proceso que todavía no lo conocía. El error llegó como un
    traceback en el registro —"Unknown indicator: Mecha"— con el bot ya
    apagado y la pantalla diciendo que estaba encendido.

    Es el caso de actualizar la aplicación: una estrategia guardada puede
    nombrar un bloque que se renombró o se quitó. Que falle al ENCENDER, con el
    nombre adentro del mensaje, es la diferencia entre arreglarlo y adivinarlo.
    """
    doc = _doc()
    doc["estrategia"]["entry_long"] = [{
        "left": {"type": "indicator", "name": "NoExisteJamas", "params": {}},
        "op": ">", "right": {"type": "const", "value": 1}}]
    with pytest.raises(ValueError, match="no conoce"):
        Bot(doc=doc, adaptador=_Exchange(), modo=SIMULACRO)


def test_los_indicadores_que_SI_existen_no_molestan():
    """El control no puede rechazar una estrategia legítima."""
    Bot(doc=_doc(), adaptador=_Exchange(), modo=SIMULACRO)
