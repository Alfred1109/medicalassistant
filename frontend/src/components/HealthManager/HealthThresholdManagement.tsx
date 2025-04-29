import * as React from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select, { SelectChangeEvent } from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import FormHelperText from '@mui/material/FormHelperText';
import Grid from '@mui/material/Grid';
import Divider from '@mui/material/Divider';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import Snackbar from '@mui/material/Snackbar';
import TablePagination from '@mui/material/TablePagination';
import Tooltip from '@mui/material/Tooltip';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import InfoIcon from '@mui/icons-material/Info';
import WarningIcon from '@mui/icons-material/Warning';
import ErrorIcon from '@mui/icons-material/Error';
import axios from 'axios';

// API基础URL
const API_BASE_URL = 'http://localhost:8000';

// 健康数据阈值接口
interface HealthDataThreshold {
  id: string;
  name: string;
  description?: string;
  data_type: string;
  vital_type?: string;
  test_name?: string;
  patient_id?: string;
  normal_range: {
    min?: number;
    max?: number;
  };
  warning_range: {
    min?: number;
    max?: number;
  };
  critical_range: {
    min?: number;
    max?: number;
  };
  unit?: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

// 新建或更新阈值的接口
interface ThresholdFormData {
  name: string;
  description?: string;
  data_type: string;
  vital_type?: string;
  test_name?: string;
  patient_id?: string;
  normal_range: {
    min?: number | string;
    max?: number | string;
  };
  warning_range: {
    min?: number | string;
    max?: number | string;
  };
  critical_range: {
    min?: number | string;
    max?: number | string;
  };
  unit?: string;
  is_active: boolean;
}

// 初始表单数据
const initialFormData: ThresholdFormData = {
  name: '',
  description: '',
  data_type: 'vital_signs', // 默认为生命体征类型
  vital_type: '',
  test_name: '',
  patient_id: '',
  normal_range: {
    min: '',
    max: ''
  },
  warning_range: {
    min: '',
    max: ''
  },
  critical_range: {
    min: '',
    max: ''
  },
  unit: '',
  is_active: true
};

// 数据类型选项
const dataTypeOptions = [
  { value: 'vital_signs', label: '生命体征' },
  { value: 'lab_results', label: '检验结果' }
];

// 生命体征类型选项
const vitalTypeOptions = [
  { value: 'blood_pressure', label: '血压' },
  { value: 'heart_rate', label: '心率' },
  { value: 'blood_glucose', label: '血糖' },
  { value: 'body_temperature', label: '体温' },
  { value: 'weight', label: '体重' },
  { value: 'height', label: '身高' },
  { value: 'oxygen_saturation', label: '血氧饱和度' },
  { value: 'respiratory_rate', label: '呼吸频率' },
  { value: 'step_count', label: '步数' }
];

// 健康数据阈值管理组件属性
interface HealthThresholdManagementProps {
  patientId?: string; // 可选的患者ID，如果提供则只显示该患者的阈值
}

// 健康数据阈值管理组件
const HealthThresholdManagement = ({ patientId }: HealthThresholdManagementProps) => {
  // 阈值列表
  const [thresholds, setThresholds] = React.useState<HealthDataThreshold[]>([]);
  // 加载状态
  const [loading, setLoading] = React.useState<boolean>(false);
  // 错误信息
  const [error, setError] = React.useState<string | null>(null);
  // 对话框状态
  const [dialogOpen, setDialogOpen] = React.useState<boolean>(false);
  // 确认删除对话框状态
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState<boolean>(false);
  // 当前编辑的阈值ID
  const [currentThresholdId, setCurrentThresholdId] = React.useState<string | null>(null);
  // 表单数据
  const [formData, setFormData] = React.useState<ThresholdFormData>(initialFormData);
  // 表单验证错误
  const [formErrors, setFormErrors] = React.useState<Record<string, string>>({});
  // 提示消息
  const [snackbar, setSnackbar] = React.useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });
  // 分页
  const [page, setPage] = React.useState(0);
  const [rowsPerPage, setRowsPerPage] = React.useState(10);

  // 加载阈值数据
  React.useEffect(() => {
    loadThresholds();
  }, [patientId]);

  // 加载阈值列表
  const loadThresholds = async () => {
    try {
      setLoading(true);
      setError(null);

      // 构建查询参数
      let url = `${API_BASE_URL}/api/health/alerts/thresholds`;
      if (patientId) {
        url += `?patient_id=${patientId}`;
      }

      // 调用API获取阈值列表
      const response = await axios.get(url);
      setThresholds(response.data);
    } catch (err) {
      console.error('加载健康数据阈值失败:', err);
      setError('加载健康数据阈值失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  // 处理表单输入变化
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | { name?: string; value: unknown }>) => {
    const { name, value } = e.target;
    
    if (!name) return;

    // 处理嵌套对象的字段
    if (name.includes('.')) {
      const [parent, child] = name.split('.');
      setFormData((prev: any) => ({
        ...prev,
        [parent]: {
          ...prev[parent],
          [child]: value
        }
      }));
    } else {
      setFormData((prev: any) => ({ ...prev, [name]: value }));
    }

    // 清除相关字段的错误
    if (formErrors[name]) {
      setFormErrors((prev: any) => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  // 处理数据类型变化
  const handleDataTypeChange = (e: SelectChangeEvent<string>) => {
    const value = e.target.value;
    
    // 重置相关字段
    setFormData((prev: any) => ({
      ...prev,
      data_type: value,
      vital_type: value === 'vital_signs' ? prev.vital_type : '',
      test_name: value === 'lab_results' ? prev.test_name : ''
    }));
  };

  // 验证表单
  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    // 验证必填字段
    if (!formData.name.trim()) {
      errors.name = '请输入阈值名称';
    }

    if (!formData.data_type) {
      errors.data_type = '请选择数据类型';
    }

    // 验证生命体征类型或检测名称
    if (formData.data_type === 'vital_signs' && !formData.vital_type) {
      errors['vital_type'] = '请选择生命体征类型';
    } else if (formData.data_type === 'lab_results' && !formData.test_name?.trim()) {
      errors['test_name'] = '请输入检测名称';
    }

    // 验证阈值范围
    if (
      !formData.normal_range.min && 
      !formData.normal_range.max && 
      !formData.warning_range.min && 
      !formData.warning_range.max &&
      !formData.critical_range.min && 
      !formData.critical_range.max
    ) {
      errors['ranges'] = '请至少设置一个阈值范围';
    }

    // 验证单位
    if (!formData.unit?.trim()) {
      errors.unit = '请输入单位';
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // 处理表单提交
  const handleSubmit = async () => {
    if (!validateForm()) {
      return;
    }

    try {
      setLoading(true);

      // 准备提交数据，转换数字字段
      const submitData = {
        ...formData,
        normal_range: {
          min: formData.normal_range.min !== '' ? Number(formData.normal_range.min) : undefined,
          max: formData.normal_range.max !== '' ? Number(formData.normal_range.max) : undefined
        },
        warning_range: {
          min: formData.warning_range.min !== '' ? Number(formData.warning_range.min) : undefined,
          max: formData.warning_range.max !== '' ? Number(formData.warning_range.max) : undefined
        },
        critical_range: {
          min: formData.critical_range.min !== '' ? Number(formData.critical_range.min) : undefined,
          max: formData.critical_range.max !== '' ? Number(formData.critical_range.max) : undefined
        }
      };

      // 清理不需要的字段
      if (formData.data_type === 'vital_signs') {
        delete submitData.test_name;
      } else {
        delete submitData.vital_type;
      }

      if (!patientId && !formData.patient_id) {
        delete submitData.patient_id;
      } else if (patientId) {
        submitData.patient_id = patientId;
      }

      let response;
      if (currentThresholdId) {
        // 更新现有阈值
        response = await axios.put(
          `${API_BASE_URL}/api/health/alerts/thresholds/${currentThresholdId}`,
          submitData
        );
        setSnackbar({
          open: true,
          message: '已成功更新健康数据阈值',
          severity: 'success'
        });
      } else {
        // 创建新阈值
        response = await axios.post(
          `${API_BASE_URL}/api/health/alerts/thresholds`,
          submitData
        );
        setSnackbar({
          open: true,
          message: '已成功创建健康数据阈值',
          severity: 'success'
        });
      }

      // 关闭对话框并重新加载数据
      setDialogOpen(false);
      loadThresholds();
    } catch (err: any) {
      console.error('保存健康数据阈值失败:', err);
      setSnackbar({
        open: true,
        message: `保存健康数据阈值失败: ${err.response?.data?.detail || err.message}`,
        severity: 'error'
      });
    } finally {
      setLoading(false);
    }
  };

  // 处理新建阈值
  const handleAddThreshold = () => {
    setCurrentThresholdId(null);
    setFormData({
      ...initialFormData,
      patient_id: patientId || ''
    });
    setFormErrors({});
    setDialogOpen(true);
  };

  // 处理编辑阈值
  const handleEditThreshold = async (id: string) => {
    try {
      setLoading(true);
      
      // 获取阈值详情
      const response = await axios.get(`${API_BASE_URL}/api/health/alerts/thresholds/${id}`);
      const threshold = response.data;
      
      // 转换为表单数据格式
      setFormData({
        name: threshold.name,
        description: threshold.description || '',
        data_type: threshold.data_type,
        vital_type: threshold.vital_type || '',
        test_name: threshold.test_name || '',
        patient_id: threshold.patient_id || '',
        normal_range: {
          min: threshold.normal_range?.min !== undefined ? String(threshold.normal_range.min) : '',
          max: threshold.normal_range?.max !== undefined ? String(threshold.normal_range.max) : ''
        },
        warning_range: {
          min: threshold.warning_range?.min !== undefined ? String(threshold.warning_range.min) : '',
          max: threshold.warning_range?.max !== undefined ? String(threshold.warning_range.max) : ''
        },
        critical_range: {
          min: threshold.critical_range?.min !== undefined ? String(threshold.critical_range.min) : '',
          max: threshold.critical_range?.max !== undefined ? String(threshold.critical_range.max) : ''
        },
        unit: threshold.unit || '',
        is_active: threshold.is_active
      });
      
      setCurrentThresholdId(id);
      setFormErrors({});
      setDialogOpen(true);
    } catch (err) {
      console.error('获取阈值详情失败:', err);
      setSnackbar({
        open: true,
        message: '获取阈值详情失败，请稍后重试',
        severity: 'error'
      });
    } finally {
      setLoading(false);
    }
  };

  // 处理删除阈值确认
  const handleDeleteConfirm = () => {
    if (!currentThresholdId) return;
    
    setDeleteDialogOpen(true);
  };

  // 执行删除阈值
  const handleDeleteThreshold = async () => {
    if (!currentThresholdId) return;
    
    try {
      setLoading(true);
      
      // 调用删除API
      await axios.delete(`${API_BASE_URL}/api/health/alerts/thresholds/${currentThresholdId}`);
      
      setSnackbar({
        open: true,
        message: '已成功删除健康数据阈值',
        severity: 'success'
      });
      
      // 关闭对话框并重新加载数据
      setDeleteDialogOpen(false);
      setDialogOpen(false);
      loadThresholds();
    } catch (err) {
      console.error('删除健康数据阈值失败:', err);
      setSnackbar({
        open: true,
        message: '删除健康数据阈值失败，请稍后重试',
        severity: 'error'
      });
    } finally {
      setLoading(false);
    }
  };

  // 关闭提示消息
  const handleCloseSnackbar = () => {
    setSnackbar(prev => ({ ...prev, open: false }));
  };

  // 处理分页更改
  const handleChangePage = (event: unknown, newPage: number) => {
    setPage(newPage);
  };

  // 处理每页行数更改
  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // 获取数据类型显示名称
  const getDataTypeLabel = (dataType: string): string => {
    return dataTypeOptions.find(option => option.value === dataType)?.label || dataType;
  };

  // 获取生命体征类型显示名称
  const getVitalTypeLabel = (vitalType: string): string => {
    return vitalTypeOptions.find(option => option.value === vitalType)?.label || vitalType;
  };

  // 渲染阈值详情信息
  const renderThresholdDetails = () => {
    return (
      <Box>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <TextField
              fullWidth
              required
              label="阈值名称"
              name="name"
              value={formData.name}
              onChange={handleInputChange}
              error={!!formErrors.name}
              helperText={formErrors.name}
              disabled={loading}
            />
          </Grid>
          
          <Grid item xs={12}>
            <TextField
              fullWidth
              label="描述"
              name="description"
              value={formData.description}
              onChange={handleInputChange}
              multiline
              rows={2}
              disabled={loading}
            />
          </Grid>
          
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth required error={!!formErrors.data_type}>
              <InputLabel>数据类型</InputLabel>
              <Select
                name="data_type"
                value={formData.data_type}
                onChange={handleDataTypeChange}
                label="数据类型"
                disabled={loading}
              >
                {dataTypeOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
              {formErrors.data_type && (
                <FormHelperText>{formErrors.data_type}</FormHelperText>
              )}
            </FormControl>
          </Grid>
          
          {formData.data_type === 'vital_signs' ? (
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required error={!!formErrors.vital_type}>
                <InputLabel>生命体征类型</InputLabel>
                <Select
                  name="vital_type"
                  value={formData.vital_type}
                  onChange={handleInputChange}
                  label="生命体征类型"
                  disabled={loading}
                >
                  {vitalTypeOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
                {formErrors.vital_type && (
                  <FormHelperText>{formErrors.vital_type}</FormHelperText>
                )}
              </FormControl>
            </Grid>
          ) : (
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                required
                label="检测名称"
                name="test_name"
                value={formData.test_name}
                onChange={handleInputChange}
                error={!!formErrors.test_name}
                helperText={formErrors.test_name}
                disabled={loading}
              />
            </Grid>
          )}
          
          {!patientId && (
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="患者ID"
                name="patient_id"
                value={formData.patient_id}
                onChange={handleInputChange}
                helperText="留空表示适用于所有患者的通用阈值"
                disabled={loading}
              />
            </Grid>
          )}
          
          <Grid item xs={12}>
            <TextField
              fullWidth
              required
              label="单位"
              name="unit"
              value={formData.unit}
              onChange={handleInputChange}
              error={!!formErrors.unit}
              helperText={formErrors.unit || "例如：bpm, mmHg, mg/dL等"}
              disabled={loading}
            />
          </Grid>
          
          <Grid item xs={12}>
            <Typography variant="subtitle1" gutterBottom>
              阈值范围设置
            </Typography>
            {formErrors.ranges && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {formErrors.ranges}
              </Alert>
            )}
          </Grid>
          
          <Grid item xs={12}>
            <Paper sx={{ p: 2, bgcolor: 'success.light', color: 'success.contrastText' }}>
              <Typography variant="subtitle2" gutterBottom>
                正常范围
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="最小值"
                    name="normal_range.min"
                    type="number"
                    value={formData.normal_range.min}
                    onChange={handleInputChange}
                    disabled={loading}
                    InputProps={{ inputProps: { step: 'any' } }}
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="最大值"
                    name="normal_range.max"
                    type="number"
                    value={formData.normal_range.max}
                    onChange={handleInputChange}
                    disabled={loading}
                    InputProps={{ inputProps: { step: 'any' } }}
                  />
                </Grid>
              </Grid>
            </Paper>
          </Grid>
          
          <Grid item xs={12}>
            <Paper sx={{ p: 2, bgcolor: 'warning.light', color: 'warning.contrastText' }}>
              <Typography variant="subtitle2" gutterBottom>
                警告范围
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="最小值"
                    name="warning_range.min"
                    type="number"
                    value={formData.warning_range.min}
                    onChange={handleInputChange}
                    disabled={loading}
                    InputProps={{ inputProps: { step: 'any' } }}
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="最大值"
                    name="warning_range.max"
                    type="number"
                    value={formData.warning_range.max}
                    onChange={handleInputChange}
                    disabled={loading}
                    InputProps={{ inputProps: { step: 'any' } }}
                  />
                </Grid>
              </Grid>
            </Paper>
          </Grid>
          
          <Grid item xs={12}>
            <Paper sx={{ p: 2, bgcolor: 'error.light', color: 'error.contrastText' }}>
              <Typography variant="subtitle2" gutterBottom>
                严重范围
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="最小值"
                    name="critical_range.min"
                    type="number"
                    value={formData.critical_range.min}
                    onChange={handleInputChange}
                    disabled={loading}
                    InputProps={{ inputProps: { step: 'any' } }}
                  />
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="最大值"
                    name="critical_range.max"
                    type="number"
                    value={formData.critical_range.max}
                    onChange={handleInputChange}
                    disabled={loading}
                    InputProps={{ inputProps: { step: 'any' } }}
                  />
                </Grid>
              </Grid>
            </Paper>
          </Grid>
        </Grid>
      </Box>
    );
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h6">健康数据阈值管理</Typography>
        <Button
          variant="contained"
          color="primary"
          startIcon={<AddIcon />}
          onClick={handleAddThreshold}
          disabled={loading}
        >
          添加阈值
        </Button>
      </Box>
      
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}
      
      <TableContainer component={Paper}>
        <Table aria-label="健康数据阈值表格">
          <TableHead>
            <TableRow>
              <TableCell>名称</TableCell>
              <TableCell>数据类型</TableCell>
              <TableCell>具体类型</TableCell>
              <TableCell>正常范围</TableCell>
              <TableCell>警告范围</TableCell>
              <TableCell>严重范围</TableCell>
              <TableCell>单位</TableCell>
              <TableCell>状态</TableCell>
              <TableCell align="center">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading && thresholds.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} align="center">
                  <CircularProgress size={24} sx={{ my: 2 }} />
                </TableCell>
              </TableRow>
            ) : thresholds.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} align="center">
                  没有找到健康数据阈值
                </TableCell>
              </TableRow>
            ) : (
              thresholds
                .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                .map((threshold) => (
                  <TableRow key={threshold.id}>
                    <TableCell>{threshold.name}</TableCell>
                    <TableCell>{getDataTypeLabel(threshold.data_type)}</TableCell>
                    <TableCell>
                      {threshold.data_type === 'vital_signs'
                        ? getVitalTypeLabel(threshold.vital_type || '')
                        : threshold.test_name}
                    </TableCell>
                    <TableCell>
                      {threshold.normal_range?.min !== undefined && threshold.normal_range?.max !== undefined
                        ? `${threshold.normal_range.min} - ${threshold.normal_range.max}`
                        : threshold.normal_range?.min !== undefined
                        ? `>= ${threshold.normal_range.min}`
                        : threshold.normal_range?.max !== undefined
                        ? `<= ${threshold.normal_range.max}`
                        : '未设置'}
                    </TableCell>
                    <TableCell>
                      {threshold.warning_range?.min !== undefined && threshold.warning_range?.max !== undefined
                        ? `${threshold.warning_range.min} - ${threshold.warning_range.max}`
                        : threshold.warning_range?.min !== undefined
                        ? `>= ${threshold.warning_range.min}`
                        : threshold.warning_range?.max !== undefined
                        ? `<= ${threshold.warning_range.max}`
                        : '未设置'}
                    </TableCell>
                    <TableCell>
                      {threshold.critical_range?.min !== undefined && threshold.critical_range?.max !== undefined
                        ? `${threshold.critical_range.min} - ${threshold.critical_range.max}`
                        : threshold.critical_range?.min !== undefined
                        ? `>= ${threshold.critical_range.min}`
                        : threshold.critical_range?.max !== undefined
                        ? `<= ${threshold.critical_range.max}`
                        : '未设置'}
                    </TableCell>
                    <TableCell>{threshold.unit}</TableCell>
                    <TableCell>
                      <Chip
                        label={threshold.is_active ? '激活' : '停用'}
                        color={threshold.is_active ? 'success' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title="编辑">
                        <IconButton
                          size="small"
                          color="primary"
                          onClick={() => handleEditThreshold(threshold.id)}
                          disabled={loading}
                        >
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))
            )}
          </TableBody>
        </Table>
        <TablePagination
          rowsPerPageOptions={[5, 10, 25]}
          component="div"
          count={thresholds.length}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
          labelRowsPerPage="每页行数:"
          labelDisplayedRows={({ from, to, count }) => `${from}-${to} 共 ${count}`}
        />
      </TableContainer>
      
      {/* 阈值表单对话框 */}
      <Dialog
        open={dialogOpen}
        onClose={() => !loading && setDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          {currentThresholdId ? '编辑健康数据阈值' : '添加健康数据阈值'}
        </DialogTitle>
        <DialogContent dividers>
          {renderThresholdDetails()}
        </DialogContent>
        <DialogActions>
          {currentThresholdId && (
            <Button
              color="error"
              onClick={handleDeleteConfirm}
              disabled={loading}
            >
              删除
            </Button>
          )}
          <Box sx={{ flexGrow: 1 }} />
          <Button onClick={() => setDialogOpen(false)} disabled={loading}>
            取消
          </Button>
          <Button
            variant="contained"
            color="primary"
            onClick={handleSubmit}
            disabled={loading}
          >
            {loading ? <CircularProgress size={24} /> : '保存'}
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 删除确认对话框 */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => !loading && setDeleteDialogOpen(false)}
      >
        <DialogTitle>删除确认</DialogTitle>
        <DialogContent>
          <DialogContentText>
            确定要删除这个健康数据阈值吗？此操作不可撤销。
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)} disabled={loading}>
            取消
          </Button>
          <Button
            color="error"
            onClick={handleDeleteThreshold}
            disabled={loading}
          >
            {loading ? <CircularProgress size={24} /> : '确认删除'}
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

export default HealthThresholdManagement; 