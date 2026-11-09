"""可信控制端创建临时沙箱并验收；管理凭据不会注入沙箱。"""

import argparse
import json
import os
import shlex
from contextlib import contextmanager
from ipaddress import ip_address
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = "/opt/kli-quant"
PYTHON = f"{ROOT}/venv/bin/python"
AXI = f"{ROOT}/venv/bin/axi"


def creation_options(environ):
    """创建前校验配置，仅注入后端地址和 CLI 配置路径。"""
    required = (
        "CUBESANDBOX_API_URL",
        "CUBESANDBOX_DOMAIN",
        "CUBESANDBOX_TEMPLATE_ID",
        "KLI_QUANT_BACKEND_URL",
        "E2B_API_KEY",
    )
    values = {key: environ.get(key, "").strip() for key in required}
    for key, value in values.items():
        if not value:
            raise ValueError(f"缺少配置：{key}")
    for key in ("CUBESANDBOX_API_URL", "KLI_QUANT_BACKEND_URL"):
        url = urlsplit(values[key])
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
        ):
            raise ValueError(f"配置必须为不含凭据、查询或片段的 HTTP 地址：{key}")
        values[key] = values[key].rstrip("/")
    # 集群默认拦截内网；按后端配置放行单个主机，不扩大到整个内网网段。
    backend_host = urlsplit(values["KLI_QUANT_BACKEND_URL"]).hostname
    try:
        address = ip_address(backend_host)
        destination = f"{address}/{address.max_prefixlen}"
    except ValueError:
        destination = backend_host
    # 延迟导入让普通测试和后端无需安装管理 SDK。
    from cubesandbox import Config

    return {
        "template": values["CUBESANDBOX_TEMPLATE_ID"],
        "config": Config(
            api_url=values["CUBESANDBOX_API_URL"],
            api_key=values["E2B_API_KEY"],
            sandbox_domain=values["CUBESANDBOX_DOMAIN"],
            proxy_node_ip=environ.get("CUBE_PROXY_NODE_IP") or None,
        ),
        "envs": {
            "KLI_QUANT_BACKEND_URL": values["KLI_QUANT_BACKEND_URL"],
            "AXI_CONFIG": f"{ROOT}/sandbox/cli/axi.json",
        },
        "timeout": 300,
        "network": {"allow_out": [destination]},
    }


@contextmanager
def temporary_sandbox(environ=None):
    """创建后的任何验收失败都执行清理，五分钟 TTL 作为失联兜底。"""
    options = creation_options(os.environ if environ is None else environ)
    from cubesandbox import Sandbox

    sandbox = Sandbox.create(**options)
    try:
        yield sandbox
    finally:
        sandbox.kill()


def checked_command(sandbox, command):
    """SDK 对非零退出码不抛错，因此在控制端明确判定失败。"""
    result = sandbox.commands.run(command, timeout=90)
    if result.exit_code != 0:
        raise RuntimeError(f"沙箱命令失败（退出码 {result.exit_code}）：{command}")
    return result.stdout


def verify_sandbox(sandbox, backend_url, *, check_tools=False):
    """默认仅检查健康与离线工具；业务调用须显式指向测试后端。"""
    # 通过同一个独立解释器验证注入与 PTC；不依赖登录 shell 的 PATH。
    probe = f"""
import os
import httpx
from sandbox.cli import tushare
assert os.environ['KLI_QUANT_BACKEND_URL'] == {backend_url.rstrip("/")!r}
assert os.environ['AXI_CONFIG'] == {f"{ROOT}/sandbox/cli/axi.json"!r}
assert len(tushare.CONTRACTS) == 187
assert not any(k in os.environ for k in (
    'TUSHARE_TOKEN', 'E2B_API_KEY', 'CUBE_API_KEY', 'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY', 'LANGSMITH_API_KEY', 'POSTGRES_PASSWORD'))
r = httpx.get(os.environ['KLI_QUANT_BACKEND_URL'] + '/api/health',
              timeout=10, trust_env=False)
r.raise_for_status()
assert r.json() == {{'status': 'ok'}}
"""
    checked_command(sandbox, f"{PYTHON} -c {shlex.quote(probe)}")
    tools = json.loads(checked_command(sandbox, f"{AXI} list tushare"))
    if len(tools.get("tools", [])) != 187:
        raise RuntimeError("沙箱未注册完整的 187 个工具")
    checked_command(sandbox, f"{AXI} search 股票日线")
    checked_command(sandbox, f"{AXI} describe tushare/daily")
    if check_tools:
        # 固定样例仅用于显式选择的测试后端，验收信封中的业务状态。
        command = f'{AXI} run tushare/daily -j \'{{"ts_code":"000001.SZ"}}\''
        result = json.loads(checked_command(sandbox, command))
        if (
            result.get("status") != "success"
            or (result.get("data") or {}).get("status") != "success"
        ):
            raise RuntimeError("CLI 业务验收失败")
        ptc = (
            "from axi import tool; "
            "r = tool('tushare/daily')(ts_code='000001.SZ'); "
            "assert r['status'] == 'success'"
        )
        checked_command(sandbox, f"{PYTHON} -c {shlex.quote(ptc)}")


def main():
    """显式读取集中配置；进程环境优先，便于同模板切换测试后端。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="/workspace/deploy/kli-quant/.env")
    parser.add_argument(
        "--check-tools", action="store_true", help="仅对测试后端执行 CLI/PTC 请求"
    )
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False, interpolate=False)
    with temporary_sandbox() as sandbox:
        verify_sandbox(
            sandbox, os.environ["KLI_QUANT_BACKEND_URL"], check_tools=args.check_tools
        )
    print("沙箱验收通过，临时实例已清理")


if __name__ == "__main__":
    main()
