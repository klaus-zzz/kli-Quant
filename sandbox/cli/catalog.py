"""后端与 CLI 共用的离线契约，不读取任何凭据。"""

import json
import math
import re
from datetime import datetime
from pathlib import Path

# 只有本目录中明确标为积分接口的契约可以执行。
CONTRACTS = {
    item["name"]: item
    for path in sorted((Path(__file__).parent / "contracts").glob("*.json"))
    if (item := json.loads(path.read_text()))["permission"] == "points"
}


def validate(name: str, params: dict, fields: str = "") -> None:
    """按静态契约拒绝未知参数、错误类型和超出边界的查询。"""
    if name not in CONTRACTS:
        raise ValueError("接口未开放")
    contract = CONTRACTS[name]
    schema = contract["input_schema"]
    props = schema["properties"]
    if params.keys() - props.keys():
        raise ValueError("包含未知参数")
    if any(key not in params for key in schema["required"]):
        raise ValueError("缺少必填参数")
    if schema.get("anyOf") and not any(
        all(key in params for key in option["required"]) for option in schema["anyOf"]
    ):
        raise ValueError("缺少条件必填参数")
    for key, value in params.items():
        prop = props[key]
        kind = prop["type"]
        if kind == "string":
            if not isinstance(value, str) or not 1 <= len(value) <= 2000:
                raise ValueError("字符串参数类型或长度无效")
        elif kind == "integer":
            if type(value) is not int:
                raise ValueError("整数参数类型无效")
        elif type(value) not in (int, float):
            raise ValueError("数值参数类型无效")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("数值必须有限")
        # 分页只对官方声明的参数生效，数值字符串保持上游原类型。
        if key in ("limit", "offset"):
            if isinstance(value, str) and not value.isascii():
                raise ValueError("分页参数无效")
            try:
                number = int(value)
            except (ValueError, TypeError):
                raise ValueError("分页参数无效") from None
            low, high = (1, 10000) if key == "limit" else (0, 1000000)
            if not low <= number <= high:
                raise ValueError("分页参数超出边界")
        if isinstance(value, str):
            desc = prop["description"].upper()
            # 日、月、季度各有含义，不能把宏观季度误当成八位日期。
            fmt = None
            if "YYYY-MM-DD HH:MM:SS" in desc:
                fmt = "%Y-%m-%d %H:%M:%S"
            elif "YYYYMMDD" in desc or key.endswith("_date") or key == "date":
                fmt = "%Y%m%d"
            elif "YYYYMM" in desc or key in ("m", "month", "start_m", "end_m"):
                fmt = "%Y%m"
            elif key == "period":
                fmt = "%Y%m%d"
            if fmt:
                try:
                    values = value.split(",") if "逗号" in desc else [value]
                    for part in values:
                        if datetime.strptime(part, fmt).strftime(fmt) != part:
                            raise ValueError
                except ValueError:
                    raise ValueError("日期参数无效") from None
            if key in ("q", "start_q", "end_q") and not re.fullmatch(
                r"\d{4}Q[1-4]", value
            ):
                raise ValueError("季度参数无效")
    for start, end in (("start_date", "end_date"), ("start_m", "end_m")):
        if start in params and end in params and params[start] > params[end]:
            raise ValueError("开始日期不得晚于结束日期")
    if not isinstance(fields, str) or len(fields) > 20000:
        raise ValueError("字段选择无效")
    selected = fields.split(",") if fields else []
    allowed = {field["name"] for field in contract["output_fields"]}
    if len(selected) != len(set(selected)) or set(selected) - allowed:
        raise ValueError("包含未知或重复的输出字段")
