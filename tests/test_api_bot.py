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


def _con_respaldo(**kw):
    """Un bot con las metricas que la cantera mira."""
    d = _doc()
    d["respaldo"] = {"trades": kw.get("trades", 200),
                     "profit_factor": kw.get("pf", 1.5),
                     "expectancy_r": kw.get("expr", 0.3),
                     "max_drawdown_pct": kw.get("dd", 10.0)}
    d["fuera_de_muestra"] = {"trades": kw.get("oos_trades", 80),
                             "profit_factor": kw.get("oos_pf", 1.2)}
    return d


@pytest.fixture()
def client(tmp_path):
    from botiquant.vivo.piloto import PILOTO
    with TestClient(create_app(workdir=tmp_path / "ws")) as c:
        yield c
    # Un bot que quede vivo entre pruebas las contamina todas: la siguiente
    # encuentra el piloto ocupado y falla por un motivo que no es el suyo.
    PILOTO.apagar(espera=5.0)
    PILOTO.vuelos.clear()


# ------------------------------------------------------------- apagado

def test_arranca_apagado(client):
    """Nada opera solo. Encender es siempre una decisión de alguien."""
    e = client.get("/api/bot").json()
    assert e["encendido"] is False and e["hay_bot"] is False
    assert e["vuelos"] == [] and e["porcion_libre"] == 1.0


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
    # con respaldo suficiente, para que lo que falle sea la CLAVE y no la
    # cantera: una prueba que pasa por el motivo equivocado no prueba nada
    r = client.post("/api/bot/encender",
                    json={"bot": _con_respaldo(), "modo": "practica"})
    assert r.status_code == 400
    assert "claves" in r.json()["detail"].lower()


def test_real_sin_clave_cargada_tampoco(client):
    r = client.post("/api/bot/encender",
                    json={"bot": _con_respaldo(), "modo": "real"})
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
    assert e["vuelos"][0]["manda_ordenes"] is False, (
        "el simulacro no puede mandar órdenes")
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
    assert next(iter(PILOTO.vuelos.values())).bot.perdida_maxima_diaria == 250.0
    client.post("/api/bot/apagar")


def test_sin_tope_declarado_queda_en_cero(client):
    """Cero es SIN tope. Inventar uno prudente por defecto detendria bots que
    su dueno no pidio detener, y a la hora equivocada."""
    from botiquant.vivo.piloto import PILOTO
    client.post("/api/bot/encender", json={"bot": _doc(), "modo": "simulacro"})
    assert next(iter(PILOTO.vuelos.values())).bot.perdida_maxima_diaria == 0.0
    client.post("/api/bot/apagar")


# ------------------------------------------------------------- la cantera


def test_no_se_puede_encender_en_real_una_estrategia_sin_probar(client):
    """La puerta que justifica toda la cantera.

    Sin esto se puede encender con plata real una estrategia de nueve
    operaciones — la aplicacion no tenia NADA que lo impidiera.
    """
    r = client.post("/api/bot/encender", json={
        "bot": _con_respaldo(trades=9, oos_trades=4), "modo": "real"})
    assert r.status_code == 422
    assert "todavía no puede operar" in str(r.json())


def test_sin_fuera_de_muestra_no_se_llega_a_real(client):
    d = _con_respaldo()
    d["fuera_de_muestra"] = {}
    r = client.post("/api/bot/encender", json={"bot": d, "modo": "real"})
    assert r.status_code == 422


def test_el_simulacro_no_pide_nada(client):
    """Mirar que haria el bot es gratis y tiene que seguir siendolo."""
    r = client.post("/api/bot/encender", json={
        "bot": _con_respaldo(trades=3, pf=0.2, dd=90.0), "modo": "simulacro"})
    assert r.status_code == 200, r.text
    client.post("/api/bot/apagar")


def test_la_puerta_vive_en_el_SERVIDOR_y_no_en_la_pantalla(client):
    """Una comprobacion que vive solo en el navegador la saltea cualquiera que
    llame al endpoint — y este es el unico endpoint que puede mover plata."""
    r = client.post("/api/bot/encender", json={
        "bot": _con_respaldo(trades=5), "modo": "real"})
    assert r.status_code == 422


def test_el_rechazo_dice_que_falta(client):
    r = client.post("/api/bot/encender", json={
        "bot": _con_respaldo(oos_trades=3), "modo": "real"})
    detalle = r.json()["detail"]
    assert "puertas" in detalle
    assert any(not p["pasa"] for p in detalle["puertas"])


# ----------------------------------------------- Binance, y sólo en demo

