import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, CircularProgress, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import { apiService } from '../../services/api';
import DeviceBinding from '../Patient/DeviceBinding';

type PatientChoice = { id: string; name: string };

const PatientDevices: React.FC = () => {
  const actor = useSelector((state: RootState) => state.auth.user);
  const [patients, setPatients] = useState<PatientChoice[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [managing, setManaging] = useState(false);
  const generation = useRef(0);
  const medical = actor?.role === 'doctor' || actor?.role === 'health_manager';

  useEffect(() => {
    const request = ++generation.current;
    setPatients([]); setSelectedId(''); setManaging(false); setError('');
    if (!medical) return;
    setLoading(true);
    const fetch = actor.role === 'doctor' ? apiService.doctor.getPatients : apiService.healthManager.getPatients;
    fetch().then(({ data }) => {
      if (generation.current !== request) return;
      if (!Array.isArray(data) || data.some(patient => !patient || typeof patient.id !== 'string' || !patient.id)
          || new Set(data.map(patient => patient.id)).size !== data.length) {
        throw new Error('患者名单无效');
      }
      setPatients(data.map(patient => ({ id: patient.id, name: patient.name || '未命名患者' })));
    }).catch(() => {
      if (generation.current === request) setError('授权患者名单没有加载成功，请重试。');
    }).finally(() => {
      if (generation.current === request) setLoading(false);
    });
    return () => { generation.current += 1; };
  }, [actor?.id, actor?.role, medical, retry]);

  if (!medical) return <Alert severity="warning">请从医护工作站进入患者设备管理。</Alert>;
  const selected = patients.find(patient => patient.id === selectedId);
  return <Box>
    <Typography variant="h5" gutterBottom>患者设备管理</Typography>
    <Stack spacing={2} sx={{ mb: 3 }}>
      <Typography color="text.secondary">请选择您负责的患者，查看或管理该患者的设备绑定。</Typography>
      {loading && <CircularProgress size={24} />}
      {error && <Alert severity="error" action={<Button color="inherit" onClick={() => setRetry(value => value + 1)}>重试</Button>}>{error}</Alert>}
      {!loading && !error && patients.length === 0 && <Alert severity="info">当前没有已分配的患者。</Alert>}
      {patients.length > 0 && <TextField select label="患者" value={selectedId} disabled={managing}
        onChange={event => setSelectedId(event.target.value)} sx={{ maxWidth: 400 }}>
        <MenuItem value="">选择患者</MenuItem>
        {patients.map(patient => <MenuItem key={patient.id} value={patient.id}>{patient.name}</MenuItem>)}
      </TextField>}
    </Stack>
    {selected ? <DeviceBinding key={`${actor.id}:${selected.id}`} patientId={selected.id}
      patientName={selected.name} onManagingChange={setManaging} /> :
      !loading && !error && patients.length > 0 && <Alert severity="info">选择患者后显示该患者的设备。</Alert>}
  </Box>;
};

export default PatientDevices;
