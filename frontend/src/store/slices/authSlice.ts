import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios, { AxiosResponse } from 'axios';
import type { ThunkApiConfig } from '../types';
import { API_BASE_URL } from '../../config/api';

// User interface
export interface User {
  id: string;
  email: string;
  name: string;
  role: 'patient' | 'doctor' | 'health_manager' | 'admin';
  createdAt: string;
  updatedAt: string;
  avatar?: string;
}

// Auth state interface
export interface AuthState {
  user: User | null;
  token: string | null;
  checking: boolean;
  sessionCheckRequestId: string | null;
  sessionCheckToken: string | null;
  loading: boolean;
  loginLoading: boolean;  // 专门用于登录操作的loading状态
  registerLoading: boolean;  // 专门用于注册操作的loading状态
  profileLoading: boolean;  // 专门用于个人资料操作的loading状态
  error: string | null;
}

// Initial state
const initialState: AuthState = {
  user: null,
  token: localStorage.getItem('token'),
  checking: true,
  sessionCheckRequestId: null,
  sessionCheckToken: null,
  loading: false,
  loginLoading: false,
  registerLoading: false,
  profileLoading: false,
  error: null,
};

interface LoginThunkArg {
  email: string;
  password: string;
}

interface LoginSuccessPayload {
  user: User;
  token: string;
}

// Register user
export const register = createAsyncThunk<
  { user: User; token: string }, // Returned
  { name: string; email: string; password: string }, // ThunkArg
  ThunkApiConfig // ThunkApiConfig
>(
  'auth/register',
  async (userData, { rejectWithValue }) => {
    try {
      const response: AxiosResponse<{ user: User; token: string }> = await axios.post(
        `${API_BASE_URL}/users/register`,
        {
          email: userData.email,
          password: userData.password,
          name: userData.name,
          role: 'patient', // Default role, or get from userData if applicable
        }
      );
      localStorage.setItem('token', response.data.token);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Registration failed');
    }
  }
);

// Login user
export const login = createAsyncThunk<
  LoginSuccessPayload, // Returned type
  LoginThunkArg,       // Argument type
  ThunkApiConfig       // ThunkAPI config with rejectValue type
>(
  'auth/login',
  async (credentials, { rejectWithValue }) => {
    try {
      const params = new URLSearchParams();
      params.append('username', credentials.email);
      params.append('password', credentials.password);

      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('请求超时，请检查网络连接或服务器状态')), 8000);
      });

      const requestPromise: Promise<AxiosResponse<LoginSuccessPayload & { access_token: string }>> = axios.post(
        `${API_BASE_URL}/users/login`,
        params,
        {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Accept': 'application/json'
          }
        }
      );

      const responseOrError = await Promise.race([requestPromise, timeoutPromise]);

      // If timeoutPromise rejected, it would be caught by the outer catch block.
      // So, if we are here, responseOrError should be the result of requestPromise.
      // We assume it's an AxiosResponse if it's an object with a 'data' property.
      if (responseOrError && typeof responseOrError === 'object' && 'data' in responseOrError && 'status' in responseOrError) {
        const successfulResponse = responseOrError as AxiosResponse<LoginSuccessPayload & { access_token: string }>;
        if (successfulResponse.data && successfulResponse.data.access_token && successfulResponse.data.user) {
          localStorage.setItem('token', successfulResponse.data.access_token);
          localStorage.setItem('userRole', successfulResponse.data.user.role);
          return {
            user: successfulResponse.data.user as User,
            token: successfulResponse.data.access_token
          };
        }
      }
      // If the structure is not as expected, or if it somehow wasn't a timeout but also not a valid success
      console.error('登录响应格式错误');
      return rejectWithValue('登录响应格式错误或请求被中断');

    } catch (error: any) {
      console.error('登录请求失败');
      let errorMessage = '登录失败，请稍后重试';
      if (error.message && error.message.includes('超时')) {
        errorMessage = error.message;
      } else if (axios.isAxiosError(error) && error.response) {
        if (error.response.status === 401) {
          errorMessage = '用户名或密码不正确';
        } else if (error.response.status === 400) {
          errorMessage = '请求格式错误';
          if (error.response.data && error.response.data.detail) {
            errorMessage += `: ${error.response.data.detail}`;
          }
        } else if (error.response.status === 500) {
          errorMessage = '服务器内部错误，请稍后重试';
        } else {
          errorMessage = error.response.data?.detail || error.response.statusText || '登录请求失败';
        }
      } else if (axios.isAxiosError(error) && error.request) {
        errorMessage = '无法连接到服务器，请检查网络连接';
      } else {
        // This will catch the TypeError if isAxiosError itself is the problem on a non-Axios error
        errorMessage = error.message || '发送请求时发生未知错误';
      }
      return rejectWithValue(errorMessage);
    }
  }
);

