"""Validación: volver a correr lo encontrado sobre un período que se elige después.

La validación del minado reserva el tramo ANTES de buscar. Ésta lo elige
después, y por eso puede responder algo que la otra no: cómo le fue a esta
estrategia en el último año, o durante un año concreto.

Lo que decide si el resultado significa algo es el solapamiento. Volver a
correr una estrategia sobre las mismas velas con las que se la encontró
devuelve los mismos números por construcción y no valida nada — y como se ve
idéntico a un éxito, hay que medirlo y avisarlo.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app


@pytest.fixture(scope="module")
def minado(tmp_path_factory):
    """Un workspace con una corrida real archivada."""
    app = create_app(workdir=tmp_path_factory.mktemp("val"))
    with TestClient(app) as c:
        ds = c.post("/api/datasets/sample",
                    json={"symbol": "EURUSD", "bars": 4000}).json()["id"]
        arranque = c.post("/api/mine", json={
            "dataset_id": ds, "target_keep": 3, "max_candidates": 200,
            "min_trades": 5, "seed": 7, "timeframe": "1h",
            "settings": {"spread": 0.0001, "slippage": 0.0, "initial_capital": 10000},
        })
        assert arranque.status_code == 200, f"{arranque.status_code}: {arranque.text[:300]}"
        jid = arranque.json()["job_id"]
        for _ in range(900):
            if c.get(f"/api/jobs/{jid}").json()["status"] != "running":
                break
            time.sleep(0.1)
        filas = c.get("/api/banco").json()
        assert filas, "la corrida no dejó nada que validar"
        rango = c.get("/api/corridas").json()["corridas"][0]["contexto"]["measured_range"]
        yield c, ds, filas, rango


def test_valida_una_del_banco_sobre_otro_periodo(minado):
    c, _ds, filas, rango = minado
    # la segunda mitad del histórico medido
    mitad = rango["to"][:10]
    r = c.post("/api/validar", json={
        "estrategias": [{"origen": "banco", "id": filas[0]["banco_id"]}],
        "date_from": rango["from"][:10], "date_to": mitad,
    })
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["periodo"]["to"] == mitad
    fila = cuerpo["resultados"][0]
    assert fila["nombre"] == filas[0]["name"]
    assert "antes" in fila, "tiene que traer con qué comparar"
    assert "error" not in fila, fila.get("error")
    assert fila["despues"]["trades"] > 0, "tiene que haber operado de verdad"
    assert fila["ratio"] is not None


def test_avisa_cuando_el_periodo_ya_lo_vio_la_busqueda(minado):
    """El caso que arruina la validación sin que se note: pedir el MISMO tramo
    con el que se minó. Los números vuelven iguales y parecen una confirmación."""
    c, _ds, filas, rango = minado
    r = c.post("/api/validar", json={
        "estrategias": [{"origen": "banco", "id": filas[0]["banco_id"]}],
        "date_from": rango["from"][:10], "date_to": rango["to"][:10],
    }).json()["resultados"][0]

    assert r["solapamiento_pct"] > 95, (
        "validar sobre el tramo minado tiene que reportarse como solapado")


def test_un_periodo_realmente_nuevo_no_marca_solapamiento(minado):
    c, _ds, filas, _rango = minado
    r = c.post("/api/validar", json={
        "estrategias": [{"origen": "banco", "id": filas[0]["banco_id"]}],
        "date_from": "1990-01-01", "date_to": "1991-01-01",
    }).json()["resultados"][0]

    assert r["solapamiento_pct"] == 0.0


def test_valida_varias_de_una_vez(minado):
    c, _ds, filas, rango = minado
    pedidas = [{"origen": "banco", "id": f["banco_id"]} for f in filas[:3]]
    r = c.post("/api/validar", json={
        "estrategias": pedidas,
        "date_from": rango["from"][:10], "date_to": rango["to"][:10],
    }).json()

    assert len(r["resultados"]) == len(pedidas)
    assert {x["nombre"] for x in r["resultados"]} == {f["name"] for f in filas[:3]}
    assert all("error" not in x for x in r["resultados"])

    # y validar sobre el MISMO tramo devuelve los MISMOS numeros: es lo que
    # hace que un solapamiento alto no signifique nada
    for x in r["resultados"]:
        assert x["despues"]["trades"] == x["antes"]["trades"]
        assert x["ratio"] == 1.0


def test_tambien_valida_una_guardada(minado):
    """El contexto de una guardada vive en su `meta` y no en una corrida: la
    validación tiene que poder leer las dos formas."""
    c, _ds, filas, rango = minado
    c.post("/api/banco/guardar", json={"ids": [filas[0]["banco_id"]]})
    sid = c.get("/api/strategies").json()[0]["id"]

    r = c.post("/api/validar", json={
        "estrategias": [{"origen": "guardada", "id": sid}],
        "date_from": rango["from"][:10], "date_to": rango["to"][:10],
    })
    assert r.status_code == 200
    fila = r.json()["resultados"][0]
    assert fila["origen"] == "guardada"
    assert "error" not in fila, fila.get("error")
    assert fila["despues"]["trades"] > 0


def test_sin_periodo_no_corre(minado):
    c, _ds, filas, _r = minado
    r = c.post("/api/validar", json={
        "estrategias": [{"origen": "banco", "id": filas[0]["banco_id"]}]})
    assert r.status_code == 400


def test_una_estrategia_que_ya_no_esta_da_404(minado):
    c, _ds, _f, rango = minado
    r = c.post("/api/validar", json={
        "estrategias": [{"origen": "banco", "id": "no-existe"}],
        "date_from": rango["from"][:10], "date_to": rango["to"][:10]})
    assert r.status_code == 404


# ---------------------------------------------------------------- Monte Carlo
def test_montecarlo_desde_una_del_banco(minado):
    """No hace falta guardar un resultado antes: se le corre el backtest a la
    estrategia y se rebarajan sus operaciones reales."""
    c, _ds, filas, _r = minado
    r = c.post("/api/montecarlo", json={
        "estrategia": {"origen": "banco", "id": filas[0]["banco_id"]},
        "simulations": 300, "seed": 5,
    })
    assert r.status_code == 200, r.text
    mc = r.json()
    assert mc["simulations"] == 300
    assert mc["trades_per_sim"] >= 5
    # lo que el usuario mira
    assert 0 <= mc["final_equity"]["prob_loss"] <= 100
    assert 0 <= mc["risk_of_ruin_pct"] <= 100
    assert len(mc["bands"]["p50"]) == len(mc["bands"]["steps"])
    assert mc["max_drawdown_pct"]["p95"] >= mc["max_drawdown_pct"]["median"]


def test_montecarlo_es_reproducible(minado):
    """Misma semilla, mismo resultado: si no, dos corridas seguidas dan
    riesgos de ruina distintos y el número deja de significar algo."""
    c, _ds, filas, _r = minado
    pedido = {"estrategia": {"origen": "banco", "id": filas[0]["banco_id"]},
              "simulations": 200, "seed": 11}
    a = c.post("/api/montecarlo", json=pedido).json()
    b = c.post("/api/montecarlo", json=pedido).json()
    assert a["risk_of_ruin_pct"] == b["risk_of_ruin_pct"]
    assert a["final_equity"]["median"] == b["final_equity"]["median"]


def test_montecarlo_necesita_operaciones_suficientes(minado):
    c, _ds, _f, _r = minado
    r = c.post("/api/montecarlo", json={"trade_pnls": [1.0, -2.0]})
    assert r.status_code == 400
    assert "5" in r.json()["detail"]


# ------------------------------------------------- robustez comparada
def test_robustez_corre_sobre_todas_y_las_rankea(minado):
    """El error que tenía la pantalla: con cuatro seleccionadas simulaba una
    sola, en silencio. Y de a una el número no sirve para decidir — 12% de
    probabilidad de perder no es bueno ni malo hasta compararlo."""
    c, _ds, filas, _r = minado
    pedidas = [{"origen": "banco", "id": f["banco_id"]} for f in filas[:3]]
    r = c.post("/api/robustez", json={"estrategias": pedidas, "simulations": 200})
    assert r.status_code == 200, r.text
    cuerpo = r.json()

    assert len(cuerpo["resultados"]) == len(pedidas), "tiene que simular TODAS"
    sanas = [x for x in cuerpo["resultados"] if "mc" in x]
    assert sanas, "ninguna pudo simularse"
    # el ranking va de menor a mayor probabilidad de perder plata
    puestos = sorted(sanas, key=lambda x: x["puesto"])
    probs = [x["prob_perder"] for x in puestos]
    assert probs == sorted(probs)
    assert puestos[0]["puesto"] == 1
    for x in sanas:
        assert 0 <= x["prob_perder"] <= 100
        assert x["operaciones"] >= 5


def test_robustez_sin_estrategias_no_corre(minado):
    c, _ds, _f, _r = minado
    assert c.post("/api/robustez", json={"estrategias": []}).status_code == 400
