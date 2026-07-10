import { describe, expect, it } from "vitest";
import type { BayesianRisk, StreamChartOutEvaluated, StreamConfigOut } from "../api/contracts";
import { availableRiskNumber, unavailableRiskMessage } from "./bayesianRiskAvailability";
import { prepareChartData } from "./chartDataTransform";
import type { ChartPoint } from "./chartPoint";
import { probabilityToPercent, summarizeChartRisk } from "./chartRisk";
import { formatResultsTooltip } from "./chartTooltips";

const unavailableRisk = {
  status: "unavailable",
  unavailable_reason: "missing_effective_prior",
  probability_outside_limits: null,
  probability_outside_warning: null,
  risk_score: null,
  posterior_mean: null,
  predictive_sigma: null,
  warn_streak: 0,
  hold_streak: 0,
} as unknown as BayesianRisk;

const record = {
  id: 1,
  timestamp: "2026-01-01T00:00:00Z",
  result_value: 100,
  include_in_stats: true,
  disposition: "monitor",
  signals: [],
  bayesian_risk: unavailableRisk,
};
const stream = {
  target_value: 100,
  sigma: 2,
  warning_limit_sd: 2,
  action_limit_sd: 3,
  risk_threshold_warn: 50,
  risk_threshold_hold: 80,
} as unknown as StreamConfigOut;

describe("unavailable Bayesian inference", () => {
  it("never coerces missing metrics to zero", () => {
    expect(probabilityToPercent(null)).toBeNull();
    expect(availableRiskNumber(unavailableRisk, "risk_score")).toBeNull();
    expect(unavailableRiskMessage(unavailableRisk)).toContain("Missing effective prior");
  });

  it("returns an explicit unavailable summary and null plot points", () => {
    const data = { records: [record], alerts: [], events: [], lot_segments: [] } as unknown as StreamChartOutEvaluated;
    const summary = summarizeChartRisk(data.records, stream);
    const prepared = prepareChartData(data, stream, false, false);
    expect(summary?.status).toBe("unavailable");
    expect(summary?.riskLabel).toBe("Unavailable");
    expect(prepared.warningProbabilityPoints[0][1]).toBeNull();
    expect(prepared.actionProbabilityPoints[0][1]).toBeNull();
  });

  it("uses unavailable wording in point tooltips without zero metrics", () => {
    const point = {
      value: [record.timestamp, record.result_value],
      record_id: 1,
      bayesian_risk: unavailableRisk,
    } satisfies ChartPoint;
    const tooltip = formatResultsTooltip([{ data: point }], stream);
    expect(tooltip).toContain("Unavailable");
    expect(tooltip).toContain("Missing effective prior");
    expect(tooltip).not.toContain("0/100");
  });
});
