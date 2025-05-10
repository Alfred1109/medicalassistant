import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Button,
  Chip,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Switch,
  FormControlLabel,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress,
  Alert,
  Tooltip,
  Stack
} from '@mui/material';
import {
  Schedule as ScheduleIcon,
  Email as EmailIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  Save as SaveIcon,
  Add as AddIcon,
  ContentCopy as ContentCopyIcon
} from '@mui/icons-material';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 报表调度配置类型
export interface ReportSchedule {
  id: string;
  name: string;
  description?: string;
  reportId: string;
  reportName: string;
  frequency: 'once' | 'daily' | 'weekly' | 'monthly';
  weekday?: number; // 0-6, 周日为0
  monthDay?: number; // 1-31
  time?: string; // HH:MM 格式
  nextRunTime: Date;
  recipients: string[];
  format: 'pdf' | 'excel' | 'html';
  enabled: boolean;
  createdAt: Date;
  createdBy: string;
  lastRunTime?: Date;
  lastRunStatus?: 'success' | 'error';
}

interface ReportSchedulerProps {
  savedReports: Array<{id: string; name: string}>;
  schedules: ReportSchedule[];
  loading?: boolean;
  onSaveSchedule: (schedule: Partial<ReportSchedule>) => Promise<void>;
  onDeleteSchedule: (scheduleId: string) => Promise<void>;
  onToggleSchedule: (scheduleId: string, enabled: boolean) => Promise<void>;
}

/**
 * 报表调度组件
 * 用于设置报表的自动生成和发送计划
 */
