"""¿La estrategia sigue rindiendo como decía el backtest?

Lo que se defiende acá es sobre todo el CALLADO. Un semáforo que opina con
doce operaciones se equivoca seguido, y uno que se equivoca seguido lo apaga
el usuario a la semana — que es peor que no tenerlo, porque da la sensación de
estar cubierto.
"""

from __future__ import annotations

import pytest

from botiquant.vivo.semaforo import (AMARILLO, CALLADO, CERRADAS_MINIMAS,
                                     NARANJA, VERDE, revisar)


def _cierres(ganancias: list[float]) -> list[dict]:
    return [{"accion": "cerrar", "ganancia": g} for g in ganancias]


def _mezcla(n: int, pf_objetivo: float) -> list[dict]:
    """`n` operaciones cerradas cuyo profit factor da aproximadamente el pedido.

    Mitad ganadoras de `pf_objetivo` y mitad perdedoras de 1: el cociente entre
    lo ganado y lo perdido es el profit factor.
    """
    mitad = n // 2
    return _cierres([pf_objetivo] * mitad + [-1.0] * (n - mitad))


# --------------------------------------------------------------- el callado

def test_con_pocas_operaciones_no_opina():
    """Con doce, dos operaciones grandes mueven el profit factor de 0,8 a 1,6.

    Opinar ahí es tirar una moneda con cara de análisis.
    """
    v = revisar(_mezcla(12, 0.3), {"profit_factor": 1.4})
    assert v.estado == CALLADO
    assert "todavía no alcanza" in v.motivo


def test_justo_en_el_minimo_ya_opina():
    v = revisar(_mezcla(CERRADAS_MINIMAS, 1.4), {"profit_factor": 1.4})
    assert v.estado != CALLADO


def test_sin_linea_base_no_hay_nada_que_comparar():
    """La comparación es contra SU backtest, no contra un número absoluto.

    Sin respaldo no se puede decir si 1,20 es bueno o malo: depende de si la
    estrategia se midió en 1,15 o en 1,80.
    """
    assert revisar(_mezcla(60, 1.4), {}).estado == CALLADO
    assert revisar(_mezcla(60, 1.4), {"profit_factor": 0}).estado == CALLADO


def test_sin_ninguna_perdida_tampoco_opina():
    """Un profit factor infinito es justo la situación en la que no hay nada
    que medir. Tratarlo como un número altísimo pintaría de verde algo sin
    evaluar."""
    v = revisar(_cierres([1.0] * 40), {"profit_factor": 1.4})
    assert v.estado == CALLADO
    assert "sin pérdidas" in v.motivo


def test_las_operaciones_abiertas_no_cuentan():
    """Se mide sobre lo CERRADO. Una posición abierta todavía puede darse
    vuelta, y contarla adelanta un veredicto sobre algo que no terminó."""
    registro = _mezcla(40, 1.4) + [{"accion": "abrir_largo"}] * 20
    assert revisar(registro, {"profit_factor": 1.4}).cerradas == 40


# ------------------------------------------------------------- los colores

def test_rindiendo_como_se_midio_queda_en_verde():
    v = revisar(_mezcla(60, 1.4), {"profit_factor": 1.4})
    assert v.estado == VERDE
    assert v.recomendacion == "", "en verde no hay nada que recomendar"


def test_rindiendo_MEJOR_tambien_es_verde():
    """El semáforo mide deterioro, no desviación. Que rinda más de lo medido
    no es un problema que haya que señalar."""
    assert revisar(_mezcla(60, 3.0), {"profit_factor": 1.4}).estado == VERDE


def test_una_caida_moderada_es_amarillo():
    # 60% de su ventaja: cae entre 0,50 y 0,70
    v = revisar(_mezcla(60, 0.85), {"profit_factor": 1.4})
    assert v.estado == AMARILLO
    assert "mitad" in v.recomendacion


def test_perder_la_ventaja_es_naranja():
    v = revisar(_mezcla(60, 0.5), {"profit_factor": 1.4})
    assert v.estado == NARANJA
    assert "simulacro" in v.recomendacion


def test_la_banda_es_ancha_a_proposito():
    """Medido sobre las cuatro estrategias de BTCUSDT: el profit factor fuera
    de muestra quedó entre 0,80 y 0,90 del de adentro, y esas cuatro son las
    BUENAS. Un umbral en 0,9 las habría marcado a todas en amarillo el primer
    mes, y el semáforo se apagaría antes de servir para nada.
    """
    # 80% de la ventaja, que es lo que conservaron las buenas
    assert revisar(_mezcla(60, 1.12), {"profit_factor": 1.4}).estado == VERDE


# ------------------------------------------------------- lo que se muestra

def test_el_veredicto_trae_los_dos_numeros():
    """Sin los dos, "bajó al 60%" no se puede juzgar: 60% de 1,8 sigue siendo
    rentable y 60% de 1,15 no."""
    v = revisar(_mezcla(60, 0.85), {"profit_factor": 1.4})
    assert v.pf_base == 1.4
    assert v.pf_vivo is not None
    assert v.conserva is not None
    assert "1.40" in v.motivo


def test_amarillo_y_naranja_piden_mirar():
    assert revisar(_mezcla(60, 0.85), {"profit_factor": 1.4}).hay_que_mirar
    assert revisar(_mezcla(60, 0.5), {"profit_factor": 1.4}).hay_que_mirar
    assert not revisar(_mezcla(60, 1.4), {"profit_factor": 1.4}).hay_que_mirar
    assert not revisar(_mezcla(5, 1.4), {"profit_factor": 1.4}).hay_que_mirar


