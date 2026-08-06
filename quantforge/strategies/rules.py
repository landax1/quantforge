"""Vectorised evaluation of conditions against an OHLCV frame.

Turns :class:`~quantforge.core.models.Condition` lists into boolean numpy
arrays. All comparisons treat NaN (warm-up) as False.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantforge.core.models import Condition, Operand, TimeFilter
from quantforge.indicators.base import IndicatorCache


class EvalContext:
    """Holds the frame and indicator cache used while evaluating rules."""

    def __init__(self, df: pd.DataFrame, cache: IndicatorCache | None = None) -> None:
        self.df = df
        self.cache = cache or IndicatorCache(df)
        self.n = len(df)

    def resolve(self, op: Operand) -> np.ndarray:
        """Resolve one operand to a float64 array aligned with the frame."""
        if op.type == "const":
            arr = np.full(self.n, float(op.value))
        elif op.type == "price":
            field = op.field_name if op.field_name in self.df.columns else "close"
            arr = self.df[field].to_numpy(dtype=np.float64)
        elif op.type == "indicator":
            outputs = self.cache.get(op.name, op.params)
            key = op.output if op.output in outputs else next(iter(outputs))
            arr = outputs[key]
        else:
            raise ValueError(f"Unknown operand type: {op.type}")
        if op.shift > 0:
            arr = np.concatenate([np.full(op.shift, np.nan), arr[: -op.shift]])
        return arr


def _shift1(a: np.ndarray) -> np.ndarray:
    out = np.empty_like(a)
    out[0] = np.nan
    out[1:] = a[:-1]
    return out


def eval_condition(cond: Condition, ctx: EvalContext) -> np.ndarray:
    """Evaluate one condition to a boolean array (NaN-safe)."""
    left = ctx.resolve(cond.left)
    op = cond.op

    if op in ("rising", "falling"):
        prev = _shift1(left)
        with np.errstate(invalid="ignore"):
            res = left > prev if op == "rising" else left < prev
        return np.nan_to_num(res.astype(np.float64), nan=0.0).astype(bool) & ~np.isnan(left) & ~np.isnan(prev)

    right = ctx.resolve(cond.right)
    valid = ~np.isnan(left) & ~np.isnan(right)

    with np.errstate(invalid="ignore"):
        if op == ">":
            res = left > right
        elif op == "<":
            res = left < right
        elif op == ">=":
            res = left >= right
        elif op == "<=":
            res = left <= right
        elif op in ("cross_above", "cross_below"):
            pl, pr = _shift1(left), _shift1(right)
            pvalid = ~np.isnan(pl) & ~np.isnan(pr)
            if op == "cross_above":
                res = (left > right) & (pl <= pr)
            else:
                res = (left < right) & (pl >= pr)
            valid &= pvalid
        else:
            raise ValueError(f"Unknown operator: {op}")

    return res & valid


def eval_conditions(conds: list[Condition], ctx: EvalContext) -> np.ndarray:
    """AND-combine a list of conditions. Empty list -> all False (no signal)."""
    if not conds:
        return np.zeros(ctx.n, dtype=bool)
    out = np.ones(ctx.n, dtype=bool)
    for c in conds:
        out &= eval_condition(c, ctx)
    return out


def time_filter_mask(tf: TimeFilter, index: pd.DatetimeIndex) -> np.ndarray:
    """Boolean mask of bars where entries are allowed."""
    if not tf.enabled:
        return np.ones(len(index), dtype=bool)
    days = np.asarray(index.dayofweek)
    hours = np.asarray(index.hour)
    mask = np.isin(days, np.asarray(tf.days, dtype=days.dtype))
    if tf.start_hour <= tf.end_hour:
        mask &= (hours >= tf.start_hour) & (hours < tf.end_hour)
    else:  # overnight session, e.g. 22 -> 6
        mask &= (hours >= tf.start_hour) | (hours < tf.end_hour)
    return mask
