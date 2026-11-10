"""浏览器读取固定资料时仍受会话归属约束，不需要沙箱执行权限。"""

from test_agent_integration import agent as agent
from test_research_contract import draft
from test_research_service import research as research

from backend.research.models import Submission


def test_browser_reads_archived_evidence_after_completion(agent):
    runtime, session, _, client = agent
    run, _ = runtime.research.submit(
        session, "browser", Submission(event="事件", question="核对原文")
    )
    run_id = run["id"]
    runtime.research.claim(session, run_id)
    ref = runtime.research.store_evidence(
        session,
        run_id,
        "source",
        {
            "blocks": [{"locator": "p:1", "text": "<script>不执行</script>"}],
            "raw_base64": "原始 HTML",
        },
        {},
    )
    runtime.research.publish(session, run_id, draft())
    headers = {"Authorization": "Bearer chat-secret", "X-Session-ID": session}
    path = f"/api/research/runs/{run_id}/evidence"
    listing = client.get(path, headers=headers)
    assert listing.status_code == 200
    assert listing.json()["evidence"][0]["evidence_id"] == ref["evidence_id"]
    response = client.get(f"{path}/{ref['evidence_id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["document"]["blocks"][0]["locator"] == "p:1"
    assert "raw_base64" not in response.json()["document"]
    assert "object_key" not in response.text + listing.text
    other = runtime.ledger.create_session("developer")
    headers["X-Session-ID"] = other
    assert client.get(path, headers=headers).status_code == 404
    assert (
        client.get(f"{path}/{ref['evidence_id']}", headers=headers).status_code == 404
    )
    assert client.get(path).status_code == 401


def test_snapshot_exposes_question_and_previous_version(agent):
    runtime, session, _, client = agent
    first, _ = runtime.research.submit(
        session, "first", Submission(event="事件", question="原问题")
    )
    runtime.research.claim(session, first["id"])
    runtime.research.publish(session, first["id"], draft())
    second, _ = runtime.research.submit(
        session,
        "next",
        Submission(event="新证据", question="复核", previous_run_id=first["id"]),
    )
    response = client.get(
        f"/api/chat/sessions/{session}",
        headers={"Authorization": "Bearer chat-secret"},
    )
    runs = {r["run_id"]: r for r in response.json()["research"]}
    assert runs[str(second["id"])]["previous_run_id"] == str(first["id"])
    assert runs[str(first["id"])]["question"] == "原问题"


def test_revision_context_supplies_fixed_previous_judgments(agent):
    """复核必须取得旧判断 ID，不能让模型猜测 revisions 的对应关系。"""
    runtime, session, _, client = agent
    first, _ = runtime.research.submit(
        session, "old", Submission(event="事件", question="旧判断")
    )
    runtime.research.claim(session, first["id"])
    original = runtime.research.publish(session, first["id"], draft())
    second, _ = runtime.research.submit(
        session,
        "revision",
        Submission(event="新证据", question="复核", previous_run_id=first["id"]),
    )
    runtime.research.claim(session, second["id"])
    response = client.get(
        "/api/research/context",
        headers={"Authorization": "host-injected", "X-Research-Run": str(second["id"])},
    )
    assert response.status_code == 200
    assert response.json()["previous_result"] == original
    assert runtime.research.result(session, first["id"]) == original


def test_browser_can_inspect_unvalidated_array_output(agent):
    """代码可能输出数组而非正式产物对象，探索归档仍应可读。"""
    runtime, session, _, client = agent
    run, _ = runtime.research.submit(
        session, "array", Submission(event="事件", question="检查计算输出")
    )
    runtime.research.claim(session, run["id"])
    ref = runtime.research.store_evidence(session, run["id"], "output", [1, 2], {})
    response = client.get(
        f"/api/research/runs/{run['id']}/evidence/{ref['evidence_id']}",
        headers={"Authorization": "Bearer chat-secret", "X-Session-ID": session},
    )
    assert response.status_code == 200
    assert response.json()["document"] == [1, 2]
