# 真实服务与业务联调

先读 [测试规则](../AGENTS.md)。

- 真实服务测试同时标记 integration 和 live，并保留环境变量显式启用条件；默认离线检查不运行。
- 测试数据库仅使用 FINA_TEST_DATABASE_URL 专用库，不回退到业务数据库。
- `test_live_services.py` 用 FINA_LIVE_SERVICES=1 启用，验证归档、行情和沙箱链路。
- `test_live_agent.py`、`test_live_chat.py` 用 FINA_LIVE_AGENT=1 启用，验证真实研究、持续对话、复核与取消。
- 在隔离开发容器中安装当前源码和底座，从 Fina-Agent 根目录读取后端配置；命令见 README。
- 真实调用仅使用已授权的开发或测试服务及额度；不使用生产数据。
- 在 finally 中清理本用例创建的沙箱、归档和数据库记录，按自身执行或会话编号限定范围。
- 结论可以是证据不足；成功依据是实际走过要求的业务链路，不要求产生投资机会。
