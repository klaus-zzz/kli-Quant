"""把量化能力注册到通用服务；底座源码不导入本项目。"""

import json

from fina_agent.applications import Application

from kli_quant.config import Settings
from kli_quant.contracts import Finish, MarketSnapshot
from kli_quant.market import get_market_snapshot
from kli_quant.validation import Calculation, validate_calculation, validate_finish


def market_tool(store, args, settings):
    """只在后端取出数据源凭据；固定输入截止点仍由底座传入。"""
    return get_market_snapshot(store, args, Settings())


def artifact_validator(store, content, purpose, execution):
    """金融引用需求在应用中生成，底座只检查声明引用是否齐全。"""
    result = validate_calculation(store, content, purpose, execution)
    calculation = result["calculation"]
    result["required_refs"] = [calculation["snapshot_id"], *calculation["evidence_ids"]]
    return result


def missing_services():
    return [] if Settings().tushare_token else ["tushare"]


def create_application():
    """应用版本固定到任务输入；规则变更必须升级版本。"""
    return Application(
        id="kli-quant",
        label="kli-Quant 量化研究",
        version="0.1.0",
        prompt="正式 signal/backtest 产物必须符合 Calculation："
        + json.dumps(Calculation.model_json_schema(), ensure_ascii=False),
        tools={
            "get_market_snapshot": (
                MarketSnapshot,
                "获取固定版本的 A 股日线快照，明确单位、时间与缺失。",
                market_tool,
            )
        },
        finish_model=Finish,
        validate_finish=validate_finish,
        validate_artifact=artifact_validator,
        missing_services=missing_services,
    )
