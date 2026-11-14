import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, MenuItem, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import httpClient from '../../services/httpClient';
import type { RootState } from '../../store';

interface Portrait {
  recorded_at: string;
  patient: { id: string; name: string; source_project_id?: number | null };
  followups: Array<{ id: string; status: string; scheduled_time: string; actual_time: string; void: boolean; display_state: string }>;
  plans: Array<{ id: string; status: string; void: boolean; published: boolean; published_time: string }>;
  timeline: Array<{ kind: string; id: string; state: string }>;
  missing_followup_time: number;
  overdue_followups: number;
}
interface Material { id: string; title: string; body: string; assignment_id?: string; status?: string; feedback?: string; guidance?: string }
interface Finding { label: string; value: string; unit: string; source: string }
interface Extracted { label: string; value: string; unit: string; source: string }
interface ReportRow { id: string; filename: string; report_date: string; parse_status: string; review_status: string; review_note: string; findings: Finding[]; extracted_values?: Extracted[] }
interface VoiceRow { id: string; transcription_status: string; transcript: string | null; size: number }
interface IndicatorRow { id: string; label: string; source_label: string; unit: string; low: number | null; high: number | null; icf_code: string; state?: string; value?: string | null }
interface IndicatorResult { configured: boolean; message: string; indicators: IndicatorRow[]; coverage?: { matched: number; defined: number } | null; within_bounds?: { inside: number; compared: number } | null }
interface VoiceEvent { id: string; kind: string }
interface ShareRow { id: string; target_project_id: number; status: string; access_granted: boolean }
interface Scope { same_project: boolean | null; clinical_access: boolean; message: string; share_granted: boolean }
const displayLabel: Record<string, string> = {
  void: '作废', missing_time: '缺少时间', overdue: '计划时间已过，仍未完成', recorded: '有记录',
  followup: '随访', plan: '方案', education: '宣教', report: '报告', voice: '语音',
  assigned: '已分配', read: '已阅读', pending: '待审核', reviewed: '已审核', rejected: '已退回',
  not_transcribed: '未转写', browser_suggested: '浏览器识别，待医护确认', manual: '人工确认',
  published: '已发布', draft: '草稿', lost: '已失访',
  missing: '没有已审核结果', unbounded: '已记录，未设上下限', not_numeric: '结果不是数字',
  inside: '在录入的上下限内', outside: '超出录入的上下限',
};

const timeLabel: Record<string, string> = { present: '有时间', missing: '缺少时间', invalid: '时间无法读取' };

async function sendFile(url: string, body: FormData) {
  return httpClient.post(url, body, { transformRequest: [(data, headers) => { headers.delete('Content-Type'); return data; }] });
}

