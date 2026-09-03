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
    # Lo que escribe una planilla en castellano. Un archivo exportado de Excel
    # en es-AR traía "fecha;apertura;maximo;minimo;cierre;volumen" y no se
    # reconocía ni una columna (3 de septiembre de 2026).
    "fecha": "date", "hora": "time", "fecha_hora": "time", "fecha y hora": "time",
    "apertura": "open", "abertura": "open",
    "maximo": "high", "máximo": "high",
    "minimo": "low", "mínimo": "low",
    "cierre": "close", "ultimo": "close", "último": "close",
    "volumen": "volume",
}


def parse_ohlcv_csv(content: bytes | str) -> pd.DataFrame:
    """Parse CSV bytes/text into a normalised OHLCV frame.

    Raises ``ValueError`` with a human-readable message when the file cannot
    be understood.
    """
    text = content.decode("utf-8-sig", errors="replace") if isinstance(content, bytes) else content
    sep = _sniff_separator(text)
    # Punto y coma es lo que usa una planilla configurada en castellano, y esa
    # misma planilla escribe la coma como separador decimal: leerlo con el
    # punto dejaba "1801,27" como texto y el archivo entero sin una sola vela
    # válida (3 de septiembre de 2026).
    decimal = "," if sep == ";" else "."
    df = pd.read_csv(io.StringIO(text), sep=sep, decimal=decimal)
    if df.shape[1] < 5:
        raise ValueError("El archivo necesita al menos una columna de tiempo "
                         "y las cuatro de precio (apertura, m\u00e1ximo, m\u00ednimo, cierre).")

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
            raise ValueError(f"Falta la columna {col}.")
        out[col] = pd.to_numeric(df[col].to_numpy(), errors="coerce")
    if "volume" in df.columns:
        out["volume"] = pd.to_numeric(df["volume"].to_numpy(), errors="coerce")
    else:
        out["volume"] = 0.0

    # LO QUE SE TIRA SE CUENTA Y SE DICE. Antes esto era un `dropna` y un
    # deduplicado en silencio: un archivo con un `low` negativo, una marca de
    # tiempo repetida y tres filas cortadas entraba con el tilde verde y sin
    # una palabra. Quien lo subió minaba sobre datos rotos creyendo que
    # estaban enteros (3 de septiembre de 2026).
    total = len(out)
    descartes: dict[str, int] = {}

    def _tirar(mascara, motivo: str) -> None:
        nonlocal out
        n = int(mascara.sum())
        if n:
            descartes[motivo] = descartes.get(motivo, 0) + n
            out = out[~mascara]

    _tirar(out[["open", "high", "low", "close"]].isna().any(axis=1), "sin_precio")
    out["volume"] = out["volume"].fillna(0.0)
    # Un precio no puede ser cero ni negativo, y la vela tiene que cerrar
    # dentro de su propio rango. Una sola vela incoherente le mueve el ATR y
    # los máximos a toda la serie.
    _tirar((out[["open", "high", "low", "close"]] <= 0).any(axis=1), "precio_invalido")
    _tirar((out["high"] < out["low"])
           | (out["high"] < out[["open", "close"]].max(axis=1))
           | (out["low"] > out[["open", "close"]].min(axis=1)), "vela_incoherente")
    _tirar(pd.Series(out.index.duplicated(keep="first"), index=out.index), "repetida")
    out = out.sort_index()

    if len(out) < 100:
        # ANTES DECÍA "Only 0 valid rows found — need at least 100 bars": en
        # inglés con la aplicación en castellano, y sin decir qué mirar. El
        # cero casi siempre es la cabecera, el separador o la coma decimal.
        detalle = ("Revisá el separador de columnas, los nombres de las columnas "
                   "y el separador decimal." if len(out) == 0 else
                   f"Se leyeron {total} filas y quedaron {len(out)} v\u00e1lidas.")
        raise ValueError(f"El archivo dej\u00f3 {len(out)} velas y hacen falta al "
                         f"menos 100. {detalle}")
    # Viajan con el marco: ningún llamador se rompe y el que quiera avisar,
    # avisa. `attrs` sobrevive al guardado en el workspace.
    out.attrs["filas_leidas"] = total
    out.attrs["descartadas"] = descartes
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


def _a_fechas(crudo: pd.Series) -> pd.Series:
    """Convierte texto a fechas, mirando si el archivo usa día/mes o mes/día.

    `format="mixed"` deja que pandas decida cada fila por separado y por
    omisión pone el mes primero. Con velas horarias de veinticinco días
    fechadas 02/01/2023 → 26/01/2023 eso daba once meses de historia
    desordenada, guardada igual y etiquetada "1h": la búsqueda después minaba
    sobre una serie que no existió nunca. Encontrado el 3 de septiembre de 2026.

    La regla es simple y no adivina cuando no hace falta: se parsea de las dos
    maneras y gana la que deje las velas EN ORDEN. Un archivo de velas viene
    ordenado en el tiempo; el orden es la evidencia. Si las dos quedan
    ordenadas, el archivo es ambiguo (todos los días ≤ 12) y se deja el
    criterio de siempre, que es el ISO y el de MetaTrader.
    """
    texto = crudo.astype(str)
    intentos = []
    for dia_primero in (False, True):
        try:
            ts = pd.to_datetime(texto, errors="coerce", format="mixed",
                                dayfirst=dia_primero)
        except (ValueError, TypeError):
            continue
        validas = int(ts.notna().sum())
        limpias = ts.dropna()
        ordenada = bool(limpias.is_monotonic_increasing) if len(limpias) > 1 else True
        intentos.append((validas, ordenada, dia_primero, ts))

    if not intentos:
        return pd.to_datetime(texto, errors="coerce")
    # más filas parseadas manda; a igualdad de filas, la que quede ordenada;
    # y a igualdad de las dos cosas, el criterio de siempre (mes primero)
    mejor = max(intentos, key=lambda x: (x[0], x[1], not x[2]))
    return mejor[3]


def _build_timestamp(df: pd.DataFrame) -> pd.DatetimeIndex:
    if "date" in df.columns and "time" in df.columns and \
            not pd.api.types.is_numeric_dtype(df["time"]):
        raw = df["date"].astype(str) + " " + df["time"].astype(str)
        ts = _a_fechas(raw)
    elif "time" in df.columns:
        col = df["time"]
        if pd.api.types.is_numeric_dtype(col):
            vals = pd.to_numeric(col, errors="coerce").astype("float64")
            med = float(np.nanmedian(vals))
            unit = "ms" if med > 1e11 else "s"          # Binance uses ms epochs
            ts = pd.to_datetime(vals, unit=unit, errors="coerce")
        else:
            ts = _a_fechas(col.astype(str).str.replace(".", "-", regex=False))
    elif "date" in df.columns:
        ts = _a_fechas(df["date"].astype(str).str.replace(".", "-", regex=False))
    else:
        raise ValueError("No se encontró ninguna columna de fecha ni de hora.")

    ts = pd.DatetimeIndex(ts)
    if ts.tz is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    if ts.isna().all():
        raise ValueError("No se pudieron leer las fechas. Revisá el "
                         "formato de la columna de tiempo y el separador de columnas.")
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
