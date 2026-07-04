<template>
  <section class="kiosk-chart-tile">
    <header class="tile-header">
      <div class="tile-title">
        <h2>{{ panel.title }}</h2>
        <div>{{ panel.streamId }} · {{ panel.windowLabel }}</div>
      </div>
      <div class="tile-actions">
        <ChartRiskBadge :summary="riskSummary" kiosk />
        <el-button size="small" @click="emit('open-single', panel.streamId)">Open</el-button>
      </div>
    </header>

    <ChartView
      kiosk
      kiosk-density="tile"
      :forced-stream-id="panel.streamId"
      :forced-start="panel.start"
      :forced-end="panel.end"
      :forced-mode="mode"
      :refresh-token="refreshToken"
      @risk-summary="updateRiskSummary"
    />
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import ChartRiskBadge from "./ChartRiskBadge.vue";
import ChartView from "./ChartView.vue";
import type { ChartRiskSummary } from "./chartRisk";
import type { KioskPanel } from "./kioskPanels";
import type { ChartMode } from "./kioskRuntime";

const props = defineProps<{
  panel: KioskPanel;
  mode: ChartMode;
  refreshToken: number;
}>();
const emit = defineEmits<{
  "open-single": [streamId: string];
}>();

const riskSummary = ref<ChartRiskSummary | null>(null);

function updateRiskSummary(summary: ChartRiskSummary | null): void {
  riskSummary.value = summary;
}

watch(
  () => [props.panel.streamId, props.refreshToken],
  () => {
    riskSummary.value = null;
  }
);
</script>

<style scoped>
.kiosk-chart-tile {
  background: #0f172a;
  border: 1px solid #334155;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.tile-header {
  align-items: center;
  border-bottom: 1px solid #334155;
  display: flex;
  gap: 10px;
  justify-content: space-between;
  min-height: 56px;
  padding: 8px 10px;
}

.tile-title {
  min-width: 0;
}

.tile-title h2 {
  color: #f8fafc;
  font-size: 16px;
  line-height: 1.15;
  margin: 0 0 3px;
}

.tile-title div {
  color: #cbd5e1;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tile-actions {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

:deep(.chart-page--kiosk) {
  background: transparent;
}

:deep(.chart-card) {
  margin-bottom: 0;
}

:deep(.chart-card--kiosk) {
  border-radius: 0;
}

:deep(.risk-badge--kiosk) {
  border-radius: 4px;
  min-width: 118px;
  padding: 5px 8px;
}

:deep(.risk-badge--kiosk strong) {
  font-size: 14px;
}

:deep(.risk-badge--kiosk span),
:deep(.risk-badge--kiosk .risk-badge__eyebrow) {
  font-size: 10px;
}
</style>
