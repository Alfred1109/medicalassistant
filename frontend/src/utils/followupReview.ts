import type { FollowUpRecord, ReviewFollowUpRequest } from '../types/followup';
import type { FillTask } from '../services/formIntegrationService';

export function canReviewFollowUp(record: FollowUpRecord, actor: { id: string; role: string } | null): boolean {
  return !!actor && ['doctor', 'health_manager'].includes(actor.role) &&
    record.status === 'in_review' && [record.provider_id, record.created_by].includes(actor.id);
}

/** Return only the confirmed snapshot bound to the viewed node; no fallback to another task. */
export function verifiedReviewTask(record: FollowUpRecord, task: FillTask): boolean {
  const ref = record.effective_response;
  return followUpEvidenceSource(record) === 'external_form' && !!ref && String(ref.task_id) === task.id && record.patient_id === task.patientId &&
    task.status === 'confirmed' && !!task.confirmation &&
    String(ref.response_id) === String(task.confirmation.response_id) &&
    ['submitted', 'restored'].includes(task.confirmation.remote_status) &&
    !task.remoteQueryError && !['revoked', 'cancelled', 'expired', 'invalidated'].includes(task.remoteStatus ?? '');
}

export function followUpError(error: unknown, fallback: string): string {
  const body = (error as { response?: { data?: { detail?: unknown; message?: unknown } } })?.response?.data;
  if (typeof body?.detail === 'string') return body.detail;
  if (typeof body?.message === 'string') return body.message;
  return fallback;
}

export function buildFollowUpReviewRequest(record: FollowUpRecord, decision: 'approved' | 'returned', comment: string): ReviewFollowUpRequest {
  return {
    decision, expected_version: record.mutation_version,
    ...(comment.trim() ? { comment: comment.trim() } : {}),
    ...(followUpEvidenceSource(record) === 'external_form' && record.effective_response ? { evidence: { ...record.effective_response } } : {}),
  };
}

/** Source comes from the server's current-evidence contract, including resolved legacy records. */
export function followUpEvidenceSource(record: FollowUpRecord): 'manual_entry' | 'external_form' | 'ambiguous' | 'unknown' {
  const source = record.current_evidence?.source;
  if (record.completion_data?.source === 'manual_entry' && record.effective_response) return 'ambiguous';
  return source === 'manual_entry' || source === 'external_form' || source === 'ambiguous' ? source : 'unknown';
}

export function hasConflictingFollowUpSources(record: FollowUpRecord): boolean {
  return followUpEvidenceSource(record) === 'ambiguous';
}

/** Match the backend re-evaluation state machine; existing successors cannot fork. */
export function canReEvaluateFollowUp(record: FollowUpRecord, actor: { id: string; role: string } | null): boolean {
  return !!actor && ['doctor', 'health_manager'].includes(actor.role) &&
    ['completed', 'canceled', 'missed', 'overdue'].includes(record.status) &&
    !record.next_visit_id && !record.next_follow_up_id;
}
