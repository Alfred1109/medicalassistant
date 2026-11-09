import type { ThunkDispatch } from '@reduxjs/toolkit';
import type { AnyAction } from 'redux';
import type { AuthState } from './slices/authSlice';
import type { UIState } from './slices/uiSlice';
import type { RehabState } from '../types/rehab';
import type { AgentState } from './slices/agentSlice';

/**
 * store 的完整 state 类型。
 *
 * 单独放在这里是为了打断循环依赖:各 slice 需要 RootState 来标注 thunk 的
 * getState 返回值,而 store/index.ts 又要 import 这些 slice。如果 RootState
 * 写成 ReturnType<typeof store.getState>,类型推导会绕回自身,TS 只能退化成
 * unknown,于是 slice 里 `const { auth } = getState()` 全部报错。
 */
export type RootState = {
  auth: AuthState;
  ui: UIState;
  rehab: RehabState;
  agents: AgentState;
};

/**
 * dispatch 需要能接收 thunk。redux 的 Dispatch<AnyAction> 不接受 thunk,
 * 组件里请用 useDispatch<AppDispatch>()。
 */
export type AppDispatch = ThunkDispatch<RootState, unknown, AnyAction>;

/**
 * createAsyncThunk 的 ThunkApiConfig。
 *
 * RTK 1.9 是通过 `state` 字段推导 getState 的返回类型的(不是 getState 本身),
 * 所以这里必须写 state,否则 slice 里的 getState() 会被推导成 unknown。
 */
export interface ThunkApiConfig {
  state: RootState;
  dispatch: AppDispatch;
  rejectValue: string;
}
