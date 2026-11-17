import api from './httpClient';

export type RehabInterventionType = 'diet' | 'exercise' | 'medication' | 'psychology';

// T72 结构化处方增量字段（疗程 / 执行要求）；历史快照可能没有这两个字段
export interface PublishedRehabCourse {
  duration_days?: number | null;
  sessions_total?: number | null;
  note?: string | null;
}

export interface PublishedRehabItem {
  item_id: string;
  intervention_type: RehabInterventionType;
  name: string;
  description?: string | null;
  schedule?: Record<string, unknown> | null;
  course?: PublishedRehabCourse | null;
  execution_requirements?: string[] | null;
  patient_instructions?: string | null;
  guidance_video_url?: string | null;
  contraindications?: string[] | null;
  diet_fields?: Record<string, unknown> | null;
  medication_fields?: Record<string, unknown> | null;
  psychology_fields?: Record<string, unknown> | null;
}

export interface PublishedRehabPlan {
  id: string;
  version_id: string;
  publication_revision: number;
  published_at: string;
  content: { name: string; description?: string | null; goal?: string | null;
    start_date?: string | null; end_date?: string | null; frequency?: string | null;
    patient_instructions?: string | null };
  items: PublishedRehabItem[];
}

export interface PublishedRehabPage {
  items: PublishedRehabPlan[];
  total: number;
  status_counts: { active: number; completed: number };
  skip: number;
  limit: number;
}

export interface PatientRehabAttachment {
  id: string;
  content_type: string;
  name: string;
}

export interface PatientRehabFeedback {
  id: string;
  version_id: string;
  prescription_item_id: string;
  execution_status: 'completed' | 'partial' | 'not_done';
  feelings: string;
  performed_at: string;
  attachments?: PatientRehabAttachment[];
  cycle_id?: string | null;
  intervention_type?: RehabInterventionType | null;
  clinical_review?: { status: 'pending' | 'verified' | 'return_for_supplement'; revision: number; note?: string | null; reviewed_at?: string | null } | null;
  supplements?: { id: string; note: string; submitted_at: string; attachments?: PatientRehabAttachment[] }[];
}

export interface PatientTrainingCycle {
  id: string; title: string; start_date: string; end_date: string; status: 'open' | 'accepted';
  acceptance?: { note: string; accepted_at: string } | null;
}

const root = '/rehabilitation/publications';
export const rehabPublications = {
  myPlans: (skip: number, limit: number, signal?: AbortSignal) =>
    api.get<PublishedRehabPage>(`${root}/my-plans`, { params: { skip, limit }, signal }),
  myPlan: (planId: string, signal?: AbortSignal) =>
    api.get<PublishedRehabPlan>(`${root}/my-plans/${encodeURIComponent(planId)}`, { signal }),
  uploadFeedbackMedia: (planId: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return api.post<PatientRehabAttachment>(`/rehabilitation/plans/${encodeURIComponent(planId)}/patient-feedback/media`, body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  feedbackMedia: (planId: string, mediaId: string) => api.get<Blob>(
    `/rehabilitation/plans/${encodeURIComponent(planId)}/patient-feedback/media/${encodeURIComponent(mediaId)}`,
    { responseType: 'blob' }),
  submitFeedback: (planId: string, body: { event_id: string; version_id: string; prescription_item_id: string;
    execution_status: PatientRehabFeedback['execution_status']; feelings: string; performed_at: string; media_ids?: string[] }) =>
    api.post<{ feedback: PatientRehabFeedback; created: boolean }>(
      `/rehabilitation/plans/${encodeURIComponent(planId)}/patient-feedback`, body),
  feedback: (planId: string, skip: number, limit: number, signal?: AbortSignal) => api.get<{ items: PatientRehabFeedback[]; total: number }>(
    `/rehabilitation/plans/${encodeURIComponent(planId)}/patient-feedback`, { params: { skip, limit }, signal }),
  supplement: (planId: string, feedbackId: string, body: { event_id: string; note: string; media_ids: string[] }) =>
    api.post(`/rehabilitation/plans/${encodeURIComponent(planId)}/patient-feedback/${encodeURIComponent(feedbackId)}/supplements`, body),
  trainingCycles: (planId: string, signal?: AbortSignal) => api.get<{ items: PatientTrainingCycle[] }>(
    `/rehabilitation/plans/${encodeURIComponent(planId)}/training-cycles`, { signal }),
};
