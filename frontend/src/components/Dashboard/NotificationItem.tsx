import React from 'react';
import { 
  ListItem, 
  ListItemText, 
  ListItemAvatar, 
  Avatar, 
  Typography, 
  Box 
} from '@mui/material';
import { 
  Notifications as AlertIcon,
  Event as EventIcon,
  Assignment as AssignmentIcon,
  Healing as HealingIcon,
  Chat as MessageIcon
} from '@mui/icons-material';
import { formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { NotificationType, Priority } from '../../constants/enums';
import { STATUS_COLORS } from '../../constants/colors';
import { StatusChip } from '../common';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  priority?: Priority;
}

interface NotificationItemProps {
  notification: Notification;
  onClick?: (id: string) => void;
}

const NotificationItem: React.FC<NotificationItemProps> = ({ notification, onClick }) => {
  // 根据通知类型获取图标
  const getIcon = () => {
    switch (notification.type) {
      case NotificationType.ALERT:
        return <AlertIcon />;
      case NotificationType.REMINDER:
        return <EventIcon />;
      case NotificationType.TASK:
        return <AssignmentIcon />;
      case NotificationType.REHAB:
        return <HealingIcon />;
      case NotificationType.MESSAGE:
        return <MessageIcon />;
      default:
        return <AlertIcon />;
    }
  };

  // 根据优先级获取颜色
  const getPriorityColor = () => {
    switch (notification.priority) {
      case Priority.HIGH:
        return STATUS_COLORS.error;
      case Priority.MEDIUM:
        return STATUS_COLORS.warning;
      case Priority.LOW:
      default:
        return STATUS_COLORS.pending;
    }
  };

  // 格式化时间为相对时间
  const formatTime = (timestamp: string) => {
    return formatDistanceToNow(new Date(timestamp), { 
      addSuffix: true,
      locale: zhCN 
    });
  };

  return (
    <ListItem 
      alignItems="flex-start" 
      sx={{ 
        opacity: notification.read ? 0.7 : 1,
        bgcolor: notification.read ? 'transparent' : 'action.hover',
        borderLeft: notification.priority ? `4px solid ${getPriorityColor()}` : 'none',
        '&:hover': { bgcolor: 'action.selected' }
      }}
      onClick={() => onClick && onClick(notification.id)}
    >
      <ListItemAvatar>
        <Avatar sx={{ bgcolor: notification.read ? 'action.disabledBackground' : 'primary.main' }}>
          {getIcon()}
        </Avatar>
      </ListItemAvatar>
      <ListItemText
        primary={
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography component="span" variant="subtitle2" sx={{ mr: 1 }}>
              {notification.title}
            </Typography>
            {!notification.read && (
              <StatusChip 
                label="新" 
                small 
                color="primary" 
              />
            )}
          </Box>
        }
        secondary={
          <>
            <Typography component="span" variant="body2" color="text.primary">
              {notification.message}
            </Typography>
            <Typography component="div" variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
              {formatTime(notification.timestamp)}
            </Typography>
          </>
        }
      />
    </ListItem>
  );
};

export default NotificationItem; 