# 后端规则

- 本目录只提供 FastAPI 服务；入口为 `backend.main:app`。
- 当前唯一接口为 `GET /api/health`，只表示进程可响应，不探测数据库或其他外部服务。
- 不在初始化阶段引入金融表、数据工具、研究接口、后台任务或 Agent 客户端。
- Python 使用四空格缩进；依赖在根 `pyproject.toml` 管理，由 uv 更新锁文件。
- 在仓库根执行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`。
