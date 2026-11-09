import type { Notification } from '../services/notificationService';

const FOLLOWUP_ROLES = new Set(['patient', 'doctor', 'health_manager', 'admin']);

export function validFollowUpId(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f\d]{24}$/i.test(value);
}

/** Notification content is untrusted: only a known entity can select a route. */
export function notificationTarget(notification: Notification, role: string | undefined): string | null {
  if (!role || !FOLLOWUP_ROLES.has(role) || notification.notification_type !== 'followup' ||
      notification.related_entity_type !== 'followup' || !validFollowUpId(notification.related_entity_id)) return null;
  return `/app/follow-ups/${notification.related_entity_id.toLowerCase()}`;
}

export function canReadFollowUp(role: string | undefined): boolean {
  return !!role && FOLLOWUP_ROLES.has(role);
}

export function followUpDetailError(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 401) return '登录已失效，请重新登录后查看。';
  if (status === 403) return '当前无权查看此随访，患者归属或访问权限可能已变更。';
  if (status === 404) return '此随访不存在或已移除。';
  return '随访详情加载失败，请重试。';
}

/** Mongo BSON dates are UTC; legacy API responses omit their UTC suffix. */
export function formatFollowUpSchedule(value: string, timeZone?: string): string {
  if (!value) return '未提供';
  const iso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$/i;
  if (!iso.test(value)) return `${value}（原始时间，未转换）`;
  const withZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
  const date = new Date(withZone);
  if (Number.isNaN(date.getTime())) return `${value}（原始时间，未转换）`;
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    second: '2-digit', hourCycle: 'h23', timeZoneName: 'longOffset',
  }).format(date).replace(/GMT/g, 'UTC');
}
