"""Franjas horarias: el motor ya sabía filtrar por hora, y ahora el minero lo usa.

Lo que se comprueba acá es la cadena entera, porque cada eslabón roto se ve
igual que un éxito: si el genoma no lleva la franja, todas las candidatas
operan 24 horas y los resultados parecen normales; si el exportador no la
lleva, el robot opera 24 horas en MetaTrader y la diferencia aparece recién
con dinero real.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.core import sesiones
from botiquant.core.models import BacktestSettings, RiskConfig
from botiquant.backtesting.engine import run_backtest
from botiquant.generator.generator import Genome, build_spec, random_genome
from botiquant.genetic.evolution import _crossover, _mutate
from botiquant.mining.miner import mine
from botiquant.reports.mql5 import export_mql5
from botiquant.reports.pine import export_pine


@pytest.fixture(scope="module")
def horario_df():
    """Dos años de velas horarias con una tendencia SÓLO entre las 13 y las 21.

    Fuera de esa franja el precio hace ruido puro. Una estrategia de ruptura
    tiene que ganar dentro y perder o no operar fuera: si el filtro horario no
    se aplicara, los dos casos darían el mismo número.
    """
    idx = pd.date_range("2022-01-03", periods=24 * 500, freq="h")
    rng = np.random.default_rng(7)
    paso = np.where((idx.hour >= 13) & (idx.hour < 21), 0.9, 0.0)
    ruido = rng.normal(0, 1.0, len(idx))
    close = 1000 + np.cumsum(paso + ruido)
    df = pd.DataFrame({
        "open": close, "high": close + 1.5, "low": close - 1.5,
        "close": close, "volume": 1000.0,
    }, index=idx)
    return df


def _genoma(sesion):
    return Genome(driver="donchian_break", filters=(),
                  genes={"donchian_break": {"period": 20}},
                  stop_mult=2.0, session=sesion)


def test_la_franja_cambia_el_resultado(horario_df):
    riesgo = RiskConfig(size_mode="risk_pct", size_value=1.0, reward_ratio=2.0)
    ajustes = BacktestSettings(initial_capital=10_000.0)

    dentro = run_backtest(horario_df, build_spec(_genoma("nueva_york"), "long", riesgo), ajustes)
    fuera = run_backtest(horario_df, build_spec(_genoma("asia"), "long", riesgo), ajustes)

    # la tendencia vive en la sesión de Nueva York; en la asiática hay ruido
    assert dentro.metrics["trades"] > 0
    assert dentro.metrics["net_profit_pct"] > fuera.metrics["net_profit_pct"]


def test_toda_operacion_cae_dentro_de_la_franja(horario_df):
    riesgo = RiskConfig(size_mode="risk_pct", size_value=1.0, reward_ratio=2.0)
    res = run_backtest(horario_df, build_spec(_genoma("nueva_york"), "long", riesgo),
                       BacktestSettings())
    horas = {pd.Timestamp(t.entry_time).hour for t in res.trades}
    assert horas, "sin operaciones no hay nada que comprobar"
    # el fill es en la apertura de la vela SIGUIENTE a la señal, así que la
    # entrada puede caer una hora después del borde
    assert min(horas) >= 13 and max(horas) <= 21


def test_sin_restriccion_el_filtro_queda_apagado():
    """Y no en 0-24 de lunes a viernes: eso borraría los fines de semana de
    las criptomonedas sin que nadie lo haya pedido."""
    tf = sesiones.filtro(sesiones.SIN_RESTRICCION)
    assert tf.enabled is False


def test_normalizar_nunca_deja_al_minero_sin_opciones():
    assert sesiones.normalizar([]) == ["todo"]
    assert sesiones.normalizar(None) == ["todo"]
    assert sesiones.normalizar(["no_existe"]) == ["todo"]
    assert sesiones.normalizar(["londres", "londres", "asia"]) == ["londres", "asia"]


def test_la_franja_entra_en_la_identidad_del_genoma():
    """Dos candidatas idénticas salvo el horario son candidatas distintas. Sin
    esto, la búsqueda descartaría la segunda por duplicada."""
    a, b = _genoma("londres"), _genoma("nueva_york")
    assert a.key() != b.key()


def test_una_sola_franja_no_es_un_gen(horario_df):
    rng = np.random.default_rng(3)
    g = [random_genome(["donchian_break"], [], 0, rng, sessions=["londres"])
         for _ in range(20)]
    assert {x.session for x in g} == {"londres"}


def test_con_varias_la_busqueda_elige():
    rng = np.random.default_rng(3)
    g = [random_genome(["donchian_break"], [], 0, rng,
                       sessions=["londres", "nueva_york", "asia"])
         for _ in range(60)]
    assert len({x.session for x in g}) > 1


def test_la_cria_hereda_una_franja_de_sus_padres():
    rng = np.random.default_rng(1)
    hijo = _crossover(_genoma("londres"), _genoma("asia"), rng)
    assert hijo.session in ("londres", "asia")


def test_la_mutacion_solo_mueve_el_horario_si_hay_de_donde_elegir():
    rng = np.random.default_rng(1)
    quieto = _mutate(_genoma("londres"), ["donchian_break"], [], 0, rng, 1.0,
                     sessions=["londres"])
    assert quieto.session == "londres"


def test_el_minado_devuelve_la_franja_de_cada_estrategia(horario_df):
    out = mine(horario_df, ["donchian_break"], [],
               max_filters=0, direction="long",
               risk=RiskConfig(size_mode="risk_pct", size_value=1.0, reward_ratio=2.0),
               min_trades=5, max_candidates=25,
               sessions=["nueva_york", "londres"])
    assert out["sessions"] == ["nueva_york", "londres"]
    for fila in out["databank"]:
        assert fila["session"] in ("nueva_york", "londres")
        assert fila["session_hours"]


def test_el_robot_exportado_lleva_la_franja():
    """El eslabón que más caro sale romper: sin esto el EA opera las 24 horas
    en MetaTrader y no es la misma estrategia que se minó."""
    riesgo = RiskConfig(size_mode="risk_pct", size_value=1.0, reward_ratio=2.0)
    spec = build_spec(_genoma("nueva_york"), "long", riesgo)

    mq5 = export_mql5(spec)
    assert "InpUseSession  = true" in mq5
    assert "InpStartHourUTC = 13" in mq5
    assert "InpEndHourUTC   = 21" in mq5
    assert "bool InSession()" in mq5
    assert "if(!InSession())" in mq5

    pine = export_pine(spec)
    assert "1300-2100" in pine
    assert 'time(timeframe.period, InpSession, "UTC")' in pine


def test_sin_franja_el_robot_no_filtra_pero_compila():
    riesgo = RiskConfig(size_mode="risk_pct", size_value=1.0, reward_ratio=2.0)
    spec = build_spec(_genoma(sesiones.SIN_RESTRICCION), "long", riesgo)
    mq5 = export_mql5(spec)
    # la función tiene que existir igual: OnTick la llama siempre
    assert "bool InSession()" in mq5
    assert "InpUseSession" in mq5 and "false" in mq5.split("InpUseSession")[1][:40]
