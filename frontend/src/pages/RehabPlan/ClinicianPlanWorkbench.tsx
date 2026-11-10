import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Checkbox, Chip, CircularProgress, Container, Dialog,
  DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, MenuItem, Paper, Stack,
  TablePagination, TextField, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import httpClient from '../../services/httpClient';
import type { Patient } from '../../types/patient.types';
import { rehabClinicalWorkbench as api, type ClinicalPlan, type ClinicalFeedback, type DraftItem,
  type DraftState } from '../../services/rehabClinicalWorkbench';
import { contentForm, contentPayload, emptyContent, interventionLabels, operationId, validateItems,
  workbenchError, type FormContent } from '../../utils/rehabClinicalWorkbench';
import { FeedbackAttachments } from './PatientPlans';

type Actor = { id: string; role: string };
const LIMIT = 20;
const dateText = (value: string) => {
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN', { hour12: false }) : '时间未识别';
};

export function ClinicalContentFields({ value, onChange, disabled = false, includePatientInstructions = true }: {
  value: FormContent; onChange: (value: FormContent) => void; disabled?: boolean; includePatientInstructions?: boolean;
}) {
  const field = (key: keyof FormContent, label: string, multiline = false, required = false) => <TextField
    key={key} label={label} value={value[key]} disabled={disabled} required={required} fullWidth
    multiline={multiline} minRows={multiline ? 2 : undefined}
    inputProps={{ maxLength: key === 'name' ? 200 : key === 'goal' ? 2000 : key === 'frequency' ? 500 : 5000 }}
    onChange={event => onChange({ ...value, [key]: event.target.value })} />;
  return <Stack spacing={2}>
    {field('name', '方案名称', false, true)}{field('description', '方案说明', true, true)}
    {field('goal', '康复目标', true, true)}
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      <TextField fullWidth label="开始时间" type="datetime-local" required value={value.start_date} disabled={disabled}
        InputLabelProps={{ shrink: true }} inputProps={{ step: '0.001' }} onChange={event => onChange({ ...value, start_date: event.target.value })} />
      <TextField fullWidth label="结束时间（选填）" type="datetime-local" value={value.end_date} disabled={disabled}
        InputLabelProps={{ shrink: true }} inputProps={{ step: '0.001' }} onChange={event => onChange({ ...value, end_date: event.target.value })} />
    </Stack>
    {field('frequency', '总体安排（选填）')}{includePatientInstructions && field('patient_instructions', '患者注意事项（选填）', true)}
  </Stack>;
}

function safeGuidanceVideo(url?: string | null): string {
  const value = url?.trim() || '';
  return /^(https?:\/\/\S+|\/api\/rehabilitation\/exercises\/media\/[a-f\d]{32}\.(mp4|webm))$/i.test(value) ? value : '';
}

