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
import DevicesIcon from '@mui/icons-material/Devices';
import StorageIcon from '@mui/icons-material/Storage';

import { deviceService } from '../../services/deviceService';

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

// 修复结果（与后端 POST /devices/{id}/repair 返回对齐）
interface RepairResult {
  success: boolean;
  message: string;
  repair_actions?: string[];
  repair_results?: Array<{ action: string; success: boolean; message?: string; reason?: string }>;
  new_status?: any;
}

// 组件属性
interface DeviceConnectionTestProps {
  deviceId?: string;
  deviceType?: string;
  onComplete?: (success: boolean, results: TestItem[]) => void;
  autoStart?: boolean;
}

// 初始化真实测试项（只包含可由后端接口验证的项目）
const buildInitialTests = (): TestItem[] => [
  {
    id: 'status',
    name: '设备状态检查',
    description: '通过 GET /devices/{id}/status 查询设备真实状态、电量与最后同步时间',
    status: 'pending',
    icon: <DevicesIcon />
  },
  {
    id: 'data',
    name: '数据读取检查',
    description: '尝试读取设备最近的数据记录，验证数据链路可用',
    status: 'pending',
    icon: <StorageIcon />
  }
];

// 提取后端返回的错误消息
const getApiErrorMessage = (err: any, fallback: string): string => {
  return err?.response?.data?.detail || err?.message || fallback;
};

