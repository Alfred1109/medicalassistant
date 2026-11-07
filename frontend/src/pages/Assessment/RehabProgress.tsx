import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import {
  Box,
  Typography,
  Container,
  Paper,
  Card,
  CardContent,
  Button,
  LinearProgress,
  Alert,
  CircularProgress,
  Chip,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import TimelineIcon from '@mui/icons-material/Timeline';
import { AppDispatch, RootState } from '../../store';
import { fetchRehabPlans } from '../../store/slices/rehabSlice';
import { RehabPlan } from '../../types/rehab';

/**
 * 康复进度页面（真实数据版）
 *
 * 数据来源：dispatch 已有的 fetchRehabPlans thunk（GET /rehabilitation/plans），
 * 计划对象的 exercises[].completed 为真实完成标记，完成率据此计算。
 *
 * 后端不提供独立的"康复目标"接口，本页不再展示虚构目标；
 * 详细的统计与趋势请查看各计划详情页的"康复进度评估"（真实 /statistics、/trends 端点）。
 */

// 状态中文映射
const statusLabels: Record<string, string> = {
  active: '进行中',
  completed: '已完成',
  archived: '已归档',
  cancelled: '已取消',
};

// 状态芯片颜色
const statusColors: Record<string, 'primary' | 'success' | 'default' | 'error'> = {
  active: 'primary',
  completed: 'success',
  archived: 'default',
  cancelled: 'error',
};

// 基于计划内 exercises[].completed 计算真实完成率
const calculateProgress = (plan: RehabPlan): number | null => {
  if (!plan.exercises || plan.exercises.length === 0) return null;
  const completed = plan.exercises.filter((ex) => ex.completed).length;
  return Math.round((completed / plan.exercises.length) * 100);
};

const RehabProgress: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const plans = useSelector((state: RootState) => state.rehab?.plans || []);
  const loading = useSelector((state: RootState) => state.rehab?.loading || false);
  const error = useSelector((state: RootState) => state.rehab?.error);

  // 拉取真实康复计划列表
  React.useEffect(() => {
    dispatch(fetchRehabPlans());
  }, [dispatch]);

  // 手动重试（错误状态下的重载按钮）
  const handleRetry = () => {
    dispatch(fetchRehabPlans());
  };

  return (
    <Container maxWidth="lg">
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <TimelineIcon color="primary" sx={{ mr: 2, fontSize: 32 }} />
          <Typography variant="h5" component="h1">
            康复进度评估
          </Typography>
        </Box>
        <Typography variant="body1" color="text.secondary" paragraph>
          查看您各个康复计划的真实完成进度
        </Typography>
      </Paper>

      {/* 错误状态（含重试） */}
      {!loading && error && (
        <Alert
          severity="error"
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small" onClick={handleRetry}>
              重试
            </Button>
          }
        >
          {error}
        </Alert>
      )}

      {/* 加载状态 */}
      {loading && (
        <Box display="flex" justifyContent="center" my={4}>
          <CircularProgress />
        </Box>
      )}

      {/* 空状态 */}
      {!loading && !error && plans.length === 0 && (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1">暂无康复计划，无法展示进度数据。</Typography>
        </Paper>
      )}

      {/* 真实计划进度列表 */}
      {!loading && plans.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              各计划完成进度
            </Typography>
            <List>
              {plans.map((plan: RehabPlan) => {
                const planId = plan.id || plan._id || '';
                const progress = calculateProgress(plan);
                return (
                  <ListItem
                    key={planId}
                    divider
                    secondaryAction={
                      <Button
                        size="small"
                        component={Link}
                        to={`/app/rehab-plans/${planId}`}
                      >
                        查看统计
                      </Button>
                    }
                  >
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="body1">{plan.name || plan.title}</Typography>
                          <Chip
                            size="small"
                            label={statusLabels[plan.status] || plan.status}
                            color={statusColors[plan.status] || 'default'}
                          />
                        </Box>
                      }
                      secondary={
                        progress !== null
                          ? `已完成运动 ${plan.exercises.filter((ex) => ex.completed).length}/${plan.exercises.length} 项`
                          : '计划内暂无运动条目，无法计算完成率'
                      }
                    />
                    {progress !== null && (
                      <Box sx={{ width: '30%', display: 'flex', alignItems: 'center', mr: 2 }}>
                        <Box sx={{ width: '100%', mr: 1 }}>
                          <LinearProgress variant="determinate" value={progress} />
                        </Box>
                        <Typography variant="body2">{progress}%</Typography>
                      </Box>
                    )}
                  </ListItem>
                );
              })}
            </List>
          </CardContent>
        </Card>
      )}

      {/* 诚实说明：后端无"康复目标"接口，本页不展示虚构目标 */}
      {!loading && !error && plans.length > 0 && (
        <Alert severity="info" sx={{ mt: 3 }}>
          康复目标功能暂无后端支持，此处不做展示。更详细的进度统计与完成趋势请进入具体计划的详情页查看。
        </Alert>
      )}
    </Container>
  );
};

export default RehabProgress;
