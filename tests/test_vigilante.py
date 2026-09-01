"""El vigilante de frecuencia: que avise cuando hay algo, y que se calle cuando no.

De las dos mitades, la que más cuesta hacer bien es la segunda. Un vigilante
que grita cuando todavía no puede saber nada se apaga a la semana, y un
vigilante apagado es peor que ninguno: da la sensación de estar cubierto.
"""

from __future__ import annotations

import pandas as pd
import pytest

from botiquant.vivo.vigilante import (AMARILLO, CALLADO, ESPERADAS_MINIMAS,
                                      VERDE, por_semana, revisar)

ARRANQUE = pd.Timestamp("2026-08-01", tz="UTC")


def _respaldo(trades=148, years=4.07):
    return {"trades": trades, "years": years}


def _abrio(n):
    return [{"accion": "abrir_largo"} for _ in range(n)]


def _en(semanas):
    return ARRANQUE + pd.Timedelta(weeks=semanas)


# --------------------------------------------------------- cuándo callarse

def test_no_opina_hasta_tener_con_que():
    """La mitad que más importa.

    Medido sobre las estrategias guardadas: operan entre 0,13 y 0,70 veces por
    semana. Con 0,13 esperadas hay que esperar dos meses para ver UNA. Decir
    "no está operando" a las dos semanas no es una alerta temprana, es ruido.
    """
    v = revisar(_respaldo(94, 13.59), [], ARRANQUE, _en(2))   # 0,13 por semana
    assert v.estado == CALLADO
    assert not v.opina
    assert "semanas más" in v.razon


def test_callado_NO_quiere_decir_que_este_bien():
    """Decir que está bien sería tan equivocado como decir que está mal."""
    v = revisar(_respaldo(), [], ARRANQUE, _en(1))
    assert v.estado == CALLADO
    assert v.estado != VERDE


def test_cuando_junta_suficiente_esperado_si_opina():
    # 0,70 por semana × 5 semanas = 3,5 esperadas, por encima del mínimo
    v = revisar(_respaldo(), _abrio(3), ARRANQUE, _en(5))
    assert v.opina


def test_el_umbral_esta_en_las_esperadas_y_no_en_el_tiempo():
    """Una estrategia que opera seguido puede juzgarse en dias; una lenta
    necesita meses. El reloj no es la medida correcta: las esperadas si."""
    rapida = revisar({"trades": 5200, "years": 1.0}, _abrio(90), ARRANQUE,
                     _en(1))          # 100 por semana
    lenta = revisar(_respaldo(94, 13.59), [], ARRANQUE, _en(1))
    assert rapida.opina and not lenta.opina


# ------------------------------------------------------------ cuándo avisar

def test_avisa_cuando_esperaba_y_no_abrio_ninguna():
    """El caso que justifica todo el vigilante.

    Un bot que deberia haber abierto varias veces y no abrio ninguna no esta
    teniendo un mal mes: esta roto, y roto de las maneras que NO dan error.
    """
    v = revisar(_respaldo(), [], ARRANQUE, _en(6))
    assert v.estado == AMARILLO
    assert "no abrió ninguna" in v.razon
    # y dice qué revisar, que es la mitad del valor de una alerta
    assert "permiso de trading" in v.razon


def test_avisa_cuando_opera_MUCHO_mas_de_lo_medido():
    """Diez veces mas operaciones no es la estrategia que se probo.

    Es el lado que se olvida: se vigila que no pare, y no que se desboque.
    """
    v = revisar(_respaldo(), _abrio(40), ARRANQUE, _en(6))
    assert v.estado == AMARILLO
    assert "mucho más" in v.razon


def test_no_avisa_por_una_desviacion_normal():
    """La frecuencia de una estrategia varía sola con el régimen del mercado.

    Estrechar la banda convierte al vigilante en alguien que avisa todo el
    tiempo, que es la forma de que lo apaguen.
    """
    # esperaba ~4,2 en 6 semanas; 3 y 6 son desviaciones que pasan solas
    assert revisar(_respaldo(), _abrio(3), ARRANQUE, _en(6)).estado == VERDE
    assert revisar(_respaldo(), _abrio(6), ARRANQUE, _en(6)).estado == VERDE


