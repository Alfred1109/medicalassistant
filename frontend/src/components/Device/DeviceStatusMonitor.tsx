import React from 'react';
import { 
  Box, 
  Card, 
  CardContent, 
  Chip, 
  Divider, 
  Grid, 
  IconButton, 
  Paper, 
  Tooltip, 
  Typography 
} from '@mui/material';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Battery20Icon from '@mui/icons-material/Battery20';
import Battery50Icon from '@mui/icons-material/Battery50';
import Battery80Icon from '@mui/icons-material/Battery80';
import BatteryFullIcon from '@mui/icons-material/BatteryFull';
import BatteryChargingFullIcon from '@mui/icons-material/BatteryChargingFull';
import SignalCellular0BarIcon from '@mui/icons-material/SignalCellular0Bar';
import SignalCellular1BarIcon from '@mui/icons-material/SignalCellular1Bar';
import SignalCellular2BarIcon from '@mui/icons-material/SignalCellular2Bar';
import SignalCellular3BarIcon from '@mui/icons-material/SignalCellular3Bar';
import SignalCellular4BarIcon from '@mui/icons-material/SignalCellular4Bar';
import RefreshIcon from '@mui/icons-material/Refresh';
import SyncIcon from '@mui/icons-material/Sync';
import InfoIcon from '@mui/icons-material/Info';
import WarningIcon from '@mui/icons-material/Warning';
import ErrorIcon from '@mui/icons-material/Error';

// 设备类型定义
interface Device {
  id: string;
  name: string;
  patientId: string;
  patientName: string;
  type: '血压计' | '血糖仪' | '体温计' | '心电图' | '体重秤' | '手环' | '其他';
  status: 'online' | 'offline' | 'error' | 'syncing';
  batteryLevel: number;
  signalStrength: number; // 1-5
  lastSyncTime: string;
  nextSyncTime?: string;
  firmwareVersion: string;
  firmwareUpdateAvailable: boolean;
  errorMessage?: string;
  connectionType: 'bluetooth' | 'wifi' | 'cable';
}

// 组件属性
interface DeviceStatusMonitorProps {
  onRefresh?: () => void;
  onDeviceSync?: (deviceId: string) => void;
  onDeviceDetails?: (deviceId: string) => void;
}

// 示例数据
const mockDevices: Device[] = [
  {
    id: 'bp-12345',
    name: '血压监测仪 A',
    patientId: 'P10001',
    patientName: '张三',
    type: '血压计',
    status: 'online',
    batteryLevel: 86,
    signalStrength: 4,
    lastSyncTime: '2024-05-20 08:15:32',
    nextSyncTime: '2024-05-20 20:15:32',
    firmwareVersion: '1.2.3',
    firmwareUpdateAvailable: false,
    connectionType: 'bluetooth'
  },
  {
    id: 'wt-67890',
    name: '体重秤 B',
    patientId: 'P10002',
    patientName: '李四',
    type: '体重秤',
    status: 'offline',
    batteryLevel: 23,
    signalStrength: 1,
    lastSyncTime: '2024-05-19 19:30:45',
    firmwareVersion: '2.0.1',
    firmwareUpdateAvailable: true,
    connectionType: 'wifi'
  },
  {
    id: 'ecg-24680',
    name: '心电监测仪 C',
    patientId: 'P10003',
    patientName: '王五',
    type: '心电图',
    status: 'syncing',
    batteryLevel: 62,
    signalStrength: 3,
    lastSyncTime: '2024-05-20 10:05:18',
    nextSyncTime: '2024-05-20 22:05:18',
    firmwareVersion: '3.1.5',
    firmwareUpdateAvailable: false,
    connectionType: 'bluetooth'
  },
  {
    id: 'bg-13579',
    name: '血糖仪 D',
    patientId: 'P10004',
    patientName: '赵六',
    type: '血糖仪',
    status: 'error',
    batteryLevel: 45,
    signalStrength: 2,
    lastSyncTime: '2024-05-18 15:45:10',
    firmwareVersion: '1.8.2',
    firmwareUpdateAvailable: false,
    errorMessage: '设备校准失败，请重新校准',
    connectionType: 'bluetooth'
  },
  {
    id: 'wb-97531',
    name: '智能手环 E',
    patientId: 'P10005',
    patientName: '孙七',
    type: '手环',
    status: 'online',
    batteryLevel: 91,
    signalStrength: 5,
    lastSyncTime: '2024-05-20 09:20:56',
    nextSyncTime: '2024-05-20 21:20:56',
    firmwareVersion: '4.2.0',
    firmwareUpdateAvailable: true,
    connectionType: 'bluetooth'
  }
];

