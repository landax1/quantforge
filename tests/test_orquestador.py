"""El que ejecuta lo que el ciclo decide.

Todo corre sin base de datos, sin red y sin esperar: se le pasan funciones de
mentira y se comprueba a cuáles llamó. Es la razón de que reciba sus acciones
de afuera en vez de importarlas.

Lo que más se defiende: que una vuelta haga UNA cosa, que un error no apague
todo, y que una acción sin quien la haga no se anote como hecha.
"""

from __future__ import annotations

import pytest

from botiquant import ciclo, estados
from botiquant.orquestador import Orquestador


def _estado(estrategias=None, horas=0.0, en_practica=0):
    return lambda: {"estrategias": estrategias or [],
                    "horas_desde_minado": horas, "en_practica": en_practica}


class _Espia:
    """Anota a qué acción se llamó y con qué ids."""

    def __init__(self):
        self.llamadas: list[tuple[str, list[str]]] = []

    def para(self, nombre: str):
        def hacer(ids):
            self.llamadas.append((nombre, list(ids)))
        return hacer

    def todas(self) -> dict:
        return {n: self.para(n) for n in
                (ciclo.MINAR, ciclo.VALIDAR, ciclo.PROMOVER, ciclo.RETIRAR)}


def _e(id_, estado, *, naranja=0, practica_ok=True):
    return {"id": id_, "estado": estado, "vueltas_en_naranja": naranja,
            "cantera": {"practica": practica_ok}}


def _orq(estrategias=None, horas=0.0, en_practica=0, **params):
    espia = _Espia()
    o = Orquestador(leer_estado=_estado(estrategias, horas, en_practica),
                    acciones=espia.todas())
    o.params = ciclo.Parametros.from_dict({"encendido": True, **params})
    return o, espia


# --------------------------------------------------------- decidir sin hacer

def test_puede_decir_que_haria_sin_tocar_nada():
    """Es como se prueba un sistema autónomo sin dejarlo suelto, y lo que se
    le muestra al usuario antes de que empiece."""
    o, espia = _orq([_e("a", estados.NUEVA)], horas=99, en_practica=99)
    t = o.que_haria()
    assert t.accion == ciclo.VALIDAR
    assert espia.llamadas == [], "preguntar no puede ejecutar"


def test_apagado_no_hace_nada_aunque_se_le_pida_una_vuelta():
    o, espia = _orq([_e("a", estados.NUEVA)], horas=99)
    o.params = ciclo.Parametros()          # apagado
    v = o.una_vuelta()
    assert v.accion == ciclo.NADA
    assert espia.llamadas == []


# ------------------------------------------------------ una cosa por vuelta

def test_una_vuelta_hace_UNA_sola_accion():
    """Parece más eficiente encadenar validar-promover-minar en una pasada.

    Pero cada acción cambia el estado del mundo, y la decisión siguiente tiene
    que tomarse sobre el mundo nuevo. Encadenando, el ciclo promueve sobre una
    foto vieja — y con un tope de cinco en práctica, eso es promover seis.
    """
    o, espia = _orq([_e("lista", estados.VALIDADA), _e("cruda", estados.NUEVA)],
                    horas=99, en_practica=0)
    o.una_vuelta()
    assert len(espia.llamadas) == 1
    assert espia.llamadas[0][0] == ciclo.PROMOVER


def test_la_vuelta_siguiente_decide_sobre_el_mundo_nuevo():
    """El estado se vuelve a leer en cada vuelta, no se cachea."""
    filas = [_e("lista", estados.VALIDADA)]
    espia = _Espia()
    o = Orquestador(leer_estado=lambda: {"estrategias": filas,
                                         "horas_desde_minado": 99,
                                         "en_practica": 0},
                    acciones=espia.todas())
    o.params = ciclo.Parametros.from_dict({"encendido": True})

    o.una_vuelta()
    assert espia.llamadas[-1][0] == ciclo.PROMOVER
    # el mundo cambió: ya está en práctica
    filas[0]["estado"] = estados.PRACTICA
    o.una_vuelta()
    assert espia.llamadas[-1][0] == ciclo.MINAR


# ----------------------------------------------------------- los errores

def test_un_error_en_una_accion_NO_apaga_el_ciclo():
    """A diferencia del bot: acá una vuelta que falla es una estrategia que no
    se validó, no una orden que no salió. El problema puede ser de una sola
    estrategia, y apagar todo por eso sería peor.
    """
    def revienta(ids):
        raise RuntimeError("la estrategia 3 no tiene dataset")

    o = Orquestador(leer_estado=_estado([_e("a", estados.NUEVA)], 99, 99),
                    acciones={ciclo.VALIDAR: revienta})
    o.params = ciclo.Parametros.from_dict({"encendido": True})
    v = o.una_vuelta()
    assert "no tiene dataset" in v.error
    assert o.error == "", "el ciclo sigue en pie"


def test_una_accion_sin_quien_la_haga_no_se_anota_como_hecha():
    """Si no, el registro diría que promovió algo que sigue donde estaba."""
    o = Orquestador(leer_estado=_estado([_e("a", estados.VALIDADA)], 1, 0),
                    acciones={})          # ninguna
    o.params = ciclo.Parametros.from_dict({"encendido": True})
    v = o.una_vuelta()
    assert v.accion == ciclo.PROMOVER
    assert "no hay quién" in v.error


def test_lo_que_no_hizo_nada_no_ensucia_el_registro():
    """Cuarenta vueltas diciendo "nada que hacer" tapan la única que importa."""
    o, _ = _orq([], horas=0, minar_cada_horas=12)
    for _ in range(5):
        o.una_vuelta()
    assert o.estado()["registro"] == []


