/**
 * 表单平台（113.44）集成填报服务。
 *
 * 后端路由：/api/integrations/forms（全部要求登录）。
 * embedToken 明文只在创建任务响应中出现一次，由调用方立即交给 iframe 使用；
 * 服务与组件都不把它写入任何持久化存储。
 */

import apiClient from './apiClient';

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
    answers: { question_id: number; answer_text: string }[];
    verified_at: string;
  } | null;
  lastError?: string | null;
  remoteStatus?: string | null;
  remoteQueryError?: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  confirmedAt: string | null;
}

export interface CreateFillTaskPayload {
  patientId: string;
  remoteProjectId: number;
  remoteCenterId: number;
  remoteSubjectId: number;
  remoteQuestionnaireId: number;
  remoteOperatorUserId: number;
  allowedOrigin: string;
  visitCode?: string;
  visitName?: string;
  maTaskRef?: string;
}

export interface CreateFillTaskResult extends FillTask {
  embedToken: string;
}

export interface EmbedUrlResult {
  taskId: string;
  embedUrl: string;
  sessionUuid: string | null;
  expiresAt: string | null;
  allowedOrigin: string;
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

const buildCreatePayload = (payload: CreateFillTaskPayload): Record<string, unknown> => ({
  patient_id: payload.patientId,
  remote_project_id: payload.remoteProjectId,
  remote_center_id: payload.remoteCenterId,
  remote_subject_id: payload.remoteSubjectId,
  remote_questionnaire_id: payload.remoteQuestionnaireId,
  remote_operator_user_id: payload.remoteOperatorUserId,
  allowed_origin: payload.allowedOrigin,
  ...(payload.visitCode ? { visit_code: payload.visitCode } : {}),
  ...(payload.visitName ? { visit_name: payload.visitName } : {}),
  ...(payload.maTaskRef ? { ma_task_ref: payload.maTaskRef } : {}),
});

export const formIntegrationService = {
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

  async createFillTask(payload: CreateFillTaskPayload): Promise<CreateFillTaskResult> {
    return apiClient.post<CreateFillTaskResult>(
      '/integrations/forms/fill-tasks',
      buildCreatePayload(payload),
    );
  },

  async getFillTask(taskId: string): Promise<FillTask> {
    return apiClient.get<FillTask>(`/integrations/forms/fill-tasks/${taskId}`);
  },

  async getEmbedUrl(taskId: string): Promise<EmbedUrlResult> {
    return apiClient.get<EmbedUrlResult>(
      `/integrations/forms/fill-tasks/${taskId}/embed-url`,
    );
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