// Check token validity and get user data
export const checkAuthStatus = createAsyncThunk<
  User, // Returned
  void, // ThunkArg (no argument for this one)
  ThunkApiConfig
>(
  'auth/checkStatus',
  async (_, { rejectWithValue, getState }) => {
    const { auth } = getState();
    if (!auth.token) {
      return rejectWithValue('No token found');
    }
    try {
      const response: AxiosResponse<User> = await axios.get(`${API_BASE_URL}/users/me`, {
        headers: { Authorization: `Bearer ${auth.token}` }
      });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Session expired');
    }
  }
);

interface UpdateUserProfileArg {
  name: string;
  email?: string;
  currentPassword?: string;
  newPassword?: string;
}

// 添加更新用户资料的异步操作
export const updateUserProfile = createAsyncThunk<
  User, // Returned
  UpdateUserProfileArg, // ThunkArg
  ThunkApiConfig
>(
  'auth/updateProfile',
  async (userData, { rejectWithValue, getState }) => {
    const { auth } = getState();
    if (!auth.token) {
      return rejectWithValue('No token found');
    }
    try {
      const response: AxiosResponse<User> = await axios.put(`${API_BASE_URL}/users/profile`, userData, {
        headers: { Authorization: `Bearer ${auth.token}` }
      });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '更新个人资料失败');
    }
  }
);

// Legacy demo exports use the same backend authentication as ordinary login.
// They cannot manufacture a principal or a token, and require explicitly seeded accounts.
const demoLogin = (kind: string, email: string, password: string) => createAsyncThunk<
  LoginSuccessPayload, void, ThunkApiConfig
>(`auth/${kind}`, async (_, { dispatch, rejectWithValue }) => {
  try {
    return await dispatch(login({ email, password })).unwrap();
  } catch (error) {
    return rejectWithValue(typeof error === 'string' ? error : '演示账号登录失败');
  }
});
export const mockDoctorLogin = demoLogin('mockDoctorLogin', 'doctor@example.com', 'Doctor123!');
export const mockHealthManagerLogin = demoLogin('mockHealthManagerLogin', 'liujk@example.com', 'Manager123!');
export const mockAdminLogin = demoLogin('mockAdminLogin', 'admin@example.com', 'Admin123!');
export const mockPatientLogin = demoLogin('mockPatientLogin', 'zhangsan@example.com', 'Patient123!');

// A token replacement or logout invalidates every validation of the previous session.
function invalidateSessionCheck(state: AuthState) {
  state.checking = false;
  state.sessionCheckRequestId = null;
  state.sessionCheckToken = null;
}

function isCurrentSessionCheck(state: AuthState, requestId: string) {
  return state.sessionCheckRequestId === requestId && state.sessionCheckToken === state.token;
}

