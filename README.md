# kli-Quant

基于 [Fina-Agent](https://github.com/klaus-zzz/Fina-Agent) / Deep Agents 的独立量化研究应用。
当前提供 A 股事件查证、固定 Tushare 日线、沙箱计算、条件性观察校验与新证据复核。
这是新项目：参考 OmniQuant 的研究准入与计算口径经验，不复制其部署或用户数据。
尚未完成与 OmniQuant 的同条件对照，不宣称效果更好或保证投资收益。

## 分工

- Fina-Agent 运行 Agent、控制预算/权限、管理 CubeSandbox、S3、任务与界面。
- kli-Quant 提供金融配置目录、get_market_snapshot、正式产物及结论校验。
- CLI 通过 HTTP 提交任务，不读取模型或 Tushare 凭据。
- 该实例工作台固定使用 kli-Quant 应用；没有另造一套聊天或任务运行系统。

## 开发运行

Python 3.13、uv 和 Fina-Agent 0.2.x；两个仓库放在同一父目录（当前锁文件使用相对路径依赖）：
底座尚未合入主分支时，请检出本项目 CI 中固定的底座提交。

```text
workspace/
  Fina-Agent/backend/
  kli-Quant/
```

```bash
uv sync --locked
uv run kli-quant --help
```

本项目使用独立 Fina-Agent 实例，经 HTTP 接入；业务提示在 `.fina-agent/prompts/AGENTS.md`
维护，模板在 `.fina-agent/config.yaml` 的 `sandbox.template_id` 配置，null 沿用实例环境变量。
修改后重启 API 和 Worker；已创建任务保留旧提示词与模板。

按底座 README 的独立实例示例启动，设置 AGENT_APPLICATION_DIR 为本项目，
AGENT_CONFIG_DIR 为本项目 `.fina-agent`，AGENT_ENV_FILE 为本项目 `.env`。
凭据文件仅供后端挂载读取，包含模型、PG、S3、CubeSandbox、Tushare 和可选 LangSmith 配置。
请使用独立开发数据库与 bucket；服务端可共用，但任务队列不能和其他项目混用。
客户端不读取这些凭据。默认 kli-Quant 实例 API 端口 8001，CLI 使用 `--server` 指定地址。
启动后 `GET /api/applications` 应只包含 kli-quant；配置完整不代表数据源已经连通。

```bash
uv run kli-quant --server http://127.0.0.1:8001 research '核实某事件对公司的影响，主动查找反证；证据不足时明确说明'
uv run kli-quant --server http://127.0.0.1:8001 research '新增待核实材料' --topic <research_id> --url https://example.com/source
uv run kli-quant --server http://127.0.0.1:8001 status <run_id>
```

## 金融边界

- 当前只支持 A 股 daily / 1d / none；一次最多三只证券、一年区间。
- 价格保留十进制文本，成交量为手，成交额为千元；缺失值不补零。
- 排除截止点当天未完成日线。历史行情标记 historical_reconstruction，不宣称点时数据。
- 正式 signal 产物由后端重算 close_return，验证日期、单位、币种、口径和引用。
- backtest 当前仅是带基准的区间收益比较，尚不是含费用、滑点的策略回测。
- observation 必须有正反查证、可确定时间的支持证据、条件与 validated signal 产物。
- 允许 insufficient_evidence 或 no_opportunity，不为了完成任务编造机会。
- 新材料创建新执行并保留旧结论；细粒度判断依赖图和自动监控尚未实现。
- 第一版无自动交易、复杂选股策略或多 Agent；金融规则变更需要升级应用版本。

## 验证

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -m 'not integration'
```

离线测试不联网、不读取个人凭据。集成测试仅使用 FINA_TEST_DATABASE_URL 指定的专用库。
隔离容器内装好本应用与底座，工作目录设为底座 backend（读取其 .env）：

```bash
FINA_LIVE_SERVICES=1 python -m pytest /app/application/tests/test_live_services.py -s
FINA_LIVE_AGENT=1 python -m pytest /app/application/tests/test_live_agent.py -s
```

真实测试需要现有已授权服务额度；测试结束清理自身执行对应的沙箱、S3 对象和数据库记录。
不使用生产数据库，不把测试替身结果展示为真实接入。

代码采用 Apache-2.0；数据服务许可独立于代码许可。
