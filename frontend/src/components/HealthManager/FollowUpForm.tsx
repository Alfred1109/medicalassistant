import React, { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Button,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Chip,
  CircularProgress,
  FormHelperText,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction
} from '@mui/material';
import { LocalizationProvider, DateTimePicker } from '@mui/x-date-pickers';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { zhCN } from 'date-fns/locale';
import { Add as AddIcon, Delete as DeleteIcon } from '@mui/icons-material';

// 随访类型选项
const followUpTypes = [
  { value: 'phone', label: '电话随访' },
  { value: 'online', label: '线上随访' },
  { value: 'onsite', label: '门诊随访' },
  { value: 'home_visit', label: '家庭访视' },
  { value: 'remote_monitoring', label: '远程监测' },
  { value: 'group', label: '小组随访' },
  { value: 'other', label: '其他' },
];

// 随访状态选项
const followUpStatusOptions = [
  { value: 'scheduled', label: '已计划' },
  { value: 'completed', label: '已完成' },
  { value: 'canceled', label: '已取消' },
  { value: 'missed', label: '已错过' },
  { value: 'rescheduled', label: '已重新安排' },
];

interface FollowUpFormProps {
  followUp?: any;
  patientId: string;
  currentUserId: string;
  onSave: (formData: any) => void;
  onCancel: () => void;
  loading?: boolean;
  healthRecords?: any[];
}

interface QuestionItem {
  question_id: string;
  question: string;
  answer_type: string;
  options?: string[];
  required: boolean;
  answer?: string;
}

