"""Cada EA arriesga sobre SU PORCION de la cuenta, no sobre el balance entero.

Es el bloqueante para armar un portafolio en MetaTrader, y fallaba en
silencio: cada EA respetaba su propio numero y entre todos arriesgaban de mas.

    cinco EA al 1% midiendo contra el balance total
    -> una operacion simultanea de los cinco arriesga 5%, no 1%
    con veinte, 20%

Nadie se entera hasta que la cuenta se mueve mucho mas de lo esperado.
"""

from __future__ import annotations

import pytest

from botiquant.core.models import StrategySpec
from botiquant.reports.mql5 import export_mql5


def _spec() -> StrategySpec:
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return StrategySpec.from_dict({
        "name": "x", "direction": "long",
        "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
        "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                 "stop_type": "atr", "stop_value": 2.0,
                 "target_type": "atr", "target_value": 4.0},
    })


def test_el_tamanio_se_calcula_sobre_la_porcion_y_no_sobre_el_balance():
    """La linea que arregla el problema de fondo."""
    code = export_mql5(_spec(), ea_name="BQ_A", porcion=20.0)
    assert "double miParte = AccountInfoDouble(ACCOUNT_BALANCE) * InpPorcionPct / 100.0;" in code
    assert "double riskMoney = miParte * InpRiskPct / 100.0;" in code
    assert "riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct" not in code, (
        "volvio a medir contra el balance entero")


def test_la_porcion_viaja_al_script():
    assert "InpPorcionPct  = 20;" in export_mql5(_spec(), ea_name="a", porcion=20.0)
    assert "InpPorcionPct  = 5;" in export_mql5(_spec(), ea_name="a", porcion=5.0)


def test_por_defecto_maneja_la_cuenta_entera():
    """Un EA solo en su cuenta tiene que comportarse igual que antes.

    Si el default fuera otro, todos los exportados hasta hoy pasarian a
    operar mas chico sin que nadie lo pidiera.
    """
    assert "InpPorcionPct  = 100;" in export_mql5(_spec(), ea_name="a")


def test_el_aviso_de_riesgo_tambien_mide_contra_la_porcion():
    """Medirlo contra el balance entero haria que un bot con 20% de la cuenta
    reporte 0,2% cuando pidio 1%, y quien lo lea va a pensar que el calculo
    esta mal cuando el que esta mal es el aviso.

    La variable se llamaba `balance` conteniendo la PORCION, y el mensaje decia
    "del balance". Visto en el probador de MetaTrader: un EA con el 30% imprimio
    "pierde 30.64 = 0.98% del balance" sobre un balance de 10.410, donde 30,64
    es el 0,3%. El calculo estaba bien y la frase producia justo la duda que
    este bloque venia a evitar.
    """
    code = export_mql5(_spec(), ea_name="a", porcion=20.0)
    assert ("double miParte = AccountInfoDouble(ACCOUNT_BALANCE) * "
            "InpPorcionPct / 100.0;") in code
    assert "MathAbs(loss) / miParte * 100.0" in code
    # y el texto dice contra que mide, con la porcion en plata al lado
    assert "parte (%.0f%% de la cuenta" in code


def test_sigue_siendo_editable():
    """Va como `input`: alguien puede querer repartir distinto de lo que
    propuso la aplicacion."""
    assert "input double InpPorcionPct" in export_mql5(_spec(), ea_name="a")


def test_cinco_bots_al_veinte_por_ciento_suman_la_cuenta():
    """La cuenta que hay que poder hacer de cabeza: cinco porciones de 20%
    reparten el 100% y cada uno arriesga 1% DE LO SUYO, o sea 0,2% del total.
    Los cinco juntos: 1%. Que es lo que se pidio.
    """
    porciones = [20.0] * 5
    assert sum(porciones) == 100.0
    riesgo_total = sum(p / 100.0 * 1.0 for p in porciones)
    assert riesgo_total == pytest.approx(1.0)
