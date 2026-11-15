import React from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import EventNoteIcon from '@mui/icons-material/EventNote';
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import type { RootState } from '../../store';
import { apiService } from '../../services/api';
import type { FollowUpRecord } from '../../types/followup';
import { getFollowUpStatusInfo, getFollowUpTypeLabel } from '../../constants/followup';

// 与通知中心跳转的 /app/follow-ups/:id 共享详情页同一条只读链路：
// 详情由该页面经 GET /health-records/followups/{id} 读取，后端做患者 self 授权。
export function canOpenFollowUpDetail(record: Pick<FollowUpRecord, 'id'> | null | undefined): boolean {
  return typeof record?.id === 'string' && /^[a-f\d]{24}$/i.test(record.id);
}

export function sortFollowUpsByScheduled(records: FollowUpRecord[]): FollowUpRecord[] {
  // 计划时间升序；缺时间的记录（待定）排在最后，不与有时间记录混排。
  return [...records].sort((left, right) => {
    const leftKey = left.scheduled_date || '9999-12-31';
    const rightKey = right.scheduled_date || '9999-12-31';
    return leftKey.localeCompare(rightKey);
  });
}

const MyFollowUps: React.FC = () => {
  const user = useSelector((state: RootState) => state.auth.user);
  const navigate = useNavigate();
  const [records, setRecords] = React.useState<FollowUpRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async (signal?: AbortSignal) => {
    if (!user?.id) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await apiService.getFollowUps(user.id);
      setRecords(sortFollowUpsByScheduled(Array.isArray(data) ? data : []));
    } catch (err: any) {
      if (!signal?.aborted) {
        setRecords([]);
        setError(err?.response?.data?.detail || err?.message || '随访记录加载失败');
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [user?.id]);

  React.useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <Paper sx={{ p: { xs: 2, md: 3 }, maxWidth: 850, mx: 'auto' }}>
      <Stack spacing={2}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <EventNoteIcon color="primary" />
          <Typography variant="h5" component="h1">我的随访</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary">
          这里是医护人员为你安排的随访安排（只读）。如需调整时间或补填信息，请联系负责的医护人员。
        </Typography>
        {loading && <Box role="status"><CircularProgress size={24} aria-label="正在加载随访记录" /></Box>}
        {error && <Alert severity="error">{error}</Alert>}
        {!loading && !error && records.length === 0 && (
          <Alert severity="info">目前没有你的随访记录。</Alert>
        )}
        {records.map(record => {
          const status = getFollowUpStatusInfo(record.status);
          return (
            <Box key={record.id} sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
                <Chip size="small" color={status.color} label={status.label} />
                <Typography sx={{ flexGrow: 1 }}>{getFollowUpTypeLabel(record.follow_up_type)}</Typography>
                {canOpenFollowUpDetail(record) && (
                  <Button size="small" onClick={() => navigate(`/app/follow-ups/${record.id}`)}>
                    查看详情
                  </Button>
                )}
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                计划时间：{record.scheduled_date || '待定'}
              </Typography>
              {record.description && (
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', mt: 0.5 }}>
                  说明：{record.description}
                </Typography>
              )}
            </Box>
          );
        })}
      </Stack>
    </Paper>
  );
};

export default MyFollowUps;
