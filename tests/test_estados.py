"""En qué punto del camino está cada estrategia, y el cementerio.

Sin esto el ciclo no puede correr solo: el programa necesita poder preguntarse
"¿cuáles están listas para validar?" y "¿cuáles hay que retirar?" sin que
nadie se lo diga. Mezcladas en una sola lista, esa pregunta no tiene respuesta.

Lo que más se defiende acá son las dos reglas que duelen: que no se pueda
saltear el camino, y que del cementerio se vuelva al principio.
"""

from __future__ import annotations

import pytest

from botiquant.estados import (NUEVA, PRACTICA, PRODUCCION, RETIRADA, TODOS,
                               VALIDADA, EstadoError, mover, normalizar, puede,
                               resumen, siguiente)


# ------------------------------------------------------- lo que ya existía

def test_una_estrategia_sin_estado_es_nueva():
    """Las que se guardaron antes de que esto existiera no tienen ninguno.

    Nadie las validó ni las corrió, así que nuevas es lo que son. Con eso no
    hay que migrar nada ni inventarles un pasado.
    """
    assert normalizar(None) == NUEVA
    assert normalizar("") == NUEVA
    assert normalizar("cualquier cosa") == NUEVA


def test_un_estado_conocido_se_respeta():
    for e in TODOS:
        assert normalizar(e) == e


# --------------------------------------------------- no se saltea el camino

def test_no_se_puede_ir_de_nueva_a_produccion():
    """Es encender con plata algo que nunca se probó.

    Es exactamente lo que la cantera y esto existen para impedir, y es el
    salto que alguien va a querer dar cuando vea un backtest lindo.
    """
    assert not puede(NUEVA, PRODUCCION)
    with pytest.raises(EstadoError, match="No se puede pasar"):
        mover(NUEVA, PRODUCCION)


def test_el_camino_completo_se_puede_recorrer():
    """El control: si esto falla, el modelo quedó tan cerrado que no sirve."""
    assert puede(NUEVA, VALIDADA)
    assert puede(VALIDADA, PRACTICA)
    assert puede(PRACTICA, PRODUCCION)


def test_de_produccion_se_puede_BAJAR_a_practica():
    """Es lo que recomienda el semáforo cuando la ventaja se deteriora.

    Tiene que ser un paso barato: si bajar costara tanto como retirar, nadie
    lo daría y la estrategia seguiría corriendo con plata.
    """
    assert puede(PRODUCCION, PRACTICA)


def test_desde_cualquier_lado_se_puede_retirar():
    for e in (NUEVA, VALIDADA, PRACTICA, PRODUCCION):
        assert puede(e, RETIRADA), f"no se puede retirar desde {e}"


def test_moverse_al_mismo_estado_no_es_un_movimiento():
    with pytest.raises(EstadoError, match="Ya está"):
        mover(PRACTICA, PRACTICA)


# ------------------------------------------------------------ el cementerio

def test_retirar_EXIGE_un_motivo():
    """Un cementerio sin autopsias es una lista de nombres.

    No sirve para lo único que tiene que servir: que la próxima con el mismo
    problema no se encienda igual.
    """
    with pytest.raises(EstadoError, match="por qué"):
        mover(PRODUCCION, RETIRADA)
    with pytest.raises(EstadoError, match="por qué"):
        mover(PRODUCCION, RETIRADA, motivo="   ")


def test_el_motivo_y_el_origen_quedan_guardados():
    """De dónde venía importa tanto como el motivo: una que murió en
    producción y una que nunca salió de nueva son dos historias distintas."""
    c = mover(PRODUCCION, RETIRADA, motivo="el spread nocturno se comía la ventaja")
    assert c["estado"] == RETIRADA
    assert c["retiro"]["motivo"] == "el spread nocturno se comía la ventaja"
    assert c["retiro"]["desde"] == PRODUCCION


def test_del_cementerio_se_vuelve_AL_PRINCIPIO_y_no_a_donde_estaba():
    """La regla que más cuesta respetar y la que más plata ahorra.

    Reactivar en producción algo retirado "porque venía teniendo mala suerte"
    es el movimiento con el que se pierde plata, y es justo el que uno quiere
    hacer a las once de la noche.
    """
    assert puede(RETIRADA, NUEVA)
    assert not puede(RETIRADA, PRODUCCION)
    assert not puede(RETIRADA, PRACTICA)
    assert not puede(RETIRADA, VALIDADA)


def test_el_mensaje_de_ese_rechazo_explica_QUE_hacer():
    with pytest.raises(EstadoError, match="rehacer el camino"):
        mover(RETIRADA, PRODUCCION)


