"""验证后端的隔离服务边界，不连接真实抓取源站。"""

import httpx
import pytest

from backend.research import fetch_client


@pytest.mark.parametrize(
    "endpoint",
    ["http://research-fetcher:18101/fetch", "http://custom-worker:9000/source/fetch"],
)
def test_backend_only_calls_configured_fetch_service(monkeypatch, endpoint):
    """用户 URL 仅进入请求体；不接受代理环境或来源重定向替换内部服务地址。"""
    real_client = httpx.Client
    calls = []
    monkeypatch.setenv("RESEARCH_FETCHER_URL", endpoint)

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "available", "blocks": []})

    def client(**kwargs):
        assert kwargs == {"trust_env": False, "timeout": 30, "follow_redirects": False}
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(fetch_client.httpx, "Client", client)
    assert fetch_client.fetch_source("https://example.com/")["status"] == "available"
    assert str(calls[0].url) == endpoint
    assert b"https://example.com/" in calls[0].content


@pytest.mark.parametrize("endpoint", [None, "", "   "])
def test_missing_fetch_service_config_never_connects(monkeypatch, endpoint):
    """未配置部署地址时直接失败，不猜服务名或回退到来源地址。"""
    monkeypatch.delenv("RESEARCH_FETCHER_URL", raising=False)
    if endpoint is not None:
        monkeypatch.setenv("RESEARCH_FETCHER_URL", endpoint)

    def unexpected_client(**kwargs):
        pytest.fail("缺少配置时不应创建网络客户端")

    monkeypatch.setattr(fetch_client.httpx, "Client", unexpected_client)
    assert fetch_client.fetch_source("https://example.com/")["error"] == (
        "fetcher_unavailable"
    )


@pytest.mark.parametrize("status", [302, 500])
def test_fetch_service_failure_never_falls_back_to_source(monkeypatch, status):
    """服务重定向或故障只能返回失败，不在后端重试目标来源。"""
    real_client = httpx.Client
    calls = []
    monkeypatch.setenv("RESEARCH_FETCHER_URL", "http://custom-worker:9000/fetch")

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


def test_invalid_fetch_service_config_returns_unavailable(monkeypatch):
    """部署地址端口写错时保留失败记录，不抛出配置异常原文。"""
    monkeypatch.setenv("RESEARCH_FETCHER_URL", "http://custom-worker:bad/fetch")
    assert fetch_client.fetch_source("https://example.com/")["error"] == (
        "fetcher_unavailable"
    )
