# BayesianQC Review Report (Codex)

Date: 2026-02-13

Scope
- QC math (Bayesian + Westgard)
- Usability and featureset (Vue UI)
- Code quality, best practices, and bugs (FastAPI + SQLModel)
- Architecture concern: API as “true middleware” and single CRUD boundary to the database

Verification
- Backend tests: `/.venv/bin/python -m pytest -q` (9 passed).
- Frontend typecheck: not rerun in this pass (no TS changes were required for the backend scalability work).
- Python typecheck: `/.venv/bin/pyright` is currently broken due to a stale shebang pointing at `/home/user/BAYESIANQC/...` (repo moved to `/home/user/projects/BAYESIANQC`). See `/.venv/bin/pyright`.

## Executive Summary
- The **frontend does not talk to SQLite directly**; it uses HTTP (`fetch`) against the FastAPI API (`frontend/src/api/client.ts`). That part of the “middleware API” goal is already true.
- The backend is **not yet a clean middleware layer internally**: DB writes happen mid-request and in lower-level helpers, which makes ingestion **non-atomic** and makes CSV “rollback on row error” **incorrect** in the presence of `commit()` calls.
- QC math is directionally correct: the Bayesian engine is a conjugate Normal–Inverse-Gamma update with a Student-t predictive distribution, and the frequentist rules approximate a standard Westgard subset. The main risks are **policy/consistency gaps**, **edge cases** (sigma=0), and **performance scaling** (chart endpoint).
- Chart scalability has been materially improved by **persisting per-record evaluations** (`QCRecord.signals`, `QCRecord.bayesian_risk`, `QCRecord.disposition`) and making chart retrieval a mostly-read path. The remaining scalability risk is **full-stream reprocessing** on out-of-order ingestion / retroactive config changes.

## Top Findings (Prioritized)

### P0: PosteriorState Updates Are Not Concurrency-Safe (Lost Updates)
Impact
- Concurrent ingestions for the same `stream_id` can overwrite each other’s `PosteriorState` update (classic read-modify-write race), permanently corrupting the Bayesian state (and any downstream risk scoring that depends on it).

Evidence
- `infer_risk()` reads then mutates `PosteriorState` with no locking/optimistic check: `/home/user/projects/BAYESIANQC/app/bayesian.py:586-643`.

Recommendation
- Make ingestion a single transaction and enforce mutual exclusion per stream during posterior updates.
- If/when you move to Postgres: use `SELECT ... FOR UPDATE` (SQLAlchemy `with_for_update()`) on the `PosteriorState` row inside the ingestion transaction.
- If staying on SQLite: `FOR UPDATE` isn’t available; use an optimistic concurrency strategy (e.g., update with a `WHERE updated_at = <old>` guard and rebuild+retry on conflict) or a lock table / `BEGIN IMMEDIATE` strategy.

Verification
- Add a test that fires N concurrent ingestions for one stream and asserts `PosteriorState.n_obs` increments by N and matches a recomputed posterior from the QCRecord history.

### P0: Ingestion Atomicity (Improved for `/qc/records`, Still a Risk Elsewhere)
Impact
- Previously, ingestion could partially write (record inserted + committed) and then fail later, leaving missing/incorrect downstream artifacts (audit entry, alert, posterior state).
- CSV ingestion attempted per-row rollback, but helper-level `commit()` calls meant rollback could not undo already-committed work.

Status
- Improved in this workspace for `/qc/records` and `/qc/records/csv`:
  - `process_ingestion()` now performs **one commit at the end** and explicitly `rollback()`s on exceptions to keep the session usable for CSV loops.
  - Ingestion calls Bayesian and storage helpers with `commit=False` so ingestion is not fractured by helper commits.

Evidence
- Ingestion now has a single commit boundary: `/home/user/projects/BAYESIANQC/app/main.py` (`process_ingestion`).
- Helpers support `commit=False` for composition: `/home/user/projects/BAYESIANQC/app/storage.py` (`record_audit`, `create_alert`, `store_receipt`) and `/home/user/projects/BAYESIANQC/app/bayesian.py` (`infer_risk`, `rebuild_posterior_state`).

