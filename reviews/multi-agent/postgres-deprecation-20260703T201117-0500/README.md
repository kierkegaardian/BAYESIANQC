# BAYESIANQC Postgres Runtime Deprecation Review Packet

Timestamp: 20260703T201117-0500

## Review Scope

This packet covers the local/dev persistence cutover from dual SQLite/Postgres behavior to a Postgres-only app runtime. SQLite is retained only as a legacy import/rehearsal source.

Review for P0/P1 risks in:

- Runtime startup and local demo operation.
- Alembic upgrade behavior and schema drift detection.
- Legacy SQLite-to-Postgres import rehearsal.
- Postgres test database lifecycle and isolation.
- Documentation clarity for demo users and lab operators.

Do not push, change remotes, or mutate external infrastructure during review.

## Core Implementation Summary

- `app/db.py` now rejects SQLite and non-Postgres URLs at runtime.
- `init_db()` delegates to Alembic for Postgres schema setup instead of SQLModel `create_all`.
- `app/migrations.py` now contains only the Alembic upgrade helper.
- SQLite-specific runtime migration code was removed from app startup.
- Stream write locking now uses Postgres row locks only.
- The pytest harness creates and drops a disposable Postgres database from `BAYESIANQC_POSTGRES_TEST_URL`.
- `scripts/rehearse_sqlite_to_postgres.py` now rehearses Postgres upgrade/schema/sequence/posterior checks and uses SQLite only as a legacy source when `--copy-data` is requested.
- `Makefile`, demo scripts, README, lab-readiness docs, validation docs, migration strategy, and architecture docs describe Postgres as the supported local/dev runtime.

## Key Files To Inspect

- `app/db.py`
- `app/migrations.py`
- `app/services/locks.py`
- `tests/conftest.py`
- `tests/test_migrations.py`
- `scripts/rehearse_sqlite_to_postgres.py`
- `Makefile`
- `scripts/run_demo.sh`
- `scripts/stop_demo.sh`
- `README.md`
- `docs/LAB_READINESS.md`
- `docs/VALIDATION_PACKAGE.md`
- `docs/MIGRATION_STRATEGY.md`
- `docs/ARCHITECTURE.md`

## Known Boundaries

- This is a local/dev cutover, not a shared lab production deployment.
- Existing `bayesianqc.db` may still exist in a developer worktree, but app startup must not read, create, or mutate it.
- SQLite is still allowed as an explicit source input to the legacy import rehearsal.
- Production/lab go-live remains blocked by backup/restore SOP, rollback proof, OIDC/MFA, e-signature semantics, and formal Bayesian validation.
