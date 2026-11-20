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
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { patientClinical } from '../../services/patientClinical';
import { apiErrorMessage } from '../../services/patientErrors';
import { formatAppDate } from '../../utils/dateTime';

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

const PAGE_SIZE = 20;

function FollowUpHistory({ accountId }: { accountId: string }) {
  const navigate = useNavigate();
  const [page, setPage] = React.useState(0);
  const load = React.useCallback(async (signal: AbortSignal) => {
    const patientId = await patientClinical.selfId(signal);
    const { data } = await apiService.getFollowUps(patientId, { skip: page * PAGE_SIZE, limit: PAGE_SIZE + 1 }, signal);
    if (!Array.isArray(data)) throw new Error('随访接口返回的数据格式无效');
    return { records: sortFollowUpsByScheduled(data.slice(0, PAGE_SIZE)), hasNext: data.length > PAGE_SIZE };
  }, [page]);
  const { data, error, loading, reload } = useAsyncResource(load, Boolean(accountId));
  const records = data?.records ?? [];

  return (
    <Paper sx={{ p: { xs: 2, md: 3 }, maxWidth: 850, mx: 'auto' }}>
      <Stack spacing={2}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <EventNoteIcon color="primary" />
          <Typography variant="h5" component="h1">我的随访</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary">
          查看医护为你安排的随访。如需调整时间或补填信息，请联系负责的医护人员。
        </Typography>
        {loading && <Box role="status"><CircularProgress size={24} aria-label="正在加载随访记录" /></Box>}
        {!!error && <Alert severity="error" action={<Button onClick={reload}>重试</Button>}>{apiErrorMessage(error, '随访记录加载失败')}</Alert>}
        {data && records.length === 0 && (
          <Alert severity="info">{page > 0 ? '本页没有随访记录。' : '目前没有你的随访记录。'}</Alert>
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
                计划时间：{formatAppDate(record.scheduled_date, 'minute', { empty: '待定', invalid: '待定' })}
              </Typography>
              {record.description && (
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', mt: 0.5 }}>
                  说明：{record.description}
                </Typography>
              )}
            </Box>
          );
        })}
        {(page > 0 || data?.hasNext) && <Stack direction="row" spacing={2} alignItems="center" justifyContent="center">
          <Button disabled={loading || page === 0} onClick={() => setPage(page - 1)}>上一页</Button>
          <Typography variant="body2">第 {page + 1} 页</Typography>
          <Button disabled={loading || !data?.hasNext} onClick={() => setPage(page + 1)}>下一页</Button>
        </Stack>}
      </Stack>
    </Paper>
  );
}

export default function MyFollowUps() {
  const accountId = useSelector((state: RootState) => state.auth.user?.id) || '';
  return <FollowUpHistory key={accountId} accountId={accountId} />;
}
