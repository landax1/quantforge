"""Mining loop: determinism with a pinned seed, fresh seeds otherwise."""

from __future__ import annotations

import time

import pytest

from quantforge.generator.templates import drivers, filters
from quantforge.mining.miner import _CRIT_BY_KEY, mine

DRIVERS = [d.id for d in drivers()]
FILTERS = [f.id for f in filters()]


def test_mine_reproducible_with_seed(df):
    kw = dict(max_filters=1, min_trades=5, max_candidates=40, keep_top=10, seed=123)
    a = mine(df, DRIVERS, FILTERS, **kw)
    b = mine(df, DRIVERS, FILTERS, **kw)
    assert a["seed"] == b["seed"] == 123
    assert a["tested"] == b["tested"]
    assert [r["id"] for r in a["databank"]] == [r["id"] for r in b["databank"]]
    assert [r["fitness"] for r in a["databank"]] == [r["fitness"] for r in b["databank"]]


def test_mine_generates_fresh_seed(df):
    a = mine(df, DRIVERS, FILTERS, max_candidates=15, min_trades=5, seed=None)
    assert isinstance(a["seed"], int) and 0 <= a["seed"] < 2**31
    assert a["tested"] > 0


def test_mine_databank_ranked_and_capped(df):
    r = mine(df, DRIVERS, FILTERS, max_candidates=80, min_trades=5,
             keep_top=10, seed=7)
    bank = r["databank"]
    assert len(bank) <= 10
    fits = [row["fitness"] for row in bank]
    assert fits == sorted(fits, reverse=True)
    for row in bank:
        assert row["metrics"]["trades"] >= 5
        assert row["spec"]["entry_long"] or row["spec"]["entry_short"]


def test_mine_runs_until_the_databank_is_full(df):
    """Con objetivo, la búsqueda para al llenar el databank — no al agotar un
    número fijo de candidatas."""
    goal = 6
    r = mine(df, DRIVERS, FILTERS, min_trades=5, seed=31,
             target_keep=goal, max_candidates=5000, keep_top=10,
             accept={"min_pf": 1.0})
    assert r["reached_goal"] is True
    assert len(r["databank"]) == goal, "no debe seguir minando de más"
    assert r["target_keep"] == goal
    assert r["hit_cap"] is False
    # y el tope de seguridad no fue lo que la frenó
    assert r["tested"] < 5000


def test_goal_larger_than_keep_top_still_fills(df):
    """Pedir más estrategias que keep_top no debe recortar el databank."""
    r = mine(df, DRIVERS, FILTERS, min_trades=5, seed=33,
             target_keep=12, keep_top=5, max_candidates=5000,
             accept={"min_pf": 1.0})
    assert len(r["databank"]) == 12


def test_impossible_goal_stops_at_the_safety_cap(df):
    """Un objetivo inalcanzable no puede buscar para siempre."""
    r = mine(df, DRIVERS, FILTERS, min_trades=5, seed=37,
             target_keep=50, max_candidates=40, accept={"min_cagr_pct": 999.0})
    assert r["reached_goal"] is False
    assert r["hit_cap"] is True
    assert r["tested"] == 40
    assert r["diagnosis"]["reason"] == "min_cagr_pct"


def test_exit_distance_is_searched_per_candidate(df):
    """El usuario sólo elige riesgo % y relación R:B; la distancia del stop la
    busca el minero, en volatilidad, así vale igual en cualquier mercado."""
    from quantforge.core.models import RiskConfig

    risk = RiskConfig(size_mode="risk_pct", size_value=1, reward_ratio=2.5)
    r = mine(df, DRIVERS, FILTERS, max_candidates=40, min_trades=5, seed=41, risk=risk)
    rows = r["databank"]
    assert rows, "debería aceptar algo con criterios abiertos"

    mults = {row["stop_mult"] for row in rows}
    assert len(mults) > 1, "cada candidata busca su propia distancia de stop"
    for row in rows:
        assert 1.0 <= row["stop_mult"] <= 5.0
        rk = row["spec"]["risk"]
        assert rk["stop_type"] == "atr" and rk["target_type"] == "atr"
        assert rk["stop_value"] == row["stop_mult"]
        # el target sale de la relación pedida, no de un segundo número suelto
        assert rk["target_value"] == pytest.approx(row["stop_mult"] * 2.5)
        assert "×ATR" in row["genes_label"]


