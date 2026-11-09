import React, { useEffect, useState } from 'react';
import { Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from '@mui/material';
import { apiService } from '../../services/api';
import type { FollowUpRecord } from '../../types/followup';
import { followUpError } from '../../utils/followupReview';
import { getFollowUpStatusInfo } from '../../constants/followup';

function localDateTime() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export default function FollowUpManualEntryDialog({ followUpId, onClose, onSaved }: {
  followUpId: string | null; onClose: () => void; onSaved: () => void | Promise<void>;
}) {
  const [record, setRecord] = useState<FollowUpRecord | null>(null);
  const [actualDate, setActualDate] = useState('');
  const [result, setResult] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => { setActualDate(localDateTime()); setResult(''); setNotes(''); }, [followUpId]);
  useEffect(() => {
    let cancelled = false;
    setRecord(null); setError(null); setStale(false);
    if (!followUpId) return;
    setLoading(true);
    apiService.getFollowUp(followUpId).then(({ data }) => { if (!cancelled) setRecord(data); })
      .catch(loadError => { if (!cancelled) setError(followUpError(loadError, '加载随访失败。')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [followUpId, reload]);
  const writable = record && ['scheduled', 'awaiting_fill', 'rescheduled'].includes(record.status) && Number.isInteger(record.mutation_version);
  const submit = async () => {
    if (!record || !writable || stale || loading || submitting) return;
    const date = new Date(actualDate);
    if (!actualDate || !Number.isFinite(date.getTime()) || !result.trim()) { setError('请填写有效的实际日期和随访结果。'); return; }
    setSubmitting(true); setError(null);
    try {
      await apiService.completeFollowUp(record.id, { expected_version: record.mutation_version, actual_date: date.toISOString(), follow_up_result: result.trim(), notes: notes.trim() || undefined });
      await onSaved();
    } catch (saveError) {
      if ((saveError as { response?: { status?: number } })?.response?.status === 409) setStale(true);
      setError(followUpError(saveError, '手工录入未保存，请核对后重试。'));
    } finally { setSubmitting(false); }
  };
  return <Dialog open={!!followUpId} onClose={submitting ? undefined : onClose} fullWidth maxWidth="sm">
    <DialogTitle>随访手工录入</DialogTitle>
    <DialogContent dividers><Stack spacing={2}>
      {loading && <CircularProgress size={24} />}
      {error && <Alert severity="error">{error}</Alert>}
      {record && <><Typography>患者：{record.patient_name || record.patient_id}</Typography><Typography>状态：{getFollowUpStatusInfo(record.status).label}</Typography><Typography>随访说明：{record.description || '未提供'}</Typography></>}
      {record && !writable && <Alert severity="warning">当前节点状态或版本不允许录入，请核对后重新加载。</Alert>}
      {stale && <Alert severity="warning">节点已变化，输入已保留。请重新加载并核对最新节点后再次提交。</Alert>}
      <TextField label="实际日期" type="datetime-local" value={actualDate} onChange={event => setActualDate(event.target.value)} InputLabelProps={{ shrink: true }} required disabled={loading || submitting} />
      <TextField label="随访结果" multiline minRows={3} value={result} onChange={event => setResult(event.target.value)} required disabled={loading || submitting} />
      <TextField label="备注" multiline minRows={2} value={notes} onChange={event => setNotes(event.target.value)} disabled={loading || submitting} />
      <Alert severity="info">提交后进入待医护审阅，审阅通过后才算完成随访。</Alert>
    </Stack></DialogContent>
    <DialogActions><Button onClick={() => setReload(value => value + 1)} disabled={loading || submitting}>重新加载节点</Button><Button onClick={onClose} disabled={submitting}>取消</Button><Button variant="contained" onClick={() => void submit()} disabled={!writable || stale || loading || submitting}>提交手工录入</Button></DialogActions>
  </Dialog>;
}
