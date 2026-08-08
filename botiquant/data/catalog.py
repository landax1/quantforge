"""Catalogue of ready-to-mine instruments.

Each entry carries the Dukascopy symbol used to fetch history plus the broker
cost profile that instrument actually trades at, so the mining page can preset
spread and slippage instead of asking the user to guess.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from botiquant.data.loader import parse_ohlcv_csv

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
    """Fetch M1 history for a catalogue instrument via ``npx dukascopy-node``.

    Requires node/npx on PATH and a network connection — the only part of
    Botiquant that is not offline, and only when the user asks for it.
    """
    entry = BY_KEY.get(key)
    if entry is None:
        raise ValueError(f"Instrumento desconocido: {key}")
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        raise RuntimeError("npx (Node.js) no está instalado — hace falta para descargar de Dukascopy")

    out_dir = Path(workdir) / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in out_dir.glob("*.csv")}

    cmd = [npx, "dukascopy-node", "-i", entry["dukascopy"],
           "-from", date_from or entry["from"], "-to", date_to or _today(),
           "-t", "m1", "-f", "csv", "-v", "true", "-dir", str(out_dir)]
    if progress:
        progress(0.05, f"Descargando {entry['label']} desde Dukascopy…")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    last_pct = 0.0
    for line in proc.stdout or []:
        m = re.search(r"(\d+)%", line)
        if m and progress:
            pct = min(int(m.group(1)) / 100.0 * 0.8, 0.8)
            if pct > last_pct:
                last_pct = pct
                progress(0.05 + pct, f"Descargando {entry['label']}… {m.group(1)}%")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"La descarga falló (código {proc.returncode})")

    new = [p for p in out_dir.glob("*.csv") if p.name not in before]
    if not new:
        raise RuntimeError("La descarga no produjo ningún archivo")
    csv_path = max(new, key=lambda p: p.stat().st_mtime)

    if progress:
        progress(0.88, "Parseando velas…")
    df = parse_ohlcv_csv(csv_path.read_bytes())
    if progress:
        progress(0.95, "Convirtiendo a hora del servidor…")
    df = to_server_time(df)
    csv_path.unlink(missing_ok=True)
    return df


def _today() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%d")
