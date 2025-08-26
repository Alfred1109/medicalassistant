import React from 'react';
import { Box, Typography, Tooltip } from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import { SxProps, Theme } from '@mui/system';

interface ValueDisplayProps {
  /**
   * 要显示的数值
   */
  value: number | string;
  
  /**
   * 显示单位
   */
  unit?: string;
  
  /**
   * 数值变化趋势
   */
  trend?: {
    direction: 'up' | 'down' | 'stable';
    value: number;
    suffix?: '%' | '+' | string;
  };
  
  /**
   * 数值尺寸
   */
  size?: 'small' | 'medium' | 'large';
  
  /**
   * 前缀
   */
  prefix?: string;
  
  /**
   * 提示信息
   */
  tooltip?: string;
  
  /**
   * 自定义样式
   */
  sx?: SxProps<Theme>;
  
  /**
   * 数值颜色
   */
  color?: string;
  
  /**
   * 单位颜色
   */
  unitColor?: string;
}

/**
 * 通用值显示组件
 * 用于在各处统一展示带有单位的数值
 */
const ValueDisplay: React.FC<ValueDisplayProps> = ({
  value,
  unit,
  trend,
  size = 'medium',
  prefix,
  tooltip,
  sx = {},
  color,
  unitColor = 'text.secondary'
}) => {
  // 根据尺寸确定排版变体
  const getVariant = () => {
    switch (size) {
      case 'small':
        return 'body2';
      case 'large':
        return 'h5';
      case 'medium':
      default:
        return 'body1';
    }
  };

  const variant = getVariant();
  
  // 计算趋势颜色
  const getTrendColor = () => {
    if (!trend) return undefined;
    return trend.direction === 'up' ? 'error.main' : 
           trend.direction === 'down' ? 'success.main' : 
           undefined;
  };
  
  // 渲染趋势图标
  const renderTrendIcon = () => {
    if (!trend) return null;
    
    const trendColor = getTrendColor();
    
    return (
      <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', ml: 0.5 }}>
        {trend.direction === 'up' ? (
          <TrendingUpIcon fontSize="small" color="error" />
        ) : trend.direction === 'down' ? (
          <TrendingDownIcon fontSize="small" color="success" />
        ) : null}
        <Typography 
          variant="caption" 
          component="span"
          sx={{ 
            ml: 0.5,
            color: trendColor
          }}
        >
          {trend.value}{trend.suffix || ''}
        </Typography>
      </Box>
    );
  };

  const content = (
    <Box 
      sx={{ 
        display: 'inline-flex', 
        alignItems: 'baseline',
        ...sx 
      }}
    >
      {prefix && (
        <Typography 
          variant={variant} 
          component="span" 
          sx={{ mr: 0.5, color: color || 'inherit' }}
        >
          {prefix}
        </Typography>
      )}
      <Typography 
        variant={variant} 
        component="span" 
        sx={{ 
          fontWeight: 500,
          color: color || 'inherit'
        }}
      >
        {value}
      </Typography>
      {unit && (
        <Typography 
          variant={size === 'large' ? 'body2' : 'caption'} 
          component="span" 
          sx={{ 
            ml: 0.5,
            color: unitColor
          }}
        >
          {unit}
        </Typography>
      )}
      {renderTrendIcon()}
    </Box>
  );
  
  // 如果有提示信息，则包装在Tooltip中
  if (tooltip) {
    return (
      <Tooltip title={tooltip}>
        <span>{content}</span>
      </Tooltip>
    );
  }
  
  return content;
};

export default ValueDisplay; 