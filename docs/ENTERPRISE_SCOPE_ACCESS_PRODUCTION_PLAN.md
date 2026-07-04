# Enterprise Scope Access Production Plan

Date: 2026-07-04

Status: reviewed draft; incorporates AGY, Grok, and Codex explorer feedback.
Gemini CLI review was attempted but failed because the installed Gemini client is
no longer supported for this account tier.

Scope: add API-key scope grants for `site`, `lab_bench`, `stream_id`, and
`assignment_group`; return effective scope from `/me`; enforce scope on the
first operational surfaces; default UI filters to that scope; and test
cross-scope denial for chart, backlog, ingest, alert, comment, audit, kiosk,
and import paths.

## Goal

Make BAYESIANQC safe for multi-site or multi-bench evaluation while preserving
the current API-key authentication model. This slice creates the authorization
resource model that OIDC/SAML users and groups can map into later. It does not
ship OIDC, MFA, grant-management UI, or advanced charting.

Backend enforcement is authoritative. UI filtering is only an ergonomic default.

## Current Baseline

- `ApiKey` stores role, hash, description, and active status.
- `UserContext` carries role, API-key id, permissions, and actor string.
- `/me` returns role, API-key id, and permissions only.
- `StreamConfig`, `Instrument`, `KioskLayout`, `QCBacklogItem`, alerts,
  comments, QC records, events, and import rows carry or can derive `stream_id`
  and often `site`, `lab_bench`, or `assignment_group`.
- Current backend filters are caller-supplied and are not access-control checks.
- `IngestionReceipt` is globally keyed by idempotency key and currently has no
  stream or principal binding.

## Non-Goals

- No OIDC/SAML/MFA.
- No full grant-management UI.
- No row-level encryption or tenant-specific schemas.
- No statistical charting expansion.
- No broad cleanup of `app/main.py` outside the touched access boundaries.

## Grant Model

Add `AccessGrant` in `app/db_models.py` for this first slice only:

- `id`
- `api_key_id`
- `site`
- `lab_bench`
- `stream_id`
- `assignment_group`
- `active`
- `created_at`
- `created_by`
- `reason`

Use one row per grant. Null dimensions mean "any value" inside that grant row.
This is intentionally API-key scoped. Add `principal_id`, `group_id`, effective
dating, and OIDC/SAML group mapping in a later migration after the service-key
path is proven.

Indexes:

- `(api_key_id, active)`
- `(stream_id)`
- `(site, lab_bench)`
- `(assignment_group)`

Extend `IngestionReceipt` with at least `stream_id` and `api_key_id` so replay
can be checked against the caller's current scope. If a receipt is quarantined
before stream resolution, store the best available `stream_id` from the payload.

## Enforcement Flag

Add `BAYESIANQC_ENFORCE_ACCESS_GRANTS=0|1`.

When the flag is `0`, all users get an unrestricted effective scope and grant
rows are ignored for enforcement. This is a global bypass for safe seeding and
local demo continuity.

When the flag is `1`:

- `admin` keys with no grants remain unrestricted only if explicitly allowed by
  a small `break_glass_unrestricted_admin` helper.
- non-admin keys with no grants have an empty scope.
- keys with grants are restricted to the union of active grants.

Rollout must seed and verify grants while the flag is `0`, then flip the flag
once, atomically, after verification.

## Scope Semantics

A request is in scope when at least one active grant matches the target context:

- `stream_id` grant matches that exact stream.
- `site` and/or `lab_bench` grant matches the target stream/backlog/kiosk site
  and bench.
- `assignment_group` grant matches backlog assignment group.
- null dimensions in a grant row do not constrain that dimension.

For list routes, backend query predicates must intersect caller filters with the
effective scope. For direct-object read routes, return 404 when the target is
out of scope. For mutations on an already visible object, return 403 when the
target state would move it out of scope.

## Backend Boundaries

Create `app/services/access_scopes.py`:

