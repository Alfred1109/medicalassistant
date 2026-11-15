import api from './httpClient';

// T77 方案版本历史：消费后端 REH01 结构化端点
// （backend/app/api/routers/rehabilitation_router.py:650-698，
// 授权为对象级 patient_access，与方案详情一致）。

// 版本列表条目（GET /rehabilitation/plans/{plan_id}/versions，
// 服务端按 version_no 倒序；见 rehab_plan_structure_service.list_plan_versions）
export interface PlanVersionSummary {
  _id: string;
  plan_id: string;
  version_no: number;
  status?: string;
  /** 创建版本时填写的人类可读变更摘要（可为空） */
  note?: string | null;
  /** 本版本内新增的处方项 item_id 列表 */
  item_ids?: string[];
  created_by?: string | null;
  created_at?: string;
  updated_at?: string;
}

// 版本详情（GET /rehabilitation/plans/{plan_id}/versions/{version_id}），
// snapshot 为创建版本时对方案白名单字段（name/description/goal/condition/
// frequency/start_date/end_date/exercises/notes）的深拷贝快照
export interface PlanVersionDetail extends PlanVersionSummary {
  snapshot?: Record<string, unknown> | null;
  center_id?: string | null;
  project_id?: string | null;
  reviewed_by?: string | null;
  review_note?: string | null;
}

// 处方项（GET /rehabilitation/plans/{plan_id}/items?version_id=...），
// item_id 由服务端分配且跨版本稳定
export interface PrescriptionItem {
  item_id: string;
  version_id?: string;
  name?: string;
  intervention_type?: string;
  [key: string]: unknown;
}

export const planVersionService = {
  /** 列出方案全部版本（version_no 倒序） */
  listVersions: async (planId: string, limit = 100): Promise<PlanVersionDetail[]> => {
    const { data } = await api.get(`/rehabilitation/plans/${encodeURIComponent(planId)}/versions`, {
      params: { limit },
    });
    return Array.isArray(data) ? data : [];
  },

  /** 读取单个版本（含内容快照） */
  getVersion: async (planId: string, versionId: string): Promise<PlanVersionDetail> => {
    const { data } = await api.get(
      `/rehabilitation/plans/${encodeURIComponent(planId)}/versions/${encodeURIComponent(versionId)}`,
    );
    return data;
  },

  /** 列出方案的处方项（可按版本过滤） */
  listItems: async (planId: string, versionId?: string, limit = 200): Promise<PrescriptionItem[]> => {
    const { data } = await api.get(`/rehabilitation/plans/${encodeURIComponent(planId)}/items`, {
      params: { version_id: versionId, limit },
    });
    return Array.isArray(data) ? data : [];
  },
};

// ── 快照 / 处方项差异（纯函数，便于测试与复用）──────────────────────────

export interface SnapshotFieldDiff {
  field: string;
  baseValue: string;
  targetValue: string;
  changed: boolean;
}

const renderValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '（空）';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
};

/** 对两个版本快照按白名单字段逐项对比（未出现的字段按“（空）”处理） */
export const diffSnapshotFields = (
  base: Record<string, unknown> | null | undefined,
  target: Record<string, unknown> | null | undefined,
  fields: string[] = ['name', 'description', 'goal', 'condition', 'frequency', 'start_date', 'end_date', 'notes'],
): SnapshotFieldDiff[] =>
  fields.map((field) => {
    const baseValue = renderValue(base?.[field]);
    const targetValue = renderValue(target?.[field]);
    return { field, baseValue, targetValue, changed: baseValue !== targetValue };
  });

export interface ItemDiffEntry {
  item_id: string;
  base?: PrescriptionItem;
  target?: PrescriptionItem;
}

export interface PrescriptionItemDiff {
  added: ItemDiffEntry[];
  removed: ItemDiffEntry[];
  changed: ItemDiffEntry[];
  unchangedCount: number;
}

// 参与对比的字段：排除随版本变化的归属字段（_id/version_id），item_id 稳定
const ITEM_DIFF_SKIP_KEYS = new Set(['_id', 'version_id']);

const itemFingerprint = (item: PrescriptionItem): string => {
  const rest: Record<string, unknown> = {};
  Object.keys(item)
    .filter((key) => !ITEM_DIFF_SKIP_KEYS.has(key))
    .sort()
    .forEach((key) => { rest[key] = item[key]; });
  return JSON.stringify(rest);
};

/** 按 item_id 对比两个版本的处方项：新增/移除/变更/未变 */
export const diffPrescriptionItems = (
  baseItems: PrescriptionItem[],
  targetItems: PrescriptionItem[],
): PrescriptionItemDiff => {
  const baseById = new Map(baseItems.filter((item) => item.item_id).map((item) => [item.item_id, item]));
  const targetById = new Map(targetItems.filter((item) => item.item_id).map((item) => [item.item_id, item]));
  const result: PrescriptionItemDiff = { added: [], removed: [], changed: [], unchangedCount: 0 };
  targetById.forEach((targetItem, itemId) => {
    const baseItem = baseById.get(itemId);
    if (!baseItem) result.added.push({ item_id: itemId, target: targetItem });
    else if (itemFingerprint(baseItem) !== itemFingerprint(targetItem)) {
      result.changed.push({ item_id: itemId, base: baseItem, target: targetItem });
    } else result.unchangedCount += 1;
  });
  baseById.forEach((baseItem, itemId) => {
    if (!targetById.has(itemId)) result.removed.push({ item_id: itemId, base: baseItem });
  });
  return result;
};
