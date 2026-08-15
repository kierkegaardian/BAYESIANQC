# BAYESIANQC Standards-Aware Feature Roadmap

Date: 2026-06-28

Provenance:
- AGY Opus review: `reviews/agy/bayesianqc-opus-feature-review-20260628T211241-0500.md`
- AGY model requested: `Claude Opus 4.6 (Thinking)`
- Prior remediation review: `reviews/agy/bayesianqc-remediation-review-20260628T200526-0500.md`

This document is a product and implementation roadmap, not a compliance certificate or licensed standards excerpt. It uses standards at a high level: ASTM D6299-style statistical quality control, ISO/IEC 17025-style lab quality management, ISO 5725 / 13528 / 21748-style statistical validation and uncertainty thinking, and ISO 8000-style data-quality governance.

## Executive Assessment

BAYESIANQC is now a defensible lab prototype. The post-remediation baseline has no known P0/P1 blockers from AGY review. The core strengths are:

- API-key auth with PBKDF2 storage and constant-time row lookup by deterministic lookup hash.
- Role-aware read/mutate separation with backend-derived audit actor identity.
- Stream-level ingestion locking and reprocessing for out-of-order records, resolution changes, config changes, and prior changes.
- Normal-Inverse-Gamma Bayesian posterior update with persistent state.
- Frequentist QC rule evaluation and Bayesian risk output on each ingested record.
- Versioned stream configs and priors with effective-date behavior.
- Alert, investigation, CAPA, audit, chart, and role-aware UI surfaces.

The next product direction should not be more algorithmic novelty first. It should be: make the current QC workflow usable by a lab, make the data defensible, then add richer statistics.

## Remaining Product Risks

1. Transaction boundaries are not fully clean. Some helper modules still commit or expose commit flags. Services should own transaction boundaries.
2. `app/main.py` remains too large and mixes endpoint, service, query, and validation work.
3. Frequentist rule selection is not configurable enough for lab-specific SQC policy.
4. Baseline estimation is still mostly classical mean/SD; robust baseline options are needed.
5. Unit mismatches are rejected, not converted through controlled, audited conversion rules.
6. Invalid or suspicious records are rejected instead of quarantined for data-quality review.
7. Bayesian model diagnostics and fallback behavior are not yet visible to users.
8. Audit `before` snapshots are not consistently complete for all configuration and lifecycle changes.
9. Postgres is the default local/dev runtime with Alembic migrations, but stronger foreign keys and production-like rollback/restore proof are still required before shared lab deployment.
10. Lab administration features remain incomplete: QA Manager role, segregation of duty, electronic signatures, retention, legal hold, notification/distribution routing, local-plus-SSO auth, user/group administration, and LIMS/middleware mapping.

## Phase 0: MVP-Next

Goal: make the prototype practical for a supervised lab evaluation without changing the statistical core.

### F0.1 Manual QC Entry

Build a keyboard-friendly manual QC entry page for analysts. It should prefill recent stream, lot, method, instrument, and units; show target, sigma, warning/action limits, and current risk; validate fields inline; and support a batch-entry mode for multiple QC levels in one run.

Acceptance criteria:
- Manual entry uses the same backend ingestion service as API and CSV ingestion.
- Entry source is visible in audit output.
- Out-of-range values require a confirmation reason or go to quarantine once that exists.

### F0.2 Audit Log Viewer

Expose `GET /audit` in the UI. Auditors should be able to filter by entity, actor, role, action, date range, stream, and API key id. Rows should expand to before/after JSON with a readable diff.

Status: implemented in the frontend as `/audit` with client-side filtering, before/after expansion, changed-field summaries, and CSV/JSON export.

Acceptance criteria:
- Auditors can view audit but cannot mutate.
- Export supports CSV or JSON for audit packets.

### F0.3 Dashboard and Reports Page

Add a lab dashboard for current operating status: streams in control, streams at warning/action, open alerts, overdue alerts, open investigations, open CAPAs, and recent audit activity.

Acceptance criteria:
- Dashboard is read-only for all READ roles.
- Cards deep-link to filtered list views.

### F0.4 Stream and Prior Configuration UI

