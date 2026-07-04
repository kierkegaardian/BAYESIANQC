Performing a strict docs and workflow review per the packet: loading the review skill format and spot-checking key operator-facing docs (read-only).
# Grok Composer Review — Remediated Local/Dev Postgres Cutover (Docs & Operator Workflow)

**Date:** 2026-07-03
**Scope:** Docs, operator workflow, and review-packet accuracy for Postgres-first local/dev (not shared-lab production).
**Instruction:** Read-only; no file changes.

---

## Verdict

**Conditionally acceptable for local/dev Postgres-first operation**, with **one structural test gap (P0-1)** and **two operator-doc gaps (P1)** that should be fixed or explicitly waived before calling the cutover “signed off.”

Prior blockers on **AGENTS.md**, **8010 runtime smoke**, **copy-target warnings**, and **production/lab boundary** are largely remediated. Remaining issues are mostly **how evidence is labeled** and **small runbook inconsistencies**, not missing Alembic/Compose wiring.

---

## Prior blocker verification

| Prior issue | Status |
|-------------|--------|
| Validation wording (SQLite vs Postgres evidence) | **Partial** — README/AGENTS clarify `pytest` vs `make check-postgres`; review packet still aggregates gates without three labeled buckets. |
| Copy target clarity (`POSTGRES_COPY_URL`, disposable, truncate) | **Remediated** — README, `Makefile`, `MIGRATION_STRATEGY.md`, `VALIDATION_PACKAGE.md` align; `check-postgres` ≠ copy is stated in README. |
| `AGENTS.md` Postgres runbook | **Remediated** — Compose, default URL, `make check-postgres`. |
| Runtime smoke on **8010** | **Remediated** — packet cites 8010 after `stop_demo.sh`; `run_demo.sh` sets `BAYESIANQC_DB_URL` + seed flag. |
| Production / shared-lab boundary | **Remediated** — README points to readiness docs; packet and `MIGRATION_STRATEGY.md` cutover rule scope shared-lab separately. |

---

## P0 (blocking for local/dev unless waived)

### P0-1 — Default `pytest` is still not Postgres application coverage

`tests/conftest.py` pins a temp **SQLite** URL and `init_db()` on that path uses `create_all` + SQLite migrations, not the Postgres/Alembic startup path. The packet’s **`33 passed, 4 skipped`** is valid **SQLite regression**, not proof that ingestion, backlog, chart, quarantine, etc. behave the same on Postgres.

**Remediation already in docs:** README and AGENTS label default `pytest` as SQLite compatibility.
**Still blocking for a strict cutover sign-off** unless you **waive** with written acceptance: *Postgres app behavior is gated by `make check-postgres`, opt-in migration tests, and documented 8010 smoke—not the default suite.*

### P0-2 — Dual schema evolution paths (SQLite `user_version` vs Alembic)

Still true architecturally. Rehearsal + disposable Postgres tests reduce drift risk but do not replace a cross-engine integration gate or explicit “parity = migrations + copy + smoke only” statement in the **review packet** (docs already caveat this under remaining gaps).

**Waivable for local/dev** if the packet’s validation section is rewritten into explicit buckets (see P2-1).

---

## P1 (blocking for local/dev unless waived)

### P1-1 — `VALIDATION_PACKAGE.md` “Required Local Gates” still traps SQLite-minded operators

Section “Required Local Gates” still lists bare `pytest tests/test_migrations.py` and `python scripts/rehearse_sqlite_to_postgres.py` **without** requiring `BAYESIANQC_POSTGRES_TEST_URL` / Postgres URL context. On a fresh machine, Postgres-marked tests **skip** unless env is set.

`alembic.ini` now defaults to Compose Postgres (good), but the **wording split** between “local gates” and “Required Local/Dev Postgres Gate” is easy to mis-run. Operators who only execute the first block can believe migration validation passed when Postgres tests never ran.

**Fix:** Move Postgres-only lines out of the generic gate list, or prefix every Postgres command with required env vars and “skips without …”.