function InterventionEditor({ item, index, disabled, change, remove, library }: {
  item: DraftItem; index: number; disabled: boolean; change: (next: DraftItem) => void; remove: () => void;
  library: { id: string; name: string; video_url: string }[];
}) {
  const [videoError, setVideoError] = useState('');
  const video = safeGuidanceVideo(item.guidance_video_url);
  const lines = (value?: string[] | null) => (value || []).join('\n');
  const parseLines = (value: string) => value.split('\n').map(line => line.trim()).filter(Boolean);
  const labels: Record<string, string> = { drug_ref: '药品', dosage: '用量', frequency: '频率', route: '给药方式',
    monitoring: '监测要求', meal_structure_ref: '膳食安排', energy_target: '能量目标', nutrient_targets: '营养目标',
    food_restrictions: '食物限制', modality_ref: '干预方式', session_plan: '会话安排', instrument_refs: '量表',
    value: '数值', unit: '单位', text: '说明' };
  const detail = (value: unknown): string => value === null || value === undefined ? '' : Array.isArray(value) ?
    value.map(detail).filter(Boolean).join('；') : typeof value === 'object' ? Object.entries(value as Record<string, unknown>)
      .filter(([, itemValue]) => detail(itemValue)).map(([key, itemValue]) => `${labels[key] || key}：${detail(itemValue)}`).join('；') : String(value);
  return <Paper variant="outlined" sx={{ p: 2 }}>
    <Stack spacing={1.5}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="subtitle1">{interventionLabels[item.intervention_type]}干预 {index + 1}</Typography>
        <Button color="error" disabled={disabled} onClick={remove}>移除此项</Button>
      </Stack>
      <TextField label="干预名称" required value={item.name} disabled={disabled} inputProps={{ maxLength: 200 }}
        onChange={event => change({ ...item, name: event.target.value })} />
      <TextField label="具体内容" multiline minRows={2} value={item.description || ''} disabled={disabled}
        inputProps={{ maxLength: 5000 }} onChange={event => change({ ...item, description: event.target.value })} />
      {([['饮食详细要求', item.diet_fields], ['用药详细要求', item.medication_fields], ['心理详细要求', item.psychology_fields]] as const)
        .filter(([, value]) => detail(value)).map(([label, value]) => <Alert key={label} severity="info">
          <Typography variant="body2">{label}：{detail(value)}</Typography>
          <Typography variant="caption">以上已记录要求将随草稿保留；请核对其与具体内容是否一致。</Typography>
        </Alert>)}
      <TextField label="执行频率或安排（选填）" value={String(item.schedule?.frequency || '')} disabled={disabled}
        onChange={event => change({ ...item, schedule: { ...item.schedule, frequency: event.target.value } })} />
      <TextField label="执行时段（选填）" value={String(item.schedule?.time_of_day || '')} disabled={disabled}
        onChange={event => change({ ...item, schedule: { ...item.schedule, time_of_day: event.target.value } })} />
      {item.intervention_type === 'exercise' && <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        {(['days_per_week', 'sets', 'reps', 'duration_minutes'] as const).map((key, position) => <TextField key={key}
          label={['每周天数（选填）', '组数（选填）', '每组次数（选填）', '时长分钟（选填）'][position]} type="number"
          value={item.schedule?.[key] ?? (key === 'reps' ? item.schedule?.repetitions : undefined) ?? ''} disabled={disabled} inputProps={{ min: 0, step: 1 }}
          onChange={event => { const schedule = { ...item.schedule, [key]: event.target.value === '' ? null : Number(event.target.value) };
            if (key === 'reps') delete schedule.repetitions;
            change({ ...item, schedule }); }} />)}
      </Stack>}
      <TextField label="适用条件（选填，每行一条）" multiline minRows={2} value={lines(item.applicability_conditions)}
        disabled={disabled} onChange={event => change({ ...item, applicability_conditions: parseLines(event.target.value) })} />
      <TextField label="禁忌与注意事项（选填，每行一条）" multiline minRows={2} value={lines(item.contraindications)}
        disabled={disabled} onChange={event => change({ ...item, contraindications: parseLines(event.target.value) })} />
      <TextField label="给患者的执行说明（选填）" multiline minRows={2} value={item.patient_instructions || ''} disabled={disabled}
        inputProps={{ maxLength: 5000 }} onChange={event => change({ ...item, patient_instructions: event.target.value })} />
      <Typography variant="body2">指导动作视频（选填，只属于本项任务，发布后随这项任务给患者看）</Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <Button component="label" disabled={disabled}>上传本项视频
          <input hidden type="file" accept="video/mp4,video/webm" onChange={async event => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (!file) return;
            setVideoError('');
            const body = new FormData();
            body.append('file', file);
            try {
              const { data } = await httpClient.post<{ url?: string }>('/rehabilitation/exercises/media', body, { headers: { 'Content-Type': 'multipart/form-data' } });
              if (!safeGuidanceVideo(data.url)) { setVideoError('视频没有保存。'); return; }
              change({ ...item, guidance_video_url: data.url });
            } catch { setVideoError('视频没有上传。'); }
          }} />
        </Button>
        <TextField select size="small" label="或选用运动库里的动作视频" disabled={disabled} sx={{ minWidth: 240 }}
          value={library.some(entry => entry.video_url === video) ? video : ''}
          onChange={event => change({ ...item, guidance_video_url: event.target.value || null })}>
          <MenuItem value="">不从运动库选择</MenuItem>
          {library.map(entry => <MenuItem key={entry.id} value={entry.video_url}>{entry.name}</MenuItem>)}
        </TextField>
        {video && <Button color="error" disabled={disabled} onClick={() => change({ ...item, guidance_video_url: null })}>移除本项视频</Button>}
      </Stack>
      {videoError && <Alert severity="error">{videoError}</Alert>}
      {video && <video src={video} controls style={{ width: '100%', maxHeight: 280 }} />}
    </Stack>
  </Paper>;
}

