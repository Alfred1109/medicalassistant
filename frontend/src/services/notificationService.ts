import { API_COLLECTION_PATHS } from '../config/apiPaths';
import api from './api';

// 通知类型定义（与后端 Notification 模型对齐：models/communication.py + notification_service.py）
// 后端实际响应字段为 read / time / notification_type（前端不再维护 isRead/timestamp/type 第二套命名），
// notification_type 当前真实落库值只有 "message"（communication_service 三处触发点），
// 其余类型为预留，界面按未知类型回退到默认图标/文案。
export interface Notification {
  id: string;
  title: string;
  content: string;
  notification_type: string;
  time: string; // ISO 时间字符串（FastAPI 序列化 datetime）
  read: boolean;
  priority?: 'low' | 'normal' | 'high' | 'urgent';
  sender_id?: string;
  sender_name?: string;
  sender_role?: string;
  recipient_id?: string;
  related_entity_id?: string | null;
  related_entity_type?: string | null;
}

export interface NotificationSettings {
  enableEmail: boolean;
  enablePush: boolean;
  enableSystem: boolean;
  notifyOnMessage: boolean;
  notifyOnAppointment: boolean;
  notifyOnTask: boolean;
  notifyOnHealthAlert: boolean;
  notifyOnFollowUp: boolean;
  dailySummary: boolean;
}

// 创建通知API服务
export const notificationApi = {
  // 获取通知列表（后端 GET /api/notifications 参数为 limit / skip / type / read）
  async getNotifications(params?: {
    limit?: number;
    skip?: number;
    type?: string;
    read?: boolean;
  }) {
    try {
      const response = await api.get(API_COLLECTION_PATHS.NOTIFICATIONS, { params });
      return response.data;
    } catch (error) {
      console.error('获取通知失败:', error);
      throw error;
    }
  },
  
  // 标记通知为已读
  async markAsRead(notificationId: string) {
    try {
      const response = await api.put(`/notifications/${notificationId}/read`);
      return response.data;
    } catch (error) {
      console.error('标记通知已读失败:', error);
      throw error;
    }
  },
  
  // 标记所有通知为已读
  async markAllAsRead() {
    try {
      const response = await api.put('/notifications/read-all');
      return response.data;
    } catch (error) {
      console.error('标记所有通知已读失败:', error);
      throw error;
    }
  },
  
  // 删除通知
  async deleteNotification(notificationId: string) {
    try {
      const response = await api.delete(`/notifications/${notificationId}`);
      return response.data;
    } catch (error) {
      console.error('删除通知失败:', error);
      throw error;
    }
  },
  
  // 清空所有通知
  async clearAllNotifications() {
    try {
      const response = await api.delete('/notifications/clear-all');
      return response.data;
    } catch (error) {
      console.error('清空通知失败:', error);
      throw error;
    }
  },
  
  // 获取未读通知数量
  async getUnreadCount() {
    try {
      const response = await api.get('/notifications/unread/count');
      return response.data;
    } catch (error) {
      console.error('获取未读通知数量失败:', error);
      throw error;
    }
  }

  // 注意：后端 /api/notifications 无 GET/PUT /notifications/settings 端点，
  // 通知偏好设置为后端能力待建设，原 getSettings / updateSettings 死链已删除。
};
