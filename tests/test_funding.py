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


# ------------------------------------------- el viaje de ida y vuelta al disco
#
# Todo lo de arriba usa series armadas en memoria. Esta parte cubre el hueco
# que eso dejaba: guardar la serie y volver a leerla. Se descubrio minando de
# verdad, cuando el minado entero murio con AttributeError en medio.

def test_una_serie_guardada_vuelve_como_fechas_y_no_como_texto(tmp_path):
    """`parse_dates` NO parsea marcas con zona horaria, y NO avisa.

    Deja el indice como texto, y el error aparece mucho despues —al pedirle
    `.tz`— en medio de un minado. Es el peor tipo de fallo: silencioso donde
    se origina y ruidoso donde no se puede entender.
    """
    from botiquant.data.store import DataStore
    from botiquant.database.db import Database

    st = DataStore(tmp_path / "datasets", Database(tmp_path / "bq.sqlite"))
    idx = pd.to_datetime(["2019-09-10 08:00:00", "2019-09-10 16:00:00"], utc=True)
    st.guardar_funding("abc", pd.Series([0.0001, -0.0002], index=idx, name="funding"))

    vuelta = st.funding("abc")
    assert isinstance(vuelta.index, pd.DatetimeIndex)
    assert vuelta.index.tz is not None
    assert list(vuelta.values) == [0.0001, -0.0002]


def test_las_tasas_con_milisegundos_tambien_vuelven(tmp_path):
    """Binance informa el momento de liquidacion con precisiones distintas.

    Medido sobre los 7.629 cobros reales de BTCUSDT: 3.294 traen milisegundos
    y el resto no. No es un caso raro — es casi la mitad. Con una sola de esas
    filas, pandas se rinde con el archivo ENTERO.
    """
    from botiquant.data.store import DataStore
    from botiquant.database.db import Database

    st = DataStore(tmp_path / "datasets", Database(tmp_path / "bq.sqlite"))
    # La misma trampa, en el armado de esta prueba: sin `format="ISO8601"`,
    # pandas revienta ACA antes de llegar al store. Queda como recordatorio de
    # que el problema no era del store sino de mezclar precisiones.
    idx = pd.to_datetime(["2019-09-10 08:00:00+00:00",
                          "2019-09-14 16:00:00.001000+00:00"],
                         utc=True, format="ISO8601")
    st.guardar_funding("abc", pd.Series([0.0001, 0.0002], index=idx, name="funding"))

    vuelta = st.funding("abc")
    assert isinstance(vuelta.index, pd.DatetimeIndex)
    assert len(vuelta) == 2


def test_el_motor_puede_usar_la_serie_que_volvio_del_disco(tmp_path, velas):
    """La comprobacion de fondo: que el viaje entero sirva.

    Guardar bien y leer bien no alcanza si lo que vuelve no lo puede consumir
    el motor — que es exactamente donde fallaba.
    """
    from botiquant.data.store import DataStore
    from botiquant.database.db import Database

    st = DataStore(tmp_path / "datasets", Database(tmp_path / "bq.sqlite"))
    st.guardar_funding("abc", _tasas(velas, 0.001))

    con = _final(velas, "long", st.funding("abc"))
    sin = _final(velas, "long", None)
    assert con < sin, "la serie leida del disco no llego a cobrarle nada"


def test_un_CFD_sigue_sin_tener_funding(tmp_path):
    """None y no una serie vacia: el motor distingue "no hay" de "hay y vale
    cero", y un CFD es lo primero."""
    from botiquant.data.store import DataStore
    from botiquant.database.db import Database

    st = DataStore(tmp_path / "datasets", Database(tmp_path / "bq.sqlite"))
    assert st.funding("no-existe") is None


# ------------------------------------------------- que la corrida se pueda guardar

def test_los_ajustes_con_funding_se_pueden_convertir_a_JSON():
    """El bug que tiro diez minutos de computo a la basura.

    `asdict` copia la serie ENTERA —siete mil tasas de un pandas Series— y eso
    no es serializable. El minado de un perpetuo corria las mil quinientas
    candidatas completas y recien moria al archivar la corrida.

    Es el peor momento posible para fallar: todo el trabajo hecho y nada
    guardado. Y no pasa nunca con un CFD, porque ahi la serie es None.
    """
    import json

    idx = pd.date_range("2024-01-01", periods=500, freq="8h", tz="UTC")
    ajustes = BacktestSettings(
        funding=pd.Series([0.0001] * 500, index=idx, name="funding"))
    json.dumps(ajustes.to_dict())          # esto reventaba


def test_queda_anotado_CUANTOS_cobros_tenia():
    """Lo que sirve para entender despues por que una corrida dio distinto.

    Cero cobros y siete mil son dos corridas distintas del mismo instrumento,
    y sin este numero no hay forma de distinguirlas mirando lo archivado.
    """
    idx = pd.date_range("2024-01-01", periods=42, freq="8h", tz="UTC")
    con = BacktestSettings(funding=pd.Series([0.0] * 42, index=idx))
    assert con.to_dict()["funding_cobros"] == 42
    assert BacktestSettings().to_dict()["funding_cobros"] == 0


def test_la_ida_y_vuelta_no_se_rompe():
    """Nunca la hubo: la serie no viaja por JSON, la pone el servidor a partir
    del dataset. Esto lo deja fijado para que nadie la agregue por comodidad."""
    d = BacktestSettings(spread=0.36, swap_anual=5.0).to_dict()
    vuelta = BacktestSettings.from_dict(d)
    assert vuelta.spread == 0.36
    assert vuelta.swap_anual == 5.0
    assert vuelta.funding is None
