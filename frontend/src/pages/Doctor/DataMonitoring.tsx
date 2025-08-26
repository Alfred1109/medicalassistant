import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Divider,
  Tabs,
  Tab,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  IconButton,
  Button,
  Chip,
  Alert,
  CircularProgress,
} from '@mui/material';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import LinearProgress from '@mui/material/LinearProgress';
import RefreshIcon from '@mui/icons-material/Refresh';
import TimelineIcon from '@mui/icons-material/Timeline';
import FavoriteIcon from '@mui/icons-material/Favorite';
import OpacityIcon from '@mui/icons-material/Opacity';
import DeviceThermostatIcon from '@mui/icons-material/DeviceThermostat';
import MonitorWeightIcon from '@mui/icons-material/MonitorWeight';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import WarningIcon from '@mui/icons-material/Warning';
import ErrorIcon from '@mui/icons-material/Error';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { Link } from 'react-router-dom';
// 模拟图表导入，在实际项目中替换为实际的图表库
// 比如 import { Line, Bar } from 'react-chartjs-2';

// 选项卡面板属性接口
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 生命体征数据接口
interface VitalSign {
  id: number;
  type: string;
  value: string;
  unit: string;
  time: string;
  status: 'normal' | 'warning' | 'alert';
  reference: string;
  history: any[];
}

// 血糖数据接口
interface GlucoseData {
  id: number;
  timePoint: string;
  value: number;
  unit: string;
  time: string;
  status: 'normal' | 'warning' | 'alert';
  reference: string;
}

// 血压趋势数据接口
interface BPTrendData {
  date: string;
  systolic: number;
  diastolic: number;
}

