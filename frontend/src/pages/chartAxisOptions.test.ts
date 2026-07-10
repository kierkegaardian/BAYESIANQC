import { describe, expect, it, vi } from "vitest";

vi.mock("echarts", () => ({ init: vi.fn() }));

import type { StreamConfigOut } from "../api/contracts";
import { formatChartAxisTick } from "./chartAxisOptions";
import { buildControlSeries } from "./chartControlSeries";
import { buildResultsAxes } from "./chartResultsAxes";
import type { OutlierPoint } from "./chartPoint";

describe("chart axes", () => {
  it("formats large and fractional ticks consistently", () => {
    expect(formatChartAxisTick(1234.56)).toBe((1234.56).toLocaleString(undefined, { maximumFractionDigits: 1 }));
    expect(formatChartAxisTick(1.234)).toBe((1.234).toLocaleString(undefined, { maximumFractionDigits: 2 }));
  });

  it("uses the same action-limit extent for the axis and overlays", () => {
    const config = buildControlSeries({
      target_value: 100,
      sigma: 2,
      warning_limit_sd: 2,
      action_limit_sd: 3,
    } as unknown as StreamConfigOut);
    expect(config?.minValue).toBe(94);
    expect(config?.maxValue).toBe(106);
    expect(config?.yAxis.min).toBe(94);
    expect(config?.yAxis.max).toBe(106);
  });

  it("shares the time extent across broken panels and labels the axis break", () => {
    const control = buildControlSeries({
      target_value: 100, sigma: 2, warning_limit_sd: 2, action_limit_sd: 3,
    } as unknown as StreamConfigOut);
    const outlier = {
      value: ["2026-01-02T00:00:00Z", 120], record_id: 1, symbolRotate: 0,
      itemStyle: { color: "#ef4444" },
      label: { show: true, formatter: "120", position: "top", color: "#991b1b", fontWeight: 600 },
    } satisfies OutlierPoint;
    const extent = { min: "2026-01-01T00:00:00Z", max: "2026-01-03T00:00:00Z" };
    const axes = buildResultsAxes(control, [outlier], [], false, false, extent);
    expect(axes.xAxes.every((axis) => axis.min === extent.min && axis.max === extent.max)).toBe(true);
    expect(String(axes.yAxes[0].name)).toContain("axis break");
  });
});
