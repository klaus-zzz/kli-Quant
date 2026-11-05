"""原文受控抓取：Scrapling 负责解析与 HTTP，项目保留 URL 和资源预算检查。"""

import base64
import hashlib
import ipaddress
import re
import socket
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from curl_cffi import CurlECode, CurlError, CurlOpt
from scrapling.fetchers import FetcherSession
from scrapling.parser import Selector

from fetcher.network_policy import is_public

MAX_BYTES = 4 * 1024 * 1024
TIMEOUT = 20


class FetchError(Exception):
    """稳定抓取错误分类，不依赖研究业务异常或暴露底层网络信息。"""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def normalize_url(url):
    """统一 URL 解释，拒绝凭据、作用域和易被不同解析器歧义处理的形式。"""
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or any(ord(c) < 33 for c in url)
        or "\\" in url
    ):
        raise FetchError("unsafe_url")
    port = (
        parts.port
        if parts.port is not None
        else (443 if parts.scheme == "https" else 80)
    )
    if port != (443 if parts.scheme == "https" else 80):
        raise FetchError("unsafe_port")
    host = parts.hostname.encode("idna").decode("ascii")
    if not re.fullmatch(r"[a-zA-Z0-9.:-]+", host):
        raise FetchError("unsafe_url")
    try:
        host = str(ipaddress.ip_address(host))
    except ValueError:
        # 拒绝十进制整数、十六进制和缩写 IP，避免系统 DNS 与 curl 解释不一致。
        if re.fullmatch(
            r"(?:0x[0-9a-fA-F]+|[0-9]+)(?:\.(?:0x[0-9a-fA-F]+|[0-9]+))*", host
        ):
            raise FetchError("unsafe_url")
    authority = f"[{host}]" if ":" in host else host
    return urlunsplit((parts.scheme, authority, parts.path or "/", parts.query, ""))


def resolve_public(url):
    """检查全部 A/AAAA 结果；选择一个已验证 IP，下载层不再解析来源域名。"""
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    records = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not is_public(ip) for ip in addresses):
        raise FetchError("unsafe_address")
    return addresses[0]


def fetch_pinned(url, address, **kwargs):
    """固定单次连接 IP，同时由原 URL 决定 Host、SNI 和证书验证域名。"""
    port = urlsplit(url).port or (443 if url.startswith("https:") else 80)
    target = f"[{address}]" if ":" in address else address
    with FetcherSession() as session:
        # Scrapling 未公开 curl_options；此适配点随固定版本的真实 TLS 回归维护。
        session._curl_session.curl_options = {
            CurlOpt.RESOLVE: [f"*:{port}:{target}"],
            CurlOpt.PROXY: "",
            CurlOpt.NOPROXY: "*",
            CurlOpt.PROTOCOLS_STR: "http,https",
            CurlOpt.FRESH_CONNECT: 1,
            CurlOpt.FORBID_REUSE: 1,
        }
        return session.get(url, **kwargs)


def download(url):
    """重定向逐跳复查，限制总时长和原文大小，不加载脚本或子资源。"""
    deadline = time.monotonic() + TIMEOUT
    for _ in range(5):
        url = normalize_url(url)
        address = resolve_public(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("fetch_timeout")
        raw = bytearray()

        def collect(chunk):
            """传输中超限立即终止，不等整个响应进入内存。"""
            if time.monotonic() >= deadline:
                raise FetchError("fetch_timeout")
            if len(raw) + len(chunk) > MAX_BYTES:
                raise FetchError("source_too_large")
            raw.extend(chunk)
            return len(chunk)

        try:
            response = fetch_pinned(
                url,
                address,
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
            raise FetchError(codes.get(exc.code, "fetch_failed")) from None
        if time.monotonic() >= deadline:
            raise FetchError("fetch_timeout")
        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise FetchError("invalid_redirect")
            url = urljoin(url, location)
            continue
        if response.status != 200:
            raise FetchError("fetch_http_error")
        content_type = (
            response.headers.get("content-type", "").split(";")[0].strip().lower()
        )
        if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
            raise FetchError("unsupported_content_type")
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise FetchError("unsupported_encoding")
        return url, bytes(raw), content_type
    raise FetchError("too_many_redirects")


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
    except FetchError as exc:
        document["error"] = exc.code
    except (OSError, ValueError):
        document["error"] = "fetch_failed"
    document["fetched_at"] = datetime.now(UTC).isoformat()
    return document