# ------------------------------------------------------------- lo que cuenta

def test_solo_cuenta_las_vueltas_que_ABRIERON():
    """El registro tiene una fila por vuelta y el bot da una por vela.

    Contarlas todas daria miles de "operaciones" por semana y el vigilante
    diria que se desboco siempre.
    """
    registro = ([{"accion": "nada"}] * 500 + _abrio(4)
                + [{"accion": "cerrar"}] * 4)
    v = revisar(_respaldo(), registro, ARRANQUE, _en(6))
    assert v.observadas == 4


def test_los_cierres_no_cuentan_como_operaciones_nuevas():
    v = revisar(_respaldo(), [{"accion": "cerrar"}] * 10, ARRANQUE, _en(6))
    assert v.observadas == 0


# ------------------------------------------------------- lo que no se sabe

def test_sin_frecuencia_esperada_no_hay_nada_que_comparar():
    """Una estrategia guardada por una version vieja no trae `years`."""
    assert revisar({"trades": 100}, _abrio(5), ARRANQUE, _en(6)).estado == CALLADO
    assert por_semana({"trades": 100}) is None


def test_sin_arranque_no_hay_ventana():
    assert revisar(_respaldo(), [], None, _en(6)).estado == CALLADO


def test_la_frecuencia_se_calcula_bien():
    """148 operaciones en 4,07 años son 0,70 por semana."""
    assert por_semana(_respaldo()) == pytest.approx(0.699, abs=0.01)


# ------------------------------------------------ el vigilante en el piloto

def test_el_estado_del_bot_trae_el_veredicto_del_vigilante():
    """Una comprobacion que nadie lee no vigila nada.

    Va adentro del estado —lo que la pantalla pide en cada refresco— y no en
    un endpoint aparte que haya que ir a buscar.
    """
    import numpy as np

    from botiquant.vivo.adaptador import Posicion
    from botiquant.vivo.piloto import Piloto
    from botiquant.vivo.runner import SIMULACRO, Bot

    class _Ex:
        es_real = False
        def velas(self, s, i, limite=500):
            n = 200
            t = pd.date_range("2026-08-01", periods=n, freq="1h", tz="UTC")
            c = 78_000 + np.sin(np.arange(n) / 9) * 900
            return pd.DataFrame({"open": c, "high": c + 60, "low": c - 60,
                                 "close": c, "volume": np.full(n, 10.0)}, index=t)
        def capital(self): return 10_000.0
        def posicion(self, s): return Posicion()
        def contrato(self, s): return {"decimales_cantidad": 4,
                                       "minimo": 0.0001}
        def abrir(self, *a): return {}
        def cerrar(self, *a): return {}

    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    doc = {"formato": "botiquant-bot", "version": 1, "nombre": "t",
           "ejecucion": {"simbolo": "BTC-USDT", "timeframe": "1h"},
           "respaldo": {"trades": 148, "years": 4.07},
           "estrategia": {"name": "t", "direction": "long",
                          "entry_long": [{"left": ema(5), "op": "cross_above",
                                          "right": ema(20)}],
                          "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                                   "stop_type": "atr", "stop_value": 2.0,
                                   "target_type": "atr", "target_value": 4.0,
                                   "atr_period": 14}}}
    from botiquant.vivo.piloto import Vuelo
    p = Piloto()
    _b = Bot(doc=doc, adaptador=_Ex(), modo=SIMULACRO)
    p.vuelos[_b.simbolo] = Vuelo(bot=_b)
    e = p.estado()["vuelos"][0]
    assert "vigilante" in e
    # recien arrancado no puede opinar, y eso es lo correcto
    assert e["vigilante"]["estado"] == CALLADO


def test_el_vigilante_mira_el_registro_ENTERO_y_no_las_ultimas_cuarenta():
    """El estado recorta el registro para mostrarlo; el vigilante no puede
    contar sobre ese recorte o un bot viejo pareceria que nunca opera."""
    import inspect

    from botiquant.vivo import piloto
    fuente = inspect.getsource(piloto.Piloto._vigilar)
    assert "b.registro" in fuente
    assert "[-40:]" not in fuente
