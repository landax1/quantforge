"""Estrategias guardadas: tienen que sobrevivir a la corrida que las encontró.

Una estrategia sin su contexto no sirve de nada meses después — el spec dice
qué reglas usa, pero no sobre qué instrumento se encontró, con qué timeframe
ni con qué costos. Sin eso no se puede volver a exportar ni comparar.
"""

from __future__ import annotations

import io

import pytest

from quantforge.database.db import Database


def _spec() -> dict:
    return {
        "name": "EMA cross", "direction": "long",
        "entry_long": [{"left": {"type": "indicator", "name": "EMA", "params": {"period": 12}},
                        "op": "cross_above",
                        "right": {"type": "indicator", "name": "EMA", "params": {"period": 26}}}],
        "entry_short": [],
        "risk": {"stop_type": "atr", "stop_value": 2.5, "target_type": "atr",
                 "target_value": 5.0, "size_mode": "risk_pct", "size_value": 1.0},
    }


def test_context_survives_the_round_trip(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    meta = {"dataset_name": "SP500 M1", "timeframe": "30m", "spread": 0.36,
            "metrics": {"profit_factor": 1.35, "cagr_pct": 8.1}, "oos_ratio": 0.92}
    sid = db.save_strategy("S-018", _spec(), notes="del mining del martes", meta=meta)

    got = db.get_strategy(sid)
    assert got["meta"]["timeframe"] == "30m"
    assert got["meta"]["metrics"]["profit_factor"] == 1.35
    assert got["notes"] == "del mining del martes"

    listed = db.list_strategies()
    assert listed[0]["meta"]["dataset_name"] == "SP500 M1"


def test_an_old_workspace_gains_the_column_without_losing_data(tmp_path):
    """Migración aditiva: una base creada antes de `meta` sigue funcionando."""
    import sqlite3
    path = tmp_path / "viejo.sqlite"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE strategies (id TEXT PRIMARY KEY, name TEXT NOT NULL,
            spec TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL, updated TEXT NOT NULL);
        INSERT INTO strategies VALUES ('a','vieja','{}','nota','2026-01-01','2026-01-01');
    """)
    con.commit()
    con.close()

    db = Database(path)                      # dispara la migración
    rows = db.list_strategies()
    assert len(rows) == 1
    assert rows[0]["name"] == "vieja"
    assert rows[0]["meta"] == {}, "las viejas quedan con contexto vacío, no rotas"
    # y desde ahora acepta contexto
    db.save_strategy("nueva", _spec(), meta={"timeframe": "1h"})
    assert any(r["meta"].get("timeframe") == "1h" for r in db.list_strategies())


def test_saving_through_the_api_keeps_the_context(client_with_sample):
    client = client_with_sample
    r = client.post("/api/strategies", json={
        "spec": _spec(), "name": "S-004", "notes": "candidata",
        "meta": {"timeframe": "4h", "metrics": {"profit_factor": 1.2}},
    })
    assert r.status_code == 200
    sid = r.json()["id"]
    listed = client.get("/api/strategies").json()
    fila = next(x for x in listed if x["id"] == sid)
    assert fila["name"] == "S-004"
    assert fila["meta"]["timeframe"] == "4h"


def test_path_import_is_refused_in_multiuser_mode(tmp_path, monkeypatch):
    """Leer una ruta arbitraria del servidor sólo es aceptable en local."""
    from fastapi.testclient import TestClient

    import quantforge.api.app as appmod

    monkeypatch.setattr(appmod, "MULTIUSER", True)
    c = TestClient(appmod.create_app(tmp_path))
    r = c.post("/api/datasets/import-path", json={"path": "C:/Windows/win.ini"})
    assert r.status_code == 403
    assert "multiusuario" in r.json()["detail"]
