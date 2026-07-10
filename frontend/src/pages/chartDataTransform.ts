import type {
  MarkAreaComponentOption,
  MarkLineComponentOption,
} from "echarts";
import type {
  AlertOutWithQc,
  QCRecordChartOutEvaluated,
  StreamChartOutEvaluated,
  StreamCatalogOut,
} from "../api/contracts";
import { buildControlSeries, type ControlSeriesConfig } from "./chartControlSeries";
import type { ChartPoint, OutlierPoint } from "./chartPoint";
import { summarizeChartRisk, type ChartRiskSummary } from "./chartRisk";
import { availableRiskNumber, riskIsUnavailable } from "./bayesianRiskAvailability";
import { deriveLotSegments, formatEventLabel, padSegmentEnd } from "./chartViewSupport";

export type TimeValue = [string, number | null];
export type MarkLineData = NonNullable<MarkLineComponentOption["data"]>;

export type PreparedChartData = {
  records: QCRecordChartOutEvaluated[];
  riskSummary: ChartRiskSummary | null;
  controlConfig: ControlSeriesConfig | null;
  logScaleAllowed: boolean;
  logScaleActive: boolean;
  resultPoints: ChartPoint[];
  posteriorMeanPoints: TimeValue[];
  predictiveLowerPoints: TimeValue[];
  predictiveUpperPoints: TimeValue[];
  credibleLowerPoints: TimeValue[];
  credibleUpperPoints: TimeValue[];
  warningProbabilityPoints: TimeValue[];
  actionProbabilityPoints: TimeValue[];
  alertPoints: Array<[string, number | null]>;
  segmentAreas: NonNullable<MarkAreaComponentOption["data"]>;
  eventLines: MarkLineData;
  alertLines: MarkLineData;
  lotBoundaryLines: MarkLineData;
  highOutliers: OutlierPoint[];
  lowOutliers: OutlierPoint[];
  showTimelineMarkerLabels: boolean;
  timeExtent: { min: string; max: string } | null;
};

function percent(value: number | null | undefined): number | null {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null;
  return Math.max(0, Math.min(100, Number(value) * 100));
}

function riskValue(
  record: QCRecordChartOutEvaluated,
  key: "posterior_mean" | "probability_outside_warning" | "probability_outside_limits"
): number | null {
  return availableRiskNumber(record.bayesian_risk, key);
}

function intervalValue(
  record: QCRecordChartOutEvaluated,
  key: "predictive_interval" | "credible_interval",
  index: 0 | 1
): number | null {
  const interval = record.bayesian_risk?.[key];
  if (!interval || riskIsUnavailable(record.bayesian_risk)) return null;
  const value = Number(interval[index]);
  return Number.isFinite(value) ? value : null;
}

function basePoint(record: QCRecordChartOutEvaluated, value: number | null): ChartPoint {
  return {
    value: [record.timestamp, value],
    lot: record.control_material_lot,
    record_id: record.id,
    include_in_stats: record.include_in_stats,
    resolved_reason: record.resolved_reason,
    resolved_at: record.resolved_at,
    disposition: record.disposition ?? null,
    signals: record.signals ?? null,
    bayesian_risk: record.bayesian_risk ?? null,
    itemStyle: record.include_in_stats === false ? { color: "#94a3b8" } : undefined,
  };
}

function outlierPoint(record: QCRecordChartOutEvaluated, high: boolean, showLabel: boolean): OutlierPoint {
  const resolved = record.include_in_stats === false;
  return {
    ...basePoint(record, record.result_value),
    value: [record.timestamp, record.result_value],
    symbolRotate: high ? 0 : 180,
    itemStyle: { color: resolved ? "#94a3b8" : "#ef4444" },
    label: {
      show: showLabel,
      formatter: `${record.result_value}`,
      position: high ? "top" : "bottom",
      color: resolved ? "#64748b" : "#991b1b",
      fontWeight: 600,
    },
  };
}

