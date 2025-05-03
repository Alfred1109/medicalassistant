import React, { useState, useEffect, useCallback } from 'react';
// 导入Material-UI组件
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid';
import Typography from '@mui/material/Typography';
import Divider from '@mui/material/Divider';
import Button from '@mui/material/Button';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select, { SelectChangeEvent } from '@mui/material/Select';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import InputAdornment from '@mui/material/InputAdornment';
import Snackbar from '@mui/material/Snackbar';
import { useTheme } from '@mui/material/styles';
import { alpha } from '@mui/material/styles';

// 导入Material-UI图标
import RefreshIcon from '@mui/icons-material/Refresh';
import SettingsIcon from '@mui/icons-material/Settings';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import DateRangeIcon from '@mui/icons-material/DateRange';
import HeartRateIcon from '@mui/icons-material/MonitorHeart';
import WeightIcon from '@mui/icons-material/Scale';
import ActivityIcon from '@mui/icons-material/DirectionsRun';
import BloodIcon from '@mui/icons-material/BloodtypeOutlined';
import SleepIcon from '@mui/icons-material/Hotel';
import TempIcon from '@mui/icons-material/Thermostat';
import CloseIcon from '@mui/icons-material/Close';
import AddIcon from '@mui/icons-material/Add';
import ColorLensIcon from '@mui/icons-material/ColorLens';
import DeleteIcon from '@mui/icons-material/Delete';
import CancelIcon from '@mui/icons-material/Cancel';

// 导入图表库
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';

// 导入react-beautiful-dnd用于拖拽功能
import { 
  DragDropContext, 
  Droppable, 
  Draggable,
  type DropResult,
  type DroppableProvided,
  type DraggableProvided,
  type DraggableStateSnapshot
} from 'react-beautiful-dnd';

// 导入类型和服务
import { HealthDataType, WidgetSize, TimeRange, WidgetType } from '../../types/health';
import healthDataService from '../../services/healthDataService';
import type { HealthData } from '../../services/healthDataService';

// 自定义组件类型，覆盖原来的WidgetConfig类型
interface WidgetConfig {
  id: string;
  title: string;
  type: WidgetType;
  dataType: HealthDataType;
  dataKey: string;  // 添加必需的dataKey字段
  size: WidgetSize;
  timeRange: TimeRange;
  position: number;
  thresholds?: {
    min: number;
    max: number;
  };
  goal?: number;
  color?: string;
}

// 图表工具提示接口
interface CustomTooltipProps {
  active?: boolean;
  payload?: any[];
  label?: string;
}

// 新增小部件表单接口
interface WidgetFormData {
  title: string;
  type: WidgetType;
  dataType: HealthDataType;
  size: WidgetSize;
  timeRange: TimeRange;
  goal?: number;
  color?: string;
}

// 定义更详细的图表数据类型
interface ChartDataItem {
  time: string;
  date: string;
  value: number | string;
  unit: string;
  systolic?: number;
  diastolic?: number;
}

// 自定义工具提示组件
const CustomTooltip: React.FC<CustomTooltipProps> = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <Paper sx={{ p: 1, backgroundColor: '#fff', boxShadow: 1 }}>
        <Typography variant="body2">{`时间: ${label}`}</Typography>
        <Typography variant="body2" color="primary">
          {`${payload[0].name}: ${payload[0].value} ${payload[0].payload.unit}`}
        </Typography>
      </Paper>
    );
  }
  return null;
};

