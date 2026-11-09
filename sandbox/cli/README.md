# Tushare 工具

本目录提供 187 个独立的 `tushare/<接口名>` axi 工具。`contracts/` 保存逐接口的
中文说明、官方来源、核对日期、参数 schema、原始输出字段、单位说明和文档修正。
`restricted.json` 仅记录独立授权、权限不明、写入、停用及非 HTTP 能力，不注册工具。

## 安装与调用

在仓库根目录安装锁定依赖，启动后端；开发运行时版本见根 README。

```bash
uv sync --locked
# 只给后端加载根目录凭据；不要给 axi 导出 TUSHARE_TOKEN。
uv run uvicorn backend.main:app --host 127.0.0.1 --port 18100 --env-file .env
```

另一个终端从仓库根目录执行：

```bash
export AXI_CONFIG="$PWD/sandbox/cli/axi.json"
export PYTHONPATH="$PWD"
# 首次配置时复制，并按需修改其中的后端地址。
cp -n sandbox/cli/.env.example sandbox/cli/.env
uv run axi list tushare
uv run axi search "股票日线"
uv run axi describe tushare/daily
uv run axi run tushare/daily -j '{"ts_code":"000001.SZ","trade_date":"20261030","fields":"ts_code,trade_date,close"}'
```

`list`、`search`、`describe` 只需本地契约。工具通过公开 `axi.tool` 装饰器注册，
根据契约生成函数签名；不读取 axi 的私有注册表。PTC（在 Python 中直接调用工具）
使用相同配置和实现：

```python
from axi import tool

# 本地函数只转发到后端，不持有数据源凭据。
result = tool("tushare/daily")(ts_code="000001.SZ", trade_date="20261030")
```

CLI 按以下优先级读取 `KLI_QUANT_BACKEND_URL`：进程环境变量、
`sandbox/cli/.env`、默认地址 `http://127.0.0.1:18100`。
文件路径相对于 `tushare.py` 定位，切换工作目录不影响读取；文件缺失或值为空时使用默认地址。
不会搜索根 `.env`，也不将文件中的其他变量导出到进程；模型参数不能改地址。
分发时需要 CLI 代码、包路径和依赖（含 `python-dotenv`），不复制根 `.env` 或后端配置。
CLI 的 `.env` 不提交版本库，里面只填写后端地址：

```dotenv
KLI_QUANT_BACKEND_URL=http://127.0.0.1:18100
```

CubeSandbox 控制端读取集中配置，再注入到新沙箱；可复用创建入口：

```python
from sandbox.create_sandbox import AXI, checked_command, temporary_sandbox

# 配置来自创建沙箱的服务，地址无需写入 CLI 或模板镜像。
with temporary_sandbox() as sandbox:
    # 创建时注入的变量会被 commands.run 启动的 CLI 继承。
    checked_command(sandbox, f"{AXI} list tushare")
```

