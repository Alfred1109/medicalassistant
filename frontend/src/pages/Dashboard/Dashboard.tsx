import React, { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Container,
  Divider,
  Grid,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Paper,
  Typography,
  useTheme,
} from '@mui/material';
import {
  Add as AddIcon,
  FitnessCenter as FitnessCenterIcon,
  Timeline as TimelineIcon,
  Schedule as ScheduleIcon,
} from '@mui/icons-material';

import { AppDispatch, RootState } from '../../store';
import { fetchRehabPlans } from '../../store/slices/rehabSlice';

const Dashboard: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const theme = useTheme();
  const { plans, loading } = useSelector((state: RootState) => state.rehab);
  const { user } = useSelector((state: RootState) => state.auth);

  useEffect(() => {
    dispatch(fetchRehabPlans());
  }, [dispatch]);

  const getActivePlans = () => {
    return plans.filter(plan => plan.status === 'active');
  };

  const getCompletedExercises = (planId: string) => {
    const plan = plans.find(p => p.id === planId);
    if (!plan) return 0;
    
    const completedCount = plan.exercises.filter(ex => ex.completed).length;
    return {
      count: completedCount,
      total: plan.exercises.length,
      percentage: plan.exercises.length > 0 
        ? (completedCount / plan.exercises.length) * 100 
        : 0
    };
  };

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return 'N/A';
    
    try {
      const date = new Date(dateString);
      // 检查日期是否有效
      if (isNaN(date.getTime())) {
        return 'Invalid Date';
      }
      
      return new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      }).format(date);
    } catch (error) {
      console.error('Date formatting error:', error);
      return 'Invalid Date';
    }
  };

  const getNextScheduledExercises = () => {
    const allExercises = plans.flatMap((plan, planIndex) => 
      plan.exercises.map((ex, exIndex) => ({
        ...ex,
        planId: plan.id,
        planName: plan.name,
        id: ex.id || `exercise-${plan.id}-${exIndex}`
      }))
    );
    
    return allExercises
      .filter(ex => !ex.completed && ex.scheduledDate)
      .sort((a, b) => new Date(a.scheduledDate).getTime() - new Date(b.scheduledDate).getTime())
      .slice(0, 5);
  };

  if (loading) {
    return (
      <Box sx={{ width: '100%', mt: 4 }}>
        <LinearProgress />
      </Box>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          欢迎, {user?.name || '用户'}
        </Typography>
        <Button
          variant="contained" 
          color="primary"
          startIcon={<AddIcon />}
          component={Link}
          to="/rehab-plans/new"
        >
          新建康复计划
        </Button>
      </Box>

      <Grid container spacing={3}>
        {/* Active Plans */}
        <Grid item xs={12} md={8}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              borderRadius: 2,
              boxShadow: theme.shadows[2],
              height: '100%',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <FitnessCenterIcon color="primary" sx={{ mr: 1 }} />
              <Typography component="h2" variant="h6" color="primary">
                进行中的康复计划
              </Typography>
            </Box>
            <Divider sx={{ mb: 2 }} />
            
            {getActivePlans().length === 0 ? (
              <Box sx={{ py: 4, textAlign: 'center' }}>
                <Typography variant="body1" color="text.secondary">
                  您目前没有进行中的康复计划。
                </Typography>
                <Button
                  variant="outlined"
                  color="primary"
                  startIcon={<AddIcon />}
                  component={Link}
                  to="/rehab-plans/new"
                  sx={{ mt: 2 }}
                >
                  创建您的第一个计划
                </Button>
              </Box>
            ) : (
              <List>
                {getActivePlans().map((plan) => {
                  const progress = getCompletedExercises(plan.id);
                  
                  return (
                    <ListItem 
                      key={plan.id}
                      sx={{ 
                        border: '1px solid',
                        borderColor: 'divider',
                        borderRadius: 1,
                        mb: 2,
                        flexDirection: 'column',
                        alignItems: 'flex-start'
                      }}
                      component={Link}
                      to={`/rehab-plans/${plan.id}`}
                      style={{ textDecoration: 'none', color: 'inherit' }}
                    >
                      <Box sx={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <ListItemText
                          primary={plan.name}
                          secondary={`创建时间: ${formatDate(plan.createdAt)}`}
                          primaryTypographyProps={{ fontWeight: 'bold', color: 'primary.main' }}
                        />
                        <Typography variant="body2" color="text.secondary">
                          已完成 {progress.count} / {progress.total} 个训练
                        </Typography>
                      </Box>
                      <Box sx={{ width: '100%', mt: 1 }}>
                        <LinearProgress 
                          variant="determinate" 
                          value={progress.percentage} 
                          sx={{ height: 8, borderRadius: 5 }}
                        />
                      </Box>
                    </ListItem>
                  );
                })}
              </List>
            )}
          </Paper>
        </Grid>
        
        {/* Upcoming Exercises */}
        <Grid item xs={12} md={4}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              borderRadius: 2,
              boxShadow: theme.shadows[2],
            }}
          >
            <CardHeader
              title="即将进行的训练"
              titleTypographyProps={{ variant: 'h6', color: 'primary' }}
              avatar={<ScheduleIcon color="primary" />}
            />
            <Divider />
            <CardContent sx={{ flexGrow: 1, pt: 0 }}>
              {getNextScheduledExercises().length === 0 ? (
                <Box sx={{ py: 3, textAlign: 'center' }}>
                  <Typography variant="body2" color="text.secondary">
                    您没有即将进行的训练。
                  </Typography>
                </Box>
              ) : (
                <List>
                  {getNextScheduledExercises().map((exercise) => (
                    <ListItem
                      key={exercise.id}
                      sx={{
                        borderBottom: '1px solid',
                        borderColor: 'divider',
                        py: 1,
                      }}
                      component={Link}
                      to={`/rehab-plans/${exercise.planId}`}
                      style={{ textDecoration: 'none', color: 'inherit' }}
                    >
                      <ListItemText
                        primary={exercise.name}
                        secondary={`${exercise.planName} · ${formatDate(exercise.scheduledDate)}`}
                        primaryTypographyProps={{ fontWeight: 'medium' }}
                      />
                    </ListItem>
                  ))}
                </List>
              )}
            </CardContent>
          </Card>
        </Grid>
        
        {/* Progress Summary */}
        <Grid item xs={12}>
          <Paper
            sx={{
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              borderRadius: 2,
              boxShadow: theme.shadows[2],
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <TimelineIcon color="primary" sx={{ mr: 1 }} />
              <Typography component="h2" variant="h6" color="primary">
                康复总体进度
              </Typography>
            </Box>
            <Divider sx={{ mb: 2 }} />
            
            {plans.length === 0 ? (
              <Box sx={{ py: 4, textAlign: 'center' }}>
                <Typography variant="body1" color="text.secondary">
                  您还没有创建任何康复计划。
                </Typography>
              </Box>
            ) : (
              <Grid container spacing={2}>
                {plans.slice(0, 3).map((plan) => {
                  const progress = getCompletedExercises(plan.id);
                  
                  return (
                    <Grid item xs={12} md={4} key={plan.id}>
                      <Box
                        sx={{
                          p: 2,
                          border: '1px solid',
                          borderColor: 'divider',
                          borderRadius: 2,
                        }}
                      >
                        <Typography variant="subtitle1" fontWeight="bold">
                          {plan.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                          状态: {plan.status === 'active' ? '进行中' : '已完成'}
                        </Typography>
                        <Box sx={{ width: '100%', mb: 1 }}>
                          <LinearProgress
                            variant="determinate"
                            value={progress.percentage}
                            sx={{ height: 8, borderRadius: 5 }}
                          />
                        </Box>
                        <Typography variant="body2" align="right">
                          {Math.round(progress.percentage)}% 完成
                        </Typography>
                      </Box>
                    </Grid>
                  );
                })}
              </Grid>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Container>
  );
};

export default Dashboard; 