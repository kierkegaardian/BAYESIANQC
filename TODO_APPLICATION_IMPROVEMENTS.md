# BAYESIANQC Application Improvement TODO

Created: 2026-07-13
Source: detailed math, backend, UI, demo, and deployability review supplied by the user.

## Purpose and Boundaries

This is the execution backlog for improving application correctness, data integrity, user experience, demo readiness, and eventual lab-pilot readiness.

Related documents have different scopes:

- `docs/STANDARDS_FEATURE_ROADMAP.md` covers longer-term standards-aware product features.
- `TODO_REPO_CLEANUP.md` covers repository hygiene and packaging of existing work.
- `docs/LAB_READINESS.md` defines the boundary between a supervised prototype and a validated lab deployment.
- This file tracks concrete remediation and verification work from the application review.

The review is a point-in-time snapshot. Before implementing an item, check active branches and worktrees for an existing fix. Do not mark an item complete until its acceptance evidence has been rerun on the intended release SHA.

## Status and Priority Rules

- `[ ]` means open or not verified on the intended release branch.
- `[x]` means implemented and verified with evidence recorded below the item.
- P0 blocks any use. P1 blocks an unattended/public demo. P2 should be fixed before a lab pilot unless explicitly accepted with rationale.
- Every completed item must name the tests, review artifact, or smoke evidence that proves it.
- Demo claims must remain limited to synthetic stakeholder demonstration data.
- No shared-lab or production claim is allowed until the lab-pilot gate at the end of this document passes.

## Recommended Execution Order

| Wave | Outcome | Entry gate | Exit gate |
| --- | --- | --- | --- |
| 0 | Re-baselined backlog | Intended branch selected | Review findings mapped to current code |
| 1 | Correct math and evaluation contracts | Baseline tests recorded | All math P1s and numerical tests pass |
| 2 | Atomic, scope-safe data workflows | Wave 1 complete | Duplicate, transaction, alert, and scope tests pass |
| 3 | Safe stakeholder UI | Stable backend contracts | Frontend unit, build, and browser acceptance pass |
| 4 | Truthful synthetic demo | Waves 1-3 complete | Deterministic fixture and guided walkthrough pass |
| 5 | Disposable public demo | Security/dependency gates clear | External smoke, stability, reset, and teardown proven |
| 6 | Lab-pilot hardening | Demo feedback triaged | Formal validation and operational controls accepted |

## Wave 0 — Re-baseline Current State

- [ ] **BASE-01 — Select the implementation baseline (P1).** Record branch, commit SHA, worktree path, dirty-state handling, and which related branches were checked for existing fixes.
- [ ] **BASE-02 — Reproduce or retire every review finding (P1).** For each ID below, record `reproduced`, `already fixed`, `superseded`, or `not reproducible`, with a test or command.
- [ ] **BASE-03 — Capture quality-gate baseline (P1).** Run Postgres pytest, Ruff, Pyright, frontend typecheck/build, migration rehearsal, OpenAPI/schema drift check, and `git diff --check`.
- [ ] **BASE-04 — Protect modularity (P2).** Split heavily modified modules when useful; do not add more endpoints directly to oversized `app/main.py`, and split `ChartView.vue` before major chart work.
- [ ] **BASE-05 — Create a remediation evidence index (P2).** Keep one table mapping these IDs to commit, tests, screenshots, reviewer result, and any explicit deferral.

## Wave 1 — Mathematics and Evaluation Correctness

### Distribution and Bayesian contracts

- [ ] **MATH-01 — Use Student-t for every supported finite degree of freedom (P1).** Remove the `df >= 30` Normal approximation from probability and quantile calculations.
  - Acceptance: CDF absolute error is at most `1e-10` and PPF error at most `1e-8` at df 4, 10, 30, and 100.
  - Acceptance: at df 30 and three scales, the two-sided tail is approximately `0.0053899641`.
  - Acceptance: tests cover both sides, extreme-but-supported probabilities, and continuity around the former cutoff.

