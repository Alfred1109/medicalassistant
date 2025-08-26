import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, Paper, Typography, List, ListItem, ListItemAvatar, 
  ListItemText, Avatar, IconButton, Divider, Badge, Tooltip,
  Button, Menu, MenuItem, ListItemIcon, Tabs, Tab, Chip,
  CircularProgress
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import NotificationsIcon from '@mui/icons-material/Notifications';
import MessageIcon from '@mui/icons-material/Message';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import AssignmentIcon from '@mui/icons-material/Assignment';
import SettingsIcon from '@mui/icons-material/Settings';
import FilterListIcon from '@mui/icons-material/FilterList';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import RefreshIcon from '@mui/icons-material/Refresh';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import WarningIcon from '@mui/icons-material/Warning';
import { useNavigate } from 'react-router-dom';
import { Notification } from '../../services/notificationService';

// 扩展通知类型，包含健康预警和随访提醒
export type NotificationType = 
  'message' | 'appointment' | 'task' | 'system' | 'health_alert' | 'followup';

// 扩展通知优先级
export type NotificationPriority = 'normal' | 'important' | 'urgent';

// 组件属性定义
interface NotificationCenterProps {
  notifications: Notification[];
  loading?: boolean;
  onMarkAsRead?: (notificationId: string) => Promise<void>;
  onMarkAllAsRead?: () => Promise<void>;
  onDeleteNotification?: (notificationId: string) => Promise<void>;
  onClearAll?: () => Promise<void>;
  onRefresh?: () => Promise<void>;
  onNotificationClick?: (notification: Notification) => void;
  onSettingsClick?: () => void;
}

// 通知类型图标映射
const notificationTypeIcons: Record<NotificationType, React.ReactNode> = {
  message: <MessageIcon color="primary" />,
  appointment: <CalendarTodayIcon color="secondary" />,
  task: <AssignmentIcon color="action" />,
  system: <NotificationsIcon color="warning" />,
  health_alert: <HealthAndSafetyIcon color="error" />,
  followup: <NotificationsActiveIcon color="info" />
};

// 通知类型文本映射
const notificationTypeText: Record<NotificationType, string> = {
  message: '消息',
  appointment: '预约',
  task: '任务',
  system: '系统',
  health_alert: '健康预警',
  followup: '随访提醒'
};

// 通知优先级颜色映射
const priorityColorMap: Record<NotificationPriority, string> = {
  normal: 'default',
  important: 'primary',
  urgent: 'error'
};

