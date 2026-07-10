import { describe, expect, it } from "vitest";
import type { QCRecordChartOutEvaluated, StreamConfigOut } from "../api/contracts";
import { summarizeChartRisk } from "./chartRisk";

const stream = {
  sigma: 1,
  risk_threshold_warn: 50,
  risk_threshold_hold: 80,
  bayes_warn_prob_threshold: null,
  bayes_hold_prob_threshold: null,
} as unknown as StreamConfigOut;

function record(timestamp: string, actionRisk: number, disposition: "accept" | "reject") {
  return {
    id: Date.parse(timestamp),
    timestamp,
    result_value: 10,
    include_in_stats: true,
    disposition,
    signals: [],
    bayesian_risk: {
      probability_outside_limits: actionRisk,
      probability_outside_warning: actionRisk,
      predictive_sigma: 1,
      risk_score: actionRisk * 100,
    },
  } as unknown as QCRecordChartOutEvaluated;
}

describe("summarizeChartRisk", () => {
  it("does not present a frequentist rejection as high predictive risk", () => {
    const summary = summarizeChartRisk([record("2026-01-01T00:00:00Z", 0.01, "reject")], stream);
    expect(summary?.tone).toBe("low");
    expect(summary?.riskLabel).toBe("1.0%");
    expect(summary?.stateLabel).toBe("Reject");
  });

  it("labels the highest predictive risk in the selected window", () => {
    const summary = summarizeChartRisk([
      record("2026-01-01T00:00:00Z", 0.9, "accept"),
      record("2026-01-02T00:00:00Z", 0.02, "accept"),
    ], stream);
    expect(summary?.riskLabel).toBe("90%");
    expect(summary?.riskContextLabel).toBe("Highest in selected window");
    expect(summary?.detailLabel).toContain("Highest in selected window");
    expect(summary?.detailLabel).not.toContain("Peak");
  });
});
