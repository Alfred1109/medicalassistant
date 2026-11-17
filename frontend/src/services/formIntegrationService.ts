/**
 * 表单平台（113.44）集成填报服务。
 *
 * 后端路由：/api/integrations/forms（全部要求登录）。
 * embedToken 明文只在创建任务响应中出现一次，由调用方立即交给 iframe 使用；
 * 服务与组件都不把它写入任何持久化存储。
 */

import apiClient from './apiClient';
import type { FollowUpWorkbenchPage } from '../types/followup';

export interface FillTaskRemoteRefs {
  project_id: number;
  center_id: number;
  subject_id: number;
  questionnaire_id: number;
}

export interface FillTask {
  id: string;
  patientId: string;
  operator: { userId: string; role: string };
  remoteRefs: FillTaskRemoteRefs;
  visitCode?: string | null;
  visitName?: string | null;
  maTaskRef?: string | null;
  status:
    | 'session_created'
    | 'waiting_fill'
    | 'submitted'
    | 'confirmed'
    | 'cancelled'
    | 'failed';
  session: {
    sessionUuid: string | null;
    responseId: number | null;
    expiresAt: string | null;
  };
  confirmation?: {
    response_id: number;
    session_uuid: string;
    remote_status: string;
    visit_code?: string | null;
    submitted_at?: string | null;
    answers: { question_id: number; answer_text: string | null }[];
    verified_at: string;
  } | null;
  lastError?: string | null;
  remoteStatus?: string | null;
  remoteQueryError?: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  confirmedAt: string | null;
}

export interface PatientSelfTask {
  id: string;
  status: string;
  patientId: string;
  followupVisitId: string | null;
  remoteRefs: FillTaskRemoteRefs;
  session: { sessionId: string | null; status: string | null; expiresAt: string | null };
  verifiedEvidence?: {
    fill_mode: string;
    session_uuid: string;
    response_id: number;
    remote_status: string;
    is_voided: boolean;
    user_id: number | null;
    submitted_at: string;
    updated_at: string;
    questionnaire_version_ref: {
      form_id: number;
      family_id: number;
      version: number;
      definition_sha256: string;
    };
    visit_code?: string | null;
    answers: { question_id: number; answer_text: string | null }[];
    verified_at: string;
    snapshot_sha256: string;
  };
}

export interface CreateFillTaskPayload {
  patientId: string;
  remoteProjectId: number;
  remoteCenterId: number;
  remoteSubjectId: number;
  remoteQuestionnaireId: number;
  formBindingId: string;
  formPurpose: 'initial_assessment' | 'followup' | 'reassessment';
  allowedOrigin: string;
  visitCode?: string;
  visitName?: string;
  maTaskRef?: string;
  followupVisitId?: string;
}

export interface FillCandidateForm {
  binding_id: string;
  form_id: number;
  version: number;
  purpose: CreateFillTaskPayload['formPurpose'];
  title: string;
}

export interface FillCandidateReference {
  project_id: number;
  center_id: number;
  subject_id: number;
  forms: FillCandidateForm[];
}

export interface FillCandidatePatient {
  patient_id: string;
  name: string;
  references: FillCandidateReference[];
}

export interface FillCandidatesPage {
  patients: FillCandidatePatient[];
  skip: number;
  limit: number;
  total: number;
}

export type CreateFillTaskResult = FillTask;

export interface EmbedUrlResult {
  taskId: string;
  embedUrl: string;
  sessionUuid: string | null;
  expiresAt: string | null;
  allowedOrigin: string;
}

export type FillTaskLaunch = {
  taskId: string;
  sessionUuid: string;
  expiresAt: string;
  allowedOrigin: string;
} & ({ mode: 'launch'; action: string; token: string } | { mode: 'resume'; url: string });

/** Submit a one-use credential without putting it in browser navigation URLs. */
export const submitFillLaunch = (launch: FillTaskLaunch, frame: HTMLIFrameElement): void => {
  const destination = launch.mode === 'launch' ? launch.action : launch.url;
  const url = new URL(destination);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash
      || !launch.sessionUuid || !frame.name) throw new Error('填报入口无效');
  const expectedPath = `/integration/${launch.mode === 'launch' ? 'embed' : 'resume'}/${encodeURIComponent(launch.sessionUuid)}`;
  if (url.pathname !== expectedPath) throw new Error('填报会话不匹配');
  if (launch.mode === 'resume') {
    frame.src = url.href;
    return;
  }
  if (typeof launch.token !== 'string' || !launch.token) throw new Error('填报凭证无效');
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = url.href;
  form.target = frame.name;
  form.hidden = true;
  const input = document.createElement('input');
  input.type = 'hidden';
  input.name = 'token';
  input.value = launch.token;
  form.appendChild(input);
  document.body.appendChild(form);
  try { form.submit(); } finally { input.value = ''; form.remove(); }
};

export interface FillTaskListPage {
  status: string;
  page: number;
  pageSize: number;
}

export const FORM_PLATFORM_POST_MESSAGE_SOURCE = 'form11344';

export interface FormPlatformFillStatusMessage {
  source: typeof FORM_PLATFORM_POST_MESSAGE_SOURCE;
  type: 'fill_status';
  sessionSid: string;
  responseId: number | null;
  status: string;
}

