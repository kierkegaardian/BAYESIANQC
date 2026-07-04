The review of the **BAYESIANQC** chart and kiosk enhancements is complete. The implementation is high-quality, with effective fixes for date range selection and tooltip accuracy.

### Findings

#### 1. Must-Fix Bugs
*   **None Identified.** (Initial concerns regarding `alerts` scope and `MarkLineComponentOption` types were resolved by verifying the full source file context; they are correctly defined/imported).

#### 2. Risky Edge Cases
*   **Timezone-Dependent Day Boundaries:** `startOfSelectedDay` and `endOfSelectedDay` utilize the browser's local timezone (`setHours(0/23)`).
    *   *Risk:* Users in different timezones selecting the same "calendar day" will request different UTC windows from the API.
    *   *Recommendation:* Verify if the requirement is "User's Local Day" (correct as-is) or a canonical "UTC Day". If the latter, refactor to use `Date.UTC`.
*   **Timeline Visual Clutter:** Plotting every event and alert as a vertical `markLine` will cause significant visual noise on high-volume or "chatty" streams.
    *   *Recommendation:* Prioritize the "chart-level controls" recommended in `CHART_KIOSK_REVIEW.md` to allow operators to toggle event/alert overlays.
*   **ECharts Label Collisions:** `markLine` labels for events, alerts, and lot changes may overlap if timestamps are near-identical.
    *   *Recommendation:* Consider using `emphasis` or `avoidLabelOverlap` (though difficult with `markLine`) if fixtures show unreadable labels on busy days.

#### 3. Missing Tests
*   **Frontend Option Builder Units:** The logic for transforming `StreamChartOutEvaluated` into `EChartsOption` (specifically `resultMarkLines` and the priority tooltip logic) is complex but currently only covered by backend integration tests.
    *   *Recommendation:* Extract the option-building logic into a separate utility/composable to enable Vitest unit testing.

### Component Feedback

| Component | Note |
| :--- | :--- |
| **Date Handling** | **Excellent fix.** Moving the end-date boundary to `23:59:59` correctly includes results from the final selected day. |
| **Tooltip Logic** | **Excellent fix.** `hasNumericChartValue` correctly prioritizes real values over `null` main-series points on broken axes. |
| **Kiosk Fixture** | **Robust.** The `load_chart_kiosk_suite.py` script and its associated CSV/JSON samples provide a realistic, deterministic test bed. |
| **Resize Logic** | **Correct.** Debounced resize (120ms) and proper listener cleanup in `onBeforeUnmount` prevent memory leaks and layout thrashing. |

### Final Sanity Check
The `test_chart_kiosk.py` successfully exercises the resolution of outliers and the inclusion of evaluations in the chart output, which are critical for the kiosk display's integrity. No regressions noted.
