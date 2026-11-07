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

// 后端 GET /patients/statistics 为存根端点（直接返回空对象，见 patient_router.py:251-260），
// 下列指标均无真实数据源，显示"暂无数据源"而非伪造数值。
const NO_SOURCE_STATS = [
  { icon: <FitnessCenterIcon sx={{ color: 'text.disabled', mr: 1 }} />, label: '训练完成率', display: '-- %', desc: '康复训练计划完成比例' },
  { icon: <TrendingUpIcon sx={{ color: 'text.disabled', mr: 1 }} />, label: '康复进度', display: '-- %', desc: '本月康复总体进度' },
  { icon: <AccessTimeIcon sx={{ color: 'text.disabled', mr: 1 }} />, label: '训练时长', display: '-- 小时', desc: '累计训练时长' },
  { icon: <ReportProblemIcon sx={{ color: 'text.disabled', mr: 1 }} />, label: '平均疼痛指数', display: '-- /10', desc: '近两周平均疼痛水平' },
];

// rehab_progress 文档中不对外展示的内部字段
const INTERNAL_KEYS = new Set(['_id', 'id', 'user_id']);

const Statistics: React.FC = () => {
  const [progressData, setProgressData] = React.useState<Record<string, any> | null>(null);
  const [progressUnavailable, setProgressUnavailable] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

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
  }, [loadProgress]);

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        我的康复数据
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        注意：本页统计指标依赖后端 /patients/statistics 接口，该接口当前为存根（返回空对象），
        相关指标在后端实现前不展示演示数据。
      </Alert>

      <Grid container spacing={3}>
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
