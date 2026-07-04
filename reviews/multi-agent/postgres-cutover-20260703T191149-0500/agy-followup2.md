# Review Findings

## P1 - Blocking for local/dev
1. **Startup Race Condition in `run_demo.sh`**: The script invokes `docker compose ... up -d postgres` and immediately spawns the backend via `uvicorn`. Because the Postgres container takes a few seconds to initialize and accept connections (especially on a fresh volume boot), the backend's synchronous `init_db()` will likely crash with a connection error.
   - **Remediation**: Add a synchronization barrier. Either use `docker compose ... up -d --wait postgres` (ensuring a `healthcheck` is defined in `docker-compose.yml`), or add a polling loop in `run_demo.sh` (e.g., using `pg_isready` or simple `nc`/Python retry logic) before executing the backend.

## P2 - Non-blocking / Recommended
1. **Redundant Migration Instruction**: The updated `README.md` snippet for starting the Postgres dev database includes executing `alembic upgrade head` immediately before `uvicorn app.main:app`. However, the documentation directly below it notes that `init_db()` applies Alembic migrations automatically for non-SQLite URLs. This manual instruction is redundant and should be removed to avoid developer confusion.
2. **Disposable Safety Boundary**: The README mentions that `migration-rehearse-postgres-copy` is destructive and requires a disposable target. Since the `Makefile` is currently untracked, just ensure that the underlying Make target enforces a safety check against the `_disposable` suffix in the URL before passing the `--truncate-target` flag to the script.

---

# Verification of Prior Blockers
All prior follow-up blockers are successfully remediated in this packet:
- **Untracked worktree visibility**: Explicitly acknowledged and enumerated in the "Worktree Inclusion Note" section.
- **Expanded Postgres API smoke coverage**: `/me`, backlog, `POST /qc/records`, quarantine, chart, and audit endpoints are fully incorporated into both runtime smoke validation and `test_migrations.py`.
- **AGENTS seed env**: `BAYESIANQC_SEED_LOCAL_DEV_KEY=1` is implemented, documented in `AGENTS.md` and `README.md`, and integrated into `run_demo.sh`.
- **Validation-package gate labeling**: Pre-regulated deployment gating is appropriately called out in the README and "Remaining Gaps", referencing the `LAB_READINESS` and `VALIDATION_PACKAGE` documents.
- **Evidence buckets**: Evidence is clearly categorized into Static/SQLite Regression, Local/Dev Postgres Gate, and Rehearsal.
- **Empty SQLite-source caveat**: Accurately documented in the Rehearsal evidence (`streams_checked was 0`), acknowledging the local SQLite state while relying on the seeded tests for copy validation.

# Structural Review Summary

- **Migration Correctness & Data Integrity**: `rehearse_sqlite_to_postgres.py` cleanly verifies row counts, schema/indexes, sequence alignment, and posterior computation with a rigorous `1e-9` tolerance.
- **Postgres-First Runtime Boundary**: Clean transition in `app/db.py`. The application will now fail visibly if Postgres is unavailable, which effectively mitigates the risk of a silent (and dangerous) fallback to SQLite during standard local development.
- **SQLite Fallback Risk**: Neutralized. SQLite is strictly opt-in for regression and explicit copy-rehearsal compatibility.
- **Sequence and Copy Rehearsal**: Covered thoroughly by both the manual Python script rehearsal and the `test_migrations.py` disposable-Postgres suite.
- **Concurrency Coverage**: Successfully addressed via the "concurrent same-stream ingestion" case in the test suite.
- **Operational Rollback/Readiness**: Correctly scoped. The remaining gaps (OIDC/MFA, cross-engine schema diffs, timezone hardening) are correctly deferred as production/shared-lab blockers rather than local/dev blockers.

**Decision**: **APPROVED WITH 1 BLOCKER**. Resolve the container initialization race condition in `scripts/run_demo.sh` prior to staging/committing the untracked files to guarantee a reliable "clone and run" developer experience.
