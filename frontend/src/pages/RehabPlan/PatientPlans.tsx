import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, CircularProgress, Container, Divider, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import { useNavigate, useParams } from 'react-router-dom';
import type { RootState } from '../../store';
import { rehabPublications, type PatientRehabFeedback, type PublishedRehabPlan, type RehabInterventionType } from '../../services/rehabPublications';

const categories: Record<RehabInterventionType, string> = {
  diet: '饮食', exercise: '运动', medication: '用药', psychology: '心理',
};
const labels: Record<string, string> = {
  days_per_week: '每周天数', sets: '组数', reps: '每组次数', repetitions: '每组次数',
  duration_minutes: '时长（分钟）', frequency: '频率', time_of_day: '时间',
  drug_ref: '药品', dosage: '剂量', route: '给药方式', monitoring: '监测要求',
  meal_structure_ref: '膳食安排', energy_target: '能量目标', nutrient_targets: '营养目标',
  food_restrictions: '食物限制', modality_ref: '干预形式', session_plan: '会话安排',
  instrument_refs: '量表',
};

function newRequestId(): string {
  if (!globalThis.crypto || typeof globalThis.crypto.getRandomValues !== 'function') {
    throw new Error('当前浏览器无法安全生成提交标识，请更换浏览器后重试。');
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (Array.isArray(value)) return value.map(displayValue).filter(Boolean).join('、');
  if (typeof value === 'object') return Object.entries(value as Record<string, unknown>)
    .filter(([, item]) => displayValue(item)).map(([key, item]) => `${labels[key] || key}：${displayValue(item)}`).join('；');
  return String(value);
}

function dateText(value?: string | null): string {
  if (!value) return '未填写';
  // Dates may be calendar dates; preserve those without shifting time zones.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

export function validPatientPlan(value: unknown, expectedId?: string): value is PublishedRehabPlan {
  if (!value || typeof value !== 'object') return false;
  const plan = value as PublishedRehabPlan;
  return typeof plan.id === 'string' && /^[a-f\d]{24}$/i.test(plan.id)
    && (!expectedId || plan.id.toLowerCase() === expectedId.toLowerCase())
    && typeof plan.version_id === 'string' && /^[a-f\d]{24}$/i.test(plan.version_id)
    && Number.isSafeInteger(plan.publication_revision) && plan.publication_revision >= 0
    && typeof plan.published_at === 'string' && Boolean(plan.content) && typeof plan.content.name === 'string'
    && Array.isArray(plan.items) && plan.items.every(item => item && typeof item === 'object'
      && typeof item.item_id === 'string' && /^[a-f\d]{24}$/i.test(item.item_id)
      && Object.prototype.hasOwnProperty.call(categories, item.intervention_type) && typeof item.name === 'string');
}

export function feedbackReference(record: PatientRehabFeedback, plan: PublishedRehabPlan): string {
  if (record.version_id === plan.version_id) {
    const item = plan.items.find(entry => entry.item_id === record.prescription_item_id);
    if (item) return `当前发布方案 · ${categories[item.intervention_type]} · ${item.name}`;
  }
  return `历史发布版本 ${record.version_id} · 处方 ${record.prescription_item_id}`;
}

export function validPatientFeedback(value: unknown, planId: string, accountId: string): value is PatientRehabFeedback {
  if (!value || typeof value !== 'object') return false;
  const record = value as PatientRehabFeedback & { plan_id?: string; recorded_by?: string };
  return record.plan_id === planId && record.recorded_by === accountId
    && typeof record.id === 'string' && /^[a-f\d]{24}$/i.test(record.id)
    && typeof record.version_id === 'string' && /^[a-f\d]{24}$/i.test(record.version_id)
    && typeof record.prescription_item_id === 'string' && /^[a-f\d]{24}$/i.test(record.prescription_item_id)
    && ['completed', 'partial', 'not_done'].includes(record.execution_status)
    && typeof record.feelings === 'string' && typeof record.performed_at === 'string';
}

function FeedbackForm({ plan, itemId, onSaved, onUnavailable }: { plan: PublishedRehabPlan; itemId: string; onSaved: () => void; onUnavailable: () => void }) {
  const [status, setStatus] = useState<PatientRehabFeedback['execution_status'] | ''>('');
  const [feelings, setFeelings] = useState('');
  const [when, setWhen] = useState('');
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const attempt = useRef<string | null>(null);
  const changed = () => { attempt.current = null; setMessage(''); setError(''); };
  const submit = async () => {
    if (!status || !feelings.trim() || !when || Number.isNaN(new Date(when).getTime())) {
      setError('请选择执行情况，填写感受和执行时间。'); return;
    }
    try { if (!attempt.current) attempt.current = newRequestId(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : '无法安全创建提交，请更换浏览器。'); return; }
    setPending(true); setError(''); setMessage('');
    try {
      await rehabPublications.submitFeedback(plan.id, { event_id: attempt.current, version_id: plan.version_id,
        prescription_item_id: itemId, execution_status: status, feelings: feelings.trim(), performed_at: new Date(when).toISOString() });
      setMessage('反馈已提交，医护可以查看。'); setFeelings(''); setWhen(''); setStatus(''); attempt.current = null; onSaved();
    } catch (failure) {
      const code = (failure as { response?: { status?: number } })?.response?.status;
      if (code === 403 || code === 404) { onUnavailable(); return; }
      setError(code === 409 ? '方案已更新或本次提交发生冲突，请刷新方案后重新确认再提交。' :
        code === 422 ? '反馈内容或执行时间不符合要求，请检查后重试。' : '反馈提交失败，请检查网络后重试。');
    } finally { setPending(false); }
  };
  return <Stack spacing={1.5} sx={{ mt: 2 }}>
    <Typography variant="subtitle2">填写执行情况和感受</Typography>
    <TextField select label="执行情况" size="small" value={status} disabled={pending} onChange={event => { changed(); setStatus(event.target.value as PatientRehabFeedback['execution_status']); }}>
      <MenuItem value="completed">已执行</MenuItem><MenuItem value="partial">部分执行</MenuItem><MenuItem value="not_done">未执行</MenuItem>
    </TextField>
    <TextField label="执行时间" type="datetime-local" size="small" value={when} disabled={pending} onChange={event => { changed(); setWhen(event.target.value); }} InputLabelProps={{ shrink: true }} />
    <TextField label="您的感受或遇到的问题" multiline minRows={2} value={feelings} disabled={pending} inputProps={{ maxLength: 2000 }} onChange={event => { changed(); setFeelings(event.target.value); }} />
    {error && <Alert severity="error">{error}</Alert>}{message && <Alert severity="success">{message}</Alert>}
    <Box><Button variant="outlined" disabled={pending} onClick={submit}>提交反馈</Button></Box>
  </Stack>;
}

function PlanSummary({ plan, onFeedbackSaved, onUnavailable }: { plan: PublishedRehabPlan; onFeedbackSaved: () => void; onUnavailable: () => void }) {
  return <Stack spacing={2}>
    <Typography variant="h5">{plan.content.name || '康复方案'}</Typography>
    <Typography variant="body2" color="text.secondary">医护确认发布时间：{dateText(plan.published_at)}</Typography>
    <Typography>目标：{plan.content.goal || '未填写'}</Typography>
    {plan.content.description && <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>方案说明：{plan.content.description}</Typography>}
    <Typography>起止时间：{dateText(plan.content.start_date)} 至 {dateText(plan.content.end_date)}</Typography>
    {plan.content.patient_instructions && <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>注意事项：{plan.content.patient_instructions}</Typography>}
    {(Object.keys(categories) as RehabInterventionType[]).map(type => {
      const items = plan.items.filter(item => item.intervention_type === type);
      return <Box key={type}><Divider sx={{ mb: 2 }} /><Typography variant="h6" gutterBottom>{categories[type]}</Typography>
        {items.length === 0 ? <Typography color="text.secondary">医护尚未配置</Typography> :
          <Stack spacing={1.5}>{items.map(item => <Paper variant="outlined" sx={{ p: 2 }} key={item.item_id}>
            <Typography fontWeight="medium">{item.name}</Typography>
            {item.description && <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{item.description}</Typography>}
            {([['安排', item.schedule], ['饮食内容', item.diet_fields], ['用药内容', item.medication_fields], ['心理内容', item.psychology_fields], ['医护提示', item.patient_instructions], ['注意事项', item.contraindications]] as const).map(([label, value]) => displayValue(value) &&
              <Typography key={label} variant="body2" sx={{ overflowWrap: 'anywhere' }}>{label}：{displayValue(value)}</Typography>)}
            <FeedbackForm key={`${plan.version_id}:${item.item_id}`} plan={plan} itemId={item.item_id} onSaved={onFeedbackSaved} onUnavailable={onUnavailable} />
          </Paper>)}</Stack>}
      </Box>;
    })}
  </Stack>;
}

export function PatientPlanList() {
  const actor = useSelector((state: RootState) => state.auth.user);
  return <PatientPlanListForActor key={`${actor?.id}:${actor?.role}`} />;
}

function PatientPlanListForActor() {
  const navigate = useNavigate();
  const [items, setItems] = useState<PublishedRehabPlan[]>([]);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const limit = 20;
  useEffect(() => {
    const controller = new AbortController();
    setItems([]); setTotal(0); setError(''); setLoading(true);
    rehabPublications.myPlans(page * limit, limit, controller.signal).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (!data || !Array.isArray(data.items) || !data.items.every(item => validPatientPlan(item)) || !Number.isSafeInteger(data.total) || data.total < data.items.length
          || data.skip !== page * limit || data.limit !== limit || data.items.length > limit) throw new Error('方案列表格式异常');
      const lastPage = Math.max(0, Math.ceil(data.total / limit) - 1);
      if (page > lastPage) { setPage(lastPage); return; }
      setItems(data.items); setTotal(data.total);
    }).catch(() => { if (!controller.signal.aborted) setError('无法加载康复方案，请重试。'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, reload]);
  return <Container maxWidth="md"><Stack spacing={2}>
    <Typography variant="h4">我的康复方案</Typography>
    <Typography color="text.secondary">这里只展示医护确认发布的方案。方案调整后，发布的新版本会显示在这里。</Typography>
    {loading && <CircularProgress size={24} aria-label="正在加载方案" />}
    {error && <Alert severity="error" action={<Button onClick={() => setReload(value => value + 1)}>重试</Button>}>{error}</Alert>}
    {!loading && !error && items.length === 0 && <Alert severity="info">暂无医护发布的康复方案。</Alert>}
    {items.map(plan => <Card variant="outlined" key={plan.id}><CardContent><Stack spacing={1}>
      <Typography variant="h6">{plan.content.name || '康复方案'}</Typography>
      <Typography variant="body2" color="text.secondary">发布时间：{dateText(plan.published_at)}</Typography>
      <Typography>目标：{plan.content.goal || '未填写'}</Typography>
      <Box><Button onClick={() => navigate(`/app/rehab-plans/${plan.id}`)}>查看方案</Button></Box>
    </Stack></CardContent></Card>)}
    {total > limit && <Stack direction="row" spacing={2} alignItems="center"><Button disabled={loading || page === 0} onClick={() => setPage(value => value - 1)}>上一页</Button><Typography>第 {page + 1} 页，共 {total} 项</Typography><Button disabled={loading || (page + 1) * limit >= total} onClick={() => setPage(value => value + 1)}>下一页</Button></Stack>}
  </Stack></Container>;
}

export function PatientPlanDetail() {
  const actor = useSelector((state: RootState) => state.auth.user);
  const { id } = useParams<{ id: string }>();
  return <PatientPlanDetailForActor key={`${actor?.id}:${actor?.role}:${id}`} id={id} accountId={actor?.id || ''} />;
}

function PatientPlanDetailForActor({ id, accountId }: { id?: string; accountId: string }) {
  const navigate = useNavigate();
  const [plan, setPlan] = useState<PublishedRehabPlan | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [historyReload, setHistoryReload] = useState(0);
  const [history, setHistory] = useState<PatientRehabFeedback[]>([]);
  const [historyError, setHistoryError] = useState('');
  const [historyPage, setHistoryPage] = useState(0);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setPlan(null); setError(''); setLoading(true);
    if (!id || !/^[a-f\d]{24}$/i.test(id)) { setError('方案不存在。'); setLoading(false); return () => controller.abort(); }
    rehabPublications.myPlan(id, controller.signal).then(({ data }) => {
      if (!controller.signal.aborted) {
        if (!validPatientPlan(data, id)) throw new Error('方案内容格式异常');
        setPlan(data);
      }
    }).catch(error => {
      if (!controller.signal.aborted) setError(error?.response?.status === 403 ? '您无权查看该方案。' : error?.response?.status === 404 ? '该方案不存在或已撤回。' : '无法加载康复方案，请重试。');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, reload]);
  useEffect(() => {
    const controller = new AbortController();
    setHistory([]); setHistoryTotal(0); setHistoryError('');
    if (!plan) return () => controller.abort();
    setHistoryLoading(true);
    rehabPublications.feedback(plan.id, historyPage * 20, 20, controller.signal).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(data.items) || !data.items.every(record => validPatientFeedback(record, plan.id, accountId))
          || !Number.isSafeInteger(data.total) || data.total < data.items.length || data.items.length > 20) throw new Error('invalid feedback page');
      const last = Math.max(0, Math.ceil(data.total / 20) - 1);
      if (historyPage > last) { setHistoryPage(last); return; }
      setHistory(data.items); setHistoryTotal(data.total);
    }).catch(() => { if (!controller.signal.aborted) setHistoryError('暂时无法读取已提交反馈。'); })
      .finally(() => { if (!controller.signal.aborted) setHistoryLoading(false); });
    return () => controller.abort();
  }, [plan, historyReload, historyPage, accountId]);
  return <Container maxWidth="md"><Stack spacing={2}>
    <Stack direction="row" spacing={1}><Button onClick={() => navigate('/app/rehab-plans')}>返回我的方案</Button><Button disabled={loading} onClick={() => setReload(value => value + 1)}>刷新方案</Button></Stack>
    {loading && <CircularProgress size={24} aria-label="正在加载方案" />}
    {error && <Alert severity="error" action={<Button onClick={() => setReload(value => value + 1)}>重试</Button>}>{error}</Alert>}
    {plan && <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}><PlanSummary plan={plan}
      onFeedbackSaved={() => { setHistoryPage(0); setHistoryReload(value => value + 1); }}
      onUnavailable={() => { setPlan(null); setHistory([]); setError('当前无权查看该方案或方案已撤回，请刷新确认。'); }} /></Paper>}
    {plan && <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}><Stack spacing={1}><Typography variant="h6">我的反馈</Typography>
      {historyError && <Alert severity="error">{historyError}</Alert>}
      {historyLoading && <CircularProgress size={20} aria-label="正在加载反馈" />}
      {!historyLoading && !historyError && history.length === 0 && <Typography color="text.secondary">暂无反馈记录。</Typography>}
      {history.map(record => <Box key={record.id}><Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>{feedbackReference(record, plan)}</Typography><Typography variant="body2">{dateText(record.performed_at)} · {record.execution_status === 'completed' ? '已执行' : record.execution_status === 'partial' ? '部分执行' : '未执行'}</Typography><Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{record.feelings}</Typography></Box>)}
      {historyTotal > 20 && <Stack direction="row" alignItems="center" spacing={1}><Button disabled={historyLoading || historyPage === 0} onClick={() => setHistoryPage(value => value - 1)}>上一页</Button><Typography variant="body2">第 {historyPage + 1} 页，共 {historyTotal} 条</Typography><Button disabled={historyLoading || (historyPage + 1) * 20 >= historyTotal} onClick={() => setHistoryPage(value => value + 1)}>下一页</Button></Stack>}
    </Stack></Paper>}
  </Stack></Container>;
}
