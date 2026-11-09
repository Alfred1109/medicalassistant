export type QualitySource = 'followup' | 'rehab_plan';
export type QualityIssueStatus = 'open' | 'in_progress' | 'pending_review' | 'closed';
export interface QualityFilters { patient_id?: string; start_date?: string; end_date?: string; }
export interface QualityPage<T> { items: T[]; total: number; skip: number; limit: number; }
export interface ProcessSummary {
  selected_total: number; scope_total: number; missing_date_count: number; invalid_date_count: number; unresolved_patient_count: number;
  by_status: Array<{status: string; count: number}>;
}
export interface QualityOverview {
  generated_at: string;
  scope_kind: 'assigned_patients' | 'all_source_records' | 'selected_patient'; read_consistency: 'independent_live_reads';
  publication_validation: 'reference_and_required_structure';
  window: { start_date: string | null; end_date: string | null; followup_date_field: string; plan_date_field: string };
  followups: ProcessSummary & { in_review_count: number };
  plans: ProcessSummary & { publication_states: Array<{state: string; count: number}> };
}
export interface QualityFact {
  source_type: QualitySource; source_id: string; patient_id: string | null; status: string;
  source_reference_state: 'valid' | 'unaddressable';
  date: string | null; date_quality: 'valid' | 'missing' | 'invalid'; publication_state?: string | null;
  patient_reference_state: 'valid' | 'missing' | 'invalid' | 'not_found' | 'ambiguous';
  issue_eligible: boolean;
}
export interface QualityFactPage extends QualityPage<QualityFact> { date_field: string; }
export interface QualityIssue {
  id: string; patient_id: string; source_type: QualitySource; source_id: string; title: string;
  description: string; status: QualityIssueStatus; version: number; assignee_id: string | null;
  created_by: string; created_at: string; updated_at: string;
}
export interface QualityIssueDetail extends QualityIssue {
  evidence_refs: string[]; resolution?: string | null;
  timeline: Array<{action: string; actor_id: string; at: string; note: string;
    evidence_refs?: string[]; assignee_id?: string; decision?: string;
    from_status: string | null; to_status: string; version: number}>;
}
export interface QualityAssignee { id: string; name: string; role: string; }
export interface CreateQualityIssue {
  request_id: string; patient_id: string; source_type: QualitySource; source_id: string;
  title: string; description: string; evidence_refs: string[];
}
