Second follow-up review for remediated BAYESIANQC local/dev Postgres cutover. Findings first with P0/P1/P2 severity. Treat P0/P1 as blocking for local/dev only if not addressed by the current packet/docs/tests. Scope excludes shared-lab production. Verify fixes for prior follow-up blockers: untracked worktree visibility, expanded Postgres API smoke coverage, AGENTS seed env, validation-package gate labeling, evidence buckets, and empty SQLite-source caveat. Do not mutate files.

=== REVIEW_PACKET.md ===
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
- `make migration-rehearse-postgres-copy` requires `POSTGRES_COPY_URL` and is documented as destructive/disposable-only.
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
- Runtime smoke on port `8010` against Postgres: `/me`, `POST /qc/records`, `/qc/backlog`, `/streams/hba1c-arch/chart`, `/qc/quarantine`, and `/audit` passed. Existing `bayesianqc.db` timestamp and size stayed unchanged.

### SQLite-To-Postgres Rehearsal
- `.venv/bin/python scripts/rehearse_sqlite_to_postgres.py`: passed; `revision_head` and schema smoke `alembic_version` both `20260703_0002`.
- SQLite-to-Postgres copy rehearsal against a temporary Postgres DB with `make migration-rehearse-postgres-copy`: passed; table counts matched, sequences OK, posterior checks OK. The current source `bayesianqc.db` has no QC records, so `streams_checked` was `0` for that source.
- Seeded-source copy and posterior-value parity are covered by `tests/test_migrations.py` under `BAYESIANQC_POSTGRES_TEST_URL`.

## Worktree Inclusion Note
This packet reviews the live worktree, not a staged commit. Several cutover files are currently untracked and must be included before any PR/commit, including `alembic.ini`, `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml`, `migrations/`, `scripts/rehearse_sqlite_to_postgres.py`, `tests/test_migrations.py`, and the new migration/readiness docs. Do not infer merge readiness from `git diff --stat` alone; use `git status --short` as well.

## Known Constraints
- The stale port `8010` process was stopped with `scripts/stop_demo.sh`; `scripts/run_demo.sh` now starts port `8010` with `BAYESIANQC_DB_URL` set to the local/dev Postgres URL.
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

=== GIT STATUS SHORT ===
 M .gitignore
 M AGENTS.md
 M CLAUDE.md
 M GEMINI.md
 M README.md
 M app/api_models.py
 M app/db.py
 M app/db_models.py
 M app/evaluations.py
 M app/main.py
 M app/migrations.py
 M app/models.py
 M app/rbac.py
 M app/storage.py
 M docs/ARCHITECTURE.md
 M frontend/package.json
 M frontend/src/App.vue
 M frontend/src/api/contracts.ts
 M frontend/src/api/schema.ts
 M frontend/src/components/AppLayout.vue
 M frontend/src/pages/Alerts.vue
 M frontend/src/pages/Analytes.vue
 M frontend/src/pages/Capas.vue
 M frontend/src/pages/ChartView.vue
 M frontend/src/pages/Events.vue
 M frontend/src/pages/Ingestion.vue
 M frontend/src/pages/Instruments.vue
 M frontend/src/pages/Investigations.vue
 M frontend/src/pages/Login.vue
 M frontend/src/pages/Methods.vue
 M frontend/src/pages/Streams.vue
 M frontend/src/router/index.ts
 M frontend/src/router/meta.d.ts
 M frontend/src/styles/global.css
 M requirements.txt
 M reviews/codex/latest.md
 M scripts/create_api_key.py
 M scripts/run_demo.sh
 M scripts/stop_demo.sh
 M tests/conftest.py
 M tests/test_ingestion.py
