import axios from 'axios';
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';
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

// 创建具有基础URL和默认头部的axios实例
const api: AxiosInstance = axios.create({
  baseURL: 'http://localhost:5502/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// 添加请求拦截器，包含认证令牌
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 添加响应拦截器，处理常见错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // 处理401未授权错误
    if (error.response && error.response.status === 401) {
      // 当令牌无效或过期时清除本地存储
      if (localStorage.getItem('token')) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        
        // 如果不在认证页面，重定向到登录页面
        if (!window.location.pathname.includes('/auth')) {
          window.location.href = '/auth';
        }
      }
    }
    
    // 处理网络错误
    if (!error.response) {
      console.error('网络错误:', error.message);
    }
    
    return Promise.reject(error);
  }
);

// API服务方法
export const apiService = {
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