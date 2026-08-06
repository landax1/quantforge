"""El QF Score mide repetibilidad, no rentabilidad.

Estos tests fijan el principio: una estrategia espectacular hecha con poca
evidencia tiene que puntuar POR DEBAJO de una modesta pero sólida. Si alguna
vez se toca la fórmula, esto es lo que no puede romperse.
"""

from __future__ import annotations

from quantforge.backtesting.metrics import SCORE_PARTS, qf_score, score_breakdown


def metrics(**over) -> dict[str, float]:
    base = {
        "trades": 400, "profit_factor": 1.4, "sharpe": 1.2, "cagr_pct": 8.0,
        "max_drawdown_pct": 12.0, "expectancy_r": 0.25,
        "months_positive_pct": 62.0, "top_trade_share_pct": 6.0,
        "net_profit_pct": 100.0,
    }
    base.update(over)
    return base


def test_lucky_moonshot_scores_below_a_modest_workhorse():
    """+900% en 24 operaciones, con la mitad del profit en una sola y 55% de
    caída, contra un +25% anual repartido en 500 operaciones."""
    moonshot = metrics(trades=24, cagr_pct=90.0, net_profit_pct=900.0,
                       max_drawdown_pct=55.0, profit_factor=2.4, sharpe=0.7,
                       months_positive_pct=41.0, top_trade_share_pct=50.0,
                       expectancy_r=0.9)
    workhorse = metrics(trades=500, cagr_pct=9.0, net_profit_pct=120.0,
                        max_drawdown_pct=11.0, profit_factor=1.35, sharpe=1.3,
                        months_positive_pct=63.0, top_trade_share_pct=5.0,
                        expectancy_r=0.22)
    assert qf_score(moonshot) < qf_score(workhorse)
    # y la de más rentabilidad es justamente la peor puntuada
    assert moonshot["cagr_pct"] > workhorse["cagr_pct"]


def test_more_evidence_never_hurts():
    few, many = qf_score(metrics(trades=40)), qf_score(metrics(trades=400))
    assert many > few


def test_deeper_drawdown_lowers_the_score():
    assert qf_score(metrics(max_drawdown_pct=40.0)) < qf_score(metrics(max_drawdown_pct=10.0))


def test_profit_concentrated_in_one_trade_is_penalised():
    spread = qf_score(metrics(top_trade_share_pct=5.0))
    lucky = qf_score(metrics(top_trade_share_pct=60.0))
    assert lucky < spread


def test_losing_strategies_collapse_toward_zero():
    """PF por debajo de 0.95 no puntúa, por espectacular que se vea el resto."""
    loser = metrics(profit_factor=0.9, cagr_pct=-3.0, sharpe=1.8)
    assert qf_score(loser) == 0.0


def test_score_is_bounded_and_decomposable():
    perfect = metrics(trades=2000, profit_factor=3.0, sharpe=3.0, cagr_pct=40.0,
                      max_drawdown_pct=5.0, expectancy_r=1.0,
                      months_positive_pct=90.0, top_trade_share_pct=2.0)
    s = qf_score(perfect)
    assert 0.0 <= s <= 100.0
    parts = score_breakdown(perfect)
    assert set(parts) == {k for k, _l, _w in SCORE_PARTS}
    assert all(0.0 <= v <= 1.0 for v in parts.values())
    # el total es exactamente la suma ponderada de sus partes
    assert round(sum(parts[k] * w for k, _l, w in SCORE_PARTS), 2) == s


def test_no_trades_scores_zero():
    assert qf_score(metrics(trades=0)) == 0.0
