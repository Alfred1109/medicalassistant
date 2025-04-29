import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Link, useNavigate } from 'react-router-dom';
import { 
  Box, 
  Button, 
  Card, 
  CardActions, 
  CardContent, 
  Container, 
  Divider,
  FormControl,
  Grid, 
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper, 
  Select,
  TextField,
  Typography
} from '@mui/material';
import { useTheme } from '@mui/material/styles';

// 需要单独导入的Material UI组件
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import InputAdornment from '@mui/material/InputAdornment';
import Menu from '@mui/material/Menu';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Tooltip from '@mui/material/Tooltip';

import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import SearchIcon from '@mui/icons-material/Search';
import ArchiveIcon from '@mui/icons-material/Archive';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import FilterListIcon from '@mui/icons-material/FilterList';
import GridViewIcon from '@mui/icons-material/GridView';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import ScheduleIcon from '@mui/icons-material/Schedule';
import ViewListIcon from '@mui/icons-material/ViewList';

import { format } from 'date-fns';
import { createSelector } from 'reselect';

// 导入React hooks
const { useState, useEffect } = React;

// 导入Redux相关
import { AppDispatch, RootState } from '../../store';
import { fetchRehabPlans, deleteRehabPlan } from '../../store/slices/rehabSlice';
import { RehabPlan } from '../../types/rehab';

// 创建记忆化选择器
const selectRehabPlans = createSelector(
  [(state: RootState) => state.rehab?.plans || []],
  (plans) => plans
);

// 定义状态类型
type PlanStatus = 'all' | 'active' | 'completed' | 'archived';

// 定义视图类型
type ViewMode = 'grid' | 'list';

/**
 * 康复计划列表页面组件
 */
