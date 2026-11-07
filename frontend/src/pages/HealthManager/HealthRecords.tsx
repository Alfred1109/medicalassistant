import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  Divider,
  Grid,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  Chip,
  Button,
  IconButton,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  CircularProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  SelectChangeEvent,
} from '@mui/material';
import { Search as SearchIcon, Add as AddIcon, ArrowBack as ArrowBackIcon, Edit as EditIcon, Delete as DeleteIcon, Visibility as VisibilityIcon } from '@mui/icons-material';
import { useSelector } from 'react-redux';
import { apiService } from '../../services/api';
import type { RootState } from '../../store/types';

// 随访类型选项（对应后端 FollowUpType 枚举）
const followUpTypes = [
  { value: 'phone', label: '电话随访' },
  { value: 'online', label: '线上随访' },
  { value: 'onsite', label: '门诊随访' },
  { value: 'home_visit', label: '家庭访视' },
  { value: 'remote_monitoring', label: '远程监测' },
  { value: 'group', label: '小组随访' },
  { value: 'other', label: '其他' },
];

// ISO 时间转 datetime-local 输入值（本地时区）
const toLocalInput = (iso?: string): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 标签面板组件
function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`health-record-tabpanel-${index}`}
      aria-labelledby={`health-record-tab-${index}`}
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

// 记录类型选项
const recordTypes = [
  { value: 'all', label: '全部类型' },
  { value: 'medical_record', label: '门诊病历' },
  { value: 'admission_record', label: '入院记录' },
  { value: 'discharge_summary', label: '出院小结' },
  { value: 'surgery_record', label: '手术记录' },
  { value: 'examination_report', label: '检查报告' },
  { value: 'progress_note', label: '病程记录' },
  { value: 'consultation', label: '会诊意见' },
  { value: 'prescription', label: '处方' },
  { value: 'nursing_record', label: '护理记录' },
  { value: 'other', label: '其他' },
];

