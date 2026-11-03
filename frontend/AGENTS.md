# 前端规则

- 使用 React/TypeScript，入口为 `src/main.tsx`，两空格缩进。
- 当前页面仅显示“开发骨架”及真实后端健康状态，不展示模拟业务数据或研究结果。
- 浏览器请求使用同源 `/api/health`，由 Vite 开发代理转发；代理目标只能来自开发服务端配置。
- 不加载根目录 `.env`，不将后端环境整份传入前端，不使用 `VITE_*` 存放凭据。
- `package-lock.json` 由 npm 生成；运行 `npm ci`、`npm run check`、`npm run build`。
- 浏览器测试位于根 `tests/e2e/`；启动开发服务后执行 `npm run test:e2e`。
