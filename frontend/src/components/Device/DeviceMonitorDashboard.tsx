import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Card, 
  CardContent, 
  Typography, 
  Grid, 
  Divider, 
  Chip, 
  Paper, 
  CircularProgress, 
  IconButton, 
  Alert, 
  AlertTitle, 
  ButtonGroup,
  Button,
  Tab,
  Tabs,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  TextField,
  Tooltip,
  LinearProgress
} from '@mui/material';
import { 
  DeviceHub, 
  Sync, 
  Warning, 
  Error as ErrorIcon, 
  CheckCircle, 
  Dashboard, 
  ShowChart, 
  Notifications, 
  InsertChart, 
  BatteryAlert, 
  SignalCellularAlt, 
  SignalCellularConnectedNoInternet0Bar, 
  Refresh, 
  Tune, 
  Settings 
} from '@mui/icons-material';
import { useSnackbar } from 'notistack';
import { deviceService } from '../../services/deviceService';
import { analyticsService } from '../../services/analyticsService';
import DeviceStatusCard from './DeviceStatusCard';
import DeviceDataGraph from './DeviceDataGraph';
import DeviceAlertList from './DeviceAlertList';
import PredictionAnalysisChart from '../Analytics/PredictionAnalysisChart';

// 设备状态类型定义
interface DeviceStatus {
  status: 'online' | 'offline' | 'error' | 'syncing';
  battery_level: number;
  signal_strength: number; // 1-5
  last_sync_time: string;
  message?: string;
}

// 设备类型定义
interface Device {
  id: string;
  name: string;
  type: string;
  manufacturer: string;
  model: string;
  status: 'active' | 'inactive' | 'maintenance' | 'deleted';
  firmware_version: string;
  connection_type: 'bluetooth' | 'wifi' | 'cable';
  patient_id: string;
  patient_name?: string;
  last_connected?: string;
  battery_level?: number;
}

// 设备问题类型定义
interface DeviceIssue {
  type: string;
  message: string;
  severity: 'high' | 'medium' | 'low';
}

// 设备状态监控响应类型
interface DeviceStatusResponse {
  device: Device;
  status: DeviceStatus;
  status_score: number;
  issues: DeviceIssue[];
  recommendations: string[];
}

// 设备预警类型定义
interface DeviceAlert {
  type: 'device_status' | 'data_anomaly';
  device_id: string;
  device_name: string;
  message: string;
  severity: 'high' | 'medium' | 'low';
  timestamp?: string;
  data_type?: string;
  value?: number;
  unit?: string;
  anomaly_score?: number;
  status_score?: number;
  issue_type?: string;
  recommendations?: string[];
}

// 仪表板属性接口
interface DeviceMonitorDashboardProps {
  patientId?: string;
  deviceId?: string;
  refreshInterval?: number; // 刷新间隔（秒）
}

/**
 * 设备监控仪表板组件
 * 提供设备状态监控、数据异常检测和预警功能的可视化界面
 */
