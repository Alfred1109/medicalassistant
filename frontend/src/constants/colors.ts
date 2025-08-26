/**
 * 颜色常量定义
 * 统一管理系统中使用的颜色值
 */

// 主题色
export const PRIMARY_COLOR = '#1976d2';
export const SECONDARY_COLOR = '#dc004e';
export const SUCCESS_COLOR = '#4caf50';
export const ERROR_COLOR = '#f44336';
export const WARNING_COLOR = '#ff9800';
export const INFO_COLOR = '#2196f3';

// 图表颜色 - 与charts/ChartTypes.ts中的颜色保持一致
export const CHART_COLORS = [
  '#0088FE', // 主蓝色
  '#00C49F', // 绿色
  '#FFBB28', // 黄色
  '#FF8042', // 橙色
  '#8884d8', // 紫色
  '#82ca9d', // 浅绿色
  '#ffc658', // 浅黄色
  '#8dd1e1', // 浅蓝色
  '#a4de6c', // 浅绿色
  '#d0ed57', // 黄绿色
  '#83a6ed', // 淡蓝色
  '#8884d8', // 淡紫色
];

// 状态颜色映射
export const STATUS_COLORS = {
  active: SUCCESS_COLOR,
  pending: INFO_COLOR,
  warning: WARNING_COLOR,
  error: ERROR_COLOR,
  disabled: '#9e9e9e',
}; 