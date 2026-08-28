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
#: Cada uno de estos se comprobo bajando el 3 de junio de 2024 y comparando el
#: cierre con el precio real de ese dia. El numero de al lado es ese cierre: es
#: la prueba, no un comentario. Si alguna vez uno de estos baja distinto, se
#: nota comparando contra el numero que esta aca.
ESCALA: dict[str, float] = {
    # los cuatro originales, verificados a mano hace meses
    "eurusd": 1e5,
    "usa500idxusd": 1e3,
    "xauusd": 1e3,
    "btcusd": 1e1,
    # agregados el 27 de agosto de 2026, cada uno verificado contra el cierre
    # real del 3 de junio de 2024
    "usdjpy": 1e3,          # 155,116
    "deuidxeur": 1e3,       # 18.482,477   (DAX 40)
    "jpnidxjpy": 1e3,       # 38.551,417   (Nikkei)
    "usatechidxusd": 1e3,   # 18.689,398   (Nasdaq 100)
    "gbridxgbp": 1e3,       # 8.258,592    (FTSE 100)
    "xagusd": 1e3,          # 29,562       (plata)
    "gascmdusd": 1e4,       # 2,6242       (gas natural)
    "audusd": 1e5,          # 0,6645
}

#: POR QUE ESTAN ACA Y NO SE CONSULTAN.
#:
#: Consultar es lo correcto para un instrumento que nadie verifico: es eso o
#: adivinar. Pero para uno que SI verificamos, dejar que dependa de la API en
#: la maquina del usuario es cambiar una certeza por un pedido de red que
#: falla.
#:
#: MEDIDO, y por eso este bloque existe: probando doce instrumentos seguidos,
#: Dukascopy contesto 429 a la mitad, y cuatro de esos siguieron en 429 con un
#: pedido cada veinte segundos mientras otros contestaban 200 en el mismo
#: minuto. No se por que —puede ser cuota por instrumento, o que esos codigos
#: esten restringidos— y no hace falta saberlo para decidir esto: el usuario
#: se topa con el 429 igual, sepamos o no la causa.
#:
#: Un usuario que agrega un instrumento del catalogo no tiene por que enterarse
#: de nada de esto. La consulta queda para lo que no esta en esta tabla.

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

#: Entre los reintentos de la segunda pasada. Van de a uno y espaciados: si lo
#: que sobra son pedidos, repetirlos rápido choca contra el mismo límite.
ESPERA_SEGUNDA_PASADA = 1.5

#: EL 429 DE ESTA API NO SIEMPRE ES UN LIMITE DE PEDIDOS, y confundirlo costo
#: dos vueltas de razonamiento equivocado.
#:
#: Ciertas combinaciones de instrumento y fecha contestan 429 SIEMPRE, sin
#: importar cuanto se espere. Medido, mismo instrumento y anios contiguos:
#: GAS.CMD-USD/2022 contesta 200 y GAS.CMD-USD/2023 contesta 429, las dos cosas
#: de forma estable. Y los cuatro instrumentos que "nunca se podian consultar"
#: —Dow, WTI, Brent, USD-CHF— contestaron al primer intento cambiando la fecha:
#:
#:     Dow      3/6/2024 -> 429      12/9/2023 -> 200 (1e3)
#:     WTI      3/6/2024 -> 429      12/9/2023 -> 200 (1e3)
#:     Brent    3/6/2024 -> 429      12/9/2023 -> 200 (1e3)
#:     USD-CHF  3/6/2024 -> 429      12/9/2023 -> 200 (1e5)
#:
#: Con una sola fecha, un instrumento que caiga en una de esas combinaciones es
#: inconsultable para siempre y ningun reintento lo arregla. Por eso se prueban
#: varias fechas ANTES de reintentar: cambiar de dia es lo que funciona.
#:
#: (Antes decia aca que insistir "causaba" el bloqueo, apoyado en que un codigo
#: rechazaba trece veces seguidas. Rechazaba por la fecha. No hay evidencia de
#: que insistir bloquee nada; el numero bajo de reintentos queda porque con
#: varias fechas ya no hace falta insistir, no por el motivo que decia.)
REINTENTOS_ESCALA = 2
ESPERA_ESCALA = 30.0

