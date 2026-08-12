"""Una estrategia guardada tiene que dar los mismos números al reabrirla.

Es la propiedad que hace útil guardar algo. Sin ella, la lista muestra unos
resultados y el detalle otros, y ninguno de los dos se puede creer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import botiquant.api.app as appmod
from botiquant.generator.templates import drivers
from botiquant.mining.miner import mine


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        yield c


def test_the_miner_reports_the_exact_range_it_measured(df):
    """Con hora, no recortado al día: redondear mueve el corte unas velas y con
    él los números."""
    out = mine(df, [d.id for d in drivers()][:3], [], max_candidates=5,
               min_trades=1, seed=1)

    r = out["measured_range"]
    assert r["from"] == str(df.index[0])
    assert r["to"] == str(df.index[-1])
    assert len(r["from"]) > 10, "sin hora no se puede reproducir el corte exacto"


def test_the_measured_range_is_the_in_sample_half_when_split(df):
    """Con división in/out, las métricas del databank salen del tramo de
    adentro: es ese el que hay que guardar, no el total."""
    out = mine(df, [d.id for d in drivers()][:3], [], max_candidates=5,
               min_trades=1, oos_pct=30.0, seed=1)

    if out.get("split") is None:
        pytest.skip("el dataset de prueba es corto para partirlo")
    assert out["measured_range"]["to"] < str(df.index[-1]), \
        "el tramo medido llega hasta el final: no se reservó nada"
    assert out["measured_range"]["to"][:10] == out["split"]["is_to"]


def test_reopening_on_the_saved_range_reproduces_the_numbers(cliente):
    """El bug de fondo: sin el rango, reabrir corría el backtest sobre TODA la
    historia y devolvía otra estrategia con el mismo nombre. Con riesgo
    agresivo sobre veinte años eso llega a dar -100%."""
    cliente.post("/api/datasets/sample", json={"symbol": "TEST", "bars": 6000})
    ds = cliente.get("/api/datasets").json()[0]["id"]
    spec = {"name": "t", "direction": "long",
            "entry_long": [{"left": {"type": "indicator", "name": "EMA",
                                     "params": {"period": 10}},
                            "op": "cross_above",
                            "right": {"type": "indicator", "name": "EMA",
                                      "params": {"period": 30}}}],
            "entry_short": [], "risk": {"stop_type": "atr", "stop_value": 2}}

    entero = cliente.get(f"/api/datasets").json()[0]
    mitad = {"dataset_id": ds, "spec": spec,
             "date_from": entero["start"], "date_to": entero["start"][:4] + "-06-30"}

    a = cliente.post("/api/backtest", json=mitad).json()["result"]["metrics"]
    b = cliente.post("/api/backtest", json=mitad).json()["result"]["metrics"]
    assert a == b, "el mismo tramo tiene que dar el mismo resultado"

    # y sobre todo el histórico da OTRA cosa: es lo que se veía al reabrir
    todo = cliente.post("/api/backtest",
                        json={"dataset_id": ds, "spec": spec}).json()["result"]["metrics"]
    assert todo["trades"] != a["trades"], \
        "si el tramo no cambiara nada, el bug no habría existido"
