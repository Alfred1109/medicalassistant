import { API_COLLECTION_PATHS } from '../config/apiPaths';
import type { AxiosResponse } from 'axios';
import api from './httpClient';
import type { LoginCredentials, TokenResponse, User } from '../types/api.types';
import type { Patient, PatientHealthRecord } from '../types/patient.types';
import type { Doctor } from '../types/doctor.types';
import type { FollowUpRecord, FollowUpWorkbenchQuery, FollowUpWorkbenchPage, ReviewFollowUpRequest, ReEvaluateFollowUpRequest } from '../types/followup';

// API服务方法
export const apiService = {
  // 设备相关API
  // 后端 GET /api/devices 返回当前登录用户（token 主体）绑定的设备列表，
  // 不存在 GET /devices/user/{userId} 路由；userId 参数仅保留兼容旧调用方。
  getUserDevices: (userId?: string) => api.get(API_COLLECTION_PATHS.DEVICES),
  // 后端 POST /api/devices/bind 以当前登录用户为绑定主体（body 为 DeviceCreate，
  // device_type 必填），不再在 body 中传 user_id。
  bindUserDevice: (userId: string, deviceData: any) => {
    const { type, ...rest } = deviceData || {};
    return api.post('/devices/bind', { ...rest, device_type: rest.device_type ?? type });
  },
  // 后端为 DELETE /api/devices/{device_id}/unbind，没有 POST /devices/unbind
  unbindUserDevice: (userId: string, deviceId: string) => api.delete(`/devices/${deviceId}/unbind`),
  // 后端查询参数为 start_date / end_date / data_type / limit
  getDeviceData: (deviceId: string, params: any) => api.get(`/devices/${deviceId}/data`, {
    params: params ? {
      start_date: params.startDate ?? params.start_date,
      end_date: params.endDate ?? params.end_date,
      data_type: params.dataType ?? params.data_type,
      limit: params.limit,
    } : undefined,
  }),
  syncDeviceData: (deviceId: string) => api.post(`/devices/${deviceId}/sync`),
  recordDeviceReading: (deviceId: string, body: { data_type: string; value: string; unit: string; measured_at: string }) =>
    api.post(`/devices/${deviceId}/readings`, body),
  getDeviceStatus: (deviceId: string) => api.get(`/devices/${deviceId}/status`),
  // 后端为 PUT /api/devices/{device_id}/config（DeviceConfigUpdate: sync_frequency /
  // notifications_enabled / custom_name / alarm_settings），没有 POST /devices/{id}/configure
  configureDevice: (deviceId: string, config: any) => api.put(`/devices/${deviceId}/config`, {
    sync_frequency: config?.syncFrequency ?? config?.sync_frequency,
    notifications_enabled: config?.notificationsEnabled ?? config?.notifications_enabled,
    custom_name: config?.customName ?? config?.custom_name,
    alarm_settings: config?.alarmSettings ?? config?.alarm_settings,
  }),
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
    
    getPatientMonitoring: (patientId: string, startDate?: string, endDate?: string): Promise<AxiosResponse<any>> =>
      api.get(`/doctors/patient-monitoring/${patientId}`, {
        params: { start_date: startDate, end_date: endDate }
      }),
  },
  
  healthManager: {
    getPatients: (): Promise<AxiosResponse<Patient[]>> => api.get('/health-managers/patients'),
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

  // 健康档案(健康管理师页面直接调用这些方法)
  getHealthRecords: (patientId: string, params?: Record<string, any>): Promise<AxiosResponse<any[]>> =>
    api.get('/health-records', { params: { patient_id: patientId, ...(params || {}) } }),

  getHealthRecordStats: (patientId: string): Promise<AxiosResponse<any>> =>
    api.get(`/health-records/stats/${patientId}`),

  createHealthRecord: (recordData: any): Promise<AxiosResponse<any>> =>
    api.post('/health-records', recordData),

  updateHealthRecord: (recordId: string, recordData: any): Promise<AxiosResponse<any>> =>
    api.put(`/health-records/${recordId}`, recordData),

  deleteHealthRecord: (recordId: string): Promise<AxiosResponse<any>> =>
    api.delete(`/health-records/${recordId}`),

  // 随访记录
  getFollowUps: (patientId: string, params?: Record<string, any>): Promise<AxiosResponse<FollowUpRecord[]>> =>
    api.get('/health-records/followups', { params: { patient_id: patientId, ...(params || {}) } }),

  getFollowUpWorkbench: (params: FollowUpWorkbenchQuery, signal?: AbortSignal): Promise<AxiosResponse<FollowUpWorkbenchPage>> =>
    api.get('/health-records/followup-workbench', { params, signal }),

  getFollowUp: (followUpId: string): Promise<AxiosResponse<FollowUpRecord>> =>
    api.get(`/health-records/followups/${followUpId}`),

  reviewFollowUp: (followUpId: string, data: ReviewFollowUpRequest): Promise<AxiosResponse<FollowUpRecord>> =>
    api.post(`/health-records/followups/${followUpId}/review`, data),

  reEvaluateFollowUp: (followUpId: string, data: ReEvaluateFollowUpRequest): Promise<AxiosResponse<FollowUpRecord>> =>
    api.post(`/health-records/followups/${followUpId}/re-evaluate`, data),

  createFollowUp: (followUpData: any): Promise<AxiosResponse<any>> =>
    api.post('/health-records/followups', followUpData),

  updateFollowUp: (followUpId: string, followUpData: any): Promise<AxiosResponse<any>> =>
    api.put(`/health-records/followups/${followUpId}`, followUpData),

  completeFollowUp: (followUpId: string, data: { expected_version: number; actual_date: string; follow_up_result: string; notes?: string }): Promise<AxiosResponse<any>> =>
    api.post(`/health-records/followups/${followUpId}/complete`, data ?? {}),

  cancelFollowUp: (followUpId: string, data: { cancel_reason: string }): Promise<AxiosResponse<any>> =>
    api.post(`/health-records/followups/${followUpId}/cancel`, data),

  rescheduleFollowUp: (followUpId: string, data: { new_date: string; reason?: string }): Promise<AxiosResponse<any>> =>
    api.post(`/health-records/followups/${followUpId}/reschedule`, data),

  markFollowUpOverdue: (followUpId: string, data: { reason: string }): Promise<AxiosResponse<FollowUpRecord>> =>
    api.post(`/health-records/followups/${followUpId}/overdue`, data),

  markFollowUpLost: (followUpId: string, data: { reason: string }): Promise<AxiosResponse<FollowUpRecord>> =>
    api.post(`/health-records/followups/${followUpId}/lost`, data),

  // 健康数据(体征、化验结果等)
  getHealthData: (patientId: string, params?: Record<string, any>): Promise<AxiosResponse<any[]>> =>
    api.get('/health-records/health-data', { params: { patient_id: patientId, ...(params || {}) } }),
  
  // AI助手接口
  // 注意：后端 agent_router 不提供 POST /agents/{id}/execute，只保留查询/CRUD 接口。
  agent: {
    getAgents: (): Promise<AxiosResponse<any[]>> =>
      api.get(API_COLLECTION_PATHS.AGENTS),
    
    createAgent: (agentData: any): Promise<AxiosResponse<any>> => 
      api.post(API_COLLECTION_PATHS.AGENTS, agentData),
    
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
    // 注意：后端 /api/admin/doctors 仅有 GET/POST，无 PUT/DELETE /admin/doctors/{id}，
    // 故不提供 updateDoctor / deleteDoctor（后端能力待建设）。
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
