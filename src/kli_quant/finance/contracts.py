"""量化应用的输入与正式结论契约。"""

from datetime import date
from typing import Literal

from fina_agent.agent.contracts import StrictModel
from pydantic import Field, field_validator


class MarketSnapshot(StrictModel):
    instrument_ids: list[str] = Field(min_length=1, max_length=3)
    dataset: Literal["daily"] = "daily"
    start: date
    end: date
    frequency: Literal["1d"] = "1d"
    fields: list[Literal["open", "high", "low", "close", "vol", "amount"]] = Field(
        default_factory=lambda: ["open", "high", "low", "close", "vol", "amount"]
    )
    adjustment: Literal["none"] = "none"

    @field_validator("instrument_ids")
    @classmethod
    def stock_codes(cls, codes: list[str]) -> list[str]:
        """只开放第一版已核实权限和单位的 A 股日线。"""
        import re

        if any(not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", code) for code in codes):
            raise ValueError("只接受完整 A 股代码，例如 600000.SH")
        return sorted(set(codes))


class Finish(StrictModel):
    outcome: Literal["insufficient_evidence", "no_opportunity", "observation"]
    conclusion: str = Field(min_length=1, max_length=4000)
    support: list[str] = Field(default_factory=list, max_length=20)
    contradict: list[str] = Field(default_factory=list, max_length=20)
    artifact_ids: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="只填 publish_artifact 的 artifact_id，不填 snapshot_id 或 execution_id",
    )
    conditions: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=20)
