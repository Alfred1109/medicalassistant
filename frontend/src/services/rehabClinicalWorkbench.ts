import api from './httpClient';
import type { PublishedRehabCourse, PublishedRehabItem, PublishedRehabPlan, PatientRehabFeedback } from './rehabPublications';

export interface ClinicalPlan {
  _id: string; name: string; patient_id: string; description?: string; goal?: string;
  start_date?: string; end_date?: string | null; frequency?: string | null; status?: string;
}
export interface DraftContent {
  name: string; description: string; goal: string; start_date: string;
  end_date?: string | null; frequency?: string | null; patient_instructions?: string | null;
}
export interface DraftItem extends Omit<PublishedRehabItem, 'item_id'> {
  item_id?: string;
  applicability_conditions?: string[] | null;
  patient_instructions?: string | null;
  course?: PublishedRehabCourse | null;
}
// T72 禁忌规则命中提示（warn 不阻断，block 阻断发布）
export interface ContraindicationFinding {
  rule_id?: string; level?: 'warn' | 'block'; scope?: string; item_id?: string;
  item_name?: string; message?: string; status?: string; source?: string;
}
export interface ContraindicationReport {
  warnings?: ContraindicationFinding[]; blocks?: ContraindicationFinding[]; checked_at?: string;
}
// T72 发布签署记录（医护侧可见；患者投影不含签署内容）
export interface PublicationSignature {
  signed_by: string; signed_by_role?: string; signed_at: string;
  declaration: string; declaration_status?: string; declaration_acknowledged?: boolean;
  confirmation_note?: string; snapshot_hash: string;
}
export interface SignatureDeclaration {
  declaration: string; status?: string; source?: string;
}
export interface ClinicalDraft {
  id: string; revision: number; version_no: number; content: DraftContent; items: DraftItem[];
  contraindication_findings?: ContraindicationReport | null;
}
export interface DraftState {
  plan_id: string; draft: ClinicalDraft | null; published_version_id: string | null;
  publication_revision: number; has_publication_history: boolean;
  published?: PublishedRehabPlan | null; signature?: PublicationSignature | null;
}
export interface ClinicalFeedback extends PatientRehabFeedback { plan_id: string; submitted_at?: string; }
const root = '/rehabilitation/publications/plans';
const planPath = (id: string) => `${root}/${encodeURIComponent(id)}`;

export const rehabClinicalWorkbench = {
  plans: (patientId: string, skip: number, limit: number, signal?: AbortSignal) => api.get<ClinicalPlan[]>(
    '/rehabilitation/plans', { params: { patient_id: patientId, skip, limit }, signal }),
  create: (patientId: string, content: DraftContent) => api.post<ClinicalPlan>('/rehabilitation/plans', {
    patient_id: patientId, name: content.name, description: content.description, goal: content.goal,
    start_date: content.start_date, end_date: content.end_date || null, frequency: content.frequency || null,
    status: 'draft', exercises: [],
  }),
  draft: (id: string, signal?: AbortSignal) => api.get<DraftState>(`${planPath(id)}/draft`, { signal }),
  save: (id: string, body: { request_id: string; expected_draft_id: string | null;
    expected_draft_revision: number | null; content: DraftContent; items: DraftItem[] }) => api.put<DraftState>(`${planPath(id)}/draft`, body),
  publish: (id: string, body: { request_id: string; draft_id: string; expected_draft_revision: number;
    expected_publication_id: string | null; confirmed: true; declaration_acknowledged?: true;
    confirmation_note: string }) => api.post(`${planPath(id)}/publish`, body),
  withdraw: (id: string, body: { request_id: string; expected_publication_id: string;
    reason: string; action: 'withdraw' | 'cancel' | 'archive' }) => api.post(`${planPath(id)}/withdraw`, body),
  signatureDeclaration: (signal?: AbortSignal) => api.get<SignatureDeclaration>(
    '/rehabilitation/publications/signature-declaration', { signal }),
  contraindicationRules: (signal?: AbortSignal) => api.get<{ rules: { rule_id?: string;
    level?: string; scope?: string; description?: string; status?: string; source?: string }[] }>(
    '/rehabilitation/publications/contraindication-rules', { signal }),
  feedback: (id: string, skip: number, limit: number, signal?: AbortSignal) => api.get<{
    items: ClinicalFeedback[]; total: number; skip: number; limit: number;
  }>(`/rehabilitation/plans/${encodeURIComponent(id)}/patient-feedback`, { params: { skip, limit }, signal }),
};
