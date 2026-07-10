import type * as echarts from "echarts";
import type { ControlSeriesConfig } from "./chartControlSeries";
import type { OutlierPoint } from "./chartPoint";
import {
  buildBrokenMainYAxis,
  buildBrokenOutlierYAxis,
  buildOutlierAxis,
  formatChartAxisTick,
} from "./chartAxisOptions";

export type ResultsAxes = {
  grids: echarts.GridComponentOption[];
  xAxes: echarts.XAXisComponentOption[];
  yAxes: echarts.YAXisComponentOption[];
  mainAxisIndex: number;
  highAxisIndex: number | null;
  lowAxisIndex: number | null;
  axisPointer: echarts.EChartsOption["axisPointer"];
};

export function buildResultsAxes(
  control: ControlSeriesConfig | null,
  highOutliers: OutlierPoint[],
  lowOutliers: OutlierPoint[],
  logScaleActive: boolean,
  isKiosk: boolean,
  timeExtent: { min: string; max: string } | null,
  isTileKiosk = false
): ResultsAxes {
  const highRange = buildOutlierAxis(highOutliers.map((point) => point.value[1]));
  const lowRange = buildOutlierAxis(lowOutliers.map((point) => point.value[1]));
  const grids: echarts.GridComponentOption[] = [];
  const xAxes: echarts.XAXisComponentOption[] = [];
  const yAxes: echarts.YAXisComponentOption[] = [];
  let mainAxisIndex = 0;
  let highAxisIndex: number | null = null;
  let lowAxisIndex: number | null = null;
  const baseXAxis = (show: boolean): echarts.XAXisComponentOption => ({
    type: "time",
    boundaryGap: ["4%", "4%"],
    min: timeExtent?.min,
    max: timeExtent?.max,
    axisLabel: { show },
    axisTick: { show },
    axisLine: { show },
  });
  const pushAxis = (
    grid: echarts.GridComponentOption,
    xAxis: echarts.XAXisComponentOption,
    yAxis: echarts.YAXisComponentOption
  ): number => {
    const index = grids.length;
    grids.push(grid);
    xAxes.push({ ...xAxis, gridIndex: index });
    yAxes.push({ ...yAxis, gridIndex: index });
    return index;
  };

  if (!logScaleActive && control && (highRange || lowRange)) {
    const edge = { left: "6%", right: "4%", containLabel: true };
    if (highRange && lowRange) {
      highAxisIndex = pushAxis({ ...edge, top: isTileKiosk ? "9%" : "4%", height: "16%" }, baseXAxis(false), buildBrokenOutlierYAxis(highRange, isKiosk, isTileKiosk));
      mainAxisIndex = pushAxis({ ...edge, top: "26%", height: "48%" }, baseXAxis(false), buildBrokenMainYAxis(control.yAxis, isKiosk));
      lowAxisIndex = pushAxis({ ...edge, top: "78%", height: "16%" }, baseXAxis(true), buildBrokenOutlierYAxis(lowRange, isKiosk, isTileKiosk));
    } else if (highRange) {
      highAxisIndex = pushAxis({ ...edge, top: isTileKiosk ? "9%" : "4%", height: "18%" }, baseXAxis(false), buildBrokenOutlierYAxis(highRange, isKiosk, isTileKiosk));
      mainAxisIndex = pushAxis({ ...edge, top: "30%", height: "62%" }, baseXAxis(true), buildBrokenMainYAxis(control.yAxis, isKiosk));
    } else if (lowRange) {
      mainAxisIndex = pushAxis({ ...edge, top: "4%", height: "62%" }, baseXAxis(false), buildBrokenMainYAxis(control.yAxis, isKiosk));
      lowAxisIndex = pushAxis({ ...edge, top: "70%", height: "18%" }, baseXAxis(true), buildBrokenOutlierYAxis(lowRange, isKiosk, isTileKiosk));
    }
  } else {
    grids.push({ left: "6%", right: "4%", top: "6%", bottom: "12%", containLabel: true });
    xAxes.push(baseXAxis(true));
    yAxes.push(logScaleActive ? {
      type: "log",
      name: "Result",
      min: "dataMin",
      max: "dataMax",
      axisLabel: { hideOverlap: true, formatter: formatChartAxisTick },
    } : control?.yAxis ?? {
      type: "value",
      name: "Result",
      axisLabel: { hideOverlap: true, formatter: formatChartAxisTick },
    });
  }
  const axisPointer = !logScaleActive && control && (highRange || lowRange)
    ? { link: [{ xAxisIndex: xAxes.map((_, index) => index) }] }
    : undefined;
  if (isTileKiosk && yAxes[mainAxisIndex]) {
    yAxes[mainAxisIndex] = { ...yAxes[mainAxisIndex], name: "" };
  }
  return { grids, xAxes, yAxes, mainAxisIndex, highAxisIndex, lowAxisIndex, axisPointer };
}
