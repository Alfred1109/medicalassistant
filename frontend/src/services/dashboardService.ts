import apiClient from './apiClient';
import { API_BASE_URL } from '../config/constants';

export interface HealthMetric {
  id: string;
  name: string;
  value: string;
  unit: string;
  status: string;
  trend: string;
  timestamp: string;
  user_id: string;
}

export interface TodoItem {
  id: string;
  title: string;
  description: string;
  due: string;
  completed: boolean;
  important: boolean;
  user_id: string;
  timestamp: string;
}

export interface Exercise {
  name: string;
  completed: boolean;
}

export interface RehabProgress {
  id: string;
  plan: string;
  progress: number;
  next_session: string;
  user_id: string;
  doctor_id: string;
  exercises: Exercise[];
  timestamp: string;
}

export interface DashboardData {
  health_metrics: HealthMetric[];
  todo_items: TodoItem[];
  rehab_progress: RehabProgress | null;
}

export interface Notification {
  id: string;
  title: string;
  content: string;
  sender_id: string;
  sender_name: string;
  sender_role: string;
  recipient_id: string;
  time: string;
  read: boolean;
  notification_type: string;
  priority: string;
  related_entity_id?: string;
  related_entity_type?: string;
}

const dashboardService = {
  /**
   * 获取仪表盘所有数据
   */
  getDashboardData: (): Promise<DashboardData> => {
    return apiClient.get<DashboardData>('/patients/dashboard-data');
  },
  
  /**
   * 获取健康指标数据
   */
  getHealthMetrics: (): Promise<HealthMetric[]> => {
    return apiClient.get<HealthMetric[]>('/patients/health-metrics');
  },
  
  /**
   * 获取待办事项
   */
  getTodoItems: (): Promise<TodoItem[]> => {
    return apiClient.get<TodoItem[]>('/patients/todo-items');
  },
  
  /**
   * 获取康复进度
   */
  getRehabProgress: (): Promise<RehabProgress> => {
    return apiClient.get<RehabProgress>('/patients/rehab-progress');
  },
  
  /**
   * 获取通知列表
   */
  getNotifications: (limit: number = 5): Promise<Notification[]> => {
    return apiClient.get<Notification[]>(`/notifications?limit=${limit}`);
  },
  
  /**
   * 将通知标记为已读
   */
  markNotificationAsRead: (notificationId: string): Promise<void> => {
    return apiClient.put<void>(`/notifications/${notificationId}/read`);
  },
  
  /**
   * 将所有通知标记为已读
   */
  markAllNotificationsAsRead: (): Promise<void> => {
    return apiClient.put<void>('/notifications/read-all');
  }
};

export default dashboardService; 