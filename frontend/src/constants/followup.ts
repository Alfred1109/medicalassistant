import type { ChipProps } from '@mui/material';

export const followUpTypes = [
  { value: 'phone', label: '电话随访' },
  { value: 'online', label: '线上随访' },
  { value: 'onsite', label: '门诊随访' },
  { value: 'home_visit', label: '家庭访视' },
  { value: 'remote_monitoring', label: '远程监测' },
  { value: 'group', label: '小组随访' },
  { value: 'other', label: '其他' },
] as const;

// Display/filter metadata only. Transitions remain server-side domain operations.
export const followUpStatuses = [
  { value: 'pending_schedule', label: '待安排', color: 'default' },
  { value: 'scheduled', label: '已计划', color: 'primary' },
  { value: 'awaiting_fill', label: '待填写', color: 'info' },
  { value: 'in_review', label: '待医护审阅', color: 'warning' },
  { value: 'completed', label: '已完成', color: 'success' },
  { value: 'canceled', label: '已取消', color: 'error' },
  { value: 'missed', label: '已错过', color: 'warning' },
  { value: 'overdue', label: '已逾期', color: 'warning' },
  { value: 'lost', label: '已失访', color: 'error' },
  { value: 'rescheduled', label: '已重新安排', color: 'info' },
] as const;

export function getFollowUpStatusInfo(status: string): { label: string; color: ChipProps['color'] } {
  const entry = followUpStatuses.find(item => item.value === status);
  return entry ?? { label: status, color: 'default' };
}

export function getFollowUpTypeLabel(type: string): string {
  return followUpTypes.find(item => item.value === type)?.label ?? type;
}

export const manualEntryText = {
  action: '提交手工录入',
  confirmation: '提交后进入待医护审阅，审阅通过后才算完成随访。',
  success: '手工录入已提交，待医护审阅',
} as const;
