### Review Findings

**Must-fix / Bugs**
1.  **Timezone Displacement in ISO Strings:** `startOfSelectedDay` and `endOfSelectedDay` use local `Date` methods (`setHours`) but export via `toISOString()`. This creates a "floating" UTC window that shifts based on the client's local timezone (e.g., a user in UTC-5 selecting Jan 5 sends `2026-01-05T05:00:00Z`). If the backend expects pure UTC-truncated days, this will consistently miss early-morning records.
2.  **Unthrottled Resize Listener:** `window.addEventListener("resize", resizeCharts)` triggers ECharts `.resize()` calls on every pixel change. This causes significant UI jank during manual window resizing or on low-power kiosk hardware.

**Risky Edge Cases**
1.  **MarkLine Overlap/Clutter:** Merging lot transitions, events, and alerts into a single `resultMarkLines` array without collision management will result in unreadable overlapping labels if multiple markers share a timestamp (e.g., a lot change occurring exactly at a maintenance event).
2.  **Tooltip Selection:** `hasNumericChartValue` correctly filters out broken-axis `null` values, but if multiple numeric series overlap at one point, the tooltip may still pick an arbitrary series.

**Missing Tests**
1.  **Frontend Date Utilities:** Isolation tests for `startOfSelectedDay` and `endOfSelectedDay` are needed to verify behavior across different browser timezones.
2.  **Loader Robustness:** `load_chart_kiosk_suite.py` uses `SystemExit` on any API failure. For kiosk/demo environments, it should ideally log the error and continue to ensure partial data availability rather than failing the entire suite.

---

### Detailed Review

#### `frontend/src/pages/ChartView.vue`
*   **Resize Logic:** **Action required.** Wrap `resizeCharts` in a 100-200ms debounce to prevent performance degradation during resize events.
*   **Marker Merging:** The implementation of `resultMarkLines` and `riskMarkLines` is clean, but the logic should eventually support toggling these overlays to prevent chart "noise" in high-event streams.
*   **Type Safety:** Proper use of `MarkLineData` type and `as const` for ECharts enums (e.g., `type: "dotted" as const`) is a good improvement.
*   **Tooltip Fix:** The `hasNumericChartValue` helper is a surgical and effective fix for the reported "clipped main-series null" outlier bug.

#### `scripts/load_chart_kiosk_suite.py`
*   **Idempotency:** Good implementation of `Idempotency-Key` using `run_id`. This allows the script to be run repeatedly against a dev environment without duplication.
*   **Event Deduplication:** The `existing_event_keys` set comparison is a robust way to handle partial fixture updates.

#### `tests/test_chart_kiosk.py`
*   **Coverage:** Excellent end-to-end verification. It correctly exercises the integration between ingestion, resolution, and the chart evaluation output.
*   **Assertions:** Explicitly checking that `bayesian_risk` is `None` for resolved/excluded records is a high-value regression check for the statistical engine.

#### `docs/CHART_KIOSK_REVIEW.md`
*   **Architectural Debt:** The recommendation to split `ChartView.vue` (currently 1,000+ lines) is correct. Moving ECharts option construction into dedicated composables or builder classes should be the next priority.