def test_al_salir_del_cementerio_se_limpia_la_autopsia():
    """Dejarla pegada a una estrategia que volvió a empezar hace creer que
    sigue retirada."""
    c = mover(RETIRADA, NUEVA)
    assert c["estado"] == NUEVA
    assert c["retiro"] is None


# ------------------------------------------------------------- el siguiente

def test_dice_cual_es_el_proximo_paso():
    assert siguiente(NUEVA) == VALIDADA
    assert siguiente(VALIDADA) == PRACTICA
    assert siguiente(PRACTICA) == PRODUCCION


def test_en_produccion_y_en_el_cementerio_no_hay_siguiente():
    assert siguiente(PRODUCCION) is None
    assert siguiente(RETIRADA) is None


# --------------------------------------------------------------- el resumen

def test_cuenta_cuantas_hay_en_cada_estado():
    filas = [{"estado": NUEVA}, {"estado": NUEVA}, {"estado": PRODUCCION},
             {"estado": RETIRADA}, {}]
    r = resumen(filas)
    assert r[NUEVA] == 3, "la fila sin estado cuenta como nueva"
    assert r[PRODUCCION] == 1
    assert r[RETIRADA] == 1
    assert r[VALIDADA] == 0


def test_el_resumen_trae_todos_los_estados_aunque_esten_en_cero():
    """Para que la pantalla no tenga que saber cuáles existen, y para que un
    estado nuevo aparezca solo en vez de faltar en silencio."""
    assert set(resumen([])) == set(TODOS)


# ------------------------------------------------- el estado sobrevive al disco

def _cliente(tmp_path):
    from fastapi.testclient import TestClient

    from botiquant.api.app import create_app
    return TestClient(create_app(workdir=tmp_path / "ws"))


def _guardar(c, nombre="x"):
    r = c.post("/api/strategies", json={
        "name": nombre, "spec": {"name": nombre, "direction": "long"},
        "meta": {"metrics": {"trades": 200, "profit_factor": 1.5}}})
    assert r.status_code in (200, 201), r.text
    return c.get("/api/strategies").json()[0]["id"]


def test_una_estrategia_nueva_arranca_en_nueva(tmp_path):
    with _cliente(tmp_path) as c:
        _guardar(c)
        fila = c.get("/api/strategies").json()[0]
        assert fila["estado"] == NUEVA
        assert fila["siguiente"] == VALIDADA


def test_el_movimiento_se_guarda_y_sobrevive(tmp_path):
    """Si no sobreviviera a cerrar el programa, el ciclo automático no podría
    retomar donde quedó."""
    with _cliente(tmp_path) as c:
        sid = _guardar(c)
        r = c.post(f"/api/strategies/{sid}/estado", json={"estado": VALIDADA})
        assert r.status_code == 200, r.text
        assert c.get("/api/strategies").json()[0]["estado"] == VALIDADA


def test_el_servidor_TAMBIEN_impide_saltear_el_camino(tmp_path):
    """Una regla que sólo viva en la pantalla la saltea cualquiera que llame
    al endpoint."""
    with _cliente(tmp_path) as c:
        sid = _guardar(c)
        r = c.post(f"/api/strategies/{sid}/estado", json={"estado": PRODUCCION})
        assert r.status_code == 409
        assert "No se puede pasar" in r.json()["detail"]


def test_retirar_sin_motivo_se_rechaza_del_lado_del_servidor(tmp_path):
    with _cliente(tmp_path) as c:
        sid = _guardar(c)
        r = c.post(f"/api/strategies/{sid}/estado", json={"estado": RETIRADA})
        assert r.status_code == 409
        assert "por qué" in r.json()["detail"]


def test_la_autopsia_queda_guardada_y_se_lee(tmp_path):
    with _cliente(tmp_path) as c:
        sid = _guardar(c)
        c.post(f"/api/strategies/{sid}/estado",
               json={"estado": RETIRADA, "motivo": "el spread se comía la ventaja"})
        fila = c.get("/api/strategies").json()[0]
        assert fila["estado"] == RETIRADA
        assert fila["retiro"]["motivo"] == "el spread se comía la ventaja"
        assert fila["retiro"]["desde"] == NUEVA


def test_del_cementerio_el_servidor_solo_deja_volver_al_principio(tmp_path):
    with _cliente(tmp_path) as c:
        sid = _guardar(c)
        c.post(f"/api/strategies/{sid}/estado",
               json={"estado": RETIRADA, "motivo": "sobreajustada"})
        assert c.post(f"/api/strategies/{sid}/estado",
                      json={"estado": PRODUCCION}).status_code == 409
        r = c.post(f"/api/strategies/{sid}/estado", json={"estado": NUEVA})
        assert r.status_code == 200
        assert c.get("/api/strategies").json()[0]["retiro"] is None


