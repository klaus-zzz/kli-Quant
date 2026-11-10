"""研究薄客户端：只传业务参数，不读取或发送任何凭据。"""

import hashlib
import json
import os

import httpx
from axi import tool


def request(method, path, payload=None, key=None, run_id=""):
    """宿主代理负责身份注入；错误只返回后端稳定分类。"""
    base = os.environ["KLI_QUANT_BACKEND_URL"].rstrip("/")
    try:
        response = httpx.request(
            method,
            base + "/api/research" + path,
            json=payload,
            headers={
                **({"Idempotency-Key": key} if key else {}),
                **({"X-Research-Run": run_id} if run_id else {}),
            },
            timeout=70,
            trust_env=False,
        )
        if response.status_code >= 400:
            return {"error": response.json().get("error", "research_unavailable")}
        return response.json()
    except (httpx.HTTPError, ValueError):
        return {"error": "research_unavailable"}


@tool(
    name="context",
    description=(
        "获取当前研究的固定问题、预算、截止时间及正式结果 JSON Schema。"
        "聊天模式返回会话标识。"
    ),
)
def context(run_id: str = "") -> dict:
    return request("GET", "/context", run_id=run_id)


@tool(
    name="submit",
    description=(
        "登记多跳研究，返回 run_id 和 agent 参数；"
        "随后必须原样调用原生 agent 工具启动后台研究。"
        "event 或 url 至少一个。复核旧结论用 previous_run_id 新建版本。"
    ),
)
def submit(
    question: str, event: str = "", url: str = "", previous_run_id: str = ""
) -> dict:
    payload = {"question": question}
    payload.update(
        {
            k: v
            for k, v in {
                "event": event,
                "url": url,
                "previous_run_id": previous_run_id,
            }.items()
            if v
        }
    )
    # 同一用户消息的相同提交固定一个幂等键；消息标识不是认证身份。
    message = os.environ.get("KLI_QUANT_MESSAGE_ID", "")
    if not message:
        return {"error": "message_context_missing"}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return request("POST", "/runs", payload, key=f"{message}:{digest}")


@tool(name="status", description="查询本会话研究进度、预算及取消状态。")
def status(run_id: str) -> dict:
    return request("GET", f"/runs/{run_id}")


@tool(
    name="cancel",
    description="取消本会话研究；cancelling 表示正在确认执行停止，不等于已经取消。",
)
def cancel(run_id: str) -> dict:
    return request("POST", f"/runs/{run_id}/cancel")


@tool(
    name="result",
    description="读取研究发布后的固定版本、哈希及完整结果。没有正式结果时返回错误。",
)
def result(run_id: str) -> dict:
    return request("GET", f"/runs/{run_id}/result")


@tool(
    name="source",
    description=(
        "在后端受控网络读取公网原文，保存固定证据，"
        "返回 evidence_id、段落及时间信息。仅研究任务可用。"
    ),
)
def source(run_id: str, url: str) -> dict:
    return request("POST", "/source", {"url": url}, run_id=run_id)


@tool(
    name="evidence",
    description="读取当前研究或关联旧版本的固定证据；禁止读取其他会话。",
)
def evidence(run_id: str, evidence_id: str) -> dict:
    return request("GET", f"/evidence/{evidence_id}", run_id=run_id)


@tool(
    name="execute",
    description=(
        "在当前任务沙箱执行 Python 代码并归档。inputs 为证据 ID 列表；"
        "代码用 json.load(sys.stdin) 读取以证据 ID 为键的固定输入。"
        "stdout 打印 JSON 可作为产物；检查 exit_code，失败后修改代码再执行。"
    ),
)
def execute(run_id: str, code: str, inputs: list[str]) -> dict:
    return request("POST", "/execute", {"code": code, "inputs": inputs}, run_id=run_id)


@tool(
    name="publish",
    description=(
        "提交正式研究结果。先用 context 获取 Schema；"
        "必须说明多跳支持、反证、缺口、条件及失效条件，可如实返回证据不足。"
        "后端校验后才发布；返回 errors/published=false 时，在原截止前修正草稿再调用。"
    ),
)
def publish(run_id: str, draft: dict) -> dict:
    return request("POST", "/publish", draft, run_id=run_id)
