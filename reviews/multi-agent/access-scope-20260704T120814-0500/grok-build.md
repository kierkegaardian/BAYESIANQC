**Findings (strict implementation + rollout review of the supplied Enterprise Scope Access Production Plan)**

The plan is a reasonable high-level access-control slice. The current codebase has **zero** scope enforcement beyond role/permission checks: `get_current_user` + `UserContext` (role + `api_key_id` only), `list_*` queries accept caller filters, and every direct-object route (`/{id}`, `/{stream_id}/...`) does a raw PK or `stream_id` lookup with no grant evaluation. Idempotency, comments, imports, and kiosks are particularly exposed.

All analysis below is derived from actual code (models, security/rbac, main.py endpoints, ingestion/storage, backlog/comments/imports/kiosks services, migrations, frontend session, and tests). I did not execute the plan, run its commands/scripts, apply its migrations, or modify anything.

### P0 (production-blocking / direct bypasses)

1. **Idempotency receipt leakage (critical bypass)**
   - `process_ingestion` (ingestion.py:159) does `get_idempotent_response` by raw `idempotency_key` then returns the full prior `IngestionResult`/`QuarantineResult` (containing `qc`, `alert_created`, `stream_id` data, etc.).
   - `get_idempotent_response` + `store_receipt` (storage.py:353) are purely key-based. `IngestionReceipt` records no `stream_id`, no `api_key_id`, no scope.
   - A scoped key can replay an out-of-scope receipt if the key is reused or known. No scope check occurs before or after receipt return.
   - Plan correctly calls this out in "Main Risks" but the enforcement wave does not explicitly place a scope gate **before** the receipt fast-path or make receipts scope-aware.

2. **Direct-object reads and mutations have no scope enforcement**
   - `/streams/{stream_id}/configs`, `/priors`, `/chart` (main.py:849, 970, 1320): path `stream_id` is used directly in queries. `stream_chart` builds records/events/alerts without caller check.
   - `GET/PATCH /qc/backlog/{item_id}` (routers/qc_backlog.py:66): `get_backlog_item` is raw `id` fetch + `backlog_out`.
   - `PATCH /qc/records/{record_id}/resolution` (main.py:565): fetches record, takes its `stream_id` only for lock.
   - `PATCH /alerts/{alert_id}` (main.py:1054): raw `alert_id` fetch.
   - Import: `get_batch`, `batch_detail`, `patch_import_row`, `apply_ready_rows` (routers/imports.py + import_apply.py:100) operate on PKs/rows with no stream scope.
   - Kiosk: `get_kiosk` + `kiosk_layout_out` returns panels with raw `stream_id`s (routers/kiosks.py + services/kiosks.py).
   - Comments: `list_comments` filters by `qc_record_id`/`alert_id`/`run_id` with no stream derivation + scope check (routers/qc_comments.py + qc_comments.py:140).

3. **Mutation paths resolve context before (or without) scope**
   - `POST /qc/records` (and CSV variant) delegates to `process_ingestion` which resolves `StreamConfig`, backlog item, creates alerts, completes backlog, and stores receipts before any grant check could occur.
   - `POST /qc/backlog` and `POST /qc/comments` derive stream via target lookup (qc_comments.py `_target_*_context`) but never check the caller's grants.
   - `apply_ready_rows` blindly calls `process_ingestion` for every `READY_TO_APPLY` row.

4. **Alerts/comments derivation is a closed-failure risk**
   - Alerts carry `stream_id` but `list_alerts` (main.py:1039) and patch are global.
   - Comments can be created against a record/alert/run and later listed by ID without the original stream grant. `_target_*` lookups succeed for any existing target.

### P1 (edge cases + incomplete coverage in listed areas)

