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
  Snackbar,
  SelectChangeEvent,
  CircularProgress,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import FilterListIcon from '@mui/icons-material/FilterList';
import RefreshIcon from '@mui/icons-material/Refresh';
import TimelineIcon from '@mui/icons-material/Timeline';
import { Link, useParams, useSearchParams } from 'react-router-dom';

// 导入HealthDataVisualization组件
import HealthDataVisualization from '../../components/HealthManager/HealthDataVisualization';
import { apiService } from '../../services/api';
import api from '../../services/api';

// 健康数据记录类型（对应后端 HealthDataResponse：
// patient_id / data_type / data_content / source / recorded_by / recorded_at / metadata）
interface HealthDataRecord {
  id: string;
  patient_id: string;
  data_type: string;
  data_content: {
    value?: string | number | { systolic?: number; diastolic?: number; [key: string]: any };
    unit?: string;
    notes?: string;
    [key: string]: any;
  };
  source?: string;
  recorded_by?: string;
  recorded_at: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, any>;
}

// 数据类型映射（语义类型，对应 data_type / data_content.type）
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

// 数据来源映射（后端 source：manual/device/app/integration）
const sourceMap: Record<string, string> = {
  manual: '手动录入',
  device: '设备采集',
  app: '应用程序',
  integration: '外部系统'
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

// 过滤器接口（与后端 GET /health-records/health-data 查询参数对应；
// 后端不支持按标签过滤，故不含 tags）
interface FilterOptions {
  data_type?: string;
  date_from?: string;
  date_to?: string;
}

// 健康数据管理页面组件
const HealthDataManagement = () => {
  // 患者ID：路由参数 /patientId 优先，其次查询串 ?patientId=，均缺失时要求用户指定
  const { patientId: routePatientId } = useParams<{ patientId?: string }>();
  const [searchParams] = useSearchParams();
  const patientId = routePatientId || searchParams.get('patientId') || '';

  // 状态
  const [tabValue, setTabValue] = React.useState(0);
  const [healthData, setHealthData] = React.useState<HealthDataRecord[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [filters, setFilters] = React.useState<FilterOptions>({});
  const [showCreateDialog, setShowCreateDialog] = React.useState(false);
  const [showFilterDialog, setShowFilterDialog] = React.useState(false);
  const [snackbar, setSnackbar] = React.useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });

  // 新建表单（受控），对应后端 HealthDataCreate：
  // patient_id / data_type / data_content{value,unit,notes} / source / recorded_at；
  // recorded_by 由后端从当前登录用户写入，前端不伪造
  const [formData, setFormData] = React.useState({
    data_type: 'blood_pressure',
    value: '',
    unit: '',
    notes: '',
    source: 'manual',
    recorded_at: ''
  });
  const [formError, setFormError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  // 加载健康数据（真实接口：GET /health-records/health-data?patient_id=...）
  const loadHealthData = async () => {
    if (!patientId) return;
    try {
      setLoading(true);
      const response = await apiService.getHealthData(patientId, {
        data_type: filters.data_type || undefined,
        start_date: filters.date_from || undefined,
        end_date: filters.date_to || undefined,
      });
      setHealthData(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载健康数据失败');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    loadHealthData();
  }, [patientId, filters]);

  // 处理标签页变更
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // 处理添加健康数据
  const handleAddHealthData = () => {
    setFormData({
      data_type: 'blood_pressure',
      value: '',
      unit: 'mmHg',
      notes: '',
      source: 'manual',
      recorded_at: ''
    });
    setFormError(null);
    setShowCreateDialog(true);
  };

  // 处理新建表单提交（真实接口：POST /health-records/health-data）
  const handleFormSubmit = async () => {
    if (!patientId) return;
    if (!formData.value.trim()) {
      setFormError('请填写测量数值');
      return;
    }
    try {
      setSubmitting(true);
      setFormError(null);
      // 血压按 "收缩压/舒张压" 拆分为结构化数据，其余存为数值/文本
      const data_content: HealthDataRecord['data_content'] =
        formData.data_type === 'blood_pressure'
          ? (() => {
              const [systolic, diastolic] = formData.value.split('/').map(s => Number(s.trim()));
              return {
                value: { systolic, diastolic },
                unit: formData.unit || undefined,
                notes: formData.notes || undefined,
              };
            })()
          : {
              value: formData.value.trim(),
              unit: formData.unit || undefined,
              notes: formData.notes || undefined,
            };

      await api.post('/health-records/health-data', {
        patient_id: patientId,
        data_type: formData.data_type,
        data_content,
        source: formData.source,
        recorded_at: formData.recorded_at || undefined,
      });

      setShowCreateDialog(false);
      setSnackbar({
        open: true,
        message: '健康数据添加成功',
        severity: 'success'
      });
      loadHealthData();
    } catch (err: any) {
      setFormError(err.response?.data?.detail || '添加健康数据失败');
      console.error(err);
    } finally {
      setSubmitting(false);
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
    if (isNaN(date.getTime())) return dateString;
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

  // 展示用语义类型：优先 data_content.type（后端生命体征工厂的写法），退回 data_type
  const displayType = (item: HealthDataRecord): string => {
    const type = (item.data_content && item.data_content.type) || item.data_type;
    return dataTypeMap[type] || type;
  };

  // 展示用数值：血压为 {systolic, diastolic} 时拼为 "收缩压/舒张压"
  const displayValue = (item: HealthDataRecord): string => {
    const value = item.data_content?.value;
    if (value && typeof value === 'object') {
      const bp = value as { systolic?: number; diastolic?: number };
      if (bp.systolic != null && bp.diastolic != null) {
        return `${bp.systolic}/${bp.diastolic}`;
      }
      return JSON.stringify(value);
    }
    return value != null ? String(value) : '-';
  };

  // 将健康数据转换为可视化组件需要的格式
  const getChartData = () => {
    // 转换为可视化组件所需的数据格式
    return healthData.map(item => {
      const value = item.data_content?.value;
      return {
        id: item.id,
        data_type: item.data_type,
        data: {
          vital_type: item.data_type,
          value: value,
          unit: item.data_content?.unit
        },
        recorded_at: item.recorded_at,
        source: item.source
      };
    });
  };

  // 未指定患者时的诚实提示（后端接口要求必填 patient_id，且无患者列表接口可默认）
  if (!patientId) {
    return (
      <Box>
        <Typography variant="h5" gutterBottom>
          健康数据管理
        </Typography>
        <Divider sx={{ mb: 3 }} />
        <Alert severity="info">
          请先指定患者（通过患者列表进入，或在地址后附加 ?patientId=患者ID）后查看健康数据。本页面不预设默认患者。
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        健康数据管理
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        管理患者（ID: {patientId}）的健康指标数据，记录和追踪各项健康指标变化。
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
            to={`/app/health-manager/health-data-timeline/${patientId}`}
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
          <Paper elevation={1}>
            <Box p={3}>
              {loading ? (
                <Typography align="center">
                  <CircularProgress size={20} sx={{ mr: 1, verticalAlign: 'middle' }} />
                  加载中...
                </Typography>
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
                            label={displayType(item)}
                            color="primary"
                            size="small"
                            sx={{ mb: 1 }}
                          />
                        </Box>

                        <Typography variant="h6" sx={{ mb: 0.5 }}>
                          {displayValue(item)}
                          {item.data_content?.unit ? ` ${item.data_content.unit}` : ''}
                        </Typography>

                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          测量时间: {formatDate(item.recorded_at)}
                        </Typography>

                        {item.source && (
                          <Typography variant="body2" color="text.secondary" gutterBottom>
                            来源: {sourceMap[item.source] || item.source}
                          </Typography>
                        )}

                        {item.recorded_by && (
                          <Typography variant="body2" color="text.secondary" gutterBottom>
                            记录人ID: {item.recorded_by}
                          </Typography>
                        )}

                        {item.data_content?.notes && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            备注: {item.data_content.notes}
                          </Typography>
                        )}
                      </Paper>
                    </Grid>
                  ))}
                </Grid>
              )}
            </Box>
          </Paper>
        </TabPanel>

        {/* 趋势图表标签页 */}
        <TabPanel value={tabValue} index={1}>
          <HealthDataVisualization
            data={getChartData()}
            loading={loading}
            error={error || undefined}
            height={500}
            onTimeRangeChange={() => {}}
          />
        </TabPanel>
      </Box>

      {/* 新建健康数据对话框（真实接口 POST /health-records/health-data）。
          后端无单条健康数据的 PUT/DELETE 接口，故不提供编辑/删除操作。 */}
      <Dialog open={showCreateDialog} onClose={() => setShowCreateDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>添加健康数据</DialogTitle>
        <DialogContent>
          <Box component="form" sx={{ pt: 1 }} onSubmit={(e) => { e.preventDefault(); handleFormSubmit(); }}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth margin="normal">
                  <InputLabel>数据类型</InputLabel>
                  <Select
                    value={formData.data_type}
                    label="数据类型"
                    onChange={(e: SelectChangeEvent<string>) => {
                      const dataType = e.target.value as string;
                      const defaultUnit: Record<string, string> = {
                        blood_pressure: 'mmHg',
                        blood_glucose: 'mmol/L',
                        heart_rate: 'bpm',
                        body_temperature: '°C',
                        weight: 'kg',
                        height: 'cm',
                        blood_oxygen: '%',
                        respiratory_rate: '次/分',
                        step_count: '步',
                      };
                      setFormData({ ...formData, data_type: dataType, unit: defaultUnit[dataType] || '' });
                    }}
                  >
                    {Object.entries(dataTypeMap).map(([value, label]) => (
                      <MenuItem key={value} value={value}>{label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  label={formData.data_type === 'blood_pressure' ? '血压（收缩压/舒张压）' : '测量数值'}
                  placeholder={formData.data_type === 'blood_pressure' ? '120/80' : ''}
                  margin="normal"
                  value={formData.value}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, value: e.target.value })}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="单位"
                  margin="normal"
                  value={formData.unit}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, unit: e.target.value })}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <FormControl fullWidth margin="normal">
                  <InputLabel>数据来源</InputLabel>
                  <Select
                    value={formData.source}
                    label="数据来源"
                    onChange={(e: SelectChangeEvent<string>) => setFormData({ ...formData, source: e.target.value as string })}
                  >
                    {Object.entries(sourceMap).map(([value, label]) => (
                      <MenuItem key={value} value={value}>{label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>

              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="测量时间（留空则使用当前时间）"
                  type="datetime-local"
                  margin="normal"
                  value={formData.recorded_at}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, recorded_at: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>

              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="备注"
                  multiline
                  rows={2}
                  margin="normal"
                  value={formData.notes}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, notes: e.target.value })}
                />
              </Grid>

              {formError && (
                <Grid item xs={12}>
                  <Alert severity="error">{formError}</Alert>
                </Grid>
              )}
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowCreateDialog(false)}>取消</Button>
          <Button onClick={handleFormSubmit} variant="contained" color="primary" disabled={submitting}>
            {submitting ? '保存中...' : '保存'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 过滤器对话框（数据类型/日期范围对应后端查询参数；标签过滤后端不支持，已移除） */}
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
                    onChange={(e: SelectChangeEvent<string>) => setFilters({ ...filters, data_type: e.target.value as string })}
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