const RehabPlans: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const theme = useTheme();
  
  // 从Redux中获取康复计划数据
  const plans = useSelector(selectRehabPlans);
  const loading = useSelector((state: RootState) => state.rehab.loading);
  
  // 本地状态
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<PlanStatus>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [selectedPlans, setSelectedPlans] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<string>('startDate');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState<boolean>(false);
  const [planToDelete, setPlanToDelete] = useState<string | null>(null);
  const [menuAnchorEl, setMenuAnchorEl] = useState<null | HTMLElement>(null);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  
  // 加载康复计划数据
  useEffect(() => {
    dispatch(fetchRehabPlans());
  }, [dispatch]);
  
  // 菜单处理函数
  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, planId: string) => {
    setMenuAnchorEl(event.currentTarget);
    setActivePlanId(planId);
  };
  
  const handleMenuClose = () => {
    setMenuAnchorEl(null);
    setActivePlanId(null);
  };
  
  // 删除对话框处理
  const handleDeleteClick = (planId: string) => {
    setPlanToDelete(planId);
    setDeleteDialogOpen(true);
    handleMenuClose();
  };
  
  const handleDeleteConfirm = () => {
    if (planToDelete) {
      dispatch(deleteRehabPlan(planToDelete));
    }
    setDeleteDialogOpen(false);
    setPlanToDelete(null);
  };
  
  const handleDeleteCancel = () => {
    setDeleteDialogOpen(false);
    setPlanToDelete(null);
  };
  
  // 选择项处理
  const handleSelectPlan = (planId: string) => {
    setSelectedPlans(prev => {
      if (prev.includes(planId)) {
        return prev.filter(id => id !== planId);
      } else {
        return [...prev, planId];
      }
    });
  };
  
  const handleSelectAll = () => {
    if (selectedPlans.length === filteredPlans.length) {
      setSelectedPlans([]);
    } else {
      setSelectedPlans(filteredPlans.map(plan => plan.id || plan._id || ''));
    }
  };
  
  // 批量删除处理
  const handleBulkDelete = () => {
    // 这里可以实现批量删除逻辑
    // 例如: selectedPlans.forEach(planId => dispatch(deleteRehabPlan(planId)));
    console.log('批量删除:', selectedPlans);
    setSelectedPlans([]);
  };
  
  // 筛选和排序逻辑
  const filteredPlans = React.useMemo(() => {
    let result = [...plans];
    
    // 搜索过滤
    if (searchTerm) {
      const lowerCaseSearch = searchTerm.toLowerCase();
      result = result.filter(plan => 
        (plan.name?.toLowerCase() || '').includes(lowerCaseSearch) || 
        (plan.description?.toLowerCase() || '').includes(lowerCaseSearch)
      );
    }
    
    // 状态过滤
    if (statusFilter !== 'all') {
      result = result.filter(plan => plan.status === statusFilter);
    }
    
    // 排序
    result.sort((a, b) => {
      switch (sortBy) {
        case 'name':
          return (a.name || a.title || '').localeCompare(b.name || b.title || '');
        case 'startDate':
          return new Date(a.startDate).getTime() - new Date(b.startDate).getTime();
        case 'exercises':
          return (b.exercises?.length || 0) - (a.exercises?.length || 0);
        default:
          return 0;
      }
    });
    
    return result;
  }, [plans, searchTerm, statusFilter, sortBy]);
  
  // 格式化日期函数
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    try {
      return format(new Date(dateString), 'yyyy-MM-dd');
    } catch (e) {
      return 'Invalid date';
    }
  };
  
  // 计算完成百分比
  const calculateProgress = (plan: RehabPlan) => {
    if (!plan.exercises || plan.exercises.length === 0) return 0;
    const completedExercises = plan.exercises.filter(ex => ex.completed).length;
    return Math.round((completedExercises / plan.exercises.length) * 100);
  };
  
  // 获取状态芯片样式
  const getStatusChipColor = (status: string) => {
    switch (status) {
      case 'active':
        return {
          color: 'primary',
          icon: <PlayCircleOutlineIcon fontSize="small" />
        };
      case 'completed':
        return {
          color: 'success',
          icon: <CheckCircleIcon fontSize="small" />
        };
      case 'archived':
        return {
          color: 'default',
          icon: <ArchiveIcon fontSize="small" />
        };
      default:
        return {
          color: 'default',
          icon: null
        };
    }
  };
  
  // 渲染计划卡片 (网格视图)
  const renderPlanCard = (plan: RehabPlan) => {
    const planId = plan.id || plan._id || '';
    const isSelected = selectedPlans.includes(planId);
    const progress = calculateProgress(plan);
    const statusInfo = getStatusChipColor(plan.status);
    
    return (
      <Card 
        sx={{ 
          height: '100%', 
          display: 'flex', 
          flexDirection: 'column',
          position: 'relative',
          border: isSelected ? `2px solid ${theme.palette.primary.main}` : 'none',
          transition: 'all 0.2s'
        }}
      >
        {/* 选择框 */}
        <Checkbox
          checked={isSelected}
          onChange={() => handleSelectPlan(planId)}
          sx={{ position: 'absolute', top: 0, left: 0, zIndex: 1 }}
        />
        
        {/* 菜单按钮 */}
        <IconButton
          aria-label="more"
          sx={{ position: 'absolute', top: 0, right: 0 }}
          onClick={(e) => handleMenuOpen(e, planId)}
        >
          <MoreVertIcon />
        </IconButton>
        
        <CardContent sx={{ flexGrow: 1, pt: 4 }}>
          <Stack direction="row" alignItems="center" spacing={1} mb={1}>
            <Typography variant="h6" component="div" noWrap>
              {plan.name || plan.title}
            </Typography>
            <Chip 
              size="small"
              label={plan.status}
              color={statusInfo.color as any}
              icon={statusInfo.icon}
            />
          </Stack>
          
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {plan.description?.length > 80 
              ? `${plan.description.substring(0, 80)}...` 
              : plan.description}
          </Typography>
          
          <Stack spacing={1}>
            <Typography variant="body2">
              <ScheduleIcon fontSize="small" sx={{ verticalAlign: 'middle', mr: 0.5 }} />
              开始时间: {formatDate(plan.startDate)}
            </Typography>
            
            <Typography variant="body2">
              练习数量: {plan.exercises?.length || 0}
            </Typography>
            
            <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
              <Typography variant="body2" sx={{ mr: 1 }}>
                完成进度:
              </Typography>
              <Box sx={{ width: '100%', mr: 1 }}>
                <LinearProgress variant="determinate" value={progress} />
              </Box>
              <Typography variant="body2">{progress}%</Typography>
            </Box>
          </Stack>
        </CardContent>
        <Divider />
        <CardActions>
          <Button
            size="small"
            component={Link}
            to={`/app/rehab-plans/${planId}`}
          >
            查看详情
          </Button>
          <Button
            size="small"
            component={Link}
            to={`/app/rehab-plans/edit/${planId}`}
          >
            编辑
          </Button>
        </CardActions>
      </Card>
    );
  };
  
  // 渲染计划列表项 (列表视图)
  const renderPlanListItem = (plan: RehabPlan) => {
    const planId = plan.id || plan._id || '';
    const isSelected = selectedPlans.includes(planId);
    const progress = calculateProgress(plan);
    const statusInfo = getStatusChipColor(plan.status);
    
    return (
      <Paper 
        sx={{ 
          p: 2, 
          mb: 2,
          border: isSelected ? `2px solid ${theme.palette.primary.main}` : 'none',
          transition: 'all 0.2s'
        }}
      >
        <Grid container alignItems="center">
          <Grid item xs={1}>
            <Checkbox
              checked={isSelected}
              onChange={() => handleSelectPlan(planId)}
            />
          </Grid>
          <Grid item xs={3}>
            <Typography variant="subtitle1" noWrap>
              {plan.name || plan.title}
            </Typography>
          </Grid>
          <Grid item xs={2}>
            <Chip 
              size="small"
              label={plan.status}
              color={statusInfo.color as any}
              icon={statusInfo.icon}
            />
          </Grid>
          <Grid item xs={2}>
            <Typography variant="body2">
              {formatDate(plan.startDate)}
            </Typography>
          </Grid>
          <Grid item xs={2}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <Box sx={{ width: '50%', mr: 1 }}>
                <LinearProgress variant="determinate" value={progress} />
              </Box>
              <Typography variant="body2">{progress}%</Typography>
            </Box>
          </Grid>
          <Grid item xs={2}>
            <Stack direction="row" spacing={1}>
              <Tooltip title="查看详情">
                <IconButton 
                  size="small"
                  component={Link}
                  to={`/app/rehab-plans/${planId}`}
                >
                  <SearchIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="编辑">
                <IconButton 
                  size="small"
                  component={Link}
                  to={`/app/rehab-plans/edit/${planId}`}
                >
                  <EditIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="更多操作">
                <IconButton
                  size="small"
                  onClick={(e) => handleMenuOpen(e, planId)}
                >
                  <MoreVertIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          </Grid>
        </Grid>
      </Paper>
    );
  };
  
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      {/* 标题和操作按钮区 */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1" gutterBottom>
          康复计划管理
        </Typography>
        <Button
          variant="contained"
          color="primary"
          startIcon={<AddIcon />}
          component={Link}
          to="/app/rehab-plans/new"
        >
          新建计划
        </Button>
      </Box>
      
      {/* 搜索和筛选区 */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              placeholder="搜索康复计划..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              variant="outlined"
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
            />
          </Grid>
          <Grid item xs={12} md={3}>
            <FormControl fullWidth variant="outlined">
              <InputLabel>状态</InputLabel>
              <Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as PlanStatus)}
                label="状态"
              >
                <MenuItem value="all">所有状态</MenuItem>
                <MenuItem value="active">进行中</MenuItem>
                <MenuItem value="completed">已完成</MenuItem>
                <MenuItem value="archived">已归档</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={3}>
            <FormControl fullWidth variant="outlined">
              <InputLabel>排序方式</InputLabel>
              <Select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                label="排序方式"
              >
                <MenuItem value="startDate">按开始日期</MenuItem>
                <MenuItem value="name">按名称</MenuItem>
                <MenuItem value="exercises">按练习数量</MenuItem>
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Paper>
      
      {/* 批量操作工具栏 */}
      {selectedPlans.length > 0 && (
        <Paper sx={{ p: 2, mb: 3, bgcolor: theme.palette.primary.light }}>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="subtitle1" color="primary.contrastText">
              已选择 {selectedPlans.length} 个计划
            </Typography>
            <Box>
              <Button 
                size="small" 
                color="error"
                onClick={handleBulkDelete}
                startIcon={<DeleteIcon />}
                sx={{ color: theme.palette.error.main, bgcolor: 'white', mr: 1 }}
              >
                批量删除
              </Button>
              <Button 
                size="small"
                onClick={() => setSelectedPlans([])}
                sx={{ color: theme.palette.primary.contrastText }}
              >
                取消选择
              </Button>
            </Box>
          </Box>
        </Paper>
      )}
      
      {/* 视图切换和结果计数 */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="subtitle1" color="text.secondary">
          共 {filteredPlans.length} 个康复计划
        </Typography>
        <Box>
          <Tooltip title="网格视图">
            <IconButton
              color={viewMode === 'grid' ? 'primary' : 'default'}
              onClick={() => setViewMode('grid')}
            >
              <GridViewIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="列表视图">
            <IconButton
              color={viewMode === 'list' ? 'primary' : 'default'}
              onClick={() => setViewMode('list')}
            >
              <ViewListIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>
      
      {/* 加载指示器 */}
      {loading && (
        <Box sx={{ width: '100%', mt: 2, mb: 2 }}>
          <LinearProgress />
        </Box>
      )}
      
      {/* 内容区 - 网格视图或列表视图 */}
      {!loading && (
        <>
          {filteredPlans.length === 0 ? (
            <Paper sx={{ p: 4, textAlign: 'center' }}>
              <Typography variant="body1">
                {searchTerm || statusFilter !== 'all' 
                  ? '没有找到匹配的康复计划。' 
                  : '您目前还没有康复计划。点击"新建计划"按钮开始创建。'}
              </Typography>
            </Paper>
          ) : (
            <>
              {viewMode === 'grid' ? (
                <Grid container spacing={3}>
                  {filteredPlans.map((plan: RehabPlan) => (
                    <Grid 
                      item 
                      xs={12} 
                      sm={6} 
                      md={4} 
                      key={plan.id || plan._id}
                    >
                      {renderPlanCard(plan)}
                    </Grid>
                  ))}
                </Grid>
              ) : (
                <Box>
                  {/* 列表标题 */}
                  <Paper sx={{ p: 2, mb: 2, bgcolor: theme.palette.grey[100] }}>
                    <Grid container alignItems="center">
                      <Grid item xs={1}>
                        <Checkbox
                          indeterminate={selectedPlans.length > 0 && selectedPlans.length < filteredPlans.length}
                          checked={selectedPlans.length > 0 && selectedPlans.length === filteredPlans.length}
                          onChange={handleSelectAll}
                        />
                      </Grid>
                      <Grid item xs={3}>
                        <Typography variant="subtitle2">计划名称</Typography>
                      </Grid>
                      <Grid item xs={2}>
                        <Typography variant="subtitle2">状态</Typography>
                      </Grid>
                      <Grid item xs={2}>
                        <Typography variant="subtitle2">开始日期</Typography>
                      </Grid>
                      <Grid item xs={2}>
                        <Typography variant="subtitle2">进度</Typography>
                      </Grid>
                      <Grid item xs={2}>
                        <Typography variant="subtitle2">操作</Typography>
                      </Grid>
                    </Grid>
                  </Paper>
                  
                  {/* 列表内容 */}
                  {filteredPlans.map((plan: RehabPlan) => renderPlanListItem(plan))}
                </Box>
              )}
            </>
          )}
        </>
      )}
      
      {/* 上下文菜单 */}
      <Menu
        anchorEl={menuAnchorEl}
        open={Boolean(menuAnchorEl)}
        onClose={handleMenuClose}
      >
        <MenuItem 
          component={Link} 
          to={`/app/rehab-plans/${activePlanId}`}
          onClick={handleMenuClose}
        >
          <SearchIcon fontSize="small" sx={{ mr: 1 }} />
          查看详情
        </MenuItem>
        <MenuItem 
          component={Link} 
          to={`/app/rehab-plans/edit/${activePlanId}`}
          onClick={handleMenuClose}
        >
          <EditIcon fontSize="small" sx={{ mr: 1 }} />
          编辑计划
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => activePlanId && handleDeleteClick(activePlanId)}>
          <DeleteIcon fontSize="small" sx={{ mr: 1, color: theme.palette.error.main }} />
          <Typography color="error">删除计划</Typography>
        </MenuItem>
      </Menu>
      
      {/* 删除确认对话框 */}
      <Dialog
        open={deleteDialogOpen}
        onClose={handleDeleteCancel}
      >
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <DialogContentText>
            您确定要删除这个康复计划吗？此操作无法撤销。
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeleteCancel}>取消</Button>
          <Button onClick={handleDeleteConfirm} color="error" autoFocus>
            删除
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default RehabPlans; 