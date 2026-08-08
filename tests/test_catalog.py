"""Instrument catalogue: entries are well-formed and readiness is honest."""

from __future__ import annotations

import pandas as pd

from botiquant.data.catalog import BY_KEY, CATALOG, to_server_time


def test_catalog_entries_complete():
    keys = {c["key"] for c in CATALOG}
    assert {"sp500", "eurusd", "xauusd", "btcusd"} <= keys
    for c in CATALOG:
        assert c["spread"] > 0 and c["slippage"] >= 0
        assert c["dukascopy"] and c["category"] and c["full_name"]
        assert BY_KEY[c["key"]] is c


def test_server_time_shift():
    idx = pd.date_range("2024-06-03 12:00", periods=3, freq="1min")  # UTC
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                      index=idx)
    out = to_server_time(df)
    # June => New York is UTC-4, +7 server offset => UTC+3
    assert out.index[0] == pd.Timestamp("2024-06-03 15:00")
    assert len(out) == len(df)


def test_sample_datasets_never_count_as_ready(client_with_sample):
    """A synthetic dataset named EURUSD must not mark the instrument downloaded."""
    catalog = client_with_sample.get("/api/catalog").json()
    eurusd = next(c for c in catalog if c["key"] == "eurusd")
    assert eurusd["dataset_id"] is None, "sample data must not be reported as real history"
