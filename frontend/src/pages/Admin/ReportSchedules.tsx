import { useCallback, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Container, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { apiErrorMessage } from '../../services/patientErrors';
import { reportSchedules, type ReportCatalogItem, type ReportFrequency, type ReportSchedule,
  type ReportSchedulePayload } from '../../services/reportSchedules';
import type { RootState } from '../../store';
import { formatAppDate } from '../../utils/dateTime';

const frequencyLabels: Record<ReportFrequency, string> = { once: '单次', daily: '每天', weekly: '每周', monthly: '每月' };
const rangeLabels: Record<string, string> = { day: '日', week: '周', month: '月', quarter: '季度', year: '年' };
const statusLabels: Record<string, string> = {
  ready: '已生成', success: '已生成', error: '失败', failed: '失败',
  running: '生成中', recovering: '正在恢复', pending: '待生成',
};
const PAGE_SIZE = 20;
const timestamp = (value?: string | null) => formatAppDate(value, 'zoned', {
  empty: '—', invalid: '—', assumeUtc: true, timeZone: 'UTC',
});

interface ScheduleForm {
  id?: string;
  name: string;
  reportId: string;
  timeRange: string;
  frequency: ReportFrequency;
  time: string;
  nextRunTime: string;
  weekday: string;
  monthDay: string;
  recipients: string;
}

function formFromSchedule(catalog: ReportCatalogItem[], actorId: string, row?: ReportSchedule): ScheduleForm {
  const next = row?.nextRunTime ? new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(row.nextRunTime) ? row.nextRunTime : `${row.nextRunTime}Z`) : null;
  return {
    id: row?.id, name: row?.name ?? '', reportId: row?.reportId ?? catalog[0]?.id ?? '',
    timeRange: row?.timeRange ?? 'month', frequency: row?.frequency ?? 'daily', time: row?.time ?? '09:00',
    nextRunTime: next && Number.isFinite(next.getTime()) ? next.toISOString().slice(0, 16) : '',
    weekday: String(row?.weekday ?? 1), monthDay: String(row?.monthDay ?? 1),
    recipients: row?.recipients.join(', ') ?? actorId,
  };
}

