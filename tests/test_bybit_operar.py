"""Operar futuros perpetuos en Bybit por API.

LO QUE SE DEFIENDE ACA SON LAS CUATRO DIFERENCIAS CON BINANCE QUE FALLAN
CALLADAS. Ninguna de las cuatro da error al copiarla mal:

  1. el rechazo llega con HTTP 200 y `retCode` adentro del cuerpo;
  2. la firma es sobre `timestamp + api_key + recv_window + carga`, y va en una
     cabecera, no en la query;
  3. las velas llegan de nueva a vieja;
  4. `reduceOnly` y `positionIdx` conviven, al revés que en Binance.

Cada una tiene su test acá, y cada test dice qué pasaría si se rompiera.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from botiquant.data import bybit_trade as by

#: El contrato de BTCUSDT tal como lo devuelve Bybit, MEDIDO el 31/8/2026.
_CONTRATO = {
    "simbolo": "BTCUSDT", "minimo": 0.001, "paso": 0.001, "paso_texto": "0.001",
    "decimales_cantidad": 3, "maximo": 150.0, "minimo_nocional": 5.0,
    "tick": 0.1, "tick_texto": "0.1", "decimales_precio": 1,
}


class _Respuesta:
    def __init__(self, cuerpo):
        self._c = json.dumps(cuerpo).encode()

    def read(self):
        return self._c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _sobre(result=None, ret_code=0, ret_msg="OK"):
    """Un cuerpo de Bybit completo: el resultado siempre viene envuelto."""
    return {"retCode": ret_code, "retMsg": ret_msg,
            "result": result if result is not None else {}, "time": 1}


def _espiar(monkeypatch, devuelve=None):
    """Reemplaza la red y guarda el pedido tal como habría salido."""
    visto = {}

    def _abrir(req, timeout=30):
        visto["url"] = req.full_url
        visto["metodo"] = req.get_method()
        visto["headers"] = {k.lower(): v for k, v in req.headers.items()}
        visto["cuerpo"] = req.data.decode() if req.data else ""
        return _Respuesta(devuelve if devuelve is not None else _sobre())

    monkeypatch.setattr(by.urllib.request, "urlopen", _abrir)
    return visto


# ================================================== 1) el error viene con 200

def test_un_rechazo_con_HTTP_200_ES_UN_ERROR(monkeypatch):
    """LA DIFERENCIA MAS PELIGROSA CON BINANCE.

    Binance rechaza con 4xx y el módulo lo detecta por `HTTPError`. Bybit
    contesta 200 y mete el rechazo adentro del cuerpo. Si este test se rompe,
    el código está dando por buenas las respuestas de error: una lista vacía en
    vez de un fallo, o una orden que se cree mandada y no existe.
    """
    _espiar(monkeypatch, _sobre(ret_code=10001, ret_msg="params error: symbol invalid"))
    with pytest.raises(by.BybitError) as e:
        by._pedir("/v5/market/instruments-info", {"symbol": "NOEXISTE"},
                  base="https://x")
    assert e.value.codigo == 10001
    assert "symbol invalid" in str(e.value)


def test_el_codigo_del_rechazo_se_conserva(monkeypatch):
    """Cada retCode manda a mirar otra cosa: 10003 la clave, 10002 el reloj.

    Envolverlos todos en un mensaje genérico manda a revisar la clave siempre,
    que es el error que costó tres intentos en BingX.
    """
    _espiar(monkeypatch, _sobre(ret_code=10002, ret_msg="invalid request, please check your timestamp"))
    with pytest.raises(by.BybitError) as e:
        by._pedir("/v5/account/info", api_key="K", secret="S", base="https://x")
    assert e.value.codigo == 10002


def test_una_respuesta_buena_devuelve_el_result_pelado(monkeypatch):
    _espiar(monkeypatch, _sobre({"list": [{"symbol": "BTCUSDT"}]}))
    d = by._pedir("/v5/market/instruments-info", base="https://x")
    assert d == {"list": [{"symbol": "BTCUSDT"}]}


# ============================================================== 2) la firma

def test_la_firma_es_ts_mas_clave_mas_ventana_mas_query(monkeypatch):
    """NO SE FIRMAN LOS PARAMETROS SOLOS, como en Binance.

    Firmar sólo la query —que es lo que uno copia sin pensar— da "invalid
    signature", que manda a revisar la clave cuando la clave está bien.
    """
    visto = _espiar(monkeypatch)
    by._pedir("/v5/position/list", {"category": "linear", "symbol": "BTCUSDT"},
              api_key="K", secret="S", base="https://x")

    h = visto["headers"]
    query = visto["url"].split("?", 1)[1]
    esperada = hmac.new(
        b"S", f"{h['x-bapi-timestamp']}K{h['x-bapi-recv-window']}{query}".encode(),
        hashlib.sha256).hexdigest()
    assert h["x-bapi-sign"] == esperada


def test_la_firma_NO_viaja_en_la_query(monkeypatch):
    """En Binance la firma es un parámetro más; acá es una cabecera.

    Mandarla en la query además de en la cabecera cambiaría el texto firmado y
    la firma dejaría de coincidir consigo misma.
    """
    visto = _espiar(monkeypatch)
    by._pedir("/v5/account/info", api_key="K", secret="S", base="https://x")
    assert "signature" not in visto["url"]
    assert "sign=" not in visto["url"]
    assert "x-bapi-sign" in visto["headers"]


def test_un_POST_firma_EXACTAMENTE_el_cuerpo_QUE_VIAJA(monkeypatch):
    """LA REGLA QUE NO SE PUEDE ROMPER.

    El cuerpo se serializa UNA vez: se firma ese texto y se manda ese mismo
    texto. Volver a serializarlo para enviarlo puede cambiar el orden de las
    claves o los espacios, y entonces la firma es válida sobre un texto que
    nunca viajó.
    """
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")

    h = visto["headers"]
    esperada = hmac.new(
        b"S",
        f"{h['x-bapi-timestamp']}K{h['x-bapi-recv-window']}{visto['cuerpo']}".encode(),
        hashlib.sha256).hexdigest()
    assert h["x-bapi-sign"] == esperada, "se firmó algo distinto de lo que se mandó"


def test_un_POST_manda_json_y_lo_dice(monkeypatch):
    """Binance manda formulario; Bybit, JSON. El servidor parsea según esto."""
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    assert visto["headers"]["content-type"] == "application/json"
    assert json.loads(visto["cuerpo"])["symbol"] == "BTCUSDT"


def test_sin_credenciales_no_se_manda_ninguna_cabecera_de_firma(monkeypatch):
    """Los datos de mercado son públicos: pedirlos no debe exigir clave."""
    visto = _espiar(monkeypatch, _sobre({"list": []}))
    by._pedir("/v5/market/time", base="https://x")
    assert not any(k.startswith("x-bapi") for k in visto["headers"])


# =========================================================== 3) las velas

def _kline(filas):
    return _sobre({"category": "linear", "list": filas})


def test_las_velas_se_devuelven_DE_VIEJA_A_NUEVA(monkeypatch):
    """BYBIT LAS MANDA AL REVES Y NO ROMPE NADA VISIBLE.

    El motor espera de vieja a nueva porque así llegan de Binance y de BingX.
    Con el orden invertido, las medias y el ADX se calculan igual y devuelven
    números creíbles: el bot opera al revés y parece que anda.
    """
    # Como llegan de Bybit: la más reciente primero.
    _espiar(monkeypatch, _kline([
        ["1788188400000", "78591.9", "78749.1", "78164.2", "78630", "3069.9", "1"],
        ["1788184800000", "77827.7", "78670.7", "77697.9", "78591.9", "6831.4", "1"],
        ["1788181200000", "77900.1", "78250", "77680", "77827.7", "5018.7", "1"],
    ]))
    df = by.velas("BTCUSDT", "1h", 3, base="https://x")

    assert df.index.is_monotonic_increasing, "las velas quedaron al revés"
    assert float(df["close"].iloc[-1]) == 78630.0, "la última no es la más nueva"
    assert float(df["close"].iloc[0]) == 77827.7


def test_las_velas_traen_las_columnas_que_espera_el_motor(monkeypatch):
    _espiar(monkeypatch, _kline([
        ["1788181200000", "1", "2", "0.5", "1.5", "10", "1"]]))
    df = by.velas("BTCUSDT", "1h", 1, base="https://x")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert str(df.index.tz) == "UTC"


def test_el_intervalo_se_TRADUCE_y_no_se_manda_crudo(monkeypatch):
    """Bybit usa "60", no "1h". Y NO rechaza "1h": devuelve otra cosa o vacío.

    Un vacío silencioso se lee como "el símbolo no existe", que manda a
    revisar el símbolo cuando el problema es el intervalo.
    """
    visto = _espiar(monkeypatch, _kline([["1", "1", "2", "0.5", "1.5", "10", "1"]]))
    by.velas("BTCUSDT", "1h", 1, base="https://x")
    assert "interval=60" in visto["url"]
    assert "interval=1h" not in visto["url"]


def test_un_intervalo_que_no_existe_no_llega_a_la_red(monkeypatch):
    _espiar(monkeypatch, _kline([]))
    with pytest.raises(by.BybitError):
        by.velas("BTCUSDT", "7h", 1, base="https://x")


def test_sin_velas_el_error_dice_lo_del_guion(monkeypatch):
    """BingX pide BTC-USDT y Bybit BTCUSDT: es el error que uno comete al
    cambiar de exchange, y el mensaje tiene que nombrarlo."""
    _espiar(monkeypatch, _kline([]))
    with pytest.raises(by.BybitError) as e:
        by.velas("BTC-USDT", "1h", 5, base="https://x")
    assert "guion" in str(e.value)


# ============================== 4) reduceOnly y positionIdx conviven

def test_cerrar_manda_reduceOnly_EN_LOS_DOS_MODOS(monkeypatch):
    """LA TRAMPA DE COPIAR EL MODULO DE BINANCE.

    Allá `reduceOnly` y `positionSide` son excluyentes y hay que elegir uno
    según el modo. Acá van los dos, siempre. Sin `reduceOnly`, la orden
    contraria NO CIERRA: abre el lado opuesto en silencio, que es lo que pasó
    en BingX.
    """
    for modo in ("una_via", "cobertura"):
        visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
        by.cerrar("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo=modo,
                  contrato_=_CONTRATO, base="https://x")
        cuerpo = json.loads(visto["cuerpo"])
        assert cuerpo["reduceOnly"] is True, f"sin reduceOnly en modo {modo}"
        assert "positionIdx" in cuerpo, f"sin positionIdx en modo {modo}"


def test_cerrar_manda_el_lado_CONTRARIO(monkeypatch):
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.cerrar("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
              contrato_=_CONTRATO, base="https://x")
    assert json.loads(visto["cuerpo"])["side"] == "Sell"

    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.cerrar("BTCUSDT", -1, 0.005, api_key="K", secret="S", modo="una_via",
              contrato_=_CONTRATO, base="https://x")
    assert json.loads(visto["cuerpo"])["side"] == "Buy"


def test_el_positionIdx_sale_del_modo_y_del_lado(monkeypatch):
    """0 en una vía; 1 el largo y 2 el corto en cobertura.

    El equivocado hace que la orden toque la posición del otro lado, o que el
    exchange la rechace con un mensaje que no menciona el modo por ningún lado.
    """
    casos = [("una_via", 1, 0), ("una_via", -1, 0),
             ("cobertura", 1, 1), ("cobertura", -1, 2)]
    for modo, lado, esperado in casos:
        visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
        by.abrir("BTCUSDT", lado, 0.005, api_key="K", secret="S", modo=modo,
                 contrato_=_CONTRATO, base="https://x")
        assert json.loads(visto["cuerpo"])["positionIdx"] == esperado


# ====================================== la cantidad, que es lo que se arriesga

def test_la_cantidad_viaja_como_TEXTO(monkeypatch):
    """Bybit pide `qty` como cadena. Un número lo rechaza."""
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.005, api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    assert json.loads(visto["cuerpo"])["qty"] == "0.005"
    assert '"qty":"' in visto["cuerpo"], "viajó como número, no como texto"


def test_la_cantidad_NUNCA_sale_en_notacion_cientifica(monkeypatch):
    """`str(0.00001)` en Python da "1e-05", y el exchange lo rechaza con un
    error sobre el parámetro que no menciona el formato."""
    contrato = dict(_CONTRATO, minimo=0.00001, paso=0.00001,
                    paso_texto="0.00001", decimales_cantidad=5)
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.00001, api_key="K", secret="S", modo="una_via",
             contrato_=contrato, base="https://x")
    qty = json.loads(visto["cuerpo"])["qty"]
    assert "e" not in qty.lower(), f"salió en notación científica: {qty}"
    assert qty == "0.00001"


def test_se_redondea_SIEMPRE_HACIA_ABAJO(monkeypatch):
    """Hacia arriba se arriesga MAS de lo que se pidió, y de a poco.

    Una orden rechazada por chica se ve; una que arriesga 1,3% cuando se pidió
    1% no se ve nunca.
    """
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.0059, api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    assert json.loads(visto["cuerpo"])["qty"] == "0.005"


def test_el_redondeo_no_pierde_un_tercio_de_la_orden():
    """`floor(0.3 / 0.1)` da 2 en aritmética binaria. Con Decimal da 3.

    Es un error que no levanta ninguna alarma: la orden entra, sólo que por
    dos tercios de lo que se dimensionó.
    """
    c = dict(_CONTRATO, paso=0.1, paso_texto="0.1", decimales_cantidad=1)
    assert by._redondear(0.3, c) == "0.3"


def test_por_debajo_del_minimo_NO_SE_MANDA_NADA(monkeypatch):
    """Redondear hacia arriba para alcanzar el mínimo arriesgaría más de lo
    pedido sin decirlo. Se prefiere no operar."""
    _espiar(monkeypatch, _sobre({"orderId": "1"}))
    with pytest.raises(by.BybitError) as e:
        by.abrir("BTCUSDT", 1, 0.0004, api_key="K", secret="S", modo="una_via",
                 contrato_=_CONTRATO, base="https://x")
    assert "mínimo" in str(e.value)


def test_el_minimo_por_NOCIONAL_tambien_frena_la_orden(monkeypatch):
    """EN LA MAYORIA DE LOS SIMBOLOS ES EL NOCIONAL EL QUE MANDA, NO LA CANTIDAD.

    MEDIDO el 31/8/2026: en XRPUSDT el mínimo por cantidad son 0,1 XRP —catorce
    centavos— pero Bybit exige 5 USDT de nocional. Una orden de 0,1 XRP pasa el
    control de cantidad y la rechaza el exchange igual. Lo mismo en DOGE, ADA,
    LINK, AVAX y TRX.
    """
    xrp = {"simbolo": "XRPUSDT", "minimo": 0.1, "paso": 0.1, "paso_texto": "0.1",
           "decimales_cantidad": 1, "maximo": 0.0, "minimo_nocional": 5.0,
           "tick": 0.0001, "tick_texto": "0.0001", "decimales_precio": 4}
    _espiar(monkeypatch, _sobre({"orderId": "1"}))
    with pytest.raises(by.BybitError) as e:
        by.abrir("XRPUSDT", 1, 0.1, precio=1.3699, api_key="K", secret="S",
                 modo="una_via", contrato_=xrp, base="https://x")
    assert "nocional" in str(e.value)


def test_con_nocional_suficiente_la_orden_sale(monkeypatch):
    """El control no puede frenar una orden legítima: 4 XRP son 5,48 USDT."""
    xrp = {"simbolo": "XRPUSDT", "minimo": 0.1, "paso": 0.1, "paso_texto": "0.1",
           "decimales_cantidad": 1, "maximo": 0.0, "minimo_nocional": 5.0,
           "tick": 0.0001, "tick_texto": "0.0001", "decimales_precio": 4}
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("XRPUSDT", 1, 4.0, precio=1.3699, api_key="K", secret="S",
             modo="una_via", contrato_=xrp, base="https://x")
    assert json.loads(visto["cuerpo"])["qty"] == "4.0"


def test_sin_precio_el_nocional_no_se_puede_comprobar(monkeypatch):
    """Una orden a mercado no lleva precio, así que sin él ese control no
    existe y lo hace el exchange. Se deja pasar a propósito: inventar un precio
    para poder comprobar sería peor que no comprobar."""
    xrp = {"simbolo": "XRPUSDT", "minimo": 0.1, "paso": 0.1, "paso_texto": "0.1",
           "decimales_cantidad": 1, "maximo": 0.0, "minimo_nocional": 5.0,
           "tick": 0.0001, "tick_texto": "0.0001", "decimales_precio": 4}
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("XRPUSDT", 1, 0.1, api_key="K", secret="S", modo="una_via",
             contrato_=xrp, base="https://x")
    assert json.loads(visto["cuerpo"])["qty"] == "0.1"


def test_por_encima_del_maximo_a_mercado_tampoco(monkeypatch):
    """Bybit corta las órdenes a mercado más arriba que las límite. Partirla
    en varias sin decirlo dejaría media posición abierta creyendo que entró
    entera."""
    _espiar(monkeypatch, _sobre({"orderId": "1"}))
    with pytest.raises(by.BybitError) as e:
        by.abrir("BTCUSDT", 1, 200.0, api_key="K", secret="S", modo="una_via",
                 contrato_=_CONTRATO, base="https://x")
    assert "máximo" in str(e.value)


def test_un_lado_invalido_no_manda_nada(monkeypatch):
    _espiar(monkeypatch, _sobre({"orderId": "1"}))
    with pytest.raises(by.BybitError):
        by.abrir("BTCUSDT", 0, 0.005, api_key="K", secret="S", modo="una_via",
                 contrato_=_CONTRATO, base="https://x")
    with pytest.raises(by.BybitError):
        by.cerrar("BTCUSDT", 0, 0.005, api_key="K", secret="S", modo="una_via",
                  contrato_=_CONTRATO, base="https://x")


# ============================ la proteccion viaja DENTRO de la entrada

def test_el_stop_y_el_objetivo_van_EN_LA_MISMA_ORDEN(monkeypatch):
    """LO QUE HACE QUE NO EXISTA UNA POSICION DESPROTEGIDA NI POR UN INSTANTE.

    En Binance el stop es una segunda orden que se manda después de que la
    entrada se llenó, y entre las dos hay una ventana: si el proceso se muere
    ahí, queda una posición abierta que nadie está cuidando.
    """
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.005, stop=70000, objetivo=90000,
             api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    cuerpo = json.loads(visto["cuerpo"])
    assert cuerpo["stopLoss"] == "70000.0"
    assert cuerpo["takeProfit"] == "90000.0"
    assert cuerpo["tpslMode"] == "Full", "cerraría sólo una parte de la posición"


def test_el_stop_se_mide_contra_el_precio_de_MARCA(monkeypatch):
    """Es el que Bybit usa para liquidar. Con el último precio negociado, una
    mecha en un libro fino dispara un stop que la liquidación no habría
    tocado."""
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.005, stop=70000, objetivo=90000,
             api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    cuerpo = json.loads(visto["cuerpo"])
    assert cuerpo["slTriggerBy"] == "MarkPrice"
    assert cuerpo["tpTriggerBy"] == "MarkPrice"


def test_sin_stop_no_se_manda_el_parametro_vacio(monkeypatch):
    """Un `stopLoss` en cero o NaN no es "sin stop": es un stop en cero."""
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.005, stop=float("nan"), objetivo=None,
             api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    cuerpo = json.loads(visto["cuerpo"])
    assert "stopLoss" not in cuerpo
    assert "takeProfit" not in cuerpo


def test_el_precio_del_stop_se_ajusta_al_tick(monkeypatch):
    """Un stop con más decimales que el tick se rechaza."""
    visto = _espiar(monkeypatch, _sobre({"orderId": "1"}))
    by.abrir("BTCUSDT", 1, 0.005, stop=70000.037, objetivo=None,
             api_key="K", secret="S", modo="una_via",
             contrato_=_CONTRATO, base="https://x")
    assert json.loads(visto["cuerpo"])["stopLoss"] == "70000.0"


def test_proteger_sin_stop_ni_objetivo_no_manda_nada(monkeypatch):
    _espiar(monkeypatch, _sobre({}))
    with pytest.raises(by.BybitError):
        by.proteger("BTCUSDT", 1, stop=None, objetivo=float("nan"),
                    api_key="K", secret="S", modo="una_via",
                    contrato_=_CONTRATO, base="https://x")


# ====================================================== lecturas de la cuenta

def test_el_saldo_no_revienta_con_el_retirable_VACIO(monkeypatch):
    """MEDIDO en una cuenta real: `availableToWithdraw` vuelve cadena vacía, no
    cero. Pasarla por `float` levanta ValueError en mitad de una vuelta del
    bot, y el runner corta por "no se pudo leer el saldo"."""
    _espiar(monkeypatch, _sobre({"list": [{"coin": [
        {"coin": "USDT", "equity": "0.00000441", "walletBalance": "0.00000441",
         "availableToWithdraw": ""}]}]}))
    assert by.saldo("K", "S", base="https://x") == pytest.approx(0.00000441)


def test_el_saldo_de_una_moneda_que_no_esta_es_cero(monkeypatch):
    _espiar(monkeypatch, _sobre({"list": [{"coin": [
        {"coin": "BTC", "equity": "1"}]}]}))
    assert by.saldo("K", "S", moneda="USDT", base="https://x") == 0.0


def test_la_posicion_se_lee_con_signo(monkeypatch):
    _espiar(monkeypatch, _sobre({"list": [
        {"symbol": "BTCUSDT", "side": "Sell", "size": "0.02", "avgPrice": "78000"}]}))
    p = by.posicion("BTCUSDT", "K", "S", base="https://x")
    assert p["lado"] == -1 and p["cantidad"] == 0.02


def test_una_posicion_en_cero_es_estar_plano(monkeypatch):
    """MEDIDO: sin posición abierta Bybit devuelve igual una fila, con size 0.
    Leerla como posición abierta haría que el bot no entre nunca."""
    _espiar(monkeypatch, _sobre({"list": [
        {"symbol": "BTCUSDT", "side": "", "size": "0", "positionIdx": 0}]}))
    assert by.posicion("BTCUSDT", "K", "S", base="https://x")["lado"] == 0


def test_el_modo_se_lee_del_positionIdx(monkeypatch):
    """Bybit tiene endpoint para CAMBIAR el modo pero ninguno para
    consultarlo. El `positionIdx` de la posición lo dice, y viene aunque no
    haya nada abierto."""
    _espiar(monkeypatch, _sobre({"list": [
        {"symbol": "BTCUSDT", "size": "0", "positionIdx": 0}]}))
    assert by.modo_posicion("K", "S", base="https://x") == "una_via"

    _espiar(monkeypatch, _sobre({"list": [
        {"symbol": "BTCUSDT", "size": "0", "positionIdx": 1},
        {"symbol": "BTCUSDT", "size": "0", "positionIdx": 2}]}))
    assert by.modo_posicion("K", "S", base="https://x") == "cobertura"


def test_los_permisos_dicen_si_la_clave_PUEDE_OPERAR(monkeypatch):
    """Una clave de sólo lectura pasa todas las comprobaciones —lee saldo, lee
    posiciones— y recién falla al mandar la primera orden, que es el peor
    momento para enterarse."""
    _espiar(monkeypatch, _sobre({"readOnly": 1, "note": "botiquant 1",
                                 "expiredAt": "2026-12-01T15:48:09Z",
                                 "ips": ["*"], "permissions": {}}))
    p = by.permisos("K", "S", base="https://x")
    assert p["solo_lectura"] is True and p["puede_operar"] is False
    assert p["vence"] == "2026-12-01T15:48:09Z"


# ================================================ a cuanto entro la orden

def test_el_precio_de_ejecucion_SE_PREGUNTA_APARTE(monkeypatch):
    """Bybit no lo dice al responder: `/v5/order/create` devuelve `orderId` y
    nada más. Sin esto el registro dice que operó pero no a cuánto, que es el
    dato que sirve para comparar contra lo que esperaba la estrategia."""
    _espiar(monkeypatch, _sobre({"list": [
        {"orderId": "abc", "orderStatus": "Filled", "cumExecQty": "0.005",
         "avgPrice": "78000.5", "cumExecFee": "0.21"}]}))
    d = by.detalle_orden("BTCUSDT", "abc", api_key="K", secret="S",
                         base="https://x")
    assert d["precio"] == 78000.5 and d["cantidad"] == 0.005


def test_una_orden_que_no_aparece_es_un_error(monkeypatch):
    """Devolver ceros haría que el registro anote una entrada a precio cero."""
    _espiar(monkeypatch, _sobre({"list": []}))
    with pytest.raises(by.BybitError):
        by.detalle_orden("BTCUSDT", "abc", api_key="K", secret="S",
                         base="https://x")


# ============================================================ el contrato

def test_el_contrato_saca_los_filtros_del_lugar_correcto(monkeypatch):
    """MEDIDO en BTCUSDT el 31/8/2026."""
    _espiar(monkeypatch, _sobre({"list": [{
        "symbol": "BTCUSDT",
        "lotSizeFilter": {"minOrderQty": "0.001", "qtyStep": "0.001",
                          "maxOrderQty": "1500.000", "maxMktOrderQty": "150.000",
                          "minNotionalValue": "5"},
        "priceFilter": {"tickSize": "0.10"}}]}))
    c = by.contrato("BTCUSDT", base="https://x")
    assert c["minimo"] == 0.001 and c["decimales_cantidad"] == 3
    assert c["minimo_nocional"] == 5.0
    assert c["decimales_precio"] == 1
    # El tope de una orden A MERCADO, no el de una límite: todas las de este
    # módulo son a mercado.
    assert c["maximo"] == 150.0


def test_un_simbolo_que_no_existe_es_un_error(monkeypatch):
    _espiar(monkeypatch, _sobre({"list": []}))
    with pytest.raises(by.BybitError):
        by.contrato("NOEXISTEUSDT", base="https://x")


def test_cuenta_minima_manda_el_mayor_de_los_dos_minimos():
    """MEDIDO: con BTC a 78.000 el mínimo por cantidad son 78 USDT y el
    nocional 5, así que manda el primero. Con stop 2% y riesgo 1% hacen falta
    156 USDT — y en un portafolio eso es POR ESTRATEGIA."""
    hacen_falta = by.cuenta_minima(78_000, _CONTRATO, stop_pct=2.0, riesgo_pct=1.0)
    assert hacen_falta == pytest.approx(156.0)


def test_los_decimales_se_cuentan_sobre_el_texto():
    assert by._decimales("0.001") == 3
    assert by._decimales("1") == 0
    assert by._decimales("0.10") == 1
    assert by._decimales("100") == 0
