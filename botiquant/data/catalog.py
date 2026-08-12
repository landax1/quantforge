"""Catalogue of ready-to-mine instruments.

Each entry carries the Dukascopy symbol used to fetch history plus the broker
cost profile that instrument actually trades at, so the mining page can preset
spread and slippage instead of asking the user to guess.
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
        "category": "Índices",
        "from": "2013-01-01",
        "spread": 0.36,
        "slippage": 0.1,
        "stop_points": 40.0,
        "target_points": 80.0,
        "note": "CFD del S&P 500 — spread típico 0.36 puntos",
    },
    {
        "key": "eurusd",
        "label": "EURUSD",
        "full_name": "Euro / US Dollar",
        "dukascopy": "eurusd",
        "category": "Forex",
        "from": "2005-01-01",
        "spread": 0.00012,
        "slippage": 0.00003,
        "stop_points": 0.0060,
        "target_points": 0.0120,
        "note": "El par más operado — spread típico 1.2 pips",
    },
    {
        "key": "xauusd",
        "label": "XAUUSD",
        "full_name": "Oro / US Dollar",
        "dukascopy": "xauusd",
        "category": "Metales",
        "from": "2010-01-01",
        "spread": 0.25,
        "slippage": 0.05,
        "stop_points": 18.0,
        "target_points": 36.0,
        "note": "Oro spot — spread típico 25 cents",
    },
    {
        "key": "btcusd",
        "label": "BTCUSD",
        "full_name": "Bitcoin / US Dollar",
        "dukascopy": "btcusd",
        "category": "Cripto",
        "from": "2017-01-01",
        "spread": 12.0,
        "slippage": 3.0,
        "stop_points": 900.0,
        "target_points": 1800.0,
        "note": "Bitcoin CFD — spread ancho, cuidado con el scalping",
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
