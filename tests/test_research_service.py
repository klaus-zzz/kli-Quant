"""使用显式专用 PostgreSQL 测试库验证事务和竞态，不访问业务库。"""

import asyncio
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_research_contract import draft

from backend.main import app
from backend.research.api import principal
from backend.research.api import service as service_dependency
from backend.research.migrate import migrate
from backend.research.models import ResearchError, Submission
from backend.research.repository import Repository
from backend.research.service import ResearchService
from backend.research.storage import Archive, encode


class MemoryArchive:
    """只替代对象传输，摘要校验与真实存储保持同样行为。"""

    def __init__(self):
        self.objects = {}

    def put(self, run_id, document):
        key, raw = str(uuid4()), encode(document)
        self.objects[key] = raw
        return {
            "object_key": key,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        }

    def read(self, ref):
        raw = self.objects[ref["object_key"]]
        if len(raw) != ref["size"] or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ResearchError("content_mismatch")
        return json.loads(raw)


class ControlledExecutor:
    """只记录派发；测试显式推进任务，不能当成真实模型联调。"""

    def __init__(self):
        self.calls = []

    def submit(self, run_id):
        self.calls.append(run_id)


@pytest.fixture
def research():
    dsn = os.environ.get("RESEARCH_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("未指定专用研究测试库")
    if not urlsplit(dsn).path.lstrip("/").startswith("kli_quant_test_"):
        pytest.fail("测试库名必须以 kli_quant_test_ 开头")
    migrate(dsn)
    repo = Repository(dsn)
    with repo.transaction() as conn:
        conn.execute(
            "TRUNCATE research_hops,research_results,"
            "research_evidence,research_runs CASCADE"
        )
    return ResearchService(repo, MemoryArchive(), ControlledExecutor())


def start(research, key=None, owner="alice", previous=None):
    run, _ = research.submit(
        owner,
        key or str(uuid4()),
        Submission(event="供给事件", question="库存是否缓冲", previous_run_id=previous),
    )
    assert research.claim(owner, run["id"])
    return run["id"]


def test_submit_idempotency_and_concurrency(research):
    payload = Submission(event="事件", question="影响")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: research.submit("alice", "same", payload), range(4))
        )
    assert sum(created for _, created in results) == 1
    assert len({run["id"] for run, _ in results}) == 1
    assert len(research.executor.calls) == 1
    with pytest.raises(ResearchError, match="idempotency_conflict"):
        research.submit("alice", "same", Submission(event="变化", question="影响"))


def test_not_ready_and_dispatch_failure(research):
    research.executor = None
    with pytest.raises(ResearchError, match="executor_not_ready"):
        research.submit("alice", "none", Submission(event="事件", question="影响"))
    with research.repo.transaction() as conn:
        assert (
            conn.execute("SELECT count(*) AS n FROM research_runs").fetchone()["n"] == 0
        )

    class BrokenExecutor:
        def submit(self, run_id):
            raise RuntimeError("private-error")

    research.executor = BrokenExecutor()
    run, _ = research.submit(
        "alice", "failed", Submission(event="事件", question="影响")
    )
    assert run["status"] == "failed" and run["error"] == "dispatch_failed"


def test_result_versions_and_ownership(research):
    first = start(research)
    result = research.publish("alice", first, draft())
    assert result["result"]["conclusion"] == "insufficient_evidence"
    assert research.cancel("alice", first)["status"] == "completed"
    assert research.publish("alice", first, draft()) == result
    second = start(research, previous=first)
    revised = draft()
    revised["revisions"] = [
        {"hop_id": "supply", "change": "maintained", "reason": "仍缺原文"}
    ]
    research.publish("alice", second, revised)
    assert research.result("alice", first) == result
    with pytest.raises(ResearchError, match="not_found"):
        research.result("bob", first)
    with pytest.raises(ResearchError, match="immutable_result"):
        research.publish("alice", first, {**draft(), "summary": "覆写"})


def test_cancel_and_completion_race(research):
    run_id = start(research)

    def publish():
        try:
            research.publish("alice", run_id, draft())
        except ResearchError as exc:
            assert exc.code == "run_not_running"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(publish), pool.submit(research.cancel, "alice", run_id)]
        for future in futures:
            future.result()
    status = research.get("alice", run_id)["status"]
    assert status in {"cancelling", "completed"}
    research.acknowledge_cancel("alice", run_id)
    final = research.get("alice", run_id)["status"]
    assert final == ("cancelled" if status == "cancelling" else "completed")
    assert research.cancel("alice", run_id)["status"] == final


def test_budget_survives_service_restart(research):
    research.max_calls = 2
    run_id = start(research)
    with ThreadPoolExecutor(max_workers=4) as pool:

        def attempt(_):
            try:
                research.reserve_call("alice", run_id)
                return True
            except ResearchError:
                return False

        assert sum(pool.map(attempt, range(4))) == 2
    restarted = ResearchService(research.repo, research.archive, research.executor)
    with pytest.raises(ResearchError, match="budget_exceeded"):
        restarted.reserve_call("alice", run_id)
    assert restarted.get("alice", run_id)["used_calls"] == 2


def source(research, run_id, published="2020-01-01T00:00:00+00:00", owner="alice"):
    document = {
        "status": "available",
        "published_at": published,
        "blocks": [{"locator": "p:1", "text": "供给没有下降"}],
    }
    return research.store_evidence(owner, run_id, "source", document, {})


