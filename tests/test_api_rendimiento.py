"""El panel de rendimiento le pregunta a la cuenta, no a los bots.

Se comprueba con un exchange de mentira: que el resultado venga partido por
concepto, que el depósito inicial no cuente como ganancia, y que un símbolo
que el exchange rechaza no tire abajo el panel entero.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app
from botiquant.data import binance_trade as bt
from botiquant.vivo import claves


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(claves, "leer", lambda *a, **k: ("clave", "secreto"))
    monkeypatch.setattr(bt, "saldo", lambda *a, **k: 4999.73)
    monkeypatch.setattr(bt, "posiciones", lambda *a, **k: [
        {"simbolo": "ETHUSDT", "cantidad": 0.01, "pnl_abierto": 1.25}])
    monkeypatch.setattr(bt, "movimientos", lambda *a, **k: [
        {"incomeType": "TRANSFER", "income": "5000", "symbol": ""},
        {"incomeType": "REALIZED_PNL", "income": "-0.0486", "symbol": "BTCUSDT"},
        {"incomeType": "COMMISSION", "income": "-0.2203", "symbol": "BTCUSDT"},
        {"incomeType": "REALIZED_PNL", "income": "0.5", "symbol": "SOLUSDT"},
    ])

    def cerradas(sim, *a, **k):
        if sim == "SOLUSDT":
            raise bt.BinanceError("Invalid symbol.", -1121)
        return [{"simbolo": sim, "cuando": 1788222732044, "lado": "venta",
                 "cantidad": 0.0007, "precio": 78752.5, "pnl": -0.00007,
                 "comision": 0.022, "orden": 1},
                {"simbolo": sim, "cuando": 1788222725284, "lado": "compra",
                 "cantidad": 0.0007, "precio": 78752.6, "pnl": 0.0,
                 "comision": 0.022, "orden": 2}]
    monkeypatch.setattr(bt, "cerradas", cerradas)
    with TestClient(create_app(workdir=tmp_path / "ws")) as c:
        yield c


def test_el_resultado_va_partido_y_el_deposito_no_cuenta(client):
    e = client.get("/api/cuenta/rendimiento").json()
    assert e["saldo"] == 4999.73
    assert e["resultado"] == {"pnl": 0.4514, "comision": -0.2203,
                              "funding": 0.0, "neto": 0.2311}
    assert e["pnl_abierto"] == 1.25 and len(e["posiciones"]) == 1


def test_un_simbolo_rechazado_no_tira_abajo_el_panel(client):
    e = client.get("/api/cuenta/rendimiento").json()
    # BTC respondió, SOL no: quedan las de BTC, ordenadas de la más reciente.
    assert [c["orden"] for c in e["cerradas"]] == [1, 2]
    assert e["cuantas_cerradas"] == 1 and e["win_rate_pct"] == 0.0


def test_sin_clave_dice_que_falta_la_clave(client, monkeypatch):
    def sin(*a, **k):
        raise claves.ClaveError("No hay clave de binance para practica.")
    monkeypatch.setattr(claves, "leer", sin)
    r = client.get("/api/cuenta/rendimiento")
    assert r.status_code == 400 and "clave" in r.json()["detail"].lower()
