import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Divider,
  Alert,
  Button,
  CircularProgress,
} from '@mui/material';
import api, { apiService } from '../../services/api';

// 医生工作统计（GET /doctors/statistics，后端已真实聚合，见 doctor_router.py:283）
// patientCount: 关联患者数；rehabPlans: 康复计划总数/进行中/已完成；
// completedSessionsThisMonth: 患者本月完成的训练进度记录数（rehab_progress 当前无写入方，通常为 0，真实空数据）
interface DoctorStatistics {
  patientCount: number;
  rehabPlans: { total: number; active: number; completed: number };
  completedSessionsThisMonth: number;
}

const Statistics: React.FC = () => {
  // 真实数据源：GET /doctors/patients（患者总数，空库如实 []）与
  // GET /doctors/statistics（工作统计，已真实聚合，无数据时如实为 0）
  const [patientCount, setPatientCount] = React.useState<number | null>(null);
  const [doctorStats, setDoctorStats] = React.useState<DoctorStatistics | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadStats = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 患者总数（GET /doctors/patients，后端已诚实化：不再返回 mock_* 模拟患者）
      const response = await apiService.doctor.getPatients();
      const list: any[] = Array.isArray(response.data) ? response.data : [];
      setPatientCount(list.length);

      // 医生工作统计（GET /doctors/statistics）
      const statsRes = await api.get('/doctors/statistics');
      setDoctorStats({
        patientCount: Number(statsRes.data?.patientCount ?? 0),
        rehabPlans: {
          total: Number(statsRes.data?.rehabPlans?.total ?? 0),
          active: Number(statsRes.data?.rehabPlans?.active ?? 0),
          completed: Number(statsRes.data?.rehabPlans?.completed ?? 0),
        },
        completedSessionsThisMonth: Number(statsRes.data?.completedSessionsThisMonth ?? 0),
      });
    } catch (err: any) {
      console.error('获取患者统计数据失败:', err);
      setError(err?.response?.data?.detail || err?.message || '获取患者统计数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadStats();
  }, [loadStats]);

  // 无数据源的指标卡片（后端无疗效评定类数据，如实展示"暂无数据源"）
  const noSourceMetrics = [
    { label: '平均康复时间', unit: '天', desc: '患者平均康复所需时间' },
    { label: '康复成功率', unit: '%', desc: '康复治疗的成功比例' },
  ];

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        康复统计分析
      </Typography>

      {error && (
        <Alert
          severity="error"
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small" onClick={loadStats}>
              重试
            </Button>
          }
        >
          {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* 患者总数（GET /doctors/patients） */}
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1">
                患者总数
              </Typography>
              {loading ? (
                <CircularProgress size={24} sx={{ my: 1.5 }} />
              ) : (
                <Typography variant="h5" color="primary">
                  {patientCount ?? '-'} 位
                </Typography>
              )}
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                现有康复治疗中的患者总数（来源：GET /doctors/patients）
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* 康复计划统计（GET /doctors/statistics rehabPlans） */}
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1">
                康复计划（进行中/已完成）
              </Typography>
              {loading ? (
                <CircularProgress size={24} sx={{ my: 1.5 }} />
              ) : (
                <Typography variant="h5" color="primary">
                  {doctorStats ? `${doctorStats.rehabPlans.active} / ${doctorStats.rehabPlans.completed}` : '-'}
                </Typography>
              )}
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                本人负责的康复计划，进行中/已完成（总数 {doctorStats?.rehabPlans.total ?? 0}，
                来源：GET /doctors/statistics）
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* 本月完成训练（GET /doctors/statistics completedSessionsThisMonth；rehab_progress 当前无写入方，通常为 0） */}
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1">
                本月完成训练
              </Typography>
              {loading ? (
                <CircularProgress size={24} sx={{ my: 1.5 }} />
              ) : (
                <Typography variant="h5" color="primary">
                  {doctorStats?.completedSessionsThisMonth ?? 0} 次
                </Typography>
              )}
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                本月完成的训练进度记录数（来源：GET /doctors/statistics；训练进度记录当前无写入方，通常为 0，系真实空数据）
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {noSourceMetrics.map((metric) => (
          <Grid item xs={12} md={6} lg={3} key={metric.label}>
            <Card>
              <CardContent>
                <Typography variant="subtitle1">
                  {metric.label}
                </Typography>
                <Typography variant="h5" color="text.disabled">
                  -- {metric.unit}
                </Typography>
                <Divider sx={{ my: 1 }} />
                <Typography variant="body2" color="text.secondary">
                  {metric.desc}
                </Typography>
                <Typography variant="caption" color="warning.main" component="div" sx={{ mt: 1 }}>
                  暂无数据源：后端无疗效评定类数据，待后端补充后接入。
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}

        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              详细统计数据
            </Typography>
            <Typography variant="body1">
              此页面计划展示康复治疗的详细统计数据和图表，包括治疗成功率、按疾病类型分类的患者数量、治疗时长分布等。
            </Typography>
            <Box sx={{ mt: 2 }}>
              <Alert severity="info">
                患者总数、康复计划数、本月完成训练数已接入真实统计端点（GET /doctors/statistics）；
                平均康复时间、康复成功率等指标依赖疗效评定类数据，后端补齐前保持"暂无数据源"，不展示演示数据。
              </Alert>
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Statistics;
