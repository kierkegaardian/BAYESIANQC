Now let me read the truncated portion of the ARCHITECTURE.md section and examine key source files in detail.
Now I have a thorough understanding of the entire review packet. Let me launch subagents to examine the actual source files in parallel while I begin drafting the artifact.
I've launched parallel code analysis subagents and set a timer. I'll wait for their findings before assembling the full review artifact.

[From subagent 79568e21-9ab3-4d9f-a36a-b6361b4b1009 (Backend code reviewer)]

Here is a detailed summary of the BAYESIANQC backend code:

---

## 1. DB Models (`app/db_models.py`)

All models use SQLModel (Pydantic + SQLAlchemy).

### Models & Key Fields:

| Model | Key Fields | Notes |
|---|---|---|
| **ApiKey** | `id`, `key_hash`, `key_lookup_hash`, `role`, `description`, `created_at` | `key_lookup_hash` enables O(1) lookup without full-table scan |
| **Instrument** | `id`, `name`, `serial_number`, `status`, `site` | `status` defaults to `"active"` |
| **Method** | `id`, `name`, `version`, `instrument_id` | Links to Instrument |
| **Analyte** | `id`, `name`, `units`, `method_id` | Links to Method |
| **StreamConfig** | `id`, `stream_id`, `version`, `analyte_id`, `method_id`, `instrument_id`, `qc_level`, `lot_number`, `units`, `target`, `warning_limit_sd`, `action_limit_sd`, `baseline_window`, `bayesian_enabled`, `risk_warning_threshold`, `risk_hold_threshold`, `risk_hold_persistence`, `effective_from`, `created_at`, `created_by` | Versioned config with composite uniqueness on `(stream_id, version)`. **Index on `(stream_id, effective_from)`**. |
| **PriorConfig** | `id`, `stream_id`, `version`, `mu0`, `kappa0`, `alpha0`, `beta0`, `effective_from`, `created_at`, `created_by` | NIG prior params. Index on `(stream_id, effective_from)`. |
| **PosteriorState** | `id`, `stream_id` (unique), `mu_n`, `kappa_n`, `alpha_n`, `beta_n`, `n_obs`, `updated_at` | Single row per stream. Unique constraint on `stream_id`. |
| **QCRecord** | `id`, `stream_id`, `value`, `units`, `timestamp`, `operator_id`, `reagent_lot`, `run_id`, `entry_mode`, `flags`, `include_in_stats`, `resolved_by`, `resolution_reason`, `resolved_at`, `signals`, `bayesian_risk`, `disposition`, `ingested_at`, `source` | **Index on `(stream_id, timestamp)`**. `signals` and `bayesian_risk` stored as JSON strings. |
| **QCEvent** | `id`, `stream_id`, `event_type`, `timestamp`, `metadata_json`, `description`, `created_at` | Non-result events (calibration, maintenance, etc.) |
| **AlertRecord** | `id`, `stream_id`, `qc_record_id`, `severity`, `rule`, `message`, `status`, `acknowledged_by`, `reason`, `created_at`, `updated_at` | **Index on `(stream_id, created_at)`**. |
| **Investigation** | `id`, `title`, `stream_id`, `description`, `status`, `outcome`, `created_by`, `created_at`, `updated_at`, `reason` | Linked to alerts via `InvestigationAlertLink`. |
| **InvestigationAlertLink** | `investigation_id`, `alert_id` | M:N link table. |
| **Capa** | `id`, `title`, `stream_id`, `root_cause`, `corrective_action`, `preventive_action`, `status`, `owner`, `due_date`, `created_by`, `created_at`, `updated_at`, `reason` | |
| **CapaLink** | `capa_id`, `alert_id`, `investigation_id` | Links CAPA to alerts and investigations. |
| **AuditEntry** | `id`, `entity_type`, `entity_id`, `action`, `actor`, `actor_role`, `api_key_id`, `before`, `after`, `reason`, `timestamp` | Immutable audit log. |
| **IngestionReceipt** | `id`, `idempotency_key` (unique, indexed), `response_json`, `created_at` | Idempotent ingestion support. |

