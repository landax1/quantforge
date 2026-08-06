"""Shared fixtures."""

from __future__ import annotations

import pytest

from quantforge.core.models import Condition, Operand, RiskConfig, StrategySpec
from quantforge.data.sample import generate_sample


@pytest.fixture(scope="session")
def df():
    return generate_sample("TEST", bars=5000, start_price=100.0)


@pytest.fixture()
def client_with_sample(tmp_path):
    """API client whose workspace holds one synthetic EURUSD dataset."""
    from fastapi.testclient import TestClient

    from quantforge.api.app import create_app

    app = create_app(workdir=tmp_path)
    with TestClient(app) as c:
        c.post("/api/datasets/sample", json={"symbol": "EURUSD", "bars": 1000})
        yield c


@pytest.fixture()
def ema_spec() -> StrategySpec:
    def ema(period: float) -> Operand:
        return Operand(type="indicator", name="EMA", params={"period": period})

    return StrategySpec(
        name="EMA cross",
        direction="both",
        entry_long=[Condition(ema(20), "cross_above", ema(80))],
        entry_short=[Condition(ema(20), "cross_below", ema(80))],
        risk=RiskConfig(stop_type="atr", stop_value=2.0, target_type="atr", target_value=3.0),
    )
