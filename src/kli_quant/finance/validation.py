"""正式产物重算核心指标；校验通过仅说明口径一致，不证明投资逻辑成立。"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fina_agent.agent.contracts import StrictModel, ToolError
from fina_agent.agent.storage import RunStore
from pydantic import Field

from kli_quant.finance.contracts import Finish


class Calculation(StrictModel):
    """第一版正式计算只支持可独立重算的区间收益比较。"""

    purpose: Literal["signal", "backtest"]
    method: Literal["close_return"]
    snapshot_id: str
    instrument_id: str
    start: date
    end: date
    value: Decimal = Field(allow_inf_nan=False)
    unit: Literal["ratio"]
    price_basis: Literal["unadjusted_close"]
    currency: Literal["CNY"]
    timezone: Literal["Asia/Shanghai"]
    time_basis: Literal["historical_reconstruction"]
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    benchmark: str | None = None
    benchmark_value: Decimal | None = Field(default=None, allow_inf_nan=False)


def evidence_refs(store: RunStore, ids: list[str], *, formal: bool) -> list:
    """引用须属于当前执行；正式结果只接受截止点前已公开的可定位原文。"""
    records = []
    for reference in ids:
        row = store.require(reference, {"evidence"})
        published = row.data.get("published_at")
        if formal and (not published or datetime.fromisoformat(published) > store.run.as_of):
            raise ToolError("evidence_time_unknown_or_future")
        records.append(row)
    return records


def validate_calculation(store: RunStore, content: bytes, purpose: str, execution) -> dict:
    """从归档快照重算收益，不信任沙箱自报的数字或引用。"""
    calculation = Calculation.model_validate_json(content)
    if calculation.purpose != purpose:
        raise ToolError("purpose_mismatch")
    snapshot = store.require(calculation.snapshot_id, {"snapshot"})
    if calculation.snapshot_id not in execution.data["input_refs"]:
        raise ToolError("input_not_executed")
    evidence_refs(store, calculation.evidence_ids, formal=True)
    payload = json.loads(store.archive.get(snapshot.data["object"]))
    if (
        snapshot.data["quality"]["missing_values"]
        or snapshot.data["coverage"]["missing_instruments"]
    ):
        raise ToolError("incomplete_snapshot")
    latest = store.run.as_of.astimezone(ZoneInfo("Asia/Shanghai")).date()
    if not calculation.start < calculation.end < latest:
        raise ToolError("invalid_calculation_dates")

    def actual_return(code: str) -> Decimal:
        prices = {
            row["trade_date"]: row["close"] for row in payload["rows"] if row["ts_code"] == code
        }
        try:
            first = Decimal(prices[calculation.start.isoformat()])
            last = Decimal(prices[calculation.end.isoformat()])
            return last / first - 1
        except (KeyError, TypeError, ArithmeticError):
            raise ToolError("missing_calculation_prices") from None

    computed = actual_return(calculation.instrument_id)
    if abs(computed - calculation.value) > Decimal("0.00000001"):
        raise ToolError("calculation_mismatch")
    if purpose == "backtest" and not calculation.benchmark:
        raise ToolError("benchmark_required")
    if calculation.benchmark:
        if calculation.benchmark_value is None or abs(
            actual_return(calculation.benchmark) - calculation.benchmark_value
        ) > Decimal("0.00000001"):
            raise ToolError("benchmark_mismatch")
    elif calculation.benchmark_value is not None:
        raise ToolError("benchmark_required")
    return {
        "calculation": calculation.model_dump(mode="json"),
        "checks": ["references", "time", "units", "price_basis", "recomputed_return"],
        "limitations": [
            "仅历史区间收益比较，非策略回测或可交易收益",
            "不复权，可能受分红拆股影响；不含费用和滑点",
            "历史重建数据不能证明无前视偏差",
        ],
    }


def validate_finish(store: RunStore, args: Finish, calls: list) -> dict:
    """缺口可以结束研究，正式观察必须完成正反查证、行情及计算校验。"""
    if set(args.support) & set(args.contradict):
        raise ToolError("conflicting_evidence_roles")
    formal = args.outcome == "observation"
    evidence_refs(store, args.support + args.contradict, formal=formal)
    artifacts = [store.require(reference, {"artifact"}) for reference in args.artifact_ids]
    if formal or args.outcome == "no_opportunity":
        directions = {
            call.arguments.get("stance", "neutral")
            for call in calls
            if call.name == "search_evidence"
            and call.result
            and call.result["status"] in {"ok", "partial", "empty"}
        }
        if not {"support", "contradict"}.issubset(directions):
            raise ToolError("both_evidence_directions_required")
        if not args.support and not args.contradict:
            raise ToolError("evidence_required")
    if formal:
        if not args.support or not args.conditions:
            raise ToolError("conditional_support_required")
        if not any(
            row.data["validation"] == "validated" and row.data["purpose"] == "signal"
            for row in artifacts
        ):
            raise ToolError("validated_signal_artifact_required")
    return {
        **args.model_dump(mode="json"),
        "outcome_label": {
            "observation": "条件性观察",
            "no_opportunity": "没有发现机会",
            "insufficient_evidence": "证据不足",
        }[args.outcome],
        "research_complete": True,
        "evidence_sufficient": formal,
        "signal_usable": formal,
        "fact_type": "conditional_inference" if formal else "research_conclusion",
        "reviewed_judgment_ids": store.run.input.get("review_judgment_ids", []),
    }
