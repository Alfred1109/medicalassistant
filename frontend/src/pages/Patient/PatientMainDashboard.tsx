import React from 'react';
import { 
  Box, 
  Typography, 
  Grid, 
  Paper, 
  Card, 
  CardContent, 
  CardActions,
  Button, 
  Divider, 
  List, 
  ListItem, 
  ListItemText, 
  ListItemIcon,
  ListItemAvatar,
  Avatar,
  Chip,
  IconButton,
  LinearProgress,
  Stack
} from '@mui/material';

// 图标可能需要根据实际项目调整导入方式
const HeartIcon = () => <span>❤️</span>;
const DirectionsWalkIcon = () => <span>🚶</span>;
const DoctorIcon = () => <span>👨‍⚕️</span>;
const NotificationsIcon = () => <span>🔔</span>;
const EventIcon = () => <span>📅</span>;
const ArrowForwardIcon = () => <span>➡️</span>;
const CheckCircleIcon = () => <span>✅</span>;
const WarningIcon = () => <span>⚠️</span>;
const DeviceIcon = () => <span>📱</span>;
const MedicationIcon = () => <span>💊</span>;
const NoteIcon = () => <span>📝</span>;
const ChatIcon = () => <span>💬</span>;

import { Link } from 'react-router-dom';

// 模拟健康指标数据
const healthMetrics = [
  { id: 1, name: '心率', value: '75', unit: '次/分', status: 'normal', icon: <HeartIcon />, trend: '+2%' },
  { id: 2, name: '血压', value: '120/80', unit: 'mmHg', status: 'normal', icon: <HeartIcon />, trend: '-1%' },
  { id: 3, name: '步数', value: '6,532', unit: '步/天', status: 'good', icon: <DirectionsWalkIcon />, trend: '+15%' },
  { id: 4, name: '睡眠', value: '7.5', unit: '小时', status: 'normal', icon: <HeartIcon />, trend: '+5%' },
];

// 模拟待办事项
const todoItems = [
  { id: 1, title: '血压记录', description: '请完成今日的血压测量记录', due: '今天', completed: false, important: true },
  { id: 2, title: '服药提醒', description: '降压药 - 每日2次', due: '12:30', completed: true, important: true },
  { id: 3, title: '康复练习', description: '完成下肢力量训练', due: '今天', completed: false, important: false },
  { id: 4, title: '睡眠日记', description: '记录昨晚睡眠情况', due: '今天', completed: false, important: false },
];

// 模拟医生通知
const doctorNotifications = [
  { id: 1, title: '康复计划已更新', doctor: '张医生', time: '今天 09:30', read: false },
  { id: 2, title: '下周随访预约提醒', doctor: '李医师', time: '昨天 14:45', read: true },
  { id: 3, title: '新的健康建议', doctor: '王医生', time: '2天前', read: true },
];

// 模拟康复进度
const rehabProgress = {
  plan: '下肢功能恢复计划',
  progress: 65,
  nextSession: '明天 15:00',
  exercises: [
    { name: '下肢伸展', completed: true },
    { name: '平衡训练', completed: true },
    { name: '步态训练', completed: false },
    { name: '力量训练', completed: false },
  ]
};

// 获取状态颜色
const getStatusColor = (status: string) => {
  switch (status) {
    case 'normal': return 'primary';
    case 'good': return 'success';
    case 'warning': return 'warning';
    case 'danger': return 'error';
    default: return 'primary';
  }
};

