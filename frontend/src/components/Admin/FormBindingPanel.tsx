import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, MenuItem, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { formCatalog, formCatalogError } from '../../services/formCatalog';
import { useFormCatalog } from '../../hooks/useFormCatalog';
import type { CatalogForm, CatalogProject, CreateFormBinding, FormBinding, FormBindingsResult, FormPurpose } from '../../types/formCatalog';
import { buildFormBindingReview, FORM_PURPOSE_LABELS } from '../../utils/patientLinkReview';
import CatalogPageState from './CatalogPageState';

export function FormBindingConfirmation({ project, form, purpose }: { project: CatalogProject; form: CatalogForm; purpose: FormPurpose }) {
  return <Box sx={{ display: 'grid', gap: 1 }}>
    <Typography>项目：{project.name}（#{project.project_id}）</Typography>
    <Typography>问卷：{form.title}（#{form.form_id}）</Typography>
    <Typography>正式版本：{form.current_version?.version}</Typography>
    <Typography>用途：{FORM_PURPOSE_LABELS[purpose]}</Typography>
    <Alert severity="info">记录该项目使用的问卷版本和用途。实际使用时仍需核验中心、患者及操作者授权。</Alert>
  </Box>;
}

export default function FormBindingPanel({ project }: { project: CatalogProject | null }) {
  const loader = useCallback((cursor: string | undefined, signal: AbortSignal) => formCatalog.forms(project?.project_id || 0, { cursor }, signal), [project?.project_id]);
  const forms = useFormCatalog<CatalogForm>(`forms:${project?.project_id || 0}`, project ? loader : null);
  const [formId, setFormId] = useState(0);
  const [verifiedForm, setVerifiedForm] = useState<CatalogForm | null>(null);
  const [versionLoading, setVersionLoading] = useState(false);
  const [versionError, setVersionError] = useState<string | null>(null);
  const [versionRevision, setVersionRevision] = useState(0);
  const [purpose, setPurpose] = useState<FormPurpose | ''>('');
  const [evidence, setEvidence] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [review, setReview] = useState<CreateFormBinding | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [revision, setRevision] = useState(0);
  const [bindings, setBindings] = useState<FormBindingsResult | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [revoking, setRevoking] = useState<FormBinding | null>(null);
  const [reason, setReason] = useState('');

  useEffect(() => {
    setVerifiedForm(null); setVersionError(null); setConfirmed(false);
    if (!project || !formId) return;
    const controller = new AbortController(); setVersionLoading(true);
    formCatalog.formVersion(project.project_id, formId, controller.signal).then(({ data }) => {
      if (data.form.project_id !== project.project_id || data.form.form_id !== formId || data.version.form_id !== formId) throw new Error('Changed form version');
      if (!controller.signal.aborted) setVerifiedForm({ ...data.form, current_version: data.version });
    }).catch(cause => { if (!controller.signal.aborted) setVersionError(formCatalogError(cause, '问卷正式版本核验失败，请重新选择。')); })
      .finally(() => { if (!controller.signal.aborted) setVersionLoading(false); });
    return () => controller.abort();
  }, [project, formId, versionRevision]);

  useEffect(() => {
    const controller = new AbortController(); setListLoading(true); setListError(null); setBindings(null);
    formCatalog.formBindings(page * 20, 20, controller.signal).then(({ data }) => {
      if (!Array.isArray(data.items) || typeof data.total !== 'number') throw new Error('Invalid bindings page');
      if (!controller.signal.aborted) setBindings(data);
    }).catch(cause => { if (!controller.signal.aborted) setListError(formCatalogError(cause, '问卷用途列表加载失败。')); })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [page, revision]);

  const prepareReview = () => {
    setError(null); setNotice(null);
    try { setReview(buildFormBindingReview({ project, form: verifiedForm, purpose, evidenceReference: evidence, confirmed })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '请检查问卷用途信息。'); }
  };
  const save = async () => {
    if (!review) return;
    setBusy(true); setError(null);
    try {
      await formCatalog.createFormBinding(review); setReview(null); setEvidence(''); setConfirmed(false);
      setNotice('问卷用途已保存。'); setPage(0); setRevision(value => value + 1);
    } catch (cause) { setError(formCatalogError(cause, '问卷用途保存失败，请重新核实版本。')); }
    finally { setBusy(false); }
  };
  const revoke = async () => {
    if (!revoking || !reason.trim()) return;
    setBusy(true); setError(null);
    try {
      await formCatalog.revokeFormBinding(revoking.id, reason.trim()); setRevoking(null); setReason('');
      setNotice('问卷用途已撤销，历史记录保留。'); setRevision(value => value + 1);
    } catch (cause) { setError(formCatalogError(cause, '撤销失败，请刷新后重试。')); }
    finally { setBusy(false); }
  };

  return <>
    {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mb: 3 }}>
      <Typography variant="h6" gutterBottom>选择正式问卷及用途</Typography>
      {!project && <Typography color="text.secondary" sx={{ mb: 2 }}>请先选择来源项目。</Typography>}
      <TextField select fullWidth label="项目问卷" value={formId || ''} disabled={!project || forms.loading || busy} onChange={event => { setFormId(Number(event.target.value)); setPurpose(''); setEvidence(''); setConfirmed(false); }}>
        <MenuItem value="" disabled>请选择问卷</MenuItem>
        {forms.items.map(form => <MenuItem key={form.form_id} value={form.form_id}>{form.title} · 问卷 #{form.form_id}{form.current_version ? ` · 版本 ${form.current_version.version}` : ' · 暂无正式版本'}</MenuItem>)}
      </TextField><CatalogPageState {...forms} />
      {project && !forms.loading && !forms.error && forms.items.length === 0 && <Typography variant="body2" sx={{ mt: 1 }}>该项目没有获授权的有效问卷。</Typography>}
      {versionLoading && <CircularProgress size={20} sx={{ mt: 2 }} />}
      {versionError && <Alert severity="error" sx={{ mt: 2 }} action={<Button onClick={() => setVersionRevision(value => value + 1)}>重试</Button>}>{versionError}</Alert>}
      {verifiedForm && <Alert severity="info" sx={{ mt: 2 }}>已核实问卷 #{verifiedForm.form_id} 的版本 {verifiedForm.current_version?.version}。</Alert>}
      <TextField select fullWidth sx={{ mt: 2 }} label="业务用途" value={purpose} disabled={busy} onChange={event => { setPurpose(event.target.value as FormPurpose); setConfirmed(false); }}>
        <MenuItem value="" disabled>请明确选择用途</MenuItem>
        {(Object.keys(FORM_PURPOSE_LABELS) as FormPurpose[]).map(value => <MenuItem key={value} value={value}>{FORM_PURPOSE_LABELS[value]}</MenuItem>)}
      </TextField>
      <TextField fullWidth sx={{ mt: 2 }} label="用途核实依据引用" value={evidence} inputProps={{ maxLength: 256 }} disabled={busy} onChange={event => setEvidence(event.target.value)} helperText="填写正式表单选择依据或审批记录编号，不粘贴患者资料。" />
      <FormControlLabel sx={{ mt: 1 }} control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} label="我已核实该问卷版本适用于所选用途" />
      <Box sx={{ mt: 1 }}><Button variant="contained" disabled={busy || !verifiedForm || versionLoading || !purpose || !confirmed || !evidence.trim()} onClick={prepareReview}>核对问卷用途</Button></Box>
    </Paper>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
      <Typography variant="h6" gutterBottom>已记录的问卷用途</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>此处保留已核实的用途记录；实际使用前仍需重新核验来源授权和问卷当前版本。</Typography>
      {listLoading && <CircularProgress size={22} />}
      {listError && <Alert severity="error" action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>}>{listError}</Alert>}
      {bindings && <><TableContainer sx={{ overflowX: 'auto' }}><Table size="small" sx={{ minWidth: 620 }}><TableHead><TableRow><TableCell>项目 / 问卷</TableCell><TableCell>版本 / 用途</TableCell><TableCell>状态</TableCell><TableCell>操作</TableCell></TableRow></TableHead><TableBody>{bindings.items.map(binding => <TableRow key={binding.id}>
        <TableCell>{binding.title}<br /><Typography variant="caption">项目 {binding.project_id} / 问卷 {binding.form_id}</Typography></TableCell>
        <TableCell>版本 {binding.version}<br />{FORM_PURPOSE_LABELS[binding.purpose] || binding.purpose}</TableCell>
        <TableCell><Chip size="small" label={binding.status === 'active' ? '已记录' : binding.status === 'revoked' ? '已撤销' : binding.status} color={binding.status === 'active' ? 'success' : 'default'} /></TableCell>
        <TableCell><Button size="small" color="error" disabled={busy || binding.status !== 'active'} onClick={() => { setRevoking(binding); setReason(''); }}>撤销</Button></TableCell>
      </TableRow>)}</TableBody></Table></TableContainer>
      {bindings.items.length === 0 && <Typography sx={{ py: 2 }} color="text.secondary">暂无问卷用途记录。</Typography>}
      <Box sx={{ mt: 2, display: 'flex', gap: 1, alignItems: 'center' }}><Button disabled={page === 0 || listLoading} onClick={() => setPage(value => value - 1)}>上一页</Button><Typography variant="body2">第 {page + 1} 页，共 {bindings.total} 条</Typography><Button disabled={(page + 1) * 20 >= bindings.total || listLoading} onClick={() => setPage(value => value + 1)}>下一页</Button></Box></>}
    </Paper>
    <Dialog open={Boolean(review)} onClose={() => { if (!busy) setReview(null); }} fullWidth maxWidth="sm"><DialogTitle>确认问卷用途</DialogTitle><DialogContent>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {review && project && verifiedForm && <FormBindingConfirmation project={project} form={verifiedForm} purpose={review.purpose} />}
      {review && <Typography variant="body2" sx={{ mt: 2, overflowWrap: 'anywhere' }}>核实依据：{review.evidence_reference}</Typography>}
    </DialogContent><DialogActions><Button disabled={busy} onClick={() => setReview(null)}>返回核对</Button><Button variant="contained" disabled={busy} onClick={() => void save()}>{busy ? '保存中…' : '确认用途'}</Button></DialogActions></Dialog>
    <Dialog open={Boolean(revoking)} onClose={() => { if (!busy) setRevoking(null); }} fullWidth maxWidth="sm"><DialogTitle>撤销问卷用途</DialogTitle><DialogContent>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Typography sx={{ mb: 2 }}>撤销后保留历史记录。请填写原因。</Typography><TextField autoFocus fullWidth label="撤销原因" value={reason} inputProps={{ maxLength: 256 }} onChange={event => setReason(event.target.value)} />
    </DialogContent><DialogActions><Button disabled={busy} onClick={() => setRevoking(null)}>取消</Button><Button color="error" disabled={busy || !reason.trim()} onClick={() => void revoke()}>确认撤销</Button></DialogActions></Dialog>
  </>;
}
