"""Continuous random strategy mining with a live databank.

The SQX-style experience: sample random genomes (structure AND gene values),
backtest each one, and keep a ranked databank that the UI renders while the
search runs. The seed defaults to a fresh random value on every run — shown
and returned so any run can be reproduced exactly — instead of a fixed seed
that would make every run return identical results.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

import numpy as np
import pandas as pd

from quantforge.backtesting.engine import run_backtest
from quantforge.backtesting.metrics import fitness, qf_score, score_breakdown
from quantforge.core.jobs import JobHandle
from quantforge.core.models import BacktestSettings, RiskConfig
from quantforge.genetic.evolution import _crossover, _mutate
from quantforge.generator.generator import Genome, build_spec, random_genome
from quantforge.generator.templates import TEMPLATES
from quantforge.indicators.base import IndicatorCache

_ROW_METRICS = ("net_profit_pct", "cagr_pct", "profit_factor", "max_drawdown_pct",
                "win_rate_pct", "sharpe", "trades", "expectancy_r",
                "exposure_pct", "cagr_exposed_pct", "years",
                "avg_win", "avg_loss", "avg_trade",
                "months_positive_pct", "months_total", "worst_month_pct",
                "top_trade_share_pct")

# after this many consecutive duplicate genomes the space is considered mined out
_EXHAUSTED_AFTER = 300


def _gene_summary(genome: Genome) -> str:
    parts = []
    for t_id in (genome.driver, *genome.filters):
        vals = genome.genes.get(t_id) or {}
        if vals:
            parts.append(",".join(f"{k}={v:g}" for k, v in sorted(vals.items())))
    if genome.stop_mult is not None:
        parts.append(f"SL={genome.stop_mult:g}×ATR")
    if genome.trail_mult:
        parts.append(f"trail={genome.trail_mult:g}×ATR")
    if genome.max_bars:
        parts.append(f"máx {genome.max_bars} velas")
    return " · ".join(parts)


#: points kept for the inline equity sparkline shown on each databank row
_SPARK_POINTS = 48


def _spark(equity: np.ndarray) -> list[float]:
    """Heavily downsampled equity curve — enough to read its shape at a glance."""
    n = len(equity)
    if n == 0:
        return []
    idx = np.linspace(0, n - 1, min(n, _SPARK_POINTS)).astype(int)
    return [round(float(equity[i]), 2) for i in idx]


def _row(genome: Genome, spec, m: dict[str, float], score: float,
         serial: int, equity: np.ndarray | None = None) -> dict[str, Any]:
    return {
        "id": genome.key(),
        "name": f"S-{serial:03d}",
        "blocks": spec.name,
        "genes_label": _gene_summary(genome),
        "spark": _spark(equity) if equity is not None else [],
        "driver": genome.driver,
        "filters": list(genome.filters),
        "genes": genome.genes,
        "stop_mult": genome.stop_mult,
        "trail_mult": genome.trail_mult,
        "max_bars": genome.max_bars,
        "metrics": {k: m[k] for k in _ROW_METRICS},
        "fitness": round(float(score), 4),
        # el score y su desglose viajan siempre, aunque se esté ordenando por
        # otro criterio: es lo que el usuario mira para decidir
        "score": qf_score(m),
        "score_parts": {k: round(v, 3) for k, v in score_breakdown(m).items()},
        "spec": spec.to_dict(),
    }


#: acceptance criterion -> (metric, comparison, human label)
_CRITERIA: tuple[tuple[str, str, str, str], ...] = (
    ("min_pf", "profit_factor", "min", "profit factor"),
    ("min_win_rate_pct", "win_rate_pct", "min", "porcentaje de aciertos"),
    ("min_sharpe", "sharpe", "min", "Sharpe"),
    ("max_dd_pct", "max_drawdown_pct", "max", "max drawdown"),
    ("min_net_pct", "net_profit_pct", "min", "ganancia total"),
    ("min_cagr_pct", "cagr_pct", "min", "rendimiento anual"),
    ("min_exposure_pct", "exposure_pct", "min", "tiempo en mercado"),
)

_CRIT_BY_KEY = {k: (metric, kind, label) for k, metric, kind, label in _CRITERIA}


def _failed_criteria(m: dict[str, float], accept: dict[str, float | None]) -> list[str]:
    """Which acceptance criteria this candidate misses (empty = accepted)."""
    missed = []
    for key, metric, kind, _label in _CRITERIA:
        limit = accept.get(key)
        if limit is None:
            continue
        if kind == "min" and m[metric] < limit:
            missed.append(key)
        elif kind == "max" and m[metric] > limit:
            missed.append(key)
    return missed


def _passes(m: dict[str, float], accept: dict[str, float | None]) -> bool:
    """Databank acceptance: None disables an individual criterion."""
    return not _failed_criteria(m, accept)


def mine(
    df: pd.DataFrame,
    drivers: list[str],
    filters: list[str],
    *,
    max_filters: int = 2,
    direction: str = "both",
    risk: RiskConfig | None = None,
    settings: BacktestSettings | None = None,
    fitness_mode: str = "composite",
    min_trades: int = 30,
    accept: dict[str, float | None] | None = None,
    max_candidates: int = 2000,
    target_keep: int | None = None,
    keep_top: int = 100,
    seed: int | None = None,
    method: str = "random",
    population: int = 40,
    oos_pct: float = 0.0,
    handle: JobHandle | None = None,
) -> dict[str, Any]:
    """Mining loop over the strategy space.

    ``method="random"`` samples genomes independently — broad, unbiased, and
    the honest baseline. ``method="evolution"`` keeps a population and breeds
    the best performers each generation, which converges on strong regions of
    the space much faster but explores less widely.

    Two ways to say when to stop. With ``target_keep`` the search runs until
    that many strategies have been ACCEPTED into the databank — the natural
    request ("quiero 50 que cumplan"), since how many candidates that takes is
    unknowable up front. ``max_candidates`` then acts purely as a safety cap so
    an impossible set of criteria cannot search forever. Without
    ``target_keep`` the old behaviour stands: test exactly ``max_candidates``.
    """
    if not drivers:
        raise ValueError("At least one driver template is required")

    # ---------------------------------------------------------- in / out of sample
    # Con oos_pct > 0 la búsqueda sólo ve el tramo inicial y el final queda
    # reservado. Cada candidata aceptada se vuelve a correr ahí, sobre datos que
    # no participaron de la selección. Es la única medida del databank que no
    # está contaminada por haber elegido la estrategia mirando esos mismos datos:
    # buscar sobre 51 millones de combinaciones siempre encuentra algo que se ve
    # bien en el pasado, y esta columna es la que lo delata.
    df_full = df
    df_oos = None
    if oos_pct and 0.0 < oos_pct < 90.0:
        cut = int(len(df) * (1.0 - oos_pct / 100.0))
        if cut > 200 and len(df) - cut > 200:
            df, df_oos = df_full.iloc[:cut], df_full.iloc[cut:]
    if target_keep is not None:
        target_keep = max(int(target_keep), 1)
        # the bank must be able to hold the goal, otherwise trimming to
        # keep_top would silently cap the search below what was asked for
        keep_top = max(keep_top, target_keep)
    if seed is None:
        seed = secrets.randbelow(2**31)
    rng = np.random.default_rng(seed)
    cache = IndicatorCache(df)
    # una sola caché para el tramo reservado: se reutiliza en cada validación
    cache_oos = IndicatorCache(df_oos) if df_oos is not None else None
    settings = settings or BacktestSettings()

    accept = accept or {}
    seen: set[str] = set()
    bank: list[dict[str, Any]] = []
    best_history: list[float] = []
    tested = 0
    passed = 0
    dupes = 0
    too_few_trades = 0
    blocked_by: dict[str, int] = {}
    # best value reached per criterion, so an empty databank can explain itself
    best_seen: dict[str, float] = {}
    # Candidatas que fallaron EXACTAMENTE un criterio, y cuál. Es el dato que
    # de verdad sirve: dice qué filtro aflojar para que entren estrategias.
    near_miss: dict[str, int] = {}
    # Mejor valor alcanzado ENTRE LAS QUE FALLARON cada criterio. `best_seen`
    # mira todas las candidatas, así que puede superar el límite pedido cuando
    # la que lo superaba cayó por otro filtro — y entonces el mensaje decía
    # "pediste 65 y lo mejor fue 70.67", que se lee como una contradicción.
    fail_best: dict[str, float] = {}
    t0 = time.time()

    # drawdown of the highest-CAGR candidate, to project what raising the risk
    # per trade would cost — CAGR and drawdown both scale ~linearly with it
    top_cagr: dict[str, float] = {}

    def _validate_oos(spec) -> dict[str, Any]:
        """Corre la estrategia aceptada sobre el tramo reservado.

        ``oos_ratio`` es lo que hay que mirar: profit factor de afuera dividido
        el de adentro. Cerca de 1 significa que la ventaja se sostuvo; cerca de
        0 que la estrategia describía el pasado y nada más. Se calcula sobre el
        profit factor y no sobre la ganancia porque no depende de cuántos años
        tenga cada tramo.
        """
        res_oos = run_backtest(df_oos, spec, settings, cache=cache_oos)
        mo = res_oos.metrics
        pf_is = None
        return {
            "oos": {
                "profit_factor": mo["profit_factor"],
                "net_profit_pct": mo["net_profit_pct"],
                "cagr_pct": mo["cagr_pct"],
                "max_drawdown_pct": mo["max_drawdown_pct"],
                "win_rate_pct": mo["win_rate_pct"],
                "trades": mo["trades"],
            },
        }

    def _oos_ratio(row: dict[str, Any]) -> float | None:
        """Cuánto sobrevive la ventaja fuera de muestra, de 0 a 1+."""
        oos = row.get("oos")
        if not oos or not oos["trades"]:
            return None
        pf_in = max(row["metrics"]["profit_factor"], 1e-9)
        return round(min(oos["profit_factor"] / pf_in, 9.99), 3)

    def _note_best(m: dict[str, float]) -> None:
        for key, metric, kind, _label in _CRITERIA:
            v = m[metric]
            cur = best_seen.get(key)
            if cur is None:
                best_seen[key] = v
            elif kind == "min":
                best_seen[key] = max(cur, v)
            else:
                best_seen[key] = min(cur, v)
        if not top_cagr or m["cagr_pct"] > top_cagr["cagr_pct"]:
            top_cagr.update({"cagr_pct": m["cagr_pct"],
                             "max_drawdown_pct": m["max_drawdown_pct"]})

    def _note_fail(key: str, m: dict[str, float]) -> None:
        """Lo más cerca que estuvo de este criterio algo que efectivamente falló."""
        metric, kind, _label = _CRIT_BY_KEY[key]
        v, cur = m[metric], fail_best.get(key)
        if cur is None:
            fail_best[key] = v
        else:
            fail_best[key] = max(cur, v) if kind == "min" else min(cur, v)

    def _eta_s() -> float | None:
        """Seconds left to fill the databank at the acceptance rate so far."""
        if target_keep is None or not bank:
            return None
        missing = target_keep - len(bank)
        if missing <= 0:
            return 0.0
        elapsed = max(time.time() - t0, 1e-6)
        per_second = len(bank) / elapsed
        return round(missing / per_second, 1) if per_second > 0 else None

    def _fraction() -> float:
        """Progress means "how full is the databank" when a goal was set."""
        if target_keep is not None:
            return min(len(bank) / target_keep, 1.0)
        return min(tested / max_candidates, 1.0)

    def snapshot(final: bool = False) -> dict[str, Any]:
        return {
            "seed": seed,
            "tested": tested,
            "target": max_candidates,          # safety cap on candidates tested
            "target_keep": target_keep,        # goal: strategies in the databank
            "passed": passed,
            "rejected": tested - passed,
            "kept": len(bank),
            "accept": accept,
            "best_fitness": bank[0]["fitness"] if bank else 0.0,
            "elapsed_s": round(time.time() - t0, 1),
            "eta_s": _eta_s(),
            "best_history": best_history,
            "databank": bank if final else bank[:50],
            "split": None if df_oos is None else {
                "is_from": str(df.index[0])[:10], "is_to": str(df.index[-1])[:10],
                "oos_from": str(df_oos.index[0])[:10], "oos_to": str(df_oos.index[-1])[:10],
                "is_bars": len(df), "oos_bars": len(df_oos),
            },
            "diagnosis": _diagnose(),
        }

    def _diagnose() -> dict[str, Any]:
        """Why the databank is empty, in the user's terms."""
        if bank or tested == 0:
            return {}
        if too_few_trades == tested:
            return {"reason": "trades",
                    "text": f"Ninguna de las {tested} llegó a {min_trades} operaciones. "
                            f"Bajá el mínimo de trades o probá un timeframe más chico."}
        worst = max(blocked_by.items(), key=lambda kv: kv[1], default=None)
        if worst is None:
            return {}

        # Lo más accionable primero: si hubo candidatas que sólo tropezaron con
        # UN filtro, ese es el que hay que aflojar y se sabe exactamente cuántas
        # entrarían. Recién si no hay ninguna se informa el que más descarta.
        near = max(near_miss.items(), key=lambda kv: kv[1], default=None)
        if near is not None:
            key, count = near
            label = _CRIT_BY_KEY[key][2]
            limit, reached = accept.get(key), fail_best.get(key)
            txt = (f"<b>{count}</b> de las {tested} cumplían todo salvo "
                   f"<b>{label}</b>. Pediste {limit:g} y la mejor de ésas llegó a "
                   f"<b>{reached:.2f}</b>: aflojá ese filtro y entran.")
        else:
            key, count = worst
            label = _CRIT_BY_KEY[key][2]
            limit, reached = accept.get(key), fail_best.get(key)
            txt = (f"Ninguna candidata quedó cerca: todas fallan dos filtros o más "
                   f"a la vez. El que más descarta es <b>{label}</b> ({count} de "
                   f"{tested}); pediste {limit:g} y las que fallaron ahí no pasaron "
                   f"de <b>{reached:.2f}</b>.") if reached is not None else ""
        out = {"reason": key, "criterion": label, "limit": limit,
               "best_reached": reached, "rejected": count, "text": txt,
               "near_miss": near_miss}
        # la sugerencia de riesgo proyecta desde el MEJOR rendimiento alcanzado
        # por cualquier candidata, no desde el mejor de las que fallaron
        hint = _risk_suggestion(key, limit, best_seen.get(key))
        if hint:
            out["suggestion"] = hint
        return out

    def _risk_suggestion(key: str, limit: float | None,
                         reached: float | None) -> dict[str, Any] | None:
        """If the return target is out of reach at the current risk per trade,
        work out the risk that would get there — and what it costs in drawdown.

        Both CAGR and drawdown scale close to linearly with risk per trade
        (measured on SP500 H1: 1% risk -> 5.9% CAGR / 8.8% DD; 3% -> 17.3%/25.1%),
        so a single multiplier projects both honestly enough to decide with.
        """
        if key != "min_cagr_pct" or not limit or not reached or reached <= 0:
            return None
        if risk is None or risk.size_mode not in ("risk_pct", "percent_equity"):
            return None
        factor = limit / reached
        if factor <= 1.05:
            return None                                   # ya está al alcance
        current = risk.size_value
        dd_now = top_cagr.get("max_drawdown_pct", 0.0)
        unit = "riesgo por operación" if risk.size_mode == "risk_pct" else "capital nominal"

        # Un multiplicador enorme significa que el objetivo no está en este
        # mercado: subir el riesgo lo alcanzaría en el papel y reventaría la
        # cuenta en la práctica. Mejor proponer una meta que sí existe.
        SANE_FACTOR = 4.0
        if factor > SANE_FACTOR * 3:
            realistic = round(reached * SANE_FACTOR, 1)
            return {
                "current": current, "needed": None, "factor": round(factor, 2),
                "dd_now": round(dd_now, 1),
                "dd_projected": round(dd_now * SANE_FACTOR, 1),
                "size_mode": risk.size_mode, "unreachable": True,
                "realistic_target": realistic,
                "text": (f"Ni subiendo el riesgo se llega: harían falta "
                         f"<b>{factor:.0f}×</b> más ({round(current * factor, 1):g}% por "
                         f"operación), lo que reventaría la cuenta antes de lograrlo. "
                         f"Con este mercado y estas salidas, un objetivo realista es "
                         f"<b>~{realistic:g}% anual</b> subiendo el {unit} a "
                         f"{round(current * SANE_FACTOR, 1):g}%."),
                "warning": ("Si querés más rendimiento, conviene cambiar el mercado, el "
                            "timeframe o las salidas — no forzar el tamaño de posición."),
            }

        needed = round(current * factor, 2)
        dd_then = dd_now * factor
        return {
            "current": current, "needed": needed, "factor": round(factor, 2),
            "dd_now": round(dd_now, 1), "dd_projected": round(dd_then, 1),
            "size_mode": risk.size_mode, "unreachable": False,
            "text": (f"Con {unit} de <b>{current:g}%</b> el techo es ~{reached:.1f}% anual. "
                     f"Para llegar a {limit:g}% haría falta subirlo a <b>{needed:g}%</b> "
                     f"({factor:.1f}× más), y el drawdown pasaría de ~{dd_now:.0f}% a "
                     f"<b>~{dd_then:.0f}%</b>."),
            "warning": ("Un drawdown así vacía cuentas reales: es perder más de la mitad "
                        "del capital antes de recuperar." if dd_then >= 45 else ""),
        }

    def evaluate(genome: Genome, note: str = "") -> float:
        """Backtest one genome, update every counter, return its fitness."""
        nonlocal tested, passed, too_few_trades
        spec = build_spec(genome, direction=direction, risk=risk)
        res = run_backtest(df, spec, settings, cache=cache)
        m = res.metrics
        tested += 1
        score = -1e9

        if m["trades"] < min_trades:
            too_few_trades += 1
        else:
            _note_best(m)
            missed = _failed_criteria(m, accept)
            for k in missed:
                blocked_by[k] = blocked_by.get(k, 0) + 1
                _note_fail(k, m)
            if len(missed) == 1:
                near_miss[missed[0]] = near_miss.get(missed[0], 0) + 1
            score = float(fitness(m, fitness_mode))
            if not missed:
                passed += 1
                row = _row(genome, spec, m, score, passed, res.equity)
                if cache_oos is not None:
                    row.update(_validate_oos(spec))
                    row["oos_ratio"] = _oos_ratio(row)
                bank.append(row)
                bank.sort(key=lambda r: r["fitness"], reverse=True)
                del bank[keep_top:]

        if tested % 5 == 0 or tested >= max_candidates:
            best_history.append(bank[0]["fitness"] if bank else 0.0)
        # las primeras candidatas se publican de a una: en un dataset grande
        # cada backtest tarda casi un segundo y esperar diez para el primer
        # snapshot hace que la app parezca colgada apenas se aprieta Iniciar
        if handle is not None and (tested <= 5 or tested % 10 == 0
                                   or tested >= max_candidates):
            if target_keep is not None:
                msg = (f"{len(bank)}/{target_keep} estrategias en el databank · "
                       f"{tested:,} probadas{note}")
            else:
                msg = (f"{tested}/{max_candidates} candidatas · "
                       f"{len(bank)} en el databank{note}")
            handle.progress(_fraction(), msg)
            handle.publish(snapshot())
        return score

    def keep_going() -> bool:
        """Stop on: cancel, goal reached, or the safety cap on candidates."""
        if handle is not None and handle.cancelled:
            return False
        if tested >= max_candidates:
            return False
        if target_keep is not None:
            return len(bank) < target_keep
        return True

    def fresh_genome() -> Genome | None:
        """A genome not tried yet, or None once the space looks exhausted."""
        nonlocal dupes
        for _ in range(_EXHAUSTED_AFTER):
            g = random_genome(drivers, filters, max_filters, rng)
            if g.key() not in seen:
                seen.add(g.key())
                dupes = 0
                return g
            dupes += 1
        return None

    if method == "evolution":
        pop_size = max(int(population), 8)
        pop: list[tuple[float, Genome]] = []
        while len(pop) < pop_size and keep_going():
            g = fresh_genome()
            if g is None:
                break
            pop.append((evaluate(g, " · población inicial"), g))

        generation = 0
        while pop and keep_going():
            generation += 1
            pop.sort(key=lambda t: t[0], reverse=True)
            elite = pop[:max(2, pop_size // 5)]
            children: list[tuple[float, Genome]] = list(elite)

            def pick() -> Genome:
                idx = rng.integers(0, len(pop), size=3)
                return max((pop[i] for i in idx), key=lambda t: t[0])[1]

            while len(children) < pop_size and keep_going():
                child = _mutate(_crossover(pick(), pick(), rng),
                                drivers, filters, max_filters, rng, 0.3)
                if child.key() in seen:
                    alt = fresh_genome()
                    if alt is None:
                        break
                    child = alt
                else:
                    seen.add(child.key())
                children.append((evaluate(child, f" · generación {generation}"), child))
            if len(children) <= len(elite):
                break
            pop = children
    else:
        while keep_going():
            genome = fresh_genome()
            if genome is None:
                break
            evaluate(genome)

    out = snapshot(final=True)
    out["stopped"] = bool(handle.cancelled) if handle is not None else False
    out["exhausted"] = dupes >= _EXHAUSTED_AFTER
    out["reached_goal"] = target_keep is not None and len(bank) >= target_keep
    # searched as far as it was allowed to and still came up short: the UI has
    # to say so instead of presenting a half-full databank as a finished run
    out["hit_cap"] = (target_keep is not None and not out["reached_goal"]
                      and not out["stopped"] and not out["exhausted"])
    out["method"] = method
    out["too_few_trades"] = too_few_trades
    out["blocked_by"] = blocked_by
    out["best_seen"] = {k: round(v, 3) for k, v in best_seen.items()}
    return out
