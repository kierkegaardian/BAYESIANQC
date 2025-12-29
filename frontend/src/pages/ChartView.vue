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

  const seriesData = records.map((record: any) => [
    record.timestamp,
    record.result_value,
  ]);
  const alertPoints = alerts.map((alert: any) => [
    alert.created_at,
    alert.bayesian_risk?.risk_score ?? 0,
  ]);

  if (chart) {
    chart.setOption({
      xAxis: { type: "time" },
      yAxis: { type: "value", name: "Result" },
      series: [
        {
          name: "Result",
          type: "line",
          data: seriesData,
          smooth: true,
          lineStyle: { color: "#2563eb" },
        },
        {
          name: "Alerts (risk)",
          type: "scatter",
          data: alertPoints,
          yAxisIndex: 0,
          symbolSize: 10,
          itemStyle: { color: "#dc2626" },
        },
      ],
      tooltip: { trigger: "axis" },
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
