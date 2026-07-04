Reviewing the Postgres cutover: reading the review skill and inspecting critical paths in the codebase.
## 1. Verdict: **approve-with-nits**

The Postgres-only runtime cutover is implemented coherently: SQLite is rejected at startup, schema setup goes through Alembic, stream locking is Postgres-only, tests use disposable Postgres DBs, and the validation receipt matches what I checked locally (38 tests passed; SQLite URL fails fast with the documented `RuntimeError`).

Nothing in scope rises to a **P0/P1 code defect** that would block a local/dev demo when Docker Postgres is up. The main milestone risks are **repo packaging** (large untracked cutover tree) and **operator/docs friction** (pytest without Postgres, optional destructive rehearsal flags).

---

## 2. Findings (by severity)

### P1 — Process / demo milestone (not a logic bug)

| # | Finding | Reference |
|---|---------|-----------|
| P1-1 | **Cutover infrastructure is still mostly untracked.** A fresh clone cannot reproduce Postgres runtime, migrations, CI, or `make check-postgres` without the untracked paths from git status (`alembic.ini`, `migrations/`, `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml`, `scripts/rehearse_sqlite_to_postgres.py`, `tests/test_migrations.py`, migration/readiness docs, etc.). Tracked diffs alone understate merge readiness. | Git status in review packet |
| P1-2 | **`pytest` is hard-coupled to a live Postgres.** `tests/conftest.py` creates/drops `bayesianqc_pytest_{pid}` on the configured host; there is no graceful skip if Compose is down. That matches the cutover intent but will surprise anyone who runs `pytest` before `docker compose up -d postgres`. | `tests/conftest.py` L14–76, L103–106 |

### P2 — Worth fixing or documenting; not demo blockers

| # | Finding | Reference |
|---|---------|-----------|
| P2-1 | **Destructive legacy copy is only guarded in Make, not in the script.** `migration-rehearse-postgres-copy` requires a disposable URL substring; `scripts/rehearse_sqlite_to_postgres.py` still accepts `--copy-data --truncate-target` against any `--postgres-url`. | `Makefile` L42–45; `scripts/rehearse_sqlite_to_postgres.py` L146–149, L319–320 |
| P2-2 | **Test runtime cost.** Full suite took ~63s here largely because `reset_db` calls `init_db()` → Alembic on every test. Acceptable for 38 tests; will hurt as the suite grows. | `tests/conftest.py` L103–106; local `pytest -q` |
| P2-3 | **Revision `20260703_0002` is only partially defensive.** Column/index adds are guarded; `op.create_table("qcbacklogitem", …)` is not. Normal Alembic versioning avoids re-run; messy manual DB state could still fail upgrades. | `migrations/versions/20260703_0002_qc_backlog.py` L19–72 |
| P2-4 | **Initial revision still mirrors full metadata via `create_all`.** Fine for local/dev; already called out as a regulated-deployment gap. | `migrations/versions/20260703_0001_initial_sqlmodel_schema.py` L45–46; `docs/MIGRATION_STRATEGY.md` |
| P2-5 | **Helper scripts still default API key to `local-dev-key` without seeding.** Safe when `BAYESIANQC_SEED_LOCAL_DEV_KEY=1` or `run_demo.sh`; easy 401 if someone starts `uvicorn` without the seed export. README quick start is correct; `scripts/post_sample_qc.py` default is the footgun. | `app/storage.py` L42–46, L139–140; `scripts/post_sample_qc.py` (grep) |

### P3 — Nits

| # | Finding | Reference |
|---|---------|-----------|
| P3-1 | SQLite rejection message and default Postgres URL are clear and consistent. | `app/db.py` L13–21, L47–49 |
| P3-2 | `alembic.ini` default URL is Postgres, not SQLite (prior review concern addressed). | `alembic.ini` L4 |
| P3-3 | Validation left smoke/demo rows in the default local DB (noted in packet residual risk). | Review packet “Residual Validation Risk” |

**No P0 findings** for local/dev Postgres runtime, migration head `20260703_0002`, or SQLite-as-runtime regression.

---

## 3. Fixes required before demo / job-search milestone

**Required (P1):**

1. **Stage and commit the untracked cutover bundle** so a clone gets: `docker-compose.yml`, `alembic.ini`, `migrations/`, `Makefile`, `.github/workflows/ci.yml`, `scripts/rehearse_sqlite_to_postgres.py`, `tests/test_migrations.py`, and the Postgres/migration docs referenced from README.
2. **Make the Postgres prerequisite obvious for tests** — e.g. one line in README/AGENTS: `docker compose up -d postgres` before `pytest` / `make check`, or a conftest failure message that says that explicitly (not only a connection error).

**Recommended before sharing the repo (P2, cheap):**

3. Add a **script-level guard** for `--copy-data` + `--truncate-target` (same disposable URL rule as Make), or require `--i-know-this-is-disposable`.
4. Optionally add a **one-command demo entry** in README pointing at `scripts/run_demo.sh` (already sets `BAYESIANQC_DB_URL` + `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`).

**Not required for local/dev demo:** production backup/restore, OIDC/MFA, formal Bayesian validation, schema-diff CI gate.

---

## 4. Remaining production / lab-readiness gaps (document, not blockers)

Already well captured in `docs/LAB_READINESS.md`, `docs/VALIDATION_PACKAGE.md`, and `docs/MIGRATION_STRATEGY.md`; worth keeping visible:

- **Regulated migration hygiene:** move from metadata `create_all` baseline to explicit forward-only Alembic deltas; add automated schema-diff gate before shared-lab Postgres.
- **Cutover evidence:** archived rehearsal JSON, backup/restore drill, rollback proof, reviewer synthesis for anything beyond local/dev.
- **Security / compliance:** no `BAYESIANQC_SEED_LOCAL_DEV_KEY` in shared environments; OIDC/MFA, e-signature semantics, audit export/retention SOPs.
- **Data / time semantics:** UTC-naive datetime handling; limited FK coverage per `db_models.py`.
- **Concurrency:** Postgres `FOR UPDATE` on stream config is in place; optional posterior-state row locking / optimistic concurrency still listed in architecture notes.
- **Legacy data path:** operators with only `bayesianqc.db` must use rehearsal/import docs — the app will not read that file at runtime.

---

**Summary:** Approve the technical cutover for local/dev demo with nits. Before the milestone, **commit the untracked Postgres/migration/CI tree** and **surface the Docker Postgres requirement for tests**. Everything else is documentation, operator safety, or out-of-scope lab production readiness.
