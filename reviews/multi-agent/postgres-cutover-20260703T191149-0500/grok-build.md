**Findings first (strict build/runtime + cutover review).**

Review performed via direct static inspection of current tree (app/, tests/, scripts/, migrations/, docker-compose.yml, Makefile, .github/workflows/ci.yml, README, docs, models, and related). Did not execute, replay, or resolve any commands/paths from the supplied packet block.

All claims in the packet (default URL, rehearsal script features, test additions, make targets, validation numbers, schema head `20260703_0002`) are consistent with the code present. The implementation correctly makes Postgres the default and keeps SQLite strictly opt-in. However, multiple structural, coverage, and integrity gaps exist.

### P0/P1 (Blocking)

**P1: alembic.ini default remains SQLite.**
`sqlalchemy.url = sqlite:///./bayesianqc.db` (alembic.ini:4). `migrations/env.py` correctly prefers `BAYESIANQC_MIGRATION_DB_URL`/`BAYESIANQC_DB_URL`, but bare `alembic`, some docs examples, or accidental invocation without the env var will operate on SQLite. This is a footgun during cutover and for any developer/CI operator following "just run alembic".

**P1: Dual migration implementations with drift risk.**
`app/migrations.py` contains a complete parallel SQLite path (`SQLITE_SCHEMA_VERSION=8`, `run_sqlite_migrations`, hand-coded `_migrate_*` steps using PRAGMA user_version + `CREATE TABLE IF NOT EXISTS` + `IF NOT EXISTS` index guards). Alembic revisions (`20260703_0001` + `0002`) are the PG path. `init_db` and `run_alembic_migrations` correctly dispatch, but any future DDL (especially the backlog work or JSON/eval fields) must be kept in sync manually. The sqlite path is not derived from Alembic. This is unacceptable for a claimed "Postgres-first" cutover.

**P1: Weak foreign-key coverage.**
Only a handful of FKs are declared in `app/db_models.py` (Instrument→Method→Analyte, PosteriorState→PriorConfig/StreamConfig). `qc_backlog_item_id`, most link tables (`investigationalertlink`, `capalink`), StreamConfig/Prior references by value, and many `*_id` columns have only indexes. `migrations/versions/20260703_0002_qc_backlog.py` adds the column/index without a constraint. `rehearse_sqlite_to_postgres.py` copy and ingestion can create orphans with no DB enforcement. Packet correctly calls this out as still needed.

**P1: Posterior value integrity after copy is under-validated.**
`posterior_checks` (rehearsal + tests) only asserts `n_obs` parity + table counts. `sequence_checks` is good. Full Bayesian recomputation (`mu_n`/`kappa_n`/etc.) is done only inside `test_postgres_same_stream_concurrent_ingestion_matches_posterior_history`. The `--copy-data` path does not re-execute the update rules against copied rows. Packet acknowledges this gap.

**P1: Alembic downgrade paths untested on Postgres.**
Both migration files define `downgrade()`. No test exercises them (disposable or otherwise). `test_migrations.py` only does forward upgrade + copy.

**P1: Datetime/TZ handling is dialect-sensitive and risky.**
Models and `20260703_0002` use plain `sa.DateTime()` (no `timezone=True`). `app/timeutils.py:as_utc` explicitly assumes "SQLite commonly returns naive datetimes; we treat them as UTC". Postgres + psycopg commonly surfaces different tz behavior. Ordering, baseline windows, `has_later_record`, and chart queries are vulnerable to silent skew after cutover. Tests that passed may not have stressed this.

### Test Gaps (beyond packet "Remaining Gaps")

- `pytest` (the 33 passed) runs exclusively under SQLite via `tests/conftest.py` autouse `reset_db` + `os.environ.setdefault(..., sqlite...)`. Postgres coverage is 100% opt-in and invisible to normal `make test` / `pytest`.
- Only one narrow concurrency scenario (same-stream ingestion, 5 threads, happy path + math verification). No cross-stream, no writers on alerts/quarantine/backlog/config + ingest, no reprocess under contention, no lock timeout/rollback injection.
- No test that the process default (no `BAYESIANQC_DB_URL` at all) produces the declared Postgres DSN and fails visibly when PG is absent.
- No roundtrip content validation of copied JSON columns (`signals`, `bayesian_risk`, `raw_payload`, `context`, etc.), enums, or audit `before/after`.
- No matrix or explicit "default URL" job in CI beyond the explicit `make postgres-*` steps.
- Disposable DB fixture + `ThreadPoolExecutor` test mutates global `_ENGINE` cache; fragile if more tests are added.

