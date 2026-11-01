"""金融时间、单位和权限边界的回归。"""

from datetime import UTC, datetime

import pytest
from fina_agent.agent.contracts import ToolError
from pydantic import ValidationError

from kli_quant.contracts import MarketSnapshot
from kli_quant.market import validate_rows


def test_market_time_units_and_missing_values():
    args = MarketSnapshot(instrument_ids=["600000.SH"], start="2026-10-01", end="2026-10-30")
    row = {
        "ts_code": "600000.SH",
        "trade_date": "20261030",
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10.5,
        "vol": None,
        "amount": 123,
    }
    output = validate_rows([row], args, datetime(2026, 11, 1, tzinfo=UTC))
    assert output[0]["vol"] is None
    assert output[0]["close"] == "10.5"
    with pytest.raises(ToolError, match="outside_time_boundary"):
        validate_rows([row], args, datetime(2026, 10, 30, tzinfo=UTC))
    with pytest.raises(ToolError, match="invalid_market_data"):
        validate_rows([{**row, "close": float("nan")}], args, datetime(2026, 11, 1, tzinfo=UTC))


def test_model_cannot_change_permission_or_adjustment():
    with pytest.raises(ValidationError):
        MarketSnapshot(
            instrument_ids=["600000.SH"],
            start="2026-10-01",
            end="2026-10-02",
            frequency="1m",
            token="not-allowed",
        )
