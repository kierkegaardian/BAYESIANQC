# BayesianQC — Charting + Bayesian Outputs Review (Actionability Gaps)

Date: 2026-02-04

This review focuses on whether the current **charts** and **Bayesian outputs** provide **valid, actionable signals** for lab personnel (i.e., “what happened, why it’s flagged, what to do next”, without misleading visuals or stale/misaligned calculations).

## Executive Summary

The prototype has solid building blocks (stream config, prior versioning, Westgard-style rules, posterior state persistence, record exclusion + posterior rebuild), but **the information required for actionable interpretation is not surfaced** and some Bayesian computations can become **invalid** under realistic lab workflows (config/prior changes, out-of-order ingestion, point exclusion effects on historical signals).

If you do only 3 things next:
1) **Fix Bayesian posterior correctness across time** (prior/version boundaries + out-of-order ingestion).
2) **Return/compute per-record signals + Bayesian risk for charting** (not just on alerts).
3) **Make the UI show “why”** (rule evidence + posterior/predictive context) and ensure time alignment.

---

## P0 (Must-fix for “valid signals”)

### 1) Bayesian posterior state becomes invalid with out-of-order ingestion
- **Where:** `app/bayesian.py` (`infer_risk`)
- **What:** Posterior is updated in the order ingestions arrive, not strictly by `record.timestamp`.
- **Why it matters:** Manual/offline/backfilled QC records are common. One backdated record can corrupt the posterior for all future ingestions, making risk scores misleading.
- **Expected fix:** If `PosteriorState.updated_at > record_timestamp`, trigger a **rebuild** (or insert/redo) rather than incremental update.

### 2) Prior versioning exists, but Bayesian updates ignore effective-date changes
- **Where:** `app/bayesian.py` (`infer_risk`, `rebuild_posterior_state`)
- **What:** `PosteriorState` is per `stream_id` only. When priors change (`PriorConfig.effective_from`), state is not reset/rebuilt and `rebuild_posterior_state` only uses the *first record’s* prior for the entire series.
- **Why it matters:** After a prior change, Bayesian outputs can be mathematically incorrect and hard to detect by end users.
- **Expected fix:** Track prior provenance (e.g., `prior_version`/`effective_from`) in `PosteriorState` and rebuild/reset when the active prior changes; in rebuild, switch priors at effective boundaries.

### 3) Excluding a QC point rebuilds the current posterior, but historical signals/risk remain stale
- **Where:** `app/main.py` (`PATCH /qc/records/{id}/resolution`), `frontend/src/pages/ChartView.vue`
- **What:** Exclusion calls `rebuild_posterior_state`, but **alerts and previously-computed signals/risk are not recomputed** for downstream points.
- **Why it matters:** Westgard rules (2-2s/4-1s/10x) and Bayesian risk depend on history. After exclusion, the chart/alerts can present “facts” that no longer hold.
- **Expected fix:** Add a **stream reprocessing** path (sync job or on-demand recompute for the displayed time window) and/or store per-record evaluation derived from a canonical recompute.

### 4) Charting can misrepresent QC behavior due to smoothing
- **Where:** `frontend/src/pages/ChartView.vue` (`resultSeries.smooth = true`)
- **What:** The Levey-Jennings line is smoothed.
- **Why it matters:** QC charts typically use point-to-point segments; smoothing can visually invent trends/overshoot and reduce trust in the chart as evidence.
- **Expected fix:** Use `smooth: false` (or switch to scatter + optional straight line).

---

## P1 (Blocks “actionable signals” in daily use)

### 5) Chart endpoint lacks per-point “signal context” (risk, disposition, rule violations)
- **Where:** `app/api_models.py` (`QCRecordChartOut`), `app/main.py` (`GET /streams/{stream_id}/chart`)
- **What:** The chart returns record values only; **no disposition**, **no frequentist signals**, **no Bayesian risk per point**.
- **Why it matters:** Lab users need point-level interpretation on the chart (what fired, severity, confidence).
- **Expected fix:** Extend chart output to include derived fields per record (or a companion “evaluations” series).

### 6) Alerts are not linkable back to the exact QC point in the UI
- **Where:** `app/models.py` (`AlertOut`), `frontend/src/pages/ChartView.vue`, `frontend/src/pages/Alerts.vue`
- **What:** `AlertRecord` stores `qc_record_id`, but `AlertOut` does not expose it, and ChartView uses `alert.created_at` as the X value.
- **Why it matters:** Users can’t click an alert and see it on the chart, or confidently align risk to the point that caused it.
- **Expected fix:** Expose `qc_record_id` (and/or the QC record timestamp/value) on `AlertOut`, then use the record timestamp for chart alignment.

