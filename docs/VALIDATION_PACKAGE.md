# BayesianQC Validation Package

Date: 2026-06-28

## Required Static And Postgres Gates
```bash
docker compose up -d postgres
pytest
pyright
ruff check app tests scripts
npm --prefix frontend run check
git diff --check
python -m pytest tests/test_ingestion.py tests/test_chart_kiosk.py
npm --prefix frontend run gen:api
git diff --exit-code -- openapi.json frontend/src/api/schema.ts
python scripts/rehearse_sqlite_to_postgres.py --postgres-url "$BAYESIANQC_DB_URL"
```
`pytest` creates a disposable Postgres database by default. It is no longer a SQLite compatibility gate.

## Required Local/Dev Postgres Gate
Use a disposable local Postgres target:
```bash
docker compose up -d postgres
export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
export BAYESIANQC_POSTGRES_TEST_URL="$BAYESIANQC_DB_URL"
alembic upgrade head
python scripts/rehearse_sqlite_to_postgres.py --postgres-url "$BAYESIANQC_DB_URL"
BAYESIANQC_POSTGRES_TEST_URL="$BAYESIANQC_DB_URL" pytest tests/test_migrations.py
```
The migration/API-smoke tests create disposable databases derived from `BAYESIANQC_POSTGRES_TEST_URL` or the local Compose URL.

If a legacy SQLite source database exists and the target can be reset:
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
Do not run the copy rehearsal against a shared dev or lab database.

## Functional Matrices

### RBAC
- Auditor can read streams, charts, alerts, investigations, CAPAs, audit, and summary reports.
- Auditor cannot ingest QC, create events, approve records, update alerts, or edit configuration.
- Data steward can read and edit configuration.
- Data steward cannot ingest QC, create events, approve records, update alerts, or change investigations/CAPAs.
- QC analyst can read and ingest QC/events.
- QC analyst cannot edit configuration or approve workflow changes.
- Admin has all permissions.

### Ingestion and Bayesian State
- Minimal QC payload omitting optional fields is accepted.
- Duplicate exact payload is flagged as duplicate and remains auditable.
- Same-stream concurrent ingestion produces the expected `PosteriorState.n_obs`.
- Out-of-order ingestion reprocesses persisted per-record evaluations and matches full recomputation.
- Prior/config changes effective before existing records reprocess the affected stream.

### Audit Reconstruction
- Every emitted audit response has `after`.
- Audit rows include `actor`, `actor_role`, and `api_key_id`.
- Resolution exclusion/reinclusion requires a reason.
- Alert, investigation, and CAPA updates require a reason.
- Chart reconstruction for a selected historical window can explain records, events, alerts, exclusions, and CAPA links from stored data.

## Pilot Evidence Bundle
Archive these files for each pilot validation run:
- OpenAPI JSON generated from the tested commit.
- Test fixture payloads and CSVs.
- DB row-count summary for instruments, methods, analytes, streams, priors, records, events, alerts, investigations, CAPAs, audit, and receipts.
- Alembic revision and migration rehearsal JSON output, including sequence and posterior-parameter checks.
- Audit export for the validated chart date range.
- Reviewer artifacts showing zero unresolved P0/P1 findings or explicit waivers.

This local/dev Postgres cutover does not satisfy the full pilot evidence bundle by itself. A pilot bundle still requires an OpenAPI snapshot/diff, fixture archive, audit export, backup/restore evidence, rollback proof, and final reviewer synthesis.
