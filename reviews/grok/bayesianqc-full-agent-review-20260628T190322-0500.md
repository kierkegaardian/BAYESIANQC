**Findings first (strict senior lab QC reviewer, 2026-06-28 packet + current tree).**

BAYESIANQC is a working FastAPI + Vue prototype exercising core Bayesian + frequentist QC ingestion, evaluation, alerting, basic workflows, and charting. It is **not** lab-ready. Core math + persistence + UI for the happy path exist and pass current checks (13 pytest, pyright 0, ruff clean, npm typecheck/build ok except Vite chunk warning). However, multiple P0 defects directly contradict the SRS, break RBAC expectations, and prevent defensible use under CLIA/CAP/ISO 15189 or 21 CFR Part 11-like controls.

Citations are from the supplied packet (FILE: excerpts, git status, API probes, checks) + current workspace reads of the same paths.

### 1. Current implemented feature set (what actually exists)

**Ingestion & evaluation (core)**
- `POST /qc/records` + CSV: full payload validation, units normalization, bounds, duplicate detection (exact + possible), snapshot `raw_payload`, `signals`/`bayesian_risk`/`disposition` persisted on `QCRecord`. Idempotency-Key supported. Out-of-order triggers reprocess. (app/main.py:652 (process_ingestion), 510; app/storage.py:266 (detect_duplicate); packet API probe + samples)
- Frequentist: 1-3s (action), 2-2s/R-4s/4-1s/10x (warn) using recent included values + per-config baseline (fixed or date range). (app/frequentist.py:30; app/evaluations.py:120)
- Bayesian: Normal-Inverse-Gamma update, predictive P(outside warn/action) using Student-t (df<30) or normal approx, risk_score = round(P_action * 100), streaks for consecutive policy, credible/predictive intervals. Persistent `PosteriorState` + versioned `PriorConfig`. `infer_risk_as_of` + rebuild for history. (app/bayesian.py:160 (_update_posterior), 230 (_risk_from_posterior), 610 (infer_risk), 460 (rebuild); packet Bayesian justification)
- Hybrid disposition: REJECT on any ACTION signal; HOLD_FOR_REVIEW on hold streak; MONITOR on signals or warn streak; else ACCEPT. (app/main.py:300 (determine_disposition); app/domain.py:10)

**Master data + config**
- Versioned `StreamConfig` (limits, risk thresholds, bayes_*_prob + consecutive, rule_set JSON, effective_from) + `PriorConfig`. `GET /streams`, `.../configs`, priors. Basic Instrument/Method/Analyte CRUD. Seeded HbA1c stream. (app/models.py:1130 (StreamConfigBase validators); app/storage.py:140 (create_stream_config); packet endpoint map)

**Workflows**
- Alerts created on non-ACCEPT. PATCH status/assign/due. Convert to Investigation (problem, containment, outcome taxonomy, links). CAPA (DRAFT→...→CLOSED, root cause + actions + owners + due + verification + effectiveness_criteria required on approve). Resolution (include_in_stats toggle + reprocess). Events (lot/cal/maintenance etc). (app/main.py:1112 (alerts), 1178 (investigations), 1250 (capas); app/db_models.py:1550 (AlertRecord etc); packet REQ-INV/REQ-CAPA)

**UI + chart**
- Vue + ECharts: results LJ chart (mean-centered, 1/2/3σ bands from config, broken axis + log toggle for outliers), separate risk plot (P(outside) lines + alerts), lot segments, click-to-resolve points. Help buttons everywhere. Streams/Ingestion/Alerts/Events/Investigations/CAPAs/Instruments etc pages. Login stores API key. (frontend/src/pages/ChartView.vue: packet 1041-1300 excerpts + current template lines 20-40 (mode, log, risk series with markArea/markLine); packet README ChartView notes)

**Audit + infra**
- `AuditEntry` (actor=role, before/after JSON, reason) on ingest/resolve/config changes. SQLite `PRAGMA user_version` migrations (v4: evaluations columns). `GET /audit`, `/reports/summary`, `/streams/.../chart`. OpenAPI, CORS. (app/migrations.py:70; app/storage.py:320 (record_audit); app/db_models.py:1610; packet REQ-AUD)

**Not implemented** (per SRS + packet roadmap): full manual entry form + batch UI, webhooks, OIDC/MFA, hierarchical lot/instrument models, fan charts/uncertainty viz, backtest validation pack, proper service/repo layering (ARCHITECTURE.md target not reached), config UI forms, retention/legal hold, PDF export, drift model, etc.

### 2. Real bugs / regressions / security / compliance gaps (P0 > P1 > P2)

**P0 (must fix before any lab data or audit)**
- **Field optionality broken (causes documented 422)**: `QCRecordIn` declares `operator_id`, `reagent_lot`, `calibration_status`, `run_id`, `comments` as `Optional[str]` without `= None`. Pydantic v2 requires the keys. Packet explicitly: "minimal QC payload omitting optional ... returns 422". (app/models.py:71-79 from packet + grep; contrasts with `flags: ... = None`)
- **RBAC is inverted for readers/auditors**: `ROLE_PERMISSIONS` gives AUDITOR `[]` and DATA_STEWARD only `EDIT_CONFIG`. Every read (`GET /streams`, `/instruments`, `/alerts`, `/audit`, `/capas` etc.) does `require_permission(Permission.INGEST_QC)`. Packet probe confirms: AUDITOR/DATA_STEWARD → 403 on GET /streams. (app/rbac.py:19; app/main.py:943 (list_streams), 729 (instruments), 1114 (alerts), 1360 (audit); packet "Fresh API probes")
- **Deprecated startup + hygiene**: `@app.on_event("startup")` (2 FastAPI deprecation warnings per packet checks). Uncommitted conflict markers in reviews/codex/latest.md block clean `git diff --check`. (app/main.py:130; packet conflict scan lines 1/232/266)
- **Audit invariants weak**: `_audit_out` raises if `after is None` (app/main.py:350). Ingestion audit uses role only (not key id or real actor). No auth events logged. `before` often None. (app/storage.py:320; TYPESAFETY_TODO.md in packet)
- **No transaction safety for concurrent ingestion**: PosteriorState updates and reprocess happen with commits inside helpers/storage; out-of-order path + CSV row rollback; no locking. ARCHITECTURE.md calls this out as current problem. (app/bayesian.py:650; app/evaluations.py:260; app/main.py:560)

