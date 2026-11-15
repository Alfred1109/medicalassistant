import api from './httpClient';

// 患者端临床功能面（T75）：宣教消费 / 本人指标对照 / 本人预警。
// 全部走患者自取端点：宣教 GET /clinical/education（患者角色后端自取本人）、
// 指标与预警 GET /clinical/patients/{id}/...（后端做对象级 self 授权），
// 阅读反馈 POST /clinical/education/assignments/{id}/read（后端仅患者本人）。
export interface PatientEducationMaterial {
  id: string;
  title: string;
  body: string;
  author_id: string;
  assignment_id: string;
  status: string;
  feedback: string;
  guidance: string;
}

export interface PatientIndicatorRow {
  id: string;
  label: string;
  source_label: string;
  unit: string;
  low: number | null;
  high: number | null;
  icf_code: string;
  state: 'inside' | 'outside' | 'missing' | 'unbounded' | 'not_numeric';
  value: string | null;
}

export interface PatientIndicatorsResult {
  configured: boolean;
  indicators: PatientIndicatorRow[];
  coverage: { matched: number; defined: number } | null;
  within_bounds: { inside: number; compared: number } | null;
  message: string;
}

export interface PatientHealthAlert {
  id: string;
  patient_id: string;
  data_type: string | null;
  value: unknown;
  vital_type: string | null;
  test_name: string | null;
  unit: string | null;
  alert_level: string;
  status: string;
  recorded_at: string | null;
  created_at: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
}

const path = (patientId: string, suffix: string) =>
  `/clinical/patients/${encodeURIComponent(patientId)}${suffix}`;

export const patientClinical = {
  education: (signal?: AbortSignal) =>
    api.get<{ materials: PatientEducationMaterial[] }>('/clinical/education', { signal }),
  acknowledgeEducation: (assignmentId: string, feedback: string) =>
    api.post(`/clinical/education/assignments/${encodeURIComponent(assignmentId)}/read`, { feedback }),
  indicators: (patientId: string, signal?: AbortSignal) =>
    api.get<PatientIndicatorsResult>(path(patientId, '/indicators'), { signal }),
  alerts: (patientId: string, skip = 0, limit = 100, signal?: AbortSignal) =>
    api.get<{ alerts: PatientHealthAlert[] }>(path(patientId, '/alerts'),
      { params: { skip, limit }, signal }),
};