Recommendation
- Continue the “true middleware” refactor by moving all request workflows into `app/services/*` and making repo/helpers `commit()`-free by default.
- If you want structured transaction scopes (`with session.begin():`) for service code, consider:
  - ensuring auth uses a separate session, or
  - using nested transactions (savepoints) for per-row CSV handling.

### P1: Chart Endpoint Performance (Addressed via Persisted Evaluations), But Reprocessing Can Be Expensive
Status
- Addressed in this workspace by persisting evaluations on `QCRecord` and switching `/streams/{stream_id}/chart` to read them.

What changed
- Added persisted fields on `QCRecord`: `/home/user/projects/BAYESIANQC/app/db_models.py`.
  - `signals` (JSON list of frequentist signals)
  - `bayesian_risk` (JSON snapshot of Bayesian risk/intervals)
  - `disposition` (string enum value)
- Added a batch reprocessor: `/home/user/projects/BAYESIANQC/app/evaluations.py` (also updates `PosteriorState`).
- On mutation endpoints that can invalidate cached evaluations, the API now triggers a reprocess:
  - record resolution (`include_in_stats` flips)
  - retroactive stream config versions
  - retroactive prior versions
  - out-of-order ingestion (record timestamp before existing history)
- Added a backfill utility script for existing DBs: `/home/user/projects/BAYESIANQC/scripts/reprocess_stream_evaluations.py`.
  - Example: `/.venv/bin/python scripts/reprocess_stream_evaluations.py --stream-id hba1c-arch`

Residual risk (Gemini also flagged this)
- Out-of-order ingestion currently triggers a **full-stream** reprocess synchronously, which can be slow for large streams and can block other writes on SQLite.
- This is the correct *semantic* fix (later points must be recomputed), but you likely want to evolve this into:
  - incremental reprocessing (recompute from the inserted timestamp forward), and/or
  - async/background reprocessing with a “pending recalculation” UI state.

### P1: Alert Filtering In Chart Uses `created_at` Instead of QC Timestamp (Fixed)
Impact
- Chart `start/end` filters can drop alerts that correspond to QC points in the requested time window, because alert creation time may not equal QC record time.

Evidence
- Previously in `/home/user/projects/BAYESIANQC/app/main.py`, alert filters used `AlertRecord.created_at` even though charts map alerts to `QCRecord.timestamp`.

Status
- Fixed in this workspace: alerts are filtered by joined `QCRecord.timestamp` when available, with a fallback to `AlertRecord.created_at` for alerts with no linked QC record: `/home/user/projects/BAYESIANQC/app/main.py`.

### P1: Frequentist Rules Can Divide By Zero If Baseline Sigma Collapses
Impact
- If baseline stats are computed from a baseline period with zero variance (or too little data), `sigma` can be 0 and `z_score = ... / sigma` will raise.

Evidence
- Baseline sample SD computed without guarding for degenerate variance: `/home/user/projects/BAYESIANQC/app/storage.py:249-266`.
- Division by `sigma` unguarded: `/home/user/projects/BAYESIANQC/app/frequentist.py:21-36`.

Recommendation
- If `sigma <= 0`, fail fast with a clear configuration error (preferred for QA/validation), or fall back to configured `StreamConfig.sigma` only if you explicitly choose that policy.
- Add a test for the “baseline sigma is 0” edge case.

### P2: “Baseline” Is Implemented Differently Between Frequentist and Bayesian
Impact
- Frequentist evaluation can use a baseline period (`baseline_start/baseline_end`) and derive mean/sigma from DB history.
- Bayesian risk uses `StreamConfig.target_value` and `StreamConfig.sigma` for action/warn bounds (fixed limits), ignoring baseline periods.
- If you use baseline periods, frequentist and Bayesian can disagree on what “±2/±3 SD” means.

Evidence
- Frequentist baseline stats derive mean/sigma from DB: `/home/user/projects/BAYESIANQC/app/storage.py:249-266`.
- Bayesian bounds use configured target/sigma: `/home/user/projects/BAYESIANQC/app/bayesian.py:224-290` (bounds at `:245-248`).

