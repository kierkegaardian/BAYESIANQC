# BayesianQC Architecture (Middleware-First)

Date: 2026-02-13

Goals
- Keep the **frontend contract stable**: the UI only ever talks to the HTTP API (no direct DB access).
- Make the backend a “true middleware” internally: **only the API/service layer owns transactions** and DB mutations.
- Isolate statistical logic so you can **refactor queries / swap databases** without rewriting QC math.
- Make charts **read-mostly** at scale by persisting per-record evaluations.

Historical Non-Goals
- Full DDD rewrite.
- Alembic is part of the active Postgres persistence boundary.

## Current Shape
- Legacy query logic and writes remain spread across endpoints (`app/main.py`) and storage helpers
  (`app/storage.py`), so continued service extraction is still warranted.
- Statistical computation is pure and typed under `app/math/`; it performs no database writes.
- Every new evaluation is stored as an immutable `QCRecordEvaluation`. `QCRecord` keeps a current
  pointer and synchronized JSON read caches for compatibility.
- `/streams/{stream_id}/chart` is read-mostly and exposes per-record evaluation provenance rather
  than reconstructing historical limits from the current stream configuration.

## Current State vs Target State
Current (today)
- Endpoints and workflows largely live in `app/main.py`.
- DB access lives in `app/storage.py` (repo-ish) plus scattered queries in `app/main.py`.
- `app/evaluation_replay.py` and `app/math/evaluation_engine.py` provide the deterministic replay and
  point-evaluation kernel used by ingestion, inclusion changes, and administrative reprocessing.
- `app/evaluations.py` coordinates preview/apply while persistence and reconciliation are split into
  typed services under `app/services/`.

Target (direction)
- Split into `app/api/` + `app/services/` + `app/repos/` + `app/math/` with transaction boundaries owned by services.

## Target Module Split

### `app/api/` (HTTP Interface)
Responsibilities
- Request parsing/validation, auth, error mapping.
- Call a service function and return DTOs.

Rules
- No SQL queries beyond trivial “load current user” or wiring.
- No math or policy logic besides formatting / mapping.

Suggested modules
- `app/api/qc.py` (ingestion/resolution endpoints)
- `app/api/streams.py` (configs/priors endpoints)
- `app/api/reports.py`, `app/api/audit.py`, etc.

### `app/services/` (Workflows + Transactions)
Responsibilities
- Own the unit-of-work boundary: `with session.begin(): ...`
- Coordinate repo reads/writes + math evaluation + policy decisions.
- Enforce invariants: idempotency, dedupe policy, resolution behavior.

Suggested modules
- `app/services/ingestion.py`
  - `ingest_record(...) -> IngestionResult`
  - Guarantees: one transaction per record (CSV ingests can rollback per-row).
- `app/evaluations.py`
  - `preview_stream_evaluations(stream_id)` and fingerprint-guarded `apply_stream_reprocessing(...)`.
- `app/services/evaluation_persistence.py`
  - Append-only evaluation snapshots, compatibility caches, and alert reconciliation.
- `app/services/alerts.py`
  - “create/close/update alert” policies

Rules
- Services may call repos and math modules.
- Services may not contain raw SQL strings; prefer repos.

### `app/repos/` (Data Access)
Responsibilities
- All SQLModel/SQLAlchemy queries and persistence operations (CRUD).
- No business logic; no policy decisions; no FastAPI concepts.

Rules
- No `commit()` in repos. They operate within the caller’s transaction.
- Return domain objects or DB models; keep mapping to API models in services/api.

Suggested modules
- `app/repos/qc_records.py`
- `app/repos/stream_configs.py`
- `app/repos/priors.py`
- `app/repos/posterior_state.py`
- `app/repos/alerts.py`
- `app/repos/audit.py`

### `app/math/` (Pure Statistical Computation)
Responsibilities
- Pure functions only (no `Session`, no DB).
- Deterministic given inputs (record stream, config, prior, previous state).

Suggested modules
- `app/math/bayesian_nig.py`
  - `update_posterior(prior_state, x) -> posterior_state`
  - `infer_risk(posterior_state, config, streak_state) -> BayesianRisk`
