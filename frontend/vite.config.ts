import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 代理目标只用于 Vite 进程，不向浏览器注入后端配置。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": process.env.BACKEND_PROXY_TARGET ?? "http://127.0.0.1:18100",
    },
  },
});