- [ ] **MATH-02 — Validate all statistical values as finite (P1).** Reject NaN and Infinity for targets, sigma, limits, bounds, prior parameters, results, and conversion factors/offsets.
  - Acceptance: enforce `sigma > 0`, `kappa0 > 0`, `alpha0 > 1`, `beta0 > 0`, ordered limits, and `min_value <= max_value`.
  - Acceptance: calculate omitted `beta0` as `(alpha0 - 1) * sigma^2`.
  - Acceptance: malformed configuration returns HTTP 422 before ingestion can use it.

- [ ] **MATH-03 — Represent missing priors as unavailable, never zero risk (P1).** Add an explicit Bayesian availability contract.
  - Acceptance: missing effective prior returns `status="unavailable"`, reason `missing_effective_prior`, and null probability, score, posterior, and interval fields.
  - Acceptance: overall disposition becomes `hold_for_review` unless a frequentist action rule already requires rejection.
  - Acceptance: the UI says “Bayesian inference unavailable”; it never displays zero or stale risk.
  - Acceptance: legacy stored risk JSON without a status remains readable as available.

- [ ] **MATH-04 — Preserve and identify the validated NIG engine (P1).** Extract typed pure math helpers under `app/math/` while retaining compatibility imports where needed.
  - Acceptance: sequential Normal-Inverse-Gamma updates match a closed-form batch posterior within `1e-12`.
  - Acceptance: newly calculated snapshots include a stable engine identifier such as `nig-student-t-v1`.
  - Acceptance: predictive intervals are never narrower than credible intervals for the covered cases.

- [ ] **MATH-05 — Quarantine unexpected model failures (P1).** Numerical model failures must follow the existing HTTP 202 quarantine path and must not mutate posterior statistics.
  - Acceptance: failure injection proves no QC record, posterior observation, signal, or alert is partially persisted.

### Frequentist rules and effective dating

- [ ] **RULE-01 — Separate named Westgard constants from configurable chart limits (P1).** Implement 1-3s at 3 SD, 2-2s at 2 SD, 4-1s at 1 SD, and 10x using side-of-mean history.
- [ ] **RULE-02 — Make R-4s scientifically valid or disable it (P1).** Never calculate it across different runs, controls, or configuration boundaries.
  - Acceptance: history resets at configuration boundaries.
  - Acceptance: if within-run, across-control grouping is not modeled, reject new R-4s configuration and disable the rule.
  - Acceptance: cross-run and cross-configuration regression tests cannot produce R-4s.
- [ ] **RULE-03 — Correct the synthetic variability story (P1).** Rename the alternating fixture to “alternating high/low variability” and remove every R-4s claim until valid grouping exists.
- [ ] **RULE-04 — Stop future-effective fallback (P1).** Ingestion before the first effective configuration or prior must quarantine rather than borrow a future version.
  - Acceptance: default stream queries return only versions active at the requested/current time; scheduled versions require an explicit option.
- [ ] **RULE-05 — Assert risk/disposition invariants (P2).** Test `P(outside warning) >= P(outside action)` and keep Bayesian predictive risk separate from overall frequentist disposition.

## Wave 2 — Data Integrity, Authorization, and Transactions

### Duplicate and reprocessing policy

- [ ] **DATA-01 — Detect duplicates before record insertion (P1).** Exact duplicates return the existing snapshot and do not update the posterior, signals, or alerts.
  - Acceptance: response is HTTP 200 with `status="duplicate"` and an auditable `duplicate_qc_attempt` event.
  - Acceptance: possible duplicates return HTTP 409 for direct ingestion; CSV/import records a row-level conflict and continues.
  - Acceptance: concurrent duplicate submissions produce one record and one posterior observation.
- [ ] **DATA-02 — Define retry-safe manual idempotency (P1).** Generate a UUID for a manual submission and reuse it only for that operation's retry.
- [ ] **DATA-03 — Reconcile alerts after every evaluation-changing operation (P1).** Use one service for reprocessing, exclusion, reinclusion, backdated records, and configuration/prior changes.
  - Acceptance: non-accepting records create or update their active alert snapshot.
  - Acceptance: accepted or excluded records close their active alert with reason `evaluation superseded by reprocess`.
  - Acceptance: a `reconcile_alert` audit event records before/after state in the same transaction.
  - Acceptance: no accepted record retains an unexplained open reject alert.

