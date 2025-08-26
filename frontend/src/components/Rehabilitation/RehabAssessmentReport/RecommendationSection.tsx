import React from 'react';
import { 
  Box, 
  Typography, 
  Paper, 
  Grid, 
  Divider, 
  Card,
  CardContent,
  List,
  ListItem,
  ListItemIcon,
  ListItemText
} from '@mui/material';
import AssignmentIcon from '@mui/icons-material/Assignment';
import TipsAndUpdatesIcon from '@mui/icons-material/TipsAndUpdates';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import AdjustIcon from '@mui/icons-material/Adjust';
import { Patient, RehabPlan, AssessmentMetric } from './index';

interface RecommendationSectionProps {
  patient: Patient;
  plan: RehabPlan;
  metrics: AssessmentMetric[];
}

/**
 * 康复评估报告中的建议部分组件，基于评估结果提供康复训练建议
 */
const RecommendationSection: React.FC<RecommendationSectionProps> = ({
  patient,
  plan,
  metrics
}) => {
  // 生成建议内容（实际项目中可能来自后端生成或医生手动输入）
  const generateRecommendations = () => {
    // 检查是否有需要关注的指标（进步不明显或下降的指标）
    const concernMetrics = metrics.filter(metric => 
      !metric.isPositiveTrend || metric.improvementPercentage < 0.1
    );
    
    // 根据计划完成情况给出建议
    const completedExercises = plan.exercises.filter(ex => ex.completed).length;
    const completionRate = completedExercises / plan.exercises.length;
    
    const recommendations = [];
    
    // 基于计划完成情况的总体建议
    if (completionRate < 0.3) {
      recommendations.push("当前训练完成度较低，建议加强依从性，按计划完成训练");
    } else if (completionRate < 0.7) {
      recommendations.push("训练完成情况中等，建议保持当前训练节奏，并关注训练质量");
    } else {
      recommendations.push("训练完成情况良好，建议继续保持，并可适当增加训练强度");
    }
    
    // 基于具体指标的建议
    concernMetrics.forEach(metric => {
      if (metric.improvementPercentage < 0) {
        recommendations.push(`${metric.name}指标有所下降，建议调整相关训练方式和强度`);
      } else if (metric.improvementPercentage < 0.05) {
        recommendations.push(`${metric.name}指标进步不明显，建议增加相关训练频次`);
      }
    });
    
    // 基于目标的建议
    if (plan.targetConditions.length > 0) {
      recommendations.push("建议继续针对目标症状进行专项训练");
    }
    
    // 添加一些标准化建议
    recommendations.push("建议保持规律作息，避免过度疲劳");
    recommendations.push("建议均衡饮食，保证足够蛋白质摄入，促进肌肉恢复");
    
    return recommendations;
  };
  
  // 生成康复注意事项
  const generatePrecautions = () => {
    return [
      "训练过程中如感到明显疼痛，应立即停止并咨询医生",
      "避免长时间保持同一姿势，预防继发性损伤",
      "训练前做足热身，训练后做好放松",
      "遵循循序渐进原则，不要急于求成",
      "定期复查，及时调整康复计划"
    ];
  };
  
  // 生成后续计划建议
  const generateNextSteps = () => {
    // 检查整体进步情况
    const overallImprovement = metrics.reduce((acc, metric) => 
      acc + metric.improvementPercentage, 0
    ) / metrics.length;
    
    if (overallImprovement < 0.1) {
      return [
        "建议一周后再次评估，调整训练计划",
        "考虑增加训练频次或调整训练方式",
        "安排医生详细检查，排除潜在问题"
      ];
    } else if (overallImprovement < 0.3) {
      return [
        "建议两周后再次评估",
        "继续执行当前计划，适当增加挑战性",
        "关注主要症状的变化趋势"
      ];
    } else {
      return [
        "建议一个月后再次评估",
        "可以适当增加训练难度和强度",
        "逐步过渡到日常功能性训练"
      ];
    }
  };
  
  const recommendations = generateRecommendations();
  const precautions = generatePrecautions();
  const nextSteps = generateNextSteps();
  
  return (
    <Paper 
      elevation={0} 
      sx={{ 
        p: 3,
        border: '1px solid #eee',
        '@media print': { border: 'none', p: 0, boxShadow: 'none' }
      }}
    >
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold' }}>
        评估建议
      </Typography>
      
      <Grid container spacing={3}>
        {/* 训练建议 */}
        <Grid item xs={12}>
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <AssignmentIcon color="primary" sx={{ mr: 1 }} />
                <Typography variant="subtitle1" fontWeight="bold">
                  康复训练建议
                </Typography>
              </Box>
              <Divider sx={{ my: 1 }} />
              <List dense disablePadding>
                {recommendations.map((recommendation, index) => (
                  <ListItem key={index} disableGutters>
                    <ListItemIcon sx={{ minWidth: 30 }}>
                      <AdjustIcon fontSize="small" color="primary" />
                    </ListItemIcon>
                    <ListItemText primary={recommendation} />
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
        
        {/* 注意事项 */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <WarningAmberIcon color="warning" sx={{ mr: 1 }} />
                <Typography variant="subtitle1" fontWeight="bold">
                  注意事项
                </Typography>
              </Box>
              <Divider sx={{ my: 1 }} />
              <List dense disablePadding>
                {precautions.map((precaution, index) => (
                  <ListItem key={index} disableGutters>
                    <ListItemIcon sx={{ minWidth: 30 }}>
                      <AdjustIcon fontSize="small" color="warning" />
                    </ListItemIcon>
                    <ListItemText primary={precaution} />
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
        
        {/* 后续计划 */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <TipsAndUpdatesIcon color="info" sx={{ mr: 1 }} />
                <Typography variant="subtitle1" fontWeight="bold">
                  后续计划
                </Typography>
              </Box>
              <Divider sx={{ my: 1 }} />
              <List dense disablePadding>
                {nextSteps.map((step, index) => (
                  <ListItem key={index} disableGutters>
                    <ListItemIcon sx={{ minWidth: 30 }}>
                      <AdjustIcon fontSize="small" color="info" />
                    </ListItemIcon>
                    <ListItemText primary={step} />
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      
      <Box sx={{ mt: 3, p: 2, bgcolor: '#f8f8f8', borderRadius: 1 }}>
        <Typography variant="body2" color="text.secondary" fontStyle="italic">
          注：本报告生成的建议基于当前评估数据自动生成，具体康复方案请遵医嘱。
        </Typography>
      </Box>
    </Paper>
  );
};

export default RecommendationSection; 