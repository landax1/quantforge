"""El reloj del bróker viaja al robot exportado.

MetaTrader fecha sus velas con la hora del SERVIDOR del bróker, y los datos con
los que mina esta aplicación están en UTC. La mayoría de los brókers corre en
UTC+2 o UTC+3, así que una estrategia minada para operar 13:00–16:00 UTC tiene
que disparar tres horas más tarde en la hora del servidor.

Si eso queda mal, no falla nada: la estrategia opera en la franja equivocada y
los resultados no se parecen a los del backtest. Por eso el valor sale de la
configuración del usuario y viene ya puesto en el archivo, en vez de quedar en
cero esperando que alguien lo recuerde.

La zona horaria del usuario no interviene en ningún momento: dos personas en
países distintos con el mismo bróker obtienen backtests idénticos.
"""

from __future__ import annotations

import re

import pytest

from botiquant.core import sesiones
from botiquant.core.models import StrategySpec
from botiquant.generator.generator import Genome, build_spec
from botiquant.reports.mql5 import export_mql5


def _offset_del_codigo(code: str) -> int:
    m = re.search(r"input int\s+InpServerUTCOffset\s*=\s*(-?\d+)", code)
    assert m, "el robot no declara InpServerUTCOffset"
    return int(m.group(1))


def _spec_con_franja() -> StrategySpec:
    g = Genome(driver="ema_cross", session="nueva_york")
    return build_spec(g)


@pytest.mark.parametrize("horas", [-5, -3, 0, 2, 3, 5])
def test_el_offset_pedido_llega_al_robot(horas):
    code = export_mql5(_spec_con_franja(), server_utc_offset=horas)
    assert _offset_del_codigo(code) == horas


def test_por_defecto_es_cero():
    """Cero es honesto —hay brókers en UTC— y por eso la aplicación lo pregunta."""
    assert _offset_del_codigo(export_mql5(_spec_con_franja())) == 0


def test_la_franja_minada_es_la_que_se_exporta():
    """Las horas del robot son las de la sesión, en UTC; el offset las corre."""
    ini, fin, _dias, _en, _es = sesiones.SESIONES["nueva_york"]
    code = export_mql5(_spec_con_franja(), server_utc_offset=3)
    assert re.search(rf"InpStartHourUTC\s*=\s*{ini}\b", code)
    assert re.search(rf"InpEndHourUTC\s*=\s*{fin}\b", code)
    # y el filtro descuenta el offset antes de comparar la hora
    assert "TimeCurrent() - (long)InpServerUTCOffset * 3600" in code


def test_sin_franja_el_offset_no_cambia_nada():
    """Una estrategia sin restricción horaria opera igual en cualquier servidor."""
    sin_franja = build_spec(Genome(driver="ema_cross"))
    code = export_mql5(sin_franja, server_utc_offset=3)
    assert re.search(r"InpUseSession\s*=\s*false", code), (
        "sin franja horaria el filtro tiene que venir desactivado")
