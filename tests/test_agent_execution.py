"""用固定测试代码验证远端执行封装；不运行模型生成代码或访问外网。"""

import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.agent.execution import RUNNER, execute
from backend.research.models import ResearchError
from backend.research.storage import encode


def test_execution_binds_code_input_and_exit_status(tmp_path):
    """代码读取归档输入并返回 JSON；改动输入后原摘要必须拒绝执行。"""
    path = tmp_path / "input.json"
    raw = encode(
        {
            "code": "import json,sys; print(json.dumps(json.load(sys.stdin)))",
            "inputs": {"evidence": [1, 2, 3]},
        }
    )
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    command = [sys.executable, "-I", "-c", RUNNER, str(path), digest]
    response = subprocess.run(command, capture_output=True, text=True, timeout=10)
    captured = json.loads(response.stdout)
    assert captured["exit_code"] == 0
    assert json.loads(captured["stdout"]) == {"evidence": [1, 2, 3]}
    path.write_bytes(raw + b" ")
    assert subprocess.run(command, capture_output=True, timeout=10).returncode != 0


def test_failed_code_is_not_a_successful_execution(tmp_path):
    path = tmp_path / "input.json"
    raw = encode({"code": "raise ValueError('test failure')", "inputs": {}})
    path.write_bytes(raw)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            RUNNER,
            str(path),
            hashlib.sha256(raw).hexdigest(),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert json.loads(result.stdout)["exit_code"] != 0


def test_nonfinite_output_returns_stable_error():
    research = Mock()
    research.read_evidence.return_value = ({"kind": "dataset"}, {})
    research.store_evidence.return_value = {"evidence_id": "fixed"}
    sb = Mock()
    sb.commands.run.return_value = SimpleNamespace(
        exit_code=0,
        stdout=json.dumps({"exit_code": 0, "stdout": "NaN", "stderr": ""}),
    )
    runtime = SimpleNamespace(research=research, sandboxes=Mock())
    runtime.sandboxes.attach.return_value = sb
    with pytest.raises(ResearchError, match="invalid_execution_response"):
        execute(runtime, {"session_id": "s", "run_id": "r"}, "print('NaN')", ["i"])
