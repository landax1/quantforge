"""Indicator correctness and hygiene checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from botiquant.indicators.base import REGISTRY, IndicatorCache


def test_registry_complete():
    expected = {"SMA", "EMA", "RSI", "MACD", "ATR", "ADX", "VWAP", "Donchian",
                "Bollinger", "CCI", "Stochastic", "Supertrend", "Ichimoku",
                "VolumeSMA", "Momentum"}
    assert expected <= set(REGISTRY)


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_outputs_aligned_and_finite_tail(df, name):
    cls = REGISTRY[name]
    out = cls.compute(df, **{p.name: p.default for p in cls.params})
    assert set(out) == set(cls.outputs)
    for key, arr in out.items():
        assert len(arr) == len(df), f"{name}.{key} misaligned"
        # after warm-up the tail must be finite
        tail = arr[-100:]
        assert np.isfinite(tail).all(), f"{name}.{key} has NaN in tail"


def test_sma_matches_pandas(df):
    out = REGISTRY["SMA"].compute(df, period=10)["value"]
    expected = df["close"].rolling(10).mean().to_numpy()
    np.testing.assert_allclose(out[20:], expected[20:], rtol=1e-10)


def test_rsi_bounds(df):
    rsi = REGISTRY["RSI"].compute(df, period=14)["value"]
    valid = rsi[~np.isnan(rsi)]
    assert (valid >= 0).all() and (valid <= 100).all()


def test_donchian_excludes_current_bar(df):
    out = REGISTRY["Donchian"].compute(df, period=20)
    i = 500
    window_high = df["high"].iloc[i - 20:i].max()   # excludes bar i
    assert out["upper"][i] == pytest.approx(window_high)


def test_supertrend_direction_is_pm_one(df):
    d = REGISTRY["Supertrend"].compute(df, period=10, mult=3.0)["direction"]
    valid = d[~np.isnan(d)]
    assert set(np.unique(valid)) <= {-1.0, 1.0}


def test_cache_reuses_computation(df):
    cache = IndicatorCache(df)
    a = cache.get("EMA", {"period": 21})
    b = cache.get("EMA", {"period": 21.0})
    assert a is b   # identical params -> same object


def test_no_lookahead_ema(df):
    """Truncating the frame must not change earlier EMA values."""
    full = REGISTRY["EMA"].compute(df, period=30)["value"]
    part = REGISTRY["EMA"].compute(df.iloc[:1000], period=30)["value"]
    np.testing.assert_allclose(full[:1000], part, rtol=1e-12, equal_nan=True)
