import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import {
  DeviceRepairRecord,
  DeviceRepairSummary,
  deviceRepairService,
} from '../../services/deviceRepairService';

// T77 设备维修记录（只读）：消费后端 GET /device-repairs/history、
// /device-repairs/{repair_id} 与 /device-repairs/device/{device_id}/summary。
// 后端能力边界：维修记录仅有只读端点（医疗 staff 只读守卫），不存在
// 维修登记（创建/修改/删除）端点，故本面板不提供新建登记入口。

interface DeviceOption {
  id: string;
  name: string;
}

const dateText = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false });
};

const renderValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(renderValue).join('、') || '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

// 详情对话框里不重复展示的主键字段
const DETAIL_SKIP_KEYS = new Set(['_id']);

function RepairDetailDialog({ record, onClose }: { record: DeviceRepairRecord | null; onClose: () => void }) {
  const [detail, setDetail] = useState<DeviceRepairRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!record?._id) { setDetail(null); return; }
    const controller = new AbortController();
    setDetail(null); setLoading(true); setError('');
    deviceRepairService.getDetail(record._id).then((data) => {
      if (!controller.signal.aborted) setDetail(data);
    }).catch(() => {
      if (!controller.signal.aborted) setError('维修记录详情读取失败，请重试。');
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [record?._id]);

  const shown = detail || record;
  return (
    <Dialog open={!!record} fullWidth maxWidth="sm" onClose={onClose}>
      <DialogTitle>维修记录详情</DialogTitle>
      <DialogContent dividers>
        {loading && <CircularProgress size={24} aria-label="正在加载维修记录详情" />}
        {error && <Alert severity="error">{error}</Alert>}
        {shown && !loading && !error && (
          <Stack spacing={1}>
            {Object.keys(shown)
              .filter((key) => !DETAIL_SKIP_KEYS.has(key))
              .sort()
              .map((key) => (
                <Typography key={key} variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                  <strong>{key}</strong>：{renderValue(shown[key])}
                </Typography>
              ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>关闭</Button></DialogActions>
    </Dialog>
  );
}

function DeviceSummaryCard({ deviceId, days }: { deviceId: string; days: number }) {
  const [summary, setSummary] = useState<DeviceRepairSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setSummary(null); setLoading(true); setError('');
    deviceRepairService.getDeviceSummary(deviceId, days).then((data) => {
      if (!controller.signal.aborted) setSummary(data);
    }).catch(() => {
      if (!controller.signal.aborted) setError('修复统计摘要读取失败，请重试。');
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [deviceId, days]);

  if (loading) return <CircularProgress size={22} aria-label="正在加载修复统计" />;
  if (error) return <Alert severity="warning">{error}</Alert>;
  if (!summary) return null;
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>修复统计（最近 {summary.days_analyzed} 天）</Typography>
      <Typography variant="body2">
        共 {summary.total_repairs} 次 · 成功 {summary.successful_repairs} 次 · 失败 {summary.failed_repairs} 次 ·
        成功率 {summary.success_rate}% · 最近修复：{dateText(summary.latest_repair_time)}
      </Typography>
      {summary.common_issues.length > 0 && (
        <Typography variant="body2" color="text.secondary">
          常见修复动作：{summary.common_issues.map((issue) => `${issue.action}（${issue.count}）`).join('、')}
        </Typography>
      )}
    </Paper>
  );
}

const DeviceRepairRecords: React.FC<{ devices: DeviceOption[] }> = ({ devices }) => {
  const [deviceId, setDeviceId] = useState('');
  const [successFilter, setSuccessFilter] = useState('');
  const [days, setDays] = useState('30');
  const [records, setRecords] = useState<DeviceRepairRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [selected, setSelected] = useState<DeviceRepairRecord | null>(null);

  const daysNumber = Number(days) > 0 ? Number(days) : undefined;
  const successValue = successFilter === 'true' ? true : successFilter === 'false' ? false : undefined;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setRecords([]);
    deviceRepairService.listHistory({
      deviceId: deviceId || undefined,
      success: successValue,
      days: daysNumber,
      limit: 100,
    }).then((rows) => {
      if (!controller.signal.aborted) setRecords(rows);
    }).catch(() => {
      if (!controller.signal.aborted) setError('维修记录读取失败，请重试。');
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [deviceId, successFilter, days, reloadKey]);

  const deviceName = useMemo(() => {
    const map = new Map(devices.map((device) => [device.id, device.name]));
    return (id?: string) => (id && map.get(id)) || id || '—';
  }, [devices]);

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 2 }}>
        维修记录为系统自动登记的只读历史（后端仅提供查询端点，无手工登记入口）。
        非 admin 角色只能看到其归属患者设备的记录。
      </Alert>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          select size="small" label="按设备筛选" sx={{ minWidth: 220 }} value={deviceId}
          onChange={(event) => setDeviceId(event.target.value)}
        >
          <MenuItem value="">全部设备</MenuItem>
          {devices.map((device) => (
            <MenuItem key={device.id} value={device.id}>{device.name}</MenuItem>
          ))}
        </TextField>
        <TextField
          select size="small" label="修复结果" sx={{ minWidth: 160 }} value={successFilter}
          onChange={(event) => setSuccessFilter(event.target.value)}
        >
          <MenuItem value="">全部</MenuItem>
          <MenuItem value="true">成功</MenuItem>
          <MenuItem value="false">失败</MenuItem>
        </TextField>
        <TextField
          size="small" type="number" label="最近天数" sx={{ maxWidth: 140 }} value={days}
          inputProps={{ min: 1 }} onChange={(event) => setDays(event.target.value)}
        />
        <Box alignSelf="center">
          <Button onClick={() => setReloadKey((key) => key + 1)} disabled={loading}>刷新</Button>
        </Box>
      </Stack>

      {deviceId && <Box sx={{ mb: 2 }}><DeviceSummaryCard deviceId={deviceId} days={daysNumber || 90} /></Box>}

      {loading && <CircularProgress size={24} aria-label="正在加载维修记录" />}
      {error && (
        <Alert severity="error" action={<Button onClick={() => setReloadKey((key) => key + 1)}>重试</Button>}>
          {error}
        </Alert>
      )}
      {!loading && !error && records.length === 0 && (
        <Alert severity="info">所选范围内没有维修记录。</Alert>
      )}
      {!loading && !error && records.length > 0 && (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>修复时间</TableCell>
                <TableCell>设备</TableCell>
                <TableCell>修复动作</TableCell>
                <TableCell>结果</TableCell>
                <TableCell>详情</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {records.map((record) => (
                <TableRow key={record._id}>
                  <TableCell>{dateText(record.repair_time)}</TableCell>
                  <TableCell>{deviceName(record.device_id)}</TableCell>
                  <TableCell sx={{ maxWidth: 360, overflowWrap: 'anywhere' }}>
                    {renderValue(record.repair_actions)}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      color={record.overall_success === true ? 'success' : record.overall_success === false ? 'error' : 'default'}
                      label={record.overall_success === true ? '成功' : record.overall_success === false ? '失败' : '未标记'}
                    />
                  </TableCell>
                  <TableCell>
                    <Button size="small" onClick={() => setSelected(record)}>详情</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <RepairDetailDialog record={selected} onClose={() => setSelected(null)} />
    </Box>
  );
};

export default DeviceRepairRecords;
