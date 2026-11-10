import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Button,
  TextField,
  MenuItem,
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
  Chip,
  CircularProgress,
  Stack,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DevicesIcon from '@mui/icons-material/Devices';
import WatchIcon from '@mui/icons-material/Watch';
import SmartphoneIcon from '@mui/icons-material/Smartphone';
import SettingsRemoteIcon from '@mui/icons-material/SettingsRemote';
import SyncIcon from '@mui/icons-material/Sync';
import BatteryFullIcon from '@mui/icons-material/BatteryFull';
import CloseIcon from '@mui/icons-material/Close';
import InfoIcon from '@mui/icons-material/Info';
import DeleteIcon from '@mui/icons-material/Delete';
import TimelineIcon from '@mui/icons-material/Timeline';
import { Link } from 'react-router-dom';

// 导入设备数据展示组件与设备服务
import DeviceDataDisplay from '../../components/Device/DeviceDataDisplay';
import DeviceConnectionTest from '../../components/Device/DeviceConnectionTest';
import { deviceService, Device, DeviceCreatePayload, DeviceStatus } from '../../services/deviceService';

// 绑定表单状态接口
interface BindFormState {
  open: boolean;
  deviceType: string;
  name: string;
  model: string;
  manufacturer: string;
  connectionType: string;
  firmwareVersion: string;
}

// 可选的设备类型（device_type 为自由字符串，后端仅要求必填）
const DEVICE_TYPE_OPTIONS = ['手环', '血压计', '血糖仪', '体重秤', '体温计', '其他'];

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

// 提取后端返回的错误消息
const getApiErrorMessage = (err: any, fallback: string): string => {
  return err?.response?.data?.detail || err?.message || fallback;
};

// 时间格式化
const formatDateTime = (value?: string | null): string => {
  if (!value) return '未知';
  const date = new Date(value);
  return isNaN(date.getTime()) ? String(value) : date.toLocaleString();
};

// 设备状态映射为展示文案与颜色
const getStatusLabel = (status?: string | null): string => {
  switch ((status || '').toLowerCase()) {
    case 'online': return '在线';
    case 'offline': return '离线';
    case 'error': return '异常';
    case 'syncing': return '同步中';
    default: return status || '未知';
  }
};

const getStatusChipColor = (status?: string | null): 'success' | 'default' | 'error' | 'warning' => {
  switch ((status || '').toLowerCase()) {
    case 'online': return 'success';
    case 'offline': return 'default';
    case 'error': return 'error';
    default: return 'warning';
  }
};

