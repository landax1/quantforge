"""Velas y funding de los perpetuos de Binance.

Es la segunda fuente de datos, al lado de Dukascopy, y existe por una razón
concreta: exportar a MetaTrader es el paso donde se cae la gente. De cuatro
descargas y cinco aperturas de la aplicación, nadie llegó a operar. Un exchange
se conecta con una clave pegada en un campo.

POR QUÉ BINANCE Y NO EL EXCHANGE DONDE SE VA A OPERAR. Medido: BTCUSDT en
Binance y en BingX correlacionan 0,99974 en sus movimientos, con 0,0019% de
diferencia media de precio — cien veces menos que la comisión de una operación.
Y Binance da siete años de historia contra los nueve meses de BingX. Se mina
con los datos buenos y se ejecuta donde la persona tenga cuenta.

EL FUNDING VIAJA APARTE Y NO ES OPCIONAL. Un perpetuo cobra o paga cada ocho
horas por tener la posición abierta. Medido sobre los 7.626 cobros de BTCUSDT
desde septiembre de 2019: media de +0,01061% por cobro, que anualizada da
+11,61%, y negativa sólo el 14,3% del tiempo.

(Acá decía "0,2% anual en Bitcoin". Era falso y lo escribí yo. Queda anotado
porque el número equivocado hacía parecer que la serie no valía la pena.)

Ese 11,61% es lo que costaría estar comprado TODO el año; como sólo se cobra
con la posición abierta, el costo real es la tasa por la exposición y ronda el
1,3% anual en nuestras estrategias.

Pero el signo importa más que el tamaño. Positiva significa que los largos le
pagan a los cortos, y lo fue el 85,7% del tiempo: durante siete años el lado
vendido de Bitcoin COBRÓ 11,61% anual sólo por estar puesto. Sin esta serie el
backtest no sólo subestima un costo — no puede ver esa familia entera.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

import pandas as pd

BASE = "https://fapi.binance.com"

#: Cuántas velas devuelve como máximo cada pedido. Es el límite de la API.
POR_PEDIDO = 1000

#: Pausa entre pedidos. Binance permite mucho más, pero bajar siete años son
#: unos ciento veinte pedidos y no hay apuro: medido, el histórico entero de
#: BTCUSDT en 30 minutos tarda cerca de un minuto igual.
PAUSA = 0.12

#: Los intervalos que entiende la API, mapeados desde los nuestros.
INTERVALOS = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
              "1h": "1h", "4h": "4h", "1d": "1d"}


class BinanceError(RuntimeError):
    """Algo salió mal hablando con Binance, con un texto que se puede mostrar."""


def _pedir(ruta: str, **params: Any) -> Any:
    q = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    url = f"{BASE}{ruta}?{q}" if q else f"{BASE}{ruta}"
    req = urllib.request.Request(url, headers={"User-Agent": "botiquant"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        cuerpo = e.read()[:200].decode(errors="replace")
        if e.code == 451:
            raise BinanceError(
                "Binance no responde desde tu región. Podés seguir usando los "
                "instrumentos de Dukascopy.") from e
        if e.code == 429:
            raise BinanceError(
                "Binance está limitando los pedidos. Esperá un minuto y probá "
                "de nuevo.") from e
        raise BinanceError(f"Binance devolvió {e.code}: {cuerpo}") from e
    except OSError as e:
        raise BinanceError(f"No se pudo conectar con Binance: {e}") from e


def _ms(fecha: str | dt.date | pd.Timestamp) -> int:
    return int(pd.Timestamp(fecha, tz="UTC").timestamp() * 1000)


def descargar(simbolo: str, desde: str | dt.date, hasta: str | dt.date | None = None,
              intervalo: str = "30m",
              progreso: Callable[[float, str], None] | None = None) -> pd.DataFrame:
    """Trae velas de un perpetuo, ordenadas por tiempo y en UTC.

    Devuelve las mismas columnas que el descargador de Dukascopy —open, high,
    low, close, volume con el tiempo de índice— para que el resto de la
    aplicación no tenga que saber de dónde salieron.
    """
    if intervalo not in INTERVALOS:
        raise BinanceError(f"Intervalo no soportado: {intervalo}")

    t0, t1 = _ms(desde), _ms(hasta or dt.date.today())
    if t0 >= t1:
        raise BinanceError("la fecha de inicio es posterior a la de fin")

    filas: list[list] = []
    cursor = t0
    #: Sólo para la barra de progreso; el corte real es que la API deje de
    #: devolver velas, porque el instrumento puede empezar después de `desde`.
    span = max(t1 - t0, 1)

    while cursor < t1:
        lote = _pedir("/fapi/v1/klines", symbol=simbolo,
                      interval=INTERVALOS[intervalo], startTime=cursor,
                      endTime=t1, limit=POR_PEDIDO)
        if not lote:
            break
        filas.extend(lote)
        ultimo = int(lote[-1][0])
        if ultimo <= cursor:            # sin avance: el instrumento se terminó
            break
        cursor = ultimo + 1
        if progreso:
            progreso(min((cursor - t0) / span, 1.0),
                     f"{len(filas):,} velas de {simbolo}")
        if len(lote) < POR_PEDIDO:      # último tramo disponible
            break
        time.sleep(PAUSA)

    if not filas:
        raise BinanceError(
            f"Binance no tiene velas de {simbolo} en ese rango. El contrato "
            "puede ser más nuevo que la fecha pedida.")

    df = pd.DataFrame(
        [(int(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[4]), float(f[5]))
         for f in filas],
        columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df = df.set_index("time").sort_index()
    # La paginación por timestamp puede repetir la vela del borde.
    return df[~df.index.duplicated(keep="first")]


def funding(simbolo: str, desde: str | dt.date,
            hasta: str | dt.date | None = None,
            progreso: Callable[[float, str], None] | None = None) -> pd.Series:
    """La serie histórica de tasas de funding, indexada por el momento de cobro.

    Se guarda aparte de las velas porque tiene su propia frecuencia: se liquida
    cada ocho horas, no en cada barra. El motor la consulta para cargar o
    acreditar a las posiciones que estén abiertas en esos instantes.

    El signo importa tanto como el tamaño. Tasa positiva: los largos le pagan a
    los cortos. Negativa: al revés. Medido sobre el S&P sintético de BingX, la
    tasa negativa equivale a que un comprado COBRE 11% anual sólo por estar
    puesto — más de lo que rinden nuestras estrategias en ese mercado.
    """
    t0, t1 = _ms(desde), _ms(hasta or dt.date.today())
    filas: list[dict] = []
    cursor = t0
    span = max(t1 - t0, 1)

    while cursor < t1:
        lote = _pedir("/fapi/v1/fundingRate", symbol=simbolo,
                      startTime=cursor, endTime=t1, limit=POR_PEDIDO)
        if not lote:
            break
        filas.extend(lote)
        ultimo = int(lote[-1]["fundingTime"])
        if ultimo <= cursor:
            break
        cursor = ultimo + 1
        if progreso:
            progreso(min((cursor - t0) / span, 1.0),
                     f"{len(filas):,} tasas de {simbolo}")
        if len(lote) < POR_PEDIDO:
            break
        time.sleep(PAUSA)

    if not filas:
        return pd.Series(dtype=float, name="funding",
                         index=pd.DatetimeIndex([], tz="UTC", name="time"))

    s = pd.Series(
        [float(f["fundingRate"]) for f in filas],
        index=pd.to_datetime([int(f["fundingTime"]) for f in filas],
                             unit="ms", utc=True),
        name="funding")
    s.index.name = "time"
    return s[~s.index.duplicated(keep="first")].sort_index()


def perpetuos() -> list[dict[str, Any]]:
    """Los contratos perpetuos que se pueden operar, con su precisión.

    Se consulta y no se hardcodea porque la lista cambia: Binance agrega y
    retira pares seguido, y un símbolo que ya no existe da un error feo cuando
    alguien intenta bajarlo.
    """
    info = _pedir("/fapi/v1/exchangeInfo")
    return [
        {"symbol": s["symbol"], "base": s["baseAsset"], "quote": s["quoteAsset"],
         "estado": s.get("status")}
        for s in info.get("symbols", [])
        if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING"
    ]