const DeviceConnectionTest: React.FC<DeviceConnectionTestProps> = ({
  deviceId,
  deviceType = 'unknown',
  onComplete,
  autoStart = false
}) => {
  // 状态
  const [testInProgress, setTestInProgress] = useState(false);
  const [currentTestIndex, setCurrentTestIndex] = useState(-1);
  const [testResults, setTestResults] = useState<TestItem[]>(buildInitialTests);
  const [overallSuccess, setOverallSuccess] = useState<boolean | null>(null);
  const [testCompleted, setTestCompleted] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [repairResult, setRepairResult] = useState<RepairResult | null>(null);
  const [repairError, setRepairError] = useState<string | null>(null);

  // 更新单个测试项结果
  const updateTest = (index: number, partial: Partial<TestItem>) => {
    setTestResults(prevTests => {
      const newTests = [...prevTests];
      newTests[index] = { ...newTests[index], ...partial };
      return newTests;
    });
  };

  // 单项真实检查：全部来自后端接口，不模拟任何结果
  const runSingleTest = async (testId: string): Promise<Partial<TestItem>> => {
    if (!deviceId) {
      return { status: 'failure', message: '未指定设备' };
    }

    if (testId === 'status') {
      const s = await deviceService.getDeviceStatus(deviceId);
      const status = (s.status || '').toLowerCase();
      const detailsParts: string[] = [];
      if (s.battery_level !== undefined && s.battery_level !== null) {
        detailsParts.push(`电量: ${s.battery_level}%`);
      }
      if (s.signal_strength !== undefined && s.signal_strength !== null) {
        detailsParts.push(`信号强度: ${s.signal_strength}/5`);
      }
      if (s.last_sync_time) {
        detailsParts.push(`最后同步: ${new Date(s.last_sync_time).toLocaleString()}`);
      }
      if (s.message) {
        detailsParts.push(s.message);
      }
      const details = detailsParts.join(' | ');

      if (status === 'online') {
        return { status: 'success', message: '设备在线', details };
      }
      if (status === 'offline') {
        return { status: 'warning', message: '设备当前离线', details };
      }
      return {
        status: 'failure',
        message: `设备状态异常（${s.status || '未知'}）`,
        details
      };
    }

    // data: 读取最近一条数据记录验证数据链路
    const list = await deviceService.getDeviceData(deviceId, { limit: 1 });
    if (list.length > 0) {
      const latest = list[0];
      return {
        status: 'success',
        message: '设备数据可正常读取',
        details: `最近一条: ${new Date(latest.timestamp).toLocaleString()}（${latest.data_type}）`
      };
    }
    return {
      status: 'warning',
      message: '设备暂无数据记录',
      details: '设备尚未上报任何数据，可在同步数据后重新测试'
    };
  };

  // 运行全部测试（顺序执行真实检查）
  const runTests = async () => {
    if (!deviceId || testInProgress) return;

    setTestInProgress(true);
    setCurrentTestIndex(0);
    setOverallSuccess(null);
    setTestCompleted(false);
    setRepairResult(null);
    setRepairError(null);

    const tests = buildInitialTests();
    setTestResults(tests);

    let allOk = true;
    const finished: TestItem[] = [];

    for (let index = 0; index < tests.length; index++) {
      setCurrentTestIndex(index);
      updateTest(index, { status: 'running' });

      try {
        const result = await runSingleTest(tests[index].id);
        updateTest(index, result);
        finished.push({ ...tests[index], ...result } as TestItem);
        if (result.status === 'failure') allOk = false;
      } catch (err: any) {
        const failure = {
          status: 'failure' as const,
          message: getApiErrorMessage(err, '检查失败'),
        };
        updateTest(index, failure);
        finished.push({ ...tests[index], ...failure } as TestItem);
        allOk = false;
      }
    }

    setCurrentTestIndex(-1);
    setTestInProgress(false);
    setTestCompleted(true);
    setOverallSuccess(allOk);

    if (onComplete) {
      onComplete(allOk, finished);
    }
  };

  // 首次渲染时按需自动开始测试
  React.useEffect(() => {
    setTestResults(buildInitialTests());
    setOverallSuccess(null);
    setTestCompleted(false);
    setCurrentTestIndex(-1);
    setRepairResult(null);
    setRepairError(null);
    if (autoStart && deviceId) {
      runTests();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId, deviceType, autoStart]);

  // 修复动作：调用真实的 POST /devices/{id}/repair，并展示后端返回的修复结果
  const handleRepair = async () => {
    if (!deviceId || repairing) return;

    setRepairing(true);
    setRepairResult(null);
    setRepairError(null);

    try {
      const result = await deviceService.repairDevice(deviceId);
      setRepairResult(result);
      if (result.success) {
        // 修复成功后重新执行检查，验证修复效果
        await runTests();
      }
    } catch (err: any) {
      setRepairError(getApiErrorMessage(err, '修复请求失败'));
    } finally {
      setRepairing(false);
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

        {!deviceId && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            未指定设备，无法执行连接测试。
          </Alert>
        )}

        {deviceId && !testInProgress && !testCompleted && (
          <Alert severity="info" sx={{ mb: 2 }}>
            此工具将通过后端接口检查设备的真实状态（在线/离线、电量、最后同步时间）和数据读取链路。
            点击"开始测试"按钮开始检查。
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
              ? "检查完成，设备状态与数据链路正常。"
              : "检查完成，发现设备存在问题，可尝试执行修复。"}
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
                        <Chip label="检查中" size="small" color="primary" sx={{ ml: 1 }} />
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

        {/* 真实修复结果展示 */}
        {repairResult && (
          <Box sx={{ mt: 2 }}>
            <Alert severity={repairResult.success ? 'success' : 'error'}>
              {repairResult.message || (repairResult.success ? '修复完成' : '修复未能解决问题')}
            </Alert>
            {repairResult.repair_results && repairResult.repair_results.length > 0 && (
              <List dense>
                {repairResult.repair_results.map((r, idx) => (
                  <ListItem key={idx}>
                    <ListItemIcon>
                      {r.success
                        ? <CheckCircleIcon color="success" fontSize="small" />
                        : <ErrorIcon color="error" fontSize="small" />}
                    </ListItemIcon>
                    <ListItemText
                      primary={r.action}
                      secondary={r.success ? (r.message || '已执行') : (r.reason || r.message || '执行失败')}
                    />
                  </ListItem>
                ))}
              </List>
            )}
          </Box>
        )}

        {repairError && (
          <Alert severity="error" sx={{ mt: 2 }}>修复失败: {repairError}</Alert>
        )}

        <Stack direction="row" spacing={2} mt={3} justifyContent="center">
          <Button
            variant="contained"
            color="primary"
            disabled={!deviceId || testInProgress || repairing}
            onClick={runTests}
            sx={{ minWidth: 120 }}
          >
            {testCompleted ? "重新测试" : "开始测试"}
          </Button>

          <Button
            variant="outlined"
            color="primary"
            sx={{ minWidth: 120 }}
            onClick={handleRepair}
            disabled={!deviceId || testInProgress || repairing}
          >
            {repairing ? <CircularProgress size={20} /> : "修复设备"}
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
};

export default DeviceConnectionTest;
