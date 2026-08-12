"""Descarga de velas M1 desde Dukascopy, sin Node.

Antes esto llamaba a `npx dukascopy-node`, y eso funcionaba mientras la
aplicación se corría desde el repositorio en una máquina de desarrollo. Dentro
del .exe no: el paquete no lleva Node, y la mayoría de la gente no lo tiene
instalado. La aplicación se descargaba vacía y su única forma de conseguir
datos fallaba con un error sobre `npx` que a un trader no le dice nada.

Dukascopy publica los datos como archivos por día, comprimidos con LZMA, que es
parte de la biblioteca estándar de Python. No hacía falta Node para nada.

El formato: un archivo por día e instrumento, 1440 registros de 24 bytes —uno
por minuto—, cada uno con el minuto del día, apertura, cierre, mínimo, máximo y
volumen. Los precios son ENTEROS escalados, no decimales: leerlos como float da
ceros, que fue justamente el primer resultado al probarlo.

Los datos van de Dukascopy a la máquina del usuario sin pasar por nuestro
servidor. Eso no es sólo elegante: servir 1,6 GB por usuario sería el gasto más
grande del producto.
"""

from __future__ import annotations

import datetime as dt
import lzma
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterator

import httpx
import pandas as pd

BASE = "https://datafeed.dukascopy.com/datafeed"

#: Cada registro: minuto del día (int32), apertura, cierre, mínimo y máximo
#: (int32 escalados) y volumen (float32).
_REGISTRO = struct.Struct(">5i1f")
_TAM = _REGISTRO.size          # 24 bytes

#: Cuántos decimales usa cada instrumento. No se puede adivinar del dato: 107896
#: es 1,07896 en EURUSD y 107.896 en un índice. Verificado contra precios reales.
ESCALA: dict[str, float] = {
    "eurusd": 1e5,
    "usa500idxusd": 1e3,
    "xauusd": 1e3,
    "btcusd": 1e1,
}
#: Para lo que no está en la tabla. Los pares de divisas son la mayoría del
#: catálogo de Dukascopy y casi todos usan cinco decimales.
ESCALA_POR_DEFECTO = 1e5

#: Bajar quince años son miles de pedidos. Con uno a la vez tarda horas; con
#: demasiados a la vez Dukascopy empieza a cortar conexiones. Doce anda bien y
#: no lo enoja.
CONCURRENCIA = 12
REINTENTOS = 3


class DukascopyError(Exception):
    """No se pudo traer o interpretar el histórico."""


def escala_de(simbolo: str) -> float:
    return ESCALA.get(simbolo.lower(), ESCALA_POR_DEFECTO)


def _url(simbolo: str, dia: dt.date) -> str:
    # El mes va en base 0 en las rutas de Dukascopy: enero es 00. Es la causa
    # clásica de bajar el mes equivocado sin que nada falle.
    return (f"{BASE}/{simbolo.upper()}/{dia.year}/{dia.month - 1:02d}/"
            f"{dia.day:02d}/BID_candles_min_1.bi5")


def _dias(desde: dt.date, hasta: dt.date) -> Iterator[dt.date]:
    d = desde
    while d <= hasta:
        # sábado y domingo no tienen archivo en casi ningún instrumento; se
        # saltan para no gastar miles de pedidos en 404
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def _traer_dia(cliente: httpx.Client, simbolo: str, dia: dt.date) -> tuple[str, bytes]:
    """Devuelve (estado, contenido) con estado en {ok, sin_datos, fallo}.

    La distinción es lo más importante de este módulo. Un feriado no tiene
    archivo y eso es normal; un 503 es Dukascopy diciendo "ahora no puedo".
    Tratarlos igual —que es lo que hacía la primera versión— produce un
    histórico con agujeros que nadie ve: la descarga dice que terminó bien y el
    backtest corre sobre un mercado que se pasó semanas cerrado. Es peor que
    fallar, porque el resultado parece válido.
    """
    url = _url(simbolo, dia)
    espera = 1.0
    for intento in range(REINTENTOS):
        try:
            r = cliente.get(url)
            if r.status_code == 404:
                return "sin_datos", b""
            if r.status_code == 200:
                return ("ok", r.content) if r.content else ("sin_datos", b"")
            # 503 y compañía: Dukascopy limita por IP cuando se le pide mucho
            # seguido. Insistir más rápido lo empeora.
            if intento < REINTENTOS - 1:
                time.sleep(espera)
                espera *= 2
        except (httpx.HTTPError, httpx.StreamError):
            if intento < REINTENTOS - 1:
                time.sleep(espera)
                espera *= 2
    return "fallo", b""


