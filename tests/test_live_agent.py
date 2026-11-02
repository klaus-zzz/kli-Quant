"""模型驱动的真实研究与新证据复核；仅显式 live 标记启用。"""

import os

import pytest
from fastapi.testclient import TestClient
from fina_agent.agent.storage import Archive
from fina_agent.main import create_app
from fina_agent.models import Record, Research, Run, ToolCall
from fina_agent.worker import tick
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from kli_quant.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("FINA_LIVE_AGENT") != "1",
        reason="model-driven live research requires explicit opt-in",
    ),
]


def test_real_agent_and_new_evidence_review():
    """结论允许证据不足，但必须实际走过查证、行情和沙箱链路。"""
    url = os.environ.get("FINA_TEST_DATABASE_URL")
    assert url, "dedicated test database required"
    settings = Settings(database_url=url)
    engine = create_engine(url)
    archive = Archive(settings)
    research_id = None
    with TestClient(create_app(settings)) as client:
        try:
            response = client.post(
                "/api/researches",
                json={
                    "application": "kli-quant",
                    "event": "研究利率政策变化是否足以支持浦发银行（600000.SH）的短期观察。"
                    "请核实政策支持和净息差承压等反证。必须获取2026-10-20到2026-10-30的"
                    "固定日线，在沙箱实际编写执行代码计算区间收益、读回并归档探索产物。"
                    "行情波动不能当成政策因果证明；材料时间未知时明确证据不足。",
                    "source_urls": ["https://www.pbc.gov.cn/"],
                },
            )
            assert response.status_code == 202, "live API could not create research"
            initial = response.json()
            research_id = initial["research_id"]
            assert tick(settings, engine)
            first = client.get(f"/api/runs/{initial['run_id']}").json()
            print("first run:", first["status"], first["stop_reason"])
            for call in first["calls"]:
                result = call["result"] or {}
                print(
                    call["step"],
                    call["name"],
                    result.get("status"),
                    (result.get("error") or {}).get("code", ""),
                )
            assert first["status"] in {"completed", "inconclusive"}
            kinds = {row["kind"] for row in first["records"]}
            assert {
                "document",
                "evidence",
                "snapshot",
                "execution",
                "artifact",
                "judgment",
            } <= kinds
            original_judgments = [row for row in first["records"] if row["kind"] == "judgment"]
            assert all(
                row["data"]["evaluation_not_before"] == row["data"]["published_at"]
                for row in original_judgments
            )
            response = client.post(
                f"/api/researches/{research_id}/runs",
                json={
                    "application": "kli-quant",
                    "event": "新增待核实线索：净息差承压可能抵消政策支持，但目前没有已验证的"
                    "公司披露。复核上一轮判断，不把此用户线索当成事实，不重复行情计算，"
                    "资料不足时直接保存证据不足的结论与下一步观察条件。",
                },
            )
            assert response.status_code == 202
            assert tick(settings, engine)
            second = client.get(f"/api/runs/{response.json()['run_id']}").json()
            print("review run:", second["status"], second["stop_reason"])
            assert second["status"] in {"completed", "inconclusive"}
            assert second["parent_run_id"] == initial["run_id"]
            unchanged = client.get(f"/api/runs/{initial['run_id']}").json()
            assert [
                row for row in unchanged["records"] if row["kind"] == "judgment"
            ] == original_judgments
            assert unchanged["as_of"] == first["as_of"]
        finally:
            if research_id:
                with Session(engine) as session:
                    runs = list(
                        session.scalars(
                            select(Run)
                            .where(Run.research_id == research_id)
                            .order_by(Run.as_of.desc())
                        )
                    )
                    for run in runs:
                        assert not run.cleanup_pending, "test sandbox cleanup is pending"
                        for page in archive.client.get_paginator("list_objects_v2").paginate(
                            Bucket=archive.bucket, Prefix=f"runs/{run.id}/"
                        ):
                            for item in page.get("Contents", []):
                                archive.client.delete_object(Bucket=archive.bucket, Key=item["Key"])
                        session.execute(delete(ToolCall).where(ToolCall.run_id == run.id))
                        session.execute(delete(Record).where(Record.run_id == run.id))
                        session.delete(run)
                        session.flush()
                    session.execute(delete(Research).where(Research.id == research_id))
                    session.commit()
    engine.dispose()