// 生成随机健康数据
const generateMockHealthData = (): HealthData[] => {
  const now = new Date();
  const data: HealthData[] = [];
  
  // 生成心率数据 (每小时一条)
  for (let i = 0; i < 24; i++) {
    const timestamp = new Date(now);
    timestamp.setHours(now.getHours() - 24 + i);
    
    data.push({
      id: `hr-${i}`,
      type: 'heart_rate',
      value: Math.floor(60 + Math.random() * 40), // 60-100 bpm
      unit: 'bpm',
      timestamp: timestamp.toISOString(),
      deviceId: 'dev-123',
      deviceName: '心率监测手表'
    });
  }
  
  // 生成血压数据 (每4小时一条)
  for (let i = 0; i < 6; i++) {
    const timestamp = new Date(now);
    timestamp.setHours(now.getHours() - 24 + i * 4);
    
    const systolic = Math.floor(110 + Math.random() * 30); // 收缩压 110-140
    const diastolic = Math.floor(60 + Math.random() * 30); // 舒张压 60-90
    
    data.push({
      id: `bp-${i}`,
      type: 'blood_pressure',
      value: `${systolic}/${diastolic}`,
      unit: 'mmHg',
      timestamp: timestamp.toISOString(),
      deviceId: 'dev-456',
      deviceName: '血压监测仪'
    });
  }
  
  // 生成血糖数据 (每天3条)
  for (let i = 0; i < 3; i++) {
    const timestamp = new Date(now);
    timestamp.setHours(8 + i * 6); // 8:00, 14:00, 20:00
    
    data.push({
      id: `bg-${i}`,
      type: 'blood_glucose',
      value: Math.floor(70 + Math.random() * 70), // 70-140 mg/dL
      unit: 'mg/dL',
      timestamp: timestamp.toISOString(),
      deviceId: 'dev-789',
      deviceName: '血糖监测仪'
    });
  }
  
  // 生成体重数据 (每天1条)
  const weightTimestamp = new Date(now);
  weightTimestamp.setHours(7, 0, 0); // 早上7点
  
  data.push({
    id: `wt-1`,
    type: 'weight',
    value: 65 + (Math.random() * 2 - 1), // 64-66kg
    unit: 'kg',
    timestamp: weightTimestamp.toISOString(),
    deviceId: 'dev-321',
    deviceName: '智能体重秤'
  });
  
  // 生成步数数据 (每天1条)
  data.push({
    id: `steps-1`,
    type: 'steps',
    value: Math.floor(5000 + Math.random() * 5000), // 5000-10000步
    unit: '步',
    timestamp: now.toISOString(),
    deviceId: 'dev-123',
    deviceName: '活动追踪器'
  });
  
  // 生成睡眠数据 (每天1条)
  const sleepHours = 6 + Math.random() * 2; // 6-8小时
  data.push({
    id: `sleep-1`,
    type: 'sleep',
    value: sleepHours,
    unit: '小时',
    timestamp: weightTimestamp.toISOString(),
    deviceId: 'dev-123',
    deviceName: '睡眠监测器'
  });
  
  // 生成体温数据 (每12小时1条)
  for (let i = 0; i < 2; i++) {
    const timestamp = new Date(now);
    timestamp.setHours(8 + i * 12); // 8:00, 20:00
    
    data.push({
      id: `temp-${i}`,
      type: 'temperature',
      value: 36.4 + Math.random() * 1, // 36.4-37.4°C
      unit: '°C',
      timestamp: timestamp.toISOString(),
      deviceId: 'dev-234',
      deviceName: '体温计'
    });
  }
  
  return data;
};