// 设备状态监控组件
const DeviceStatusMonitor: React.FC<DeviceStatusMonitorProps> = ({ 
  onRefresh, 
  onDeviceSync, 
  onDeviceDetails 
}) => {
  // 获取电池图标
  const getBatteryIcon = (level: number) => {
    if (level >= 80) return <BatteryFullIcon color="success" />;
    if (level >= 50) return <Battery80Icon color="success" />;
    if (level >= 20) return <Battery50Icon color="warning" />;
    return <Battery20Icon color="error" />;
  };

  // 获取信号强度图标
  const getSignalIcon = (strength: number) => {
    switch (strength) {
      case 5: return <SignalCellular4BarIcon color="success" />;
      case 4: return <SignalCellular3BarIcon color="success" />;
      case 3: return <SignalCellular2BarIcon color="warning" />;
      case 2: return <SignalCellular1BarIcon color="warning" />;
      case 1: return <SignalCellular0BarIcon color="error" />;
      default: return <SignalCellular0BarIcon color="error" />;
    }
  };

  // 获取设备状态图标和颜色
  const getStatusChip = (status: Device['status']) => {
    switch (status) {
      case 'online':
        return <Chip size="small" color="success" label="在线" />;
      case 'offline':
        return <Chip size="small" color="default" label="离线" />;
      case 'error':
        return <Chip size="small" color="error" label="错误" />;
      case 'syncing':
        return <Chip size="small" color="info" label="同步中" icon={<SyncIcon />} />;
    }
  };

  // 处理刷新
  const handleRefresh = () => {
    if (onRefresh) {
      onRefresh();
    } else {
      console.log('刷新设备状态');
      // 这里可以添加模拟刷新的代码
    }
  };

  // 处理设备同步
  const handleDeviceSync = (deviceId: string) => {
    if (onDeviceSync) {
      onDeviceSync(deviceId);
    } else {
      console.log(`同步设备: ${deviceId}`);
      // 这里可以添加模拟同步的代码
    }
  };

  // 处理查看设备详情
  const handleDeviceDetails = (deviceId: string) => {
    if (onDeviceDetails) {
      onDeviceDetails(deviceId);
    } else {
      console.log(`查看设备详情: ${deviceId}`);
      // 这里可以添加模拟查看详情的代码
    }
  };

  // 获取设备统计信息
  const getDeviceStats = () => {
    const total = mockDevices.length;
    const online = mockDevices.filter(d => d.status === 'online').length;
    const offline = mockDevices.filter(d => d.status === 'offline').length;
    const error = mockDevices.filter(d => d.status === 'error').length;
    const syncing = mockDevices.filter(d => d.status === 'syncing').length;
    const lowBattery = mockDevices.filter(d => d.batteryLevel < 20).length;
    const updateAvailable = mockDevices.filter(d => d.firmwareUpdateAvailable).length;

    return { total, online, offline, error, syncing, lowBattery, updateAvailable };
  };

  const stats = getDeviceStats();

  return (
    <Card>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h5" component="h2">
            设备状态监控
          </Typography>
          <Tooltip title="刷新设备状态">
            <IconButton onClick={handleRefresh}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>

        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={6} md={3}>
            <Paper elevation={1} sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="h6" color="primary">
                {stats.total}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                总设备数
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} md={3}>
            <Paper elevation={1} sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="h6" color="success.main">
                {stats.online}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                在线设备
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} md={3}>
            <Paper elevation={1} sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="h6" color="text.secondary">
                {stats.offline}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                离线设备
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} md={3}>
            <Paper elevation={1} sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="h6" color="error.main">
                {stats.error}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                错误设备
              </Typography>
            </Paper>
          </Grid>
        </Grid>

        <Divider sx={{ mb: 3 }} />

        <Typography variant="h6" gutterBottom>
          设备状态详情
        </Typography>

        <TableContainer component={Paper} elevation={1}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>设备名称</TableCell>
                <TableCell>患者</TableCell>
                <TableCell>类型</TableCell>
                <TableCell>状态</TableCell>
                <TableCell>电量</TableCell>
                <TableCell>信号</TableCell>
                <TableCell>上次同步</TableCell>
                <TableCell>操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {mockDevices.map((device) => (
                <TableRow key={device.id} hover>
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      <Typography variant="body2">
                        {device.name}
                      </Typography>
                      {device.firmwareUpdateAvailable && (
                        <Tooltip title="有可用固件更新">
                          <InfoIcon color="primary" fontSize="small" sx={{ ml: 1 }} />
                        </Tooltip>
                      )}
                    </Box>
                  </TableCell>
                  <TableCell>{device.patientName} ({device.patientId})</TableCell>
                  <TableCell>{device.type}</TableCell>
                  <TableCell>{getStatusChip(device.status)}</TableCell>
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      {getBatteryIcon(device.batteryLevel)}
                      <Typography variant="body2" sx={{ ml: 1 }}>
                        {device.batteryLevel}%
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      {getSignalIcon(device.signalStrength)}
                    </Box>
                  </TableCell>
                  <TableCell>{device.lastSyncTime}</TableCell>
                  <TableCell>
                    <Box>
                      <Tooltip title="同步设备">
                        <IconButton 
                          size="small" 
                          onClick={() => handleDeviceSync(device.id)}
                          disabled={device.status === 'syncing' || device.status === 'offline'}
                        >
                          <SyncIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="查看详情">
                        <IconButton 
                          size="small" 
                          onClick={() => handleDeviceDetails(device.id)}
                        >
                          <InfoIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      {device.status === 'error' && (
                        <Tooltip title={device.errorMessage || '设备错误'}>
                          <IconButton size="small" color="error">
                            <ErrorIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        <Box mt={2} display="flex" justifyContent="space-between" alignItems="center">
          <Box display="flex" alignItems="center">
            <Box display="flex" alignItems="center" mr={2}>
              <Battery20Icon color="error" fontSize="small" sx={{ mr: 0.5 }} />
              <Typography variant="body2" color="textSecondary">
                低电量: {stats.lowBattery}
              </Typography>
            </Box>
            <Box display="flex" alignItems="center" mr={2}>
              <InfoIcon color="primary" fontSize="small" sx={{ mr: 0.5 }} />
              <Typography variant="body2" color="textSecondary">
                可更新: {stats.updateAvailable}
              </Typography>
            </Box>
            <Box display="flex" alignItems="center">
              <SyncIcon color="info" fontSize="small" sx={{ mr: 0.5 }} />
              <Typography variant="body2" color="textSecondary">
                同步中: {stats.syncing}
              </Typography>
            </Box>
          </Box>
          <Typography variant="body2" color="textSecondary">
            上次更新: {new Date().toLocaleString()}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

export default DeviceStatusMonitor; 