// 选项卡面板组件
function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`data-monitoring-tabpanel-${index}`}
      aria-labelledby={`data-monitoring-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

// 模拟患者列表
const MOCK_PATIENTS = [
  { id: '1001', name: '张三', age: 45, gender: '男', diagnosis: '腰椎间盘突出' },
  { id: '1002', name: '李四', age: 58, gender: '男', diagnosis: '骨关节炎' },
  { id: '1003', name: '王五', age: 35, gender: '女', diagnosis: '腕管综合征' },
  { id: '1004', name: '赵六', age: 62, gender: '女', diagnosis: '脑卒中后遗症' },
];

// 生命体征模拟数据
const MOCK_VITAL_SIGNS: VitalSign[] = [
  { 
    id: 1, 
    type: '心率', 
    value: '78', 
    unit: 'bpm', 
    time: '2023-06-01 08:30', 
    status: 'normal',
    reference: '60-100 bpm',
    history: [75, 72, 78, 79, 80, 77, 78]
  },
  { 
    id: 2, 
    type: '血压', 
    value: '135/85', 
    unit: 'mmHg', 
    time: '2023-06-01 08:30', 
    status: 'warning',
    reference: '收缩压 < 130, 舒张压 < 80 mmHg',
    history: [
      { systolic: 132, diastolic: 84 }, 
      { systolic: 129, diastolic: 83 }, 
      { systolic: 135, diastolic: 85 }, 
      { systolic: 140, diastolic: 86 },
      { systolic: 138, diastolic: 85 }, 
      { systolic: 132, diastolic: 82 }
    ]
  },
  { 
    id: 3, 
    type: '体温', 
    value: '36.5', 
    unit: '°C', 
    time: '2023-06-01 08:30', 
    status: 'normal',
    reference: '36.0-37.3°C',
    history: [36.4, 36.5, 36.7, 36.5, 36.4, 36.5, 36.5]
  },
  { 
    id: 4, 
    type: '呼吸频率', 
    value: '18', 
    unit: '次/分钟', 
    time: '2023-06-01 08:30', 
    status: 'normal',
    reference: '12-20 次/分钟',
    history: [16, 17, 18, 16, 17, 18, 18]
  },
  { 
    id: 5, 
    type: '血氧饱和度', 
    value: '95', 
    unit: '%', 
    time: '2023-06-01 08:30', 
    status: 'normal',
    reference: '95-100%',
    history: [97, 96, 96, 95, 96, 97, 95]
  }
];

// 血糖模拟数据
const MOCK_GLUCOSE_DATA: GlucoseData[] = [
  { id: 1, timePoint: '早餐前', value: 5.2, unit: 'mmol/L', time: '2023-06-01 07:30', status: 'normal', reference: '3.9-7.2 mmol/L' },
  { id: 2, timePoint: '早餐后2小时', value: 9.1, unit: 'mmol/L', time: '2023-06-01 09:30', status: 'warning', reference: '< 8.3 mmol/L' },
  { id: 3, timePoint: '午餐前', value: 6.3, unit: 'mmol/L', time: '2023-06-01 12:00', status: 'normal', reference: '3.9-7.2 mmol/L' },
  { id: 4, timePoint: '午餐后2小时', value: 8.8, unit: 'mmol/L', time: '2023-06-01 14:00', status: 'warning', reference: '< 8.3 mmol/L' },
  { id: 5, timePoint: '晚餐前', value: 5.9, unit: 'mmol/L', time: '2023-06-01 18:00', status: 'normal', reference: '3.9-7.2 mmol/L' },
  { id: 6, timePoint: '晚餐后2小时', value: 7.8, unit: 'mmol/L', time: '2023-06-01 20:00', status: 'normal', reference: '< 8.3 mmol/L' },
  { id: 7, timePoint: '睡前', value: 6.5, unit: 'mmol/L', time: '2023-06-01 22:00', status: 'normal', reference: '3.9-7.2 mmol/L' },
];

// 血压趋势模拟数据
const MOCK_BP_TREND: BPTrendData[] = [
  { date: '5/25', systolic: 128, diastolic: 80 },
  { date: '5/26', systolic: 130, diastolic: 82 },
  { date: '5/27', systolic: 125, diastolic: 78 },
  { date: '5/28', systolic: 132, diastolic: 83 },
  { date: '5/29', systolic: 135, diastolic: 85 },
  { date: '5/30', systolic: 130, diastolic: 81 },
  { date: '5/31', systolic: 128, diastolic: 80 },
  { date: '6/1', systolic: 135, diastolic: 85 },
];

// 用药情况模拟数据
const MOCK_MEDICATIONS = [
  {
    id: 1,
    name: '布洛芬缓释胶囊',
    dosage: '0.3g',
    frequency: '每日3次',
    startDate: '2023-05-20',
    endDate: '2023-06-20',
    purpose: '疼痛管理',
    status: 'active'
  },
  {
    id: 2,
    name: '盐酸氨基葡萄糖胶囊',
    dosage: '0.75g',
    frequency: '每日1次',
    startDate: '2023-05-15',
    endDate: '2023-08-15',
    purpose: '关节健康',
    status: 'active'
  },
  {
    id: 3,
    name: '维生素D钙片',
    dosage: '1片',
    frequency: '每日1次',
    startDate: '2023-05-15',
    endDate: '长期',
    purpose: '骨骼健康',
    status: 'active'
  }
];

// 康复进度模拟数据
const MOCK_REHAB_PROGRESS = {
  startDate: '2023-05-01',
  currentWeek: 5,
  totalWeeks: 12,
  completionRate: 65,
  painLevel: {
    initial: 8,
    current: 4,
    target: 0
  },
  mobility: {
    initial: 40,
    current: 65,
    target: 90
  },
  strength: {
    initial: 30,
    current: 55,
    target: 85
  },
  weeklyExercises: [
    { week: 1, completed: 100 },
    { week: 2, completed: 90 },
    { week: 3, completed: 85 },
    { week: 4, completed: 75 },
    { week: 5, completed: 65 },
  ],
  nextAppointment: '2023-06-05 14:30'
};

const DataMonitoring: React.FC = () => {
  // 状态管理
  const [tabValue, setTabValue] = React.useState(0);
  const [selectedPatient, setSelectedPatient] = React.useState<string>('');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [vitals, setVitals] = React.useState<VitalSign[]>([]);
  const [glucoseData, setGlucoseData] = React.useState<GlucoseData[]>([]);
  const [bpTrend, setBpTrend] = React.useState<BPTrendData[]>([]);
  const [medications, setMedications] = React.useState<any[]>([]);
  const [rehabProgress, setRehabProgress] = React.useState<any>(null);

  // 处理选项卡变更
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // 处理患者选择变更
  const handlePatientChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setSelectedPatient(event.target.value as string);
  };

  // 获取状态图标和颜色
  const getStatusIcon = (status: string) => {
    switch(status) {
      case 'normal':
        return <CheckCircleIcon fontSize="small" color="success" />;
      case 'warning':
        return <WarningIcon fontSize="small" color="warning" />;
      case 'alert':
        return <ErrorIcon fontSize="small" color="error" />;
      default:
        return null;
    }
  };
  
  // 获取状态颜色
  const getStatusColor = (status: string) => {
    switch(status) {
      case 'normal':
        return 'success';
      case 'warning':
        return 'warning';
      case 'alert':
        return 'error';
      default:
        return 'default';
    }
  };

  // 模拟加载数据
  const loadPatientData = () => {
    setLoading(true);
    setError(null);
    
    // 模拟API延迟
    setTimeout(() => {
      // 设置模拟数据
      setVitals(MOCK_VITAL_SIGNS);
      setGlucoseData(MOCK_GLUCOSE_DATA);
      setBpTrend(MOCK_BP_TREND);
      setMedications(MOCK_MEDICATIONS);
      setRehabProgress(MOCK_REHAB_PROGRESS);
      setLoading(false);
    }, 1000);
  };

  // 初始加载数据
  React.useEffect(() => {
    if (selectedPatient) {
      loadPatientData();
    }
  }, [selectedPatient]);

  // 模拟图表组件 - 实际项目中应使用真实的图表库
  const LineChartPlaceholder = ({ title, data }: { title: string, data: any[] }) => (
    <Box sx={{ width: '100%', height: 200, bgcolor: 'action.hover', p: 2, borderRadius: 1, position: 'relative' }}>
      <Typography variant="subtitle2" gutterBottom>{title}</Typography>
      <Typography variant="caption" sx={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }}>
        图表将在此处显示 - 包含 {data.length} 数据点
      </Typography>
    </Box>
  );

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        患者数据监测
      </Typography>
      
      <Paper sx={{ p: 3, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6} md={4}>
            <FormControl fullWidth>
              <InputLabel id="patient-select-label">选择患者</InputLabel>
              <Select
                labelId="patient-select-label"
                id="patient-select"
                value={selectedPatient}
                label="选择患者"
                onChange={handlePatientChange as any}
              >
                <MenuItem value="">
                  <em>请选择</em>
                </MenuItem>
                {MOCK_PATIENTS.map((patient) => (
                  <MenuItem key={patient.id} value={patient.id}>
                    {patient.name} ({patient.age}岁, {patient.gender})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={8} textAlign="right">
            <Button 
              variant="contained" 
              color="primary"
              startIcon={<RefreshIcon />}
              onClick={loadPatientData}
              disabled={!selectedPatient || loading}
              sx={{ mr: 1 }}
            >
              刷新数据
            </Button>
            {selectedPatient && (
              <Button
                component={Link}
                to={`/health-manager/health-data-timeline/${selectedPatient}`}
                variant="outlined"
                startIcon={<TimelineIcon />}
              >
                查看时间线
              </Button>
            )}
          </Grid>
        </Grid>
      </Paper>
      
      {!selectedPatient ? (
        <Alert severity="info" sx={{ mt: 2 }}>请选择一位患者以查看其健康数据监测信息</Alert>
      ) : loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>
      ) : (
        <Box sx={{ width: '100%' }}>
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs 
              value={tabValue} 
              onChange={handleTabChange} 
              aria-label="health data tabs"
              variant="scrollable"
              scrollButtons="auto"
            >
              <Tab icon={<FavoriteIcon />} iconPosition="start" label="生命体征" />
              <Tab icon={<OpacityIcon />} iconPosition="start" label="血压/血糖" />
              <Tab icon={<LocalHospitalIcon />} iconPosition="start" label="用药情况" />
              <Tab icon={<MonitorWeightIcon />} iconPosition="start" label="康复进度" />
            </Tabs>
          </Box>
          
          {/* 生命体征选项卡 */}
          <TabPanel value={tabValue} index={0}>
            <Grid container spacing={3}>
              {/* 生命体征摘要卡片 */}
              {vitals.map((vital) => (
                <Grid item xs={12} sm={6} md={4} key={vital.id}>
                  <Card variant="outlined">
                    <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                        <Typography variant="subtitle1" component="div">
                          {vital.type}
                        </Typography>
                        {getStatusIcon(vital.status)}
                      </Box>
                      <Box display="flex" alignItems="baseline">
                        <Typography variant="h4" component="span" color={`${getStatusColor(vital.status)}.main`}>
                          {vital.value}
                        </Typography>
                        <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                          {vital.unit}
                        </Typography>
                      </Box>
                      <Typography variant="caption" color="text.secondary" component="div">
                        记录时间: {vital.time}
                      </Typography>
                      <Divider sx={{ my: 1 }} />
                      <Typography variant="caption" color="text.secondary">
                        参考范围: {vital.reference}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
              
              {/* 生命体征历史趋势图表 */}
              <Grid item xs={12}>
                <Paper sx={{ p: 2 }}>
                  <Typography variant="h6" gutterBottom>生命体征趋势</Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <LineChartPlaceholder 
                        title="心率趋势 (bpm)" 
                        data={vitals.length > 0 ? vitals[0].history : []} 
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <LineChartPlaceholder 
                        title="体温趋势 (°C)" 
                        data={vitals.length > 0 ? vitals[2].history : []} 
                      />
                    </Grid>
                  </Grid>
                </Paper>
              </Grid>
            </Grid>
          </TabPanel>
          
          {/* 血压/血糖选项卡 */}
          <TabPanel value={tabValue} index={1}>
            <Grid container spacing={3}>
              {/* 血压部分 */}
              <Grid item xs={12}>
                <Paper sx={{ p: 3, mb: 3 }}>
                  <Typography variant="h6" gutterBottom>血压监测</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={4}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle1" gutterBottom>当前血压</Typography>
                          <Box display="flex" alignItems="baseline">
                            <Typography variant="h4" component="span" color={vitals.length > 0 && vitals[1].status === 'warning' ? 'warning.main' : 'text.primary'}>
                              {vitals.length > 0 ? vitals[1].value : '-/-'}
                            </Typography>
                            <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                              mmHg
                            </Typography>
                          </Box>
                          <Typography variant="caption" color="text.secondary">
                            {vitals.length > 0 ? `记录于 ${vitals[1].time}` : '无数据'}
                          </Typography>
                          {vitals.length > 0 && vitals[1].status === 'warning' && (
                            <Alert severity="warning" sx={{ mt: 1 }}>
                              血压偏高，请注意监测
                            </Alert>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>
                    <Grid item xs={12} md={8}>
                      <LineChartPlaceholder title="血压趋势" data={bpTrend} />
                    </Grid>
                  </Grid>
                </Paper>
              </Grid>
              
              {/* 血糖部分 */}
              <Grid item xs={12}>
                <Paper sx={{ p: 3 }}>
                  <Typography variant="h6" gutterBottom>血糖监测</Typography>
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>测量时间点</TableCell>
                          <TableCell>数值</TableCell>
                          <TableCell>状态</TableCell>
                          <TableCell>参考范围</TableCell>
                          <TableCell>记录时间</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {glucoseData.map((row) => (
                          <TableRow key={row.id} hover>
                            <TableCell>{row.timePoint}</TableCell>
                            <TableCell>
                              <Box display="flex" alignItems="center">
                                {row.value} {row.unit}
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Chip 
                                size="small" 
                                label={row.status === 'normal' ? '正常' : '偏高'} 
                                color={getStatusColor(row.status) as any} 
                                icon={getStatusIcon(row.status)}
                              />
                            </TableCell>
                            <TableCell>{row.reference}</TableCell>
                            <TableCell>{row.time}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  <Box mt={3}>
                    <LineChartPlaceholder title="血糖日内波动" data={glucoseData.map(item => item.value)} />
                  </Box>
                </Paper>
              </Grid>
            </Grid>
          </TabPanel>
          
          {/* 用药情况选项卡 */}
          <TabPanel value={tabValue} index={2}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Paper sx={{ p: 3, mb: 3 }}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                    <Typography variant="h6">当前用药</Typography>
                    <Button 
                      variant="outlined" 
                      size="small"
                      component={Link}
                      to={`/doctor/health-records/${selectedPatient}`}
                    >
                      查看完整用药史
                    </Button>
                  </Box>
                  
                  <TableContainer>
                    <Table>
                      <TableHead>
                        <TableRow>
                          <TableCell>药品名称</TableCell>
                          <TableCell>剂量</TableCell>
                          <TableCell>频率</TableCell>
                          <TableCell>用途</TableCell>
                          <TableCell>起止日期</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {medications.map((med) => (
                          <TableRow key={med.id} hover>
                            <TableCell>
                              <Typography variant="body2" fontWeight="500">
                                {med.name}
                              </Typography>
                            </TableCell>
                            <TableCell>{med.dosage}</TableCell>
                            <TableCell>{med.frequency}</TableCell>
                            <TableCell>{med.purpose}</TableCell>
                            <TableCell>
                              {med.startDate} 至 {med.endDate === '长期' ? (
                                <Chip size="small" label="长期" color="primary" />
                              ) : med.endDate}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Paper>
              </Grid>
              
              <Grid item xs={12}>
                <Paper sx={{ p: 3 }}>
                  <Typography variant="h6" gutterBottom>服药依从性</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle2" color="text.secondary">
                            本周服药依从率
                          </Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                            <Box sx={{ width: '100%', mr: 1 }}>
                              <LinearProgress 
                                variant="determinate" 
                                value={85} 
                                color="success"
                                sx={{ height: 10, borderRadius: 5 }}
                              />
                            </Box>
                            <Box sx={{ minWidth: 35 }}>
                              <Typography variant="body2" color="text.secondary">85%</Typography>
                            </Box>
                          </Box>
                          <Typography variant="body2" mt={1}>
                            患者本周服药情况良好，但周三早晨剂量缺失。
                          </Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle2" color="text.secondary">
                            近4周服药依从率趋势
                          </Typography>
                          <Box sx={{ height: 120, mt: 2 }}>
                            <LineChartPlaceholder 
                              title="依从率趋势" 
                              data={[90, 88, 78, 85]} 
                            />
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  </Grid>
                </Paper>
              </Grid>
            </Grid>
          </TabPanel>
          
          {/* 康复进度选项卡 */}
          <TabPanel value={tabValue} index={3}>
            {rehabProgress ? (
              <Grid container spacing={3}>
                {/* 康复进度概览 */}
                <Grid item xs={12}>
                  <Paper sx={{ p: 3, mb: 3 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                      <Typography variant="h6">康复计划进度</Typography>
                      <Button 
                        variant="outlined" 
                        size="small"
                        component={Link}
                        to={`/rehab-plans`}
                      >
                        查看完整计划
                      </Button>
                    </Box>
                    
                    <Grid container spacing={3}>
                      <Grid item xs={12} md={6}>
                        <Box>
                          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                            当前进度
                          </Typography>
                          <Box sx={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
                            <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                              <CircularProgress 
                                variant="determinate" 
                                value={rehabProgress.completionRate} 
                                size={100}
                                thickness={5}
                                color="primary"
                              />
                              <Box
                                sx={{
                                  top: 0,
                                  left: 0,
                                  bottom: 0,
                                  right: 0,
                                  position: 'absolute',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                }}
                              >
                                <Typography variant="h5" component="div" color="text.secondary">
                                  {`${rehabProgress.completionRate}%`}
                                </Typography>
                              </Box>
                            </Box>
                            <Box ml={3}>
                              <Typography variant="body2" gutterBottom>
                                开始日期: {rehabProgress.startDate}
                              </Typography>
                              <Typography variant="body2" gutterBottom>
                                当前周期: 第 {rehabProgress.currentWeek} 周 / 共 {rehabProgress.totalWeeks} 周
                              </Typography>
                              <Typography variant="body2">
                                下次复诊: {rehabProgress.nextAppointment}
                              </Typography>
                            </Box>
                          </Box>
                        </Box>
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                          每周训练完成率
                        </Typography>
                        <Box sx={{ height: 150 }}>
                          <LineChartPlaceholder 
                            title="每周训练完成率" 
                            data={rehabProgress.weeklyExercises.map((w: any) => w.completed)} 
                          />
                        </Box>
                      </Grid>
                    </Grid>
                  </Paper>
                </Grid>
                
                {/* 康复关键指标 */}
                <Grid item xs={12}>
                  <Paper sx={{ p: 3 }}>
                    <Typography variant="h6" gutterBottom>康复关键指标</Typography>
                    <Grid container spacing={3}>
                      <Grid item xs={12} md={4}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                              疼痛等级 (0-10)
                            </Typography>
                            <Box sx={{ width: '100%', mb: 1 }}>
                              <LinearProgress 
                                variant="determinate" 
                                value={(rehabProgress.painLevel.current / 10) * 100} 
                                color={rehabProgress.painLevel.current <= 3 ? "success" : 
                                      rehabProgress.painLevel.current <= 6 ? "warning" : "error"}
                                sx={{ height: 10, borderRadius: 5 }}
                              />
                            </Box>
                            <Box display="flex" justifyContent="space-between">
                              <Typography variant="body2">
                                初始值: {rehabProgress.painLevel.initial}
                              </Typography>
                              <Typography variant="body2" fontWeight="bold">
                                当前值: {rehabProgress.painLevel.current}
                              </Typography>
                              <Typography variant="body2">
                                目标值: {rehabProgress.painLevel.target}
                              </Typography>
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                      
                      <Grid item xs={12} md={4}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                              关节活动度 (%)
                            </Typography>
                            <Box sx={{ width: '100%', mb: 1 }}>
                              <LinearProgress 
                                variant="determinate" 
                                value={rehabProgress.mobility.current} 
                                color="primary"
                                sx={{ height: 10, borderRadius: 5 }}
                              />
                            </Box>
                            <Box display="flex" justifyContent="space-between">
                              <Typography variant="body2">
                                初始值: {rehabProgress.mobility.initial}%
                              </Typography>
                              <Typography variant="body2" fontWeight="bold">
                                当前值: {rehabProgress.mobility.current}%
                              </Typography>
                              <Typography variant="body2">
                                目标值: {rehabProgress.mobility.target}%
                              </Typography>
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                      
                      <Grid item xs={12} md={4}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                              肌肉力量 (%)
                            </Typography>
                            <Box sx={{ width: '100%', mb: 1 }}>
                              <LinearProgress 
                                variant="determinate" 
                                value={rehabProgress.strength.current} 
                                color="primary"
                                sx={{ height: 10, borderRadius: 5 }}
                              />
                            </Box>
                            <Box display="flex" justifyContent="space-between">
                              <Typography variant="body2">
                                初始值: {rehabProgress.strength.initial}%
                              </Typography>
                              <Typography variant="body2" fontWeight="bold">
                                当前值: {rehabProgress.strength.current}%
                              </Typography>
                              <Typography variant="body2">
                                目标值: {rehabProgress.strength.target}%
                              </Typography>
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                    </Grid>
                  </Paper>
                </Grid>
              </Grid>
            ) : (
              <Alert severity="info">
                未找到当前患者的康复计划信息，请先选择患者或创建康复计划。
              </Alert>
            )}
          </TabPanel>
        </Box>
      )}
    </Box>
  );
};

export default DataMonitoring; 