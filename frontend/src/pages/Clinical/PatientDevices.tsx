import PatientSelect from '../../components/common/PatientSelect';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Stack, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import { apiService } from '../../services/api';
import { patientDomainErrorCopy } from '../../services/patientErrors';
import {
  mergePatientBatches,
  patientBatchComplete,
  patientLoadMoreAvailable,
  PATIENT_LIST_ONE_SHOT_CAP,
  PATIENT_LIST_PAGE_SIZE,
} from '../../services/patientList';
import DeviceBinding from '../Patient/DeviceBinding';

type PatientChoice = { id: string; name: string };

const PatientDevices: React.FC = () => {
  const actor = useSelector((state: RootState) => state.auth.user);
  const [patients, setPatients] = useState<PatientChoice[]>([]);
  // T59 分页预适配：缺省仍为一次性全量拉取；「加载更多」为可选追加路径，
  // 仅在一次性结果达到上限阈值（canonical 域缺省截断场景）时出现。
  const [morePatients, setMorePatients] = useState<PatientChoice[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState('');
  const [allLoaded, setAllLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [managing, setManaging] = useState(false);
  const generation = useRef(0);
  const medical = actor?.role === 'doctor' || actor?.role === 'health_manager';

  useEffect(() => {
    const request = ++generation.current;
    setPatients([]); setMorePatients([]); setMoreError(''); setAllLoaded(false);
    setSelectedId(''); setManaging(false); setError('');
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
    }).catch(error => {
      if (generation.current === request) setError(patientDomainErrorCopy(error) ?? '授权患者名单没有加载成功，请重试。');
    }).finally(() => {
      if (generation.current === request) setLoading(false);
    });
    return () => { generation.current += 1; };
  }, [actor?.id, actor?.role, medical, retry]);

  // 一次性全量 + 「加载更多」追加的合并视图；未追加时与原全量行为一致。
  const choices = useMemo(
    () => mergePatientBatches<PatientChoice>(patients, morePatients),
    [patients, morePatients]);

  const handleLoadMore = async () => {
    if (loadingMore || loading || managing) return;
    const request = generation.current;
    setLoadingMore(true);
    setMoreError('');
    try {
      const { data } = await apiService.doctor.getPatients(
        { skip: choices.length, limit: PATIENT_LIST_PAGE_SIZE });
      const batch = Array.isArray(data) ? data : [];
      if (generation.current !== request) return;
      const fresh = batch
        .filter(patient => patient && typeof patient.id === 'string' && patient.id)
        .map(patient => ({ id: patient.id, name: patient.name || '未命名患者' }));
      setMorePatients(prev => mergePatientBatches<PatientChoice>(prev, fresh));
      if (patientBatchComplete(batch.length)) setAllLoaded(true);
    } catch (err) {
      // 患者域错误（含 503 INVALID_PATIENT_PAGINATION）走统一文案映射
      if (generation.current === request) setMoreError(patientDomainErrorCopy(err) ?? '加载更多患者失败，请重试。');
    } finally {
      if (generation.current === request) setLoadingMore(false);
    }
  };

  if (!medical) return <Alert severity="warning">请从医护工作站进入患者设备管理。</Alert>;
  const selected = choices.find(patient => patient.id === selectedId);
  // 分页追加仅面向医生端点：/health-managers/patients 尚未提供分页参数
  // （本任务范围仅覆盖 doctor find_assigned_patients 路径）。
  const doctorPaged = actor?.role === 'doctor';
  const showLoadMore = doctorPaged && patientLoadMoreAvailable(choices.length, allLoaded);
  return <Box>
    <Typography variant="h5" gutterBottom>患者设备管理</Typography>
    <Stack spacing={2} sx={{ mb: 3 }}>
      <Typography color="text.secondary">请选择您负责的患者，查看或管理该患者的设备绑定。</Typography>
      {loading && <CircularProgress size={24} />}
      {error && <Alert severity="error" action={<Button color="inherit" onClick={() => setRetry(value => value + 1)}>重试</Button>}>{error}</Alert>}
      {!loading && !error && choices.length === 0 && <Alert severity="info">当前没有已分配的患者。</Alert>}
      {choices.length > 0 && <PatientSelect label="患者" value={selectedId} disabled={managing}
        onChange={setSelectedId} patients={choices} emptyLabel="选择患者" sx={{ maxWidth: 400 }} />}
      {moreError && <Alert severity="error" action={<Button color="inherit" onClick={handleLoadMore}>重试</Button>}>{moreError}</Alert>}
      {showLoadMore && <Button variant="outlined" onClick={handleLoadMore}
        disabled={loadingMore || managing} sx={{ alignSelf: 'flex-start' }}>
        {loadingMore ? '加载中...' : '加载更多患者'}
      </Button>}
      {!showLoadMore && allLoaded && choices.length >= PATIENT_LIST_ONE_SHOT_CAP
        && <Typography variant="body2" color="text.secondary">已加载全部患者</Typography>}
    </Stack>
    {selected ? <DeviceBinding key={`${actor.id}:${selected.id}`} patientId={selected.id}
      patientName={selected.name} onManagingChange={setManaging} /> :
      !loading && !error && choices.length > 0 && <Alert severity="info">选择患者后显示该患者的设备。</Alert>}
  </Box>;
};

export default PatientDevices;
