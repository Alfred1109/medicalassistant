import React from 'react';
import { Box, Typography, LinearProgress, Paper, Grid } from '@mui/material';
import { Check as CheckIcon, Warning as WarningIcon } from '@mui/icons-material';
import { REHAB_STATUS_MAP } from '../../constants/mappings';
import { StatusChip, ValueDisplay } from '../common';

interface RehabProgressProps {
  planName: string;
  progress: number;
  daysLeft: number;
  completedSessions: number;
  totalSessions: number;
  status: 'active' | 'completed' | 'expired';
}

const RehabProgressSection: React.FC<RehabProgressProps> = ({
  planName,
  progress,
  daysLeft,
  completedSessions,
  totalSessions,
  status
}) => {
  // 使用统一的状态映射
  const getStatusConfig = () => {
    const statusInfo = REHAB_STATUS_MAP[status];
    
    // 添加图标（因为我们在映射中移除了图标）
    const icon = status === 'completed' ? <CheckIcon fontSize="small" /> :
                status === 'expired' ? <WarningIcon fontSize="small" /> : null;
    
    return {
      ...statusInfo,
      icon
    };
  };

  const statusConfig = getStatusConfig();

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography variant="h6" component="h3">
          {planName}
        </Typography>
        <StatusChip
          label={statusConfig.label}
          color={statusConfig.color}
          small
          icon={statusConfig.icon}
        />
      </Box>

      <Box sx={{ mb: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            总进度
          </Typography>
          <ValueDisplay
            value={progress}
            unit="%"
            size="small"
          />
        </Box>
        <LinearProgress variant="determinate" value={progress} sx={{ height: 8, borderRadius: 4 }} />
      </Box>

      <Grid container spacing={2}>
        <Grid item xs={6}>
          <Box>
            <Typography variant="body2" color="text.secondary">
              训练计划
            </Typography>
            <ValueDisplay
              value={completedSessions}
              unit={`/ ${totalSessions} 次`}
            />
          </Box>
        </Grid>
        <Grid item xs={6}>
          <Box>
            <Typography variant="body2" color="text.secondary">
              剩余天数
            </Typography>
            <ValueDisplay
              value={daysLeft}
              unit="天"
              color={daysLeft < 5 ? 'error.main' : undefined}
            />
          </Box>
        </Grid>
      </Grid>
    </Paper>
  );
};

export default RehabProgressSection; 