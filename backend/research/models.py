"""集中定义输入和正式产物；拒绝模型覆盖后端控制字段。"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=12000)]


class Model(BaseModel):
    """统一禁止未知字段和无意义的空白字符串。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Submission(Model):
    event: Text | None = None
    url: Annotated[str, Field(max_length=2048)] | None = None
    question: Text
    previous_run_id: UUID | None = None

    @model_validator(mode="after")
    def require_input(self):
        """事件与原文链接至少提供一个；网络校验在采集时执行。"""
        if not self.event and not self.url:
            raise ValueError("需要事件或链接")
        if self.url and not self.url.startswith(("https://", "http://")):
            raise ValueError("链接协议无效")
        return self


class Reference(Model):
    evidence_id: UUID
    locator: Annotated[str, Field(min_length=1, max_length=200)]


class Hop(Model):
    id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
    parents: list[str] = Field(default_factory=list, max_length=100)
    trigger: Text
    question: Text
    entities: list[Text] = Field(min_length=1, max_length=100)
    time_scope: Text
    finding: Text
    supports: list[Reference] = Field(default_factory=list, max_length=100)
    counters: list[Reference] = Field(default_factory=list, max_length=100)
    alternatives: list[Text] = Field(max_length=100)
    gaps: list[Text] = Field(max_length=100)
    conditions: Text
    invalidation: Text


class Revision(Model):
    hop_id: str
    change: Literal["maintained", "changed", "withdrawn"]
    reason: Text


class Artifact(Model):
    """正式计算只接受明确口径和受信执行记录对应的输出。"""

    evidence_id: UUID
    kind: Literal["observation", "backtest"]
    execution_id: UUID
    inputs: list[UUID] = Field(min_length=1, max_length=100)
    calendar_id: UUID
    trading_dates: list[str] = Field(min_length=1, max_length=10000)
    price_unit: Literal["CNY/share"]
    return_unit: Literal["ratio"]
    adjustment: Literal["none", "forward", "backward"]
    adjustment_factor_id: UUID | None = None
    return_basis: Literal["simple_close_to_close"]
    fee_bps: float = Field(ge=0, le=10000, allow_inf_nan=False)
    fee_basis: Literal["per_side_turnover"]


class ResultBundle(Model):
    conclusion: Literal[
        "conditional_observation", "insufficient_evidence", "no_opportunity"
    ]
    summary: Text
    valid_from: datetime
    valid_until: datetime
    conditions: Text
    invalidation: Text
    gaps: list[Text] = Field(max_length=100)
    hops: list[Hop] = Field(min_length=1, max_length=100)
    artifacts: list[Artifact] = Field(default_factory=list, max_length=20)
    revisions: list[Revision] = Field(default_factory=list, max_length=100)


class ResearchError(Exception):
    """稳定错误分类，避免把底层异常和敏感配置传给调用方。"""

    def __init__(self, code: str, status: int = 409):
        self.code = code
        self.status = status
        super().__init__(code)
