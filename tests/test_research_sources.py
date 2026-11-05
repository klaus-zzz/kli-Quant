"""URL 格式、协议与固定原文解析，不连接真实站点。"""

import socket
from types import SimpleNamespace

import pytest

from backend.research import sources
from backend.research.models import ResearchError


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/",
        "http://[::1]/",
        "http://[fc00::1]/",
        "http://198.18.0.1/",
        "https://unresolved.example/",
    ],
)
def test_url_validation_does_not_resolve_or_classify_addresses(monkeypatch, url):
    """域名与各类 IP 均只做格式检查，解析交给实际下载库。"""

    def unexpected_dns(*args, **kwargs):
        pytest.fail("URL 校验不应进行 DNS 预解析")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_dns)
    assert sources.normalize_url(url) == url


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
        sources.normalize_url(url)


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


@pytest.mark.parametrize(
    "target,error",
    [
        ("file:///etc/passwd", "unsafe_url"),
        ("http://user:pass@example.com/", "unsafe_url"),
        ("http://example.com:8000/", "unsafe_port"),
    ],
)
def test_redirect_rechecks_url_constraints(monkeypatch, target, error):
    """不检查 IP 分类，但跳转后的协议、凭据和端口仍须校验。"""
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status=302, headers={"location": target})

    monkeypatch.setattr(sources.Fetcher, "get", fetch)
    result = sources.fetch_source("http://public.example")
    assert result["error"] == error
    assert len(calls) == 1


def test_hostname_and_fragment_normalized():
    """不维护站点白名单；去掉片段并规范化域名。"""
    assert sources.normalize_url("https://Any-Source.example/page#part") == (
        "https://any-source.example/page"
    )


def test_redirect_to_internal_ip_is_allowed(monkeypatch):
    """按当前网络取舍，内网跳转不会被应用层地址分类拦截。"""
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return SimpleNamespace(status=302, headers={"location": "http://10.0.0.1/"})
        kwargs["content_callback"](b"Internal source")
        return SimpleNamespace(status=200, headers={"content-type": "text/plain"})

    monkeypatch.setattr(sources.Fetcher, "get", fetch)
    document = sources.fetch_source("https://example.com/")
    assert document["status"] == "available"
    assert document["canonical_url"] == "http://10.0.0.1/"
    assert calls == ["https://example.com/", "http://10.0.0.1/"]


def test_redirects_share_remaining_time(monkeypatch):
    """跳转不能重新获得完整预算，最终归档 URL 与原始字节仍准确。"""
    now, budgets = [0], []
    monkeypatch.setattr(sources.time, "monotonic", lambda: now[0])

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