// Auth slice
const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    logout: (state: AuthState) => {
      invalidateSessionCheck(state);
      state.user = null;
      state.token = null;
      state.error = null;
      localStorage.removeItem('token');
      localStorage.removeItem('userRole');
    },
    clearAuthError: (state: AuthState) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // Register cases
      .addCase(register.pending, (state: AuthState) => {
        state.registerLoading = true;
        state.loading = false;
        state.error = null;
      })
      .addCase(register.fulfilled, (state: AuthState, action: PayloadAction<{ user: User; token: string }>) => {
        invalidateSessionCheck(state);
        state.registerLoading = false;
        state.loading = false;
        state.checking = false;
        state.user = action.payload.user;
        state.token = action.payload.token;
      })
      .addCase(register.rejected, (state: AuthState, action) => {
        state.registerLoading = false;
        state.loading = false;
        state.checking = false;
        state.error = action.payload as string;
      })

      // Login cases
      .addCase(login.pending, (state: AuthState) => {
        state.loginLoading = true;
        state.error = null;
      })
      .addCase(login.fulfilled, (state: AuthState, action: PayloadAction<LoginSuccessPayload>) => {
        invalidateSessionCheck(state);
        state.loginLoading = false;
        state.checking = false;
        state.user = action.payload.user;
        state.token = action.payload.token;
        state.error = null;
      })
      .addCase(login.rejected, (state: AuthState, action) => {
        state.loginLoading = false;
        state.error = action.payload as string;
      })

      // Check auth status cases
      .addCase(checkAuthStatus.pending, (state: AuthState, action) => {
        state.checking = true;
        state.sessionCheckRequestId = action.meta.requestId;
        state.sessionCheckToken = state.token;
        state.error = null;
      })
      .addCase(checkAuthStatus.fulfilled, (state: AuthState, action) => {
        if (!isCurrentSessionCheck(state, action.meta.requestId)) return;
        invalidateSessionCheck(state);
        state.user = action.payload;
      })
      .addCase(checkAuthStatus.rejected, (state: AuthState, action) => {
        if (!isCurrentSessionCheck(state, action.meta.requestId)) return;
        // A stale validation must not erase a newer token (including another tab's).
        if (localStorage.getItem('token') === state.token) {
          localStorage.removeItem('token');
          localStorage.removeItem('userRole');
        }
        invalidateSessionCheck(state);
        state.user = null;
        state.token = null;
        state.error = action.payload as string;
      })

      // Update user profile cases
      .addCase(updateUserProfile.pending, (state: AuthState) => {
        state.profileLoading = true;
        state.error = null;
      })
      .addCase(updateUserProfile.fulfilled, (state: AuthState, action: PayloadAction<User>) => {
        state.profileLoading = false;
        state.user = action.payload;
        state.error = null;
      })
      .addCase(updateUserProfile.rejected, (state: AuthState, action) => {
        state.profileLoading = false;
        state.error = action.payload as string;
      })

      // 添加模拟医生登录处理
      .addCase(mockDoctorLogin.pending, (state) => {
        state.loading = true;
        state.loginLoading = true;
        state.error = null;
      })
      .addCase(mockDoctorLogin.fulfilled, (state, action) => {
        invalidateSessionCheck(state);
        state.loading = false;
        state.loginLoading = false;
        state.user = action.payload.user;
        state.token = action.payload.token;
        state.checking = false;
      })
      .addCase(mockDoctorLogin.rejected, (state, action) => {
        state.loading = false;
        state.loginLoading = false;
        state.error = action.payload || '模拟医生登录失败';
      })

      // 添加模拟健康管理师登录处理
      .addCase(mockHealthManagerLogin.pending, (state) => {
        state.loading = true;
        state.loginLoading = true;
        state.error = null;
      })
      .addCase(mockHealthManagerLogin.fulfilled, (state, action) => {
        invalidateSessionCheck(state);
        state.loading = false;
        state.loginLoading = false;
        state.user = action.payload.user;
        state.token = action.payload.token;
        state.checking = false;
      })
      .addCase(mockHealthManagerLogin.rejected, (state, action) => {
        state.loading = false;
        state.loginLoading = false;
        state.error = action.payload || '模拟健康管理师登录失败';
      })

      // 添加模拟管理员登录处理
      .addCase(mockAdminLogin.pending, (state) => {
        state.loading = true;
        state.loginLoading = true;
        state.error = null;
      })
      .addCase(mockAdminLogin.fulfilled, (state, action) => {
        invalidateSessionCheck(state);
        state.loading = false;
        state.loginLoading = false;
        state.user = action.payload.user;
        state.token = action.payload.token;
        state.checking = false;
      })
      .addCase(mockAdminLogin.rejected, (state, action) => {
        state.loading = false;
        state.loginLoading = false;
        state.error = action.payload || '模拟管理员登录失败';
      })

      // 添加模拟患者登录处理
      .addCase(mockPatientLogin.pending, (state) => {
        state.loading = true;
        state.loginLoading = true;
        state.error = null;
      })
      .addCase(mockPatientLogin.fulfilled, (state, action) => {
        invalidateSessionCheck(state);
        state.loading = false;
        state.loginLoading = false;
        state.user = action.payload.user;
        state.token = action.payload.token;
        state.checking = false;
      })
      .addCase(mockPatientLogin.rejected, (state, action) => {
        state.loading = false;
        state.loginLoading = false;
        state.error = action.payload || '模拟患者登录失败';
      });
  },
});

export const { logout, clearAuthError } = authSlice.actions;
export default authSlice.reducer;
