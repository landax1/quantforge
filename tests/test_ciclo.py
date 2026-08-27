"""Los parámetros del ciclo automático y qué toca hacer en cada momento.

Lo que se defiende acá es sobre todo el ORDEN de las decisiones y los límites
que no se pueden configurar. Un sistema que se maneja solo hace lo que le
dijeron mil veces sin que nadie mire: un orden equivocado no se nota en una
vuelta, se nota a la semana con las estrategias buenas apagadas y las malas
corriendo.
"""

from __future__ import annotations

import pytest

from botiquant import estados
from botiquant.ciclo import (MINAR, NADA, PROMOVER, RETIRAR, VALIDAR,
                             Parametros, que_toca)


def _p(**kw) -> Parametros:
    base = {"encendido": True}
    base.update(kw)
    return Parametros.from_dict(base)


def _e(id_: str, estado: str, *, practica_ok=True, naranja=0) -> dict:
    return {"id": id_, "estado": estado,
            "cantera": {"practica": practica_ok},
            "vueltas_en_naranja": naranja}


# ----------------------------------------------------------- el interruptor

def test_apagado_no_hace_nada():
    """Y es el default: nadie estrena un sistema autónomo prendiéndolo sin
    mirar qué hace."""
    assert Parametros().encendido is False
    t = que_toca(Parametros(), estrategias=[_e("a", estados.NUEVA)],
                 horas_desde_el_ultimo_minado=999)
    assert t.accion == NADA
    assert "apagado" in t.motivo


# ------------------------------------------------------------- el orden

def test_primero_retira_lo_que_esta_fallando():
    """Retirar libera un lugar, y por eso va antes que promover.

    Al revés, el ciclo llena los lugares con estrategias nuevas mientras deja
    corriendo las que ya se agotaron.
    """
    t = que_toca(_p(vueltas_en_naranja=3),
                 estrategias=[_e("mala", estados.PRODUCCION, naranja=3),
                              _e("lista", estados.VALIDADA)],
                 horas_desde_el_ultimo_minado=999)
    assert t.accion == RETIRAR
    assert t.ids == ["mala"]


def test_despues_promueve_lo_que_ya_esta_probado():
    """Antes de buscar más. Buscar cuando ya hay algo listo esperando es
    gastar veinte minutos para llegar al mismo lugar."""
    t = que_toca(_p(), estrategias=[_e("lista", estados.VALIDADA),
                                    _e("cruda", estados.NUEVA)],
                 horas_desde_el_ultimo_minado=999, en_practica=0)
    assert t.accion == PROMOVER
    assert t.ids == ["lista"]


def test_despues_valida_lo_que_nadie_probo():
    t = que_toca(_p(), estrategias=[_e("cruda", estados.NUEVA)],
                 horas_desde_el_ultimo_minado=999, en_practica=99)
    assert t.accion == VALIDAR
    assert t.ids == ["cruda"]


def test_y_recien_al_final_busca_mas():
    t = que_toca(_p(minar_cada_horas=12), estrategias=[],
                 horas_desde_el_ultimo_minado=13)
    assert t.accion == MINAR


def test_si_no_paso_el_tiempo_no_mina():
    t = que_toca(_p(minar_cada_horas=12), estrategias=[],
                 horas_desde_el_ultimo_minado=3)
    assert t.accion == NADA
    assert "próximo minado" in t.motivo


# --------------------------------------------------------------- los topes

def test_no_promueve_si_no_hay_lugar():
    """El tope es el número que más importa: cada estrategia corriendo es una
    porción del capital."""
    t = que_toca(_p(max_en_practica=3),
                 estrategias=[_e("lista", estados.VALIDADA)],
                 horas_desde_el_ultimo_minado=1, en_practica=3)
    assert t.accion != PROMOVER


