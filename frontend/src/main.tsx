import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Provider } from 'react-redux';
import { CssBaseline } from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import store from './store';
import { PersistGate } from 'redux-persist/integration/react';
import { persistor } from './store';
// 导入自定义主题
import theme from './theme';

// 导入路由配置和工具函数
import { 
  AppRoutes,
  LoadingFallback, 
  ErrorBoundary
} from './routes';

// 导入备用页面组件，用于顶级错误边界
import { FallbackIndexPage } from './fallbackPages';

// 基本错误处理
const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('未找到根元素，无法渲染应用');
}

// 应用组件
const App = () => (
  <Provider store={store}>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <ErrorBoundary fallback={<FallbackIndexPage />}>
          <Routes>
            <Route path="/*" element={<AppRoutes />} />
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </ThemeProvider>
  </Provider>
);

// 渲染应用
ReactDOM.createRoot(rootElement!).render(
  <React.StrictMode>
    <Provider store={store}>
      <PersistGate loading={<LoadingFallback />} persistor={persistor}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <App />
        </ThemeProvider>
      </PersistGate>
    </Provider>
  </React.StrictMode>
); 