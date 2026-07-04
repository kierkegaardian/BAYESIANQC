# BayesianQC Lab-Readiness Notes

Date: 2026-06-28

## Current Target
BayesianQC is now a defensible lab prototype for local evaluation and supervised pilot planning. It is not yet a fully validated production LIS/LIMS component.

## Deployment Boundary
- Postgres is the only supported local/dev runtime and the intended lab deployment database.
- Legacy SQLite files are supported only as import sources for one-way migration rehearsal.
- Start the dev database with:
  ```bash
  docker compose up -d postgres
  export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
  export BAYESIANQC_SEED_LOCAL_DEV_KEY=1
  uvicorn app.main:app --reload --port 8010
  ```
- Alembic revision `20260703_0002` is the current Postgres schema head. The app applies Alembic automatically on startup.
- Run `python scripts/rehearse_sqlite_to_postgres.py --postgres-url "$BAYESIANQC_DB_URL"` for a Postgres schema rehearsal. For a disposable target only, run `make migration-rehearse-postgres-copy POSTGRES_COPY_URL=postgresql+psycopg://...` to rehearse a legacy SQLite import copy/count, sequence, and posterior-parameter path.
- Tests use Postgres. Set `BAYESIANQC_POSTGRES_TEST_URL` to override the base URL; the harness creates and drops disposable databases derived from it.
- `local-dev-key` is a dev/test convenience. Do not enable `BAYESIANQC_SEED_LOCAL_DEV_KEY` in shared lab-like environments.
- API keys are stored as salted PBKDF2 hashes. Legacy SHA-256 hashes are accepted only long enough to migrate on successful authentication.

## Validation Gate
Before any lab pilot, run the checks in [VALIDATION_PACKAGE.md](VALIDATION_PACKAGE.md) and archive:
- command output
- OpenAPI schema snapshot
- validation fixture data
- audit export for the tested chart window
- reviewer artifacts for P0/P1 risk review

## Remaining Non-v1 Gaps
- OIDC/MFA and enterprise identity lifecycle.
- Electronic signatures and meaning-of-signature capture.
- Segregation-of-duty policy beyond role permissions.
- Retention, legal hold, and backup/restore SOPs.
- Notification routing, escalation, and alert storm controls.
- Formal Bayesian model validation, backtesting, and monitoring.
- LIMS/instrument middleware mapping and interface validation.
- Production-grade Postgres migration/cutover SOP with rollback proof.
- Generated cross-engine schema-diff checks beyond the current Alembic head/version, row-count, sequence, and posterior-parameter rehearsal.
- Timezone hardening beyond the current UTC-normalized datetime convention.
