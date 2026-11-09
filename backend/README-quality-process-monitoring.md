# Rehabilitation process monitoring

This API describes stored process facts. It does not define kidney ICF scores,
clinical targets, adherence, effectiveness, overdue thresholds or automatic
quality incidents. Clinical definitions require their own confirmed dictionary.

## Sources and authorization

`/api/quality-monitoring/overview`, `/followups`, `/plans` and `/report.csv` are
read-only medical/admin endpoints. The existing patient assignment policy is
applied before any aggregation or pagination. Doctors use `practitioners`;
health managers use `health_managers`. A requested patient outside the current
scope is rejected. Patients and unrelated roles cannot enumerate process data.
The authenticated medical/admin actor is also re-read through the shared
identity kernel and must map to exactly one active account with the same role.
Same-value ObjectId/string actor ambiguity, deactivation, disappearance or role
change fails before any source count, detail or CSV is returned.
Medical scope uses the shared read-only `core/patient_identity.py` grouping
kernel and is checked in one batch against both ObjectId and canonical
string account keys. Ambiguous identities stop the whole query with
`QUALITY_PATIENT_SCOPE_UNVERIFIED`; no partial counts or CSV are returned.
Unique patients that are inactive, missing or no longer assigned are excluded
from the default scope while other valid assigned patients remain visible.
Explicitly selecting an inactive or unassigned patient is rejected. An
explicitly selected admin patient receives the same
unique active-identity check, while admin all-source monitoring retains its
clearly labeled orphan/ambiguity counts.
A canonical patient-domain marker stops these legacy-domain reads; it never
falls back to user IDs after a patient-domain cutover.

Follow-up data is accessed through `FollowupService`; plan and publication facts
through `RehabPublicationService`. No legacy analytics or orphan training
collections participate. Publication validity checks the exact version pointer,
plan, patient, workflow and published status. No pointer or version contents,
clinical notes, draft text or account details are returned in monitoring rows.

Admin all-source monitoring can include records with missing, malformed,
ambiguous or dangling patient references. `scope_kind=all_source_records`
explicitly identifies this boundary, and `unresolved_patient_count` reports those
records across the whole source scope. Medical assignment filters cannot expose
such unrelated records. An explicit patient selection uses `selected_patient`;
otherwise medical scope is `assigned_patients`.

The detail field `patient_reference_state=valid` only confirms a unique patient
reference exists. It does not assert that the account is active or supported by
the manual-issue API. The separate `issue_eligible` flag requires a unique active
patient, a canonical 24-character ObjectId patient ID and an ObjectId source
record that the source API can load. In the admin all-source scope, legacy string
IDs, disabled/ambiguous accounts and noncanonical references remain countable
process facts but cannot
be registered through this action. This is a current UI affordance, not an
authorization token: issue creation always checks its own current source and
patient authorization again.
`source_reference_state=valid` additionally indicates a real BSON ObjectId source
that the source endpoint can address. A same-value string `_id` remains a distinct
unaddressable source; it must not navigate to the ObjectId record or open issue
registration. Compound/unconvertible source IDs are displayed only as an
unaddressable marker, with no raw source document exposed.

## Time and counting semantics

Both dates must include a timezone. Bounds are converted to UTC and form the
half-open interval `[start_date,end_date)`. Follow-ups use `scheduled_date`.
Plans use `created_at`: publication counts represent the **current publication
facts of the plans created in the selected window**, not publication events
that occurred inside that window.

`selected_total` counts the filtered date window; `scope_total`, missing-date,
invalid-date and unresolved-patient counts cover the whole authorized source
scope. Undated records cannot be attributed to a window. With no date filter,
they remain in the selected result, with an explicit date-quality marker.
Deleted records are excluded. Statuses outside the declared enum are grouped
as unknown, missing/null or invalid; they are not silently mapped to normal.

The two sources are read independently in real time and may have a time gap.
`read_consistency=independent_live_reads` and the CSV state this explicitly.
`generated_at` is the report construction time, not a cross-collection snapshot
timestamp. Count and details use the same source query construction, but two
separate requests can naturally change when business data changes.

Publication state is `published`, `unpublished`, `withdrawn`, `stopped`, or
`invalid_reference`. Withdrawn requires a recorded matching withdrawn version;
a history flag without its source record is invalid. Stopped denotes the stored
cancelled/canceled/archived parent state, without a new clinical judgment.
Published requires the same string-pointer type as patient-list selection and a
matching version with the required snapshot content, dates, nonempty item
identities/categories/names, publisher, publication time, confirmation note and
positive revision. `publication_validation=reference_and_required_structure`
states the boundary: this aggregation does not reproduce every nested Pydantic
content constraint and is not a guarantee that every nested clinical value is
readable, clinically valid or suitable for a patient. Malformed required fields
are classified `invalid_reference`, never normal publication success.

## CSV report

`GET /report.csv` accepts the same patient and date filters as the overview and
uses the same calculation. It returns actual UTF-8 BOM CSV, fixed filename
`quality-process-report.csv`, and no-store headers. Its metadata includes the
generation time, selected scope, date definitions and missing-data scope.
Potential spreadsheet formulas are escaped. The file is a process report, not
a clinical quality certificate or ICF report.

## Internal source fence

Manual quality workflows can call `FollowupService.quality_source()` and
`fence_quality_source()` inside their transaction. The latter performs a real
increment of the internal `_access_fence`, checks its type and matched source,
and leaves clinical mutation versions and update times unchanged. Public
follow-up DTOs omit it. Mongo change streams and database auditing still observe
this internal write; consumers must not interpret it as a clinical edit.

## Isolated verification

```bash
DEBUG=false PYTHONPATH=backend \
REHAB_TEST_QUALITY_MONITORING_MONGO_URI='mongodb://127.0.0.1:<private-test-port>' \
backend/.venv/bin/python -m pytest -q backend/tests/test_quality_monitoring.py
```

Only a disposable local Mongo should be used. Tests create and delete uniquely
named synthetic databases. This read-only aggregation suite does not need a
replica set; the separate incident workflow does require transactions.
