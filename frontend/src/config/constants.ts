// API配置
export const API_BASE_URL = 'http://localhost:5502/api';

// 文件上传限制大小（单位：字节）
export const MAX_UPLOAD_FILE_SIZE = 5 * 1024 * 1024; // 5MB

// 文件上传允许的MIME类型
export const ALLOWED_FILE_TYPES = [
  'image/jpeg',
  'image/png',
  'image/gif',
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
];

// 分页配置
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 10,
  DEFAULT_PAGE: 1
};

// 本地存储键名
export const STORAGE_KEYS = {
  TOKEN: 'token',
  USER: 'user',
  PREFERENCES: 'preferences'
};

// 路由路径
export const ROUTES = {
  HOME: '/',
  LOGIN: '/login',
  REGISTER: '/register',
  PATIENT: {
    DASHBOARD: '/patient/dashboard',
    HEALTH_RECORDS: '/patient/health-records',
    REHAB_PLANS: '/patient/rehab-plans',
    HEALTH_DATA: '/patient/health-data',
    MESSAGES: '/patient/messages',
    DOCUMENTS: '/patient/documents'
  },
  DOCTOR: {
    DASHBOARD: '/doctor/dashboard',
    PATIENTS: '/doctor/patients',
    REHAB_PLANS: '/doctor/rehab-plans',
    FOLLOW_UPS: '/doctor/follow-ups',
    MESSAGES: '/doctor/messages'
  },
  HEALTH_MANAGER: {
    DASHBOARD: '/health-manager/dashboard',
    PATIENTS: '/health-manager/patients',
    HEALTH_DATA: '/health-manager/health-data',
    REHAB_PLANS: '/health-manager/rehab-plans',
    MESSAGES: '/health-manager/messages'
  },
  ADMIN: {
    DASHBOARD: '/admin/dashboard',
    USERS: '/admin/users',
    SETTINGS: '/admin/settings',
    PERMISSIONS: '/admin/permissions'
  }
};

// HTTP状态码
export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  INTERNAL_SERVER_ERROR: 500
};

// 通知类型
export const NOTIFICATION_TYPES = {
  GENERAL: 'general',
  MEDICAL: 'medical',
  APPOINTMENT: 'appointment',
  SYSTEM: 'system'
};

// 通知优先级
export const NOTIFICATION_PRIORITIES = {
  LOW: 'low',
  NORMAL: 'normal',
  HIGH: 'high',
  URGENT: 'urgent'
};

// 健康指标状态
export const HEALTH_METRIC_STATUS = {
  NORMAL: 'normal',
  GOOD: 'good',
  WARNING: 'warning',
  DANGER: 'danger'
};

// 用户角色
export const USER_ROLES = {
  PATIENT: 'patient',
  DOCTOR: 'doctor',
  HEALTH_MANAGER: 'healthManager',
  ADMIN: 'admin'
};

// 在线状态
export const ONLINE_STATUS = {
  ONLINE: 'online',
  OFFLINE: 'offline',
  AWAY: 'away',
  BUSY: 'busy'
}; 