# ------------------------------------------------------------- el registro

def test_el_registro_dice_que_hizo_y_por_que():
    o, _ = _orq([_e("a", estados.NUEVA)], horas=99, en_practica=99)
    o.una_vuelta()
    fila = o.estado()["registro"][0]
    assert fila["accion"] == ciclo.VALIDAR
    assert fila["motivo"]
    assert fila["ids"] == ["a"]


def test_el_estado_trae_lo_proximo_que_va_a_hacer():
    o, _ = _orq([_e("a", estados.NUEVA)], horas=99, en_practica=99)
    assert o.estado()["proxima"]["accion"] == ciclo.VALIDAR


def test_el_registro_se_muestra_del_mas_nuevo_al_mas_viejo():
    o, _ = _orq([_e("a", estados.NUEVA), _e("b", estados.NUEVA)],
                horas=99, en_practica=99)
    o.una_vuelta()
    o.una_vuelta()
    r = o.estado()["registro"]
    assert len(r) == 2
    assert r[0]["cuando"] >= r[1]["cuando"]


# ------------------------------------------------- lo que nunca puede hacer

def test_nunca_ejecuta_una_accion_de_produccion():
    """La promoción automática llega hasta práctica. El orquestador no lo
    sabe ni puede eludirlo: le pregunta a `ciclo` y ejecuta lo que diga."""
    o, espia = _orq([_e("a", estados.PRACTICA)], horas=1, en_practica=0)
    for _ in range(5):
        o.una_vuelta()
    for nombre, _ in espia.llamadas:
        assert nombre != estados.PRODUCCION


def test_no_promueve_lo_que_la_cantera_frena():
    o, espia = _orq([_e("floja", estados.VALIDADA, practica_ok=False)],
                    horas=1, en_practica=0)
    o.una_vuelta()
    assert not any(n == ciclo.PROMOVER for n, _ in espia.llamadas)


# --------------------------------------------------------- encender y apagar

def test_encender_y_apagar_no_deja_el_hilo_colgado():
    import time

    o, espia = _orq([], horas=0)
    o.encender()
    time.sleep(0.2)
    assert o.corriendo
    o.apagar()
    assert not o.corriendo


def test_encender_dos_veces_no_arranca_dos_hilos():
    """Dos ciclos sobre las mismas estrategias se pisarían promoviendo y
    retirando lo mismo."""
    import time

    o, _ = _orq([], horas=0)
    o.encender()
    primero = o._hilo
    o.encender()
    time.sleep(0.1)
    assert o._hilo is primero
    o.apagar()


# ------------------------------------------------- el ciclo dentro de la app

def _cliente(tmp_path):
    from fastapi.testclient import TestClient

    from botiquant.api.app import create_app
    return TestClient(create_app(workdir=tmp_path / "ws"))


def test_se_puede_mirar_que_haria_sin_encenderlo(tmp_path):
    """Como conviene estrenar un sistema autonomo: mirando, no soltandolo."""
    with _cliente(tmp_path) as c:
        r = c.get("/api/ciclo")
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["corriendo"] is False
        assert e["params"]["encendido"] is False
        assert "accion" in e["proxima"]


def test_arranca_apagado(tmp_path):
    with _cliente(tmp_path) as c:
        assert c.get("/api/ciclo").json()["params"]["encendido"] is False


def test_encender_y_apagar_por_la_api(tmp_path):
    with _cliente(tmp_path) as c:
        r = c.post("/api/ciclo/params", json={"encendido": True,
                                              "minar_cada_horas": 24})
        assert r.json()["corriendo"] is True
        assert r.json()["params"]["minar_cada_horas"] == 24
        r = c.post("/api/ciclo/params", json={"encendido": False})
        assert r.json()["corriendo"] is False


def test_un_paso_a_mano_FUNCIONA_con_el_ciclo_apagado(tmp_path):
    """Encontrado usándolo: el paso a mano no hacía nada si estaba apagado.

    Y ese endpoint existe justo para verlo actuar SIN dejarlo suelto, que es
    exactamente cuando el ciclo está apagado. `encendido` significa "corre
    solo", no "puede decidir".
    """
    with _cliente(tmp_path) as c:
        # con una estrategia sin probar hay algo que hacer
        c.post("/api/strategies", json={
            "name": "x", "spec": {"name": "x", "direction": "long"},
            "meta": {"metrics": {"trades": 200, "profit_factor": 1.5}}})
        assert c.get("/api/ciclo").json()["params"]["encendido"] is False

        r = c.post("/api/ciclo/paso")
        assert r.status_code == 200, r.text
        assert r.json()["hizo"]["accion"] != "nada", (
            "el paso a mano no puede quedarse quieto por el interruptor")


def test_pero_el_bucle_automatico_SI_respeta_el_interruptor(tmp_path):
    """La contracara. Si el interruptor no frenara el bucle, apagar el ciclo
    no serviría de nada."""
    from botiquant import ciclo as cic

    o = Orquestador(leer_estado=_estado([_e("a", estados.NUEVA)], 99, 99),
                    acciones={})
    o.params = cic.Parametros()          # apagado
    assert o.una_vuelta().accion == cic.NADA
    assert o.una_vuelta(a_mano=True).accion == cic.VALIDAR


def test_la_api_tampoco_deja_promover_a_produccion(tmp_path):
    """Aunque se mande en el payload de parámetros."""
    with _cliente(tmp_path) as c:
        r = c.post("/api/ciclo/params",
                   json={"encendido": False, "promover_hasta": "produccion"})
        assert r.json()["params"]["promover_hasta"] == "practica"