def test_promueve_solo_hasta_llenar_los_huecos():
    listas = [_e(f"l{i}", estados.VALIDADA) for i in range(10)]
    t = que_toca(_p(max_en_practica=5), estrategias=listas,
                 horas_desde_el_ultimo_minado=1, en_practica=3)
    assert t.accion == PROMOVER
    assert len(t.ids) == 2, "sólo los que entran"


def test_no_promueve_lo_que_la_cantera_frena():
    """El ciclo no puede saltearse las puertas: son lo único que hay entre un
    sistema que promueve solo y algo que tuvo suerte."""
    t = que_toca(_p(), estrategias=[_e("floja", estados.VALIDADA,
                                       practica_ok=False)],
                 horas_desde_el_ultimo_minado=1, en_practica=0)
    assert t.accion != PROMOVER


def test_valida_de_a_pocas():
    """Cada validación es un backtest completo más mil simulaciones."""
    crudas = [_e(f"c{i}", estados.NUEVA) for i in range(30)]
    t = que_toca(_p(validar_por_vuelta=5), estrategias=crudas,
                 horas_desde_el_ultimo_minado=1, en_practica=99)
    assert len(t.ids) == 5


def test_no_retira_al_primer_naranja():
    """Un naranja puede volver a verde. Retirar de inmediato haría que el
    ciclo se coma sus propias estrategias en una racha mala."""
    t = que_toca(_p(vueltas_en_naranja=3),
                 estrategias=[_e("dudosa", estados.PRODUCCION, naranja=1)],
                 horas_desde_el_ultimo_minado=1)
    assert t.accion != RETIRAR


# ------------------------------------------- lo que NO se puede configurar

def test_la_promocion_automatica_no_llega_a_plata_real():
    """Aunque venga en el payload.

    Que algo pase a operar con plata de verdad es una decisión de una persona,
    aunque todo lo demás corra solo. No es una preferencia que se configura.
    Si algún día se automatiza, hay que cambiar el código a propósito — y esta
    prueba es la que se pone roja para avisarlo.
    """
    p = Parametros.from_dict({"promover_hasta": estados.PRODUCCION})
    assert p.promover_hasta == estados.PRACTICA


def test_el_ciclo_nunca_devuelve_una_tarea_de_produccion():
    listas = [_e("l", estados.PRACTICA)]
    t = que_toca(_p(), estrategias=listas, horas_desde_el_ultimo_minado=1)
    assert estados.PRODUCCION not in (t.accion, t.motivo)


# ----------------------------------------------------------- los defaults

def test_los_valores_por_defecto_son_timidos():
    """Un ciclo que arranca minando cada hora es un ciclo que nadie deja
    prendido. Los defaults tienen que producir un sistema del que uno se pueda
    ir tranquilo la primera noche."""
    p = Parametros()
    assert p.encendido is False
    assert p.minar_cada_horas >= 12
    assert p.max_en_practica <= 5
    assert p.reservar_pct >= 20, "sin tramo reservado nada puede llegar a real"


@pytest.mark.parametrize("clave,valor,esperado", [
    ("minar_cada_horas", 0, 1),          # no se puede minar cada cero horas
    ("minar_cada_horas", 9999, 168),     # ni cada año
    ("max_en_practica", 0, 1),
    ("max_en_practica", 999, 20),
    ("reservar_pct", 90, 60),            # reservar casi todo no deja con qué buscar
    ("vueltas_en_naranja", 0, 1),
])
def test_los_valores_absurdos_se_acotan(clave, valor, esperado):
    """En un sistema que corre solo, un número absurdo no lo corrige nadie."""
    assert getattr(Parametros.from_dict({clave: valor}), clave) == esperado


def test_un_valor_que_no_es_numero_no_rompe_el_ciclo():
    assert Parametros.from_dict({"minar_cada_horas": "doce"}).minar_cada_horas == 12


def test_la_ida_y_vuelta_conserva_todo():
    p = _p(minar_cada_horas=24, max_en_practica=8, instrumentos=["BTCUSDT"])
    assert Parametros.from_dict(p.to_dict()).to_dict() == p.to_dict()
