import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Paper,
  Chip,
  LinearProgress,
  Divider,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Badge,
  Alert,
} from '@mui/material';
import { styled } from '@mui/material/styles';

// 模拟一个图表组件 - 在实际应用中应该使用正式的图表库如 recharts 或 Chart.js
const MockChart = styled(Box)(({ theme }) => ({
  height: 180,
  width: '100%',
  backgroundColor: theme.palette.grey[100],
  borderRadius: theme.shape.borderRadius,
  position: 'relative',
  overflow: 'hidden',
  '&::before': {
    content: '""',
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: '70%',
    background: `linear-gradient(180deg, ${theme.palette.primary.main}33 0%, ${theme.palette.primary.main}22 100%)`,
  },
  '&::after': {
    content: '""',
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: '2px',
    backgroundColor: theme.palette.primary.main,
  }
}));

// 数据点组件
const DataPoint = styled(Box)<{ value: number }>(({ theme, value }) => ({
  position: 'absolute',
  width: 8,
  height: 8,
  backgroundColor: theme.palette.primary.main,
  borderRadius: '50%',
  bottom: `${(value / 200) * 70}%`,
  transform: 'translate(-50%, 50%)',
}));

// 模拟数据类型
interface DeviceData {
  id: string;
  deviceId: string;
  deviceName: string;
  deviceType: string;
  timestamp: string;
  metrics: {
    [key: string]: number | string;
  };
  status: 'normal' | 'warning' | 'error';
}

// 组件属性接口
interface DeviceDataDisplayProps {
  deviceId?: string;
  patientId?: string;
  showChart?: boolean;
  height?: number | string;
  timeRange?: 'day' | 'week' | 'month';
  onError?: (error: string) => void;
}

// 模拟一些测量数据
const generateMockData = (count: number, deviceType: string): DeviceData[] => {
  const now = new Date();
  const data: DeviceData[] = [];
  
  for (let i = 0; i < count; i++) {
    const timeOffset = i * (deviceType === 'bloodPressure' ? 6 : 1) * 3600000; // 每小时或每6小时
    const timestamp = new Date(now.getTime() - timeOffset);
    
    let metrics: { [key: string]: number | string } = {};
    let status: 'normal' | 'warning' | 'error' = 'normal';
    
    if (deviceType === 'heartRate') {
      // 心率模拟数据，正常范围60-100
      const value = Math.floor(70 + Math.random() * 30 + Math.sin(i / 3) * 10);
      metrics = { value };
      
      if (value > 100) status = 'warning';
      if (value > 120) status = 'error';
    } else if (deviceType === 'bloodPressure') {
      // 血压模拟数据，正常范围收缩压90-140，舒张压60-90
      const systolic = Math.floor(110 + Math.random() * 30 + Math.sin(i / 2) * 15);
      const diastolic = Math.floor(70 + Math.random() * 20 + Math.sin(i / 2) * 10);
      metrics = { systolic, diastolic };
      
      if (systolic > 140 || diastolic > 90) status = 'warning';
      if (systolic > 160 || diastolic > 100) status = 'error';
    } else if (deviceType === 'steps') {
      // 步数模拟数据
      const steps = Math.floor(500 + Math.random() * 1000 * (i % 24 < 12 ? (i % 12) / 6 : (12 - i % 12) / 6));
      metrics = { steps };
    } else if (deviceType === 'sleep') {
      // 睡眠模拟数据（小时）
      const duration = 5 + Math.random() * 4;
      const quality = Math.floor(60 + Math.random() * 40);
      metrics = { duration: duration.toFixed(1), quality };
      
      if (duration < 6) status = 'warning';
      if (duration < 5) status = 'error';
    }
    
    data.push({
      id: `data-${i}`,
      deviceId: `device-${deviceType}`,
      deviceName: deviceType === 'heartRate' ? '心率监测器' :
                 deviceType === 'bloodPressure' ? '血压计' :
                 deviceType === 'steps' ? '活动追踪器' : '睡眠监测器',
      deviceType,
      timestamp: timestamp.toISOString(),
      metrics,
      status
    });
  }
  
  return data;
};

