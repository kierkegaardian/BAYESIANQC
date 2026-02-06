I will begin by reviewing the Bayesian and charting logic in `app/bayesian.py` and `app/main.py` to assess the mathematical correctness and performance implications of the new risk calculation and visualization features.
This review of the **Bayesian QC Prototype** diff focuses on the integrity of the statistical engine, its performance at scale, and its integration with the UI/API.

### 1. P1 Findings & Concrete Risks

#### **[P1] Performance Bottleneck: O(N) Walk in `stream_chart`**
*   **Location:** `app/main.py` (lines 1354–1425)
*   **Risk:** To render the continuous risk line, the `stream_chart` endpoint fetches **every historical record** for a stream since the start of its current prior (`history_query`) and re-calculates the Bayesian update for every single point in that history. 
*   **Impact:** In a production lab with thousands of records per stream, this will lead to multi-second latencies and potential API timeouts. The UI will become unresponsive as the database grows.
*   **Fix:** Use the cached `PosteriorState` as a "checkpoint." Fetch the state first; if the state is valid and falls within the current prior's window, iterate only from `state.updated_at` to the chart end.

#### **[P1] Side-Effect in Inference (Transactional Integrity)**
*   **Location:** `app/bayesian.py` (lines 360, 396)
*   **Risk:** `infer_risk` and `rebuild_posterior_state` execute `session.commit()`.
*   **Impact:** This breaks the atomicity of the ingestion process. In `process_ingestion`, the session is committed halfway through. If a record is ingested successfully but a subsequent step (like generating the `AlertRecord` or writing the audit log) fails, the record and the updated `PosteriorState` will remain in the DB. The inference function should not commit the transaction; it should let the top-level caller manage the unit of work.

---

### 2. Math & Statistical Correctness

#### **[P2] Student’s t-Distribution Implementation**
*   **Status:** **Excellent Improvement.**
*   **Detail:** Moving from a Normal approximation to a Student’s t-distribution for predictive risk (`_student_t_cdf` via the regularized incomplete beta function) correctly accounts for "heavy tails" of uncertainty when sample counts are low. This prevents the system from being overconfident during the first ~30 observations of a new lot/prior.
*   **Threshold:** The `_NORMAL_APPROX_DF_THRESHOLD = 30.0` is standard and appropriate for performance.

#### **[P2] Bayesian State Invalidation & Out-of-Order Handling**
*   **Status:** **Correct.**
*   **Detail:** The addition of `prior_id` to `PosteriorState` and the check in `infer_risk` correctly handles "re-calibration." If a user updates the baseline (`PriorConfig`) or ingests a late record with a timestamp earlier than the current state, the system detects the staleness and rebuilds the posterior correctly.

---

### 3. API & UI Alignment

#### **[P1] Corrected Alert Alignment**
*   **Location:** `frontend/src/pages/ChartView.vue` (line 479)
*   **Improvement:** Changing alert mapping from `alert.created_at` to `alert.qc_record_timestamp` is a vital fix. Previously, alerts appeared at the time of *ingestion*, which could be hours after the actual QC failure, making the chart misleading.

#### **[P2] Risk Line Chart Actionability**
*   **Detail:** Transitioning the risk chart from a scatter plot of alerts to a continuous line plot of the predictive risk score (`riskPoints`) is highly valuable. It allows lab managers to see "approaching" risk (e.g., a score climbing from 20 to 60) before a hard threshold is crossed and an alert is fired.

---

### 4. Suggested Fixes

| File | Issue | Fix |
| :--- | :--- | :--- |
| `app/bayesian.py` | Side-effect commits | Remove `session.commit()` from `rebuild_posterior_state` and `infer_risk`. Use `session.add(state)` but defer the commit to `app/main.py`. |
| `app/main.py` | Chart O(N) walk | Fetch `PosteriorState` first. If `state.updated_at` is between the prior start and the chart end, start the math walk from the state's `mu_n`/`kappa_n` instead of the prior's `mu0`/`kappa0`. |
| `app/models.py` | Validator Strictness | Ensure `model_validator` in `StreamConfigBase` allows legacy data where `warning_limit_sd` might equal `action_limit_sd` (change `<` to `<=`). |
| `app/bayesian.py` | `_list_priors` | Add caching or limit the query if the number of prior versions becomes large (though typically small per stream). |

**Summary:** The diff significantly matures the statistical engine. Resolving the $O(N)$ chart performance and the transactional side-effects in the inference engine will make this production-ready.
