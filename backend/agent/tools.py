"""沙箱使用的研究 HTTP 工具；归属和执行标识只从可信绑定获取。"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from backend.agent.execution import execute
from backend.research.api import principal, view
from backend.research.models import Model, ResearchError, ResultBundle

router = APIRouter(prefix="/api/research")


async def body(request, limit=131072):
    """限制传入内容且不回显原始校验错误。"""
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise ResearchError("request_too_large", 413)
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except ValueError:
        raise ResearchError("invalid_request", 422) from None


def binding(request, *, require_run=True):
    """会话身份和已核对归属的研究标识一起约束计算、预算和发布。"""
    row = request.scope.get("research_binding")
    if not row or (
        require_run and (row.get("run_id") is None or not row.get("sandbox_id"))
    ):
        raise ResearchError("research_identity_required", 403)
    runtime = request.app.state.agent
    if require_run:
        runtime.research.require_running(
            runtime.research.get(row["session_id"], row["run_id"])
        )
    return runtime, row


@router.get("/context")
def context(request: Request, owner=Depends(principal)):
    runtime, row = binding(request, require_run=False)
    if row.get("run_id") is None:
        return {"mode": "chat", "session_id": owner}
    run = runtime.research.get(owner, row["run_id"])
    return {
        "mode": "research",
        **view(run),
        "request": run["request"],
        # 复核直接取得旧判断和产物 ID，避免把新 run_id 当成旧结果查询目标。
        "previous_result": (
            runtime.research.result(owner, run["previous_run_id"])
            if run["previous_run_id"]
            else None
        ),
        "result_schema": ResultBundle.model_json_schema(),
        # JSON Schema 只描述报告字段；同时公开执行与引用的语义契约，供模型编写代码。
        "execution_contract": {
            "input": "{evidence_id: document}",
            "dataset_table": "document.response.data",
            "output": {
                "conventions": (
                    "与最终 Artifact 除 evidence_id、execution_id 外的字段严格一致，"
                    "含默认 null；inputs 顺序也一致"
                ),
                "observations": (
                    "非空数组，每项含 trade_date 和正数 close；"
                    "日期顺序等于 trading_dates，可添加计算值"
                ),
            },
            "stdout": (
                "只输出一个 JSON 对象；诊断信息写 stderr；"
                "检查 exit_code，失败后修改并重新执行"
            ),
            "artifact": (
                "使用本次 execute 返回的 output.evidence_id、execution.evidence_id "
                "和固定 inputs；不能关联旧代码输出"
            ),
        },
        "citation_rules": (
            "supports/counters 只接受 source 或 dataset，"
            "不能引用 output/code/execution。"
            "source 必须 available、published_at 已知且不晚于 cutoff，"
            "否则仅作探索并记录 gaps；"
            "不得从正文推断日期覆盖元数据。dataset 使用 table 或 row:从0开始的行号。"
            "计算输出通过 artifacts 关联。"
            "任一 hop 的 supports 为空时，必须用 insufficient_evidence 并写清 gaps。"
        ),
        "publish_feedback": (
            "草稿错误返回 errors 且 published=false；可在原截止前修正再发布。"
        ),
    }


class Source(Model):
    url: str = Field(min_length=1, max_length=2048)


class Execution(Model):
    code: str = Field(min_length=1, max_length=32768)
    inputs: list[UUID] = Field(min_length=1, max_length=30)


@router.post("/source")
async def source(request: Request, owner=Depends(principal)):
    runtime, row = await run_in_threadpool(binding, request)
    try:
        args = Source.model_validate(await body(request))
    except ValueError:
        raise ResearchError("invalid_request", 422) from None
    ref = await run_in_threadpool(
        runtime.research.collect_source, owner, row["run_id"], args.url
    )
    _, document = await run_in_threadpool(
        runtime.research.read_evidence, owner, row["run_id"], ref["evidence_id"]
    )
    return {
        "evidence": ref,
        "document": {k: v for k, v in document.items() if k != "raw_base64"},
    }


@router.get("/evidence/{evidence_id}")
def evidence(evidence_id: UUID, request: Request, owner=Depends(principal)):
    runtime, row = binding(request)
    ref, document = runtime.research.read_evidence(owner, row["run_id"], evidence_id)
    return {"kind": ref["kind"], "document": document}


@router.post("/execute")
async def execution(request: Request, owner=Depends(principal)):
    runtime, row = await run_in_threadpool(binding, request)
    try:
        args = Execution.model_validate(await body(request))
    except ValueError:
        raise ResearchError("invalid_request", 422) from None
    return await run_in_threadpool(execute, runtime, row, args.code, args.inputs)


@router.post("/publish")
async def publish(request: Request, owner=Depends(principal)):
    runtime, row = await run_in_threadpool(binding, request)
    draft = await body(request)
    # 草稿预检不产生正式版本；模型获得稳定错误后可修正，发布仍重新校验并持锁。
    _, errors = await run_in_threadpool(
        runtime.research.check_draft, owner, row["run_id"], draft
    )
    if errors:
        return {"error": "validation_failed", "errors": errors, "published": False}
    return await run_in_threadpool(
        runtime.research.publish, owner, row["run_id"], draft
    )
