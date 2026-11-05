"""公网边界与固定原文解析，不连接真实站点。"""

import socket

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

    class Connection:
        def __init__(self, *args):
            calls.append(args)

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return type(
                "Response",
                (),
                {"status": 302, "getheader": lambda *a: "http://internal/"},
            )()

        def close(self):
            pass

    monkeypatch.setattr(sources, "PinnedConnection", Connection)
    result = sources.fetch_source("http://public.example")
    assert result["error"] == "unsafe_address"
    assert len(calls) == 1


def test_pinned_connection_does_not_resolve_hostname(monkeypatch):
    calls = []
    monkeypatch.setattr(
        socket, "create_connection", lambda target, **kw: calls.append(target)
    )
    connection = sources.PinnedConnection("public.example", 80, "8.8.8.8", False, 2)
    connection.connect()
    assert calls == [("8.8.8.8", 80)]


@pytest.mark.parametrize("truncated", [False, True])
def test_response_closed_on_last_chunk(monkeypatch, truncated):
    """HTTPResponse 读到最后一块会关闭 fp，不能在下轮再访问 fp.raw。"""
    from types import SimpleNamespace

    monkeypatch.setattr(
        sources, "public_target", lambda url: (url, "example.com", 80, "8.8.8.8")
    )

    class Response:
        status = 200
        length = 10

        def __init__(self):
            self.fp = SimpleNamespace(
                raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=lambda _: None))
            )

        def getheader(self, key, default=None):
            return "text/plain" if key == "Content-Type" else default

        def read1(self, size):
            self.fp = None
            self.length = 5 if truncated else 0
            return b"hello"

        def isclosed(self):
            return self.fp is None

    class Connection:
        def __init__(self, *args):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(sources, "PinnedConnection", Connection)
    if truncated:
        with pytest.raises(ResearchError, match="incomplete_source"):
            sources.download("http://example.com/")
    else:
        assert sources.download("http://example.com/")[1] == b"hello"
