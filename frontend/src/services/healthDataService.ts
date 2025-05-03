import { HealthDataType, WidgetSize, TimeRange, WidgetType } from '../types/health';

// 健康数据类型
export interface HealthData {
  id: string;
  type: HealthDataType;
  value: number | string;
  unit: string;
  timestamp: string;
  deviceId?: string;
  deviceName?: string;
  userId?: string;
  notes?: string;
}

// 小部件配置类型
export interface WidgetConfig {
  id: string;
  title: string;
  type: WidgetType;
  dataType: HealthDataType;
  dataKey: string;
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

// 图表数据项类型
export interface ChartDataItem {
  time: string;
  date: string;
  value: number | string;
  unit: string;
  systolic?: number;
  diastolic?: number;
}

// 格式化数据以供图表使用
export const formatDataForChart = (data: HealthData[], dataType: HealthDataType): ChartDataItem[] => {
  // 根据数据类型进行不同的处理
  const filteredData = data.filter(item => item.type === dataType);
  
  // 按时间排序
  const sortedData = filteredData.sort((a, b) => 
    new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );
  
  // 转换为图表所需格式
  return sortedData.map(item => {
    const date = new Date(item.timestamp);
    const result: ChartDataItem = {
      time: date.toLocaleTimeString(),
      date: date.toLocaleDateString(),
      value: item.value,
      unit: item.unit
    };
    
    // 血压数据特殊处理
    if (dataType === 'blood_pressure') {
      const parts = typeof item.value === 'string' ? item.value.split('/') : [];
      if (parts.length === 2) {
        result.systolic = parseInt(parts[0]);
        result.diastolic = parseInt(parts[1]);
      }
    }
    
    return result;
  });
};

// 获取最新值
export const getLatestValue = (data: HealthData[], dataType: HealthDataType): HealthData | null => {
  const filteredData = data.filter(item => item.type === dataType);
  
  if (filteredData.length === 0) return null;
  
  // 按时间排序并获取最新的
  return filteredData.sort((a, b) => 
    new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  )[0];
};

// 生成模拟健康数据
const generateMockHealthData = (): HealthData[] => {
  const now = new Date();
  const data: HealthData[] = [];
  
  // 心率数据
  for (let i = 0; i < 24; i++) {
    const timestamp = new Date(now);
    timestamp.setHours(now.getHours() - 24 + i);
    
    data.push({
      id: `hr-${i}`,
      type: 'heart_rate',
      value: Math.floor(60 + Math.random() * 40), // 60-100 bpm
      unit: 'bpm',
      timestamp: timestamp.toISOString()
    });
  }
  
  // 血压数据
  for (let i = 0; i < 6; i++) {
    const timestamp = new Date(now);
    timestamp.setHours(now.getHours() - 24 + i * 4);
    
    const systolic = Math.floor(110 + Math.random() * 30); // 收缩压 110-140
    const diastolic = Math.floor(60 + Math.random() * 30); // 舒张压 60-90
    
    data.push({
      id: `bp-${i}`,
      type: 'blood_pressure',
      value: `${systolic}/${diastolic}`,
      unit: 'mmHg',
      timestamp: timestamp.toISOString()
    });
  }
  
  // 体重数据
  data.push({
    id: 'weight-1',
    type: 'weight',
    value: 72.5,
    unit: 'kg',
    timestamp: new Date().toISOString()
  });
  
  // 血糖数据
  data.push({
    id: 'glucose-1',
    type: 'blood_glucose',
    value: 95,
    unit: 'mg/dL',
    timestamp: new Date().toISOString()
  });
  
  // 步数数据
  data.push({
    id: 'steps-1',
    type: 'steps',
    value: 8500,
    unit: '步',
    timestamp: new Date().toISOString()
  });
  
  // 睡眠数据
  data.push({
    id: 'sleep-1',
    type: 'sleep',
    value: 7.5,
    unit: '小时',
    timestamp: new Date().toISOString()
  });
  
  return data;
};

// 模拟数据
const mockHealthData: HealthData[] = generateMockHealthData();

// 默认小部件配置
const defaultWidgets: WidgetConfig[] = [
  {
    id: 'widget-1',
    title: '心率监测',
    type: 'line',
    dataType: 'heart_rate',
    dataKey: 'value',
    size: 'medium',
    timeRange: 'day',
    position: 1,
    color: '#FF5252'
  },
  {
    id: 'widget-2',
    title: '血压监测',
    type: 'bar',
    dataType: 'blood_pressure',
    dataKey: 'value',
    size: 'medium',
    timeRange: 'week',
    position: 2,
    color: '#536DFE'
  },
  {
    id: 'widget-3',
    title: '血糖监测',
    type: 'line',
    dataType: 'blood_glucose',
    dataKey: 'value',
    size: 'small',
    timeRange: 'week',
    position: 3,
    color: '#FF9800'
  },
  {
    id: 'widget-4',
    title: '体重趋势',
    type: 'line',
    dataType: 'weight',
    dataKey: 'value',
    size: 'small',
    timeRange: 'month',
    position: 4,
    color: '#4CAF50'
  },
  {
    id: 'widget-5',
    title: '今日步数',
    type: 'goal',
    dataType: 'steps',
    dataKey: 'value',
    size: 'small',
    timeRange: 'day',
    position: 5,
    goal: 10000,
    color: '#03A9F4'
  },
  {
    id: 'widget-6',
    title: '睡眠时长',
    type: 'stat',
    dataType: 'sleep',
    dataKey: 'value',
    size: 'small',
    timeRange: 'day',
    position: 6,
    color: '#9C27B0'
  }
];

/**
 * 健康数据服务
 */
const healthDataService = {
  /**
   * 获取用户健康数据
   * @param userId 用户ID
   * @param timeRange 时间范围
   * @returns 健康数据数组
   */
  getUserHealthData: async (userId: string, timeRange?: string): Promise<HealthData[]> => {
    try {
      // 这里应该从API获取数据，现在使用模拟数据
      return mockHealthData;
    } catch (error) {
      console.error('获取健康数据失败:', error);
      return [];
    }
  },
  
  /**
   * 获取用户仪表盘配置
   * @param userId 用户ID
   * @returns 仪表盘配置
   */
  getUserDashboardConfig: async (userId: string): Promise<WidgetConfig[]> => {
    try {
      // 这里应该从API获取数据，现在使用默认配置
      return defaultWidgets;
    } catch (error) {
      console.error('获取仪表盘配置失败:', error);
      return defaultWidgets;
    }
  },
  
  /**
   * 保存用户健康仪表盘配置
   * @param userId 用户ID
   * @param widgets 控件配置数组
   * @returns 是否成功
   */
  saveUserDashboardConfig: async (userId: string, widgets: WidgetConfig[]): Promise<boolean> => {
    try {
      // 这里应该调用API保存配置
      console.log('保存仪表盘配置:', userId, widgets);
      return true;
    } catch (error) {
      console.error('保存仪表盘配置失败:', error);
      return false;
    }
  }
};

export default healthDataService; 