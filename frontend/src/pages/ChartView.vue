<template>
  <div class="page chart-page" :class="{ 'chart-page--kiosk': isKiosk }">
    <div v-if="!isKiosk" class="page-header">
      <div>
        <h2>QC Charts</h2>
        <div class="muted">Visualize QC results, alerts, and events.</div>
      </div>
      <el-button @click="loadChart">Refresh</el-button>
    </div>

    <div v-if="!isKiosk" class="toolbar" style="margin-bottom: 16px">
      <el-select v-model="streamId" placeholder="Select stream" class="full-width" style="max-width: 260px">
        <el-option
          v-for="stream in streams"
          :key="stream.stream_id"
          :label="stream.stream_id"
          :value="stream.stream_id"
        />
      </el-select>
      <el-date-picker v-model="startDate" type="date" placeholder="Start date" />
      <el-date-picker v-model="endDate" type="date" placeholder="End date" />
      <el-radio-group v-model="chartMode" size="small">
        <el-radio-button label="results">Results</el-radio-button>
        <el-radio-button label="risk">Risk</el-radio-button>
        <el-radio-button label="both">Both</el-radio-button>
      </el-radio-group>
      <el-switch
        v-show="chartMode !== 'risk'"
        v-model="useLogScale"
        active-text="Log scale"
        inactive-text="Linear"
      />
      <el-button type="primary" @click="loadChart">Load</el-button>
    </div>

    <el-card :class="['chart-card', { 'chart-card--kiosk': isKiosk }]">
      <div v-if="!isKiosk" class="chart-panel-header">
        <div>
          <h3>{{ currentStreamLabel }}</h3>
          <div class="muted">{{ chartSubtitle }}</div>
        </div>
        <ChartRiskBadge :summary="latestRiskSummary" />
      </div>

      <div v-show="chartMode !== 'risk'" ref="resultsChartRef" :style="resultsChartStyle"></div>

      <div
        class="risk-rail"
        :class="{ 'risk-rail--standalone': chartMode === 'risk', 'risk-rail--kiosk': isKiosk }"
      >
        <div v-if="!isKiosk" class="risk-rail-header">
          <span>Bayesian risk</span>
          <span>{{ latestRiskSummary?.detailLabel ?? "No risk history" }}</span>
        </div>
        <div ref="riskChartRef" :style="riskChartStyle"></div>
      </div>
    </el-card>

    <el-dialog
      v-model="commentDialogOpen"
      :title="pointDialogTitle"
      :width="pointDialogWidth"
      destroy-on-close
    >
      <div v-if="selectedPoint" class="point-comment-context">
        <div><span>Record</span><strong>#{{ selectedPoint.record_id }}</strong></div>
        <div><span>Time</span><strong>{{ formatPointTime(selectedPoint.value[0]) }}</strong></div>
        <div><span>Result</span><strong>{{ selectedPoint.value[1] ?? "outlier" }}</strong></div>
        <div><span>Disposition</span><strong>{{ selectedPoint.disposition ?? "-" }}</strong></div>
        <div><span>Signals</span><strong>{{ selectedPointSignalLabel }}</strong></div>
        <div><span>Bayesian risk</span><strong>{{ selectedPointRiskLabel }}</strong></div>
      </div>
      <QCCommentThread
        v-if="selectedPoint"
        target-type="qc_record"
        :target-id="String(selectedPoint.record_id)"
        title="Record Comments"
      />
      <template #footer>
        <el-button @click="commentDialogOpen = false">Close</el-button>
        <el-button
          v-if="canApprove && selectedPoint?.include_in_stats === false"
          type="primary"
          @click="promptSelectedResolution(true)"
        >
          Reinstate
        </el-button>
        <el-button
          v-if="canApprove && selectedPoint?.include_in_stats !== false"
          type="warning"
          @click="promptSelectedResolution(false)"
        >
          Exclude From Stats
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import type {
  ECElementEvent,
  LineSeriesOption,
  MarkAreaComponentOption,
  MarkLineComponentOption,
  ScatterSeriesOption,
} from "echarts";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";
import { canApprove } from "../api/session";
import ChartRiskBadge from "./ChartRiskBadge.vue";
import QCCommentThread from "../components/QCCommentThread.vue";
import {
  BAYESIAN_RISK_MEANING,
  BAYESIAN_RISK_SCORE_MEANING,
  bayesianRiskBasisText,
  riskThresholds,
  summarizeChartRisk,
  type ChartRiskSummary,
} from "./chartRisk";
import type {
  AlertOutWithQc,
  BayesianRisk,
  Disposition,
  FrequentistSignal,
  LotSegmentOut,
  QCEventOut,
  QCRecordChartOut,
  QCRecordResolutionIn,
  StreamChartOutEvaluated,
  StreamConfigOut,
} from "../api/contracts";

type ChartMode = "results" | "risk" | "both";
type KioskDensity = "full" | "tile";
type ChartViewProps = {
  kiosk?: boolean;
  kioskDensity?: KioskDensity;
  forcedStreamId?: string;
  forcedStart?: string;
  forcedEnd?: string;
  forcedMode?: ChartMode;
  refreshToken?: number;
};

const props = withDefaults(defineProps<ChartViewProps>(), {
  kiosk: false,
});
const emit = defineEmits<{
  "risk-summary": [summary: ChartRiskSummary | null];
}>();