const HealthRecords: React.FC = () => {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  
  // 状态管理
  const [tabValue, setTabValue] = useState(0);
  const [records, setRecords] = useState<any[]>([]);
  const [followUps, setFollowUps] = useState<any[]>([]);
  const [healthData, setHealthData] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedRecord, setSelectedRecord] = useState<any>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [recordDialogOpen, setRecordDialogOpen] = useState(false);
  const [followUpDialogOpen, setFollowUpDialogOpen] = useState(false);
  const [selectedFollowUp, setSelectedFollowUp] = useState<any>(null);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');
  const [filterType, setFilterType] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  // 当前登录用户（用于后端必填的 created_by / provider_id 字段）
  const currentUser = useSelector((state: RootState) => state.auth.user);
  // 健康档案表单（受控），对应后端 HealthRecordCreate：
  // patient_id / record_type / title / content / created_by / tags
  const [recordForm, setRecordForm] = useState({
    record_type: 'medical_record',
    title: '',
    content: '',
    tags: ''
  });
  // 随访表单（受控），对应后端 FollowUpRecordCreate：
  // patient_id / follow_up_type / scheduled_date / provider_id / description
  const [followUpForm, setFollowUpForm] = useState({
    follow_up_type: 'phone',
    scheduled_date: '',
    description: ''
  });
  // 健康数据详情（只读查看，数据已在健康数据标签页抓取）
  const [healthDataDetail, setHealthDataDetail] = useState<any>(null);
  
  // 处理标签切换
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };
  
  // 返回患者列表
  const handleBack = () => {
    navigate('/app/health-manager/patients');
  };
  
  // 获取患者健康档案
  const fetchHealthRecords = async () => {
    if (!patientId) return;
    
    try {
      setLoading(true);
      const response = await apiService.getHealthRecords(patientId, {});
      setRecords(response.data);
      
      // 获取统计信息
      const statsResponse = await apiService.getHealthRecordStats(patientId);
      setStats(statsResponse.data);
      
      setLoading(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || '获取健康档案失败');
      setLoading(false);
      showSnackbar('获取健康档案失败', 'error');
    }
  };
  
  // 获取随访记录
  const fetchFollowUps = async () => {
    if (!patientId) return;
    
    try {
      const response = await apiService.getFollowUps(patientId, {});
      setFollowUps(response.data);
    } catch (err: any) {
      showSnackbar('获取随访记录失败', 'error');
    }
  };
  
  // 获取健康数据
  const fetchHealthData = async () => {
    if (!patientId) return;
    
    try {
      const response = await apiService.getHealthData(patientId, {});
      setHealthData(response.data);
    } catch (err: any) {
      showSnackbar('获取健康数据失败', 'error');
    }
  };
  
  // 组件挂载和患者ID更改时加载数据
  useEffect(() => {
    if (patientId) {
      fetchHealthRecords();
      fetchFollowUps();
      fetchHealthData();
    } else {
      setLoading(false);
    }
  }, [patientId]);
  
  // 打开健康档案对话框（record 为空表示新建，否则编辑并预填）
  const handleOpenRecordDialog = (record: any = null) => {
    setSelectedRecord(record);
    setRecordForm({
      record_type: record?.record_type || 'medical_record',
      title: record?.title || '',
      content: record?.content || '',
      tags: Array.isArray(record?.tags) ? record.tags.join(',') : ''
    });
    setRecordDialogOpen(true);
  };
  
  // 关闭健康档案对话框
  const handleCloseRecordDialog = () => {
    setSelectedRecord(null);
    setRecordDialogOpen(false);
  };
  
  // 打开随访记录对话框（followUp 为空表示新建，否则编辑并预填）
  const handleOpenFollowUpDialog = (followUp: any = null) => {
    setSelectedFollowUp(followUp);
    setFollowUpForm({
      follow_up_type: followUp?.follow_up_type || 'phone',
      scheduled_date: toLocalInput(followUp?.scheduled_date),
      description: followUp?.description || ''
    });
    setFollowUpDialogOpen(true);
  };
  
  // 关闭随访记录对话框
  const handleCloseFollowUpDialog = () => {
    setSelectedFollowUp(null);
    setFollowUpDialogOpen(false);
  };
  
  // 打开删除确认对话框
  const handleOpenDeleteDialog = (record: any) => {
    setSelectedRecord(record);
    setDeleteDialogOpen(true);
  };
  
  // 关闭删除确认对话框
  const handleCloseDeleteDialog = () => {
    setDeleteDialogOpen(false);
  };
  
  // 确认删除健康档案
  const handleDeleteRecord = async () => {
    if (!selectedRecord) return;
    
    try {
      await apiService.deleteHealthRecord(selectedRecord.id);
      showSnackbar('健康档案已删除', 'success');
      fetchHealthRecords();
    } catch (err: any) {
      showSnackbar('删除健康档案失败', 'error');
    }
    
    setDeleteDialogOpen(false);
    setSelectedRecord(null);
  };
  
  // 处理健康档案保存（对应后端 HealthRecordCreate / HealthRecordUpdate）
  const handleSaveRecord = async (formData: typeof recordForm) => {
    // created_by 为后端必填字段，取当前登录用户，绝不伪造
    if (!currentUser?.id) {
      showSnackbar('无法获取当前登录用户，暂不能保存', 'error');
      return;
    }
    if (!formData.title.trim() || !formData.content.trim()) {
      showSnackbar('标题和内容为必填项', 'error');
      return;
    }

    try {
      // tags 前端以逗号输入，提交时拆分为数组
      const tags = formData.tags
        .split(/[,，]/)
        .map(tag => tag.trim())
        .filter(Boolean);

      if (selectedRecord) {
        await apiService.updateHealthRecord(selectedRecord.id, {
          title: formData.title.trim(),
          content: formData.content,
          record_type: formData.record_type,
          tags
        });
        showSnackbar('健康档案已更新', 'success');
      } else {
        await apiService.createHealthRecord({
          patient_id: patientId,
          record_type: formData.record_type,
          title: formData.title.trim(),
          content: formData.content,
          created_by: currentUser.id,
          tags
        });
        showSnackbar('健康档案已创建', 'success');
      }

      handleCloseRecordDialog();
      fetchHealthRecords();
    } catch (err: any) {
      showSnackbar(err.response?.data?.detail || '保存健康档案失败', 'error');
    }
  };

  // 处理随访记录保存（对应后端 FollowUpRecordCreate / FollowUpRecordUpdate）
  const handleSaveFollowUp = async (formData: typeof followUpForm) => {
    // provider_id 为后端必填字段，取当前登录用户，绝不伪造
    if (!currentUser?.id) {
      showSnackbar('无法获取当前登录用户，暂不能保存', 'error');
      return;
    }
    if (!formData.scheduled_date) {
      showSnackbar('请选择计划随访日期', 'error');
      return;
    }
    if (!formData.description.trim()) {
      showSnackbar('随访说明为必填项', 'error');
      return;
    }

    try {
      if (selectedFollowUp) {
        await apiService.updateFollowUp(selectedFollowUp.id, {
          follow_up_type: formData.follow_up_type,
          scheduled_date: formData.scheduled_date,
          description: formData.description.trim(),
          provider_id: currentUser.id
        });
        showSnackbar('随访记录已更新', 'success');
      } else {
        await apiService.createFollowUp({
          patient_id: patientId,
          follow_up_type: formData.follow_up_type,
          scheduled_date: formData.scheduled_date,
          provider_id: currentUser.id,
          description: formData.description.trim()
        });
        showSnackbar('随访记录已创建', 'success');
      }

      handleCloseFollowUpDialog();
      fetchFollowUps();
    } catch (err: any) {
      showSnackbar(err.response?.data?.detail || '保存随访记录失败', 'error');
    }
  };
  
  // 显示提示信息
  const showSnackbar = (message: string, severity: 'success' | 'error') => {
    setSnackbarMessage(message);
    setSnackbarSeverity(severity);
    setSnackbarOpen(true);
  };
  
  // 关闭提示信息
  const handleCloseSnackbar = () => {
    setSnackbarOpen(false);
  };
  
  // 处理记录类型筛选
  const handleFilterChange = (event: SelectChangeEvent) => {
    setFilterType(event.target.value);
  };
  
  // 过滤健康档案列表
  const filteredRecords = records.filter(record => {
    const matchesType = filterType === 'all' || record.record_type === filterType;
    const matchesSearch = searchTerm === '' ||
      (record.title || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (record.content && String(record.content).toLowerCase().includes(searchTerm.toLowerCase()));

    return matchesType && matchesSearch;
  });
  
  // 如果没有提供患者ID，显示选择患者的提示
  if (!patientId) {
    return (
      <Box p={3}>
        <Typography variant="h5" gutterBottom>健康档案管理</Typography>
        <Alert severity="info" sx={{ mt: 2 }}>
          请从患者列表中选择一个患者查看其健康档案
        </Alert>
        <Button 
          variant="contained" 
          color="primary" 
          onClick={handleBack} 
          sx={{ mt: 2 }}
        >
          返回患者列表
        </Button>
      </Box>
    );
  }
  
  // 加载中显示
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="400px">
        <CircularProgress />
      </Box>
    );
  }
  
  return (
    <Box>
      <Box display="flex" alignItems="center" mb={3}>
        <IconButton onClick={handleBack} sx={{ mr: 1 }}>
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h5" component="h1">
          患者健康档案管理
        </Typography>
      </Box>
      
      {/* 统计信息卡片 */}
      {stats && (
        <Grid container spacing={2} mb={3}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography variant="h6" color="primary" gutterBottom>总记录数</Typography>
                <Typography variant="h4">{stats.total_records}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography variant="h6" color="primary" gutterBottom>即将到来的随访</Typography>
                <Typography variant="h4">{stats.upcoming_followups?.length || 0}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography variant="h6" color="primary" gutterBottom>最近更新</Typography>
                <Typography variant="body1">
                  {stats.recent_updates?.length > 0 
                    ? new Date(stats.recent_updates[0]).toLocaleDateString() 
                    : '无'}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography variant="h6" color="primary" gutterBottom>待处理事项</Typography>
                <Typography variant="h4">{stats.pending_actions?.length || 0}</Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
      
      <Paper sx={{ width: '100%', mb: 3 }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          indicatorColor="primary"
          textColor="primary"
          variant="fullWidth"
        >
          <Tab label="健康档案" />
          <Tab label="随访记录" />
          <Tab label="健康数据" />
        </Tabs>
        
        {/* 健康档案标签页 */}
        <TabPanel value={tabValue} index={0}>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Box display="flex" gap={2} flexGrow={1}>
              <TextField
                placeholder="搜索健康档案..."
                variant="outlined"
                size="small"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: <SearchIcon color="action" fontSize="small" sx={{ mr: 1 }} />,
                }}
                sx={{ minWidth: 200 }}
              />
              <FormControl variant="outlined" size="small" sx={{ minWidth: 150 }}>
                <InputLabel id="record-type-filter-label">记录类型</InputLabel>
                <Select
                  labelId="record-type-filter-label"
                  id="record-type-filter"
                  value={filterType}
                  onChange={handleFilterChange}
                  label="记录类型"
                >
                  {recordTypes.map((type) => (
                    <MenuItem key={type.value} value={type.value}>
                      {type.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
            <Button
              startIcon={<AddIcon />}
              variant="contained"
              color="primary"
              onClick={() => handleOpenRecordDialog()}
            >
              新建档案
            </Button>
          </Box>
          
          {filteredRecords.length === 0 ? (
            <Alert severity="info">
              没有符合条件的健康档案
            </Alert>
          ) : (
            <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>标题</TableCell>
                    <TableCell>记录类型</TableCell>
                    <TableCell>创建时间</TableCell>
                    <TableCell>更新时间</TableCell>
                    <TableCell>创建者</TableCell>
                    <TableCell align="right">操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredRecords.map((record) => {
                    // 将记录类型的键转换为可读标签
                    const recordTypeLabel = recordTypes.find(
                      type => type.value === record.record_type
                    )?.label || record.record_type;
                    
                    return (
                      <TableRow key={record.id}>
                        <TableCell>{record.title}</TableCell>
                        <TableCell>{recordTypeLabel}</TableCell>
                        <TableCell>{new Date(record.created_at).toLocaleString()}</TableCell>
                        <TableCell>{new Date(record.updated_at).toLocaleString()}</TableCell>
                        <TableCell>{record.created_by}</TableCell>
                        <TableCell align="right">
                          <IconButton color="primary" onClick={() => handleOpenRecordDialog(record)}>
                            <VisibilityIcon />
                          </IconButton>
                          <IconButton color="primary" onClick={() => handleOpenRecordDialog(record)}>
                            <EditIcon />
                          </IconButton>
                          <IconButton color="error" onClick={() => handleOpenDeleteDialog(record)}>
                            <DeleteIcon />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </TabPanel>
        
        {/* 随访记录标签页 */}
        <TabPanel value={tabValue} index={1}>
          <Box display="flex" justifyContent="flex-end" mb={2}>
            <Button
              startIcon={<AddIcon />}
              variant="contained"
              color="primary"
              onClick={() => handleOpenFollowUpDialog()}
            >
              新建随访
            </Button>
          </Box>
          
          {followUps.length === 0 ? (
            <Alert severity="info">
              没有随访记录
            </Alert>
          ) : (
            <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>随访类型</TableCell>
                    <TableCell>计划日期</TableCell>
                    <TableCell>状态</TableCell>
                    <TableCell>实际日期</TableCell>
                    <TableCell>创建者</TableCell>
                    <TableCell align="right">操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {followUps.map((followUp) => (
                    <TableRow key={followUp.id}>
                      <TableCell>{followUp.follow_up_type}</TableCell>
                      <TableCell>{new Date(followUp.scheduled_date).toLocaleString()}</TableCell>
                      <TableCell>
                        <Chip 
                          label={followUp.status}
                          color={
                            followUp.status === 'completed' ? 'success' :
                            followUp.status === 'scheduled' ? 'primary' :
                            followUp.status === 'canceled' ? 'error' : 'default'
                          }
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        {followUp.actual_date 
                          ? new Date(followUp.actual_date).toLocaleString()
                          : '-'
                        }
                      </TableCell>
                      <TableCell>{followUp.created_by}</TableCell>
                      <TableCell align="right">
                        <IconButton color="primary" onClick={() => handleOpenFollowUpDialog(followUp)}>
                          <VisibilityIcon />
                        </IconButton>
                        <IconButton color="primary" onClick={() => handleOpenFollowUpDialog(followUp)}>
                          <EditIcon />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </TabPanel>
        
        {/* 健康数据标签页 */}
        <TabPanel value={tabValue} index={2}>
          {healthData.length === 0 ? (
            <Alert severity="info">
              没有健康数据记录
            </Alert>
          ) : (
            <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>数据类型</TableCell>
                    <TableCell>记录时间</TableCell>
                    <TableCell>数据来源</TableCell>
                    <TableCell>记录者</TableCell>
                    <TableCell align="right">查看详情</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {healthData.map((data) => (
                    <TableRow key={data.id}>
                      <TableCell>{data.data_type}</TableCell>
                      <TableCell>{new Date(data.recorded_at).toLocaleString()}</TableCell>
                      <TableCell>{data.source || '手动录入'}</TableCell>
                      <TableCell>{data.recorded_by || '-'}</TableCell>
                      <TableCell align="right">
                        <IconButton
                          color="primary"
                          title="查看详情"
                          onClick={() => setHealthDataDetail(data)}
                        >
                          <VisibilityIcon />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </TabPanel>
      </Paper>
      
      {/* 健康档案编辑对话框（真实接口：POST/PUT /health-records，
          字段对应后端 HealthRecordCreate：patient_id / record_type / title / content / created_by / tags） */}
      <Dialog open={recordDialogOpen} onClose={handleCloseRecordDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedRecord ? '编辑健康档案' : '创建健康档案'}
        </DialogTitle>
        <DialogContent>
          <Box component="form" sx={{ pt: 1 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth margin="normal">
                  <InputLabel>记录类型</InputLabel>
                  <Select
                    value={recordForm.record_type}
                    label="记录类型"
                    onChange={(e: SelectChangeEvent) => setRecordForm({ ...recordForm, record_type: e.target.value })}
                  >
                    {recordTypes.filter(type => type.value !== 'all').map((type) => (
                      <MenuItem key={type.value} value={type.value}>
                        {type.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  label="标题"
                  margin="normal"
                  value={recordForm.title}
                  onChange={(e) => setRecordForm({ ...recordForm, title: e.target.value })}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  required
                  multiline
                  rows={5}
                  label="内容"
                  margin="normal"
                  value={recordForm.content}
                  onChange={(e) => setRecordForm({ ...recordForm, content: e.target.value })}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="标签（用逗号分隔）"
                  margin="normal"
                  value={recordForm.tags}
                  onChange={(e) => setRecordForm({ ...recordForm, tags: e.target.value })}
                  helperText="多个标签请用逗号分隔"
                />
              </Grid>
              <Grid item xs={12}>
                <Typography variant="caption" color="text.secondary">
                  创建者将记录为当前登录用户（后端必填字段）
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseRecordDialog}>取消</Button>
          <Button
            onClick={() => handleSaveRecord(recordForm)}
            variant="contained"
            color="primary"
            disabled={!currentUser}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 随访记录编辑对话框（真实接口：POST/PUT /health-records/followups，
          字段对应后端 FollowUpRecordCreate：patient_id / follow_up_type / scheduled_date /
          provider_id / description；provider_id 取当前登录用户） */}
      <Dialog open={followUpDialogOpen} onClose={handleCloseFollowUpDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedFollowUp ? '编辑随访记录' : '创建随访记录'}
        </DialogTitle>
        <DialogContent>
          <Box component="form" sx={{ pt: 1 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth margin="normal">
                  <InputLabel>随访类型</InputLabel>
                  <Select
                    value={followUpForm.follow_up_type}
                    label="随访类型"
                    onChange={(e: SelectChangeEvent) => setFollowUpForm({ ...followUpForm, follow_up_type: e.target.value })}
                  >
                    {followUpTypes.map((type) => (
                      <MenuItem key={type.value} value={type.value}>
                        {type.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  label="计划随访日期"
                  type="datetime-local"
                  margin="normal"
                  value={followUpForm.scheduled_date}
                  onChange={(e) => setFollowUpForm({ ...followUpForm, scheduled_date: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  required
                  multiline
                  rows={4}
                  label="随访说明"
                  margin="normal"
                  value={followUpForm.description}
                  onChange={(e) => setFollowUpForm({ ...followUpForm, description: e.target.value })}
                />
              </Grid>
              <Grid item xs={12}>
                <Typography variant="caption" color="text.secondary">
                  随访负责人将记录为当前登录用户（后端必填字段）
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseFollowUpDialog}>取消</Button>
          <Button
            onClick={() => handleSaveFollowUp(followUpForm)}
            variant="contained"
            color="primary"
            disabled={!currentUser}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 健康数据只读详情对话框（数据来自已抓取的真实接口 GET /health-records/health-data） */}
      <Dialog open={!!healthDataDetail} onClose={() => setHealthDataDetail(null)} maxWidth="sm" fullWidth>
        <DialogTitle>健康数据详情</DialogTitle>
        <DialogContent>
          {healthDataDetail && (
            <Box sx={{ pt: 1 }}>
              <Typography variant="body1" sx={{ mb: 1 }}>
                <strong>数值：</strong>
                {healthDataDetail.data_content?.value != null
                  ? (typeof healthDataDetail.data_content.value === 'object'
                    ? JSON.stringify(healthDataDetail.data_content.value)
                    : String(healthDataDetail.data_content.value))
                  : '-'}
                {healthDataDetail.data_content?.unit ? ` ${healthDataDetail.data_content.unit}` : ''}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                <strong>数据类型：</strong>{healthDataDetail.data_type}
                {healthDataDetail.data_content?.type ? `（${healthDataDetail.data_content.type}）` : ''}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                <strong>记录时间：</strong>
                {healthDataDetail.recorded_at
                  ? new Date(healthDataDetail.recorded_at).toLocaleString()
                  : '-'}
              </Typography>
              {healthDataDetail.source && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  <strong>数据来源：</strong>{healthDataDetail.source}
                </Typography>
              )}
              {healthDataDetail.recorded_by && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  <strong>记录者：</strong>{healthDataDetail.recorded_by}
                </Typography>
              )}
              {healthDataDetail.data_content?.notes && (
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>备注：</strong>{healthDataDetail.data_content.notes}
                </Typography>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHealthDataDetail(null)}>关闭</Button>
        </DialogActions>
      </Dialog>
      
      {/* 删除确认对话框 */}
      <Dialog open={deleteDialogOpen} onClose={handleCloseDeleteDialog}>
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <Typography>
            确定要删除健康档案 "{selectedRecord?.title}" 吗？此操作不可恢复。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDeleteDialog}>取消</Button>
          <Button onClick={handleDeleteRecord} color="error" variant="contained">
            删除
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 消息提示 */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
      >
        <Alert onClose={handleCloseSnackbar} severity={snackbarSeverity} sx={{ width: '100%' }}>
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default HealthRecords; 