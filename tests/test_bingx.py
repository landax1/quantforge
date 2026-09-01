"""El cliente del exchange donde se va a operar.

Todo lo de acá corre SIN RED: las respuestas se simulan. Es a propósito. Un
test que le pega a la API de verdad falla los días que BingX se cae, tarda
segundos en vez de milisegundos, y —lo peor— pasa en verde el día que rompen
el formato, porque quien lo escribió ya no está mirando.

Lo que sí se comprobó contra la API real, el 26 de agosto de 2026, y por eso
está codificado acá abajo como expectativa fija:

  * el techo son 1.000 velas, no las 1.440 documentadas
  * las velas llegan como objetos y de la MÁS NUEVA a la más vieja
  * un error viene con código HTTP 200 y `code` distinto de cero adentro
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from botiquant.data import bingx


# ------------------------------------------------------------------ el molde

def _respuesta(data: Any, code: int = 0, msg: str = "") -> str:
    return json.dumps({"code": code, "msg": msg, "data": data})


def _vela(t: int, close: float) -> dict[str, Any]:
    return {"time": t, "open": close, "high": close + 1,
            "low": close - 1, "close": close, "volume": 10.0}


@pytest.fixture
def falso(monkeypatch):
    """Reemplaza la red y deja ver con qué parámetros se la llamó."""
    llamadas: list[dict[str, Any]] = []
    cuerpo = {"valor": _respuesta([])}

    class _Resp:
        def __init__(self, texto): self.texto = texto
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.texto.encode()

    def _urlopen(req, timeout=None):
        llamadas.append({"url": req.full_url, "headers": dict(req.headers),
                         "cuerpo": req.data or b"", "metodo": req.get_method()})
        return _Resp(cuerpo["valor"])

    monkeypatch.setattr(bingx.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(bingx.json, "load", lambda r: json.loads(r.read()))
    return llamadas, cuerpo


# ------------------------------------------------------------------ las velas

def test_las_velas_se_ordenan_de_vieja_a_nueva(falso):
    """El error más peligroso de todos: no falla, miente.

    BingX manda de la más nueva a la más vieja. Usadas así, cada indicador se
    calcula sobre el pasado invertido — una EMA de 20 mira el futuro. No tira
    ningún error: devuelve números plausibles y equivocados.
    """
    _, cuerpo = falso
    cuerpo["valor"] = _respuesta([
        _vela(3_000_000, 300.0), _vela(2_000_000, 200.0), _vela(1_000_000, 100.0)])
    df = bingx.velas("BTC-USDT", "1h", 3)
    assert list(df.index) == sorted(df.index)
    assert df["close"].tolist() == [100.0, 200.0, 300.0]


def test_el_limite_se_acota_a_lo_que_la_api_aguanta(falso):
    """Pedir de más devuelve VACÍO, no un error.

    Medido: 1.440 devuelve 1.000 sin avisar y 2.000 devuelve una lista vacía.
    Un vacío silencioso se confunde con "ese instrumento no existe", así que
    el techo se aplica de este lado y nunca se llega a pedirlo.
    """
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta([_vela(1_000_000, 100.0)])
    bingx.velas("BTC-USDT", "1h", 5000)
    assert "limit=1000" in llamadas[-1]["url"]


def test_un_intervalo_que_no_existe_se_rechaza_antes_de_salir(falso):
    llamadas, _ = falso
    with pytest.raises(bingx.BingXError, match="Intervalo"):
        bingx.velas("BTC-USDT", "7h")
    assert not llamadas, "no tendría que haber salido a la red"


def test_sin_velas_el_mensaje_dice_que_revisar(falso):
    """El error más común es el guion: BTCUSDT en Binance, BTC-USDT en BingX."""
    _, cuerpo = falso
    cuerpo["valor"] = _respuesta([])
    with pytest.raises(bingx.BingXError, match="guion"):
        bingx.velas("BTCUSDT", "1h", 10)


def test_el_rango_de_fechas_viaja_cuando_se_pide(falso):
    """No está documentado en v3 pero funciona; se comprobó contra la API."""
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta([_vela(1_750_000_000_000, 100.0)])
    bingx.velas("BTC-USDT", "1h", 10, desde=1_750_000_000_000,
                hasta=1_750_100_000_000)
    assert "startTime=1750000000000" in llamadas[-1]["url"]
    assert "endTime=1750100000000" in llamadas[-1]["url"]


# ------------------------------------------------------------------ el error

def test_un_error_con_200_no_pasa_por_exito(falso):
    """BingX contesta 200 y pone el error adentro del cuerpo.

    Un cliente que sólo mire el código HTTP toma un rechazo por un resultado
    vacío y el runner sigue operando como si nada hubiera pasado.
    """
    _, cuerpo = falso
    cuerpo["valor"] = _respuesta(None, code=100413, msg="API Key is incorrect")
    with pytest.raises(bingx.BingXError, match="100413"):
        bingx.velas("BTC-USDT", "1h", 10)


# ------------------------------------------------------------------ la firma

def test_sin_credenciales_no_se_firma_ni_viaja_la_clave(falso):
    """Los datos de mercado son públicos: no hay motivo para mandar la clave."""
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta([_vela(1_000_000, 100.0)])
    bingx.velas("BTC-USDT", "1h", 10)
    assert "signature=" not in llamadas[-1]["url"]
    assert not any(k.lower() == "x-bx-apikey" for k in llamadas[-1]["headers"])


def test_el_secreto_nunca_viaja_en_el_pedido(falso):
    """La prueba que importa de toda la autenticación.

    La clave pública va en un header porque el exchange la necesita para saber
    quién sos. El SECRETO no: sólo firma. Si alguna vez aparece en la URL, se
    filtra en cada registro de servidor y de proxy del camino.
    """
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta({"balance": {"asset": "USDT", "balance": "100"}})
    bingx.saldo("CLAVE_PUBLICA", "SECRETO_QUE_NO_PUEDE_SALIR")
    url = llamadas[-1]["url"]
    assert "SECRETO_QUE_NO_PUEDE_SALIR" not in url
    assert "signature=" in url


def test_la_firma_cubre_el_timestamp(falso):
    """Firmar sin el timestamp adentro deja el pedido reutilizable por otro.

    Si el timestamp se agregara DESPUÉS de firmar, cualquiera que intercepte
    el pedido puede cambiarle la hora y repetirlo.
    """
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta({"balance": {"asset": "USDT", "balance": "1"}})
    bingx.saldo("clave", "secreto")
    url = llamadas[-1]["url"]
    query = url.split("?", 1)[1]
    firmado, _, firma = query.rpartition("&signature=")
    assert "timestamp=" in firmado

    import hashlib
    import hmac
    esperada = hmac.new(b"secreto", firmado.encode(), hashlib.sha256).hexdigest()
    assert firma == esperada


# ------------------------------------------------------------------ la cuenta

def test_el_saldo_se_normaliza(falso):
    _, cuerpo = falso
    cuerpo["valor"] = _respuesta({"balance": {
        "asset": "USDT", "balance": "1250.5",
        "availableMargin": "1200.0", "unrealizedProfit": "-12.3"}})
    s = bingx.saldo("clave", "secreto")
    assert s == {"moneda": "USDT", "saldo": 1250.5,
                 "disponible": 1200.0, "no_realizado": -12.3}


def test_las_posiciones_se_normalizan(falso):
    """El runner pregunta al exchange qué hay abierto, no a su propia memoria.

    Si se cortó la luz a mitad de una operación, la verdad está de este lado.
    """
    _, cuerpo = falso
    cuerpo["valor"] = _respuesta([{
        "symbol": "BTC-USDT", "positionSide": "LONG", "positionAmt": "0.0025",
        "avgPrice": "78000.0", "unrealizedProfit": "3.5"}])
    p = bingx.posiciones("clave", "secreto", "BTC-USDT")
    assert p == [{"simbolo": "BTC-USDT", "lado": "long", "cantidad": 0.0025,
                  "precio_entrada": 78000.0, "no_realizado": 3.5}]


def test_sin_posiciones_devuelve_lista_vacia_y_no_revienta(falso):
    _, cuerpo = falso
    cuerpo["valor"] = _respuesta([])
    assert bingx.posiciones("clave", "secreto") == []


# ------------------------------------------------------------------ el contrato

def test_el_contrato_se_busca_sin_importar_mayusculas(falso):
    _, cuerpo = falso
    cuerpo["valor"] = _respuesta([
        {"symbol": "ETH-USDT", "quantityPrecision": 2},
        {"symbol": "BTC-USDT", "quantityPrecision": 4, "tradeMinQuantity": 0.0001}])
    assert bingx.contrato("btc-usdt")["quantityPrecision"] == 4


def test_un_contrato_que_no_existe_lo_dice(falso):
    _, cuerpo = falso
    cuerpo["valor"] = _respuesta([{"symbol": "ETH-USDT"}])
    with pytest.raises(bingx.BingXError, match="no lista"):
        bingx.contrato("DOGE-USDT")


# ------------------------------------------------- la firma, contrastada con BingX
#
# Las tres cosas de esta sección estaban MAL y ninguna avisaba: el exchange
# contesta "clave incorrecta" (100413), que manda a revisar la clave y no la
# firma. Salieron de contrastar el cliente contra la referencia oficial.

def test_los_parametros_se_ordenan_alfabeticamente_antes_de_firmar(falso):
    """Firmar en el orden en que uno los escribió no coincide nunca.

    El servidor arma la cadena a firmar ordenada; una firma válida sobre un
    texto distinto es una firma inválida. Se descubre recién con una clave de
    verdad, y el mensaje culpa a la clave.
    """
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta({"balance": {"asset": "USDT", "balance": "1"}})
    bingx._pedir("/x", {"zeta": 1, "alfa": 2, "medio": 3},
                 api_key="k", secret="s")
    query = llamadas[-1]["url"].split("?", 1)[1]
    firmado = query.rpartition("&signature=")[0]
    claves = [t.split("=")[0] for t in firmado.split("&")]
    assert claves == sorted(claves), f"sin ordenar: {claves}"


def test_un_post_manda_los_parametros_en_el_cuerpo(falso):
    """En la URL, el servidor no los ve.

    Una orden mandada por query string a un endpoint POST llega sin symbol,
    sin side y sin quantity. El exchange contesta que faltan parámetros y
    nadie sospecha del método.
    """
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta({"orderId": 1})
    bingx._pedir("/openApi/swap/v2/trade/order",
                 {"symbol": "BTC-USDT", "quantity": 0.01},
                 api_key="k", secret="s", metodo="POST")
    ultima = llamadas[-1]
    assert "?" not in ultima["url"], "un POST no lleva la query en la URL"
    assert b"symbol=BTC-USDT" in ultima["cuerpo"]
    assert b"signature=" in ultima["cuerpo"]
    assert ultima["headers"].get("Content-type") == \
        "application/x-www-form-urlencoded"


def test_un_diccionario_viaja_como_json_y_no_como_repr_de_python(falso):
    """`str({"a": 1})` da `{'a': 1}` con comillas simples, que no es JSON.

    Es la forma más fácil de romper el `stopLoss` sin darse cuenta: el
    parámetro viaja, la firma cierra, y el exchange rechaza el objeto.
    """
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta({"orderId": 1})
    bingx._pedir("/x", {"stopLoss": {"type": "STOP_MARKET", "stopPrice": 76000.0}},
                 api_key="k", secret="s", metodo="POST")
    enviado = llamadas[-1]["cuerpo"].decode()
    assert '{"type":"STOP_MARKET","stopPrice":76000.0}' in enviado
    assert "'" not in enviado, "comillas simples: eso es repr de Python, no JSON"


def test_el_precio_del_stop_viaja_como_numero_y_no_como_texto(falso):
    """BingX valida el tipo: `{"stopPrice":"76000"}` lo rechaza."""
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta({"orderId": 1})
    bingx._pedir("/x", {"stopLoss": {"type": "STOP_MARKET", "stopPrice": 76000.0}},
                 api_key="k", secret="s", metodo="POST")
    assert '"stopPrice":76000.0' in llamadas[-1]["cuerpo"].decode()


@pytest.mark.parametrize("malo", ["a&b", "a=b", "a?b", "a#b", "a\nb"])
def test_un_caracter_que_romperia_la_firma_se_rechaza_antes_de_salir(falso, malo):
    """Un `&` en un valor parte la query en dos y la firma deja de cerrar."""
    llamadas, _ = falso
    with pytest.raises(bingx.BingXError, match="firma"):
        bingx._pedir("/x", {"clientOrderId": malo}, api_key="k", secret="s")
    assert not llamadas, "no tendría que haber salido a la red"


def test_la_firma_se_calcula_sobre_exactamente_lo_que_se_manda(falso):
    """La comprobación de fondo: se rehace la firma y tiene que coincidir."""
    import hashlib
    import hmac
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta({"orderId": 1})
    bingx._pedir("/x", {"symbol": "BTC-USDT", "quantity": 0.01},
                 api_key="k", secret="elsecreto", metodo="POST")
    enviado = llamadas[-1]["cuerpo"].decode()
    firmado, _, firma = enviado.rpartition("&signature=")
    esperada = hmac.new(b"elsecreto", firmado.encode(), hashlib.sha256).hexdigest()
    assert firma == esperada


# --------------------------------------------- el modo de posicion de la cuenta

def _adaptador(falso, cobertura: bool):
    from botiquant.vivo.adaptador import BingX
    llamadas, cuerpo = falso
    a = BingX("k", "s")
    a._cobertura = cobertura
    a._contratos["BTC-USDT"] = {"decimales_cantidad": 4,
                                "minimo": 0.0001}
    cuerpo["valor"] = _respuesta({"orderId": 1})
    return a, llamadas


def test_en_modo_cobertura_la_orden_lleva_LONG_o_SHORT(falso):
    a, llamadas = _adaptador(falso, cobertura=True)
    a.abrir("BTC-USDT", 1, 0.01, 76_000.0, 82_000.0)
    enviado = llamadas[-1]["cuerpo"].decode()
    assert "positionSide=LONG" in enviado
    a.abrir("BTC-USDT", -1, 0.01, 82_000.0, 76_000.0)
    assert "positionSide=SHORT" in llamadas[-1]["cuerpo"].decode()


def test_en_modo_simple_la_orden_lleva_BOTH(falso):
    """Mandar LONG en una cuenta one-way hace que el exchange rechace la orden.

    Y el mensaje no menciona el modo de posición por ningún lado, así que se
    busca el problema en la clave, en el símbolo o en la cantidad.
    """
    a, llamadas = _adaptador(falso, cobertura=False)
    a.abrir("BTC-USDT", 1, 0.01, 76_000.0, 82_000.0)
    assert "positionSide=BOTH" in llamadas[-1]["cuerpo"].decode()


def test_al_cerrar_en_modo_simple_va_reduceOnly(falso):
    """Sin `reduceOnly`, la orden contraria ABRE del otro lado en vez de cerrar.

    Es el peor resultado posible de un cierre: el bot cree que salió y en
    realidad tiene el doble de exposición, del lado equivocado.
    """
    from botiquant.vivo.adaptador import Posicion
    a, llamadas = _adaptador(falso, cobertura=False)
    a.cerrar("BTC-USDT", Posicion(1, 0.01, 78_000.0))
    enviado = llamadas[-1]["cuerpo"].decode()
    assert "reduceOnly=true" in enviado
    assert "side=SELL" in enviado


def test_al_cerrar_en_cobertura_NO_va_reduceOnly(falso):
    """En cobertura BingX rechaza el parámetro: ahí el positionSide ya dice
    cuál posición se está tocando."""
    from botiquant.vivo.adaptador import Posicion
    a, llamadas = _adaptador(falso, cobertura=True)
    a.cerrar("BTC-USDT", Posicion(1, 0.01, 78_000.0))
    assert "reduceOnly" not in llamadas[-1]["cuerpo"].decode()


def test_el_modo_se_pregunta_una_sola_vez(falso):
    """Es una preferencia de la cuenta que no cambia sola.

    Preguntarla en cada orden agrega una llamada a la red justo en el momento
    en que menos conviene demorarse.
    """
    from botiquant.vivo.adaptador import BingX
    llamadas, cuerpo = falso
    cuerpo["valor"] = _respuesta({"dualSidePosition": "true"})
    a = BingX("k", "s")
    assert a.cobertura() is True
    antes = len(llamadas)
    assert a.cobertura() is True
    assert len(llamadas) == antes, "preguntó dos veces"
