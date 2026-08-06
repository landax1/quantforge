"""API integration tests over a temp workspace."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from quantforge.api.app import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    app = create_app(workdir=tmp_path_factory.mktemp("qf"))
    with TestClient(app) as c:
        yield c


def _first_dataset(client) -> str:
    existing = client.get("/api/datasets").json()
    if existing:
        return existing[0]["id"]
    return client.post("/api/datasets/sample",
                       json={"symbol": "TEST", "bars": 5000}).json()["id"]


def _spec() -> dict:
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return {
        "name": "api test", "direction": "long",
        "entry_long": [{"left": ema(15), "op": "cross_above", "right": ema(60)}],
        "risk": {"stop_type": "atr", "stop_value": 2, "target_type": "atr", "target_value": 3},
    }


def test_meta(client):
    m = client.get("/api/meta").json()
    assert len(m["indicators"]) >= 15
    assert any(t["kind"] == "driver" for t in m["templates"])


def test_datasets_start_empty(client):
    # no synthetic auto-seeding: the user imports real data via the Data page
    assert client.get("/api/datasets").json() == []


def test_backtest_and_result_flow(client):
    ds = _first_dataset(client)
    r = client.post("/api/backtest", json={"dataset_id": ds, "spec": _spec(), "save": True})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["metrics"]["trades"] > 0
    rid = body["result_id"]

    assert client.get(f"/api/results/{rid}").status_code == 200
    assert "Equity curve" in client.get(f"/api/results/{rid}/report.html").text
    assert client.get(f"/api/results/{rid}/trades.csv").status_code == 200
    assert client.get(f"/api/results/{rid}/report.xlsx").status_code == 200

    mc = client.post("/api/montecarlo", json={"result_id": rid, "simulations": 200})
    assert mc.status_code == 200
    assert "risk_of_ruin_pct" in mc.json()


def test_incoherent_risk_config_is_rejected(client):
    """risk_pct sizing needs a measurable stop distance — the API must say so
    instead of silently falling back to full-equity sizing."""
    ds = _first_dataset(client)
    for stop_type in ("money", "none"):
        r = client.post("/api/backtest", json={
            "dataset_id": ds, "spec": _spec(),
            "risk": {"size_mode": "risk_pct", "size_value": 1,
                     "stop_type": stop_type, "stop_value": 50},
        })
        assert r.status_code == 400, f"{stop_type} debería rechazarse"
        assert "%" in r.json()["detail"]

    # the coherent pairing still works
    ok = client.post("/api/backtest", json={
        "dataset_id": ds, "spec": _spec(),
        "risk": {"size_mode": "risk_pct", "size_value": 1,
                 "stop_type": "points", "stop_value": 2},
    })
    assert ok.status_code == 200


def test_mine_rejects_costs_from_another_instrument(client):
    """El spread del S&P sobre un par de forex es 30% por operación: todas las
    candidatas dan -100% y la app parece rota. Tiene que fallar explícito."""
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD_COST", "bars": 800,
                           "start_price": 1.15}).json()["id"]
    r = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 5,
        "settings": {"spread": 0.36, "slippage": 0.1},
        "risk": {"size_mode": "risk_pct", "size_value": 1,
                 "stop_type": "points", "stop_value": 0.006},
    })
    assert r.status_code == 400
    assert "costos" in r.json()["detail"].lower()


def test_datasets_carry_exit_and_cost_suggestions(client):
    """Cada dataset viaja con salidas a su escala de precio: un stop en puntos
    heredado de otro mercado no se alcanza nunca y no se cierra ni una trade."""
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "SCALE", "bars": 600, "start_price": 1.15}).json()["id"]
    d = next(d for d in client.get("/api/datasets").json() if d["id"] == ds)
    assert d["suggested_stop"] > 0
    assert d["suggested_target"] > d["suggested_stop"]
    ratio = d["suggested_stop"] / d["last_close"]
    assert 0.0005 < ratio < 0.05, "el stop sugerido debe ser alcanzable"


def test_ui_assets_are_cache_busted(client):
    """A stale app.js silently shows an older app — asset URLs must change
    whenever the file does."""
    html = client.get("/").text
    assert "/static/app.js?v=" in html
    assert "/static/charts.js?v=" in html
    assert "/static/styles.css?v=" in html


def test_upload_rejects_garbage(client):
    r = client.post("/api/datasets/upload",
                    files={"file": ("bad.csv", io.BytesIO(b"not,a,real\nfile,1,2"), "text/csv")})
    assert r.status_code == 400


def test_strategy_crud(client):
    r = client.post("/api/strategies", json={"spec": _spec()})
    sid = r.json()["id"]
    names = [s["name"] for s in client.get("/api/strategies").json()]
    assert "api test" in names
    client.delete(f"/api/strategies/{sid}")
    assert all(s["id"] != sid for s in client.get("/api/strategies").json())


def test_job_flow_generate(client):
    ds = _first_dataset(client)
    job = client.post("/api/generate", json={
        "dataset_id": ds, "drivers": ["ema_cross"], "filters": [],
        "max_filters": 0, "min_trades": 1, "top_n": 3,
    }).json()
    import time
    for _ in range(120):
        j = client.get(f"/api/jobs/{job['job_id']}").json()
        if j["status"] != "running":
            break
        time.sleep(0.3)
    assert j["status"] == "done", j.get("error")
    assert j["result"], "generator should return candidates"
