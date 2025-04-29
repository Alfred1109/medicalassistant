import React, { useState, useEffect, FC } from 'react';
import {
  Box,
  Typography,
  Divider,
  Paper,
  Tab,
  Tabs,
  Button,
  Snackbar,
  Alert,
  Stack,
  Chip,
  CircularProgress,
} from '@mui/material';
import Badge from '@mui/material/Badge';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import ShareIcon from '@mui/icons-material/Share';
import FilterListIcon from '@mui/icons-material/FilterList';
import RefreshIcon from '@mui/icons-material/Refresh';
import WarningIcon from '@mui/icons-material/Warning';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

// 导入组件
import HealthDataTimeline from '../../components/HealthManager/HealthDataTimeline';

// API URL
const API_BASE_URL = 'http://localhost:8000';

// 健康数据时间线项目类型
interface HealthDataTimelineItem {
  id: string;
  data_type: string;
  title: string;
  description: string;
  value: string | number;
  unit: string;
  timestamp: string;
  metadata?: {
    device?: string;
    location?: string;
    notes?: string;
    tags?: string[];
    alert_status?: string;
    alert_level?: string;
    [key: string]: any;
  };
}

// 健康数据类型
interface HealthData {
  id: string;
  patient_id: string;
  patient_name?: string;
  data_type: string;
  value: string | number | { [key: string]: any };
  unit?: string;
  measured_at?: string;
  recorded_at?: string;
  device?: string;
  additional_info?: { [key: string]: any };
  tags?: string[];
  notes?: string;
  alert_level?: string;
  alert_status?: string;
  alert_message?: string;
  recorded_by?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: any;
}

// 预警数据类型
interface AlertData {
  id: string;
  health_data_id: string;
  patient_id: string;
  data_type: string;
  value: number | { [key: string]: any };
  alert_level: string;
  status: string;
  alert_message?: string;
}

// 转换健康数据到时间线项目
const convertHealthDataToTimelineItems = (healthData: HealthData[]): HealthDataTimelineItem[] => {
  return healthData.map(item => ({
    id: item.id,
    data_type: item.data_type,
    title: getDataTitle(item.data_type, item),
    description: getDataDescription(item.data_type, item),
    value: getDisplayValue(item),
    unit: item.unit || getUnitByDataType(item.data_type),
    timestamp: item.measured_at || item.recorded_at || '',
    metadata: {
      device: item.device,
      notes: item.notes,
      tags: item.tags,
      alert_status: item.alert_status,
      alert_level: item.alert_level
    }
  }));
};

// 获取单位
const getUnitByDataType = (dataType: string): string => {
  const unitMap: Record<string, string> = {
    blood_pressure: 'mmHg',
    blood_glucose: 'mmol/L',
    heart_rate: 'bpm',
    body_temperature: '°C',
    weight: 'kg',
    height: 'cm',
    oxygen_saturation: '%',
    respiratory_rate: '次/分',
    step_count: '步',
  };
  return unitMap[dataType] || '';
};

// 获取数据标题
const getDataTitle = (dataType: string, data: HealthData): string => {
  const dataTypeMap: Record<string, string> = {
    blood_pressure: '血压测量',
    blood_glucose: '血糖检测',
    heart_rate: '心率监测',
    body_temperature: '体温记录',
    weight: '体重记录',
    height: '身高测量',
    sleep: '睡眠记录',
    step_count: '步数统计',
    oxygen_saturation: '血氧监测',
    respiratory_rate: '呼吸频率'
  };
  
  // 如果有预警信息，添加预警标记
  let title = dataTypeMap[dataType] || `${dataType}记录`;
  if (data.alert_level === 'warning') {
    title = `⚠️ ${title} (警告)`;
  } else if (data.alert_level === 'critical') {
    title = `🚨 ${title} (严重)`;
  }
  
  return title;
};

// 获取数据描述
const getDataDescription = (dataType: string, data: HealthData): string => {
  let description = '';
  
  // 添加预警信息
  if (data.alert_level) {
    const alertMsg = data.alert_level === 'warning' ? '警告: 数值超出正常范围' : '严重: 数值大幅偏离正常范围';
    description += `${alertMsg}`;
    
    if (data.alert_message) {
      description += ` - ${data.alert_message}`;
    }
    
    description += '\n';
  }
  
  if (data.notes) {
    description += data.notes;
  }
  
  if (data.tags && data.tags.length > 0) {
    description += description ? '\n' : '';
    description += `标签: ${data.tags.join(', ')}`;
  }
  
  return description;
};

