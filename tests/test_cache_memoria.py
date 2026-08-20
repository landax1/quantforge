"""La caché de datos reparte su presupuesto según lo que pesa cada frame.

Medido sobre los cuatro instrumentos que trae la aplicación:

    instrumento   crudo M1   resampleado 1h
    EURUSD          368 MB          6.1 MB
    XAUUSD          256 MB          4.3 MB
    BTCUSD          179 MB          3.0 MB
    SP500           213 MB          3.6 MB

Con una sola lista de ocho entradas entraban los cuatro crudos y los cuatro
resampleados: 1.033 MB por el solo hecho de haber mirado los cuatro
instrumentos. Con presupuestos separados: 409 MB.

El crudo es un medio —sirve para producir el resampleado y después no se toca,
porque el minado corre en 1h, 4h o 1d— así que se guardan pocos y se conservan
muchos derivados, que es lo que se usa una y otra vez.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.data.store import DataStore
from botiquant.database.db import Database


def _velas(n: int, inicio: str = "2020-01-01") -> pd.DataFrame:
    idx = pd.date_range(inicio, periods=n, freq="1min")
    base = 100 + np.cumsum(np.random.default_rng(3).normal(0, .05, n))
    return pd.DataFrame({"open": base, "high": base + .1, "low": base - .1,
                         "close": base, "volume": 1.0}, index=idx).rename_axis("time")


@pytest.fixture()
def store(tmp_path):
    db = Database(tmp_path / "b.sqlite")
    return DataStore(tmp_path / "datasets", db)


def test_los_crudos_se_desalojan_antes_que_los_derivados(store):
    """Es todo el punto: el que pesa sesenta veces más ocupa menos lugares."""
    ids = [store.add(f"I{i}", _velas(4000))["id"] for i in range(5)]
    for i in ids:
        store.load(i, "1h")
    crudos = [k for k in store._cache if "@" not in k]
    derivados = [k for k in store._cache if "@" in k]
    assert len(crudos) <= store._crudos_max, "se guardaron más crudos que el tope"
    assert len(derivados) == 5, "se perdió un resampleado, que es lo barato de guardar"


def test_volver_a_un_derivado_cacheado_no_lee_el_disco(store, monkeypatch):
    """El error que introdujo el reparto y hubo que corregir.

    `load` preguntaba por el crudo antes que por el resampleado. Como el crudo
    se desaloja primero, volver a un instrumento ya cacheado releía ocho
    millones de velas del disco: trece segundos y medio para devolver algo que
    ya estaba en memoria.
    """
    ids = [store.add(f"J{i}", _velas(4000))["id"] for i in range(5)]
    for i in ids:
        store.load(i, "1h")
    assert ids[0] not in store._cache, "el crudo del primero tenía que haberse ido"

    def prohibido(*a, **k):
        raise AssertionError("volvió a leer el disco teniendo el resampleado en memoria")

    monkeypatch.setattr(pd, "read_csv", prohibido)
    assert len(store.load(ids[0], "1h")) > 0


def test_el_nativo_sigue_funcionando(store):
    """Pedir el crudo a propósito tiene que seguir dando el crudo."""
    ds = store.add("K", _velas(3000))["id"]
    nativo = store.load(ds)
    assert len(nativo) == 3000
    assert len(store.load(ds, "native")) == 3000


def test_borrar_limpia_las_dos_familias(store):
    ds = store.add("L", _velas(3000))["id"]
    store.load(ds, "1h")
    store.delete(ds)
    assert not [k for k in store._cache if k.startswith(ds)]
