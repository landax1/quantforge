"""Performance metrics computed from an equity curve and a trade list."""

from __future__ import annotations

import numpy as np
import pandas as pd

from botiquant.core.models import Trade

# Annualisation: bars per year inferred from the median bar interval.
_SECONDS_PER_YEAR = 365.25 * 24 * 3600


def bars_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 3:
        return 252.0
    # unit-safe regardless of ns/us datetime resolution (pandas 3 may use either)
    deltas = np.diff(index.values).astype("timedelta64[s]").astype(np.float64)
    median = float(np.median(deltas))
    if median <= 0:
        return 252.0
    return _SECONDS_PER_YEAR / median


def max_drawdown(equity: np.ndarray) -> tuple[float, float]:
    """Return (max drawdown in money, max drawdown in %)."""
    if len(equity) == 0:
        return 0.0, 0.0
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_pct = np.where(peak > 0, dd / peak * 100.0, 0.0)
    return float(dd.max()), float(dd_pct.max())


def compute_metrics(eq: pd.Series, trades: list[Trade], initial: float) -> dict[str, float]:
    """All headline metrics as a flat JSON-friendly dict."""
    equity = eq.to_numpy(dtype=np.float64)
    final = float(equity[-1]) if len(equity) else initial
    net_profit = final - initial
    net_profit_pct = net_profit / initial * 100.0 if initial else 0.0

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    gross_win = float(sum(wins))
    gross_loss = float(-sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss > 1e-9 else (99.0 if gross_win > 0 else 0.0)
    win_rate = len(wins) / len(trades) * 100.0 if trades else 0.0
    avg_trade = net_profit / len(trades) if trades else 0.0
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    # expectancy in R (average loss as the risk unit)
    expectancy = ((win_rate / 100.0) * avg_win - (1 - win_rate / 100.0) * avg_loss) / avg_loss \
        if avg_loss > 1e-9 else 0.0

    dd_abs, dd_pct = max_drawdown(equity)
    recovery = net_profit / dd_abs if dd_abs > 1e-9 else 0.0

    # bar returns for Sharpe / Sortino
    rets = np.diff(equity) / np.where(equity[:-1] > 0, equity[:-1], np.nan)
    rets = rets[~np.isnan(rets)]
    bpy = bars_per_year(eq.index)
    if len(rets) > 2 and rets.std(ddof=1) > 1e-12:
        sharpe = float(rets.mean() / rets.std(ddof=1) * np.sqrt(bpy))
    else:
        sharpe = 0.0
    downside = rets[rets < 0]
    if len(rets) > 2 and len(downside) > 1 and downside.std(ddof=1) > 1e-12:
        sortino = float(rets.mean() / downside.std(ddof=1) * np.sqrt(bpy))
    else:
        sortino = 0.0

    # Calendar span, not bar count: an hourly series covers ~8.9 "bar years" per
    # 13.6 calendar years because markets close nights and weekends. Dividing by
    # bar-years would inflate CAGR by ~50%.
    if len(eq.index) > 1:
        span_seconds = (eq.index[-1] - eq.index[0]).total_seconds()
        years = max(span_seconds / _SECONDS_PER_YEAR, 1e-9)
    else:
        years = max(len(equity) / bpy, 1e-9)
    cagr = ((final / initial) ** (1.0 / years) - 1.0) * 100.0 if initial > 0 and final > 0 else 0.0

    # Time in the market. A strategy flat 97% of the time cannot compound like
    # buy & hold however good its edge is — this is the number that explains a
    # healthy profit factor sitting next to a tiny CAGR.
    bars_held = sum(t.bars for t in trades)
    exposure = bars_held / len(equity) * 100.0 if len(equity) else 0.0
    # return per unit of time actually risked
    cagr_exposed = cagr / (exposure / 100.0) if exposure > 0.01 else 0.0

    # Consistencia en el calendario y reparto de la ganancia: las dos señales
    # que separan una ventaja real de una racha afortunada. Un mes bueno cada
    # tres, o una sola operación que hizo la mitad del profit, son estrategias
    # que no se pueden repetir aunque el total cierre lindo.
    months_positive, months_total, worst_month = _month_stats(eq, initial)
    top_trade_share = (max(wins) / gross_win * 100.0) if wins and gross_win > 1e-9 else 100.0

    return {
        "net_profit": round(net_profit, 2),
        "net_profit_pct": round(net_profit_pct, 2),
        "cagr_pct": round(cagr, 2),
        "profit_factor": round(min(profit_factor, 99.0), 3),
        "sharpe": round(sharpe, 3),
        "sortino": round(min(sortino, 99.0), 3),
        "max_drawdown": round(dd_abs, 2),
        "max_drawdown_pct": round(dd_pct, 2),
        "recovery_factor": round(recovery, 3),
        "win_rate_pct": round(win_rate, 2),
        "trades": len(trades),
        "avg_trade": round(avg_trade, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy_r": round(expectancy, 3),
        "final_equity": round(final, 2),
        "exposure_pct": round(exposure, 2),
        "cagr_exposed_pct": round(min(cagr_exposed, 9999.0), 2),
        "years": round(years, 2),
        "months_positive_pct": round(months_positive, 2),
        "months_total": months_total,
        # Cuántas veces opera al mes. Es el mismo dato que `trades` pero
        # comparable: 200 operaciones son muchas en dos años y pocas en veinte,
        # y sobre el total no se puede pedir un mínimo que signifique lo mismo
        # en dos históricos de distinto largo.
        "trades_per_month": round(len(trades) / months_total, 2) if months_total else 0.0,
        # El mismo dato en la unidad en la que se piensa una cuenta de fondeo.
        # "Necesito operar casi todos los días" se verifica contra operaciones
        # por SEMANA: por mes, un 20 puede ser cuatro días seguidos y después
        # nada, y para un desafío con fecha de vencimiento eso no sirve.
        #
        # Se deriva de los mismos meses que la línea de arriba, y no del span
        # en segundos, para que los dos números no puedan contradecirse.
        "trades_per_week": (round(len(trades) / (months_total * _SEMANAS_POR_MES), 2)
                            if months_total else 0.0),
        "worst_month_pct": round(worst_month, 2),
        "top_trade_share_pct": round(min(top_trade_share, 100.0), 2),
    }


#: Semanas que tiene un mes en promedio (52,1775 / 12). Sale del año medio y
#: no de 4, que acumularía casi un mes de error al año.
_SEMANAS_POR_MES = 52.1775 / 12

def _month_stats(eq: pd.Series, initial: float) -> tuple[float, int, float]:
    """(% de meses positivos, meses totales, peor mes en %)."""
    if len(eq) < 2:
        return 0.0, 0, 0.0
    monthly_last = eq.resample("ME").last()
    prev = monthly_last.shift(1)
    if len(prev) > 0:
        prev.iloc[0] = initial
    rets = ((monthly_last / prev - 1.0) * 100.0).dropna()
    rets = rets[np.isfinite(rets)]
    if not len(rets):
        return 0.0, 0, 0.0
    positive = float((rets > 0).sum()) / len(rets) * 100.0
    return positive, int(len(rets)), float(rets.min())


# ============================================================== QF Score ====
# La rentabilidad NO manda. Un +300% hecho con 22 operaciones, la mitad del
# profit en una sola de ellas y un 60% de drawdown es una anécdota, no una
# estrategia; un +40% repartido en 500 operaciones y en casi todos los meses
# es algo que se puede volver a operar mañana. El score mide eso último.
#
# Seis componentes de 0 a 1, cada uno con su peso, multiplicados por un factor
# de viabilidad que hunde a las que ni siquiera ganan plata. Total: 0 a 100.
SCORE_PARTS: tuple[tuple[str, str, float], ...] = (
    ("consistencia", "Consistencia (Sharpe)", 22.0),
    ("recuperacion", "Ganancia vs. caída", 22.0),
    ("evidencia", "Evidencia (nº de operaciones)", 18.0),
    ("ventaja", "Ventaja por operación", 16.0),
    ("estabilidad", "Estabilidad mes a mes", 14.0),
    ("reparto", "Ganancia repartida", 8.0),
)


def _clip01(x: float) -> float:
    return 0.0 if x <= 0 else (1.0 if x >= 1 else float(x))


def score_breakdown(m: dict[str, float]) -> dict[str, float]:
    """Cada componente del QF Score, de 0 a 1, para poder mostrarlo abierto."""
    trades = m.get("trades", 0)
    if not trades:
        return {k: 0.0 for k, _l, _w in SCORE_PARTS}

    dd = max(m.get("max_drawdown_pct", 0.0), 0.5)
    mar = m.get("cagr_pct", 0.0) / dd          # rendimiento por unidad de caída

    return {
        # Sharpe 2.0 es sobresaliente en sistemas de este tipo
        "consistencia": _clip01(m.get("sharpe", 0.0) / 2.0),
        # MAR 0.8 (ganar al año el 80% de lo que se cae) es excelente
        "recuperacion": _clip01(mar / 0.8),
        # 400 operaciones ya son muestra suficiente; 50 casi no dicen nada
        "evidencia": _clip01(np.sqrt(trades) / np.sqrt(400.0)),
        # 0.3R de expectativa por operación es una ventaja fuerte
        "ventaja": _clip01(m.get("expectancy_r", 0.0) / 0.3),
        # 40% de meses positivos no es nada; 65% es muy consistente
        "estabilidad": _clip01((m.get("months_positive_pct", 0.0) - 40.0) / 25.0),
        # si la mejor operación aporta más del 35% del profit, fue suerte
        "reparto": _clip01((35.0 - m.get("top_trade_share_pct", 100.0)) / 30.0),
    }


def bq_score(m: dict[str, float]) -> float:
    """Puntaje 0-100 de Botiquant: qué tan repetible parece la estrategia."""
    if not m.get("trades", 0):
        return 0.0
    parts = score_breakdown(m)
    total = sum(parts[k] * w for k, _l, w in SCORE_PARTS)
    # viabilidad: por debajo de PF 0.95 no hay nada que puntuar; recién en 1.20
    # el score se expresa entero. Mantiene el orden entre las perdedoras sin
    # dejar que se acerquen a una ganadora.
    viability = _clip01((m.get("profit_factor", 0.0) - 0.95) / 0.25)
    return round(total * viability, 2)


def fitness(metrics: dict[str, float], mode: str = "composite") -> float:
    """Fitness determinista que usan el minero, el generador y el GA.

    ``composite`` es el QF Score: ordena por robustez, no por rentabilidad.
    Los otros modos existen para comparar contra un criterio único.
    """
    trades = metrics.get("trades", 0)
    if trades == 0:
        return -1e9
    if mode == "net_profit":
        return metrics["net_profit"]
    if mode == "profit_factor":
        return metrics["profit_factor"] * min(np.sqrt(trades), 10.0)
    if mode == "sharpe":
        return metrics["sharpe"]
    if mode == "activity":
        # Para quien tiene FECHA DE VENCIMIENTO: un desafio de cuenta fondeada
        # no premia a la mejor estrategia sino a la mejor que ademas alcance a
        # operar dentro del plazo.
        #
        # Es un desempate y no un criterio nuevo, y eso importa. Pedir la
        # frecuencia como FILTRO no funciona: medido sobre SP500 a 30 minutos,
        # cuatro anios, 1400 candidatas, exigir tres operaciones por semana
        # ademas de rentabilidad y caida chica devuelve cero, y exigir dos
        # devuelve una — tan pocas que encontrar algo depende de la semilla.
        # Ser rentable es ser selectivo, y ser selectivo es operar poco.
        #
        # Como orden en cambio siempre devuelve algo: entran las que pasaron la
        # vara de calidad y arriba quedan las que mas operan. El premio se topa
        # en cinco por semana —una por dia habil, que es lo que se pide— para
        # que no gane la que opera trescientas veces por ruido.
        base = bq_score(metrics)
        por_semana = min(metrics.get("trades_per_week", 0.0), 5.0)
        return base + 12.0 * (por_semana / 5.0)
    return bq_score(metrics)