Build UI forms for stream config and prior config versioning. The UI should show version history, effective dates, active version, previous version, and the rationale for creating a new version.

Acceptance criteria:
- New config versions require a reason.
- Backdated effective dates warn that historical reprocessing will occur.
- Prior parameters include help text for lab users.

### F0.5 Risk Trendline

Plot Bayesian risk score over time on the Levey-Jennings chart as a secondary 0-100 axis. Show warning and hold thresholds as reference lines.

Acceptance criteria:
- Tooltip shows result value, z-distance, frequentist signals, risk score, and disposition.
- Risk line can be toggled off for visual clarity.

### F0.6 Alert Filtering and SLA Columns

Add filters for stream, severity, status, assignee, and date range. Add due/overdue indicators and list views for investigations and CAPAs using the same filter patterns.

Acceptance criteria:
- Alert updates require a backend-enforced reason.
- Auditors see filters and details but not save/submit controls.

### F0.7 CSV Preview and Row-Level Validation

Before uploading a CSV, show parsed rows, validation errors, duplicate warnings, and what stream each row resolves to.

Acceptance criteria:
- Bad rows do not prevent good rows from being submitted.
- Upload summary includes accepted, rejected, duplicate, and quarantined counts.

## Phase 1: Lab-Readiness Foundation

Goal: move from demo to a controlled lab pilot under realistic quality-system expectations.

### F1.1 Configurable SQC Rule Sets

Replace hardcoded frequentist rule selection with versioned rule-set configuration. Support enabling/disabling rules, rule severity, window sizes, and built-in schemes.

Feature scope:
- Current new-stream rules: individual-result 1-3s, 2-2s, 4-1s, and 10x. Legacy R-4s configurations retain a visibly labelled nonstandard sequential variant only.
- Add common trend/run variants such as 7T and 8x.
- Add a rule-set version to each stream config.
- Reprocess records when a rule set changes retroactively.

### F1.2 CUSUM and EWMA

Add CUSUM and EWMA as configurable SQC methods for small sustained shifts. These should produce chart data and feed the same disposition pipeline as existing frequentist signals.

Feature scope:
- CUSUM reference value, decision interval, reset policy.
- EWMA lambda, dynamic limits, warm-up behavior.
- Chart overlays for CUSUM/EWMA signals.

### F1.3 Robust Baseline Estimation

Add baseline method selection per stream.

Feature scope:
- Classical mean/SD.
- Median/MAD.
- Trimmed or winsorized mean/SD.
- Iterative robust estimator suitable for contaminated baseline windows.
- Baseline method changes are versioned and audited.

### F1.4 Controlled Unit Conversion

Implement unit conversion as data governance, not ad hoc math.

Feature scope:
- Conversion rules with factor, offset, source, effective dates, and status.
- Per-stream policy: reject mismatch, convert with warning, or convert silently.
- Audit original value/unit and converted value/unit.
- UI for managing conversion rules.

### F1.5 Quarantine Queue

Suspicious records should be preserved and reviewed, not simply discarded.

Feature scope:
- Store rejected payload, validation failures, source, actor, and timestamp.
- Review actions: approve ingestion, reject with reason, link to investigation.
- Quarantine reasons: out of bounds, future timestamp, stale timestamp, unknown mapping, suspicious duplicate, unit mismatch, inactive instrument.

### F1.6 Bayesian Model Health

Add model diagnostics so users know when Bayesian risk is trustworthy.

Feature scope:
- Posterior health status per stream: healthy, degraded, degenerate.
- Posterior predictive surprise score.
- Detect variance collapse, excessive prior dominance, insufficient observations, and stale posterior state.
- Fallback to frequentist-only disposition when model health is degenerate.
- Audit model-health transitions.

### F1.7 Complete Historical Reconstruction

Make every relevant audit event reconstructable.

Feature scope:
- Consistent `before` and `after` snapshots for config, prior, alert, investigation, CAPA, and record-resolution changes.
- A historical chart reconstruction endpoint: stream state as of a timestamp.
- Reportable evidence package for any chart date.

### F1.8 Postgres Migrations and Referential Integrity

