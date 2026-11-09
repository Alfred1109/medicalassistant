import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Divider,
  MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { qualityApi } from '../../services/quality';
import type { QualityAssignee, QualityFact, QualityIssueDetail as Issue } from '../../types/quality';
import { evidenceReferences, issueStatusLabels, qualityError, qualityOperationId, qualitySourcePath, qualityTime } from '../../utils/quality';

type Actor = { id: string; role: string };
const validIssue = (value: Issue, id?: string) => Boolean(value && /^[a-f\d]{24}$/i.test(value.id) && (!id || value.id === id)
  && Number.isSafeInteger(value.version) && value.version >= 0 && Array.isArray(value.timeline)
  && Array.isArray(value.evidence_refs) && value.status in issueStatusLabels);

export function CreateQualityIssueDialog({ fact, onClose, onCreated }: {
  fact: QualityFact; onClose: () => void; onCreated: (id: string) => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [evidence, setEvidence] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true);
  const attempt = useRef<{signature: string; id: string} | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const submit = async () => {
    if (!fact.patient_id || !title.trim() || !description.trim()) { setError('请填写问题标题及人工核实后的具体说明。'); return; }
    let refs: string[];
    try { refs = evidenceReferences(evidence); } catch (failure) { setError((failure as Error).message); return; }
    const body = { patient_id: fact.patient_id, source_type: fact.source_type, source_id: fact.source_id,
      title: title.trim(), description: description.trim(), evidence_refs: refs };
    const signature = JSON.stringify(body);
    if (!attempt.current || attempt.current.signature !== signature) attempt.current = {signature, id: qualityOperationId()};
    setPending(true); setError('');
    try {
      const { data } = await qualityApi.create({ ...body, request_id: attempt.current.id });
      if (!alive.current) return;
      if (!validIssue(data) || data.patient_id !== fact.patient_id || data.source_id !== fact.source_id || data.source_type !== fact.source_type) throw new Error('invalid issue response');
      onCreated(data.id);
    } catch (failure) { if (alive.current) setError(qualityError(failure, '问题登记失败，请保留内容后重试。')); }
    finally { if (alive.current) setPending(false); }
  };
  return <Dialog open onClose={pending ? undefined : onClose} maxWidth="sm" fullWidth>
    <DialogTitle>人工登记过程问题</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
      <Alert severity="info">请根据已核实的来源登记问题。页面统计不会自动判定临床异常。</Alert>
      <Typography variant="body2">来源：{fact.source_type === 'followup' ? '随访记录' : '康复方案'} · {fact.source_id}</Typography>
      <TextField label="问题标题" required value={title} disabled={pending} inputProps={{ maxLength: 200 }} onChange={event => setTitle(event.target.value)} />
      <TextField label="核实情况与问题说明" required multiline minRows={3} value={description} disabled={pending} inputProps={{ maxLength: 5000 }} onChange={event => setDescription(event.target.value)} />
      <TextField label="证据引用（每行一条）" required helperText="填写 1 至 20 条可追溯的记录或材料编号，每条不超过 256 字。" multiline minRows={2} value={evidence} disabled={pending} onChange={event => setEvidence(event.target.value)} />
      {error && <Alert severity="error">{error}</Alert>}
    </Stack></DialogContent><DialogActions><Button disabled={pending} onClick={onClose}>取消</Button><Button variant="contained" disabled={pending} onClick={submit}>登记问题</Button></DialogActions>
  </Dialog>;
}

