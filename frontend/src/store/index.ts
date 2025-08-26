import { configureStore } from '@reduxjs/toolkit';
import { combineReducers } from 'redux';
import type { Middleware } from 'redux';
import { 
  persistStore, 
  persistReducer, 
  FLUSH, 
  REHYDRATE, 
  PAUSE, 
  PERSIST, 
  PURGE, 
  REGISTER 
} from 'redux-persist';
import storage from 'redux-persist/lib/storage';
import { setupListeners } from '@reduxjs/toolkit/query';

// 导入reducers
import authReducer from './slices/authSlice';
import uiReducer from './slices/uiSlice';
import rehabReducer from './slices/rehabSlice';
import agentsReducer from './slices/agentSlice';

// 导入RTK查询API
import { api } from './api';

// Redux持久化配置
const persistConfig = {
  key: 'root',
  version: 1,
  storage,
  // 白名单 - 只持久化这些reducer
  whitelist: ['auth'],
  // 黑名单 - 不持久化这些reducer
  blacklist: ['ui'],
};

// 组合所有reducer
const rootReducer = combineReducers({
  auth: authReducer,
  ui: uiReducer,
  rehab: rehabReducer,
  agents: agentsReducer,
  [api.reducerPath]: api.reducer,
});

// 创建持久化reducer
const persistedReducer = persistReducer(persistConfig, rootReducer);

// 自定义中间件，用于开发环境日志
const logger: Middleware = (store: any) => (next: any) => (action: any) => {
  if (process.env.NODE_ENV !== 'production') {
    console.group(`Action: ${action.type}`);
    console.info('dispatched', action);
    const result = next(action);
    console.log('next state', store.getState());
    console.groupEnd();
    return result;
  }
  return next(action);
};

// 创建store
export const store = configureStore({
  reducer: persistedReducer,
  middleware: (getDefaultMiddleware: any) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: [FLUSH, REHYDRATE, PAUSE, PERSIST, PURGE, REGISTER],
      },
    }).concat(process.env.NODE_ENV !== 'production' ? [logger, api.middleware] : [api.middleware]),
  devTools: process.env.NODE_ENV !== 'production',
});

// 创建持久化store
export const persistor = persistStore(store);

// 启用RTK Query的监听器，支持自动重新获取等功能
setupListeners(store.dispatch);

// 导出类型
export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store; 