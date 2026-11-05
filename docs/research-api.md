# 研究执行与证据契约

研究接口保存业务状态、固定输入和可追溯结论。OmniAgent 决定研究步骤；
本服务不实现 Agent 循环。当前没有真实执行器和可信身份接线，提交返回 503，
不会产生无人处理的任务。健康接口仍只检查进程。

## HTTP 契约

所有研究操作要求可信服务端身份。禁止从请求正文、run_id 或任意来源 Header
推断身份。集成方须在认证后向 ASGI scope 注入 `research_owner`，并注入
`app.state.research_service`；测试通过依赖覆盖注入，不是上线认证方案。

| 方法和路径 | 请求与响应 |
| --- | --- |
| POST `/api/research/runs` | `event` 或 `url` 至少一个，必填 `question`；可选 `previous_run_id`；必填 `Idempotency-Key`。首次返回 202，重复返回 200 和相同 run_id |
| GET `/api/research/runs/{run_id}` | 状态、阶段、截止点、预算与使用量、失败分类 |
| POST `/api/research/runs/{run_id}/cancel` | 无请求体；重复调用安全；返回当前状态 |
| GET `/api/research/runs/{run_id}/result` | 完成后返回固定结果和对象引用；没有有效结果时返回 409 和当前状态 |

调用方不能设置 owner、cutoff、预算、对象存储键或执行器状态。
同一 owner 和幂等键绑定规范化请求；不同内容复用同一个键返回 409。
越权和不存在统一返回 404；无效请求返回 422，服务未配置返回 503。
错误不会回显凭据或底层服务异常。

## 状态与完成语义

`queued → running → completed / failed`；排队取消可直接到 `cancelled`，
运行取消先到 `cancelling`，执行器确认停止后到 `cancelled`。
取消和完成通过数据库行锁串行判断；已进入终态不可改写。
执行器提交必须快速返回，不能在 HTTP 请求内执行研究。
提交派发失败记为 failed；进程崩溃后的超时执行由可信集成方调用超时收尾，
不会自动重新运行模型或声称已复现。取消超时保留 cancelling，直到确认停止。

执行完成与业务结论分开：`conditional_observation`、`insufficient_evidence`、
`no_opportunity` 都是正常结论。结构或来源校验失败保留草稿和错误，执行记为
failed / validation_failed，不发布正式结果。

## 固定证据与多跳关系

PostgreSQL 保存执行、证据、判断和结果索引；SeaweedFS S3 保存不可覆盖的对象。
对象引用含 evidence_id、run_id、sha256；只有经过归属检查才能读对象。
原文使用受控 HTTP 下载和 Scrapling 解析，归档原始字节、文本段落、规范化 URL、
抓取时间及页面声明的发布时间。引用采用固定段落编号；转载独立性默认 unknown。
仅支持 HTML/纯文本，动态页面、PDF、抓取失败和未知时间明确保留限制。
拒绝私网、回环、链路本地地址，DNS 所有结果须为公网；连接固定到已检查的 IP，
TLS 仍验证原域名。每次重定向重新检查，不继承宿主代理。
代理 DNS 若将公网域名映射为 `198.18.*` 或私网 IPv6，抓取会返回 unsafe_address；
开发/部署网络须提供真实公网解析。可在隔离验收容器中为已核实的目标设置临时
hosts 映射，但不能将这种验证配置扩展为允许任意私网访问。

Tushare 快照保存接口、参数、fields、完整响应和抓取时间；沿用工具白名单和
全局请求限制，额外使用数据库控制每个研究的调用预算。
选择输出字段时自动补齐契约中的必要日期字段，并分别保留 requested_fields 和
实际 fields；响应仍缺少日期字段时不能发布为正式证据。默认每次执行最多 30 次
资料/数据采集、300 秒；适配器必须同时遵守 deadline，不把取消请求视作已经停止。
数据不完整不代表全量；历史记录今天可查询不证明当时可获得。
未具备可信时点依据的快照允许探索和描述性研究，不能发布为无未来信息的回测输入。
财报期、披露日期、行情日期和抓取时间分别记录，不相互代替。

判断以结构化节点提交，包含前驱节点及引出本跳的发现、问题、实体、时间范围、
判断、支持引用、反证、缺口、条件和失效条件。引用定位必须存在于固定证据。
不限定跳数，不固化行业到个股的路径；检查关系不等于证明因果判断正确。
新证据复核创建新 run，关联同一 owner 的旧完成版本；必须说明受影响判断和变化原因。
历史证据只允许引用明确关联的前一版本；旧结果永久保持原样。

## 受信执行器接口

后端 Python 服务提供提交、认领、进度、证据采集、产物归档、发布、失败及取消确认。
这些是服务端集成函数，不是模型可任意调用的管理 HTTP API。
适配器负责把 run_id 绑定到可信任务、身份、截止点和沙箱执行记录。
代码、输入和输出的哈希及退出码须由受信适配器记录，不能由模型自报后直接批准。
研究内的数据调用必须经 `collect_dataset` 归档；已有 `/api/tushare/{name}` 是普通
工具入口，不会自动绑定研究。沙箱接线时必须阻止绕过研究入口的网络访问，不能把
普通工具的未归档返回值当作研究证据。完成/取消状态可用 get 查询核对，不依赖推送。
本次不实现 Gateway 通知、CubeSandbox 身份代理或模型执行。

