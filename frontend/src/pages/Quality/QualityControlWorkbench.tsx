import React, { useEffect, useState } from 'react';
import { Alert, Button, Container, MenuItem, Paper, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import api from '../../services/httpClient';
import type { RootState } from '../../store';
import type { Patient } from '../../types/patient.types';
import type { QualityFact, QualityFilters } from '../../types/quality';
import { qualityError, qualityFilters } from '../../utils/quality';
import QualityMonitoringPanel from './QualityMonitoringPanel';
import QualityIssueList from './QualityIssueList';
import QualityIssueDetailDialog, { CreateQualityIssueDialog } from './QualityIssueDetail';

export default function QualityControlWorkbench() {
  const actor = useSelector((state: RootState) => state.auth.user);
  if (!actor || !['doctor', 'health_manager', 'admin'].includes(actor.role)) return <Alert severity="error">当前账号无权访问过程质控工作台。</Alert>;
  return <QualityWorkspace key={`${actor.id}:${actor.role}`} actor={{ id: actor.id, role: actor.role }} />;
}

function QualityWorkspace({ actor }: {actor: {id: string; role: string}}) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientError, setPatientError] = useState('');
  const [patientId, setPatientId] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [filters, setFilters] = useState<QualityFilters>({});
  const [filterError, setFilterError] = useState('');
  const [tab, setTab] = useState<'followup' | 'rehab_plan' | 'issues'>('rehab_plan');
  const [createFact, setCreateFact] = useState<QualityFact | null>(null);
  const [issueId, setIssueId] = useState<string | null>(null);
  const [issueRefresh, setIssueRefresh] = useState(0);
  const medical = actor.role === 'doctor' || actor.role === 'health_manager';
  useEffect(() => {
    const controller = new AbortController();
    setPatients([]); setPatientError('');
    if (!medical) return () => controller.abort();
    api.get<Patient[]>(actor.role === 'health_manager' ? '/health-managers/patients' : '/doctors/patients', { signal: controller.signal })
      .then(({data}) => { if (!controller.signal.aborted) { if (!Array.isArray(data)) throw new Error('invalid patients'); setPatients(data); } })
      .catch(failure => { if (!controller.signal.aborted) setPatientError(qualityError(failure, '患者目录加载失败，当前仍可查询后端限定的全部授权范围。')); });
    return () => controller.abort();
  }, [actor.role, medical]);
  const apply = () => {
    try { setFilters(qualityFilters(patientId, startDate, endDate)); setFilterError(''); }
    catch (failure) { setFilterError((failure as Error).message); }
  };
  const clear = () => { setPatientId(''); setStartDate(''); setEndDate(''); setFilters({}); setFilterError(''); };
  const patientNames = new Map(patients.map(patient => [patient.id, patient.name]));
  const scopeKey = JSON.stringify(filters);
  return <Container maxWidth="xl"><Stack spacing={2}>
    <Typography variant="h4" component="h1">过程质控工作台</Typography>
    <Typography color="text.secondary">查看真实业务过程，人工核实问题并跟踪整改与复核。临床指标、ICF评分和达标规则仍须按确认口径单独配置。</Typography>
    {!medical && <Alert severity="info">管理员可查看当前记录与处置历史；问题登记、分派和复核由当前获授权的医护操作。</Alert>}
    <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        {medical ? <TextField select label="患者范围" value={patientId} size="small" sx={{ minWidth: 230 }} onChange={event => setPatientId(event.target.value)}>
          <MenuItem value="">全部启用且获授权患者</MenuItem>{patients.map(patient => <MenuItem key={patient.id} value={patient.id}>{patient.name}</MenuItem>)}
        </TextField> : <TextField label="患者编号（选填）" size="small" value={patientId} onChange={event => setPatientId(event.target.value)} />}
        <TextField label="开始日期（选填）" type="date" size="small" value={startDate} onChange={event => setStartDate(event.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField label="结束日期（选填）" type="date" size="small" value={endDate} onChange={event => setEndDate(event.target.value)} InputLabelProps={{ shrink: true }} />
        <Button variant="contained" onClick={apply}>应用筛选</Button><Button onClick={clear}>清除筛选</Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">日期按本地日历日查询，包含所选结束日。日期筛选仅作用过程事实与统计报告。</Typography>
      {patientError && <Alert severity="warning">{patientError}</Alert>}{filterError && <Alert severity="error">{filterError}</Alert>}
    </Stack></Paper>
    <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto" aria-label="质控工作区">
      <Tab value="rehab_plan" label="康复方案过程" /><Tab value="followup" label="随访过程" /><Tab value="issues" label="人工问题处置" />
    </Tabs>
    {tab === 'issues' ? <QualityIssueList key={scopeKey} patientId={filters.patient_id} actor={actor} patientNames={patientNames} refresh={issueRefresh} onOpen={setIssueId} /> :
      <QualityMonitoringPanel key={`${scopeKey}:${tab}`} filters={filters} source={tab} patientNames={patientNames} canCreate={medical}
        onCreate={fact => { if (fact.issue_eligible && fact.source_reference_state === 'valid') setCreateFact(fact); }} />}
    {createFact && medical && <CreateQualityIssueDialog key={`${createFact.source_type}:${createFact.source_id}`} fact={createFact}
      onClose={() => setCreateFact(null)} onCreated={id => { setCreateFact(null); setIssueId(id); setIssueRefresh(value => value + 1); setTab('issues'); }} />}
    {issueId && <QualityIssueDetailDialog key={`${actor.id}:${issueId}`} issueId={issueId} actor={actor} onClose={() => setIssueId(null)} onChanged={() => setIssueRefresh(value => value + 1)} />}
  </Stack></Container>;
}
