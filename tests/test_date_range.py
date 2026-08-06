"""Minar y backtestear sobre un tramo elegido, no siempre sobre todo.

Es la base de la validación out-of-sample: si el rango no se puede elegir,
toda estrategia se juzga sobre los mismos datos con los que fue encontrada.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantforge.api.app import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


@pytest.fixture
def dataset(client):
    """Un dataset horario largo: ~3.5 años, suficiente para partirlo."""
    r = client.post("/api/datasets/sample", json={
        "symbol": "RANGE", "bars": 30_000, "timeframe_minutes": 60,
        "start": "2020-01-01"})
    assert r.status_code == 200, r.text
    return r.json()


def _spec():
    return {"name": "t", "direction": "long",
            "entry_long": [{"left": {"type": "price", "field": "close"},
                            "op": ">",
                            "right": {"type": "indicator", "name": "EMA",
                                      "params": {"period": 20}}}],
            "entry_short": [],
            "risk": {"stop_type": "atr", "stop_value": 2, "target_type": "atr",
                     "target_value": 4, "size_mode": "risk_pct", "size_value": 1}}


def test_backtest_without_dates_uses_everything(client, dataset):
    r = client.post("/api/backtest", json={"dataset_id": dataset["id"], "spec": _spec()})
    assert r.status_code == 200, r.text
    ts = r.json()["result"]["timestamps"]
    assert pd.Timestamp(ts[0]).year == 2020


def test_backtest_honours_the_date_range(client, dataset):
    r = client.post("/api/backtest", json={
        "dataset_id": dataset["id"], "spec": _spec(),
        "date_from": "2021-06-01", "date_to": "2022-12-31"})
    assert r.status_code == 200, r.text
    ts = r.json()["result"]["timestamps"]
    first, last = pd.Timestamp(ts[0]), pd.Timestamp(ts[-1])
    assert first >= pd.Timestamp("2021-06-01")
    assert last <= pd.Timestamp("2023-01-01")


def test_end_date_covers_the_whole_day(client, dataset):
    """'hasta 2021-12-31' significa el día entero, no su primer segundo."""
    r = client.post("/api/backtest", json={
        "dataset_id": dataset["id"], "spec": _spec(),
        "date_from": "2020-06-01", "date_to": "2021-12-31"})
    assert r.status_code == 200, r.text
    last = pd.Timestamp(r.json()["result"]["timestamps"][-1])
    assert last.date() == pd.Timestamp("2021-12-31").date()


def test_two_ranges_give_different_results(client, dataset):
    """Sin esto el recorte no estaría haciendo nada."""
    a = client.post("/api/backtest", json={
        "dataset_id": dataset["id"], "spec": _spec(),
        "date_from": "2020-01-01", "date_to": "2021-06-30"}).json()["result"]
    b = client.post("/api/backtest", json={
        "dataset_id": dataset["id"], "spec": _spec(),
        "date_from": "2021-07-01", "date_to": "2023-06-30"}).json()["result"]
    assert (a["metrics"]["trades"] != b["metrics"]["trades"]
            or a["metrics"]["net_profit"] != b["metrics"]["net_profit"])


def test_range_too_short_is_rejected_with_a_readable_reason(client, dataset):
    r = client.post("/api/backtest", json={
        "dataset_id": dataset["id"], "spec": _spec(),
        "date_from": "2020-01-01", "date_to": "2020-01-05"})
    assert r.status_code == 400
    assert "velas" in r.json()["detail"]


def test_inverted_range_is_rejected(client, dataset):
    r = client.post("/api/backtest", json={
        "dataset_id": dataset["id"], "spec": _spec(),
        "date_from": "2022-01-01", "date_to": "2021-01-01"})
    assert r.status_code == 400
    assert "anterior" in r.json()["detail"]


def test_mining_reports_the_range_it_actually_used(client, dataset):
    import time
    r = client.post("/api/mine", json={
        "dataset_id": dataset["id"], "drivers": ["ema_cross"],
        "filters": [], "max_candidates": 12, "min_trades": 2,
        "date_from": "2021-01-01", "date_to": "2022-12-31",
        "risk": {"stop_type": "atr", "stop_value": 2, "target_type": "atr",
                 "target_value": 4, "size_mode": "risk_pct", "size_value": 1},
    })
    assert r.status_code == 200, r.text
    job = r.json()["job_id"]
    for _ in range(200):
        j = client.get(f"/api/jobs/{job}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert j["status"] == "done", j
    rng = j["result"]["range"]
    assert pd.Timestamp(rng["from"]) >= pd.Timestamp("2021-01-01")
    assert pd.Timestamp(rng["to"]) <= pd.Timestamp("2023-01-01")
    assert rng["bars"] > 0
