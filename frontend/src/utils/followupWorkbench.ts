import type { FollowUpFilters, FollowUpWorkbenchQuery } from '../types/followup';

/** Date-picker values are local calendar days; the API interval is [start, end). */
export function localDayBoundary(value: string, nextDay = false): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) throw new Error('请选择有效日期');
  const [, y, m, d] = match;
  const date = new Date(Number(y), Number(m) - 1, Number(d));
  if (date.getFullYear() !== Number(y) || date.getMonth() !== Number(m) - 1 || date.getDate() !== Number(d)) {
    throw new Error('请选择有效日期');
  }
  if (nextDay) date.setDate(date.getDate() + 1);
  return date.toISOString();
}

export function buildFollowUpWorkbenchQuery(patientId: string, filters: FollowUpFilters, page: number, pageSize: number): FollowUpWorkbenchQuery {
  if (!Number.isInteger(page) || page < 0 || !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) throw new Error('分页参数无效');
  if (filters.start_date && filters.end_date && filters.start_date > filters.end_date) throw new Error('开始日期不能晚于结束日期');
  return {
    patient_id: patientId && patientId !== 'all' ? patientId : undefined,
    status: filters.status || undefined,
    follow_up_type: filters.follow_up_type || undefined,
    start_date: filters.start_date ? localDayBoundary(filters.start_date) : undefined,
    end_date: filters.end_date ? localDayBoundary(filters.end_date, true) : undefined,
    patient_name: filters.patient_name?.trim() || undefined,
    skip: page * pageSize,
    limit: pageSize,
  };
}
