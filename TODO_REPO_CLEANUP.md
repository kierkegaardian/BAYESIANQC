# BAYESIANQC Repo Cleanup TODO

Date: 2026-06-28

Purpose: get the current dirty tree into a clean, reviewable state without deleting useful work. This repo currently mixes remediation code, chart-kiosk fixture work, review artifacts, generated runtime files, and local caches.

Do not run broad destructive cleanup commands until each bucket below has been reviewed.

## Safety Rules

- Preserve all untracked files until they are classified.
- Use dry runs first: `git clean -nd` and `git clean -ndX`.
- Stop the demo before removing PID/log/runtime files: `scripts/stop_demo.sh`.
- Do not delete review artifacts until the useful conclusions are copied into durable docs or archived.
- Stage cleanup in small commits or reviewable batches.

## Current Dirty Buckets

### Bucket A: Remediation Code and Docs

These are likely intended product changes from the remediation slice and should be reviewed together:

- `app/db.py`
- `app/db_models.py`
- `app/main.py`
- `app/migrations.py`
- `app/models.py`
- `app/rbac.py`
- `app/security.py`
- `app/services/`
- `app/storage.py`
- `frontend/src/api/session.ts`
- frontend page/layout updates
- `docker-compose.yml`
- `docs/LAB_READINESS.md`
- `docs/MIGRATION_STRATEGY.md`
- `docs/VALIDATION_PACKAGE.md`
- `docs/STANDARDS_FEATURE_ROADMAP.md`
- `README.md`
- `requirements.txt`
- `scripts/create_api_key.py`
- `scripts/run_demo.sh`
- `scripts/stop_demo.sh`
- `tests/conftest.py`
- `tests/test_ingestion.py`

TODO:
- [ ] Confirm this bucket is one coherent remediation commit or split into backend/frontend/docs commits.
- [ ] Re-run full quality gates before staging.
- [ ] Ensure `app/main.py` size is documented as a temporary exception until service extraction.

### Bucket B: Chart-Kiosk Fixture Work

These appear to be useful demo/fixture additions but predate or sit beside the remediation work:

- `samples/chart_kiosk_*.json`
- `samples/chart_kiosk_*.csv`
- `samples/chart_kiosk_d86_*.json`
- `samples/chart_kiosk_d86_*.csv`
- `scripts/load_chart_kiosk_suite.py`
- `tests/test_chart_kiosk.py`
- `docs/CHART_KIOSK_REVIEW.md`

TODO:
- [ ] Decide whether chart-kiosk fixtures belong in the same branch as remediation.
- [ ] If yes, stage as a separate fixture/demo commit.
- [ ] If no, archive or move to a follow-up branch before committing remediation.
- [ ] Verify fixture loader is idempotent and covered by tests.

### Bucket C: Tooling and CI Files

These are useful but should be intentionally adopted:

- `.github/workflows/ci.yml`
- `Makefile`
- `pyproject.toml`
- `uv.lock`
- `requirements-dev.txt`
- `pyrightconfig.json`
- `TYPESAFETY_TODO.md`

TODO:
- [ ] Decide package manager strategy: `pip/requirements` only, or adopt `uv.lock`.
- [ ] If adopting `uv.lock`, commit it and document `uv` usage.
- [ ] If not adopting `uv.lock`, add it to `.gitignore`.
- [ ] Ensure CI matches the commands in `README.md` and the remediation handoff.
- [ ] Reconcile `pyproject.toml`, `requirements.txt`, and `requirements-dev.txt`.

### Bucket D: Review Artifacts

Current review directories include AGY, Grok, Gemini, and Codex outputs:

- `reviews/agy/`
- `reviews/grok/`
- `reviews/gemini/`
- `reviews/codex/latest.md`

TODO:
- [ ] Keep the final AGY remediation review: `reviews/agy/bayesianqc-remediation-review-20260628T200526-0500.md`.
- [ ] Keep the AGY Opus feature review: `reviews/agy/bayesianqc-opus-feature-review-20260628T211241-0500.md`.
- [ ] Archive failed or superseded review attempts under `reviews/archive/` or leave untracked.
- [ ] Decide whether `reviews/*/*.input.txt`, `reviews/*/*.agy.log`, and `*.stderr.log` should ever be committed.
- [ ] Update `reviews/codex/latest.md` only if it is meant to remain the current Codex review pointer.

### Bucket E: Generated Runtime and Cache Files

These should generally be ignored and deleted after confirming no process is using them:

- `.demo-backend.pid`
- `.demo-frontend.pid`
- `bayesianqc.db`
- `uvicorn.log`
- `frontend/vite.log`
- `.pytest_cache/`
- `.ruff_cache/`
- `app/__pycache__/`
- `tests/__pycache__/`
- `scripts/__pycache__/`
- `bayesianqc.egg-info/`