def test_binance_en_REAL_se_rechaza_en_el_ENDPOINT(client):
    """SE CORTA EN DOS LUGARES, Y LOS DOS HACEN FALTA.

    El adaptador ya no tiene forma de apuntar a la cuenta real —no acepta una
    base— así que aunque esto pasara, la orden iría igual a demo. Y ahí está el
    problema: el usuario habría pedido real y habría creído que operó en real.
    Un 400 explica por qué no se puede; un adaptador que igual opera en demo
    deja a alguien mirando números que no son los que cree.
    """
    r = client.post("/api/bot/encender",
                    json={"bot": _con_respaldo(), "modo": "real",
                          "exchange": "binance"})
    assert r.status_code == 400
    assert "sólo en demo" in r.json()["detail"]


def test_un_exchange_inventado_se_rechaza(client):
    r = client.post("/api/bot/encender",
                    json={"bot": _con_respaldo(), "modo": "practica",
                          "exchange": "kraken"})
    assert r.status_code == 400


def test_sin_decir_exchange_sigue_siendo_bingx(client):
    """Compatibilidad: los bots que ya existían no mandan `exchange`, y no
    pueden cambiar de casa por una actualización."""
    r = client.post("/api/bot/encender",
                    json={"bot": _con_respaldo(), "modo": "practica"})
    # falla por falta de clave de BingX, no por exchange desconocido
    assert r.status_code == 400
    assert "bingx" in r.json()["detail"].lower()


def test_binance_en_practica_pide_su_propia_clave(client):
    """La de BingX no sirve, y el mensaje tiene que nombrar a Binance: si
    dijera sólo "no hay claves guardadas", uno va a cargar la que ya tenía."""
    r = client.post("/api/bot/encender",
                    json={"bot": _con_respaldo(), "modo": "practica",
                          "exchange": "binance"})
    assert r.status_code == 400
    assert "binance" in r.json()["detail"].lower()


# ------------------------------------------------------- abrir un enlace

def test_solo_se_abren_NUESTROS_enlaces(client, monkeypatch):
    """SE PIDE POR NOMBRE Y NO POR URL.

    Es más fuerte que una lista blanca de direcciones: aunque alguien llame al
    endpoint a mano, lo único que puede pedir es uno de los nombres que la
    aplicación conoce. Un endpoint que abre la URL que le manden es un endpoint
    que manda a la gente adonde le manden.
    """
    import webbrowser
    abiertas = []
    monkeypatch.setattr(webbrowser, "open", lambda u: abiertas.append(u))

    r = client.post("/api/abrir-enlace", json={"nombre": "binance_clave"})
    assert r.status_code == 200
    assert abiertas == ["https://demo.binance.com/en/my/settings/api-management"]

    # una URL entera, que es lo que uno intentaría inyectar
    r = client.post("/api/abrir-enlace",
                    json={"nombre": "https://no-es-binance.example/robar"})
    assert r.status_code == 403
    assert len(abiertas) == 1, "abrió algo que no era nuestro"


def test_el_enlace_de_la_clave_es_el_de_DEMO(client, monkeypatch):
    """No el de binance.com a secas: esa sería la clave de la cuenta real, y
    la aplicación no puede operar con ella."""
    import webbrowser
    abiertas = []
    monkeypatch.setattr(webbrowser, "open", lambda u: abiertas.append(u))
    client.post("/api/abrir-enlace", json={"nombre": "binance_clave"})
    client.post("/api/abrir-enlace", json={"nombre": "binance_demo"})
    assert all(u.startswith("https://demo.binance.com/") for u in abiertas)


# ==================================== la porcion, desde el endpoint

def test_la_porcion_llega_hasta_el_bot(client):
    """Sin esto cada bot se cree dueño del 100% de la cuenta."""
    from botiquant.vivo.piloto import PILOTO
    r = client.post("/api/bot/encender",
                    json={"bot": _con_respaldo(), "modo": "simulacro",
                          "porcion": 0.25})
    assert r.status_code == 200
    assert next(iter(PILOTO.vuelos.values())).bot.porcion == 0.25
    assert r.json()["porcion_usada"] == 0.25


def test_sin_porcion_es_la_cuenta_entera(client):
    """Compatibilidad: un bot de antes no puede achicarse por actualizar."""
    from botiquant.vivo.piloto import PILOTO
    client.post("/api/bot/encender",
                json={"bot": _con_respaldo(), "modo": "simulacro"})
    assert next(iter(PILOTO.vuelos.values())).bot.porcion == 1.0


def test_una_porcion_imposible_se_rechaza(client):
    """Con 0 el bot dimensionaría sobre cero, no abriría nunca, y parecería
    que la estrategia no da señales."""
    r = client.post("/api/bot/encender",
                    json={"bot": _con_respaldo(), "modo": "simulacro",
                          "porcion": 0})
    assert r.status_code == 400


# ------------------------------------------- las promovidas que quedaron sin bot

