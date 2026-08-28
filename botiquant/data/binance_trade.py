"""Operar futuros perpetuos USDⓈ-M en Binance, desde la aplicación.

POR QUE POR API Y NO POR WEBHOOK. Binance tiene webhook nativo de TradingView
—"Signal Trading"— y ese camino no necesita que nada esté prendido, porque el
que evalúa la estrategia es TradingView. Pero exige una cuenta TradingView Pro,
que es paga, y eso deja afuera a la mayoría.

Y hay algo que el webhook no puede hacer: un PORTAFOLIO. Con alertas, cada
estrategia va sola y nadie mira el conjunto — nadie reparte el capital ni frena
la cuenta entera si cae. Eso es justamente lo que la aplicación hace para
MetaTrader, y es el motivo de que acá se opere por API.

LO QUE ESTO SI CUESTA, y hay que decirlo: algo tiene que estar despierto cuando
cierra la vela. La aplicación ya funciona así y lo dice en pantalla —"opera
mientras esta aplicación esté abierta"—. Un VPS es sólo una computadora que no
se apaga.

===========================================================================
LO QUE NO SE PARECE A BINGX, Y POR QUE NO SE PUEDE COPIAR AQUEL CODIGO
===========================================================================

En BingX hubo tres errores de firma y ninguno avisaba: el exchange contestaba
"clave incorrecta", que manda a revisar la clave. Acá las reglas son OTRAS, así
que copiar aquello habría producido exactamente el mismo tipo de error:

  · BingX exige ORDENAR los parámetros antes de firmar. Binance dice
    explícitamente que "pueden mandarse en cualquier orden", pero la firma se
    calcula sobre el texto TAL COMO SE MANDA. O sea que no hay que ordenar:
    hay que firmar exactamente la misma cadena que viaja.
  · Lo que se firma es `totalParams` = query string CONCATENADA con el cuerpo.
  · La firma va AL FINAL, y la cabecera se llama `X-MBX-APIKEY`.

===========================================================================
EL MODO DE POSICION SE PREGUNTA, NO SE SUPONE
===========================================================================

Binance tiene dos modos y cada uno quiere un parámetro DISTINTO para cerrar:

    una vía (one-way)   -> `reduceOnly=true`, y NO `positionSide`
    cobertura (hedge)   -> `positionSide`, y NO `reduceOnly`  (da -1106)

Mandar el par equivocado devuelve -4061 o -1106. En BingX el mismo descuido era
peor —sin `reduceOnly`, la orden de cierre ABRIA el lado contrario en silencio—
así que acá al menos falla ruidoso. Igual se pregunta el modo una vez y se arma
la orden según eso, en vez de asumir uno.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

#: Producción y pruebas. El testnet es una cuenta con dinero falso y su propia
#: clave: se puede recorrer el camino entero sin tocar una cuenta real.
#:
#: OJO: LOS MINIMOS NO SON LOS MISMOS EN LOS DOS. Medido el 28/8/2026 en
#: BTCUSDT: el testnet acepta 0,0001 con cuatro decimales y la cuenta real pide
#: 0,001 con tres. O sea que una cantidad que entra en pruebas puede rechazarse
#: en real. Por eso `contrato()` se pregunta contra la MISMA base con la que se
#: va a operar, y no se cachea entre entornos.
BASE_REAL = "https://fapi.binance.com"
BASE_PRUEBA = "https://demo-fapi.binance.com"

#: Cuánto puede tardar el pedido en llegar antes de que Binance lo descarte.
#: El valor por defecto de Binance son 5 segundos; con una conexión lenta o el
#: reloj de la máquina un poco corrido, eso rechaza órdenes válidas.
RECV_WINDOW = 10_000


class BinanceError(RuntimeError):
    """Binance rechazó algo, y el mensaje es el suyo.

    Se conserva el código: -2015 es clave o permisos, -4061 es el modo de
    posición, -1106 es un parámetro de más. Cada uno manda a mirar otra cosa, y
    un mensaje genérico manda a revisar la clave siempre.
    """

    def __init__(self, mensaje: str, codigo: int | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.del_exchange = mensaje


def _valor(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _pedir(ruta: str, params: dict[str, Any] | None = None, *,
           api_key: str = "", secret: str = "", metodo: str = "GET",
           base: str = BASE_PRUEBA, timeout: float = 30.0) -> Any:
    """Un pedido a Binance, firmado si le dan credenciales.

    SE FIRMA EXACTAMENTE LA CADENA QUE VIAJA. No se ordena y no se firma una
    versión distinta de la que se manda: la firma es sobre `totalParams`, que
    es la query concatenada con el cuerpo. Cualquier diferencia entre lo
    firmado y lo enviado da "signature for this request is not valid", que
    manda a revisar la clave cuando el problema es el texto.

    El secreto NO viaja: se usa para firmar y no sale de esta función.
    """
    p = dict(params or {})
    headers = {"User-Agent": "botiquant"}

    if api_key and secret:
        p.setdefault("timestamp", int(time.time() * 1000))
        p.setdefault("recvWindow", RECV_WINDOW)

    # urlencode y no armado a mano: un símbolo o un decimal con caracteres
    # especiales rompería la cadena, y acá lo firmado tiene que ser idéntico a
    # lo enviado.
    query = urllib.parse.urlencode({k: _valor(v) for k, v in p.items()})

    if api_key and secret:
        firma = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        query = f"{query}&signature={firma}" if query else f"signature={firma}"
        headers["X-MBX-APIKEY"] = api_key

    cuerpo = None
    if metodo in ("POST", "DELETE", "PUT"):
        # Los parámetros van en el cuerpo; la firma ya está adentro de `query`,
        # que es lo mismo que se firmó.
        cuerpo = query.encode()
        url = f"{base}{ruta}"
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        url = f"{base}{ruta}?{query}" if query else f"{base}{ruta}"

    req = urllib.request.Request(url, data=cuerpo, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        crudo = e.read()[:400].decode(errors="replace")
        try:
            d = json.loads(crudo)
            raise BinanceError(
                f"[{d.get('code')}] {d.get('msg') or crudo}",
                codigo=d.get("code")) from e
        except (ValueError, AttributeError):
            raise BinanceError(f"Binance devolvió {e.code}: {crudo}") from e
    except OSError as e:
        raise BinanceError(f"No se pudo conectar con Binance: {e}") from e


# --------------------------------------------------------------- sin clave

def ping(base: str = BASE_PRUEBA) -> bool:
    """¿Contesta? Sin clave: sirve para separar "no hay red" de "clave mala"."""
    _pedir("/fapi/v1/ping", base=base)
    return True


def cuenta_minima(precio: float, contrato_: dict[str, Any], *,
                  stop_pct: float, riesgo_pct: float) -> float:
    """Cuánta cuenta hace falta para que la orden más chica sea posible.

    ES LA PREGUNTA QUE DECIDE SI EL BOT VA A OPERAR O NO, y no se puede
    contestar sin los mínimos del exchange. Con una cuenta por debajo de esto,
    el tamaño que sale del riesgo pedido queda debajo del mínimo y la orden se
    rechaza — o, peor, se redondea hacia arriba y se arriesga más de lo pedido.

    MEDIDO en Binance con BTCUSDT a 77.499: el mínimo por cantidad son 0,001
    BTC = 77 USDT, y el mínimo por nocional 50 USDT. Manda el mayor de los dos,
    o sea 77. Con stop del 2% y riesgo del 1%, hace falta una cuenta de 155
    USDT — y en un portafolio eso es POR ESTRATEGIA, porque cada una maneja su
    porción.
    """
    if precio <= 0 or stop_pct <= 0 or riesgo_pct <= 0:
        return 0.0
    minimo_en_plata = max(contrato_.get("minimo", 0.0) * precio,
                          contrato_.get("minimo_nocional", 0.0))
    riesgo_de_esa_orden = minimo_en_plata * stop_pct / 100.0
    return riesgo_de_esa_orden / (riesgo_pct / 100.0)


def contrato(simbolo: str, base: str = BASE_PRUEBA) -> dict[str, Any]:
    """Mínimo, paso y decimales de ese símbolo.

    HACE FALTA ANTES DE MANDAR NADA. Una cantidad con más decimales de los que
    el símbolo acepta se rechaza; una por debajo del mínimo también. Preguntarlo
    es la diferencia entre redondear bien y que la orden no entre.
    """
    d = _pedir("/fapi/v1/exchangeInfo", base=base)
    for s in d.get("symbols", []):
        if s.get("symbol") == simbolo:
            f = {x["filterType"]: x for x in s.get("filters", [])}
            lote = f.get("LOT_SIZE", {})
            mercado = f.get("MARKET_LOT_SIZE", lote)
            return {
                "simbolo": simbolo,
                "minimo": float(mercado.get("minQty") or lote.get("minQty") or 0),
                "paso": float(mercado.get("stepSize") or lote.get("stepSize") or 0),
                "decimales_cantidad": int(s.get("quantityPrecision") or 0),
                "decimales_precio": int(s.get("pricePrecision") or 0),
                "minimo_nocional": float(f.get("MIN_NOTIONAL", {}).get("notional") or 0),
            }
    raise BinanceError(f"{simbolo} no existe en los futuros de Binance.")


# --------------------------------------------------------------- con clave

def modo_posicion(api_key: str, secret: str,
                  base: str = BASE_PRUEBA) -> str:
    """"una_via" o "cobertura". Determina CON QUE se cierra una posición.

    Se pregunta en vez de asumirse: cada modo quiere un parámetro distinto y el
    equivocado da -4061 o -1106. Ver el encabezado del módulo.
    """
    d = _pedir("/fapi/v1/positionSide/dual", api_key=api_key, secret=secret,
               base=base)
    return "cobertura" if d.get("dualSidePosition") else "una_via"


def saldo(api_key: str, secret: str, moneda: str = "USDT",
          base: str = BASE_PRUEBA) -> float:
    """El disponible de la cuenta de futuros, en esa moneda."""
    d = _pedir("/fapi/v2/balance", api_key=api_key, secret=secret, base=base)
    for a in d:
        if a.get("asset") == moneda:
            return float(a.get("availableBalance") or 0.0)
    return 0.0


def posicion(simbolo: str, api_key: str, secret: str,
             base: str = BASE_PRUEBA) -> dict[str, Any]:
    """Lo que hay abierto en ese símbolo. Se PREGUNTA, no se recuerda.

    Recordarla en memoria significa que un reinicio de la aplicación, o una
    orden puesta a mano desde el exchange, dejan al bot operando contra una
    posición que cree que no existe.
    """
    d = _pedir("/fapi/v2/positionRisk", {"symbol": simbolo},
               api_key=api_key, secret=secret, base=base)
    total = 0.0
    entrada = float("nan")
    for p in d:
        if p.get("symbol") != simbolo:
            continue
        cant = float(p.get("positionAmt") or 0.0)
        if cant:
            total += cant
            entrada = float(p.get("entryPrice") or 0.0)
    lado = 1 if total > 0 else (-1 if total < 0 else 0)
    return {"lado": lado, "cantidad": abs(total), "precio_entrada": entrada}


# ------------------------------------------------------------ mandar órdenes

def _redondear(cantidad: float, contrato_: dict[str, Any]) -> float:
    """La cantidad al paso que el símbolo acepta, SIEMPRE HACIA ABAJO.

    Hacia abajo y no al más cercano: redondear hacia arriba arriesga MAS de lo
    que se pidió, y de a poco. Una orden rechazada por chica se ve; una que
    arriesga 1,3% cuando se pidió 1% no se ve nunca.
    """
    paso = float(contrato_.get("paso") or 0.0)
    if paso <= 0:
        return abs(cantidad)
    import math
    n = math.floor(abs(cantidad) / paso + 1e-9) * paso
    return round(n, int(contrato_.get("decimales_cantidad") or 8))


def abrir(simbolo: str, lado: int, cantidad: float, *,
          api_key: str, secret: str, modo: str,
          contrato_: dict[str, Any] | None = None,
          base: str = BASE_PRUEBA) -> dict[str, Any]:
    """Abre a mercado. `lado` es +1 largo, -1 corto.

    EL MODO DECIDE QUE PARAMETRO VA, y por eso es obligatorio en vez de tener
    un valor por omisión: en `cobertura` hay que decir a qué lado va la
    posición, y en `una_via` mandar ese mismo parámetro da -4061. Un valor por
    omisión sería elegir al azar entre andar y fallar.
    """
    if lado not in (1, -1):
        raise BinanceError("El lado tiene que ser +1 (largo) o -1 (corto).")
    c = contrato_ or contrato(simbolo, base)
    qty = _redondear(cantidad, c)
    minimo = float(c.get("minimo") or 0.0)
    if qty < minimo or qty <= 0:
        raise BinanceError(
            f"La cantidad que sale del riesgo pedido ({cantidad:g}) queda por "
            f"debajo del mínimo de {simbolo} ({minimo:g}). Con esta cuenta el "
            f"bot no puede abrir sin arriesgar más de lo pedido.")

    p: dict[str, Any] = {"symbol": simbolo, "type": "MARKET", "quantity": qty,
                         "side": "BUY" if lado > 0 else "SELL"}
    if modo == "cobertura":
        p["positionSide"] = "LONG" if lado > 0 else "SHORT"
    return _pedir("/fapi/v1/order", p, api_key=api_key, secret=secret,
                  metodo="POST", base=base)


def cerrar(simbolo: str, lado_abierto: int, cantidad: float, *,
           api_key: str, secret: str, modo: str,
           contrato_: dict[str, Any] | None = None,
           base: str = BASE_PRUEBA) -> dict[str, Any]:
    """Cierra lo que haya abierto, mandando la orden contraria.

    ACA ESTA EL ERROR QUE EN BINGX COSTO CARO: sin marcar la orden como de
    cierre, la contraria no cierra sino que ABRE el lado opuesto. En Binance se
    marca distinto según el modo:

        una_via    -> `reduceOnly=true`, y NO `positionSide`
        cobertura  -> `positionSide` del lado que se cierra, y NO `reduceOnly`
                      (mandarlo da -1106)

    Los dos son excluyentes, así que no se pueden mandar "los dos por las
    dudas": hay que saber en cuál está la cuenta.
    """
    if lado_abierto not in (1, -1):
        raise BinanceError("No hay posición abierta que cerrar.")
    c = contrato_ or contrato(simbolo, base)
    qty = _redondear(cantidad, c)
    if qty <= 0:
        raise BinanceError("La cantidad a cerrar quedó en cero al redondear.")

    p: dict[str, Any] = {"symbol": simbolo, "type": "MARKET", "quantity": qty,
                         # la contraria a la que abrió
                         "side": "SELL" if lado_abierto > 0 else "BUY"}
    if modo == "cobertura":
        p["positionSide"] = "LONG" if lado_abierto > 0 else "SHORT"
    else:
        p["reduceOnly"] = True
    return _pedir("/fapi/v1/order", p, api_key=api_key, secret=secret,
                  metodo="POST", base=base)
