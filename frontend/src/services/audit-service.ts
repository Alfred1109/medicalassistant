import axios from 'axios';
import { AuditLog, AuditLogFilter, AuditLogList } from '../types/audit';

// 基础URL - 确保与后端路由匹配
const BASE_URL = '/api/audit-logs';

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
    // 构建查询参数
    const params = new URLSearchParams();
    
    // 添加过滤条件参数
    if (filter.user_id) params.append('user_id', filter.user_id);
    if (filter.action) params.append('action', filter.action);
    if (filter.resource_type) params.append('resource_type', filter.resource_type);
    if (filter.resource_id) params.append('resource_id', filter.resource_id);
    if (filter.status) params.append('status', filter.status);
    if (filter.start_date) params.append('start_date', filter.start_date);
    if (filter.end_date) params.append('end_date', filter.end_date);
    
    // 添加分页和排序参数
    params.append('skip', (page * limit).toString());
    params.append('limit', limit.toString());
    params.append('sort_by', sortBy);
    params.append('sort_order', sortOrder.toString());
    
    try {
      const response = await axios({
        method: 'GET',
        url: `${BASE_URL}`,
        params: params
      });
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
      const response = await axios({
        method: 'GET',
        url: `${BASE_URL}/${id}`
      });
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
    try {
      const response = await axios({
        method: 'GET',
        url: `${BASE_URL}/user/${userId}/recent`,
        params: { limit }
      });
      return response.data;
    } catch (error) {
      console.error('获取用户最近审计日志失败:', error);
      throw error;
    }
  }
}; 