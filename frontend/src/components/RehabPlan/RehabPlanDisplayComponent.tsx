import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Divider,
  Chip,
  Button,
  IconButton,
  LinearProgress,
  Card,
  CardContent,
  CardActions,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Avatar,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress
} from '@mui/material';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import AssignmentIcon from '@mui/icons-material/Assignment';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import WarningIcon from '@mui/icons-material/Warning';
import TimerIcon from '@mui/icons-material/Timer';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import CheckIcon from '@mui/icons-material/Check';
import VisibilityIcon from '@mui/icons-material/Visibility';
import EditIcon from '@mui/icons-material/Edit';
import { format, parseISO, differenceInDays } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 类型定义
interface Exercise {
  id: string;
  name: string;
  description: string;
  target_area: string;
  instruction: string;
  video_url?: string;
  image_url?: string;
  difficulty: 'easy' | 'medium' | 'hard';
  duration_minutes: number;
  equipment_required: string[];
  contraindications?: string[];
}

interface ExerciseAssignment {
  exercise_id: string;
  exercise: Exercise;
  repetitions: number;
  sets: number;
  duration_minutes?: number;
  notes?: string;
  order: number;
}

interface TrainingSession {
  id: string;
  title: string;
  description?: string;
  exercises: ExerciseAssignment[];
  completed: boolean;
  completion_date?: string;
  completion_feedback?: string;
  scheduled_date: string;
}

interface RehabPlan {
  id: string;
  patient_id: string;
  title: string;
  description: string;
  condition: string;
  status: 'active' | 'completed' | 'pending' | 'canceled';
  start_date: string;
  end_date: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  training_sessions: TrainingSession[];
  notes?: string;
  goals?: string[];
}

interface RehabPlanDisplayComponentProps {
  plan: RehabPlan;
  loading?: boolean;
  error?: string;
  onCompleteSession?: (sessionId: string, feedback: string) => Promise<void>;
  onEditPlan?: () => void;
  onViewExercise?: (exerciseId: string) => void;
}

