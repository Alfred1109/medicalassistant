import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  CircularProgress,
  Alert,
  Chip,
  LinearProgress,
  Stack,
  Divider,
} from '@mui/material';

// 图标导入
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import BluetoothIcon from '@mui/icons-material/Bluetooth';
import WifiIcon from '@mui/icons-material/Wifi';
import StorageIcon from '@mui/icons-material/Storage';
import SettingsIcon from '@mui/icons-material/Settings';
import DevicesIcon from '@mui/icons-material/Devices';
import PowerIcon from '@mui/icons-material/Power';

// 测试项类型
interface TestItem {
  id: string;
  name: string;
  description: string;
  status: 'pending' | 'running' | 'success' | 'failure' | 'warning';
  message?: string;
  details?: string;
  icon: React.ReactNode;
}

// 组件属性
interface DeviceConnectionTestProps {
  deviceId?: string;
  deviceType?: string;
  onComplete?: (success: boolean, results: TestItem[]) => void;
  autoStart?: boolean;
}

const DeviceConnectionTest: React.FC<DeviceConnectionTestProps> = ({
  deviceId,
  deviceType = 'unknown',
  onComplete,
  autoStart = false
}) => {
  // 状态
  const [testInProgress, setTestInProgress] = useState(autoStart);
  const [currentTestIndex, setCurrentTestIndex] = useState(autoStart ? 0 : -1);
  const [testResults, setTestResults] = useState<TestItem[]>([]);
  const [overallSuccess, setOverallSuccess] = useState<boolean | null>(null);
  const [testCompleted, setTestCompleted] = useState(false);
  
  // 初始化测试项
  React.useEffect(() => {
    const initialTests: TestItem[] = [
      {
        id: 'bluetooth',
        name: '蓝牙连接',
        description: '检查设备蓝牙连接状态',
        status: 'pending',
        icon: <BluetoothIcon />
      },
      {
        id: 'wifi',
        name: '网络连接',
        description: '检查设备网络连接状态',
        status: 'pending',
        icon: <WifiIcon />
      },
      {
        id: 'battery',
        name: '电池状态',
        description: '检查设备电池电量',
        status: 'pending',
        icon: <PowerIcon />
      },
      {
        id: 'storage',
        name: '存储空间',
        description: '检查设备存储空间',
        status: 'pending',
        icon: <StorageIcon />
      },
      {
        id: 'config',
        name: '配置检查',
        description: '验证设备配置是否正确',
        status: 'pending',
        icon: <SettingsIcon />
      },
      {
        id: 'data_sync',
        name: '数据同步',
        description: '测试数据同步功能',
        status: 'pending',
        icon: <DevicesIcon />
      }
    ];
    
    setTestResults(initialTests);
    
    // 如果autoStart为true，自动开始测试
    if (autoStart) {
      runTest(0);
    }
  }, [deviceId, deviceType, autoStart]);
  
  // 开始测试
  const startTest = () => {
    setTestInProgress(true);
    setCurrentTestIndex(0);
    setOverallSuccess(null);
    setTestCompleted(false);
    
    // 重置测试状态
    setTestResults(prevTests => 
      prevTests.map(test => ({
        ...test,
        status: 'pending',
        message: undefined,
        details: undefined
      }))
    );
    
    // 开始第一个测试
    runTest(0);
  };
  
  // 运行单个测试
  const runTest = (index: number) => {
    if (index >= testResults.length) {
      // 所有测试完成
      completeAllTests();
      return;
    }
    
    setCurrentTestIndex(index);
    
    // 更新测试状态为运行中
    setTestResults(prevTests => {
      const newTests = [...prevTests];
      newTests[index] = {
        ...newTests[index],
        status: 'running'
      };
      return newTests;
    });
    
    // 模拟测试过程
    setTimeout(() => {
      // 模拟测试结果
      const result = simulateTestResult(testResults[index].id);
      
      // 更新测试结果
      setTestResults(prevTests => {
        const newTests = [...prevTests];
        newTests[index] = {
          ...newTests[index],
          ...result
        };
        return newTests;
      });
      
      // 继续下一个测试
      setTimeout(() => {
        runTest(index + 1);
      }, 500);
    }, 1000 + Math.random() * 1000); // 随机延迟，模拟不同测试的耗时
  };
  
  // 完成所有测试
  const completeAllTests = () => {
    const success = testResults.every(test => 
      test.status === 'success' || test.status === 'warning'
    );
    
    setOverallSuccess(success);
    setTestInProgress(false);
    setTestCompleted(true);
    
    if (onComplete) {
      onComplete(success, testResults);
    }
  };
  
  // 模拟测试结果
  const simulateTestResult = (testId: string): Partial<TestItem> => {
    // 模拟成功率
    const successRate = 0.8;
    const isSuccess = Math.random() < successRate;
    
    if (isSuccess) {
      // 成功结果
      switch (testId) {
        case 'bluetooth':
          return {
            status: 'success',
            message: '蓝牙连接正常',
            details: '信号强度: 良好 (-65dBm)'
          };
        case 'wifi':
          return {
            status: Math.random() > 0.7 ? 'warning' : 'success',
            message: Math.random() > 0.7 ? '网络连接较弱' : '网络连接正常',
            details: Math.random() > 0.7 ? '信号强度: 较弱 (-85dBm)' : '信号强度: 良好 (-60dBm)'
          };
        case 'battery':
          const batteryLevel = Math.floor(50 + Math.random() * 50);
          return {
            status: batteryLevel < 20 ? 'warning' : 'success',
            message: `电池电量: ${batteryLevel}%`,
            details: batteryLevel < 20 ? '电量较低，请及时充电' : '电量充足'
          };
        case 'storage':
          const storagePercent = Math.floor(60 + Math.random() * 30);
          return {
            status: storagePercent > 90 ? 'warning' : 'success',
            message: `剩余存储空间: ${100 - storagePercent}%`,
            details: storagePercent > 90 ? '存储空间接近满，建议清理数据' : '存储空间充足'
          };
        case 'config':
          return {
            status: 'success',
            message: '设备配置正确',
            details: `固件版本: v${Math.floor(1 + Math.random() * 3)}.${Math.floor(Math.random() * 10)}.${Math.floor(Math.random() * 10)}`
          };
        case 'data_sync':
          return {
            status: 'success',
            message: '数据同步正常',
            details: '最后同步时间: 刚刚'
          };
        default:
          return {
            status: 'success',
            message: '测试通过'
          };
      }
    } else {
      // 失败结果
      switch (testId) {
        case 'bluetooth':
          return {
            status: 'failure',
            message: '蓝牙连接失败',
            details: '无法与设备建立蓝牙连接，请确保设备在范围内且已开启蓝牙'
          };
        case 'wifi':
          return {
            status: 'failure',
            message: '网络连接失败',
            details: '设备无法连接到网络，请检查Wi-Fi设置'
          };
        case 'battery':
          return {
            status: 'warning',
            message: '电池电量低: 15%',
            details: '电量过低，部分功能可能受限，请及时充电'
          };
        case 'storage':
          return {
            status: 'warning',
            message: '存储空间不足: 5%',
            details: '存储空间几乎已满，请清理不必要的数据'
          };
        case 'config':
          return {
            status: 'failure',
            message: '配置验证失败',
            details: '设备配置不正确或已过期，请重新配置'
          };
        case 'data_sync':
          return {
            status: 'failure',
            message: '数据同步失败',
            details: '无法与服务器同步数据，请检查网络连接'
          };
        default:
          return {
            status: 'failure',
            message: '测试失败'
          };
      }
    }
  };
  
  // 获取测试状态图标
  const getTestStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircleIcon color="success" />;
      case 'failure':
        return <ErrorIcon color="error" />;
      case 'warning':
        return <ErrorIcon color="warning" />;
      case 'running':
        return <CircularProgress size={20} />;
      default:
        return null;
    }
  };
  
  // 获取总体测试进度
  const getOverallProgress = () => {
    const completed = testResults.filter(test => 
      test.status !== 'pending' && test.status !== 'running'
    ).length;
    
    return (completed / testResults.length) * 100;
  };
  
  return (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">设备连接测试</Typography>
          <Chip 
            label={deviceId ? `设备ID: ${deviceId}` : '未指定设备'} 
            color="primary" 
            variant="outlined" 
          />
        </Box>
        
        {!testInProgress && !testCompleted && (
          <Alert severity="info" sx={{ mb: 2 }}>
            此工具将测试设备的连接状态、电池电量、存储空间和数据同步功能。
            点击"开始测试"按钮开始全面测试。
          </Alert>
        )}
        
        {testInProgress && (
          <Box mb={3}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography variant="body2">
                测试进度: {Math.round(getOverallProgress())}%
              </Typography>
              <Typography variant="body2">
                {currentTestIndex + 1} / {testResults.length}
              </Typography>
            </Box>
            <LinearProgress 
              variant="determinate" 
              value={getOverallProgress()} 
              sx={{ height: 8, borderRadius: 4 }}
            />
          </Box>
        )}
        
        {testCompleted && overallSuccess !== null && (
          <Alert 
            severity={overallSuccess ? "success" : "error"} 
            sx={{ mb: 3 }}
          >
            {overallSuccess 
              ? "所有测试已完成，设备连接状态良好！" 
              : "测试完成，检测到一些问题需要解决。"}
          </Alert>
        )}
        
        <List>
          {testResults.map((test, index) => (
            <React.Fragment key={test.id}>
              <ListItem
                sx={{
                  backgroundColor: test.status === 'running' 
                    ? 'rgba(25, 118, 210, 0.08)' 
                    : 'transparent',
                  borderRadius: 1,
                  transition: 'background-color 0.3s'
                }}
              >
                <ListItemIcon>
                  {test.status === 'pending' || test.status === 'running' 
                    ? test.icon 
                    : getTestStatusIcon(test.status)}
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Box display="flex" alignItems="center">
                      <Typography variant="body1">{test.name}</Typography>
                      {test.status === 'running' && (
                        <Chip label="测试中" size="small" color="primary" sx={{ ml: 1 }} />
                      )}
                    </Box>
                  }
                  secondary={
                    <>
                      <Typography variant="body2" color="text.secondary">
                        {test.status === 'pending' ? test.description : (test.message || test.description)}
                      </Typography>
                      {test.details && test.status !== 'pending' && (
                        <Typography variant="caption" component="div" color="text.secondary" sx={{ mt: 0.5 }}>
                          {test.details}
                        </Typography>
                      )}
                    </>
                  }
                />
              </ListItem>
              {index < testResults.length - 1 && <Divider component="li" variant="inset" />}
            </React.Fragment>
          ))}
        </List>
        
        <Stack direction="row" spacing={2} mt={3} justifyContent="center">
          <Button
            variant="contained"
            color="primary"
            disabled={testInProgress}
            onClick={startTest}
            sx={{ minWidth: 120 }}
          >
            {testCompleted ? "重新测试" : "开始测试"}
          </Button>
          
          {testCompleted && (
            <Button
              variant="outlined"
              color="primary"
              sx={{ minWidth: 120 }}
              onClick={() => {
                // 模拟修复问题
                if (!overallSuccess) {
                  setTestResults(prevTests => 
                    prevTests.map(test => ({
                      ...test,
                      status: test.status === 'failure' ? 'warning' : test.status,
                      message: test.status === 'failure' ? '问题已修复，但需要注意' : test.message
                    }))
                  );
                  setOverallSuccess(true);
                }
              }}
              disabled={overallSuccess === true}
            >
              修复问题
            </Button>
          )}
        </Stack>
      </Paper>
    </Box>
  );
};

export default DeviceConnectionTest; 