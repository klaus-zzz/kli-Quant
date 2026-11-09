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
