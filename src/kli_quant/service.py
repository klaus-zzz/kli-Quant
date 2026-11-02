"""独立金融 HTTP 服务：复用通用执行库，金融任务只在本服务运行。"""

import hashlib
import secrets
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fina_agent.agent.storage import Archive, json_bytes
from fina_agent.api import ResearchInput, enqueue_run, run_detail
from fina_agent.applications import get_application
from fina_agent.chat_store import job_data
from fina_agent.main import create_app
from fina_agent.models import Conversation, Record, Run, utcnow
from fina_agent.remote_contracts import TaskSnapshot, TaskSubmission
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kli_quant.config import Settings


def require_scope(x_task_scope: Annotated[UUID, Header()]):
    """服务认证通过后仍检查资源归属，知道任务编号不能跨会话操作。"""
    return str(x_task_scope)


def owned_run(session, task_id, scope):
    run = session.get(Run, str(task_id))
    if not run or run.conversation_id != scope:
        raise HTTPException(404, "task_not_found")
    return run


def reference(record):
    """归档对象按原始字节引用；结构化记录按稳定 JSON 字节引用。"""
    obj = record.data.get("object")
    content = json_bytes(record.data) if obj is None else None
    return {
        "id": record.id,
        "kind": record.kind,
        "media_type": obj.get("media_type", "application/octet-stream")
        if obj
        else "application/json",
        "sha256": obj["sha256"] if obj else hashlib.sha256(content).hexdigest(),
        "size": obj["size"] if obj else len(content),
    }


def snapshot(session, run):
    """推送与查询共用同一状态投影，摘要不能替代完整证据和固定结果。"""
    card = job_data(session, run)
    records = list(
        session.scalars(select(Record).where(Record.run_id == run.id).order_by(Record.created_at))
    )
    judgment = card["judgment"]
    data = TaskSnapshot(
        task_id=run.id,
        scope_id=run.conversation_id,
        status=run.status,
        created_at=run.as_of,
        revision="0" * 64,
        summary=str(judgment.get("conclusion", ""))[:4000] if judgment else "",
        progress={
            key: card[key] for key in ("last_tool", "stop_reason", "research_id", "parent_run_id")
        },
        result_refs=[reference(record) for record in records],
    ).model_dump(mode="json")
    data["revision"] = hashlib.sha256(
        json_bytes({k: v for k, v in data.items() if k != "revision"})
    ).hexdigest()
    return data


def create_service(settings=None):
    """所有研究和归档接口均需服务凭据；浏览器经底座代理，不接触令牌。"""
    settings = settings or Settings()
    if not settings.http_tool_token:
        raise RuntimeError("financial_http_token_not_configured")
    # 只复用生命周期和健康检查，不继承未经 scope 检查的 HTTP/WebSocket 路由。
    app = create_app(settings, trusted_hosts=["*"], include_api=False)

    @app.middleware("http")
    async def authenticate(request, call_next):
        if request.url.path != "/api/health":
            expected = "Bearer " + settings.http_tool_token.get_secret_value()
            supplied = request.headers.get("authorization", "")
            if not secrets.compare_digest(supplied.encode(), expected.encode()):
                return JSONResponse(status_code=401, content={"detail": "service_auth_required"})
            # 旧 HTTP 接口只在原运行库中保留；独立金融服务只公开有 scope 检查的 v1。
            if not request.url.path.startswith("/v1/"):
                return JSONResponse(status_code=404, content={"detail": "not_found"})
        return await call_next(request)

    @app.post("/v1/tasks", status_code=202)
    def submit(
        body: TaskSubmission, request: Request, scope: Annotated[str, Depends(require_scope)]
    ):
        from kli_quant.finance.contracts import ResearchRequest

        try:
            args = ResearchRequest.model_validate(body.input)
            research_input = ResearchInput(request_id=body.request_id, **args.model_dump())
        except ValidationError:
            raise HTTPException(422, "invalid_research_input") from None
        fingerprint = hashlib.sha256(json_bytes(body.model_dump(mode="json"))).hexdigest()
        with Session(request.app.state.database_engine) as session:
            application = get_application("kli-quant")
            # 持久会话行作为同 scope 的短事务锁；并发提交先幂等认领，再串行校验。
            session.execute(
                insert(Conversation)
                .values(
                    id=scope,
                    title="HTTP 研究任务",
                    application=application.id,
                    application_version=application.version,
                    prompt="",
                    created_at=utcnow(),
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.scalar(select(Conversation).where(Conversation.id == scope).with_for_update())
            existing = session.get(Run, str(body.request_id))
            if existing:
                if (
                    existing.conversation_id != scope
                    or existing.input.get("http_request_hash") != fingerprint
                ):
                    raise HTTPException(409, "request_id_conflict")
                return snapshot(session, existing)
            parent = owned_run(session, body.parent_task_id, scope) if body.parent_task_id else None
            if parent:
                latest = session.scalar(
                    select(Run.id)
                    .where(
                        Run.research_id == parent.research_id,
                    )
                    .order_by(Run.as_of.desc())
                    .limit(1)
                )
                if latest != parent.id:
                    raise HTTPException(409, "parent_is_not_latest_version")
            created = enqueue_run(
                session,
                settings,
                research_input,
                research_id=parent.research_id if parent else None,
                conversation_id=scope,
            )
            run = session.get(Run, created["run_id"])
            run.input = {**run.input, "http_request_hash": fingerprint}
            session.commit()
            return snapshot(session, run)

    @app.get("/v1/tasks/{task_id}")
    def status(task_id: UUID, request: Request, scope: Annotated[str, Depends(require_scope)]):
        with Session(request.app.state.database_engine) as session:
            return snapshot(session, owned_run(session, task_id, scope))

    @app.post("/v1/tasks/{task_id}/cancel")
    def cancel(task_id: UUID, request: Request, scope: Annotated[str, Depends(require_scope)]):
        with Session(request.app.state.database_engine) as session:
            run = session.scalar(select(Run).where(Run.id == str(task_id)).with_for_update())
            owned_run(session, task_id, scope)
            if run.status in {"queued", "running"}:
                run.status, run.stop_reason, run.finished_at = "cancelled", "cancelled", utcnow()
                session.commit()
            return snapshot(session, run)

    @app.get("/v1/tasks/{task_id}/detail")
    def detail(task_id: UUID, request: Request, scope: Annotated[str, Depends(require_scope)]):
        with Session(request.app.state.database_engine) as session:
            owned_run(session, task_id, scope)
        return run_detail(str(task_id), request)

    @app.get("/v1/tasks/{task_id}/results/{record_id}")
    def result(
        task_id: UUID,
        record_id: UUID,
        request: Request,
        scope: Annotated[str, Depends(require_scope)],
    ):
        with Session(request.app.state.database_engine) as session:
            owned_run(session, task_id, scope)
            record = session.get(Record, str(record_id))
            if not record or record.run_id != str(task_id):
                raise HTTPException(404, "result_not_found")
            try:
                content = (
                    Archive(settings).get(record.data["object"])
                    if "object" in record.data
                    else json_bytes(record.data)
                )
            except Exception:
                raise HTTPException(503, "result_unavailable") from None
            return Response(
                content,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{record.id}.bin"',
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "sandbox",
                },
            )

    return app
