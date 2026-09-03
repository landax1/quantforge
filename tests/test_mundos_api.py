"""Cada sección (CFDs / cripto) ve sólo lo suyo.

El banco, las corridas y las guardadas se comparten entre las dos secciones,
así que "Cripto" abría con las 236 corridas de SP500 y cambiar de sección
parecía no hacer nada: un parpadeo y la misma pantalla (2 de septiembre).
El recorte se hace en el servidor porque la paginación del banco vive ahí.
"""

from __future__ import annotations

import glob

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app
from botiquant.database.db import Database

from tests.test_banco import _corrida, _fila


@pytest.fixture()
def cliente(tmp_path):
    with TestClient(create_app(workdir=tmp_path / "ws")) as c:
        db = Database(glob.glob(str(tmp_path / "ws" / "*.sqlite"))[0])
        yield c, db


def _dos_corridas(db: Database) -> tuple[str, str]:
    sp = _corrida(db, "SP500 H1 (Dukascopy)", filas=[_fila(0), _fila(1), _fila(2)])
    eth = _corrida(db, "ETHUSDT H1", filas=[_fila(3)])
    return sp, eth


def test_las_corridas_y_el_total_son_de_la_seccion(cliente):
    c, db = cliente
    sp, eth = _dos_corridas(db)

    cripto = c.get("/api/corridas", params={"mundo": "exchange"}).json()
    cfd = c.get("/api/corridas", params={"mundo": "metatrader"}).json()
    todo = c.get("/api/corridas").json()

    assert [x["id"] for x in cripto["corridas"]] == [eth]
    assert cripto["total"] == 1
    assert [x["id"] for x in cfd["corridas"]] == [sp]
    assert cfd["total"] == 3
    assert todo["total"] == 4


def test_el_banco_paginado_no_mezcla_secciones(cliente):
    c, db = cliente
    sp, eth = _dos_corridas(db)

    filas = c.get("/api/banco", params={"mundo": "exchange"}).json()
    assert {f["corrida_id"] for f in filas} == {eth}

    filas = c.get("/api/banco", params={"mundo": "metatrader"}).json()
    assert {f["corrida_id"] for f in filas} == {sp}


def test_una_seccion_sin_corridas_da_cero_y_no_todo(cliente):
    """Lo que hacía la vieja pantalla: al no haber nada de cripto mostraba
    lo de CFDs. Una lista vacía de corridas tiene que dar vacío."""
    c, db = cliente
    _corrida(db, "SP500 H1 (Dukascopy)")

    r = c.get("/api/corridas", params={"mundo": "exchange"}).json()
    assert r["corridas"] == [] and r["total"] == 0
    assert c.get("/api/banco", params={"mundo": "exchange"}).json() == []


def test_lo_que_no_se_puede_clasificar_se_ve_en_las_dos(cliente):
    c, db = cliente
    propio = _corrida(db, "mi_csv_raro")

    for mundo in ("exchange", "metatrader"):
        r = c.get("/api/corridas", params={"mundo": mundo}).json()
        assert [x["id"] for x in r["corridas"]] == [propio]


def test_las_guardadas_tambien_se_recortan(cliente):
    c, db = cliente
    spec = {"name": "S", "entry": {"type": "ema_cross"}}
    db.save_strategy("cfd", spec, meta={"dataset_name": "SP500 H1 (Dukascopy)"})
    db.save_strategy("perp", spec, meta={"dataset_name": "ETHUSDT H1"})
    db.save_strategy("vieja", spec, meta={})

    nombres = lambda mundo: sorted(  # noqa: E731
        x["name"] for x in c.get("/api/strategies", params={"mundo": mundo}).json())

    assert nombres("exchange") == ["perp", "vieja"]
    assert nombres("metatrader") == ["cfd", "vieja"]
    assert nombres("") == ["cfd", "perp", "vieja"]


def test_al_guardar_del_banco_el_nombre_lleva_el_mercado(cliente):
    """Cada corrida arranca en S-001 y en Probar convivían tres S-001: el
    nombre guardado lleva el mercado (S-001-ETH), sin repetirlo si ya lo tiene."""
    c, db = cliente
    corrida = _corrida(db, "ETHUSDT H1", filas=[_fila(0)])
    ids = db.ids_banco_de(corrida)
    r = c.post("/api/banco/guardar", json={"ids": ids}).json()
    assert r["guardadas"][0]["name"] == "S-000-ETH"
    sp = _corrida(db, "SP500 H1 (MetaTrader)", filas=[_fila(1)])
    r2 = c.post("/api/banco/guardar", json={"ids": db.ids_banco_de(sp)}).json()
    assert r2["guardadas"][0]["name"] == "S-001-SP500"
