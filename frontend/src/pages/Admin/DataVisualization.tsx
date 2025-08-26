import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Divider,
  Tabs,
  Tab,
  Button,
  CircularProgress
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import { 
  ChartDataType, 
  TimeRange, 
  TrendData, 
  DistributionData, 
  ComparisonData, 
  StatsOverview 
} from '../../types/dataAnalysis';
import AnalyticsChart from '../../components/Analytics/AnalyticsChart';
import { analyticsService } from '../../services/analyticsService';

// 模拟图表组件
const ChartPlaceholder: React.FC<{ title: string; height?: number; type?: string }> = ({ 
  title, 
  height = 300,
  type = "line"
}) => {
  return (
    <Box 
      sx={{ 
        height: height, 
        display: 'flex', 
        flexDirection: 'column',
        alignItems: 'center', 
        justifyContent: 'center',
        border: '1px dashed grey',
        borderRadius: 1,
        p: 2
      }}
    >
      <Typography variant="subtitle1" gutterBottom>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" align="center">
        这里将显示{type === "line" ? "折线图" : type === "bar" ? "柱状图" : type === "pie" ? "饼图" : "图表"}数据
        <br />
        集成真实图表库后替换
      </Typography>
    </Box>
  );
};

// 模拟数据
const mockData = {
  patientCount: 1248,
  weekPatientChange: 4.2,
  doctorCount: 86,
  totalDevices: 152,
  activeDeviceRate: 82,
  avgTrainingTime: 45,
  rehabilitationRate: 68,
  patientSatisfaction: 92
};

