"""正式产物须与可信执行和固定输入对应，失败不能伪造成功。"""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.research.models import Artifact, ResearchError
from backend.research.validation import check_artifact


def artifact_fixture():
    ids = {key: uuid4() for key in ("calendar", "price", "code", "execution", "output")}
    artifact = Artifact(
        evidence_id=ids["output"],
        kind="observation",
        execution_id=ids["execution"],
        inputs=[ids["calendar"], ids["price"]],
        calendar_id=ids["calendar"],
        trading_dates=["20200102"],
        price_unit="CNY/share",
        return_unit="ratio",
        adjustment="none",
        return_basis="simple_close_to_close",
        fee_bps=3,
        fee_basis="per_side_turnover",
    )
    metadata = {
        "status": "success",
        "future": False,
        "time_fields_complete": True,
        "fetched_at": "2026-01-01T00:00:00Z",
    }
    documents = {
        str(ids["calendar"]): (
            {"kind": "dataset", "sha256": "cal", "metadata": metadata},
            {
                "api_name": "trade_cal",
                "response": {
                    "data": {
                        "fields": ["cal_date", "is_open"],
                        "items": [["20200102", 1]],
                    }
                },
            },
        ),
        str(ids["price"]): (
            {"kind": "dataset", "sha256": "price", "metadata": metadata},
            {
                "api_name": "daily",
                "response": {
                    "data": {
                        "fields": ["ts_code", "trade_date", "close"],
                        "items": [["000001.SZ", "20200102", 10]],
                    }
                },
            },
        ),
        str(ids["code"]): ({"kind": "code", "sha256": "code"}, {"code": "print(10)"}),
        str(ids["output"]): (
            {"kind": "output", "sha256": "output"},
            {
                "conventions": artifact.model_dump(
                    mode="json", exclude={"evidence_id", "execution_id"}
                ),
                "observations": [{"trade_date": "20200102", "close": 10}],
            },
        ),
    }
    execution = {
        "exit_code": 0,
        "code_id": str(ids["code"]),
        "output_id": str(ids["output"]),
        "input_ids": [str(i) for i in artifact.inputs],
        "items": {
            key: {"sha256": ref["sha256"]} for key, (ref, _) in documents.items()
        },
    }
    documents[str(ids["execution"])] = ({"kind": "execution"}, execution)
    return artifact, documents, {"cutoff": datetime.now(UTC)}


def test_valid_observation():
    artifact, documents, run = artifact_fixture()
    check_artifact(artifact, run, lambda key: documents[str(key)])


@pytest.mark.parametrize(
    "fault,code",
    [
        ("exit", "execution_failed"),
        ("inputs", "execution_input_mismatch"),
        ("hash", "execution_content_mismatch"),
        ("calendar", "invalid_trading_dates"),
        ("conventions", "output_conventions_mismatch"),
    ],
)
def test_failed_or_mismatched_execution_rejected(fault, code):
    artifact, documents, run = artifact_fixture()
    execution = documents[str(artifact.execution_id)][1]
    if fault == "exit":
        execution["exit_code"] = 1
    elif fault == "inputs":
        execution["input_ids"] = []
    elif fault == "hash":
        execution["items"][str(artifact.evidence_id)]["sha256"] = "wrong"
    elif fault == "calendar":
        documents[str(artifact.calendar_id)][1]["response"]["data"]["items"][0][1] = 0
    else:
        documents[str(artifact.evidence_id)][1]["conventions"]["fee_bps"] = 999
    with pytest.raises(ResearchError, match=code):
        check_artifact(artifact, run, lambda key: documents[str(key)])


def test_backtest_rejects_recently_fetched_history():
    artifact, documents, run = artifact_fixture()
    artifact.kind = "backtest"
    documents[str(artifact.evidence_id)][1]["conventions"]["kind"] = "backtest"
    with pytest.raises(ResearchError, match="historical_availability_unverified"):
        check_artifact(artifact, run, lambda key: documents[str(key)])


def test_wrong_unit_rejected_on_otherwise_valid_artifact():
    artifact, _, _ = artifact_fixture()
    body = deepcopy(artifact.model_dump(mode="json"))
    body["return_unit"] = "percent"
    with pytest.raises(ValidationError):
        Artifact.model_validate(body)


def test_empty_output_cannot_be_published_as_calculation():
    artifact, documents, run = artifact_fixture()
    documents[str(artifact.evidence_id)][1].pop("observations")
    with pytest.raises(ResearchError, match="output_data_required"):
        check_artifact(artifact, run, lambda key: documents[str(key)])
