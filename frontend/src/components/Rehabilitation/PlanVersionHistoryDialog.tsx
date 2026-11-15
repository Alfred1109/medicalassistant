import { formatAppDate } from '../../utils/dateTime';
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
  Divider,
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
  PlanVersionDetail,
  PlanVersionSummary,
  PrescriptionItem,
  PrescriptionItemDiff,
  SnapshotFieldDiff,
  diffPrescriptionItems,
  diffSnapshotFields,
  planVersionService,
} from '../../services/planVersionHistory';

// T77 方案版本历史：医护端消费 GET /rehabilitation/plans/{plan_id}/versions[-/{id}]
// 与 /items?version_id=...（对象级授权与方案详情一致，由后端裁决）。
// 展示形态：版本列表（version_no/时间/变更摘要）→ 选中版本与基准版本的
// 快照字段差异 + 处方项差异（item_id 跨版本稳定，可跨版本对比）。

const FIELD_LABELS: Record<string, string> = {
  name: '方案名称',
  description: '方案说明',
  goal: '康复目标',
  condition: '病情/状况',
  frequency: '总体安排',
  start_date: '开始时间',
  end_date: '结束时间',
  notes: '备注',
};

const SNAPSHOT_FIELDS = Object.keys(FIELD_LABELS);

const dateText = (value?: string | null) => {
  return formatAppDate(value, 'localeZh24', { empty: '—', invalid: String(value) });
};

const itemName = (item?: PrescriptionItem) =>
  (item?.name && String(item.name)) || '未命名干预';

const interventionLabel = (type?: string) => {
  const labels: Record<string, string> = {
    medication: '用药', diet: '膳食', psychology: '心理', exercise: '运动训练',
  };
  return (type && labels[type]) || type || '未标注';
};