- **Backlog**: `list_backlog_items` and direct get have no scope filters. `assignment_group` + `stream_id` + `site`/`lab_bench` are all present on the model but only used as caller-supplied filters. Create can target any stream + group.
- **Imports (Wave 2)**: Batches can be mixed-scope. `apply_ready_rows` and row PATCH can retarget streams. `list_batches` / `batch_detail` expose everything (including rows whose parsed `stream_id` would be out-of-scope). Creator scoping for unparsed batches is absent. Plan correctly flags "mixed-scope rows" but the apply semantics ("apply only rows in scope; leave others") are not yet designed in the import services.
- **Kiosk leakage**: Saved layouts + panels expose `stream_id`s and labels. `ensure_stream_exists` only validates existence, not grants. Kiosk runtime paths (frontend + backend) will surface out-of-scope names unless panels are filtered at read time (backend must still be authoritative).
- **List filtering semantics**: `list_streams` (main.py:831) applies user `site`/`lab_bench` filters but does not intersect with grants. Supplying an out-of-scope filter currently just narrows results; after enforcement it must not let a scoped caller discover existence via enumeration or error differences.
- **CSV ingest and event paths**: `/qc/records/csv` and `/qc/events` call the same unguarded code.
- **Quarantine + resolution side effects**: Quarantine can be linked to backlog; resolution triggers re-eval on the record's stream. These are reachable via direct ID.

### P2 (migration/rollout safety + test gaps + creep)

- **Migration/rollout**:
  - Plan's flag (`BAYESIANQC_ENFORCE_ACCESS_GRANTS`, default 0) + "seed grants then flip" order is the right shape. No such flag or wiring exists today.
  - "admin with no grants = unrestricted" + "any grant present → restricted" is subtle and must be implemented exactly; a missing grant row for a prod service key after flip is a hard outage.
  - Null semantics ("any value") + union across multiple grant rows will be the source of query bugs in `apply_*_scope`.
  - Latest migration is `20260704_0005_import_ingestion`. Plan's `0006` naming is consistent but the upgrade must be strictly additive (no column changes to existing tables) and downgrade must be clean.
  - No mention of how `IngestionReceipt`, `AuditEntry`, or existing seed data (many `site`/`lab_bench`=null) interact with grants.
  - "Postgres copy rehearsal still reports clean schema parity" is good but must be expanded to cover grant table + indexes.

- **Test coverage gaps**:
  - Existing tests (test_ingestion, test_qc_backlog, test_imports, etc.) exercise role permissions and some idempotency, but **no** cross-scope negative cases, no seeded restricted keys, no direct-ID 404/403 denial tests, no import mixed-batch apply, and no kiosk panel scoping.
  - Idempotency tests do not cover "replay under different principal".
  - Frontend tests are thin; plan correctly de-emphasizes them but still needs contract + smoke coverage for `/me` scope shape and 403/404 handling.
  - No tests yet for the proposed `AccessGrant` indexes or effective dating.

- **Unnecessary scope creep / over-design for the slice**:
  - `principal_type` / `principal_id` / `group_id` / `effective_from` / `effective_until` + full dating on the first table is premature when the non-goal is "no OIDC". A minimal `api_key_id` + dimension columns + `active` table is sufficient and can be extended later.
  - A brand-new `app/services/access_scopes.py` with a rich `AccessScope` typed model + many helpers risks becoming a second RBAC layer. Start with focused query helpers called from existing services/endpoints.
  - "Internal/admin support for creating test grants" via script extension is acceptable; building even light grant CRUD in this slice would be creep.
  - Full `CurrentUserOut` expansion is fine, but exposing every dimension + `enforced` must be behind the flag for compatibility.

### Additional concrete issues

- **404 vs 403 policy** is stated well in the plan ("404 for direct-object reads where hiding existence is appropriate") but will be inconsistently applied without a single `require_*_access` helper used everywhere. Current code uses 404 liberally for "not found" (which can become an oracle).
- `stream_write_lock` is per-stream; fine, but scope checks must occur outside the lock where possible.
- Audit entries and quarantine rows embed stream data; they are not currently access-controlled.
- Frontend `session.ts` only knows role/permissions. All listed pages (Backlog, ChartView, Ingestion, Imports, QCCommentThread, Kiosk) currently trust backend lists or allow arbitrary selectors.
- Plan size guardrail ("<=300 LOC new/heavily modified") will be violated by the new service + main.py changes + tests; the exception must be recorded explicitly.