export const isFormPlatformFillStatusMessage = (
  data: unknown,
): data is FormPlatformFillStatusMessage => {
  if (typeof data !== 'object' || data === null) return false;
  const candidate = data as Record<string, unknown>;
  return (
    candidate.source === FORM_PLATFORM_POST_MESSAGE_SOURCE &&
    candidate.type === 'fill_status' &&
    typeof candidate.sessionSid === 'string' &&
    candidate.sessionSid.length > 0 &&
    (candidate.responseId === null || typeof candidate.responseId === 'number') &&
    typeof candidate.status === 'string'
  );
};

/** Only the iframe opened for this task may report its fill status. */
export const isTrustedFormPlatformFillStatusEvent = (
  event: Pick<MessageEvent, 'origin' | 'source' | 'data'>,
  frameWindow: Window | null,
  embed: Pick<EmbedUrlResult, 'embedUrl' | 'sessionUuid'>,
): event is Pick<MessageEvent<FormPlatformFillStatusMessage>, 'origin' | 'source' | 'data'> => {
  if (!frameWindow || event.source !== frameWindow || !embed.sessionUuid) return false;
  let url: URL;
  try {
    url = new URL(embed.embedUrl);
  } catch {
    return false;
  }
  if (!['https:', 'http:'].includes(url.protocol) || event.origin !== url.origin) return false;
  return isFormPlatformFillStatusMessage(event.data) && event.data.sessionSid === embed.sessionUuid;
};

const buildCreatePayload = (payload: CreateFillTaskPayload): Record<string, unknown> => ({
  patient_id: payload.patientId,
  remote_project_id: payload.remoteProjectId,
  remote_center_id: payload.remoteCenterId,
  remote_subject_id: payload.remoteSubjectId,
  remote_questionnaire_id: payload.remoteQuestionnaireId,
  form_binding_id: payload.formBindingId,
  form_purpose: payload.formPurpose,
  allowed_origin: payload.allowedOrigin,
  ...(payload.visitCode ? { visit_code: payload.visitCode } : {}),
  ...(payload.visitName ? { visit_name: payload.visitName } : {}),
  ...(payload.maTaskRef ? { ma_task_ref: payload.maTaskRef } : {}),
  ...(payload.followupVisitId ? { followup_visit_id: payload.followupVisitId } : {}),
});

export const formIntegrationService = {
  async listFillCandidates(skip = 0, limit = 50): Promise<FillCandidatesPage> {
    return apiClient.get<FillCandidatesPage>('/integrations/forms/fill-candidates', { params: { skip, limit } });
  },

  async listPatientFollowups(patientId: string, skip = 0, limit = 50): Promise<FollowUpWorkbenchPage> {
    return apiClient.get<FollowUpWorkbenchPage>('/health-records/followup-workbench', {
      params: { patient_id: patientId, skip, limit },
    });
  },

  async listFillTasks(params?: {
    status?: string;
    patientId?: string;
    skip?: number;
    limit?: number;
  }): Promise<{ items: FillTask[]; total: number; skip: number; limit: number }> {
    const query: Record<string, string | number> = {};
    if (params?.status) query.status = params.status;
    if (params?.patientId) query.patient_id = params.patientId;
    if (params?.skip !== undefined) query.skip = params.skip;
    if (params?.limit !== undefined) query.limit = params.limit;
    return apiClient.get<{ items: FillTask[]; total: number; skip: number; limit: number }>(
      '/integrations/forms/fill-tasks',
      { params: query },
    );
  },

  async listFillTaskPage(query: FillTaskListPage): Promise<{
    items: FillTask[]; total: number; page: number;
  }> {
    if (!Number.isInteger(query.page) || query.page < 0 ||
        !Number.isInteger(query.pageSize) || query.pageSize < 1 || query.pageSize > 100) {
      throw new RangeError('填报任务分页参数无效');
    }
    const fetch = (page: number) => this.listFillTasks({
      ...(query.status ? { status: query.status } : {}),
      skip: page * query.pageSize,
      limit: query.pageSize,
    });
    let page = query.page;
    let result = await fetch(page);
    // 筛选、撤权或取消后总数可能缩小；重新取得仍存在的末页。
    while (page > Math.max(0, Math.ceil(result.total / query.pageSize) - 1)) {
      page = Math.max(0, Math.ceil(result.total / query.pageSize) - 1);
      result = await fetch(page);
    }
    return { items: result.items, total: result.total, page };
  },

  async createFillTask(payload: CreateFillTaskPayload): Promise<CreateFillTaskResult> {
    return apiClient.post<CreateFillTaskResult>(
      '/integrations/forms/fill-tasks',
      buildCreatePayload(payload),
    );
  },

  async getFillTask(taskId: string): Promise<FillTask> {
    return apiClient.get<FillTask>(`/integrations/forms/fill-tasks/${taskId}`);
  },

  async getPatientSelfTask(taskId: string): Promise<PatientSelfTask> {
    return apiClient.get<PatientSelfTask>(`/integrations/forms/patient-self/tasks/${encodeURIComponent(taskId)}`);
  },

  async launchFillTask(taskId: string): Promise<FillTaskLaunch> {
    return apiClient.post<FillTaskLaunch>(`/integrations/forms/fill-tasks/${encodeURIComponent(taskId)}/launch`);
  },

  async confirmFillTask(taskId: string): Promise<FillTask> {
    return apiClient.post<FillTask>(
      `/integrations/forms/fill-tasks/${taskId}/confirm`,
    );
  },

  async cancelFillTask(taskId: string): Promise<FillTask> {
    return apiClient.post<FillTask>(
      `/integrations/forms/fill-tasks/${taskId}/cancel`,
    );
  },
};