**P1 (serious for correctness, ops, or compliance)**
- **Disposition + risk not always re-evaluated consistently** on config/prior changes or resolution; relies on full reprocess which mutates history. `include_in_stats=False` points still affect some recent-value windows? No. (app/evaluations.py:130 (recent deque only on include); packet reprocess script)
- **Duplicate detection too narrow** (only stream+ts+value+run_id for exact). No business-key or operator/lot awareness. (app/storage.py:266)
- **Persisted JSON evals untyped on read** (`signals`, `bayesian_risk` as `list[dict]` / `dict`). Re-hydration via `model_validate` can fail silently on schema drift. (app/db_models.py:1530; app/main.py:360)
- **Frontend bundle + auth surface**: Vite large chunk warning (packet npm check). UI is pure API-key passthrough (localStorage-style); no per-user identity, no logout that clears server state, no key rotation UI. All `/streams/.../chart` etc. still need the key. (frontend/src/api/client.ts:29; router/index.ts:144; packet)
- **Migrations + DB assumptions**: Custom PRAGMA only; no FKs enforced in all paths; SQLite default for "lab" prototype. No at-rest encryption. (app/db.py:30; app/migrations.py:80)
- **Capa/Investigation approval fields enforced only at PATCH, not model level**; `created_by` is always role string. (app/main.py:490 (validate_capa_fields); db_models)

**P2 (important but secondary)**
- Bayesian edge cases (alpha_n <=1, sigma=0, no priors, df=0) return minimal objects; `infer_risk_as_of` can short-circuit to risk=0. No PPC diagnostics or model-failure fallback surfaced to UI/audit (SRS REQ-BAYES-30/31).
- Baseline stats and frequentist use only included points but reprocess logic is duplicated across paths (evaluations.py vs bayesian.py).
- No rate limiting, key expiration, or IP scoping on API keys. `local-dev-key` is ADMIN and documented everywhere.
- Chart data and risk computation still compute-heavy on some paths despite persisted evals.
- No drift in `PosteriorState` or historical risk series separate from per-record snapshots (roadmap item).

### 3. What must be done before a real lab can use it (prioritized)

**P0 gates (do not load real QC data until fixed)**
1. Fix `QCRecordIn` + any other In models: add `= None` (or `Field(default=None)`) for all documented optionals. Add explicit required-field tests. (app/models.py:71)
2. RBAC overhaul: add `READ` (or split `VIEW_*`) permission. AUDITOR gets read-only on streams/alerts/audit/charts/etc. DATA_STEWARD gets EDIT_CONFIG + read. Update every `@app.get` and `require_permission`. Regenerate schema + update frontend contracts. (app/rbac.py, main.py ~20+ endpoints)
3. Replace `@app.on_event`; move seed to lifespan. Remove conflict markers; enforce `git diff --check` in CI.
4. Make audit robust: always write non-null `after`, record `api_key_id` + role, never raise on read. Add auth failure audit.
5. Add proper unit-of-work + locking (or optimistic) around ingestion + `PosteriorState`. Document single-writer or use Postgres row locks. (See ARCHITECTURE.md in packet)
6. Remove `local-dev-key` as default in all docs/scripts; require explicit provisioning. Add key metadata (owner, expires, last_used).

**P1 (lab usability + defensibility)**
- Enforce e-signature semantics on APPROVE actions (name + meaning + timestamp + reason); prevent same-user create+approve where policy requires segregation.
- Persist full risk score + posterior summaries per record historically (roadmap); expose in chart/exports.
- Strengthen duplicate + bounds + QC-level matching + raw-payload roundtrip tests. Cover out-of-order + resolution + reprocess end-to-end.
- Production DB path: documented Postgres + Alembic + TLS + at-rest (or validated FS), plus migration cutover script. Drop SQLite as sole option.
- CI: add generated OpenAPI drift check, key rotation test, RBAC matrix test, Bayesian math property tests. Fix Vite chunk.
- Frontend: make key storage explicit + scoped; add "current user/role" display; surface posterior_mean/sigma/predictive values (TYPESAFETY_TODO).

**P2 (full SRS / production)**
- Implement remaining SRS (manual entry form with preview + keyboard flow, webhooks/notifications, effectiveness auto-eval, config UI, retention, reports export).
- Add validation pack / backtest workspace + promotion gates (REQ-VAL).
- Address roadmap items only after the above (no unrelated rewrites).
- Threat model + pen-test equivalent for API key handling, audit tamper-evidence, CORS.

**Bottom line**: The prototype proves the Bayesian + Westgard hybrid concept and has clean math + persisted evaluations. The gaps (especially RBAC, required-optionals, auth model, audit strength, and SQLite-for-lab) are not cosmetic—they make the system non-compliant and unsafe for real QC data today. Fix the P0s, re-run the exact packet probes + full RBAC matrix + math regression suite, then reassess.

No extraneous architecture proposals. All citations traceable to packet file contents or the matching paths in the current tree.
