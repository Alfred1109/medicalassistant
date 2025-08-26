import React, { useState, useEffect } from 'react';
import { Box, Typography, Container, Paper, CircularProgress, Alert } from '@mui/material';
import NotificationCenter from '../components/Patient/NotificationCenter';
import api from '../services/api';
import { Notification } from '../services/notificationService';
import { useNavigate } from 'react-router-dom';
import { ROUTES, STORAGE_KEYS } from '../config/constants';

/**
 * 通知页面
 * 集成NotificationCenter组件，提供通知数据和操作
 */
const NotificationsPage: React.FC = () => {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // 获取通知列表
  const fetchNotifications = async () => {
    setLoading(true);
    setError(null);
    
    // 检查token是否存在
    const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
    if (!token) {
      console.log('用户未登录，请先登录');
      setError('您需要登录才能查看通知');
      setLoading(false);
      // 可选：重定向到登录页
      // navigate(ROUTES.LOGIN);
      return;
    }
    
    try {
      // 使用api服务而不是直接使用axios，api服务会自动添加token
      const response = await api.get('notifications');
      setNotifications(response.data || []);
    } catch (error) {
      console.error('获取通知列表失败:', error);
      setError('获取通知列表失败，请稍后重试');
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  };

  // 标记通知为已读
  const handleMarkAsRead = async (notificationId: string) => {
    try {
      await api.put(`notifications/${notificationId}/read`);
      setNotifications(prevNotifications =>
        prevNotifications.map(notification =>
          notification.id === notificationId
            ? { ...notification, isRead: true }
            : notification
        )
      );
    } catch (error) {
      console.error('标记通知已读失败:', error);
    }
  };

  // 标记所有通知为已读
  const handleMarkAllAsRead = async () => {
    try {
      await api.put('notifications/read-all');
      setNotifications(prevNotifications =>
        prevNotifications.map(notification => ({ ...notification, isRead: true }))
      );
    } catch (error) {
      console.error('标记所有通知已读失败:', error);
    }
  };

  // 删除通知
  const handleDeleteNotification = async (notificationId: string) => {
    try {
      await api.delete(`notifications/${notificationId}`);
      setNotifications(prevNotifications =>
        prevNotifications.filter(notification => notification.id !== notificationId)
      );
    } catch (error) {
      console.error('删除通知失败:', error);
    }
  };

  // 清除所有通知
  const handleClearAll = async () => {
    try {
      await api.delete('notifications/clear-all');
      setNotifications([]);
    } catch (error) {
      console.error('清除所有通知失败:', error);
    }
  };

  // 初始加载通知
  useEffect(() => {
    console.log('NotificationsPage组件已加载');
    fetchNotifications();
  }, []);

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          通知中心
        </Typography>
        
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        
        <Box sx={{ mt: 3 }}>
          <NotificationCenter
            notifications={notifications}
            loading={loading}
            onMarkAsRead={handleMarkAsRead}
            onMarkAllAsRead={handleMarkAllAsRead}
            onDeleteNotification={handleDeleteNotification}
            onClearAll={handleClearAll}
            onRefresh={fetchNotifications}
          />
        </Box>
      </Paper>
    </Container>
  );
};

export default NotificationsPage; 