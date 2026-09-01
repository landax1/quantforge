"""Los cinco filtros de contexto nuevos, y los indicadores que los sostienen.

Hasta acá había doce disparadores de entrada y sólo cinco filtros, y esa
desproporción se nota: la búsqueda encuentra la señal pero no tiene con qué
descartar los momentos en que esa misma señal falla.

Se comprueba que filtran DE VERDAD —que quitan operaciones— y que los dos
exportadores saben escribirlos. Un filtro que el exportador no sabe traducir
produce un robot que opera distinto del backtest, que es la peor de las
fallas posibles porque se ve idéntica a un éxito.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.backtesting.engine import run_backtest
from botiquant.core.models import BacktestSettings, RiskConfig
from botiquant.generator.generator import Genome, build_spec
from botiquant.generator.templates import TEMPLATES, filters
from botiquant.indicators.base import IndicatorCache
from botiquant.reports.mql5 import export_mql5
from botiquant.reports.pine import export_pine

NUEVOS = ["breakout_ready_filter", "pullback_filter", "strong_close_filter",
          "expansion_filter", "skip_weekday_filter"]


@pytest.fixture(scope="module")
def df():
    idx = pd.date_range("2022-01-03", periods=9000, freq="h")
    rng = np.random.default_rng(5)
    close = 1000 + np.cumsum(rng.normal(0.02, 1.0, len(idx)))
    alto = close + np.abs(rng.normal(0, 1.2, len(idx)))
    bajo = close - np.abs(rng.normal(0, 1.2, len(idx)))
    return pd.DataFrame({"open": close, "high": alto, "low": bajo,
                         "close": close, "volume": 1000.0}, index=idx)


def test_ahora_hay_doce_filtros():
    """Diez de contexto y precio, más los dos de funding.

    El número está clavado a propósito: cada filtro nuevo multiplica el espacio
    de búsqueda —los dos de funding lo llevaron de 245 a 419 millones— y eso no
    puede pasar sin que alguien lo mire.
    """
    ids = {f.id for f in filters()}
    assert len(ids) == 12
    assert set(NUEVOS) <= ids
    assert {"funding_alto_filter", "funding_bajo_filter"} <= ids


@pytest.mark.parametrize("fid", NUEVOS)
def test_cada_filtro_quita_operaciones(df, fid):
    riesgo = RiskConfig(size_mode="risk_pct", size_value=1.0, reward_ratio=2.0)
    ajustes = BacktestSettings()
    cache = IndicatorCache(df)

    def correr(filtros):
        g = Genome(driver="ema_cross", filters=tuple(filtros),
                   genes={"ema_cross": {"fast": 20, "slow": 80},
                          **{f: {x.name: x.default for x in TEMPLATES[f].genes}
                             for f in filtros}},
                   stop_mult=2.0)
        return run_backtest(df, build_spec(g, "both", riesgo), ajustes, cache=cache)

    sin = correr([])
    con = correr([fid])
    assert sin.metrics["trades"] > 0
    # un filtro que no descarta nada no es un filtro
    assert con.metrics["trades"] < sin.metrics["trades"]


@pytest.mark.parametrize("fid", NUEVOS)
def test_los_dos_exportadores_saben_escribirlo(fid):
    riesgo = RiskConfig(size_mode="risk_pct", size_value=1.0, reward_ratio=2.0)
    g = Genome(driver="ema_cross", filters=(fid,),
               genes={"ema_cross": {"fast": 20, "slow": 80},
                      fid: {x.name: x.default for x in TEMPLATES[fid].genes}},
               stop_mult=2.0)
    spec = build_spec(g, "both", riesgo)
    mq5 = export_mql5(spec)
    pine = export_pine(spec)
    assert "NO SOPORTADO" not in mq5
    assert "NO SOPORTADO" not in pine


def test_el_cierre_dentro_de_la_vela_va_de_0_a_100(df):
    v = IndicatorCache(df).get("ClosePosition", {})["value"]
    assert np.nanmin(v) >= 0.0 and np.nanmax(v) <= 100.0


def test_el_dia_de_la_semana_numera_el_lunes_como_1(df):
    v = IndicatorCache(df).get("DayOfWeek", {})["value"]
    lunes = df.index.dayofweek == 0
    assert set(np.unique(v[lunes])) == {1.0}


def test_las_distancias_excluyen_la_vela_evaluada(df):
    """Si el máximo del rango incluyera la vela actual, "el cierre está a
    menos de X del máximo" sería casi siempre cierto y el filtro no filtraría
    nada — es el mismo error que ya rompió el canal de Donchian exportado."""
    d = IndicatorCache(df).get("DistATR", {"period": 20})
    negativas = np.nansum(d["to_high"] < -1e-9)
    # con el máximo excluido, el cierre PUEDE estar por encima: eso es una
    # ruptura y tiene que poder pasar
    assert negativas > 0


def test_saltear_un_dia_apaga_la_senal_ese_dia(df):
    """Se comprueba sobre la SEÑAL y no sobre la operación: el fill ocurre en
    la apertura de la vela siguiente, así que una señal del domingo se llena
    el lunes y contarla como "operó un lunes" sería un falso positivo."""
    from botiquant.strategies.rules import EvalContext, eval_conditions
    riesgo = RiskConfig(size_mode="risk_pct", size_value=1.0, reward_ratio=2.0)
    g = Genome(driver="ema_cross", filters=("skip_weekday_filter",),
               genes={"ema_cross": {"fast": 20, "slow": 80},
                      "skip_weekday_filter": {"day": 1}},   # 1 = lunes
               stop_mult=2.0)
    spec = build_spec(g, "both", riesgo)
    ctx = EvalContext(df)
    senal = eval_conditions(spec.entry_long, ctx)
    assert senal.any(), "sin señales no hay nada que comprobar"
    lunes = np.asarray(df.index.dayofweek) == 0
    assert not (senal & lunes).any()


def test_los_operadores_de_igualdad_toleran_el_ruido_de_los_float():
    """DayOfWeek viaja como float. Con igualdad exacta, un 3.0000000000000004
    salido de cualquier cuenta intermedia haría que la condición no se
    cumpliera nunca sin que nada lo delate."""
    from botiquant.core.models import Condition, Operand
    from botiquant.strategies.rules import EvalContext, eval_condition
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    marco = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                          "close": 1.0 + 3e-16, "volume": 1.0}, index=idx)
    ctx = EvalContext(marco)
    c = Condition(left=Operand(type="price", field_name="close"), op="==",
                  right=Operand(type="const", value=1.0))
    assert eval_condition(c, ctx).all()


# ============== que ningun criterio se caiga entre la pantalla y el minero

def test_TODOS_los_criterios_existen_en_la_pantalla():
    """UN FILTRO QUE SE PIDE Y NO SE APLICA ES EL PEOR ERROR DE ESTA APP.

    Son tres eslabones —la tabla de criterios, el mapa de la pantalla y el
    endpoint— y basta que uno se olvide de un criterio para que el número
    viaje y nadie lo mire. No hay error: hay una búsqueda que no filtra por lo
    que se le pidió, y eso sólo se descubre leyendo los resultados con
    desconfianza.

    El endpoint ya no puede olvidarse: arma el diccionario recorriendo
    `_CRIT_BY_KEY`. El que sí puede quedarse atrás es el mapa del navegador,
    que es de otro archivo y de otro lenguaje. Esto lo ata.
    """
    from pathlib import Path

    from botiquant.mining.miner import _CRIT_BY_KEY

    app_js = (Path(__file__).resolve().parents[1] / "ui" / "app.js"
              ).read_text(encoding="utf-8")
    mapa = app_js[app_js.index("const CRIT_FIELD = {"):]
    mapa = mapa[:mapa.index("};")]

    faltan = sorted(k for k in _CRIT_BY_KEY if f'"{k}"' not in mapa)
    assert not faltan, (
        f"criterios que el minero conoce y la pantalla no puede mandar: "
        f"{faltan}. Se agregaron a `_CRITERIA` y quedaron sin conectar.")


def test_la_pantalla_no_inventa_criterios_que_el_minero_no_conoce():
    """La contracara, y desde hoy es ruidosa: `mine` rechaza una clave que no
    conoce. Antes la ignoraba, que es como se mina creyendo que se filtra."""
    from pathlib import Path

    from botiquant.mining.miner import _CRIT_BY_KEY

    app_js = (Path(__file__).resolve().parents[1] / "ui" / "app.js"
              ).read_text(encoding="utf-8")
    mapa = app_js[app_js.index("const CRIT_FIELD = {"):]
    mapa = mapa[:mapa.index("};")]

    import re as _re
    manda = set(_re.findall(r':\s*"([a-z_]+)"', mapa))
    sobran = sorted(manda - set(_CRIT_BY_KEY))
    assert not sobran, f"la pantalla manda criterios inexistentes: {sobran}"
