**Grok Build Review: BAYESIANQC local/dev Postgres cutover (remediated)**

**Date:** 2026-07-03
**Scope:** local/dev Postgres-first cutover only. Production/shared-lab explicitly out of scope.
**Approach:** Static inspection of current tree + comparison to supplied REVIEW_PACKET.md (no commands from the packet were executed; no files mutated).

### Prior blocker verification (as instructed)
- **alembic.ini default**: PASS. `sqlalchemy.url` is the Compose Postgres URL.
- **dual migrations**: Mitigated at runtime. `init_db()` + `run_alembic_migrations`/`run_sqlite_migrations` correctly branch (`sqlite` path does `create_all` + ladder; else Alembic). Legacy SQLite ladder (to v8) remains in `app/migrations.py`.
- **posterior recomputation**: PASS. `scripts/rehearse_sqlite_to_postgres.py` uses `_POSTERIOR_TOLERANCE = 1e-9` + `_expected_posterior` (matches `app.bayesian._update_posterior`). `tests/test_migrations.py` has explicit recompute in `test_sqlite_to_postgres_copy...` and `test_postgres_same_stream_concurrent...` (approx 1e-12).
- **downgrade tests**: PASS. `test_postgres_downgrade_to_previous_revision_and_reupgrade` explicitly downgrades to `20260703_0001`, asserts absence of `qcbacklogitem` + column, then re-upgrades and checks head.
- **runtime on 8010**: PASS. `scripts/run_demo.sh` (with `setsid`, env injection of Postgres URL + seed flag), `stop_demo.sh`, README, and AGENTS.md updated. Lifespan calls `init_db()`.
- **copy target**: PASS. Makefile target requires `POSTGRES_COPY_URL` (or fails), script raises if target has data without `--truncate-target`, docs label it destructive/disposable-only. Rehearsal also does sequence reset + posterior check on copy path.

### Findings (P0/P1/P2)

#### P0 (blocking for local/dev cutover unless explicitly waived)
- **Narrow Postgres coverage in the declared gate.** `make check-postgres` runs Compose up + Alembic + `tests/test_migrations.py` (7 tests under `BAYESIANQC_POSTGRES_TEST_URL`) + non-copy rehearsal. Normal `pytest` (33 passed in packet) forces SQLite via `tests/conftest.py` top-level `os.environ.setdefault("BAYESIANQC_DB_URL", sqlite...)`. The only PG ingestion exercised is the copy test (1 record) and the concurrent same-stream test (5 records). Broader paths (`test_ingestion.py`, services, API routers, evaluations, backlog, alerts, audit, chart reprocessing, etc.) have no automated Postgres execution in the cutover gate. This is a material gap for "Postgres is now the default."
- **Autouse fixture + DB_URL monkeypatch hazard.** `conftest.py:reset_db` (autouse) does `init_db()`, mass deletes, seed, and final `/tmp` file unlink. PG-specific tests set `BAYESIANQC_DB_URL` (or use disposable) via monkeypatch inside the test function. Ordering, engine caching in `app/db.py`, and the unconditional sqlite default create fragile interactions and risk of acting on the wrong engine or leaking sqlite state.

#### P1 (high severity for the cutover; address or accept)
- **Demo script lifecycle leaves state.** `run_demo.sh` always does `docker compose up -d postgres`. `stop_demo.sh` only stops postgres when `BAYESIANQC_STOP_POSTGRES=1`. Default behavior leaves the container + named volume running.
- **Persistent dev Postgres is unmanaged.** Packet correctly documents that the dev DB "contains smoke rows" and is not pristine. Rehearsal against the live dev URL can legitimately report `streams_checked: 0`. No reset step exists in `check-postgres`, demo scripts, or Makefile targets.
- **Dual-implementation surface not reduced.** ~200+ LOC of SQLite PRAGMA/user_version ladder, resequencing, index helpers, etc. live in `app/migrations.py` (and `run_sqlite_migrations` is imported unconditionally). Correctly guarded for PG, but still parsed/imported and a future drift vector.
- **Dev key seeding footgun.** `_seed_local_dev_key_enabled()` in `storage.py` seeds `local-dev-key` only when the env var is set *or* the URL is sqlite. Postgres dev path requires the explicit export (correctly shown in README/scripts), but a minimal startup produces a running API with no usable local admin key.

#### P2 (medium / operational / acknowledged gaps)
- **Missing FK on backlog linkage.** `QCRecord.qc_backlog_item_id` is declared as bare `Optional[int] = Field(..., index=True)`. No `foreign_key=` (unlike `instrument_id`/`method_id`). Migration 0002 uses manual `op.add_column` + index with no FK. Alembic 0001 benefits from `create_all` on metadata; 0002 does not. Matches the packet's "Stronger foreign-key coverage" remaining gap.
- **Engine singleton friction is still visible.** `app/db.py` caches `_ENGINE`; multiple sites (tests, rehearsal, get_engine checks) call `dispose()` + re-init when URL changes. Functional for the cutover but indicates a pain point.
- **Datetime handling still soft.** `timeutils.as_utc`, `utcnow()`, and storage of `datetime` objects are used throughout. Packet correctly flags the need for formal timezone hardening before anything beyond local/dev. Postgres surfaces differences more than SQLite.
- **No generated cross-engine schema diff.** Packet's "Remaining Gaps" are accurate: Alembic head + manual schema/index/count/sequence/posterior checks are the current guard. No automated `alembic --autogenerate` comparison or similar is present.
- **Other items matching packet.** Vite large chunk warning remains; copy rehearsal is intentionally manual/destructive; backup/restore, OIDC, retention, formal model validation, etc. are out of scope.

### Positive observations (for balance)
- `alembic.ini`, `app/db.py` (`DEFAULT_DB_URL`, branching `init_db`, sync `get_session` + yield), `app/migrations.py` (guarded Alembic runner + `_alembic_config` override), demo scripts, Makefile targets, and `rehearse_sqlite_to_postgres.py` (head derivation, schema checks, sequence reset, posterior, copy guards) are all aligned with the remediation intent.
- Downgrade coverage and same-stream concurrent ingestion + posterior recompute are present and exercised.
- No obvious silent SQLite fallback for normal (non-explicit) startup.
- Most route handlers using `Depends(get_session)` are sync (the few async handlers do not take the session dependency).
- 0002 downgrade implementation drops the added column/index/table.

### Recommendation for local/dev cutover
The explicit prior blockers are remediated. The implementation is usable for local/dev with the documented steps.

However, the two P0 items (narrow automated coverage on the new default engine + fixture isolation risk) mean confidence in "no PG-specific regressions" is lower than for the SQLite path. Either expand the Postgres gate (e.g., run a core subset of ingestion/API tests under disposable PG) or document the limitation explicitly before treating the cutover as complete for day-to-day local/dev work.

All other points are consistent with the gaps and constraints already declared in the supplied packet.
