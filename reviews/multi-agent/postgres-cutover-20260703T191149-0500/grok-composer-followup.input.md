Review the remediated BAYESIANQC local/dev Postgres cutover for docs, workflow clarity, and end-user/lab-operator cutover understanding. Findings first with P0/P1/P2 severity. Treat P0/P1 as blocking for local/dev unless explicitly scoped to shared-lab production. Verify prior blockers: validation wording, copy target clarity, AGENTS.md, runtime smoke on 8010, and production/lab boundary clarity. Do not mutate files.

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
- `docker compose up -d postgres`: passed; `bayesianqc-postgres-1` healthy.
- `BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc .venv/bin/alembic upgrade head`: passed, head `20260703_0002`.
- `.venv/bin/python scripts/rehearse_sqlite_to_postgres.py`: passed; `revision_head` and schema smoke `alembic_version` both `20260703_0002`.
- SQLite-to-Postgres copy rehearsal against temporary Postgres DB with `make migration-rehearse-postgres-copy`: passed; table counts matched, sequences OK, posterior checks OK. The current source `bayesianqc.db` has no QC records, so `streams_checked` was `0` for that source.
- `BAYESIANQC_POSTGRES_TEST_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc .venv/bin/python -m pytest tests/test_migrations.py -q`: `7 passed`.
- `make check-postgres`: passed; includes Compose Postgres, Alembic upgrade, Postgres migration tests, and Postgres rehearsal with posterior recomputation on the dev Postgres data.
- `.venv/bin/python -m pytest -q`: `33 passed, 4 skipped`.
- `.venv/bin/pyright`: `0 errors`.
- `.venv/bin/python -m ruff check app tests scripts`: passed.
- `npm --prefix frontend run check`: passed with the known Vite large chunk warning.
- `git diff --check`: passed.
- Anchored conflict marker scan `^(<<<<<<<|=======|>>>>>>>)`: no hits.
- Runtime smoke on port `8010` against Postgres: `/me`, `POST /qc/records`, `/qc/backlog`, `/streams/hba1c-arch/chart`, `/qc/quarantine`, and `/audit` passed. Existing `bayesianqc.db` timestamp and size stayed unchanged.

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

=== CURRENT GIT DIFF STAT ===
 .gitignore                            |   8 +
 AGENTS.md                             |  10 +-
 CLAUDE.md                             |   1 +
 GEMINI.md                             |   2 +
 README.md                             |  42 +-
 app/api_models.py                     |   5 +-
 app/db.py                             |  22 +-
 app/db_models.py                      |  84 +++-
 app/evaluations.py                    |   2 +-
 app/main.py                           | 731 +++++++++++++++-------------------
 app/migrations.py                     | 225 ++++++++++-
 app/models.py                         | 164 +++++++-
 app/rbac.py                           |  57 ++-
 app/storage.py                        |  92 ++++-
 docs/ARCHITECTURE.md                  |  10 +-
 frontend/package.json                 |   1 +
 frontend/src/App.vue                  |   7 +-
 frontend/src/api/contracts.ts         |  16 +
 frontend/src/api/schema.ts            | 583 ++++++++++++++++++++++++++-
 frontend/src/components/AppLayout.vue |  39 +-
 frontend/src/pages/Alerts.vue         |  23 +-
 frontend/src/pages/Analytes.vue       |   7 +-
 frontend/src/pages/Capas.vue          |  39 +-
 frontend/src/pages/ChartView.vue      | 255 ++++++++++--
 frontend/src/pages/Events.vue         |  19 +-
 frontend/src/pages/Ingestion.vue      | 441 ++++++++++++++------
 frontend/src/pages/Instruments.vue    |   7 +-
 frontend/src/pages/Investigations.vue |  17 +-
 frontend/src/pages/Login.vue          |  12 +-
 frontend/src/pages/Methods.vue        |   7 +-
 frontend/src/pages/Streams.vue        |   5 +-
 frontend/src/router/index.ts          |  51 ++-
 frontend/src/router/meta.d.ts         |   2 +-
 frontend/src/styles/global.css        | 145 ++++++-
 requirements.txt                      |   2 +
 reviews/codex/latest.md               |  37 ++
 scripts/create_api_key.py             |   7 +-
 scripts/run_demo.sh                   |  16 +-
 scripts/stop_demo.sh                  |   6 +-
 tests/conftest.py                     |   5 +
 tests/test_ingestion.py               | 432 +++++++++++++++++++-
 41 files changed, 2945 insertions(+), 691 deletions(-)

=== TARGETED DIFF ===
diff --git a/AGENTS.md b/AGENTS.md
index e8d0235..8ae4b20 100644
--- a/AGENTS.md
+++ b/AGENTS.md
@@ -11,6 +11,7 @@
 - Heavily-modified response (enforced): if modular splitting clearly improves maintainability, propose a split plan first; otherwise pause for user acknowledgement before committing any file that would exceed `400` LOC, and record the exception rationale in the handoff.
 - Typesafety rule (enforced): apply stack-appropriate strict typing in every change (strict TypeScript for TS, Python type hints + pyright/mypy where configured, ShellCheck/input validation for shell, explicit declarations for Fortran/C# where applicable).
 - Remote/push rule (enforced): do not change remotes or push destinations without explicit user confirmation; treat `origin` as canonical by default. This applies to human-in-the-loop agent actions and does not override already-approved CI automation.
+- Workspace fast-path rule (enforced): for trivial, self-contained requests that do not touch files, secrets, infrastructure, active project state, or prior context, answer directly and skip continuity-ledger reads/updates, broad repo scans, discovery docs, and second-agent review; for non-trivial workspace/repo/infra/follow-up work, read the relevant context first and update continuity only when state materially changes.
 <!-- GOVERNANCE_BASELINE_END -->

 ## Precedence
@@ -20,13 +21,16 @@
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
+  then run `uvicorn app.main:app --reload --port 8010`.
 - Sample payload: `python scripts/post_sample_qc.py`.
-- Run tests: `pytest`.
+- Run tests: `pytest`; run the local/dev Postgres gate with `make check-postgres`.
 - Frontend dev (from `frontend/package.json`): `npm run dev` in `frontend/`.

 ## Notes
diff --git a/README.md b/README.md
index bf5bc91..7c76245 100644
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
@@ -41,6 +44,32 @@ curl -X POST http://127.0.0.1:8010/qc/records/csv \
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
+python scripts/rehearse_sqlite_to_postgres.py \
+  --postgres-url "$POSTGRES_COPY_URL" \
+  --copy-data \
+  --truncate-target
+```
+Only run the copy form against a disposable target; it truncates target rows when `--truncate-target` is present. The JSON output includes Alembic head/version checks, row-count parity, Postgres sequence checks, and posterior parameter recomputation.
+SQLite is retained only for explicit compatibility tests and SQLite-to-Postgres import rehearsal. Set `BAYESIANQC_DB_URL=sqlite:///...` deliberately when that path is being tested.

 ## Frontend UI (Vue + Element Plus)
 ```bash
@@ -53,11 +82,13 @@ Override the API base with `VITE_API_URL` in `frontend/.env.local`.
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
@@ -96,9 +127,16 @@ Click chart points to resolve them (exclude from stats) or reinstate them.
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
