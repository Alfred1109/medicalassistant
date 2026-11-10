import api from './httpClient';
import type {
  CatalogCenter, CatalogForm, CatalogProject, CatalogResult, CatalogSubject,
  AddPatientContext, CreatePatientLink, LocalLinkPatient, PatientLink, PatientLinksResult, PatientReference,
  CreateFormBinding, FormBinding, FormBindingsResult, ImportedPerson, ImportedPeopleResult, ImportedRole,
} from '../types/formCatalog';

const ROOT = '/integrations/forms';
interface PageQuery { limit?: number; cursor?: string; }

export const formCatalog = {
  projects: (query: PageQuery = {}, signal?: AbortSignal) => api.get<CatalogResult<CatalogProject>>(`${ROOT}/catalog/projects`, { params: query, signal }),
  importedPeople: (projectId: number, signal?: AbortSignal) => api.get<{ people: ImportedPerson[] }>(`${ROOT}/catalog/projects/${projectId}/people`, { signal }),
  importPeople: (projectId: number) => api.post<ImportedPeopleResult>(`${ROOT}/catalog/projects/${projectId}/people/import`),
  assignImportedRole: (userId: string, role: ImportedRole, evidence_reference: string) => api.post<ImportedPerson>(`${ROOT}/catalog/people/${encodeURIComponent(userId)}/role`, { role, evidence_reference }),
  setImportedCare: (patientId: string, practitionerId: string, assigned: boolean, evidence_reference: string) => api.post<ImportedPerson>(`${ROOT}/catalog/people/${encodeURIComponent(patientId)}/care`, { practitioner_id: practitionerId, assigned, evidence_reference }),
  centers: (projectId: number, query: PageQuery = {}, signal?: AbortSignal) => api.get<CatalogResult<CatalogCenter>>(`${ROOT}/catalog/projects/${projectId}/centers`, { params: query, signal }),
  subjects: (projectId: number, centerId: number, query: PageQuery = {}, signal?: AbortSignal) => api.get<CatalogResult<CatalogSubject>>(`${ROOT}/catalog/projects/${projectId}/subjects`, { params: { ...query, center_id: centerId, status: 'all' }, signal }),
  forms: (projectId: number, query: PageQuery = {}, signal?: AbortSignal) => api.get<CatalogResult<CatalogForm>>(`${ROOT}/catalog/projects/${projectId}/forms`, { params: { ...query, status: 'active' }, signal }),
  formVersion: (projectId: number, formId: number, signal?: AbortSignal) => api.get<{ form: CatalogForm; version: NonNullable<CatalogForm['current_version']> }>(`${ROOT}/catalog/projects/${projectId}/forms/${formId}/version`, { signal }),
  patientReference: (projectId: number, centerId: number, subjectId: number, signal?: AbortSignal) => api.get<PatientReference>(`${ROOT}/catalog/projects/${projectId}/centers/${centerId}/subjects/${subjectId}/patient-reference`, { signal }),
  localPatients: (skip = 0, limit = 100, signal?: AbortSignal) => api.get<LocalLinkPatient[]>('/admin/patients', { params: { skip, limit }, signal }),
  links: (skip = 0, limit = 20, signal?: AbortSignal) => api.get<PatientLinksResult>(`${ROOT}/patient-links`, { params: { skip, limit }, signal }),
  createLink: (body: CreatePatientLink) => api.post<PatientLink>(`${ROOT}/patient-links`, body),
  revokeLink: (id: string, reason: string) => api.post<PatientLink>(`${ROOT}/patient-links/${encodeURIComponent(id)}/revoke`, { reason }),
  addLinkContext: (id: string, body: AddPatientContext) => api.post<PatientLink>(`${ROOT}/patient-links/${encodeURIComponent(id)}/contexts`, body),
  formBindings: (skip = 0, limit = 20, signal?: AbortSignal) => api.get<FormBindingsResult>(`${ROOT}/form-bindings`, { params: { skip, limit }, signal }),
  createFormBinding: (body: CreateFormBinding) => api.post<FormBinding>(`${ROOT}/form-bindings`, body),
  revokeFormBinding: (id: string, reason: string) => api.post<FormBinding>(`${ROOT}/form-bindings/${encodeURIComponent(id)}/revoke`, { reason }),
};

export function formCatalogError(error: unknown, fallback: string): string {
  const value = error as { response?: { status?: number; data?: { detail?: unknown; message?: unknown; } }; message?: unknown };
  const detail = value?.response?.data?.detail;
  if (value?.response?.status === 403) return '当前账号没有访问这项来源资料的权限。';
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message;
  if (typeof detail === 'string') return detail;
  if (typeof value?.response?.data?.message === 'string') return value.response.data.message;
  return fallback;
}
