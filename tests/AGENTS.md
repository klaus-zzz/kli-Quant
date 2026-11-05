# 测试规则

- 后端与浏览器测试放在本目录；独立抓取器的专属测试随服务放在 `fetcher/tests/`。
- `test_health.py` 验证后端健康响应和接口边界；`e2e/` 验证浏览器成功、失败和异常响应状态。
- 普通测试不得请求生产数据、付费接口或使用真实凭据；健康检查测试无需外部服务。
- 研究集成测试仅在显式设置 `RESEARCH_TEST_DATABASE_URL` 时运行，库名须以 `kli_quant_test_` 开头；真实归档验证只用 `kli-quant-test-` 前缀的专用 bucket。共享服务的凭据由后端环境注入，不写入测试夹具。
- 后端执行 `uv run pytest`；前后端启动后，在 `frontend/` 执行 `npm run test:e2e`。
- E2E 默认访问 `http://127.0.0.1:15173`；覆盖端口时通过 `PLAYWRIGHT_BASE_URL` 指定地址。
- 容器验收使用唯一的根 Compose 和独立项目名；核对源码挂载、健康请求及热更新，完成后仅清理本次容器和依赖卷。
