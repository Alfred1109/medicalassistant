import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Alert,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import api from '../../services/api';

// 患者统计（GET /patients/statistics，后端已真实聚合，见 patient_router.py:251）
// rehabPlans: 本人康复计划总数/进行中/已完成；
// progress: 训练进度记录数/已完成数/完成率（rehab_progress 当前无写入方，通常为 0，真实空数据）
interface PatientStatistics {
  rehabPlans: { total: number; active: number; completed: number };
  progress: { totalRecords: number; completedRecords: number; completionRate: number };
}

// 下列指标无真实数据源，显示"暂无数据源"而非伪造数值。
const NO_SOURCE_STATS = [
  { icon: <TrendingUpIcon sx={{ color: 'text.disabled', mr: 1 }} />, label: '康复进度', display: '-- %', desc: '本月康复总体进度' },
  { icon: <AccessTimeIcon sx={{ color: 'text.disabled', mr: 1 }} />, label: '训练时长', display: '-- 小时', desc: '累计训练时长' },
  { icon: <ReportProblemIcon sx={{ color: 'text.disabled', mr: 1 }} />, label: '平均疼痛指数', display: '-- /10', desc: '近两周平均疼痛水平' },
];

// rehab_progress 文档中不对外展示的内部字段
const INTERNAL_KEYS = new Set(['_id', 'id', 'user_id']);

const Statistics: React.FC = () => {
  const [progressData, setProgressData] = React.useState<Record<string, any> | null>(null);
  const [progressUnavailable, setProgressUnavailable] = React.useState<string | null>(null);
  const [patientStats, setPatientStats] = React.useState<PatientStatistics | null>(null);
  const [statsError, setStatsError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  // 真实接口 GET /patients/statistics（康复计划数与训练完成率，已真实聚合）
  const loadStats = React.useCallback(async () => {
    setStatsError(null);
    try {
      const response = await api.get('/patients/statistics');
      const data = response?.data;
      setPatientStats(
        data && typeof data === 'object'
          ? {
              rehabPlans: {
                total: Number(data?.rehabPlans?.total ?? 0),
                active: Number(data?.rehabPlans?.active ?? 0),
                completed: Number(data?.rehabPlans?.completed ?? 0),
              },
              progress: {
                totalRecords: Number(data?.progress?.totalRecords ?? 0),
                completedRecords: Number(data?.progress?.completedRecords ?? 0),
                completionRate: Number(data?.progress?.completionRate ?? 0),
              },
            }
          : null
      );
    } catch (err: any) {
      console.error('获取患者统计数据失败:', err);
      setPatientStats(null);
      setStatsError(err?.response?.data?.detail || err?.message || '获取患者统计数据失败');
    }
  }, []);

  // 真实接口 GET /patients/rehab-progress（读取 rehab_progress 集合；
  // 当前代码库无写入方，通常返回 404 —— 以空态如实呈现）
  const loadProgress = React.useCallback(async () => {
    setLoading(true);
    setProgressUnavailable(null);
    try {
      const response = await api.get('/patients/rehab-progress');
      const data = response?.data;
      setProgressData(data && typeof data === 'object' ? data : null);
    } catch (err: any) {
      const status = err?.response?.status;
      console.error('获取康复进度失败:', err);
      setProgressUnavailable(
        status === 404
          ? '暂无康复进度记录（尚未生成康复进度数据）'
          : err?.response?.data?.detail || err?.message || '获取康复进度失败'
      );
      setProgressData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadProgress();
    loadStats();
  }, [loadProgress, loadStats]);

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        我的康复数据
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        数据说明：康复计划数与训练完成率已接入真实统计端点（GET /patients/statistics）；
        其余指标（康复进度、训练时长、平均疼痛指数）暂无数据源，后端补齐前不展示演示数据。
      </Alert>

      {statsError && (
        <Alert severity="error" sx={{ mb: 3 }}>{statsError}</Alert>
      )}

      <Grid container spacing={3}>
        {/* 训练完成率（GET /patients/statistics progress.completionRate） */}
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <FitnessCenterIcon sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6">
                  训练完成率
                </Typography>
              </Box>
              <Typography variant="h4" color="primary" gutterBottom>
                {patientStats ? `${patientStats.progress.completionRate}%` : '...'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                已完成 {patientStats?.progress.completedRecords ?? 0} / 共 {patientStats?.progress.totalRecords ?? 0} 条训练记录
              </Typography>
              <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1 }}>
                来源：GET /patients/statistics；训练进度记录当前无写入方，通常为 0，系真实空数据。
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* 康复计划数（GET /patients/statistics rehabPlans） */}
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <TrendingUpIcon sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6">
                  康复计划（进行中/已完成）
                </Typography>
              </Box>
              <Typography variant="h4" color="primary" gutterBottom>
                {patientStats ? `${patientStats.rehabPlans.active} / ${patientStats.rehabPlans.completed}` : '...'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                本人康复计划，进行中/已完成（总数 {patientStats?.rehabPlans.total ?? 0}）
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {NO_SOURCE_STATS.map((stat) => (
          <Grid item xs={12} md={6} lg={3} key={stat.label}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" mb={1}>
                  {stat.icon}
                  <Typography variant="h6">
                    {stat.label}
                  </Typography>
                </Box>
                <Typography variant="h4" color="text.disabled" gutterBottom>
                  {stat.display}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {stat.desc}
                </Typography>
                <Typography variant="caption" color="warning.main" component="div" sx={{ mt: 1 }}>
                  暂无数据源，待后端实现统计接口后接入。
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}

        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6" gutterBottom>
                康复进度记录
              </Typography>
              <Button
                variant="outlined"
                size="small"
                onClick={loadProgress}
                disabled={loading}
              >
                刷新
              </Button>
            </Box>

            {loading ? (
              <Typography variant="body2" color="text.secondary">
                加载中...
              </Typography>
            ) : progressData ? (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>字段</TableCell>
                      <TableCell>值</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {Object.entries(progressData)
                      .filter(([key]) => !INTERNAL_KEYS.has(key))
                      .map(([key, value]) => (
                        <TableRow key={key} hover>
                          <TableCell>{key}</TableCell>
                          <TableCell>
                            {typeof value === 'object' && value !== null
                              ? JSON.stringify(value)
                              : String(value)}
                          </TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Alert severity="info">
                {progressUnavailable ?? '暂无康复进度记录'}
              </Alert>
            )}
          </Paper>
        </Grid>

        <Grid item xs={12}>
          <Paper sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body1">
              更详细的图表分析和数据报告功能将在后端统计能力就绪后推出。
            </Typography>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Statistics;