export function prepareChartData(
  data: StreamChartOutEvaluated,
  stream: StreamCatalogOut | undefined,
  requestedLogScale: boolean,
  isKiosk: boolean,
  isTileKiosk = false
): PreparedChartData {
  const records = data.records;
  const validTimes = records
    .map((record) => record.timestamp)
    .filter((timestamp) => Number.isFinite(Date.parse(timestamp)))
    .sort((left, right) => Date.parse(left) - Date.parse(right));
  const alerts = data.alerts as AlertOutWithQc[];
  const segments = data.lot_segments.length ? data.lot_segments : deriveLotSegments(records);
  const showTimelineMarkerLabels = !isKiosk && segments.length + data.events.length + alerts.length <= 6;
  const controlConfig = buildControlSeries(stream, !isTileKiosk);
  const min = controlConfig?.minValue;
  const max = controlConfig?.maxValue;
  const logScaleAllowed = records.every((record) => record.result_value > 0) && (min === undefined || min > 0);
  const logScaleActive = requestedLogScale && logScaleAllowed;
  const allowBreaks = !logScaleActive && min !== undefined && max !== undefined &&
    records.some((record) => record.result_value < min || record.result_value > max);
  const resultPoints = records.map((record) => basePoint(
    record,
    allowBreaks && min !== undefined && max !== undefined &&
      (record.result_value < min || record.result_value > max) ? null : record.result_value
  ));
  const highOutliers: OutlierPoint[] = [];
  const lowOutliers: OutlierPoint[] = [];
  if (allowBreaks && min !== undefined && max !== undefined) {
    for (const record of records) {
      if (record.result_value > max) highOutliers.push(outlierPoint(record, true, !isTileKiosk));
      if (record.result_value < min) lowOutliers.push(outlierPoint(record, false, !isTileKiosk));
    }
  }
  const segmentAreas: NonNullable<MarkAreaComponentOption["data"]> = segments.map((segment) => [
    { xAxis: segment.start, label: { show: showTimelineMarkerLabels, formatter: `Lot ${segment.control_material_lot}` } },
    { xAxis: padSegmentEnd(segment.start, segment.end) },
  ] as const);
  const eventLines: MarkLineData = data.events.map((event) => ({
    xAxis: event.timestamp,
    label: { show: showTimelineMarkerLabels, formatter: formatEventLabel(event), color: "#0369a1", fontSize: 11 },
    lineStyle: { color: "#0ea5e9", type: "dotted" as const, width: 1.5 },
  }));
  const alertLines: MarkLineData = alerts.map((alert) => ({
    xAxis: alert.qc_record_timestamp ?? alert.created_at,
    label: { show: showTimelineMarkerLabels, formatter: "Alert", color: "#991b1b", fontSize: 11 },
    lineStyle: { color: "#dc2626", type: "solid" as const, width: 1.25 },
  }));
  const lotBoundaryLines: MarkLineData = segments.slice(1).map((segment) => ({
    xAxis: segment.start,
    lineStyle: { color: "#94a3b8", type: "dashed" as const },
    label: { show: showTimelineMarkerLabels, formatter: `Lot ${segment.control_material_lot}`, color: "#475569", fontSize: 11 },
  }));
  return {
    records,
    riskSummary: summarizeChartRisk(records, stream),
    controlConfig,
    logScaleAllowed,
    logScaleActive,
    resultPoints,
    posteriorMeanPoints: records.map((record) => [record.timestamp, riskValue(record, "posterior_mean")]),
    predictiveLowerPoints: records.map((record) => [record.timestamp, intervalValue(record, "predictive_interval", 0)]),
    predictiveUpperPoints: records.map((record) => [record.timestamp, intervalValue(record, "predictive_interval", 1)]),
    credibleLowerPoints: records.map((record) => [record.timestamp, intervalValue(record, "credible_interval", 0)]),
    credibleUpperPoints: records.map((record) => [record.timestamp, intervalValue(record, "credible_interval", 1)]),
    warningProbabilityPoints: records.map((record) => [record.timestamp, percent(availableRiskNumber(record.bayesian_risk, "probability_outside_warning"))]),
    actionProbabilityPoints: records.map((record) => [record.timestamp, percent(availableRiskNumber(record.bayesian_risk, "probability_outside_limits"))]),
    alertPoints: alerts.map((alert) => [
      alert.qc_record_timestamp ?? alert.created_at,
      percent(availableRiskNumber(alert.bayesian_risk, "probability_outside_limits")),
    ]),
    segmentAreas,
    eventLines,
    alertLines,
    lotBoundaryLines,
    highOutliers,
    lowOutliers,
    showTimelineMarkerLabels,
    timeExtent: validTimes.length ? { min: validTimes[0], max: validTimes[validTimes.length - 1] } : null,
  };
}