### Issues:
- **No foreign key constraints** are declared between models (e.g., `QCRecord.stream_id` → `StreamConfig.stream_id`). This is by design for SQLite flexibility but weakens referential integrity.
- **No `updated_at` on PosteriorState** for optimistic concurrency — wait, it does have `updated_at`. ✓
- **JSON string storage** for `signals` and `bayesian_risk` — works but limits queryability.

---

## 2. Bayesian Module (`app/bayesian.py`)

~460 lines. Implements Normal-Inverse-Gamma (NIG) conjugate updating from scratch (no external stats library).

### Key Functions:

| Function | Lines | Purpose |
|---|---|---|
| `_clamp01` | 21 | Clamp float to [0,1] |
| `_normal_cdf` | 25 | Normal CDF via `math.erfc` |
| `_beta_continued_fraction` | 31 | Lentz's algorithm for incomplete beta |
| `_regularized_incomplete_beta` | 74 | Regularized incomplete beta function |
| `_student_t_cdf` | 94 | Student-t CDF via incomplete beta |
| `_student_t_ppf` | 107 | Student-t inverse CDF (bisection method) |
| `_student_t_interval_quantile` | 139 | Cached 95% CI quantiles |
| `_interval_quantile` | 144 | Interval quantile with caching |
| `_update_posterior` | 153 | **Core NIG update**: takes (mu0, kappa0, alpha0, beta0, x) → (mu_n, kappa_n, alpha_n, beta_n) |
| `_probability_inside_bounds` | 167 | P(next value inside bounds) using predictive t-distribution |
| `_update_policy_streaks` | 184 | Tracks consecutive warning/hold threshold breaches for persistence-based alerting |
| `_risk_from_posterior` | 225 | Computes risk score (0-100), credible intervals, predictive intervals, policy state |
| `update_posterior_and_infer_risk` | 294 | **Main entry point**: full NIG update + risk inference + streak tracking |
| `_list_priors` | 330 | List all priors for a stream |
| `_active_prior` | 340 | Find effective prior at a timestamp |
| `infer_risk_as_of` | 353 | Recompute risk for a historical point by replaying records |
| `rebuild_posterior_state` | 459 | Full rebuild of posterior from all records (used after config/prior changes) |
| `infer_risk` | 601 | Compute risk from current posterior without updating |

### NIG Update Logic (lines 153-165):
```
kappa_n = kappa0 + 1
mu_n = (kappa0 * mu0 + x) / kappa_n
alpha_n = alpha0 + 0.5
beta_n = beta0 + 0.5 * kappa0 * (x - mu0)^2 / kappa_n
```
This is the standard conjugate update. ✓

### Risk Score Formula (lines 225-292):
- Computes degrees of freedom = 2 * alpha_n
- Predictive scale = sqrt(beta_n * (kappa_n + 1) / (alpha_n * kappa_n))
- P(inside action limits) via Student-t CDF
- Risk = (1 - P_inside) * 100, clamped to [0, 100]
- Credible intervals for mean: mu_n ± t_quantile * sqrt(beta_n / (alpha_n * kappa_n))
- Predictive intervals: mu_n ± t_quantile * predictive_scale

### Issues:
- **`rebuild_posterior_state` and `infer_risk_as_of` contain `session.commit()` calls** inside the function. This violates the architecture's "no commit in math/repos" rule. These should be moved to the service layer.
- The bisection-based `_student_t_ppf` is adequate but slow for high precision. Not a blocker but could be optimized.
- **No model diagnostics** (REQ-BAYES-30/31): no posterior predictive checks, no degenerate-state detection.

---

## 3. Frequentist Module (`app/frequentist.py`)

~95 lines. Implements Westgard multirules.

### Rules Implemented:
| Rule | Description | Severity |
|---|---|---|
| **1-3s** | Single value > 3 SD from target | ACTION |
| **2-2s** | 2 consecutive values > 2 SD same side | ACTION |
| **R-4s** | Range of last 2 values > 4 SD | ACTION |
| **4-1s** | 4 consecutive values > 1 SD same side | WARNING |
| **10x** | 10 consecutive values on same side of target | WARNING |

### What's Missing:
- **No CUSUM** chart logic (REQ-FREQ-03)
- **No EWMA** chart logic (REQ-FREQ-03)
- **No multi-level cross-rule evaluation** (REQ-FREQ-22): rules are evaluated per-stream only
- **No configurable rule sets**: the rule set is hardcoded
- **No 7T/8x trend rules** (common in ASTM D6299 context)
- **No severity customization** per rule

