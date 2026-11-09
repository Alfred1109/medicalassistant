# Manual process quality issues

This workflow records a concern entered by an authorized clinician. It does not
infer a clinical abnormality, choose ICF thresholds or mark a clinical outcome as
failed. Every entry references an existing same-patient follow-up or rehabilitation
plan. Evidence references identify the human review/action records; they are not
automatically verified attachments.

The patient identity domain remains legacy and account-backed. An existing
canonical patient-domain marker causes a fail-closed error; the workflow cannot
infer a new source patient/account association.

## Workflow and authorization

- Creation produces `open`, version 0. It requires a title, description and at
  least one evidence reference.
- Assignment selects a currently active doctor or health manager who is actually
  assigned to the same patient. Reassignment is available only in `open` or
  `in_progress`, returns the issue to `open`, and requires fresh confirmation.
- Only the current assignee may confirm (`open` to `in_progress`) and submit a
  disposition (`in_progress` to `pending_review`). The disposition includes a
  statement and evidence references.
- Any currently authorized doctor or health manager may review, including the
  handler, as explicitly chosen by the user. Approval closes the issue; return
  goes to `in_progress` for a new disposition. Every reviewer is recorded.
- Closed issues have no delete or edit endpoint. Return, reassignment, earlier
  dispositions and reviews remain in the append-only timeline.
- Administrators have read access only. Patient and research roles do not access
  the workflow. Clinical scope uses the current patient-side `practitioners` or
  `health_managers` relation, never a creator/assignee shortcut.

All ordinary reads are limited to active, currently authorized patient records,
including the administrator list. Deactivating a patient or removing a clinical
assignment hides the issue from that ordinary scope without deleting history.
This is not a specialized retained-history audit search interface.
List scope also verifies unique account identity before converting identifiers
to patient references. An ObjectId and a string user key with the same visible
value cannot be merged into one authorization scope: the list fails closed and
asks for identity review. Detail, assignee selection and mutations likewise
require a unique active account.
Identity candidate expansion and grouping use the shared read-only
`core.patient_identity` helper; the quality service retains its own role,
assignment, error and transactional fence policy. List and directory checks
read candidates in batches rather than querying once per patient.

## Atomicity and source facts

`quality_issues` holds the issue and its versioned timeline. Each successful
operation also inserts a deterministic receipt in `quality_issue_operations` in
the same majority/snapshot MongoDB transaction. Every mutation requires
`expected_version` and `request_id`; an exact replay returns the current issue
without repeating its transition. A reused key with different content is a
conflict. A stale version is a conflict, not a last-writer overwrite.

MongoDB replica-set transactions are required. There is no standalone or
sequential-write fallback. Missing storage/transaction support fails the write.
The receipt's `_id` provides database-enforced idempotency independently of a
read-before-insert check.

Writes re-read current actor, patient and assignment state inside the transaction.
Real internal `_access_fence` updates on the participating account documents
serialize against concurrent deactivation and assignment changes. Creation also
locks its actual same-patient source through the source domain service, preventing
an issue from being committed against a concurrently deleted/reassigned source.
Source metadata is not copied into the issue.

The internal fences are persisted updates and are visible to MongoDB change
streams. They do not change clinical mutation versions, business timestamps or
clinical audit fields. Future change-stream consumers must classify those updates
separately from clinical edits.

## API

All paths are under `/api/quality/issues`:

- `GET /assignees?patient_id=...` gives current eligible responsible clinicians.
- `GET` lists the current authorized range with patient/status/assignee filters,
  stable pagination and a matching total.
- `POST` creates an issue, returning 201 on creation and 200 on exact replay.
- `GET /{id}` reads its detail and timeline.
- `POST /{id}/assign`, `/confirm`, `/resolve`, `/review` perform the transitions.

The API has no arbitrary navigation URL, severity inference, automatic candidate
insertion, bulk close or destructive audit operation. Responses use explicit
projections and UTC offsets, disable caching, and do not expose account passwords
or clinical source payloads.

## Isolated verification

Use only a disposable local replica set and the unique databases created by the
tests:

```bash
DEBUG=false PYTHONPATH=backend \
REHAB_TEST_QUALITY_ISSUE_MONGO_URI='mongodb://127.0.0.1:<isolated-port>/?directConnection=true' \
backend/.venv/bin/python -m pytest -q backend/tests/test_quality_issues.py
```

The suite covers the complete self-review workflow, return and evidence history,
current role/assignment scope, real source references, parallel idempotency and
CAS, transaction rollback, revocation and source-change races, retained history
after deactivation, and REST/cache contracts. Never point it at shared or
production data.
