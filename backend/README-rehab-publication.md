# Clinical rehabilitation drafts and patient publications

This workflow reuses `rehab_plan_versions` and `rehab_prescription_items`.
Versions tagged `workflow=patient_publication` are edited only through the new
publication draft API. A draft version and its prescription items are the single
editable content source; publishing freezes a whitelist in that version and
sets `rehab_plans.published_version_id` in the same majority/snapshot transaction.
Legacy active plans, generated drafts, old approval flags and automatically
created exercise schedules are never silently published or copied as clinical
instructions. Every intervention and schedule is explicitly entered and confirmed
by a currently assigned doctor or health manager. System administration alone
does not grant a clinical publication capability.

The patient reads only the current explicit published pointer. Draft changes
leave the previous publication visible until the new draft is confirmed.
The draft response includes the safe current publication, so a clinician can
explicitly use it as the basis of an adjustment. Stable item IDs can be carried
from that publication into the next draft; arbitrary old or foreign IDs cannot.
Published snapshots never resolve changing exercise-library content at read time.
Absent intervention categories are not filled with generated recommendations.

Withdraw, cancel and archive share one operation. They retain the frozen version
and its audit, clear the patient-visible pointer, and increment the publication
revision atomically. Cancel sets the parent status to `cancelled`; archive sets
it to `archived`; withdraw alone leaves the parent status unchanged. Restoring
an old parent status cannot restore the cleared pointer. A permanent
`has_publication_history` protects the record against legacy hard deletion.
Publication and withdrawal use expected draft/pointer revisions and persisted
request fingerprints; duplicate requests do not create duplicate versions, and
reusing a key for different content is rejected.

MongoDB replica-set transactions are required; there is no sequential-write
fallback. Explicit writes install unique `(plan_id,version_no)` and
`(version_id,item_id)` indexes. Existing duplicate/malformed versions must be
reviewed rather than repaired silently. The only additional collection,
`rehab_publication_operations`, stores command idempotency/audit references, not
another prescription content source.

Current identity mapping is legacy-only: one unique active `users(role=patient)`
document is the clinical patient account. A canonical patient-domain marker stops
this mapping; it never falls back to users after a future cutover. Every write
rechecks active operator, active patient and current role-specific assignments
inside its transaction. Real increments of internal `_access_fence` on account
documents and `_publication_fence` on the plan make concurrent stop/reassignment,
publication, deletion and withdrawal conflict and revalidate. The fields are
not public DTO fields or clinical revisions. Mongo change streams observe these
internal writes; consumers must not interpret them as clinical content edits.

The new endpoints live below `/api/rehabilitation/publications`. Patient outputs
use explicit content/item whitelists, omit internal notes and metadata, and
serialize UTC dates with offsets. Responses are `no-store`. Patient execution
feedback is handled by its dedicated event workflow and does not mutate a
published prescription or infer training completion percentages. Legacy generic
event APIs reject reserved patient-report identifiers and publication-workflow
items; unique event-index failure blocks event writes.

Validation uses a disposable local replica set:

```bash
DEBUG=false PYTHONPATH=backend \
REHAB_TEST_PUBLICATION_MONGO_URI='mongodb://127.0.0.1:<isolated-port>/?directConnection=true' \
backend/.venv/bin/python -m pytest -q backend/tests/test_rehab_publications.py
```

The tests create unique databases and delete only those databases. Never point
them at a shared or production database. This local implementation is not a
production deployment or clinical acceptance record.
