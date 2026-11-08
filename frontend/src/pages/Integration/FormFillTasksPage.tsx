/**
 * 集成填报任务列表页（医护侧，EMB02 雏形）。
 *
 * 职责：
 * - 展示当前用户发起的嵌入填报任务（admin 可见全部），支持状态过滤与刷新；
 * - 打开嵌入页（仅 session_created / waiting_fill 可打开）；
 * - 手动确认（向远端核实提交状态）与取消任务；
 * - 任务创建暂通过后端 API（试点阶段）；正式创建入口依赖患者/受试者
 *   映射（DATA01）就绪后另行设计，这里不做模拟创建。
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  MenuItem,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';

import { RootState } from '../../store';
import {
  formIntegrationService,
  FillTask,
  FillTaskListPage,
} from '../../services/formIntegrationService';

const STATUS_LABELS: Record<string, string> = {
  session_created: '会话已创建',
  waiting_fill: '等待填写',
  submitted: '已提交',
  confirmed: '待审阅（已核实）',
  cancelled: '已取消',
  failed: '失败',
};

const STATUS_COLORS: Record<string, 'default' | 'primary' | 'info' | 'warning' | 'success' | 'error'> = {
  session_created: 'default',
  waiting_fill: 'info',
  submitted: 'warning',
  confirmed: 'success',
  cancelled: 'default',
  failed: 'error',
};

const STATUS_OPTIONS = Object.keys(STATUS_LABELS);

const FormFillTasksPage: React.FC = () => {
  const navigate = useNavigate();
  const user = useSelector((state: RootState) => state.auth.user);
  const [tasks, setTasks] = useState<FillTask[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState<FillTaskListPage>({ status: '', page: 0, pageSize: 20 });
  const queryRef = useRef(query);
  const requestId = useRef(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);

  const rolePrefix = user?.role === 'health_manager' ? 'health-manager' : 'doctor';

  const load = useCallback(async (nextQuery: FillTaskListPage) => {
    const currentRequest = ++requestId.current;
    queryRef.current = nextQuery;
    setQuery(nextQuery);
    setLoading(true);
    setError(null);
    setTasks([]);
    try {
      const result = await formIntegrationService.listFillTaskPage(nextQuery);
      if (currentRequest !== requestId.current) return;
      setTasks(result.items);
      setTotal(result.total);
      const currentQuery = { ...nextQuery, page: result.page };
      queryRef.current = currentQuery;
      setQuery(currentQuery);
    } catch (err) {
      if (currentRequest !== requestId.current) return;
      setError(err instanceof Error && err.message ? err.message : '加载填报任务列表失败');
    } finally {
      if (currentRequest === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(queryRef.current);
    return () => { requestId.current += 1; };
  }, [load]);

  const handleOpen = (task: FillTask) => {
    navigate(`/app/${rolePrefix}/form-fill/${task.id}`);
  };

  const handleConfirm = async (task: FillTask) => {
    setBusyTaskId(task.id);
    setError(null);
    try {
      await formIntegrationService.confirmFillTask(task.id);
      await load(queryRef.current);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : '确认失败：远端状态核验未通过');
    } finally {
      setBusyTaskId(null);
    }
  };

  const handleCancel = async (task: FillTask) => {
    if (!window.confirm('确认取消该填报任务？远端会话将一并作废。')) return;
    setBusyTaskId(task.id);
    setError(null);
    try {
      await formIntegrationService.cancelFillTask(task.id);
      await load(queryRef.current);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : '取消失败');
    } finally {
      setBusyTaskId(null);
    }
  };

  const canOpen = (task: FillTask) =>
    task.status === 'session_created' || task.status === 'waiting_fill';

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h5">表单填报任务（113.44 嵌入）</Typography>
        <Button variant="outlined" onClick={() => void load(queryRef.current)} disabled={loading || busyTaskId !== null}>
          刷新
        </Button>
      </Box>

      <Box display="flex" gap={2} mb={2} alignItems="center">
        <TextField
          select
          label="状态过滤"
          size="small"
          sx={{ width: 200 }}
          value={query.status}
          disabled={busyTaskId !== null}
          onChange={(e) => void load({ ...queryRef.current, status: e.target.value, page: 0 })}
        >
          <MenuItem value="">全部</MenuItem>
          {STATUS_OPTIONS.map((status) => (
            <MenuItem key={status} value={status}>
              {STATUS_LABELS[status]}
            </MenuItem>
          ))}
        </TextField>
        <Typography variant="body2" color="text.secondary">
          共 {total} 条任务
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box display="flex" justifyContent="center" py={6}>
          <CircularProgress />
        </Box>
      ) : (
        <TableContainer component={Paper} aria-busy={loading}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>任务标识</TableCell>
                <TableCell>患者</TableCell>
                <TableCell>访视</TableCell>
                <TableCell>远端引用（项目/中心/受试者/表单）</TableCell>
                <TableCell>状态</TableCell>
                <TableCell>创建时间</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tasks.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <Typography variant="body2" color="text.secondary" py={2}>
                      {error ? '任务加载失败，请重试。' : '暂无填报任务。任务创建暂通过后端 API 发起（试点阶段）。'}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {tasks.map((task) => (
                <TableRow key={task.id} hover>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {task.id}
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {task.patientId}
                  </TableCell>
                  <TableCell>{task.visitCode ?? '—'}</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {task.remoteRefs.project_id} / {task.remoteRefs.center_id} /{' '}
                    {task.remoteRefs.subject_id} / {task.remoteRefs.questionnaire_id}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={STATUS_LABELS[task.status] ?? task.status}
                      color={STATUS_COLORS[task.status] ?? 'default'}
                    />
                  </TableCell>
                  <TableCell>{task.createdAt ?? '—'}</TableCell>
                  <TableCell align="right">
                    <Box display="flex" gap={1} justifyContent="flex-end">
                      {canOpen(task) && (
                        <Button
                          size="small"
                          variant="contained"
                          onClick={() => handleOpen(task)}
                        >
                          打开填报
                        </Button>
                      )}
                      {(task.status === 'submitted' || task.status === 'waiting_fill') && (
                        <Button
                          size="small"
                          onClick={() => void handleConfirm(task)}
                          disabled={busyTaskId === task.id}
                        >
                          确认提交
                        </Button>
                      )}
                      {(task.status === 'session_created' ||
                        task.status === 'waiting_fill') && (
                        <Button
                          size="small"
                          color="error"
                          onClick={() => void handleCancel(task)}
                          disabled={busyTaskId === task.id}
                        >
                          取消
                        </Button>
                      )}
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <TablePagination
        component="div"
        count={total}
        page={loading ? Math.min(query.page, Math.max(0, Math.ceil(total / query.pageSize) - 1)) : query.page}
        rowsPerPage={query.pageSize}
        rowsPerPageOptions={[10, 20, 50, 100]}
        labelRowsPerPage="每页任务数"
        labelDisplayedRows={({ from, to, count }) => `${from}–${to}，共 ${count} 条`}
        getItemAriaLabel={(type) => type === 'next' ? '下一页' : type === 'previous' ? '上一页' : type === 'first' ? '第一页' : '最后一页'}
        backIconButtonProps={{ disabled: loading || busyTaskId !== null || query.page === 0 }}
        nextIconButtonProps={{ disabled: loading || busyTaskId !== null || (query.page + 1) * query.pageSize >= total }}
        SelectProps={{ disabled: loading || busyTaskId !== null }}
        onPageChange={(_, page) => void load({ ...queryRef.current, page })}
        onRowsPerPageChange={(event) => void load({ ...queryRef.current, pageSize: Number(event.target.value), page: 0 })}
      />

      <Typography sx={{ mt: 2 }} variant="caption" color="text.secondary">
        嵌入链接为一次性令牌：关闭或过期后需重新创建任务；“待审阅（已核实）”表示后端已向
        113.44 核实答卷真实提交。
      </Typography>
    </Box>
  );
};

export default FormFillTasksPage;
