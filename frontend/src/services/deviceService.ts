import { apiService } from './api';

// 设备类型定义（与后端 DeviceResponse 字段对齐，snake_case）
export interface Device {
  id: string;
  device_type: string;
  name: string;
  manufacturer?: string | null;
  model?: string | null;
  connection_type?: string | null;
  firmware_version?: string | null;
  patient_id?: string | null;
  status: string; // 'online' | 'offline' | 'error' ...
  last_connected?: string | null;
  battery_level?: number | null;
  settings?: Record<string, any> | null;
  created_at?: string;
  updated_at?: string;
}

// 绑定设备提交载荷（与后端 DeviceCreate 对齐：device_type / name 必填）
export interface DeviceCreatePayload {
  device_type: string;
  name: string;
  manufacturer?: string;
  model?: string;
  connection_type?: string;
  firmware_version?: string;
  settings?: Record<string, any>;
}

// 设备数据条目（与后端 DeviceDataResponse 对齐）
export interface DeviceDataItem {
  id: string;
  device_id: string;
  timestamp: string;
  data_type: string;
  value: any;
  unit: string;
  metadata?: Record<string, any> | null;
  created_at?: string;
}

// 设备状态（与后端 DeviceStatusResponse 对齐）
export interface DeviceStatus {
  status: string;
  battery_level: number;
  signal_strength: number;
  last_sync_time?: string | null;
  message?: string | null;
}

// 设备配置类型定义
export interface DeviceConfig {
  syncFrequency: 'realtime' | 'hourly' | 'daily' | 'manual';
  notificationsEnabled: boolean;
  customName?: string;
  alarmSettings?: Record<string, any>;
}

// 设备服务（全部对接真实后端 /api/devices 接口）
const deviceService = {
  // 获取当前登录用户绑定的设备列表（GET /api/devices）
  getUserDevices: async (): Promise<Device[]> => {
    try {
      const response = await apiService.getUserDevices();
      return response.data;
    } catch (error) {
      console.error('获取用户设备列表失败:', error);
      throw error;
    }
  },

  // 绑定新设备到当前登录用户（POST /api/devices/bind，device_type / name 必填）
  bindDevice: async (deviceData: DeviceCreatePayload): Promise<Device> => {
    try {
      const response = await apiService.bindUserDevice('', deviceData);
      return response.data;
    } catch (error) {
      console.error('绑定设备失败:', error);
      throw error;
    }
  },

  // 解绑设备（DELETE /api/devices/{id}/unbind）
  unbindDevice: async (deviceId: string): Promise<void> => {
    try {
      await apiService.unbindUserDevice('', deviceId);
    } catch (error) {
      console.error('解绑设备失败:', error);
      throw error;
    }
  },

  // 获取设备数据（GET /api/devices/{id}/data，支持 start_date / end_date / data_type / limit）
  getDeviceData: async (
    deviceId: string,
    params?: { startDate?: string; endDate?: string; limit?: number; dataType?: string }
  ): Promise<DeviceDataItem[]> => {
    try {
      const response = await apiService.getDeviceData(deviceId, params);
      return response.data;
    } catch (error) {
      console.error('获取设备数据失败:', error);
      throw error;
    }
  },

  // 同步设备数据（POST /api/devices/{id}/sync，返回后端 device_service 的同步结果）
  syncDeviceData: async (
    deviceId: string
  ): Promise<{ success: boolean; message: string; new_data?: any[]; [key: string]: any }> => {
    try {
      const response = await apiService.syncDeviceData(deviceId);
      return response.data;
    } catch (error) {
      console.error('同步设备数据失败:', error);
      throw error;
    }
  },

  // 获取设备状态（GET /api/devices/{id}/status）
  getDeviceStatus: async (deviceId: string): Promise<DeviceStatus> => {
    try {
      const response = await apiService.getDeviceStatus(deviceId);
      return response.data;
    } catch (error) {
      console.error('获取设备状态失败:', error);
      throw error;
    }
  },

  // 配置设备（PUT /api/devices/{id}/config）
  configureDevice: async (
    deviceId: string,
    config: DeviceConfig
  ): Promise<{ success: boolean; message: string }> => {
    try {
      const response = await apiService.configureDevice(deviceId, config);
      return response.data;
    } catch (error) {
      console.error('配置设备失败:', error);
      throw error;
    }
  },

  // 修复设备异常（POST /api/devices/{id}/repair，返回真实的修复动作与结果）
  repairDevice: async (deviceId: string): Promise<{
    success: boolean;
    message: string;
    repair_actions?: string[];
    repair_results?: Array<{ action: string; success: boolean; message?: string; reason?: string }>;
    new_status?: any;
  }> => {
    try {
      const response = await apiService.repairDevice(deviceId);
      return response.data;
    } catch (error) {
      console.error('修复设备失败:', error);
      throw error;
    }
  }
};

export { deviceService };
