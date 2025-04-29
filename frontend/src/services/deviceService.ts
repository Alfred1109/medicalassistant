import { apiService } from './api';
import api from './api';

// 设备类型定义
export interface Device {
  id: string;
  name: string;
  type: '血压计' | '血糖仪' | '体温计' | '心电图' | '体重秤' | '手环' | '其他';
  status: 'online' | 'offline' | 'error' | 'syncing';
  batteryLevel: number;
  signalStrength: number; // 1-5
  lastSyncTime: string;
  nextSyncTime?: string;
  firmwareVersion: string;
  firmwareUpdateAvailable: boolean;
  errorMessage?: string;
  connectionType: 'bluetooth' | 'wifi' | 'cable';
  patientId: string;
  patientName: string;
}

// 设备数据类型定义
export interface DeviceData {
  id: string;
  deviceId: string;
  timestamp: string;
  dataType: string;
  value: any;
  unit: string;
  metadata?: Record<string, any>;
}

// 设备配置类型定义
export interface DeviceConfig {
  deviceId: string;
  syncFrequency: 'realtime' | 'hourly' | 'daily' | 'manual';
  notificationsEnabled: boolean;
  customName?: string;
  alarmSettings?: Record<string, any>;
}

// 设备服务
const deviceService = {
  // 获取用户绑定的设备列表
  getUserDevices: async (userId: string): Promise<Device[]> => {
    try {
      const response = await apiService.getUserDevices(userId);
      return response.data;
    } catch (error) {
      console.error('获取用户设备列表失败:', error);
      throw error;
    }
  },

  // 绑定新设备
  bindDevice: async (userId: string, deviceData: Omit<Device, 'id' | 'status' | 'lastSyncTime' | 'batteryLevel' | 'signalStrength'>): Promise<Device> => {
    try {
      const response = await apiService.bindUserDevice(userId, deviceData);
      return response.data;
    } catch (error) {
      console.error('绑定设备失败:', error);
      throw error;
    }
  },

  // 解绑设备
  unbindDevice: async (userId: string, deviceId: string): Promise<void> => {
    try {
      await apiService.unbindUserDevice(userId, deviceId);
    } catch (error) {
      console.error('解绑设备失败:', error);
      throw error;
    }
  },

  // 获取设备数据
  getDeviceData: async (deviceId: string, params?: { startDate?: string; endDate?: string; limit?: number; dataType?: string }): Promise<DeviceData[]> => {
    try {
      const response = await apiService.getDeviceData(deviceId, params);
      return response.data;
    } catch (error) {
      console.error('获取设备数据失败:', error);
      throw error;
    }
  },

  // 同步设备数据
  syncDeviceData: async (deviceId: string): Promise<{ success: boolean; message: string; newData?: DeviceData[] }> => {
    try {
      const response = await apiService.syncDeviceData(deviceId);
      return response.data;
    } catch (error) {
      console.error('同步设备数据失败:', error);
      throw error;
    }
  },

  // 获取设备状态
  getDeviceStatus: async (deviceId: string): Promise<{ status: Device['status']; batteryLevel: number; signalStrength: number; lastSyncTime: string }> => {
    try {
      const response = await apiService.getDeviceStatus(deviceId);
      return response.data;
    } catch (error) {
      console.error('获取设备状态失败:', error);
      throw error;
    }
  },

  // 配置设备
  configureDevice: async (deviceId: string, config: DeviceConfig): Promise<{ success: boolean; message: string }> => {
    try {
      const response = await apiService.configureDevice(deviceId, config);
      return response.data;
    } catch (error) {
      console.error('配置设备失败:', error);
      throw error;
    }
  },

  // 模拟扫描设备（仅用于演示）
  scanForDevices: async (): Promise<Device[]> => {
    // 模拟API调用延迟
    return new Promise((resolve) => {
      setTimeout(() => {
        const mockDevices: Device[] = [
          {
            id: 'bt-123456',
            name: '智能手环 Pro',
            type: '手环',
            status: 'online',
            batteryLevel: 85,
            signalStrength: 4,
            lastSyncTime: new Date().toISOString(),
            firmwareVersion: '2.1.3',
            connectionType: 'bluetooth',
            firmwareUpdateAvailable: false,
            patientId: '',
            patientName: ''
          },
          {
            id: 'bt-654321',
            name: '血压监测仪',
            type: '血压计',
            status: 'offline',
            batteryLevel: 92,
            signalStrength: 3,
            lastSyncTime: new Date(Date.now() - 86400000).toISOString(), // 一天前
            firmwareVersion: '1.5.0',
            connectionType: 'bluetooth',
            firmwareUpdateAvailable: true,
            patientId: '',
            patientName: ''
          },
          {
            id: 'wifi-abcdef',
            name: '智能体重秤',
            type: '体重秤',
            status: 'online',
            batteryLevel: 76,
            signalStrength: 5,
            lastSyncTime: new Date(Date.now() - 3600000).toISOString(), // 一小时前
            firmwareVersion: '3.0.2',
            connectionType: 'wifi',
            firmwareUpdateAvailable: false,
            patientId: '',
            patientName: ''
          }
        ];
        
        resolve(mockDevices);
      }, 2000);
    });
  },

  // 模拟设备连接（仅用于演示）
  connectToDevice: async (deviceId: string): Promise<{ success: boolean; message: string }> => {
    // 模拟API调用延迟
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        // 模拟90%成功率
        if (Math.random() > 0.1) {
          resolve({
            success: true,
            message: '设备连接成功'
          });
        } else {
          reject({
            success: false,
            message: '连接设备失败，请确保设备已开启并在范围内'
          });
        }
      }, 2000);
    });
  },

  // 模拟测试设备连接（仅用于演示）
  testDeviceConnection: async (deviceId: string): Promise<{ success: boolean; message: string; details?: any }> => {
    // 模拟API调用延迟
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        // 模拟85%成功率
        if (Math.random() > 0.15) {
          resolve({
            success: true,
            message: '设备连接正常，数据同步测试成功',
            details: {
              latency: Math.floor(Math.random() * 100),
              dataTransferRate: Math.floor(500 + Math.random() * 1000) + 'kbps',
              batteryLevel: Math.floor(70 + Math.random() * 30) + '%'
            }
          });
        } else {
          reject({
            success: false,
            message: '设备数据同步测试失败，请检查网络连接或设备状态',
            details: {
              errorCode: 'ERR_DATA_SYNC_TIMEOUT',
              retryRecommended: true
            }
          });
        }
      }, 2500);
    });
  },
  
  // 获取设备异常预警
  getDeviceAnomalies: async (userId: string, timeRange?: string): Promise<any[]> => {
    try {
      const response = await api.get(`/devices/anomalies`, {
        params: { 
          user_id: userId,
          time_range: timeRange || 'week'
        }
      });
      return response.data;
    } catch (error) {
      console.error('获取设备异常预警失败:', error);
      throw error;
    }
  }
};

export { deviceService }; 