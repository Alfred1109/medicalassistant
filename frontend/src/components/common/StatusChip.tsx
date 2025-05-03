import React from 'react';
import { Chip } from '@mui/material';
import { SxProps, Theme } from '@mui/system';

// 自定义ChipColor类型
type ChipColor = 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning';

interface StatusChipProps {
  /**
   * 显示的标签文本
   */
  label: string;
  
  /**
   * 颜色 - 可以使用MUI默认颜色名称或自定义
   */
  color?: ChipColor | string;
  
  /**
   * 是否显示为小型芯片
   */
  small?: boolean;
  
  /**
   * 图标组件（可选）
   */
  icon?: React.ReactNode;
  
  /**
   * 自定义样式
   */
  sx?: SxProps<Theme>;
  
  /**
   * 点击处理函数（可选）
   */
  onClick?: () => void;
  
  /**
   * 删除处理函数（可选）
   */
  onDelete?: () => void;
  
  /**
   * 边框变体（默认为填充）
   */
  variant?: 'filled' | 'outlined';
}

/**
 * 通用状态芯片组件
 * 在整个应用中用于统一展示状态信息
 */
const StatusChip: React.FC<StatusChipProps> = ({
  label,
  color = 'default',
  small = false,
  icon,
  sx = {},
  onClick,
  onDelete,
  variant = 'filled'
}) => {
  // 判断是否为MUI内置颜色
  const isMuiColor = [
    'default', 'primary', 'secondary', 'error', 
    'info', 'success', 'warning'
  ].includes(color as string);
  
  // 如果是自定义颜色，则通过sx设置
  const customStyle: SxProps<Theme> = !isMuiColor 
    ? { 
        bgcolor: color, 
        color: '#fff',
        '&:hover': { bgcolor: color }
      } 
    : {};
  
  return (
    <Chip
      label={label}
      color={isMuiColor ? (color as ChipColor) : undefined}
      size={small ? 'small' : 'medium'}
      icon={icon}
      variant={variant}
      sx={{
        height: small ? 20 : 24,
        ...customStyle,
        ...sx
      }}
      onClick={onClick}
      onDelete={onDelete}
    />
  );
};

export default StatusChip; 