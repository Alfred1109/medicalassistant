import React, { useEffect, useState } from 'react';
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, MenuItem, TextField, Typography,
} from '@mui/material';
import { FillCandidatePatient, FillCandidatesPage, formIntegrationService } from '../../services/formIntegrationService';
import type { FollowUpWorkbenchPage } from '../../types/followup';

const PURPOSE: Record<string, string> = {
  initial_assessment: '初评', followup: '随访', reassessment: '复评',
};
const PAGE_SIZE = 50;

type Props = { open: boolean; onClose: () => void; onCreated: (id: string) => void };

export default function FillTaskCreateDialog({ open, onClose, onCreated }: Props) {
  const [page, setPage] = useState<FillCandidatesPage | null>(null);
  const [skip, setSkip] = useState(0);
  const [patientId, setPatientId] = useState('');
  const [referenceIndex, setReferenceIndex] = useState('');
  const [formId, setFormId] = useState('');
  const [followups, setFollowups] = useState<FollowUpWorkbenchPage | null>(null);
  const [followupSkip, setFollowupSkip] = useState(0);
  const [followupId, setFollowupId] = useState('');
  const [followupError, setFollowupError] = useState('');
  const [followupLoading, setFollowupLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    let current = true;
    setLoading(true); setError(''); setPatientId(''); setReferenceIndex(''); setFormId('');
    formIntegrationService.listFillCandidates(skip, PAGE_SIZE).then(result => {
      if (current) setPage(result);
    }).catch(() => {
      if (current) { setPage(null); setError('无法加载可填报的患者和问卷，请重试。'); }
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [open, skip]);

  useEffect(() => {
    setFollowupId(''); setFollowups(null); setFollowupError('');
    if (!open || !patientId) return;
    let current = true;
    setFollowupLoading(true);
    formIntegrationService.listPatientFollowups(patientId, followupSkip, PAGE_SIZE).then(result => {
      if (current) setFollowups(result);
    }).catch(() => {
      if (current) setFollowupError('随访记录加载失败，请重试或先不关联随访。');
    }).finally(() => { if (current) setFollowupLoading(false); });
    return () => { current = false; };
  }, [open, patientId, followupSkip]);

  const patient: FillCandidatePatient | undefined = page?.patients.find(item => item.patient_id === patientId);
  const reference = referenceIndex === '' ? undefined : patient?.references[Number(referenceIndex)];
  const form = reference?.forms.find(item => item.binding_id === formId);
  const followup = followups?.items.find(item => item.id === followupId);
  const close = () => { if (!saving) { setSkip(0); onClose(); } };

  const create = async () => {
    if (!patient || !reference || !form || saving) return;
    setSaving(true); setError('');
    try {
      const task = await formIntegrationService.createFillTask({
        patientId: patient.patient_id, remoteProjectId: reference.project_id,
        remoteCenterId: reference.center_id, remoteSubjectId: reference.subject_id,
        remoteQuestionnaireId: form.form_id, formBindingId: form.binding_id,
        formPurpose: form.purpose, allowedOrigin: window.location.origin,
        ...(followup ? { followupVisitId: followup.id, ...(followup.visit_code ? { visitCode: followup.visit_code } : {}) } : {}),
      });
      setSkip(0); onCreated(task.id);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : '创建填报任务失败，请检查关联和权限。');
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
      <DialogTitle>新建问卷填报任务</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          请选择已核实来源的患者和问卷。创建时系统会再次核验当前权限和问卷版本。
        </Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {loading ? <Box display="flex" justifyContent="center"><CircularProgress size={28} /></Box> : (
          <>
            {page && page.total === 0 && <Alert severity="info">暂无可填报的患者和问卷，请联系管理员核实关联与授权。</Alert>}
            <TextField select fullWidth margin="normal" label="患者" value={patientId} disabled={saving || !page?.patients.length}
              onChange={event => { setPatientId(event.target.value); setReferenceIndex(''); setFormId(''); setFollowupSkip(0); }}>
              {(page?.patients ?? []).map(item => <MenuItem key={item.patient_id} value={item.patient_id}>{item.name || item.patient_id}</MenuItem>)}
            </TextField>
            {page && page.total > PAGE_SIZE && <Box display="flex" alignItems="center" gap={1}>
              <Button size="small" disabled={saving || skip === 0} onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}>上一页</Button>
              <Typography variant="caption">第 {Math.floor(skip / PAGE_SIZE) + 1} 页，共 {page.total} 位患者</Typography>
              <Button size="small" disabled={saving || skip + PAGE_SIZE >= page.total} onClick={() => setSkip(skip + PAGE_SIZE)}>下一页</Button>
            </Box>}
            <TextField select fullWidth margin="normal" label="患者来源" value={referenceIndex} disabled={saving || !patient}
              onChange={event => { setReferenceIndex(event.target.value); setFormId(''); }}>
              {(patient?.references ?? []).map((item, index) => <MenuItem key={`${item.project_id}-${item.center_id}-${item.subject_id}`} value={String(index)}>
                项目 {item.project_id} · 中心 {item.center_id} · 受试者 {item.subject_id}
              </MenuItem>)}
            </TextField>
            <TextField select fullWidth margin="normal" label="问卷及用途" value={formId} disabled={saving || !reference}
              onChange={event => setFormId(event.target.value)}>
              {(reference?.forms ?? []).map(item => <MenuItem key={item.binding_id} value={item.binding_id}>
                {item.title} · {PURPOSE[item.purpose] ?? item.purpose} · 版本 {item.version}
              </MenuItem>)}
            </TextField>
            {reference && reference.forms.length === 0 && <Alert severity="info">该来源尚无已审核的问卷用途。</Alert>}
            {patient && <>
              {followupError && <Alert severity="warning">{followupError}</Alert>}
              <TextField select fullWidth margin="normal" label="关联随访（可选）" value={followupId}
                disabled={saving || followupLoading || !followups} onChange={event => setFollowupId(event.target.value)}>
                <MenuItem value="">不关联随访</MenuItem>
                {(followups?.items ?? []).filter(item => !['completed', 'canceled', 'cancelled'].includes(item.status)).map(item =>
                  <MenuItem key={item.id} value={item.id}>{item.description || '随访'} · {item.scheduled_date}</MenuItem>)}
              </TextField>
              {followups && followups.total > PAGE_SIZE && <Box display="flex" alignItems="center" gap={1}>
                <Button size="small" disabled={saving || followupSkip === 0} onClick={() => setFollowupSkip(Math.max(0, followupSkip - PAGE_SIZE))}>上一页</Button>
                <Typography variant="caption">随访第 {Math.floor(followupSkip / PAGE_SIZE) + 1} 页，共 {followups.total} 条</Typography>
                <Button size="small" disabled={saving || followupSkip + PAGE_SIZE >= followups.total} onClick={() => setFollowupSkip(followupSkip + PAGE_SIZE)}>下一页</Button>
              </Box>}
            </>}
          </>
        )}
      </DialogContent>
      <DialogActions><Button onClick={close} disabled={saving}>取消</Button>
        <Button variant="contained" onClick={() => void create()} disabled={!form || loading || saving}>{saving ? '创建中…' : '创建并打开'}</Button>
      </DialogActions>
    </Dialog>
  );
}
