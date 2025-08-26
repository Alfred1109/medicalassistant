import React from 'react';
import {
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Box
} from '@mui/material';
import FormHelperText from '@mui/material/FormHelperText';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import Slider from '@mui/material/Slider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import { zhCN } from 'date-fns/locale';

// 通用字段属性
interface BaseFieldProps {
  name: string;
  label: string;
  error?: string;
  required?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  helperText?: string;
}

// 文本输入字段
interface TextFieldComponentProps extends BaseFieldProps {
  type: 'text' | 'email' | 'password' | 'number' | 'tel' | 'url' | 'textarea';
  value: string | number;
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  multiline?: boolean;
  rows?: number;
  placeholder?: string;
  autoFocus?: boolean;
}

// 选择字段
interface SelectFieldProps extends BaseFieldProps {
  type: 'select';
  value: string | number;
  onChange: (e: React.ChangeEvent<{ name?: string; value: unknown }>) => void;
  options: Array<{ value: string | number; label: string }>;
  multiple?: boolean;
}

// 日期选择器字段
interface DateFieldProps extends BaseFieldProps {
  type: 'date';
  value: Date | null;
  onChange: (date: Date | null) => void;
  minDate?: Date;
  maxDate?: Date;
}

// 开关字段
interface SwitchFieldProps extends BaseFieldProps {
  type: 'switch';
  value: boolean;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  color?: 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' | 'default';
}

// 滑块字段
interface SliderFieldProps extends BaseFieldProps {
  type: 'slider';
  value: number | number[];
  onChange: (event: Event, value: number | number[]) => void;
  min?: number;
  max?: number;
  step?: number;
  marks?: boolean | { value: number; label: string }[];
  valueLabelDisplay?: 'auto' | 'on' | 'off';
}

// 联合类型
type FormFieldProps = 
  | TextFieldComponentProps 
  | SelectFieldProps 
  | DateFieldProps 
  | SwitchFieldProps 
  | SliderFieldProps;

/**
 * 通用表单字段组件
 * 根据type属性渲染不同类型的表单控件
 */
const FormField: React.FC<FormFieldProps> = (props) => {
  const { type, name, label, error, required, disabled, fullWidth = true, helperText } = props;

  switch (type) {
    case 'text':
    case 'email':
    case 'password':
    case 'number':
    case 'tel':
    case 'url':
    case 'textarea': {
      const { value, onChange, multiline, rows, placeholder, autoFocus } = props;
      return (
        <TextField
          name={name}
          label={label}
          value={value}
          onChange={onChange}
          error={!!error}
          helperText={error || helperText}
          required={required}
          disabled={disabled}
          fullWidth={fullWidth}
          type={type === 'textarea' ? 'text' : type}
          multiline={multiline || type === 'textarea'}
          rows={rows}
          placeholder={placeholder}
          autoFocus={autoFocus}
          variant="outlined"
          margin="normal"
        />
      );
    }

    case 'select': {
      const { value, onChange, options, multiple } = props;
      return (
        <FormControl
          error={!!error}
          required={required}
          disabled={disabled}
          fullWidth={fullWidth}
          variant="outlined"
          margin="normal"
        >
          <InputLabel>{label}</InputLabel>
          <Select
            name={name}
            value={value}
            onChange={onChange as any}
            label={label}
            multiple={multiple}
          >
            {options.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </Select>
          {(error || helperText) && (
            <FormHelperText error={!!error}>{error || helperText}</FormHelperText>
          )}
        </FormControl>
      );
    }

    case 'date': {
      const { value, onChange, minDate, maxDate } = props;
      return (
        <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
          <DatePicker 
            label={label}
            value={value}
            onChange={onChange}
            disabled={disabled}
            minDate={minDate}
            maxDate={maxDate}
            slotProps={{
              textField: {
                name,
                fullWidth,
                required,
                error: !!error,
                helperText: error || helperText,
                margin: "normal",
                variant: "outlined"
              }
            }}
          />
        </LocalizationProvider>
      );
    }

    case 'switch': {
      const { value, onChange, color = 'primary' } = props;
      return (
        <Box mt={2} mb={1}>
          <FormControl 
            error={!!error}
            required={required}
            disabled={disabled}
            fullWidth={fullWidth}
          >
            <FormControlLabel
              control={
                <Switch
                  name={name}
                  checked={value}
                  onChange={onChange}
                  color={color}
                />
              }
              label={label}
            />
            {(error || helperText) && (
              <FormHelperText error={!!error}>{error || helperText}</FormHelperText>
            )}
          </FormControl>
        </Box>
      );
    }

    case 'slider': {
      const { 
        value, 
        onChange, 
        min = 0, 
        max = 100, 
        step = 1, 
        marks, 
        valueLabelDisplay = 'auto' 
      } = props;
      return (
        <Box mt={2} mb={1}>
          <Typography id={`${name}-label`} gutterBottom>
            {label} {required && <span style={{ color: '#f44336' }}>*</span>}
          </Typography>
          <Slider
            name={name}
            value={value}
            onChange={onChange as any}
            aria-labelledby={`${name}-label`}
            min={min}
            max={max}
            step={step}
            marks={marks}
            disabled={disabled}
            valueLabelDisplay={valueLabelDisplay}
          />
          {(error || helperText) && (
            <FormHelperText error={!!error}>{error || helperText}</FormHelperText>
          )}
        </Box>
      );
    }

    default:
      return null;
  }
};

export default FormField; 