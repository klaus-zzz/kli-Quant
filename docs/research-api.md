# 研究接口

管理研究任务、固定输入、证据关系和结果版本。研究步骤由 OmniAgent 原生后台子 Agent 负责，后端负责
状态、归属、预算和结果校验。启用 [Agent 接入](agent.md) 后提供真实执行器；
未启用时提交仍返回 503。

## HTTP 接口

所有研究操作要求服务端认证身份。

| 方法与路径 | 说明 |
| --- | --- |
| POST `/api/research/runs` | 创建研究。必填 `question`，`event`、`url` 至少一个，可选 `previous_run_id`；请求头必填 `Idempotency-Key`。首次返回 202，重复请求返回 200 和原 run_id；queued 时同时返回原生 agent 启动参数 |
| GET `/api/research/runs/{run_id}` | 查询状态、阶段、截止时间、预算及使用量 |
| POST `/api/research/runs/{run_id}/cancel` | 请求取消，无请求体，可重复调用 |
| GET `/api/research/runs/{run_id}/result` | 获取固定结果与证据引用；尚无有效结果返回 409 |
| GET `/api/research/runs/{run_id}/evidence` | 查询该执行的固定归档目录；返回证据 ID、类型、摘要和元数据，不含对象存储键 |
| GET `/api/research/runs/{run_id}/evidence/{evidence_id}` | 校验归属和摘要后读取固定资料；可读当前执行或明确关联的前序执行，移除原始 HTML 字节 |

同一用户用同一幂等键提交不同内容返回 409；不存在或无权访问返回 404，
无效输入返回 422，服务未就绪返回 503。归属、截止时间和预算由服务端确定。
状态视图另含 `question` 和 `previous_run_id`，供浏览器展示研究问题和固定版本关系。
浏览器归档读取使用聊天认证与 `X-Session-ID`，不要求沙箱执行身份，也不受研究终态限制。
运行、失败或取消后的资料仍可核对，但归档存在不代表报告已通过校验。

提交只登记研究；主 Agent 随后调用返回的 `agent` 参数启动后台任务。
状态流转为 `queued → running → completed / failed`，running 来自受信原生任务事件。
queued 研究可直接取消；
运行中的任务先进入 `cancelling`，确认停止后变为 `cancelled`。终态不可改写。
执行完成不代表发现机会：条件性观察、证据不足、没有机会都是正常业务结论。

## 数据与结果

- PostgreSQL 保存执行、证据和结果索引，使用参数化 SQL 与版本化迁移。
- SeaweedFS S3 保存固定原文、数据快照、代码和产物；引用包含 `evidence_id`、
  `run_id`、`sha256`，读取时校验归属和内容，旧对象与结果不覆盖。
- 每跳判断记录前驱、问题、支持与反对证据、缺口及失效条件。新证据创建新任务，
  通过 `previous_run_id` 关联旧版本，不在原结果上修改。

启用 Agent 时，Tushare 入口使用宿主代理绑定的会话身份，额外要求 `X-Research-Run`。
CLI 工具的 run_id 参数逐次传入；后端校验研究归属，再经过 collect_dataset
保存请求和完整快照、扣除预算。省略研究标识或跨会话调用均被拒绝。
未启用 Agent 的原开发入口不会自动归档。重放读取固定输入，不重新抓取最新数据。
发布时间、披露时间、行情日期和抓取时间分别记录；未知或不完整数据明确标注。
没有可信历史可得性依据的数据可用于探索，不能作为无未来信息的正式回测输入。

发布前校验来源、引用、多跳关系、时点和产物；回测另查单位、复权、交易日及费用
口径。代码、输入、输出和退出码须来自可信执行记录；失败时保留草稿及错误，不发布正式结果。

## 原文抓取

原文由独立的 [fetcher 服务](../fetcher/README.md) 抓取，后端负责保存证据。
支持公网 HTML/纯文本，保留原始字节、摘要、固定段落及时间信息；不支持动态页面和 PDF。
抓取依赖、网络隔离策略及专属测试集中在 `fetcher/`。

## 接入与配置

认证层向 ASGI scope 注入归属，执行器通过 `app.state.research_service` 接线。
Agent 开发入口采用独立聊天 Token + 服务端会话归属；沙箱通过宿主网络代理注入
随机会话身份；研究通过 X-Research-Run 选择并核对归属，身份和执行成功不能由模型自报。
执行器须遵守任务预算、截止时间和取消状态，并提交可信的执行记录。

后端配置项：`RESEARCH_DATABASE_URL`、`RESEARCH_S3_ENDPOINT`、`RESEARCH_S3_BUCKET`、
`RESEARCH_S3_ACCESS_KEY`、`RESEARCH_S3_SECRET_KEY`，模板见 [.env.example](../.env.example)。
数据库迁移需显式执行，S3 bucket 需预先创建。
新增 003_native_tasks 保存原生任务快照，不是任务队列；升级前停止旧执行器并回收旧沙箱。
003 会收尾旧未完成研究，已发布结果与证据不变。

`RESEARCH_FETCHER_URL` 是可信抓取服务的完整接口地址，例如
`http://my-fetcher:18101/fetch`；服务名、端口或路径变更时修改此项即可。
根 Compose 提供开发默认值；独立运行后端需显式设置，缺少配置或服务故障均不回退直连。

```bash
uv sync --locked
uv run python -m backend.research.migrate up
uv run pytest
```

迁移 `down` 会删除研究索引但保留 S3 对象，回退前须停用研究入口并备份。
普通测试不依赖外部服务；集成测试通过 `RESEARCH_TEST_DATABASE_URL` 和
`RESEARCH_TEST_S3_*` 指定专用资源。测试会清空研究表，库名须以 `kli_quant_test_`
开头，bucket 名须以 `kli-quant-test-` 开头，禁止使用生产数据。
