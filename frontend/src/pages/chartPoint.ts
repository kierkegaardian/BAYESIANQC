import type {
  BayesianRisk,
  Disposition,
  FrequentistSignal,
  QCRecordChartOutEvaluated,
} from "../api/contracts";

export type ChartPoint = {
  value: [string, number | null];
  lot?: string | null;
  record_id: number;
  include_in_stats?: boolean | null;
  resolved_reason?: string | null;
  resolved_at?: string | null;
  disposition?: Disposition | null;
  signals?: FrequentistSignal[] | null;
  bayesian_risk?: BayesianRisk | null;
  itemStyle?: { color?: string };
};

export type OutlierPoint = Omit<ChartPoint, "value"> & {
  value: [string, number];
  symbolRotate: number;
  itemStyle: { color: string };
  label: {
    show: boolean;
    formatter: string;
    position: "top" | "bottom";
    color: string;
    fontWeight: number;
  };
};

export type TooltipItem = { data?: unknown; value?: unknown; seriesName?: unknown };

export function recordToChartPoint(record: QCRecordChartOutEvaluated): ChartPoint {
  return {
    value: [record.timestamp, record.result_value],
    lot: record.control_material_lot,
    record_id: record.id,
    include_in_stats: record.include_in_stats,
    resolved_reason: record.resolved_reason,
    resolved_at: record.resolved_at,
    disposition: record.disposition ?? null,
    signals: record.signals ?? null,
    bayesian_risk: record.bayesian_risk ?? null,
  };
}

export function isChartPoint(value: unknown): value is ChartPoint {
  if (!value || typeof value !== "object") return false;
  const point = value as { record_id?: unknown; value?: unknown };
  return typeof point.record_id === "number" && Array.isArray(point.value) &&
    point.value.length === 2 && typeof point.value[0] === "string";
}

export function asFormatterItems(params: unknown): TooltipItem[] {
  if (Array.isArray(params)) {
    return params.filter((item): item is TooltipItem => !!item && typeof item === "object");
  }
  return params && typeof params === "object" ? [params as TooltipItem] : [];
}

export function hasNumericChartValue(item: TooltipItem): boolean {
  const value = isChartPoint(item.data) ? item.data.value[1] : null;
  return typeof value === "number" && Number.isFinite(value);
}

export function escapeTooltipValue(value: string | number): string {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function tooltipLine(label: string, value: string | number): string {
  return `<div><strong>${escapeTooltipValue(label)}:</strong> ${escapeTooltipValue(value)}</div>`;
}

export function formatPointTime(value: string): string {
  return new Date(value).toLocaleString();
}
