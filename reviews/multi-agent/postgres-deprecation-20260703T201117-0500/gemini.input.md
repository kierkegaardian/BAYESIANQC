# Git Status

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
 M app/timeutils.py
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

# Diff Stat

 .gitignore                            |   8 +
 AGENTS.md                             |  15 +-
 CLAUDE.md                             |   1 +
 GEMINI.md                             |   2 +
 README.md                             |  51 ++-
 app/api_models.py                     |   5 +-
 app/db.py                             |  45 +--
 app/db_models.py                      |  84 +++-
 app/evaluations.py                    |   2 +-
 app/main.py                           | 731 +++++++++++++++-------------------
 app/migrations.py                     | 117 +-----
 app/models.py                         | 164 +++++++-
 app/rbac.py                           |  57 ++-
 app/storage.py                        |  91 ++++-
 app/timeutils.py                      |   3 +-
 docs/ARCHITECTURE.md                  |  37 +-
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
 scripts/run_demo.sh                   |  29 +-
 scripts/stop_demo.sh                  |   6 +-
 tests/conftest.py                     |  82 +++-
 tests/test_ingestion.py               | 432 +++++++++++++++++++-
 42 files changed, 2849 insertions(+), 835 deletions(-)

# Review Packet README

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

# Validation Receipt

# Validation Receipt

## Static, Type, Frontend, And Test Gates

- `.venv/bin/ruff check app tests scripts`: passed.
- `.venv/bin/pyright`: passed with 0 errors.
- `npm --prefix frontend run check`: passed. Vite emitted the existing large chunk warning.
- `git diff --check`: passed.
- `rg -n "^(<<<<<<<|=======|>>>>>>>)" .`: no conflict markers found.
- `bash -n scripts/run_demo.sh scripts/stop_demo.sh`: passed.
- `.venv/bin/pytest -q`: passed, 38 tests.

## Postgres And Migration Gates

- `docker compose ps postgres`: Postgres container healthy on local port 54329.
- `make check-postgres`: passed.
- `tests/test_migrations.py`: 8 tests passed inside `make check-postgres`.
- Alembic upgraded Postgres to `20260703_0002`.
- Rehearsal JSON reported `revision_head: 20260703_0002` and schema `alembic_version: 20260703_0002`.
- Rehearsal sequence checks returned status `ok`.
- Rehearsal posterior checks returned `ok: true`.
- Guarded copy rehearsal with `POSTGRES_COPY_URL` containing `disposable` passed with copied counts matching source counts and target sequence checks OK.
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

## Residual Validation Risk

- Review packet has not yet been approved by the requested independent reviewers at the time this file was created.
- The default local database now contains smoke/demo rows from validation.

# Selected Tracked Diffs

