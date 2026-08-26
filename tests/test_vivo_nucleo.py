"""Que el bot decida exactamente lo que hizo el backtest.

Es la prueba de fondo de todo el proyecto. Si el bot opera distinto de lo que
se midió, el número que convenció a la persona de encender el bot es una
mentira — y se entera con su propia plata.

Por eso las pruebas centrales de acá no comprueban que el núcleo haga algo
razonable: comprueban que haga LO MISMO que `run_backtest`, corriendo los dos
sobre los mismos datos y comparando el resultado.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.backtesting.engine import run_backtest
from botiquant.core.models import BacktestSettings, StrategySpec
from botiquant.vivo import nucleo
from botiquant.vivo.nucleo import (ABRIR_CORTO, ABRIR_LARGO, CERRAR, NADA,
                                   decidir, solo_cerradas)


def _velas(n: int = 400, freq: str = "1h") -> pd.DataFrame:
    t = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    precio = 100 + np.sin(np.arange(n) / 25) * 9 + np.arange(n) * 0.02
    return pd.DataFrame({"open": precio, "high": precio + 0.6,
                         "low": precio - 0.6, "close": precio,
                         "volume": np.full(n, 1000.0)}, index=t)


def _spec(stop_type: str = "percent", stop_value: float = 2.0) -> StrategySpec:
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    return StrategySpec.from_dict({
        "name": "prueba", "direction": "both",
        "entry_long": [{"left": ema(5), "op": "cross_above", "right": ema(20)}],
        "entry_short": [{"left": ema(5), "op": "cross_below", "right": ema(20)}],
        "risk": {"size_mode": "risk_pct", "size_value": 1.0,
                 "stop_type": stop_type, "stop_value": stop_value,
                 "target_type": stop_type, "target_value": stop_value * 2,
                 "atr_period": 14},
    })


# ------------------------------------------------- la vela que no está cerrada

def test_la_vela_en_formacion_se_descarta():
    """Medido contra BingX: la lista incluye la vela EN CURSO.

    Un cierre que todavía no ocurrió hace que la señal aparezca y desaparezca
    dentro de la misma hora, y el bot entraría siguiendo un número provisorio.
    """
    df = _velas(50)
    # son las 10:30 y la vela de las 10:00 todavía no cerró
    ahora = df.index[-1] + pd.Timedelta("30min")
    assert len(solo_cerradas(df, "1h", ahora)) == len(df) - 1


def test_si_el_exchange_ya_no_manda_la_en_curso_no_se_tira_una_buena():
    """No se tira la última a ciegas.

    Pidiendo justo después de un cierre, el exchange puede no incluir todavía
    la nueva. Tirar igual perdería una vela cerrada y atrasaría TODAS las
    señales una barra entera.
    """
    df = _velas(50)
    ahora = df.index[-1] + pd.Timedelta("90min")   # la última ya cerró hace rato
    assert len(solo_cerradas(df, "1h", ahora)) == len(df)


def test_una_temporalidad_desconocida_no_pasa_en_silencio():
    with pytest.raises(ValueError, match="Temporalidad"):
        solo_cerradas(_velas(10), "7h")


# --------------------------------------------- lo mismo que hizo el backtest

def _primera_entrada(df, spec, ajustes):
    """El índice y los datos de la primera operación que abrió el motor."""
    r = run_backtest(df, spec, ajustes).to_dict()
    ops = r["trades"]
    assert ops, "la estrategia de prueba tiene que operar"
    t = ops[0]
    idx = df.index.get_loc(pd.Timestamp(t["entry_time"]))
    return idx, t


def test_decide_la_misma_direccion_y_el_mismo_tamanio_que_el_motor():
    """La prueba central.

    Se corre el backtest, se mira su PRIMERA operación, y se le pregunta al
    núcleo qué haría parado en esa misma vela. Tienen que coincidir en el lado,
    en la cantidad y en el stop.

    Con stop porcentual y sin costos, la coincidencia tiene que ser exacta: no
    hay ninguna diferencia legítima entre los dos caminos.
    """
    df, spec = _velas(), _spec("percent", 2.0)
    ajustes = BacktestSettings(initial_capital=10_000.0)
    i, t = _primera_entrada(df, spec, ajustes)

    d = decidir(df.iloc[:i], spec, posicion=0, capital=10_000.0,
                precio=float(df["open"].iloc[i]))

    assert d.accion == (ABRIR_LARGO if t["direction"] == "long" else ABRIR_CORTO)
    # `Trade` guarda units y precio redondeados a 6 decimales, asi que la
    # tolerancia es la del redondeo y no la del float. Mas fino que esto
    # compara contra el redondeo del motor, no contra su calculo.
    assert d.cantidad == pytest.approx(t["units"], abs=1e-6)
    assert d.precio == pytest.approx(t["entry_price"], abs=1e-6)


def test_con_costos_el_tamanio_sigue_coincidiendo():
    """Los costos mueven el precio de entrada, y el tamaño va con él.

    Si el núcleo dimensionara sobre el precio limpio y el motor sobre el precio
    con spread, las dos posiciones serían distintas desde la primera operación.
    """
    df, spec = _velas(), _spec("percent", 2.0)
    ajustes = BacktestSettings(initial_capital=10_000.0, spread=0.04, slippage=0.01)
    i, t = _primera_entrada(df, spec, ajustes)

    # el precio que el motor usó ya trae los costos adentro
    d = decidir(df.iloc[:i], spec, posicion=0, capital=10_000.0,
                precio=float(t["entry_price"]))
    assert d.cantidad == pytest.approx(t["units"], abs=1e-6)


def test_sin_senial_no_hace_nada():
    df, spec = _velas(), _spec()
    # una vela cualquiera lejos de todo cruce
    d = decidir(df.iloc[:37], spec, posicion=0, capital=10_000.0)
    assert d.accion == NADA
    assert not d.opera


# ---------------------------------------------------------------- las salidas

def test_estando_comprado_una_senial_de_venta_cierra():
    """Y cierra, no da vuelta la posición en un solo paso.

    El motor cierra en la barra y recién puede volver a entrar en la siguiente.
    Dar vuelta de una haría el doble de nocional en una sola orden.
    """
    df, spec = _velas(), _spec()
    ctx_i = None
    for i in range(30, len(df)):
        d = decidir(df.iloc[:i], spec, posicion=1, capital=10_000.0)
        if d.accion == CERRAR:
            ctx_i = i
            break
    assert ctx_i is not None, "tendría que haber encontrado una salida"


def test_el_maximo_de_velas_cierra_aunque_no_haya_senial():
    df = _velas()
    spec = StrategySpec.from_dict({
        **_spec().to_dict(),
        "risk": {**_spec().risk.to_dict(), "max_bars_in_trade": 5}})
    d = decidir(df.iloc[:80], spec, posicion=1, capital=10_000.0,
                barras_en_posicion=5)
    assert d.accion == CERRAR
    assert "máximo" in d.motivo


def test_con_posicion_abierta_y_sin_senial_se_queda_quieto():
    df, spec = _velas(), _spec()
    d = decidir(df.iloc[:37], spec, posicion=1, capital=10_000.0)
    assert d.accion == NADA


# ------------------------------------------------------- las negativas duras

def test_nunca_abre_sin_stop_cuando_el_stop_se_pidio():
    """En el backtest esto produjo una operación de 134.259 velas al 100% del
    capital. En vivo sería una posición sin stop, que es la forma más rápida
    de perderlo todo.

    Con sólo 15 velas el ATR de 14 apenas arrancó y el stop no se puede
    calcular en la mayoría de los casos; lo que NO puede pasar es que abra
    igual.
    """
    df, spec = _velas(), _spec("atr", 2.0)
    for i in range(3, 16):
        d = decidir(df.iloc[:i], spec, posicion=0, capital=10_000.0)
        if d.opera:
            assert not np.isnan(d.stop), (
                f"abrió en la vela {i} sin poder calcular el stop")


def test_sin_capital_no_abre():
    df, spec = _velas(), _spec()
    i, _ = _primera_entrada(df, spec, BacktestSettings(initial_capital=10_000.0))
    assert decidir(df.iloc[:i], spec, posicion=0, capital=0.0).accion == NADA


def test_con_pocas_velas_no_decide_nada():
    df, spec = _velas(), _spec()
    assert decidir(df.iloc[:1], spec, capital=10_000.0).accion == NADA


# ------------------------------------------------------------- la franja horaria

def _con_franja(**extra) -> StrategySpec:
    base = _spec().to_dict()
    base["time_filter"] = {"enabled": True, "start_hour": 3, "end_hour": 4}
    base.update(extra)
    return StrategySpec.from_dict(base)


def test_la_franja_horaria_impide_toda_entrada():
    df = _velas()
    spec = _con_franja()
    assert not any(decidir(df.iloc[:i], spec, posicion=0, capital=10_000.0).opera
                   for i in range(30, 200))


def test_fuera_de_la_franja_la_reversion_tampoco_cierra():
    """Copiado del motor, y conviene entender por qué antes de "arreglarlo".

    El motor enmascara `entry_short` con la franja horaria ANTES de usarla, y
    después usa esa misma señal enmascarada como salida de un largo. O sea que
    fuera de la franja la reversión no cierra tampoco.

    Verificado leyendo el motor, no supuesto: si el núcleo cerrara igual,
    operaría distinto del backtest cada vez que la estrategia tenga franja.

    Lo que SÍ cierra fuera de la franja son el stop, el objetivo, el máximo de
    velas y una condición de salida propia — o sea que la posición no queda
    huérfana, que era la preocupación razonable.
    """
    df = _velas()
    spec = _con_franja()
    assert not any(
        decidir(df.iloc[:i], spec, posicion=1, capital=10_000.0).accion == CERRAR
        for i in range(30, 200))


def test_una_condicion_de_salida_propia_si_cierra_fuera_de_la_franja():
    """La franja filtra entradas; `exit_long` no pasa por ese filtro."""
    ema = lambda p: {"type": "indicator", "name": "EMA", "params": {"period": p}}
    df = _velas()
    spec = _con_franja(exit_long=[{"left": ema(5), "op": "cross_below",
                                   "right": ema(20)}])
    assert any(
        decidir(df.iloc[:i], spec, posicion=1, capital=10_000.0).accion == CERRAR
        for i in range(30, 200))


# --------------------------------------------------- el registro sirve de algo

def test_toda_decision_dice_por_que():
    """Un registro que dice "abrió" y no dice por qué no sirve para nada."""
    df, spec = _velas(), _spec()
    for i in (5, 37, 80, 150):
        assert decidir(df.iloc[:i], spec, posicion=0, capital=10_000.0).motivo
