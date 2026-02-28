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
<!-- GOVERNANCE_BASELINE_END -->

## Precedence
- Follow `/home/user/AGENTS.md` for workspace-wide rules and credential handling.

## Repo Summary
- Project ID (portable): `BAYESIANQC`
- Path (current environment): `/home/user/projects/BAYESIANQC`
- Stack: FastAPI QC prototype; API on 8010; Vue/Vite UI in `frontend/` (dev port 5177).
- Data: SQLite database at `./bayesianqc.db`.

## Common Commands (from README.md)
- Create venv and install: `python -m venv .venv` then `pip install -r requirements.txt`.
- Run API: `uvicorn app.main:app --reload --port 8010`.
- Sample payload: `python scripts/post_sample_qc.py`.
- Run tests: `pytest`.
- Frontend dev (from `frontend/package.json`): `npm run dev` in `frontend/`.

## Notes
- API requires `X-API-Key`; default local key: `local-dev-key` (admin) or set `BAYESIANQC_API_KEY`.
- UI expects the API at `http://127.0.0.1:8010`.
 - UI dev server runs at `http://127.0.0.1:5177`.

## Quality
- **Typesafety (Request):** Enforce robust, stack-appropriate typesafety in all changes (Python type hints + pyright/mypy; strict TS types in the UI).
