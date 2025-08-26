import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Divider,
  Grid,
  LinearProgress,
  Chip,
  Paper,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Tooltip,
  IconButton,
  Button,
} from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import TrendingFlatIcon from '@mui/icons-material/TrendingFlat';
import InsertChartIcon from '@mui/icons-material/InsertChart';
import SportsScoreIcon from '@mui/icons-material/SportsScore';
import ScheduleIcon from '@mui/icons-material/Schedule';
import InfoIcon from '@mui/icons-material/Info';
import DownloadIcon from '@mui/icons-material/Download';
import PrintIcon from '@mui/icons-material/Print';
import { format, differenceInDays, addDays, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { Exercise, RehabPlan } from '../../types/rehab';

// 进度评估相关类型定义
interface ProgressMetric {
  name: string;
  value: number;
  target: number;
  unit: string;
  trend: 'up' | 'down' | 'flat';
  lastValue?: number;
}

interface WeeklyProgress {
  week: number;
  completionRate: number;
  exerciseCount: number;
  painLevel?: number;
  improvementRate?: number;
}

interface RehabProgressEvaluationProps {
  plan: RehabPlan;
  loading?: boolean;
}

const RehabProgressEvaluation: React.FC<RehabProgressEvaluationProps> = ({ plan, loading = false }) => {
  // 模拟计算康复进度数据
  const calculateProgressMetrics = (plan: RehabPlan): ProgressMetric[] => {
    // 在实际应用中，这些数据应该从后端API获取或基于真实数据计算
    return [
      {
        name: '总体完成率',
        value: calculateCompletionRate(plan),
        target: 100,
        unit: '%',
        trend: 'up',
        lastValue: calculateCompletionRate(plan) - 5,
      },
      {
        name: '训练频率',
        value: calculateTrainingFrequency(plan),
        target: 7,
        unit: '次/周',
        trend: 'up',
        lastValue: calculateTrainingFrequency(plan) - 1,
      },
      {
        name: '平均疼痛指数',
        value: 3.2,
        target: 0,
        unit: '级',
        trend: 'down',
        lastValue: 4.5,
      },
      {
        name: '活动能力提升',
        value: 15,
        target: 50,
        unit: '%',
        trend: 'up',
        lastValue: 10,
      },
    ];
  };

  // 计算完成率
  const calculateCompletionRate = (plan: RehabPlan): number => {
    if (!plan.exercises || plan.exercises.length === 0) return 0;
    
    const completedExercises = plan.exercises.filter(ex => ex.completed).length;
    return Math.round((completedExercises / plan.exercises.length) * 100);
  };

  // 计算训练频率 (每周平均次数)
  const calculateTrainingFrequency = (plan: RehabPlan): number => {
    if (!plan.exercises || plan.exercises.length === 0) return 0;
    
    try {
      const startDate = parseISO(plan.startDate);
      const endDate = plan.endDate ? parseISO(plan.endDate) : new Date();
      const totalDays = differenceInDays(endDate, startDate) + 1;
      const totalWeeks = Math.max(1, Math.ceil(totalDays / 7));
      return Math.round((plan.exercises.length / totalWeeks) * 10) / 10; // 保留一位小数
    } catch (e) {
      console.error("Date calculation error:", e);
      return 0;
    }
  };

  // 模拟每周进度数据
  const generateWeeklyProgress = (plan: RehabPlan): WeeklyProgress[] => {
    // 在实际应用中，这些数据应该从后端API获取
    const weeks = [];
    let startDate;
    try {
      startDate = parseISO(plan.startDate);
    } catch (e) {
      console.error("Invalid date format:", e);
      startDate = new Date();
    }
    
    const totalWeeks = 4; // 假设展示4周数据
    
    for (let i = 0; i < totalWeeks; i++) {
      weeks.push({
        week: i + 1,
        completionRate: Math.min(100, 55 + i * 15 + Math.floor(Math.random() * 10)),
        exerciseCount: 6 + Math.floor(Math.random() * 3),
        painLevel: Math.max(1, 5 - i * 0.8 - Math.random()),
        improvementRate: i * 7 + 5 + Math.floor(Math.random() * 5),
      });
    }
    
    return weeks;
  };

  // 计算剩余天数
  const calculateRemainingDays = (plan: RehabPlan): number => {
    if (!plan.endDate) return 0;
    
    try {
      const today = new Date();
      const endDate = parseISO(plan.endDate);
      const days = differenceInDays(endDate, today);
      return days >= 0 ? days : 0;
    } catch (e) {
      console.error("Date calculation error:", e);
      return 0;
    }
  };

  // 格式化日期
  const formatDate = (dateString: string): string => {
    try {
      return format(parseISO(dateString), 'yyyy年MM月dd日', { locale: zhCN });
    } catch (e) {
      return dateString;
    }
  };

  // 渲染趋势图标
  const renderTrendIcon = (trend: 'up' | 'down' | 'flat', isPositive: boolean = true) => {
    const color = isPositive 
      ? (trend === 'up' ? 'success.main' : trend === 'down' ? 'error.main' : 'warning.main')
      : (trend === 'down' ? 'success.main' : trend === 'up' ? 'error.main' : 'warning.main');
      
    return (
      <Box component="span" sx={{ color, display: 'inline-flex', alignItems: 'center', ml: 1 }}>
        {trend === 'up' && <TrendingUpIcon fontSize="small" />}
        {trend === 'down' && <TrendingDownIcon fontSize="small" />}
        {trend === 'flat' && <TrendingFlatIcon fontSize="small" />}
      </Box>
    );
  };

  // 计算指标
  const progressMetrics = calculateProgressMetrics(plan);
  const weeklyProgress = generateWeeklyProgress(plan);
  const remainingDays = calculateRemainingDays(plan);

  return (
    <Box>
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6" component="h2">
              康复进度评估
            </Typography>
            <Box>
              <Tooltip title="导出评估报告">
                <IconButton size="small" sx={{ mr: 1 }}>
                  <DownloadIcon />
                </IconButton>
              </Tooltip>
              <Tooltip title="打印评估报告">
                <IconButton size="small">
                  <PrintIcon />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>

          <Box mb={3}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={0} variant="outlined" sx={{ p: 2, height: '100%' }}>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    康复开始日期
                  </Typography>
                  <Typography variant="body1" fontWeight="medium">
                    {formatDate(plan.startDate)}
                  </Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={0} variant="outlined" sx={{ p: 2, height: '100%' }}>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    预计结束日期
                  </Typography>
                  <Typography variant="body1" fontWeight="medium">
                    {plan.endDate ? formatDate(plan.endDate) : "未设定"}
                  </Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={0} variant="outlined" sx={{ p: 2, height: '100%' }}>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    剩余天数
                  </Typography>
                  <Typography variant="body1" fontWeight="medium">
                    {remainingDays} 天
                  </Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={0} variant="outlined" sx={{ p: 2, height: '100%', bgcolor: 'primary.light', borderColor: 'primary.main' }}>
                  <Typography variant="body2" color="primary.contrastText" gutterBottom>
                    总体完成度
                  </Typography>
                  <Box display="flex" alignItems="center">
                    <Typography variant="h5" fontWeight="bold" color="primary.contrastText">
                      {Math.round(calculateCompletionRate(plan))}%
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={calculateCompletionRate(plan)} 
                    sx={{ height: 8, borderRadius: 4, mt: 1, bgcolor: 'rgba(255,255,255,0.3)' }}
                  />
                </Paper>
              </Grid>
            </Grid>
          </Box>

          <Typography variant="subtitle2" gutterBottom>
            核心康复指标
          </Typography>
          <Grid container spacing={2} sx={{ mb: 3 }}>
            {progressMetrics.map((metric, index) => (
              <Grid item xs={12} sm={6} md={3} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                    <Typography variant="body2" color="textSecondary" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                      {metric.name}
                      <Tooltip title={`目标值: ${metric.target}${metric.unit}`}>
                        <InfoIcon fontSize="small" sx={{ ml: 0.5, fontSize: '0.9rem', color: 'text.secondary' }} />
                      </Tooltip>
                    </Typography>
                    <Box display="flex" alignItems="baseline">
                      <Typography variant="h6" component="span" fontWeight="medium">
                        {metric.value}{metric.unit}
                      </Typography>
                      {metric.lastValue && (
                        <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                          {metric.trend === 'up' && `+${(metric.value - metric.lastValue).toFixed(1)}`}
                          {metric.trend === 'down' && `-${(metric.lastValue - metric.value).toFixed(1)}`}
                          {metric.trend === 'flat' && `±0`}
                          {renderTrendIcon(
                            metric.trend, 
                            (metric.name === '平均疼痛指数') ? metric.trend === 'down' : metric.trend === 'up'
                          )}
                        </Typography>
                      )}
                    </Box>
                    <LinearProgress 
                      variant="determinate" 
                      value={(metric.value / metric.target) * 100} 
                      sx={{ height: 6, borderRadius: 3, mt: 1 }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Typography variant="subtitle2" gutterBottom>
            每周康复进展
          </Typography>
          <Grid container spacing={2}>
            {weeklyProgress.map((week, index) => (
              <Grid item xs={12} sm={6} lg={3} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                    <Typography variant="body2" color="primary" fontWeight="medium" gutterBottom>
                      第{week.week}周
                    </Typography>
                    <List dense disablePadding>
                      <ListItem disablePadding sx={{ mb: 0.5 }}>
                        <ListItemIcon sx={{ minWidth: 30 }}>
                          <SportsScoreIcon fontSize="small" color="success" />
                        </ListItemIcon>
                        <ListItemText 
                          primary={`完成率: ${week.completionRate}%`}
                          primaryTypographyProps={{ variant: 'body2' }}
                        />
                      </ListItem>
                      <ListItem disablePadding sx={{ mb: 0.5 }}>
                        <ListItemIcon sx={{ minWidth: 30 }}>
                          <ScheduleIcon fontSize="small" color="info" />
                        </ListItemIcon>
                        <ListItemText 
                          primary={`训练次数: ${week.exerciseCount}次`}
                          primaryTypographyProps={{ variant: 'body2' }}
                        />
                      </ListItem>
                      {week.painLevel && (
                        <ListItem disablePadding sx={{ mb: 0.5 }}>
                          <ListItemIcon sx={{ minWidth: 30 }}>
                            <TrendingDownIcon fontSize="small" color="error" />
                          </ListItemIcon>
                          <ListItemText 
                            primary={`疼痛指数: ${week.painLevel.toFixed(1)}`}
                            primaryTypographyProps={{ variant: 'body2' }}
                          />
                        </ListItem>
                      )}
                      {week.improvementRate && (
                        <ListItem disablePadding>
                          <ListItemIcon sx={{ minWidth: 30 }}>
                            <TrendingUpIcon fontSize="small" color="success" />
                          </ListItemIcon>
                          <ListItemText 
                            primary={`提升率: ${week.improvementRate}%`}
                            primaryTypographyProps={{ variant: 'body2' }}
                          />
                        </ListItem>
                      )}
                    </List>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Box mt={3} display="flex" justifyContent="center">
            <Button
              variant="outlined"
              color="primary"
              startIcon={<InsertChartIcon />}
            >
              查看详细进度分析
            </Button>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
};

export default RehabProgressEvaluation; 