# Repo Agent Notes

## Precedence
- Follow `/home/user/AGENTS.md` for workspace-wide rules and credential handling.

## Repo Summary
- Path: `/home/user/BAYESIANQC`.
- Stack: FastAPI QC prototype; API on 8010; Vue/Vite UI in `frontend/`.
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
