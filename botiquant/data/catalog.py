"""Catalogue of ready-to-mine instruments.

Each entry carries the Dukascopy symbol used to fetch history plus the broker
cost profile that instrument actually trades at, so the mining page can preset
spread and slippage instead of asking the user to guess.

``direction`` es la direccion que conviene buscar en ese instrumento, y sale
de medir, no de razonar. Se razono primero y se razono mal: "solo los indices
tienen deriva al alza". Los numeros dicen otra cosa — 200 candidatas por
instrumento, 1h, diez anios, riesgo 1%, misma vara, contando las que dan
profit factor >= 1:

                  solo largos   ambas
    SP500                 123      40
    XAUUSD                101      33
    BTCUSD                 76      39
    EURUSD                 12      12   (pero ambas llega a +2% y largos no)

El oro y el Bitcoin tambien subieron estos diez anios, asi que shortearlos es
pelear contra la tendencia de fondo. El unico sin deriva es el par de divisas,
y ahi permitir cortos sube el techo de 1.92% a 4.05% anual.

``aliases`` son los nombres con los que uno se puede encontrar este mismo
mercado en la lista de simbolos de un broker. No es cosmetico: al probar
el EA del S&P en el tester, MetaTrader contesto "symbol SP500 not exist"
porque ese servidor lo llama US500. El bot estaba bien y no operaba nunca.

``min_cagr`` es el rendimiento anual que conviene exigir en ese mercado, y
tambien sale de medir. Los techos, sobre 200 candidatas con la misma vara:
S&P 14,95%, oro 20,20%, Bitcoin 21,84% y EURUSD 4,05%. Pedirle 3% a los
cuatro trata como iguales a mercados que no lo son: en EURUSD eso equivale a
exigir casi el maximo posible, y la busqueda se va a decenas de minutos.

``fuente`` dice de donde se baja el historico. Existe porque hay dos tipos de
instrumento con costos que funcionan distinto:

  · ``dukascopy`` son CFD. El costo esta en el SPREAD, en unidades de precio.
  · ``binance`` son perpetuos de exchange. El libro es ajustado, asi que el
    spread es despreciable y el costo real es la COMISION, en % del nocional.
    Ademas cobran o pagan ``funding`` cada ocho horas por tener la posicion
    abierta, que el CFD no tiene.

La diferencia no es menor. Medido, ida y vuelta como % del precio: nuestro
spread de S&P son 0,0072% y la comision taker de un exchange es 0,10% — trece
veces mas. En Bitcoin la brecha se achica a 3,6x con taker y 1,4x con maker,
porque su spread ya es alto. Por eso cripto es el mercado donde el exchange
tiene sentido y los indices no.

``contract_size`` y ``min_lot`` son REFERENCIAS, igual que el spread: cada
broker define las suyas y la pantalla dice que hay que comprobarlas. Existen
para poder contestar la unica pregunta que el capital inicial deberia contestar
y no contestaba: con esta plata y este riesgo, la posicion que sale, ¿el broker
la acepta? Si no la acepta, el minimo obliga a arriesgar mas de lo pedido y el
usuario se entera recien operando con plata de verdad.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

from botiquant.data.loader import parse_ohlcv_csv
from botiquant.data.dukascopy import descargar as descargar_dukascopy

# Server-time offset applied to Dukascopy UTC data so mined session rules match
# what an MT5 EA sees on a GMT+3 broker (New York + 7).
SERVER_TZ_OFFSET_HOURS = 7

CATALOG: list[dict[str, Any]] = [
    {
        "key": "sp500",
        "label": "SP500",
        "full_name": "S&P 500 index CFD",
        "dukascopy": "usa500idxusd",
        "category": "indices",
        "from": "2013-01-01",
        "spread": 0.36,
        "slippage": 0.1,
        "stop_points": 40.0,
        "target_points": 80.0,
        "contract_size": 100,
        "min_lot": 0.1,
        "min_cagr": 3.0,
        "aliases": ["SP500", "US500", "SPX500", "S&P500", "USA500", "US500Cash"],
        "direction": "long",
        "mejor_rendimiento": True,
    },
    {
        "key": "eurusd",
        "label": "EURUSD",
        "full_name": "Euro / US Dollar",
        "dukascopy": "eurusd",
        "category": "forex",
        "from": "2005-01-01",
        "spread": 0.00012,
        "slippage": 0.00003,
        "stop_points": 0.0060,
        "target_points": 0.0120,
        "contract_size": 100000,
        "min_lot": 0.01,
        "min_cagr": 1.0,
        "aliases": ["EURUSD"],
        "direction": "both",
    },
    {
        "key": "xauusd",
        "label": "XAUUSD",
        "full_name": "Oro / US Dollar",
        "dukascopy": "xauusd",
        "category": "metals",
        "from": "2010-01-01",
        "spread": 0.25,
        "slippage": 0.05,
        "stop_points": 18.0,
        "target_points": 36.0,
        "contract_size": 100,
        "min_lot": 0.01,
        "min_cagr": 3.0,
        "aliases": ["XAUUSD", "GOLD", "XAUUSD.spot"],
        "direction": "long",
    },
    {
        "key": "btcusd",
        "label": "BTCUSD",
        "full_name": "Bitcoin / US Dollar",
        "dukascopy": "btcusd",
        "category": "crypto",
        "from": "2017-01-01",
        "spread": 12.0,
        "slippage": 3.0,
        "stop_points": 900.0,
        "target_points": 1800.0,
        "contract_size": 1,
        "min_lot": 0.01,
        "min_cagr": 3.0,
        "aliases": ["BTCUSD", "BTCUSDT", "Bitcoin"],
        "direction": "long",
    },
    # ── Perpetuos de exchange ────────────────────────────────────────────
    # Se bajan de Binance y no del exchange donde se opera. Medido: BTCUSDT en
    # Binance y en BingX correlacionan 0,99974 en sus movimientos, con 0,0019%
    # de diferencia media de precio — cien veces menos que la comision de una
    # operacion. Y Binance da siete anios de historia contra los nueve meses de
    # BingX. Se mina con los datos buenos y se ejecuta donde haya cuenta.
    #
    # `spread` en cero NO es un olvido: en un libro de ordenes el costo es la
    # comision, y ponerlo tambien como spread seria cobrarlo dos veces.
    {
        "key": "btcusdt",
        "label": "BTCUSDT",
        "full_name": "Bitcoin perpetuo (Binance)",
        "fuente": "binance",
        "binance": "BTCUSDT",
        "category": "cripto",
        "from": "2019-09-08",
        "spread": 0.0,
        "slippage": 3.0,
        "commission_pct": 0.04,
        "stop_points": 800.0,
        "target_points": 1600.0,
        "contract_size": 1,
        "min_lot": 0.001,
        "min_cagr": 3.0,
        "aliases": ["BTCUSDT", "BTC-USDT", "BTCUSD", "BTCPERP"],
        # Bitcoin subio estos anios, pero a diferencia de los indices el
        # funding le PAGA al lado corto: sobre siete anios la tasa media fue
        # +11,61% anual, cobrada por los vendedores. Se permiten las dos
        # direcciones para que la busqueda pueda encontrar esa familia.
        "direction": "both",
        "mejor_rendimiento": False,
    },
    {
        "key": "ethusdt",
        "label": "ETHUSDT",
        "full_name": "Ethereum perpetuo (Binance)",
        "fuente": "binance",
        "binance": "ETHUSDT",
        "category": "cripto",
        "from": "2019-11-27",
        "spread": 0.0,
        "slippage": 0.2,
        "commission_pct": 0.04,
        "stop_points": 60.0,
        "target_points": 120.0,
        "contract_size": 1,
        "min_lot": 0.001,
        "min_cagr": 3.0,
        "aliases": ["ETHUSDT", "ETH-USDT", "ETHUSD", "ETHPERP"],
        "direction": "both",
        "mejor_rendimiento": False,
    },
]

BY_KEY = {c["key"]: c for c in CATALOG}


def default_stop_points(last_close: float) -> tuple[float, float]:
    """Distancias de SL/TP razonables para un instrumento, en unidades de precio.

    Un stop se expresa en puntos absolutos, así que 200 puntos son medio
    razonables en un índice de 7000 y literalmente imposibles en EURUSD a
    1.15: el precio nunca recorre esa distancia, la estrategia no cierra
    nunca y la búsqueda entera devuelve cero. Escalar al precio (~0.5% para
    el stop, el doble para el target) mantiene el mismo comportamiento en
    cualquier mercado; se redondea a 2 cifras significativas para que el
    número que ve el usuario sea legible.
    """
    price = abs(float(last_close or 0.0))
    if price <= 0:
        return 200.0, 400.0
    stop = price * 0.005
    exp = math.floor(math.log10(stop))
    stop = round(stop, -(exp - 1))          # 2 cifras significativas
    return stop, stop * 2


def to_server_time(df: pd.DataFrame) -> pd.DataFrame:
    """Shift a UTC-indexed frame to broker server time (NY+7)."""
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York")
    shifted = ny + pd.Timedelta(hours=SERVER_TZ_OFFSET_HOURS)
    out = df.copy()
    out.index = pd.DatetimeIndex(shifted.tz_localize(None))
    return out


def simbolo_fuente(entry: dict) -> str:
    """El nombre del instrumento en SU fuente.

    Existe porque el catálogo dejó de tener una sola: un CFD se identifica por
    su símbolo de Dukascopy y un perpetuo por el de Binance. Todo lo que antes
    leía `entry["dukascopy"]` directo rompía al aparecer el primer instrumento
    que no viene de ahí.
    """
    return entry.get(entry.get("fuente", "dukascopy"), entry["label"])


def download(key: str, workdir: Path, date_from: str | None = None,
             date_to: str | None = None,
             progress=None) -> pd.DataFrame:
    """Trae el histórico M1 de un instrumento del catálogo desde Dukascopy.

    Antes esto invocaba `npx dukascopy-node`. Funcionaba en una máquina de
    desarrollo y fallaba en la de cualquier usuario: el .exe no lleva Node y
    casi nadie lo tiene instalado, así que la aplicación se descargaba vacía y
    su único modo de conseguir datos daba un error sobre `npx`.

    Ahora se baja en Python. Lo único que sigue necesitando es conexión, y sólo
    cuando el usuario la pide.
    """
    entry = BY_KEY.get(key)
    if entry is None:
        raise ValueError(f"Instrumento desconocido: {key}")

    fuente = entry.get("fuente", "dukascopy")

    def avance(frac: float, msg: str) -> None:
        if progress:
            progress(0.02 + frac * 0.88, f"{entry['label']} · {msg}")

    if fuente == "binance":
        # Un perpetuo de exchange ya viene en UTC y no pasa por el ajuste de
        # hora de servidor: ese ajuste existe para alinear los CFD con el
        # horario del broker, y un mercado que opera 24/7 no tiene sesiones
        # que alinear.
        from botiquant.data.binance import descargar as descargar_binance
        if progress:
            progress(0.02, f"Conectando con Binance para {entry['label']}…")
        return descargar_binance(entry["binance"],
                                 date_from or entry["from"],
                                 date_to or _today(),
                                 intervalo="1m", progreso=avance)

    if progress:
        progress(0.02, f"Conectando con Dukascopy para {entry['label']}…")
    df = descargar_dukascopy(entry["dukascopy"],
                             date_from or entry["from"],
                             date_to or _today(),
                             progreso=avance)
    if progress:
        progress(0.95, "Convirtiendo a hora del servidor…")
    return to_server_time(df)


def _today() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%d")
