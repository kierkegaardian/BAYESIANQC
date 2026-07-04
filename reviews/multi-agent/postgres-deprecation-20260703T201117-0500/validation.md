# Validation Receipt

## Static, Type, Frontend, And Test Gates

- `.venv/bin/ruff check app tests scripts`: passed.
- `.venv/bin/pyright`: passed with 0 errors.
- `npm --prefix frontend run check`: passed. Vite emitted the existing large chunk warning.
- `git diff --check`: passed.
- `rg -n "^(<<<<<<<|=======|>>>>>>>)" .`: no conflict markers found.
- `bash -n scripts/run_demo.sh scripts/stop_demo.sh`: passed.
- `.venv/bin/pytest -q`: passed, 39 tests after reviewer hardening.

## Postgres And Migration Gates

- `docker compose ps postgres`: Postgres container healthy on local port 54329.
- `make check-postgres`: passed.
- `tests/test_migrations.py`: 9 tests passed inside `make check-postgres`.
- Alembic upgraded Postgres to `20260703_0002`.
- Rehearsal JSON reported `revision_head: 20260703_0002` and schema `alembic_version: 20260703_0002`.
- Rehearsal sequence checks returned status `ok`.
- Rehearsal posterior checks returned `ok: true`.
- Guarded copy rehearsal with `POSTGRES_COPY_URL` containing `disposable` passed with copied counts matching source counts and target sequence checks OK.
- Non-disposable `--copy-data --truncate-target` rehearsal attempts now fail before target connection with a disposable-target error.
- Disposable copy target `bayesianqc_disposable_deprecation_codex` was dropped after rehearsal.

## Runtime Smoke

- Fresh `scripts/run_demo.sh` start launched Postgres-backed backend on `8010` and frontend on `5177`.
- Backend process environment included `BAYESIANQC_DB_URL=postgresql+psycopg://...`.
- `/me` returned admin context using `X-API-Key: local-dev-key`.
- `POST /qc/records` accepted manual smoke run `smoke-postgres-20260704-1`.
- `/streams/hba1c-arch/chart` returned records with Bayesian risk fields.
- `/qc/backlog` returned HTTP 200.
- `/qc/quarantine` returned HTTP 200.
- `/audit` returned the smoke `ingest_qc` audit row.
- `BAYESIANQC_DB_URL=sqlite:///tmp/nope.db` raised `RuntimeError: BAYESIANQC app runtime requires Postgres; SQLite is legacy-import input only.`
- `bayesianqc.db` stat stayed `1783120453 348160 bayesianqc.db` before and after normal demo startup.

## Reviewer-Driven Hardening

- `app/migrations.py` now uses `engine.connect()` and lets Alembic manage its transaction.
- `app/services/locks.py` now takes a Postgres advisory transaction lock per stream before the row lock, while no-oping for explicit legacy SQLite source sessions.
- `scripts/rehearse_sqlite_to_postgres.py` now guards destructive copy rehearsals at script level, not only in Make.
- `_reset_postgres_sequences` now skips tables with no Postgres serial sequence.
- `tests/conftest.py` now raises an explicit local-Postgres prerequisite error when the test base URL cannot be reached.
- `tests/test_migrations.py` now covers the non-disposable copy guard.

## Residual Validation Risk

- AGY, Grok build, and Grok composer completed with approve-with-nits verdicts. Claude and legacy Gemini could not authenticate and are archived as failure artifacts.
- The default local database now contains smoke/demo rows from validation.
