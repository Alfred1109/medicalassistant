import React, { useState, useEffect } from 'react';
import type { FC } from 'react';
import type { MouseEvent } from 'react';
import {
  Box,
  Typography,
  Paper,
  Divider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  CircularProgress,
  Alert,
  Button,
  Chip,
  Stack
} from '@mui/material';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import ToggleButton from '@mui/material/ToggleButton';
import { SelectChangeEvent } from '@mui/material/Select';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell, 
  BarChart, Bar, Legend 
} from 'recharts';
import { format, parseISO, subDays, addDays, eachDayOfInterval } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { Line as ChartJSLine } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip as ChartJSTooltip,
  Legend as ChartJSLegend,
  ChartOptions
} from 'chart.js';

// 注册Chart.js组件
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  ChartJSTooltip,
  ChartJSLegend
);

// 数据类型定义
interface HealthDataPoint {
  id: string;
  data_type: string;
  data: any;
  recorded_at: string;
  source?: string;
}

// 处理后的数据点类型
interface ProcessedDataPoint {
  date: string;
  value: number;
  unit?: string;
  formattedDate?: string;
  [key: string]: any;
}

interface HealthDataVisualizationProps {
  data: HealthDataPoint[];
  dataType?: string;
  title?: string;
  loading?: boolean;
  error?: string;
  height?: number;
  onTimeRangeChange?: (range: string) => void;
}

// 时间范围选项
const timeRangeOptions = [
  { value: 7, label: '最近7天' },
  { value: 14, label: '最近14天' },
  { value: 30, label: '最近30天' },
  { value: 90, label: '最近3个月' }
];

// 图表类型选项
const chartTypeOptions: { value: string; label: string }[] = [
  { value: 'blood_pressure', label: '血压' },
  { value: 'blood_glucose', label: '血糖' },
  { value: 'heart_rate', label: '心率' },
  { value: 'body_temperature', label: '体温' },
  { value: 'respiratory_rate', label: '呼吸频率' },
  { value: 'weight', label: '体重' },
  { value: 'oxygen_saturation', label: '血氧' },
  { value: 'step_count', label: '步数' }
];

// 颜色配置
const CHART_COLORS = [
  '#2196F3', '#FF9800', '#4CAF50', '#F44336',
  '#9C27B0', '#3F51B5', '#00BCD4', '#FFEB3B'
];

// 数据单位映射
const DATA_UNITS: {[key: string]: string} = {
  blood_pressure: 'mmHg',
  blood_glucose: 'mmol/L',
  heart_rate: 'bpm',
  body_temperature: '°C',
  respiratory_rate: '次/分',
  weight: 'kg',
  height: 'cm',
  bmi: '',
  oxygen_saturation: '%',
  step_count: '步'
};

