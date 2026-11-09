export interface CatalogSource { system: string; environment: string; }
export interface CatalogPage { limit: number; has_more: boolean; next_cursor: string | null; }
export interface CatalogResult<T> { data: T[]; page: CatalogPage; }
export interface CatalogProject { project_id: number; name: string; status: string; source: CatalogSource; }
export interface CatalogCenter { center_id: number; project_id: number; name: string | null; center_code: string; status: string; }
export interface CatalogSubject { subject_id: number; project_id: number; center_id: number | null; code: string; status: string; }
export interface CatalogForm {
  form_id: number; project_id: number; title: string; status: string;
  current_version: null | { form_id: number; family_id: number; version: number; version_state: string; definition_sha256: string | null; };
}
export interface PatientReference {
  source: CatalogSource; project_id: number; center_id: number; subject_id: number;
  patient_id: number; patient_archive_id: number;
}
export interface PatientLink {
  id: string; local_patient_id: string; reference: PatientReference;
  references?: PatientReference[];
  status: string; verified_at: string; revoked_at?: string | null;
}
export interface PatientLinksResult { items: PatientLink[]; skip: number; limit: number; total: number; }
export interface LocalLinkPatient { id: string; name?: string; status?: string; }
export interface CreatePatientLink {
  local_patient_id: string; project_id: number; center_id: number; subject_id: number;
  evidence_reference: string; identity_verified: true;
}
export type AddPatientContext = Omit<CreatePatientLink, 'local_patient_id'>;
export type FormPurpose = 'initial_assessment' | 'followup' | 'reassessment';
export interface FormBinding {
  id: string; project_id: number; form_id: number; version: number; title: string;
  version_ref: NonNullable<CatalogForm['current_version']>;
  purpose: FormPurpose; status: string; verified_at: string;
}
export interface FormBindingsResult { items: FormBinding[]; skip: number; limit: number; total: number; }
export interface CreateFormBinding {
  project_id: number; form_id: number; version: number; purpose: FormPurpose;
  evidence_reference: string; confirmed: true;
}