@pytest.mark.parametrize(
    "fault", ["foreign", "tampered", "future", "unknown", "locator"]
)
def test_invalid_references_retain_draft(research, fault):
    run_id = start(research)
    other = start(research, owner="bob") if fault == "foreign" else run_id
    published = (
        "2099-01-01T00:00:00+00:00" if fault == "future" else "2020-01-01T00:00:00Z"
    )
    ref = source(
        research,
        other,
        None if fault == "unknown" else published,
        owner="bob" if fault == "foreign" else "alice",
    )
    if fault == "tampered":
        with research.repo.transaction() as conn:
            row = research.repo.evidence(
                conn, research.get("alice", run_id), ref["evidence_id"]
            )
        research.archive.objects[row["object_key"]] = b"tampered"
    body = draft()
    body["hops"][0]["supports"] = [
        {
            "evidence_id": ref["evidence_id"],
            "locator": "p:999" if fault == "locator" else "p:1",
        }
    ]
    with pytest.raises(ResearchError, match="validation_failed"):
        research.publish("alice", run_id, body)
    assert research.get("alice", run_id)["error"] == "validation_failed"
    with research.repo.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM research_results WHERE run_id=%s", (run_id,)
        ).fetchone()
    assert not row["valid"] and row["errors"]
    assert research.archive.read(row) == body


def test_snapshot_uses_shared_tushare_and_fixed_input(research, monkeypatch):
    from backend import tushare

    run_id = start(research)
    calls = []

    async def execute(name, params, fields):
        calls.append((name, params, fields))
        return tushare.result(
            name,
            params,
            "success",
            {
                "fields": ["ts_code", "trade_date", "close"],
                "items": [["000001.SZ", "20200102", 10]],
            },
        )

    monkeypatch.setattr(tushare, "execute_query", execute)
    ref = asyncio.run(
        research.collect_dataset(
            "alice",
            run_id,
            "daily",
            {"ts_code": "000001.SZ", "trade_date": "20200102"},
            "ts_code,trade_date,close",
        )
    )
    _, snapshot = research.read_evidence("alice", run_id, ref["evidence_id"])
    assert snapshot["fields"] == "ts_code,trade_date,close"
    assert snapshot["response"]["data"]["items"][0][2] == 10
    assert len(calls) == 1


def test_http_success_cancel_result_states(research):
    app.dependency_overrides[principal] = lambda: "alice"
    app.dependency_overrides[service_dependency] = lambda: research
    try:
        with TestClient(app) as client:
            payload = {"event": "事件", "question": "影响"}
            response = client.post(
                "/api/research/runs", json=payload, headers={"Idempotency-Key": "http"}
            )
            assert response.status_code == 202
            run_id = response.json()["run_id"]
            assert (
                client.post(
                    "/api/research/runs",
                    json=payload,
                    headers={"Idempotency-Key": "http"},
                ).status_code
                == 200
            )
            assert client.get(f"/api/research/runs/{run_id}/result").status_code == 409
            assert (
                client.post(f"/api/research/runs/{run_id}/cancel").json()["status"]
                == "cancelled"
            )
            assert not research.claim("alice", UUID(run_id))
    finally:
        app.dependency_overrides.clear()


def test_real_s3_hash_and_readback(research):
    """真实 S3 测试必须显式配置专属 bucket；不创建或扫描共享 bucket。"""
    bucket = os.environ.get("RESEARCH_TEST_S3_BUCKET", "")
    if not bucket:
        pytest.skip("未配置专用 S3 测试 bucket")
    assert bucket.startswith("kli-quant-test-")
    archive = Archive(
        os.environ["RESEARCH_TEST_S3_ENDPOINT"],
        bucket,
        os.environ["RESEARCH_TEST_S3_ACCESS_KEY"],
        os.environ["RESEARCH_TEST_S3_SECRET_KEY"],
    )
    ref = archive.put(uuid4(), {"原文": "固定内容"})
    assert archive.read(ref) == {"原文": "固定内容"}
    archive.client.put_object(Bucket=bucket, Key=ref["object_key"], Body=b"bad")
    with pytest.raises(ResearchError, match="content_mismatch"):
        archive.read(ref)


def test_migration_rollback_and_repeat(research):
    """首次建表、重复升级及显式回退都在专用空测试库执行。"""
    dsn = research.repo.dsn
    migrate(dsn)
    migrate(dsn, "down")
    with research.repo.transaction() as conn:
        assert (
            conn.execute(
                "SELECT to_regclass('research_runs') AS table_name"
            ).fetchone()["table_name"]
            is None
        )
    migrate(dsn)
    assert start(research)


def test_deadline_and_cancel_pending_are_distinct(research):
    run_id = start(research)
    with research.repo.transaction() as conn:
        conn.execute(
            "UPDATE research_runs SET deadline=now()-interval '1 second' WHERE id=%s",
            (run_id,),
        )
    assert research.get("alice", run_id)["error"] == "deadline_exceeded"
    another = start(research)
    research.cancel("alice", another)
    with research.repo.transaction() as conn:
        conn.execute(
            "UPDATE research_runs SET deadline=now()-interval '1 second' WHERE id=%s",
            (another,),
        )
    assert research.get("alice", another)["status"] == "cancelling"


def test_no_opportunity_is_a_successful_business_conclusion(research):
    run_id = start(research)
    evidence = source(research, run_id)
    body = draft()
    body["conclusion"] = "no_opportunity"
    for hop in body["hops"]:
        hop["supports"] = [{"evidence_id": evidence["evidence_id"], "locator": "p:1"}]
    assert (
        research.publish("alice", run_id, body)["result"]["conclusion"]
        == "no_opportunity"
    )
    assert research.get("alice", run_id)["status"] == "completed"