?? .github/
?? Makefile
?? TODO_REPO_CLEANUP.md
?? alembic.ini
?? app/routers/
?? app/security.py
?? app/services/
?? docker-compose.yml
?? docs/CHART_KIOSK_REVIEW.md
?? docs/LAB_READINESS.md
?? docs/MIGRATION_STRATEGY.md
?? docs/STANDARDS_FEATURE_ROADMAP.md
?? docs/TOOL_FLOW_DIAGRAM.html
?? docs/VALIDATION_PACKAGE.md
?? frontend/src/api/session.ts
?? frontend/src/pages/Audit.vue
?? frontend/src/pages/Backlog.vue
?? frontend/src/pages/ChartKiosk.vue
?? frontend/src/pages/Quarantine.vue
?? frontend/src/pages/ingestionWorkflow.ts
?? frontend/src/pages/kioskPanels.ts
?? migrations/
?? pyproject.toml
?? reviews/agy/
?? reviews/gemini/chart-kiosk-d86-review-2026-05-13-final.md
?? reviews/gemini/chart-kiosk-d86-review-2026-05-13-final2.md
?? reviews/gemini/chart-kiosk-d86-review-2026-05-13-followup.md
?? reviews/gemini/chart-kiosk-d86-review-2026-05-13.md
?? reviews/gemini/chart-kiosk-review-2026-05-13-final.md
?? reviews/gemini/chart-kiosk-review-2026-05-13-followup.md
?? reviews/gemini/chart-kiosk-review-2026-05-13.md
?? reviews/grok/
?? reviews/multi-agent/
?? samples/chart_kiosk_assets.json
?? samples/chart_kiosk_d86_events.json
?? samples/chart_kiosk_d86_priors.json
?? samples/chart_kiosk_d86_records.csv
?? samples/chart_kiosk_d86_streams.json
?? samples/chart_kiosk_events.json
?? samples/chart_kiosk_prior.json
?? samples/chart_kiosk_qc_records.csv
?? samples/chart_kiosk_refinery_assets.json
?? samples/chart_kiosk_refinery_events.json
?? samples/chart_kiosk_refinery_priors.json
?? samples/chart_kiosk_refinery_records.csv
?? samples/chart_kiosk_refinery_streams.json
?? samples/chart_kiosk_stream.json
?? scripts/load_chart_kiosk_suite.py
?? scripts/rehearse_sqlite_to_postgres.py
?? tests/test_chart_kiosk.py
?? tests/test_migrations.py
?? tests/test_qc_backlog.py
?? uv.lock

