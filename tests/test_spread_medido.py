"""El spread se mide; si no se puede medir, no se inventa.

Cada entrada del catalogo lleva un `spread` y ese numero entra en TODOS los
backtests de ese instrumento. Un spread inventado no falla nunca: el backtest
corre y cobra un costo que no es el que se paga.
"""

from __future__ import annotations

import pytest

from botiquant.data import spread as sp


class _Resp:
    def __init__(self, code, cuerpo=None):
        self.status_code = code
        self._c = cuerpo or {}

    def json(self):
        return self._c


def _dia(mult, primero, deltas):
    """Un dia como lo devuelve Dukascopy: diferencias acumuladas, no precios."""
    return {"multiplier": mult, "close": primero,
            "times": [0] + [1] * len(deltas),
            "closes": [0] + list(deltas)}


def _red(monkeypatch, por_lado):
    """`por_lado` mapea 'BID'/'ASK' a una respuesta (o a None para 429)."""
    pedidos = []

    class _C:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url):
            pedidos.append(url)
            lado = "ASK" if "/ASK/" in url else "BID"
            r = por_lado.get(lado)
            return r if r is not None else _Resp(429)

    monkeypatch.setattr(sp.httpx, "Client", _C)
    monkeypatch.setattr(sp.time, "sleep", lambda *_: None)
    return pedidos


# ------------------------------------------------------------- la medicion

def test_el_spread_es_ask_menos_bid(monkeypatch):
    _red(monkeypatch, {
        "BID": _Resp(200, _dia(0.001, 100.000, [0, 0, 0])),
        "ASK": _Resp(200, _dia(0.001, 100.020, [0, 0, 0])),
    })
    m = sp.medir("X-USD")
    assert m.spread == pytest.approx(0.02)
    assert m.precio == pytest.approx(100.0)


def test_usa_la_MEDIANA_y_no_el_promedio(monkeypatch):
    """En la apertura y el cierre el spread se abre varias veces y vuelve. El
    promedio se lo come entero y devuelve un numero que nadie paga operando en
    horario normal.

    Acá tres minutos normales y uno con el spread cien veces mas ancho: la
    mediana lo ignora, el promedio lo tomaria en serio.
    """
    _red(monkeypatch, {
        "BID": _Resp(200, _dia(0.001, 100.0, [0, 0, 0])),
        # el ultimo minuto abre el spread a 1,0 en vez de 0,01
        "ASK": _Resp(200, _dia(0.001, 100.01, [0, 0, 990])),
    })
    m = sp.medir("X-USD")
    assert m.spread == pytest.approx(0.01), "la mediana no se deja arrastrar"


def test_el_precio_viaja_con_la_medicion(monkeypatch):
    """Sin el precio, "0,053" no se puede juzgar: no es lo mismo sobre 1,07
    que sobre 25.000. El porcentaje es lo unico comparable entre mercados."""
    _red(monkeypatch, {
        "BID": _Resp(200, _dia(0.001, 200.0, [0, 0])),
        "ASK": _Resp(200, _dia(0.001, 200.1, [0, 0])),
    })
    m = sp.medir("X-USD")
    assert m.pct == pytest.approx(0.05)


# --------------------------------------------- lo que NO hace: estimar

def test_sin_ASK_levanta_y_dice_que_falta_el_ASK(monkeypatch):
    """El caso real y el motivo de que el mensaje distinga.

    MEDIDO en GAS.CMD-USD: diez fechas, diez veces BID sí y ASK no. Eso no es
    un límite temporal ni una fecha mal elegida —que se arreglarían esperando o
    probando otro día— sino que ese instrumento no publica ASK acá. Decir
    "probá más tarde" mandaría a esperar algo que no va a pasar.
    """
    _red(monkeypatch, {"BID": _Resp(200, _dia(0.001, 100.0, [0])), "ASK": None})
    with pytest.raises(sp.SpreadDesconocido, match="no ASK|no publica ASK"):
        sp.medir("GAS.CMD-USD")


def test_sin_ningun_dato_tambien_levanta(monkeypatch):
    _red(monkeypatch, {"BID": None, "ASK": None})
    with pytest.raises(sp.SpreadDesconocido):
        sp.medir("X-USD")


def test_no_devuelve_cero_ni_un_valor_prudente(monkeypatch):
    """La tentacion es devolver algo "por las dudas". Un spread de cero hace
    que toda estrategia parezca mas rentable de lo que es, y uno inventado
    cobra un costo que no se paga; las dos cosas sin fallar."""
    _red(monkeypatch, {"BID": None, "ASK": None})
    with pytest.raises(sp.SpreadDesconocido):
        sp.medir("X-USD")
    assert not hasattr(sp, "SPREAD_POR_DEFECTO")


