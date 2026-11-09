import httpClient from './httpClient';
import type { FollowUpReminderPage, FollowUpReminderStatus } from '../types/followupReminders';

export const followupReminders = {
  status: (signal?: AbortSignal) => httpClient.get<FollowUpReminderStatus>('/health-records/followup-reminders/status', { signal }),
  history: (followupId: string, skip = 0, limit = 20, signal?: AbortSignal) =>
    httpClient.get<FollowUpReminderPage>('/health-records/followup-reminders', { params: { followup_id: followupId, skip, limit }, signal }),
};
