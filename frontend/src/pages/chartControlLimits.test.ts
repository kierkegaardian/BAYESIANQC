import { describe, expect, it } from "vitest";

import { buildControlLimitSteps, type ProvenanceRecord } from "./chartControlLimits";

const configured = (id: number, timestamp: string, centerline: number): ProvenanceRecord => ({
  id,
  timestamp,
  evaluation: {
    threshold_mode: "explicit_probabilities",
    limits: {
      source: "configured",
      centerline,
      sigma: 2,
      warning_lower: centerline - 4,
      warning_upper: centerline + 4,
      action_lower: centerline - 6,
      action_upper: centerline + 6,
    },
  },
});

describe("buildControlLimitSteps", () => {
  it("uses each record's immutable applied limits across config changes", () => {
    const steps = buildControlLimitSteps([
      configured(1, "2026-01-01T00:00:00Z", 10),
      configured(2, "2026-02-01T00:00:00Z", 20),
    ]);

    expect(steps.centerline).toEqual([
      ["2026-01-01T00:00:00Z", 10],
      ["2026-02-01T00:00:00Z", 20],
    ]);
    expect(steps.actionUpper.map((point) => point[1])).toEqual([16, 26]);
    expect(steps.minValue).toBe(4);
    expect(steps.maxValue).toBe(26);
    expect(steps.segments[0]?.end).toBe("2026-02-01T00:00:00Z");
  });

  it("creates a gap for legacy records instead of inventing current limits", () => {
    const steps = buildControlLimitSteps([
      configured(1, "2026-01-01T00:00:00Z", 10),
      { id: 2, timestamp: "2026-01-02T00:00:00Z", evaluation: null },
    ]);

    expect(steps.centerline[1]).toEqual(["2026-01-02T00:00:00Z", null]);
    expect(steps.actionLower[1]).toEqual(["2026-01-02T00:00:00Z", null]);
    expect(steps.legacyRecordIds).toEqual([2]);
    expect(steps.segments).toHaveLength(1);
  });

  it("labels a fixed baseline with dates and sample count", () => {
    const record = configured(1, "2026-02-01T00:00:00Z", 10);
    if (!record.evaluation) throw new Error("test fixture missing evaluation");
    record.evaluation.limits = {
      ...record.evaluation.limits,
      source: "fixed_baseline",
      baseline_start: "2026-01-01T00:00:00Z",
      baseline_end: "2026-01-31T00:00:00Z",
      baseline_count: 12,
    };
    expect(buildControlLimitSteps([record]).fixedBaselineLabels[0]).toContain("n=12");
  });
});
