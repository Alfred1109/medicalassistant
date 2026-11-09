# Patient self-reported rehabilitation execution

`POST /api/rehabilitation/plans/{plan_id}/patient-feedback` accepts a client UUID,
the exact published `version_id` and `prescription_item_id`, self-reported
`execution_status` (`completed`, `partial`, `not_done`), `feelings`, and an
explicitly timezone-aware `performed_at`. The report is a patient's statement;
it does not update the plan's exercise counters, adherence, clinical assessment,
or diagnosis. Historical progress is not copied into this stream.

Only the currently authenticated patient can submit. The current legacy patient
account and plan ownership are rechecked in the transaction. A canonical patient
domain refuses this account-by-patient-ID rule until its explicit identity
resolver is integrated. Clinicians cannot impersonate patients through this API.

New submissions require the parent's current publication pointer, a published
`patient_publication` version belonging to that plan and patient, and an item
present in that version's frozen `items_snapshot`. A version change requires the
patient to refresh and reconfirm. Cancellation, archive or withdrawal prevents
new submissions. A completed plan can retain its published version and accept
patient recollections. Authenticated, authorized users can still read historical
reports, including after a withdrawal; every historical reference is validated
against its exact frozen publication and item.

`rehab_execution_events` is the only report store. New reports use
`event_type=patient_report`, `schema_version=1` and the protected stored event key
`patient-report:<account-id>:<client-uuid>`. General execution-event APIs reject
this namespace and do not accept a client-selected event type. Listing patient
reports requires matching patient, account, explicit report type and schema;
old generic events are not presented as patient feedback.

The unique `(plan_id,event_id)` index is mandatory. Its creation or validation
failure stops writes; there is no read-before-insert fallback. Payloads are
normalized and hashed. A matching request returns the original record; the same
key with changed content returns conflict. A successful request can be replayed
after a new version is published, because a replay does not create new feedback.

Writes use MongoDB snapshot/majority transactions. Real internal `_access_fence`
writes on accounts and `_publication_fence` writes on the parent plan cause
concurrent deactivation, ownership or publication changes to conflict and be
rechecked. Plan business revisions and update timestamps are not changed.
These internal writes are visible to Mongo change streams. Event insertion and
the internal fences commit or roll back together. No standalone sequential-write
fallback is supported.

The list endpoint has server-side pagination and a true total. Responses are
explicit field projections, use UTC timestamps, and carry `Cache-Control:
no-store`. UI rendering must treat all patient text as untrusted text.

For isolated replica-set verification:

```bash
DEBUG=false PYTHONPATH=backend \
REHAB_TEST_PATIENT_FEEDBACK_URI='mongodb://127.0.0.1:<isolated-port>/?directConnection=true' \
backend/.venv/bin/python -m pytest -q backend/tests/test_rehab_patient_feedback.py
```

Never point this suite at a shared or production database.
