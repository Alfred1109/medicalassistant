# Follow-up in-app reminders

The confirmed policy is one in-app reminder to the patient account and the
explicit responsible clinician, during the 24 hours before a scheduled plan.
Only `scheduled` and `awaiting_fill` nodes qualify. There is no catch-up after
the plan time, no automatic overdue/lost transition, and no SMS/email channel.
Legacy `reminder_before` and `reminder_settings.days_before` are not read: their
historical units differ.

## Release configuration and lifecycle

`FOLLOWUP_REMINDERS_ENABLED=false` is the default. Enabling this release can
create real notifications for existing eligible records, so enable it only in
the intended deployment after testing its source data and recipient rules.
`FOLLOWUP_REMINDERS_POLL_SECONDS` defaults to 30 (accepted range 1–300).
Start/stop the application through the root `start.sh` / `stop.sh`. Startup
checks replica-set support and creates the reminder indexes before dispatch;
storage failure leaves this feature stopped, while its status reports an error.
There is no standalone or sequential-write fallback. Restart after repairing a
startup storage problem. Per-plan persistence failures are recorded with a
retryable `failed` status when storage permits, do not block other due plans, and
are retried each poll. An uncertain committed winner is never overwritten by a
failure record.
Shutdown cancels and awaits the scanner before closing the Mongo client.

The current application launcher still enforces one worker. Multiple concurrent
dispatchers are safe against duplicate notification creation through the ledger
and transactions; that does not remove the application's separate WebSocket
multi-worker acceptance requirements. Realtime notification hints remain best
effort; the durable inbox is authoritative.

## Identity and concurrency

Legacy patients resolve only to the same unique, active `users(role=patient)`
document. A name, source patient reference, or an unrelated account never grants
access. Clinicians require explicit top-level `provider_id`, an active doctor or
health-manager account, and the corresponding current patient assignment. A
canonical patient-domain marker stops dispatch with
`REMINDER_PATIENT_DOMAIN_UNSUPPORTED`; there is no users fallback after cutover.

Each event is identified by policy, node, exact UTC plan time, patient and
recipient slot; the provider slot also contains its explicit account identity.
Ordinary edits and deletion of an inbox notification do not generate it again.
Missing/disabled accounts and unavailable assignments produce retryable skipped
history; restoring them before the plan time allows the next scan to generate
exactly one notification. Retrying after the plan time cannot send it.

The delivery ledger and notifications commit in one majority/snapshot Mongo
transaction. A real `$inc` of internal `_reminder_fence` on the source node and
the relevant accounts serializes dispatch against concurrent cancellation,
rescheduling, deactivation and assignment changes; a conflict retries and
revalidates the source. A no-op update was tested and does **not** provide this
guarantee. Neither `mutation_version`, `updated_at`, business fields nor clinical
audit records are changed by the fence. Existing fence values must be nonnegative
integers; malformed values fail closed.

The fence is an internal persisted top-level field. User constructors accept and
discard it; public user DTOs and the explicit follow-up mapping omit it. Mongo
change streams **do observe the fence updates**, including their transaction
metadata. There are currently no users/follow-up change-stream consumers in this
application; future consumers must classify these internal updates separately
from clinical edits. Do not claim that reminder dispatch is invisible to change
streams or database auditing.

## Visible status and evidence

`GET /api/health-records/followup-reminders/status` reports enabled/running state,
last scan/success and a sanitized error code. `GET .../followup-reminders` supports
`followup_id`, `skip`, `limit` and returns history only within the current medical
patient scope. These endpoints are for clinicians and administrators.

`persisted` means a notification was generated in the system inbox. It does not
mean delivered or read. Notification content contains no patient name or clinical
details. Its entity is `followup`; opening the entity must recheck current object
authorization. User deletion of the notification does not delete reminder history.
Skipped history describes the latest checked reason, not a permanent decision to
withhold a reminder. A scan never automatically revisits already-past plans.

## Isolated verification

Use a disposable local replica set and a unique test database per test:

```bash
DEBUG=false PYTHONPATH=backend \
REHAB_TEST_REMINDER_MONGO_URI='mongodb://127.0.0.1:<isolated-port>/?directConnection=true' \
backend/.venv/bin/python -m pytest -q backend/tests/test_followup_reminders.py
```

Never point this suite at a shared or production database.
