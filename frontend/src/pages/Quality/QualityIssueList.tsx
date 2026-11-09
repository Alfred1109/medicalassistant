import React, { useEffect, useState } from 'react';
import { Alert, Button, Checkbox, CircularProgress, FormControlLabel, MenuItem, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Typography } from '@mui/material';
import { qualityApi } from '../../services/quality';
import type { QualityIssue, QualityPage } from '../../types/quality';
import { issueStatusLabels, qualityError, qualityTime } from '../../utils/quality';

export default function QualityIssueList({ patientId, actor, patientNames, onOpen, refresh }: {
  patientId?: string; actor: {id: string; role: string}; patientNames: Map<string, string>;
  onOpen: (id: string) => void; refresh: number;
}) {
  const [status, setStatus] = useState('');
  const [mine, setMine] = useState(false);
  const [page, setPage] = useState(0);
  const [limit, setLimit] = useState(20);
  const [response, setResponse] = useState<QualityPage<QualityIssue> | null>(null);
  const [responseKey, setResponseKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const key = JSON.stringify([patientId, status, mine, page, limit]);
  useEffect(() => {
    const controller = new AbortController();
    setResponse(null); setLoading(true); setError('');
    qualityApi.issues({patient_id: patientId, status: status || undefined,
      assignee_id: mine ? actor.id : undefined, skip: page * limit, limit}, controller.signal).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (!data || !Array.isArray(data.items) || !Number.isSafeInteger(data.total) || data.total < data.items.length
          || data.skip !== page * limit || data.limit !== limit || data.items.length > limit
          || data.items.some(row => !row.id || !(row.status in issueStatusLabels) || (patientId && row.patient_id !== patientId))) throw new Error('invalid issue list');
      const last = Math.max(0, Math.ceil(data.total / limit) - 1);
      if (page > last) { setPage(last); return; }
      setResponse(data); setResponseKey(key);
    }).catch(failure => { if (!controller.signal.aborted) setError(qualityError(failure, '问题列表加载失败，请重试。')); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  // key contains all applied filters and paging.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, refresh, reload, actor.id]);
  const visible = responseKey === key ? response : null;
  return <Stack spacing={2}>
    <Stack direction={{ xs: 'column', sm: 'row' }} alignItems={{ sm: 'center' }} spacing={2}>
      <TextField select label="问题状态" size="small" value={status} onChange={event => { setStatus(event.target.value); setPage(0); }} sx={{ minWidth: 160 }}>
        <MenuItem value="">全部状态</MenuItem>{Object.entries(issueStatusLabels).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
      </TextField>
      {actor.role !== 'admin' && <FormControlLabel control={<Checkbox checked={mine} onChange={event => { setMine(event.target.checked); setPage(0); }} />} label="只看分派给我" />}
      <Button disabled={loading} onClick={() => setReload(value => value + 1)}>刷新问题列表</Button>
    </Stack>
    <Typography variant="body2" color="text.secondary">问题均由医护人工核实登记。此列表使用患者与状态筛选，过程统计的日期筛选不限制问题历史。</Typography>
    {loading && <CircularProgress size={24} aria-label="正在加载过程问题" />}{error && <Alert severity="error" action={<Button onClick={() => setReload(value => value + 1)}>重试</Button>}>{error}</Alert>}
    {visible && <>
      {visible.items.length === 0 ? <Alert severity="info">当前范围暂无可查看问题，不能据此判定没有历史问题或过程已达标。</Alert> : <TableContainer component={Paper} variant="outlined"><Table sx={{ minWidth: 650 }} size="small" aria-label="人工问题处置列表">
        <TableHead><TableRow><TableCell>问题</TableCell><TableCell>患者</TableCell><TableCell>状态</TableCell><TableCell>更新时间</TableCell><TableCell>操作</TableCell></TableRow></TableHead>
        <TableBody>{visible.items.map(issue => <TableRow key={issue.id}>
          <TableCell sx={{ maxWidth: 280, overflowWrap: 'anywhere' }}>{issue.title}</TableCell><TableCell sx={{ maxWidth: 220, overflowWrap: 'anywhere' }}>{patientNames.get(issue.patient_id) || issue.patient_id}</TableCell>
          <TableCell>{issueStatusLabels[issue.status]}</TableCell><TableCell>{qualityTime(issue.updated_at)}</TableCell>
          <TableCell><Button size="small" onClick={() => onOpen(issue.id)}>查看处置</Button></TableCell>
        </TableRow>)}</TableBody>
      </Table></TableContainer>}
      <TablePagination component="div" count={visible.total} page={page} rowsPerPage={limit} rowsPerPageOptions={[20, 50, 100]}
        onPageChange={(_, next) => setPage(next)} onRowsPerPageChange={event => { setLimit(Number(event.target.value)); setPage(0); }}
        labelRowsPerPage="每页行数" labelDisplayedRows={({ from, to, count }) => `${from}-${to} 共 ${count}`} />
    </>}
  </Stack>;
}