Recommendation
- Decide the invariant:
  - Option A: `StreamConfig.target_value/sigma` are always the validated limits; baseline periods are only used to *help compute those values*, not at runtime.
  - Option B: Baseline period is a first-class runtime concept and both Bayesian and frequentist derive bounds from it consistently (and the UI must show which baseline was used).
- Document it and enforce it in API validation.

### P2: API Key Storage Is A Fast Unsalted Hash
Impact
- If the `ApiKey.key_hash` values leak, SHA-256 is cheap to brute force relative to a password-hash/KDF approach.

Evidence
- Hashing is direct SHA-256: `/home/user/projects/BAYESIANQC/app/rbac.py:33-43` and `/home/user/projects/BAYESIANQC/scripts/create_api_key.py`.

Recommendation
- Use a slow KDF (argon2/bcrypt/scrypt) and store per-key salt.
- Add minimal key management endpoints or rotation strategy if this leaves “prototype” land.

### P2: “R-4s” Rule Implementation Does Not Match Classic Westgard Semantics
Impact
- If you expect classic Westgard multirule behavior, the current implementation of `R-4s` (two consecutive points in the same stream) can miss “within-run between-levels” random error detection and can also produce confusing signals under a stream-per-level model.

Evidence
- Current R-4s compares only against the previous record in the same stream: `/home/user/projects/BAYESIANQC/app/frequentist.py:48-55`.
- Stream identity includes `qc_level` (and the UI/API submit one record at a time), so there is no notion of a “run” containing multiple levels to compare.

Recommendation
- Either rename the rule to match what it actually does (two-point opposite-side rule within a single stream), or extend ingestion to accept a batch/run containing multiple QC levels and evaluate within-run rules across levels (optionally configurable per analyte/instrument).

### P2: SQLite Migrations Should Be Explicit and Versioned (Addressed)
Status
- Fixed in this workspace: runtime `_ensure_sqlite_columns()` was replaced with an explicit, versioned SQLite migration runner using `PRAGMA user_version`.
- The previous unconditional default backfills for Bayesian threshold fields were removed; NULL values now remain NULL and the app’s existing fallbacks apply.

Evidence
- `init_db()` runs migrations: `/home/user/projects/BAYESIANQC/app/db.py`.
- Versioned migration steps live in: `/home/user/projects/BAYESIANQC/app/migrations.py`.

Recommendation
- Keep this lightweight migration runner for the SQLite prototype, and switch to Alembic (or equivalent) when you move to Postgres for production-like deployments.

## QC Math Review

### Bayesian Engine (Normal–Inverse-Gamma + Student-t Predictive)
What’s correct / strong
- Posterior update is the standard NIG one-observation update: `/home/user/projects/BAYESIANQC/app/bayesian.py:152-163`.
- Predictive distribution uses a Student-t with `df = 2*alpha`, and scale consistent with NIG predictive: `/home/user/projects/BAYESIANQC/app/bayesian.py:224-290`.
- Exceedance probability is computed as `1 - P(lower <= X <= upper)` for warning/action bounds, which is the right shape for a “risk of violating limits” score: `/home/user/projects/BAYESIANQC/app/bayesian.py:242-265`.
- Warn/hold streak policy is centralized and supports an N-consecutive policy: `/home/user/projects/BAYESIANQC/app/bayesian.py:183-221`.

Main math-policy gaps
- “Outside limits” is derived only from action-limit exceedance probability, while “outside warning” is separately tracked. That’s fine, but you should be explicit that `risk_score` is strictly `P(outside action)` in percent.
- Interval confidence level is hard-coded at 95% (`_DEFAULT_INTERVAL_LEVEL = 0.95`), which is likely to become a validation requirement later: `/home/user/projects/BAYESIANQC/app/bayesian.py:14-17`.

### Frequentist Westgard Rules
What’s correct / strong
- Core rule patterns are recognizable and implemented over a recent history window: `/home/user/projects/BAYESIANQC/app/frequentist.py:14-69`.
- The rules are driven by a configurable ruleset (`rule_set` JSON): `/home/user/projects/BAYESIANQC/app/frequentist.py:24-25`.