### Transaction ownership

- [ ] **TX-01 — Remove commits from storage helpers (P1).** Quarantine, backlog, events, alerts, investigations, CAPAs, links, receipts, and audit helpers must flush/return only.
- [ ] **TX-02 — Give each mutation one service-owned transaction (P1).** Each endpoint performs one final commit or complete rollback; stream advisory locks remain held through commit.
- [ ] **TX-03 — Add failure-injection coverage (P1).** Fail after every intermediate entity, relationship, receipt, and audit write.
  - Acceptance: no partial state survives and retry does not need to repair prior partial writes.

### Scope and relationship integrity

- [ ] **AUTH-01 — Enforce scope before linking investigations or CAPAs (P1).** A user may not link, reveal, count, update, or report an out-of-scope alert or workflow entity.
- [ ] **AUTH-02 — Add explicit stream scope to investigations and CAPAs (P1).** Use an additive migration, derive/backfill scope through links, and abort on conflicting multi-stream links.
  - Acceptance: scoped users never see null-scope rows; genuinely global unlinked rows remain unrestricted-admin only.
  - Acceptance: scoped creation requires a linked in-scope alert or investigation.
  - Acceptance: list, detail, update, and report-summary queries apply the same scope filter.
- [ ] **AUTH-03 — Add real relationship constraints (P1).** Add foreign keys and appropriate uniqueness constraints to investigation-alert and CAPA link tables.
- [ ] **AUTH-04 — Prove least privilege endpoint-by-endpoint (P1).** Test every allowed and forbidden route directly against FastAPI, including totals and report summaries.
- [ ] **DATA-04 — Type and govern unit conversions (P2).** Validate finite factors/offsets at configuration time and preserve original plus converted values and units.
- [ ] **DATA-05 — Persist historical evaluation context (P2).** Chart points must carry the effective config/prior/ruleset/conversion/engine identity needed to explain their stored disposition.

## Wave 3 — Stakeholder UI Safety and Clarity

### Forms, state, and failure handling

- [ ] **UI-01 — Start manual results blank (P1).** Use null, never the stream target; disable submission until the operator explicitly supplies a finite value, while treating zero as valid.
- [ ] **UI-02 — Add per-operation submission locks (P1).** Prevent double submits and preserve the idempotency token for retry.
- [ ] **UI-03 — Use drafts for alert edits (P1).** Cancel or failed PATCH restores the server value; optimistic UI must not claim an unsaved change.
- [ ] **UI-04 — Make failures persistent and retryable (P1).** Network failures show an error and Retry action; stale counts and tables are visibly stale rather than presented as current.
- [ ] **UI-05 — Fix login and deep links (P1).** Enter submits without navigation to `/login?`, and successful authentication returns to the requested permitted route.
- [ ] **UI-06 — Remove competing configuration creation paths from stakeholder mode (P1).** Keep the governed location/datastream workflow and hide or retire legacy free-text creation routes.

### Lists and dashboard

- [ ] **UI-07 — Paginate Alerts and Audit server-side (P1).** Default limit 50, maximum 200, offset support, scoped `X-Total-Count`, and stable `created_at DESC, id DESC` ordering.
- [ ] **UI-08 — Add useful filters and defaults (P1).** Alerts support status, disposition, stream, and date filters and default to open/acknowledged. Audit uses its existing filters server-side.
- [ ] **UI-09 — Label exports honestly (P2).** Until full-result export exists, use “Export current page.”
- [ ] **UI-10 — Refocus dashboard counts (P2).** Emphasize active work, provide closed/history context, and deep-link cards to filtered workflow pages.

### Charts, accessibility, mobile, and performance

