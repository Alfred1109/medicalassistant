import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActions,
  Divider,
  Chip,
  List,
  ListItem,
  ListItemText,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  LinearProgress,
  Alert,
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Visibility as VisibilityIcon,
  CalendarToday as CalendarIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { AppDispatch, RootState } from '../store';
import { fetchRehabPlans, createRehabPlan, updateRehabPlan, deleteRehabPlan } from '../store/slices/rehabSlice';
import ExerciseRecommendation from '../components/Rehabilitation/ExerciseRecommendation';

const RehabPlanPage: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { plans, loading, error } = useSelector((state: RootState) => state.rehab);
  const { user } = useSelector((state: RootState) => state.auth);

  const [openDialog, setOpenDialog] = useState(false);
  const [showRecommendations, setShowRecommendations] = useState(false);
  const [currentPlan, setCurrentPlan] = useState<any>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    duration: 4,
    frequency: 3,
    targetBodyPart: '',
    condition: '',
    goal: '',
  });

  useEffect(() => {
    dispatch(fetchRehabPlans());
  }, [dispatch]);

  const handleOpenDialog = (plan?: any) => {
    if (plan) {
      setFormData({
        name: plan.name,
        description: plan.description,
        duration: plan.duration || 4,
        frequency: plan.frequency || 3,
        targetBodyPart: plan.targetBodyPart || '',
        condition: plan.condition || '',
        goal: plan.goal || '',
      });
      setCurrentPlan(plan);
    } else {
      setFormData({
        name: '',
        description: '',
        duration: 4,
        frequency: 3,
        targetBodyPart: '',
        condition: '',
        goal: '',
      });
      setCurrentPlan(null);
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | { name?: string; value: unknown }>) => {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name as string]: value,
    });
  };

  const handleSubmit = async () => {
    try {
      if (currentPlan) {
        await dispatch(updateRehabPlan({
          id: currentPlan._id,
          planData: formData,
        }));
      } else {
        await dispatch(createRehabPlan(formData));
      }
      handleCloseDialog();
    } catch (error) {
      console.error('Error saving plan:', error);
    }
  };

  const handleDeletePlan = async (planId: string) => {
    if (window.confirm('Are you sure you want to delete this rehabilitation plan?')) {
      try {
        await dispatch(deleteRehabPlan(planId));
      } catch (error) {
        console.error('Error deleting plan:', error);
      }
    }
  };

  const handleViewPlanDetail = (planId: string) => {
    navigate(`/rehab-plans/${planId}`);
  };

  const calculateProgress = (plan: any) => {
    if (!plan.exercises || plan.exercises.length === 0) return 0;
    
    const completedExercises = plan.exercises.filter((ex: any) => ex.completed).length;
    return (completedExercises / plan.exercises.length) * 100;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1">
          Rehabilitation Plans
        </Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={() => dispatch(fetchRehabPlans())}
            sx={{ mr: 2 }}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => handleOpenDialog()}
          >
            New Plan
          </Button>
        </Box>
      </Box>

      {loading && <LinearProgress sx={{ mb: 2 }} />}
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {!loading && plans.length === 0 && (
        <Box textAlign="center" py={5}>
          <Typography variant="h6" color="textSecondary" gutterBottom>
            No rehabilitation plans found
          </Typography>
          <Button 
            variant="contained" 
            startIcon={<AddIcon />} 
            onClick={() => handleOpenDialog()}
            sx={{ mt: 2 }}
          >
            Create your first plan
          </Button>
        </Box>
      )}

      <Grid container spacing={3}>
        {plans.map((plan) => (
          <Grid item xs={12} md={6} lg={4} key={plan._id}>
            <Card 
              elevation={2}
              sx={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                transition: 'transform 0.2s',
                '&:hover': {
                  transform: 'translateY(-5px)',
                  boxShadow: 6,
                },
              }}
            >
              <CardContent sx={{ flexGrow: 1 }}>
                <Typography variant="h5" component="h2" gutterBottom>
                  {plan.name}
                </Typography>
                
                <Box display="flex" alignItems="center" mb={1}>
                  <CalendarIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} />
                  <Typography variant="body2" color="text.secondary">
                    Created: {formatDate(plan.createdAt)}
                  </Typography>
                </Box>
                
                <Typography variant="body1" paragraph>
                  {plan.description}
                </Typography>
                
                <Box mb={2}>
                  <Chip 
                    label={`Duration: ${plan.duration} weeks`} 
                    size="small" 
                    sx={{ mr: 1, mb: 1 }} 
                  />
                  <Chip 
                    label={`Frequency: ${plan.frequency}x weekly`} 
                    size="small" 
                    sx={{ mr: 1, mb: 1 }} 
                  />
                  {plan.targetBodyPart && (
                    <Chip 
                      label={`Target: ${plan.targetBodyPart}`} 
                      size="small" 
                      sx={{ mr: 1, mb: 1 }} 
                    />
                  )}
                  {plan.condition && (
                    <Chip 
                      label={`Condition: ${plan.condition}`} 
                      size="small" 
                      sx={{ mr: 1, mb: 1 }} 
                    />
                  )}
                </Box>
                
                <Divider sx={{ mb: 2 }} />
                
                <Typography variant="subtitle2" gutterBottom>
                  Exercises ({plan.exercises?.length || 0})
                </Typography>
                
                {plan.exercises && plan.exercises.length > 0 ? (
                  <>
                    <List dense sx={{ mb: 2 }}>
                      {plan.exercises.slice(0, 3).map((exercise: any) => (
                        <ListItem key={exercise._id || exercise.id}>
                          <ListItemText 
                            primary={exercise.name}
                            secondary={`${exercise.sets || 3} sets × ${exercise.reps || 10} reps`}
                          />
                        </ListItem>
                      ))}
                      {plan.exercises.length > 3 && (
                        <ListItem>
                          <ListItemText 
                            primary={`+ ${plan.exercises.length - 3} more exercises`}
                            primaryTypographyProps={{ color: 'text.secondary', variant: 'body2' }}
                          />
                        </ListItem>
                      )}
                    </List>
                    
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        Progress
                      </Typography>
                      <LinearProgress 
                        variant="determinate" 
                        value={calculateProgress(plan)} 
                        sx={{ height: 8, borderRadius: 1 }}
                      />
                      <Typography variant="caption" color="text.secondary" align="right" display="block" sx={{ mt: 0.5 }}>
                        {`${Math.round(calculateProgress(plan))}%`}
                      </Typography>
                    </Box>
                  </>
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    No exercises added yet
                  </Typography>
                )}
              </CardContent>
              
              <CardActions sx={{ justifyContent: 'space-between', px: 2, pb: 2 }}>
                <Button
                  size="small"
                  startIcon={<VisibilityIcon />}
                  onClick={() => handleViewPlanDetail(plan._id)}
                >
                  View Details
                </Button>
                <Box>
                  <IconButton 
                    size="small" 
                    onClick={() => handleOpenDialog(plan)}
                    sx={{ mr: 1 }}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton 
                    size="small" 
                    onClick={() => handleDeletePlan(plan._id)}
                    color="error"
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Box>
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Create/Edit Plan Dialog */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {currentPlan ? 'Edit Rehabilitation Plan' : 'Create New Rehabilitation Plan'}
        </DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                name="name"
                label="Plan Name"
                value={formData.name}
                onChange={handleInputChange}
                fullWidth
                required
                margin="normal"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                name="description"
                label="Description"
                value={formData.description}
                onChange={handleInputChange}
                fullWidth
                multiline
                rows={3}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                name="duration"
                label="Duration (weeks)"
                value={formData.duration}
                onChange={handleInputChange}
                type="number"
                fullWidth
                margin="normal"
                InputProps={{ inputProps: { min: 1, max: 52 } }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                name="frequency"
                label="Frequency (per week)"
                value={formData.frequency}
                onChange={handleInputChange}
                type="number"
                fullWidth
                margin="normal"
                InputProps={{ inputProps: { min: 1, max: 7 } }}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                name="targetBodyPart"
                label="Target Body Part"
                value={formData.targetBodyPart}
                onChange={handleInputChange}
                fullWidth
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                name="condition"
                label="Condition"
                value={formData.condition}
                onChange={handleInputChange}
                fullWidth
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                name="goal"
                label="Goal"
                value={formData.goal}
                onChange={handleInputChange}
                fullWidth
                margin="normal"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
          >
            {currentPlan ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Exercise Recommendations Dialog */}
      <Dialog 
        open={showRecommendations} 
        onClose={() => setShowRecommendations(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Exercise Recommendations</DialogTitle>
        <DialogContent>
          <ExerciseRecommendation 
            onAddExercises={(exercises) => {
              console.log('Added exercises:', exercises);
              setShowRecommendations(false);
            }} 
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowRecommendations(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default RehabPlanPage; 