const NotificationCenter: React.FC<NotificationCenterProps> = ({
  notifications,
  loading = false,
  onMarkAsRead,
  onMarkAllAsRead,
  onDeleteNotification,
  onClearAll,
  onRefresh,
  onNotificationClick,
  onSettingsClick
}) => {
  const navigate = useNavigate();
  const [currentTab, setCurrentTab] = useState<string>('all');
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [filterMenuAnchorEl, setFilterMenuAnchorEl] = useState<null | HTMLElement>(null);
  
  // 处理通知点击
  const handleNotificationClick = (notification: Notification) => {
    if (!notification.isRead && onMarkAsRead) {
      onMarkAsRead(notification.id).catch(err => 
        console.error('Failed to mark notification as read:', err)
      );
    }
    
    if (onNotificationClick) {
      onNotificationClick(notification);
    } else if (notification.relatedLink) {
      navigate(notification.relatedLink);
    }
  };
  
  // 处理标记为已读
  const handleMarkAsRead = async (event: React.MouseEvent, notificationId: string) => {
    event.stopPropagation();
    if (onMarkAsRead) {
      try {
        await onMarkAsRead(notificationId);
      } catch (error) {
        console.error('Failed to mark notification as read:', error);
      }
    }
  };
  
  // 处理删除通知
  const handleDelete = async (event: React.MouseEvent, notificationId: string) => {
    event.stopPropagation();
    if (onDeleteNotification) {
      try {
        await onDeleteNotification(notificationId);
      } catch (error) {
        console.error('Failed to delete notification:', error);
      }
    }
  };
  
  // 打开菜单
  const handleMenuOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
    setAnchorEl(event.currentTarget);
  };
  
  // 关闭菜单
  const handleMenuClose = () => {
    setAnchorEl(null);
  };
  
  // 打开过滤菜单
  const handleFilterMenuOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
    setFilterMenuAnchorEl(event.currentTarget);
  };
  
  // 关闭过滤菜单
  const handleFilterMenuClose = () => {
    setFilterMenuAnchorEl(null);
  };
  
  // 处理标记所有为已读
  const handleMarkAllAsRead = async () => {
    if (onMarkAllAsRead) {
      try {
        await onMarkAllAsRead();
      } catch (error) {
        console.error('Failed to mark all notifications as read:', error);
      }
    }
    handleMenuClose();
  };
  
  // 处理清除所有通知
  const handleClearAll = async () => {
    if (onClearAll) {
      try {
        await onClearAll();
      } catch (error) {
        console.error('Failed to clear all notifications:', error);
      }
    }
    handleMenuClose();
  };
  
  // 处理刷新通知
  const handleRefresh = async () => {
    if (onRefresh) {
      try {
        await onRefresh();
      } catch (error) {
        console.error('Failed to refresh notifications:', error);
      }
    }
    handleMenuClose();
  };
  
  // 处理切换标签
  const handleTabChange = (event: React.SyntheticEvent, newValue: string) => {
    setCurrentTab(newValue);
  };
  
  // 处理设置点击
  const handleSettingsClick = () => {
    if (onSettingsClick) {
      onSettingsClick();
    }
    handleMenuClose();
  };
  
  // 格式化时间
  const formatTime = (date: Date | string) => {
    const notificationDate = typeof date === 'string' ? new Date(date) : date;
    const now = new Date();
    const diffMs = now.getTime() - notificationDate.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    
    if (diffDay > 0) {
      return diffDay === 1 ? '昨天' : `${diffDay}天前`;
    } else if (diffHour > 0) {
      return `${diffHour}小时前`;
    } else if (diffMin > 0) {
      return `${diffMin}分钟前`;
    } else {
      return '刚刚';
    }
  };
  
  // 通知分组
  const groupedNotifications = useMemo(() => {
    const groups: {
      [key: string]: Notification[];
    } = {
      today: [],
      yesterday: [],
      older: []
    };
    
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterday = today - 86400000; // 减去一天的毫秒数
    
    notifications.forEach(notification => {
      const notificationDate = typeof notification.timestamp === 'string' 
        ? new Date(notification.timestamp) 
        : notification.timestamp;
      const notificationTime = notificationDate.getTime();
      
      if (notificationTime >= today) {
        groups.today.push(notification);
      } else if (notificationTime >= yesterday) {
        groups.yesterday.push(notification);
      } else {
        groups.older.push(notification);
      }
    });
    
    return groups;
  }, [notifications]);
  
  // 过滤通知
  const filteredNotifications = useMemo(() => {
    if (currentTab === 'all') return notifications;
    if (currentTab === 'unread') return notifications.filter(n => !n.isRead);
    return notifications.filter(n => n.type === currentTab);
  }, [notifications, currentTab]);
  
  // 过滤并分组通知
  const filteredGroupedNotifications = useMemo(() => {
    const groups: {
      [key: string]: Notification[];
    } = {
      today: [],
      yesterday: [],
      older: []
    };
    
    if (currentTab === 'all' || currentTab === 'unread') {
      // 如果是全部或未读，使用已有的分组，并根据未读过滤
      if (currentTab === 'unread') {
        groups.today = groupedNotifications.today.filter(n => !n.isRead);
        groups.yesterday = groupedNotifications.yesterday.filter(n => !n.isRead);
        groups.older = groupedNotifications.older.filter(n => !n.isRead);
      } else {
        groups.today = groupedNotifications.today;
        groups.yesterday = groupedNotifications.yesterday;
        groups.older = groupedNotifications.older;
      }
    } else {
      // 如果是特定类型，重新分组
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      const yesterday = today - 86400000; // 减去一天的毫秒数
      
      notifications
        .filter(n => n.type === currentTab)
        .forEach(notification => {
          const notificationDate = typeof notification.timestamp === 'string' 
            ? new Date(notification.timestamp) 
            : notification.timestamp;
          const notificationTime = notificationDate.getTime();
          
          if (notificationTime >= today) {
            groups.today.push(notification);
          } else if (notificationTime >= yesterday) {
            groups.yesterday.push(notification);
          } else {
            groups.older.push(notification);
          }
        });
    }
    
    return groups;
  }, [groupedNotifications, notifications, currentTab]);
  
  // 获取未读通知数量
  const unreadCount = notifications.filter(n => !n.isRead).length;
  
  // 获取每种类型的通知数量
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    notifications.forEach(notification => {
      counts[notification.type] = (counts[notification.type] || 0) + 1;
    });
    return counts;
  }, [notifications]);
  
  // 获取每种类型的未读通知数量
  const unreadTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    notifications.filter(n => !n.isRead).forEach(notification => {
      counts[notification.type] = (counts[notification.type] || 0) + 1;
    });
    return counts;
  }, [notifications]);
  
  // 检查一个组是否为空
  const isGroupEmpty = (group: Notification[]) => group.length === 0;
  
  // 检查所有分组是否为空
  const areAllGroupsEmpty = () => {
    return isGroupEmpty(filteredGroupedNotifications.today) && 
           isGroupEmpty(filteredGroupedNotifications.yesterday) && 
           isGroupEmpty(filteredGroupedNotifications.older);
  };
  
  return (
    <Paper sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: 1, borderColor: 'divider' }}>
        <Box display="flex" alignItems="center">
          <Badge badgeContent={unreadCount} color="error" sx={{ mr: 1 }}>
            <NotificationsIcon />
          </Badge>
          <Typography variant="h6">通知中心</Typography>
        </Box>
        <Box>
          <Tooltip title="过滤">
            <IconButton onClick={handleFilterMenuOpen} size="small">
              <FilterListIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="更多选项">
            <IconButton onClick={handleMenuOpen} size="small">
              <MoreVertIcon />
            </IconButton>
          </Tooltip>
          
          {/* 过滤菜单 */}
          <Menu
            anchorEl={filterMenuAnchorEl}
            open={Boolean(filterMenuAnchorEl)}
            onClose={handleFilterMenuClose}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'right',
            }}
            transformOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
          >
            <MenuItem onClick={() => { setCurrentTab('all'); handleFilterMenuClose(); }}>
              <ListItemIcon>
                <NotificationsIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>所有通知</ListItemText>
              <Chip 
                label={notifications.length} 
                size="small" 
                color="default" 
                sx={{ ml: 1 }} 
              />
            </MenuItem>
            <MenuItem onClick={() => { setCurrentTab('unread'); handleFilterMenuClose(); }}>
              <ListItemIcon>
                <Badge badgeContent={unreadCount} color="error">
                  <NotificationsIcon fontSize="small" />
                </Badge>
              </ListItemIcon>
              <ListItemText>未读通知</ListItemText>
              <Chip 
                label={unreadCount} 
                size="small" 
                color="error" 
                sx={{ ml: 1 }} 
              />
            </MenuItem>
            <Divider />
            <MenuItem onClick={() => { setCurrentTab('message'); handleFilterMenuClose(); }}>
              <ListItemIcon>
                <MessageIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>消息</ListItemText>
              <Chip 
                label={typeCounts['message'] || 0} 
                size="small" 
                color="primary" 
                sx={{ ml: 1 }} 
              />
            </MenuItem>
            <MenuItem onClick={() => { setCurrentTab('appointment'); handleFilterMenuClose(); }}>
              <ListItemIcon>
                <CalendarTodayIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>预约</ListItemText>
              <Chip 
                label={typeCounts['appointment'] || 0} 
                size="small" 
                color="secondary" 
                sx={{ ml: 1 }} 
              />
            </MenuItem>
            <MenuItem onClick={() => { setCurrentTab('task'); handleFilterMenuClose(); }}>
              <ListItemIcon>
                <AssignmentIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>任务</ListItemText>
              <Chip 
                label={typeCounts['task'] || 0} 
                size="small" 
                color="success" 
                sx={{ ml: 1 }} 
              />
            </MenuItem>
            <MenuItem onClick={() => { setCurrentTab('health_alert'); handleFilterMenuClose(); }}>
              <ListItemIcon>
                <HealthAndSafetyIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>健康预警</ListItemText>
              <Chip 
                label={typeCounts['health_alert'] || 0} 
                size="small" 
                color="error" 
                sx={{ ml: 1 }} 
              />
            </MenuItem>
            <MenuItem onClick={() => { setCurrentTab('followup'); handleFilterMenuClose(); }}>
              <ListItemIcon>
                <NotificationsActiveIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>随访提醒</ListItemText>
              <Chip 
                label={typeCounts['followup'] || 0} 
                size="small" 
                color="info" 
                sx={{ ml: 1 }} 
              />
            </MenuItem>
          </Menu>
          
          {/* 更多选项菜单 */}
          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={handleMenuClose}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'right',
            }}
            transformOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
          >
            <MenuItem onClick={handleMarkAllAsRead}>
              <ListItemIcon>
                <CheckCircleIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>全部标记为已读</ListItemText>
            </MenuItem>
            <MenuItem onClick={handleClearAll}>
              <ListItemIcon>
                <DeleteIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>清空所有通知</ListItemText>
            </MenuItem>
            <MenuItem onClick={handleRefresh}>
              <ListItemIcon>
                <RefreshIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>刷新</ListItemText>
            </MenuItem>
            <Divider />
            <MenuItem onClick={handleSettingsClick}>
              <ListItemIcon>
                <SettingsIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>通知设置</ListItemText>
            </MenuItem>
          </Menu>
        </Box>
      </Box>
      
      {/* 通知类型标签页 */}
      <Tabs
        value={currentTab}
        onChange={handleTabChange}
        indicatorColor="primary"
        textColor="primary"
        variant="scrollable"
        scrollButtons="auto"
        sx={{ px: 2, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab
          icon={<Badge badgeContent={unreadCount} color="error"><NotificationsIcon /></Badge>}
          iconPosition="start"
          label="全部"
          value="all"
        />
        <Tab
          icon={<Badge badgeContent={unreadTypeCounts['message'] || 0} color="primary"><MessageIcon /></Badge>}
          iconPosition="start"
          label="消息"
          value="message"
        />
        <Tab
          icon={<Badge badgeContent={unreadTypeCounts['appointment'] || 0} color="secondary"><CalendarTodayIcon /></Badge>}
          iconPosition="start"
          label="预约"
          value="appointment"
        />
        <Tab
          icon={<Badge badgeContent={unreadTypeCounts['task'] || 0} color="success"><AssignmentIcon /></Badge>}
          iconPosition="start"
          label="任务"
          value="task"
        />
        <Tab
          icon={<Badge badgeContent={unreadTypeCounts['health_alert'] || 0} color="error"><HealthAndSafetyIcon /></Badge>}
          iconPosition="start"
          label="健康预警"
          value="health_alert"
        />
        <Tab
          icon={<Badge badgeContent={unreadTypeCounts['followup'] || 0} color="info"><NotificationsActiveIcon /></Badge>}
          iconPosition="start"
          label="随访提醒"
          value="followup"
        />
      </Tabs>
      
      {/* 通知列表 */}
      {loading ? (
        <Box display="flex" justifyContent="center" alignItems="center" flexGrow={1}>
          <CircularProgress />
        </Box>
      ) : (
        <List sx={{ flexGrow: 1, overflow: 'auto', py: 0 }}>
          {areAllGroupsEmpty() ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', p: 3 }}>
              <Typography variant="body1" color="textSecondary" align="center">
                暂无通知
              </Typography>
              <Button
                variant="outlined"
                startIcon={<RefreshIcon />}
                onClick={handleRefresh}
                sx={{ mt: 2 }}
              >
                刷新
              </Button>
            </Box>
          ) : (
            <>
              {/* 今天的通知 */}
              {!isGroupEmpty(filteredGroupedNotifications.today) && (
                <>
                  <Box sx={{ px: 2, py: 1, bgcolor: 'background.default' }}>
                    <Typography variant="subtitle2" color="textSecondary">
                      今天
                    </Typography>
                  </Box>
                  {filteredGroupedNotifications.today.map((notification, index) => (
                    <NotificationItem 
                      key={notification.id}
                      notification={notification}
                      onClick={() => handleNotificationClick(notification)}
                      onMarkAsRead={(e) => handleMarkAsRead(e, notification.id)}
                      onDelete={(e) => handleDelete(e, notification.id)}
                      isLast={index === filteredGroupedNotifications.today.length - 1}
                    />
                  ))}
                </>
              )}
              
              {/* 昨天的通知 */}
              {!isGroupEmpty(filteredGroupedNotifications.yesterday) && (
                <>
                  <Box sx={{ px: 2, py: 1, bgcolor: 'background.default' }}>
                    <Typography variant="subtitle2" color="textSecondary">
                      昨天
                    </Typography>
                  </Box>
                  {filteredGroupedNotifications.yesterday.map((notification, index) => (
                    <NotificationItem 
                      key={notification.id}
                      notification={notification}
                      onClick={() => handleNotificationClick(notification)}
                      onMarkAsRead={(e) => handleMarkAsRead(e, notification.id)}
                      onDelete={(e) => handleDelete(e, notification.id)}
                      isLast={index === filteredGroupedNotifications.yesterday.length - 1}
                    />
                  ))}
                </>
              )}
              
              {/* 更早的通知 */}
              {!isGroupEmpty(filteredGroupedNotifications.older) && (
                <>
                  <Box sx={{ px: 2, py: 1, bgcolor: 'background.default' }}>
                    <Typography variant="subtitle2" color="textSecondary">
                      更早
                    </Typography>
                  </Box>
                  {filteredGroupedNotifications.older.map((notification, index) => (
                    <NotificationItem 
                      key={notification.id}
                      notification={notification}
                      onClick={() => handleNotificationClick(notification)}
                      onMarkAsRead={(e) => handleMarkAsRead(e, notification.id)}
                      onDelete={(e) => handleDelete(e, notification.id)}
                      isLast={index === filteredGroupedNotifications.older.length - 1}
                    />
                  ))}
                </>
              )}
            </>
          )}
        </List>
      )}
    </Paper>
  );
};

