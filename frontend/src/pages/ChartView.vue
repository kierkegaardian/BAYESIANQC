<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>QC Charts</h2>
        <div class="muted">Visualize QC results, alerts, and events.</div>
      </div>
      <el-button @click="loadChart">Refresh</el-button>
    </div>

    <div class="toolbar" style="margin-bottom: 16px">
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
      <el-switch v-model="useLogScale" active-text="Log scale" inactive-text="Linear" />
      <el-button type="primary" @click="loadChart">Load</el-button>
    </div>

    <el-card>
      <div ref="chartRef" style="height: 420px"></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";

const chartRef = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;

const streams = ref<any[]>([]);
const streamId = ref("");
const startDate = ref<Date | null>(null);
const endDate = ref<Date | null>(null);
const useLogScale = ref(false);
const suppressLogReload = ref(false);

function deriveLotSegments(records: any[]) {
  if (!records.length) {
    return [];
  }
  const segments = [];
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

function padSegmentEnd(start: string, end: string) {
  if (start !== end) {
    return end;
  }
  const startDate = new Date(start);
  return new Date(startDate.getTime() + 1000).toISOString();
}

async function loadStreams() {
  streams.value = await api.get("/streams");
  if (!streamId.value && streams.value.length) {
    streamId.value = streams.value[0].stream_id;
  }
}

async function updateResolution(
  recordId: number,
  includeInStats: boolean,
  reason?: string
) {
  try {
    await api.patch(`/qc/records/${recordId}/resolution`, {
      include_in_stats: includeInStats,
      resolved_reason: reason || null,
    });
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

function attachChartHandlers() {
  if (!chart) {
    return;
  }
  chart.off("click");
  chart.on("click", async (params: any) => {
    if (
      params?.seriesName !== "Result" &&
      params?.seriesName !== "High outliers" &&
      params?.seriesName !== "Low outliers"
    ) {
      return;
    }
    const recordId = Number(params?.data?.record_id);
    if (!recordId) {
      return;
    }
    const includeInStats = params?.data?.include_in_stats !== false;
    if (includeInStats) {
      const result = await ElMessageBox.prompt(
        "Why should this point be excluded from stats?",
        "Resolve QC Point",
        {
          confirmButtonText: "Resolve",
          cancelButtonText: "Cancel",
          inputPlaceholder: "e.g. reagent lot change or known variation",
        }
      ).catch(() => null);
      if (!result) {
        return;
      }
      await updateResolution(recordId, false, result.value);
      return;
    }
    const confirm = await ElMessageBox.confirm(
      "Re-include this point in statistics and Bayesian updates?",
      "Reinstate QC Point",
      {
        confirmButtonText: "Reinstate",
        cancelButtonText: "Cancel",
        type: "warning",
      }
    ).catch(() => null);
    if (!confirm) {
      return;
    }
    await updateResolution(recordId, true);
  });
}

function buildControlSeries(stream: any) {
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

  const markAreaData = [
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

  const markLineData = [
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

  const controlSeries: echarts.SeriesOption = {
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

  const yAxis = {
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
    params.set("start", startDate.value.toISOString());
  }
  if (endDate.value) {
    params.set("end", endDate.value.toISOString());
  }
  params.set("limit", "500");
  return params.toString();
}

async function loadChart() {
  if (!streamId.value) {
    return;
  }
  if (!streams.value.length) {
    await loadStreams();
  }
  const stream = streams.value.find((item) => item.stream_id === streamId.value);
  const query = buildParams();
  const data = await api.get(`/streams/${streamId.value}/chart?${query}`);
  const records = data.records || [];
  const alerts = data.alerts || [];
  const segments = data.lot_segments?.length
    ? data.lot_segments
    : deriveLotSegments(records);

  const controlConfig = buildControlSeries(stream);
  const limitMin = controlConfig?.minValue;
  const limitMax = controlConfig?.maxValue;
  const logScaleAllowed =
    records.every((record: any) => record.result_value > 0) &&
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
    records.some(
      (record: any) =>
        record.result_value < limitMin || record.result_value > limitMax
    );

  const seriesData = records.map((record: any) => ({
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
    itemStyle:
      record.include_in_stats === false
        ? { color: "#94a3b8" }
        : undefined,
  }));
  const alertPoints = alerts.map((alert: any) => [
    alert.created_at,
    alert.bayesian_risk?.risk_score ?? 0,
  ]);

  const segmentAreas = segments.map((segment: any) => [
    {
      xAxis: segment.start,
      label: { formatter: `Lot ${segment.control_material_lot}` },
    },
    { xAxis: padSegmentEnd(segment.start, segment.end) },
  ]);

  const lotLines = segments.slice(1).map((segment: any) => ({
    xAxis: segment.start,
    label: { formatter: `Lot ${segment.control_material_lot}` },
  }));

  const resultSeries: echarts.SeriesOption = {
    name: "Result",
    type: "line",
    data: seriesData,
    smooth: true,
    connectNulls: false,
    lineStyle: { color: "#2563eb" },
  };

  if (segmentAreas.length) {
    resultSeries.markArea = {
      silent: true,
      itemStyle: { color: "rgba(148, 163, 184, 0.18)" },
      label: { color: "#475569", fontSize: 11 },
      data: segmentAreas,
    };
  }

  if (lotLines.length) {
    resultSeries.markLine = {
      silent: true,
      symbol: "none",
      data: lotLines.map((segment: any) => ({
        ...segment,
        lineStyle: { color: "#94a3b8", type: "dashed" },
        label: { color: "#475569", fontSize: 11 },
      })),
    };
  }

  const highOutliers: any[] = [];
  const lowOutliers: any[] = [];
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
        };
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
    scale: true,
    min: "dataMin",
    max: "dataMax",
  };

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
        }
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
        }
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
        }
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
        }
      );
    }
  } else {
    grids.push({ left: "6%", right: "4%", top: "6%", bottom: "12%", containLabel: true });
    xAxes.push(baseXAxis(true));
    if (logScaleActive) {
      yAxes.push(logAxis);
    } else {
      yAxes.push(controlConfig?.yAxis || { type: "value", name: "Result" });
    }
  }

  if (controlConfig?.controlSeries) {
    controlConfig.controlSeries.xAxisIndex = mainAxisIndex;
    controlConfig.controlSeries.yAxisIndex = mainAxisIndex;
  }

  resultSeries.xAxisIndex = mainAxisIndex;
  resultSeries.yAxisIndex = mainAxisIndex;

  const series: echarts.SeriesOption[] = [
    ...(controlConfig?.controlSeries ? [controlConfig.controlSeries] : []),
    resultSeries,
  ];

  if (highOutliers.length && highAxisIndex !== null) {
    series.push({
      name: "High outliers",
      type: "scatter",
      data: highOutliers,
      symbol: "triangle",
      symbolSize: 12,
      xAxisIndex: highAxisIndex,
      yAxisIndex: highAxisIndex,
    });
  }

  if (lowOutliers.length && lowAxisIndex !== null) {
    series.push({
      name: "Low outliers",
      type: "scatter",
      data: lowOutliers,
      symbol: "triangle",
      symbolSize: 12,
      xAxisIndex: lowAxisIndex,
      yAxisIndex: lowAxisIndex,
    });
  }

  series.push({
    name: "Alerts (risk)",
    type: "scatter",
    data: alertPoints,
    xAxisIndex: mainAxisIndex,
    yAxisIndex: mainAxisIndex,
    symbolSize: 10,
    itemStyle: { color: "#dc2626" },
  });

  if (chart) {
    const axisPointer =
      !logScaleActive && controlConfig && (hasHighOutliers || hasLowOutliers)
        ? { link: [{ xAxisIndex: xAxes.map((_, index) => index) }] }
        : undefined;
    chart.setOption({
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      axisPointer,
      series,
      tooltip: {
        trigger: "axis",
        formatter: (items: any[]) => {
          const recordItem = items?.find(
            (item) => item?.data?.record_id
          );
          if (!recordItem) {
            return "";
          }
          const lot = recordItem?.data?.lot;
          const value = recordItem?.data?.value?.[1];
          const timestamp = recordItem?.data?.value?.[0];
          const includeInStats = recordItem?.data?.include_in_stats !== false;
          const resolvedReason = recordItem?.data?.resolved_reason;
          const parts = [];
          if (timestamp) {
            parts.push(new Date(timestamp).toLocaleString());
          }
          if (value !== undefined) {
            parts.push(`Result: ${value}`);
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
    });
  }
}

watch(useLogScale, async () => {
  if (suppressLogReload.value) {
    suppressLogReload.value = false;
    return;
  }
  await loadChart();
});

onMounted(async () => {
  await loadStreams();
  if (chartRef.value) {
    chart = echarts.init(chartRef.value);
    attachChartHandlers();
  }
  await loadChart();
});

onBeforeUnmount(() => {
  if (chart) {
    chart.dispose();
    chart = null;
  }
});
</script>
