import React from 'react';
import {
  Box,
  Typography,
  Paper,
  List,
  ListItem,
  ListItemText,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  Chip,
  Divider,
  Alert,
  CircularProgress,
  Tooltip
} from '@mui/material';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import ListItemSecondaryAction from '@mui/material/ListItemSecondaryAction';
import IconButton from '@mui/material/IconButton';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import CheckIcon from '@mui/icons-material/Check';
import NotificationsIcon from '@mui/icons-material/Notifications';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import NotificationsOffIcon from '@mui/icons-material/NotificationsOff';
import AddIcon from '@mui/icons-material/Add';
import PhoneIcon from '@mui/icons-material/Phone';
import SmsIcon from '@mui/icons-material/Sms';
import ChatIcon from '@mui/icons-material/Chat';
import CalendarMonthIcon from '@mui/icons-material/CalendarMonth';
import { format, differenceInDays, isPast, isFuture } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 随访提醒状态类型
type ReminderStatus = 'pending' | 'completed' | 'cancelled' | 'overdue';

// 随访方式类型
type FollowUpMethod = 'phone' | 'message' | 'inperson' | 'video' | 'other';

// 随访提醒对象接口
interface FollowUpReminder {
  id: string;
  patient_id: string;
  patient_name: string;
  scheduled_date: string;
  status: ReminderStatus;
  followup_method: FollowUpMethod;
  notes: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  completed_by?: string;
  completion_notes?: string;
}

// 组件属性接口
interface FollowUpReminderComponentProps {
  reminders: FollowUpReminder[];
  loading?: boolean;
  error?: string;
  onAddReminder?: (reminder: Partial<FollowUpReminder>) => Promise<void>;
  onUpdateReminder?: (id: string, reminder: Partial<FollowUpReminder>) => Promise<void>;
  onDeleteReminder?: (id: string) => Promise<void>;
  onCompleteReminder?: (id: string, notes: string) => Promise<void>;
}

// 随访方式映射
const followUpMethodMap: Record<FollowUpMethod, { label: string, icon: React.ReactNode }> = {
  phone: { label: '电话随访', icon: <PhoneIcon fontSize="small" /> },
  message: { label: '短信随访', icon: <SmsIcon fontSize="small" /> },
  inperson: { label: '面诊随访', icon: <CalendarMonthIcon fontSize="small" /> },
  video: { label: '视频随访', icon: <ChatIcon fontSize="small" /> },
  other: { label: '其他方式', icon: <NotificationsIcon fontSize="small" /> }
};

// 随访状态映射
const reminderStatusMap: Record<ReminderStatus, { label: string, color: 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' }> = {
  pending: { label: '待执行', color: 'primary' },
  completed: { label: '已完成', color: 'success' },
  cancelled: { label: '已取消', color: 'default' },
  overdue: { label: '已过期', color: 'error' }
};

