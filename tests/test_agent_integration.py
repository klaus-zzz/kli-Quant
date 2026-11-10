"""真实测试库配合 HTTP/模型替身，验证业务接线的安全与生命周期。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from test_research_service import research as research

from backend.agent.runtime import Runtime
from backend.main import app
from backend.research.api import service
from backend.research.models import ResearchError, Submission


@pytest.fixture
def agent(research, monkeypatch):
    runtime = Runtime(research, {"KLI_QUANT_CHAT_TOKEN": "chat-secret"})
    runtime.ready = True
    session = runtime.ledger.create_session("developer")
    identity = {"session_id": session, "run_id": None}

    def authenticate(value):
        if value != "host-injected":
            raise ResearchError("unauthorized", 401)
        return identity.copy()

    runtime.sandboxes = SimpleNamespace(
        authenticate=authenticate, close=Mock(), ensure=Mock()
    )
    monkeypatch.setattr(app.state, "agent", runtime, raising=False)
    app.dependency_overrides[service] = lambda: research
    yield runtime, session, identity, TestClient(app)
    app.dependency_overrides.clear()


def test_identity_budget_and_session_boundaries(agent, monkeypatch):
    runtime, session, identity, client = agent
    payload = {"event": "事件", "question": "研究"}
    assert (
        client.post(
            "/api/research/runs",
            json=payload,
            headers={"X-Run-ID": "fake", "Idempotency-Key": "one"},
        ).status_code
        == 401
    )
    headers = {"Authorization": "host-injected", "Idempotency-Key": "one"}
    response = client.post("/api/research/runs", json=payload, headers=headers)
    assert response.status_code == 202
    from uuid import UUID

    run_id = UUID(response.json()["run_id"])
    assert runtime.research.claim(session, run_id)
    identity["run_id"] = run_id
    with runtime.repo.transaction() as conn:
        conn.execute("UPDATE research_runs SET max_calls=1 WHERE id=%s", (run_id,))

    async def data(*args):
        return {
            "status": "success",
            "data": {
                "fields": ["ts_code", "trade_date", "close"],
                "items": [["000001.SZ", "20200102", 10]],
            },
            "fetched_at": "2020-01-03T00:00:00Z",
        }

    monkeypatch.setattr("backend.tushare.execute_query", data)
    query = {"params": {"ts_code": "000001.SZ", "trade_date": "20200102"}}
    result = client.post("/api/tushare/daily", headers=headers, json=query)
    assert result.status_code == 200 and result.json()["evidence"]["run_id"] == str(
        run_id
    )
    assert (
        client.post("/api/tushare/daily", headers=headers, json=query).status_code
        == 409
    )
    assert client.post("/api/tushare/daily", json=query).status_code == 401
    assert (
        client.post("/api/research/runs", headers=headers, json=payload).status_code
        == 404
    )
    other = runtime.ledger.create_session("developer")
    headers = {"Authorization": "Bearer chat-secret", "X-Session-ID": other}
    assert (
        client.get(f"/api/research/runs/{run_id}", headers=headers).status_code == 404
    )


def test_cancel_and_restart_do_not_restart_research(agent):
    runtime, session, _, _ = agent
    run, _ = runtime.research.submit(
        session, "cancel", Submission(event="事件", question="研究")
    )
    runtime.research.claim(session, run["id"])
    runtime.research.cancel(session, run["id"])
    runtime.recover()
    assert runtime.research.get(session, run["id"])["status"] == "cancelled"
    runtime.sandboxes.close.assert_called_once()
    run, _ = runtime.research.submit(
        session, "restart", Submission(event="事件", question="研究")
    )
    runtime.research.claim(session, run["id"])
    runtime.recover()
    assert runtime.research.get(session, run["id"])["status"] == "failed"
    assert not runtime.research.claim(session, run["id"])


def test_context_exposes_execution_and_citation_contract(agent):
    runtime, session, identity, client = agent
    run, _ = runtime.research.submit(
        session, "contract", Submission(event="事件", question="研究")
    )
    runtime.research.claim(session, run["id"])
    identity["run_id"] = run["id"]
    response = client.get(
        "/api/research/context", headers={"Authorization": "host-injected"}
    )
    contract = response.json()["execution_contract"]
    assert contract["input"] == "{evidence_id: document}"
    assert contract["dataset_table"] == "document.response.data"
    assert set(contract["output"]) == {"conventions", "observations"}
    assert "evidence_id" in contract["output"]["conventions"]
    assert "published_at" in response.json()["citation_rules"]


def test_invalid_agent_draft_can_be_corrected_before_deadline(agent):
    from test_research_contract import draft

    runtime, session, identity, client = agent
    run, _ = runtime.research.submit(
        session, "correct", Submission(event="事件", question="研究")
    )
    runtime.research.claim(session, run["id"])
    identity["run_id"] = run["id"]
    headers = {"Authorization": "host-injected"}
    payload = draft()
    payload["conclusion"] = "conditional_observation"
    response = client.post("/api/research/publish", headers=headers, json=payload)
    assert response.json() == {
        "error": "validation_failed",
        "errors": ["evidence_required"],
        "published": False,
    }
    assert runtime.research.get(session, run["id"])["status"] == "running"
    payload["conclusion"] = "insufficient_evidence"
    response = client.post("/api/research/publish", headers=headers, json=payload)
    assert response.status_code == 200 and response.json()["version"] == 1


def test_websocket_rejects_nonobject_authentication(agent):
    from starlette.websockets import WebSocketDisconnect

    _, session, _, client = agent
    with client.websocket_connect(f"/api/chat/sessions/{session}/ws") as ws:
        ws.send_json([])
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401


def test_shutdown_waits_for_chat_sandbox_registration(agent):
    import asyncio
    import threading
    from unittest.mock import AsyncMock

    runtime, session, _, _ = agent
    runtime.ledger.enqueue("creating", session, session, "chat", "创建中")
    runtime.ws = SimpleNamespace(send=AsyncMock())

    async def scenario():
        started = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def create(*args):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(2)

        runtime.sandboxes.ensure.side_effect = create
        task = asyncio.create_task(runtime.tick())
        await started.wait()
        task.cancel()
        await asyncio.sleep(0.02)
        waiting = not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert waiting
        runtime.ws.send.assert_not_called()

    asyncio.run(scenario())


def test_expired_session_does_not_block_other_deliveries(agent):
    import asyncio
    from unittest.mock import AsyncMock

    runtime, session, _, _ = agent
    other = runtime.ledger.create_session("developer")
    runtime.ledger.enqueue("expired", session, session, "chat", "过期会话")
    runtime.ledger.enqueue("fresh", other, other, "chat", "新会话")
    runtime.sandboxes.ensure.side_effect = [ResearchError("session_expired"), None]
    runtime.ws = SimpleNamespace(send=AsyncMock())
    asyncio.run(runtime.tick())
    runtime.ws.send.assert_called_once()
    assert runtime.ledger.deliveries(session)[0]["state"] == "failed"
    assert runtime.ledger.deliveries(other)[0]["state"] == "sending"


def test_notification_deduplicates_and_forbids_new_research(agent):
    runtime, session, _, client = agent
    run, _ = runtime.research.submit(
        session, "cancelled", Submission(event="事件", question="研究")
    )
    runtime.research.cancel(session, run["id"])
    runtime.advance_research()
    runtime.advance_research()
    deliveries = runtime.ledger.deliveries(session)
    assert len(deliveries) == 1 and deliveries[0]["kind"] == "notification"
    runtime.ledger.begin(deliveries[0]["id"])
    response = client.post(
        "/api/research/runs",
        json={"event": "事件", "question": "研究"},
        headers={"Authorization": "host-injected", "Idempotency-Key": "new"},
    )
    assert response.status_code == 403


def test_private_reconnect_is_scoped_and_authenticated(agent, monkeypatch):
    runtime, session, _, client = agent
    runtime.env["KLI_QUANT_CONTROL_TOKEN"] = "control-secret"
    with runtime.repo.transaction() as conn:
        conn.execute(
            "INSERT INTO agent_sandboxes (thread_id,session_id,sandbox_id,"
            "identity_sha256,traffic_token,cli_sha256,expires_at,active) "
            "VALUES (%s,%s,'own','hash','private-token','code',"
            "now()+interval '1 minute',true)",
            (session, session),
        )

    async def upstream(*args, **kwargs):
        assert kwargs["body"]["timeout"] <= 60
        return SimpleNamespace(
            content=b"{}", status_code=200, json=lambda: {"sandboxID": "own"}
        )

    monkeypatch.setattr("backend.agent.cube_api.upstream", upstream)
    headers = {"X-API-Key": "control-secret"}
    assert client.post("/api/agent/cube/sandboxes/own/connect").status_code == 401
    assert (
        client.post(
            "/api/agent/cube/sandboxes/other/connect", headers=headers
        ).status_code
        == 404
    )
    response = client.post(
        "/api/agent/cube/sandboxes/own/connect",
        headers=headers,
        json={"timeout": 999999},
    )
    assert response.json()["trafficAccessToken"] == "private-token"
    assert response.json()["envdAccessToken"] == "private-token"
    assert client.post("/api/agent/cube/sandboxes", headers=headers).status_code == 405


def test_envd_proxy_checks_instance_token_and_fixed_target(agent, monkeypatch):
    import httpx

    runtime, session, _, client = agent
    runtime.env.update(CUBE_PROXY_NODE_IP="192.0.2.10", CUBESANDBOX_DOMAIN="cube.test")
    with runtime.repo.transaction() as conn:
        conn.execute(
            "INSERT INTO agent_sandboxes (thread_id,session_id,sandbox_id,"
            "identity_sha256,traffic_token,cli_sha256,expires_at,active) "
            "VALUES (%s,%s,'own','hash','instance-token','code',"
            "now()+interval '1 minute',true)",
            (session, session),
        )
    headers = {"E2b-Sandbox-Id": "own", "X-Access-Token": "wrong"}
    assert client.get("/api/agent/cube/envd/files", headers=headers).status_code == 401
    headers["X-Access-Token"] = "instance-token"
    assert client.get("/api/agent/cube/envd/admin", headers=headers).status_code == 404
    headers["E2b-Sandbox-Id"] = "foreign"
    assert client.get("/api/agent/cube/envd/files", headers=headers).status_code == 401
    headers.update({"E2b-Sandbox-Id": "own", "Host": "attacker.test"})

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"file-content"

    class Upstream:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        def build_request(self, method, url, **kwargs):
            assert url == "http://192.0.2.10/files"
            assert kwargs["headers"]["Host"] == "49983-own.cube.test"
            assert kwargs["headers"]["e2b-traffic-access-token"] == "instance-token"
            assert "X-Access-Token" not in kwargs["headers"]
            return None

        async def send(self, request, **kwargs):
            return httpx.Response(200, stream=Stream())

        async def aclose(self):
            pass

    monkeypatch.setattr("backend.agent.envd.httpx.AsyncClient", Upstream)
    assert (
        client.get("/api/agent/cube/envd/files", headers=headers).content
        == b"file-content"
    )


def test_disconnected_supervision_cancels_without_starting_queued_work(agent):
    runtime, session, _, _ = agent
    queued, _ = runtime.research.submit(
        session, "queued", Submission(event="事件", question="研究")
    )
    cancelled, _ = runtime.research.submit(
        session, "disconnected", Submission(event="事件", question="研究")
    )
    runtime.research.claim(session, cancelled["id"])
    runtime.research.cancel(session, cancelled["id"])
    runtime.ready = False
    runtime.advance_research()
    assert runtime.research.get(session, cancelled["id"])["status"] == "cancelled"
    assert runtime.research.get(session, queued["id"])["status"] == "queued"
    runtime.sandboxes.ensure.assert_not_called()


def test_reconnect_checks_live_history_before_next_delivery(agent):
    import asyncio
    from unittest.mock import AsyncMock

    runtime, session, _, _ = agent
    runtime.ledger.enqueue("old", session, session, "chat", "旧消息")
    runtime.ledger.begin("old")
    runtime.ledger.recover()
    runtime.ledger.enqueue("new", session, session, "chat", "新消息")
    runtime.history = AsyncMock(return_value={"live": {"message_id": "old"}})
    runtime.ws = SimpleNamespace(send=AsyncMock())
    asyncio.run(runtime.tick())
    runtime.ws.send.assert_not_called()
    runtime.history.return_value = {"messages": []}
    asyncio.run(runtime.tick())
    runtime.ws.send.assert_called_once()
    assert runtime.ledger.deliveries(session)[0]["state"] == "uncertain"


def test_cancel_stops_upstream_turn_without_resubmitting_research(agent):
    import asyncio
    import json
    from unittest.mock import AsyncMock

    runtime, session, _, _ = agent
    run, _ = runtime.research.submit(
        session, "stop", Submission(event="事件", question="研究")
    )
    runtime.research.claim(session, run["id"])
    thread = f"kqr-{run['id'].hex}"
    runtime.ledger.enqueue("running", session, thread, "research", "工作", run["id"])
    runtime.ledger.begin("running")
    runtime.research.cancel(session, run["id"])
    runtime.ws = SimpleNamespace(send=AsyncMock())
    asyncio.run(runtime.tick())
    assert (
        json.loads(runtime.ws.send.call_args.args[0])["payload"]["question"] == "/stop"
    )
    asyncio.run(runtime.tick())
    runtime.ws.send.assert_called_once()


def test_publish_waits_for_agent_turn_before_destroying_sandbox(agent, monkeypatch):
    runtime, session, _, _ = agent
    run, _ = runtime.research.submit(
        session, "publish", Submission(event="事件", question="研究")
    )
    thread = f"kqr-{run['id'].hex}"
    runtime.ledger.enqueue(
        "research-test", session, thread, "research", "工作", run["id"]
    )
    runtime.ledger.begin("research-test")
    with runtime.repo.transaction() as conn:
        conn.execute(
            "UPDATE research_runs SET status='completed' WHERE id=%s", (run["id"],)
        )
        conn.execute(
            "INSERT INTO agent_sandboxes (thread_id,session_id,run_id,identity_sha256,"
            "cli_sha256,expires_at) VALUES "
            "(%s,%s,%s,'hash','code',now()+interval '1 hour')",
            (thread, session, run["id"]),
        )
    monkeypatch.setattr(runtime.research, "result", lambda *args: {"version": 1})
    runtime.advance_research()
    runtime.sandboxes.close.assert_not_called()
    runtime.ledger.record(
        {
            "message_id": "research-test",
            "thread_id": thread,
            "message_seq": 0,
            "payload": {"type": "done"},
        }
    )
    runtime.advance_research()
    runtime.sandboxes.close.assert_called_once_with(thread)
