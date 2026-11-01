"""拒绝伪造引用、错误单位、失配收益和未查证的观察。"""

import json
from datetime import UTC, datetime

import pytest
from fina_agent.agent.contracts import ToolError
from fina_agent.agent.storage import json_bytes
from pydantic import ValidationError

from kli_quant.contracts import Finish
from kli_quant.validation import validate_calculation, validate_finish


def calculation_fixture(store):
    """虚构价格只用于证明校验器独立重算，不作为真实业务结果。"""
    store.run.as_of = datetime(2026, 11, 1, tzinfo=UTC)
    evidence = store.add("evidence", {"published_at": "2026-10-01T00:00:00+00:00"})
    snapshot = store.archive_record(
        "snapshot",
        json_bytes(
            {
                "rows": [
                    {"ts_code": "600000.SH", "trade_date": "2026-10-20", "close": "10"},
                    {"ts_code": "600000.SH", "trade_date": "2026-10-21", "close": "11"},
                ]
            }
        ),
        "application/json",
        {"quality": {"missing_values": False}, "coverage": {"missing_instruments": []}},
    )
    execution = store.add("execution", {"input_refs": [snapshot.id]})
    value = {
        "purpose": "signal",
        "method": "close_return",
        "snapshot_id": snapshot.id,
        "instrument_id": "600000.SH",
        "start": "2026-10-20",
        "end": "2026-10-21",
        "value": "0.1",
        "unit": "ratio",
        "price_basis": "unadjusted_close",
        "currency": "CNY",
        "timezone": "Asia/Shanghai",
        "time_basis": "historical_reconstruction",
        "evidence_ids": [evidence.id],
    }
    return value, execution


def test_recompute_and_reference_ownership(store):
    value, execution = calculation_fixture(store)
    assert (
        "recomputed_return"
        in validate_calculation(store, json_bytes(value), "signal", execution)["checks"]
    )
    with pytest.raises(ToolError, match="calculation_mismatch"):
        validate_calculation(store, json_bytes({**value, "value": "10"}), "signal", execution)
    with pytest.raises(ToolError, match="unauthorized_reference"):
        validate_calculation(
            store, json_bytes({**value, "evidence_ids": ["invented"]}), "signal", execution
        )
    with pytest.raises(ValidationError):
        validate_calculation(store, json_bytes({**value, "unit": "percent"}), "signal", execution)


def test_backtest_requires_explicit_benchmark(store):
    value, execution = calculation_fixture(store)
    value["purpose"] = "backtest"
    with pytest.raises(ToolError, match="benchmark_required"):
        validate_calculation(store, json_bytes(value), "backtest", execution)


def test_no_opportunity_requires_both_directions(store):
    with pytest.raises(ToolError, match="both_evidence_directions_required"):
        validate_finish(store, Finish(outcome="no_opportunity", conclusion="无机会"), [])
    data = validate_finish(
        store, Finish(outcome="insufficient_evidence", conclusion="原文无法获取"), []
    )
    assert data["signal_usable"] is False


def test_empty_searches_cannot_prove_no_opportunity(store):
    from types import SimpleNamespace

    calls = [
        SimpleNamespace(
            name="search_evidence", arguments={"stance": stance}, result={"status": "empty"}
        )
        for stance in ("support", "contradict")
    ]
    with pytest.raises(ToolError, match="evidence_required"):
        validate_finish(store, Finish(outcome="no_opportunity", conclusion="没有机会"), calls)


def test_unknown_time_prevents_formal_observation(store):
    value, execution = calculation_fixture(store)
    evidence = store.require(value["evidence_ids"][0], {"evidence"})
    evidence.data = {"published_at": None}
    with pytest.raises(ToolError, match="evidence_time_unknown_or_future"):
        validate_calculation(store, json.dumps(value).encode(), "signal", execution)


def test_calculation_uses_shanghai_day_at_utc_midnight_boundary(store):
    value, execution = calculation_fixture(store)
    store.run.as_of = datetime(2026, 10, 21, 17, tzinfo=UTC)  # 上海已是 22 日。
    assert validate_calculation(store, json_bytes(value), "signal", execution)["checks"]