### P1-2 — `AGENTS.md` API key story disagrees with README / `run_demo.sh`

README quick start and `run_demo.sh` set `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`. **AGENTS.md** still says the default local key is `local-dev-key` and shows `uvicorn` **without** the seed export.

On Postgres-first startup without seeding, **`local-dev-key` may not exist** — operators following AGENTS alone will hit 401s despite the “default key” note.

### P1-3 — Copy rehearsal evidence is structurally weak for real SQLite imports

Packet notes current `bayesianqc.db` has **no QC records**, so copy rehearsal reported **`streams_checked: 0`**. That is honest but means the **documented import path** was not exercised on non-empty posterior/QC data in this validation run.

For a lab operator planning “import my old SQLite file,” **P1** until rehearsal is re-run against a seeded SQLite source (or waiver documents empty-source-only proof).

---

## P2 (non-blocking; clarity and packet hygiene)

| ID | Finding |
|----|---------|
| P2-1 | Review packet should label evidence in **three buckets**: (1) SQLite `pytest`, (2) `make check-postgres` / migration tests, (3) optional `migration-rehearse-postgres-copy` on disposable DB—not one narrative paragraph. |
| P2-2 | README copy snippet uses `$POSTGRES_COPY_URL` without an adjacent `export POSTGRES_COPY_URL=...` / “create disposable DB” line (the Testing section points to `make`—good, but the Postgres dev block is thinner). |
| P2-3 | `make check-postgres` runs `migration-rehearse-postgres` against the **shared** dev DB (smoke rows). Fine for dev; packet should say “non-clean-room” explicitly (known constraint partially covers this). |
| P2-4 | Readiness doc dates (2026-06-28) vs cutover packet (2026-07-03)—minor freshness signal; content matches remediated URLs/head. |
| P2-5 | CI: step 1 `make check` is SQLite-centric; step 2 adds Postgres—correct, but “CI is fully Postgres-first” is a misread. |
| P2-6 | Full lab pilot archive (`gen:api`, OpenAPI diff, functional matrices, JSON artifacts) — **shared-lab scope** per `LAB_READINESS.md`; not a local/dev cutover blocker if scope stays local/dev. |

---

## What is in good shape (credit)

- **Postgres-first runtime default** in `app/db.py` matches Compose URL; no silent SQLite fallback on normal startup.
- **`alembic.ini`** defaults to local/dev Postgres (fixes earlier CLI/SQLite trap).
- **`make check-postgres`** composition is clear in `Makefile`; README separates destructive copy to `migration-rehearse-postgres-copy`.
- **Posterior recomputation** in `scripts/rehearse_sqlite_to_postgres.py` checks `mu_n`/`kappa_n`/`alpha_n`/`beta_n` with `1e-9` tolerance—not merely `n_obs` (packet summary is accurate here).
- **8010 smoke** and **`run_demo.sh`** Postgres env + seed align with operator expectations when using the demo scripts.
- **Production/shared-lab** blockers are listed and not conflated with this slice.

---

## Minimum actions to clear P0/P1 for local/dev sign-off

1. **Packet:** Re-bucket validation evidence (SQLite vs Postgres migration vs optional copy); note empty SQLite source for copy proof or re-run with seeded DB.
2. **`VALIDATION_PACKAGE.md`:** Remove or relabel bare `pytest tests/test_migrations.py` in the generic gate so Postgres skips cannot be mistaken for pass.
3. **`AGENTS.md`:** Add `BAYESIANQC_SEED_LOCAL_DEV_KEY=1` to the Run API stanza (or document that keys must be created via `create_api_key.py` and drop “default local key” wording).

**Waiver (local/dev only):** Accept P0-1/P0-2 with: *“Integration suite remains SQLite-backed; Postgres cutover confidence = migration tests + `check-postgres` + 8010 smoke; no production/shared-lab claim.”*

Without waiver or the three doc/packet tweaks above, **P0-1 and P1-1/P1-2 remain blocking for a strict local/dev reviewer gate.** Shared-lab/regulated deployment remains **out of scope** and correctly **not** cleared by this slice.
