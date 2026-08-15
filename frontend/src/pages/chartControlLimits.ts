export type AppliedLimits = {
  centerline: number;
  sigma: number;
  warning_lower: number;
  warning_upper: number;
  action_lower: number;
  action_upper: number;
  source: "configured" | "fixed_baseline";
  baseline_start?: string | null;
  baseline_end?: string | null;
  baseline_count?: number | null;
};

export type ProvenanceRecord = {
  id: number;
  timestamp: string;
  evaluation?: {
    threshold_mode: string;
    limits: AppliedLimits;
  } | null;
};

export type ControlLimitSteps = {
  centerline: Array<[string, number | null]>;
  sigmaLower: Array<[string, number | null]>;
  sigmaUpper: Array<[string, number | null]>;
  warningLower: Array<[string, number | null]>;
  warningUpper: Array<[string, number | null]>;
  actionLower: Array<[string, number | null]>;
  actionUpper: Array<[string, number | null]>;
  minValue?: number;
  maxValue?: number;
  legacyRecordIds: number[];
  fixedBaselineLabels: string[];
  segments: Array<{ start: string; end: string; limits: AppliedLimits }>;
};

function finite(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function point(timestamp: string, value: unknown): [string, number | null] {
  return [timestamp, finite(value)];
}

function baselineLabel(limits: AppliedLimits): string | null {
  if (
    limits.source !== "fixed_baseline" ||
    !limits.baseline_start ||
    !limits.baseline_end ||
    !limits.baseline_count
  ) {
    return null;
  }
  const start = new Date(limits.baseline_start).toLocaleDateString();
  const end = new Date(limits.baseline_end).toLocaleDateString();
  return `${start}–${end}, n=${limits.baseline_count}`;
}

export function buildControlLimitSteps(records: ProvenanceRecord[]): ControlLimitSteps {
  const steps: ControlLimitSteps = {
    centerline: [],
    sigmaLower: [],
    sigmaUpper: [],
    warningLower: [],
    warningUpper: [],
    actionLower: [],
    actionUpper: [],
    legacyRecordIds: [],
    fixedBaselineLabels: [],
    segments: [],
  };
  const actionLows: number[] = [];
  const actionHighs: number[] = [];
  const labels = new Set<string>();

  for (const [index, record] of records.entries()) {
    const limits = record.evaluation?.limits;
    if (!limits) {
      steps.legacyRecordIds.push(record.id);
      for (const series of [
        steps.centerline,
        steps.sigmaLower,
        steps.sigmaUpper,
        steps.warningLower,
        steps.warningUpper,
        steps.actionLower,
        steps.actionUpper,
      ]) {
        series.push([record.timestamp, null]);
      }
      continue;
    }
    const nextTimestamp = records[index + 1]?.timestamp;
    const end = nextTimestamp ?? new Date(new Date(record.timestamp).getTime() + 1000).toISOString();
    steps.segments.push({ start: record.timestamp, end, limits });
    steps.centerline.push(point(record.timestamp, limits.centerline));
    steps.sigmaLower.push(point(record.timestamp, limits.centerline - limits.sigma));
    steps.sigmaUpper.push(point(record.timestamp, limits.centerline + limits.sigma));
    steps.warningLower.push(point(record.timestamp, limits.warning_lower));
    steps.warningUpper.push(point(record.timestamp, limits.warning_upper));
    steps.actionLower.push(point(record.timestamp, limits.action_lower));
    steps.actionUpper.push(point(record.timestamp, limits.action_upper));
    const low = finite(limits.action_lower);
    const high = finite(limits.action_upper);
    if (low !== null) actionLows.push(low);
    if (high !== null) actionHighs.push(high);
    const label = baselineLabel(limits);
    if (label) labels.add(label);
  }
  if (actionLows.length) steps.minValue = Math.min(...actionLows);
  if (actionHighs.length) steps.maxValue = Math.max(...actionHighs);
  steps.fixedBaselineLabels = [...labels];
  return steps;
}
