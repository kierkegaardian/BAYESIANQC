import type * as echarts from "echarts";
import type {
  LineSeriesOption,
  MarkAreaComponentOption,
  MarkLineComponentOption,
} from "echarts";
import type { StreamCatalogOut } from "../api/contracts";
import { formatChartAxisTick } from "./chartAxisOptions";

export type ControlSeriesConfig = {
  controlSeries: LineSeriesOption;
  yAxis: echarts.YAXisComponentOption;
  minValue: number;
  maxValue: number;
};

export function buildControlSeries(
  stream: StreamCatalogOut | undefined,
  showLabels = true
): ControlSeriesConfig | null {
  if (!stream) return null;
  const mean = Number(stream.target_value);
  const sigma = Number(stream.sigma);
  if (!Number.isFinite(mean) || !Number.isFinite(sigma) || sigma <= 0) return null;

  const warningSd = Number.isFinite(Number(stream.warning_limit_sd))
    ? Number(stream.warning_limit_sd)
    : 2;
  const actionSd = Number.isFinite(Number(stream.action_limit_sd))
    ? Number(stream.action_limit_sd)
    : 3;
  const minValue = mean - actionSd * sigma;
  const maxValue = mean + actionSd * sigma;

  const markAreaData: MarkAreaComponentOption["data"] = [
    [
      { yAxis: minValue, itemStyle: { color: "rgba(239, 68, 68, 0.08)" } },
      { yAxis: maxValue },
    ],
    [
      { yAxis: mean - warningSd * sigma, itemStyle: { color: "rgba(234, 179, 8, 0.1)" } },
      { yAxis: mean + warningSd * sigma },
    ],
    [
      { yAxis: mean - sigma, itemStyle: { color: "rgba(34, 197, 94, 0.12)" } },
      { yAxis: mean + sigma },
    ],
  ];
  const label = (formatter: string, color: string) => ({
    formatter,
    color,
    show: showLabels,
    position: "insideEndTop" as const,
  });
  const markLineData: MarkLineComponentOption["data"] = [
    { yAxis: mean, lineStyle: { color: "#0f172a", width: 1.5 }, label: label("Mean", "#0f172a") },
    { yAxis: mean + warningSd * sigma, lineStyle: { color: "#f59e0b", type: "dashed" }, label: label(`+${warningSd} SD`, "#f59e0b") },
    { yAxis: mean - warningSd * sigma, lineStyle: { color: "#f59e0b", type: "dashed" }, label: label(`-${warningSd} SD`, "#f59e0b") },
    { yAxis: maxValue, lineStyle: { color: "#ef4444", type: "dashed" }, label: label(`+${actionSd} SD`, "#ef4444") },
    { yAxis: minValue, lineStyle: { color: "#ef4444", type: "dashed" }, label: label(`-${actionSd} SD`, "#ef4444") },
  ];
  const controlSeries: LineSeriesOption = {
    name: "Control Limits",
    type: "line",
    data: [],
    showSymbol: false,
    lineStyle: { opacity: 0 },
    silent: true,
    markArea: { silent: true, data: markAreaData },
    markLine: { silent: true, symbol: "none", data: markLineData },
    tooltip: { show: false },
    emphasis: { disabled: true },
  };
  return {
    controlSeries,
    minValue,
    maxValue,
    yAxis: {
      type: "value",
      name: "Result",
      min: minValue,
      max: maxValue,
      axisLabel: { hideOverlap: true, formatter: formatChartAxisTick },
    },
  };
}
