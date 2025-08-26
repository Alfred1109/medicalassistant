import { AuditLog, AuditLogFilter, AuditLogPaginatedResult } from '../types/audit';
import { apiRequest } from '../utils/apiUtils';

const BASE_URL = '/api/v1/admin/audit-logs';

/**
 * 获取审计日志列表
 * @param page 页码
 * @param pageSize 每页数量
 * @param filter 过滤条件
 * @returns 分页审计日志列表
 */
export const getAuditLogs = async (
  page: number = 1, 
  pageSize: number = 10, 
  filter: AuditLogFilter = {}
): Promise<AuditLogPaginatedResult> => {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
    ...Object.entries(filter)
      .filter(([_, value]) => value !== undefined && value !== '')
      .reduce((acc, [key, value]) => ({ ...acc, [key]: value }), {})
  });

  return apiRequest<AuditLogPaginatedResult>(`${BASE_URL}?${params.toString()}`);
};

/**
 * 获取单个审计日志详情
 * @param id 审计日志ID
 * @returns 审计日志详情
 */
export const getAuditLogById = async (id: string): Promise<AuditLog> => {
  return apiRequest<AuditLog>(`${BASE_URL}/${id}`);
};

/**
 * 导出审计日志为CSV
 * @param filter 过滤条件
 * @returns 下载链接
 */
export const exportAuditLogs = async (filter: AuditLogFilter = {}): Promise<string> => {
  const params = new URLSearchParams(
    Object.entries(filter)
      .filter(([_, value]) => value !== undefined && value !== '')
      .reduce((acc, [key, value]) => ({ ...acc, [key]: value }), {})
  );

  return apiRequest<string>(`${BASE_URL}/export?${params.toString()}`);
};

/**
 * 获取审计日志统计数据
 * @param filter 过滤条件
 * @returns 统计数据
 */
export const getAuditLogStats = async (filter: AuditLogFilter = {}): Promise<any> => {
  const params = new URLSearchParams(
    Object.entries(filter)
      .filter(([_, value]) => value !== undefined && value !== '')
      .reduce((acc, [key, value]) => ({ ...acc, [key]: value }), {})
  );

  return apiRequest<any>(`${BASE_URL}/stats?${params.toString()}`);
}; 