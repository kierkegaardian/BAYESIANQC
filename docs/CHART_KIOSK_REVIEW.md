# Chart Review and Kiosk Fixture

## Fixes made in this pass
- Render QC event timeline markers on the result chart and risk chart. The API already returned `events`, but the chart page ignored them.
- Render alert timeline markers on the result chart. The risk chart already plotted alert points, but result-only mode did not expose alert timing.
- Treat the selected end date as the end of that local day. Previously, choosing an end date sent midnight, which excluded most results from that same day.
- Debounce ECharts resize handling so full-screen or kiosk display changes do not leave stale chart dimensions or cause resize jank.
- Prefer numeric chart points in result tooltips. Broken-axis outliers no longer show the clipped main-series `null` value when the outlier marker has the real value.

## Kiosk fixture suite
- Stream config: `samples/chart_kiosk_stream.json`
- Prior config: `samples/chart_kiosk_prior.json`
- QC records: `samples/chart_kiosk_qc_records.csv`
- QC events: `samples/chart_kiosk_events.json`
- D86 assets: `samples/chart_kiosk_assets.json`
- D86 stream configs: `samples/chart_kiosk_d86_streams.json`
- D86 prior configs: `samples/chart_kiosk_d86_priors.json`
- D86 QC records: `samples/chart_kiosk_d86_records.csv`
- D86 events: `samples/chart_kiosk_d86_events.json`
- Loader for a running local API:
  ```bash
  python scripts/load_chart_kiosk_suite.py --base-url http://127.0.0.1:8010
  ```
- Synthetic multi-domain demo fixture generator:
  ```bash
  python scripts/generate_demo_kiosk_fixtures.py --check
  python scripts/load_chart_kiosk_suite.py --suite demo
  python scripts/load_chart_kiosk_suite.py --suite demo --families fuel_astm,steel_metals
  python scripts/load_chart_kiosk_suite.py --suite all
  ```
- Automated coverage: `tests/test_chart_kiosk.py`

The fixture targets the dedicated `hba1c-kiosk` stream and six D86 OptiDist streams:
- `d86-optidist-od1-ibp`
- `d86-optidist-od1-50pct`
- `d86-optidist-od1-fbp`
- `d86-optidist-od2-ibp`
- `d86-optidist-od2-50pct`
- `d86-optidist-od2-fbp`

The HbA1c fixture covers:
- stable baseline points near target
- high-side warning drift
- high action outlier
- control-material lot transitions across `LOT-001`, `LOT-002`, and `LOT-003`
- low-side warning drift
- low action outlier that is resolved/excluded by the test
- calibration, reagent lot change, control-material lot change, and maintenance event markers
- alert timestamps and persisted per-record evaluations in chart output

The D86 fixture adds:
- two OptiDist-style instruments: `OptiDist OD-1` and `OptiDist OD-2`
- ASTM D86 streams for `IBP`, `50% Recovered`, and `FBP`
- high-side and low-side warning/action examples
- control-material lot transitions between `D86-STD-A` and `D86-STD-B`

The generated synthetic demo suite adds:
- family routes: `/kiosk/demo`, `/kiosk/fuel`, `/kiosk/medical`, `/kiosk/pharma`, and `/kiosk/steel`
- family ids: `fuel_astm`, `medical_clinical`, `pharma_qc`, and `steel_metals`
- 32 synthetic instruments, 100 streams, 2,500 QC records, 300 events, exclusions, scheduled backlog items, completed backlog runs, and quarantine examples
- generated outputs under `samples/demo_kiosk/`, with source definitions in `scripts/demo_kiosk/`

These generated fixtures are product-demo data only. They must not be presented as validated ASTM, manufacturer, clinical, pharmacological, or regulatory reference data.

## Snapshot and Multi-Chart Kiosk Recommendation
- Add chart snapshots: yes. A snapshot should capture the stream id, date window, rendered chart options, API response version, and a PNG/SVG export. This gives review/audit receipts without changing live chart data.
- Add multi-chart kiosks: yes, but make them saved layouts rather than screenshots. A layout should store an ordered list of chart panels, stream ids, date window policy, mode (`results`, `risk`, or `both`), refresh interval, and overlay toggles.
- Build multi-chart first for live operations, then add snapshot export for handoff/audit. The kiosk should remain live; snapshots should be evidence artifacts.

## Verification
- `pytest` passes with the kiosk fixture test included.
- `pyright` reports zero errors.
- `npm run check` passes; Vite still reports the existing large chunk warning.

## Recommended bug fixes next
- Split `frontend/src/pages/ChartView.vue` into smaller chart-option builders/composables. It is over 1,000 lines, so the next meaningful chart change should pull data shaping and ECharts option construction out of the page component.
- Add visible loading, error, and empty-state panels to the chart page. Failed API calls currently surface weakly and kiosk displays need obvious failure states.
- Add a dedicated kiosk route that cycles streams/date windows and hides operational navigation. The fixture is ready for this, but the current UI is still an operator chart page.
- Add chart-level controls for event and alert overlays so busy streams can declutter timeline markers.
- Decide whether resolving a QC result should also update or annotate its existing alert. The chart now shows resolved points, but historical alerts remain open unless handled separately.
- Add frontend unit tests around chart option builders after the chart page is split. The current chart logic is hard to test directly because it is embedded in a single Vue page.