### Architecture:
- `evaluate_rules_for_values(value, recent_values, target, sigma)` → pure function ✓
- `evaluate_rules(record, recent_records, config)` → wrapper that computes target/sigma from config or baseline

---

## 4. Ingestion Service (`app/services/ingestion.py`)

~200 lines. This is the well-structured service extracted from main.py.

### Key Functions:

| Function | Purpose |
|---|---|
| `normalize_units` | Validates/converts units against stream config. Currently rejects mismatches; no actual conversion logic. |
| `validate_bounds` | Checks plausibility bounds (5 SD from target). Raises 422 on violation. |
| `determine_disposition` | Maps (signals, bayesian_risk) → Disposition enum |
| `alert_severity` | Maps Disposition → severity string |
| `alert_out` / `audit_out` | DTO mappers |
| `process_ingestion` | **Core orchestrator**: validates → deduplicates → normalizes → locks stream → evaluates freq rules → updates Bayesian posterior → determines disposition → creates alerts → records audit → stores receipt |

### Transaction Handling:
- Uses `stream_write_lock(session, stream_id)` for serialized access ✓
- The lock module (`app/services/locks.py`) uses `threading.RLock` for SQLite and `SELECT ... FOR UPDATE` for Postgres ✓
- `process_ingestion` operates within the caller's session — the commit happens in `main.py` endpoint

### Issues:
- `normalize_units` **rejects mismatches but doesn't convert**. REQ-DATA-11 requires controlled unit conversions.
- `validate_bounds` uses a hard-coded 5 SD bound. Should be configurable per stream.
- No **exception queue** for quarantining invalid records (REQ-DATA-12)

---

## 5. Evaluations Module (`app/evaluations.py`)

~70 lines. Handles reprocessing when historical state changes.

### Key Function:
- `reprocess_stream_evaluations(session, stream_id, *, commit=True)`:
  1. Loads all records ordered by timestamp
  2. For each record: re-evaluates frequentist rules + Bayesian risk
  3. Updates `signals`, `bayesian_risk`, `disposition` on each record
  4. Optionally commits

### Issues:
- Takes a `commit` parameter — partially violates the "services own transactions" rule
- Calls `infer_risk_as_of` from `bayesian.py` which itself may commit — double-commit risk
- **No batch optimization**: processes records one at a time. Could be slow for large streams.

---

## 6. Storage Module (`app/storage.py`)

~440 lines. Repository-like module for all CRUD operations.

### Functions (selected):

