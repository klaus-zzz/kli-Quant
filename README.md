# kli-Quant

面向金融业务的开发骨架。目前只有 FastAPI 进程健康检查和 React/TypeScript 空应用，
页面明确显示“开发骨架”，通过真实请求确认后端状态，不展示模拟研究结果。

## 范围与目录

| 路径 | 当前职责 |
| --- | --- |
| `backend/` | FastAPI 入口，仅 `GET /api/health` |
| `frontend/` | React 空应用和 Vite 开发代理 |
| `sandbox/cli/` | CLI 目录说明，无可执行工具 |
| `tests/` | 健康接口回归与浏览器检查 |
| `compose.yaml` | 唯一开发 Compose，只启动前后端 |
| `AGENTS.md` | 公共规则及四个目录规则索引 |

尚未实现金融数据工具、多跳研究、Agent 对话、数据库业务表、对象归档、登录和支付。
后续 Agent 使用 OmniAgent `v1`，数据库使用 PostgreSQL，归档使用 SeaweedFS S3，
沙箱使用已有内网 CubeSandbox；本阶段不连接或启动这些服务，不构建沙箱镜像，不部署生产。

## 运行时基线

- Python **3.12.15**：由 `.python-version` 锁定，项目限定 3.12 系列，依赖由 `uv.lock` 锁定。
- uv **0.13.7**；Node.js **24.22.2**，前端依赖由 `package-lock.json` 锁定。
- Docker Engine 与 Compose v2；开发使用外部网络 `docker`。

兼容性核对：OmniAgent `v1`（1.0.0a84）声明 Python ≥3.11，
`kli-axi` 0.0.13 声明 ≥3.12，其模块和命令为 `axi`；
OmniAgent 沙箱定义基于 Python 3.12.11，现有 CubeSandbox 派生镜像
`iruiiii/omniagent-sandbox:quant-0.1.5` 实测 Python 3.12.15。
因此选择 3.12.15 作为统一开发基线。这里只核对运行时约束，未验证后续服务的完整集成。
本项目尚不安装 OmniAgent 或 kli-axi，也不复制它们的源码。

## 开发容器启动（推荐）

在仓库根目录执行：

```bash
# 网络只需创建一次，已有同名网络时直接复用。
docker network inspect docker >/dev/null 2>&1 || docker network create docker
cp .env.example .env
docker compose config --quiet
docker compose up -d --wait --wait-timeout 300
docker compose logs -f
```

页面地址为 <http://127.0.0.1:15173>，后端为 <http://127.0.0.1:18100/api/health>。
首次启动会下载锁定的依赖；若页面端口尚未就绪，等待前端日志出现 Vite 地址。
端口只绑定本机；如有冲突，修改根 `.env` 的 `FRONTEND_PORT` 或 `BACKEND_PORT`。
浏览器请求同源 `/api/health`，Vite 将其转发到后端容器。根 `.env` 仅用于 Compose 端口配置，
不会作为环境变量注入前端；请勿添加含凭据的 `VITE_*`。

前后端挂载当前仓库源码，Python 环境和 Node 依赖使用独立卷。
修改 `backend/main.py` 会重载后端，修改 `frontend/src/App.tsx` 会触发页面热更新。
依赖变更后更新对应锁文件，再执行 `docker compose restart`。

停止：`docker compose down`；要清除本项目的开发依赖卷：`docker compose down -v`。
外部 `docker` 网络不会被删除。

## 宿主机干净安装与启动

先安装上述 uv 和 Node 版本，再从仓库根目录执行：

```bash
uv sync --locked
npm --prefix frontend ci
uv run uvicorn backend.main:app --host 127.0.0.1 --port 18100 --reload
# 在第二个终端运行：
npm --prefix frontend run dev
```

宿主机模式的代理目标默认为 `http://127.0.0.1:18100`，无需 `.env`。
如需改端口，用 `BACKEND_PROXY_TARGET` 指向实际后端，并调整 Vite 的 `--port` 参数。

## 检查与验收

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
npm --prefix frontend run check
npm --prefix frontend run build
docker compose config --quiet
```

在当前源码的开发容器中复验：

```bash
docker compose exec -T backend uv run pytest
docker compose exec -T backend uv run ruff check .
docker compose exec -T backend uv run ruff format --check .
docker compose exec -T frontend npm run check
docker compose exec -T frontend npm run build
```

浏览器回归需要前后端已启动。在宿主机安装前端依赖后执行：

```bash
cd frontend
npx playwright install --with-deps chromium
npm run test:e2e
```

自定义前端端口时，设置 `PLAYWRIGHT_BASE_URL`。回归覆盖实际连通、HTTP 错误及无效响应；
还应手工核对请求等待状态、断网、窄屏展示，以及修改前后端源码后的热更新。
`/api/health` 返回 `{"status":"ok"}` 只代表当前后端进程能够响应，不表示外部服务就绪。
CI 执行依赖锁校验、后端回归、格式检查、前端构建及 Compose 配置校验。

## 许可

沿用仓库原有 [Apache License 2.0](LICENSE)。旧业务实现已移除；本仓库当前维护上述最小骨架。
