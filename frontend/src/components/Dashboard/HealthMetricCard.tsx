import React from 'react';
import { 
  Card, 
  CardContent, 
  Typography, 
  Box, 
  LinearProgress, 
  IconButton, 
  Tooltip
} from '@mui/material';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import { PRIMARY_COLOR, STATUS_COLORS } from '../../constants/colors';
import { StatusChip, ValueDisplay } from '../common';

interface HealthMetricCardProps {
  title: string;
  value: number;
  unit: string;
  normal: {
    min: number;
    max: number;
  };
  trend?: {
    direction: 'up' | 'down' | 'stable';
    percentage: number;
  };
  color?: string;
  description?: string;
  onClick?: () => void;
}

const HealthMetricCard: React.FC<HealthMetricCardProps> = ({
  title,
  value,
  unit,
  normal,
  trend,
  color = PRIMARY_COLOR,
  description,
  onClick
}) => {
  // 计算值在正常范围内的百分比位置
  const calcValuePosition = () => {
    const range = normal.max - normal.min;
    const position = ((value - normal.min) / range) * 100;
    
    // 确保位置在0-100之间
    return Math.max(0, Math.min(100, position));
  };
  
  // 判断值是否在正常范围内
  const isNormal = value >= normal.min && value <= normal.max;
  
  // 获取状态芯片的颜色和文字
  const getStatusChip = () => {
    if (value < normal.min) {
      return { color: 'warning', label: '偏低' };
    } else if (value > normal.max) {
      return { color: 'error', label: '偏高' };
    } else {
      return { color: 'success', label: '正常' };
    }
  };
  
  const statusChip = getStatusChip();
  
  // 获取状态颜色
  const getStatusColor = () => {
    if (value < normal.min) {
      return STATUS_COLORS.warning;
    } else if (value > normal.max) {
      return STATUS_COLORS.error;
    } else {
      return STATUS_COLORS.active;
    }
  };

  return (
    <Card 
      sx={{ 
        height: '100%', 
        border: `1px solid ${isNormal ? '#e0e0e0' : '#ffcc80'}`,
        boxShadow: isNormal ? undefined : '0 0 10px rgba(255, 152, 0, 0.2)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.2s ease-in-out',
        '&:hover': onClick ? { transform: 'translateY(-4px)', boxShadow: 3 } : {}
      }}
      onClick={onClick}
    >
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
          <Typography variant="subtitle1" color="text.secondary">
            {title}
          </Typography>
          <StatusChip
            label={statusChip.label}
            color={statusChip.color}
            small
          />
        </Box>
        
        <ValueDisplay
          value={value}
          unit={unit}
          size="large"
          trend={trend ? {
            direction: trend.direction,
            value: trend.percentage,
            suffix: '%'
          } : undefined}
        />
        
        <Box mt={2} mb={1} display="flex" alignItems="center">
          <Typography variant="caption" color="text.secondary" mr={1}>
            {normal.min}
          </Typography>
          <Box sx={{ flexGrow: 1, position: 'relative' }}>
            <LinearProgress
              variant="determinate"
              value={100}
              sx={{
                height: 8,
                borderRadius: 4,
                backgroundColor: '#e0e0e0',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: color,
                },
              }}
            />
            {/* 当前值标记 */}
            <Box
              sx={{
                position: 'absolute',
                left: `${calcValuePosition()}%`,
                top: '50%',
                transform: 'translate(-50%, -50%)',
                width: 12,
                height: 12,
                borderRadius: '50%',
                backgroundColor: isNormal ? color : getStatusColor(),
                border: '2px solid white',
                boxShadow: '0 0 4px rgba(0,0,0,0.2)',
                zIndex: 1,
              }}
            />
          </Box>
          <Typography variant="caption" color="text.secondary" ml={1}>
            {normal.max}
          </Typography>
        </Box>
        
        {description && (
          <Box mt={1} display="flex" alignItems="center">
            <Tooltip title={description}>
              <IconButton size="small" sx={{ p: 0, mr: 0.5 }}>
                <ArrowDropDownIcon fontSize="small" color="action" />
              </IconButton>
            </Tooltip>
            <Typography variant="caption" color="text.secondary" noWrap>
              {description}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default HealthMetricCard; 