# BAYESIANQC

This repository captures requirements for a Bayesian-enabled laboratory quality control platform **and** a working prototype API that exercises core ingestion, rule evaluation, Bayesian-style risk scoring, alert creation, and audit logging for manual and automated QC data.

## Bayesian justification
Bayesian priors represent the expected in-control mean/variance for a QC stream. Each incoming QC value updates a persistent posterior state (Normal-Inverse-Gamma update). Using that posterior, the system computes the predictive probability that the next value falls outside configured action limits (target +/- action_limit_sd * sigma), converts it into a 0-100 risk score, and uses it to influence disposition thresholds. In parallel, frequentist Westgard-style rules (1-3s, 2-2s, R-4s, 4-1s, 10x) are evaluated. Notifications are triggered when either rule violations occur or the Bayesian risk score crosses configured warning/hold thresholds.

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
3. The app creates a local SQLite DB at `./bayesianqc.db` on first run.
4. API calls require an `X-API-Key` header. Default local key: `local-dev-key` (admin) or set `BAYESIANQC_API_KEY`.
5. Open `http://127.0.0.1:8010/docs` or ingest QC data (manual or automated) against the seeded HbA1c stream using the `/qc/records` endpoint. The API returns frequentist signals (1-3s/2-2s/R-4s/4-1s/10x), Bayesian-style risk, disposition, duplicate detection, and an audit entry. Alerts are created for action/warning states.

## Sample payload helper
Post a fresh timestamped payload against the running API:
```bash
python scripts/post_sample_qc.py
```
To target a different host or port:
```bash
python scripts/post_sample_qc.py --base-url http://127.0.0.1:8010
```

## CSV ingestion
```bash
curl -X POST http://127.0.0.1:8010/qc/records/csv \
  -H "X-API-Key: local-dev-key" \
  -F "file=@samples/qc_records_sample.csv"
```

## API key provisioning
```bash
python scripts/create_api_key.py --role qc_analyst --description "local tester"
```

## Frontend UI (Vue + Element Plus)
```bash
cd frontend
npm install
npm run dev
```
The UI runs on `http://127.0.0.1:5173` and expects the API at `http://127.0.0.1:8010`.
Override the API base with `VITE_API_URL` in `frontend/.env.local`.
Every UI page includes a Help button with page purpose and basic usage notes.

## Endpoint map
- `GET /` Landing page with links and basic usage.
- `GET /docs` Interactive Swagger UI.
- `GET /redoc` Reference docs.
- `POST /qc/records` Ingest a QC record (requires `X-API-Key`).
- `POST /qc/records/csv` Ingest QC records from CSV (requires `X-API-Key`).
- `GET /instruments` List instruments.
- `POST /instruments` Create an instrument (requires `X-API-Key` + edit permission).
- `PATCH /instruments/{instrument_id}` Update an instrument (requires `X-API-Key` + edit permission).
- `GET /methods` List methods.
- `POST /methods` Create a method (requires `X-API-Key` + edit permission).
- `PATCH /methods/{method_id}` Update a method (requires `X-API-Key` + edit permission).
- `GET /analytes` List analytes.
- `POST /analytes` Create an analyte (requires `X-API-Key` + edit permission).
- `PATCH /analytes/{analyte_id}` Update an analyte (requires `X-API-Key` + edit permission).
- `GET /streams` List active stream configs.
- `GET /streams/{stream_id}/configs` List all versions for a stream.
- `POST /streams` Create a new stream config (requires `X-API-Key` + edit permission).
- `POST /streams/{stream_id}/configs` Create a new version for a stream (requires `X-API-Key` + edit permission).
- `POST /streams/{stream_id}/priors` Create a Bayesian prior config (requires `X-API-Key` + edit permission).
- `GET /streams/{stream_id}/priors` List prior versions for a stream.
- `POST /qc/events` Ingest non-result QC events (requires `X-API-Key`).
- `GET /qc/events` List QC events.
- `GET /alerts` List alerts.
- `PATCH /alerts/{alert_id}` Update alert status/assignment (requires `X-API-Key` + approve permission).
- `POST /investigations` Create an investigation (requires `X-API-Key` + approve permission).
- `GET /investigations` List investigations.
- `PATCH /investigations/{investigation_id}` Update an investigation (requires `X-API-Key` + approve permission).
- `POST /capas` Create a CAPA (requires `X-API-Key` + approve permission).
- `GET /capas` List CAPAs.
- `PATCH /capas/{capa_id}` Update a CAPA (requires `X-API-Key` + approve permission).
- `GET /audit` Audit log entries.
- `GET /reports/summary` Summary counts for alerts/investigations/CAPAs.
- `GET /streams/{stream_id}/chart` Chart data for a stream (records + events + alerts + lot segments).

## Testing
- Install dependencies with `pip install -r requirements.txt` (inside your virtualenv).
- Run the automated checks:
  ```bash
  pytest
  ```

## Documents
- [Software Requirements Specification](docs/SRS.md): Full, structured requirements including manual QC entry, workflow, and compliance expectations.

## Roadmap

### Data & Persistence
- **Historical Risk Scores:** Persist the raw Bayesian Risk Score (0-100) for *every* data point (not just alerts) to enable historical risk trending.
- **Enhanced Audit:** Deepen audit logging to capture pre/post states for complex configuration changes (e.g., priors).

### Visualization & UI
- **Risk Trendline:** Add a secondary Y-axis to the Levey-Jennings chart to visualize the "Risk Score" trajectory over time.
- **Configuration UI:** Build dedicated UI forms for managing `StreamConfig` and `PriorConfig` (currently API-driven).

### Integration & Architecture
- **Webhooks:** Implement a webhook system to push "Risk Alerts" to a parent LIMS, decoupling the response cycle.
- **OIDC/Auth:** Upgrade from static API keys to OIDC/OAuth2 for better integration with enterprise identity providers.
