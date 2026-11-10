"""原生任务接线：真实数据库验证归属、通知、取消与发布的独立状态。"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_agent_integration import agent as agent
from test_research_contract import draft
from test_research_service import research as research

from backend.research.models import Submission


def task_frame(session, run_id, task_id="bg_one", status="running"):
    # prompt 的固定首行只用于关联，实际授权仍由后端会话归属裁决。
    return {
        "type": "task",
        "thread_id": session,
        "payload": {
            "task_id": task_id,
            "kind": "agent",
            "name": "deep-search",
            "brief": f"research:{run_id}",
            "status": status,
            "progress": None,
        },
    }


def receive(runtime, *frames):
    async def incoming():
        for frame in frames:
            yield json.dumps(frame)

    asyncio.run(runtime.receive(incoming()))


def create_run(runtime, session, key="native"):
    return runtime.research.submit(
        session, key, Submission(event="事件", question="研究")
    )[0]["id"]


def test_native_task_claims_only_its_session_and_does_not_publish(agent):
    runtime, session, _, _ = agent
    run_id = create_run(runtime, session)
    other = runtime.ledger.create_session("developer")
    receive(runtime, task_frame(other, run_id, "bg_foreign"))
    assert runtime.research.get(session, run_id)["status"] == "queued"
    receive(runtime, task_frame(session, run_id))
    assert runtime.research.get(session, run_id)["status"] == "running"
    receive(runtime, task_frame(session, run_id, status="completed"))
    assert runtime.research.get(session, run_id)["status"] == "failed"
    runtime.sandboxes.close.assert_not_called()


def test_proactive_messages_are_saved_once_for_known_sessions(agent):
    runtime, session, _, _ = agent
    frame = {
        "type": "event",
        "thread_id": session,
        "message_id": "agent-result",
        "message_seq": 0,
        "payload": {"type": "delta", "text": "研究结果"},
    }
    receive(runtime, frame, frame, {**frame, "thread_id": "unknown"})
    rows = runtime.ledger.deliveries(session)
    assert len(rows) == 1 and rows[0]["answer"] == "研究结果"


def test_duplicate_launch_is_stopped_without_replacing_original_task(agent):
    runtime, session, _, _ = agent
    run_id = create_run(runtime, session)
    receive(
        runtime,
        task_frame(session, run_id),
        task_frame(session, run_id, "bg_duplicate"),
    )
    assert runtime.native.stops() == [
        {"task_id": "bg_duplicate", "session_id": session}
    ]
    receive(runtime, task_frame(session, run_id, "bg_duplicate", "cancelled"))
    assert runtime.research.get(session, run_id)["status"] == "running"


def test_submit_returns_native_launch_arguments_without_dispatching(agent):
    runtime, session, _, client = agent
    response = client.post(
        "/api/research/runs",
        json={"question": "研究", "event": "事件"},
        headers={"Authorization": "host-injected", "Idempotency-Key": "launch"},
    )
    assert response.status_code == 202
    run = response.json()
    assert run["agent"] == {
        "name": "deep-search",
        "prompt": f"research:{run['run_id']}",
        "run_in_background": True,
    }
    assert runtime.ledger.deliveries(session) == []
    runtime.sandboxes.ensure.assert_not_called()


def test_cancel_one_research_leaves_other_research_running(agent):
    runtime, session, _, _ = agent
    first, second = create_run(runtime, session), create_run(runtime, session, "second")
    receive(runtime, task_frame(session, first), task_frame(session, second, "bg_two"))
    runtime.research.cancel(session, first)
    receive(runtime, task_frame(session, first, status="cancelled"))
    assert runtime.research.get(session, second)["status"] == "running"
    runtime.sandboxes.close.assert_not_called()


def test_bash_task_with_same_name_is_not_a_research_task(agent):
    runtime, session, _, _ = agent
    frame = task_frame(session, "ordinary-command")
    frame["payload"]["kind"] = "bash"
    receive(runtime, frame)
    assert runtime.native.stops() == []


def test_cancel_uses_native_task_stop_and_keeps_shared_sandbox(agent):
    runtime, session, _, _ = agent
    run_id = create_run(runtime, session)
    receive(runtime, task_frame(session, run_id))
    runtime.research.cancel(session, run_id)
    runtime.ws = SimpleNamespace(send=AsyncMock())
    asyncio.run(runtime.tick())
    sent = [json.loads(c.args[0]) for c in runtime.ws.send.call_args_list]
    assert {"type": "task_stop", "thread_id": session, "task_id": "bg_one"} in sent
    assert runtime.research.get(session, run_id)["status"] == "cancelling"
    receive(runtime, task_frame(session, run_id, status="cancelled"))
    assert runtime.research.get(session, run_id)["status"] == "cancelled"
    runtime.sandboxes.close.assert_not_called()


def test_shared_identity_checks_explicit_run_ownership(agent):
    runtime, session, _, client = agent
    run_id = create_run(runtime, session)
    receive(runtime, task_frame(session, run_id))
    headers = {"Authorization": "host-injected", "X-Research-Run": str(run_id)}
    assert client.get("/api/research/context", headers=headers).json()["run_id"] == str(
        run_id
    )
    other = runtime.ledger.create_session("developer")
    foreign = create_run(runtime, other, "foreign")
    headers["X-Research-Run"] = str(foreign)
    assert client.get("/api/research/context", headers=headers).status_code == 404


def test_chat_token_cannot_impersonate_sandbox_execution(agent, monkeypatch):
    from unittest.mock import Mock

    runtime, session, _, client = agent
    run_id = create_run(runtime, session)
    receive(runtime, task_frame(session, run_id))
    execute = Mock(return_value={})
    monkeypatch.setattr("backend.agent.tools.execute", execute)
    response = client.post(
        "/api/research/execute",
        headers={
            "Authorization": "Bearer chat-secret",
            "X-Session-ID": session,
            "X-Research-Run": str(run_id),
        },
        json={"code": "print(1)", "inputs": [str(run_id)]},
    )
    assert response.status_code == 403
    execute.assert_not_called()


def test_native_notification_cannot_submit_another_research(agent):
    runtime, session, _, client = agent
    receive(
        runtime,
        {
            "type": "event",
            "thread_id": session,
            "message_id": "agent-notify",
            "message_seq": 0,
            "payload": {"type": "init"},
        },
    )
    response = client.post(
        "/api/research/runs",
        json={"question": "再次研究", "event": "通知"},
        headers={"Authorization": "host-injected", "Idempotency-Key": "notification"},
    )
    assert response.status_code == 403


def test_published_result_survives_task_completion_and_reconnect(agent):
    runtime, session, _, _ = agent
    run_id = create_run(runtime, session)
    receive(runtime, task_frame(session, run_id))
    result = runtime.research.publish(session, run_id, draft())
    receive(runtime, task_frame(session, run_id, status="completed"))
    receive(runtime, {"type": "task_list", "thread_id": session, "tasks": []})
    assert runtime.research.result(session, run_id) == result
    runtime.sandboxes.close.assert_not_called()


def test_deadline_stops_only_expired_task_without_recycling_sandbox(agent):
    runtime, session, _, _ = agent
    run_id = create_run(runtime, session)
    receive(runtime, task_frame(session, run_id))
    with runtime.repo.transaction() as conn:
        conn.execute("UPDATE research_runs SET deadline=now() WHERE id=%s", (run_id,))
    assert runtime.native.stops() == [{"task_id": "bg_one", "session_id": session}]
    assert runtime.research.get(session, run_id)["error"] == "deadline_exceeded"
    runtime.sandboxes.close.assert_not_called()


def test_reconnect_keeps_live_native_task_and_shared_sandbox(agent):
    runtime, session, _, _ = agent
    run_id = create_run(runtime, session)
    task = task_frame(session, run_id)
    receive(runtime, task)
    runtime.recover()
    receive(
        runtime, {"type": "task_list", "thread_id": session, "tasks": [task["payload"]]}
    )
    assert runtime.research.get(session, run_id)["status"] == "running"
    runtime.sandboxes.close.assert_not_called()
    assert runtime.ledger.deliveries(session) == []


@pytest.mark.parametrize("cancel", [False, True])
def test_missing_native_task_is_reconciled_without_restart(agent, cancel):
    runtime, session, _, _ = agent
    run_id = create_run(runtime, session)
    receive(runtime, task_frame(session, run_id))
    if cancel:
        runtime.research.cancel(session, run_id)
    runtime.recover()
    assert runtime.research.get(session, run_id)["status"] == (
        "cancelling" if cancel else "running"
    )
    receive(runtime, {"type": "task_list", "thread_id": session, "tasks": []})
    assert runtime.research.get(session, run_id)["status"] == (
        "cancelled" if cancel else "failed"
    )
