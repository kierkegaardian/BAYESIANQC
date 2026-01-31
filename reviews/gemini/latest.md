I have reviewed the provided diffs. The codebase changes introduce significant improvements in typesafety and API structure, but several critical reliability and maintainability issues were introduced.

### Must-Fix Bugs & Regressions

1.  **CSV Ingestion Data Loss (`app/main.py`)**
    *   **Context:** In `ingest_qc_records_csv`, the loop catches exceptions and calls `session.rollback()`.
    *   **Issue:** Since `session` is dependency-injected (and likely shared for the request scope), `session.rollback()` will discard **all** previously processed rows in the loop, not just the current failing one (unless explicit intermediate commits exist). The API will report `accepted` counts that do not match the database state.
    *   **Fix:** Use `session.begin_nested()` (savepoints) within the loop to isolate row failures, or ensure explicit commits per row.

2.  **Audit Log Crash (`app/main.py`)**
    *   **Context:** `_audit_out` raises `RuntimeError("Audit entry missing after snapshot")` if `entry.after` is `None`.
    *   **Issue:** The `AuditEntry` model defines `after` as optional (likely for deletion events). This check will cause the `GET /audit` endpoint to return a 500 Internal Server Error as soon as a single "delete" audit entry exists.
    *   **Fix:** Remove the exception or handle `None` gracefully.

3.  **Hardcoded Python Path (`frontend/package.json`)**
    *   **Context:** `"gen:api": "../.venv/bin/python ..."`
    *   **Issue:** This assumes a specific relative path and OS (Linux/Unix) for the virtual environment. It will fail on Windows or if the venv is named differently.
    *   **Fix:** Use `python` (assuming active environment) or make the path configurable.

### Risky Edge Cases

1.  **Date String Comparison (`frontend/src/pages/ChartView.vue`)**
    *   **Issue:** `deriveLotSegments` compares date strings (`start !== end`). API serialization changes (e.g., timezone differences) could break equality checks.
    *   **Recommendation:** Parse to timestamps before comparing.

2.  **Chart Interaction (`frontend/src/pages/ChartView.vue`)**
    *   **Issue:** The click handler explicitly checks `seriesName !== "Result"`.
    *   **Risk:** Users clicking on "Risk" points (which are interactive-looking) will get no response, potentially confusing them.

3.  **Frontend Types Sync**
    *   **Issue:** `frontend/src/api/contracts.ts` manually re-exports types. If `gen:api` changes `schema.ts` significantly, `contracts.ts` may become stale or break without a clear build error if not strictly checked.

### Test Ideas

1.  **Partial Batch Failure:** Upload a CSV with [Valid, Invalid, Valid] rows. Assert that the database contains exactly 2 new records.
2.  **Audit Nullability:** Manually insert an audit record with `after=None` and verify `GET /audit` returns 200 OK.
3.  **Chart Series Click:** Verify that clicking on outlier/risk points either triggers the resolution flow or provides feedback.
