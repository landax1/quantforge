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

CONTRASTADO CONTRA LA REFERENCIA OFICIAL de `POST /fapi/v1/order`: una orden a
mercado pide sólo `quantity` —sin `price` ni `timeInForce`—, `positionSide`
DEBE mandarse en cobertura, `reduceOnly` NO PUEDE mandarse en cobertura, y
`recvWindow` tiene un tope de 60.000 ms. Las cuatro coinciden con lo que hace
este módulo.

===========================================================================
EL STOP NO SE MANDA POR DONDE SE MANDA LA ENTRADA
===========================================================================

MEDIDO el 31/8/2026 contra la API: `POST /fapi/v1/order` RECHAZA todos los
tipos condicionales con `-4120 Order type not supported for this endpoint`.
Se probaron ocho variantes de parametros —con y sin `closePosition`, con y sin
`priceProtect`, con cantidad y con `reduceOnly`— y las ocho dieron lo mismo:
no es una combinacion mal armada, es el endpoint.

La causa es un cambio de Binance del 2025-12-09: las condicionales de futuros
USDⓈ-M se mudaron a un Algo Service propio. Lo que cambia:

    poner el stop      POST   /fapi/v1/algoOrder      (antes /fapi/v1/order)
    el precio          `triggerPrice`                 (antes `stopPrice`)
    verlas             GET    /fapi/v1/openAlgoOrders (antes /fapi/v1/openOrders)
    cancelarlas        DELETE /fapi/v1/algoOpenOrders

LO PELIGROSO NO ES EL RECHAZO SINO LA CONSULTA. Que la orden falle se ve. Pero
`/fapi/v1/openOrders` sigue contestando 200 con una lista VACIA aunque el stop
este perfectamente puesto —MEDIDO: cero ordenes con dos condicionales vivas—
asi que un codigo que pregunte ahi concluye "no hay stop" cuando lo hay, y al
reves nunca se entera de que si lo hay.

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


#: Reloj de Binance menos reloj local, en milisegundos. Ver `_sincronizar`.
_DESFASE_MS = 0
#: Cuándo se midió (reloj local, segundos); 0 es "nunca".
_DESFASE_MEDIDO = 0.0
#: Códigos que dicen "probá de nuevo" y no "esto está mal": reloj fuera de
#: ventana, error interno, límite de pedidos, tiempo agotado, sobrecarga.
TRANSITORIOS = frozenset({-1001, -1003, -1007, -1008, -1021})


