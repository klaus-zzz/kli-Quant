"""控制端边界与失败回收测试；SDK 使用替身，不创建付费资源。"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sandbox.create_sandbox import (
    AXI,
    checked_command,
    creation_options,
    temporary_sandbox,
    verify_sandbox,
)


@pytest.fixture
def control(monkeypatch):
    """替换管理客户端，捕获真实调用参数而不发出网络请求。"""
    instance = Mock()
    sdk = SimpleNamespace(Config=SimpleNamespace, Sandbox=Mock())
    sdk.Sandbox.create.return_value = instance
    monkeypatch.setitem(sys.modules, "cubesandbox", sdk)
    env = {
        "CUBESANDBOX_API_URL": "http://cube.test:3000",
        "CUBESANDBOX_DOMAIN": "cube.test",
        "CUBESANDBOX_TEMPLATE_ID": "tpl-test",
        "CUBE_PROXY_NODE_IP": "192.0.2.10",
        "KLI_QUANT_BACKEND_URL": "http://backend.test:18100/",
        "E2B_API_KEY": "control-secret",
        "TUSHARE_TOKEN": "must-not-copy",
        "OPENAI_API_KEY": "must-not-copy",
    }
    return env, sdk, instance


def test_creation_whitelist_and_backend_change(control):
    """同模板下新建实例取得新的 URL，管理与数据源凭据不进入 envs。"""
    env, sdk, instance = control
    for url in ("http://backend-a:18100", "http://backend-b:18100"):
        env["KLI_QUANT_BACKEND_URL"] = url
        with temporary_sandbox(env):
            options = sdk.Sandbox.create.call_args.kwargs
            assert options["template"] == "tpl-test"
            assert options["config"].api_key == "control-secret"
            assert options["config"].proxy_node_ip == "192.0.2.10"
            assert options["envs"] == {
                "KLI_QUANT_BACKEND_URL": url,
                "AXI_CONFIG": "/opt/kli-quant/sandbox/cli/axi.json",
            }
    assert instance.kill.call_count == 2


@pytest.mark.parametrize(
    ("url", "destination"),
    [
        ("http://192.0.2.10:18100", "192.0.2.10/32"),
        ("http://[2001:db8::10]:18100", "2001:db8::10/128"),
        ("https://backend.test", "backend.test"),
    ],
)
def test_creation_allows_only_configured_backend(control, url, destination):
    """默认内网出站被拦截，仅为本次配置的后端主机添加实例级放行。"""
    env, _, _ = control
    env["KLI_QUANT_BACKEND_URL"] = url
    assert creation_options(env)["network"] == {"allow_out": [destination]}


@pytest.mark.parametrize(
    "key",
    [
        "CUBESANDBOX_API_URL",
        "CUBESANDBOX_DOMAIN",
        "CUBESANDBOX_TEMPLATE_ID",
        "KLI_QUANT_BACKEND_URL",
        "E2B_API_KEY",
    ],
)
@pytest.mark.parametrize("value", ["", "   "])
def test_missing_config_fails_before_create(control, key, value):
    """空白配置也视作缺失，避免意外使用 SDK 默认服务。"""
    env, sdk, _ = control
    env[key] = value
    with pytest.raises(ValueError, match=key), temporary_sandbox(env):
        pass
    sdk.Sandbox.create.assert_not_called()


@pytest.mark.parametrize(
    "url", ["file:///tmp/a", "http://", "http://u:p@host", "http://host?a=1"]
)
def test_invalid_backend_url(control, url):
    """后端配置不能携带凭据或无法转发的地址格式。"""
    env, _, _ = control
    env["KLI_QUANT_BACKEND_URL"] = url
    with pytest.raises(ValueError, match="HTTP"):
        creation_options(env)


def test_verification_failure_cleans_up(control):
    """连接失败、配置缺失和非零退出码均沿相同路径回收实例。"""
    env, _, instance = control
    instance.commands.run.return_value = SimpleNamespace(exit_code=1)
    with pytest.raises(RuntimeError, match="退出码 1"), temporary_sandbox(env) as sb:
        checked_command(sb, "failed-probe")
    instance.kill.assert_called_once()


def test_remote_exception_cleans_up(control):
    env, _, instance = control
    instance.commands.run.side_effect = TimeoutError("unreachable")
    with pytest.raises(TimeoutError), temporary_sandbox(env) as sb:
        checked_command(sb, "health-probe")
    instance.kill.assert_called_once()


def test_registered_tools_and_business_status(control):
    """按 axi 真实 JSON 结构判定数量与业务状态，而非只看命令成功。"""
    env, _, instance = control

    def run(command, **kwargs):
        output = "{}"
        if command == f"{AXI} list tushare":
            output = json.dumps({"server": "tushare", "tools": [{}] * 187})
        if " run tushare/daily " in command:
            output = json.dumps({"status": "success", "data": {"status": "success"}})
        return SimpleNamespace(exit_code=0, stdout=output)

    instance.commands.run.side_effect = run
    verify_sandbox(instance, env["KLI_QUANT_BACKEND_URL"], check_tools=True)
    assert instance.commands.run.call_count == 6


def test_cli_dependencies_are_declared():
    """防止直接导入依赖仅靠 axi 的间接依赖偶然可用。"""
    import ast
    from pathlib import Path

    imports = set()
    for path in Path("sandbox/cli").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    external = imports - sys.stdlib_module_names - {"sandbox"}
    mapping = {"axi": "kli-axi", "dotenv": "python-dotenv"}
    declared = Path("sandbox/requirements.in").read_text()
    assert all(mapping.get(name, name) + "==" in declared for name in external)


@pytest.mark.parametrize("status", ["service_error", "permission_denied", "empty"])
def test_business_failure_cleans_up(control, status):
    """CLI 退出成功也可能有业务错误，必须判失败并回收实例。"""
    env, _, instance = control
    instance.commands.run.side_effect = [
        SimpleNamespace(exit_code=0, stdout=""),
        SimpleNamespace(exit_code=0, stdout=json.dumps({"tools": [{}] * 187})),
        SimpleNamespace(exit_code=0, stdout="[]"),
        SimpleNamespace(exit_code=0, stdout="{}"),
        SimpleNamespace(
            exit_code=0,
            stdout=json.dumps({"status": "success", "data": {"status": status}}),
        ),
    ]
    with (
        pytest.raises(RuntimeError, match="业务验收失败"),
        temporary_sandbox(env) as sb,
    ):
        verify_sandbox(sb, env["KLI_QUANT_BACKEND_URL"], check_tools=True)
    instance.kill.assert_called_once()