const DeviceDataDisplay: React.FC<DeviceDataDisplayProps> = ({
  deviceId,
  patientId,
  showChart = true,
  height = 'auto',
  timeRange = 'day',
  onError
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deviceData, setDeviceData] = useState<{[key: string]: DeviceData[]}>({});
  const [selectedMetric, setSelectedMetric] = useState<string>('heartRate');
  const [timeRangeValue, setTimeRangeValue] = useState<string>(timeRange);
  
  // 模拟获取设备数据
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      
      try {
        // 在实际应用中，这里应该调用API获取真实数据
        // 模拟API调用延迟
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // 生成模拟数据
        const heartRateData = generateMockData(24, 'heartRate');
        const bloodPressureData = generateMockData(8, 'bloodPressure');
        const stepsData = generateMockData(24, 'steps');
        const sleepData = generateMockData(7, 'sleep');
        
        setDeviceData({
          heartRate: heartRateData,
          bloodPressure: bloodPressureData,
          steps: stepsData,
          sleep: sleepData
        });
        
        setLoading(false);
      } catch (err) {
        console.error('Error loading device data:', err);
        setError('获取设备数据失败，请稍后再试');
        setLoading(false);
        if (onError) onError('数据加载失败');
      }
    };
    
    loadData();
  }, [deviceId, patientId, timeRange, onError]);
  
  // 处理指标切换
  const handleMetricChange = (
    event: React.MouseEvent<HTMLElement>,
    newMetric: string | null,
  ) => {
    if (newMetric !== null) {
      setSelectedMetric(newMetric);
    }
  };
  
  // 处理时间范围切换
  const handleTimeRangeChange = (
    event: React.MouseEvent<HTMLElement>,
    newTimeRange: string | null,
  ) => {
    if (newTimeRange !== null) {
      setTimeRangeValue(newTimeRange);
    }
  };
  
  // 获取当前选择指标的最新数据
  const getLatestData = (type: string): DeviceData | null => {
    const data = deviceData[type];
    return data && data.length > 0 ? data[0] : null;
  };
  
  // 获取图表数据点
  const getChartDataPoints = (type: string, count: number = 12): DeviceData[] => {
    const data = deviceData[type];
    return data ? data.slice(0, count) : [];
  };
  
  // 获取状态颜色
  const getStatusColor = (status: 'normal' | 'warning' | 'error') => {
    switch (status) {
      case 'normal': return 'success';
      case 'warning': return 'warning';
      case 'error': return 'error';
      default: return 'primary';
    }
  };
  
  // 获取指标显示值
  const getMetricDisplay = (data: DeviceData | null) => {
    if (!data) return { value: '-', unit: '' };
    
    switch (data.deviceType) {
      case 'heartRate':
        return { 
          value: data.metrics.value?.toString() || '-', 
          unit: '次/分',
          label: '心率'
        };
      case 'bloodPressure':
        return { 
          value: `${data.metrics.systolic}/${data.metrics.diastolic}`, 
          unit: 'mmHg',
          label: '血压'
        };
      case 'steps':
        return { 
          value: data.metrics.steps?.toString() || '-', 
          unit: '步',
          label: '步数'
        };
      case 'sleep':
        return { 
          value: data.metrics.duration?.toString() || '-', 
          unit: '小时',
          label: '睡眠时长'
        };
      default:
        return { value: '-', unit: '', label: '未知' };
    }
  };
  
  // 获取图表Y轴值
  const getChartValue = (data: DeviceData) => {
    switch (data.deviceType) {
      case 'heartRate':
        return Number(data.metrics.value) || 0;
      case 'bloodPressure':
        return Number(data.metrics.systolic) || 0;
      case 'steps':
        return Math.min(200, (Number(data.metrics.steps) || 0) / 50);
      case 'sleep':
        return Number(data.metrics.duration) * 10 || 0;
      default:
        return 0;
    }
  };
  
  // 渲染图表
  const renderChart = () => {
    const chartData = getChartDataPoints(selectedMetric);
    if (chartData.length === 0) return null;
    
    return (
      <MockChart>
        {/* 简易图表模拟 - 在实际应用中应该使用专业图表库 */}
        {chartData.map((data, index) => (
          <Tooltip 
            key={data.id} 
            title={`${new Date(data.timestamp).toLocaleTimeString()}: ${getMetricDisplay(data).value} ${getMetricDisplay(data).unit}`}
          >
            <DataPoint 
              value={getChartValue(data)} 
              sx={{ left: `${(index / (chartData.length - 1)) * 100}%` }}
            />
          </Tooltip>
        ))}
      </MockChart>
    );
  };
  
  // 渲染指标切换按钮
  const renderMetricSelector = () => (
    <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center' }}>
      <ToggleButtonGroup
        value={selectedMetric}
        exclusive
        onChange={handleMetricChange}
        aria-label="数据指标选择"
        size="small"
      >
        <ToggleButton value="heartRate" aria-label="心率">
          <Badge 
            color={getLatestData('heartRate')?.status === 'normal' ? 'success' : 
                getLatestData('heartRate')?.status === 'warning' ? 'warning' : 'error'} 
            variant="dot"
            invisible={!getLatestData('heartRate') || getLatestData('heartRate')?.status === 'normal'}
          >
            心率
          </Badge>
        </ToggleButton>
        <ToggleButton value="bloodPressure" aria-label="血压">
          <Badge 
            color={getLatestData('bloodPressure')?.status === 'normal' ? 'success' : 
                getLatestData('bloodPressure')?.status === 'warning' ? 'warning' : 'error'} 
            variant="dot"
            invisible={!getLatestData('bloodPressure') || getLatestData('bloodPressure')?.status === 'normal'}
          >
            血压
          </Badge>
        </ToggleButton>
        <ToggleButton value="steps" aria-label="步数">
          步数
        </ToggleButton>
        <ToggleButton value="sleep" aria-label="睡眠">
          <Badge 
            color={getLatestData('sleep')?.status === 'normal' ? 'success' : 
                getLatestData('sleep')?.status === 'warning' ? 'warning' : 'error'} 
            variant="dot"
            invisible={!getLatestData('sleep') || getLatestData('sleep')?.status === 'normal'}
          >
            睡眠
          </Badge>
        </ToggleButton>
      </ToggleButtonGroup>
    </Box>
  );
  
  // 渲染时间范围选择器
  const renderTimeRangeSelector = () => (
    <Box sx={{ mb: 2, display: 'flex', justifyContent: 'center' }}>
      <ToggleButtonGroup
        value={timeRangeValue}
        exclusive
        onChange={handleTimeRangeChange}
        aria-label="时间范围选择"
        size="small"
      >
        <ToggleButton value="day" aria-label="今日">
          今日
        </ToggleButton>
        <ToggleButton value="week" aria-label="本周">
          本周
        </ToggleButton>
        <ToggleButton value="month" aria-label="本月">
          本月
        </ToggleButton>
      </ToggleButtonGroup>
    </Box>
  );
  
  // 渲染最新数据卡片
  const renderDataCards = () => {
    const types = ['heartRate', 'bloodPressure', 'steps', 'sleep'];
    
    return (
      <Grid container spacing={2}>
        {types.map(type => {
          const data = getLatestData(type);
          const metric = getMetricDisplay(data);
          const statusColor = data ? getStatusColor(data.status) : 'default';
          
          return (
            <Grid item xs={6} sm={3} key={type}>
              <Card variant={selectedMetric === type ? 'elevation' : 'outlined'} 
                    sx={{ 
                      boxShadow: selectedMetric === type ? 3 : 0,
                      borderColor: selectedMetric === type ? 'primary.main' : 'divider',
                      cursor: 'pointer'
                    }}
                    onClick={() => setSelectedMetric(type)}>
                <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                    <Typography variant="subtitle2" color="text.secondary">
                      {metric.label}
                    </Typography>
                    {data && data.status !== 'normal' && (
                      <Chip 
                        label={data.status === 'warning' ? '注意' : '异常'} 
                        color={statusColor}
                        size="small"
                      />
                    )}
                  </Box>
                  <Typography variant="h4" component="div" 
                    color={data?.status === 'normal' ? 'text.primary' : `${statusColor}.main`}>
                    {metric.value}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {metric.unit} · {data ? new Date(data.timestamp).toLocaleString() : '-'}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>
    );
  };
  
  if (loading) {
    return (
      <Box sx={{ width: '100%', height }}>
        <Typography variant="subtitle1" gutterBottom>加载设备数据中...</Typography>
        <LinearProgress />
      </Box>
    );
  }
  
  if (error) {
    return (
      <Box sx={{ width: '100%', height }}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }
  
  return (
    <Box sx={{ width: '100%', height }}>
      <Grid container spacing={3}>
        <Grid item xs={12}>
          {renderDataCards()}
        </Grid>
        
        {showChart && (
          <Grid item xs={12}>
            <Paper sx={{ p: 2 }}>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">{getMetricDisplay(getLatestData(selectedMetric)).label}数据趋势</Typography>
                {renderTimeRangeSelector()}
              </Box>
              
              <Divider sx={{ mb: 2 }} />
              
              {renderMetricSelector()}
              {renderChart()}
              
              <Box mt={1} display="flex" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">
                  {timeRangeValue === 'day' ? '过去24小时' : 
                   timeRangeValue === 'week' ? '过去7天' : '过去30天'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  最后更新: {new Date().toLocaleString()}
                </Typography>
              </Box>
            </Paper>
          </Grid>
        )}
      </Grid>
    </Box>
  );
};

export default DeviceDataDisplay; 