def test_recomienda_pero_no_apaga():
    """Con un bot y sin historial propio, actuar solo sobre una muestra chica
    haría más daño que bien. Primero alguien tiene que ver el semáforo cambiar
    de color varias veces y decidir si le cree.

    Si algún día se automatiza, esta prueba es la que hay que cambiar a
    propósito — y no una que se rompa sola.
    """
    v = revisar(_mezcla(60, 0.4), {"profit_factor": 1.4})
    assert v.estado == NARANJA
    assert not hasattr(v, "apagar")
    assert not hasattr(v, "nuevo_tamanio")


def test_un_registro_vacio_no_revienta():
    assert revisar([], {"profit_factor": 1.4}).estado == CALLADO
    assert revisar(None, {"profit_factor": 1.4}).estado == CALLADO


# ------------------------------------------- el semaforo llega al estado del bot

def test_el_estado_del_bot_trae_el_semaforo():
    """Un semaforo que nadie ve no sirve de nada.

    Va al lado del vigilante y no adentro: uno mira CUANTO opera y el otro
    COMO LE VA, se contestan en momentos distintos, y mezclarlos daria un
    unico estado que no se sabe cual de las dos cosas esta diciendo.
    """
    import pandas as pd

    from botiquant.vivo.piloto import Piloto
    from botiquant.vivo.runner import SIMULACRO, Bot

    class _Nada:
        es_real = False
        def velas(self, *a, **k):
            import numpy as np
            t = pd.date_range("2026-08-01", periods=200, freq="1h", tz="UTC")
            c = np.full(200, 100.0)
            return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1,
                                 "close": c, "volume": c}, index=t)
        def capital(self): return 1000.0
        def posicion(self, s):
            from botiquant.vivo.adaptador import Posicion
            return Posicion()

    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    doc = {
        "formato": "botiquant-bot", "version": 1, "nombre": "t",
        "ejecucion": {"simbolo": "BTC-USDT", "timeframe": "1h"},
        "respaldo": {"profit_factor": 1.4},
        "estrategia": {
            "name": "t", "direction": "long",
            "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
            "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                     "stop_type": "atr", "stop_value": 2.0,
                     "target_type": "atr", "target_value": 4.0,
                     "atr_period": 14}},
    }
    from botiquant.vivo.piloto import Vuelo
    p = Piloto()
    bot = Bot(doc=doc, adaptador=_Nada(), modo=SIMULACRO)
    bot.registro = _mezcla(60, 0.85)
    # El piloto sostiene VARIOS bots, así que lo de cada uno vive en `vuelos`
    # y arriba queda sólo lo del conjunto.
    p.vuelos[bot.simbolo] = Vuelo(bot=bot)

    v = p.estado()["vuelos"][0]
    assert "semaforo" in v, "el semáforo no llegó al estado"
    assert "vigilante" in v, "y el vigilante tiene que seguir estando"
    assert v["semaforo"]["estado"] == AMARILLO
    assert v["semaforo"]["pf_base"] == 1.4
    assert v["semaforo"]["recomendacion"]


# ============================ la memoria: sin esto no se retira nada

from botiquant.vivo.semaforo import Veredicto, actualizar, NARANJA, VERDE  # noqa: E402


def _v(color, cerradas=40):
    return Veredicto(color, "motivo", "", cerradas=cerradas)


def test_el_naranja_SUMA_una_vuelta():
    """Es la única que puede terminar en retiro. Un veredicto suelto no
    alcanza para decidir: el ciclo espera una racha, y alguien tiene que
    contarla."""
    v = actualizar(None, _v(NARANJA))
    assert v["vueltas_naranja"] == 1
    v = actualizar(v, _v(NARANJA))
    assert v["vueltas_naranja"] == 2


def test_el_verde_RESETEA():
    """Volvió a rendir: la racha anterior ya no describe a esta estrategia."""
    v = {"vueltas_naranja": 5}
    assert actualizar(v, _v(VERDE))["vueltas_naranja"] == 0


def test_el_amarillo_NI_SUMA_NI_BORRA():
    """El semáforo dice de sí mismo que un amarillo "puede ser mala suerte
    todavía": sumarlo retiraría por ruido, y borrarlo dejaría que una caída
    real se limpie sola cada vez que rebota un poco."""
    v = actualizar({"vueltas_naranja": 2}, _v(AMARILLO))
    assert v["vueltas_naranja"] == 2


def test_el_callado_tampoco_borra():
    """No hay con qué opinar. No opinar no es una opinión buena, así que no
    puede limpiar una racha que ya se había ganado."""
    v = actualizar({"vueltas_naranja": 2}, _v(CALLADO, cerradas=3))
    assert v["vueltas_naranja"] == 2


def test_solo_el_verde_borra_y_hace_falta_DEMOSTRARLO():
    """Una que cae, rebota a amarillo y vuelve a caer NO limpia la cuenta.
    Para borrarla hay que volver a rendir, no simplemente dejar de estar mal.
    """
    v = None
    for color in (NARANJA, AMARILLO, NARANJA, CALLADO, NARANJA):
        v = actualizar(v, _v(color))
    assert v["vueltas_naranja"] == 3, "un rebote a amarillo le limpió la racha"


def test_guarda_lo_que_hace_falta_para_mostrarlo():
    v = actualizar(None, _v(NARANJA), cuando="2026-09-01")
    assert v["color"] == NARANJA and v["cerradas"] == 40
    assert v["actualizado"] == "2026-09-01"
