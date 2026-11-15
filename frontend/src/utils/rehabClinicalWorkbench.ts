import type { ClinicalPlan, ContraindicationFinding, ContraindicationReport, DraftContent, DraftItem } from '../services/rehabClinicalWorkbench';
import { patientDomainErrorCopy } from '../services/patientErrors';

export const interventionLabels = { diet: '饮食', exercise: '运动', medication: '用药', psychology: '心理' } as const;
export type FormContent = { name: string; description: string; goal: string; start_date: string;
  end_date: string; frequency: string; patient_instructions: string };
export const emptyContent = (): FormContent => ({ name: '', description: '', goal: '', start_date: '',
  end_date: '', frequency: '', patient_instructions: '' });
export function localDateInput(value?: string | null): string {
  if (!value) return '';
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  if (!Number.isFinite(date.getTime())) return '';
  const pad = (number: number) => String(number).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${String(date.getMilliseconds()).padStart(3, '0')}`;
}
export function contentForm(content: Partial<Record<keyof FormContent, string | null>> | ClinicalPlan): FormContent {
  return { name: content.name || '', description: content.description || '', goal: content.goal || '',
    start_date: localDateInput(content.start_date), end_date: localDateInput(content.end_date),
    frequency: content.frequency || '', patient_instructions: 'patient_instructions' in content ? content.patient_instructions || '' : '' };
}
export function contentPayload(value: FormContent): DraftContent {
  if (!value.name.trim() || !value.description.trim() || !value.goal.trim() || !value.start_date) {
    throw new Error('请填写方案名称、说明、目标和开始时间。');
  }
  const start = new Date(value.start_date);
  const end = value.end_date ? new Date(value.end_date) : null;
  if (!Number.isFinite(start.getTime()) || (end && (!Number.isFinite(end.getTime()) || end < start))) {
    throw new Error('请检查开始和结束时间。');
  }
  return { name: value.name.trim(), description: value.description.trim(), goal: value.goal.trim(),
    start_date: start.toISOString(), end_date: end?.toISOString() || null, frequency: value.frequency.trim() || null,
    patient_instructions: value.patient_instructions.trim() || null };
}
export function validateItems(items: DraftItem[]): DraftItem[] {
  if (items.some(item => !item.name.trim())) throw new Error('请为每条干预填写名称。');
  return items.map(item => {
    const requirements = item.execution_requirements?.map(line => line.trim()).filter(Boolean);
    const requirementLines = requirements && requirements.length ? requirements : null;
    const course = item.course && (item.course.duration_days || item.course.sessions_total || item.course.note?.trim())
      ? { ...item.course, note: item.course.note?.trim() || null } : null;
    return { ...item, name: item.name.trim(), description: item.description?.trim() || null,
      patient_instructions: item.patient_instructions?.trim() || null,
      guidance_video_url: item.guidance_video_url?.trim() || null,
      execution_requirements: requirementLines, course };
  });
}

// T72 禁忌命中提示文案（warn 与 block 都展示；block 另行阻断发布）
export function findingLines(report: ContraindicationReport | null | undefined): string[] {
  const findings = [...(report?.blocks || []), ...(report?.warnings || [])];
  return findings.filter(finding => typeof finding?.message === 'string' && finding.message.trim())
    .map(finding => `${finding.level === 'block' ? '【阻断】' : '【提示】'}${finding.message}` +
      (finding.status ? `（${finding.status}）` : ''));
}
export function operationId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}
export function workbenchError(error: unknown, fallback: string): string {
  // 患者域错误（如 503 REHAB_PATIENT_DOMAIN_UNSUPPORTED）优先使用统一提示文案
  const patientCopy = patientDomainErrorCopy(error);
  if (patientCopy) return patientCopy;
  const response = (error as { response?: { status?: number; data?: { detail?: unknown; message?: string } } })?.response;
  if (response?.status === 409) return '方案已更新或本次操作发生冲突。请重新加载核对后再操作。';
  if (response?.status === 403) return '当前已无权管理该患者的方案。';
  if (response?.status === 404) return '方案不存在或当前不可访问。';
  const detail = response?.data?.detail;
  if (typeof detail === 'string') return detail;
  // 结构化错误（如 422 REHAB_CONTRAINDICATION_BLOCK：detail={error,message,details}）
  if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
    return (detail as { message: string }).message;
  }
  return fallback;
}
