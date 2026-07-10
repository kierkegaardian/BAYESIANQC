import { LineChart, ScatterChart } from "echarts/charts";
import {
  AriaComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { init, use, type EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

use([
  LineChart,
  ScatterChart,
  AriaComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export { init };
export type ECharts = EChartsType;