### Minimal changes that make the plan materially safer

1. **Idempotency hardening (mandatory before Wave 1 complete)**: Store `stream_id` (and optionally `api_key_id`) on `IngestionReceipt`. On replay lookup, after fetching the receipt, resolve the stream context and call the same scope check that would apply to a fresh ingest; on mismatch treat as cache miss (or return 403). Add this check even when the flag is off for test coverage.

2. **Simplify AccessGrant for slice 1**: Columns limited to `id, api_key_id, site, lab_bench, stream_id, assignment_group, active, created_at, created_by, reason`. Drop `principal_type/group/principal_id/effective_until`. Add a follow-up migration later. This shrinks the data model and helper surface dramatically.

3. **Single enforcement helper + early exit**: Add (small) `require_stream_access(session, user, stream_id, action)` that is called at the start of every Wave 1 endpoint **and** before idempotent replay, before backlog linkage, before alert creation, and before resolution. Use it for both direct objects and to intersect list query filters. Decide and document the 404/403 rule once.

4. **Import safety gate**: In `apply_ready_rows` and row PATCH, resolve the target stream (and any replacement) and require access **per row**. Leave out-of-scope rows untouched and surface a clear per-batch warning. Do not allow a scoped key to see row counts/details for streams outside its grants (return filtered or 404 the batch if nothing remains visible).

5. **Comments/alerts closed**: When listing or creating comments by `qc_record_id`/`alert_id`, derive the stream first, then require access (404 the specific target if out of scope). Same for alert patch. Never allow cross-stream comment enumeration via ID filters.

6. **Kiosk minimal**: On panel append/create, call stream access check for every `stream_id` in the payload. On read of a kiosk (for a non-admin), the backend may still return the layout but plan should explicitly state that kiosk consumers must tolerate 403/empty chart data for individual panels.

7. **Receipt + grant creator linkage**: Record `api_key_id` on grants and consider it on receipts for audit/debug. This also helps "who granted this" questions.

8. **Rollout checklist additions (make explicit in plan)**:
   - Before flip: run a verification script that enumerates active keys, prints their effective grants (or "unrestricted"), and confirms no prod service key will become accidentally restricted.
   - After flip: monitor not just 403/404 rates but also "scope-empty list" rates on `/streams` and backlog, plus any idempotency replay denials.
   - Explicit "current flag state" line in the deployment handoff.

9. **Test minimums (add to acceptance)**:
   - At least one test per Wave 1 surface (chart, backlog get/patch, ingest, alert, comment, stream config) using a restricted key vs. an out-of-scope object (assert 403 or 404).
   - Dedicated idempotency cross-scope replay test.
   - Import apply test with mixed-scope batch (in-scope rows applied, others left ready + warning emitted).
   - Migration test that creates the table + indexes and that downgrade removes only them.
   - Negative test: scoped key cannot use direct ID to discover existence of another stream's objects (exact status code per policy).

10. **Guardrails**: Add an explicit size/complexity exception note in the plan for the access_scopes module + changes to ingestion + main.py (or split enforcement into smaller focused modules from the start).

These changes are minimal deltas to the existing plan text. Implementing the simplified grant model + idempotency scope check on replay + one central `require_stream_access` used everywhere would eliminate the highest-risk bypasses before the flag is ever flipped to 1.

The plan's conservative principles ("backend is authoritative", "same result from list and direct", "fail closed on missing links") are sound. The gaps are in the concrete enforcement points and in under-estimating how many paths derive or bypass stream context (idempotency receipts, comment targets, import rows, kiosk panels, resolution side-effects). Address the P0 items above and the rollout becomes much safer.
