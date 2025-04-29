import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Button,
  TextField,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  LinearProgress,
  IconButton,
  Snackbar,
} from '@mui/material';
import CardMedia from '@mui/material/CardMedia';
import AddIcon from '@mui/icons-material/Add';
import DevicesIcon from '@mui/icons-material/Devices';
import WatchIcon from '@mui/icons-material/Watch';
import SmartphoneIcon from '@mui/icons-material/Smartphone';
import BluetoothIcon from '@mui/icons-material/Bluetooth';
import BluetoothSearchingIcon from '@mui/icons-material/BluetoothSearching';
import SettingsRemoteIcon from '@mui/icons-material/SettingsRemote';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import SyncIcon from '@mui/icons-material/Sync';
import MemoryIcon from '@mui/icons-material/Memory';
import BatteryFullIcon from '@mui/icons-material/BatteryFull';
import BatteryChargingFullIcon from '@mui/icons-material/BatteryChargingFull';
import CloseIcon from '@mui/icons-material/Close';
import InfoIcon from '@mui/icons-material/Info';
import DeleteIcon from '@mui/icons-material/Delete';
import CircularProgress from '@mui/material/CircularProgress';
import { Link } from 'react-router-dom';

// 设备类型定义
interface Device {
  id: string;
  name: string;
  type: 'wristband' | 'monitor' | 'phone' | string;
  status: 'connected' | 'disconnected' | 'available';
  lastActive?: string;
  batteryLevel?: number;
  model?: string;
  serialNumber?: string;
  firmwareVersion?: string;
  lastSync?: string;
}

// 向导状态接口
interface WizardState {
  open: boolean;
  activeStep: number;
  deviceType: string;
  deviceName: string;
  deviceCode: string;
}

