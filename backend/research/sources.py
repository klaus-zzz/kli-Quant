"""原文受控抓取：固定公网连接目标，解析器不持有网络能力。"""

import base64
import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from scrapling.parser import Selector

from backend.research.models import ResearchError

MAX_BYTES = 4 * 1024 * 1024
TIMEOUT = 20


def public_target(url):
    """验证全部 DNS 结果，再固定一个已验证的 IP 防止二次解析绕过。"""
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or any(ord(c) < 33 for c in url)
    ):
        raise ResearchError("unsafe_url", 422)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port != (443 if parts.scheme == "https" else 80):
        raise ResearchError("unsafe_port", 422)
    host = parts.hostname.encode("idna").decode("ascii")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = [item[4][0] for item in addresses]
    parsed = [ipaddress.ip_address(ip) for ip in ips]
    if not ips or any(
        not ip.is_global or ip.is_multicast or ip.is_reserved for ip in parsed
    ):
        raise ResearchError("unsafe_address", 422)
    authority = f"[{host}]" if ":" in host else host
    normalized = urlunsplit(
        (parts.scheme, authority, parts.path or "/", parts.query, "")
    )
    return normalized, host, port, ips[0]


class PinnedConnection(http.client.HTTPConnection):
    """只连接已审查的 IP；HTTPS 证书和 SNI 仍使用原域名。"""

    def __init__(self, host, port, ip, tls, timeout):
        super().__init__(host, port, timeout=timeout)
        self.ip, self.tls = ip, tls

    def connect(self):
        self.sock = socket.create_connection((self.ip, self.port), timeout=self.timeout)
        if self.tls:
            self.sock = ssl.create_default_context().wrap_socket(
                self.sock, server_hostname=self.host
            )


def download(url):
    """重定向逐跳复查，限制总时长和原文大小，不加载脚本或子资源。"""
    deadline = time.monotonic() + TIMEOUT
    for _ in range(5):
        url, host, port, ip = public_target(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ResearchError("fetch_timeout")
        parts = urlsplit(url)
        path = urlunsplit(("", "", parts.path, parts.query, ""))
        conn = PinnedConnection(host, port, ip, parts.scheme == "https", remaining)
        try:
            conn.request(
                "GET",
                path,
                headers={
                    "Accept-Encoding": "identity",
                    "User-Agent": "kli-Quant-research/0.1",
                    "Accept": "text/html,text/plain",
                },
            )
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ResearchError("invalid_redirect")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ResearchError("fetch_http_error")
            content_type = response.getheader("Content-Type", "").split(";")[0].lower()
            if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                raise ResearchError("unsupported_content_type")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ResearchError("unsupported_encoding")
            raw = bytearray()
            while not response.isclosed():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ResearchError("fetch_timeout")
                # 小块读取并重新设置剩余超时，防止慢速响应无限占用连接。
                response.fp.raw._sock.settimeout(remaining)
                chunk = response.read1(min(65536, MAX_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise ResearchError("source_too_large")
            if response.length not in {None, 0}:
                raise ResearchError("incomplete_source")
            return url, bytes(raw), content_type
        finally:
            conn.close()
    raise ResearchError("too_many_redirects")


def extract(raw, content_type):
    """只提取保存内容中的文字；发布时间未知时不猜测。"""
    if content_type == "text/plain":
        paragraphs = [p.strip() for p in raw.decode("utf-8").splitlines() if p.strip()]
        return paragraphs, None
    page = Selector(raw, adaptive=False, huge_tree=False)
    nodes = page.xpath("//article//p | //main//p | //body//p | //h1 | //h2 | //h3")
    paragraphs = [n.get_all_text(separator="", strip=False).strip() for n in nodes]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        paragraphs = [
            " ".join(
                page.xpath(
                    "//body//text()[not(ancestor::script or ancestor::style "
                    "or ancestor::noscript)]"
                ).getall()
            ).strip()
        ]
    value = page.xpath('//meta[@property="article:published_time"]/@content').get()
    published = None
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                published = parsed.astimezone(UTC).isoformat()
        except ValueError:
            pass
    return [p for p in paragraphs if p], published


def fetch_source(url):
    """抓取失败也形成可归档记录，错误分类不携带网络异常原文。"""
    document = {"requested_url": url, "status": "unavailable", "blocks": []}
    try:
        canonical, raw, content_type = download(url)
        paragraphs, published = extract(raw, content_type)
        document.update(
            {
                "status": "available" if paragraphs else "empty",
                "canonical_url": canonical,
                "content_type": content_type,
                "raw_base64": base64.b64encode(raw).decode(),
                "content_sha256": hashlib.sha256(raw).hexdigest(),
                "published_at": published,
                "publication_basis": "page_declared" if published else "unknown",
                "independence": "unknown",
                "blocks": [
                    {"locator": f"p:{i}", "text": text}
                    for i, text in enumerate(paragraphs, 1)
                ],
            }
        )
    except ResearchError as exc:
        document["error"] = exc.code
    except (OSError, ValueError, http.client.HTTPException):
        document["error"] = "fetch_failed"
    document["fetched_at"] = datetime.now(UTC).isoformat()
    return document
