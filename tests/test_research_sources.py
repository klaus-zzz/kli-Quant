"""公网边界与固定原文解析，不连接真实站点。"""

import socket
from types import SimpleNamespace

import pytest

from backend.research import sources
from backend.research.models import ResearchError


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "224.0.0.1",
        "ff02::1",
    ],
)
def test_private_resolution_rejected(monkeypatch, ip):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (ip, 80))]
    )
    with pytest.raises(ResearchError, match="unsafe_address"):
        sources.public_target("http://public.example/")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "https://example.com:8443/",
        "https://example.com/\r\nHost:localhost",
    ],
)
def test_unsafe_urls_rejected(url):
    with pytest.raises((ResearchError, ValueError)):
        sources.public_target(url)


def test_mixed_dns_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (2, 1, 6, "", ("8.8.8.8", 80)),
            (2, 1, 6, "", ("127.0.0.1", 80)),
        ],
    )
    with pytest.raises(ResearchError):
        sources.public_target("http://public.example")


def test_scrapling_parses_fixed_blocks():
    html = (
        b'<html><head><meta property="article:published_time" '
        b'content="2020-01-01T12:00:00Z"></head><body><article>'
        b"<p>Supply <b>fell</b>.</p><p>Inventory grew.</p></article></body></html>"
    )
    blocks, published = sources.extract(html, "text/html")
    assert blocks == ["Supply fell.", "Inventory grew."]
    assert published == "2020-01-01T12:00:00+00:00"
    assert sources.extract(b"<body><p>No date</p></body>", "text/html")[1] is None


def test_redirect_rechecks_private_target(monkeypatch):
    """首次访问公网，重定向到元数据地址时不得建立第二个连接。"""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [
            (2, 1, 6, "", ("127.0.0.1" if host == "internal" else "8.8.8.8", 80))
        ],
    )
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status=302, headers={"location": "http://internal/"})

    monkeypatch.setattr(sources.Fetcher, "get", fetch)
    result = sources.fetch_source("http://public.example")
    assert result["error"] == "unsafe_address"
    assert len(calls) == 1


def test_any_public_hostname_is_accepted(monkeypatch):
    """允许任意公网来源，不维护站点白名单；去掉片段并规范化域名。"""
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))]
    )
    assert sources.public_target("https://Any-Source.example/page#part") == (
        "https://any-source.example/page"
    )


def test_redirects_share_remaining_time(monkeypatch):
    """跳转不能重新获得完整预算，最终归档 URL 与原始字节仍准确。"""
    now, budgets = [0], []
    monkeypatch.setattr(sources.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(sources, "public_target", lambda url: url)

    def fetch(url, **kwargs):
        budgets.append(kwargs["timeout"])
        now[0] += 6
        if len(budgets) == 1:
            return SimpleNamespace(status=302, headers={"location": "/final"})
        kwargs["content_callback"](b"hello")
        return SimpleNamespace(status=200, headers={"content-type": "text/plain"})

    monkeypatch.setattr(sources.Fetcher, "get", fetch)
    assert sources.download("https://example.com/") == (
        "https://example.com/final",
        b"hello",
        "text/plain",
    )
    assert budgets == [sources.TIMEOUT, sources.TIMEOUT - 6]
