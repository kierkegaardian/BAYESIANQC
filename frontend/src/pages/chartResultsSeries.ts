import type * as echarts from "echarts";
import type { LineSeriesOption, ScatterSeriesOption } from "echarts";
import type { PreparedChartData, TimeValue } from "./chartDataTransform";
import type { ResultsAxes } from "./chartResultsAxes";

function referenceLine(
  name: string,
  data: TimeValue[],
  color: string,
  type: "solid" | "dashed" | "dotted" = "solid",
  width = 1.5
): LineSeriesOption {
  return {
    name,
    type: "line",
    data,
    showSymbol: false,
    connectNulls: false,
    silent: true,
    lineStyle: { color, type, width },
    tooltip: { show: false },
    emphasis: { disabled: true },
  };
}

function assignMainAxis(series: LineSeriesOption[], index: number): void {
  for (const item of series) {
    item.xAxisIndex = index;
    item.yAxisIndex = index;
  }
}

export function buildResultsSeries(
  data: PreparedChartData,
  axes: ResultsAxes,
  isKiosk: boolean,
  isTileKiosk: boolean
): echarts.SeriesOption[] {
  const result: LineSeriesOption = {
    name: "Result",
    type: "line",
    data: data.resultPoints,
    smooth: false,
    connectNulls: false,
    showSymbol: isKiosk,
    symbolSize: isKiosk ? (isTileKiosk ? 5 : 7) : 6,
    lineStyle: { color: "#2563eb" },
  };
  if (data.segmentAreas.length) {
    result.markArea = {
      silent: true,
      itemStyle: { color: "rgba(148, 163, 184, 0.18)" },
      label: { show: data.showTimelineMarkerLabels, color: "#475569", fontSize: 11 },
      data: data.segmentAreas,
    };
  }
  const markerLines = [...data.lotBoundaryLines, ...data.eventLines, ...data.alertLines];
  if (markerLines.length) result.markLine = { silent: true, symbol: "none", data: markerLines };

  const referenceSeries = [
    referenceLine("Predictive interval (low)", data.predictiveLowerPoints, "rgba(20, 184, 166, 0.75)", "dashed"),
    referenceLine("Predictive interval (high)", data.predictiveUpperPoints, "rgba(20, 184, 166, 0.75)", "dashed"),
    referenceLine("Mean credible interval (low)", data.credibleLowerPoints, "rgba(71, 85, 105, 0.6)", "dotted", 1.25),
    referenceLine("Mean credible interval (high)", data.credibleUpperPoints, "rgba(71, 85, 105, 0.6)", "dotted", 1.25),
    referenceLine("Posterior mean", data.posteriorMeanPoints, "#16a34a", "solid", 2),
    result,
  ];
  assignMainAxis(referenceSeries, axes.mainAxisIndex);
  const series: echarts.SeriesOption[] = [];
  if (data.controlConfig) {
    data.controlConfig.controlSeries.xAxisIndex = axes.mainAxisIndex;
    data.controlConfig.controlSeries.yAxisIndex = axes.mainAxisIndex;
    series.push(data.controlConfig.controlSeries);
  }
  series.push(...referenceSeries);
  if (data.highOutliers.length && axes.highAxisIndex !== null) {
    const outliers: ScatterSeriesOption = {
      name: "High outliers",
      type: "scatter",
      data: data.highOutliers,
      symbol: "triangle",
      symbolSize: 12,
      xAxisIndex: axes.highAxisIndex,
      yAxisIndex: axes.highAxisIndex,
    };
    series.push(outliers);
  }
  if (data.lowOutliers.length && axes.lowAxisIndex !== null) {
    const outliers: ScatterSeriesOption = {
      name: "Low outliers",
      type: "scatter",
      data: data.lowOutliers,
      symbol: "triangle",
      symbolSize: 12,
      xAxisIndex: axes.lowAxisIndex,
      yAxisIndex: axes.lowAxisIndex,
    };
    series.push(outliers);
  }
  return series;
}
