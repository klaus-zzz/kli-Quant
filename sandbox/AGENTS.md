# 沙箱规则

- 本文件覆盖 CLI、模板 Dockerfile 和控制端创建/验收入口。
- 允许构建包含本仓库 axi CLI 的专属模板；保留基础镜像 envd 启动契约，不覆盖共享模板。
- Dockerfile 直接基于 CubeSandbox 官方 base，FROM 使用明确版本标签，不追加 digest。
- CLI 不读取数据源凭据，只向受控后端发送参数；仅使用 axi 的公开注册机制。
- 后续沙箱使用已有内网 CubeSandbox；CLI 分发依赖为 `kli-axi`，模块和命令为 `axi`。
- Python 兼容性基线及已核对的版本见根 README，不在此重复维护版本。
- 验证包括全部契约与工具注册、搜索、描述和 PTC 调用；真实请求与 HTTP 替身分别报告。
- 控制端配置集中在 `/workspace/deploy/kli-quant/.env`；仅将后端 URL 和 CLI 运行配置注入沙箱。
- 镜像不得包含 `.env`、数据源或管理凭据；使用根构建上下文和 Dockerfile 专属白名单。
- 模板构建、注册与真实沙箱验收分别报告；不把 commands.run 的 Python PTC 视作 run_code 验证。

## axi 工具接入

以下规则提炼自 [kli-axi 的 axi-creator](https://github.com/klaus-zzz/kli-axi/blob/754fb05e8081a78a8f05eea88fa4d7d9342b5b33/skills/axi-creator/SKILL.md)，仅用于本项目原生工具的开发与维护。
复杂输入、输出模型和注册机制按需查阅同版本的[原生工具参考](https://github.com/klaus-zzz/kli-axi/blob/754fb05e8081a78a8f05eea88fa4d7d9342b5b33/skills/axi-creator/references/native-tools.md)；新增 MCP 接入或导出需另有明确需求。

- 沿用 `cli/contracts/`、`cli/catalog.py` 与 `cli/tushare.py` 的契约和注册流程；通过公开 `axi.tool(name=...)` 注册，`tool("server/name")` 仅用于取得调用句柄，不作为装饰器。
- 在 `cli/axi.json` 的 `nativeTools` 中声明可导入模块与稳定组名；通过绝对路径 `AXI_CONFIG` 选用配置，当前目录的 `axi.json` 不会自动加载。CLI 与 PTC 必须使用同一配置及依赖环境。
- 用明确的参数名、类型和默认值表达输入；允许 `None` 不等于参数可省略。保留契约校验及后端再次校验，不以自然语言描述代替约束。
- 工具描述写清业务对象、能力和适用条件，包含搜索关键词；搜索索引使用工具名和工具级描述，参数说明用于 describe。
- 保持返回结构稳定且可序列化；`output_example` 仅展示形状，返回类型注解不会自动生成输出 schema，需要输出校验时才显式声明 `output_model`。
- 保留本项目业务信封：CLI 先检查 axi 外层 `status`，再检查内层业务 `status`；PTC 直接检查业务结果。`empty`、`incomplete`、权限或限流等状态不得当作完整查询成功，也不额外包装 axi 信封。
- import 阶段只加载契约和注册工具，网络请求留在执行阶段；数据源凭据始终由后端保管，不因通用接入示例而引入 CLI 凭据读取或请求参数覆盖身份。
- 修改后在同一环境验证 list/search、describe、CLI 和 PTC 的一致性，并覆盖典型无效参数与业务失败；HTTP 替身和真实只读调用分开报告，不为验证扩展真实调用权限。
