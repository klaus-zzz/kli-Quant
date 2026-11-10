"""在已绑定沙箱执行固定代码和输入，执行事实由控制端采集。"""

import hashlib
import json
import shlex
from uuid import uuid4

from backend.research.models import ResearchError
from backend.research.storage import encode
from sandbox.create_sandbox import PYTHON

# 子进程仅接收固定输入；限制时间、内存和输出文件，错误不会当作成功。
RUNNER = """
import hashlib, json, os, resource, signal, subprocess, sys, tempfile
from contextlib import suppress
raw = open(sys.argv[1], "rb").read()
if hashlib.sha256(raw).hexdigest() != sys.argv[2]:
    raise RuntimeError("fixed input changed")
request = json.loads(raw)
def limits():
    resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024*1024, 1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (40, 40))
with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
    try:
        child = subprocess.Popen(
            [sys.executable, "-I", "-c", request["code"]],
            stdin=subprocess.PIPE, stdout=out, stderr=err,
            start_new_session=True, preexec_fn=limits)
        child.communicate(json.dumps(request["inputs"]).encode(), timeout=45)
        status = child.returncode
    except subprocess.TimeoutExpired:
        status = 124
    finally:
        # 正常退出也清理同组子进程，不能让后台计算逃过本次执行时间限制。
        if "child" in locals():
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
    out.seek(0)
    err.seek(0)
    print(json.dumps({"exit_code": status,
        "stdout": out.read(1024*1024).decode("utf-8", "replace"),
        "stderr": err.read(1024*1024).decode("utf-8", "replace")}))
"""


def execute(runtime, binding, code, input_ids):
    """代码内容和输入先冻结，再校验远端实际读取的字节。"""
    research = runtime.research
    owner, run_id = binding["session_id"], binding["run_id"]
    research.reserve_call(owner, run_id)
    inputs = {}
    for evidence_id in input_ids:
        ref, document = research.read_evidence(owner, run_id, evidence_id)
        if ref["kind"] not in {"source", "dataset"}:
            raise ResearchError("invalid_execution_input", 422)
        inputs[str(evidence_id)] = document
    raw = encode({"code": code, "inputs": inputs})
    if len(raw) > 8 * 1024 * 1024:
        raise ResearchError("execution_input_too_large", 413)
    digest = hashlib.sha256(raw).hexdigest()
    code_ref = research.store_evidence(owner, run_id, "code", {"source": code}, {})
    sb = runtime.sandboxes.attach(binding)
    path = f"/tmp/kli-quant-execution-{uuid4().hex}.json"
    sb.files.write(path, raw)
    command = f"{PYTHON} -I -c {shlex.quote(RUNNER)} {shlex.quote(path)} {digest}"
    actual = sb.commands.run(command, timeout=55)
    if actual.exit_code != 0:
        raise ResearchError("execution_transport_failed", 502)
    try:
        captured = json.loads(actual.stdout)
        status, stdout = captured["exit_code"], captured["stdout"]
        if type(status) is not int or not isinstance(stdout, str):
            raise ValueError
        try:
            output = json.loads(stdout)
        except ValueError:
            output = {"text": stdout}
        # Python JSON 默认接受 NaN/Infinity；归档前统一拒绝这些非标准数值。
        encode(output)
    except (ValueError, KeyError, TypeError):
        raise ResearchError("invalid_execution_response", 502) from None
    output_ref = research.store_evidence(owner, run_id, "output", output, {})
    execution = research.record_execution(
        owner,
        run_id,
        code_ref["evidence_id"],
        input_ids,
        output_ref["evidence_id"],
        status,
    )
    return {"code": code_ref, "output": output_ref, "execution": execution, **captured}
