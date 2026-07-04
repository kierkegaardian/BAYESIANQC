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
   docker compose up -d postgres
   export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
   export BAYESIANQC_SEED_LOCAL_DEV_KEY=1
   uvicorn app.main:app --reload --port 8010
   ```
3. The app applies Alembic migrations to Postgres on startup.
4. API calls require an `X-API-Key` header. With `BAYESIANQC_SEED_LOCAL_DEV_KEY=1`, the local admin key is `local-dev-key`; otherwise create keys with `scripts/create_api_key.py`.
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
Stored API-key hashes use salted PBKDF2. Legacy SHA-256 key hashes are migrated after successful authentication.

## Postgres dev database
Postgres is the only supported app runtime. The built-in default URL is:
`postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc`.

```bash
docker compose up -d postgres
export BAYESIANQC_DB_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc
export BAYESIANQC_SEED_LOCAL_DEV_KEY=1
uvicorn app.main:app --reload --port 8010
```
`init_db()` applies Alembic migrations automatically. The app rejects `sqlite://` URLs at startup; legacy SQLite files are import sources only.
See [Lab Readiness](docs/LAB_READINESS.md), [Validation Package](docs/VALIDATION_PACKAGE.md), and [Migration Strategy](docs/MIGRATION_STRATEGY.md) before any lab-like deployment.

To rehearse the current Postgres schema:
```bash
python scripts/rehearse_sqlite_to_postgres.py --postgres-url "$BAYESIANQC_DB_URL"
```

For a legacy SQLite import rehearsal only, create a disposable target and copy into it:
```bash
docker exec bayesianqc-postgres-1 dropdb -U bayesianqc --if-exists bayesianqc_disposable
docker exec bayesianqc-postgres-1 createdb -U bayesianqc bayesianqc_disposable
export POSTGRES_COPY_URL=postgresql+psycopg://bayesianqc:bayesianqc@127.0.0.1:54329/bayesianqc_disposable
python scripts/rehearse_sqlite_to_postgres.py \
  --postgres-url "$POSTGRES_COPY_URL" \
  --copy-data \
  --truncate-target
```
Only run the copy form against a disposable target; it truncates target rows when `--truncate-target` is present. The JSON output includes Alembic head/version checks, row-count parity, Postgres sequence checks, and posterior parameter recomputation.
Do not set `BAYESIANQC_DB_URL` to SQLite; the app will fail fast.

## Frontend UI (Vue + Element Plus)
```bash
cd frontend
npm install
npm run dev
```
The UI runs on `http://127.0.0.1:5177` and expects the API at `http://127.0.0.1:8010`.
Override the API base with `VITE_API_URL` in `frontend/.env.local`.
Every UI page includes a Help button with page purpose and basic usage notes.
Chart view now centers on the stream mean, shows color-coded 1/2/3 sigma bands using stream config limits, and uses a broken Y-axis when outliers exceed control limits (with an optional log-scale toggle).
Click chart points to resolve them (exclude from stats) or reinstate them.
The unattended chart kiosk is available at `http://127.0.0.1:5177/kiosk/charts`; the refinery demo kiosk is at `http://127.0.0.1:5177/kiosk/refinery` after loading `scripts/load_chart_kiosk_suite.py`.

## Endpoint map
- `GET /` Landing page with links and basic usage.
- `GET /docs` Interactive Swagger UI.
- `GET /redoc` Reference docs.
- `GET /me` Current role, API-key id, and permissions.
- `POST /qc/records` Ingest a QC record (requires `X-API-Key`).
- `POST /qc/records/csv` Ingest QC records from CSV (requires `X-API-Key`).
- `PATCH /qc/records/{record_id}/resolution` Resolve/reinstate a QC record (requires `X-API-Key` + approve permission).
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
- Start Postgres, then run the automated checks:
  ```bash
  docker compose up -d postgres
  pytest
  ```
  The test harness creates a disposable Postgres database from `BAYESIANQC_POSTGRES_TEST_URL` or the local Compose URL.
- Run the local/dev Postgres gate:
  ```bash
  make check-postgres
  ```
  For the destructive copy rehearsal, create a disposable target database and run `make migration-rehearse-postgres-copy POSTGRES_COPY_URL=postgresql+psycopg://...`.

## Documents
- [Software Requirements Specification](docs/SRS.md): Full, structured requirements including manual QC entry, workflow, and compliance expectations.
- [Tool Flow Diagram](docs/TOOL_FLOW_DIAGRAM.html): Browser-openable end-user and technical flow diagram.

## Roadmap

### Data & Persistence
- **Historical Risk Scores:** Persist the raw Bayesian Risk Score (0-100) for *every* data point (not just alerts) to enable historical risk trending.
- **Enhanced Audit:** Deepen audit logging to capture pre/post states for complex configuration changes (e.g., priors).

### Visualization & UI
- **Risk Trendline:** Add a secondary Y-axis to the Levey-Jennings chart to visualize the "Risk Score" trajectory over time.
- **Configuration UI:** Build dedicated UI forms for managing `StreamConfig` and `PriorConfig` (currently API-driven).
- **Uncertainty Visualization (Fan Charts):**
  - *Goal:* Visualize the evolution of belief over time by overlaying Credible Intervals (CI) for the mean and Predictive Intervals (PI) for future results on the Levey-Jennings chart.
  - *Research:*
    - "Fan Charts" (e.g., Bank of England inflation forecasts) for displaying widening/narrowing uncertainty.
    - Differentiating between "uncertainty of the mean" (narrow band) and "uncertainty of the next result" (wide band, comparable to SD limits).
    - Methods to optimize frontend rendering of shaded bands using ECharts `custom` series or `area` plots.

### Integration & Architecture
- **Webhooks & Notifications:**
  - Implement a webhook system to push "Risk Alerts" to a parent LIMS.
  - *Research:* Asynchronous task queues (e.g., Celery, ARQ) to handle email/Slack dispatch without blocking the ingestion API response.
- **OIDC/Auth:** Upgrade from static API keys to OIDC/OAuth2 for better integration with enterprise identity providers.

### Advanced Bayesian Models
- **Drift Detection (Time-Varying Mean):**
  - *Goal:* Detect gradual shifts in the process mean before they trigger traditional "Shift" rules.
  - *Research:*
    - **Dynamic Linear Models (DLM):** specifically the "Local Level Model" (random walk plus noise).
    - **Kalman Filter:** The classic recursive solution for linear Gaussian systems, which is mathematically equivalent to the Bayesian DLM for this use case.
    - Reference: *Bayesian Forecasting and Dynamic Models* by Harrison & West.
- **Lot-to-Lot Variation (Hierarchical Modeling):**
  - *Goal:* "Borrow strength" (shrinkage) across control material lots so that new lots with few data points yield stable risk estimates based on historical performance of previous lots.
  - *Research:*
    - **Bayesian Hierarchical / Multilevel Models:** Modeling `Result ~ Normal(Lot_Mean, Sigma)` where `Lot_Mean ~ Normal(Global_Mean, Tau)`.
    - **Partial Pooling:** How to balance between "no pooling" (treating every lot as independent) and "complete pooling" (ignoring lot differences).
    - Reference: *Bayesian Data Analysis* (Gelman et al.), specifically chapters on Hierarchical Models.