def _sincronizar(base: str = BASE_PRUEBA, timeout: float = 10.0) -> int:
    """Mide cuánto adelanta el reloj de Binance al de esta máquina.

    ==================================================================
    LA PC NO SINCRONIZA SU RELOJ. Pasó de verdad: el servicio de hora de
    Windows estaba parado, el reloj iba cuatro segundos atrás, y la demo
    tarda otros cuatro en responder. Binance rechazó los pedidos con -1021
    y dos bots se apagaron en plena vela.
    ==================================================================

    Se descuenta la mitad del viaje, que es la estimación honesta del
    instante en que el servidor leyó su reloj. Arreglar el reloj de Windows
    pide permisos de administrador; esto no pide nada.
    """
    global _DESFASE_MS, _DESFASE_MEDIDO
    t0 = time.time() * 1000
    req = urllib.request.Request(f"{base}/fapi/v1/time", headers={"User-Agent": "botiquant"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        servidor = int(json.load(r)["serverTime"])
    t1 = time.time() * 1000
    _DESFASE_MS = int(servidor - (t0 + t1) / 2)
    _DESFASE_MEDIDO = time.time()
    return _DESFASE_MS


def _marcar_medido() -> None:
    global _DESFASE_MEDIDO
    _DESFASE_MEDIDO = time.time()


def _ahora_ms() -> int:
    """La hora que Binance espera ver: la local corregida por el desfase."""
    return int(time.time() * 1000) + _DESFASE_MS


def _pedir(ruta: str, params: dict[str, Any] | None = None, *,
           api_key: str = "", secret: str = "", metodo: str = "GET",
           base: str = BASE_PRUEBA, timeout: float = 30.0,
           _reintento: bool = False) -> Any:
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
        # La primera vez que se firma algo se mide el reloj; después sólo
        # cuando Binance dice que está fuera de ventana.
        if not _DESFASE_MEDIDO:
            try:
                _sincronizar(base)
            except (OSError, ValueError, KeyError, TypeError):
                # Se sigue con el reloj local y no se vuelve a intentar en
                # cada pedido: si el reloj está mal, el -1021 lo va a decir
                # y ahí se mide de nuevo.
                _marcar_medido()
        p.setdefault("timestamp", _ahora_ms())
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
        except ValueError:
            raise BinanceError(f"Binance devolvió {e.code}: {crudo}") from e
        if not isinstance(d, dict):
            raise BinanceError(f"Binance devolvió {e.code}: {crudo}") from e
        if d.get("code") == -1021 and not _reintento and api_key and secret:
            # RELOJ FUERA DE VENTANA: se vuelve a medir el desfase y se
            # repite UNA vez con la hora corregida. Una sola, para no
            # insistir contra un exchange que rechaza por otra cosa.
            try:
                _sincronizar(base)
            except (OSError, ValueError, KeyError):
                pass
            return _pedir(ruta, params, api_key=api_key, secret=secret,
                          metodo=metodo, base=base, timeout=timeout,
                          _reintento=True)
        raise BinanceError(
            f"[{d.get('code')}] {d.get('msg') or crudo}",
            codigo=d.get("code")) from e
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
                # El salto de precio. MEDIDO en BTCUSDT: el tick es 0,10
                # mientras que `pricePrecision` dice 2, o sea que respetar los
                # decimales NO alcanza para respetar el tick. Se guarda como
                # texto además de como número porque el redondeo se hace con
                # Decimal, y pasarlo por float pierde justo lo que hace falta.
                "tick": float(f.get("PRICE_FILTER", {}).get("tickSize") or 0),
                "tick_texto": str(f.get("PRICE_FILTER", {}).get("tickSize") or "0"),
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


def posiciones(api_key: str, secret: str,
               base: str = BASE_PRUEBA) -> list[dict[str, Any]]:
    """TODAS las posiciones abiertas de la cuenta, no las de un símbolo.

    Es lo que hace falta para un tablero: con varios bots, preguntar símbolo
    por símbolo son varias llamadas y una foto que no es simultánea — una
    posición podría abrirse entre la primera y la última y el total no cerrar
    con nada.

    Y ES LA CUENTA LA QUE MANDA, no lo que los bots recuerden. Una posición
    abierta a mano desde Binance aparece acá igual, que es justamente lo que
    uno quiere ver en un tablero: qué hay, no qué debería haber.
    """
    d = _pedir("/fapi/v2/positionRisk", {}, api_key=api_key, secret=secret,
               base=base) or []
    salida = []
    for p in d:
        cant = float(p.get("positionAmt") or 0.0)
        if not cant:
            continue
        salida.append({
            "simbolo": p.get("symbol") or "",
            "lado": 1 if cant > 0 else -1,
            "cantidad": abs(cant),
            "precio_entrada": float(p.get("entryPrice") or 0.0),
            "precio_marca": float(p.get("markPrice") or 0.0),
            "pnl_abierto": float(p.get("unRealizedProfit") or 0.0),
            "liquidacion": float(p.get("liquidationPrice") or 0.0),
            "apalancamiento": float(p.get("leverage") or 0.0),
        })
    return salida


def movimientos(api_key: str, secret: str, *, desde_ms: int | None = None,
                limite: int = 1000,
                base: str = BASE_PRUEBA) -> list[dict[str, Any]]:
    """De qué se compone el resultado de la cuenta, partido por concepto.

    ==================================================================
    ESTE ES EL UNICO ENDPOINT QUE SEPARA LA VENTAJA DE LOS COSTOS.
    ==================================================================

    Binance devuelve el PNL realizado, la comisión y el funding como filas
    distintas, y esa separación es la que convierte un tablero en información:
    una estrategia puede tener el PNL en positivo y la cuenta en negativo
    porque las comisiones se lo comieron, y sumando un solo número eso no se
    ve — se ve "pierde", que manda a cambiar la estrategia cuando lo que hay
    que cambiar es cuánto opera.

    El signo viene de Binance: la comisión siempre negativa, el funding a
    favor o en contra según de qué lado estaba la posición.
    """
    p: dict[str, Any] = {"limit": int(min(max(limite, 1), 1000))}
    if desde_ms:
        p["startTime"] = int(desde_ms)
    return _pedir("/fapi/v1/income", p, api_key=api_key, secret=secret,
                  base=base) or []


def cerradas(simbolo: str, api_key: str, secret: str, *, limite: int = 100,
             base: str = BASE_PRUEBA) -> list[dict[str, Any]]:
    """Las ejecuciones de ese símbolo, de la más nueva a la más vieja.

    UNA OPERACION PUEDE SER VARIAS EJECUCIONES: una orden a mercado grande se
    llena contra varios niveles del libro y Binance devuelve una fila por
    llenado. No se agrupan acá —agrupar exige decidir qué es "la misma
    operación", y eso depende de la estrategia— pero el tablero lo dice para
    que nadie lea diez filas como diez operaciones.
    """
    d = _pedir("/fapi/v1/userTrades", {"symbol": simbolo, "limit": int(limite)},
               api_key=api_key, secret=secret, base=base) or []
    return [{
        "simbolo": t.get("symbol") or "",
        "cuando": int(t.get("time") or 0),
        "lado": "compra" if t.get("buyer") else "venta",
        "cantidad": float(t.get("qty") or 0.0),
        "precio": float(t.get("price") or 0.0),
        "pnl": float(t.get("realizedPnl") or 0.0),
        "comision": float(t.get("commission") or 0.0),
        "orden": t.get("orderId"),
    } for t in reversed(d)]


def ordenes_abiertas(simbolo: str, api_key: str, secret: str,
                     base: str = BASE_PRUEBA) -> list[dict[str, Any]]:
    """Las órdenes que siguen vivas en ese símbolo. El stop, entre ellas.

    ES LA UNICA FORMA DE COMPROBAR QUE LA PROTECCION QUEDO PUESTA. Que
    `proteger` no haya devuelto error significa que el pedido se aceptó, no que
    el exchange tenga el stop anotado. Y la diferencia entre esas dos cosas es
    una posición que uno cree protegida y no lo está — que se descubre el día
    que el precio va en contra, o sea el peor día para descubrirlo.

    Se devuelve la lista cruda: al llamador le interesa el `type` y el
    `stopPrice`, y filtrar acá lo obligaría a adivinar cuál le importa.
    """
    return _pedir("/fapi/v1/openOrders", {"symbol": simbolo},
                  api_key=api_key, secret=secret, base=base) or []


def condicionales_abiertas(simbolo: str, api_key: str, secret: str,
                           base: str = BASE_PRUEBA) -> list[dict[str, Any]]:
    """Los stops y objetivos vivos. NO ESTAN DONDE LAS DEMAS ORDENES.

    ==================================================================
    `ordenes_abiertas` NO LOS VE, Y NO AVISA: DEVUELVE UNA LISTA VACIA.
    ==================================================================

    MEDIDO el 31/8/2026 con un stop y un objetivo correctamente puestos:
    `/fapi/v1/openOrders` devolvió CERO órdenes. Desde la mudanza al Algo
    Service las condicionales sólo aparecen acá. Preguntar en el lugar viejo da
    "no hay stop" cuando lo hay — una alarma falsa permanente— y jamás confirma
    que lo haya.

    Se normalizan los dos campos que importan, porque el Algo Service los llama
    distinto que el endpoint viejo: `orderType` en vez de `type`, y
    `triggerPrice` en vez de `stopPrice`.
    """
    d = _pedir("/fapi/v1/openAlgoOrders", {"symbol": simbolo},
               api_key=api_key, secret=secret, base=base) or []
    return [{
        "id": o.get("algoId"),
        "tipo": o.get("orderType") or o.get("type") or "",
        "disparo": float(o.get("triggerPrice") or 0.0),
        "estado": o.get("algoStatus") or "",
        "cierra_todo": bool(o.get("closePosition")),
        "crudo": o,
    } for o in d]


def detalle_orden(simbolo: str, order_id: Any, *, api_key: str, secret: str,
                  base: str = BASE_PRUEBA) -> dict[str, Any]:
    """A cuánto entró, preguntado DESPUES de mandar la orden.

    HACE FALTA PORQUE LA RESPUESTA DE LA ORDEN NO LO TRAE. Ni siquiera con
    `newOrderRespType=RESULT`: medido el 31/8/2026 en una orden a mercado
    llenada entera, `executedQty` vino bien y `avgPrice` vino en None, porque
    Binance responde antes de agregar los llenados.

    Sin esto el registro del bot dice que operó pero no a cuánto, que es
    justamente el dato que sirve para comparar la ejecución contra lo que
    esperaba la estrategia.
    """
    o = _pedir("/fapi/v1/order", {"symbol": simbolo, "orderId": order_id},
               api_key=api_key, secret=secret, base=base)
    return {
        "id": o.get("orderId"),
        "estado": o.get("status") or "",
        "cantidad": float(o.get("executedQty") or 0.0),
        "precio": float(o.get("avgPrice") or 0.0),
    }


def cancelar_todo(simbolo: str, api_key: str, secret: str,
                  base: str = BASE_PRUEBA) -> dict[str, Any]:
    """Cancela TODAS las órdenes pendientes de ese símbolo.

    HACE FALTA AL CERRAR A MANO. Si se cierra la posición con una orden a
    mercado, el stop y el objetivo que quedaron puestos pueden sobrevivirla.
    Los de `closePosition` se cancelan solos —no les queda nada que cerrar—
    pero depender de eso es depender de un detalle del exchange en vez de
    dejar la cuenta limpia a propósito.

    ES UNA LIMPIEZA, NO UN CIERRE: no toca la posición. Cancelar las órdenes
    con la posición abierta la deja DESPROTEGIDA, así que esto va DESPUES de
    cerrar y nunca antes.

    SON DOS BORRADOS Y NO UNO. Las comunes y las condicionales viven en
    servicios distintos desde el cambio del 2025-12-09, y cancelar sólo las
    comunes deja el stop y el objetivo dando vueltas: MEDIDO, después de cerrar
    la posición las dos condicionales seguían vivas.
    """
    salidas: dict[str, Any] = {}
    salidas["comunes"] = _pedir("/fapi/v1/allOpenOrders", {"symbol": simbolo},
                                api_key=api_key, secret=secret,
                                metodo="DELETE", base=base)
    # Sin condicionales vivas esto devuelve un error en vez de no hacer nada,
    # y no tener nada que borrar no es un fallo de la limpieza.
    try:
        salidas["condicionales"] = _pedir(
            "/fapi/v1/algoOpenOrders", {"symbol": simbolo}, api_key=api_key,
            secret=secret, metodo="DELETE", base=base)
    except BinanceError as exc:
        salidas["condicionales"] = {"sin_efecto": str(exc)}
    return salidas


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


def _a_tick(precio: float, contrato_: dict[str, Any]) -> float:
    """Un precio ajustado al salto que el símbolo acepta.

    SIN ESTO EL STOP NO ENTRA. Medido el 31/8/2026: un stop calculado como
    `precio * 0.95` da 74.783,525 y Binance lo rechaza con -1111 "Precision is
    over the maximum defined for this asset". El número es correcto; lo que
    está mal es que tenga más decimales de los que el símbolo admite.

    Se redondea al TICK y no a los decimales, que son dos límites distintos: en
    BTCUSDT el tick es 0,10 y los decimales son 2, así que 74.783,52 respeta
    los decimales y no respeta el tick. Redondear al tick cumple los dos.

    Al más cercano y no hacia un lado: acá no hay riesgo que se acumule —el
    tick son diez centavos sobre setenta y ocho mil dólares— y sesgarlo correría
    el stop siempre para el mismo lado sin ningún motivo.
    """
    from decimal import ROUND_HALF_UP, Decimal
    tick = Decimal(str(contrato_.get("tick_texto") or "0"))
    n = Decimal(str(precio))
    if tick > 0:
        n = (n / tick).to_integral_value(rounding=ROUND_HALF_UP) * tick
    return float(n)


def abrir(simbolo: str, lado: int, cantidad: float, *,
          api_key: str, secret: str, modo: str,
          precio: float | None = None,
          contrato_: dict[str, Any] | None = None,
          base: str = BASE_PRUEBA) -> dict[str, Any]:
    """Abre a mercado. `lado` es +1 largo, -1 corto.

    EL MODO DECIDE QUE PARAMETRO VA, y por eso es obligatorio en vez de tener
    un valor por omisión: en `cobertura` hay que decir a qué lado va la
    posición, y en `una_via` mandar ese mismo parámetro da -4061. Un valor por
    omisión sería elegir al azar entre andar y fallar.

    `precio` es opcional y sirve para UNA sola cosa: comprobar el mínimo por
    NOCIONAL antes de mandar. Sin él ese control no se puede hacer —una orden a
    mercado no lleva precio— y lo termina haciendo el exchange.
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

    # EL MINIMO POR NOCIONAL, QUE ES OTRO Y SE COMPRUEBA APARTE.
    #
    # Son dos límites distintos y pasar uno no dice nada del otro: en BTCUSDT
    # manda la cantidad —0,001 BTC son 78 USDT contra 50 de nocional— pero en
    # un símbolo barato manda el nocional, y ahí una orden que pasa el control
    # de arriba la rechaza el exchange igual. Es el mismo hueco que apareció en
    # Bybit, donde el nocional manda en seis de los diez símbolos líquidos.
    nocional_min = float(c.get("minimo_nocional") or 0.0)
    if precio and nocional_min and qty * precio < nocional_min:
        raise BinanceError(
            f"La orden ({qty:g} {simbolo} ≈ {qty * precio:,.2f} USDT) no llega "
            f"al mínimo por nocional de {nocional_min:g} USDT. El mínimo por "
            f"cantidad sí lo pasa: son dos límites distintos.")

    p: dict[str, Any] = {"symbol": simbolo, "type": "MARKET", "quantity": qty,
                         "side": "BUY" if lado > 0 else "SELL",
                         # RESULT trae mas que ACK, pero OJO: NO TRAE EL
                         # PRECIO DE EJECUCION. Medido el 31/8/2026 en una
                         # orden a mercado que se lleno entera: `executedQty`
                         # viene bien (0.0007) y `avgPrice` viene en None.
                         # Binance responde antes de agregar los llenados.
                         # Para saber a cuanto entro hay que preguntarlo
                         # despues, con `detalle_orden`.
                         "newOrderRespType": "RESULT"}
    if modo == "cobertura":
        p["positionSide"] = "LONG" if lado > 0 else "SHORT"
    return _pedir("/fapi/v1/order", p, api_key=api_key, secret=secret,
                  metodo="POST", base=base)


def proteger(simbolo: str, lado: int, *, stop: float, objetivo: float,
             api_key: str, secret: str, modo: str,
             contrato_: dict[str, Any] | None = None,
             base: str = BASE_PRUEBA) -> list[dict[str, Any]]:
    """Deja el stop y el objetivo PUESTOS EN EL EXCHANGE.

    ==================================================================
    ESTO ES LO QUE HACE QUE APAGAR LA APLICACION NO DESPROTEJA NADA.
    ==================================================================

    Un bot que vigila su propio stop deja de proteger en el momento en que deja
    de correr — que es justo cuando más falta hace: se cortó la luz, se cerró el
    programa, se suspendió la laptop. Con las órdenes puestas del lado del
    exchange, apagar la aplicación significa que no entra en operaciones nuevas,
    no que la abierta quede a la deriva.

    Son DOS ORDENES SEPARADAS y no parámetros de la de entrada: en futuros de
    Binance el stop y el objetivo se mandan como `STOP_MARKET` y
    `TAKE_PROFIT_MARKET` aparte.

    `closePosition=true` cierra la posición ENTERA al dispararse, y por eso NO
    lleva cantidad —la documentación dice que no se puede usar con `quantity` ni
    con `reduceOnly`—. Es lo que se quiere: si el stop cerrara sólo una parte,
    quedaría la mitad de la posición sin protección y nadie lo miraría.

    `workingType=MARK_PRICE` y no el precio del contrato: el precio de marca es
    el que Binance usa para liquidar, así que es contra el que conviene medir el
    stop. Con el precio del contrato, una mecha en un libro fino puede disparar
    un stop que la liquidación no habría tocado.

    VA POR `/fapi/v1/algoOrder` Y NO POR DONDE VA LA ENTRADA. Desde el cambio
    de Binance del 2025-12-09 las condicionales viven en el Algo Service, y el
    endpoint de siempre las rechaza con -4120. Ver el encabezado del módulo.

    Y EL PRECIO SE LLAMA `triggerPrice`, NO `stopPrice`. Es el mismo número con
    otro nombre: mandarlo con el viejo lo ignora y la orden queda sin disparo.

    EL PRECIO SE AJUSTA AL TICK antes de mandarlo. Un stop calculado como un
    porcentaje del precio casi nunca cae en un múltiplo del tick, y Binance lo
    rechaza con -1111 — que habla de precisión y no dice cuál de los dos
    límites se pasó. Ver `_a_tick`.
    """
    c = contrato_ or contrato(simbolo, base)
    salidas = []
    contraria = "SELL" if lado > 0 else "BUY"
    for tipo, precio in (("STOP_MARKET", stop),
                         ("TAKE_PROFIT_MARKET", objetivo)):
        if not precio or precio != precio:      # None o NaN
            continue
        p: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": simbolo, "side": contraria, "type": tipo,
            "triggerPrice": _a_tick(precio, c), "closePosition": True,
            "workingType": "MARK_PRICE", "priceProtect": True,
        }
        if modo == "cobertura":
            p["positionSide"] = "LONG" if lado > 0 else "SHORT"
        salidas.append(_pedir("/fapi/v1/algoOrder", p, api_key=api_key,
                              secret=secret, metodo="POST", base=base))
    return salidas


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
                         "side": "SELL" if lado_abierto > 0 else "BUY",
                         "newOrderRespType": "RESULT"}
    if modo == "cobertura":
        p["positionSide"] = "LONG" if lado_abierto > 0 else "SHORT"
    else:
        p["reduceOnly"] = True
    return _pedir("/fapi/v1/order", p, api_key=api_key, secret=secret,
                  metodo="POST", base=base)


# ------------------------------------------------------------------- velas

def velas(simbolo: str, intervalo: str = "1h", limite: int = 500,
          base: str = BASE_REAL) -> "Any":
    """Las últimas `limite` velas cerradas.

    ==================================================================
    OJO CON LA BASE: por omisión son las de PRODUCCION, incluso cuando
    se está operando contra el testnet.
    ==================================================================

    MEDIDO el 28/8/2026 en BTCUSDT, la misma vela horaria:

        testnet   O=77.802,5  C=77.877,0  volumen 73.438
        real      O=77.755,8  C=77.877,1  volumen  9.244

    El precio se sigue casi exacto —los cierres coinciden al décimo— pero el
    VOLUMEN difiere ocho veces, porque el del testnet sale de operaciones
    falsas. Y la biblioteca tiene dos indicadores de volumen: una estrategia
    que use alguno decidiría distinto en pruebas que en real, y esa diferencia
    no aparece como error sino como un bot que "en testnet andaba".

    Se pide a producción para que la decisión sea la misma en los dos lados.
    Lo que cambia entre entornos es dónde se ejecuta la orden, no qué se ve.
    """
    import pandas as pd

    d = _pedir("/fapi/v1/klines",
               {"symbol": simbolo, "interval": intervalo, "limit": int(limite)},
               base=base)
    if not d:
        raise BinanceError(f"Binance no devolvió velas de {simbolo} {intervalo}.")
    df = pd.DataFrame(d, columns=[
        "time", "open", "high", "low", "close", "volume", "cierra", "quote",
        "trades", "taker_base", "taker_quote", "ignorar"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype("float64")
    return df.set_index("time")[["open", "high", "low", "close", "volume"]]
