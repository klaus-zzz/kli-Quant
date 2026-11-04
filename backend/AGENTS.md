# 后端规则

- 本目录只提供 FastAPI 服务；入口为 `backend.main:app`。
- `GET /api/health` 只表示进程可响应，不探测数据库或其他外部服务。
- Tushare 通过受控 POST 入口调用，共用离线契约白名单；凭据仅由后端读取，不回显上游错误原文。
- 不引入金融表、研究接口、后台任务或 Agent 客户端。
- Python 使用四空格缩进；依赖在根 `pyproject.toml` 管理，由 uv 更新锁文件。
- 在仓库根执行 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`。