function FeedbackList({ planId, publication }: { planId: string; publication: DraftState['published'] }) {
  const [rows, setRows] = useState<ClinicalFeedback[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setRows([]); setTotal(0); setLoading(true); setError('');
    api.feedback(planId, page * LIMIT, LIMIT, controller.signal).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(data.items) || !Number.isSafeInteger(data.total) || data.total < data.items.length ||
          data.items.some(item => item.plan_id !== planId)) throw new Error('invalid feedback response');
      const last = Math.max(0, Math.ceil(data.total / LIMIT) - 1);
      if (page > last) { setPage(last); return; }
      setRows(data.items); setTotal(data.total);
    }).catch(failure => { if (!controller.signal.aborted) setError(workbenchError(failure, '患者反馈加载失败，请重试。')); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [planId, page, reload]);
  const labels = { completed: '已执行', partial: '部分执行', not_done: '未执行' };
  return <Stack spacing={1.5}>
    <Stack direction="row" justifyContent="space-between"><Typography variant="h6">患者执行反馈</Typography>
      <Button onClick={() => setReload(value => value + 1)} disabled={loading}>刷新反馈</Button></Stack>
    <Typography color="text.secondary" variant="body2">反馈为患者自述，可能对应调整前的方案，不替代医护评估。</Typography>
    {loading && <CircularProgress size={24} aria-label="正在加载患者反馈" />}{error && <Alert severity="error">{error}</Alert>}
    {!loading && !error && rows.length === 0 && <Typography>暂无患者反馈。</Typography>}
    {rows.map(row => <Paper variant="outlined" sx={{ p: 2 }} key={row.id}>
      <Typography fontWeight="medium">{publication?.version_id === row.version_id
        ? publication.items.find(item => item.item_id === row.prescription_item_id)?.name || '当前方案干预反馈'
        : '历史方案干预反馈'}</Typography>
      <Typography>{labels[row.execution_status] || '执行情况未识别'} · {dateText(row.performed_at)}</Typography>
      <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{row.feelings}</Typography>
      <FeedbackAttachments planId={planId} items={row.attachments} />
    </Paper>)}
    {total > LIMIT && <TablePagination component="div" count={total} page={page} rowsPerPage={LIMIT} rowsPerPageOptions={[]}
      onPageChange={(_, next) => setPage(next)} labelDisplayedRows={({ from, to, count }) => `${from}-${to} 共 ${count}`} />}
  </Stack>;
}

