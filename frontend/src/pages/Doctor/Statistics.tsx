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
import { apiService } from '../../services/api';

const Statistics: React.FC = () => {
  // 患者总数来自真实接口 GET /doctors/patients；
  // 其余指标后端 GET /doctors/statistics 为存根（返回空对象，见 doctor_router.py:250），
  // 无数据源，显示"暂无数据源"而非伪造数值。
  const [patientCount, setPatientCount] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [mockNotice, setMockNotice] = React.useState<string | null>(null);

  const loadStats = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    setMockNotice(null);
    try {
      const response = await apiService.doctor.getPatients();
      const list: any[] = Array.isArray(response.data) ? response.data : [];
      // 后端缺陷防护：无真实患者时 GET /doctors/patients 会返回 id 形如 "mock_1"
      // 的模拟数据（doctor_router.py:34-49），过滤后不作为真实统计展示
      const realPatients = list.filter(p => !String(p?.id ?? p?._id ?? '').startsWith('mock_'));
      if (list.length > realPatients.length) {
        setMockNotice('后端在无真实患者数据时返回了模拟患者（后端缺陷，待修复），患者总数不计入模拟数据。');
      }
      setPatientCount(realPatients.length);
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

  // 无数据源的指标卡片（后端 /doctors/statistics 为存根）
  const noSourceMetrics = [
    { label: '本月治疗次数', unit: '次', desc: '本月进行的康复治疗总次数' },
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

      {mockNotice && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          {mockNotice}
        </Alert>
      )}

      <Grid container spacing={3}>
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
                  暂无数据源：后端 /doctors/statistics 为存根端点（返回空对象），待后端实现后接入。
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
                详细统计与图表依赖后端统计聚合端点，当前 /doctors/statistics 未实现具体查询逻辑，
                相关功能在后端补齐前保持禁用，不展示演示数据。
              </Alert>
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Statistics;
