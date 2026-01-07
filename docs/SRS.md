# Bayesian QC Control and CAPA System — Software Requirements Specification

## 1. Introduction
This Software Requirements Specification (SRS) captures functional and non-functional requirements for a laboratory statistical quality control (SQC) platform that combines frequentist control charts and Bayesian risk assessment with end-to-end investigation and CAPA management. Requirements are organized to remain traceable to acceptance criteria and to support future design, validation, and audit activities.

## 2. Scope and Definitions (REQ-SCOPE)
- **REQ-SCOPE-01**: Support SQC using frequentist control charts/rules and Bayesian models that update as new QC data arrive.
- **REQ-SCOPE-02**: Link QC signals through investigation, CAPA, effectiveness checks, and closure.
- **REQ-SCOPE-03**: Treat each QC stream as a unique combination of analyte, method, instrument, site, matrix (if applicable), QC level, control-material lot, and units (configurable).

## 3. Users, Roles, and Permissions (REQ-SEC-ROLE)
- **REQ-ROLE-01**: Provide RBAC with at least: QC Analyst, Supervisor, QA Manager, Admin, Auditor/Read-only, Data/Model Steward.
- **REQ-ROLE-02**: Restrict who can edit master data, change chart parameters, change Bayesian priors/models, override dispositions, approve/close CAPA, and configure integrations.
- **REQ-ROLE-03**: Support electronic approvals (name, timestamp, meaning of signature) for investigation and CAPA transitions.
- **REQ-ROLE-04**: Support segregated duties policies (e.g., creator cannot be sole approver) as configurable.

## 4. Data Ingestion and Validation (REQ-DATA)
### 4.1 Inputs and Metadata
- **REQ-DATA-01**: Ingest QC results via API, CSV upload, database connector, and message feed (e.g., middleware) at minimum.
- **REQ-DATA-02**: Each QC record supports result value, timestamp, analyte, QC level, instrument ID, method ID, operator ID (optional), reagent lot (optional), control-material lot, calibration status (optional), run/batch ID (optional), units, and flags (e.g., repeated test).
- **REQ-DATA-03**: Ingest non-result events: calibration, maintenance, reagent lot change, control-material lot change, software updates, environmental alerts—each with timestamps and metadata.

### 4.2 Data Quality Rules
- **REQ-DATA-10**: Validate required fields per QC stream and reject or quarantine incomplete records.
- **REQ-DATA-11**: Validate units and apply controlled unit conversions where configured (with audit trail).
- **REQ-DATA-12**: Detect impossible/illogical values (configurable bounds) and route to an exception queue.
- **REQ-DATA-13**: Detect duplicates (same stream + timestamp/run ID + value) with configurable handling.
- **REQ-DATA-14**: Store original raw ingested payloads for traceability and link to normalized records.

## 5. Master Data and Configuration (REQ-CONFIG)
- **REQ-CONFIG-01**: Maintain master data for instruments, analytes, methods, QC materials/levels, target values, allowable total error (TEa)/clinical relevance thresholds (optional), sites, operators (optional), and lots.
- **REQ-CONFIG-02**: Support per-stream configuration for chart type(s), rule set(s), control limit approach, baseline period selection, and Bayesian model selection.
- **REQ-CONFIG-03**: Version-control configuration objects (chart definitions, rule sets, priors) and prevent silent edits; changes are time-stamped and attributable.
- **REQ-CONFIG-04**: Support effective-date activation of new configurations so changes do not retroactively alter historical interpretations unless explicitly reprocessed with an auditable reason.

## 6. Frequentist Control Charts and Rules (REQ-FREQ)
### 6.1 Chart Generation
- **REQ-FREQ-01**: Generate Levey–Jennings/Shewhart charts with centerline and control limits for each QC stream.
- **REQ-FREQ-02**: Support warning limits and action limits (e.g., ±2 SD, ±3 SD) as configurable.
- **REQ-FREQ-03**: Support CUSUM and EWMA charts as optional chart types per stream.
- **REQ-FREQ-04**: Support rolling-window and fixed-baseline options for mean/SD estimation, configurable per stream.
- **REQ-FREQ-05**: Allow QC points to be marked as excluded from statistical calculations while remaining visible on charts with clear visual distinction and audit trail.

### 6.2 Limit Calculation and Baseline Management
- **REQ-FREQ-10**: Support baseline selection by date range, by run count, and by “stable period” criteria.
- **REQ-FREQ-11**: Compute mean and SD using at least classical (mean/SD) and robust (median/MAD or trimmed) methods, configurable.
- **REQ-FREQ-12**: Support rules for when to re-baseline (e.g., after CAPA closure, after lot change, after calibration change), configurable.
- **REQ-FREQ-13**: Preserve historical baselines and show which baseline applied to each plotted point.

