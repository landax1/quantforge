"""El EA opera en el reloj del histórico con el que se minó, no en otro.

EL ERROR QUE EVITA. La estrategia se minó con velas que dicen 07:00 en el
reloj de un servidor, y el robot filtra sesiones con el reloj que le pasaron.
Si no son el mismo, la estrategia se minó entre las 7 y las 16 de un reloj y
el robot opera entre las 7 y las 16 de OTRO. No falla nada: los números no se
parecen a los del backtest y nadie sabe por qué.

Hasta acá el reloj era una preferencia global —un desplegable— y los datos de
Dukascopy se corrían con una constante. Al aparecer una segunda fuente eso
deja de alcanzar: las velas de MetaTrader vienen en la hora del servidor de
donde salieron, y ese servidor no es el mismo para todos.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from botiquant.api.app import create_app
    monkeypatch.setenv("BQ_EXPORTS", str(tmp_path / "salida"))
    return TestClient(create_app(workdir=tmp_path / "ws"))


def _velas(n=300) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = pd.Series(range(n), dtype=float) + 100.0
    return pd.DataFrame({"open": base.values, "high": base.values + 1,
                         "low": base.values - 1, "close": base.values,
                         "volume": 1.0}, index=idx)


def _spec():
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return {"name": "S", "direction": "long",
            "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
            "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                     "stop_type": "atr", "stop_value": 2.0,
                     "target_type": "atr", "target_value": 4.0}}


def _offset_del_ea(texto: str) -> int:
    linea = [l for l in texto.splitlines() if "InpServerUTCOffset" in l][0]
    return int("".join(c for c in linea.split("=")[1] if c in "-0123456789"))


def _tienda(workdir: Path):
    """La misma tienda que usa la aplicación para ese espacio de trabajo."""
    from botiquant.api.app import _base_de_datos
    from botiquant.data.store import DataStore
    from botiquant.database.db import Database
    return DataStore(workdir / "datasets", Database(_base_de_datos(workdir)))


def _con_dataset(workdir: Path, utc_offset):
    """Guarda un histórico con ese reloj y devuelve su id."""
    ds = _tienda(workdir).add("US500 H1 (MetaTrader)", _velas(),
                              source="metatrader", utc_offset=utc_offset)
    return ds["id"]


def test_manda_el_reloj_del_historico_y_no_el_del_desplegable(tmp_path,
                                                              monkeypatch):
    """El caso que importa: el usuario dejó el desplegable en 0 —o nunca lo
    tocó— y el histórico vino de un servidor en UTC+3."""
    with _cliente(tmp_path, monkeypatch) as c:
        ds_id = _con_dataset(tmp_path / "ws", 3.0)
        r = c.post("/api/export/mql5", json={
            "spec": _spec(), "name": "X", "dataset_id": ds_id,
            "server_utc_offset": 0})
        assert r.status_code == 200, r.text
        assert _offset_del_ea(r.text) == 3


def test_sin_reloj_en_el_historico_vale_el_del_usuario(tmp_path, monkeypatch):
    """Los datos de Dukascopy no traen reloj medido, y los guardados viejos
    tampoco. Ahí la elección del usuario es lo único que hay."""
    with _cliente(tmp_path, monkeypatch) as c:
        ds_id = _con_dataset(tmp_path / "ws", None)
        r = c.post("/api/export/mql5", json={
            "spec": _spec(), "name": "X", "dataset_id": ds_id,
            "server_utc_offset": 2})
        assert _offset_del_ea(r.text) == 2


def test_un_reloj_de_CERO_en_el_historico_no_se_confunde_con_no_saberlo(
        tmp_path, monkeypatch):
    """Hay servidores en UTC, así que 0 es un valor válido. Si se tratara como
    «no se sabe», ganaría el desplegable y el EA operaría corrido."""
    with _cliente(tmp_path, monkeypatch) as c:
        ds_id = _con_dataset(tmp_path / "ws", 0.0)
        r = c.post("/api/export/mql5", json={
            "spec": _spec(), "name": "X", "dataset_id": ds_id,
            "server_utc_offset": 3})
        assert _offset_del_ea(r.text) == 0, "el 0 del histórico tiene que ganar"
