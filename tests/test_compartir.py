"""Compartir una estrategia con un enlace que se abre sin cuenta.

Lo que se publica es sólo la estrategia; el secreto que vuelve es lo único
que apaga el enlace; sin licencia y con un tope por día por dirección.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app


def _doc(nivel="usar"):
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}  # noqa: E731
    return {
        "nivel": nivel, "nombre": "S-007", "autor": "juan", "instrumento": "ETHUSDT H1",
        "timeframe": "1h", "direccion": "both", "bloques": "EMA crossover",
        "reglas": ["Entrada larga: EMA(20) cruza arriba de EMA(80)"], "salidas": "Stop 2×ATR",
        "costos": {"spread": 0.0, "slippage": 0.05, "commission_pct": 0.04, "initial_capital": 10000},
        "metricas": {"cagr_pct": 12.5, "max_drawdown_pct": 9.1, "profit_factor": 1.3, "trades": 210},
        "curva": [10000 + i * 7 for i in range(300)],
        "fechas": [f"2024-01-{1 + (i % 28):02d}" for i in range(300)],
        "validacion": {"estado": "aprobada", "tramos": 4, "tramos_ganadores": 4, "eficiencia": 0.8,
                       "retorno_fuera_pct": 22.0,
                       "detalle": {"tramos": [{"n": 1, "juzga": ["2024-01-01", "2024-06-01"], "afuera_pct": 5.0}]}},
        "mundo": "exchange",
        "spec": {
            "name": "S-007",
            "entry_long": [{"type": "cross_above", "left": ema(20), "right": ema(80)}],
            "entry_short": [],
            "risk": {"stop_type": "atr", "stop_value": 2.0, "reward_ratio": 2.0},
        },
    }


@pytest.fixture()
def c(tmp_path):
    with TestClient(create_app(workdir=tmp_path / "ws")) as cliente:
        yield cliente


def test_el_enlace_se_abre_sin_cuenta_y_se_puede_bajar(c):
    r = c.post("/api/compartir", json=_doc())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["codigo"] and d["secreto"] and d["url"].endswith("/s/" + d["codigo"])

    pagina = c.get(f"/s/{d['codigo']}")
    assert pagina.status_code == 200
    assert "S-007" in pagina.text and "ETHUSDT" in pagina.text and "Aprobada" in pagina.text
    assert "noindex" in pagina.text
    assert "Usar en TradingView" in pagina.text

    j = c.get(f"/api/s/{d['codigo']}").json()
    assert j["nombre"] == "S-007" and "spec" not in j, "las reglas ejecutables no viajan en el JSON"
    assert j["vistas"] == 1

    pine = c.get(f"/api/s/{d['codigo']}/pine")
    assert pine.status_code == 200 and "strategy(" in pine.text
    mq5 = c.get(f"/api/s/{d['codigo']}/mql5")
    assert mq5.status_code == 200 and "OnTick" in mq5.text


def test_para_mirar_no_entrega_las_reglas(c):
    d = c.post("/api/compartir", json=_doc("mirar")).json()
    assert c.get(f"/api/s/{d['codigo']}/pine").status_code == 403
    pagina = c.get(f"/s/{d['codigo']}").text
    assert "Usar en TradingView" not in pagina
    # ni las reglas escritas: "las reglas quedan con vos" tiene que ser cierto
    assert "cruza arriba" not in pagina
    assert "EMA crossover" not in pagina, "los bloques son la receta dicha en dos palabras"
    j = c.get(f"/api/s/{d['codigo']}").json()
    assert j["reglas"] == [] and j["bloques"] == ""


def test_apagar_exige_el_secreto_y_el_enlace_deja_de_abrir(c):
    d = c.post("/api/compartir", json=_doc()).json()
    assert c.post(f"/api/s/{d['codigo']}/apagar", json={"secreto": "otro"}).status_code == 404
    assert c.post(f"/api/s/{d['codigo']}/apagar", json={"secreto": d["secreto"]}).status_code == 200
    assert c.get(f"/s/{d['codigo']}").status_code == 410
    assert c.get(f"/api/s/{d['codigo']}/pine").status_code == 410


def test_no_publica_lo_que_no_es_la_estrategia(c):
    doc = _doc()
    doc["api_key"] = "SECRETA"
    doc["saldo"] = 1234
    d = c.post("/api/compartir", json=doc).json()
    j = c.get(f"/api/s/{d['codigo']}").json()
    assert "api_key" not in j and "saldo" not in j
    assert "SECRETA" not in c.get(f"/s/{d['codigo']}").text


def test_hay_un_tope_por_dia(c):
    for _ in range(30):
        assert c.post("/api/compartir", json=_doc()).status_code == 200
    assert c.post("/api/compartir", json=_doc()).status_code == 429


def test_un_enlace_que_no_existe(c):
    assert c.get("/s/nada").status_code == 404
    assert c.get("/api/s/nada").status_code == 404


def test_la_pagina_dice_con_que_costos_se_midio(c):
    """Cerraba con \"con los costos indicados\" sin indicar ninguno, y el
    documento traía los del mercado en pantalla en vez de los de la
    estrategia (2 de septiembre de 2026)."""
    d = c.post("/api/compartir", json=_doc()).json()
    pagina = c.get(f"/s/{d['codigo']}").text
    assert "Costos:" in pagina
    assert "comisión" in pagina and "0.040" in pagina
    assert "capital inicial" in pagina


def _doc_pf():
    return {
        "nivel": "mirar", "tipo": "portafolio", "autor": "nico",
        "nombre": "Portafolio · S-007 + S-002", "instrumento": "ETHUSDT + XMRUSDT",
        "timeframe": "", "direccion": "", "bloques": "", "reglas": [], "salidas": "",
        "costos": {}, "metricas": {"cagr_pct": 9.4, "max_drawdown_pct": 6.1, "avg_correlation": 0.05},
        "curva": [10000 + i * 5 for i in range(120)],
        "fechas": [f"2025-01-{1 + (i % 28):02d}" for i in range(120)],
        "validacion": None, "mundo": "exchange",
        "portafolio": {
            "nombres": ["S-007-ETH", "S-002-XMR"],
            "correlacion": 0.05,
            "ventana": {"from": "2024-08-27", "to": "2026-09-01"},
            "partes": [{"nombre": "S-007-ETH", "cagr_pct": 12.5, "riesgo_pct": 55.0},
                       {"nombre": "S-002-XMR", "cagr_pct": 6.3, "riesgo_pct": 45.0}],
        },
    }


def test_un_portafolio_se_comparte_y_dice_que_lo_compone(c):
    """Es la otra mitad del producto: el conjunto dice si dos estrategias se
    suman o son la misma apuesta, y eso es lo que uno quiere mostrar."""
    d = c.post("/api/compartir", json=_doc_pf()).json()
    pagina = c.get(f"/s/{d['codigo']}").text
    assert "Apuestas de verdad distintas" in pagina
    assert "S-007-ETH" in pagina and "S-002-XMR" in pagina
    assert "55% del riesgo" in pagina
    assert "2024-08-27" in pagina, "tiene que decir sobre qué ventana está medido"
    # y no promete reglas que no tiene
    assert "Usar en TradingView" not in pagina
    j = c.get(f"/api/s/{d['codigo']}").json()
    assert j["tipo"] == "portafolio" and j["portafolio"]["correlacion"] == 0.05


def test_un_portafolio_de_estrategias_parecidas_lo_dice(c):
    doc = _doc_pf()
    doc["portafolio"]["correlacion"] = 0.85
    d = c.post("/api/compartir", json=doc).json()
    assert "Son casi la misma apuesta" in c.get(f"/s/{d['codigo']}").text
