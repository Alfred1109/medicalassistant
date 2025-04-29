import React, { useState, useEffect } from 'react';
import { 
  Box, Paper, Typography, Grid, FormControl, 
  InputLabel, Select, MenuItem, Button, Divider,
  Card, CardContent, CircularProgress, Chip
} from '@mui/material';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, 
  AreaChart, Area, ScatterChart, Scatter, ResponsiveContainer,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
  ComposedChart, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis
} from 'recharts';
import DownloadIcon from '@mui/icons-material/Download';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import AssessmentIcon from '@mui/icons-material/Assessment';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';

// 数据点类型
interface DataPoint {
  id: string;
  value: number;
  timestamp: string | Date;
  category?: string;
  label?: string;
  metadata?: Record<string, any>;
}

// 数据集定义
interface Dataset {
  id: string;
  name: string;
  type: 'bloodPressure' | 'bloodGlucose' | 'heartRate' | 'exercise' | 'sleep' | 'weight' | 'custom';
  unit: string;
  color: string;
  data: DataPoint[];
  normalRange?: {
    min: number;
    max: number;
  };
}

// 图表类型
type ChartType = 'line' | 'bar' | 'pie' | 'area' | 'scatter' | 'composed' | 'radar';

// 时间范围
type TimeRange = '1d' | '7d' | '30d' | '90d' | '1y' | 'all' | 'custom';

// 组件属性
interface AdvancedDataVisualizationProps {
  datasets: Dataset[];
  defaultChartType?: ChartType;
  defaultTimeRange?: TimeRange;
  loading?: boolean;
  onTimeRangeChange?: (range: TimeRange, startDate?: Date, endDate?: Date) => void;
  onDatasetChange?: (datasetIds: string[]) => void;
  onExportData?: (format: 'csv' | 'json' | 'pdf') => void;
  title?: string;
  subtitle?: string;
}

// 颜色组
const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658'];

// 格式化数据
const formatData = (datasets: Dataset[], chartType: ChartType) => {
  if (chartType === 'pie') {
    // 饼图需要聚合数据
    return datasets.map(dataset => ({
      name: dataset.name,
      value: dataset.data.reduce((sum, point) => sum + point.value, 0) / dataset.data.length,
      color: dataset.color
    }));
  }
  
  if (chartType === 'radar') {
    // 雷达图需要特殊格式化
    const result: Record<string, any>[] = [];
    
    datasets.forEach(dataset => {
      dataset.data.forEach(point => {
        const existingPoint = result.find(item => item.category === point.category);
        if (existingPoint) {
          existingPoint[dataset.name] = point.value;
        } else if (point.category) {
          const newPoint: Record<string, any> = { category: point.category };
          newPoint[dataset.name] = point.value;
          result.push(newPoint);
        }
      });
    });
    
    return result;
  }
  
  // 普通图表数据格式化，合并多个数据集
  const combinedData: Record<string, any>[] = [];
  
  datasets.forEach(dataset => {
    dataset.data.forEach(point => {
      const pointDate = new Date(point.timestamp);
      const dateString = pointDate.toISOString().split('T')[0];
      
      const existingPoint = combinedData.find(item => item.date === dateString);
      if (existingPoint) {
        existingPoint[dataset.name] = point.value;
      } else {
        const newPoint: Record<string, any> = { 
          date: dateString,
          timestamp: pointDate
        };
        newPoint[dataset.name] = point.value;
        combinedData.push(newPoint);
      }
    });
  });
  
  // 按时间排序
  return combinedData.sort((a, b) => a.timestamp - b.timestamp);
};

// 获取图表颜色
const getDatasetColors = (datasets: Dataset[]): Record<string, string> => {
  const colors: Record<string, string> = {};
  
  datasets.forEach(dataset => {
    colors[dataset.name] = dataset.color;
  });
  
  return colors;
};

