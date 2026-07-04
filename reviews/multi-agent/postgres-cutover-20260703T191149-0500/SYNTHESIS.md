# BayesianQC Postgres Cutover Reviewer Synthesis

Date: 2026-07-03
Scope: local/dev Postgres-first cutover only. Shared-lab/regulated production remains out of scope.

## Local/Dev Gate Decision
No unresolved P0/P1 findings remain for the local/dev Postgres cutover after the final focused AGY and Grok composer reviews.

## Reviewer Results
- AGY strict (`agy-strict.md`) initially blocked on stale port `8010`, weak posterior parity, and rollback/runbook gaps. Disposition: fixed by restarting demo through Postgres-backed scripts, adding posterior parameter recomputation, and documenting local rollback boundaries.
- Grok build (`grok-build.md`, `grok-build-followup2.md`) initially blocked on `alembic.ini`, downgrade coverage, posterior parity, and broader Postgres confidence. Disposition: fixed with Postgres Alembic default, downgrade/re-upgrade test, posterior recomputation, and an 8-test disposable Postgres suite including API smoke.
- Grok composer (`grok-composer.md`, `grok-composer-followup2.md`, `grok-composer-final.md`) initially blocked on unclear validation labeling, missing seed-env command, copy-target assumptions, and operator workflow gaps. Disposition: fixed by separating SQLite/Postgres evidence buckets, adding `BAYESIANQC_SEED_LOCAL_DEV_KEY=1` to AGENTS, provisioning disposable copy DBs in docs, and adding a Make target guard.
- AGY final (`agy-final.md`) verified the last P1s closed: `run_demo.sh` now waits for Postgres readiness, disposable DB creation is documented, and destructive copy target guarding is present.
- Claude (`claude-review.md`) could not run because the local Claude CLI is not logged in. Disposition: archived as a failed reviewer artifact; not counted as approval.
- Legacy Gemini (`gemini-legacy.md`) failed due local auth/client eligibility. Disposition: archived as a failed supplemental artifact; not counted as approval.

## Validation Receipt
- Static/SQLite: `pytest -q` passed with `33 passed, 5 skipped`; `pyright` passed; `ruff check app tests scripts` passed; `npm --prefix frontend run check` passed with the known Vite large chunk warning.
- Hygiene: `git diff --check` passed; anchored conflict-marker scan had no hits.
- Postgres: `make check-postgres` passed with Compose Postgres, Alembic upgrade, 8 migration/API tests, and schema/posterior rehearsal.
- Copy rehearsal: `make migration-rehearse-postgres-copy` passed against a `bayesianqc_disposable_rehearsal_*` target.
- Runtime: `scripts/run_demo.sh` starts Postgres, waits for readiness, starts backend on `8010` with Postgres URL and seed key, and starts frontend on `5177`; `/me` passed and `bayesianqc.db` was unchanged.

## Remaining Gaps
- Worktree is not a staged commit. Relevant untracked files must be included before PR/commit.
- Shared-lab/regulated deployment still requires generated cross-engine schema diff, stronger FK review, timezone hardening, backup/restore and rollback proof, OIDC/MFA, e-signature semantics, retention controls, and formal Bayesian validation.
- Direct script invocation of `scripts/rehearse_sqlite_to_postgres.py --copy-data --truncate-target` can still be destructive; the guarded documented path is `make migration-rehearse-postgres-copy`.