const chartMode = ref<ChartMode>(props.forcedMode ?? "results");
const isKiosk = computed(() => props.kiosk);
const isTileKiosk = computed(() => isKiosk.value && props.kioskDensity === "tile");
const resultsChartStyle = computed(() => ({
  height: isKiosk.value
    ? isTileKiosk.value
      ? chartMode.value === "both"
        ? "22vh"
        : "30vh"
      : "58vh"
    : "clamp(260px, 32vh, 420px)",
}));
const riskChartStyle = computed(() => ({
  height: isKiosk.value
    ? isTileKiosk.value
      ? chartMode.value === "risk"
        ? "32vh"
        : "9vh"
      : chartMode.value === "risk"
        ? "calc(100vh - 124px)"
        : "20vh"
    : chartMode.value === "risk"
      ? "340px"
      : "clamp(108px, 14vh, 132px)",
}));
const resultsChartRef = ref<HTMLDivElement | null>(null);
const riskChartRef = ref<HTMLDivElement | null>(null);
let resultsChart: echarts.ECharts | null = null;
let riskChart: echarts.ECharts | null = null;

let resizeTimer: number | null = null;

type ChartPoint = {
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

type OutlierPoint = Omit<ChartPoint, "value"> & {
  value: [string, number];
  symbolRotate: number;
  itemStyle: { color: string };
  label: {
    show: true;
    formatter: string;
    position: "top" | "bottom";
    color: string;
    fontWeight: number;
  };
};

function isChartPoint(value: unknown): value is ChartPoint {
  if (!value || typeof value !== "object") {
    return false;
  }
  const recordId = (value as { record_id?: unknown }).record_id;
  const tuple = (value as { value?: unknown }).value;
  return (
    typeof recordId === "number" &&
    Array.isArray(tuple) &&
    tuple.length === 2 &&
    typeof tuple[0] === "string"
  );
}

type TooltipItem = { data?: unknown; value?: unknown; seriesName?: unknown };
type TooltipDisplayOptions = {
  appendTo?: "body";
  className?: string;
  confine?: boolean;
  renderMode: "html";
};
type MarkLineData = NonNullable<MarkLineComponentOption["data"]>;

function asFormatterItems(params: unknown): TooltipItem[] {
  if (Array.isArray(params)) {
    return params.filter((item): item is TooltipItem => !!item && typeof item === "object");
  }
  if (params && typeof params === "object") {
    return [params as TooltipItem];
  }
  return [];
}

function hasNumericChartValue(item: TooltipItem): boolean {
  if (!isChartPoint(item.data)) {
    return false;
  }
  const value = item.data.value[1];
  return typeof value === "number" && Number.isFinite(value);
}

const streams = ref<StreamConfigOut[]>([]);
const streamId = ref("");
const startDate = ref<Date | null>(null);
const endDate = ref<Date | null>(null);
const useLogScale = ref(false);
const suppressLogReload = ref(false);
const latestRiskSummary = ref<ChartRiskSummary | null>(null);
const commentDialogOpen = ref(false);
const selectedPoint = ref<ChartPoint | null>(null);
const currentStreamLabel = computed(() => streamId.value || "Select stream");
const chartSubtitle = computed(() =>
  chartMode.value === "risk"
    ? "Bayesian predictive exceedance probabilities with alert markers."
    : "Results with Bayesian risk aligned to the same time window."
);
const pointDialogTitle = computed(() => (isKiosk.value ? "QC Point Detail" : "QC Point Comments"));
const pointDialogWidth = computed(() => (isKiosk.value ? "min(760px, calc(100vw - 32px))" : "560px"));
const selectedPointSignalLabel = computed(() => {
  const signals = selectedPoint.value?.signals;
  return signals?.length ? signals.map((signal) => signal.rule).join(", ") : "none";
});
const selectedPointRiskLabel = computed(() => {
  const risk = selectedPoint.value?.bayesian_risk;
  if (!risk || !Number.isFinite(Number(risk.risk_score))) {
    return "-";
  }
  return `${Number(risk.risk_score).toFixed(0)}/100`;
});

function deriveLotSegments(records: QCRecordChartOut[]): LotSegmentOut[] {
  if (!records.length) {
    return [];
  }
  const segments: LotSegmentOut[] = [];
  let currentLot = records[0].control_material_lot || "unknown";
  let start = records[0].timestamp;
  let last = records[0].timestamp;
  let count = 0;
  for (const record of records) {
    const lot = record.control_material_lot || "unknown";
    if (lot !== currentLot) {
      segments.push({
        control_material_lot: currentLot,
        start,
        end: last,
        count,
      });
      currentLot = lot;
      start = record.timestamp;
      count = 0;
    }
    count += 1;
    last = record.timestamp;
  }
  segments.push({
    control_material_lot: currentLot,
    start,
    end: last,
    count,
  });
  return segments;
}

function padSegmentEnd(start: string, end: string): string {
  if (start !== end) {
    return end;
  }
  const startDate = new Date(start);
  return new Date(startDate.getTime() + 1000).toISOString();
}

function formatEventLabel(event: QCEventOut): string {
  return String(event.event_type).replaceAll("_", " ");
}

function startOfSelectedDay(date: Date): string {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy.toISOString();
}

function endOfSelectedDay(date: Date): string {
  const copy = new Date(date);
  copy.setHours(23, 59, 59, 999);
  return copy.toISOString();
}

function parseSelectedDate(value: string | undefined): Date | null {
  if (!value) {
    return null;
  }
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly) {
    const [, year, month, day] = dateOnly;
    return new Date(Number(year), Number(month) - 1, Number(day));
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function syncForcedKioskState(): void {
  if (!isKiosk.value) {
    return;
  }
  if (props.forcedStreamId) {
    streamId.value = props.forcedStreamId;
  }
  chartMode.value = props.forcedMode ?? "both";
  startDate.value = parseSelectedDate(props.forcedStart);
  endDate.value = parseSelectedDate(props.forcedEnd);
  useLogScale.value = false;
}

function resizeCharts(): void {
  if (resizeTimer !== null) {
    window.clearTimeout(resizeTimer);
  }
  resizeTimer = window.setTimeout(() => {
    resultsChart?.resize();
    riskChart?.resize();
    resizeTimer = null;
  }, 120);
}

async function loadStreams() {
  streams.value = await api.get<StreamConfigOut[]>("/streams");
  if (isKiosk.value && props.forcedStreamId) {
    streamId.value = props.forcedStreamId;
  } else if (!streamId.value && streams.value.length) {
    streamId.value = streams.value[0].stream_id;
  }
}

async function updateResolution(
  recordId: number,
  includeInStats: boolean,
  reason?: string
) {
  try {
    const payload: QCRecordResolutionIn = {
      include_in_stats: includeInStats,
      resolved_reason: reason || null,
    };
    await api.patch(`/qc/records/${recordId}/resolution`, payload);
    ElMessage.success(
      includeInStats ? "Record reinstated" : "Record resolved"
    );
    await loadChart();
  } catch (error) {
    const message =
      error instanceof Error && error.message
        ? error.message
        : "Failed to update record";
    ElMessage.error(message);
  }
}

async function handleChartClick(params: ECElementEvent): Promise<void> {
  if (
    params?.seriesName !== "Result" &&
    params?.seriesName !== "High outliers" &&
    params?.seriesName !== "Low outliers"
  ) {
    return;
  }
  if (!isChartPoint(params.data)) {
    return;
  }
  selectedPoint.value = params.data;
  commentDialogOpen.value = true;
}

function tooltipDisplayOptions(): TooltipDisplayOptions {
  return isKiosk.value
    ? { appendTo: "body", className: "qc-chart-tooltip", confine: false, renderMode: "html" }
    : { confine: true, renderMode: "html" };
}

function formatPointTime(value: string): string {
  return new Date(value).toLocaleString();
}

async function promptSelectedResolution(includeInStats: boolean): Promise<void> {
  const point = selectedPoint.value;
  if (!point || !canApprove.value) {
    return;
  }
  const promptResult = await ElMessageBox.prompt(
    includeInStats ? "Reason" : "Why should this point be excluded from stats?",
    includeInStats ? "Reinstate QC Point" : "Resolve QC Point",
    {
      confirmButtonText: includeInStats ? "Reinstate" : "Resolve",
      cancelButtonText: "Cancel",
      inputPlaceholder: includeInStats
        ? "Why should this point be included again?"
        : "e.g. reagent lot change or known variation",
    }
  ).catch(() => null);
  if (!promptResult) {
    return;
  }
  await updateResolution(point.record_id, includeInStats, promptResult.value);
  commentDialogOpen.value = false;
}

function attachResultsChartHandlers() {
  if (!resultsChart) {
    return;
  }
  resultsChart.off("click");
  resultsChart.on("click", (params: ECElementEvent) => {
    void handleChartClick(params);
  });
}

function buildControlSeries(stream: StreamConfigOut | undefined) {
  if (!stream) {
    return null;
  }
  const mean = Number(stream.target_value);
  const sigma = Number(stream.sigma);
  if (!Number.isFinite(mean) || !Number.isFinite(sigma) || sigma <= 0) {
    return null;
  }
  const warningSd = Number.isFinite(Number(stream.warning_limit_sd))
    ? Number(stream.warning_limit_sd)
    : 2;
  const actionSd = Number.isFinite(Number(stream.action_limit_sd))
    ? Number(stream.action_limit_sd)
    : 3;

  const actionDelta = actionSd * sigma;

  const markAreaData: MarkAreaComponentOption["data"] = [
    [
      {
        yAxis: mean - actionSd * sigma,
        itemStyle: { color: "rgba(239, 68, 68, 0.08)" },
      },
      { yAxis: mean + actionSd * sigma },
    ],
    [
      {
        yAxis: mean - warningSd * sigma,
        itemStyle: { color: "rgba(234, 179, 8, 0.1)" },
      },
      { yAxis: mean + warningSd * sigma },
    ],
    [
      {
        yAxis: mean - sigma,
        itemStyle: { color: "rgba(34, 197, 94, 0.12)" },
      },
      { yAxis: mean + sigma },
    ],
  ];

  const markLineData: MarkLineComponentOption["data"] = [
    {
      yAxis: mean,
      lineStyle: { color: "#0f172a", width: 1.5 },
      label: { formatter: "Mean", color: "#0f172a" },
    },
    {
      yAxis: mean + warningSd * sigma,
      lineStyle: { color: "#f59e0b", type: "dashed" },
      label: { formatter: `+${warningSd} SD`, color: "#f59e0b" },
    },
    {
      yAxis: mean - warningSd * sigma,
      lineStyle: { color: "#f59e0b", type: "dashed" },
      label: { formatter: `-${warningSd} SD`, color: "#f59e0b" },
    },
    {
      yAxis: mean + actionSd * sigma,
      lineStyle: { color: "#ef4444", type: "dashed" },
      label: { formatter: `+${actionSd} SD`, color: "#ef4444" },
    },
    {
      yAxis: mean - actionSd * sigma,
      lineStyle: { color: "#ef4444", type: "dashed" },
      label: { formatter: `-${actionSd} SD`, color: "#ef4444" },
    },
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

  const yAxis: echarts.YAXisComponentOption = {
    type: "value",
    name: "Result",
    min: mean - actionDelta,
    max: mean + actionDelta,
  };

  return { controlSeries, yAxis, minValue: mean - actionDelta, maxValue: mean + actionDelta };
}

function buildOutlierAxis(values: number[], direction: "high" | "low") {
  if (!values.length) {
    return null;
  }
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = Math.max(
    Math.abs(maxValue - minValue),
    Math.abs(maxValue),
    Math.abs(minValue),
    1
  );
  const pad = span * 0.1;
  if (direction === "high") {
    return { min: minValue, max: maxValue + pad };
  }
  return { min: minValue - pad, max: maxValue };
}

function buildParams() {
  const params = new URLSearchParams();
  if (startDate.value) {
    params.set("start", startOfSelectedDay(startDate.value));
  }
  if (endDate.value) {
    params.set("end", endOfSelectedDay(endDate.value));
  }
  params.set("limit", "500");
  return params.toString();
}

async function ensureCharts(): Promise<void> {
  await nextTick();
  if (chartMode.value !== "risk" && resultsChartRef.value) {
    if (!resultsChart) {
      resultsChart = echarts.init(resultsChartRef.value);
      attachResultsChartHandlers();
    } else {
      resultsChart.resize();
    }
  }
  if (riskChartRef.value) {
    if (!riskChart) {
      riskChart = echarts.init(riskChartRef.value);
    } else {
      riskChart.resize();
    }
  }
}

async function loadChart() {
  if (!streamId.value) {
    return;
  }
  if (!streams.value.length) {
    await loadStreams();
  }
  await ensureCharts();
  const stream = streams.value.find((item) => item.stream_id === streamId.value);
  const query = buildParams();
  const data = await api.get<StreamChartOutEvaluated>(
    `/streams/${streamId.value}/chart?${query}`
  );
  const records = data.records;
  const alerts = data.alerts as AlertOutWithQc[];
  const segments = data.lot_segments.length
    ? data.lot_segments
    : deriveLotSegments(records);
  const riskSummary = summarizeChartRisk(records, stream);
  latestRiskSummary.value = riskSummary;
  emit("risk-summary", riskSummary);

  const controlConfig = buildControlSeries(stream);
  const limitMin = controlConfig?.minValue;
  const limitMax = controlConfig?.maxValue;
  const logScaleAllowed =
    records.every((record) => record.result_value > 0) &&
    (limitMin === undefined || limitMin > 0);
  const logScaleActive = useLogScale.value && logScaleAllowed;
  if (useLogScale.value && !logScaleAllowed) {
    suppressLogReload.value = true;
    useLogScale.value = false;
    ElMessage.warning("Log scale requires positive values; showing linear scale.");
  }
  const allowBreaks =
    !logScaleActive &&
    limitMin !== undefined &&
    limitMax !== undefined &&
    records.some((record) => record.result_value < limitMin || record.result_value > limitMax);

  const seriesData: ChartPoint[] = records.map((record) => ({
    value: [
      record.timestamp,
      allowBreaks &&
      limitMin !== undefined &&
      limitMax !== undefined &&
      (record.result_value < limitMin || record.result_value > limitMax)
        ? null
        : record.result_value,
    ],
    lot: record.control_material_lot,
    record_id: record.id,
    include_in_stats: record.include_in_stats,
    resolved_reason: record.resolved_reason,
    resolved_at: record.resolved_at,
    disposition: record.disposition ?? null,
    signals: record.signals ?? null,
    bayesian_risk: record.bayesian_risk ?? null,
    itemStyle:
      record.include_in_stats === false
        ? { color: "#94a3b8" }
        : undefined,
  }));
  const posteriorMeanPoints: Array<[string, number | null]> = records.map((record) => [
    record.timestamp,
    record.bayesian_risk && record.bayesian_risk.posterior_mean !== null && record.bayesian_risk.posterior_mean !== undefined
      ? Number(record.bayesian_risk.posterior_mean)
      : null,
  ]);
  const predictiveLowerPoints: Array<[string, number | null]> = records.map((record) => [
    record.timestamp,
    record.bayesian_risk?.predictive_interval
      ? Number(record.bayesian_risk.predictive_interval[0])
      : null,
  ]);
  const predictiveUpperPoints: Array<[string, number | null]> = records.map((record) => [
    record.timestamp,
    record.bayesian_risk?.predictive_interval
      ? Number(record.bayesian_risk.predictive_interval[1])
      : null,
  ]);
  const credibleLowerPoints: Array<[string, number | null]> = records.map((record) => [
    record.timestamp,
    record.bayesian_risk?.credible_interval
      ? Number(record.bayesian_risk.credible_interval[0])
      : null,
  ]);
  const credibleUpperPoints: Array<[string, number | null]> = records.map((record) => [
    record.timestamp,
    record.bayesian_risk?.credible_interval
      ? Number(record.bayesian_risk.credible_interval[1])
      : null,
  ]);
  const warnProbabilityPoints: Array<[string, number | null]> = records.map((record) => [
    record.timestamp,
    record.bayesian_risk
      ? Math.max(
          0,
          Math.min(100, Number(record.bayesian_risk.probability_outside_warning) * 100)
        )
      : null,
  ]);
  const actionProbabilityPoints: Array<[string, number | null]> = records.map((record) => [
    record.timestamp,
    record.bayesian_risk
      ? Math.max(
          0,
          Math.min(100, Number(record.bayesian_risk.probability_outside_limits) * 100)
        )
      : null,
  ]);
  const alertPoints: Array<[string, number]> = alerts.map((alert) => [
    alert.qc_record_timestamp ?? alert.created_at,
    alert.bayesian_risk
      ? Math.max(0, Math.min(100, Number(alert.bayesian_risk.probability_outside_limits) * 100))
      : 0,
  ]);

  const segmentAreas: MarkAreaComponentOption["data"] = segments.map((segment) => [
    {
      xAxis: segment.start,
      label: { show: !isKiosk.value, formatter: `Lot ${segment.control_material_lot}` },
    },
    { xAxis: padSegmentEnd(segment.start, segment.end) },
  ] as const);

  const eventLines: MarkLineData = data.events.map((event) => ({
    xAxis: event.timestamp,
    label: { show: !isKiosk.value, formatter: formatEventLabel(event), color: "#0369a1", fontSize: 11 },
    lineStyle: { color: "#0ea5e9", type: "dotted" as const, width: 1.5 },
  }));

  const alertLines: MarkLineData = alerts.map((alert) => ({
    xAxis: alert.qc_record_timestamp ?? alert.created_at,
    label: { show: !isKiosk.value, formatter: "Alert", color: "#991b1b", fontSize: 11 },
    lineStyle: { color: "#dc2626", type: "solid" as const, width: 1.25 },
  }));

  const resultSeries: LineSeriesOption = {
    name: "Result",
    type: "line",
    data: seriesData,
    smooth: false,
    connectNulls: false,
    showSymbol: isKiosk.value,
    symbolSize: isKiosk.value ? (isTileKiosk.value ? 5 : 7) : 6,
    lineStyle: { color: "#2563eb" },
  };

  if (segmentAreas.length) {
    resultSeries.markArea = {
      silent: true,
      itemStyle: { color: "rgba(148, 163, 184, 0.18)" },
      label: { show: !isKiosk.value, color: "#475569", fontSize: 11 },
      data: segmentAreas,
    };
  }

  const resultMarkLines: MarkLineData = [
    ...segments.slice(1).map((segment) => ({
      xAxis: segment.start,
      lineStyle: { color: "#94a3b8", type: "dashed" as const },
      label: {
        show: !isKiosk.value,
        formatter: `Lot ${segment.control_material_lot}`,
        color: "#475569",
        fontSize: 11,
      },
    })),
    ...eventLines,
    ...alertLines,
  ];

  if (resultMarkLines.length) {
    resultSeries.markLine = {
      silent: true,
      symbol: "none",
      data: resultMarkLines,
    };
  }

  const posteriorMeanSeries: LineSeriesOption = {
    name: "Posterior mean",
    type: "line",
    data: posteriorMeanPoints,
    showSymbol: false,
    connectNulls: false,
    silent: true,
    lineStyle: { color: "#16a34a", width: 2 },
    tooltip: { show: false },
    emphasis: { disabled: true },
  };

  const predictiveLowerSeries: LineSeriesOption = {
    name: "Predictive interval (low)",
    type: "line",
    data: predictiveLowerPoints,
    showSymbol: false,
    connectNulls: false,
    silent: true,
    lineStyle: { color: "rgba(20, 184, 166, 0.75)", type: "dashed", width: 1.5 },
    tooltip: { show: false },
    emphasis: { disabled: true },
  };

  const predictiveUpperSeries: LineSeriesOption = {
    name: "Predictive interval (high)",
    type: "line",
    data: predictiveUpperPoints,
    showSymbol: false,
    connectNulls: false,
    silent: true,
    lineStyle: { color: "rgba(20, 184, 166, 0.75)", type: "dashed", width: 1.5 },
    tooltip: { show: false },
    emphasis: { disabled: true },
  };

  const credibleLowerSeries: LineSeriesOption = {
    name: "Mean credible interval (low)",
    type: "line",
    data: credibleLowerPoints,
    showSymbol: false,
    connectNulls: false,
    silent: true,
    lineStyle: { color: "rgba(71, 85, 105, 0.6)", type: "dotted", width: 1.25 },
    tooltip: { show: false },
    emphasis: { disabled: true },
  };

  const credibleUpperSeries: LineSeriesOption = {
    name: "Mean credible interval (high)",
    type: "line",
    data: credibleUpperPoints,
    showSymbol: false,
    connectNulls: false,
    silent: true,
    lineStyle: { color: "rgba(71, 85, 105, 0.6)", type: "dotted", width: 1.25 },
    tooltip: { show: false },
    emphasis: { disabled: true },
  };

  const highOutliers: OutlierPoint[] = [];
  const lowOutliers: OutlierPoint[] = [];
  if (allowBreaks && limitMin !== undefined && limitMax !== undefined) {
    for (const record of records) {
      if (record.result_value > limitMax || record.result_value < limitMin) {
        const isHigh = record.result_value > limitMax;
        const isResolved = record.include_in_stats === false;
        const labelColor = isResolved ? "#64748b" : "#991b1b";
        const outlier = {
          value: [record.timestamp, record.result_value],
          lot: record.control_material_lot,
          record_id: record.id,
          include_in_stats: record.include_in_stats,
          resolved_reason: record.resolved_reason,
          resolved_at: record.resolved_at,
          symbolRotate: isHigh ? 0 : 180,
          itemStyle: { color: isResolved ? "#94a3b8" : "#ef4444" },
          label: {
            show: true,
            formatter: `${record.result_value}`,
            position: isHigh ? "top" : "bottom",
            color: labelColor,
            fontWeight: 600,
          },
        } satisfies OutlierPoint;
        if (isHigh) {
          highOutliers.push(outlier);
        } else {
          lowOutliers.push(outlier);
        }
      }
    }
  }

  const highAxisRange = buildOutlierAxis(
    highOutliers.map((point) => point.value[1]),
    "high"
  );
  const lowAxisRange = buildOutlierAxis(
    lowOutliers.map((point) => point.value[1]),
    "low"
  );

  const hasHighOutliers = Boolean(highAxisRange);
  const hasLowOutliers = Boolean(lowAxisRange);

  const grids: echarts.GridComponentOption[] = [];
  const xAxes: echarts.XAXisComponentOption[] = [];
  const yAxes: echarts.YAXisComponentOption[] = [];
  let mainAxisIndex = 0;
  let highAxisIndex: number | null = null;
  let lowAxisIndex: number | null = null;

  const baseXAxis = (showLabels: boolean): echarts.XAXisComponentOption => ({
    type: "time",
    axisLabel: { show: showLabels },
    axisTick: { show: showLabels },
    axisLine: { show: showLabels },
  });

  const pushAxis = (
    grid: echarts.GridComponentOption,
    xAxis: echarts.XAXisComponentOption,
    yAxis: echarts.YAXisComponentOption
  ) => {
    const index = grids.length;
    grids.push(grid);
    xAxes.push({ ...xAxis, gridIndex: index });
    yAxes.push({ ...yAxis, gridIndex: index });
    return index;
  };

  const logAxis = {
    type: "log",
    name: "Result",
    min: "dataMin",
    max: "dataMax",
  } satisfies echarts.YAXisComponentOption;

  if (!logScaleActive && controlConfig && (hasHighOutliers || hasLowOutliers)) {
    const left = "6%";
    const right = "4%";
    if (hasHighOutliers && hasLowOutliers) {
      highAxisIndex = pushAxis(
        { left, right, top: "4%", height: "18%", containLabel: true },
        baseXAxis(false),
        {
          type: "value",
          name: "High",
          min: highAxisRange?.min,
          max: highAxisRange?.max,
        } satisfies echarts.YAXisComponentOption
      );
      mainAxisIndex = pushAxis(
        { left, right, top: "26%", height: "48%", containLabel: true },
        baseXAxis(false),
        controlConfig.yAxis
      );
      lowAxisIndex = pushAxis(
        { left, right, top: "78%", height: "18%", containLabel: true },
        baseXAxis(true),
        {
          type: "value",
          name: "Low",
          min: lowAxisRange?.min,
          max: lowAxisRange?.max,
        } satisfies echarts.YAXisComponentOption
      );
    } else if (hasHighOutliers) {
      highAxisIndex = pushAxis(
        { left, right, top: "4%", height: "22%", containLabel: true },
        baseXAxis(false),
        {
          type: "value",
          name: "High",
          min: highAxisRange?.min,
          max: highAxisRange?.max,
        } satisfies echarts.YAXisComponentOption
      );
      mainAxisIndex = pushAxis(
        { left, right, top: "30%", height: "62%", containLabel: true },
        baseXAxis(true),
        controlConfig.yAxis
      );
    } else if (hasLowOutliers) {
      mainAxisIndex = pushAxis(
        { left, right, top: "4%", height: "62%", containLabel: true },
        baseXAxis(false),
        controlConfig.yAxis
      );
      lowAxisIndex = pushAxis(
        { left, right, top: "70%", height: "22%", containLabel: true },
        baseXAxis(true),
        {
          type: "value",
          name: "Low",
          min: lowAxisRange?.min,
          max: lowAxisRange?.max,
        } satisfies echarts.YAXisComponentOption
      );
    }
  } else {
    grids.push({ left: "6%", right: "4%", top: "6%", bottom: "12%", containLabel: true });
    xAxes.push(baseXAxis(true));
    if (logScaleActive) {
      yAxes.push(logAxis);
    } else {
      yAxes.push(
        controlConfig?.yAxis ?? ({ type: "value", name: "Result" } satisfies echarts.YAXisComponentOption)
      );
    }
  }

  if (controlConfig?.controlSeries) {
    controlConfig.controlSeries.xAxisIndex = mainAxisIndex;
    controlConfig.controlSeries.yAxisIndex = mainAxisIndex;
  }

  posteriorMeanSeries.xAxisIndex = mainAxisIndex;
  posteriorMeanSeries.yAxisIndex = mainAxisIndex;
  predictiveLowerSeries.xAxisIndex = mainAxisIndex;
  predictiveLowerSeries.yAxisIndex = mainAxisIndex;
  predictiveUpperSeries.xAxisIndex = mainAxisIndex;
  predictiveUpperSeries.yAxisIndex = mainAxisIndex;
  credibleLowerSeries.xAxisIndex = mainAxisIndex;
  credibleLowerSeries.yAxisIndex = mainAxisIndex;
  credibleUpperSeries.xAxisIndex = mainAxisIndex;
  credibleUpperSeries.yAxisIndex = mainAxisIndex;

  resultSeries.xAxisIndex = mainAxisIndex;
  resultSeries.yAxisIndex = mainAxisIndex;

  const series: echarts.SeriesOption[] = [
    ...(controlConfig?.controlSeries ? [controlConfig.controlSeries] : []),
    predictiveLowerSeries,
    predictiveUpperSeries,
    credibleLowerSeries,
    credibleUpperSeries,
    posteriorMeanSeries,
    resultSeries,
  ];

  if (highOutliers.length && highAxisIndex !== null) {
    const outliers: ScatterSeriesOption = {
      name: "High outliers",
      type: "scatter",
      data: highOutliers,
      symbol: "triangle",
      symbolSize: 12,
      xAxisIndex: highAxisIndex,
      yAxisIndex: highAxisIndex,
    };
    series.push(outliers);
  }

  if (lowOutliers.length && lowAxisIndex !== null) {
    const outliers: ScatterSeriesOption = {
      name: "Low outliers",
      type: "scatter",
      data: lowOutliers,
      symbol: "triangle",
      symbolSize: 12,
      xAxisIndex: lowAxisIndex,
      yAxisIndex: lowAxisIndex,
    };
    series.push(outliers);
  }

  const axisPointer =
    !logScaleActive && controlConfig && (hasHighOutliers || hasLowOutliers)
      ? { link: [{ xAxisIndex: xAxes.map((_, index) => index) }] }
      : undefined;

  const resultsOption: echarts.EChartsOption = {
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    axisPointer,
    series,
    tooltip: {
      ...tooltipDisplayOptions(),
      trigger: isKiosk.value ? "item" : "axis",
      triggerOn: "mousemove|click",
      formatter: (params: unknown) => {
        const items = asFormatterItems(params);
        const recordItem =
          items.find(hasNumericChartValue) ??
          items.find((item) => isChartPoint(item.data));
        if (!recordItem || !isChartPoint(recordItem.data)) {
          return "";
        }
        const lot = recordItem.data.lot;
        const value = recordItem.data.value[1];
        const timestamp = recordItem.data.value[0];
        const includeInStats = recordItem.data.include_in_stats !== false;
        const resolvedReason = recordItem.data.resolved_reason;
        const disposition = recordItem.data.disposition;
        const signals = recordItem.data.signals;
        const risk = recordItem.data.bayesian_risk;
        const parts: string[] = [];
        if (timestamp) {
          parts.push(new Date(timestamp).toLocaleString());
        }
        if (typeof value === "number" && Number.isFinite(value)) {
          parts.push(`Result: ${value}`);
        }
        if (disposition) {
          parts.push(`Disposition: ${disposition}`);
        }
        if (signals && signals.length) {
          const summary = signals.map((signal) => signal.rule).join(", ");
          parts.push(`Signals: ${summary}`);
        }
        if (risk) {
          const riskScore = Number.isFinite(Number(risk.risk_score)) ? Number(risk.risk_score).toFixed(0) : "-";
          const pWarn = Math.max(0, Math.min(1, Number(risk.probability_outside_warning)));
          const pAction = Math.max(0, Math.min(1, Number(risk.probability_outside_limits)));
          parts.push(`Bayesian risk: ${riskScore}/100`);
          parts.push(BAYESIAN_RISK_MEANING);
          parts.push(bayesianRiskBasisText("through this point"));
          parts.push(BAYESIAN_RISK_SCORE_MEANING);
          parts.push(`P(outside warn): ${(pWarn * 100).toFixed(1)}%`);
          parts.push(`P(outside action): ${(pAction * 100).toFixed(1)}%`);
          if (risk.posterior_mean !== null && risk.posterior_mean !== undefined) {
            parts.push(`Posterior mean: ${Number(risk.posterior_mean).toFixed(4)}`);
          }
          if (risk.credible_interval) {
            const lo = Number(risk.credible_interval[0]);
            const hi = Number(risk.credible_interval[1]);
            parts.push(`Mean CI95: [${lo.toFixed(4)}, ${hi.toFixed(4)}]`);
          }
          if (risk.predictive_interval) {
            const lo = Number(risk.predictive_interval[0]);
            const hi = Number(risk.predictive_interval[1]);
            parts.push(`Pred PI95: [${lo.toFixed(4)}, ${hi.toFixed(4)}]`);
          }
          const warnReq =
            stream?.bayes_warn_consecutive !== null && stream?.bayes_warn_consecutive !== undefined
              ? Number(stream.bayes_warn_consecutive)
              : 1;
          const holdReq =
            stream?.bayes_hold_consecutive !== null && stream?.bayes_hold_consecutive !== undefined
              ? Number(stream.bayes_hold_consecutive)
              : 1;
          const warnStreak = Number.isFinite(Number(risk.warn_streak)) ? Number(risk.warn_streak) : 0;
          const holdStreak = Number.isFinite(Number(risk.hold_streak)) ? Number(risk.hold_streak) : 0;
          parts.push(`Streaks: warn ${warnStreak}/${warnReq}, hold ${holdStreak}/${holdReq}`);
        }
        if (lot) {
          parts.push(`Lot: ${lot}`);
        }
        if (!includeInStats) {
          parts.push("Resolved: excluded from stats");
          if (resolvedReason) {
            parts.push(`Reason: ${resolvedReason}`);
          }
        }
        return parts.join("<br/>");
      },
    },
  };
  if (resultsChart && (chartMode.value === "results" || chartMode.value === "both")) {
    resultsChart.setOption(resultsOption);
  }

  const thresholds = riskThresholds(stream);
  const thresholdLines: MarkLineData = [
    {
      yAxis: thresholds.warnLine,
      lineStyle: { color: "#f59e0b", type: "dashed" },
      label: { formatter: `Warn ${thresholds.warnLine.toFixed(0)}%`, color: "#f59e0b" },
    },
    {
      yAxis: thresholds.holdLine,
      lineStyle: { color: "#ef4444", type: "dashed" },
      label: { formatter: `Hold ${thresholds.holdLine.toFixed(0)}%`, color: "#ef4444" },
    },
  ];

  const actionSeries: LineSeriesOption = {
    name: "P(outside action)",
    type: "line",
    data: actionProbabilityPoints,
    showSymbol: false,
    connectNulls: false,
    lineStyle: { color: "#dc2626" },
  };

  if (segmentAreas.length) {
    actionSeries.markArea = {
      silent: true,
      itemStyle: { color: "rgba(148, 163, 184, 0.18)" },
      label: { show: !isKiosk.value, color: "#475569", fontSize: 11 },
      data: segmentAreas,
    };
  }

  const riskMarkLines: MarkLineData = [
    ...thresholdLines,
    ...eventLines,
  ];

  if (riskMarkLines.length) {
    actionSeries.markLine = {
      silent: true,
      symbol: "none",
      data: riskMarkLines,
    };
  }

  const warnSeries: LineSeriesOption = {
    name: "P(outside warn)",
    type: "line",
    data: warnProbabilityPoints,
    showSymbol: false,
    connectNulls: false,
    lineStyle: { color: "#f59e0b" },
  };

  if (segmentAreas.length) {
    warnSeries.markArea = {
      silent: true,
      itemStyle: { color: "rgba(148, 163, 184, 0.18)" },
      label: { show: !isKiosk.value, color: "#475569", fontSize: 11 },
      data: segmentAreas,
    };
  }

  const alertSeries: ScatterSeriesOption = {
    name: "Alerts",
    type: "scatter",
    data: alertPoints,
    symbolSize: 9,
    itemStyle: { color: "#7f1d1d" },
  };

  const riskOption: echarts.EChartsOption = {
    grid: {
      left: isKiosk.value ? "5%" : "6%",
      right: isKiosk.value ? "5%" : "8%",
      top: chartMode.value === "risk" ? "8%" : "4%",
      bottom: chartMode.value === "risk" ? "18%" : "24%",
      containLabel: true,
    },
    xAxis: {
      type: "time",
      axisLabel: { show: chartMode.value === "risk" || !isKiosk.value },
    },
    yAxis: {
      type: "value",
      name: chartMode.value === "risk" ? "Predictive exceedance (%)" : "Risk (%)",
      min: 0,
      max: 100,
      splitNumber: chartMode.value === "risk" ? 5 : 3,
      axisLabel: { formatter: "{value}%" },
    },
    series: [warnSeries, actionSeries, alertSeries],
    tooltip: {
      ...tooltipDisplayOptions(),
      trigger: "axis",
      triggerOn: "mousemove|click",
      formatter: (params: unknown) => {
        const items = asFormatterItems(params);
        const primary = items.find((item) => Array.isArray(item.value) && item.value.length === 2);
        const raw = primary?.value;
        if (!Array.isArray(raw) || raw.length !== 2) {
          return "";
        }
        const timestamp = String(raw[0]);
        const ts = Number.isFinite(Date.parse(timestamp))
          ? new Date(timestamp).toLocaleString()
          : timestamp;
        const lines = items
          .map((item) => {
            const value = item.value;
            if (!Array.isArray(value) || value.length !== 2) {
              return null;
            }
            const rawVal = Number(value[1]);
            if (!Number.isFinite(rawVal)) {
              return null;
            }
            const label = typeof item.seriesName === "string" ? item.seriesName : "Value";
            return `${label}: ${rawVal.toFixed(1)}%`;
          })
          .filter((line): line is string => Boolean(line));
        const helpLines = lines.length
          ? [
              BAYESIAN_RISK_MEANING,
              bayesianRiskBasisText("through this timestamp"),
              BAYESIAN_RISK_SCORE_MEANING,
            ]
          : [];
        return [ts, ...lines, ...helpLines].join("<br/>");
      },
    },
  };
  if (riskChart) {
    riskChart.setOption(riskOption);
  }
}

watch(useLogScale, async () => {
  if (suppressLogReload.value) {
    suppressLogReload.value = false;
    return;
  }
  await loadChart();
});

watch(chartMode, async () => {
  await ensureCharts();
  await loadChart();
});

watch(
  () => [
    props.forcedStreamId,
    props.forcedStart,
    props.forcedEnd,
    props.forcedMode,
    props.kioskDensity,
    props.refreshToken,
  ],
  async () => {
    if (!isKiosk.value) {
      return;
    }
    syncForcedKioskState();
    await ensureCharts();
    await loadChart();
  }
);

onMounted(async () => {
  window.addEventListener("resize", resizeCharts);
  syncForcedKioskState();
  await loadStreams();
  syncForcedKioskState();
  await ensureCharts();
  await loadChart();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeCharts);
  if (resizeTimer !== null) {
    window.clearTimeout(resizeTimer);
    resizeTimer = null;
  }
  resultsChart?.dispose();
  resultsChart = null;
  riskChart?.dispose();
  riskChart = null;
});
</script>

<style scoped>
.chart-panel-header {
  align-items: center;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin: -4px 0 12px;
  min-width: 0;
  padding-bottom: 12px;
}

.chart-panel-header h3 {
  font-size: 18px;
  line-height: 1.2;
  margin: 0 0 4px;
}

.chart-card {
  margin-bottom: 16px;
}

.chart-card:last-child {
  margin-bottom: 0;
}

.chart-page--kiosk {
  height: 100%;
  padding: 0;
  background: #111827;
}

.chart-card--kiosk {
  border: none;
  border-radius: 0;
}

.chart-card--kiosk :deep(.el-card__body) {
  padding: 8px 12px;
}

.risk-rail {
  border-top: 1px solid #e5e7eb;
  margin-top: 8px;
  padding-top: 8px;
}

.risk-rail-header {
  align-items: center;
  color: #475569;
  display: flex;
  font-size: 12px;
  font-weight: 600;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 2px;
}

.risk-rail-header span:last-child {
  color: #64748b;
  font-weight: 500;
  text-align: right;
}

.risk-rail--standalone {
  border-top: 0;
  margin-top: 0;
  padding-top: 0;
}

.risk-rail--kiosk {
  border-color: #334155;
}

.point-comment-context {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 16px;
}

.point-comment-context div {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  min-width: 0;
  overflow-wrap: anywhere;
  padding: 8px;
}

.point-comment-context span {
  color: #64748b;
  display: block;
  font-size: 12px;
}

.point-comment-context strong {
  display: block;
  margin-top: 2px;
}

@media (max-width: 760px) {
  .chart-panel-header,
  .risk-rail-header {
    align-items: stretch;
    flex-direction: column;
  }

  .risk-rail-header span:last-child {
    text-align: left;
  }

  .point-comment-context {
    grid-template-columns: 1fr;
  }
}
</style>
