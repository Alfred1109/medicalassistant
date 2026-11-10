import React, { useState, useEffect, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Box,
  Typography,
  Container,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  CircularProgress,
} from '@mui/material';
import RecommendIcon from '@mui/icons-material/Recommend';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import { AppDispatch, RootState } from '../../store';
import { getRecommendations } from '../../store/slices/rehabSlice';
import { Exercise } from '../../types/rehab';
import { apiService } from '../../services/api';

/**
 * 训练推荐页面（真实数据版）
 *
 * 数据来源：dispatch 已有的 getRecommendations thunk
 * （GET /rehabilitation/exercises/recommendations，patient_id 为必填查询参数，
 * condition / goal 可选，用于过滤）。
 *
 * 后端不提供推荐历史与训练反馈接口，相关虚构板块已移除；
 * 选中患者后即以当前输入的病症/目标发起真实查询。
 */

// 难度中文映射（后端枚举 easy/medium/hard）
const difficultyLabels: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
};

const ExerciseRecommendations: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const [searchParams, setSearchParams] = useSearchParams();

  const recommendations = useSelector((state: RootState) => state.rehab?.recommendations || []);
  const loading = useSelector((state: RootState) => state.rehab?.loading || false);
  const error = useSelector((state: RootState) => state.rehab?.error);

  // 患者：URL ?patientId= 优先，其次下拉选择（医生患者列表，患者角色 403 如实提示）
  const [patients, setPatients] = useState<{ id: string; name: string }[]>([]);
  const [patientsLoading, setPatientsLoading] = useState(false);
  const [patientsError, setPatientsError] = useState<string | null>(null);
  const [patientId, setPatientId] = useState<string>(searchParams.get('patientId') || '');

  // 过滤条件（均为可选，后端对应可选查询参数）
  const [condition, setCondition] = useState('');
  const [goal, setGoal] = useState('');

  // 发起真实推荐查询
  const fetchRecommendations = useCallback((pid: string, cond: string, gol: string) => {
    if (!pid) return;
    dispatch(getRecommendations({ patientId: pid, condition: cond.trim(), goal: gol.trim() }));
  }, [dispatch]);

  // 加载医生的患者列表（真实接口 GET /doctors/patients；患者角色 403 如实提示）
  useEffect(() => {
    let cancelled = false;
    const loadPatients = async () => {
      setPatientsLoading(true);
      setPatientsError(null);
      try {
        const response = await apiService.doctor.getPatients();
        const list: any[] = Array.isArray(response.data) ? response.data : [];
        if (!cancelled) {
          setPatients(list
            .map((p) => ({ id: String(p?.id ?? p?._id ?? ''), name: String(p?.name ?? '未知患者') }))
            .filter((p) => p.id));
        }
      } catch (err: any) {
        if (!cancelled) {
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

  // 选中患者即以默认条件发起查询，并同步 URL
  const handlePatientChange = (pid: string) => {
    setPatientId(pid);
    setSearchParams(pid ? { patientId: pid } : {});
    fetchRecommendations(pid, condition, goal);
  };

  // URL 直达 ?patientId= 时自动查询
  useEffect(() => {
    const pid = searchParams.get('patientId');
    if (pid) {
      fetchRecommendations(pid, condition, goal);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasPatient = !!patientId;

  return (
    <Container maxWidth="lg">
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <RecommendIcon color="primary" sx={{ mr: 2, fontSize: 32 }} />
          <Typography variant="h5" component="h1">
            训练推荐
          </Typography>
        </Box>
        <Typography variant="body1" color="text.secondary" paragraph>
          按病症和目标询问本机已配置的文本模型。结果是参考建议，不是已签署的训练处方。
        </Typography>

        {/* 查询控件：患者（必填，后端 patient_id 必填） + 病症/目标（可选过滤） */}
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth disabled={patientsLoading}>
              <InputLabel>选择患者</InputLabel>
              <Select
                value={patientId}
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
          </Grid>
          <Grid item xs={12} sm={3}>
            <TextField
              fullWidth
              label="病症（可选）"
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
            />
          </Grid>
          <Grid item xs={12} sm={3}>
            <TextField
              fullWidth
              label="康复目标（可选）"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
          </Grid>
          <Grid item xs={12} sm={2}>
            <Button
              variant="contained"
              fullWidth
              disabled={!hasPatient || loading}
              onClick={() => fetchRecommendations(patientId, condition, goal)}
            >
              查询推荐
            </Button>
          </Grid>
        </Grid>

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
      </Paper>

      {/* 未选择患者 */}
      {!hasPatient ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1">请先选择患者以获取训练推荐</Typography>
        </Paper>
      ) : (
        <>
          {/* 错误状态 */}
          {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

          {/* 加载状态 */}
          {loading && (
            <Box display="flex" justifyContent="center" my={4}>
              <CircularProgress />
            </Box>
          )}

          {/* 空状态 */}
          {!loading && !error && recommendations.length === 0 && (
            <Paper sx={{ p: 4, textAlign: 'center' }}>
              <Typography variant="body1">暂无匹配的训练推荐</Typography>
            </Paper>
          )}

          {/* 真实推荐结果 */}
          {!loading && recommendations.length > 0 && (
            <Grid container spacing={3}>
              {recommendations.map((exercise: Exercise) => {
                const exerciseId = String(exercise.id ?? exercise._id ?? '');
                return (
                  <Grid item xs={12} md={6} key={exerciseId}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                          <FitnessCenterIcon color="primary" sx={{ mr: 1 }} />
                          <Typography variant="h6">{exercise.name}</Typography>
                        </Box>

                        <Typography variant="body2" color="text.secondary" paragraph>
                          {exercise.description || '暂无描述'}
                        </Typography>

                        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
                          <Typography variant="body2">
                            <strong>难度:</strong>{' '}
                            {exercise.difficulty
                              ? difficultyLabels[exercise.difficulty] || exercise.difficulty
                              : '未标注'}
                          </Typography>
                          <Typography variant="body2">
                            <strong>时长:</strong>{' '}
                            {exercise.duration_minutes != null ? `${exercise.duration_minutes} 分钟` : '未标注'}
                          </Typography>
                          {exercise.body_part && (
                            <Typography variant="body2">
                              <strong>部位:</strong> {exercise.body_part}
                            </Typography>
                          )}
                        </Box>

                        <Box sx={{ mb: 2 }}>
                          {exerciseId && (
                            <Chip
                              size="small"
                              label={exercise.source === 'configured_model' ? `模型 ${exercise.model || ''}`.trim() : `ID: ${exerciseId}`}
                              variant="outlined"
                              sx={{ mr: 0.5 }}
                            />
                          )}
                        </Box>

                        <Box sx={{ display: 'flex', gap: 1 }}>
                          <Button
                            variant="contained"
                            color="primary"
                            component={Link}
                            to={`/app/exercises/${exerciseId}`}
                            disabled={!exerciseId}
                          >
                            开始训练
                          </Button>
                          <Button
                            variant="outlined"
                            component={Link}
                            to={`/app/exercises/${exerciseId}`}
                            disabled={!exerciseId}
                          >
                            查看详情
                          </Button>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                );
              })}
            </Grid>
          )}
        </>
      )}

      {/* 诚实说明：推荐历史与训练反馈暂无后端支持 */}
      <Alert severity="info" sx={{ mt: 3 }}>
        推荐历史与训练反馈功能暂无后端支持，本页不做展示。
      </Alert>
    </Container>
  );
};

export default ExerciseRecommendations;