前提是沙箱已安装 CLI 依赖并配置 `AXI_CONFIG` 和模块路径。
也可给单次 `sandbox.commands.run(..., envs={...})` 传入变量。
`run_code` 默认不会继承创建沙箱时的 `envs`，不要与 `commands.run` 混用这一假设；
具体可见 [CubeSandbox 环境变量说明](https://cubesandbox.com/guide/environment-variables)。
如果以文件方式配置，将仅含后端地址的 `.env` 放到沙箱内 `tushare.py` 同目录即可。
地址必须从沙箱可达，`127.0.0.1` 指沙箱自身；当前 Compose 后端端口发布到宿主机所有接口。
跨机器访问时使用后端宿主机内网地址，并核对沙箱路由与端口访问规则。

后端上游则通过根 `.env` 中的 `TUSHARE_BASE_URL` 配置，默认官方地址
`https://api.tushare.pro`。仅填写可信地址，后端会向该地址发送 `TUSHARE_TOKEN`。

## 后端协议与边界

`POST /api/tushare/{name}` 请求体为 `{"params": {...}, "fields": "字段1,字段2"}`。
后端再次检查白名单、必填条件、未知参数、类型、日期、分页和输出字段。
`fields` 是 HTTP 协议顶层字段，不能放进 `params`；空字符串采用官方默认字段。
仅文档列明的接口接受 `limit` / `offset`，不会为所有接口添加分页。
普通财务接口遵守各自文档的必填条件；VIP 查询需提供股票或报告期。

结果包含 `status`、`data`、`source`、`query`、`fetched_at`（UTC）和 `limits`。
`data.fields` / `data.items` 保留原始字段顺序、数值与单位，不转换成金额或复权值。
状态包括 `success`、`empty`、`permission_denied`、`rate_limited`、`timeout`、
`service_error`、`incomplete`，以及本地的 `invalid_request`、`not_configured`、
`budget_exceeded`、`busy`。业务结果使用 HTTP 200 信封，调用方必须检查 `status`；
axi 的外层 `success` 仅表示工具函数执行完成。

上游地址由后端环境配置，单次总耗时 60 秒，解压后响应最多 20 MiB；单进程最多并发 4 次、
每分钟最多 30 次真实请求，不自动重试、不自动翻页。CLI 的 HTTP 超时设为 65 秒，
比后端 60 秒处理上限多留 5 秒返回余量。
达到文档行数上限、请求 `limit` 或上游报告 `has_more` 时返回 `incomplete`；未公布上限或未达到上限
都不能证明全量，`limits.completeness` 会说明未知或可能截断。
开放调用只表示允许向官方发请求，不承诺账户积分、接口权限或上游可用性。

当前入口仅供受控开发网络，后端端口应限制为允许的沙箱来源访问。不要通过反向代理公开该入口，
不要以多 worker 部署绕过进程内预算；多用户认证和分布式预算尚未实现。
前端只挂载自己的源码和浏览器测试目录，根 `.env` 的数据源配置仅向后端注入。
上游错误原文不回显，避免携带凭据；权限、限流分类依赖上游错误码和中文提示，
未识别的错误统一为 `service_error`。

## 维护与验证

修改契约时核对对应官方页面，保留来源日期及修正原因，勿从表头猜测输入输出。
典型修正包括 `end_date: None`、`offset: intint`、输出表误标“必选”、条件必填和
字段选择参数归属。单位只使用官方字段描述；文档未注明时不作推断。

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

测试使用明确的 HTTP 替身及虚构凭据，覆盖全部契约与注册，以及恶意参数、日期、
权限、限流、超时、空数据、大小和行数截断。真实验收应单独运行上述 CLI / PTC，
小范围抽样股票基础、行情、财务、指数、基金、宏观及 VIP，记录实际状态与行数；
不要把契约结构测试当作全部接口真实可用的证明。

## 专属模板与控制端

构建上下文为仓库根目录；`sandbox/Dockerfile.dockerignore` 仅放行 CLI Python、
契约 JSON 与锁文件。直接使用官方基础镜像 `ghcr.io/tencentcloud/cubesandbox-base:2026.16`，
保留 envd 2026.16、tini 和原始 ENTRYPOINT/CMD；新模板装入本仓库工具，不使用旧模板 ID。
Dockerfile 的 FROM 使用明确版本标签，不追加 digest。

官方 base 不含 Python，由 uv 0.13.7 下载 Python 3.12.15 到 `/opt/kli-quant/python`，
CLI 依赖安装到 `/opt/kli-quant/venv`。
axi 的绝对路径为 `/opt/kli-quant/venv/bin/axi`，PTC 使用同目录的 `python`。
CLI 包路径通过该环境的 `.pth` 文件注册，无需注入服务端禁止的 `PYTHONPATH`，
也不依赖 envd 继承镜像环境或命令的工作目录。
`kli-axi` 提供框架及 `axi` 命令；本仓库的 `sandbox.cli.tushare` 是另外复制的工具模块，
因此仍需要注册其包路径。Python 版本和 187 个工具的数量在构建后验收。
基础镜像没有 Jupyter 服务，本模板不提供 `run_code`；Python PTC 经 `commands.run` 执行。
参考 [官方镜像启动契约](https://cubesandbox.com/guide/tutorials/bring-your-own-image.html)
和 [官方 Python SDK](https://cubesandbox.com/guide/tutorials/sdk/python)。

0.1.1 使用旧派生镜像，0.1.2 起直接使用官方 base。以下为 0.1.2 的发布命令；
后续修改须递增版本，不覆盖已发布标签。

```bash
# 从仓库根目录构建；选择尚未发布的标签，禁止覆盖共享模板或已发布镜像。
docker build --platform linux/amd64 -f sandbox/Dockerfile \
  -t iruiiii/omniagent-sandbox:kli-quant-0.1.2 .
# 目标开发资源获准且本地验收通过后才推送。
docker push --platform linux/amd64 iruiiii/omniagent-sandbox:kli-quant-0.1.2
```

当前集群为 x86_64，CubeMaster/cubemastercli v0.7.3，实例类型 cubebox。
计算节点须先通过安装包自带的虚拟化预检，确认 `/dev/kvm` 可用；管理页面正常不代表
沙箱可运行。预检的 `CUBE_DATA_PATH` 应指向实际 XFS 数据盘路径。
在已有集群管理机执行以下命令；保留 envd 探针，不传入后端地址或管理凭据：

```bash
cubemastercli tpl create-from-image \
  --image iruiiii/omniagent-sandbox:kli-quant-0.1.2 \
  --alias kli-quant-0-1-2 --instance-type cubebox \
  --cpu 2000 --memory 2048 --writable-layer-size 1G \
  --expose-port 49983 --probe 49983 --probe-path /health
cubemastercli tpl list -o wide
```

若管理机访问镜像仓库失败，仅通过 `docker save` / `docker load` 载入镜像并不足以解决。
当前 v0.7.3 的[原生导出器默认启用](https://github.com/TencentCloud/CubeSandbox/blob/4411c96ba8658a959de34693f54f4918db2a432f/CubeTemplateCenter/pkg/image/native.go)，
会直接访问镜像仓库，绕过 Docker 本地缓存。可将上述 `--image` 改为经确认的代理镜像地址，
例如 `docker.agentfixit.ai/iruiiii/omniagent-sandbox:kli-quant-0.1.2`；构建前核对代理返回的
镜像 digest 与发布版本一致。显式使用代理地址无需更改导出模式或重启服务。
不能把载入镜像或创建任务成功视为模板 READY。

等待模板 READY 后，将新 ID 写入 `/workspace/deploy/kli-quant/.env` 的
`CUBESANDBOX_TEMPLATE_ID`。控制端所需配置如下（值留空表示必须自行填写）：

```dotenv
CUBESANDBOX_API_URL=
CUBESANDBOX_DOMAIN=
CUBESANDBOX_TEMPLATE_ID=
E2B_API_KEY=
KLI_QUANT_BACKEND_URL=
# 控制端无法解析沙箱通配域名时，填写 CubeProxy 节点 IP。
CUBE_PROXY_NODE_IP=
```

此配置文件也可能含 Agent 凭据，不能复制进镜像；根 `.env.example` 只维护后端配置。
控制端 SDK 固定 `cubesandbox==0.7.3`，通过 uv 的独立 `sandbox` 依赖组安装：

```bash
uv sync --locked --group sandbox
uv run --locked --group sandbox python -m sandbox.create_sandbox
# 只在明确指向测试后端、其上游为 HTTP 替身时启用业务探针。
uv run --locked --group sandbox python -m sandbox.create_sandbox --check-tools
```

默认从上述集中配置加载，进程环境优先；`--env-file` 可指定测试专用配置。
入口校验必填项，只把 `KLI_QUANT_BACKEND_URL`、`AXI_CONFIG` 传给
`Sandbox.create(envs=...)`。默认验收健康接口和 187 个离线工具的注册、搜索、描述。
创建时同时通过 `network.allow_out` 放行后端 URL 的主机：IPv4 使用 `/32`，IPv6 使用
`/128`，域名保持原值；规则仅作用于该实例，不修改集群策略。地址改变后，新实例的放行目标同步改变。
`--check-tools` 另外执行 `daily` 的 CLI 与 PTC 请求，并检查业务信封状态；
此开关会请求所配置的后端，不能用于未获授权的真实 Tushare 调用。
成功或失败都会删除临时实例；实例 TTL 为 300 秒，清理失败会向控制端报错。

原始场景复验：准备两个独立测试后端 A/B，使用同一模板分别运行上述命令，
每次仅在控制端更改 `KLI_QUANT_BACKEND_URL`。核对 A/B 请求日志与模板 digest，
无需手动 export 到沙箱，也无需重建镜像。旧实例仍保留创建时的地址。

依赖更新先更新根 `uv.lock`，同步 `sandbox/requirements.in` 的直接依赖版本，
再从根锁文件导出约束并重生成带哈希的 CLI 锁文件：

```bash
uv export --locked --no-dev --no-emit-project --no-hashes \
  --output-file /tmp/kli-quant-sandbox-constraints.txt
uv pip compile sandbox/requirements.in --python-version 3.12 \
  --constraint /tmp/kli-quant-sandbox-constraints.txt --generate-hashes \
  --output-file sandbox/requirements.lock
rm /tmp/kli-quant-sandbox-constraints.txt
uv run pytest tests/test_sandbox.py tests/test_tushare.py
```

排查时先区分失败阶段：模板未 READY 查集群构建任务；命令不通查 envd 的
`:49983/health`、CubeSandbox 域名解析和代理；导入失败查镜像内 `.pth`、独立解释器与 `AXI_CONFIG` 路径；
后端不可达查沙箱路由与后端端口来源规则。非零退出码会导致验收失败，不能只看 SDK
调用是否抛异常。普通单测不访问真实集群或付费数据源。
