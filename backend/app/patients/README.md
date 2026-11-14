# Clinical patients and optional login accounts

This module is a foundation, not an already enabled business-domain migration.
Existing routes and user services have not been changed by this module.

`clinical_patients` contains clinical entities. New source patients require no
local user, email, password, identity binding or self-service permission. Their
physician/health-manager assignment lists start empty. Callers must validate a
remote reference and perform human review before invoking `create_from_source`;
the repository does not attest source authorization or grant object access.

Reads and writes require the durable `patient_domain_state` singleton
`clinical-patients-v1` to be canonical. There is no users fallback. Missing,
inactive, deleted or otherwise unavailable canonical patients cannot inherit
legacy account relations. Source identity uniqueness includes exact normalized
origin, system, environment and global source patient ID; subject and archive
references for individual projects remain separate from this global identity.

The explicit migration preserves legacy patient `_id` values, clinical fields
and existing patient-side assignment lists. Existing business references need
no ID rewrite. `users` remain read-only. For each legacy patient document, the
transaction creates one explicit `patient_account_links` relation with equal
account/patient IDs and source `legacy_same_document`, reviewer, evidence and
time. This records an existing intrinsic relation, never a name-based match.
Inactive legacy accounts produce disabled links. New source patients produce
no accounts or links. `legacy_user_id` alone never grants access. `resolve_self`
requires the explicit verified link, an unambiguous active local patient account
and active canonical clinical patient; it never repairs missing/disabled links. Unknown/malformed legacy data causes rejection rather than guessed data.
Review any legacy assignments before exposing them through new business policy.

## Controlled migration

Use a reviewed environment with the exact Mongo URL and DB explicitly loaded.
The tool never prints credentials. Inspect by default:

```bash
DEBUG=false backend/.venv/bin/python backend/scripts/manage_clinical_patients.py \
  --manifest-output /private/new-inspection.json
```

**Cutover is currently disabled in the CLI** because existing business routes
have not yet been migrated. The following command documents a future procedure;
it will refuse to apply until that integration and its verification are complete.
After a full database backup and independent recovery rehearsal, stop the
application using its `stop.sh`. Application writers, scheduled tasks and any
external direct database tools must be excluded by the deployment procedure.
Only then apply with the exact manifest, database and listener ports:

```bash
DEBUG=false backend/.venv/bin/python backend/scripts/manage_clinical_patients.py \
  --apply --expected-manifest /private/new-inspection.json \
  --expected-database-name '<reviewed-db>' \
  --backup-directory /private/new-patient-migration \
  --reviewer '<reviewer-reference>' --evidence-reference '<review-evidence>' \
  --managed-unit rehab-app.service \
  --expected-working-directory '<reviewed-release-directory>' \
  --application-port '<backend-port>' --application-port '<frontend-port>' \
  --maintenance-confirmed
```

The CLI checks the real managed unit is stopped with MainPID0, matches the
reviewed application path/start/stop entries, has no surviving recorded project
processes, and has no listener at each explicit application port. Its library
requires an independent maintenance guard and rechecks it before commit. A
boolean flag alone is insufficient. These checks **cannot establish the absence
of unknown external Mongo writers**: snapshot reads do not lock read-only source
users. The tool deliberately does not add temporary lock fields to accounts or
alter their change stream. Do not use it while independent write exclusion
cannot be established. It is not an online synchronization service.

The source snapshot contains complete legacy patient account documents and can
therefore contain secrets. It remains in a new private directory (0700/files
0600), is never uploaded or emitted as output, and does not replace a full DB
backup. No database restore function exists. The migration transaction writes
only the new clinical collection, explicit legacy account links and mode marker. Failure before commit rolls
those writes back. Before commit, an immutable fsynced journal marks the outcome
unknown; a crash or uncertain Mongo commit must be investigated without loading
an old backup. Success adds a separate immutable committed receipt. Subsequent
invocations never overwrite or refresh an existing canonical domain.

### Noop rerun verification and latecomer patients (post-cutover)

Re-running the apply command against an already canonical domain is not a
silent noop. It re-reads the current `role: "patient"` documents (the same
scope as the recorded checksum) and verifies two post-cutover hazards:

- **Baseline drift fails closed.** The fingerprint of the documents covered by
  the migration baseline — those with a `legacy_same_document` account link —
  is recomputed and compared with the `legacy_sha256` recorded in
  `patient_domain_state`. Any difference raises `LEGACY_BASELINE_DRIFTED`
  carrying both digests (baseline vs. current) and any detected latecomer IDs,
  and nothing is written. A legacy patient document was modified or deleted
  after cutover, so canonical and legacy data may have diverged; reconcile
  manually before any further migration attempt.