export default function QualityIssueDetailDialog({ issueId, actor, onClose, onChanged }: {
  issueId: string; actor: Actor; onClose: () => void; onChanged: () => void;
}) {
  const navigate = useNavigate();
  const [issue, setIssue] = useState<Issue | null>(null);
  const [assignees, setAssignees] = useState<QualityAssignee[]>([]);
  const [directoryError, setDirectoryError] = useState('');
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reload, setReload] = useState(0);
  const [needsReload, setNeedsReload] = useState(false);
  const [assigneeId, setAssigneeId] = useState('');
  const [note, setNote] = useState('');
  const [resolution, setResolution] = useState('');
  const [evidence, setEvidence] = useState('');
  const [decision, setDecision] = useState<'approve' | 'return'>('approve');
  const alive = useRef(true);
  const attempt = useRef<{signature: string; id: string} | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const medical = actor.role === 'doctor' || actor.role === 'health_manager';
  useEffect(() => {
    const controller = new AbortController();
    setIssue(null); setAssignees([]); setDirectoryError(''); setLoading(true); setError(''); setNeedsReload(false);
    qualityApi.issue(issueId, controller.signal).then(async ({data}) => {
      if (controller.signal.aborted) return;
      if (!validIssue(data, issueId)) throw new Error('invalid issue response');
      setIssue(data); setNote(''); setResolution(''); setEvidence(''); setAssigneeId('');
      if (medical && ['open', 'in_progress'].includes(data.status)) {
        try {
          const directory = await qualityApi.assignees(data.patient_id, controller.signal);
          if (controller.signal.aborted) return;
          if (!Array.isArray(directory.data.items) || directory.data.items.some(item => !item.id || !['doctor', 'health_manager'].includes(item.role))) throw new Error('invalid directory');
          setAssignees(directory.data.items);
        } catch (failure) {
          if (!controller.signal.aborted) {
            const status = (failure as {response?: {status?: number}})?.response?.status;
            if (status === 403 || status === 404) { setIssue(null); setNeedsReload(true); setError(qualityError(failure, '当前问题已不可访问。')); }
            else setDirectoryError(qualityError(failure, '责任人目录加载失败，请重新加载后分派。'));
          }
        }
      }
    }).catch(failure => { if (!controller.signal.aborted) setError(qualityError(failure, '问题详情加载失败，请重试。')); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [issueId, medical, reload]);
  const mutate = async (action: 'assign' | 'confirm' | 'resolve' | 'review') => {
    if (!issue || !medical || needsReload) return;
    let refs: string[] = [];
    if (action === 'resolve' || action === 'review') {
      try { refs = evidenceReferences(evidence); } catch (failure) { setError((failure as Error).message); return; }
    }
    const common = {expected_version: issue.version};
    let body: Record<string, unknown>;
    if (action === 'assign') { if (!assigneeId || !note.trim()) { setError('请选择责任人并填写分派说明。'); return; } body = {...common, assignee_id: assigneeId, note: note.trim()}; }
    else if (action === 'confirm') { if (!note.trim()) { setError('请填写确认说明。'); return; } body = {...common, note: note.trim()}; }
    else if (action === 'resolve') { if (!resolution.trim()) { setError('请填写具体整改说明。'); return; } body = {...common, resolution: resolution.trim(), evidence_refs: refs}; }
    else { if (!note.trim()) { setError('请填写复核说明。'); return; } body = {...common, decision, note: note.trim(), evidence_refs: refs}; }
    const signature = JSON.stringify([action, body]);
    if (!attempt.current || attempt.current.signature !== signature) attempt.current = {signature, id: qualityOperationId()};
    const request_id = attempt.current.id;
    setPending(true); setError(''); setMessage('');
    try {
      if (action === 'assign') await qualityApi.assign(issue.id, {...common, request_id, assignee_id: assigneeId, note: note.trim()});
      if (action === 'confirm') await qualityApi.confirm(issue.id, {...common, request_id, note: note.trim()});
      if (action === 'resolve') await qualityApi.resolve(issue.id, {...common, request_id, resolution: resolution.trim(), evidence_refs: refs});
      if (action === 'review') await qualityApi.review(issue.id, {...common, request_id, decision, note: note.trim(), evidence_refs: refs});
      if (!alive.current) return;
      setMessage('操作已保存，正在重新核对当前状态。'); setReload(value => value + 1); onChanged();
    } catch (failure) {
      if (!alive.current) return;
      const status = (failure as {response?: {status?: number}})?.response?.status;
      if (status === 409) setNeedsReload(true);
      if (status === 403 || status === 404) { setIssue(null); setNeedsReload(true); }
      setError(qualityError(failure, '操作未能确认保存，请保留原内容后重试。'));
    } finally { if (alive.current) setPending(false); }
  };
  const actionLabel: Record<string, string> = { create: '登记问题', assign: '分派责任人', confirm: '确认处理', resolve: '提交整改', review: '复核' };
  return <Dialog open onClose={pending ? undefined : onClose} maxWidth="md" fullWidth>
    <DialogTitle>过程问题处置</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
      <Box><Button disabled={loading || pending} onClick={() => setReload(value => value + 1)}>重新加载问题</Button></Box>
      {loading && <CircularProgress size={24} aria-label="正在加载问题详情" />}{error && <Alert severity="error">{error}</Alert>}{message && <Alert severity="success">{message}</Alert>}
      {issue && <>
        <Typography variant="h6" sx={{ overflowWrap: 'anywhere' }}>{issue.title}</Typography><Typography>状态：{issueStatusLabels[issue.status]}</Typography>
        <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{issue.description}</Typography>
        <Typography variant="body2">责任人：{assignees.find(person => person.id === issue.assignee_id)?.name || issue.assignee_id || '尚未分派'}</Typography>
        {issue.evidence_refs.length > 0 && <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>登记证据引用：{issue.evidence_refs.join('；')}</Typography>}
        {issue.resolution && <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="subtitle2">最近整改说明</Typography><Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{issue.resolution}</Typography></Paper>}
        <Box><Button disabled={!qualitySourcePath(issue.source_type, issue.source_id)} onClick={() => { const path = qualitySourcePath(issue.source_type, issue.source_id); if (path) navigate(path); }}>查看当前来源</Button></Box>
        {medical && !needsReload && <>
          {['open', 'in_progress'].includes(issue.status) && <>
            <Divider /><Typography variant="h6">分派责任人</Typography>
            {directoryError && <Alert severity="error">{directoryError}</Alert>}
            <TextField select label="当前获授权的责任医护" value={assigneeId} disabled={pending || !assignees.length} onChange={event => setAssigneeId(event.target.value)}>
              <MenuItem value="">请选择</MenuItem>{assignees.map(person => <MenuItem key={person.id} value={person.id}>{person.name}（{person.role === 'doctor' ? '医生' : '健康管理师'}）</MenuItem>)}
            </TextField>
            <TextField label="分派或确认说明" multiline minRows={2} value={note} disabled={pending} inputProps={{ maxLength: 2000 }} onChange={event => setNote(event.target.value)} />
            <Box><Button disabled={pending || !assigneeId || !note.trim()} onClick={() => mutate('assign')}>确认分派</Button></Box>
          </>}
          {issue.status === 'open' && issue.assignee_id === actor.id && <Box><Button variant="contained" disabled={pending || !note.trim()} onClick={() => mutate('confirm')}>责任人确认处理</Button></Box>}
          {issue.status === 'in_progress' && issue.assignee_id === actor.id && <>
            <Divider /><Typography variant="h6">提交整改</Typography>
            <TextField label="整改情况与结果" multiline minRows={3} value={resolution} disabled={pending} inputProps={{ maxLength: 5000 }} onChange={event => setResolution(event.target.value)} />
            <TextField label="整改证据引用（每行一条）" required helperText="1 至 20 条，每条不超过 256 字。" multiline minRows={2} value={evidence} disabled={pending} onChange={event => setEvidence(event.target.value)} />
            <Box><Button variant="contained" disabled={pending || !resolution.trim()} onClick={() => mutate('resolve')}>提交整改待复核</Button></Box>
          </>}
          {issue.status === 'pending_review' && <>
            <Divider /><Typography variant="h6">人工复核</Typography>
            <TextField select label="复核结论" value={decision} disabled={pending} onChange={event => setDecision(event.target.value as 'approve' | 'return')}><MenuItem value="approve">通过并关闭</MenuItem><MenuItem value="return">退回继续整改</MenuItem></TextField>
            <TextField label="复核说明" multiline minRows={2} value={note} disabled={pending} inputProps={{ maxLength: 2000 }} onChange={event => setNote(event.target.value)} />
            <TextField label="复核证据引用（每行一条）" required helperText="1 至 20 条，每条不超过 256 字。" multiline minRows={2} value={evidence} disabled={pending} onChange={event => setEvidence(event.target.value)} />
            <Box><Button variant="contained" disabled={pending || !note.trim()} onClick={() => mutate('review')}>提交复核结论</Button></Box>
          </>}
        </>}
        {!medical && <Alert severity="info">当前角色仅可查看处置记录，处理操作由获授权的医护完成。</Alert>}
        <Divider /><Typography variant="h6">处置历史</Typography>
        {issue.timeline.length === 0 && <Typography>暂无历史记录。</Typography>}
        {issue.timeline.map((entry, index) => <Paper variant="outlined" key={`${entry.version}:${index}`} sx={{ p: 2 }}>
          <Typography variant="subtitle2">{actionLabel[entry.action] || entry.action} · {qualityTime(entry.at)}</Typography>
          <Typography variant="body2">操作者：{entry.actor_id}</Typography><Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{entry.note}</Typography>
          {entry.decision && <Typography variant="body2">结论：{entry.decision === 'approve' ? '通过' : entry.decision === 'return' ? '退回' : entry.decision}</Typography>}
          {entry.evidence_refs?.length ? <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>证据：{entry.evidence_refs.join('；')}</Typography> : null}
        </Paper>)}
      </>}
    </Stack></DialogContent><DialogActions><Button disabled={pending} onClick={onClose}>关闭</Button></DialogActions>
  </Dialog>;
}
