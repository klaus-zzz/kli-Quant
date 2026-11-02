# kli-Quant 开发约定

- 本项目是独立金融应用；通用运行时由 Fina-Agent / Deep Agents 提供。
- Python 使用 uv，沟通与独立职责注释使用中文。
- 修改前阅读 README.md 和目标模块；遵循工作区先设计、最小改动和凭据保护规则。
- 应用通过安装包入口点向可信后端注册工具；客户端只通过 HTTP 提交任务。
- 本项目使用独立 Fina-Agent 实例，业务提示及模板选择统一在 Fina-Agent/.fina-agent/ 配置并挂载，不在本仓库复制配置；数据库与归档 bucket 不和其他项目实例共用。
- 模型不能决定权限、时点、预算；数据凭据只由后端读取。
- 固定原文、行情和计算口径；正式结果必须重算并验证引用，不承诺投资收益。
- 新证据创建新执行，历史证据与结论不可覆盖。
- 不复制 OmniQuant 的服务配置或用户数据；参考业务规则必须补验收。
- 检查：uv run ruff check .、uv run ruff format --check .、uv run pytest -m 'not integration'。
- 行为变更按 ponytail、针对性测试、ponytail-review、隔离开发容器、真实联调顺序完成。
- 测试数据库仅使用 FINA_TEST_DATABASE_URL；真实服务测试需要显式 live 标记。
- 验证后提交功能分支并创建 PR；本任务不部署生产，不提交凭据。
- 清理任务临时资源，保留源测试和依赖环境；结果默认直接在对话中报告。

- 金融工作台在 frontend/，修改时读 frontend/AGENTS.md 和 frontend/src/AGENTS.md；前端使用 npm，提交 package-lock.json。

- 本项目 Compose 继承通用 Agent dev 服务并负责安装金融包；不得要求底座 Compose 硬编码本项目。
- 金融结果字段及发布时间之后的评估约束由本应用维护，通用底座只保存不可变记录和执行状态。
