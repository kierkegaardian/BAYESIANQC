This review covers the final D86 loader and test follow-up.

### Must-Fix Bugs & Regressions

1.  **Missing Record Idempotency Assertion**: In `test_chart_kiosk_loader_functions_are_idempotent`, you verify that assets, streams, priors, and events are idempotent (returning 0 created on second pass), but you **omitted the second call to `load_records`**. The test currently does not prove that `Idempotency-Key` works or that the loader correctly identifies and ignores duplicate records.
2.  **Rigid Method Lookup in `ensure_assets`**: The analyte loop uses `methods_by_key.get(...)` which is only populated by methods found in the *current* execution's fixture files. If a user tries to load a fixture containing only analytes (targeting existing instruments/methods), the script will `SystemExit`.
    *   **Fix**: The analyte loop should fall back to `methods_for_instrument(instrument_id).get(analyte_key)` if `methods_by_key` misses.
3.  **Untested `json.loads` Error Path**: `load_records` now catches `json.JSONDecodeError` for the `flags` column and raises `SystemExit`. This is an important safety check for CSV hand-editing but is not exercised in `tests/test_chart_kiosk.py`.

### Risky Edge Cases

1.  **Duplicate Loader Logic in Tests**: `tests/test_chart_kiosk.py` contains `load_kiosk_assets` and `load_kiosk_fixture`, which largely reimplement the logic found in `scripts/load_chart_kiosk_suite.py`. This creates a maintenance burden where the test might pass even if the actual loader script is broken (or vice versa).
    *   **Recommendation**: Refactor `test_chart_kiosk_fixture_exercises_chart_annotations` to use the `ensure_*` and `load_*` functions directly from the script to ensure the test exercises the production code path.
2.  **Instrument-Method Cache Sync**: `methods_for_instrument` caches based on `instrument_id`. If two fixture files are processed and the second one adds a method to an instrument that was already fetched in the first file, the local cache might be stale. However, since the script updates the local cache (`existing[method_key] = ...`) after a POST, this is likely safe as long as no external processes are modifying assets simultaneously.

### Missing Tests

1.  **Case-Insensitivity Verification**: While the code now uses `normalized_name`, there is no test case in `test_chart_kiosk.py` that verifies "OptiDist" in a fixture matches "optidist" on the server.
2.  **`--skip-config` CLI Logic**: The `main()` function's logic for `args.skip_config` (populating `stream_ids` from files without hitting the API) is not covered by any unit or integration test. A typo in the list comprehension could break the final summary printout.
3.  **Invalid JSON Flags**: As noted in Must-Fix #3, a test case with a malformed `flags` string in the CSV would ensure the `SystemExit` behaves as expected.

### Overall Assessment
The idempotency and casefolding improvements are solid, but the test suite needs to actually execute the record idempotency check and the script's entry-point logic to be considered "fully verified." The duplication of loader logic in `test_chart_kiosk.py` is the primary technical debt item.
