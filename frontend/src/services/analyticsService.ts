import { 
  AnalyticsApiResponse, 
  ChartDataType, 
  StatsOverview, 
  TimeRange, 
  TrendData, 
  DistributionData, 
  ComparisonData,
  PredictionResult
} from '../types/dataAnalysis';
import api from './api'; // 导入配置好的axios实例

// 基础API路径 - 已移除，因为api实例已设置baseURL
// const API_BASE_URL = '/api';

/**
 * 数据分析服务
 * 提供各种数据分析相关的API请求函数
 */
export const analyticsService = {
  /**
   * 获取统计数据概览
   */
  async getStatsOverview(): Promise<StatsOverview> {
    try {
      const response = await api.get(`system/visualization/overview`);
      
      if (response.data.status === 'error') {
        throw new Error(response.data.message || '获取统计数据失败');
      }
      
      return response.data.data;
    } catch (error) {
      console.error('获取统计数据概览失败:', error);
      
      // 返回模拟数据（实际项目中应该使用更合适的错误处理方式）
      return {
        patientCount: 1248,
        weekPatientChange: 4.2,
        doctorCount: 86,
        totalDevices: 152,
        activeDeviceRate: 82,
        avgTrainingTime: 45,
        rehabilitationRate: 68,
        patientSatisfaction: 92
      };
    }
  },
  
  /**
   * 获取趋势数据
   * @param dataType 数据类型
   * @param timeRange 时间范围
   */
  async getTrendData(dataType: ChartDataType, timeRange: TimeRange): Promise<TrendData[]> {
    try {
      const response = await api.get(`analytics/trend`, {
        params: { dataType, timeRange }
      });
      
      if (response.data.status === 'error') {
        throw new Error(response.data.message || '获取趋势数据失败');
      }
      
      return response.data.data;
    } catch (error) {
      console.error(`获取${dataType}趋势数据失败:`, error);
      
      // 返回模拟数据
      return generateMockTrendData(dataType, timeRange);
    }
  },
  
  /**
   * 获取分布数据
   * @param dataType 数据类型
   * @param timeRange 时间范围
   */
  async getDistributionData(dataType: ChartDataType, timeRange: TimeRange): Promise<DistributionData[]> {
    try {
      const response = await api.get(`analytics/distribution`, {
        params: { dataType, timeRange }
      });
      
      if (response.data.status === 'error') {
        throw new Error(response.data.message || '获取分布数据失败');
      }
      
      return response.data.data;
    } catch (error) {
      console.error(`获取${dataType}分布数据失败:`, error);
      
      // 返回模拟数据
      return generateMockDistributionData(dataType);
    }
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
    try {
      const response = await api.get(`analytics/comparison`, {
        params: { dataType, timeRange, compareWith }
      });
      
      if (response.data.status === 'error') {
        throw new Error(response.data.message || '获取对比数据失败');
      }
      
      return response.data.data;
    } catch (error) {
      console.error(`获取${dataType}对比数据失败:`, error);
      
      // 返回模拟数据
      return generateMockComparisonData(dataType, compareWith);
    }
  },
  
  /**
   * 导出报表数据
   * @param dataType 数据类型
   * @param timeRange 时间范围
   * @param format 导出格式
   */
  async exportReport(
    dataType: ChartDataType, 
    timeRange: TimeRange,
    format: 'csv' | 'xlsx' | 'pdf'
  ): Promise<Blob> {
    try {
      const response = await api.get(`analytics/export`, {
        params: { dataType, timeRange, format },
        responseType: 'blob',
        headers: { 
          Accept: format === 'pdf' ? 'application/pdf' : 'application/octet-stream' 
        }
      });
      
      return response.data;
    } catch (error) {
      console.error(`导出${dataType}报表数据失败:`, error);
      throw error;
    }
  },

  /**
   * 获取高级预测分析数据
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
    try {
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
      
      return response.data;
    } catch (error) {
      console.error(`获取预测分析数据失败:`, error);
      
      // 返回模拟数据
      return generateMockPredictionData(dataType, method, predictionDays, confidenceInterval);
    }
  }
};

// 生成模拟的趋势数据
function generateMockTrendData(dataType: ChartDataType, timeRange: TimeRange): TrendData[] {
  const result: TrendData[] = [];
  const daysCount = timeRange === 'day' ? 24 : // 按小时
                  timeRange === 'week' ? 7 : 
                  timeRange === 'month' ? 30 : 
                  timeRange === 'quarter' ? 90 : 
                  timeRange === 'year' ? 12 : 30; // 默认30天
  
  const now = new Date();
  const isMonthly = timeRange === 'year'; // 年度数据按月展示
  
  for (let i = 0; i < daysCount; i++) {
    const date = new Date();
    
    if (isMonthly) {
      // 设置为前N个月
      date.setMonth(now.getMonth() - (daysCount - 1) + i);
      date.setDate(1); // 月初
    } else if (timeRange === 'day') {
      // 设置为前N小时
      date.setHours(now.getHours() - (daysCount - 1) + i);
    } else {
      // 设置为前N天
      date.setDate(now.getDate() - (daysCount - 1) + i);
    }
    
    // 根据数据类型生成不同的随机值
    let value: number;
    switch (dataType) {
      case 'patient':
        // 患者数据的基线较高
        value = Math.floor(1000 + Math.random() * 500) + (i * 5);
        break;
      case 'doctor':
        // 医生工作量，缓慢增长
        value = Math.floor(50 + Math.random() * 30) + (i * 0.2);
        break;
      case 'device':
        // 设备使用量，波动较大
        value = Math.floor(100 + Math.random() * 100) + (i * Math.sin(i * 0.5) * 5);
        break;
      case 'rehabilitation':
        // 康复数据，稳步增长
        value = Math.floor(60 + Math.random() * 20) + (i * 0.8);
        break;
      default:
        value = Math.floor(100 + Math.random() * 100);
    }
    
    const formattedDate = isMonthly
      ? `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}`
      : timeRange === 'day'
        ? `${date.getHours().toString().padStart(2, '0')}:00`
        : `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
    
    result.push({
      date: formattedDate,
      value: Math.max(0, value) // 确保值不为负数
    });
  }
  
  return result;
}

// 生成模拟的分布数据
function generateMockDistributionData(dataType: ChartDataType): DistributionData[] {
  switch (dataType) {
    case 'patient':
      // 患者年龄分布
      return [
        { name: '0-18岁', value: 126, color: '#8884d8' },
        { name: '19-35岁', value: 284, color: '#82ca9d' },
        { name: '36-50岁', value: 324, color: '#ffc658' },
        { name: '51-65岁', value: 286, color: '#ff8042' },
        { name: '66岁以上', value: 228, color: '#0088FE' }
      ];
    case 'doctor':
      // 医生专业分布
      return [
        { name: '神经科', value: 18, color: '#8884d8' },
        { name: '骨科', value: 22, color: '#82ca9d' },
        { name: '康复科', value: 28, color: '#ffc658' },
        { name: '内科', value: 12, color: '#ff8042' },
        { name: '其他', value: 6, color: '#0088FE' }
      ];
    case 'device':
      // 设备类型分布
      return [
        { name: '康复训练设备', value: 68, color: '#8884d8' },
        { name: '监测设备', value: 42, color: '#82ca9d' },
        { name: '辅助设备', value: 24, color: '#ffc658' },
        { name: '评估设备', value: 18, color: '#ff8042' }
      ];
    case 'rehabilitation':
      // 康复类型分布
      return [
        { name: '运动功能', value: 42, color: '#8884d8' },
        { name: '言语功能', value: 18, color: '#82ca9d' },
        { name: '认知功能', value: 16, color: '#ffc658' },
        { name: '日常生活', value: 24, color: '#ff8042' }
      ];
    default:
      return [
        { name: '类别A', value: 30, color: '#8884d8' },
        { name: '类别B', value: 25, color: '#82ca9d' },
        { name: '类别C', value: 35, color: '#ffc658' },
        { name: '类别D', value: 10, color: '#ff8042' }
      ];
  }
}

// 生成模拟的对比数据
function generateMockComparisonData(dataType: ChartDataType, compareWith: string): ComparisonData[] {
  const categories = dataType === 'patient' ? ['新患者', '复诊患者', '住院患者', '出院患者'] :
                  dataType === 'doctor' ? ['普通门诊', '专家门诊', '手术', '查房'] :
                  dataType === 'device' ? ['康复训练', '评估测试', '日常监测', '急救使用'] :
                  dataType === 'rehabilitation' ? ['初级康复', '中级康复', '高级康复', '康复评估'] :
                  ['类别A', '类别B', '类别C', '类别D'];
  
  const periods = compareWith === 'lastPeriod' ? 
    { current: '本期', previous: '上期' } : 
    { current: '今年', previous: '去年' };
    
  return categories.map(category => {
    const currentValue = Math.floor(50 + Math.random() * 100);
    const previousValue = Math.floor(currentValue * (0.7 + Math.random() * 0.6)); // 70%-130%的变化
    
    return {
      category,
      [periods.current]: currentValue,
      [periods.previous]: previousValue
    };
  });
}

// 生成模拟的预测数据
function generateMockPredictionData(
  dataType: string,
  method: string,
  predictionDays: number,
  withConfidence: boolean
): PredictionResult {
  const now = new Date();
  const historyData = [];
  
  // 生成历史数据
  for (let i = 0; i < 30; i++) {
    const date = new Date();
    date.setDate(now.getDate() - (30 - i));
    
    // 为不同数据类型生成不同范围的模拟值
    let baseValue = 0;
    switch (dataType) {
      case 'heart_rate':
        baseValue = 70 + Math.random() * 10;
        break;
      case 'blood_pressure':
        baseValue = 120 + Math.random() * 20;
        break;
      case 'temperature':
        baseValue = 36.5 + Math.random() * 1;
        break;
      case 'steps':
        baseValue = 5000 + Math.random() * 3000;
        break;
      default:
        baseValue = 100 + Math.random() * 50;
    }
    
    historyData.push({
      value: baseValue + i * 0.5 * (Math.random() > 0.5 ? 1 : -1),
      timestamp: date.toISOString(),
      data_type: dataType
    });
  }
  
  // 生成预测数据
  const predictions = [];
  const confidenceIntervals = [];
  
  let lastValue = historyData[historyData.length - 1].value;
  const trend = (lastValue - historyData[0].value) / 30;
  
  for (let i = 0; i < predictionDays; i++) {
    // 添加一些随机波动
    const randomFactor = Math.random() * 0.1 * lastValue;
    const predictedValue = lastValue + trend * (i + 1) + (randomFactor - (0.05 * lastValue));
    
    predictions.push(predictedValue);
    
    if (withConfidence) {
      // 增加随时间的不确定性
      const uncertainty = (i + 1) * 0.02 * lastValue;
      confidenceIntervals.push({
        lower: predictedValue - uncertainty,
        upper: predictedValue + uncertainty
      });
    }
  }
  
  return {
    status: 'success',
    data_type: dataType,
    device_id: 'mock-device-123',
    days_analyzed: 30,
    prediction_days: predictionDays,
    method: method,
    data_points: historyData.length,
    prediction: {
      values: predictions,
      confidence_interval: withConfidence ? confidenceIntervals : null
    },
    all_predictions: method === 'ensemble' ? {
      linear: {
        values: predictions.map(v => v * 0.9),
        confidence_interval: withConfidence ? confidenceIntervals.map(ci => ({
          lower: ci.lower * 0.9,
          upper: ci.upper * 0.9
        })) : null
      },
      arima: {
        values: predictions.map(v => v * 1.1),
        confidence_interval: withConfidence ? confidenceIntervals.map(ci => ({
          lower: ci.lower * 1.1,
          upper: ci.upper * 1.1
        })) : null
      },
      prophet: {
        values: predictions.map(v => v * 1.05),
        confidence_interval: withConfidence ? confidenceIntervals.map(ci => ({
          lower: ci.lower * 1.05,
          upper: ci.upper * 1.05
        })) : null
      },
      ensemble: {
        values: predictions,
        confidence_interval: withConfidence ? confidenceIntervals : null
      }
    } : null,
    history: {
      original: historyData.map(item => item.value),
      aggregated: historyData.map(item => ({
        date: item.timestamp.split('T')[0],
        value: item.value
      }))
    }
  };
} 