"""El spread real de un instrumento, medido en vez de supuesto.

POR QUE EXISTE ESTE ARCHIVO. Cada entrada del catalogo lleva un `spread`, y ese
numero entra en TODOS los backtests de ese instrumento: es lo que se paga en
cada operacion. Hasta ahora los cuatro valores del catalogo venian de afuera y
no habia forma de conseguir el quinto sin inventarlo.

Dukascopy publica BID y ASK por separado, y su endpoint de minutos devuelve el
dia entero en un solo pedido. La diferencia entre los dos ES el spread, minuto
a minuto. No hay que estimarlo.

SE USA LA MEDIANA Y NO EL PROMEDIO. En la apertura y el cierre el spread se
abre varias veces y vuelve; el promedio se lo come entero y devuelve un numero
que nadie paga operando en horario normal.

LO QUE ESTE NUMERO NO ES. No es el spread del broker del usuario. Dukascopy es
un banco con libro institucional y cada broker retail pone el suyo. MEDIDO
sobre los cuatro instrumentos donde conocemos las dos puntas, la razon entre el
spread del catalogo y el de Dukascopy fue:

    EURUSD 4,0x     SP500 0,7x     XAUUSD 0,7x     BTCUSD 0,2x

o sea que NO hay un recargo estable: la razon mas alta es veinticinco veces la
mas baja, y ni siquiera va siempre para el mismo lado. Por eso no se calibra —
se informa el numero medido y de donde sale. Notar que en los tres que no son
divisas, Dukascopy resulto MAS ANCHO que lo que el catalogo asumia, o sea que
usarlo directo peca de caro y no de barato, que es el lado en el que conviene
equivocarse.

(Ese mismo control dejo una pregunta abierta sobre el catalogo actual: asume 12
de spread en el CFD de Bitcoin y Dukascopy cobraba 75,7 con Bitcoin a 25.931.)
"""

from __future__ import annotations

import datetime as dt
import lzma
import statistics
import time
from dataclasses import dataclass

import httpx

from botiquant.data import dukascopy as dk

API = "https://jetta.dukascopy.com/v1/candles/minute"

#: Dias con los que se mide. Tres y de anios distintos: el spread cambia con la
#: volatilidad, y un solo dia agitado da un numero que no representa nada. Son
#: los mismos que usa la consulta de escala, por el mismo motivo — hay
#: combinaciones de instrumento y dia que contestan 429 siempre.
DIAS = ("2023/9/12", "2024/3/6", "2022/11/9")

ESPERA = 4.0


class SpreadDesconocido(Exception):
    """No se pudo medir. Ver el mensaje: el motivo importa."""


#: Dias con los que se mide por el datafeed. Van con fecha real porque ahi el
#: archivo es por dia y no hay forma de pedir "un dia cualquiera".
#:
#: CINCO Y NO TRES. Midiendo el gas, uno de los tres no vino —el archivo BID de
#: ese dia no estaba, el ASK si— y la mediana quedo apoyada en dos. Con cinco,
#: perder uno no cambia nada.
#:
#: Y repartidos en anios, que resulto importar mas de lo que parecia. MEDIDO en
#: GAS.CMD-USD sobre cuatro dias entre 2021 y 2025: el spread en unidades de
#: precio es casi constante —0,0102 a 0,0105— y el porcentaje va de 0,17% a
#: 0,53%, sólo porque el precio del gas fue de 1,94 a 6,12. Midiendo un dia
#: solo se puede sacar cualquiera de esos dos numeros y creer que es el del
#: instrumento.
DIAS_ARCHIVO = (dt.date(2023, 9, 12), dt.date(2024, 3, 6), dt.date(2022, 11, 9),
                dt.date(2021, 6, 15), dt.date(2025, 1, 14))


@dataclass(frozen=True)
class Medicion:
    """Lo medido, con lo que hace falta para poder discutirlo."""

    spread: float
    #: El precio tipico en el momento de medir. Sin esto, "0,053" no se puede
    #: juzgar: hay que saber si es sobre 1,07 o sobre 25.000.
    precio: float
    minutos: int
    dias: tuple[str, ...]

    #: De donde salio. Importa al leer el numero: son dos servidores distintos
    #: de la misma casa y no siempre tienen lo mismo.
    fuente: str = "api"

    @property
    def pct(self) -> float:
        """El spread como porcentaje del precio, que es lo comparable."""
        return 100.0 * self.spread / self.precio if self.precio else 0.0


def _un_dia(codigo: str, fecha: str, lado: str,
            cliente: httpx.Client) -> dict[int, float] | None:
    """Los cierres de un dia, ya en precio.

    El formato de Dukascopy NO son precios: `closes` viene como diferencias
    acumuladas contra la vela anterior, en unidades de 1/multiplier. Leerlo
    como precio da numeros absurdos.
    """
    r = cliente.get(f"{API}/{codigo}/{lado}/{fecha}")
    if r.status_code != 200:
        return None
    d = r.json()
    mult = float(d.get("multiplier") or 0.0)
    if not 0.0 < mult <= 1.0:
        return None
    t = 0
    c = round(float(d["close"]) / mult)
    fuera: dict[int, float] = {}
    for i, (dt_, dc) in enumerate(zip(d["times"], d["closes"])):
        t += dt_
        if i:
            c += dc
        fuera[t] = c * mult
    return fuera


