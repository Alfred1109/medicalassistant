import React, { useState, useEffect } from 'react';
import { Box, Typography, Container, Paper, CircularProgress } from '@mui/material';
import NotificationCenter from '../components/Patient/NotificationCenter';
import axios from 'axios';
import { Notification } from '../services/notificationService';

/**
 * 通知页面
 * 集成NotificationCenter组件，提供通知数据和操作
 */
const NotificationsPage: React.FC = () => {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // 获取通知列表
  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/api/notifications');
      setNotifications(response.data || []);
    } catch (error) {
      console.error('获取通知列表失败:', error);
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  };

  // 标记通知为已读
  const handleMarkAsRead = async (notificationId: string) => {
    try {
      await axios.put(`/api/notifications/${notificationId}/read`);
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
      await axios.put('/api/notifications/read-all');
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
      await axios.delete(`/api/notifications/${notificationId}`);
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
      await axios.delete('/api/notifications/clear-all');
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