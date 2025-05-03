import { AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';

// API响应的基本接口
export interface ApiResponse<T = any> {
  data: T;
  status: number;
  statusText: string;
  headers: Record<string, string>;
  config: AxiosRequestConfig;
}

// 用户相关类型
export interface User {
  id: string;
  email: string;
  name: string;
  role: 'patient' | 'doctor' | 'health_manager' | 'admin';
  permissions: string[];
  createdAt: string;
  updatedAt: string;
  is_active: boolean;
  last_login?: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
} 