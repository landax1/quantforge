"""Operar futuros perpetuos USDT —"linear"— en Bybit, desde la aplicación.

POR QUE BYBIT. Es uno de los dos exchanges con webhook nativo de TradingView,
así que el mismo usuario puede elegir los dos caminos sin cambiar de casa: la
alerta de TradingView si prefiere no dejar nada prendido, o esta API si quiere
el PORTAFOLIO —repartir el capital entre estrategias y frenar la cuenta entera
si cae—, que con alertas sueltas no se puede hacer porque nadie mira el
conjunto.

===========================================================================
LO QUE NO SE PARECE A BINANCE, Y POR QUE COPIAR AQUEL CODIGO FALLA CALLADO
===========================================================================

Son cuatro diferencias y NINGUNA da error al copiarla mal. Todas fueron
comprobadas contra la API el 31/8/2026, no deducidas:

  1. UN ERROR DE BYBIT LLEGA CON HTTP 200.
     MEDIDO: pedir un símbolo inexistente devuelve HTTP 200 y el rechazo va
     adentro del cuerpo, `{"retCode": 10001, "retMsg": "params error: symbol
     invalid"}`. El módulo de Binance detecta el rechazo por `HTTPError`, y ese
     mismo código acá daría la respuesta POR BUENA: una lista vacía en vez de
     un error, o una orden que se cree mandada y no existe. Es la diferencia
     más peligrosa de las cuatro y por eso `_pedir` mira `retCode` SIEMPRE,
     antes que nada.

  2. NO SE FIRMAN LOS PARAMETROS.
     Se firma `timestamp + api_key + recv_window + (query o cuerpo)`, y la
     firma viaja en la cabecera `X-BAPI-SIGN`, no dentro de la query como en
     Binance. Firmar sólo los parámetros —que es lo que uno copia sin pensar—
     da "invalid signature", que manda a revisar la clave cuando la clave está
     bien.

  3. LAS VELAS VIENEN DE NUEVA A VIEJA.
     MEDIDO en BTCUSDT: la primera fila es la más reciente. Binance y BingX las
     mandan al revés. Esto no rompe nada visible: el motor calcularía las medias
     y el ADX sobre el tiempo invertido y devolvería números perfectamente
     creíbles, sólo que del revés. Acá se ordena antes de devolver.

  4. `reduceOnly` Y `positionIdx` CONVIVEN.
     En Binance son EXCLUYENTES —mandar los dos da -1106— y por eso aquel
     módulo elige uno según el modo. En Bybit `positionIdx` es obligatorio
     siempre y `reduceOnly` se agrega encima. Aplicar acá la regla de Binance
     deja la orden de cierre sin `reduceOnly` en modo cobertura, que es
     exactamente el error que en BingX ABRIA el lado contrario en silencio.

===========================================================================
LO QUE SI ES MEJOR QUE EN BINANCE
===========================================================================

EL STOP Y EL OBJETIVO VIAJAN EN LA ORDEN DE ENTRADA. En Binance hay que mandar
dos órdenes más después de que la entrada se llenó, y entre una cosa y la otra
la posición queda un rato desprotegida: si el proceso se muere justo ahí, queda
abierta y sin stop. Acá `takeProfit` y `stopLoss` son parámetros de la propia
orden, así que no existe esa ventana.

===========================================================================
LO QUE ESTA VERIFICADO Y LO QUE NO
===========================================================================

  * VERIFICADO contra la API real: la forma del error, el orden de las velas,
    los filtros del contrato, la firma (autentica y responde), el saldo, las
    posiciones y el modo de posición.
  * VERIFICADO contra la referencia oficial de `POST /v5/order/create`: los
    nombres de los parámetros, que `qty` va como TEXTO, que `positionIdx` es
    obligatorio, y que el stop y el objetivo se aceptan en la orden de entrada.
  * NO VERIFICADO todavía: una orden de verdad. La clave con la que se probó
    es de sólo lectura, así que el tramo de escritura está contrastado contra
    la documentación pero no ejecutado. Hasta que se corra con una clave de
    práctica, tratar `abrir`, `cerrar` y `proteger` como no probados.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

#: Los tres entornos, que son tres cuentas DISTINTAS.
#:
#: MEDIDO el 31/8/2026: una clave de la cuenta real devuelve 10003 "API key is
#: invalid" contra testnet y contra demo. No hay claves que sirvan en más de un
#: entorno, así que el que quiera probar tiene que crear la suya en el entorno
#: donde va a probar.
#:
#: `demo` es plata de juguete sobre la MISMA cuenta de siempre —se crea desde el
#: panel de Bybit— y por eso es la de por omisión: no obliga a registrarse en
#: otro sitio. `testnet` es un sitio aparte, con registro aparte.
BASE_REAL = "https://api.bybit.com"
BASE_PRUEBA = "https://api-demo.bybit.com"
BASE_TESTNET = "https://api-testnet.bybit.com"

#: Los perpetuos liquidados en USDT. Bybit unificó spot, futuros e inversos
#: bajo la misma API y `category` es lo que los separa: sin él, o con el
#: equivocado, el mismo símbolo devuelve otro instrumento.
CATEGORIA = "linear"

#: Cuánto puede demorarse el pedido en llegar antes de que Bybit lo descarte.
#:
#: OJO CON LA ASIMETRIA: la regla del servidor es
#: `hora_servidor - recv_window <= timestamp < hora_servidor + 1000`. O sea que
#: agrandar esto tolera un reloj ATRASADO o una conexión lenta, pero NO un
#: reloj adelantado: más de un segundo por delante se rechaza aunque acá se
#: pongan diez. Si aparece 10002, el reloj de la máquina va adelante y lo que
#: hay que arreglar es el reloj.
RECV_WINDOW = 10_000

#: Los intervalos de la aplicación traducidos a los de Bybit, que usa minutos
#: sueltos y letras. Se traduce en vez de pasarlos tal cual porque Bybit NO
#: rechaza "1h": lo toma como otra cosa o devuelve vacío, y un vacío silencioso
#: se lee como "el símbolo no existe".
INTERVALOS = {"1m": "1", "5m": "5", "15m": "15", "30m": "30",
              "1h": "60", "4h": "240", "1d": "D"}

#: Tope de velas por pedido que admite la API.
POR_PEDIDO = 1000


class BybitError(RuntimeError):
    """Bybit rechazó algo, y el mensaje es el suyo.

    Se conserva `retCode` porque cada uno manda a mirar otra cosa: 10003 es la
    clave, 10004 es la firma, 10002 es el reloj, 110007 es saldo insuficiente y
    110017 es una reducción que no reduce nada. Un mensaje genérico manda a
    revisar la clave siempre, que es el error que costó tres intentos en BingX.
    """

    def __init__(self, mensaje: str, codigo: int | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.del_exchange = mensaje


def _decimales(paso: Any) -> int:
    """Cuántos decimales admite ese paso, contados sobre el TEXTO.

    Con `Decimal` y no con float: el paso llega como "0.001" y pasarlo por
    float para contarle los decimales es pedirle a la representación binaria
    que conserve algo que no conserva.
    """
    exp = Decimal(str(paso)).normalize().as_tuple().exponent
    return max(0, -int(exp))


def _pedir(ruta: str, params: dict[str, Any] | None = None, *,
           api_key: str = "", secret: str = "", metodo: str = "GET",
           base: str = BASE_PRUEBA, timeout: float = 30.0) -> Any:
    """Un pedido a Bybit, firmado si le dan credenciales. Devuelve `result`.

    ==================================================================
    EL RECHAZO NO VIENE COMO ERROR DE HTTP: VIENE CON HTTP 200 Y
    `retCode` DISTINTO DE CERO. Mirarlo no es opcional.
    ==================================================================

    LA FIRMA ES SOBRE `timestamp + api_key + recv_window + carga`, donde la
    carga es la query en un GET y el cuerpo JSON en un POST. Y el cuerpo se
    serializa UNA SOLA VEZ: se firma ese texto y se manda ESE MISMO texto. Si
    se volviera a serializar para enviarlo, cualquier diferencia de orden o de
    espacios —que `json.dumps` puede introducir— produce una firma válida sobre
    un texto que nunca viajó, y el síntoma es "invalid signature", que manda a
    revisar la clave.

    El secreto NO viaja: se usa para firmar y no sale de esta función.
    """
    p = dict(params or {})
    headers = {"User-Agent": "botiquant"}
    cuerpo: bytes | None = None

    if metodo == "GET":
        carga = urllib.parse.urlencode(p)
        url = f"{base}{ruta}?{carga}" if carga else f"{base}{ruta}"
    else:
        # Una sola serialización: esta cadena es la que se firma Y la que se
        # manda. Ver el encabezado de la función.
        carga = json.dumps(p, separators=(",", ":"))
        cuerpo = carga.encode()
        url = f"{base}{ruta}"
        headers["Content-Type"] = "application/json"

    if api_key and secret:
        ts = str(int(time.time() * 1000))
        recv = str(RECV_WINDOW)
        firma = hmac.new(secret.encode(), f"{ts}{api_key}{recv}{carga}".encode(),
                         hashlib.sha256).hexdigest()
        headers.update({"X-BAPI-API-KEY": api_key, "X-BAPI-TIMESTAMP": ts,
                        "X-BAPI-RECV-WINDOW": recv, "X-BAPI-SIGN": firma,
                        # 2 = HMAC. Bybit también acepta RSA, y sin decir cuál
                        # es, valida contra el que tenga configurado.
                        "X-BAPI-SIGN-TYPE": "2"})

    req = urllib.request.Request(url, data=cuerpo, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        crudo = e.read()[:400].decode(errors="replace")
        raise BybitError(f"Bybit devolvió {e.code}: {crudo}") from e
    except OSError as e:
        raise BybitError(f"No se pudo conectar con Bybit: {e}") from e

    # ACA ESTA LA DIFERENCIA CON BINANCE. Llegar hasta este punto no significa
    # que haya salido bien: significa que hubo respuesta.
    codigo = d.get("retCode")
    if codigo != 0:
        raise BybitError(f"[{codigo}] {d.get('retMsg') or 'sin mensaje'}",
                         codigo=codigo)
    return d.get("result")


# --------------------------------------------------------------- sin clave

def ping(base: str = BASE_PRUEBA) -> bool:
    """¿Contesta? Sin clave: separa "no hay red" de "la clave está mal"."""
    _pedir("/v5/market/time", base=base)
    return True


def contrato(simbolo: str, base: str = BASE_PRUEBA,
             categoria: str = CATEGORIA) -> dict[str, Any]:
    """Mínimo, paso y tick de ese símbolo.

    HACE FALTA ANTES DE MANDAR NADA: una cantidad con más decimales de los que
    el símbolo acepta se rechaza, y una por debajo del mínimo también.

    Se guardan los pasos como TEXTO además de como número. El redondeo se hace
    con `Decimal` sobre ese texto, así que convertirlo a float acá sería perder
    justo lo que hace falta conservar.

    MEDIDO en BTCUSDT: mínimo 0,001 BTC, paso 0,001, nocional mínimo 5 USDT,
    tick 0,10. Con BTC a 78.000 el que manda es el mínimo por cantidad —78
    USDT— y no el nocional.
    """
    d = _pedir("/v5/market/instruments-info",
               {"category": categoria, "symbol": simbolo}, base=base)
    for s in (d.get("list") or []):
        if s.get("symbol") != simbolo:
            continue
        lote = s.get("lotSizeFilter", {})
        precio = s.get("priceFilter", {})
        paso = lote.get("qtyStep") or "0"
        tick = precio.get("tickSize") or "0"
        return {
            "simbolo": simbolo,
            "minimo": float(lote.get("minOrderQty") or 0),
            "paso": float(paso),
            "paso_texto": str(paso),
            "decimales_cantidad": _decimales(paso),
            # El tope de una orden A MERCADO es más bajo que el de una límite,
            # y es el que corresponde acá porque todas las de este módulo son
            # a mercado.
            "maximo": float(lote.get("maxMktOrderQty")
                            or lote.get("maxOrderQty") or 0),
            "minimo_nocional": float(lote.get("minNotionalValue") or 0),
            "tick": float(tick),
            "tick_texto": str(tick),
            "decimales_precio": _decimales(tick),
        }
    raise BybitError(f"{simbolo} no existe en los perpetuos {categoria} de Bybit.")


def cuenta_minima(precio: float, contrato_: dict[str, Any], *,
                  stop_pct: float, riesgo_pct: float) -> float:
    """Cuánta cuenta hace falta para que la orden más chica sea posible.

    ES LA PREGUNTA QUE DECIDE SI EL BOT VA A OPERAR O NO. Con una cuenta por
    debajo de esto, el tamaño que sale del riesgo pedido queda debajo del
    mínimo del exchange: o la orden se rechaza, o —peor— se redondea hacia
    arriba y se arriesga más de lo que se pidió.

    Misma cuenta que en Binance, con los mínimos de Bybit: manda el mayor entre
    el mínimo por cantidad y el mínimo por nocional. En un portafolio esto es
    POR ESTRATEGIA, porque cada una maneja su porción.
    """
    if precio <= 0 or stop_pct <= 0 or riesgo_pct <= 0:
        return 0.0
    minimo_en_plata = max(contrato_.get("minimo", 0.0) * precio,
                          contrato_.get("minimo_nocional", 0.0))
    riesgo_de_esa_orden = minimo_en_plata * stop_pct / 100.0
    return riesgo_de_esa_orden / (riesgo_pct / 100.0)


# --------------------------------------------------------------- con clave

def permisos(api_key: str, secret: str,
             base: str = BASE_PRUEBA) -> dict[str, Any]:
    """Qué puede hacer esta clave, dicho por Bybit.

    SIRVE PARA AVISAR ANTES Y NO DESPUES. Una clave de sólo lectura deja pasar
    todas las comprobaciones —lee el saldo, lee las posiciones, lee el
    contrato— y recién falla cuando hay que mandar la primera orden, que es el
    peor momento para enterarse. Preguntarlo de entrada permite decirlo en
    pantalla mientras todavía no hay nada en juego.

    También devuelve el vencimiento: las claves de Bybit CADUCAN, y una clave
    vencida falla igual que una mal escrita.
    """
    d = _pedir("/v5/user/query-api", api_key=api_key, secret=secret, base=base)
    return {
        "solo_lectura": bool(d.get("readOnly")),
        "puede_operar": not bool(d.get("readOnly")),
        "vence": d.get("expiredAt") or "",
        "nota": d.get("note") or "",
        "ips": d.get("ips") or [],
        "permisos": d.get("permissions") or {},
    }


def modo_posicion(api_key: str, secret: str, simbolo: str = "BTCUSDT",
                  base: str = BASE_PRUEBA,
                  categoria: str = CATEGORIA) -> str:
    """"una_via" o "cobertura". Determina QUE `positionIdx` lleva cada orden.

    SE PREGUNTA MIRANDO UNA POSICION, y no hay mejor manera: Bybit tiene
    endpoint para CAMBIAR el modo pero ninguno para consultarlo. Lo que sí dice
    es el `positionIdx` de cada posición del símbolo — 0 cuando la cuenta está
    en una vía, 1 y 2 cuando está en cobertura— y eso viene aunque no haya nada
    abierto.

    MEDIDO en una cuenta real sin posiciones: devuelve una fila con
    `positionIdx = 0`, o sea que el modo se puede saber sin operar.
    """
    d = _pedir("/v5/position/list", {"category": categoria, "symbol": simbolo},
               api_key=api_key, secret=secret, base=base)
    for p in (d.get("list") or []):
        if int(p.get("positionIdx") or 0) != 0:
            return "cobertura"
    return "una_via"


def _idx(modo: str, lado: int) -> int:
    """El `positionIdx` que va en la orden. 0 en una vía; 1 largo y 2 corto.

    Es obligatorio en las dos modalidades, a diferencia del `positionSide` de
    Binance, que en modo simple NO se puede mandar.
    """
    if modo != "cobertura":
        return 0
    return 1 if lado > 0 else 2


def saldo(api_key: str, secret: str, moneda: str = "USDT",
          base: str = BASE_PRUEBA) -> float:
    """El disponible de la cuenta unificada, en esa moneda.

    Se lee `equity` de la moneda y no `availableToWithdraw`: MEDIDO en una
    cuenta real, ese campo vuelve VACIO —cadena de largo cero, no cero— y
    pasarlo por `float` revienta. Lo retirable además no es lo operable: parte
    del capital puede estar sosteniendo margen y seguir siendo capital.
    """
    d = _pedir("/v5/account/wallet-balance", {"accountType": "UNIFIED"},
               api_key=api_key, secret=secret, base=base)
    for cuenta in (d.get("list") or []):
        for c in (cuenta.get("coin") or []):
            if c.get("coin") == moneda:
                return float(c.get("equity") or c.get("walletBalance") or 0.0)
    return 0.0


def posicion(simbolo: str, api_key: str, secret: str,
             base: str = BASE_PRUEBA,
             categoria: str = CATEGORIA) -> dict[str, Any]:
    """Lo que hay abierto en ese símbolo. Se PREGUNTA, no se recuerda.

    Recordarla en memoria significa que un reinicio de la aplicación, o una
    orden puesta a mano desde el exchange, dejan al bot operando contra una
    posición que cree que no existe.

    En cobertura pueden venir DOS filas del mismo símbolo, una por lado; se
    suman con signo, así que un largo y un corto iguales dan plano, que es lo
    que efectivamente hay.

    Devuelve además el STOP y el OBJETIVO que el exchange tiene registrados,
    que es la única forma de comprobar que la protección quedó puesta de
    verdad. Que la orden de entrada no haya dado error no alcanza: lo que
    importa es que Bybit los tenga anotados del lado de él.
    """
    d = _pedir("/v5/position/list", {"category": categoria, "symbol": simbolo},
               api_key=api_key, secret=secret, base=base)
    total = 0.0
    entrada = float("nan")
    stop = objetivo = 0.0
    for p in (d.get("list") or []):
        if p.get("symbol") != simbolo:
            continue
        cant = float(p.get("size") or 0.0)
        if not cant:
            continue
        signo = -1.0 if str(p.get("side")) == "Sell" else 1.0
        total += signo * cant
        entrada = float(p.get("avgPrice") or 0.0)
        # Vienen como cadena, y VACIAS cuando no hay ninguno puesto: pasarlas
        # por float sin el `or 0` levanta ValueError.
        stop = float(p.get("stopLoss") or 0.0)
        objetivo = float(p.get("takeProfit") or 0.0)
    lado = 1 if total > 0 else (-1 if total < 0 else 0)
    return {"lado": lado, "cantidad": abs(total), "precio_entrada": entrada,
            "stop": stop, "objetivo": objetivo}


# ------------------------------------------------------------ mandar órdenes

def _redondear(cantidad: float, contrato_: dict[str, Any]) -> str:
    """La cantidad al paso que el símbolo acepta, SIEMPRE HACIA ABAJO y en TEXTO.

    HACIA ABAJO y no al más cercano: redondear hacia arriba arriesga MAS de lo
    que se pidió, y de a poco. Una orden rechazada por chica se ve; una que
    arriesga 1,3% cuando se pidió 1% no se ve nunca.

    EN TEXTO porque Bybit pide `qty` como cadena, y porque es la única forma de
    que no se cuele un `1e-05`: `str(0.00001)` en Python da notación
    científica, que el exchange rechaza con un error sobre el parámetro y no
    sobre el formato.

    Con `Decimal` y no con float: `floor(0.3 / 0.1)` da 2 en aritmética binaria
    y ahí se pierde un tercio de la orden sin que nadie se entere.
    """
    paso = Decimal(contrato_.get("paso_texto") or "0")
    dec = int(contrato_.get("decimales_cantidad") or 0)
    n = Decimal(str(abs(cantidad)))
    if paso > 0:
        n = (n / paso).to_integral_value(rounding=ROUND_DOWN) * paso
    return f"{n:.{dec}f}"


def _a_tick(precio: float, contrato_: dict[str, Any]) -> str:
    """Un precio ajustado al tick del símbolo, en texto.

    Un stop con más decimales que el tick se rechaza. Se redondea al más
    cercano y no hacia un lado: acá no hay riesgo que se acumule —el tick de
    BTCUSDT son diez centavos sobre setenta y ocho mil dólares— y sesgarlo
    correría el stop siempre para el mismo lado sin motivo.
    """
    tick = Decimal(contrato_.get("tick_texto") or "0")
    dec = int(contrato_.get("decimales_precio") or 0)
    n = Decimal(str(precio))
    if tick > 0:
        n = (n / tick).to_integral_value(rounding=ROUND_HALF_UP) * tick
    return f"{n:.{dec}f}"


def abrir(simbolo: str, lado: int, cantidad: float, *,
          api_key: str, secret: str, modo: str,
          stop: float | None = None, objetivo: float | None = None,
          precio: float | None = None,
          contrato_: dict[str, Any] | None = None,
          base: str = BASE_PRUEBA, categoria: str = CATEGORIA) -> dict[str, Any]:
    """Abre a mercado, CON EL STOP Y EL OBJETIVO PUESTOS EN LA MISMA ORDEN.

    ==================================================================
    QUE LA PROTECCION VIAJE ADENTRO DE LA ENTRADA ES LO QUE HACE QUE NO
    EXISTA UNA POSICION DESPROTEGIDA, NI POR UN INSTANTE.
    ==================================================================

    En Binance el stop es una segunda orden que se manda después de que la
    entrada se llenó, y entre las dos hay una ventana: si el proceso se muere
    ahí —o el segundo pedido falla— queda una posición abierta que nadie está
    cuidando. Bybit acepta `stopLoss` y `takeProfit` como parámetros de la
    orden de entrada, así que esa ventana no existe.

    Y las órdenes quedan DEL LADO DEL EXCHANGE: apagar la aplicación significa
    que no entra en operaciones nuevas, no que la abierta quede a la deriva.

    `slTriggerBy=MarkPrice` y no el precio del último negocio: el de marca es
    el que Bybit usa para liquidar, así que es contra el que conviene medir el
    stop. Con el último precio, una mecha en un libro fino dispara un stop que
    la liquidación no habría tocado.

    `tpslMode=Full` cierra la posición ENTERA al dispararse. Si cerrara sólo
    una parte quedaría la mitad sin protección y nadie lo miraría.

    OJO CON LA RESPUESTA: Bybit devuelve `orderId` y nada más. NO dice a cuánto
    entró —no hay equivalente al `newOrderRespType=RESULT` de Binance— así que
    el precio de ejecución hay que preguntarlo aparte con `detalle_orden`.

    `precio` es opcional y sirve para UNA sola cosa: comprobar el mínimo por
    NOCIONAL antes de mandar. Sin él ese control no se puede hacer —una orden a
    mercado no lleva precio— y lo rechaza el exchange en vez de este módulo.
    """
    if lado not in (1, -1):
        raise BybitError("El lado tiene que ser +1 (largo) o -1 (corto).")
    c = contrato_ or contrato(simbolo, base, categoria)
    qty = _redondear(cantidad, c)

    minimo = float(c.get("minimo") or 0.0)
    if float(qty) < minimo or float(qty) <= 0:
        raise BybitError(
            f"La cantidad que sale del riesgo pedido ({cantidad:g}) queda por "
            f"debajo del mínimo de {simbolo} ({minimo:g}). Con esta cuenta el "
            f"bot no puede abrir sin arriesgar más de lo pedido.")
    # EL MINIMO POR NOCIONAL, QUE EN LA MAYORIA DE LOS SIMBOLOS ES EL QUE MANDA.
    #
    # MEDIDO el 31/8/2026: en XRPUSDT el mínimo por cantidad son 0,1 XRP —14
    # centavos— pero Bybit exige 5 USDT de nocional. O sea que una orden puede
    # pasar el control de arriba y ser rechazada igual. Lo mismo en DOGE, ADA,
    # LINK, AVAX y TRX: en los seis manda el nocional, no la cantidad.
    nocional_min = float(c.get("minimo_nocional") or 0.0)
    if precio and nocional_min and float(qty) * precio < nocional_min:
        raise BybitError(
            f"La orden ({qty} {simbolo} ≈ {float(qty) * precio:,.2f} USDT) no "
            f"llega al mínimo por nocional de {nocional_min:g} USDT. El mínimo "
            f"por cantidad sí lo pasa: es el nocional el que manda en este "
            f"símbolo.")

    maximo = float(c.get("maximo") or 0.0)
    if maximo and float(qty) > maximo:
        raise BybitError(
            f"La cantidad ({qty}) pasa el máximo por orden a mercado de "
            f"{simbolo} ({maximo:g}). Habría que partirla en varias órdenes, y "
            f"este módulo no lo hace: se prefiere no mandar nada a mandar la "
            f"mitad y creer que entró entera.")

    p: dict[str, Any] = {
        "category": categoria, "symbol": simbolo,
        "side": "Buy" if lado > 0 else "Sell",
        "orderType": "Market", "qty": qty,
        # Obligatorio en las dos modalidades, al revés que en Binance.
        "positionIdx": _idx(modo, lado),
    }
    if stop is not None and stop == stop and stop > 0:      # descarta NaN
        p.update({"stopLoss": _a_tick(stop, c), "slTriggerBy": "MarkPrice",
                  "slOrderType": "Market", "tpslMode": "Full"})
    if objetivo is not None and objetivo == objetivo and objetivo > 0:
        p.update({"takeProfit": _a_tick(objetivo, c), "tpTriggerBy": "MarkPrice",
                  "tpOrderType": "Market", "tpslMode": "Full"})

    return _pedir("/v5/order/create", p, api_key=api_key, secret=secret,
                  metodo="POST", base=base)


def cerrar(simbolo: str, lado_abierto: int, cantidad: float, *,
           api_key: str, secret: str, modo: str,
           contrato_: dict[str, Any] | None = None,
           base: str = BASE_PRUEBA, categoria: str = CATEGORIA) -> dict[str, Any]:
    """Cierra lo que haya abierto, mandando la orden contraria.

    ACA ESTA EL ERROR QUE EN BINGX COSTO CARO: sin marcar la orden como de
    cierre, la contraria no cierra sino que ABRE el lado opuesto, en silencio.

    Y ACA ESTA LA TRAMPA DE COPIAR EL MODULO DE BINANCE: allá `reduceOnly` y
    `positionSide` son excluyentes y hay que elegir uno según el modo. En Bybit
    NO: `positionIdx` va siempre y `reduceOnly` se agrega encima, en las dos
    modalidades. Traer la regla de Binance dejaría la orden de cierre sin
    `reduceOnly` en cobertura, que es exactamente la falla de BingX.
    """
    if lado_abierto not in (1, -1):
        raise BybitError("No hay posición abierta que cerrar.")
    c = contrato_ or contrato(simbolo, base, categoria)
    qty = _redondear(cantidad, c)
    if float(qty) <= 0:
        raise BybitError("La cantidad a cerrar quedó en cero al redondear.")

    p: dict[str, Any] = {
        "category": categoria, "symbol": simbolo,
        # la contraria a la que abrió
        "side": "Sell" if lado_abierto > 0 else "Buy",
        "orderType": "Market", "qty": qty,
        "positionIdx": _idx(modo, lado_abierto),
        "reduceOnly": True,
    }
    return _pedir("/v5/order/create", p, api_key=api_key, secret=secret,
                  metodo="POST", base=base)


def proteger(simbolo: str, lado: int, *, stop: float | None, objetivo: float | None,
             api_key: str, secret: str, modo: str,
             contrato_: dict[str, Any] | None = None,
             base: str = BASE_PRUEBA,
             categoria: str = CATEGORIA) -> dict[str, Any]:
    """Pone o corrige el stop y el objetivo de una posición YA ABIERTA.

    El camino normal es que la protección viaje dentro de la entrada —ver
    `abrir`— así que esto es para los otros dos casos: mover el stop mientras
    la operación corre, y ponerle protección a algo que se abrió por fuera de
    la aplicación.

    No es una orden sino un ajuste de la posición (`/v5/position/trading-stop`),
    y por eso no lleva cantidad ni lado de orden: `tpslMode=Full` ya dice que se
    aplica a la posición entera.
    """
    c = contrato_ or contrato(simbolo, base, categoria)
    p: dict[str, Any] = {"category": categoria, "symbol": simbolo,
                         "tpslMode": "Full", "positionIdx": _idx(modo, lado)}
    if stop is not None and stop == stop and stop > 0:
        p.update({"stopLoss": _a_tick(stop, c), "slTriggerBy": "MarkPrice"})
    if objetivo is not None and objetivo == objetivo and objetivo > 0:
        p.update({"takeProfit": _a_tick(objetivo, c), "tpTriggerBy": "MarkPrice"})
    if "stopLoss" not in p and "takeProfit" not in p:
        raise BybitError("No se pidió ni stop ni objetivo: no hay nada que poner.")
    return _pedir("/v5/position/trading-stop", p, api_key=api_key,
                  secret=secret, metodo="POST", base=base)


def detalle_orden(simbolo: str, order_id: str, *, api_key: str, secret: str,
                  base: str = BASE_PRUEBA,
                  categoria: str = CATEGORIA) -> dict[str, Any]:
    """A cuánto entró y cuánto entró, preguntado después de mandar la orden.

    HACE FALTA PORQUE BYBIT NO LO DICE AL RESPONDER. La respuesta de
    `/v5/order/create` trae `orderId` y nada más; el precio promedio y la
    cantidad ejecutada hay que ir a buscarlos. Sin esto, el registro del bot
    dice que operó pero no a cuánto, que es justo el dato que sirve para
    comparar la ejecución contra lo que esperaba la estrategia.

    Se consulta el historial y no las órdenes abiertas: una orden a mercado se
    llena en el momento, así que para cuando se pregunta ya no está entre las
    vivas.
    """
    d = _pedir("/v5/order/history",
               {"category": categoria, "symbol": simbolo, "orderId": order_id},
               api_key=api_key, secret=secret, base=base)
    for o in (d.get("list") or []):
        if o.get("orderId") != order_id:
            continue
        return {
            "id": order_id,
            "estado": o.get("orderStatus") or "",
            "cantidad": float(o.get("cumExecQty") or 0.0),
            "precio": float(o.get("avgPrice") or 0.0),
            "comision": float(o.get("cumExecFee") or 0.0),
        }
    raise BybitError(f"Bybit no encontró la orden {order_id} de {simbolo}.")


# ------------------------------------------------------------------- velas

def velas(simbolo: str, intervalo: str = "1h", limite: int = 500,
          base: str = BASE_REAL, categoria: str = CATEGORIA) -> "Any":
    """Las últimas velas, ORDENADAS DE VIEJA A NUEVA y en UTC.

    ==================================================================
    BYBIT LAS MANDA AL REVES: LA PRIMERA FILA ES LA MAS RECIENTE.
    ==================================================================

    MEDIDO el 31/8/2026 en BTCUSDT horario: llegan 15:00, 14:00, 13:00, 12:00,
    en ese orden. Binance y BingX las mandan de vieja a nueva, así que el motor
    espera eso y ninguna capa de más abajo lo revisa.

    Y NO ROMPE NADA VISIBLE, que es lo peor: las medias, el ADX y el Donchian
    se calculan igual sobre el tiempo invertido y devuelven números creíbles.
    Un bot alimentado así opera al revés y parece que anda.

    La última fila es la vela EN CURSO, sin cerrar. No se descarta acá: de eso
    se ocupa `solo_cerradas` en el núcleo, que es donde ya se decide para todos
    los exchanges, y hacerlo dos veces sería tirar una vela buena.

    OJO CON LA BASE: por omisión son las de PRODUCCION, incluso cuando se opera
    contra el entorno de prueba. Es la misma decisión que en Binance y por el
    mismo motivo: el volumen de un entorno de prueba sale de operaciones
    falsas, y la biblioteca tiene dos indicadores que lo usan. Que la decisión
    sea idéntica en los dos lados importa más que la coherencia de mirar y
    operar contra el mismo sitio; lo que cambia entre entornos es dónde se
    ejecuta la orden, no qué se ve.
    """
    import pandas as pd

    if intervalo not in INTERVALOS:
        raise BybitError(
            f"Intervalo no soportado: {intervalo}. "
            f"Son {', '.join(INTERVALOS)}.")
    # Se acota acá y no se confía en el servidor: pedir de más devuelve vacío,
    # y un vacío silencioso se confunde con "el símbolo no existe".
    limite = max(1, min(int(limite), POR_PEDIDO))

    d = _pedir("/v5/market/kline",
               {"category": categoria, "symbol": simbolo,
                "interval": INTERVALOS[intervalo], "limit": limite}, base=base)
    filas = d.get("list") or []
    if not filas:
        raise BybitError(
            f"Bybit no devolvió velas de {simbolo}. Revisá que el símbolo vaya "
            f"sin guion (BTCUSDT, no BTC-USDT) y que el contrato exista.")

    df = pd.DataFrame([{
        "time": pd.to_datetime(int(f[0]), unit="ms", utc=True),
        "open": float(f[1]), "high": float(f[2]), "low": float(f[3]),
        "close": float(f[4]), "volume": float(f[5]),
    } for f in filas]).set_index("time")

    # LA LINEA QUE ARREGLA EL ORDEN. Ver el encabezado.
    df = df.sort_index()
    return df[~df.index.duplicated(keep="last")]
