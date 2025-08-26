import api from './api';
import { STORAGE_KEYS } from '../config/constants';

/**
 * 认证服务
 */
export const AuthService = {
  /**
   * 登录并获取令牌
   * @param username 用户名
   * @param password 密码
   */
  async login(username: string, password: string) {
    try {
      // 创建表单数据
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);
      
      // 调用带刷新令牌的登录接口
      const response = await api.post('/users/login/refresh', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        }
      });
      
      // 保存令牌和用户信息到本地存储
      if (response.data && response.data.access_token) {
        localStorage.setItem(STORAGE_KEYS.TOKEN, response.data.access_token);
        localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, response.data.refresh_token);
        localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(response.data.user));
        localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, String(Date.now() + (response.data.expires_in * 1000)));
      }
      
      return response.data;
    } catch (error) {
      console.error('登录失败:', error);
      throw error;
    }
  },
  
  /**
   * 刷新访问令牌
   */
  async refreshToken() {
    try {
      const refreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
      
      if (!refreshToken) {
        throw new Error('没有刷新令牌');
      }
      
      // 调用刷新令牌接口
      const response = await api.post('/users/refresh-token', {
        refresh_token: refreshToken
      });
      
      // 更新本地存储中的令牌
      if (response.data && response.data.access_token) {
        localStorage.setItem(STORAGE_KEYS.TOKEN, response.data.access_token);
        localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, response.data.refresh_token);
        localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, String(Date.now() + (response.data.expires_in * 1000)));
        
        // 如果响应中包含用户信息，也更新用户信息
        if (response.data.user) {
          localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(response.data.user));
        }
      }
      
      return response.data;
    } catch (error) {
      console.error('刷新令牌失败:', error);
      // 刷新失败时，清除所有令牌和用户信息
      this.logout();
      throw error;
    }
  },
  
  /**
   * 检查令牌是否过期或即将过期
   * @param expiryThresholdMs 过期阈值（毫秒），默认为5分钟
   * @returns 令牌是否过期或即将过期
   */
  isTokenExpired(expiryThresholdMs = 5 * 60 * 1000): boolean {
    const tokenExpiryString = localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRY);
    
    if (!tokenExpiryString) {
      return true;
    }
    
    const tokenExpiry = Number(tokenExpiryString);
    return Date.now() > tokenExpiry - expiryThresholdMs;
  },
  
  /**
   * 自动刷新令牌（如果需要）
   * @returns 是否成功刷新了令牌
   */
  async autoRefreshToken(): Promise<boolean> {
    try {
      // 检查令牌是否过期或即将过期
      if (this.isTokenExpired()) {
        // 刷新令牌
        await this.refreshToken();
        return true;
      }
      return false;
    } catch (error) {
      console.error('自动刷新令牌失败:', error);
      return false;
    }
  },
  
  /**
   * 获取当前用户
   */
  async getCurrentUser() {
    try {
      // 先尝试自动刷新令牌（如果需要）
      await this.autoRefreshToken();
      
      // 调用获取当前用户接口
      const response = await api.get('/users/me');
      return response.data;
    } catch (error) {
      console.error('获取当前用户失败:', error);
      throw error;
    }
  },
  
  /**
   * 退出登录
   */
  logout() {
    localStorage.removeItem(STORAGE_KEYS.TOKEN);
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.USER);
    localStorage.removeItem(STORAGE_KEYS.TOKEN_EXPIRY);
  },
  
  /**
   * 检查用户是否已经登录
   */
  isLoggedIn(): boolean {
    return !!localStorage.getItem(STORAGE_KEYS.TOKEN);
  }
};

export default AuthService; 