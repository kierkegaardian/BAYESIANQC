import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { ECElementEvent } from "echarts";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import type { QCRecordChartOutEvaluated, StreamCatalogOut, StreamChartOutEvaluated } from "../api/contracts";
import { loadStreamCatalog } from "../api/streamCatalog";
import { init as initChart, type ECharts } from "../charts/echarts";
import type { ChartRiskSummary } from "./chartRisk";
import { prepareChartData } from "./chartDataTransform";
import { buildResultsOption } from "./chartResultsOption";
import { buildRiskOption } from "./chartRiskOption";
import { endOfSelectedDay, parseSelectedDate, startOfSelectedDay } from "./chartViewSupport";

export type ChartMode = "results" | "risk" | "both";
export type ChartViewProps = {
  kiosk?: boolean;
  kioskDensity?: "full" | "tile";
  forcedStreamId?: string;
  forcedStart?: string;
  forcedEnd?: string;
  forcedMode?: ChartMode;
  refreshToken?: number;
};

export function useChartController(
  props: Readonly<ChartViewProps>,
  emitRiskSummary: (summary: ChartRiskSummary | null) => void,
  handleChartClick: (event: ECElementEvent) => void
) {
  const chartMode = ref<ChartMode>(props.forcedMode ?? "results");
  const streams = ref<StreamCatalogOut[]>([]);
  const chartRecords = ref<QCRecordChartOutEvaluated[]>([]);
  const streamId = ref("");
  const startDate = ref<Date | null>(null);
  const endDate = ref<Date | null>(null);
  const useLogScale = ref(false);
  const latestRiskSummary = ref<ChartRiskSummary | null>(null);
  const loading = ref(false);
  const error = ref("");
  const resultsChartRef = ref<HTMLDivElement | null>(null);
  const riskChartRef = ref<HTMLDivElement | null>(null);
  const isKiosk = computed(() => Boolean(props.kiosk));
  const isTileKiosk = computed(() => isKiosk.value && props.kioskDensity === "tile");
  const currentStreamLabel = computed(() => streamId.value || "Select stream");
  const chartSubtitle = computed(() => chartMode.value === "risk"
    ? "Bayesian predictive exceedance probabilities with alert markers."
    : "Results with Bayesian risk aligned to the same time window.");
  const resultsChartAriaLabel = computed(
    () => `QC results chart for ${currentStreamLabel.value}; ${chartRecords.value.length} data points.`
  );
  const riskChartAriaLabel = computed(
    () => `Predictive warning and action risk chart for ${currentStreamLabel.value}.`
  );
  const resultsChartStyle = computed(() => ({
    height: isKiosk.value
      ? isTileKiosk.value ? chartMode.value === "both" ? "22vh" : "30vh" : "58vh"
      : "clamp(260px, 32vh, 420px)",
  }));
  const riskChartStyle = computed(() => ({
    height: isKiosk.value
      ? isTileKiosk.value ? chartMode.value === "risk" ? "32vh" : "9vh"
        : chartMode.value === "risk" ? "calc(100vh - 124px)" : "20vh"
      : chartMode.value === "risk" ? "340px" : "clamp(108px, 14vh, 132px)",
  }));

  let resultsChart: ECharts | null = null;
  let riskChart: ECharts | null = null;
  let resizeTimer: number | null = null;
  let mounted = false;
  let requestSequence = 0;
  let suppressLogReload = false;

  function syncForcedState(): void {
    if (!isKiosk.value) return;
    if (props.forcedStreamId) streamId.value = props.forcedStreamId;
    chartMode.value = props.forcedMode ?? "both";
    startDate.value = parseSelectedDate(props.forcedStart);
    endDate.value = parseSelectedDate(props.forcedEnd);
    useLogScale.value = false;
  }

  function resizeCharts(): void {
    if (resizeTimer !== null) window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      resultsChart?.resize();
      riskChart?.resize();
      resizeTimer = null;
    }, 120);
  }

  async function loadStreams(): Promise<void> {
    streams.value = await loadStreamCatalog();
    if (isKiosk.value && props.forcedStreamId) streamId.value = props.forcedStreamId;
    else if (!streamId.value && streams.value.length) streamId.value = streams.value[0].stream_id;
  }

  function buildQuery(): string {
    const params = new URLSearchParams({ limit: "500" });
    if (startDate.value) params.set("start", startOfSelectedDay(startDate.value));
    if (endDate.value) params.set("end", endOfSelectedDay(endDate.value));
    return params.toString();
  }

  async function ensureCharts(): Promise<void> {
    await nextTick();
    if (chartMode.value !== "risk" && resultsChartRef.value) {
      if (!resultsChart) {
        resultsChart = initChart(resultsChartRef.value);
        resultsChart.on("click", handleChartClick);
      } else resultsChart.resize();
    }
    if (riskChartRef.value) {
      if (!riskChart) riskChart = initChart(riskChartRef.value);
      else riskChart.resize();
    }
  }

  async function loadChart(): Promise<void> {
    const sequence = ++requestSequence;
    loading.value = true;
    error.value = "";
    try {
      if (!streams.value.length) await loadStreams();
      if (!streamId.value) return;
      await ensureCharts();
      const stream = streams.value.find((item) => item.stream_id === streamId.value);
      const data = await api.get<StreamChartOutEvaluated>(`/streams/${streamId.value}/chart?${buildQuery()}`);
      if (sequence !== requestSequence) return;
      const prepared = prepareChartData(data, stream, useLogScale.value, isKiosk.value, isTileKiosk.value);
      chartRecords.value = prepared.records;
      latestRiskSummary.value = prepared.riskSummary;
      emitRiskSummary(prepared.riskSummary);
      if (useLogScale.value && !prepared.logScaleAllowed) {
        suppressLogReload = true;
        useLogScale.value = false;
        ElMessage.warning("Log scale requires positive values; showing linear scale.");
      }
      if (resultsChart && chartMode.value !== "risk") {
        resultsChart.setOption(buildResultsOption(prepared, stream, isKiosk.value, isTileKiosk.value));
      }
      riskChart?.setOption(buildRiskOption(prepared, stream, chartMode.value, isKiosk.value, isTileKiosk.value));
    } catch (caught) {
      if (sequence === requestSequence) {
        error.value = caught instanceof Error ? caught.message : "Chart data could not be loaded.";
      }
    } finally {
      if (sequence === requestSequence) loading.value = false;
    }
  }

  watch(useLogScale, () => {
    if (!mounted) return;
    if (suppressLogReload) {
      suppressLogReload = false;
      return;
    }
    void loadChart();
  });
  watch(chartMode, () => { if (mounted) void loadChart(); });
  watch(
    () => [props.forcedStreamId, props.forcedStart, props.forcedEnd, props.forcedMode, props.kioskDensity, props.refreshToken],
    () => {
      if (!mounted || !isKiosk.value) return;
      syncForcedState();
      void loadChart();
    }
  );
  onMounted(() => {
    mounted = true;
    window.addEventListener("resize", resizeCharts);
    syncForcedState();
    void loadChart();
  });
  onBeforeUnmount(() => {
    mounted = false;
    requestSequence += 1;
    window.removeEventListener("resize", resizeCharts);
    if (resizeTimer !== null) window.clearTimeout(resizeTimer);
    resultsChart?.dispose();
    riskChart?.dispose();
  });

  return {
    chartMode, chartRecords, chartSubtitle, currentStreamLabel, endDate, error, isKiosk,
    isTileKiosk, latestRiskSummary, loadChart, loading, resultsChartAriaLabel,
    resultsChartRef, resultsChartStyle, riskChartAriaLabel, riskChartRef, riskChartStyle,
    startDate, streamId, streams, useLogScale,
  };
}
