import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  Divider,
  IconButton,
  CircularProgress,
  List,
  ListItem,
  ListItemText,
  Alert,
  Snackbar,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  LinearProgress,
  Stack,
  Tooltip
} from '@mui/material';
import {
  WarningAmber as WarningIcon,
  Check as CheckIcon,
  Error as ErrorIcon,
  BatteryAlert as BatteryIcon,
  SignalWifiStatusbar4Bar as SignalIcon,
  SignalWifiStatusbarConnectedNoInternet0 as NoSignalIcon,
  DataUsage as DataIcon,
  Refresh as RefreshIcon,
  Build as RepairIcon,
  Info as InfoIcon
} from '@mui/icons-material';
import { deviceService } from '../../services/deviceService';
import { formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 设备状态类型
type DeviceStatus = 'online' | 'offline' | 'error' | 'syncing' | 'idle';

// 设备信息接口
interface Device {
  id: string;
  name: string;
  type: string;
  status: DeviceStatus;
  batteryLevel: number;
  signalStrength: number; // 1-5
  lastSyncTime: string;
  firmwareVersion?: string;
  firmwareUpdateAvailable?: boolean;
  errorMessage?: string;
  patientName: string;
  model?: string;
  manufacturer?: string;
}

// 修复结果接口
interface RepairResult {
  action: string;
  success: boolean;
  message?: string;
  reason?: string;
}

// 修复响应接口
interface RepairResponse {
  success: boolean;
  message: string;
  repair_actions: string[];
  repair_results: RepairResult[];
  new_status?: any;
}

const DeviceMonitoringDashboard: React.FC = () => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [repairingDevice, setRepairingDevice] = useState<string | null>(null);
  const [repairDialogOpen, setRepairDialogOpen] = useState(false);
  const [repairResult, setRepairResult] = useState<RepairResponse | null>(null);
  const [snackbar, setSnackbar] = useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });

  // 加载设备数据
  useEffect(() => {
    const fetchDevices = async () => {
      try {
        setLoading(true);
        // 这里应该是从API获取设备列表，现在使用模拟数据
        const mockDevices: Device[] = [
          {
            id: '1',
            name: '智能血压计A',
            type: '血压计',
            status: 'online',
            batteryLevel: 85,
            signalStrength: 4,
            lastSyncTime: new Date(Date.now() - 3600000).toISOString(),
            firmwareVersion: '2.1.0',
            firmwareUpdateAvailable: false,
            patientName: '张三',
            model: 'BP-200',
            manufacturer: '康佳医疗'
          },
          {
            id: '2',
            name: '智能血糖仪B',
            type: '血糖仪',
            status: 'offline',
            batteryLevel: 15,
            signalStrength: 1,
            lastSyncTime: new Date(Date.now() - 86400000 * 3).toISOString(),
            firmwareVersion: '1.5.0',
            firmwareUpdateAvailable: true,
            patientName: '李四',
            model: 'GM-100',
            manufacturer: '康佳医疗'
          },
          {
            id: '3',
            name: '智能体温计C',
            type: '体温计',
            status: 'error',
            batteryLevel: 45,
            signalStrength: 3,
            lastSyncTime: new Date(Date.now() - 86400000).toISOString(),
            errorMessage: '传感器异常',
            patientName: '王五',
            model: 'TM-50',
            manufacturer: '康佳医疗'
          }
        ];
        
        setDevices(mockDevices);
        setLoading(false);
      } catch (err) {
        setError('加载设备数据失败');
        setLoading(false);
        console.error('加载设备数据失败:', err);
      }
    };

    fetchDevices();
  }, []);

  // 修复设备
  const handleRepairDevice = async (deviceId: string) => {
    try {
      setRepairingDevice(deviceId);
      
      // 调用设备修复API
      const response = await deviceService.repairDevice(deviceId);
      setRepairResult(response);
      
      // 打开修复结果对话框
      setRepairDialogOpen(true);
      
      // 如果修复成功，更新设备状态
      if (response.success && response.new_status) {
        setDevices(prev => 
          prev.map(device => 
            device.id === deviceId 
              ? {
                  ...device,
                  status: response.new_status.status,
                  batteryLevel: response.new_status.battery_level,
                  signalStrength: response.new_status.signal_strength,
                  lastSyncTime: response.new_status.last_sync_time,
                  firmwareUpdateAvailable: false
                }
              : device
          )
        );
      }
      
      setSnackbar({
        open: true,
        message: response.success ? '设备修复成功' : '设备修复失败',
        severity: response.success ? 'success' : 'error'
      });
    } catch (err) {
      console.error('修复设备失败:', err);
      setSnackbar({
        open: true,
        message: '修复设备失败，请稍后重试',
        severity: 'error'
      });
    } finally {
      setRepairingDevice(null);
    }
  };

  // 刷新设备状态
  const handleRefreshStatus = async (deviceId: string) => {
    try {
      // 实际应用中应该调用API
      // 这里使用模拟数据
      const updatedDevices = devices.map(device => {
        if (device.id === deviceId) {
          return {
            ...device,
            batteryLevel: Math.min(100, device.batteryLevel + 5),
            status: device.status === 'offline' ? 'online' : device.status,
            lastSyncTime: new Date().toISOString()
          };
        }
        return device;
      });
      
      setDevices(updatedDevices);
      
      setSnackbar({
        open: true,
        message: '设备状态已更新',
        severity: 'success'
      });
    } catch (err) {
      console.error('刷新设备状态失败:', err);
      setSnackbar({
        open: true,
        message: '刷新设备状态失败',
        severity: 'error'
      });
    }
  };

  // 状态标签渲染
  const renderStatusChip = (status: DeviceStatus) => {
    switch (status) {
      case 'online':
        return <Chip icon={<CheckIcon />} label="在线" color="success" size="small" />;
      case 'offline':
        return <Chip icon={<WarningIcon />} label="离线" color="default" size="small" />;
      case 'error':
        return <Chip icon={<ErrorIcon />} label="错误" color="error" size="small" />;
      case 'syncing':
        return <Chip icon={<DataIcon />} label="同步中" color="info" size="small" />;
      case 'idle':
        return <Chip icon={<InfoIcon />} label="空闲" color="default" size="small" />;
      default:
        return <Chip label="未知" color="default" size="small" />;
    }
  };

  // 电池状态渲染
  const renderBatteryStatus = (level: number) => {
    let color = 'success';
    if (level < 20) color = 'error';
    else if (level < 50) color = 'warning';

    return (
      <Box display="flex" alignItems="center">
        <BatteryIcon color={color as 'success' | 'error' | 'warning'} />
        <Typography variant="body2" sx={{ ml: 0.5 }}>
          {level}%
        </Typography>
      </Box>
    );
  };

  // 信号强度渲染
  const renderSignalStrength = (strength: number) => {
    let icon = <NoSignalIcon color="error" />;
    let label = '无信号';
    let color: 'error' | 'warning' | 'success' = 'error';

    if (strength >= 4) {
      icon = <SignalIcon color="success" />;
      label = '信号强';
      color = 'success';
    } else if (strength >= 2) {
      icon = <SignalIcon color="warning" />;
      label = '信号中';
      color = 'warning';
    }

    return (
      <Box display="flex" alignItems="center">
        {icon}
        <Typography variant="body2" sx={{ ml: 0.5 }} color={`${color}.main`}>
          {label}
        </Typography>
      </Box>
    );
  };

  // 是否需要维护
  const needsMaintenance = (device: Device) => {
    return (
      device.status === 'error' ||
      device.status === 'offline' ||
      device.batteryLevel < 20 ||
      device.signalStrength < 2 ||
      device.firmwareUpdateAvailable ||
      new Date(device.lastSyncTime).getTime() < Date.now() - 86400000 * 2 // 2天未同步
    );
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '400px' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        {error}
      </Alert>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" gutterBottom>
        设备监控仪表盘
      </Typography>
      
      <Box sx={{ mb: 3 }}>
        <Typography variant="body1" color="text.secondary">
          监控设备的状态、电量和信号强度，及时发现异常情况。
        </Typography>
      </Box>
      
      <Grid container spacing={3}>
        {/* 设备总览卡片 */}
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2, height: '100%' }}>
            <Typography variant="h6" gutterBottom>
              设备总览
            </Typography>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                总设备数: {devices.length}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
              <Chip
                icon={<CheckIcon />}
                label={`在线: ${devices.filter(d => d.status === 'online').length}`}
                color="success"
                variant="outlined"
              />
              <Chip
                icon={<WarningIcon />}
                label={`离线: ${devices.filter(d => d.status === 'offline').length}`}
                color="default"
                variant="outlined"
              />
              <Chip
                icon={<ErrorIcon />}
                label={`错误: ${devices.filter(d => d.status === 'error').length}`}
                color="error"
                variant="outlined"
              />
            </Box>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" gutterBottom>
              需要维护的设备
            </Typography>
            <List dense>
              {devices.filter(needsMaintenance).map(device => (
                <ListItem key={device.id}>
                  <ListItemText
                    primary={device.name}
                    secondary={`${device.patientName} | ${device.type}`}
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    color="primary"
                    onClick={() => handleRepairDevice(device.id)}
                    startIcon={repairingDevice === device.id ? <CircularProgress size={16} /> : <RepairIcon />}
                    disabled={repairingDevice === device.id}
                  >
                    修复
                  </Button>
                </ListItem>
              ))}
              {devices.filter(needsMaintenance).length === 0 && (
                <ListItem>
                  <ListItemText
                    primary="所有设备状态良好"
                    secondary="无需维护"
                  />
                </ListItem>
              )}
            </List>
          </Paper>
        </Grid>
        
        {/* 设备状态卡片 */}
        <Grid item xs={12} md={8}>
          <Grid container spacing={2}>
            {devices.map(device => (
              <Grid item xs={12} key={device.id}>
                <Card>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                      <Box>
                        <Typography variant="h6">{device.name}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {device.type} | {device.model} | {device.manufacturer}
                        </Typography>
                      </Box>
                      {renderStatusChip(device.status)}
                    </Box>
                    
                    <Divider sx={{ my: 1 }} />
                    
                    <Grid container spacing={2} sx={{ mt: 1 }}>
                      <Grid item xs={6} sm={3}>
                        <Typography variant="body2" color="text.secondary">电池</Typography>
                        {renderBatteryStatus(device.batteryLevel)}
                      </Grid>
                      <Grid item xs={6} sm={3}>
                        <Typography variant="body2" color="text.secondary">信号</Typography>
                        {renderSignalStrength(device.signalStrength)}
                      </Grid>
                      <Grid item xs={6} sm={3}>
                        <Typography variant="body2" color="text.secondary">最后同步</Typography>
                        <Typography variant="body2">
                          {formatDistanceToNow(new Date(device.lastSyncTime), { addSuffix: true, locale: zhCN })}
                        </Typography>
                      </Grid>
                      <Grid item xs={6} sm={3}>
                        <Typography variant="body2" color="text.secondary">固件版本</Typography>
                        <Box display="flex" alignItems="center">
                          <Typography variant="body2">
                            {device.firmwareVersion || '未知'}
                          </Typography>
                          {device.firmwareUpdateAvailable && (
                            <Tooltip title="有可用更新">
                              <InfoIcon color="info" fontSize="small" sx={{ ml: 0.5 }} />
                            </Tooltip>
                          )}
                        </Box>
                      </Grid>
                    </Grid>
                    
                    {device.status === 'error' && (
                      <Alert severity="error" sx={{ mt: 2 }}>
                        错误: {device.errorMessage || '未知错误'}
                      </Alert>
                    )}
                    
                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
                      <Button
                        size="small"
                        startIcon={<RefreshIcon />}
                        onClick={() => handleRefreshStatus(device.id)}
                        sx={{ mr: 1 }}
                      >
                        刷新状态
                      </Button>
                      <Button
                        size="small"
                        startIcon={<RepairIcon />}
                        variant="outlined"
                        color="primary"
                        onClick={() => handleRepairDevice(device.id)}
                        disabled={repairingDevice === device.id}
                      >
                        {repairingDevice === device.id ? (
                          <>
                            <CircularProgress size={16} sx={{ mr: 1 }} />
                            修复中...
                          </>
                        ) : (
                          '修复设备'
                        )}
                      </Button>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Grid>
      </Grid>
      
      {/* 修复结果对话框 */}
      <Dialog
        open={repairDialogOpen}
        onClose={() => setRepairDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          设备修复结果
        </DialogTitle>
        <DialogContent>
          {repairResult && (
            <Box>
              <Alert 
                severity={repairResult.success ? 'success' : 'error'}
                sx={{ mb: 2 }}
              >
                {repairResult.message}
              </Alert>
              
              <Typography variant="subtitle2" gutterBottom>
                执行的修复操作:
              </Typography>
              <List dense>
                {repairResult.repair_results.map((result, index) => (
                  <ListItem key={index}>
                    <ListItemText
                      primary={result.action}
                      secondary={result.message || result.reason || (result.success ? '修复成功' : '修复失败')}
                    />
                    {result.success ? (
                      <CheckIcon color="success" />
                    ) : (
                      <ErrorIcon color="error" />
                    )}
                  </ListItem>
                ))}
              </List>
              
              {repairResult.new_status && (
                <>
                  <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>
                    新状态:
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">状态</Typography>
                      <Typography variant="body2">
                        {repairResult.new_status.status}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">电池电量</Typography>
                      <Typography variant="body2">
                        {repairResult.new_status.battery_level}%
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">信号强度</Typography>
                      <Typography variant="body2">
                        {repairResult.new_status.signal_strength}/5
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">最后同步时间</Typography>
                      <Typography variant="body2">
                        {repairResult.new_status.last_sync_time ? 
                          formatDistanceToNow(new Date(repairResult.new_status.last_sync_time), { addSuffix: true, locale: zhCN }) : 
                          '未知'}
                      </Typography>
                    </Grid>
                  </Grid>
                </>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRepairDialogOpen(false)}>
            关闭
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 提示消息 */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
      >
        <Alert 
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))} 
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default DeviceMonitoringDashboard; 