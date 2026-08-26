"""El costo de mantener un CFD: que exista, que sea por tiempo, y que no sea comisión.

Este archivo cubre el hueco simétrico al de test_funding.py. Aquel modela el
costo de mantener de un perpetuo, que es público y exacto. Éste modela el de un
CFD, que el bróker fija y nadie publica — y que hasta ahora valía cero en todos
los backtests de S&P, oro y EURUSD.

La distinción que estas pruebas defienden es que el swap NO se puede reemplazar
subiendo la comisión. La comisión escala con cuántas operaciones hacés; el swap
con cuánto tiempo estás adentro. Son dos ejes y hacen falta los dos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.backtesting.engine import run_backtest
from botiquant.core.models import BacktestSettings, StrategySpec


def _spec(direccion: str) -> StrategySpec:
    cruce = {"op": "cross_above" if direccion == "long" else "cross_below",
             "left": {"type": "indicator", "name": "EMA", "params": {"period": 2}},
             "right": {"type": "indicator", "name": "EMA", "params": {"period": 5}}}
    return StrategySpec.from_dict({
        "name": "prueba", "direction": direccion,
        "entry_long": [cruce] if direccion == "long" else [],
        "entry_short": [cruce] if direccion == "short" else [],
        "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                 "stop_type": "atr", "stop_value": 5.0,
                 "target_type": "atr", "target_value": 10.0,
                 "reward_ratio": 2.0, "atr_period": 14},
    })


def _velas(freq: str = "1h", n: int = 600) -> pd.DataFrame:
    t = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    precio = 100 + np.sin(np.arange(n) / 30) * 8 + np.arange(n) * 0.01
    return pd.DataFrame({"open": precio, "high": precio + 0.5,
                         "low": precio - 0.5, "close": precio,
                         "volume": np.full(n, 1000.0)}, index=t)


@pytest.fixture
def velas() -> pd.DataFrame:
    return _velas()


def _final(velas, direccion="long", swap=0.0, **extra) -> float:
    ajustes = BacktestSettings(initial_capital=10_000.0, swap_anual=swap, **extra)
    return run_backtest(velas, _spec(direccion), ajustes).to_dict()[
        "metrics"]["final_equity"]


def test_en_cero_el_motor_no_cambia_en_nada(velas):
    """La red de seguridad.

    Quien no configure el costo de mantener tiene que obtener exactamente el
    mismo número que antes de que este campo existiera. Si esto falla, el
    cambio movió el resultado de los cuatro instrumentos que ya funcionaban.
    """
    assert _final(velas, swap=0.0) == run_backtest(
        velas, _spec("long"), BacktestSettings(initial_capital=10_000.0)
    ).to_dict()["metrics"]["final_equity"]


def test_le_cobra_al_comprado(velas):
    assert _final(velas, "long", swap=5.0) < _final(velas, "long", swap=0.0)


def test_tambien_le_cobra_al_vendido(velas):
    """La diferencia de fondo con el funding.

    El funding lo paga un lado y lo COBRA el otro. El swap se lo cobra el
    bróker, así que lo pagan los dos. Si esta prueba falla porque el vendido
    terminó con más capital, el swap se implementó con el signo del funding.
    """
    assert _final(velas, "short", swap=5.0) < _final(velas, "short", swap=0.0)


def test_cuanto_mas_alta_la_tasa_mas_caro(velas):
    caro = _final(velas, swap=20.0)
    barato = _final(velas, swap=5.0)
    assert caro < barato, (
        f"20% anual tiene que costar más que 5%; dio {caro:.2f} contra {barato:.2f}")


def test_es_un_costo_por_tiempo_y_no_por_operacion():
    """Lo que lo distingue de la comisión, y la razón de que sea un campo aparte.

    Las mismas velas en 1h y en 4h cubren tramos de calendario distintos: 600
    velas de una hora son 25 días y 600 de cuatro horas son 100. Con la misma
    tasa anual, el tramo largo tiene que pagar más aunque el número de barras
    sea idéntico. Una comisión no distingue eso: cobraría igual en los dos.
    """
    corto = _velas("1h")
    largo = _velas("4h")
    pago_corto = _final(corto, swap=0.0) - _final(corto, swap=10.0)
    pago_largo = _final(largo, swap=0.0) - _final(largo, swap=10.0)
    assert pago_largo > pago_corto, (
        "cuatro veces más calendario tiene que pagar más swap; "
        f"pagó {pago_largo:.4f} contra {pago_corto:.4f}")


def test_un_hueco_de_fin_de_semana_no_multiplica_el_swap():
    """Se usa la mediana del salto entre velas, no el primero ni el promedio.

    Los datos de un CFD tienen huecos de sábado y domingo. Si la duración de
    barra saliera de un salto cualquiera, un backtest que empieza un viernes
    cobraría el swap de tres días en cada barra del año entero.
    """
    base = _velas("1h", 480)
    con_hueco = pd.concat([base.iloc[:100], base.iloc[100:].set_axis(
        base.index[100:] + pd.Timedelta("48h"))])
    corrido = _final(con_hueco, swap=10.0)
    limpio = _final(base, swap=10.0)
    # el hueco cambia algo —hay más calendario— pero no puede cambiarlo tanto
    # como para que el costo se dispare por un factor de días
    assert abs(corrido - limpio) < abs(limpio - _final(base, swap=0.0)) * 3, (
        "un hueco de fin de semana descontroló el prorrateo del swap")


def test_el_swap_y_el_funding_conviven(velas):
    """Un instrumento no tiene los dos, pero el motor no puede romperse si los ve.

    Y sobre todo: se suman, no se pisan. Si uno anulara al otro, configurar mal
    un instrumento haría desaparecer un costo en silencio.
    """
    tasas = pd.Series(np.full(len(velas.index[::8]), 0.001), index=velas.index[::8])
    solo_swap = _final(velas, swap=5.0)
    los_dos = _final(velas, swap=5.0, funding=tasas)
    assert los_dos < solo_swap
