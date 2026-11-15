import { formatAppDate } from '../utils/dateTime';
import { useState, useEffect } from 'react';
import dashboardService, { 
  DashboardData, 
  HealthMetric, 
  TodoItem, 
  PublishedRehabPlans,
  Notification
} from '../services/dashboardService';

interface DashboardState {
  loading: boolean;
  error: string | null;
  healthMetrics: HealthMetric[];
  todoItems: TodoItem[];
  publishedRehabPlans: PublishedRehabPlans | null;
  notifications: Notification[];
  notificationsLoading: boolean;
  notificationsError: string | null;
}

export const useDashboard = () => {
  const [state, setState] = useState<DashboardState>({
    loading: true,
    error: null,
    healthMetrics: [],
    todoItems: [],
    publishedRehabPlans: null,
    notifications: [],
    notificationsLoading: true,
    notificationsError: null
  });

  // 获取仪表盘所有数据
  const fetchDashboardData = async () => {
    try {
      setState(prev => ({ ...prev, loading: true, error: null }));
      const data = await dashboardService.getDashboardData();
      setState(prev => ({
        ...prev,
        loading: false,
        healthMetrics: data.health_metrics,
        todoItems: data.todo_items,
        publishedRehabPlans: data.published_rehab_plans
      }));
    } catch (error) {
      console.error('获取仪表盘数据失败:', error);
      setState(prev => ({ 
        ...prev, 
        loading: false, 
        error: error instanceof Error ? error.message : '获取数据失败'
      }));
    }
  };

  // 获取通知数据
  const fetchNotifications = async (limit: number = 5) => {
    try {
      setState(prev => ({ ...prev, notificationsLoading: true, notificationsError: null }));
      const notifications = await dashboardService.getNotifications(limit);
      
      // 处理通知时间格式
      const processedNotifications = notifications.map(notification => {
        const formattedTime = formatAppDate(notification.time, 'notification', { invalid: 'NaN-NaN-NaN' });
        
        return {
          ...notification,
          time: formattedTime
        };
      });
      
      setState(prev => ({
        ...prev,
        notificationsLoading: false,
        notifications: processedNotifications
      }));
    } catch (error) {
      console.error('获取通知数据失败:', error);
      setState(prev => ({ 
        ...prev, 
        notificationsLoading: false, 
        notificationsError: error instanceof Error ? error.message : '获取通知失败'
      }));
    }
  };

  // 标记通知为已读
  const markNotificationAsRead = async (notificationId: string) => {
    try {
      await dashboardService.markNotificationAsRead(notificationId);
      setState(prev => ({
        ...prev,
        notifications: prev.notifications.map(notification => 
          notification.id === notificationId 
            ? { ...notification, read: true } 
            : notification
        )
      }));
    } catch (error) {
      console.error('标记通知已读失败:', error);
    }
  };

  // 标记所有通知为已读
  const markAllNotificationsAsRead = async () => {
    try {
      await dashboardService.markAllNotificationsAsRead();
      setState(prev => ({
        ...prev,
        notifications: prev.notifications.map(notification => ({ ...notification, read: true }))
      }));
    } catch (error) {
      console.error('标记所有通知已读失败:', error);
    }
  };

  // 初始化加载
  useEffect(() => {
    fetchDashboardData();
    fetchNotifications();
  }, []);

  return {
    ...state,
    refreshDashboard: fetchDashboardData,
    refreshNotifications: fetchNotifications,
    markNotificationAsRead,
    markAllNotificationsAsRead
  };
};

export default useDashboard;
