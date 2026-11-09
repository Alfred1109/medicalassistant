import type { ClinicalPlan, DraftContent, DraftItem } from '../services/rehabClinicalWorkbench';

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
  return items.map(item => ({ ...item, name: item.name.trim(), description: item.description?.trim() || null,
    patient_instructions: item.patient_instructions?.trim() || null }));
}
export function operationId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}
export function workbenchError(error: unknown, fallback: string): string {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown; message?: string } } })?.response;
  if (response?.status === 409) return '方案已更新或本次操作发生冲突。请重新加载核对后再操作。';
  if (response?.status === 403) return '当前已无权管理该患者的方案。';
  if (response?.status === 404) return '方案不存在或当前不可访问。';
  if (typeof response?.data?.detail === 'string') return response.data.detail;
  return fallback;
}
