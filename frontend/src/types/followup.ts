/** FollowUpRecordResponse contract from backend/app/schemas/followup.py. */
export interface FollowUpQuestion {
  question_id: string;
  question_text: string;
  question_type: string;
  options?: Array<Record<string, string>> | null;
  required: boolean;
  order: number;
}

export interface FollowUpAnswer {
  question_id: string;
  answer_value: unknown;
  answer_text?: string | null;
  answered_at: string;
}

export interface FollowUpRecord {
  id: string;
  patient_id: string;
  created_by: string;
  provider_id: string;
  follow_up_type: string;
  scheduled_date: string;
  actual_date?: string | null;
  status: string;
  mutation_version: number;
  notes?: string | null;
  description: string;
  created_at: string;
  updated_at: string;
  questions?: FollowUpQuestion[];
  answers?: FollowUpAnswer[];
  related_records?: string[];
  metadata?: Record<string, unknown>;
  follow_up_result?: string | null;
  next_follow_up_id?: string | null;
  template_id?: string | null;
  reminder_before?: number | null;
  completion_data?: Record<string, unknown> | null;
  current_evidence?: {
    source: 'manual_entry' | 'external_form' | 'ambiguous' | 'unknown';
    submission_id?: string;
    submitted_version?: number;
    legacy?: boolean;
  } | null;
  submission_history?: Array<Record<string, unknown>>;
  cancellation_data?: Record<string, unknown> | null;
  visit_code?: string | null;
  review?: Record<string, unknown> | null;
  effective_response?: Record<string, unknown> | null;
  fill_task_ids?: string[];
  previous_visit_id?: string | null;
  next_visit_id?: string | null;
  // T73 随访小结（存量文档缺省为 null）
  followup_summary?: {
    conclusion: string;
    next_plan_suggestion?: string | null;
    abnormal_findings?: string | null;
    recorded_by?: string | null;
    recorded_at?: string | null;
  } | null;
  // Local display enrichment; never used as an identity or authorization key.
  patient_name?: string;
}

export interface FollowUpFilters {
  follow_up_type?: string;
  status?: string;
  start_date?: string | null;
  end_date?: string | null;
  patient_name?: string;
}

export interface FollowUpWorkbenchQuery {
  patient_id?: string;
  status?: string;
  follow_up_type?: string;
  start_date?: string;
  end_date?: string;
  patient_name?: string;
  skip: number;
  limit: number;
}

export interface FollowUpWorkbenchPage {
  items: FollowUpRecord[];
  total: number;
  skip: number;
  limit: number;
  status_counts?: Record<string, number>;
}

// T73 随访小结提交（结论必填，后端 FollowUpSummaryPayload）
export interface FollowUpSummaryPayload {
  conclusion: string;
  next_plan_suggestion?: string;
  abnormal_findings?: string;
}

export interface ReviewFollowUpRequest {
  decision: 'approved' | 'returned';
  expected_version: number;
  comment?: string;
  evidence?: Record<string, unknown>;
}

export interface ReEvaluateFollowUpRequest {
  scheduled_date: string;
  reason?: string;
}
