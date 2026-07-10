import type {
  BayesianRisk,
  Disposition,
  QCRecordChartOutEvaluated,
  StreamCatalogOut,
} from "../api/contracts";
import {
  availableRiskNumber,
  riskIsUnavailable,
  unavailableRiskMessage,
  unavailableRiskReason,
} from "./bayesianRiskAvailability";

export type ChartRiskTone = "none" | "low" | "monitor" | "hold" | "action";

export type ChartRiskSummary = {
  status: "available" | "unavailable";
  timestamp: string;
  risk: BayesianRisk;
  disposition: Disposition | null;
  actionProbability: number | null;
  warningProbability: number | null;
  riskScore: number | null;
  riskLabel: string;
  riskContextLabel: string;
  stateLabel: string;
  reasonLabel: string;
  detailLabel: string;
  tone: ChartRiskTone;
};

export const BAYESIAN_RISK_MEANING =
  "Bayesian risk estimates the chance that the next included QC result will fall outside configured warning/action limits.";

export const BAYESIAN_RISK_SCORE_MEANING =
  "Risk score is P(outside action limits) scaled 0-100.";

export function bayesianRiskBasisText(basis: string): string {
  return `Basis: configured stream prior plus included historical QC results for this stream ${basis}; resolved/excluded results do not update the posterior.`;
}

export function bayesianRiskHelpText(basis: string): string {
  return `${BAYESIAN_RISK_MEANING} ${bayesianRiskBasisText(basis)} ${BAYESIAN_RISK_SCORE_MEANING}`;
}

type RiskThresholds = {
  warnLine: number;
  holdLine: number;
  warnUsesWarningProbability: boolean;
};

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

export function probabilityToPercent(value: number | null | undefined): number | null {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null;
  return clampPercent(Number(value) * 100);
}

export function formatRiskPercent(value: number): string {
  const clamped = clampPercent(value);
  return `${clamped >= 10 ? clamped.toFixed(0) : clamped.toFixed(1)}%`;
}

export function riskThresholds(stream: StreamCatalogOut | undefined): RiskThresholds {
  if (!stream) {
    return { warnLine: 50, holdLine: 80, warnUsesWarningProbability: false };
  }
  const configuredWarnLine =
    stream.bayes_warn_prob_threshold !== null && stream.bayes_warn_prob_threshold !== undefined
      ? probabilityToPercent(stream.bayes_warn_prob_threshold)
      : null;
  const configuredHoldLine =
    stream.bayes_hold_prob_threshold !== null && stream.bayes_hold_prob_threshold !== undefined
      ? probabilityToPercent(stream.bayes_hold_prob_threshold)
      : null;
  return {
    warnLine: configuredWarnLine ?? clampPercent(Number(stream.risk_threshold_warn)),
    holdLine: configuredHoldLine ?? clampPercent(Number(stream.risk_threshold_hold)),
    warnUsesWarningProbability:
      stream.bayes_warn_prob_threshold !== null && stream.bayes_warn_prob_threshold !== undefined,
  };
}

function latestEvaluatedRecord(
  records: QCRecordChartOutEvaluated[]
): QCRecordChartOutEvaluated | null {
  for (let index = records.length - 1; index >= 0; index -= 1) {
    const record = records[index];
    if (record.include_in_stats !== false && record.bayesian_risk && !riskIsUnavailable(record.bayesian_risk)) {
      return record;
    }
  }
  return null;
}

function signalRank(record: QCRecordChartOutEvaluated): number {
  const signals = record.signals ?? [];
  if (signals.some((signal) => signal.severity === "action")) {
    return 5;
  }
  return signals.length ? 3 : 0;
}

function riskTone(
  actionProbability: number,
  warningProbability: number,
  thresholds: RiskThresholds
): ChartRiskTone {
  if (actionProbability >= thresholds.holdLine) {
    return "hold";
  }
  const warnBasis = thresholds.warnUsesWarningProbability ? warningProbability : actionProbability;
  if (warnBasis >= thresholds.warnLine) {
    return "monitor";
  }
  return "low";
}

function stateLabel(
  disposition: Disposition | null,
): string {
  if (disposition === "reject") {
    return "Reject";
  }
  if (disposition === "hold-for-review") {
    return "Hold review";
  }
  if (disposition === "monitor") {
    return "Monitor";
  }
  return disposition === "accept" ? "Accept" : "Not evaluated";
}

function toneRank(tone: ChartRiskTone): number {
  return { none: 0, low: 1, monitor: 2, hold: 3, action: 4 }[tone];
}