// 获取显示值
const getDisplayValue = (data: HealthData): string | number => {
  if (data.data_type === 'blood_pressure') {
    if (data.additional_info && data.additional_info.systolic && data.additional_info.diastolic) {
      return `${data.additional_info.systolic}/${data.additional_info.diastolic}`;
    } else if (typeof data.value === 'object' && 'systolic' in data.value && 'diastolic' in data.value) {
      const bpValue = data.value as { systolic: number, diastolic: number };
      return `${bpValue.systolic}/${bpValue.diastolic}`;
    }
  }
  
  return data.value as string | number;
};

// 模拟健康数据
const mockHealthData: HealthData[] = [
  {
    id: '1',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'blood_pressure',
    value: '120/80',
    unit: 'mmHg',
    measured_at: '2023-05-08T09:15:00Z',
    device: 'Omron HEM-7121',
    additional_info: {
      systolic: 120,
      diastolic: 80,
      position: 'sitting',
      arm: 'left'
    },
    tags: ['晨检', '空腹'],
    notes: '早晨起床后测量',
    recorded_by: 'user1',
    created_at: '2023-05-08T09:20:00Z',
    updated_at: '2023-05-08T09:20:00Z'
  },
  {
    id: '2',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'blood_glucose',
    value: '5.6',
    unit: 'mmol/L',
    measured_at: '2023-05-08T12:30:00Z',
    device: 'Accu-Chek Active',
    additional_info: {
      timing: 'after_meal',
      meal_type: 'lunch'
    },
    tags: ['餐后2小时'],
    notes: '午餐后测量',
    recorded_by: 'user1',
    created_at: '2023-05-08T12:35:00Z',
    updated_at: '2023-05-08T12:35:00Z'
  },
  {
    id: '3',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'heart_rate',
    value: '72',
    unit: 'bpm',
    measured_at: '2023-05-08T15:45:00Z',
    device: 'Apple Watch Series 7',
    additional_info: {
      activity: 'resting'
    },
    tags: ['静息'],
    notes: '下午休息时测量',
    recorded_by: 'user1',
    created_at: '2023-05-08T15:50:00Z',
    updated_at: '2023-05-08T15:50:00Z'
  },
  {
    id: '4',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'body_temperature',
    value: '36.5',
    unit: '°C',
    measured_at: '2023-05-08T18:00:00Z',
    device: 'Braun ThermoScan 7',
    additional_info: {
      method: 'oral'
    },
    tags: ['日常检查'],
    notes: '晚餐前测量',
    recorded_by: 'user1',
    created_at: '2023-05-08T18:05:00Z',
    updated_at: '2023-05-08T18:05:00Z'
  },
  {
    id: '5',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'weight',
    value: '70.5',
    unit: 'kg',
    measured_at: '2023-05-09T07:00:00Z',
    device: 'Xiaomi Smart Scale',
    additional_info: {},
    tags: ['晨检'],
    notes: '晨起测量',
    recorded_by: 'user1',
    created_at: '2023-05-09T07:05:00Z',
    updated_at: '2023-05-09T07:05:00Z'
  },
  {
    id: '6',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'oxygen_saturation',
    value: '98',
    unit: '%',
    measured_at: '2023-05-09T14:20:00Z',
    device: 'Fingertip Pulse Oximeter',
    additional_info: {},
    tags: ['例行检查'],
    notes: '下午休息时测量',
    recorded_by: 'user1',
    created_at: '2023-05-09T14:25:00Z',
    updated_at: '2023-05-09T14:25:00Z'
  },
  {
    id: '7',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'heart_rate',
    value: '68',
    unit: 'bpm',
    measured_at: '2023-05-09T14:30:00Z',
    device: 'Apple Watch Series 7',
    additional_info: {
      activity: 'resting'
    },
    tags: ['静息'],
    notes: '下午休息时测量',
    recorded_by: 'user1',
    created_at: '2023-05-09T14:35:00Z',
    updated_at: '2023-05-09T14:35:00Z'
  },
  {
    id: '8',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'blood_pressure',
    value: '118/78',
    unit: 'mmHg',
    measured_at: '2023-05-09T18:45:00Z',
    device: 'Omron HEM-7121',
    additional_info: {
      systolic: 118,
      diastolic: 78,
      position: 'sitting',
      arm: 'left'
    },
    tags: ['晚间检查'],
    notes: '晚餐后测量',
    recorded_by: 'user1',
    created_at: '2023-05-09T18:50:00Z',
    updated_at: '2023-05-09T18:50:00Z'
  },
  {
    id: '9',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'step_count',
    value: '8652',
    unit: '步',
    measured_at: '2023-05-09T21:00:00Z',
    device: 'Fitbit Charge 5',
    additional_info: {
      distance: 6.3,
      distance_unit: 'km',
      calories: 345
    },
    tags: ['日常活动'],
    notes: '今日步数统计',
    recorded_by: 'user1',
    created_at: '2023-05-09T21:05:00Z',
    updated_at: '2023-05-09T21:05:00Z'
  },
  {
    id: '10',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'blood_glucose',
    value: '5.4',
    unit: 'mmol/L',
    measured_at: '2023-05-10T07:30:00Z',
    device: 'Accu-Chek Active',
    additional_info: {
      timing: 'fasting'
    },
    tags: ['空腹'],
    notes: '早晨空腹测量',
    recorded_by: 'user1',
    created_at: '2023-05-10T07:35:00Z',
    updated_at: '2023-05-10T07:35:00Z'
  }
];

