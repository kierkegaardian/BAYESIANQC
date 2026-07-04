# BayesianQC Migration Strategy

Date: 2026-06-28

## Current State
- Postgres is the only supported app runtime. `init_db()` runs Alembic on startup.
- The app rejects `sqlite://` URLs; legacy SQLite files are import sources only.
- Alembic revision `20260703_0002` is the current Postgres schema head.
- A local rehearsal helper exists at `scripts/rehearse_sqlite_to_postgres.py` and reports schema checks, table counts, sequence checks, Alembic head/version checks, and posterior parameter recomputation.
- Production-like shared-lab Postgres use is still blocked until the validation bundle includes backup/restore proof, rollback evidence, OIDC/MFA, e-signature semantics, and formal Bayesian model validation.

## Local Upgrade Validation
Run the empty-schema upgrade path against Postgres:
```bash
docker compose up -d postgres
export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
alembic upgrade head
python scripts/rehearse_sqlite_to_postgres.py --postgres-url "$BAYESIANQC_DB_URL"
```

Confirm indexes and constraints:
   - `qcrecord (stream_id, timestamp)`
   - unique `posteriorstate (stream_id)`
   - unique idempotency receipt key
   - `alertrecord (stream_id, created_at)`

The always-on Postgres Alembic smoke is covered by:
```bash
pytest tests/test_migrations.py::test_alembic_upgrade_head_creates_current_schema \
  tests/test_migrations.py::test_rehearsal_revision_head_tracks_alembic_head
```
The full local/dev gate is:
```bash
make check-postgres
```

## Postgres Rehearsal
Start the dev database and run the Postgres upgrade:
```bash
docker compose up -d postgres
export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
alembic upgrade head
python scripts/rehearse_sqlite_to_postgres.py --postgres-url "$BAYESIANQC_DB_URL"
```

Run opt-in Postgres migration tests with a disposable URL:
```bash
export BAYESIANQC_POSTGRES_TEST_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
pytest tests/test_migrations.py
```
The Postgres fixture creates and drops temporary databases derived from `BAYESIANQC_POSTGRES_TEST_URL`.
Equivalent local/dev gate:
```bash
make check-postgres
```

If a legacy SQLite source exists and the target is disposable, rehearse the copy/count path:
```bash
docker exec bayesianqc-postgres-1 dropdb -U bayesianqc --if-exists bayesianqc_disposable
docker exec bayesianqc-postgres-1 createdb -U bayesianqc bayesianqc_disposable
export POSTGRES_COPY_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc_disposable
make migration-rehearse-postgres-copy
```
Equivalent direct script form:
```bash
python scripts/rehearse_sqlite_to_postgres.py \
  --sqlite-db bayesianqc.db \
  --postgres-url "$POSTGRES_COPY_URL" \
  --copy-data \
  --truncate-target
```

Archive:
- script JSON output
- table counts from the legacy source and Postgres
- `alembic_version`
- index/constraint checks
- sequence and posterior-state sanity checks
- any reviewer artifacts

## Cutover Rule
Use Postgres for local/dev runtime. Do not point a shared lab process at Postgres until the migration revision, validation bundle, rollback proof, and reviewer synthesis are archived together.

## Remaining Gaps
- The first revision uses the current SQLModel metadata as the schema source; before regulated deployment, freeze future revisions as explicit `op.create_table` / `op.add_column` deltas.
- Foreign-key coverage remains limited to relationships already declared in `app/db_models.py`.
- A generated schema-diff gate is still needed before shared-lab use.
- Datetimes are still treated as UTC-normalized naive values in parts of the stack; formal timezone hardening is required before shared-lab deployment.
- No rollback proof, restore drill, or backup/retention SOP is included yet.
