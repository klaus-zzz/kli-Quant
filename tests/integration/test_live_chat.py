"""真实模型在对话中调度研究，研究期间继续聊天并保留版本与取消记录。"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fina_agent.agent.storage import Archive
from fina_agent.main import create_app
from fina_agent.models import ChatTurn, Conversation, Record, Research, Run, ToolCall
from fina_agent.worker import tick
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from kli_quant.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("FINA_LIVE_AGENT") != "1", reason="live chat requires explicit opt-in"
    ),
]


def test_real_conversation_background_research_and_cancel():
    """只用专用数据库；本测试创建的归档、沙箱与会话在收尾删除。"""
    url = os.environ.get("FINA_TEST_DATABASE_URL")
    assert url, "dedicated test database required"
    settings = Settings(database_url=url)
    database = create_engine(url)
    archive = Archive(settings)
    conversation_id = None
    worker = None
    pool = ThreadPoolExecutor(max_workers=1)
    with TestClient(create_app(settings)) as client:
        try:
            conversation_id = client.post("/api/conversations").json()["id"]

            def send(content):
                response = client.post(
                    f"/api/conversations/{conversation_id}/messages",
                    json={"request_id": str(uuid4()), "content": content},
                )
                assert response.status_code == 200
                turn = response.json()
                print(
                    "chat:",
                    turn["id"],
                    turn["status"],
                    [call["name"] for call in turn["calls"]],
                    flush=True,
                )
                assert turn["status"] == "completed", turn["error"]
                return turn

            def detail():
                return client.get(f"/api/conversations/{conversation_id}").json()

            send("请用一句中文解释事实与假设的区别，不需要启动研究。")
            assert not detail()["jobs"]
            send(
                "请立即在后台研究利率政策变化对浦发银行600000.SH的影响，"
                "原文线索https://www.pbc.gov.cn/；寻找支持和净息差承压等反证。"
                "必须获取2026-10-20至2026-10-30日线，在沙箱写代码计算区间收益、"
                "执行、读回并归档探索产物。资料不足就明确证据不足，不必向我确认。"
            )
            first = detail()["jobs"][0]
            assert first["status"] == "queued"
            worker = pool.submit(tick, settings, database)
            for _ in range(20):
                if detail()["jobs"][0]["status"] == "running":
                    break
                time.sleep(0.5)
            assert detail()["jobs"][0]["status"] == "running"
            send("研究继续在后台做。先用一句话解释条件性观察与确定性预测的区别，不要再启动研究。")
            assert len(detail()["jobs"]) == 1
            print("background status after chat:", detail()["jobs"][0]["status"], flush=True)
            assert worker.result(timeout=settings.run_timeout_seconds + 30)
            finished = client.get(f"/api/runs/{first['id']}").json()
            print("research:", first["id"], finished["status"], finished["stop_reason"], flush=True)
            assert finished["status"] in {"completed", "inconclusive"}
            assert {"document", "evidence", "snapshot", "execution", "artifact", "judgment"} <= {
                row["kind"] for row in finished["records"]
            }
            assert detail()["jobs"][0]["judgment"]
            send("仅依据后台已保存的研究结论，用两句话解释结果与缺口，不要新建研究。")
            send(
                "新增未核实线索：净息差压力可能抵消政策支持。请用 research_id "
                + first["research_id"]
                + " 启动新版本复核，不要把线索当事实。"
            )
            jobs = detail()["jobs"]
            assert len(jobs) == 2 and jobs[-1]["parent_run_id"] == first["id"]
            send("请取消刚才新建的复核研究，保留第一轮完成结果。")
            assert detail()["jobs"][-1]["status"] == "cancelled"
            unchanged = client.get(f"/api/runs/{first['id']}").json()
            assert [r for r in unchanged["records"] if r["kind"] == "judgment"] == [
                r for r in finished["records"] if r["kind"] == "judgment"
            ]
        finally:
            if conversation_id:
                for job in client.get(f"/api/conversations/{conversation_id}").json()["jobs"]:
                    client.post(f"/api/conversations/{conversation_id}/runs/{job['id']}/cancel")
            if worker:
                worker.result(timeout=settings.run_timeout_seconds + 30)
            pool.shutdown()
            if conversation_id:
                with Session(database) as session:
                    runs = list(
                        session.scalars(
                            select(Run)
                            .where(Run.conversation_id == conversation_id)
                            .order_by(Run.as_of.desc())
                        )
                    )
                    research_ids = {run.research_id for run in runs}
                    for run in runs:
                        assert not run.cleanup_pending, "sandbox cleanup pending"
                        for page in archive.client.get_paginator("list_objects_v2").paginate(
                            Bucket=archive.bucket, Prefix=f"runs/{run.id}/"
                        ):
                            for item in page.get("Contents", []):
                                archive.client.delete_object(Bucket=archive.bucket, Key=item["Key"])
                        session.execute(delete(ToolCall).where(ToolCall.run_id == run.id))
                        session.execute(delete(Record).where(Record.run_id == run.id))
                        session.delete(run)
                        session.flush()
                    session.execute(delete(Research).where(Research.id.in_(research_ids)))
                    session.execute(
                        delete(ChatTurn).where(ChatTurn.conversation_id == conversation_id)
                    )
                    session.execute(delete(Conversation).where(Conversation.id == conversation_id))
                    session.commit()
    database.dispose()