=== TARGETED DIFF ===
diff --git a/AGENTS.md b/AGENTS.md
index e8d0235..12cdc6c 100644
--- a/AGENTS.md
+++ b/AGENTS.md
@@ -11,6 +11,7 @@
 - Heavily-modified response (enforced): if modular splitting clearly improves maintainability, propose a split plan first; otherwise pause for user acknowledgement before committing any file that would exceed `400` LOC, and record the exception rationale in the handoff.
 - Typesafety rule (enforced): apply stack-appropriate strict typing in every change (strict TypeScript for TS, Python type hints + pyright/mypy where configured, ShellCheck/input validation for shell, explicit declarations for Fortran/C# where applicable).
 - Remote/push rule (enforced): do not change remotes or push destinations without explicit user confirmation; treat `origin` as canonical by default. This applies to human-in-the-loop agent actions and does not override already-approved CI automation.
+- Workspace fast-path rule (enforced): for trivial, self-contained requests that do not touch files, secrets, infrastructure, active project state, or prior context, answer directly and skip continuity-ledger reads/updates, broad repo scans, discovery docs, and second-agent review; for non-trivial workspace/repo/infra/follow-up work, read the relevant context first and update continuity only when state materially changes.
 <!-- GOVERNANCE_BASELINE_END -->

 ## Precedence
@@ -20,17 +21,22 @@
 - Project ID (portable): `BAYESIANQC`
 - Path (current environment): `/home/user/projects/BAYESIANQC`
 - Stack: FastAPI QC prototype; API on 8010; Vue/Vite UI in `frontend/` (dev port 5177).
-- Data: SQLite database at `./bayesianqc.db`.
+- Data: Postgres is the default local/dev database via Docker Compose on host port `54329`.
+  SQLite remains available only when explicitly configured for compatibility/import rehearsal.

 ## Common Commands (from README.md)
 - Create venv and install: `python -m venv .venv` then `pip install -r requirements.txt`.
-- Run API: `uvicorn app.main:app --reload --port 8010`.
+- Run API: `docker compose up -d postgres`, export
+  `BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc`,
+  export `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`, then run
+  `uvicorn app.main:app --reload --port 8010`.
 - Sample payload: `python scripts/post_sample_qc.py`.
-- Run tests: `pytest`.
+- Run tests: `pytest`; run the local/dev Postgres gate with `make check-postgres`.
 - Frontend dev (from `frontend/package.json`): `npm run dev` in `frontend/`.

 ## Notes
-- API requires `X-API-Key`; default local key: `local-dev-key` (admin) or set `BAYESIANQC_API_KEY`.
+- API requires `X-API-Key`; with `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`, the local admin key is
+  `local-dev-key`.
 - UI expects the API at `http://127.0.0.1:8010`.
  - UI dev server runs at `http://127.0.0.1:5177`.

diff --git a/README.md b/README.md
index bf5bc91..a15f0fc 100644
--- a/README.md
+++ b/README.md
@@ -14,10 +14,13 @@ Bayesian priors represent the expected in-control mean/variance for a QC stream.
    ```
 2. Run the FastAPI app:
    ```bash
+   docker compose up -d postgres
+   export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
+   export BAYESIANQC_SEED_LOCAL_DEV_KEY=1
    uvicorn app.main:app --reload --port 8010
    ```
-3. The app creates a local SQLite DB at `./bayesianqc.db` on first run.
-4. API calls require an `X-API-Key` header. Default local key: `local-dev-key` (admin) or set `BAYESIANQC_API_KEY`.
+3. The app applies Alembic migrations to Postgres on startup.
+4. API calls require an `X-API-Key` header. With `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`, the local admin key is `local-dev-key`; otherwise create keys with `scripts/create_api_key.py`.
 5. Open `http://127.0.0.1:8010/docs` or ingest QC data (manual or automated) against the seeded HbA1c stream using the `/qc/records` endpoint. The API returns frequentist signals (1-3s/2-2s/R-4s/4-1s/10x), Bayesian-style risk, disposition, duplicate detection, and an audit entry. Alerts are created for action/warning states.

 ## Sample payload helper
@@ -41,6 +44,33 @@ curl -X POST http://127.0.0.1:8010/qc/records/csv \
 ```bash
 python scripts/create_api_key.py --role qc_analyst --description "local tester"
 ```
+Stored API-key hashes use salted PBKDF2. Legacy SHA-256 key hashes are migrated after successful authentication.
+
+## Postgres dev database
+Postgres is the default local/dev runtime. The built-in default URL is:
+`postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc`.
+
+```bash
+docker compose up -d postgres
+export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
+export BAYESIANQC_SEED_LOCAL_DEV_KEY=1
+alembic upgrade head
+uvicorn app.main:app --reload --port 8010
+```
+`init_db()` also applies Alembic migrations automatically for non-SQLite URLs. There is no silent fallback to SQLite for normal app startup; if Postgres is unavailable, startup should fail visibly.
+See [Lab Readiness](docs/LAB_READINESS.md), [Validation Package](docs/VALIDATION_PACKAGE.md), and [Migration Strategy](docs/MIGRATION_STRATEGY.md) before any lab-like deployment.
+
+To rehearse the current schema and optional SQLite-to-Postgres copy path:
+```bash
+python scripts/rehearse_sqlite_to_postgres.py
+export POSTGRES_COPY_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc_disposable
+python scripts/rehearse_sqlite_to_postgres.py \
+  --postgres-url "$POSTGRES_COPY_URL" \
+  --copy-data \
+  --truncate-target
+```
+Only run the copy form against a disposable target; it truncates target rows when `--truncate-target` is present. The JSON output includes Alembic head/version checks, row-count parity, Postgres sequence checks, and posterior parameter recomputation.
+SQLite is retained only for explicit compatibility tests and SQLite-to-Postgres import rehearsal. Set `BAYESIANQC_DB_URL=sqlite:///...` deliberately when that path is being tested.

 ## Frontend UI (Vue + Element Plus)
 ```bash
@@ -53,11 +83,13 @@ Override the API base with `VITE_API_URL` in `frontend/.env.local`.
 Every UI page includes a Help button with page purpose and basic usage notes.
 Chart view now centers on the stream mean, shows color-coded 1/2/3 sigma bands using stream config limits, and uses a broken Y-axis when outliers exceed control limits (with an optional log-scale toggle).
 Click chart points to resolve them (exclude from stats) or reinstate them.
+The unattended chart kiosk is available at `http://127.0.0.1:5177/kiosk/charts`; the refinery demo kiosk is at `http://127.0.0.1:5177/kiosk/refinery` after loading `scripts/load_chart_kiosk_suite.py`.

 ## Endpoint map
 - `GET /` Landing page with links and basic usage.
 - `GET /docs` Interactive Swagger UI.
 - `GET /redoc` Reference docs.
+- `GET /me` Current role, API-key id, and permissions.
 - `POST /qc/records` Ingest a QC record (requires `X-API-Key`).
 - `POST /qc/records/csv` Ingest QC records from CSV (requires `X-API-Key`).
 - `PATCH /qc/records/{record_id}/resolution` Resolve/reinstate a QC record (requires `X-API-Key` + approve permission).
@@ -96,9 +128,16 @@ Click chart points to resolve them (exclude from stats) or reinstate them.
   ```bash
   pytest
   ```
+  This is the SQLite compatibility/regression suite unless a test explicitly sets a different database URL.
+- Run the local/dev Postgres gate:
+  ```bash
+  make check-postgres
+  ```
+  For the destructive copy rehearsal, create a disposable target database and run `make migration-rehearse-postgres-copy POSTGRES_COPY_URL=postgresql+psycopg://...`.

 ## Documents
 - [Software Requirements Specification](docs/SRS.md): Full, structured requirements including manual QC entry, workflow, and compliance expectations.
+- [Tool Flow Diagram](docs/TOOL_FLOW_DIAGRAM.html): Browser-openable end-user and technical flow diagram.

 ## Roadmap

diff --git a/app/db.py b/app/db.py
index 0764092..e39bfe7 100644
--- a/app/db.py
+++ b/app/db.py
@@ -2,23 +2,25 @@ from __future__ import annotations

 import os
 import sqlite3
-from collections.abc import AsyncIterator
+from collections.abc import Iterator
 from typing import Optional

 from sqlalchemy import event
 from sqlalchemy.engine import Engine
 from sqlmodel import Session, SQLModel, create_engine

-from app.migrations import run_sqlite_migrations
+from app.migrations import run_alembic_migrations, run_sqlite_migrations

 _ENGINE: Optional[Engine] = None
+_SQLITE_BUSY_TIMEOUT_MS = 5000
+DEFAULT_DB_URL = "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"


 def _build_engine() -> Engine:
-    db_url = os.getenv("BAYESIANQC_DB_URL", "sqlite:///./bayesianqc.db")
+    db_url = os.getenv("BAYESIANQC_DB_URL", DEFAULT_DB_URL)
     connect_args = {}
     if db_url.startswith("sqlite"):
-        connect_args = {"check_same_thread": False}
+        connect_args = {"check_same_thread": False, "timeout": _SQLITE_BUSY_TIMEOUT_MS / 1000}
     engine = create_engine(db_url, echo=False, connect_args=connect_args)
     if db_url.startswith("sqlite"):
         _configure_sqlite(engine)
@@ -31,18 +33,19 @@ def _configure_sqlite(engine: Engine) -> None:
         if isinstance(dbapi_connection, sqlite3.Connection):
             cursor = dbapi_connection.cursor()
             cursor.execute("PRAGMA foreign_keys=ON")
+            cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
             cursor.close()


 def get_engine() -> Engine:
     global _ENGINE
-    db_url = os.getenv("BAYESIANQC_DB_URL", "sqlite:///./bayesianqc.db")
+    db_url = os.getenv("BAYESIANQC_DB_URL", DEFAULT_DB_URL)
     if _ENGINE is None or str(_ENGINE.url) != db_url:
         _ENGINE = _build_engine()
     return _ENGINE


-async def get_session() -> AsyncIterator[Session]:
+def get_session() -> Iterator[Session]:
     engine = get_engine()
     with Session(engine, expire_on_commit=False) as session:
         yield session
@@ -50,5 +53,8 @@ async def get_session() -> AsyncIterator[Session]:

 def init_db() -> None:
     engine = get_engine()
-    SQLModel.metadata.create_all(engine)
-    run_sqlite_migrations(engine)
+    if str(engine.url).startswith("sqlite"):
+        SQLModel.metadata.create_all(engine)
+        run_sqlite_migrations(engine)
+        return
+    run_alembic_migrations(engine)
diff --git a/scripts/run_demo.sh b/scripts/run_demo.sh
index fd98e8a..ddf04b2 100755
--- a/scripts/run_demo.sh
+++ b/scripts/run_demo.sh
@@ -6,14 +6,20 @@ BACKEND_PID="${ROOT_DIR}/.demo-backend.pid"
 FRONTEND_PID="${ROOT_DIR}/.demo-frontend.pid"
 BACKEND_LOG="${ROOT_DIR}/uvicorn.log"
 FRONTEND_LOG="${ROOT_DIR}/frontend/vite.log"
+POSTGRES_URL="${BAYESIANQC_DB_URL:-postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc}"
+
+start_postgres() {
+  docker compose -f "${ROOT_DIR}/docker-compose.yml" up -d postgres
+}

 start_backend() {
   if [[ -f "${BACKEND_PID}" ]] && kill -0 "$(cat "${BACKEND_PID}")" 2>/dev/null; then
     echo "Backend already running (PID $(cat "${BACKEND_PID}"))."
     return
   fi
-  nohup "${ROOT_DIR}/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8010 \
-    > "${BACKEND_LOG}" 2>&1 &
+  env BAYESIANQC_DB_URL="${POSTGRES_URL}" BAYESIANQC_SEED_LOCAL_DEV_KEY=1 \
+    setsid "${ROOT_DIR}/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8010 \
+    > "${BACKEND_LOG}" 2>&1 < /dev/null &
   echo $! > "${BACKEND_PID}"
   echo "Backend started (PID $(cat "${BACKEND_PID}"))."
 }
@@ -23,11 +29,13 @@ start_frontend() {
     echo "Frontend already running (PID $(cat "${FRONTEND_PID}"))."
     return
   fi
-  (cd "${ROOT_DIR}/frontend" && nohup npm run dev -- --host 0.0.0.0 --port 5177 \
-    > "${FRONTEND_LOG}" 2>&1 & echo $! > "${FRONTEND_PID}")
+  setsid bash -lc "cd '${ROOT_DIR}/frontend' && exec npm run dev -- --host 0.0.0.0 --port 5177" \
+    > "${FRONTEND_LOG}" 2>&1 < /dev/null &
+  echo $! > "${FRONTEND_PID}"
   echo "Frontend started (PID $(cat "${FRONTEND_PID}"))."
 }

+start_postgres
 start_backend
 start_frontend

diff --git a/scripts/stop_demo.sh b/scripts/stop_demo.sh
index ea513bf..b9893a9 100755
--- a/scripts/stop_demo.sh
+++ b/scripts/stop_demo.sh
@@ -11,7 +11,7 @@ stop_pid() {
     local pid
     pid="$(cat "${pid_file}")"
     if kill -0 "${pid}" 2>/dev/null; then
-      kill "${pid}"
+      kill -- "-${pid}" 2>/dev/null || kill "${pid}"
       echo "Stopped process ${pid}."
     fi
     rm -f "${pid_file}"
@@ -20,3 +20,7 @@ stop_pid() {

 stop_pid "${FRONTEND_PID}"
 stop_pid "${BACKEND_PID}"
+
+if [[ "${BAYESIANQC_STOP_POSTGRES:-0}" == "1" ]]; then
+  docker compose -f "${ROOT_DIR}/docker-compose.yml" stop postgres
+fi
