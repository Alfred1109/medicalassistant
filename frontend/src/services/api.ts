import axios from 'axios';

// Create axios instance with base URL and default headers
const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add a request interceptor to include the auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Add a response interceptor to handle common errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Handle 401 Unauthorized errors
    if (error.response && error.response.status === 401) {
      // Clear local storage when token is invalid or expired
      if (localStorage.getItem('token')) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        
        // Redirect to login page if not already there
        if (!window.location.pathname.includes('/auth')) {
          window.location.href = '/auth';
        }
      }
    }
    
    // Handle network errors
    if (!error.response) {
      console.error('Network Error:', error.message);
    }
    
    return Promise.reject(error);
  }
);

// API service methods
const apiService = {
  // Auth endpoints
  login: (credentials) => api.post('/users/login', credentials),
  register: (userData) => api.post('/users/register', userData),
  getCurrentUser: () => api.get('/users/me'),
  updateProfile: (userId, data) => api.put(`/users/${userId}`, data),
  
  // Rehab plan endpoints
  getRehabPlans: () => api.get('/rehabilitation/plans'),
  getRehabPlanById: (planId) => api.get(`/rehabilitation/plans/${planId}`),
  createRehabPlan: (planData) => api.post('/rehabilitation/plans', planData),
  updateRehabPlan: (planId, planData) => api.put(`/rehabilitation/plans/${planId}`, planData),
  deleteRehabPlan: (planId) => api.delete(`/rehabilitation/plans/${planId}`),
  
  // Exercise endpoints
  getExercises: () => api.get('/rehabilitation/exercises'),
  getExerciseById: (exerciseId) => api.get(`/rehabilitation/exercises/${exerciseId}`),
  createExercise: (exerciseData) => api.post('/rehabilitation/exercises', exerciseData),
  updateExercise: (exerciseId, exerciseData) => api.put(`/rehabilitation/exercises/${exerciseId}`, exerciseData),
  deleteExercise: (exerciseId) => api.delete(`/rehabilitation/exercises/${exerciseId}`),
  
  // Agent endpoints
  getAgents: () => api.get('/agents'),
  getAgentById: (agentId) => api.get(`/agents/${agentId}`),
  createAgent: (agentData) => api.post('/agents', agentData),
  updateAgent: (agentId, agentData) => api.put(`/agents/${agentId}`, agentData),
  deleteAgent: (agentId) => api.delete(`/agents/${agentId}`),
  queryAgent: (agentId, query) => api.post(`/agents/${agentId}/query`, query),
  
  // 健康档案相关接口
  // 获取患者健康档案列表
  getHealthRecords: (patientId, params) => api.get(`/health-records?patient_id=${patientId}`, { params }),
  // 获取健康档案详情
  getHealthRecordById: (recordId) => api.get(`/health-records/${recordId}`),
  // 创建健康档案
  createHealthRecord: (recordData) => api.post('/health-records', recordData),
  // 更新健康档案
  updateHealthRecord: (recordId, recordData) => api.put(`/health-records/${recordId}`, recordData),
  // 删除健康档案
  deleteHealthRecord: (recordId) => api.delete(`/health-records/${recordId}`),
  // 获取健康档案版本
  getHealthRecordVersion: (recordId, versionNumber) => api.get(`/health-records/version/${recordId}/${versionNumber}`),
  // 获取健康档案统计信息
  getHealthRecordStats: (patientId) => api.get(`/health-records/stats/${patientId}`),
  
  // 随访记录相关接口
  // 创建随访记录
  createFollowUp: (followUpData) => api.post('/health-records/followups', followUpData),
  // 获取随访记录详情
  getFollowUpById: (followUpId) => api.get(`/health-records/followups/${followUpId}`),
  // 更新随访记录
  updateFollowUp: (followUpId, followUpData) => api.put(`/health-records/followups/${followUpId}`, followUpData),
  // 获取患者的随访记录列表
  getFollowUps: (patientId, params) => api.get(`/health-records/followups?patient_id=${patientId}`, { params }),
  // 完成随访
  completeFollowUp: (followUpId, data) => api.post(`/health-records/followups/${followUpId}/complete`, data),
  // 取消随访
  cancelFollowUp: (followUpId, data) => api.post(`/health-records/followups/${followUpId}/cancel`, data),
  // 重新安排随访
  rescheduleFollowUp: (followUpId, data) => api.post(`/health-records/followups/${followUpId}/reschedule`, data),
  // 获取即将到来的随访
  getUpcomingFollowUps: (patientId, days) => api.get(`/health-records/followups/upcoming`, { params: { patient_id: patientId, days } }),
  // 获取与健康档案关联的随访记录
  getRelatedFollowUps: (recordId) => api.get(`/health-records/related-followups/${recordId}`),
  
  // 健康数据相关接口
  // 创建健康数据
  createHealthData: (data) => api.post('/health-records/health-data', data),
  // 获取健康数据详情
  getHealthDataById: (dataId) => api.get(`/health-records/health-data/${dataId}`),
  // 获取患者的健康数据列表
  getHealthData: (patientId, params) => api.get(`/health-records/health-data?patient_id=${patientId}`, { params }),
  // 创建生命体征记录
  createVitalSign: (data) => api.post('/health-records/vital-signs', data),
  // 创建实验室检查结果
  createLabResult: (data) => api.post('/health-records/lab-results', data),
  // 获取医疗时间线
  getMedicalTimeline: (patientId, params) => api.get(`/health-records/timeline/${patientId}`, { params }),
  
  // 用户仪表盘配置相关接口
  // 获取用户仪表盘配置
  getUserDashboardConfig: (userId) => api.get(`/users/${userId}/dashboard-config`),
  // 保存用户仪表盘配置
  saveUserDashboardConfig: (userId, configData) => api.put(`/users/${userId}/dashboard-config`, configData),
  // 重置用户仪表盘配置为默认值
  resetUserDashboardConfig: (userId) => api.post(`/users/${userId}/dashboard-config/reset`),
  
  // 设备管理相关接口
  // 获取用户绑定的设备列表
  getUserDevices: (userId) => api.get(`/users/${userId}/devices`),
  // 绑定新设备
  bindUserDevice: (userId, deviceData) => api.post(`/users/${userId}/devices`, deviceData),
  // 解绑设备
  unbindUserDevice: (userId, deviceId) => api.delete(`/users/${userId}/devices/${deviceId}`),
  // 获取设备数据
  getDeviceData: (deviceId, params) => api.get(`/devices/${deviceId}/data`, { params }),
  // 同步设备数据
  syncDeviceData: (deviceId) => api.post(`/devices/${deviceId}/sync`),
  // 获取设备状态
  getDeviceStatus: (deviceId) => api.get(`/devices/${deviceId}/status`),
  // 配置设备
  configureDevice: (deviceId, configData) => api.put(`/devices/${deviceId}/config`, configData),
};

export { apiService };
export default api; 