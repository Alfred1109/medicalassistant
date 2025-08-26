import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemSecondaryAction,
  ListItemText,
  Paper,
  Snackbar,
  Tab,
  Tabs,
  TextField,
  Typography,
  Alert,
  Stack,
} from '@mui/material';
import {
  Sync as SyncIcon,
  Watch as WatchIcon,
  BloodtypeOutlined as BloodIcon,
  MonitorHeart as HeartIcon,
  DevicesOther as OtherDeviceIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Check as CheckIcon,
  Warning as WarningIcon,
  Add as AddIcon,
} from '@mui/icons-material';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch, RootState } from '../../store';
import { formatDate } from '../../utils/dateUtils';

// 定义接口
interface Device {
  id: string;
  name: string;
  type: string;
  status: 'connected' | 'disconnected' | 'syncing';
  lastSync: string | null;
  batteryLevel?: number;
  manufacturer?: string;
}

interface SyncHistory {
  id: string;
  deviceId: string;
  deviceName: string;
  timestamp: string;
  status: 'success' | 'failed' | 'partial';
  recordsCount: number;
  message?: string;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 选项卡面板组件
const TabPanel = (props: TabPanelProps) => {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`device-tabpanel-${index}`}
      aria-labelledby={`device-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
};

const DeviceDataSync: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);
  const [syncingDevices, setSyncingDevices] = useState<string[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info';
  }>({
    open: false,
    message: '',
    severity: 'info',
  });

  // 模拟数据 - 实际项目中应通过API获取
  const [devices, setDevices] = useState<Device[]>([
    {
      id: '1',
      name: '心率监测手表',
      type: 'watch',
      status: 'connected',
      lastSync: '2023-10-15T08:30:00Z',
      batteryLevel: 78,
      manufacturer: 'HealthTrack',
    },
    {
      id: '2',
      name: '血压计',
      type: 'blood_pressure',
      status: 'disconnected',
      lastSync: '2023-10-10T15:45:00Z',
      batteryLevel: 35,
      manufacturer: 'OmronHealth',
    },
    {
      id: '3',
      name: '血糖仪',
      type: 'glucose',
      status: 'connected',
      lastSync: '2023-10-14T19:20:00Z',
      batteryLevel: 92,
      manufacturer: 'GlucoSense',
    },
  ]);

  const [syncHistory, setSyncHistory] = useState<SyncHistory[]>([
    {
      id: '1',
      deviceId: '1',
      deviceName: '心率监测手表',
      timestamp: '2023-10-15T08:30:00Z',
      status: 'success',
      recordsCount: 128,
    },
    {
      id: '2',
      deviceId: '2',
      deviceName: '血压计',
      timestamp: '2023-10-10T15:45:00Z',
      status: 'failed',
      recordsCount: 0,
      message: '连接超时，请检查设备是否开启',
    },
    {
      id: '3',
      deviceId: '3',
      deviceName: '血糖仪',
      timestamp: '2023-10-14T19:20:00Z',
      status: 'partial',
      recordsCount: 45,
      message: '部分数据同步成功，3条记录格式错误',
    },
    {
      id: '4',
      deviceId: '1',
      deviceName: '心率监测手表',
      timestamp: '2023-10-14T07:15:00Z',
      status: 'success',
      recordsCount: 96,
    },
  ]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleSyncDevice = (deviceId: string) => {
    // 模拟同步过程
    setSyncingDevices([...syncingDevices, deviceId]);
    
    // 更新设备状态
    setDevices(prevDevices =>
      prevDevices.map(device =>
        device.id === deviceId ? { ...device, status: 'syncing' } : device
      )
    );

    // 模拟异步同步操作
    setTimeout(() => {
      // 随机确定同步结果
      const success = Math.random() > 0.2;
      
      if (success) {
        // 同步成功
        const now = new Date().toISOString();
        const recordsCount = Math.floor(Math.random() * 100) + 20;
        
        // 添加新的同步历史记录
        const newSyncRecord: SyncHistory = {
          id: Date.now().toString(),
          deviceId,
          deviceName: devices.find(d => d.id === deviceId)?.name || '',
          timestamp: now,
          status: 'success',
          recordsCount,
        };
        
        setSyncHistory([newSyncRecord, ...syncHistory]);
        
        // 更新设备状态
        setDevices(prevDevices =>
          prevDevices.map(device =>
            device.id === deviceId
              ? { ...device, status: 'connected', lastSync: now }
              : device
          )
        );
        
        setSnackbar({
          open: true,
          message: `已成功同步 ${recordsCount} 条记录`,
          severity: 'success',
        });
      } else {
        // 同步失败
        const now = new Date().toISOString();
        
        // 添加新的同步历史记录
        const newSyncRecord: SyncHistory = {
          id: Date.now().toString(),
          deviceId,
          deviceName: devices.find(d => d.id === deviceId)?.name || '',
          timestamp: now,
          status: 'failed',
          recordsCount: 0,
          message: '设备连接失败，请确保设备已开启并在范围内',
        };
        
        setSyncHistory([newSyncRecord, ...syncHistory]);
        
        // 更新设备状态
        setDevices(prevDevices =>
          prevDevices.map(device =>
            device.id === deviceId
              ? { ...device, status: 'disconnected' }
              : device
          )
        );
        
        setSnackbar({
          open: true,
          message: '数据同步失败，请重试',
          severity: 'error',
        });
      }
      
      // 移除同步中状态
      setSyncingDevices(syncingDevices.filter(id => id !== deviceId));
    }, 2500);
  };

  const handleRefreshDevices = () => {
    // 模拟刷新设备列表
    setSnackbar({
      open: true,
      message: '正在扫描附近设备...',
      severity: 'info',
    });
    
    setTimeout(() => {
      // 模拟找到新设备
      const foundNewDevice = Math.random() > 0.5;
      
      if (foundNewDevice) {
        const newDevice: Device = {
          id: `new-${Date.now()}`,
          name: '新体温计',
          type: 'thermometer',
          status: 'disconnected',
          lastSync: null,
          manufacturer: 'ThermoHealth',
        };
        
        setDevices([...devices, newDevice]);
        
        setSnackbar({
          open: true,
          message: '发现新设备: 新体温计',
          severity: 'success',
        });
      } else {
        setSnackbar({
          open: true,
          message: '扫描完成，未发现新设备',
          severity: 'info',
        });
      }
    }, 2000);
  };

  const getDeviceIcon = (type: string) => {
    switch (type) {
      case 'watch':
        return <WatchIcon />;
      case 'blood_pressure':
      case 'glucose':
        return <BloodIcon />;
      default:
        return <OtherDeviceIcon />;
    }
  };

  const getStatusColor = (status: Device['status']) => {
    switch (status) {
      case 'connected':
        return 'success';
      case 'disconnected':
        return 'error';
      case 'syncing':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getStatusLabel = (status: Device['status']) => {
    switch (status) {
      case 'connected':
        return '已连接';
      case 'disconnected':
        return '未连接';
      case 'syncing':
        return '同步中';
      default:
        return '未知';
    }
  };

  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };

  return (
    <Box sx={{ width: '100%' }}>
      <Paper sx={{ mb: 3 }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          indicatorColor="primary"
          textColor="primary"
          centered
        >
          <Tab label="我的设备" id="device-tab-0" />
          <Tab label="同步历史" id="device-tab-1" />
          <Tab label="数据分析" id="device-tab-2" />
        </Tabs>
      </Paper>

      <TabPanel value={tabValue} index={0}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6" component="h2">
            设备列表
          </Typography>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={handleRefreshDevices}
          >
            刷新设备
          </Button>
        </Box>

        <Grid container spacing={3}>
          {devices.map((device) => (
            <Grid item xs={12} sm={6} md={4} key={device.id}>
              <Card 
                variant="outlined"
                sx={{ 
                  height: '100%',
                  position: 'relative',
                  borderColor: device.status === 'connected' ? 'success.light' : 'inherit'
                }}
              >
                <CardHeader
                  title={device.name}
                  subheader={device.manufacturer}
                  avatar={
                    <Box sx={{ 
                      backgroundColor: 'background.default', 
                      borderRadius: '50%', 
                      p: 1, 
                      display: 'flex' 
                    }}>
                      {getDeviceIcon(device.type)}
                    </Box>
                  }
                  action={
                    <Chip 
                      label={getStatusLabel(device.status)}
                      color={getStatusColor(device.status) as any}
                      size="small"
                      sx={{ mr: 1 }}
                    />
                  }
                />
                <Divider />
                <CardContent>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    上次同步: {device.lastSync ? formatDate(device.lastSync) : '从未同步'}
                  </Typography>
                  
                  {device.batteryLevel !== undefined && (
                    <Box display="flex" alignItems="center" mt={1} mb={2}>
                      <Typography variant="body2" color="text.secondary" mr={1}>
                        电量:
                      </Typography>
                      <Box sx={{ position: 'relative', display: 'inline-flex', width: '100%' }}>
                        <CircularProgress
                          variant="determinate"
                          value={device.batteryLevel}
                          size={28}
                          thickness={6}
                          sx={{
                            color: 
                              device.batteryLevel > 60 ? 'success.main' :
                              device.batteryLevel > 20 ? 'warning.main' :
                              'error.main',
                          }}
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
                            {device.batteryLevel}%
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  )}
                  
                  <Button
                    variant="contained"
                    fullWidth
                    startIcon={syncingDevices.includes(device.id) ? <CircularProgress size={16} color="inherit" /> : <SyncIcon />}
                    onClick={() => handleSyncDevice(device.id)}
                    disabled={syncingDevices.includes(device.id) || device.status === 'syncing'}
                    color={device.status === 'connected' ? 'primary' : 'secondary'}
                  >
                    {syncingDevices.includes(device.id) ? '同步中...' : '同步数据'}
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          ))}
          
          <Grid item xs={12} sm={6} md={4}>
            <Card
              variant="outlined"
              sx={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                p: 3,
                borderStyle: 'dashed',
                cursor: 'pointer',
              }}
              onClick={handleRefreshDevices}
            >
              <AddIcon sx={{ fontSize: 40, color: 'primary.main', mb: 2 }} />
              <Typography variant="h6" color="primary">添加新设备</Typography>
              <Typography variant="body2" color="text.secondary" align="center" mt={1}>
                点击扫描附近可用的设备进行配对
              </Typography>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        <Typography variant="h6" component="h2" gutterBottom>
          同步历史记录
        </Typography>
        
        <List>
          {syncHistory.map((record) => (
            <Paper
              key={record.id}
              variant="outlined"
              sx={{ mb: 2, overflow: 'hidden' }}
            >
              <ListItem
                secondaryAction={
                  <Chip
                    label={
                      record.status === 'success' ? '成功' : 
                      record.status === 'failed' ? '失败' : '部分成功'
                    }
                    color={
                      record.status === 'success' ? 'success' : 
                      record.status === 'failed' ? 'error' : 'warning'
                    }
                    icon={
                      record.status === 'success' ? <CheckIcon /> : 
                      record.status === 'failed' ? <WarningIcon /> : <WarningIcon />
                    }
                  />
                }
              >
                <ListItemAvatar>
                  {getDeviceIcon(devices.find(d => d.id === record.deviceId)?.type || '')}
                </ListItemAvatar>
                <ListItemText
                  primary={record.deviceName}
                  secondary={
                    <>
                      <Typography component="span" variant="body2" color="text.primary">
                        {formatDate(record.timestamp)}
                      </Typography>
                      {record.status !== 'failed' && (
                        <Typography component="span" variant="body2" sx={{ ml: 1 }}>
                          • 同步 {record.recordsCount} 条记录
                        </Typography>
                      )}
                    </>
                  }
                />
              </ListItem>
              {record.message && (
                <Box sx={{ px: 2, pb: 2, pt: 0 }}>
                  <Alert severity={record.status === 'failed' ? 'error' : 'warning'}>
                    {record.message}
                  </Alert>
                </Box>
              )}
            </Paper>
          ))}
        </List>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <Typography variant="h6" color="text.secondary" gutterBottom>
            数据分析功能正在开发中
          </Typography>
          <Typography variant="body2" color="text.secondary">
            即将推出设备数据趋势分析、健康评估和智能建议功能。
          </Typography>
        </Box>
      </TabPanel>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleCloseSnackbar} severity={snackbar.severity} sx={{ width: '100%' }}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default DeviceDataSync; 