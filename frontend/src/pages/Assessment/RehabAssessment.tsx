import React, { useState, useCallback } from 'react';
import { useSelector } from 'react-redux';
import { useSearchParams } from 'react-router-dom';
import {
  Box,
  Typography,
  Container,
  Paper,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  Button,
  Alert,
  CircularProgress,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
} from '@mui/material';
import AssessmentIcon from '@mui/icons-material/Assessment';
import { formatAppDate } from '../../utils/dateTime';
import api from '../../services/httpClient';
import { patientClinical } from '../../services/patientClinical';
import { apiErrorMessage } from '../../services/patientErrors';
import PatientSelect from '../../components/common/PatientSelect';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { usePatientOptions } from '../../hooks/usePatientOptions';
import type { RootState } from '../../store';

interface AssessmentRecord {
  _id?: string;
  id?: string;
  patient_id?: string;
  plan_id?: string | null;
  practitioner_id?: string | null;
  assessment_type?: string; // initial / follow_up / discharge
  range_of_motion?: Record<string, number> | null;
  muscle_strength?: Record<string, number> | null;
  pain_level?: Record<string, number> | null;
  functional_status?: Record<string, number> | null;
  notes?: string | null;
  scores?: Record<string, number> | null;
  created_at?: string;
  updated_at?: string;
}

// 评估类型中文映射（后端枚举：initial, follow_up, discharge）
const assessmentTypeLabels: Record<string, string> = {
  initial: '初期评估',
  follow_up: '随访评估',
  discharge: '出院评估',
};

