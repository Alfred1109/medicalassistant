import React, { useEffect, useState } from 'react';
import {
  Alert, Box, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, MenuItem, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { formCatalog, formCatalogError } from '../../services/formCatalog';
import type { CatalogCenter, CatalogProject, CatalogSubject, CreatePatientLink, LocalLinkPatient, PatientLink, PatientLinksResult, PatientReference } from '../../types/formCatalog';
import { buildPatientContextReview, buildPatientLinkReview, canAddPatientContext } from '../../utils/patientLinkReview';

export function PatientLinkConfirmation({ localPatientId, localName, project, center, subject, reference }: {
  localPatientId: string; localName: string; project: CatalogProject; center: CatalogCenter; subject: CatalogSubject; reference: PatientReference;
}) {
  return <Box sx={{ display: 'grid', gap: 1 }}>
    <Typography>康复患者：{localName}（{localPatientId}）</Typography>
    <Typography>来源项目：{project.name}（#{project.project_id}）</Typography>
    <Typography>来源中心：{center.name || center.center_code}（#{center.center_id}）</Typography>
    <Typography>受试者：{subject.code || '无代码'}（#{subject.subject_id}）</Typography>
    <Typography>患者档案编号：{reference.patient_id}；机构档案编号：{reference.patient_archive_id}</Typography>
    <Alert severity="warning">请确认已在系统外核实这是同一位患者。关联不会变更现有医护分配或账号权限。</Alert>
  </Box>;
}

export default function PatientLinkPanel({ project, center, subject }: {
  project: CatalogProject | null; center: CatalogCenter | null; subject: CatalogSubject | null;
}) {
  const [reference, setReference] = useState<PatientReference | null>(null);
  const [referenceError, setReferenceError] = useState<string | null>(null);
  const [referenceLoading, setReferenceLoading] = useState(false);
  const [referenceRevision, setReferenceRevision] = useState(0);
  const [patients, setPatients] = useState<LocalLinkPatient[]>([]);
  const [patientOffset, setPatientOffset] = useState(0);
  const [patientsMore, setPatientsMore] = useState(false);
  const [patientsLoading, setPatientsLoading] = useState(false);
  const [patientsError, setPatientsError] = useState<string | null>(null);
  const [patientRevision, setPatientRevision] = useState(0);
  const [localPatientId, setLocalPatientId] = useState('');
  const [evidence, setEvidence] = useState('');
  const [verified, setVerified] = useState(false);
  const [review, setReview] = useState<CreatePatientLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [revision, setRevision] = useState(0);
  const [links, setLinks] = useState<PatientLinksResult | null>(null);
  const [linksError, setLinksError] = useState<string | null>(null);
  const [linksLoading, setLinksLoading] = useState(false);
  const [revoking, setRevoking] = useState<PatientLink | null>(null);
  const [reason, setReason] = useState('');
  const [contextLink, setContextLink] = useState<PatientLink | null>(null);
  const [contextEvidence, setContextEvidence] = useState('');
  const [contextVerified, setContextVerified] = useState(false);

  useEffect(() => {
    if (!project || !center || !subject) return;
    const controller = new AbortController(); setReferenceLoading(true); setReference(null); setReferenceError(null);
    formCatalog.patientReference(project.project_id, center.center_id, subject.subject_id, controller.signal)
      .then(({ data }) => { if (!controller.signal.aborted) setReference(data); })
      .catch(cause => { if (!controller.signal.aborted) setReferenceError(formCatalogError(cause, '来源患者档案核验失败。')); })
      .finally(() => { if (!controller.signal.aborted) setReferenceLoading(false); });
    return () => controller.abort();
  }, [project, center, subject, referenceRevision]);

  useEffect(() => {
    const controller = new AbortController(); setPatientsLoading(true); setPatientsError(null);
    formCatalog.localPatients(patientOffset, 100, controller.signal).then(({ data }) => {
      if (!Array.isArray(data) || data.some(item => typeof item.id !== 'string')) throw new Error('Invalid local patients');
      if (!controller.signal.aborted) { setPatients(previous => patientOffset ? [...previous, ...data] : data); setPatientsMore(data.length === 100); }
    }).catch(cause => { if (!controller.signal.aborted) setPatientsError(formCatalogError(cause, '康复患者列表加载失败。')); })
      .finally(() => { if (!controller.signal.aborted) setPatientsLoading(false); });
    return () => controller.abort();
  }, [patientOffset, patientRevision]);

  useEffect(() => {
    const controller = new AbortController(); setLinksLoading(true); setLinksError(null); setLinks(null);
    formCatalog.links(page * 20, 20, controller.signal).then(({ data }) => {
      if (!Array.isArray(data.items) || typeof data.total !== 'number') throw new Error('Invalid links page');
      if (!controller.signal.aborted) setLinks(data);
    }).catch(cause => { if (!controller.signal.aborted) setLinksError(formCatalogError(cause, '患者关联列表加载失败。')); })
      .finally(() => { if (!controller.signal.aborted) setLinksLoading(false); });
    return () => controller.abort();
  }, [page, revision]);

  const prepareReview = () => {
    setError(null); setNotice(null);
    try { setReview(buildPatientLinkReview({ localPatientId, project, center, subject, reference, evidenceReference: evidence, identityVerified: verified })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '请检查关联资料。'); }
  };
  const save = async () => {
    if (!review) return;
    setBusy(true); setError(null);
    try {
      await formCatalog.createLink(review); setReview(null); setEvidence(''); setVerified(false);
      setNotice('患者关联已保存。'); setPage(0); setRevision(value => value + 1);
    } catch (cause) { setError(formCatalogError(cause, '患者关联保存失败，请重新核实来源资料。')); }
    finally { setBusy(false); }
  };
  const revoke = async () => {
    if (!revoking || !reason.trim()) return;
    setBusy(true); setError(null);
    try {
      await formCatalog.revokeLink(revoking.id, reason.trim()); setRevoking(null); setReason('');
      setNotice('患者关联已撤销，历史记录保留。'); setRevision(value => value + 1);
    } catch (cause) { setError(formCatalogError(cause, '撤销失败，请刷新后重试。')); }
    finally { setBusy(false); }
  };
  const addContext = async () => {
    if (!contextLink) return;
    setBusy(true); setError(null);
    try {
      const body = buildPatientContextReview(contextLink, { localPatientId: contextLink.local_patient_id,
        project, center, subject, reference, evidenceReference: contextEvidence, identityVerified: contextVerified });
      await formCatalog.addLinkContext(contextLink.id, body); setContextLink(null);
      setNotice('已追加项目患者引用，原关联和历史记录保留。'); setRevision(value => value + 1);
    } catch (cause) { setError(formCatalogError(cause, cause instanceof Error ? cause.message : '追加项目引用失败。')); }
    finally { setBusy(false); }
  };

  return <>
    {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mb: 3 }}>
      <Typography variant="h6" gutterBottom>核实并关联现有康复患者</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>每位患者保留一个主关联。患者已有主关联时，请在下方记录中追加同一患者的新项目引用。</Typography>
      {!subject && <Typography color="text.secondary" sx={{ mb: 2 }}>请先选择来源项目、中心和受试者代码。</Typography>}
      {referenceLoading && <CircularProgress size={20} />}
      {referenceError && <Alert severity="error" action={<Button onClick={() => setReferenceRevision(value => value + 1)}>重试</Button>} sx={{ mb: 2 }}>{referenceError}</Alert>}
      {reference && <Alert severity="info" sx={{ mb: 2 }}>来源患者编号 {reference.patient_id}，机构档案编号 {reference.patient_archive_id}。请依据正式核验记录确认与下方患者的对应关系。</Alert>}
      <TextField select fullWidth label="已有康复患者" value={localPatientId} disabled={patientsLoading || busy} onChange={event => { setLocalPatientId(event.target.value); setVerified(false); setEvidence(''); }}>
        <MenuItem value="" disabled>请选择已建档患者</MenuItem>
        {patients.map(patient => <MenuItem key={patient.id} value={patient.id}>{patient.name || '未命名患者'} · {patient.id}{patient.status ? ` · ${patient.status}` : ''}</MenuItem>)}
      </TextField>
      {patientsError && <Alert severity="error" sx={{ mt: 1 }} action={<Button onClick={() => setPatientRevision(value => value + 1)}>重试</Button>}>{patientsError}</Alert>}
      {patientsMore && <Button size="small" disabled={patientsLoading} onClick={() => setPatientOffset(patients.length)}>加载更多康复患者</Button>}
      {!patientsLoading && !patientsError && patients.length === 0 && <Typography variant="body2" sx={{ mt: 1 }}>暂无已建档康复患者，需先完成患者建档。</Typography>}
      <TextField fullWidth sx={{ mt: 2 }} label="核实依据引用" value={evidence} inputProps={{ maxLength: 256 }} disabled={busy} onChange={event => setEvidence(event.target.value)} helperText="填写审批单或核验记录编号；不要粘贴证件号码、病历或影像资料。" />
      <FormControlLabel sx={{ mt: 1 }} control={<Checkbox checked={verified} disabled={busy} onChange={event => setVerified(event.target.checked)} />} label="我已核实来源档案和所选康复记录属于同一位患者" />
      <Box sx={{ mt: 1 }}><Button variant="contained" disabled={busy || !reference || referenceLoading || !localPatientId || !verified || !evidence.trim()} onClick={prepareReview}>核对关联信息</Button></Box>
    </Paper>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
      <Typography variant="h6" gutterBottom>已记录的患者关联</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>此处保留人工核实记录；实际使用前仍需重新核验来源授权和患者项目上下文。</Typography>
      {linksLoading && <CircularProgress size={22} />}
      {linksError && <Alert severity="error" action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>}>{linksError}</Alert>}
      {links && <><TableContainer sx={{ overflowX: 'auto' }}><Table size="small" sx={{ minWidth: 620 }}><TableHead><TableRow><TableCell>康复患者编号</TableCell><TableCell>来源档案</TableCell><TableCell>状态</TableCell><TableCell>操作</TableCell></TableRow></TableHead>
        <TableBody>{links.items.map(link => <TableRow key={link.id}>
          <TableCell sx={{ overflowWrap: 'anywhere' }}>{link.local_patient_id}</TableCell>
          <TableCell>来源患者 {link.reference.patient_id}{(link.references || [link.reference]).map(item => <Typography key={`${item.project_id}:${item.center_id}:${item.subject_id}`} variant="body2">项目 {item.project_id} / 中心 {item.center_id} / 受试者 {item.subject_id}</Typography>)}</TableCell>
          <TableCell><Chip size="small" label={link.status === 'verified' ? '已核实记录' : link.status === 'revoked' ? '已撤销' : link.status} color={link.status === 'verified' ? 'success' : 'default'} /></TableCell>
          <TableCell><Button size="small" disabled={busy || !canAddPatientContext(link, reference)} onClick={() => { setContextLink(link); setContextEvidence(''); setContextVerified(false); setError(null); }}>追加当前项目引用</Button><Button size="small" color="error" disabled={busy || link.status !== 'verified'} onClick={() => { setRevoking(link); setReason(''); }}>撤销</Button></TableCell>
        </TableRow>)}</TableBody></Table></TableContainer>
        {links.items.length === 0 && <Typography sx={{ py: 2 }} color="text.secondary">暂无患者关联记录。</Typography>}
        <Box sx={{ mt: 2, display: 'flex', gap: 1, alignItems: 'center' }}><Button disabled={page === 0 || linksLoading} onClick={() => setPage(value => value - 1)}>上一页</Button><Typography variant="body2">第 {page + 1} 页，共 {links.total} 条</Typography><Button disabled={(page + 1) * 20 >= links.total || linksLoading} onClick={() => setPage(value => value + 1)}>下一页</Button></Box></>}
    </Paper>
    <Dialog open={Boolean(review)} onClose={() => { if (!busy) setReview(null); }} fullWidth maxWidth="sm">
      <DialogTitle>确认患者对应关系</DialogTitle><DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {project && center && subject && reference && review && <PatientLinkConfirmation localPatientId={review.local_patient_id} localName={patients.find(patient => patient.id === review.local_patient_id)?.name || '未命名患者'} project={project} center={center} subject={subject} reference={reference} />}
        {review && <Typography variant="body2" sx={{ mt: 2, overflowWrap: 'anywhere' }}>核实依据：{review.evidence_reference}</Typography>}
      </DialogContent><DialogActions><Button disabled={busy} onClick={() => setReview(null)}>返回核对</Button><Button variant="contained" disabled={busy} onClick={() => void save()}>{busy ? '保存中…' : '确认关联'}</Button></DialogActions>
    </Dialog>
    <Dialog open={Boolean(revoking)} onClose={() => { if (!busy) setRevoking(null); }} fullWidth maxWidth="sm"><DialogTitle>撤销患者关联</DialogTitle><DialogContent>{error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}<Typography sx={{ mb: 2 }}>撤销后保留历史记录。请填写具体原因，账号及医护分配不会因此改变。</Typography><TextField autoFocus fullWidth label="撤销原因" value={reason} inputProps={{ maxLength: 256 }} onChange={event => setReason(event.target.value)} /></DialogContent><DialogActions><Button disabled={busy} onClick={() => setRevoking(null)}>取消</Button><Button color="error" disabled={busy || !reason.trim()} onClick={() => void revoke()}>确认撤销</Button></DialogActions></Dialog>
    <Dialog open={Boolean(contextLink)} onClose={() => { if (!busy) setContextLink(null); }} fullWidth maxWidth="sm"><DialogTitle>核实并追加项目引用</DialogTitle><DialogContent>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {contextLink && project && center && subject && reference && <PatientLinkConfirmation localPatientId={contextLink.local_patient_id} localName={patients.find(patient => patient.id === contextLink.local_patient_id)?.name || '已关联患者'} project={project} center={center} subject={subject} reference={reference} />}
      <TextField fullWidth sx={{ mt: 2 }} label="追加引用的核实依据" value={contextEvidence} inputProps={{ maxLength: 256 }} onChange={event => setContextEvidence(event.target.value)} helperText="仅填写核验记录编号，不粘贴个人敏感资料。" />
      <FormControlLabel control={<Checkbox checked={contextVerified} onChange={event => setContextVerified(event.target.checked)} />} label="我已核实本次项目受试者仍对应同一位患者" />
    </DialogContent><DialogActions><Button disabled={busy} onClick={() => setContextLink(null)}>取消</Button><Button variant="contained" disabled={busy || !contextVerified || !contextEvidence.trim() || !contextLink || !canAddPatientContext(contextLink, reference)} onClick={() => void addContext()}>确认追加</Button></DialogActions></Dialog>
  </>;
}
