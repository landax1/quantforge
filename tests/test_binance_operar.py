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
             "minimo_nocional": 50.0, "decimales_precio": 2,
             "tick": 0.1, "tick_texto": "0.10"}


def _espiar_varias(monkeypatch, devuelve=None):
    """Como `_espiar` pero guarda TODOS los pedidos: `proteger` manda dos y
    `cancelar_todo` borra en dos servicios distintos."""
    vistos = []

    def _abrir(req, timeout=30):
        vistos.append({"url": req.full_url, "metodo": req.get_method(),
                       "cuerpo": req.data.decode() if req.data else ""})
        return _Respuesta(devuelve if devuelve is not None else {})

    monkeypatch.setattr(bx.urllib.request, "urlopen", _abrir)
    return vistos


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


def test_la_orden_pide_el_precio_de_ejecucion(monkeypatch):
    """Binance devuelve "ACK" por omisión: un acuse SIN precio de ejecución.

    Esa respuesta es la que el bot anota en su registro, así que sin pedir
    RESULT el registro dice que operó y no a cuánto — que es justo lo que hace
    falta para comparar la ejecución contra lo que esperaba la estrategia.
    """
    visto = _espiar(monkeypatch, {"orderId": 1, "avgPrice": "77000"})
    bx.abrir("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    assert "newOrderRespType=RESULT" in visto["cuerpo"]

    visto2 = _espiar(monkeypatch, {"orderId": 2})
    bx.cerrar("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
              contrato_=_CONTRATO, base="https://x")
    assert "newOrderRespType=RESULT" in visto2["cuerpo"]


def test_una_orden_a_mercado_no_manda_precio_ni_timeInForce(monkeypatch):
    """La referencia oficial dice que una MARKET pide sólo `quantity`.
    Mandar `price` o `timeInForce` la rechaza."""
    visto = _espiar(monkeypatch, {"orderId": 1})
    bx.abrir("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    assert "price=" not in visto["cuerpo"]
    assert "timeInForce" not in visto["cuerpo"]


def test_el_recvWindow_no_pasa_el_tope_de_Binance():
    """El máximo son 60.000 ms; por encima, Binance rechaza el pedido."""
    assert 0 < bx.RECV_WINDOW <= 60_000


# ================= el stop vive en el exchange, y en OTRO SERVICIO

def test_el_stop_y_el_objetivo_van_al_EXCHANGE(monkeypatch):
    """Lo que hace que apagar la aplicación no desproteja nada.

    Un bot que vigila su propio stop deja de proteger justo cuando más falta
    hace: se cortó la luz, se cerró el programa, se suspendió la laptop. Con
    las órdenes puestas del lado del exchange, apagar la app significa que no
    entra en operaciones nuevas — no que la abierta quede a la deriva.
    """
    vistos = _espiar_varias(monkeypatch, {"algoId": 1})
    r = bx.proteger("BTCUSDT", 1, stop=70000, objetivo=80000, api_key="K",
                    secret="S", modo="una_via", contrato_=_CONTRATO,
                    base="https://x")
    assert len(r) == 2, "tienen que ser DOS órdenes: stop y objetivo"
    cuerpos = [v["cuerpo"] for v in vistos]
    assert any("type=STOP_MARKET" in c for c in cuerpos)
    assert any("type=TAKE_PROFIT_MARKET" in c for c in cuerpos)
    # las dos son la contraria de la posición: un largo se protege vendiendo
    assert all("side=SELL" in c for c in cuerpos)


def test_la_condicional_va_al_ALGO_SERVICE_y_no_al_endpoint_de_siempre(monkeypatch):
    """EL CAMBIO DE BINANCE DEL 2025-12-09.

    MEDIDO el 31/8/2026: `POST /fapi/v1/order` rechaza TODOS los tipos
    condicionales con -4120, en las ocho variantes de parámetros que se
    probaron. No es una combinación mal armada: es el endpoint. Si este test se
    rompe, el bot vuelve a abrir posiciones que se creen protegidas y no lo
    están.
    """
    vistos = _espiar_varias(monkeypatch, {"algoId": 1})
    bx.proteger("BTCUSDT", 1, stop=70000, objetivo=float("nan"), api_key="K",
                secret="S", modo="una_via", contrato_=_CONTRATO,
                base="https://x")
    assert all("/fapi/v1/algoOrder" in v["url"] for v in vistos)
    assert all("algoType=CONDITIONAL" in v["cuerpo"] for v in vistos)


def test_el_parametro_del_disparador_es_triggerPrice(monkeypatch):
    """EN EL ALGO SERVICE SE LLAMA `triggerPrice`, NO `stopPrice`.

    Es el mismo número con otro nombre. Mandarlo con el viejo lo ignora, y la
    orden queda registrada SIN disparador: aparece en la lista, parece que está
    todo bien, y nunca se ejecuta.
    """
    vistos = _espiar_varias(monkeypatch, {"algoId": 1})
    bx.proteger("BTCUSDT", -1, stop=80000, objetivo=float("nan"), api_key="K",
                secret="S", modo="una_via", contrato_=_CONTRATO,
                base="https://x")
    assert "triggerPrice=80000" in vistos[0]["cuerpo"]
    assert "stopPrice" not in vistos[0]["cuerpo"]


def test_el_precio_del_stop_se_AJUSTA_AL_TICK(monkeypatch):
    """SIN ESTO EL STOP NO ENTRA.

    MEDIDO: un stop calculado como `precio * 0.95` da 74.783,525 y Binance lo
    rechaza con -1111 "Precision is over the maximum defined for this asset".
    El número es correcto; le sobran decimales.

    Se redondea al TICK y no a los decimales, que son dos límites distintos: en
    BTCUSDT el tick es 0,10 y los decimales son 2, así que 74.783,52 respeta
    los decimales y NO respeta el tick.
    """
    vistos = _espiar_varias(monkeypatch, {"algoId": 1})
    bx.proteger("BTCUSDT", 1, stop=74783.525, objetivo=float("nan"),
                api_key="K", secret="S", modo="una_via", contrato_=_CONTRATO,
                base="https://x")
    assert "triggerPrice=74783.5" in vistos[0]["cuerpo"]


def test_closePosition_va_SIN_cantidad(monkeypatch):
    """`closePosition` no se puede usar con `quantity` ni con `reduceOnly`.

    Y es lo que se quiere: si el stop cerrara sólo una parte, quedaría la mitad
    de la posición sin protección y nadie lo miraría.
    """
    vistos = _espiar_varias(monkeypatch, {"algoId": 1})
    bx.proteger("BTCUSDT", 1, stop=70000, objetivo=float("nan"), api_key="K",
                secret="S", modo="una_via", contrato_=_CONTRATO,
                base="https://x")
    assert "closePosition=true" in vistos[0]["cuerpo"]
    assert "quantity" not in vistos[0]["cuerpo"]
    assert "reduceOnly" not in vistos[0]["cuerpo"]


def test_el_disparador_mira_el_precio_de_MARCA(monkeypatch):
    """Es el que Binance usa para liquidar. Con el precio del contrato, una
    mecha en un libro fino dispara un stop que la liquidación no habría
    tocado."""
    vistos = _espiar_varias(monkeypatch, {"algoId": 1})
    bx.proteger("BTCUSDT", 1, stop=70000, objetivo=float("nan"), api_key="K",
                secret="S", modo="una_via", contrato_=_CONTRATO,
                base="https://x")
    assert "workingType=MARK_PRICE" in vistos[0]["cuerpo"]


def test_sin_stop_ni_objetivo_no_manda_ordenes(monkeypatch):
    """Una estrategia sin salidas por precio no tiene qué proteger, y mandar
    una orden con disparador vacío la haría rechazar."""
    _espiar_varias(monkeypatch, {"algoId": 1})
    assert bx.proteger("BTCUSDT", 1, stop=float("nan"), objetivo=float("nan"),
                       api_key="K", secret="S", modo="una_via",
                       contrato_=_CONTRATO, base="https://x") == []


# ================================ el minimo por NOCIONAL, que es otro limite

def test_el_minimo_por_NOCIONAL_tambien_frena_la_orden(monkeypatch):
    """SON DOS LIMITES DISTINTOS Y PASAR UNO NO DICE NADA DEL OTRO.

    En BTCUSDT manda la cantidad —0,001 BTC son 78 USDT contra 50 de nocional—
    pero en un símbolo barato manda el nocional, y ahí una orden que pasa el
    control de cantidad la rechaza el exchange igual. Es el mismo hueco que
    apareció en Bybit, donde el nocional manda en seis de los diez líquidos.
    """
    barato = {"minimo": 1.0, "paso": 1.0, "decimales_cantidad": 0,
              "minimo_nocional": 50.0}
    _espiar(monkeypatch, {"orderId": 1})
    with pytest.raises(bx.BinanceError) as e:
        bx.abrir("ALGOUSDT", 1, 10, precio=0.20, api_key="K", secret="S",
                 modo="una_via", contrato_=barato, base="https://x")
    assert "nocional" in str(e.value)


def test_con_nocional_suficiente_la_orden_sale(monkeypatch):
    """El control no puede frenar una orden legítima."""
    barato = {"minimo": 1.0, "paso": 1.0, "decimales_cantidad": 0,
              "minimo_nocional": 50.0}
    visto = _espiar(monkeypatch, {"orderId": 1})
    bx.abrir("ALGOUSDT", 1, 300, precio=0.20, api_key="K", secret="S",
             modo="una_via", contrato_=barato, base="https://x")
    assert "quantity=300" in visto["cuerpo"]


def test_sin_precio_el_nocional_no_se_comprueba(monkeypatch):
    """Una orden a mercado no lleva precio. Inventar uno para poder comprobar
    sería peor que no comprobar: lo hace el exchange."""
    barato = {"minimo": 1.0, "paso": 1.0, "decimales_cantidad": 0,
              "minimo_nocional": 50.0}
    visto = _espiar(monkeypatch, {"orderId": 1})
    bx.abrir("ALGOUSDT", 1, 10, api_key="K", secret="S", modo="una_via",
             contrato_=barato, base="https://x")
    assert "quantity=10" in visto["cuerpo"]


# ============================= comprobar que el stop QUEDO, y limpiar despues

def test_las_ordenes_abiertas_se_pueden_leer(monkeypatch):
    """QUE `proteger` NO HAYA FALLADO NO SIGNIFICA QUE EL STOP ESTE PUESTO.

    Significa que el pedido se aceptó. La diferencia entre esas dos cosas es
    una posición que uno cree protegida y no lo está, y eso se descubre el día
    que el precio va en contra.
    """
    _espiar(monkeypatch, [{"symbol": "BTCUSDT", "type": "STOP_MARKET",
                           "stopPrice": "70000"}])
    o = bx.ordenes_abiertas("BTCUSDT", "K", "S", base="https://x")
    assert o[0]["type"] == "STOP_MARKET"


def test_cancelar_todo_es_un_DELETE(monkeypatch):
    """Va como DELETE y firmado: un GET no cancelaría nada y no avisaría."""
    visto = _espiar(monkeypatch, {"code": 200})
    bx.cancelar_todo("BTCUSDT", "K", "S", base="https://x")
    assert visto["metodo"] == "DELETE"
    assert "signature=" in visto["cuerpo"]


def test_las_condicionales_NO_ESTAN_donde_las_demas_ordenes(monkeypatch):
    """`ordenes_abiertas` NO LAS VE, Y NO AVISA: DEVUELVE UNA LISTA VACIA.

    MEDIDO el 31/8/2026 con un stop y un objetivo correctamente puestos:
    `/fapi/v1/openOrders` devolvió CERO órdenes. Preguntar en el lugar viejo da
    "no hay stop" cuando lo hay —una alarma falsa permanente— y jamás confirma
    que lo haya.
    """
    visto = _espiar(monkeypatch, [{"algoId": 7, "orderType": "STOP_MARKET",
                                   "triggerPrice": "74783.50",
                                   "algoStatus": "NEW", "closePosition": True}])
    c = bx.condicionales_abiertas("BTCUSDT", "K", "S", base="https://x")
    assert "/fapi/v1/openAlgoOrders" in visto["url"]
    # el Algo Service los llama distinto: `orderType` y `triggerPrice`
    assert c[0]["tipo"] == "STOP_MARKET"
    assert c[0]["disparo"] == 74783.50


def test_cancelar_todo_borra_EN_LOS_DOS_SERVICIOS(monkeypatch):
    """Las comunes y las condicionales viven separadas desde el cambio.

    MEDIDO: después de cerrar la posición las dos condicionales seguían vivas.
    Cancelar sólo las comunes deja el stop y el objetivo dando vueltas.
    """
    vistos = _espiar_varias(monkeypatch, {"code": 200})
    bx.cancelar_todo("BTCUSDT", "K", "S", base="https://x")
    urls = " ".join(v["url"] for v in vistos)
    assert "/fapi/v1/allOpenOrders" in urls
    assert "/fapi/v1/algoOpenOrders" in urls
    assert all(v["metodo"] == "DELETE" for v in vistos)


def test_el_precio_de_ejecucion_SE_PREGUNTA_APARTE(monkeypatch):
    """NI SIQUIERA CON `newOrderRespType=RESULT` VIENE EN LA RESPUESTA.

    MEDIDO el 31/8/2026 en una orden a mercado llenada entera: `executedQty`
    vino bien y `avgPrice` vino en None, porque Binance responde antes de
    agregar los llenados. Sin preguntar aparte, el registro dice que operó pero
    no a cuánto.
    """
    _espiar(monkeypatch, {"orderId": 5, "status": "FILLED",
                          "executedQty": "0.0007", "avgPrice": "78728.30"})
    d = bx.detalle_orden("BTCUSDT", 5, api_key="K", secret="S", base="https://x")
    assert d["precio"] == 78728.30 and d["cantidad"] == 0.0007
