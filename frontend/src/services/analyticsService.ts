import {
  ChartDataType,
  StatsOverview,
  TimeRange,
  TrendData,
  DistributionData,
  ComparisonData,
  PredictionResult
} from '../types/dataAnalysis';
import api from './api'; // 导入配置好的axios实例

/**
 * 数据分析服务
 *
 * 数据来源（真实后端端点，见 backend/app/api/routers/analytics_router.py）：
 * - GET /api/system/visualization/overview  统计概览（响应键已是 camelCase）
 * - GET /api/analytics/trend                趋势（原始形状 { timestamp, value }）
 * - GET /api/analytics/distribution         分布（原始形状 { category, value }）
 * - GET /api/analytics/comparison           对比（原始形状 { category, currentValue, compareValue }）
 * - GET /api/device-analysis/predict-advanced/{device_id} 高级预测（稀疏数据时返回 400）
 *
 * 注意：本服务不再在请求失败时回退到前端模拟数据（原 generateMock* 已删除），
 * 请求失败会向上抛出，由页面渲染错误态。
 * 已知后端缺陷（报告，不在此掩盖）：backend/app/services/analytics_service.py 的
 * trend/distribution/comparison 三个查询在服务层仍返回随机模拟值，且
 * get_stats_overview 异常时会回退模拟概览数据 —— 需后端修复。
 */

// 后端趋势数据原始行形状
interface RawTrendRow {
  timestamp?: string;
  date?: string;
  value: number | string;
}

// 后端分布数据原始行形状
interface RawDistributionRow {
  category?: string;
  name?: string;
  value: number | string;
}

// 后端对比数据原始行形状
interface RawComparisonRow {
  category: string;
  currentValue?: number | string;
  compareValue?: number | string;
}

// 将后端 timestamp 格式化为图表 x 轴标签
const formatTrendLabel = (timestamp: string, timeRange: TimeRange): string => {
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return String(timestamp);
  const pad = (n: number) => n.toString().padStart(2, '0');
  if (timeRange === 'year') return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
  if (timeRange === 'day') {
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:00`;
  }
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};

const toNumber = (value: number | string | undefined): number => {
  const parsed = typeof value === 'number' ? value : parseFloat(String(value ?? ''));
  return isNaN(parsed) ? 0 : parsed;
};

export const analyticsService = {
  /**
   * 获取统计数据概览
   */
  async getStatsOverview(): Promise<StatsOverview> {
    const response = await api.get(`system/visualization/overview`);

    if (response.data.status === 'error') {
      throw new Error(response.data.message || '获取统计数据失败');
    }

    return response.data.data as StatsOverview;
  },

  /**
   * 获取趋势数据
   * @param dataType 数据类型
   * @param timeRange 时间范围
   */
  async getTrendData(dataType: ChartDataType, timeRange: TimeRange): Promise<TrendData[]> {
    const response = await api.get(`analytics/trend`, {
      // 后端查询参数为 data_type / time_range
      params: { data_type: dataType, time_range: timeRange }
    });

    if (response.data.status === 'error') {
      throw new Error(response.data.message || '获取趋势数据失败');
    }

    const rows: RawTrendRow[] = Array.isArray(response.data.data) ? response.data.data : [];
    return rows.map(row => ({
      date: formatTrendLabel(String(row.timestamp ?? row.date ?? ''), timeRange),
      value: toNumber(row.value)
    }));
  },

  /**
   * 获取分布数据
   * @param dataType 数据类型
   * @param timeRange 时间范围
   */
  async getDistributionData(dataType: ChartDataType, timeRange: TimeRange): Promise<DistributionData[]> {
    const response = await api.get(`analytics/distribution`, {
      // 后端查询参数为 data_type / time_range
      params: { data_type: dataType, time_range: timeRange }
    });

    if (response.data.status === 'error') {
      throw new Error(response.data.message || '获取分布数据失败');
    }

    const rows: RawDistributionRow[] = Array.isArray(response.data.data) ? response.data.data : [];
    return rows.map(row => ({
      name: String(row.name ?? row.category ?? ''),
      value: toNumber(row.value)
    }));
  },

  /**
   * 获取对比数据
   * @param dataType 数据类型
   * @param timeRange 时间范围
   * @param compareWith 对比时间段/类别
   */
  async getComparisonData(
    dataType: ChartDataType,
    timeRange: TimeRange,
    compareWith: string
  ): Promise<ComparisonData[]> {
    const response = await api.get(`analytics/comparison`, {
      // 后端查询参数为 data_type / time_range / compare_with
      params: { data_type: dataType, time_range: timeRange, compare_with: compareWith }
    });

    if (response.data.status === 'error') {
      throw new Error(response.data.message || '获取对比数据失败');
    }

    const rows: RawComparisonRow[] = Array.isArray(response.data.data) ? response.data.data : [];
    return rows.map(row => ({
      category: String(row.category ?? ''),
      currentValue: toNumber(row.currentValue),
      compareValue: toNumber(row.compareValue)
    }));
  },

  // 注意：后端 /api/analytics 下无导出报表端点（原 GET /analytics/export 已删除），
  // 导出报表为后端能力待建设，不再提供 exportReport 死链方法。

  /**
   * 获取高级预测分析数据
   *
   * 后端在设备数据点过稀时返回 400（错误语义为"数据不足"，见 device_analysis_router），
   * 该错误会原样抛出，由调用方以错误态呈现，不做静默降级。
   *
   * @param deviceId 设备ID
   * @param dataType 数据类型
   * @param days 分析最近多少天的数据
   * @param predictionDays 预测未来多少天的数据
   * @param method 预测方法
   * @param confidenceInterval 是否计算置信区间
   * @param interval 数据聚合间隔
   */
  async getAdvancedPrediction(
    deviceId: string,
    dataType: string,
    days: number = 30,
    predictionDays: number = 7,
    method: 'linear' | 'arima' | 'prophet' | 'ensemble' = 'linear',
    confidenceInterval: boolean = true,
    interval: 'hour' | 'day' | 'week' | 'month' = 'day'
  ): Promise<PredictionResult> {
    const params = new URLSearchParams({
      data_type: dataType,
      days: days.toString(),
      prediction_days: predictionDays.toString(),
      method,
      confidence_interval: confidenceInterval.toString(),
      interval
    });

    const response = await api.get(
      `device-analysis/predict-advanced/${deviceId}`,
      { params }
    );

    if (response.data.status === 'error') {
      throw new Error(response.data.message || '获取预测分析数据失败');
    }

    return response.data as PredictionResult;
  }
};
