import { defineConfig } from "@playwright/test";

// 使用 CommonJS 配置兼容根 tests/ 的依赖映射；只测试已启动的开发服务。
export default defineConfig({
  testDir: "../tests/e2e",
  tsconfig: "./tsconfig.json",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:15173",
    browserName: "chromium",
  },
});
