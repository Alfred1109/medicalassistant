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
  Paper,
  CircularProgress,
  FormHelperText,
  Divider
} from '@mui/material';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { zhCN } from 'date-fns/locale';

// 记录类型选项
const recordTypes = [
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

// 可见性选项
const visibilityOptions = [
  { value: 'all', label: '所有人可见' },
  { value: 'doctor_only', label: '仅医生可见' },
  { value: 'patient_only', label: '仅患者可见' },
  { value: 'medical_staff', label: '医护人员可见' },
];

interface HealthRecordFormProps {
  record?: any;
  patientId: string;
  currentUserId: string;
  onSave: (formData: any) => void;
  onCancel: () => void;
  loading?: boolean;
}

const HealthRecordForm: React.FC<HealthRecordFormProps> = ({
  record,
  patientId,
  currentUserId,
  onSave,
  onCancel,
  loading = false
}) => {
  // 表单状态
  const [formData, setFormData] = useState({
    title: '',
    record_type: 'medical_record',
    content: {},
    visibility: 'all',
    tags: [],
    created_by: '',
    metadata: {},
    changeDescription: ''
  });
  
  // 表单错误状态
  const [formErrors, setFormErrors] = useState({
    title: '',
    record_type: '',
    content: ''
  });
  
  // 标签输入
  const [tagInput, setTagInput] = useState('');
  
  // 根据记录类型动态生成的内容字段
  const [contentFields, setContentFields] = useState<any[]>([]);
  
  // 初始化表单数据
  useEffect(() => {
    if (record) {
      setFormData({
        title: record.title || '',
        record_type: record.record_type || 'medical_record',
        content: record.content || {},
        visibility: record.visibility || 'all',
        tags: record.tags || [],
        created_by: record.created_by || currentUserId,
        metadata: record.metadata || {},
        changeDescription: ''
      });
    } else {
      setFormData({
        title: '',
        record_type: 'medical_record',
        content: {},
        visibility: 'all',
        tags: [],
        created_by: currentUserId,
        metadata: {},
        changeDescription: ''
      });
    }
  }, [record, currentUserId]);
  
  // 根据记录类型设置内容字段
  useEffect(() => {
    const fields = getContentFieldsByType(formData.record_type);
    setContentFields(fields);
    
    // 初始化内容对象，确保每个字段都有值
    const initialContent = { ...formData.content };
    fields.forEach(field => {
      if (initialContent[field.name] === undefined) {
        initialContent[field.name] = '';
      }
    });
    
    setFormData(prev => ({
      ...prev,
      content: initialContent
    }));
  }, [formData.record_type]);
  
  // 根据记录类型获取内容字段定义
  const getContentFieldsByType = (recordType: string) => {
    switch (recordType) {
      case 'medical_record':
        return [
          { name: 'chief_complaint', label: '主诉', type: 'text', multiline: true, required: true },
          { name: 'present_illness', label: '现病史', type: 'text', multiline: true, required: true },
          { name: 'past_history', label: '既往史', type: 'text', multiline: true, required: false },
          { name: 'examination', label: '体格检查', type: 'text', multiline: true, required: false },
          { name: 'diagnosis', label: '诊断', type: 'text', multiline: true, required: true },
          { name: 'treatment_plan', label: '治疗计划', type: 'text', multiline: true, required: true },
        ];
      case 'admission_record':
        return [
          { name: 'admission_date', label: '入院日期', type: 'date', required: true },
          { name: 'chief_complaint', label: '主诉', type: 'text', multiline: true, required: true },
          { name: 'present_illness', label: '现病史', type: 'text', multiline: true, required: true },
          { name: 'admission_diagnosis', label: '入院诊断', type: 'text', multiline: true, required: true },
          { name: 'admission_department', label: '入院科室', type: 'text', required: true },
          { name: 'attending_physician', label: '主治医师', type: 'text', required: true },
        ];
      case 'discharge_summary':
        return [
          { name: 'admission_date', label: '入院日期', type: 'date', required: true },
          { name: 'discharge_date', label: '出院日期', type: 'date', required: true },
          { name: 'admission_diagnosis', label: '入院诊断', type: 'text', multiline: true, required: true },
          { name: 'discharge_diagnosis', label: '出院诊断', type: 'text', multiline: true, required: true },
          { name: 'treatment_course', label: '治疗经过', type: 'text', multiline: true, required: true },
          { name: 'discharge_status', label: '出院状态', type: 'text', required: true },
          { name: 'follow_up_instructions', label: '随访建议', type: 'text', multiline: true, required: false },
        ];
      case 'surgery_record':
        return [
          { name: 'surgery_date', label: '手术日期', type: 'date', required: true },
          { name: 'surgery_name', label: '手术名称', type: 'text', required: true },
          { name: 'surgeons', label: '手术医师', type: 'text', required: true },
          { name: 'anesthesia', label: '麻醉方式', type: 'text', required: true },
          { name: 'pre_diagnosis', label: '术前诊断', type: 'text', multiline: true, required: true },
          { name: 'post_diagnosis', label: '术后诊断', type: 'text', multiline: true, required: true },
          { name: 'procedure_details', label: '手术过程', type: 'text', multiline: true, required: true },
          { name: 'complications', label: '并发症', type: 'text', multiline: true, required: false },
        ];
      case 'examination_report':
        return [
          { name: 'exam_date', label: '检查日期', type: 'date', required: true },
          { name: 'exam_type', label: '检查类型', type: 'text', required: true },
          { name: 'exam_site', label: '检查部位', type: 'text', required: true },
          { name: 'findings', label: '检查所见', type: 'text', multiline: true, required: true },
          { name: 'impression', label: '印象', type: 'text', multiline: true, required: true },
          { name: 'recommendations', label: '建议', type: 'text', multiline: true, required: false },
        ];
      case 'progress_note':
        return [
          { name: 'note_date', label: '记录日期', type: 'date', required: true },
          { name: 'subjective', label: '主观资料', type: 'text', multiline: true, required: true },
          { name: 'objective', label: '客观资料', type: 'text', multiline: true, required: true },
          { name: 'assessment', label: '评估', type: 'text', multiline: true, required: true },
          { name: 'plan', label: '计划', type: 'text', multiline: true, required: true },
        ];
      case 'consultation':
        return [
          { name: 'consultation_date', label: '会诊日期', type: 'date', required: true },
          { name: 'requesting_physician', label: '申请医师', type: 'text', required: true },
          { name: 'consulting_physician', label: '会诊医师', type: 'text', required: true },
          { name: 'reason', label: '会诊原因', type: 'text', multiline: true, required: true },
          { name: 'recommendations', label: '会诊意见', type: 'text', multiline: true, required: true },
        ];
      case 'prescription':
        return [
          { name: 'prescription_date', label: '处方日期', type: 'date', required: true },
          { name: 'prescriber', label: '处方医师', type: 'text', required: true },
          { name: 'medications', label: '药品(格式：药名;剂量;用法;疗程)', type: 'text', multiline: true, required: true },
          { name: 'diagnosis', label: '诊断', type: 'text', required: true },
          { name: 'instructions', label: '用药说明', type: 'text', multiline: true, required: false },
        ];
      default:
        return [
          { name: 'record_date', label: '记录日期', type: 'date', required: true },
          { name: 'title', label: '标题', type: 'text', required: true },
          { name: 'content', label: '内容', type: 'text', multiline: true, required: true },
        ];
    }
  };
  
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
  
  // 处理内容字段变化
  const handleContentChange = (name: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      content: {
        ...prev.content,
        [name]: value
      }
    }));
    
    // 清除内容错误
    if (formErrors.content) {
      setFormErrors(prev => ({
        ...prev,
        content: ''
      }));
    }
  };
  
  // 处理日期变化
  const handleDateChange = (name: string, date: Date | null) => {
    if (date) {
      handleContentChange(name, date.toISOString());
    }
  };
  
  // 添加标签
  const handleAddTag = () => {
    if (tagInput.trim() && !formData.tags.includes(tagInput.trim())) {
      setFormData(prev => ({
        ...prev,
        tags: [...prev.tags, tagInput.trim()]
      }));
      setTagInput('');
    }
  };
  
  // 删除标签
  const handleDeleteTag = (tagToDelete: string) => {
    setFormData(prev => ({
      ...prev,
      tags: prev.tags.filter(tag => tag !== tagToDelete)
    }));
  };
  
  // 验证表单
  const validateForm = () => {
    const errors = {
      title: '',
      record_type: '',
      content: ''
    };
    let isValid = true;
    
    if (!formData.title.trim()) {
      errors.title = '请输入标题';
      isValid = false;
    }
    
    if (!formData.record_type) {
      errors.record_type = '请选择记录类型';
      isValid = false;
    }
    
    // 验证必填内容字段
    const requiredFields = contentFields.filter(field => field.required);
    for (const field of requiredFields) {
      if (!formData.content[field.name]) {
        errors.content = '请填写所有必填字段';
        isValid = false;
        break;
      }
    }
    
    setFormErrors(errors);
    return isValid;
  };
  
  // 提交表单
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validateForm()) {
      // 提交表单数据
      onSave({
        patient_id: patientId,
        title: formData.title,
        record_type: formData.record_type,
        content: formData.content,
        visibility: formData.visibility,
        tags: formData.tags,
        created_by: formData.created_by,
        metadata: formData.metadata,
        change_description: formData.changeDescription
      });
    }
  };
  
  return (
    <Box component="form" onSubmit={handleSubmit} noValidate>
      <Grid container spacing={3}>
        <Grid item xs={12} sm={8}>
          <TextField
            fullWidth
            label="标题"
            name="title"
            value={formData.title}
            onChange={handleInputChange}
            required
            error={!!formErrors.title}
            helperText={formErrors.title}
            disabled={loading}
          />
        </Grid>
        
        <Grid item xs={12} sm={4}>
          <FormControl fullWidth required error={!!formErrors.record_type}>
            <InputLabel id="record-type-label">记录类型</InputLabel>
            <Select
              labelId="record-type-label"
              id="record-type"
              name="record_type"
              value={formData.record_type}
              onChange={handleSelectChange}
              label="记录类型"
              disabled={loading || !!record}
            >
              {recordTypes.map((type) => (
                <MenuItem key={type.value} value={type.value}>
                  {type.label}
                </MenuItem>
              ))}
            </Select>
            {formErrors.record_type && (
              <FormHelperText>{formErrors.record_type}</FormHelperText>
            )}
          </FormControl>
        </Grid>
        
        <Grid item xs={12}>
          <Typography variant="subtitle1" gutterBottom>
            档案内容
          </Typography>
          <Divider sx={{ mb: 2 }} />
          
          {formErrors.content && (
            <FormHelperText error sx={{ mb: 2 }}>
              {formErrors.content}
            </FormHelperText>
          )}
          
          <Grid container spacing={2}>
            <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
              {contentFields.map((field) => (
                <Grid item xs={12} sm={field.type === 'date' ? 6 : 12} key={field.name}>
                  {field.type === 'date' ? (
                    <DatePicker
                      label={`${field.label}${field.required ? ' *' : ''}`}
                      value={formData.content[field.name] ? new Date(formData.content[field.name]) : null}
                      onChange={(date) => handleDateChange(field.name, date)}
                      disabled={loading}
                      slotProps={{
                        textField: {
                          fullWidth: true,
                          required: field.required,
                        },
                      }}
                    />
                  ) : (
                    <TextField
                      fullWidth
                      label={field.label}
                      value={formData.content[field.name] || ''}
                      onChange={(e) => handleContentChange(field.name, e.target.value)}
                      multiline={field.multiline}
                      rows={field.multiline ? 4 : 1}
                      required={field.required}
                      disabled={loading}
                    />
                  )}
                </Grid>
              ))}
            </LocalizationProvider>
          </Grid>
        </Grid>
        
        <Grid item xs={12} sm={6}>
          <FormControl fullWidth>
            <InputLabel id="visibility-label">可见性</InputLabel>
            <Select
              labelId="visibility-label"
              id="visibility"
              name="visibility"
              value={formData.visibility}
              onChange={handleSelectChange}
              label="可见性"
              disabled={loading}
            >
              {visibilityOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        
        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="修改说明"
            name="changeDescription"
            value={formData.changeDescription}
            onChange={handleInputChange}
            placeholder="若修改现有记录，请说明修改原因"
            disabled={loading || !record}
          />
        </Grid>
        
        <Grid item xs={12}>
          <Box display="flex" alignItems="center" mb={1}>
            <TextField
              label="标签"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              placeholder="输入标签并按回车"
              disabled={loading}
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddTag();
                }
              }}
              sx={{ marginRight: 1 }}
            />
            <Button 
              variant="outlined" 
              onClick={handleAddTag}
              disabled={!tagInput.trim() || loading}
            >
              添加
            </Button>
          </Box>
          
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {formData.tags.map((tag) => (
              <Chip
                key={tag}
                label={tag}
                onDelete={() => handleDeleteTag(tag)}
                disabled={loading}
              />
            ))}
          </Box>
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
                record ? '更新档案' : '创建档案'
              )}
            </Button>
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
};

export default HealthRecordForm; 