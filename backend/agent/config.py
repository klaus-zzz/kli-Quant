"""只在显式启用时读取集中 Agent 配置，缺项即拒绝启动。"""

import os
import re
from ipaddress import ip_address
from urllib.parse import urlsplit

from dotenv import dotenv_values

from backend.agent.runtime import Runtime


def configured_runtime(research):
    path = os.environ.get("KLI_QUANT_AGENT_ENV_FILE")
    if not path:
        return None
    if research is None:
        raise ValueError("启用 Agent 前必须配置研究数据库与归档")
    values = dotenv_values(path, interpolate=False)
    required = (
        "CUBESANDBOX_API_URL",
        "CUBESANDBOX_DOMAIN",
        "CUBESANDBOX_TEMPLATE_ID",
        "CUBE_PROXY_NODE_IP",
        "E2B_API_KEY",
        "KLI_QUANT_BACKEND_URL",
        "OMNIAGENT_URL",
        "OMNIAGENT_GATEWAY_TOKEN",
        "KLI_QUANT_CHAT_TOKEN",
        "KLI_QUANT_CONTROL_TOKEN",
    )
    for key in required:
        if not values.get(key):
            raise ValueError(f"缺少 Agent 配置：{key}")
    ip_address(values["CUBE_PROXY_NODE_IP"])
    for key in ("KLI_QUANT_CHAT_TOKEN", "KLI_QUANT_CONTROL_TOKEN"):
        if len(values[key]) < 32:
            raise ValueError(f"配置须使用至少 32 字符的随机值：{key}")
    if not re.fullmatch(r"e2b_[0-9a-fA-F]{32,}", values["KLI_QUANT_CONTROL_TOKEN"]):
        raise ValueError("控制 Token 须为 e2b_ 加至少 32 位随机十六进制字符")
    if (
        len(
            {
                values[k]
                for k in (
                    "KLI_QUANT_CHAT_TOKEN",
                    "KLI_QUANT_CONTROL_TOKEN",
                    "OMNIAGENT_GATEWAY_TOKEN",
                )
            }
        )
        != 3
    ):
        raise ValueError("聊天、Gateway 与沙箱控制端必须使用不同凭据")
    url = urlsplit(values["OMNIAGENT_URL"])
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ValueError("OMNIAGENT_URL 必须是无凭据的 HTTP 服务地址")
    return Runtime(research, values)