def test_las_promovidas_sin_bot_se_ven_y_se_reencienden_con_un_clic(client, tmp_path):
    """Los bots mueren con la app y no se reencienden solos; la estrategia
    sigue en "práctica". Sin esto la pantalla decía "8 en práctica" con cero
    operando y ningún lugar donde verlo. Se listan, y un clic las reenciende
    a todas; sin clave, cada fallo dice por qué en vez de fallar en silencio."""
    import glob
    from botiquant import estados
    from botiquant.database.db import Database

    ruta = glob.glob(str(tmp_path / "ws" / "*.sqlite"))[0]
    db = Database(ruta)
    ds = db.insert_dataset("ETHUSDT H1", "binance", 100, "2024-01-01", "2024-12-31", "1h")
    sid = db.save_strategy("S-009", _doc()["estrategia"],
                           meta={"dataset_id": ds, "timeframe": "1h"})
    db.mover_estado(sid, estados.mover(estados.NUEVA, estados.VALIDADA), None)
    db.mover_estado(sid, estados.mover(estados.VALIDADA, estados.PRACTICA), None)

    e = client.get("/api/bot").json()
    assert [(a["name"], a["simbolo"]) for a in e["apagadas"]] == [("S-009", "ETH-USDT")]

    r = client.post("/api/bot/reencender").json()
    assert r["encendidas"] == []
    assert len(r["fallos"]) == 1 and "binance" in r["fallos"][0]["motivo"].lower()


def test_el_ciclo_no_promueve_lo_que_salio_sobreajustado_fuera_de_muestra(tmp_path):
    """Pasó de verdad: el ciclo promovió por las métricas del minado y una
    estrategia quedó operando con veredicto "sobreajustada" en la prueba
    fuera de muestra. Las métricas del minado son las de los datos donde se
    la encontró; el veredicto dice si aguanta en los que nunca vio.

    Arma su propia app: el orquestador es uno por proceso y queda atado a la
    base de la primera app que lo pidió."""
    import glob
    from botiquant import estados
    from botiquant import orquestador as orq
    from botiquant.database.db import Database

    orq.ORQUESTADOR = None
    try:
        with TestClient(create_app(workdir=tmp_path / "ws")) as c:
            db = Database(glob.glob(str(tmp_path / "ws" / "*.sqlite"))[0])
            ds = db.insert_dataset("ETHUSDT H1", "binance", 100, "2024-01-01",
                                   "2024-12-31", "1h")
            fuertes = {"trades": 200, "profit_factor": 1.5, "max_drawdown_pct": 10.0,
                       "expectancy_r": 0.3}
            buena = db.save_strategy("S-buena", _doc()["estrategia"],
                                     meta={"dataset_id": ds, "timeframe": "1h",
                                           "metrics": fuertes})
            mala = db.save_strategy("S-mala", _doc()["estrategia"],
                                    meta={"dataset_id": ds, "timeframe": "1h",
                                          "metrics": fuertes})
            for sid in (buena, mala):
                db.mover_estado(sid, estados.mover(estados.NUEVA, estados.VALIDADA), None)
            db.guardar_validacion(mala, {"veredicto": "overfitted", "tramos": 4,
                                         "tramos_ganadores": 1}, None)
            db.guardar_validacion(buena, {"veredicto": "robust", "tramos": 4,
                                          "tramos_ganadores": 4}, None)

            # Se le pregunta al lector del ciclo y se decide con `que_toca`,
            # sin encenderlo: encendido, promueve en la primera vuelta y ya no
            # queda nada que mirar.
            from botiquant import ciclo as cic
            c.get("/api/ciclo")                       # arma el orquestador
            est = orq.ORQUESTADOR.leer_estado()
            t = cic.que_toca(cic.Parametros.from_dict({"encendido": True}),
                             estrategias=est["estrategias"],
                             horas_desde_el_ultimo_minado=est["horas_desde_minado"],
                             en_practica=est["en_practica"])
            assert t.accion == cic.PROMOVER, t
            assert buena in t.ids and mala not in t.ids
    finally:
        orq.ORQUESTADOR = None


def test_el_ciclo_y_reencender_anotan_de_que_estrategia_salio_el_bot():
    """El botón manual ya guardaba `estrategia_id` en el documento del bot;
    el ciclo y "reencender" pasaban por otro camino y no. Tras un reinicio
    los ocho robots volvían sin id y la lista no podía saber cuáles estaban
    de verdad en el aire: "Operar 8" contra "Operando 9" (3 de septiembre de
    2026). No hay Binance en la suite, así que se mira el camino compartido."""
    import inspect
    import re
    from botiquant.api import app as mod

    fuente = inspect.getsource(mod)
    i = fuente.index("def _encender_del_ciclo")
    cuerpo = fuente[i:fuente.index("PILOTO.encender(Bot(", i)]
    assert re.search(r'doc\["estrategia_id"\]\s*=\s*str\(fila\.get\("id"\)', cuerpo), (
        "el camino del ciclo tiene que anotar de qué estrategia salió el bot "
        "ANTES de encenderlo")
