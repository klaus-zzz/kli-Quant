"""Tushare 日线固定快照；价格十进制文本、不补零、不隐式复权。"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx
from fina_agent.agent.contracts import ToolError, result
from fina_agent.agent.storage import RunStore, json_bytes
from fina_agent.models import utcnow

from kli_quant.config import Settings
from kli_quant.contracts import MarketSnapshot

FIELDS = ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"]
UNITS = {
    "open": "CNY/share",
    "high": "CNY/share",
    "low": "CNY/share",
    "close": "CNY/share",
    "vol": "100 shares",
    "amount": "1000 CNY",
}


def validate_rows(rows: list[dict], args: MarketSnapshot, as_of: datetime) -> list[dict]:
    """过滤尚未完成的日期并检查数值和价格关系，缺失值保留 null。"""
    latest = as_of.astimezone(ZoneInfo("Asia/Shanghai")).date()
    if args.start > args.end or args.end >= latest or (args.end - args.start).days > 366:
        raise ToolError("outside_time_boundary")
    validated, seen = [], set()
    for row in rows:
        try:
            day = datetime.strptime(row["trade_date"], "%Y%m%d").date()
            code = row["ts_code"]
            if code not in args.instrument_ids or not args.start <= day <= args.end:
                raise ValueError
            if (code, day) in seen:
                raise ValueError
            seen.add((code, day))
            parsed = {}
            for field in FIELDS[2:]:
                value = None if row.get(field) is None else Decimal(str(row[field]))
                if value is not None and (not value.is_finite() or value < 0):
                    raise ValueError
                parsed[field] = value
            if all(parsed[k] is not None for k in ["open", "high", "low", "close"]):
                if not (
                    0
                    < parsed["low"]
                    <= min(parsed["open"], parsed["close"])
                    <= max(parsed["open"], parsed["close"])
                    <= parsed["high"]
                ):
                    raise ValueError
            validated.append(
                {
                    "ts_code": code,
                    "trade_date": day.isoformat(),
                    **{k: str(v) if v is not None else None for k, v in parsed.items()},
                }
            )
        except (ValueError, KeyError, TypeError, InvalidOperation):
            raise ToolError("invalid_market_data") from None
    return sorted(validated, key=lambda row: (row["ts_code"], row["trade_date"]))


def get_market_snapshot(store: RunStore, args: MarketSnapshot, settings: Settings) -> dict:
    """相同查询复用固定版本，避免同轮计算悄悄换用修订数据。"""
    request = args.model_dump(mode="json")
    validate_rows([], args, store.run.as_of)
    for record in store.records("snapshot"):
        if record.data["request"] == request:
            quality = record.data["quality"]
            partial = quality["missing_values"] or record.data["coverage"]["missing_instruments"]
            return result(
                "partial" if partial else "ok",
                snapshot_result(record),
                limitations=record.data["limitations"],
                provenance=[record.id],
            )
    rows = []
    with httpx.Client(timeout=20, trust_env=False) as client:
        for code in args.instrument_ids:
            response = client.post(
                "https://api.tushare.pro",
                json={
                    "api_name": "daily",
                    "token": settings.tushare_token.get_secret_value(),
                    "params": {
                        "ts_code": code,
                        "start_date": args.start.strftime("%Y%m%d"),
                        "end_date": args.end.strftime("%Y%m%d"),
                    },
                    "fields": ",".join(FIELDS),
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                # 提供方原始错误可能包含请求参数或凭据，不转发。
                raise ToolError("provider_denied_or_unavailable")
            data = payload.get("data") or {}
            if data.get("fields") != FIELDS:
                raise ToolError("invalid_market_schema")
            for values in data.get("items", []):
                if len(values) != len(FIELDS):
                    raise ToolError("invalid_market_schema")
                rows.append(dict(zip(FIELDS, values, strict=True)))
    rows = validate_rows(rows, args, store.run.as_of)
    if not rows:
        return result("empty", [], limitations=["供应方未返回行情；不补零、不切换来源"])
    missing = [code for code in args.instrument_ids if not any(r["ts_code"] == code for r in rows)]
    nulls = any(value is None for row in rows for value in row.values())
    limitations = [
        "当前获取的历史日线，非当时已存档版本；不可宣称点时回测",
        "未校验交易日历；缺失日期可能为停牌或数据缺口，默认不填充",
    ]
    data = {
        "request": request,
        "provider": "tushare.daily",
        "fetched_at": utcnow().isoformat(),
        "schema": {
            "numeric": "decimal string",
            "units": UNITS,
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "date": "ISO-8601",
        },
        "coverage": {"rows": len(rows), "missing_instruments": missing},
        "quality": {
            "missing_values": nulls,
            "calendar_verified": False,
            "incomplete_bars": False,
            "point_in_time": False,
        },
        "adjustment_metadata": {"adjustment": "none", "factors": None},
        "limitations": limitations,
        "preview": rows[:5],
    }
    record = store.archive_record(
        "snapshot", json_bytes({**data, "rows": rows}), "application/json", data
    )
    return result(
        "partial" if missing or nulls else "ok",
        snapshot_result(record),
        limitations=limitations,
        provenance=[record.id],
    )


def snapshot_result(record) -> dict:
    """快照记录同时是归档下载入口，显式返回固定文件的哈希。"""
    return {
        "snapshot_id": record.id,
        "artifact_id": record.id,
        "content_hash": record.data["object"]["sha256"],
        **record.data,
    }
