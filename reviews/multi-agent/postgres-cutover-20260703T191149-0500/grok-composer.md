Reviewing the cutover packet against the repo: checking DB defaults, migration/rehearsal scripts, tests, Makefile, and readiness docs.
## Verdict

**Reviewer gate: BLOCKED** for treating this slice as a complete, operator-safe Postgres cutover validation. Core Postgres migration and opt-in migration tests look credible, but the packet over-aggregates evidence, understates SQLite vs Postgres test boundaries, and does not satisfy the repo’s own validation/archive gate.

Safe to acknowledge: **local/dev default URL is Postgres**, Alembic head `20260703_0002` is wired, and opt-in `tests/test_migrations.py` with disposable DBs is the right shape of cutover testing.

---

## P0 (blocking)

### P0-1 — Primary `pytest` gate is not Postgres-first; packet cites it as cutover evidence

`tests/conftest.py` forces `BAYESIANQC_DB_URL` to a temp SQLite file and `init_db()` runs `create_all` + `run_sqlite_migrations`, not Alembic/Postgres. Ingestion, backlog, chart kiosk, and most integration coverage never exercise the Postgres runtime path.

The packet lists `.venv/bin/python -m pytest -q`: `33 passed, 3 skipped` alongside migration work without stating that this is **SQLite application behavior**, not Postgres cutover proof. That is a **false completeness signal** for migration correctness and data integrity at the app layer.

**Required before sign-off:** Label that result as “SQLite regression only,” or add a documented Postgres-backed integration gate (or waive in writing with explicit risk acceptance).

### P0-2 — Two live schema evolution paths; parity is asserted, not gated

SQLite uses `PRAGMA user_version` steps in `app/migrations.py`; Postgres uses Alembic. The default test harness never proves `init_db()` on Postgres matches SQLite-backed tests for the same commit.

Cutover rehearsal validates Alembic schema, copy counts, sequences, and `n_obs` sanity—not that **all app paths** behave identically on both engines.

**Required:** Explicit “schema parity” statement limited to what was tested, plus a tracked drift-risk item (or automated cross-engine smoke).

---

## P1 (blocking unless explicitly waived)

### P1-1 — `make check-postgres` ≠ SQLite→Postgres copy rehearsal

`Makefile` `check-postgres` ends with `migration-rehearse-postgres`, which runs `rehearse_sqlite_to_postgres.py --postgres-url "$(POSTGRES_URL)"` **without** `--copy-data` / `--truncate-target`.

The packet’s copy/count/sequence/posterior copy evidence came from a **separate** disposable-target run. Equating `make check-postgres` with full copy rehearsal is **misleading** for operators.

**Fix docs/packet:** Split “schema upgrade gate” vs “destructive copy gate”; add a Make target for the copy path or mark copy as manual mandatory before any real SQLite import.

### P1-2 — `VALIDATION_PACKAGE.md` / `MIGRATION_STRATEGY.md` imply full migration tests without Postgres env

Both documents tell operators to run `pytest tests/test_migrations.py` (and bare `alembic upgrade head` in places) without always requiring `BAYESIANQC_POSTGRES_TEST_URL` / `BAYESIANQC_DB_URL`. Without those vars, three Postgres tests skip and Alembic can target `alembic.ini`’s default `sqlite:///./bayesianqc.db`.

That is a **SQLite/Postgres boundary trap**: app default is Postgres; CLI migration default can still be SQLite.

### P1-3 — `AGENTS.md` still canonicalizes SQLite

Repo agent notes still say “Data: SQLite database at `./bayesianqc.db`” and show `uvicorn` with no Compose/Postgres steps. That contradicts `app/db.py` `DEFAULT_DB_URL` and README—high risk for agents and operators using the wrong runbook.

### P1-4 — Lab-readiness / validation gate not met by packet evidence

`docs/LAB_READINESS.md` (2026-06-28) requires `VALIDATION_PACKAGE.md` checks **and archived**: command output, OpenAPI snapshot, fixtures, audit export, P0/P1 reviewer artifacts.

The packet does not show: `gen:api` / OpenAPI diff, functional matrix execution, archived rehearsal **JSON**, or pilot bundle items. “33 passed + make check-postgres” is not the documented lab validation gate.

Do not read this slice as satisfying “Before any lab pilot” in LAB_READINESS without waivers.

### P1-5 — Data-integrity claims exceed automation

