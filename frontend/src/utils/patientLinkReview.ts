import type { AddPatientContext, CatalogCenter, CatalogForm, CatalogProject, CatalogSubject, CreateFormBinding, CreatePatientLink, FormPurpose, PatientLink, PatientReference } from '../types/formCatalog';

export function buildPatientLinkReview(input: {
  localPatientId: string; project: CatalogProject | null; center: CatalogCenter | null;
  subject: CatalogSubject | null; reference: PatientReference | null;
  evidenceReference: string; identityVerified: boolean;
}): CreatePatientLink {
  const { project, center, subject, reference } = input;
  if (!input.localPatientId || !project || !center || !subject || !reference) throw new Error('请选择完整的患者与来源档案。');
  if (center.project_id !== project.project_id || subject.project_id !== project.project_id || subject.center_id !== center.center_id
      || reference.project_id !== project.project_id || reference.center_id !== center.center_id || reference.subject_id !== subject.subject_id
      || reference.source.system !== project.source.system || reference.source.environment !== project.source.environment) {
    throw new Error('来源档案已变化，请重新选择并核实。');
  }
  const evidence = input.evidenceReference.trim();
  if (!input.identityVerified || !evidence || evidence.length > 256) throw new Error('请先核实患者对应关系并填写不超过 256 字的证据引用。');
  return { local_patient_id: input.localPatientId, project_id: project.project_id, center_id: center.center_id,
    subject_id: subject.subject_id, evidence_reference: evidence, identity_verified: true };
}

export const FORM_PURPOSE_LABELS: Record<FormPurpose, string> = {
  initial_assessment: '初评', followup: '随访', reassessment: '复评',
};

export function canAddPatientContext(link: PatientLink, reference: PatientReference | null): boolean {
  if (!reference || link.status !== 'verified' || reference.patient_id !== link.reference.patient_id
      || reference.source.system !== link.reference.source.system || reference.source.environment !== link.reference.source.environment) return false;
  return !(link.references || [link.reference]).some(item => item.project_id === reference.project_id
    && item.center_id === reference.center_id && item.subject_id === reference.subject_id);
}

export function buildPatientContextReview(link: PatientLink, input: Parameters<typeof buildPatientLinkReview>[0]): AddPatientContext {
  if (input.localPatientId !== link.local_patient_id || !canAddPatientContext(link, input.reference)) throw new Error('只能为同一位已核实患者追加新的项目引用。');
  const { local_patient_id: _, ...body } = buildPatientLinkReview(input);
  return body;
}

export function buildFormBindingReview(input: { project: CatalogProject | null; form: CatalogForm | null; purpose: FormPurpose | ''; evidenceReference: string; confirmed: boolean }): CreateFormBinding {
  const { project, form } = input;
  const version = form?.current_version;
  if (!project || !form || form.project_id !== project.project_id || !version || version.form_id !== form.form_id
      || version.version_state !== 'current' || !version.definition_sha256) throw new Error('请选择具有正式发布版本的问卷。');
  if (!Object.prototype.hasOwnProperty.call(FORM_PURPOSE_LABELS, input.purpose) || !input.confirmed || !input.evidenceReference.trim() || input.evidenceReference.trim().length > 256) throw new Error('请明确问卷用途，并填写不超过 256 字的核实依据引用。');
  return { project_id: project.project_id, form_id: form.form_id, version: version.version,
    purpose: input.purpose as FormPurpose, evidence_reference: input.evidenceReference.trim(), confirmed: true };
}
