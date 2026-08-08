"""Dataset store: OHLCV files cached on disk + metadata in SQLite.

Frames are persisted as compact CSVs under ``<workdir>/datasets`` and loaded
into an in-memory LRU so repeated backtests never touch the disk.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

import pandas as pd

from botiquant.data.loader import infer_timeframe, resample_ohlcv
from botiquant.database.db import Database


class DataStore:
    def __init__(self, root: Path, db: Database) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = db
        self._cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self._cache_max = 8

    # ------------------------------------------------------------------ CRUD
    def add(self, name: str, df: pd.DataFrame, source: str = "upload") -> dict[str, Any]:
        ds_id = self.db.insert_dataset(
            name=name, source=source, rows=len(df),
            start=str(df.index[0]), end=str(df.index[-1]),
            timeframe=infer_timeframe(df.index),
            last_close=float(df["close"].iloc[-1]) if len(df) else None,
        )
        path = self._path(ds_id)
        df.to_csv(path, index_label="time", float_format="%.6f")
        self._cache_put(ds_id, df)
        return self.db.get_dataset(ds_id)

    def load(self, ds_id: str, timeframe: str | None = None) -> pd.DataFrame:
        df = self._cache.get(ds_id)
        if df is None:
            path = self._path(ds_id)
            if not path.exists():
                raise FileNotFoundError(f"Dataset {ds_id} not found on disk")
            df = pd.read_csv(path, index_col="time", parse_dates=["time"])
            df = df.astype("float64")
            self._cache_put(ds_id, df)
        if timeframe and timeframe != "native":
            key = f"{ds_id}@{timeframe}"
            cached = self._cache.get(key)
            if cached is None:
                cached = resample_ohlcv(df, timeframe)
                self._cache_put(key, cached)
            return cached
        return df

    def delete(self, ds_id: str) -> None:
        self.db.delete_dataset(ds_id)
        self._cache.pop(ds_id, None)
        for key in [k for k in self._cache if k.startswith(f"{ds_id}@")]:
            self._cache.pop(key, None)
        path = self._path(ds_id)
        if path.exists():
            path.unlink()

    def list(self) -> list[dict[str, Any]]:
        return self.db.list_datasets()

    # -------------------------------------------------------------- helpers
    def _path(self, ds_id: str) -> Path:
        return self.root / f"{ds_id}.csv"

    def _cache_put(self, key: str, df: pd.DataFrame) -> None:
        self._cache[key] = df
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
