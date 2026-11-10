# kli-Quant

面向金融业务的开发项目，提供 FastAPI 健康检查、187 个 Tushare 数据工具和研究业务接口。
React/TypeScript 页面提供持续对话、后台研究进度、取消、固定证据与版本复核，不展示模拟研究结果。

## 范围与目录

| 路径 | 当前职责 |
| --- | --- |
| `backend/` | 健康检查、受控 Tushare 入口、研究状态及证据归档 |
| `frontend/` | 对话与研究界面和 Vite 开发代理 |
| `fetcher/` | 独立原文抓取服务、镜像、依赖和专属测试 |
| `sandbox/cli/` | 离线契约、187 个 axi 工具及调用说明 |
| `sandbox/Dockerfile` | 专属 CubeSandbox 模板及隔离 CLI 依赖 |
| `sandbox/create_sandbox.py` | 可信控制端的临时沙箱创建与验收 |
| `tests/` | 后端回归、研究集成测试与浏览器检查 |
| `compose.yaml` | 前后端与隔离抓取服务的开发配置 |
| `AGENTS.md` | 公共规则及目录规则索引 |

研究接口支持多跳证据、固定归档和结果校验，原文抓取与解析使用
[Scrapling](https://github.com/D4Vinci/Scrapling) 和
[curl_cffi](https://curl-cffi.readthedocs.io/en/latest/api.html)。
抓取仅访问公网，使用 [nftables](https://www.nftables.org/) 隔离网络出口。
可显式启用 OmniAgent Gateway 与原生后台研究，聊天和研究共用私有会话沙箱，
使用单用户开发认证；
Gateway 客户端使用 [websockets](https://github.com/python-websockets/websockets) 建立连接。
详见 [Agent 接入](docs/agent.md) 和 [研究接口说明](docs/research-api.md)。

## 运行时基线

- Python **3.12.15**：由 `.python-version` 锁定，项目限定 3.12 系列，依赖由 `uv.lock` 锁定。
- uv **0.13.7**；Node.js **24.22.2**，前端依赖由 `package-lock.json` 锁定。
- Linux Docker Engine 与 Compose ≥2.33.1；开发使用外部网络 `docker`。

兼容性核对：OmniAgent `v1`（1.0.0a84）声明 Python ≥3.11，
`kli-axi` 0.0.13 声明 ≥3.12，其模块和命令为 `axi`；
OmniAgent 沙箱定义基于 Python 3.12.11，现有 CubeSandbox 派生镜像
`iruiiii/omniagent-sandbox:quant-0.1.5` 实测 Python 3.12.15。
因此选择 3.12.15 作为统一开发基线。
本项目使用 `kli-axi==0.0.13` 注册金融工具；[OmniAgent](https://github.com/aivp/OmniAgent)
使用独立镜像运行，只接公开 Gateway、历史与沙箱协议，不复制上游源码。
工具框架来自 [kli-axi](https://github.com/klaus-zzz/kli-axi)（基于 [AXI](https://github.com/deku0818/axi)）；
采用其 `754fb05` 版 `axi-use` 及 PTC 参考作为业务 Agent 的工具使用技能，
`axi-creator` 的适用规则整理在 [沙箱开发规则](sandbox/AGENTS.md)，用于维护原生工具接入。
工具契约、调用方式和安全边界见 [Tushare 工具说明](sandbox/cli/README.md)。
专属模板使用 [CubeSandbox](https://github.com/TencentCloud/CubeSandbox) 的 envd 执行命令，
控制端通过官方 Python SDK 创建实例并动态注入后端地址，见同一说明中的模板章节。
独立模板验收入口不启动 Agent；业务接线复用该模板，并在任务初始化时装载研究 CLI。
镜像构建成功不代表集群模板注册、网络和业务调用均已通过。

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
前端端口只绑定本机，后端端口发布到宿主机所有接口，供受控内网沙箱访问。
请限制后端端口的网络访问来源；如有端口冲突，修改根 `.env` 的 `FRONTEND_PORT` 或 `BACKEND_PORT`。
浏览器请求同源 `/api/health`，Vite 将其转发到后端容器。根 `.env` 支持 Compose 端口配置
及 `TUSHARE_TOKEN`、`TUSHARE_BASE_URL`，并通过后端的 `env_file` 加载到后端容器；
前端不加载该文件，请勿添加含凭据的 `VITE_*`。
`TUSHARE_BASE_URL` 默认使用 `https://api.tushare.pro`；修改 `.env` 后执行
`docker compose up -d backend` 更新容器环境。

后端挂载仓库，前端只挂载 `frontend/` 和浏览器测试目录，依赖使用独立卷。
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
uv run --directory fetcher pytest
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

自定义前端端口时，设置 `PLAYWRIGHT_BASE_URL`。健康回归经过实际开发代理和后端；
对话回归使用受控响应覆盖消息恢复、幂等重试、断网、取消、版本链接和内容安全，不能代替真实模型验收。
还应核对真实 Agent 后台执行、主动回复，以及修改前后端源码后的热更新。
`/api/health` 返回 `{"status":"ok"}` 只代表当前后端进程能够响应，不表示外部服务就绪。
CI 分别校验后端与抓取器的锁文件和回归测试，并检查格式、前端构建及 Compose 配置。
抓取服务的部署配置和验证方式见 [fetcher 说明](fetcher/README.md)。

## 对话与研究入口

只启动默认开发服务时，页面可检查后端健康；真实对话需按 [Agent 接入](docs/agent.md)
配置研究存储并启动 `agent` profile。页面输入独立的开发聊天凭据，发送事件、链接或普通问题。
研究在右侧更新，可以取消、查看支持与反证、核对固定数据和执行代码，再补充证据触发复核。
窄屏通过“对话 / 研究”切换工作面。

页面刷新后重新输入聊天凭据恢复会话；不会把服务端凭据存入浏览器。研究版本有固定地址，
新结果保留旧版本。当前采用两秒快照轮询，正文按纯文本展示；尚不提供多用户登录或生产认证。
“证据不足”“没有机会”是业务结果；超时、执行失败和校验拒绝会单独提示，不伪装成有效报告。

## 许可

沿用仓库原有 [Apache License 2.0](LICENSE)。接口字段及权限说明以各契约链接的官方文档为准。
