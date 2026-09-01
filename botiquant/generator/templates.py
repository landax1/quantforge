"""Rule templates: the building blocks the generator and GA combine.

A template knows how to build mirrored long/short condition lists from a set
of tunable *genes*. Drivers produce entry triggers; filters gate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from botiquant.core.models import Condition, Operand


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


# ------------------------------------------------------- el posicionamiento
#
# LOS UNICOS BLOQUES QUE NO MIRAN EL PRECIO. El funding lo paga el lado que
# esta de mas, asi que dice quien esta amontonado — informacion que no esta
# adentro de la vela y que por eso puede decidir distinto de todo lo demas.
# Es lo que le falta a un portafolio armado solo con medias moviles:
# decisiones que no se muevan todas juntas.
#
# SOLO EXISTEN EN PERPETUOS. Un CFD no tiene funding, y `mine` corta con un
# mensaje si alguien los pide sobre un historico que no lo trae.
#
# VAN POR PERCENTIL Y NO POR VALOR. Ver `FundingPct`: la tasa media anualizada
# va de +16,6% en Monero a -2,2% en Zcash, asi que un umbral crudo seria un
# filtro distinto en cada moneda.


@template("funding_alto_filter", "Crowded longs (high funding)", "filter", "funding",
          (Gene("period", 90, 30, 300, 30), Gene("pct", 80, 60, 95, 5)))
def _funding_alto(g: dict[str, float]):
    """Sólo cuando el funding está en la parte alta de su rango reciente.

    Funding alto es gente pagando por estar comprada. Si eso es buena o mala
    señal NO lo decide este archivo —lo decide la búsqueda, probándolo— y por
    eso el bloque existe en las dos versiones y no sólo en la que a alguien le
    parece la correcta.
    """
    c = [cond(ind("FundingPct", period=g["period"]), ">", const(g["pct"]))]
    return c, list(c)


@template("funding_bajo_filter", "Crowded shorts (low funding)", "filter", "funding",
          (Gene("period", 90, 30, 300, 30), Gene("pct", 20, 5, 40, 5)))
def _funding_bajo(g: dict[str, float]):
    """La contraria. Ver `funding_alto_filter`."""
    c = [cond(ind("FundingPct", period=g["period"]), "<", const(g["pct"]))]
    return c, list(c)


@template("atr_rising_filter", "Volatility expanding", "filter", "volatility",
          (Gene("period", 14, 7, 30, 1),))
def _atr_f(g: dict[str, float]):
    c = [cond(ind("ATR", period=g["period"]), "rising", const(0))]
    return c, list(c)


# --------------------------------------------------- filtros de contexto
#
# Los cinco de arriba miran indicadores clásicos. Estos cinco miran la
# ESTRUCTURA de lo que acaba de pasar: dónde está el precio dentro de su
# rango reciente, cómo cerró la última vela, qué día es. Son las preguntas que
# un operador se hace antes de apretar el botón y que la búsqueda no podía
# hacerse, y todos están normalizados —ATR, porcentaje, día— así que el mismo
# umbral significa lo mismo en cualquier instrumento.


@template("breakout_ready_filter", "Price at the edge of its range", "filter", "channel",
          (Gene("period", 20, 10, 100, 10), Gene("dist", 1.0, 0.25, 3.0, 0.25)))
def _breakout_ready(g: dict[str, float]):
    """Sólo cuando el precio ya está pegado al extremo del rango.

    Es el filtro que le falta a toda estrategia de ruptura: entra únicamente
    si el precio llegó a la puerta, y descarta las señales que aparecen en el
    medio del rango, donde una ruptura todavía tiene que recorrer todo el
    camino antes de ser una ruptura.
    """
    d = dict(period=g["period"])
    long = [cond(ind("DistATR", output="to_high", **d), "<", const(g["dist"]))]
    short = [cond(ind("DistATR", output="to_low", **d), "<", const(g["dist"]))]
    return long, short


@template("pullback_filter", "Price pulled back from the extreme", "filter", "channel",
          (Gene("period", 20, 10, 100, 10), Gene("dist", 1.5, 0.5, 5.0, 0.5)))
def _pullback(g: dict[str, float]):
    """El complemento exacto del anterior: sólo cuando el precio retrocedió.

    Las estrategias de reversión compran barato dentro de una tendencia, y
    "barato" no es un precio: son unos cuantos ATR por debajo de donde estuvo.
    """
    d = dict(period=g["period"])
    long = [cond(ind("DistATR", output="to_high", **d), ">", const(g["dist"]))]
    short = [cond(ind("DistATR", output="to_low", **d), ">", const(g["dist"]))]
    return long, short


@template("strong_close_filter", "Bar closed strong", "filter", "momentum",
          (Gene("level", 65, 55, 90, 5),))
def _strong_close(g: dict[str, float]):
    """La última vela cerró en su tercio superior (o inferior, para cortos)."""
    c = ind("ClosePosition")
    return ([cond(c, ">", const(g["level"]))],
            [cond(c, "<", const(100 - g["level"]))])


@template("expansion_filter", "Expansion bar", "filter", "volatility",
          (Gene("period", 20, 10, 100, 10), Gene("mult", 1.2, 0.6, 3.0, 0.2)))
def _expansion(g: dict[str, float]):
    """Sólo cuando la vela mide más que su volatilidad habitual.

    Distinto de "volatilidad expandiéndose", que mira la tendencia del ATR:
    esto mira si ESTA vela, la que dio la señal, tuvo tamaño de verdad. Una
    señal en una vela minúscula suele ser ruido con forma de señal.
    """
    c = [cond(ind("DistATR", output="bar_range", period=g["period"]), ">", const(g["mult"]))]
    return c, list(c)


@template("skip_weekday_filter", "Skip one weekday", "filter", "other",
          (Gene("day", 1, 1, 5, 1),))
def _skip_weekday(g: dict[str, float]):
    """No operar un día concreto de la semana (1 = lunes ... 5 = viernes).

    No se solapa con las franjas horarias: una franja recorta las HORAS de
    todos los días, y esto saca un día entero. El lunes abre con el hueco del
    fin de semana y el viernes cierra posiciones antes del cierre semanal; que
    a una estrategia le convenga saltearse alguno es una hipótesis vieja y
    barata de comprobar.
    """
    c = [cond(ind("DayOfWeek"), "!=", const(g["day"]))]
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