- [ ] **CHART-01 — Split chart orchestration from pure option/data modules (P1).** Separate data transformation, option construction, interaction state, and accessible data-table behavior before further expansion.
- [ ] **CHART-02 — Separate statistical facts in copy (P1).** Show predictive action risk, overall disposition, and the reason as three distinct facts.
- [ ] **CHART-03 — Correct chart labels and axes (P1).** Rename “Peak” to “Highest in selected window,” format all numeric axes, and keep Mean/Warn/Hold labels inside the plot.
- [ ] **CHART-04 — Fix broken-axis time semantics (P1).** Panels share one time extent, show explicit break markers, and label the outlier panel; no unrelated years may appear.
- [ ] **CHART-05 — Add a compact complete legend (P2).** Cover result, mean/limits, posterior mean, credible interval, predictive interval, events, and alerts.
- [ ] **CHART-06 — Add non-canvas access (P1).** Provide accessible chart labels, textual summary, keyboard-reachable point details, and a “View chart data” table.
- [ ] **PERF-01 — Cache the stream catalog (P1).** A six-tile kiosk makes one stream-catalog request per refresh cycle, not six.
- [ ] **PERF-02 — Split the production bundle (P2).** Lazy-load routes and use modular ECharts imports; record gzip sizes and budgets in CI.
- [ ] **MOBILE-01 — Replace the full-page mobile sidebar (P1).** Use a drawer and viewport-responsive dialogs; verify at 390 x 844.
- [ ] **KIOSK-01 — Pause rotation during interaction (P2).** Focused charts and open point dialogs must not rotate away.

## Wave 4 — Deterministic Synthetic Demo

- [ ] **DEMO-01 — Rebuild fixtures from a fresh database (P1).** Fixture loading is deterministic and idempotent, and all evaluations are recomputed by the corrected engine.
- [ ] **DEMO-02 — Seed a coherent workload (P1).** Target a small mix such as 8 open alerts, 6 acknowledged alerts, remaining history closed, 2 open investigations, 1 CAPA in implementation, mixed backlog, and reviewed/open quarantine examples.
- [ ] **DEMO-03 — Remove misleading claims (P1).** No fixture, label, tooltip, or walkthrough calls alternating cross-run values R-4s.
- [ ] **DEMO-04 — Add the synthetic-use banner (P1).** Dashboard and kiosk surfaces say “Synthetic stakeholder demonstration — not validated for laboratory use.”
- [ ] **DEMO-05 — Script and test one guided story (P1).** Cover kiosk overview, low Bayesian risk plus frequentist rejection as separate facts, Bayesian warning before action breach, alternating variability, quarantine, comments, point resolution, alert update, investigation, and CAPA.
- [ ] **DEMO-06 — Restrict stakeholder navigation and APIs (P1).** Hide and route-guard configuration, imports, raw ingestion, API docs, audit, and administration; backend authorization remains primary.

## Wave 5 — Free, Disposable Public Demo

- [ ] **DEPLOY-01 — Use a private origin topology (P1).** Postgres and API have no host ports; only the internal reverse proxy is reachable by the accountless Quick Tunnel.
- [ ] **DEPLOY-02 — Add defense-in-depth edge policy (P1).** Protect the entire app with Basic Auth, strip inbound credentials, inject only the stakeholder key, return 404 for docs/OpenAPI, and deny unapproved API methods/routes.
- [ ] **DEPLOY-03 — Generate fresh secrets and synthetic state (P1).** Never commit credentials or use customer, PHI, or production lab data; share URL and password separately.
- [ ] **DEPLOY-04 — Pin and audit dependencies/images (P1).** No public release with a high/critical advisory; document reachability and explicit waiver for any accepted moderate advisory.
- [ ] **DEPLOY-05 — Add health, readiness, and resource checks (P1).** Readiness covers database connectivity, migration head, and writable archive; services run non-root with bounded logs and conservative limits.
- [ ] **DEPLOY-06 — Build a reproducible release (P1).** Record clean release SHA, archive checksum, image tags, and image digests; rehearse fresh migration plus populated upgrade.
- [ ] **DEPLOY-07 — Run private then public smoke (P1).** Prove Basic challenge, stakeholder identity, permitted mutations, forbidden ingestion/config/admin writes, docs 404, path-normalization resistance, and all stakeholder routes.
- [ ] **DEPLOY-08 — Prove reset and teardown (P1).** Reset by recreating the demo database/archive; stop the tunnel first, verify the old URL dies, stop only project-scoped containers, remove secrets, and confirm no unexpected listeners remain.
- [ ] **DEPLOY-09 — State the hosting limitation (P2).** Quick Tunnels are random, testing-only, and have no SLA; ChatGPT may carry the walkthrough but is not the Vue/FastAPI/Postgres runtime.

