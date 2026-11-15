import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { formatAppDate } from '../../utils/dateTime';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
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
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import {
  deviceGateway,
  AutomatedReading,
  CollectionSession,
  DeviceQualityReport,
  DevicePublicationOption,
  ProtocolAssumption,
} from '../../services/deviceService';

// T74 设备自动采集详情面板：
// - 自动采集数据时序列表 + 单指标 sparkline（单系列：不设图例，标题即指标名；
//   表格视图始终存在，可访问性兜底）；
// - 质量标记（quality_flags）以「文字 chip」呈现，不做纯颜色编码；
// - 采集会话管理（开始/结束/取消）；
// - 协议假设核实清单透出（待厂商文档核实的字段假设）。

const formatDate = (value?: string | null) =>
  formatAppDate(value, 'locale', { empty: '—', invalid: value ? String(value) : '—' });

// 质量标记语义化标签（与后端 quality_flags 常量对齐）
const QUALITY_FLAG_LABELS: Record<string, string> = {
  out_of_order: '乱序',
  unregistered_metric: '未登记指标',
};
const flagLabel = (flag: string) => {
  if (flag.startsWith('out_of_range:')) return `超范围:${flag.split(':')[1]}`;
  return QUALITY_FLAG_LABELS[flag] ?? flag;
};

// 单系列 sparkline：细线（2px）、末点标记，文本一律用文本色
const Sparkline: React.FC<{ points: Array<{ ts: number; value: number }>; color: string }> = ({
  points,
  color,
}) => {
  if (points.length < 2) {
    return (
      <Typography variant="body2" color="text.secondary">
        数据点不足 2 个，暂不绘制趋势图（完整数值见下方列表）
      </Typography>
    );
  }
  const width = 480;
  const height = 120;
  const padding = 8;
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const tsMin = points[0].ts;
  const tsMax = points[points.length - 1].ts;
  const tsSpan = tsMax - tsMin || 1;
  const coords = points.map((p) => ({
    x: padding + ((p.ts - tsMin) / tsSpan) * (width - padding * 2),
    y: height - padding - ((p.value - min) / span) * (height - padding * 2),
  }));
  const path = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const last = coords[coords.length - 1];
  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="自动采集数据趋势简图（完整数值见下方列表）"
      data-testid="device-reading-sparkline"
    >
      <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last.x} cy={last.y} r={4} fill={color} />
    </svg>
  );
};

