"""Portafolio sobre estrategias del banco, y las notas de las guardadas."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from botiquant.analysis.walkforward import _verdict
from botiquant.api.app import create_app
from botiquant.portfolio.portfolio import build_portfolio


def _curva(inicio: str, n: int, pendiente: float, ruido: float, semilla: int):
    idx = pd.date_range(inicio, periods=n, freq="D")
    rng = np.random.default_rng(semilla)
    eq = 10_000 * np.cumprod(1 + pendiente + rng.normal(0, ruido, n))
    return {"equity": [float(x) for x in eq],
            "timestamps": [str(t) for t in idx], "initial_capital": 10_000.0}


def test_dos_curvas_distintas_dan_correlacion_baja():
    a = {"name": "A", **_curva("2020-01-01", 600, 0.0004, 0.01, 1)}
    b = {"name": "B", **_curva("2020-01-01", 600, 0.0003, 0.01, 2)}
    p = build_portfolio([a, b])
    assert p["metrics"]["avg_correlation"] is not None
    assert abs(p["metrics"]["avg_correlation"]) < 0.3
    assert p["sin_datos"] == []


def test_dos_curvas_iguales_se_delatan():
    base = _curva("2020-01-01", 600, 0.0004, 0.01, 3)
    p = build_portfolio([{"name": "A", **base}, {"name": "B", **base}])
    assert p["metrics"]["avg_correlation"] > 0.99


def test_un_periodo_que_no_se_solapa_no_se_lee_como_diversificacion():
    """El error que tenía: una estrategia medida en OTRO tramo queda plana en
    la intersección, su correlación sale NaN, viaja como null y se pintaba
    como 0.00 — o sea, "diversificación perfecta" justo cuando no hay con qué
    afirmarlo."""
    a = {"name": "A", **_curva("2020-01-01", 800, 0.0004, 0.01, 4)}
    # B termina antes de que A empiece a moverse en la ventana compartida
    vieja = _curva("2016-01-01", 500, 0.0004, 0.01, 5)
    b = {"name": "B", **vieja}
    p = build_portfolio([a, b])
    assert "B" in p["sin_datos"]
    assert p["metrics"]["avg_correlation"] is None
    # y ninguna celda de la matriz miente con un cero
    plana = p["correlation"][1]
    assert all(v is None for v in plana)


def test_la_ventana_compartida_viaja_con_el_resultado():
    a = {"name": "A", **_curva("2020-01-01", 600, 0.0004, 0.01, 6)}
    b = {"name": "B", **_curva("2020-06-01", 600, 0.0004, 0.01, 7)}
    p = build_portfolio([a, b])
    assert p["ventana"]["from"] >= "2020-06-01"
    assert p["ventana"]["days"] > 0


def test_menos_de_dos_no_es_un_portafolio():
    with pytest.raises(ValueError):
        build_portfolio([{"name": "A", **_curva("2020-01-01", 100, 0.0004, 0.01, 8)}])


# ----------------------------------------------------------------- veredicto WF

def test_ganar_en_todos_los_tramos_no_es_sobreajuste():
    """Cuatro de cuatro tramos fuera de muestra en ganancia con eficiencia
    0.24 se declaraba "sobreajustada", que es decirle al usuario que tire lo
    único que le funcionó. El ajuste SIEMPRE es optimista: que sobreviva menos
    de lo prometido es lo normal, que gane en todos los tramos no."""
    assert _verdict(0.24, 1.0) == "acceptable"
    assert _verdict(0.6, 1.0) == "robust"


def test_un_tramo_afortunado_no_tapa_a_los_demas():
    assert _verdict(0.9, 0.25) == "overfitted"


def test_el_veredicto_duro_sigue_existiendo():
    assert _verdict(0.1, 0.4) == "overfitted"
    assert _verdict(0.55, 0.8) == "robust"


# --------------------------------------------------------------------- notas

@pytest.fixture
def cliente(tmp_path):
    return TestClient(create_app(workdir=tmp_path))


def _guardar(cliente):
    r = cliente.post("/api/strategies", json={
        "name": "S-001",
        "spec": {"name": "S-001", "direction": "long",
                 "entry_long": [{"left": {"type": "price", "field": "close"},
                                 "op": ">", "right": {"type": "const", "value": 1}}],
                 "risk": {"stop_type": "atr", "stop_value": 2.0}},
        "notes": "",
    })
    assert r.status_code == 200
    return r.json()["id"]


def test_se_puede_escribir_por_que_la_guardaste(cliente):
    sid = _guardar(cliente)
    r = cliente.post(f"/api/strategies/{sid}/nota", json={"notes": "la mejor en NY"})
    assert r.status_code == 200
    assert r.json()["notes"] == "la mejor en NY"
    fila = next(x for x in cliente.get("/api/strategies").json() if x["id"] == sid)
    assert fila["notes"] == "la mejor en NY"


def test_la_nota_no_pisa_la_estrategia(cliente):
    """Existe aparte de POST /api/strategies justamente por esto: ese endpoint
    reescribe el spec entero, y anotar no puede arriesgar perderlo."""
    sid = _guardar(cliente)
    antes = cliente.get("/api/strategies").json()
    spec_antes = next(x for x in antes if x["id"] == sid)["spec"]
    cliente.post(f"/api/strategies/{sid}/nota", json={"notes": "hola"})
    despues = cliente.get("/api/strategies").json()
    assert next(x for x in despues if x["id"] == sid)["spec"] == spec_antes


def test_una_nota_enorme_se_recorta(cliente):
    sid = _guardar(cliente)
    r = cliente.post(f"/api/strategies/{sid}/nota", json={"notes": "x" * 9000})
    assert len(r.json()["notes"]) == 4000


def test_anotar_algo_que_no_existe_da_404(cliente):
    assert cliente.post("/api/strategies/noexiste/nota", json={"notes": "a"}).status_code == 404