function isLowConfidence(
  record: QCRecordChartOutEvaluated,
  stream: StreamCatalogOut | undefined,
  warningProbability: number,
  actionProbability: number,
  thresholds: RiskThresholds
): boolean {
  if (signalRank(record) > 0 || actionProbability >= thresholds.holdLine) {
    return false;
  }
  const predictiveSigma = availableRiskNumber(record.bayesian_risk, "predictive_sigma");
  const configuredSigma = Number(stream?.sigma);
  const widePredictiveInterval =
    predictiveSigma !== null &&
    Number.isFinite(configuredSigma) &&
    configuredSigma > 0 &&
    predictiveSigma / configuredSigma >= 1.35;
  return warningProbability >= thresholds.warnLine || widePredictiveInterval;
}

function chooseSummaryRecord(
  records: QCRecordChartOutEvaluated[],
  stream: StreamCatalogOut | undefined,
  thresholds: RiskThresholds
): QCRecordChartOutEvaluated | null {
  let best: QCRecordChartOutEvaluated | null = null;
  let bestRank: [number, number, number, number, number] | null = null;
  for (const record of records) {
    if (record.include_in_stats === false || !record.bayesian_risk || riskIsUnavailable(record.bayesian_risk)) {
      continue;
    }
    const actionProbability = probabilityToPercent(availableRiskNumber(record.bayesian_risk, "probability_outside_limits"));
    const warningProbability = probabilityToPercent(availableRiskNumber(record.bayesian_risk, "probability_outside_warning"));
    if (actionProbability === null || warningProbability === null) continue;
    const tone = riskTone(actionProbability, warningProbability, thresholds);
    const lowConfidence = isLowConfidence(record, stream, warningProbability, actionProbability, thresholds);
    const rank: [number, number, number, number, number] = [
      toneRank(tone) + (lowConfidence ? 0.5 : 0),
      actionProbability,
      warningProbability,
      signalRank(record),
      Date.parse(record.timestamp) || 0,
    ];
    if (!bestRank || rank.some((value, index) => value > bestRank![index] && rank.slice(0, index).every((left, prior) => left === bestRank![prior]))) {
      best = record;
      bestRank = rank;
    }
  }
  return best;
}

export function summarizeChartRisk(
  records: QCRecordChartOutEvaluated[],
  stream: StreamCatalogOut | undefined
): ChartRiskSummary | null {
  const thresholds = riskThresholds(stream);
  const record = chooseSummaryRecord(records, stream, thresholds);
  if (!record?.bayesian_risk) {
    const unavailable = [...records].reverse().find(
      (item) => item.include_in_stats !== false && riskIsUnavailable(item.bayesian_risk)
    );
    if (!unavailable?.bayesian_risk) return null;
    return {
      status: "unavailable",
      timestamp: unavailable.timestamp,
      risk: unavailable.bayesian_risk,
      disposition: unavailable.disposition ?? null,
      actionProbability: null,
      warningProbability: null,
      riskScore: null,
      riskLabel: "Unavailable",
      riskContextLabel: "Bayesian inference unavailable",
      stateLabel: stateLabel(unavailable.disposition ?? null),
      reasonLabel: unavailableRiskReason(unavailable.bayesian_risk),
      detailLabel: unavailableRiskMessage(unavailable.bayesian_risk),
      tone: "none",
    };
  }
  const actionProbability = probabilityToPercent(availableRiskNumber(record.bayesian_risk, "probability_outside_limits"));
  const warningProbability = probabilityToPercent(availableRiskNumber(record.bayesian_risk, "probability_outside_warning"));
  if (actionProbability === null || warningProbability === null) return null;
  const disposition = record.disposition ?? null;
  const tone = riskTone(actionProbability, warningProbability, thresholds);
  const lowConfidence = isLowConfidence(record, stream, warningProbability, actionProbability, thresholds);
  const latest = latestEvaluatedRecord(records);
  const isPeak = latest !== null && latest.timestamp !== record.timestamp;
  const detailPrefix = lowConfidence ? "Low confidence" : isPeak ? "Highest in selected window" : "Latest";
  const signalRules = (record.signals ?? []).map((signal) => signal.rule);
  const reasonLabel = signalRules.length
    ? `Frequentist signal: ${signalRules.join(", ")}`
    : lowConfidence
      ? "Bayesian estimate has elevated uncertainty"
      : "No frequentist rule signal at this point";
  return {
    status: "available",
    timestamp: record.timestamp,
    risk: record.bayesian_risk,
    disposition,
    actionProbability,
    warningProbability,
    riskScore: (() => {
      const value = availableRiskNumber(record.bayesian_risk, "risk_score");
      return value === null ? null : clampPercent(value);
    })(),
    riskLabel: formatRiskPercent(actionProbability),
    riskContextLabel: isPeak ? "Highest in selected window" : "Latest evaluated point",
    stateLabel: stateLabel(disposition),
    reasonLabel,
    detailLabel: `${detailPrefix}: Warn ${formatRiskPercent(warningProbability)} / Action ${formatRiskPercent(
      actionProbability
    )}`,
    tone,
  };
}
