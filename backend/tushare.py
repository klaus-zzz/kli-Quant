"""受控的 Tushare HTTP 入口；凭据仅在本模块执行请求时读取。"""

import asyncio
import json
import os
import time
from collections import deque
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request

from sandbox.cli.catalog import CONTRACTS, validate

router = APIRouter()
MAX_BYTES = 20 * 1024 * 1024
TIMEOUT = 60
# 单进程开发服务的硬预算；无自动重试或自动翻页。
_slots = asyncio.Semaphore(4)
_calls: deque[float] = deque()


def result(name, params, status, data=None, message=None, limits=None):
    """成功、失败和空结果使用同一信封，保留查询及来源信息。"""
    return {
        "status": status,
        "data": data,
        "message": message,
        "source": {"provider": "tushare", "api_name": name},
        "query": params,
        "fetched_at": datetime.now(UTC).isoformat(),
        "limits": {"auto_paginate": False, **(limits or {})},
    }


def error_status(code, message):
    """仅用上游消息分类，绝不把原始消息回显给调用方。"""
    if code == 429 or any(
        word in message for word in ("频率", "每分钟", "每小时", "每天最多")
    ):
        return "rate_limited"
    if code in (401, 403, 2002) or any(
        word in message for word in ("权限", "积分", "token", "Token")
    ):
        return "permission_denied"
    return "service_error"


async def fetch(name, params, fields, token):
    """限制总耗时、解压后大小并禁止跟随重定向。"""
    # 上游由后端环境配置，未设置时使用官方地址。
    upstream = os.environ.get("TUSHARE_BASE_URL", "https://api.tushare.pro")
    payload = {"api_name": name, "token": token, "params": params, "fields": fields}
    async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
        async with client.stream("POST", upstream, json=payload) as response:
            if response.status_code != 200:
                return result(name, params, error_status(response.status_code, ""))
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    return result(
                        name, params, "incomplete", message="响应超过大小上限"
                    )
    text = content.decode("utf-8")
    if token in text:
        return result(name, params, "service_error", message="上游响应包含敏感内容")
    body = json.loads(text)
    if token in json.dumps(body, ensure_ascii=False, allow_nan=False):
        return result(name, params, "service_error", message="上游响应包含敏感内容")
    if not isinstance(body, dict) or type(body.get("code")) is not int:
        raise ValueError("无效上游信封")
    if body["code"] != 0:
        return result(
            name, params, error_status(body["code"], str(body.get("msg", "")))
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise ValueError("无效上游数据")
    columns, rows = data.get("fields"), data.get("items")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ValueError("无效上游表格")
    known = {item["name"] for item in CONTRACTS[name]["output_fields"]}
    if any(not isinstance(c, str) or c not in known for c in columns):
        raise ValueError("上游字段与契约不符")
    if len(set(columns)) != len(columns) or any(
        not isinstance(r, list) or len(r) != len(columns) for r in rows
    ):
        raise ValueError("上游行列不匹配")
    if fields and set(fields.split(",")) - set(columns):
        return result(name, params, "incomplete", data, message="上游缺少所选字段")
    cap = CONTRACTS[name]["row_limit"]
    requested = int(params["limit"]) if "limit" in params else None
    thresholds = [v for v in (cap, requested) if v is not None]
    truncated = data.get("has_more") is True or bool(
        thresholds and len(rows) >= min(thresholds)
    )
    # 未公布上限时不能声称全量；数据仍原样返回并明确完整性未知。
    status = "incomplete" if truncated else "success" if rows else "empty"
    return result(
        name,
        params,
        status,
        data,
        limits={
            "row_limit": cap,
            "rows": len(rows),
            "completeness": "possibly_truncated" if truncated else "unknown",
        },
    )


@router.post("/api/tushare/{name}")
async def query(name: str, request: Request):
    """入口重复验证调用方输入，预算在发送真实请求之前扣减。"""
    params = {}
    try:
        # 手动读取有界请求，避免框架错误详情回显任意输入。
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 32768:
                raise ValueError("请求体过大")
        body = json.loads(raw)
        if not isinstance(body, dict) or body.keys() - {"params", "fields"}:
            raise ValueError("请求结构无效")
        params, fields = body.get("params", {}), body.get("fields", "")
        if not isinstance(params, dict):
            raise ValueError("参数必须是对象")
        validate(name, params, fields)
    except (ValueError, TypeError):
        return result(name, {}, "invalid_request", message="接口、参数或字段选择无效")
    runtime = getattr(request.app.state, "agent", None)
    if runtime is not None:
        # Agent 模式所有数据调用都扣当前研究预算并冻结证据，不能旁路普通入口。
        from starlette.concurrency import run_in_threadpool

        from backend.research.models import ResearchError

        binding = await run_in_threadpool(runtime.authorize_research, request)
        if binding.get("run_id") is None:
            raise ResearchError("research_identity_required", 403)
        owner, run_id = binding["session_id"], binding["run_id"]
        ref = await runtime.research.collect_dataset(
            owner, run_id, name, params, fields
        )
        _, document = await run_in_threadpool(
            runtime.research.read_evidence, owner, run_id, ref["evidence_id"]
        )
        return {**document["response"], "evidence": ref}
    return await execute_query(name, params, fields)


async def execute_query(name, params, fields=""):
    """HTTP 和研究快照共用白名单、凭据及请求限制，避免旁路调用。"""
    try:
        validate(name, params, fields)
    except (ValueError, TypeError):
        return result(name, {}, "invalid_request", message="接口、参数或字段选择无效")
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        return result(name, params, "not_configured", message="后端未配置数据源凭据")
    if token in json.dumps(params, ensure_ascii=False):
        return result(name, {}, "invalid_request", message="请求包含敏感内容")
    now = time.monotonic()
    while _calls and _calls[0] <= now - 60:
        _calls.popleft()
    if len(_calls) >= 30:
        return result(
            name, params, "budget_exceeded", message="每分钟最多 30 次上游请求"
        )
    if _slots.locked():
        return result(name, params, "busy", message="后端并发已满")
    _calls.append(now)
    try:
        async with _slots, asyncio.timeout(TIMEOUT):
            return await fetch(name, params, fields, token)
    except (TimeoutError, httpx.TimeoutException):
        return result(name, params, "timeout")
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return result(name, params, "service_error", message="数据源响应无效或暂不可用")
