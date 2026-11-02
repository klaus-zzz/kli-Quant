# kli-Quant

基于 Deep Agents 的独立金融研究服务。对话入口由 [Fina-Agent](https://github.com/klaus-zzz/Fina-Agent)
提供；A 股事件多跳研究作为 HTTP 后台工具接入，支持固定行情、沙箱计算、证据与版本。
研究完成后唤醒对话 Agent 主动解释结果，研究期间仍可继续聊天或取消。

## 职责与配置

- 本仓库：金融 HTTP 服务、研究 Worker、行情与结果校验、React 工作台。
- Fina-Agent：通用对话、WebSocket Gateway、HTTP 工具调度、沙箱与归档运行库。
- Fina-Agent 不安装本包；金融服务单向使用它的通用 Python 库，并在独立容器、数据库执行。
- 配置集中在 Fina-Agent/.fina-agent；金融服务挂载 providers/kli-quant，模板与 Prompt 不在本仓库复制。

`src/kli_quant/service.py` 实现提交、查询、取消和结果引用；领域规则位于 finance/。
`frontend/` 经同源网关聊天，经底座代理查看金融详情，不持有任何服务凭据。
[开发规则](AGENTS.md) 按目录分层，另一个会话的目录整理可独立合并。

## 开发运行

Python 3.13、uv、Node 24；两仓库相邻放置。按 Fina-Agent README 配置它的根 `.env`：
DATABASE_URL 为对话库，KLI_DATABASE_URL 为独立金融库，两者不能相同；
KLI_TOOL_TOKEN 为两端共享服务令牌。模型、Tushare、S3、CubeSandbox 仍由后端读取。
所有服务使用外部 docker 网络，金融服务默认不向宿主发布端口。

先从 Fina-Agent 启动并迁移对话服务，然后在本仓库：

```bash
uv sync --locked
docker compose build research-dev
docker compose run --rm research-dev sh -ec 'uv sync --locked && .venv/bin/python -m kli_quant.migrate'
docker compose up -d
```

工作台 http://127.0.0.1:5173，默认代理 fina-agent-dev-agent-dev-1:8000。
AGENT_PROXY_TARGET 可覆盖底座地址，AGENT_ENV_FILE / AGENT_CONFIG_DIR 控制集中配置挂载。
配置修改后重启对应服务；旧执行保留创建时提示词与模板。
`docker compose down` 停止开发容器，不部署生产。

金融服务内部入口是 kli-research:8000，HTTP 契约在 Fina-Agent/docs/http-tools.md。
CLI 适用于具有服务凭据的后端操作环境，不应把令牌交给普通浏览器用户：

```bash
uv run kli-quant --server http://kli-research:8000 --scope <UUID> research '核实事件并查找反证'
uv run kli-quant --server http://kli-research:8000 --scope <UUID> research '新增线索' --parent <task_id>
uv run kli-quant --server http://kli-research:8000 --scope <UUID> status <task_id>
uv run kli-quant --server http://kli-research:8000 --scope <UUID> cancel <task_id>
```

重试提交可传同一个 --request-id；新证据必须引用该主题最新终态版本，否则拒绝。
旧研究数据不自动迁移或删除，旧界面历史入口仅查询旧底座数据库；新研究从会话任务卡查看。
旧金融会话固定原应用，切换为独立服务后应创建新会话，不能静默改写历史。

## 金融边界

支持 A 股 daily / 1d / none，每次最多三只证券、一年区间；价格保留十进制文本，
成交量为手、成交额为千元。排除截止点当天未完成日线，不把历史重建说成点时数据。
正式 signal / backtest 重算 close_return 并验证时间、单位、引用和计算口径；
backtest 仅表示带基准的区间收益比较，不包含完整交易、费用或滑点模型。
observation 需要支持和反向查证、可确定时间的证据、条件及 validated signal。
允许 insufficient_evidence 或 no_opportunity，不编造机会，不宣称收益。
新证据追加执行和判断，保留旧版；不做自动交易、复杂选股或多 Agent。

## 验证

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -m 'not integration'
npm --prefix frontend ci
npm --prefix frontend run build
```

真实测试须显式设置 FINA_LIVE_SERVICES=1 或 FINA_LIVE_AGENT=1；数据库仅使用
FINA_TEST_DATABASE_URL 专用测试库。跨服务 Gateway 测试另外要求独立的
FINA_TEST_CORE_DATABASE_URL、FINA_TEST_GATEWAY_URL 和 FINA_TEST_PROVIDER_URL。
只有实走 HTTP/Gateway、模型、行情、归档和沙箱才算真实接入，不用替身代替。
测试清理自身记录与对象，保留测试源码和已有服务。Apache-2.0，数据许可独立。
