"""El banco: lo que el databank deja de perder al empezar otra búsqueda.

Hasta acá el databank vivía en la memoria del trabajo en curso. Arrancar una
corrida nueva lo borraba entero y sin avisar, así que comparar dos
configuraciones significaba anotar los números a mano antes de apretar
Iniciar. Estos tests cubren lo que hace falta para que eso deje de pasar:
que la corrida quede archivada con su contexto, que se pueda ordenar y filtrar,
que se puedan rescatar varias de un saque, y que el banco tenga un techo.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from botiquant.api.app import create_app
from botiquant.core.jobs import JobManager
from botiquant.database.db import Database


# --------------------------------------------------------------------- ayudas
def _fila(i: int, *, pf: float = 1.5, cagr: float = 20.0, dd: float = 10.0,
          oos: float | None = None) -> dict:
    return {
        "name": f"S-{i:03d}", "spec": {"name": f"S-{i:03d}"}, "score": 90 - i,
        "oos_ratio": oos, "stop_mult": 2.0, "blocks": "EMA cross",
        "genes_label": "EMA(20)/EMA(80)",
        "metrics": {"cagr_pct": cagr, "profit_factor": pf, "max_drawdown_pct": dd,
                    "trades": 40 + i, "months_positive_pct": 55.0},
    }


def _corrida(db: Database, nombre: str = "EURUSD", *, filas: list[dict] | None = None,
             tf: str = "1h", riesgo: float = 1.0, user_id: str | None = None) -> str:
    return db.guardar_corrida(
        dataset_id=f"ds-{nombre}", dataset_name=nombre, timeframe=tf, seed=7,
        tested=300, elapsed=12.5, ended="completa",
        contexto={
            "direction": "long",
            "risk": {"size_mode": "risk_pct", "size_value": riesgo, "reward_ratio": 2.0},
            "settings": {"initial_capital": 10_000.0, "spread": 0.36,
                         "slippage": 0.1, "commission_pct": 0.0},
            "measured_range": {"from": "2015-01-01 00:00:00", "to": "2020-01-01 00:00:00"},
        },
        filas=filas if filas is not None else [_fila(0), _fila(1)],
        user_id=user_id)["id"]


@pytest.fixture()
def db(tmp_path) -> Database:
    return Database(tmp_path / "botiquant.sqlite")


# ------------------------------------------------------- archivo de la corrida
def test_una_corrida_sobrevive_a_la_siguiente(db):
    """El motivo de todo esto: minar de nuevo ya no borra lo anterior."""
    _corrida(db, "EURUSD")
    _corrida(db, "XAUUSD")

    corridas = db.list_corridas()
    assert [c["dataset_name"] for c in corridas] == ["XAUUSD", "EURUSD"]
    assert db.contar_banco() == 4


def test_cada_fila_sabe_de_que_corrida_salio(db):
    """Sin esto el banco es una bolsa: cien estrategias sin decir sobre qué
    instrumento ni con qué filtros se encontró cada una."""
    a = _corrida(db, "EURUSD", tf="1h")
    b = _corrida(db, "XAUUSD", tf="15m")

    assert {f["corrida_id"] for f in db.list_banco(corrida_id=a)} == {a}
    assert len(db.list_banco(corrida_id=b)) == 2
    assert len(db.list_banco()) == 4


def test_el_contexto_viaja_con_la_corrida(db):
    """Una fila del banco sin su riesgo es un número sin unidad: 20% anual al
    1% de riesgo y 20% al 3% no son la misma estrategia."""
    cid = _corrida(db, "EURUSD", riesgo=2.5)
    ctx = db.list_corridas()[0]["contexto"]

    assert ctx["risk"]["size_value"] == 2.5
    assert ctx["settings"]["spread"] == 0.36
    assert ctx["measured_range"]["from"] == "2015-01-01 00:00:00"
    assert db.list_corridas()[0]["id"] == cid


# ------------------------------------------------------------------ el orden
def test_se_ordena_por_profit_factor_en_los_dos_sentidos(db):
    _corrida(db, "EURUSD", filas=[_fila(0, pf=1.2), _fila(1, pf=2.4), _fila(2, pf=1.8)])

    baja = [f["metrics"]["profit_factor"] for f in db.list_banco(orden="pf")]
    sube = [f["metrics"]["profit_factor"] for f in db.list_banco(orden="pf", desc=False)]

    assert baja == [2.4, 1.8, 1.2]
    assert sube == [1.2, 1.8, 2.4]


def test_en_la_caida_maxima_el_primer_clic_muestra_las_mejores(db):
    """Menos drawdown es mejor. Si el primer clic ordenara descendente como en
    las demás, la columna arrancaría mostrando las peores."""
    _corrida(db, "EURUSD", filas=[_fila(0, dd=30), _fila(1, dd=8), _fila(2, dd=19)])

    assert [f["metrics"]["max_drawdown_pct"] for f in db.list_banco(orden="dd")] == [8, 19, 30]


def test_las_que_no_tienen_dato_van_siempre_al_fondo(db):
    """Pedir "las mejores fuera de muestra" no puede arrancar con las que ni
    siquiera se midieron fuera de muestra."""
    _corrida(db, "EURUSD", filas=[_fila(0), _fila(1, oos=0.9), _fila(2, oos=0.4)])

    orden = [f["oos_ratio"] for f in db.list_banco(orden="oos")]
    assert orden == [0.9, 0.4, None]
    # y tampoco al invertir el sentido
    assert [f["oos_ratio"] for f in db.list_banco(orden="oos", desc=False)] == [0.4, 0.9, None]


def test_un_orden_desconocido_no_rompe_ni_inventa(db):
    """El orden llega por querystring: cualquiera puede mandar cualquier cosa,
    y una columna sin validar es una inyección de SQL."""
    _corrida(db, "EURUSD")
    filas = db.list_banco(orden="'; DROP TABLE banco; --")

    assert len(filas) == 2
    assert db.contar_banco() == 2


# -------------------------------------------------------------- selección
def test_se_borran_varias_de_un_saque(db):
    cid = _corrida(db, "EURUSD", filas=[_fila(i) for i in range(5)])
    ids = [f["banco_id"] for f in db.list_banco(corrida_id=cid)][:3]

    assert db.borrar_banco(ids) == 3
    assert db.contar_banco() == 2


def test_borrar_la_corrida_se_lleva_sus_filas(db):
    a = _corrida(db, "EURUSD", filas=[_fila(i) for i in range(4)])
    _corrida(db, "XAUUSD", filas=[_fila(9)])

    assert db.borrar_corrida(a) == 1
    assert db.contar_banco() == 1
    assert [c["dataset_name"] for c in db.list_corridas()] == ["XAUUSD"]


# ------------------------------------------------------------------- el tope
def test_el_tope_poda_corridas_enteras(db):
    """Media corrida es peor que ninguna: el puesto 1 de 25 significa algo, y
    el puesto 1 de las 9 que sobrevivieron significa otra cosa que nadie pidió."""
    db.TOPE_BANCO = 10
    db.TOPE_CORRIDAS = 40
    for k in range(5):
        _corrida(db, f"C{k}", filas=[_fila(i) for i in range(4)])

    vivas = db.list_corridas()
    assert db.contar_banco() <= 10
    # ninguna corrida quedó a medias
    for c in vivas:
        assert c["n"] == 4
    # y las que sobreviven son las últimas
    assert [c["dataset_name"] for c in vivas] == ["C4", "C3"]


def test_lo_recien_minado_nunca_es_lo_que_se_poda(db):
    """Aunque la corrida sola supere el tope. Tirar lo que el usuario acaba de
    esperar diez minutos sería la peor forma posible de aplicar un límite."""
    db.TOPE_BANCO = 10
    _corrida(db, "VIEJA", filas=[_fila(i) for i in range(4)])
    _corrida(db, "GRANDE", filas=[_fila(i) for i in range(25)])

    assert [c["dataset_name"] for c in db.list_corridas()] == ["GRANDE"]
    assert db.contar_banco() == 25


def test_tambien_hay_tope_de_corridas(db):
    db.TOPE_CORRIDAS = 3
    for k in range(6):
        _corrida(db, f"C{k}", filas=[_fila(0)])

    assert len(db.list_corridas()) == 3


# ---------------------------------------------------------------- de a quién
def test_el_banco_de_otro_no_se_ve_ni_se_borra(db):
    mio = _corrida(db, "EURUSD", user_id="yo")
    _corrida(db, "XAUUSD", user_id="vos")

    assert [c["dataset_name"] for c in db.list_corridas("yo")] == ["EURUSD"]
    assert db.contar_banco("yo") == 2

    ajenas = [f["banco_id"] for f in db.list_banco(user_id="vos")]
    assert db.borrar_banco(ajenas, user_id="yo") == 0
    assert db.contar_banco("vos") == 2
    assert db.get_banco(ajenas, user_id="yo") == []
    assert db.borrar_corrida(mio, user_id="vos") == 0


# -------------------------------------------------------------------- pausa
def test_pausar_no_pierde_lo_encontrado_y_reanudar_sigue():
    """Detener descarta la población y los genomas ya probados. Pausar los
    conserva: es la diferencia entre continuar y volver a empezar."""
    jobs = JobManager(max_running=2)
    visto = {"vueltas": 0}

    def trabajo(handle):
        for _ in range(400):
            if handle.paused:
                handle.esperar()
            if handle.cancelled:
                break
            visto["vueltas"] += 1
            time.sleep(0.002)
        return visto["vueltas"]

    jid = jobs.submit_streaming("mine", trabajo)
    time.sleep(0.05)
    assert jobs.pause(jid, True) is True

    time.sleep(0.05)
    congelado = visto["vueltas"]
    time.sleep(0.15)
    assert visto["vueltas"] == congelado          # de verdad frenó

    assert jobs.get(jid).to_dict()["paused"] is True
    jobs.pause(jid, False)
    time.sleep(0.1)
    assert visto["vueltas"] > congelado           # y de verdad siguió
    jobs.cancel(jid)


def test_cancelar_despierta_a_una_busqueda_en_pausa():
    """Sin esto el hilo queda dormido esperando un reanudar que no llega
    nunca, y con él el lugar que ocupa en la cola."""
    jobs = JobManager(max_running=2)
    fin = {"ok": False}

    def trabajo(handle):
        while True:
            if handle.paused:
                handle.esperar()
            if handle.cancelled:
                fin["ok"] = True
                return None
            time.sleep(0.005)

    jid = jobs.submit_streaming("mine", trabajo)
    time.sleep(0.05)
    jobs.pause(jid, True)
    time.sleep(0.1)                                # ya está dormido adentro

    jobs.cancel(jid)
    # que el evento quede puesto es lo que lo despierta en el acto. Sin esto
    # igual saldría, pero recién cuando venciera la espera de medio segundo:
    # el test pasaría y el arreglo no estaría.
    assert jobs.get(jid).reanudar.is_set() is True
    assert jobs.get(jid).paused is False

    time.sleep(0.3)
    assert fin["ok"] is True
    assert jobs.get(jid).status == "done"


def test_no_se_pausa_algo_que_ya_termino():
    jobs = JobManager(max_running=2)
    jid = jobs.submit("x", lambda p: 1)
    time.sleep(0.15)

    assert jobs.pause(jid, True) is False
    assert jobs.pause("no-existe", True) is False


# ----------------------------------------------------------------- por la API
@pytest.fixture()
def client(tmp_path):
    app = create_app(workdir=tmp_path)
    with TestClient(app) as c:
        yield c


def test_minar_deja_la_corrida_archivada(client):
    """La prueba de punta a punta: se mina y el banco queda, sin que la
    pantalla haya tenido que guardar nada."""
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD", "bars": 1200}).json()["id"]
    jid = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 3, "max_candidates": 120,
        "min_trades": 3, "seed": 5,
        "settings": {"spread": 0.0001, "slippage": 0.0},
    }).json()["job_id"]

    for _ in range(600):
        job = client.get(f"/api/jobs/{jid}").json()
        if job["status"] != "running":
            break
        time.sleep(0.1)
    assert job["status"] == "done", job.get("error")

    banco = client.get("/api/corridas").json()
    assert len(banco["corridas"]) == 1
    corrida = banco["corridas"][0]
    assert corrida["n"] == banco["total"] > 0
    assert corrida["dataset_name"].startswith("EURUSD")
    assert corrida["contexto"]["measured_range"]["from"]
    assert banco["tope"] >= 100

    filas = client.get("/api/banco", params={"orden": "pf"}).json()
    pf = [f["metrics"]["profit_factor"] for f in filas]
    assert pf == sorted(pf, reverse=True)


def test_guardar_del_banco_usa_el_contexto_de_su_corrida(client):
    """Guardar mirando la configuración de la pantalla le pegaría a una
    estrategia de EURUSD los costos que hoy están cargados para otro mercado."""
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD", "bars": 1200}).json()["id"]
    jid = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 2, "max_candidates": 120,
        "min_trades": 3, "seed": 5, "timeframe": "1h",
        "settings": {"spread": 0.0002, "slippage": 0.0},
        "risk": {"size_mode": "risk_pct", "size_value": 1.5, "reward_ratio": 2.0},
    }).json()["job_id"]
    for _ in range(600):
        if client.get(f"/api/jobs/{jid}").json()["status"] != "running":
            break
        time.sleep(0.1)

    filas = client.get("/api/banco").json()
    assert filas, "la corrida no dejó nada en el banco"
    ids = [f["banco_id"] for f in filas[:2]]

    r = client.post("/api/banco/guardar", json={"ids": ids})
    assert r.status_code == 200
    assert len(r.json()["guardadas"]) == len(ids)

    guardadas = client.get("/api/strategies").json()
    assert len(guardadas) == len(ids)
    meta = guardadas[0]["meta"]
    assert meta["dataset_name"].startswith("EURUSD")
    assert meta["timeframe"] == "1h"
    assert meta["riskPct"] == 1.5
    assert meta["rr"] == 2.0
    assert meta["spread"] == 0.0002
    # sin esto, reabrirla corre el backtest sobre toda la historia y da otra cosa
    assert meta["measured_range"]["from"]
    assert meta["metrics"]["profit_factor"] is not None


def test_guardar_del_banco_no_borra_del_banco(client):
    """Guardar es copiar a un estante aparte. Si además sacara la fila del
    banco, revisar una corrida la iría vaciando a medida que se la mira."""
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD", "bars": 1200}).json()["id"]
    jid = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 2, "max_candidates": 120,
        "min_trades": 3, "seed": 5, "settings": {"spread": 0.0001},
    }).json()["job_id"]
    for _ in range(600):
        if client.get(f"/api/jobs/{jid}").json()["status"] != "running":
            break
        time.sleep(0.1)

    antes = client.get("/api/corridas").json()["total"]
    ids = [f["banco_id"] for f in client.get("/api/banco").json()[:1]]
    client.post("/api/banco/guardar", json={"ids": ids})

    assert client.get("/api/corridas").json()["total"] == antes


def test_borrar_del_banco_por_la_api(client):
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD", "bars": 1200}).json()["id"]
    jid = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 3, "max_candidates": 120,
        "min_trades": 3, "seed": 5, "settings": {"spread": 0.0001},
    }).json()["job_id"]
    for _ in range(600):
        if client.get(f"/api/jobs/{jid}").json()["status"] != "running":
            break
        time.sleep(0.1)

    filas = client.get("/api/banco").json()
    ids = [f["banco_id"] for f in filas[:2]]
    assert client.post("/api/banco/borrar", json={"ids": ids}).json()["borradas"] == 2
    assert client.get("/api/corridas").json()["total"] == len(filas) - 2

    cid = client.get("/api/corridas").json()["corridas"][0]["id"]
    assert client.delete(f"/api/corridas/{cid}").json()["borradas"] == 1
    assert client.get("/api/corridas").json()["total"] == 0


def test_una_corrida_sin_resultados_queda_anotada_igual(client):
    """Es el experimento que MÁS conviene recordar: dice que con esa vara, sobre
    ese instrumento, se probaron cientos de candidatas y no pasó ninguna. Sin el
    registro, dentro de un mes se vuelve a intentar exactamente lo mismo."""
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD", "bars": 1200}).json()["id"]
    jid = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 5, "max_candidates": 40,
        "seed": 5, "settings": {"spread": 0.0001},
        # inalcanzable de verdad: 1200 velas no dan un millón de operaciones.
        # Un profit factor altísimo NO sirve para esto — una estrategia sin
        # ninguna operación perdedora tiene profit factor infinito y pasa.
        "min_trades": 1_000_000,
    }).json()["job_id"]
    for _ in range(600):
        if client.get(f"/api/jobs/{jid}").json()["status"] != "running":
            break
        time.sleep(0.1)

    banco = client.get("/api/corridas").json()
    assert len(banco["corridas"]) == 1
    corrida = banco["corridas"][0]
    assert corrida["encontradas"] == 0
    assert corrida["n"] == 0
    assert corrida["tested"] > 0             # buscó de verdad
    assert corrida["contexto"]["min_trades"] == 1_000_000
    # y no ocupa lugar del banco, que se mide en estrategias
    assert banco["total"] == 0


def test_encontradas_distingue_lo_que_borraste_de_lo_que_nunca_hubo(client):
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD", "bars": 1200}).json()["id"]
    jid = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 3, "max_candidates": 120,
        "min_trades": 3, "seed": 5, "settings": {"spread": 0.0001},
    }).json()["job_id"]
    for _ in range(600):
        if client.get(f"/api/jobs/{jid}").json()["status"] != "running":
            break
        time.sleep(0.1)

    hallo = client.get("/api/corridas").json()["corridas"][0]["encontradas"]
    assert hallo > 0

    ids = [f["banco_id"] for f in client.get("/api/banco").json()]
    client.post("/api/banco/borrar", json={"ids": ids})

    corrida = client.get("/api/corridas").json()["corridas"][0]
    assert corrida["n"] == 0            # no queda ninguna
    assert corrida["encontradas"] == hallo   # pero sí había encontrado


def test_guardar_algo_que_ya_no_esta_avisa(client):
    assert client.post("/api/banco/guardar", json={"ids": ["no-existe"]}).status_code == 404


def test_el_ciclo_puede_pedir_que_lo_minado_quede_guardado(client):
    """El ciclo minaba para el banco y nada más: sin esto, sólo llegaba a
    validar y promover lo que una persona guardó a mano. Con la marca, lo que
    queda en el banco queda también en Mis estrategias, como nuevo."""
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD", "bars": 1200}).json()["id"]
    jid = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 2, "max_candidates": 120,
        "min_trades": 3, "seed": 5, "timeframe": "1h",
        "settings": {"spread": 0.0002, "slippage": 0.0},
        "guardar_al_terminar": True, "sin_trailing": True,
    }).json()["job_id"]
    for _ in range(600):
        job = client.get(f"/api/jobs/{jid}").json()
        if job["status"] != "running":
            break
        time.sleep(0.1)
    assert job["status"] == "done", job.get("error")

    banco = client.get("/api/banco").json()
    guardadas = client.get("/api/strategies").json()
    assert banco and len(guardadas) == len(banco)
    assert {g["estado"] for g in guardadas} == {"nueva"}
    assert guardadas[0]["meta"]["dataset_name"].startswith("EURUSD")
    # Y SIN TRAILING, que el ciclo pide y el endpoint no pasaba: minaba con
    # trailing igual y descubría al promover que el bot no podía usarlas.
    assert all(not ((g["spec"].get("risk") or {}).get("trail_atr") or 0)
               for g in guardadas)


def test_sin_la_marca_lo_minado_no_se_guarda_solo(client):
    """El botón sigue siendo el que guarda cuando mina una persona."""
    ds = client.post("/api/datasets/sample",
                     json={"symbol": "EURUSD", "bars": 1200}).json()["id"]
    jid = client.post("/api/mine", json={
        "dataset_id": ds, "target_keep": 2, "max_candidates": 120,
        "min_trades": 3, "seed": 5,
        "settings": {"spread": 0.0002, "slippage": 0.0},
    }).json()["job_id"]
    for _ in range(600):
        if client.get(f"/api/jobs/{jid}").json()["status"] != "running":
            break
        time.sleep(0.1)
    assert client.get("/api/banco").json()
    assert client.get("/api/strategies").json() == []
