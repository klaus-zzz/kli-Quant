"""检查可验证的来源与计算契约，不把结构检查当成投资判断证明。"""

from datetime import UTC, datetime
from math import isfinite

from backend.research.models import ResearchError
from sandbox.cli.catalog import CONTRACTS

TIME_FIELDS = {"trade_date", "ann_date", "f_ann_date", "end_date", "cal_date"}


def required_time_fields(name):
    """从现有工具契约取日期字段，字段筛选不能移除截止点校验依据。"""
    return sorted(
        TIME_FIELDS
        & {f["name"] for f in CONTRACTS.get(name, {}).get("output_fields", [])}
    )


def dataset_times(document, cutoff):
    """保留各日期字段；历史接口今天返回的数据不自动具备历史可得性。"""
    response = document["response"]
    table = response.get("data") or {}
    fields = table.get("fields", [])
    dates = {}
    for index, field in enumerate(fields):
        if field in TIME_FIELDS:
            dates[field] = sorted(
                {str(r[index]) for r in table.get("items", []) if r[index]}
            )
    limit = cutoff.strftime("%Y%m%d")
    future = any(v > limit for values in dates.values() for v in values)
    return {
        "status": response["status"],
        "dates": dates,
        "future": future,
        "time_fields_complete": set(required_time_fields(document.get("api_name")))
        <= set(fields),
        "fetched_at": response["fetched_at"],
        "availability_basis": "observed_at_fetch",
        "completeness": response.get("limits", {}).get("completeness", "unknown"),
    }


def validate_bundle(bundle, run, evidence, previous_hops):
    """所有引用读取都经过归属与摘要检查，逐项返回稳定错误分类。"""
    errors = []
    if not bundle.valid_from.tzinfo or not bundle.valid_until.tzinfo:
        errors.append("timezone_required")
    elif bundle.valid_until <= bundle.valid_from or bundle.valid_from > run["cutoff"]:
        errors.append("invalid_time_scope")
    seen = set()
    for hop in bundle.hops:
        if hop.id in seen or any(parent not in seen for parent in hop.parents):
            errors.append("invalid_hop_graph")
        seen.add(hop.id)
        if not hop.supports and not hop.gaps:
            errors.append("unsupported_judgment")
        if bundle.conclusion != "insufficient_evidence" and not hop.supports:
            errors.append("evidence_required")
        for citation in [*hop.supports, *hop.counters]:
            try:
                ref, document = evidence(citation.evidence_id)
                check_citation(ref, document, citation.locator, run["cutoff"])
            except ResearchError as exc:
                errors.append(exc.code)
    if run["previous_run_id"]:
        if not bundle.revisions or any(
            r.hop_id not in previous_hops for r in bundle.revisions
        ):
            errors.append("revision_reason_required")
    elif bundle.revisions:
        errors.append("unexpected_revision")
    for artifact in bundle.artifacts:
        try:
            check_artifact(artifact, run, evidence)
        except ResearchError as exc:
            errors.append(exc.code)
    return sorted(set(errors))


def check_citation(ref, document, locator, cutoff):
    """引用定位必须指向真实固定内容，缺时间的原文只能作为探索线索。"""
    if ref["kind"] == "source":
        if document["status"] != "available":
            raise ResearchError("source_unavailable")
        published = document.get("published_at")
        if not published:
            raise ResearchError("publication_time_unknown")
        if datetime.fromisoformat(published) > cutoff:
            raise ResearchError("future_source")
        if locator not in {b["locator"] for b in document["blocks"]}:
            raise ResearchError("invalid_locator")
    elif ref["kind"] == "dataset":
        meta = ref["metadata"]
        if meta["future"]:
            raise ResearchError("future_dataset")
        if not meta.get("time_fields_complete", False):
            raise ResearchError("time_fields_missing")
        if meta["status"] not in {"success", "empty"}:
            raise ResearchError("dataset_not_complete")
        table = document["response"].get("data") or {}
        count = len(table.get("items", []))
        if locator == "table" or (
            locator.startswith("row:")
            and locator[4:].isdigit()
            and 0 <= int(locator[4:]) < count
        ):
            return
        raise ResearchError("invalid_locator")
    else:
        raise ResearchError("invalid_citation_kind")


def check_artifact(artifact, run, evidence):
    """计算产物绑定可信执行；正式回测额外要求历史可得性证据。"""
    execution_ref, execution = evidence(artifact.execution_id)
    output_ref, output = evidence(artifact.evidence_id)
    if execution_ref["kind"] != "execution" or output_ref["kind"] != "output":
        raise ResearchError("execution_kind_mismatch")
    if execution["exit_code"] != 0:
        raise ResearchError("execution_failed")
    if execution["output_id"] != str(artifact.evidence_id) or set(
        execution["input_ids"]
    ) != {str(i) for i in artifact.inputs}:
        raise ResearchError("execution_input_mismatch")
    for evidence_id, expected in execution["items"].items():
        ref, _ = evidence(evidence_id)
        if ref["sha256"] != expected["sha256"]:
            raise ResearchError("execution_content_mismatch")
    # 输出本身必须携带相同口径，避免报告字段与实际计算输出脱节。
    expected = artifact.model_dump(mode="json", exclude={"evidence_id", "execution_id"})
    if not isinstance(output, dict) or output.get("conventions") != expected:
        raise ResearchError("output_conventions_mismatch")
    observations = output.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ResearchError("output_data_required")
    # 正式输出必须包含有界数值及对应交易日，只有口径标签不算计算结果。
    if (
        any(
            not isinstance(row, dict)
            or type(row.get("close")) not in {int, float}
            or not isfinite(row["close"])
            or row["close"] <= 0
            for row in observations
        )
        or [row.get("trade_date") for row in observations] != artifact.trading_dates
    ):
        raise ResearchError("invalid_output_data")
    if artifact.calendar_id not in artifact.inputs:
        raise ResearchError("calendar_input_required")
    calendar_ref, calendar = evidence(artifact.calendar_id)
    if calendar_ref["kind"] != "dataset" or calendar.get("api_name") != "trade_cal":
        raise ResearchError("calendar_required")
    table = calendar["response"].get("data") or {}
    rows = [dict(zip(table.get("fields", []), r)) for r in table.get("items", [])]
    open_days = {r.get("cal_date") for r in rows if str(r.get("is_open")) == "1"}
    days = artifact.trading_dates
    if days != sorted(set(days)) or not set(days) <= open_days:
        raise ResearchError("invalid_trading_dates")
    for day in days:
        try:
            parsed = datetime.strptime(day, "%Y%m%d").replace(tzinfo=UTC)
        except ValueError:
            raise ResearchError("invalid_trading_dates") from None
        if parsed > run["cutoff"]:
            raise ResearchError("future_artifact")
    if artifact.adjustment != "none":
        if artifact.adjustment_factor_id not in artifact.inputs:
            raise ResearchError("adjustment_factor_required")
        _, factor = evidence(artifact.adjustment_factor_id)
        if factor.get("api_name") != "adj_factor":
            raise ResearchError("adjustment_factor_required")
    for evidence_id in artifact.inputs:
        ref, document = evidence(evidence_id)
        if ref["kind"] == "dataset":
            check_citation(ref, document, "table", run["cutoff"])
        else:
            raise ResearchError("unsupported_artifact_input")
        if artifact.kind == "backtest":
            fetched = datetime.fromisoformat(ref["metadata"]["fetched_at"])
            first_day = datetime.strptime(days[0], "%Y%m%d").replace(tzinfo=UTC)
            if fetched >= first_day:
                raise ResearchError("historical_availability_unverified")
