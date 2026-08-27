"""Encender el bot desde la aplicación.

Es la única acción de toda la aplicación que puede mover plata, así que lo que
se comprueba acá no es que funcione sino que NO funcione de más: que no arranque
sin que alguien haya dicho explícitamente en qué modo, que no opere sin clave,
y que el simulacro no necesite ninguna.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app


def _doc():
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return {
        "formato": "botiquant-bot", "version": 1, "nombre": "S-042",
        "ejecucion": {"simbolo": "BTC-USDT", "timeframe": "1h"},
        "estrategia": {
            "name": "S-042", "direction": "both",
            "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
            "entry_short": [{"left": ema(5), "op": "cross_below", "right": ema(20)}],
            "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                     "stop_type": "atr", "stop_value": 2.0,
                     "target_type": "atr", "target_value": 4.0, "atr_period": 14}},
    }


@pytest.fixture()
def client(tmp_path):
    from botiquant.vivo.piloto import PILOTO
    with TestClient(create_app(workdir=tmp_path / "ws")) as c:
        yield c
    # Un bot que quede vivo entre pruebas las contamina todas: la siguiente
    # encuentra el piloto ocupado y falla por un motivo que no es el suyo.
    PILOTO.apagar(espera=5.0)
    PILOTO.bot = None


# ------------------------------------------------------------- apagado

def test_arranca_apagado(client):
    """Nada opera solo. Encender es siempre una decisión de alguien."""
    assert client.get("/api/bot").json() == {"encendido": False, "hay_bot": False}


def test_apagar_lo_que_no_esta_encendido_no_revienta(client):
    assert client.post("/api/bot/apagar").json()["encendido"] is False


# ------------------------------------------------- lo que NO puede pasar

def test_sin_modo_no_arranca(client):
    """`modo` no tiene default a propósito.

    Un default que opere convierte un payload incompleto —un bug nuestro, un
    cliente viejo— en órdenes reales. Sin default, lo peor que pasa es que no
    arranque.
    """
    r = client.post("/api/bot/encender", json={"bot": _doc()})
    assert r.status_code == 400
    assert "modo" in r.json()["detail"]


def test_un_modo_inventado_no_arranca(client):
    r = client.post("/api/bot/encender", json={"bot": _doc(), "modo": "turbo"})
    assert r.status_code == 400


def test_sin_archivo_del_bot_no_arranca(client):
    r = client.post("/api/bot/encender", json={"modo": "simulacro"})
    assert r.status_code == 400


def test_practica_sin_clave_cargada_no_arranca(client):
    """Y lo dice claro. Antes de esto, arrancaba y fallaba en la primera vuelta
    con un error de red que no explicaba nada."""
    r = client.post("/api/bot/encender", json={"bot": _doc(), "modo": "practica"})
    assert r.status_code == 400
    assert "claves" in r.json()["detail"].lower()


def test_real_sin_clave_cargada_tampoco(client):
    r = client.post("/api/bot/encender", json={"bot": _doc(), "modo": "real"})
    assert r.status_code == 400


def test_un_archivo_que_no_es_nuestro_se_rechaza(client):
    r = client.post("/api/bot/encender",
                    json={"bot": {"formato": "otra-cosa"}, "modo": "simulacro"})
    assert r.status_code == 400


# --------------------------------------------------------- el simulacro

def test_el_simulacro_NO_necesita_ninguna_clave(client):
    """Es lo que lo hace útil.

    Si el simulacro pidiera credenciales, dejaría de servir para lo único que
    sirve: mirar qué haría el bot antes de haber creado siquiera la clave.
    """
    r = client.post("/api/bot/encender", json={"bot": _doc(), "modo": "simulacro"})
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["encendido"] is True
    assert e["manda_ordenes"] is False, "el simulacro no puede mandar órdenes"
    client.post("/api/bot/apagar")


def test_no_se_pueden_encender_dos(client):
    """Dos bots sobre la misma cuenta se pelean por la misma posición."""
    client.post("/api/bot/encender", json={"bot": _doc(), "modo": "simulacro"})
    r = client.post("/api/bot/encender", json={"bot": _doc(), "modo": "simulacro"})
    assert r.status_code == 409
    client.post("/api/bot/apagar")


def test_apagar_y_volver_a_encender(client):
    client.post("/api/bot/encender", json={"bot": _doc(), "modo": "simulacro"})
    assert client.post("/api/bot/apagar").json()["encendido"] is False
    r = client.post("/api/bot/encender", json={"bot": _doc(), "modo": "simulacro"})
    assert r.status_code == 200
    client.post("/api/bot/apagar")


# --------------------------------------------------------------- pánico

def test_el_panico_apaga(client):
    client.post("/api/bot/encender", json={"bot": _doc(), "modo": "simulacro"})
    e = client.post("/api/bot/panico").json()
    assert e["encendido"] is False
    assert "cerrado" in e


# ---------------------------------------------------- sólo en el escritorio

def test_servido_a_varios_no_existe(tmp_path, monkeypatch):
    """Un servidor compartido que opera con la cuenta de alguien es otro
    producto, con otras obligaciones."""
    monkeypatch.setenv("BQ_MULTIUSER", "1")
    import importlib

    from botiquant.api import app as modulo
    importlib.reload(modulo)
    try:
        with TestClient(modulo.create_app(workdir=tmp_path / "ws")) as c:
            assert c.get("/api/bot").status_code == 404
            assert c.post("/api/bot/encender",
                          json={"bot": _doc(), "modo": "simulacro"}).status_code == 404
    finally:
        monkeypatch.delenv("BQ_MULTIUSER", raising=False)
        importlib.reload(modulo)


def test_el_tope_de_perdida_llega_hasta_el_bot(client):
    """Se configura en la pantalla y tiene que llegar a la guarda.

    Estaba conectado del motor para abajo pero no habia forma de ponerlo desde
    la aplicacion: una proteccion que existe y no se puede activar no protege
    de nada.
    """
    from botiquant.vivo.piloto import PILOTO
    r = client.post("/api/bot/encender", json={
        "bot": _doc(), "modo": "simulacro", "perdida_maxima": 250.0})
    assert r.status_code == 200, r.text
    assert PILOTO.bot.perdida_maxima_diaria == 250.0
    client.post("/api/bot/apagar")


def test_sin_tope_declarado_queda_en_cero(client):
    """Cero es SIN tope. Inventar uno prudente por defecto detendria bots que
    su dueno no pidio detener, y a la hora equivocada."""
    from botiquant.vivo.piloto import PILOTO
    client.post("/api/bot/encender", json={"bot": _doc(), "modo": "simulacro"})
    assert PILOTO.bot.perdida_maxima_diaria == 0.0
    client.post("/api/bot/apagar")
