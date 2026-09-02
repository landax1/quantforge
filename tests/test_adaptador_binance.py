"""El adaptador de Binance: sólo demo, y nunca una posición sin stop.

Las dos propiedades que defiende este archivo son las que no se pueden
comprobar operando, porque para verlas fallar habría que provocar una falla en
el exchange:

  1. que no exista forma de apuntar a la cuenta real;
  2. que si la protección no queda puesta, la posición se cierre EN EL ACTO.

La segunda es la que importa cuando el bot corre sin que nadie mire.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.data import binance_trade as bt
from botiquant.vivo.adaptador import Binance, Posicion, a_simbolo

_CONTRATO = {"simbolo": "BTCUSDT", "minimo": 0.0001, "paso": 0.0001,
             "decimales_cantidad": 4, "decimales_precio": 2,
             "minimo_nocional": 50.0, "tick": 0.1, "tick_texto": "0.10"}


def _velas(precio=78000.0):
    idx = pd.date_range("2026-08-31", periods=3, freq="h", tz="UTC")
    return pd.DataFrame({"open": precio, "high": precio, "low": precio,
                         "close": precio, "volume": 1.0}, index=idx)


class _Falso:
    """Un adaptador con la red reemplazada, que anota lo que le pidieron."""

    def __init__(self, monkeypatch, *, proteger_falla=None, condicionales=()):
        self.a = Binance("K", "S")
        self.hechos: list[str] = []
        self.cerradas: list[float] = []

        monkeypatch.setattr(bt, "velas", lambda *a, **k: _velas())
        monkeypatch.setattr(bt, "contrato", lambda *a, **k: dict(_CONTRATO))
        monkeypatch.setattr(bt, "modo_posicion", lambda *a, **k: "una_via")
        # el margen se prepara antes de abrir; en la red falsa no hay nada que preparar
        monkeypatch.setattr(bt, "preparar_margen",
                            lambda *a, **k: {"margen": "aislado", "apalancamiento": 5})
        monkeypatch.setattr(bt, "detalle_orden",
                            lambda *a, **k: {"precio": 78752.6, "cantidad": 0.0007,
                                             "id": 1, "estado": "FILLED"})
        monkeypatch.setattr(bt, "cancelar_todo", lambda *a, **k: {})

        def _abrir(*a, **k):
            self.hechos.append("abrir")
            return {"orderId": 1}

        def _proteger(*a, **k):
            self.hechos.append("proteger")
            if proteger_falla:
                raise bt.BinanceError(proteger_falla, codigo=-4120)
            return [{}]

        def _condicionales(*a, **k):
            return [{"tipo": t, "disparo": 1.0, "id": 1, "estado": "NEW",
                     "cierra_todo": True, "crudo": {}} for t in condicionales]

        def _cerrar(simbolo, lado, cantidad, **k):
            self.hechos.append("cerrar")
            self.cerradas.append(cantidad)
            return {"orderId": 2}

        # La posición existe mientras no se haya cerrado.
        def _posicion(*a, **k):
            if "cerrar" in self.hechos or "abrir" not in self.hechos:
                return {"lado": 0, "cantidad": 0.0, "precio_entrada": float("nan")}
            return {"lado": 1, "cantidad": 0.0007, "precio_entrada": 78752.6}

        monkeypatch.setattr(bt, "abrir", _abrir)
        monkeypatch.setattr(bt, "proteger", _proteger)
        monkeypatch.setattr(bt, "condicionales_abiertas", _condicionales)
        monkeypatch.setattr(bt, "cerrar", _cerrar)
        monkeypatch.setattr(bt, "posicion", _posicion)


# ==================================== 1) no se puede tocar la cuenta real

def test_NO_EXISTE_forma_de_apuntar_a_la_cuenta_real():
    """MAS FUERTE QUE "EL DEFAULT ES SEGURO".

    Un valor por omisión lo da vuelta un bug, un JSON mal leído o un campo que
    llegó en None. Esto no tiene qué dar vuelta: el constructor no acepta una
    base, así que para operar en real hay que editar el archivo a propósito.
    """
    assert "base" not in Binance.__init__.__code__.co_varnames
    assert "real" not in Binance.__init__.__code__.co_varnames
    a = Binance("K", "S")
    assert a.base == bt.BASE_PRUEBA
    assert a.es_real is False


def test_es_real_no_es_un_calculo():
    """Es un atributo de clase, no algo que se derive de la URL: derivarlo
    abriría la puerta a que una URL distinta lo vuelva verdadero."""
    assert Binance.es_real is False


# ============================ 2) nunca una posición sin stop, ni un instante

def test_si_la_proteccion_FALLA_se_cierra_la_posicion_en_el_acto(monkeypatch):
    """LA PROPIEDAD QUE IMPORTA CUANDO NADIE ESTA MIRANDO.

    En Binance el stop es una SEGUNDA llamada —las condicionales viven en otro
    servicio— así que entre que la entrada se llena y el stop queda puesto hay
    una ventana. Si el segundo pedido falla, queda una posición abierta sin
    protección y nadie se entera hasta que el precio va en contra.

    Entre quedarse desprotegido y cerrar una operación que quizás era buena, se
    cierra: perder una entrada cuesta una comisión, quedarse sin stop cuesta lo
    que el mercado quiera.
    """
    f = _Falso(monkeypatch, proteger_falla="[-4120] Order type not supported")
    r = f.a.abrir("BTCUSDT", 1, 0.0007, stop=74000.0, objetivo=86000.0)

    assert f.hechos == ["abrir", "proteger", "cerrar"]
    assert r["cerrada_por_seguridad"] is True
    assert "-4120" in r["desprotegida"]
    # se cierra por lo que HAY, no por lo que se pidió
    assert f.cerradas == [0.0007]


def test_que_el_pedido_no_falle_NO_ALCANZA(monkeypatch):
    """UN PEDIDO ACEPTADO Y UN STOP ANOTADO SON DOS COSAS DISTINTAS.

    Medido el 31/8/2026 contra la API. Por eso después de proteger se pregunta
    si la condicional está REGISTRADA, en vez de confiar en que no hubo
    excepción. Sin esta comprobación, un stop que se acepta y no queda deja al
    bot operando convencido de que está cubierto.
    """
    # proteger no levanta nada, pero no hay ninguna condicional puesta
    f = _Falso(monkeypatch, condicionales=())
    r = f.a.abrir("BTCUSDT", 1, 0.0007, stop=74000.0, objetivo=86000.0)

    assert f.hechos == ["abrir", "proteger", "cerrar"]
    assert "no quedó registrado" in r["desprotegida"]


def test_con_el_stop_puesto_NO_se_cierra_nada(monkeypatch):
    """El control no puede cerrar operaciones buenas: si el stop quedó, la
    posición sigue abierta y el bot sigue su curso."""
    f = _Falso(monkeypatch, condicionales=("STOP_MARKET", "TAKE_PROFIT_MARKET"))
    r = f.a.abrir("BTCUSDT", 1, 0.0007, stop=74000.0, objetivo=86000.0)

    assert f.hechos == ["abrir", "proteger"]
    assert "desprotegida" not in r
    assert r["precio_ejecutado"] == 78752.6


def test_una_estrategia_SIN_stop_no_pasa_por_la_proteccion(monkeypatch):
    """Sin stop ni objetivo no hay nada que poner, y pedirlo igual haría que el
    exchange rechace una orden con disparador vacío.

    OJO: que este camino exista no significa que el bot pueda operar sin stop.
    Eso lo prohíben las guardas antes de llegar acá, y con otro motivo.
    """
    f = _Falso(monkeypatch)
    f.a.abrir("BTCUSDT", 1, 0.0007, stop=float("nan"), objetivo=float("nan"))
    assert f.hechos == ["abrir"]


# ================================================ el resto de la superficie

def test_el_precio_de_ejecucion_se_pregunta_aparte(monkeypatch):
    """La respuesta de la orden no lo trae ni con RESULT. Sin esto el registro
    del bot dice que operó pero no a cuánto."""
    f = _Falso(monkeypatch, condicionales=("STOP_MARKET",))
    r = f.a.abrir("BTCUSDT", 1, 0.0007, stop=74000.0, objetivo=float("nan"))
    assert r["precio_ejecutado"] == 78752.6


def test_las_velas_se_piden_a_PRODUCCION(monkeypatch):
    """A propósito, aunque se opere contra el entorno de prueba.

    El volumen de un entorno de prueba sale de operaciones falsas, y la
    biblioteca tiene dos indicadores que lo usan: el bot decidiría distinto en
    pruebas que en real, y eso no aparece como error sino como un bot que "en
    demo andaba".
    """
    vistas: dict = {}

    def _espiar(simbolo, intervalo, limite, base=None):
        vistas["base"] = base
        return _velas()

    monkeypatch.setattr(bt, "velas", _espiar)
    df = Binance("K", "S").velas("BTCUSDT", "1h", 5)

    assert vistas["base"] == bt.BASE_REAL, "se pidieron al entorno de prueba"
    assert df.index.is_monotonic_increasing


def test_cerrar_limpia_DESPUES_de_cerrar_y_no_antes(monkeypatch):
    """Cancelar las órdenes con la posición abierta la deja DESPROTEGIDA.

    Y la limpieza hace falta porque, medido, el stop y el objetivo SOBREVIVEN
    al cierre de la posición: quedan colgados esperando algo que ya no existe.
    """
    orden: list[str] = []
    monkeypatch.setattr(bt, "contrato", lambda *a, **k: dict(_CONTRATO))
    monkeypatch.setattr(bt, "modo_posicion", lambda *a, **k: "una_via")
    monkeypatch.setattr(bt, "cerrar",
                        lambda *a, **k: orden.append("cerrar") or {"orderId": 2})
    monkeypatch.setattr(bt, "cancelar_todo",
                        lambda *a, **k: orden.append("limpiar") or {})

    Binance("K", "S").cerrar("BTCUSDT", Posicion(1, 0.0007, 78000.0))
    assert orden == ["cerrar", "limpiar"]


def test_cerrar_sin_posicion_no_manda_nada(monkeypatch):
    llamadas: list[str] = []
    monkeypatch.setattr(bt, "cerrar", lambda *a, **k: llamadas.append("x"))
    r = Binance("K", "S").cerrar("BTCUSDT", Posicion())
    assert not llamadas and "sin_efecto" in r


# ================================== el mismo par, escrito como cada casa

def test_el_simbolo_del_BOT_GUARDADO_funciona_en_Binance(monkeypatch):
    """EL AGUJERO QUE ABRIA ELEGIR EXCHANGE SIN TOCAR EL DOCUMENTO DEL BOT.

    El archivo del bot se escribió cuando había un solo exchange, así que lleva
    el símbolo con guion —BTC-USDT— adentro. Elegir Binance le pedía ese
    símbolo a Binance, y Binance no contesta "formato inválido": contesta que
    ese símbolo no existe, que manda a revisar el catálogo cuando el par existe
    perfectamente.
    """
    vistos = []
    monkeypatch.setattr(bt, "velas",
                        lambda s, i, l, base=None: vistos.append(s) or _velas())
    monkeypatch.setattr(bt, "contrato",
                        lambda s, b=None: vistos.append(s) or dict(_CONTRATO))
    monkeypatch.setattr(bt, "posicion",
                        lambda s, *a, **k: vistos.append(s) or
                        {"lado": 0, "cantidad": 0.0, "precio_entrada": float("nan")})

    a = Binance("K", "S")
    a.velas("BTC-USDT", "1h", 5)
    a.contrato("BTC-USDT")
    a.posicion("BTC-USDT")
    assert vistos == ["BTCUSDT", "BTCUSDT", "BTCUSDT"]


def test_se_traduce_EN_LOS_DOS_SENTIDOS():
    """Cada casa recibe lo suyo, venga como venga el símbolo guardado."""
    for entrada in ("BTCUSDT", "BTC-USDT", "btc-usdt"):
        assert a_simbolo(entrada, con_guion=True) == "BTC-USDT"
        assert a_simbolo(entrada, con_guion=False) == "BTCUSDT"


def test_las_cotizaciones_de_CUATRO_letras_no_se_parten_mal():
    """BTCUSDC partido por longitud fija da "BTCU" + "SDC", que es un símbolo
    que no existe. Y BTCUSD sí existe: son tres letras."""
    assert a_simbolo("BTCUSDC", con_guion=True) == "BTC-USDC"
    assert a_simbolo("BTCUSD", con_guion=True) == "BTC-USD"


def test_lo_que_no_reconoce_pasa_TAL_CUAL():
    """No adivina. Inventar un guion en el lugar equivocado daría un símbolo
    que existe y es otro; mejor que falle del lado del exchange con su propio
    mensaje."""
    assert a_simbolo("RAROUNO", con_guion=True) == "RAROUNO"


# --------------------------------------------- margen aislado, antes de abrir

def test_antes_de_abrir_se_pone_margen_aislado_y_apalancamiento_bajo(monkeypatch):
    """El primer trade de una estrategia abrió en cruzado a 20× y el usuario
    preguntó por qué: nadie lo fijaba. Ahora se fija en cada apertura, y con
    el apalancamiento del adaptador, no el que haya quedado en la cuenta."""
    f = _Falso(monkeypatch)
    visto = {}

    def _margen(simbolo, k, s, *, apalancamiento, base):
        f.hechos.append("margen")
        visto.update(simbolo=simbolo, apalancamiento=apalancamiento)
        return {"margen": "aislado", "apalancamiento": apalancamiento}
    monkeypatch.setattr(bt, "preparar_margen", _margen)
    f.a.abrir("BTCUSDT", 1, 0.0007, stop=74000.0, objetivo=86000.0)
    assert f.hechos[:2] == ["margen", "abrir"]
    assert visto == {"simbolo": "BTCUSDT", "apalancamiento": Binance.APALANCAMIENTO}


def test_si_el_margen_no_se_puede_poner_aislado_NO_se_abre(monkeypatch):
    """Abrir en cruzado sería exactamente lo que se quiso evitar."""
    f = _Falso(monkeypatch)

    def _falla(*a, **k):
        raise bt.BinanceError("[-4048] Margin type cannot be changed if there exists position.",
                              codigo=-4048)
    monkeypatch.setattr(bt, "preparar_margen", _falla)
    with pytest.raises(bt.BinanceError, match="-4048"):
        f.a.abrir("BTCUSDT", 1, 0.0007, stop=74000.0, objetivo=86000.0)
    assert "abrir" not in f.hechos


def test_ya_esta_asi_no_es_error(monkeypatch):
    """-4046 (ya en aislado) y -4059 (mismo apalancamiento) no son fallos."""
    import io
    import json
    import urllib.error
    llamadas = []

    def _abrir(req, timeout=30):
        llamadas.append(req.full_url)
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {},
            io.BytesIO(json.dumps({"code": -4046, "msg": "No need to change margin type."}).encode()))
    monkeypatch.setattr(bt.urllib.request, "urlopen", _abrir)
    monkeypatch.setattr(bt, "_DESFASE_MEDIDO", 1.0)
    r = bt.preparar_margen("BTCUSDT", "K", "S", apalancamiento=5, base="https://x")
    assert r["margen"] == "aislado" and len(llamadas) == 2
