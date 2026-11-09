# OmniAgent 开发接入

业务后端保存研究状态、归属、调用预算、固定证据和通知账本。
[OmniAgent v1](https://github.com/aivp/OmniAgent/tree/v1) 负责模型规划、工具选择和回复；
通过其 [Gateway](https://github.com/aivp/OmniAgent/blob/v1/docs/gateway-protocol.md)
及 [历史接口](https://github.com/aivp/OmniAgent/blob/v1/docs/history-protocol.md) 接入。
后端通过 [websockets](https://websockets.readthedocs.io/) 维护 Gateway 客户端连接。
不重写 Agent 框架，也不复制上游源码；上游许可未确认，独立镜像不随本项目分发。
前端仍为空应用，本阶段仅提供 HTTP/WebSocket 开发入口。

## 配置与启动

后端存储及 Tushare 配置保留在根 `.env`，Agent 配置只维护在
`/workspace/deploy/kli-quant/.env` 和 `.omniagent/`。模型、数据库与 Gateway
沿用 OmniAgent 的原生配置；不得将这些凭据写进提示词、沙箱或前端。

集中配置须包含：

| 配置 | 用途 |
| --- | --- |
| `OMNIAGENT_URL` | 容器内独立 Agent 地址，默认项目为 `http://kli-quant-skeleton-agent:8090` |
| `OMNIAGENT_GATEWAY_TOKEN` | 上游 Gateway 与历史接口认证 |
| `KLI_QUANT_CHAT_TOKEN` | 独立随机聊天 Token，至少 32 字符，绑定固定开发用户 |
| `KLI_QUANT_CONTROL_TOKEN` | `e2b_` 加 64 位随机十六进制字符，兼容上游 SDK 格式 |
| `CUBESANDBOX_API_URL`、`CUBESANDBOX_DOMAIN`、`E2B_API_KEY` | 真实集群管理入口，仅后端持有原始管理权限 |
| `CUBE_PROXY_NODE_IP` | 私有数据面代理的固定内网 IP，不能由请求参数覆盖 |
| `CUBESANDBOX_TEMPLATE_ID` | 本项目已验收的专属模板 |
| `KLI_QUANT_BACKEND_URL` | 沙箱可达的后端地址；HTTP 必须使用固定 IP |
| `LANGSMITH_TRACING`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT` | 通过 LangChain 原生追踪上传研究正文和代码 |

三个 Token 必须不同。不要将集中 `.env` 作为后端普通环境文件整体复制。
OpenAI 兼容基础地址填写 `/v1`，不附加 `/responses` 等具体接口。
需要 Responses 工具调用的模型通过 `llm_params.openai.use_responses_api: true` 启用；
例如 GPT-6.1 Sol 的要求见[官方函数调用说明](https://developers.openai.com/api/docs/guides/function-calling)。
Agent 的沙箱 API 地址和管理凭据由 Compose 覆盖为业务控制入口和独立控制 Token。
模型、PostgreSQL 和追踪变量继续按集中原生配置设置。
集群的公开根证书放在集中目录 `certs/cube-root-ca.crt`，先核对指纹和代理证书链。
Compose 只读挂载该公开证书，镜像原生入口更新信任库；不复制私钥、不关闭 TLS 校验。

根 `.env` 设置 `KLI_QUANT_AGENT_ENV_FILE=/agent-config/.env`，并填写独立开发研究库与
S3 bucket。默认关闭 Agent，不改变原健康检查和受控工具开发方式。
本地 Agent 镜像须先由管理员确认是 `1.0.0a84`，配置使用固定本地标签且禁止自动拉取；
不要把未知的 `latest` 直接冒充已核对版本。

```bash
# 根 .env 已填写；--env-file 第二份只补集中 Agent 配置的 Compose 插值。
docker compose --env-file .env --env-file /workspace/deploy/kli-quant/.env config --quiet
docker compose --env-file .env --env-file /workspace/deploy/kli-quant/.env run --rm backend \
  sh -c 'uv sync --locked --group sandbox && uv run --no-sync python -m backend.research.migrate up'
docker compose --env-file .env --env-file /workspace/deploy/kli-quant/.env \
  --profile agent up -d backend research-fetcher agent
```

Agent 的 `.omniagent/config.yaml` 使用 PostgreSQL 持久化、开启 Gateway，
`sandbox.executor=cubesandbox`，禁用 Agent 自建的 `background_task`、`agent`、
`schedule` 和 `artifacts` 工具。研究调度与产物归档只有业务后端一个入口。
`sandbox.env.AXI_CONFIG=/opt/kli-quant/sandbox/cli/axi.json`；
`sandbox.env_from_auth.KLI_QUANT_MESSAGE_ID='{message_id}'` 只传非秘密消息标识，
供 CLI 生成幂等键。研究方法提示词维护在集中 `.omniagent/prompts/AGENTS.md`。
不要在共享 Agent 库执行清表测试；集成测试使用临时专用库和 bucket。

## 对话协议

所有 HTTP 聊天请求使用 `Authorization: Bearer <聊天 Token>`。
服务端分配会话 ID，不接受客户端自报用户身份或上游 thread_id。

| 方法与路径 | 用途 |
| --- | --- |
| POST `/api/chat/sessions` | 创建会话，返回 `session_id` |
| POST `/api/chat/sessions/{id}/messages` | 提交 `{message_id: UUID, text: 字符串}`，同 ID 相同内容幂等 |
| GET `/api/chat/sessions/{id}` | 投递状态、正文、研究状态和连接情况 |
| GET `/api/chat/sessions/{id}/history` | 上游持久历史与本地投递状态，供断线核对 |
| WS `/api/chat/sessions/{id}/ws` | 接收快照、聊天 event 和 research_progress，也可发消息 |

WebSocket 使用 Authorization 请求头；浏览器不支持自定义头时，首帧发送
`{"authorization":"Bearer <聊天 Token>"}`，随后发送与 HTTP 相同的消息对象。
Token 不放 URL。首个快照含已有研究和投递；`resync_required` 表示客户端需要重新
读取快照和历史。断开浏览器只停止订阅，不取消研究。

直接查询或取消研究时，在聊天认证外增加 `X-Session-ID`，接口见[研究说明](research-api.md)。
启用后，一个会话内消息串行投递；研究另开执行线程，因此不阻塞原会话聊天。
研究完成通知携带固定 run_id、result_id、版本和哈希，唤醒原会话 Agent 读取并解释。

## 身份、执行与恢复边界

[CubeSandbox 安全代理](https://docs.cubesandbox.com/zh/guide/security-proxy)
为每个沙箱注入独立随机身份，只放行指定后端主机、端口和研究/Tushare 路径。
沙箱禁止公网出口，外部原文由隔离抓取器读取；CLI 不读取任何数据源凭据。
代理覆盖伪造的 Authorization；模型提供的 run_id 不是认证依据。
研究默认 300 秒、30 次采集或受信执行调用，失败也扣预算；截止后拒绝发布。

私有沙箱令牌只保存于业务数据库，`/api/agent/cube` 只允许控制 Token 查询或接回
本项目登记且有效的实例，补齐当前集群 connect 响应缺失的 `trafficAccessToken`。
不提供创建沙箱或任意代理；续期不能超过授权截止点。沙箱不能访问该控制入口。
当前 e2b SDK 不自动发送 CubeSandbox 的私有访问头，因此 Compose 将
`E2B_SANDBOX_URL` 指向 `/api/agent/cube/envd`。该入口校验实例 ID 和独立实例令牌，
只转发白名单内的 envd 文件/命令 RPC，目标固定为代理 IP 和该实例的 49983 端口，
再添加 `e2b-traffic-access-token`；不透传客户端 Host 或任意认证头。
请求上限 16 MiB、响应上限 32 MiB，并受实例截止时间限制。
控制面和数据面仅用于可信开发内网；不向浏览器提供这些 Token。

模板仍复用已验收镜像；每次创建后装载当前研究 CLI 及 axi 配置。
研究复用同一实例，控制端归档代码与固定输入，再执行摘要校验后的字节。
执行限制 45 秒、512 MiB、每个输出流 1 MiB，归档实际退出码和输出摘要。
模型自行在 bash 中运行的代码不自动获得可信执行记录；正式产物必须经 research/execute。
`research/context` 同时给出结果 Schema、固定输入/输出格式和引用规则。
Agent 发布入口先只读预检；无效草稿返回稳定 `errors` 与 `published=false`，
模型可在原预算、截止内修改后重试。正式发布仍完整校验、持锁，固定版本不可改写。

Gateway 没有 ACK 或游标重放：发送前持久落账；发送后失联标记 `uncertain`
（“回复待核对”），保留固定结果且不自动重发。下一条投递前核对上游 live 状态，
避免与旧轮次合并。历史缺少可信完成确认时不把未知状态伪装成已完成。
通知按研究版本唯一，重复调度不重复创建正式结论。

进程重启后，旧运行研究标记失败，取消中的研究先销毁沙箱再确认取消；不重新执行旧任务。
Gateway 离线时监管仍处理取消、超时和回收，恢复后再投递尚未发送的通知。
取消或失败时通过 Gateway `/stop` 终止研究线程生成；断线时先停止沙箱执行，
重连后补发幂等停止命令，不重新运行研究。
后端重启保留有效聊天沙箱，避免上游进程缓存变成失效句柄；研究沙箱按失败/取消收尾。
聊天授权期为一小时；过期投递明确失败并提示新建会话，已有结果仍可查询。
不替换上游仍缓存的沙箱句柄。崩溃创建窗口由有限 TTL 兜底。
需要重新研究时新建版本，已发布结果不改写。当前只支持单个调度实例和单用户开发入口，
不构成面向多用户或生产的认证系统。

开发结束先停止独立后端和 Agent，再显式回收该业务库登记的沙箱：

```bash
docker compose --env-file .env --env-file /workspace/deploy/kli-quant/.env stop backend agent
docker compose --env-file .env --env-file /workspace/deploy/kli-quant/.env run --rm --no-deps backend \
  uv run --no-sync python -m backend.agent.cleanup
docker compose --env-file .env --env-file /workspace/deploy/kli-quant/.env down -v
```

清理入口与调度器共用数据库租约，后端仍运行时拒绝清理。
执行破坏性回归或删测试库前，必须确认本库的 `agent_sandboxes` 已清空；
不能先清表再查资源归属。独立测试项目须给所有命令加同一个 `-p` 项目名。