def test_reward_ratio_changes_only_the_target(df):
    from quantforge.core.models import RiskConfig

    kw = dict(max_candidates=12, min_trades=5, seed=44)
    a = mine(df, DRIVERS, FILTERS, risk=RiskConfig(reward_ratio=1.0), **kw)["databank"]
    b = mine(df, DRIVERS, FILTERS, risk=RiskConfig(reward_ratio=3.0), **kw)["databank"]
    assert a and b
    assert a[0]["spec"]["risk"]["target_value"] == pytest.approx(a[0]["stop_mult"] * 1.0)
    assert b[0]["spec"]["risk"]["target_value"] == pytest.approx(b[0]["stop_mult"] * 3.0)


def test_diagnosis_never_contradicts_itself(df):
    """Bug real: el mensaje decia 'pediste 65 y lo mejor que aparecio fue 70.67'.

    `best_seen` miraba TODAS las candidatas, asi que podia superar el limite
    cuando la que lo superaba caia por otro filtro. El numero que se muestra
    tiene que salir de las que fallaron ESE criterio, y por definicion queda
    corto."""
    r = mine(df, DRIVERS, FILTERS, max_candidates=80, min_trades=5, seed=91,
             accept={"min_pf": 1.6, "min_win_rate_pct": 65.0})
    if r["passed"]:
        return                      # con este seed si entraron, no aplica
    d = r["diagnosis"]
    key, limit, reached = d["reason"], d["limit"], d["best_reached"]
    kind = _CRIT_BY_KEY[key][1]
    if kind == "min":
        assert reached < limit, (
            f"dice que {key} bloquea pero informa {reached} >= {limit} pedido")
    else:
        assert reached > limit


def test_diagnosis_points_at_the_filter_worth_relaxing(df):
    """Cuando algunas candidatas fallan un solo criterio, el diagnostico tiene
    que decir cual y cuantas entrarian al aflojarlo."""
    r = mine(df, DRIVERS, FILTERS, max_candidates=80, min_trades=5, seed=55,
             accept={"min_pf": 1.05, "min_win_rate_pct": 99.0})
    assert r["passed"] == 0
    d = r["diagnosis"]
    # el win rate imposible es el unico que falla: son todas near-miss
    assert d["reason"] == "min_win_rate_pct"
    assert d["near_miss"].get("min_win_rate_pct", 0) > 0
    assert "cumplían todo salvo" in d["text"]


def test_win_rate_is_an_acceptance_filter(df):
    """El porcentaje de aciertos filtra como cualquier otro criterio."""
    r = mine(df, DRIVERS, FILTERS, max_candidates=60, min_trades=5, seed=13,
             accept={"min_win_rate_pct": 45.0})
    for row in r["databank"]:
        assert row["metrics"]["win_rate_pct"] >= 45.0

    # y cuando es imposible, el diagnóstico lo nombra
    imposible = mine(df, DRIVERS, FILTERS, max_candidates=30, min_trades=5, seed=13,
                     accept={"min_win_rate_pct": 100.0})
    assert imposible["passed"] == 0
    assert imposible["diagnosis"]["reason"] == "min_win_rate_pct"
    assert "aciertos" in imposible["diagnosis"]["text"]


def test_mine_acceptance_filters(df):
    r = mine(df, DRIVERS, FILTERS, max_candidates=60, min_trades=5, seed=7,
             accept={"min_pf": 1.05, "max_dd_pct": 30.0, "min_sharpe": None,
                     "min_net_pct": 0.0})
    assert r["passed"] + r["rejected"] == r["tested"]
    for row in r["databank"]:
        assert row["metrics"]["profit_factor"] >= 1.05
        assert row["metrics"]["max_drawdown_pct"] <= 30.0
        assert row["metrics"]["net_profit_pct"] >= 0.0


def test_empty_databank_explains_itself(df):
    """An impossible target must come back with the reason and how close it got."""
    r = mine(df, DRIVERS, FILTERS, max_candidates=40, min_trades=5, seed=11,
             accept={"min_cagr_pct": 999.0})
    assert r["passed"] == 0
    d = r["diagnosis"]
    assert d["reason"] == "min_cagr_pct"
    assert d["limit"] == 999.0
    assert d["best_reached"] < 999.0, "debe informar el mejor valor alcanzado"
    assert "rendimiento anual" in d["text"]

    # and with a reachable bar there is no complaint to make
    ok = mine(df, DRIVERS, FILTERS, max_candidates=40, min_trades=5, seed=11,
              accept={"min_pf": 0.1})
    assert ok["passed"] > 0
    assert ok["diagnosis"] == {}


