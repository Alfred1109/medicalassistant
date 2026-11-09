import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Stack, TextField, Typography } from '@mui/material';
import { apiService } from '../../services/api';
import { formIntegrationService, type FillTask } from '../../services/formIntegrationService';
import type { FollowUpRecord } from '../../types/followup';
import { buildFollowUpReviewRequest, canReviewFollowUp, followUpError, followUpEvidenceSource, verifiedReviewTask } from '../../utils/followupReview';
import { getFollowUpStatusInfo } from '../../constants/followup';

const valueText = (value: unknown): string => value === null || value === undefined || value === '' ? '未提供' :
  typeof value === 'object' ? JSON.stringify(value) : String(value);

export function FollowUpReviewEvidence({ record, task }: { record: FollowUpRecord; task: FillTask | null }) {
  const source = followUpEvidenceSource(record);
  const manual = source === 'manual_entry';
  const answers = record.answers ?? [];
  const questions = new Map((record.questions ?? []).map(question => [question.question_id, question.question_text]));
  return <Stack spacing={1.5}>
    <Typography>患者：{record.patient_name || record.patient_id}</Typography>
    <Typography>状态：{getFollowUpStatusInfo(record.status).label}</Typography>
    <Typography>随访说明：{valueText(record.description)}</Typography>
    <Typography>当前提交：{valueText(record.current_evidence?.submission_id)} · 版本：{valueText(record.current_evidence?.submitted_version)}</Typography>
    {record.current_evidence?.legacy && <Alert severity="info">这是服务端从历史记录核实的来源，原记录没有提交编号。</Alert>}
    {source === 'ambiguous' || source === 'unknown' ? <Alert severity="warning">当前证据来源{source === 'ambiguous' ? '存在冲突' : '尚未确定'}，请先核查，当前不能批准。</Alert> : manual ? <>
      <Alert severity="info">来源：手工录入。以下为已保存的录入内容。</Alert>
      <Typography>录入时间：{valueText(record.completion_data?.completed_at)}</Typography>
      <Typography sx={{ whiteSpace: 'pre-wrap' }}>随访结果：{valueText(record.follow_up_result ?? record.completion_data?.result)}</Typography>
      <Typography sx={{ whiteSpace: 'pre-wrap' }}>备注：{valueText(record.notes ?? record.completion_data?.notes)}</Typography>
      {answers.length === 0 && <Typography color="text.secondary">没有录入问题回答。</Typography>}
      {answers.map((answer, index) => <Box key={`${answer.question_id}-${index}`}>
        <Typography fontWeight={600}>{questions.get(answer.question_id) || `问题 ${answer.question_id}`}</Typography>
        <Typography sx={{ whiteSpace: 'pre-wrap' }}>{valueText(answer.answer_text ?? answer.answer_value)}</Typography>
      </Box>)}
    </> : <>
      <Alert severity="info">来源：外部表单。答卷引用用于追溯，只有下方成功加载的确认证据快照属于本次可见内容；当前源答卷状态仍以表单平台为准。</Alert>
      <Typography>任务：{valueText(record.effective_response?.task_id)}</Typography>
      <Typography>答卷：{valueText(record.effective_response?.response_id)}</Typography>
      <Typography>提交时间：{valueText(record.effective_response?.submitted_at)}</Typography>
      {task && verifiedReviewTask(record, task) && <>
        <Typography>核实时间：{valueText(task.confirmation?.verified_at)}</Typography>
        <Typography variant="subtitle2">已确认的回答快照（以问题编号标识）</Typography>
        {task.confirmation?.answers.map((answer, index) => <Box key={`${answer.question_id}-${index}`}>
          <Typography fontWeight={600}>问题 {answer.question_id}</Typography>
          <Typography sx={{ whiteSpace: 'pre-wrap' }}>{valueText(answer.answer_text)}</Typography>
        </Box>)}
      </>}
    </>}
    <Divider />
    <Typography variant="subtitle2">提交历史</Typography>
    {record.submission_history?.length ? record.submission_history.map((entry, index) => {
      const snapshot = entry.snapshot && typeof entry.snapshot === 'object' ? entry.snapshot as Record<string, unknown> : {};
      const ref = snapshot.effective_response && typeof snapshot.effective_response === 'object' ? snapshot.effective_response as Record<string, unknown> : {};
      return <Box key={String(entry.submission_id ?? index)} sx={{ borderLeft: 2, borderColor: 'divider', pl: 1.5 }}>
        <Typography>{entry.source === 'manual_entry' ? '手工录入' : entry.source === 'external_form' ? '外部表单' : '历史证据快照'} · {valueText(entry.submitted_at)}</Typography>
        <Typography variant="body2">提交编号：{valueText(entry.submission_id)} · 版本：{valueText(entry.submitted_version ?? entry.observed_version)}</Typography>
        {snapshot.follow_up_result != null && <Typography sx={{ whiteSpace: 'pre-wrap' }}>结果：{valueText(snapshot.follow_up_result)}</Typography>}
        {snapshot.notes != null && <Typography sx={{ whiteSpace: 'pre-wrap' }}>备注：{valueText(snapshot.notes)}</Typography>}
        {ref.response_id != null && <Typography>历史答卷引用：{valueText(ref.response_id)}</Typography>}
      </Box>;
    }) : <Typography color="text.secondary">暂无提交历史快照。</Typography>}
    <Divider />
    <Typography variant="subtitle2">审阅历史</Typography>
    {Array.isArray(record.review?.history) && record.review.history.length ? record.review.history.map((entry: Record<string, unknown>, index: number) =>
      <Box key={String(entry.review_id ?? index)}>
        <Typography>{entry.decision === 'approved' ? '通过' : entry.decision === 'returned' ? '退回' : valueText(entry.decision)} · {valueText(entry.reviewed_at)} · {valueText(entry.reviewer_id)}</Typography>
        <Typography sx={{ whiteSpace: 'pre-wrap' }}>{valueText(entry.comment)}</Typography>
      </Box>) : <Typography color="text.secondary">暂无审阅记录。</Typography>}
  </Stack>;
}

