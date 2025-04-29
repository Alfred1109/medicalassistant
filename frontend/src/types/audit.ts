// 审计日志类型定义

/**
 * 审计日志操作类型枚举
 */
export enum AuditAction {
  ACCESS = 'access',
  LOGIN = 'login',
  LOGOUT = 'logout',
  CREATE = 'create',
  UPDATE = 'update',
  DELETE = 'delete',
  GRANT = 'grant',
  REVOKE = 'revoke',
  QUERY = 'query',
  VIEW = 'view',
  MODIFY = 'modify'
}

/**
 * 审计日志资源类型枚举
 */
export enum AuditResourceType {
  USER = 'user',
  PATIENT = 'patient',
  DOCTOR = 'doctor',
  DEVICE = 'device',
  REHAB_PLAN = 'rehab_plan',
  EXERCISE = 'exercise',
  ASSESSMENT = 'assessment',
  REPORT = 'report',
  SETTINGS = 'settings',
  ACCESS_CONTROL = 'access_control',
  SYSTEM = 'system'
}

/**
 * 审计日志状态类型
 */
export type AuditStatus = 'success' | 'failure';

/**
 * 审计日志实体接口
 */
export interface AuditLog {
  id: string;
  user_id: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  ip_address?: string;
  details?: any;
  status: AuditStatus;
  created_at: string;
}

/**
 * 审计日志过滤器接口
 */
export interface AuditLogFilter {
  user_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
}

/**
 * 审计日志分页结果接口
 */
export interface AuditLogPaginatedResult {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
}

// 审计日志分页响应
export interface AuditLogList {
  total: number;
  items: AuditLog[];
} 