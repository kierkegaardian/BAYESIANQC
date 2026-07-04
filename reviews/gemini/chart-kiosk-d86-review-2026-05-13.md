### Code Review: BAYESIANQC Chart Kiosk Expansion & D86 Fixtures

#### Findings Summary
The chart kiosk expansion and D86 fixtures are well-structured and provide excellent automated coverage for complex distillation QC workflows. However, there are two **P0 bugs** in the loader logic that could lead to incomplete deployments and misleading output, along with several robustness issues in the fixture synchronization.

---

#### Must-fix (Bugs & Regressions)

1. **[P0] Loader ignores D86 streams on `--skip-config`**: In `scripts/load_chart_kiosk_suite.py`, the `main` function (lines 240-243) hardcodes `stream_ids = ["hba1c-kiosk"]` if `--skip-config` is passed. This causes the script to ignore the D86 streams even if they already exist in the database, resulting in a misleading final console message that omits the six new D86 routes.
2. **[P0] Case-Sensitive Asset Lookups**: `ensure_assets` (lines 90-112) performs case-sensitive checks against existing instruments, methods, and analytes. If the database contains "PAC" but the fixture specifies "pac", the loader will attempt to create a duplicate, likely failing with a 400/500 error or polluting the metadata with near-duplicates.
3. **[P1] Fixture Synchronization Gap**: `ensure_prior_config` (line 153) returns `False` if *any* prior exists for a stream. This means updates to fixture priors (e.g., tuning `mu0` or `kappa0` for the D86 streams) will never be applied unless the database is manually purged. The loader should ideally check if the existing prior matches the fixture or provide an overwrite flag.

---

#### Risky Edge Cases

1. **[P1] Event History Scaling**: `existing_event_keys` (line 207) only fetches the last 500 events to check for duplicates. If a kiosk stream accumulates more than 500 events, the loader will start attempting to re-insert historical events, relying on the API's internal idempotency which may not be exhaustive for events (unlike records).
2. **[P1] Loader Crash on Invalid JSON**: `clean_record` (line 53) uses `json.loads(str(payload["flags"]))`. If a CSV row contains a malformed or non-JSON string in the `flags` column, the script will crash with a `JSONDecodeError` rather than reporting the specific row and continuing or failing gracefully.
3. **[P2] Redundant API Pressure**: `ensure_assets` (lines 114-116) fetches the full list of methods and analytes inside loops for every path and asset set. For large fixture suites, this creates unnecessary API overhead; these should be cached locally during the script execution.

---

#### Missing Tests

1. **Loader CLI Verification**: There are no tests covering the loader's command-line interface, specifically the interaction between `--skip-assets`, `--skip-events`, and the record loading sequence.
2. **Exact Path Parity**: `tests/test_chart_kiosk.py` uses the `/qc/records/csv` endpoint for bulk upload, but the production loader script (`load_chart_kiosk_suite.py`) uses individual `POST /qc/records` calls. The tests should verify the single-record path used by the script to ensure it handles the fixture payloads identically.
3. **Idempotency Validation**: Add a test case that runs the `load_kiosk_fixture` twice in succession to verify that no duplicate events, instruments, or configs are created.

#### Recommendation
**Approved with fixes.** Address the P0 logic bug in `main` and the case-sensitivity in `ensure_assets` before merging. Consider adding a `--force` or `--update` flag to the loader to allow refreshing existing prior/stream configurations.