### 6.3 Rule Evaluation (Signals)
- **REQ-FREQ-20**: Evaluate rule sets per incoming QC point and generate signals (violations) with rule ID and evidence.
- **REQ-FREQ-21**: Support common multirule schemes (e.g., 1-3s, 2-2s, R-4s, 4-1s, 10x) and allow custom rule definitions.
- **REQ-FREQ-22**: Support rule evaluation across multiple QC levels for the same analyte/instrument if configured.
- **REQ-FREQ-23**: Classify signals by severity (info/warn/action) based on rule type and local policy.

## 7. Bayesian Modeling Layer (REQ-BAYES)
### 7.1 Model Catalog (Minimum Viable Set)
- **REQ-BAYES-01**: Support Bayesian in-control mean/variance model for each QC stream (posterior for μ and σ).
- **REQ-BAYES-02**: Support Bayesian drift model (time-varying mean) for early detection of gradual shifts.
- **REQ-BAYES-03**: Support Bayesian lot-effect model (control-material lot and/or reagent lot) with partial pooling.
- **REQ-BAYES-04**: Support Bayesian multi-instrument hierarchical model (optional) to borrow strength across instruments for the same method/analyte.
- **REQ-BAYES-05**: Support an outlier/contamination component (e.g., mixture likelihood) or robust likelihood option for occasional gross errors.

### 7.2 Priors and Governance
- **REQ-BAYES-10**: Allow priors to be defined per stream and/or inherited from a template (per method/analyte).
- **REQ-BAYES-11**: Provide default priors suitable for startup/low-data conditions and allow explicit override with justification.
- **REQ-BAYES-12**: Version priors and record author, rationale, effective date, and approval status.

### 7.3 Inference and Outputs
- **REQ-BAYES-20**: Update posterior summaries upon new QC data ingestion (at least daily; optionally near-real-time).
- **REQ-BAYES-21**: Output for each point/time: posterior mean, credible interval for μ, posterior for σ, and posterior predictive distribution.
- **REQ-BAYES-22**: Compute exceedance probabilities at minimum:
  - P(|μ − target| > bias_threshold)
  - P(next_result outside frequentist action limits)
  - P(drift_rate > configured_delta) when drift model enabled
- **REQ-BAYES-23**: Surface a normalized Bayesian Risk Score (0–100) per stream and timestamp derived from configured probabilities.

### 7.4 Model Diagnostics
- **REQ-BAYES-30**: Provide basic model-fit diagnostics (posterior predictive checks summary, residual flags) suitable for QA review.
- **REQ-BAYES-31**: Detect model failure conditions (non-convergence/degenerate updates) and fall back to frequentist-only scoring with explicit warning and audit log.

## 8. Hybrid Decision Engine (REQ-HYB)
- **REQ-HYB-01**: Support hybrid policies combining frequentist signals and Bayesian risk metrics into dispositions.
- **REQ-HYB-02**: Provide policy templates, including:
  - Frequentist action rule OR Bayesian high-risk triggers escalation.
  - Frequentist marginal violation AND Bayesian low-risk ⇒ confirmatory QC required before CAPA.
  - No frequentist violation BUT Bayesian drift probability > threshold for N consecutive points ⇒ emerging drift investigation.
- **REQ-HYB-03**: Allow per-stream thresholds for Bayesian triggers (e.g., 0.8/0.9/0.95) and persistence requirements (N points).
- **REQ-HYB-04**: Support confirmatory testing workflows (repeat QC, second QC level, recalibration check) as defined actions triggered by hybrid policies.
- **REQ-HYB-05**: Generate a single, auditable disposition for each QC point/run (e.g., Accept, Accept-with-monitoring, Hold-for-review, Reject/Out-of-control).

## 9. Alerting, Routing, and Escalation (REQ-ALERT)
- **REQ-ALERT-01**: Create alert objects from frequentist signals, Bayesian risk triggers, or hybrid dispositions.
- **REQ-ALERT-02**: Support routing rules by site, instrument group, analyte criticality, and on-call schedule (configurable).
- **REQ-ALERT-03**: Support notifications via email and/or messaging integration (configurable), with throttling to prevent alert storms.
- **REQ-ALERT-04**: Support acknowledgment, assignment, due dates, and escalation if SLA is breached.

## 10. Investigation Workflow (REQ-INV)
- **REQ-INV-01**: Allow conversion of an alert into an Investigation record.
- **REQ-INV-02**: Capture problem statement, affected streams/runs, suspected causes, immediate containment, data reviewed, attachments, and decision outcome.
- **REQ-INV-03**: Link investigations to relevant events (calibration/maintenance/lot change) and display them on the chart timeline.
- **REQ-INV-04**: Support investigation outcomes: No issue found, Operator error, Instrument issue, Reagent/lot issue, Method issue, Environmental, Other (configurable taxonomy).

