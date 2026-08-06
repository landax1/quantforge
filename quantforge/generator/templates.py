"""Rule templates: the building blocks the generator and GA combine.

A template knows how to build mirrored long/short condition lists from a set
of tunable *genes*. Drivers produce entry triggers; filters gate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from quantforge.core.models import Condition, Operand


def ind(name: str, output: str = "value", shift: int = 0, **params: float) -> Operand:
    return Operand(type="indicator", name=name, params=dict(params), output=output, shift=shift)


def price(field_name: str = "close") -> Operand:
    return Operand(type="price", field_name=field_name)


def const(v: float) -> Operand:
    return Operand(type="const", value=float(v))


def cond(left: Operand, op: str, right: Operand) -> Condition:
    return Condition(left=left, op=op, right=right)


@dataclass(frozen=True, slots=True)
class Gene:
    """One tunable number inside a template."""

    name: str
    default: float
    min: float
    max: float
    step: float = 1.0


BuildFn = Callable[[dict[str, float]], tuple[list[Condition], list[Condition]]]


@dataclass(frozen=True, slots=True)
class RuleTemplate:
    id: str
    label: str
    kind: str                       # "driver" | "filter"
    category: str
    genes: tuple[Gene, ...]
    build: BuildFn = field(repr=False, compare=False, default=None)  # type: ignore[assignment]

    def resolved(self, genes: dict[str, float] | None) -> dict[str, float]:
        out = {g.name: g.default for g in self.genes}
        if genes:
            for g in self.genes:
                if g.name in genes:
                    out[g.name] = min(max(float(genes[g.name]), g.min), g.max)
        return out


TEMPLATES: dict[str, RuleTemplate] = {}


def template(id: str, label: str, kind: str, category: str, genes: tuple[Gene, ...]):
    """Decorator registering a build function as a template."""
    def wrap(fn: BuildFn) -> BuildFn:
        TEMPLATES[id] = RuleTemplate(id=id, label=label, kind=kind,
                                     category=category, genes=genes, build=fn)
        return fn
    return wrap


# --------------------------------------------------------------------- drivers

@template("ema_cross", "EMA crossover", "driver", "trend",
          (Gene("fast", 20, 5, 60, 5), Gene("slow", 80, 30, 250, 10)))
def _ema_cross(g: dict[str, float]):
    fast, slow = g["fast"], max(g["slow"], g["fast"] + 5)
    long = [cond(ind("EMA", period=fast), "cross_above", ind("EMA", period=slow))]
    short = [cond(ind("EMA", period=fast), "cross_below", ind("EMA", period=slow))]
    return long, short


@template("price_ema", "Price crosses EMA", "driver", "trend",
          (Gene("period", 50, 10, 200, 10),))
def _price_ema(g: dict[str, float]):
    long = [cond(price(), "cross_above", ind("EMA", period=g["period"]))]
    short = [cond(price(), "cross_below", ind("EMA", period=g["period"]))]
    return long, short


@template("donchian_break", "Donchian breakout", "driver", "channel",
          (Gene("period", 20, 10, 100, 5),))
def _donchian(g: dict[str, float]):
    long = [cond(price(), ">", ind("Donchian", output="upper", period=g["period"]))]
    short = [cond(price(), "<", ind("Donchian", output="lower", period=g["period"]))]
    return long, short


@template("rsi_reversal", "RSI reversal", "driver", "momentum",
          (Gene("period", 14, 5, 30, 1), Gene("level", 30, 15, 45, 5)))
def _rsi_rev(g: dict[str, float]):
    long = [cond(ind("RSI", period=g["period"]), "cross_above", const(g["level"]))]
    short = [cond(ind("RSI", period=g["period"]), "cross_below", const(100 - g["level"]))]
    return long, short


@template("macd_cross", "MACD signal cross", "driver", "momentum",
          (Gene("fast", 12, 6, 20, 2), Gene("slow", 26, 20, 60, 4), Gene("signal", 9, 5, 15, 2)))
def _macd(g: dict[str, float]):
    fast, slow = g["fast"], max(g["slow"], g["fast"] + 6)
    m = dict(fast=fast, slow=slow, signal=g["signal"])
    long = [cond(ind("MACD", output="macd", **m), "cross_above", ind("MACD", output="signal", **m))]
    short = [cond(ind("MACD", output="macd", **m), "cross_below", ind("MACD", output="signal", **m))]
    return long, short


@template("stoch_cross", "Stochastic reversal", "driver", "momentum",
          (Gene("k_period", 14, 5, 30, 1), Gene("level", 20, 10, 40, 5)))
def _stoch(g: dict[str, float]):
    k = ind("Stochastic", output="k", k_period=g["k_period"], d_period=3)
    long = [cond(k, "cross_above", const(g["level"]))]
    short = [cond(k, "cross_below", const(100 - g["level"]))]
    return long, short


@template("supertrend_flip", "Supertrend flip", "driver", "trend",
          (Gene("period", 10, 5, 30, 1), Gene("mult", 3.0, 1.0, 6.0, 0.5)))
def _supertrend(g: dict[str, float]):
    d = ind("Supertrend", output="direction", period=g["period"], mult=g["mult"])
    long = [cond(d, "cross_above", const(0))]
    short = [cond(d, "cross_below", const(0))]
    return long, short


@template("bollinger_revert", "Bollinger mean reversion", "driver", "volatility",
          (Gene("period", 20, 10, 60, 5), Gene("mult", 2.0, 1.5, 3.5, 0.25)))
def _boll(g: dict[str, float]):
    b = dict(period=g["period"], mult=g["mult"])
    long = [cond(price(), "cross_below", ind("Bollinger", output="lower", **b))]
    short = [cond(price(), "cross_above", ind("Bollinger", output="upper", **b))]
    return long, short


@template("cci_extreme", "CCI recovery", "driver", "momentum",
          (Gene("period", 20, 10, 50, 5), Gene("level", 100, 50, 200, 25)))
def _cci(g: dict[str, float]):
    c = ind("CCI", period=g["period"])
    long = [cond(c, "cross_above", const(-g["level"]))]
    short = [cond(c, "cross_below", const(g["level"]))]
    return long, short


@template("momentum_sign", "Momentum zero-cross", "driver", "momentum",
          (Gene("period", 12, 5, 50, 1),))
def _mom(g: dict[str, float]):
    m = ind("Momentum", period=g["period"])
    long = [cond(m, "cross_above", const(0))]
    short = [cond(m, "cross_below", const(0))]
    return long, short


@template("vwap_cross", "VWAP cross", "driver", "volume", ())
def _vwap(g: dict[str, float]):
    long = [cond(price(), "cross_above", ind("VWAP"))]
    short = [cond(price(), "cross_below", ind("VWAP"))]
    return long, short


@template("ichimoku_kumo", "Ichimoku cloud breakout", "driver", "trend",
          (Gene("kijun", 26, 15, 60, 5),))
def _ichi(g: dict[str, float]):
    p = dict(tenkan=9, kijun=g["kijun"], senkou=52)
    long = [cond(price(), "cross_above", ind("Ichimoku", output="senkou_a", **p)),
            cond(price(), ">", ind("Ichimoku", output="senkou_b", **p))]
    short = [cond(price(), "cross_below", ind("Ichimoku", output="senkou_a", **p)),
             cond(price(), "<", ind("Ichimoku", output="senkou_b", **p))]
    return long, short


# --------------------------------------------------------------------- filters

@template("adx_filter", "ADX strength filter", "filter", "trend",
          (Gene("period", 14, 7, 30, 1), Gene("level", 20, 10, 40, 5)))
def _adx_f(g: dict[str, float]):
    c = [cond(ind("ADX", output="adx", period=g["period"]), ">", const(g["level"]))]
    return c, list(c)


@template("ema_trend_filter", "EMA trend filter", "filter", "trend",
          (Gene("period", 200, 50, 400, 25),))
def _trend_f(g: dict[str, float]):
    long = [cond(price(), ">", ind("EMA", period=g["period"]))]
    short = [cond(price(), "<", ind("EMA", period=g["period"]))]
    return long, short


@template("rsi_zone_filter", "RSI regime filter", "filter", "momentum",
          (Gene("period", 14, 7, 30, 1),))
def _rsi_zone(g: dict[str, float]):
    r = ind("RSI", period=g["period"])
    return [cond(r, ">", const(50))], [cond(r, "<", const(50))]


@template("volume_filter", "Above-average volume", "filter", "volume",
          (Gene("period", 20, 10, 60, 5),))
def _vol_f(g: dict[str, float]):
    c = [cond(price("volume"), ">", ind("VolumeSMA", period=g["period"]))]
    return c, list(c)


@template("atr_rising_filter", "Volatility expanding", "filter", "volatility",
          (Gene("period", 14, 7, 30, 1),))
def _atr_f(g: dict[str, float]):
    c = [cond(ind("ATR", period=g["period"]), "rising", const(0))]
    return c, list(c)


def drivers() -> list[RuleTemplate]:
    return [t for t in TEMPLATES.values() if t.kind == "driver"]


def filters() -> list[RuleTemplate]:
    return [t for t in TEMPLATES.values() if t.kind == "filter"]


def template_catalog() -> list[dict]:
    return [
        {"id": t.id, "label": t.label, "kind": t.kind, "category": t.category,
         "genes": [{"name": g.name, "default": g.default, "min": g.min,
                    "max": g.max, "step": g.step} for g in t.genes]}
        for t in TEMPLATES.values()
    ]
