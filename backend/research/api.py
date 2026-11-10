"""四个研究 HTTP 能力；可信身份和执行器接线缺失时明确拒绝。"""

import json
from uuid import UUID

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.research.models import ResearchError, Submission

router = APIRouter(prefix="/api/research/runs")


def principal(request: Request):
    """只信任认证中间件注入的 scope；普通 Header 和正文均无效。"""
    owner = request.scope.get("research_owner")
    runtime = getattr(request.app.state, "agent", None)
    if owner is None and runtime is not None:
        binding = runtime.authorize_research(request)
        request.scope["research_binding"] = binding
        owner = binding["session_id"]
    if not isinstance(owner, str) or not owner:
        raise ResearchError("identity_not_ready", 503)
    return owner


def service(request: Request):
    research = getattr(request.app.state, "research_service", None)
    if research is None:
        raise ResearchError("executor_not_ready", 503)
    return research


def view(run):
    """只返回业务状态，隐藏内部幂等键、归属、原始输入和存储配置。"""
    return {
        "run_id": str(run["id"]),
        **{
            k: run[k]
            for k in (
                "status",
                "stage",
                "error",
                "cutoff",
                "deadline",
                "max_calls",
                "used_calls",
            )
        },
    }


@router.post("")
async def submit(request: Request, owner=Depends(principal), research=Depends(service)):
    """限制请求体；Pydantic 错误不回显用户输入。"""
    from starlette.concurrency import run_in_threadpool

    key = request.headers.get("Idempotency-Key", "")
    if not key or len(key) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ResearchError("invalid_idempotency_key", 422)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 32768:
            raise ResearchError("request_too_large", 413)
    try:
        body = Submission.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        raise ResearchError("invalid_request", 422) from None
    run, created = await run_in_threadpool(research.submit, owner, key, body)
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        jsonable_encoder(view(run)), status_code=202 if created else 200
    )


@router.get("/{run_id}")
def get_run(run_id: UUID, owner=Depends(principal), research=Depends(service)):
    return view(research.get(owner, run_id))


@router.post("/{run_id}/cancel")
def cancel(run_id: UUID, owner=Depends(principal), research=Depends(service)):
    return view(research.cancel(owner, run_id))


@router.get("/{run_id}/result")
def get_result(run_id: UUID, owner=Depends(principal), research=Depends(service)):
    return research.result(owner, run_id)


def install_handlers(app):
    """异常只输出稳定分类，数据库连接字符串和 S3 密钥不会回显。"""

    async def business_error(request, exc):
        if request.url.path.startswith("/api/agent/cube/"):
            # 官方 e2b SDK 的错误解析要求 code/message，不回显底层异常正文。
            return JSONResponse(
                {"code": exc.status, "message": exc.code}, status_code=exc.status
            )
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    async def storage_error(request, exc):
        return JSONResponse({"error": "research_storage_unavailable"}, status_code=503)

    app.add_exception_handler(ResearchError, business_error)
    for kind in (psycopg.Error, BotoCoreError, ClientError):
        app.add_exception_handler(kind, storage_error)