## 11. CAPA Module (REQ-CAPA)
### 11.1 CAPA Lifecycle
- **REQ-CAPA-01**: Support CAPA states: Draft, Open, Implementing, Effectiveness Check, Closed, Reopened.
- **REQ-CAPA-02**: Require mandatory fields before CAPA approval: root cause category, corrective actions, preventive actions, owners, due dates, and verification plan.
- **REQ-CAPA-03**: Support multiple actions per CAPA, each with owner, due date, evidence, and completion status.

### 11.2 Linking CAPA to QC Evidence
- **REQ-CAPA-10**: Link each CAPA to alerts, investigations, QC points, runs/batches, instruments, analytes, lots, and events.
- **REQ-CAPA-11**: Render CAPA events as annotations on control charts (start/open, action implemented, effectiveness passed/failed, closed).
- **REQ-CAPA-12**: Lock referenced QC evidence from deletion; corrections handled via amend/correct workflow with audit trail.

### 11.3 Effectiveness Checks (Bayesian-Compatible)
- **REQ-CAPA-20**: Support effectiveness criteria defined as frequentist, Bayesian, and hybrid combinations (e.g., no rule violations for X runs; P(|μ−target|>B) < p_threshold for X points; drift probability below threshold).
- **REQ-CAPA-21**: Automatically evaluate effectiveness criteria and propose Pass/Fail with supporting evidence.

## 12. Control Chart UI/UX (REQ-UI)
- **REQ-UI-01**: Provide an interactive chart view per QC stream with zoom, pan, and time-range filtering.
- **REQ-UI-02**: Display frequentist centerline/limits and identify which baseline version applies over time.
- **REQ-UI-03**: When Bayesian is enabled, overlay at least posterior mean of μ, credible interval band for μ (configurable level), and optional posterior predictive band for next observation.
- **REQ-UI-04**: Show a risk indicator (score and/or probability) aligned to each time point/run.
- **REQ-UI-05**: Show timeline annotations for calibration, maintenance, lot changes, investigations, and CAPA milestones.
- **REQ-UI-06**: Provide drill-down from a signal to the exact rule fired, Bayesian probabilities, and data context.
- **REQ-UI-07**: Support comparing streams (e.g., same analyte across instruments) with aligned timelines.

## 13. Reporting and Analytics (REQ-REP)
- **REQ-REP-01**: Provide dashboards for current in-control status, open alerts, open investigations, open CAPAs, and overdue items.
- **REQ-REP-02**: Produce periodic QC performance reports (false alarm rate, mean time to detect, mean time to resolution, frequency of shifts, drift indicators).
- **REQ-REP-03**: Report CAPA KPIs: cycle time by root cause category, recurrence rates, effectiveness failures, and top recurring instruments/analytes.
- **REQ-REP-04**: Export reports to PDF and CSV with traceability to underlying data and configuration versions.

## 14. Audit Trail, Compliance, and Retention (REQ-AUD)
- **REQ-AUD-01**: Maintain an immutable audit log for data ingestion, edits/corrections, configuration changes, rule/model changes, dispositions, investigation/CAPA state transitions, and approvals.
- **REQ-AUD-02**: Audit entries include who, what, when, before/after values, reason code/comment, and associated object IDs.
- **REQ-AUD-03**: Support records retention policies (by site/regime) and legal hold.
- **REQ-AUD-04**: Support auditor-friendly reconstruction: reproduce chart and disposition exactly as of a historical date given then-effective configuration/model versions.

## 15. Integrations and APIs (REQ-API)
- **REQ-API-01**: Expose APIs to ingest QC data, ingest event data, retrieve charts/signals, retrieve CAPA status, and export audit logs (permissioned).
- **REQ-API-02**: Support idempotent ingestion endpoints and provide ingestion receipts with validation errors.
- **REQ-API-03**: Support mapping from external identifiers (LIMS/LIS/instrument middleware) to internal master data with a reconciliation UI.

## 16. Security, Privacy, and Reliability (REQ-NFR)
- **REQ-NFR-01**: Encrypt data in transit (TLS) and at rest.
- **REQ-NFR-02**: Support SSO (SAML/OIDC) and MFA (where available).
- **REQ-NFR-03**: Support environment separation (dev/test/prod) and validated deployment controls.
- **REQ-NFR-04**: Meet defined uptime and RPO/RTO targets (configurable by customer).
- **REQ-NFR-05**: Provide observability: logs, metrics, tracing for ingestion latency, rule evaluation, Bayesian update health, and alert delivery.

