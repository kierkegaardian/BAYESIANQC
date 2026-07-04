# Review Findings

**P0 - Blocking**
- **Missing Untracked/Unstaged Files in Diff**: The `CURRENT GIT DIFF STAT` indicates that critical files outlined in the Implementation Summary are missing from the commit. Specifically, `alembic.ini`, the `alembic/` directory (containing migration `20260703_0002`), `Makefile`, `scripts/rehearse_sqlite_to_postgres.py`, `tests/test_migrations.py`, and `docker-compose.yml` (if newly introduced) are completely absent. The validation passed on the local machine due to untracked/unstaged files, but the PR is fundamentally incomplete and cannot be merged.

**P1 - Blocking (for shared-lab deployment; acceptable for local/dev cutover if waived)**
- **Unsafe Automatic Migrations in `init_db()`**: `app/db.py` introduces `run_alembic_migrations(engine)` into the app startup sequence. While convenient for single-worker local/dev environments, this is a dangerous concurrency hazard for multi-worker or multi-container deployments where race conditions during schema mutation can corrupt the database. This must be disabled or explicitly gated behind a strict local-dev environment flag before any shared-lab cutover.

**P2 - Non-Blocking / Polish**
- **Unconditional Postgres Docker Compose Execution**: In `scripts/run_demo.sh`, `start_postgres()` unconditionally runs `docker compose up -d postgres` every time the script is executed. If a developer explicitly overrides the `BAYESIANQC_DB_URL` to test the SQLite fallback or points to a remote database, the script will spin up the local Docker container anyway. This should ideally be conditionally bypassed if the DB URL does not point to the local Compose instance.

---

### Verification of Prior Blockers
- **Stale port 8010 runtime:** Verified Fixed. The use of `setsid` combined with stdin redirection (`< /dev/null`) in `run_demo.sh` and the process group kill (`kill -- "-${pid}"`) in `stop_demo.sh` correctly prevents orphaned Uvicorn worker processes from surviving script termination.
- **`alembic.ini` SQLite default:** Not verified. (File missing from diff stat; blocked by P0).
- **`AGENTS.md` SQLite canonicalization:** Verified Fixed. Postgres is now declared as the canonical default, with SQLite explicitly relegated to fallback/rehearsal testing.
- **Destructive copy rehearsal target:** Verified Fixed. The README accurately documents `--truncate-target` and restricts it to disposable use.
- **Posterior parameter recomputation:** Not verified. (Script missing from diff stat; blocked by P0).
- **Downgrade/re-upgrade coverage:** Not verified. (Test file missing from diff stat; blocked by P0).
- **Validation wording:** Verified Fixed. Rehearsal constraints and local state are accurately described in the packet.

### General Notes
- Changing `get_session()` in `app/db.py` from `async def` (`AsyncIterator`) to `def` (`Iterator`) is an excellent and correct fix. It forces FastAPI to run the dependency generator in its synchronous threadpool, preventing blocking DB calls from stalling the main event loop.
- The SQLite `busy_timeout` pragma addition in `app/db.py` is a solid concurrency improvement for the fallback path.
