import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 开发请求经同源代理进入后端，浏览器不接触服务凭据。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        // 保留浏览器 Host，与后端 Origin 校验一致，避免同源提交被误拦截。
        changeOrigin: false,
      },
    },
  },
});
