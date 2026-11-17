import type { FollowUpRecord, ReviewFollowUpRequest } from '../types/followup';
import type { FillTask, PatientSelfTask } from '../services/formIntegrationService';

export interface ReviewEvidenceTask {
  id: string;
  patientId: string;
  status: string;
  session: { sessionUuid: string | null; responseId: number | null; expiresAt: string | null };
  confirmation?: NonNullable<FillTask['confirmation']> | null;
  evidenceSource: 'external_form' | 'patient_self';
  followupVisitId?: string | null;
  remoteRefs?: FillTask['remoteRefs'];
  remoteStatus?: string | null;
  remoteQueryError?: string | null;
  versionRef?: PatientSelfTask['verifiedEvidence'] extends infer E
    ? E extends { questionnaire_version_ref: infer V } ? V : never : never;
}

export function canReviewFollowUp(record: FollowUpRecord, actor: { id: string; role: string } | null): boolean {
  return !!actor && ['doctor', 'health_manager'].includes(actor.role) &&
    record.status === 'in_review' && [record.provider_id, record.created_by].includes(actor.id);
}

/** Return only the confirmed snapshot bound to the viewed node; no fallback to another task. */
export function verifiedReviewTask(record: FollowUpRecord, task: FillTask | ReviewEvidenceTask): boolean {
  const ref = record.effective_response;
  const confirmation = task.confirmation;
  const sourceMatches = followUpEvidenceSource(record) === 'external_form' && !!ref && String(ref.task_id) === task.id && record.patient_id === task.patientId &&
    task.status === 'confirmed' && !!confirmation &&
    String(ref.response_id) === String(confirmation.response_id) &&
    ['submitted', 'restored'].includes(confirmation.remote_status) &&
    !task.remoteQueryError && !['revoked', 'cancelled', 'expired', 'invalidated'].includes(task.remoteStatus ?? '');
  if (!sourceMatches) return false;
  if (!('evidenceSource' in task) || task.evidenceSource !== 'patient_self') return true;
  const version = task.versionRef;
  return task.followupVisitId === record.id && !!version && !!task.remoteRefs &&
    Number.isInteger(version.form_id) && version.form_id === task.remoteRefs.questionnaire_id &&
    Number.isInteger(version.family_id) && version.family_id > 0 &&
    Number.isInteger(version.version) && version.version > 0 &&
    /^[a-f0-9]{64}$/i.test(version.definition_sha256) &&
    confirmation!.session_uuid === task.session.sessionUuid &&
    !!task.session.sessionUuid && !!confirmation!.answers.length;
}

const nonEmptyAnswers = (answers: unknown): answers is { question_id: number; answer_text: string | null }[] =>
  Array.isArray(answers) && answers.length > 0 && answers.every(answer =>
    !!answer && typeof answer === 'object' && Number.isInteger((answer as { question_id?: unknown }).question_id) &&
    ((answer as { answer_text?: unknown }).answer_text === null ||
      typeof (answer as { answer_text?: unknown }).answer_text === 'string'));

const stableJson = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`).join(',')}}`;
  }
  return JSON.stringify(value) ?? 'null';
};

async function patientSelfSnapshotDigest(evidence: NonNullable<PatientSelfTask['verifiedEvidence']>): Promise<string> {
  const snapshot = {
    fill_mode: evidence.fill_mode,
    session_uuid: evidence.session_uuid,
    response_id: evidence.response_id,
    remote_status: evidence.remote_status,
    submitted_at: evidence.submitted_at,
    updated_at: evidence.updated_at,
    questionnaire_version_ref: evidence.questionnaire_version_ref,
    visit_code: evidence.visit_code ?? null,
    answers: evidence.answers,
  };
  const bytes = new TextEncoder().encode(stableJson(snapshot));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

/** Convert the dedicated patient-self endpoint into the evidence shape used by the review UI. */
export async function patientSelfReviewTask(record: FollowUpRecord, raw: PatientSelfTask): Promise<ReviewEvidenceTask | null> {
  const evidence = raw.verifiedEvidence;
  const version = evidence?.questionnaire_version_ref;
  const ref = record.effective_response;
  if (!evidence || !ref || raw.status !== 'confirmed' || raw.id !== String(ref.task_id) ||
      raw.patientId !== record.patient_id || raw.followupVisitId !== record.id ||
      raw.session.status !== 'submitted' || !raw.session.sessionId ||
      evidence.fill_mode !== 'patient_self' || evidence.remote_status !== 'submitted' ||
      evidence.is_voided !== false || evidence.user_id !== null ||
      String(evidence.response_id) !== String(ref.response_id) ||
      evidence.session_uuid !== raw.session.sessionId ||
      !version || version.form_id !== raw.remoteRefs.questionnaire_id ||
      !Number.isInteger(version.form_id) || !Number.isInteger(version.family_id) ||
      !Number.isInteger(version.version) || version.version < 1 ||
      !/^[a-f0-9]{64}$/i.test(version.definition_sha256) ||
      (record.visit_code && evidence.visit_code && record.visit_code !== evidence.visit_code) ||
      !nonEmptyAnswers(evidence.answers) || !/^[a-f0-9]{64}$/i.test(evidence.snapshot_sha256) ||
      !evidence.verified_at) return null;
  if (await patientSelfSnapshotDigest(evidence) !== evidence.snapshot_sha256.toLowerCase()) return null;

  const confirmation = {
    response_id: evidence.response_id,
    session_uuid: evidence.session_uuid,
    remote_status: evidence.remote_status,
    visit_code: evidence.visit_code,
    submitted_at: evidence.submitted_at,
    answers: evidence.answers,
    verified_at: evidence.verified_at,
  };
  return {
    id: raw.id,
    patientId: raw.patientId,
    status: 'confirmed',
    session: { sessionUuid: raw.session.sessionId, responseId: evidence.response_id, expiresAt: raw.session.expiresAt },
    confirmation,
    evidenceSource: 'patient_self',
    followupVisitId: raw.followupVisitId,
    remoteRefs: raw.remoteRefs,
    versionRef: version,
  };
}

/** Use the patient-self read API only when the ordinary task route reports not found. */
export async function loadFollowUpReviewTask(
  record: FollowUpRecord,
  taskId: string,
  loaders: {
    getFillTask: (id: string) => Promise<FillTask>;
    getPatientSelfTask: (id: string) => Promise<PatientSelfTask>;
  },
): Promise<ReviewEvidenceTask> {
  try {
    const ordinary = await loaders.getFillTask(taskId);
    if (!verifiedReviewTask(record, ordinary) || !nonEmptyAnswers(ordinary.confirmation?.answers)) {
      throw new Error('无法核实当前普通填报答卷内容，当前不能批准。');
    }
    return { ...ordinary, evidenceSource: 'external_form' };
  } catch (error) {
    const status = (error as { response?: { status?: number } })?.response?.status;
    if (status !== 404) throw error;
  }

  const patientTask = await loaders.getPatientSelfTask(taskId);
  const normalized = await patientSelfReviewTask(record, patientTask);
  if (!normalized || !verifiedReviewTask(record, normalized) ||
      !nonEmptyAnswers(normalized.confirmation?.answers)) {
    throw new Error('无法核实患者本人答卷与当前随访的绑定，或确认快照没有可见回答；当前不能批准。');
  }
  return normalized;
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
