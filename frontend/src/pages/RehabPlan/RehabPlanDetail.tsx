import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Grid,
  IconButton,
  LinearProgress,
  Paper,
  Typography,
  useTheme,
  Tab,
  Tabs,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import InfoIcon from '@mui/icons-material/Info';
import AssessmentIcon from '@mui/icons-material/Assessment';

import { AppDispatch, RootState } from '../../store';
import { fetchRehabPlanById, deleteRehabPlan, updateExerciseCompletion } from '../../store/slices/rehabSlice';
import { Exercise } from '../../types/rehab';
import ExerciseRecommendation from '../../components/Rehabilitation/ExerciseRecommendation';
import RehabProgressEvaluation from '../../components/Rehabilitation/RehabProgressEvaluation';

// TabPanel组件用于实现标签页内容切换
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel = (props: TabPanelProps) => {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`rehab-plan-tabpanel-${index}`}
      aria-labelledby={`rehab-plan-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ pt: 2 }}>
          {children}
        </Box>
      )}
    </div>
  );
};

const RehabPlanDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const theme = useTheme();
  
  const { selectedPlan, loading } = useSelector((state: RootState) => state.rehab);
  
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [showRecommendations, setShowRecommendations] = React.useState(false);
  const [tabValue, setTabValue] = React.useState(0);
  
  React.useEffect(() => {
    if (id && id !== 'undefined' && id !== 'null') {
      dispatch(fetchRehabPlanById(id));
    } else {
      navigate('/rehab-plans');
    }
  }, [dispatch, id, navigate]);
  
  const handleDeleteClick = () => {
    setDeleteDialogOpen(true);
  };
  
  const handleDeleteCancel = () => {
    setDeleteDialogOpen(false);
  };
  
  const handleDeleteConfirm = () => {
    if (id) {
      dispatch(deleteRehabPlan(id))
        .unwrap()
        .then(() => {
          navigate('/rehab-plans');
        });
    }
    setDeleteDialogOpen(false);
  };
  
  const handleToggleExerciseCompletion = (exerciseId: string | undefined, completed: boolean) => {
    // 确保计划ID和练习ID都有效
    if (id && exerciseId) {
      dispatch(updateExerciseCompletion({ 
        planId: id, 
        exerciseId, 
        completed: !completed 
      }));
    } else {
      console.error('无法更新练习完成状态: ', 
        !id ? '无效的计划ID' : '无效的练习ID', 
        { planId: id, exerciseId }
      );
    }
  };
  
  const handleAddExercisesClick = () => {
    setShowRecommendations(true);
  };
  
  const handleRecommendationsClose = () => {
    setShowRecommendations(false);
    // Refresh plan data after adding exercises
    if (id) {
      dispatch(fetchRehabPlanById(id));
    }
  };
  
  const handleChangeTab = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };
  
  const getCompletionPercentage = () => {
    if (!selectedPlan) return 0;
    
    const totalExercises = selectedPlan.exercises.length;
    if (totalExercises === 0) return 0;
    
    const completedExercises = selectedPlan.exercises.filter((ex: Exercise) => ex.completed).length;
    return (completedExercises / totalExercises) * 100;
  };
  
  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return 'N/A';
    
    try {
      const date = new Date(dateString);
      // 检查日期是否有效
      if (isNaN(date.getTime())) {
        return 'Invalid date';
      }
      return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      }).format(date);
    } catch (error) {
      console.error('Date formatting error:', error);
      return 'Invalid date';
    }
  };
  
  if (loading || !selectedPlan) {
    return (
      <Box sx={{ width: '100%', mt: 4 }}>
        <LinearProgress />
      </Box>
    );
  }
  
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/rehab-plans')}
          sx={{ mb: 2 }}
        >
          返回康复计划列表
        </Button>
        
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h4" component="h1" gutterBottom>
            {selectedPlan.name}
          </Typography>
          <Box>
            <IconButton 
              color="primary" 
              onClick={() => navigate(`/rehab-plans/edit/${id}`)}
              sx={{ mr: 1 }}
            >
              <EditIcon />
            </IconButton>
            <IconButton color="error" onClick={handleDeleteClick}>
              <DeleteIcon />
            </IconButton>
          </Box>
        </Box>
        
        <Chip 
          label={selectedPlan.status === 'active' ? '进行中' : '已完成'} 
          color={selectedPlan.status === 'active' ? 'success' : 'default'}
          size="small"
        />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          创建时间: {formatDate(selectedPlan.createdAt)}
        </Typography>
      </Box>
      
      <Tabs
        value={tabValue}
        onChange={handleChangeTab}
        aria-label="rehab plan tabs"
        sx={{ borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab 
          icon={<FitnessCenterIcon />} 
          iconPosition="start" 
          label="训练内容" 
          id="rehab-plan-tab-0"
          aria-controls="rehab-plan-tabpanel-0"
        />
        <Tab 
          icon={<AssessmentIcon />} 
          iconPosition="start" 
          label="进度评估" 
          id="rehab-plan-tab-1"
          aria-controls="rehab-plan-tabpanel-1"
        />
      </Tabs>
      
      <TabPanel value={tabValue} index={0}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Card sx={{ mb: 3, borderRadius: 2 }}>
              <CardContent>
                <Typography variant="h6" component="h2" gutterBottom>
                  计划详情
                </Typography>
                <Divider sx={{ mb: 2 }} />
                
                <Typography variant="body1" paragraph>
                  {selectedPlan.description || '暂无描述信息。'}
                </Typography>
                
                <Box sx={{ mt: 3 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    进度
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <LinearProgress 
                      variant="determinate" 
                      value={getCompletionPercentage()} 
                      sx={{ 
                        flexGrow: 1, 
                        mr: 2, 
                        height: 8, 
                        borderRadius: 5 
                      }} 
                    />
                    <Typography variant="body2">
                      {Math.round(getCompletionPercentage())}%
                    </Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    {selectedPlan.exercises.filter((ex: Exercise) => ex.completed).length} / {selectedPlan.exercises.length} 训练已完成
                  </Typography>
                </Box>
              </CardContent>
            </Card>
            
            <Button
              variant="contained"
              color="primary"
              startIcon={<AddIcon />}
              fullWidth
              onClick={handleAddExercisesClick}
              sx={{ mb: 3 }}
            >
              添加训练
            </Button>
          </Grid>
          
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 2, borderRadius: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <FitnessCenterIcon color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6" component="h2">
                  训练内容
                </Typography>
              </Box>
              <Divider sx={{ mb: 2 }} />
              
              {selectedPlan.exercises.length === 0 ? (
                <Box sx={{ py: 4, textAlign: 'center' }}>
                  <Typography variant="body1" color="text.secondary">
                    该计划暂无训练内容。
                  </Typography>
                  <Button
                    variant="outlined"
                    color="primary"
                    startIcon={<AddIcon />}
                    onClick={handleAddExercisesClick}
                    sx={{ mt: 2 }}
                  >
                    添加训练
                  </Button>
                </Box>
              ) : (
                <Box>
                  {selectedPlan.exercises.map((exercise: Exercise) => (
                    <Card 
                      key={exercise.id || exercise._id} 
                      sx={{ 
                        mb: 2, 
                        borderRadius: 1,
                        border: '1px solid',
                        borderColor: 'divider',
                        bgcolor: exercise.completed ? 'success.light' : 'background.paper',
                        opacity: exercise.completed ? 0.8 : 1,
                      }}
                    >
                      <CardContent sx={{ 
                        display: 'flex', 
                        alignItems: 'flex-start',
                        '&:last-child': { pb: 2 } 
                      }}>
                        <Checkbox
                          checked={exercise.completed}
                          onChange={() => handleToggleExerciseCompletion(exercise.id || exercise._id, exercise.completed)}
                          sx={{ mt: -0.5, mr: 1 }}
                        />
                        <Box sx={{ flexGrow: 1 }}>
                          <Typography variant="subtitle1" sx={{ 
                            fontWeight: 'medium',
                            textDecoration: exercise.completed ? 'line-through' : 'none'
                          }}>
                            {exercise.name}
                          </Typography>
                          
                          <Typography variant="body2" color="text.secondary" paragraph>
                            {exercise.description}
                          </Typography>
                          
                          <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
                            {exercise.bodyPart && (
                              <Chip 
                                key={`bodypart-${exercise.id}`}
                                label={exercise.bodyPart} 
                                size="small" 
                                variant="outlined"
                              />
                            )}
                            
                            {exercise.difficulty && (
                              <Chip 
                                key={`difficulty-${exercise.id}`}
                                label={exercise.difficulty} 
                                size="small" 
                                variant="outlined"
                                color={
                                  exercise.difficulty === 'easy' ? 'success' :
                                  exercise.difficulty === 'medium' ? 'warning' : 'error'
                                }
                              />
                            )}
                            
                            {exercise.scheduledDate && (
                              <Chip 
                                key={`scheduled-${exercise.id}`}
                                label={`预定日期: ${formatDate(exercise.scheduledDate)}`}
                                size="small" 
                                variant="outlined"
                                icon={<InfoIcon />}
                              />
                            )}
                          </Box>
                          
                          {(exercise.sets && exercise.sets > 0) && (exercise.repetitions && exercise.repetitions > 0) && (
                            <Typography variant="body2" color="text.primary" sx={{ mt: 1 }}>
                              {exercise.sets} 组 × {exercise.repetitions} 次
                            </Typography>
                          )}
                        </Box>
                      </CardContent>
                    </Card>
                  ))}
                </Box>
              )}
            </Paper>
          </Grid>
        </Grid>
      </TabPanel>
      
      <TabPanel value={tabValue} index={1}>
        {selectedPlan && <RehabProgressEvaluation plan={selectedPlan} />}
      </TabPanel>
      
      {/* 确认删除对话框 */}
      <Dialog
        open={deleteDialogOpen}
        onClose={handleDeleteCancel}
      >
        <DialogTitle>删除康复计划</DialogTitle>
        <DialogContent>
          <DialogContentText>
            确定要删除"{selectedPlan.name}"康复计划吗？此操作无法撤销。
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeleteCancel}>取消</Button>
          <Button onClick={handleDeleteConfirm} color="error" autoFocus>
            删除
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 训练推荐对话框 */}
      <Dialog
        open={showRecommendations}
        onClose={handleRecommendationsClose}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>
          添加训练到计划
        </DialogTitle>
        <DialogContent dividers>
          <ExerciseRecommendation planId={id} onClose={handleRecommendationsClose} />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleRecommendationsClose}>完成</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default RehabPlanDetail; 