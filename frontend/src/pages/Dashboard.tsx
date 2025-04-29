import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Grid,
  Paper,
  Typography,
  Button,
  Card,
  CardContent,
  CardActions,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  LinearProgress,
  Avatar,
  IconButton,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  FitnessCenter as FitnessCenterIcon,
  Psychology as PsychologyIcon,
  Person as PersonIcon,
  CalendarToday as CalendarIcon,
  CheckCircle as CheckCircleIcon,
  PendingActions as PendingIcon,
  Launch as LaunchIcon,
  TrendingUp as TrendingUpIcon,
} from '@mui/icons-material';
import { AppDispatch, RootState } from '../store';
import { fetchRehabPlans } from '../store/slices/rehabSlice';
import { fetchAgents } from '../store/slices/agentSlice';

const Dashboard: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const { plans, loading: plansLoading } = useSelector((state: RootState) => state.rehab);
  const { agents, loading: agentsLoading } = useSelector((state: RootState) => state.agents);

  React.useEffect(() => {
    dispatch(fetchRehabPlans());
    dispatch(fetchAgents());
  }, [dispatch]);

  const getActivePlans = () => {
    return plans.filter(plan => !plan.completed);
  };

  const getCompletedPlans = () => {
    return plans.filter(plan => plan.completed);
  };

  const getActiveExercisesCount = () => {
    let count = 0;
    plans.forEach(plan => {
      if (!plan.completed && plan.exercises) {
        count += plan.exercises.length;
      }
    });
    return count;
  };

  const getCompletedExercisesCount = () => {
    let count = 0;
    plans.forEach(plan => {
      if (plan.exercises) {
        count += plan.exercises.filter(ex => ex.completed).length;
      }
    });
    return count;
  };

  const getOverallProgress = () => {
    const totalExercises = plans.reduce((total, plan) => 
      total + (plan.exercises ? plan.exercises.length : 0), 0);
    
    if (totalExercises === 0) return 0;
    
    const completedExercises = getCompletedExercisesCount();
    return (completedExercises / totalExercises) * 100;
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1">
          Dashboard
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Welcome back, {user?.name || 'User'}
        </Typography>
      </Box>

      {/* Progress Summary Section */}
      <Paper 
        elevation={0}
        sx={{ 
          p: 3, 
          mb: 4, 
          borderRadius: 2,
          backgroundColor: 'primary.main',
          color: 'white',
        }}
      >
        <Grid container spacing={3} alignItems="center">
          <Grid item xs={12} md={8}>
            <Typography variant="h5" gutterBottom fontWeight="bold">
              Rehabilitation Progress
            </Typography>
            <Typography variant="body1" paragraph>
              You have {getActivePlans().length} active rehabilitation plans with {getActiveExercisesCount()} exercises.
              Keep up the good work!
            </Typography>
            <Box sx={{ mt: 2 }}>
              <Box display="flex" justifyContent="space-between" mb={1}>
                <Typography variant="body2">Overall Progress</Typography>
                <Typography variant="body2">{Math.round(getOverallProgress())}%</Typography>
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={getOverallProgress()} 
                sx={{ 
                  height: 10, 
                  borderRadius: 5,
                  backgroundColor: 'rgba(255, 255, 255, 0.3)',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: 'white',
                  }
                }} 
              />
            </Box>
          </Grid>
          <Grid item xs={12} md={4} sx={{ textAlign: 'center' }}>
            <Button 
              variant="contained" 
              size="large"
              color="secondary"
              onClick={() => navigate('/rehab-plans')}
              sx={{ 
                py: 1.5,
                px: 4,
                borderRadius: 2,
                backgroundColor: 'white',
                color: 'primary.main',
                '&:hover': {
                  backgroundColor: 'rgba(255, 255, 255, 0.9)',
                }
              }}
            >
              View All Plans
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {/* Dashboard Widgets */}
      <Grid container spacing={3}>
        {/* Active Plans Widget */}
        <Grid item xs={12} md={6} lg={4}>
          <Card 
            elevation={2}
            sx={{ 
              borderRadius: 2,
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <CardContent sx={{ flexGrow: 1 }}>
              <Box display="flex" alignItems="center" mb={2}>
                <Avatar sx={{ backgroundColor: 'primary.light', mr: 2 }}>
                  <FitnessCenterIcon />
                </Avatar>
                <Typography variant="h6">
                  Active Rehabilitation Plans
                </Typography>
              </Box>
              <Divider sx={{ mb: 2 }} />
              {plansLoading ? (
                <LinearProgress sx={{ my: 3 }} />
              ) : getActivePlans().length > 0 ? (
                <List>
                  {getActivePlans().slice(0, 3).map((plan) => (
                    <ListItem 
                      key={plan._id}
                      secondaryAction={
                        <IconButton edge="end" onClick={() => navigate(`/rehab-plans/${plan._id}`)}>
                          <LaunchIcon fontSize="small" />
                        </IconButton>
                      }
                    >
                      <ListItemIcon>
                        <PendingIcon color="primary" />
                      </ListItemIcon>
                      <ListItemText 
                        primary={plan.name} 
                        secondary={`${plan.exercises?.length || 0} exercises`} 
                      />
                    </ListItem>
                  ))}
                  {getActivePlans().length > 3 && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1, ml: 2 }}>
                      + {getActivePlans().length - 3} more plans
                    </Typography>
                  )}
                </List>
              ) : (
                <Box textAlign="center" py={2}>
                  <Typography variant="body1" color="text.secondary">
                    No active plans found
                  </Typography>
                </Box>
              )}
            </CardContent>
            <CardActions>
              <Button 
                size="small" 
                startIcon={<FitnessCenterIcon />}
                onClick={() => navigate('/rehab-plans')}
                sx={{ ml: 1, mb: 1 }}
              >
                Manage Plans
              </Button>
            </CardActions>
          </Card>
        </Grid>

        {/* Agents Widget */}
        <Grid item xs={12} md={6} lg={4}>
          <Card 
            elevation={2}
            sx={{ 
              borderRadius: 2,
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <CardContent sx={{ flexGrow: 1 }}>
              <Box display="flex" alignItems="center" mb={2}>
                <Avatar sx={{ backgroundColor: 'secondary.light', mr: 2 }}>
                  <PsychologyIcon />
                </Avatar>
                <Typography variant="h6">
                  Rehabilitation Agents
                </Typography>
              </Box>
              <Divider sx={{ mb: 2 }} />
              {agentsLoading ? (
                <LinearProgress sx={{ my: 3 }} />
              ) : agents.length > 0 ? (
                <List>
                  {agents.slice(0, 3).map((agent) => (
                    <ListItem 
                      key={agent._id}
                      secondaryAction={
                        <Button 
                          size="small" 
                          variant="outlined" 
                          onClick={() => navigate(`/agents/${agent._id}`)}
                        >
                          Chat
                        </Button>
                      }
                    >
                      <ListItemIcon>
                        <PsychologyIcon color="secondary" />
                      </ListItemIcon>
                      <ListItemText 
                        primary={agent.name} 
                        secondary={agent.model} 
                      />
                    </ListItem>
                  ))}
                  {agents.length > 3 && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1, ml: 2 }}>
                      + {agents.length - 3} more agents
                    </Typography>
                  )}
                </List>
              ) : (
                <Box textAlign="center" py={2}>
                  <Typography variant="body1" color="text.secondary">
                    No agents found
                  </Typography>
                </Box>
              )}
            </CardContent>
            <CardActions>
              <Button 
                size="small" 
                startIcon={<PsychologyIcon />}
                onClick={() => navigate('/agents')}
                sx={{ ml: 1, mb: 1 }}
              >
                Manage Agents
              </Button>
            </CardActions>
          </Card>
        </Grid>

        {/* Stats Widget */}
        <Grid item xs={12} md={6} lg={4}>
          <Card 
            elevation={2}
            sx={{ 
              borderRadius: 2,
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <CardContent>
              <Box display="flex" alignItems="center" mb={2}>
                <Avatar sx={{ backgroundColor: 'success.light', mr: 2 }}>
                  <TrendingUpIcon />
                </Avatar>
                <Typography variant="h6">
                  Rehabilitation Stats
                </Typography>
              </Box>
              <Divider sx={{ mb: 3 }} />
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Paper 
                    elevation={0} 
                    sx={{ 
                      p: 2, 
                      textAlign: 'center',
                      backgroundColor: 'primary.light',
                      color: 'white',
                      borderRadius: 2
                    }}
                  >
                    <Typography variant="h4" fontWeight="bold">
                      {getActiveExercisesCount()}
                    </Typography>
                    <Typography variant="body2">
                      Active Exercises
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={6}>
                  <Paper 
                    elevation={0} 
                    sx={{ 
                      p: 2, 
                      textAlign: 'center',
                      backgroundColor: 'secondary.light',
                      color: 'white',
                      borderRadius: 2
                    }}
                  >
                    <Typography variant="h4" fontWeight="bold">
                      {getCompletedExercisesCount()}
                    </Typography>
                    <Typography variant="body2">
                      Completed Exercises
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={6}>
                  <Paper 
                    elevation={0} 
                    sx={{ 
                      p: 2, 
                      textAlign: 'center',
                      backgroundColor: 'success.light',
                      color: 'white',
                      borderRadius: 2
                    }}
                  >
                    <Typography variant="h4" fontWeight="bold">
                      {getCompletedPlans().length}
                    </Typography>
                    <Typography variant="body2">
                      Plans Completed
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={6}>
                  <Paper 
                    elevation={0} 
                    sx={{ 
                      p: 2, 
                      textAlign: 'center',
                      backgroundColor: 'info.light',
                      color: 'white',
                      borderRadius: 2
                    }}
                  >
                    <Typography variant="h4" fontWeight="bold">
                      {agents.length}
                    </Typography>
                    <Typography variant="body2">
                      Available Agents
                    </Typography>
                  </Paper>
                </Grid>
              </Grid>
            </CardContent>
            <CardActions>
              <Button 
                size="small" 
                startIcon={<CalendarIcon />}
                onClick={() => navigate('/calendar')}
                sx={{ ml: 1, mb: 1 }}
              >
                View Calendar
              </Button>
            </CardActions>
          </Card>
        </Grid>

        {/* Quick Actions Widget */}
        <Grid item xs={12}>
          <Paper 
            elevation={2}
            sx={{ 
              p: 3, 
              borderRadius: 2 
            }}
          >
            <Typography variant="h6" gutterBottom>
              Quick Actions
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <Grid container spacing={2}>
              <Grid item xs={6} sm={3}>
                <Button 
                  variant="outlined" 
                  size="large"
                  fullWidth
                  startIcon={<FitnessCenterIcon />}
                  onClick={() => navigate('/rehab-plans/new')}
                  sx={{ py: 1.5 }}
                >
                  New Plan
                </Button>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Button 
                  variant="outlined" 
                  size="large"
                  fullWidth
                  startIcon={<PsychologyIcon />}
                  onClick={() => navigate('/agents/new')}
                  sx={{ py: 1.5 }}
                >
                  New Agent
                </Button>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Button 
                  variant="outlined" 
                  size="large"
                  fullWidth
                  startIcon={<CheckCircleIcon />}
                  onClick={() => navigate('/exercises')}
                  sx={{ py: 1.5 }}
                >
                  Exercises
                </Button>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Button 
                  variant="outlined" 
                  size="large"
                  fullWidth
                  startIcon={<PersonIcon />}
                  onClick={() => navigate('/profile')}
                  sx={{ py: 1.5 }}
                >
                  My Profile
                </Button>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard; 