import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Chip, CircularProgress, Paper, Stack, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import { useNavigate, useParams } from 'react-router-dom';
import type { RootState } from '../store';
import type { FollowUpRecord } from '../types/followup';
import { apiService } from '../services/api';
import { getFollowUpStatusInfo, getFollowUpTypeLabel } from '../constants/followup';
import { canReadFollowUp, followUpDetailError, validFollowUpId, formatFollowUpSchedule } from '../utils/notificationTarget';

/** Deliberately projects the patient-facing appointment summary only. */
export function FollowUpReadOnlySummary({ record }: { record: FollowUpRecord }) {
  return <Stack spacing={2}>
    <Box><Chip label={getFollowUpStatusInfo(record.status).label} /></Box>
    <Typography>随访方式：{getFollowUpTypeLabel(record.follow_up_type)}</Typography>
    <Typography>计划时间：{formatFollowUpSchedule(record.scheduled_date)}</Typography>
    <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>随访说明：{record.description || '未填写'}</Typography>
    <Typography variant="body2" color="text.secondary">如需调整随访安排，请联系负责的医护人员。</Typography>
  </Stack>;
}

export default function FollowUpDetailPage() {
  const actor = useSelector((state: RootState) => state.auth.user);
  const { followUpId } = useParams<{ followUpId: string }>();
  // Changing accounts or records unmounts all fetched data before rendering.
  return <FollowUpDetail key={`${actor?.id}:${actor?.role}:${followUpId}`} actor={actor} followUpId={followUpId} />;
}

function FollowUpDetail({ actor, followUpId }: {
  actor: RootState['auth']['user']; followUpId: string | undefined;
}) {
  const navigate = useNavigate();
  const [record, setRecord] = useState<FollowUpRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setRecord(null); setError(null); setLoading(true);
    if (!canReadFollowUp(actor?.role) || !validFollowUpId(followUpId)) {
      setError('无法查看此随访。'); setLoading(false);
      return;
    }
    // A notification reference is never an authorization grant. Always read
    // the live endpoint, which checks current self/medical patient access.
    apiService.getFollowUp(followUpId).then(({ data }) => {
      if (!cancelled) setRecord(data);
    }).catch(loadError => {
      if (!cancelled) setError(followUpDetailError(loadError));
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [actor?.id, actor?.role, followUpId, reload]);
  const workspace = actor?.role === 'doctor' ? '/app/doctor/follow-ups' :
    actor?.role === 'health_manager' ? '/app/health-manager/follow-ups' : null;
  return <Paper sx={{ p: { xs: 2, md: 3 }, maxWidth: 850, mx: 'auto' }}>
    <Stack spacing={3}>
      <Typography variant="h5" component="h1">随访安排</Typography>
      {loading && <Box role="status"><CircularProgress size={24} aria-label="正在加载随访" /></Box>}
      {error && <Alert severity="error">{error}</Alert>}
      {record && <FollowUpReadOnlySummary record={record} />}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <Button onClick={() => navigate('/app/notifications')}>返回通知中心</Button>
        <Button disabled={loading} onClick={() => setReload(value => value + 1)}>重新加载</Button>
        {workspace && <Button onClick={() => navigate(workspace)}>前往随访工作台</Button>}
      </Stack>
    </Stack>
  </Paper>;
}
