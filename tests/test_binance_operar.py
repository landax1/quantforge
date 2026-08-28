"""Operar futuros perpetuos en Binance por API.

LO QUE MAS SE DEFIENDE ACA ES LA FIRMA, porque es lo que falla en silencio: el
exchange contesta "clave inválida" y eso manda a revisar la clave cuando el
problema es el texto que se firmó. En BingX hubo TRES errores de este tipo y
ninguno avisaba.

Y las reglas de Binance NO son las de BingX, así que copiar aquel código habría
producido exactamente los mismos errores con otro disfraz.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse

import pytest

from botiquant.data import binance_trade as bx


class _Respuesta:
    def __init__(self, cuerpo):
        self._c = json.dumps(cuerpo).encode()

    def read(self):
        return self._c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _espiar(monkeypatch, devuelve=None):
    """Reemplaza la red y guarda el pedido tal como habría salido."""
    visto = {}

    def _abrir(req, timeout=30):
        visto["url"] = req.full_url
        visto["metodo"] = req.get_method()
        visto["headers"] = {k.lower(): v for k, v in req.headers.items()}
        visto["cuerpo"] = req.data.decode() if req.data else ""
        return _Respuesta(devuelve if devuelve is not None else {})

    monkeypatch.setattr(bx.urllib.request, "urlopen", _abrir)
    return visto


# ============================================================== la firma

def test_se_firma_EXACTAMENTE_la_cadena_que_viaja(monkeypatch):
    """LA REGLA QUE NO SE PUEDE ROMPER.

    La firma va sobre `totalParams`, que es lo que efectivamente se manda. Si
    se firmara una versión distinta —ordenada, escapada de otra forma— la firma
    sería válida sobre un texto que el servidor arma de otra manera, y no
    coincide nunca. El síntoma es "signature not valid", que manda a revisar la
    clave.
    """
    visto = _espiar(monkeypatch, {"ok": 1})
    bx._pedir("/fapi/v2/balance", {"b": "2", "a": "1"},
              api_key="K", secret="S", base="https://x")

    query = visto["url"].split("?", 1)[1]
    firmado, _, firma = query.rpartition("&signature=")
    esperada = hmac.new(b"S", firmado.encode(), hashlib.sha256).hexdigest()
    assert firma == esperada, "se firmó algo distinto de lo que se mandó"


def test_NO_se_ordenan_los_parametros(monkeypatch):
    """En BingX hay que ordenarlos; acá NO.

    Binance dice que pueden ir en cualquier orden, pero la firma se calcula
    sobre el texto tal como viaja. Ordenar acá y no allá —o al revés— es
    exactamente el error que costó tres intentos en BingX.
    """
    visto = _espiar(monkeypatch, {})
    bx._pedir("/fapi/v2/balance", {"zeta": 1, "alfa": 2},
              api_key="K", secret="S", base="https://x")
    query = visto["url"].split("?", 1)[1]
    assert query.index("zeta") < query.index("alfa"), "los reordenó"


def test_la_firma_va_AL_FINAL(monkeypatch):
    visto = _espiar(monkeypatch, {})
    bx._pedir("/fapi/v2/balance", {"a": 1}, api_key="K", secret="S",
              base="https://x")
    assert visto["url"].split("?", 1)[1].split("&")[-1].startswith("signature=")


def test_la_cabecera_de_la_clave_es_la_de_Binance(monkeypatch):
    """`X-MBX-APIKEY`. La de BingX es `X-BX-APIKEY`: con la equivocada el
    pedido va sin identificar y el error habla de permisos."""
    visto = _espiar(monkeypatch, {})
    bx._pedir("/fapi/v2/balance", api_key="K", secret="S", base="https://x")
    assert visto["headers"].get("X-mbx-apikey".lower()) == "K"


def test_un_POST_manda_los_parametros_en_el_CUERPO(monkeypatch):
    """En la URL, Binance no los ve — y la firma quedaría sobre parámetros que
    el servidor no recibió."""
    visto = _espiar(monkeypatch, {})
    bx._pedir("/fapi/v1/order", {"symbol": "BTCUSDT"}, api_key="K", secret="S",
              metodo="POST", base="https://x")
    assert "?" not in visto["url"]
    assert "symbol=BTCUSDT" in visto["cuerpo"]
    assert "signature=" in visto["cuerpo"]


def test_el_secreto_NUNCA_viaja(monkeypatch):
    """Se usa para firmar y no sale de la función. Si apareciera en la URL o en
    una cabecera, quedaría en cualquier registro intermedio."""
    visto = _espiar(monkeypatch, {})
    bx._pedir("/fapi/v2/balance", {"a": 1}, api_key="K",
              secret="SECRETO_QUE_NO_PUEDE_SALIR", base="https://x")
    todo = visto["url"] + visto["cuerpo"] + json.dumps(visto["headers"])
    assert "SECRETO_QUE_NO_PUEDE_SALIR" not in todo


def test_sin_clave_no_se_firma_ni_se_manda_timestamp(monkeypatch):
    """Los endpoints públicos no la necesitan, y mandar una firma inválida ahí
    convierte un pedido que anda en uno que falla."""
    visto = _espiar(monkeypatch, {})
    bx._pedir("/fapi/v1/ping", base="https://x")
    assert "signature" not in visto["url"]
    assert "timestamp" not in visto["url"]


# ============================================================== los errores

def test_el_codigo_del_error_se_conserva(monkeypatch):
    """-2015 es clave o permisos, -4061 es el modo de posición, -1106 un
    parámetro de más. Cada uno manda a mirar otra cosa; un mensaje genérico
    manda a revisar la clave siempre."""
    import urllib.error

    def _falla(req, timeout=30):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {},
            __import__("io").BytesIO(
                json.dumps({"code": -4061,
                            "msg": "Order's position side does not match"}).encode()))

    monkeypatch.setattr(bx.urllib.request, "urlopen", _falla)
    with pytest.raises(bx.BinanceError) as e:
        bx._pedir("/fapi/v1/order", api_key="K", secret="S", base="https://x")
    assert e.value.codigo == -4061
    assert "position side" in str(e.value)


# ==================================================== los mínimos del contrato

def _contrato(minimo, paso, nocional=0.0):
    return {"minimo": minimo, "paso": paso, "minimo_nocional": nocional}


def test_la_cuenta_minima_sale_del_MAYOR_de_los_dos_minimos():
    """Binance pide dos cosas a la vez: una cantidad mínima y un nocional
    mínimo. Mirar sólo uno deja pasar órdenes que el otro rechaza.

    MEDIDO con BTCUSDT a 77.499: el mínimo por cantidad son 0,001 BTC = 77
    USDT y el nocional mínimo 50. Manda el de 77.
    """
    c = _contrato(0.001, 0.001, nocional=50.0)
    assert bx.cuenta_minima(77_499, c, stop_pct=2.0, riesgo_pct=1.0) == pytest.approx(155, abs=2)

    # y al revés: si el nocional fuera el que manda, tiene que ganar él
    barato = _contrato(0.001, 0.001, nocional=500.0)
    assert bx.cuenta_minima(1_000, barato, stop_pct=2.0, riesgo_pct=1.0) > \
        bx.cuenta_minima(1_000, _contrato(0.001, 0.001), stop_pct=2.0, riesgo_pct=1.0)


def test_menos_riesgo_por_operacion_pide_MAS_cuenta():
    """Es al revés de lo que parece y por eso conviene fijarlo: arriesgar menos
    con un mínimo fijo obliga a tener más capital, no menos."""
    c = _contrato(0.001, 0.001, nocional=50.0)
    con_1 = bx.cuenta_minima(77_499, c, stop_pct=2.0, riesgo_pct=1.0)
    con_medio = bx.cuenta_minima(77_499, c, stop_pct=2.0, riesgo_pct=0.5)
    assert con_medio > con_1


def test_datos_absurdos_no_dividen_por_cero():
    c = _contrato(0.001, 0.001)
    assert bx.cuenta_minima(0, c, stop_pct=2.0, riesgo_pct=1.0) == 0.0
    assert bx.cuenta_minima(100, c, stop_pct=0, riesgo_pct=1.0) == 0.0
    assert bx.cuenta_minima(100, c, stop_pct=2.0, riesgo_pct=0) == 0.0


# ============================================ el modo de posición se pregunta

def test_el_modo_de_posicion_se_PREGUNTA(monkeypatch):
    """Cada modo quiere un parámetro distinto para cerrar y el equivocado da
    -4061 o -1106. Suponerlo es elegir al azar entre dos errores."""
    _espiar(monkeypatch, {"dualSidePosition": True})
    assert bx.modo_posicion("K", "S", base="https://x") == "cobertura"

    _espiar(monkeypatch, {"dualSidePosition": False})
    assert bx.modo_posicion("K", "S", base="https://x") == "una_via"


def test_la_posicion_se_pregunta_y_devuelve_lado_y_cantidad(monkeypatch):
    """Recordarla en memoria significa que un reinicio, o una orden puesta a
    mano en el exchange, dejan al bot operando contra una posición que cree que
    no existe."""
    _espiar(monkeypatch, [{"symbol": "BTCUSDT", "positionAmt": "-0.5",
                           "entryPrice": "70000"}])
    p = bx.posicion("BTCUSDT", "K", "S", base="https://x")
    assert p["lado"] == -1
    assert p["cantidad"] == pytest.approx(0.5)
    assert p["precio_entrada"] == pytest.approx(70000)


def test_sin_posicion_el_lado_es_cero(monkeypatch):
    _espiar(monkeypatch, [{"symbol": "BTCUSDT", "positionAmt": "0"}])
    assert bx.posicion("BTCUSDT", "K", "S", base="https://x")["lado"] == 0


# ====================================================== abrir y cerrar

_CONTRATO = {"minimo": 0.001, "paso": 0.001, "decimales_cantidad": 3,
             "minimo_nocional": 50.0}


def test_cerrar_en_una_via_manda_reduceOnly_y_NO_positionSide(monkeypatch):
    """EL ERROR QUE EN BINGX COSTO CARO: sin marcar la orden como de cierre, la
    contraria no cierra — ABRE el lado opuesto, en silencio."""
    visto = _espiar(monkeypatch, {"orderId": 1})
    bx.cerrar("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
              contrato_=_CONTRATO, base="https://x")
    assert "reduceOnly=true" in visto["cuerpo"]
    assert "positionSide" not in visto["cuerpo"], "en una vía da -4061"
    assert "side=SELL" in visto["cuerpo"], "cerrar un largo se hace vendiendo"


def test_cerrar_en_cobertura_manda_positionSide_y_NO_reduceOnly(monkeypatch):
    """Al revés que en una vía. Mandar `reduceOnly` acá da -1106, y los dos
    juntos no se pueden: por eso el modo se pregunta."""
    visto = _espiar(monkeypatch, {"orderId": 1})
    bx.cerrar("BTCUSDT", -1, 0.005, api_key="K", secret="S", modo="cobertura",
              contrato_=_CONTRATO, base="https://x")
    assert "positionSide=SHORT" in visto["cuerpo"]
    assert "reduceOnly" not in visto["cuerpo"], "en cobertura da -1106"
    assert "side=BUY" in visto["cuerpo"], "cerrar un corto se hace comprando"


def test_abrir_en_una_via_no_manda_positionSide(monkeypatch):
    visto = _espiar(monkeypatch, {"orderId": 1})
    bx.abrir("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    assert "positionSide" not in visto["cuerpo"]
    assert "side=BUY" in visto["cuerpo"]


def test_la_cantidad_se_redondea_SIEMPRE_HACIA_ABAJO(monkeypatch):
    """Hacia abajo y no al más cercano.

    Redondear hacia arriba arriesga MAS de lo que se pidió, y de a poco. Una
    orden rechazada por chica se ve; una que arriesga 1,3% cuando se pidió 1%
    no se ve nunca.
    """
    visto = _espiar(monkeypatch, {"orderId": 1})
    bx.abrir("BTCUSDT", 1, 0.0059, api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    assert "quantity=0.005" in visto["cuerpo"], visto["cuerpo"]


def test_por_debajo_del_minimo_se_NIEGA_en_vez_de_redondear_para_arriba():
    """Subirla al mínimo sería operar más grande de lo pedido sin avisar."""
    with pytest.raises(bx.BinanceError, match="por debajo del mínimo"):
        bx.abrir("BTCUSDT", 1, 0.0004, api_key="K", secret="S",
                 modo="una_via", contrato_=_CONTRATO, base="https://x")


def test_un_lado_invalido_no_manda_nada():
    with pytest.raises(bx.BinanceError):
        bx.abrir("BTCUSDT", 0, 0.01, api_key="K", secret="S", modo="una_via",
                 contrato_=_CONTRATO, base="https://x")
    with pytest.raises(bx.BinanceError):
        bx.cerrar("BTCUSDT", 0, 0.01, api_key="K", secret="S", modo="una_via",
                  contrato_=_CONTRATO, base="https://x")
