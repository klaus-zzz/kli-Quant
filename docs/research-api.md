# 研究接口

管理研究任务、固定输入、证据关系和结果版本。研究步骤由执行器负责，后端负责
状态、归属、预算和结果校验。当前身份认证与真实执行器尚未接入，提交返回 503。

## HTTP 接口

所有研究操作要求服务端认证身份。

| 方法与路径 | 说明 |
| --- | --- |
| POST `/api/research/runs` | 创建研究。必填 `question`，`event`、`url` 至少一个，可选 `previous_run_id`；请求头必填 `Idempotency-Key`。首次返回 202，重复请求返回 200 和原 run_id |
| GET `/api/research/runs/{run_id}` | 查询状态、阶段、截止时间、预算及使用量 |
| POST `/api/research/runs/{run_id}/cancel` | 请求取消，无请求体，可重复调用 |
| GET `/api/research/runs/{run_id}/result` | 获取固定结果与证据引用；尚无有效结果返回 409 |

同一用户用同一幂等键提交不同内容返回 409；不存在或无权访问返回 404，
无效输入返回 422，服务未就绪返回 503。归属、截止时间和预算由服务端确定。

状态流转为 `queued → running → completed / failed`。排队任务可直接取消；
运行中的任务先进入 `cancelling`，确认停止后变为 `cancelled`。终态不可改写。
执行完成不代表发现机会：条件性观察、证据不足、没有机会都是正常业务结论。

## 数据与结果

- PostgreSQL 保存执行、证据和结果索引，使用参数化 SQL 与版本化迁移。
- SeaweedFS S3 保存固定原文、数据快照、代码和产物；引用包含 `evidence_id`、
  `run_id`、`sha256`，读取时校验归属和内容，旧对象与结果不覆盖。
- 每跳判断记录前驱、问题、支持与反对证据、缺口及失效条件。新证据创建新任务，
  通过 `previous_run_id` 关联旧版本，不在原结果上修改。

研究内的数据采集须经 `collect_dataset` 保存请求和完整快照；普通 Tushare 工具
调用不会自动归档为研究证据。重放读取固定输入，不重新抓取最新数据。
发布时间、披露时间、行情日期和抓取时间分别记录；未知或不完整数据明确标注。
没有可信历史可得性依据的数据可用于探索，不能作为无未来信息的正式回测输入。

发布前校验来源、引用、多跳关系、时点和产物；回测另查单位、复权、交易日及费用
口径。代码、输入、输出和退出码须来自可信执行记录；失败时保留草稿及错误，不发布正式结果。

## 原文抓取

使用 [Scrapling](https://github.com/D4Vinci/Scrapling) 的静态 HTTP 抓取和 HTML
解析，底层 HTTP/TLS 由 [curl_cffi](https://curl-cffi.readthedocs.io/en/latest/api.html)
处理，版本见 [pyproject.toml](../pyproject.toml)。保存原始字节、文本段落、URL、
抓取时间和可确认的发布时间；引用定位到固定段落。

支持标准 80/443 端口的 HTTP(S)，不预查 DNS 或区分公网、内网 IP。
逐跳检查协议、URL 凭据和端口，保留 TLS 校验，不继承环境代理。
最多 5 次请求，共享 20 秒请求预算，单个响应上限 4 MiB。
仅支持 HTML/纯文本；不启动浏览器，暂不支持动态页面和 PDF。

## 接入与配置

认证层向 ASGI scope 注入 `research_owner`，执行器通过
`app.state.research_service` 接线；身份和执行成功不能由模型或普通请求头自报。
执行器须遵守任务预算、截止时间和取消状态，并提交可信的执行记录。

后端配置项：`RESEARCH_DATABASE_URL`、`RESEARCH_S3_ENDPOINT`、`RESEARCH_S3_BUCKET`、
`RESEARCH_S3_ACCESS_KEY`、`RESEARCH_S3_SECRET_KEY`，模板见 [.env.example](../.env.example)。
数据库迁移需显式执行，S3 bucket 需预先创建。

```bash
uv sync --locked
uv run python -m backend.research.migrate up
uv run pytest
```

迁移 `down` 会删除研究索引但保留 S3 对象，回退前须停用研究入口并备份。
普通测试不依赖外部服务；集成测试通过 `RESEARCH_TEST_DATABASE_URL` 和
`RESEARCH_TEST_S3_*` 指定专用资源。测试会清空研究表，库名须以 `kli_quant_test_`
开头，bucket 名须以 `kli-quant-test-` 开头，禁止使用生产数据。
