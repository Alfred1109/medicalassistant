import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Divider,
  Grid,
  Button,
  Tabs,
  Tab,
  Chip,
  IconButton,
  Dialog,
  DialogContent,
  DialogTitle,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Stack,
  Alert,
  Snackbar
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import VisibilityIcon from '@mui/icons-material/Visibility';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import FilterListIcon from '@mui/icons-material/FilterList';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import RefreshIcon from '@mui/icons-material/Refresh';
import TimelineIcon from '@mui/icons-material/Timeline';
import { Link } from 'react-router-dom';

// 导入组件
import HealthDataForm from '../../components/HealthManager/HealthDataForm';
// 导入HealthDataVisualization组件
// 注意：如果这个组件不存在或没有默认导出，需要先创建或修复该组件
// 如果当前暂时不使用该组件，可以暂时注释这行导入
// import HealthDataVisualization from '../../components/HealthManager/HealthDataVisualization';
import HealthDataVisualization from '../../components/HealthManager/HealthDataVisualization';

// 健康数据记录类型定义
interface HealthDataRecord {
  id: string;
  patient_id: string;
  patient_name?: string;
  data_type: string;
  value: string | number;
  unit: string;
  measured_at: string;
  device?: string;
  additional_info: {
    systolic?: number;
    diastolic?: number;
    [key: string]: any;
  };
  tags?: string[];
  notes?: string;
  recorded_by?: string;
  created_at: string;
  updated_at: string;
}

// 模拟数据
const mockHealthData: HealthDataRecord[] = [
  {
    id: '1',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'blood_pressure',
    value: '120/80',
    unit: 'mmHg',
    measured_at: '2023-04-20T09:15:00Z',
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
    created_at: '2023-04-20T09:20:00Z',
    updated_at: '2023-04-20T09:20:00Z'
  },
  {
    id: '2',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'blood_glucose',
    value: '5.6',
    unit: 'mmol/L',
    measured_at: '2023-04-20T12:30:00Z',
    device: 'Accu-Chek Active',
    additional_info: {
      timing: 'after_meal',
      meal_type: 'lunch'
    },
    tags: ['餐后2小时'],
    notes: '午餐后测量',
    recorded_by: 'user1',
    created_at: '2023-04-20T12:35:00Z',
    updated_at: '2023-04-20T12:35:00Z'
  },
  {
    id: '3',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'heart_rate',
    value: '72',
    unit: 'bpm',
    measured_at: '2023-04-20T15:45:00Z',
    device: 'Apple Watch Series 7',
    additional_info: {
      activity: 'resting'
    },
    tags: ['静息'],
    notes: '下午休息时测量',
    recorded_by: 'user1',
    created_at: '2023-04-20T15:50:00Z',
    updated_at: '2023-04-20T15:50:00Z'
  },
  {
    id: '4',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'body_temperature',
    value: '36.5',
    unit: '°C',
    measured_at: '2023-04-20T18:00:00Z',
    device: 'Braun ThermoScan 7',
    additional_info: {
      method: 'oral'
    },
    tags: ['日常检查'],
    notes: '晚餐前测量',
    recorded_by: 'user1',
    created_at: '2023-04-20T18:05:00Z',
    updated_at: '2023-04-20T18:05:00Z'
  },
  {
    id: '5',
    patient_id: '1001',
    patient_name: '张三',
    data_type: 'weight',
    value: '70.5',
    unit: 'kg',
    measured_at: '2023-04-21T07:00:00Z',
    device: 'Xiaomi Smart Scale',
    additional_info: {},
    tags: ['晨检'],
    notes: '晨起测量',
    recorded_by: 'user1',
    created_at: '2023-04-21T07:05:00Z',
    updated_at: '2023-04-21T07:05:00Z'
  }
];

// 数据类型映射
const dataTypeMap: Record<string, string> = {
  blood_pressure: '血压',
  blood_glucose: '血糖',
  heart_rate: '心率',
  body_temperature: '体温',
  weight: '体重',
  height: '身高',
  sleep: '睡眠',
  step_count: '步数',
  blood_oxygen: '血氧',
  respiratory_rate: '呼吸频率'
};

