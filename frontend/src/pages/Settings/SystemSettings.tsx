import React, { useState, useEffect } from 'react';
import { useSelector } from 'react-redux';
import { RootState } from '../../store';
import {
  Box,
  Container,
  Typography,
  Card,
  CardContent,
  Tabs,
  Tab,
  Switch,
  FormGroup,
  FormControlLabel,
  Divider,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Alert,
  Snackbar,
  CircularProgress,
  Grid,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogContentText
} from '@mui/material';
import {
  Save as SaveIcon,
  Refresh as RefreshIcon,
  Security as SecurityIcon,
  Notifications as NotificationsIcon,
  Palette as PaletteIcon,
  Storage as StorageIcon,
  AdminPanelSettings as AdminIcon,
  Backup as BackupIcon,
  Delete as DeleteIcon
} from '@mui/icons-material';

// 导入通知设置组件
import NotificationSettings from '../../components/common/NotificationSettings';
import httpClient from '../../services/httpClient';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`settings-tabpanel-${index}`}
      aria-labelledby={`settings-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

function a11yProps(index: number) {
  return {
    id: `settings-tab-${index}`,
    'aria-controls': `settings-tabpanel-${index}`,
  };
}

const SystemSettings: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });

  // 获取用户角色
  const userRole = useSelector((state: RootState) => state.auth.user?.role);

  // 界面设置状态
  const [uiSettings, setUiSettings] = useState({
    theme: 'light',
    language: 'zh-CN',
    compactMode: false,
    enableAnimations: true,
    showAdvancedFeatures: false
  });

  // 安全设置状态
  const [securitySettings, setSecuritySettings] = useState({
    twoFactorAuth: false,
    sessionTimeout: '30',
    autoLogout: true,
    loginNotifications: true,
    deviceTrust: false
  });

  // 系统设置状态（仅管理员可见）
  const [systemSettings, setSystemSettings] = useState({
    maintenanceMode: false,
    allowRegistration: true,
    dataRetentionDays: '365',
    backupFrequency: 'daily',
    logLevel: 'info'
  });

  // 数据清理对话框状态
  const [clearDataDialog, setClearDataDialog] = useState(false);

  const [syncSummary, setSyncSummary] = useState('人员同步记录在管理端的「同步记录」里。');
  const [lastBackup, setLastBackup] = useState('');

  useEffect(() => {
    httpClient.get('/settings/me').then(({ data }) => {
      if (data?.ui) setUiSettings(current => ({ ...current, ...data.ui }));
    }).catch(() => undefined);
    if (userRole !== 'admin') return;
    httpClient.get('/admin/settings/operations').then(({ data }) => {
      setSystemSettings({
        maintenanceMode: Boolean(data.maintenance_mode),
        allowRegistration: data.allow_registration !== false,
        dataRetentionDays: String(data.data_retention_days ?? 365),
        backupFrequency: data.backup_frequency || 'daily',
        logLevel: data.log_level || 'info',
      });
      setSecuritySettings(current => ({ ...current, loginNotifications: data.login_notifications !== false, sessionTimeout: String(data.session_timeout_minutes ?? 480) }));
      setLastBackup(data.last_backup_at ? new Date(data.last_backup_at).toLocaleString() : '');
    }).catch(() => undefined);
    httpClient.get('/integrations/forms/catalog/runs/summary').then(({ data }) => {
      const projects = Array.isArray(data?.projects) ? data.projects : [];
      setSyncSummary(projects.length ? `已有 ${projects.length} 个项目的人员导入记录。` : '还没有人员导入记录。');
    }).catch(() => setSyncSummary('人员同步记录在管理端的「同步记录」里。'));
  }, [userRole]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // 处理界面设置变更
  const handleUiSettingChange = (setting: string, value: any) => {
    setUiSettings(prev => ({
      ...prev,
      [setting]: value
    }));
  };

  // 处理安全设置变更
  const handleSecuritySettingChange = (setting: string, value: any) => {
    setSecuritySettings(prev => ({
      ...prev,
      [setting]: value
    }));
  };

  // 处理系统设置变更
  const handleSystemSettingChange = (setting: string, value: any) => {
    setSystemSettings(prev => ({
      ...prev,
      [setting]: value
    }));
  };

  const saveOperations = async () => {
    try {
      await httpClient.put('/admin/settings/operations', {
        allow_registration: systemSettings.allowRegistration,
        maintenance_mode: systemSettings.maintenanceMode,
        session_timeout_minutes: Number(securitySettings.sessionTimeout),
        data_retention_days: Number(systemSettings.dataRetentionDays),
        backup_frequency: systemSettings.backupFrequency,
        log_level: systemSettings.logLevel,
        login_notifications: securitySettings.loginNotifications,
      });
      setNotification({ open: true, message: '系统设置已保存。超过保留天数的日志和通知已清理。', severity: 'success' });
    } catch {
      setNotification({ open: true, message: '系统设置没有保存。', severity: 'error' });
    }
  };

  const downloadBackup = async () => {
    try {
      const response = await httpClient.get('/admin/settings/backup', { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'rehab-backup.json';
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setNotification({ open: true, message: '备份没有下载。', severity: 'error' });
    }
  };

  // 重置设置到默认值（仅重置本页内存状态）
  const handleResetSettings = (category: string) => {
    switch (category) {
      case 'ui':
        setUiSettings({
          theme: 'light',
          language: 'zh-CN',
          compactMode: false,
          enableAnimations: true,
          showAdvancedFeatures: false
        });
        break;
      case 'security':
        setSecuritySettings({
          twoFactorAuth: false,
          sessionTimeout: '30',
          autoLogout: true,
          loginNotifications: true,
          deviceTrust: false
        });
        break;
      case 'system':
        setSystemSettings({
          maintenanceMode: false,
          allowRegistration: true,
          dataRetentionDays: '365',
          backupFrequency: 'daily',
          logLevel: 'info'
        });
        break;
    }
    
    setNotification({
      open: true,
      message: `${category}设置已在本页重置为默认值（后端未接入，不会保存到服务器）`,
      severity: 'info'
    });
  };

  // 清理缓存数据
  const handleClearData = async () => {
    setLoading(true);
    try {
      // 清理本地存储的缓存数据
      const keysToKeep = ['token', 'userRole', 'userInfo'];
      const allKeys = Object.keys(localStorage);
      
      allKeys.forEach(key => {
        if (!keysToKeep.includes(key)) {
          localStorage.removeItem(key);
        }
      });

      setNotification({
        open: true,
        message: '缓存数据已清理',
        severity: 'success'
      });
    } catch (error) {
      setNotification({
        open: true,
        message: '清理缓存数据失败',
        severity: 'error'
      });
    } finally {
      setLoading(false);
      setClearDataDialog(false);
    }
  };

  // 关闭通知
  const handleCloseNotification = () => {
    setNotification(prev => ({ ...prev, open: false }));
  };

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        系统设置
      </Typography>
      
      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            aria-label="系统设置选项卡"
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab icon={<NotificationsIcon />} label="通知设置" {...a11yProps(0)} />
            <Tab icon={<PaletteIcon />} label="界面设置" {...a11yProps(1)} />
            <Tab icon={<SecurityIcon />} label="安全设置" {...a11yProps(2)} />
            <Tab icon={<StorageIcon />} label="数据管理" {...a11yProps(3)} />
            {userRole === 'admin' && (
              <Tab icon={<AdminIcon />} label="系统管理" {...a11yProps(4)} />
            )}
          </Tabs>
        </Box>

        {/* 通知设置 */}
        <TabPanel value={tabValue} index={0}>
          <NotificationSettings />
        </TabPanel>

        {/* 界面设置 */}
        <TabPanel value={tabValue} index={1}>
          <Box>
            <Typography variant="h6" gutterBottom>
              界面外观设置
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <FormControl fullWidth margin="normal">
                  <InputLabel>主题模式</InputLabel>
                  <Select
                    value={uiSettings.theme}
                    label="主题模式"
                    onChange={(e) => handleUiSettingChange('theme', e.target.value)}
                  >
                    <MenuItem value="light">浅色主题</MenuItem>
                    <MenuItem value="dark">深色主题</MenuItem>
                    <MenuItem value="auto">跟随系统</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControl fullWidth margin="normal">
                  <InputLabel>语言</InputLabel>
                  <Select
                    value={uiSettings.language}
                    label="语言"
                    onChange={(e) => handleUiSettingChange('language', e.target.value)}
                  >
                    <MenuItem value="zh-CN">简体中文</MenuItem>
                    <MenuItem value="zh-TW">繁体中文</MenuItem>
                    <MenuItem value="en-US">English</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>

            <Divider sx={{ my: 3 }} />

            <Typography variant="h6" gutterBottom>
              界面行为设置
            </Typography>
            <FormGroup>
              <FormControlLabel
                control={
                  <Switch
                    checked={uiSettings.compactMode}
                    onChange={(e) => handleUiSettingChange('compactMode', e.target.checked)}
                  />
                }
                label="紧凑模式（减少界面间距，显示更多内容）"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={uiSettings.enableAnimations}
                    onChange={(e) => handleUiSettingChange('enableAnimations', e.target.checked)}
                  />
                }
                label="启用动画效果"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={uiSettings.showAdvancedFeatures}
                    onChange={(e) => handleUiSettingChange('showAdvancedFeatures', e.target.checked)}
                  />
                }
                label="显示高级功能选项"
              />
            </FormGroup>

            <Alert severity="info" sx={{ mt: 3, mb: 2 }}>
              界面偏好会按当前账号保存。
            </Alert>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                startIcon={<SaveIcon />}
                onClick={async () => {
                  try {
                    await httpClient.put('/settings/me', { ui: uiSettings });
                    setNotification({ open: true, message: '界面设置已保存', severity: 'success' });
                  } catch {
                    setNotification({ open: true, message: '界面设置没有保存', severity: 'error' });
                  }
                }}
              >
                保存界面设置
              </Button>
              <Button
                variant="outlined"
                startIcon={<RefreshIcon />}
                onClick={() => handleResetSettings('ui')}
              >
                重置为默认
              </Button>
            </Box>
          </Box>
        </TabPanel>

        {/* 安全设置 */}
        <TabPanel value={tabValue} index={2}>
          <Box>
            <Typography variant="h6" gutterBottom>
              账户安全
            </Typography>
            <Alert severity="info" sx={{ mb: 2 }}>
              双重验证和信任设备由问卷系统账号负责，本系统不另发一套验证码。本地密码在个人资料里修改。
            </Alert>
            <FormGroup>
              <FormControlLabel
                control={
                  <Switch
                    checked={securitySettings.loginNotifications}
                    onChange={(e) => handleSecuritySettingChange('loginNotifications', e.target.checked)}
                    disabled={userRole !== 'admin'}
                  />
                }
                label="登录后写入一条站内通知"
              />
            </FormGroup>

            <Divider sx={{ my: 3 }} />

            <Typography variant="h6" gutterBottom>
              会话管理
            </Typography>
            <FormControl margin="normal" sx={{ minWidth: 200 }}>
              <InputLabel>会话超时时间</InputLabel>
              <Select
                value={securitySettings.sessionTimeout}
                label="会话超时时间"
                onChange={(e) => handleSecuritySettingChange('sessionTimeout', e.target.value)}
              >
                <MenuItem value="15">15分钟</MenuItem>
                <MenuItem value="30">30分钟</MenuItem>
                <MenuItem value="60">1小时</MenuItem>
                <MenuItem value="120">2小时</MenuItem>
                <MenuItem value="480">8小时</MenuItem>
              </Select>
            </FormControl>

            <Alert severity="info" sx={{ mt: 3, mb: 2 }}>
              会话时长作用于新的登录。统一登录会按这里的上限缩短本系统会话；问卷系统自己的会话不在这里改。
            </Alert>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button variant="contained" startIcon={<SaveIcon />} disabled={userRole !== 'admin'} onClick={saveOperations}>
                保存安全设置
              </Button>
            </Box>
          </Box>
        </TabPanel>

        {/* 数据管理 */}
        <TabPanel value={tabValue} index={3}>
          <Box>
            <Typography variant="h6" gutterBottom>
              数据存储设置
            </Typography>
            
            <List>
              <ListItem>
                <ListItemText
                  primary="缓存数据"
                  secondary="清理本地缓存数据可以释放存储空间，但可能需要重新加载某些内容"
                />
                <ListItemSecondaryAction>
                  <Button
                    variant="outlined"
                    color="warning"
                    startIcon={<DeleteIcon />}
                    onClick={() => setClearDataDialog(true)}
                  >
                    清理缓存
                  </Button>
                </ListItemSecondaryAction>
              </ListItem>
              
              <Divider />
              
              <ListItem>
                <ListItemText
                  primary="人员同步"
                  secondary={syncSummary}
                />
                <ListItemSecondaryAction>
                  <Chip label="导入记录" size="small" />
                </ListItemSecondaryAction>
              </ListItem>

              <Divider />

              <ListItem>
                <ListItemText
                  primary="离线数据"
                  secondary="临床记录不保存离线副本，避免把过期内容当成当前记录。"
                />
                <ListItemSecondaryAction>
                  <Chip label="不离线" size="small" />
                </ListItemSecondaryAction>
              </ListItem>
            </List>
          </Box>
        </TabPanel>

        {/* 系统管理（仅管理员可见） */}
        {userRole === 'admin' && (
          <TabPanel value={tabValue} index={4}>
            <Box>
              <Typography variant="h6" gutterBottom>
                系统管理设置
              </Typography>
              
              <Alert severity="warning" sx={{ mb: 3 }}>
                <strong>警告：</strong> 以下设置将影响整个系统的运行，请谨慎操作。
              </Alert>

              <FormGroup>
                <FormControlLabel
                  control={
                    <Switch
                      checked={systemSettings.maintenanceMode}
                      onChange={(e) => handleSystemSettingChange('maintenanceMode', e.target.checked)}
                    />
                  }
                  label="维护模式（启用后其他用户将无法访问系统）"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={systemSettings.allowRegistration}
                      onChange={(e) => handleSystemSettingChange('allowRegistration', e.target.checked)}
                    />
                  }
                  label="允许新用户注册"
                />
              </FormGroup>

              <Divider sx={{ my: 3 }} />

              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="数据保留天数"
                    type="number"
                    value={systemSettings.dataRetentionDays}
                    onChange={(e) => handleSystemSettingChange('dataRetentionDays', e.target.value)}
                    helperText="保存时清理早于这个天数的审计日志和通知，不删除临床记录。"
                  />
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>备份频率</InputLabel>
                    <Select
                      value={systemSettings.backupFrequency}
                      label="备份频率"
                      onChange={(e) => handleSystemSettingChange('backupFrequency', e.target.value)}
                    >
                      <MenuItem value="hourly">每小时</MenuItem>
                      <MenuItem value="daily">每天</MenuItem>
                      <MenuItem value="weekly">每周</MenuItem>
                      <MenuItem value="monthly">每月</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>日志级别</InputLabel>
                    <Select
                      value={systemSettings.logLevel}
                      label="日志级别"
                      onChange={(e) => handleSystemSettingChange('logLevel', e.target.value)}
                    >
                      <MenuItem value="debug">Debug</MenuItem>
                      <MenuItem value="info">Info</MenuItem>
                      <MenuItem value="warning">Warning</MenuItem>
                      <MenuItem value="error">Error</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              </Grid>

              <Alert severity="info" sx={{ mt: 3, mb: 2 }}>
                立即备份会下载一份去掉密码、令牌和头像的数据文件，每个集合最多 2000 条。服务保持运行时，会按备份频率在服务器数据目录再写一份同样的文件。上次备份：{lastBackup || '还没有'}。
              </Alert>
              <Box sx={{ display: 'flex', gap: 2 }}>
                <Button variant="contained" startIcon={<SaveIcon />} onClick={saveOperations}>保存系统设置</Button>
                <Button variant="outlined" startIcon={<BackupIcon />} color="info" onClick={downloadBackup}>立即备份</Button>
              </Box>
            </Box>
          </TabPanel>
        )}
      </Card>

      {/* 清理数据确认对话框 */}
      <Dialog
        open={clearDataDialog}
        onClose={() => setClearDataDialog(false)}
      >
        <DialogTitle>确认清理缓存数据</DialogTitle>
        <DialogContent>
          <DialogContentText>
            此操作将清理本地缓存的数据，包括临时文件和缓存内容。
            您的登录状态和个人设置不会受到影响。
            <br /><br />
            是否确定要继续？
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClearDataDialog(false)}>
            取消
          </Button>
          <Button
            onClick={handleClearData}
            color="warning"
            variant="contained"
            disabled={loading}
            startIcon={loading ? <CircularProgress size={20} /> : <DeleteIcon />}
          >
            {loading ? '清理中...' : '确认清理'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 通知消息 */}
      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={handleCloseNotification}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleCloseNotification} severity={notification.severity}>
          {notification.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default SystemSettings;
