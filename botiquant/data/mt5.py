"""Velas del MetaTrader que el usuario ya tiene instalado.

POR QUE EXISTE. Dukascopy nos limita: bajando los tres instrumentos nuevos
rechazó entre el 3% y el 6% de los días de cada uno, y las tres descargas
terminaron sin dejar nada después de diez minutos. Los datos de MetaTrader ya
están en el disco del usuario, no hay límite de pedidos, y vienen como precios
decimales — sin la escala entera que produce históricos divididos por cien.

LO QUE ESTA FUENTE TRAE Y LO QUE NO. Medido sobre MetaQuotes-Demo, que es el
servidor que viene con cualquier MetaTrader 5:

    Forex     126 pares
    Indexes    26 (US500, JPN225, FRA40, ESP35, UK100, HK50, AUS200…)
    Metals     10 (oro, plata, platino, paladio)
    Nasdaq  ~12.000 acciones y ETF

No hay energía, ni bonos, ni CFD de cripto. Así que ESTO NO REEMPLAZA A
DUKASCOPY: el gas, el petróleo, el Bund y el CFD de Bitcoin siguen viniendo de
allá. Es una fuente más, no la única.

Y la profundidad depende de la temporalidad: ~8 años en H1 y sólo unos 3 meses
en M1. Para minar en una hora sobra; para 15 minutos no alcanza.

======================================================================
EL RELOJ ES LA PARTE PELIGROSA, y es el motivo de que este módulo mida en
vez de suponer.
======================================================================

Las velas de Dukascopy vienen en UTC y la aplicación les suma un ajuste para
aproximar el reloj del broker. Las de MetaTrader vienen YA en la hora del
servidor de donde se bajaron — y ese reloj no es el mismo para todos: medido,
MetaQuotes-Demo corre en UTC+3.

ESE NUMERO SE MIDIO DESPUES DE DEDUCIRLO MAL. Mirando una vela horaria parecía
UTC: la última decía 15:00 con el reloj real en 15:02. La medición contra el
último tick dice UTC+3, y la descarga lo confirma — la última vela es de las
18:00. Una vela vieja o a medio sincronizar alcanza para deducir un reloj
equivocado, y tres horas de corrimiento no rompen nada: sólo hacen que la
estrategia se mine en una franja y el EA opere en otra.

Si al histórico de MetaTrader se le aplicara el mismo ajuste que al de
Dukascopy, quedaría corrido varias horas y NO FALLARÍA NADA: la estrategia se
mina en una franja horaria y el EA opera en otra. Por eso cada descarga
devuelve el desfase que midió, para que viaje con el dataset en vez de vivir
en una constante global.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd


class MT5Error(Exception):
    """No se pudo hablar con MetaTrader, o no se puede confiar en lo que dijo."""


#: Las temporalidades que se pueden pedir. El nombre es el de la aplicación.
TEMPORALIDADES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")

#: Cuántas velas entrega MetaTrader de una. Medido: pidiendo 100.000 contesta
#: "Invalid params" y con 50.000 anda, así que se pagina.
POR_PEDIDO = 50_000

#: Más viejo que esto y la hora del último tick no sirve para medir el reloj:
#: el mercado está cerrado y ese tick es del viernes.
TICK_VIEJO_SEGUNDOS = 7 * 24 * 3600

#: Cuánto puede alejarse la medición de un desfase redondo antes de darla por
#: sucia. Seis minutos: un tick llega con segundos de retraso, no con minutos.
TOLERANCIA_HORAS = 0.1


def _mt5():
    """El módulo de MetaTrader, con un error entendible si no está."""
    try:
        import MetaTrader5 as mt5           # noqa: N813
    except ImportError as exc:
        raise MT5Error(
            "Falta el módulo de MetaTrader 5. Se instala con "
            "`pip install MetaTrader5` y sólo funciona en Windows.") from exc
    return mt5


def _tf(nombre: str):
    mt5 = _mt5()
    tabla = {"1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5,
             "15m": mt5.TIMEFRAME_M15, "30m": mt5.TIMEFRAME_M30,
             "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4,
             "1d": mt5.TIMEFRAME_D1}
    if nombre not in tabla:
        raise MT5Error(f"Temporalidad desconocida para MetaTrader: {nombre}")
    return tabla[nombre]


@dataclass(frozen=True)
class Conexion:
    """Con qué terminal se está hablando. Va al dataset para poder discutirlo."""

    servidor: str
    cuenta: int
    #: Horas que el servidor adelanta respecto de UTC. `None` cuando no se pudo
    #: medir — y eso NO es cero.
    desfase_utc: float | None


def conectar() -> Conexion:
    """Se engancha al MetaTrader que esté abierto y dice a cuál.

    No abre uno nuevo ni pide credenciales: usa la sesión que el usuario ya
    tiene. Si no hay ninguna, lo dice con esas palabras.
    """
    mt5 = _mt5()
    if not mt5.initialize():
        raise MT5Error(
            f"No se pudo hablar con MetaTrader ({mt5.last_error()}). "
            f"Abrilo, entrá a una cuenta —la demo que trae alcanza— y "
            f"probá de nuevo.")
    cuenta = mt5.account_info()
    if cuenta is None:
        raise MT5Error("MetaTrader está abierto pero sin cuenta iniciada.")
    return Conexion(servidor=cuenta.server, cuenta=cuenta.login,
                    desfase_utc=desfase_del_servidor())


def desfase_del_servidor(simbolo: str = "EURUSD") -> float | None:
    """Cuántas horas adelanta el servidor respecto de UTC, o None.

    DEVUELVE None EN VEZ DE CERO CUANDO NO SE PUEDE MEDIR, y esa distinción es
    todo el sentido de la función. Se mide comparando la hora del último tick
    —que el servidor sella con SU reloj— contra UTC. Si el mercado está
    cerrado, ese tick es del viernes y la cuenta da cualquier cosa.

    Cero es un desfase válido —hay servidores en UTC— así que no puede ser
    también el valor de "no sé".

    Se mide contra el TICK y no contra la última vela: una vela a medio
    sincronizar da un reloj equivocado sin que nada falle. Fue el error que se
    cometió escribiendo este módulo: por la vela parecía UTC, por el tick es
    UTC+3, y la descarga le dio la razón al tick.
    """
    mt5 = _mt5()
    tick = mt5.symbol_info_tick(simbolo)
    if tick is None or not tick.time:
        return None
    ahora = dt.datetime.now(dt.timezone.utc)
    if abs(ahora.timestamp() - tick.time) > TICK_VIEJO_SEGUNDOS:
        return None
    # El tick trae la hora del SERVIDOR guardada como si fuera UTC. La
    # diferencia contra el reloj real es el desfase.
    servidor = dt.datetime.fromtimestamp(tick.time, dt.timezone.utc)
    horas = (servidor - ahora).total_seconds() / 3600.0
    # Los brokers usan desfases enteros, o de media hora en algún caso raro.
    # La tolerancia es angosta A PROPOSITO: un tick llega con segundos de
    # retraso, no con minutos, así que una diferencia grande significa que la
    # medición está sucia y no que el broker tenga un reloj raro. Con doce
    # minutos de holgura, un desfase de 1,7 horas se aceptaba como 1,5 — o sea
    # que el módulo que existe para no adivinar el reloj adivinaba.
    redondo = round(horas * 2) / 2
    if abs(horas - redondo) > TOLERANCIA_HORAS:
        return None
    return redondo


def instrumentos(grupos: tuple[str, ...] = ("Forex", "Indexes", "Metals")
                 ) -> list[dict[str, Any]]:
    """Lo que ese terminal ofrece, por carpeta.

    Se filtran las carpetas a propósito: MetaQuotes-Demo trae doce mil acciones
    de Nasdaq y ninguna sirve para lo que hace la aplicación.
    """
    mt5 = _mt5()
    todos = mt5.symbols_get() or []
    fuera = []
    for s in todos:
        carpeta = s.path.rsplit("\\", 1)[0] if "\\" in s.path else s.path
        if not any(carpeta.startswith(g) for g in grupos):
            continue
        fuera.append({"simbolo": s.name, "grupo": carpeta,
                      "digitos": s.digits, "punto": s.point,
                      "contrato": s.trade_contract_size,
                      "lote_min": s.volume_min,
                      "spread_puntos": s.spread})
    return sorted(fuera, key=lambda x: (x["grupo"], x["simbolo"]))


def descargar(simbolo: str, timeframe: str = "1h", *,
              maximo: int = 200_000,
              progreso: Callable[[float, str], None] | None = None
              ) -> pd.DataFrame:
    """Las velas de ese símbolo, de la más vieja a la más nueva.

    El índice queda en la HORA DEL SERVIDOR, sin convertir. Convertirlo acá
    sería adivinar: quien guarda el dataset tiene que anotar el desfase que
    devolvió `conectar()` y decidir con eso.
    """
    import numpy as np

    mt5 = _mt5()
    # SIN CONECTAR, `symbol_select` devuelve False para TODO, y el mensaje
    # "ese símbolo no existe" manda a buscar el problema donde no está: alguien
    # se pone a probar nombres —US500, SP500, SPX500— cuando lo que falta es
    # abrir MetaTrader. Se distinguen los dos casos.
    if mt5.account_info() is None and not mt5.initialize():
        raise MT5Error(
            f"No hay conexión con MetaTrader ({mt5.last_error()}). Abrilo, "
            f"entrá a una cuenta y probá de nuevo — no es que falte "
            f"{simbolo}.")
    if not mt5.symbol_select(simbolo, True):
        raise MT5Error(f"{simbolo} no existe en este servidor de MetaTrader.")

    tf = _tf(timeframe)
    trozos: list[Any] = []
    desde_pos = 0
    while desde_pos < maximo:
        cuantas = min(POR_PEDIDO, maximo - desde_pos)
        r = mt5.copy_rates_from_pos(simbolo, tf, desde_pos, cuantas)
        if r is None or not len(r):
            break
        trozos.append(r)
        if progreso:
            total = sum(len(x) for x in trozos)
            progreso(min(0.95, total / maximo), f"{total:,} velas de {simbolo}")
        if len(r) < cuantas:
            break                      # se acabó la historia
        desde_pos += len(r)

    if not trozos:
        raise MT5Error(
            f"MetaTrader no devolvió velas de {simbolo} en {timeframe}. "
            f"Abrí un gráfico de ese símbolo y esperá a que baje el histórico.")

    # QUIEN GARANTIZA EL ORDEN ES `sort_index`, mas abajo, y no el orden en que
    # se concatenan las paginas. Habia un `trozos[::-1]` aca con un comentario
    # que decia que las reordenaba; se comprobo quitandolo y no cambia nada,
    # asi que era una linea que solo servia para hacer creer que el orden
    # dependia de ella.
    crudo = np.concatenate(trozos)
    df = pd.DataFrame(crudo)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={"tick_volume": "volume"})
    df = df[["time", "open", "high", "low", "close", "volume"]]
    df = df.set_index("time").sort_index()
    return df[~df.index.duplicated(keep="first")]