| Function | Lines | Issue? |
|---|---|---|
| `seed_defaults` | 50-175 | Seeds instruments, methods, analytes, streams, priors for demo. **Contains `session.commit()`** — should be in service layer. |
| `create_stream_config` | 176 | ✓ No commit |
| `get_active_stream_config` | 229 | ✓ Pure query |
| `create_prior_config` | 254 | ✓ |
| `baseline_stats` | 302 | Computes mean/SD from records. ✓ |
| `detect_duplicate` | 319 | Checks stream_id + timestamp + value. ✓ |
| `store_receipt` | 356 | **Contains `session.commit()`** — should be in caller |
| `record_audit` | 374 | ✓ No commit (adds to session, doesn't commit) |
| `create_alert` | 425 | **Has `commit` parameter** — partial violation |
| `update_alert` | 435 | **Contains `session.commit()`** |
| `create_investigation` | 442 | **Contains `session.commit()`** |
| `update_investigation` | 454 | **Contains `session.commit()`** |
| `create_capa` | 462 | **Contains `session.commit()`** |
| `update_capa` | 474 | **Contains `session.commit()`** |

### Summary of Commit Violations:
Multiple functions call `session.commit()` directly. The ARCHITECTURE.md explicitly states repos should never commit. This is a known tech-debt item for the service-layer refactor.

---

## 7. RBAC Module (`app/rbac.py`)

~85 lines.

### Roles (enum):
- `admin`, `qc_analyst`, `qc_supervisor`, `data_steward`, `auditor`

### Permissions (enum):
- `READ`, `INGEST_QC`, `APPROVE`, `EDIT_CONFIG`

### Role → Permission Mapping:
| Role | Permissions |
|---|---|
| admin | ALL |
| qc_analyst | READ, INGEST_QC |
| qc_supervisor | READ, INGEST_QC, APPROVE |
| data_steward | READ, EDIT_CONFIG |
| auditor | READ |

### Auth Flow:
1. Extract `X-API-Key` header
2. Compute `key_lookup_hash` for O(1) lookup
3. If not found, try legacy SHA-256 hash lookup
4. If found via legacy, migrate to PBKDF2 + set lookup hash
5. Verify PBKDF2 hash
6. Return `UserContext(role, api_key_id)`

### Issues:
- **No QA Manager role** (REQ-ROLE-01 requires it)
- **No segregation-of-duty** enforcement (REQ-ROLE-04)
- **No electronic signature capture** (REQ-ROLE-03)
- Roles are static per API key — no per-session role elevation or impersonation

---

## 8. Security Module (`app/security.py`)

~55 lines. Clean implementation.

- `legacy_sha256_hash`: SHA-256 for backward compat
- `api_key_lookup_hash`: Deterministic SHA-256 prefix for O(1) DB lookup
- `hash_api_key`: PBKDF2-HMAC-SHA256 with random salt, 600k iterations
- `verify_api_key`: Extracts salt from stored hash, recomputes, constant-time compare
- `api_key_hash_needs_migration`: Detects legacy hashes by format

✓ No issues found. Solid implementation.

---

## 9. Main Module (`app/main.py`)

~1100+ lines. Still the largest module. Contains all endpoint definitions plus significant business logic.

### Structure:
- Lines 1-105: Imports, model definitions for request/response DTOs
- Lines 106-140: Lifespan (DB init, migrations, seeding)
- Lines 140-270: HTML page generators (root, docs, redoc, /me)
- Lines 273-440: Helper functions (CSV parsing, lot segments, DTO mappers, validation)
- Lines 443-1156: All endpoint handlers

### Business Logic Still in main.py:
- `parse_csv_row`: CSV → QCRecordIn mapping
- `_lot_segments`: Computes lot transition segments from records
- `validate_capa_fields`: CAPA validation logic
- `require_reason`: Reason enforcement
- All endpoint handlers directly query DB via `session` parameter
- `resolve_qc_record` (line 476): Contains significant business logic (lock, refresh, update, reprocess, audit)
- Alert/Investigation/CAPA CRUD handlers contain inline DB operations

### Issues:
- **Massive god-module**: should be split per ARCHITECTURE.md plan
- **Business logic in endpoints**: resolution, alert update, investigation/CAPA lifecycle should be in services
- **Inline DB queries**: Endpoints directly use `session.exec(select(...))` instead of going through repos

---

## 10. Supporting Modules

### `app/domain.py` (12 lines):
- `SignalSeverity` enum: `WARNING`, `ACTION`
- `Disposition` enum: `ACCEPT`, `WARNING`, `HOLD`, `ACTION`

### `app/stats.py` (18 lines):
- `sample_mean_sd(values)`: Classical mean and population SD
- **No robust estimators** (median/MAD, trimmed mean) — required by REQ-FREQ-11

### `app/timeutils.py` (8 lines):
- `as_utc(value)`: Ensures datetime has UTC timezone

### `app/api_models.py` (~75 lines):
- Response models for CSV ingestion, alert/investigation/CAPA summaries, chart output, lot segments

---

## 11. DB Init & Migrations

### `app/db.py` (~55 lines):
- `_build_engine`: Creates SQLAlchemy engine from `BAYESIANQC_DB_URL` env var (defaults to SQLite)
- `_configure_sqlite`: Sets WAL mode, foreign keys ON, busy timeout
- `get_engine`: Singleton engine
- `get_session`: FastAPI dependency yielding sessions
- `init_db`: Creates tables via `SQLModel.metadata.create_all` + runs SQLite migrations

### `app/migrations.py` (~160 lines):
- SQLite-only migrations using `PRAGMA user_version`
- 6 migration steps (0→6)
- Handles column additions, index creation, and data backfills
- **No Alembic** — acknowledged in MIGRATION_STRATEGY.md as a pre-lab-deployment requirement

---

## 12. Locks Module (`app/services/locks.py`)

~50 lines. Clean implementation.

- `_sqlite_lock`: Thread-level `RLock` per stream_id (dict-based)
- `_is_sqlite`: Checks engine dialect
- `_lock_stream_row`: `SELECT ... FOR UPDATE` on PosteriorState for Postgres
- `stream_write_lock`: Context manager that picks SQLite lock or Postgres row lock

✓ Correct dual-strategy locking.

[From subagent fbdc35f4-f52c-45f8-8f5e-6dcc82747a3c (Frontend and test reviewer)]

Here is a detailed summary of the BAYESIANQC frontend, tests, and supporting files:

---

## 1. Frontend Vue Pages

### Pages Summary:

| Page | Key Features | API Calls | Missing/Issues |
|---|---|---|---|
| **Login.vue** | API key entry, role display, session storage | `GET /me` | No OIDC/SSO. No MFA. |
| **ChartView.vue** | Levey-Jennings chart with ECharts, sigma bands (1/2/3 SD), broken Y-axis for outliers, log-scale toggle, point click to resolve/reinstate, lot segment markers, event annotations, alert markers, CAPA annotations | `GET /streams/{id}/chart`, `PATCH /qc/records/{id}/resolution` | No risk trendline overlay. No fan charts/uncertainty bands. No stream comparison. No time-range picker (uses default). |
| **Streams.vue** | List streams, link to chart | `GET /streams` | No create/edit stream UI. No inline config display. |
| **Instruments.vue** | List/create/edit instruments | `GET/POST/PATCH /instruments` | Basic CRUD only. No status lifecycle. |
| **Methods.vue** | List/create/edit methods | `GET/POST/PATCH /methods` | Basic CRUD. |
| **Analytes.vue** | List/create/edit analytes | `GET/POST/PATCH /analytes` | Basic CRUD. |
| **Ingestion.vue** | CSV file upload | `POST /qc/records/csv` | No manual single-record entry form. No validation preview. No drag-and-drop. |
| **Alerts.vue** | List alerts, update status/assignment with reason | `GET /alerts`, `PATCH /alerts/{id}` | No filtering by severity/stream. No real-time updates. No SLA/due date display. |
| **Investigations.vue** | List/create/update investigations | `GET/POST/PATCH /investigations` | No link to alerts displayed. No attachments. |
| **Capas.vue** | List/create/update CAPAs with full field validation | `GET/POST/PATCH /capas` | No effectiveness check automation. No CAPA lifecycle visualization. |
| **Events.vue** | List/create QC events | `GET /qc/events`, `POST /qc/events` | No filtering. No chart integration from this page. |

### Common Patterns:
- All pages have a Help button (`el-dialog`) with page-specific guidance
- Use Element Plus components consistently
- All mutation operations pass `X-API-Key` from session storage
- Error handling via `ElMessage.error()` with API error detail extraction

---

## 2. Frontend API Layer

### `session.ts`:
- `getApiKey()` / `setApiKey()` / `clearApiKey()`: Session storage for API key
- `apiHeaders()`: Returns `{ 'X-API-Key': key }` headers
- `apiClient`: Configured axios instance with base URL from `VITE_API_URL` env var

### `schema.ts`:
- ~170 lines of TypeScript interfaces matching backend Pydantic models
- All API response types defined: `IngestionResult`, `StreamConfigOut`, `AlertOut`, `InvestigationOut`, `CapaOut`, `QCRecordChartOut`, `StreamChartOut`, etc.
- Bayesian risk fields: `risk_score`, `p_inside`, `credible_interval`, `predictive_interval`, `warning_streak`, `hold_streak`

### `contracts.ts`:
- Exports `API_BASE` constant
- Exports typed API path builders

---

## 3. Frontend Router (`index.ts`)

Routes:
- `/login` → Login
- `/` → Streams (default)
- `/streams/:id/chart` → ChartView
- `/instruments` → Instruments
- `/methods` → Methods
- `/analytes` → Analytes
- `/ingestion` → Ingestion
- `/alerts` → Alerts
- `/investigations` → Investigations
- `/capas` → Capas
- `/events` → Events

**Missing routes**: No audit log viewer page. No reports/dashboard page. No admin/user management page.

---

## 4. AppLayout.vue

- Sidebar navigation with Element Plus `el-menu`
- Header with app title
- Logout button (clears session, redirects to /login)
- Auth guard: redirects to /login if no API key in session
- Navigation items match all routes

---

## 5. Tests

### `test_ingestion.py` (~500 lines, 15 test cases):

| Test | What It Covers |
|---|---|
| `test_ingestion_rejects_missing_stream` | 404 on unknown stream |
| `test_units_mismatch_rejected` | 422 on wrong units |
| `test_action_signal_and_alert_created` | Full ingestion → signal → alert → audit pipeline |
| `test_minimal_qc_payload_accepts_documented_optional_fields` | Optional field handling |
| `test_read_roles_can_read_without_mutating` | RBAC: auditor can GET, cannot POST |
| `test_invalid_api_key_does_not_scan_pbkdf2_keys` | Auth perf: no full-table scan |
| `test_legacy_api_key_migrates_without_active_key_scan` | Legacy key migration |
| `test_audit_entries_include_actor_role_and_key` | Audit completeness |
| `test_resolution_reason_required_for_statistical_inclusion_changes` | Resolution workflow |
| `test_alert_update_requires_reason_and_uses_backend_actor` | Alert update with reason |
| `test_concurrent_same_stream_ingestion_keeps_posterior_count` | Concurrency correctness |
| `test_bayesian_risk_includes_intervals_and_policy_state` | Risk output shape |
| `test_bayesian_hold_requires_persistence` | Persistence-based alerting |
| `test_duplicate_detection` | Duplicate handling |
| `test_manual_entry_audited` | Manual entry audit trail |
| `test_bayesian_state_rebuilds_on_out_of_order_ingestion` | Out-of-order reprocessing correctness |
| `test_bayesian_state_resets_on_prior_change` | Prior change → full rebuild |

### `test_chart_kiosk.py` (~300 lines, 4 test cases):

| Test | What It Covers |
|---|---|
| `test_chart_kiosk_fixture_exercises_chart_annotations` | Full fixture load → chart data with events, alerts, lot segments, CAPA annotations |
| `test_chart_kiosk_loader_functions_are_idempotent` | Idempotent fixture loading |
| `test_chart_kiosk_loader_reports_bad_flags_json` | Error handling for malformed JSON |
| `test_chart_kiosk_loader_reports_bad_numeric_csv_data` | Error handling for bad CSV data |

### Missing Test Coverage:
- No negative RBAC tests for `data_steward` and `qc_supervisor` boundaries
- No test for CSV ingestion endpoint
- No test for CAPA lifecycle state transitions
- No test for investigation-alert linking
- No test for stream config versioning conflicts
- No performance/load tests
- No frontend E2E tests

---

## 6. Sample Data (`samples/`)

| File | Description |
|---|---|
| `qc_records_sample.csv` | Generic QC records CSV |
| `chart_kiosk_assets.json` | Instruments, methods, analytes for D86/HbA1c kiosk |
| `chart_kiosk_d86_events.json` | D86 distillation events |
| `chart_kiosk_d86_priors.json` | D86 Bayesian priors |
| `chart_kiosk_d86_records.csv` | D86 QC measurement records |
| `chart_kiosk_d86_streams.json` | D86 stream configs |
| `chart_kiosk_events.json` | HbA1c events |
| `chart_kiosk_prior.json` | HbA1c prior |
| `chart_kiosk_qc_records.csv` | HbA1c QC records |
| `chart_kiosk_stream.json` | HbA1c stream config |

---

## 7. Scripts

| Script | Purpose |
|---|---|
| `create_api_key.py` | CLI to create API keys with role |
| `post_sample_qc.py` | Posts a sample QC record for testing |
| `generate_openapi_json.py` | Exports OpenAPI spec to `openapi.json` |
| `load_chart_kiosk_suite.py` | Loads full kiosk demo fixture (assets, streams, priors, records, events) |
| `reprocess_stream_evaluations.py` | CLI to reprocess all evaluations for a stream |
| `run_demo.sh` | Starts backend + frontend for demo |
| `stop_demo.sh` | Stops demo processes |

---

## 8. Config Files

### `pyproject.toml`:
- Project name: `bayesianqc`
- Python ≥ 3.11
- Dependencies: fastapi, uvicorn, sqlmodel, pydantic, httpx
- Dev deps: pytest, pytest-asyncio, pyright, ruff
- Pyright and ruff configured

### `docker-compose.yml`:
- Single `postgres` service (PostgreSQL 17)
- Port 54329 → 5432
- Volume for data persistence
- DB: `bayesianqc`, user: `bayesianqc`, password: `bayesianqc`

### `Makefile`:
- Targets: `test`, `lint`, `typecheck`, `format`, `dev`, `demo`, `openapi`, `ci` (combines test+lint+typecheck+openapi-check)

### `.github/workflows/ci.yml`:
- Runs on push/PR to main
- Python 3.12 + Node 20
- Steps: install deps → pytest → pyright → ruff → frontend type-check → openapi schema drift check

---

## 9. Prior Review Artifacts

### Latest AGY review (`reviews/agy/bayesianqc-remediation-review-20260628T200526-0500.md`):
- Confirmed P0/P1 blockers fixed
- Stale-read blocker: fixed via `stream_write_lock` + `session.refresh`
- API key DoS: fixed via `key_lookup_hash`
- RBAC spoofing: fixed via server-side `user.actor`
- Audit reasons: enforced on all state changes

### Codex review (`reviews/codex/latest.md`):
- Positive review of remediation
- Notes remaining tech debt in main.py size
- Suggests continued service extraction

### Gemini reviews (`reviews/gemini/`):
- Multiple chart kiosk reviews from May 2026
- Focus on D86 distillation QC use case
- Recommendations for fan charts, risk trendlines, lot-to-lot modeling

---

Now I have everything I need to produce the comprehensive review artifact. Let me synthesize both subagent reports with my standards analysis.
Both subagents have reported back and the review artifact is complete. Let me also clean up the subagents.
The review is complete. Here's a summary of what I produced:

---

## Review Complete

The full artifact is at **[bayesianqc_standards_review_and_roadmap.md](file:///home/user/.gemini/antigravity-cli/brain/8c0c8e38-bbbc-4afe-9c89-ac07498ff7e5/bayesianqc_standards_review_and_roadmap.md)**.

### Key Conclusions

**No P0/P1 blockers remain.** The remediation was well-executed — PBKDF2 auth, RBAC spoofing, concurrency locking, and audit reason enforcement are all solid.

### Eight P2/P3 Findings
1. **Transaction boundary violations** — scattered `commit()` calls in storage.py, bayesian.py, evaluations.py
2. **Hardcoded rule sets** — labs can't configure which Westgard rules apply per stream (ASTM D6299 gap)
3. **No robust estimators** — only classical mean/SD; missing median/MAD and ISO 5725 Algorithm A
4. **No unit conversion** — rejects mismatches rather than converting with audit trail
5. **No quarantine queue** — implausible values discarded rather than held for review (ISO 8000 gap)
6. **No model diagnostics** — no posterior predictive checks or degenerate-state detection
7. **No FK constraints** — SQLModel models lack referential integrity declarations
8. **Incomplete audit `before` state** — config changes don't always serialize the prior version

### Four-Phase Roadmap (27 Features)
| Phase | Focus | Features |
|-------|-------|----------|
| **Phase 0 (MVP-Next)** | Demo-ready | Manual QC entry, audit viewer, dashboard, config UI, risk trendline, alert filtering |
| **Phase 1 (Lab-Readiness)** | ISO 17025 pilot | Configurable rules, CUSUM/EWMA, robust estimators, unit conversion, quarantine, model diagnostics, full audit, FKs, QA Manager + SoD, webhooks |
| **Phase 2 (Advanced)** | Bayesian differentiation | Drift detection DLM, lot-to-lot hierarchy, outlier model, backtesting, multi-stream comparison, fan charts, PT integration, CAPA effectiveness automation |
| **Phase 3 (Operational)** | Enterprise | OIDC/SSO, e-signatures, retention/legal hold, observability, LIMS mapping, ISO 8000 scoring, report generation, multi-tenant, API versioning |

### Repo Cleanup
17-item checklist covering `.gitignore` gaps, monolith decomposition sequencing, review artifact archival, test coverage gaps, and missing developer docs.

### Full SRS Traceability
All 80+ SRS requirements mapped to current status (✅/⚠️/❌) and roadmap phase.
