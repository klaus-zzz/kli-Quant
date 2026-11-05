"""验证后端的隔离服务边界，不连接真实抓取源站。"""

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.research import fetch_api, fetch_client


def test_backend_only_calls_fixed_fetch_service(monkeypatch):
    """用户 URL 仅进入请求体；不接受代理环境或来源重定向替换内部服务地址。"""
    real_client = httpx.Client
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "available", "blocks": []})

    def client(**kwargs):
        assert kwargs == {"trust_env": False, "timeout": 30, "follow_redirects": False}
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(fetch_client.httpx, "Client", client)
    assert fetch_client.fetch_source("https://example.com/")["status"] == "available"
    assert str(calls[0].url) == "http://research-fetcher:18101/fetch"
    assert b"https://example.com/" in calls[0].content


@pytest.mark.parametrize("status", [302, 500])
def test_fetch_service_failure_never_falls_back_to_source(monkeypatch, status):
    """服务重定向或故障只能返回失败，不在后端重试目标来源。"""
    real_client = httpx.Client
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "http://127.0.0.1/"})

    monkeypatch.setattr(
        fetch_client.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    assert (
        fetch_client.fetch_source("https://example.com/")["error"]
        == "fetcher_unavailable"
    )
    assert len(calls) == 1


def test_worker_rejects_policy_overrides(monkeypatch):
    """服务入口只接收 URL，不能由调用方禁用证书或指定内网连接 IP。"""
    calls = []
    monkeypatch.setattr(fetch_api, "fetch_source", lambda url: calls.append(url) or {})
    with TestClient(fetch_api.app) as client:
        assert (
            client.post("/fetch", json={"url": "https://example.com/"}).status_code
            == 200
        )
        assert (
            client.post(
                "/fetch", json={"url": "https://example.com/", "verify": False}
            ).status_code
            == 422
        )
        assert client.post("/fetch", json={"url": "x" * 2049}).status_code == 422
    assert calls == ["https://example.com/"]
