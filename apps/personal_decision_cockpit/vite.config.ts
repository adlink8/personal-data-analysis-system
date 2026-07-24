/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 驾驶舱由 rag-api（127.0.0.1:8000）以 /app/ 托管；dev 时把只读投影与
// 各 Authority 端点代理到后端，前端始终用相对路径同源调用。
const API_TARGET = 'http://127.0.0.1:8000';
const PROXIED_PREFIXES = [
  '/ui',
  '/intelligence',
  '/decision',
  '/proactive',
  '/agent',
  '/knowledge',
  '/health',
  '/stats',
];

export default defineConfig({
  base: '/app/',
  plugins: [react()],
  build: {
    // 清空 dist 再构建，避免多轮 hash 产物堆积（rag-api 静态托管该目录）
    emptyOutDir: true,
  },
  server: {
    // 显式绑 127.0.0.1，避免 localhost 在部分 Windows 环境只解析到 IPv6
    host: '127.0.0.1',
    port: 5173,
    proxy: Object.fromEntries(PROXIED_PREFIXES.map((prefix) => [prefix, API_TARGET])),
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: false,
  },
});
