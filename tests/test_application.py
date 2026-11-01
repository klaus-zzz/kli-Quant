"""领域扩展只能通过公开契约接入，通用应用不能获得金融权限。"""

from unittest.mock import patch

import pytest
from fina_agent.agent.contracts import ToolError
from fina_agent.agent.tools.runner import ToolRunner
from fina_agent.applications import get_application


def test_registration_and_version_are_explicit():
    app = get_application("kli-quant")
    assert app.version == "0.1.0"
    assert "get_market_snapshot" in app.tools
    with pytest.raises(ToolError, match="application_not_installed"):
        get_application("assistant")
    assert "先拆解影响链条" in app.prompt
    with pytest.raises(ToolError, match="application_version_changed"):
        get_application("kli-quant", "different")


def test_financial_finish_still_rejects_unsubstantiated_signal(store, settings):
    from fina_agent.agent.contracts import Action

    store.run.input = {"application": "kli-quant", "application_version": "0.1.0"}
    store.session.commit()
    with patch.object(store.session, "refresh"):
        output = ToolRunner(store, settings).call(
            0, Action(name="finish", arguments={"outcome": "observation", "conclusion": "虚构利好"})
        )
    assert output["status"] == "failed"
    assert not store.records("judgment")
