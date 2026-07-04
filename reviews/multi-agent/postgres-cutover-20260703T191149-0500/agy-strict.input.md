# BayesianQC Postgres Cutover Review Packet

Date: 2026-07-03
Scope: local/dev Postgres-first cutover, migration validation, and reviewer gate.

## Implementation Summary
- Postgres is now the default app runtime URL in `app/db.py`: `postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc`.
- SQLite remains available only when explicitly configured, primarily for compatibility tests and SQLite-to-Postgres rehearsal.
- `scripts/rehearse_sqlite_to_postgres.py` now derives Alembic head dynamically, reports `20260703_0002`, checks schema/indexes, row-count parity, Postgres sequence next values, and `PosteriorState.n_obs` sanity.
- `tests/test_migrations.py` now has opt-in disposable Postgres tests via `BAYESIANQC_POSTGRES_TEST_URL`, including Alembic upgrade, SQLite copy parity, sequence validation, posterior sanity, and same-stream concurrent ingestion.
- `Makefile`, CI, README, run scripts, and readiness docs now describe and exercise the Postgres-first local/dev path.
- Generated runtime artifacts were removed before and after validation; existing unrelated dirty work was preserved.

## Validation Evidence
- `docker compose up -d postgres`: passed; `bayesianqc-postgres-1` healthy.
- `BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc .venv/bin/alembic upgrade head`: passed, head `20260703_0002`.
- `.venv/bin/python scripts/rehearse_sqlite_to_postgres.py`: passed; `revision_head` and schema smoke `alembic_version` both `20260703_0002`.
- SQLite-to-Postgres copy rehearsal against temporary Postgres DB with `--copy-data --truncate-target`: passed; table counts matched, sequences OK, posterior sanity OK.
- `BAYESIANQC_POSTGRES_TEST_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc .venv/bin/python -m pytest tests/test_migrations.py -q`: `6 passed`.
- `make check-postgres`: passed; includes Compose Postgres, Alembic upgrade, Postgres migration tests, and Postgres rehearsal.
- `.venv/bin/python -m pytest -q`: `33 passed, 3 skipped`.
- `.venv/bin/pyright`: `0 errors`.
- `.venv/bin/python -m ruff check app tests scripts`: passed.
- `npm --prefix frontend run check`: passed with the known Vite large chunk warning.
- `git diff --check`: passed.
- Anchored conflict marker scan `^(<<<<<<<|=======|>>>>>>>)`: no hits.
- Runtime smoke on port `8011` against Postgres: `/me`, `/qc/backlog`, `/qc/records`, `/streams/hba1c-arch/chart`, `/qc/quarantine`, and `/audit` passed. Existing `bayesianqc.db` timestamp and size stayed unchanged.

## Known Constraints
- Port `8010` was already occupied by an older BAYESIANQC uvicorn process with no `BAYESIANQC_DB_URL`; it was left untouched. Smoke used port `8011`.
- The local Postgres dev database contains smoke rows from runtime validation.
- Production/shared-lab cutover is explicitly out of scope for this slice.
- Existing dirty/untracked repo work predates this slice and was preserved.

## Remaining Gaps
- Full Bayesian posterior value recomputation and cross-database value comparison still need automation beyond `PosteriorState.n_obs` sanity.
- Stronger foreign-key coverage and explicit future Alembic DDL deltas are still needed before regulated deployment.
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