## 17. Model Lifecycle and Validation Pack (REQ-VAL)
- **REQ-VAL-01**: Provide a validation workspace using historical data to backtest frequentist rule performance, Bayesian trigger performance, and hybrid policy performance.
- **REQ-VAL-02**: Compute backtest metrics: sensitivity, specificity, detection delay, and alert burden under configurable scenarios.
- **REQ-VAL-03**: Require approval to promote a model/policy version to production and preserve the validation evidence package.

## 18. Acceptance Criteria Examples (REQ-ACC)
- **REQ-ACC-01**: With a QC stream configured with ±3 SD limits, when a point exceeds +3 SD, generate a frequentist action signal within a defined time from ingestion.
- **REQ-ACC-02**: With a drift model threshold P(drift)>0.9 for 2 consecutive points, when posterior drift probability exceeds 0.9 for two sequential ingestions, generate an “emerging drift” alert.
- **REQ-ACC-03**: When an alert is converted to CAPA, automatically annotate the chart at CAPA Open and update annotations at each CAPA milestone.
- **REQ-ACC-04**: When an auditor selects a historical date, reproduce chart limits, rules, Bayesian outputs, and disposition consistent with the then-effective versions.

## 19. Manual / Hand Entry of QC Data (REQ-MANUAL)
### 19.1 Core Capability
- **REQ-MANUAL-01**: Allow authorized users to manually enter QC results through a structured data-entry form.
- **REQ-MANUAL-02**: Support manual entry of result value, QC lot, control level, analyte, instrument ID, method ID, units, timestamp (user-entered or system-proposed), operator, run/batch ID (optional), and comments/notes.
- **REQ-MANUAL-03**: Treat manual entries identically to automated entries for chart plotting, frequentist rule evaluation, Bayesian updating, alert generation, and CAPA linkage.

### 19.2 Data Validation and Enforcement
- **REQ-MANUAL-10**: Perform full validation on manual entries (required fields, numeric ranges, units, valid QC level/analyte/instrument, lot/instrument status with configurable warnings).
- **REQ-MANUAL-11**: Provide inline warnings for values outside realistic limits, mismatched QC lots, or timestamps in the future/past beyond policy.
- **REQ-MANUAL-12**: Require confirmation before submitting out-of-range values.

### 19.3 Audit Trail Requirements
- **REQ-MANUAL-20**: Record who entered manual data, exact timestamp, original raw value, and any edits with before/after details, editor identity, and reason code.
- **REQ-MANUAL-21**: Editing or deleting manual QC data requires a reason for change, optional supervisor approval (configurable), and full audit trace.
- **REQ-MANUAL-22**: Never silently overwrite manual entries; changes create new revisions.

### 19.4 Workflow and Safety
- **REQ-MANUAL-30**: Manual entries immediately feed into frequentist evaluation, Bayesian updating, hybrid decisioning, alerting, and routing.
- **REQ-MANUAL-31**: Optionally allow “pending review” status and supervisor approval before inclusion into statistical baselines.
- **REQ-MANUAL-32**: Prevent manual entries from corrupting Bayesian priors; incorporate only through the posterior update stream.

### 19.5 UI/UX for Manual Entry
- **REQ-MANUAL-40**: Provide a keyboard-friendly, pre-populated interface optimized for rapid entry with auto-fill from recent context.
- **REQ-MANUAL-41**: Support batch hand-entry (multiple QC results for a run) with row-wise validation.
- **REQ-MANUAL-42**: Display target value, control limits, optional historical snippet, and optional Bayesian risk preview during entry to deter erroneous inputs.

### 19.6 Handling Unusual or Offline Situations
- **REQ-MANUAL-50**: Support manual QC entry when instruments are offline, interfaces are down, or retrospective documentation is required.
- **REQ-MANUAL-51**: Allow marking entries as Offline QC, Transcribed QC from paper, Corrected value, or Reconstructed run for audit clarity.

## 20. Assumptions and Open Questions
- Performance targets for ingest-to-signal latency and chart rendering need definition by deployment environment.
- Specific Bayesian model families and implementation technologies (e.g., Stan, PyMC, NumPyro) are to be selected during design with validation considerations.
- Confirmatory workflow templates for hybrid decisioning may require site-specific calibration.
- Regulatory mappings (e.g., CLIA, CAP, ISO 15189) should be aligned with retention and audit requirements in future elaboration.

## 21. Traceability and Next Steps
- Requirements are grouped by domain areas to support traceability to design, implementation, and validation artifacts.
- Future iterations should add: state diagrams for alert → investigation → CAPA, data schemas for ingestion and storage, and a catalog of hybrid policy templates with threshold/persistence defaults per analyte risk tier.