const DeviceBinding: React.FC = () => {
  // 设备列表（真实数据：GET /api/devices）
  const [devices, setDevices] = React.useState<Device[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  // 设备详情对话框
  const [selectedDevice, setSelectedDevice] = React.useState<Device | null>(null);
  const [openDeviceDialog, setOpenDeviceDialog] = React.useState(false);
  const [dialogTabValue, setDialogTabValue] = React.useState(0);
  const [syncing, setSyncing] = React.useState(false);
  const [readingType, setReadingType] = React.useState('');
  const [readingValue, setReadingValue] = React.useState('');
  const [readingUnit, setReadingUnit] = React.useState('');
  const [readingVersion, setReadingVersion] = React.useState(0);
  // 详情打开时实时查询的状态（GET /api/devices/{id}/status）
  const [dialogStatus, setDialogStatus] = React.useState<DeviceStatus | null>(null);
  const [dialogStatusLoading, setDialogStatusLoading] = React.useState(false);

  // 解绑确认
  const [confirmUnbind, setConfirmUnbind] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);

  const [snackbar, setSnackbar] = React.useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });

  // 绑定表单状态（POST /api/devices/bind）
  const [bindForm, setBindForm] = React.useState<BindFormState>({
    open: false,
    deviceType: '',
    name: '',
    model: '',
    manufacturer: '',
    connectionType: '',
    firmwareVersion: ''
  });
  const [binding, setBinding] = React.useState(false);

  // 主标签页状态
  const [mainTabValue, setMainTabValue] = React.useState(0);

  // 加载设备列表
  const loadDevices = React.useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const list = await deviceService.getUserDevices();
      setDevices(list);
    } catch (err: any) {
      setLoadError(getApiErrorMessage(err, '获取设备列表失败，请稍后再试'));
    } finally {
      setLoading(false);
    }
  }, []);

  // 页面挂载时获取真实设备列表
  React.useEffect(() => {
    loadDevices();
  }, [loadDevices]);

  const handleOpenBindForm = () => {
    setBindForm({ open: true, deviceType: '', name: '', model: '', manufacturer: '', connectionType: '', firmwareVersion: '' });
  };

  const handleCloseBindForm = () => {
    if (binding) return;
    setBindForm(prev => ({ ...prev, open: false }));
  };

  const handleBindFieldChange = (field: keyof BindFormState, value: string) => {
    setBindForm(prev => ({ ...prev, [field]: value }));
  };

  // 提交绑定：调用真实的 POST /api/devices/bind，成功后重新拉取列表
  const handleBindSubmit = async () => {
    const name = bindForm.name.trim();
    if (!bindForm.deviceType || !name) return;

    setBinding(true);
    try {
      const payload: DeviceCreatePayload = {
        device_type: bindForm.deviceType,
        name,
      };
      if (bindForm.model.trim()) payload.model = bindForm.model.trim();
      if (bindForm.manufacturer.trim()) payload.manufacturer = bindForm.manufacturer.trim();
      if (bindForm.connectionType.trim()) payload.connection_type = bindForm.connectionType.trim();
      if (bindForm.firmwareVersion.trim()) payload.firmware_version = bindForm.firmwareVersion.trim();

      const created = await deviceService.bindDevice(payload);
      setBindForm(prev => ({ ...prev, open: false }));
      setSnackbar({
        open: true,
        message: `设备「${created?.name || name}」绑定成功`,
        severity: 'success'
      });
      await loadDevices();
    } catch (err: any) {
      setSnackbar({
        open: true,
        message: `绑定失败: ${getApiErrorMessage(err, '请检查设备信息后重试')}`,
        severity: 'error'
      });
    } finally {
      setBinding(false);
    }
  };

  // 打开设备详情，并实时查询设备状态
  const handleOpenDeviceDetail = async (device: Device) => {
    setSelectedDevice(device);
    setOpenDeviceDialog(true);
    setDialogTabValue(0);
    setDialogStatus(null);
    setDialogStatusLoading(true);
    try {
      setDialogStatus(await deviceService.getDeviceStatus(device.id));
    } catch {
      // 状态查询失败时回退展示列表中的已知信息，不伪造数据
    } finally {
      setDialogStatusLoading(false);
    }
  };

  const handleCloseDeviceDetail = () => {
    setOpenDeviceDialog(false);
    setConfirmUnbind(false);
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setDialogTabValue(newValue);
  };

  // 同步设备数据：调用真实的 POST /api/devices/{id}/sync
  const handleSyncDevice = async () => {
    if (!selectedDevice) return;

    setSyncing(true);
    try {
      const result = await deviceService.syncDeviceData(selectedDevice.id);
      const ok = result?.success !== false;
      setSnackbar({
        open: true,
        message: result?.message || `设备 ${selectedDevice.name} 数据同步完成`,
        severity: ok ? 'success' : 'error'
      });
      // 同步后刷新列表与实时状态
      await loadDevices();
      try {
        setDialogStatus(await deviceService.getDeviceStatus(selectedDevice.id));
      } catch {
        // 状态刷新失败不影响同步结果展示
      }
    } catch (err: any) {
      setSnackbar({
        open: true,
        message: `数据同步失败: ${getApiErrorMessage(err, '请稍后再试')}`,
        severity: 'error'
      });
    } finally {
      setSyncing(false);
    }
  };

  // 解绑设备：调用真实的 DELETE /api/devices/{id}/unbind
  const handleUnbindDevice = async () => {
    if (!selectedDevice) return;

    setDeleting(true);
    try {
      await deviceService.unbindDevice(selectedDevice.id);
      setOpenDeviceDialog(false);
      setConfirmUnbind(false);
      setSnackbar({
        open: true,
        message: `设备「${selectedDevice.name}」已解绑`,
        severity: 'info'
      });
      await loadDevices();
    } catch (err: any) {
      setSnackbar({
        open: true,
        message: `解绑失败: ${getApiErrorMessage(err, '请稍后再试')}`,
        severity: 'error'
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleCloseSnackbar = () => {
    setSnackbar(prev => ({ ...prev, open: false }));
  };

  const getDeviceIcon = (type: string) => {
    if (type.includes('手环') || type.includes('wristband')) return <WatchIcon />;
    if (type.includes('监测') || type.includes('monitor')) return <SettingsRemoteIcon />;
    if (type.includes('手机') || type.includes('phone')) return <SmartphoneIcon />;
    return <DevicesIcon />;
  };

  const getBatteryColor = (level: number | null | undefined) => {
    if (!level) return 'grey.500';
    if (level > 60) return 'success.main';
    if (level > 20) return 'warning.main';
    return 'error.main';
  };

  // 详情内展示的电量与状态：优先使用实时查询结果，回退到列表数据
  const displayBattery = dialogStatus
    ? (dialogStatus.battery_level ?? selectedDevice?.battery_level ?? null)
    : (selectedDevice?.battery_level ?? null);
  const displayStatus = dialogStatus?.status || selectedDevice?.status;
  const displayLastSync = dialogStatus?.last_sync_time || null;

  // 处理主标签页切换
  const handleMainTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setMainTabValue(newValue);
  };

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        设备绑定与管理
      </Typography>

      {/* 主标签页切换 */}
      <Paper sx={{ mb: 3 }}>
        <Tabs
          value={mainTabValue}
          onChange={handleMainTabChange}
          indicatorColor="primary"
          textColor="primary"
          centered
        >
          <Tab icon={<DevicesIcon />} iconPosition="start" label="设备管理" />
          <Tab icon={<TimelineIcon />} iconPosition="start" label="设备数据" />
        </Tabs>
      </Paper>

      {/* 设备管理标签页内容 */}
      {mainTabValue === 0 && (
        <Grid container spacing={3}>
          <Grid item xs={12} md={7}>
            <Paper sx={{ p: 3, mb: 3 }}>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">已绑定设备</Typography>
                <Button
                  variant="contained"
                  color="primary"
                  startIcon={<AddIcon />}
                  onClick={handleOpenBindForm}
                >
                  添加设备
                </Button>
              </Box>

              {loading ? (
                <Box textAlign="center" my={4}>
                  <CircularProgress size={28} />
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    正在加载设备列表...
                  </Typography>
                </Box>
              ) : loadError ? (
                <Alert
                  severity="error"
                  action={
                    <Button color="inherit" size="small" onClick={loadDevices}>
                      重试
                    </Button>
                  }
                >
                  {loadError}
                </Alert>
              ) : devices.length > 0 ? (
                <List>
                  {devices.map((device) => (
                    <React.Fragment key={device.id}>
                      <ListItem>
                        <ListItemIcon>
                          {getDeviceIcon(device.device_type)}
                        </ListItemIcon>
                        <ListItemText
                          primary={
                            <Box display="flex" alignItems="center" gap={1}>
                              {device.name}
                              <Chip
                                size="small"
                                label={getStatusLabel(device.status)}
                                color={getStatusChipColor(device.status)}
                                variant="outlined"
                              />
                            </Box>
                          }
                          secondary={`类型: ${device.device_type || '未知'} | 最后连接: ${formatDateTime(device.last_connected)}${device.battery_level != null ? ` | 电量: ${device.battery_level}%` : ''}`}
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
                <Alert severity="info">
                  暂无已绑定的设备。点击"添加设备"填写设备信息完成绑定。
                </Alert>
              )}
            </Paper>
          </Grid>

          <Grid item xs={12} md={5}>
            <Card>
              <CardContent>
                <Typography gutterBottom variant="h6" component="div">
                  康复监测设备说明
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  绑定您的智能康复监测设备后，系统将展示设备上报的真实训练与健康数据。
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
      )}

      {/* 设备数据标签页内容 */}
      {mainTabValue === 1 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>设备健康数据</Typography>
          <Divider sx={{ mb: 3 }} />

          {devices.length > 0 ? (
            <>
              <DeviceDataDisplay
                deviceId={devices[0].id}
                showChart={true}
                timeRange="day"
                onError={(error) => {
                  setSnackbar({
                    open: true,
                    message: `数据加载错误: ${error}`,
                    severity: 'error'
                  });
                }}
              />

              <Box mt={4}>
                <DeviceConnectionTest
                  deviceId={devices[0].id}
                  deviceType={devices[0].device_type}
                  onComplete={(success) => {
                    setSnackbar({
                      open: true,
                      message: success
                        ? '设备检查完成：状态与数据链路正常'
                        : '设备检查完成：发现问题，可尝试修复',
                      severity: success ? 'success' : 'warning'
                    });
                  }}
                />
              </Box>
            </>
          ) : (
            <Alert severity="info" sx={{ mb: 2 }}>
              {loading
                ? '正在加载设备列表...'
                : '您还没有绑定任何设备。请先在设备管理标签页中绑定设备，然后查看设备数据。'}
            </Alert>
          )}
        </Paper>
      )}

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
                  {getDeviceIcon(selectedDevice.device_type)}
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
                          <Typography variant="body2" color="text.secondary">设备类型</Typography>
                          <Typography variant="body1">
                            {selectedDevice.device_type || '未知'}
                          </Typography>
                        </Box>

                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">设备型号</Typography>
                          <Typography variant="body1">
                            {selectedDevice.model || '未知'}
                          </Typography>
                        </Box>

                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">制造商</Typography>
                          <Typography variant="body1">
                            {selectedDevice.manufacturer || '未知'}
                          </Typography>
                        </Box>

                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">连接类型</Typography>
                          <Typography variant="body1">
                            {selectedDevice.connection_type || '未知'}
                          </Typography>
                        </Box>

                        <Box>
                          <Typography variant="body2" color="text.secondary">固件版本</Typography>
                          <Typography variant="body1">
                            {selectedDevice.firmware_version || '未知'}
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
                          {dialogStatusLoading && (
                            <CircularProgress size={14} sx={{ ml: 1, verticalAlign: 'middle' }} />
                          )}
                        </Typography>
                        <Divider sx={{ mb: 2 }} />

                        <Box sx={{ mb: 1, display: 'flex', alignItems: 'center' }}>
                          <BatteryFullIcon sx={{ mr: 1, color: getBatteryColor(displayBattery) }} />
                          <Box sx={{ flex: 1 }}>
                            <Typography variant="body2" color="text.secondary">
                              电池电量
                            </Typography>
                            {displayBattery != null ? (
                              <>
                                <LinearProgress
                                  variant="determinate"
                                  value={Math.min(100, displayBattery)}
                                  sx={{
                                    height: 8,
                                    borderRadius: 4,
                                    mb: 1,
                                    '& .MuiLinearProgress-bar': {
                                      backgroundColor: getBatteryColor(displayBattery)
                                    }
                                  }}
                                />
                                <Typography variant="body2">
                                  {displayBattery}%
                                </Typography>
                              </>
                            ) : (
                              <Typography variant="body1">未知</Typography>
                            )}
                          </Box>
                        </Box>

                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">连接状态</Typography>
                          <Box display="flex" alignItems="center">
                            <Chip
                              size="small"
                              label={getStatusLabel(displayStatus)}
                              color={getStatusChipColor(displayStatus)}
                            />
                            {dialogStatus?.signal_strength != null && (
                              <Typography variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                                信号强度: {dialogStatus.signal_strength}/5
                              </Typography>
                            )}
                          </Box>
                        </Box>

                        <Box sx={{ mb: 1 }}>
                          <Typography variant="body2" color="text.secondary">最后连接时间</Typography>
                          <Typography variant="body1">
                            {formatDateTime(selectedDevice.last_connected)}
                          </Typography>
                        </Box>

                        <Box>
                          <Typography variant="body2" color="text.secondary">最后同步时间</Typography>
                          <Typography variant="body1">
                            {displayLastSync ? formatDateTime(displayLastSync) : '从未同步'}
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
                    设备数据
                  </Typography>
                  <Alert severity="info" sx={{ textAlign: 'left', mb: 2 }}>
                    还没有接入设备厂商接口。开始同步不会生成电量或测量值。下面可以登记一条你实际看到的读数，记录会标明“手工登记”。
                  </Alert>
                  <Stack direction="row" spacing={1} justifyContent="center" sx={{ mb: 2 }}>
                    <TextField size="small" label="类型" value={readingType} onChange={event => setReadingType(event.target.value)} />
                    <TextField size="small" label="数值" value={readingValue} onChange={event => setReadingValue(event.target.value)} />
                    <TextField size="small" label="单位" value={readingUnit} onChange={event => setReadingUnit(event.target.value)} />
                    <Button variant="outlined" disabled={!selectedDevice || !readingType.trim() || !readingValue.trim()} onClick={async () => {
                      if (!selectedDevice) return;
                      try {
                        await deviceService.recordReading(selectedDevice.id, {
                          data_type: readingType.trim(), value: readingValue.trim(), unit: readingUnit.trim(),
                          measured_at: new Date().toISOString(),
                        });
                        setReadingValue('');
                        setReadingVersion(value => value + 1);
                        setSnackbar({ open: true, message: '已保存手工登记的读数', severity: 'success' });
                      } catch (err: any) {
                        setSnackbar({ open: true, message: getApiErrorMessage(err, '读数没有保存'), severity: 'error' });
                      }
                    }}>登记读数</Button>
                  </Stack>

                  {syncing ? (
                    <Box sx={{ width: '100%', mt: 3 }}>
                      <LinearProgress />
                      <Typography variant="body2" sx={{ mt: 2 }}>
                        正在同步数据，请稍候...
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
                      最后同步: {displayLastSync ? formatDateTime(displayLastSync) : '从未同步'}
                    </Typography>
                  </Box>

                  {/* 真实设备数据展示（无数据时显示诚实空状态） */}
                  <Box sx={{ mt: 5, textAlign: 'left' }}>
                    <DeviceDataDisplay
                      key={readingVersion}
                      deviceId={selectedDevice.id}
                      showChart={true}
                      timeRange="day"
                      onError={(error) => {
                        setSnackbar({
                          open: true,
                          message: `数据加载错误: ${error}`,
                          severity: 'error'
                        });
                      }}
                    />
                  </Box>
                </Box>
              </TabPanel>
            </DialogContent>
            <DialogActions>
              <Button
                color="error"
                startIcon={<DeleteIcon />}
                onClick={() => setConfirmUnbind(true)}
                disabled={deleting}
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

      {/* 解绑确认对话框 */}
      <Dialog open={confirmUnbind} onClose={() => !deleting && setConfirmUnbind(false)} maxWidth="xs" fullWidth>
        <DialogTitle>确认解除绑定？</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            解绑后设备「{selectedDevice?.name}」将不再向您的账户上报数据，此操作通过服务端完成且不可撤销。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmUnbind(false)} disabled={deleting}>取消</Button>
          <Button
            onClick={handleUnbindDevice}
            color="error"
            variant="contained"
            disabled={deleting}
            startIcon={deleting ? <CircularProgress size={16} /> : <DeleteIcon />}
          >
            {deleting ? '解绑中...' : '确认解绑'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 绑定新设备对话框（真实绑定：POST /api/devices/bind） */}
      <Dialog
        open={bindForm.open}
        onClose={handleCloseBindForm}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">绑定新设备</Typography>
            {!binding && (
              <IconButton onClick={handleCloseBindForm}>
                <CloseIcon />
              </IconButton>
            )}
          </Box>
        </DialogTitle>

        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary" paragraph>
            请填写设备的真实信息，绑定后设备将关联到您的账户。
          </Typography>

          <Grid container spacing={3} sx={{ mt: 0 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                required
                select
                label="设备类型"
                variant="outlined"
                value={bindForm.deviceType}
                onChange={(e) => handleBindFieldChange('deviceType', e.target.value)}
              >
                {DEVICE_TYPE_OPTIONS.map((option) => (
                  <MenuItem key={option} value={option}>{option}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                required
                label="设备名称"
                variant="outlined"
                value={bindForm.name}
                onChange={(e) => handleBindFieldChange('name', e.target.value)}
                helperText="给设备起个名字，方便识别"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="设备型号（选填）"
                variant="outlined"
                value={bindForm.model}
                onChange={(e) => handleBindFieldChange('model', e.target.value)}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="制造商（选填）"
                variant="outlined"
                value={bindForm.manufacturer}
                onChange={(e) => handleBindFieldChange('manufacturer', e.target.value)}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="连接类型（选填）"
                variant="outlined"
                value={bindForm.connectionType}
                onChange={(e) => handleBindFieldChange('connectionType', e.target.value)}
                helperText="如 bluetooth / wifi"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="固件版本（选填）"
                variant="outlined"
                value={bindForm.firmwareVersion}
                onChange={(e) => handleBindFieldChange('firmwareVersion', e.target.value)}
              />
            </Grid>
          </Grid>
        </DialogContent>

        <DialogActions>
          <Button onClick={handleCloseBindForm} disabled={binding}>
            取消
          </Button>
          <Button
            onClick={handleBindSubmit}
            variant="contained"
            color="primary"
            disabled={!bindForm.deviceType || !bindForm.name.trim() || binding}
            startIcon={binding ? <CircularProgress size={16} /> : <AddIcon />}
          >
            {binding ? '绑定中...' : '确认绑定'}
          </Button>
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
