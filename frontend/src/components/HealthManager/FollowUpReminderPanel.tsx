import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Divider, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, Typography } from '@mui/material';
import { followupReminders } from '../../services/followupReminders';
import type { FollowUpReminderPage, FollowUpReminderStatus } from '../../types/followupReminders';
import { followUpError } from '../../utils/followupReview';
import { reminderReason, reminderServiceInfo, reminderTime } from '../../utils/followupReminders';

const LIMIT = 20;
type State = { key: string; loading: boolean; runtime: FollowUpReminderStatus | null; history: FollowUpReminderPage | null; runtimeError: string | null; historyError: string | null };

export function FollowUpReminderSummary({ runtime, history, runtimeError, historyError }: Omit<State, 'key' | 'loading'>) {
  const info = runtime ? reminderServiceInfo(runtime) : null;
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return <Stack spacing={1.5}>
    {runtimeError && <Alert severity="error">{runtimeError}</Alert>}
    {info && <Alert severity={info.severity}>{info.text}</Alert>}
    {runtime && <Typography variant="body2" color="text.secondary">最近检查：{reminderTime(runtime.last_checked_at)}；最近成功：{reminderTime(runtime.last_success_at)}</Typography>}
    <Typography variant="body2" color="text.secondary">以下结果仅表示是否已生成站内通知，不代表收件人已收到或阅读。时间按本地时区（{zone}）显示；历史记录可能对应调整前的安排。</Typography>
    {historyError && <Alert severity="error">{historyError}</Alert>}
    {history && history.items.length === 0 && <Alert severity="info">本页暂无提醒处理记录，不能据此认定已生成通知。</Alert>}
    {history && (['patient', 'provider'] as const).filter(slot => !history.items.some(item => item.slot === slot)).map(slot => <Typography key={slot} variant="body2" color="text.secondary">{slot === 'patient' ? '患者' : '责任医护'}：{history.total > history.items.length ? '本页未包含该类收件人的处理记录。' : '暂无处理记录；尚不能确认未生成的具体原因。'}</Typography>)}
    {history && history.items.length > 0 && <TableContainer><Table size="small" aria-label="随访提醒处理记录" sx={{ minWidth: 650 }}>
      <TableHead><TableRow><TableCell>收件人类型</TableCell><TableCell>处理结果</TableCell><TableCell>计划时间</TableCell><TableCell>检查时间</TableCell></TableRow></TableHead>
      <TableBody>{history.items.map((item, index) => <TableRow key={`${item.slot}:${item.planned_at}:${item.checked_at}:${index}`}>
        <TableCell>{item.slot === 'patient' ? '患者' : item.slot === 'provider' ? '责任医护' : '未识别的收件人类型'}</TableCell>
        <TableCell>{item.status === 'persisted' ? '已生成站内通知' : item.status === 'skipped' || item.status === 'failed' ? <><Typography variant="body2">{item.status === 'failed' ? '生成失败，计划时间前会自动重试' : '未生成通知'}</Typography><Typography variant="caption" color="text.secondary">{reminderReason(item.reason)}</Typography></> : '未识别的处理结果，请核查'}</TableCell>
        <TableCell>{reminderTime(item.planned_at)}</TableCell><TableCell>{reminderTime(item.checked_at)}</TableCell>
      </TableRow>)}</TableBody>
    </Table></TableContainer>}
  </Stack>;
}

export default function FollowUpReminderPanel({ followUpId, actor }: { followUpId: string; actor: { id: string; role: string } }) {
  const [page, setPage] = useState(0);
  const [reload, setReload] = useState(0);
  const identity = `${actor.id}:${actor.role}`;
  const key = JSON.stringify([identity, followUpId, page]);
  const [state, setState] = useState<State>({ key: '', loading: false, runtime: null, history: null, runtimeError: null, historyError: null });
  const generation = useRef(0);
  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    const empty = { key, runtime: null, history: null, runtimeError: null, historyError: null };
    setState({ ...empty, loading: true });
    void Promise.allSettled([followupReminders.status(controller.signal), followupReminders.history(followUpId, page * LIMIT, LIMIT, controller.signal)]).then(([runtime, history]) => {
      if (controller.signal.aborted || generation.current !== current) return;
      const next: State = { ...empty, loading: false };
      if (runtime.status === 'fulfilled' && typeof runtime.value.data?.enabled === 'boolean' && typeof runtime.value.data?.running === 'boolean' && typeof runtime.value.data?.state === 'string') next.runtime = runtime.value.data;
      else next.runtimeError = runtime.status === 'rejected' ? followUpError(runtime.reason, '无法读取提醒服务状态，请重试。') : '提醒服务状态格式异常，请重试。';
      if (history.status === 'fulfilled') {
        const data = history.value.data;
        if (data && Array.isArray(data.items) && Number.isSafeInteger(data.total) && data.total >= data.items.length && data.skip === page * LIMIT && data.limit === LIMIT
            && data.items.length <= LIMIT && data.items.every(item => item && typeof item === 'object' && item.followup_id === followUpId && typeof item.slot === 'string' && typeof item.status === 'string' && typeof item.planned_at === 'string' && typeof item.checked_at === 'string')) {
          const last = Math.max(0, Math.ceil(data.total / LIMIT) - 1);
          if (page > last) { setPage(last); return; }
          next.history = data;
        } else next.historyError = '提醒处理记录格式异常，请重试。';
      } else next.historyError = followUpError(history.reason, '无法读取提醒处理记录，可能已无访问权限。');
      setState(next);
    });
    return () => { generation.current++; controller.abort(); };
  }, [identity, followUpId, key, page, reload]);
  const visible: State = state.key === key ? state : { key, loading: true, runtime: null, history: null, runtimeError: null, historyError: null };
  return <Box sx={{ minWidth: 0 }}>
    <Divider sx={{ my: 1 }} />
    <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1} sx={{ mb: 1.5 }}><Typography variant="h6">随访提醒</Typography><Button onClick={() => setReload(value => value + 1)} disabled={visible.loading}>重新查询提醒</Button></Stack>
    {visible.loading ? <CircularProgress size={24} aria-label="正在查询提醒" /> : <FollowUpReminderSummary runtime={visible.runtime} history={visible.history} runtimeError={visible.runtimeError} historyError={visible.historyError} />}
    {!visible.loading && visible.history && visible.history.total > LIMIT && <TablePagination component="div" count={visible.history.total} page={page} rowsPerPage={LIMIT} rowsPerPageOptions={[]} onPageChange={(_, next) => setPage(next)} labelDisplayedRows={({ from, to, count }) => `${from}-${to} 共 ${count}`} />}
  </Box>;
}