def _filas(crudo: bytes, dia: dt.date, divisor: float) -> list[tuple]:
    if not crudo:
        return []
    try:
        datos = lzma.LZMADecompressor().decompress(crudo)
    except lzma.LZMAError:
        return []
    base = dt.datetime.combine(dia, dt.time.min)
    out = []
    for i in range(len(datos) // _TAM):
        seg, o, c, l, h, vol = _REGISTRO.unpack_from(datos, i * _TAM)
        if o == 0 and h == 0 and l == 0:
            continue                    # minuto sin cotización
        out.append((base + dt.timedelta(seconds=seg),
                    o / divisor, h / divisor, l / divisor, c / divisor, float(vol)))
    return out


def descargar(simbolo: str, desde: str | dt.date, hasta: str | dt.date | None = None,
              progreso: Callable[[float, str], None] | None = None) -> pd.DataFrame:
    """Trae velas M1 y las devuelve ordenadas por tiempo, en UTC."""
    d0 = pd.Timestamp(desde).date() if isinstance(desde, str) else desde
    d1 = (pd.Timestamp(hasta).date() if isinstance(hasta, str)
          else hasta or dt.date.today())
    if d0 > d1:
        raise DukascopyError("la fecha de inicio es posterior a la de fin")

    dias = list(_dias(d0, d1))
    if not dias:
        raise DukascopyError("el rango no contiene ningún día hábil")
    divisor = escala_de(simbolo)
    filas: list[tuple] = []
    hechos = 0

    fallados: list[dt.date] = []
    limites = httpx.Limits(max_connections=CONCURRENCIA,
                           max_keepalive_connections=CONCURRENCIA)
    with httpx.Client(timeout=60.0, limits=limites,
                      headers={"User-Agent": "Botiquant"}) as cliente:
        with ThreadPoolExecutor(max_workers=CONCURRENCIA) as pool:
            # se mantiene el orden de los días para no tener que ordenar 8
            # millones de filas después
            for dia, (estado, crudo) in zip(dias, pool.map(
                    lambda d: _traer_dia(cliente, simbolo, d), dias)):
                if estado == "fallo":
                    fallados.append(dia)
                else:
                    filas.extend(_filas(crudo, dia, divisor))
                hechos += 1
                if progreso and hechos % 25 == 0:
                    progreso(hechos / len(dias),
                             f"{hechos:,} de {len(dias):,} días · "
                             f"{len(filas):,} velas")

    # Se aborta en vez de entregar un histórico incompleto. Un dataset con
    # semanas faltantes no da error en ningún lado: da un backtest con menos
    # operaciones y otras métricas, y nadie se entera nunca.
    if fallados:
        muestra = ", ".join(str(d) for d in fallados[:3])
        raise DukascopyError(
            f"Dukascopy rechazó {len(fallados)} de {len(dias)} días "
            f"(por ejemplo {muestra}). Suele ser un límite temporal por "
            f"cantidad de pedidos: esperá unos minutos y probá de nuevo. "
            f"No se guarda nada a medias.")

    if not filas:
        raise DukascopyError(
            f"Dukascopy no devolvió datos para {simbolo} entre {d0} y {d1}.")

    df = pd.DataFrame(filas, columns=["time", "open", "high", "low", "close", "volume"])
    df = df.set_index("time").sort_index()
    # Un mismo minuto repetido rompe el resampleo y las métricas: pasa en los
    # bordes de horario de verano.
    return df[~df.index.duplicated(keep="first")]
