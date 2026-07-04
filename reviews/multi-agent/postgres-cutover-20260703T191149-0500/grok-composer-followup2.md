Conducting a read-only review: verifying prior blockers and scanning docs, Makefile, and migration tooling against the review packet.


# Second Grok Composer Follow-Up — Local/Dev Postgres Cutover (Docs & Operator Workflow)

**Date:** 2026-07-03
**Scope:** Local/dev Postgres-first cutover, migration validation, operator runbooks (not shared-lab production).
**Mode:** Read-only review against the supplied packet, git status, and targeted diff.

---

## Verdict

**Acceptable for local/dev Postgres-first operation** — prior P0/P1 doc blockers are largely closed in the current tree, packet, and gates. **Not merge-ready as a PR** until untracked cutover artifacts are added (process, not runtime).

Shared-lab / regulated deployment stays **out of scope** and **not cleared** by this slice.

---

## Prior blocker verification

| Prior blocker | Status | Notes |
|---------------|--------|--------|
| **AGENTS seed env** (`BAYESIANQC_SEED_LOCAL_DEV_KEY=1`) | **Remediated** | Run API stanza and Notes match README / `run_demo.sh`; no implied `local-dev-key` without seed. |
| **Validation package labeling** (SQLite vs Postgres) | **Remediated** | `docs/VALIDATION_PACKAGE.md` splits **Required Static And SQLite Compatibility Gates** vs **Required Local/Dev Postgres Gate**; line 17 states bare `pytest` and bare rehearsal are not the Postgres gate; line 80 scopes pilot bundle. |
| **Evidence buckets** | **Remediated** | Packet uses three sections: Static/SQLite, Local/Dev Postgres Gate, SQLite-To-Postgres Rehearsal. |
| **Copy target export** (`POSTGRES_COPY_URL`) | **Remediated** | README Postgres block exports `POSTGRES_COPY_URL`; Makefile fails if unset; destructive/truncate behavior documented. |
| **Worktree inclusion note** | **Remediated** | Packet lists untracked cutover files and warns against `git diff --stat` alone. |
| **Empty SQLite-source caveat** | **Remediated** | Packet documents `streams_checked: 0` on empty `bayesianqc.db`; seeded copy/posterior parity is in `tests/test_migrations.py` (`test_sqlite_to_postgres_copy_preserves_counts_sequences_and_posterior`, `streams_checked == 1`). |

---

## Findings (severity order)

### P0 — None blocking for local/dev (given current docs/tests/packet)

No open P0 for local/dev that is unaddressed by the packet, `make check-postgres`, opt-in migration tests (`8 passed` with `BAYESIANQC_POSTGRES_TEST_URL`), and documented 8010 smoke.

**Waived / accepted architectural note (not a local/dev blocker):** Default `pytest` remains SQLite-centric via `tests/conftest.py`. That is **explicitly labeled** in README, AGENTS, `VALIDATION_PACKAGE.md`, and packet bucket 1. Postgres app paths are covered by bucket 2 (migration tests include API smoke) and packet runtime smoke.

---

### P1

#### P1-1 — `docs/MIGRATION_STRATEGY.md` still implies Postgres migration tests without env

```25:29:docs/MIGRATION_STRATEGY.md
The automated migration test covers those checks with:
```bash
pytest tests/test_migrations.py
```
This command runs SQLite-compatible migration coverage unless `BAYESIANQC_POSTGRES_TEST_URL` is set.
```

The caveat is on the **next** line; an operator who stops at the command block can believe full migration validation ran while **five** Postgres tests **skip** without `BAYESIANQC_POSTGRES_TEST_URL`. `VALIDATION_PACKAGE.md` and README Testing are clearer; this file lags.

**Local/dev impact:** Mis-run gate, not a code defect. **Mitigation in packet:** `make check-postgres` / `test-postgres` set the env. **Blocking only if** operators are told to follow `MIGRATION_STRATEGY.md` alone without `make check-postgres`.

#### P1-2 — Disposable copy target DB is not provisioned in runbooks

Copy examples use `…/bayesianqc_disposable`, but `docker-compose.yml` only creates `bayesianqc`. The rehearsal script runs `alembic upgrade` against the URL and does not `CREATE DATABASE`. First-time copy rehearsal fails until an operator creates the database manually (tests create temp DBs themselves; copy docs do not mirror that).

