import { formatAppDate } from '../../utils/dateTime';
import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Alert,
  Grid,
  IconButton,
  LinearProgress,
  Paper,
  Typography,
  useTheme,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import InfoIcon from '@mui/icons-material/Info';

import { AppDispatch, RootState } from '../../store';
import { fetchRehabPlanById, deleteRehabPlan } from '../../store/slices/rehabSlice';
import { Exercise } from '../../types/rehab';
import ExerciseRecommendation from '../../components/Rehabilitation/ExerciseRecommendation';

const RehabPlanDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const theme = useTheme();

  const { selectedPlan, loading } = useSelector((state: RootState) => state.rehab);

  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [showRecommendations, setShowRecommendations] = React.useState(false);

  React.useEffect(() => {
    if (id && id !== 'undefined' && id !== 'null') {
      dispatch(fetchRehabPlanById(id));
    } else {
      navigate('/app/rehab-plans');
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
          navigate('/app/rehab-plans');
        });
    }
    setDeleteDialogOpen(false);
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

  const formatDate = (dateString: string | undefined) => {
    return formatAppDate(dateString, 'dayEn', { empty: 'N/A', invalid: 'Invalid date' });
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
          onClick={() => navigate('/app/rehab-plans')}
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
              onClick={() => navigate(`/app/rehab-plans/edit/${id}`)}
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

      <Alert severity="info" sx={{ my: 2 }} action={<Button color="inherit" component={Link} to="/app/rehab-plans">打开新版方案工作台</Button>}>
        旧方案不再由医护人员登记训练完成。患者执行情况只记录在新版已发布方案的患者自述中。
      </Alert>
      <Box sx={{ pt: 2 }}>
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
                        bgcolor: 'background.paper',
                      }}
                    >
                      <CardContent sx={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        '&:last-child': { pb: 2 }
                      }}>
                        <Box sx={{ flexGrow: 1 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 'medium' }}>
                            {exercise.name}
                          </Typography>

                          <Typography variant="body2" color="text.secondary" paragraph>
                            {exercise.description}
                          </Typography>

                          <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
                            {exercise.body_part && (
                              <Chip
                                key={`bodypart-${exercise.id}`}
                                label={exercise.body_part}
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
      </Box>

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