### Docker / CI Issues

- CI (`ci.yml`) correctly uses GitHub service container on 54329 and calls the granular targets (avoiding `postgres-up`). `make check-postgres` (which does unconditional `docker compose up`) is only for local.
- No failure modes tested: missing psycopg, compose healthcheck flake, port collision inside runner, or compose volume state leaking into CI.
- Compose has a named volume but no documented cleanup or test profile. Local smoke leaves rows (acknowledged).
- No integration of readiness checks (e.g., a `/ready` or startup probe that confirms migrations + seed).

### Command / Docs / Makefile Accuracy

- `migration-rehearse` (no `--postgres-url`) and `migration-rehearse-postgres` are distinct; several docs/README examples are easy to mis-copy.
- `alembic.ini` + plain `alembic` commands are underspecified in the "Postgres-first" story.
- `scripts/rehearse_sqlite_to_postgres.py --sqlite-db` defaults to `bayesianqc.db`; the copy path hard-requires the file when `--copy-data` is used.
- `run_demo.sh` and `Makefile` POSTGRES_URL defaults are consistent with `app/db.py`, but any drift will be painful.
- Known Vite large-chunk warning is still present (non-blocking).

### Runtime / Data-Integrity Risks

- `copy_sqlite_rows` uses `metadata.sorted_tables` + bulk `insert()`. With sparse FKs this usually works, but ordering is not guaranteed to be safe if more FKs are added later. No `deferrable` or per-table transaction granularity.
- `sequence_checks` + `_reset_postgres_sequences` are well-written for the "id" serial case, but any table whose PK is populated differently (or added later) will be missed.
- Global `_ENGINE` singleton in `app/db.py` + URL-string comparison can retain a stale engine after env changes in long-lived processes or certain test orders.
- `stream_write_lock` FOR UPDATE is on `StreamConfig`; the first writer for an unseeded stream or concurrent config creation could have subtle races (though seed + existing data mitigates in practice).
- `init_db` + lifespan seed always runs. On PG with no `BAYESIANQC_SEED_LOCAL_DEV_KEY`, the dev key is not seeded (intentional per `_seed_local_dev_key_enabled`), but this is a behavior change from prior SQLite-default world.
- No explicit handling or test for `IntegrityError` / unique violation paths under the new lock on Postgres.

### Positive Notes (for balance)

- Disposable Postgres DB creation/termination in tests is correctly isolated.
- `stream_write_lock` abstraction + explicit sequence validation + concurrent math assertion in one test are high-quality.
- CI + Makefile structure cleanly separates the Postgres gate.
- Runtime smoke endpoints and "no change to existing bayesianqc.db" claims align with the Postgres-default + conditional code.
- Alembic `0002` uses inspector guards for the additive column (defensive for the revision).

### Summary Recommendation

**Do not waive the P1 items.** The cutover is directionally correct and the rehearsal/lock/concurrent math work is solid, but the dual-migration surface, missing FKs, weak posterior value validation on copy, alembic.ini default, TZ exposure, and narrow test boundary are material for anything beyond pure local/dev.

Before any further promotion:
- Make alembic default Postgres or remove the sqlite default.
- Either generate Alembic migrations from models for the SQLite path or retire the legacy `run_sqlite_migrations` for all but throwaway rehearsal.
- Add at least one full Bayesian recompute assertion in the copy rehearsal.
- Add downgrade tests and broader concurrency.
- Declare and enforce the datetime tz story (or document the naive-UTC contract everywhere).

The listed "Remaining Gaps" in the packet (full posterior recompute automation, stronger FKs, backup/rollback, etc.) remain accurate and are not mitigated by the current evidence.