// 通知项组件
interface NotificationItemProps {
  notification: Notification;
  onClick: () => void;
  onMarkAsRead: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
  isLast: boolean;
}

const NotificationItem: React.FC<NotificationItemProps> = ({
  notification,
  onClick,
  onMarkAsRead,
  onDelete,
  isLast
}) => {
  const { id, title, content, type, timestamp, isRead, priority = 'normal' } = notification;
  
  return (
    <>
      <ListItem
        alignItems="flex-start"
        button
        onClick={onClick}
        sx={{
          bgcolor: isRead ? 'inherit' : 'action.hover',
          py: 1.5,
          position: 'relative',
          '&::after': priority === 'urgent' ? {
            content: '""',
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: '4px',
            backgroundColor: 'error.main'
          } : priority === 'important' ? {
            content: '""',
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: '4px',
            backgroundColor: 'warning.main'
          } : undefined
        }}
      >
        <ListItemAvatar>
          <Avatar
            src={notification.sender?.avatar}
            alt={notification.sender?.name}
          >
            {notificationTypeIcons[type as NotificationType] || <NotificationsIcon />}
          </Avatar>
        </ListItemAvatar>
        <ListItemText
          primary={
            <Box display="flex" justifyContent="space-between" alignItems="center">
              <Typography
                variant="subtitle1"
                component="div"
                sx={{ 
                  fontWeight: isRead ? 'normal' : 'bold',
                  display: 'flex',
                  alignItems: 'center'
                }}
              >
                {title}
                {priority === 'urgent' && (
                  <Tooltip title="紧急">
                    <WarningIcon 
                      fontSize="small" 
                      color="error" 
                      sx={{ ml: 1 }} 
                    />
                  </Tooltip>
                )}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                {formatTime(timestamp)}
              </Typography>
            </Box>
          }
          secondary={
            <Box>
              <Typography
                variant="body2"
                color="textPrimary"
                component="span"
                sx={{ display: 'inline', fontWeight: isRead ? 'normal' : 'medium' }}
              >
                {content}
              </Typography>
              <Box mt={1} display="flex" justifyContent="space-between" alignItems="center">
                <Chip
                  size="small"
                  label={notificationTypeText[type as NotificationType] || type}
                  color={
                    type === 'message' ? 'primary' :
                    type === 'appointment' ? 'secondary' :
                    type === 'task' ? 'success' :
                    type === 'health_alert' ? 'error' :
                    type === 'followup' ? 'info' : 'warning'
                  }
                  variant="outlined"
                />
                <Box>
                  {!isRead && (
                    <Tooltip title="标记为已读">
                      <IconButton
                        onClick={onMarkAsRead}
                        size="small"
                        sx={{ ml: 1 }}
                      >
                        <CheckCircleIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                  <Tooltip title="删除">
                    <IconButton
                      onClick={onDelete}
                      size="small"
                      sx={{ ml: 1 }}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
            </Box>
          }
        />
      </ListItem>
      {!isLast && <Divider variant="inset" component="li" />}
    </>
  );
};

export default NotificationCenter; 