"""后端只委托隔离抓取服务；服务不可用时不回退到后端直连。"""

import os
from datetime import UTC, datetime

import httpx


def fetch_source(url):
    """部署环境决定服务地址，业务请求不能覆盖，也不读取代理设置。"""
    try:
        endpoint = os.environ.get("RESEARCH_FETCHER_URL", "").strip()
        if not endpoint:
            raise ValueError("未配置抓取服务地址")
        with httpx.Client(
            trust_env=False, timeout=30, follow_redirects=False
        ) as client:
            response = client.post(endpoint, json={"url": url})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return {
            "requested_url": url,
            "status": "unavailable",
            "error": "fetcher_unavailable",
            "blocks": [],
            "fetched_at": datetime.now(UTC).isoformat(),
        }
