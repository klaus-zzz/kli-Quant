"""在开发 Agent 容器运行的配置冒烟检查；不请求付费模型接口。"""

import tempfile

from langchain_core.messages import HumanMessage
from omniagent.config import get_config
from omniagent.llm import catalog
from omniagent.llm.manager import create_llm
from omniagent.llm.thinking import allowed_levels


def main():
    """验证缓存可写、能力目录身份正确，以及档位进入实际请求体。"""
    config = get_config()
    cache = config.config_dir / "cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryFile(dir=cache) as probe:
        probe.write(b"cache writable")

    model = config.config.agent.models.main
    assert model is not None, "缺少主模型"
    match = catalog.match(model)
    assert match.kind == "exact", "模型能力必须精确匹配，检查 alias 和缓存"
    assert match.entry.catalog_id.rsplit("/", 1)[-1] == model.model, (
        "模型能力别名与实际请求模型不一致"
    )
    levels = allowed_levels(model)
    assert levels, "模型目录未提供思考档位"
    if model.model == "gpt-6.1-sol":
        assert levels == ("low", "medium", "high", "xhigh", "max"), levels

    # 检查 SDK 最终组装的请求，不只确认界面或中间参数存在。
    for effort in levels:
        llm = create_llm(model.model, effort=effort)
        payload = llm._get_request_payload([HumanMessage(content="配置检查")])
        actual = payload.get("reasoning_effort") or payload.get("reasoning", {}).get(
            "effort"
        )
        assert actual == effort, f"请求体未携带档位 {effort}"
    print(f"通过：{model.model}，档位 {', '.join(levels)}；缓存可写、请求参数正确")


if __name__ == "__main__":
    main()
