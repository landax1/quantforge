"""Las puertas que impiden que algo sin probar toque plata.

Lo que se defiende acá no es que las varas sean las correctas —eso es una
decisión de producto y va a cambiar— sino que el filtro no se pueda saltear:
que lo que no se midió no pase, que el destino sin riesgo no pida nada, y que
el destino con riesgo pida evidencia de fuera de muestra.
"""

from __future__ import annotations

import pytest

from botiquant.cantera import (PRACTICA, REAL, SIMULACRO, VARAS, por_que_no,
                               revisar)


def _meta(*, trades=200, pf=1.5, expr=0.3, dd=10.0,
          oos_trades=80, oos_pf=1.2, con_oos=True) -> dict:
    m = {"metrics": {"trades": trades, "profit_factor": pf,
                     "expectancy_r": expr, "max_drawdown_pct": dd}}
    if con_oos:
        m["oos"] = {"trades": oos_trades, "profit_factor": oos_pf}
    return m


# ------------------------------------------------------- el destino sin riesgo

def test_el_simulacro_no_pide_nada():
    """Es gratis, no manda órdenes, y su único propósito es que alguien MIRE.

    Poner una vara acá es impedirle a la gente mirar qué haría el bot, que es
    justo el paso que queremos que den antes de arriesgar algo.
    """
    assert revisar(_meta(trades=3, pf=0.2, dd=90.0, con_oos=False),
                   SIMULACRO).pasa
    assert VARAS[SIMULACRO] == []


# --------------------------------------------------- el tamaño de muestra

def test_un_profit_factor_altisimo_con_pocas_operaciones_NO_pasa():
    """La regla más valiosa y la que más se resiste.

    Un profit factor de 32 sobre nueve operaciones no es una estrategia
    excepcional: son nueve tiradas de moneda que salieron bien. Rechazarla se
    siente como dejar plata en la mesa y es exactamente al revés.
    """
    r = revisar(_meta(trades=9, pf=32.0, expr=3.0, dd=2.0,
                      oos_trades=4, oos_pf=20.0), REAL)
    assert not r.pasa
    assert any(p["metrica"] == "trades" for p in r.faltan)


def test_la_muestra_fuera_de_muestra_tambien_tiene_piso():
    """Cincuenta operaciones en el tramo reservado, no cinco.

    Sin eso, una estrategia con 500 operaciones en total y 6 afuera pasaría
    por tener evidencia externa cuando en realidad no la tiene.
    """
    assert not revisar(_meta(oos_trades=6), REAL).pasa


# ------------------------------------------------- lo que falta no se regala

def test_una_metrica_sin_medir_NO_se_da_por_cumplida():
    """La ausencia de evidencia no es evidencia.

    Dar por buena una métrica que nadie midió es la forma más silenciosa de
    saltarse el filtro entero: la estrategia pasa, nadie ve un error, y lo que
    la habilitó fue un campo vacío.
    """
    m = _meta()
    del m["metrics"]["expectancy_r"]
    r = revisar(m, REAL)
    assert not r.pasa
    assert any(p["detalle"] == "sin medir" for p in r.faltan)


def test_sin_tramo_fuera_de_muestra_no_se_llega_a_real():
    """Es la puerta que separa "encontré algo" de "aguantó donde no miré"."""
    assert not revisar(_meta(con_oos=False), REAL).pasa


def test_sin_tramo_fuera_de_muestra_SI_se_puede_practicar():
    """Con plata de juguete, el costo de equivocarse es el tiempo.

    Exigir out-of-sample para mirar en demo dejaría a la gente sin el paso
    intermedio, que es justo donde se aprende.
    """
    assert revisar(_meta(con_oos=False), PRACTICA).pasa


# ------------------------------------------------------------ los umbrales

@pytest.mark.parametrize("campo,valor", [
    ("pf", 1.05),          # apenas rentable
    ("expr", 0.05),        # expectativa muy chica
    ("dd", 35.0),          # caída que nadie aguanta despierto
])
def test_real_rechaza_lo_flojo(campo, valor):
    assert not revisar(_meta(**{campo: valor}), REAL).pasa


def test_una_que_cumple_todo_pasa():
    """El control. Si esto se pone rojo, las varas quedaron imposibles y el
    filtro dice que no a todo — que es una forma silenciosa de no servir."""
    r = revisar(_meta(), REAL)
    assert r.pasa, r.faltan


def test_una_estrategia_que_perdio_fuera_de_muestra_no_llega_a_real():
    """El piso duro: haber ganado donde la búsqueda no miró.

    Un profit factor apenas por encima de 1 fuera de muestra es evidencia
    débil, y el número se muestra para que se pueda juzgar. Pero por DEBAJO
    de 1 no hay nada que juzgar: perdió.
    """
    assert not revisar(_meta(oos_pf=0.85), REAL).pasa
    assert revisar(_meta(oos_pf=1.02), REAL).pasa


# -------------------------------------------------------------- el mensaje

def test_el_rechazo_dice_QUE_hacer_y_no_solo_que_no():
    m = _meta(con_oos=False)
    texto = por_que_no(revisar(m, REAL))
    assert "reservando un tramo" in texto


def test_nombra_una_sola_vara_y_no_seis():
    """Una lista de seis incumplimientos no se lee; la primera ya alcanza."""
    texto = por_que_no(revisar(_meta(trades=5, pf=0.5, expr=0.0, dd=80.0,
                                     oos_trades=2, oos_pf=0.3), REAL))
    assert texto.count(":") <= 1
    assert len(texto) < 120


def test_cuando_pasa_no_hay_nada_que_explicar():
    assert por_que_no(revisar(_meta(), REAL)) == ""


def test_un_destino_inventado_se_rechaza():
    with pytest.raises(ValueError, match="Destino"):
        revisar(_meta(), "turbo")


# ----------------------------------------------- la escalera es una escalera

def test_lo_que_pasa_a_real_pasa_tambien_a_practica():
    """Si la vara de real fuera más floja que la de práctica en algo, la
    escalera dejaría de ser una escalera y nadie lo notaría."""
    m = _meta()
    assert revisar(m, REAL).pasa
    assert revisar(m, PRACTICA).pasa
    assert revisar(m, SIMULACRO).pasa