function ScheduleEditor({ form, catalog, saving, error, onChange, onSave, onClose }: {
  form: ScheduleForm; catalog: ReportCatalogItem[]; saving: boolean; error: string;
  onChange: (form: ScheduleForm) => void; onSave: () => void; onClose: () => void;
}) {
  const catalogItem = catalog.find(item => item.id === form.reportId);
  return <Dialog open onClose={() => { if (!saving) onClose(); }} fullWidth maxWidth="sm">
    <DialogTitle>{form.id ? '编辑报表计划' : '新建报表计划'}</DialogTitle>
    <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
      {error && <Alert severity="error">{error}</Alert>}
      <TextField label="计划名称" value={form.name} required inputProps={{ maxLength: 120 }}
        onChange={event => onChange({ ...form, name: event.target.value })} />
      <TextField select label="报表内容" value={form.reportId} onChange={event => {
        const reportId = event.target.value;
        const ranges = catalog.find(item => item.id === reportId)?.timeRanges ?? [];
        onChange({ ...form, reportId, timeRange: ranges.includes(form.timeRange) ? form.timeRange : ranges[0] || 'month' });
      }}>
        {catalog.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      {!!catalogItem?.timeRanges.length &&
        <TextField select label="数据范围" value={form.timeRange} onChange={event => onChange({ ...form, timeRange: event.target.value })}>
          {catalogItem.timeRanges.map(value => <MenuItem key={value} value={value}>{rangeLabels[value] || value}</MenuItem>)}
        </TextField>}
      <TextField select label="执行频率" value={form.frequency} onChange={event => onChange({ ...form, frequency: event.target.value as ReportFrequency })}>
        {Object.entries(frequencyLabels).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
      </TextField>
      {form.frequency === 'once'
        ? <TextField label="执行日期和时间（UTC）" type="datetime-local" InputLabelProps={{ shrink: true }}
            value={form.nextRunTime} onChange={event => onChange({ ...form, nextRunTime: event.target.value })} />
        : <TextField label="执行时间（UTC）" type="time" InputLabelProps={{ shrink: true }} value={form.time}
            onChange={event => onChange({ ...form, time: event.target.value })} />}
      {form.frequency === 'weekly' && <TextField select label="星期" value={form.weekday} onChange={event => onChange({ ...form, weekday: event.target.value })}>
        {['周日', '周一', '周二', '周三', '周四', '周五', '周六'].map((label, day) => <MenuItem key={day} value={String(day)}>{label}</MenuItem>)}
      </TextField>}
      {form.frequency === 'monthly' && <TextField type="number" label="每月日期" value={form.monthDay} inputProps={{ min: 1, max: 31, step: 1 }}
        helperText="当月没有所选日期时，在该月最后一天执行。"
        onChange={event => onChange({ ...form, monthDay: event.target.value })} />}
      <TextField label="站内接收账号 ID" value={form.recipients} onChange={event => onChange({ ...form, recipients: event.target.value })}
        helperText="默认发给当前账号。多个已授权账号请用逗号分隔。" />
    </Stack></DialogContent>
    <DialogActions><Button onClick={onClose} disabled={saving}>取消</Button>
      <Button variant="contained" disabled={saving || !form.name.trim() || !catalogItem} onClick={onSave}>{saving ? '保存中' : '保存计划'}</Button>
    </DialogActions>
  </Dialog>;
}

function ReportScheduleWorkspace({ actorId }: { actorId: string }) {
  const [form, setForm] = useState<ScheduleForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [page, setPage] = useState(0);
  const loadSchedules = useCallback(async (signal: AbortSignal) => {
    const [catalog, schedules] = await Promise.all([reportSchedules.catalog(signal), reportSchedules.list(signal)]);
    if (!Array.isArray(catalog.data?.items) || !Array.isArray(schedules.data)) throw new Error('报表计划接口响应异常。');
    return { catalog: catalog.data.items, schedules: schedules.data };
  }, []);
  const loadRuns = useCallback(async (signal: AbortSignal) => {
    const { data } = await reportSchedules.runs(page * PAGE_SIZE, PAGE_SIZE, signal);
    if (!Array.isArray(data?.items) || !Number.isSafeInteger(data.total)) throw new Error('报表结果接口响应异常。');
    return data;
  }, [page]);
  const schedules = useAsyncResource(loadSchedules);
  const runs = useAsyncResource(loadRuns);
  const catalog = schedules.data?.catalog ?? [];

  const edit = (row?: ReportSchedule) => { setEditError(''); setForm(formFromSchedule(catalog, actorId, row)); };
  const save = async () => {
    if (!form || saving) return;
    setEditError('');
    const recipients = [...new Set(form.recipients.split(/[,，\s]+/).filter(Boolean))];
    const onceAt = form.nextRunTime ? new Date(`${form.nextRunTime}Z`) : null;
    const monthDay = Number(form.monthDay);
    if (!recipients.length || recipients.some(id => !/^[a-f0-9]{24}$/i.test(id))) {
      setEditError('请填写有效的接收账号 ID。'); return;
    }
    if (form.frequency === 'once' && (!onceAt || !Number.isFinite(onceAt.getTime()) || onceAt.getTime() <= Date.now())) {
      setEditError('请选择未来的 UTC 执行时间。'); return;
    }
    if (form.frequency !== 'once' && !/^([01]\d|2[0-3]):[0-5]\d$/.test(form.time)) {
      setEditError('请填写有效的 UTC 执行时间。'); return;
    }
    if (form.frequency === 'monthly' && (!Number.isInteger(monthDay) || monthDay < 1 || monthDay > 31)) {
      setEditError('每月执行日期需为 1 至 31 日。'); return;
    }
    const body: ReportSchedulePayload = {
      name: form.name.trim(), reportId: form.reportId, timeRange: form.timeRange, frequency: form.frequency,
      recipients, format: 'html',
      ...(form.frequency === 'once' && onceAt ? { nextRunTime: onceAt.toISOString() } : { time: form.time }),
      ...(form.frequency === 'weekly' ? { weekday: Number(form.weekday) } : {}),
      ...(form.frequency === 'monthly' ? { monthDay } : {}),
    };
    setSaving(true);
    try {
      if (form.id) await reportSchedules.update(form.id, body);
      else await reportSchedules.create(body);
      setForm(null);
      schedules.reload();
      runs.reload();
    } catch (error) { setEditError(apiErrorMessage(error, '保存报表计划失败。')); }
    finally { setSaving(false); }
  };

  const toggle = async (row: ReportSchedule) => {
    if (busyId) return;
    setActionError(''); setBusyId(row.id);
    try { await reportSchedules.toggle(row.id, !row.enabled); schedules.reload(); }
    catch (error) { setActionError(apiErrorMessage(error, '更新计划状态失败。')); }
    finally { setBusyId(''); }
  };

  const download = async (id: string) => {
    if (busyId) return;
    setActionError(''); setBusyId(id);
    try {
      const { data } = await reportSchedules.run(id);
      if (data?.id !== id || data.format !== 'html' || typeof data.html !== 'string' || !data.html) throw new Error('报表内容尚不可用。');
      const url = URL.createObjectURL(new Blob([data.html], { type: 'text/html;charset=utf-8' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${data.reportName || '定时报表'}.html`;
      try { anchor.click(); } finally { setTimeout(() => URL.revokeObjectURL(url), 0); }
    } catch (error) { setActionError(apiErrorMessage(error, '下载报表失败。')); }
    finally { setBusyId(''); }
  };

  return <Container maxWidth="lg"><Stack spacing={2.5}>
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1}>
      <Box><Typography variant="h5" component="h1">定时报表</Typography>
        <Typography color="text.secondary">系统按设定的 UTC 时间生成报表，授权账号可在这里下载 HTML 文件。</Typography></Box>
      <Stack direction="row" spacing={1}>
        <Button onClick={() => { schedules.reload(); runs.reload(); }}>刷新</Button>
        <Button variant="contained" onClick={() => edit()} disabled={!catalog.length}>新建计划</Button>
      </Stack>
    </Stack>
    {actionError && <Alert severity="error">{actionError}</Alert>}
    <Typography variant="h6" component="h2">报表计划</Typography>
    {schedules.loading && <CircularProgress size={24} aria-label="正在读取计划" />}
    {!!schedules.error && <Alert severity="error" action={<Button onClick={schedules.reload}>重试</Button>}>
      {apiErrorMessage(schedules.error, '读取报表计划失败。')}
    </Alert>}
    {schedules.data?.schedules.length === 0 && <Alert severity="info">暂无报表计划。</Alert>}
    {schedules.data?.schedules.map(row => {
      const operational = row.executionVersion === 1;
      return <Card variant="outlined" key={row.id}><CardContent><Stack spacing={1}>
        <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
          <Typography variant="h6">{row.name}</Typography>
          <Chip size="small" label={operational ? row.enabled ? '已启用' : '已停用' : '历史计划'} />
        </Stack>
        <Typography variant="body2">{catalog.find(item => item.id === row.reportId)?.label || row.reportName || row.reportId} · {frequencyLabels[row.frequency] || row.frequency}</Typography>
        {operational && <Typography variant="body2" color="text.secondary">下次执行 {row.enabled ? timestamp(row.nextRunTime) : '—'} · 最近执行 {timestamp(row.lastRunTime)}{row.lastRunStatus ? `（${statusLabels[row.lastRunStatus] || row.lastRunStatus}）` : ''}</Typography>}
        {operational && <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => edit(row)}>编辑</Button>
          {(row.enabled || row.frequency !== 'once' || row.nextRunTime) &&
            <Button size="small" disabled={!!busyId} onClick={() => void toggle(row)}>{row.enabled ? '停用' : '启用'}</Button>}
        </Stack>}
      </Stack></CardContent></Card>;
    })}
    <Divider />
    <Typography variant="h6" component="h2">报表结果</Typography>
    {runs.loading && <CircularProgress size={24} aria-label="正在读取报表结果" />}
    {!!runs.error && <Alert severity="error" action={<Button onClick={runs.reload}>重试</Button>}>
      {apiErrorMessage(runs.error, '读取报表结果失败。')}
    </Alert>}
    {runs.data?.items.length === 0 && <Alert severity="info">暂无报表结果。</Alert>}
    {runs.data?.items.map(row => <Card key={row.id} variant="outlined"><CardContent><Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Box sx={{ flexGrow: 1 }}><Typography>{row.reportName || row.reportId}</Typography>
        <Typography variant="body2" color="text.secondary">计划执行 {timestamp(row.scheduledFor)} · 生成 {timestamp(row.generatedAt)}</Typography></Box>
      <Chip size="small" label={statusLabels[row.status] || row.status} />
      {row.generatedAt && row.format === 'html' && ['ready', 'success'].includes(row.status) &&
        <Button disabled={!!busyId} onClick={() => void download(row.id)}>下载 HTML</Button>}
    </Stack></CardContent></Card>)}
    {(page > 0 || (runs.data && runs.data.total > PAGE_SIZE)) && <Stack direction="row" alignItems="center" spacing={2}>
      <Button disabled={runs.loading || page === 0} onClick={() => setPage(value => value - 1)}>上一页</Button>
      <Typography variant="body2">第 {page + 1} 页</Typography>
      <Button disabled={runs.loading || !runs.data || (page + 1) * PAGE_SIZE >= runs.data.total}
        onClick={() => setPage(value => value + 1)}>下一页</Button>
    </Stack>}
    {form && <ScheduleEditor form={form} catalog={catalog} error={editError} saving={saving} onChange={setForm}
      onSave={() => void save()} onClose={() => setForm(null)} />}
  </Stack></Container>;
}

export default function ReportSchedules() {
  const actor = useSelector((state: RootState) => state.auth.user);
  return actor ? <ReportScheduleWorkspace key={actor.id} actorId={actor.id} /> : null;
}
