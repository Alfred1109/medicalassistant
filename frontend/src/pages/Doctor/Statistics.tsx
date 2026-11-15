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
import { useSelector } from 'react-redux';
import api, { apiService } from '../../services/api';
import { apiErrorMessage } from '../../services/patientErrors';
import { RootState } from '../../store';

// 医护工作统计（医生 GET /doctors/statistics；健康管理师 GET /health-managers/statistics，
// 后端均为真实聚合，见 doctor_router.py / health_manager_router.py）
// patientCount: 关联患者数；rehabPlans: 康复方案总数/进行中/已完成；
// followUps: 仅健康管理师端返回（随访总数/已完成/待完成）
interface WorkStatistics {
  patientCount: number;
  rehabPlans: { total: number; active: number; completed: number };
  patientSelfReportsThisMonth: {
    total: number; completed: number; partial: number; not_done: number;
    periodStart: string; periodEnd: string;
  };
  followUps?: { total: number; completed: number; pending: number };
}

const Statistics: React.FC = () => {
  // 医生与健康管理师共用本页面，但统计端点按角色分域（各自后端都有角色守卫）
  const userRole = useSelector((state: RootState) => state.auth.user?.role);
  const isHealthManager = userRole === 'health_manager';
  const statisticsPath = isHealthManager ? '/health-managers/statistics' : '/doctors/statistics';
  const patientsPath = isHealthManager ? 'GET /health-managers/patients' : 'GET /doctors/patients';

  // 真实数据源：患者列表（空库如实 []）与工作统计（已真实聚合，无数据时如实为 0）
  const [patientCount, setPatientCount] = React.useState<number | null>(null);
  const [workStats, setWorkStats] = React.useState<WorkStatistics | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadStats = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 患者总数（归属患者列表；空库如实 []，不再返回 mock_* 模拟患者）
      const response = isHealthManager
        ? await apiService.healthManager.getPatients()
        : await apiService.doctor.getPatients();
      const list: any[] = Array.isArray(response.data) ? response.data : [];
      setPatientCount(list.length);

      // 工作统计（医生 / 健康管理师各自端点）
      const statsRes = await api.get(statisticsPath);
      const reportStats = statsRes.data?.patientSelfReportsThisMonth;
      const reportCounts = ['total', 'completed', 'partial', 'not_done']
        .map(key => Number(reportStats?.[key]));
      if (!reportStats || reportCounts.some(value => !Number.isInteger(value) || value < 0)
          || typeof reportStats.periodStart !== 'string' || !reportStats.periodStart
          || typeof reportStats.periodEnd !== 'string' || !reportStats.periodEnd) {
        throw new Error('患者自报统计响应缺少有效计数或时间范围');
      }
      setWorkStats({
        patientCount: Number(statsRes.data?.patientCount ?? 0),
        rehabPlans: {
          total: Number(statsRes.data?.rehabPlans?.total ?? 0),
          active: Number(statsRes.data?.rehabPlans?.active ?? 0),
          completed: Number(statsRes.data?.rehabPlans?.completed ?? 0),
        },
        patientSelfReportsThisMonth: {
          total: reportCounts[0],
          completed: reportCounts[1],
          partial: reportCounts[2],
          not_done: reportCounts[3],
          periodStart: reportStats.periodStart,
          periodEnd: reportStats.periodEnd,
        },
        followUps: statsRes.data?.followUps
          ? {
            total: Number(statsRes.data.followUps.total ?? 0),
            completed: Number(statsRes.data.followUps.completed ?? 0),
            pending: Number(statsRes.data.followUps.pending ?? 0),
          }
          : undefined,
      });
    } catch (err: any) {
      console.error('获取患者统计数据失败:', err);
      setWorkStats(null);
      setError(apiErrorMessage(err, '获取患者统计数据失败'));
    } finally {
      setLoading(false);
    }
  }, [isHealthManager, statisticsPath]);

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
        {/* 患者总数（归属患者列表端点） */}
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
                现有康复治疗中的患者总数（来源：{patientsPath}）
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* 康复方案统计（统计端点 rehabPlans） */}
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
                  {workStats ? `${workStats.rehabPlans.active} / ${workStats.rehabPlans.completed}` : '-'}
                </Typography>
              )}
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                本人负责的康复计划，进行中/已完成（总数 {workStats?.rehabPlans.total ?? 0}，
                来源：{statisticsPath}）
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* 统计患者自报条数，不将其解释为已核验训练场次。 */}
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1">
                本月患者自报
              </Typography>
              {loading ? (
                <CircularProgress size={24} sx={{ my: 1.5 }} />
              ) : (
                <Typography variant="h5" color="primary">
                  {workStats ? `${workStats.patientSelfReportsThisMonth.total} 条` : '--'}
                </Typography>
              )}
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                {workStats ? <>自报完成 {workStats.patientSelfReportsThisMonth.completed}，
                  部分完成 {workStats.patientSelfReportsThisMonth.partial}，
                  未完成 {workStats.patientSelfReportsThisMonth.not_done}。按执行时间统计：
                  {workStats.patientSelfReportsThisMonth.periodStart} 至 {workStats.patientSelfReportsThisMonth.periodEnd}。</>
                  : '自报统计暂不可用。'}
              </Typography>
              <Typography variant="caption" color="text.secondary" component="div">
                来源：{statisticsPath}；计数代表患者自述，不代表已核验训练场次。
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* 随访统计（仅健康管理师端返回 followUps） */}
        {isHealthManager && (
          <Grid item xs={12} md={6} lg={3}>
            <Card>
              <CardContent>
                <Typography variant="subtitle1">
                  随访（已完成/待完成）
                </Typography>
                {loading ? (
                  <CircularProgress size={24} sx={{ my: 1.5 }} />
                ) : (
                  <Typography variant="h5" color="primary">
                    {workStats?.followUps
                      ? `${workStats.followUps.completed} / ${workStats.followUps.pending}`
                      : '-'}
                  </Typography>
                )}
                <Divider sx={{ my: 1 }} />
                <Typography variant="body2" color="text.secondary">
                  本人负责患者的随访记录，已完成/待完成（总数 {workStats?.followUps?.total ?? 0}，
                  来源：{statisticsPath}）
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        )}

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
                  暂无数据源：后端尚无经确认的训练场次统计口径。
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
                患者总数、康复计划数、本月患者自报数已接入真实统计端点（{statisticsPath}），自报不等同于已核验训练场次；
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
