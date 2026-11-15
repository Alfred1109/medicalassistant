// ICF 工作台（T71）：ICF 结构化评估、指标自动预警、正式报告查看/审核/导出。
// 临床口径说明：类目字典、指标阈值与判定结论均为后端可配置默认值，
// 统一标注「待临床确认，可后台维护」；页面不做本地临床判定。
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, Container, Divider, FormControlLabel, MenuItem, Paper,
  Stack, Switch, Tab, Tabs, TextField, Typography,
} from '@mui/material';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import api from '../../services/httpClient';
import {
  ICF_DOMAINS, ICF_DOMAIN_LABELS, ICF_PENDING_CONFIRMATION_NOTE,
  dedupePatients, groupIcfItemsByDomain, icfError, icfMetricStateLabel,
  icfMetricValueText, icfQualifierLabel, validateIcfCategory, validateIcfItems,
} from '../../utils/icf';
import type { IcfCategory, IcfItemInput } from '../../utils/icf';
import {
  icfApi, type IcfAssessment, type IcfMetricConfig, type IcfMetricsResult,
  type IcfReport,
} from '../../services/icfService';

interface PatientOption { id: string; name: string }

export default function IcfWorkbenchPage() {
  const actor = useSelector((state: RootState) => state.auth.user);
  if (!actor || !['doctor', 'health_manager', 'admin'].includes(actor.role)) {
    return <Alert severity="error">当前账号无权访问 ICF 工作台。</Alert>;
  }
  return <IcfWorkspace key={`${actor.id}:${actor.role}`} role={actor.role} />;
}

function IcfWorkspace({ role }: { role: string }) {
  const [patients, setPatients] = useState<PatientOption[]>([]);
  const [patientError, setPatientError] = useState('');
  const [patientId, setPatientId] = useState('');
  const [tab, setTab] = useState(0);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const medical = role === 'doctor' || role === 'health_manager';
  useEffect(() => {
    const controller = new AbortController();
    if (!medical) return () => controller.abort();
    icfListPatients(role, controller.signal).then(({ data, failure }) => {
      if (controller.signal.aborted) return;
      if (failure) setPatientError(icfError(failure, '患者目录加载失败。'));
      else setPatients(dedupePatients(data ?? []).map(patient => ({ id: patient.id, name: patient.name })));
    });
    return () => controller.abort();
  }, [medical, role]);

  const run = useCallback(async (action: () => Promise<void>) => {
    setError(''); setMessage('');
    try { await action(); } catch (failure) {
      // 本地校验错误（无 response）直接展示 message；后端错误走统一文案。
      const local = (failure as Error)?.message;
      setError(icfError(failure, local || '操作失败，请稍后重试。'));
    }
  }, []);

  return (
    <Container maxWidth="xl">
      <Stack spacing={2}>
        <Typography variant="h4" component="h1">ICF 评估工作台</Typography>
        <Alert severity="info">{ICF_PENDING_CONFIRMATION_NOTE}指标阈值与判定结论亦为可配置默认口径。</Alert>
        {medical && (
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
              <TextField select label="选择患者" size="small" sx={{ minWidth: 240 }}
                value={patientId}
                onChange={event => { setPatientId(event.target.value); setError(''); setMessage(''); }}>
                <MenuItem value="">请选择患者</MenuItem>
                {patients.map(patient => (
                  <MenuItem key={patient.id} value={patient.id}>{patient.name}</MenuItem>
                ))}
              </TextField>
              {patientError && <Typography color="error" variant="body2">{patientError}</Typography>}
            </Stack>
          </Paper>
        )}
        {role === 'admin' && (
          <Alert severity="warning">
            管理员可在患者编号框中显式输入患者 ID 进行查看；评估录入、审核与预警评估由获授权医护操作。
          </Alert>
        )}
        {error && <Alert severity="error">{error}</Alert>}
        {message && <Alert severity="success">{message}</Alert>}
        <Paper variant="outlined">
          <Tabs value={tab} onChange={(_, next) => setTab(next)}>
            <Tab label="ICF 评估" />
            <Tab label="指标与预警" />
            <Tab label="正式报告" />
          </Tabs>
          <Divider />
          <Box sx={{ p: 2 }}>
            {tab === 0 && <AssessmentTab patientId={patientId} medical={medical} run={run} onMessage={setMessage} />}
            {tab === 1 && <MetricsTab patientId={patientId} run={run} onMessage={setMessage} />}
            {tab === 2 && <ReportTab patientId={patientId} medical={medical} run={run} onMessage={setMessage} />}
          </Box>
        </Paper>
      </Stack>
    </Container>
  );
}