export default function ClinicalWorkbench() {
  const actor = useSelector((state: RootState) => state.auth.user);
  const [patients, setPatients] = useState<Array<{ id: string; name: string }>>([]);
  const [patientId, setPatientId] = useState('');
  const [tab, setTab] = useState('portrait');
  const [error, setError] = useState('');
  const [portrait, setPortrait] = useState<Portrait | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [feedback, setFeedback] = useState('');
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [reportDate, setReportDate] = useState('');
  const [reviewNote, setReviewNote] = useState<Record<string, string>>({});
  const [voice, setVoice] = useState<VoiceRow[]>([]);
  const [transcriptDraft, setTranscriptDraft] = useState<Record<string, string>>({});
  const [voiceEvents, setVoiceEvents] = useState<VoiceEvent[]>([]);
  const [consent, setConsent] = useState(false);
  const [finding, setFinding] = useState<Record<string, { label: string; value: string; unit: string }>>({});
  const [guidance, setGuidance] = useState<Record<string, string>>({});
  const [shares, setShares] = useState<ShareRow[]>([]);
  const [targetProject, setTargetProject] = useState('');
  const [shareReason, setShareReason] = useState('');
  const [scope, setScope] = useState<Scope | null>(null);
  const [indicators, setIndicators] = useState<IndicatorResult | null>(null);
  const [rule, setRule] = useState({ label: '', source_label: '', unit: '', low: '', high: '', icf_code: '' });
  const clinical = actor?.role === 'doctor' || actor?.role === 'health_manager' || actor?.role === 'admin';

  useEffect(() => {
    if (!actor) return;
    if (actor.role === 'patient') { setPatientId(actor.id); return; }
    if (actor.role !== 'doctor' && actor.role !== 'health_manager') return;
    const path = actor.role === 'doctor' ? '/doctors/patients' : '/health-managers/patients';
    httpClient.get(path).then(({ data }) => {
      const rows = Array.isArray(data) ? data : [];
      setPatients(rows.map((row: { id?: string; _id?: string; name?: string }) => ({ id: String(row.id || row._id), name: row.name || '未命名患者' })));
    }).catch(() => setError('患者名单没有加载出来。'));
  }, [actor]);

  const load = async (id: string) => {
    if (!id) return;
    setError('');
    try {
      const [scopeResult, portraitResult, materialResult, reportResult, voiceResult, shareResult, indicatorResult] = await Promise.all([
        httpClient.get(`/clinical/patients/${id}/scope`),
        httpClient.get(`/clinical/patients/${id}/portrait`),
        httpClient.get('/clinical/education', { params: { patient_id: id } }),
        httpClient.get(`/clinical/patients/${id}/reports`),
        httpClient.get(`/clinical/patients/${id}/voice`),
        httpClient.get(`/clinical/patients/${id}/shares`),
        httpClient.get(`/clinical/patients/${id}/indicators`),
      ]);
      setScope(scopeResult.data);
      setPortrait(portraitResult.data);
      setMaterials(materialResult.data.materials || []);
      setReports(reportResult.data.reports || []);
      setVoice(voiceResult.data.notes || []);
      setVoiceEvents(voiceResult.data.events || []);
      setShares(shareResult.data.requests || []);
      setIndicators(indicatorResult.data);
    } catch {
      setPortrait(null);
      setError('这份资料没有打开。如果患者属于另一个来源项目，需要 113.44 的共享授权。');
    }
  };

  useEffect(() => { if (patientId) load(patientId).catch(() => undefined); }, [patientId]);

  if (!actor) return null;
  const selected = patientId;

  return <Box>
    <Typography variant="h5" gutterBottom>患者记录</Typography>
    <Alert severity="info" sx={{ mb: 2 }}>带文字的报告会抽出原文里的数字，扫描页在配置了视觉模型时才摘录。抽出的数字要人工审核后才参与对照。浏览器能识别语音时会给出待确认文字，听原声保存后才算人工转写。</Alert>
    {clinical && actor.role !== 'admin' && <TextField select size="small" label="患者" value={selected} sx={{ mb: 2, minWidth: 240 }}
      onChange={event => setPatientId(event.target.value)}>
      <MenuItem value="">选择患者</MenuItem>
      {patients.map(patient => <MenuItem key={patient.id} value={patient.id}>{patient.name}</MenuItem>)}
    </TextField>}
    {actor.role === 'admin' && <TextField size="small" label="患者编号" value={patientId} sx={{ mb: 2 }}
      onChange={event => setPatientId(event.target.value)} />}
    {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}
    <Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ mb: 2 }}>
      <Tab value="portrait" label="画像" /><Tab value="education" label="宣教" />
      <Tab value="reports" label="报告" /><Tab value="voice" label="语音" />
      <Tab value="indicators" label="指标" /><Tab value="scope" label="项目范围" />
    </Tabs>
    {tab === 'portrait' && portrait && <Stack spacing={1}>
      <Typography>{portrait.patient.name}，来源项目 {portrait.patient.source_project_id ?? '未标记'}，读取时间 {portrait.recorded_at}</Typography>
      <Typography>缺少可用时间的随访：{portrait.missing_followup_time}；计划已过仍未完成：{portrait.overdue_followups}</Typography>
      {portrait.followups.map(row => <Typography key={row.id}>随访 {row.status}，{displayLabel[row.display_state] || row.display_state}，计划时间{timeLabel[row.scheduled_time]}，实际时间{timeLabel[row.actual_time]}</Typography>)}
      {portrait.plans.map(row => <Typography key={row.id}>方案 {row.status}{row.void ? '（作废，不作为当前方案）' : row.published ? '（已发布）' : '（未发布）'}</Typography>)}
      {portrait.timeline.length === 0 && <Typography>还没有随访、方案、宣教、报告或语音记录。</Typography>}
      {portrait.timeline.map(item => <Typography key={`${item.kind}-${item.id}`} color="text.secondary">{displayLabel[item.kind] || item.kind} · {displayLabel[item.state] || item.state}</Typography>)}
    </Stack>}
    {tab === 'education' && <Stack spacing={2}>
      {clinical && <>
        <TextField size="small" label="标题" value={title} onChange={event => setTitle(event.target.value)} />
        <TextField size="small" label="正文" multiline minRows={3} value={body} onChange={event => setBody(event.target.value)} />
        <Button variant="outlined" onClick={async () => {
          const created = await httpClient.post('/clinical/education', { title, body });
          if (selected) await httpClient.post('/clinical/education/assignments', { material_id: created.data.id, patient_id: selected });
          setTitle(''); setBody(''); await load(selected);
        }}>保存并分配给当前患者</Button>
      </>}
      {materials.map(item => <Box key={item.assignment_id || item.id}>
        <Typography fontWeight="medium">{item.title}</Typography>
        <Typography sx={{ whiteSpace: 'pre-wrap' }}>{item.body}</Typography>
        {item.status && <Typography color="text.secondary">进度：{item.status === 'read' ? '已阅读' : '已分配，尚未阅读'}{item.feedback ? `。患者反馈：${item.feedback}` : ''}{item.guidance ? `。医护指导：${item.guidance}` : ''}</Typography>}
        <Button size="small" onClick={() => {
          if (!window.speechSynthesis) { setError('当前浏览器不能朗读。'); return; }
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(new SpeechSynthesisUtterance(item.body));
        }}>朗读正文</Button>
        {clinical && item.assignment_id && <>
          <TextField size="small" placeholder="给患者的指导" value={guidance[item.assignment_id] || ''} onChange={event => setGuidance(current => ({ ...current, [item.assignment_id || '']: event.target.value }))} />
          <Button size="small" onClick={async () => { await httpClient.post(`/clinical/education/assignments/${item.assignment_id}/guidance`, { guidance: guidance[item.assignment_id!] || '' }); await load(selected); }}>保存指导</Button>
        </>}
      </Box>)}
      {actor.role === 'patient' && materials.filter(item => item.assignment_id && item.status !== 'read').map(item => <Box key={item.assignment_id}>
        <TextField size="small" fullWidth label="阅读反馈" value={feedback} onChange={event => setFeedback(event.target.value)} />
        <Button sx={{ mt: 1 }} onClick={async () => { await httpClient.post(`/clinical/education/assignments/${item.assignment_id}/read`, { feedback }); setFeedback(''); await load(selected); }}>标记已读</Button>
      </Box>)}
    </Stack>}
    {tab === 'reports' && <Stack spacing={2}>
      <TextField size="small" type="date" label="报告日期" value={reportDate} InputLabelProps={{ shrink: true }} onChange={event => setReportDate(event.target.value)} />
      <Button variant="outlined" component="label">上传报告
        <input hidden type="file" accept="application/pdf,image/jpeg,image/png" onChange={async event => {
          const file = event.target.files?.[0];
          if (!file || !selected) return;
          const form = new FormData();
          form.set('file', file); form.set('report_date', reportDate); form.set('stated_patient_id', selected);
          await sendFile(`/clinical/patients/${selected}/reports`, form); await load(selected);
        }} />
      </Button>
      {reports.map(row => <Box key={row.id}>
        <Typography>{row.filename}，日期 {row.report_date}，识别状态：{row.parse_status === 'model_suggested' ? '已摘录，待审核' : '未自动识别'}，审核：{row.review_status === 'pending' ? '待人工审核' : row.review_status === 'reviewed' ? '已审核' : '已退回'}</Typography>
        <Typography color="text.secondary">从原文抽出的数字还不是已确认指标。人工填写的项目标明来自原件。</Typography>
        {(row.extracted_values || []).map(item => <Typography key={`${row.id}-x-${item.label}-${item.value}`}>{item.label} {item.value} {item.unit}（{item.source}）</Typography>)}
        {(row.findings || []).map(item => <Typography key={`${row.id}-${item.label}`}>{item.label} {item.value} {item.unit}（{item.source}）</Typography>)}
        {row.review_note && <Typography color="text.secondary">{row.review_note}</Typography>}
        <Button size="small" onClick={async () => {
          const { data } = await httpClient.get(`/clinical/reports/${row.id}/content`, { responseType: 'blob' });
          window.open(URL.createObjectURL(data), '_blank');
        }}>查看原件</Button>
        {clinical && <>
          <TextField size="small" placeholder="人工审核说明" value={reviewNote[row.id] || ''} onChange={event => setReviewNote(current => ({ ...current, [row.id]: event.target.value }))} />
          <TextField size="small" placeholder="项目" value={finding[row.id]?.label || ''} onChange={event => setFinding(current => ({ ...current, [row.id]: { ...current[row.id], label: event.target.value, value: current[row.id]?.value || '', unit: current[row.id]?.unit || '' } }))} />
          <TextField size="small" placeholder="结果" value={finding[row.id]?.value || ''} onChange={event => setFinding(current => ({ ...current, [row.id]: { ...current[row.id], label: current[row.id]?.label || '', value: event.target.value, unit: current[row.id]?.unit || '' } }))} />
          <TextField size="small" placeholder="单位" value={finding[row.id]?.unit || ''} onChange={event => setFinding(current => ({ ...current, [row.id]: { ...current[row.id], label: current[row.id]?.label || '', value: current[row.id]?.value || '', unit: event.target.value } }))} />
          <Button size="small" onClick={async () => { const item = finding[row.id]; await httpClient.post(`/clinical/reports/${row.id}/findings`, item); await load(selected); }}>记入人工解读</Button>
          <Button size="small" onClick={async () => { await httpClient.post(`/clinical/reports/${row.id}/review`, { accepted: true, note: reviewNote[row.id] || '' }); await load(selected); }}>通过审核</Button>
          <Button size="small" color="warning" onClick={async () => { await httpClient.post(`/clinical/reports/${row.id}/review`, { accepted: false, note: reviewNote[row.id] || '' }); await load(selected); }}>退回</Button>
        </>}
      </Box>)}
    </Stack>}
    {tab === 'voice' && <Stack spacing={2}>
      <Alert severity="info">录音前需要同意保存这段语音。系统保存原声。浏览器识别出的文字标为待确认，听原声核对后再保存。</Alert>
      <Button size="small" variant={consent ? 'contained' : 'outlined'} onClick={() => setConsent(true)}>同意保存本次录音</Button>
      <Button variant="outlined" disabled={!consent || !selected} onClick={async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          const recorder = new MediaRecorder(stream);
          const chunks: Blob[] = [];
          let heard = '';
          const speechWindow = window as Window & { SpeechRecognition?: new () => { lang: string; continuous: boolean; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; start: () => void; stop: () => void }; webkitSpeechRecognition?: new () => { lang: string; continuous: boolean; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; start: () => void; stop: () => void } };
          const SpeechRecognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
          const recognition = SpeechRecognition ? new SpeechRecognition() : null;
          if (recognition) {
            recognition.lang = 'zh-CN';
            recognition.continuous = true;
            recognition.onresult = event => {
              heard = Array.from(event.results).map(result => result[0]?.transcript || '').join('');
            };
            try { recognition.start(); } catch { heard = ''; }
          }
          recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
          recorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());
            try { recognition?.stop(); } catch { /* 识别器可能已经结束 */ }
            const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
            const form = new FormData();
            form.set('file', new File([blob], 'voice.webm', { type: blob.type }));
            form.set('consent', 'true');
            if (heard.trim()) form.set('browser_transcript', heard.trim());
            await sendFile(`/clinical/patients/${selected}/voice`, form);
            await load(selected);
          };
          recorder.start();
          window.setTimeout(() => { if (recorder.state !== 'inactive') recorder.stop(); }, 5000);
        } catch {
          await httpClient.post(`/clinical/patients/${selected}/voice-events`, { kind: 'permission_denied' }).catch(() => undefined);
          setError('没有拿到麦克风权限。这次失败已记下，没有保存录音，也没有生成转写。');
        }
      }}>录制 5 秒语音</Button>
      {voiceEvents.map(event => <Typography key={event.id}>失败记录：麦克风权限被拒绝</Typography>)}
      {voice.map(row => <Box key={row.id}>
        <Typography>语音 {row.size} 字节，转写：{displayLabel[row.transcription_status] || row.transcription_status}</Typography>
        {row.transcript && <Typography color="text.secondary">{row.transcript}</Typography>}
        <Button size="small" onClick={async () => {
          const { data } = await httpClient.get(`/clinical/voice/${row.id}/content`, { responseType: 'blob' });
          const audio = new Audio(URL.createObjectURL(data));
          await audio.play();
        }}>播放原录音</Button>
        <TextField size="small" placeholder="听原声后填写转写" value={transcriptDraft[row.id] || ''} onChange={event => setTranscriptDraft(current => ({ ...current, [row.id]: event.target.value }))} />
        <Button size="small" onClick={async () => { await httpClient.post(`/clinical/voice/${row.id}/transcript`, { text: transcriptDraft[row.id] || '' }); await load(selected); }}>保存人工转写</Button>
      </Box>)}
    </Stack>}
    {tab === 'indicators' && <Stack spacing={2}>
      <Alert severity="info">{indicators?.message || '还没有对照结果。'}</Alert>
      {indicators?.coverage && <Typography>已有审核结果的指标 {indicators.coverage.matched} / {indicators.coverage.defined}</Typography>}
      {indicators?.within_bounds && <Typography>落在医护录入上下限内的 {indicators.within_bounds.inside} / {indicators.within_bounds.compared}</Typography>}
      {(indicators?.indicators || []).map(item => <Typography key={item.id}>{item.label}：{item.value || '无已审核结果'} {item.unit}，{displayLabel[item.state || ''] || item.state}{item.icf_code ? `，ICF 编码 ${item.icf_code}（只保存，不评分）` : ''}</Typography>)}
      {clinical && <>
        <TextField size="small" label="指标名称" value={rule.label} onChange={event => setRule(current => ({ ...current, label: event.target.value }))} />
        <TextField size="small" label="对应的已审核项目名" value={rule.source_label} onChange={event => setRule(current => ({ ...current, source_label: event.target.value }))} />
        <TextField size="small" label="单位" value={rule.unit} onChange={event => setRule(current => ({ ...current, unit: event.target.value }))} />
        <TextField size="small" label="下限（选填）" value={rule.low} onChange={event => setRule(current => ({ ...current, low: event.target.value }))} />
        <TextField size="small" label="上限（选填）" value={rule.high} onChange={event => setRule(current => ({ ...current, high: event.target.value }))} />
        <TextField size="small" label="ICF 编码（选填，不参与评分）" value={rule.icf_code} onChange={event => setRule(current => ({ ...current, icf_code: event.target.value }))} />
        <Button variant="outlined" onClick={async () => {
          await httpClient.post('/clinical/indicators', {
            label: rule.label, source_label: rule.source_label, unit: rule.unit, icf_code: rule.icf_code,
            low: rule.low === '' ? null : Number(rule.low), high: rule.high === '' ? null : Number(rule.high),
          });
          setRule({ label: '', source_label: '', unit: '', low: '', high: '', icf_code: '' });
          if (selected) await load(selected);
        }}>保存这条指标</Button>
        {(indicators?.indicators || []).map(item => <Button key={`retire-${item.id}`} size="small" onClick={async () => {
          await httpClient.post(`/clinical/indicators/${item.id}/retire`);
          if (selected) await load(selected);
        }}>停用 {item.label}</Button>)}
      </>}
      {selected && <Button size="small" onClick={async () => {
        const { data } = await httpClient.get(`/clinical/patients/${selected}/indicators.csv`, { responseType: 'blob' });
        const url = URL.createObjectURL(data);
        const anchor = document.createElement('a');
        anchor.href = url; anchor.download = 'indicators.csv'; anchor.click();
        URL.revokeObjectURL(url);
      }}>下载这次对照</Button>}
    </Stack>}
    {tab === 'scope' && scope && <Stack spacing={2}>
      <Alert severity={scope.clinical_access ? 'info' : 'warning'}>{scope.message}当前没有生效的跨项目授权。</Alert>
      {clinical && <>
        <TextField size="small" label="目标项目编号" value={targetProject} onChange={event => setTargetProject(event.target.value)} />
        <TextField size="small" label="申请原因" value={shareReason} onChange={event => setShareReason(event.target.value)} />
        <Button variant="outlined" onClick={async () => {
          await httpClient.post(`/clinical/patients/${selected}/shares`, { target_project_id: Number(targetProject), reason: shareReason });
          setShareReason(''); await load(selected);
        }}>提交共享申请</Button>
      </>}
      {shares.map(row => <Box key={row.id}>
        <Typography>目标项目 {row.target_project_id}，状态 {row.status === 'withdrawn' ? '已撤回' : '等待 113.44 授权'}，资料访问：未放开</Typography>
        {row.status !== 'withdrawn' && <Button size="small" onClick={async () => { await httpClient.post(`/clinical/shares/${row.id}/withdraw`); await load(selected); }}>撤回申请</Button>}
      </Box>)}
    </Stack>}
  </Box>;
}
