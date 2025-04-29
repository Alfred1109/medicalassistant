import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Button, 
  Card, 
  CardContent, 
  CircularProgress, 
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Grid, 
  Paper, 
  Step, 
  StepContent, 
  StepLabel, 
  Stepper, 
  TextField, 
  Typography,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Alert,
  Tooltip,
  Divider
} from '@mui/material';
import { 
  BluetoothSearching, 
  Check, 
  Close, 
  DevicesOther, 
  Refresh, 
  SyncProblem,
  WifiTethering,
  Help
} from '@mui/icons-material';

// 设备类型定义
interface Device {
  id: string;
  name: string;
  type: string;
  status: 'available' | 'paired' | 'offline';
  batteryLevel?: number;
  firmwareVersion?: string;
  connectionType: 'bluetooth' | 'wifi' | 'cable';
  lastSynced?: string;
}

// 绑定状态类型
type BindingStatus = 'idle' | 'scanning' | 'connecting' | 'configuring' | 'testing' | 'success' | 'failed';

const DeviceBindingWizard: React.FC = () => {
  // 状态管理
  const [activeStep, setActiveStep] = useState(0);
  const [availableDevices, setAvailableDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [bindingStatus, setBindingStatus] = useState<BindingStatus>('idle');
  const [patientId, setPatientId] = useState<string>('');
  const [configOptions, setConfigOptions] = useState({
    deviceName: '',
    syncFrequency: 'daily',
    notificationsEnabled: true
  });
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [openHelp, setOpenHelp] = useState(false);
  const [testResults, setTestResults] = useState<{passed: boolean, message: string} | null>(null);

  // 模拟扫描设备
  const scanForDevices = () => {
    setIsScanning(true);
    setBindingStatus('scanning');
    setErrorMessage(null);
    
    // 模拟异步API调用
    setTimeout(() => {
      const mockDevices: Device[] = [
        {
          id: 'bt-123456',
          name: '智能手环 Pro',
          type: '手环',
          status: 'available',
          batteryLevel: 85,
          firmwareVersion: '2.1.3',
          connectionType: 'bluetooth',
          lastSynced: '从未同步'
        },
        {
          id: 'bt-654321',
          name: '血压监测仪',
          type: '血压计',
          status: 'available',
          batteryLevel: 92,
          firmwareVersion: '1.5.0',
          connectionType: 'bluetooth',
          lastSynced: '从未同步'
        },
        {
          id: 'wifi-abcdef',
          name: '智能体重秤',
          type: '体重秤',
          status: 'available',
          batteryLevel: 76,
          firmwareVersion: '3.0.2',
          connectionType: 'wifi',
          lastSynced: '从未同步'
        }
      ];
      
      setAvailableDevices(mockDevices);
      setIsScanning(false);
      setBindingStatus('idle');
    }, 2000);
  };

  // 选择设备
  const handleDeviceSelect = (device: Device) => {
    setSelectedDevice(device);
    // 预设设备名称
    setConfigOptions({
      ...configOptions,
      deviceName: `${device.name} (${device.type})`
    });
  };

  // 连接设备
  const connectToDevice = () => {
    if (!selectedDevice) return;
    
    setBindingStatus('connecting');
    setErrorMessage(null);
    
    // 模拟连接过程
    setTimeout(() => {
      // 模拟90%成功率
      if (Math.random() > 0.1) {
        setBindingStatus('idle');
        setActiveStep(prev => prev + 1);
      } else {
        setBindingStatus('failed');
        setErrorMessage('连接设备失败，请确保设备已开启并在范围内');
      }
    }, 2000);
  };

  // 配置设备
  const configureDevice = () => {
    setBindingStatus('configuring');
    setErrorMessage(null);
    
    // 模拟配置过程
    setTimeout(() => {
      setBindingStatus('idle');
      setActiveStep(prev => prev + 1);
    }, 1500);
  };

  // 测试设备连接
  const testDeviceConnection = () => {
    setBindingStatus('testing');
    setErrorMessage(null);
    setTestResults(null);
    
    // 模拟测试过程
    setTimeout(() => {
      // 模拟85%成功率
      if (Math.random() > 0.15) {
        setTestResults({
          passed: true,
          message: '设备连接正常，数据同步测试成功。'
        });
        setBindingStatus('success');
      } else {
        setTestResults({
          passed: false,
          message: '设备数据同步测试失败，请检查网络连接或设备状态。'
        });
        setBindingStatus('failed');
      }
    }, 2500);
  };

  // 完成绑定
  const finalizeBinding = () => {
    // 这里应该调用API保存设备绑定信息
    console.log('设备绑定完成：', {
      device: selectedDevice,
      patientId,
      config: configOptions
    });
    
    // 重置表单，准备下一次绑定
    resetForm();
  };

  // 重置表单
  const resetForm = () => {
    setActiveStep(0);
    setSelectedDevice(null);
    setBindingStatus('idle');
    setPatientId('');
    setConfigOptions({
      deviceName: '',
      syncFrequency: 'daily',
      notificationsEnabled: true
    });
    setErrorMessage(null);
    setTestResults(null);
  };

  // 处理表单变更
  const handleConfigChange = (field: string, value: any) => {
    setConfigOptions({
      ...configOptions,
      [field]: value
    });
  };

  // 步骤定义
  const steps = [
    {
      label: '选择设备',
      description: '搜索并选择要绑定的健康监测设备',
      content: (
        <Box>
          <Box display="flex" alignItems="center" mb={2}>
            <Button 
              variant="contained" 
              color="primary" 
              onClick={scanForDevices}
              startIcon={<BluetoothSearching />}
              disabled={isScanning}
            >
              {isScanning ? '正在扫描...' : '扫描设备'}
            </Button>
            {isScanning && <CircularProgress size={24} sx={{ ml: 2 }} />}
            <Tooltip title="设备绑定帮助">
              <IconButton onClick={() => setOpenHelp(true)} sx={{ ml: 1 }}>
                <Help />
              </IconButton>
            </Tooltip>
          </Box>
          
          {availableDevices.length === 0 && !isScanning && (
            <Alert severity="info" sx={{ mb: 2 }}>
              未发现可用设备，请确保设备已开启并处于配对模式，然后点击"扫描设备"按钮
            </Alert>
          )}
          
          <List sx={{ width: '100%', bgcolor: 'background.paper' }}>
            {availableDevices.map((device) => (
              <Paper 
                key={device.id} 
                elevation={selectedDevice?.id === device.id ? 3 : 1}
                sx={{ 
                  mb: 1, 
                  border: selectedDevice?.id === device.id ? '2px solid #3f51b5' : 'none',
                  cursor: 'pointer'
                }}
                onClick={() => handleDeviceSelect(device)}
              >
                <ListItem>
                  <ListItemText
                    primary={
                      <Box display="flex" alignItems="center">
                        {device.connectionType === 'bluetooth' ? (
                          <BluetoothSearching color="primary" sx={{ mr: 1 }} />
                        ) : (
                          <WifiTethering color="primary" sx={{ mr: 1 }} />
                        )}
                        <Typography variant="subtitle1">{device.name}</Typography>
                        {selectedDevice?.id === device.id && (
                          <Check color="success" sx={{ ml: 1 }} />
                        )}
                      </Box>
                    }
                    secondary={
                      <>
                        <Typography variant="body2" component="span">
                          {`类型: ${device.type} | 电量: ${device.batteryLevel}% | 固件版本: ${device.firmwareVersion}`}
                        </Typography>
                      </>
                    }
                  />
                </ListItem>
              </Paper>
            ))}
          </List>
          
          {errorMessage && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {errorMessage}
            </Alert>
          )}
        </Box>
      )
    },
    {
      label: '患者关联',
      description: '将设备关联到特定患者',
      content: (
        <Box>
          <TextField
            label="患者ID"
            variant="outlined"
            fullWidth
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            margin="normal"
            helperText="请输入要关联的患者ID或扫描患者腕带"
          />
          
          <TextField
            label="设备名称"
            variant="outlined"
            fullWidth
            value={configOptions.deviceName}
            onChange={(e) => handleConfigChange('deviceName', e.target.value)}
            margin="normal"
            helperText="为设备设置一个易于识别的名称"
          />
          
          {errorMessage && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {errorMessage}
            </Alert>
          )}
        </Box>
      )
    },
    {
      label: '设备配置',
      description: '配置设备同步和通知选项',
      content: (
        <Box>
          <Paper elevation={1} sx={{ p: 2, mb: 2 }}>
            <Typography variant="subtitle1" gutterBottom>
              设备基本信息
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Typography variant="body2">
                  设备名称: {selectedDevice?.name}
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2">
                  设备类型: {selectedDevice?.type}
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2">
                  连接方式: {selectedDevice?.connectionType === 'bluetooth' ? '蓝牙' : 'WiFi'}
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2">
                  固件版本: {selectedDevice?.firmwareVersion}
                </Typography>
              </Grid>
            </Grid>
          </Paper>
          
          <Paper elevation={1} sx={{ p: 2 }}>
            <Typography variant="subtitle1" gutterBottom>
              同步设置
            </Typography>
            <Box>
              <TextField
                select
                label="同步频率"
                value={configOptions.syncFrequency}
                onChange={(e) => handleConfigChange('syncFrequency', e.target.value)}
                fullWidth
                margin="normal"
                SelectProps={{
                  native: true,
                }}
              >
                <option value="realtime">实时同步</option>
                <option value="hourly">每小时</option>
                <option value="daily">每日</option>
                <option value="manual">手动同步</option>
              </TextField>
              
              <Box display="flex" alignItems="center" mt={2}>
                <TextField
                  label="接收设备通知"
                  select
                  value={configOptions.notificationsEnabled ? 'yes' : 'no'}
                  onChange={(e) => handleConfigChange('notificationsEnabled', e.target.value === 'yes')}
                  sx={{ width: '100%' }}
                  SelectProps={{
                    native: true,
                  }}
                >
                  <option value="yes">是</option>
                  <option value="no">否</option>
                </TextField>
              </Box>
            </Box>
          </Paper>
          
          {bindingStatus === 'configuring' && (
            <Box display="flex" alignItems="center" justifyContent="center" mt={2}>
              <CircularProgress size={24} sx={{ mr: 1 }} />
              <Typography>正在配置设备...</Typography>
            </Box>
          )}
        </Box>
      )
    },
    {
      label: '测试连接',
      description: '测试设备连接和数据同步',
      content: (
        <Box>
          <Button
            variant="contained"
            color="primary"
            startIcon={bindingStatus === 'testing' ? <CircularProgress size={20} color="inherit" /> : <DevicesOther />}
            onClick={testDeviceConnection}
            disabled={bindingStatus === 'testing'}
            fullWidth
            sx={{ mb: 3 }}
          >
            {bindingStatus === 'testing' ? '测试中...' : '测试设备连接'}
          </Button>
          
          {testResults && (
            <Alert 
              severity={testResults.passed ? "success" : "error"}
              sx={{ mb: 2 }}
              action={
                !testResults.passed && (
                  <Button color="inherit" size="small" onClick={() => testDeviceConnection()}>
                    重试
                  </Button>
                )
              }
            >
              {testResults.message}
            </Alert>
          )}
          
          <Paper elevation={1} sx={{ p: 2 }}>
            <Typography variant="subtitle1" gutterBottom>
              设备概要
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Typography variant="body2">设备名称: {selectedDevice?.name}</Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2">别名: {configOptions.deviceName}</Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2">患者ID: {patientId}</Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2">同步频率: {
                  configOptions.syncFrequency === 'realtime' ? '实时同步' :
                  configOptions.syncFrequency === 'hourly' ? '每小时' :
                  configOptions.syncFrequency === 'daily' ? '每日' : '手动同步'
                }</Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2">接收通知: {configOptions.notificationsEnabled ? '是' : '否'}</Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="body2">状态: {
                  bindingStatus === 'success' ? '已连接' :
                  bindingStatus === 'failed' ? '连接失败' :
                  bindingStatus === 'testing' ? '测试中' : '待测试'
                }</Typography>
              </Grid>
            </Grid>
          </Paper>
        </Box>
      )
    }
  ];

  // 处理下一步
  const handleNext = () => {
    if (activeStep === 0) {
      // 验证是否选择了设备
      if (!selectedDevice) {
        setErrorMessage('请先选择一个设备');
        return;
      }
      connectToDevice();
    } else if (activeStep === 1) {
      // 验证患者ID
      if (!patientId.trim()) {
        setErrorMessage('请输入患者ID');
        return;
      }
      setActiveStep(prev => prev + 1);
    } else if (activeStep === 2) {
      configureDevice();
    } else if (activeStep === 3) {
      // 确认已测试成功
      if (bindingStatus !== 'success') {
        setErrorMessage('请先成功测试设备连接');
        return;
      }
      finalizeBinding();
    }
  };

  // 处理上一步
  const handleBack = () => {
    setActiveStep(prev => prev - 1);
    setErrorMessage(null);
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h5" component="h2" gutterBottom>
          设备绑定向导
        </Typography>
        <Typography variant="body2" color="textSecondary" paragraph>
          按照步骤绑定健康监测设备，完成后设备数据将自动同步到平台
        </Typography>
        
        <Divider sx={{ my: 2 }} />
        
        <Stepper activeStep={activeStep} orientation="vertical">
          {steps.map((step, index) => (
            <Step key={step.label}>
              <StepLabel>
                <Typography variant="subtitle1">{step.label}</Typography>
              </StepLabel>
              <StepContent>
                <Typography variant="body2" color="textSecondary" paragraph>
                  {step.description}
                </Typography>
                {step.content}
                <Box sx={{ mb: 2, mt: 2 }}>
                  <div>
                    <Button
                      variant="contained"
                      onClick={handleNext}
                      sx={{ mt: 1, mr: 1 }}
                      disabled={
                        bindingStatus === 'scanning' || 
                        bindingStatus === 'connecting' || 
                        bindingStatus === 'configuring' ||
                        bindingStatus === 'testing'
                      }
                    >
                      {index === steps.length - 1 ? '完成' : '下一步'}
                    </Button>
                    <Button
                      disabled={index === 0 || bindingStatus !== 'idle'}
                      onClick={handleBack}
                      sx={{ mt: 1, mr: 1 }}
                    >
                      上一步
                    </Button>
                  </div>
                </Box>
              </StepContent>
            </Step>
          ))}
        </Stepper>
        
        {activeStep === steps.length && (
          <Paper square elevation={0} sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              设备绑定完成！
            </Typography>
            <Typography paragraph>
              设备"{configOptions.deviceName}"已成功绑定到患者ID: {patientId}
            </Typography>
            <Button onClick={resetForm} sx={{ mt: 1, mr: 1 }}>
              绑定新设备
            </Button>
          </Paper>
        )}
      </CardContent>
      
      {/* 帮助对话框 */}
      <Dialog
        open={openHelp}
        onClose={() => setOpenHelp(false)}
        aria-labelledby="help-dialog-title"
      >
        <DialogTitle id="help-dialog-title">设备绑定帮助</DialogTitle>
        <DialogContent>
          <DialogContentText>
            <Typography paragraph>
              <strong>步骤1：准备设备</strong><br/>
              确保设备电量充足并已开启。大多数设备需要进入配对模式，请参考设备说明书了解如何激活配对模式。
            </Typography>
            <Typography paragraph>
              <strong>步骤2：扫描并连接</strong><br/>
              点击"扫描设备"按钮寻找可用的健康监测设备。从列表中选择您要绑定的设备，然后点击"下一步"。
            </Typography>
            <Typography paragraph>
              <strong>步骤3：关联患者</strong><br/>
              输入要关联的患者ID，并为设备设置一个易于识别的名称。
            </Typography>
            <Typography paragraph>
              <strong>步骤4：配置同步选项</strong><br/>
              设置数据同步频率和通知选项，以满足患者的监测需求。
            </Typography>
            <Typography paragraph>
              <strong>步骤5：测试连接</strong><br/>
              测试设备连接和数据同步，确保一切正常工作。
            </Typography>
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenHelp(false)} color="primary">
            关闭
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default DeviceBindingWizard; 