async function icfListPatients(role: string, signal: AbortSignal):
    Promise<{ data: PatientOption[] | null; failure: unknown }> {
  try {
    const url = role === 'health_manager' ? '/health-managers/patients' : '/doctors/patients';
    const { data } = await api.get<PatientOption[]>(url, { signal });
    return { data, failure: null };
  } catch (failure) {
    return { data: null, failure };
  }
}

// ---------------- ICF 评估 ----------------

function AssessmentTab({ patientId, medical, run, onMessage }: {
  patientId: string; medical: boolean;
  run: (action: () => Promise<void>) => Promise<void>; onMessage: (text: string) => void;
}) {
  const [categories, setCategories] = useState<IcfCategory[]>([]);
  const [assessments, setAssessments] = useState<IcfAssessment[]>([]);
  const [loadedPatient, setLoadedPatient] = useState('');
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [draftSource, setDraftSource] = useState('manual');
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});

  const loadCategories = useCallback(() => run(async () => {
    const { data } = await icfApi.categories();
    setCategories(data.categories);
  }), [run]);

  const loadAssessments = useCallback(() => run(async () => {
    if (!patientId) { setAssessments([]); setLoadedPatient(''); return; }
    const { data } = await icfApi.assessments(patientId);
    setAssessments(data.assessments);
    setLoadedPatient(patientId);
  }), [run, patientId]);

  useEffect(() => { void loadCategories(); }, [loadCategories]);
  useEffect(() => { void loadAssessments(); }, [loadAssessments]);

  const enabledCategories = useMemo(
    () => categories.filter(category => category.enabled), [categories]);

  const submit = () => run(async () => {
    if (!patientId) throw new Error('请先选择患者。');
    const items: IcfItemInput[] = Object.entries(draft)
      .filter(([, value]) => value !== '')
      .map(([code, value]) => ({
        code,
        qualifier: /^\d+$/.test(value.trim()) ? Number(value.trim()) : value.trim(),
      }));
    const validated = validateIcfItems(items);
    await icfApi.createAssessment(patientId, {
      items: validated.map(item => ({ code: item.code, qualifier: item.qualifier, note: item.note })),
      source: draftSource,
    });
    onMessage('ICF 评估已保存，等待医护审核。');
    setDraft({});
    await loadAssessments();
  });

  const review = (assessment: IcfAssessment, accepted: boolean) => run(async () => {
    // 审核备注必填（与后端 REVIEW_NOTE_REQUIRED 对齐）。
    const note = (reviewNotes[assessment.id] ?? '').trim();
    if (!note) throw new Error('请填写审核意见后再提交审核。');
    await icfApi.reviewAssessment(assessment.id, {
      accepted, note, expected_version: assessment.mutation_version,
    });
    onMessage(accepted ? '评估已审核通过。' : '评估已驳回。');
    setReviewNotes(previous => ({ ...previous, [assessment.id]: '' }));
    await loadAssessments();
  });

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        限定值口径：0 无问题 / 1 轻度 / 2 中度 / 3 重度 / 4 完全；也可录入定性描述（1-20 字）。{ICF_PENDING_CONFIRMATION_NOTE}
      </Typography>
      {medical && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2">新增评估</Typography>
          <TextField select size="small" label="评估来源" value={draftSource}
            onChange={event => setDraftSource(event.target.value)} sx={{ mt: 1, minWidth: 200 }}>
            <MenuItem value="manual">手工评估</MenuItem>
            <MenuItem value="followup">随访结果</MenuItem>
            <MenuItem value="plan">康复方案</MenuItem>
          </TextField>
          {ICF_DOMAINS.map(domain => {
            const rows = enabledCategories.filter(category => category.domain === domain);
            if (rows.length === 0) return null;
            return (
              <Box key={domain} sx={{ mt: 2 }}>
                <Typography variant="subtitle2">{ICF_DOMAIN_LABELS[domain]}</Typography>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }} useFlexGap flexWrap="wrap">
                  {rows.map(category => (
                    <TextField key={category.id}
                      label={`${category.code} ${category.name}`}
                      size="small" sx={{ width: 260 }}
                      value={draft[category.code] ?? ''}
                      placeholder="0-4 或定性"
                      onChange={event => setDraft(previous => ({ ...previous, [category.code]: event.target.value }))}
                    />
                  ))}
                </Stack>
              </Box>
            );
          })}
          <Button variant="contained" sx={{ mt: 2 }} onClick={submit}>保存评估</Button>
        </Paper>
      )}
      <Typography variant="subtitle2">评估记录{loadedPatient ? '' : '（请先选择患者）'}</Typography>
      {assessments.map(assessment => (
        <Paper key={assessment.id} variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip size="small" label={
              assessment.review_status === 'reviewed' ? '已审核'
                : assessment.review_status === 'rejected' ? '已驳回' : '待审核'} />
            <Typography variant="body2">
              {assessment.source === 'followup' ? '随访结果' : assessment.source === 'plan' ? '康复方案' : '手工评估'}
              ｜评估时间 {assessment.assessed_at?.slice(0, 16).replace('T', ' ')}
              ｜版本 v{assessment.content_revision}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 1 }} useFlexGap flexWrap="wrap">
            {(assessment.items ?? []).map(item => (
              <Chip key={item.code} size="small" variant="outlined"
                label={`${item.code} ${item.name}：${icfQualifierLabel(item.qualifier)}`} />
            ))}
          </Stack>
          {medical && assessment.review_status === 'pending' && (
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }}>
              <TextField size="small" label="审核意见（必填）"
                value={reviewNotes[assessment.id] ?? ''}
                onChange={event => setReviewNotes(previous => ({ ...previous, [assessment.id]: event.target.value }))}
                sx={{ flexGrow: 1 }} />
              <Button size="small" variant="contained"
                onClick={() => review(assessment, true)}>通过</Button>
              <Button size="small" color="error"
                onClick={() => review(assessment, false)}>驳回</Button>
            </Stack>
          )}
        </Paper>
      ))}
    </Stack>
  );
}

