import { useState, useEffect } from 'react';
import dashboardService, { 
  DashboardData, 
  HealthMetric, 
  TodoItem, 
  RehabProgress,
  Notification
} from '../services/dashboardService';

interface DashboardState {
  loading: boolean;
  error: string | null;
  healthMetrics: HealthMetric[];
  todoItems: TodoItem[];
  rehabProgress: RehabProgress | null;
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
    rehabProgress: null,
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
        rehabProgress: data.rehab_progress
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
        const date = new Date(notification.time);
        const now = new Date();
        const diffInDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
        
        let formattedTime;
        if (diffInDays === 0) {
          formattedTime = '今天 ' + date.getHours().toString().padStart(2, '0') + ':' + 
            date.getMinutes().toString().padStart(2, '0');
        } else if (diffInDays === 1) {
          formattedTime = '昨天 ' + date.getHours().toString().padStart(2, '0') + ':' + 
            date.getMinutes().toString().padStart(2, '0');
        } else if (diffInDays < 7) {
          formattedTime = diffInDays + '天前';
        } else {
          formattedTime = date.getFullYear() + '-' + 
            (date.getMonth() + 1).toString().padStart(2, '0') + '-' + 
            date.getDate().toString().padStart(2, '0');
        }
        
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