const RehabPlanDisplayComponent: React.FC<RehabPlanDisplayComponentProps> = ({
  plan,
  loading = false,
  error,
  onCompleteSession,
  onEditPlan,
  onViewExercise
}) => {
  // 状态
  const [selectedSession, setSelectedSession] = React.useState<TrainingSession | null>(null);
  const [completionDialogOpen, setCompletionDialogOpen] = React.useState(false);
  const [completionFeedback, setCompletionFeedback] = React.useState('');
  const [sessionCompleting, setSessionCompleting] = React.useState(false);
  
  // 格式化日期
  const formatDate = (dateString: string) => {
    try {
      return format(parseISO(dateString), 'yyyy年MM月dd日', { locale: zhCN });
    } catch (e) {
      return dateString;
    }
  };
  
  // 计算计划进度百分比
  const calculateProgress = () => {
    if (!plan.training_sessions.length) return 0;
    
    const completedCount = plan.training_sessions.filter(session => session.completed).length;
    return Math.round((completedCount / plan.training_sessions.length) * 100);
  };
  
  // 计算剩余天数
  const calculateRemainingDays = () => {
    try {
      const today = new Date();
      const endDate = parseISO(plan.end_date);
      const days = differenceInDays(endDate, today);
      return days >= 0 ? days : 0;
    } catch (e) {
      return 0;
    }
  };
  
  // 获取状态显示
  const getStatusDisplay = () => {
    const statusMap = {
      active: { label: '进行中', color: 'primary', icon: <TimerIcon /> },
      completed: { label: '已完成', color: 'success', icon: <CheckCircleIcon /> },
      pending: { label: '未开始', color: 'default', icon: <WarningIcon /> },
      canceled: { label: '已取消', color: 'error', icon: <WarningIcon /> }
    };
    
    return statusMap[plan.status] || statusMap.pending;
  };
  
  // 处理完成训练计划点击
  const handleSessionComplete = (session: TrainingSession) => {
    setSelectedSession(session);
    setCompletionFeedback('');
    setCompletionDialogOpen(true);
  };
  
  // 关闭完成对话框
  const handleCloseCompletionDialog = () => {
    setCompletionDialogOpen(false);
    setSelectedSession(null);
  };
  
  // 提交完成反馈
  const handleSubmitCompletion = async () => {
    if (!selectedSession || !onCompleteSession) return;
    
    setSessionCompleting(true);
    try {
      await onCompleteSession(selectedSession.id, completionFeedback);
      handleCloseCompletionDialog();
    } catch (error) {
      console.error('提交训练反馈失败', error);
    } finally {
      setSessionCompleting(false);
    }
  };
  
  // 渲染难度级别
  const renderDifficulty = (difficulty: string) => {
    const difficultyMap = {
      easy: { label: '简单', color: 'success' },
      medium: { label: '中等', color: 'warning' },
      hard: { label: '困难', color: 'error' },
    };
    
    const difficultyInfo = difficultyMap[difficulty as keyof typeof difficultyMap] || difficultyMap.medium;
    
    return (
      <Chip 
        label={difficultyInfo.label}
        size="small"
        color={difficultyInfo.color as any}
      />
    );
  };
  
  // 获取训练部位图标
  const getAreaIcon = (area: string) => {
    // 这里可以根据不同部位返回不同图标
    return <FitnessCenterIcon />;
  };
  
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={3}>
        <CircularProgress />
      </Box>
    );
  }
  
  if (error) {
    return (
      <Box p={3}>
        <Typography color="error">{error}</Typography>
      </Box>
    );
  }
  
  const progress = calculateProgress();
  const remainingDays = calculateRemainingDays();
  const statusDisplay = getStatusDisplay();
  
  return (
    <Box>
      <Paper variant="outlined" sx={{ mb: 3, overflow: 'hidden' }}>
        <Box px={3} py={2} bgcolor="background.default">
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={8}>
              <Typography variant="h5" component="h1" gutterBottom>
                {plan.title}
              </Typography>
              <Box display="flex" alignItems="center" mb={1}>
                <Chip 
                  icon={statusDisplay.icon}
                  label={statusDisplay.label}
                  color={statusDisplay.color as any}
                  size="small"
                  sx={{ mr: 1 }}
                />
                <Typography variant="body2" color="textSecondary">
                  {formatDate(plan.start_date)} - {formatDate(plan.end_date)}
                </Typography>
              </Box>
              {plan.condition && (
                <Typography variant="body2" color="textSecondary">
                  康复情况: {plan.condition}
                </Typography>
              )}
            </Grid>
            <Grid item xs={12} md={4} sx={{ textAlign: { xs: 'left', md: 'right' } }}>
              {onEditPlan && (
                <Button 
                  variant="outlined" 
                  startIcon={<EditIcon />}
                  onClick={onEditPlan}
                  sx={{ ml: { xs: 0, md: 1 } }}
                >
                  编辑计划
                </Button>
              )}
            </Grid>
          </Grid>
        </Box>
        
        <Divider />
        
        <Box p={3}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={4}>
              <Box mb={2}>
                <Typography variant="body2" color="textSecondary" gutterBottom>
                  总体进度
                </Typography>
                <Box display="flex" alignItems="center">
                  <Box flexGrow={1} mr={2}>
                    <LinearProgress 
                      variant="determinate" 
                      value={progress} 
                      sx={{ height: 8, borderRadius: 4 }}
                    />
                  </Box>
                  <Typography variant="body2" fontWeight="bold">
                    {progress}%
                  </Typography>
                </Box>
              </Box>
              
              <Box mb={2}>
                <Typography variant="body2" color="textSecondary" gutterBottom>
                  训练统计
                </Typography>
                <Grid container spacing={1}>
                  <Grid item xs={6}>
                    <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                      <Typography variant="body2" color="textSecondary">
                        总训练次数
                      </Typography>
                      <Typography variant="h6">
                        {plan.training_sessions.length}
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={6}>
                    <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                      <Typography variant="body2" color="textSecondary">
                        已完成
                      </Typography>
                      <Typography variant="h6">
                        {plan.training_sessions.filter(s => s.completed).length}
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={6}>
                    <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                      <Typography variant="body2" color="textSecondary">
                        剩余天数
                      </Typography>
                      <Typography variant="h6">
                        {remainingDays}
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={6}>
                    <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                      <Typography variant="body2" color="textSecondary">
                        待完成
                      </Typography>
                      <Typography variant="h6">
                        {plan.training_sessions.filter(s => !s.completed).length}
                      </Typography>
                    </Paper>
                  </Grid>
                </Grid>
              </Box>
              
              {plan.goals && plan.goals.length > 0 && (
                <Box mb={2}>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    康复目标
                  </Typography>
                  <List dense>
                    {plan.goals.map((goal, index) => (
                      <ListItem key={index} disablePadding>
                        <ListItemAvatar sx={{ minWidth: 36 }}>
                          <CheckCircleIcon color="primary" fontSize="small" />
                        </ListItemAvatar>
                        <ListItemText primary={goal} />
                      </ListItem>
                    ))}
                  </List>
                </Box>
              )}
              
              {plan.description && (
                <Box mb={2}>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    计划描述
                  </Typography>
                  <Typography variant="body2">
                    {plan.description}
                  </Typography>
                </Box>
              )}
              
              {plan.notes && (
                <Box mb={2}>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    康复建议
                  </Typography>
                  <Typography variant="body2">
                    {plan.notes}
                  </Typography>
                </Box>
              )}
            </Grid>
            
            <Grid item xs={12} md={8}>
              <Typography variant="subtitle1" gutterBottom>
                训练计划
              </Typography>
              
              {plan.training_sessions.length === 0 ? (
                <Typography variant="body2" color="textSecondary">
                  暂无训练计划
                </Typography>
              ) : (
                <Box>
                  {plan.training_sessions
                    .sort((a, b) => new Date(a.scheduled_date).getTime() - new Date(b.scheduled_date).getTime())
                    .map(session => (
                      <Accordion key={session.id} variant="outlined" sx={{ mb: 1 }}>
                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                          <Box width="100%" display="flex" alignItems="center" justifyContent="space-between">
                            <Box display="flex" alignItems="center">
                              {session.completed ? (
                                <CheckCircleIcon color="success" sx={{ mr: 1 }} />
                              ) : (
                                <AssignmentIcon color="primary" sx={{ mr: 1 }} />
                              )}
                              <Box>
                                <Typography variant="body1">
                                  {session.title}
                                </Typography>
                                <Typography variant="body2" color="textSecondary">
                                  计划日期: {formatDate(session.scheduled_date)}
                                </Typography>
                              </Box>
                            </Box>
                            <Box>
                              <Chip 
                                label={session.completed ? '已完成' : '待完成'} 
                                color={session.completed ? 'success' : 'default'}
                                size="small"
                              />
                            </Box>
                          </Box>
                        </AccordionSummary>
                        <AccordionDetails>
                          {session.description && (
                            <Typography variant="body2" paragraph>
                              {session.description}
                            </Typography>
                          )}
                          
                          <Typography variant="subtitle2" gutterBottom>
                            训练动作 ({session.exercises.length})
                          </Typography>
                          
                          <Grid container spacing={2}>
                            {session.exercises
                              .sort((a, b) => a.order - b.order)
                              .map(assignment => (
                                <Grid item xs={12} md={6} key={assignment.exercise_id}>
                                  <Card variant="outlined">
                                    <CardContent sx={{ pb: 1 }}>
                                      <Box display="flex" alignItems="center" mb={1}>
                                        <Avatar sx={{ bgcolor: 'primary.main', mr: 1.5 }}>
                                          {getAreaIcon(assignment.exercise.target_area)}
                                        </Avatar>
                                        <Box>
                                          <Typography variant="body1">
                                            {assignment.exercise.name}
                                          </Typography>
                                          <Box display="flex" alignItems="center">
                                            <Typography variant="caption" color="textSecondary" sx={{ mr: 1 }}>
                                              {assignment.exercise.target_area}
                                            </Typography>
                                            {renderDifficulty(assignment.exercise.difficulty)}
                                          </Box>
                                        </Box>
                                      </Box>
                                      
                                      <Divider sx={{ my: 1 }} />
                                      
                                      <Grid container spacing={1}>
                                        <Grid item xs={6}>
                                          <Typography variant="caption" color="textSecondary">
                                            组数
                                          </Typography>
                                          <Typography variant="body2" fontWeight="medium">
                                            {assignment.sets} 组
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={6}>
                                          <Typography variant="caption" color="textSecondary">
                                            每组次数
                                          </Typography>
                                          <Typography variant="body2" fontWeight="medium">
                                            {assignment.repetitions} 次
                                          </Typography>
                                        </Grid>
                                        {assignment.duration_minutes && (
                                          <Grid item xs={6}>
                                            <Typography variant="caption" color="textSecondary">
                                              时长
                                            </Typography>
                                            <Typography variant="body2" fontWeight="medium">
                                              {assignment.duration_minutes} 分钟
                                            </Typography>
                                          </Grid>
                                        )}
                                      </Grid>
                                      
                                      {assignment.notes && (
                                        <Typography variant="body2" sx={{ mt: 1 }}>
                                          {assignment.notes}
                                        </Typography>
                                      )}
                                    </CardContent>
                                    <CardActions sx={{ pt: 0, pb: 1 }}>
                                      {onViewExercise && (
                                        <Button 
                                          size="small" 
                                          startIcon={<VisibilityIcon />}
                                          onClick={() => onViewExercise(assignment.exercise_id)}
                                        >
                                          查看详情
                                        </Button>
                                      )}
                                    </CardActions>
                                  </Card>
                                </Grid>
                              ))}
                          </Grid>
                          
                          {session.completion_feedback && session.completed && (
                            <Box mt={2}>
                              <Typography variant="subtitle2" gutterBottom>
                                训练反馈
                              </Typography>
                              <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
                                <Typography variant="body2">
                                  {session.completion_feedback}
                                </Typography>
                                <Typography variant="caption" color="textSecondary" mt={0.5} display="block">
                                  完成于 {session.completion_date ? formatDate(session.completion_date) : '未知时间'}
                                </Typography>
                              </Paper>
                            </Box>
                          )}
                          
                          {!session.completed && plan.status === 'active' && onCompleteSession && (
                            <Box mt={2} display="flex" justifyContent="flex-end">
                              <Button
                                variant="contained"
                                color="primary"
                                startIcon={<CheckIcon />}
                                onClick={() => handleSessionComplete(session)}
                              >
                                标记为已完成
                              </Button>
                            </Box>
                          )}
                        </AccordionDetails>
                      </Accordion>
                    ))}
                </Box>
              )}
            </Grid>
          </Grid>
        </Box>
      </Paper>
      
      {/* 完成训练对话框 */}
      <Dialog
        open={completionDialogOpen}
        onClose={handleCloseCompletionDialog}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          完成训练: {selectedSession?.title}
        </DialogTitle>
        <DialogContent>
          <Box mt={1}>
            <Typography variant="body2" gutterBottom>
              请填写您的训练反馈，包括感受、遇到的问题或改进建议等。
            </Typography>
            <textarea
              style={{
                width: '100%',
                minHeight: '120px',
                padding: '12px',
                border: '1px solid #ddd',
                borderRadius: '4px',
                marginTop: '8px',
                fontFamily: 'inherit',
                fontSize: '14px',
                resize: 'vertical'
              }}
              value={completionFeedback}
              onChange={(e) => setCompletionFeedback(e.target.value)}
              placeholder="请输入您的训练反馈..."
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseCompletionDialog}>取消</Button>
          <Button 
            variant="contained" 
            color="primary"
            onClick={handleSubmitCompletion}
            disabled={sessionCompleting}
            endIcon={sessionCompleting ? <CircularProgress size={20} /> : undefined}
          >
            提交
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default RehabPlanDisplayComponent; 