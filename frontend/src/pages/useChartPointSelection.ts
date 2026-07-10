import { ref } from "vue";
import type { ECElementEvent } from "echarts";
import type { QCRecordChartOutEvaluated } from "../api/contracts";
import { isChartPoint, recordToChartPoint, type ChartPoint } from "./chartPoint";

const pointSeries = new Set(["Result", "High outliers", "Low outliers"]);

export function useChartPointSelection(onInteraction?: (active: boolean) => void) {
  const selectedPoint = ref<ChartPoint | null>(null);
  const dialogOpen = ref(false);

  function selectPoint(point: ChartPoint): void {
    selectedPoint.value = point;
    dialogOpen.value = true;
    onInteraction?.(true);
  }

  function setDialogOpen(active: boolean): void {
    dialogOpen.value = active;
    onInteraction?.(active);
  }

  function selectRecord(record: QCRecordChartOutEvaluated): void {
    selectPoint(recordToChartPoint(record));
  }

  function handleChartClick(event: ECElementEvent): void {
    if (typeof event.seriesName !== "string" || !pointSeries.has(event.seriesName)) return;
    if (isChartPoint(event.data)) selectPoint(event.data);
  }

  return { dialogOpen, handleChartClick, selectRecord, selectedPoint, setDialogOpen };
}
