import { HealthDataType, WidgetSize, TimeRange, WidgetType } from '../types/health';
import api from './httpClient';

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
 *
 * 数据来源（真实后端端点，见 backend/app/api/routers/health_record_router.py）：
 * - GET /api/health-records/health-data  按患者列出健康数据（patient_id 必填）
 *
 * 注意：
 * - 本服务不在请求失败时回退到前端模拟数据（原 generateMockHealthData 已删除），
 *   请求失败会向上抛出，由调用方渲染错误态。
 * - 后端要求具体患者 ID，不支持 'me' 之类的占位符；调用方需先解析出真实患者 ID。
 * - 后端生命体征 vital_type 尚无 sleep / steps 等类型的写入路径（前端类型已定义），
 *   这些数据自然缺席，由调用方展示诚实空态，不做前端补数。
 */

// 后端健康数据行形状（HealthDataResponse，见 backend/app/schemas/health_record.py）
interface BackendHealthDataRow {
  id: string;
  patient_id: string;
  data_type: string; // vital_sign / lab_result / ...
  data: {
    type?: string; // vital_sign：生命体征类型（heart_rate、blood_pressure、body_temperature...）
    value?: number | string | Record<string, number>;
    unit?: string | null;
    notes?: string | null;
    [key: string]: unknown;
  };
  device_id?: string | null;
  recorded_at: string;
}

// 后端生命体征类型 → 前端 HealthDataType 映射；
// 后端存在但前端类型未覆盖的类型（blood_oxygen、respiratory_rate 等）跳过
const vitalTypeToHealthDataType: Record<string, HealthDataType> = {
  heart_rate: 'heart_rate',
  blood_pressure: 'blood_pressure',
  weight: 'weight',
  blood_glucose: 'blood_glucose',
  blood_sugar: 'blood_glucose',
  body_temperature: 'temperature',
  temperature: 'temperature'
};

const healthDataService = {
  /**
   * 获取用户健康数据
   * @param userId 患者 ID（后端 patient_id 必填，不支持 'me' 占位）
   * @param timeRange 时间范围（映射为 start_date 查询参数）
   * @returns 健康数据数组
   */
  getUserHealthData: async (userId: string, timeRange?: string): Promise<HealthData[]> => {
    const params: Record<string, string> = { patient_id: userId };

    if (timeRange) {
      const days = ({ day: 1, week: 7, month: 30, year: 365 } as Record<string, number>)[timeRange];
      if (days) {
        params.start_date = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
      }
    }

    const response = await api.get('health-records/health-data', { params });

    // 后端该端点直接返回数组；兼容可能的 {status, data} 包装
    const rows: BackendHealthDataRow[] = Array.isArray(response.data)
      ? response.data
      : (response.data?.data ?? []);

    return rows.flatMap((row): HealthData[] => {
      // 仅映射生命体征类数据；其余 data_type（lab_result 等）不属于本服务前端类型
      if (row.data_type !== 'vital_sign') return [];

      const mappedType = vitalTypeToHealthDataType[String(row.data?.type ?? '')];
      if (!mappedType) return [];

      return [
        {
          id: row.id,
          type: mappedType,
          value: (row.data?.value ?? '') as number | string,
          unit: row.data?.unit ?? '',
          timestamp: row.recorded_at,
          deviceId: row.device_id ?? undefined,
          userId: row.patient_id,
          notes: row.data?.notes ?? undefined
        }
      ];
    });
  },

  /**
   * 获取用户仪表盘配置
   *
   * 后端暂无仪表盘配置端点（全库无 dashboard/widget 配置路由），
   * 返回前端默认布局；defaultWidgets 是界面默认配置，不是模拟业务数据。
   * 后端补齐配置端点后应改为真实读取。
   *
   * @param userId 用户ID
   * @returns 仪表盘配置
   */
  getUserDashboardConfig: async (_userId: string): Promise<WidgetConfig[]> => {
    return defaultWidgets;
  },

  /**
   * 保存用户健康仪表盘配置
   *
   * 后端暂无仪表盘配置端点，无法持久化：如实返回 false（不再假造保存成功）。
   * 后端补齐端点后应改为真实提交。
   *
   * @param userId 用户ID
   * @param widgets 控件配置数组
   * @returns 是否成功
   */
  saveUserDashboardConfig: async (_userId: string, _widgets: WidgetConfig[]): Promise<boolean> => {
    return false;
  }
};

export default healthDataService; 