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
  version: 2,
  storage,
  // 白名单 - 只持久化这些reducer
  // Authentication is always revalidated; never persist bearer or cookie identity projections.
  whitelist: [],
  migrate: async (state: any) => {
    if (!state) return state;
    const { auth: _oldAuthentication, ...remaining } = state;
    return remaining;
  },
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

// 仅记录动作类型，避免在开发者控制台泄露患者数据、答卷或身份凭据。
const logger: Middleware = (storeApi) => (next) => (action) => {
  if (import.meta.env.DEV && typeof action?.type === 'string') {
    console.debug(`Action: ${action.type}`);
  }
  const result = next(action);
  if (action?.type === 'auth/logout') storeApi.dispatch(api.util.resetApiState());
  return result;
};

// 创建store
export const store = configureStore({
  reducer: persistedReducer,
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: [FLUSH, REHYDRATE, PAUSE, PERSIST, PURGE, REGISTER],
      },
    }).concat(logger, api.middleware),
  devTools: import.meta.env.DEV,
});

// 创建持久化store
export const persistor = persistStore(store);

// 启用RTK Query的监听器，支持自动重新获取等功能
setupListeners(store.dispatch);

// 导出类型(定义在 types.ts,避免 slices <-> store/index.ts 的循环依赖)
export type { RootState, AppDispatch } from './types';

export default store;
