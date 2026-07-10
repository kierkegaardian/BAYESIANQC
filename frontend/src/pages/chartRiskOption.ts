import type * as echarts from "echarts";
import type { LineSeriesOption, ScatterSeriesOption } from "echarts";
import type { StreamCatalogOut } from "../api/contracts";
import type { MarkLineData, PreparedChartData } from "./chartDataTransform";
import { riskThresholds } from "./chartRisk";
import { formatRiskTooltip, tooltipDisplayOptions } from "./chartTooltips";

function probabilitySeries(
  name: string,
  points: PreparedChartData["actionProbabilityPoints"],
  color: string,
  data: PreparedChartData
): LineSeriesOption {
  const series: LineSeriesOption = {
    name,
    type: "line",
    data: points,
    showSymbol: false,
    connectNulls: false,
    lineStyle: { color },
  };
  if (data.segmentAreas.length) {
    series.markArea = {
      silent: true,
      itemStyle: { color: "rgba(148, 163, 184, 0.18)" },
      label: { show: data.showTimelineMarkerLabels, color: "#475569", fontSize: 11 },
      data: data.segmentAreas,
    };
  }
  return series;
}

export function buildRiskOption(
  data: PreparedChartData,
  stream: StreamCatalogOut | undefined,
  chartMode: "results" | "risk" | "both",
  isKiosk: boolean,
  isTileKiosk = false
): echarts.EChartsOption {
  const thresholds = riskThresholds(stream);
  const thresholdLines: MarkLineData = [
    {
      yAxis: thresholds.warnLine,
      lineStyle: { color: "#f59e0b", type: "dashed" },
      label: { show: !isTileKiosk, formatter: `Warn ${thresholds.warnLine.toFixed(0)}%`, color: "#f59e0b", position: "insideEndTop" },
    },
    {
      yAxis: thresholds.holdLine,
      lineStyle: { color: "#ef4444", type: "dashed" },
      label: { show: !isTileKiosk, formatter: `Hold ${thresholds.holdLine.toFixed(0)}%`, color: "#ef4444", position: "insideEndTop" },
    },
  ];
  const action = probabilitySeries("P(outside action)", data.actionProbabilityPoints, "#dc2626", data);
  const riskLines = [...thresholdLines, ...data.eventLines];
  if (riskLines.length) action.markLine = { silent: true, symbol: "none", data: riskLines };
  const warning = probabilitySeries("P(outside warn)", data.warningProbabilityPoints, "#f59e0b", data);
  const alerts: ScatterSeriesOption = {
    name: "Alerts",
    type: "scatter",
    data: data.alertPoints,
    symbolSize: 9,
    itemStyle: { color: "#7f1d1d" },
  };
  return {
    aria: { enabled: true, decal: { show: true } },
    grid: {
      left: isKiosk ? "5%" : "6%",
      right: isKiosk ? "6%" : "8%",
      top: chartMode === "risk" ? "8%" : "4%",
      bottom: chartMode === "risk" ? "18%" : "24%",
      containLabel: true,
    },
    xAxis: {
      type: "time",
      min: data.timeExtent?.min,
      max: data.timeExtent?.max,
      axisLabel: { show: chartMode === "risk" || !isKiosk },
    },
    yAxis: {
      type: "value",
      name: chartMode === "risk" ? "Predictive exceedance (%)" : "Risk (%)",
      min: 0,
      max: 100,
      splitNumber: chartMode === "risk" ? 5 : 3,
      axisLabel: { formatter: "{value}%" },
    },
    series: [warning, action, alerts],
    tooltip: {
      ...tooltipDisplayOptions(isKiosk),
      trigger: "axis",
      triggerOn: "mousemove|click|mousewheel",
      formatter: formatRiskTooltip,
    },
  };
}
