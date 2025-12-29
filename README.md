# BAYESIANQC

This repository captures requirements for a Bayesian-enabled laboratory quality control platform **and** a working prototype API that exercises core ingestion, rule evaluation, Bayesian-style risk scoring, alert creation, and audit logging for manual and automated QC data.

## Quick start
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Run the FastAPI app:
   ```bash
   uvicorn app.main:app --reload --port 8010
   ```
3. Open `http://127.0.0.1:8010/docs` or ingest QC data (manual or automated) against the seeded HbA1c stream using the `/qc/records` endpoint. The API returns frequentist signals (1-3s/2-2s), Bayesian-style risk, disposition, duplicate detection, and an audit entry. A placeholder alert is generated for action/warning states.

## Sample payload helper
Post a fresh timestamped payload against the running API:
```bash
python scripts/post_sample_qc.py
```
To target a different host or port:
```bash
python scripts/post_sample_qc.py --base-url http://127.0.0.1:8010
```

## Testing
- Install dependencies with `pip install -r requirements.txt` (inside your virtualenv).
- Run the automated checks:
  ```bash
  pytest
  ```

## Documents
- [Software Requirements Specification](docs/SRS.md): Full, structured requirements including manual QC entry, workflow, and compliance expectations.
