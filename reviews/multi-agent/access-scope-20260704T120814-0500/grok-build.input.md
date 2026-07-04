# Enterprise Scope Access Production Plan

Date: 2026-07-04

Status: draft for multi-agent review

Scope: implement API-key/user scope grants for `site`, `lab_bench`, `stream_id`, and
`assignment_group`; return effective scopes from `/me`; enforce them on the first
operational surfaces; default UI filters to the user's allowed scope; and add
negative tests for cross-scope access.

## Goal

Make BAYESIANQC safe for multi-site or multi-bench evaluation without waiting for
OIDC. The first production slice should keep the current API-key authentication
model, add explicit grant records, and enforce grants in backend queries and
mutations. OIDC/SAML group claims can later map into the same grant model.

This is an access-control foundation, not the full enterprise identity project.
The initial design must be conservative: unrestricted admin behavior stays
explicit, scoped service accounts cannot see or mutate outside their grants, and
unauthorized direct-object access fails even when a caller knows an id.

## Current Baseline

- `ApiKey` stores role, hash, description, and active status.
- `UserContext` exposes role, API-key id, permissions, and actor string.
- `/me` returns role, API-key id, and permissions only.
- `StreamConfig`, `Instrument`, `KioskLayout`, and `QCBacklogItem` already carry
  `site` and/or `lab_bench`.
- `QCBacklogItem` already carries `assignment_group`, `assigned_to`, and
  `stream_id`.
- `QCComment`, `AlertRecord`, `QCEvent`, `QCRecord`, and import rows carry
  `stream_id` or can derive it from a linked record/alert/run.
- Current backend filters are user-supplied, not user-scope-enforced.

## Non-Goals For This Slice

- No OIDC, MFA, or SAML implementation.
- No UI for grant administration beyond seed/script support unless it is needed
  for local testing.
- No new advanced charting or analytics.
- No retroactive data cleanup beyond migration defaults.
- No row-level encryption or tenant-isolated schemas.

## Design Principles

1. Backend enforcement is authoritative. UI filters are convenience only.
2. Missing grants mean unrestricted only for explicitly unrestricted roles/keys.
3. A scoped key must receive the same result from list and direct-object routes:
   out-of-scope data is hidden or rejected.
4. Mutations must check the target stream/backlog/import/comment context before
   state changes or audit writes.
5. Scope decisions must be easy to test without booting the frontend.
6. All scope-denial paths should avoid leaking whether an out-of-scope object
   exists unless the endpoint already necessarily exposes object identity.

## Data Model

Add a new `AccessGrant` table in `app/db_models.py`:

- `id`
- `principal_type`: `api_key`, `user`, `group`
- `api_key_id`: nullable FK-style reference to `ApiKey.id`
- `principal_id`: nullable string for future OIDC subject or local user id
- `group_id`: nullable string for future OIDC/SAML group claim
- `site`: nullable string
- `lab_bench`: nullable string
- `stream_id`: nullable string
- `assignment_group`: nullable string
- `active`: bool
- `effective_from`: datetime
- `effective_until`: nullable datetime
- `created_at`, `created_by`, `reason`

Use one row per grant. Null dimensions mean "any value" within that grant row.
Examples:

- API key can read only one stream: `api_key_id=7`, `stream_id="hba1c-main"`.
- API key can operate one bench: `api_key_id=8`, `site="Main Lab"`,
  `lab_bench="Chem Bench 1"`.
- Backlog group key can work a queue: `api_key_id=9`,
  `assignment_group="night-shift"`.

Add indexes for:

- `(principal_type, api_key_id, active)`
- `(principal_type, principal_id, active)`
- `(principal_type, group_id, active)`
- `(site, lab_bench)`
- `(stream_id)`
- `(assignment_group)`

Do not add a JSON grants field to `ApiKey`. A normalized table makes effective
dating, audit, and future group mapping tractable.

## Scope Semantics

Effective scope is the union of active grants for the authenticated principal.

Unrestricted behavior:

- `admin` with no grants remains unrestricted for local/demo continuity.
- Any role with at least one grant is restricted to the grant union.
- Non-admin roles with no grants initially remain unrestricted behind a feature
  flag defaulting to compatibility mode in local dev. Production should flip the
  flag after seeded grants exist.

Feature flag:

- `BAYESIANQC_ENFORCE_ACCESS_GRANTS=0|1`
- Default: `0` for compatibility in existing tests and demos.
- Production plan: deploy migration and grant seeding first, then enable `1`.

This avoids breaking the local demo while still letting tests prove the enforced
path.

## Backend Modules

Create `app/services/access_scopes.py`:

- `AccessScope` typed model with normalized allowed sets and `unrestricted`.
- `effective_scope(session, user)` loads active grant rows.
- `can_access_stream(session, user, stream_id, at_time=None)` validates a stream.
- `apply_stream_scope(query, model, scope)` applies stream/site/bench filters.
- `apply_backlog_scope(query, scope)` applies stream/site/bench/group filters.
- `require_stream_access(session, user, stream_id, action)` raises 404 or 403.
- `require_backlog_access(session, user, item, action)` checks item context.
- `filter_scope_options(scope)` returns `/me` payload values for UI defaults.

Keep policy helpers out of `app/main.py`. Endpoint code should call one helper
at the boundary, then delegate to existing services.

## API Changes

Extend `CurrentUserOut`:

- `effective_scope.unrestricted`
- `effective_scope.sites`
- `effective_scope.lab_benches`
- `effective_scope.stream_ids`
- `effective_scope.assignment_groups`
- `effective_scope.enforced`

Add internal/admin support for creating test grants:

- Prefer `scripts/create_api_key.py --grant-site ... --grant-bench ...`
  extensions for this slice.
- Defer full grant-management API/UI unless the implementation becomes awkward
  without it.

## Enforcement Wave 1

Implement these routes first:

- `GET /me`: include effective scope.
- `GET /streams`: restrict returned stream configs by scope. If the user passes
  `site` or `lab_bench` outside scope, return an empty list.
- `GET /streams/{stream_id}/configs`: require stream access.
- `GET /streams/{stream_id}/priors`: require stream access.
- `GET /streams/{stream_id}/chart`: require stream access before querying
  records, events, and alerts.
- `POST /qc/records`: require stream access after resolving the stream config,
  before accepted insert, quarantine, backlog linkage, or idempotent replay.
- `PATCH /qc/records/{record_id}/resolution`: require access to the record's
  stream before exclusion/reinstatement.
- `GET /qc/backlog`: restrict by stream/site/bench/assignment group.
- `GET/PATCH /qc/backlog/{id}`: require backlog item access.
- `POST /qc/backlog`: require access to the stream and requested group/bench.
- `GET /alerts`: restrict by alert stream.
- `PATCH /alerts/{id}`: require alert stream access.
- `GET/POST /qc/comments`: require access to the derived stream context.

Use 404 for direct-object reads where hiding existence is appropriate. Use 403
for mutation attempts where the caller has already supplied a valid in-scope
parent but requests an out-of-scope child.

## Enforcement Wave 2

Apply the same policy to import surfaces after Wave 1 is green:

- `GET /qc/imports`: restrict batches by rows whose streams are in scope and by
  creator when no stream has been parsed yet.
- `GET /qc/imports/{batch_id}`: show only accessible rows/artifacts or reject
  if no accessible content remains.
- `POST /qc/imports`: allow upload, but parsed row review and auto-apply must
  apply stream scope before rows become `ready_to_apply`.
- `PATCH /qc/imports/rows/{row_id}`: require access to the row's target stream,
  target backlog item, and any replacement stream.
- `POST /qc/imports/{batch_id}/apply`: apply only rows in scope; leave
  out-of-scope ready rows untouched with a clear batch warning.

If import scoping becomes too large, cut Wave 2 into a follow-up implementation
slice rather than weakening Wave 1.

## Frontend Plan

Update generated schema after backend changes, then extend `frontend/src/api/session.ts`:

- expose `effectiveScope`
- helper functions:
  - `scopeDefaultSite()`
  - `scopeDefaultBench()`
  - `scopeDefaultAssignmentGroup()`
  - `isScopeRestricted()`

