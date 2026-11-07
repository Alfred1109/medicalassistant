import api from './api'; // 使用配置好的api实例
import { AuditLog, AuditLogFilter, AuditLogList } from '../types/audit';

// 无需添加前导斜杠，因为api实例已配置baseURL
const BASE_URL = 'audit-logs';
const SORT_FIELDS = new Set(['created_at', 'user_id', 'action', 'resource_type', 'resource_id', 'status']);

/**
 * 审计日志服务类
 * 提供审计日志相关API调用
 */
export const AuditService = {
  /**
   * 获取审计日志列表
   * @param filter 过滤条件
   * @param page 页码
   * @param limit 每页数量
   * @param sortBy 排序字段
   * @param sortOrder 排序顺序 (-1降序, 1升序)
   * @returns 审计日志列表
   */
  async getAuditLogs(
    filter: AuditLogFilter = {}, 
    page: number = 0, 
    limit: number = 50,
    sortBy: string = 'created_at',
    sortOrder: number = -1
  ): Promise<AuditLogList> {
    if (!Number.isInteger(page) || page < 0 || !Number.isInteger(limit) || limit < 1 || limit > 100) {
      throw new RangeError('审计日志分页参数无效');
    }
    if (!SORT_FIELDS.has(sortBy) || (sortOrder !== -1 && sortOrder !== 1)) {
      throw new RangeError('审计日志排序参数无效');
    }
    try {
      // 构建查询参数
      const params: Record<string, string | number> = {
        skip: page * limit,
        limit,
        sort_by: sortBy,
        sort_order: sortOrder
      };
      
      // 添加过滤条件参数
      if (filter.user_id) params.user_id = filter.user_id;
      if (filter.action) params.action = filter.action;
      if (filter.resource_type) params.resource_type = filter.resource_type;
      if (filter.resource_id) params.resource_id = filter.resource_id;
      if (filter.status) params.status = filter.status;
      if (filter.start_date) params.start_date = filter.start_date;
      if (filter.end_date) params.end_date = filter.end_date;
      
      const response = await api.get<AuditLogList>(`${BASE_URL}/`, { params });
      return response.data;
    } catch (error) {
      console.error('获取审计日志失败:', error);
      throw error;
    }
  },
  
  /**
   * 获取审计日志详情
   * @param id 审计日志ID
   * @returns 审计日志详情
   */
  async getAuditLogById(id: string): Promise<AuditLog> {
    try {
      const response = await api.get<AuditLog>(`${BASE_URL}/${encodeURIComponent(id)}`);
      return response.data;
    } catch (error) {
      console.error('获取审计日志详情失败:', error);
      throw error;
    }
  },
  
  /**
   * 获取用户最近的审计日志
   * @param userId 用户ID
   * @param limit 返回数量
   * @returns 用户最近的审计日志
   */
  async getRecentLogsByUser(userId: string, limit: number = 10): Promise<AuditLog[]> {
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
      throw new RangeError('最近审计日志条数必须为1到50之间的整数');
    }
    try {
      const response = await api.get<AuditLog[]>(`${BASE_URL}/user/${encodeURIComponent(userId)}/recent`, {
        params: { limit }
      });
      return response.data;
    } catch (error) {
      console.error('获取用户最近审计日志失败:', error);
      throw error;
    }
  }
};