def test_el_resumen_cuenta_sin_traerse_todo(tmp_path):
    """Lo pide el ciclo automático tanto como la pantalla."""
    with _cliente(tmp_path) as c:
        _guardar(c, "a")
        _guardar(c, "b")
        r = c.get("/api/estrategias/resumen").json()
        assert r["por_estado"][NUEVA] == 2
        assert r["cementerio"] == RETIRADA
        assert r["orden"][0] == NUEVA


# ------------------------------------------- validar es un PASO, no un boton

def _con_datos(tmp_path):
    """Un cliente con un instrumento cargado, para poder correr el backtest."""
    c = _cliente(tmp_path)
    c.__enter__()
    c.post("/api/datasets/sample", json={"symbol": "EURUSD", "bars": 3000})
    return c


def _guardar_operable(c):
    """Una estrategia que opera de verdad sobre el instrumento de prueba."""
    ds = c.get("/api/datasets").json()[0]
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    r = c.post("/api/strategies", json={
        "name": "operable",
        "spec": {"name": "operable", "direction": "long",
                 "entry_long": [{"left": ema(5), "op": "cross_above",
                                 "right": ema(20)}],
                 "risk": {"stop_type": "atr", "stop_value": 2.0,
                          "target_type": "atr", "target_value": 4.0}},
        "meta": {"dataset_id": ds["id"], "timeframe": "1h", "capital": 10_000.0,
                 "metrics": {"trades": 50, "profit_factor": 1.3}}})
    assert r.status_code in (200, 201), r.text
    return c.get("/api/strategies").json()[0]["id"]


def test_validar_corre_las_pruebas_y_mueve_el_estado(tmp_path):
    """El paso que convierte "la encontré" en "la puse a prueba"."""
    c = _con_datos(tmp_path)
    try:
        sid = _guardar_operable(c)
        r = c.post(f"/api/strategies/{sid}/validar", json={"simulations": 200})
        assert r.status_code == 200, r.text
        v = r.json()["validacion"]
        assert v["operaciones"] > 0
        assert v["dd_p95_pct"] >= 0
        assert r.json()["estado"] == VALIDADA
    finally:
        c.__exit__(None, None, None)


def test_la_validacion_queda_guardada_y_sobrevive(tmp_path):
    """Si se perdiera al cambiar de pantalla, la lista no podría decir cuáles
    están probadas — que es justo lo que el ciclo necesita saber."""
    c = _con_datos(tmp_path)
    try:
        sid = _guardar_operable(c)
        c.post(f"/api/strategies/{sid}/validar", json={"simulations": 200})
        fila = c.get("/api/strategies").json()[0]
        assert fila["estado"] == VALIDADA
        assert fila["validacion"]["dd_p95_pct"] >= 0
    finally:
        c.__exit__(None, None, None)


def test_registra_CUANTO_PEOR_puede_ser_el_mismo_conjunto_de_operaciones(tmp_path):
    """Es el número que enseña algo.

    La caída histórica es UNA realización. Una caída baja con un múltiplo alto
    significa que la estrategia tuvo suerte con el orden de sus operaciones —
    y eso no se ve en ninguna métrica del backtest.
    """
    c = _con_datos(tmp_path)
    try:
        sid = _guardar_operable(c)
        v = c.post(f"/api/strategies/{sid}/validar",
                   json={"simulations": 300}).json()["validacion"]
        assert v["cuanto_peor"] is None or v["cuanto_peor"] >= 1.0
    finally:
        c.__exit__(None, None, None)


def test_sin_instrumento_no_se_puede_validar(tmp_path):
    """Y lo dice, en vez de inventar un backtest sobre datos que no son."""
    with _cliente(tmp_path) as c:
        sid = _guardar(c)
        r = c.post(f"/api/strategies/{sid}/validar", json={})
        assert r.status_code == 422
        assert "instrumento" in r.json()["detail"]


def test_validar_no_es_aprobar(tmp_path):
    """"Validada" significa que se le corrieron las pruebas, NO que las pasó.

    Quién puede operar con plata lo decide la cantera, que mira otras cosas.
    Confundirlas haría que "validada" sonara a aprobación y alguien la
    encendiera por eso.
    """
    c = _con_datos(tmp_path)
    try:
        sid = _guardar_operable(c)
        c.post(f"/api/strategies/{sid}/validar", json={"simulations": 200})
        fila = c.get("/api/strategies").json()[0]
        assert fila["estado"] == VALIDADA
        # la cantera sigue diciendo que no: no tiene fuera de muestra
        assert fila["cantera"]["real"]["pasa"] is False
    finally:
        c.__exit__(None, None, None)