- **Latecomer patients are reported, never auto-migrated.** Legacy patient
  documents that appear after cutover (no `legacy_same_document` link, hence
  outside the recorded baseline) do not trigger the drift error; the rerun
  stays a verified noop and returns their `_id` values in `latecomer_ids`.
  They are not migrated automatically. **Open decision (pending business
  confirmation):** the concrete latecomer handling workflow — a per-patient
  reviewed migration command or a new audited batch tool — is deliberately not
  implemented in this library.

Baseline coverage is inferred from the `legacy_same_document` links written at
migration time. If such a link is removed manually later, its patient document
is conservatively reported as a latecomer rather than silently ignored.

## Domain switch (patient_access kernel dispatch)

The authorization kernel `app/core/patient_access.py` reads the durable
`patient_domain_state` singleton (`clinical-patients-v1`) through
`repository.domain_mode` and dispatches per mode:

- No state document (the current default) means the legacy users-backed domain:
  every kernel entry point (`load_patient_doc`, `ensure_patient_access`,
  `ensure_self_patient_access`, `assigned_patient_query`) keeps its existing
  legacy semantics, including the 503 ambiguity latch. Legacy-mode behavior is
  unchanged; business consumers still drive legacy queries directly.
- An explicit `{mode: "legacy", schema_version: <SCHEMA_VERSION>}` state
  document — the audited rollback carrier required by the cutover SOP — is the
  second legal legacy form. It dispatches to exactly the same legacy behavior
  as a missing document; the only difference is that the switch stays
  observable and auditable (record who/when/why on the document, aligned with
  the canonical state's audit style) and rollback never silently degrades by
  deleting the singleton. Under an explicit legacy state the canonical
  repository paths (`require_canonical`: `get`, `list_assigned`,
  `resolve_self`, `create_from_source`, ...) keep refusing with
  `PATIENT_DOMAIN_NOT_MIGRATED`, so a rollback never produces a half-migrated
  write path; re-running the migration tool also refuses
  (`PATIENT_DOMAIN_STATE_CONFLICT`) until the state is reconciled by a
  reviewed manual procedure.
- `mode == "canonical"` with the matching `schema_version` routes object loads
  and assignment checks to `ClinicalPatientRepository` (clinical_patients) and
  self resolution through `repo.resolve_self` (verified `patient_account_links`
  only; an account ID is never assumed to be a patient ID). Range dispatch goes
  through the kernel's async `assigned_scope_query`, whose canonical query is
  `repository.assigned_query` and therefore already contains `status=active`;
  medical-role validation errors are identical in both modes. The canonical
  branch never reads `users.is_active` as a patient status — clinical
  availability is the clinical document's `status` field.
- Anything else fails closed: an unrecognized state document variant
  (`migrating`, an explicit legacy state with a wrong/missing schema version,
  unknown mode) or a transport-level read failure raises `PatientAccessError`
  with HTTP 503 (`PATIENT_DOMAIN_STATE_UNAVAILABLE`) instead of falling back
  to legacy.

The three legal observations of the switch are therefore: no document (implicit
legacy), an explicit matching legacy document (audited rollback carrier), and a
matching canonical document.

In-memory test doubles that model the switch declare `patient_domain_state`
explicitly (see `tests/patient_identity_fake.legacy_domain_state`); a real Mongo
database always resolves the state collection, and ordinary fakes that omit it
stay legacy by definition.

## Integration still required

Switch clinical patient loading, physician lists, follow-up scope, clinical
records, devices, rehabilitation plans and statistics to one repository and
authorization policy together. Patient-account self access must resolve an
explicitly verified association through `resolve_self`; other manual link origins
require their own reviewed workflow. It must not infer a relation from matching IDs.
Communication participant IDs and audit actor IDs remain account identities.
Do not bulk-rewrite every `user_id` as a clinical patient ID.

`create_from_source(..., session=session)` participates in the caller Mongo
transaction for mode reads, index-presence probes and insert. MongoDB forbids
`listIndexes` inside transactions, so full index definitions are checked outside
the transaction and exact index names are required via in-transaction hints.
Deployment must exclude concurrent DDL. Missing/malformed indexes and index
operation errors fail closed. Callers can commit the
clinical entity with their external reference and audit atomically. This does
not create an account or assign care staff.

No production data or existing application path is changed merely by adding
these files. Deployment and business-route integration require their own review
and acceptance.
