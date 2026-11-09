import React, { useEffect, useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Divider,
  Chip,
  Button,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack,
  Grid,
  CircularProgress,
  Alert
} from '@mui/material';
import { format, isValid, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { LocalizationProvider, DatePicker } from '@mui/x-date-pickers';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';

// 图标
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import DoneIcon from '@mui/icons-material/Done';
import CancelIcon from '@mui/icons-material/Cancel';
import EventIcon from '@mui/icons-material/Event';
import RefreshIcon from '@mui/icons-material/Refresh';
import FilterListIcon from '@mui/icons-material/FilterList';
import SearchIcon from '@mui/icons-material/Search';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';

import type { FollowUpFilters, FollowUpRecord } from '../../types/followup';
import {
  followUpTypes, followUpStatuses, getFollowUpStatusInfo, getFollowUpTypeLabel, manualEntryText,
} from '../../constants/followup';

// 组件属性
interface FollowUpListProps {
  records: FollowUpRecord[];
  loading?: boolean;
  error?: string;
  totalCount?: number;
  page?: number;
  pageSize?: number;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  onAdd?: () => void;
  onEdit?: (id: string) => void;
  onView?: (id: string) => void;
  onReEvaluate?: (id: string) => void;
  canReEvaluate?: (record: FollowUpRecord) => boolean;
  onComplete?: (id: string) => void;
  onReview?: (id: string) => void;
  canReview?: (record: FollowUpRecord) => boolean;
  onCancel?: (id: string) => void;
  onReschedule?: (id: string) => void;
  onDelete?: (id: string) => void;
  onFilterChange?: (filters: FollowUpFilters) => void;
  onRefresh?: () => void;
  currentFilters?: FollowUpFilters;
}

const EMPTY_FILTERS: FollowUpFilters = {};

const FollowUpList: React.FC<FollowUpListProps> = ({
  records,
  loading = false,
  error,
  totalCount = 0,
  page = 0,
  pageSize = 10,
  onPageChange,
  onPageSizeChange,
  onAdd,
  onEdit,
  onView,
  onReEvaluate,
  canReEvaluate,
  onComplete,
  onReview,
  canReview,
  onCancel,
  onReschedule,
  onDelete,
  onFilterChange,
  onRefresh,
  currentFilters = EMPTY_FILTERS
}) => {
  // 状态
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState(currentFilters);
  useEffect(() => { setFilters(currentFilters); }, [currentFilters]);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [actionDialogOpen, setActionDialogOpen] = useState(false);
  const [actionType, setActionType] = useState<'complete' | 'cancel' | 'reschedule' | null>(null);
  
  // 过滤器变更处理
  const handleFilterChange = <K extends keyof FollowUpFilters>(field: K, value: FollowUpFilters[K]) => {
    const newFilters = { ...filters, [field]: value };
    setFilters(newFilters);
  };
  
  // 应用过滤器
  const applyFilters = () => {
    if (onFilterChange) {
      onFilterChange(filters);
    }
    setShowFilters(false);
  };
  
  // 重置过滤器
  const resetFilters = () => {
    setFilters({});
    if (onFilterChange) {
      onFilterChange({});
    }
    setShowFilters(false);
  };
  
  // 处理页面变更
  const handleChangePage = (event: unknown, newPage: number) => {
    if (onPageChange) {
      onPageChange(newPage);
    }
  };
  
  // 处理每页数量变更
  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (onPageSizeChange) {
      onPageSizeChange(parseInt(event.target.value, 10));
    }
    if (onPageChange) {
      onPageChange(0);
    }
  };
  
  // 删除对话框处理
  const handleDeleteClick = (id: string) => {
    setSelectedRecordId(id);
    setDeleteDialogOpen(true);
  };
  
  const handleDeleteConfirm = () => {
    if (selectedRecordId && onDelete) {
      onDelete(selectedRecordId);
    }
    setDeleteDialogOpen(false);
    setSelectedRecordId(null);
  };
  
  // 操作对话框处理
  const handleActionClick = (id: string, action: 'complete' | 'cancel' | 'reschedule') => {
    setSelectedRecordId(id);
    setActionType(action);
    setActionDialogOpen(true);
  };
  
  const handleActionConfirm = () => {
    if (selectedRecordId) {
      switch (actionType) {
        case 'complete':
          if (onComplete) onComplete(selectedRecordId);
          break;
        case 'cancel':
          if (onCancel) onCancel(selectedRecordId);
          break;
        case 'reschedule':
          if (onReschedule) onReschedule(selectedRecordId);
          break;
      }
    }
    setActionDialogOpen(false);
    setSelectedRecordId(null);
    setActionType(null);
  };
  
  // 格式化日期
  const formatDate = (dateString: string) => {
    try {
      return format(parseISO(dateString), 'yyyy年MM月dd日 HH:mm', { locale: zhCN });
    } catch (e) {
      return dateString;
    }
  };
  
  // 渲染操作按钮
  const renderActions = (record: FollowUpRecord) => {
    switch (record.status) {
      case 'in_review':
        return onReview ? <Button size="small" disabled={canReview ? !canReview(record) : false} onClick={() => onReview(record.id)}>审阅随访</Button> : null;
      case 'scheduled':
      case 'awaiting_fill':
      case 'rescheduled':
        return (
          <Stack direction="row" spacing={1}>
            <IconButton 
              size="small" 
              color="success" 
              onClick={() => handleActionClick(record.id, 'complete')}
              title={manualEntryText.action}
            >
              <DoneIcon fontSize="small" />
            </IconButton>
            <IconButton 
              size="small" 
              color="primary" 
              onClick={() => handleActionClick(record.id, 'reschedule')}
              title="重新安排"
            >
              <EventIcon fontSize="small" />
            </IconButton>
            <IconButton 
              size="small" 
              color="error" 
              onClick={() => handleActionClick(record.id, 'cancel')}
              title="取消随访"
            >
              <CancelIcon fontSize="small" />
            </IconButton>
          </Stack>
        );
      case 'completed':
      case 'canceled':
      case 'missed':
      case 'overdue':
      case 'lost':
        if (onView) return null;
        return (
          <Stack direction="row" spacing={1}>
            <IconButton 
              size="small" 
              color="primary" 
              onClick={() => onEdit && onEdit(record.id)}
              title="查看详情"
            >
              <MoreHorizIcon fontSize="small" />
            </IconButton>
          </Stack>
        );
      default:
        return (
          <Stack direction="row" spacing={1}>
            <IconButton 
              size="small" 
              color="primary" 
              onClick={() => onEdit && onEdit(record.id)}
              title="编辑"
            >
              <EditIcon fontSize="small" />
            </IconButton>
            <IconButton 
              size="small" 
              color="error" 
              onClick={() => handleDeleteClick(record.id)}
              title="删除"
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Stack>
        );
    }
  };
  
  return (
    <Paper elevation={2}>
      <Box sx={{ p: { xs: 2, sm: 3 }, minWidth: 0 }}>
        <Box display="flex" justifyContent="space-between" mb={2} sx={{ flexDirection: { xs: 'column', sm: 'row' }, alignItems: { xs: 'flex-start', sm: 'center' }, gap: 1 }}>
          <Typography variant="h6">随访管理</Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            <Button 
              startIcon={<RefreshIcon />} 
              onClick={onRefresh} 
              sx={{ mr: 1 }}
            >
              刷新
            </Button>
            <Button 
              startIcon={<FilterListIcon />} 
              onClick={() => setShowFilters(!showFilters)}
              sx={{ mr: 1 }}
              color={Object.keys(filters).length > 0 ? 'primary' : 'inherit'}
              variant={Object.keys(filters).length > 0 ? 'contained' : 'outlined'}
            >
              筛选
            </Button>
            <Button 
              startIcon={<AddIcon />} 
              variant="contained" 
              color="primary"
              onClick={onAdd}
            >
              新建随访
            </Button>
          </Box>
        </Box>
        
        <Divider sx={{ mb: 2 }} />
        
        {/* 过滤器面板 */}
        {showFilters && (
          <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={6} md={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>随访类型</InputLabel>
                  <Select
                    value={filters.follow_up_type || ''}
                    label="随访类型"
                    onChange={(e) => handleFilterChange('follow_up_type', e.target.value)}
                  >
                    <MenuItem value="">全部</MenuItem>
                    {followUpTypes.map(type => (
                      <MenuItem key={type.value} value={type.value}>{type.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>状态</InputLabel>
                  <Select
                    value={filters.status || ''}
                    label="状态"
                    onChange={(e) => handleFilterChange('status', e.target.value)}
                  >
                    <MenuItem value="">全部</MenuItem>
                    {followUpStatuses.map(status => (
                      <MenuItem key={status.value} value={status.value}>{status.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
                  <DatePicker<Date>
                    label="开始日期"
                    format="yyyy-MM-dd"
                    value={filters.start_date ? parseISO(filters.start_date) : null}
                    onChange={(date) => {
                      if (date === null || isValid(date)) {
                        handleFilterChange('start_date', date ? format(date, 'yyyy-MM-dd') : null);
                      }
                    }}
                    slotProps={{ textField: { size: 'small', fullWidth: true } }}
                  />
                </LocalizationProvider>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={zhCN}>
                  <DatePicker<Date>
                    label="结束日期"
                    format="yyyy-MM-dd"
                    value={filters.end_date ? parseISO(filters.end_date) : null}
                    onChange={(date) => {
                      if (date === null || isValid(date)) {
                        handleFilterChange('end_date', date ? format(date, 'yyyy-MM-dd') : null);
                      }
                    }}
                    slotProps={{ textField: { size: 'small', fullWidth: true } }}
                  />
                </LocalizationProvider>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TextField
                  fullWidth
                  size="small"
                  label="搜索患者"
                  value={filters.patient_name || ''}
                  onChange={(e) => handleFilterChange('patient_name', e.target.value)}
                  InputProps={{
                    startAdornment: <SearchIcon color="action" fontSize="small" sx={{ mr: 1 }} />,
                  }}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box display="flex">
                  <Button 
                    variant="contained" 
                    color="primary" 
                    onClick={applyFilters}
                    sx={{ mr: 1 }}
                  >
                    应用筛选
                  </Button>
                  <Button 
                    variant="outlined" 
                    onClick={resetFilters}
                  >
                    重置
                  </Button>
                </Box>
              </Grid>
            </Grid>
          </Paper>
        )}
        
        {/* 错误提示 */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        
        {/* 数据表格 */}
        {loading ? (
          <Box display="flex" justifyContent="center" alignItems="center" height={300}>
            <CircularProgress />
          </Box>
        ) : records.length === 0 ? (
          <Box display="flex" justifyContent="center" alignItems="center" height={200}>
            <Typography color="text.secondary">
              {error ? '随访记录未能加载，请点击刷新重试。' : '暂无随访记录'}
            </Typography>
          </Box>
        ) : (
          <>
            <TableContainer>
              <Table aria-label="随访记录表格" sx={{ minWidth: 880 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>患者</TableCell>
                    <TableCell>随访类型</TableCell>
                    <TableCell>计划日期</TableCell>
                    <TableCell>实际日期</TableCell>
                    <TableCell>状态</TableCell>
                    <TableCell>备注</TableCell>
                    <TableCell>操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {records.map((record) => {
                    const statusInfo = getFollowUpStatusInfo(record.status);
                    
                    return (
                      <TableRow key={record.id}>
                        <TableCell>{record.patient_name || record.patient_id}</TableCell>
                        <TableCell>{getFollowUpTypeLabel(record.follow_up_type)}</TableCell>
                        <TableCell>
                          {formatDate(record.scheduled_date)}
                        </TableCell>
                        <TableCell>
                          {record.actual_date ? formatDate(record.actual_date) : '-'}
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={statusInfo.label} 
                            size="small" 
                            color={statusInfo.color}
                          />
                        </TableCell>
                        <TableCell>
                          <Typography 
                            variant="body2" 
                            sx={{ 
                              maxWidth: 200, 
                              whiteSpace: 'nowrap', 
                              overflow: 'hidden', 
                              textOverflow: 'ellipsis' 
                            }}
                          >
                            {record.notes || '-'}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Stack spacing={0.5}>
                            {onView && <Button size="small" onClick={() => onView(record.id)}>查看详情</Button>}
                            {renderActions(record)}
                            {onReEvaluate && canReEvaluate?.(record) && <Button size="small" onClick={() => onReEvaluate(record.id)}>发起复评</Button>}
                            {(record.next_visit_id || record.next_follow_up_id) && <Typography variant="caption" color="text.secondary">已有后继节点</Typography>}
                          </Stack>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
            
            <TablePagination
              rowsPerPageOptions={[5, 10, 25, 50]}
              component="div"
              count={totalCount}
              rowsPerPage={pageSize}
              page={page}
              onPageChange={handleChangePage}
              onRowsPerPageChange={handleChangeRowsPerPage}
              labelRowsPerPage="每页行数:"
              labelDisplayedRows={({ from, to, count }) => `${from}-${to} 共 ${count}`}
            />
          </>
        )}
      </Box>
      
      {/* 删除确认对话框 */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
      >
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <Typography>
            您确定要删除这条随访记录吗？此操作不可撤销。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>取消</Button>
          <Button onClick={handleDeleteConfirm} color="error" autoFocus>
            删除
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 操作确认对话框 */}
      <Dialog
        open={actionDialogOpen}
        onClose={() => setActionDialogOpen(false)}
      >
        <DialogTitle>
          {actionType === 'complete' ? manualEntryText.action :
           actionType === 'cancel' ? '取消随访' :
           actionType === 'reschedule' ? '重新安排随访' : ''}
        </DialogTitle>
        <DialogContent>
          <Typography>
            {actionType === 'complete' ? manualEntryText.confirmation :
             actionType === 'cancel' ? '您确定要取消此随访吗？' :
             actionType === 'reschedule' ? '您确定要重新安排此随访吗？' : ''}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setActionDialogOpen(false)}>取消</Button>
          <Button 
            onClick={handleActionConfirm} 
            color={
              actionType === 'complete' ? 'success' :
              actionType === 'cancel' ? 'error' :
              'primary'
            } 
            autoFocus
          >
            确认
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default FollowUpList;