Main math-policy gaps
- Severity classification is partially a policy decision. Right now `2-2s` is `WARN`, not `ACTION`, which will affect dispositions (`monitor` vs `reject`): `/home/user/projects/BAYESIANQC/app/frequentist.py:38-46` and `/home/user/projects/BAYESIANQC/app/main.py:256-293` (disposition).

## Middleware/API Architecture Review (DB Only Hit By API)

### Current State
- Web UI uses the API client and does not access SQLite directly: `/home/user/projects/BAYESIANQC/frontend/src/api/client.ts`.
- Within the backend, DB access is spread across:
  - Endpoints in `/home/user/projects/BAYESIANQC/app/main.py`
  - “Storage” helpers in `/home/user/projects/BAYESIANQC/app/storage.py`
  - Inference/state code in `/home/user/projects/BAYESIANQC/app/bayesian.py`
  - Frequentist evaluation in `/home/user/projects/BAYESIANQC/app/frequentist.py`
  - Batch evaluation/backfill in `/home/user/projects/BAYESIANQC/app/evaluations.py`

### Why This Still Feels Like “Not True Middleware”
- There’s no single clear “service” layer that owns the unit-of-work and transaction boundaries.
- Math modules perform persistence (`commit()`), which ties business logic to DB semantics and makes it harder to evolve.

### Recommended Refactor Shape (Minimal, High Leverage)
- `app/services/ingestion.py`
  - Owns: ingest record, evaluate frequentist, infer Bayesian, create audit + alert, store receipt.
  - Owns: transaction boundary (commit once, rollback fully).
- `app/repos/*.py` (or expand `app/storage.py`)
  - Owns: CRUD queries for each table and any joins.
- `app/math/bayes.py` and `app/math/westgard.py`
  - Pure functions only (no SQLModel Session).

This structure keeps the API contract stable while allowing DB query refactors without touching frontend code.

For the detailed module split and a safe SQLite -> Postgres plan, see:
- `/home/user/projects/BAYESIANQC/docs/ARCHITECTURE.md`

## Usability/Featureset Review (UI)

Strengths
- Clear “console” navigation and contextual help (`HelpButton`).
- Charts are genuinely useful: show LJ bands, posterior mean/intervals, risk trends, and allow click-to-resolve/reinstate points: `/home/user/projects/BAYESIANQC/frontend/src/pages/ChartView.vue`.

Major gaps for real lab usability
- No UI to manage Bayesian priors (API exists, UI doesn’t expose it).
- Streams UI can create a stream and view versions, but there’s no “create new version” or “edit active config” workflow.
- CAPA actions are entered as raw JSON strings, which is a high-friction UI for end users.
- Methods/Analytes screens expose numeric IDs rather than human-readable linked context (instrument name, method name).

## Gemini Second-Agent Review
Ran Gemini CLI review (saved to `/home/user/projects/BAYESIANQC/reviews/gemini/latest.md`) and incorporated the findings that held up.

Key Gemini findings that I agree with and have integrated above
- Concurrency/lost-update risk in `PosteriorState` updates (must be addressed before treating Bayesian state as authoritative).
- Chart scaling concerns: compute-on-read risk/signal evaluation was not going to survive real volumes; persisting per-record evaluations fixes the hot path, but full-stream reprocessing for retroactive changes is still a scalability pressure point.
- Transaction boundary problems (multiple commits inside a single “logical ingestion”).
- Westgard R-4s semantics gap under a “stream-per-level” model.

Gemini finding I would treat as a tradeoff, not a defect
- Normal approximation at `df >= 30` for intervals: this is a performance/accuracy trade. If you want validation-grade accuracy, make it configurable or remove the approximation; if you want speed for large chart history walks, keep it (but fix the chart architecture first so you’re not doing huge history walks in request/response at all).

Gemini finding I would reframe
- “Missing indexes”: there are per-column indexes (`index=True`) on `QCRecord.stream_id`, `QCRecord.timestamp`, and `PosteriorState.stream_id`, but there is no composite index tailored to the common `(stream_id, timestamp)` access pattern. If chart/ingestion queries become slow, consider adding composite indexes once you move off SQLite or once you formalize migrations.
