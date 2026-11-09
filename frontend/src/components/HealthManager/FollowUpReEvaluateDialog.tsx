import React, { useEffect, useState } from 'react';
import { Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from '@mui/material';
import { apiService } from '../../services/api';
import type { FollowUpRecord } from '../../types/followup';
import { canReEvaluateFollowUp, followUpError } from '../../utils/followupReview';
import { getFollowUpStatusInfo } from '../../constants/followup';
import FollowUpVisitLinks from './FollowUpVisitLinks';

export default function FollowUpReEvaluateDialog({ followUpId, actor, onClose, onCreated }: {
  followUpId: string | null; actor: { id: string; role: string } | null;
  onClose: () => void; onCreated: (record: FollowUpRecord) => void | Promise<void>;
}) {
  const [record, setRecord] = useState<FollowUpRecord | null>(null);
  const [date, setDate] = useState('');
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => { setDate(''); setReason(''); }, [followUpId]);
  useEffect(() => {
    let cancelled = false;
    setRecord(null); setError(null); setStale(false);
    if (!followUpId) return;
    setLoading(true);
    apiService.getFollowUp(followUpId).then(({ data }) => { if (!cancelled) setRecord(data); })
      .catch(loadError => { if (!cancelled) setError(followUpError(loadError, '加载原随访失败。')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [followUpId, reload]);
  const allowed = record && canReEvaluateFollowUp(record, actor);
  const submit = async () => {
    if (!record || !allowed || submitting || loading || stale) return;
    const scheduledDate = new Date(date);
    if (!date || !Number.isFinite(scheduledDate.getTime())) { setError('请选择有效的复评计划日期。'); return; }
    setSubmitting(true); setError(null);
    try {
      const { data } = await apiService.reEvaluateFollowUp(record.id, {
        scheduled_date: scheduledDate.toISOString(), ...(reason.trim() ? { reason: reason.trim() } : {}),
      });
      await onCreated(data);
    } catch (saveError) {
      if ((saveError as { response?: { status?: number } })?.response?.status === 409) setStale(true);
      setError(followUpError(saveError, '复评节点创建未确认，请保留输入并核查后重试。'));
    } finally { setSubmitting(false); }
  };
  return <Dialog open={!!followUpId} onClose={submitting ? undefined : onClose} fullWidth maxWidth="sm">
    <DialogTitle>发起复评</DialogTitle>
    <DialogContent dividers><Stack spacing={2}>
      {loading && <CircularProgress size={24} />}
      {error && <Alert severity="error">{error}</Alert>}
      {record && <>
        <Typography>患者：{record.patient_name || record.patient_id}</Typography>
        <Typography>原节点状态：{getFollowUpStatusInfo(record.status).label}</Typography>
        <Typography>原随访说明：{record.description || '未提供'}</Typography>
        <FollowUpVisitLinks record={record} />
      </>}
      {record && !allowed && <Alert severity="warning">当前账号、节点状态或已有后继关联不允许再次发起复评。</Alert>}
      {stale && <Alert severity="warning">节点已变化，请重新加载并核查后继关联后继续。输入已保留。</Alert>}
      <TextField label="复评计划日期" type="datetime-local" required value={date} onChange={event => setDate(event.target.value)} InputLabelProps={{ shrink: true }} disabled={submitting || loading} />
      <TextField label="复评说明" multiline minRows={3} value={reason} onChange={event => setReason(event.target.value)} disabled={submitting || loading} />
      <Alert severity="info">将新建随访节点，继承原节点的责任人、类型和既有表单配置。原节点结果与历史将保留。</Alert>
    </Stack></DialogContent>
    <DialogActions>
      <Button disabled={loading || submitting} onClick={() => setReload(value => value + 1)}>重新加载</Button>
      <Button disabled={submitting} onClick={onClose}>取消</Button>
      <Button variant="contained" disabled={!allowed || stale || loading || submitting} onClick={() => void submit()}>创建复评节点</Button>
    </DialogActions>
  </Dialog>;
}
