"""后端只委托隔离抓取服务；服务不可用时不回退到后端直连。"""

from datetime import UTC, datetime

import httpx


def fetch_source(url):
    """固定内部服务地址不接受模型覆盖，也不读取宿主代理设置。"""
    try:
        with httpx.Client(
            trust_env=False, timeout=30, follow_redirects=False
        ) as client:
            response = client.post(
                "http://research-fetcher:18101/fetch", json={"url": url}
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return {
            "requested_url": url,
            "status": "unavailable",
            "error": "fetcher_unavailable",
            "blocks": [],
            "fetched_at": datetime.now(UTC).isoformat(),
        }
