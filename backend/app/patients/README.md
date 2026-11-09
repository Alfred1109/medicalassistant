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