function PlanEditor({ plan, onClose, onChanged }: { plan: ClinicalPlan; onClose: () => void; onChanged: () => void }) {
  const [snapshot, setSnapshot] = useState<DraftState | null>(null);
  const [form, setForm] = useState(emptyContent);
  const [items, setItems] = useState<DraftItem[]>([]);
  const [library, setLibrary] = useState<{ id: string; name: string; video_url: string }[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    httpClient.post('/rehabilitation/exercises/list', { skip: 0, limit: 100 }, { signal: controller.signal }).then(({ data }) => {
      if (!Array.isArray(data)) return;
      setLibrary(data.flatMap(row => {
        if (!row || typeof row !== 'object') return [];
        const entry = row as Record<string, unknown>;
        const videoUrl = typeof entry.video_url === 'string' ? entry.video_url : '';
        const name = typeof entry.name === 'string' ? entry.name : '';
        const id = typeof entry._id === 'string' ? entry._id : typeof entry.id === 'string' ? entry.id : videoUrl;
        return safeGuidanceVideo(videoUrl) && name ? [{ id, name, video_url: videoUrl }] : [];
      }));
    }).catch(() => { if (!controller.signal.aborted) setLibrary([]); });
    return () => controller.abort();
  }, []);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reload, setReload] = useState(0);
  const [needsReload, setNeedsReload] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [withdrawAction, setWithdrawAction] = useState<'withdraw' | 'cancel' | 'archive'>('withdraw');
  const alive = useRef(true);
  const attempt = useRef<{ signature: string; id: string } | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const requestId = (action: string, body: unknown) => {
    const signature = JSON.stringify([action, body]);
    if (!attempt.current || attempt.current.signature !== signature) attempt.current = { signature, id: operationId() };
    return attempt.current.id;
  };
  const apply = (data: DraftState) => {
    if (data.plan_id !== plan._id || !Number.isSafeInteger(data.publication_revision) ||
        (data.draft && (!Array.isArray(data.draft.items) || !Number.isSafeInteger(data.draft.revision)))) {
      throw new Error('方案读取结果不匹配，请重新加载。');
    }
    setSnapshot(data); setNeedsReload(false); setDirty(false); setConfirmed(false); setNote('');
    if (data.draft) { setForm(contentForm(data.draft.content)); setItems(data.draft.items); setEditing(true); }
    else if (!data.has_publication_history) { setForm(contentForm(plan)); setItems([]); setEditing(true); }
    else { setForm(emptyContent()); setItems([]); setEditing(false); }
  };
  useEffect(() => {
    const controller = new AbortController();
    setSnapshot(null); setLoading(true); setError('');
    api.draft(plan._id, controller.signal).then(({ data }) => { if (!controller.signal.aborted) apply(data); })
      .catch(failure => { if (!controller.signal.aborted) setError(workbenchError(failure, '方案读取失败，请重试。')); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  // This editor is keyed by plan and actor; plan identity cannot change in place.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan._id, reload]);
  const changed = () => { setDirty(true); setConfirmed(false); setMessage(''); setError(''); };
  const mutation = async (action: () => Promise<void>) => {
    setPending(true); setError(''); setMessage('');
    try { await action(); }
    catch (failure) {
      if (!alive.current) return;
      if ((failure as { response?: { status?: number } })?.response?.status === 409) setNeedsReload(true);
      setError(workbenchError(failure, failure instanceof Error && !(failure as { response?: unknown }).response ? failure.message : '操作结果未确认，请保留当前内容并重试同一操作，或重新加载核查。'));
    } finally { if (alive.current) setPending(false); }
  };
  const save = () => mutation(async () => {
    if (!snapshot) return;
    const body = { expected_draft_id: snapshot.draft?.id || null, expected_draft_revision: snapshot.draft?.revision ?? null,
      content: contentPayload(form), items: validateItems(items) };
    const response = await api.save(plan._id, { ...body, request_id: requestId('save', body) });
    if (!alive.current) return;
    apply(response.data); attempt.current = null; setMessage('草稿已保存，患者尚看不到这次修改。'); onChanged();
  });
  const publish = () => mutation(async () => {
    if (!snapshot?.draft || dirty || !confirmed || !note.trim()) throw new Error('请先保存草稿，核对完整内容并勾选确认，填写确认说明。');
    const body = { draft_id: snapshot.draft.id, expected_draft_revision: snapshot.draft.revision,
      expected_publication_id: snapshot.published_version_id, confirmed: true as const, confirmation_note: note.trim() };
    await api.publish(plan._id, { ...body, request_id: requestId('publish', body) });
    if (!alive.current) return;
    attempt.current = null; setMessage('发布操作已处理，正在刷新方案状态。'); setReload(value => value + 1); onChanged();
  });
  const withdraw = () => mutation(async () => {
    if (!snapshot?.published_version_id || !reason.trim()) throw new Error('请填写本次操作的原因。');
    const body = { expected_publication_id: snapshot.published_version_id, reason: reason.trim(), action: withdrawAction };
    await api.withdraw(plan._id, { ...body, request_id: requestId('withdraw', body) });
    if (!alive.current) return;
    attempt.current = null; setReason(''); setMessage('操作已处理，正在刷新方案状态。历史记录仍保留。'); setReload(value => value + 1); onChanged();
  });
  return <Dialog open fullWidth maxWidth="md" onClose={() => { if (!pending) onClose(); }}>
    <DialogTitle>方案管理 · {plan.name}</DialogTitle>
    <DialogContent dividers><Stack spacing={2.5}>
      {loading && <CircularProgress size={24} aria-label="正在读取方案" />}{error && <Alert severity="error">{error}</Alert>}
      {message && <Alert severity="success">{message}</Alert>}
      <Box><Button disabled={pending || loading} onClick={() => setReload(value => value + 1)}>重新加载方案</Button></Box>
      {snapshot && <>
        <Stack direction="row" spacing={1} flexWrap="wrap"><Chip label={snapshot.published_version_id ? '已发布 · 患者可见' : '未发布 · 患者不可见'} color={snapshot.published_version_id ? 'success' : 'default'} />
          {snapshot.draft && <Chip label={`草稿第 ${snapshot.draft.version_no} 版`} />}{dirty && <Chip label="有未保存修改" color="warning" />}</Stack>
        {!editing && <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          {snapshot.published && <Button disabled={pending} onClick={() => { setForm(contentForm(snapshot.published!.content)); setItems(snapshot.published!.items); setEditing(true); changed(); }}>以当前发布内容起草</Button>}
          <Button disabled={pending} onClick={() => { setForm(emptyContent()); setItems([]); setEditing(true); changed(); }}>建立空白草稿</Button>
        </Stack>}
        {editing && <>
          <Typography variant="h6">医护草稿</Typography>
          <ClinicalContentFields value={form} disabled={pending || needsReload} onChange={next => { setForm(next); changed(); }} />
          <Typography variant="h6">干预内容</Typography>
          <Typography variant="body2" color="text.secondary">逐项填写经核实的内容和执行说明；未配置的干预不会自动生成。</Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">{Object.entries(interventionLabels).map(([type, label]) => <Button key={type} variant="outlined" disabled={pending || needsReload || items.length >= 200}
            onClick={() => { setItems(value => [...value, { intervention_type: type as DraftItem['intervention_type'], name: '' }]); changed(); }}>添加{label}干预</Button>)}</Stack>
          {items.map((item, index) => <InterventionEditor key={item.item_id || `new-${index}`} item={item} index={index} library={library} disabled={pending || needsReload}
            change={next => { setItems(value => value.map((entry, position) => position === index ? next : entry)); changed(); }}
            remove={() => { setItems(value => value.filter((_, position) => position !== index)); changed(); }} />)}
          <Box><Button variant="contained" disabled={pending || needsReload} onClick={save}>保存医护草稿</Button></Box>
          <Divider /><Typography variant="h6">确认发布给患者</Typography>
          <FormControlLabel control={<Checkbox checked={confirmed} disabled={pending || dirty || !snapshot.draft || needsReload}
            onChange={event => setConfirmed(event.target.checked)} />} label="我已核对以上完整方案和干预内容，确认发布给患者" />
          <TextField label="确认说明" multiline minRows={2} value={note} disabled={pending || needsReload} inputProps={{ maxLength: 2000 }} onChange={event => setNote(event.target.value)} />
          <Box><Button variant="contained" disabled={pending || needsReload || dirty || !snapshot.draft || !items.length || !confirmed || !note.trim()} onClick={publish}>确认并发布方案</Button></Box>
        </>}
        {snapshot.published_version_id && <>
          <Divider /><Typography variant="h6">停止患者查看</Typography>
          <Typography variant="body2">撤回、取消或归档后，患者立即不能查看该方案，历史记录仍保留。</Typography>
          <TextField select label="处理方式" value={withdrawAction} disabled={pending || needsReload} onChange={event => setWithdrawAction(event.target.value as typeof withdrawAction)}>
            <MenuItem value="withdraw">撤回发布</MenuItem><MenuItem value="cancel">取消方案</MenuItem><MenuItem value="archive">归档方案</MenuItem>
          </TextField>
          <TextField label="处理原因" multiline minRows={2} value={reason} disabled={pending || needsReload} inputProps={{ maxLength: 2000 }} onChange={event => setReason(event.target.value)} />
          <Box><Button color="error" disabled={pending || needsReload || !reason.trim()} onClick={withdraw}>确认停止患者查看</Button></Box>
        </>}
        <Divider /><FeedbackList key={`${plan._id}:${snapshot.published_version_id}`} planId={plan._id} publication={snapshot.published} />
      </>}
    </Stack></DialogContent>
    <DialogActions><Button disabled={pending} onClick={onClose}>关闭</Button></DialogActions>
  </Dialog>;
}

function PatientWorkspace({ actor, patient }: { actor: Actor; patient: Patient }) {
  const [plans, setPlans] = useState<ClinicalPlan[]>([]);
  const [page, setPage] = useState(0);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ClinicalPlan | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyContent);
  const [pending, setPending] = useState(false);
  const [createError, setCreateError] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setPlans([]); setLoading(true); setError('');
    api.plans(patient.id, page * LIMIT, LIMIT, controller.signal).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(data) || data.some(plan => plan.patient_id !== patient.id || !plan._id)) throw new Error('invalid plan scope');
      if (!data.length && page) { setPage(value => value - 1); return; }
      setPlans(data);
    }).catch(failure => { if (!controller.signal.aborted) setError(workbenchError(failure, '方案列表加载失败，请重试。')); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [patient.id, page, reload]);
  const create = async () => {
    let body;
    try { body = contentPayload(form); } catch (failure) { setCreateError((failure as Error).message); return; }
    setPending(true); setCreateError('');
    try {
      const { data } = await api.create(patient.id, body);
      if (!alive.current) return;
      if (!data._id || data.patient_id !== patient.id) throw new Error('invalid creation response');
      setCreating(false); setSelected(data); setPage(0); setReload(value => value + 1);
    } catch (failure) {
      if (!alive.current) return;
      const status = (failure as { response?: { status?: number } })?.response?.status;
      if (!status || status >= 500) { setUncertain(true); setCreateError('保存结果未确认。请关闭窗口并刷新列表核查，避免重复创建。'); }
      else setCreateError(workbenchError(failure, '方案创建失败，请检查输入。'));
    } finally { if (alive.current) setPending(false); }
  };
  return <Stack spacing={2}>
    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1}>
      <Typography variant="h6">{patient.name}的康复方案</Typography>
      <Stack direction="row" spacing={1}><Button onClick={() => setReload(value => value + 1)} disabled={loading}>刷新列表</Button>
        <Button variant="contained" onClick={() => { setForm(emptyContent()); setUncertain(false); setCreateError(''); setCreating(true); }}>新建方案草稿</Button></Stack>
    </Stack>
    {loading && <CircularProgress size={24} aria-label="正在加载方案列表" />}{error && <Alert severity="error">{error}</Alert>}
    {!loading && !error && !plans.length && <Alert severity="info">该患者暂无康复方案，可以从草稿开始填写。</Alert>}
    {plans.map(plan => <Card variant="outlined" key={plan._id}><CardContent><Stack spacing={1}>
      <Typography variant="h6">{plan.name}</Typography><Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{plan.description}</Typography>
      <Typography variant="body2" color="text.secondary">目标：{plan.goal || '未填写'}；发布情况以管理页核验结果为准。</Typography>
      <Box><Button onClick={() => setSelected(plan)}>管理内容、发布与患者反馈</Button></Box>
    </Stack></CardContent></Card>)}
    <Stack direction="row" spacing={2} alignItems="center" justifyContent="flex-end">
      <Button disabled={loading || !page} onClick={() => setPage(value => value - 1)}>上一页</Button><Typography>第 {page + 1} 页</Typography>
      <Button disabled={loading || plans.length < LIMIT} onClick={() => setPage(value => value + 1)}>下一页</Button>
    </Stack>
    {selected && <PlanEditor key={`${actor.id}:${selected._id}`} plan={selected} onClose={() => setSelected(null)} onChanged={() => setReload(value => value + 1)} />}
    <Dialog open={creating} fullWidth maxWidth="sm" onClose={() => { if (!pending) setCreating(false); }}>
      <DialogTitle>为{patient.name}新建方案草稿</DialogTitle><DialogContent dividers>
        <Stack spacing={2}><Typography variant="body2">填写经核实的方案基本信息，保存后继续配置四类干预。草稿不会直接展示给患者。</Typography>
          <ClinicalContentFields value={form} onChange={setForm} disabled={pending || uncertain} includePatientInstructions={false} />{createError && <Alert severity="error">{createError}</Alert>}</Stack>
      </DialogContent><DialogActions><Button disabled={pending} onClick={() => setCreating(false)}>关闭</Button>
        <Button disabled={pending || uncertain} variant="contained" onClick={create}>创建草稿并继续配置</Button></DialogActions>
    </Dialog>
  </Stack>;
}

