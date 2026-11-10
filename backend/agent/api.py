"""单用户开发对话入口；浏览器只连接业务后端。"""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from backend.agent.tools import body
from backend.research.api import view
from backend.research.models import Model, ResearchError

router = APIRouter(prefix="/api/chat")


def agent(request):
    runtime = getattr(request.app.state, "agent", None)
    if runtime is None:
        raise ResearchError("agent_not_ready", 503)
    return runtime


def session_access(request, session):
    runtime = agent(request)
    owner = runtime.user(request.headers.get("Authorization", ""))
    runtime.ledger.session(owner, session)
    return runtime


class Message(Model):
    message_id: UUID
    text: str = Field(min_length=1, max_length=12000)
    effort: str | None = Field(default=None, min_length=1, max_length=32)


async def enqueue(runtime, session, value):
    """输入大小和身份在业务入口收口，不透传客户端 configurable。"""
    if not runtime.ready:
        raise ResearchError("agent_not_ready", 503)
    try:
        message = Message.model_validate(value)
    except ValueError:
        raise ResearchError("invalid_message", 422) from None
    if message.effort is not None:
        thinking = await runtime.thinking(session)
        if message.effort not in thinking["levels"]:
            raise ResearchError("unsupported_effort", 422)
    await run_in_threadpool(
        runtime.ledger.enqueue,
        str(message.message_id),
        session,
        session,
        "chat",
        message.text,
        effort=message.effort,
    )
    return {"type": "accepted", "message_id": str(message.message_id)}


def snapshot(runtime, session):
    with runtime.repo.transaction() as conn:
        runs = conn.execute(
            "SELECT * FROM research_runs WHERE owner=%s ORDER BY created_at", (session,)
        ).fetchall()
    return {
        "type": "snapshot",
        "session_id": session,
        "connected": runtime.ready,
        "deliveries": runtime.ledger.deliveries(session),
        "research": [view(r) for r in runs],
        "tasks": runtime.native.list(session),
    }


@router.post("/sessions", status_code=201)
def create_session(request: Request):
    runtime = agent(request)
    owner = runtime.user(request.headers.get("Authorization", ""))
    return {"session_id": runtime.ledger.create_session(owner)}


@router.get("/sessions/{session}")
def get_session(session: str, request: Request):
    return snapshot(session_access(request, session), session)


@router.get("/sessions")
def list_sessions(request: Request):
    runtime = agent(request)
    owner = runtime.user(request.headers.get("Authorization", ""))
    return {"sessions": runtime.ledger.sessions(owner)}


@router.get("/sessions/{session}/thinking")
async def thinking(session: str, request: Request):
    runtime = await run_in_threadpool(session_access, request, session)
    return await runtime.thinking(session)


@router.get("/sessions/{session}/history")
async def history(session: str, request: Request):
    runtime = await run_in_threadpool(session_access, request, session)
    # 上游历史是核对依据；缺少终态 ACK 的投递仍如实保留 uncertain。
    return {
        "history": await runtime.history(session),
        "deliveries": await run_in_threadpool(runtime.ledger.deliveries, session),
    }


@router.post("/sessions/{session}/messages", status_code=202)
async def message(session: str, request: Request):
    runtime = await run_in_threadpool(session_access, request, session)
    return await enqueue(runtime, session, await body(request, 32768))


@router.websocket("/sessions/{session}/ws")
async def websocket(session: str, ws: WebSocket):
    """认证走请求头或首帧，Token 不进 URL；断开连接不取消研究。"""
    await ws.accept()
    queue, tasks, runtime = asyncio.Queue(maxsize=128), [], None
    try:
        runtime = agent(ws)
        authorization = ws.headers.get("Authorization", "")
        if not authorization:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=5)
            if len(raw) > 1024:
                raise ResearchError("unauthorized", 401)
            authentication = json.loads(raw)
            if not isinstance(authentication, dict):
                raise ResearchError("unauthorized", 401)
            authorization = authentication.get("authorization", "")
        owner = runtime.user(authorization)
        await run_in_threadpool(runtime.ledger.session, owner, session)
        runtime.listeners.setdefault(session, set()).add(queue)
        from fastapi.encoders import jsonable_encoder

        await ws.send_json(
            jsonable_encoder(await run_in_threadpool(snapshot, runtime, session))
        )

        async def incoming():
            while True:
                raw = await ws.receive_text()
                if len(raw.encode()) > 32768:
                    raise ResearchError("request_too_large", 413)
                accepted = await enqueue(runtime, session, json.loads(raw))
                await queue.put(accepted)

        async def outgoing():
            while True:
                await ws.send_json(await queue.get())

        tasks = [asyncio.create_task(incoming()), asyncio.create_task(outgoing())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (ResearchError, ValueError, TimeoutError):
        await ws.close(code=4401)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if runtime:
            runtime.listeners.get(session, set()).discard(queue)
            if not runtime.listeners.get(session):
                runtime.listeners.pop(session, None)