const HealthDataVisualization: FC<HealthDataVisualizationProps> = ({
  data,
  dataType = 'vital_sign',
  title = '健康数据趋势',
  loading = false,
  error,
  height = 400,
  onTimeRangeChange
}) => {
  // 状态
  const [timeRange, setTimeRange] = useState<number>(14);
  const [chartType, setChartType] = useState<string>('line');
  const [processedData, setProcessedData] = useState<ProcessedDataPoint[]>([]);
  const [selectedDataTypes, setSelectedDataTypes] = useState<string[]>([]);
  const [availableDataTypes, setAvailableDataTypes] = useState<{ type: string, label: string, unit?: string }[]>([]);
  const [viewMode, setViewMode] = useState<'line' | 'table'>('line');
  
  // 处理时间范围变更
  const handleTimeRangeChange = (event: SelectChangeEvent) => {
    const value = event.target.value;
    setTimeRange(Number(value));
    if (onTimeRangeChange) {
      onTimeRangeChange(value as string);
    }
  };
  
  // 处理图表类型变更
  const handleChartTypeChange = (event: SelectChangeEvent) => {
    const value = event.target.value;
    setChartType(value as string);
  };
  
  // 处理视图模式变更
  const handleViewModeChange = (
    event: MouseEvent<HTMLElement>,
    newMode: 'line' | 'table',
  ) => {
    if (newMode !== null) {
      setViewMode(newMode);
    }
  };
  
  // 处理数据类型选择
  const handleDataTypeToggle = (type: string) => {
    setSelectedDataTypes((prev: string[]) => {
      if (prev.includes(type)) {
        return prev.filter((t: string) => t !== type);
      } else {
        return [...prev, type];
      }
    });
  };
  
  // 根据数据类型获取名称
  const getDataTypeLabel = (type: string) => {
    const dataTypeMapping: { [key: string]: string } = {
      blood_pressure: '血压',
      heart_rate: '心率',
      body_temperature: '体温',
      respiratory_rate: '呼吸频率',
      oxygen_saturation: '血氧饱和度',
      blood_glucose: '血糖',
      weight: '体重',
      height: '身高',
      bmi: 'BMI',
      step_count: '步数'
    };
    return dataTypeMapping[type] || type;
  };
  
  // 根据时间范围获取起始日期
  const getStartDate = (days: number): Date => {
    const today = new Date();
    return subDays(today, days - 1);
  };
  
  // 格式化日期
  const formatDate = (dateString: string, formatStr: string = 'MM-dd') => {
    try {
      return format(parseISO(dateString), formatStr, { locale: zhCN });
    } catch (err) {
      return dateString;
    }
  };
  
  // 处理数据，转换为图表所需格式
  useEffect(() => {
    if (!data || data.length === 0) {
      setProcessedData([]);
      setSelectedDataTypes([]);
      setAvailableDataTypes([]);
      return;
    }
    
    // 筛选选定数据类型的数据
    const filteredData = data.filter(item => item.data_type === dataType);
    
    // 获取所有可用的数据类型
    const types = [...new Set(filteredData.map(item => {
      if (dataType === 'vital_sign') {
        return item.data.vital_type;
      } else if (dataType === 'lab_result') {
        return item.data.test_name;
      }
      return item.data_type;
    }))];
    
    const typeObjects = types.map((type: any) => ({
      type: String(type),
      label: getDataTypeLabel(String(type)),
      unit: DATA_UNITS[String(type)] || ''
    }));
    
    setAvailableDataTypes(typeObjects);
    
    // 如果未选择类型，默认选择第一个
    if (selectedDataTypes.length === 0 && typeObjects.length > 0) {
      setSelectedDataTypes([typeObjects[0].type]);
    }
    
    // 基于时间范围筛选和处理数据
    const startDate = getStartDate(timeRange);
    const endDate = new Date();
    
    // 为每个数据类型创建连续日期序列
    const dateRange = eachDayOfInterval({ start: startDate, end: endDate });
    const dateMap: { [key: string]: { [key: string]: any } } = {};
    
    // 初始化日期映射
    dateRange.forEach(date => {
      const dateStr = format(date, 'yyyy-MM-dd');
      dateMap[dateStr] = {
        date: dateStr,
        formattedDate: format(date, 'MM/dd', { locale: zhCN })
      };
      // 初始化所有数据类型字段
      types.forEach(type => {
        dateMap[dateStr][type] = null;
      });
    });
    
    // 填充数据
    filteredData.forEach(item => {
      try {
        const itemDate = format(parseISO(item.recorded_at), 'yyyy-MM-dd');
        
        if (parseISO(itemDate) < startDate || parseISO(itemDate) > endDate) {
          return;
        }
        
        const itemType = dataType === 'vital_sign' 
          ? item.data.vital_type 
          : dataType === 'lab_result' 
            ? item.data.test_name 
            : item.data_type;
            
        if (!itemType || !dateMap[itemDate]) {
          return;
        }
            
        let value: number | null = null;
        
        if (dataType === 'vital_sign') {
          if (itemType === 'blood_pressure') {
            // 血压特殊处理，存储收缩压和舒张压
            if (item.data.value && typeof item.data.value === 'object') {
              dateMap[itemDate]['systolic'] = item.data.value.systolic;
              dateMap[itemDate]['diastolic'] = item.data.value.diastolic;
              // 平均动脉压 MAP = (SBP + 2*DBP) / 3
              const systolic = item.data.value.systolic || 0;
              const diastolic = item.data.value.diastolic || 0;
              value = (systolic + 2 * diastolic) / 3;
            }
          } else {
            // 其他生命体征直接使用值
            value = typeof item.data.value === 'number' 
              ? item.data.value 
              : parseFloat(item.data.value);
          }
        } else if (dataType === 'lab_result') {
          value = typeof item.data.value === 'number' 
            ? item.data.value 
            : parseFloat(item.data.value);
        } else {
          value = typeof item.data.value === 'number' 
            ? item.data.value 
            : parseFloat(item.data.value);
        }
        
        if (value !== null && !isNaN(value)) {
          dateMap[itemDate][itemType] = value;
        }
      } catch (err) {
        console.error('处理数据项时出错:', err, item);
      }
    });
    
    // 转换为数组
    const processed = Object.values(dateMap);
    setProcessedData(processed);
    
  }, [data, dataType, timeRange, selectedDataTypes]);
  
  // 自定义工具提示组件
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || payload.length === 0) {
      return null;
    }
    
    return (
      <Paper elevation={3} sx={{ p: 1.5, backgroundColor: 'rgba(255, 255, 255, 0.9)' }}>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {label}
        </Typography>
        {payload.map((entry: any, index: number) => {
          const dataType = entry.dataKey;
          const unit = availableDataTypes.find(t => t.type === dataType)?.unit || '';
          return (
            <Typography 
              key={`tooltip-${index}`} 
              variant="body2" 
              sx={{ color: entry.color || CHART_COLORS[index % CHART_COLORS.length] }}
            >
              {getDataTypeLabel(dataType)}: {entry.value !== null ? entry.value : '无数据'} {unit}
            </Typography>
          );
        })}
      </Paper>
    );
  };
  
  // 渲染柱状图
  const renderBarChart = () => {
    if (processedData.length === 0 || selectedDataTypes.length === 0) {
      return (
        <Box display="flex" justifyContent="center" alignItems="center" height={height * 0.8}>
          <Typography color="text.secondary">
            暂无数据可显示
          </Typography>
        </Box>
      );
    }
    
    return (
      <ResponsiveContainer width="100%" height={height * 0.8}>
        <BarChart data={processedData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="formattedDate" />
          <YAxis />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          {selectedDataTypes.map((type: string, index: number) => (
            <Bar 
              key={type} 
              dataKey={type} 
              name={getDataTypeLabel(type)} 
              fill={CHART_COLORS[index % CHART_COLORS.length]} 
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  };
  
  // 渲染折线图
  const renderLineChart = () => {
    if (processedData.length === 0 || selectedDataTypes.length === 0) {
      return (
        <Box display="flex" justifyContent="center" alignItems="center" height={height * 0.8}>
          <Typography color="text.secondary">
            暂无数据可显示
          </Typography>
        </Box>
      );
    }
    
    return (
      <ResponsiveContainer width="100%" height={height * 0.8}>
        <LineChart data={processedData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="formattedDate" />
          <YAxis />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          {selectedDataTypes.map((type: string, index: number) => (
            <Line 
              key={type} 
              type="monotone" 
              dataKey={type} 
              name={getDataTypeLabel(type)}
              stroke={CHART_COLORS[index % CHART_COLORS.length]} 
              dot={{ r: 4 }} 
              activeDot={{ r: 8 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  };
  
  // 渲染表格
  const renderTable = () => {
    if (processedData.length === 0 || selectedDataTypes.length === 0) {
      return (
        <Box display="flex" justifyContent="center" alignItems="center" height={height * 0.8}>
          <Typography color="text.secondary">
            暂无数据可显示
          </Typography>
        </Box>
      );
    }
    
    return (
      <Box sx={{ maxHeight: height * 0.8, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'center' }}>
          <thead>
            <tr style={{ backgroundColor: '#f5f5f5' }}>
              <th style={{ padding: '8px', border: '1px solid #ddd' }}>日期</th>
              {selectedDataTypes.map(type => (
                <th key={type} style={{ padding: '8px', border: '1px solid #ddd' }}>
                  {getDataTypeLabel(type)} ({availableDataTypes.find(t => t.type === type)?.unit || ''})
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {processedData.map((item, index) => (
              <tr key={index} style={{ backgroundColor: index % 2 === 0 ? 'white' : '#f9f9f9' }}>
                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{item.formattedDate}</td>
                {selectedDataTypes.map(type => (
                  <td key={`${index}-${type}`} style={{ padding: '8px', border: '1px solid #ddd' }}>
                    {item[type] !== null ? item[type] : '-'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
    );
  };
  
  // 渲染图表
  const renderChart = () => {
    if (processedData.length === 0) {
      return (
        <Box display="flex" justifyContent="center" alignItems="center" height={height * 0.8}>
          <Typography color="text.secondary">
            暂无数据可显示
          </Typography>
        </Box>
      );
    }
    
    if (viewMode === 'table') {
      return renderTable();
    }
    
    switch (chartType) {
      case 'bar':
        return renderBarChart();
      case 'line':
      default:
        return renderLineChart();
    }
  };
  
  return (
    <Paper elevation={1} sx={{ p: 3 }}>
      <Box>
        <Typography variant="h6" gutterBottom>{title}</Typography>
        <Divider sx={{ mb: 2 }} />
        
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel id="time-range-label">时间范围</InputLabel>
              <Select
                labelId="time-range-label"
                value={timeRange}
                label="时间范围"
                onChange={handleTimeRangeChange}
              >
                {timeRangeOptions.map(option => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel id="chart-type-label">图表类型</InputLabel>
              <Select
                labelId="chart-type-label"
                value={chartType}
                label="图表类型"
                onChange={handleChartTypeChange}
              >
                <MenuItem value="line">折线图</MenuItem>
                <MenuItem value="bar">柱状图</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <ToggleButtonGroup
              value={viewMode}
              exclusive
              onChange={handleViewModeChange}
              size="small"
              fullWidth
            >
              <ToggleButton value="line" aria-label="图表">
                图表
              </ToggleButton>
              <ToggleButton value="table" aria-label="表格">
                表格
              </ToggleButton>
            </ToggleButtonGroup>
          </Grid>
        </Grid>
        
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            数据选择:
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            {availableDataTypes.map(({ type, label }) => (
              <Chip
                key={type}
                label={label}
                color={selectedDataTypes.includes(type) ? "primary" : "default"}
                onClick={() => handleDataTypeToggle(type)}
                sx={{ m: 0.5 }}
              />
            ))}
          </Stack>
        </Box>
        
        {loading ? (
          <Box display="flex" justifyContent="center" alignItems="center" height={height}>
            <CircularProgress />
          </Box>
        ) : (
          renderChart()
        )}
      </Box>
    </Paper>
  );
};

export default HealthDataVisualization; 