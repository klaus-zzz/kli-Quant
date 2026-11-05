"""Scrapling 下载层的真实 HTTP 回归；本地源站不接触生产服务。"""

import base64
import gzip
import hashlib
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fetcher import sources

BODY = b"<html><body><article><p>Fixed evidence.</p></article></body></html>"


@pytest.fixture
def origin(monkeypatch):
    """将不存在的测试域名绑定本地源站，仅夹具放行随机端口和测试地址。"""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle(self):
            """证书拒绝或预算中止时，客户端提前断连是预期行为。"""
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            requests.append((self.path, self.headers["Host"]))
            redirects = {
                "/redirect": "/final",
                "/bad-scheme": "file:///etc/passwd",
                "/loop": "/loop",
                "/missing-location": None,
            }
            if self.path in redirects:
                self.send_response(302)
                if redirects[self.path]:
                    self.send_header("Location", redirects[self.path])
                self.end_headers()
                return
            self.send_response(403 if self.path == "/error" else 200)
            content_type = {
                "/pdf": "application/pdf",
                "/plain": "text/plain",
            }.get(self.path, "text/html")
            self.send_header("Content-Type", content_type)
            body = b"Plain evidence." if self.path == "/plain" else BODY
            if self.path == "/gzip":
                body = gzip.compress(body)
            if self.path == "/truncated":
                self.send_header("Content-Length", "1000")
            elif self.path not in {"/slow", "/large"}:
                # 明确正文长度，HTTPS 正常响应无需靠未发送 close_notify 的断连结束。
                self.send_header("Content-Length", str(len(body)))
            if self.path == "/gzip":
                self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            try:
                if self.path == "/slow":
                    # 持续滴流也必须在总预算耗尽时退出。
                    for _ in range(100):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.02)
                elif self.path == "/large":
                    for _ in range(256):
                        self.wfile.write(b"x" * 1024)
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://source.invalid:{server.server_port}"
    check = sources.normalize_url
    resolve = sources.resolve_public

    def allow_test_origin(url):
        return url if url == base or url.startswith(base + "/") else check(url)

    monkeypatch.setattr(sources, "normalize_url", allow_test_origin)
    monkeypatch.setattr(
        sources,
        "resolve_public",
        lambda url: "127.0.0.1" if url.startswith(base) else resolve(url),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield base, requests, server
    server.shutdown()
    server.server_close()
    thread.join()


def test_download_preserves_archivable_bytes_and_final_url(origin):
    base, requests, _ = origin
    document = sources.fetch_source(base + "/redirect")
    assert document["status"] == "available"
    assert document["canonical_url"] == base + "/final"
    assert base64.b64decode(document["raw_base64"]) == BODY
    assert document["content_sha256"] == hashlib.sha256(BODY).hexdigest()
    assert document["blocks"] == [{"locator": "p:1", "text": "Fixed evidence."}]
    assert [path for path, _ in requests] == ["/redirect", "/final"]
    assert all(host == base.removeprefix("http://") for _, host in requests)


def test_download_plain_text(origin):
    base, _, _ = origin
    assert sources.fetch_source(base + "/plain")["blocks"] == [
        {"locator": "p:1", "text": "Plain evidence."}
    ]


def test_ipv6_connection_binding(origin, monkeypatch):
    """IPv6 绑定同样不解析不存在的域名，HTTP Host 保留来源域名。"""
    _, requests, http_server = origin

    class IPv6Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6

    try:
        server = IPv6Server(("::1", 0), http_server.RequestHandlerClass)
    except OSError:
        pytest.skip("测试环境未启用 IPv6 回环")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(sources, "normalize_url", lambda url: url)
    monkeypatch.setattr(sources, "resolve_public", lambda url: "::1")
    try:
        url = f"http://ipv6.invalid:{server.server_port}/"
        assert sources.fetch_source(url)["status"] == "available"
        assert requests == [("/", f"ipv6.invalid:{server.server_port}")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    "path,error,count",
    [
        ("/bad-scheme", "unsafe_url", 1),
        ("/loop", "too_many_redirects", 5),
        ("/missing-location", "invalid_redirect", 1),
        ("/truncated", "incomplete_source", 1),
        ("/pdf", "unsupported_content_type", 1),
        ("/gzip", "unsupported_encoding", 1),
        ("/error", "fetch_http_error", 1),
    ],
)
def test_download_rejects_bad_responses(origin, path, error, count):
    base, requests, _ = origin
    document = sources.fetch_source(base + path)
    assert document["status"] == "unavailable"
    assert document["error"] == error
    assert "raw_base64" not in document
    assert len(requests) == count


def test_download_stops_oversized_body(origin, monkeypatch):
    base, requests, _ = origin
    monkeypatch.setattr(sources, "MAX_BYTES", 1024)
    document = sources.fetch_source(base + "/large")
    assert document["error"] == "source_too_large"
    assert "raw_base64" not in document
    assert len(requests) == 1


def test_download_timeout_bounds_continuous_response(origin, monkeypatch):
    base, requests, _ = origin
    monkeypatch.setattr(sources, "TIMEOUT", 0.15)
    started = time.monotonic()
    assert sources.fetch_source(base + "/slow")["error"] == "fetch_timeout"
    assert time.monotonic() - started < 1.5
    assert len(requests) == 1


def test_download_accepts_exact_size_limit(origin, monkeypatch):
    base, _, _ = origin
    monkeypatch.setattr(sources, "MAX_BYTES", len(BODY))
    assert sources.fetch_source(base)["status"] == "available"


def test_download_ignores_environment_proxy(origin, monkeypatch):
    """设置不可达代理后仍能直连本地源站，验证实际业务调用的配置。"""
    base, requests, _ = origin
    with socket.socket() as closed_proxy:
        closed_proxy.bind(("127.0.0.1", 0))
        proxy = f"http://127.0.0.1:{closed_proxy.getsockname()[1]}"
        for name in ("http_proxy", "https_proxy", "all_proxy"):
            monkeypatch.setenv(name, proxy)
            monkeypatch.setenv(name.upper(), proxy)
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("NO_PROXY", "")
        assert sources.fetch_source(base)["status"] == "available"
    assert len(requests) == 1


def test_https_verifies_certificate_and_original_hostname(
    origin, tmp_path, monkeypatch
):
    """本地 CA 只在测试中受信；证书不受信或域名不匹配时均须拒绝。"""
    import ssl
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    _, requests, http_server = origin
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "source.invalid")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("source.invalid")]), False
        )
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    names = []
    context.set_servername_callback(lambda sock, name, ctx: names.append(name))
    server = ThreadingHTTPServer(("127.0.0.1", 0), http_server.RequestHandlerClass)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # 仅放行下面构造的随机测试端口，不改生产 URL 校验。
    monkeypatch.setattr(sources, "normalize_url", lambda url: url)
    monkeypatch.setattr(sources, "resolve_public", lambda url: "127.0.0.1")
    url = f"https://source.invalid:{server.server_port}/"
    real_fetch = sources.fetch_pinned

    def fetch_with_test_ca(url, address, **kwargs):
        assert kwargs["verify"] is True
        kwargs["verify"] = str(cert_file)
        return real_fetch(url, address, **kwargs)

    try:
        assert sources.fetch_source(url)["error"] == "fetch_failed"
        monkeypatch.setattr(sources, "fetch_pinned", fetch_with_test_ca)
        assert sources.fetch_source(url)["status"] == "available"
        wrong_host = url.replace("source.invalid", "wrong.invalid")
        assert sources.fetch_source(wrong_host)["error"] == "fetch_failed"
        assert len(requests) == 1
        assert "source.invalid" in names
        assert requests[0][1] == f"source.invalid:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