const FollowUpReminderComponent: React.FC<FollowUpReminderComponentProps> = ({
  reminders,
  loading = false,
  error,
  onAddReminder,
  onUpdateReminder,
  onDeleteReminder,
  onCompleteReminder
}) => {
  // 状态
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [completeDialogOpen, setCompleteDialogOpen] = React.useState(false);
  const [confirmDeleteDialogOpen, setConfirmDeleteDialogOpen] = React.useState(false);
  const [selectedReminder, setSelectedReminder] = React.useState<FollowUpReminder | null>(null);
  const [formValues, setFormValues] = React.useState<Partial<FollowUpReminder>>({
    scheduled_date: format(new Date(), 'yyyy-MM-dd'),
    followup_method: 'phone',
    status: 'pending',
    notes: ''
  });
  const [completionNotes, setCompletionNotes] = React.useState('');
  
  // 处理表单输入变化
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormValues((prev: Partial<FollowUpReminder>) => ({ ...prev, [name]: value }));
  };
  
  // 处理选择框变化
  const handleSelectChange = (e: any) => {
    const { name, value } = e.target;
    setFormValues((prev: Partial<FollowUpReminder>) => ({ ...prev, [name]: value }));
  };
  
  // 处理日期变化
  const handleDateChange = (date: Date | null) => {
    if (date) {
      setFormValues((prev: Partial<FollowUpReminder>) => ({ 
        ...prev, 
        scheduled_date: format(date, 'yyyy-MM-dd')
      }));
    }
  };
  
  // 打开添加/编辑对话框
  const handleOpenDialog = (reminder: FollowUpReminder | null = null) => {
    if (reminder) {
      setSelectedReminder(reminder);
      setFormValues({
        scheduled_date: reminder.scheduled_date,
        followup_method: reminder.followup_method,
        status: reminder.status,
        notes: reminder.notes
      });
    } else {
      setSelectedReminder(null);
      setFormValues({
        scheduled_date: format(new Date(), 'yyyy-MM-dd'),
        followup_method: 'phone',
        status: 'pending',
        notes: ''
      });
    }
    setDialogOpen(true);
  };
  
  // 关闭对话框
  const handleCloseDialog = () => {
    setDialogOpen(false);
    setSelectedReminder(null);
  };
  
  // 打开完成对话框
  const handleOpenCompleteDialog = (reminder: FollowUpReminder) => {
    setSelectedReminder(reminder);
    setCompletionNotes('');
    setCompleteDialogOpen(true);
  };
  
  // 关闭完成对话框
  const handleCloseCompleteDialog = () => {
    setCompleteDialogOpen(false);
    setSelectedReminder(null);
  };
  
  // 打开删除确认对话框
  const handleOpenDeleteDialog = (reminder: FollowUpReminder) => {
    setSelectedReminder(reminder);
    setConfirmDeleteDialogOpen(true);
  };
  
  // 关闭删除确认对话框
  const handleCloseDeleteDialog = () => {
    setConfirmDeleteDialogOpen(false);
    setSelectedReminder(null);
  };
  
  // 提交表单
  const handleSubmit = async () => {
    try {
      if (selectedReminder && onUpdateReminder) {
        await onUpdateReminder(selectedReminder.id, formValues);
      } else if (onAddReminder) {
        await onAddReminder(formValues);
      }
      handleCloseDialog();
    } catch (error) {
      console.error('保存随访提醒失败', error);
    }
  };
  
  // 完成随访
  const handleCompleteReminder = async () => {
    if (selectedReminder && onCompleteReminder) {
      try {
        await onCompleteReminder(selectedReminder.id, completionNotes);
        handleCloseCompleteDialog();
      } catch (error) {
        console.error('完成随访失败', error);
      }
    }
  };
  
  // 删除随访提醒
  const handleDeleteReminder = async () => {
    if (selectedReminder && onDeleteReminder) {
      try {
        await onDeleteReminder(selectedReminder.id);
        handleCloseDeleteDialog();
      } catch (error) {
        console.error('删除随访提醒失败', error);
      }
    }
  };
  
  // 格式化日期
  const formatDate = (dateString: string) => {
    try {
      return format(new Date(dateString), 'yyyy年MM月dd日', { locale: zhCN });
    } catch (e) {
      return dateString;
    }
  };
  
  // 计算状态（处理过期状态）
  const calculateStatus = (reminder: FollowUpReminder): ReminderStatus => {
    if (reminder.status === 'completed' || reminder.status === 'cancelled') {
      return reminder.status;
    }
    
    try {
      const scheduledDate = new Date(reminder.scheduled_date);
      if (isPast(scheduledDate) && differenceInDays(new Date(), scheduledDate) > 0) {
        return 'overdue';
      }
    } catch (e) {
      // 日期格式错误，返回原始状态
    }
    
    return reminder.status;
  };
  
  // 排序提醒（待执行和过期的排在前面，已完成和取消的排在后面）
  const sortedReminders = [...reminders].sort((a, b) => {
    const statusA = calculateStatus(a);
    const statusB = calculateStatus(b);
    
    // 首先按状态优先级排序
    const statusPriority: Record<ReminderStatus, number> = {
      overdue: 0,
      pending: 1,
      completed: 2,
      cancelled: 3
    };
    
    const priorityDiff = statusPriority[statusA] - statusPriority[statusB];
    if (priorityDiff !== 0) return priorityDiff;
    
    // 然后按日期排序
    try {
      const dateA = new Date(a.scheduled_date);
      const dateB = new Date(b.scheduled_date);
      
      // 待执行的按日期从早到晚
      if (statusA === 'pending') {
        return dateA.getTime() - dateB.getTime();
      }
      
      // 已完成的按完成时间从晚到早
      if (statusA === 'completed' && a.completed_at && b.completed_at) {
        return new Date(b.completed_at).getTime() - new Date(a.completed_at).getTime();
      }
    } catch (e) {
      // 日期格式错误，保持原始顺序
    }
    
    return 0;
  });
  
  // 计算紧急程度（用于UI显示）
  const calculateUrgency = (reminder: FollowUpReminder): 'normal' | 'urgent' | 'today' => {
    if (calculateStatus(reminder) === 'overdue') return 'urgent';
    
    try {
      const scheduledDate = new Date(reminder.scheduled_date);
      const today = new Date();
      
      if (
        scheduledDate.getDate() === today.getDate() &&
        scheduledDate.getMonth() === today.getMonth() &&
        scheduledDate.getFullYear() === today.getFullYear()
      ) {
        return 'today';
      }
      
      const daysUntil = differenceInDays(scheduledDate, today);
      if (daysUntil >= 0 && daysUntil <= 3) return 'urgent';
    } catch (e) {
      // 日期格式错误
    }
    
    return 'normal';
  };
  
  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h6">随访提醒</Typography>
        <Button 
          variant="contained" 
          color="primary"
          startIcon={<AddIcon />}
          onClick={() => handleOpenDialog()}
        >
          添加提醒
        </Button>
      </Box>
      
      {loading ? (
        <Box display="flex" justifyContent="center" my={3}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error">{error}</Alert>
      ) : (
        <Paper variant="outlined">
          <List>
            {sortedReminders.length > 0 ? (
              sortedReminders.map((reminder) => {
                const status = calculateStatus(reminder);
                const urgency = calculateUrgency(reminder);
                
                return (
                  <React.Fragment key={reminder.id}>
                    <ListItem
                      sx={{
                        bgcolor: urgency === 'urgent' 
                          ? 'rgba(255, 0, 0, 0.05)' 
                          : urgency === 'today' 
                            ? 'rgba(255, 165, 0, 0.05)'
                            : 'transparent'
                      }}
                    >
                      <ListItemText
                        primary={
                          <Box display="flex" alignItems="center">
                            {followUpMethodMap[reminder.followup_method].icon}
                            <Typography variant="body1" ml={1}>
                              {reminder.patient_name}的{followUpMethodMap[reminder.followup_method].label}
                            </Typography>
                            <Chip 
                              size="small" 
                              label={reminderStatusMap[status].label}
                              color={reminderStatusMap[status].color}
                              sx={{ ml: 1 }}
                            />
                          </Box>
                        }
                        secondary={
                          <Box mt={1}>
                            <Typography variant="body2" color="textSecondary">
                              预定日期: {formatDate(reminder.scheduled_date)}
                              {status === 'pending' && (
                                <Chip 
                                  size="small" 
                                  label={
                                    urgency === 'today' 
                                      ? "今天" 
                                      : urgency === 'urgent' 
                                        ? "即将到期" 
                                        : null
                                  }
                                  color={urgency === 'urgent' ? "error" : "warning"}
                                  sx={{ ml: 1, visibility: urgency === 'normal' ? 'hidden' : 'visible' }}
                                />
                              )}
                            </Typography>
                            {reminder.notes && (
                              <Typography variant="body2" color="textSecondary" mt={0.5}>
                                备注: {reminder.notes}
                              </Typography>
                            )}
                            {reminder.completed_at && (
                              <Typography variant="body2" color="textSecondary" mt={0.5}>
                                完成时间: {formatDate(reminder.completed_at)}
                              </Typography>
                            )}
                            {reminder.completion_notes && (
                              <Typography variant="body2" color="textSecondary" mt={0.5}>
                                完成备注: {reminder.completion_notes}
                              </Typography>
                            )}
                          </Box>
                        }
                      />
                      <ListItemSecondaryAction>
                        {status === 'pending' && (
                          <Tooltip title="标记为已完成">
                            <IconButton 
                              edge="end" 
                              aria-label="完成" 
                              onClick={() => handleOpenCompleteDialog(reminder)}
                            >
                              <CheckIcon />
                            </IconButton>
                          </Tooltip>
                        )}
                        <Tooltip title="编辑">
                          <IconButton 
                            edge="end" 
                            aria-label="编辑" 
                            onClick={() => handleOpenDialog(reminder)}
                          >
                            <EditIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="删除">
                          <IconButton 
                            edge="end" 
                            aria-label="删除" 
                            onClick={() => handleOpenDeleteDialog(reminder)}
                          >
                            <DeleteIcon />
                          </IconButton>
                        </Tooltip>
                      </ListItemSecondaryAction>
                    </ListItem>
                    <Divider component="li" />
                  </React.Fragment>
                );
              })
            ) : (
              <ListItem>
                <ListItemText
                  primary="没有随访提醒"
                  secondary={'点击"添加提醒"按钮创建新的随访提醒'}
                />
              </ListItem>
            )}
          </List>
        </Paper>
      )}
      
      {/* 添加/编辑对话框 */}
      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedReminder ? '编辑随访提醒' : '添加随访提醒'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <DatePicker 
                label="预定日期"
                value={formValues.scheduled_date ? new Date(formValues.scheduled_date) : null}
                onChange={handleDateChange}
                sx={{ width: '100%' }}
              />
            </Grid>
            
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>随访方式</InputLabel>
                <Select
                  name="followup_method"
                  value={formValues.followup_method}
                  onChange={handleSelectChange}
                  label="随访方式"
                >
                  {Object.entries(followUpMethodMap).map(([value, { label, icon }]) => (
                    <MenuItem key={value} value={value}>
                      <Box display="flex" alignItems="center">
                        {icon}
                        <Typography sx={{ ml: 1 }}>{label}</Typography>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            {selectedReminder && (
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>状态</InputLabel>
                  <Select
                    name="status"
                    value={formValues.status}
                    onChange={handleSelectChange}
                    label="状态"
                  >
                    {Object.entries(reminderStatusMap).map(([value, { label }]) => (
                      <MenuItem key={value} value={value}>{label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
            )}
            
            <Grid item xs={12}>
              <TextField
                fullWidth
                multiline
                rows={4}
                name="notes"
                label="备注"
                value={formValues.notes}
                onChange={handleInputChange}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog} color="inherit">取消</Button>
          <Button onClick={handleSubmit} color="primary" variant="contained">
            保存
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 完成对话框 */}
      <Dialog open={completeDialogOpen} onClose={handleCloseCompleteDialog} maxWidth="sm" fullWidth>
        <DialogTitle>完成随访</DialogTitle>
        <DialogContent>
          <Box mt={2}>
            <TextField
              fullWidth
              multiline
              rows={4}
              label="完成备注"
              value={completionNotes}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCompletionNotes(e.target.value)}
              placeholder="请输入随访结果和备注信息"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseCompleteDialog} color="inherit">取消</Button>
          <Button onClick={handleCompleteReminder} color="primary" variant="contained">
            标记为已完成
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 删除确认对话框 */}
      <Dialog open={confirmDeleteDialogOpen} onClose={handleCloseDeleteDialog}>
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <Typography>确定要删除这条随访提醒吗？此操作无法撤销。</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDeleteDialog} color="inherit">取消</Button>
          <Button onClick={handleDeleteReminder} color="error">
            删除
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default FollowUpReminderComponent; 