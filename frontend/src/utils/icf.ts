// ICF 工作台（T71）共享纯逻辑：类目展示、限定值校验、域分组、指标结果摘要。
//
// 临床口径说明：类目字典、指标阈值与判定均为后端可配置默认值，统一标注
// 「待临床确认，可后台维护」；本文件只做展示与校验，不硬编码临床判定。
import type { AxiosError } from 'axios';
// 类目/条目/指标行类型单属主在 services/icfService（与后端契约对齐），此处仅 re-export。
import type { IcfCategory, IcfItem, IcfMetricRow } from '../services/icfService';

export type { IcfCategory, IcfItem, IcfMetricRow };

export const ICF_DOMAINS = ['body', 'activity', 'participation'] as const;
export type IcfDomain = typeof ICF_DOMAINS[number];

export const ICF_DOMAIN_LABELS: Record<IcfDomain, string> = {
  body: '身体功能',
  activity: '活动',
  participation: '参与',
};

export const ICF_QUALIFIER_LABELS: Record<number, string> = {
  0: '无问题',
  1: '轻度',
  2: '中度',
  3: '重度',
  4: '完全',
};

export const ICF_PENDING_CONFIRMATION_NOTE = '字典口径待临床确认，可后台维护。';

export interface IcfItemInput {
  code: string;
  qualifier: number | string;
  note?: string;
}

// 限定值展示：数值 0-4 用固定中文标签，定性按录入原样。
export function icfQualifierLabel(qualifier: number | string | undefined): string {
  if (typeof qualifier === 'number' && Number.isInteger(qualifier)
      && qualifier >= 0 && qualifier <= 4) return ICF_QUALIFIER_LABELS[qualifier];
  if (typeof qualifier === 'number') return String(qualifier);
  return (qualifier ?? '').toString();
}

// 录入校验：至少一项、编码重复拒绝、限定值必须 0-4 整数或非空定性文本。
export function validateIcfItems(items: IcfItemInput[]): IcfItemInput[] {
  const normalized = (items ?? []).map(item => ({
    code: (item?.code ?? '').toString().trim().toLowerCase(),
    qualifier: item?.qualifier,
    note: (item?.note ?? '').toString(),
  })).filter(item => item.code);
  if (normalized.length === 0) throw new Error('至少录入一个 ICF 类目限定值。');
  const seen = new Set<string>();
  for (const item of normalized) {
    if (seen.has(item.code)) throw new Error(`类目编码 ${item.code} 重复录入。`);
    seen.add(item.code);
    const qualifier = item.qualifier;
    if (typeof qualifier === 'number') {
      if (!Number.isInteger(qualifier) || qualifier < 0 || qualifier > 4) {
        throw new Error(`类目 ${item.code} 的限定值必须是 0-4 的整数。`);
      }
    } else if (typeof qualifier === 'string') {
      const text = qualifier.trim();
      if (!text || text.length > 20) {
        throw new Error(`类目 ${item.code} 的定性限定值需要 1-20 个字符。`);
      }
      item.qualifier = text;
    } else {
      throw new Error(`类目 ${item.code} 的限定值缺失或类型无效。`);
    }
  }
  return normalized;
}

// 域分组：未标注域的条目归入身体功能，保证展示完整。
export function groupIcfItemsByDomain(items: IcfItem[]): Record<IcfDomain, IcfItem[]> {
  const grouped: Record<IcfDomain, IcfItem[]> = { body: [], activity: [], participation: [] };
  for (const item of items ?? []) {
    const domain = (ICF_DOMAINS as readonly string[]).includes(item?.domain)
      ? (item.domain as IcfDomain) : 'body';
    grouped[domain].push(item);
  }
  return grouped;
}

export const ICF_METRIC_STATE_LABELS: Record<string, string> = {
  ok: '正常',
  alert: '触发预警',
  insufficient_data: '数据不足',
  disabled: '已停用',
  unsupported: '未知定义',
};

export function icfMetricStateLabel(state: string): string {
  return ICF_METRIC_STATE_LABELS[state] ?? state;
}

export function icfMetricValueText(metric: IcfMetricRow): string {
  if (metric.state === 'alert' || metric.state === 'ok') {
    if (metric.metric_key === 'attainment_rate' || metric.metric_key === 'followup_completion_rate') {
      return typeof metric.value === 'number' ? `${Math.round(metric.value * 100)}%` : '—';
    }
    if (metric.metric_key === 'qualifier_improvement') {
      return typeof metric.value === 'number' ? `${metric.value} 个类目未达标` : '—';
    }
  }
  return '—';
}

// 类目表单校验：编码 1-20 字符（小写字母+数字）、名称 1-80、域必须三域之一。
export function validateIcfCategory(code: string, name: string, domain: string): void {
  const normalizedCode = (code ?? '').trim().toLowerCase();
  if (!/^[a-z][a-z0-9]{1,19}$/.test(normalizedCode)) {
    throw new Error('类目编码需以字母开头，1-20 位字母或数字（如 b130、d450）。');
  }
  const normalizedName = (name ?? '').trim();
  if (!normalizedName || normalizedName.length > 80) throw new Error('类目名称需 1-80 个字符。');
  if (!(ICF_DOMAINS as readonly string[]).includes(domain)) {
    throw new Error('域分类必须是身体功能、活动或参与。');
  }
}

// 后端错误文案：409 冲突 / 403 授权 / 404 不存在优先，其余回退后端 message。
export function icfError(error: unknown, fallback: string): string {
  const response = (error as AxiosError<{detail?: unknown; message?: string}>)?.response;
  if (response?.status === 409) return '记录已变化或本次请求发生冲突，请重新加载核对后再操作。';
  if (response?.status === 403) return '当前账号无权查看或处理这些记录。';
  if (response?.status === 404) return '记录不存在或当前不可访问。';
  if (typeof response?.data?.detail === 'string') return response.data.detail;
  if (typeof response?.data?.message === 'string') return response.data.message;
  return fallback;
}
