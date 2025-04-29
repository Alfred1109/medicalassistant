// API基础URL
export const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

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

// 分页参数
export const DEFAULT_PAGE_SIZE = 10;

// 本地存储键名
export const STORAGE_KEYS = {
  AUTH_TOKEN: 'auth_token',
  USER_INFO: 'user_info',
  THEME_PREFERENCE: 'theme_preference',
  NOTIFICATION_SETTINGS: 'notification_settings'
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
  INFO: 'info',
  SUCCESS: 'success',
  WARNING: 'warning',
  ERROR: 'error'
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