TODO:
- [x] Stop/remove stale demo runtime state. No matching uvicorn/Vite demo processes were running; stale PID files were removed.
- [x] Add missing ignore patterns for `.pytest_cache/` and `.ruff_cache/`.
- [ ] Run `git clean -ndX` and inspect ignored-delete candidates.
- [x] Remove exact ignored generated runtime files without broad-cleaning `.venv/`, `frontend/node_modules/`, `frontend/dist/`, or `openapi.json`.
- [x] Ignore and remove transient review input/log artifacts (`*.input.txt`, `*.agy.log`, `*.stderr.log`) while preserving durable review Markdown.

## Code Cleanup Plan

### 1. Service Boundary Cleanup

- [ ] Move alert update logic from `app/main.py` into `app/services/alerts.py`.
- [ ] Move investigation create/update logic into `app/services/investigations.py`.
- [ ] Move CAPA create/update logic into `app/services/capas.py`.
- [ ] Move record resolution/reprocess/audit logic into `app/services/resolution.py`.
- [ ] Remove remaining `session.commit()` calls from helper/repo-like functions.
- [ ] Keep one transaction boundary per service entrypoint.

### 2. Repository Layer

- [ ] Create `app/repos/` with modules for records, streams, priors, alerts, audit, investigations, CAPAs, and master data.
- [ ] Move repeated `session.exec(select(...))` queries out of `app/main.py`.
- [ ] Keep repos free of FastAPI exceptions and HTTP status codes.
- [ ] Keep repos free of commits.

### 3. Math Layer

- [ ] Move Bayesian math toward pure functions under `app/math/`.
- [ ] Move frequentist rule evaluation toward configurable rule definitions.
- [ ] Keep DB-backed posterior reconstruction in services, not math modules.

### 4. API Split

- [ ] Split `app/main.py` into routers after service/repo extraction:
  - `app/api/qc.py`
  - `app/api/streams.py`
  - `app/api/master_data.py`
  - `app/api/alerts.py`
  - `app/api/investigations.py`
  - `app/api/capas.py`
  - `app/api/audit.py`
  - `app/api/reports.py`
- [ ] Keep `app/main.py` to app construction, middleware, lifespan, and router inclusion.

## Test Cleanup Plan

- [ ] Add data steward negative tests for ingest/approve boundaries.
- [ ] Add supervisor/QA manager tests once QA Manager exists.
- [ ] Add CSV endpoint tests with row-level error handling.
- [ ] Add stream config version conflict tests.
- [ ] Add investigation-alert-CAPA linking tests.
- [ ] Add CAPA state-transition tests.
- [ ] Add chart edge cases: empty stream, one point, all points excluded, no alerts, multiple lots.
- [ ] Add auth tests for legacy key migration and invalid-key fast failure.
- [ ] Add Postgres CI job now that Alembic migration scaffolding exists.

## Documentation Cleanup Plan

- [ ] Update `docs/ARCHITECTURE.md` to reflect the new service layer and remaining deviations.
- [ ] Add `CONTRIBUTING.md` with quality gates and branch expectations.
- [ ] Add `CHANGELOG.md` starting from the remediation baseline.
- [ ] Add a short deployment runbook for Postgres demo and legacy SQLite import only.
- [ ] Link `docs/STANDARDS_FEATURE_ROADMAP.md` from `README.md`.
- [ ] Document which review artifacts are durable and which are scratch.

## Suggested Cleanup Sequence

1. Stop demo services and remove ignored runtime files. (Done for stale PID/log/cache/legacy DB runtime state.)
2. Add missing ignore patterns and run ignored-file cleanup. (Done for targeted runtime/cache/review-log outputs; dependency/build artifacts intentionally preserved.)
3. Decide whether chart-kiosk fixtures are in-scope for this branch.
4. Decide whether `uv.lock`, `pyproject.toml`, `Makefile`, and CI are in-scope.
5. Archive or leave untracked superseded review artifacts.
6. Stage remediation code/docs separately from fixture/tooling work.
7. Run full gates:
   - `.venv/bin/python -m pytest -q`
   - `.venv/bin/pyright`
   - `.venv/bin/python -m ruff check app tests scripts`
   - `npm --prefix frontend run check`
   - `git diff --check`
   - conflict-marker scan
   - OpenAPI regeneration drift check

## Definition of Clean

- `git status --short` has only intentional staged changes.
- Generated DB, logs, PID files, caches, pycache, and egg-info files are absent or ignored.
- Review artifacts are either committed intentionally, archived intentionally, or left untracked intentionally.
- Chart-kiosk fixtures are either committed as a coherent fixture slice or moved out of the remediation branch.
- The README, architecture docs, and validation docs agree on the supported commands and deployment path.
