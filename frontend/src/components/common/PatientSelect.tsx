import React from 'react';
import { MenuItem, TextField, type TextFieldProps } from '@mui/material';
import type { PatientOption } from '../../hooks/usePatientOptions';

type Props = Omit<TextFieldProps, 'select' | 'children' | 'onChange' | 'value'> & {
  patients: PatientOption[];
  value: string;
  onChange: (patientId: string) => void;
  loading?: boolean;
  emptyLabel?: string;
  emptyValue?: string;
};

export default function PatientSelect({ patients, value, onChange, loading = false,
  emptyLabel = '请选择患者', emptyValue = '', disabled, ...props }: Props) {
  return <TextField {...props} select value={value} disabled={disabled || loading}
    onChange={event => onChange(event.target.value)}>
    <MenuItem value={emptyValue}>{loading ? '正在加载患者列表…' : emptyLabel}</MenuItem>
    {value && value !== emptyValue && !patients.some(patient => patient.id === value) &&
      <MenuItem value={value}>{value}</MenuItem>}
    {patients.map(patient => <MenuItem key={patient.id} value={patient.id}>{patient.name}</MenuItem>)}
  </TextField>;
}