// 标签页容器组件
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`health-data-tab-${index}`}
      aria-labelledby={`health-data-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

// 过滤器接口
interface FilterOptions {
  patient_id?: string;
  data_type?: string;
  date_from?: string;
  date_to?: string;
  tags?: string[];
}

// 健康数据管理页面组件
const HealthDataManagement = () => {
  // 状态
  const [tabValue, setTabValue] = React.useState(0);
  const [healthData, setHealthData] = React.useState<HealthDataRecord[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [filters, setFilters] = React.useState<FilterOptions>({});
  const [showForm, setShowForm] = React.useState(false);
  const [currentData, setCurrentData] = React.useState<HealthDataRecord | null>(null);
  const [formMode, setFormMode] = React.useState<'create' | 'edit'>('create');
  const [showFilterDialog, setShowFilterDialog] = React.useState(false);
  const [selectedPatientId, setSelectedPatientId] = React.useState<string>('1001'); // 默认患者ID
  const [snackbar, setSnackbar] = React.useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });
  
  // 加载健康数据
  React.useEffect(() => {
    loadHealthData();
  }, [filters, selectedPatientId]);
  
  // 加载健康数据
  const loadHealthData = async () => {
    try {
      setLoading(true);
      
      // 模拟API延迟
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // 模拟过滤
      let filteredData = [...mockHealthData];
      
      // 按患者ID过滤
      if (selectedPatientId) {
        filteredData = filteredData.filter(item => item.patient_id === selectedPatientId);
      }
      
      // 按数据类型过滤
      if (filters.data_type) {
        filteredData = filteredData.filter(item => item.data_type === filters.data_type);
      }
      
      // 按日期范围过滤
      if (filters.date_from) {
        const fromDate = new Date(filters.date_from);
        filteredData = filteredData.filter(item => new Date(item.measured_at) >= fromDate);
      }
      
      if (filters.date_to) {
        const toDate = new Date(filters.date_to);
        filteredData = filteredData.filter(item => new Date(item.measured_at) <= toDate);
      }
      
      // 按标签过滤
      if (filters.tags && filters.tags.length > 0) {
        filteredData = filteredData.filter(item => 
          item.tags && item.tags.some((tag: string) => filters.tags?.includes(tag))
        );
      }
      
      setHealthData(filteredData);
      setError(null);
    } catch (err) {
      setError('加载健康数据失败');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理标签页变更
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };
  
  // 处理添加健康数据
  const handleAddHealthData = () => {
    setCurrentData(null);
    setFormMode('create');
    setShowForm(true);
  };
  
  // 处理编辑健康数据
  const handleEditHealthData = (id: string) => {
    const data = healthData.find(item => item.id === id);
    if (data) {
      setCurrentData(data);
      setFormMode('edit');
      setShowForm(true);
    }
  };
  
  // 处理删除健康数据
  const handleDeleteHealthData = async (id: string) => {
    try {
      setLoading(true);
      
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // 更新本地数据
      setHealthData((prev: HealthDataRecord[]) => prev.filter(item => item.id !== id));
      
      // 显示成功消息
      setSnackbar({
        open: true,
        message: '健康数据删除成功',
        severity: 'success'
      });
    } catch (err) {
      setSnackbar({
        open: true,
        message: '删除失败',
        severity: 'error'
      });
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理表单提交
  const handleFormSubmit = async (data: any) => {
    try {
      setLoading(true);
      
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 500));
      
      if (formMode === 'create') {
        // 创建新数据
        const newData: HealthDataRecord = {
          id: `${Date.now()}`, // 模拟ID生成
          patient_id: selectedPatientId,
          patient_name: '张三', // 硬编码演示用
          ...data,
          recorded_by: 'current_user', // 模拟当前用户
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        };
        
        // 更新本地数据
        setHealthData((prev: HealthDataRecord[]) => [newData, ...prev]);
        
        // 显示成功消息
        setSnackbar({
          open: true,
          message: '健康数据添加成功',
          severity: 'success'
        });
      } else if (currentData) {
        // 更新数据
        setHealthData((prev: HealthDataRecord[]) => 
          prev.map((item: HealthDataRecord) => 
            item.id === currentData.id 
              ? { 
                  ...item, 
                  ...data,
                  updated_at: new Date().toISOString()
                } 
              : item
          )
        );
        
        // 显示成功消息
        setSnackbar({
          open: true,
          message: '健康数据更新成功',
          severity: 'success'
        });
      }
      
      // 关闭表单
      setShowForm(false);
    } catch (err) {
      setSnackbar({
        open: true,
        message: '操作失败',
        severity: 'error'
      });
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理过滤对话框打开
  const handleOpenFilterDialog = () => {
    setShowFilterDialog(true);
  };
  
  // 处理过滤对话框关闭
  const handleCloseFilterDialog = () => {
    setShowFilterDialog(false);
  };
  
  // 应用过滤器
  const handleApplyFilters = (newFilters: FilterOptions) => {
    setFilters(newFilters);
    setShowFilterDialog(false);
  };
  
  // 重置过滤器
  const handleResetFilters = () => {
    setFilters({});
  };
  
  // 格式化日期
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };
  
  // 关闭提示消息
  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };
  
  // 将健康数据转换为可视化组件需要的格式
  const getChartData = () => {
    // 转换为可视化组件所需的数据格式
    return healthData.map(item => ({
      id: item.id,
      data_type: 'vital_sign',
      data: {
        vital_type: item.data_type,
        value: item.data_type === 'blood_pressure' 
          ? { systolic: item.additional_info.systolic, diastolic: item.additional_info.diastolic } 
          : item.value,
        unit: item.unit
      },
      recorded_at: item.measured_at,
      source: item.device
    }));
  };
  
  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        健康数据管理
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        管理患者的健康指标数据，记录和追踪各项健康指标变化。
      </Typography>
      <Divider sx={{ mb: 3 }} />
      
      {/* 功能按钮 */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between' }}>
        <Stack direction="row" spacing={2}>
          <Button 
            variant="contained" 
            startIcon={<AddIcon />}
            onClick={handleAddHealthData}
          >
            添加健康数据
          </Button>
          <Button 
            variant="outlined" 
            startIcon={<FilterListIcon />}
            onClick={handleOpenFilterDialog}
          >
            过滤器
          </Button>
          {Object.keys(filters).length > 0 && (
            <Button 
              variant="text" 
              onClick={handleResetFilters}
            >
              重置过滤器
            </Button>
          )}
        </Stack>
        <Stack direction="row" spacing={2}>
          <Button 
            variant="outlined"
            startIcon={<TimelineIcon />}
            component={Link}
            to={`/health-manager/health-data-timeline/${selectedPatientId}`}
          >
            查看时间线
          </Button>
          <IconButton onClick={loadHealthData} disabled={loading}>
            <RefreshIcon />
          </IconButton>
        </Stack>
      </Box>
      
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>
      )}
      
      {/* 内容标签页 */}
      <Box sx={{ width: '100%' }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs 
            value={tabValue} 
            onChange={handleTabChange} 
            aria-label="健康数据标签页"
          >
            <Tab label="数据列表" />
            <Tab label="趋势图表" />
          </Tabs>
        </Box>
        
        {/* 数据列表标签页 */}
        <TabPanel value={tabValue} index={0}>
          {showForm ? (
            <HealthDataForm
              initialData={currentData || undefined}
              onSubmit={handleFormSubmit}
              onCancel={() => setShowForm(false)}
              patientId={selectedPatientId}
            />
          ) : (
            <Paper elevation={1}>
              <Box p={3}>
                {loading ? (
                  <Typography align="center">加载中...</Typography>
                ) : healthData.length === 0 ? (
                  <Typography align="center">暂无健康数据记录</Typography>
                ) : (
                  <Grid container spacing={2}>
                    {healthData.map(item => (
                      <Grid item xs={12} md={6} lg={4} key={item.id}>
                        <Paper 
                          variant="outlined" 
                          sx={{ 
                            p: 2, 
                            position: 'relative',
                            transition: 'all 0.2s',
                            '&:hover': { 
                              boxShadow: 3 
                            }
                          }}
                        >
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                            <Chip 
                              label={dataTypeMap[item.data_type] || item.data_type} 
                              color="primary" 
                              size="small" 
                              sx={{ mb: 1 }}
                            />
                            <Box>
                              <IconButton 
                                size="small" 
                                onClick={() => handleEditHealthData(item.id)}
                              >
                                <EditIcon fontSize="small" />
                              </IconButton>
                              <IconButton 
                                size="small" 
                                onClick={() => handleDeleteHealthData(item.id)} 
                                color="error"
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </Box>
                          </Box>
                          
                          <Typography variant="h6" sx={{ mb: 0.5 }}>
                            {item.data_type === 'blood_pressure' 
                              ? `${item.additional_info.systolic}/${item.additional_info.diastolic} ${item.unit}`
                              : `${item.value} ${item.unit}`}
                          </Typography>
                          
                          <Typography variant="body2" color="text.secondary" gutterBottom>
                            测量时间: {formatDate(item.measured_at)}
                          </Typography>
                          
                          {item.device && (
                            <Typography variant="body2" color="text.secondary" gutterBottom>
                              设备: {item.device}
                            </Typography>
                          )}
                          
                          {item.tags && item.tags.length > 0 && (
                            <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                              {item.tags.map((tag: string, index: number) => (
                                <Chip 
                                  key={index} 
                                  label={tag} 
                                  size="small" 
                                  variant="outlined"
                                />
                              ))}
                            </Box>
                          )}
                          
                          {item.notes && (
                            <Typography variant="body2" sx={{ mt: 1 }}>
                              备注: {item.notes}
                            </Typography>
                          )}
                        </Paper>
                      </Grid>
                    ))}
                  </Grid>
                )}
              </Box>
            </Paper>
          )}
        </TabPanel>
        
        {/* 趋势图表标签页 */}
        <TabPanel value={tabValue} index={1}>
          {/* 暂时注释掉HealthDataVisualization组件，因为可能不存在或没有默认导出 */}
          {/* <HealthDataVisualization 
            data={getChartData()} 
            loading={loading}
            error={error || undefined}
            height={500}
            onTimeRangeChange={() => {}}
          /> */}
          <HealthDataVisualization 
            data={getChartData()} 
            loading={loading}
            error={error || undefined}
            height={500}
            onTimeRangeChange={() => {}}
          />
        </TabPanel>
      </Box>
      
      {/* 过滤器对话框 */}
      <Dialog open={showFilterDialog} onClose={handleCloseFilterDialog} maxWidth="sm" fullWidth>
        <DialogTitle>过滤健康数据</DialogTitle>
        <DialogContent>
          <Box component="form" sx={{ pt: 1 }}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControl fullWidth margin="normal">
                  <InputLabel>数据类型</InputLabel>
                  <Select
                    value={filters.data_type || ''}
                    label="数据类型"
                    onChange={(e: React.ChangeEvent<{ value: unknown }>) => setFilters({ ...filters, data_type: e.target.value as string })}
                  >
                    <MenuItem value="">全部类型</MenuItem>
                    {Object.entries(dataTypeMap).map(([value, label]) => (
                      <MenuItem key={value} value={value}>{label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="开始日期"
                  type="date"
                  margin="normal"
                  value={filters.date_from || ''}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilters({ ...filters, date_from: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>
              
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="结束日期"
                  type="date"
                  margin="normal"
                  value={filters.date_to || ''}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilters({ ...filters, date_to: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="标签（用逗号分隔）"
                  margin="normal"
                  value={(filters.tags || []).join(',')}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilters({ ...filters, tags: e.target.value ? e.target.value.split(',') : [] })}
                  helperText="多个标签请用英文逗号分隔"
                />
              </Grid>
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseFilterDialog}>取消</Button>
          <Button onClick={() => handleApplyFilters(filters)} variant="contained">
            应用过滤器
          </Button>
        </DialogActions>
      </Dialog>
      
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

export default HealthDataManagement; 