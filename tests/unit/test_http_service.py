"""金融 HTTP 服务协议：虚构数据测试，不连接外部服务。"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fina_agent.agent.storage import json_bytes
from fina_agent.models import Record
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from kli_quant.service import create_service


@pytest.fixture
def client(store, settings):
    settings.http_tool_token = SecretStr("fictional-service-token")
    with (
        patch("kli_quant.application.Settings", return_value=settings),
        TestClient(create_service(settings)) as client,
    ):
        client.app.state.database_engine = store.session.bind
        client.headers.update(
            {
                "Authorization": "Bearer fictional-service-token",
                "X-Task-Scope": str(uuid4()),
            }
        )
        yield client


def submit(client, **extra):
    body = {"request_id": str(uuid4()), "input": {"event": "虚构金融研究"}, **extra}
    response = client.post("/v1/tasks", json=body)
    assert response.status_code == 202, response.text
    return body, response.json()


def test_http_submit_retry_conflict_and_scope(client):
    body, task = submit(client)
    assert client.post("/v1/tasks", json=body).json() == task
    assert (
        client.post("/v1/tasks", json={**body, "input": {"event": "不同内容"}}).status_code == 409
    )
    task_id = task["task_id"]
    assert client.get(f"/v1/tasks/{task_id}").json() == task
    other_scope = {"X-Task-Scope": str(uuid4())}
    assert client.get(f"/v1/tasks/{task_id}", headers=other_scope).status_code == 404
    assert client.post(f"/v1/tasks/{task_id}/cancel", headers=other_scope).status_code == 404
    assert client.post("/v1/tasks", json=body, headers=other_scope).status_code == 409


def test_http_cancel_and_review_keep_old_result(client, store):
    body, first = submit(client)
    task_id = first["task_id"]
    record = Record(run_id=task_id, kind="judgment", data={"conclusion": "虚构旧结论"})
    store.session.add(record)
    store.session.commit()
    cancelled = client.post(f"/v1/tasks/{task_id}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert client.post(f"/v1/tasks/{task_id}/cancel").json() == cancelled
    _, review = submit(client, parent_task_id=task_id, input={"event": "虚构新线索"})
    assert review["progress"]["parent_run_id"] == task_id
    assert client.get(f"/v1/tasks/{task_id}").json() == cancelled
    content = client.get(f"/v1/tasks/{task_id}/results/{record.id}")
    assert content.content == json_bytes(record.data)
    assert client.get(f"/v1/tasks/{review['task_id']}/results/{record.id}").status_code == 404


def test_http_auth_and_input_boundary(client):
    assert client.get("/v1/tasks/" + str(uuid4()), headers={"Authorization": ""}).status_code == 401
    assert client.post("/api/researches", json={"event": "绕过 scope"}).status_code == 404
    bad = client.post(
        "/v1/tasks",
        json={
            "request_id": str(uuid4()),
            "input": {"event": "虚构", "run_max_steps": 999},
        },
    )
    assert bad.status_code == 422
    for payload in ({}, {"source_urls": ["http://user:password@example.com/private"]}):
        assert (
            client.post(
                "/v1/tasks",
                json={
                    "request_id": str(uuid4()),
                    "input": payload,
                },
            ).status_code
            == 422
        )


def test_provider_does_not_expose_unscoped_gateway(client):
    """HTTP 中间件不会保护 WebSocket，提供方不能继承底座聊天入口。"""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/agent/gateway", headers={"origin": "http://testserver"}
        ):
            pass


def test_review_cannot_silently_change_requested_parent(client):
    _, first = submit(client)
    client.post(f"/v1/tasks/{first['task_id']}/cancel")
    _, second = submit(client, parent_task_id=first["task_id"])
    client.post(f"/v1/tasks/{second['task_id']}/cancel")
    response = client.post(
        "/v1/tasks",
        json={
            "request_id": str(uuid4()),
            "input": {"event": "虚构旧父版本"},
            "parent_task_id": first["task_id"],
        },
    )
    assert response.status_code == 409
