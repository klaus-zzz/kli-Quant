"""工作台列表与思考档位走真实持久层，模型服务使用替身。"""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

from test_agent_integration import agent as agent
from test_research_service import research as research


def test_sessions_only_list_authenticated_owner(agent):
    runtime, session, _, client = agent
    other = runtime.ledger.create_session("someone-else")
    runtime.ledger.enqueue("title", session, session, "chat", "第一条对话")
    assert client.get("/api/chat/sessions").status_code == 401
    response = client.get(
        "/api/chat/sessions", headers={"Authorization": "Bearer chat-secret"}
    )
    assert response.status_code == 200
    rows = response.json()["sessions"]
    assert any(row["id"] == session and row["title"] == "第一条对话" for row in rows)
    assert all(row["id"] != other for row in rows)


def test_effort_is_validated_persisted_and_delivered(agent, monkeypatch):
    runtime, session, _, client = agent
    thinking = {
        "control": "effort",
        "levels": ["low", "high"],
        "current_effort": None,
        "recommended_effort": "low",
    }
    monkeypatch.setattr(runtime, "thinking", AsyncMock(return_value=thinking))
    headers = {"Authorization": "Bearer chat-secret"}
    path = f"/api/chat/sessions/{session}"
    assert client.get(path + "/thinking").status_code == 401
    assert client.get(path + "/thinking", headers=headers).json() == thinking
    message = {"message_id": str(uuid4()), "text": "你好", "effort": "high"}
    assert (
        client.post(path + "/messages", headers=headers, json=message).status_code
        == 202
    )
    assert (
        client.post(path + "/messages", headers=headers, json=message).status_code
        == 202
    )
    changed = {**message, "effort": "low"}
    assert (
        client.post(path + "/messages", headers=headers, json=changed).status_code
        == 409
    )
    unsupported = {**message, "message_id": str(uuid4()), "effort": "xhigh"}
    assert (
        client.post(path + "/messages", headers=headers, json=unsupported).status_code
        == 422
    )
    runtime.ws = AsyncMock()
    asyncio.run(runtime.tick())
    frame = json.loads(runtime.ws.send.call_args.args[0])
    assert frame["payload"]["effort"] == "high"
    assert frame["payload"]["user_id"] == "developer"


def test_thinking_does_not_read_another_owners_session(agent, monkeypatch):
    runtime, _, _, client = agent
    other = runtime.ledger.create_session("someone-else")
    upstream = AsyncMock()
    monkeypatch.setattr(runtime, "thinking", upstream)
    response = client.get(
        f"/api/chat/sessions/{other}/thinking",
        headers={"Authorization": "Bearer chat-secret"},
    )
    assert response.status_code == 404
    upstream.assert_not_called()