const PatientMainDashboard: React.FC = () => {
  const [loading, setLoading] = React.useState(true);
  
  // 模拟数据加载
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(false);
    }, 1000);
    
    return () => clearTimeout(timer);
  }, []);
  
  return (
    <Box>
      {/* 页面标题 */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h5" component="h1">
          患者主面板
        </Typography>
        <Stack direction="row" spacing={1}>
          <IconButton color="primary" component={Link} to="/app/patient/communications">
            <ChatIcon />
          </IconButton>
          <IconButton color="primary">
            <NotificationsIcon />
          </IconButton>
        </Stack>
      </Box>
      
      <Grid container spacing={3}>
        {/* 健康状态概览 */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="h6" gutterBottom>
              健康状态概览
            </Typography>
            <Grid container spacing={2}>
              {healthMetrics.map((metric) => (
                <Grid item xs={6} sm={3} key={metric.id}>
                  <Card variant="outlined">
                    <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                      <Box display="flex" justifyContent="space-between">
                        <Box display="flex" alignItems="center">
                          {metric.icon}
                          <Typography variant="subtitle2" sx={{ ml: 1 }}>
                            {metric.name}
                          </Typography>
                        </Box>
                        <Chip 
                          label={metric.trend} 
                          size="small" 
                          color={metric.trend.includes('+') ? 'success' : 'primary'}
                          variant="outlined"
                        />
                      </Box>
                      <Box display="flex" alignItems="baseline" mt={1}>
                        <Typography variant="h4" component="div" color={`${getStatusColor(metric.status)}.main`}>
                          {metric.value}
                        </Typography>
                        <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                          {metric.unit}
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
            <Box textAlign="right" mt={1}>
              <Button 
                endIcon={<ArrowForwardIcon />}
                component={Link}
                to="/app/patient/statistics"
                size="small"
              >
                查看详细数据
              </Button>
            </Box>
          </Paper>
        </Grid>
        
        {/* 左侧内容 - 待办和康复进度 */}
        <Grid item xs={12} md={6}>
          {/* 待办事项 */}
          <Paper sx={{ p: 2, mb: 3, height: '100%' }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">
                今日待办
              </Typography>
              <IconButton size="small" component={Link} to="/app/patient/daily-records">
                <ArrowForwardIcon />
              </IconButton>
            </Box>
            
            <List sx={{ width: '100%' }}>
              {todoItems.slice(0, 3).map((item) => (
                <React.Fragment key={item.id}>
                  <ListItem 
                    secondaryAction={
                      item.completed ? (
                        <CheckCircleIcon />
                      ) : (
                        <Chip 
                          label={item.due} 
                          size="small" 
                          color={item.important ? "error" : "primary"} 
                          variant={item.important ? "filled" : "outlined"}
                        />
                      )
                    }
                    sx={{
                      backgroundColor: item.completed ? 'rgba(0, 0, 0, 0.03)' : 'transparent',
                      borderRadius: 1,
                      textDecoration: item.completed ? 'line-through' : 'none',
                      color: item.completed ? 'text.secondary' : 'text.primary',
                    }}
                  >
                    <ListItemIcon>
                      {item.title.includes('血压') && <HeartIcon />}
                      {item.title.includes('服药') && <MedicationIcon />}
                      {item.title.includes('康复') && <DirectionsWalkIcon />}
                      {item.title.includes('睡眠') && <NoteIcon />}
                    </ListItemIcon>
                    <ListItemText 
                      primary={item.title} 
                      secondary={item.description}
                    />
                  </ListItem>
                  {item.id < todoItems.slice(0, 3).length && <Divider component="li" />}
                </React.Fragment>
              ))}
            </List>
            
            <Box textAlign="center" mt={2}>
              <Button 
                variant="outlined"
                size="small"
                component={Link}
                to="/app/patient/daily-records"
              >
                查看全部待办 ({todoItems.length})
              </Button>
            </Box>
          </Paper>
        </Grid>
        
        {/* 右侧内容 - 通知和设备 */}
        <Grid item xs={12} md={6}>
          {/* 医生通知 */}
          <Paper sx={{ p: 2, mb: 3 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">
                医生通知
              </Typography>
              <IconButton size="small" component={Link} to="/app/patient/communications">
                <ArrowForwardIcon />
              </IconButton>
            </Box>
            
            <List sx={{ width: '100%' }}>
              {doctorNotifications.map((notification, index) => (
                <React.Fragment key={notification.id}>
                  <ListItem
                    sx={{
                      backgroundColor: notification.read ? 'transparent' : 'rgba(25, 118, 210, 0.08)',
                      borderRadius: 1,
                    }}
                  >
                    <ListItemAvatar>
                      <Avatar sx={{ bgcolor: notification.read ? 'grey.300' : 'primary.main' }}>
                        <DoctorIcon />
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText
                      primary={
                        <Typography variant="body1" component="span">
                          {notification.title}
                          {!notification.read && (
                            <Chip
                              label="新"
                              size="small"
                              color="error"
                              sx={{ ml: 1, height: 20 }}
                            />
                          )}
                        </Typography>
                      }
                      secondary={`${notification.doctor} · ${notification.time}`}
                    />
                  </ListItem>
                  {index < doctorNotifications.length - 1 && <Divider component="li" variant="inset" />}
                </React.Fragment>
              ))}
            </List>
          </Paper>
          
          {/* 康复进度 */}
          <Paper sx={{ p: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">
                康复进度跟踪
              </Typography>
              <Chip 
                icon={<EventIcon />} 
                label={`下次: ${rehabProgress.nextSession}`} 
                size="small" 
                color="primary" 
                variant="outlined"
              />
            </Box>
            
            <Typography variant="subtitle1" gutterBottom>
              {rehabProgress.plan}
            </Typography>
            
            <Box sx={{ display: 'flex', alignItems: 'center', mt: 1, mb: 2 }}>
              <Box sx={{ width: '100%', mr: 1 }}>
                <LinearProgress 
                  variant="determinate" 
                  value={rehabProgress.progress} 
                  sx={{ height: 10, borderRadius: 5 }}
                />
              </Box>
              <Box sx={{ minWidth: 35 }}>
                <Typography variant="body2" color="text.secondary">
                  {`${Math.round(rehabProgress.progress)}%`}
                </Typography>
              </Box>
            </Box>
            
            <Typography variant="subtitle2" gutterBottom>
              训练项目
            </Typography>
            
            <List dense>
              {rehabProgress.exercises.map((exercise, index) => (
                <ListItem key={index} sx={{ py: 0.5 }}>
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    {exercise.completed ? (
                      <CheckCircleIcon />
                    ) : (
                      <CircleIcon color="disabled" fontSize="small" />
                    )}
                  </ListItemIcon>
                  <ListItemText primary={exercise.name} />
                </ListItem>
              ))}
            </List>
            
            <Box textAlign="center" mt={2}>
              <Button 
                variant="contained"
                size="small"
                color="primary"
                component={Link}
                to="/app/rehab-plans"
              >
                查看康复计划详情
              </Button>
            </Box>
          </Paper>
        </Grid>
        
        {/* 设备连接状态 */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">
                设备连接状态
              </Typography>
              <Button 
                startIcon={<DeviceIcon />} 
                size="small"
                component={Link}
                to="/app/patient/devices"
              >
                管理设备
              </Button>
            </Box>
            
            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <Card variant="outlined">
                  <CardContent sx={{ display: 'flex', alignItems: 'center', p: 2 }}>
                    <Avatar sx={{ bgcolor: 'success.main', mr: 2 }}>
                      <DeviceIcon />
                    </Avatar>
                    <Box>
                      <Typography variant="subtitle1">
                        心率监测器
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        连接正常 · 电量 82%
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={4}>
                <Card variant="outlined">
                  <CardContent sx={{ display: 'flex', alignItems: 'center', p: 2 }}>
                    <Avatar sx={{ bgcolor: 'warning.main', mr: 2 }}>
                      <DeviceIcon />
                    </Avatar>
                    <Box>
                      <Typography variant="subtitle1">
                        血压计
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        连接正常 · 电量 45%
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={4}>
                <Card variant="outlined">
                  <CardContent sx={{ display: 'flex', alignItems: 'center', p: 2 }}>
                    <Avatar sx={{ bgcolor: 'error.main', mr: 2 }}>
                      <DeviceIcon />
                    </Avatar>
                    <Box>
                      <Typography variant="subtitle1">
                        康复训练设备
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        <Box component="span" sx={{ display: 'flex', alignItems: 'center' }}>
                          <WarningIcon />
                          <span style={{ marginLeft: '4px' }}>连接断开</span>
                        </Box>
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

// 用于未完成项目的空心圆图标
const CircleIcon = ({ color, fontSize }: { color: 'disabled' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning', fontSize: 'small' | 'medium' | 'large' | 'inherit' }) => {
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-block',
        width: fontSize === 'small' ? 16 : 24,
        height: fontSize === 'small' ? 16 : 24,
        borderRadius: '50%',
        border: `2px solid ${color === 'disabled' ? '#bdbdbd' : ''}`,
      }}
    />
  );
};

export default PatientMainDashboard; 