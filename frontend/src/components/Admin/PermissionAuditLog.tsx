import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Chip,
  IconButton,
  Tooltip,
  Card,
  CardContent,
  Grid,
  TextField,
  MenuItem,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress,
  Stack,
  Badge
} from '@mui/material';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import {
  Visibility as VisibilityIcon,
  FilterList as FilterIcon,
  Refresh as RefreshIcon,
  Info as InfoIcon,
  Person as PersonIcon,
  Clear as ClearIcon,
  VerifiedUser as VerifiedUserIcon
} from '@mui/icons-material';
import { format, parseISO } from 'date-fns';
import zhCN from 'date-fns/locale/zh-CN';
import ReactJson from 'react-json-view';

import { AuditService } from '../../services/audit-service';
import { AuditLog, AuditLogFilter } from '../../types/audit';

// 权限操作类型映射颜色
const actionColors = {
  grant: 'success',
  revoke: 'error',
  access: 'info',
  query: 'secondary',
  view: 'primary',
  assign: 'warning',
  remove: 'default'
};

/**
 * 权限审计日志组件
 * 专注于显示与权限相关的审计日志记录
 */
const PermissionAuditLog: React.FC = () => {
  // 状态管理
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  
  // 过滤器设置 - 默认只显示权限相关记录
  const [filter, setFilter] = useState<AuditLogFilter>({
    resource_type: 'permission'
  });
  
  // 临时过滤器状态
  const [tempFilter, setTempFilter] = useState<AuditLogFilter>({
    resource_type: 'permission'
  });
  
  // 加载审计日志
  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await AuditService.getAuditLogs(
        filter,
        page,
        rowsPerPage,
        'created_at',
        -1
      );
      setLogs(result.items);
      setTotal(result.total);
    } catch (error) {
      console.error('加载权限审计日志失败:', error);
    } finally {
      setLoading(false);
    }
  }, [filter, page, rowsPerPage]);
  
  // 初始加载
  useEffect(() => {
    loadLogs();
  }, [loadLogs]);
  
  // 查看日志详情
  const handleViewDetails = async (logId: string) => {
    try {
      const log = await AuditService.getAuditLogById(logId);
      setSelectedLog(log);
      setDetailsDialogOpen(true);
    } catch (error) {
      console.error('获取日志详情失败:', error);
    }
  };
  
  // 处理分页变化
  const handleChangePage = (event: unknown, newPage: number) => {
    setPage(newPage);
  };
  
  // 处理每页记录数变化
  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };
  
  // 刷新数据
  const handleRefresh = () => {
    loadLogs();
  };
  
  // 打开过滤器对话框
  const handleOpenFilterDialog = () => {
    setTempFilter({ ...filter });
    setFilterDialogOpen(true);
  };
  
  // 应用过滤器
  const handleApplyFilter = () => {
    setFilter({ ...tempFilter });
    setPage(0);
    setFilterDialogOpen(false);
  };
  
  // 清除过滤器（除了resource_type保持为permission）
  const handleClearFilter = () => {
    setTempFilter({ resource_type: 'permission' });
  };
  
  // 获取用户名称的辅助函数（实际应用中可能需要从API获取）
  const getUserName = (userId: string) => {
    return userId; // 简化示例，实际应用中应查询用户名
  };
  
  // 格式化权限名称显示
  const formatPermissionName = (permission: string) => {
    if (!permission) return '-';
    
    // 将permission:action格式的权限名称转换为更友好的显示
    const parts = permission.split(':');
    if (parts.length === 2) {
      return `${parts[0]} (${parts[1]})`;
    }
    return permission;
  };
  
  // 渲染表格
  const renderTable = () => (
    <TableContainer component={Paper} sx={{ mt: 2 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>时间</TableCell>
            <TableCell>操作者</TableCell>
            <TableCell>操作</TableCell>
            <TableCell>权限</TableCell>
            <TableCell>目标用户</TableCell>
            <TableCell>角色</TableCell>
            <TableCell>操作</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={7} align="center">
                <CircularProgress size={24} />
                <Typography variant="body2" sx={{ ml: 2 }}>
                  加载中...
                </Typography>
              </TableCell>
            </TableRow>
          ) : logs.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} align="center">
                <Typography variant="body2">
                  暂无权限操作记录
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            logs.map((log) => (
              <TableRow key={log.id} hover>
                <TableCell>
                  {format(parseISO(log.created_at), 'yyyy-MM-dd HH:mm:ss')}
                </TableCell>
                <TableCell>{getUserName(log.user_id)}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={log.action}
                    color={actionColors[log.action as keyof typeof actionColors] || 'default'}
                  />
                </TableCell>
                <TableCell>
                  {formatPermissionName(log.details?.permission || '-')}
                </TableCell>
                <TableCell>{getUserName(log.details?.target_user_id || '-')}</TableCell>
                <TableCell>{log.details?.role || '-'}</TableCell>
                <TableCell>
                  <Tooltip title="查看详情">
                    <IconButton size="small" onClick={() => handleViewDetails(log.id)}>
                      <VisibilityIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      <TablePagination
        rowsPerPageOptions={[10, 25, 50, 100]}
        component="div"
        count={total}
        rowsPerPage={rowsPerPage}
        page={page}
        onPageChange={handleChangePage}
        onRowsPerPageChange={handleChangeRowsPerPage}
        labelRowsPerPage="每页行数:"
        labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count !== -1 ? count : '?'}`}
      />
    </TableContainer>
  );
  
  // 渲染工具栏
  const renderToolbar = () => (
    <Box sx={{ mb: 2 }}>
      <Card>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={6}>
              <Typography variant="h6" component="h2">
                <VerifiedUserIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                权限操作审计日志
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Stack direction="row" spacing={1} justifyContent={{ xs: 'flex-start', md: 'flex-end' }}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<FilterIcon />}
                  onClick={handleOpenFilterDialog}
                >
                  过滤
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<RefreshIcon />}
                  onClick={handleRefresh}
                >
                  刷新
                </Button>
              </Stack>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
    </Box>
  );
  
  // 渲染过滤器对话框
  const renderFilterDialog = () => (
    <Dialog open={filterDialogOpen} onClose={() => setFilterDialogOpen(false)} maxWidth="md">
      <DialogTitle>
        <Box display="flex" alignItems="center">
          <FilterIcon sx={{ mr: 1 }} />
          过滤权限审计日志
        </Box>
      </DialogTitle>
      <DialogContent dividers>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="操作者ID"
              value={tempFilter.user_id || ''}
              onChange={(e) => setTempFilter({ ...tempFilter, user_id: e.target.value })}
              variant="outlined"
              size="small"
              margin="normal"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="操作类型"
              select
              value={tempFilter.action || ''}
              onChange={(e) => setTempFilter({ ...tempFilter, action: e.target.value })}
              variant="outlined"
              size="small"
              margin="normal"
            >
              <MenuItem value="">全部操作</MenuItem>
              <MenuItem value="grant">授予权限</MenuItem>
              <MenuItem value="revoke">撤销权限</MenuItem>
              <MenuItem value="access">权限检查</MenuItem>
              <MenuItem value="assign">分配角色</MenuItem>
              <MenuItem value="remove">移除角色</MenuItem>
            </TextField>
          </Grid>
          <Grid item xs={12} md={12}>
            <TextField
              fullWidth
              label="目标用户ID"
              value={tempFilter.resource_id || ''}
              onChange={(e) => setTempFilter({ ...tempFilter, resource_id: e.target.value })}
              variant="outlined"
              size="small"
              margin="normal"
              helperText="权限变更影响的用户ID"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
              <DatePicker
                label="开始日期"
                value={tempFilter.start_date ? new Date(tempFilter.start_date) : null}
                onChange={(date) => setTempFilter({
                  ...tempFilter,
                  start_date: date ? date.toISOString() : undefined
                })}
                slotProps={{
                  textField: {
                    fullWidth: true,
                    size: "small",
                    margin: "normal"
                  }
                }}
              />
            </LocalizationProvider>
          </Grid>
          <Grid item xs={12} md={6}>
            <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
              <DatePicker
                label="结束日期"
                value={tempFilter.end_date ? new Date(tempFilter.end_date) : null}
                onChange={(date) => setTempFilter({
                  ...tempFilter,
                  end_date: date ? date.toISOString() : undefined
                })}
                slotProps={{
                  textField: {
                    fullWidth: true,
                    size: "small",
                    margin: "normal"
                  }
                }}
              />
            </LocalizationProvider>
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClearFilter} startIcon={<ClearIcon />}>
          清除
        </Button>
        <Button onClick={() => setFilterDialogOpen(false)}>
          取消
        </Button>
        <Button onClick={handleApplyFilter} variant="contained" color="primary">
          应用
        </Button>
      </DialogActions>
    </Dialog>
  );
  
  // 渲染详情对话框
  const renderDetailsDialog = () => (
    <Dialog
      open={detailsDialogOpen}
      onClose={() => setDetailsDialogOpen(false)}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>
        <Box display="flex" alignItems="center">
          <InfoIcon sx={{ mr: 1 }} />
          审计日志详情
        </Box>
      </DialogTitle>
      <DialogContent dividers>
        {selectedLog && (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2">操作时间</Typography>
              <Typography variant="body2">
                {format(parseISO(selectedLog.created_at), 'yyyy-MM-dd HH:mm:ss')}
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2">操作者</Typography>
              <Typography variant="body2">
                <Stack direction="row" alignItems="center" spacing={1}>
                  <PersonIcon fontSize="small" />
                  {getUserName(selectedLog.user_id)}
                </Stack>
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2">操作类型</Typography>
              <Typography variant="body2">
                <Chip
                  size="small"
                  label={selectedLog.action}
                  color={actionColors[selectedLog.action as keyof typeof actionColors] || 'default'}
                />
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2">资源类型</Typography>
              <Typography variant="body2">{selectedLog.resource_type}</Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2">资源ID</Typography>
              <Typography variant="body2">{selectedLog.resource_id || '-'}</Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2">IP地址</Typography>
              <Typography variant="body2">{selectedLog.ip_address || '-'}</Typography>
            </Grid>
            <Grid item xs={12}>
              <Typography variant="subtitle2">详细信息</Typography>
              <Paper sx={{ p: 2, mt: 1, maxHeight: '300px', overflow: 'auto' }}>
                {selectedLog.details ? (
                  <ReactJson
                    src={selectedLog.details}
                    name={false}
                    displayDataTypes={false}
                    displayObjectSize={false}
                    enableClipboard={false}
                    style={{ backgroundColor: 'transparent' }}
                  />
                ) : (
                  <Typography variant="body2">无详细信息</Typography>
                )}
              </Paper>
            </Grid>
          </Grid>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setDetailsDialogOpen(false)}>
          关闭
        </Button>
      </DialogActions>
    </Dialog>
  );
  
  return (
    <Box>
      {renderToolbar()}
      {renderTable()}
      {renderFilterDialog()}
      {renderDetailsDialog()}
    </Box>
  );
};

export default PermissionAuditLog; 