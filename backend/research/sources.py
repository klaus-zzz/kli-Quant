"""原文受控抓取：Scrapling 负责 HTTP，项目保留地址与资源预算检查。"""

import base64
import hashlib
import ipaddress
import socket
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from curl_cffi import CurlECode, CurlError
from scrapling.fetchers import Fetcher
from scrapling.parser import Selector

from backend.research.models import ResearchError

MAX_BYTES = 4 * 1024 * 1024
TIMEOUT = 20


def public_target(url):
    """允许任意公网域名；每跳检查全部 DNS 结果并返回规范化 URL。"""
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
    return urlunsplit((parts.scheme, authority, parts.path or "/", parts.query, ""))


def download(url):
    """重定向逐跳复查，限制总时长和原文大小，不加载脚本或子资源。"""
    deadline = time.monotonic() + TIMEOUT
    for _ in range(5):
        url = public_target(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ResearchError("fetch_timeout")
        raw = bytearray()

        def collect(chunk):
            """传输中超限立即终止，不等整个响应进入内存。"""
            if time.monotonic() >= deadline:
                raise ResearchError("fetch_timeout")
            if len(raw) + len(chunk) > MAX_BYTES:
                raise ResearchError("source_too_large")
            raw.extend(chunk)
            return len(chunk)

        try:
            # shortcut: 接受库二次 DNS 解析的风险；需消除此风险时补出站隔离。
            response = Fetcher.get(
                url,
                follow_redirects=False,
                retries=1,
                timeout=remaining,
                proxies={"all": ""},
                verify=True,
                impersonate=None,
                stealthy_headers=False,
                accept_encoding="identity",
                content_callback=collect,
                selector_config={"adaptive": False, "huge_tree": False},
                headers={
                    "User-Agent": "kli-Quant-research/0.1",
                    "Accept": "text/html,text/plain",
                },
            )
        except CurlError as exc:
            codes = {
                CurlECode.OPERATION_TIMEDOUT: "fetch_timeout",
                CurlECode.PARTIAL_FILE: "incomplete_source",
            }
            raise ResearchError(codes.get(exc.code, "fetch_failed")) from None
        if time.monotonic() >= deadline:
            raise ResearchError("fetch_timeout")
        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise ResearchError("invalid_redirect")
            url = urljoin(url, location)
            continue
        if response.status != 200:
            raise ResearchError("fetch_http_error")
        content_type = (
            response.headers.get("content-type", "").split(";")[0].strip().lower()
        )
        if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
            raise ResearchError("unsupported_content_type")
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise ResearchError("unsupported_encoding")
        return url, bytes(raw), content_type
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
    except (OSError, ValueError):
        document["error"] = "fetch_failed"
    document["fetched_at"] = datetime.now(UTC).isoformat()
    return document
