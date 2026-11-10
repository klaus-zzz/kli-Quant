"""仅适配本项目沙箱的接回协议，不提供通用集群管理代理。"""

import hmac
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from backend.research.models import ResearchError

router = APIRouter(prefix="/api/agent/cube", include_in_schema=False)


def control(request):
    """控制端凭据与聊天凭据分离，沙箱网络规则不放行此路由。"""
    runtime = getattr(request.app.state, "agent", None)
    if runtime is None:
        raise ResearchError("agent_not_ready", 503)
    expected = runtime.env["KLI_QUANT_CONTROL_TOKEN"]
    supplied = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise ResearchError("unauthorized", 401)
    return runtime


async def upstream(runtime, method, path, *, params=None, body=None):
    """目标和认证只能来自宿主配置，错误正文不会穿透给调用方。"""
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        response = await client.request(
            method,
            runtime.env["CUBESANDBOX_API_URL"].rstrip("/") + path,
            headers={"X-API-Key": runtime.env["E2B_API_KEY"]},
            params=params,
            json=body,
        )
    if response.status_code >= 400:
        raise ResearchError("sandbox_control_unavailable", response.status_code)
    return response


@router.get("/v2/sandboxes")
@router.get("/sandboxes")
async def list_sandboxes(request: Request):
    """保留 SDK 原始列表结构，但只返回数据库登记且有效的本项目实例。"""
    runtime = control(request)
    with runtime.repo.transaction() as conn:
        allowed = {
            r["sandbox_id"]
            for r in conn.execute(
                "SELECT sandbox_id FROM agent_sandboxes "
                "WHERE active AND expires_at>now()"
            )
        }
    response = await upstream(
        runtime,
        "GET",
        request.url.path.removeprefix("/api/agent/cube"),
        params=request.query_params,
    )
    body = response.json()
    if not isinstance(body, list):
        raise ResearchError("sandbox_protocol_mismatch", 502)
    return [row for row in body if row.get("sandboxID") in allowed]


@router.api_route("/sandboxes/{sandbox_id}", methods=["GET", "DELETE"])
@router.post("/sandboxes/{sandbox_id}/{action}")
async def sandbox_action(sandbox_id: str, request: Request, action: str = ""):
    """只允许接回、核对和有限续期；创建由可信业务执行器独占。"""
    runtime = control(request)
    if (request.method, action) not in {
        ("GET", ""),
        ("DELETE", ""),
        ("POST", "connect"),
        ("POST", "timeout"),
    }:
        raise ResearchError("not_found", 404)
    with runtime.repo.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM agent_sandboxes WHERE sandbox_id=%s AND active "
            "AND expires_at>now()",
            (sandbox_id,),
        ).fetchone()
    if row is None:
        raise ResearchError("not_found", 404)
    body = None
    if action:
        # 忽略客户端要求的任意 TTL，不允许超过研究截止点或会话授权期。
        body = {
            "timeout": max(
                1, int((row["expires_at"] - datetime.now(UTC)).total_seconds())
            )
        }
    response = await upstream(
        runtime,
        request.method,
        f"/sandboxes/{sandbox_id}" + (f"/{action}" if action else ""),
        body=body,
    )
    if request.method == "DELETE":
        with runtime.repo.transaction() as conn:
            conn.execute(
                "UPDATE agent_sandboxes SET active=false WHERE sandbox_id=%s",
                (sandbox_id,),
            )
    if not response.content:
        return Response(status_code=response.status_code)
    result = response.json()
    if action == "connect":
        result["trafficAccessToken"] = row["traffic_token"]
        # e2b 只自动发送 envd 头；窄数据代理验证此实例令牌后转换私有访问头。
        result["envdAccessToken"] = row["traffic_token"]
    return JSONResponse(result, status_code=response.status_code)