// ---------------- 指标与预警 ----------------

function MetricsTab({ patientId, run, onMessage }: {
  patientId: string; run: (action: () => Promise<void>) => Promise<void>; onMessage: (text: string) => void;
}) {
  const [metrics, setMetrics] = useState<IcfMetricsResult | null>(null);
  const [configs, setConfigs] = useState<IcfMetricConfig[]>([]);
  const [includeDisabled, setIncludeDisabled] = useState(false);

  const loadConfigs = useCallback(() => run(async () => {
    const { data } = await icfApi.metricConfigs();
    setConfigs(data.metrics);
  }), [run]);

  useEffect(() => { void loadConfigs(); }, [loadConfigs]);

  const compute = () => run(async () => {
    if (!patientId) throw new Error('请先选择患者。');
    const { data } = await icfApi.metrics(patientId);
    setMetrics(data);
  });

  const evaluate = () => run(async () => {
    if (!patientId) throw new Error('请先选择患者。');
    const { data } = await icfApi.evaluateMetrics(patientId);
    setMetrics(data);
    const count = data.triggered?.length ?? 0;
    onMessage(count > 0 ? `已触发 ${count} 条预警（复用健康预警链路）。` : '本次无新增预警。');
  });

  const toggleConfig = (config: IcfMetricConfig, enabled: boolean) => run(async () => {
    await icfApi.updateMetricConfig(config.metric_key, { enabled });
    await loadConfigs();
  });

  return (
    <Stack spacing={2}>
      {patientId && (
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={compute}>计算指标</Button>
          <Button variant="contained" onClick={evaluate}>计算并评估预警</Button>
        </Stack>
      )}
      <Typography variant="body2" color="text.secondary">
        阈值与判定为可配置默认口径，待临床确认；预警复用既有健康预警（health_data_alerts）链路。
      </Typography>
      {metrics?.metrics.map(metric => (
        <Paper key={metric.metric_key} variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip size="small" color={metric.state === 'alert' ? 'warning' : metric.state === 'ok' ? 'success' : 'default'}
              label={icfMetricStateLabel(metric.state)} />
            <Typography variant="body1">{metric.name ?? metric.metric_key}</Typography>
            <Typography variant="body2" color="text.secondary">{icfMetricValueText(metric)}</Typography>
          </Stack>
          <Typography variant="body2" sx={{ mt: 0.5 }}>{metric.message}</Typography>
        </Paper>
      ))}
      <Divider />
      <FormControlLabel
        control={<Switch checked={includeDisabled} onChange={event => setIncludeDisabled(event.target.checked)} />}
        label="显示已停用指标" />
      {configs.filter(config => includeDisabled || config.enabled).map(config => (
        <Paper key={config.id} variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="subtitle2">{config.name}</Typography>
            <Chip size="small" label={config.enabled ? '已启用' : '已停用'}
              color={config.enabled ? 'success' : 'default'} />
          </Stack>
          <Typography variant="body2" color="text.secondary">{config.description}</Typography>
          <Typography variant="body2">阈值参数：{JSON.stringify(config.params)}</Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <Button size="small" onClick={() => toggleConfig(config, !config.enabled)}>
              {config.enabled ? '停用' : '启用'}
            </Button>
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}

// ---------------- 正式报告 ----------------

function ReportTab({ patientId, medical, run, onMessage }: {
  patientId: string; medical: boolean;
  run: (action: () => Promise<void>) => Promise<void>; onMessage: (text: string) => void;
}) {
  const [reports, setReports] = useState<IcfReport[]>([]);
  const [loadedPatient, setLoadedPatient] = useState('');
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});

  const loadReports = useCallback(() => run(async () => {
    if (!patientId) { setReports([]); setLoadedPatient(''); return; }
    const { data } = await icfApi.reports(patientId);
    setReports(data.reports);
    setLoadedPatient(patientId);
  }), [run, patientId]);

  useEffect(() => { void loadReports(); }, [loadReports]);

  const review = (report: IcfReport, accepted: boolean) => run(async () => {
    // 审核备注必填（与后端 REVIEW_NOTE_REQUIRED 对齐）。
    const note = (reviewNotes[report.id] ?? '').trim();
    if (!note) throw new Error('请填写审核意见后再提交审核。');
    await icfApi.reviewReport(report.id, {
      accepted, note, expected_version: report.mutation_version,
    });
    onMessage(accepted ? '报告已审核通过，可导出。' : '报告已驳回。');
    setReviewNotes(previous => ({ ...previous, [report.id]: '' }));
    await loadReports();
  });

  const exportJson = (report: IcfReport) => run(async () => {
    const { data } = await icfApi.exportReportJson(report.id);
    const url = URL.createObjectURL(data);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `icf-report-${report.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    onMessage('报告 JSON 已导出。');
  });

  const openHtml = (report: IcfReport) => {
    window.open(icfApi.exportReportHtmlUrl(report.id), '_blank', 'noopener');
  };

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        报告由已审核评估生成，经医护审核后可导出（结构化 JSON / 打印友好 HTML）。{ICF_PENDING_CONFIRMATION_NOTE}
      </Typography>
      {reports.length === 0 && (
        <Typography variant="body2">{loadedPatient ? '暂无正式报告。' : '请先选择患者。'}</Typography>
      )}
      {reports.map(report => (
        <Paper key={report.id} variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip size="small" label={
              report.review_status === 'reviewed' ? '已审核' : report.review_status === 'rejected' ? '已驳回' : '待审核'} />
            <Typography variant="subtitle1">{report.title}</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary">
            生成时间 {report.generated_at?.slice(0, 16).replace('T', ' ')} ｜ 版本 v{report.content_revision}
          </Typography>
          {medical && report.review_status === 'pending' && (
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }}>
              <TextField size="small" label="审核意见（必填）"
                value={reviewNotes[report.id] ?? ''}
                onChange={event => setReviewNotes(previous => ({ ...previous, [report.id]: event.target.value }))}
                sx={{ flexGrow: 1 }} />
              <Button size="small" variant="contained" onClick={() => review(report, true)}>通过</Button>
              <Button size="small" color="error" onClick={() => review(report, false)}>驳回</Button>
            </Stack>
          )}
          {report.exportable && (
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              <Button size="small" variant="outlined" onClick={() => exportJson(report)}>导出 JSON</Button>
              <Button size="small" variant="outlined" onClick={() => openHtml(report)}>打印 / HTML</Button>
            </Stack>
          )}
        </Paper>
      ))}
    </Stack>
  );
}
