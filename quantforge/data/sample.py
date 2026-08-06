"""Deterministic synthetic market data.

A seeded regime-switching random walk produces realistic OHLCV series so the
app is useful out of the box, works offline, and every run reproduces the
exact same bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_sample(
    symbol: str = "DEMO",
    start: str = "2021-01-01",
    bars: int = 26_000,
    timeframe_minutes: int = 60,
    start_price: float = 100.0,
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate a deterministic OHLCV frame.

    The seed defaults to a hash of the symbol so each symbol gets its own —
    but always identical — history.
    """
    if seed is None:
        seed = abs(hash_symbol(symbol)) % (2**31)
    rng = np.random.default_rng(seed)

    # regime-switching drift/vol: trending up, ranging, trending down
    n = bars
    regime_len = rng.integers(200, 900, size=n // 200 + 2)
    drifts, vols = [], []
    for length in regime_len:
        regime = rng.integers(0, 3)
        drift = (0.00012, 0.0, -0.00010)[regime]
        vol = rng.uniform(0.0035, 0.0095)
        drifts.append(np.full(length, drift))
        vols.append(np.full(length, vol))
        if sum(len(d) for d in drifts) >= n:
            break
    drift = np.concatenate(drifts)[:n]
    vol = np.concatenate(vols)[:n]

    log_ret = drift + vol * rng.standard_normal(n)
    close = start_price * np.exp(np.cumsum(log_ret))
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]

    span = np.abs(rng.standard_normal(n)) * vol * close * 0.8
    high = np.maximum(open_, close) + span * rng.uniform(0.2, 1.0, n)
    low = np.minimum(open_, close) - span * rng.uniform(0.2, 1.0, n)
    volume = (rng.lognormal(mean=10.0, sigma=0.6, size=n)).round(0)

    idx = pd.date_range(start=start, periods=n, freq=f"{timeframe_minutes}min")
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    return df.round(5)


def hash_symbol(symbol: str) -> int:
    """Stable cross-run hash (Python's ``hash`` is salted per process)."""
    h = 2166136261
    for ch in symbol.encode():
        h = (h ^ ch) * 16777619 % (2**32)
    return h


BUILTIN_SAMPLES: dict[str, dict] = {
    "EURUSD (sample 1h)": dict(symbol="EURUSD", start="2021-01-01", bars=26_000,
                               timeframe_minutes=60, start_price=1.10),
    "BTCUSD (sample 1h)": dict(symbol="BTCUSD", start="2021-01-01", bars=26_000,
                               timeframe_minutes=60, start_price=30_000.0),
    "SPX (sample 1d)": dict(symbol="SPX", start="2010-01-01", bars=3_900,
                            timeframe_minutes=1440, start_price=1_100.0),
}
