"""隔离抓取服务的输入边界。"""

from fastapi.testclient import TestClient

from fetcher import api


def test_worker_rejects_policy_overrides(monkeypatch):
    """服务入口只接收 URL，不能由调用方禁用证书或指定内网连接 IP。"""
    calls = []
    monkeypatch.setattr(api, "fetch_source", lambda url: calls.append(url) or {})
    with TestClient(api.app) as client:
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
