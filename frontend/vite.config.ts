import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd());
  
  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5501, // 前端端口
      open: false,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: 'http://localhost:5502',
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