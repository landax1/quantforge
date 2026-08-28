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
#: es 1,07896 en EURUSD y 107.896 en un índice.
#:
#: Los cuatro de acá se verificaron a mano contra precios reales. Sirven de
#: red: si la consulta a Dukascopy falla, estos siguen andando sin internet
#: extra. Y de prueba: las cuatro coinciden con lo que devuelve la API, que es
#: como se comprobó que la API dice la verdad.
ESCALA: dict[str, float] = {
    "eurusd": 1e5,
    "usa500idxusd": 1e3,
    "xauusd": 1e3,
    "btcusd": 1e1,
}

#: NO HAY VALOR POR DEFECTO, y esa ausencia es la decisión importante de este
#: módulo.
#:
#: Tener uno es cómodo y silencioso: un instrumento que caiga ahí y no sea un
#: par de divisas se baja con los precios divididos por cien —el Dow a 387 en
#: vez de 38.700— y NO falla nada. El backtest corre, las métricas salen, y son
#: de un mercado que no existe. Medido: de siete instrumentos probados fuera de
#: la tabla, SEIS necesitaban 1e3 y sólo GBPUSD 1e5, así que adivinar acierta
#: una de cada siete veces.
#:
#: Sin datos se puede vivir. Con datos equivocados que parecen buenos, no.

#: De dónde se consulta el multiplicador de un instrumento. Dukascopy lo
#: publica junto con las velas de su API JSON, así que no hay que mantener una
#: tabla de mil quinientas filas que se desactualiza sola.
API_VELAS = "https://jetta.dukascopy.com/v1/candles/minute"

#: Lo consultado en esta sesión. Un instrumento se pregunta una vez y no en
#: cada uno de los miles de días que se bajan.
_ESCALAS_VISTAS: dict[str, float] = {}

#: Bajar quince años son miles de pedidos. Con uno a la vez tarda horas; con
#: demasiados a la vez Dukascopy empieza a cortar conexiones. Doce anda bien y
#: no lo enoja.
CONCURRENCIA = 12
REINTENTOS = 3

#: La escala se reintenta MAS veces y esperando MAS que un dia de velas, y la
#: asimetria es a proposito.
#:
#: Un dia es uno de miles: si insiste demasiado, bajar quince anios pasa de
#: minutos a horas. La escala se pregunta UNA vez por instrumento en toda la
#: vida del programa, asi que esperar medio minuto no le cuesta nada a nadie
#: — y si no la consigue, el instrumento entero no se puede bajar.
#:
#: MEDIDO: probando doce instrumentos seguidos con la espera corta, SEIS
#: fallaron por limite de pedidos. Con esta espera el limite se atraviesa.
REINTENTOS_ESCALA = 5
ESPERA_ESCALA = 2.0


class DukascopyError(Exception):
    """No se pudo traer o interpretar el histórico."""


def consultar_escala(codigo: str) -> float | None:
    """El multiplicador que Dukascopy declara para ese instrumento.

    `codigo` es el nombre de su API —"USA30.IDX-USD"— y no el de la ruta del
    datafeed. Devuelve None si no se pudo averiguar; quien llama decide qué
    hacer con eso, porque acá no se puede saber si vale la pena arriesgarse.

    Se pregunta en vez de mantener una tabla porque el catálogo de Dukascopy
    tiene mil quinientos instrumentos y una tabla propia se desactualiza sola.
    Verificado contra los cuatro que ya estaban medidos a mano: los cuatro
    coinciden.
    """
    if not codigo:
        return None
    # Un día cualquiera de mercado abierto. Sólo interesa el multiplicador, que
    # es del instrumento y no del día.
    url = f"{API_VELAS}/{codigo}/BID/2024/6/3"
    espera = ESPERA_ESCALA
    for intento in range(REINTENTOS_ESCALA):
        try:
            with httpx.Client(timeout=15.0) as c:
                r = c.get(url)
            if r.status_code == 200:
                m = float(r.json().get("multiplier") or 0.0)
                return 1.0 / m if 0.0 < m <= 1.0 else None
            # 429 es lo habitual pidiendo varios seguidos, y es el caso que
            # importa: sin reintentar, agregar cinco instrumentos de una vez
            # dejaba a la mitad sin escala.
            if r.status_code in (429, 503) and intento < REINTENTOS_ESCALA - 1:
                time.sleep(espera)
                espera *= 2
                continue
            return None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            if intento < REINTENTOS_ESCALA - 1:
                time.sleep(espera)
                espera *= 2
                continue
            return None
    return None


def escala_de(simbolo: str, codigo_api: str = "") -> float:
    """La escala de este instrumento, o se niega a adivinarla.

    El orden importa. La tabla primero porque esos cuatro están verificados a
    mano y no queremos que una consulta que falla cambie el resultado de los
    instrumentos que la aplicación viene bajando desde siempre.

    Si no está en la tabla y no se pudo consultar, LEVANTA en vez de suponer.
    Bajar con la escala equivocada produce un histórico que parece bueno y es
    de otro mercado: el backtest corre, las métricas salen, y todo lo que se
    decida encima está mal. Un error acá se lee y se arregla; ese silencio no.
    """
    clave = simbolo.lower()
    if clave in ESCALA:
        return ESCALA[clave]
    if clave in _ESCALAS_VISTAS:
        return _ESCALAS_VISTAS[clave]

    consultada = consultar_escala(codigo_api)
    if consultada is not None:
        _ESCALAS_VISTAS[clave] = consultada
        return consultada

    raise DukascopyError(
        f"No se pudo averiguar la escala de precios de {simbolo}. Sin ese dato "
        f"los precios saldrían divididos o multiplicados por cien y el "
        f"histórico parecería correcto igual, así que no se baja. "
        f"Probá de nuevo en un minuto: Dukascopy limita las consultas seguidas.")


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
              progreso: Callable[[float, str], None] | None = None,
              codigo_api: str = "") -> pd.DataFrame:
    """Trae velas M1 y las devuelve ordenadas por tiempo, en UTC.

    `codigo_api` es el nombre del instrumento en la API de Dukascopy —
    "USA30.IDX-USD"— y hace falta para averiguar la escala de precios de todo
    lo que no esté en la tabla verificada a mano. Sin él, un instrumento nuevo
    NO se baja, porque bajarlo con la escala equivocada da un histórico que
    parece bueno y es de otro mercado.
    """
    d0 = pd.Timestamp(desde).date() if isinstance(desde, str) else desde
    d1 = (pd.Timestamp(hasta).date() if isinstance(hasta, str)
          else hasta or dt.date.today())
    if d0 > d1:
        raise DukascopyError("la fecha de inicio es posterior a la de fin")

    dias = list(_dias(d0, d1))
    if not dias:
        raise DukascopyError("el rango no contiene ningún día hábil")
    # ANTES de bajar nada. Averiguarlo al final significaria descargar quince
    # anios y recien ahi descubrir que no se puede interpretar el precio.
    divisor = escala_de(simbolo, codigo_api)
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
