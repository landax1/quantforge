"""El funding de un perpetuo: quién paga, quién cobra, y que un CFD no lo sufra.

Es la tercera clase de costo del motor y funciona distinto a las otras dos: no
se paga al abrir ni al cerrar, sino cada ocho horas por TENER la posición
abierta. Modelarlo no es un refinamiento contable — es lo que permite ver una
familia de estrategias que hoy no se puede.

Medido sobre siete años de BTCUSDT en Binance: la tasa media fue +0,01061% por
cobro, que son +11,61% anual, y fue negativa sólo el 14,3% del tiempo. Tasa
positiva significa que los largos le pagan a los cortos. O sea que durante siete
años el lado corto de Bitcoin COBRÓ 11,6% anual sólo por estar puesto — más de
lo que rinden casi todas las estrategias que encuentra la aplicación.

Por eso el signo importa tanto como el tamaño, y por eso estas pruebas lo miran
en las dos direcciones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.backtesting.engine import run_backtest
from botiquant.core.models import BacktestSettings, StrategySpec

#: Una estrategia que compra al principio y no vende nunca. Sirve para aislar
#: el funding: sin salidas, lo único que mueve el capital es el precio y la
#: tasa, así que la diferencia entre dos corridas ES el funding.
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


@pytest.fixture
def velas() -> pd.DataFrame:
    """Un mercado que sube y baja, con velas de una hora."""
    n = 600
    t = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    precio = 100 + np.sin(np.arange(n) / 30) * 8 + np.arange(n) * 0.01
    return pd.DataFrame({"open": precio, "high": precio + 0.5,
                         "low": precio - 0.5, "close": precio,
                         "volume": np.full(n, 1000.0)}, index=t)


def _tasas(velas: pd.DataFrame, valor: float) -> pd.Series:
    """Una tasa fija cada ocho horas, como liquida un exchange de verdad."""
    idx = velas.index[::8]
    return pd.Series(np.full(len(idx), valor), index=idx, name="funding")


def _final(velas, direccion, funding=None) -> float:
    ajustes = BacktestSettings(initial_capital=10_000.0, funding=funding)
    return run_backtest(velas, _spec(direccion), ajustes).to_dict()[
        "metrics"]["final_equity"]


def test_sin_serie_el_motor_no_cambia_en_nada(velas):
    """La red de seguridad de todo este cambio.

    Un CFD no tiene funding y no puede pagar nada. Si esto falla, el cambio
    alteró el resultado de los cuatro instrumentos que ya funcionaban.
    """
    assert _final(velas, "long", None) == _final(velas, "long", pd.Series(dtype=float))


def test_tasa_positiva_le_cobra_al_comprado(velas):
    """Positiva = los largos pagan. Es la situación normal en cripto."""
    sin = _final(velas, "long", None)
    con = _final(velas, "long", _tasas(velas, 0.001))
    assert con < sin, (
        "con tasa positiva el comprado tiene que terminar con menos capital; "
        f"terminó con {con:.2f} contra {sin:.2f} sin funding")


def test_tasa_positiva_le_paga_al_vendido(velas):
    """Y ésta es la mitad que importa para el producto.

    Si sólo se modelara como costo, la aplicación seguiría sin poder encontrar
    la familia de estrategias cortas que vive de cobrar el funding.
    """
    sin = _final(velas, "short", None)
    con = _final(velas, "short", _tasas(velas, 0.001))
    assert con > sin, (
        "con tasa positiva el vendido tiene que COBRAR; "
        f"terminó con {con:.2f} contra {sin:.2f} sin funding")


def test_la_tasa_negativa_invierte_los_papeles(velas):
    """Pasó el 14,3% del tiempo en siete años: ahí el comprado cobra."""
    assert _final(velas, "long", _tasas(velas, -0.001)) > _final(velas, "long", None)
    assert _final(velas, "short", _tasas(velas, -0.001)) < _final(velas, "short", None)


def test_cobra_mas_cuanto_mas_tiempo_abierta(velas):
    """No es un costo por operación: es un costo por TIEMPO.

    Es lo que lo distingue del spread y de la comisión, y lo que hace que
    penalice a las estrategias que mantienen posiciones largas en el tiempo.
    """
    poco = _final(velas, "long", _tasas(velas, 0.001))
    mucho = _final(velas, "long", pd.Series(
        np.full(len(velas.index[::2]), 0.001), index=velas.index[::2]))
    assert mucho < poco, (
        "cobrando cada dos horas en vez de cada ocho tiene que costar más")


def test_una_tasa_fuera_del_rango_no_rompe_nada(velas):
    """Las liquidaciones anteriores o posteriores a los datos se ignoran.

    Pasa siempre en la práctica: la serie de funding y la de velas se bajan por
    separado y nunca empiezan y terminan exactamente igual.
    """
    fuera = pd.Series([0.001, 0.001],
                      index=pd.to_datetime(["2020-01-01", "2030-01-01"], utc=True))
    assert _final(velas, "long", fuera) == _final(velas, "long", None)