// 获取默认小部件配置
const getDefaultWidgets = (): WidgetConfig[] => {
  return [
    {
      id: 'widget-1',
      title: '心率趋势',
      type: 'line',
      dataType: 'heart_rate',
      dataKey: 'heart_rate',
      size: 'medium',
      timeRange: 'day',
      position: 0,
      thresholds: { min: 60, max: 100 },
      color: '#FF5252'
    },
    {
      id: 'widget-2',
      title: '血压记录',
      type: 'bar',
      dataType: 'blood_pressure',
      dataKey: 'blood_pressure',
      size: 'medium',
      timeRange: 'week',
      position: 1,
      color: '#536DFE'
    },
    {
      id: 'widget-3',
      title: '血糖监测',
      type: 'line',
      dataType: 'blood_glucose',
      dataKey: 'blood_glucose',
      size: 'small',
      timeRange: 'week',
      position: 2,
      thresholds: { min: 70, max: 140 },
      color: '#FFA726'
    },
    {
      id: 'widget-4',
      title: '体重记录',
      type: 'line',
      dataType: 'weight',
      dataKey: 'weight',
      size: 'small',
      timeRange: 'month',
      position: 3,
      color: '#66BB6A'
    },
    {
      id: 'widget-5',
      title: '每日步数',
      type: 'goal',
      dataType: 'steps',
      dataKey: 'steps',
      size: 'small',
      timeRange: 'day',
      position: 4,
      goal: 8000,
      color: '#8D6E63'
    },
    {
      id: 'widget-6',
      title: '睡眠时长',
      type: 'stat',
      dataType: 'sleep',
      dataKey: 'sleep',
      size: 'small',
      timeRange: 'day',
      position: 5,
      goal: 8,
      color: '#4527A0'
    }
  ];
};

// 格式化数据以供图表使用
const formatDataForChart = (data: HealthData[], dataType: HealthDataType): ChartDataItem[] => {
  // 根据数据类型进行不同的处理
  const filteredData = data.filter(item => item.type === dataType);
  
  // 按时间排序
  const sortedData = filteredData.sort((a, b) => 
    new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );
  
  // 转换为图表所需格式
  return sortedData.map(item => {
    const date = new Date(item.timestamp);
    const result: ChartDataItem = {
      time: date.toLocaleTimeString(),
      date: date.toLocaleDateString(),
      value: item.value,
      unit: item.unit
    };
    
    // 血压数据特殊处理
    if (dataType === 'blood_pressure') {
      const parts = typeof item.value === 'string' ? item.value.split('/') : [];
      if (parts.length === 2) {
        result.systolic = parseInt(parts[0]);
        result.diastolic = parseInt(parts[1]);
      }
    }
    
    return result;
  });
};

// 获取最新值
const getLatestValue = (data: HealthData[], dataType: HealthDataType) => {
  const filteredData = data.filter(item => item.type === dataType);
  
  if (filteredData.length === 0) return null;
  
  // 按时间排序并获取最新的
  return filteredData.sort((a, b) => 
    new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  )[0];
};

// 辅助函数：获取数据图标
const getDataTypeIcon = (type: HealthData['type']) => {
  switch (type) {
    case 'heart_rate':
      return <HeartRateIcon />;
    case 'blood_pressure':
      return <BloodIcon />;
    case 'blood_glucose':
      return <BloodIcon />;
    case 'weight':
      return <WeightIcon />;
    case 'steps':
      return <ActivityIcon />;
    case 'sleep':
      return <SleepIcon />;
    case 'temperature':
      return <TempIcon />;
    default:
      return <FitnessCenterIcon />;
  }
};