diff --git a/AGENTS.md b/AGENTS.md
index e8d0235..b5a548c 100644
--- a/AGENTS.md
+++ b/AGENTS.md
@@ -11,6 +11,7 @@
 - Heavily-modified response (enforced): if modular splitting clearly improves maintainability, propose a split plan first; otherwise pause for user acknowledgement before committing any file that would exceed `400` LOC, and record the exception rationale in the handoff.
 - Typesafety rule (enforced): apply stack-appropriate strict typing in every change (strict TypeScript for TS, Python type hints + pyright/mypy where configured, ShellCheck/input validation for shell, explicit declarations for Fortran/C# where applicable).
 - Remote/push rule (enforced): do not change remotes or push destinations without explicit user confirmation; treat `origin` as canonical by default. This applies to human-in-the-loop agent actions and does not override already-approved CI automation.
+- Workspace fast-path rule (enforced): for trivial, self-contained requests that do not touch files, secrets, infrastructure, active project state, or prior context, answer directly and skip continuity-ledger reads/updates, broad repo scans, discovery docs, and second-agent review; for non-trivial workspace/repo/infra/follow-up work, read the relevant context first and update continuity only when state materially changes.
 <!-- GOVERNANCE_BASELINE_END -->

 ## Precedence
@@ -20,17 +21,23 @@
 - Project ID (portable): `BAYESIANQC`
 - Path (current environment): `/home/user/projects/BAYESIANQC`
 - Stack: FastAPI QC prototype; API on 8010; Vue/Vite UI in `frontend/` (dev port 5177).
-- Data: SQLite database at `./bayesianqc.db`.
+- Data: Postgres is the default local/dev database via Docker Compose on host port `54329`.
+  Legacy SQLite databases are supported only as import inputs, never as app runtime databases.

 ## Common Commands (from README.md)
 - Create venv and install: `python -m venv .venv` then `pip install -r requirements.txt`.
-- Run API: `uvicorn app.main:app --reload --port 8010`.
+- Run API: `docker compose up -d postgres`, export
+  `BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc`,
+  export `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`, then run
+  `uvicorn app.main:app --reload --port 8010`.
 - Sample payload: `python scripts/post_sample_qc.py`.
-- Run tests: `pytest`.
+- Run tests: `pytest`; the test harness creates a disposable Postgres database from
+  `BAYESIANQC_POSTGRES_TEST_URL` or the local Compose URL.
 - Frontend dev (from `frontend/package.json`): `npm run dev` in `frontend/`.

 ## Notes
-- API requires `X-API-Key`; default local key: `local-dev-key` (admin) or set `BAYESIANQC_API_KEY`.
+- API requires `X-API-Key`; with `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`, the local admin key is
+  `local-dev-key`.
 - UI expects the API at `http://127.0.0.1:8010`.
  - UI dev server runs at `http://127.0.0.1:5177`.

diff --git a/README.md b/README.md
index bf5bc91..13d226a 100644
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
@@ -41,6 +44,38 @@ curl -X POST http://127.0.0.1:8010/qc/records/csv \
 ```bash
 python scripts/create_api_key.py --role qc_analyst --description "local tester"
 ```
+Stored API-key hashes use salted PBKDF2. Legacy SHA-256 key hashes are migrated after successful authentication.
+
+## Postgres dev database
+Postgres is the only supported app runtime. The built-in default URL is:
+`postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc`.
+
+```bash
+docker compose up -d postgres
+export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
+export BAYESIANQC_SEED_LOCAL_DEV_KEY=1
+uvicorn app.main:app --reload --port 8010
+```
+`init_db()` applies Alembic migrations automatically. The app rejects `sqlite://` URLs at startup; legacy SQLite files are import sources only.
+See [Lab Readiness](docs/LAB_READINESS.md), [Validation Package](docs/VALIDATION_PACKAGE.md), and [Migration Strategy](docs/MIGRATION_STRATEGY.md) before any lab-like deployment.
+
+To rehearse the current Postgres schema:
+```bash
+python scripts/rehearse_sqlite_to_postgres.py --postgres-url "$BAYESIANQC_DB_URL"
+```
+
+For a legacy SQLite import rehearsal only, create a disposable target and copy into it:
+```bash
+docker exec bayesianqc-postgres-1 dropdb -U bayesianqc --if-exists bayesianqc_disposable
+docker exec bayesianqc-postgres-1 createdb -U bayesianqc bayesianqc_disposable
+export POSTGRES_COPY_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc_disposable
+python scripts/rehearse_sqlite_to_postgres.py \
+  --postgres-url "$POSTGRES_COPY_URL" \
+  --copy-data \
+  --truncate-target
+```
+Only run the copy form against a disposable target; it truncates target rows when `--truncate-target` is present. The JSON output includes Alembic head/version checks, row-count parity, Postgres sequence checks, and posterior parameter recomputation.
+Do not set `BAYESIANQC_DB_URL` to SQLite; the app will fail fast.

 ## Frontend UI (Vue + Element Plus)
 ```bash
@@ -53,11 +88,13 @@ Override the API base with `VITE_API_URL` in `frontend/.env.local`.
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
@@ -92,13 +129,21 @@ Click chart points to resolve them (exclude from stats) or reinstate them.

 ## Testing
 - Install dependencies with `pip install -r requirements.txt` (inside your virtualenv).
-- Run the automated checks:
+- Start Postgres, then run the automated checks:
   ```bash
+  docker compose up -d postgres
   pytest
   ```
+  The test harness creates a disposable Postgres database from `BAYESIANQC_POSTGRES_TEST_URL` or the local Compose URL.
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
index 0764092..bd0bd5a 100644
--- a/app/db.py
+++ b/app/db.py
@@ -1,48 +1,44 @@
 from __future__ import annotations

 import os
-import sqlite3
-from collections.abc import AsyncIterator
+from collections.abc import Iterator
 from typing import Optional

-from sqlalchemy import event
 from sqlalchemy.engine import Engine
-from sqlmodel import Session, SQLModel, create_engine
+from sqlmodel import Session, create_engine

-from app.migrations import run_sqlite_migrations
+from app.migrations import run_alembic_migrations

 _ENGINE: Optional[Engine] = None
+DEFAULT_DB_URL = "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"


-def _build_engine() -> Engine:
-    db_url = os.getenv("BAYESIANQC_DB_URL", "sqlite:///./bayesianqc.db")
-    connect_args = {}
-    if db_url.startswith("sqlite"):
-        connect_args = {"check_same_thread": False}
-    engine = create_engine(db_url, echo=False, connect_args=connect_args)
+def _database_url() -> str:
+    db_url = os.getenv("BAYESIANQC_DB_URL", DEFAULT_DB_URL)
     if db_url.startswith("sqlite"):
-        _configure_sqlite(engine)
-    return engine
+        raise RuntimeError("BAYESIANQC app runtime requires Postgres; SQLite is legacy-import input only.")
+    if not db_url.startswith("postgresql"):
+        raise RuntimeError("BAYESIANQC app runtime requires a postgresql+psycopg SQLAlchemy URL.")
+    return db_url
+
+
+def _build_engine() -> Engine:
+    return create_engine(_database_url(), echo=False)


-def _configure_sqlite(engine: Engine) -> None:
-    @event.listens_for(engine, "connect")
-    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
-        if isinstance(dbapi_connection, sqlite3.Connection):
-            cursor = dbapi_connection.cursor()
-            cursor.execute("PRAGMA foreign_keys=ON")
-            cursor.close()
+def _engine_url(engine: Engine) -> str:
+    return engine.url.render_as_string(hide_password=False)


 def get_engine() -> Engine:
     global _ENGINE
-    db_url = os.getenv("BAYESIANQC_DB_URL", "sqlite:///./bayesianqc.db")
-    if _ENGINE is None or str(_ENGINE.url) != db_url:
+    db_url = _database_url()
+    if _ENGINE is None or _engine_url(_ENGINE) != db_url:
         _ENGINE = _build_engine()
     return _ENGINE


-async def get_session() -> AsyncIterator[Session]:
+def get_session() -> Iterator[Session]:
     engine = get_engine()
     with Session(engine, expire_on_commit=False) as session:
         yield session
@@ -50,5 +46,4 @@ async def get_session() -> AsyncIterator[Session]:

 def init_db() -> None:
     engine = get_engine()
-    SQLModel.metadata.create_all(engine)
-    run_sqlite_migrations(engine)
+    run_alembic_migrations(engine)
diff --git a/app/migrations.py b/app/migrations.py
index 5f15694..21dbbe8 100644
--- a/app/migrations.py
+++ b/app/migrations.py
@@ -1,112 +1,23 @@
 from __future__ import annotations

-from typing import Optional
+from pathlib import Path

+from alembic import command
+from alembic.config import Config
 from sqlalchemy.engine import Engine

-SQLITE_SCHEMA_VERSION = 4
-_DEFAULT_BUSY_TIMEOUT_MS = 5000
+_PROJECT_ROOT = Path(__file__).resolve().parents[1]


-def _sqlite_user_version(cursor) -> int:
-    cursor.execute("PRAGMA user_version")
-    row = cursor.fetchone()
-    if not row:
-        return 0
-    return int(row[0] or 0)
+def _alembic_config(db_url: str) -> Config:
+    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
+    config.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
+    config.set_main_option("sqlalchemy.url", db_url)
+    return config


-def _sqlite_set_user_version(cursor, version: int) -> None:
-    cursor.execute(f"PRAGMA user_version = {int(version)}")
-
-
-def _sqlite_table_columns(cursor, table_name: str) -> set[str]:
-    cursor.execute(f"PRAGMA table_info({table_name})")
-    return {str(row[1]) for row in cursor.fetchall()}
-
-
-def _sqlite_add_column_if_missing(cursor, table_name: str, column_name: str, column_sql: str) -> None:
-    columns = _sqlite_table_columns(cursor, table_name)
-    if column_name in columns:
-        return
-    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")
-
-
-def _migrate_0_to_1(cursor) -> None:
-    # QC record resolution/exclusion fields.
-    _sqlite_add_column_if_missing(cursor, "qcrecord", "include_in_stats", "include_in_stats BOOLEAN DEFAULT 1")
-    _sqlite_add_column_if_missing(cursor, "qcrecord", "resolved_at", "resolved_at DATETIME")
-    _sqlite_add_column_if_missing(cursor, "qcrecord", "resolved_by", "resolved_by VARCHAR")
-    _sqlite_add_column_if_missing(cursor, "qcrecord", "resolved_reason", "resolved_reason VARCHAR")
-    cursor.execute("UPDATE qcrecord SET include_in_stats = 1 WHERE include_in_stats IS NULL")
-
-
-def _migrate_1_to_2(cursor) -> None:
-    # PosteriorState metadata and streaks.
-    _sqlite_add_column_if_missing(cursor, "posteriorstate", "prior_id", "prior_id INTEGER")
-    _sqlite_add_column_if_missing(cursor, "posteriorstate", "config_id", "config_id INTEGER")
-    _sqlite_add_column_if_missing(cursor, "posteriorstate", "warn_streak", "warn_streak INTEGER DEFAULT 0")
-    _sqlite_add_column_if_missing(cursor, "posteriorstate", "hold_streak", "hold_streak INTEGER DEFAULT 0")
-    cursor.execute("UPDATE posteriorstate SET warn_streak = 0 WHERE warn_streak IS NULL")
-    cursor.execute("UPDATE posteriorstate SET hold_streak = 0 WHERE hold_streak IS NULL")
-
-
-def _migrate_2_to_3(cursor) -> None:
-    # StreamConfig Bayesian policy fields.
-    _sqlite_add_column_if_missing(cursor, "streamconfig", "bayes_warn_prob_threshold", "bayes_warn_prob_threshold FLOAT")
-    _sqlite_add_column_if_missing(cursor, "streamconfig", "bayes_warn_consecutive", "bayes_warn_consecutive INTEGER")
-    _sqlite_add_column_if_missing(cursor, "streamconfig", "bayes_hold_prob_threshold", "bayes_hold_prob_threshold FLOAT")
-    _sqlite_add_column_if_missing(cursor, "streamconfig", "bayes_hold_consecutive", "bayes_hold_consecutive INTEGER")
-    # Intentionally do not backfill defaults here; leaving NULL makes misconfiguration visible,
-    # and the app already has backwards-compatible fallbacks.
-
-
-def _migrate_3_to_4(cursor) -> None:
-    # Persisted per-record evaluations for read-mostly charts.
-    _sqlite_add_column_if_missing(cursor, "qcrecord", "signals", "signals JSON")
-    _sqlite_add_column_if_missing(cursor, "qcrecord", "bayesian_risk", "bayesian_risk JSON")
-    _sqlite_add_column_if_missing(cursor, "qcrecord", "disposition", "disposition VARCHAR")
-
-
-def run_sqlite_migrations(engine: Engine, *, target_version: Optional[int] = None) -> None:
-    if not str(engine.url).startswith("sqlite"):
-        return
-
-    desired_version = SQLITE_SCHEMA_VERSION if target_version is None else int(target_version)
-    if desired_version < 0:
-        raise ValueError("target_version must be >= 0")
-
-    connection = engine.raw_connection()
-    cursor = connection.cursor()
-    try:
-        # Allow migrations to wait briefly if another process is touching the DB at startup.
-        cursor.execute(f"PRAGMA busy_timeout = {_DEFAULT_BUSY_TIMEOUT_MS}")
-        while True:
-            # SQLite doesn't support row-level locks; take a write lock for schema changes.
-            cursor.execute("BEGIN IMMEDIATE")
-            try:
-                current = _sqlite_user_version(cursor)
-                if current >= desired_version:
-                    connection.commit()
-                    return
-
-                next_version = current + 1
-                if current == 0:
-                    _migrate_0_to_1(cursor)
-                elif current == 1:
-                    _migrate_1_to_2(cursor)
-                elif current == 2:
-                    _migrate_2_to_3(cursor)
-                elif current == 3:
-                    _migrate_3_to_4(cursor)
-                else:
-                    raise RuntimeError(f"Unknown sqlite schema version {current}")
-
-                _sqlite_set_user_version(cursor, next_version)
-                connection.commit()
-            except Exception:
-                connection.rollback()
-                raise
-    finally:
-        cursor.close()
-        connection.close()
+def run_alembic_migrations(engine: Engine, *, revision: str = "head") -> None:
+    config = _alembic_config(engine.url.render_as_string(hide_password=False))
+    with engine.begin() as connection:
+        config.attributes["connection"] = connection
+        command.upgrade(config, revision)
diff --git a/app/storage.py b/app/storage.py
index 41e7afe..afc2ef0 100644
--- a/app/storage.py
+++ b/app/storage.py
@@ -1,9 +1,10 @@
 from __future__ import annotations

-import hashlib
+import os
 from datetime import datetime, timezone
 from typing import Optional, Tuple

+from sqlalchemy import or_
 from sqlmodel import Session, col, select

 from app.db_models import (
@@ -30,6 +31,7 @@ from app.models import (
     Role,
     StreamConfigIn,
 )
+from app.security import api_key_hash_needs_migration, api_key_lookup_hash, hash_api_key, legacy_sha256_hash, verify_api_key
 from app.stats import sample_mean_sd


@@ -37,6 +39,13 @@ def utcnow() -> datetime:
     return datetime.now(timezone.utc)


+def _seed_local_dev_key_enabled() -> bool:
+    value = os.getenv("BAYESIANQC_SEED_LOCAL_DEV_KEY")
+    if value is None:
+        return False
+    return value.strip().lower() in {"1", "true", "yes", "on"}
+
+
 def seed_defaults(session: Session) -> None:
     instrument = session.exec(select(Instrument).where(Instrument.name == "Architect")).first()
     if not instrument:
@@ -127,20 +136,49 @@ def seed_defaults(session: Session) -> None:
         session.add(prior)
         session.commit()

-    default_key = "local-dev-key"
-    key_hash = hashlib.sha256(default_key.encode("utf-8")).hexdigest()
-    api_key = session.exec(select(ApiKey).where(ApiKey.key_hash == key_hash)).first()
-    if api_key:
-        if api_key.role != Role.ADMIN:
+    if _seed_local_dev_key_enabled():
+        default_key = "local-dev-key"
+        lookup_hash = api_key_lookup_hash(default_key)
+        legacy_hash = legacy_sha256_hash(default_key)
+        api_key = session.exec(
+            select(ApiKey).where(
+                col(ApiKey.active) == True,
+                or_(col(ApiKey.key_lookup_hash) == lookup_hash, col(ApiKey.key_hash) == legacy_hash),
+            )
+        ).first()
+        if api_key is None:
+            api_key = session.exec(
+                select(ApiKey).where(col(ApiKey.active) == True, ApiKey.description == "local dev key")
+            ).first()
+            if api_key is not None and not verify_api_key(default_key, api_key.key_hash):
+                api_key = None
+        if api_key:
+            if api_key_hash_needs_migration(api_key.key_hash):
+                api_key.key_hash = hash_api_key(default_key)
+            api_key.key_lookup_hash = lookup_hash
             api_key.role = Role.ADMIN
+            api_key.description = api_key.description or "local dev key"
             session.add(api_key)
             session.commit()
-    else:
-        session.add(ApiKey(key_hash=key_hash, role=Role.ADMIN, description="local dev key"))
-        session.commit()
+        else:
+            session.add(
+                ApiKey(
+                    key_hash=hash_api_key(default_key),
+                    key_lookup_hash=lookup_hash,
+                    role=Role.ADMIN,
+                    description="local dev key",
+                )
+            )
+            session.commit()


-def create_stream_config(session: Session, payload: StreamConfigIn, created_by: str) -> StreamConfig:
+def create_stream_config(
+    session: Session,
+    payload: StreamConfigIn,
+    created_by: str,
+    *,
+    commit: bool = True,
+) -> StreamConfig:
     current_version = session.exec(
         select(StreamConfig.version)
         .where(StreamConfig.stream_id == payload.stream_id)
@@ -179,7 +217,10 @@ def create_stream_config(session: Session, payload: StreamConfigIn, created_by:
         created_by=created_by,
     )
     session.add(config)
-    session.commit()
+    if commit:
+        session.commit()
+    else:
+        session.flush()
     session.refresh(config)
     return config

@@ -209,7 +250,14 @@ def list_stream_configs(session: Session, stream_id: str) -> list[StreamConfig]:
     )


-def create_prior_config(session: Session, stream_id: str, payload: PriorConfigIn, created_by: str) -> PriorConfig:
+def create_prior_config(
+    session: Session,
+    stream_id: str,
+    payload: PriorConfigIn,
+    created_by: str,
+    *,
+    commit: bool = True,
+) -> PriorConfig:
     current_version = session.exec(
         select(PriorConfig.version)
         .where(PriorConfig.stream_id == stream_id)
@@ -227,7 +275,10 @@ def create_prior_config(session: Session, stream_id: str, payload: PriorConfigIn
         created_by=created_by,
     )
     session.add(config)
-    session.commit()
+    if commit:
+        session.commit()
+    else:
+        session.flush()
     session.refresh(config)
     return config

@@ -329,10 +380,24 @@ def record_audit(
     after: Optional[dict],
     reason: Optional[str],
     *,
+    actor_role: Optional[Role] = None,
+    api_key_id: Optional[int] = None,
     commit: bool = True,
 ) -> AuditEntry:
+    if actor_role is None:
+        role_value = actor.split(":key-", 1)[0]
+        try:
+            actor_role = Role(role_value)
+        except ValueError:
+            actor_role = None
+    if api_key_id is None and ":key-" in actor:
+        _, key_id_text = actor.rsplit(":key-", 1)
+        if key_id_text.isdigit():
+            api_key_id = int(key_id_text)
     entry = AuditEntry(
         actor=actor,
+        actor_role=actor_role,
+        api_key_id=api_key_id,
         action=action,
         entity_type=entity_type,
         entity_id=entity_id,
diff --git a/app/timeutils.py b/app/timeutils.py
index 23c73dd..474237b 100644
--- a/app/timeutils.py
+++ b/app/timeutils.py
@@ -7,9 +7,8 @@ def as_utc(value: datetime) -> datetime:
     """
     Normalize datetimes for safe comparison.

-    SQLite commonly returns naive datetimes; we treat them as UTC.
+    Legacy imports and some driver paths can return naive datetimes; treat them as UTC.
     """
     if value.tzinfo is None:
         return value.replace(tzinfo=timezone.utc)
     return value.astimezone(timezone.utc)
-
diff --git a/docs/ARCHITECTURE.md b/docs/ARCHITECTURE.md
index 623e415..dede748 100644
--- a/docs/ARCHITECTURE.md
+++ b/docs/ARCHITECTURE.md
@@ -8,9 +8,9 @@ Goals
 - Isolate statistical logic so you can **refactor queries / swap databases** without rewriting QC math.
 - Make charts **read-mostly** at scale by persisting per-record evaluations.

-Non-Goals (for now)
+Historical Non-Goals
 - Full DDD rewrite.
-- Introducing a large migration framework (e.g., Alembic) before Postgres is actually in use.
+- Alembic is part of the active Postgres persistence boundary.

 ## Current Shape (Problems)
 - Query logic and writes are spread across endpoints (`app/main.py`), “storage” helpers (`app/storage.py`),
@@ -131,48 +131,43 @@ Operational policy
 - Reprocess proactively on mutations (resolution/config/prior) and on out-of-order ingestion.
 - Optional: expose an explicit maintenance endpoint later (`POST /streams/{id}/reprocess`) for operators.

-## SQLite -> Postgres Migration Plan (Safe)
+## Postgres Persistence And Legacy Import

-### Phase 0: Make the App DB-Agnostic (Now)
-- Ensure every DB call is behind repos/services.
-- Avoid SQLite-specific SQL in business logic.
-
-### Phase 1: Add Postgres as a Dev/CI Target
-- Add a `docker-compose.yml` for Postgres (dev only).
-- Teach the app to run against `BAYESIANQC_DB_URL=postgresql+psycopg://...`.
+### Current Runtime
+- `docker-compose.yml` provides Postgres and `BAYESIANQC_DB_URL=postgresql+psycopg://...` is the documented default runtime path.
+- SQLite is not a supported app runtime. Legacy SQLite files are only supported as one-way import sources.
+- The test harness creates disposable Postgres databases from `BAYESIANQC_POSTGRES_TEST_URL` or the local Compose URL.
 - Add indexes you will need immediately:
   - `qcrecord (stream_id, timestamp)`
   - `posteriorstate (stream_id)` unique
   - `alertrecord (stream_id, created_at)` (and maybe `qc_record_id`)

-### Phase 2: Introduce Real Migrations
-- When Postgres is introduced, switch from `PRAGMA user_version` scripts to Alembic (or similar).
+### Migrations
+- Alembic is the only app migration path.
 - Use explicit, versioned migrations for:
   - JSON -> JSONB
   - constraints (unique indexes, NOT NULL where appropriate)
   - foreign keys and cascade policies

-### Phase 3: Data Migration (SQLite -> Postgres)
+### Legacy Import
 Safety principles
 - Freeze writes during the cutover (short maintenance window).
 - Migrate schema first, then data, then verify.

 Steps
-1. Deploy code that can talk to Postgres (but still uses SQLite in prod).
-2. Create Postgres schema via migrations.
-3. Export SQLite tables:
+1. Create Postgres schema via migrations.
+2. Export legacy SQLite tables:
    - simplest: `sqlite3 bayesianqc.db .dump` is not ideal for types
    - better: export per-table CSV with headers, then import with `COPY`
    - alternative: `pgloader` if you want speed and can validate the mapping
-4. Import into Postgres.
-5. Verification checks:
+3. Import into Postgres.
+4. Verification checks:
    - row counts per table
    - spot-check streams: recompute `PosteriorState` from `QCRecord` history and compare
    - verify `idempotency_key` uniqueness and alert linkage integrity
-6. Switch `BAYESIANQC_DB_URL` to Postgres and restart.
-7. Post-cutover: run a full `reprocess_stream_evaluations` per stream once to ensure cached evaluations align.
+5. Post-import: run a full `reprocess_stream_evaluations` per stream once to ensure cached evaluations align.

-### Phase 4: Concurrency Correctness (Postgres Benefits)
+### Concurrency Correctness
 - Fix the `PosteriorState` lost-update race by locking:
   - `SELECT posteriorstate ... FOR UPDATE` inside the ingestion transaction.
 - Optionally add optimistic concurrency:
diff --git a/scripts/run_demo.sh b/scripts/run_demo.sh
index fd98e8a..9da5563 100755
--- a/scripts/run_demo.sh
+++ b/scripts/run_demo.sh
@@ -6,14 +6,33 @@ BACKEND_PID="${ROOT_DIR}/.demo-backend.pid"
 FRONTEND_PID="${ROOT_DIR}/.demo-frontend.pid"
 BACKEND_LOG="${ROOT_DIR}/uvicorn.log"
 FRONTEND_LOG="${ROOT_DIR}/frontend/vite.log"
+POSTGRES_URL="${BAYESIANQC_DB_URL:-postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc}"
+
+start_postgres() {
+  docker compose -f "${ROOT_DIR}/docker-compose.yml" up -d postgres
+  wait_for_postgres
+}
+
+wait_for_postgres() {
+  for _ in {1..40}; do
+    if docker compose -f "${ROOT_DIR}/docker-compose.yml" exec -T postgres \
+      pg_isready -U bayesianqc -d bayesianqc >/dev/null 2>&1; then
+      return
+    fi
+    sleep 1
+  done
+  echo "Postgres did not become ready in time." >&2
+  exit 1
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
@@ -23,11 +42,13 @@ start_frontend() {
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
diff --git a/tests/conftest.py b/tests/conftest.py
index 41534ae..55a568d 100644
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -3,14 +3,78 @@ import pathlib
 import sys

 import pytest
+from sqlalchemy import create_engine, text
+from sqlalchemy.engine import make_url
 from sqlmodel import Session, delete

 ROOT = pathlib.Path(__file__).resolve().parents[1]
 if str(ROOT) not in sys.path:
     sys.path.insert(0, str(ROOT))

-TEST_DB_PATH = pathlib.Path("/tmp/bayesianqc_test.db")
-os.environ.setdefault("BAYESIANQC_DB_URL", f"sqlite:///{TEST_DB_PATH}")
+DEFAULT_TEST_BASE_URL = "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"
+_TEST_DATABASE_NAME = f"bayesianqc_pytest_{os.getpid()}"
+_TEST_DATABASE_CREATED = False
+_BASE_POSTGRES_URL: str | None = None
+
+
+def _postgres_base_url() -> str:
+    global _BASE_POSTGRES_URL
+    if _BASE_POSTGRES_URL is not None:
+        return _BASE_POSTGRES_URL
+    value = (
+        os.environ.get("BAYESIANQC_POSTGRES_TEST_URL")
+        or os.environ.get("BAYESIANQC_DB_URL")
+        or DEFAULT_TEST_BASE_URL
+    )
+    if value.startswith("sqlite"):
+        raise RuntimeError("Tests are Postgres-only; set BAYESIANQC_POSTGRES_TEST_URL to a Postgres URL.")
+    if not value.startswith("postgresql"):
+        raise RuntimeError("BAYESIANQC tests require a postgresql+psycopg SQLAlchemy URL.")
+    _BASE_POSTGRES_URL = value
+    return value
+
+
+def _test_database_url() -> str:
+    base = make_url(_postgres_base_url())
+    return base.set(database=_TEST_DATABASE_NAME).render_as_string(hide_password=False)
+
+
+def _maintenance_url() -> str:
+    return make_url(_postgres_base_url()).set(database="postgres").render_as_string(hide_password=False)
+
+
+def _ensure_test_database() -> None:
+    global _TEST_DATABASE_CREATED
+    if _TEST_DATABASE_CREATED:
+        return
+    admin_engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
+    with admin_engine.connect() as connection:
+        connection.execute(text(f'DROP DATABASE IF EXISTS "{_TEST_DATABASE_NAME}"'))
+        connection.execute(text(f'CREATE DATABASE "{_TEST_DATABASE_NAME}"'))
+    admin_engine.dispose()
+    _TEST_DATABASE_CREATED = True
+
+
+def _drop_test_database() -> None:
+    if not _TEST_DATABASE_CREATED:
+        return
+    admin_engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
+    with admin_engine.connect() as connection:
+        connection.execute(
+            text(
+                "SELECT pg_terminate_backend(pid) "
+                "FROM pg_stat_activity "
+                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
+            ),
+            {"database_name": _TEST_DATABASE_NAME},
+        )
+        connection.execute(text(f'DROP DATABASE IF EXISTS "{_TEST_DATABASE_NAME}"'))
+    admin_engine.dispose()
+
+
+os.environ.setdefault("BAYESIANQC_POSTGRES_TEST_URL", _postgres_base_url())
+os.environ["BAYESIANQC_DB_URL"] = _test_database_url()
+os.environ.setdefault("BAYESIANQC_SEED_LOCAL_DEV_KEY", "1")

 from app.db import get_engine, init_db
 from app.db_models import (
@@ -26,9 +90,11 @@ from app.db_models import (
     InvestigationAlertLink,
     Method,
     PosteriorState,
+    QCBacklogItem,
     PriorConfig,
     QCEvent,
     QCRecord,
+    QCRecordQuarantine,
     StreamConfig,
 )
 from app.storage import seed_defaults
@@ -36,13 +102,15 @@ from app.storage import seed_defaults

 @pytest.fixture(autouse=True)
 def reset_db():
-    db_path = TEST_DB_PATH
+    _ensure_test_database()
     init_db()
     with Session(get_engine()) as session:
         for table in [
             IngestionReceipt,
             AlertRecord,
             QCRecord,
+            QCRecordQuarantine,
+            QCBacklogItem,
             QCEvent,
             InvestigationAlertLink,
             Investigation,
@@ -62,5 +130,9 @@ def reset_db():
         seed_defaults(session)
     yield
     get_engine().dispose()
-    if db_path.exists():
-        db_path.unlink()
+
+
+def pytest_sessionfinish(session, exitstatus) -> None:
+    del session, exitstatus
+    get_engine().dispose()
+    _drop_test_database()

# Current Key Files


## Makefile

PYTHON ?= .venv/bin/python
ALEMBIC ?= .venv/bin/alembic
NPM ?= npm
POSTGRES_URL ?= postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
POSTGRES_TEST_URL ?= $(POSTGRES_URL)
POSTGRES_COPY_URL ?=

.PHONY: lint typecheck test build check postgres-up postgres-upgrade test-postgres migration-upgrade migration-rehearse migration-rehearse-postgres migration-rehearse-postgres-copy check-postgres

lint:
	$(PYTHON) -m ruff check app tests scripts

typecheck:
	$(PYTHON) -m pyright

test:
	$(PYTHON) -m pytest

build:
	$(NPM) --prefix frontend run check

check: lint typecheck test build

postgres-up:
	docker compose up -d postgres

postgres-upgrade:
	BAYESIANQC_DB_URL="$(POSTGRES_URL)" $(ALEMBIC) upgrade head

test-postgres:
	BAYESIANQC_POSTGRES_TEST_URL="$(POSTGRES_TEST_URL)" $(PYTHON) -m pytest tests/test_migrations.py

migration-upgrade:
	BAYESIANQC_DB_URL="$(POSTGRES_URL)" $(ALEMBIC) upgrade head

migration-rehearse:
	BAYESIANQC_DB_URL="$(POSTGRES_URL)" $(PYTHON) scripts/rehearse_sqlite_to_postgres.py --postgres-url "$(POSTGRES_URL)"

migration-rehearse-postgres:
	BAYESIANQC_DB_URL="$(POSTGRES_URL)" $(PYTHON) scripts/rehearse_sqlite_to_postgres.py --postgres-url "$(POSTGRES_URL)"

migration-rehearse-postgres-copy:
	test -n "$(POSTGRES_COPY_URL)" || (echo "Set POSTGRES_COPY_URL to a disposable Postgres database URL"; exit 2)
	case "$(POSTGRES_COPY_URL)" in *disposable*|*rehearsal*|*test*) ;; *) echo "POSTGRES_COPY_URL must look disposable: include disposable, rehearsal, or test"; exit 2;; esac
	BAYESIANQC_DB_URL="$(POSTGRES_COPY_URL)" $(PYTHON) scripts/rehearse_sqlite_to_postgres.py --postgres-url "$(POSTGRES_COPY_URL)" --copy-data --truncate-target

check-postgres: postgres-up postgres-upgrade test-postgres migration-rehearse-postgres

## alembic.ini

[alembic]
script_location = migrations
prepend_sys_path = .
sqlalchemy.url = postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S

## docker-compose.yml

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: bayesianqc
      POSTGRES_USER: bayesianqc
      POSTGRES_PASSWORD: bayesianqc
    ports:
      - "54329:5432"
    volumes:
      - bayesianqc-postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bayesianqc -d bayesianqc"]
      interval: 5s
      timeout: 3s
      retries: 20

volumes:
  bayesianqc-postgres:

## migrations/env.py

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.db_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _configured_url() -> str:
    return (
        os.getenv("BAYESIANQC_MIGRATION_DB_URL")
        or os.getenv("BAYESIANQC_DB_URL")
        or config.get_main_option("sqlalchemy.url")
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_configured_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _configured_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

## migrations/script.py.mako

"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}

## migrations/versions/20260703_0001_initial_sqlmodel_schema.py

"""Initial SQLModel schema.

Revision ID: 20260703_0001
Revises:
Create Date: 2026-07-03
"""

from __future__ import annotations

from alembic import op
from sqlmodel import SQLModel

import app.db_models  # noqa: F401

revision = "20260703_0001"
down_revision = None
branch_labels = None
depends_on = None

_INITIAL_TABLE_NAMES = (
    "instrument",
    "method",
    "analyte",
    "streamconfig",
    "priorconfig",
    "posteriorstate",
    "qcrecord",
    "qcrecordquarantine",
    "qcevent",
    "alertrecord",
    "investigation",
    "investigationalertlink",
    "capa",
    "capalink",
    "auditentry",
    "ingestionreceipt",
    "apikey",
)


def _initial_tables():
    return [SQLModel.metadata.tables[name] for name in _INITIAL_TABLE_NAMES]


def upgrade() -> None:
    SQLModel.metadata.create_all(bind=op.get_bind(), tables=_initial_tables())


def downgrade() -> None:
    SQLModel.metadata.drop_all(bind=op.get_bind(), tables=_initial_tables())

## migrations/versions/20260703_0002_qc_backlog.py

"""Add QC backlog work items.

Revision ID: 20260703_0002
Revises: 20260703_0001
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260703_0002"
down_revision = "20260703_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    qcrecord_columns = {column["name"] for column in inspector.get_columns("qcrecord")}
    qcrecord_indexes = {index["name"] for index in inspector.get_indexes("qcrecord")}
    if "qc_backlog_item_id" not in qcrecord_columns:
        op.add_column("qcrecord", sa.Column("qc_backlog_item_id", sa.Integer(), nullable=True))
    if "ix_qcrecord_qc_backlog_item_id" not in qcrecord_indexes:
        op.create_index("ix_qcrecord_qc_backlog_item_id", "qcrecord", ["qc_backlog_item_id"])
    op.create_table(
        "qcbacklogitem",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("stream_id", sa.String(), nullable=False),
        sa.Column("analyte", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("instrument", sa.String(), nullable=False),
        sa.Column("site", sa.String(), nullable=True),
        sa.Column("qc_level", sa.String(), nullable=False),
        sa.Column("units", sa.String(), nullable=False),
        sa.Column("reference_material_lot", sa.String(), nullable=False),
        sa.Column("reference_material_label", sa.String(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("lab_bench", sa.String(), nullable=True),
        sa.Column("assignment_group", sa.String(), nullable=True),
        sa.Column("assigned_to", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("requested_by", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by", sa.String(), nullable=True),
        sa.Column("completed_qc_record_id", sa.Integer(), nullable=True),
        sa.Column("last_quarantine_id", sa.Integer(), nullable=True),
    )
    for name, columns in [
        ("ix_qcbacklogitem_stream_id", ["stream_id"]),
        ("ix_qcbacklogitem_instrument", ["instrument"]),
        ("ix_qcbacklogitem_due_at", ["due_at"]),
        ("ix_qcbacklogitem_lab_bench", ["lab_bench"]),
        ("ix_qcbacklogitem_assignment_group", ["assignment_group"]),
        ("ix_qcbacklogitem_assigned_to", ["assigned_to"]),
        ("ix_qcbacklogitem_completed_qc_record_id", ["completed_qc_record_id"]),
        ("ix_qcbacklogitem_last_quarantine_id", ["last_quarantine_id"]),
        ("ix_qcbacklogitem_status_due", ["status", "due_at"]),
        ("ix_qcbacklogitem_instrument_due", ["instrument", "due_at"]),
        ("ix_qcbacklogitem_bench_due", ["lab_bench", "due_at"]),
        ("ix_qcbacklogitem_group_due", ["assignment_group", "due_at"]),
        ("ix_qcbacklogitem_assignee_due", ["assigned_to", "due_at"]),
        ("ix_qcbacklogitem_stream_due", ["stream_id", "due_at"]),
    ]:
        op.create_index(name, "qcbacklogitem", columns)


def downgrade() -> None:
    for name in [
        "ix_qcbacklogitem_stream_due",
        "ix_qcbacklogitem_assignee_due",
        "ix_qcbacklogitem_group_due",
        "ix_qcbacklogitem_bench_due",
        "ix_qcbacklogitem_instrument_due",
        "ix_qcbacklogitem_status_due",
        "ix_qcbacklogitem_last_quarantine_id",
        "ix_qcbacklogitem_completed_qc_record_id",
        "ix_qcbacklogitem_assigned_to",
        "ix_qcbacklogitem_assignment_group",
        "ix_qcbacklogitem_lab_bench",
        "ix_qcbacklogitem_due_at",
        "ix_qcbacklogitem_instrument",
        "ix_qcbacklogitem_stream_id",
    ]:
        op.drop_index(name, table_name="qcbacklogitem")
    op.drop_table("qcbacklogitem")
    op.drop_index("ix_qcrecord_qc_backlog_item_id", table_name="qcrecord")
    op.drop_column("qcrecord", "qc_backlog_item_id")

## scripts/rehearse_sqlite_to_postgres.py

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, Session, col, select

import app.db_models  # noqa: F401
from app.bayesian import _update_posterior
from app.db_models import PosteriorState, PriorConfig, QCRecord
from app.timeutils import as_utc

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POSTGRES_URL = "postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc"
_POSTERIOR_TOLERANCE = 1e-9


def _alembic_config(db_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def revision_head() -> str:
    head = ScriptDirectory.from_config(_alembic_config(DEFAULT_POSTGRES_URL)).get_current_head()
    if head is None:
        raise RuntimeError("Alembic migration head is not available")
    return head


@contextmanager
def _migration_url(db_url: str):
    previous = os.environ.get("BAYESIANQC_MIGRATION_DB_URL")
    os.environ["BAYESIANQC_MIGRATION_DB_URL"] = db_url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("BAYESIANQC_MIGRATION_DB_URL", None)
        else:
            os.environ["BAYESIANQC_MIGRATION_DB_URL"] = previous


def run_upgrade(db_url: str) -> None:
    with _migration_url(db_url):
        command.upgrade(_alembic_config(db_url), "head")


def run_downgrade(db_url: str, revision: str) -> None:
    with _migration_url(db_url):
        command.downgrade(_alembic_config(db_url), revision)


def table_names() -> list[str]:
    return [table.name for table in SQLModel.metadata.sorted_tables]


def table_counts(engine: Engine, names: Sequence[str]) -> dict[str, int]:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for name in names:
            if name not in existing:
                counts[name] = -1
                continue
            counts[name] = int(connection.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one())
    return counts


def _target_has_data(engine: Engine, names: Sequence[str]) -> bool:
    return any(count > 0 for count in table_counts(engine, names).values())


def _reset_postgres_sequences(engine: Engine, names: Sequence[str]) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        for name in names:
            table = SQLModel.metadata.tables[name]
            if "id" not in table.c:
                continue
            connection.execute(
                text(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{name}', 'id'),
                        COALESCE((SELECT MAX(id) FROM "{name}"), 0) + 1,
                        false
                    )
                    """
                )
            )


def sequence_checks(engine: Engine, names: Sequence[str]) -> dict[str, Any]:
    if engine.dialect.name != "postgresql":
        return {"status": "skipped", "reason": "not_postgres"}

    checks: dict[str, Any] = {"status": "ok", "tables": {}, "mismatches": []}
    with engine.connect() as connection:
        for name in names:
            table = SQLModel.metadata.tables[name]
            if "id" not in table.c:
                continue
            sequence_name = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                {"table_name": name},
            ).scalar_one_or_none()
            if sequence_name is None:
                continue
            max_id = int(connection.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{name}"')).scalar_one())
            sequence_row = connection.execute(text(f"SELECT last_value, is_called FROM {sequence_name}")).one()
            expected_next = max_id + 1 if max_id > 0 else 1
            actual_last = int(sequence_row.last_value)
            is_called = bool(sequence_row.is_called)
            actual_next = actual_last + 1 if is_called else actual_last
            ok = actual_next == expected_next
            checks["tables"][name] = {
                "max_id": max_id,
                "expected_next": expected_next,
                "last_value": actual_last,
                "actual_next": actual_next,
                "is_called": is_called,
                "ok": ok,
            }
            if not ok:
                checks["mismatches"].append(name)
    if checks["mismatches"]:
        checks["status"] = "mismatch"
    return checks


def copy_sqlite_rows(source: Engine, target: Engine, *, truncate_target: bool) -> dict[str, int]:
    names = table_names()
    if _target_has_data(target, names) and not truncate_target:
        raise RuntimeError("Target database is not empty; pass --truncate-target for a destructive rehearsal reset")

    tables = list(SQLModel.metadata.sorted_tables)
    copied: dict[str, int] = {}
    with source.connect() as source_connection, target.begin() as target_connection:
        if truncate_target:
            for table in reversed(tables):
                target_connection.execute(table.delete())
        for table in tables:
            rows = [dict(row) for row in source_connection.execute(table.select()).mappings().all()]
            if rows:
                target_connection.execute(table.insert(), rows)
            copied[table.name] = len(rows)
    _reset_postgres_sequences(target, names)
    return copied


def count_comparison(source_counts: dict[str, int], target_counts: dict[str, int]) -> dict[str, Any]:
    mismatches = {
        name: {"source": source_counts.get(name), "target": target_counts.get(name)}
        for name in sorted(source_counts)
        if source_counts.get(name) != target_counts.get(name)
    }
    return {"ok": not mismatches, "mismatches": mismatches}


def _expected_posterior(records: Sequence[QCRecord], priors: Sequence[PriorConfig]) -> dict[str, Any] | None:
    if not records or not priors:
        return None

    prior_idx = 0
    first_ts = as_utc(records[0].timestamp)
    while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= first_ts:
        prior_idx += 1
    current_prior = priors[prior_idx]
    mu_n, kappa_n, alpha_n, beta_n = current_prior.mu0, current_prior.kappa0, current_prior.alpha0, current_prior.beta0
    n_obs = 0

    for record in records:
        record_ts = as_utc(record.timestamp)
        while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= record_ts:
            prior_idx += 1
        record_prior = priors[prior_idx]
        if record_prior.id != current_prior.id:
            current_prior = record_prior
            mu_n, kappa_n, alpha_n, beta_n = (
                current_prior.mu0,
                current_prior.kappa0,
                current_prior.alpha0,
                current_prior.beta0,
            )
            n_obs = 0
        mu_n, kappa_n, alpha_n, beta_n = _update_posterior(mu_n, kappa_n, alpha_n, beta_n, record.result_value)
        n_obs += 1

    return {
        "mu_n": mu_n,
        "kappa_n": kappa_n,
        "alpha_n": alpha_n,
        "beta_n": beta_n,
        "n_obs": n_obs,
        "prior_id": current_prior.id,
    }


def _posterior_mismatch(state: PosteriorState, expected: dict[str, Any]) -> dict[str, Any] | None:
    mismatched: dict[str, Any] = {}
    for field in ("mu_n", "kappa_n", "alpha_n", "beta_n"):
        actual_value = float(getattr(state, field))
        expected_value = float(expected[field])
        if not math.isclose(actual_value, expected_value, rel_tol=0.0, abs_tol=_POSTERIOR_TOLERANCE):
            mismatched[field] = {"actual": actual_value, "expected": expected_value}
    for field in ("n_obs", "prior_id"):
        actual_value = getattr(state, field)
        expected_value = expected[field]
        if actual_value != expected_value:
            mismatched[field] = {"actual": actual_value, "expected": expected_value}
    return mismatched or None


def posterior_checks(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    if not {"posteriorstate", "qcrecord", "priorconfig"} <= set(inspector.get_table_names()):
        return {"ok": False, "reason": "missing_posterior_record_or_prior_table", "mismatches": []}

    with Session(engine) as session:
        record_counts = dict(
            session.exec(
                select(QCRecord.stream_id, func.count())
                .where(col(QCRecord.include_in_stats) == True)
                .group_by(QCRecord.stream_id)
            ).all()
        )
        records_by_stream: dict[str, list[QCRecord]] = {}
        records = session.exec(
            select(QCRecord)
            .where(col(QCRecord.include_in_stats) == True)
            .order_by(col(QCRecord.stream_id).asc(), col(QCRecord.timestamp).asc(), col(QCRecord.id).asc())
        ).all()
        for record in records:
            records_by_stream.setdefault(record.stream_id, []).append(record)
        states = {
            state.stream_id: state
            for state in session.exec(select(PosteriorState).order_by(PosteriorState.stream_id)).all()
        }
        priors_by_stream = {
            stream_id: list(
                session.exec(
                    select(PriorConfig)
                    .where(PriorConfig.stream_id == stream_id)
                    .order_by(col(PriorConfig.effective_from).asc(), col(PriorConfig.version).asc())
                ).all()

## docs/LAB_READINESS.md

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

## docs/VALIDATION_PACKAGE.md

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

## docs/MIGRATION_STRATEGY.md

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
