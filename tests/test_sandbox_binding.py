"""研究网络策略只允许业务入口；不请求真实沙箱。"""

from types import SimpleNamespace

import pytest

from backend.agent.sandboxes import CLI
from sandbox.binding import bound_options


def test_control_plane_loads_this_repository_cli():
    assert (CLI / "research.py").is_file()
    assert (CLI / "axi.json").is_file()


def test_expired_chat_cannot_replace_agent_cached_sandbox(monkeypatch):
    from datetime import UTC, datetime, timedelta
    from unittest.mock import Mock

    from backend.agent.sandboxes import Sandboxes
    from backend.research.models import ResearchError

    boxes = Sandboxes(None, {})
    monkeypatch.setattr(
        boxes,
        "row",
        lambda _: {
            "active": True,
            "expires_at": datetime.now(UTC) - timedelta(seconds=1),
        },
    )
    boxes.close = Mock()
    with pytest.raises(ResearchError, match="session_expired"):
        boxes.ensure("expired", "expired")
    boxes.close.assert_not_called()


def test_bound_policy_keeps_identity_outside_sandbox(monkeypatch):
    """绑定身份只能出现在代理规则，不能进入模型可读的环境或元数据。"""
    monkeypatch.setattr(
        "sandbox.binding.creation_options",
        lambda env: {
            "network": {"allow_out": ["192.0.2.1/32"]},
            "envs": {"KLI_QUANT_BACKEND_URL": env["KLI_QUANT_BACKEND_URL"]},
        },
    )
    import sys

    monkeypatch.setitem(
        sys.modules,
        "cubesandbox",
        SimpleNamespace(**dict.fromkeys(("Rule", "Match", "Action", "Inject"), dict)),
    )
    options = bound_options(
        {"KLI_QUANT_BACKEND_URL": "http://192.0.2.1:18100"},
        "only-on-host",
        "kq-test",
        "developer",
        120,
    )
    assert options["allow_internet_access"] is False
    assert options["network"]["allow_public_traffic"] is False
    assert "allow_out" not in options["network"]
    assert "only-on-host" not in str(options["envs"])
    assert "only-on-host" not in str(options["metadata"])
    rules = options["network"]["rules"]
    assert {r["match"]["path"] for r in rules} == {"/api/research/*", "/api/tushare/*"}
    for rule in rules:
        assert rule["match"]["host"] == "192.0.2.1"
        assert rule["match"]["port"] == 18100
        assert rule["action"]["inject"][0]["secret"] == "only-on-host"


@pytest.mark.parametrize("url", ["http://backend.test:18100", "http://192.0.2.1/a"])
def test_plain_http_requires_fixed_destination(monkeypatch, url):
    """明文身份注入固定目标 IP，拒绝 DNS 改向和隐含路径前缀。"""
    monkeypatch.setattr("sandbox.binding.creation_options", lambda env: {})
    with pytest.raises(ValueError):
        bound_options({"KLI_QUANT_BACKEND_URL": url}, "secret", "kq-x", "dev", 60)
