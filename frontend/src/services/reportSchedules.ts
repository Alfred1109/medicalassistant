import api from './httpClient';

export interface ReportCatalogItem { id: string; label: string; formats: string[]; timeRanges: string[] }
export type ReportFrequency = 'once' | 'daily' | 'weekly' | 'monthly';

export interface ReportSchedulePayload {
  name: string;
  description?: string;
  reportId: string;
  frequency: ReportFrequency;
  timeRange: string;
  format: 'html';
  recipients: string[];
  nextRunTime?: string;
  time?: string;
  weekday?: number;
  monthDay?: number;
}

export interface ReportSchedule extends Omit<ReportSchedulePayload, 'format'> {
  id: string;
  format: string;
  reportName?: string | null;
  enabled: boolean;
  createdBy: string;
  executionVersion?: number | null;
  lastRunTime?: string | null;
  lastRunStatus?: string | null;
  retryCount?: number | null;
}

export interface ReportRun {
  id: string;
  scheduleId: string;
  reportId: string;
  reportName: string;
  generatedAt: string | null;
  scheduledFor: string | null;
  status: string;
  format: string;
}

const root = '/report-schedules';
export const reportSchedules = {
  catalog: (signal?: AbortSignal) => api.get<{ items: ReportCatalogItem[] }>(`${root}/catalog`, { signal }),
  list: (signal?: AbortSignal) => api.get<ReportSchedule[]>(root, { signal }),
  create: (body: ReportSchedulePayload) => api.post<{ id: string }>(root, body),
  update: (id: string, body: ReportSchedulePayload) => api.put(`${root}/${encodeURIComponent(id)}`, body),
  toggle: (id: string, enabled: boolean) => api.patch(`${root}/${encodeURIComponent(id)}/toggle`, null, { params: { enabled } }),
  runs: (skip: number, limit: number, signal?: AbortSignal) =>
    api.get<{ items: ReportRun[]; total: number }>(`${root}/runs`, { params: { skip, limit }, signal }),
  run: (id: string) => api.get<ReportRun & { html: string }>(`${root}/runs/${encodeURIComponent(id)}`),
};
