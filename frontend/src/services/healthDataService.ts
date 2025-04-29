import { apiService } from './api';
import api from './api';
import { HealthData as BaseHealthData, WidgetConfig as BaseWidgetConfig, DashboardConfig } from '../types/health';

// 健康数据服务扩展类型
export interface HealthData extends BaseHealthData {
  id: string;
  type: 'heart_rate' | 'blood_pressure' | 'blood_glucose' | 'weight' | 'steps' | 'sleep' | 'temperature';
  value: number | string;
  unit: string;
  // 这里保留服务特有的字段
  deviceId?: string;
  deviceName?: string;
}

// 扩展WidgetConfig以兼容服务特定功能
export interface WidgetConfig extends BaseWidgetConfig {
  dataType?: HealthData['type'];
  size?: 'small' | 'medium' | 'large';
  timeRange?: 'day' | 'week' | 'month' | 'year';
  position?: number;
  goal?: number;
  thresholds?: {
    min?: number;
    max?: number;
  };
}

// 健康数据服务
const healthDataService = {
  // 获取患者健康数据
  getHealthData: async (patientId?: string, params?: { timeRange?: string; type?: string; startDate?: string; endDate?: string }) => {
    try {
      if (patientId) {
        const response = await apiService.getHealthData(patientId, params);
        return response.data;
      } else {
        // 获取当前登录用户的健康数据
        const response = await api.get('/health-records/health-data/current-user');
        return response;
      }
    } catch (error) {
      console.error('获取健康数据失败:', error);
      throw error;
    }
  },

  // 获取特定类型的最新健康数据
  getLatestHealthData: async (patientId: string, type: HealthData['type']) => {
    try {
      const response = await apiService.getHealthData(patientId, { limit: 1, type, sort: '-timestamp' });
      return response.data.length > 0 ? response.data[0] : null;
    } catch (error) {
      console.error(`获取${type}最新数据失败:`, error);
      throw error;
    }
  },

  // 创建健康数据记录
  createHealthData: async (data: Omit<HealthData, 'id'>) => {
    try {
      const response = await apiService.createHealthData(data);
      return response.data;
    } catch (error) {
      console.error('创建健康数据失败:', error);
      throw error;
    }
  },

  // 批量创建健康数据记录（例如从设备同步）
  createBatchHealthData: async (dataArray: Omit<HealthData, 'id'>[]) => {
    try {
      const response = await api.post('/health-records/health-data/batch', { data: dataArray });
      return response.data;
    } catch (error) {
      console.error('批量创建健康数据失败:', error);
      throw error;
    }
  },

  // 获取用户的仪表盘配置
  getUserDashboardConfig: async (userId: string): Promise<{ widgets: WidgetConfig[] }> => {
    try {
      const response = await apiService.getUserDashboardConfig(userId);
      return response.data;
    } catch (error) {
      console.error('获取仪表盘配置失败:', error);
      throw error;
    }
  },

  // 保存用户的仪表盘配置
  saveUserDashboardConfig: async (userId: string, config: { widgets: WidgetConfig[] }) => {
    try {
      const response = await apiService.saveUserDashboardConfig(userId, config);
      return response.data;
    } catch (error) {
      console.error('保存仪表盘配置失败:', error);
      throw error;
    }
  },

  // 重置用户的仪表盘配置为默认值
  resetUserDashboardConfig: async (userId: string) => {
    try {
      const response = await apiService.resetUserDashboardConfig(userId);
      return response.data;
    } catch (error) {
      console.error('重置仪表盘配置失败:', error);
      throw error;
    }
  },

  // 获取健康数据统计信息
  getHealthDataStats: async (patientId: string, params?: { type?: string; startDate?: string; endDate?: string }) => {
    try {
      const response = await api.get(`/health-records/health-data/stats`, {
        params: { patient_id: patientId, ...params }
      });
      return response.data;
    } catch (error) {
      console.error('获取健康数据统计信息失败:', error);
      throw error;
    }
  },

  // 获取健康数据阈值
  getHealthDataThresholds: async (patientId: string) => {
    try {
      const response = await api.get(`/health-records/thresholds`, {
        params: { patient_id: patientId }
      });
      return response.data;
    } catch (error) {
      console.error('获取健康数据阈值失败:', error);
      throw error;
    }
  },

  // 设置健康数据阈值
  setHealthDataThreshold: async (patientId: string, type: HealthData['type'], threshold: { min?: number; max?: number; warnMin?: number; warnMax?: number }) => {
    try {
      const response = await api.post(`/health-records/thresholds`, {
        patientId,
        type,
        ...threshold
      });
      return response.data;
    } catch (error) {
      console.error('设置健康数据阈值失败:', error);
      throw error;
    }
  },

  // 以下是为了支持PersonalizedDashboard组件而添加的新方法

  // 获取当前用户的仪表盘配置
  getDashboardConfig: async (): Promise<{ data: DashboardConfig }> => {
    try {
      const response = await api.get('/health-records/dashboard/config');
      return response;
    } catch (error) {
      console.error('获取仪表盘配置失败:', error);
      throw error;
    }
  },

  // 保存当前用户的仪表盘配置
  saveDashboardConfig: async (config: DashboardConfig): Promise<{ data: DashboardConfig }> => {
    try {
      const response = await api.post('/health-records/dashboard/config', config);
      return response;
    } catch (error) {
      console.error('保存仪表盘配置失败:', error);
      throw error;
    }
  },

  // 获取用户的格式化健康数据（与PersonalizedDashboard组件兼容）
  getFormattedHealthData: async (timeRange: string = 'week'): Promise<HealthData[]> => {
    try {
      const response = await api.get('/health-records/health-data/formatted', {
        params: { timeRange }
      });
      return response.data;
    } catch (error) {
      console.error('获取格式化健康数据失败:', error);
      throw error;
    }
  },

  // 转换API数据格式为Dashboard兼容格式
  transformHealthData: (apiData: any[]): HealthData[] => {
    return apiData.map(item => {
      const result: HealthData = {
        id: item.id,
        type: item.type,
        value: item.value,
        unit: item.unit,
        timestamp: item.timestamp
      };

      // 根据类型设置对应的属性
      switch (item.type) {
        case 'heart_rate':
          result.heartRate = Number(item.value);
          break;
        case 'blood_pressure':
          if (item.systolic) result.bloodPressureSystolic = Number(item.systolic);
          if (item.diastolic) result.bloodPressureDiastolic = Number(item.diastolic);
          break;
        case 'blood_glucose':
          result.bloodSugar = Number(item.value);
          break;
        case 'weight':
          result.weight = Number(item.value);
          break;
        case 'temperature':
          result.temperature = Number(item.value);
          break;
        case 'steps':
          result.stepCount = Number(item.value);
          break;
        case 'sleep':
          result.sleepHours = Number(item.value);
          break;
      }

      return result;
    });
  }
};

export default healthDataService; 