Promote Postgres from dev option to lab deployment target.

Feature scope:
- Alembic or equivalent versioned migrations. Current head `20260703_0002` exists; future schema changes still need explicit reviewed revisions.
- Foreign keys for instrument, method, analyte, QC record, alert, investigation, CAPA, and receipt relationships.
- Restrictive delete behavior for lab records.
- CI job that runs tests against Postgres.

### F1.9 QA Manager and Segregation of Duty

Add a QA Manager role and backend policy checks that prevent self-approval for sensitive actions.

Feature scope:
- Role: QA Manager with model/policy approval authority.
- Analyst who entered a record cannot be sole approver of its exclusion.
- CAPA creator cannot approve their own effectiveness check.
- Investigation creator cannot be sole closer.
- Audit logs include policy decisions.

### F1.10 Notifications, Distribution Groups, and Webhooks

Add outbound notifications, recipient groups, report routing, customer-managed delivery configuration, and delivery audit.

Feature scope:
- Webhooks with HMAC signing and retries.
- Events: alert created/escalated, investigation created/closed, CAPA opened/closed, model degraded.
- Distribution groups for QC signals, escalation, and generated reports, with recipients drawn from users, user groups, roles, sites, benches, instruments, and assignment groups.
- Customer-managed delivery adapters for SMTP, webhooks, Apprise-compatible routes, ntfy/Gotify push, and SMS gateways; customers provide credentials, servers, carrier/API contracts, and IT operation so BAYESIANQC does not require vendor-funded messaging accounts.
- Delivery log with status, retry count, and last error.
- Throttling to prevent alert storms.

## Phase 2: Advanced Analytics

Goal: add the features that make BAYESIANQC more than a conventional control-charting tool.

### F2.1 Bayesian Drift Detection

Add a time-varying mean model such as a local-level dynamic linear model. Use it to estimate gradual drift probability and drift rate.

### F2.2 Lot-to-Lot Hierarchical Modeling

Model control-material lots with partial pooling so new lots borrow strength from historical lots while retaining lot-specific offsets.

### F2.3 Outlier or Contamination Model

Add a robust likelihood or mixture model to estimate the probability that a point is a gross error without immediately corrupting the posterior.

### F2.4 Backtesting and Model Validation Workspace

Replay historical data through candidate policies and models. Compare sensitivity, specificity, detection delay, false alert burden, and alert-to-resolution time.

### F2.5 Multi-Stream Comparison

Compare the same analyte across instruments or the same instrument across analytes with aligned timelines and normalized SD-unit axes.

### F2.6 Fan Charts and Uncertainty Bands

Visualize credible intervals for the posterior mean and predictive intervals for future observations. These bands should be visually distinct from control limits.

### F2.7 Proficiency Testing and Measurement Uncertainty

Ingest proficiency-testing events, z-scores, assigned values, uncertainty, and bias evidence. Link method uncertainty budgets to stream configuration and Bayesian priors.

Feature scope:
- Treat proficiency testing and interlaboratory crosscheck data as a separate evidence workflow from routine QC charting.
- Store round/program metadata, provider, sample identifiers, assigned or accepted reference value, uncertainty, peer-group context, and received/reported timestamps.
- Compute and preserve z-score or equivalent performance metrics when the lab SOP defines the formula and acceptance criteria.
- Link PT/ILCP failures to alerts, investigations, CAPA, affected-method review, and auditor export packets.
- Do not treat PT/ILCP samples as ordinary posterior-updating QC points unless a lab-owned policy explicitly says to do so.

### F2.8 CAPA Effectiveness Automation

Let CAPAs define statistical effectiveness criteria and have the system propose pass/fail when post-CAPA data meets or misses the criteria.

## Execution Planning TODO: Advanced SQC Waves

Use these roadmap handles when generating execution plans in future chats. Each wave should produce its own plan before implementation; avoid bundling all advanced statistics into one slice.

Before any implementation wave, create a fit-for-purpose research note for the target method. The note should compare qcc-style feature coverage, open statistical references, lab SOP needs, and BAYESIANQC workflow constraints. Use qcc as a feature taxonomy and behavior reference only; do not copy, port, or translate GPL-licensed code into this project.

