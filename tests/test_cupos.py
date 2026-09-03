"""Tope de búsquedas simultáneas.

Minar es trabajo de procesador puro: una búsqueda ocupa un núcleo durante
minutos. Sin tope, cada clic en "Minar" arrancaba un hilo más y un puñado de
personas dejaba el servidor a paso de hombre para todos.
"""

from __future__ import annotations

import threading
import time

import pytest

from botiquant.core.jobs import DemasiadoTrabajo, JobManager


def _lento(freno: threading.Event):
    """Un trabajo que no termina hasta que se lo suelta."""
    def fn(_progress):
        freno.wait(timeout=5)
        return "listo"
    return fn


def test_the_machine_queues_work_when_full():
    """EL CUPO GLOBAL ENCOLA, NO RECHAZA. Con un solo lugar, cada prueba que
    se pedía mientras el Piloto probaba lo suyo volvía con 429; cuatro
    personas probaron la aplicación el 2 de septiembre y las cuatro chocaron
    con eso. Ahora espera su turno y arranca sola."""
    import time
    freno = threading.Event()
    jobs = JobManager(max_running=2, max_por_usuario=99)
    try:
        jobs.submit("probar", _lento(freno), dueno="ana")
        jobs.submit("probar", _lento(freno), dueno="beto")
        tercero = jobs.submit("probar", _lento(freno), dueno="caro")
        assert jobs.get(tercero).status == "queued"
        # una BÚSQUEDA, en cambio, no espera en cola: se rechaza con texto
        with pytest.raises(DemasiadoTrabajo, match="capacidad"):
            jobs.submit("mine", _lento(freno), dueno="dani")
        assert "cola" in jobs.get(tercero).message.lower()
        # y para quien sondea sigue siendo "running", con la marca de cola
        assert jobs.get(tercero).to_dict()["status"] == "running"
        assert jobs.get(tercero).to_dict()["en_cola"] is True
    finally:
        freno.set()
    for _ in range(100):
        if jobs.get(tercero).status == "done":
            break
        time.sleep(0.05)
    assert jobs.get(tercero).status == "done", "el encolado tiene que arrancar solo al liberarse un lugar"


def test_one_person_cannot_take_every_slot():
    """Sin el cupo por persona, alguien apretando el botón repetidas veces
    llena la máquina y nadie más entra."""
    freno = threading.Event()
    jobs = JobManager(max_running=5, max_por_usuario=1)
    try:
        jobs.submit("mine", _lento(freno), dueno="ana")

        with pytest.raises(DemasiadoTrabajo, match="Ya tenés una búsqueda"):
            jobs.submit("mine", _lento(freno), dueno="ana")

        # y el lugar sigue disponible para otro
        assert jobs.submit("mine", _lento(freno), dueno="beto")
    finally:
        freno.set()


def test_a_finished_job_frees_its_slot():
    """Si el lugar no se liberara, el servidor dejaría de aceptar trabajo para
    siempre después de las primeras búsquedas."""
    freno = threading.Event()
    jobs = JobManager(max_running=1, max_por_usuario=1)
    jobs.submit("mine", _lento(freno), dueno="ana")
    freno.set()

    for _ in range(50):                       # se espera a que el hilo termine
        if jobs._corriendo() == 0:
            break
        time.sleep(0.05)

    assert jobs._corriendo() == 0
    assert jobs.submit("mine", lambda _p: "ok", dueno="ana")


def test_a_crashed_job_frees_its_slot_too():
    """Un trabajo que revienta tiene que soltar el lugar igual: si no, cada
    error dejaría un cupo ocupado para siempre."""
    jobs = JobManager(max_running=1, max_por_usuario=1)

    def revienta(_progress):
        raise RuntimeError("boom")

    jobs.submit("mine", revienta, dueno="ana")
    for _ in range(50):
        if jobs._corriendo() == 0:
            break
        time.sleep(0.05)

    assert jobs._corriendo() == 0
    assert jobs.submit("mine", lambda _p: "ok", dueno="ana")


def test_a_local_install_is_not_rationed_per_person():
    """Sin cuentas el dueño es None, y ahí el cupo por persona no aplica: en tu
    propia máquina no tiene sentido racionarte contra vos mismo."""
    freno = threading.Event()
    jobs = JobManager(max_running=3, max_por_usuario=1)
    try:
        jobs.submit("mine", _lento(freno), dueno=None)
        assert jobs.submit("mine", _lento(freno), dueno=None)
    finally:
        freno.set()


def test_the_default_leaves_a_core_for_serving():
    """Si el tope fuera igual a la cantidad de núcleos, el servidor se quedaría
    sin nadie que atienda pedidos mientras mina."""
    import os

    jobs = JobManager()
    assert jobs._max_running == max(1, (os.cpu_count() or 2) - 1)
    assert jobs._max_running >= 1


# ----------------------------------------------------------- de punta a punta
def test_a_second_search_gets_a_clear_429(tmp_path, monkeypatch):
    """El rechazo tiene que llegar como 429 y con un texto que se pueda mostrar
    tal cual. Un 500 haría pensar que la aplicación se rompió."""
    from fastapi.testclient import TestClient

    import botiquant.api.app as appmod

    monkeypatch.setenv("BQ_MAX_BUSQUEDAS", "1")
    monkeypatch.setenv("BQ_MAX_POR_USUARIO", "1")
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)

    with TestClient(appmod.create_app(workdir=tmp_path)) as c:
        c.post("/api/datasets/sample", json={"symbol": "TEST", "bars": 4000})
        ds = c.get("/api/datasets").json()[0]["id"]
        cuerpo = {"dataset_id": ds, "max_candidates": 400, "target_keep": 50,
                  "risk": {"stop_type": "atr", "stop_value": 2}}

        primera = c.post("/api/mine", json=cuerpo)
        assert primera.status_code == 200

        segunda = c.post("/api/mine", json=cuerpo)
        assert segunda.status_code == 429, segunda.text
        detalle = segunda.json()["detail"]
        assert "búsqueda" in detalle or "capacidad" in detalle

        c.post(f"/api/jobs/{primera.json()['job_id']}/stop")


def test_reading_a_limit_from_the_environment_is_forgiving():
    """Un valor roto no puede dejar el tope en cero: eso no sería "sin límite",
    sería nadie puede minar."""
    import os

    import botiquant.api.app as appmod

    for crudo, esperado in [("7", 7), ("0", None), ("-3", None),
                            ("ocho", None), ("", None), ("  4 ", 4)]:
        os.environ["BQ_PRUEBA"] = crudo
        assert appmod._entero("BQ_PRUEBA") is esperado or                appmod._entero("BQ_PRUEBA") == esperado, crudo
    os.environ.pop("BQ_PRUEBA", None)
    assert appmod._entero("BQ_PRUEBA") is None


def test_the_per_person_limit_is_configurable():
    """El tope por persona sale del entorno, y se prueba sobre el gestor y no
    sobre la API: alla la primera busqueda puede terminar antes de que llegue
    la tercera peticion —el dato de prueba es chico— y el test pasaria o
    fallaria segun la velocidad de la maquina. Un test que depende del reloj no
    prueba nada."""
    freno = threading.Event()
    jobs = JobManager(max_running=4, max_por_usuario=2)
    try:
        jobs.submit("mine", _lento(freno), dueno="ana")
        jobs.submit("mine", _lento(freno), dueno="ana")

        with pytest.raises(DemasiadoTrabajo):
            jobs.submit("mine", _lento(freno), dueno="ana")
    finally:
        freno.set()
