import { createSlice, createAsyncThunk, PayloadAction, Dispatch } from '@reduxjs/toolkit';
import axios, { AxiosResponse } from 'axios';
import { RootState } from '..';

// Base API URL - 使用代理配置，不需要完整URL
// const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// User interface
export interface User {
  id: string;
  email: string;
  name: string;
  role: 'patient' | 'doctor' | 'health_manager' | 'admin';
  createdAt: string;
  updatedAt: string;
}

// Auth state interface
export interface AuthState {
  user: User | null;
  token: string | null;
  checking: boolean;
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

// Typed ThunkAPI
interface ThunkApiConfig {
  dispatch: Dispatch;
  getState: () => RootState;
  rejectValue: string;
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
      const response: AxiosResponse<{ user: User; token: string }> = await (axios as any).post(
        `/api/users/register`,
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
      console.log('Attempting login with:', credentials.email);
      const params = new URLSearchParams();
      params.append('username', credentials.email);
      params.append('password', credentials.password);
      console.log('Sending login request to API...');

      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('请求超时，请检查网络连接或服务器状态')), 8000);
      });

      const requestPromise: Promise<AxiosResponse<LoginSuccessPayload & { access_token: string }>> = (axios as any).post(
        '/api/users/login', 
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
      console.error('Login response format error or unexpected issue:', responseOrError);
      return rejectWithValue('登录响应格式错误或请求被中断');

    } catch (error: any) {
      console.error('Login error (outer catch):', error);
      let errorMessage = '登录失败，请稍后重试';
      if (error.message && error.message.includes('超时')) {
        errorMessage = error.message;
      } else if ((axios as any).isAxiosError(error) && error.response) {
        console.error('Error response data:', error.response.data);
        console.error('Error response status:', error.response.status);
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
      } else if ((axios as any).isAxiosError(error) && error.request) {
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
      const response: AxiosResponse<User> = await (axios as any).get(`/api/users/me`, {
        headers: { Authorization: `Bearer ${auth.token}` }
      });
      return response.data;
    } catch (error: any) {
      localStorage.removeItem('token');
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
      const response: AxiosResponse<User> = await axios.put(`/api/users/profile`, userData, {
        headers: { Authorization: `Bearer ${auth.token}` }
      });
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '更新个人资料失败');
    }
  }
);

// Auth slice
const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    logout: (state: AuthState) => {
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
      .addCase(checkAuthStatus.pending, (state: AuthState) => {
        state.checking = true;
        state.error = null;
      })
      .addCase(checkAuthStatus.fulfilled, (state: AuthState, action: PayloadAction<User>) => {
        state.checking = false;
        state.user = action.payload;
      })
      .addCase(checkAuthStatus.rejected, (state: AuthState, action) => {
        state.checking = false;
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
      });
  },
});

export const { logout, clearAuthError } = authSlice.actions;
export default authSlice.reducer; 