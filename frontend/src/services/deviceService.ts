import { apiService } from './api';
import api from './api';

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
  /** 医护及管理员需明确选择患者；患者可省略以绑定本人。 */
  patient_id?: string;
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
  getPatientDevices: async (patientId: string): Promise<Device[]> => {
    if (!patientId) throw new Error('请先选择患者');
    const response = await apiService.getPatientDevices(patientId);
    if (!Array.isArray(response.data) || response.data.some((device: Device) => device.patient_id !== patientId)) {
      throw new Error('设备所属患者与当前选择不一致，请重新核实');
    }
    return response.data;
  },

  // 获取当前账号有权管理的患者设备（GET /api/devices）
  getUserDevices: async (): Promise<Device[]> => {
    try {
      const response = await apiService.getUserDevices();
      return response.data;
    } catch (error) {
      console.error('获取用户设备列表失败:', error);
      throw error;
    }
  },

  // 绑定设备到患者（POST /api/devices/bind，医护需要提供 patient_id）
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
  recordReading: async (deviceId: string, body: { data_type: string; value: string; unit: string; measured_at: string }) => {
    const response = await apiService.recordDeviceReading(deviceId, body);
    return response.data;
  },

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

// ══ T74 设备数据接入网关（自动采集）══════════════════════════════════════

// 自动采集读数条目（对齐网关入库的 device_data 文档）
export interface AutomatedReading {
  id?: string;
  timestamp: string;
  data_type: string;
  value: number;
  unit: string;
  quality_flags?: string[] | null;
  metadata?: {
    source?: string; // automated / automated_simulated_replay / 手工登记
    session_id?: string | null;
    simulated?: boolean;
  } | null;
}

// 质量报告（GET /devices/{id}/quality-report）
export interface DeviceQualityReport {
  device_id: string;
  window: { start: string | null; end: string | null };
  total_automated: number;
  passed: number;
  flagged: number;
  pass_rate: number | null;
  flags: Record<string, number>;
  out_of_range_count: number;
}

// 采集会话（POST/GET /devices/{id}/sessions）
export interface CollectionSession {
  _id: string;
  device_id: string;
  device_sn?: string | null;
  patient_id: string;
  status: string; // active / ended / cancelled
  plan_id?: string | null;
  exercise_id?: string | null;
  linkage_status: 'linked' | 'registered' | 'none';
  linkage_error?: string | null;
  started_at: string;
  ended_at?: string | null;
  summary?: Record<string, any> | null;
  notes?: string | null;
}

// 协议假设条目（GET /devices/{id}/gateway/protocol-assumptions）
export interface ProtocolAssumption {
  claim: string;
  verify: string;
  impact: string;
}

export interface ProtocolAssumptionsResponse {
  device_id: string;
  model: string | null;
  adapter_id: string | null;
  message?: string;
  assumptions: ProtocolAssumption[];
}

// 网关上报响应（readings 数组含逐条 written/duplicate/rejected 结果）
export interface GatewayIngestResult {
  success: boolean;
  device: { id: string; device_sn: string };
  accepted_count: number;
  duplicate_count: number;
  rejected_count: number;
  readings: Array<{
    action: 'written' | 'duplicate' | 'rejected';
    frame_index: number;
    data_type: string;
    timestamp: string;
    quality_flags: string[];
    reason?: string;
    error?: string;
  }>;
}

const deviceGateway = {
  // 自动采集数据（复用 GET /devices/{id}/data，前端按来源过滤展示）
  getAutomatedReadings: async (deviceId: string, limit = 50): Promise<AutomatedReading[]> => {
    const response = await api.get(`/devices/${deviceId}/data`, {
      params: { limit },
    });
    const rows: AutomatedReading[] = Array.isArray(response.data) ? response.data : [];
    return rows.filter(
      (row) => row.metadata?.source === 'automated' || row.metadata?.source === 'automated_simulated_replay',
    );
  },

  getQualityReport: async (
    deviceId: string,
    params?: { start?: string; end?: string },
  ): Promise<DeviceQualityReport> => {
    const response = await api.get(`/devices/${deviceId}/quality-report`, { params });
    return response.data;
  },

  startCollectionSession: async (
    deviceId: string,
    body: { plan_id?: string; exercise_id?: string; notes?: string },
  ): Promise<CollectionSession> => {
    const response = await api.post(`/devices/${deviceId}/sessions`, body);
    return response.data;
  },

  endCollectionSession: async (deviceId: string, sessionId: string, cancel = false): Promise<CollectionSession> => {
    const response = await api.post(`/devices/${deviceId}/sessions/${sessionId}/end`, null, {
      params: { cancel },
    });
    return response.data;
  },

  listCollectionSessions: async (deviceId: string, limit = 50): Promise<CollectionSession[]> => {
    const response = await api.get(`/devices/${deviceId}/sessions`, { params: { limit } });
    return Array.isArray(response.data) ? response.data : [];
  },

  getProtocolAssumptions: async (deviceId: string): Promise<ProtocolAssumptionsResponse> => {
    const response = await api.get(`/devices/${deviceId}/gateway/protocol-assumptions`);
    return response.data;
  },

  // 模拟数据回放（仅 admin，测试/演示；读数带 simulated 标记）
  replaySimulated: async (deviceId: string, frameCount = 4): Promise<GatewayIngestResult> => {
    const response = await api.post(
      `/devices/${deviceId}/gateway/replay-simulated`,
      null,
      { params: { frame_count: frameCount } },
    );
    return response.data;
  },
};

export { deviceGateway };
