/**
 * 健康数据相关类型声明
 */

// 健康数据类型
export type HealthDataType = 'heart_rate' | 'blood_pressure' | 'weight' | 'blood_glucose' | 'sleep' | 'steps' | 'temperature';

// 健康数据实体
export interface HealthData {
  id: string;
  timestamp: string;
  type: HealthDataType;
  value: number;
  unit: string;
  notes?: string;
  source?: string;
  userId?: string;
  heartRate?: number;
  systolicBP?: number;
  diastolicBP?: number;
  weight?: number;
  bloodGlucose?: number;
  sleepHours?: number;
  steps?: number;
  temperature?: number;
  oxygenSaturation?: number;
  stressLevel?: number;
}

// 窗口组件尺寸
export type WidgetSize = 'small' | 'medium' | 'large';

// 时间范围
export type TimeRange = 'day' | 'week' | 'month' | 'year';

// 窗口组件类型
export type WidgetType = 'line' | 'bar' | 'stat' | 'area' | 'progress' | 'goal';

// 窗口组件配置
export interface WidgetConfig {
  id: string;
  title: string;
  type: WidgetType;
  dataType: HealthDataType;
  dataKey: string;  // 对应HealthData中的属性名
  size: WidgetSize;
  timeRange: TimeRange;
  position: number;
  thresholds?: {
    min: number;
    max: number;
  };
  goal?: number;
  color?: string;
}

// 健康数据基本类型
export interface HealthData {
  timestamp: string;
  // 基础健康指标
  heartRate?: number;
  bloodPressureSystolic?: number;
  bloodPressureDiastolic?: number;
  bloodSugar?: number;
  weight?: number;
  temperature?: number;
  stepCount?: number;
  sleepHours?: number;
  // 其他可能需要的属性
  oxygenSaturation?: number;
  respirationRate?: number;
  caloriesBurned?: number;
  activityMinutes?: number;
  distance?: number;
  hydration?: number;
  stressLevel?: number;
}

// Widget配置接口
export interface WidgetConfig {
  id: string;
  title: string;
  type: WidgetType;
  dataKey: string;  // 对应HealthData中的属性名
  gridSize?: number; // 在网格中占用的列数，默认为4
  color?: string;    // 图表颜色
}

// 仪表盘配置
export interface DashboardConfig {
  widgets: WidgetConfig[];
  userId?: string;
  lastModified?: string;
}

// 健康数据阈值定义
export interface HealthThreshold {
  id?: string;
  dataKey: string;  // 对应HealthData中的属性名
  minValue?: number;
  maxValue?: number;
  criticalMinValue?: number;
  criticalMaxValue?: number;
  targetValue?: number;
  userId?: string;
  patientId?: string;
  isDefault?: boolean;
}

// 设备数据
export interface Device {
  id: string;
  name: string;
  type: string;
  manufacturer: string;
  model: string;
  serialNumber?: string;
  status: 'connected' | 'disconnected' | 'pairing' | 'error';
  lastSyncTime?: string;
  batteryLevel?: number;
  supportedMetrics: string[];
  userId?: string;
  patientId?: string;
}

// 健康数据导入记录
export interface HealthDataImport {
  id: string;
  importTime: string;
  source: string;
  deviceId?: string;
  records: number;
  status: 'completed' | 'failed' | 'partial' | 'processing';
  errorMessage?: string;
  userId: string;
  patientId?: string;
}

// 健康数据统计信息
export interface HealthDataStats {
  dataKey: string;
  timeRange: string;
  count: number;
  min?: number;
  max?: number;
  avg?: number;
  median?: number;
  trend?: 'increasing' | 'decreasing' | 'stable';
  lastValue?: number;
  lastUpdateTime?: string;
}

// 健康数据过滤参数
export interface HealthDataFilterParams {
  startDate?: string;
  endDate?: string;
  dataTypes?: string[];
  timeRange?: 'day' | 'week' | 'month' | 'year' | 'custom';
  limit?: number;
  offset?: number;
  sortBy?: string;
  sortDirection?: 'asc' | 'desc';
} 