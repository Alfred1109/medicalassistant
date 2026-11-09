export interface FollowUpReminderStatus {
  enabled: boolean;
  running: boolean;
  state: string;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_error_code: string | null;
}

export interface FollowUpReminderRecord {
  policy: string;
  followup_id: string;
  patient_id: string;
  slot: string;
  status: 'persisted' | 'skipped' | 'failed' | (string & {});
  reason: string | null;
  planned_at: string;
  checked_at: string;
  notification_id?: string;
}

export interface FollowUpReminderPage {
  items: FollowUpReminderRecord[];
  total: number;
  skip: number;
  limit: number;
}