export default function ClinicianPlanWorkbench() {
  const actor = useSelector((state: RootState) => state.auth.user);
  if (!actor || !['doctor', 'health_manager'].includes(actor.role)) return <Alert severity="error">医护方案工作台需要医生或健康管理师权限。</Alert>;
  return <Workspace key={`${actor.id}:${actor.role}`} actor={actor} />;
}
function Workspace({ actor }: { actor: Actor }) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientId, setPatientId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setPatients([]); setPatientId(''); setLoading(true); setError('');
    api.patients(actor.role, controller.signal).then(({ data }) => {
      if (!controller.signal.aborted) { if (!Array.isArray(data)) throw new Error('invalid patients'); setPatients(data); }
    }).catch(failure => { if (!controller.signal.aborted) setError(workbenchError(failure, '患者列表加载失败，请重试。')); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [actor.id, actor.role, reload]);
  const patient = patients.find(item => item.id === patientId);
  return <Container maxWidth="lg" sx={{ py: 3 }}><Stack spacing={2.5}>
    <Typography variant="h4" component="h1">康复方案工作台</Typography>
    <Typography color="text.secondary">选择患者，填写并确认方案内容后发布。患者只能查看已发布内容，草稿调整不会直接改变患者看到的安排。</Typography>
    {loading && <CircularProgress size={24} aria-label="正在加载患者" />}{error && <Alert severity="error" action={<Button onClick={() => setReload(value => value + 1)}>重试</Button>}>{error}</Alert>}
    {!loading && !error && !patients.length && <Alert severity="info">当前没有分配给您的患者。</Alert>}
    <TextField select label="选择已授权患者" value={patientId} disabled={loading || !patients.length} onChange={event => setPatientId(event.target.value)} sx={{ maxWidth: 450 }}>
      <MenuItem value="">请选择患者</MenuItem>{patients.map(item => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
    </TextField>
    {patient && <PatientWorkspace key={`${actor.id}:${patient.id}`} actor={actor} patient={patient} />}
  </Stack></Container>;
}
