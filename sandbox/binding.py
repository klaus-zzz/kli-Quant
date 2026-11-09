"""研究沙箱的宿主侧身份绑定；不把业务凭据交给沙箱。"""

from ipaddress import ip_address
from urllib.parse import urlsplit

from sandbox.create_sandbox import creation_options


def bound_options(environ, identity, thread_id, user_id, timeout):
    """复用模板配置，以精确 L7 规则替代整机 IP 放行。"""
    options = creation_options(environ)
    url = urlsplit(environ["KLI_QUANT_BACKEND_URL"])
    if url.path not in {"", "/"}:
        raise ValueError("研究后端地址不能包含路径前缀")
    if url.scheme == "http":
        # 明文代理不能验证域名对端，内网接入必须固定目的 IP。
        ip_address(url.hostname)
    from cubesandbox import Action, Inject, Match, Rule

    rules = []
    for name, path, methods in (
        ("research", "/api/research/*", ["GET", "POST"]),
        ("tushare", "/api/tushare/*", ["POST"]),
    ):
        rules.append(
            Rule(
                name=name,
                match=Match(
                    host=url.hostname,
                    port=url.port or (443 if url.scheme == "https" else 80),
                    scheme=url.scheme,
                    path=path,
                    method=methods,
                ),
                action=Action(
                    allow=True,
                    inject=[Inject(header="Authorization", secret=identity)],
                ),
            )
        )
    options.update(
        timeout=timeout,
        allow_internet_access=False,
        network={"allow_public_traffic": False, "rules": rules},
        metadata={"thread_id": thread_id, "user_id": user_id},
    )
    return options