- `AccessScope`: `unrestricted`, `enforced`, allowed site/bench/stream/group sets.
- `effective_scope(session, user)`.
- `stream_scope_predicate(scope, model)`.
- `backlog_scope_predicate(scope)`.
- `require_stream_access(session, user, stream_id, *, hide=True)`.
- `require_record_access(session, user, record_id, *, hide=True)`.
- `require_alert_access(session, user, alert_id, *, hide=True)`.
- `require_comment_target_access(session, user, target_context, *, hide=True)`.
- `require_backlog_access(session, user, item, target_update=None)`.
- `scope_summary_for_me(scope)`.

Keep role permissions in `app/rbac.py`; keep resource grants in
`app/services/access_scopes.py`. Services that can be called from multiple
routes, especially ingestion and imports, must enforce scope internally rather
than relying only on route dependencies.

If grant models are split out of `app/db_models.py`, update Alembic metadata
imports and `tests/conftest.py` cleanup. The first implementation should keep
the table in `app/db_models.py` to avoid that extra moving part.

## API Changes

Extend `CurrentUserOut`:

- `effective_scope.unrestricted`
- `effective_scope.enforced`
- `effective_scope.sites`
- `effective_scope.lab_benches`
- `effective_scope.stream_ids`
- `effective_scope.assignment_groups`

Extend `scripts/create_api_key.py` with optional grant arguments:

- `--grant-site`
- `--grant-bench`
- `--grant-stream`
- `--grant-group`
- `--grant-reason`

Defer grant CRUD API unless implementation cannot be tested without it.

## Wave 1 Enforcement

Implement and test these before import scoping:

- `/me`: return effective scope.
- `/streams`: restrict by effective scope, not just caller filters.
- `/streams/{stream_id}/configs` and `/streams/{stream_id}/priors`: require
  stream access.
- `/streams/{stream_id}/chart`: require stream access before querying records,
  events, alerts, and lot segments.
- `/qc/records`: require stream access before idempotent replay, accepted insert,
  quarantine, backlog linkage, alert creation, or receipt storage.
- `/qc/records/csv`: each row must use the same checked ingestion path.
- `PATCH /qc/records/{record_id}/resolution`: require record stream access
  before exclusion/reinstatement and reprocessing.
- `/qc/backlog`: restrict list by stream/site/bench/group; direct get/update
  must check current item access and target-state access for `lab_bench`,
  `assignment_group`, and assignee/group changes.
- `/alerts`: restrict list by alert stream; patch requires alert stream access.
- `/qc/comments`: derive record/alert/run stream context first; list/create must
  fail closed and avoid leaking target existence.
- `/audit`: restrict audit list by visible entities where possible; otherwise
  scoped non-admin keys should not receive global audit rows.
- `/kiosks` and `/kiosks/{slug}`: saved layouts containing out-of-scope panels
  must not leak stream ids. For the first slice, reject the saved layout for a
  restricted caller if any active panel is out of scope.

Also consider snapshotting `site` and `lab_bench` onto `QCRecord`, `AlertRecord`,
`QCComment`, quarantine, and import rows in a later follow-up. For this slice,
stream-id checks are mandatory and site/bench checks may resolve through the
effective stream config.

## Wave 2 Import Enforcement

Do this after Wave 1 is green, or split it into a follow-up if the diff grows.

- `GET /qc/imports`: scoped users see only batches with visible content or their
  own unparsed batches.
- `GET /qc/imports/{batch_id}`: reject if no visible rows remain; do not leak raw
  archive/source paths for out-of-scope content.
- `POST /qc/imports`: upload may be accepted, but parsed rows targeting
  out-of-scope streams must become terminal `failed/ignored` rows with an
  "out of scope" reason, not invisible ready rows.
- `PATCH /qc/imports/rows/{row_id}`: require access to the current row stream,
  replacement stream, and replacement backlog item.
- `POST /qc/imports/{batch_id}/apply`: apply only in-scope rows; out-of-scope
  rows must already be terminal or clearly blocked, not silently left dangling.

## Frontend Plan

