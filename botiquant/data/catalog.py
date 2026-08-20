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
        "direction": "long",
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

    if progress:
        progress(0.02, f"Conectando con Dukascopy para {entry['label']}…")

    def avance(frac: float, msg: str) -> None:
        if progress:
            progress(0.02 + frac * 0.88, f"{entry['label']} · {msg}")

    df = descargar_dukascopy(entry["dukascopy"],
                             date_from or entry["from"],
                             date_to or _today(),
                             progreso=avance)
    if progress:
        progress(0.95, "Convirtiendo a hora del servidor…")
    return to_server_time(df)


def _today() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%d")
