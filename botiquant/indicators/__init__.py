"""Modular indicator library. Register custom indicators via ``@register``."""

from botiquant.indicators.base import Indicator, ParamDef, REGISTRY, register, indicator_catalog
from botiquant.indicators import library as _library  # noqa: F401  (populates REGISTRY)

__all__ = ["Indicator", "ParamDef", "REGISTRY", "register", "indicator_catalog"]
