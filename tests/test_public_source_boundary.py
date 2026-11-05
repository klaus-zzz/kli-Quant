"""公网地址边界；所有 DNS 和网络请求均由测试控制。"""

import socket
from types import SimpleNamespace

import pytest

from backend.research import sources


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.1"],
        ["169.254.169.254"],
        ["100.100.100.200"],
        ["168.63.129.16"],
        ["198.18.0.1"],
        ["224.0.0.1"],
        ["::1"],
        ["fc00::1"],
        ["fe80::1"],
        ["::ffff:127.0.0.1"],
        ["64:ff9b::a00:1"],
        ["2002:7f00:1::"],
        ["2001::1"],
        ["93.184.216.34", "10.0.0.1"],
        ["2606:4700:4700::1111", "fc00::1"],
        ["93.184.216.34", "::1"],
        [],
    ],
)
def test_unsafe_dns_never_reaches_transport(monkeypatch, addresses):
    """任一解析结果不安全即拒绝，包括平台元数据与 IPv6 过渡地址。"""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET6 if ":" in ip else socket.AF_INET, 1, 6, "", (ip, 80))
            for ip in addresses
        ],
    )
    calls = []

    def fetch(url, address, **kwargs):
        calls.append(url)
        kwargs["content_callback"](b"should not be downloaded")
        return SimpleNamespace(status=200, headers={"content-type": "text/plain"})

    monkeypatch.setattr(sources, "fetch_pinned", fetch)
    result = sources.fetch_source("http://source.example/")
    assert result.get("error") == "unsafe_address"
    assert calls == []


@pytest.mark.parametrize("redirect", [False, True])
def test_next_attempt_and_same_host_redirect_recheck_dns(monkeypatch, redirect):
    """同名域名变为私网后，下一次抓取或重定向均拒绝，不复用旧校验。"""
    answers = iter(["93.184.216.34", "127.0.0.1"])
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", (next(answers), 80))],
    )
    calls = []

    def fetch(url, address, **kwargs):
        calls.append(address)
        assert kwargs["retries"] == 1
        assert kwargs["follow_redirects"] is False
        kwargs["content_callback"](b"public evidence")
        return SimpleNamespace(
            status=302 if redirect else 200,
            headers={"location": "/next", "content-type": "text/plain"},
        )

    monkeypatch.setattr(sources, "fetch_pinned", fetch)
    result = sources.fetch_source("https://source.example/")
    if not redirect:
        assert result["status"] == "available"
        result = sources.fetch_source("https://source.example/")
    assert result["error"] == "unsafe_address"
    assert calls == ["93.184.216.34"]


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:4700:4700::1111"])
def test_transport_receives_only_validated_ip(monkeypatch, address):
    """连接参数使用此次校验的地址，不将域名交回连接层解析。"""
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 80))]
    )
    options = {}

    class Session:
        def __enter__(self):
            self._curl_session = SimpleNamespace(curl_options={})
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            options.update(self._curl_session.curl_options)
            assert url == "https://source.example/"
            assert kwargs["verify"] is True
            kwargs["content_callback"](b"fixed bytes")
            return SimpleNamespace(status=200, headers={"content-type": "text/plain"})

    monkeypatch.setattr(sources, "FetcherSession", Session)
    assert sources.fetch_source("https://source.example/")["status"] == "available"
    target = f"[{address}]" if ":" in address else address
    assert options[sources.CurlOpt.RESOLVE] == [f"*:443:{target}"]
    assert options[sources.CurlOpt.PROXY] == ""
    assert options[sources.CurlOpt.NOPROXY] == "*"
