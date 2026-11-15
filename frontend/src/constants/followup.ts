import type { ChipProps } from '@mui/material';
import type { FollowUpRecord } from '../types/followup';

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

// T73 状态徽章：overdue/lost 区分自动（后台按规则标记）与人工（metadata 记录操作人）来源。
// 存量手工标记无 source 字段，按 operator_id / recognized_by 存在视为人工。
type DispositionRecord = Pick<FollowUpRecord, 'status' | 'metadata'>;

type OverdueMarker = { source?: string; operator_id?: string | null };
type LostMarker = { source?: string; recognized_by?: string | null;
  restored_at?: string | null; restored_by?: string | null };

export function getOverdueMarker(metadata: FollowUpRecord['metadata']): OverdueMarker | null {
  const marker = metadata?.overdue;
  return marker && typeof marker === 'object' ? marker as OverdueMarker : null;
}

export function getLostMarker(metadata: FollowUpRecord['metadata']): LostMarker | null {
  const marker = metadata?.lost;
  return marker && typeof marker === 'object' ? marker as LostMarker : null;
}

export function getFollowUpStatusBadge(record: DispositionRecord): { label: string; color: ChipProps['color'] } {
  const info = getFollowUpStatusInfo(record.status);
  if (record.status === 'overdue') {
    const marker = getOverdueMarker(record.metadata);
    if (marker?.source === 'automated') return { label: '已逾期（系统自动）', color: 'warning' };
    if (marker?.operator_id) return { label: '已逾期（手工标记）', color: 'warning' };
    return info;
  }
  if (record.status === 'lost') {
    const marker = getLostMarker(record.metadata);
    if (marker?.source === 'automated') return { label: '已失访（系统自动认定）', color: 'error' };
    if (marker?.recognized_by) return { label: '已失访（人工认定）', color: 'error' };
    return info;
  }
  return info;
}

// T73 随访小结展示行（患者端/详情端共用只读呈现；空字段不产出展示行）
export function getFollowUpSummaryRows(summary: FollowUpRecord['followup_summary']): Array<{ label: string; value: string }> {
  if (!summary || typeof summary !== 'object' || !summary.conclusion) return [];
  const rows: Array<{ label: string; value: string }> = [];
  const push = (label: string, value?: string | null) => {
    if (typeof value === 'string' && value.trim()) rows.push({ label, value });
  };
  push('结论', summary.conclusion);
  push('下次计划建议', summary.next_plan_suggestion);
  push('异常记录', summary.abnormal_findings);
  return rows;
}

export const manualEntryText = {
  action: '提交手工录入',
  confirmation: '提交后进入待医护审阅，审阅通过后才算完成随访。',
  success: '手工录入已提交，待医护审阅',
} as const;
