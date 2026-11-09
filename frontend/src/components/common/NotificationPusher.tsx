import React, { useEffect, useState } from 'react';
import { Snackbar, Alert, Badge, IconButton, Typography, Box, useTheme } from '@mui/material';
import NotificationsIcon from '@mui/icons-material/Notifications';
import CloseIcon from '@mui/icons-material/Close';
import useWebSocket from '../../hooks/useWebSocket';
import { API_BASE_URL } from '../../config/api';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import { notificationApi } from '../../services/notificationService';

/**
 * 通知 WS 地址推导（与 chatWsService.resolveChatWsBaseUrl 同规则）：
 * 后端通知端点挂在应用根 /ws/notifications（websockets.py:301），
 * 不在 /api 前缀下，因此从 API_BASE_URL 去掉末尾 /api 得基址；
 * 鉴权由共享 transport 按登录模式处理；OIDC 使用同源 Cookie。
 */
function resolveNotificationWsUrl(): string {
  const withoutApi = API_BASE_URL.replace(/\/api\/?$/, '');
  const base = /^https?:\/\//i.test(withoutApi)
    ? withoutApi.replace(/^http/i, 'ws')
    : `${window.location.origin.replace(/^http/, 'ws')}${withoutApi}`;
  return `${base}/ws/notifications`;
}

interface NotificationPusherProps {
  onNotificationClick?: () => void;
}

/**
 * 外层组件：经过服务端验证的业务用户保护。
 * 未登录时直接不渲染，避免 useWebSocket 以无效身份
 * 连接 /ws/notifications 被后端拒绝后进入无意义重连循环。
 * hooks 规则不允许条件调用，故拆成「守卫壳 + 已连接子组件」两层。
 */
const NotificationPusher: React.FC<NotificationPusherProps> = (props) => {
  const { token, user, mode } = useSelector((state: RootState) => state.auth);
  if (!user || (mode !== 'oidc' && !token)) return null;
  return <ConnectedNotificationPusher key={`${user.id}:${user.role}`} {...props} />;
};

interface ConnectedNotificationPusherProps extends NotificationPusherProps {

}

const ConnectedNotificationPusher: React.FC<ConnectedNotificationPusherProps> = ({
  onNotificationClick
}) => {
  const theme = useTheme();
  const [notification, setNotification] = useState<{
    open: boolean;
    message: string;
    type: 'success' | 'info' | 'warning' | 'error';
    duration: number;
  } | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);

  // 初始拉取真实未读数（后端 GET /api/notifications/unread/count 直接返回 int）
  useEffect(() => {
    let cancelled = false;
    const refreshCount = () => { notificationApi.getUnreadCount()
      .then((count) => {
        if (!cancelled && typeof count === 'number') setUnreadCount(count);
      })
      .catch((error) => {
        // 静默降级：拉取失败仅保留徽标为 0，不打扰用户
        console.error('获取未读通知数量失败:', error);
      }); };
    refreshCount();
    window.addEventListener('notifications:changed', refreshCount);
    return () => { cancelled = true; window.removeEventListener('notifications:changed', refreshCount); };
  }, []);

  // WebSocket连接，用于接收实时通知（后端 /ws/notifications）
  const { lastMessage, isConnected } = useWebSocket(resolveNotificationWsUrl());

  // 处理收到的WebSocket消息
  useEffect(() => {
    if (lastMessage) {
      try {
        const data = JSON.parse(lastMessage.data);
        // 后端广播形状：{"type":"notification","data":{content,priority,...}}（websockets.py send_notification）
        if (data.type === 'notification' && data.data) {
          const priority = data.data.priority;
          setNotification({
            open: true,
            message: data.data.content,
            type: priority === 'urgent' ? 'error' : priority === 'high' ? 'warning' : 'info',
            duration: 5000
          });
          // 后端随后会补发 notification_count，这里本地先 +1 保证徽标即时性
          setUnreadCount(count => count + 1);
        }
        // 后端在通知落库后推送真实未读数：{"type":"notification_count","count":N}
        if (data.type === 'notification_count' && typeof data.count === 'number') {
          setUnreadCount(data.count);
        }
      } catch (error) {
        console.error('解析通知消息失败:', error);
      }
    }
  }, [lastMessage]);

  // 关闭通知
  const handleClose = () => {
    setNotification(prev => prev ? { ...prev, open: false } : null);
  };

  return (
    <>
      {/* 通知图标和未读数量（断连时图标变灰静默降级，不弹提示） */}
      <Box position="relative" display="inline-block">
        <IconButton
          color="inherit"
          onClick={onNotificationClick}
          sx={{
            transition: 'all 0.3s',
            '&:hover': { transform: 'scale(1.1)' }
          }}
        >
          <Badge
            badgeContent={unreadCount}
            color="error"
            sx={{
              '& .MuiBadge-badge': {
                animation: unreadCount > 0 ? `${theme.transitions.create(['transform'], {
                  duration: theme.transitions.duration.shorter,
                  easing: theme.transitions.easing.easeInOut,
                })} 0.5s ease-in-out` : 'none',
              }
            }}
          >
            <NotificationsIcon
              sx={{
                color: isConnected ? theme.palette.primary.main : theme.palette.text.secondary
              }}
            />
          </Badge>
        </IconButton>
      </Box>

      {/* 通知弹窗 */}
      {notification && (
        <Snackbar
          open={notification.open}
          autoHideDuration={notification.duration}
          onClose={handleClose}
          anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
          sx={{ mt: 7 }}
        >
          <Alert
            onClose={handleClose}
            severity={notification.type}
            sx={{
              width: '100%',
              alignItems: 'center'
            }}
            action={
              <IconButton
                size="small"
                aria-label="close"
                color="inherit"
                onClick={handleClose}
              >
                <CloseIcon fontSize="small" />
              </IconButton>
            }
          >
            <Typography variant="body2">{notification.message}</Typography>
          </Alert>
        </Snackbar>
      )}
    </>
  );
};

export default NotificationPusher;
