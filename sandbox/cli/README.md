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

CLI 的后端地址默认 `http://127.0.0.1:18100`，由启动环境中的
`KLI_QUANT_BACKEND_URL` 修改；模型参数不能改地址。分发时仅需要 `sandbox/cli/`
及其包路径和依赖，不复制根 `.env` 或后端配置。完整 CubeSandbox 网络接入尚未实现。

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

固定 HTTPS 上游，单次总耗时 20 秒，解压后响应最多 8 MiB；单进程最多并发 4 次、
每分钟最多 30 次真实请求，不自动重试、不自动翻页。CLI 等待后端最多 25 秒。
达到文档行数上限、请求 `limit` 或上游报告 `has_more` 时返回 `incomplete`；未公布上限或未达到上限
都不能证明全量，`limits.completeness` 会说明未知或可能截断。
开放调用只表示允许向官方发请求，不承诺账户积分、接口权限或上游可用性。

当前入口仅供受控开发网络，Compose 端口绑定本机。不要通过反向代理公开该入口，
不要以多 worker 部署绕过进程内预算；多用户认证和分布式预算尚未实现。
前端只挂载自己的源码和浏览器测试目录，根 `.env` 仅向后端注入 `TUSHARE_TOKEN`。
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
