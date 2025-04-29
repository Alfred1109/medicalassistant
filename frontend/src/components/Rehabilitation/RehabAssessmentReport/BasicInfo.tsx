import React from 'react';
import { Box, Typography, Grid, Paper, Divider } from '@mui/material';
import { formatDate } from './utils';
import { RehabPlan } from './index';

interface BasicInfoProps {
  plan: RehabPlan;
  assessmentDate: string;
}

/**
 * 康复评估报告的基本信息组件，展示评估和计划基本信息
 */
const BasicInfo: React.FC<BasicInfoProps> = ({
  plan,
  assessmentDate
}) => {
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
        计划基本信息
      </Typography>
      
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6}>
          <InfoItem label="计划名称" value={plan.title} />
          <InfoItem label="计划ID" value={plan.id} />
          <InfoItem label="开始日期" value={formatDate(plan.startDate)} />
          <InfoItem label="状态" value={
            plan.status === 'active' ? '进行中' :
            plan.status === 'completed' ? '已完成' :
            plan.status === 'paused' ? '已暂停' : '已取消'
          } />
        </Grid>
        
        <Grid item xs={12} sm={6}>
          <InfoItem label="评估日期" value={formatDate(assessmentDate)} />
          <InfoItem label="评估类型" value="常规进度评估" />
          <InfoItem label="训练项目" value={`${plan.exercises.length}项`} />
          {plan.endDate && (
            <InfoItem label="计划结束" value={formatDate(plan.endDate)} />
          )}
        </Grid>
      </Grid>
      
      {plan.description && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            计划描述
          </Typography>
          <Typography variant="body2">
            {plan.description}
          </Typography>
        </Box>
      )}
    </Paper>
  );
};

// 信息项组件
const InfoItem: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <Box sx={{ display: 'flex', mb: 1.5 }}>
    <Typography 
      variant="body2" 
      sx={{ 
        color: 'text.secondary', 
        width: '80px', 
        flexShrink: 0 
      }}
    >
      {label}:
    </Typography>
    <Typography variant="body2" sx={{ fontWeight: 500 }}>
      {value || '--'}
    </Typography>
  </Box>
);

export default BasicInfo; 