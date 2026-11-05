"""可选的真实 HTTP 能力验证；安装 fetchers 扩展后运行，不访问外网。"""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("curl_cffi")
from curl_cffi import CurlError, CurlOpt  # noqa: E402
from curl_cffi.requests import Session  # noqa: E402
from scrapling.fetchers import Fetcher, FetcherSession  # noqa: E402


@pytest.fixture
def origin(monkeypatch):
    """本地源站模拟跳转、慢响应和截断；清除代理只作用于测试进程。"""
    for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append((self.path, self.headers["Host"]))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/final")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            if self.path == "/truncated":
                self.send_header("Content-Length", "100")
            self.end_headers()
            try:
                if self.path == "/slow":
                    # 持续滴流不能把总耗时限制变成可无限续期的读取超时。
                    for _ in range(100):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.02)
                elif self.path == "/large":
                    for _ in range(256):
                        self.wfile.write(b"x" * 1024)
                else:
                    self.wfile.write(b"<p>Fixed evidence.</p>")
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", requests
    server.shutdown()
    server.server_close()
    thread.join()


def fetch(url, **kwargs):
    """关闭浏览器伪装和重试，单独验证静态抓取的网络行为。"""
    return Fetcher.get(
        url, impersonate=None, stealthy_headers=False, retries=1, **kwargs
    )


def test_fetcher_downloads_and_parses(origin):
    base, requests = origin
    response = fetch(base, follow_redirects=False)
    assert response.status == 200
    assert response.xpath("//p/text()").get() == "Fixed evidence."
    assert len(requests) == 1


def test_fetcher_can_leave_redirects_to_caller(origin):
    base, requests = origin
    response = fetch(base + "/redirect", follow_redirects=False)
    assert response.status == 302
    assert response.headers["location"] == "/final"
    assert len(requests) == 1


def test_fetcher_safe_mode_rejects_private_redirect(origin):
    base, requests = origin
    with pytest.raises(CurlError):
        fetch(base + "/redirect", follow_redirects="safe")
    assert len(requests) == 1


def test_fetcher_timeout_bounds_continuous_response(origin):
    base, requests = origin
    started = time.monotonic()
    with pytest.raises(CurlError) as error:
        fetch(base + "/slow", timeout=0.15, follow_redirects=False)
    assert error.value.code == 28
    assert time.monotonic() - started < 1.5
    assert len(requests) == 1


def test_fetcher_callback_stops_oversized_body(origin):
    """读取回调在超过预算时终止传输，不等待整个响应装入内存。"""
    base, _ = origin
    body = bytearray()

    def collect(chunk):
        if len(body) + len(chunk) > 1024:
            raise ValueError("source_too_large")
        body.extend(chunk)
        return len(chunk)

    with pytest.raises(ValueError, match="source_too_large"):
        fetch(base + "/large", content_callback=collect, follow_redirects=False)
    assert len(body) <= 1024


def test_fetcher_rejects_truncated_body(origin):
    base, requests = origin
    with pytest.raises(CurlError) as error:
        fetch(base + "/truncated", follow_redirects=False)
    assert error.value.code == 18
    assert len(requests) == 1


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="Scrapling 0.5.1 未公开 curl 会话选项，无法固定已审查的 IP",
)
def test_fetcher_pins_verified_address(origin):
    """域名无有效解析也必须只连接指定 IP，不能交给库再次解析。"""
    base, requests = origin
    port = base.rsplit(":", 1)[1]
    response = fetch(
        f"http://research.invalid:{port}/",
        follow_redirects=False,
        curl_options={CurlOpt.RESOLVE: [f"research.invalid:{port}:127.0.0.1"]},
    )
    assert response.status == 200
    assert requests == [("/", f"research.invalid:{port}")]


def test_fetcher_session_also_rejects_network_options():
    """会话公开构造器同样不接受固定 IP 选项，避免误判为调用位置错误。"""
    with pytest.raises(TypeError):
        FetcherSession(curl_options={})


def test_underlying_curl_supports_pinning_and_proxy_isolation(origin, monkeypatch):
    """定位限制在 Scrapling 封装层；使用 curl 的公开会话配置即可满足。"""
    base, requests = origin
    port = base.rsplit(":", 1)[1]
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    with Session(
        trust_env=False,
        curl_options={CurlOpt.RESOLVE: [f"research.invalid:{port}:127.0.0.1"]},
    ) as session:
        response = session.get(f"http://research.invalid:{port}/", timeout=2)
    assert response.status_code == 200
    assert requests == [("/", f"research.invalid:{port}")]


def test_fetcher_empty_proxy_mapping_disables_environment(origin, monkeypatch):
    """公开 proxies 参数可以禁用代理，不需要访问私有会话设置。"""
    base, requests = origin
    # 占用一个不监听的端口，确保代理目标不可连接且不会访问其他服务。
    with socket.socket() as closed_proxy:
        closed_proxy.bind(("127.0.0.1", 0))
        port = closed_proxy.getsockname()[1]
        monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{port}")
        with pytest.raises(CurlError):
            fetch(base, timeout=1)
        assert requests == []
        response = fetch(base, proxies={"all": ""}, timeout=1)
    assert response.status == 200
    assert len(requests) == 1