### qcc-Informed Gap Research Backlog

TODO: Determine which qcc-supported SPC features are worth implementing in BAYESIANQC, and in what form, before treating them as product commitments.

Research needed:
- Full Shewhart family fit: decide which of `xbar`, `R`, `S`, one-at-time, `p`, `np`, `c`, `u`, and `g` charts map to likely lab workflows.
- One-at-time / I-MR fit: determine whether moving-range sigma estimation should become the default for individual analytical-result streams or remain an optional baseline method.
- Attribute and count workflows: define the data model for defect, nonconforming-unit, nonconformity, and non-event counts before implementing `p`, `np`, `c`, `u`, or `g` charts.
- Phase I / Phase II semantics: decide how baseline/training data, monitoring data, exclusions, and new data should be represented in a validated lab workflow.
- Rule-set alignment: compare current Westgard-style rules with Western Electric-style rule variants and decide which built-in schemes and severity defaults should be offered.
- EWMA / CUSUM fit: determine parameters, warm-up, reset, and disposition semantics that make sense for lab QC rather than generic manufacturing SPC.
- OC curves, ARL, and process capability: decide whether these are analyst planning tools, validation-pack outputs, or routine dashboard features.
- Multivariate SPC: identify real use cases before adding Hotelling T2-style charts, covariance modeling, or ellipse views.
- Pareto and cause-effect tools: decide whether these belong in investigation/CAPA analytics rather than the core QC chart module.
- Overdispersion checks: determine whether binomial/Poisson diagnostics are needed for attribute/count QC streams.
- Overlay and comparison strategy: decide when overlaying charts is valid, when normalized overlays are required, and when aligned small multiples are safer.
- Context stratification analytics: determine which operator, actor, group, shift, site, bench, instrument, method, lot, and entry-source comparisons support process improvement without becoming naive blame metrics.
- Extension model: decide whether BAYESIANQC should expose custom chart/rule plugins or keep methods as reviewed, versioned first-party modules.

### W1 SQC Configuration Foundation

TODO: Build the versioned configuration layer that later chart families can share.

Plan must cover:
- Versioned chart family, rule set, baseline method, control-limit source, severity policy, affected-interval policy, and SOP reference.
- Effective-date behavior, retroactive reprocessing rules, and audit rationale.
- Fixtures that prove historical reconstruction uses the then-effective config.

### W2 Routine Shewhart Expansion

TODO: Expand beyond the current individual Levey-Jennings/Shewhart chart without overfitting to demo data.

Plan must cover:
- I-MR first for individual analytical results, including moving range calculation and optional MR chart view.
- X-bar/R/S only after subgroup data has a real data model and import path.
- Attribute charts (`p`, `np`, `c`, `u`) only when a defect/count workflow exists.
- Process capability only after baseline selection, distribution assumptions, and spec limits are explicit.

### W3 EWMA and CUSUM

TODO: Implement EWMA and CUSUM as configurable small-shift detectors.

Plan must cover:
- EWMA lambda, warm-up behavior, dynamic limits, reset policy, and chart overlay.
- CUSUM target, reference value, decision interval, one-sided/two-sided handling, reset policy, and chart overlay.
- Signal generation, disposition integration, audit evidence, and validation fixtures.

### W4 D6299-Style Precision and Bias Support

TODO: Add standards-aware evidence support for precision, bias, and site-performance workflows without embedding licensed standards text.

Plan must cover:
- Lab-owned SOP binding for precision/bias checks, accepted reference values, site precision, and bias acceptance criteria.
- Robust baseline and outlier handling, uncertainty inputs, and reportable evidence packets.
- Clear separation between "supports following D6299-style workflows" and "certifies compliance."

### W5 PT / ILCP Module

TODO: Build a dedicated proficiency-testing and interlaboratory crosscheck workflow.

Plan must cover:
- PT/ILCP round metadata, assigned or accepted values, uncertainty, peer-group summaries, z-scores or local performance metrics, and report packets.
- Links to alerts, investigations, CAPA, method review, and affected-result evaluation.
- Guardrails that keep PT/ILCP evidence distinct from routine QC posterior updates unless policy-approved.

