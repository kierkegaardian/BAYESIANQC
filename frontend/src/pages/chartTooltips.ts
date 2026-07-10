import type { StreamCatalogOut } from "../api/contracts";
import {
  asFormatterItems,
  hasNumericChartValue,
  isChartPoint,
  tooltipLine,
} from "./chartPoint";
import {
  availableRiskNumber,
  riskIsUnavailable,
  unavailableRiskReason,
} from "./bayesianRiskAvailability";

export type TooltipDisplayOptions = {
  appendTo?: "body";
  className: string;
  confine: true;
  extraCssText: string;
  renderMode: "html";
};

export function tooltipDisplayOptions(isKiosk: boolean): TooltipDisplayOptions {
  const common = {
    className: "qc-chart-tooltip",
    confine: true as const,
    extraCssText: [
      "max-width: min(360px, calc(100vw - 32px))",
      "white-space: normal",
      "overflow-wrap: anywhere",
      "line-height: 1.35",
    ].join(";"),
    renderMode: "html" as const,
  };
  return isKiosk ? { ...common, appendTo: "body" } : common;
}

export function formatResultsTooltip(params: unknown, stream?: StreamCatalogOut): string {
  const items = asFormatterItems(params);
  const item = items.find(hasNumericChartValue) ?? items.find((entry) => isChartPoint(entry.data));
  if (!item || !isChartPoint(item.data)) return "";
  const point = item.data;
  const parts = [`<div class="qc-chart-tooltip__time">${new Date(point.value[0]).toLocaleString()}</div>`];
  if (typeof point.value[1] === "number" && Number.isFinite(point.value[1])) {
    parts.push(tooltipLine("Result", point.value[1]));
  }
  if (point.disposition) parts.push(tooltipLine("Overall status", point.disposition));
  if (point.signals?.length) {
    parts.push(tooltipLine("Signals", point.signals.map((signal) => signal.rule).join(", ")));
  }
  const risk = point.bayesian_risk;
  if (risk) {
    if (riskIsUnavailable(risk)) {
      parts.push(tooltipLine("Bayesian inference", "Unavailable"));
      parts.push(tooltipLine("Reason", unavailableRiskReason(risk)));
    } else {
      const score = availableRiskNumber(risk, "risk_score");
      const warning = availableRiskNumber(risk, "probability_outside_warning");
      const action = availableRiskNumber(risk, "probability_outside_limits");
      if (score !== null) parts.push(tooltipLine("Risk", `${score.toFixed(0)}/100`));
      if (warning !== null && action !== null) {
        parts.push(tooltipLine("P warn/action", `${(warning * 100).toFixed(1)}% / ${(action * 100).toFixed(1)}%`));
      }
      const posterior = availableRiskNumber(risk, "posterior_mean");
      if (posterior !== null) parts.push(tooltipLine("Posterior mean", posterior.toFixed(4)));
      const warnRequired = Number(stream?.bayes_warn_consecutive ?? 1);
      const holdRequired = Number(stream?.bayes_hold_consecutive ?? 1);
      const warnStreak = Number.isFinite(Number(risk.warn_streak)) ? Number(risk.warn_streak) : 0;
      const holdStreak = Number.isFinite(Number(risk.hold_streak)) ? Number(risk.hold_streak) : 0;
      parts.push(tooltipLine("Streaks", `warn ${warnStreak}/${warnRequired}, hold ${holdStreak}/${holdRequired}`));
    }
  }
  if (point.lot) parts.push(tooltipLine("Lot", point.lot));
  if (point.include_in_stats === false) {
    parts.push(tooltipLine("Resolved", "excluded from stats"));
    if (point.resolved_reason) parts.push(tooltipLine("Reason", point.resolved_reason));
  }
  return parts.join("");
}

export function formatRiskTooltip(params: unknown): string {
  const items = asFormatterItems(params);
  const primary = items.find((item) => Array.isArray(item.value) && item.value.length === 2);
  if (!Array.isArray(primary?.value) || primary.value.length !== 2) return "";
  const timestamp = String(primary.value[0]);
  const labelTime = Number.isFinite(Date.parse(timestamp)) ? new Date(timestamp).toLocaleString() : timestamp;
  const lines = items.flatMap((item) => {
    if (!Array.isArray(item.value) || item.value.length !== 2) return [];
    const value = Number(item.value[1]);
    if (!Number.isFinite(value)) return [];
    const label = typeof item.seriesName === "string" ? item.seriesName : "Value";
    return [`<div>${label}: ${value.toFixed(1)}%</div>`];
  });
  return [
    `<div class="qc-chart-tooltip__time">${labelTime}</div>`,
    ...lines,
    ...(lines.length ? [tooltipLine("Basis", "current chart timestamp")] : []),
  ].join("");
}
