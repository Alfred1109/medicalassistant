import React, { useEffect, useState } from 'react';
import { Snackbar, Alert, Badge, IconButton, Typography, Box, useTheme } from '@mui/material';
import NotificationsIcon from '@mui/icons-material/Notifications';
import CloseIcon from '@mui/icons-material/Close';
import useWebSocket from '../../hooks/useWebSocket';

interface NotificationPusherProps {
  onNotificationClick?: () => void;
  unreadCount?: number;
}

const NotificationPusher: React.FC<NotificationPusherProps> = ({
  onNotificationClick,
  unreadCount = 0
}) => {
  const theme = useTheme();
  const [notification, setNotification] = useState<{
    open: boolean;
    message: string;
    type: 'success' | 'info' | 'warning' | 'error';
    duration: number;
  } | null>(null);
  
  // WebSocket连接，用于接收实时通知
  const { lastMessage, isConnected } = useWebSocket(`${import.meta.env.VITE_WS_URL || 'wss://api.example.com'}/notifications/ws`);
  
  // 处理收到的WebSocket消息
  useEffect(() => {
    if (lastMessage) {
      try {
        const data = JSON.parse(lastMessage.data);
        if (data.type === 'notification') {
          setNotification({
            open: true,
            message: data.content,
            type: data.level || 'info',
            duration: data.duration || 5000
          });
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
      {/* 通知图标和未读数量 */}
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