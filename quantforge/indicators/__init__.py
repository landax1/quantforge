"""Modular indicator library. Register custom indicators via ``@register``."""

from quantforge.indicators.base import Indicator, ParamDef, REGISTRY, register, indicator_catalog
from quantforge.indicators import library as _library  # noqa: F401  (populates REGISTRY)

__all__ = ["Indicator", "ParamDef", "REGISTRY", "register", "indicator_catalog"]