const DataVisualization: React.FC = () => {
  // 状态管理
  const [timeRange, setTimeRange] = useState<TimeRange>('month');
  const [dataType, setDataType] = useState<ChartDataType>('patient');
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statsData, setStatsData] = useState<StatsOverview | null>(null);
  const [trendData, setTrendData] = useState<TrendData[]>([]);
  const [distributionData, setDistributionData] = useState<DistributionData[]>([]);
  const [comparisonData, setComparisonData] = useState<ComparisonData[]>([]);
  const [exportLoading, setExportLoading] = useState(false);

  // 处理类型变更
  const handleDataTypeChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setDataType(event.target.value as ChartDataType);
  };

  // 处理时间范围变更
  const handleTimeRangeChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setTimeRange(event.target.value as TimeRange);
  };

  // 处理标签切换
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // 导出数据
  const handleExportData = async (format: 'csv' | 'xlsx' | 'pdf') => {
    try {
      setExportLoading(true);
      const blob = await analyticsService.exportReport(dataType, timeRange, format);
      
      // 创建下载链接
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${dataType}_report_${timeRange}.${format}`;
      document.body.appendChild(a);
      a.click();
      
      // 清理
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('导出数据失败:', error);
    } finally {
      setExportLoading(false);
    }
  };

  // 加载数据
  const loadData = async () => {
    setLoading(true);
    try {
      // 并行加载多个数据源
      const [stats, trend, distribution, comparison] = await Promise.all([
        analyticsService.getStatsOverview(),
        analyticsService.getTrendData(dataType, timeRange),
        analyticsService.getDistributionData(dataType, timeRange),
        analyticsService.getComparisonData(dataType, timeRange, 'lastPeriod')
      ]);
      
      setStatsData(stats);
      setTrendData(trend);
      setDistributionData(distribution);
      setComparisonData(comparison);
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  // 当数据类型或时间范围变化时重新加载数据
  useEffect(() => {
    loadData();
  }, [dataType, timeRange]);

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          数据可视化
        </Typography>
        <Box display="flex" gap={2} alignItems="center">
          <FormControl variant="outlined" size="small" sx={{ minWidth: 120 }}>
            <InputLabel>数据类型</InputLabel>
            <Select
              value={dataType}
              onChange={handleDataTypeChange}
              label="数据类型"
            >
              <MenuItem value="patient">患者数据</MenuItem>
              <MenuItem value="doctor">医生数据</MenuItem>
              <MenuItem value="device">设备数据</MenuItem>
              <MenuItem value="rehabilitation">康复数据</MenuItem>
            </Select>
          </FormControl>
          
          <FormControl variant="outlined" size="small" sx={{ minWidth: 120 }}>
            <InputLabel>时间范围</InputLabel>
            <Select
              value={timeRange}
              onChange={handleTimeRangeChange}
              label="时间范围"
            >
              <MenuItem value="day">今日</MenuItem>
              <MenuItem value="week">本周</MenuItem>
              <MenuItem value="month">本月</MenuItem>
              <MenuItem value="quarter">季度</MenuItem>
              <MenuItem value="year">年度</MenuItem>
            </Select>
          </FormControl>
          
          <Button 
            variant="outlined" 
            size="small"
            startIcon={<DownloadIcon />}
            onClick={() => handleExportData('xlsx')}
            disabled={exportLoading}
          >
            {exportLoading ? <CircularProgress size={16} /> : '导出'}
          </Button>
        </Box>
      </Box>

      {/* 数据概览卡片 */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                总患者数
              </Typography>
              <Typography variant="h4" component="div">
                {statsData?.patientCount || 0}
              </Typography>
              <Typography 
                variant="body2" 
                color={(statsData?.weekPatientChange || 0) > 0 ? "success.main" : "error.main"}
              >
                {(statsData?.weekPatientChange || 0) > 0 ? "+" : ""}
                {statsData?.weekPatientChange || 0}% 较上周
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                总医生数
              </Typography>
              <Typography variant="h4" component="div">
                {statsData?.doctorCount || 0}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                包含专科医生和康复师
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                设备总数
              </Typography>
              <Typography variant="h4" component="div">
                {statsData?.totalDevices || 0}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                活跃率: {statsData?.activeDeviceRate || 0}%
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                平均训练时长
              </Typography>
              <Typography variant="h4" component="div">
                {statsData?.avgTrainingTime || 0}分钟
              </Typography>
              <Typography variant="body2" color="text.secondary">
                康复有效率: {statsData?.rehabilitationRate || 0}%
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* 图表视图选项卡 */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="趋势分析" />
          <Tab label="对比分析" />
          <Tab label="分布分析" />
        </Tabs>
      </Box>

      {/* 趋势分析 */}
      {tabValue === 0 && (
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                {dataType === 'patient' && '患者数量趋势'}
                {dataType === 'doctor' && '医生工作量趋势'}
                {dataType === 'device' && '设备使用趋势'}
                {dataType === 'rehabilitation' && '康复效果趋势'}
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <AnalyticsChart 
                type="line"
                data={trendData}
                height={400}
                loading={loading}
                xKey="date"
                yKeys={["value"]}
                title={`${timeRange === 'day' ? '今日' : timeRange === 'week' ? '本周' : timeRange === 'month' ? '本月' : timeRange === 'quarter' ? '季度' : '年度'}趋势`}
              />
            </Paper>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                {dataType === 'patient' && '患者年龄分布'}
                {dataType === 'doctor' && '医生专业分布'}
                {dataType === 'device' && '设备类型分布'}
                {dataType === 'rehabilitation' && '康复类型分布'}
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <AnalyticsChart 
                type="pie"
                data={distributionData}
                height={300}
                loading={loading}
                nameKey="name"
                valueKey="value"
                title="分布情况"
              />
            </Paper>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                {dataType === 'patient' && '患者满意度'}
                {dataType === 'doctor' && '医生评分'}
                {dataType === 'device' && '设备利用率'}
                {dataType === 'rehabilitation' && '康复进度'}
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <AnalyticsChart 
                type="bar"
                data={trendData.slice(-5)} // 只显示最近5条数据
                height={300}
                loading={loading}
                xKey="date"
                yKeys={["value"]}
                title="评分情况"
              />
            </Paper>
          </Grid>
        </Grid>
      )}

      {/* 对比分析 */}
      {tabValue === 1 && (
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                不同时间段对比
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <AnalyticsChart 
                type="bar"
                data={comparisonData}
                height={400}
                loading={loading}
                xKey="category"
                yKeys={Object.keys(comparisonData[0] || {}).filter(k => k !== 'category')}
                title="时间段对比"
              />
            </Paper>
          </Grid>
          
          <Grid item xs={12}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                不同类别对比
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <AnalyticsChart 
                type="bar"
                data={comparisonData}
                height={400}
                loading={loading}
                xKey="category"
                yKeys={Object.keys(comparisonData[0] || {}).filter(k => k !== 'category')}
                title="类别对比"
              />
            </Paper>
          </Grid>
        </Grid>
      )}

      {/* 分布分析 */}
      {tabValue === 2 && (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                地域分布
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <AnalyticsChart 
                type="pie"
                data={[
                  { name: '北京', value: 25, color: '#8884d8' },
                  { name: '上海', value: 20, color: '#82ca9d' },
                  { name: '广州', value: 18, color: '#ffc658' },
                  { name: '深圳', value: 15, color: '#ff8042' },
                  { name: '其他', value: 22, color: '#0088FE' }
                ]}
                height={350}
                loading={loading}
                nameKey="name"
                valueKey="value"
                title="地域分布图"
              />
            </Paper>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                类别分布
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <AnalyticsChart 
                type="pie"
                data={distributionData}
                height={350}
                loading={loading}
                nameKey="name"
                valueKey="value"
                title="类别分布图"
              />
            </Paper>
          </Grid>
          
          <Grid item xs={12}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                数据趋势分析
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <AnalyticsChart 
                type="area"
                data={trendData}
                height={350}
                loading={loading}
                xKey="date"
                yKeys={["value"]}
                title="数据趋势图"
              />
            </Paper>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};

export default DataVisualization; 