import React from 'react';
import { formatAppDate } from '../../utils/dateTime';
import dashboardService, { type ActionableTodo } from '../../services/dashboardService';
import { deviceService, Device as DeviceInfo } from '../../services/deviceService';
import { notificationApi, Notification } from '../../services/notificationService';
import { rehabPublications, PublishedRehabPlan, PatientRehabFeedback } from '../../services/rehabPublications';
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
  Stack,
  CircularProgress
} from '@mui/material';

// 图标可能需要根据实际项目调整导入方式
const DoctorIcon = () => <span>👨‍⚕️</span>;
const NotificationsIcon = () => <span>🔔</span>;
const ArrowForwardIcon = () => <span>➡️</span>;
const CheckCircleIcon = () => <span>✅</span>;
const DeviceIcon = () => <span>📱</span>;
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
  quality_flags?: string[];
  [key: string]: any;
}

// 设备列表直接复用 deviceService 的 Device 类型（与后端 DeviceResponse 字段对齐，snake_case）
// 通知数据类型复用 notificationService 的 Notification（与后端 Notification 模型对齐）

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
  return formatAppDate(value, 'minute', { invalid: '' }) || null;
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
  const [todoItems, setTodoItems] = React.useState<ActionableTodo[]>([]);
  const [todoError, setTodoError] = React.useState(false);
  const [todoSourceErrors, setTodoSourceErrors] = React.useState<string[]>([]);
  const [rehabPlans, setRehabPlans] = React.useState<PublishedRehabPlan[]>([]);
  const [rehabPlansError, setRehabPlansError] = React.useState(false);
  const [recentFeedback, setRecentFeedback] = React.useState<Array<{ plan: PublishedRehabPlan; feedback: PatientRehabFeedback }>>([]);
  const [feedbackError, setFeedbackError] = React.useState(false);
  const [devices, setDevices] = React.useState<DeviceInfo[]>([]);
  const [devicesError, setDevicesError] = React.useState(false);

  // 加载通知数据
  React.useEffect(() => {
    // 获取通知
    const fetchNotifications = async () => {
      try {
        setNotificationsLoading(true);
        console.log('开始获取通知数据...');

        const response = await notificationApi.getNotifications({ limit: 5 });

        console.log('通知数据API响应:', response);

        if (response) {
          // 转换时间格式为更友好的显示形式
          const notificationsWithFormattedTime = response.map((notification: any) => {
            const formattedTime = formatAppDate(notification.time, 'notification', { invalid: 'NaN-NaN-NaN' });

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

  // 一次性拉取主面板事实：健康指标 / 待办 / 已发布康复方案 / 绑定设备。
  React.useEffect(() => {
    let cancelled = false;

    const loadData = async () => {
      const [metricsRes, todosRes, plansRes, devicesRes] = await Promise.allSettled([
        dashboardService.getHealthMetrics() as unknown as Promise<RawHealthMetric[]>,
        dashboardService.getTodoCenter(),
        rehabPublications.myPlans(0, 5),
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
      if (todosRes.status === 'fulfilled' && Array.isArray(todosRes.value.items)) {
        setTodoItems(todosRes.value.items);
        setTodoSourceErrors(todosRes.value.source_errors ?? []);
        setTodoError(false);
      } else {
        setTodoItems([]);
        setTodoSourceErrors([]);
        setTodoError(true);
      }

      if (plansRes.status === 'fulfilled' && Array.isArray(plansRes.value.data?.items)) {
        const plans = plansRes.value.data.items;
        setRehabPlans(plans);
        setRehabPlansError(false);
        const feedbackPages = await Promise.allSettled(plans.map(plan => rehabPublications.feedback(plan.id, 0, 5)));
        if (cancelled) return;
        setFeedbackError(feedbackPages.some(result => result.status === 'rejected'));
        const reports = feedbackPages.flatMap((result, index) => result.status === 'fulfilled'
          ? result.value.data.items.map(feedback => ({ plan: plans[index], feedback })) : []);
        reports.sort((left, right) => Date.parse(right.feedback.performed_at) - Date.parse(left.feedback.performed_at));
        setRecentFeedback(reports.slice(0, 3));
      } else {
        setRehabPlans([]);
        setRecentFeedback([]);
        setFeedbackError(false);
        setRehabPlansError(true);
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
                        {!!metric.quality_flags?.length && (
                          <Typography variant="caption" color="warning.main">
                            数据质量标记：{metric.quality_flags.join('、')}
                          </Typography>
                        )}
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
                待办事项
              </Typography>
              <IconButton size="small" component={Link} to="/app/patient/todos" aria-label="查看全部待办">
                <ArrowForwardIcon />
              </IconButton>
            </Box>

            {loading ? (
              <PanelLoading />
            ) : todoError ? (
              <PanelError text="待办事项加载失败，请稍后重试" />
            ) : todoItems.length === 0 ? (
              <>
                {todoSourceErrors.length > 0 && <PanelError text="部分待办来源暂时不可用，当前列表可能不完整。" />}
                {todoSourceErrors.length === 0 && <PanelEmpty text="暂无待处理事项" />}
                <Box textAlign="center" mt={2}>
                  <Button component={Link} to="/app/patient/todos" size="small">查看待办中心</Button>
                </Box>
              </>
            ) : (
              <>
                {todoSourceErrors.length > 0 && <Typography variant="body2" color="warning.main" mb={1}>部分待办来源暂时不可用，当前列表可能不完整。</Typography>}
                <List sx={{ width: '100%' }}>
                  {todoItems.slice(0, 3).map((item, index) => (
                    <React.Fragment key={item.id}>
                      <ListItem component={Link} to={item.href} sx={{ borderRadius: 1, color: 'inherit', textDecoration: 'none' }}>
                        <ListItemIcon>
                          {item.type === 'questionnaire' ? <NoteIcon /> : <CheckCircleIcon />}
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
                    to="/app/patient/todos"
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

          {/* 已发布方案与患者本人提交的执行自述 */}
          <Paper sx={{ p: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">
                我的康复方案与执行反馈
              </Typography>
              <Button size="small" component={Link} to="/app/rehab-plans">查看全部方案</Button>
            </Box>

            {loading ? (
              <PanelLoading />
            ) : rehabPlansError ? (
              <PanelError text="康复方案加载失败，请稍后重试" />
            ) : (
              <>
                {rehabPlans.length === 0 ? <PanelEmpty text="暂无医护发布的康复方案" /> : <List dense>
                  {rehabPlans.map(plan => <ListItem key={plan.id} alignItems="flex-start" divider>
                    <ListItemText primary={plan.content.name || '康复方案'}
                      secondary={`发布时间：${formatDateTime(plan.published_at) ?? '未提供'}`} />
                    <Button size="small" component={Link} to={`/app/rehab-plans/${plan.id}`}>查看方案与反馈</Button>
                  </ListItem>)}
                </List>}
                <Typography variant="subtitle2" sx={{ mt: 2 }}>最近的执行自述</Typography>
                {feedbackError && <Typography variant="body2" color="error.main" sx={{ mt: 1 }}>部分自述记录暂时无法加载，请到方案详情重试。</Typography>}
                {recentFeedback.length === 0 && !feedbackError ? <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  暂无患者自述记录。方案详情页可提交执行情况；这里不推算训练完成率。
                </Typography> : recentFeedback.length > 0 ? <List dense>{recentFeedback.map(({ plan, feedback }) => <ListItem key={`${plan.id}:${feedback.id}`} divider>
                  <ListItemText primary={`${plan.content.name || '康复方案'} · ${feedback.execution_status === 'completed' ? '自述已执行' : feedback.execution_status === 'partial' ? '自述部分执行' : '自述未执行'}`}
                    secondary={`${formatDateTime(feedback.performed_at) ?? '时间未提供'}${feedback.feelings ? ` · ${feedback.feelings}` : ''}`} />
                </ListItem>)}</List> : null}
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

export default PatientMainDashboard;
