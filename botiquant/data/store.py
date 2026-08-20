"""Dataset store: OHLCV files cached on disk + metadata in SQLite.

Frames are persisted as compact CSVs under ``<workdir>/datasets`` and loaded
into an in-memory LRU so repeated backtests never touch the disk.

La cache tiene DOS presupuestos porque los frames no pesan igual: uno crudo
de un minuto ronda los 300 MB y su version en una hora, los cinco. Ver
``_podar``.
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
        # Dos presupuestos y no uno. Un frame crudo M1 pesa entre 179 y 368 MB;
        # su version en 1h, entre 3 y 6. Con una sola lista de ocho entradas
        # entraban los cuatro crudos y los cuatro resampleados: 1.033 MB por
        # haber mirado los cuatro instrumentos.
        #
        # El crudo es un MEDIO: sirve para producir el resampleado y despues no
        # se toca, porque el minado corre en 1h, 4h o 1d. El que se usa todo el
        # tiempo es el chico. Por eso se guardan pocos crudos y muchos
        # resampleados, y cambiar de instrumento sin cambiar de timeframe no
        # vuelve a leer el disco.
        self._cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self._crudos_max = 2
        self._derivados_max = 12

    # ------------------------------------------------------------------ CRUD
    def add(self, name: str, df: pd.DataFrame, source: str = "upload",
            user_id: str | None = None) -> dict[str, Any]:
        ds_id = self.db.insert_dataset(
            name=name, source=source, rows=len(df),
            start=str(df.index[0]), end=str(df.index[-1]),
            timeframe=infer_timeframe(df.index),
            last_close=float(df["close"].iloc[-1]) if len(df) else None,
            user_id=user_id,
        )
        path = self._path(ds_id)
        df.to_csv(path, index_label="time", float_format="%.6f")
        self._cache_put(ds_id, df)
        return self.db.get_dataset(ds_id, user_id)

    def load(self, ds_id: str, timeframe: str | None = None) -> pd.DataFrame:
        """El frame pedido, del cache si está, del disco si no.

        Se pregunta PRIMERO por el resampleado. Parece un detalle y no lo es:
        el crudo se desaloja antes que el derivado —pesa sesenta veces más— así
        que leerlo para después descubrir que el resampleado ya estaba en
        memoria costaba trece segundos y medio de lectura de disco para nada.
        Medido sobre EURUSD, ocho millones de velas.
        """
        key = f"{ds_id}@{timeframe}" if timeframe and timeframe != "native" else ""
        if key:
            listo = self._cache.get(key)
            if listo is not None:
                self._cache.move_to_end(key)      # sigue siendo el más reciente
                return listo

        df = self._cache.get(ds_id)
        if df is None:
            path = self._path(ds_id)
            if not path.exists():
                raise FileNotFoundError(f"Dataset {ds_id} not found on disk")
            df = pd.read_csv(path, index_col="time", parse_dates=["time"])
            df = df.astype("float64")
            self._cache_put(ds_id, df)
        else:
            self._cache.move_to_end(ds_id)

        if key:
            derivado = resample_ohlcv(df, timeframe)
            self._cache_put(key, derivado)
            return derivado
        return df

    def delete(self, ds_id: str, user_id: str | None = None) -> None:
        # Se mira ANTES de borrar: si la fila no era suya, el DELETE no toca
        # nada y el archivo del disco tiene que quedarse donde está. Borrarlo
        # igual dejaría un instrumento compartido sin sus velas.
        antes = self.db.list_datasets(user_id)
        self.db.delete_dataset(ds_id, user_id)
        if not any(d["id"] == ds_id for d in antes):
            return
        if any(d["id"] == ds_id for d in self.db.list_datasets(user_id)):
            return                                  # seguía ahí: no era suya
        self._cache.pop(ds_id, None)
        for key in [k for k in self._cache if k.startswith(f"{ds_id}@")]:
            self._cache.pop(key, None)
        path = self._path(ds_id)
        if path.exists():
            path.unlink()

    def list(self, user_id: str | None = None) -> list[dict[str, Any]]:
        return self.db.list_datasets(user_id)

    # -------------------------------------------------------------- helpers
    def _path(self, ds_id: str) -> Path:
        return self.root / f"{ds_id}.csv"

    @staticmethod
    def _es_derivado(key: str) -> bool:
        """Un resampleado se reconoce por el arroba: ``<id>@1h``."""
        return "@" in key

    def _cache_put(self, key: str, df: pd.DataFrame) -> None:
        self._cache[key] = df
        self._cache.move_to_end(key)
        self._podar()

    def _podar(self) -> None:
        """Recorta cada familia contra su propio tope, del mas viejo al mas nuevo."""
        for derivado, tope in ((True, self._derivados_max), (False, self._crudos_max)):
            claves = [k for k in self._cache if self._es_derivado(k) is derivado]
            for k in claves[:max(len(claves) - tope, 0)]:
                self._cache.pop(k, None)
