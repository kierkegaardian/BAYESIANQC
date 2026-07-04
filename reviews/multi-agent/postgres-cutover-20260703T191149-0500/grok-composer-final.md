Verifying the four previously open P1s against the repo (read-only).


## Findings (focused P1 verification)

### Previously open P1-1 — `MIGRATION_STRATEGY.md` bare Postgres test command

**Status: closed.**

The doc no longer presents a single bare `pytest tests/test_migrations.py` as migration validation. It splits:

- **SQLite-only smoke** — two named tests, with an explicit line: *“Do not count this as the Postgres gate.”*
- **Postgres gate** — `export BAYESIANQC_POSTGRES_TEST_URL=…` immediately before `pytest tests/test_migrations.py`, plus `make check-postgres` as the equivalent one-liner.

An operator who follows the Postgres Rehearsal section gets the required env (or Make, which sets `POSTGRES_TEST_URL` in `test-postgres`). The follow-up P1 about stopping at a bare command block is remediated in the current tree.

---

### Previously open P1-2 — Disposable copy DB provisioning

**Status: closed.**

Copy runbooks now include explicit provisioning before `POSTGRES_COPY_URL` / `make migration-rehearse-postgres-copy`:

- `docs/MIGRATION_STRATEGY.md` (dropdb / createdb for `bayesianqc_disposable`)
- `docs/VALIDATION_PACKAGE.md` (same)
- `README.md` Postgres dev section (same)

The optional copy path is documented as turnkey against Compose Postgres, not “assume the DB exists.” Packet evidence that disposable copy passed after the safety guard is consistent with these steps.

---

### Previously open P1 — `run_demo.sh` readiness race

**Status: closed (no remaining P1).**

`scripts/run_demo.sh` calls `start_postgres` → `wait_for_postgres` (up to 40s, `pg_isready` via `docker compose exec`) **before** `start_backend`. Backend startup also sets `BAYESIANQC_DB_URL` and `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`.

**Residual (P2, not P1):** `docker compose up -d postgres` is not `--wait`; readiness relies on the polling loop. That is a reasonable local/dev barrier. If the backend PID file indicates an already-running process, Postgres is not re-checked — a stale-process edge case, not the original “backend starts before Postgres accepts connections” race.

---

### Previously open P1 — Copy target guard

**Status: closed for the documented operator path.**

`Makefile` target `migration-rehearse-postgres-copy`:

- Requires non-empty `POSTGRES_COPY_URL`
- Rejects URLs that do not contain `disposable`, `rehearsal`, or `test`
- Invokes the script with `--copy-data --truncate-target`

Packet validation (`bayesianqc_disposable_rehearsal_*` / `bayesianqc_disposable`) aligns with that guard. The main dev database URL `…/bayesianqc` does not match the pattern.

**Residual (P2):** `scripts/rehearse_sqlite_to_postgres.py` has no URL substring guard; only Makefile + docs steer operators. A direct script invocation with `--truncate-target` against a non-disposable URL could still truncate. That is an expert footgun, not an open P1 for the documented `make migration-rehearse-postgres-copy` workflow.

---

## P0 / P1 for local/dev (this scope only)

| Severity | Remaining for local/dev? |
|----------|---------------------------|
| **P0** | **No** — for the four targeted P1s and Postgres-first local/dev cutover described in the packet. |
| **P1** | **No** — MIGRATION_STRATEGY Postgres commands, disposable DB provisioning, `run_demo` readiness ordering, and copy-target guard are addressed in code/docs as verified above. |

Shared-lab / regulated items in the packet (schema-diff gate, backup/restore, OIDC/MFA, etc.) stay **out of scope** and are **not** counted here.

---

## Verdict

**Local/dev Postgres cutover is acceptable from a strict docs/operator perspective on these four P1s.** No file changes required for this review slice.

**Non-blocking notes (P2):** script-level copy guard parity with Makefile; `run_demo` could use `compose up --wait` as a polish; worktree still needs untracked cutover artifacts committed before PR/CI reproducibility (process, not runtime).