## 校验与重放

发布校验来源归属、内容哈希、引用定位、截止点、多跳关系和结论必填项。
观察信号/回测另外校验单位、复权、交易日、收益/费用口径及可信执行记录。
对象上传并验证后才发布数据库结果；未引用对象可按任务前缀核查后清理。
重放读取已归档输入；不重新抓取最新数据。重新执行计算由执行器接线负责。

## 配置、迁移及验证

配置仅在后端：`RESEARCH_DATABASE_URL`、`RESEARCH_S3_ENDPOINT`、
`RESEARCH_S3_BUCKET`、`RESEARCH_S3_ACCESS_KEY`、`RESEARCH_S3_SECRET_KEY`。
业务表使用参数化 SQL；迁移由 `python -m backend.research.migrate up` 显式执行。
回退使用 `down`，会删除研究索引，必须先停用研究入口并备份；不会删除 S3 对象。
不在请求中自动建表，也不自动创建业务 bucket。

普通 `pytest` 不连接外部服务；集成测试须显式指定专用测试库和 bucket。
真实模型、沙箱及主动通知未联调，不能用受控执行器测试代替。

```bash
# 后端环境已注入专用开发库及 S3 配置时执行；不会从其他项目寻找凭据。
uv run python -m backend.research.migrate up
uv run pytest
# 使用独立测试库和测试 bucket 的连接配置运行集成测试。
# RESEARCH_TEST_DATABASE_URL 及 RESEARCH_TEST_S3_* 应通过本地环境注入。
uv run pytest tests/test_research_service.py
```

集成测试会清空指定测试库中的研究表，库名必须以 `kli_quant_test_` 开头。
真实 S3 测试使用 `RESEARCH_TEST_S3_ENDPOINT`、`RESEARCH_TEST_S3_BUCKET`、
`RESEARCH_TEST_S3_ACCESS_KEY`、`RESEARCH_TEST_S3_SECRET_KEY`，bucket 名必须以
`kli-quant-test-` 开头。CI 使用独立 PostgreSQL 容器；S3 真实验证须单独配置。
测试结束只清理本次测试库、角色、bucket、开发容器和依赖卷，不删除共享服务数据卷。

Scrapling 使用固定版本 0.5.1 的纯解析器，BSD-3-Clause 许可，
依据 [官方安装与解析说明](https://github.com/D4Vinci/Scrapling#installation)。
具体使用 `scrapling.parser.Selector` 的 XPath 查询和文本提取方法，提取 HTML
段落、标题及 `article:published_time` 元信息；关闭自适应定位。HTTP 下载由本项目
负责公网地址校验、重定向复查、超时和大小限制，不调用 Scrapling 的网络抓取接口。
不安装其浏览器、MCP 或代理轮换组件；站点拒绝访问时记录失败，不尝试绕过认证。

### Scrapling 抓取替换验收

替换下载层必须同时满足：固定到已检查的 IP 并保持原域名 TLS 校验、逐跳检查
重定向、不继承环境代理、限制下载大小及耗时、拒绝响应截断。不能只检查 URL
后再让抓取库自行解析，也不能通过关闭证书验证来连接 IP。

Scrapling 0.5.1 + curl_cffi 0.17.0 的实际验证结果：

| 能力 | 结果 |
| --- | --- |
| HTTP 下载与解析 | 可用 |
| 关闭自动重定向、拒绝私网重定向 | 可用；关闭后仍需业务层逐跳检查 |
| 关闭重试并限制单次请求总耗时 | 可用，持续滴流仍会超时；多跳仍需共享剩余预算 |
| 读取回调限制响应大小、拒绝响应截断 | 可用 |
| 禁用环境代理 | `proxies={"all": ""}` 可用，不能只依赖默认设置 |
| 固定已检查的 IP | 不满足：`Fetcher.get` 和 `FetcherSession` 均拒绝 `curl_options` |

底层 curl_cffi 的公开 `Session(curl_options=..., trust_env=False)` 可以完成固定
IP 与代理隔离，但 Scrapling 没有暴露该配置入口。本次保留原下载层，没有引入
访问 `_curl_session` 等私有属性的版本绑定适配，也没有放松地址检查。
固定 IP 条件未通过，因此没有进一步声称 HTTPS 原域名校验已完成替换验收。

可选测试 `tests/test_scrapling_fetcher.py` 使用本地 HTTP 源站验证真实网络行为，
不请求生产接口，也不启动浏览器。复现命令：

```bash
uv run --with 'scrapling[fetchers]==0.5.1' --with 'curl-cffi==0.17.0' \
  pytest -q -rx tests/test_scrapling_fetcher.py
```

基础依赖不含 `fetchers` 扩展，普通测试会跳过此模块。仅验证环境临时安装
扩展及其浏览器相关 Python 包，不下载浏览器二进制，也不加入生产依赖。
标为 `xfail` 的用例表示替换条件尚未满足；上游接口改变后若用例通过，严格模式
会要求重新审查这一限制，不能把预期失败当作功能已经验收。

接口参考：[Scrapling 静态抓取](https://scrapling.readthedocs.io/en/latest/fetching/static.html)
及其底层 [curl_cffi 会话配置](https://curl-cffi.readthedocs.io/en/latest/api.html)。
版本行为以指定版本的实际测试为准，在线文档可能随上游更新。