const DeviceIngestionPanel: React.FC<{
  deviceId: string;
  deviceName: string;
  open: boolean;
  onClose: () => void;
}> = ({ deviceId, deviceName, open, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readings, setReadings] = useState<AutomatedReading[]>([]);
  const [report, setReport] = useState<DeviceQualityReport | null>(null);
  const [sessions, setSessions] = useState<CollectionSession[]>([]);
  const [publicationOptions, setPublicationOptions] = useState<DevicePublicationOption[]>([]);
  const [assumptions, setAssumptions] = useState<ProtocolAssumption[]>([]);
  const [adapterId, setAdapterId] = useState<string | null>(null);
  const [assumptionNote, setAssumptionNote] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [planId, setPlanId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [prescriptionItemId, setPrescriptionItemId] = useState('');
  const [sessionBusy, setSessionBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [readingRows, qualityReport, sessionRows, protocol, planOptions] = await Promise.all([
        deviceGateway.getAutomatedReadings(deviceId),
        deviceGateway.getQualityReport(deviceId),
        deviceGateway.listCollectionSessions(deviceId),
        deviceGateway.getProtocolAssumptions(deviceId),
        deviceGateway.getPublicationOptions(deviceId).catch(() => []),
      ]);
      setReadings(readingRows);
      setReport(qualityReport);
      setSessions(sessionRows);
      setPublicationOptions(planOptions);
      setAssumptions(protocol.assumptions ?? []);
      setAdapterId(protocol.adapter_id ?? null);
      setAssumptionNote(protocol.message ?? null);
      const types = Array.from(new Set(readingRows.map((r) => r.data_type)));
      setSelectedType((prev) => (prev && types.includes(prev) ? prev : types[0] ?? null));
    } catch (err: any) {
      setError(
        err.response
          ? `加载自动采集数据失败: ${err.response.status} ${err.response.data?.detail ?? ''}`
          : `加载自动采集数据失败: ${err.message ?? '未知错误'}`,
      );
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const dataTypes = useMemo(
    () => Array.from(new Set(readings.map((r) => r.data_type))),
    [readings],
  );

  const chartPoints = useMemo(() => {
    const rows = readings
      .filter((r) => r.data_type === selectedType)
      .map((r) => ({ ts: new Date(r.timestamp).getTime(), value: Number(r.value) }))
      .filter((p) => !Number.isNaN(p.ts) && !Number.isNaN(p.value))
      .sort((a, b) => a.ts - b.ts);
    return rows;
  }, [readings, selectedType]);

  const handleStartSession = async () => {
    setSessionBusy(true);
    setActionMessage(null);
    setActionError(null);
    try {
      await deviceGateway.startCollectionSession(deviceId, {
        plan_id: planId.trim() || undefined,
        version_id: versionId.trim() || undefined,
        prescription_item_id: prescriptionItemId.trim() || undefined,
      });
      setActionMessage('采集会话已开始，期间设备上报读数将挂到该会话');
      await load();
    } catch (err: any) {
      setActionError(err.response?.data?.detail ?? `开始会话失败: ${err.message ?? '未知错误'}`);
    } finally {
      setSessionBusy(false);
    }
  };

  const handleEndSession = async (sessionId: string, cancel: boolean) => {
    setSessionBusy(true);
    setActionMessage(null);
    setActionError(null);
    try {
      const ended = await deviceGateway.endCollectionSession(deviceId, sessionId, cancel);
      const summary = ended.summary ?? {};
      setActionMessage(
        cancel
          ? '采集会话已取消'
          : `采集会话已结束：自动读数 ${summary.readings_count ?? 0} 条，含质量标记 ${summary.flagged_count ?? 0} 条`,
      );
      await load();
    } catch (err: any) {
      setActionError(err.response?.data?.detail ?? `结束会话失败: ${err.message ?? '未知错误'}`);
    } finally {
      setSessionBusy(false);
    }
  };

  const handleReplay = async () => {
    setSessionBusy(true);
    setActionMessage(null);
    setActionError(null);
    try {
      const result = await deviceGateway.replaySimulated(deviceId, 4);
      setActionMessage(
        `模拟回放完成（数据已标记 simulated，非真实采集）：入库 ${result.accepted_count}，重复 ${result.duplicate_count}，拒绝 ${result.rejected_count}`,
      );
      await load();
    } catch (err: any) {
      setActionError(err.response?.data?.detail ?? `模拟回放失败: ${err.message ?? '未知错误'}`);
    } finally {
      setSessionBusy(false);
    }
  };

  const activeSession = sessions.find((s) => s.status === 'active');

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        自动采集详情 — {deviceName}
        <Typography variant="caption" color="text.secondary" sx={{ ml: 2 }}>
          协议适配器: {adapterId ?? '未登记（该型号未接入协议适配器）'}
        </Typography>
      </DialogTitle>
      <DialogContent>
        {loading && (
          <Box display="flex" justifyContent="center" py={4}>
            <CircularProgress />
          </Box>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
            <Button size="small" onClick={load} sx={{ ml: 2 }}>
              重试
            </Button>
          </Alert>
        )}
        {!loading && !error && (
          <Stack spacing={3}>
            {actionMessage && <Alert severity="success">{actionMessage}</Alert>}
            {actionError && <Alert severity="error">{actionError}</Alert>}

            {/* 质量报告摘要 */}
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle1" gutterBottom>
                数据质量报告（自动采集）
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" color="text.secondary">自动采集总数</Typography>
                  <Typography variant="h6">{report?.total_automated ?? '—'}</Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" color="text.secondary">合格率</Typography>
                  <Typography variant="h6">
                    {report?.pass_rate !== null && report?.pass_rate !== undefined
                      ? `${(report.pass_rate * 100).toFixed(1)}%`
                      : '—'}
                  </Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" color="text.secondary">质量标记条数</Typography>
                  <Typography variant="h6">{report?.flagged ?? '—'}</Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" color="text.secondary">超范围条数</Typography>
                  <Typography variant="h6">{report?.out_of_range_count ?? '—'}</Typography>
                </Grid>
              </Grid>
            </Paper>

            {/* 时序简图 + 指标选择 */}
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                <Typography variant="subtitle1">
                  自动采集趋势{selectedType ? ` — ${selectedType}` : ''}
                </Typography>
                {dataTypes.length > 0 && (
                  <ToggleButtonGroup
                    size="small"
                    exclusive
                    value={selectedType}
                    onChange={(_, v) => v && setSelectedType(v)}
                  >
                    {dataTypes.map((type) => (
                      <ToggleButton key={type} value={type}>
                        {type}
                      </ToggleButton>
                    ))}
                  </ToggleButtonGroup>
                )}
              </Box>
              <Sparkline points={chartPoints} color="#1976d2" />
            </Paper>

            {/* 会话管理 */}
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle1" gutterBottom>
                采集会话
              </Typography>
              <Stack direction="row" spacing={2} alignItems="flex-end" flexWrap="wrap" useFlexGap>
                <TextField
                  select
                  size="small"
                  label="关联已发布运动方案（可选）"
                  value={planId}
                  onChange={(e) => {
                    const selected = publicationOptions.find(option => option.plan_id === e.target.value);
                    setPlanId(selected?.plan_id ?? '');
                    setVersionId(selected?.version_id ?? '');
                    setPrescriptionItemId('');
                  }}
                  sx={{ width: 260 }}
                >
                  <MenuItem value="">不关联方案</MenuItem>
                  {publicationOptions.map(option => <MenuItem key={option.plan_id} value={option.plan_id}>
                    {option.plan_name}
                  </MenuItem>)}
                </TextField>
                <TextField
                  select
                  size="small"
                  label="已发布运动处方项"
                  value={prescriptionItemId}
                  disabled={!planId}
                  onChange={(e) => setPrescriptionItemId(e.target.value)}
                  sx={{ width: 260 }}
                >
                  <MenuItem value="">请选择运动项</MenuItem>
                  {(publicationOptions.find(option => option.plan_id === planId)?.items ?? []).map(item => <MenuItem key={item.item_id} value={item.item_id}>
                    {item.name}
                  </MenuItem>)}
                </TextField>
                <Button
                  variant="contained"
                  disabled={sessionBusy || !!activeSession || (!!planId && (!versionId || !prescriptionItemId))}
                  onClick={handleStartSession}
                >
                  开始采集会话
                </Button>
                <Button
                  variant="outlined"
                  disabled={sessionBusy}
                  onClick={handleReplay}
                  title="演示数据：回放读数全部标记 simulated，不冒充真实采集"
                >
                  模拟数据回放（演示）
                </Button>
              </Stack>
              <Typography variant="caption" color="text.secondary">
                可选方案和运动项由该设备绑定患者当前发布内容自动加载；采集数据仍作为设备观测保存，不登记为训练完成。
              </Typography>
              {activeSession && (
                <Alert severity="info" sx={{ mt: 2 }}>
                  进行中会话 {activeSession._id}（方案关联：
                  {activeSession.linkage_status === 'linked'
                    ? '已打通'
                    : activeSession.linkage_status === 'registered'
                      ? '登记待人工关联'
                      : '无'}
                  {activeSession.linkage_error ? `，${activeSession.linkage_error}` : ''}）
                  <Button size="small" onClick={() => handleEndSession(activeSession._id, false)} sx={{ ml: 1 }}>
                    结束
                  </Button>
                  <Button size="small" onClick={() => handleEndSession(activeSession._id, true)} sx={{ ml: 1 }}>
                    取消
                  </Button>
                </Alert>
              )}
              <TableContainer sx={{ mt: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>开始时间</TableCell>
                      <TableCell>状态</TableCell>
                      <TableCell>方案关联</TableCell>
                      <TableCell>摘要</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sessions.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4}>暂无采集会话</TableCell>
                      </TableRow>
                    ) : (
                      sessions.map((session) => (
                        <TableRow key={session._id}>
                          <TableCell>{formatDate(session.started_at)}</TableCell>
                          <TableCell>
                            {session.status === 'active' ? '进行中' : session.status === 'ended' ? '已结束' : '已取消'}
                          </TableCell>
                          <TableCell>
                            {session.linkage_status === 'linked'
                              ? `已关联（${session.plan_id ?? ''} / ${session.prescription_item_id ?? ''}）`
                              : session.linkage_status === 'registered'
                                ? '登记待人工关联'
                                : '无'}
                          </TableCell>
                          <TableCell>
                            {session.summary?.readings_count !== undefined
                              ? `读数 ${session.summary.readings_count} / 标记 ${session.summary.flagged_count ?? 0}`
                              : '—'}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>

            {/* 自动采集读数时序列表（表格视图 + 质量标记） */}
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle1" gutterBottom>
                自动采集数据（最近 50 条，表格为数值权威视图）
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>时间戳</TableCell>
                      <TableCell>指标</TableCell>
                      <TableCell>数值</TableCell>
                      <TableCell>单位</TableCell>
                      <TableCell>来源</TableCell>
                      <TableCell>质量标记</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {readings.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6}>
                          暂无自动采集数据（设备侧尚未通过网关上报；演示可用「模拟数据回放」）
                        </TableCell>
                      </TableRow>
                    ) : (
                      readings.map((reading, index) => (
                        <TableRow key={reading.id ?? `${reading.timestamp}-${reading.data_type}-${index}`}>
                          <TableCell>{formatDate(reading.timestamp)}</TableCell>
                          <TableCell>{reading.data_type}</TableCell>
                          <TableCell>{String(reading.value)}</TableCell>
                          <TableCell>{reading.unit || '—'}</TableCell>
                          <TableCell>
                            {reading.metadata?.source === 'automated_simulated_replay' ? '模拟回放' : '自动采集'}
                          </TableCell>
                          <TableCell>
                            {reading.quality_flags && reading.quality_flags.length > 0 ? (
                              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                {reading.quality_flags.map((flag) => (
                                  <Chip key={flag} label={flagLabel(flag)} size="small" color="warning" variant="outlined" />
                                ))}
                              </Stack>
                            ) : (
                              '—'
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>

            {/* 协议假设核实清单 */}
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle1" gutterBottom>
                协议假设核实清单（待厂商文档核实）
              </Typography>
              {assumptionNote && (
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {assumptionNote}
                </Typography>
              )}
              {assumptions.length === 0 && !assumptionNote && (
                <Typography variant="body2" color="text.secondary">无登记的协议假设</Typography>
              )}
              {assumptions.map((assumption, index) => (
                <Box key={index} mb={1.5}>
                  <Typography variant="body2">
                    {index + 1}. {assumption.claim}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    核实方式：{assumption.verify}
                    {assumption.impact ? ` ｜ 影响：${assumption.impact}` : ''}
                  </Typography>
                  <Divider sx={{ mt: 1 }} />
                </Box>
              ))}
            </Paper>
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default DeviceIngestionPanel;