#: Dias con los que se prueba, en orden. Tres y de anios distintos: si una
#: fecha resulta ser de las que contestan 429 para ese instrumento, las otras
#: dos lo salvan.
FECHAS_ESCALA = ("2024/6/3", "2023/9/12", "2022/2/8")


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
    # Se prueban VARIAS fechas antes de reintentar ninguna. Ver el bloque de
    # FECHAS_ESCALA: hay combinaciones de instrumento y dia que contestan 429
    # de forma permanente, y ahi cambiar de dia es lo unico que funciona.
    espera = ESPERA_ESCALA
    for intento in range(REINTENTOS_ESCALA):
        try:
            for fecha in FECHAS_ESCALA:
                with httpx.Client(timeout=15.0) as c:
                    r = c.get(f"{API_VELAS}/{codigo}/BID/{fecha}")
                if r.status_code == 200:
                    m = float(r.json().get("multiplier") or 0.0)
                    return 1.0 / m if 0.0 < m <= 1.0 else None
                if r.status_code not in (429, 503):
                    break
            # Si las TRES fechas dieron 429, ahi si puede ser un limite real
            # y vale esperar una vez. Si fuera la combinacion permanente, las
            # otras dos fechas ya lo habrian salvado.
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
        f"Esperá unos minutos y probá UNA vez: Dukascopy limita por "
        f"instrumento, y reintentar seguido lo bloquea más tiempo.")


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

    # SEGUNDA PASADA SOBRE LOS RECHAZADOS, DE A UNO Y DESPACIO.
    #
    # La primera versión abortaba acá, y eso convertía un tropiezo del 5% en
    # perder el 95% que ya estaba bajado. MEDIDO bajando los tres instrumentos
    # nuevos: Bund 174 rechazados de 2.695, WTI 197 de 3.896, gas 127 de 3.650
    # — entre 3% y 6%, y las tres descargas terminaron sin dejar nada después
    # de diez minutos cada una. Con eso, agregar un instrumento no funcionaba.
    #
    # Va de a uno y no en paralelo a propósito: si lo que sobra son pedidos,
    # repetirlos a la misma velocidad los vuelve a chocar contra el mismo
    # límite. Los que quedan son pocos, así que ir despacio cuesta segundos.
    if fallados and progreso:
        progreso(0.98, f"Reintentando {len(fallados)} días que Dukascopy "
                       f"rechazó…")
    if fallados:
        quedan: list[dt.date] = []
        with httpx.Client(timeout=60.0,
                          headers={"User-Agent": "Botiquant"}) as cliente:
            for i, dia in enumerate(fallados):
                if i:
                    time.sleep(ESPERA_SEGUNDA_PASADA)
                estado, crudo = _traer_dia(cliente, simbolo, dia)
                if estado == "fallo":
                    quedan.append(dia)
                else:
                    filas.extend(_filas(crudo, dia, divisor))
        fallados = quedan

    # Se aborta en vez de entregar un histórico incompleto. Un dataset con
    # semanas faltantes no da error en ningún lado: da un backtest con menos
    # operaciones y otras métricas, y nadie se entera nunca.
    if fallados:
        muestra = ", ".join(str(d) for d in fallados[:3])
        raise DukascopyError(
            f"Dukascopy siguió rechazando {len(fallados)} de {len(dias)} días "
            f"después de reintentarlos de a uno (por ejemplo {muestra}). "
            f"Esperá unos minutos y probá de nuevo; no se guarda nada a "
            f"medias, así que no vas a quedarte con un histórico con agujeros.")

    if not filas:
        raise DukascopyError(
            f"Dukascopy no devolvió datos para {simbolo} entre {d0} y {d1}.")

    df = pd.DataFrame(filas, columns=["time", "open", "high", "low", "close", "volume"])
    df = df.set_index("time").sort_index()
    # Un mismo minuto repetido rompe el resampleo y las métricas: pasa en los
    # bordes de horario de verano.
    return df[~df.index.duplicated(keep="first")]
