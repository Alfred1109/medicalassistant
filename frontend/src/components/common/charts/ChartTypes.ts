/**
 * 图表类型定义
 * 统一管理项目中使用的图表类型
 */

// 图表类型
export type ChartType = 'line' | 'bar' | 'pie' | 'area';

// 时间范围
export type TimeRange = '1d' | '7d' | '30d' | '90d' | '1y' | 'all' | 'custom';

// 图表数据点
export interface DataPoint {
  [key: string]: any;
}

// 图表配置
export interface ChartConfig {
  id: string;
  title: string;
  type: ChartType;
  height?: number;
  width?: number;
  data?: DataPoint[];
  colors?: Record<string, string>;
  xKey?: string;
  yKeys?: string[];
  stacked?: boolean;
  showLegend?: boolean;
  showTooltip?: boolean;
  showGrid?: boolean;
  timeRange?: TimeRange;
}

// 图表颜色
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

// 图表工具函数
export const getColorForKey = (key: string, index: number, colors?: Record<string, string>): string => {
  if (colors && colors[key]) {
    return colors[key];
  }
  return CHART_COLORS[index % CHART_COLORS.length];
};

// 格式化图表数据
export const formatChartValue = (value: any): string => {
  if (value === null || value === undefined) {
    return '-';
  }
  
  if (typeof value === 'number') {
    // 对于较大的数字使用千分位分隔符
    if (value >= 10000 || value <= -10000) {
      return value.toLocaleString('zh-CN');
    }
    
    // 保留一位小数点
    return value.toFixed(1);
  }
  
  return String(value);
}; 