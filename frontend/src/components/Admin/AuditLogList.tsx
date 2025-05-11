import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Table, 
  TableBody, 
  TableCell, 
  TableContainer, 
  TableHead, 
  TableRow, 
  TablePagination,
  Paper, 
  Typography, 
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
  CircularProgress
} from '@mui/material';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import {
  Visibility as VisibilityIcon,
  FilterList as FilterIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  Clear as ClearIcon
} from '@mui/icons-material';
import { format, parseISO } from 'date-fns';
import zhCN from 'date-fns/locale/zh-CN';

import { AuditService } from '../../services/audit-service';
import { AuditLog, AuditLogFilter, AuditAction, AuditResourceType } from '../../types/audit';

// 状态类型颜色映射
const statusColors = {
  success: 'success',
  failure: 'error'
};

// 操作类型颜色映射
const actionColors: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'> = {
  access: 'info',
  login: 'success',
  logout: 'default',
  create: 'primary',
  update: 'warning',
  delete: 'error',
  grant: 'success',
  revoke: 'error',
  query: 'info',
  view: 'info',
  modify: 'warning'
};

/**
 * 审计日志列表组件
 */
const AuditLogList: React.FC = () => {
  // 状态管理
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [filter, setFilter] = useState<AuditLogFilter>({});
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
  
  // 临时过滤器状态（用于对话框）
  const [tempFilter, setTempFilter] = useState<AuditLogFilter>({});
  
  // 加载审计日志
  const loadAuditLogs = async () => {
    setLoading(true);
    try {
      const result = await AuditService.getAuditLogs(
        filter, 
        page,
        rowsPerPage
      );
      setLogs(result.items);
      setTotal(result.total);
    } catch (error) {
      console.error('加载审计日志失败:', error);
    } finally {
      setLoading(false);
    }
  };
  
  // 初始加载
  useEffect(() => {
    loadAuditLogs();
  }, [page, rowsPerPage, filter]);
  
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
  
  // 页面变化处理
  const handleChangePage = (event: unknown, newPage: number) => {
    setPage(newPage);
  };
  
  // 每页行数变化处理
  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
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
  
  // 清除过滤器
  const handleClearFilter = () => {
    setTempFilter({});
  };
  
  // 刷新数据
  const handleRefresh = () => {
    loadAuditLogs();
  };
  
  // 渲染日志表格
  const renderLogsTable = () => (
    <TableContainer component={Paper} sx={{ mt: 2 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>时间</TableCell>
            <TableCell>用户ID</TableCell>
            <TableCell>操作</TableCell>
            <TableCell>资源类型</TableCell>
            <TableCell>资源ID</TableCell>
            <TableCell>状态</TableCell>
            <TableCell>IP地址</TableCell>
            <TableCell>操作</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {logs.length === 0 ? (
            <TableRow>
              <TableCell colSpan={8} align="center">
                {loading ? '加载中...' : '暂无数据'}
              </TableCell>
            </TableRow>
          ) : (
            logs.map((log) => (
              <TableRow key={log.id}>
                <TableCell>
                  {format(parseISO(log.created_at), 'yyyy-MM-dd HH:mm:ss')}
                </TableCell>
                <TableCell>{log.user_id}</TableCell>
                <TableCell>
                  <Chip 
                    size="small" 
                    label={log.action} 
                    color={actionColors[log.action] || 'default'} 
                    variant="outlined"
                  />
                </TableCell>
                <TableCell>{log.resource_type}</TableCell>
                <TableCell>{log.resource_id || '-'}</TableCell>
                <TableCell>
                  <Chip 
                    size="small" 
                    label={log.status} 
                    color={statusColors[log.status as keyof typeof statusColors]} 
                  />
                </TableCell>
                <TableCell>{log.ip_address || '-'}</TableCell>
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
        rowsPerPageOptions={[5, 10, 25, 50]}
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
  
  // 渲染过滤器对话框
  const renderFilterDialog = () => (
    <Dialog open={filterDialogOpen} onClose={() => setFilterDialogOpen(false)} maxWidth="md">
      <DialogTitle>
        <Box display="flex" alignItems="center">
          <FilterIcon sx={{ mr: 1 }} />
          过滤审计日志
        </Box>
      </DialogTitle>
      <DialogContent dividers>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="用户ID"
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
              <MenuItem value="">全部</MenuItem>
              {Object.values(AuditAction).map((action) => (
                <MenuItem key={action} value={action}>{action}</MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="资源类型"
              select
              value={tempFilter.resource_type || ''}
              onChange={(e) => setTempFilter({ ...tempFilter, resource_type: e.target.value })}
              variant="outlined"
              size="small"
              margin="normal"
            >
              <MenuItem value="">全部</MenuItem>
              {Object.values(AuditResourceType).map((type) => (
                <MenuItem key={type} value={type}>{type}</MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="资源ID"
              value={tempFilter.resource_id || ''}
              onChange={(e) => setTempFilter({ ...tempFilter, resource_id: e.target.value })}
              variant="outlined"
              size="small"
              margin="normal"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="状态"
              select
              value={tempFilter.status || ''}
              onChange={(e) => setTempFilter({ ...tempFilter, status: e.target.value })}
              variant="outlined"
              size="small"
              margin="normal"
            >
              <MenuItem value="">全部</MenuItem>
              <MenuItem value="success">成功</MenuItem>
              <MenuItem value="failure">失败</MenuItem>
            </TextField>
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
                slotProps={{ textField: { fullWidth: true, size: 'small', margin: 'normal' } }}
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
                slotProps={{ textField: { fullWidth: true, size: 'small', margin: 'normal' } }}
              />
            </LocalizationProvider>
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button startIcon={<ClearIcon />} onClick={handleClearFilter} color="inherit">
          清除
        </Button>
        <Button startIcon={<SearchIcon />} onClick={handleApplyFilter} color="primary" variant="contained">
          应用
        </Button>
      </DialogActions>
    </Dialog>
  );
  
  // 渲染日志详情对话框
  const renderDetailsDialog = () => (
    <Dialog open={detailsDialogOpen} onClose={() => setDetailsDialogOpen(false)} maxWidth="md" fullWidth>
      <DialogTitle>
        审计日志详情
      </DialogTitle>
      <DialogContent dividers>
        {selectedLog && (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary">ID</Typography>
              <Typography variant="body2">{selectedLog.id}</Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary">时间</Typography>
              <Typography variant="body2">
                {format(parseISO(selectedLog.created_at), 'yyyy-MM-dd HH:mm:ss')}
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary">用户ID</Typography>
              <Typography variant="body2">{selectedLog.user_id}</Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary">操作</Typography>
              <Chip 
                size="small" 
                label={selectedLog.action} 
                color={actionColors[selectedLog.action] || 'default'} 
                variant="outlined"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary">资源类型</Typography>
              <Typography variant="body2">{selectedLog.resource_type}</Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary">资源ID</Typography>
              <Typography variant="body2">{selectedLog.resource_id || '-'}</Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary">状态</Typography>
              <Chip 
                size="small" 
                label={selectedLog.status} 
                color={statusColors[selectedLog.status as keyof typeof statusColors]} 
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary">IP地址</Typography>
              <Typography variant="body2">{selectedLog.ip_address || '-'}</Typography>
            </Grid>
            <Grid item xs={12}>
              <Typography variant="subtitle2" color="text.secondary">详细信息</Typography>
              {selectedLog.details ? (
                <Box 
                  sx={{ 
                    backgroundColor: 'action.hover',
                    p: 2,
                    borderRadius: 1,
                    overflowX: 'auto'
                  }}
                >
                  <pre style={{ margin: 0 }}>
                    {JSON.stringify(selectedLog.details, null, 2)}
                  </pre>
                </Box>
              ) : (
                <Typography variant="body2">无</Typography>
              )}
            </Grid>
          </Grid>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setDetailsDialogOpen(false)}>关闭</Button>
      </DialogActions>
    </Dialog>
  );

  return (
    <div>
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6" component="h2">
              审计日志
            </Typography>
            <Box>
              <Tooltip title="刷新">
                <IconButton onClick={handleRefresh} disabled={loading}>
                  {loading ? <CircularProgress size={24} /> : <RefreshIcon />}
                </IconButton>
              </Tooltip>
              <Tooltip title="筛选">
                <IconButton onClick={handleOpenFilterDialog}>
                  <FilterIcon />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
          
          {/* 已应用的过滤器提示 */}
          {Object.keys(filter).length > 0 && (
            <Box display="flex" flexWrap="wrap" gap={1} mb={2}>
              {filter.user_id && (
                <Chip size="small" label={`用户ID: ${filter.user_id}`} onDelete={() => setFilter({ ...filter, user_id: undefined })} />
              )}
              {filter.action && (
                <Chip size="small" label={`操作: ${filter.action}`} onDelete={() => setFilter({ ...filter, action: undefined })} />
              )}
              {filter.resource_type && (
                <Chip size="small" label={`资源类型: ${filter.resource_type}`} onDelete={() => setFilter({ ...filter, resource_type: undefined })} />
              )}
              {filter.resource_id && (
                <Chip size="small" label={`资源ID: ${filter.resource_id}`} onDelete={() => setFilter({ ...filter, resource_id: undefined })} />
              )}
              {filter.status && (
                <Chip size="small" label={`状态: ${filter.status}`} onDelete={() => setFilter({ ...filter, status: undefined })} />
              )}
              {filter.start_date && (
                <Chip 
                  size="small" 
                  label={`开始日期: ${format(parseISO(filter.start_date), 'yyyy-MM-dd')}`} 
                  onDelete={() => setFilter({ ...filter, start_date: undefined })} 
                />
              )}
              {filter.end_date && (
                <Chip 
                  size="small" 
                  label={`结束日期: ${format(parseISO(filter.end_date), 'yyyy-MM-dd')}`} 
                  onDelete={() => setFilter({ ...filter, end_date: undefined })} 
                />
              )}
              <Chip 
                size="small" 
                label="清除全部" 
                onDelete={() => setFilter({})} 
                color="error" 
              />
            </Box>
          )}
          
          {renderLogsTable()}
        </CardContent>
      </Card>
      
      {renderFilterDialog()}
      {renderDetailsDialog()}
    </div>
  );
};

export default AuditLogList; 