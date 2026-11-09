import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Typography, Container, Paper, Alert, Button, Stack } from '@mui/material';
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import type { RootState } from '../store';
import NotificationCenter from '../components/Patient/NotificationCenter';
import { Notification, notificationApi } from '../services/notificationService';
import { notificationTarget } from '../utils/notificationTarget';

const PAGE_SIZE = 20;
const notifyChanged = () => window.dispatchEvent(new Event('notifications:changed'));

/**
 * 通知页面
 * 集成NotificationCenter组件，提供通知数据和操作
 */
const NotificationsPage: React.FC = () => {
  const actor = useSelector((state: RootState) => state.auth.user);
  return <NotificationWorkspace key={`${actor?.id}:${actor?.role}`} role={actor?.role} />;
};

const NotificationWorkspace: React.FC<{ role?: string }> = ({ role }) => {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const request = useRef(0);

  // 获取通知列表
  const fetchNotifications = useCallback(async () => {
    const current = ++request.current;
    setLoading(true);
    setError(null);
    
    try {
      const data = await notificationApi.getNotifications({ skip: page * PAGE_SIZE, limit: PAGE_SIZE });
      if (request.current === current) setNotifications(data || []);
    } catch (error) {
      console.error('获取通知列表失败:', error);
      if (request.current === current) { setError('获取通知列表失败，请稍后重试'); setNotifications([]); }
    } finally {
      if (request.current === current) setLoading(false);
    }
  }, [page]);

  // 标记通知为已读
  const handleMarkAsRead = async (notificationId: string) => {
    try {
      setOperationError(null);
      await notificationApi.markAsRead(notificationId);
      setNotifications(prevNotifications =>
        prevNotifications.map(notification =>
          notification.id === notificationId
            ? { ...notification, read: true }
            : notification
        )
      );
      notifyChanged();
    } catch (error) {
      console.error('标记通知已读失败:', error);
      setOperationError('标记通知已读失败，请重试。');
      throw error;
    }
  };

  // 标记所有通知为已读
  const handleMarkAllAsRead = async () => {
    try {
      setOperationError(null);
      await notificationApi.markAllAsRead();
      setNotifications(prevNotifications =>
        prevNotifications.map(notification => ({ ...notification, read: true }))
      );
      notifyChanged();
    } catch (error) {
      console.error('标记所有通知已读失败:', error);
      setOperationError('全部标记为已读失败，请重试。');
      throw error;
    }
  };

  // 删除通知
  const handleDeleteNotification = async (notificationId: string) => {
    try {
      setOperationError(null);
      await notificationApi.deleteNotification(notificationId);
      setNotifications(prevNotifications =>
        prevNotifications.filter(notification => notification.id !== notificationId)
      );
      notifyChanged();
    } catch (error) {
      console.error('删除通知失败:', error);
      setOperationError('删除通知失败，请重试。');
      throw error;
    }
  };

  // 清除所有通知
  const handleClearAll = async () => {
    try {
      setOperationError(null);
      await notificationApi.clearAllNotifications();
      setNotifications([]);
      setPage(0);
      notifyChanged();
    } catch (error) {
      console.error('清除所有通知失败:', error);
      setOperationError('清空通知失败，请重试。');
      throw error;
    }
  };

  // 初始加载通知
  useEffect(() => {
    fetchNotifications();
    return () => { request.current += 1; };
  }, [fetchNotifications]);

  const openNotification = (notification: Notification) => {
    const target = notificationTarget(notification, role);
    if (target) navigate(target);
    else if (notification.notification_type === 'followup') setOperationError('此提醒没有可打开的随访，请联系负责的医护人员。');
  };

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          通知中心
        </Typography>
        
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} action={<Button onClick={fetchNotifications}>重试</Button>}>
            {error}
          </Alert>
        )}
        {operationError && <Alert severity="error" sx={{ mb: 2 }}>{operationError}</Alert>}
        
        <Box sx={{ mt: 3 }}>
          <NotificationCenter
            notifications={notifications}
            loading={loading}
            onMarkAsRead={handleMarkAsRead}
            onMarkAllAsRead={handleMarkAllAsRead}
            onDeleteNotification={handleDeleteNotification}
            onClearAll={handleClearAll}
            onRefresh={fetchNotifications}
            onNotificationClick={openNotification}
          />
        </Box>
        <Stack direction="row" spacing={2} justifyContent="flex-end" alignItems="center" sx={{ mt: 2 }}>
          <Button disabled={loading || page === 0} onClick={() => setPage(value => value - 1)}>上一页</Button>
          <Typography variant="body2">第 {page + 1} 页</Typography>
          <Button disabled={loading || notifications.length < PAGE_SIZE} onClick={() => setPage(value => value + 1)}>下一页</Button>
        </Stack>
      </Paper>
    </Container>
  );
};

export default NotificationsPage;
