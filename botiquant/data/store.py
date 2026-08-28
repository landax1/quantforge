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
            user_id: str | None = None,
            utc_offset: float | None = None) -> dict[str, Any]:
        """`utc_offset`: en qué reloj están las fechas de `df`.

        Son las horas que ese reloj adelanta respecto de UTC. None es "no se
        sabe" y NO es cero: un histórico corrido tres horas no falla en ningún
        lado, sólo hace que la estrategia se mine en una franja y el EA opere
        en otra.
        """
        ds_id = self.db.insert_dataset(
            name=name, source=source, rows=len(df),
            start=str(df.index[0]), end=str(df.index[-1]),
            timeframe=infer_timeframe(df.index),
            last_close=float(df["close"].iloc[-1]) if len(df) else None,
            user_id=user_id, utc_offset=utc_offset,
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

    def _path_funding(self, ds_id: str) -> Path:
        """El funding vive en un archivo hermano, no adentro del de velas.

        Tiene otra frecuencia: se liquida cada ocho horas, no en cada barra.
        Meterlo como columna obligaría a repetir el valor en miles de filas o a
        dejar huecos, y ademas romperia todos los datasets que ya existen.
        Como archivo aparte, el instrumento que no lo tiene simplemente no lo
        tiene, y el motor se comporta igual que siempre.
        """
        return self.root / f"{self._raiz(ds_id)}.funding.csv"

    @staticmethod
    def _raiz(ds_id: str) -> str:
        """El id sin el sufijo de resampleo: ``abc@1h`` es ``abc``.

        Un frame a una hora y el mismo a treinta minutos comparten la serie de
        funding: las tasas son del instrumento, no de la temporalidad.
        """
        return ds_id.split("@", 1)[0]

    def guardar_funding(self, ds_id: str, serie) -> None:
        """Guarda las tasas de un perpetuo al lado de sus velas."""
        if serie is None or not len(serie):
            return
        serie.to_csv(self._path_funding(ds_id), index_label="time",
                     header=["funding"])

    def funding(self, ds_id: str):
        """Las tasas de este instrumento, o ``None`` si no es un perpetuo.

        Devolver ``None`` y no una serie vacía es deliberado: el motor
        distingue "no hay funding" de "hay funding y vale cero", y un CFD es lo
        primero.
        """
        ruta = self._path_funding(ds_id)
        if not ruta.exists():
            return None
        s = pd.read_csv(ruta, index_col="time")["funding"]
        # Se convierte A MANO y no con `parse_dates`. Con marcas que llevan
        # zona horaria —"2019-09-10 08:00:00+00:00", que es como las escribe
        # `guardar_funding`— pandas NO las parsea y NO avisa: deja el índice
        # como texto. Después `s.index.tz` revienta con AttributeError en
        # medio de un minado, que es donde se descubrió.
        #
        # `utc=True` además normaliza: si algún día una serie viniera con otro
        # huso, quedaría comparable con las velas sin que nadie lo note.
        # `format="ISO8601"` y no el inferido: las tasas de Binance NO tienen
        # todas el mismo formato. La mayoría cae en el segundo exacto y unas
        # pocas traen milisegundos —"16:00:00.001000+00:00"— porque el momento
        # de liquidación que informa el exchange no es exactamente redondo.
        # Sin esto, pandas se rinde con el archivo entero por unas pocas filas.
        s.index = pd.to_datetime(s.index, utc=True, format="ISO8601")
        s.index.name = "time"
        return s

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