def test_sin_codigo_no_sale_a_la_red(monkeypatch):
    pedidos = _red(monkeypatch, {})
    with pytest.raises(sp.SpreadDesconocido):
        sp.medir("")
    assert pedidos == []


def test_un_multiplicador_absurdo_se_descarta(monkeypatch):
    """Cero daria division por cero; mayor que uno invertiria los precios."""
    _red(monkeypatch, {"BID": _Resp(200, {"multiplier": 0, "close": 1,
                                          "times": [0], "closes": [0]}),
                       "ASK": _Resp(200, {"multiplier": 0, "close": 1,
                                          "times": [0], "closes": [0]})})
    with pytest.raises(sp.SpreadDesconocido):
        sp.medir("X-USD")


def test_las_fechas_son_de_anios_distintos():
    """El spread cambia con la volatilidad: tres dias de la misma semana dan
    un numero que solo vale para esa semana."""
    anios = {f.split("/")[0] for f in sp.DIAS}
    assert len(sp.DIAS) >= 3
    assert len(anios) >= 3


# =========================================================================
# El segundo camino: los archivos por dia
# =========================================================================
#
# Existe por un caso concreto: GAS.CMD-USD publica BID y no ASK en la API de
# minutos —diez fechas probadas, diez veces igual—, y el datafeed de archivos,
# que es de la misma casa y otro servidor, si tiene los dos lados.

import datetime as dt
import lzma

from botiquant.data import dukascopy as dk


def _bi5(velas):
    """Un .bi5 como el que sirve Dukascopy: (minuto, apertura, cierre, min, max, vol)."""
    return lzma.compress(b"".join(dk._REGISTRO.pack(*v) for v in velas),
                         format=lzma.FORMAT_ALONE)


def _red_archivos(monkeypatch, por_lado):
    pedidos = []

    class _C:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url):
            pedidos.append(url)
            lado = "ASK" if "ASK_candles" in url else "BID"
            r = por_lado.get(lado)
            return r if r is not None else _Resp(429)

    monkeypatch.setattr(sp.httpx, "Client", _C)
    monkeypatch.setattr(sp.time, "sleep", lambda *_: None)
    return pedidos


class _RespBin:
    def __init__(self, code, contenido=b""):
        self.status_code = code
        self.content = contenido


def test_desde_archivos_mide_ask_menos_bid(monkeypatch):
    _red_archivos(monkeypatch, {
        "BID": _RespBin(200, _bi5([(0, 27000, 27000, 27000, 27000, 1.0),
                                   (60, 27100, 27100, 27100, 27100, 1.0)])),
        "ASK": _RespBin(200, _bi5([(0, 27020, 27020, 27020, 27020, 1.0),
                                   (60, 27120, 27120, 27120, 27120, 1.0)])),
    })
    m = sp.medir_desde_archivos("gascmdusd", 1e4)
    assert m.spread == pytest.approx(0.002)
    assert m.fuente == "archivos"


def test_los_minutos_sin_cotizacion_no_cuentan(monkeypatch):
    """Vienen en cero. Contarlos mete un spread de cero en la mediana y
    abarata el instrumento entero."""
    _red_archivos(monkeypatch, {
        "BID": _RespBin(200, _bi5([(0, 27000, 27000, 27000, 27000, 1.0),
                                   (60, 0, 0, 0, 0, 0.0)])),
        "ASK": _RespBin(200, _bi5([(0, 27020, 27020, 27020, 27020, 1.0),
                                   (60, 0, 0, 0, 0, 0.0)])),
    })
    m = sp.medir_desde_archivos("gascmdusd", 1e4)
    assert m.minutos == 3, "tres días con un minuto útil cada uno"
    assert m.spread == pytest.approx(0.002)


def test_desde_archivos_tambien_levanta_si_no_puede(monkeypatch):
    _red_archivos(monkeypatch, {"BID": None, "ASK": None})
    with pytest.raises(sp.SpreadDesconocido):
        sp.medir_desde_archivos("gascmdusd", 1e4)


def test_la_medicion_dice_de_donde_salio(monkeypatch):
    """Son dos servidores distintos de la misma casa y no siempre tienen lo
    mismo. Al leer un spread hay que poder saber por cuál se midió."""
    _red_archivos(monkeypatch, {
        "BID": _RespBin(200, _bi5([(0, 100, 100, 100, 100, 1.0)])),
        "ASK": _RespBin(200, _bi5([(0, 110, 110, 110, 110, 1.0)])),
    })
    assert sp.medir_desde_archivos("x", 1e2).fuente == "archivos"

    _red(monkeypatch, {"BID": _Resp(200, _dia(0.001, 100.0, [0])),
                       "ASK": _Resp(200, _dia(0.001, 100.02, [0]))})
    assert sp.medir("X-USD").fuente == "api"


def test_las_fechas_de_archivo_son_de_anios_distintos():
    assert len({d.year for d in sp.DIAS_ARCHIVO}) >= 3