def medir(codigo_api: str, dias: tuple[str, ...] = DIAS,
          espera: float = ESPERA) -> Medicion:
    """El spread de ese instrumento, o levanta explicando por que no.

    `codigo_api` es el nombre de la API de Dukascopy — "LIGHT.CMD-USD".

    LEVANTA EN VEZ DE DEVOLVER UN NUMERO FLOJO. Un spread inventado no falla:
    el backtest corre y cobra un costo que no es el que se paga. Si no se puede
    medir, el instrumento no esta listo para el catalogo, y eso es una
    respuesta valida.
    """
    if not codigo_api:
        raise SpreadDesconocido("hace falta el código de API del instrumento")

    difs: list[float] = []
    precios: list[float] = []
    sin_ask = 0
    with httpx.Client(timeout=40.0) as c:
        for i, fecha in enumerate(dias):
            if i:
                time.sleep(espera)
            bid = _un_dia(codigo_api, fecha, "BID", c)
            time.sleep(espera)
            ask = _un_dia(codigo_api, fecha, "ASK", c)
            if bid and not ask:
                sin_ask += 1
            if not bid or not ask:
                continue
            for k in bid.keys() & ask.keys():
                if ask[k] > bid[k] > 0:
                    difs.append(ask[k] - bid[k])
                    precios.append(bid[k])

    if not difs:
        # Se distingue el caso porque son problemas distintos: si hay BID y no
        # hay ASK, no es un límite temporal ni una fecha mal elegida — ese
        # instrumento no publica ASK acá y hay que medirlo por otro lado.
        # Medido en GAS.CMD-USD: diez fechas, diez veces BID sí y ASK no.
        if sin_ask:
            raise SpreadDesconocido(
                f"{codigo_api} publica BID pero no ASK en esta API "
                f"({sin_ask} de {len(dias)} días), así que el spread no se "
                f"puede medir por acá. Hay que bajarlo del datafeed de "
                f"archivos, que sí tiene los dos lados.")
        raise SpreadDesconocido(
            f"no se pudo traer BID y ASK de {codigo_api} en ninguna de las "
            f"fechas probadas. Dukascopy contesta 429 de forma permanente "
            f"para ciertas combinaciones de instrumento y día.")

    return Medicion(spread=statistics.median(difs),
                    precio=statistics.median(precios),
                    minutos=len(difs), dias=tuple(dias))


# ---------------------------------------------------------------------------
# El segundo camino: los archivos por dia
# ---------------------------------------------------------------------------
#
# EXISTE POR UN CASO CONCRETO. GAS.CMD-USD publica BID y no ASK en la API de
# arriba —diez fechas probadas, diez veces igual— asi que su spread no se puede
# medir por ahi. El datafeed de archivos, que es de la misma casa y otro
# servidor, si tiene los dos lados.
#
# No es el camino por defecto porque cuesta mas: un archivo por dia y por lado,
# contra un pedido que trae el dia entero. Se usa cuando el primero no puede.


def _dia_archivo(simbolo: str, dia: dt.date, lado: str,
                 escala: float, cliente: httpx.Client) -> dict[int, float] | None:
    url = (f"{dk.BASE}/{simbolo.upper()}/{dia.year}/{dia.month - 1:02d}/"
           f"{dia.day:02d}/{lado}_candles_min_1.bi5")
    try:
        r = cliente.get(url)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or not r.content:
        return None
    crudo = lzma.LZMADecompressor().decompress(r.content)
    fuera: dict[int, float] = {}
    for i in range(0, len(crudo) - dk._TAM + 1, dk._TAM):
        minuto, apertura, cierre, _, _, _ = dk._REGISTRO.unpack_from(crudo, i)
        if apertura:            # los minutos sin cotizacion vienen en cero
            fuera[minuto] = cierre / escala
    return fuera


def medir_desde_archivos(simbolo: str, escala: float,
                         dias: tuple[dt.date, ...] = DIAS_ARCHIVO) -> Medicion:
    """El spread leyendo los archivos por dia, con los dos lados.

    `simbolo` es el nombre de la ruta del datafeed —"gascmdusd"— y no el de la
    API. `escala` la da `dukascopy.escala_de`.
    """
    difs: list[float] = []
    precios: list[float] = []
    with httpx.Client(timeout=40.0) as c:
        for dia in dias:
            bid = _dia_archivo(simbolo, dia, "BID", escala, c)
            ask = _dia_archivo(simbolo, dia, "ASK", escala, c)
            if not bid or not ask:
                continue
            for k in bid.keys() & ask.keys():
                if ask[k] > bid[k] > 0:
                    difs.append(ask[k] - bid[k])
                    precios.append(bid[k])

    if not difs:
        raise SpreadDesconocido(
            f"tampoco se pudo medir {simbolo} desde los archivos por día.")

    return Medicion(spread=statistics.median(difs),
                    precio=statistics.median(precios),
                    minutos=len(difs),
                    dias=tuple(d.isoformat() for d in dias),
                    fuente="archivos")
