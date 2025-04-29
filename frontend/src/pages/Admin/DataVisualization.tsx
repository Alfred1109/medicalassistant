import React from 'react';
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
} from '@mui/material';

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
  const [timeRange, setTimeRange] = React.useState('month');
  const [dataType, setDataType] = React.useState('patient');
  const [tabValue, setTabValue] = React.useState(0);

  const handleTimeRangeChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setTimeRange(event.target.value as string);
  };

  const handleDataTypeChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setDataType(event.target.value as string);
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          数据可视化
        </Typography>
        <Box display="flex" gap={2}>
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
                {mockData.patientCount}
              </Typography>
              <Typography variant="body2" color={mockData.weekPatientChange > 0 ? "success.main" : "error.main"}>
                {mockData.weekPatientChange > 0 ? "+" : ""}{mockData.weekPatientChange}% 较上周
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
                {mockData.doctorCount}
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
                {mockData.totalDevices}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                活跃率: {mockData.activeDeviceRate}%
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
                {mockData.avgTrainingTime}分钟
              </Typography>
              <Typography variant="body2" color="text.secondary">
                康复有效率: {mockData.rehabilitationRate}%
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
              <ChartPlaceholder 
                title={`${timeRange === 'day' ? '今日' : timeRange === 'week' ? '本周' : timeRange === 'month' ? '本月' : timeRange === 'quarter' ? '季度' : '年度'}趋势`} 
                height={400} 
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
              <ChartPlaceholder title="分布情况" type="pie" />
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
              <ChartPlaceholder title="评分情况" type="bar" />
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
              <ChartPlaceholder 
                title="时间段对比" 
                height={400} 
                type="bar"
              />
            </Paper>
          </Grid>
          <Grid item xs={12}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                不同类别对比
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <ChartPlaceholder 
                title="类别对比" 
                height={400} 
                type="bar"
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
              <ChartPlaceholder 
                title="地域分布图" 
                height={350} 
              />
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                类别分布
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <ChartPlaceholder 
                title="类别分布图" 
                height={350}
                type="pie"
              />
            </Paper>
          </Grid>
          <Grid item xs={12}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>
                热力图分析
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <ChartPlaceholder 
                title="使用热力图" 
                height={350}
              />
            </Paper>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};

export default DataVisualization; 