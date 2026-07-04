import type {
  BayesianRisk,
  Disposition,
  QCRecordChartOutEvaluated,
  StreamConfigOut,
} from "../api/contracts";

export type ChartRiskTone = "none" | "low" | "monitor" | "hold" | "action";

export type ChartRiskSummary = {
  timestamp: string;
  risk: BayesianRisk;
  disposition: Disposition | null;
  actionProbability: number;
  warningProbability: number;
  riskScore: number;
  riskLabel: string;
  stateLabel: string;
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

export function probabilityToPercent(value: number | null | undefined): number {
  return clampPercent(Number(value ?? 0) * 100);
}

export function formatRiskPercent(value: number): string {
  const clamped = clampPercent(value);
  return `${clamped >= 10 ? clamped.toFixed(0) : clamped.toFixed(1)}%`;
}

export function riskThresholds(stream: StreamConfigOut | undefined): RiskThresholds {
  if (!stream) {
    return { warnLine: 50, holdLine: 80, warnUsesWarningProbability: false };
  }
  const warnLine =
    stream.bayes_warn_prob_threshold !== null && stream.bayes_warn_prob_threshold !== undefined
      ? probabilityToPercent(stream.bayes_warn_prob_threshold)
      : clampPercent(Number(stream.risk_threshold_warn));
  const holdLine =
    stream.bayes_hold_prob_threshold !== null && stream.bayes_hold_prob_threshold !== undefined
      ? probabilityToPercent(stream.bayes_hold_prob_threshold)
      : clampPercent(Number(stream.risk_threshold_hold));
  return {
    warnLine,
    holdLine,
    warnUsesWarningProbability:
      stream.bayes_warn_prob_threshold !== null && stream.bayes_warn_prob_threshold !== undefined,
  };
}

function latestEvaluatedRecord(
  records: QCRecordChartOutEvaluated[]
): QCRecordChartOutEvaluated | null {
  for (let index = records.length - 1; index >= 0; index -= 1) {
    const record = records[index];
    if (record.include_in_stats !== false && record.bayesian_risk) {
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
  disposition: Disposition | null,
  actionProbability: number,
  warningProbability: number,
  thresholds: RiskThresholds
): ChartRiskTone {
  if (disposition === "reject") {
    return "action";
  }
  if (disposition === "hold-for-review" || actionProbability >= thresholds.holdLine) {
    return "hold";
  }
  const warnBasis = thresholds.warnUsesWarningProbability ? warningProbability : actionProbability;
  if (disposition === "monitor" || warnBasis >= thresholds.warnLine) {
    return "monitor";
  }
  return "low";
}

function stateLabel(
  tone: ChartRiskTone,
  disposition: Disposition | null,
  lowConfidence: boolean
): string {
  if (disposition === "reject") {
    return "Reject";
  }
  if (disposition === "hold-for-review") {
    return "Hold review";
  }
  if (lowConfidence) {
    return "Low confidence";
  }
  if (disposition === "monitor") {
    return "Monitor";
  }
  if (tone === "action") {
    return "Action";
  }
  if (tone === "hold") {
    return "Hold review";
  }
  if (tone === "monitor") {
    return "Monitor";
  }
  return "Accept";
}

function toneRank(tone: ChartRiskTone): number {
  return { none: 0, low: 1, monitor: 2, hold: 3, action: 4 }[tone];
}

function isLowConfidence(
  record: QCRecordChartOutEvaluated,
  stream: StreamConfigOut | undefined,
  warningProbability: number,
  actionProbability: number,
  thresholds: RiskThresholds
): boolean {
  if (signalRank(record) > 0 || actionProbability >= thresholds.holdLine) {
    return false;
  }
  const predictiveSigma = Number(record.bayesian_risk?.predictive_sigma);
  const configuredSigma = Number(stream?.sigma);
  const widePredictiveInterval =
    Number.isFinite(predictiveSigma) &&
    Number.isFinite(configuredSigma) &&
    configuredSigma > 0 &&
    predictiveSigma / configuredSigma >= 1.35;
  return warningProbability >= thresholds.warnLine || widePredictiveInterval;
}

function chooseSummaryRecord(
  records: QCRecordChartOutEvaluated[],
  stream: StreamConfigOut | undefined,
  thresholds: RiskThresholds
): QCRecordChartOutEvaluated | null {
  let best: QCRecordChartOutEvaluated | null = null;
  let bestRank: [number, number, number, number, number] | null = null;
  for (const record of records) {
    if (record.include_in_stats === false || !record.bayesian_risk) {
      continue;
    }
    const actionProbability = probabilityToPercent(record.bayesian_risk.probability_outside_limits);
    const warningProbability = probabilityToPercent(record.bayesian_risk.probability_outside_warning);
    const disposition = record.disposition ?? null;
    const tone = riskTone(disposition, actionProbability, warningProbability, thresholds);
    const lowConfidence = isLowConfidence(record, stream, warningProbability, actionProbability, thresholds);
    const rank: [number, number, number, number, number] = [
      signalRank(record),
      toneRank(tone) + (lowConfidence ? 0.5 : 0),
      actionProbability,
      warningProbability,
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
  stream: StreamConfigOut | undefined
): ChartRiskSummary | null {
  const thresholds = riskThresholds(stream);
  const record = chooseSummaryRecord(records, stream, thresholds);
  if (!record?.bayesian_risk) {
    return null;
  }
  const actionProbability = probabilityToPercent(record.bayesian_risk.probability_outside_limits);
  const warningProbability = probabilityToPercent(record.bayesian_risk.probability_outside_warning);
  const disposition = record.disposition ?? null;
  const tone = riskTone(disposition, actionProbability, warningProbability, thresholds);
  const lowConfidence = isLowConfidence(record, stream, warningProbability, actionProbability, thresholds);
  const latest = latestEvaluatedRecord(records);
  const isPeak = latest !== null && latest.timestamp !== record.timestamp;
  const riskLabelPrefix = lowConfidence && actionProbability < 10 ? "Warn" : isPeak ? "Peak" : "Risk";
  const riskLabelValue = lowConfidence && actionProbability < 10 ? warningProbability : actionProbability;
  const detailPrefix = lowConfidence ? "Low confidence" : isPeak ? "Peak window" : "Latest";
  return {
    timestamp: record.timestamp,
    risk: record.bayesian_risk,
    disposition,
    actionProbability,
    warningProbability,
    riskScore: clampPercent(Number(record.bayesian_risk.risk_score)),
    riskLabel: `${riskLabelPrefix} ${formatRiskPercent(riskLabelValue)}`,
    stateLabel: stateLabel(tone, disposition, lowConfidence),
    detailLabel: `${detailPrefix}: Warn ${formatRiskPercent(warningProbability)} / Action ${formatRiskPercent(
      actionProbability
    )}`,
    tone,
  };
}