const FollowUpForm: React.FC<FollowUpFormProps> = ({
  followUp,
  patientId,
  currentUserId,
  onSave,
  onCancel,
  loading = false,
  healthRecords = []
}) => {
  // 表单状态
  const [formData, setFormData] = useState({
    follow_up_type: 'phone',
    scheduled_date: new Date(),
    actual_date: null as Date | null,
    status: 'scheduled',
    notes: '',
    questions: [] as QuestionItem[],
    answers: [] as QuestionItem[],
    health_record_ids: [] as string[],
    created_by: currentUserId
  });
  
  // 表单错误状态
  const [formErrors, setFormErrors] = useState({
    follow_up_type: '',
    scheduled_date: '',
    notes: ''
  });
  
  // 问题相关状态
  const [newQuestion, setNewQuestion] = useState('');
  const [newQuestionType, setNewQuestionType] = useState('text');
  const [newQuestionRequired, setNewQuestionRequired] = useState(false);
  const [newQuestionOptions, setNewQuestionOptions] = useState('');
  
  // 初始化表单数据
  useEffect(() => {
    if (followUp) {
      setFormData({
        follow_up_type: followUp.follow_up_type || 'phone',
        scheduled_date: followUp.scheduled_date ? new Date(followUp.scheduled_date) : new Date(),
        actual_date: followUp.actual_date ? new Date(followUp.actual_date) : null,
        status: followUp.status || 'scheduled',
        notes: followUp.notes || '',
        questions: followUp.questions || [],
        answers: followUp.answers || [],
        health_record_ids: followUp.health_record_ids || [],
        created_by: followUp.created_by || currentUserId
      });
    } else {
      setFormData({
        follow_up_type: 'phone',
        scheduled_date: new Date(),
        actual_date: null,
        status: 'scheduled',
        notes: '',
        questions: [],
        answers: [],
        health_record_ids: [],
        created_by: currentUserId
      });
    }
  }, [followUp, currentUserId]);
  
  // 处理表单输入变化
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
    
    // 清除错误提示
    if (formErrors[name as keyof typeof formErrors]) {
      setFormErrors(prev => ({
        ...prev,
        [name]: ''
      }));
    }
  };
  
  // 处理下拉框变化
  const handleSelectChange = (e: React.ChangeEvent<{ name?: string; value: unknown }>) => {
    const { name, value } = e.target;
    if (name) {
      setFormData(prev => ({
        ...prev,
        [name]: value
      }));
    }
  };
  
  // 处理日期时间变化
  const handleDateChange = (field: string, date: Date | null) => {
    if (date) {
      setFormData(prev => ({
        ...prev,
        [field]: date
      }));
    }
  };
  
  // 添加问题
  const handleAddQuestion = () => {
    if (!newQuestion.trim()) return;
    
    const newQuestionItem: QuestionItem = {
      question_id: `q_${Date.now()}`,
      question: newQuestion,
      answer_type: newQuestionType,
      required: newQuestionRequired,
    };
    
    // 如果是选择题，添加选项
    if (newQuestionType === 'option' && newQuestionOptions.trim()) {
      newQuestionItem.options = newQuestionOptions.split(',').map(opt => opt.trim());
    }
    
    setFormData(prev => ({
      ...prev,
      questions: [...prev.questions, newQuestionItem]
    }));
    
    // 重置问题输入
    setNewQuestion('');
    setNewQuestionType('text');
    setNewQuestionRequired(false);
    setNewQuestionOptions('');
  };
  
  // 删除问题
  const handleDeleteQuestion = (questionId: string) => {
    setFormData(prev => ({
      ...prev,
      questions: prev.questions.filter(q => q.question_id !== questionId)
    }));
  };
  
  // 添加健康档案关联
  const handleAddHealthRecord = (recordId: string) => {
    if (recordId && !formData.health_record_ids.includes(recordId)) {
      setFormData(prev => ({
        ...prev,
        health_record_ids: [...prev.health_record_ids, recordId]
      }));
    }
  };
  
  // 删除健康档案关联
  const handleRemoveHealthRecord = (recordId: string) => {
    setFormData(prev => ({
      ...prev,
      health_record_ids: prev.health_record_ids.filter(id => id !== recordId)
    }));
  };
  
  // 验证表单
  const validateForm = () => {
    const errors = {
      follow_up_type: '',
      scheduled_date: '',
      notes: ''
    };
    let isValid = true;
    
    if (!formData.follow_up_type) {
      errors.follow_up_type = '请选择随访类型';
      isValid = false;
    }
    
    if (!formData.scheduled_date) {
      errors.scheduled_date = '请选择计划日期';
      isValid = false;
    }
    
    if (formData.status === 'completed' && !formData.actual_date) {
      errors.scheduled_date = '已完成的随访需要填写实际日期';
      isValid = false;
    }
    
    setFormErrors(errors);
    return isValid;
  };
  
  // 提交表单
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validateForm()) {
      // 将日期转换为ISO字符串
      const submissionData = {
        ...formData,
        scheduled_date: formData.scheduled_date.toISOString(),
        actual_date: formData.actual_date ? formData.actual_date.toISOString() : null,
        patient_id: patientId
      };
      
      onSave(submissionData);
    }
  };
  
  // 获取关联的健康档案标题
  const getHealthRecordTitle = (recordId: string) => {
    const record = healthRecords.find(r => r.id === recordId);
    return record ? record.title : recordId;
  };
  
  // 问题类型选项
  const questionTypes = [
    { value: 'text', label: '文本' },
    { value: 'number', label: '数字' },
    { value: 'option', label: '选择题' },
    { value: 'boolean', label: '是/否' }
  ];
  
  return (
    <Box component="form" onSubmit={handleSubmit} noValidate>
      <Grid container spacing={3}>
        <Grid item xs={12} sm={6}>
          <FormControl fullWidth required error={!!formErrors.follow_up_type}>
            <InputLabel id="follow-up-type-label">随访类型</InputLabel>
            <Select
              labelId="follow-up-type-label"
              id="follow-up-type"
              name="follow_up_type"
              value={formData.follow_up_type}
              onChange={handleSelectChange}
              label="随访类型"
              disabled={loading}
            >
              {followUpTypes.map((type) => (
                <MenuItem key={type.value} value={type.value}>
                  {type.label}
                </MenuItem>
              ))}
            </Select>
            {formErrors.follow_up_type && (
              <FormHelperText>{formErrors.follow_up_type}</FormHelperText>
            )}
          </FormControl>
        </Grid>
        
        <Grid item xs={12} sm={6}>
          <FormControl fullWidth required>
            <InputLabel id="status-label">状态</InputLabel>
            <Select
              labelId="status-label"
              id="status"
              name="status"
              value={formData.status}
              onChange={handleSelectChange}
              label="状态"
              disabled={loading || !followUp}
            >
              {followUpStatusOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        
        <Grid item xs={12} sm={6}>
          <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
            <DateTimePicker
              label="计划日期 *"
              value={formData.scheduled_date}
              onChange={(date) => handleDateChange('scheduled_date', date)}
              disabled={loading}
              slotProps={{
                textField: {
                  fullWidth: true,
                  required: true,
                  error: !!formErrors.scheduled_date,
                  helperText: formErrors.scheduled_date
                },
              }}
            />
          </LocalizationProvider>
        </Grid>
        
        <Grid item xs={12} sm={6}>
          <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
            <DateTimePicker
              label="实际日期"
              value={formData.actual_date}
              onChange={(date) => handleDateChange('actual_date', date)}
              disabled={loading || formData.status !== 'completed'}
              slotProps={{
                textField: {
                  fullWidth: true,
                },
              }}
            />
          </LocalizationProvider>
        </Grid>
        
        <Grid item xs={12}>
          <TextField
            fullWidth
            label="备注"
            name="notes"
            value={formData.notes}
            onChange={handleInputChange}
            multiline
            rows={3}
            disabled={loading}
          />
        </Grid>
        
        <Grid item xs={12}>
          <Typography variant="subtitle1" gutterBottom>
            随访问题
          </Typography>
          <Divider sx={{ mb: 2 }} />
          
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} sm={5}>
              <TextField
                fullWidth
                label="问题内容"
                value={newQuestion}
                onChange={(e) => setNewQuestion(e.target.value)}
                disabled={loading}
              />
            </Grid>
            <Grid item xs={12} sm={3}>
              <FormControl fullWidth>
                <InputLabel id="question-type-label">问题类型</InputLabel>
                <Select
                  labelId="question-type-label"
                  value={newQuestionType}
                  onChange={(e) => setNewQuestionType(e.target.value)}
                  label="问题类型"
                  disabled={loading}
                >
                  {questionTypes.map((type) => (
                    <MenuItem key={type.value} value={type.value}>
                      {type.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth>
                <InputLabel id="required-label">是否必填</InputLabel>
                <Select
                  labelId="required-label"
                  value={newQuestionRequired ? 'true' : 'false'}
                  onChange={(e) => setNewQuestionRequired(e.target.value === 'true')}
                  label="是否必填"
                  disabled={loading}
                >
                  <MenuItem value="true">是</MenuItem>
                  <MenuItem value="false">否</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={2}>
              <Button
                fullWidth
                variant="contained"
                onClick={handleAddQuestion}
                disabled={!newQuestion.trim() || loading}
                sx={{ height: '100%' }}
              >
                添加问题
              </Button>
            </Grid>
            {newQuestionType === 'option' && (
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="选项（用逗号分隔）"
                  value={newQuestionOptions}
                  onChange={(e) => setNewQuestionOptions(e.target.value)}
                  placeholder="选项1,选项2,选项3"
                  disabled={loading}
                />
              </Grid>
            )}
          </Grid>
          
          <List>
            {formData.questions.map((question, index) => (
              <ListItem key={question.question_id} divider>
                <ListItemText
                  primary={
                    <Box display="flex" alignItems="center">
                      <Typography component="span" variant="body1">
                        {`${index + 1}. ${question.question}`}
                      </Typography>
                      {question.required && (
                        <Chip size="small" label="必填" color="primary" sx={{ ml: 1 }} />
                      )}
                    </Box>
                  }
                  secondary={
                    <Typography variant="body2" color="text.secondary">
                      {`类型: ${questionTypes.find(t => t.value === question.answer_type)?.label || question.answer_type}`}
                      {question.options ? ` | 选项: ${question.options.join(', ')}` : ''}
                    </Typography>
                  }
                />
                <ListItemSecondaryAction>
                  <IconButton edge="end" onClick={() => handleDeleteQuestion(question.question_id)} disabled={loading}>
                    <DeleteIcon />
                  </IconButton>
                </ListItemSecondaryAction>
              </ListItem>
            ))}
            {formData.questions.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                还没有添加任何问题
              </Typography>
            )}
          </List>
        </Grid>
        
        <Grid item xs={12}>
          <Typography variant="subtitle1" gutterBottom>
            关联健康档案
          </Typography>
          <Divider sx={{ mb: 2 }} />
          
          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel id="health-record-label">选择健康档案</InputLabel>
            <Select
              labelId="health-record-label"
              value=""
              onChange={(e) => handleAddHealthRecord(e.target.value as string)}
              label="选择健康档案"
              disabled={loading || healthRecords.length === 0}
            >
              <MenuItem value="" disabled>选择要关联的健康档案</MenuItem>
              {healthRecords.map((record) => (
                <MenuItem key={record.id} value={record.id} disabled={formData.health_record_ids.includes(record.id)}>
                  {record.title}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          
          <List>
            {formData.health_record_ids.map((recordId) => (
              <ListItem key={recordId} divider>
                <ListItemText primary={getHealthRecordTitle(recordId)} />
                <ListItemSecondaryAction>
                  <IconButton edge="end" onClick={() => handleRemoveHealthRecord(recordId)} disabled={loading}>
                    <DeleteIcon />
                  </IconButton>
                </ListItemSecondaryAction>
              </ListItem>
            ))}
            {formData.health_record_ids.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                还没有关联任何健康档案
              </Typography>
            )}
          </List>
        </Grid>
        
        <Grid item xs={12}>
          <Box display="flex" justifyContent="flex-end" gap={2} mt={2}>
            <Button 
              onClick={onCancel}
              disabled={loading}
            >
              取消
            </Button>
            <Button 
              type="submit" 
              variant="contained" 
              color="primary"
              disabled={loading}
            >
              {loading ? (
                <CircularProgress size={24} />
              ) : (
                followUp ? '更新随访' : '创建随访'
              )}
            </Button>
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
};

export default FollowUpForm; 