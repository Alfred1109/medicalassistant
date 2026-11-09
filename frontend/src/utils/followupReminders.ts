import type { FollowUpReminderStatus } from '../types/followupReminders';

const reasons: Record<string, string> = {
  PATIENT_ACCOUNT_UNAVAILABLE: '患者没有可用的登录账号，因此未生成本次提醒。',
  PROVIDER_ACCOUNT_UNAVAILABLE: '责任医护账号不可用，因此未生成本次提醒。',
  PROVIDER_NOT_ASSIGNED: '责任医护当前未分配管理该患者，因此未生成本次提醒。',
  PLAN_PASSED: '计划时间已过，未补发提醒。',
  PERSISTENCE_FAILED: '站内通知暂未能保存，计划时间前会自动重试；已过计划时间不会补发。',
};

export function reminderReason(reason: string | null | undefined) {
  return reason && reasons[reason] ? reasons[reason] : '未提供可识别的处理原因，请联系管理员核查。';
}

export function reminderServiceInfo(status: FollowUpReminderStatus): { severity: 'success' | 'warning' | 'error' | 'info'; text: string } {
  if (!status.enabled) return { severity: 'warning', text: '随访提醒服务未启用，当前不会自动生成站内通知。' };
  if (status.state === 'error') {
    const detail = status.last_error_code === 'REMINDER_PATIENT_DOMAIN_UNSUPPORTED'
      ? '当前患者档案尚未接入提醒账号解析。'
      : status.last_error_code === 'REMINDER_STORAGE_UNAVAILABLE'
        ? '提醒存储或事务条件不可用。' : '最近一次提醒检查失败。';
    return { severity: 'error', text: `随访提醒服务异常：${detail}请联系管理员核查。` };
  }
  if (status.state === 'starting') return { severity: 'info', text: '随访提醒服务正在启动，尚不能确认已完成检查。' };
  if (status.running && status.state === 'ready') return { severity: 'success', text: '随访提醒服务运行中，最近一次检查成功。' };
  return { severity: 'warning', text: '随访提醒服务尚未就绪或未运行，请联系管理员核查。' };
}

/** These endpoints serialize BSON UTC timestamps without an offset. */
export function reminderTime(value: string | null | undefined) {
  if (!value) return '未记录';
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? '时间不可用' : date.toLocaleString('zh-CN', { hour12: false });
}
