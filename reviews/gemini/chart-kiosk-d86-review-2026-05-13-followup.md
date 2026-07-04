### Findings: BAYESIANQC D86 Follow-up Review

#### 1. Must-Fix: Performance & Integrity (Loader)
*   **O(N) API Overhead in `ensure_assets`**: The loader performs a GET request to `/methods` for every method and `/analytes` for every analyte. With the D86 expansion (6+ streams), this creates unnecessary network churn.
*   **Analyte Collision/Duplicate POSTs**: Within the `ensure_assets` analyte loop, the `existing` map is never updated after a successful POST. If a fixture contains duplicate analytes or if multiple fixture files are processed in one run, the loader will attempt redundant POSTs because it only knows about assets that existed *before* the script started.
*   **Initial Instrument Fetch**: `ensure_assets` fetches all instruments at the start, but if a new instrument is created during the loop, `instruments_by_key` is updated. However, `existing` for methods and analytes is *not* handled with the same consistency, leading to the state drift mentioned above.

#### 2. Must-Fix: Test Coverage Gap
*   **Logic Duplication vs. Script Verification**: `tests/test_chart_kiosk.py` re-implements the loading logic (using `AsyncClient`) rather than executing `scripts/load_chart_kiosk_suite.py`.
    *   **Risk**: The complex case-folding (`normalized_name`), prior-matching (`prior_matches`), and idempotency-key logic in the actual loader remain **untested** by CI.
    *   **Requirement**: The test should ideally invoke the script via `subprocess` or import and run its `main` to ensure the production loading path is valid.

#### 3. Risky Edge Cases
*   **`clean_record` JSON handling**: `payload["flags"] = json.loads(str(payload["flags"]))` is fragile. If the input is already a list/dict (e.g., if `clean_record` is reused for JSON input), `str()` will produce invalid JSON for `loads`.
*   **Timestamp Normalization**: `normalized_timestamp` replaces `Z` with `+00:00` and then converts back to `Z`. This is safe for standard ISO8601, but the loader should explicitly handle sub-second precision if the API returns more/fewer digits than the fixture (e.g., `.000Z` vs `.000000Z`), as string comparison in `prior_matches` will fail on precision mismatch.

#### 4. Missing Improvements
*   **`--skip-config` Validation**: When `--skip-config` is used, the loader "assumes" streams exist but provides no warning if they don't. It only collects IDs from local files. A single HEAD or GET check per `stream_id` would prevent runtime errors during record ingestion.
*   **Event Fetch Limit**: `existing_event_keys` uses `limit=5000`. While sufficient for the kiosk, a production-scale stream will eventually exceed this, causing the deduplication logic to fail and recreate old events.

#### Recommendation
**Blocking**: Update `test_chart_kiosk.py` to exercise the actual script logic. Refactor `ensure_assets` to update its local "existing" cache after POSTing to prevent duplicate attempts within a single execution.