- `app/math/rules.py`
  - `evaluate_rules(value, recent_values, target, sigma, ruleset) -> list[FrequentistSignal]`
- `app/math/control_limits.py`
  - Resolve configured or version-frozen fixed-baseline limits once for all evaluation consumers.
- `app/math/evaluation_engine.py`
  - Combine rules, Student-t next-result risk, disposition, state, and algorithm provenance.

### `app/domain/` (Types + Invariants)
Responsibilities
- Enums, dataclasses, policy DTOs, and “business meaning” types (Disposition, SignalSeverity, etc.).
- No DB.

## Transaction Boundary Rules (What “True Middleware” Means)
- Endpoints call **exactly one** service entrypoint per request.
- That service entrypoint owns:
  - `session.begin()` / `commit()` / `rollback()`
  - locking strategy (important for `PosteriorState` concurrency)
- Repos and math are not allowed to call `commit()`.

Concrete example: QC ingestion
1. API validates payload.
2. Service starts a transaction.
3. Repo inserts `QCRecord` (no commit yet).
4. Service computes evaluations via math modules.
5. Repo updates `QCRecord` with `{signals, bayesian_risk, disposition}`.
6. Repo upserts `PosteriorState` (under lock/optimistic guard).
7. Repo inserts audit + alert if needed.
8. Service commits once.

## Chart Scalability (Read-Mostly)
Implemented direction
- Persist immutable per-record evaluations in `QCRecordEvaluation`, including applied centerline,
  sigma, bounds, config/prior IDs and versions, threshold mode, and engine identifiers.
- Retain `signals`, `bayesian_risk`, and `disposition` on `QCRecord` only as synchronized read caches.
- Reprocessing is required when historical changes occur:
  - out-of-order ingestion
  - record exclusion/inclusion (`include_in_stats`)
  - config/prior changes effective in the past

Operational policy
- Keep `/streams/{stream_id}/chart` read-mostly.
- Replay immediately for out-of-order ingestion and inclusion changes, because those requests carry an
  audit reason.
- Backdated config/prior versions require admin preview/apply with a matching state fingerprint and a
  nonblank reason; future-dated versions remain inactive until their effective time.

## Postgres Persistence And Legacy Import

### Current Runtime
- `docker-compose.yml` provides Postgres and `BAYESIANQC_DB_URL=postgresql+psycopg://...` is the documented default runtime path.
- SQLite is not a supported app runtime. Legacy SQLite files are only supported as one-way import sources.
- The test harness creates disposable Postgres databases from `BAYESIANQC_POSTGRES_TEST_URL` or the local Compose URL.
- Add indexes you will need immediately:
  - `qcrecord (stream_id, timestamp)`
  - `posteriorstate (stream_id)` unique
  - `alertrecord (stream_id, created_at)` (and maybe `qc_record_id`)

### Migrations
- Alembic is the only app migration path.
- Use explicit, versioned migrations for:
  - JSON -> JSONB
  - constraints (unique indexes, NOT NULL where appropriate)
  - foreign keys and cascade policies

### Legacy Import
Safety principles
- Freeze writes during the cutover (short maintenance window).
- Migrate schema first, then data, then verify.

Steps
1. Create Postgres schema via migrations.
2. Export legacy SQLite tables:
   - simplest: `sqlite3 bayesianqc.db .dump` is not ideal for types
   - better: export per-table CSV with headers, then import with `COPY`
   - alternative: `pgloader` if you want speed and can validate the mapping
3. Import into Postgres.
4. Verification checks:
   - row counts per table
   - spot-check streams: recompute `PosteriorState` from `QCRecord` history and compare
   - verify `idempotency_key` uniqueness and alert linkage integrity
5. Existing imported records remain `legacy_unverified`; an administrator previews and explicitly
   applies historical evaluation only after reviewing record and alert effects.

### Concurrency Correctness
- Fix the `PosteriorState` lost-update race by locking:
  - `SELECT posteriorstate ... FOR UPDATE` inside the ingestion transaction.
- Optionally add optimistic concurrency:
  - `updated_at` guard in `WHERE` clause when updating state.
