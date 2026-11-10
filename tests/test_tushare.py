"""使用明确的 HTTP 测试替身验证契约、安全边界和结果分类。"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import tushare
from backend.main import app
from sandbox.cli.catalog import CONTRACTS, validate


@pytest.fixture
def upstream(monkeypatch):
    """替换官方 HTTP 连接；测试不读取真实凭据、不请求真实数据。"""
    monkeypatch.setenv("TUSHARE_TOKEN", "fixture-secret-only")
    tushare._calls.clear()
    original = httpx.AsyncClient
    calls = []
    response = {"code": 0, "data": {"fields": ["ts_code"], "items": [["000001.SZ"]]}}

    def handler(request):
        calls.append(json.loads(request.content))
        if isinstance(response, Exception):
            raise response
        if isinstance(response, bytes):
            return httpx.Response(200, content=response)
        return httpx.Response(200, json=response)

    monkeypatch.setattr(
        tushare.httpx,
        "AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handler)),
    )

    def set_response(value):
        nonlocal response
        response = value

    return calls, set_response


def test_catalog():
    """全目录必须是唯一的积分接口，并具备输入输出证据。"""
    assert len(CONTRACTS) == 187
    for name, contract in CONTRACTS.items():
        assert contract["name"] == name
        assert contract["permission"] == "points"
        assert contract["source"].startswith("https://tushare.pro/document/")
        schema = contract["input_schema"]
        assert set(schema["required"]) <= schema["properties"].keys()
        assert schema["additionalProperties"] is False
        assert contract["output_fields"]
        names = [field["name"] for field in contract["output_fields"]]
        assert len(names) == len(set(names)), name
    assert CONTRACTS["fund_company"]["input_schema"]["properties"] == {}
    assert (
        CONTRACTS["index_weight"]["input_schema"]["properties"]["end_date"]["type"]
        == "string"
    )
    assert (
        CONTRACTS["fund_manager"]["input_schema"]["properties"]["offset"]["type"]
        == "integer"
    )


@pytest.mark.parametrize(
    "name,params",
    [
        ("daily", {"trade_date": "20260230"}),
        ("daily", {"trade_date": 20261030}),
        ("daily", {"token": "evil"}),
        ("daily", {"start_date": "20261104", "end_date": "20261030"}),
        ("daily", {"limit": 1}),
        ("income", {"period": "20260930"}),
        ("income_vip", {}),
        ("daily_basic", {}),
        ("fund_manager", {"offset": True}),
        ("fund_manager", {"offset": -1}),
        ("fund_manager", {"limit": 10001}),
        ("us_basic", {"limit": "-1"}),
        ("cn_gdp", {"start_q": "2026Q5"}),
    ],
)
def test_invalid_params(name, params):
    with pytest.raises(ValueError):
        validate(name, params)


def test_valid_conditions():
    """核对条件必填、无参数接口及不同日期精度。"""
    validate("daily_basic", {"trade_date": "20261030"})
    validate("income_vip", {"period": "20260930"})
    validate("fund_company", {})
    validate("stk_nineturn", {"trade_date": "2026-10-30 15:00:00"})
    validate("cn_gdp", {"start_q": "2026Q1"})
    validate("daily", {"ts_code": "000001.SZ"}, "ts_code,close")
    with pytest.raises(ValueError):
        validate("daily", {}, "ts_code,token")
    with pytest.raises(ValueError):
        validate("daily", {}, "close,close")


def test_blocked_endpoints(upstream):
    """所有仅记录接口从直接 HTTP 入口也无法绕过。"""
    blocked = json.loads(Path("sandbox/cli/restricted.json").read_text())
    with TestClient(app) as client:
        for record in blocked:
            assert record["name"] not in CONTRACTS
            reply = client.post("/api/tushare/" + record["name"], json={}).json()
            assert reply["status"] == "invalid_request"
    assert upstream[0] == []


@pytest.mark.parametrize(
    "code,msg,status",
    [
        (2002, "bad fixture-secret-only", "permission_denied"),
        (1, "每分钟次数超限", "rate_limited"),
        (1, "没有接口权限", "permission_denied"),
        (500, "服务错误", "service_error"),
    ],
)
def test_errors_redacted(upstream, code, msg, status):
    # 敏感消息在完整响应检查时被提前拒绝，不泄露原文。
    upstream[1]({"code": code, "msg": msg})
    with TestClient(app) as client:
        response = client.post("/api/tushare/daily", json={})
    assert response.json()["status"] == (
        "service_error" if "fixture-secret-only" in msg else status
    )
    assert "fixture-secret-only" not in response.text


def test_success_and_fields(upstream):
    with TestClient(app) as client:
        reply = client.post(
            "/api/tushare/daily",
            json={"params": {"trade_date": "20261030"}, "fields": "ts_code"},
        ).json()
    assert reply["status"] == "success"
    assert reply["data"]["items"] == [["000001.SZ"]]
    assert reply["query"] == {"trade_date": "20261030"}
    assert upstream[0][0]["fields"] == "ts_code"
    assert upstream[0][0]["token"] == "fixture-secret-only"


@pytest.mark.parametrize("configured", [None, "https://upstream.example.test/api"])
def test_upstream_address(monkeypatch, configured):
    """通过实际请求路径验证官方默认地址和环境覆盖，不连接真实上游。"""
    monkeypatch.delenv("TUSHARE_BASE_URL", raising=False)
    if configured is not None:
        monkeypatch.setenv("TUSHARE_BASE_URL", configured)
    monkeypatch.setenv("TUSHARE_TOKEN", "fixture-secret-only")
    tushare._calls.clear()
    original = httpx.AsyncClient
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(
            200, json={"code": 0, "data": {"fields": [], "items": []}}
        )

    monkeypatch.setattr(
        tushare.httpx,
        "AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handler)),
    )
    with TestClient(app) as client:
        assert client.post("/api/tushare/daily", json={}).json()["status"] == "empty"
    assert urls == [configured or "https://api.tushare.pro"]


@pytest.mark.parametrize(
    "data,status",
    [
        ({"fields": ["ts_code"], "items": []}, "empty"),
        ({"fields": ["ts_code"], "items": [["x"]] * 6000}, "incomplete"),
        ({"fields": ["ts_code"], "items": [["x", 1]]}, "service_error"),
        ({"fields": ["unknown"], "items": [["x"]]}, "service_error"),
        ({"fields": ["ts_code", "ts_code"], "items": []}, "service_error"),
    ],
)
def test_data_shape_and_truncation(upstream, data, status):
    upstream[1]({"code": 0, "data": data})
    with TestClient(app) as client:
        reply = client.post("/api/tushare/daily", json={}).json()
    assert reply["status"] == status


def test_timeout_size_budget(upstream, monkeypatch):
    with TestClient(app) as client:
        upstream[1](httpx.ReadTimeout("sensitive upstream detail"))
        assert client.post("/api/tushare/daily", json={}).json()["status"] == "timeout"
        upstream[1]({"code": 0, "data": {"fields": [], "items": []}})
        monkeypatch.setattr(tushare, "MAX_BYTES", 10)
        assert (
            client.post("/api/tushare/daily", json={}).json()["status"] == "incomplete"
        )
        tushare._calls.extend([tushare.time.monotonic()] * 30)
        assert (
            client.post("/api/tushare/daily", json={}).json()["status"]
            == "budget_exceeded"
        )


def test_rejected_before_upstream(upstream, monkeypatch):
    with TestClient(app) as client:
        for body in (
            {"token": "evil"},
            {"params": []},
            {"params": {"url": "http://evil"}},
            [],
        ):
            assert (
                client.post("/api/tushare/daily", json=body).json()["status"]
                == "invalid_request"
            )
        assert (
            client.post("/api/tushare/daily", content="x" * 33000).json()["status"]
            == "invalid_request"
        )
        monkeypatch.delenv("TUSHARE_TOKEN")
        assert (
            client.post("/api/tushare/daily", json={}).json()["status"]
            == "not_configured"
        )
    assert upstream[0] == []


@pytest.mark.parametrize(
    "file_value,env_value,expected",
    [
        (None, None, "http://127.0.0.1:18100"),
        ("", None, "http://127.0.0.1:18100"),
        ("'http://file-backend:18100/'", None, "http://file-backend:18100"),
        (
            "http://file-backend:18100",
            "http://sandbox-backend:18100",
            "http://sandbox-backend:18100",
        ),
    ],
)
def test_axi_registration_and_ptc(
    monkeypatch, tmp_path, file_value, env_value, expected
):
    """核对注册、PTC 和地址优先级；配置定位不依赖当前工作目录。"""
    import subprocess
    import sys

    # 独立进程避免 axi 的进程级配置与其他测试相互污染。
    monkeypatch.setenv("AXI_CONFIG", str(Path("sandbox/cli/axi.json").resolve()))
    monkeypatch.setenv("PYTHONPATH", str(Path.cwd()))
    monkeypatch.delenv("KLI_QUANT_BACKEND_URL", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    if env_value is not None:
        monkeypatch.setenv("KLI_QUANT_BACKEND_URL", env_value)
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    if file_value is not None:
        (cli_dir / ".env").write_text(f"KLI_QUANT_BACKEND_URL={file_value}\n")
    # 当前目录的凭据文件不得被自动搜索或加载。
    (tmp_path / ".env").write_text(
        "TUSHARE_TOKEN=must-not-load\nKLI_QUANT_BACKEND_URL=http://wrong-backend\n"
    )
    script = """
