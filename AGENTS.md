# Repo Agent Notes

<!-- GOVERNANCE_BASELINE_START -->
## Governance Baseline (Canonical)
- Project ID (portable): `BAYESIANQC`
- Path (current environment): `/home/user/projects/BAYESIANQC`
- Canonical origin (current): `git@github-account:kierkegaardian/BAYESIANQC.git`
- Default branch (current): `main`
- Stack / language (canonical): Python FastAPI backend + TypeScript/Vite frontend.
- File-size rule (enforced target): keep new files and heavily modified files (`>100` non-comment LOC changed or `>25%` of file touched) at `<= 300` LOC where practical; split into modules when larger. Exceptions are allowed for generated files, lockfiles, or legacy files when splitting would reduce clarity.
- Heavily-modified response (enforced): if modular splitting clearly improves maintainability, propose a split plan first; otherwise pause for user acknowledgement before committing any file that would exceed `400` LOC, and record the exception rationale in the handoff.
- Typesafety rule (enforced): apply stack-appropriate strict typing in every change (strict TypeScript for TS, Python type hints + pyright/mypy where configured, ShellCheck/input validation for shell, explicit declarations for Fortran/C# where applicable).
- Remote/push rule (enforced): do not change remotes or push destinations without explicit user confirmation; treat `origin` as canonical by default. This applies to human-in-the-loop agent actions and does not override already-approved CI automation.
- Workspace fast-path rule (enforced): for trivial, self-contained requests that do not touch files, secrets, infrastructure, active project state, or prior context, answer directly and skip continuity-ledger reads/updates, broad repo scans, discovery docs, and second-agent review; for non-trivial workspace/repo/infra/follow-up work, read the relevant context first and update continuity only when state materially changes.
<!-- GOVERNANCE_BASELINE_END -->

## Precedence
- Follow `/home/user/AGENTS.md` for workspace-wide rules and credential handling.

## Repo Summary
- Project ID (portable): `BAYESIANQC`
- Path (current environment): `/home/user/projects/BAYESIANQC`
- Stack: FastAPI QC prototype; API on 8010; Vue/Vite UI in `frontend/` (dev port 5177).
- Data: Postgres is the default local/dev database via Docker Compose on host port `54329`.
  Legacy SQLite databases are supported only as import inputs, never as app runtime databases.

## Common Commands (from README.md)
- Create venv and install: `python -m venv .venv` then `pip install -r requirements.txt`.
- Run API: `docker compose up -d postgres`, export
  `BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc`,
  export `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`, then run
  `uvicorn app.main:app --reload --port 8010`.
- Sample payload: `python scripts/post_sample_qc.py`.
- Run tests: `pytest`; the test harness creates a disposable Postgres database from
  `BAYESIANQC_POSTGRES_TEST_URL` or the local Compose URL.
- Frontend dev (from `frontend/package.json`): `npm run dev` in `frontend/`.

## Notes
- API requires `X-API-Key`; with `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`, the local admin key is
  `local-dev-key`.
- UI expects the API at `http://127.0.0.1:8010`.
 - UI dev server runs at `http://127.0.0.1:5177`.

## Quality
- **Typesafety (Request):** Enforce robust, stack-appropriate typesafety in all changes (Python type hints + pyright/mypy; strict TS types in the UI).
