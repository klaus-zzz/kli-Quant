# 前端工程

先读 [根目录规则](../AGENTS.md)，界面修改继续读 [src/AGENTS.md](src/AGENTS.md)。

- 使用 React、TypeScript、Vite 和 npm；同步 package.json 与 package-lock.json。
- 保持 TypeScript 严格检查，不以 any 或忽略错误绕过接口问题。
- 从本目录执行 `npm ci`、`npm run typecheck`、`npm run build`。
- 开发 API 通过 Vite 同源代理访问；正式静态托管需独立配置反向代理。
- 不把 Tushare、模型、S3 或沙箱凭据放进 VITE_ 变量或浏览器代码。
- 不为占位页增加路由、状态管理和 UI 依赖；有真实需求时再选择。
- 新增配置同步 README，默认保持本机开发访问范围。
- 构建通过不代表交互通过，界面变更应检查实际浏览器和窄屏表现。
