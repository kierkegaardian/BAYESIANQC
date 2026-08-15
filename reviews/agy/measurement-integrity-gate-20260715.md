# Tier-B Read-Only Patch Review

## P0/P1 Findings
**Explicit Statement:** No P0 or P1 defects were identified in this patch. The Student-t tail-stability logic, Pydantic `FiniteFloat` validation, omitted beta derivation, unit conversion schemas, and frontend measurement blanking are mathematically and logically correct.

---

## P2 Gaps

### 1. Potential `NameError` due to missing `timezone` import in `app/main.py`
* **File:** [app/main.py](file:///home/user/.gemini/antigravity-cli/scratch/app/main.py#L978)
* **Description:** The patch introduces `datetime.now(timezone.utc)` but does not add an explicit import for `timezone` from the `datetime` module. If `timezone` is not already imported elsewhere in `app/main.py`, calling `create_prior` with an omitted `beta0` will raise a runtime `NameError`.
* **Recommendation:** Ensure `timezone` is imported:
  ```python
  from datetime import datetime, timezone
  ```

### 2. Form Input Robustness for `defaultPriorBeta` in Frontend
* **File:** [frontend/src/pages/DatastreamSetup.vue](file:///home/user/.gemini/antigravity-cli/scratch/frontend/src/pages/DatastreamSetup.vue#L129)
* **Description:** The computed property `defaultPriorBeta` calculates `(draft.prior_alpha0 - 1) * draft.sigma ** 2`. If a user temporarily clears the `prior_alpha0` or `sigma` fields in the UI form, these properties may resolve to `null`, `""`, or `undefined`. This coercion can result in `NaN` or negative prior betas, causing display anomalies or downstream validation errors.
* **Recommendation:** Wrap the computation in a safety guard:
  ```typescript
  const defaultPriorBeta = computed(() => {
    const alpha = Number(draft.prior_alpha0);
    const sigma = Number(draft.sigma);
    if (!isNaN(alpha) && alpha > 1 && !isNaN(sigma) && sigma > 0) {
      return Number(((alpha - 1) * sigma ** 2).toFixed(6));
    }
    return null;
  });
  ```

### 3. Concurrency Safety of `effective_config` Database Read
* **File:** [app/main.py](file:///home/user/.gemini/antigravity-cli/scratch/app/main.py#L976-L982)
* **Description:** In `create_prior`, the query for `effective_config` runs within a `stream_write_lock`. If `stream_write_lock` is a thread-level or process-level lock, it does not guarantee protection against concurrent database updates from separate service/worker nodes. This could lead to a race condition where a configuration is updated concurrently, causing an incorrect `sigma` value to be retrieved for the derivation of `beta0`.
* **Recommendation:** Consider locking the stream row at the database transaction level (e.g., using `with_for_update()`) if running in a multi-instance production environment.
