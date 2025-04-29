import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Divider,
} from '@mui/material';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';

const Statistics: React.FC = () => {
  // 模拟数据
  const statsData = {
    weeklyProgress: 65,
    monthlyProgress: 72,
    totalTrainingHours: 38,
    averagePainLevel: 2.5,
    exerciseCompletionRate: 85,
    consistencyRate: 78,
  };
  
  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        我的康复数据
      </Typography>
      
      <Grid container spacing={3}>
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <FitnessCenterIcon sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6">
                  训练完成率
                </Typography>
              </Box>
              <Typography variant="h4" color="primary" gutterBottom>
                {statsData.exerciseCompletionRate}%
              </Typography>
              <Typography variant="body2" color="text.secondary">
                您完成了85%的康复训练计划
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <TrendingUpIcon sx={{ color: 'success.main', mr: 1 }} />
                <Typography variant="h6">
                  康复进度
                </Typography>
              </Box>
              <Typography variant="h4" color="success.main" gutterBottom>
                {statsData.monthlyProgress}%
              </Typography>
              <Typography variant="body2" color="text.secondary">
                本月康复总体进度
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <AccessTimeIcon sx={{ color: 'info.main', mr: 1 }} />
                <Typography variant="h6">
                  训练时长
                </Typography>
              </Box>
              <Typography variant="h4" color="info.main" gutterBottom>
                {statsData.totalTrainingHours}小时
              </Typography>
              <Typography variant="body2" color="text.secondary">
                累计训练时长
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <ReportProblemIcon sx={{ color: 'warning.main', mr: 1 }} />
                <Typography variant="h6">
                  平均疼痛指数
                </Typography>
              </Box>
              <Typography variant="h4" color="warning.main" gutterBottom>
                {statsData.averagePainLevel}/10
              </Typography>
              <Typography variant="body2" color="text.secondary">
                近两周平均疼痛水平
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              康复趋势分析
            </Typography>
            <Typography variant="body1" paragraph>
              根据您的数据分析，您的康复进度符合预期。持续训练将有助于更快恢复。
            </Typography>
            <Divider sx={{ my: 2 }} />
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Typography variant="subtitle1" gutterBottom>
                  本周亮点
                </Typography>
                <Typography variant="body2">
                  • 训练完成率提高了5%<br />
                  • 疼痛指数下降了0.8<br />
                  • 完成了所有核心训练项目
                </Typography>
              </Grid>
              <Grid item xs={12} md={4}>
                <Typography variant="subtitle1" gutterBottom>
                  需要改进
                </Typography>
                <Typography variant="body2">
                  • 增加每天的训练时长<br />
                  • 提高训练一致性<br />
                  • 更规律地记录康复数据
                </Typography>
              </Grid>
              <Grid item xs={12} md={4}>
                <Typography variant="subtitle1" gutterBottom>
                  医生建议
                </Typography>
                <Typography variant="body2">
                  • 重点加强右腿肌肉锻炼<br />
                  • 增加平衡训练的频率<br />
                  • 观察并记录疼痛变化
                </Typography>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
        
        <Grid item xs={12}>
          <Paper sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body1">
              更详细的图表分析和数据报告功能将在下一版本中推出，敬请期待。
            </Typography>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Statistics; 