interface Props {
  followUpId: string | null;
  actor: { id: string; role: string } | null;
  onClose: () => void;
  onReviewed: () => void | Promise<void>;
}

export default function FollowUpReviewDialog({ followUpId, actor, onClose, onReviewed }: Props) {
  const [record, setRecord] = useState<FollowUpRecord | null>(null);
  const [task, setTask] = useState<FillTask | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [stale, setStale] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRecord(null); setTask(null); setError(null); setEvidenceError(null); setComment(''); setStale(false);
    if (!followUpId) return;
    setLoading(true);
    const load = async () => {
      try {
        const { data } = await apiService.getFollowUp(followUpId);
        if (cancelled) return;
        setRecord(data);
        const source = followUpEvidenceSource(data);
        if (source === 'ambiguous' || source === 'unknown') setEvidenceError('当前证据来源存在冲突或尚未确定，请核查后再批准。');
        if (source === 'external_form') {
          const taskId = data.effective_response?.task_id;
          if (typeof taskId !== 'string' || !taskId) {
            setEvidenceError('未提供可核实的答卷任务引用，当前不能批准。');
          } else {
            try {
              const loadedTask = await formIntegrationService.getFillTask(taskId);
              if (cancelled) return;
              if (!verifiedReviewTask(data, loadedTask) || !loadedTask.confirmation?.answers.length) {
                setEvidenceError('无法核实当前答卷内容，或确认快照没有可见回答。请核查源表单，当前不能批准。');
              } else setTask(loadedTask);
            } catch (taskError) {
              if (!cancelled) setEvidenceError(followUpError(taskError, '无法取得获授权的答卷内容，当前不能批准。'));
            }
          }
        }
      } catch (loadError) {
        if (!cancelled) setError(followUpError(loadError, '加载随访详情失败，请重新加载。'));
      } finally { if (!cancelled) setLoading(false); }
    };
    void load();
    return () => { cancelled = true; };
  }, [followUpId, reload]);

  const eligible = record && canReviewFollowUp(record, actor);
  const versionReady = record && Number.isInteger(record.mutation_version);
  const approvalReady = record && (followUpEvidenceSource(record) === 'manual_entry' ||
    (task && verifiedReviewTask(record, task) && !!task.confirmation?.answers.length));
  const submit = async (decision: 'approved' | 'returned') => {
    if (!record || !eligible || !versionReady || stale || submitting || loading || (decision === 'approved' && (!approvalReady || evidenceError))) return;
    if (decision === 'returned' && !comment.trim()) { setError('退回前请填写原因，便于重新录入或填报。'); return; }
    setSubmitting(true); setError(null);
    try {
      await apiService.reviewFollowUp(record.id, buildFollowUpReviewRequest(record, decision, comment));
      await onReviewed();
    } catch (submitError) {
      const status = (submitError as { response?: { status?: number } })?.response?.status;
      if (status === 409) setStale(true);
      setError(followUpError(submitError, '审阅未成功保存，请核对后重试。'));
    } finally { setSubmitting(false); }
  };

  return <Dialog open={!!followUpId} onClose={submitting ? undefined : onClose} fullWidth maxWidth="md">
    <DialogTitle>随访审阅</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2}>
        {loading && <CircularProgress aria-label="正在加载随访审阅证据" size={28} />}
        {error && <Alert severity="error">{error}</Alert>}
        {record && <FollowUpReviewEvidence record={record} task={task} />}
        {record && !eligible && <Alert severity="warning">仅待审阅随访的责任医护可以审阅；当前账号或节点状态不符合要求。</Alert>}
        {record && !versionReady && <Alert severity="error">缺少节点版本，无法安全提交审阅，请重新加载。</Alert>}
        {evidenceError && <Alert severity="warning">{evidenceError}</Alert>}
        {stale && <Alert severity="warning">记录已变化，请重新加载并重新审阅后提交。</Alert>}
        {record && <TextField label="审阅意见（退回时必填）" multiline minRows={3} value={comment} onChange={event => setComment(event.target.value)} disabled={submitting || loading || !eligible || stale} />}
        <Alert severity="info">通过后完成随访；退回后进入待填写，需要重新录入或新建填报任务。</Alert>
      </Stack>
    </DialogContent>
    <DialogActions>
      <Button onClick={() => setReload(value => value + 1)} disabled={submitting || loading}>重新加载</Button>
      <Button onClick={onClose} disabled={submitting}>关闭</Button>
      <Button color="warning" onClick={() => void submit('returned')} disabled={!eligible || !versionReady || submitting || loading || stale}>退回</Button>
      <Button variant="contained" onClick={() => void submit('approved')} disabled={!eligible || !versionReady || submitting || loading || stale || !approvalReady || !!evidenceError}>审阅通过</Button>
    </DialogActions>
  </Dialog>;
}
