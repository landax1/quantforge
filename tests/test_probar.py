"""Poner a prueba: una acción, dos pruebas, un veredicto que queda guardado.

Antes esto eran dos secciones del menú —Monte Carlo y Walk-forward— con el
mismo selector de estrategias repetido y ningún registro de lo que devolvían.
Se corría el walk-forward, salía un veredicto, y al cambiar de pantalla se
perdía: la lista de estrategias no podía decir cuáles estaban probadas.

Lo que se prueba acá es lo que hace que el flujo funcione:

* el veredicto SOBREVIVE, porque de eso depende la columna de estado;
* sólo se puede probar lo guardado, que es lo que le da sentido a guardar;
* el estado se puede volver a 'sin probar', porque editarle las salidas a una
  estrategia deja el veredicto viejo describiendo otra cosa.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app


def _esperar(c, jid, limite=1800):
    for _ in range(limite):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.1)
    raise AssertionError("el trabajo no terminó")


@pytest.fixture(scope="module")
def guardada(tmp_path_factory):
    """Un workspace con una estrategia real ya guardada."""
    app = create_app(workdir=tmp_path_factory.mktemp("probar"))
    with TestClient(app) as c:
        ds = c.post("/api/datasets/sample",
                    json={"symbol": "EURUSD", "bars": 6000}).json()["id"]
        arranque = c.post("/api/mine", json={
            "dataset_id": ds, "target_keep": 1, "max_candidates": 200,
            "min_trades": 10, "seed": 11, "timeframe": "1h",
            "settings": {"spread": 0.0001, "initial_capital": 10000},
        })
        assert arranque.status_code == 200, arranque.text[:300]
        _esperar(c, arranque.json()["job_id"])
        filas = c.get("/api/banco").json()
        assert filas, "la corrida no dejó nada que guardar"
        r = c.post("/api/banco/guardar", json={"ids": [filas[0]["banco_id"]]})
        assert r.status_code == 200, r.text[:300]
        sid = c.get("/api/strategies").json()[0]["id"]
        yield c, sid


def test_una_estrategia_recien_guardada_esta_sin_probar(guardada):
    c, sid = guardada
    fila = next(s for s in c.get("/api/strategies").json() if s["id"] == sid)
    assert fila["validacion"] == {}, "no debería traer veredicto sin haberla probado"


def test_probar_deja_un_veredicto_que_sobrevive(guardada):
    c, sid = guardada
    arranque = c.post("/api/probar", json={"strategy_id": sid})
    assert arranque.status_code == 200, arranque.text[:400]
    j = _esperar(c, arranque.json()["job_id"])
    assert j["status"] == "done", j.get("error")
    out = j["result"]

    assert out["estado"] in ("aprobada", "aceptable", "no_paso")
    assert out["tramos"] >= 2, "una prueba de un solo tramo no distingue suerte"
    assert 0 <= out["tramos_ganadores"] <= out["tramos"]
    assert out["periodo"]["from"] < out["periodo"]["to"]
    # el detalle viaja para poder dibujar la curva fuera de muestra
    assert out["detalle"]["oos_equity"], "sin curva no hay nada que mostrar"

    # y esto es lo que antes se perdía: el veredicto sigue ahí después
    fila = next(s for s in c.get("/api/strategies").json() if s["id"] == sid)
    v = fila["validacion"]
    assert v["estado"] == out["estado"]
    assert v["eficiencia"] == out["eficiencia"]
    assert "detalle" not in v, "la curva no se guarda: son cientos de puntos por fila"
    assert v["probada"], "tiene que quedar cuándo se probó"


def test_monte_carlo_viaja_resumido_y_no_como_tablero(guardada):
    """De Monte Carlo se guardan los dos números que se miran, no la distribución.

    Rebaraja las operaciones de la estrategia, así que la ganancia total sale
    igual en las mil simulaciones: no puede detectar sobreajuste. Lo único que
    aporta es el camino — qué caída habría habido que aguantar."""
    c, sid = guardada
    v = next(s for s in c.get("/api/strategies").json() if s["id"] == sid)["validacion"]
    mc = v.get("mc")
    if mc is None:
        pytest.skip("esta estrategia no llegó a 5 operaciones")
    assert set(mc) >= {"dd_tipico_pct", "dd_malo_pct", "ruina_pct", "prob_perder_pct"}
    assert mc["dd_malo_pct"] >= mc["dd_tipico_pct"], "el percentil 95 no puede ser menor"
    assert 0 <= mc["ruina_pct"] <= 100


def test_el_estado_se_puede_borrar(guardada):
    c, sid = guardada
    assert c.delete(f"/api/probar/{sid}").status_code == 200
    fila = next(s for s in c.get("/api/strategies").json() if s["id"] == sid)
    assert fila["validacion"] == {}


def test_no_se_prueba_lo_que_no_esta_guardado(guardada):
    """Una fila del databank no se puede probar: guardar es lo que habilita esto."""
    c, _sid = guardada
    banco = c.get("/api/banco").json()
    r = c.post("/api/probar", json={"strategy_id": banco[0]["banco_id"]})
    assert r.status_code == 404, f"un id del banco no debería servir: {r.status_code}"


def test_sin_estrategia_no_corre(guardada):
    c, _sid = guardada
    assert c.post("/api/probar", json={}).status_code == 400
