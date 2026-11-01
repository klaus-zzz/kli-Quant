"""把量化能力注册到通用服务；底座源码不导入本项目。"""

import json

from fina_agent.applications import Application

from kli_quant.config import Settings
from kli_quant.contracts import Finish, MarketSnapshot
from kli_quant.market import get_market_snapshot
from kli_quant.validation import Calculation, validate_calculation, validate_finish

PROMPT = """你负责 A 股事件研究。先拆解影响链条，再查证支持与反证。
检索方向不是证据立场；转载不能当作独立来源。原文的时间和来源不明要说明缺口。
至少分别执行支持和反向查证；行情不能单独证明事件的因果影响。
公开时间缺失或连续检索无结果时记录缺口，不无限扩大检索。
优先完成用户明确要求的计算、读回和归档，预算内允许以证据不足收尾。
需要计算时调用 get_market_snapshot，execute 用 input_refs 注入该快照。
快照 rows 的数值是十进制字符串，用 Decimal 计算；量是手，成交额是千元。
探索产物格式不限；正式 signal/backtest 只能使用下面的 Calculation 格式。
这里 backtest 只表示带基准的区间收益比较，不是含交易成本的策略回测。
正式观察必须有条件、可确定公开时间的证据、以及 validated signal 产物。
没有充分证据用 insufficient_evidence，查证充分但无机会用 no_opportunity。
finish 的 artifact_ids 只填 publish_artifact 产物编号，不填行情下载编号。
"""


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
        prompt=PROMPT
        + "\nCalculation："
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
