"""Domain models: operands, conditions, risk, time filters and strategy specs.

Every model is a plain dataclass with ``to_dict`` / ``from_dict`` so specs can be
stored as JSON in SQLite and travel over the HTTP API without coupling the core
to any web framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

OperandType = Literal["indicator", "price", "const"]
Operator = Literal[">", "<", ">=", "<=", "==", "!=",
                   "cross_above", "cross_below", "rising", "falling"]
Direction = Literal["long", "short", "both"]

# ``==`` y ``!=`` existen para las magnitudes que son categorías y no escalas:
# el día de la semana, la dirección de un Supertrend. Sobre un precio no
# tendrían sentido —dos floats nunca son exactamente iguales—, pero sobre un
# valor discreto son la única forma honesta de decir "los lunes no".
OPERATORS: tuple[str, ...] = (
    ">", "<", ">=", "<=", "==", "!=", "cross_above", "cross_below", "rising", "falling",
)

PRICE_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume")


@dataclass(slots=True)
class Operand:
    """One side of a condition: an indicator output, a price field or a constant."""

    type: OperandType = "const"
    # indicator operands
    name: str = ""
    params: dict[str, float] = field(default_factory=dict)
    output: str = "value"
    # price operands
    field_name: str = "close"
    # const operands
    value: float = 0.0
    # bars to shift back (0 = current bar)
    shift: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "params": dict(self.params),
            "output": self.output,
            "field": self.field_name,
            "value": self.value,
            "shift": self.shift,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Operand":
        return cls(
            type=d.get("type", "const"),
            name=d.get("name", ""),
            params={k: float(v) for k, v in (d.get("params") or {}).items()},
            output=d.get("output", "value"),
            # JSON says "field", the dataclass attribute is field_name — accept
            # either so a hand-written spec cannot silently become a close price
            field_name=d.get("field", d.get("field_name", "close")),
            value=float(d.get("value", 0.0)),
            shift=int(d.get("shift", 0)),
        )

    def label(self) -> str:
        if self.type == "const":
            return f"{self.value:g}"
        if self.type == "price":
            return self.field_name.capitalize()
        p = ",".join(f"{v:g}" for v in self.params.values())
        out = f".{self.output}" if self.output != "value" else ""
        return f"{self.name}({p}){out}"


@dataclass(slots=True)
class Condition:
    """A single rule such as ``EMA(50) cross_above EMA(200)``."""

    left: Operand = field(default_factory=Operand)
    op: str = ">"
    right: Operand = field(default_factory=Operand)

    def to_dict(self) -> dict[str, Any]:
        return {"left": self.left.to_dict(), "op": self.op, "right": self.right.to_dict()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Condition":
        return cls(
            left=Operand.from_dict(d.get("left", {})),
            op=d.get("op", ">"),
            right=Operand.from_dict(d.get("right", {})),
        )

    def label(self) -> str:
        pretty = {
            "cross_above": "crosses above", "cross_below": "crosses below",
            "rising": "is rising", "falling": "is falling",
            "==": "is", "!=": "is not",
        }
        op = pretty.get(self.op, self.op)
        if self.op in ("rising", "falling"):
            return f"{self.left.label()} {op}"
        return f"{self.left.label()} {op} {self.right.label()}"


@dataclass(slots=True)
class RiskConfig:
    """Stop-loss / take-profit and position sizing."""

    # "points" = a fixed distance in the instrument's own price units (the way
    # a trader states a stop: "200 points"); "money" = a fixed loss in account
    # currency, converted to distance once the position size is known.
    stop_type: Literal["none", "atr", "percent", "points", "money"] = "atr"
    stop_value: float = 2.0          # ATR multiple, percent, points or money
    target_type: Literal["none", "atr", "percent", "points", "money"] = "atr"
    target_value: float = 3.0
    atr_period: int = 14
    size_mode: Literal["risk_pct", "percent_equity", "fixed_units"] = "risk_pct"
    size_value: float = 1.0          # % risked, % of equity, or units
    max_bars_in_trade: int = 0       # 0 = unlimited
    # Relación riesgo/beneficio: el target vale esta cantidad de veces el stop.
    # El minero fija stop_value por candidata (busca la distancia que funciona)
    # y deriva target_value de acá, así el usuario configura una sola relación
    # en vez de dos distancias que tienen que ser coherentes entre sí.
    reward_ratio: float = 2.0
    # Trailing en múltiplos de ATR: una vez que el precio avanzó, el stop lo
    # persigue a esta distancia y nunca retrocede. 0 lo desactiva. Es un gen
    # que el minero busca por candidata, igual que la distancia del stop.
    trail_atr: float = 0.0

    def coherence_error(self) -> str | None:
        """Why this combination cannot be simulated, or None if it is sound.

        ``risk_pct`` sizes the position from the stop distance, so it needs a
        stop whose distance is known *before* sizing. A money stop is the other
        way round (distance comes from the size), and no stop leaves nothing to
        size against — both would silently fall back to full-equity sizing.
        """
        if self.size_mode == "risk_pct":
            if self.stop_type == "none":
                return ("Arriesgar un % por operación necesita un stop loss: "
                        "sin stop no hay distancia contra la cual dimensionar.")
            if self.stop_type == "money":
                return ("Arriesgar un % por operación no se puede combinar con un "
                        "stop en dinero: el tamaño saldría del stop y el stop del "
                        "tamaño. Usá puntos, % o ATR.")
        return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RiskConfig":
        base = cls()
        return cls(
            stop_type=d.get("stop_type", base.stop_type),
            stop_value=float(d.get("stop_value", base.stop_value)),
            target_type=d.get("target_type", base.target_type),
            target_value=float(d.get("target_value", base.target_value)),
            atr_period=int(d.get("atr_period", base.atr_period)),
            size_mode=d.get("size_mode", base.size_mode),
            size_value=float(d.get("size_value", base.size_value)),
            max_bars_in_trade=int(d.get("max_bars_in_trade", 0)),
            reward_ratio=float(d.get("reward_ratio", base.reward_ratio)),
            trail_atr=max(float(d.get("trail_atr", base.trail_atr)), 0.0),
        )


@dataclass(slots=True)
class TimeFilter:
    """Restrict entries to certain week days and hours (UTC of the data)."""

    enabled: bool = False
    days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon..Fri
    start_hour: int = 0
    end_hour: int = 24

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "days": list(self.days),
                "start_hour": self.start_hour, "end_hour": self.end_hour}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TimeFilter":
        return cls(
            enabled=bool(d.get("enabled", False)),
            days=[int(x) for x in d.get("days", [0, 1, 2, 3, 4])],
            start_hour=int(d.get("start_hour", 0)),
            end_hour=int(d.get("end_hour", 24)),
        )


@dataclass(slots=True)
class StrategySpec:
    """A complete, serialisable trading strategy."""

    name: str = "Untitled strategy"
    direction: Direction = "long"
    entry_long: list[Condition] = field(default_factory=list)
    exit_long: list[Condition] = field(default_factory=list)
    entry_short: list[Condition] = field(default_factory=list)
    exit_short: list[Condition] = field(default_factory=list)
    risk: RiskConfig = field(default_factory=RiskConfig)
    time_filter: TimeFilter = field(default_factory=TimeFilter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "entry_long": [c.to_dict() for c in self.entry_long],
            "exit_long": [c.to_dict() for c in self.exit_long],
            "entry_short": [c.to_dict() for c in self.entry_short],
            "exit_short": [c.to_dict() for c in self.exit_short],
            "risk": self.risk.to_dict(),
            "time_filter": self.time_filter.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StrategySpec":
        return cls(
            name=d.get("name", "Untitled strategy"),
            direction=d.get("direction", "long"),
            entry_long=[Condition.from_dict(c) for c in d.get("entry_long", [])],
            exit_long=[Condition.from_dict(c) for c in d.get("exit_long", [])],
            entry_short=[Condition.from_dict(c) for c in d.get("entry_short", [])],
            exit_short=[Condition.from_dict(c) for c in d.get("exit_short", [])],
            risk=RiskConfig.from_dict(d.get("risk", {})),
            time_filter=TimeFilter.from_dict(d.get("time_filter", {})),
        )

    def describe(self) -> str:
        parts: list[str] = []
        if self.entry_long:
            parts.append("LONG when " + " AND ".join(c.label() for c in self.entry_long))
        if self.entry_short:
            parts.append("SHORT when " + " AND ".join(c.label() for c in self.entry_short))
        return "; ".join(parts) or "(no rules)"


@dataclass(slots=True)
class BacktestSettings:
    """Execution assumptions shared by every backtest."""

    initial_capital: float = 10_000.0

    # Two ways to price a fill, mirroring how brokers actually quote costs:
    #
    #   * absolute (preferred, broker-native): ``spread``/``slippage`` in the
    #     instrument's own price units — 0.36 for an index quoted in points,
    #     0.00012 for EURUSD. Copy them straight off the symbol spec.
    #   * relative: ``commission_pct``/``slippage_pct`` as a % of notional, for
    #     stock-style per-value commissions.
    #
    # Both are charged when both are set. The percentage defaults are 0 because
    # a stock-style 0.05% commission on a 7000-point index is ~9 points round
    # trip, which makes every mined strategy unprofitable by construction.
    spread: float = 0.0              # price units, charged once per round trip
    slippage: float = 0.0            # price units, adverse, per side
    commission_pct: float = 0.0      # per side, % of notional
    slippage_pct: float = 0.0        # adverse fill, % of price

    # EL FUNDING DE UN PERPETUO. Es la tercera clase de costo y funciona
    # distinto a las otras dos: no se paga al abrir ni al cerrar, sino cada
    # ocho horas por TENER la posición abierta.
    #
    # Va como serie y no como número porque la tasa cambia todo el tiempo.
    # Medido sobre siete años de BTCUSDT: media +0,01061% por cobro —que son
    # +11,61% anual— con extremos de ±0,30% y signo negativo el 14,3% del
    # tiempo.
    #
    # CUIDADO CON ESE 11,61%: es lo que costaría estar comprado TODO el año.
    # Como sólo se cobra con la posición abierta, el costo real es esa tasa por
    # la exposición, y nuestras estrategias rondan el 11% de tiempo en mercado:
    #
    #     exposición   costo anual real
    #          5%           0,54%
    #         11%           1,19%      <- la típica de una estrategia nuestra
    #         35%           3,80%
    #        100%          10,85%
    #
    # O sea que se lleva alrededor del 15% de una estrategia de 8% anual, no
    # toda. Y penaliza selectivamente a las que más tiempo pasan adentro, que
    # es exactamente el comportamiento correcto.
    #
    # El signo es lo otro que importa. Tasa positiva: los largos le pagan a los
    # cortos. Negativa: al revés. Como en cripto casi todo el mundo va
    # comprado, la tasa es positiva la mayor parte del tiempo y el lado corto
    # COBRA. No modelarlo no era sólo subestimar un costo: era no poder ver esa
    # familia de estrategias.
    #
    # `None` por defecto, y con eso el motor se comporta exactamente como
    # antes. Un CFD no tiene funding y no debe pagar nada.
    funding: Any = None              # pd.Series de tasas, indexada por momento de cobro

    # EL SWAP DE UN CFD. Es el mismo concepto que el funding —un costo por
    # TENER la posición— pero de la otra mitad del catálogo, y hasta hoy no lo
    # cobrábamos: los backtests de S&P, oro y EURUSD ignoraban por completo el
    # costo de mantener. No era un hueco de cripto, era un hueco nuestro.
    #
    # POR QUÉ ES UN NÚMERO Y EL FUNDING UNA SERIE. La tasa de un perpetuo es
    # pública, histórica y exacta: se baja en cuatro segundos. El swap lo fija
    # cada bróker, cambia sin aviso y NADIE publica la serie histórica. Pedir
    # el promedio anual —el número que está en la ficha del símbolo— es lo
    # máximo que se puede sostener con honestidad.
    #
    # POR QUÉ NO ES LO MISMO QUE SUBIR LA COMISIÓN. La comisión escala con
    # CUÁNTAS operaciones hacés; esto escala con CUÁNTO TIEMPO estás adentro.
    # Una estrategia de 200 entradas al año que aguanta dos horas paga mucha
    # comisión y casi nada de swap; una de 6 entradas que aguanta dos meses
    # paga lo contrario. Un solo número no puede representar a las dos.
    #
    # Y EL SIGNO ES DISTINTO AL DEL FUNDING. El funding lo paga un lado y lo
    # cobra el otro. El swap se lo cobra el bróker a los dos. Por eso no se
    # pueden meter en el mismo campo aunque midan lo mismo.
    #
    # Se prorratea por barra en vez de cobrarse sólo de un día para el otro.
    # Es una simplificación deliberada: el cobro real depende de la hora de
    # rollover del bróker y del triple del miércoles, que no sabemos. Prorratear
    # cobra de más a una estrategia intradía —del orden de 0,002% por operación
    # con 5% anual— y da exacto donde el costo importa, que es aguantando días.
    # Se equivoca hacia el lado pesimista, que es el lado correcto.
    #
    # 0 por defecto: quien no lo configure queda exactamente como estaba.
    swap_anual: float = 0.0          # % anual sobre el nocional, cobrado a los dos lados

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BacktestSettings":
        base = cls()
        return cls(
            initial_capital=float(d.get("initial_capital", base.initial_capital)),
            spread=max(float(d.get("spread", base.spread)), 0.0),
            slippage=max(float(d.get("slippage", base.slippage)), 0.0),
            commission_pct=float(d.get("commission_pct", base.commission_pct)),
            slippage_pct=float(d.get("slippage_pct", base.slippage_pct)),
            # La serie no viaja por JSON: la pone quien carga el dataset, del
            # lado del servidor. Si viniera del cliente habría que validarla
            # entera, y no hay motivo para que el navegador la mande.
            funding=d.get("funding", base.funding),
            swap_anual=max(float(d.get("swap_anual", base.swap_anual)), 0.0),
        )


@dataclass(slots=True)
class Trade:
    """One closed trade produced by the engine."""

    entry_time: str
    exit_time: str
    direction: str            # "long" | "short"
    entry_price: float
    exit_price: float
    units: float
    pnl: float
    pnl_pct: float
    bars: int
    exit_reason: str          # "signal" | "stop" | "target" | "time" | "end"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