// 把 { 左肩前屈: 90, ... } 这类指标字典渲染为 "key: value" 行
const renderMetricDict = (dict?: Record<string, number> | null): string[] => {
  if (!dict || typeof dict !== 'object') return [];
  return Object.entries(dict)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${k}: ${v}`);
};

const PAGE_SIZE = 20;

interface ReviewedReport {
  id: string;
  filename: string;
  report_date: string;
  review_current: boolean;
  findings: Array<{ label: string; value: string; unit: string }>;
}

function PatientReports() {
  const load = useCallback(async (signal: AbortSignal) => {
    const patientId = await patientClinical.selfId(signal);
    const { data } = await api.get<{ reports: ReviewedReport[] }>(
      `/clinical/patients/${encodeURIComponent(patientId)}/reports`, { signal },
    );
    if (!Array.isArray(data?.reports)) throw new Error('报告接口返回的数据格式无效');
    return data.reports.filter(report => report.review_current === true);
  }, []);
  const { data, error, loading, reload } = useAsyncResource(load);
  return <Container maxWidth="lg"><Stack spacing={2}>
    <Typography variant="h5" component="h1">康复评估报告</Typography>
    <Typography color="text.secondary">查看当前已通过医护审核的本人报告和确认结果。</Typography>
    {loading && <CircularProgress size={24} aria-label="正在读取报告" />}
    {!!error && <Alert severity="error" action={<Button onClick={reload}>重试</Button>}>
      {apiErrorMessage(error, '无法读取报告')}
    </Alert>}
    {data?.length === 0 && <Alert severity="info">目前没有已通过审核的报告。</Alert>}
    {data?.map(report => <Paper key={report.id} variant="outlined" sx={{ p: 2 }}><Stack spacing={1}>
      <Typography variant="h6">{report.filename}</Typography>
      <Typography color="text.secondary">报告日期：{formatAppDate(report.report_date, 'day')}</Typography>
      {report.findings?.map((finding, index) => <Typography key={`${finding.label}:${index}`}>
        {finding.label}：{finding.value}{finding.unit ? ` ${finding.unit}` : ''}
      </Typography>)}
    </Stack></Paper>)}
  </Stack></Container>;
}

function AssessmentWorkspace({ role, accountId }: { role: string; accountId: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const patients = usePatientOptions(role, accountId, true);
  const requested = searchParams.get('patientId') || '';
  const changePatient = (patientId: string) => {
    setSearchParams(patientId ? { patientId } : {});
  };

  return <Container maxWidth="lg">
    <Paper sx={{ p: 3, mb: 3 }}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <AssessmentIcon color="primary" />
        <Typography variant="h5" component="h1">康复评估报告</Typography>
      </Stack>
      <Box sx={{ maxWidth: 420, mt: 2 }}>
        <PatientSelect fullWidth label="选择患者" value={requested} patients={patients.patients}
          loading={patients.loading} onChange={changePatient} />
        {!!patients.error && <Alert severity="error" sx={{ mt: 1 }} action={<Button onClick={patients.reload}>重试</Button>}>
          {apiErrorMessage(patients.error, '获取患者列表失败')}
        </Alert>}
        {!patients.loading && !patients.error && !patients.patients.length && !requested &&
          <Alert severity="info" sx={{ mt: 1 }}>暂无可选患者。</Alert>}
      </Box>
    </Paper>
    {requested && <AssessmentRecords key={requested} patientId={requested} />}
  </Container>;
}

function AssessmentRecords({ patientId }: { patientId: string }) {
  const [page, setPage] = useState(0);
  const [assessmentId, setAssessmentId] = useState('');
  const loadAssessments = useCallback(async (signal: AbortSignal) => {
    const { data } = await api.get<AssessmentRecord[]>(
      `/rehabilitation/patients/${encodeURIComponent(patientId)}/assessments`,
      { params: { skip: page * PAGE_SIZE, limit: PAGE_SIZE + 1 }, signal },
    );
    if (!Array.isArray(data)) throw new Error('评估接口返回的数据格式无效');
    return { records: data.slice(0, PAGE_SIZE), hasNext: data.length > PAGE_SIZE };
  }, [patientId, page]);
  const { data, loading, error, reload } = useAsyncResource(loadAssessments);
  const assessments = data?.records ?? [];

  const loadDetail = useCallback(async (signal: AbortSignal) => {
    const { data: record } = await api.get<AssessmentRecord>(`/rehabilitation/assessments/${encodeURIComponent(assessmentId)}`, { signal });
    if (record?.patient_id !== patientId || String(record._id ?? record.id) !== assessmentId) {
      throw new Error('评估记录与当前选择不一致');
    }
    return record;
  }, [assessmentId, patientId]);
  const { data: detail, loading: detailLoading, error: detailError, reload: retryDetail } =
    useAsyncResource(loadDetail, Boolean(assessmentId));

  // 格式化时间
  const formatTime = (iso?: string): string =>
    formatAppDate(iso, 'minute', { empty: '未知时间', invalid: iso ? String(iso) : '未知时间' });

  return (
    <>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              评估记录
            </Typography>

            {/* 加载状态 */}
            {loading && (
              <Box display="flex" justifyContent="center" my={3}>
                <CircularProgress />
              </Box>
            )}

            {/* 错误状态 */}
            {!!error && <Alert severity="error" sx={{ mb: 2 }} action={<Button onClick={reload}>重试</Button>}>
              {apiErrorMessage(error, '获取评估记录失败')}
            </Alert>}

            {/* 空状态 */}
            {!loading && !error && assessments.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
                该患者暂无评估记录
              </Typography>
            )}

            {/* 真实评估记录列表 */}
            {!loading && assessments.length > 0 && (
              <List>
                {assessments.map((item) => {
                  const assessmentId = String(item._id ?? item.id ?? '');
                  return (
                    <ListItem
                      key={assessmentId}
                      divider
                      secondaryAction={
                        <Button
                          variant="outlined"
                          size="small"
                          onClick={() => setAssessmentId(assessmentId)}
                          disabled={!assessmentId}
                        >
                          查看详情
                        </Button>
                      }
                    >
                      <ListItemText
                        primary={assessmentTypeLabels[item.assessment_type || ''] || item.assessment_type || '评估记录'}
                        secondary={formatTime(item.created_at)}
                      />
                    </ListItem>
                  );
                })}
              </List>
            )}
            {(page > 0 || data?.hasNext) && <Stack direction="row" spacing={2} alignItems="center" justifyContent="center">
              <Button disabled={loading || page === 0} onClick={() => setPage(page - 1)}>上一页</Button>
              <Typography variant="body2">第 {page + 1} 页</Typography>
              <Button disabled={loading || !data?.hasNext} onClick={() => setPage(page + 1)}>下一页</Button>
            </Stack>}
          </CardContent>
        </Card>

      {/* 评估详情对话框 */}
      <Dialog open={Boolean(assessmentId)} onClose={() => setAssessmentId('')} maxWidth="sm" fullWidth>
        <DialogTitle>评估详情</DialogTitle>
        <DialogContent>
          {detailLoading && (
            <Box display="flex" justifyContent="center" my={3}>
              <CircularProgress />
            </Box>
          )}
          {!!detailError && <Alert severity="error" action={<Button onClick={retryDetail}>重试</Button>}>
            {apiErrorMessage(detailError, '获取评估详情失败')}
          </Alert>}
          {!detailLoading && detail && (
            <List dense>
              <ListItem>
                <ListItemText primary="评估类型" secondary={assessmentTypeLabels[detail.assessment_type || ''] || detail.assessment_type || '未知'} />
              </ListItem>
              <ListItem>
                <ListItemText primary="评估时间" secondary={formatTime(detail.created_at)} />
              </ListItem>
              {(() => {
                // 指标字典逐项如实展示，缺失即为"暂无数据"，不做填充
                const groups: { title: string; lines: string[] }[] = [
                  { title: '关节活动度', lines: renderMetricDict(detail.range_of_motion) },
                  { title: '肌肉力量', lines: renderMetricDict(detail.muscle_strength) },
                  { title: '疼痛指数', lines: renderMetricDict(detail.pain_level) },
                  { title: '功能状态', lines: renderMetricDict(detail.functional_status) },
                  { title: '评估得分', lines: renderMetricDict(detail.scores) },
                ];
                return groups.map((g) => (
                  <React.Fragment key={g.title}>
                    <Divider />
                    <ListItem>
                      <ListItemText
                        primary={g.title}
                        secondary={g.lines.length > 0 ? g.lines.join('；') : '暂无数据'}
                      />
                    </ListItem>
                  </React.Fragment>
                ));
              })()}
              <Divider />
              <ListItem>
                <ListItemText primary="备注" secondary={detail.notes || '暂无备注'} />
              </ListItem>
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAssessmentId('')}>关闭</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default function RehabAssessment() {
  const actor = useSelector((state: RootState) => state.auth.user);
  if (actor?.role === 'patient') return <PatientReports key={actor.id} />;
  return actor ? <AssessmentWorkspace key={`${actor.role}:${actor.id}`} role={actor.role} accountId={actor.id} /> : null;
}