Copy rehearsal `posterior_checks` only compares per-stream `PosteriorState.n_obs` to included `QCRecord` counts—not `mu_n`/`kappa_n`/`alpha_n`/`beta_n`, per-record Bayesian fields, or SQLite vs Postgres value diff. The packet’s “Remaining Gaps” admits this; the **Implementation Summary / Validation Evidence** tone still reads like stronger integrity proof than exists.

Concurrent Postgres coverage is **one** disposable-DB test (five threads, one stream). Fine for a slice; insufficient to headline “concurrency coverage” for cutover.

### P1-6 — Runtime smoke is non-reproducible in the workflow

Evidence uses port **8011** because **8010** had a stale uvicorn without documented `BAYESIANQC_DB_URL`. That is honest as a constraint but **not** a gated operator step: no script/Make target, no “stop conflicting process” SOP, no proof which DB 8010 was serving.

“`bayesianqc.db` unchanged” does not protect users who still hit the wrong server on 8010.

### P1-7 — Shared Compose Postgres polluted by validation

Known constraint: local Postgres retains smoke rows. `migration-rehearse-postgres` runs sequence/posterior checks against that shared DB, not an isolated empty DB (unlike disposable test DBs). Operators can misread green checks as clean-room validation.

**Waivable for dev-only** if the packet states “checks run against dirty shared dev DB.”

### P1-8 — Production/shared-lab blockers listed but not tied to operator “do not”

Gaps (backup/restore, rollback proof, FK DDL discipline, OIDC/MFA, e-signatures, formal Bayesian validation) are correct. The packet should state plainly: **this slice does not clear shared-lab or regulated deployment**—only local/dev Postgres-first—so “defensible lab prototype” in LAB_READINESS is not upgraded by this packet alone.

---

## P2 (non-blocking; fix for clarity)

| ID | Finding |
|----|---------|
| P2-1 | Readiness docs dated **2026-06-28**; cutover packet **2026-07-03**—operators may assume docs were refreshed with the cutover. |
| P2-2 | `revision_head()` uses Alembic config with `sqlite://` placeholder—works but confuses “Postgres head” mentally. |
| P2-3 | CI step 1 `make check` ignores the Postgres service; Postgres only in step 2—fine, but easy to misread as “CI is Postgres-first.” |
| P2-4 | Stale review artifacts (e.g. AGY review: “defaults to SQLite”) still in tree; not packet scope but adds operator noise. |

---

## What holds up (credit)

- `DEFAULT_DB_URL` in `app/db.py` matches documented Compose URL; non-SQLite `init_db()` delegates to Alembic.
- Dynamic Alembic head + rehearsal schema smoke in a temp SQLite file is a sound quick check.
- Disposable Postgres DB fixture for migration tests is appropriate; six migration tests cover upgrade, copy, sequences, and concurrent ingestion with full posterior parameter assertions on Postgres.
- CI runs `postgres-upgrade`, `test-postgres`, and `migration-rehearse-postgres` after generic `make check`.
- Packet correctly scopes production/shared-lab out and lists major regulated gaps.

---

## Minimum actions to unblock reviewer sign-off

1. **Rewrite validation evidence** into three labeled buckets: SQLite regression (`pytest` default), Postgres migration (`BAYESIANQC_POSTGRES_TEST_URL`), optional destructive copy (`--copy-data --truncate-target` on disposable target).
2. **Align operator docs**: `AGENTS.md`, `VALIDATION_PACKAGE.md`, `MIGRATION_STRATEGY.md`—always prefix Alembic/postgres pytest with required env vars; never imply bare `pytest tests/test_migrations.py` is complete.
3. **Extend or document `make check-postgres`** so “copy rehearsal” is either a named target or explicitly out of scope for that target.
4. **Archive** rehearsal JSON + OpenAPI diff per LAB_READINESS, or waive archiving with owner sign-off.
5. **Runtime SOP**: single documented port, require `BAYESIANQC_DB_URL` in run scripts, note stale-process hazard—or automated smoke on 8010 after killing conflicts.

---

## Waiver template (if you intentionally ship the dev slice)

Explicitly waive P0-1/P0-2 for **local/dev only**, with accepted risk: “Full integration suite remains SQLite-backed; Postgres behavior validated only via `test_migrations.py` + manual smoke; no production cutover.” Without that, **P0/P1 stand as blocking.**
