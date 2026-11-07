import React from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../../config/constants';
import dashboardService from '../../services/dashboardService';
import { deviceService, Device as DeviceInfo } from '../../services/deviceService';
import {
  Box,
  Typography,
  Grid,
  Paper,
  Card,
  CardContent,
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
  Stack,
  CircularProgress
} from '@mui/material';

// 图标可能需要根据实际项目调整导入方式
const HeartIcon = () => <span>❤️</span>;
const DirectionsWalkIcon = () => <span>🚶</span>;
const DoctorIcon = () => <span>👨‍⚕️</span>;
const NotificationsIcon = () => <span>🔔</span>;
const EventIcon = () => <span>📅</span>;
const ArrowForwardIcon = () => <span>➡️</span>;
const CheckCircleIcon = () => <span>✅</span>;
const DeviceIcon = () => <span>📱</span>;
const MedicationIcon = () => <span>💊</span>;
const NoteIcon = () => <span>📝</span>;
const ChatIcon = () => <span>💬</span>;

import { Link } from 'react-router-dom';

// 后端 health_metrics 为 MongoDB 原始文档，字段形状可能不固定，渲染时防御性取值
interface RawHealthMetric {
  id?: string;
  type?: string;
  name?: string;
  value?: string | number;
  unit?: string;
  status?: string;
  trend?: string;
  timestamp?: string;
  [key: string]: any;
}

// 后端 todo_items 文档，字段做可选处理，避免文档缺字段时崩溃
interface RawTodoItem {
  id?: string;
  title?: string;
  description?: string;
  due?: string;
  completed?: boolean;
  important?: boolean;
  [key: string]: any;
}

// 后端 rehab_progress 文档（404 时无数据，由调用方区分空态与错误）
interface RawRehabProgress {
  id?: string;
  plan?: string;
  progress?: number;
  next_session?: string;
  exercises?: { name?: string; completed?: boolean }[];
  [key: string]: any;
}

// 设备列表直接复用 deviceService 的 Device 类型（与后端 DeviceResponse 字段对齐，snake_case）

// 定义通知数据类型
interface Notification {
  id: string;
  title: string;
  sender_name: string;
  time: string;
  read: boolean;
}

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

// 设备状态 → Avatar 颜色
const getDeviceStatusColor = (status?: string) => {
  switch (status) {
    case 'online': return 'success.main';
    case 'offline': return 'warning.main';
    case 'error': return 'error.main';
    default: return 'primary.main';
  }
};

// 时间显示：无效或缺失时间返回 null，避免渲染出 NaN/Invalid Date
const formatDateTime = (value?: string | null) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
};

// 面板内通用的加载中提示
const PanelLoading = () => (
  <Box display="flex" justifyContent="center" alignItems="center" py={4}>
    <CircularProgress size={24} sx={{ mr: 1 }} />
    <Typography variant="body2" color="text.secondary">
      加载中...
    </Typography>
  </Box>
);

// 面板内通用的错误提示
const PanelError = ({ text }: { text: string }) => (
  <Box textAlign="center" py={4}>
    <Typography variant="body2" color="error">
      {text}
    </Typography>
  </Box>
);

// 面板内通用的空数据提示
const PanelEmpty = ({ text }: { text: string }) => (
  <Box textAlign="center" py={4}>
    <Typography variant="body2" color="text.secondary">
      {text}
    </Typography>
  </Box>
);

