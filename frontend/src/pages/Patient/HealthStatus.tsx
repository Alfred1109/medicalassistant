import React from 'react';
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import { patientClinical } from '../../services/patientClinical';
import type { PatientHealthAlert, PatientIndicatorRow } from '../../services/patientClinical';

// 指标对照状态与后端 evaluate_indicators 的 state 取值一一对应；未知取值如实回显。
export function indicatorStateLabel(state: string): string {
  const labels: Record<string, string> = {
    inside: '达标',
    outside: '超出范围',
    missing: '暂无数据',
    unbounded: '未设上下限',
    not_numeric: '数值无法对照',
  };
  return labels[state] ?? state;
}

export function alertLevelLabel(level: string | undefined): string {
  return level === 'critical' ? '危急' : level === 'warning' ? '警告' : (level || '警告');
}

export function alertStatusLabel(status: string | undefined): string {
  const labels: Record<string, string> = {
    active: '待处理',
    resolved: '已解决',
    ignored: '已忽略',
  };
  return labels[status ?? ''] ?? (status || '待处理');
}

// 上下限展示不做任何换算，与医护录入的字典值一致。
export function boundsText(low: number | null, high: number | null, unit: string): string {
  const suffix = unit ? ` ${unit}` : '';
  if (low !== null && low !== undefined && high !== null && high !== undefined) return `${low} ~ ${high}${suffix}`;
  if (low !== null && low !== undefined) return `≥ ${low}${suffix}`;
  if (high !== null && high !== undefined) return `≤ ${high}${suffix}`;
  return '未设上下限';
}

const HealthStatus: React.FC = () => {
  const user = useSelector((state: RootState) => state.auth.user);
  const [indicators, setIndicators] = React.useState<PatientIndicatorRow[]>([]);
  const [indicatorMeta, setIndicatorMeta] = React.useState<{ configured: boolean; message: string; coverage: string }>(
    { configured: false, message: '', coverage: '' });
  const [alerts, setAlerts] = React.useState<PatientHealthAlert[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async (signal?: AbortSignal) => {
    if (!user?.id) return;
    setLoading(true);
    setError(null);
    try {
      const patientId = await patientClinical.selfId(signal);
      const [indicatorResponse, alertResponse] = await Promise.all([
        patientClinical.indicators(patientId, signal),
        patientClinical.alerts(patientId, 0, 100, signal),
      ]);
      if (signal?.aborted) return;
      const indicatorData = indicatorResponse.data;
      setIndicators(Array.isArray(indicatorData?.indicators) ? indicatorData.indicators : []);
      setIndicatorMeta({
        configured: Boolean(indicatorData?.configured),
        message: indicatorData?.message || '',
        coverage: indicatorData?.within_bounds
          ? `最近一次对照：${indicatorData.within_bounds.inside}/${indicatorData.within_bounds.compared} 项达标`
          : '',
      });
      setAlerts(Array.isArray(alertResponse.data?.alerts) ? alertResponse.data.alerts : []);
    } catch (err: any) {
      if (!signal?.aborted) {
        setError(err?.response?.data?.detail?.message || err?.response?.data?.detail || err?.message || '健康数据加载失败');
        setIndicators([]);
        setAlerts([]);
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [user?.id]);

  React.useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <Paper sx={{ p: { xs: 2, md: 3 }, maxWidth: 900, mx: 'auto' }}>
      <Stack spacing={3}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <MonitorHeartIcon color="primary" />
          <Typography variant="h5" component="h1">健康指标与预警</Typography>
        </Box>
        {loading && <Box role="status"><CircularProgress size={24} aria-label="正在加载健康数据" /></Box>}
        {error && <Alert severity="error">{error}</Alert>}

        <Stack spacing={1}>
          <Typography variant="h6" component="h2">指标达标对照</Typography>
          {indicatorMeta.message && <Typography variant="body2" color="text.secondary">{indicatorMeta.message}</Typography>}
          {indicatorMeta.coverage && <Typography variant="body2" color="text.secondary">{indicatorMeta.coverage}</Typography>}
          {!loading && !error && indicators.length === 0 && (
            <Alert severity="info">还没有可对照的指标数据。</Alert>
          )}
          {indicators.length > 0 && (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>指标</TableCell>
                    <TableCell>本次结果</TableCell>
                    <TableCell>参考范围</TableCell>
                    <TableCell>对照状态</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {indicators.map(row => (
                    <TableRow key={row.id}>
                      <TableCell>{row.label}</TableCell>
                      <TableCell>{row.value ?? '—'}{row.unit ? ` ${row.unit}` : ''}</TableCell>
                      <TableCell>{boundsText(row.low, row.high, row.unit)}</TableCell>
                      <TableCell>
                        <Chip size="small" color={row.state === 'inside' ? 'success' : row.state === 'outside' ? 'error' : 'default'}
                              label={indicatorStateLabel(row.state)} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Stack>

        <Stack spacing={1}>
          <Typography variant="h6" component="h2">健康预警（只读）</Typography>
          <Typography variant="body2" color="text.secondary">
            预警由健康数据超出阈值时自动产生，处理与消除由医护人员操作。
          </Typography>
          {!loading && !error && alerts.length === 0 && (
            <Alert severity="success">当前没有健康预警记录。</Alert>
          )}
          {alerts.map(alert => (
            <Alert
              key={alert.id}
              severity={alert.alert_level === 'critical' ? 'error' : 'warning'}
              sx={{ '& .MuiAlert-message': { width: '100%' } }}
            >
              <Stack spacing={0.5}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap' }}>
                  <Chip size="small" color={alert.alert_level === 'critical' ? 'error' : 'warning'}
                        label={alertLevelLabel(alert.alert_level)} />
                  <Chip size="small" variant="outlined" label={alertStatusLabel(alert.status)} />
                  <Typography variant="body2">{alert.test_name || alert.vital_type || alert.data_type || '健康数据'}</Typography>
                </Stack>
                <Typography variant="body2">
                  记录值：{typeof alert.value === 'object' ? JSON.stringify(alert.value) : String(alert.value ?? '—')}
                  {alert.unit ? ` ${alert.unit}` : ''}
                </Typography>
                {alert.resolved_at && (
                  <Typography variant="body2" color="text.secondary">
                    处理备注：{alert.resolution_notes || '（无备注）'}
                  </Typography>
                )}
              </Stack>
            </Alert>
          ))}
        </Stack>
      </Stack>
    </Paper>
  );
};

export default HealthStatus;