// 渲染图表
const renderChart = (chartType: ChartType, formattedData: any[], datasets: Dataset[], colors: Record<string, string>) => {
  switch (chartType) {
    case 'line':
      return (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={formattedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            {datasets.map((dataset) => (
              <Line 
                key={dataset.id}
                type="monotone" 
                dataKey={dataset.name} 
                stroke={colors[dataset.name]}
                name={`${dataset.name} (${dataset.unit})`}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      );
      
    case 'bar':
      return (
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={formattedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            {datasets.map((dataset) => (
              <Bar 
                key={dataset.id}
                dataKey={dataset.name} 
                fill={colors[dataset.name]}
                name={`${dataset.name} (${dataset.unit})`}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      );
      
    case 'area':
      return (
        <ResponsiveContainer width="100%" height={400}>
          <AreaChart data={formattedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            {datasets.map((dataset) => (
              <Area 
                key={dataset.id}
                type="monotone" 
                dataKey={dataset.name} 
                stroke={colors[dataset.name]}
                fill={colors[dataset.name] + '80'} // 添加透明度
                name={`${dataset.name} (${dataset.unit})`}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      );
      
    case 'pie':
      return (
        <ResponsiveContainer width="100%" height={400}>
          <PieChart>
            <Pie
              data={formattedData}
              cx="50%"
              cy="50%"
              labelLine={true}
              outerRadius={150}
              fill="#8884d8"
              dataKey="value"
              nameKey="name"
              label={({ name, value }) => `${name}: ${value.toFixed(1)}`}
            >
              {formattedData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color || COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(value: number) => value.toFixed(2)} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      );
      
    case 'scatter':
      return (
        <ResponsiveContainer width="100%" height={400}>
          <ScatterChart margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" dataKey="timestamp" name="日期" tickFormatter={(tick) => new Date(tick).toLocaleDateString()} />
            <YAxis dataKey={datasets[0]?.name} name={datasets[0]?.name} unit={datasets[0]?.unit} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(value: number) => value.toFixed(2)} />
            <Legend />
            {datasets.map((dataset) => (
              <Scatter 
                key={dataset.id}
                name={`${dataset.name} (${dataset.unit})`} 
                data={dataset.data.map(point => ({
                  timestamp: new Date(point.timestamp).getTime(),
                  [dataset.name]: point.value
                }))} 
                fill={colors[dataset.name]} 
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      );
      
    case 'composed':
      return (
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={formattedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            {datasets.map((dataset, index) => {
              // 交替使用不同的图表类型
              const chartComponents = [
                <Line 
                  key={dataset.id}
                  type="monotone" 
                  dataKey={dataset.name} 
                  stroke={colors[dataset.name]}
                  name={`${dataset.name} (${dataset.unit})`}
                />,
                <Bar 
                  key={dataset.id}
                  dataKey={dataset.name} 
                  fill={colors[dataset.name]}
                  name={`${dataset.name} (${dataset.unit})`}
                />,
                <Area 
                  key={dataset.id}
                  type="monotone" 
                  dataKey={dataset.name} 
                  stroke={colors[dataset.name]}
                  fill={colors[dataset.name] + '80'}
                  name={`${dataset.name} (${dataset.unit})`}
                />
              ];
              
              return chartComponents[index % chartComponents.length];
            })}
          </ComposedChart>
        </ResponsiveContainer>
      );
      
    case 'radar':
      return (
        <ResponsiveContainer width="100%" height={400}>
          <RadarChart cx="50%" cy="50%" outerRadius="80%" data={formattedData}>
            <PolarGrid />
            <PolarAngleAxis dataKey="category" />
            <PolarRadiusAxis />
            {datasets.map((dataset) => (
              <Radar 
                key={dataset.id}
                name={`${dataset.name} (${dataset.unit})`} 
                dataKey={dataset.name} 
                stroke={colors[dataset.name]} 
                fill={colors[dataset.name] + '80'} 
                fillOpacity={0.6} 
              />
            ))}
            <Tooltip formatter={(value: number) => value.toFixed(2)} />
            <Legend />
          </RadarChart>
        </ResponsiveContainer>
      );
      
    default:
      return <Typography color="error">不支持的图表类型</Typography>;
  }
};

const AdvancedDataVisualization: React.FC<AdvancedDataVisualizationProps> = ({
  datasets,
  defaultChartType = 'line',
  defaultTimeRange = '30d',
  loading = false,
  onTimeRangeChange,
  onDatasetChange,
  onExportData,
  title = '健康数据分析',
  subtitle = '可视化健康趋势及关联分析'
}) => {
  const [chartType, setChartType] = useState<ChartType>(defaultChartType);
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultTimeRange);
  const [selectedDatasets, setSelectedDatasets] = useState<string[]>(datasets.map(d => d.id));
  
  // 处理图表类型变更
  const handleChartTypeChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setChartType(event.target.value as ChartType);
  };
  
  // 处理时间范围变更
  const handleTimeRangeChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    const newRange = event.target.value as TimeRange;
    setTimeRange(newRange);
    onTimeRangeChange?.(newRange);
  };
  
  // 处理数据集选择变更
  const handleDatasetChange = (datasetId: string) => {
    const newSelectedDatasets = selectedDatasets.includes(datasetId)
      ? selectedDatasets.filter(id => id !== datasetId)
      : [...selectedDatasets, datasetId];
    
    setSelectedDatasets(newSelectedDatasets);
    onDatasetChange?.(newSelectedDatasets);
  };
  
  // 处理导出数据
  const handleExportData = (format: 'csv' | 'json' | 'pdf') => {
    onExportData?.(format);
  };
  
  // 过滤选中的数据集
  const filteredDatasets = datasets.filter(dataset => selectedDatasets.includes(dataset.id));
  
  // 格式化数据
  const formattedData = formatData(filteredDatasets, chartType);
  const colors = getDatasetColors(filteredDatasets);
  
  return (
    <Box>
      <Paper elevation={0} sx={{ p: 3, mb: 3, borderRadius: 2 }}>
        <Box display="flex" flexDirection="row" justifyContent="space-between" alignItems="center" mb={2}>
          <Box>
            <Typography variant="h5" component="h2" gutterBottom>
              {title}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {subtitle}
            </Typography>
          </Box>
          <Box>
            <Button 
              variant="outlined" 
              startIcon={<DownloadIcon />}
              onClick={() => handleExportData('csv')}
              sx={{ mr: 1 }}
            >
              导出CSV
            </Button>
            <Button 
              variant="outlined" 
              startIcon={<DownloadIcon />}
              onClick={() => handleExportData('pdf')}
            >
              导出PDF
            </Button>
          </Box>
        </Box>
        
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth variant="outlined" size="small">
              <InputLabel id="chart-type-label">图表类型</InputLabel>
              <Select
                labelId="chart-type-label"
                value={chartType}
                onChange={handleChartTypeChange}
                label="图表类型"
              >
                <MenuItem value="line">折线图</MenuItem>
                <MenuItem value="bar">柱状图</MenuItem>
                <MenuItem value="area">区域图</MenuItem>
                <MenuItem value="pie">饼图</MenuItem>
                <MenuItem value="scatter">散点图</MenuItem>
                <MenuItem value="composed">组合图</MenuItem>
                <MenuItem value="radar">雷达图</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth variant="outlined" size="small">
              <InputLabel id="time-range-label">时间范围</InputLabel>
              <Select
                labelId="time-range-label"
                value={timeRange}
                onChange={handleTimeRangeChange}
                label="时间范围"
                startAdornment={<CalendarTodayIcon sx={{ ml: 1, mr: 0.5, color: 'action.active' }} />}
              >
                <MenuItem value="1d">今天</MenuItem>
                <MenuItem value="7d">最近7天</MenuItem>
                <MenuItem value="30d">最近30天</MenuItem>
                <MenuItem value="90d">最近90天</MenuItem>
                <MenuItem value="1y">最近一年</MenuItem>
                <MenuItem value="all">全部数据</MenuItem>
                <MenuItem value="custom">自定义范围</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Box display="flex" flexWrap="wrap" gap={1}>
              {datasets.map(dataset => (
                <Chip
                  key={dataset.id}
                  label={dataset.name}
                  color={selectedDatasets.includes(dataset.id) ? "primary" : "default"}
                  variant={selectedDatasets.includes(dataset.id) ? "filled" : "outlined"}
                  onClick={() => handleDatasetChange(dataset.id)}
                  sx={{ 
                    borderColor: dataset.color,
                    bgcolor: selectedDatasets.includes(dataset.id) ? dataset.color : 'transparent',
                    '& .MuiChip-label': {
                      color: selectedDatasets.includes(dataset.id) ? 'white' : dataset.color
                    }
                  }}
                />
              ))}
            </Box>
          </Grid>
        </Grid>
        
        <Divider sx={{ mb: 3 }} />
        
        {loading ? (
          <Box display="flex" justifyContent="center" alignItems="center" height={400}>
            <CircularProgress />
          </Box>
        ) : filteredDatasets.length === 0 ? (
          <Box display="flex" justifyContent="center" alignItems="center" height={400}>
            <Typography variant="h6" color="textSecondary">
              请选择至少一个数据集以查看图表
            </Typography>
          </Box>
        ) : (
          renderChart(chartType, formattedData, filteredDatasets, colors)
        )}
      </Paper>
      
      <Grid container spacing={3}>
        {filteredDatasets.map(dataset => (
          <Grid item xs={12} sm={6} md={4} key={dataset.id}>
            <Card variant="outlined" sx={{ height: '100%' }}>
              <CardContent>
                <Box display="flex" alignItems="center" mb={1}>
                  <FitnessCenterIcon sx={{ color: dataset.color, mr: 1 }} />
                  <Typography variant="h6" component="h3">
                    {dataset.name}
                  </Typography>
                </Box>
                
                <Typography variant="body2" color="textSecondary" gutterBottom>
                  单位: {dataset.unit}
                </Typography>
                
                {dataset.normalRange && (
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    正常范围: {dataset.normalRange.min} - {dataset.normalRange.max} {dataset.unit}
                  </Typography>
                )}
                
                <Divider sx={{ my: 1.5 }} />
                
                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="textSecondary">
                      平均值
                    </Typography>
                    <Typography variant="h6">
                      {(dataset.data.reduce((sum, point) => sum + point.value, 0) / dataset.data.length).toFixed(1)} {dataset.unit}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="textSecondary">
                      最新值
                    </Typography>
                    <Typography variant="h6">
                      {dataset.data.length > 0 ? 
                        dataset.data[dataset.data.length - 1].value.toFixed(1) : 'N/A'} {dataset.unit}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="textSecondary">
                      最大值
                    </Typography>
                    <Typography variant="h6">
                      {Math.max(...dataset.data.map(d => d.value)).toFixed(1)} {dataset.unit}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="textSecondary">
                      最小值
                    </Typography>
                    <Typography variant="h6">
                      {Math.min(...dataset.data.map(d => d.value)).toFixed(1)} {dataset.unit}
                    </Typography>
                  </Grid>
                </Grid>
                
                <Divider sx={{ my: 1.5 }} />
                
                <Box display="flex" alignItems="center" justifyContent="space-between">
                  <Box>
                    <Typography variant="caption" color="textSecondary">
                      数据点数
                    </Typography>
                    <Typography variant="body1">
                      {dataset.data.length}
                    </Typography>
                  </Box>
                  <Button 
                    size="small" 
                    variant="outlined" 
                    startIcon={<AssessmentIcon />}
                    onClick={() => {
                      // 如果只有这一个数据集没被选中，则添加它
                      if (!selectedDatasets.includes(dataset.id)) {
                        handleDatasetChange(dataset.id);
                      }
                      // 将图表类型更改为线图以更好地显示单一数据集
                      setChartType('line');
                    }}
                  >
                    详细分析
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

export default AdvancedDataVisualization; 