import os
from pathlib import Path
from axi import tool
from axi.providers.native import load_native_tool_modules
from axi.runtime import registry
from sandbox.cli.catalog import CONTRACTS
import httpx
load_native_tool_modules()
from sandbox.cli import tushare
tushare.__file__ = str(Path.cwd() / 'cli' / 'tushare.py')
assert {n for n in registry.list_names() if n.startswith('tushare/')} == {
    'tushare/' + n for n in CONTRACTS}
assert {n for n in registry.list_names() if n.startswith('research/')} == {
    'research/' + n for n in ('context', 'submit', 'status', 'cancel', 'result',
                             'source', 'evidence', 'execute', 'publish')}
meta = registry.get('tushare/daily')
assert 'trade_date' in meta.input_schema['properties']
assert 'run_id' in meta.input_schema['properties']
assert '成交量' in meta.description
assert 'tushare/daily' in [item.name for item in registry.search('股票日线', top_k=20)]
def fake_post(url, **kwargs):
    assert url == EXPECTED_BASE + '/api/tushare/daily'
    assert kwargs['json']['params'] == {'ts_code': '000001.SZ'}
    assert kwargs['headers'] == {'X-Research-Run': 'test-run'}
    # 客户端需等到后端处理完超时并返回结果，避免提前误报不可用。
    assert kwargs['timeout'] > BACKEND_TIMEOUT
    return httpx.Response(200, json={'status': 'success'},
                          request=httpx.Request('POST', url))