// 健康数据时间线页面组件
const HealthDataTimelinePage: React.FC = () => {
  // 状态
  const [loading, setLoading] = React.useState<boolean>(false);
  const [error, setError] = React.useState<string | null>(null);
  const [healthData, setHealthData] = React.useState<HealthData[]>([]);
  const [timelineData, setTimelineData] = React.useState<HealthDataTimelineItem[]>([]);
  const [alerts, setAlerts] = React.useState<AlertData[]>([]);
  const [showAlertsOnly, setShowAlertsOnly] = React.useState<boolean>(false);
  const [snackbar, setSnackbar] = React.useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });
  
  // 获取患者ID，如果没有则使用默认值
  const { patientId = '1001' } = useParams<{ patientId?: string }>();
  const navigate = useNavigate();
  
  // 加载健康数据
  const loadHealthData = async () => {
    try {
      setLoading(true);
      
      // 获取健康数据
      // 实际项目中替换为真实API调用
      // const response = await axios.get(`${API_BASE_URL}/api/health-records/health-data?patient_id=${patientId}`);
      // const data = response.data;
      
      // 临时使用模拟数据
      await new Promise(resolve => setTimeout(resolve, 500));
      const filteredData = mockHealthData.filter(item => item.patient_id === patientId);
      
      // 获取预警数据
      try {
        // 实际项目中，这里应该调用预警API
        // const alertsResponse = await axios.get(`${API_BASE_URL}/api/health/alerts/alerts?patient_id=${patientId}`);
        // const alertsData = alertsResponse.data;
        
        // 临时使用模拟预警数据
        const mockAlerts: AlertData[] = [
          {
            id: 'a1',
            health_data_id: '3',
            patient_id: '1001',
            data_type: 'heart_rate',
            value: 72,
            alert_level: 'warning',
            status: 'active',
            alert_message: '心率略高于正常范围'
          },
          {
            id: 'a2',
            health_data_id: '6',
            patient_id: '1001',
            data_type: 'oxygen_saturation',
            value: 98,
            alert_level: 'critical',
            status: 'active',
            alert_message: '血氧饱和度异常波动'
          }
        ];
        
        setAlerts(mockAlerts);
        
        // 将预警信息关联到健康数据
        const dataWithAlerts = filteredData.map(item => {
          const relatedAlert = mockAlerts.find(alert => alert.health_data_id === item.id);
          if (relatedAlert) {
            return {
              ...item,
              alert_level: relatedAlert.alert_level,
              alert_status: relatedAlert.status,
              alert_message: relatedAlert.alert_message
            };
          }
          return item;
        });
        
        setHealthData(dataWithAlerts);
        
        // 转换为时间线数据
        const timelineItems = convertHealthDataToTimelineItems(dataWithAlerts);
        setTimelineData(timelineItems);
      } catch (alertErr) {
        console.error('获取健康预警数据失败:', alertErr);
        // 即使预警API失败，仍然显示基本健康数据
        setHealthData(filteredData);
        const timelineItems = convertHealthDataToTimelineItems(filteredData);
        setTimelineData(timelineItems);
      }
      
      setError(null);
    } catch (err) {
      console.error('加载健康数据失败:', err);
      setError('加载健康数据失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };
  
  // 初始化加载数据
  React.useEffect(() => {
    loadHealthData();
  }, [patientId]);
  
  // 处理时间线项目点击事件
  const handleTimelineItemClick = (item: HealthDataTimelineItem) => {
    // 查找原始健康数据
    const originalData = healthData.find(data => data.id === item.id);
    
    if (originalData) {
      if (originalData.alert_level) {
        // 如果有预警，导航到预警处理页面
        // 实际项目中应该实现导航到预警处理页面
        setSnackbar({
          open: true,
          message: `正在处理 ${item.title} 的预警信息`,
          severity: originalData.alert_level === 'critical' ? 'error' : 'warning'
        });
      } else {
        // 没有预警，显示正常详情
        setSnackbar({
          open: true,
          message: `查看 ${item.title} 详情`,
          severity: 'info'
        });
      }
    }
  };
  
  // 处理数据导出
  const handleExport = (data: HealthDataTimelineItem[], format: 'csv' | 'pdf' | 'excel') => {
    // 实际项目中这里需要实现导出逻辑
    console.log(`导出数据为 ${format} 格式:`, data);
    
    // 显示提示
    setSnackbar({
      open: true,
      message: `数据已导出为 ${format.toUpperCase()} 格式`,
      severity: 'success'
    });
  };
  
  // 处理数据分享
  const handleShare = (data: HealthDataTimelineItem[]) => {
    // 实际项目中这里需要实现分享逻辑
    console.log('分享数据:', data);
    
    // 显示提示
    setSnackbar({
      open: true,
      message: '分享链接已生成',
      severity: 'success'
    });
  };
  
  // 处理数据过滤变更
  const handleDataFilterChange = (filteredData: HealthDataTimelineItem[]) => {
    console.log('过滤后的数据:', filteredData);
  };
  
  // 切换仅显示预警数据
  const toggleAlertsOnly = () => {
    setShowAlertsOnly(!showAlertsOnly);
    
    if (!showAlertsOnly) {
      // 筛选有预警的数据
      const alertItems = timelineData.filter(item => 
        item.metadata && (item.metadata.alert_level === 'warning' || item.metadata.alert_level === 'critical')
      );
      if (alertItems.length > 0) {
        setTimelineData(alertItems);
      } else {
        setSnackbar({
          open: true,
          message: '没有预警数据',
          severity: 'info'
        });
      }
    } else {
      // 恢复显示所有数据
      const allTimelineItems = convertHealthDataToTimelineItems(healthData);
      setTimelineData(allTimelineItems);
    }
  };
  
  // 关闭提示消息
  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };
  
  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        健康数据时间线
        {alerts.length > 0 && (
          <Badge 
            badgeContent={alerts.length} 
            color="error" 
            sx={{ ml: 2 }}
          >
            <WarningIcon color="error" />
          </Badge>
        )}
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        查看患者健康数据的时间线视图，了解健康指标的变化趋势和关键时间点。实时监测异常数据并提供预警通知。
      </Typography>
      <Divider sx={{ mb: 3 }} />
      
      {/* 操作按钮 */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between' }}>
        <Stack direction="row" spacing={2}>
          <Button 
            variant="outlined" 
            startIcon={<RefreshIcon />}
            onClick={loadHealthData}
            disabled={loading}
          >
            刷新数据
          </Button>
          <Button
            variant={showAlertsOnly ? "contained" : "outlined"}
            color="error"
            startIcon={<WarningIcon />}
            onClick={toggleAlertsOnly}
            disabled={loading || alerts.length === 0}
          >
            {showAlertsOnly ? "显示全部数据" : "仅显示异常数据"}
          </Button>
        </Stack>
        <Stack direction="row" spacing={2}>
          <Button 
            color="primary"
            onClick={() => navigate(`/health-manager/health-data/${patientId}`)}
          >
            查看健康数据管理
          </Button>
        </Stack>
      </Box>
      
      {/* 预警提示 */}
      {alerts.length > 0 && !showAlertsOnly && (
        <Alert 
          severity="warning" 
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small" onClick={toggleAlertsOnly}>
              查看详情
            </Button>
          }
        >
          发现 {alerts.length} 条健康数据异常，请及时查看并处理
        </Alert>
      )}
      
      {/* 时间线组件 */}
      <HealthDataTimeline 
        data={timelineData}
        loading={loading}
        error={error || undefined}
        title={showAlertsOnly ? "健康数据异常时间线" : "健康数据时间线"}
        maxHeight={600}
        onItemClick={handleTimelineItemClick}
        onExport={handleExport}
        onShare={handleShare}
        onDataFilterChange={handleDataFilterChange}
      />
      
      {/* 提示消息 */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={5000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={handleCloseSnackbar}
          severity={snackbar.severity}
          variant="filled"
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default HealthDataTimelinePage; 