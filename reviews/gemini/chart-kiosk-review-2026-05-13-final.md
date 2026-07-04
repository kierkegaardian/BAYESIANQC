Based on a strict review of the BAYESIANQC chart/kiosk changes, the implementation is solid, following engineering standards and addressing the reported issues correctly.

### Findings First

#### Must-fix bugs/regressions
*   **None identified.** The logic for date handling, resize debouncing, and marker overlays is technically sound.
*   **Type Safety:** `ChartView.vue` correctly uses `as const` for ECharts literal types and leverages `MarkLineData` for consistent data shaping.
*   **Tooltip Accuracy:** The `hasNumericChartValue` priority fix successfully prevents the common "null-value tooltip" bug in broken-axis charts.

#### Risky edge cases
*   **Visual Clutter:** The addition of both `eventLines` and `alertLines` to the `resultSeries` will cause visual congestion on high-frequency streams. While correctly implemented, this will eventually require the "Recommended" toggle controls.
*   **Local/UTC Boundaries:** `startOfSelectedDay` and `endOfSelectedDay` convert local picker dates to UTC boundaries. This is correct for "Lab Day" queries but assumes the backend storage/query logic treats these as absolute UTC instants.
*   **Race Conditions:** `loadChart` lacks a loading state or `AbortController`. Rapidly changing stream selections could lead to overlapping API responses updating the chart state out of order.

#### Missing tests
*   **Frontend Option Builders:** The logic for transforming `StreamChartOutEvaluated` into `EChartsOption` (specifically the complex `resultMarkLines` array construction) is not covered by unit tests.
*   **Date Formatting:** No unit tests for `startOfSelectedDay`/`endOfSelectedDay` to verify edge cases around DST or leap years.

---

### Detailed Review

#### `ChartView.vue`
- **Resize Logic:** Implementation of `resizeCharts` with `window.setTimeout` and cleanup in `onBeforeUnmount` is correct and prevents memory leaks/stale timers.
- **Date Handling:** Moving from `.toISOString()` to `startOfSelectedDay`/`endOfSelectedDay` correctly fixes the "missing data on the last day" bug by ensuring the range covers 00:00:00 to 23:59:59.999 local time.
- **Marker Overlays:** Correctly combines lot segments, events, and alerts into a single `markLine` data array. Using `dotted` for events and `solid` for alerts provides clear visual distinction.

#### Kiosk Fixture (`scripts/load_chart_kiosk_suite.py`)
- **Robustness:** Handles idempotency via `Idempotency-Key`, preventing duplicate records on re-runs.
- **Compatibility:** Uses `datetime.fromisoformat` with `Z` replacement for Python 3.9+ compatibility.
- **Validation:** The set-based `existing_event_keys` check prevents duplicate event creation.

#### Automated Test (`tests/test_chart_kiosk.py`)
- **Coverage:** Exercises the full lifecycle: stream setup, prior configuration, CSV ingestion, event logging, and record resolution.
- **Verification:** Assertions correctly target lot segments, event counts, and the specific behavior of excluded/resolved outliers on the chart output.

### Verdict
**Approved.** The changes are clean, the kiosk fixture provides excellent regression coverage, and the specific UI fixes (resize, tooltip, date range) directly improve production quality. Recommended follow-ups (splitting `ChartView.vue` and adding frontend unit tests) should be prioritized in the next sprint.
