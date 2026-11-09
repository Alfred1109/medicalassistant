import api from './httpClient';
import type { CreateQualityIssue, QualityAssignee, QualityFactPage, QualityFilters, QualityIssue,
  QualityIssueDetail, QualityOverview, QualityPage, QualitySource } from '../types/quality';

const issueRoot = '/quality/issues';
const issuePath = (id: string) => `${issueRoot}/${encodeURIComponent(id)}`;
export const qualityApi = {
  overview: (params: QualityFilters, signal?: AbortSignal) => api.get<QualityOverview>('/quality-monitoring/overview', { params, signal }),
  facts: (source: QualitySource, params: QualityFilters, skip: number, limit: number, signal?: AbortSignal) =>
    api.get<QualityFactPage>(`/quality-monitoring/${source === 'followup' ? 'followups' : 'plans'}`, { params: { ...params, skip, limit }, signal }),
  report: (params: QualityFilters) => api.get<Blob>('/quality-monitoring/report.csv', { params, responseType: 'blob' }),
  issues: (params: { patient_id?: string; status?: string; assignee_id?: string; skip: number; limit: number }, signal?: AbortSignal) =>
    api.get<QualityPage<QualityIssue>>(issueRoot, { params, signal }),
  issue: (id: string, signal?: AbortSignal) => api.get<QualityIssueDetail>(issuePath(id), { signal }),
  assignees: (patientId: string, signal?: AbortSignal) => api.get<{items: QualityAssignee[]}>(`${issueRoot}/assignees`, { params: { patient_id: patientId }, signal }),
  create: (body: CreateQualityIssue) => api.post<QualityIssueDetail>(issueRoot, body),
  assign: (id: string, body: { request_id: string; expected_version: number; assignee_id: string; note: string }) => api.post<QualityIssueDetail>(`${issuePath(id)}/assign`, body),
  confirm: (id: string, body: { request_id: string; expected_version: number; note: string }) => api.post<QualityIssueDetail>(`${issuePath(id)}/confirm`, body),
  resolve: (id: string, body: { request_id: string; expected_version: number; resolution: string; evidence_refs: string[] }) => api.post<QualityIssueDetail>(`${issuePath(id)}/resolve`, body),
  review: (id: string, body: { request_id: string; expected_version: number; decision: 'approve' | 'return'; note: string; evidence_refs: string[] }) => api.post<QualityIssueDetail>(`${issuePath(id)}/review`, body),
};
