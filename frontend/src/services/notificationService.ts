import api from './api';

// 通知类型定义
export interface Notification {
  id: string;
  title: string;
  content: string;
  type: 'message' | 'appointment' | 'task' | 'system' | 'health_alert' | 'followup';
  timestamp: Date | string;
  isRead: boolean;
  priority?: 'normal' | 'important' | 'urgent';
  sender?: {
    id: string;
    name: string;
    avatar?: string;
  };
  relatedLink?: string;
  metadata?: Record<string, any>;
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

// API基础URL
const API_URL = process.env.REACT_APP_API_URL || '/api';

// 创建通知API服务
export const notificationApi = {
  // 获取通知列表
  async getNotifications(params?: { 
    page?: number;
    limit?: number;
    type?: string;
    isRead?: boolean;
  }) {
    try {
      const response = await api.get('/notifications', { params });
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
  },
  
  // 获取通知设置
  async getSettings() {
    try {
      const response = await api.get('/notifications/settings');
      return response.data;
    } catch (error) {
      console.error('获取通知设置失败:', error);
      throw error;
    }
  },
  
  // 更新通知设置
  async updateSettings(settings: NotificationSettings) {
    try {
      const response = await api.put('/notifications/settings', settings);
      return response.data;
    } catch (error) {
      console.error('更新通知设置失败:', error);
      throw error;
    }
  }
}; 