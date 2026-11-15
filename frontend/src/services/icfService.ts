// ICF 评估域（T71）API 客户端。
// 后端契约见 backend/app/api/routers/icf_router.py（前缀 /api/icf）。
// 所有临床口径（类目字典、指标阈值、判定结论）均为后端可配置默认值，
// 待临床确认；本文件不做任何本地判定。
import api from './httpClient';
import { API_BASE_URL } from '../config/api';

export interface IcfCategory {
  id: string;
  code: string;
  name: string;
  domain: string;
  description?: string;
  enabled: boolean;
  source: string;
  note?: string;
}

export interface IcfItem {
  code: string;
  name: string;
  domain: string;
  qualifier: number | string;
  qualifier_kind: 'numeric' | 'text';
  note?: string;
}

export interface IcfAssessment {
  id: string;
  patient_id: string;
  assessor_id: string;
  source: string;
  source_ref: string;
  assessed_at: string;
  note: string;
  review_status: string;
  review_note: string;
  mutation_version: number;
  content_revision: number;
  items?: IcfItem[];
}

export interface IcfMetricRow {
  metric_key: string;
  name?: string;
  state: string;
  value: number | null;
  threshold: number | null;
  detail?: unknown[];
  message?: string;
  sample_scope?: { source: 'followup_records'; order: 'scheduled_date_ascending'; limit: number;
    selected_count: number; soft_deleted_excluded: boolean; date_window: null; limit_reached: boolean };
}

export interface IcfMetricsResult {
  patient_id: string;
  computed_at: string;
  metrics: IcfMetricRow[];
  triggered?: { metric_key: string; alert_id?: string }[];
  skipped?: { metric_key: string; message?: string }[];
  note?: string;
}

export interface IcfMetricConfig {
  id: string;
  metric_key: string;
  name: string;
  description: string;
  enabled: boolean;
  params: Record<string, number | string>;
  note?: string;
}

export interface IcfReport {
  id: string;
  patient_id: string;
  assessment_id: string;
  title: string;
  generated_by: string;
  generated_at?: string;
  review_status: string;
  review_note: string;
  mutation_version: number;
  content_revision: number;
  exportable: boolean;
  payload?: Record<string, unknown>;
  review_history?: { action?: string; at?: string; actor_id?: string; note?: string; accepted?: boolean }[];
}

const path = (id: string) => encodeURIComponent(id);

export const icfApi = {
  // 类目字典
  categories: (signal?: AbortSignal) => api.get<{ categories: IcfCategory[]; note: string }>('/icf/categories', { signal }),
  createCategory: (body: { code: string; name: string; domain: string; description?: string }) =>
    api.post<IcfCategory>('/icf/categories', body),
  updateCategory: (id: string, body: { name?: string; domain?: string; description?: string; enabled?: boolean }) =>
    api.put<{ id: string }>(`/icf/categories/${path(id)}`, body),

  // 结构化评估
  createAssessment: (patientId: string, body: {
    items: { code: string; qualifier: number | string; note?: string }[];
    source?: string; source_ref?: string; assessed_at?: string; note?: string;
  }) => api.post<IcfAssessment>(`/icf/patients/${path(patientId)}/assessments`, body),
  assessments: (patientId: string, signal?: AbortSignal) =>
    api.get<{ assessments: IcfAssessment[]; note: string }>(`/icf/patients/${path(patientId)}/assessments`, { signal }),
  assessment: (assessmentId: string, signal?: AbortSignal) =>
    api.get<IcfAssessment>(`/icf/assessments/${path(assessmentId)}`, { signal }),
  updateAssessment: (assessmentId: string, body: {
    items: { code: string; qualifier: number | string; note?: string }[];
    note?: string; expected_version: number;
  }) => api.put<IcfAssessment>(`/icf/assessments/${path(assessmentId)}`, body),
  reviewAssessment: (assessmentId: string, body: { accepted: boolean; note: string; expected_version: number }) =>
    api.post<IcfAssessment>(`/icf/assessments/${path(assessmentId)}/review`, body),

  // 指标与预警
  metrics: (patientId: string, signal?: AbortSignal) =>
    api.get<IcfMetricsResult>(`/icf/patients/${path(patientId)}/metrics`, { signal }),
  evaluateMetrics: (patientId: string) =>
    api.post<IcfMetricsResult>(`/icf/patients/${path(patientId)}/metrics/evaluate`, {}),
  metricConfigs: (signal?: AbortSignal) =>
    api.get<{ metrics: IcfMetricConfig[]; note: string }>('/icf/metric-configs', { signal }),
  updateMetricConfig: (metricKey: string, body: { enabled?: boolean; params?: IcfMetricConfig['params'] }) =>
    api.put<{ metric_key: string }>(`/icf/metric-configs/${path(metricKey)}`, body),

  // 正式报告
  generateReport: (patientId: string, assessmentId: string) =>
    api.post<IcfReport>(`/icf/patients/${path(patientId)}/reports`, { assessment_id: assessmentId }),
  reports: (patientId: string, signal?: AbortSignal) =>
    api.get<{ reports: IcfReport[]; disclaimer: string }>(`/icf/patients/${path(patientId)}/reports`, { signal }),
  report: (reportId: string, signal?: AbortSignal) =>
    api.get<IcfReport>(`/icf/reports/${path(reportId)}`, { signal }),
  reviewReport: (reportId: string, body: { accepted: boolean; note: string; expected_version: number }) =>
    api.post<IcfReport>(`/icf/reports/${path(reportId)}/review`, body),
  exportReportJson: (reportId: string) =>
    api.get<Blob>(`/icf/reports/${path(reportId)}/export.json`, { responseType: 'blob' }),
  // HTML 导出走浏览器原生打印/新窗口，由调用方拼 URL（相对 API 根，勿再拼 /api）。
  exportReportHtmlUrl: (reportId: string) => `${API_BASE_URL}/icf/reports/${path(reportId)}/export.html`,
};