const PatientMainDashboard: React.FC = () => {
  const [loading, setLoading] = React.useState(true);
  const [notifications, setNotifications] = React.useState<Notification[]>([]);
  const [notificationsLoading, setNotificationsLoading] = React.useState(true);

  // 主面板各区块的真实数据状态
  const [healthMetrics, setHealthMetrics] = React.useState<RawHealthMetric[]>([]);
  const [healthMetricsError, setHealthMetricsError] = React.useState(false);
  const [todoItems, setTodoItems] = React.useState<RawTodoItem[]>([]);
  const [todoError, setTodoError] = React.useState(false);
  const [rehabProgress, setRehabProgress] = React.useState<RawRehabProgress | null>(null);
  const [rehabProgressMissing, setRehabProgressMissing] = React.useState(false);
  const [rehabProgressError, setRehabProgressError] = React.useState(false);
  const [devices, setDevices] = React.useState<DeviceInfo[]>([]);
  const [devicesError, setDevicesError] = React.useState(false);

  // 加载通知数据
  React.useEffect(() => {
    // 获取通知
    const fetchNotifications = async () => {
      try {
        setNotificationsLoading(true);
        console.log('开始获取通知数据...');

        // 获取认证令牌
        const token = localStorage.getItem('token');
        if (!token) {
          console.error('认证令牌不存在，无法获取通知数据');
          setNotificationsLoading(false);
          return;
        }

        // 从API获取通知数据
        const response = await axios.get(`${API_BASE_URL}/notifications?limit=5`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        console.log('通知数据API响应:', response.data);

        if (response.data) {
          // 转换时间格式为更友好的显示形式
          const notificationsWithFormattedTime = response.data.map((notification: any) => {
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

          console.log('转换后的通知数据:', notificationsWithFormattedTime);
          setNotifications(notificationsWithFormattedTime);
        } else {
          // 如果API返回为空，使用空数组
          console.log('API返回数据为空');
          setNotifications([]);
        }
      } catch (error) {
        console.error('获取通知失败:', error);
        // 发生错误时设置为空数组
        setNotifications([]);
      } finally {
        setNotificationsLoading(false);
      }
    };

    fetchNotifications();
  }, []);

  // 一次性拉取主面板真实数据：健康指标 / 待办 / 康复进度 / 绑定设备，全部完成后统一关闭 loading
  React.useEffect(() => {
    let cancelled = false;

    const loadData = async () => {
      const [metricsRes, todosRes, progressRes, devicesRes] = await Promise.allSettled([
        dashboardService.getHealthMetrics() as unknown as Promise<RawHealthMetric[]>,
        dashboardService.getTodoItems() as unknown as Promise<RawTodoItem[]>,
        dashboardService.getRehabProgress() as unknown as Promise<RawRehabProgress>,
        deviceService.getUserDevices(),
      ]);

      if (cancelled) return;

      // 健康指标
      if (metricsRes.status === 'fulfilled' && Array.isArray(metricsRes.value)) {
        setHealthMetrics(metricsRes.value);
        setHealthMetricsError(false);
      } else {
        setHealthMetrics([]);
        setHealthMetricsError(true);
      }

      // 待办事项
      if (todosRes.status === 'fulfilled' && Array.isArray(todosRes.value)) {
        setTodoItems(todosRes.value);
        setTodoError(false);
      } else {
        setTodoItems([]);
        setTodoError(true);
      }

      // 康复进度：后端无数据时返回 404，属于"暂无数据"而非错误
      if (progressRes.status === 'fulfilled') {
        setRehabProgress(progressRes.value);
        setRehabProgressMissing(false);
        setRehabProgressError(false);
      } else if (axios.isAxiosError(progressRes.reason) && progressRes.reason.response?.status === 404) {
        setRehabProgress(null);
        setRehabProgressMissing(true);
        setRehabProgressError(false);
      } else {
        setRehabProgress(null);
        setRehabProgressMissing(false);
        setRehabProgressError(true);
      }

      // 绑定设备
      if (devicesRes.status === 'fulfilled' && Array.isArray(devicesRes.value)) {
        setDevices(devicesRes.value);
        setDevicesError(false);
      } else {
        setDevices([]);
        setDevicesError(true);
      }

      setLoading(false);
    };

    loadData();

    return () => {
      cancelled = true;
    };
  }, []);

  // 康复进度条数值防御：缺失按 0，并限制在 0~100
  const rehabProgressValue = rehabProgress
    ? Math.min(Math.max(typeof rehabProgress.progress === 'number' ? rehabProgress.progress : 0, 0), 100)
    : 0;

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
              {loading ? (
                <Grid item xs={12}>
                  <PanelLoading />
                </Grid>
              ) : healthMetricsError ? (
                <Grid item xs={12}>
                  <PanelError text="健康指标加载失败，请稍后重试" />
                </Grid>
              ) : healthMetrics.length === 0 ? (
                <Grid item xs={12}>
                  <PanelEmpty text="暂无健康指标数据" />
                </Grid>
              ) : (
                healthMetrics.map((metric, index) => (
                  <Grid item xs={6} sm={3} key={metric.id ?? `metric-${index}`}>
                    <Card variant="outlined">
                      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                        <Box display="flex" justifyContent="space-between">
                          <Typography variant="subtitle2">
                            {metric.name ?? metric.type ?? '未命名指标'}
                          </Typography>
                          {metric.trend && (
                            <Chip
                              label={metric.trend}
                              size="small"
                              color={metric.trend.includes('+') ? 'success' : 'primary'}
                              variant="outlined"
                            />
                          )}
                        </Box>
                        <Box display="flex" alignItems="baseline" mt={1}>
                          <Typography variant="h4" component="div" color={`${getStatusColor(metric.status ?? '')}.main`}>
                            {metric.value ?? '-'}
                          </Typography>
                          {metric.unit && (
                            <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                              {metric.unit}
                            </Typography>
                          )}
                        </Box>
                        {formatDateTime(metric.timestamp) && (
                          <Typography variant="caption" color="text.secondary">
                            {formatDateTime(metric.timestamp)}
                          </Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                ))
              )}
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

            {loading ? (
              <PanelLoading />
            ) : todoError ? (
              <PanelError text="待办事项加载失败，请稍后重试" />
            ) : todoItems.length === 0 ? (
              <PanelEmpty text="暂无待办事项" />
            ) : (
              <>
                <List sx={{ width: '100%' }}>
                  {todoItems.slice(0, 3).map((item, index) => (
                    <React.Fragment key={item.id ?? `todo-${index}`}>
                      <ListItem
                        secondaryAction={
                          item.completed ? (
                            <CheckCircleIcon />
                          ) : (
                            item.due && (
                              <Chip
                                label={item.due}
                                size="small"
                                color={item.important ? "error" : "primary"}
                                variant={item.important ? "filled" : "outlined"}
                              />
                            )
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
                          {(item.title ?? '').includes('血压') && <HeartIcon />}
                          {(item.title ?? '').includes('服药') && <MedicationIcon />}
                          {(item.title ?? '').includes('康复') && <DirectionsWalkIcon />}
                          {(item.title ?? '').includes('睡眠') && <NoteIcon />}
                        </ListItemIcon>
                        <ListItemText
                          primary={item.title ?? '未命名待办'}
                          secondary={item.description}
                        />
                      </ListItem>
                      {index < Math.min(todoItems.length, 3) - 1 && <Divider component="li" />}
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
              </>
            )}
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

            {notificationsLoading ? (
              <Box display="flex" justifyContent="center" alignItems="center" py={4}>
                <CircularProgress size={24} sx={{ mr: 1 }} />
                <Typography variant="body2" color="text.secondary">
                  加载通知中...
                </Typography>
              </Box>
            ) : notifications.length > 0 ? (
              <List sx={{ width: '100%' }}>
                {notifications.map((notification, index) => (
                  <React.Fragment key={notification.id}>
                    <ListItem
                      alignItems="flex-start"
                      sx={{
                        bgcolor: notification.read ? 'transparent' : 'rgba(0, 128, 255, 0.05)',
                        py: 1,
                      }}
                    >
                      <ListItemAvatar>
                        <Avatar sx={{ bgcolor: 'primary.main' }}>
                          <DoctorIcon />
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={
                          <Box display="flex" justifyContent="space-between">
                            <Typography variant="subtitle2" component="span">
                              {notification.title}
                              {!notification.read && (
                                <Chip
                                  label="新"
                                  size="small"
                                  color="primary"
                                  sx={{ ml: 1, height: 16, '& .MuiChip-label': { px: 0.5, py: 0 } }}
                                />
                              )}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {notification.time}
                            </Typography>
                          </Box>
                        }
                        secondary={
                          <Typography variant="body2" color="text.secondary">
                            {notification.sender_name}
                          </Typography>
                        }
                      />
                    </ListItem>
                    {index < notifications.length - 1 && <Divider component="li" variant="inset" />}
                  </React.Fragment>
                ))}
              </List>
            ) : (
              <Box textAlign="center" py={4}>
                <Typography variant="body2" color="text.secondary">
                  暂无通知
                </Typography>
              </Box>
            )}

            <Box textAlign="center" mt={2}>
              <Button
                variant="outlined"
                size="small"
                component={Link}
                to="/app/patient/communications"
              >
                查看全部通知
              </Button>
            </Box>
          </Paper>

          {/* 康复进度 */}
          <Paper sx={{ p: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">
                康复进度跟踪
              </Typography>
              {rehabProgress?.next_session && (
                <Chip
                  icon={<EventIcon />}
                  label={`下次: ${rehabProgress.next_session}`}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              )}
            </Box>

            {loading ? (
              <PanelLoading />
            ) : rehabProgressError ? (
              <PanelError text="康复进度加载失败，请稍后重试" />
            ) : rehabProgressMissing || !rehabProgress ? (
              // 后端 /patients/rehab-progress 无数据时返回 404，这里如实显示空状态
              <PanelEmpty text="暂无康复进度数据" />
            ) : (
              <>
                <Typography variant="subtitle1" gutterBottom>
                  {rehabProgress.plan ?? '未命名计划'}
                </Typography>

                <Box sx={{ display: 'flex', alignItems: 'center', mt: 1, mb: 2 }}>
                  <Box sx={{ width: '100%', mr: 1 }}>
                    <LinearProgress
                      variant="determinate"
                      value={rehabProgressValue}
                      sx={{ height: 10, borderRadius: 5 }}
                    />
                  </Box>
                  <Box sx={{ minWidth: 35 }}>
                    <Typography variant="body2" color="text.secondary">
                      {`${Math.round(rehabProgressValue)}%`}
                    </Typography>
                  </Box>
                </Box>

                <Typography variant="subtitle2" gutterBottom>
                  训练项目
                </Typography>

                {(rehabProgress.exercises ?? []).length > 0 ? (
                  <List dense>
                    {rehabProgress.exercises!.map((exercise, index) => (
                      <ListItem key={index} sx={{ py: 0.5 }}>
                        <ListItemIcon sx={{ minWidth: 36 }}>
                          {exercise.completed ? (
                            <CheckCircleIcon />
                          ) : (
                            <CircleIcon color="disabled" fontSize="small" />
                          )}
                        </ListItemIcon>
                        <ListItemText primary={exercise.name ?? '未命名训练'} />
                      </ListItem>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    暂无训练项目
                  </Typography>
                )}

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
              </>
            )}
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
              {loading ? (
                <Grid item xs={12}>
                  <PanelLoading />
                </Grid>
              ) : devicesError ? (
                <Grid item xs={12}>
                  <PanelError text="设备列表加载失败，请稍后重试" />
                </Grid>
              ) : devices.length === 0 ? (
                <Grid item xs={12}>
                  <PanelEmpty text="暂无绑定设备" />
                </Grid>
              ) : (
                devices.map((device, index) => (
                  <Grid item xs={12} sm={4} key={device.id ?? `device-${index}`}>
                    <Card variant="outlined">
                      <CardContent sx={{ display: 'flex', alignItems: 'center', p: 2 }}>
                        <Avatar sx={{ bgcolor: getDeviceStatusColor(device.status), mr: 2 }}>
                          <DeviceIcon />
                        </Avatar>
                        <Box>
                          <Typography variant="subtitle1">
                            {device.name ?? device.device_type ?? '未命名设备'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {[
                              device.device_type,
                              device.status ? `状态: ${device.status}` : null,
                              typeof device.battery_level === 'number' ? `电量 ${device.battery_level}%` : null,
                            ].filter(Boolean).join(' · ') || '暂无状态信息'}
                          </Typography>
                          {formatDateTime(device.last_connected) && (
                            <Typography variant="caption" color="text.secondary">
                              最近连接: {formatDateTime(device.last_connected)}
                            </Typography>
                          )}
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))
              )}
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
