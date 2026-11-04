"""将静态契约注册为独立 axi 工具，执行时仅访问本地受控后端。"""

import inspect
import json
import os
from typing import Annotated

import httpx
from axi import tool
from pydantic import Field

from sandbox.cli.catalog import CONTRACTS, validate


def make_tool(contract):
    """签名来自离线契约，公开装饰器负责注册和生成工具描述。"""
    name = contract["name"]

    def execute(**params):
        fields = params.pop("fields", "")
        validate(name, params, fields)
        base = os.environ.get("KLI_QUANT_BACKEND_URL", "http://127.0.0.1:18100")
        try:
            response = httpx.post(
                f"{base.rstrip('/')}/api/tushare/{name}",
                json={"params": params, "fields": fields},
                timeout=25,
                trust_env=False,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            # 网络异常可能包含连接配置，不把原始异常交给模型。
            return {"status": "service_error", "data": None, "message": "后端不可用"}

    parameters, annotations = [], {}
    schema = contract["input_schema"]
    for key, prop in schema["properties"].items():
        kind = {"string": str, "integer": int, "number": float}[prop["type"]]
        annotation = Annotated[kind, Field(description=prop["description"])]
        annotations[key] = annotation
        parameters.append(
            inspect.Parameter(
                key,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=annotation,
                default=inspect.Parameter.empty if key in schema["required"] else None,
            )
        )
    annotations["fields"] = Annotated[
        str, Field(description="逗号分隔的输出字段；留空采用上游默认字段")
    ]
    parameters.append(
        inspect.Parameter(
            "fields",
            inspect.Parameter.KEYWORD_ONLY,
            default="",
            annotation=annotations["fields"],
        )
    )
    execute.__name__ = name
    execute.__annotations__ = annotations
    execute.__signature__ = inspect.Signature(parameters)
    description = (
        contract["description"] + "\n条件说明：" + "；".join(contract["corrections"])
    )
    description += "\n输出字段及口径：" + json.dumps(
        contract["output_fields"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return tool(
        name=name,
        description=description,
        annotations={"readOnlyHint": True, "destructiveHint": False},
    )(execute)


# 导入只加载契约和注册工具，不连接后端或读取数据源凭据。
for _contract in CONTRACTS.values():
    make_tool(_contract)
