"""Validación fuera de muestra.

Sin esto, cada número del databank está contaminado: la estrategia fue
elegida mirando esos mismos datos. Sobre un espacio de 51 millones de
combinaciones siempre aparece algo que describe bien el pasado, así que la
única medida honesta es correr la estrategia aceptada sobre un tramo que la
búsqueda nunca vio.
"""

from __future__ import annotations

from quantforge.generator.templates import drivers, filters
from quantforge.mining.miner import mine

DRIVERS = [d.id for d in drivers()]
FILTERS = [f.id for f in filters()]


def test_without_split_nothing_changes(df):
    """oos_pct=0 deja el comportamiento anterior intacto."""
    r = mine(df, DRIVERS, FILTERS, max_candidates=30, min_trades=5, seed=5)
    assert r["split"] is None
    for row in r["databank"]:
        assert "oos" not in row


def test_the_search_never_sees_the_reserved_tail(df):
    r = mine(df, DRIVERS, FILTERS, max_candidates=30, min_trades=5, seed=5,
             oos_pct=30.0)
    s = r["split"]
    assert s is not None
    # los dos tramos son contiguos y no se solapan
    assert s["is_to"] <= s["oos_from"]
    # el reservado es ~30% de las velas
    total = s["is_bars"] + s["oos_bars"]
    assert 0.25 < s["oos_bars"] / total < 0.35


def test_every_accepted_strategy_carries_its_out_of_sample_result(df):
    r = mine(df, DRIVERS, FILTERS, max_candidates=40, min_trades=5, seed=9,
             oos_pct=30.0, accept={"min_pf": 1.0})
    assert r["databank"], "el test necesita al menos una aceptada"
    for row in r["databank"]:
        oos = row["oos"]
        assert {"profit_factor", "net_profit_pct", "trades"} <= set(oos)
        if oos["trades"]:
            # la relación compara afuera contra adentro
            esperado = oos["profit_factor"] / max(row["metrics"]["profit_factor"], 1e-9)
            assert abs(row["oos_ratio"] - round(min(esperado, 9.99), 3)) < 1e-6


def test_in_sample_metrics_ignore_the_reserved_tail(df):
    """Las métricas de adentro tienen que medirse SÓLO sobre el tramo visto.

    Si incluyeran el reservado, la validación no probaría nada: la estrategia
    ya habría "visto" los datos con los que se la juzga. Se comprueba sobre la
    MISMA estrategia, reproduciendo su backtest a mano en los dos tramos.
    """
    from quantforge.backtesting.engine import run_backtest
    from quantforge.core.models import StrategySpec

    r = mine(df, DRIVERS, FILTERS, max_candidates=20, min_trades=5, seed=3,
             oos_pct=40.0, accept={"min_pf": 1.0})
    assert r["databank"], "el test necesita al menos una aceptada"
    row = r["databank"][0]
    spec = StrategySpec.from_dict(row["spec"])

    cut = int(len(df) * 0.6)
    solo_is = run_backtest(df.iloc[:cut], spec).metrics
    entero = run_backtest(df, spec).metrics

    assert row["metrics"]["trades"] == solo_is["trades"], \
        "las métricas de adentro no coinciden con el tramo visto"
    assert row["metrics"]["trades"] != entero["trades"], \
        "las métricas de adentro incluyen el tramo reservado"
    assert row["oos"]["trades"] == run_backtest(df.iloc[cut:], spec).metrics["trades"]


def test_a_tiny_dataset_refuses_to_split(df):
    """Partir 200 velas dejaría los indicadores sin historia: se ignora."""
    r = mine(df.iloc[:300], DRIVERS, FILTERS, max_candidates=10, min_trades=1,
             seed=1, oos_pct=30.0)
    assert r["split"] is None