### W6 Validation and Export Layer

TODO: Make advanced SQC outputs defensible for audit and future standards mapping.

Plan must cover:
- Backtesting with known fixtures for each chart/rule family.
- Reproducible export packets for chart state, rule firings, Bayesian risk, PT/ILCP evidence, investigations, and CAPA links.
- A release-note gap statement that says which methods are supported, partially supported, or not supported.

### W7 Chart Comparison and Context Analytics

TODO: Add comparison tools that help labs find process causes without overclaiming from raw counts.

Plan must cover:
- Overlay rules for same-stream, same-units, normalized z-score, QC-level, cross-instrument, and cross-method views.
- Operator/user/group analytics for signal, reject, quarantine, exclusion, retest, comment, investigation, and CAPA rates.
- Denominator, minimum-sample, and stratification controls by site, bench, instrument, method, analyte, QC level, lot, shift, and entry source.
- UI language that frames findings as training/process-review signals, not individual blame.

### W8 Enterprise Scope and Access Control

TODO: Add enterprise access scoping so users and service accounts only see or enter data for authorized sites, benches, instruments, and streams.

Plan must cover:
- Grant model for user, user group, role, and API key scopes across site, lab bench, instrument, analyte/method, stream, and assignment group.
- Backend-enforced query filters for charts, streams, backlog, ingestion, imports, alerts, investigations, CAPA, comments, audit, and reports.
- Local password auth and SSO/OIDC/SAML side by side, with tested SSO-outage fallback for authorized local users.
- OIDC/SAML group-claim mapping plus local overrides, effective dates, disabled grants, audited break-glass admin/vendor-service accounts, and rotation/disable policy.
- User/group admin UI with guided add/edit, membership management, scope preview, effective-permission preview, validation, and safe defaults.
- Data-entry and chart filters that default to the user's authorized scope and make cross-site access explicit and auditable.

## Phase 3: Operational and Enterprise Readiness

Goal: make the system maintainable in a real lab environment.

Features:
- Local password auth plus SSO/OIDC/SAML with MFA, tested SSO-outage fallback, audited break-glass/vendor-service accounts, and API keys for service accounts.
- Electronic signatures with meaning-of-signature text and reauthentication.
- Retention policies and legal holds.
- Observability: structured logs, correlation IDs, metrics, health checks, alert-delivery status.
- LIMS/middleware external ID mapping with reconciliation UI.
- ISO 8000-style data quality scores for completeness, timeliness, conformance, consistency, and lineage.
- Scheduled PDF/CSV/JSON report generation with reproducible parameters and customer-managed delivery through routed distribution groups.
- Multi-site/site-scoped RBAC, bench/instrument-scoped data entry, group-scoped backlog visibility, and cross-site analytics with explicit authorization.
- API versioning and deprecation policy.
- Backup, restore, disaster-recovery, and deployment runbooks.

## Suggested Next Five Implementation Slices

1. Extract alert, investigation, CAPA, and resolution services from `app/main.py` and remove helper-level commits.
2. Build manual QC entry plus audit viewer. These are the highest usability wins for a lab evaluator.
3. Add rule-set configuration and robust baseline estimation. This is the most direct SQC standards gap.
4. Add quarantine queue and unit conversion governance. This is the core data-quality gap.
5. Keep Postgres migration tests and rehearsal green, then add stronger foreign keys before further lab-like deployment work.

## Definition of Lab-Pilot Ready

BAYESIANQC should not be described as lab-pilot ready until all of these are true:

- Postgres deployment path is tested, migrated, and documented.
- All mutation workflows have complete before/after audit snapshots.
- Role matrix includes QA Manager and segregation-of-duty checks.
- Manual QC entry, audit viewer, config UI, and dashboard are usable without API tooling.
- Rule sets and baseline methods are configurable and versioned.
- Quarantine and unit conversion are implemented with audit trail.
- Validation package can replay known fixtures and produce evidence for a defined model/policy version.
- Remaining non-v1 gaps are explicit in release notes.
