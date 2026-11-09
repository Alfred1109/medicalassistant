import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Chip, CircularProgress, Grid, Paper, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TablePagination, TableRow, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { qualityApi } from '../../services/quality';
import type { QualityFact, QualityFactPage, QualityFilters, QualityOverview, QualitySource } from '../../types/quality';
import { getFollowUpStatusInfo } from '../../constants/followup';
import { publicationLabels, qualityError, qualitySourcePath, qualityTime, specialStatusLabels, validQualityFactPage, validQualityOverview } from '../../utils/quality';

const knownPlanStatus: Record<string, string> = { draft: '草稿', active: '进行中', completed: '已完成', cancelled: '已取消', canceled: '已取消', archived: '已归档' };
const statusText = (source: QualitySource, status: string) => specialStatusLabels[status] ||
  (source === 'followup' ? getFollowUpStatusInfo(status).label : knownPlanStatus[status] || status);

export default function QualityMonitoringPanel({ filters, source, patientNames, canCreate, onCreate }: {
  filters: QualityFilters; source: QualitySource; patientNames: Map<string, string>;
  canCreate: boolean; onCreate: (fact: QualityFact) => void;
}) {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<QualityOverview | null>(null);
  const [result, setResult] = useState<QualityFactPage | null>(null);
  const [page, setPage] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const queryKey = JSON.stringify([filters, source, page, limit]);
  const [responseKey, setResponseKey] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setOverview(null); setResult(null); setError(''); setLoading(true);
    void Promise.all([qualityApi.overview(filters, controller.signal), qualityApi.facts(source, filters, page * limit, limit, controller.signal)])
      .then(([summary, facts]) => {
        if (controller.signal.aborted) return;
        const data = facts.data;
        if (!validQualityOverview(summary.data) || !validQualityFactPage(data, source, filters, page * limit, limit)) {
          throw new Error('过程监测返回格式异常，请重新查询。');
        }
        const last = Math.max(0, Math.ceil(data.total / limit) - 1);
        if (page > last) { setPage(last); return; }
        setOverview(summary.data); setResult(data); setResponseKey(queryKey);
      }).catch(failure => { if (!controller.signal.aborted) setError(qualityError(failure, '过程数据加载失败，请重试。')); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  // queryKey contains the full immutable query scope.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, reload]);
  const visibleOverview = responseKey === queryKey ? overview : null;
  const visibleResult = responseKey === queryKey ? result : null;
  const exportReport = async () => {
    setExporting(true); setExportError('');
    try {
      const response = await qualityApi.report(filters);
      if (!alive.current) return;
      const contentType = String(response.headers['content-type'] || response.data.type || '');
      if (!contentType.includes('text/csv')) throw new Error('invalid report format');
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'quality-process-report.csv';
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      if (alive.current) {
        const status = (failure as {response?: {status?: number}})?.response?.status;
        if (status === 403 || status === 404) { setOverview(null); setResult(null); setResponseKey(''); }
        setExportError(qualityError(failure, '报告导出失败，请重试。'));
      }
    }
    finally { if (alive.current) setExporting(false); }
  };
  const summary = source === 'followup' ? visibleOverview?.followups : visibleOverview?.plans;
  return <Stack spacing={2}>
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} justifyContent="space-between">
      <Typography variant="h6">{source === 'followup' ? '随访过程事实' : '康复方案过程事实'}</Typography>
      <Stack direction="row" spacing={1}><Button disabled={loading} onClick={() => setReload(value => value + 1)}>刷新过程数据</Button>
        <Button disabled={exporting} onClick={exportReport}>导出过程统计报告</Button></Stack>
    </Stack>
    {exportError && <Alert severity="error">{exportError}</Alert>}
    <Typography variant="body2" color="text.secondary">随访按计划时间统计；方案按创建时间统计，发布情况表示这些方案当前的状态。页面不据此判定临床达标、疗效、逾期或失访。</Typography>
    {loading && <CircularProgress size={24} aria-label="正在加载过程监测" />}
    {error && <Alert severity="error" action={<Button onClick={() => setReload(value => value + 1)}>重试</Button>}>{error}</Alert>}
    {summary && visibleOverview && <>
      <Typography variant="body2" color="text.secondary">统计生成时间：{qualityTime(visibleOverview.generated_at)}（本地时区：{Intl.DateTimeFormat().resolvedOptions().timeZone}）</Typography>
      <Typography variant="body2" color="text.secondary">{visibleOverview.scope_kind === 'all_source_records' ? '管理员范围包含全部来源记录，也包含无法核实患者引用的记录。' : visibleOverview.scope_kind === 'selected_patient' ? '统计范围为指定患者。' : '统计范围为当前启用且分配给您的患者。'}两类来源分别实时读取，结果可能有时间差，并非同一时刻的数据库快照。</Typography>
      <Grid container spacing={1.5}>{[
        ['筛选范围内记录', summary.selected_total], ['当前完整读取范围记录', summary.scope_total],
        ['缺失时间', summary.missing_date_count], ['时间格式异常', summary.invalid_date_count], ['患者引用待核实', summary.unresolved_patient_count],
      ].map(([label, count]) => <Grid item xs={6} md={3} key={String(label)}><Paper variant="outlined" sx={{ p: 2 }}><Typography variant="body2" color="text.secondary">{label}</Typography><Typography variant="h5">{count}</Typography></Paper></Grid>)}</Grid>
      <Alert severity="info">缺失时间、时间格式异常及患者引用待核实数量覆盖当前完整读取范围，不受日期筛选限制；无有效日期的记录不能被放进具体日期窗口。</Alert>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">{summary.by_status.map(item => <Chip key={item.status} label={`${statusText(source, item.status)}：${item.count}`} />)}</Stack>
      {source === 'followup' && <Typography>待医护审阅：{visibleOverview.followups.in_review_count}</Typography>}
      {source === 'rehab_plan' && <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">{visibleOverview.plans.publication_states.map(item => <Chip key={item.state} label={`${publicationLabels[item.state] || item.state}：${item.count}`} />)}</Stack>}
      {source === 'rehab_plan' && <Typography variant="body2" color="text.secondary">发布统计核对发布引用及必要结构，不替代完整内容核验或临床审核。</Typography>}
    </>}
    {visibleResult && <>
      {visibleResult.items.length === 0 ? <Alert severity="info">当前筛选没有过程记录。此结果不代表患者没有风险。</Alert> : <TableContainer component={Paper} variant="outlined"><Table size="small" sx={{ minWidth: 720 }} aria-label="质控过程事实明细">
        <TableHead><TableRow><TableCell>患者</TableCell><TableCell>当前状态</TableCell><TableCell>{source === 'followup' ? '计划时间' : '方案创建时间'}</TableCell><TableCell>操作</TableCell></TableRow></TableHead>
        <TableBody>{visibleResult.items.map((row, index) => <TableRow key={`${row.source_type}:${row.source_reference_state}:${row.source_id}:${index}`}>
          <TableCell sx={{ maxWidth: 260, overflowWrap: 'anywhere' }}>{row.patient_id ? patientNames.get(row.patient_id) || row.patient_id : '患者引用缺失'}
            <Typography variant="caption" display="block" sx={{ overflowWrap: 'anywhere' }}>来源编号：{row.source_id}</Typography>
          </TableCell>
          <TableCell>{statusText(source, row.status)}{row.publication_state && <Typography variant="caption" display="block">{publicationLabels[row.publication_state] || row.publication_state}</Typography>}</TableCell>
          <TableCell>{row.date_quality === 'valid' ? qualityTime(row.date) : row.date_quality === 'missing' ? '缺失时间' : '时间格式异常'}</TableCell>
          <TableCell><Stack direction="row" spacing={1}>
            <Stack spacing={0.5}><Button size="small" disabled={row.source_reference_state !== 'valid' || !qualitySourcePath(row.source_type, row.source_id)} onClick={() => { const path = qualitySourcePath(row.source_type, row.source_id); if (row.source_reference_state === 'valid' && path) navigate(path); }}>查看来源</Button>
              {row.source_reference_state !== 'valid' && <Typography variant="caption" color="text.secondary">来源暂不能直接定位</Typography>}</Stack>
            {canCreate && <Stack spacing={0.5}><Button size="small" disabled={!row.issue_eligible || row.source_reference_state !== 'valid' || !row.patient_id || !/^[a-f\d]{24}$/i.test(row.source_id)} onClick={() => onCreate(row)}>登记问题</Button>
              {!row.issue_eligible && <Typography variant="caption" color="text.secondary">患者或来源暂不满足登记条件</Typography>}</Stack>}
          </Stack></TableCell>
        </TableRow>)}</TableBody></Table></TableContainer>}
      <TablePagination component="div" count={visibleResult.total} page={page} rowsPerPage={limit} rowsPerPageOptions={[20, 50, 100]}
        onPageChange={(_, next) => setPage(next)} onRowsPerPageChange={event => { setLimit(Number(event.target.value)); setPage(0); }}
        labelRowsPerPage="每页行数" labelDisplayedRows={({ from, to, count }) => `${from}-${to} 共 ${count}`} />
    </>}
  </Stack>;
}
