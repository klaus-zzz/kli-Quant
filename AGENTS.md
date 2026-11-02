# kli-Quant 开发约定

## 阅读顺序与目录索引

修改前先读本文件、README.md，再沿目标路径逐层读取已有 AGENTS.md 和目标模块；跨目录任务逐项读取。
本文件保留通用约定，子目录只补充局部职责，不复制上层规则。
新目录只有出现独立职责或约束时才增加规则，并更新最近的上级索引。

| 修改范围 | 规则入口 | 职责 |
| --- | --- | --- |
| `src/kli_quant/` | [应用规则](src/kli_quant/AGENTS.md) | 应用注册、后端配置与 HTTP CLI |
| `src/kli_quant/finance/` | [金融规则](src/kli_quant/finance/AGENTS.md) | 输入契约、固定行情和正式结果校验 |
| `tests/` | [测试规则](tests/AGENTS.md) | 共享夹具、单元测试与集成测试索引 |
| `frontend/` | [前端工程规则](frontend/AGENTS.md) | npm 工程、开发代理与构建 |
| `frontend/src/` | [界面规则](frontend/src/AGENTS.md) | 对话、研究展示与交互 |
| 根目录、`.github/`、`docs/` | 本文件 | 项目说明、开发容器、CI 与文档资产 |

## 通用约定

- 本项目是独立金融应用；通用运行时由 Fina-Agent / Deep Agents 提供。
- Python 使用 uv，沟通与独立职责注释使用中文。
- Python 版本以 pyproject.toml 为准；从根目录执行 uv sync / uv run，提交 uv.lock，不手工修改锁文件。
- 遵循工作区先设计、最小改动和凭据保护规则；不为假设中的需求增加分层。
- 本项目使用独立 Fina-Agent 实例，业务提示及模板选择统一在 Fina-Agent/.fina-agent/ 配置并挂载，不在本仓库复制配置；数据库与归档 bucket 不和其他项目实例共用。
- 不复制 OmniQuant 的服务配置或用户数据；参考业务规则必须补验收。

## 金融与权限边界

- 应用通过安装包入口点向可信后端注册工具；客户端只通过 HTTP 提交任务。
- 模型不能决定权限、时点、预算；数据凭据只由后端读取。
- 固定原文、行情和计算口径；正式结果必须重算并验证引用，不承诺投资收益。
- 新证据创建新执行，历史证据与结论不可覆盖。

## 修改与验证

- 发现缺陷先补复现测试；重构前后运行相关测试，确认行为一致。
- 检查：uv run ruff check .、uv run ruff format --check .、uv run pytest -m 'not integration'。
- 行为变更按 ponytail、针对性测试、ponytail-review、隔离开发容器、真实联调顺序完成。
- 纯文档修改检查内容与链接；前端检查见局部规则。
- 验证后提交功能分支并创建 PR；本任务不部署生产，不提交凭据。
- 清理任务临时资源，保留源测试和依赖环境；结果默认直接在对话中报告。
