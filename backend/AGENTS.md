# 后端规则

- 本目录只提供 FastAPI 服务；入口为 `backend.main:app`。
- `GET /api/health` 只表示进程可响应，不探测数据库或其他外部服务。
- Tushare 通过受控 POST 入口调用，共用离线契约白名单；凭据仅由后端读取，不回显上游错误原文。
- 研究索引使用 PostgreSQL 参数化 SQL 和版本化迁移，原文与固定产物使用 SeaweedFS S3；不得信任模型自报归属、预算或执行成功。
- 未接入可信身份或执行器时研究接口明确返回未就绪；不在本目录重建 Agent 框架。
- OmniAgent 配置、提示词和原生 subagent 定义统一维护在 `/workspace/deploy/kli-quant/.omniagent/`，不放入后端源码；沿用整个配置目录的 Compose 挂载。模型只配置 main。
- Python 使用四空格缩进；依赖在根 `pyproject.toml` 管理，由 uv 更新锁文件。
- 在仓库根执行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`。
