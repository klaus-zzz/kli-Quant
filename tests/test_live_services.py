"""显式启用才调用真实服务；结果只输出到测试终端并清理本测试资源。"""

import os
from datetime import timedelta

import pytest
from fina_agent.agent.contracts import Action
from fina_agent.agent.storage import Archive, RunStore
from fina_agent.agent.tools.runner import ToolRunner
from fina_agent.models import Record, Research, Run, ToolCall, utcnow
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from kli_quant.config import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("FINA_LIVE_SERVICES") != "1", reason="live services require explicit opt-in"
    ),
]


def test_real_archive_market_and_iterative_sandbox():
    """原文、行情、失败修复、发布归档都真实执行；不依赖模型随机选择动作。"""
    url = os.environ.get("FINA_TEST_DATABASE_URL")
    assert url, "dedicated test database required"
    settings = Settings(database_url=url)
    assert not settings.missing_services(), "live service configuration incomplete"
    engine = create_engine(url)
    archive = Archive(settings)
    with Session(engine) as session:
        research = Research(title="真实服务隔离联调（验证后清理）")
        session.add(research)
        session.flush()
        run = Run(
            research_id=research.id,
            input={"application": "kli-quant", "application_version": "0.1.0"},
            status="running",
            policy={"run_timeout_seconds": 180},
            deadline=utcnow() + timedelta(seconds=180),
        )
        session.add(run)
        session.commit()
        run_id, research_id = run.id, research.id
        store = RunStore(session, run, archive)
        runner = ToolRunner(store, settings)
        step = 0

        def call(name, **arguments):
            nonlocal step
            output = runner.call(step, Action(name=name, arguments=arguments))
            step += 1
            print(name, output["status"], (output.get("error") or {}).get("code", ""))
            return output

        try:
            evidence = call(
                "search_evidence",
                question="核实官方发布的政策信息",
                source_urls=["https://www.gov.cn/"],
                stance="support",
            )
            assert evidence["status"] in {"ok", "partial"}
            snapshot = call(
                "get_market_snapshot",
                instrument_ids=["600000.SH"],
                start="2026-10-20",
                end="2026-10-30",
            )
            assert snapshot["status"] in {"ok", "partial"}
            snapshot_id = snapshot["data"]["snapshot_id"]
            assert (
                call("write_file", path="analysis.py", content="raise ValueError('repair-test')")[
                    "status"
                ]
                == "ok"
            )
            failed = call("execute", entrypoint="analysis.py", input_refs=[snapshot_id])
            assert failed["status"] == "failed" and failed["data"]["exit_code"] != 0
            code = (
                "import json, socket\n"
                f"data=json.load(open('/inputs/{snapshot_id}.json'))\n"
                "assert data['rows']\n"
                "try:\n"
                "    connection=socket.create_connection(('1.1.1.1',443),timeout=2)\n"
                "except OSError:\n"
                "    blocked=True\n"
                "else:\n"
                "    connection.close(); blocked=False\n"
                "assert blocked, 'sandbox network is not denied'\n"
                "summary={'row_count':len(data['rows']), 'network_blocked':blocked}\n"
                "json.dump(summary,open('result.json','w'))\n"
            )
            assert call("write_file", path="analysis.py", content=code)["status"] == "ok"
            executed = call("execute", entrypoint="analysis.py", input_refs=[snapshot_id])
            assert executed["status"] == "ok"
            assert call("read_file", path="result.json")["status"] == "ok"
            published = call(
                "publish_artifact",
                path="result.json",
                purpose="exploratory",
                execution_id=executed["data"]["execution_id"],
                source_refs=[snapshot_id],
            )
            assert published["status"] == "ok"
            assert published["data"]["validation"] == "exploratory"
            assert len(store.records("execution")) == 2
        finally:
            try:
                runner.sandbox.close()
            finally:
                # 只删除本测试 run 的对象及数据库行，保留其他任务和用户配置。
                objects = archive.client.list_objects_v2(
                    Bucket=archive.bucket, Prefix=f"runs/{run_id}/"
                )
                for item in objects.get("Contents", []):
                    archive.client.delete_object(Bucket=archive.bucket, Key=item["Key"])
                session.execute(delete(ToolCall).where(ToolCall.run_id == run_id))
                session.execute(delete(Record).where(Record.run_id == run_id))
                session.execute(delete(Run).where(Run.id == run_id))
                session.execute(delete(Research).where(Research.id == research_id))
                session.commit()
    engine.dispose()
