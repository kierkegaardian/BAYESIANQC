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
      <el-button type="primary" @click="loadChart">Load</el-button>
    </div>

    <el-card>
      <div ref="chartRef" style="height: 420px"></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import * as echarts from "echarts";
import { api } from "../api/client";

const chartRef = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;

const streams = ref<any[]>([]);
const streamId = ref("");
const startDate = ref<Date | null>(null);
const endDate = ref<Date | null>(null);

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
  const query = buildParams();
  const data = await api.get(`/streams/${streamId.value}/chart?${query}`);
  const records = data.records || [];
  const alerts = data.alerts || [];
  const segments = data.lot_segments?.length
    ? data.lot_segments
    : deriveLotSegments(records);

  const seriesData = records.map((record: any) => ({
    value: [record.timestamp, record.result_value],
    lot: record.control_material_lot,
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
      lineStyle: { color: "#94a3b8", type: "dashed" },
      label: { color: "#475569", fontSize: 11 },
      data: lotLines,
    };
  }

  if (chart) {
    chart.setOption({
      xAxis: { type: "time" },
      yAxis: { type: "value", name: "Result" },
      series: [
        resultSeries,
        {
          name: "Alerts (risk)",
          type: "scatter",
          data: alertPoints,
          yAxisIndex: 0,
          symbolSize: 10,
          itemStyle: { color: "#dc2626" },
        },
      ],
      tooltip: {
        trigger: "axis",
        formatter: (items: any[]) => {
          const resultItem = items?.find((item) => item.seriesName === "Result");
          const lot = resultItem?.data?.lot;
          const value = resultItem?.data?.value?.[1];
          const timestamp = resultItem?.data?.value?.[0];
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
          return parts.join("<br/>");
        },
      },
    });
  }
}

onMounted(async () => {
  await loadStreams();
  if (chartRef.value) {
    chart = echarts.init(chartRef.value);
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