**Local/dev impact:** Optional copy path is documented but **not turnkey**. Packet evidence for disposable copy assumes a DB that exists; empty-source caveat is honest; **seeded import proof** is test-backed, not live-`bayesianqc.db`-backed.

---

### P2

| ID | Finding |
|----|---------|
| **P2-1** | `VALIDATION_PACKAGE.md` opens the Postgres gate with “Use a disposable local Postgres target” but then uses the shared Compose DB `bayesianqc` for `alembic upgrade` and `--postgres-url "$BAYESIANQC_DB_URL"`. Accurate for dev smoke; wording conflicts with “disposable” (temp DBs are only inside migration tests). |
| **P2-2** | `make check-postgres` runs `migration-rehearse-postgres` on the **persistent** dev DB (smoke rows). Packet “Known Constraints” covers this; worth one explicit line in README Testing that rehearsal JSON on dev may show `streams_checked: 0` on an empty SQLite file while posterior checks still run on Postgres data. |
| **P2-3** | Readiness/validation doc headers dated **2026-06-28** vs packet **2026-07-03** — content aligns with head `20260703_0002`; minor freshness signal only. |
| **P2-4** | CI: `make check` then Postgres steps — correct split; “CI equals full Postgres app suite” would be a misread (same as default `pytest`). |
| **P2-5** | **PR hygiene:** Large untracked cutover surface (`alembic.ini`, `docker-compose.yml`, `Makefile`, `.github/`, `migrations/`, rehearsal script, migration tests, readiness docs). Local/dev works in the worktree; **merge/CI reproducibility** needs inclusion before sign-off as a commit. |

---

## Packet accuracy spot-check

| Claim | Assessment |
|-------|------------|
| Default runtime URL in `app/db.py` | Matches targeted diff / `DEFAULT_DB_URL`. |
| `make check-postgres` composition | Matches `Makefile` (no copy target in that target). |
| `33 passed, 5 skipped` default `pytest` | Consistent with SQLite default + skipped Postgres-only tests elsewhere in suite. |
| `8 passed` migration tests with Postgres URL | Matches eight tests in `tests/test_migrations.py` (3 always-on + 5 disposable Postgres). |
| Posterior `1e-9` tolerance | Present in rehearsal script (`_POSTERIOR_TOLERANCE`). |
| Worktree vs staged commit | Accurate per supplied `git status`. |

---

## Operator workflow summary (recommended path)

1. **Daily dev:** `docker compose up -d postgres` → `BAYESIANQC_DB_URL` + `BAYESIANQC_SEED_LOCAL_DEV_KEY=1` → `uvicorn` or `scripts/run_demo.sh`.
2. **Regression (SQLite):** `pytest` (and static gates in `VALIDATION_PACKAGE.md` as needed).
3. **Postgres cutover gate:** `make check-postgres` (or equivalent env from `VALIDATION_PACKAGE.md` § Required Local/Dev Postgres Gate).
4. **Optional destructive copy:** Create `bayesianqc_disposable` (or another throwaway DB) → `export POSTGRES_COPY_URL=…` → `make migration-rehearse-postgres-copy`.

---

## Minimum actions to clear remaining P1 for a strict local/dev reviewer gate

1. **`MIGRATION_STRATEGY.md`:** Replace bare `pytest tests/test_migrations.py` with `BAYESIANQC_POSTGRES_TEST_URL=… pytest …` or `make test-postgres` / `make check-postgres`.
2. **Copy runbook:** Add one line to create the disposable database (e.g. `psql` / `createdb` against Compose) before `migration-rehearse-postgres-copy`.

**Waiver (local/dev):** Accept P1-2 if sign-off text states: *“SQLite-to-Postgres copy with QC/posterior parity is proven in disposable Postgres tests; live `bayesianqc.db` copy rehearsal is optional and may be empty-source.”*

---

## Shared-lab / production

Remaining gaps in the packet (cross-engine schema-diff gate, FK coverage, timezone hardening, backup/restore, OIDC/MFA, e-signatures, formal Bayesian validation) remain **P0/P1 for shared-lab**, correctly **excluded** from this local/dev slice. No change to that boundary in this follow-up.
