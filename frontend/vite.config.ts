import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd());
  const backendTarget = process.env.VITE_BACKEND_TARGET || env.VITE_BACKEND_TARGET || 'http://localhost:5502';
  const backendUrl = new URL(backendTarget);
  if (!['http:', 'https:'].includes(backendUrl.protocol)) {
    throw new Error('VITE_BACKEND_TARGET must use http or https');
  }
  
  return {
    // 部署在 nginx 的路径前缀下,与 VITE_API_PREFIX 保持一致
    base: env.VITE_API_PREFIX ? `${env.VITE_API_PREFIX}/` : '/',
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5501, // 前端端口
      open: false,
      host: '127.0.0.1', // 只监听回环,对外统一由 nginx :80 转发
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
          secure: false,
          ws: true, // 支持WebSocket
          configure: (proxy, _options) => {
            proxy.on('error', (err, _req, _res) => {
              console.log('代理请求错误:', err);
            });
            proxy.on('proxyReq', (proxyReq, req, _res) => {
              console.log('代理请求:', req.method, req.url);
            });
            proxy.on('proxyRes', (proxyRes, req, _res) => {
              console.log('代理响应:', req.method, req.url, proxyRes.statusCode);
            });
          },
        },
      },
    },
    build: {
      sourcemap: true,
      outDir: 'dist',
      cssCodeSplit: true,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom'],
            mui: ['@mui/material', '@mui/icons-material'],
            router: ['react-router-dom'],
            redux: ['@reduxjs/toolkit', 'react-redux'],
          },
        },
      },
    },
  };
});
