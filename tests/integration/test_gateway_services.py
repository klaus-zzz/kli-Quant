"""独立容器的真实 Gateway→HTTP 研究→主动回复链路，禁止模型或数据替身。"""

import hashlib
import json
import os
import socket
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest
from fina_agent.agent.storage import Archive
from fina_agent.models import ChatTurn, Conversation, Record, RemoteTask, Research, Run, ToolCall
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session
from websockets.sync.client import connect

from kli_quant.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("FINA_LIVE_GATEWAY") != "1",
        reason="requires isolated real services",
    ),
]


def test_real_gateway_http_research_and_notification():
    """两个测试库和正在运行的服务由验证环境提供；测试只清理自己创建的数据。"""
    core_url = os.environ["FINA_TEST_GATEWAY_URL"]
    provider_url = os.environ["FINA_TEST_PROVIDER_URL"]
    settings = Settings(database_url=os.environ["FINA_TEST_DATABASE_URL"])
    database = create_engine(os.environ["FINA_TEST_DATABASE_URL"])
    core_db = create_engine(os.environ["FINA_TEST_CORE_DATABASE_URL"])
    archive = Archive(settings)
    cid = None
    with httpx.Client(
        base_url=core_url, headers={"Host": "localhost"}, trust_env=False, timeout=30
    ) as client:

        def detail():
            response = client.get(f"/api/conversations/{cid}")
            response.raise_for_status()
            return response.json()

        def wait_for(predicate, timeout=180):
            until = time.monotonic() + timeout
            while time.monotonic() < until:
                state = detail()
                if predicate(state):
                    return state
                time.sleep(1)
            pytest.fail("timed out waiting for persisted gateway state")

        def gateway():
            # 内网地址不进浏览器；测试保留 localhost Host 并使用真实服务认证。
            parsed = urlsplit(core_url)
            transport = socket.create_connection((parsed.hostname, parsed.port or 80), timeout=10)
            return connect(
                "ws://localhost/api/agent/gateway",
                sock=transport,
                additional_headers={
                    "Authorization": "Bearer " + settings.gateway_token.get_secret_value(),
                },
            )

        def send(content):
            request_id = str(uuid4())
            with gateway() as ws:
                ws.send(
                    json.dumps(
                        {
                            "type": "message",
                            "conversation_id": cid,
                            "request_id": request_id,
                            "content": content,
                        }
                    )
                )
                ack = json.loads(ws.recv(timeout=15))
                assert ack["type"] == "ack", "gateway rejected message"
            state = wait_for(
                lambda s: any(
                    t["id"] == request_id and t["status"] != "running" and t["status"] != "queued"
                    for t in s["turns"]
                )
            )
            turn = next(t for t in state["turns"] if t["id"] == request_id)
            assert turn["status"] == "completed", turn["error"]
            print("chat completed:", [call["name"] for call in turn["calls"]], flush=True)
            return state

        try:
            response = client.post("/api/conversations")
            response.raise_for_status()
            cid = response.json()["id"]
            assert not send("用一句话解释事实与推测，不启动研究。")["tasks"]
            state = send(
                "立即调用 research_a_share_event，在后台研究利率政策对浦发银行600000.SH的影响。"
                "原文线索https://www.pbc.gov.cn/，查找支持及净息差压力反证。必须获取"
                "2026-10-20至2026-10-30日线，在沙箱写Python计算收益，执行、读回、发布探索产物。"
                "证据不足就说明不足，不必询问。"
            )
            assert len(state["tasks"]) == 1
            first = state["tasks"][0]["id"]
            wait_for(lambda s: s["tasks"][0]["status"] == "running")
            state = send("继续后台研究。用一句话解释条件性观察，不启动其他任务。")
            assert len(state["tasks"]) == 1
            state = wait_for(
                lambda s: any(
                    t["kind"] == "task_completion" and t["status"] == "completed"
                    for t in s["turns"]
                ),
                timeout=1000,
            )
            task = state["tasks"][0]
            assert task["status"] in {"completed", "inconclusive"}, task["status"]
            notifications = [t for t in state["turns"] if t["kind"] == "task_completion"]
            assert len(notifications) == 1 and not notifications[0]["calls"]
            response = client.get(f"/api/conversations/{cid}/tasks/{first}/detail")
            response.raise_for_status()
            research = response.json()
            kinds = {r["kind"] for r in research["records"]}
            assert {
                "document",
                "evidence",
                "snapshot",
                "execution",
                "artifact",
                "judgment",
            } <= kinds
            judgment = [r for r in research["records"] if r["kind"] == "judgment"]
            reference = next(r for r in task["snapshot"]["result_refs"] if r["kind"] == "artifact")
            content = client.get(
                f"/api/conversations/{cid}/tasks/{first}/results/{reference['id']}"
            )
            assert hashlib.sha256(content.content).hexdigest() == reference["sha256"]
            with gateway() as ws:
                ws.send(
                    json.dumps(
                        {"type": "subscribe", "request_id": str(uuid4()), "conversation_id": cid}
                    )
                )
                assert json.loads(ws.recv(timeout=10))["type"] == "ack"
                assert json.loads(ws.recv(timeout=10))["data"]["turns"] == state["turns"]
            state = send(
                f"新线索：净息差压力可能抵消政策。请以 parent_task_id={first} 启动复核新版本。"
            )
            assert len(state["tasks"]) == 2 and state["tasks"][-1]["parent_task_id"] == first
            second = state["tasks"][-1]["id"]
            with gateway() as ws:
                ws.send(
                    json.dumps(
                        {
                            "type": "cancel",
                            "conversation_id": cid,
                            "request_id": str(uuid4()),
                            "task_id": second,
                        }
                    )
                )
                assert json.loads(ws.recv(timeout=10))["type"] == "ack"
            wait_for(lambda s: s["tasks"][-1]["status"] == "cancelled")
            unchanged = client.get(f"/api/conversations/{cid}/tasks/{first}/detail").json()
            assert [r for r in unchanged["records"] if r["kind"] == "judgment"] == judgment
            print(
                "real HTTP research:",
                task["status"],
                sorted(kinds),
                "notification/reconnect/cancel passed",
                flush=True,
            )
        finally:
            if cid:
                cleanup(cid, provider_url, settings, database, core_db, archive)
            database.dispose()
            core_db.dispose()


