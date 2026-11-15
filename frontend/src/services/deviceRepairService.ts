import api from './httpClient';

// T77 设备维修记录：消费后端只读端点（backend/app/api/routers/device_repair_router.py）。
// 后端能力边界：仅 GET history / {repair_id} / device/{id}/summary 三个只读端点，
// 不存在维修登记（创建/修改/删除）端点，授权为医疗 staff（doctor/health_manager/admin）
// 只读守卫 _ensure_repair_log_read_access。故本服务只读，不提供登记入口。

// 维修记录（后端返回 Dict，字段按 device_repair_logs 文档透传；已知核心字段显式声明）
export interface DeviceRepairRecord {
  _id: string;
  device_id?: string;
  repair_time?: string;
  /** 整体修复是否成功（后端按该字段过滤 success 参数） */
  overall_success?: boolean;
  /** 触发的修复动作列表 */
  repair_actions?: string[];
  [key: string]: unknown;
}

// 设备修复统计摘要（GET /device-repairs/device/{device_id}/summary）
export interface DeviceRepairSummary {
  device_id: string;
  total_repairs: number;
  successful_repairs: number;
  failed_repairs: number;
  success_rate: number;
  common_issues: Array<{ action: string; count: number }>;
  latest_repair_time?: string | null;
  days_analyzed: number;
}

export interface RepairHistoryQuery {
  deviceId?: string;
  /** true=仅成功 / false=仅失败；不传=全部 */
  success?: boolean;
  /** 查询最近多少天（后端默认 30） */
  days?: number;
  /** 返回条数上限（后端默认 50） */
  limit?: number;
}

export const deviceRepairService = {
  /** 修复历史列表（非 admin 角色后端会自动收敛到其归属患者设备范围） */
  listHistory: async (query: RepairHistoryQuery = {}): Promise<DeviceRepairRecord[]> => {
    const { data } = await api.get('/device-repairs/history', {
      params: {
        device_id: query.deviceId,
        success: query.success,
        days: query.days,
        limit: query.limit,
      },
    });
    return Array.isArray(data) ? data : [];
  },

  /** 单条维修记录详情 */
  getDetail: async (repairId: string): Promise<DeviceRepairRecord> => {
    const { data } = await api.get(`/device-repairs/${encodeURIComponent(repairId)}`);
    return data;
  },

  /** 指定设备的修复统计摘要（后端默认分析最近 90 天） */
  getDeviceSummary: async (deviceId: string, days?: number): Promise<DeviceRepairSummary> => {
    const { data } = await api.get(`/device-repairs/device/${encodeURIComponent(deviceId)}/summary`, {
      params: { days },
    });
    return data;
  },
};
