import React from 'react';
import ReactDOM from 'react-dom/client';
import { Provider } from 'react-redux';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';

import App from './App';
import theme from './theme';
import store from './store';
import './index.css';

// 基本错误处理
const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('未找到根元素，无法渲染应用');
}

// 渲染应用
ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <Provider store={store}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <App />
      </ThemeProvider>
    </Provider>
  </React.StrictMode>
); 