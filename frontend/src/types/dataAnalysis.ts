// 数据分析平台中使用的类型定义

// 通用数据点结构
export interface DataPoint {
  id?: string;
  value: number;
  timestamp: string | Date;
  label?: string;
  category?: string;
  metadata?: Record<string, any>;
}

// 图表支持的数据类型
export type ChartDataType = 'patient' | 'doctor' | 'device' | 'rehabilitation';

// 时间范围选项
export type TimeRange = 'day' | 'week' | 'month' | 'quarter' | 'year' | 'custom';

// 图表类型
export type ChartType = 'line' | 'bar' | 'pie' | 'area' | 'scatter' | 'composed' | 'radar' | 'heatmap';

// 统计数据概览
export interface StatsOverview {
  patientCount: number;
  weekPatientChange: number;
  doctorCount: number;
  totalDevices: number;
  activeDeviceRate: number;
  avgTrainingTime: number;
  rehabilitationRate: number;
  patientSatisfaction: number;
}

// 趋势数据结构
export interface TrendData {
  date: string;
  value: number;
  category?: string;
}

// 分布数据结构
export interface DistributionData {
  name: string;
  value: number;
  color?: string;
}

// 对比数据结构
export interface ComparisonData {
  category: string;
  [key: string]: any; // 动态键值对，用于不同时段或类别的对比数据
}

// 报表配置
export interface ReportConfig {
  title: string;
  description?: string;
  charts: {
    type: ChartType;
    title: string;
    dataType: ChartDataType;
    timeRange: TimeRange;
  }[];
  filters?: Record<string, any>;
  createdAt?: Date;
  scheduledDelivery?: {
    enabled: boolean;
    frequency: 'daily' | 'weekly' | 'monthly';
    recipients: string[];
  };
}

// API响应类型
export interface AnalyticsApiResponse<T> {
  status: 'success' | 'error' | 'warning';
  message?: string;
  data: T;
  metadata?: {
    total?: number;
    page?: number;
    pageSize?: number;
    timeProcessed?: string;
  };
}

// 预测分析结果
export interface PredictionResult {
  status: string;
  message?: string;
  data_type: string;
  device_id: string;
  days_analyzed: number;
  prediction_days: number;
  method: string;
  data_points: number;
  prediction: {
    values: number[];
    confidence_interval: ConfidenceInterval[] | null;
  };
  all_predictions?: {
    linear?: {
      values: number[];
      confidence_interval: ConfidenceInterval[] | null;
    };
    arima?: {
      values: number[];
      confidence_interval: ConfidenceInterval[] | null;
    };
    prophet?: {
      values: number[];
      confidence_interval: ConfidenceInterval[] | null;
    };
    ensemble?: {
      values: number[];
      confidence_interval: ConfidenceInterval[] | null;
    };
  } | null;
  history: {
    original: number[];
    aggregated: Array<{date: string; value: number}>;
  };
}

export interface ConfidenceInterval {
  lower: number;
  upper: number;
} 