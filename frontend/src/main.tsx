import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Provider } from 'react-redux';
import { Alert, Box, CssBaseline } from '@mui/material';
import App from './App';
import { API_PREFIX } from './config/constants';
import { ThemeProvider } from '@mui/material/styles';
import store from './store';
import { PersistGate } from 'redux-persist/integration/react';
import { persistor } from './store';

// 导入自定义主题
import theme from './theme';

// 导入路由配置和工具函数
import {
  LoadingFallback,
  ErrorBoundary
} from './routes';


import './index.css';
// 导入highlight.js样式用于代码高亮
import 'highlight.js/styles/github.css';

console.log('🚀 开始启动医疗助手应用...');
console.log('🔧 调试: 检查是否到达了主文件入口');

// 等待DOM加载完成
const startApp = () => {
  console.log('📋 DOM已准备好，开始渲染应用...');

  const rootElement = document.getElementById('root');
  if (!rootElement) {
    console.error('❌ 未找到根元素');
    return;
  }

  console.log('✅ 找到root元素，开始渲染React应用');

  // 应用组件
  const ApplicationRoot = () => (
    <Provider store={store}>
      <PersistGate loading={<LoadingFallback />} persistor={persistor}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <BrowserRouter basename={API_PREFIX || undefined}>
            <ErrorBoundary fallback={
              <Box sx={{ p: 3 }}>
                <Alert severity="error">页面加载失败，请刷新页面后重试。</Alert>
              </Box>
            }>
              <App />
            </ErrorBoundary>
          </BrowserRouter>
        </ThemeProvider>
      </PersistGate>
    </Provider>
  );

  try {
    // 渲染应用
    const root = ReactDOM.createRoot(rootElement);
    root.render(
      <React.StrictMode>
        <ApplicationRoot />
      </React.StrictMode>
    );
    console.log('✅ 医疗助手应用渲染完成');
    console.log('🔧 调试: React应用已成功挂载到DOM');
  } catch (error) {
    console.error('❌ 应用渲染失败:', error);
  }
};

// 确保DOM加载完成后再启动应用
if (document.readyState === 'loading') {
  console.log('⏳ 等待DOM加载完成...');
  document.addEventListener('DOMContentLoaded', startApp);
} else {
  console.log('✅ DOM已经加载完成');
  startApp();
}
