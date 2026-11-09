import React, { useEffect, useState } from 'react';
import { Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material';
import { apiService } from '../../services/api';
import type { FollowUpRecord } from '../../types/followup';
import { canReEvaluateFollowUp, followUpError } from '../../utils/followupReview';
import { getFollowUpStatusInfo, getFollowUpTypeLabel } from '../../constants/followup';
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
  return <Dialog open={!!followUpId} onClose={onClose} fullWidth maxWidth="md">
    <DialogTitle>随访详情</DialogTitle>
    <DialogContent dividers><Stack spacing={2}>
      {loading && <CircularProgress size={24} />}
      {error && <Alert severity="error">{error}</Alert>}
      {record && <>
        <Typography>患者：{record.patient_name || record.patient_id}</Typography>
        <Typography>类型：{getFollowUpTypeLabel(record.follow_up_type)} · 状态：{getFollowUpStatusInfo(record.status).label}</Typography>
        <Typography>计划日期：{record.scheduled_date}</Typography>
        <Typography sx={{ whiteSpace: 'pre-wrap' }}>说明：{record.description || '未提供'}</Typography>
        <FollowUpVisitLinks record={record} onOpen={onOpen} />
        {(record.status === 'completed' || record.status === 'in_review') && <FollowUpReviewEvidence record={record} task={null} />}
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