### 7) Results chart does not display alerts/events despite UI copy and API support
- **Where:** `frontend/src/pages/ChartView.vue`
- **What:** Template claims “results, alerts, and events”, and the API returns `events` + `alerts`, but the results chart doesn’t render them as annotations/markers.
- **Why it matters:** Events (calibration, maintenance, lot changes) are critical for interpreting shifts and deciding corrective action.
- **Expected fix:** Add event/alert markers on the timeline with tooltips and drill-down actions.

### 8) Alerts table hides the key “why” fields (signals + Bayesian detail)
- **Where:** `frontend/src/pages/Alerts.vue`
- **What:** Only shows IDs/status/disposition; does not display rule IDs/evidence or Bayesian risk/probability.
- **Why it matters:** Lab personnel need to triage quickly without opening logs or raw API payloads.
- **Expected fix:** Add columns and/or a details drawer: `severity`, `created_at`, `risk_score`, `probability_outside_limits`, `signals[]` with evidence, and quick “open chart” affordance.

---

## P2 (Quality/robustness gaps that degrade trust)

### 9) Frequentist and Bayesian calculations can disagree with what the chart shows
- **Where:** `app/storage.py` (`baseline_stats`), `app/frequentist.py`, `app/bayesian.py`, `frontend/src/pages/ChartView.vue`
- **What:** Frequentist rules may use `baseline_stats(...)` (derived mean/SD), while the chart always draws using `StreamConfig.target_value` and `StreamConfig.sigma`. Bayesian uses config target/sigma too.
- **Why it matters:** Users will see points “inside limits” while rules/alerts say otherwise (or vice versa).
- **Expected fix:** Make the chart use the same baseline/limits used for decisioning, or display both (and clearly label them).

### 10) Missing domain validation for parameters needed for safe Bayesian outputs
- **Where:** `app/models.py` (`StreamConfigIn`, `PriorConfigIn`)
- **What:** No validators enforcing required constraints like:
  - `sigma > 0`, `warning_limit_sd > 0`, `action_limit_sd > 0`, `action_limit_sd >= warning_limit_sd`
  - `0 <= risk_threshold_warn <= risk_threshold_hold <= 100`
  - For priors: `kappa0 > 0`, `alpha0 > 1`, `beta0 > 0`
- **Why it matters:** Invalid configs can silently yield nonsense risk (0 or 100) or runtime errors/div-by-zero.

### 11) “Bayesian not configured” looks like “risk is zero”
- **Where:** `app/bayesian.py` (`infer_risk`)
- **What:** If there’s no active prior, it returns `risk_score=0` and `probability_outside_limits=0.0`.
- **Why it matters:** 0 reads as “safe”, not “unknown/unavailable”.
- **Expected fix:** Add an explicit `available`/`status` field (or `risk_score: null`) and show it in UI.

### 12) Rule severities may not match typical Westgard policy
- **Where:** `app/frequentist.py`, `app/main.py` (`determine_disposition`)
- **What:** `2-2s`, `4-1s`, `10x` are classified as `WARN` (monitor), not `ACTION` (reject), so disposition may be too permissive.
- **Why it matters:** Users may take the wrong operational action when a standard “reject” rule fires.
- **Expected fix:** Make severities policy-configurable (per stream rule_set), and align default severity mapping to your lab SOP.

---

## Concrete Recommendations (next implementation slices)

### Backend (data + correctness)
1) Add a small “evaluation” model for charting: per record return (or persist) `signals`, `risk_score`, `probability_outside_limits`, `disposition`, and `n_obs` / posterior summary fields.
2) Make Bayesian state robust:
   - Detect out-of-order ingestion and rebuild.
   - Track active prior identity in state and rebuild/reset on prior changes.
3) Expose alert→record linkage: include `qc_record_id` (and record timestamp) in `AlertOut`.

### UI (actionability)
1) Chart overlays: marker shapes/colors for `disposition` and tooltips that show rule evidence + Bayesian stats.
2) Alerts triage: show risk + signals + timestamps; add “Open chart at point” navigation.
3) Make uncertainty visible: show posterior mean and credible interval band (even if initially a toggle).

---

## Quick Wins (low effort, high value)
- Remove smoothing from Levey-Jennings plot (`smooth: false`).
- Add alert detail columns to `Alerts.vue` (risk_score + signals preview).
- Use QC record timestamp (not `alert.created_at`) when plotting risk once linkage is exposed.

