<template>
  <div class="page chart-page" :class="{ 'chart-page--kiosk': isKiosk }">
    <div v-if="!isKiosk" class="page-header">
      <div>
        <h2>QC Charts</h2>
        <div class="muted">Visualize QC results, alerts, and events.</div>
      </div>
      <el-button :loading="loading" @click="loadChart">Refresh</el-button>
    </div>

    <div v-if="!isKiosk" class="toolbar chart-toolbar">
      <el-select v-model="streamId" aria-label="QC stream" placeholder="Select stream" class="stream-select">
        <el-option
          v-for="stream in streams"
          :key="stream.stream_id"
          :label="stream.stream_id"
          :value="stream.stream_id"
        />
      </el-select>
      <el-date-picker v-model="startDate" type="date" placeholder="Start date" aria-label="Chart start date" />
      <el-date-picker v-model="endDate" type="date" placeholder="End date" aria-label="Chart end date" />
      <el-radio-group v-model="chartMode" size="small" aria-label="Chart mode">
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
      <el-button type="primary" :loading="loading" @click="loadChart">Load</el-button>
    </div>

    <el-alert v-if="error" type="error" :closable="false" show-icon class="chart-error">
      <template #title>Chart data could not be loaded: {{ error }}</template>
      <el-button size="small" :loading="loading" @click="loadChart">Retry</el-button>
    </el-alert>

    <el-card :class="['chart-card', { 'chart-card--kiosk': isKiosk }]">
      <div v-if="!isKiosk" class="chart-panel-header">
        <div>
          <h3>{{ currentStreamLabel }}</h3>
          <div class="muted">{{ chartSubtitle }}</div>
        </div>
        <ChartRiskBadge :summary="latestRiskSummary" />
      </div>

      <ChartLegend v-if="!isTileKiosk" :mode="chartMode" />
      <div
        v-show="chartMode !== 'risk'"
        ref="resultsChartRef"
        :style="resultsChartStyle"
        role="img"
        :aria-label="resultsChartAriaLabel"
      ></div>
      <div
        class="risk-rail"
        :class="{ 'risk-rail--standalone': chartMode === 'risk', 'risk-rail--kiosk': isKiosk }"
      >
        <div v-if="!isKiosk" class="risk-rail-header">
          <span>Bayesian predictive risk</span>
          <span>{{ latestRiskSummary?.detailLabel ?? "No risk history" }}</span>
        </div>
        <div
          ref="riskChartRef"
          :style="riskChartStyle"
          role="img"
          :aria-label="riskChartAriaLabel"
        ></div>
      </div>
      <ChartDataTable v-if="!isKiosk" :records="chartRecords" @select="selectRecord" />
    </el-card>

    <ChartPointDialog
      :model-value="dialogOpen"
      :point="selectedPoint"
      :kiosk="isKiosk"
      @update:model-value="setDialogOpen"
      @resolved="loadChart"
    />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount } from "vue";
import ChartDataTable from "./ChartDataTable.vue";
import ChartLegend from "./ChartLegend.vue";
import ChartPointDialog from "./ChartPointDialog.vue";
import ChartRiskBadge from "./ChartRiskBadge.vue";
import { useChartController, type ChartViewProps } from "./useChartController";
import { useChartPointSelection } from "./useChartPointSelection";
import type { ChartRiskSummary } from "./chartRisk";

const props = withDefaults(defineProps<ChartViewProps>(), { kiosk: false });
const emit = defineEmits<{
  "risk-summary": [summary: ChartRiskSummary | null];
  "interaction-active": [active: boolean];
}>();
const { dialogOpen, handleChartClick, selectRecord, selectedPoint, setDialogOpen } =
  useChartPointSelection((active) => emit("interaction-active", active));
const {
  chartMode, chartRecords, chartSubtitle, currentStreamLabel, endDate, error, isKiosk,
  isTileKiosk, latestRiskSummary, loadChart, loading, resultsChartAriaLabel,
  resultsChartRef, resultsChartStyle, riskChartAriaLabel, riskChartRef, riskChartStyle,
  startDate, streamId, streams, useLogScale,
} = useChartController(props, (summary) => emit("risk-summary", summary), handleChartClick);

onBeforeUnmount(() => emit("interaction-active", false));
</script>

<style scoped src="./chartView.css"></style>