function SnapshotDiffTable({ diffs }: { diffs: SnapshotFieldDiff[] }) {
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>字段</TableCell>
            <TableCell>基准版本</TableCell>
            <TableCell>选中版本</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {diffs.map((diff) => (
            <TableRow key={diff.field} selected={diff.changed}>
              <TableCell>{FIELD_LABELS[diff.field] || diff.field}</TableCell>
              <TableCell sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{diff.baseValue}</TableCell>
              <TableCell sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                {diff.changed ? <strong>{diff.targetValue}</strong> : diff.targetValue}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function ItemDiffSection({ planId, baseVersion, targetVersion }: {
  planId: string;
  baseVersion: PlanVersionSummary | null;
  targetVersion: PlanVersionSummary;
}) {
  const [diff, setDiff] = useState<PrescriptionItemDiff | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setDiff(null);
    Promise.all([
      planVersionService.listItems(planId, baseVersion?._id, 500),
      planVersionService.listItems(planId, targetVersion._id, 500),
    ]).then(([baseItems, targetItems]) => {
      if (controller.signal.aborted) return;
      setDiff(diffPrescriptionItems(baseItems, targetItems));
    }).catch(() => {
      if (!controller.signal.aborted) setError('处方项读取失败，请重试。');
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [planId, baseVersion?._id, targetVersion._id]);

  const changedCount = diff ? diff.added.length + diff.removed.length + diff.changed.length : 0;
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">处方项差异（item_id 跨版本稳定）</Typography>
      {loading && <CircularProgress size={22} aria-label="正在对比处方项" />}
      {error && <Alert severity="error">{error}</Alert>}
      {diff && !loading && !error && (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip size="small" color="success" label={`新增 ${diff.added.length}`} />
          <Chip size="small" color="error" label={`移除 ${diff.removed.length}`} />
          <Chip size="small" color="warning" label={`变更 ${diff.changed.length}`} />
          <Chip size="small" label={`未变 ${diff.unchangedCount}`} />
          {changedCount === 0 && <Typography variant="body2" color="text.secondary">两个版本的处方项完全一致。</Typography>}
        </Stack>
      )}
      {diff && diff.added.length > 0 && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>选中版本新增：</Typography>
          {diff.added.map((entry) => (
            <Typography key={entry.item_id} variant="body2" color="text.primary">
              · {itemName(entry.target)}（{interventionLabel(entry.target?.intervention_type)} · item_id {entry.item_id}）
            </Typography>
          ))}
        </Paper>
      )}
      {diff && diff.removed.length > 0 && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>选中版本移除（基准版本仍存在）：</Typography>
          {diff.removed.map((entry) => (
            <Typography key={entry.item_id} variant="body2" color="text.secondary">
              · {itemName(entry.base)}（{interventionLabel(entry.base?.intervention_type)} · item_id {entry.item_id}）
            </Typography>
          ))}
        </Paper>
      )}
      {diff && diff.changed.length > 0 && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>内容有变更：</Typography>
          {diff.changed.map((entry) => (
            <Typography key={entry.item_id} variant="body2">
              · {itemName(entry.target)}（item_id {entry.item_id}）：
              「{itemName(entry.base)} / {interventionLabel(entry.base?.intervention_type)}」→
              「{itemName(entry.target)} / {interventionLabel(entry.target?.intervention_type)}」
            </Typography>
          ))}
        </Paper>
      )}
    </Stack>
  );
}

const PlanVersionHistoryDialog: React.FC<{ planId: string; open: boolean; onClose: () => void }> = ({
  planId,
  open,
  onClose,
}) => {
  const [versions, setVersions] = useState<PlanVersionDetail[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [baseId, setBaseId] = useState('');
  const [detail, setDetail] = useState<PlanVersionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  // 版本列表（打开或手动刷新时拉取；后端按 version_no 倒序返回）
  useEffect(() => {
    if (!open || !planId) return;
    const controller = new AbortController();
    setVersions([]); setSelectedId(''); setBaseId(''); setDetail(null);
    setListLoading(true); setListError('');
    planVersionService.listVersions(planId).then((rows) => {
      if (controller.signal.aborted) return;
      setVersions(rows);
      // 默认选中最新版本（列表首位），基准默认为更早的最近版本
      if (rows.length > 0) setSelectedId(rows[0]._id);
      if (rows.length > 1) setBaseId(rows[1]._id);
    }).catch(() => {
      if (!controller.signal.aborted) setListError('版本列表读取失败，请重试。');
    }).finally(() => {
      if (!controller.signal.aborted) setListLoading(false);
    });
    return () => controller.abort();
  }, [open, planId, reloadKey]);

  // 选中版本详情（含快照）
  useEffect(() => {
    if (!open || !planId || !selectedId) return;
    const controller = new AbortController();
    setDetail(null); setDetailLoading(true); setDetailError('');
    planVersionService.getVersion(planId, selectedId).then((data) => {
      if (!controller.signal.aborted && data && data._id === selectedId) setDetail(data);
    }).catch(() => {
      if (!controller.signal.aborted) setDetailError('版本详情读取失败，请重试。');
    }).finally(() => {
      if (!controller.signal.aborted) setDetailLoading(false);
    });
    return () => controller.abort();
  }, [open, planId, selectedId]);

  const selected = versions.find((row) => row._id === selectedId) || null;
  const base = versions.find((row) => row._id === baseId) || null;

  const snapshotDiffs = useMemo(
    () => diffSnapshotFields(base?.snapshot as Record<string, unknown> | undefined,
      detail?.snapshot as Record<string, unknown> | undefined, SNAPSHOT_FIELDS),
    [base?._id, detail?._id, base?.snapshot, detail?.snapshot], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <Dialog open={open} fullWidth maxWidth="md" onClose={onClose}>
      <DialogTitle>方案版本历史</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {listLoading && <CircularProgress size={24} aria-label="正在加载版本列表" />}
          {listError && (
            <Alert severity="error" action={<Button onClick={() => setReloadKey(key => key + 1)}>重试</Button>}>
              {listError}
            </Alert>
          )}
          {!listLoading && !listError && versions.length === 0 && (
            <Alert severity="info">该方案还没有版本快照。在工作台保存或发布方案时会形成版本记录。</Alert>
          )}
          {versions.length > 0 && (
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>版本号</TableCell>
                    <TableCell>创建时间</TableCell>
                    <TableCell>变更摘要</TableCell>
                    <TableCell>状态</TableCell>
                    <TableCell>查看</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {versions.map((row) => (
                    <TableRow key={row._id} selected={row._id === selectedId}>
                      <TableCell>第 {row.version_no} 版</TableCell>
                      <TableCell>{dateText(row.created_at)}</TableCell>
                      <TableCell sx={{ maxWidth: 320, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                        {row.note || '（未填写变更摘要）'}
                      </TableCell>
                      <TableCell>{row.status || '—'}</TableCell>
                      <TableCell>
                        <Button size="small" onClick={() => setSelectedId(row._id)}>查看详情</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          {detailLoading && <CircularProgress size={24} aria-label="正在加载版本详情" />}
          {detailError && <Alert severity="error">{detailError}</Alert>}

          {selected && !detailLoading && !detailError && (
            <Stack spacing={2}>
              <Divider />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  select size="small" label="对比基准版本" sx={{ minWidth: 240 }}
                  value={baseId}
                  onChange={(event) => setBaseId(event.target.value)}
                  helperText="与选中版本做快照和处方项差异对比"
                >
                  <MenuItem value="" disabled>请选择基准版本</MenuItem>
                  {versions.filter((row) => row._id !== selectedId).map((row) => (
                    <MenuItem key={row._id} value={row._id}>第 {row.version_no} 版（{dateText(row.created_at)}）</MenuItem>
                  ))}
                </TextField>
                {versions.length < 2 && (
                  <Typography variant="body2" color="text.secondary" alignSelf="center">
                    仅有一个版本时无法对比，选择版本可查看快照内容。
                  </Typography>
                )}
              </Stack>

              {base && (
                <Stack spacing={1}>
                  <Typography variant="subtitle2">
                    内容快照对比：基准「第 {base.version_no} 版」→ 选中「第 {selected.version_no} 版」
                  </Typography>
                  <SnapshotDiffTable diffs={snapshotDiffs} />
                </Stack>
              )}

              {base && (
                <ItemDiffSection planId={planId} baseVersion={base} targetVersion={selected} />
              )}

              {detail?.snapshot && !base && (
                <Paper variant="outlined" sx={{ p: 1.5 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>选中版本快照内容</Typography>
                  {diffSnapshotFields(null, detail.snapshot as Record<string, unknown>, SNAPSHOT_FIELDS).map((row) => (
                    <Typography key={row.field} variant="body2">
                      {FIELD_LABELS[row.field] || row.field}：{row.targetValue}
                    </Typography>
                  ))}
                </Paper>
              )}

              <Typography variant="caption" color="text.secondary">
                版本由系统在保存/发布时对方案内容做白名单快照；本页为只读历史，修改请在方案工作台进行。
              </Typography>
            </Stack>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button
          disabled={listLoading || !!listError}
          onClick={() => setReloadKey(key => key + 1)}
        >
          刷新列表
        </Button>
        <Button onClick={onClose}>关闭</Button>
      </DialogActions>
    </Dialog>
  );
};

export default PlanVersionHistoryDialog;
