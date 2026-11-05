"""无需外部配置的研究边界与产物校验。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app
from backend.research.api import principal, service
from backend.research.models import Artifact, ResultBundle, Submission
from backend.research.validation import dataset_times, validate_bundle


def draft():
    """明确承认缺证据的两跳结论，适合验证业务状态与推理关系。"""
    hop = {
        "id": "supply",
        "parents": [],
        "trigger": "事件提出供给问题",
        "question": "供给是否下降",
        "entities": ["原料"],
        "time_scope": "2020 年",
        "finding": "尚未证实",
        "supports": [],
        "counters": [],
        "alternatives": [],
        "gaps": ["缺少公告"],
        "conditions": "待核实",
        "invalidation": "新增公告否定",
    }
    second = {
        **hop,
        "id": "inventory",
        "parents": ["supply"],
        "trigger": "供给缺口需要库存缓冲验证",
        "question": "库存是否足够",
    }
    return {
        "conclusion": "insufficient_evidence",
        "summary": "证据不足",
        "valid_from": "2020-01-01T00:00:00Z",
        "valid_until": "2030-01-01T00:00:00Z",
        "conditions": "补充独立证据后复核",
        "invalidation": "假设被否定",
        "gaps": ["未获取原文"],
        "hops": [hop, second],
        "artifacts": [],
        "revisions": [],
    }


def test_no_identity_or_executor_does_not_accept_work():
    with TestClient(app) as client:
        response = client.post(
            "/api/research/runs", headers={"X-Owner": "attacker"}, json={}
        )
        assert response.status_code == 503
        assert response.json()["error"] == "identity_not_ready"
        app.dependency_overrides[principal] = lambda: "test-owner"
        try:
            response = client.post("/api/research/runs", json={})
            assert response.json()["error"] == "executor_not_ready"
        finally:
            app.dependency_overrides.clear()


def test_submission_rejects_backend_controls():
    with pytest.raises(ValidationError):
        Submission(event="test", question="why", cutoff="2020-01-01")
    with pytest.raises(ValidationError):
        Submission(question="why")


def test_invalid_http_input_does_not_echo_secrets():
    app.dependency_overrides[principal] = lambda: "test-owner"
    app.dependency_overrides[service] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/research/runs",
                headers={"Idempotency-Key": "1"},
                json={"question": "private-input", "budget": 9999},
            )
            assert response.status_code == 422
            assert "private-input" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_graph_requires_predecessors_and_revision_reason():
    data = draft()
    data["hops"][0]["parents"] = ["inventory"]
    run = {"cutoff": datetime.now(UTC), "previous_run_id": uuid4()}
    errors = validate_bundle(ResultBundle.model_validate(data), run, None, {"old"})
    assert "invalid_hop_graph" in errors
    assert "revision_reason_required" in errors


def test_wrong_units_rejected():
    with pytest.raises(ValidationError):
        Artifact.model_validate({"price_unit": "USD", "return_unit": "percent"})


def test_future_disclosure_not_hidden_by_old_period():
    document = {
        "response": {
            "status": "success",
            "fetched_at": "2020-01-01T00:00:00Z",
            "data": {
                "fields": ["end_date", "f_ann_date"],
                "items": [["20191231", "20200430"]],
            },
        }
    }
    assert dataset_times(document, datetime(2020, 2, 1, tzinfo=UTC))["future"]


def test_omitted_date_fields_cannot_bypass_cutoff():
    from backend.research.models import ResearchError
    from backend.research.validation import check_citation

    document = {
        "api_name": "daily",
        "response": {
            "status": "success",
            "fetched_at": "2020-01-01T00:00:00Z",
            "data": {"fields": ["close"], "items": [[10]]},
        },
    }
    cutoff = datetime(2020, 1, 1, tzinfo=UTC)
    ref = {"kind": "dataset", "metadata": dataset_times(document, cutoff)}
    with pytest.raises(ResearchError, match="time_fields_missing"):
        check_citation(ref, document, "table", cutoff)
