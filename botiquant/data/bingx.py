"""El cliente de BingX: velas, contratos, y lo que hace falta para operar.

Es el exchange donde se ejecuta, y no el mismo de donde salen los datos del
backtest. Ver `binance.py` para el por qué: Binance tiene siete años de
historia contra los nueve meses de BingX, y los dos precios correlacionan
0,99974. Se mina con los datos buenos y se opera donde la persona tenga cuenta.

ESTE MÓDULO NO MANDA ÓRDENES. Sólo lee. La ejecución va aparte, a propósito:
todo lo que se puede probar sin arriesgar un peso vive acá, y lo que mueve
plata queda separado y con su propio candado.

LO QUE LA DOCUMENTACIÓN DICE MAL. Medido contra la API real el 26 de agosto de
2026, porque las cuatro cosas se descubren tarde y caro:

  * El máximo de velas es 1.000, no 1.440. Pedir 1.440 devuelve 1.000 SIN
    avisar, y pedir 2.000 devuelve una lista VACÍA — no un error, vacío. Un
    cliente que confíe en el número documentado se queda sin datos y cree que
    el instrumento no existe.
  * Las velas vienen como objetos con nombre, no como el array posicional
    `[openTime, open, high, low, close, volume, closeTime]` que figura en la
    referencia.
  * Vienen de la MÁS NUEVA a la más vieja. Usarlas sin ordenar da indicadores
    calculados sobre el pasado invertido, que es el peor error posible: no
    falla, miente.
  * `startTime`/`endTime` funcionan aunque no estén documentados en v3.

BINGX CONTESTA 200 CON EL ERROR ADENTRO. El código HTTP no alcanza para saber
si salió bien: el cuerpo trae `{"code": N, "msg": ...}` y un `code` distinto
de cero es un fracaso con cara de éxito.

LA CLAVE DE API. Los datos de mercado son públicos y no la necesitan. Para el
saldo y las posiciones la firma se arma acá, pero la clave la provee quien
llama: este archivo no la lee de ningún lado, no la guarda y no la registra.
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

import pandas as pd

BASE = "https://open-api.bingx.com"

#: Medido, no documentado: el techo real son 1.000 velas por pedido.
POR_PEDIDO = 1000

#: Los intervalos que acepta, con los mismos nombres que usamos adentro.
INTERVALOS = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")


class BingXError(RuntimeError):
    """Algo salió mal hablando con BingX, con un texto que se puede mostrar.

    Cuando el rechazo viene del exchange, `codigo` y `mensaje` traen sus dos
    campos por separado. Sirve para mostrarlos sin envolverlos en una frase
    nuestra: la interfaz está en dos idiomas y el texto de BingX viene en
    inglés siempre, así que una frase en español alrededor de un mensaje en
    inglés queda mal en los dos.
    """

    def __init__(self, texto: str, codigo: int | None = None,
                 mensaje: str = "") -> None:
        super().__init__(texto)
        self.codigo = codigo
        self.mensaje = mensaje

    @property
    def del_exchange(self) -> str:
        """El rechazo tal como lo dijo BingX, sin envoltorio."""
        if self.codigo is None:
            return str(self)
        return f"[{self.codigo}] {self.mensaje or '—'}"


#: Los caracteres que no pueden aparecer en el valor de un parámetro. Romperían
#: la query que se firma, y una firma sobre una query distinta de la que se
#: manda es un rechazo con un mensaje que no explica nada.
_PROHIBIDOS = ("&", "=", "?", "#", "\r", "\n")


def _valor(v: Any) -> str:
    """Un parámetro como texto, listo para firmar.

    Los diccionarios van como JSON compacto y NO como su `str()` de Python:
    `str({"a": 1})` da `{'a': 1}` con comillas simples, que no es JSON y BingX
    rechaza. Es la forma más fácil de romper `stopLoss` sin darse cuenta.
    """
    if isinstance(v, dict):
        return json.dumps(v, separators=(",", ":"))
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _pedir(ruta: str, params: dict[str, Any] | None = None,
           api_key: str = "", secret: str = "", metodo: str = "GET") -> Any:
    """Un pedido a la API, firmado si le dan credenciales.

    TRES COSAS QUE HAY QUE HACER EXACTAMENTE ASÍ, contrastadas contra la
    referencia oficial de BingX. Las tres las tenía mal y ninguna avisa: el
    exchange contesta "clave incorrecta", que manda a revisar la clave.

    1. LOS PARÁMETROS SE ORDENAN ALFABÉTICAMENTE ANTES DE FIRMAR. Firmar en el
       orden en que uno los escribió produce una firma válida sobre un texto
       que el servidor arma distinto, y no coincide nunca.
    2. UN POST MANDA LOS PARÁMETROS EN EL CUERPO, no en la URL, con
       `application/x-www-form-urlencoded`. En la URL el servidor no los ve.
    3. NO SE URL-ENCODEA lo que se firma. La firma va sobre el texto crudo
       `clave=valor&clave=valor`; escapar las llaves de un `stopLoss` cambia el
       texto y rompe la firma.

    El secreto NO viaja a ningún lado: se usa para firmar y no sale de acá.
    """
    p = dict(params or {})
    headers = {"User-Agent": "botiquant"}

    for k, v in p.items():
        txt = _valor(v)
        if any(c in txt for c in _PROHIBIDOS):
            raise BingXError(
                f"El parámetro {k} tiene un caracter que rompería la firma.")

    if api_key and secret:
        # `timestamp` es obligatorio en los endpoints firmados y tiene que ir
        # ADENTRO de lo que se firma, no agregado después.
        p.setdefault("timestamp", int(time.time() * 1000))
        query = "&".join(f"{k}={_valor(p[k])}" for k in sorted(p))
        firma = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        query = f"{query}&signature={firma}"
        headers["X-BX-APIKEY"] = api_key
    else:
        query = "&".join(f"{k}={_valor(p[k])}" for k in sorted(p))

    cuerpo_pedido = None
    if metodo == "POST":
        url = f"{BASE}{ruta}"
        cuerpo_pedido = query.encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        url = f"{BASE}{ruta}?{query}" if query else f"{BASE}{ruta}"

    req = urllib.request.Request(url, data=cuerpo_pedido, headers=headers,
                                 method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            cuerpo = json.load(r)
    except urllib.error.HTTPError as e:
        detalle = e.read()[:200].decode(errors="replace")
        raise BingXError(f"BingX devolvió {e.code}: {detalle}") from e
    except OSError as e:
        raise BingXError(f"No se pudo conectar con BingX: {e}") from e

    # El error viene adentro de una respuesta 200: sin esto, un rechazo se
    # confunde con un resultado vacío y el runner sigue como si nada.
    if isinstance(cuerpo, dict) and cuerpo.get("code") not in (0, None):
        raise BingXError(
            f"BingX rechazó el pedido ({cuerpo.get('code')}): "
            f"{cuerpo.get('msg') or 'sin detalle'}",
            codigo=cuerpo.get("code"), mensaje=str(cuerpo.get("msg") or ""))
    return cuerpo.get("data") if isinstance(cuerpo, dict) else cuerpo


def velas(simbolo: str, intervalo: str = "1h", limite: int = POR_PEDIDO,
          desde: int | None = None, hasta: int | None = None) -> pd.DataFrame:
    """Velas de un perpetuo, ORDENADAS DE VIEJA A NUEVA y en UTC.

    Devuelve las mismas columnas que el descargador de Binance —open, high,
    low, close, volume con el tiempo de índice— para que el motor no tenga que
    saber de dónde salieron.
    """
    if intervalo not in INTERVALOS:
        raise BingXError(f"Intervalo no soportado: {intervalo}")
    # Se acota acá y no se confía en el servidor: pedir de más devuelve VACÍO,
    # y un vacío silencioso se confunde con "el instrumento no existe".
    limite = max(1, min(int(limite), POR_PEDIDO))

    params: dict[str, Any] = {"symbol": simbolo, "interval": intervalo,
                              "limit": limite}
    if desde is not None:
        params["startTime"] = int(desde)
    if hasta is not None:
        params["endTime"] = int(hasta)

    filas = _pedir("/openApi/swap/v3/quote/klines", params) or []
    if not filas:
        raise BingXError(
            f"BingX no devolvió velas de {simbolo}. Revisá que el símbolo lleve "
            f"guion (BTC-USDT, no BTCUSDT) y que el contrato exista.")

    df = pd.DataFrame([{
        "time": pd.to_datetime(int(f["time"]), unit="ms", utc=True),
        "open": float(f["open"]), "high": float(f["high"]),
        "low": float(f["low"]), "close": float(f["close"]),
        "volume": float(f["volume"]),
    } for f in filas]).set_index("time")

    df = df.sort_index()
    return df[~df.index.duplicated(keep="last")]


def contrato(simbolo: str) -> dict[str, Any]:
    """La ficha del contrato: precisión, mínimos y comisiones.

    Hace falta antes de mandar cualquier orden. El mínimo de BTC-USDT es
    0,0001 y la cantidad admite 4 decimales; una orden con más decimales la
    rechaza el exchange, y una por debajo del mínimo también.
    """
    todos = _pedir("/openApi/swap/v2/quote/contracts") or []
    for c in todos:
        if str(c.get("symbol", "")).upper() == simbolo.upper():
            return c
    raise BingXError(f"BingX no lista el contrato {simbolo}.")


def funding_actual(simbolo: str) -> dict[str, Any]:
    """La tasa vigente y cuándo se cobra la próxima.

    Es el dato de AHORA, no la serie histórica: para minar se usa la de
    Binance, que llega hasta 2019. Ésta sirve en vivo, para saber cuánto va a
    costar —o pagar— mantener la posición abierta hasta el próximo cobro.
    """
    d = _pedir("/openApi/swap/v2/quote/premiumIndex", {"symbol": simbolo}) or {}
    return {
        "tasa": float(d.get("lastFundingRate") or 0.0),
        "precio_marca": float(d.get("markPrice") or 0.0),
        "proximo_cobro": int(d.get("nextFundingTime") or 0),
        "cada_horas": int(d.get("fundingIntervalHours") or 8),
    }


def modo_cobertura(api_key: str, secret: str) -> bool:
    """¿La cuenta está en modo cobertura (hedge) o en modo simple (one-way)?

    Decide el valor de `positionSide` en cada orden: LONG/SHORT en cobertura,
    BOTH en modo simple. Mandar el equivocado hace que el exchange rechace la
    orden, y el mensaje no dice que el problema sea éste.

    Se PREGUNTA en vez de asumir. Es una preferencia de la cuenta que el
    usuario pudo cambiar desde la aplicación del exchange hace seis meses, y
    asumir una de las dos deja a la mitad de la gente sin poder operar.
    """
    d = _pedir("/openApi/swap/v1/positionSide/dual",
               api_key=api_key, secret=secret) or {}
    return str(d.get("dualSidePosition", "")).lower() == "true"


def saldo(api_key: str, secret: str) -> dict[str, Any]:
    """El saldo de la cuenta de perpetuos. Pide clave, sólo lectura.

    Es lo primero que conviene probar con una clave nueva: si esto contesta,
    la clave y la firma están bien, y se comprobó sin tocar una orden.
    """
    d = _pedir("/openApi/swap/v2/user/balance", api_key=api_key, secret=secret)
    b = (d or {}).get("balance", d) or {}
    return {"moneda": b.get("asset", ""),
            "saldo": float(b.get("balance") or 0.0),
            "disponible": float(b.get("availableMargin") or 0.0),
            "no_realizado": float(b.get("unrealizedProfit") or 0.0)}


def posiciones(api_key: str, secret: str,
               simbolo: str = "") -> list[dict[str, Any]]:
    """Las posiciones abiertas. Pide clave, sólo lectura.

    El runner la consulta antes de cada decisión: lo que importa no es lo que
    él CREE tener abierto sino lo que el exchange dice que hay. Si se cortó la
    luz a mitad de una operación, la verdad está de este lado.
    """
    params = {"symbol": simbolo} if simbolo else {}
    d = _pedir("/openApi/swap/v2/user/positions", params,
               api_key=api_key, secret=secret) or []
    return [{"simbolo": p.get("symbol", ""),
             "lado": str(p.get("positionSide", "")).lower(),
             "cantidad": float(p.get("positionAmt") or 0.0),
             "precio_entrada": float(p.get("avgPrice") or 0.0),
             "no_realizado": float(p.get("unrealizedProfit") or 0.0)}
            for p in d]
