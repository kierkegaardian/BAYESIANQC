# BayesianQC Architecture (Middleware-First)

Date: 2026-02-13

Goals
- Keep the **frontend contract stable**: the UI only ever talks to the HTTP API (no direct DB access).
- Make the backend a “true middleware” internally: **only the API/service layer owns transactions** and DB mutations.
- Isolate statistical logic so you can **refactor queries / swap databases** without rewriting QC math.
- Make charts **read-mostly** at scale by persisting per-record evaluations.

Non-Goals (for now)
- Full DDD rewrite.
- Introducing a large migration framework (e.g., Alembic) before Postgres is actually in use.

## Current Shape (Problems)
- Query logic and writes are spread across endpoints (`app/main.py`), “storage” helpers (`app/storage.py`),
  and math (`app/bayesian.py` commits state).
- `commit()` calls inside helpers make transaction boundaries unclear, which breaks atomicity for ingestion.
- `/streams/{stream_id}/chart` was compute-heavy; risk/signal evaluations are now persisted on `QCRecord`,
  but you still need a clean layering plan to keep it maintainable.

## Current State vs Target State
Current (today)
- Endpoints and workflows largely live in `app/main.py`.
- DB access lives in `app/storage.py` (repo-ish) plus scattered queries in `app/main.py`.
- Math lives in `app/bayesian.py` and `app/frequentist.py`, but Bayesian state update still persists/commits.
- Stream reprocessing currently exists as a single module `app/evaluations.py` (batch evaluator + persistence).

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
- `app/services/evaluations.py`
  - `reprocess_stream_evaluations(stream_id)` (already exists as `app/evaluations.py`; move here later)
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
- `app/math/bayes.py`
  - `update_posterior(prior_state, x) -> posterior_state`
  - `infer_risk(posterior_state, config, streak_state) -> BayesianRisk`
- `app/math/westgard.py`
  - `evaluate_rules(value, recent_values, target, sigma, ruleset) -> list[FrequentistSignal]`

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
- Persist per-record evaluations on `QCRecord`:
  - `signals` (JSON)
  - `bayesian_risk` (JSON)
  - `disposition` (string)
- Reprocessing is required when historical changes occur:
  - out-of-order ingestion
  - record exclusion/inclusion (`include_in_stats`)
  - config/prior changes effective in the past

Operational policy
- Keep `/streams/{stream_id}/chart` read-mostly.
- Reprocess proactively on mutations (resolution/config/prior) and on out-of-order ingestion.
- Optional: expose an explicit maintenance endpoint later (`POST /streams/{id}/reprocess`) for operators.

## SQLite -> Postgres Migration Plan (Safe)

### Phase 0: Make the App DB-Agnostic (Now)
- Ensure every DB call is behind repos/services.
- Avoid SQLite-specific SQL in business logic.

### Phase 1: Add Postgres as a Dev/CI Target
- Add a `docker-compose.yml` for Postgres (dev only).
- Teach the app to run against `BAYESIANQC_DB_URL=postgresql+psycopg://...`.
- Add indexes you will need immediately:
  - `qcrecord (stream_id, timestamp)`
  - `posteriorstate (stream_id)` unique
  - `alertrecord (stream_id, created_at)` (and maybe `qc_record_id`)

### Phase 2: Introduce Real Migrations
- When Postgres is introduced, switch from `PRAGMA user_version` scripts to Alembic (or similar).
- Use explicit, versioned migrations for:
  - JSON -> JSONB
  - constraints (unique indexes, NOT NULL where appropriate)
  - foreign keys and cascade policies

### Phase 3: Data Migration (SQLite -> Postgres)
Safety principles
- Freeze writes during the cutover (short maintenance window).
- Migrate schema first, then data, then verify.

Steps
1. Deploy code that can talk to Postgres (but still uses SQLite in prod).
2. Create Postgres schema via migrations.
3. Export SQLite tables:
   - simplest: `sqlite3 bayesianqc.db .dump` is not ideal for types
   - better: export per-table CSV with headers, then import with `COPY`
   - alternative: `pgloader` if you want speed and can validate the mapping
4. Import into Postgres.
5. Verification checks:
   - row counts per table
   - spot-check streams: recompute `PosteriorState` from `QCRecord` history and compare
   - verify `idempotency_key` uniqueness and alert linkage integrity
6. Switch `BAYESIANQC_DB_URL` to Postgres and restart.
7. Post-cutover: run a full `reprocess_stream_evaluations` per stream once to ensure cached evaluations align.

### Phase 4: Concurrency Correctness (Postgres Benefits)
- Fix the `PosteriorState` lost-update race by locking:
  - `SELECT posteriorstate ... FOR UPDATE` inside the ingestion transaction.
- Optionally add optimistic concurrency:
  - `updated_at` guard in `WHERE` clause when updating state.