// 主组件
const PersonalizedDashboard: React.FC = () => {
  const theme = useTheme();
  
  // 状态管理
  const [loading, setLoading] = React.useState<boolean>(true);
  const [healthData, setHealthData] = React.useState<HealthData[]>([]);
  const [widgets, setWidgets] = React.useState<WidgetConfig[]>([]);
  const [editMode, setEditMode] = React.useState<boolean>(false);
  const [dateRange, setDateRange] = React.useState<'day' | 'week' | 'month'>('week');
  const [menuAnchorEl, setMenuAnchorEl] = React.useState<null | HTMLElement>(null);
  const [selectedWidget, setSelectedWidget] = React.useState<string | null>(null);
  
  // 新增状态
  const [openWidgetDialog, setOpenWidgetDialog] = React.useState<boolean>(false);
  const [widgetFormData, setWidgetFormData] = React.useState<WidgetFormData>({
    title: '',
    type: 'line',
    dataType: 'heart_rate',
    size: 'small',
    timeRange: 'day',
    color: '#8884d8'
  });
  const [snackbarOpen, setSnackbarOpen] = React.useState<boolean>(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState<string>('');
  const [editingWidgetId, setEditingWidgetId] = React.useState<string | null>(null);
  const [patientId, setPatientId] = React.useState<string>('current'); // 'current' 指当前登录的患者

  // 获取实际数据
  React.useEffect(() => {
    fetchRealData();
  }, [dateRange, patientId]);

  // 从API获取真实数据
  const fetchRealData = async () => {
    setLoading(true);
    try {
      // 先尝试从API获取数据
      let response;
      const params = { 
        timeRange: dateRange,
        // 可以添加其他过滤参数
      };
      
      if (patientId === 'current') {
        // 获取当前登录用户的健康数据
        response = await healthDataService.getUserHealthData('me', params.timeRange);
      } else {
        // 获取特定患者的健康数据
        response = await healthDataService.getUserHealthData(patientId, params.timeRange);
      }
      
      // 检查响应数据
      if (response && response.length > 0) {
        setHealthData(response);
      } else {
        // 如果没有数据，使用模拟数据
        console.log('未找到真实健康数据，使用模拟数据');
        setHealthData(generateMockHealthData());
      }

      // 获取用户仪表盘配置
      await fetchDashboardConfig();
    } catch (error) {
      console.error('获取健康数据失败:', error);
      // 出错时使用模拟数据
      setHealthData(generateMockHealthData());
      
      // 如果没有小部件配置，使用默认配置
      if (widgets.length === 0) {
        setWidgets(getDefaultWidgets());
      }
      
      setSnackbarMessage('获取健康数据失败，已加载模拟数据');
      setSnackbarOpen(true);
    } finally {
      setLoading(false);
    }
  };

  // 模拟获取数据的函数（作为备份）
  const fetchData = async () => {
    setLoading(true);
    
    // 模拟API调用延迟
    setTimeout(() => {
      // 生成模拟数据
      setHealthData(generateMockHealthData());
      
      // 模拟仪表盘配置
      if (widgets.length === 0) {
        setWidgets(getDefaultWidgets());
      }
      
      setLoading(false);
    }, 1500);
  };

  // 处理菜单打开
  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, widgetId: string) => {
    setMenuAnchorEl(event.currentTarget);
    setSelectedWidget(widgetId);
  };

  // 处理菜单关闭
  const handleMenuClose = () => {
    setMenuAnchorEl(null);
    setSelectedWidget(null);
  };

  // 切换编辑模式
  const toggleEditMode = async () => {
    if (editMode) {
      // 如果当前处于编辑模式，退出时保存配置
      try {
        await saveDashboardConfig();
        setSnackbarMessage('仪表盘配置已保存');
        setSnackbarOpen(true);
      } catch (error) {
        console.error('保存仪表盘配置失败:', error);
        setSnackbarMessage('保存仪表盘配置失败');
        setSnackbarOpen(true);
      }
    }
    setEditMode(!editMode);
  };

  // 保存仪表盘配置到后端
  const saveDashboardConfig = async () => {
    try {
      await healthDataService.saveUserDashboardConfig(
        patientId === 'current' ? 'me' : patientId, 
        widgets
      );
      return true;
    } catch (error) {
      console.error('保存配置失败:', error);
      throw error;
    }
  };

  // 删除小部件
  const handleDeleteWidget = () => {
    if (selectedWidget) {
      setWidgets(widgets.filter((widget: WidgetConfig) => widget.id !== selectedWidget));
      handleMenuClose();
    }
  };

  // 编辑小部件
  const handleEditWidget = () => {
    if (selectedWidget) {
      const widget = widgets.find(w => w.id === selectedWidget);
      if (widget) {
        setWidgetFormData({
          title: widget.title,
          type: widget.type,
          dataType: widget.dataType,
          size: widget.size,
          timeRange: widget.timeRange,
          goal: widget.goal,
          color: widget.color
        });
        setEditingWidgetId(widget.id);
        setOpenWidgetDialog(true);
      }
      handleMenuClose();
    }
  };

  // 添加新小部件
  const handleAddWidget = () => {
    setWidgetFormData({
      title: '',
      type: 'line',
      dataType: 'heart_rate',
      size: 'medium',
      timeRange: 'day',
      color: '#2196f3'
    });
    setOpenWidgetDialog(true);
  };

  // 处理小部件表单变更
  const handleWidgetFormChange = (field: keyof WidgetFormData, value: any) => {
    setWidgetFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  // 保存小部件
  const handleSaveWidget = () => {
    if (editingWidgetId) {
      // 编辑现有小部件
      setWidgets(prev => 
        prev.map(w => w.id === editingWidgetId ? {
          ...w,
          title: widgetFormData.title,
          type: widgetFormData.type,
          dataType: widgetFormData.dataType,
          dataKey: widgetFormData.dataType, // 使用数据类型作为dataKey
          size: widgetFormData.size,
          timeRange: widgetFormData.timeRange,
          goal: widgetFormData.goal,
          color: widgetFormData.color
        } : w)
      );
    } else {
      // 添加新小部件
      const newWidget: WidgetConfig = {
        id: `widget-${Date.now()}`,
        title: widgetFormData.title,
        type: widgetFormData.type,
        dataType: widgetFormData.dataType,
        dataKey: widgetFormData.dataType, // 使用数据类型作为dataKey
        size: widgetFormData.size,
        timeRange: widgetFormData.timeRange,
        position: widgets.length + 1,
        ...(widgetFormData.goal && { goal: widgetFormData.goal }),
        ...(widgetFormData.color && { color: widgetFormData.color })
      };
      
      setWidgets(prev => [...prev, newWidget]);
    }
    
    setOpenWidgetDialog(false);
    setEditingWidgetId(null);
  };

  // 根据小部件大小返回Grid尺寸
  const getGridSize = (size: WidgetSize) => {
    switch (size) {
      case 'small':
        return { xs: 12, sm: 6, md: 4 };
      case 'medium':
        return { xs: 12, sm: 12, md: 6 };
      case 'large':
        return { xs: 12, sm: 12, md: 12 };
      default:
        return { xs: 12, sm: 6, md: 4 };
    }
  };

  // 处理拖拽结束
  const handleDragEnd = (result: DropResult) => {
    if (!result.destination) return;
    
    const items = Array.from(widgets);
    const [reorderedItem] = items.splice(result.source.index, 1);
    items.splice(result.destination.index, 0, reorderedItem);
    
    // 更新位置顺序
    const updatedWidgets = items.map((item, index) => ({
      ...item,
      position: index
    }));
    
    setWidgets(updatedWidgets);
  };

  // 渲染小部件内容
  const renderWidgetContent = (widget: WidgetConfig, healthData: HealthData[]) => {
    const chartData = formatDataForChart(healthData, widget.dataType);
    
    switch (widget.type) {
      case 'line':
        return (
          <Box sx={{ height: 200, width: '100%' }}>
            <ResponsiveContainer>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis />
                <RechartsTooltip content={<CustomTooltip />} />
                <Legend />
                <Line 
                  type="monotone" 
                  dataKey="value" 
                  stroke={widget.color || '#8884d8'} 
                  activeDot={{ r: 8 }} 
                />
                {widget.dataType === 'blood_pressure' && (
                  <>
                    <Line type="monotone" dataKey="systolic" stroke="#82ca9d" />
                    <Line type="monotone" dataKey="diastolic" stroke="#ffc658" />
                  </>
                )}
              </LineChart>
            </ResponsiveContainer>
          </Box>
        );
      
      case 'bar':
        return (
          <Box sx={{ height: 200, width: '100%' }}>
            <ResponsiveContainer>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis />
                <RechartsTooltip content={<CustomTooltip />} />
                <Legend />
                <Bar 
                  dataKey="value" 
                  fill={widget.color || '#8884d8'} 
                />
                {widget.dataType === 'blood_pressure' && (
                  <>
                    <Bar dataKey="systolic" fill="#82ca9d" />
                    <Bar dataKey="diastolic" fill="#ffc658" />
                  </>
                )}
              </BarChart>
            </ResponsiveContainer>
          </Box>
        );
      
      case 'stat':
        const latestData = getLatestValue(healthData, widget.dataType);
        return (
          <Card 
            sx={{ 
              height: '100%', 
              boxShadow: 'none', 
              border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`
            }}
          >
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Box 
                  sx={{ 
                    bgcolor: widget.color || theme.palette.primary.main, 
                    color: '#fff',
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mr: 2
                  }}
                >
                  {getDataTypeIcon(widget.dataType)}
                </Box>
                <Typography variant="h6">{widget.title}</Typography>
              </Box>
              <Box sx={{ textAlign: 'center', py: 2 }}>
                <Typography variant="h3" component="div" sx={{ mb: 1 }}>
                  {latestData?.value || '暂无数据'} {latestData?.unit || ''}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {latestData?.timestamp ? `最后更新: ${new Date(latestData.timestamp).toLocaleString()}` : '暂无数据'}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        );
      
      case 'goal':
        const latestGoalData = getLatestValue(healthData, widget.dataType);
        const currentValue = latestGoalData && typeof latestGoalData.value === 'number' ? latestGoalData.value : 0;
        const goalValue = widget.goal || 100;
        const progress = Math.min(100, (currentValue / goalValue) * 100);
        
        return (
          <Card 
            sx={{ 
              height: '100%', 
              boxShadow: 'none', 
              border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`
            }}
          >
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Box 
                  sx={{ 
                    bgcolor: widget.color || theme.palette.primary.main, 
                    color: '#fff',
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mr: 2
                  }}
                >
                  {getDataTypeIcon(widget.dataType)}
                </Box>
                <Typography variant="h6">{widget.title}</Typography>
              </Box>
              <Box sx={{ textAlign: 'center', position: 'relative' }}>
                <CircularProgress
                  variant="determinate"
                  value={progress}
                  size={120}
                  thickness={4}
                  sx={{ color: widget.color || theme.palette.primary.main }}
                />
                <Box
                  sx={{
                    position: 'absolute',
                    top: '50%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                  }}
                >
                  <Typography variant="h4" component="div">
                    {Math.round(progress)}%
                  </Typography>
                </Box>
                <Typography variant="h6" component="div" sx={{ mt: 2 }}>
                  {currentValue} / {goalValue} {latestGoalData?.unit || ''}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        );
      
      default:
        return (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body1">不支持的小部件类型</Typography>
          </Box>
        );
    }
  };

  // 更新配置响应处理逻辑
  const fetchDashboardConfig = async () => {
    try {
      if (patientId) {
        // 获取用户仪表盘配置
        const configResponse = await healthDataService.getUserDashboardConfig(patientId === 'current' ? 'me' : patientId);
        if (configResponse && Array.isArray(configResponse)) {
          setWidgets(configResponse);
        } else {
          // 如果没有配置或格式不正确，使用默认配置
          setWidgets(getDefaultWidgets());
        }
      }
    } catch (error) {
      console.error('获取仪表盘配置失败:', error);
      // 出错时使用默认配置
      setWidgets(getDefaultWidgets());
    }
  };

  // 渲染主界面骨架
  return (
    <Box sx={{ width: '100%' }}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 2
        }}
      >
        <Typography variant="h5" component="h1">
          个性化健康数据仪表盘
        </Typography>
        <Box>
          {editMode && (
            <Button
              variant="outlined"
              startIcon={<AddIcon />}
              onClick={handleAddWidget}
              sx={{ mr: 1 }}
            >
              添加小部件
            </Button>
          )}
          <Button
            variant="outlined"
            startIcon={editMode ? <SaveIcon /> : <EditIcon />}
            onClick={toggleEditMode}
            sx={{ mr: 1 }}
          >
            {editMode ? '保存布局' : '编辑仪表盘'}
          </Button>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchRealData}
          >
            刷新数据
          </Button>
        </Box>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* 日期范围选择 */}
      <Box sx={{ mb: 2 }}>
        <Tabs
          value={dateRange}
          onChange={(_, newValue: 'day' | 'week' | 'month') => setDateRange(newValue)}
          indicatorColor="primary"
          textColor="primary"
        >
          <Tab value="day" label="今日" />
          <Tab value="week" label="本周" />
          <Tab value="month" label="本月" />
        </Tabs>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
          <CircularProgress />
          <Typography variant="body1" sx={{ ml: 2 }}>
            加载健康数据中...
          </Typography>
        </Box>
      ) : (
        <DragDropContext onDragEnd={handleDragEnd}>
          <Droppable droppableId="widgets" direction="horizontal">
            {(provided: DroppableProvided) => (
              <Grid 
                container 
                spacing={2}
                {...provided.droppableProps}
                ref={provided.innerRef}
              >
                {widgets.length > 0 ? (
                  widgets
                    .sort((a: WidgetConfig, b: WidgetConfig) => a.position - b.position)
                    .map((widget: WidgetConfig, index: number) => (
                      <Draggable 
                        key={widget.id} 
                        draggableId={widget.id} 
                        index={index}
                        isDragDisabled={!editMode}
                      >
                        {(provided: DraggableProvided, snapshot: DraggableStateSnapshot) => (
                          <Grid 
                            item 
                            {...getGridSize(widget.size)}
                            ref={provided.innerRef}
                            {...provided.draggableProps}
                            {...provided.dragHandleProps}
                            sx={{ 
                              transition: 'transform 0.2s',
                              transform: snapshot.isDragging ? 'scale(1.02)' : 'scale(1)'
                            }}
                          >
                            <Card 
                              sx={{ 
                                height: '100%',
                                transition: 'all 0.3s',
                                ...(editMode && { 
                                  cursor: 'move',
                                  '&:hover': { boxShadow: 6 } 
                                })
                              }}
                            >
                              <CardHeader
                                title={
                                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                                    {getDataTypeIcon(widget.dataType)}
                                    <Typography variant="h6" sx={{ ml: 1 }}>
                                      {widget.title}
                                    </Typography>
                                  </Box>
                                }
                                action={
                                  <IconButton 
                                    aria-label="settings" 
                                    onClick={(e: React.MouseEvent<HTMLElement>) => handleMenuOpen(e, widget.id)}
                                  >
                                    <MoreVertIcon />
                                  </IconButton>
                                }
                              />
                              <Divider />
                              <CardContent>
                                {renderWidgetContent(widget, healthData)}
                              </CardContent>
                            </Card>
                          </Grid>
                        )}
                      </Draggable>
                    ))
                ) : (
                  <Grid item xs={12}>
                    <Alert severity="info">
                      未找到小部件配置，请添加健康数据卡片。
                    </Alert>
                  </Grid>
                )}
                {provided.placeholder}
              </Grid>
            )}
          </Droppable>
        </DragDropContext>
      )}

      {/* 小部件菜单 */}
      <Menu
        anchorEl={menuAnchorEl}
        open={Boolean(menuAnchorEl)}
        onClose={handleMenuClose}
      >
        <MenuItem onClick={handleEditWidget}>
          <SettingsIcon fontSize="small" sx={{ mr: 1 }} />
          编辑小部件
        </MenuItem>
        <MenuItem onClick={handleDeleteWidget}>
          <CloseIcon fontSize="small" sx={{ mr: 1 }} />
          删除小部件
        </MenuItem>
      </Menu>

      {/* 添加/编辑小部件对话框 */}
      <Dialog open={openWidgetDialog} onClose={() => setOpenWidgetDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingWidgetId ? '编辑小部件' : '添加新小部件'}
        </DialogTitle>
        <DialogContent>
          <Box component="form" sx={{ mt: 1 }}>
            <TextField
              fullWidth
              margin="normal"
              label="小部件标题"
              value={widgetFormData.title}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleWidgetFormChange('title', e.target.value)}
            />
            
            <FormControl fullWidth margin="normal">
              <InputLabel>小部件类型</InputLabel>
              <Select
                value={widgetFormData.type}
                onChange={(e: SelectChangeEvent) => handleWidgetFormChange('type', e.target.value as WidgetType)}
                label="小部件类型"
              >
                <MenuItem value="line">折线图</MenuItem>
                <MenuItem value="bar">柱状图</MenuItem>
                <MenuItem value="stat">数值统计</MenuItem>
                <MenuItem value="goal">目标进度</MenuItem>
              </Select>
            </FormControl>
            
            <FormControl fullWidth margin="normal">
              <InputLabel>数据类型</InputLabel>
              <Select
                value={widgetFormData.dataType}
                onChange={(e: SelectChangeEvent) => handleWidgetFormChange('dataType', e.target.value as HealthDataType)}
                label="数据类型"
              >
                <MenuItem value="heart_rate">心率</MenuItem>
                <MenuItem value="blood_pressure">血压</MenuItem>
                <MenuItem value="blood_glucose">血糖</MenuItem>
                <MenuItem value="weight">体重</MenuItem>
                <MenuItem value="steps">步数</MenuItem>
                <MenuItem value="sleep">睡眠</MenuItem>
                <MenuItem value="temperature">体温</MenuItem>
              </Select>
            </FormControl>
            
            <FormControl fullWidth margin="normal">
              <InputLabel>小部件大小</InputLabel>
              <Select
                value={widgetFormData.size}
                onChange={(e: SelectChangeEvent) => handleWidgetFormChange('size', e.target.value as WidgetSize)}
                label="小部件大小"
              >
                <MenuItem value="small">小</MenuItem>
                <MenuItem value="medium">中</MenuItem>
                <MenuItem value="large">大</MenuItem>
              </Select>
            </FormControl>
            
            <FormControl fullWidth margin="normal">
              <InputLabel>时间范围</InputLabel>
              <Select
                value={widgetFormData.timeRange}
                onChange={(e: SelectChangeEvent) => handleWidgetFormChange('timeRange', e.target.value as TimeRange)}
                label="时间范围"
              >
                <MenuItem value="day">天</MenuItem>
                <MenuItem value="week">周</MenuItem>
                <MenuItem value="month">月</MenuItem>
                <MenuItem value="year">年</MenuItem>
              </Select>
            </FormControl>
            
            {widgetFormData.type === 'goal' && (
              <TextField
                fullWidth
                margin="normal"
                label="目标值"
                type="number"
                value={widgetFormData.goal || ''}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleWidgetFormChange('goal', Number(e.target.value))}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      {widgetFormData.dataType === 'steps' ? '步' : 
                        widgetFormData.dataType === 'heart_rate' ? 'bpm' : 
                        widgetFormData.dataType === 'weight' ? 'kg' : ''}
                    </InputAdornment>
                  ),
                }}
              />
            )}
            
            <TextField
              fullWidth
              margin="normal"
              label="颜色"
              value={widgetFormData.color || '#8884d8'}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleWidgetFormChange('color', e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <ColorLensIcon sx={{ color: widgetFormData.color || '#8884d8' }} />
                  </InputAdornment>
                ),
              }}
              placeholder="#RRGGBB"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenWidgetDialog(false)}>取消</Button>
          <Button onClick={handleSaveWidget} color="primary" variant="contained">
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 通知消息 */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={() => setSnackbarOpen(false)}
        message={snackbarMessage}
        action={
          <IconButton
            size="small"
            color="inherit"
            onClick={() => setSnackbarOpen(false)}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        }
      />
    </Box>
  );
};

export default PersonalizedDashboard; 