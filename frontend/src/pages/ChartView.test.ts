// @vitest-environment happy-dom
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ElementPlus from "element-plus";

const charts = vi.hoisted(() => {
  const instances: Array<{
    setOption: ReturnType<typeof vi.fn>;
    on: ReturnType<typeof vi.fn>;
    resize: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
  }> = [];
  return { instances, init: vi.fn(() => {
    const chart = { setOption: vi.fn(), on: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
    instances.push(chart);
    return chart;
  }) };
});

const apiGet = vi.hoisted(() => vi.fn());
vi.mock("../charts/echarts", () => ({ init: charts.init }));
vi.mock("../api/client", () => ({ api: { get: apiGet, patch: vi.fn() } }));

import ChartView from "./ChartView.vue";
import { clearStreamCatalog } from "../api/streamCatalog";

describe("ChartView orchestration", () => {
  beforeEach(() => {
    charts.instances.length = 0;
    charts.init.mockClear();
    apiGet.mockReset();
    clearStreamCatalog();
    apiGet.mockImplementation(async (path: string) => path === "/stream-catalog" ? [{
      stream_id: "demo-stream",
      target_value: 100,
      sigma: 2,
      warning_limit_sd: 2,
      action_limit_sd: 3,
      risk_threshold_warn: 50,
      risk_threshold_hold: 80,
    }] : {
      records: [{
        id: 1,
        timestamp: "2026-01-01T00:00:00Z",
        result_value: 100,
        include_in_stats: true,
        disposition: "accept",
        signals: [],
        bayesian_risk: {
          probability_outside_warning: 0.02,
          probability_outside_limits: 0.01,
          predictive_sigma: 2,
          risk_score: 1,
        },
      }],
      alerts: [],
      events: [],
      lot_segments: [],
    });
  });

  it("loads chart data and renders both accessible canvases with ECharts isolated", async () => {
    const wrapper = mount(ChartView, {
      props: { kiosk: true, forcedStreamId: "demo-stream", forcedMode: "both" },
      global: {
        plugins: [ElementPlus],
        stubs: {
          ChartDataTable: true,
          ChartLegend: true,
          ChartPointDialog: true,
          ChartRiskBadge: true,
        },
      },
    });
    await flushPromises();
    await flushPromises();
    expect(apiGet).toHaveBeenCalledWith("/stream-catalog");
    expect(apiGet).toHaveBeenCalledWith(expect.stringContaining("/streams/demo-stream/chart?"));
    expect(charts.init).toHaveBeenCalledTimes(2);
    expect(charts.instances.every((chart) => chart.setOption.mock.calls.length === 1)).toBe(true);
    expect(wrapper.findAll('[role="img"]')).toHaveLength(2);
    wrapper.unmount();
    expect(charts.instances.every((chart) => chart.dispose.mock.calls.length === 1)).toBe(true);
  });
});
