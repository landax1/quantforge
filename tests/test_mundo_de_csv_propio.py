"""Un CSV propio pertenece a la sección desde la que se importó.

Un histórico de oro subido a mano no tiene cómo clasificarse por el nombre,
así que se veía en las dos secciones: en Cripto aparecía con "Encender en
demo" ofrecido para una estrategia de oro, y la fila del banco no abría
("el instrumento ya no está", que era falso). Lo encontró un usuario de
prueba el 3 de septiembre de 2026. Desde entonces la importación guarda el
mundo ("upload@exchange") y cada sección ve sólo lo suyo.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app
from botiquant.data.semilla import mundo_de_fuente


@pytest.fixture()
def c():
    app = create_app(workdir=pathlib.Path(tempfile.mkdtemp()))
    with TestClient(app) as cliente:
        yield cliente


def _csv(n: int = 160) -> bytes:
    import datetime as dt
    filas = ["time,open,high,low,close,volume"]
    p, t0 = 2000.0, dt.datetime(2026, 1, 1)
    for i in range(n):
        p += (1 if i % 3 else -1) * 1.5
        filas.append(f"{t0 + dt.timedelta(hours=i):%Y-%m-%d %H:%M:%S},{p},{p + 2},{p - 2},{p + 1},100")
    return chr(10).join(filas).encode()


def test_la_fuente_lleva_el_mundo():
    assert mundo_de_fuente("upload@exchange") == "exchange"
    assert mundo_de_fuente("import@metatrader") == "metatrader"
    assert mundo_de_fuente("upload@otra") is None
    assert mundo_de_fuente("upload") is None
    assert mundo_de_fuente("binance") == "exchange"


def test_el_csv_subido_desde_cripto_queda_en_cripto(c):
    r = c.post("/api/datasets/upload?mundo=exchange",
               files={"file": ("ORO propio.csv", _csv(), "text/csv")})
    assert r.status_code == 200, r.text
    fila = next(d for d in c.get("/api/datasets").json() if d["name"] == "ORO propio")
    assert fila["mundo"] == "exchange"
    assert fila["source"] == "upload@exchange"


def test_sin_decir_la_seccion_no_se_adivina(c):
    r = c.post("/api/datasets/upload", files={"file": ("ORO viejo.csv", _csv(), "text/csv")})
    assert r.status_code == 200, r.text
    fila = next(d for d in c.get("/api/datasets").json() if d["name"] == "ORO viejo")
    assert fila["mundo"] is None
    assert fila["source"] == "upload"


def test_los_errores_del_servidor_tienen_ingles(c):
    r = c.get("/api/jobs/no-existe", headers={"X-Idioma": "en"})
    assert r.status_code == 404
    assert r.json()["detail"] == "That task no longer exists."
    r = c.get("/api/jobs/no-existe", headers={"X-Idioma": "es"})
    assert r.json()["detail"] == "Esa tarea ya no existe."


def test_a_un_csv_viejo_se_le_pone_la_seccion_despues(c):
    r = c.post("/api/datasets/upload", files={"file": ("GER40_H1.csv", _csv(), "text/csv")})
    ds = r.json()["id"]
    r = c.post(f"/api/datasets/{ds}/mundo", json={"mundo": "metatrader"})
    assert r.status_code == 200, r.text
    fila = next(d for d in c.get("/api/datasets").json() if d["id"] == ds)
    assert fila["mundo"] == "metatrader" and fila["source"] == "upload@metatrader"
    assert c.post(f"/api/datasets/{ds}/mundo", json={"mundo": "luna"}).status_code == 400
    assert c.post("/api/datasets/no-existe/mundo", json={"mundo": "exchange"}).status_code == 404


def test_el_nombre_clasifica_por_tokens_enteros():
    from botiquant.data.catalog import mundo_de_nombre

    assert mundo_de_nombre("GER40_H1") is None          # GER40 no está en el catálogo
    assert mundo_de_nombre("XAUUSD_H1") == "metatrader"
    assert mundo_de_nombre("ARIEL XAUUSD H1") == "metatrader"
    assert mundo_de_nombre("BTCUSDT H1") == "exchange"
    assert mundo_de_nombre("mis velas raras") is None
    # BTCUSD está adentro de BTCUSDT: por subcadena se confundían
    assert mundo_de_nombre("BTCUSDTX H1") is None
