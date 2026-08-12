"""Format-tolerant OHLCV loading.

Accepts generic CSVs, MetaTrader 4/5 exports, TradingView exports and Binance
kline dumps. Column names and delimiters are auto-detected; the result is
always a UTC-indexed frame with columns open/high/low/close/volume.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

_COLUMN_ALIASES: dict[str, str] = {
    "open": "open", "o": "open",
    "high": "high", "h": "high", "max": "high",
    "low": "low", "l": "low", "min": "low",
    "close": "close", "c": "close", "last": "close",
    "volume": "volume", "vol": "volume", "tickvol": "volume", "tick_volume": "volume",
    "real_volume": "volume", "volume_btc": "volume",
    "time": "time", "date": "date", "datetime": "time", "timestamp": "time",
    "open_time": "time", "gmt time": "time", "local time": "time",
}


def parse_ohlcv_csv(content: bytes | str) -> pd.DataFrame:
    """Parse CSV bytes/text into a normalised OHLCV frame.

    Raises ``ValueError`` with a human-readable message when the file cannot
    be understood.
    """
    text = content.decode("utf-8-sig", errors="replace") if isinstance(content, bytes) else content
    sep = _sniff_separator(text)
    df = pd.read_csv(io.StringIO(text), sep=sep)
    if df.shape[1] < 5:
        raise ValueError("File needs at least time + OHLC columns")

    df.columns = [str(c).strip().lower().replace('"', "") for c in df.columns]

    # headerless MT4-style file: 2020.01.02,00:00,1.12,1.13,1.11,1.12,500
    if not _has_known_header(df.columns):
        df = pd.read_csv(io.StringIO(text), sep=sep, header=None)
        df = _apply_positional_names(df)

    rename = {c: _COLUMN_ALIASES[c] for c in df.columns if c in _COLUMN_ALIASES}
    df = df.rename(columns=rename)

    ts = _build_timestamp(df)
    out = pd.DataFrame(index=ts)
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")
        out[col] = pd.to_numeric(df[col].to_numpy(), errors="coerce")
    if "volume" in df.columns:
        out["volume"] = pd.to_numeric(df["volume"].to_numpy(), errors="coerce")
    else:
        out["volume"] = 0.0

    out = out.dropna(subset=["open", "high", "low", "close"])
    out["volume"] = out["volume"].fillna(0.0)
    out = out[~out.index.duplicated(keep="first")].sort_index()
    if len(out) < 100:
        raise ValueError(f"Only {len(out)} valid rows found — need at least 100 bars")
    return out


def _sniff_separator(text: str) -> str:
    head = text[:4000]
    counts = {sep: head.count(sep) for sep in (",", ";", "\t")}
    return max(counts, key=lambda s: counts[s]) or ","


def _has_known_header(cols: list[str] | pd.Index) -> bool:
    known = sum(1 for c in cols if str(c).strip().lower() in _COLUMN_ALIASES)
    return known >= 4


def _apply_positional_names(df: pd.DataFrame) -> pd.DataFrame:
    ncols = df.shape[1]
    if ncols >= 7:
        df.columns = ["date", "time", "open", "high", "low", "close", "volume"] + \
            [f"extra{i}" for i in range(ncols - 7)]
    elif ncols == 6:
        df.columns = ["time", "open", "high", "low", "close", "volume"]
    else:
        df.columns = ["time", "open", "high", "low", "close"][:ncols]
    return df


def _build_timestamp(df: pd.DataFrame) -> pd.DatetimeIndex:
    if "date" in df.columns and "time" in df.columns and \
            not pd.api.types.is_numeric_dtype(df["time"]):
        raw = df["date"].astype(str) + " " + df["time"].astype(str)
        ts = pd.to_datetime(raw, errors="coerce", format="mixed")
    elif "time" in df.columns:
        col = df["time"]
        if pd.api.types.is_numeric_dtype(col):
            vals = pd.to_numeric(col, errors="coerce").astype("float64")
            med = float(np.nanmedian(vals))
            unit = "ms" if med > 1e11 else "s"          # Binance uses ms epochs
            ts = pd.to_datetime(vals, unit=unit, errors="coerce")
        else:
            ts = pd.to_datetime(col.astype(str).str.replace(".", "-", regex=False),
                                errors="coerce", format="mixed")
    elif "date" in df.columns:
        ts = pd.to_datetime(df["date"].astype(str).str.replace(".", "-", regex=False),
                            errors="coerce", format="mixed")
    else:
        raise ValueError("No time/date column found")

    ts = pd.DatetimeIndex(ts)
    if ts.tz is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    if ts.isna().all():
        raise ValueError("Could not parse timestamps")
    return ts


_RESAMPLE_MAP = {"5m": "5min", "15m": "15min", "30m": "30min",
                 "1h": "1h", "4h": "4h", "1d": "1D", "1w": "1W"}


#: Cuántos segundos dura cada timeframe, para poder comparar el pedido contra
#: lo que el dataset realmente tiene.
_SEGUNDOS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
             "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample to a higher timeframe ('5m','15m','30m','1h','4h','1d','1w').

    Agrupar sólo funciona hacia arriba. Pedir 15 minutos sobre velas de una
    hora no da 15 minutos: los huecos se descartan y vuelven las MISMAS velas
    de una hora, con la etiqueta equivocada. Eso es peor que fallar — la
    estrategia se busca sobre velas horarias, se exporta como M15, y en
    MetaTrader corre sobre un gráfico de 15 minutos con reglas que nunca se
    probaron ahí.
    """
    rule = _RESAMPLE_MAP.get(timeframe)
    if rule is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    pedido = _SEGUNDOS.get(timeframe)
    nativo = _SEGUNDOS.get(infer_timeframe(df.index))
    if pedido and nativo and pedido < nativo:
        raise ValueError(
            f"Este instrumento tiene velas de {infer_timeframe(df.index)} y estás "
            f"pidiendo {timeframe}. No se puede: agrupar velas sólo funciona hacia "
            f"timeframes más grandes. Descargá el histórico de 1 minuto desde Datos "
            f"para minar por debajo de {infer_timeframe(df.index)}.")

    out = df.resample(rule).agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
    ).dropna(subset=["open", "close"])
    return out


def infer_timeframe(index: pd.DatetimeIndex) -> str:
    """Human label for the native bar interval."""
    if len(index) < 3:
        return "?"
    # unit-safe regardless of ns/us datetime resolution (pandas 3 may use either)
    deltas = np.diff(index.values).astype("timedelta64[s]").astype(np.float64)
    secs = float(np.median(deltas))
    table = [(60, "1m"), (300, "5m"), (900, "15m"), (1800, "30m"),
             (3600, "1h"), (14400, "4h"), (86400, "1d"), (604800, "1w")]
    for s, label in table:
        if abs(secs - s) / s < 0.35:
            return label
    return f"{int(secs)}s"
