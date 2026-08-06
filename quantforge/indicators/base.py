"""Indicator base class, parameter metadata and the global registry.

An indicator is a stateless class that turns an OHLCV frame plus parameters
into one or more named output series. Adding a custom indicator is three
lines: subclass :class:`Indicator`, declare ``params``/``outputs``, implement
``compute`` and decorate with ``@register``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class ParamDef:
    """Metadata for one tunable parameter (drives the UI and the optimizer)."""

    name: str
    default: float
    min: float
    max: float
    step: float = 1.0

    def to_dict(self) -> dict[str, float | str]:
        return {"name": self.name, "default": self.default,
                "min": self.min, "max": self.max, "step": self.step}


class Indicator(ABC):
    """Base class for all indicators."""

    name: ClassVar[str] = ""
    label: ClassVar[str] = ""
    category: ClassVar[str] = "other"     # trend | momentum | volatility | volume | channel
    params: ClassVar[tuple[ParamDef, ...]] = ()
    outputs: ClassVar[tuple[str, ...]] = ("value",)

    @classmethod
    @abstractmethod
    def compute(cls, df: pd.DataFrame, **p: float) -> dict[str, np.ndarray]:
        """Return ``{output_name: float64 array aligned with df}``."""

    @classmethod
    def resolved_params(cls, given: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for pd_ in cls.params:
            v = float(given.get(pd_.name, pd_.default))
            out[pd_.name] = v
        return out


REGISTRY: dict[str, type[Indicator]] = {}


def register(cls: type[Indicator]) -> type[Indicator]:
    """Class decorator adding an indicator to the global registry."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a name")
    REGISTRY[cls.name] = cls
    return cls


def indicator_catalog() -> list[dict[str, Any]]:
    """JSON-friendly catalog of every registered indicator (consumed by the UI)."""
    return [
        {
            "name": c.name,
            "label": c.label or c.name,
            "category": c.category,
            "params": [p.to_dict() for p in c.params],
            "outputs": list(c.outputs),
        }
        for c in sorted(REGISTRY.values(), key=lambda c: (c.category, c.name))
    ]


class IndicatorCache:
    """Memoises indicator computations for one dataset during a run.

    The generator, optimizer and GA evaluate thousands of strategies over the
    same frame; caching by ``(name, sorted params)`` makes repeated rules free.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self._store: dict[tuple, dict[str, np.ndarray]] = {}

    def get(self, name: str, params: dict[str, float]) -> dict[str, np.ndarray]:
        cls = REGISTRY.get(name)
        if cls is None:
            raise KeyError(f"Unknown indicator: {name}")
        resolved = cls.resolved_params(params)
        key = (name, tuple(sorted(resolved.items())))
        hit = self._store.get(key)
        if hit is None:
            hit = cls.compute(self.df, **resolved)
            self._store[key] = hit
        return hit