httpx.post = fake_post
queried = tool('tushare/daily')(ts_code='000001.SZ', run_id='test-run')
assert queried['status'] == 'success'
assert 'TUSHARE_TOKEN' not in os.environ
"""
    script = (
        f"EXPECTED_BASE = {expected!r}\nBACKEND_TIMEOUT = {tushare.TIMEOUT}\n" + script
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=tmp_path
    )
    assert completed.returncode == 0, completed.stderr


def test_month_lists_and_invalid_month():
    """宏观文档允许逗号分隔月份，单月仍须校验真实月份。"""
    validate("cn_cpi", {"m": "202601,202602"})
    with pytest.raises(ValueError):
        validate("cn_m", {"m": "202613"})


def test_requested_columns_missing(upstream):
    """上游未返回所选字段时不得冒充成功。"""
    with TestClient(app) as client:
        reply = client.post(
            "/api/tushare/daily", json={"fields": "ts_code,close"}
        ).json()
    assert reply["status"] == "incomplete"


def test_nonfinite_upstream_values(upstream):
    """非标准 JSON 数值不可在最终序列化时导致未处理异常。"""
    # MockTransport 返回合法编码但非标准的 NaN 字面量。
    upstream[1](b'{"code":0,"data":{"fields":["close"],"items":[[NaN]]}}')
    with TestClient(app) as client:
        reply = client.post("/api/tushare/daily", json={}).json()
    assert reply["status"] == "service_error"


def test_concurrency_limit(monkeypatch):
    """四个在途请求占满后，第五个立即被拒绝且不发送上游请求。"""
    import asyncio

    from starlette.requests import Request

    monkeypatch.setenv("TUSHARE_TOKEN", "fixture-secret-only")
    tushare._calls.clear()

    async def scenario():
        release, full = asyncio.Event(), asyncio.Event()
        count = 0

        async def fake_fetch(name, params, fields, token):
            nonlocal count
            count += 1
            if count == 4:
                full.set()
            await release.wait()
            return tushare.result(name, params, "empty")

        async def receive():
            return {"type": "http.request", "body": b"{}", "more_body": False}

        def request():
            return Request({"type": "http", "method": "POST", "app": app}, receive)

        monkeypatch.setattr(tushare, "fetch", fake_fetch)
        monkeypatch.setattr(tushare, "_slots", asyncio.Semaphore(4))
        tasks = [
            asyncio.create_task(tushare.query("daily", request())) for _ in range(4)
        ]
        await asyncio.wait_for(full.wait(), timeout=2)
        assert (await tushare.query("daily", request()))["status"] == "busy"
        release.set()
        await asyncio.gather(*tasks)
        assert count == 4

    asyncio.run(scenario())


def test_upstream_has_more(upstream):
    """真实协议中的 has_more 也必须参与不完整数据判断。"""
    upstream[1](
        {
            "code": 0,
            "data": {"fields": ["ts_code"], "items": [["000001.SZ"]], "has_more": True},
        }
    )
    with TestClient(app) as client:
        reply = client.post("/api/tushare/daily", json={}).json()
    assert reply["status"] == "incomplete"
