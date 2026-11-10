"""为已登记私有沙箱转换 SDK 数据面认证头，不开放通用网络代理。"""

import base64
import hmac
from datetime import UTC, datetime
from ipaddress import ip_address

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.research.models import ResearchError

router = APIRouter(prefix="/api/agent/cube/envd", include_in_schema=False)
PROCESS = {
    "List",
    "Connect",
    "Start",
    "Update",
    "StreamInput",
    "SendInput",
    "SendSignal",
    "CloseStdin",
}
FILESYSTEM = {
    "Stat",
    "MakeDir",
    "Move",
    "ListDir",
    "Remove",
    "WatchDir",
    "CreateWatcher",
    "GetWatcherEvents",
    "RemoveWatcher",
}


def target(request, path):
    """目标端口、实例和主机都由服务端确定，调用方只选允许的 envd 方法。"""
    runtime = getattr(request.app.state, "agent", None)
    if runtime is None:
        raise ResearchError("agent_not_ready", 503)
    service, _, method = path.partition("/")
    allowed = (
        path == "files"
        and request.method in {"GET", "POST"}
        or path == "health"
        and request.method == "GET"
        or request.method == "POST"
        and (
            service == "process.Process"
            and method in PROCESS
            or service == "filesystem.Filesystem"
            and method in FILESYSTEM
        )
    )
    if not allowed:
        raise ResearchError("not_found", 404)
    with runtime.repo.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM agent_sandboxes WHERE sandbox_id=%s "
            "AND active AND expires_at>now()",
            (request.headers.get("E2b-Sandbox-Id", ""),),
        ).fetchone()
    supplied = request.headers.get("X-Access-Token", "")
    if not row or not hmac.compare_digest(
        supplied.encode(), row["traffic_token"].encode()
    ):
        raise ResearchError("unauthorized", 401)
    # 此地址与 CubeSDK 的直连代理一致，不能从客户端传入 Host、URL 或端口。
    address = str(ip_address(runtime.env["CUBE_PROXY_NODE_IP"]))
    host = f"49983-{row['sandbox_id']}.{runtime.env['CUBESANDBOX_DOMAIN']}"
    return row, f"http://{address}/{path}", host


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    """流式透传 Connect RPC；头白名单、输入上限与截止点限制资源占用。"""
    from starlette.concurrency import run_in_threadpool

    row, url, host = await run_in_threadpool(target, request, path)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 16 * 1024 * 1024:
            raise ResearchError("request_too_large", 413)
    headers = {
        "Host": host,
        "e2b-traffic-access-token": row["traffic_token"],
        "Authorization": "Basic " + base64.b64encode(b"root:").decode(),
        **{
            k: v
            for k, v in request.headers.items()
            if k.lower()
            in {
                "content-type",
                "connect-protocol-version",
                "connect-timeout-ms",
                "connect-content-encoding",
                "connect-accept-encoding",
                "x-envd-user",
            }
        },
    }
    timeout = max(1, min(180, (row["expires_at"] - datetime.now(UTC)).total_seconds()))
    client = httpx.AsyncClient(timeout=timeout, trust_env=False)
    try:
        response = await client.send(
            client.build_request(
                request.method,
                url,
                headers=headers,
                params=request.query_params,
                content=bytes(raw),
            ),
            stream=True,
        )
    except BaseException as exc:
        await client.aclose()
        if isinstance(exc, httpx.HTTPError):
            raise ResearchError("sandbox_transport_unavailable", 502) from None
        raise

    async def stream():
        size = 0
        try:
            async for chunk in response.aiter_raw():
                size += len(chunk)
                if size > 32 * 1024 * 1024 or datetime.now(UTC) >= row["expires_at"]:
                    break
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=response.status_code,
        headers={
            k: v
            for k, v in response.headers.items()
            if k.lower()
            in {
                "content-type",
                "content-encoding",
                "connect-content-encoding",
            }
        },
    )