Apply UI defaults:

- `Backlog.vue`: default group/bench filters when restricted; hide "All" as a
  global claim and label it as scoped results.
- `ChartView.vue`: load scoped streams only; if one stream is available, select
  it automatically.
- `Ingestion.vue`: stream selector only shows allowed streams; backlog handoff
  handles 404/403 with a scoped-access message.
- `Imports.vue`: show scoped batch/row counts and avoid implying hidden rows are
  errors.
- `QCCommentThread.vue`: render 403/404 as unavailable for this user's scope.
- `Kiosk` routes: rely on backend stream checks; saved kiosk layouts should not
  leak out-of-scope stream names.

Do not implement client-only hiding as security.

## Migration And Rollout

1. Add migration `20260704_0006_access_grants`.
2. Create tables and indexes only. Do not modify existing records.
3. Extend `scripts/create_api_key.py` with optional grant creation.
4. Add a demo seed path only if needed for local smoke testing.
5. Keep `BAYESIANQC_ENFORCE_ACCESS_GRANTS=0` for first deploy.
6. Seed grants for intended service keys.
7. Run scope verification against staging/demo data.
8. Flip `BAYESIANQC_ENFORCE_ACCESS_GRANTS=1`.
9. Watch audit, 403/404 rates, import apply failures, and user reports.

Rollback:

- Disable `BAYESIANQC_ENFORCE_ACCESS_GRANTS`.
- No destructive schema rollback required for emergency recovery.
- If code rollback is needed, leave `accessgrant` table in place until a later
  reviewed migration removes it.

## Test Plan

Backend focused tests:

- `/me` returns unrestricted scope for local admin in compatibility mode.
- scoped key sees only granted stream from `/streams`.
- scoped key gets 404 or 403 for out-of-scope `/streams/{id}/chart`.
- scoped key cannot ingest to an out-of-scope stream.
- scoped key cannot link an out-of-scope backlog item.
- scoped key sees only matching backlog `assignment_group`.
- scoped key cannot read/update out-of-scope backlog item by id.
- scoped key sees only alerts/comments for allowed streams.
- idempotent replay does not leak an out-of-scope prior response.
- import row update/apply cannot retarget to out-of-scope streams.

Migration tests:

- upgrade creates `accessgrant` table and indexes.
- downgrade removes only the new table/indexes.
- Postgres copy rehearsal still reports clean schema parity.

Frontend tests/checks:

- `npm --prefix frontend run gen:api`.
- `npm --prefix frontend run check`.
- add focused component or static tests only where existing frontend test harness
  supports them; otherwise rely on TypeScript plus live smoke.

Full gate:

- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m ruff check app tests scripts`
- `.venv/bin/pyright`
- `npm --prefix frontend run gen:api`
- `npm --prefix frontend run check`
- `git diff --check`

## Acceptance Criteria

- A scoped API key can only list, chart, ingest, comment, and work backlog items
  inside its grants.
- Direct-object route attempts outside scope are denied.
- `/me` exposes effective scope without requiring frontend inference.
- Existing local admin demo behavior remains intact until enforcement is enabled.
- Tests prove at least chart, backlog, and ingest cross-scope denial.
- Implementation keeps new/heavily-modified files under repo size guardrails or
  records a clear exception before commit.

## Main Risks

- Out-of-scope idempotency receipts could replay old accepted responses unless
  checked against current scope before return.
- Comments and alerts derive access through linked records; missing links must
  fail closed.
- Import batches may contain mixed-scope rows; apply semantics must be explicit.
- Admin compatibility defaults could be mistaken for production posture. The
  deployment handoff must call out the enforcement flag state.
- Kiosk routes can expose stream labels if saved layouts are not filtered.

## Recommended Implementation Order

1. Migration, models, and `CurrentUserOut` types.
2. Access-scope service helpers with unit tests.
3. `/me`, `/streams`, chart, and record ingestion enforcement.
4. Backlog enforcement.
5. Alerts and comments enforcement.
6. Import enforcement or explicit follow-up split if too large.
7. Frontend scope defaults.
8. Full validation and live demo smoke.
