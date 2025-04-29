import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';
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
  error: string | null;
}

// Initial state
const initialState: AuthState = {
  user: null,
  token: localStorage.getItem('token'),
  checking: true,
  loading: false,
  error: null,
};

// Register user
export const register = createAsyncThunk(
  'auth/register',
  async (userData: { name: string; email: string; password: string }, { rejectWithValue }) => {
    try {
      const response = await axios.post(`/api/users/register`, {
        email: userData.email,
        password: userData.password,
        name: userData.name,
        role: 'patient' // 默认角色
      });
      localStorage.setItem('token', response.data.token);
      return response.data;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || 'Registration failed');
    }
  }
);

// Login user
export const login = createAsyncThunk(
  'auth/login',
  async (credentials: { email: string; password: string }, { rejectWithValue }) => {
    try {
      console.log('Attempting login with:', credentials.email);
      
      // 使用FormData来匹配OAuth2PasswordRequestForm的要求
      const formData = new FormData();
      formData.append('username', credentials.email);
      formData.append('password', credentials.password);
      
      const response = await axios.post(`/api/users/login`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        }
      });
      
      console.log('Login response:', response.data);
      
      localStorage.setItem('token', response.data.access_token);
      localStorage.setItem('userRole', response.data.user.role);
      return {
        user: response.data.user,
        token: response.data.access_token
      };
    } catch (error: any) {
      console.error('Login error:', error);
      
      // 提供更详细的错误信息
      const errorMessage = error.response?.data?.detail || 
                         error.response?.statusText || 
                         (error.message === 'Network Error' ? '无法连接到服务器' : '登录失败');
      
      return rejectWithValue(errorMessage);
    }
  }
);

// Check token validity and get user data
export const checkAuthStatus = createAsyncThunk(
  'auth/checkStatus',
  async (_, { rejectWithValue, getState }) => {
    const { auth } = getState() as { auth: AuthState };
    
    if (!auth.token) {
      return rejectWithValue('No token found');
    }
    
    try {
      const response = await axios.get(`/api/users/me`, {
        headers: {
          Authorization: `Bearer ${auth.token}`
        }
      });
      return response.data;
    } catch (error: any) {
      localStorage.removeItem('token');
      return rejectWithValue(error.response?.data?.detail || 'Session expired');
    }
  }
);

// 添加更新用户资料的异步操作
export const updateUserProfile = createAsyncThunk(
  'auth/updateProfile',
  async (userData: {name: string, email?: string, currentPassword?: string, newPassword?: string}, { rejectWithValue, getState }) => {
    const { auth } = getState() as { auth: AuthState };
    
    if (!auth.token) {
      return rejectWithValue('No token found');
    }
    
    try {
      const response = await axios.put(`/api/users/profile`, userData, {
        headers: {
          Authorization: `Bearer ${auth.token}`
        }
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
    logout: (state) => {
      state.user = null;
      state.token = null;
      state.error = null;
      localStorage.removeItem('token');
      localStorage.removeItem('userRole');
    },
    clearAuthError: (state) => {
      state.error = null;
    },
    // 添加模拟登录的reducer
    mockAdminLogin: (state) => {
      const mockToken = 'mock-admin-token-123456';
      const mockUser: User = {
        id: 'admin1',
        email: 'admin@example.com',
        name: '系统管理员',
        role: 'admin',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      
      state.user = mockUser;
      state.token = mockToken;
      state.checking = false;
      state.loading = false;
      state.error = null;
      
      localStorage.setItem('token', mockToken);
      localStorage.setItem('userRole', 'admin');
    },
    // 添加模拟医生登录
    mockDoctorLogin: (state) => {
      const mockToken = 'mock-doctor-token-123456';
      const mockUser: User = {
        id: 'doctor1',
        email: 'doctor@example.com',
        name: '张医生',
        role: 'doctor',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      
      state.user = mockUser;
      state.token = mockToken;
      state.checking = false;
      state.loading = false;
      state.error = null;
      
      localStorage.setItem('token', mockToken);
      localStorage.setItem('userRole', 'doctor');
    },
    // 添加模拟健康管理师登录
    mockHealthManagerLogin: (state) => {
      const mockToken = 'mock-health-manager-token-123456';
      const mockUser: User = {
        id: 'hm1',
        email: 'healthmanager@example.com',
        name: '李健康',
        role: 'health_manager',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      
      state.user = mockUser;
      state.token = mockToken;
      state.checking = false;
      state.loading = false;
      state.error = null;
      
      localStorage.setItem('token', mockToken);
      localStorage.setItem('userRole', 'health_manager');
    },
    // 添加模拟患者登录
    mockPatientLogin: (state) => {
      const mockToken = 'mock-patient-token-123456';
      const mockUser: User = {
        id: 'patient1',
        email: 'patient@example.com',
        name: '王患者',
        role: 'patient',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      
      state.user = mockUser;
      state.token = mockToken;
      state.checking = false;
      state.loading = false;
      state.error = null;
      
      localStorage.setItem('token', mockToken);
      localStorage.setItem('userRole', 'patient');
    }
  },
  extraReducers: (builder) => {
    builder
      // Register cases
      .addCase(register.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(register.fulfilled, (state, action: PayloadAction<{ user: User; token: string }>) => {
        state.loading = false;
        state.checking = false;
        state.user = action.payload.user;
        state.token = action.payload.token;
      })
      .addCase(register.rejected, (state, action) => {
        state.loading = false;
        state.checking = false;
        state.error = action.payload as string;
      })
      
      // Login cases
      .addCase(login.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(login.fulfilled, (state, action: PayloadAction<{ user: User; token: string }>) => {
        state.loading = false;
        state.checking = false;
        state.user = action.payload.user;
        state.token = action.payload.token;
      })
      .addCase(login.rejected, (state, action) => {
        state.loading = false;
        state.checking = false;
        state.error = action.payload as string;
      })
      
      // Check auth status cases
      .addCase(checkAuthStatus.pending, (state) => {
        state.checking = true;
        state.error = null;
      })
      .addCase(checkAuthStatus.fulfilled, (state, action: PayloadAction<User>) => {
        state.checking = false;
        state.user = action.payload;
      })
      .addCase(checkAuthStatus.rejected, (state, action) => {
        state.checking = false;
        state.user = null;
        state.token = null;
        state.error = action.payload as string;
      })
      
      // Update user profile cases
      .addCase(updateUserProfile.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateUserProfile.fulfilled, (state, action: PayloadAction<User>) => {
        state.loading = false;
        state.user = action.payload;
        state.error = null;
      })
      .addCase(updateUserProfile.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { logout, clearAuthError, mockAdminLogin, mockDoctorLogin, mockHealthManagerLogin, mockPatientLogin } = authSlice.actions;
export default authSlice.reducer; 