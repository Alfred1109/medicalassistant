import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';
import { API_BASE_URL, STORAGE_KEYS } from '../config/constants';
import { 
  ApiResponse, 
  LoginCredentials, 
  TokenResponse, 
  User 
} from '../types/api.types';
import { 
  Patient, 
  PatientHealthRecord 
} from '../types/patient.types';
import { 
  Doctor, 
  FollowUp 
} from '../types/doctor.types';

// 标记是否正在刷新令牌，避免重复刷新
let isRefreshing = false;
// 存储因为等待令牌刷新而挂起的请求
let waitingQueue: Array<{
  onSuccess: (token: string) => void;
  onFailure: (error: any) => void;
}> = [];

// 处理刷新令牌后的回调
const processQueue = (error: any, token: string | null) => {
  waitingQueue.forEach(promise => {
    if (error) {
      promise.onFailure(error);
    } else if (token) {
      promise.onSuccess(token);
    }
  });
  
  // 处理完成后清空队列
  waitingQueue = [];
};

// 创建axios实例
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  }
});

// 请求拦截器
api.interceptors.request.use(
  async (config: AxiosRequestConfig) => {
    // 从localStorage获取token - 每次请求时重新获取，确保使用最新token
    const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
    const tokenExpiry = localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRY);
    const refreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
    
    // 检查token是否即将过期（5分钟内）
    const isExpiringSoon = tokenExpiry && (Number(tokenExpiry) - Date.now() < 5 * 60 * 1000);
    
    // 自动刷新token的逻辑（当token即将过期且有刷新token可用）
    if (token && isExpiringSoon && refreshToken) {
      // 排除刷新token的请求本身，避免循环
      if (config.url?.includes('/users/refresh-token')) {
        return config;
      }
      
      // 如果不是正在刷新中，则执行刷新
      if (!isRefreshing) {
        isRefreshing = true;
        
        try {
          // 刷新token
          const response = await axios.post(`${API_BASE_URL}/users/refresh-token`, {
            refresh_token: refreshToken
          });
          
          const newToken = response.data.access_token;
          const newRefreshToken = response.data.refresh_token;
          const expiresIn = response.data.expires_in;
          
          // 更新存储
          localStorage.setItem(STORAGE_KEYS.TOKEN, newToken);
          localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, newRefreshToken);
          localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, String(Date.now() + (expiresIn * 1000)));
          
          // 使用新token更新当前请求
          if (config.headers) {
            config.headers.Authorization = `Bearer ${newToken}`;
          }
          
          // 处理队列中等待的请求
          processQueue(null, newToken);
          
          console.log('[API] Token自动刷新成功');
        } catch (error) {
          // 刷新失败，处理队列中的错误
          processQueue(error, null);
          
          // 清除token
          localStorage.removeItem(STORAGE_KEYS.TOKEN);
          localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
          localStorage.removeItem(STORAGE_KEYS.USER);
          localStorage.removeItem(STORAGE_KEYS.TOKEN_EXPIRY);
          
          console.error('[API] Token刷新失败:', error);
          
          // 重定向到登录页（如果需要）
          if (!window.location.pathname.includes('/login')) {
            window.location.href = '/login';
          }
        } finally {
          isRefreshing = false;
        }
      } else {
        // 如果正在刷新中，将请求加入队列
        return new Promise((resolve, reject) => {
          waitingQueue.push({
            onSuccess: (newToken: string) => {
              if (config.headers) {
                config.headers.Authorization = `Bearer ${newToken}`;
              }
              resolve(config);
            },
            onFailure: (refreshError: any) => {
              reject(refreshError);
            }
          });
        });
      }
    }
    
    // DEBUG - 输出请求信息和token状态
    console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`);
    console.log(`[API Token Status] ${token ? 'Token存在' : 'Token不存在'}`);
    
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
      // DEBUG - 输出授权头信息
      console.log(`[API Auth Header] Authorization: Bearer ${token.substring(0, 15)}...`);
    }
    
    return config;
  },
  (error: AxiosError) => {
    console.error('[API Request Error]', error);
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  (response: AxiosResponse) => {
    // DEBUG - 输出请求成功信息
    console.log(`[API Response] ${response.config.method?.toUpperCase()} ${response.config.url} - Status: ${response.status}`);
    return response;
  },
  (error: AxiosError) => {
    // 处理错误情况，例如401未授权跳转到登录页
    if (error.response) {
      console.error(`[API Error] Status: ${error.response.status}, URL: ${error.config?.url}`);
      
      if (error.response.status === 401) {
        console.warn('[API Authentication Error] Token无效或过期，重定向到登录页');
        // 清除无效token
        localStorage.removeItem(STORAGE_KEYS.TOKEN);
        localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.USER);
        localStorage.removeItem(STORAGE_KEYS.TOKEN_EXPIRY);
        
        // 避免在登录页上发生重定向循环
        if (!window.location.pathname.includes('/login')) {
          window.location.href = '/login';
        }
      }
    } else if (error.request) {
      // 请求已发出但未收到响应
      console.error('[API Error] 请求未收到响应', error.request);
    } else {
      // 请求配置出错
      console.error('[API Error] 请求配置错误', error.message);
    }
    
    return Promise.reject(error);
  }
);

// API服务方法
export const apiService = {
  // 设备相关API
  getUserDevices: (userId: string) => api.get(`/devices/user/${userId}`),
  bindUserDevice: (userId: string, deviceData: any) => api.post(`/devices/bind`, { ...deviceData, user_id: userId }),
  unbindUserDevice: (userId: string, deviceId: string) => api.post(`/devices/unbind`, { user_id: userId, device_id: deviceId }),
  getDeviceData: (deviceId: string, params: any) => api.get(`/devices/${deviceId}/data`, { params }),
  syncDeviceData: (deviceId: string) => api.post(`/devices/${deviceId}/sync`),
  getDeviceStatus: (deviceId: string) => api.get(`/devices/${deviceId}/status`),
  configureDevice: (deviceId: string, config: any) => api.post(`/devices/${deviceId}/configure`, config),
  repairDevice: (deviceId: string) => api.post(`/devices/${deviceId}/repair`),

  // 认证接口
  auth: {
    login: (credentials: LoginCredentials): Promise<AxiosResponse<TokenResponse>> => 
      api.post('/users/login', credentials),
    
    register: (userData: Partial<User>): Promise<AxiosResponse<User>> => 
      api.post('/users/register', userData),
    
    getCurrentUser: (): Promise<AxiosResponse<User>> => 
      api.get('/users/me'),
    
    updateProfile: (userId: string, data: Partial<User>): Promise<AxiosResponse<User>> => 
      api.put(`/users/${userId}`, data),
  },
  
  // 医生相关接口
  doctor: {
    getPatients: (): Promise<AxiosResponse<Patient[]>> => 
      api.get('/doctors/patients'),
    
    getPatientHealthRecord: (patientId: string): Promise<AxiosResponse<PatientHealthRecord>> => 
      api.get(`/doctors/health-records/${patientId}`),
    
    getFollowUps: (status?: string): Promise<AxiosResponse<FollowUp[]>> => 
      api.get('/doctors/follow-ups', { params: { status } }),
    
    createFollowUp: (data: Partial<FollowUp>): Promise<AxiosResponse<FollowUp>> => 
      api.post('/doctors/follow-ups', data),
    
    getPatientMonitoring: (patientId: string, startDate?: string, endDate?: string): Promise<AxiosResponse<any>> => 
      api.get(`/doctors/patient-monitoring/${patientId}`, {
        params: { start_date: startDate, end_date: endDate }
      }),
  },
  
  // 康复计划接口
  rehabilitation: {
    getPlans: (patientId?: string): Promise<AxiosResponse<any[]>> => 
      api.get('/rehabilitation/plans', { params: { patient_id: patientId } }),
    
    getPlanById: (planId: string): Promise<AxiosResponse<any>> => 
      api.get(`/rehabilitation/plans/${planId}`),
    
    createPlan: (planData: any): Promise<AxiosResponse<any>> => 
      api.post('/rehabilitation/plans', planData),
    
    updatePlan: (planId: string, planData: any): Promise<AxiosResponse<any>> => 
      api.put(`/rehabilitation/plans/${planId}`, planData),
    
    deletePlan: (planId: string): Promise<AxiosResponse<any>> => 
      api.delete(`/rehabilitation/plans/${planId}`),
  },
  
  // 健康记录接口
  healthRecord: {
    getRecords: (patientId: string): Promise<AxiosResponse<any[]>> => 
      api.get(`/health-records`, { params: { patient_id: patientId } }),
    
    getRecordById: (recordId: string): Promise<AxiosResponse<any>> => 
      api.get(`/health-records/${recordId}`),
    
    createRecord: (recordData: any): Promise<AxiosResponse<any>> => 
      api.post('/health-records', recordData),
    
    updateRecord: (recordId: string, recordData: any): Promise<AxiosResponse<any>> => 
      api.put(`/health-records/${recordId}`, recordData),
    
    deleteRecord: (recordId: string): Promise<AxiosResponse<any>> => 
      api.delete(`/health-records/${recordId}`),
  },
  
  // AI助手接口
  agent: {
    executeAgent: (agentId: string): Promise<AxiosResponse<any>> => 
      api.post(`/agents/${agentId}/execute`),
    
    getAgents: (): Promise<AxiosResponse<any[]>> => 
      api.get('/agents'),
    
    createAgent: (agentData: any): Promise<AxiosResponse<any>> => 
      api.post('/agents', agentData),
    
    updateAgent: (agentId: string, agentData: any): Promise<AxiosResponse<any>> => 
      api.put(`/agents/${agentId}`, agentData),
    
    deleteAgent: (agentId: string): Promise<AxiosResponse<any>> => 
      api.delete(`/agents/${agentId}`),
    
    queryAgent: (agentId: string, query: string): Promise<AxiosResponse<any>> => 
      api.post(`/agents/${agentId}/query`, { query })
  },
  
  // 管理员接口
  admin: {
    getDoctors: (params?: any): Promise<AxiosResponse<Doctor[]>> => 
      api.get('/admin/doctors', { params }),
    
    createDoctor: (doctorData: Partial<Doctor>): Promise<AxiosResponse<Doctor>> => 
      api.post('/admin/doctors', doctorData),
    
    updateDoctor: (doctorId: string, doctorData: Partial<Doctor>): Promise<AxiosResponse<Doctor>> => 
      api.put(`/admin/doctors/${doctorId}`, doctorData),
    
    deleteDoctor: (doctorId: string): Promise<AxiosResponse<any>> => 
      api.delete(`/admin/doctors/${doctorId}`),
  },
  
  // 患者相关接口
  patient: {
    getDailyRecords: (startDate?: string, endDate?: string): Promise<AxiosResponse<any[]>> => 
      api.get('/patients/daily-records', { params: { start_date: startDate, end_date: endDate } }),
    
    createDailyRecord: (recordData: any): Promise<AxiosResponse<any>> => 
      api.post('/patients/daily-records', recordData),
    
    updateDailyRecord: (recordId: string, recordData: any): Promise<AxiosResponse<any>> => 
      api.put(`/patients/daily-records/${recordId}`, recordData),
    
    deleteDailyRecord: (recordId: string): Promise<AxiosResponse<any>> => 
      api.delete(`/patients/daily-records/${recordId}`),
    
    getDashboardData: (): Promise<AxiosResponse<any>> => 
      api.get('/patients/dashboard-data'),
    
    getHealthMetrics: (): Promise<AxiosResponse<any[]>> => 
      api.get('/patients/health-metrics'),
  },
};

export default api; 