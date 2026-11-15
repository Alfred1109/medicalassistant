import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from '@mui/material';
import { apiService } from '../../services/api';
import type { FollowUpRecord, FollowUpSummaryPayload } from '../../types/followup';
import { canReEvaluateFollowUp, followUpError } from '../../utils/followupReview';
import { getFollowUpStatusBadge, getFollowUpTypeLabel, getFollowUpSummaryRows, getOverdueMarker, getLostMarker } from '../../constants/followup';
import FollowUpVisitLinks from './FollowUpVisitLinks';
import { FollowUpReviewEvidence } from './FollowUpReviewDialog';
import FollowUpReminderPanel from './FollowUpReminderPanel';

type Props = {
  followUpId: string | null; actor: { id: string; role: string } | null;
  onClose: () => void; onOpen: (id: string) => void; onReEvaluate: (id: string) => void;
};

export default function FollowUpDetailsDialog(props: Props) {
  return <FollowUpDetailsContent key={`${props.actor?.id}:${props.actor?.role}:${props.followUpId}`} {...props} />;
}

// T73 随访小结编辑（待审阅/已完成节点；重复提交覆盖，后端审计留痕）
function FollowUpSummaryEditor({ record, actor, onSaved }: {
  record: FollowUpRecord; actor: { id: string; role: string } | null; onSaved: () => void;
}) {
  const summary = record.followup_summary;
  const [open, setOpen] = useState(false);
  const [conclusion, setConclusion] = useState(summary?.conclusion ?? '');
  const [nextPlan, setNextPlan] = useState(summary?.next_plan_suggestion ?? '');
  const [abnormal, setAbnormal] = useState(summary?.abnormal_findings ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!actor || !['doctor', 'health_manager', 'admin'].includes(actor.role)
      || !['in_review', 'completed'].includes(record.status)) return null;
  const save = async () => {
    if (!conclusion.trim()) { setError('请填写随访结论'); return; }
    try {
      setSaving(true); setError(null);
      const payload: FollowUpSummaryPayload = {
        conclusion: conclusion.trim(),
        next_plan_suggestion: nextPlan.trim() || undefined,
        abnormal_findings: abnormal.trim() || undefined,
      };
      await apiService.setFollowUpSummary(record.id, payload);
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(followUpError(err, '随访小结保存失败，请重试。'));
    } finally { setSaving(false); }
  };
  return <>
    <Button size="small" onClick={() => setOpen(true)}>{summary ? '修改随访小结' : '填写随访小结'}</Button>
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>随访小结</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField fullWidth required multiline rows={3} label="结论"
            value={conclusion} onChange={event => setConclusion(event.target.value)} />
          <TextField fullWidth multiline rows={2} label="下次计划建议（可选）"
            value={nextPlan} onChange={event => setNextPlan(event.target.value)} />
          <TextField fullWidth multiline rows={2} label="异常记录（可选）"
            value={abnormal} onChange={event => setAbnormal(event.target.value)} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>取消</Button>
        <Button variant="contained" disabled={saving} onClick={save}>保存</Button>
      </DialogActions>
    </Dialog>
  </>;
}

function FollowUpDetailsContent({ followUpId, actor, onClose, onOpen, onReEvaluate }: Props) {
  const [record, setRecord] = useState<FollowUpRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setRecord(null); setError(null);
    if (!followUpId) return;
    setLoading(true);
    apiService.getFollowUp(followUpId).then(({ data }) => { if (!cancelled) setRecord(data); })
      .catch(loadError => { if (!cancelled) setError(followUpError(loadError, '无法读取该访视，可能已无访问权限。')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [followUpId, reload]);
  const summaryRows = record ? getFollowUpSummaryRows(record.followup_summary) : [];
  return <Dialog open={!!followUpId} onClose={onClose} fullWidth maxWidth="md">
    <DialogTitle>随访详情</DialogTitle>
    <DialogContent dividers><Stack spacing={2}>
      {loading && <CircularProgress size={24} />}
      {error && <Alert severity="error">{error}</Alert>}
      {record && <>
        <Typography>患者：{record.patient_name || record.patient_id}</Typography>
        <Typography>类型：{getFollowUpTypeLabel(record.follow_up_type)} · 状态：{getFollowUpStatusBadge(record).label}</Typography>
        {record.status === 'overdue' && (() => {
          const marker = getOverdueMarker(record.metadata);
          if (marker?.source === 'automated') return <Typography variant="body2" color="text.secondary">逾期来源：系统按后台规则自动标记（阈值口径待临床确认）</Typography>;
          if (marker?.operator_id) return <Typography variant="body2" color="text.secondary">逾期来源：医护手工标记</Typography>;
          return null;
        })()}
        {record.status === 'lost' && (() => {
          const marker = getLostMarker(record.metadata);
          if (marker?.restored_at) return <Typography variant="body2" color="text.secondary">该随访曾被人工恢复（恢复人 {marker.restored_by ?? '未知'}）</Typography>;
          return null;
        })()}
        <Typography>计划日期：{record.scheduled_date}</Typography>
        <Typography sx={{ whiteSpace: 'pre-wrap' }}>说明：{record.description || '未提供'}</Typography>
        {summaryRows.length > 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>随访小结</Typography>
            {summaryRows.map(row => (
              <Typography key={row.label} variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                {row.label}：{row.value}
              </Typography>
            ))}
            {record.followup_summary?.recorded_at && (
              <Typography variant="caption" color="text.secondary">
                记录于 {record.followup_summary.recorded_at}
                {record.followup_summary.recorded_by ? ` · 记录人 ${record.followup_summary.recorded_by}` : ''}
              </Typography>
            )}
          </Box>
        )}
        <FollowUpVisitLinks record={record} onOpen={onOpen} />
        {(record.status === 'completed' || record.status === 'in_review') && <FollowUpReviewEvidence record={record} task={null} />}
        {record && ['doctor', 'health_manager', 'admin'].includes(actor?.role ?? '') && (
          <FollowUpSummaryEditor record={record} actor={actor} onSaved={() => setReload(value => value + 1)} />
        )}
        {actor && ['doctor', 'health_manager', 'admin'].includes(actor.role) && <FollowUpReminderPanel key={`${actor.id}:${record.id}`} followUpId={record.id} actor={actor} />}
      </>}
    </Stack></DialogContent>
    <DialogActions>
      <Button onClick={() => setReload(value => value + 1)} disabled={loading}>重新加载</Button>
      <Button onClick={onClose}>关闭</Button>
      {record && canReEvaluateFollowUp(record, actor) && <Button variant="contained" onClick={() => onReEvaluate(record.id)}>发起复评</Button>}
    </DialogActions>
  </Dialog>;
}
