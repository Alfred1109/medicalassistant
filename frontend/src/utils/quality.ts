import type { QualityFactPage, QualityFilters, QualityOverview, QualitySource } from '../types/quality';

export const issueStatusLabels = { open: '待确认', in_progress: '整改中', pending_review: '待复核', closed: '已关闭' } as const;
export const publicationLabels: Record<string, string> = { published: '发布引用及基本结构已核对', unpublished: '尚未发布', withdrawn: '已撤回', stopped: '已取消或归档', invalid_reference: '发布引用或基本结构异常' };
export const specialStatusLabels: Record<string, string> = { __unknown__: '未识别状态', __missing__: '缺失状态', __invalid__: '无效状态' };
export function qualityTime(value?: string | null): string {
  if (!value) return '未记录';
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN', { hour12: false }) : '时间格式无法识别';
}
export function qualityFilters(patientId: string, startDate: string, endDate: string): QualityFilters {
  const result: QualityFilters = {};
  if (patientId.trim()) result.patient_id = patientId.trim();
  const calendar = (value: string, next = false) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('请选择有效日期。');
    const [year, month, day] = value.split('-').map(Number);
    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) throw new Error('日期无效。');
    if (next) date.setDate(date.getDate() + 1);
    return date;
  };
  const start = startDate ? calendar(startDate) : null;
  const end = endDate ? calendar(endDate, true) : null;
  if (start && end && end <= start) throw new Error('结束日期不能早于开始日期。');
  if (start) result.start_date = start.toISOString();
  if (end) result.end_date = end.toISOString();
  return result;
}
export function qualityError(error: unknown, fallback: string): string {
  const response = (error as {response?: {status?: number; data?: {detail?: unknown; message?: string}}})?.response;
  if (response?.status === 409) return '记录已变化或本次请求发生冲突，请重新加载核对后再操作。';
  if (response?.status === 403) return '当前账号无权查看或处理这些记录。';
  if (response?.status === 404) return '记录不存在或当前不可访问。';
  if (typeof response?.data?.detail === 'string') return response.data.detail;
  if (typeof response?.data?.message === 'string') return response.data.message;
  return fallback;
}
export function qualityOperationId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, '0')).join('');
}
export function qualitySourcePath(source: QualitySource, id: string): string | null {
  if (!/^[a-f\d]{24}$/i.test(id)) return null;
  return source === 'followup' ? `/app/follow-ups/${id}` : source === 'rehab_plan' ? `/app/rehab-plans/${id}` : null;
}
export const evidenceLines = (value: string): string[] => value.split('\n').map(line => line.trim()).filter(Boolean);
export function evidenceReferences(value: string): string[] {
  const refs = [...new Set(evidenceLines(value))];
  if (refs.length < 1 || refs.length > 20 || refs.some(item => item.length > 256)) {
    throw new Error('请填写 1 至 20 条证据引用，每条不超过 256 字。');
  }
  return refs;
}
const count = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0;
export function validQualityOverview(value: QualityOverview): boolean {
  if (!value || typeof value.generated_at !== 'string' || !value.window || !['assigned_patients', 'all_source_records', 'selected_patient'].includes(value.scope_kind)
      || value.read_consistency !== 'independent_live_reads' || value.publication_validation !== 'reference_and_required_structure') return false;
  for (const summary of [value.followups, value.plans]) {
    if (!summary || ![summary.selected_total, summary.scope_total, summary.missing_date_count,
      summary.invalid_date_count, summary.unresolved_patient_count].every(count) || !Array.isArray(summary.by_status)
      || summary.by_status.some(item => !item || typeof item.status !== 'string' || !count(item.count))) return false;
  }
  return count(value.followups.in_review_count) && Array.isArray(value.plans.publication_states)
    && value.plans.publication_states.every(item => item && typeof item.state === 'string' && count(item.count));
}
export function validQualityFactPage(value: QualityFactPage, source: QualitySource, filters: QualityFilters, skip: number, limit: number): boolean {
  return Boolean(value && Array.isArray(value.items) && count(value.total) && value.total >= value.items.length
    && value.skip === skip && value.limit === limit && value.items.length <= limit
    && value.items.every(row => row && row.source_type === source && typeof row.source_id === 'string'
      && ['valid', 'unaddressable'].includes(row.source_reference_state)
      && (row.patient_id === null || typeof row.patient_id === 'string') && typeof row.status === 'string'
      && (row.date === null || typeof row.date === 'string') && ['valid', 'missing', 'invalid'].includes(row.date_quality)
      && typeof row.issue_eligible === 'boolean'
      && ['valid', 'missing', 'invalid', 'not_found', 'ambiguous'].includes(row.patient_reference_state)
      && (!filters.patient_id || row.patient_id === filters.patient_id)));
}
