# BayesianQC Postgres Cutover Review Packet

Date: 2026-07-03
Scope: local/dev Postgres-first cutover, migration validation, and reviewer gate.

## Implementation Summary
- Postgres is now the default app runtime URL in `app/db.py`: `postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc`.
- SQLite remains available only when explicitly configured, primarily for compatibility tests and SQLite-to-Postgres rehearsal.
- `alembic.ini` defaults to the local/dev Postgres Compose URL; SQLite requires explicit configuration.
- `scripts/rehearse_sqlite_to_postgres.py` now derives Alembic head dynamically, reports `20260703_0002`, checks schema/indexes, row-count parity, Postgres sequence next values, and posterior-parameter recomputation with `1e-9` tolerance.
- `tests/test_migrations.py` now has opt-in disposable Postgres tests via `BAYESIANQC_POSTGRES_TEST_URL`, including Alembic upgrade, downgrade/re-upgrade, SQLite copy parity, sequence validation, posterior recomputation, and same-stream concurrent ingestion.
- `Makefile`, CI, README, run scripts, and readiness docs now describe and exercise the Postgres-first local/dev path.
- `scripts/run_demo.sh` starts Compose Postgres and waits for `pg_isready` before spawning the backend.
- `make migration-rehearse-postgres-copy` requires `POSTGRES_COPY_URL`, refuses URLs that do not look disposable/test/rehearsal, and is documented as destructive/disposable-only.
- Generated runtime artifacts were removed before and after validation; existing unrelated dirty work was preserved.

## Validation Evidence
### Static And SQLite Regression
- `.venv/bin/python -m pytest -q`: `33 passed, 5 skipped`. This is the SQLite compatibility/regression suite by default.
- `.venv/bin/pyright`: `0 errors`.
- `.venv/bin/python -m ruff check app tests scripts`: passed.
- `npm --prefix frontend run check`: passed with the known Vite large chunk warning.
- `git diff --check`: passed.
- Anchored conflict marker scan `^(<<<<<<<|=======|>>>>>>>)`: no hits.

### Local/Dev Postgres Gate
- `docker compose up -d postgres`: passed; `bayesianqc-postgres-1` healthy.
- `BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc .venv/bin/alembic upgrade head`: passed, head `20260703_0002`.
- `BAYESIANQC_POSTGRES_TEST_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc .venv/bin/python -m pytest tests/test_migrations.py -q`: `8 passed`. This now includes Alembic upgrade, downgrade/re-upgrade, SQLite copy parity with seeded QC data, sequence validation, posterior recomputation, concurrent same-stream ingestion, and a disposable-Postgres API smoke for `/me`, backlog, `POST /qc/records`, quarantine, chart, and audit.
- `make check-postgres`: passed; includes Compose Postgres, Alembic upgrade, Postgres migration/API tests, and Postgres rehearsal with posterior recomputation on the non-pristine dev Postgres data.
- `bash -n scripts/run_demo.sh scripts/stop_demo.sh`: passed.
- `make migration-rehearse-postgres-copy` against a `bayesianqc_disposable_rehearsal_*` target: passed after the disposable-name safety guard.
- Runtime smoke on port `8010` against Postgres: `/me`, `POST /qc/records`, `/qc/backlog`, `/streams/hba1c-arch/chart`, `/qc/quarantine`, and `/audit` passed. Existing `bayesianqc.db` timestamp and size stayed unchanged.

### SQLite-To-Postgres Rehearsal
- `.venv/bin/python scripts/rehearse_sqlite_to_postgres.py`: passed; `revision_head` and schema smoke `alembic_version` both `20260703_0002`.
- SQLite-to-Postgres copy rehearsal against a temporary Postgres DB with `make migration-rehearse-postgres-copy`: passed; table counts matched, sequences OK, posterior checks OK. The current source `bayesianqc.db` has no QC records, so `streams_checked` was `0` for that source.
- Seeded-source copy and posterior-value parity are covered by `tests/test_migrations.py` under `BAYESIANQC_POSTGRES_TEST_URL`.

## Worktree Inclusion Note
This packet reviews the live worktree, not a staged commit. Several cutover files are currently untracked and must be included before any PR/commit, including `alembic.ini`, `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml`, `migrations/`, `scripts/rehearse_sqlite_to_postgres.py`, `tests/test_migrations.py`, and the new migration/readiness docs. Do not infer merge readiness from `git diff --stat` alone; use `git status --short` as well.

## Known Constraints
- The stale port `8010` process was stopped with `scripts/stop_demo.sh`; `scripts/run_demo.sh` now starts port `8010` with `BAYESIANQC_DB_URL` set to the local/dev Postgres URL and waits for Postgres readiness first.
- The local Postgres dev database contains smoke rows from runtime validation and is not a pristine fixture database.
- Production/shared-lab cutover is explicitly out of scope for this slice.
- Existing dirty/untracked repo work predates this slice and was preserved.

## Remaining Gaps
- A generated cross-engine schema-diff gate is still needed before regulated deployment; the current guard is Alembic head/version, schema/index checks, row-count checks, sequence checks, and posterior recomputation.
- Stronger foreign-key coverage and explicit future Alembic DDL deltas are still needed before regulated deployment.
- Datetime handling still relies on UTC-normalized values and needs formal timezone hardening before shared-lab use.
- Backup/restore SOP, rollback proof, OIDC/MFA, e-signature semantics, retention controls, and formal Bayesian model validation remain blockers for shared lab deployment.
- The frontend build still emits the known large Vite chunk warning.

## Reviewer Instructions
Act as a strict reviewer. Findings first. Treat P0/P1 findings as blocking unless explicitly waived. Focus on:
- migration correctness and data integrity
- Postgres-first runtime boundary
- SQLite fallback risk
- sequence and copy rehearsal correctness
- concurrency coverage
- operational rollback/readiness gaps
- docs and command accuracy
