import type * as echarts from "echarts";
import type { StreamCatalogOut } from "../api/contracts";
import type { PreparedChartData } from "./chartDataTransform";
import { buildResultsAxes } from "./chartResultsAxes";
import { buildResultsSeries } from "./chartResultsSeries";
import { formatResultsTooltip, tooltipDisplayOptions } from "./chartTooltips";

export function buildResultsOption(
  data: PreparedChartData,
  stream: StreamCatalogOut | undefined,
  isKiosk: boolean,
  isTileKiosk: boolean
): echarts.EChartsOption {
  const axes = buildResultsAxes(
    data.controlConfig,
    data.highOutliers,
    data.lowOutliers,
    data.logScaleActive,
    isKiosk,
    data.timeExtent,
    isTileKiosk
  );
  return {
    aria: { enabled: true, decal: { show: true } },
    grid: axes.grids,
    xAxis: axes.xAxes,
    yAxis: axes.yAxes,
    axisPointer: axes.axisPointer,
    series: buildResultsSeries(data, axes, isKiosk, isTileKiosk),
    tooltip: {
      ...tooltipDisplayOptions(isKiosk),
      trigger: isKiosk ? "item" : "axis",
      triggerOn: "mousemove|click|mousewheel",
      formatter: (params: unknown) => formatResultsTooltip(params, stream),
    },
  };
}
