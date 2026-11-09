"""配置在启动时拒绝 SDK 不接受的控制 Token，避免聊天中途失败。"""

from types import SimpleNamespace

import pytest

from backend.agent.config import configured_runtime


def test_nonascii_control_token_is_rejected_without_server_error():
    from backend.agent.cube_api import control
    from backend.research.models import ResearchError

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                agent=SimpleNamespace(env={"KLI_QUANT_CONTROL_TOKEN": "control-secret"})
            )
        ),
        headers={"X-API-Key": "错误令牌"},
    )
    with pytest.raises(ResearchError, match="unauthorized"):
        control(request)


def test_stop_sets_flag_before_waiting_for_transport_cleanup():
    import asyncio
    from unittest.mock import Mock

    from backend.agent.runtime import Runtime

    async def scenario():
        runtime = Runtime(SimpleNamespace(repo=None), {})
        runtime.recover = Mock()

        async def transport():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # 模拟连接收尾吞掉取消，仍须由停止标记退出重连循环。
                await runtime.stopping.wait()

        runtime.task = asyncio.create_task(transport())
        runtime.supervisor = asyncio.create_task(runtime.stopping.wait())
        await asyncio.sleep(0)
        stopper = asyncio.create_task(runtime.stop())
        await asyncio.sleep(0.02)
        stopping = runtime.stopping.is_set()
        runtime.stopping.set()
        await stopper
        assert stopping
        runtime.recover.assert_called_once()

    asyncio.run(scenario())


def test_gateway_stop_does_not_wait_for_another_incoming_frame(monkeypatch):
    import asyncio
    from unittest.mock import Mock

    from backend.agent.runtime import Runtime

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def __aiter__(self):
            await asyncio.Event().wait()
            yield ""

    monkeypatch.setattr("backend.agent.runtime.connect", lambda *a, **k: Connection())
    runtime = Runtime(
        SimpleNamespace(repo=None),
        {"OMNIAGENT_URL": "http://agent", "OMNIAGENT_GATEWAY_TOKEN": "gateway"},
    )
    runtime.lease = Mock()

    async def stop_during_tick():
        runtime.stopping.set()

    runtime.tick = stop_during_tick
    asyncio.run(asyncio.wait_for(runtime.run(), timeout=1))


def test_control_token_must_match_e2b_sdk_format(tmp_path, monkeypatch):
    values = {
        "CUBESANDBOX_API_URL": "http://127.0.0.1:8080",
        "CUBESANDBOX_DOMAIN": "cube.example",
        "CUBESANDBOX_TEMPLATE_ID": "template",
        "CUBE_PROXY_NODE_IP": "127.0.0.1",
        "E2B_API_KEY": "upstream",
        "KLI_QUANT_BACKEND_URL": "http://127.0.0.1:18100",
        "OMNIAGENT_URL": "http://agent:8090",
        "OMNIAGENT_GATEWAY_TOKEN": "gateway",
        "KLI_QUANT_CHAT_TOKEN": "chat" * 10,
        "KLI_QUANT_CONTROL_TOKEN": "control" * 10,
    }
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()))
    monkeypatch.setenv("KLI_QUANT_AGENT_ENV_FILE", str(path))
    with pytest.raises(ValueError, match="e2b_"):
        configured_runtime(SimpleNamespace(repo=None))