def test_unreachable_return_target_suggests_more_risk(df):
    """Asking for more than the risk level can deliver must produce a concrete
    suggestion — the needed risk AND the drawdown it would cost."""
    from quantforge.core.models import RiskConfig

    risk = RiskConfig(stop_type="points", stop_value=2, target_type="points",
                      target_value=4, size_mode="risk_pct", size_value=1)
    r = mine(df, DRIVERS, FILTERS, max_candidates=50, min_trades=5, seed=21,
             risk=risk, accept={"min_cagr_pct": 200.0})
    assert r["passed"] == 0
    sug = r["diagnosis"].get("suggestion")
    assert sug, "un objetivo alcanzable subiendo el riesgo debe sugerirlo"
    assert sug["current"] == 1
    assert sug["needed"] > sug["current"]
    assert sug["dd_projected"] > sug["dd_now"], "debe advertir el costo en drawdown"
    assert "drawdown" in sug["text"]


def test_absurd_target_proposes_a_realistic_one_instead(df):
    """When even huge leverage wouldn't get there, say so and counter-offer."""
    from quantforge.core.models import RiskConfig

    risk = RiskConfig(stop_type="points", stop_value=2, target_type="points",
                      target_value=4, size_mode="risk_pct", size_value=1)
    r = mine(df, DRIVERS, FILTERS, max_candidates=40, min_trades=5, seed=21,
             risk=risk, accept={"min_cagr_pct": 5000.0})
    sug = r["diagnosis"]["suggestion"]
    assert sug["unreachable"] is True
    assert sug["needed"] is None, "no debe recomendar un tamaño suicida"
    assert 0 < sug["realistic_target"] < 5000.0
    assert "realista" in sug["text"]


def test_no_risk_suggestion_when_sizing_is_fixed(df):
    """With fixed lots there is no risk knob to turn — do not invent advice."""
    from quantforge.core.models import RiskConfig

    risk = RiskConfig(stop_type="points", stop_value=2, target_type="points",
                      target_value=4, size_mode="fixed_units", size_value=1)
    r = mine(df, DRIVERS, FILTERS, max_candidates=30, min_trades=5, seed=21,
             risk=risk, accept={"min_cagr_pct": 200.0})
    assert "suggestion" not in r["diagnosis"]


def test_min_trades_rejection_is_reported_separately(df):
    r = mine(df, DRIVERS, FILTERS, max_candidates=20, min_trades=10**6, seed=3)
    assert r["passed"] == 0
    assert r["too_few_trades"] == r["tested"]
    assert r["diagnosis"]["reason"] == "trades"


def test_evolution_mode_breeds_and_stays_reproducible(df):
    kw = dict(max_filters=1, min_trades=5, max_candidates=60, keep_top=20,
              seed=77, method="evolution", population=12)
    a = mine(df, DRIVERS, FILTERS, **kw)
    b = mine(df, DRIVERS, FILTERS, **kw)
    assert a["method"] == "evolution"
    assert a["tested"] > 0
    assert [r["id"] for r in a["databank"]] == [r["id"] for r in b["databank"]]
    # never re-evaluates the same genome twice
    ids = [r["id"] for r in a["databank"]]
    assert len(ids) == len(set(ids))


def test_evolution_and_random_share_the_databank_shape(df):
    common = dict(max_filters=1, min_trades=5, max_candidates=40, seed=5)
    rnd = mine(df, DRIVERS, FILTERS, **common, method="random")
    evo = mine(df, DRIVERS, FILTERS, **common, method="evolution", population=10)
    for r in (rnd, evo):
        assert {"seed", "tested", "passed", "databank", "diagnosis"} <= set(r)
        for row in r["databank"]:
            assert {"name", "blocks", "metrics", "spec", "fitness"} <= set(row)


def test_mine_stop_via_handle(df):
    class FakeHandle:
        cancelled = False
        def progress(self, frac, msg=""):
            pass
        def publish(self, snap):
            # cancel as soon as the first snapshot arrives
            FakeHandle.cancelled = True

    t0 = time.time()
    r = mine(df, DRIVERS, FILTERS, max_candidates=100_000, min_trades=5,
             seed=1, handle=FakeHandle())
    assert r["stopped"] is True
    assert r["tested"] < 100_000
    assert time.time() - t0 < 60