def cleanup(cid, provider_url, settings, database, core_db, archive):
    """按本次会话限定清理范围；先取消并等待沙箱回收，再删除归档与测试记录。"""
    headers = {
        "Authorization": "Bearer " + settings.http_tool_token.get_secret_value(),
        "X-Task-Scope": cid,
    }
    with Session(database) as session:
        ids = list(session.scalars(select(Run.id).where(Run.conversation_id == cid)))
    with httpx.Client(
        base_url=provider_url, headers=headers, trust_env=False, timeout=15
    ) as client:
        for run_id in ids:
            client.post(f"/v1/tasks/{run_id}/cancel")
    for _ in range(60):
        with Session(database) as session:
            runs = list(session.scalars(select(Run).where(Run.conversation_id == cid)))
            pending = any(
                run.cleanup_pending
                or (run.deadline is not None and not run.state.get("worker_released"))
                for run in runs
            )
        if not pending:
            break
        time.sleep(1)
    assert not pending, "worker and sandbox cleanup must finish before deleting records"
    with Session(core_db) as session:
        rows = list(
            session.scalars(
                select(RemoteTask)
                .where(RemoteTask.conversation_id == cid)
                .order_by(RemoteTask.created_at.desc())
            )
        )
        for row in rows:
            session.delete(row)
            session.flush()
        session.execute(delete(ChatTurn).where(ChatTurn.conversation_id == cid))
        session.execute(delete(Conversation).where(Conversation.id == cid))
        session.commit()
    with Session(database) as session:
        runs = list(
            session.scalars(
                select(Run).where(Run.conversation_id == cid).order_by(Run.as_of.desc())
            )
        )
        topics = {run.research_id for run in runs}
        for run in runs:
            for page in archive.client.get_paginator("list_objects_v2").paginate(
                Bucket=archive.bucket, Prefix=f"runs/{run.id}/"
            ):
                for item in page.get("Contents", []):
                    archive.client.delete_object(Bucket=archive.bucket, Key=item["Key"])
            session.execute(delete(ToolCall).where(ToolCall.run_id == run.id))
            session.execute(delete(Record).where(Record.run_id == run.id))
            session.delete(run)
            session.flush()
        session.execute(delete(Research).where(Research.id.in_(topics)))
        session.execute(delete(Conversation).where(Conversation.id == cid))
        session.commit()