## Wave 6 — Post-Demo Lab-Pilot Gate

- [ ] **LAB-01 — Add immutable evaluation provenance.** Persist evaluation runs and alert supersession so historical decisions can be reconstructed exactly.
- [ ] **LAB-02 — Version governed duplicate and rule policy.** Store idempotency fingerprints, duplicate-policy versions, structured rule definitions, reset policy, and a valid run/control grouping key.
- [ ] **LAB-03 — Complete identity and segregation of duty.** Add named OIDC identities, MFA/enterprise lifecycle as required, electronic signatures, and policy-enforced independent approvals.
- [ ] **LAB-04 — Complete audit and retention controls.** Provide full scoped exports, retention/legal-hold policy, tamper-evident evidence handling, and restore-tested backups.
- [ ] **LAB-05 — Formally validate the statistical model.** Backtest representative datasets, document assumptions and failure modes, set monitoring criteria, and obtain SME expected-result signoff.
- [ ] **LAB-06 — Validate real interfaces safely.** Use sanitized instrument files, governed/reconstructable conversions, interface mapping tests, and no production data during pilot development.
- [ ] **LAB-07 — Benchmark representative volume.** Measure full-stream reprocessing, kiosk/read-model behavior, alert generation, and database growth under realistic load.
- [ ] **LAB-08 — Assemble the validation package.** Archive requirements traceability, risk analysis, test protocols/results, dependency inventory, migration/rollback proof, backup/restore evidence, and reviewer approvals.

## Required Automated Evidence

- [ ] Postgres pytest, Ruff, Pyright, frontend typecheck, and production build pass.
- [ ] Fresh migration and populated-database upgrade rehearsals pass.
- [ ] OpenAPI regeneration and TypeScript contract drift checks pass.
- [ ] Math accuracy, NIG equivalence, missing-prior, finite-input, duplicate-concurrency, R-4s boundary, transaction-failure, and scope-leak tests pass.
- [ ] Frontend tests cover blank manual entry, submission locks, alert draft rollback, risk/disposition wording, guards, pagination, and network failures.
- [ ] Browser acceptance passes at 1440 x 900, 1920 x 1080, and 390 x 844 with no clipped labels, bad axes, console errors, or failed requests.
- [ ] Keyboard users can reach chart data and point details.
- [ ] Dependency audits report no unresolved high/critical advisory.
- [ ] A fresh security/auth/deployment review has no unresolved P0/P1 finding or records an explicit, owner-approved waiver.

## Definition of Done for the Josh-Style Demo Milestone

- [ ] Every visible mathematical claim is correct and traceable to a test.
- [ ] Bayesian unavailability is explicit; no false zero risk is shown.
- [ ] R-4s is either grouped correctly or absent from the product and story.
- [ ] Least privilege is enforced by FastAPI and independently narrowed at the edge.
- [ ] Failed workflows leave no partial entity, link, receipt, alert, posterior, or audit state.
- [ ] Synthetic fixtures tell a small, coherent, repeatable story.
- [ ] The release is reproducible from a clean SHA and can be reset from scratch.
- [ ] Public access, forbidden-route behavior, deep links, off-LAN use, stability, and teardown are proven.
- [ ] The UI and handoff clearly state that the demo is synthetic and not validated for laboratory use.

## Completion Log

Add one row when an item is marked complete.

| Date | ID | Release SHA | Evidence | Notes or waiver |
| --- | --- | --- | --- | --- |
| | | | | |
