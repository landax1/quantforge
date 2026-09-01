"""El lazo completo: opera, se agota, y el ciclo lo saca.

Es el recorrido que hace que esto sea un sistema y no una colección de piezas:

    el bot opera  ->  se guarda lo operado  ->  el semáforo compara contra el
    backtest  ->  se cuentan las vueltas en naranja  ->  el ciclo retira

Cada eslabón tiene sus propios tests. Este archivo prueba que estén UNIDOS,
que es justo lo que faltaba: el mecanismo de retiro estaba escrito entero y
recibía siempre un cero, así que no podía dispararse nunca.
"""

from __future__ import annotations

import pathlib
import tempfile

from botiquant import estados
from botiquant.ciclo import MINAR, RETIRAR, Parametros, que_toca
from botiquant.database.db import Database
from botiquant.vivo import semaforo

#: El backtest decía profit factor 2. Es la línea base contra la que se compara.
RESPALDO = {"profit_factor": 2.0, "trades": 300}


def _db() -> Database:
    return Database(pathlib.Path(tempfile.mkdtemp()) / "t.db")


def _operar(db: Database, sid: str, *, ganadoras: int, perdedoras: int,
            gana: float = 1.0, pierde: float = 1.5) -> None:
    """Opera de verdad contra la base, como lo haría el bot."""
    for i in range(ganadoras):
        db.anotar_operacion(sid, {"cuando": f"2026-09-01T{i:02d}:00",
                                  "accion": "cerrar", "ganancia": gana})
    for i in range(perdedoras):
        db.anotar_operacion(sid, {"cuando": f"2026-09-02T{i:02d}:00",
                                  "accion": "cerrar", "ganancia": -pierde})


def _vuelta(db: Database, sid: str) -> dict:
    """Una vuelta del ciclo: mira lo operado y actualiza la memoria."""
    f = [x for x in db.list_strategies(None) if x["id"] == sid][0]
    v = semaforo.revisar(db.operaciones(sid), RESPALDO)
    nueva = semaforo.actualizar(f.get("vigilancia"), v, cuando="2026-09-02")
    db.guardar_vigilancia(sid, nueva)
    return nueva


def _guardar(db: Database) -> str:
    r = db.save_strategy(name="S-042", spec={"name": "S-042"})
    return r["id"] if isinstance(r, dict) else r


# ============================================ lo operado sobrevive

def test_lo_operado_SOBREVIVE_a_cerrar_la_aplicacion():
    """El registro del bot vive en memoria. Sin guardarlo, una estrategia no
    puede acumular sus treinta operaciones a lo largo de semanas — y treinta
    es el mínimo para que el semáforo opine."""
    db = _db()
    sid = _guardar(db)
    _operar(db, sid, ganadoras=2, perdedoras=1)

    # otra instancia sobre el mismo archivo: como abrir la aplicación de nuevo
    otra = Database(db.path)
    assert len(otra.operaciones(sid)) == 3


# ====================================== el lazo entero, eslabón por eslabón

def test_una_que_se_agota_TERMINA_RETIRADA():
    """EL RECORRIDO COMPLETO.

    El backtest decía 2,0 de profit factor. En vivo hace 0,67 — o sea que
    conserva un tercio de su ventaja, que es naranja. Tres vueltas así y el
    ciclo la saca.
    """
    db = _db()
    sid = _guardar(db)
    db.mover_estado(sid, {"estado": estados.PRACTICA, "retiro": {}})
    # 15 ganadas de 1 y 15 perdidas de 1,5: pf vivo 0,67 contra 2,0 del
    # backtest. Conserva el 33%, debajo del 50% que separa naranja.
    _operar(db, sid, ganadoras=15, perdedoras=15)

    colores = [_vuelta(db, sid) for _ in range(3)]
    assert [c["color"] for c in colores] == [semaforo.NARANJA] * 3
    assert colores[-1]["vueltas_naranja"] == 3

    fila = {"id": sid, "estado": estados.PRACTICA,
            "cantera": {"practica": True},
            "vueltas_en_naranja": colores[-1]["vueltas_naranja"]}

    t = que_toca(Parametros.from_dict(
        {"encendido": True, "vueltas_en_naranja": 3, "retirar_solo": True}),
        estrategias=[fila], horas_desde_el_ultimo_minado=1)
    assert t.accion == RETIRAR and t.ids == [sid]


def test_con_el_interruptor_APAGADO_la_señala_y_no_la_saca():
    """El default. El ciclo sigue su camino y aun así dice a quién sacaría."""
    db = _db()
    sid = _guardar(db)
    db.mover_estado(sid, {"estado": estados.PRACTICA, "retiro": {}})
    _operar(db, sid, ganadoras=15, perdedoras=15)
    for _ in range(3):
        v = _vuelta(db, sid)

    fila = {"id": sid, "estado": estados.PRACTICA,
            "cantera": {"practica": True},
            "vueltas_en_naranja": v["vueltas_naranja"]}
    t = que_toca(Parametros.from_dict(
        {"encendido": True, "vueltas_en_naranja": 3}),
        estrategias=[fila], horas_desde_el_ultimo_minado=999)

    assert t.accion == MINAR, "retiró con el interruptor apagado"
    assert t.retirables == [sid], "se calló lo que vio"


def test_una_que_SE_RECUPERA_no_se_retira():
    """El verde resetea, y es lo que evita que el ciclo se coma sus propias
    estrategias en una racha mala.

    Dos vueltas en naranja, después vuelve a rendir, y la cuenta arranca de
    cero: la racha anterior ya no la describe.
    """
    db = _db()
    sid = _guardar(db)
    db.mover_estado(sid, {"estado": estados.PRACTICA, "retiro": {}})
    _operar(db, sid, ganadoras=15, perdedoras=15)
    _vuelta(db, sid)
    v = _vuelta(db, sid)
    assert v["vueltas_naranja"] == 2

    # se recupera: muchas ganadas nuevas la devuelven por encima del 70%
    _operar(db, sid, ganadoras=60, perdedoras=0, gana=2.0)
    v = _vuelta(db, sid)
    assert v["color"] == semaforo.VERDE
    assert v["vueltas_naranja"] == 0, "un verde no le limpió la racha"


def test_sin_operaciones_suficientes_NO_OPINA():
    """Con doce operaciones cerradas dos grandes mueven el profit factor de
    0,8 a 1,6. Opinar ahí es tirar una moneda con cara de análisis."""
    db = _db()
    sid = _guardar(db)
    _operar(db, sid, ganadoras=3, perdedoras=3)
    v = _vuelta(db, sid)
    assert v["color"] == semaforo.CALLADO
    assert v["vueltas_naranja"] == 0
