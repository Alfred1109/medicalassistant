import * as React from 'react';
import { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  FormControl,
  FormHelperText,
  Grid,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography
} from '@mui/material';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { LocalizationProvider, DateTimePicker } from '@mui/x-date-pickers';
import { format, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 健康数据类型及其单位
const dataTypes = {
  blood_pressure: { name: '血压', unit: 'mmHg', hasAdditionalInfo: true },
  heart_rate: { name: '心率', unit: 'bpm' },
  blood_oxygen: { name: '血氧', unit: '%' },
  blood_glucose: { name: '血糖', unit: 'mmol/L', hasAdditionalInfo: true },
  body_temperature: { name: '体温', unit: '°C' },
  weight: { name: '体重', unit: 'kg' },
  height: { name: '身高', unit: 'cm' },
  bmi: { name: 'BMI', unit: '', calculated: true },
  sleep: { name: '睡眠', unit: '小时', hasAdditionalInfo: true },
  step_count: { name: '步数', unit: '步' },
  water_intake: { name: '饮水量', unit: 'ml' },
  calorie_intake: { name: '热量摄入', unit: 'kcal', hasAdditionalInfo: true },
  calorie_burn: { name: '热量消耗', unit: 'kcal' },
  mood: { name: '情绪', unit: '', hasAdditionalInfo: true, isEnum: true },
  pain: { name: '疼痛', unit: '', hasAdditionalInfo: true, isEnum: true },
  custom: { name: '自定义', unit: '', hasAdditionalInfo: true }
};

const moodOptions = ['很好', '良好', '一般', '不佳', '糟糕'];
const painOptions = ['无痛', '轻微', '中度', '严重', '剧烈'];

// 健康数据记录接口
export interface HealthDataRecord {
  id?: string;
  patient_id: string;
  data_type: string;
  value: number | string;
  unit: string;
  measured_at: Date | string;
  recorded_by?: string;
  device?: string;
  additional_info?: {
    systolic?: number;
    diastolic?: number;
    before_meal?: boolean;
    after_meal?: boolean;
    quality?: string;
    duration?: number;
    food_details?: string;
    location?: string;
    intensity?: string;
    description?: string;
    [key: string]: any;
  };
  tags?: string[];
  notes?: string;
}

// 组件属性接口
export interface HealthDataFormProps {
  initialData?: Partial<HealthDataRecord>;
  onSubmit: (data: HealthDataRecord) => void;
  onCancel: () => void;
  patientId?: string;
}

const HealthDataForm = ({
  initialData = {},
  onSubmit,
  onCancel,
  patientId
}: HealthDataFormProps) => {
  // 表单状态
  const [formData, setFormData] = useState<Partial<HealthDataRecord>>({
    patient_id: patientId || initialData.patient_id || '',
    data_type: initialData.data_type || 'blood_pressure',
    value: initialData.value || '',
    unit: initialData.unit || '',
    measured_at: initialData.measured_at || new Date(),
    device: initialData.device || '',
    additional_info: initialData.additional_info || {},
    tags: initialData.tags || [],
    notes: initialData.notes || ''
  });

  // 错误状态
  const [errors, setErrors] = useState<Record<string, string>>({});

  // 当数据类型改变时更新单位
  useEffect(() => {
    if (formData.data_type && dataTypes[formData.data_type as keyof typeof dataTypes]) {
      setFormData(prev => ({
        ...prev,
        unit: dataTypes[prev.data_type as keyof typeof dataTypes].unit,
        additional_info: initialData.additional_info || {}
      }));
    }
  }, [formData.data_type, initialData.additional_info]);

  // 处理表单提交
  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    
    // 验证表单
    const newErrors: Record<string, string> = {};
    
    if (!formData.patient_id) {
      newErrors.patient_id = '患者ID不能为空';
    }
    
    if (!formData.data_type) {
      newErrors.data_type = '数据类型不能为空';
    }
    
    if (formData.value === '' || formData.value === undefined) {
      newErrors.value = '数值不能为空';
    }
    
    if (!formData.measured_at) {
      newErrors.measured_at = '测量时间不能为空';
    }
    
    // 额外验证：血压
    if (formData.data_type === 'blood_pressure') {
      if (!formData.additional_info?.systolic) {
        newErrors['additional_info.systolic'] = '收缩压不能为空';
      }
      if (!formData.additional_info?.diastolic) {
        newErrors['additional_info.diastolic'] = '舒张压不能为空';
      }
    }
    
    // 血糖额外验证
    if (formData.data_type === 'blood_glucose' && 
        !formData.additional_info?.before_meal && 
        !formData.additional_info?.after_meal) {
      newErrors['additional_info.meal'] = '请选择餐前或餐后';
    }
    
    setErrors(newErrors);
    
    // 如果没有错误，提交表单
    if (Object.keys(newErrors).length === 0) {
      // 格式化日期
      const formattedData = {
        ...formData,
        measured_at: formData.measured_at instanceof Date 
          ? formData.measured_at.toISOString() 
          : formData.measured_at
      } as HealthDataRecord;
      
      onSubmit(formattedData);
    }
  };

  // 处理输入变化
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
    
    // 清除错误
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: '' }));
    }
  };

  // 处理选择变化
  const handleSelectChange = (e: React.ChangeEvent<{ name?: string; value: unknown }>) => {
    const { name, value } = e.target;
    if (name) {
      setFormData(prev => ({
        ...prev,
        [name]: value
      }));
      
      // 清除错误
      if (errors[name as string]) {
        setErrors(prev => ({ ...prev, [name as string]: '' }));
      }
    }
  };

  // 处理日期变化
  const handleDateChange = (date: Date | null) => {
    if (date) {
      setFormData(prev => ({
        ...prev,
        measured_at: date
      }));
      
      // 清除错误
      if (errors.measured_at) {
        setErrors(prev => ({ ...prev, measured_at: '' }));
      }
    }
  };

  // 处理附加信息变化
  const handleAdditionalInfoChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | { name?: string; value: unknown }>
  ) => {
    const { name, value } = e.target;
    if (name && name.startsWith('additional_info.')) {
      const field = name.replace('additional_info.', '');
      setFormData(prev => ({
        ...prev,
        additional_info: {
          ...prev.additional_info,
          [field]: value
        }
      }));
      
      // 清除错误
      if (errors[name]) {
        setErrors(prev => ({ ...prev, [name]: '' }));
      }
    }
  };

  // 处理标签变化
  const handleTagsChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const tags = e.target.value.split(',').map(tag => tag.trim());
    setFormData(prev => ({
      ...prev,
      tags
    }));
  };

  // 渲染额外信息字段
  const renderAdditionalFields = () => {
    const type = formData.data_type as keyof typeof dataTypes;
    
    if (!type || !dataTypes[type].hasAdditionalInfo) return null;
    
    switch (type) {
      case 'blood_pressure':
        return (
          <>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="收缩压"
                name="additional_info.systolic"
                type="number"
                value={formData.additional_info?.systolic || ''}
                onChange={handleAdditionalInfoChange}
                InputProps={{
                  endAdornment: <InputAdornment position="end">mmHg</InputAdornment>,
                }}
                error={!!errors['additional_info.systolic']}
                helperText={errors['additional_info.systolic']}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="舒张压"
                name="additional_info.diastolic"
                type="number"
                value={formData.additional_info?.diastolic || ''}
                onChange={handleAdditionalInfoChange}
                InputProps={{
                  endAdornment: <InputAdornment position="end">mmHg</InputAdornment>,
                }}
                error={!!errors['additional_info.diastolic']}
                helperText={errors['additional_info.diastolic']}
              />
            </Grid>
          </>
        );
        
      case 'blood_glucose':
        return (
          <Grid item xs={12}>
            <FormControl component="fieldset" error={!!errors['additional_info.meal']}>
              <Typography variant="subtitle2" gutterBottom>
                测量时间
              </Typography>
              <Stack direction="row" spacing={2}>
                <FormControl>
                  <FormHelperText>
                    {errors['additional_info.meal']}
                  </FormHelperText>
                </FormControl>
              </Stack>
            </FormControl>
          </Grid>
        );
        
      // ... existing code ...
      
      default:
        return null;
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {initialData.id ? '编辑健康数据' : '添加健康数据'}
        </Typography>
        <Box component="form" onSubmit={handleSubmit}>
          <Grid container spacing={3}>
            {/* 数据类型选择 */}
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth error={!!errors.data_type}>
                <InputLabel id="data-type-label">数据类型</InputLabel>
                <Select
                  labelId="data-type-label"
                  name="data_type"
                  value={formData.data_type || ''}
                  onChange={handleSelectChange}
                  label="数据类型"
                >
                  {Object.entries(dataTypes).map(([key, { name }]) => (
                    <MenuItem key={key} value={key}>
                      {name}
                    </MenuItem>
                  ))}
                </Select>
                {errors.data_type && <FormHelperText>{errors.data_type}</FormHelperText>}
              </FormControl>
            </Grid>
            
            {/* 测量时间 */}
            <Grid item xs={12} sm={6}>
              <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
                <DateTimePicker
                  label="测量时间"
                  value={formData.measured_at}
                  onChange={handleDateChange}
                  slotProps={{
                    textField: {
                      fullWidth: true,
                      error: !!errors.measured_at,
                      helperText: errors.measured_at
                    }
                  }}
                />
              </LocalizationProvider>
            </Grid>
            
            {/* 附加字段 */}
            {renderAdditionalFields()}
            
            {/* 设备 */}
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="设备"
                name="device"
                value={formData.device || ''}
                onChange={handleChange}
              />
            </Grid>
            
            {/* 标签 */}
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="标签"
                name="tags"
                value={formData.tags?.join(', ') || ''}
                onChange={handleTagsChange}
                helperText="用逗号分隔多个标签"
              />
            </Grid>
            
            {/* 备注 */}
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="备注"
                name="notes"
                multiline
                rows={3}
                value={formData.notes || ''}
                onChange={handleChange}
              />
            </Grid>
            
            {/* 按钮 */}
            <Grid item xs={12}>
              <Stack direction="row" spacing={2} justifyContent="flex-end">
                <Button variant="outlined" onClick={onCancel}>
                  取消
                </Button>
                <Button type="submit" variant="contained" color="primary">
                  保存
                </Button>
              </Stack>
            </Grid>
          </Grid>
        </Box>
      </CardContent>
    </Card>
  );
};

export default HealthDataForm; 