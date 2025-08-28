import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Box,
  Button,
  Container,
  Grid,
  Paper,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
  Divider,
  CircularProgress,
  Card,
  CardMedia,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  FitnessCenter as FitnessCenterIcon,
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  PlayArrow as PlayArrowIcon,
  Close as CloseIcon,
} from '@mui/icons-material';

import { RootState, AppDispatch } from '../../store';
import { fetchExerciseById, deleteExercise } from '../../store/slices/rehabSlice';

// 身体部位映射
const bodyPartMap: Record<string, string> = {
  'shoulder': '肩部',
  'knee': '膝盖',
  'back': '背部',
  'neck': '颈部',
  'ankle': '踝部',
  'wrist': '手腕',
  'hip': '髋部',
  'elbow': '肘部',
};

// 难度级别映射
const difficultyMap: Record<string, string> = {
  'easy': '简单',
  'medium': '中等',
  'hard': '困难',
};

const ExerciseDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  
  const { selectedExercise, loading, error } = useSelector((state: RootState) => state.rehab);
  const { user } = useSelector((state: RootState) => state.auth);
  
  const [videoDialogOpen, setVideoDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  
  // 获取练习详情
  useEffect(() => {
    if (id) {
      dispatch(fetchExerciseById(id));
    }
  }, [dispatch, id]);
  
  // 处理视频对话框
  const handleOpenVideoDialog = () => {
    setVideoDialogOpen(true);
  };
  
  const handleCloseVideoDialog = () => {
    setVideoDialogOpen(false);
  };
  
  // 处理删除对话框
  const handleOpenDeleteDialog = () => {
    setDeleteDialogOpen(true);
  };
  
  const handleCloseDeleteDialog = () => {
    setDeleteDialogOpen(false);
  };
  
  // 确认删除练习
  const handleDeleteExercise = () => {
    if (id) {
      dispatch(deleteExercise(id))
        .then(() => {
          navigate('/app/exercises');
        });
    }
    setDeleteDialogOpen(false);
  };
  
  // 获取难度级别对应的颜色
  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty.toLowerCase()) {
      case 'easy':
        return 'success';
      case 'medium':
        return 'warning';
      case 'hard':
        return 'error';
      default:
        return 'default';
    }
  };
  
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" my={4}>
        <CircularProgress />
      </Box>
    );
  }
  
  if (error) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
        <Button 
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/app/exercises')}
        >
          返回练习列表
        </Button>
      </Container>
    );
  }
  
  if (!selectedExercise) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Alert severity="info" sx={{ mb: 3 }}>
          未找到练习信息
        </Alert>
        <Button 
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/app/exercises')}
        >
          返回练习列表
        </Button>
      </Container>
    );
  }
  
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/app/exercises')}
          sx={{ mb: 2 }}
        >
          返回练习列表
        </Button>
        
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Typography variant="h4" component="h1" gutterBottom>
            {selectedExercise.name}
          </Typography>
          
          {(user?.role === 'doctor' || user?.role === 'admin') && (
            <Box>
              <Button
                variant="outlined"
                color="primary"
                startIcon={<EditIcon />}
                component={Link}
                to={`/app/exercises/edit/${id}`}
                sx={{ mr: 1 }}
              >
                编辑
              </Button>
              <Button
                variant="outlined"
                color="error"
                startIcon={<DeleteIcon />}
                onClick={handleOpenDeleteDialog}
              >
                删除
              </Button>
            </Box>
          )}
        </Box>
      </Box>
      
      <Grid container spacing={3}>
        <Grid item xs={12} md={5}>
          <Paper sx={{ p: 0, overflow: 'hidden' }}>
            {selectedExercise.image_url ? (
              <CardMedia
                component="img"
                sx={{ width: '100%', height: 'auto', maxHeight: 300, objectFit: 'contain' }}
                image={selectedExercise.image_url}
                alt={selectedExercise.name}
              />
            ) : (
              <Box 
                sx={{ 
                  height: 300, 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  bgcolor: 'grey.200'
                }}
              >
                <FitnessCenterIcon fontSize="large" color="disabled" />
              </Box>
            )}
            
            {selectedExercise.video_url && (
              <Box textAlign="center" p={2}>
                <Button
                  variant="contained"
                  color="primary"
                  startIcon={<PlayArrowIcon />}
                  onClick={handleOpenVideoDialog}
                >
                  观看演示视频
                </Button>
              </Box>
            )}
          </Paper>
          
          <Paper sx={{ p: 3, mt: 3 }}>
            <Typography variant="h6" gutterBottom>
              基本信息
            </Typography>
            <Divider sx={{ mb: 2 }} />
            
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Typography variant="subtitle2" color="text.secondary">
                  身体部位
                </Typography>
                <Chip 
                  label={bodyPartMap[selectedExercise.body_part] || selectedExercise.body_part}
                  variant="outlined"
                  size="small"
                  icon={<FitnessCenterIcon />}
                  sx={{ mt: 0.5 }}
                />
              </Grid>
              <Grid item xs={6}>
                <Typography variant="subtitle2" color="text.secondary">
                  难度级别
                </Typography>
                <Chip 
                  label={difficultyMap[selectedExercise.difficulty.toLowerCase()] || selectedExercise.difficulty}
                  color={getDifficultyColor(selectedExercise.difficulty) as any}
                  size="small"
                  sx={{ mt: 0.5 }}
                />
              </Grid>
              <Grid item xs={6}>
                <Typography variant="subtitle2" color="text.secondary">
                  持续时间
                </Typography>
                <Typography variant="body1">
                  {selectedExercise.duration_minutes} 分钟
                </Typography>
              </Grid>
              <Grid item xs={6}>
                <Typography variant="subtitle2" color="text.secondary">
                  组数 x 重复次数
                </Typography>
                <Typography variant="body1">
                  {selectedExercise.sets} 组 x {selectedExercise.repetitions} 次
                </Typography>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
        
        <Grid item xs={12} md={7}>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              详细描述
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <Typography variant="body1" paragraph>
              {selectedExercise.description}
            </Typography>
          </Paper>
          
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              执行步骤
            </Typography>
            <Divider sx={{ mb: 2 }} />
            {selectedExercise.instructions?.length > 0 ? (
              <List>
                {selectedExercise.instructions.map((instruction: string, index: number) => (
                  <ListItem key={index}>
                    <ListItemIcon sx={{ minWidth: 32 }}>
                      <Typography variant="body1" fontWeight="bold">
                        {index + 1}.
                      </Typography>
                    </ListItemIcon>
                    <ListItemText primary={instruction} />
                  </ListItem>
                ))}
              </List>
            ) : (
              <Typography variant="body2" color="text.secondary">
                暂无详细执行步骤
              </Typography>
            )}
          </Paper>
          
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom color="success.main" sx={{ display: 'flex', alignItems: 'center' }}>
                  <CheckCircleIcon sx={{ mr: 1 }} />
                  康复获益
                </Typography>
                <Divider sx={{ mb: 2 }} />
                {selectedExercise.benefits?.length > 0 ? (
                  <List dense>
                    {selectedExercise.benefits.map((benefit: string, index: number) => (
                      <ListItem key={index}>
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          <CheckCircleIcon color="success" fontSize="small" />
                        </ListItemIcon>
                        <ListItemText primary={benefit} />
                      </ListItem>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    暂无康复获益信息
                  </Typography>
                )}
              </Paper>
            </Grid>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom color="error.main" sx={{ display: 'flex', alignItems: 'center' }}>
                  <WarningIcon sx={{ mr: 1 }} />
                  禁忌症
                </Typography>
                <Divider sx={{ mb: 2 }} />
                {selectedExercise.contraindications?.length > 0 ? (
                  <List dense>
                    {selectedExercise.contraindications.map((contraindication: string, index: number) => (
                      <ListItem key={index}>
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          <WarningIcon color="error" fontSize="small" />
                        </ListItemIcon>
                        <ListItemText primary={contraindication} />
                      </ListItem>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    暂无禁忌症信息
                  </Typography>
                )}
              </Paper>
            </Grid>
          </Grid>
        </Grid>
      </Grid>
      
      {/* 视频对话框 */}
      <Dialog
        open={videoDialogOpen}
        onClose={handleCloseVideoDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">{selectedExercise.name} - 演示视频</Typography>
            <IconButton onClick={handleCloseVideoDialog} size="small">
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent>
          {selectedExercise.video_url && (
            <Box sx={{ position: 'relative', paddingTop: '56.25%', width: '100%' }}>
              <iframe
                src={selectedExercise.video_url}
                title={selectedExercise.name}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  border: 'none'
                }}
                allowFullScreen
              />
            </Box>
          )}
        </DialogContent>
      </Dialog>
      
      {/* 删除确认对话框 */}
      <Dialog
        open={deleteDialogOpen}
        onClose={handleCloseDeleteDialog}
      >
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            您确定要删除练习"{selectedExercise.name}"吗？该操作无法撤销。
          </Typography>
        </DialogContent>
        <Box p={2} display="flex" justifyContent="flex-end" gap={1}>
          <Button onClick={handleCloseDeleteDialog}>取消</Button>
          <Button 
            variant="contained" 
            color="error" 
            onClick={handleDeleteExercise}
          >
            删除
          </Button>
        </Box>
      </Dialog>
    </Container>
  );
};

export default ExerciseDetail; 