After backend schema changes, run `npm --prefix frontend run gen:api` and update
`frontend/src/api/session.ts` with small typed helpers:

- `effectiveScope`
- `isScopeRestricted`
- `scopeLabel`
- `buildScopeQuery`
- `scopeMatchesStream`

Touch points:

- `AppLayout.vue`: show concise scope label next to role.
- `Backlog.vue`: default to assignment group, then bench/site; label "All" as
  all visible in current scope.
- `ChartView.vue`: select the first scoped stream; reject forced out-of-scope
  stream URLs with a scoped-access message.
- `Ingestion.vue`: clear stale recent stream/backlog when it is no longer in
  scope.
- `Imports.vue`: show scoped batch/row counts and avoid implying hidden rows are
  parser errors.
- `QCCommentThread.vue`, `Alerts.vue`, `Audit.vue`, `Quarantine.vue`: render
  403/404 as unavailable for this user's scope.
- `ChartKiosk.vue`, `KioskBuilder.vue`, `DatastreamSetup.vue`: default saved
  kiosk/site/bench values from effective scope; do not rewrite static demo
  kiosks client-side.

The UI must never be the only enforcement layer.

## Rollout

1. Add migration `20260704_0006_access_grants`.
2. Add access helpers, `/me` scope output, idempotency receipt hardening, and
   Wave 1 enforcement.
3. Keep `BAYESIANQC_ENFORCE_ACCESS_GRANTS=0`.
4. Seed intended service-key grants.
5. Run a verification script that prints each active key's effective scope and
   flags keys that would become empty-scope after cutover.
6. Run full validation.
7. Flip `BAYESIANQC_ENFORCE_ACCESS_GRANTS=1`.
8. Monitor 403/404 rates, empty `/streams` results, backlog empty-list rates,
   import out-of-scope row counts, and idempotency replay denials.
9. Record the flag state in the deployment handoff.

Rollback:

- Set `BAYESIANQC_ENFORCE_ACCESS_GRANTS=0`.
- Leave the additive table/columns in place until a reviewed cleanup migration.

## Test Plan

Backend:

- `/me` unrestricted with flag `0`; enforced restricted scope with flag `1`.
- flag `0` remains unrestricted even when grant rows exist.
- scoped key sees only granted streams from `/streams`.
- scoped key gets 404/403 for out-of-scope chart/config/prior direct routes.
- scoped key cannot ingest or CSV-ingest to an out-of-scope stream.
- idempotency replay cannot leak another key's or out-of-scope response.
- scoped key cannot link or update an out-of-scope backlog item.
- scoped key cannot patch backlog target state to an out-of-scope group/bench.
- scoped key sees only in-scope alerts, comments, and audit rows.
- comment target lookups for out-of-scope record/alert/run fail closed.
- saved kiosk with any out-of-scope panel is rejected for restricted callers.
- import mixed-scope rows become terminal out-of-scope failures or are blocked
  clearly; apply does not leave hidden ready rows dangling.

Migration:

- upgrade creates `accessgrant`, indexes, and receipt scope columns.
- downgrade removes only new artifacts.
- Postgres migration/copy rehearsal remains green.

Frontend and full gate:

- `npm --prefix frontend run gen:api`
- `npm --prefix frontend run check`
- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m ruff check app tests scripts`
- `.venv/bin/pyright`
- `git diff --check`
- Live smoke with one restricted key on `/backlog`, `/ingest`, `/charts`,
  `/kiosk/refinery`, `/imports`, `/alerts`, and chart comments.

## Acceptance Criteria

- Scoped API keys cannot list, chart, ingest, comment, audit, update alerts, or
  work backlog outside grants.
- Direct-object attempts outside scope are denied without useful existence leaks.
- `/me` exposes effective scope for frontend defaults.
- Idempotency receipts are scope-safe.
- Existing local demo behavior remains intact while the flag is `0`.
- The implementation can be enabled atomically after grants are seeded.
- Tests prove cross-scope denial for chart, backlog, ingest, idempotency, alert,
  comment, audit, kiosk, and import paths.
