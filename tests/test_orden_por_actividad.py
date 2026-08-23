"""El desempate por frecuencia, para quien tiene fecha de vencimiento.

Nació de un fracaso medido. La categoría para desafíos de cuenta fondeada pedía
la frecuencia como FILTRO —al menos tres operaciones por semana— y devolvía
cero. Bajarla a dos devolvía una; a una y media, cero o dos según la semilla.
Con uno o dos aciertos en mil cuatrocientas candidatas, encontrar algo pasa a
depender de la suerte.

La razón de fondo no es del buscador: ser rentable es ser selectivo, y ser
selectivo es operar poco. Medido a 30 minutos sobre SP500, entre genomas al
azar la mediana es 7,7 operaciones por semana, y entre las que además pasan un
filtro de calidad cae a 0,6.

Como orden en cambio siempre hay tabla. Entran las que pasaron la vara y arriba
quedan las que más operan.
"""

from __future__ import annotations

from botiquant.backtesting.metrics import fitness

#: Lo mínimo para que `fitness` no corte por cero operaciones. Los valores no
#: importan salvo el profit factor, que gobierna la viabilidad del score.
BASE = {"trades": 200, "profit_factor": 1.4, "sharpe": 0.8, "net_profit": 1000.0,
        "max_drawdown_pct": 8.0, "cagr_pct": 6.0, "win_rate_pct": 45.0,
        "recovery_factor": 3.0, "months_positive_pct": 60.0,
        "top_trade_share_pct": 10.0, "exposure_pct": 20.0,
        "trades_per_month": 8.0, "years": 4.0}


def _con(**cambios) -> dict:
    return BASE | cambios


def test_entre_dos_iguales_gana_la_que_mas_opera():
    """Es todo el punto: desempatar, no elegir otra cosa."""
    quieta = fitness(_con(trades_per_week=0.2), "activity")
    activa = fitness(_con(trades_per_week=4.0), "activity")
    assert activa > quieta, (
        "con todo lo demás igual, la que opera más seguido tiene que quedar "
        "arriba — es lo único que este modo agrega")


def test_no_cambia_el_orden_del_modo_de_siempre():
    """`composite` no puede moverse: es el que usa todo el resto."""
    for por_semana in (0.2, 1.0, 4.0, 40.0):
        m = _con(trades_per_week=por_semana)
        assert fitness(m, "composite") == fitness(m, "otro_cualquiera"), (
            "el modo por defecto empezó a mirar la frecuencia; eso cambiaría el "
            "orden de todas las búsquedas que no lo pidieron")


def test_el_premio_se_topa_para_que_no_gane_el_ruido():
    """Cinco por semana es una por día hábil: más que eso no es más útil.

    Sin tope, una estrategia que abre trescientas veces por semana —ruido de
    microestructura, no una idea— le ganaría a cualquiera por goleada.
    """
    justo = fitness(_con(trades_per_week=5.0), "activity")
    exagerada = fitness(_con(trades_per_week=300.0), "activity")
    assert justo == exagerada, (
        "el premio por frecuencia dejó de toparse; una candidata que opera "
        "trescientas veces por semana pasaría a ganar por operar, no por servir")


def test_el_desempate_no_puede_tapar_a_la_calidad():
    """Una mala muy activa no puede pasarle a una buena tranquila.

    Si el premio fuera grande, esta categoría dejaría de traer estrategias
    buenas y traería estrategias movidas, que es exactamente lo que no sirve
    para pasar un desafío.
    """
    buena_quieta = fitness(_con(profit_factor=1.8, recovery_factor=6.0,
                                months_positive_pct=75.0, sharpe=1.4,
                                trades_per_week=0.2), "activity")
    mala_activa = fitness(_con(profit_factor=1.02, recovery_factor=0.6,
                               months_positive_pct=40.0, sharpe=0.1,
                               trades_per_week=5.0), "activity")
    assert buena_quieta > mala_activa, (
        "el premio por frecuencia se volvió tan grande que una estrategia "
        "floja pero movida le gana a una sólida; el desempate pasó a decidir")
