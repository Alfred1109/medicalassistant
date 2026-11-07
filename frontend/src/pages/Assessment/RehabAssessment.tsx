import React, { useState, useEffect, useCallback } from 'react';
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
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
} from '@mui/material';
import AssessmentIcon from '@mui/icons-material/Assessment';
import { format } from 'date-fns';
import api, { apiService } from '../../services/api';

/**
 * 康复评估报告页面（真实数据版）
 *
 * 数据来源（均为后端真实端点）：
 * - GET /doctors/patients                      医生的患者列表（仅医生角色可用）
 * - GET /rehabilitation/patients/{patient_id}/assessments  患者评估记录列表
 * - GET /rehabilitation/assessments/{id}       单条评估详情
 *
 * 后端不提供评估指标"提升百分比"之类的对比数据（对比端点需单独调用，
 * 且历史记录为空时如实展示），页面不做任何虚构指标。
 */

// 评估记录字段（对应 backend/app/schemas/rehabilitation.py 的 AssessmentBase/Response，
// 列表端点返回原始 Mongo 文档，字段均为可选）
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

// 患者下拉项
interface PatientOption {
  id: string;
  name: string;
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

const RehabAssessment: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // 患者选择：URL ?patientId= 优先，其次下拉选择
  const [patients, setPatients] = useState<PatientOption[]>([]);
  const [patientsLoading, setPatientsLoading] = useState<boolean>(false);
  const [patientsError, setPatientsError] = useState<string | null>(null);
  const [selectedPatientId, setSelectedPatientId] = useState<string>(searchParams.get('patientId') || '');

  // 评估列表
  const [assessments, setAssessments] = useState<AssessmentRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 详情对话框
  const [detailOpen, setDetailOpen] = useState<boolean>(false);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detail, setDetail] = useState<AssessmentRecord | null>(null);

  // 加载医生的患者列表（真实接口 GET /doctors/patients；患者角色调用会 403，如实提示）
  useEffect(() => {
    let cancelled = false;
    const loadPatients = async () => {
      setPatientsLoading(true);
      setPatientsError(null);
      try {
        const response = await apiService.doctor.getPatients();
        const list: any[] = Array.isArray(response.data) ? response.data : [];
        if (!cancelled) {
          setPatients(list.map((p) => ({
            id: String(p?.id ?? p?._id ?? ''),
            name: String(p?.name ?? '未知患者'),
          })).filter((p) => p.id));
        }
      } catch (err: any) {
        if (!cancelled) {
          // 403 = 当前角色无权访问患者列表（如患者本人），仅提示，不阻塞 URL 指定患者的方式
          setPatientsError(
            err?.response?.status === 403
              ? '当前账号无患者管理权限，请通过链接参数 ?patientId= 指定患者'
              : err?.response?.data?.detail || err?.message || '获取患者列表失败'
          );
        }
      } finally {
        if (!cancelled) {
          setPatientsLoading(false);
        }
      }
    };
    loadPatients();
    return () => {
      cancelled = true;
    };
  }, []);

  // 加载选中患者的评估列表（真实接口 GET /rehabilitation/patients/{patient_id}/assessments）
  const loadAssessments = useCallback(async (patientId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get<AssessmentRecord[]>(
        `/rehabilitation/patients/${patientId}/assessments`
      );
      setAssessments(Array.isArray(response.data) ? response.data : []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || '获取评估记录失败');
      setAssessments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // 选中患者变化时拉取评估列表，并同步到 URL 查询参数
  const handlePatientChange = (patientId: string) => {
    setSelectedPatientId(patientId);
    setAssessments([]);
    setError(null);
    setSearchParams(patientId ? { patientId } : {});
    if (patientId) {
      loadAssessments(patientId);
    }
  };

  // URL 直达 ?patientId= 时自动加载
  useEffect(() => {
    const pid = searchParams.get('patientId');
    if (pid) {
      loadAssessments(pid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 打开详情对话框（真实接口 GET /rehabilitation/assessments/{id}）
  const handleViewDetail = async (assessmentId: string) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailError(null);
    setDetail(null);
    try {
      const response = await api.get<AssessmentRecord>(
        `/rehabilitation/assessments/${assessmentId}`
      );
      setDetail(response.data);
    } catch (err: any) {
      setDetailError(err?.response?.data?.detail || err?.message || '获取评估详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  // 格式化时间
  const formatTime = (iso?: string): string => {
    if (!iso) return '未知时间';
    const date = new Date(iso);
    if (isNaN(date.getTime())) return String(iso);
    return format(date, 'yyyy-MM-dd HH:mm');
  };

  return (
    <Container maxWidth="lg">
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <AssessmentIcon color="primary" sx={{ mr: 2, fontSize: 32 }} />
          <Typography variant="h5" component="h1">
            康复评估报告
          </Typography>
        </Box>
        <Typography variant="body1" color="text.secondary" paragraph>
          查看患者康复评估记录与评估结果
        </Typography>

        {/* 患者选择器（医生角色可用；患者角色请通过 ?patientId= 指定） */}
        <Box sx={{ maxWidth: 360 }}>
          <FormControl fullWidth disabled={patientsLoading}>
            <InputLabel>选择患者</InputLabel>
            <Select
              value={selectedPatientId}
              label="选择患者"
              onChange={(e) => handlePatientChange(e.target.value as string)}
            >
              {patients.map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {patientsLoading && (
            <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
              <CircularProgress size={16} sx={{ mr: 1 }} />
              <Typography variant="caption" color="text.secondary">
                正在加载患者列表...
              </Typography>
            </Box>
          )}
          {patientsError && (
            <Alert severity="info" sx={{ mt: 1 }}>
              {patientsError}
            </Alert>
          )}
        </Box>
      </Paper>

      {/* 未选择患者 */}
      {!selectedPatientId ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1">请先选择患者</Typography>
        </Paper>
      ) : (
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
            {!loading && error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

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
                          onClick={() => assessmentId && handleViewDetail(assessmentId)}
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
          </CardContent>
        </Card>
      )}

      {/* 评估详情对话框 */}
      <Dialog open={detailOpen} onClose={() => setDetailOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>评估详情</DialogTitle>
        <DialogContent>
          {detailLoading && (
            <Box display="flex" justifyContent="center" my={3}>
              <CircularProgress />
            </Box>
          )}
          {!detailLoading && detailError && <Alert severity="error">{detailError}</Alert>}
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
          <Button onClick={() => setDetailOpen(false)}>关闭</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default RehabAssessment;