const DeviceMonitorDashboard: React.FC<DeviceMonitorDashboardProps> = ({
  patientId,
  deviceId,
  refreshInterval = 30
}) => {
  // 状态
  const [activeTab, setActiveTab] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deviceStatuses, setDeviceStatuses] = useState<DeviceStatusResponse[]>([]);
  const [deviceAlerts, setDeviceAlerts] = useState<DeviceAlert[]>([]);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all');
  const [dataType, setDataType] = useState('heart_rate');
  const [predictionData, setPredictionData] = useState(null);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [predictionMethod, setPredictionMethod] = useState('ensemble');
  const [showConfidenceInterval, setShowConfidenceInterval] = useState(true);
  
  // Hooks
  const { enqueueSnackbar } = useSnackbar();

  // 处理刷新操作
  const handleRefresh = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      // 根据是否指定特定设备或患者，获取相关数据
      if (deviceId) {
        // 获取特定设备状态
        await fetchDeviceStatus(deviceId);
        // 获取特定设备预警
        await fetchDeviceAlerts(deviceId);
      } else if (patientId) {
        // 获取患者所有设备状态
        await fetchPatientDevicesStatus(patientId);
        // 获取患者所有设备预警
        await fetchPatientAlerts(patientId);
      } else {
        setError('请指定设备ID或患者ID');
        setDeviceStatuses([]);
        setDeviceAlerts([]);
      }
      
      setLastRefreshed(new Date());
    } catch (err) {
      console.error('刷新设备数据失败:', err);
      setError('刷新设备数据失败，请稍后重试');
    } finally {
      setIsLoading(false);
    }
  };

  // 获取特定设备状态
  const fetchDeviceStatus = async (deviceId: string) => {
    // 在实际项目中，使用真实API调用
    // 这里使用模拟数据
    // 示例: const response = await api.get(`/device-analysis/monitor/${deviceId}`);
    // setDeviceStatuses(response.data);
    
    // 模拟数据
    setTimeout(() => {
      setDeviceStatuses([
        {
          device: {
            id: deviceId,
            name: '智能血压计',
            type: '血压计',
            manufacturer: '康复科技',
            model: 'BP-200',
            status: 'active',
            firmware_version: '1.2.3',
            connection_type: 'bluetooth',
            patient_id: patientId || 'patient123',
            last_connected: new Date().toISOString()
          },
          status: {
            status: 'online',
            battery_level: 75,
            signal_strength: 4,
            last_sync_time: new Date().toISOString()
          },
          status_score: 15,
          issues: [],
          recommendations: ['定期检查设备状态，确保数据收集正常']
        }
      ]);
    }, 500);
  };

  // 获取患者所有设备状态
  const fetchPatientDevicesStatus = async (patientId: string) => {
    // 在实际项目中，使用真实API调用
    // 示例: const response = await api.get(`/device-analysis/patient-devices/${patientId}`);
    // setDeviceStatuses(response.data);
    
    // 模拟数据
    setTimeout(() => {
      setDeviceStatuses([
        {
          device: {
            id: 'device1',
            name: '智能血压计',
            type: '血压计',
            manufacturer: '康复科技',
            model: 'BP-200',
            status: 'active',
            firmware_version: '1.2.3',
            connection_type: 'bluetooth',
            patient_id: patientId,
            last_connected: new Date().toISOString()
          },
          status: {
            status: 'online',
            battery_level: 75,
            signal_strength: 4,
            last_sync_time: new Date().toISOString()
          },
          status_score: 15,
          issues: [],
          recommendations: ['定期检查设备状态，确保数据收集正常']
        },
        {
          device: {
            id: 'device2',
            name: '智能体温计',
            type: '体温计',
            manufacturer: '康复科技',
            model: 'TH-100',
            status: 'active',
            firmware_version: '2.0.1',
            connection_type: 'bluetooth',
            patient_id: patientId,
            last_connected: new Date(Date.now() - 86400000 * 2).toISOString() // 2天前
          },
          status: {
            status: 'offline',
            battery_level: 25,
            signal_strength: 1,
            last_sync_time: new Date(Date.now() - 86400000 * 2).toISOString()
          },
          status_score: 70,
          issues: [
            {
              type: 'offline',
              message: '设备离线',
              severity: 'medium'
            },
            {
              type: 'battery',
              message: '设备电量不足 (25%)',
              severity: 'medium'
            },
            {
              type: 'sync',
              message: '设备已超过2天未同步数据',
              severity: 'medium'
            }
          ],
          recommendations: [
            '检查设备是否开启、电池是否充足，并确保设备在信号范围内',
            '请尽快为设备充电',
            '手动触发数据同步，检查设备同步功能是否正常'
          ]
        }
      ]);
    }, 500);
  };

  // 获取特定设备预警
  const fetchDeviceAlerts = async (deviceId: string) => {
    // 在实际项目中，使用真实API调用
    // 示例: const response = await api.get(`/device-analysis/alerts/device/${deviceId}`);
    // setDeviceAlerts(response.data);
    
    // 模拟数据
    setTimeout(() => {
      setDeviceAlerts([
        {
          type: 'data_anomaly',
          device_id: deviceId,
          device_name: '智能血压计',
          message: '检测到blood_pressure_systolic数据异常值: 160mmHg',
          severity: 'medium',
          timestamp: new Date().toISOString(),
          data_type: 'blood_pressure_systolic',
          value: 160,
          unit: 'mmHg',
          anomaly_score: 65
        }
      ]);
    }, 700);
  };

  // 获取患者所有设备预警
  const fetchPatientAlerts = async (patientId: string) => {
    // 在实际项目中，使用真实API调用
    // 示例: const response = await api.get(`/device-analysis/alerts/patient/${patientId}`);
    // setDeviceAlerts(response.data);
    
    // 模拟数据
    setTimeout(() => {
      setDeviceAlerts([
        {
          type: 'device_status',
          device_id: 'device2',
          device_name: '智能体温计',
          message: '设备离线',
          severity: 'medium',
          issue_type: 'offline',
          status_score: 70,
          recommendations: ['检查设备是否开启、电池是否充足，并确保设备在信号范围内']
        },
        {
          type: 'data_anomaly',
          device_id: 'device1',
          device_name: '智能血压计',
          message: '检测到blood_pressure_systolic数据异常值: 160mmHg',
          severity: 'medium',
          timestamp: new Date().toISOString(),
          data_type: 'blood_pressure_systolic',
          value: 160,
          unit: 'mmHg',
          anomaly_score: 65
        }
      ]);
    }, 700);
  };

  // 获取指定严重程度过滤后的预警
  const getFilteredAlerts = () => {
    if (severityFilter === 'all') {
      return deviceAlerts;
    }
    return deviceAlerts.filter(alert => alert.severity === severityFilter);
  };
  
  // 获取按设备分组的预警
  const getAlertsByDevice = () => {
    const alertsByDevice: Record<string, DeviceAlert[]> = {};
    
    getFilteredAlerts().forEach(alert => {
      if (!alertsByDevice[alert.device_id]) {
        alertsByDevice[alert.device_id] = [];
      }
      alertsByDevice[alert.device_id].push(alert);
    });
    
    return alertsByDevice;
  };

  // 处理自动刷新开关
  const handleAutoRefreshToggle = () => {
    setAutoRefresh(!autoRefresh);
  };

  // 处理严重程度过滤器变更
  const handleSeverityFilterChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setSeverityFilter(event.target.value as 'all' | 'high' | 'medium' | 'low');
  };

  // 处理标签页变更
  const handleTabChange = (event: React.ChangeEvent<{}>, newValue: number) => {
    setActiveTab(newValue);
  };

  // 加载预测数据
  const loadPredictionData = async () => {
    if (!deviceId || !dataType) return;
    
    try {
      setPredictionLoading(true);
      const result = await analyticsService.getAdvancedPrediction(
        deviceId,
        dataType,
        30, // 分析最近30天的数据
        14, // 预测未来14天
        predictionMethod,
        showConfidenceInterval,
        'day'
      );
      setPredictionData(result);
    } catch (error) {
      console.error('加载预测数据失败:', error);
    } finally {
      setPredictionLoading(false);
    }
  };
  
  // 当设备ID或数据类型变化时加载预测数据
  useEffect(() => {
    loadPredictionData();
  }, [deviceId, dataType, predictionMethod, showConfidenceInterval]);
  
  // 预测方法变更处理
  const handlePredictionMethodChange = (method) => {
    setPredictionMethod(method);
  };
  
  // 置信区间显示控制
  const handleConfidenceIntervalChange = (show) => {
    setShowConfidenceInterval(show);
  };

  // 初始加载和定时刷新
  useEffect(() => {
    // 首次加载数据
    handleRefresh();
    
    // 设置自动刷新定时器
    let refreshTimer: NodeJS.Timeout;
    if (autoRefresh) {
      refreshTimer = setInterval(() => {
        handleRefresh();
      }, refreshInterval * 1000);
    }
    
    // 清理定时器
    return () => {
      if (refreshTimer) {
        clearInterval(refreshTimer);
      }
    };
  }, [deviceId, patientId, refreshInterval, autoRefresh]);

  // 设备状态展示
  const renderDeviceStatus = () => {
    if (deviceStatuses.length === 0) {
      return (
        <Box textAlign="center" py={4}>
          <Typography variant="subtitle1" color="textSecondary">
            没有找到设备状态信息
          </Typography>
        </Box>
      );
    }

    return (
      <Grid container spacing={3}>
        {deviceStatuses.map((deviceStatus) => (
          <Grid item xs={12} md={6} key={deviceStatus.device.id}>
            <Paper elevation={2} sx={{ p: 2, height: '100%' }}>
              <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
                <Typography variant="h6" component="h3">
                  {deviceStatus.device.name}
                </Typography>
                {renderStatusChip(deviceStatus.status.status)}
              </Box>

              <Typography variant="body2" color="textSecondary" gutterBottom>
                {deviceStatus.device.manufacturer} {deviceStatus.device.model} ({deviceStatus.device.type})
              </Typography>

              {/* 设备基本信息 */}
              <Grid container spacing={1} sx={{ mt: 1 }}>
                <Grid item xs={6}>
                  <Typography variant="body2">
                    <strong>固件版本:</strong> {deviceStatus.device.firmware_version}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">
                    <strong>连接方式:</strong> {renderConnectionType(deviceStatus.device.connection_type)}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">
                    <strong>最后连接:</strong> {new Date(deviceStatus.device.last_connected || '').toLocaleString()}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">
                    <strong>最后同步:</strong> {new Date(deviceStatus.status.last_sync_time).toLocaleString()}
                  </Typography>
                </Grid>
              </Grid>

              {/* 设备状态信息 */}
              <Box mt={2}>
                <Grid container spacing={2}>
                  {/* 电池电量 */}
                  <Grid item xs={6}>
                    <Paper variant="outlined" sx={{ p: 1 }}>
                      <Typography variant="subtitle2" gutterBottom>电池电量</Typography>
                      <Box display="flex" alignItems="center">
                        {renderBatteryIcon(deviceStatus.status.battery_level)}
                        <Box sx={{ width: '100%', ml: 1 }}>
                          <LinearProgress 
                            variant="determinate" 
                            value={deviceStatus.status.battery_level} 
                            color={getBatteryColor(deviceStatus.status.battery_level)}
                            sx={{ height: 10, borderRadius: 5 }}
                          />
                          <Typography variant="caption" display="block" textAlign="right" mt={0.5}>
                            {deviceStatus.status.battery_level}%
                          </Typography>
                        </Box>
                      </Box>
                    </Paper>
                  </Grid>

                  {/* 信号强度 */}
                  <Grid item xs={6}>
                    <Paper variant="outlined" sx={{ p: 1 }}>
                      <Typography variant="subtitle2" gutterBottom>信号强度</Typography>
                      <Box display="flex" alignItems="center">
                        {renderSignalIcon(deviceStatus.status.signal_strength)}
                        <Box sx={{ width: '100%', ml: 1 }}>
                          <Box display="flex" justifyContent="space-between">
                            {[1, 2, 3, 4, 5].map((level) => (
                              <Box 
                                key={level}
                                width="18%" 
                                height={level * 4 + 2} 
                                bgcolor={level <= deviceStatus.status.signal_strength ? getSignalColor(deviceStatus.status.signal_strength) : 'grey.300'} 
                                borderRadius={1}
                              />
                            ))}
                          </Box>
                          <Typography variant="caption" display="block" textAlign="right" mt={0.5}>
                            {deviceStatus.status.signal_strength}/5
                          </Typography>
                        </Box>
                      </Box>
                    </Paper>
                  </Grid>
                </Grid>
              </Box>

              {/* 设备状态评分 */}
              <Box mt={2}>
                <Paper variant="outlined" sx={{ p: 1 }}>
                  <Typography variant="subtitle2" gutterBottom>设备状态评分</Typography>
                  <Box display="flex" alignItems="center">
                    <Box sx={{ position: 'relative', display: 'inline-flex', mr: 2 }}>
                      <CircularProgress 
                        variant="determinate" 
                        value={100 - deviceStatus.status_score} 
                        color={getStatusScoreColor(deviceStatus.status_score)}
                        size={50}
                      />
                      <Box
                        sx={{
                          top: 0,
                          left: 0,
                          bottom: 0,
                          right: 0,
                          position: 'absolute',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <Typography variant="caption" component="div" color="text.secondary">
                          {100 - deviceStatus.status_score}
                        </Typography>
                      </Box>
                    </Box>
                    <Box sx={{ width: '100%' }}>
                      <Typography variant="body2">
                        {deviceStatus.status_score < 20 ? '状态良好' : 
                         deviceStatus.status_score < 50 ? '状态一般' : 
                         deviceStatus.status_score < 80 ? '状态不佳' : '状态严重'}
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        {deviceStatus.status_score < 20 ? '设备运行正常，无需干预' : 
                         deviceStatus.status_score < 50 ? '设备有轻微问题，建议关注' : 
                         deviceStatus.status_score < 80 ? '设备存在问题，需要处理' : '设备状态严重，需立即处理'}
                      </Typography>
                    </Box>
                  </Box>
                </Paper>
              </Box>

              {/* 设备问题列表 */}
              {deviceStatus.issues.length > 0 && (
                <Box mt={2}>
                  <Typography variant="subtitle2" gutterBottom>检测到的问题</Typography>
                  {deviceStatus.issues.map((issue, index) => (
                    <Alert 
                      key={index} 
                      severity={getSeverityType(issue.severity)} 
                      sx={{ mb: 1 }}
                      icon={getIssueIcon(issue.type)}
                    >
                      {issue.message}
                    </Alert>
                  ))}
                </Box>
              )}

              {/* 设备建议 */}
              {deviceStatus.recommendations.length > 0 && (
                <Box mt={2}>
                  <Typography variant="subtitle2" gutterBottom>建议</Typography>
                  <ul style={{ margin: 0, paddingLeft: '1.5rem' }}>
                    {deviceStatus.recommendations.map((recommendation, index) => (
                      <li key={index}>
                        <Typography variant="body2">{recommendation}</Typography>
                      </li>
                    ))}
                  </ul>
                </Box>
              )}

              {/* 操作按钮 */}
              <Box mt={3} display="flex" justifyContent="flex-end">
                <Button 
                  size="small" 
                  startIcon={<Sync />} 
                  variant="outlined" 
                  sx={{ mr: 1 }}
                >
                  同步数据
                </Button>
                <Button 
                  size="small" 
                  startIcon={<Settings />} 
                  variant="outlined" 
                  color="primary"
                >
                  设备设置
                </Button>
              </Box>
            </Paper>
          </Grid>
        ))}
      </Grid>
    );
  };

  // 设备预警展示
  const renderDeviceAlerts = () => {
    const filteredAlerts = getFilteredAlerts();
    
    if (filteredAlerts.length === 0) {
      return (
        <Box textAlign="center" py={4}>
          <Typography variant="subtitle1" color="textSecondary">
            没有找到符合条件的预警信息
          </Typography>
        </Box>
      );
    }

    return (
      <div>
        {/* 严重程度过滤器 */}
        <Box mb={3} display="flex" justifyContent="flex-end">
          <FormControl variant="outlined" size="small" sx={{ minWidth: 150 }}>
            <InputLabel id="severity-filter-label">严重程度</InputLabel>
            <Select
              labelId="severity-filter-label"
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as any)}
              label="严重程度"
            >
              <MenuItem value="all">全部</MenuItem>
              <MenuItem value="high">高</MenuItem>
              <MenuItem value="medium">中</MenuItem>
              <MenuItem value="low">低</MenuItem>
            </Select>
          </FormControl>
        </Box>

        {/* 预警列表，按设备分组 */}
        {Object.entries(getAlertsByDevice()).map(([deviceId, alerts]) => (
          <Paper key={deviceId} elevation={1} sx={{ mb: 3, overflow: 'hidden' }}>
            {/* 设备名称标题 */}
            <Box bgcolor="primary.main" color="primary.contrastText" p={1.5}>
              <Typography variant="h6">
                {alerts[0].device_name} ({alerts.length}个预警)
              </Typography>
            </Box>

            {/* 预警项目列表 */}
            <div>
              {alerts.map((alert, index) => (
                <Box 
                  key={`${alert.device_id}-${index}`}
                  p={2}
                  sx={{ 
                    borderBottom: index < alerts.length - 1 ? '1px solid' : 'none',
                    borderColor: 'divider'
                  }}
                >
                  <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                    <Box display="flex" alignItems="center">
                      {getAlertIcon(alert)}
                      <Box ml={2}>
                        <Typography variant="subtitle1">
                          {alert.message}
                        </Typography>
                        
                        <Typography variant="body2" color="textSecondary">
                          {alert.type === 'data_anomaly' 
                            ? `数据异常 | 分数: ${alert.anomaly_score?.toFixed(0)}/100` 
                            : `设备状态 | 分数: ${alert.status_score?.toFixed(0)}/100`}
                          
                          {alert.timestamp && ` | 时间: ${new Date(alert.timestamp).toLocaleString()}`}
                        </Typography>
                      </Box>
                    </Box>
                    <Chip 
                      label={getSeverityLabel(alert.severity)} 
                      color={getSeverityColor(alert.severity)} 
                      size="small"
                    />
                  </Box>

                  {/* 推荐处理方法 */}
                  {alert.recommendations && alert.recommendations.length > 0 && (
                    <Box mt={1.5} ml={6}>
                      <Typography variant="subtitle2">推荐处理方法:</Typography>
                      <ul style={{ margin: '0.5rem 0', paddingLeft: '1.5rem' }}>
                        {alert.recommendations.map((recommendation, i) => (
                          <li key={i}>
                            <Typography variant="body2">{recommendation}</Typography>
                          </li>
                        ))}
                      </ul>
                    </Box>
                  )}

                  {/* 数据异常详情 */}
                  {alert.type === 'data_anomaly' && alert.data_type && (
                    <Box mt={1.5} ml={6}>
                      <Button 
                        variant="outlined" 
                        size="small" 
                        startIcon={<ShowChart />}
                      >
                        查看数据趋势
                      </Button>
                    </Box>
                  )}
                </Box>
              ))}
            </div>
          </Paper>
        ))}
      </div>
    );
  };

  // 辅助函数：渲染状态标签
  const renderStatusChip = (status: string) => {
    switch(status) {
      case 'online':
        return <Chip size="small" label="在线" color="success" />;
      case 'offline':
        return <Chip size="small" label="离线" color="error" />;
      case 'error':
        return <Chip size="small" label="错误" color="error" />;
      case 'syncing':
        return <Chip size="small" label="同步中" color="info" />;
      default:
        return <Chip size="small" label="未知" color="default" />;
    }
  };

  // 渲染连接类型
  const renderConnectionType = (type: string) => {
    switch(type) {
      case 'bluetooth':
        return '蓝牙';
      case 'wifi':
        return 'Wi-Fi';
      case 'cable':
        return '有线';
      default:
        return type;
    }
  };

  // 渲染电池图标
  const renderBatteryIcon = (level: number) => {
    if (level <= 10) {
      return <BatteryAlert color="error" />;
    } else if (level <= 30) {
      return <BatteryAlert color="warning" />;
    } else {
      return <BatteryAlert color="success" />;
    }
  };

  // 渲染信号图标
  const renderSignalIcon = (strength: number) => {
    if (strength <= 1) {
      return <SignalCellularConnectedNoInternet0Bar color="error" />;
    } else if (strength <= 3) {
      return <SignalCellularAlt color="warning" />;
    } else {
      return <SignalCellularAlt color="success" />;
    }
  };

  // 获取电池颜色
  const getBatteryColor = (level: number): 'error' | 'warning' | 'success' => {
    if (level <= 10) {
      return 'error';
    } else if (level <= 30) {
      return 'warning';
    } else {
      return 'success';
    }
  };

  // 获取信号颜色
  const getSignalColor = (strength: number): string => {
    if (strength <= 1) {
      return 'error.main';
    } else if (strength <= 3) {
      return 'warning.main';
    } else {
      return 'success.main';
    }
  };

  // 获取状态分数对应颜色
  const getStatusScoreColor = (score: number): 'error' | 'warning' | 'success' => {
    if (score >= 80) {
      return 'error';
    } else if (score >= 50) {
      return 'warning';
    } else if (score >= 20) {
      return 'warning';
    } else {
      return 'success';
    }
  };

  // 获取严重程度对应的Alert类型
  const getSeverityType = (severity: string): 'error' | 'warning' | 'info' => {
    switch(severity) {
      case 'high':
        return 'error';
      case 'medium':
        return 'warning';
      case 'low':
        return 'info';
      default:
        return 'info';
    }
  };

  // 获取问题类型对应图标
  const getIssueIcon = (type: string) => {
    switch(type) {
      case 'error':
        return <ErrorIcon />;
      case 'offline':
        return <SignalCellularConnectedNoInternet0Bar />;
      case 'battery':
        return <BatteryAlert />;
      case 'signal':
        return <SignalCellularAlt />;
      case 'sync':
        return <Sync />;
      case 'firmware':
        return <Settings />;
      default:
        return <Warning />;
    }
  };

  // 获取预警图标
  const getAlertIcon = (alert: DeviceAlert) => {
    if (alert.type === 'data_anomaly') {
      return (
        <ShowChart 
          fontSize="large" 
          color={getSeverityAlertColor(alert.severity)} 
        />
      );
    } else if (alert.type === 'device_status') {
      switch(alert.issue_type) {
        case 'error':
          return <ErrorIcon fontSize="large" color={getSeverityAlertColor(alert.severity)} />;
        case 'offline':
          return <SignalCellularConnectedNoInternet0Bar fontSize="large" color={getSeverityAlertColor(alert.severity)} />;
        case 'battery':
          return <BatteryAlert fontSize="large" color={getSeverityAlertColor(alert.severity)} />;
        case 'signal':
          return <SignalCellularAlt fontSize="large" color={getSeverityAlertColor(alert.severity)} />;
        case 'sync':
          return <Sync fontSize="large" color={getSeverityAlertColor(alert.severity)} />;
        case 'firmware':
          return <Settings fontSize="large" color={getSeverityAlertColor(alert.severity)} />;
        default:
          return <Warning fontSize="large" color={getSeverityAlertColor(alert.severity)} />;
      }
    } else {
      return <Warning fontSize="large" color={getSeverityAlertColor(alert.severity)} />;
    }
  };

  // 获取严重程度对应的Alert颜色
  const getSeverityAlertColor = (severity: string): 'error' | 'warning' | 'info' => {
    switch(severity) {
      case 'high':
        return 'error';
      case 'medium':
        return 'warning';
      case 'low':
        return 'info';
      default:
        return 'info';
    }
  };

  // 获取严重程度标签文字
  const getSeverityLabel = (severity: string): string => {
    switch(severity) {
      case 'high':
        return '高';
      case 'medium':
        return '中';
      case 'low':
        return '低';
      default:
        return '未知';
    }
  };

  // 获取严重程度Chip颜色
  const getSeverityColor = (severity: string): 'error' | 'warning' | 'info' | 'default' => {
    switch(severity) {
      case 'high':
        return 'error';
      case 'medium':
        return 'warning';
      case 'low':
        return 'info';
      default:
        return 'default';
    }
  };

  return (
    <Box>
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h5" component="h2">
              <DeviceHub sx={{ mr: 1, verticalAlign: 'middle' }} />
              设备监控仪表板
            </Typography>
            <Box>
              <Tooltip title={autoRefresh ? "关闭自动刷新" : "开启自动刷新"}>
                <IconButton 
                  color={autoRefresh ? "primary" : "default"} 
                  onClick={handleAutoRefreshToggle}
                >
                  <Sync />
                </IconButton>
              </Tooltip>
              <Tooltip title="立即刷新">
                <IconButton 
                  onClick={handleRefresh} 
                  disabled={isLoading}
                >
                  <Refresh />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>

          {isLoading && <LinearProgress sx={{ mb: 2 }} />}

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              <AlertTitle>错误</AlertTitle>
              {error}
            </Alert>
          )}

          <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
            <Tabs 
              value={activeTab} 
              onChange={handleTabChange} 
              aria-label="设备监控选项卡"
            >
              <Tab 
                icon={<Dashboard />} 
                label="设备状态" 
                id="device-status-tab"
                aria-controls="device-status-panel"
              />
              <Tab 
                icon={<Notifications />} 
                label={`预警信息 (${getFilteredAlerts().length})`}
                id="device-alerts-tab"
                aria-controls="device-alerts-panel"
              />
            </Tabs>
          </Box>

          <Box role="tabpanel" hidden={activeTab !== 0} id="device-status-panel">
            {activeTab === 0 && renderDeviceStatus()}
          </Box>

          <Box role="tabpanel" hidden={activeTab !== 1} id="device-alerts-panel">
            {activeTab === 1 && renderDeviceAlerts()}
          </Box>

          <Box mt={2} display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="caption" color="textSecondary">
              最后更新: {lastRefreshed.toLocaleString()}
            </Typography>
            {autoRefresh && (
              <Typography variant="caption" color="textSecondary">
                下次更新: {new Date(lastRefreshed.getTime() + refreshInterval * 1000).toLocaleString()}
              </Typography>
            )}
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
};

export default DeviceMonitorDashboard; 