const ReportScheduler: React.FC<ReportSchedulerProps> = ({
  savedReports,
  schedules,
  loading = false,
  onSaveSchedule,
  onDeleteSchedule,
  onToggleSchedule
}) => {
  // 状态
  const [showDialog, setShowDialog] = useState(false);
  const [editSchedule, setEditSchedule] = useState<Partial<ReportSchedule> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  // 表单验证
  const validateForm = (): boolean => {
    if (!editSchedule) return false;
    
    if (!editSchedule.name?.trim()) {
      setError('请输入计划名称');
      return false;
    }
    
    if (!editSchedule.reportId) {
      setError('请选择报表');
      return false;
    }
    
    if (!editSchedule.frequency) {
      setError('请选择频率');
      return false;
    }
    
    if (editSchedule.frequency === 'weekly' && editSchedule.weekday === undefined) {
      setError('请选择星期几');
      return false;
    }
    
    if (editSchedule.frequency === 'monthly' && editSchedule.monthDay === undefined) {
      setError('请选择每月几号');
      return false;
    }
    
    if (editSchedule.frequency !== 'once' && !editSchedule.time) {
      setError('请选择时间');
      return false;
    }
    
    if (editSchedule.frequency === 'once' && !editSchedule.nextRunTime) {
      setError('请选择执行时间');
      return false;
    }
    
    if (!editSchedule.recipients || editSchedule.recipients.length === 0) {
      setError('请添加至少一个接收者');
      return false;
    }
    
    if (!editSchedule.format) {
      setError('请选择导出格式');
      return false;
    }
    
    return true;
  };

  // 打开创建计划对话框
  const handleOpenCreateDialog = () => {
    const defaultTime = new Date();
    defaultTime.setHours(8, 0, 0, 0);
    
    setEditSchedule({
      name: '',
      description: '',
      reportId: savedReports.length > 0 ? savedReports[0].id : '',
      reportName: savedReports.length > 0 ? savedReports[0].name : '',
      frequency: 'weekly',
      weekday: 1, // 周一
      time: '08:00',
      nextRunTime: defaultTime,
      recipients: [],
      format: 'pdf',
      enabled: true
    });
    
    setIsEditing(false);
    setError(null);
    setShowDialog(true);
  };

  // 打开编辑计划对话框
  const handleOpenEditDialog = (schedule: ReportSchedule) => {
    setEditSchedule({ ...schedule });
    setIsEditing(true);
    setError(null);
    setShowDialog(true);
  };

  // 关闭对话框
  const handleCloseDialog = () => {
    setShowDialog(false);
    setEditSchedule(null);
    setError(null);
  };

  // 更新调度信息
  const handleScheduleChange = (field: string, value: any) => {
    if (!editSchedule) return;
    
    let updatedSchedule: Partial<ReportSchedule> = { ...editSchedule, [field]: value };
    
    // 更新reportName
    if (field === 'reportId') {
      const report = savedReports.find(r => r.id === value);
      if (report) {
        updatedSchedule.reportName = report.name;
      }
    }
    
    // 如果更改了频率，重置相关字段
    if (field === 'frequency') {
      if (value === 'once') {
        updatedSchedule = { 
          ...updatedSchedule, 
          weekday: undefined, 
          monthDay: undefined,
          time: undefined
        };
      } else if (value === 'daily') {
        updatedSchedule = { 
          ...updatedSchedule, 
          weekday: undefined, 
          monthDay: undefined
        };
      } else if (value === 'weekly') {
        updatedSchedule = { 
          ...updatedSchedule, 
          monthDay: undefined,
          weekday: 1 // 默认周一
        };
      } else if (value === 'monthly') {
        updatedSchedule = { 
          ...updatedSchedule, 
          weekday: undefined,
          monthDay: 1 // 默认1号
        };
      }
    }
    
    setEditSchedule(updatedSchedule);
    setError(null);
  };

  // 添加接收者
  const handleAddRecipient = (email: string) => {
    if (!editSchedule) return;
    
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setError('请输入有效的电子邮件地址');
      return;
    }
    
    if (editSchedule.recipients?.includes(email)) {
      setError('该邮箱已添加');
      return;
    }
    
    const recipients = [...(editSchedule.recipients || []), email];
    setEditSchedule({ ...editSchedule, recipients });
    setError(null);
  };

  // 移除接收者
  const handleRemoveRecipient = (email: string) => {
    if (!editSchedule) return;
    
    const recipients = editSchedule.recipients?.filter(r => r !== email) || [];
    setEditSchedule({ ...editSchedule, recipients });
  };

  // 保存调度计划
  const handleSaveSchedule = async () => {
    if (!validateForm() || !editSchedule) return;
    
    try {
      await onSaveSchedule(editSchedule);
      setShowDialog(false);
      setSuccessMessage(isEditing ? '调度计划已更新' : '调度计划已创建');
      
      // 3秒后清除成功消息
      setTimeout(() => {
        setSuccessMessage(null);
      }, 3000);
    } catch (error) {
      console.error('保存调度计划失败:', error);
      setError('保存失败，请稍后重试');
    }
  };

  // 删除调度计划
  const handleDeleteSchedule = async (id: string) => {
    try {
      await onDeleteSchedule(id);
      setSuccessMessage('调度计划已删除');
      
      // 3秒后清除成功消息
      setTimeout(() => {
        setSuccessMessage(null);
      }, 3000);
    } catch (error) {
      console.error('删除调度计划失败:', error);
      setError('删除失败，请稍后重试');
    }
  };

  // 切换调度计划启用状态
  const handleToggleSchedule = async (id: string, enabled: boolean) => {
    try {
      await onToggleSchedule(id, enabled);
      setSuccessMessage(enabled ? '调度计划已启用' : '调度计划已禁用');
      
      // 3秒后清除成功消息
      setTimeout(() => {
        setSuccessMessage(null);
      }, 3000);
    } catch (error) {
      console.error('切换调度计划状态失败:', error);
      setError('操作失败，请稍后重试');
      
      // 3秒后清除错误消息
      setTimeout(() => {
        setError(null);
      }, 3000);
    }
  };

  // 格式化下次运行时间
  const formatNextRunTime = (schedule: ReportSchedule): string => {
    if (schedule.frequency === 'once') {
      return format(new Date(schedule.nextRunTime), 'yyyy-MM-dd HH:mm', { locale: zhCN });
    }
    
    const parts = [];
    
    if (schedule.frequency === 'daily') {
      parts.push('每天');
    } else if (schedule.frequency === 'weekly') {
      const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
      parts.push(`每${weekdays[schedule.weekday || 0]}`);
    } else if (schedule.frequency === 'monthly') {
      parts.push(`每月${schedule.monthDay}号`);
    }
    
    if (schedule.time) {
      parts.push(schedule.time);
    }
    
    return parts.join(' ');
  };

  // 渲染表单对话框
  const renderDialog = () => {
    if (!editSchedule) return null;
    
    return (
      <Dialog 
        open={showDialog} 
        onClose={handleCloseDialog} 
        maxWidth="md" 
        fullWidth
      >
        <DialogTitle>
          {isEditing ? '编辑调度计划' : '创建调度计划'}
        </DialogTitle>
        
        <DialogContent>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
          )}
          
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {/* 基本信息 */}
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="计划名称"
                value={editSchedule.name || ''}
                onChange={(e) => handleScheduleChange('name', e.target.value)}
                required
                error={!editSchedule.name?.trim()}
              />
            </Grid>
            
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required>
                <InputLabel>选择报表</InputLabel>
                <Select
                  value={editSchedule.reportId || ''}
                  onChange={(e) => handleScheduleChange('reportId', e.target.value)}
                  label="选择报表"
                >
                  {savedReports.map(report => (
                    <MenuItem key={report.id} value={report.id}>
                      {report.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="描述"
                value={editSchedule.description || ''}
                onChange={(e) => handleScheduleChange('description', e.target.value)}
                multiline
                rows={2}
              />
            </Grid>
            
            {/* 调度频率设置 */}
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required>
                <InputLabel>频率</InputLabel>
                <Select
                  value={editSchedule.frequency || 'weekly'}
                  onChange={(e) => handleScheduleChange('frequency', e.target.value)}
                  label="频率"
                >
                  <MenuItem value="once">一次性</MenuItem>
                  <MenuItem value="daily">每天</MenuItem>
                  <MenuItem value="weekly">每周</MenuItem>
                  <MenuItem value="monthly">每月</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            {editSchedule.frequency === 'weekly' && (
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth required>
                  <InputLabel>星期几</InputLabel>
                  <Select
                    value={editSchedule.weekday !== undefined ? editSchedule.weekday : 1}
                    onChange={(e) => handleScheduleChange('weekday', e.target.value)}
                    label="星期几"
                  >
                    <MenuItem value={0}>周日</MenuItem>
                    <MenuItem value={1}>周一</MenuItem>
                    <MenuItem value={2}>周二</MenuItem>
                    <MenuItem value={3}>周三</MenuItem>
                    <MenuItem value={4}>周四</MenuItem>
                    <MenuItem value={5}>周五</MenuItem>
                    <MenuItem value={6}>周六</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            )}
            
            {editSchedule.frequency === 'monthly' && (
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth required>
                  <InputLabel>每月几号</InputLabel>
                  <Select
                    value={editSchedule.monthDay !== undefined ? editSchedule.monthDay : 1}
                    onChange={(e) => handleScheduleChange('monthDay', e.target.value)}
                    label="每月几号"
                  >
                    {Array.from({ length: 31 }, (_, i) => i + 1).map(day => (
                      <MenuItem key={day} value={day}>{day}号</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
            )}
            
            {editSchedule.frequency === 'once' ? (
              <Grid item xs={12} sm={6}>
                <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
                  <DateTimePicker
                    label="执行时间"
                    value={editSchedule.nextRunTime || null}
                    onChange={(value) => handleScheduleChange('nextRunTime', value)}
                    slotProps={{
                      textField: {
                        fullWidth: true,
                        required: true
                      }
                    }}
                  />
                </LocalizationProvider>
              </Grid>
            ) : (
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="时间"
                  type="time"
                  value={editSchedule.time || '08:00'}
                  onChange={(e) => handleScheduleChange('time', e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  inputProps={{ step: 300 }} // 5min
                  required
                />
              </Grid>
            )}
            
            {/* 导出格式 */}
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required>
                <InputLabel>导出格式</InputLabel>
                <Select
                  value={editSchedule.format || 'pdf'}
                  onChange={(e) => handleScheduleChange('format', e.target.value)}
                  label="导出格式"
                >
                  <MenuItem value="pdf">PDF</MenuItem>
                  <MenuItem value="excel">Excel</MenuItem>
                  <MenuItem value="html">HTML</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={12} sm={6}>
              <FormControlLabel
                control={
                  <Switch
                    checked={editSchedule.enabled !== false}
                    onChange={(e) => handleScheduleChange('enabled', e.target.checked)}
                    color="primary"
                  />
                }
                label="启用该调度计划"
              />
            </Grid>
            
            {/* 接收者设置 */}
            <Grid item xs={12}>
              <Typography variant="subtitle2" gutterBottom>
                接收者
              </Typography>
              <Divider sx={{ mb: 2 }} />
              
              <Box sx={{ display: 'flex', mb: 2 }}>
                <TextField
                  id="recipient-email"
                  label="电子邮件地址"
                  variant="outlined"
                  size="small"
                  sx={{ flexGrow: 1, mr: 1 }}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter') {
                      const input = document.getElementById('recipient-email') as HTMLInputElement;
                      handleAddRecipient(input.value);
                      input.value = '';
                    }
                  }}
                />
                <Button
                  variant="outlined"
                  startIcon={<AddIcon />}
                  onClick={() => {
                    const input = document.getElementById('recipient-email') as HTMLInputElement;
                    handleAddRecipient(input.value);
                    input.value = '';
                  }}
                >
                  添加
                </Button>
              </Box>
              
              <Box sx={{ mb: 2 }}>
                {editSchedule.recipients && editSchedule.recipients.length > 0 ? (
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {editSchedule.recipients.map(email => (
                      <Chip
                        key={email}
                        label={email}
                        onDelete={() => handleRemoveRecipient(email)}
                        sx={{ mb: 1 }}
                      />
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary" align="center">
                    尚未添加接收者
                  </Typography>
                )}
              </Box>
            </Grid>
          </Grid>
        </DialogContent>
        
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button
            onClick={handleSaveSchedule}
            variant="contained"
            disabled={loading}
            startIcon={loading ? <CircularProgress size={16} /> : null}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>
    );
  };

  return (
    <Paper sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <ScheduleIcon sx={{ mr: 1 }} />
          <Typography variant="h6">报表调度管理</Typography>
        </Box>
        
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleOpenCreateDialog}
          disabled={savedReports.length === 0}
        >
          创建计划
        </Button>
      </Box>
      
      {successMessage && (
        <Alert severity="success" sx={{ mb: 2 }}>{successMessage}</Alert>
      )}
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
      )}
      
      {savedReports.length === 0 ? (
        <Alert severity="info">请先创建并保存报表，然后才能创建调度计划</Alert>
      ) : (
        <>
          {schedules.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="body1" color="text.secondary">
                暂无调度计划
              </Typography>
              <Button
                variant="outlined"
                startIcon={<AddIcon />}
                onClick={handleOpenCreateDialog}
                sx={{ mt: 2 }}
              >
                创建第一个计划
              </Button>
            </Box>
          ) : (
            <List>
              {schedules.map((schedule) => (
                <ListItem
                  key={schedule.id}
                  sx={{
                    mb: 2,
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 1,
                    bgcolor: schedule.enabled ? 'background.paper' : 'action.disabledBackground',
                  }}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Typography variant="subtitle1">{schedule.name}</Typography>
                        {schedule.enabled ? (
                          <Chip size="small" color="success" label="已启用" sx={{ ml: 1 }} />
                        ) : (
                          <Chip size="small" color="default" label="已禁用" sx={{ ml: 1 }} />
                        )}
                      </Box>
                    }
                    secondary={
                      <>
                        <Box sx={{ mt: 1 }}>
                          <Typography variant="body2" component="span">
                            报表: {schedule.reportName} | 格式: {schedule.format.toUpperCase()} | 
                            计划: {formatNextRunTime(schedule)}
                          </Typography>
                        </Box>
                        {schedule.lastRunTime && (
                          <Box sx={{ mt: 0.5 }}>
                            <Typography variant="body2" component="span">
                              上次运行: {format(new Date(schedule.lastRunTime), 'yyyy-MM-dd HH:mm', { locale: zhCN })} | 
                              状态: 
                              <Chip 
                                size="small" 
                                color={schedule.lastRunStatus === 'success' ? 'success' : 'error'} 
                                label={schedule.lastRunStatus === 'success' ? '成功' : '失败'} 
                                sx={{ ml: 0.5 }}
                              />
                            </Typography>
                          </Box>
                        )}
                        {schedule.recipients && schedule.recipients.length > 0 && (
                          <Box sx={{ mt: 0.5, display: 'flex', alignItems: 'center' }}>
                            <EmailIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary' }} />
                            <Typography variant="body2" component="span">
                              接收者: {schedule.recipients.join(', ')}
                            </Typography>
                          </Box>
                        )}
                      </>
                    }
                  />
                  <ListItemSecondaryAction>
                    <Tooltip title={schedule.enabled ? '禁用' : '启用'}>
                      <Switch
                        edge="end"
                        checked={schedule.enabled}
                        onChange={(e) => handleToggleSchedule(schedule.id, e.target.checked)}
                      />
                    </Tooltip>
                    <Tooltip title="编辑">
                      <IconButton edge="end" onClick={() => handleOpenEditDialog(schedule)} sx={{ ml: 1 }}>
                        <EditIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="删除">
                      <IconButton 
                        edge="end" 
                        onClick={() => handleDeleteSchedule(schedule.id)} 
                        sx={{ ml: 1 }}
                        color="error"
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Tooltip>
                  </ListItemSecondaryAction>
                </ListItem>
              ))}
            </List>
          )}
        </>
      )}
      
      {renderDialog()}
    </Paper>
  );
};

export default ReportScheduler; 