import React from 'react';
import { 
  Box, 
  Typography, 
  Paper, 
  Grid, 
  Divider, 
  CircularProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import PendingIcon from '@mui/icons-material/Pending';
import EventIcon from '@mui/icons-material/Event';
import RepeatIcon from '@mui/icons-material/Repeat';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import { RehabPlan } from './index';
import { formatDate, calculateElapsedDays, calculateRemainingDays, calculateCompletionRate } from './utils';

interface TrainingProgressProps {
  plan: RehabPlan;
}

/**
 * 康复评估报告中的训练进度组件，展示康复训练的完成情况
 */
const TrainingProgress: React.FC<TrainingProgressProps> = ({
  plan
}) => {
  const completionRate = calculateCompletionRate(plan);
  const elapsedDays = calculateElapsedDays(plan.startDate);
  const remainingDays = calculateRemainingDays(plan.endDate);
  
  // 计算不同状态的练习数量
  const completedExercises = plan.exercises.filter(ex => ex.completed).length;
  const pendingExercises = plan.exercises.length - completedExercises;
  
  return (
    <Paper 
      elevation={0} 
      sx={{ 
        p: 3, 
        mb: 3,
        border: '1px solid #eee',
        '@media print': { border: 'none', p: 0, boxShadow: 'none' }
      }}
    >
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold' }}>
        康复训练进度
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Box sx={{ 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center',
            justifyContent: 'center',
            p: 2
          }}>
            <Box sx={{ position: 'relative', display: 'inline-flex', mb: 2 }}>
              <CircularProgress 
                variant="determinate" 
                value={completionRate} 
                size={120}
                thickness={5}
                color="primary"
              />
              <Box
                sx={{
                  top: 0,
                  left: 0,
                  bottom: 0,
                  right: 0,
                  position: 'absolute',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Typography
                  variant="h4"
                  component="div"
                  color="primary"
                  fontWeight="bold"
                >
                  {`${completionRate}%`}
                </Typography>
              </Box>
            </Box>
            <Typography variant="h6" gutterBottom align="center">
              总体完成率
            </Typography>
            <Box sx={{ mt: 1, display: 'flex', gap: 1, justifyContent: 'center', flexWrap: 'wrap' }}>
              <Chip 
                icon={<CheckCircleIcon />} 
                label={`已完成: ${completedExercises}`} 
                color="success" 
                size="small"
              />
              <Chip 
                icon={<PendingIcon />} 
                label={`待完成: ${pendingExercises}`} 
                color="warning" 
                size="small"
              />
            </Box>
          </Box>
        </Grid>
        
        <Grid item xs={12} md={8}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1 }}>
            计划信息
          </Typography>
          
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <EventIcon color="primary" fontSize="small" sx={{ mr: 1 }} />
                <Typography variant="body2">
                  开始日期: {formatDate(plan.startDate)}
                </Typography>
              </Box>
              
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <EventIcon color="primary" fontSize="small" sx={{ mr: 1 }} />
                <Typography variant="body2">
                  结束日期: {plan.endDate ? formatDate(plan.endDate) : '未设定'}
                </Typography>
              </Box>
              
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <AccessTimeIcon color="primary" fontSize="small" sx={{ mr: 1 }} />
                <Typography variant="body2">
                  已进行 {elapsedDays} 天
                </Typography>
              </Box>
              
              {plan.endDate && (
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                  <AccessTimeIcon color="primary" fontSize="small" sx={{ mr: 1 }} />
                  <Typography variant="body2">
                    剩余 {remainingDays} 天
                  </Typography>
                </Box>
              )}
            </Grid>
            
            <Grid item xs={12} sm={6}>
              <Box sx={{ display: 'flex', mb: 1 }}>
                <Typography variant="body2" color="text.secondary" sx={{ width: '80px', flexShrink: 0 }}>
                  计划状态:
                </Typography>
                <Chip 
                  label={plan.status.toUpperCase()} 
                  color={
                    plan.status === 'active' ? 'success' :
                    plan.status === 'completed' ? 'primary' :
                    plan.status === 'paused' ? 'warning' : 'error'
                  }
                  size="small"
                />
              </Box>
              
              <Box sx={{ display: 'flex', mb: 1 }}>
                <Typography variant="body2" color="text.secondary" sx={{ width: '80px', flexShrink: 0 }}>
                  训练项目:
                </Typography>
                <Typography variant="body2" fontWeight="medium">
                  {plan.exercises.length} 项
                </Typography>
              </Box>
              
              <Box sx={{ display: 'flex', mb: 1 }}>
                <Typography variant="body2" color="text.secondary" sx={{ width: '80px', flexShrink: 0 }}>
                  创建者:
                </Typography>
                <Typography variant="body2" fontWeight="medium">
                  {plan.createdBy}
                </Typography>
              </Box>
            </Grid>
          </Grid>
          
          <Divider sx={{ my: 2 }} />
          
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1 }}>
            目标情况
          </Typography>
          
          <Box sx={{ mb: 2 }}>
            {plan.targetConditions.map((target, index) => (
              <Chip 
                key={index}
                label={target}
                size="small"
                sx={{ mr: 1, mb: 1 }}
              />
            ))}
          </Box>
        </Grid>
      </Grid>
      
      <Divider sx={{ my: 2 }} />
      
      <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1 }}>
        训练项目完成情况
      </Typography>
      
      <List sx={{ 
        bgcolor: 'background.paper',
        border: '1px solid #eee',
        borderRadius: 1,
        maxHeight: '300px',
        overflow: 'auto'
      }}>
        {plan.exercises.map((exercise, index) => (
          <ListItem key={index} divider={index < plan.exercises.length - 1}>
            <ListItemIcon>
              {exercise.completed ? (
                <CheckCircleIcon color="success" />
              ) : (
                <PendingIcon color="warning" />
              )}
            </ListItemIcon>
            <ListItemText
              primary={
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography variant="subtitle2">{exercise.name}</Typography>
                  <Chip 
                    label={`${exercise.progress}%`}
                    size="small"
                    color={exercise.completed ? "success" : "primary"}
                  />
                </Box>
              }
              secondary={
                <Box sx={{ mt: 0.5 }}>
                  {exercise.description && (
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      {exercise.description}
                    </Typography>
                  )}
                  <Grid container spacing={1}>
                    <Grid item>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <RepeatIcon fontSize="small" sx={{ fontSize: '1rem', mr: 0.5 }} />
                        <Typography variant="body2" color="text.secondary">
                          {`${exercise.sets} 组 × ${exercise.repetitions} 次`}
                        </Typography>
                      </Box>
                    </Grid>
                    
                    {exercise.duration && (
                      <Grid item>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <AccessTimeIcon fontSize="small" sx={{ fontSize: '1rem', mr: 0.5 }} />
                          <Typography variant="body2" color="text.secondary">
                            {`${exercise.duration} 分钟`}
                          </Typography>
                        </Box>
                      </Grid>
                    )}
                    
                    {exercise.frequency && exercise.frequency.length > 0 && (
                      <Grid item>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <EventIcon fontSize="small" sx={{ fontSize: '1rem', mr: 0.5 }} />
                          <Typography variant="body2" color="text.secondary">
                            {exercise.frequency.join(', ')}
                          </Typography>
                        </Box>
                      </Grid>
                    )}
                  </Grid>
                </Box>
              }
            />
          </ListItem>
        ))}
      </List>
    </Paper>
  );
};

export default TrainingProgress; 