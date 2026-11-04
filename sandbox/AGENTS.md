# 沙箱规则

- 本文件覆盖 `cli/` 及以后明确授权创建的 `Dockerfile`。
- 初始化阶段只维护目录说明，不创建 CLI 实现、镜像定义、构建脚本或沙箱模板。
- 后续沙箱使用已有内网 CubeSandbox；CLI 分发依赖为 `kli-axi`，模块和命令为 `axi`。
- Python 兼容性基线及已核对的版本见根 README，不在此重复维护版本。
- 当前验证：`git diff --check -- sandbox`，确认目录中只有规则和说明。