// 选项卡面板属性接口
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 选项卡面板组件
function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`device-tabpanel-${index}`}
      aria-labelledby={`device-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 2 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const DeviceBinding: React.FC = () => {
  const [scanning, setScanning] = React.useState(false);
  const [pairedDevices, setPairedDevices] = React.useState<Device[]>([
    {
      id: '1',
      name: '康复手环 A1',
      type: 'wristband',
      status: 'connected',
      lastActive: '2023-06-01 14:30',
      batteryLevel: 72,
      model: 'RehabBand 2000',
      serialNumber: 'RB2000-A1-12345',
      firmwareVersion: 'v1.2.3',
      lastSync: '2023-06-01 14:30'
    }
  ]);
  
  const [availableDevices, setAvailableDevices] = React.useState<Device[]>([]);
  
  // 新增状态
  const [selectedDevice, setSelectedDevice] = React.useState<Device | null>(null);
  const [openDeviceDialog, setOpenDeviceDialog] = React.useState(false);
  const [dialogTabValue, setDialogTabValue] = React.useState(0);
  const [syncing, setSyncing] = React.useState(false);
  const [snackbar, setSnackbar] = React.useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });
  
  // 设备向导状态
  const [wizardState, setWizardState] = React.useState<WizardState>({
    open: false,
    activeStep: 0,
    deviceType: '',
    deviceName: '',
    deviceCode: ''
  });
  
  const startScan = () => {
    setScanning(true);
    
    // 模拟搜索过程
    setTimeout(() => {
      setAvailableDevices([
        {
          id: '2',
          name: '康复监测器 B2',
          type: 'monitor',
          status: 'available'
        },
        {
          id: '3',
          name: '智能手环 C3',
          type: 'wristband',
          status: 'available'
        }
      ]);
      setScanning(false);
    }, 3000);
  };
  
  const pairDevice = (device: Device) => {
    const enhancedDevice: Device = {
      ...device, 
      status: 'connected' as const,
      lastActive: new Date().toLocaleString(),
      batteryLevel: 100,
      model: device.type === 'wristband' ? 'HealthBand Pro' : 'RehabMonitor 3000',
      serialNumber: `${device.type === 'wristband' ? 'HB' : 'RM'}-${Math.floor(Math.random() * 10000)}`,
      firmwareVersion: 'v1.0.0',
      lastSync: new Date().toLocaleString()
    };
    setPairedDevices([...pairedDevices, enhancedDevice]);
    setAvailableDevices(availableDevices.filter(d => d.id !== device.id));
    
    // 显示成功消息
    setSnackbar({
      open: true,
      message: `设备 ${device.name} 配对成功！`,
      severity: 'success'
    });
  };
  
  const handleOpenDeviceDetail = (device: Device) => {
    setSelectedDevice(device);
    setOpenDeviceDialog(true);
  };
  
  const handleCloseDeviceDetail = () => {
    setOpenDeviceDialog(false);
  };
  
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setDialogTabValue(newValue);
  };
  
  const handleSyncDevice = () => {
    if (!selectedDevice) return;
    
    setSyncing(true);
    
    // 模拟同步过程
    setTimeout(() => {
      setPairedDevices(pairedDevices.map(device => 
        device.id === selectedDevice.id 
          ? {...device, lastSync: new Date().toLocaleString()} 
          : device
      ));
      setSyncing(false);
      
      // 显示成功消息
      setSnackbar({
        open: true,
        message: `设备 ${selectedDevice.name} 数据同步成功！`,
        severity: 'success'
      });
    }, 2000);
  };
  
  const handleDeleteDevice = (deviceId: string) => {
    setPairedDevices(pairedDevices.filter(device => device.id !== deviceId));
    setOpenDeviceDialog(false);
    
    // 显示成功消息
    setSnackbar({
      open: true,
      message: `设备已成功移除`,
      severity: 'info'
    });
  };
  
  const handleCloseSnackbar = () => {
    setSnackbar({...snackbar, open: false});
  };
  
  const getDeviceIcon = (type: string) => {
    switch (type) {
      case 'wristband':
        return <WatchIcon />;
      case 'monitor':
        return <SettingsRemoteIcon />;
      case 'phone':
        return <SmartphoneIcon />;
      default:
        return <DevicesIcon />;
    }
  };
  
  const getBatteryColor = (level: number | undefined) => {
    if (!level) return 'grey.500';
    if (level > 60) return 'success.main';
    if (level > 20) return 'warning.main';
    return 'error.main';
  };
  
  // 打开向导
  const handleOpenWizard = () => {
    setWizardState({...wizardState, open: true, activeStep: 0});
  };
  
  // 关闭向导
  const handleCloseWizard = () => {
    setWizardState({...wizardState, open: false});
  };
  
  // 向导下一步
  const handleWizardNext = () => {
    setWizardState({...wizardState, activeStep: wizardState.activeStep + 1});
  };
  
  // 向导上一步
  const handleWizardBack = () => {
    setWizardState({...wizardState, activeStep: wizardState.activeStep - 1});
  };
  
  // 向导完成
  const handleWizardComplete = () => {
    // 创建新设备
    const newDevice: Device = {
      id: `custom-${Date.now()}`,
      name: wizardState.deviceName || `${wizardState.deviceType}设备`,
      type: wizardState.deviceType as any,
      status: 'connected',
      lastActive: new Date().toLocaleString(),
      batteryLevel: 100,
      model: wizardState.deviceType === 'wristband' ? 'HealthBand Pro' : 'RehabMonitor 3000',
      serialNumber: wizardState.deviceCode,
      firmwareVersion: 'v1.0.0',
      lastSync: new Date().toLocaleString()
    };
    
    setPairedDevices([...pairedDevices, newDevice]);
    handleCloseWizard();
    
    // 显示成功消息
    setSnackbar({
      open: true,
      message: `设备 ${newDevice.name} 配对成功！`,
      severity: 'success'
    });
  };
  
  // 更新向导字段
  const handleWizardFieldChange = (field: keyof WizardState, value: string) => {
    setWizardState({...wizardState, [field]: value});
  };
  
  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        设备绑定与管理
      </Typography>
      
      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">已绑定设备</Typography>
              <Box>
                <Button 
                  variant="outlined" 
                  color="primary" 
                  onClick={handleOpenWizard}
                  sx={{ mr: 1 }}
                >
                  手动配置
                </Button>
                <Button 
                  variant="contained" 
                  color="primary" 
                  startIcon={<AddIcon />}
                  onClick={startScan}
                  disabled={scanning}
                >
                  添加设备
                </Button>
              </Box>
            </Box>
            
            {pairedDevices.length > 0 ? (
              <List>
                {pairedDevices.map((device) => (
                  <React.Fragment key={device.id}>
                    <ListItem>
                      <ListItemIcon>
                        {getDeviceIcon(device.type)}
                      </ListItemIcon>
                      <ListItemText 
                        primary={
                          <Box display="flex" alignItems="center">
                            {device.name}
                            <CheckCircleIcon sx={{ ml: 1, color: 'success.main', fontSize: 16 }} />
                          </Box>
                        }
                        secondary={`最后活动: ${device.lastActive} | 电量: ${device.batteryLevel}%`}
                      />
                      <Button 
                        variant="outlined" 
                        size="small"
                        onClick={() => handleOpenDeviceDetail(device)}
                      >
                        管理
                      </Button>
                    </ListItem>
                    <Divider />
                  </React.Fragment>
                ))}
              </List>
            ) : (
              <Alert severity="info">没有已绑定的设备</Alert>
            )}
            
            {scanning && (
              <Box textAlign="center" my={3}>
                <BluetoothSearchingIcon sx={{ fontSize: 40, color: 'primary.main', animation: 'pulse 1.5s infinite' }} />
                <Typography>正在搜索附近设备...</Typography>
              </Box>
            )}
            
            {!scanning && availableDevices.length > 0 && (
              <Box mt={3}>
                <Typography variant="subtitle1" gutterBottom>
                  可用设备
                </Typography>
                <List>
                  {availableDevices.map((device) => (
                    <React.Fragment key={device.id}>
                      <ListItem>
                        <ListItemIcon>
                          {getDeviceIcon(device.type)}
                        </ListItemIcon>
                        <ListItemText 
                          primary={device.name}
                        />
                        <Button 
                          variant="outlined" 
                          size="small"
                          onClick={() => pairDevice(device)}
                        >
                          配对
                        </Button>
                      </ListItem>
                      <Divider />
                    </React.Fragment>
                  ))}
                </List>
              </Box>
            )}
          </Paper>
        </Grid>
        
        <Grid item xs={12} md={5}>
          <Card>
            <CardMedia
              component="img"
              height="200"
              image="https://via.placeholder.com/400x200?text=康复设备示意图"
              alt="康复设备示意图"
            />
            <CardContent>
              <Typography gutterBottom variant="h6" component="div">
                康复监测设备说明
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                我们提供多种智能康复监测设备，帮助您更好地完成康复训练并追踪训练效果。
              </Typography>
              <Typography variant="body2" color="text.secondary">
                设备类型:
              </Typography>
              <List dense>
                <ListItem>
                  <ListItemIcon>
                    <WatchIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText 
                    primary="康复手环"
                    secondary="记录日常活动和训练数据"
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon>
                    <SettingsRemoteIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText 
                    primary="康复监测器"
                    secondary="提供专业的康复训练监测与指导"
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon>
                    <SmartphoneIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText 
                    primary="手机应用"
                    secondary="与其他设备配合使用，随时查看康复数据"
                  />
                </ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      
      {/* 设备详情对话框 */}
      <Dialog
        open={openDeviceDialog}
        onClose={handleCloseDeviceDetail}
        maxWidth="md"
        fullWidth
      >
        {selectedDevice && (
          <>
            <DialogTitle>
              <Box display="flex" justifyContent="space-between" alignItems="center">
                <Box display="flex" alignItems="center">
                  {getDeviceIcon(selectedDevice.type)}
                  <Typography variant="h6" sx={{ ml: 1 }}>
                    {selectedDevice.name}
                  </Typography>
                </Box>
                <IconButton onClick={handleCloseDeviceDetail}>
                  <CloseIcon />
                </IconButton>
              </Box>
            </DialogTitle>
            <DialogContent dividers>
              <Tabs
                value={dialogTabValue}
                onChange={handleTabChange}
                variant="fullWidth"
              >
                <Tab label="设备信息" icon={<InfoIcon />} iconPosition="start" />
                <Tab label="数据同步" icon={<SyncIcon />} iconPosition="start" />
              </Tabs>
              
              <TabPanel value={dialogTabValue} index={0}>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" gutterBottom>
                          基本信息
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        
                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">
                            设备型号
                          </Typography>
                          <Typography variant="body1">
                            {selectedDevice.model || '未知'}
                          </Typography>
                        </Box>
                        
                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">
                            序列号
                          </Typography>
                          <Typography variant="body1">
                            {selectedDevice.serialNumber || '未知'}
                          </Typography>
                        </Box>
                        
                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">
                            固件版本
                          </Typography>
                          <Typography variant="body1">
                            {selectedDevice.firmwareVersion || '未知'}
                          </Typography>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                  
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" gutterBottom>
                          状态信息
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        
                        <Box sx={{ mb: 1, display: 'flex', alignItems: 'center' }}>
                          <BatteryFullIcon sx={{ mr: 1, color: getBatteryColor(selectedDevice.batteryLevel) }} />
                          <Box sx={{ flex: 1 }}>
                            <Typography variant="body2" color="text.secondary">
                              电池电量
                            </Typography>
                            <LinearProgress
                              variant="determinate"
                              value={selectedDevice.batteryLevel || 0}
                              sx={{ 
                                height: 8, 
                                borderRadius: 4,
                                mb: 1,
                                '& .MuiLinearProgress-bar': {
                                  backgroundColor: getBatteryColor(selectedDevice.batteryLevel)
                                }
                              }}
                            />
                            <Typography variant="body2">
                              {selectedDevice.batteryLevel || 0}%
                            </Typography>
                          </Box>
                        </Box>
                        
                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">
                            连接状态
                          </Typography>
                          <Box display="flex" alignItems="center">
                            <CheckCircleIcon sx={{ mr: 1, fontSize: 16, color: 'success.main' }} />
                            <Typography variant="body1">
                              已连接
                            </Typography>
                          </Box>
                        </Box>
                        
                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">
                            最后活动时间
                          </Typography>
                          <Typography variant="body1">
                            {selectedDevice.lastActive || '未知'}
                          </Typography>
                        </Box>
                        
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            最后同步时间
                          </Typography>
                          <Typography variant="body1">
                            {selectedDevice.lastSync || '未同步'}
                          </Typography>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </TabPanel>
              
              <TabPanel value={dialogTabValue} index={1}>
                <Box textAlign="center" my={2}>
                  <Typography variant="h6" gutterBottom>
                    设备数据同步
                  </Typography>
                  <Typography variant="body2" color="text.secondary" paragraph>
                    将设备收集的健康数据和训练记录同步到系统中，以便医生和康复师查看您的康复情况。
                  </Typography>
                  
                  {syncing ? (
                    <Box sx={{ width: '100%', mt: 3 }}>
                      <LinearProgress />
                      <Typography variant="body2" sx={{ mt: 2 }}>
                        正在同步数据，请不要断开设备连接...
                      </Typography>
                    </Box>
                  ) : (
                    <Button
                      variant="contained"
                      color="primary"
                      startIcon={<SyncIcon />}
                      onClick={handleSyncDevice}
                      sx={{ mt: 2 }}
                    >
                      开始同步
                    </Button>
                  )}
                  
                  <Box sx={{ mt: 4 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      上次同步: {selectedDevice.lastSync || '从未同步'}
                    </Typography>
                  </Box>
                  
                  {/* 历史数据预览 */}
                  <Box sx={{ mt: 5, textAlign: 'left' }}>
                    <Typography variant="h6" gutterBottom>
                      最近数据预览
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    <Grid container spacing={3}>
                      <Grid item xs={12} md={6}>
                        <Typography variant="subtitle2" gutterBottom>
                          今日步数
                        </Typography>
                        <Box sx={{ display: 'flex', alignItems: 'baseline' }}>
                          <Typography variant="h4" color="primary.main">
                            8,742
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                            步
                          </Typography>
                        </Box>
                        <Typography variant="body2" color="text.secondary">
                          目标: 10,000步 | 达成率: 87%
                        </Typography>
                        <LinearProgress
                          variant="determinate"
                          value={87}
                          sx={{ height: 6, borderRadius: 3, mt: 1 }}
                        />
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <Typography variant="subtitle2" gutterBottom>
                          今日消耗
                        </Typography>
                        <Box sx={{ display: 'flex', alignItems: 'baseline' }}>
                          <Typography variant="h4" color="primary.main">
                            324
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                            千卡
                          </Typography>
                        </Box>
                        <Typography variant="body2" color="text.secondary">
                          基础代谢: 1,650千卡 | 活动消耗: 324千卡
                        </Typography>
                        <LinearProgress
                          variant="determinate"
                          value={45}
                          sx={{ height: 6, borderRadius: 3, mt: 1 }}
                        />
                      </Grid>
                      
                      <Grid item xs={12}>
                        <Divider sx={{ my: 1 }} />
                      </Grid>
                      
                      <Grid item xs={12} md={4}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle2" color="text.secondary">
                              最近心率
                            </Typography>
                            <Box sx={{ display: 'flex', alignItems: 'baseline', mt: 1 }}>
                              <Typography variant="h4">
                                78
                              </Typography>
                              <Typography variant="body2" sx={{ ml: 1 }}>
                                BPM
                              </Typography>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                              记录于 今天 14:30
                            </Typography>
                            <Box 
                              sx={{ 
                                height: 60, 
                                mt: 1, 
                                display: 'flex', 
                                alignItems: 'flex-end',
                                justifyContent: 'space-between' 
                              }}
                            >
                              {[75, 72, 71, 74, 78, 76, 78].map((value, index) => (
                                <Box 
                                  key={index}
                                  sx={{
                                    height: `${value / 100 * 60}px`,
                                    width: '8px',
                                    backgroundColor: 'primary.main',
                                    borderRadius: 1
                                  }}
                                />
                              ))}
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                      
                      <Grid item xs={12} md={4}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle2" color="text.secondary">
                              今日训练
                            </Typography>
                            <Box sx={{ display: 'flex', alignItems: 'baseline', mt: 1 }}>
                              <Typography variant="h4">
                                25
                              </Typography>
                              <Typography variant="body2" sx={{ ml: 1 }}>
                                分钟
                              </Typography>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                              完成康复计划训练 1 次
                            </Typography>
                            <Box 
                              sx={{ 
                                mt: 1,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center'
                              }}
                            >
                              <Box 
                                sx={{
                                  position: 'relative',
                                  display: 'inline-flex'
                                }}
                              >
                                <CircularProgress
                                  variant="determinate"
                                  value={65}
                                  size={50}
                                  thickness={5}
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
                                  <Typography variant="caption" color="text.secondary">
                                    65%
                                  </Typography>
                                </Box>
                              </Box>
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                      
                      <Grid item xs={12} md={4}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle2" color="text.secondary">
                              睡眠质量
                            </Typography>
                            <Box sx={{ display: 'flex', alignItems: 'baseline', mt: 1 }}>
                              <Typography variant="h4">
                                7.5
                              </Typography>
                              <Typography variant="body2" sx={{ ml: 1 }}>
                                小时
                              </Typography>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                              深睡: 2.3小时 | 浅睡: 5.2小时
                            </Typography>
                            <Box 
                              sx={{ 
                                height: 20, 
                                mt: 1,
                                display: 'flex',
                                overflow: 'hidden',
                                borderRadius: 1
                              }}
                            >
                              <Box sx={{ width: '30%', bgcolor: 'primary.dark', height: '100%' }} />
                              <Box sx={{ width: '50%', bgcolor: 'primary.light', height: '100%' }} />
                              <Box sx={{ width: '20%', bgcolor: 'grey.300', height: '100%' }} />
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                    </Grid>
                    
                    <Box sx={{ textAlign: 'center', mt: 3 }}>
                      <Button
                        variant="outlined"
                        component={Link}
                        to="/patient/health-records"
                        size="small"
                      >
                        查看更多健康数据
                      </Button>
                    </Box>
                  </Box>
                </Box>
              </TabPanel>
            </DialogContent>
            <DialogActions>
              <Button
                color="error"
                startIcon={<DeleteIcon />}
                onClick={() => handleDeleteDevice(selectedDevice.id)}
              >
                解除绑定
              </Button>
              <Button onClick={handleCloseDeviceDetail} color="primary">
                关闭
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>
      
      {/* 设备绑定向导对话框 */}
      <Dialog
        open={wizardState.open}
        onClose={handleCloseWizard}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">
              设备手动配置向导
            </Typography>
            <IconButton onClick={handleCloseWizard}>
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        
        <DialogContent dividers>
          <Box sx={{ minHeight: 300, display: 'flex', flexDirection: 'column' }}>
            {/* 步骤指示器 */}
            <Box sx={{ width: '100%', mb: 3 }}>
              <LinearProgress 
                variant="determinate" 
                value={(wizardState.activeStep / 2) * 100} 
                sx={{ height: 8, borderRadius: 4 }}
              />
              <Box 
                sx={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  mt: 1 
                }}
              >
                <Typography 
                  variant="body2" 
                  color={wizardState.activeStep >= 0 ? 'primary' : 'text.secondary'}
                >
                  1. 选择设备类型
                </Typography>
                <Typography 
                  variant="body2" 
                  color={wizardState.activeStep >= 1 ? 'primary' : 'text.secondary'}
                >
                  2. 设备信息
                </Typography>
                <Typography 
                  variant="body2" 
                  color={wizardState.activeStep >= 2 ? 'primary' : 'text.secondary'}
                >
                  3. 完成配置
                </Typography>
              </Box>
            </Box>
            
            {/* 步骤内容 */}
            {wizardState.activeStep === 0 && (
              <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
                <Typography variant="h6" gutterBottom>
                  选择设备类型
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  请选择您要绑定的设备类型
                </Typography>
                
                <Grid container spacing={2} sx={{ mt: 1 }}>
                  <Grid item xs={12} sm={6}>
                    <Card 
                      variant={wizardState.deviceType === 'wristband' ? 'elevation' : 'outlined'} 
                      elevation={3}
                      onClick={() => handleWizardFieldChange('deviceType', 'wristband')}
                      sx={{ 
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        '&:hover': { boxShadow: 3 },
                        bgcolor: wizardState.deviceType === 'wristband' ? 'primary.50' : 'inherit'
                      }}
                    >
                      <CardContent sx={{ textAlign: 'center' }}>
                        <WatchIcon sx={{ fontSize: 48, color: 'primary.main', mb: 1 }} />
                        <Typography variant="h6">智能手环</Typography>
                        <Typography variant="body2" color="text.secondary">
                          记录日常活动和训练数据
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card 
                      variant={wizardState.deviceType === 'monitor' ? 'elevation' : 'outlined'} 
                      elevation={3}
                      onClick={() => handleWizardFieldChange('deviceType', 'monitor')}
                      sx={{ 
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        '&:hover': { boxShadow: 3 },
                        bgcolor: wizardState.deviceType === 'monitor' ? 'primary.50' : 'inherit'
                      }}
                    >
                      <CardContent sx={{ textAlign: 'center' }}>
                        <SettingsRemoteIcon sx={{ fontSize: 48, color: 'primary.main', mb: 1 }} />
                        <Typography variant="h6">康复监测器</Typography>
                        <Typography variant="body2" color="text.secondary">
                          提供专业的康复训练监测与指导
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Box>
            )}
            
            {wizardState.activeStep === 1 && (
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h6" gutterBottom>
                  输入设备信息
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  请输入您设备的详细信息
                </Typography>
                
                <Grid container spacing={3} sx={{ mt: 1 }}>
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="设备名称"
                      variant="outlined"
                      value={wizardState.deviceName}
                      onChange={(e) => handleWizardFieldChange('deviceName', e.target.value)}
                      helperText="给您的设备起个名字，方便识别"
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="设备SN码"
                      variant="outlined"
                      value={wizardState.deviceCode}
                      onChange={(e) => handleWizardFieldChange('deviceCode', e.target.value)}
                      helperText="请输入设备背面或包装上的序列号/SN码"
                    />
                  </Grid>
                </Grid>
              </Box>
            )}
            
            {wizardState.activeStep === 2 && (
              <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                <CheckCircleIcon sx={{ fontSize: 60, color: 'success.main', mb: 2 }} />
                <Typography variant="h6" gutterBottom align="center">
                  设备配置完成
                </Typography>
                <Typography variant="body1" paragraph align="center">
                  您的{wizardState.deviceType === 'wristband' ? '智能手环' : '康复监测器'}已准备就绪
                </Typography>
                <Typography variant="body2" color="text.secondary" align="center">
                  设备名称: {wizardState.deviceName || `${wizardState.deviceType === 'wristband' ? '智能手环' : '康复监测器'}`}<br />
                  设备类型: {wizardState.deviceType === 'wristband' ? '智能手环' : '康复监测器'}<br />
                  设备SN码: {wizardState.deviceCode}
                </Typography>
              </Box>
            )}
          </Box>
        </DialogContent>
        
        <DialogActions>
          {wizardState.activeStep > 0 && (
            <Button onClick={handleWizardBack}>
              上一步
            </Button>
          )}
          <Box sx={{ flex: '1 1 auto' }} />
          {wizardState.activeStep === 0 && (
            <Button 
              onClick={handleWizardNext}
              variant="contained" 
              disabled={!wizardState.deviceType}
            >
              下一步
            </Button>
          )}
          {wizardState.activeStep === 1 && (
            <Button 
              onClick={handleWizardNext}
              variant="contained" 
              disabled={!wizardState.deviceCode}
            >
              下一步
            </Button>
          )}
          {wizardState.activeStep === 2 && (
            <Button 
              onClick={handleWizardComplete}
              variant="contained" 
              color="success"
            >
              完成配置
            </Button>
          )}
        </DialogActions>
      </Dialog>
      
      {/* 通知消息 */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
        message={snackbar.message}
      />
    </Box>
  );
};

export default DeviceBinding; 